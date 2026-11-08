"""Task 182 seq 289 (the person: "4 moves' connected attacks": the blade after a dodge must connect).

Four small changes, each on an existing path:
- slam: the first middle landing after a real bounce aims inside the side slash's reach of the just-hit body as it will stand then
  (knife_chain_transfer.near_landing_goal, read by _middle_choice; the rows, the whole-route scan and an owned route as before);
- jump (and any Clapper's hammer recovery): two_play's IdleHit also starts at its Slam Recover entry (no hit reaction before Idle);
- small rune: at the press, the lowest hold that clears this tick's windows (a plan made early for the rows still to come
  no longer keeps its high hold);
- big rune / over_stay: the stage's own down-slash allowance (GoalPrefs.stay_pogo) also lets the chain's stomp strike that target.
"""
from dataclasses import replace
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import knife_chain_air_native as N
from ssbot.combat import knife_chain_transfer as T
from ssbot.combat import rune_lowhop as lh
from ssbot.combat import slam_play as sp
from ssbot.combat.knife_chain_commitment import ContactScan, MoveInstance, PathContact
from ssbot.combat.knife_chain_eval import Run
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.combat.knife_chain_transfer import TransferGoal
from ssbot.combat import two_play as tp
from ssbot.combat.tactics.modes import GoalPrefs
from tests.test_bounce_follow183 import Bout, clapper
from tests.test_knife_chain_transfer import fit_pose
from tests.test_sp13b import _two_cast
from tests.test_sp9 import run, two_state
from tests.test_target_entry_attack import native

HB = (0.0, 3.0, 0.5, 5.09)    # her box: width 0.5
SLASH_BOX_GAP = 3.12 - 0.25   # the side slash's reach in front of her box centre (slam_play.SLASH_X), box to box


def gap(lo, hi, bounced_right, root=None):
    # root: the bounced Clapper's root x (default its near edge, 1.34 u inside: a slam-pose body facing away)
    if root is None:
        root = hi + 1.34 if bounced_right else lo - 1.34
    return NS(lo=lo, hi=hi, width=hi - lo, seam=.5 * (lo + hi), direction=B["L"] if bounced_right else B["R"], caster=8, other=7, root=root)


# ---- slam: the landing inside the side slash's reach of the just-hit body ----

OFF = T.LAND_BODY_U + T.LAND_GAP_U + .25


def test_near_goal_is_measured_from_the_body_as_it_will_stand():
    # hit body on the right: its Idle pose facing her reaches root - 2.2516; her box 2.0 u clear of that, her centre .25 more
    assert T.near_landing_goal(gap(20., 32., True, root=34.), HB) == pytest.approx(34. - OFF)
    assert T.near_landing_goal(gap(20., 32., False, root=18.), HB) == pytest.approx(18. + OFF)
    assert T.LAND_GAP_U < SLASH_BOX_GAP                                                       # in reach, with margin
    assert T.LAND_BODY_U == 2.2516                                                            # the fit's Idle front


def test_near_goal_adds_her_own_half_width():
    wide = (0.0, 3.0, 1.0, 5.09)
    assert T.near_landing_goal(gap(20., 32., False, root=18.), wide) == pytest.approx(18. + T.LAND_BODY_U + T.LAND_GAP_U + .5)


def test_near_goal_does_not_depend_on_the_slam_pose_edge():
    # the same root with its body edge further out or in (a slam pose): the same aim; the edge only moves the seam / gap
    for edge in (19.5, 21., 22.5):
        assert T.near_landing_goal(gap(edge, 40., False, root=18.), HB) == pytest.approx(18. + OFF)


