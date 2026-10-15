"""SG4 review (task 1v1, forum.md 60): regressions for the slam map in the planner (SSBOT_FORUM_SPECIAL_MAP).

1. The map row's physics phase is read at rollout index 0 (kin.rollout advances ALPHA, not ALO / AHI): from a state
   after a non-empty prefix the planner lane of the map row is the map's own path.
2. The CONTINUE of last tick's map row keeps the full checks (after a map exit it was still judged with the Clapper's
   move dropped, on the old anchor).
3. The planner lane of a map row bounces at every map contact; a lane off the map's path keeps the full checks.
4. The full support is read again once every observed slam variant has ended (the Clapper's next move).
"""
import math
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import forum_map
from ssbot.combat import forum_planner as fp
from ssbot.combat import forum_v2 as v2
from ssbot.combat import special_map_rt as smrt
from ssbot.combat.hero_macros import ALPHAS, key_mask
from ssbot.combat.holdfilter import hold_filter_jit
from ssbot.combat.planner import PlannerConfig
from ssbot.knowledge import kinematics as kin
from tests.test_forum_planner import FLOOR, _ctx, _prefs, _reed_forecaster, _world, arena  # noqa: F401
from tests.test_special_map_sg4 import _helper, _mock, setup  # noqa: F401
from tests.test_special_mode import _raw

CL = "Song Heavy Sentry"


def _lane(start, prefix, row, params, terrain):
    """The planner's lane of a map row: prefix + the row's template, hold-filtered, with the map's bounces."""
    full = np.concatenate([np.asarray(prefix, np.int64), np.asarray(row.ext, np.int64)])
    lat, _ = hold_filter_jit(full[None], kin.HoldState.idle())
    ev = np.zeros((1, len(full)), np.int64)
    for e in row.meta["map_ev"]:
        if e < len(full):
            ev[0, e] = kin.EV_POGO
    return kin.rollout(start, lat, params, terrain, events=ev)


def test_phase_after_a_prefix(setup, monkeypatch):
    """1: phases from the start's ALPHA interval at k0; the lane follows the map's path frame by frame."""
    monkeypatch.setattr(forum_map, "FORUM_ARENA", (0.0, 80.0))
    h, R = _helper(setup)
    params, terrain = setup["params"], setup["terrain"]
    cx = 40.0
    checked = 0
    for q in range(6):
        for P, key in ((1, 0), (2, 1), (4, -1)):
            f, e = _mock(cx, "Slam Antic", 0.1, t0=100.0 + 10 * q + P)
            k0 = 6                                            # Slam Antic at 0.1 s
            want = smrt.phases_of(ALPHAS[q], ALPHAS[q], k0)
            if want[0] not in R.srcs:
                continue
            start = kin.initial_state(params, cx + 4.0, setup["hm"].stand_py, facing=-1, ground=True,
                                      alpha=ALPHAS[q])
            prefix = np.full(P, key_mask(key), np.int64)
            row = h.row(f, start, kin.HoldState.idle(), prefix, 36, q)
            assert row is not None, h.info
            assert h.info["phases"] == want, (q, P, h.info["phases"], want)
            r = _lane(start, prefix, row, params, terrain)
            m = min(len(row.meta["map_x"]), r.box.shape[1] - P - 1)
            b = r.box[0, P + 1:P + 1 + m]
            dx = np.abs(0.5 * (b[:, 0] + b[:, 2]) - row.meta["map_x"][:m])
            dy = np.abs(b[:, 1] - row.meta["map_y"][:m])
            assert dy.max() < 1e-6 and dx.max() <= 0.17, (q, P, dx.max(), dy.max())
            assert (dx < 1e-6).mean() > 0.9
            checked += 1
    assert checked >= 4


# ---- planner level (the real map file) ----
needs_map = pytest.mark.skipif(not smrt.map_path().exists(), reason="no SG4 map file")
CY = FLOOR + 4.434


def _support(parts, trk, samples=v2.SAMPLE_KS):
    rs = v2.RangeSupport(v2.Canvas(), samples, 0, None)
    rs.trk, rs.margin_mode, rs.focus, rs.dash_focus = trk, "flat:0.5", 7, None
    for iid, boxes in parts.items():
        for b in boxes:
            c, ix0, iy0 = v2.coarse(_raw(*b), 0.05, rs.cv.cell)
            for si, k in enumerate(samples):
                rs.add_raw(si, iid, c, ix0, iy0, 0.5, 0.5 if k >= v2.ESC_FROM_K else None)
    rs.finish()
    return rs


