"""Map v2 stage E1 (HANDOFF 'Task map2 - the evaluation and the handover - stage E1'): the fast evaluation's switches.
fast_danger (the danger lists from each branch's all-frames arrays, the shapes' caches keyed by bytes, robust_boxes /
union_tops compiled, a record's hammer shapes made once) and fast_windows (the windows' prefilter) give the same
boxes / windows / decisions, bit for bit; witness_fast changes only when the witness's wide beam fires; the live
configuration passes the switches only when on."""
from __future__ import annotations

import hashlib

import numpy as np
import pytest

from ssbot.knowledge import kinematics as km
from ssbot.map2 import clapper as cm
from ssbot.map2 import search as ms
from ssbot.map2 import strike as sk

C = 33.0


@pytest.fixture(scope="module")
def W():
    return ms.World()


@pytest.fixture(autouse=True)
def _flags_off():
    yield
    ms.FAST_DZ[0] = False
    sk.FAST[0] = False


def _obs(st, x, face=-1, j=2, iid=1):
    return cm.Obs(iid, st, j / 60.0, x, cm.STAND_Y, 0.0, 0.0, face, 230, None, j=j)


def _ground(W, x, face=1):
    return km.initial_state(W.params, x, sk.FLOOR + sk.FOOT, ground=True, facing=face)


def _sits(W):
    """An Idle Clapper, a slam antic (the hammers), a cast antic (the bombs), a jump cast antic (the big rune), two."""
    out = [ms.Situation(_ground(W, C - 5.0), [_obs("Idle", C, j=8)], {1: cm.Memory()}, name="idle5"),
           ms.Situation(_ground(W, C - 7.0), [_obs("Slam Antic", C, j=3)], {1: cm.Memory()}, name="slam7"),
           ms.Situation(_ground(W, C - 9.0), [_obs("Spell Antic", C, j=2)], {1: cm.Memory()}, name="cast9"),
           ms.Situation(_ground(W, C - 9.0), [_obs("Cast Slam Antic", C, j=2)], {1: cm.Memory()}, name="jcast9")]
    o1, o2 = _obs("Slam Antic", 40.0, j=10, iid=1), _obs("Walk", 26.0, face=1, j=5, iid=2)
    out.append(ms.Situation(_ground(W, 33.0), [o1, o2], {1: cm.Memory(), 2: cm.Memory()}, name="two"))
    return out


def _bits(a):
    a = np.asarray(a, np.float64).reshape(-1, 4)
    return a.shape, a.tobytes()


def _collect(W, sit, fast: bool) -> dict:
    ms._GROWN.clear()
    ms._SLABS.clear()
    S = ms.Searcher(W, ms.Cfg.live(fast_danger=fast))
    rt = S.root(sit)
    pred = rt.pred
    out = {}
    for H in (60, 30):
        out[("union", H)] = [_bits(x) for x in ms._union_danger(pred, rt.k0, H, True, None)]
    iids = ms._alive(pred)
    out[("union_skip",)] = [_bits(x) for x in ms._union_danger(pred, rt.k0, 60, True, (iids[0], 25))]
    for bi, b0 in enumerate(pred.branches):
        for vi, b in enumerate(ms.timing_views(b0)):
            for (k0, H, ifu) in ((0, 40, -1), (20, 40, 26), (45, 180, -1)):
                dz, boxes, off = ms._packed_danger(b, k0, H, ifu, True)
                out[("packed", bi, vi, k0, H, ifu)] = ([_bits(x) for x in dz], _bits(boxes), off.tolist())
            for k in (0, 7, 33, 61, 120):
                out[("bd", bi, vi, k)] = _bits(ms.branch_danger(b, k, True))
                out[("bdskip", bi, vi, k)] = _bits(ms.branch_danger(b, k, True, (iids[0],)))
            for iid in iids:
                out[("robust", bi, vi, iid)] = sk.robust_boxes(b, iid, pred.T).tobytes()
                out[("tops", bi, vi, iid)] = sk.union_tops(b, iid, pred.T).tobytes()
            g = ms.geo(b, True)
            out[("rare", bi, vi)] = [(int(k), [(s.name, s.poly.tobytes() if s.poly is not None else s.box)
                                               for (s, _) in g.rare[int(k)]]) for k in g.rare_k]
    return out


def test_fast_danger_is_bit_identical(W):
    n_rare = n_circle = 0
    for sit in _sits(W):
        A = _collect(W, sit, False)
        B = _collect(W, sit, True)
        assert set(A) == set(B), sit.name
        for k in A:
            assert A[k] == B[k], (sit.name, k)
        n_rare += sum(len(v) for k, v in A.items() if k[0] == "rare")
        n_circle += sum(1 for k, v in A.items() if k[0] == "bd" and v[0][0] > 4)
    assert n_rare > 0                      # (the hammers were exercised)