@pytest.mark.parametrize("right", [True, False])
def test_a_narrow_gap_keeps_its_centre_and_is_not_squeezed_toward_the_other_body(right):
    # the goal past the centre, or just at it: the centre
    for extra in (-2., -.5, 0.):
        root = 20.
        if right:
            hi = 22.
            lo = hi - 2 * (OFF - (root - hi)) - extra    # goal at the seam plus extra (on the bounced side when extra > 0)
            g = gap(lo, hi, True, root=root)
        else:
            lo = 18.
            hi = lo + 2 * (OFF - (lo - root)) + extra
            g = gap(lo, hi, False, root=root)
        assert T.near_landing_goal(g, HB) == g.seam
    # a little wider: the goal, on the hit body's side of the centre
    g = gap(10., 40., right, root=42. if right else 8.)
    goal = T.near_landing_goal(g, HB)
    assert goal != g.seam and (goal > g.seam) == right


LEFT = dict(bounced=(8, 24.1, -1), other=(7, 36.86, -1), hero=(23.2, 10.774, 11.4), stance_x=30.)


def _gap_of(bout):
    return T.two_gap({"ents": bout.ents}, bout.bounced)


@pytest.mark.parametrize("kw", [{}, LEFT], ids=["hit_on_the_right", "hit_on_the_left"])
def test_first_route_lands_in_side_slash_reach_of_the_hit_body(monkeypatch, kw):
    bout = Bout(monkeypatch, **kw)
    g = _gap_of(bout)
    log = bout.run()
    first = log[0]
    assert first["link"] == "middle"
    follow = first["offer"].details["follow"]
    assert follow["goal_x"] == pytest.approx(T.near_landing_goal(g, first["box"]))                        # the fresh route's goal
    assert first["offer"].details["checked_through"] == follow["land_f"]                                   # the whole route scanned
    landed = bout.notes("transfer_follow_landed")
    assert len(landed) == 1
    box = landed[0]["box"]
    assert g.lo + T.MIDDLE_PAD_U <= box[0] and box[2] <= g.hi - T.MIDDLE_PAD_U                             # still between the bodies
    to_hit_body = (g.root - T.LAND_BODY_U) - box[2] if g.direction == B["L"] else box[0] - (g.root + T.LAND_BODY_U)
    assert to_hit_body <= SLASH_BOX_GAP                                                                    # the landing attack reaches its Idle body
    centre = .5 * (box[0] + box[2])
    assert (centre > g.seam) == (g.direction == B["L"])                                                    # the hit body's side of the centre


def test_an_owned_route_keeps_the_goal_it_chose(monkeypatch):
    bout = Bout(monkeypatch)
    bout.tick()
    goal = bout.n.runner.run.v["follow"]["goal_x"]
    fit_pose(bout.ents[1], x=bout.ents[1]["pos"][0] + .6)        # the hit body has moved: a re-chosen goal would follow it
    bout.tick()
    assert bout.n.runner.run.v["follow"]["goal_x"] == goal
    # the owned route's next ticks went through _owned_route; a blocked route searches again, from the goal it chose
    monkeypatch.setattr(bout.n, "_owned_route", lambda *a, **k: None)
    bout.tick()
    assert bout.n.runner.run.v["follow"]["goal_x"] == goal


def test_a_blocked_near_landing_takes_the_next_clean_row_inside_the_gap(monkeypatch):
    # a danger on the near landing: the same scan turns those rows down and the nearest clean one to the goal is taken
    free = Bout(monkeypatch)
    free.tick()
    near = free.log[0]["offer"].details["follow"]["landing_box"]
    bout = Bout(monkeypatch, danger=[(near[0] - .1, 2.9, near[2] + .1, 5.2)])
    g = _gap_of(bout)
    log = bout.run()
    follow = log[0]["offer"].details["follow"]
    assert follow["rank"] > 0 and follow["goal_x"] == pytest.approx(T.near_landing_goal(g, log[0]["box"]))
    box = follow["landing_box"]
    assert not (box[0] < near[2] + .1 and box[2] > near[0] - .1)
    assert g.lo + T.MIDDLE_PAD_U <= box[0] and box[2] <= g.hi - T.MIDDLE_PAD_U
    assert bout.notes("transfer_follow_middle")[0]["rejected_before"]


