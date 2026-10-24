"""Map v2 stage T3: the A1_n tables as the search's envelope (search.Cfg.tables, World.envelope, the library's growth
budget and reset, the long pass, LiveCfg.tables) - the switch off is the engine; on, the same clusters."""
from __future__ import annotations

import threading

import numpy as np
import pytest

from ssbot.knowledge import kinematics as km
from ssbot.map2 import clapper as cm
from ssbot.map2 import envelope as env
from ssbot.map2 import search as ms
from ssbot.map2 import strike as sk
from ssbot.map2 import tables as tb
from ssbot.tools import m1_envelope as m1
from ssbot.tools import t1_tables as t1


@pytest.fixture(scope="module")
def W():
    """A World whose table library is a fresh (lazily expanded) search library - not the knowledge file."""
    w = ms.World()
    lib = tb.Lib(claw=False, terrain="arena")
    lib.mark()
    w.__dict__["_lib"] = lib
    return w


def _ground(W, x=30.0, alpha=0.5):
    return km.initial_state(W.params, x, sk.FLOOR + sk.FOOT, ground=True, alpha=alpha)


def _air(W, x=30.0, y=6.0, vy=-3.0):
    return km.initial_state(W.params, x, y, ground=False, vy=vy, facing=1)


def _same_fwd(a, b) -> bool:
    names = ("cl_off", "cl_y", "cl_vy", "cl_cond", "cl_iv0", "cl_ivn", "IV", "pc_cl", "pc_par", "pc_cand", "pc_lo",
             "pc_hi")
    return all(np.array_equal(getattr(a, n), getattr(b, n)) for n in names)


def test_envelope_off_is_the_engine(W):
    """tables off: World.envelope is the engine's pass, bit for bit (the switch off changes nothing)."""
    rng = np.random.default_rng(5)
    for S in (_ground(W), _air(W)):
        dz = m1.random_danger(rng, S, 30, W.E.hh)
        a = W.envelope(S, 30, dz, 2)
        b = W.E.forward(W.E.start_state(S), 30, danger=dz, terrain=W.TT, max_events=2, claw=False)
        assert _same_fwd(a, b)


@pytest.mark.parametrize("mev,T", [(1, 60), (2, 30)])
def test_envelope_tables_equal_the_engine(W, mev, T):
    """tables on: the chain with the dash bridge has the engine's clusters (heights bit-equal, x within 1e-9 u)."""
    rng = np.random.default_rng(7)
    for S in (_ground(W, 22.0), _air(W, 35.0, 7.0, 2.0), _ground(W, 40.0, 0.1)):
        dz = m1.random_danger(rng, S, T, W.E.hh)
        fe = W.envelope(S, T, dz, mev)
        ft = W.envelope(S, T, dz, mev, tables=True)
        assert getattr(ft, "lib_stats", None) is not None           # (the tables' Fwd)
        r = t1.compare(fe, ft, T)
        assert r["ok"], r


def test_reset_restores_the_library(W):
    """Lib.reset drops the growth since the mark: the counts return, a pass made before the mark is all warm again (no
    expansion) and the same arrays."""
    lib = W.table_lib()
    S0 = _ground(W, 26.0)
    a = W.envelope(S0, 30, None, 2, tables=True)
    lib.mark()
    n0, e0 = lib.n_nodes, lib.n_edges
    for S in (_air(W, 20.0, 8.0, 5.0), _ground(W, 33.0, 0.3), _air(W, 41.0, 5.0, -8.0)):
        W.envelope(S, 40, None, 2, tables=True)
    assert lib.grown() > 0
    lib.reset()
    assert (lib.n_nodes, lib.n_edges, lib.grown()) == (n0, e0, 0)
    b = W.envelope(S0, 30, None, 2, tables=True)
    assert b.lib_stats["expanded"] == 0 and b.lib_stats["new_nodes"] == 0
    assert _same_fwd(a, b)
    # the dropped nodes come back exactly when met again
    S = _air(W, 20.0, 8.0, 5.0)
    c = W.envelope(S, 40, None, 2, tables=True)
    assert t1.compare(W.envelope(S, 40, None, 2), c, 40)["ok"]


