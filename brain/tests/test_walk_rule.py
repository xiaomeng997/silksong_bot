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


def hits_of(x0, hist, p, offset=0, prelude=None):
    n = len(p.box) - 1
    h, lo, hi = wr.route_hits(x0, np.asarray(hist, float), [p], [(offset, n)], n + 1,
                              preludes=None if prelude is None else [prelude])
    return h[0], lo[0], hi[0]


def reference(x0, hist, hx, cx, cy, n, off, pre=None):
    """A plain restatement of the rule (not the kernel's code). Sol seq 359: her x before the route (frames 1 .. off - 1)
    is pre's (nan or absent: unknown), never the route's own first point; no history: unknown; a window holding an
    unknown x moves both ends out."""
    lag = wr.LAG_F
    her = {}
    for f in range(-lag, off + n):
        if f <= 0:
            her[f] = hist[lag + f] if hist is not None else float("nan")
        elif f < off:
            her[f] = pre[f - 1] if pre is not None and f - 1 < len(pre) else float("nan")
        else:
            her[f] = hx[f - off]
    lo = hi = x0
    out_h, out_lo, out_hi = [], [], []
    for i in range(off + n):
        if i > 0:
            w = [her[f] for f in range(i - 1 - lag, i)]
            unknown = any(v != v for v in w)
            if unknown or not (min(w) > hi and max(w) <= hi + wr.D_FWD - STEP):
                hi += STEP
            if unknown or not (max(w) < lo and min(w) >= lo - wr.D_FWD + STEP):
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
    for _ in range(120):
        n = int(rng.integers(1, 70))
        off = int(rng.integers(0, 9))
        x0 = float(rng.uniform(18, 44))
        hx = x0 + rng.uniform(-12, 12) + np.cumsum(rng.normal(0, .35, n + 1))
        cy = np.clip(4.6 + np.cumsum(rng.normal(0, .3, n + 1)), 4.6, 14.0)
        hist = None if rng.random() < .2 else x0 + rng.uniform(-12, 12) + np.cumsum(rng.normal(0, .3, wr.HIST_N))
        if hist is not None and rng.random() < .2:
            hist[:int(rng.integers(1, wr.HIST_N))] = np.nan          # a short tracker history (Sol seq 359: unknown)
        pre = None
        if off > 1 and rng.random() < .7:                             # the same candidate's earlier part, partly known
            pre = hx[0] + np.cumsum(rng.normal(0, .35, off - 1))[::-1]
            pre[rng.random(off - 1) < .2] = np.nan
        p = route(hx, cy)
        h, lo, hi = wr.route_hits(x0, np.zeros(0) if hist is None else hist, [p], [(off, n)], n + 1,
                                  preludes=None if pre is None else [[pre]])
        rh, rlo, rhi = reference(x0, hist, hx, hx, 0.5 * (p.box[:, 1] + p.box[:, 3]), n + 1, off, pre)
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
    h = wr.hero_history(t)          # Sol seq 359: the frames the tracker has not seen are unknown, not her oldest x
    assert h.size == wr.HIST_N and np.isnan(h[:-1]).all() and h[-1] == 30.0
    for i in range(20):
        t.feed({"dt": ar.FT, "hero": {"pos": [30.0 + i, 4.6]}, "ents": []})
    np.testing.assert_array_equal(wr.hero_history(t), 30.0 + np.arange(20 - wr.HIST_N, 20))
    t.reset()
    assert len(t.hero_hist) == 0
    h = wr.hero_history(NS(hero=(12.0, 4.0)))
    assert np.isnan(h[:-1]).all() and h[-1] == 12.0


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


# ---- Sol seq 359 (Astra, #418 P2): a route that starts later walks the same candidate's earlier part ----

