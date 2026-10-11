"""Forum planner v2-lite (combat.forum_v2, SSBOT_FORUM_V2; forum.md §43): the margin rule, the raster dilation into
Bounds-centre space, the sampled support and its bracket, the pending aims' zone test, the wrapper the planner reads,
and ForumPlanner's v2 path (escape from the row's end, the hit keys, off = the earlier planner)."""
import math

import numpy as np
import pytest

from ssbot.combat import candidates as cmod
from ssbot.combat import forum_v2 as v2
from ssbot.combat.attack_range import Mask
from ssbot.combat.forum_planner import ForumConfig, ForumPlanner
from ssbot.combat.planner import PlannerConfig
from ssbot.knowledge import kinematics as kin
from tests.test_forum_planner import FLOOR, _ctx, _prefs, _reed_forecaster, _world, arena, params  # noqa: F401


# ---- the margin ----

def test_margin_rule_flat_to_k12_then_the_fliers_curve_and_the_walkers_table():
    for k in (0, 1, 6, 12):
        assert v2.margin("Song Reed", k, "rule") == 0.5
        assert v2.margin("Song Heavy Sentry", k, "rule") == 0.5
    t = 36 / 60.0
    assert v2.margin("Song Reed", 36, "rule") == pytest.approx(0.3 + 11 * t * t)
    assert v2.margin("Song Reed", 60, "rule") == v2.margin("Song Reed", 36, "rule")      # held past K_HOLD
    assert v2.margin("Song Pilgrim 01", 36, "rule") == 0.5                                 # Envoy walker
    assert v2.margin("Song Pilgrim 03", 36, "rule") == pytest.approx(1.05)                 # Choristor walker
    assert v2.margin("Song Heavy Sentry", 12, "table") == pytest.approx(3.2)
    assert v2.margin("Song Reed", 20, "flat:0.25") == 0.25
    assert v2.margin("Song Reed", 20, "zero") == 0.0


# ---- rasters ----

def _cell_mask(x: float, y: float, cell: float = 0.05) -> Mask:
    m = np.ones((1, 1), bool)
    return Mask(m, int(math.floor(x / cell)), int(math.floor(y / cell)))


@pytest.mark.parametrize("m", [0.0, 0.5, 1.3])
def test_dilation_holds_every_point_whose_herobox_meets_the_cell_and_is_tight_to_a_cell(m):
    rng = np.random.default_rng(1)
    raw = _cell_mask(30.02, 6.01)
    q0x, q0y = raw.ix0 * 0.05, raw.iy0 * 0.05
    d, ix0, iy0 = v2.dilate(raw, 0.05, m)
    cv = v2.Canvas()
    st = cv.zeros()
    cv.paste(st, d, ix0, iy0)
    px = rng.uniform(26.0, 34.0, 20000)
    py = rng.uniform(2.0, 10.0, 20000)
    row, col, ok = cv.index(px, py)
    got = ok & st[row, col]
    # exact: the HeroBox at the point (Bounds centre + HB_DY) grown by m meets the raw 0.05 cell
    meet = (px + v2.HB_HX + m >= q0x) & (px - v2.HB_HX - m <= q0x + 0.05) & \
        (py + v2.HB_DY + v2.HB_HY + m >= q0y) & (py + v2.HB_DY - v2.HB_HY - m <= q0y + 0.05)
    assert not (meet & ~got).any()                       # conservative
    far = (px + v2.HB_HX + m < q0x - 0.21) | (px - v2.HB_HX - m > q0x + 0.26) | \
        (py + v2.HB_DY + v2.HB_HY + m < q0y - 0.21) | (py + v2.HB_DY - v2.HB_HY - m > q0y + 0.26)
    assert not (got & far).any()                         # within two coarse cells of the exact region


def test_layer_support_reads_the_union_of_the_bracketing_samples_and_nothing_outside():
    cv = v2.Canvas()
    ls = v2.LayerSupport(cv, (0, 4, 8))
    a, ia, ja = v2.dilate(_cell_mask(25.0, 5.0), 0.05, 0.0)
    b, ib, jb = v2.dilate(_cell_mask(35.0, 5.0), 0.05, 0.0)
    ls.add(0, 1, a, ia, ja)
    ls.add(1, 1, b, ib, jb)
    x = np.array([[25.0, 25.0, 25.0, 35.0, 35.0, np.nan, 5.0]])
    y = np.array([[5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0]])
    tk = np.array([0, 2, 5, 2, 8, 2, 2]) / 60.0
    o = ls.occupied(x, y, tk)
    # frame 0: sample 0 only; frame 2: samples 0 | 4; frame 5: 4 | 8 (sample 0 gone); frame 8: sample 8 (empty)
    assert o.tolist() == [[True, True, False, True, False, False, False]]
    assert ls.occupied_without(x, y, tk, 1).sum() == 0
    assert ls.occupied_only(x, y, tk, [1]).tolist() == o.tolist()


