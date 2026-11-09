"""Task 182 seq 309: FORCED_RISK while a Clapper's CC_SLAM is visible: no new umbrella while a row without one is allowed, and the committed share reads the v2 range support of the hammer's unit (the fine placements end before the strike)."""
import math
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import forum_planner as fp, forum_v2 as v2
from ssbot.combat.forum_planner import ForumConfig, ForumPlanner, slam_range_share, visible_slam_units
from ssbot.combat.planner import PlannerConfig
from ssbot.knowledge import kinematics as kin
from tests.test_forum_planner import FLOOR, _ctx, _prefs, _reed_forecaster, _world, arena, params  # noqa: F401
from tests.test_forum_v2 import _support_with

SLAM_IID, OTHER = 100, 101


def trk(*insts):
    return NS(now={iid: (name, {"pos": (30.0, FLOOR + 1.0)}, inst) for iid, name, inst in insts})


def test_visible_slam_units_takes_only_a_clapper_in_a_cc_slam_instance():
    t = trk((7, v2.CLAPPER, NS(fam="CC_SLAM")), (3, v2.CLAPPER, NS(fam="CC_SLAM")), (4, v2.CLAPPER, NS(fam="CC_CAST")),
            (5, v2.CLAPPER, None), (6, "Song Reed", NS(fam="CC_SLAM")))
    assert visible_slam_units(NS(rs=NS(trk=t))) == [3, 7]


@pytest.mark.parametrize("f", [NS(), NS(rs=NS()), NS(rs=NS(trk=NS(now={}))), NS(rs=NS(trk=NS(now=None)))])
def test_no_v2_tracker_is_no_slam(f):
    assert visible_slam_units(f) == []


def test_share_reads_the_units_support_at_the_sampled_frames():
    # box [rows, T1, 4] : a row's centre is its x0 + 0.5, y0 + 0.5
    box = np.zeros((3, 4, 4))
    for i in range(3):
        for k in range(4):
            box[i, k] = (10.0 * i + k, 1.0, 10.0 * i + k + 1.0, 2.0)
    inv = np.zeros((3, 4), bool)
    inv[2, 3] = True
    seen = {}

    def occupied_only(x, y, tk, iids):
        seen.update(x=np.array(x), y=np.array(y), tk=np.array(tk), iids=list(iids))
        return np.array([[False, True], [True, True]])

    rows = np.array([0, 2])
    fr = np.array([1, 3])
    tk = np.array([0.0, 0.1, 0.2, 0.3])
    out = slam_range_share(NS(occupied_only=occupied_only), [9], box, inv, rows, fr, tk)
    assert seen["iids"] == [9]
    assert seen["tk"].tolist() == [0.1, 0.3]
    assert seen["x"].tolist() == [[1.5, 3.5], [21.5, 23.5]]
    assert seen["y"].tolist() == [[1.5, 1.5], [1.5, 1.5]]
    assert out.tolist() == [0.5, 0.5]                 # the second row's frame 3 is invulnerable


def _forced_tick(params, arena, *, units=True, gliding=False, blocks=None, x=30.0, y=9.0):  # noqa: F811
    """A planner tick with every row in contact (forced), the hero in the air, a v2 forecast whose tracker holds the Clapper's CC_SLAM unit when units."""
    pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                      ForumConfig(deadline_ms=math.inf, esc_deadline_ms=math.inf, v2=True, forced_rank="seen_cf"), crest="Wanderer")
    pl.debug = True
    start = kin.initial_state(params, x, FLOOR + params.foot)
    start[kin.PY] = y
    start[kin.GROUND] = 0.0
    if gliding:
        start[kin.MODE] = kin.M_GLIDE
        start[kin.PHASE] = 2.0
    ls = _support_with(blocks or [(0.0, 0.0, 60.0, 30.0)])
    ls.trk = trk((SLAM_IID, v2.CLAPPER, NS(fam="CC_SLAM") if units else None))
    ls.pend = []
    f = v2.V2Forecast(_reed_forecaster(None, x=x).forecast(0.8), ls)
    r = pl.tick(_world(x), start, kin.HoldState.idle(1), np.zeros(1, np.int64), f, _prefs(None, x), _ctx())
    return pl, r, f


def _new_glide(pl, rows):
    d = pl.last_info["dbg"]
    return (np.asarray(d["mode"])[rows, int(d["P"]) + 1:] == kin.M_GLIDE).any(axis=1)


def test_forced_with_a_visible_slam_opens_no_new_umbrella_while_a_row_without_one_is_allowed(params, arena):  # noqa: F811
    pl, r, _ = _forced_tick(params, arena)
    assert r.forced_risk
    ls = pl.last_sel
    assert _new_glide(pl, np.flatnonzero(ls["allowed"])).any()      # the rule has something to exclude
    assert not _new_glide(pl, np.flatnonzero(ls["sel"])).any()
    assert not _new_glide(pl, np.array([r.idx]))[0]
    assert pl.last_info["forced_slam"] == {"units": 1, "dropped": int(_new_glide(pl, np.flatnonzero(ls["allowed"])).sum())}


def test_without_a_visible_slam_the_forced_rows_keep_the_umbrella(params, arena):  # noqa: F811
    pl, r, _ = _forced_tick(params, arena, units=False)
    assert r.forced_risk
    ls = pl.last_sel
    assert _new_glide(pl, np.flatnonzero(ls["allowed"])).any()
    assert _new_glide(pl, np.flatnonzero(ls["sel"])).any()
    assert "forced_slam" not in pl.last_info


def test_a_float_already_open_is_not_excluded(params, arena):  # noqa: F811
    pl, r, _ = _forced_tick(params, arena, gliding=True)
    assert r.forced_risk
    # the hero is in the umbrella: nothing to exclude, a row keeps gliding
    assert _new_glide(pl, np.flatnonzero(pl.last_sel["sel"])).all()


def test_the_rule_holds_only_while_a_row_without_a_new_umbrella_is_allowed(params, arena, monkeypatch):  # noqa: F811
    """Every allowed row opening an umbrella: nothing to prefer, the rows stay (forced-risk semantics unchanged)."""
    real = kin.rollout

    def all_glide(start, latched, *a, **k):
        r = real(start, latched, *a, **k)
        m = np.array(r.mode, copy=True)
        m[:, 2:] = kin.M_GLIDE
        r.mode = m
        return r

    monkeypatch.setattr(fp.kin, "rollout", all_glide)
    pl, r, _ = _forced_tick(params, arena)
    assert r.forced_risk
    assert len(np.flatnonzero(pl.last_sel["sel"])) > 0


def test_forced_key_reads_the_hammer_units_support_share(params, arena):  # noqa: F811
    """The committed key of a forced tick with a visible slam is the share in the slam unit's support (another owner's support does not count)."""
    pl, r, f = _forced_tick(params, arena, blocks=[(0.0, 0.0, 60.0, 30.0)])
    assert r.forced_risk
    ls = pl.last_sel
    pre = np.flatnonzero(ls["sel"])
    d = pl.last_info["dbg"]
    # the only owner is the slam unit: rows in contact on every sampled frame (invulnerable frames aside) have a positive share
    assert ls["sk_c"][pre].max() > 0.0
    # the same forecast without the slam unit: the key falls back to the old fine share (zero here: no committed fine placements)
    pl2, r2, _ = _forced_tick(params, arena, units=False)
    assert r2.forced_risk and not pl2.last_sel["sk_c"].any()
