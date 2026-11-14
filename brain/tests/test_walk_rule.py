"""combat.walk_rule (the person 2026-11-13, design doc quote 130): the other Clapper's Idle / Walk body on a whole route
closes on her only while she is farther than 5.5 u, read up to LAG_F frames late; B2Geometry's whole-route queries
use it for that Clapper's body contacts (SSBOT_FORUM_TWO_WALK_RULE, default on)."""
from collections import deque
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import attack_range as ar
from ssbot.combat import forum_v2 as v2
from ssbot.combat import walk_rule as wr
from ssbot.combat.knife_chain_geometry import B2Geometry

CL = v2.CLAPPER
STEP = wr.V_WALK * wr.FT


def route(xs, ys=4.6, origin=100, stage="approach"):
    """A route of hers: Bounds boxes 0.5 x 2.08 u around (x, y) per frame, pos = (x, y)."""
    xs = np.asarray(xs, float)
    ys = np.broadcast_to(np.asarray(ys, float), xs.shape)
    box = np.stack([xs - .25, ys - 1.553, xs + .25, ys + .532], 1)
    n = len(xs) - 1
    return NS(origin=origin, through=origin + n, stage=stage, box=box, pos=np.stack([xs, ys], 1),
              commands=np.zeros(n, np.int64), flags=np.zeros(n + 1, np.int64), check_flags=np.zeros(n + 1, np.int64))


def p_box(xs, ys):
    return route(xs, ys).box


def hits_of(x0, hist, p, offset=0):
    n = len(p.box) - 1
    h, lo, hi = wr.route_hits(x0, np.asarray(hist, float), [p], [(offset, n)], n + 1)
    return h[0], lo[0], hi[0]


def reference(x0, hist, hx, cx, cy, n, off):
    """A plain restatement of the rule (not the kernel's code)."""
    lag = wr.LAG_F
    her = {}
    for f in range(-lag, off + n):
        if f <= 0:
            her[f] = hist[lag + f] if hist is not None else hx[0]
        elif f < off:
            her[f] = hx[0]
        else:
            her[f] = hx[f - off]
    lo = hi = x0
    out_h, out_lo, out_hi = [], [], []
    for i in range(off + n):
        if i > 0:
            w = [her[f] for f in range(i - 1 - lag, i)]
            if not (min(w) > hi and max(w) <= hi + wr.D_FWD - STEP):
                hi += STEP
            if not (max(w) < lo and min(w) >= lo - wr.D_FWD + STEP):
                lo -= STEP
        j = i - off
        if j < 0:
            continue
        xa, ya = cx[j], cy[j]
        xb, yb = (cx[j - 1], cy[j - 1]) if j > 0 else (xa, ya)
        reach = wr.TURN_U + wr.MARGIN_U
        hit = (min(xa, xb) - wr.HB_HX <= hi + reach and max(xa, xb) + wr.HB_HX >= lo - reach
               and min(ya, yb) + wr.HB_DY - wr.HB_HY <= wr.FLOOR_Y + wr.BODY_TOP_U + wr.MARGIN_U
               and max(ya, yb) + wr.HB_DY + wr.HB_HY >= wr.FLOOR_Y - wr.MARGIN_U)
        out_h.append(hit); out_lo.append(lo); out_hi.append(hi)
    return np.array(out_h), np.array(out_lo), np.array(out_hi)


def test_constants_are_their_sources():
    from ssbot.combat import jump_behind as jb
    from ssbot.core.forum import FLOOR_Y
    from ssbot.map2 import clapper as cm
    assert wr.D_FWD == cm.WALK_DIST - cm.WALK_RANGE and wr.V_WALK == cm.WALK_SPEED
    assert wr.TURN_U == jb.CFG["turn_u"] and wr.BODY_TOP_U == jb.BODY_TOP_U
    assert wr.MARGIN_U == v2.FOCUS_M and (wr.HB_HX, wr.HB_HY, wr.HB_DY) == (v2.HB_HX, v2.HB_HY, v2.HB_DY)
    assert wr.FLOOR_Y == FLOOR_Y and wr.FT == ar.FT and wr.CLAPPER == CL
    assert wr.HIST_N == wr.LAG_F + 1