# ---- slam: on the way down at its head height, one side slash before the landing ----

SIM = NS(off=2)


def fall_boxes(n, x0, y0, dy=.4, dx=0.):
    """Her boxes after each row command (index SIM.off + m), falling dy a frame from box bottom y0."""
    out = np.zeros((SIM.off + n, 4), float)
    for m in range(n):
        x = x0 + dx * m
        out[SIM.off + m] = (x, y0 - dy * m, x + .5, y0 - dy * m + 2.08)
    return out


LEFT_GAP = gap(22.25, 40., False, root=20.)      # the hit body on the left: its Idle edge at 22.25, the slash goes left


def test_the_fall_slash_presses_at_the_first_low_frame_in_reach():
    row = np.full(30, B["R"], np.int64)
    # bottom 9.0 falling .4 a frame: <= 6.2 from m = 7; her centre 24.75 (2.5 u from the edge)
    out, m = T.fall_slash_commands(SIM, row, fall_boxes(30, 24.5, 9.), LEFT_GAP, 0.)
    assert m == 7
    assert out[m - 1] == B["L"] and out[m] == out[m + 1] == B["A"] | B["L"]
    others = np.delete(out, [m - 1, m, m + 1])
    assert (others == B["R"]).all() and (row == B["R"]).all()            # the rest of the row is untouched


def test_the_fall_slash_waits_for_the_attack_cooldown():
    row = np.full(30, B["R"], np.int64)
    _, m = T.fall_slash_commands(SIM, row, fall_boxes(30, 24.5, 9.), LEFT_GAP, .2)     # ready at ceil(.2 * 60) - 2 = 10
    assert m == 10


def test_no_fall_slash_out_of_reach_too_high_or_too_late():
    row = np.full(30, B["R"], np.int64)
    assert T.fall_slash_commands(SIM, row, fall_boxes(30, 26., 9.), LEFT_GAP, 0.) is None        # 3.5 u from the edge
    assert T.fall_slash_commands(SIM, row, fall_boxes(30, 24.5, 20.), LEFT_GAP, 0.) is None      # never down at its head by the end
    late = np.full(9, B["R"], np.int64)
    assert T.fall_slash_commands(SIM, late, fall_boxes(9, 24.5, 9.), LEFT_GAP, .2) is None       # the landing comes first


def test_the_route_carries_the_fall_slash_and_still_scans_whole(monkeypatch):
    bout = Bout(monkeypatch)
    first = bout.run()[0]
    follow = first["offer"].details["follow"]
    assert follow["fall_slash"] is not None
    masks = first["offer"].details["follow_masks"]
    m = follow["fall_slash"]
    assert masks[m] == masks[m + 1] == B["A"] | B["R"] and masks[m - 1] == B["R"]              # the hit body is on her right
    assert first["offer"].details["checked_through"] == follow["land_f"]                       # the whole route with it scanned
    assert len(bout.notes("transfer_follow_landed")) == 1
    assert bout.notes("transfer_follow_middle")[0]["fall_slash"] == m


def test_a_fall_slash_route_with_a_contact_keeps_the_plain_row(monkeypatch):
    bout = Bout(monkeypatch)
    Geo0 = N.B2Geometry

    class Geo1(Geo0):
        def scan(self, path, limit=None):
            if any(int(c) & B["A"] for c in np.asarray(path.commands)):
                return ContactScan(self.ref(path), path.origin, path.origin + 2, (PathContact(path.origin + 2, 99, "delayed"),), "a slash row refused")
            return super().scan(path, limit)

    monkeypatch.setattr(N, "B2Geometry", Geo1)
    follow = bout.run()[0]["offer"].details["follow"]
    assert follow["fall_slash"] is None


# ---- jump: IdleHit also starts when the landing hammer is off (Slam Recover: no hit reaction before Idle) ----