def test_fast_windows_are_the_same(W):
    for sit in _sits(W):
        S0 = ms.Searcher(W, ms.Cfg.live(fast_danger=True))
        rt = S0.root(sit)
        S1 = ms.Searcher(W, ms.Cfg.live(fast_danger=True, fast_windows=True))
        for fw in S0.passes(rt):
            a = [tuple(c[:7]) for c in S0.windows(rt, fw)]
            b = [tuple(c[:7]) for c in S1.windows(rt, fw)]
            assert a == b, sit.name


def _digest(res) -> str:
    rows = [(repr(e.plan.key()), round(float(e.value), 9), bool(e.safe), bool(e.finished)) for e in res.tried]
    return hashlib.md5(repr(rows).encode()).hexdigest()


def test_decisions_identical_with_the_exact_switches(W):
    for sit in _sits(W)[:4]:
        out = []
        for kw in ({}, {"fast_danger": True, "fast_windows": True}):
            ms._GROWN.clear()
            ms._SLABS.clear()
            S = ms.Searcher(W, ms.Cfg.live(pass2_bg=False, fwd_threads=0, **kw))
            S.vclock = 0.01
            out.append(_digest(S.decide(sit, cap_s=0.4)))
        assert out[0] == out[1], sit.name


def test_witness_wide_tol(W):
    """witness_fast: the wide beam only past WITNESS_TOL - the default (0.01 u, T4) unchanged; a result is the
    24-beam's whenever its miss is within the tolerance."""
    sit = _sits(W)[0]
    S = ms.Searcher(W, ms.Cfg.live())
    assert S._wide_tol() == 0.01
    S2 = ms.Searcher(W, ms.Cfg.live(witness_fast=True))
    assert S2._wide_tol() == ms.WITNESS_TOL
    rt = S.root(sit)
    fw = S.passes(rt)[0]
    g, x0, x1, y0, y1 = fw.frame_rows(40)
    for i in range(0, len(g), max(1, len(g) // 8)):
        x = 0.5 * (x0[i] + x1[i])
        a = fw.witness(40, x, y1[i], tol_y=1e-6, attack_ok=False)
        b = fw.witness(40, x, y1[i], tol_y=1e-6, attack_ok=False, wide_tol=0.01)
        assert (a is None) == (b is None)
        if a is not None:
            assert np.array_equal(a["masks"], b["masks"])
            c = fw.witness(40, x, y1[i], tol_y=1e-6, attack_ok=False, wide_tol=ms.WITNESS_TOL)
            if abs(a["miss_x"]) <= 0.01:
                assert np.array_equal(a["masks"], c["masks"])
            # (the 24-beam's keys within the tolerance, or the same keys as T4's - the wide beam ran in both)
            assert np.array_equal(a["masks"], c["masks"]) or abs(c["miss_x"]) <= ms.WITNESS_TOL + 1e-9


def test_fg_nowait_takes_the_engine_when_the_library_is_busy(W):
    """fg_nowait (tables on): a foreground pass while the library's lock is held is the engine's - the same clusters."""
    sit = _sits(W)[1]
    cfg = ms.Cfg.live(tables=True, fg_nowait=True)
    lib = W.table_lib(cfg.tables_file, cfg.tables_budget)
    if lib is None:
        pytest.skip("no table library")
    S = ms.Searcher(W, cfg)
    rt = S.root(sit)
    a = S.passes(rt, (0,))[0]
    import threading
    held, done = threading.Event(), threading.Event()

    def hold():                                  # (another thread holds the library: the lock is re-entrant)
        with lib.lock:
            held.set()
            done.wait(30)
    th = threading.Thread(target=hold, daemon=True)
    th.start()
    held.wait(10)
    n0 = ms.TABLE_STATS.get("busy", 0)
    try:
        b = S.passes(rt, (0,))[0]
    finally:
        done.set()
        th.join(10)
    assert ms.TABLE_STATS.get("busy", 0) == n0 + 1
    for t in (1, 20, 60):                         # (the chain = the engine: heights bit-equal, x within 1e-9 u)
        ra, rb = a.frame_rows(t), b.frame_rows(t)
        assert len(ra[0]) == len(rb[0])
        assert np.array_equal(np.sort(ra[4]), np.sort(rb[4]))
        assert np.allclose(np.sort(ra[1]), np.sort(rb[1]), atol=1e-9, rtol=0)
        assert np.allclose(np.sort(ra[2]), np.sort(rb[2]), atol=1e-9, rtol=0)


def test_live_config_passes_the_switches_only_when_on():
    from ssbot.map2 import live as lv
    kw = lv.search_kw(lv.LiveCfg())
    assert not any(k in kw for k in ("fast_danger", "fast_windows", "witness_fast", "fg_nowait", "shapes"))
    kw = lv.search_kw(lv.LiveCfg(fast_danger=True, fast_windows=True, witness_fast=True, fg_nowait=True))
    assert kw["fast_danger"] and kw["fast_windows"] and kw["witness_fast"] and kw["fg_nowait"] and "shapes" not in kw
    c = ms.Cfg.live(**kw)
    assert c.fast_danger and c.fast_windows and c.witness_fast and c.fg_nowait
