"""Task 182 seq 312 (the person 11-09 / 11-10; plan: main docs/plans/forum_clapper_l2_tactics.md "seq312"): the far one's move with the
near one or a big rune between, the small rune's down slashes and its end, the stacked pair's follow-up (#379), the cluster's outer
variant, and the chain's route read against the other body. L2 through its real entry (tests/test_clapper_priority's scene)."""
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import knife_chain_transfer as T
from ssbot.combat.tactics import clapper_plans as CP, clapper_separated as SEP, gauntlet as G
from ssbot.combat.tactics.l2_plan import Candidate
from ssbot.core.worldstate import E, Ev
from tests.test_clapper_priority import change, manual, scene, step   # noqa: F401  (autouse manual-B fixture)
from tests.test_middle_return313 import hero_at, move, near_attack


@pytest.fixture(autouse=True)
def plans_on(monkeypatch):
    monkeypatch.setattr(CP, "ENABLED", True)        # the plan table (production: SSBOT_FORUM_TWO_PLAN=1) holds this package's units


def tick(tac, ws, fc):
    ws.stamp.frame = int(getattr(ws.stamp, "frame", 0) or 0) + 1
    return step(tac, ws, fc)


def start(xs, hx, frame=1000):
    tac, ws, fc = scene(xs=xs, hx=hx)
    ws.stamp.frame = frame
    tick(tac, ws, fc)
    return tac, ws, fc


def slam(tac, ws, fc, iid=7, elapsed=None, state="Slam Antic"):
    if elapsed is not None:
        next(e for e in ws.entities if e.id == iid).fsm = [("Control", state, elapsed)]
    change(fc, iid, family=G.CC_SLAM, state=state, committed=True)
    return tick(tac, ws, fc)


def top(ws, iid, y):
    e = next(e for e in ws.entities if e.id == iid)
    e.dmg_boxes[0].poly = [(x, 3. if yy == 3. else y) for x, yy in e.dmg_boxes[0].poly]


def hit_on(ws, iid):
    ws.events = [NS(kind=Ev.HIT_DEALT, data=NS(target_id=iid, attack="Nail", src="Slash"))]


# ---- plan 1.x: the far one's slam ----

def test_separated_slam_stays_outside_its_range_and_slashes_the_near_one_only_within_reach():
    tac, ws, fc = start((20., 30.), 40.)                  # 7 slams, 8 stands between her (40) and it
    out = slam(tac, ws, fc)
    sep = tac.last["clapper_sep_slam"]
    assert tac.last["clapper_winner"]["rule"] == "sep_slam" and out.target == 8 and sep["branch"] == "1.2.3"
    assert sep["edge"] == pytest.approx(20. + SEP.SLAM_EDGE_U) and not sep["inside"] and sep["face"] == 1
    assert out.stance_x == pytest.approx(20. + SEP.SLAM_EDGE_U + SEP.OUT_U)
    assert 7 in out.no_hit and 8 not in out.no_hit        # 8's body (29..31) within the side slash's reach of the stance
    assert 7 in out.blocked and 8 not in out.blocked
    tac, ws, fc = start((20., 28.), 40.)                  # 8's body 27..29: out of reach from outside the range: she waits
    out = slam(tac, ws, fc)
    assert tac.last["clapper_sep_slam"]["branch"] == "1.2.3" and {7, 8} <= out.no_hit


def test_n_reaching_out_past_the_edge_gets_down_slashes_then_the_way_into_the_middle_after_both_hammers():
    tac, ws, fc = start((20., 33.), 40.)                  # 8's body 32..34 crosses the edge 32.76
    out = slam(tac, ws, fc)
    assert tac.last["clapper_sep_slam"]["branch"] == "1.2.2" and out.target == 8
    assert out.stance_x == pytest.approx(33.01) and out.hit_kw[8][3] > 0 and out.hit_kw[8][:3] == (0., 0., 0.)
    assert 7 in out.no_hit
    change(fc, 7, state="Slam 2"); tick(tac, ws, fc)
    change(fc, 7, state="Slam Recover"); out = tick(tac, ws, fc)   # its first Recover frame: the colliders of Slam 2's end still count
    assert tac.last["clapper_sep_slam"]["phase"] == "slam"
    out = tick(tac, ws, fc)                                          # both hammer stages over: over 8 into the middle
    post = tac.last["clapper_sep_slam"]
    assert post["phase"] == "post" and tac.last["clapper_winner"]["rule"] == "sep_slam" and out.target == 8
    assert out.stance_x == pytest.approx(32. - SEP.FALL_U - .25)      # her box 1 u inside 8's inner edge
    assert 8 not in out.ground_hit | out.no_pogo | out.ground_first     # its side slash counts from the air
    assert 7 in out.no_hit and tac.last["clapper_scene"] == "separated slam 1.2.2 after: into the middle"
    hit_on(ws, 8); tick(tac, ws, fc)                                   # the hit ends it
    assert tac.last["clapper_sep_slam"] is None