@pytest.fixture
def on(monkeypatch):
    for k in ("CHASE", "IDLEHIT", "CAST", "SPACE", "OPEN", "ANY"):
        monkeypatch.setattr(tp, k, True)


def test_slam_recover_entry_presses_the_side_slash_at_once(on):
    two = tp.TwoPlay()
    two.prev[7] = ("Slam 1", .03)                       # Slam 2 is really entered on frame 1000 (no start there)
    out = run(two, [two_state(1000, "Slam 2", .05), two_state(1001, "Slam Recover", 0.0), two_state(1002, "Slam Recover", 1 / 60)])
    assert out[0] is None
    assert out[1] == sp.M_A | sp.M_R and out[2] == sp.M_A | sp.M_R        # the press and its second frame, toward F (on her right)
    st = two.stats()
    assert st["idle_runs"] == 1 and st["idle_press"] == 1


def test_a_recover_seen_first_on_the_first_frame_starts_nothing(on):
    two = tp.TwoPlay()
    out = run(two, [two_state(1000, "Slam Recover", .05), two_state(1001, "Slam Recover", .07)])
    assert out == [None, None] and two.stats().get("idle_runs", 0) == 0


def test_the_run_goes_on_from_recover_into_idle_and_the_idle_entry_still_presses(on):
    two = tp.TwoPlay()
    # no press in the recovery: the attack is on cooldown at the Recover entry; the run stays open, the Idle entry starts its own
    out = run(two, [two_state(1000, "Slam 2", .05), two_state(1001, "Slam Recover", 0.0, atk_cd=.2), two_state(1002, "Slam Recover", 1 / 60, atk_cd=.2),
                    two_state(1003, "Idle", 0.0)])
    assert out[1] == 0 and out[2] == 0                                     # stands still (cooldown ends inside the window)
    assert out[3] == sp.M_A | sp.M_R and two.stats()["idle_runs"] == 2


def _in_idle(two):
    two.prev[7] = ("Idle", .4)                        # already in Idle: no entry edge, only the landing can start the run


def test_landing_in_reach_of_an_idle_clapper_presses_on_the_landing_tick(on):
    two = tp.TwoPlay()
    _in_idle(two)
    out = run(two, [two_state(1000, "Idle", .5, ground=False), two_state(1001, "Idle", .52, ground=True), two_state(1002, "Idle", .54, ground=True)])
    assert out[0] is None and out[1] == sp.M_A | sp.M_R and out[2] == sp.M_A | sp.M_R
    assert two.stats()["idle_press"] == 1


def test_landing_out_of_reach_or_on_a_busy_clapper_starts_nothing(on):
    two = tp.TwoPlay()
    _in_idle(two)
    assert run(two, [two_state(1000, "Idle", .5, ground=False, x_rel=9.), two_state(1001, "Idle", .52, ground=True, x_rel=9.)]) == [None, None]
    two = tp.TwoPlay()
    two.prev[7] = ("Walk", .4)
    assert run(two, [two_state(1000, "Walk", .5, ground=False), two_state(1001, "Walk", .52, ground=True)]) == [None, None]
    two = tp.TwoPlay()
    _in_idle(two)
    assert run(two, [two_state(1000, "Idle", .5, ground=True), two_state(1001, "Idle", .52, ground=True)]) == [None, None]    # no landing edge


def test_landing_into_recover_starts_the_run_too(on):
    two = tp.TwoPlay()
    two.prev[7] = ("Slam Recover", .1)
    out = run(two, [two_state(1000, "Slam Recover", .12, ground=False), two_state(1001, "Slam Recover", .14, ground=True)])
    assert out == [None, sp.M_A | sp.M_R]


def _falling(s, bottom, vy=-9.0):
    s["hero"]["box"] = [s["hero"]["box"][0], bottom, s["hero"]["box"][2], bottom + 2.08]
    s["hero"]["vel"] = [0.0, vy]
    return s