def _f(cx, k, state="Slam Antic", t_in=None, T=0.0, x0=None, parts=None):
    """A forecast with one Clapper (iid 7) in its slam at move frame k (game time T, the instance's start T - k / 60),
    facing +x; parts: the support's raw boxes per enemy."""
    e = {"pos": (cx, CY), "flipX": True, "type_key": CL,
         "fsms": [{"name": "Control", "state": state, "t": (k / 60.0) if t_in is None else t_in}]}
    inst = NS(fam="CC_SLAM", t0=T - k / 60.0, x0=cx if x0 is None else x0)
    trk = NS(now={7: (CL, e, inst)}, tables={}, hero=None, T=T)
    rs = _support(parts if parts is not None else {7: [(cx + 2.3, FLOOR, cx + 10.0, FLOOR + 7.0)]}, trk)
    rs.k_shift = 0
    return v2.V2Forecast(_reed_forecaster(None, x=46.0).forecast(0.8), rs)


@pytest.fixture
def map_on(monkeypatch):
    from ssbot.combat import special_mode
    monkeypatch.setattr(fp, "SPECIAL_MAP", True)
    forum_map.BOARD.clear()
    yield
    forum_map.BOARD.clear()
    special_mode.BOARD.clear()               # the planner's special context writes it (map rows too)


def _planner(params, arena_):
    pl = fp.ForumPlanner(params, arena_, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                         fp.ForumConfig(deadline_ms=math.inf, esc_deadline_ms=math.inf, v2=True))
    pl.debug = True
    return pl


@pytest.fixture(scope="module")
def wparams():
    from ssbot.train.forum_planner_policy import CREST_PARAMS
    return kin.HeroParams.load(CREST_PARAMS["Wanderer"])


def _tick(pl, f, hx, prefix=None):
    start = kin.initial_state(pl.params, hx, FLOOR + pl.params.foot, alpha=ALPHAS[1])   # not on a cycle edge
    pre = np.zeros(1, np.int64) if prefix is None else prefix
    return pl.tick(_world(hx), start, kin.HoldState.idle(1), pre, f, _prefs(None, hx), _ctx())


@needs_map
def test_continue_of_a_map_row_keeps_the_full_checks(wparams, arena, map_on):
    """2: tick 1 takes the map row; tick 2 the lunge is off its anchor (the deviation exit): no special context for
    the CONTINUE (before: the old map row's CONTINUE was judged with the Clapper's move dropped)."""
    pl = _planner(wparams, arena)
    assert pl._map is not None and pl._map._rt is not None          # preloaded at construction (review)
    cx, hx = 30.0, 35.0
    r1 = _tick(pl, _f(cx, 20), hx)
    mi = pl.last_info["map"]
    assert mi["on"] and mi["safe"] and r1.name == "SPECIAL MAP", (mi, r1.name)
    # one frame on: the Clapper lunged 0.6 u short of its anchor + displacement range
    f2 = _f(cx - 0.6, 21, state="Slam 0", t_in=0.0, T=1 / 60.0, x0=cx)
    _tick(pl, f2, hx)
    assert pl.last_info["map"]["why"] == "deviation"
    assert pl._sctx is None
    # the move dropped nowhere: no safe row ends inside the Clapper's move estimate
    safe = pl.last_sel["safe"]
    box = pl.last_sel["box"]
    cxe = 0.5 * (box[safe, -1, 0] + box[safe, -1, 2])
    assert not ((cxe > cx + 2.6) & (cxe < cx + 9.7)).any()


@needs_map
def test_map_lane_bounces_and_the_lane_guard(wparams, arena, map_on, monkeypatch):
    """3: the map row's planner lane bounces at every map contact and stays on the map's path; a map path the lane
    does not follow keeps the full checks."""
    pl = _planner(wparams, arena)
    cx = 30.0
    found = None
    for k in range(4, 40, 3):
        for hx in (33.5, 34.5, 35.5, 36.5):
            pl = _planner(wparams, arena)
            _tick(pl, _f(cx, k), hx)
            mi = pl.last_info.get("map") or {}
            if mi.get("on") and pl._sctx is not None and len(pl._map.slam[7]["plan"].contacts) >= 2:
                c2 = pl._map.slam[7]["plan"].contacts[1]
                if 1 + c2 + 6 < 36:
                    found = (k, hx)
                    break
        if found:
            break
    assert found is not None
    sc = pl._sctx
    meta = pl._spec_meta
    ev = sc.ev[0]
    for e in meta["map_ev"]:
        if e < len(ev):
            assert ev[e] & kin.EV_POGO
    lane = pl.last_info["map"]["lane"]
    assert lane[0] <= fp.MAP_LANE_TOL_X and lane[1] <= fp.MAP_LANE_TOL_Y
    # the row's planner lane (r1) rises after the second contact as the map's does
    box = pl.last_sel["box"]
    M0 = pl.last_info["map"]["row"]
    P = 1
    c2 = pl._map.slam[7]["plan"].contacts[1]
    y = box[M0, :, 1]
    assert y[P + 1 + c2 + 6] > y[P + 1 + c2] + 0.3
    # the guard: a map path 0.5 u off the lane -> no special context (the row keeps the full checks)
    k, hx = found
    pl2 = _planner(wparams, arena)
    orig = forum_map.MapHelper.row

    def row_off(self, *a, **kw):
        r = orig(self, *a, **kw)
        if r is not None:
            r.meta["map_x"] = np.asarray(r.meta["map_x"]) + 0.5
        return r
    monkeypatch.setattr(forum_map.MapHelper, "row", row_off)
    _tick(pl2, _f(cx, k), hx)
    assert pl2._sctx is None and pl2.audit.map_lane_off == 1
    assert not pl2.last_info["map"]["safe"]