def test_kernel_equals_the_plain_rule_on_random_routes():
    rng = np.random.default_rng(7)
    for _ in range(60):
        n = int(rng.integers(1, 70))
        off = int(rng.integers(0, 4))
        x0 = float(rng.uniform(18, 44))
        hx = x0 + rng.uniform(-12, 12) + np.cumsum(rng.normal(0, .35, n + 1))
        cy = np.clip(4.6 + np.cumsum(rng.normal(0, .3, n + 1)), 4.6, 14.0)
        hist = None if rng.random() < .2 else x0 + rng.uniform(-12, 12) + np.cumsum(rng.normal(0, .3, wr.HIST_N))
        p = route(hx, cy)
        h, lo, hi = wr.route_hits(x0, np.zeros(0) if hist is None else hist, [p], [(off, n)], n + 1)
        rh, rlo, rhi = reference(x0, hist, hx, hx, 0.5 * (p.box[:, 1] + p.box[:, 3]), n + 1, off)
        np.testing.assert_allclose(lo[0], rlo, atol=1e-9)
        np.testing.assert_allclose(hi[0], rhi, atol=1e-9)
        np.testing.assert_array_equal(h[0], rh)


def test_batch_rows_equal_single_routes_and_the_box_array():
    rng = np.random.default_rng(3)
    ps, spans = [], []
    for i in range(12):
        n = int(rng.integers(5, 50))
        ps.append(route(30 + np.cumsum(rng.normal(0, .3, n + 1)), 4.6 + rng.uniform(0, 4)))
        spans.append((int(rng.integers(0, 3)), n))
    W = max(n for _, n in spans) + 1
    hist = np.full(wr.HIST_N, 31.0)
    h, lo, hi = wr.route_hits(24.0, hist, ps, spans, W)
    box = np.zeros((len(ps), W, 4))
    for g, p in enumerate(ps):
        box[g, :len(p.box)] = p.box
    hb, lob, hib = wr.route_hits(24.0, hist, ps, spans, W, box=box)
    np.testing.assert_array_equal(h, hb)
    np.testing.assert_array_equal(np.isnan(lo), np.isnan(lob))
    for g, (p, (o, n)) in enumerate(zip(ps, spans)):
        h1, lo1, hi1 = wr.route_hits(24.0, hist, [p], [(o, n)], n + 1)
        np.testing.assert_array_equal(h[g, :n + 1], h1[0])
        assert not h[g, n + 1:].any() and np.isnan(lo[g, n + 1:]).all()
        np.testing.assert_allclose(lo[g, :n + 1], lo1[0])
        np.testing.assert_allclose(hi[g, :n + 1], hi1[0])


def test_rx411_2_14_walker_reaches_its_recorded_root_and_stops():
    """rx411 bout 2: 582496 (root 24.42) walked toward her from |dx| 8.69 (10061), was at x 26.02 at 10073 and turned
    back at 10074; she flew left at about 0.137 u a frame, 9.4-11.9 u high."""
    xs = 33.10 - 0.137 * np.arange(41)
    h, lo, hi = hits_of(24.42, np.full(wr.HIST_N, 33.10), route(xs, 10.5))
    assert hi[12] == pytest.approx(26.02, abs=0.02)            # the recorded root at 10073
    assert hi[40] == hi[23] and hi[40] - 24.42 < 2.5           # it stops closing (her |dx| < 5.5, LAG_F later)
    assert lo[40] == pytest.approx(24.42 - 40 * STEP)          # backing off is always possible
    assert not h.any()                                         # she is above its body throughout


def test_between_two_clappers_the_near_one_does_not_close():
    """Quote 130: two Clappers 2.5 u apart with her between: about 1 u each side, neither walks closer."""
    xs = np.full(61, 28.0)
    h, lo, hi = hits_of(24.5, np.full(wr.HIST_N, 28.0), route(xs, 4.6))
    assert (hi == 24.5).all() and not h.any()
    assert lo[-1] == pytest.approx(24.5 - 60 * STEP)


def test_a_far_walker_closes_to_5_5_u_of_her_and_stops():
    xs = np.full(61, 34.5)
    h, lo, hi = hits_of(24.5, np.full(wr.HIST_N, 34.5), route(xs, 4.6))
    assert 34.5 - hi[-1] == pytest.approx(wr.D_FWD - STEP, abs=STEP + 1e-9) and not h.any()
    k_stop = int(np.flatnonzero(np.diff(hi) == 0)[0])
    assert k_stop == pytest.approx((34.5 - 24.5 - wr.D_FWD) / STEP, abs=1.5)