def test_k_shift_reads_the_tracker_look_ahead_of_a_planner_frame():
    cv = v2.Canvas()
    ls = v2.LayerSupport(cv, (0, 2), k_shift=2)
    a, ia, ja = v2.dilate(_cell_mask(25.0, 5.0), 0.05, 0.0)
    ls.add(0, 1, a, ia, ja)
    # planner frame 2 = tracker look-ahead 0; frame 4 = look-ahead 2 (empty)
    assert ls.occupied(np.array([[25.0, 25.0]]), np.array([[5.0, 5.0]]), np.array([2, 4]) / 60.0).tolist() == \
        [[True, False]]


# ---- pending aims ----

class _Reader:
    """A fake aim_zones.AimZones: the zone is a block in front of the enemy (fan x 1..3 u, y -2..2 u)."""
    gx = np.round(np.arange(-5.0, 10.0, 0.1), 2)
    gy = np.round(np.arange(-5.0, 5.0, 0.1), 2)

    def zone(self, x, y, side, lat):
        z = np.zeros((len(self.gy), len(self.gx)), np.int8)
        z[np.ix_((self.gy >= -2) & (self.gy <= 2), (self.gx >= 1) & (self.gx <= 3))] = 1
        return z


def _pend(aim="hero", d_lo=5, d_hi=6, s=1):
    return {"iid": 1, "name": "X", "reader": _Reader(), "x": 30.0, "y": 5.0, "s": s, "aim": aim, "d_lo": d_lo,
            "d_hi": d_hi, "D": 0.1, "zones": {}}


def test_aim_fail_tests_the_decision_window_on_the_hero_side_and_through_a_lock():
    ls = v2.LayerSupport(v2.Canvas(), (0,))
    T1 = 12
    cx = np.full((4, T1), 25.0)
    cy = np.full((4, T1), 5.0 - v2.HB_DY)
    cx[0, 5] = 32.0                    # in front (right) at the decision: fails
    cx[1, 5] = 28.0                    # left side, 2 u: the mirror zone (hero aim): fails
    cx[2, 9] = 32.0                    # after the window: passes ...
    cx[3, 9] = 32.0                    # ... unless a lock holds from the window's end on
    locked = np.zeros((4, T1), bool)
    locked[3, 6:10] = True
    ls.pend = [_pend()]
    assert ls.aim_fail(cx, cy, locked).tolist() == [True, True, False, True]
    ls.pend = [_pend(aim="facing", s=1)]
    assert ls.aim_fail(cx, cy, locked).tolist() == [True, False, False, True]   # facing: the right side only
    ls.pend = [_pend(d_lo=30, d_hi=31)]                                        # after the row: its end frame
    cx2 = np.full((2, T1), 25.0)
    cx2[0, -1] = 32.0
    assert ls.aim_fail(cx2, np.full((2, T1), 5.0 - v2.HB_DY)).tolist() == [True, False]


# ---- the wrapper ----

def test_v2_forecast_answers_the_safe_test_and_delegates_the_rest(params):
    inner = _reed_forecaster(None).forecast(0.8)
    ls = v2.LayerSupport(v2.Canvas(), (0, 4))
    a, ia, ja = v2.dilate(_cell_mask(25.0, 5.0), 0.05, 0.0)
    ls.add(0, 1, a, ia, ja)
    f = v2.V2Forecast(inner, ls)
    assert f.v2 and f.origin_t == inner.origin_t and f.horizon == inner.horizon
    assert f.fc.half == v2.BOUNDS_HALF and f.fc.model is inner.fc.model
    x, y, tk = np.array([[25.0, 40.0]]), np.array([[5.0, 5.0]]), np.zeros(2)
    assert f.occupied(x, y, tk).tolist() == [[True, False]]
    o, com, fine = f.occupied_split(x, y, tk)
    assert o.tolist() == com.tolist() and not fine.any()


# ---- the planner ----