def test_the_fall_slash_goes_at_head_height_before_the_landing(on):
    two = tp.TwoPlay()
    two.prev[7] = ("Slam 2", .05)
    out = run(two, [_falling(two_state(1000, "Slam Recover", 0.0, ground=False), 8.0),      # the entry, still high
                    _falling(two_state(1001, "Slam Recover", 1 / 60, ground=False), 7.2),
                    _falling(two_state(1002, "Slam Recover", 2 / 60, ground=False), 6.1),   # at its head height, in reach
                    _falling(two_state(1003, "Slam Recover", 3 / 60, ground=False), 5.8)])
    assert out[0] is None and out[1] is None                                                # no slash high up
    assert out[2] == sp.M_A | sp.M_R and out[3] == sp.M_A | sp.M_R                          # the press and its second frame, in the air


def test_no_fall_slash_on_the_way_up_or_out_of_reach(on):
    two = tp.TwoPlay()
    two.prev[7] = ("Slam 2", .05)
    out = run(two, [_falling(two_state(1000, "Slam Recover", 0.0, ground=False), 6.0, vy=+4.),   # rising past its head height
                    _falling(two_state(1001, "Slam Recover", 1 / 60, ground=False), 6.1, vy=+2.)])
    assert out == [None, None]


@pytest.mark.parametrize("x_rel", [6., 7., 8., 9.])
def test_the_air_branch_only_presses_it_never_walks_toward_it(on, x_rel):
    two = tp.TwoPlay()
    two.prev[7] = ("Slam 2", .05)
    out = run(two, [_falling(two_state(1000, "Slam Recover", 0.0, ground=False, x_rel=x_rel), 6.0)])
    assert out == [None] and two.idle.walk == 0 and two.idle.why == "air far"              # out of reach: the row keeps the keys


@pytest.mark.parametrize("off,want", [(.3, None), (.95, None), (1.05, "press"), (1.5, "press")])
def test_the_air_press_keeps_her_box_off_its_body(on, off, want):
    two = tp.TwoPlay()
    two.prev[7] = ("Slam 2", .05)
    edge = tp.body_span(two_state(1000, "Slam Recover", 0.0)["ents"][0])[0]                 # F's near edge (she is on its left)
    s = _falling(two_state(1000, "Slam Recover", 0.0, ground=False, hx=edge - off), 6.0)
    s["hero"]["vel"] = [0.0, -9.0]
    out = run(two, [s])
    assert out == ([sp.M_A | sp.M_R] if want else [None])
    if not want:
        assert two.idle.why == "air body"


def test_the_body_margin_is_for_the_air_only(on):
    two = tp.TwoPlay()
    two.prev[7] = ("Slam 2", .05)
    edge = tp.body_span(two_state(1000, "Slam Recover", 0.0)["ents"][0])[0]
    out = run(two, [two_state(1000, "Slam Recover", 0.0, hx=edge - .3)])                    # on the ground, close: the press as before
    assert out == [sp.M_A | sp.M_R]


def test_in_the_air_the_cooldown_keeps_the_rows_keys(on):
    two = tp.TwoPlay()
    two.prev[7] = ("Slam 2", .05)
    out = run(two, [_falling(two_state(1000, "Slam Recover", 0.0, ground=False, atk_cd=.1), 6.0)])
    assert out == [None] and two.idle.why == "cooldown"                                     # no standing still in the air
    two = tp.TwoPlay()
    two.prev[7] = ("Slam 2", .05)
    out = run(two, [two_state(1000, "Slam Recover", 0.0, atk_cd=.1)])
    assert out == [0]                                                                       # on the ground it still waits, as before