def test_busy_library_falls_back_to_the_engine(W):
    """An exit check while another thread's pass holds the library: the engine's pass (the same clusters)."""
    lib = W.table_lib()
    S = _air(W, 30.0, 6.0, 0.0)
    got = {"done": threading.Event()}
    ev = threading.Event()

    def hold():
        with lib.lock:
            ev.set()
            got["done"].wait(10.0)
    th = threading.Thread(target=hold)
    th.start()
    ev.wait(5.0)
    b0 = ms.TABLE_STATS.get("busy", 0)
    fw = W.envelope(S, 20, None, 1, tables=True, blocking=False)
    got["done"].set()
    th.join()
    assert ms.TABLE_STATS.get("busy", 0) == b0 + 1
    assert getattr(fw, "lib_stats", None) is None                   # (the engine's Fwd)
    assert t1.compare(fw, W.envelope(S, 20, None, 1, tables=True), 20)["ok"]


def _sit(W):
    S = _ground(W, 26.0)
    o = cm.Obs(1, "Idle", 8 / 60.0, 33.0, cm.STAND_Y, 0.0, 0.0, -1, 230, None, j=8)
    return ms.Situation(S, [o], {1: cm.Memory()})


def test_search_with_tables_same_decision(W):
    """One decision on a virtual clock with the tables and without: the same tried plans and the same choice (the
    same clusters - here also the same order)."""
    sit = _sit(W)
    out = []
    for tables in (False, True):
        ms._GROWN.clear()
        ms._SLABS.clear()
        S = ms.Searcher(W, ms.Cfg(cap_s=0.4, depth=2, tables=tables))
        S.vclock = 0.01
        r = S.decide(sit)
        out.append([(e.plan.key(), round(float(e.value), 9), bool(e.safe)) for e in r.tried])
    assert out[0] == out[1]


def test_long_pass_windows_after_t_from(W):
    """A long pass (events, frames, t_from): its windows only after frame t_from; the passes before it unchanged."""
    sit = _sit(W)
    S = ms.Searcher(W, ms.Cfg(passes=((1, 60), (1, 120, 60)), tables=True))
    rt = S.root(sit)
    fws = S.passes(rt)
    assert fws[0].T == 60 and fws[1].T == 120 and getattr(fws[1], "t_from", 0) == 60
    w0, w1 = S.windows(rt, fws[0]), S.windows(rt, fws[1])
    assert w1 and all(c[1] > 60 for c in w1)
    S2 = ms.Searcher(W, ms.Cfg(passes=((1, 60),), tables=True))
    assert S2.windows(rt, S2.passes(rt)[0]) == w0


def test_budget_reset_at_a_decision(W):
    """Cfg.tables_budget: a decision starting with the library grown past the budget resets it first."""
    lib = W.table_lib()
    lib.mark()
    W.envelope(_air(W, 24.0, 9.0, 4.0), 40, None, 2, tables=True)
    assert lib.grown() > 10
    r0 = ms.TABLE_STATS.get("resets", 0)
    S = ms.Searcher(W, ms.Cfg(cap_s=0.05, depth=1, tables=True, tables_budget=10))
    S.vclock = 0.01
    S.decide(_sit(W))
    assert ms.TABLE_STATS.get("resets", 0) == r0 + 1


def test_live_search_kw():
    """LiveCfg -> the worker's search configuration: nothing by default (the switch off), the tables and the passes
    when set."""
    from ssbot.map2 import live as lv
    assert lv.search_kw(lv.LiveCfg()) == {}
    kw = lv.search_kw(lv.LiveCfg(tables=True, tables_budget=1000, passes="1:60/2:30/1:120:60"))
    assert kw["tables"] is True and kw["tables_budget"] == 1000
    assert kw["passes"] == ((1, 60), (2, 30), (1, 120, 60))
    c = ms.Cfg.live(**kw)
    assert c.tables and c.passes[2] == (1, 120, 60) and c.pass2_after == 6