def _astra():
    """analysis/walk_rule418_20261113/ASTRA_REVIEW418.json: the walker at 24.5, her history at 34.5; 30 frames high in
    the air from 34.5 to 29.5, then 10 frames falling at x 29.5. The whole route from frame 100, its suffix from 130."""
    X = np.r_[np.linspace(34.5, 29.5, 31), np.full(10, 29.5)]
    Y = np.r_[np.full(31, 10.0), np.linspace(9.46, 4.6, 10)]
    return route(X, Y, origin=100), route(X[30:], Y[30:], origin=130)


def test_a_later_route_walks_the_same_candidates_earlier_part():
    whole, suffix = _astra()
    hist = np.full(wr.HIST_N, 34.5)
    hw, lw, uw = hits_of(24.5, hist, whole)
    assert list(np.flatnonzero(hw)) == list(range(32, 41)) and uw[30] == pytest.approx(27.4333, abs=1e-3)
    # the suffix handed the earlier part: the whole route's interval and contacts, frame by frame
    hs, ls, us = hits_of(24.5, hist, suffix, offset=30, prelude=wr.gap_xs(100, 30, whole))
    np.testing.assert_array_equal(hs, hw[30:])
    np.testing.assert_allclose(us, uw[30:])
    np.testing.assert_allclose(ls, lw[30:])
    # without it those frames are unknown: never a smaller interval (8a9919e6 filled them with 29.5: 25.9667, no contact)
    hu, lu, uu = hits_of(24.5, hist, suffix, offset=30)
    assert (uu >= uw[30:] - 1e-9).all() and (lu <= lw[30:] + 1e-9).all() and (hu >= hw[30:]).all()
    assert uu[0] > uw[30] + 1.0


def test_prelude_alternatives_are_each_walked():
    whole, suffix = _astra()
    hist = np.full(wr.HIST_N, 34.5)
    near = (100, np.full(40, 29.5))                                   # another way here: at 29.5 from frame 100
    a = hits_of(24.5, hist, suffix, offset=30, prelude=wr.gap_xs(100, 30, near))
    b = hits_of(24.5, hist, suffix, offset=30, prelude=wr.gap_xs(100, 30, whole))
    both = hits_of(24.5, hist, suffix, offset=30, prelude=wr.gap_xs(100, 30, [near, whole]))
    assert a[2][0] < b[2][0]                                          # the two ways give different intervals
    np.testing.assert_array_equal(both[0], a[0] | b[0])
    np.testing.assert_allclose(both[2], np.fmax(a[2], b[2]))
    np.testing.assert_allclose(both[1], np.fmin(a[1], b[1]))


def _near():
    """She stands 4.5 u from the walker's root (24.5) for 30 frames, then 3.5 u: inside its 5.5 u it never closes, and
    her 28.0 stays clear of its body (root + 2.8 u + her half width); the same frames unknown let it close onto her."""
    X = np.r_[np.full(31, 29.0), np.full(10, 28.0)]
    return route(X, 4.6, origin=100), route(X[30:], 4.6, origin=130)


def test_b2geometry_checks_a_later_route_with_its_earlier_part(monkeypatch):
    """Single (scan / preflight with prelude=) and batch (scan_batch with preludes=, or the path's walk_prelude): the
    whole route's contacts of the walker on the suffix's frames; nothing handed on: a superset."""
    monkeypatch.setattr(wr, "ENABLED", True)

    def own7(scan):
        return [(c.frame, c.kind) for c in scan.contacts if c.owner_iid == 7]
    for case, hero_x, first in ((_astra, 34.5, 132), (_near, 29.0, None)):
        whole, suffix = case()
        rs = _support({7: 24.5, 9: 40.0}, hero_x)
        ref = [c for c in own7(_geo(rs).scan(whole)) if c[0] >= 130]
        assert (ref[0][0] if ref else None) == first and all(kind == "body" for _, kind in ref)
        assert own7(_geo(rs).scan(suffix, prelude=whole)) == ref
        assert own7(_geo(rs).preflight(suffix, prelude=whole)) == ref
        assert own7(_geo(rs).scan_batch([suffix, whole], preludes=[whole, None])[0]) == ref
        tagged = route(whole.pos[30:, 0], whole.pos[30:, 1], origin=130)
        tagged.walk_prelude = whole
        assert own7(_geo(rs).scan(tagged)) == ref and own7(_geo(rs).scan_batch([tagged])[0]) == ref
        alone = own7(_geo(rs).scan(suffix))
        assert set(ref) <= set(alone)
        if case is _near:
            assert alone                         # unknown frames let it close: the earlier part is what keeps her clear