def test_room_past_n_outside_the_range_takes_her_over_it_and_inside_she_side_slashes_it():
    tac, ws, fc = start((20., 36.), 45.)                  # 8's body 35..37, the edge 32.76: room 32.76 .. 34.5
    out = slam(tac, ws, fc)
    sep = tac.last["clapper_sep_slam"]
    assert sep["branch"] == "1.2.1" and sep["style"] == "stomp" and out.stance_x == pytest.approx(34.5) and out.target == 8
    hero_at(ws, 34.5)                                     # over it and down inside: still held (past its root), now side slashes
    out = tick(tac, ws, fc)
    sep = tac.last["clapper_sep_slam"]
    assert sep["branch"] == "1.2.1" and sep["style"] is None and out.target == 8 and 7 in out.no_hit
    assert out.stance_x == pytest.approx(34.5) and tac.last["clapper_winner"]["rule"] == "sep_slam"


def test_a_big_rune_across_her_way_puts_her_at_the_outer_one_of_its_edge_and_the_range_edge():
    tac, ws, fc = start((20., 50.), 40.)
    tac.rune_life = NS(live=lambda t: [NS(lo=25., hi=35.)])
    out = slam(tac, ws, fc)
    sep = tac.last["clapper_sep_slam"]
    assert sep["kind"] == "rune" and sep["branch"] == "1.1" and out.stance_x == pytest.approx(35.5) and 7 in out.no_hit


def test_inside_the_range_a_bounded_way_out_before_the_earliest_first_hammer():
    tac, ws, fc = start((20., 24.), 28.)
    out = slam(tac, ws, fc, elapsed=.1)                  # its antic began 6 frames before this tick
    wp = out.waypoint
    sep = tac.last["clapper_sep_slam"]
    assert sep["inside"] and wp is not None and wp.kind == "retreat" and wp.source == 7 and wp.family == "CC_SLAM"
    assert wp.x == pytest.approx(33.01) and wp.by_f == ws.stamp.frame - 6 + SEP.SLAM_FIRST_F - SEP.ESCAPE_LEAD_F
    assert sep["antic_f"] == ws.stamp.frame - 6


def test_no_place_outside_the_range_before_the_wall_leaves_the_existing_rules():
    tac, ws, fc = start((12., 6.), 2.)                    # the edge would lie past the left wall
    slam(tac, ws, fc)
    assert tac.last["clapper_sep_slam"] is None and tac.last["clapper_winner"]["rule"] != "sep_slam"


# ---- plan 2.x: the small rune ----

def cast(tac, ws, fc, iid, state="Spell Antic"):
    change(fc, iid, family=G.CC_CAST, state=state, committed=True)
    return tick(tac, ws, fc)


def test_small_rune_down_slashes_the_caster_when_nothing_stands_between():
    tac, ws, fc = start((20., 30.), 15.)
    out = cast(tac, ws, fc, 7)
    d = tac.last["clapper_rune_down"]
    assert tac.last["clapper_winner"]["rule"] == "rune_down" and d["case"] == "2.2 caster" and out.target == 7
    assert out.stance_x == pytest.approx(20.) and out.hit_kw[7][3] > 0 and out.hit_kw[7][:3] == (0., 0., 0.)


def test_small_rune_caster_behind_the_other_one_down_slashes_the_reachable_one_and_follows_a_crossing():
    tac, ws, fc = start((20., 30.), 15.)
    out = cast(tac, ws, fc, 8)                            # the caster is the far one
    assert tac.last["clapper_rune_down"]["case"] == "2.2 other" and out.target == 7 and 8 in out.blocked
    move(ws, fc, 7, 35.)                                  # the near one walks off through the caster: no state change, a pick now
    out = tick(tac, ws, fc)
    assert tac.last["clapper_rune_down"]["case"] == "2.2 caster" and out.target == 8 and out.stance_x == pytest.approx(30.)


def test_small_rune_double_with_a_standing_gap_still_aims_the_seam():
    # Sol seq 320: no gap condition on the double: 2.7 u between the near edges (a standing gap) is still within one blade
    from ssbot.combat.tactics.clapper_scene import geometry, standing_gap
    tac, ws, fc = start((20., 24.7), 15.)
    out = cast(tac, ws, fc, 8)
    d = tac.last["clapper_rune_down"]
    assert standing_gap(geometry(tac, ws, list(fc.subjects))) is True
    assert d["case"] == "2.2 both" and d["stance"] == pytest.approx(.5 * (21. + 23.7))
    assert out.hit_kw[out.target][3] > 0 and not ({7, 8} & out.no_hit)