def test_recover_runs_are_guarded_like_idle_runs(on):
    # air: no start; the other Clapper's slam in reach of her: no start (other_danger); out of walking reach: no walk
    two = tp.TwoPlay()
    assert run(two, [two_state(1000, "Slam 2", .05, ground=False), two_state(1001, "Slam Recover", 0.0, ground=False)]) == [None, None]
    two = tp.TwoPlay()
    out = run(two, [two_state(1000, "Slam 2", .05, b_st="Slam Antic", b_x=36.), two_state(1001, "Slam Recover", 0.0, b_st="Slam Antic", b_x=36.)])
    assert out == [None, None]
    two = tp.TwoPlay()
    assert run(two, [two_state(1000, "Slam 2", .05, x_rel=14.), two_state(1001, "Slam Recover", 0.0, x_rel=14.)]) == [None, None]


# ---- small rune: the lowest hold at the press ----


def brute(thr, k, h_min, planned, w_end):
    rel = [w for w in thr if k < w[0] <= w_end]
    for H in range(h_min, planned):
        lo_t = lh.HOP_LO[H]
        if all(w1 - k < len(lo_t) and all(lo_t[j] >= th for j in range(w0 - k, w1 - k + 1)) for w0, w1, th in rel):
            return H
    return planned


def test_a_high_plan_comes_down_to_the_lowest_hold_that_clears_this_ticks_windows():
    plan = {"H": 21, "P": 62, "w_end": 102}
    thr = [(79, 88, 2.95), (77, 89, 2.95)]
    h = lh.RuneLowHop._lowest_hold(plan, thr, 62, 9)
    assert h == brute(thr, 62, 9, 21, 102) and h < 17                                                       # a low hop
    lo_t = lh.HOP_LO[h]
    assert all(lo_t[j] >= 2.95 for w0, w1, _ in thr for j in range(w0 - 62, w1 - 62 + 1))
    assert not all(lh.HOP_LO[h - 1][j] >= 2.95 for w0, w1, _ in thr for j in range(w0 - 62, w1 - 62 + 1) if j < len(lh.HOP_LO[h - 1]))


def test_every_window_of_this_hop_must_be_cleared_even_past_a_low_landing():
    # (70, 75) needs only a low hop, (98, 104) only a long one: a short hold would be down before it: not lowered past it
    plan = {"H": 26, "P": 62, "w_end": 104}
    thr = [(73, 76, 2.95), (98, 104, 2.95)]
    h = lh.RuneLowHop._lowest_hold(plan, thr, 62, 9)
    assert h == brute(thr, 62, 9, 26, 104) and h > 16
    assert all(lh.HOP_LO[h][j] >= 2.95 for j in range(98 - 62, 104 - 62 + 1))


def test_a_split_plans_later_windows_are_its_second_hops():
    plan = {"H": 21, "P": 62, "w_end": 89, "H2": 16}
    thr = [(79, 88, 2.95), (140, 147, 2.95)]
    assert lh.RuneLowHop._lowest_hold(plan, thr, 62, 9) == brute([(79, 88, 2.95)], 62, 9, 21, 89)


def test_a_window_already_on_at_the_press_is_not_this_hops():
    plan = {"H": 21, "P": 62, "w_end": 102}
    assert (lh.RuneLowHop._lowest_hold(plan, [(60, 70, 2.95), (79, 88, 2.95)], 62, 9)
            == lh.RuneLowHop._lowest_hold(plan, [(79, 88, 2.95)], 62, 9))


def test_no_lower_hold_clears_keeps_the_plan():
    plan = {"H": 21, "P": 62, "w_end": 102}
    assert lh.RuneLowHop._lowest_hold(plan, [(79, 88, 9.)], 62, 9) == 21