def test_the_continuation_callers_hand_on_their_earlier_part(monkeypatch):
    from dataclasses import dataclass
    from ssbot.combat import knife_chain_post_actions as Post
    from ssbot.combat.knife_chain_air_native import NativeManualAirChain as Native
    from ssbot.combat.knife_chain_commitment import ContactScan, MoveInstance

    @dataclass
    class P:
        origin: int = 90
        through: int = 100
        stage: str = "approach"
        end: str = "bounce"
        kind: str = "parent"
        full: bool = False
    monkeypatch.setattr(Post, "ordinary_post", lambda parent, params, terrain, *, kind, profile, full=False:
                        P(100, 150 if full else 112, "continuation", "handback" if full else "short", kind, full))
    seen = []
    geo = NS(ref=lambda p: p.kind, scan=lambda p: seen.append((p.full, getattr(p, "walk_prelude", None)))
             or ContactScan(p.kind, p.origin, p.through, (), "clear"))
    parent = P()
    n = NS(profile=NS(short_frames=12), continuation_executable=lambda kind, p: True)
    Native._continuations(n, parent, NS(params=None, terrain=None), geo, MoveInstance(7, 80, "CC_SLAM"),
                          wall_validator=lambda p: p.kind == "left_landing" and not p.full)   # a full exit is checked too
    assert [full for full, _ in seen] == [False, False, True] and all(w is parent for _, w in seen)
    # knife_chain_b2's post-bounce exits (short and full): future's frames before the bounce
    import inspect
    from ssbot.combat import knife_chain_b2 as B
    src = inspect.getsource(B)
    assert "path.walk_prelude=future" in src and "p.walk_prelude=future" in src


def test_the_hook_entry_hands_each_way_on_to_its_stops_and_controls():
    from ssbot.combat import knife_chain_face_hook as FH
    from ssbot.combat.knife_chain_commitment import ContactScan
    from tests.test_hook_entry_bounce308 import V, hook_case, moving_rs
    f = 1001
    a, s, sim, g, path = hook_case(moving_rs())
    items = FH._entry(path, V(a), f)
    assert any(q.origin > f for q, _, _, _ in items)               # the intermediate stops start after f
    bounds = [.5 * (q.box[:, 0] + q.box[:, 2]) for q, _, _, _ in items if q.origin == f]
    for q, _, control, _ in items:
        assert q.walk_to_control and all(first == f and len(xs) == control[0] - f + 1 for first, xs in q.walk_to_control)
        own = .5 * (q.box[:, 0] + q.box[:, 2])
        k0 = q.origin - f
        for _, xs in q.walk_to_control:                             # its own rows from its origin on
            np.testing.assert_allclose(xs[k0:], own)
            # before them: a bound track's frames, the bound whose frame at the stop's origin is the stop's first row
            assert k0 == 0 or any(len(b) > k0 and np.array_equal(b[:k0], xs[:k0]) and b[k0] == own[0] for b in bounds)
        assert (q.walk_prelude is None) == (q.origin == f)

    class Geo:
        def __init__(self):
            self.paths = []

        def scan_batch(self, paths):
            self.paths += paths
            return [ContactScan("t", p.origin, p.through, (), "clear") for p in paths]
    v = V(a)
    _, controls = FH.entry_scan(Geo(), path, v, f)
    assert set(v["_hook_prelude"]) == set(controls)
    out = Geo()
    FH.entry_outs(out, sim, v, f, controls, 12)
    assert out.paths and all(any(p.walk_prelude is w for c, w in v["_hook_prelude"].items() if c[0] == p.origin)
                             for p in out.paths)