def test_small_rune_across_a_big_rune_stands_at_its_edge_and_never_hits_the_caster_across_it():
    tac, ws, fc = start((20., 30.), 15.)
    tac.rune_life = NS(live=lambda t: [NS(lo=24., hi=28.)])
    out = cast(tac, ws, fc, 8)
    d = tac.last["clapper_rune_down"]
    assert d["case"] == "2.1 rune between" and out.stance_x == pytest.approx(23.5) and out.target == 7 and 8 in out.no_hit


def end_rune(tac, ws, fc, iid):
    change(fc, iid, state="Cast 2"); tick(tac, ws, fc)
    change(fc, iid, family=G.CC_IDLE, state="Idle", committed=False)
    return tick(tac, ws, fc)


@pytest.mark.parametrize("xs,tier", [((20., 23.), "seam"), ((20., 24.5), "seam"), ((20., 30.), "fall")])
def test_after_the_small_rune_two_tiers_by_the_gap(xs, tier):
    tac, ws, fc = start(xs, 15.)
    cast(tac, ws, fc, 7)
    out = end_rune(tac, ws, fc, 7)
    a = tac.last["clapper_rune_after"]
    assert tac.last["clapper_winner"]["rule"] == "rune_after" and a["tier"] == tier
    if tier == "seam":                                    # at most 2.5 u (exactly 2.5 too): the down slash at the middle of the two
        assert out.stance_x == pytest.approx(.5 * (xs[0] + 1. + xs[1] - 1.)) and out.hit_kw[out.target][3] > 0
    else:                                                 # 8 lies farther from its wall (30 vs 20): 1 u from its edge, a side slash in the air
        assert out.target == 8 and out.stance_x == pytest.approx(29. - SEP.FALL_U - .25)
        assert 8 not in out.ground_hit | out.no_pogo and 8 not in out.hit_kw
    hit_on(ws, out.target); tick(tac, ws, fc)
    assert tac.last["clapper_rune_after"] is None


# ---- #379: the stacked pair ----

def test_no_gap_return_takes_the_seam_double_when_level_else_the_ground_in_front_of_the_near_one():
    tac, ws, fc = start((20., 23.), 15.)                  # near edges 1 u apart: no standing gap
    out = near_attack(tac, ws, fc)
    assert tac.last["clapper_scene"] == "middle return: seam double" and out.stance_x == pytest.approx(21.5)
    assert out.hit_kw[out.target][3] > 0 and not ({7, 8} & out.no_hit)
    tac, ws, fc = start((20., 23.), 15.)
    top(ws, 8, 8.2)                                       # the far one's top 1.2 u higher: no double
    out = near_attack(tac, ws, fc)
    assert tac.last["clapper_scene"] == "middle return: no gap, ground in front of the near one"
    assert out.target == 7 and out.stance_x < 19. and 7 not in out.hit_kw


def test_tight_middle_takes_the_seam_double_or_the_ground_never_the_overhead_root():
    tac, ws, fc = start((20., 21.5), 20.75)
    out = tick(tac, ws, fc)
    assert tac.last["clapper_region"] == "tight" and tac.last["clapper_scene"] == "tight middle: seam double"
    assert out.stance_x == pytest.approx(20.75)
    tac, ws, fc = start((20., 21.5), 20.75)
    top(ws, 8, 8.2)
    out = tick(tac, ws, fc)
    assert tac.last["clapper_scene"] == "tight middle: ground in front of the near one" and out.target == 7 and out.stance_x < 19.


def test_the_chase_does_not_follow_a_focus_behind_the_other_one():
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy
    me = NS(two=None)
    assert ForumPlannerPolicy._chase_block(me, 0, NS(target=7, blocked=frozenset({7}), press_walker=None)) == "separated"
    assert ForumPlannerPolicy._chase_block(me, 0, NS(target=8, blocked=frozenset({7}), press_walker=None)) is None


# ---- plan 3.x: the cluster's outer variant ----

def test_outer_choice_lure_first_else_the_final_place_farther_from_its_wall():
    c = lambda name, ok, room=None: Candidate(name, ok, None if ok else "no", name if ok else None, 1.,
                                              () if room is None else (("final_room", room),))
    assert CP.outer_choice(c("lure", True), c("attack", True, 9.), c("vault", True, 12.)) == "lure"
    assert CP.outer_choice(c("lure", False), c("attack", True, 9.), c("vault", True, 12.)) == "vault"
    assert CP.outer_choice(c("lure", False), c("attack", True, 13.), c("vault", True, 12.)) == "attack"
    assert CP.outer_choice(c("lure", False), c("attack", False), c("vault", True, 2.)) == "vault"
    assert CP.outer_choice(c("lure", False), c("attack", False), None) is None