@needs_map
def test_full_support_after_every_variant_ended(wparams, arena, map_on):
    """4: late in the slam the map row's frames past every variant's end read the full support (its next move)."""
    cx = 30.0
    seen = 0
    for k, hx in ((60, 35.0), (55, 26.0), (50, 35.0), (45, 26.0), (30, 34.0)):
        pl = _planner(wparams, arena)
        _tick(pl, _f(cx, k), hx)
        sc = pl._sctx
        if sc is None:
            continue
        rt = pl._map._rt
        assert int(sc.full_from[0]) == rt.end_max + 1 - sc.k0
        seen += 1
    assert seen >= 2


@needs_map
def test_no_index_error_without_a_continue(wparams, arena, map_on):
    """The first tick (no CONTINUE) with a map row passing stage 1: the sibling table counts the map row (it raised
    IndexError before the review)."""
    pl = _planner(wparams, arena)
    _tick(pl, _f(30.0, 10), 26.0)
    mi = pl.last_info["map"]
    assert mi["on"] and not mi["s1"]


@needs_map
def test_runtime_waits_for_the_arena_terrain(wparams, arena, map_on):
    """The policy constructs the planner on Terrain2D.empty() and sets the arena's at the episode start: the map's
    hero macros must be rolled on the arena (on the empty terrain they fell through the floor: plans without presses)."""
    from ssbot.combat.hero_macros import HeroMacros
    pl = fp.ForumPlanner(wparams, kin.Terrain2D.empty(), PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                         fp.ForumConfig(deadline_ms=math.inf, esc_deadline_ms=math.inf, v2=True))
    assert pl._map is not None and pl._map._rt is None and not pl._map._loaded
    pl.terrain = arena
    _tick(pl, _f(30.0, 20), 35.0)
    rt = pl._map._rt
    assert rt is not None and rt.hm.terrain is arena
    assert abs(rt.hm.stand_y0 - HeroMacros(wparams, arena).stand_y0) < 1e-9
    p = pl._map.slam[7]["plan"]
    assert p.presses                                              # the strike the map plans from there


def test_readiness_on_a_subset_of_rows(setup):
    """The penalty computed on the safe rows only equals the full computation on those rows."""
    h, R = _helper(setup)
    params = setup["params"]
    cx = 40.0
    f, _ = _mock(cx, "Walk", 0.3)
    start = kin.initial_state(params, cx + 4.0, setup["hm"].stand_py, facing=-1, ground=True, alpha=ALPHAS[0])
    T = 36
    xs = np.array([cx + 4.5, cx + 5.4, cx + 8.0, cx + 3.6, cx + 6.2])
    box = np.zeros((len(xs), T + 1, 4))
    y0 = setup["hm"].stand_y0
    for i, x in enumerate(xs):
        box[i, :, 0], box[i, :, 2] = x - 0.25, x + 0.25
        box[i, :, 1], box[i, :, 3] = y0, y0 + 1.3
    r1 = NS(box=box, flags=np.full((len(xs), T + 1), kin.F_GROUND, np.int64),
            mode=np.zeros((len(xs), T + 1), np.int64))
    cmd = np.zeros((len(xs), T), np.int64)
    pen, Rr = h.readiness(f, start, r1, cmd, 0, 0)
    sub = np.array([0, 2, 4])
    pen2, R2 = h.readiness(f, start, r1, cmd, 0, 1, rows=sub)
    assert np.allclose(pen2[sub], pen[sub]) and np.allclose(R2[sub], Rr[sub])
    assert (pen2[[1, 3]] == 0).all() and np.isnan(R2[[1, 3]]).all()