def _press_tick(monkeypatch, windows, planned=21):
    """The real step path at the press: a run in its stance, a kept plan with its press due this tick, these windows."""
    h = lh.RuneLowHop(two=True)
    h.b2 = True
    for i in range(0, 40):
        s = _two_cast(i, -1)
        h.step(5000 + i, s, True, True, t_game=(5000 + i) / 60.0, bombs=np.zeros((0, 6)))
        if h.run is None:
            break
    r = h.run
    assert r is not None and r.phase == "stance"
    k = r.k + 1
    windows = [(k + a, k + b, th) for a, b, th in windows]      # relative to the press frame
    monkeypatch.setattr(lh.RuneLowHop, "_threat_windows", lambda self, run, hx, xs: list(windows))
    monkeypatch.setattr(lh.RuneLowHop, "_fc_windows", lambda self, run, hx, xs=(): [])
    key = [(int(a), int(b), round(x, 2)) for a, b, x in windows]
    r.plan = {"H": planned, "P": k, "lo": k, "hi": k, "w_end": max(w[1] for w in windows), "n": 1, "of": 1, "H2": None, "k": k - 40, "thr": key}
    s = _two_cast(40, -1)
    m = h.step(5040, s, True, True, t_game=5040 / 60.0, bombs=np.zeros((0, 6)))
    return h, r, k, m, windows


def test_the_press_path_uses_the_lowest_hold_and_counts_it(monkeypatch):
    h, r, k, m, w = _press_tick(monkeypatch, [(15, 24, 2.95)])
    assert r.phase == "hop" and r.P == k and m & lh.M_J
    assert r.H == brute(w, k, h.cfg.h_min, 21, k + 24) and r.H < 17 and r.big == 0


def test_the_press_path_keeps_a_needed_high_hold(monkeypatch):
    h, r, k, m, w = _press_tick(monkeypatch, [(15, 17, 2.95), (40, 42, 2.95)], planned=26)
    assert r.phase == "hop" and r.H == brute(w, k, h.cfg.h_min, 26, k + 42) and r.H > 16 and r.big == 1


# ---- big rune: over_stay's down slash also opens the chain's stomp ----


def _goal_scene():
    ents = [clapper(7, 40.8, -1, "Air"), clapper(8, 29.5, 1, "Idle")]
    state = {"f": 2980, "hero": {"pos": [33.3, 8.9], "box": [33.05, 8.87, 33.55, 10.95], "vel": [0., 0.], "health": 7,
                                 "hero_accepting_input": True, "tm": {"dash_cd": 0.}, "anim": {"clip": "Airborne"}}, "ents": ents, "act": {"hf": {}}}
    n = native()
    n._transfer_goal = TransferGoal(8, 8, 2974, 19.9, "BOUNCE", MoveInstance(7, 2900, "CC_JUMP_CAST"))
    n._idle_ev = {8: {"entry": 2974, "buddy": True, "hit": None}}       # the Idle entered on the bounce (CANCEL), the buddy attacking
    return n, state


def _prefs(**kw):
    return GoalPrefs(mode="RUSH", stance_x=29.5, weights={}, target=8, **kw)


def test_the_stages_own_down_slash_lets_the_chains_stomp_strike_it():
    n, state = _goal_scene()
    prefs = _prefs(no_hit=frozenset({7, 8}), stay_pogo=frozenset({8}))
    out = n.goal_preferences(state, prefs, handoff=True)
    assert out is not prefs and out.target == prefs.target and out.no_hit == prefs.no_hit and n._transfer_ready
    assert [e for e in n.events if e["event"] == "target_transfer_blade"][-1]["blade"] == "stomp"


def test_any_other_ban_on_the_target_still_closes_it():
    n, state = _goal_scene()
    n.goal_preferences(state, _prefs(no_hit=frozenset({7, 8})), handoff=True)
    assert not n._transfer_ready
    assert [e for e in n.events if e["event"] == "target_transfer_blade"][-1]["blade"] == "unavailable"


def test_another_clappers_allowance_does_not_open_this_target():
    n, state = _goal_scene()
    n.goal_preferences(state, _prefs(no_hit=frozenset({7, 8}), stay_pogo=frozenset({7})), handoff=True)
    assert not n._transfer_ready