def test_running_at_it_meets_its_body_by_the_open_loop_time():
    """The person's open-loop time with D 5.5 (11-13): T = max(0, d0 - 5.5) / (v + 8) + (min(5.5, d0) - W) / v. Read
    LAG_F late the walker may keep closing up to LAG_F frames longer, so the contact comes at most that much earlier."""
    v, d0 = 8.25, 10.0
    xs = 24.5 + d0 - v * wr.FT * np.arange(80)
    h, lo, hi = hits_of(24.5, np.full(wr.HIST_N, 24.5 + d0), route(xs, 4.6))
    first = int(np.flatnonzero(h)[0])
    reach = wr.TURN_U + wr.MARGIN_U + wr.HB_HX
    T = (max(0.0, d0 - wr.D_FWD) / (v + wr.V_WALK) + (min(wr.D_FWD, d0) - reach) / v) / wr.FT
    assert T - 1 - wr.LAG_F * wr.V_WALK / v <= first <= T + 1


def test_jumping_over_it_and_landing_past_it():
    """A crossing: both ends move while she is near; above its top + margin there is no contact."""
    n = 50
    xs = np.linspace(21.0, 29.0, n + 1)
    ys = 4.6 + 6.5 * np.sin(np.linspace(0, np.pi, n + 1))
    h, lo, hi = hits_of(24.5, np.full(wr.HIST_N, 21.0), route(xs, ys))
    cy = 0.5 * (p_box(xs, ys)[:, 1] + p_box(xs, ys)[:, 3])
    bottom = np.minimum(cy, np.r_[cy[:1], cy[:-1]]) + wr.HB_DY - wr.HB_HY
    high = bottom > wr.FLOOR_Y + wr.BODY_TOP_U + wr.MARGIN_U
    assert high.any() and not h[high].any()
    assert h[-1]                                    # landed 4.5 u past the root: its back-off can reach her
    assert hi[-1] - 24.5 == pytest.approx(n * STEP) and lo[-1] < 24.5


def test_walker_x_covers_only_the_other_clappers_idle_or_walk_body(monkeypatch):
    def trk(st=None, vx=0.0, tk=CL, inst=None, pos=(24.0, 7.45)):
        return NS(now={7: (tk, {"pos": list(pos), "vel": [vx, 0.0]}, inst)})
    assert wr.walker_x(trk(), 7, 9) == 24.0
    assert wr.walker_x(trk(vx=8.0), 7, 9) == 24.0
    assert wr.walker_x(trk(), 7, 7) is None                         # the route's target
    assert wr.walker_x(trk(inst=NS(fam="CC_SLAM")), 7, 9) is None    # a move: its own forecast
    assert wr.walker_x(trk(tk="Song Reed"), 7, 9) is None
    assert wr.walker_x(trk(vx=15.0), 7, 9) is None                  # faster than a walk
    assert wr.walker_x(trk(pos=(float("nan"), 7.45)), 7, 9) is None
    assert wr.walker_x(trk(), 8, 9) is None
    monkeypatch.setattr(wr, "ENABLED", False)
    assert wr.walker_x(trk(), 7, 9) is None


def test_the_tracker_keeps_her_recent_x():
    t = ar.RangeTracker(tables={})
    assert wr.hero_history(t).size == 0
    t.feed({"dt": ar.FT, "hero": {"pos": [30.0, 4.6]}, "ents": []})
    np.testing.assert_array_equal(wr.hero_history(t), np.full(wr.HIST_N, 30.0))
    for i in range(20):
        t.feed({"dt": ar.FT, "hero": {"pos": [30.0 + i, 4.6]}, "ents": []})
    np.testing.assert_array_equal(wr.hero_history(t), 30.0 + np.arange(20 - wr.HIST_N, 20))
    t.reset()
    assert len(t.hero_hist) == 0
    assert wr.hero_history(NS(hero=(12.0, 4.0))).tolist() == [12.0] * wr.HIST_N


# ---- B2Geometry ----

def _body_mask(x):
    return ar.poly_mask([np.array([[x - 1.8, 3.01], [x + 1.8, 3.01], [x + 1.8, 6.92], [x - 1.8, 6.92]])], 0.05)