def _planner(params, arena, v2_on: bool, **kw):
    return ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                        ForumConfig(deadline_ms=math.inf, esc_deadline_ms=math.inf, v2=v2_on, **kw))


def _support_with(blocks, samples=v2.SAMPLE_KS):
    """A LayerSupport whose every sample holds the given world boxes (x0, y0, x1, y1) of raw damage."""
    ls = v2.LayerSupport(v2.Canvas(), samples)
    for i, (x0, y0, x1, y1) in enumerate(blocks):
        raw = Mask(np.ones((int(round((y1 - y0) / 0.05)), int(round((x1 - x0) / 0.05))), bool),
                   int(round(x0 / 0.05)), int(round(y0 / 0.05)))
        d, ix0, iy0 = v2.dilate(raw, 0.05, 0.0)
        for si in range(len(samples)):
            ls.add(si, 100 + i, d, ix0, iy0)
    return ls


def test_v2_off_by_default_and_the_candidate_sets_unchanged(params, arena):
    assert ForumConfig().v2 is False
    pl = _planner(params, arena, False)
    for p in cmod.POSTURES:
        a, _ = pl.fsets[p]
        b, _ = cmod.build_forum(36, p)
        assert np.array_equal(a.cmd, b.cmd)
    pl2 = _planner(params, arena, True)
    assert len(pl2.fsets["ground"][0].cmd) > len(pl.fsets["ground"][0].cmd)     # the timing rows (extension)


def test_v2_chosen_row_stays_out_of_the_support_and_keeps_an_escape(params, arena):
    x = 30.0
    mf = _reed_forecaster(None, x=40.0)
    inner = mf.forecast(0.8)
    # a wall of damage just right of the hero from the floor up: every safe row stays left of it
    ls = _support_with([(31.2, FLOOR, 33.0, FLOOR + 6.0)])
    f = v2.V2Forecast(inner, ls)
    pl = _planner(params, arena, True)
    start = kin.initial_state(params, x, FLOOR + params.foot)
    r = pl.tick(_world(x), start, kin.HoldState.idle(1), np.zeros(1, np.int64), f, _prefs(None, x), _ctx())
    assert r.S == 0 and not r.forced_risk
    tk = np.arange(r.path.shape[0]) * params.frame_time
    cx = 0.5 * (r.path[:, 0] + r.path[:, 2])
    cy = 0.5 * (r.path[:, 1] + r.path[:, 3])
    assert not ls.occupied(cx[None], cy[None], tk)[0, 1:].any()
    assert pl.audit.v2_esc_rows > 0


def test_v2_escape_fails_when_the_end_is_closed_and_passes_when_open(params, arena):
    x = 30.0
    inner = _reed_forecaster(None, x=40.0).forecast(0.8)
    pl = _planner(params, arena, True)
    start = kin.initial_state(params, x, FLOOR + params.foot)
    open_ = v2.V2Forecast(inner, _support_with([]))
    r = pl.tick(_world(x), start, kin.HoldState.idle(1), np.zeros(1, np.int64), open_, _prefs(None, x), _ctx())
    info = pl.last_info["esc"]
    assert r.S == 0 and info["fail"] == 0
    # everything is danger from look-ahead 44 on (past every row's end and its bracket): no escape from any end
    samples = v2.SAMPLE_KS
    ls = v2.LayerSupport(v2.Canvas(), samples)
    full = np.ones((ls.cv.ny, ls.cv.nx), bool)
    for si, k in enumerate(samples):
        if k >= 44:
            ls.add(si, 9, full, ls.cv.jx0, ls.cv.iy0)
    pl2 = _planner(params, arena, True)
    r2 = pl2.tick(_world(x), start, kin.HoldState.idle(1), np.zeros(1, np.int64), v2.V2Forecast(inner, ls),
                  _prefs(None, x), _ctx())
    assert not r2.forced_risk and r2.S == 1
    assert pl2.last_info["esc"]["fail"] > 0 and pl2.last_info["esc"]["unsafe"]


def test_v2_ranks_safe_rows_by_landed_hits_first(params, arena):
    x = 30.0
    mf = _reed_forecaster(None, x=31.2)             # an idle Reed in reach (its support is not read under v2)
    f = v2.V2Forecast(mf.forecast(0.8), _support_with([]))
    pl = _planner(params, arena, True)
    start = kin.initial_state(params, x, FLOOR + params.foot)
    pl.tick(_world(x), start, kin.HoldState.idle(1), np.zeros(1, np.int64), f, _prefs(None, 27.0), _ctx())
    sel = pl.last_sel
    safe = sel["safe"]
    assert safe.any() and sel["nh"][safe].max() > 0
    assert sel["nh"][sel["chosen"]] == sel["nh"][safe].max()