def test_the_allowance_needs_a_fresh_idle():
    for ev in (None, {"entry": 2974, "buddy": True, "hit": 2978}, {"entry": 2974, "buddy": None, "hit": None}):
        n, state = _goal_scene()
        n._idle_ev = {8: ev} if ev is not None else {}
        n.goal_preferences(state, _prefs(no_hit=frozenset({7, 8}), stay_pogo=frozenset({8})), handoff=True)
        assert not n._transfer_ready


def test_the_allowance_is_for_a_bounce_goal_only():
    n, state = _goal_scene()
    n._transfer_goal = TransferGoal(8, 7, 2974, 19.9, "SWITCH", MoveInstance(7, 2900, "CC_JUMP_CAST"))
    n.goal_preferences(state, _prefs(no_hit=frozenset({7, 8}), stay_pogo=frozenset({8})), handoff=True)
    assert not n._transfer_ready


def test_no_ban_is_unchanged():
    n, state = _goal_scene()
    out = n.goal_preferences(state, _prefs(), handoff=True)
    assert n._transfer_ready and out is not None


# ---- big rune: with the other Clapper in the air the vault branch no longer swallows a BOUNCE goal's own strike ----

def _bounce_routing(monkeypatch, kind="BOUNCE", ready=True, vault=None):
    from ssbot.combat import knife_chain_vault_native as VN
    from tests.test_knife_chain_vault_manual import _switch_routing_scene
    n, raw, sim, prefs, delegated, marker = _switch_routing_scene("right", monkeypatch)
    prefs.entry_attack = None
    n._transfer_goal = replace(n._transfer_goal, source_kind=kind)
    n._transfer_ready, n._vault_ready, n._air_context = ready, True, None
    monkeypatch.setattr(VN, "propose", vault if callable(vault) else (lambda *a: vault))
    out = n._propose(NS(), None, sim.start, sim.hold, sim.prefix, NS(), prefs, None)
    return out, delegated, marker


def test_no_vault_action_leaves_a_bounce_goal_its_own_strike(monkeypatch):
    out, delegated, marker = _bounce_routing(monkeypatch)
    assert out is marker and len(delegated) == 1


@pytest.mark.parametrize("kw", [{"ready": False}, {"kind": "CAST"}, {"kind": "SWITCH"}])
def test_only_a_ready_bounce_goal_falls_through_the_vault(monkeypatch, kw):
    out, delegated, _ = _bounce_routing(monkeypatch, **kw)
    assert out is None and not delegated


def test_a_vault_offer_keeps_the_keys(monkeypatch):
    offer = object()
    out, delegated, _ = _bounce_routing(monkeypatch, vault=offer)
    assert out is offer and not delegated


@pytest.mark.parametrize("what", ["run", "recovery"])
def test_a_vault_that_started_or_failed_keeps_its_owner(monkeypatch, what):
    from tests.test_knife_chain_vault_manual import _switch_routing_scene
    from ssbot.combat import knife_chain_vault_native as VN
    n, raw, sim, prefs, delegated, marker = _switch_routing_scene("right", monkeypatch)
    prefs.entry_attack = None
    n._transfer_goal = replace(n._transfer_goal, source_kind="BOUNCE")
    n._transfer_ready, n._vault_ready, n._air_context = True, True, None

    def vault(*a):
        if what == "run":
            n.runner.run = Run("vault_idle", "near", {"iid": prefs.target})
        else:
            n.recovery = {"reason": "x"}

    monkeypatch.setattr(VN, "propose", vault)
    monkeypatch.setattr(n, "_recovery_offer", lambda: None, raising=False)
    monkeypatch.setattr(n, "queued_prefix", lambda *a: (int(sim.prefix[0]), "test"))      # (the owner check itself, not a prefix refusal)
    assert n._propose(NS(), None, sim.start, sim.hold, sim.prefix, NS(), prefs, None) is None
    assert not delegated