def _support(units, hero_x, focus=9):
    """units {iid: root x}: Idle Clappers, each estimate its body box (raw = core, no hazards)."""
    now = {iid: (CL, {"pos": [x, 7.45], "vel": [0.0, 0.0]}, None) for iid, x in units.items()}
    trk = NS(now=now, tables={CL: NS(cell=0.05)}, hero=(hero_x, 4.6), T=0.0, orphan_hazards={},
             hero_hist=deque([hero_x] * wr.HIST_N, maxlen=16),
             estimate=lambda iid, k: NS(raw=_body_mask(units[iid]), core=_body_mask(units[iid]), haz=None, fam=None),
             standing_body=lambda iid, k: None)
    return v2.RangeSupport.build(trk, samples=tuple(range(0, 61)), margin_mode="focus", focus=focus)


def _geo(rs, target=9):
    return B2Geometry(NS(rs=rs), 100, NS(target_iid=target), None)


def _contacts(scan, owner=None):
    return [(c.frame - 100, c.kind) for c in scan.contacts if owner is None or c.owner_iid == owner]


def test_standing_3_5_u_from_the_other_idle_clapper_is_clear_by_the_walk_rule(monkeypatch):
    rs = _support({7: 24.5, 9: 36.0}, 28.0)
    p = route(np.full(61, 28.0), 4.6)
    monkeypatch.setattr(wr, "ENABLED", False)
    off = _geo(rs).scan(p)
    grown = [k for k, kind in _contacts(off, 7)]
    assert grown and min(grown) > 12 and all(kind == "body" for _, kind in _contacts(off, 7))   # the rule margin's growth
    monkeypatch.setattr(wr, "ENABLED", True)
    on = _geo(rs).scan(p)
    assert _contacts(on) == [] and on.source.endswith("walk rule body: 7")
    assert _geo(rs).preflight(p).contacts == ()


def test_running_into_the_other_clapper_is_still_a_body_contact(monkeypatch):
    rs = _support({7: 24.5, 9: 36.0}, 31.0)
    p = route(31.0 - 8.25 * wr.FT * np.arange(41), 4.6)
    for on in (False, True):
        monkeypatch.setattr(wr, "ENABLED", on)
        c = _contacts(_geo(rs).scan(p), 7)
        assert c and all(kind == "body" for _, kind in c)
        assert c[-1][0] == 40
    monkeypatch.setattr(wr, "ENABLED", True)
    first_on = _contacts(_geo(rs).scan(p), 7)[0][0]
    h, lo, hi = hits_of(24.5, np.full(wr.HIST_N, 31.0), p)
    assert first_on == int(np.flatnonzero(h)[0])


def test_the_target_keeps_its_raster_and_scan_batch_equals_scan(monkeypatch):
    monkeypatch.setattr(wr, "ENABLED", True)
    rs = _support({7: 24.5, 9: 36.0}, 28.0, focus=7)
    p = route(np.full(61, 28.0), 4.6)
    # the route's target keeps its own treatment: aimed at 7 the rule covers only 9, aimed at 9 only 7
    assert set(_geo(rs, target=7)._walkers(rs, [p], [(0, 60)], 61)) == {9}
    assert set(_geo(rs, target=9)._walkers(rs, [p], [(0, 60)], 61)) == {7}
    assert _geo(rs, target=7).scan(p).source.endswith("walk rule body: 9")
    rs2 = _support({7: 24.5, 9: 36.0}, 28.0)
    ps = [route(np.full(61, 28.0), 4.6), route(31.0 - 8.25 * wr.FT * np.arange(41), 4.6),
          route(np.linspace(28.0, 33.0, 31), 9.0)]
    g = _geo(rs2)
    batch = g.scan_batch(ps)
    for p_, b in zip(ps, batch):
        s = _geo(rs2).scan(p_)
        assert [(c.frame, c.owner_iid, c.kind) for c in b.contacts] == [(c.frame, c.owner_iid, c.kind) for c in s.contacts]
        assert b.source == s.source


def test_warm_loads_the_kernel_before_the_fight_and_is_wired(monkeypatch):
    import inspect
    import json
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy
    r = wr.warm()
    assert r["enabled"] is wr.ENABLED and r["ms"] >= 0 and json.dumps(r, allow_nan=False)
    calls = []
    monkeypatch.setattr(wr, "route_hits", lambda *a, **k: calls.append(1))
    monkeypatch.setattr(wr, "ENABLED", False)
    assert wr.warm()["enabled"] is False and not calls
    monkeypatch.setattr(wr, "ENABLED", True)
    assert wr.warm()["enabled"] is True and len(calls) == 2
    src = inspect.getsource(ForumPlannerPolicy.warmup)
    assert 'self.b2_warmup_report["walk_rule"]=_walk_rule.warm()' in src