def test_v2_full_support_is_forced_risk_without_errors(params, arena):
    x = 30.0
    inner = _reed_forecaster(None, x=40.0).forecast(0.8)
    ls = v2.LayerSupport(v2.Canvas(), v2.SAMPLE_KS)
    full = np.ones((ls.cv.ny, ls.cv.nx), bool)
    for si in range(len(v2.SAMPLE_KS)):
        ls.add(si, 9, full, ls.cv.jx0, ls.cv.iy0)
    pl = _planner(params, arena, True)
    r = pl.tick(_world(x), kin.initial_state(params, x, FLOOR + params.foot), kin.HoldState.idle(1),
                np.zeros(1, np.int64), v2.V2Forecast(inner, ls), _prefs(None, x), _ctx())
    assert r.forced_risk and r.S == 1


def test_escape_reads_its_own_danger_when_given():
    cv = v2.Canvas()
    ls = v2.LayerSupport(cv, (0, 4))
    a, ia, ja = v2.dilate(_cell_mask(25.0, 5.0), 0.05, 0.0)
    ls.add(0, 1, a, ia, ja)
    x, y, tk = np.array([[25.0]]), np.array([[5.0]]), np.zeros(1)
    assert ls.occupied_esc(x, y, tk).all()          # none given: the full support
    b, ib, jb = v2.dilate(_cell_mask(35.0, 5.0), 0.05, 0.0)
    ls.add_esc(0, b, ib, jb)
    assert not ls.occupied_esc(x, y, tk).any() and ls.occupied_esc(np.array([[35.0]]), y, tk).all()
    assert ls.occupied(x, y, tk).all()               # the safe test still reads the full support


def test_grouped_dilation_equals_the_union_of_each_enemys():
    cv = v2.Canvas()
    raws = [(_cell_mask(25.0, 5.0), 0.5), (_cell_mask(26.0, 7.0), 0.5), (_cell_mask(40.0, 5.0), 1.3)]
    a = v2.LayerSupport(cv, (0,))
    b = v2.LayerSupport(cv, (0,))
    for i, (r, m) in enumerate(raws):
        d, ix0, iy0 = v2.dilate(r, 0.05, m)
        a.add(0, i, d, ix0, iy0)
        c, jx0, jy0 = v2.coarse(r, 0.05)
        b.add_raw(0, i, c, jx0, jy0, m, 0.5)
    b.finish()
    assert np.array_equal(a.stack, b.stack) and a.stack.any()
    assert np.array_equal(a._stack_of(lambda i: i != 2), b._stack_of(lambda i: i != 2))
    assert b.stack_esc is not None and b.stack_esc.sum() < b.stack.sum()      # the 1.3 u enemy at 0.5 u


def test_v2_feed_reuses_the_support_between_rebuilds_shifted_to_the_origin():
    inner = _reed_forecaster(None, x=40.0).forecast(0.8)
    fd = v2.V2Feed(every=2)
    fd.feed({}, 10)
    a = fd.support(inner, 10)
    fd.feed({}, 11)
    b = fd.support(inner, 11)
    fd.feed({}, 12)
    c = fd.support(inner, 12)
    assert b.rs is not a.rs and b.rs.stack is a.rs.stack and b.rs.k_shift == -1 and fd.reused == 1
    assert c.rs.stack is not a.rs.stack and c.rs.k_shift == 0
    ls = v2.LayerSupport(v2.Canvas(), (0, 2), k_shift=-1)
    d, ix0, iy0 = v2.dilate(_cell_mask(25.0, 5.0), 0.05, 0.0)
    ls.add(1, 1, d, ix0, iy0)
    # planner frame 1 one frame after the build = the build's look-ahead 2
    assert ls.occupied(np.array([[25.0, 25.0]]), np.array([[5.0, 5.0]]), np.array([0, 1]) / 60.0).tolist() ==         [[True, True]]


