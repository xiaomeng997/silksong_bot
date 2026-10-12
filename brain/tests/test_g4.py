"""Task 1v1 G4: hits first (SSBOT_FORUM_HITS_FIRST), keep once chosen (SSBOT_FORUM_SPECIAL_KEEP), the move path's
hits (SSBOT_FORUM_MOVE_HITS), the family's bounce convention (SSBOT_FORUM_DSLASH_EVPRE) and the table v2's native
cells (specials.Lut)."""
import math
from types import SimpleNamespace as NS

import numpy as np

from ssbot.combat import dslash
from ssbot.combat import special_mode as sm
from ssbot.combat import specials
from ssbot.combat.forum_planner import ForumConfig, ForumPlanner
from ssbot.combat.planner import PlannerConfig
from ssbot.knowledge import kinematics as kin
from tests.test_dslash import _tick, params  # noqa: F401
from tests.test_forum_planner import arena  # noqa: F401


def test_move_hits_follow_the_template(params, arena):  # noqa: F811
    """The scorer's body of an enemy in a tracked move follows the template's displacement still to come (the mean
    over its branches), not its present velocity."""
    pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2), ForumConfig(v2=True), crest="Wanderer")
    nb = 200
    tps = {("F", "a"): NS(disp=np.stack([0.10 * np.arange(nb), np.zeros(nb)], 1), ratio=None, nb=nb),
           ("F", "b"): NS(disp=np.stack([0.30 * np.arange(nb), 0.05 * np.arange(nb)], 1), ratio=None, nb=nb)}
    tab = NS(spec=NS(branches={"F": ("a", "b")}, aim=set()), templates=tps, walls=(-1e9, 1e9), landing=lambda d: 0.0)
    inst = NS(fam="F", branch=None, t0=0.0, x0=30.0, y0=5.0, s=1, hero_du=0.0)
    trk = NS(now={7: ("T", {}, inst)}, tables={"T": tab}, T=10 / 60)
    T1 = 30
    vel = np.stack([30.0 + 0.5 * np.arange(T1), np.full(T1, 5.0), 31.0 + 0.5 * np.arange(T1), np.full(T1, 7.0)], 1)
    out = pl._move_hit_paths(NS(rs=NS(trk=trk)), [NS(hazard=False, iid=7)], vel[None].copy())
    k = np.arange(T1)
    assert np.allclose(out[0, :, 0], 30.0 + 0.2 * k) and np.allclose(out[0, :, 1], 5.0 + 0.025 * k)
    # an enemy not in a move keeps its body
    same = pl._move_hit_paths(NS(rs=NS(trk=trk)), [NS(hazard=False, iid=8)], vel[None].copy())
    assert np.array_equal(same, vel[None])


def test_evpre_puts_the_bounce_on_the_contact_frame(params, arena, monkeypatch):  # noqa: F811
    monkeypatch.setattr(dslash, "EVPRE", True)
    pl, _ = _tick(params, arena, {}, monkeypatch=monkeypatch)
    ds = pl._ds
    q = int(np.flatnonzero(ds.cert)[0])
    assert ds.ev[q, ds.c1[q] - 1] & kin.EV_POGO and not ds.ev[q, ds.c1[q]] & kin.EV_POGO


def test_hits_first_envelopes_fewer_rows_and_keeps_the_hits(params, arena, monkeypatch):  # noqa: F811
    pl0, r0 = _tick(params, arena, {}, monkeypatch=monkeypatch)
    monkeypatch.setattr(sm, "HITS_FIRST", True)
    pl1, r1 = _tick(params, arena, {}, monkeypatch=monkeypatch)
    a = pl1.audit
    assert a.hf_ticks == 1 and a.hf_stop == 1 and a.hf_skipped > 0
    assert a.rows_enveloped < pl0.audit.rows_enveloped
    nh0 = float(np.asarray(pl0.last_sel["nh"])[r0.idx])
    nh1 = float(np.asarray(pl1.last_sel["nh"])[r1.idx])
    assert not r1.S and nh1 >= nh0 and nh1 >= 2                        # a chain passed: two hits


def test_keep_skips_the_search_and_keeps_the_row(params, arena, monkeypatch):  # noqa: F811
    monkeypatch.setattr(sm, "KEEP", True)
    pl, r = _tick(params, arena, {}, monkeypatch=monkeypatch)
    assert r.name.startswith("DS ") and pl._kp == "ds"
    from tests.test_dslash import FLOOR, RX, _support, _reed_forecaster, _world, _prefs, _ctx
    from ssbot.combat import forum_v2 as v2
    inst = NS(fam="RE_STAB", branch=None, t0=0.0, x0=RX, y0=FLOOR + 1.0, s=-1, hero_du=0.0)
    from tests.test_dslash import _Tab
    trk = NS(now={7: ("Song Reed", {"pos": (RX, FLOOR + 1.0), "type_key": "Song Reed"}, inst)},
             tables={"Song Reed": _Tab(0.0)}, hero=None, T=1 / 60)
    f = v2.V2Forecast(_reed_forecaster(None, x=RX).forecast(0.8), _support({}, trk))
    st = kin.rollout(kin.initial_state(params, 34.0, FLOOR + params.foot), np.asarray(r.cmd[:1])[None], params,
                     arena).final
    r2 = pl.tick(_world(34.0), st, kin.HoldState.idle(1), np.zeros(1, np.int64), f, _prefs(None, 34.0), _ctx())
    a = pl.audit
    assert a.kp_ticks == 1 and a.kp_skip == 1
    assert (r2.name == "DS cont" and a.kp_kept == 1) or (a.kp_sw_gone + a.kp_sw_unsafe + a.kp_sw_escape == 1)


def test_v2_lut_reads_native_cell_runs():
    e = specials.Entry(id="x", type_key="T", move="CL_SLAM", kind="down", k0=10, k1=10, dx0=1.0, dx1=1.25, dy0=0.5,
                       dy1=1.25, vy=1, key=0, jpost=0, cert="bounce", share=0.9, hits=1, region="r", slack_t=4)
    lut = specials.Lut([e], rank_cert=False, cell=(0.25, 0.25))
    k = np.array([10, 10, 10, 10, 11])
    dy = np.array([0.6, 0.9, 1.2, 1.3, 0.6])
    got = lut.find(k, np.full(5, 1.1), dy, np.ones(5, np.int64))
    assert list(got) == [0, 0, 0, -1, -1]
    assert math.isclose(lut.rank[0], 10.9 + 0.04)


def test_v2_core_late_only_and_regions():
    """specials_v2: a core cell needs its late frames (none earlier) and the space around it free of bad cells; the
    regions are the connected cores."""
    from ssbot.tools.specials_v2 import _erode, _late_run, label
    g = np.zeros((10, 7, 7), bool)
    g[2:8, 1:6, 1:6] = True
    core = _erode(g, 3, 1)
    ks = np.flatnonzero(core.any(axis=(1, 2)))
    assert list(ks) == [2, 3, 4]                      # frames 5..7 lack 3 good frames after them; frame 1 not needed
    assert core[2, 2:5, 2:5].all() and not core[2, 1].any()
    assert _late_run(g)[2, 3, 3] == 5
    lab, n = label(core)
    assert n == 1 and (lab > 0).sum() == core.sum()