def test_the_outer_variant_plan_carries_the_vault_candidate_and_its_own_choice():
    from tests.test_l2_plan182 import body, plan_of, request
    from dataclasses import replace
    J = body(1, 19., "Jump Antic", "CC_JUMP_CAST", facing=1)
    W = body(2, 30.)
    q = replace(request("cluster", J, W, hx=33., side=1), outer=True)
    plan = plan_of(q)
    names = [c.name for c in plan.candidates]
    assert names == ["lure", "attack", "vault"] and plan.get("outer") is True
    if plan.status == "ok":
        assert plan.selected == CP.outer_choice(*plan.candidates) and plan.complete()
    q = replace(q, rune_across=True)
    v = plan_of(q).candidate("vault")
    assert not v.feasible and "3.4" in v.reason


# ---- the chain: the route ahead, the stacked follow-up ----

def test_route_meets_the_other_body_before_the_target_or_reaches_the_target_first():
    other = np.tile([24., 3., 26., 7.], (31, 1))
    target = np.tile([30., 3., 32., 7.], (31, 1))
    right = np.array([[20. + .2 * k, 4., 20.5 + .2 * k, 6.] for k in range(31)])
    k, cut = T.route_meets_other(right, 30, target, other)
    assert k is not None and cut is None and right[k][2] >= 24.
    over = right.copy(); over[:, 1] += 4.; over[:, 3] += 4.            # above its top: no meeting
    assert T.route_meets_other(over, 30, target, other) == (None, None)
    near = np.array([[28. + .2 * k, 4., 28.5 + .2 * k, 6.] for k in range(31)])
    assert T.route_meets_other(near, 30, target, other)[0] is None      # past the other one already: the target first


def test_a_jumping_body_falls_ballistically_to_the_floor_and_a_still_root_stays():
    from tests.test_bounce_follow183 import clapper
    e = clapper(7, 20., 1, state='Air')
    e['vel'] = [3., 0.]
    b0 = T.body_box(e)
    lifted = dict(e, colliders=[dict(c, verts_world=[v + (4. if i % 2 else 0.) for i, v in enumerate(c.get('verts_world') or ())])
                                for c in e.get('colliders') or ()])
    p = T.body_path(lifted, 60)
    assert p is not None and p[0][1] == pytest.approx(b0[1] + 4.)
    assert p[-1][1] == pytest.approx(T.ROUTE_FLOOR_Y) and p[-1][0] > p[0][0]           # down on the floor, carried forward
    idle = dict(clapper(7, 20., 1), vel=[3., 0.])
    q = T.body_path(idle, 10)
    assert np.allclose(q[-1], q[0])                                                     # a still-root state does not move


def test_small_rune_target_change_hands_an_unpressed_approach_back(monkeypatch):
    # plan 2.2 / design 3.3 (bout 47): the down slash's target is re-chosen every call; an approach with no pressed strike follows it
    from dataclasses import replace
    from tests.test_bounce_follow183 import Bout
    bout = Bout(monkeypatch, link='air', tail_done=True)
    bout.prefs = replace(bout.prefs, target=7, clapper_choice='rune_down')
    assert bout.tick() is None
    assert bout.notes('transfer_rune_target_handoff') and bout.notes('b2_recovery')
    bout = Bout(monkeypatch, link='air', tail_done=True)                       # outside the small rune's choice: kept as before
    bout.prefs = replace(bout.prefs, target=7, clapper_choice='keep')
    bout.tick()
    assert not bout.notes('transfer_rune_target_handoff')


def test_stacked_follow_up_hands_the_seam_double_to_the_rows_or_takes_the_ordinary_landing(monkeypatch):
    from tests.test_bounce_follow183 import Bout
    bout = Bout(monkeypatch, other=(7, 33.5, 1), link='air', tail_done=True)      # the bodies overlap: no standable gap
    assert bout.tick() is None
    st = bout.notes('transfer_follow_stacked')
    assert st and st[0]['choice'] == "seam double intent: the ordinary rows" and bout.notes('b2_recovery')
    monkeypatch.setattr(SEP, "DOUBLE_TOP_U", -1.)                               # never level: no double
    bout = Bout(monkeypatch, other=(7, 33.5, 1), link='air', tail_done=True)
    offer = bout.tick()
    st = bout.notes('transfer_follow_stacked')
    assert st and st[-1]['choice'] in ("left_landing", "right_landing", "no legal outer landing: the existing seam strike")
    if st[-1]['choice'] != "no legal outer landing: the existing seam strike":
        assert offer is not None and offer.draft.run.link == 'land'