def test_corner_zones_between_a_clapper_and_a_near_wall():
    from types import SimpleNamespace as NS
    from ssbot.combat import forum_v2 as v
    tab = NS(type_key=v.CLAPPER)
    fc = NS(trackers={1: NS(dead=False, pos=(20.0, 7.45), table=tab),            # 6 u from the left wall
                      2: NS(dead=False, pos=(31.0, 7.45), table=tab),            # mid-arena: no corner
                      3: NS(dead=True, pos=(46.0, 7.45), table=tab),             # dead: none
                      4: NS(dead=False, pos=(46.0, 7.45), table=NS(type_key="Song Reed"))})
    z = v.corner_zones(fc)
    assert z == [(v.WALL_L - 1.0, 20.0)]


# ---- the focus margin (the person, 2026-10-11) ----

def _fake_tracker(units):
    """units: {iid: (type_key, (x, y))}: every estimate a 1-cell raw mask at the unit's position, mid-move."""
    from types import SimpleNamespace as NS
    now = {iid: (tk, {"pos": p}, None) for iid, (tk, p) in units.items()}
    tables = {tk: NS(cell=0.05) for tk, _ in units.values()}
    return NS(now=now, tables=tables, hero=None, T=0.0,
              estimate=lambda iid, k: NS(raw=_cell_mask(*units[iid][1]), fam="X", haz=None))


def test_focus_mode_gives_the_others_the_rule_margin_and_is_the_v2_default():
    assert v2.MARGIN_MODE == "focus" or "SSBOT_FORUM_V2_MARGIN" in __import__("os").environ
    for k in (0, 12, 18, 36):
        for tk in ("Song Reed", "Song Heavy Sentry", "Song Pilgrim 03"):
            assert v2.margin(tk, k, "focus") == v2.margin(tk, k, "rule")


def test_focus_iid_is_the_target_else_the_only_enemy_else_none():
    one = _fake_tracker({7: ("Song Heavy Sentry", (30.0, 8.0))})
    two = _fake_tracker({7: ("Song Heavy Sentry", (30.0, 8.0)), 9: ("Song Reed", (40.0, 10.0))})
    assert v2.focus_iid(one, None) == 7 and v2.focus_iid(one, 3) == 7
    assert v2.focus_iid(two, 9) == 9 and v2.focus_iid(two, None) is None and v2.focus_iid(two, 3) is None


def test_focus_build_flat_for_the_focus_rule_for_the_others_and_the_dash_copy():
    units = {7: ("Song Heavy Sentry", (30.0, 8.0)), 9: ("Song Reed", (40.0, 10.0))}
    trk = _fake_tracker(units)
    rs = v2.RangeSupport.build(trk, margin_mode="focus", focus=7)
    flat = v2.RangeSupport.build(_fake_tracker({7: units[7]}), margin_mode="flat:0.5")
    rule = v2.RangeSupport.build(_fake_tracker({9: units[9]}), margin_mode="rule")
    rule7 = v2.RangeSupport.build(_fake_tracker({7: units[7]}), margin_mode="rule")
    assert rs.focus == 7
    assert np.array_equal(rs._stack_of(lambda i: i == 7), flat.stack)
    assert np.array_equal(rs._stack_of(lambda i: i == 9), rule.stack)
    si36 = v2.SAMPLE_KS.index(36)
    si12 = v2.SAMPLE_KS.index(12)
    assert rs.stack_dash is not None and not rs.stack_dash[si12].any()       # rule = 0.5 up to k 12: no copy
    assert np.array_equal(rs.stack_dash[si36], rule7.stack[si36]) and rs.stack_dash[si36].sum() > flat.stack[si36].sum()
    # a 1v1: the focus is the only enemy and the main stack is exactly flat 0.5 (the tj2 arm)
    solo = v2.RangeSupport.build(_fake_tracker({7: units[7]}), margin_mode="focus")
    assert solo.focus == 7 and np.array_equal(solo.stack, flat.stack)
    assert np.array_equal(solo.stack_esc, flat.stack_esc)


def test_dash_at_rows_moving_towards_the_focus_in_a_dash():
    T = 5
    mode = np.zeros((3, T), np.int64)
    vel = np.zeros((3, T, 2))
    cen = np.zeros((3, T, 2))
    cen[..., 0] = 30.0
    mode[0, 2] = kin.M_DASH
    vel[0, 2, 0] = 20.0          # dashing right, focus right: yes
    mode[1, 2] = kin.M_DASH
    vel[1, 2, 0] = -20.0         # dashing away: no
    vel[2, :, 0] = 8.0           # running at it, no dash: no
    assert v2.dash_at(mode, vel, cen, 35.0).tolist() == [True, False, False]
