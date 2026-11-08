"""Task 182: event-driven L2 plans (generator, generic executor, channel, foreground adapter, hero gates)."""
import math
import time
from dataclasses import replace
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import jump_behind as JB
from ssbot.combat.tactics import clapper_plans as CP, clapper_priority as PR, clapper_tactics as CT, gauntlet as G
from ssbot.combat.tactics.l2_plan import BLOCKED, DONE, INVALID, Candidate, Phase, Plan, PlanExecutor, Range
from ssbot.combat.tactics.l2_plan_worker import InlineChannel, PlanChannel
from ssbot.core.forum import FLOOR_Y
from ssbot.core.worldstate import E
from ssbot.knowledge import kinematics as kin
from ssbot.knowledge.kinematics import HeroParams, Terrain2D
from ssbot.train.forum_planner_policy import CREST_PARAMS
from tests.test_clapper_priority import change, manual, scene   # noqa: F401  (autouse manual-B fixture)

PARAMS = kin.hero2(HeroParams.load(CREST_PARAMS["Wanderer"]))     # the crest of the w13 fights
TERRAIN = Terrain2D(np.array([[FLOOR_Y, 0., 80.]]), np.zeros((0, 3)), np.zeros((0, 4)))
DT = float(PARAMS.frame_time)
BODY_IN = 2.2515621185302734


def hero_state(x, y=None, vx=0., ground=True, mode=None):
    S = kin.initial_state(PARAMS, x, (FLOOR_Y + PARAMS.foot) if y is None else y, vx=vx, ground=ground,
                          **({} if mode is None else {"mode": mode}))
    return np.asarray(S, np.float64)


def hand_of(x=35., t=0., **kw):
    S = hero_state(x, **kw)
    m = CP.Roller(S, np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, TERRAIN)
    return S, CP.hand_back(m, t, x)


def body(iid, x, state="Idle", family=None, vx=0., front=BODY_IN, back=1.34, facing=-1):
    # facing -1: the front to its left
    a, b = (x - front, x + back) if facing < 0 else (x - back, x + front)
    return CP.Body(iid, x, vx, a, b, state, family)


def request(scene_="middle", J=None, W=None, hx=33., t=0., antic_at=0., stage="aim", side=0, generation=1, land=None, air_at=None,
            land_vx=None, S0=None, hand=None):
    J = J if J is not None else body(1, 19., "Jump Antic", "CC_JUMP", facing=1)
    W = W if W is not None else body(2, 39.)
    if hand is None:
        S0, hand = hand_of(hx, t)
    return CP.Request(scene_, stage, (J.iid, 0.), generation, t, J, W, side, antic_at, air_at, land, land_vx, None, hand, .25, .25, 14.01,
                      48.99, 2., .25, 4., 7.76, S0, np.zeros(1, np.int64), kin.HoldState.idle(1))


def plan_of(q):
    return CP.generate(q, PARAMS, TERRAIN)


def step_(ex, t, events, values, inst):
    """The executor with the same facts for whichever plan it asks about."""
    return PlanExecutor.step(ex, t, events, lambda plan: values, lambda plan: inst)


def cand(plan, name):
    return plan.candidate(name)


# ---- the generator: the design's arithmetic and options ----

def test_the_guide_point_is_the_nearest_sufficient_one_not_a_fixed_stance():
    plan = plan_of(request())                 # 20 u apart, a normal jump, past its sufficient point by a run's reach
    stay = cand(plan, "stay")
    assert plan.selected == "stay" and stay.feasible
    assert stay.get("hmax") == pytest.approx(19. + 13.175, abs=.01)      # the design's 13.18 u
    assert stay.get("guide") == pytest.approx(19. + 13.175 - CP.GUIDE_MARGIN_U, abs=.01)
    assert stay.get("guide") - 19. > 7.                                   # not the old 5.5 / 7 u stance
    assert plan.phase("aim_wait").at[1] == "aim_guide" and stay.start == "aim_wait"


def test_the_cast_guide_uses_the_whole_rune_coverage():
    J = body(1, 19., "Cast Slam Antic", "CC_JUMP_CAST", facing=1)
    plan = plan_of(request(J=J))
    stay = cand(plan, "stay")
    assert CP.RUNE_REACH_U == pytest.approx(6.75 + 7.187)
    assert stay.get("reach") == pytest.approx(13.937)
    assert stay.get("hmax") == pytest.approx(19. + 6.43, abs=.01)        # the design's 6.43 u
    assert plan.get("reach") == pytest.approx(13.937)


def test_no_guide_when_the_stance_already_suffices():
    plan = plan_of(request(W=body(2, 44.), hx=40.))        # 25 u: the saturated jump cannot reach the walker's side
    stay = cand(plan, "stay")
    assert plan.selected == "stay" and stay.get("guide") is None and stay.start == "aim_attack"
    assert plan.phase("aim_wait") is None
    # 25 u with the whole rune needs a guide again, and 30 u does not (the design's table)
    J = body(1, 19., "Cast Slam Antic", "CC_JUMP_CAST", facing=1)
    assert cand(plan_of(request(J=J, W=body(2, 44.), hx=40.)), "stay").get("guide") is not None
    assert cand(plan_of(request(J=replace(J, x=16., a=14.66, b=18.25), W=body(2, 46.), hx=42.)), "stay").get("guide") is None


def test_the_departure_waits_until_its_absolute_deadline_and_does_not_drift():
    a = plan_of(request())
    depart = a.phase("aim_wait").at[0]
    stay = cand(a, "stay")
    travel = stay.get("travel_s")
    assert stay.get("depart_t") == pytest.approx(.48 - CP.RESERVE_S - travel, abs=3 * DT)
    # the stage starts at the latest departure, its keys applying two frames on: the bounded approach sends what this counted on
    assert depart == pytest.approx(stay.get("depart_t") - 2 * DT, abs=1e-9)
    assert a.get("latest_depart") == stay.get("depart_t")
    assert depart > stay.get("hand_t") - 2 * DT and depart > .05                # time to attack before it
    # the same geometry asked again later: the same absolute deadline, whatever the snapshot's time
    for t in (.02, .05, .1):
        S0, hand = hand_of(33., t)
        b = plan_of(request(t=t, S0=S0, hand=hand))
        assert b.phase("aim_wait").at[0] == pytest.approx(depart, abs=2 * DT)
        assert b.get("lock_t") == a.get("lock_t")


def test_too_late_for_the_guide_is_not_used_and_the_other_routes_are_chosen():
    J = body(1, 19., "Cast Slam Antic", "CC_JUMP_CAST", facing=1)
    S0, hand = hand_of(35., .80)
    plan = plan_of(request(J=J, t=.80, S0=S0, hand=hand))       # the cast's lock at .88 s: 10 u away cannot be made
    stay = cand(plan, "stay")
    assert not stay.feasible and "aim reserve" in stay.reason
    assert plan.selected in ("under", "over") and plan.selected in plan.get("prepared")


def test_a_late_hand_back_changes_only_the_time_not_the_admission():
    # the same place with a later hand-back: the guide goes when it is too late, by the time and nothing else
    S0, hand = hand_of(33., 0.)
    late = replace(hand, t=.40, index=hand.index + 24)
    plan = plan_of(request(S0=S0, hand=late))
    assert "aim reserve" in cand(plan, "stay").reason
    ok = plan_of(request(S0=S0, hand=replace(hand, t=.05, index=hand.index + 3)))
    assert cand(ok, "stay").feasible


def test_the_real_2639_layout_has_no_guide_and_keeps_the_other_routes():
    J = CP.Body(1, 18.9634, 0., 17.62, 21.01, "Cast Slam Antic", "CC_JUMP_CAST")
    W = CP.Body(2, 29.39, 0., 29.39 - BODY_IN, 30.73, "Idle", None)
    plan = plan_of(request(J=J, W=W, hx=25.))
    assert not cand(plan, "stay").feasible and "walker" in cand(plan, "stay").reason
    assert plan.selected in ("under", "over")


def test_a_walker_closing_is_counted_in_the_aim_and_not_frozen():
    still = plan_of(request())
    closing = plan_of(request(W=body(2, 39., "Walk", vx=-8.)))
    assert cand(closing, "stay").get("walker_x") == pytest.approx(39. - 8. * .48)
    assert (cand(closing, "stay").feasible is False or
            cand(closing, "stay").get("hmax") < cand(still, "stay").get("hmax"))


def test_stay_carries_the_prepared_fallback_with_its_wall_rule():
    plan = plan_of(request())
    assert plan.selected == "stay"
    prepared = plan.get("prepared")
    assert set(prepared) <= {"under", "over"} and prepared
    for name in prepared:
        c = cand(plan, name)
        assert c.feasible and c.get("wall_room") is not None and c.get("end_x") is not None
    # after the take-off every route is written before the lock, no search later
    for name in ("return", "under", "over_head", "over_wait", "over_back"):
        assert plan.phase(name) is not None and plan.phase(name).replaceable is False


def test_under_counts_the_slanted_descent_not_only_the_landing():
    # A long flat jump: the spot keeps its back + the sweep at 12 u/s; a short one keeps the standing back_u
    long_ = plan_of(request(W=body(2, 44.), hx=40.))
    under = cand(long_, "under")
    assert under.get("need_back") >= CP.BODY_BACK_U + 12. * CP.SWEEP_S + .5 - 1e-9
    assert (under.get("landing") - under.get("end_x")) >= under.get("need_back")


def test_the_way_under_is_the_bounded_approach_against_its_descent():
    # the usual aim: its landing 5 u short of her, the place 3.5 u behind that: the dash gets there before its body comes down
    usual = plan_of(request(J=body(1, 30., "Jump Antic", "CC_JUMP", facing=1), W=body(2, 38.), hx=34.))
    u = cand(usual, "under")
    assert u.feasible and abs(u.get("end_x") - u.get("aim_x")) >= 8. and u.get("arrive_t") <= u.get("by_t") - .05
    # too far for the time: not offered, the reason says why
    J = body(1, 25., "Air", "CC_JUMP", facing=1)
    far = plan_of(request(J=J, W=body(2, 47.), hx=44., stage="flight", antic_at=None, land=30., land_vx=5.45, air_at=0.))
    assert not cand(far, "under").feasible and "comes down" in cand(far, "under").reason
    # an observed landing right in front of her (a flight seen late): the way behind it is short, the run does
    short = plan_of(request(J=J, W=body(2, 38.), hx=31., stage="flight", antic_at=None, land=30., land_vx=5.45, air_at=0.))
    u = cand(short, "under")
    assert u.feasible and u.get("route_s") <= CP.DESCENT_S

def test_the_side_approach_passes_under_only_a_source_in_the_air_above_her_head(monkeypatch):
    from ssbot.combat.knife_chain_air_native import _passes_under
    air = {"fsms": [{"name": "Control", "state": "Air", "t": .1}]}
    state = {"hero": {"box": [0., 3., 1., 5.]}}
    high, low = np.array([0., 9., 2., 12.]), np.array([0., 4., 2., 8.])
    monkeypatch.setattr(CP, "ENABLED", True)
    assert _passes_under(air, high, state)
    assert not _passes_under(air, low, state)                            # it has come down to her head
    assert not _passes_under({"fsms": [{"name": "Control", "state": "Jump Antic", "t": .1}]}, high, state)
    assert not _passes_under(air, high, {"hero": {}})                     # unknown: blocked as before
    monkeypatch.setattr(CP, "ENABLED", False)
    assert not _passes_under(air, high, state)                            # flag off: the old rule


def test_over_followups_are_written_by_the_move():
    plan = plan_of(request(W=body(2, 28.), hx=24.))
    over = cand(plan, "over")
    assert over.feasible and over.get("follow") == "back"
    assert plan.phase("over_head").after("bounced") == "over_wait"
    assert plan.phase("over_head").after("hazard_over") == "over_back"
    J = body(1, 19., "Cast Slam Antic", "CC_JUMP_CAST", facing=1)
    near = plan_of(request(J=J, W=body(2, 28.), hx=24.))
    assert cand(near, "over").get("follow") == "stay"           # the far side still inside the rune: over its head longer
    assert near.phase("over_head").after("bounced") == "over_stay"
    far = plan_of(request(J=J, W=body(2, 36.), hx=32.))
    if cand(far, "over").feasible:
        assert cand(far, "over").get("follow") in ("out", "stay")


def test_no_option_is_an_explicit_no_plan():
    # the walker in an attack (no stay), a wall behind the jumper (no under), the walker's state (no over)
    J = body(1, 16., "Jump Antic", "CC_JUMP", facing=1)
    W = body(2, 24., "Slam Antic", "CC_SLAM")
    plan = plan_of(request(J=J, W=W, hx=21.))
    assert plan.status == "none" and plan.selected is None and plan.phases == ()
    assert "stay:" in plan.reason and "under:" in plan.reason and "over:" in plan.reason


def test_the_flight_stage_uses_the_observed_landing():
    J = body(1, 25., "Air", "CC_JUMP", facing=1)
    plan = plan_of(request(J=J, W=body(2, 44.), hx=40., stage="flight", antic_at=None, land=30., land_vx=5.45, air_at=0.))
    assert plan.selected == "stay" and cand(plan, "stay").start == "return" and plan.aim_deadline is None
    plan = plan_of(request(J=J, W=body(2, 35.), hx=33., stage="flight", antic_at=None, land=30., land_vx=5.45, air_at=0.))
    assert not cand(plan, "stay").feasible and plan.selected in ("under", "over")


# ---- the cluster's two plans ----

def cluster_request(J=None, G_=None, hx=26., antic_at=0., t=0.):
    J = J if J is not None else body(1, 36., "Jump Antic", "CC_JUMP")
    G_ = G_ if G_ is not None else body(2, 37.)
    return request("cluster", J=J, W=G_, hx=hx, side=-1, antic_at=antic_at, t=t)


def test_cluster_lure_when_its_whole_space_holds():
    plan = plan_of(cluster_request())
    lure, attack = cand(plan, "lure"), cand(plan, "attack")
    assert lure.feasible and plan.selected is None
    assert lure.get("return_x") == pytest.approx(37. - 4.)
    assert lure.get("h_need") is not None and lure.get("return_arrive_t") <= lure.get("by_t")
    assert attack.feasible
    assert plan.phase("lure_return").attack == "side" and plan.phase("lure_return").stance == ("front", 2)
    # past the landing the jumper is the focus until it is down, then the slash on the standing one
    assert plan.phase("lure_return").after("past_landing") == "lure_behind"
    assert plan.phase("lure_behind").target == 1 and plan.phase("lure_behind").after("hazard_over") == "lure_slash"
    assert plan.phase("lure_slash").target == 2 and plan.phase("lure_slash").attack == "side"
    assert plan.phase("attack_retreat").suppress_hits is True and plan.phase("attack_back_other").attack == "side"


def test_coming_back_from_the_retreat_the_plan_has_both_bodies_and_the_landing_decides():
    plan = plan_of(cluster_request())
    assert cand(plan, "attack").feasible
    retreat = plan.phase("attack_retreat")
    assert dict(retreat.on) == {"back_jumper": "attack_back_jumper", "back_other": "attack_back_other", "stance_lost": BLOCKED}
    assert plan.phase("attack_back_jumper").target == 1 and plan.phase("attack_back_jumper").no_hit == ()
    assert plan.phase("attack_back_other").target == 2 and plan.phase("attack_back_other").no_hit == (1,)


def test_cluster_without_room_for_the_lure_falls_to_attack_and_a_closing_walker_counts():
    # near the left wall: the landing it needs asks her past the wall
    J, G_ = body(1, 24., "Jump Antic", "CC_JUMP"), body(2, 25.)
    plan = plan_of(cluster_request(J=J, G_=G_, hx=19.))
    assert not cand(plan, "lure").feasible and "space" in cand(plan, "lure").reason
    assert cand(plan, "attack").feasible and plan.status == "ok"
    # the walker walking toward her needs a farther landing
    still = plan_of(cluster_request())
    walking = plan_of(cluster_request(G_=body(2, 37., "Walk", vx=-8.)))
    assert cand(walking, "lure").get("return_x") < cand(still, "lure").get("return_x")


def test_cluster_cast_keeps_clear_of_the_whole_rune_and_both_failing_is_explicit():
    J, G_ = body(1, 24., "Cast Slam Antic", "CC_JUMP_CAST"), body(2, 25.)
    plan = plan_of(cluster_request(J=J, G_=G_, hx=19.))
    assert plan.status == "none" and "lure:" in plan.reason and "attack:" in plan.reason
    assert "coverage" in plan.reason


# ---- parent scenes: exclusions ----

def geo_of(xs, hx, spans=None):
    low = NS(iid=1, pos=(xs[0], 7.)); high = NS(iid=2, pos=(xs[1], 7.))
    spans = spans or {1: (xs[0] - 2., xs[0] + 2.), 2: (xs[1] - 2., xs[1] + 2.)}
    (low, high) = sorted((low, high), key=lambda s: s.pos[0])
    return dict(bodies=spans, left=.25, right=.25, xa=14.01, xb=48.99, low=low, high=high, lo=0., hi=0., region=None)


def subj_(iid, x, state="Idle", family=None):
    return NS(iid=iid, pos=(x, 7.), state=state, family=family)


def test_only_a_clear_middle_with_one_jumper_is_the_three_branch_scene():
    J, W = subj_(1, 20., "Jump Antic", "CC_JUMP"), subj_(2, 34.)
    geo = geo_of((20., 34.), 27.)
    assert CP.parent_scene([J, W], geo, 27.)[0] == "middle"
    # outside two apart: neither (Root: 19 / 39, a 15.5 u gap, the hero at 45: no cluster)
    assert CP.parent_scene([J, W], geo, 15.) is None and CP.parent_scene([J, W], geo, 40.) is None
    apart = geo_of((19., 39.), 45.)
    assert CP.parent_scene([subj_(1, 19., "Jump Antic", "CC_JUMP"), subj_(2, 39.)], apart, 45.) is None
    # outside two with no standing gap between them: the cluster, never middle
    together = geo_of((28., 30.), 15., {1: (26., 30.), 2: (27., 32.)})
    pair = [subj_(1, 28., "Jump Antic", "CC_JUMP"), subj_(2, 30.)]
    assert CP.parent_scene(pair, together, 15.)[0] == "cluster" and CP.parent_scene(pair, together, 40.)[0] == "cluster"
    # stacked bodies with the roots bracketing her: neither
    stacked = geo_of((26., 28.), 27., {1: (24., 30.), 2: (25., 31.)})
    assert CP.parent_scene([subj_(1, 26., "Jump Antic", "CC_JUMP"), subj_(2, 28.)], stacked, 27.) is None
    # the bodies closed although the roots bracket her
    closed = geo_of((24., 29.), 26.5, {1: (22., 26.4), 2: (26.6, 31.)})
    assert CP.parent_scene([subj_(1, 24., "Jump Antic", "CC_JUMP"), subj_(2, 29.)], closed, 26.5) is None
    # both jumping
    assert CP.parent_scene([J, subj_(2, 34., "Jump Antic", "CC_JUMP")], geo, 27.) is None
    # no jump
    assert CP.parent_scene([subj_(1, 20.), W], geo, 27.) is None
    # the jump seen only after its landing is no new plan
    assert CP.parent_scene([subj_(1, 20., "Slam 2", "CC_JUMP"), W], geo, 27.) is None


# ---- her hand-back and her state: the key owner, no free start ----

def owned_request(hx=33., keys=(0,) * 10, known=True, **kw):
    """The same request with a key owner past the in-flight prefix (the policy adds its known keys to the committed prefix)."""
    S0, _ = hand_of(hx, 0.)
    prefix = np.array((0,) + tuple(keys), np.int64)
    m = CP.Roller(S0, prefix, kin.HoldState.idle(1), PARAMS, TERRAIN)
    hand = CP.hand_back(m, 0., hx, known)
    return replace(request(hx=hx, S0=S0, hand=hand, **kw), prefix=prefix), hand


def test_a_key_owner_past_the_physical_hand_back_moves_it_and_its_deadline_reads_that():
    # physically free at f + 2 (M_NORMAL), but the source tail owner keeps the keys for 12 more frames: Sol seq 255 A's counterexample
    free_q, free = owned_request(keys=())
    owned_q, owned = owned_request(keys=(0,) * 12)
    assert owned.known and owned.t == pytest.approx(free.t + 12 * DT, abs=1e-9) and owned.index == free.index + 12
    # a guide she reaches from the free hand-back and no longer from the owner's release: the free roll would have called it feasible
    for hx in np.arange(30., 37., .25):
        fq, _ = owned_request(hx=float(hx), keys=())
        oq, _ = owned_request(hx=float(hx), keys=(0,) * 12)
        a, b = cand(plan_of(fq), "stay"), cand(plan_of(oq), "stay")
        if a.feasible and a.get("guide") is not None and not b.feasible:
            assert "reserve" in b.reason, b.reason
            return
    pytest.fail("no layout where only the owner's release misses the guide")

def test_the_native_owner_says_what_it_holds_of_her_keys(monkeypatch):
    from ssbot.combat.knife_chain_air_native import NativeManualAirChain as N, transfer, waypoint
    state = dict(f=100)
    def owner(run=None, commitment=None, recovery=None, wall=None, goal=None):
        return NS(runner=NS(run=run), commitment=commitment, recovery=recovery, _wall_pressure=wall, _transfer_goal=goal,
                  own_bounce_released=lambda st: False)
    assert N.key_commitment(owner(), state) is None
    assert N.key_commitment(owner(commitment={}), state) == ("b2 commitment", False, ())
    assert N.key_commitment(owner(recovery={}), state) == ("b2 recovery", False, ())
    # an approach, and the plans' own Run: handed back at their next step when L2 moves on
    approach = NS(chain=transfer.PROGRAM, link="walk", v={"_approach_only": True}, lid="rune_transfer.walk")
    assert N.key_commitment(owner(run=approach), state) is None
    assert N.key_commitment(owner(run=NS(chain=waypoint.PROGRAM, link="go", v={}, lid="waypoint.go")), state) is None
    # a strike: its release cannot be told
    strike = NS(chain=transfer.PROGRAM, link="strike", v={}, lid="rune_transfer.strike")
    assert N.key_commitment(owner(run=strike), state) == ("rune_transfer.strike", False, ())
    # the source tail: its own admission's keys through its predicted end; no prediction: unknown
    tail = NS(chain=transfer.PROGRAM, link="bounce_tail", v={"source_tail_mask": 0}, lid="rune_transfer.bounce_tail")
    monkeypatch.setattr(transfer, "predicted_tail_end", lambda s, g: 111)
    assert N.key_commitment(owner(run=tail, goal=object()), state) == ("rune_transfer.bounce_tail", True, (0,) * 10)
    monkeypatch.setattr(transfer, "predicted_tail_end", lambda s, g: None)
    assert N.key_commitment(owner(run=tail, goal=object()), state) == ("rune_transfer.bounce_tail", False, ())


def test_an_owned_follow_up_route_holds_her_keys_through_its_modelled_landing(monkeypatch):
    # Task 182 seq 269 (#339 live 3475-3522): the bounce follow-up's owned middle route, chosen at 3474 to land at 3522, landed
    # there; its release is that landing, not an owner whose release cannot be told (all three branches were 'hand-back unknown'
    # through the jump cast's aim). Seq 270: the chain sees the landing on its own tick and sends one key past it (live 3521 ->
    # 3523 by rune_transfer.middle, 3522 -> 3524 by the planner), so the keys run through land_f + 1 with the route's own tail
    # key; a landing already due inside the in-flight prefix while she is in the air is no release yet (unknown)
    from ssbot.combat.knife_chain_air_native import NativeManualAirChain as N, transfer
    from ssbot.combat.knife_chain_format import MASK_NAMES as B
    R, L = B["R"], B["L"]
    state = dict(f=100)

    def owner(run, **kw):
        o = N.__new__(N)
        o.__dict__.update(dict(runner=NS(run=run), commitment=None, recovery=None, _wall_pressure=None, _transfer_goal=object(),
                               own_bounce_released=lambda st: False), **kw)
        return o

    route = {"kind": "middle", "recipe": "hold", "dir": R, "F0": 101, "masks": [R] * 6 + [0] * 4, "release_F": 107, "land_f": 113}
    middle = NS(chain=transfer.PROGRAM, link="middle", lid="rune_transfer.middle", v={"follow": route})
    # in the air, frames f + 2 .. land_f + 1 = 102 .. 114: the row from its own index 1 (R x 5, none x 4), then the middle's
    # tail (none); without the ground flag the same (a landing past the prefix)
    assert N.key_commitment(owner(middle), state, ground=False) == ("rune_transfer.middle", True, (R,) * 5 + (0,) * 8)
    assert N.key_commitment(owner(middle), state) == N.key_commitment(owner(middle), state, ground=False)
    # a landing route whose row ends at its landing: land_f + 1 is its direction key (what the last re-anchor sends)
    side = {"kind": "left_landing", "dir": L, "F0": np.int64(100), "masks": [L] * 13, "land_f": np.int64(112)}
    land = NS(chain=transfer.PROGRAM, link="land", lid="rune_transfer.land", v={"follow": side})
    assert N.key_commitment(owner(land), state, ground=False) == ("rune_transfer.land", True, (L,) * 12)
    # a modelled landing already inside the in-flight prefix, or past, while she is still in the air: not a release
    for due in (101, 99):
        soon = NS(chain=transfer.PROGRAM, link="middle", lid="rune_transfer.middle", v={"follow": {**route, "land_f": due}})
        assert N.key_commitment(owner(soon), state, ground=False) == ("rune_transfer.middle", False, ())
        assert N.key_commitment(owner(soon), state) == ("rune_transfer.middle", False, ())
    # on the ground: the chain's own tick releases a landing it accepts (any ground for a left / right landing; the middle
    # only between the two bodies, else its recovery holds her), whatever land_f says
    assert N.key_commitment(owner(land), state, ground=True) == ("rune_transfer.land", True, ())
    for inside in (True, False):
        monkeypatch.setattr(N, "_follow_landing_inside", staticmethod(lambda st, run, ok=inside: (ok, None, None)))
        assert N.key_commitment(owner(middle), state, ground=True) == ("rune_transfer.middle", inside, ())
    monkeypatch.undo()
    # no owned route: a seam positioning / strike tick, a follow-up link without its route or without its modelled landing
    for run in (NS(chain=transfer.PROGRAM, link="air", lid="rune_transfer.air", v={"follow": route}),
                NS(chain=transfer.PROGRAM, link="strike", lid="rune_transfer.strike", v={"follow": route}),
                NS(chain=transfer.PROGRAM, link="middle", lid="rune_transfer.middle", v={}),
                NS(chain=transfer.PROGRAM, link="middle", lid="rune_transfer.middle", v={"follow": {**route, "land_f": None}})):
        for ground in (False, True):
            assert N.key_commitment(owner(run), state, ground=ground) == (run.lid, False, ())
    # the owner's own holds come first, route or not
    assert N.key_commitment(owner(middle, recovery={}), state, ground=True) == ("b2 recovery", False, ())
    assert N.key_commitment(owner(middle, _wall_pressure={}), state, ground=True) == ("b2 wall pressure", False, ())
    assert N.key_commitment(owner(middle, own_bounce_released=lambda st: True), state, ground=False) is None
    # what the plans read from it: a known hand-back after those keys (unknown made every branch 'hand-back unknown')
    keys = N.key_commitment(owner(middle), state, ground=False)[2]
    _, free = owned_request(keys=())
    q, held = owned_request(keys=keys)
    assert held.known and held.index == free.index + len(keys)
    _, unknown = owned_request(keys=(), known=False)
    assert not unknown.known and plan_of(replace(q, hand=unknown)).status == "none"


def test_an_owner_whose_release_cannot_be_told_makes_no_route_and_no_free_hero():
    q, hand = owned_request(keys=(), known=False)
    assert not hand.known
    plan = plan_of(q)
    assert plan.status == "none"
    for name in ("stay", "under", "over"):
        assert not cand(plan, name).feasible and "hand-back unknown" in cand(plan, name).reason
    c = plan_of(replace(cluster_request(), hand=hand))
    assert c.status == "none" and all("hand-back unknown" in x.reason for x in c.candidates)


def test_the_request_comes_again_when_her_hand_back_becomes_known(monkeypatch):
    tac, ws, fc = planned(monkeypatch)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    r = tac.plan_runner
    S = hero_state(35.)
    tac.plan_input = CP.HeroInput(S, np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, TERRAIN, commit=("slam", False, ()))
    go_(tac, ws, fc); go_(tac, ws, fc)
    assert r.hand is not None and not r.hand.known
    assert r.exec.plan is None and r.exec.status == "blocked" and "unknown" in r.exec.reason
    n = r.requests
    set_hero(tac, 35.)
    go_(tac, ws, fc)
    assert r.requests == n + 1 and any(x.get("why", "").startswith("her hand-back is known") for x in plan_notes(tac))
    go_(tac, ws, fc)
    assert r.exec.plan is not None


def test_the_routes_roll_on_from_her_state_with_no_free_landing_or_dash():
    # a dash on a long cooldown: the way under at a run does not make it, where the ready dash does
    S0 = hero_state(34.)
    m = CP.Roller(S0, np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, TERRAIN)
    J = body(1, 30., "Jump Antic", "CC_JUMP", facing=1)
    ready = request(J=J, W=body(2, 38.), hx=34., S0=S0, hand=CP.hand_back(m, 0., 34.))
    assert cand(plan_of(ready), "under").feasible
    S1 = S0.copy()
    S1[kin.DASH_CD] = 3.
    m = CP.Roller(S1, np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, TERRAIN)
    tired = request(J=J, W=body(2, 38.), hx=34., S0=S1, hand=CP.hand_back(m, 0., 34.))
    u = cand(plan_of(tired), "under")
    assert not u.feasible and "comes down" in u.reason
    # seen in flight, she high in the air with her air moves spent: she does not start from the floor with a ready dash
    y = FLOOR_Y + PARAMS.foot + 6.
    flight = dict(J=body(1, 30., "Air", "CC_JUMP", facing=1), W=body(2, 38.), hx=34., stage="flight", antic_at=None, land=29.,
                  land_vx=5.45, air_at=0.)
    S0 = hero_state(34.)
    m = CP.Roller(S0, np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, TERRAIN)
    floor = cand(plan_of(request(S0=S0, hand=CP.hand_back(m, 0., 34.), **flight)), "under")
    S2 = np.asarray(kin.initial_state(PARAMS, 34., y, ground=False), np.float64)
    S2[kin.AIRDASHED] = 1.
    S2[kin.DASH_CD] = 3.
    m = CP.Roller(S2, np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, TERRAIN)
    high = cand(plan_of(request(S0=S2, hand=CP.hand_back(m, 0., 34.), **flight)), "under")
    assert floor.feasible and (not high.feasible or high.get("route_s") > floor.get("route_s"))


def test_a_leg_rolls_on_from_where_the_aim_keys_left_her():
    # not from a free start: the guide's keys are in the leg, so the way on from a guide is the way from the guide
    S0, hand = hand_of(33., 0.)
    q = request(hx=33., S0=S0, hand=hand)
    c = CP._Middle(q, CP.Roller(S0, np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, TERRAIN))
    assert c.start_x(25.) < 32.                     # the aim's keys moved her
    here = c.leg(None, 33.)
    there = c.leg(25., 33.)
    assert here is not None and there is not None
    assert here[2] < .1
    assert there[2] > .2


# ---- the executor: generic and small ----

def mini_plan(inst=(1, 0.), gen=1, until=10., selected="a", support=(), scene_="s", replaceable=True):
    phases = (Phase("first", target=5, on=(("go", "second"), ("bad", INVALID)), at=None, replaceable=replaceable),
              Phase("second", target=6, on=(("end", DONE), ("stuck", BLOCKED)), replaceable=False))
    return Plan(scene_, inst, gen, 0., None, until, phases=phases, candidates=(Candidate("a", True, None, "first"),), selected=selected,
                support=support)


def test_the_executor_adopts_advances_and_completes_once():
    ex = PlanExecutor()
    assert ex.offer(mini_plan(), 1., (1, 0.), {})[0] == "adopted"
    assert ex.phase.name == "first" and ex.status == "waiting"
    assert step_(ex, 1.1, lambda p: [], {}, (1, 0.)).name == "first"
    assert step_(ex, 1.2, lambda p: ["go"], {}, (1, 0.)).name == "second"
    assert ex.handled((1, 0.), "go")
    assert step_(ex, 1.3, lambda p: ["end"], {}, (1, 0.)) is None
    assert ex.status == "complete" and ex.plan is None


def test_a_result_is_checked_before_it_can_be_used():
    ex = PlanExecutor()
    assert ex.offer(mini_plan(inst=(1, 5.)), 1., (1, 0.), {}) == ("rejected", "instance changed")
    assert ex.offer(mini_plan(until=.5), 1., (1, 0.), {}) == ("rejected", "expired")
    assert ex.offer(mini_plan(support=(Range("w", 0., 1.),)), 1., (1, 0.), {"w": 3.})[0] == "rejected"
    assert ex.offer(mini_plan(support=(Range("w", 0., 1.),)), 1., (1, 0.), {})[0] == "rejected"     # unknown is no support
    assert ex.offer(mini_plan(gen=3), 1., (1, 0.), {})[0] == "adopted"
    # an older generation arriving late never overwrites the newer one
    assert ex.offer(mini_plan(gen=2), 1.1, (1, 0.), {}) == ("rejected", "out of order")
    assert ex.plan.generation == 3
    broken = Plan("s", (1, 0.), 4, 0., None, 10., phases=(Phase("first", on=(("go", "nowhere"),)),),
                  candidates=(Candidate("a", True, None, "first"),), selected="a")
    assert ex.offer(broken, 1.2, (1, 0.), {}) == ("rejected", "incomplete plan")


def test_past_the_boundary_a_new_plan_waits_and_invalid_ends_at_once():
    ex = PlanExecutor()
    ex.offer(mini_plan(support=(Range("w", 0., 1.),)), 1., (1, 0.), {"w": .5})
    step_(ex, 1.1, lambda p: ["go"], {"w": .5}, (1, 0.))
    assert ex.phase.name == "second"
    # a route past the boundary is not replaced: support is no longer read, the newer plan waits
    newer = mini_plan(gen=2)
    assert ex.offer(newer, 1.2, (1, 0.), {"w": 5.})[0] == "pending"
    assert step_(ex, 1.3, lambda p: [], {"w": 5.}, (1, 0.)).name == "second"
    assert ex.pending is newer
    assert step_(ex, 1.4, lambda p: ["stuck"], {"w": 5.}, (1, 0.)) is None and ex.status == "blocked"
    # the waiting plan is taken at the boundary, in the next step, after its checks again
    assert step_(ex, 1.5, lambda p: [], {"w": 5.}, (1, 0.)).name == "first" and ex.plan.generation == 2
    # support gone in a replaceable stage: invalid at once, no waiting for a worker
    ex2 = PlanExecutor()
    ex2.offer(mini_plan(support=(Range("w", 0., 1.),)), 1., (1, 0.), {"w": .5})
    assert step_(ex2, 1.1, lambda p: [], {"w": 3.}, (1, 0.)) is None and ex2.status == "invalid"


def test_fixed_times_and_instance_end():
    ex = PlanExecutor()
    timed = Plan("s", (1, 0.), 1, 0., None, 10., phases=(Phase("wait", at=(2., "go")), Phase("go", on=())),
                 candidates=(Candidate("a", True, None, "wait"),), selected="a")
    ex.offer(timed, 1., (1, 0.), {})
    assert step_(ex, 1.9, lambda p: [], {}, (1, 0.)).name == "wait"
    assert step_(ex, 2., lambda p: [], {}, (1, 0.)).name == "go"
    assert step_(ex, 2.1, lambda p: [], {}, (1, 9.)) is None and ex.status == "invalid"     # a new instance
    ex.offer(mini_plan(gen=9, until=3.), 2.2, (1, 0.), {})
    assert step_(ex, 3.1, lambda p: [], {}, (1, 0.)) is None and ex.status == "expired"
    ex.reset()
    assert ex.plan is None and ex.status == "idle" and not ex.history


def test_the_public_selection_starts_a_plan_without_its_own_choice():
    ex = PlanExecutor()
    plan = Plan("s", (1, 0.), 1, 0., None, 10., phases=(Phase("x"), Phase("y")),
                candidates=(Candidate("A", True, None, "x"), Candidate("B", False, "no", "y")), selected=None)
    ex.offer(plan, 1., (1, 0.), {})
    assert ex.phase is None and ex.selected is None
    assert not ex.select("B", 1.)                  # infeasible
    assert ex.select("A", 1.) and ex.phase.name == "x"


# ---- channels ----

def test_inline_channel_keeps_only_the_latest_and_a_new_epoch_drops_old_results():
    ch = InlineChannel(PARAMS, 2)
    ch.set_model(PARAMS, TERRAIN)
    a = ch.request("k", request(generation=1))
    ch.tick()                                   # in flight
    b = ch.request("k", request(generation=2))
    c = ch.request("k", request(generation=3))   # merges b
    ch.tick()                                   # a published
    assert ch.latest().sequence == a
    ch.tick()                                   # c in flight
    ch.tick()
    assert ch.latest().sequence == c and ch.latest().field.generation == 3 and ch.published == 2 and b == 2
    d = ch.request("k", request(generation=4))
    ch.tick()
    ch.invalidate()
    ch.tick(); ch.tick()
    assert ch.latest() is None and d == 4


class _FakeConn:
    """The broker's pipe: records what goes out, answers the plan message at once; during_send: an interleaving at that moment."""

    def __init__(self):
        self.out, self.during_send, self.reply = [], None, None

    def send(self, message):
        self.out.append(message)
        if message[0] == "plan":
            self.reply = ("plan", (message[1], message[2], message[3], message[4]), "PLAN", 1., self.model_id)
        if self.during_send is not None:
            hook, self.during_send = self.during_send, None
            hook()

    def poll(self, _):
        return True

    def recv(self):
        return self.reply


def _channel_without_process():
    ch = PlanChannel.__new__(PlanChannel)
    from ssbot.combat.scene_field_async import DoubleBuffer
    import threading
    ch.buffer = DoubleBuffer()
    ch._epoch = ch._sequence = 0
    ch._request = ch._model = None
    ch._model_version = 0
    ch._held_version = None
    ch._last_sent = 0
    ch._failure = None
    ch._stop = threading.Event()
    ch._wake = threading.Event()
    ch.sent = ch.published = 0
    ch._process = NS(is_alive=lambda: True)
    ch._conn = _FakeConn()
    return ch


def test_a_request_goes_with_its_own_model_whatever_the_threads_do():
    # the broker reads the latest request once: a new model and request arriving at any moment of its pass cannot cross
    ch = _channel_without_process()
    terrain_a, terrain_b = TERRAIN, Terrain2D(np.array([[FLOOR_Y + 1., 0., 80.]]), np.zeros((0, 3)), np.zeros((0, 4)))
    assert terrain_a.packed().tobytes() != terrain_b.packed().tobytes()
    ch.set_model(PARAMS, terrain_a)
    a = ch._model
    ch.request("k", "SNAP_A")
    ch._conn.model_id = a.id

    def newer():
        ch.set_model(PARAMS, terrain_b)
        ch.request("k", "SNAP_B")

    ch._conn.during_send = newer                      # exactly the old race: after the model went out, before the request
    assert ch._broker_step()
    sent = ch._conn.out
    assert [m[0] for m in sent] == ["model", "plan"] and sent[0][1] == a.version and sent[1][4] == a.version and sent[1][5] == "SNAP_A"
    assert sent[0][3] is terrain_a
    assert ch.buffer.current.key == ("k", a.version) and ch.buffer.current.sequence == 1
    # the next pass: the newer request with ITS model first
    b = ch._model
    ch._conn.model_id = b.id
    ch._conn.out = []
    assert ch._broker_step()
    assert [m[0] for m in ch._conn.out] == ["model", "plan"] and ch._conn.out[0][1] == b.version and ch._conn.out[1][5] == "SNAP_B"
    assert ch._conn.out[0][3] is terrain_b and ch.buffer.current.key == ("k", b.version)
    # an answer for another model is a failure, not a plan
    ch.request("k", "SNAP_C")
    ch._conn.model_id = "somebody else's"
    with pytest.raises(RuntimeError):
        ch._broker_step()


def test_a_missing_model_or_terrain_is_refused_never_an_empty_terrain(monkeypatch):
    for ch in (_channel_without_process(), InlineChannel(PARAMS, 1)):
        with pytest.raises(ValueError):
            ch.request("k", "SNAP")
        with pytest.raises(ValueError):
            ch.set_model(PARAMS, None)
    tac, ws, fc = planned(monkeypatch)
    tac.plan_input = CP.HeroInput(hero_state(35.), np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, None)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    tac.plan_input = CP.HeroInput(hero_state(35.), np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, None)
    r = tac.plan_runner
    r.channel = InlineChannel(PARAMS, 1)
    r._model_set = (None, None)
    go_(tac, ws, fc)
    assert r.hand is None and r.requests == 0


def test_the_resident_worker_publishes_complete_plans_and_fails_loudly():
    ch = PlanChannel(PARAMS, cpus=tuple(range(16, 24)))
    try:
        ch.set_model(PARAMS, TERRAIN)
        assert ch.worker_info["pid"] != 0 and set(ch.worker_info["cpus"]) <= set(range(16, 24))
        q = request()
        t0 = time.perf_counter_ns()
        seq = ch.request(("middle", q.instance), q)
        while (ch.latest() is None or ch.latest().sequence < seq) and time.perf_counter_ns() - t0 < 20e9:
            time.sleep(.001)
        pub = ch.latest()
        assert pub.sequence == seq and isinstance(pub.field, Plan) and pub.field.selected == "stay" and pub.field.complete()
        assert pub.build_ms > 0 and pub.origin >= t0
        # the result matches the in-process generator: pure
        direct = plan_of(q)
        assert pub.field.phase("aim_wait").at == direct.phase("aim_wait").at
        # a burst merges to the latest: fewer sends than requests, the newest published
        last = None
        for g in range(2, 42):
            last = ch.request(("middle", q.instance), replace(q, generation=g))
        t0 = time.perf_counter_ns()
        while ch.latest().sequence < last and time.perf_counter_ns() - t0 < 20e9:
            time.sleep(.001)
        assert ch.latest().field.generation == 41 and ch.sent < 41
        # a worker that dies is reported, never waited for
        ch._process.terminate()
        ch._process.join(5.)
        t0 = time.perf_counter()
        ch.request(("middle", q.instance), replace(q, generation=50))
        assert time.perf_counter() - t0 < .05
        while ch.failure is None and time.perf_counter() - t0 < 10.:
            time.sleep(.01)
        assert ch.failure is not None
        with pytest.raises(RuntimeError):
            ch.check_health()
    finally:
        ch.close()
    ch.close()                                   # twice is fine


# ---- the foreground: through the real L2 entry ----

def planned(monkeypatch, xs=(19., 39.), hx=35., family=None, delay=1, in_flight=True):
    monkeypatch.setattr(CP, "ENABLED", True)
    tac, ws, fc = scene(xs, hx)
    tac.pb.arena_x = (14.01, 48.99)
    fc.horizon, fc.known = 3., True
    ws.hero.can = {"input": True, "dash": True, "harpoon": True}
    ws.hero.contact = E("GROUND")
    ws.res.silk = E(3)
    tac.plan_runner = CP.PlanRunner(tac)
    tac.plan_runner.channel = InlineChannel(PARAMS, delay)
    set_hero(tac, hx)
    return tac, ws, fc


def set_hero(tac, x, **kw):
    tac.plan_input = CP.HeroInput(hero_state(x, **kw), np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, TERRAIN)


def go_(tac, ws, fc):
    ws.stamp.t_game_s += 1 / 60.
    for e in ws.entities:                       # the Control clocks run
        fsm = getattr(e, "fsm", None) or []
        e.fsm = [(a, b, c + 1 / 60.) for a, b, c in fsm]
    return tac._decide(ws, fc, G.GoalPrefs(mode="ENGAGE", stance_x=27., weights={}, hit_w={7: 1., 8: 1.}))


def antic(tac, ws, fc, iid=7, family=G.CC_JUMP, state="Jump Antic", elapsed=.02):
    change(fc, iid, family=family, state=state, committed=True)
    i = 0 if iid == 7 else 1
    ws.entities[i].fsm = [("Control", state, elapsed)]


def take_off(tac, ws, fc, iid=7, vx=None, face=1, state="Air"):
    i = 0 if iid == 7 else 1
    change(fc, iid, state=state)
    ws.entities[i].fsm = [("Control", state, .02)]
    ws.entities[i].flip_x = face > 0
    if vx is not None:
        ws.entities[i].vel = E((vx, 30.))


def plan_notes(tac):
    return (tac.last.get("clapper_plan") or {}).get("notes") or []


def test_after_the_first_bounce_no_second_strike_is_asked():
    plan = plan_of(request(W=body(2, 28.), hx=24.))
    assert plan.phase("over_head").attack == "stomp"
    for name in ("over_wait", "over_stay", "over_out"):
        assert plan.phase(name).attack is None and set(plan.phase(name).no_hit) == {1, 2}    # no second strike is asked for


def test_flag_off_is_the_legacy_table(monkeypatch):
    monkeypatch.setattr(CP, "ENABLED", False)
    assert CT.table() is CT.LEGACY_TABLE and CT.LEGACY_TABLE.tactics is CT.TACTICS
    assert "hold" in CT.LEGACY_TABLE.scores and "hold" not in CT.PLAN_TABLE.scores
    assert "cluster_lure" not in CT.LEGACY_TABLE.scores


def test_the_three_routes_are_there_before_the_lock_and_stay_runs_by_its_plan(monkeypatch):
    tac, ws, fc = planned(monkeypatch, hx=34.2)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    out = go_(tac, ws, fc)                       # the event: a request, the plan not yet here
    r = tac.plan_runner
    assert r.requests == 1 and r.exec.plan is None and tac.last["clapper_winner"]["rule"] == "keep"
    assert tac.last["clapper_plan"]["notes"][0]["what"] == "request"
    assert any(e.get("not_applicable") == "plan pending" for e in tac.last["clapper_eval"]["tactics"])
    go_(tac, ws, fc)
    out = go_(tac, ws, fc)                       # one tick later it is adoptable
    assert r.exec.plan is not None and r.exec.plan.selected == "stay" and r.exec.name == "aim_wait"
    res = next(n for n in sum((plan_notes(tac) for _ in [0]), []) if n["what"] == "result") if any(
        n["what"] == "result" for n in plan_notes(tac)) else None
    assert res is None or ({c["name"] for c in res["candidates"]} == {"stay", "under", "over"} and res["before_lock"])
    assert tac.last["clapper_winner"]["rule"] == "middle_jump" and out.target == 8 and 7 in out.no_hit
    assert out.entry_attack is None
    # at its absolute time, without a recomputation: to the guide point, the jumper as target
    depart = r.exec.plan.phase("aim_wait").at[0]
    n = r.requests
    while ws.stamp.t_game_s < depart:
        out = go_(tac, ws, fc)
    assert r.exec.name == "aim_guide" and r.requests == n
    assert out.target == 7 and out.stance_x == pytest.approx(r.exec.phase.stance[1])
    # she gets there: holding; the observed take-off: back to slash the walker, not waiting for the landing
    set_hero(tac, out.stance_x)
    ws.hero.pos = E((out.stance_x, ws.hero.pos.v[1]), conf=1.)
    ws.hero.hurtbox = [(out.stance_x - .25, 4.), (out.stance_x + .25, 4.), (out.stance_x + .25, 6.), (out.stance_x - .25, 6.)]
    out = go_(tac, ws, fc)
    assert r.exec.name == "aim_hold"
    fc.default = float("inf")
    take_off(tac, ws, fc, vx=9.)
    out = go_(tac, ws, fc)
    assert r.exec.name == "return" and out.target == 8 and out.entry_attack.kind == "side" and out.entry_attack.source == 7
    assert 7 in out.no_hit and r.exec.handled(r.exec.plan.instance, "departed")
    assert r.requests == n                       # no request at the take-off: it did not wait for the worker


def test_a_hand_back_past_the_departure_gives_up_the_guide_at_once_and_asks_again(monkeypatch):
    tac, ws, fc = planned(monkeypatch, hx=34.2)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    go_(tac, ws, fc); go_(tac, ws, fc)
    r = tac.plan_runner
    assert r.exec.name == "aim_wait"
    # the source tail owner took the keys: the same place, her hand-back past the written latest departure
    keys = (0,) * 40
    tac.plan_input = CP.HeroInput(hero_state(34.2), np.zeros(1 + len(keys), np.int64), kin.HoldState.idle(1), PARAMS, TERRAIN,
                                  commit=("b2 bounce_tail", True, keys))
    go_(tac, ws, fc)
    assert r.hand.known and r.hand.t > r.exec.plan.get("latest_depart")
    assert r.exec.name == "aim_attack"             # at once: the guide is given up on this tick

def test_a_late_result_is_used_only_if_its_instance_holds(monkeypatch):
    tac, ws, fc = planned(monkeypatch, delay=5)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    go_(tac, ws, fc)
    r = tac.plan_runner
    # a new move of the same jumper before the result: the old instance's result is rejected, the new one's is used
    tac.t_commit[7] = ws.stamp.t_game_s + 1.    # (gauntlet keeps t_commit by setdefault: this stands for a new instance)
    seen = []
    for _ in range(14):
        go_(tac, ws, fc)
        seen += plan_notes(tac)
    assert any(n["what"] == "result" and n["state"] == "rejected" and n["reason"] == "instance changed" for n in seen)
    assert any(n["what"] == "request" and n["why"] == "first antic" for n in seen)
    assert r.exec.plan is not None and r.exec.plan.instance == (7, tac.t_commit[7])


def test_a_late_result_after_the_takeoff_still_runs_its_written_branch(monkeypatch):
    tac, ws, fc = planned(monkeypatch, delay=4)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    go_(tac, ws, fc)                             # the request, the result four ticks away
    fc.default = float("inf")
    take_off(tac, ws, fc, vx=8.)
    out = go_(tac, ws, fc)                       # the take-off does not wait: no plan yet, the generic rules
    r = tac.plan_runner
    assert r.exec.plan is None
    seen = []
    for _ in range(5):
        out = go_(tac, ws, fc)
        seen += plan_notes(tac)
    assert r.exec.name == "return" and out.target == 8 and out.entry_attack.kind == "side"
    assert any(n["what"] == "takeoff" and n["route"] == "return" for n in seen)


def test_no_result_at_all_the_scene_is_released_and_the_generic_rules_go_on(monkeypatch):
    tac, ws, fc = planned(monkeypatch, delay=10 ** 6)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    go_(tac, ws, fc)
    r = tac.plan_runner
    assert r.context("middle", ws.stamp.t_game_s) == {"pending": True}
    t0 = ws.stamp.t_game_s
    n = r.requests
    while ws.stamp.t_game_s < t0 + CP.PEND_MAX_S + .05:
        out = go_(tac, ws, fc)
    assert r.context("middle", ws.stamp.t_game_s) is None and r.exec.plan is None
    assert tac.last["clapper_winner"]["rule"] != "middle_jump" and r.requests == n     # no storm while nothing arrives


def test_unknown_hand_back_is_not_a_route():
    S0, hand = hand_of(35.)
    plan = plan_of(request(S0=S0, hand=replace(hand, known=False, t=math.inf)))
    assert plan.status == "none" or not cand(plan, "stay").feasible
    assert "hand-back unknown" in cand(plan, "stay").reason


def test_the_switches_are_bound_in_the_manifest(monkeypatch):
    import sys
    from pathlib import Path
    import ssbot
    from ssbot.train.forum_measure_manifest import configuration_manifest
    root = Path(ssbot.__file__).parent
    m = configuration_manifest(root, None, environ={"SSBOT_FORUM_TWO_PLAN": "1", "SSBOT_FORUM_TWO_PLAN_INLINE": "1"}, modules=sys.modules)
    for key, name in (("SSBOT_FORUM_TWO_PLAN", "ENABLED"), ("SSBOT_FORUM_TWO_PLAN_INLINE", "INLINE")):
        entry = m["switches"][key]
        assert entry["resolution"] == "runtime_binding", key
        assert "ssbot.combat.tactics.clapper_plans." + name in entry["effective"]


def test_no_change_means_no_request_and_micro_motion_asks_nothing(monkeypatch):
    tac, ws, fc = planned(monkeypatch)
    go_(tac, ws, fc)
    antic(tac, ws, fc, family=G.CC_JUMP_CAST, state="Cast Slam Antic")
    go_(tac, ws, fc); go_(tac, ws, fc)
    r = tac.plan_runner
    n = r.requests
    assert r.exec.plan is not None
    for k in range(20):
        # the walker's and her small motion inside the support
        x = 39. + .02 * (k % 3)
        change(fc, 8, pos=(x, fc.subjects[1].pos[1]))
        go_(tac, ws, fc)
    assert r.requests == n


def test_a_closing_walker_asks_at_once_and_the_takeoff_does_not_wait(monkeypatch):
    tac, ws, fc = planned(monkeypatch, delay=1)
    go_(tac, ws, fc)
    antic(tac, ws, fc, family=G.CC_JUMP_CAST, state="Cast Slam Antic")
    go_(tac, ws, fc); go_(tac, ws, fc)
    r = tac.plan_runner
    n = r.requests
    gen = r.exec.plan.generation
    change(fc, 8, pos=(39. - CP.SOFT_WALKER_U - .1, fc.subjects[1].pos[1]), state="Walk")
    ws.entities[1].dmg_boxes[0].poly = [(36.9, 3.), (38.9, 3.), (38.9, 7.), (36.9, 7.)]
    go_(tac, ws, fc)
    assert r.requests == n + 1 and any(x["what"] == "request" and x["why"] == "the walker started walking" for x in plan_notes(tac))
    go_(tac, ws, fc); go_(tac, ws, fc)
    assert r.exec.plan.generation > gen
    assert r.exec.plan.get("lock_t") is not None


def test_the_walker_closed_the_gap_prepared_route_runs_by_wall_room(monkeypatch):
    tac, ws, fc = planned(monkeypatch)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    go_(tac, ws, fc); go_(tac, ws, fc)
    r = tac.plan_runner
    assert r.exec.plan.selected == "stay"
    # take-off with the walker suddenly next to the landing: no standing gap
    change(fc, 8, pos=(32., fc.subjects[1].pos[1]), state="Walk")
    ws.entities[1].dmg_boxes[0].poly = [(31., 3.), (33., 3.), (33., 7.), (31., 7.)]
    take_off(tac, ws, fc, vx=10.)
    plan = r.exec.plan
    n = r.requests
    out = go_(tac, ws, fc)
    # still the same plan (no search): one of the prepared routes, or an explicit block
    note = next(x for x in plan_notes(tac) if x["what"] == "takeoff")
    assert note["route"] in ("under", "over", "blocked") and "closed" in note["reason"]
    assert r.exec.plan is plan or r.exec.status == "blocked"
    if note["route"] == "over":
        assert out.target == 8 and out.entry_attack.kind == "stomp" and out.stance_x == pytest.approx(32.)
    elif note["route"] == "under":
        assert out.target == 7 and 7 in out.no_hit


def test_landed_in_the_gap_the_over_followup_is_done_and_elsewhere_the_return_is_handed_on(monkeypatch):
    tac, ws, fc = planned(monkeypatch)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    go_(tac, ws, fc); go_(tac, ws, fc)
    r = tac.plan_runner
    ex = r.exec
    ex.name = "over_back"
    # the walker's far side: the rows cannot cross its body: not a success; the public middle return keeps the goal
    far = 43.
    ws.hero.pos = E((far, float(ws.hero.pos.v[1])))
    ws.hero.hurtbox = [(far - .25, 4.), (far + .25, 4.), (far + .25, 6.), (far - .25, 6.)]
    set_hero(tac, far)
    ws.hero.contact = E("GROUND")
    go_(tac, ws, fc)
    assert ex.status == "handed_back" and ex.plan is None
    assert tac._clapper_priority.get("back") is not None and tac._clapper_priority["back"]["iid"] == 7
    assert any(x["what"] == "return kept" for x in plan_notes(tac))
    # in the gap: done, nothing kept
    tac, ws, fc = planned(monkeypatch)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    go_(tac, ws, fc); go_(tac, ws, fc)
    ex = tac.plan_runner.exec
    ex.name = "over_back"
    ws.hero.contact = E("GROUND")
    go_(tac, ws, fc)
    assert ex.status == "complete" and ex.plan is None and tac._clapper_priority.get("back") is None

def test_a_plan_first_seen_in_flight_keeps_its_return_too():
    # no antic clock (first seen in its flight, the replay's k_out_back: this raised and decide swallowed it, the goal was lost)
    plan = plan_of(request(J=body(1, 25., "Air", "CC_JUMP", facing=1), W=body(2, 28.), hx=26., stage="flight", antic_at=None, land=30., land_vx=5.45,
                           air_at=0.))
    runner = NS(moves={plan.instance[0]: dict(antic_at=None)}, notes=[], exec=NS(reason="landed_away"))
    sc = NS(subjects=[], t=2., hx=40., frame=500, mem={})
    CP.PlanRunner._keep_return(runner, sc, plan)
    due = sc.mem["back"]
    assert due["start_t"] == plan.made_t and due["iid"] == 1 and due["family"] == "CC_JUMP" and due["end_f"] == 500
    assert due["start_f"] == 500 - round((2. - plan.made_t) * 60.)
    assert runner.notes[-1]["what"] == "return kept"


def test_the_way_back_goes_to_the_body_standing_nearer_by_the_observed_landing(monkeypatch):
    # left of both, the retreat done and the hazard over: the landing decides who is in front of her
    for land_past, want in ((False, 7), (True, 8)):
        tac, ws, fc = planned(monkeypatch, xs=(36., 37.), hx=28.)
        go_(tac, ws, fc)
        antic(tac, ws, fc)
        go_(tac, ws, fc); go_(tac, ws, fc)
        r = tac.plan_runner
        ex = r.exec
        assert ex.plan is not None and ex.plan.scene == "cluster"
        ex.select("attack", ws.stamp.t_game_s)
        ex.name = "attack_retreat"
        r.moves[7] = dict(r.moves.get(7) or {}, land=39. if land_past else 30., air_at=ws.stamp.t_game_s - 2., face=-1, vx=-5.)
        r._resolved = "retreat"
        monkeypatch.setattr(r, "_hazard_over", lambda *a, **k: True)
        out = go_(tac, ws, fc)
        assert ex.name == ("attack_back_other" if land_past else "attack_back_jumper")
        assert out.target == want


def test_a_body_of_the_plan_gone_ends_it_with_no_error_in_the_tick(monkeypatch):
    tac, ws, fc = planned(monkeypatch)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    go_(tac, ws, fc); go_(tac, ws, fc)
    r = tac.plan_runner
    ex = r.exec
    assert ex.plan is not None
    ex.name = "under"                            # no event of its own about the other body
    gone = fc.subjects[1]
    sc = NS(tac=tac, ws=ws, t=ws.stamp.t_game_s, subjects=[fc.subjects[0]], hx=30., geo=None, frame=1, grounded=False, region=None)
    r.tick(sc)
    assert gone.iid == 8 and ex.plan is None and ex.status == "invalid" and "gone" in ex.reason


def test_a_new_move_of_the_other_one_ends_the_late_followups(monkeypatch):
    tac, ws, fc = planned(monkeypatch)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    go_(tac, ws, fc); go_(tac, ws, fc)
    ex = tac.plan_runner.exec
    ex.name = "over_back"
    change(fc, 8, family=G.CC_SLAM, state="Slam Antic", committed=True)
    go_(tac, ws, fc)
    assert ex.plan is None and ex.status == "invalid"


# ---- the bounded approach: what the plan counts on is what the Run sends ----

def _closed_loop(goal_x, by_f, x0=34., steps=120):
    """next_mask frame by frame through the model, as the Run: her arrival frame and the keys."""
    from ssbot.combat.air_chain import ChainSim
    from ssbot.combat.knife_chain_waypoint import WaypointGoal, next_mask
    from ssbot.combat.holdfilter import hold_filter_jit
    S = hero_state(x0)
    hold = kin.HoldState.idle(1)
    sent = [0]
    keys = []
    for f in range(steps):
        prefix = np.array([sent[-1]], np.int64)
        sim = ChainSim(S, prefix, hold, PARAMS, TERRAIN, f, f)
        mask, what = next_mask(sim, WaypointGoal(goal_x, by_f, "under", 1, ((1, 0.), 1, "under")), f)
        if what == "arrived":
            xs = sim.roll(np.zeros((1, 60), np.int64)).centre[0, :, 0]
            d = 1 if goal_x > x0 else -1
            crossing = int(np.argmax((xs - goal_x) * d >= -.2)) if ((xs - goal_x) * d >= -.2).any() else 0
            return f + crossing - sim.off, keys, what, float(xs[-1])
        if what == "late":
            return f, keys, what, None
        keys.append(int(mask))
        sent.append(int(mask))
        # one frame on: the mask in flight lands, the new one is next
        lat, hold2 = hold_filter_jit(prefix[None], hold)
        r = kin.rollout(S, lat, PARAMS, TERRAIN)
        S = np.asarray(r.final[:, 0], np.float64)
        hold = hold2
    return None, keys, "no end", None


# A real bounce STATE (replay k_over_out frame 2915, her planner input: DownSlash hit on the body at 19.5, 0.26 u from its back edge)
BOUNCE_S = np.array([
    21.350001, 6.327699, 21.515001, 5.979699, 21.350001, 6.327699, -8.25, -10.0, 0.164326, 1.0, -1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 4.0, -20.0, -1.0, -1.0, 0.0, 1.0, 0.049998, 0.233336, 0.0, 0.0, 0.0, 0.016666,
    0.0, 0.0, 0.0, -1.0, 1.0, 1572865.0, 9.0, 0.143334, 0.0, 0.0, 0.0, 1.0, -1.0, 0.0,
    0.0, 0.0, -1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, -1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, -0.016664, 0.0, -1.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 21.625381, 5.746896, 0.0, 0.0, 0.0, 0.399984, 2.0, 0.050002, 0.0, 0.0,
    0.0, 8.0,
], np.float64)
BOUNCE_PREFIX = 1572865
BOUNCE_HOLD = kin.HoldState(np.array([[True, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, True, True, False]], bool), np.array([[True, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, True, True, False]], bool), np.array([[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]], np.int64), np.array([[7, 1, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 5, 4, 11]], np.int64))


def _closed_loop_over(S, prefix, hold, goal, steps=90):
    """next_mask frame by frame through the model for a place past a body: the keys, how it ended, her boxes along the way."""
    from ssbot.combat.air_chain import ChainSim
    from ssbot.combat.knife_chain_waypoint import next_mask
    from ssbot.combat.holdfilter import hold_filter_jit
    sent = [prefix]
    keys, boxes, whats = [], [], []
    for f in range(steps):
        pre = np.array([sent[-1]], np.int64)
        sim = ChainSim(S, pre, hold, PARAMS, TERRAIN, f, f)
        mask, what = next_mask(sim, goal, f)
        whats.append(what)
        boxes.append(sim.roll(np.zeros((1, 3), np.int64)).box[0, sim.off])
        if what in ("arrived", "late"):
            return keys, what, boxes, whats
        keys.append(int(mask))
        sent.append(int(mask))
        lat, hold2 = hold_filter_jit(pre[None], hold)
        r = kin.rollout(S, lat, PARAMS, TERRAIN)
        S = np.asarray(r.final[:, 0], np.float64)
        hold = hold2
    return keys, "no end", boxes, whats


def test_the_way_out_waits_for_the_bounce_and_passes_above_the_body():
    from ssbot.combat.knife_chain_waypoint import WaypointGoal
    body = (17.25, 0., 20.84, CP.BODY_TOP)
    far = 16.05
    plan = ((1, 0.), 1, "over_out")
    def meets(boxes):
        return [i for i, h in enumerate(boxes) if h[0] <= body[2] and h[2] >= body[0] and h[1] <= body[3] and h[3] >= body[1]]
    # the real bounce beside its near edge: the run from the bounce on passes above it, and past her invulnerability she is never in it
    keys, what, boxes, whats = _closed_loop_over(BOUNCE_S, BOUNCE_PREFIX, BOUNCE_HOLD, WaypointGoal(far, 60, "out", 1, plan, over=body))
    assert what == "arrived", (what, whats)
    assert whats[0] == "go" and keys[0] == kin.B_LEFT, whats
    assert [i for i in meets(boxes) if i > 9] == [], meets(boxes)
    # the deadline short of the run's arrival: she waits for height, then the dash, also above it
    keys, what, boxes, whats = _closed_loop_over(BOUNCE_S, BOUNCE_PREFIX, BOUNCE_HOLD, WaypointGoal(far, 34, "out", 1, plan, over=body))
    assert what == "arrived", (what, whats)
    assert whats[0] == "wait" and any(k & kin.B_DASH for k in keys), whats
    assert [i for i in meets(boxes) if i > 9] == [], (whats, meets(boxes))
    # falling beside it: no key takes her over, and that is said: it is no route
    S = np.asarray(kin.initial_state(PARAMS, 21.35, 5., ground=False), np.float64)
    keys, what, boxes, whats = _closed_loop_over(S, 0, kin.HoldState.idle(1), WaypointGoal(far, 60, "out", 1, plan, over=body))
    assert what == "late" and not keys, (what, whats)
    # no time left either way
    keys, what, boxes, whats = _closed_loop_over(BOUNCE_S, BOUNCE_PREFIX, BOUNCE_HOLD, WaypointGoal(far, 2, "out", 1, plan, over=body))
    assert what == "late", (what, whats)
    # the same place with no body named: the ordinary approach starts into it at once (what over= is for)
    keys, what, boxes, whats = _closed_loop_over(BOUNCE_S, BOUNCE_PREFIX, BOUNCE_HOLD, WaypointGoal(far, 60, "out", 1, plan))
    assert whats[0] == "go"


def test_the_over_out_phase_is_a_bounded_passage_with_its_body():
    plan = plan_of(request(J=body(1, 25., "Air", "CC_JUMP", facing=1), W=body(2, 36.5), hx=36., stage="flight", antic_at=None, land=30.,
                           land_vx=5.45, air_at=0.))
    assert plan.phase("over_out").go == "out"
    runner = NS(exec=NS(plan=plan), _go_done=set(), moves={plan.instance[0]: dict(air_at=0.)}, stance=lambda sc, ph: 39.04)
    subjects = [NS(iid=2, pos=(36.5, 3.))]
    sc = NS(frame=100, t=.2, hx=36., geo={"bodies": {2: (35.16, 37.84)}}, subjects=subjects)
    goal = CP.PlanRunner.waypoint(runner, sc, plan.phase("over_out"))
    assert goal.x == pytest.approx(39.04) and goal.kind == "out" and goal.family == "CC_JUMP"
    assert goal.over == (36.5 - CP.BODY_HALF, 0., 36.5 + CP.BODY_HALF, CP.BODY_TOP)      # either pose, its back reaching past the observed one
    assert goal.by_f == 100 + math.ceil((CP.FLIGHT_S - .05 - .2) * 60.)
    # no observed body, no place to pass above
    assert CP.PlanRunner.waypoint(runner, NS(frame=100, t=.2, hx=36., geo={"bodies": {}}, subjects=subjects), plan.phase("over_out")) is None


def test_the_cleanup_receipt_keeps_the_plan_workers_evidence(tmp_path, monkeypatch):
    from ssbot.tools import combat_run as C
    from tests.test_b2_worker_batch import options
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_B2", "0")
    calls = []
    runner = NS(close=lambda: calls.append("close"),
                stats=lambda: (calls.append("stats"), dict(channel=dict(exit=dict(pid=7, exitcode=0))))[1])
    def closed(policy):
        return C._close_worker(options(tmp_path), link=None, recorder=None, out=None, diagnostics=None, policy=policy, stage="episodes",
                               primary_error=None)
    result = closed(NS(tac=NS(plan_runner=runner)))
    assert calls == ["close", "stats"] and result["complete"]             # closed first, so the exit is in it
    assert result["plan_worker"]["channel"]["exit"]["exitcode"] == 0 and result["resources"]["plan_worker"] == "pass"
    plain = closed(NS(tac=NS(plan_runner=None)))
    assert "plan_worker" not in plain and plain["resources"]["plan_worker"] == "not_created"


def test_the_two_play_idle_hit_keeps_to_the_phase_that_asks_no_hit():
    from ssbot.combat import two_play as TP
    cls = next(c for c in vars(TP).values() if isinstance(c, type) and "_idle_step" in vars(c))
    two = object.__new__(cls)
    two.idle = TP.IdleRun(iid=7, f0=90, re=False, d0=2., hp0=5)
    two.entry = {}
    two.plan_no_hit = frozenset({7})
    two._second = lambda f: None
    clapper = lambda iid, x: dict(iid=iid, type_key=TP._sp.CLAPPER, pos=[x, 3.], hp=100, fsms=[dict(name="Control", state="Idle", t=.5)])
    s = dict(f=100, hero=dict(health=5, pos=[25., 4.5], vel=[0., 0.]), ents=[clapper(7, 20.), clapper(8, 40.)])
    assert two._idle_step(100, s, True, True, 7) is None
    assert two.idle.why == "plan"


def test_the_plan_takes_the_keys_from_a_vault_approach_only():
    from ssbot.combat import knife_chain_air_native as AN
    cls = next(c for c in vars(AN).values() if isinstance(c, type) and "_waypoint_offer" in vars(c))
    chain = object.__new__(cls)
    chain.post_context = chain.recovery = None
    goal = NS(waypoint=NS(kind="under"))
    def takes(chain_name, link, prefs=goal):
        chain.runner = NS(run=NS(chain=chain_name, link=link))
        return chain._plan_takes_vault_approach(prefs)
    assert takes("vault_idle", "approach")
    assert not takes("vault_idle", "near")                 # a strike under way keeps its keys
    assert not takes("vault_idle", "over")
    assert not takes("rune_transfer", "approach")
    assert not takes("vault_idle", "approach", NS(waypoint=None))    # no stage asking: the approach goes on as before
    chain.post_context = {"move": 1}
    assert not takes("vault_idle", "approach")
    chain.post_context, chain.recovery = None, {"first": 1}
    assert not takes("vault_idle", "approach")
    chain.recovery, chain.runner = None, NS(run=None)
    assert not chain._plan_takes_vault_approach(goal)


def test_a_failed_waypoint_answers_for_the_jump_it_is_about():
    from ssbot.combat import knife_chain_air_native as AN
    from ssbot.combat.knife_chain_commitment import MoveInstance
    from ssbot.combat.knife_chain_failure import FailureExposure
    cls = next(c for c in vars(AN).values() if isinstance(c, type) and "_waypoint_offer" in vars(c))
    with pytest.raises(ValueError):
        FailureExposure(MoveInstance(7, 100, "WAYPOINT"), 100, 120, None)     # the Run's own label answers for nothing
    chain = object.__new__(cls)
    move = MoveInstance(7, 100, "WAYPOINT")
    chain._waypoint_responsibility = {move: (MoveInstance(7, 100, "CC_JUMP"), None)}
    exposure = chain._failure_exposure(move, 100, 120, None)
    assert exposure.move.family == "CC_JUMP" and exposure.move.target_iid == 7 and exposure.active(125)
    stop = []
    chain._waypoint_responsibility = {}
    chain._stop = lambda why, f: (stop.append(why), (_ for _ in ()).throw(RuntimeError(why)))
    with pytest.raises(RuntimeError):
        chain._failure_exposure(move, 100, 120, None)
    assert stop == ["missing critical waypoint failure responsibility"]


def test_the_run_sends_what_the_route_counted_on():
    from ssbot.combat import knife_chain_waypoint as WP
    S = hero_state(34.)
    m = CP.Roller(S, np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, TERRAIN)
    for goal, by in ((24.8, 40), (22., 45), (31., 80), (40., 60)):
        row, k, how = WP.route(m, np.zeros(CP.ROLL_T, np.int64), 0, goal, by_k=by)
        assert k is not None and k <= by, (goal, how)
        f, keys, what, x = _closed_loop(goal, by + 2)
        assert what == "arrived", (goal, what)
        assert abs(f - k) <= 6, (goal, how, f, k)                  # the frame she is there
        assert abs(x - m.xs(row[None])[0][-1]) <= 1.9, (goal, how, x)     # where she stops
        assert bool(np.any(row & kin.B_DASH)) == any(v & kin.B_DASH for v in keys), (goal, how)


def test_the_route_runs_when_it_can_and_dashes_only_when_it_must():
    from ssbot.combat import knife_chain_waypoint as WP
    S = hero_state(34.)
    m = CP.Roller(S, np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, TERRAIN)
    row, k, how = WP.route(m, np.zeros(CP.ROLL_T, np.int64), 0, 31., by_k=60)
    assert how == "run" and not np.any(row & kin.B_DASH)
    row, k, how = WP.route(m, np.zeros(CP.ROLL_T, np.int64), 0, 25., by_k=30)
    assert how == "dash" and np.any(row & kin.B_DASH) and k <= 30
    # released before the goal: the sprint's skid stops her at it, not 1.9 u past it
    x = m.xs(row[None])[0]
    assert abs(x[-1] - 25.) <= 1.9                 # (a sprint's stop is not continuous: 8.2 u, then 10.1 u: the first that gets there)
    # a dash on cooldown is pressed when it can start: an edge held through the cooldown would never start one
    S1 = S.copy()
    S1[kin.DASH_CD] = .3
    m1 = CP.Roller(S1, np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, TERRAIN)
    row, k, how = WP.route(m1, np.zeros(CP.ROLL_T, np.int64), 0, 22.)
    assert how == "dash" and np.any(m1.rollout(row[None]).mode[0] == kin.M_DASH)


# ---- Sol seq 271: the Run's whole route against the delayed hazards; the stage whose strike was given up ----

def test_the_route_keys_are_the_keys_the_run_counts_on():
    from ssbot.combat import knife_chain_waypoint as WP
    from ssbot.combat.air_chain import ChainSim
    f = 100
    for x0, goal_x in ((30., 38.), (38., 30.)):                       # either side
        sim = ChainSim(hero_state(x0), np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, TERRAIN, f, f)
        goal = WP.WaypointGoal(goal_x, f + 80, "retreat", 1, ((1, 0.), 1, "attack_retreat"))
        mask, what = WP.next_mask(sim, goal, f)
        keys = WP.route_keys(sim, goal, f, mask)
        row, k, how = WP.route(WP.SimRoller(sim), np.zeros(78 + 8, np.int64), 0, goal_x, by_k=78, tol=goal.tol)
        assert what == "go" and how == "run" and keys[0] == mask
        # the run up to the tick it hands back (Sol seq 273: next_mask's "arrived"; a run's glide is short, so at its arrival)
        assert np.array_equal(keys, row[:len(keys)]) and np.all(keys == mask) and len(keys) == k, (x0, k, len(keys))
    # a dash she holds stays held, as next_mask keeps it (releasing it would end the sprint), up to the tick it hands back: the
    # release that stops her there is that tick's, the next owner's first key
    sim = ChainSim(hero_state(30.), np.array([kin.B_RIGHT | kin.B_DASH], np.int64), kin.HoldState.idle(1), PARAMS, TERRAIN, f, f)
    goal = WP.WaypointGoal(40., f + 60, "retreat", 1, ((1, 0.), 1, "attack_retreat"))
    keys = WP.route_keys(sim, goal, f, kin.B_RIGHT | kin.B_DASH)
    assert 0 < len(keys) <= WP.MAX_F and np.all(keys == (kin.B_RIGHT | kin.B_DASH))
    # nowhere to arrive from the key sent: no route to check
    assert WP.route_keys(sim, WP.WaypointGoal(200., f + 60, "retreat", 1, ((1, 0.), 1, "attack_retreat")), f,
                         kin.B_RIGHT | kin.B_DASH) is None


@pytest.mark.parametrize("mirror", [False, True])
def test_the_route_keys_start_from_the_key_sent_never_a_refused_dash(mirror):
    # Sol seq 272 on #342: f100, 30 -> 39 u, by_f 132, prefix 0: next_mask asks R+DASH; its lock refused, the key sent is R, but the
    # route checked started from R+DASH again (route() re-chose the refused dash), 27 keys; mirrored L+DASH -> L -> L+DASH
    from ssbot.combat import knife_chain_waypoint as WP
    from ssbot.combat.air_chain import ChainSim
    f = 100
    x0, gx, key = (39., 30., kin.B_LEFT) if mirror else (30., 39., kin.B_RIGHT)
    sim = ChainSim(hero_state(x0), np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, TERRAIN, f, f)
    goal = WP.WaypointGoal(gx, 132, "retreat", 1, ((1, 0.), 1, "attack_retreat"))
    assert WP.next_mask(sim, goal, f) == (key | kin.B_DASH, "dash")
    # refused: the run of the key sent, never a dash, while every later new dash is refused too: up to next_mask's "late" at 113
    # (Sol seq 276: 13 keys, the last acting on f114; #346 checked the whole 38-key window to f139)
    keys = WP.route_keys(sim, goal, f, key, dash_refused=True)
    assert keys[0] == key and not np.any(keys & kin.B_DASH) and len(keys) == 13 and np.all(keys == key)
    # not refused: the dash it sends, held up to the tick the Run hands back (Sol seq 273: 23 keys, #343 checked 27)
    keys = WP.route_keys(sim, goal, f, key | kin.B_DASH)
    assert keys[0] == key | kin.B_DASH and np.all(keys == key | kin.B_DASH) and len(keys) == 23


def _bomb_support(*bombs, owner=1, body=None):
    """A RangeSupport holding small-rune bombs (owner, x, y, r, first, last lit look-ahead frame from its origin), its samples past any
    route; the plan's jumper (owner) in the tracker; body: a world box (x0, y0, x1, y1) of another enemy's raw damage on every sample."""
    from ssbot.combat import forum_v2 as v2
    from ssbot.combat.attack_range import Mask
    rs = v2.RangeSupport(v2.Canvas(), (0, 160))
    rs.trk = NS(now={owner: (0, 0, NS(fam="CC_JUMP_CAST"))}, orphan_hazards={})
    rs.bombs = np.asarray(bombs, np.float64).reshape(-1, 6)
    if body is not None:
        x0, y0, x1, y1 = body
        raw = Mask(np.ones((int(round((y1 - y0) / .05)), int(round((x1 - x0) / .05))), bool), int(round(x0 / .05)), int(round(y0 / .05)))
        d, ix0, iy0 = v2.dilate(raw, .05, 0.)
        for si in range(len(rs.samples)):
            rs.add(si, 100, d, ix0, iy0)
    return rs


def _offer(monkeypatch, x0, goal_x, bombs=(), active=False, by=80, f=100, body=None, lock=None, sim=None):
    """The production waypoint offer on a real model and support: (offer, chain). Its context checks pass; notes and recoveries kept.
    lock: "refuse" / "pass" stands in for the new dash's lock scan (a body met on its locked motion / none); sim: a given model
    state (her actual prefix is the queued one)."""
    from dataclasses import asdict
    from ssbot.combat import knife_chain_air_native as AN, knife_chain_waypoint as WP
    from ssbot.combat.air_chain import ChainSim
    from ssbot.combat.knife_chain_commitment import MoveInstance, PathContact
    from ssbot.combat.knife_chain_eval import Run
    cls = next(c for c in vars(AN).values() if isinstance(c, type) and "_waypoint_offer" in vars(c))
    monkeypatch.setattr(AN, "complete_hf", lambda state: True)
    monkeypatch.setattr(AN, "logical_copy", lambda r: NS(run=Run(r.run.chain, r.run.link, dict(r.run.v))))
    if sim is None:
        sim = ChainSim(hero_state(x0), np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, TERRAIN, f, f)
    plan = ((1, 0.), 3, "attack_retreat")
    goal = WP.WaypointGoal(goal_x, f + by, "retreat", 1, plan, family="CC_JUMP_CAST")
    chain = object.__new__(cls)
    chain.notes, chain.recovered = [], []
    chain._note = lambda ev, **kw: chain.notes.append(dict(event=ev, **kw))
    chain._recover = lambda why, frame: chain.recovered.append((why, frame))
    move = MoveInstance(1, f - 5, WP.FAMILY)
    run = Run(WP.PROGRAM, "go", {"iid": 1, "plan": list(plan), "x": goal_x, "by_f": f + by, "kind": "retreat", "move": asdict(move)})
    chain.runner = NS(run=run if active else None, fork_empty=lambda anchor: NS(run=None))
    chain._waypoint_failed, chain._waypoint_declined, chain._waypoint_responsibility = set(), None, {}
    chain.queued_prefix = lambda frame, state: (int(sim.prefix[0]), None)
    if lock is not None:
        met = (PathContact(f + 9, 7, "body"),) if lock == "refuse" else ()
        chain._dash_lock_scan = lambda *a, **k: (NS(complete=True, contacts=met), {"lock": lock})
    state = {"f": f, "hero": {"hero_accepting_input": True}}
    centre_y = float(sim.roll(np.zeros((1, 1), np.int64)).centre[0, 0, 1])
    rs = _bomb_support(*[(2, bx, centre_y - .9, 2.166, on, off) for bx, on, off in bombs], body=body)
    return chain._waypoint_offer(state, f / 60., sim, NS(rs=rs), NS(waypoint=goal)), chain


@pytest.mark.parametrize("mirror", [False, True])
def test_a_run_whose_route_meets_a_delayed_hazard_is_handed_back_while_others_can_leave_it(monkeypatch, mirror):
    # #341 3354-3380: the retreat Run held R toward 36.42 while owner 335470's bomb at 30.18 was forecast lit 3381-3392 on its route;
    # the one-step gate met it at 3380 (first blocked 3381), after the last tick the ordinary owners could still leave (open-loop
    # replays: a hand-back by 3372 clears it, none from 3376 on)
    x0, goal_x, bomb_x = (38., 30., 34.) if mirror else (30., 38., 34.)
    # the bomb lights while she runs through it, far past this tick's step: no new Run starts into it
    out, chain = _offer(monkeypatch, x0, goal_x, bombs=[(bomb_x, 25, 35)])
    assert out is None and not chain.recovered
    note = next(n for n in chain.notes if n["event"] == "waypoint_rejected")
    assert note["reason"] == "route meets a delayed hazard" and note["first"]["owner_iid"] == 2 and note["first"]["kind"] == "delayed"
    assert 125 <= note["first"]["frame"] <= 135 and note["active"] is False
    # a Run already going is handed back through recovery (its failure kept) and not restarted for this stage
    out, chain = _offer(monkeypatch, x0, goal_x, bombs=[(bomb_x, 25, 35)], active=True)
    assert out is None and chain.recovered == [("waypoint route meets a delayed hazard", 100)] and len(chain._waypoint_failed) == 1
    # the same bomb lit after she has run past it, or one off her route: the Run goes as before
    for bombs in ([(bomb_x, 80, 90)], [(bomb_x + (6. if mirror else -6.), 25, 35)], []):
        out, chain = _offer(monkeypatch, x0, goal_x, bombs=bombs)
        assert out is not None and out.details["waypoint"] and out.mask == (kin.B_LEFT if mirror else kin.B_RIGHT), bombs
        assert not any(n["event"] == "waypoint_rejected" for n in chain.notes)
    # lit at the place well after she gets there: the stance's own owners answer for it, not this Run
    out, chain = _offer(monkeypatch, x0, goal_x, bombs=[(goal_x, 110, 120)])
    assert out is not None
    # another enemy's body far along the route is not a delayed hazard: the step gate meets it as before
    out, chain = _offer(monkeypatch, x0, goal_x, body=(bomb_x - .5, 0., bomb_x + .5, 9.))
    assert out is not None and not any(n["event"] == "waypoint_rejected" for n in chain.notes)


def test_the_route_check_leaves_a_body_passage_and_an_unscannable_route_to_the_step_gate():
    from ssbot.combat import knife_chain_air_native as AN, knife_chain_waypoint as WP
    from ssbot.combat.knife_chain_geometry import GeometryUnavailable
    cls = next(c for c in vars(AN).values() if isinstance(c, type) and "_waypoint_delayed_ahead" in vars(c))
    chain = object.__new__(cls)
    notes = []
    chain._note = lambda ev, **kw: notes.append(dict(event=ev, **kw))
    plan = ((1, 0.), 3, "over_out")
    over = WP.WaypointGoal(40., 160, "out", 1, plan, over=(35., 3., 37., 7.))
    def unscannable(path, limit=None):
        raise GeometryUnavailable("path leaves modeled canvas")
    geo = NS(scan_delayed=unscannable)
    assert chain._waypoint_delayed_ahead(_sim_at(30.), None, over, 100, 1.6, geo, kin.B_RIGHT, True) is None and not notes
    plain = WP.WaypointGoal(40., 160, "retreat", 1, plan)
    sim = _sim_at(30.)
    from ssbot.combat.knife_chain_commitment import MoveInstance
    p = NS(iid=1, move=MoveInstance(1, 0, WP.FAMILY), origin=0, entry_k=0, press_k=None, contact_frame=None)
    assert chain._waypoint_delayed_ahead(sim, p, plain, 0, 0., geo, kin.B_RIGHT, True) is None
    assert notes == [dict(event="waypoint_route_unchecked", frame=0, reason="path leaves modeled canvas", active=True)]
    # a long route is scanned within the support's own look-ahead (its last sample): no raster rebuilt for it each tick
    seen = []
    def scan(path, limit=None):
        seen.append((len(path.commands), limit))
        return NS(contacts=())
    far = WP.WaypointGoal(45., 160, "retreat", 1, plan)
    assert chain._waypoint_delayed_ahead(sim, p, far, 0, 0., NS(forecast=NS(rs=NS(samples=(0, 31, 62))), scan_delayed=scan),
                                         kin.B_RIGHT, True) is None
    assert seen and seen[0][0] > 62 and seen[0][1] == 62
    # no route from the key sent (nowhere to arrive): noted, nothing concluded
    notes.clear()
    nowhere = WP.WaypointGoal(200., 160, "retreat", 1, plan)
    assert chain._waypoint_delayed_ahead(sim, p, nowhere, 0, 0., geo, kin.B_RIGHT | kin.B_DASH, True) is None
    assert notes == [dict(event="waypoint_route_unchecked", frame=0, reason="no route from the key sent", active=True)]


# Sol seq 272: bombs only one of the two routes from 30 -> 39 (f100, by_f 132) meets, look-ahead frames from the origin f: the dash
# is at 36.0-39.2 over keys 14-26 and the run never past 34.95 in its 38 keys; the run is at 32.5-33.3 over keys 18-24 while the dash
# is at 37.2-38.8 (key k acts at origin frame k + 2). Mirrored about 34.5.
DASH_ONLY, RUN_ONLY = (38., 16, 30), (31., 20, 26)


def _mirrored(bomb, mirror):
    return (69. - bomb[0], bomb[1], bomb[2]) if mirror else bomb


@pytest.mark.parametrize("mirror", [False, True])
def test_a_refused_dash_is_no_part_of_the_route_the_run_is_checked_on(monkeypatch, mirror):
    x0, gx, key = (39., 30., kin.B_LEFT) if mirror else (30., 39., kin.B_RIGHT)
    dash_only, run_only = _mirrored(DASH_ONLY, mirror), _mirrored(RUN_ONLY, mirror)
    def offer(lock, bomb):
        return _offer(monkeypatch, x0, gx, bombs=[bomb], by=32, lock=lock)
    # its lock refused the dash: the key sent is the direction alone and the route checked is its run
    out, chain = offer("refuse", dash_only)                      # a bomb only the refused dash would meet: no conclusion from it
    assert out is not None and out.mask == key and any(n["event"] == "waypoint_dash_refused" for n in chain.notes)
    assert not any(n["event"] == "waypoint_rejected" for n in chain.notes)
    # Sol seq 276: the run it sends instead hands back at next_mask's "late" (113, its last key on f114): a bomb on that run before it
    # still refuses the start (32.7, lit look-ahead 7..10: f107-110); one met only after it (35.0, lit 20..26: f120-126) does not
    out, chain = offer("refuse", _mirrored((32.7, 7, 10), mirror))
    note = next(n for n in chain.notes if n["event"] == "waypoint_rejected")
    assert out is None and note["reason"] == "route meets a delayed hazard" and 107 <= note["first"]["frame"] <= 110
    out, chain = offer("refuse", _mirrored((35., 20, 26), mirror))
    assert out is not None and out.mask == key and not any(n["event"] == "waypoint_rejected" for n in chain.notes)
    out, chain = offer("refuse", run_only)                       # (the run it sends meets this one only after 113 too)
    assert out is not None and not any(n["event"] == "waypoint_rejected" for n in chain.notes)
    # the dash passes its lock: the route checked is the dash it sends
    out, chain = offer("pass", dash_only)
    note = next(n for n in chain.notes if n["event"] == "waypoint_rejected")
    assert out is None and note["reason"] == "route meets a delayed hazard" and 116 <= note["first"]["frame"] <= 130
    out, chain = offer("pass", run_only)
    assert out is not None and out.mask == key | kin.B_DASH and not any(n["event"] == "waypoint_rejected" for n in chain.notes)


def _held_dash(x0, gx, by_f, ticks=3, f0=100):
    """A dash under way: next_mask frame by frame through the model from rest (as the Run, its lock passing), `ticks` ticks on.
    (sim at f0 + ticks: her state, the in-flight held DASH key, the hold state)."""
    from ssbot.combat.air_chain import ChainSim
    from ssbot.combat.holdfilter import hold_filter_jit
    from ssbot.combat.knife_chain_waypoint import WaypointGoal, next_mask
    S, hold, sent = hero_state(x0), kin.HoldState.idle(1), [0]
    goal = WaypointGoal(gx, by_f, "retreat", 1, ((1, 0.), 1, "attack_retreat"))
    for f in range(f0, f0 + ticks):
        prefix = np.array([sent[-1]], np.int64)
        mask, _ = next_mask(ChainSim(S, prefix, hold, PARAMS, TERRAIN, f, f), goal, f)
        sent.append(int(mask))
        lat, hold = hold_filter_jit(prefix[None], hold)
        S = np.asarray(kin.rollout(S, lat, PARAMS, TERRAIN).final[:, 0], np.float64)
    f = f0 + ticks
    return ChainSim(S, np.array([sent[-1]], np.int64), hold, PARAMS, TERRAIN, f, f)


@pytest.mark.parametrize("mirror", [False, True])
def test_an_active_held_dash_is_checked_from_its_held_key_through_its_release(monkeypatch, mirror):
    x0, gx, key = (39., 30., kin.B_LEFT) if mirror else (30., 39., kin.B_RIGHT)
    sim = _held_dash(x0, gx, 132)
    assert int(sim.prefix[0]) == key | kin.B_DASH                 # the dash is under way, its key in flight
    dash_only = _mirrored(DASH_ONLY, mirror)
    # still under the held dash when that bomb lights: the Run is handed back (no lock scan for a held dash)
    out, chain = _offer(monkeypatch, x0, gx, bombs=[(dash_only[0], dash_only[1] - 3, dash_only[2] - 3)], by=29, f=103,
                        active=True, sim=sim)
    assert out is None and chain.recovered == [("waypoint route meets a delayed hazard", 103)]
    assert not any(n["event"] in ("waypoint_dash_refused", "waypoint_dash_checked") for n in chain.notes)
    # lit only after her release, arrival and the next owner's first key: this Run goes on holding its dash
    out, chain = _offer(monkeypatch, x0, gx, bombs=[(gx, 40, 50)], by=29, f=103, active=True, sim=sim)
    assert out is not None and out.mask == key | kin.B_DASH and not chain.recovered


def test_the_delayed_scan_is_the_delayed_part_of_the_full_scan():
    # scan_delayed (the Run's whole-route check) = scan's delayed contacts, same frames and order, on paths through a support with
    # bombs of two owners and another enemy's body
    from ssbot.combat.air_chain import ChainSim
    from ssbot.combat.knife_chain_air import model_path
    from ssbot.combat.knife_chain_commitment import MoveInstance
    from ssbot.combat.knife_chain_geometry import B2Geometry
    sim = ChainSim(hero_state(30.), np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, TERRAIN, 100, 100)
    cy = float(sim.roll(np.zeros((1, 1), np.int64)).centre[0, 0, 1])
    rs = _bomb_support((2, 33., cy - .9, 2.166, 8, 20), (3, 36., cy - .9, 2.166, 14, 30), (2, 31., cy + 1.5, 2.166, 4, 9),
                       body=(34.5, 0., 35.5, 9.))
    move = MoveInstance(1, 95, "WAYPOINT")
    geo = B2Geometry(NS(rs=rs), 100, move, None)
    plan = NS(iid=1, move=move, origin=100, entry_k=0, press_k=None, contact_frame=None)
    rows = (np.full(40, kin.B_RIGHT), np.full(40, kin.B_RIGHT | kin.B_DASH), np.r_[np.full(12, kin.B_RIGHT | kin.B_JUMP), np.zeros(28)],
            np.r_[np.full(6, kin.B_RIGHT), np.full(34, kin.B_LEFT)])
    seen = 0
    for keys in rows:
        path = model_path(sim, plan, np.asarray(keys, np.int64), 100 / 60.)
        for limit in (None, 20, 41):
            full = geo.scan(path, limit=limit)
            want = tuple(c for c in full.contacts if c.kind == "delayed")
            got = geo.scan_delayed(path, limit=limit)
            assert got.contacts == want and got.last_frame == full.last_frame
            seen += len(want)
    assert seen > 0 and any(c.kind == "body" for keys in rows
                            for c in geo.scan(model_path(sim, plan, np.asarray(keys, np.int64), 100 / 60.)).contacts)


# ---- the over route's near row: from the start she is really at ----

def _sim_at(x):
    from ssbot.combat.air_chain import ChainSim
    return ChainSim(hero_state(x), np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, TERRAIN, 0, 0)


def _overlap(sim, entry, box, direction, upto=None):
    """Her box meets the body before the contact frame (upto: its rollout index; the row's own press + 5 by default)."""
    from ssbot.combat import dslash
    key = kin.B_RIGHT if direction > 0 else kin.B_LEFT
    h, p, b = entry["h"], entry["p"], entry["before"]
    row = np.zeros(p + dslash.POST_F, np.int64)
    row[:h] |= kin.B_JUMP
    if b == "T":
        row[:p] |= key
    dslash.strike(row, p)
    row[p:] |= key
    ro = sim.roll(row[None])
    bx = ro.box[0, :(p + 6 if upto is None else upto + 1)]
    return bool(np.any((bx[:, 0] <= box[2]) & (bx[:, 2] >= box[0]) & (bx[:, 1] <= box[3]) & (bx[:, 3] >= box[1])))


@pytest.mark.parametrize("gap", [.4, .8, 1.2, 1.7, 2.25, 2.3, 2.44, 3., 3.5])
def test_a_clean_near_row_exists_from_these_gaps_where_the_table_row_clips_the_corner(gap):
    from ssbot.combat.knife_chain_vault_entry import clean_near_row
    x = 40.
    edge = x - .25 - gap
    box = (edge - 3.59, FLOOR_Y, edge, CP.BODY_TOP)
    sim = _sim_at(x)
    entry, diag = clean_near_row(sim, box, -1)
    assert entry is not None and diag["clean"] >= 1, diag
    assert not _overlap(sim, entry, box, -1, diag["contact_index"])


def test_the_table_row_itself_clips_where_the_clean_row_does_not():
    from ssbot.combat.knife_chain_vault_entry import clean_near_row
    x = 40.
    for gap in (.8, 1.2):                          # the replays' clipped entries (m_over 0.79 with press 4; press 8 at 1.2)
        edge = x - .25 - gap
        box = (edge - 3.59, FLOOR_Y, edge, CP.BODY_TOP)
        press = 4 if gap < 1. else 8
        assert _overlap(_sim_at(x), dict(h=14, p=press, before="T"), box, -1), gap
        entry, diag = clean_near_row(_sim_at(x), box, -1)
        assert entry is not None and not _overlap(_sim_at(x), entry, box, -1, diag["contact_index"]), gap


def test_a_start_with_no_clean_row_is_excluded_not_guessed():
    from ssbot.combat.knife_chain_vault_entry import clean_near_row
    x = 40.
    # her box already in the body: nothing clean
    box = (36., FLOOR_Y, 40.1, CP.BODY_TOP)
    entry, diag = clean_near_row(_sim_at(x), box, -1)
    assert entry is None and diag["status"] == "no_clean_row"
    # off the ground or in a dash: this entry does not claim them
    from ssbot.combat.air_chain import ChainSim
    air = np.asarray(kin.initial_state(PARAMS, x, FLOOR_Y + PARAMS.foot + 3., ground=False), np.float64)
    entry, diag = clean_near_row(ChainSim(air, np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, TERRAIN, 0, 0), (30., FLOOR_Y, 37., CP.BODY_TOP), -1)
    assert entry is None and diag["status"] == "unsupported_hero_state"
    # a walker closing on her: its motion counts, the row that was clean against the still body may not be
    edge = x - .25 - 1.2
    still, _ = clean_near_row(_sim_at(x), (edge - 3.59, FLOOR_Y, edge, CP.BODY_TOP), -1)
    walking, _ = clean_near_row(_sim_at(x), (edge - 3.59, FLOOR_Y, edge, CP.BODY_TOP), -1, walker_v=8.)
    assert still is not None and (walking is None or walking != still or walking["p"] <= still["p"])


def test_the_over_call_takes_no_air_strike_row_whose_box_enters_the_body_first(monkeypatch):
    from ssbot.combat import knife_chain_transfer as T
    from ssbot.combat.air_chain import ChainSim
    from ssbot.combat.knife_chain_format import MASK_NAMES as B
    # in the air beside the body, low, moving toward it: the toward row strikes from beside it
    y = FLOOR_Y + PARAMS.foot + 1.
    S = np.asarray(kin.initial_state(PARAMS, 40., y, vx=-6., ground=False), np.float64)
    sim = ChainSim(S, np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, TERRAIN, 0, 0)
    body = np.array([35.9, FLOOR_Y, 39.3, CP.BODY_TOP])
    plain = T.press_now_row(sim, body, 2, 0, B["L"])
    assert plain is not None
    masks = np.asarray(plain["masks"], np.int64)
    ro = sim.roll(masks[None])
    j = plain["contact_frame"]
    assert T.enters_body(ro.box[0], body, j)         # the row the table takes meets the body before its contact
    clean = T.press_now_row(sim, body, 2, 0, B["L"], clean=True)
    if clean is not None:
        ro = sim.roll(np.asarray(clean["masks"], np.int64)[None])
        assert not T.enters_body(ro.box[0], body, clean["contact_frame"])
    # the over call of a plan, and only that
    monkeypatch.setattr(CP, "ENABLED", False)
    assert not T.plan_over_call({"switch_stomp": True})
    monkeypatch.setattr(CP, "ENABLED", True)
    assert T.plan_over_call({"switch_stomp": True}) and not T.plan_over_call({"switch_stomp": False})


# ---- Sol seq 256: the way out and the waits at the landing as it stands; the jumper's new move; the same-tick bounce release ----

def _walker_geo():
    return dict(xa=14.01, xb=48.99, left=.25, right=.25, bodies={2: (17.25, 20.84)})


def _resolver(hx=22., arrives=True):
    r = object.__new__(CP.PlanRunner)
    r.hand = NS(known=True)
    r.last_stance = {}
    r._arrives = lambda sc, x, by: arrives
    tac = NS(rune={}, rules=NS(face_u=4.), _ent=lambda ws, i: None)
    sc = NS(tac=tac, ws=None, t=0., hx=hx, geo=_walker_geo())
    o = NS(iid=2, pos=(19.5, 3.), state="Idle", family=None)
    return r, sc, o


def _plain(plan):
    # the same route written for a plain jump: its hammer's reach
    return replace(plan, detail=tuple((k, {"family": "CC_JUMP", "reach": 7.76}.get(k, v)) for k, v in plan.detail))


def _out_plan(prepared=("over",), land=32.4844):
    # the replay k_over_out's geometry: the walker at 19.5 (body 17.25-20.84), far stance 16.05
    J = body(1, 39.44, "Air", "CC_JUMP_CAST", facing=-1)
    plan = plan_of(request(J=J, W=body(2, 19.5), hx=22., stage="flight", antic_at=None, land=land, land_vx=-5.45, air_at=0.))
    assert cand(plan, "over").feasible and cand(plan, "over").get("follow") == "out" and plan.phase("over_head").after("bounced") == "over_out"
    return replace(plan, detail=tuple((k, prepared if k == "prepared" else v) for k, v in plan.detail))


def test_the_way_out_is_judged_at_the_observed_landing_and_body():
    plan = _out_plan()
    r, sc, o = _resolver()
    assert plan.get("reach") == pytest.approx(CP.RUNE_REACH_U) and r._far_now(sc, plan, o) == pytest.approx(16.05)
    m = dict(face=-1, x0=39.44, air_at=0., vx=-8.)
    def route(land, runner=r):
        return runner._resolve_middle(sc, plan, None, o, dict(m, land=land))[0]
    # as predicted: its far side is past the whole rune: there
    assert r._out_x(sc, plan, o, 32.4844) == pytest.approx(16.05)
    assert route(32.4844) == "over"
    # Sol's counterexample: 2.75 u nearer, still inside the 3 u support: 16.05 is 0.50 u inside the rune plus her half width (15.5474):
    # the stance is the place past it, not the aim's
    x = r._out_x(sc, plan, o, 29.7344)
    assert 14.01 <= x <= 29.7344 - CP.RUNE_REACH_U - .25
    assert route(29.7344) == "over"
    # no such place inside the wall: not the route; the prepared and supported successor, else explicitly blocked
    nearer = _out_plan(land=31.)
    assert r._out_x(sc, nearer, o, 28.3) is None
    res = r._resolve_middle(sc, nearer, None, o, dict(m, land=28.3))
    assert res[0] == "blocked" and "no prepared route" in res[1]
    both = replace(nearer, detail=tuple((k, ("under", "over") if k == "prepared" else v) for k, v in nearer.detail))
    assert r._resolve_middle(sc, both, None, o, dict(m, land=28.3))[0] == "under"
    # it cannot get there in time: not the route either
    late, _, _ = _resolver(arrives=False)
    assert late._resolve_middle(sc, plan, None, o, dict(m, land=29.7344))[0] == "blocked"
    # a plain jump: the hammer is what its way out must clear
    plain = _plain(plan)
    assert r._out_x(sc, plain, o, 27.) == pytest.approx(16.05)
    assert r._out_x(sc, plain, o, 23.5) == pytest.approx(23.5 - 7.76 - .25)


def test_a_landing_tracked_nearer_takes_the_stance_it_is_not_kept_as_safe():
    plan = _out_plan()
    r, sc, o = _resolver()
    s = NS(iid=1, family="CC_JUMP_CAST", state="Air", pos=(35., 9.))
    sc.subjects = [s, o]
    sc.grounded = False
    r.exec = PlanExecutor()
    r.exec.plan, r.exec.name, r.exec.status = plan, "over_out", "waiting"
    r.last_stance, r.notes = {}, []
    r.moves = {1: dict(air_at=0., land=32.4844, land_seen=None, vx=-8.)}
    phase = plan.phase("over_out")
    assert "stance_lost" not in r._events(sc, phase)
    assert r.stance(sc, phase) == pytest.approx(16.05)
    r.moves[1]["land"] = 29.7344                     # sharper: a place farther out still exists: the stance moves there
    assert "stance_lost" not in r._events(sc, phase)
    assert r.stance(sc, phase) <= 29.7344 - CP.RUNE_REACH_U - .25
    r.moves[1]["land"] = 28.3                        # none left: the stage ends, explicitly
    assert "stance_lost" in r._events(sc, phase) and phase.after("stance_lost") == BLOCKED
    assert r.notes[-1]["what"] == "stance lost" and r.notes[-1]["landing"] == 28.3
    # the head: with the hammer now over it
    stay = replace(plan, detail=tuple((k, "stay" if k == "follow" else v) for k, v in plan.detail))
    r.moves[1]["land"] = 32.4844
    assert not r._stance_lost(sc, stay, stay.phase("over_stay"), o, r.moves[1])
    r.moves[1]["land"] = 27.
    assert r._stance_lost(sc, stay, stay.phase("over_stay"), o, r.moves[1])
    # its ordinary reaction to the hit moves its head for a moment: judged once it stands again
    o.state = "Evade Scuttle"
    assert not r._stance_lost(sc, stay, stay.phase("over_stay"), o, r.moves[1])
    o.state = "Idle"
    # the stand and the place behind: the same
    assert plan.phase("return").after("stance_lost") == BLOCKED and plan.phase("under").after("stance_lost") == BLOCKED
    # a place she fits in is still a place, past the margin the route was chosen with (replay k_stay: 1.97 u against 2)
    r.moves[1]["land"] = 37.24
    assert r._stand_now(sc, plan, o, r.moves[1]) is None and r._stand_now(sc, plan, o, r.moves[1], gap=0.) is not None
    assert not r._stance_lost(sc, plan, plan.phase("return"), o, r.moves[1])
    r.moves[1]["land"] = 35.2                        # no room between the walker and the coverage at all
    assert r._stance_lost(sc, plan, plan.phase("return"), o, r.moves[1])
    r.moves[1]["land"] = 47.                         # no room behind it at the wall
    assert r._stance_lost(sc, plan, plan.phase("under"), o, r.moves[1])
    # the phases keep their order: the hazard over first
    assert [e for e, _ in phase.on].index("hazard_over") < [e for e, _ in phase.on].index("stance_lost")


def test_after_the_over_routes_strike_no_new_plan_asks_a_second_one(monkeypatch):
    def run(bounced):
        tac, ws, fc = planned(monkeypatch)
        go_(tac, ws, fc)
        antic(tac, ws, fc)
        go_(tac, ws, fc); go_(tac, ws, fc)
        r = tac.plan_runner
        ex = r.exec
        inst = ex.plan.instance
        if bounced:
            ex.record(inst, "bounced", ws.stamp.t_game_s)
        ex.end("blocked", "stance_lost", ws.stamp.t_game_s)
        n = r.requests
        take_off(tac, ws, fc)
        go_(tac, ws, fc)
        return r.requests - n
    assert run(False) == 1
    assert run(True) == 0


def _moved(plan, name, t, land_seen=1.):
    r = object.__new__(CP.PlanRunner)
    r.exec, r.notes = PlanExecutor(), []
    r.moves = {plan.instance[0]: dict(antic_at=None, land_seen=land_seen)}
    r.exec.plan, r.exec.name, r.exec.status = plan, name, "waiting"
    sc = NS(t=t, hx=16., mem={}, subjects=[], frame=100)
    CP.PlanRunner._jumper_moved(r, sc, plan, NS(iid=plan.instance[0], family="CC_SLAM", state="Slam Antic"))
    return r, sc


def test_the_jumpers_new_move_finishes_only_what_is_finished():
    cast = _out_plan()
    due, over = 1. + CP.RUNE_OVER_S - .3, 1. + CP.RUNE_OVER_S + .1
    # its rune still due: the stages that keep her off it go on, the new threat takes its turn by the public rule scores
    for name in ("over_head", "over_stay", "over_out", "return"):
        r, sc = _moved(cast, name, due)
        assert r.exec.plan is cast and r.exec.name == name and r.exec.status == "waiting", name
        assert "back" not in sc.mem
    # any other stage stops, not as a success; nothing to return from
    r, sc = _moved(cast, "under", due)
    assert r.exec.plan is None and r.exec.status == "interrupted" and "back" not in sc.mem
    # the rune over: the way back not made is handed on
    r, sc = _moved(cast, "over_back", over)
    assert r.exec.status == "handed_back" and sc.mem["back"]["iid"] == 1 and any(x["what"] == "return kept" for x in r.notes)
    r, sc = _moved(cast, "under", over)
    assert r.exec.status == "complete" and "back" not in sc.mem
    # a plain jump: its hazard is over with the new move
    plain = _plain(cast)
    r, sc = _moved(plain, "over_wait", 1.2)
    assert r.exec.status == "handed_back" and sc.mem["back"]["family"] == "CC_JUMP"
    r, sc = _moved(plain, "return", 1.2)
    assert r.exec.status == "complete" and "back" not in sc.mem


def test_a_plan_expiring_on_its_way_back_keeps_the_return():
    plan = _out_plan()
    r = object.__new__(CP.PlanRunner)
    r.exec, r.notes, r.pending_info = PlanExecutor(), [], None
    r.moves = {1: dict(antic_at=None)}
    r.exec.plan, r.exec.name, r.exec.status = plan, "over_back", "waiting"
    r.exec.end("expired", "past the plan's validity", 5.)
    sc = NS(t=5., hx=16., mem={}, subjects=[], frame=100)
    r._after_step(sc, plan, "over_back")
    assert sc.mem["back"]["iid"] == 1
    sc = NS(t=5., hx=16., mem={}, subjects=[], frame=100)
    r._after_step(sc, plan, "under")
    assert "back" not in sc.mem


def _bounce_chain(family="VAULT_IDLE", f=120, target_state="Idle"):
    from ssbot.combat import knife_chain_air_native as AN
    from ssbot.combat import knife_chain_transfer as T, two_play as TP
    from ssbot.combat.knife_chain_commitment import MoveInstance
    cls = next(c for c in vars(AN).values() if isinstance(c, type) and "_waypoint_offer" in vars(c))
    chain = object.__new__(cls)
    move = MoveInstance(7, 100, family)
    chain.arm, chain.recovery, chain.commitment, chain._wall_pressure = "B", None, None, None
    chain.post_context = dict(move=move, bounce=120, hit=120, press=118)
    chain._hit = 120
    chain._clock, chain._clock_known = 2., False
    chain.runner = NS(run=NS(chain="vault_idle", link="near", lid="vault_idle.near", v={}))
    chain._vault_responsibility = {move: (MoveInstance(8, 100, "CC_JUMP"), 1.)} if family == "VAULT_IDLE" else {}
    chain._transfer_responsibility, chain._transfer_target_moves = {}, {}
    def clapper(iid, x, st):
        return dict(iid=iid, type_key=TP._sp.CLAPPER, pos=[x, 3.], hp=100,
                    fsms=[dict(name="Control", state=st, t=.2)],
                    colliders=[dict(name="Song Heavy Sentry (2)", enabled=True)])
    state = dict(f=f, hero=dict(health=5), ev=[], ents=[clapper(7, 20., target_state), clapper(8, 40., "Air")])
    return chain, state, move, T


def test_this_ticks_real_bounce_releases_the_strike_along_the_path_that_takes_it():
    from ssbot.combat.knife_chain_commitment import MoveInstance
    chain, state, move, T = _bounce_chain()
    assert len(T.clappers(state)) == 2
    # the same tick: observe has released the commitment, the Run is still there until this tick's goal step
    assert chain.runner.run is not None and chain.commitment is None
    assert chain.own_bounce_released(state) and chain.key_commitment(state) is None
    # a later tick with the Run still on: nothing says it is free
    chain, state, move, T = _bounce_chain(f=121)
    assert not chain.own_bounce_released(state) and chain.key_commitment(state) == ("vault_idle.near", False, ())
    # an older post of the same Clapper, not this strike's hit
    chain, state, move, T = _bounce_chain()
    chain._hit = 119
    assert chain.key_commitment(state) == ("vault_idle.near", False, ())
    # a commitment still held, a recovery: not this path
    chain, state, move, T = _bounce_chain()
    chain.commitment = dict(move=move)
    assert chain.key_commitment(state)[1] is False
    chain, state, move, T = _bounce_chain()
    chain.recovery = dict(first=120)
    assert chain.key_commitment(state) == ("b2 recovery", False, ())
    # no parent move to bind: that path binds no goal and the Run stays
    chain, state, move, T = _bounce_chain()
    chain._vault_responsibility = {}
    assert chain.key_commitment(state) == ("vault_idle.near", False, ())
    # the struck one slamming: the old hammer tail goes on: still a holder
    chain, state, move, T = _bounce_chain(family="RUNE_TRANSFER", target_state="Slam 1")
    chain._transfer_target_moves = {move: (MoveInstance(7, 95, "CC_SLAM"), 1.)}
    chain._transfer_responsibility = {move: (MoveInstance(8, 100, "CC_CAST"), 1.)}
    assert not chain.own_bounce_released(state)
    assert chain.key_commitment(state) == ("vault_idle.near", False, ())
    # the same strike on an Idle one (its responsibility another move): released
    chain, state, move, T = _bounce_chain(family="RUNE_TRANSFER")
    chain._transfer_responsibility = {move: (MoveInstance(8, 100, "CC_JUMP"), 1.)}
    assert chain.own_bounce_released(state)


def test_the_plan_commitment_takes_the_release_and_keeps_every_other_holder():
    from ssbot.train import forum_planner_policy as P
    active, idle = NS(active=lambda: True), NS(active=lambda: False)
    seen = []
    def commit(released, slam=None, low=None, two=None, chain=None, ground=None):
        native = NS(own_bounce_released=lambda s: released, key_commitment=lambda s, ground=None: seen.append(ground) or chain)
        return P.ForumPlannerPolicy._plan_commitment(NS(slam_play=slam, claw=None, cast_stab=None, rune_lowhop=low, evade_chase=None, two=two,
                                                        chain_native=native), 120, {}, ground)
    assert commit(True, slam=active) is None                        # a slam run left over before the chain took the keys: released with it
    assert commit(False, slam=active) == ("slam", False, ())
    assert commit(True, low=active) == ("low", False, ())           # another script holding keys is another holder
    assert commit(False, two=NS(last_part="esc")) == ("two esc", False, ())  # the wall switch's running hop: on in the tested configuration
    assert commit(False, two=NS(last_part="idle"), slam=idle) is None        # its watch, an idle hit: no hold
    assert commit(False, chain=("x", True, (1, 2))) == ("x", True, (1, 2))
    # seq 270: the chain reads this STATE's ground flag, the one its own tick gets (an owned follow-up landing is released on it)
    seen.clear()
    commit(False, ground=True)
    commit(False, ground=False)
    assert seen == [True, False]


@pytest.mark.parametrize("flag", ["ANTICSWITCH", "EARLY", "JUMPHIT", "RUNETIER", "FLIPB", "SP11B", "RUNEEXIT"])
def test_a_key_script_outside_the_tested_set_is_refused_at_startup(monkeypatch, flag):
    from ssbot.train import forum_planner_policy as P
    monkeypatch.setattr(P.clapper_plans, "ENABLED", True)
    plain = NS(tac=object())
    assert P.ForumPlannerPolicy._prepare_plans(plain) is None        # the tested configuration: on to the worker (no tactics here: stops there)
    monkeypatch.setattr(P.two_play, flag, True)
    with pytest.raises(ValueError, match="not tested"):
        P.ForumPlannerPolicy._prepare_plans(plain)
    monkeypatch.setattr(P.clapper_plans, "ENABLED", False)
    assert P.ForumPlannerPolicy._prepare_plans(plain) is None        # flag off: nothing changes


def test_map2_and_the_air_show_are_outside_the_tested_set_too(monkeypatch):
    from ssbot.train import forum_planner_policy as P
    monkeypatch.setattr(P.clapper_plans, "ENABLED", True)
    plain = NS(tac=object())
    monkeypatch.setattr(P, "MAP2", True)
    with pytest.raises(ValueError, match="MAP2"):
        P.ForumPlannerPolicy._prepare_plans(plain)
    monkeypatch.setattr(P, "MAP2", False)
    monkeypatch.setattr(P.air_show, "AIRSHOW", True)
    with pytest.raises(ValueError, match="AIRSHOW"):
        P.ForumPlannerPolicy._prepare_plans(plain)


def test_stats_keep_the_denominators_of_the_latency(monkeypatch):
    tac, ws, fc = planned(monkeypatch)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    go_(tac, ws, fc); go_(tac, ws, fc)
    st = tac.plan_runner.stats()
    assert st["counts"]["results"] == 1 and st["counts"]["adopted"] == 1 and st["adopted"] == 1
    assert st["event_to_validated_ms"]["p50"] is not None and st["event_to_adopted_ms"]["max"] >= st["event_to_validated_ms"]["p50"]
    assert st["pending_wait_ms"]["n"] == 0


def test_over_waits_out_of_the_landing_hammer_or_is_no_route():
    # the walker past the hammer's reach: its head; inside it with the far side out: the far side; both inside: not offered
    J = body(1, 25., "Air", "CC_JUMP", facing=1)
    def over(wx, hx, air_at=0.):
        return cand(plan_of(request(J=J, W=body(2, wx), hx=hx, stage="flight", antic_at=None, land=30., land_vx=5.45, air_at=air_at)), "over")
    assert over(40., 36.).get("follow") == "back"
    near = over(36.5, 36.)                         # head at 36.5 inside 38.01; far side 36.5 + 1.34 + 1.2 = 39.04 outside
    assert near.feasible and near.get("follow") == "out"
    assert not over(33.5, 31.5).feasible and "coverage" in over(33.5, 31.5).reason
    # out is a passage above its body after the strike: no time for it before the hammer, no such route
    late = over(36.5, 29.)
    assert not late.feasible and "coverage" in late.reason


def test_no_standing_gap_at_the_take_off_runs_the_prepared_route_farther_from_the_wall(monkeypatch):
    # a short jump: behind its landing is near the wall, over the walker is far from the other one: the same plan runs over, no request
    tac, ws, fc = planned(monkeypatch, xs=(19., 31.5), hx=27.)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    go_(tac, ws, fc); go_(tac, ws, fc)
    r = tac.plan_runner
    plan = r.exec.plan
    assert plan is not None and "over" in plan.get("prepared")
    land = plan.get("landings")[0]
    change(fc, 8, pos=(30., fc.subjects[1].pos[1]))     # the walker a step closer at the take-off: no standing gap
    ws.entities[1].dmg_boxes[0].poly = [(29., 3.), (31., 3.), (31., 7.), (29., 7.)]
    take_off(tac, ws, fc, vx=(land - 19.) / CP.GAIN)
    n = r.requests
    out = go_(tac, ws, fc)
    note = next(x for x in plan_notes(tac) if x["what"] == "takeoff")
    assert note["route"] == "over" and "closed" in note["reason"], note
    assert r.exec.plan is plan and r.exec.name == "over_head" and r.requests == n
    assert out.target == 8 and out.entry_attack.kind == "stomp"
def test_the_walker_closes_the_gap_and_the_prepared_under_runs_by_wall_room(monkeypatch):
    # the walker closes the gap at the take-off, under ends farther from the wall than over: the same plan runs it, no request
    tac, ws, fc = planned(monkeypatch, xs=(30., 45.), hx=37.)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    go_(tac, ws, fc); go_(tac, ws, fc)
    r = tac.plan_runner
    plan = r.exec.plan
    assert plan.selected == "stay" and set(plan.get("prepared")) == {"under", "over"}
    change(fc, 8, pos=(43., fc.subjects[1].pos[1]), state="Walk")
    ws.entities[1].dmg_boxes[0].poly = [(42., 3.), (44., 3.), (44., 7.), (42., 7.)]
    take_off(tac, ws, fc, vx=3.)
    n = r.requests
    out = go_(tac, ws, fc)
    note = next(x for x in plan_notes(tac) if x["what"] == "takeoff")
    assert note["route"] == "under" and "closed" in note["reason"]
    assert r.exec.plan is plan and r.exec.name == "under" and r.requests == n
    assert out.target == 7 and out.stance_x < note["landing"]
    # the action layer is told where and by when
    assert out.waypoint is not None and out.waypoint.kind == "under" and out.waypoint.x == pytest.approx(out.stance_x)

def test_the_route_with_the_farther_wall_is_the_one_chosen():
    # both feasible in flight: under ends behind the landing, over on the walker's far side; the wall decides, in both directions
    J = body(1, 40., "Air", "CC_JUMP", facing=-1)
    plan = plan_of(request(J=J, W=body(2, 30.), hx=35., stage="flight", antic_at=None, land=39., land_vx=-5.45, air_at=0.))
    under, over = cand(plan, "under"), cand(plan, "over")
    assert under.feasible and over.feasible and under.get("wall_room") < over.get("wall_room") and plan.selected == "over"
    J = body(1, 30., "Air", "CC_JUMP", facing=-1)
    plan = plan_of(request(J=J, W=body(2, 20.), hx=25., stage="flight", antic_at=None, land=29., land_vx=-5.45, air_at=0.))
    under, over = cand(plan, "under"), cand(plan, "over")
    assert under.feasible and over.feasible and under.get("wall_room") > over.get("wall_room") and plan.selected == "under"


def test_a_walker_step_inside_the_soft_range_asks_nothing_and_past_it_asks_once(monkeypatch):
    tac, ws, fc = planned(monkeypatch, delay=4)  # the update takes a while: the old plan keeps running past its soft range
    go_(tac, ws, fc)
    antic(tac, ws, fc, family=G.CC_JUMP_CAST, state="Cast Slam Antic")
    r = tac.plan_runner
    for _ in range(8):
        go_(tac, ws, fc)
        if r.exec.plan is not None:
            break
    n = r.requests
    assert r.exec.plan is not None and r.exec.plan.get("walker_v") in (0., None)
    # a real step (past the repeat step) still inside the plan's soft range: no change for the plan
    change(fc, 8, pos=(39. - (CP.REQUEST_STEP_U + .1), fc.subjects[1].pos[1]))
    for _ in range(3):
        go_(tac, ws, fc)
    assert r.requests == n
    # past the soft range: one request; a further small motion there asks nothing new
    change(fc, 8, pos=(39. - (CP.SOFT_WALKER_U + .1), fc.subjects[1].pos[1]))
    go_(tac, ws, fc)
    assert r.requests == n + 1
    for k in range(2):
        change(fc, 8, pos=(39. - (CP.SOFT_WALKER_U + .15 + .05 * k), fc.subjects[1].pos[1]))
        go_(tac, ws, fc)
        assert r.requests == n + 1


def test_a_flight_plan_with_no_route_is_an_explicit_no_plan_in_the_tick(monkeypatch):
    # seen in flight, the jump landing past the walker: none of this scene's routes; no exception in the tick, the generic rules
    tac, ws, fc = planned(monkeypatch, xs=(19., 29.), hx=25.)
    go_(tac, ws, fc)
    change(fc, 7, family=G.CC_JUMP, state="Air", committed=True)
    tac.t_commit[7] = ws.stamp.t_game_s
    ws.entities[0].fsm = [("Control", "Air", .02)]
    ws.entities[0].flip_x = True
    ws.entities[0].vel = E((12., 30.))         # it lands at 29.99, past the walker's root
    seen = []
    for _ in range(3):
        go_(tac, ws, fc)
        seen += plan_notes(tac)
    r = tac.plan_runner
    assert any(n["what"] == "result" and n["state"] == "none" for n in seen)
    # no 95-point empty route: the generic rules answer (here the kept intercept trigger, a jump coming from behind her)
    assert tac.last["clapper_winner"]["rule"] != "middle_jump"
    assert r.exec.plan is None or r.exec.plan.scene == "intercept"


def test_an_observed_landing_outside_the_plans_support_asks_for_a_new_plan_from_it(monkeypatch):
    tac, ws, fc = planned(monkeypatch, xs=(19., 44.), hx=30.)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    go_(tac, ws, fc)
    go_(tac, ws, fc)                             # the plan, published one tick after its request
    r = tac.plan_runner
    planned_x = r.exec.plan.get("landings")
    assert planned_x
    take_off(tac, ws, fc, vx=-2.)                # lands behind where any of the plan's aims would have sent it
    go_(tac, ws, fc)
    note = next(x for x in plan_notes(tac) if x["what"] == "takeoff")
    assert note["route"] == "blocked" and "support" in note["reason"]
    assert any(x["what"] == "request" and x["stage"] == "flight" for x in plan_notes(tac))
    go_(tac, ws, fc)                             # the new plan from the observed landing, one tick on
    assert r.exec.plan is not None and r.exec.plan.get("stage") == "flight"


def test_a_pending_plan_is_checked_by_its_own_instance_when_the_active_one_is_gone(monkeypatch):
    # Root's probe: through the adapter, with no plan active the pending one must not be dropped as stale
    tac, ws, fc = planned(monkeypatch, delay=3)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    r = tac.plan_runner
    ex = r.exec
    for _ in range(8):
        go_(tac, ws, fc)
        if ex.plan is not None:
            break
    first = ex.plan
    assert first is not None
    # a newer plan is on its way (the walker started walking); the take-off comes first: past the boundary it must wait
    change(fc, 8, state="Walk")
    go_(tac, ws, fc)
    take_off(tac, ws, fc, vx=9.)
    go_(tac, ws, fc)
    assert ex.plan is first and not ex.phase.replaceable
    for _ in range(4):
        go_(tac, ws, fc)
        if ex.pending is not None:
            break
    assert ex.pending is not None and ex.pending.generation > first.generation
    newer = ex.pending
    # the running route ends (no plan active): the waiting plan is checked on its own instance and its own prediction, and taken
    ex.end("invalid", "the route ended", ws.stamp.t_game_s)
    go_(tac, ws, fc)
    assert ex.plan is newer and not any(x["what"] == "rejected" for x in plan_notes(tac))
    st = r.stats()
    assert st["counts"]["pending"] == 1 and st["counts"]["pending_adopted"] == 1 and st["pending_wait_ms"]["n"] == 1


def test_a_cluster_result_arriving_on_the_take_off_tick_takes_the_take_off_on_that_tick(monkeypatch):
    # Root's probe: the public selector chooses at the very tick the first result comes with the jump already off
    for off, want in ((True, "attack_retreat"), (False, "attack_aim")):
        tac, ws, fc = planned(monkeypatch, xs=(36., 37.), hx=29., delay=2)
        go_(tac, ws, fc)
        antic(tac, ws, fc)
        go_(tac, ws, fc)
        r = tac.plan_runner
        ex = r.exec
        if off:
            take_off(tac, ws, fc, face=-1, vx=-3.)
        for _ in range(4):                         # the first result comes on a tick with the jump already off
            out = go_(tac, ws, fc)
            if ex.plan is not None:
                break
        assert ex.plan is not None and ex.selected in ("attack", "lure")
        if off:
            assert ex.name in ("attack_retreat", "lure_return"), ex.name
            assert any(x["what"] == "takeoff" for x in plan_notes(tac))
            assert out.target == ex.phase.target
        else:
            assert ex.name in ("attack_aim", "lure_hold", "lure_wait", "lure_go"), ex.name


def test_a_real_bounce_advances_the_over_route_and_a_hit_alone_does_not(monkeypatch):
    tac, ws, fc = planned(monkeypatch)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    go_(tac, ws, fc); go_(tac, ws, fc)
    r = tac.plan_runner
    ex = r.exec
    ex.name = "over_head"
    S = hero_state(35.)
    # a DownSlash hit in this STATE's events and no pogo evidence (plan_input.bounce None): no bounce
    from ssbot.core.worldstate import Ev
    assert not r._bounced(NS(tac=tac, ws=NS(events=(NS(kind=Ev.HIT_DEALT, data=NS(target_id=8, src="DownSlash")),))), NS(iid=8))
    go_(tac, ws, fc)
    assert ex.name == "over_head"
    # the real bounce on the OTHER Clapper is no bounce of this route
    tac.plan_input = CP.HeroInput(S, np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, TERRAIN, bounce=7)
    go_(tac, ws, fc)
    assert ex.name == "over_head"
    # the bounce on the walker, in its ordinary reaction to the hit: the route goes on, the reaction is no invalidation
    for reaction in ("Dmg Attack", "Evade Scuttle"):
        ex.name = "over_head"
        change(fc, 8, state=reaction)
        tac.plan_input = CP.HeroInput(S, np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, TERRAIN, bounce=8)
        go_(tac, ws, fc)
        assert ex.plan is not None and ex.name == "over_wait", reaction
        set_hero(tac, 35.)
        go_(tac, ws, fc)
        assert ex.plan is not None and ex.name == "over_wait", reaction
    # its new attack ends it
    change(fc, 8, family=G.CC_SLAM, state="Slam Antic", committed=True)
    go_(tac, ws, fc)
    assert ex.plan is None and ex.status == "invalid"


def test_the_cluster_retreat_needs_its_candidate_and_the_time_not_only_the_wall(monkeypatch):
    # Root's probe: a retreat of 23 u in a 0.916 s flight is no prepared route
    tac, ws, fc = planned(monkeypatch, xs=(40., 41.), hx=35.)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    go_(tac, ws, fc); go_(tac, ws, fc)
    r = tac.plan_runner
    ex = r.exec
    assert ex.plan is not None and ex.plan.scene == "cluster"
    assert cand(ex.plan, "attack").feasible
    ex.selected, ex.name = "attack", "attack_aim"
    plan = ex.plan
    take_off(tac, ws, fc, face=-1, vx=-12.)         # lands 11 u out: the coverage's far end is out of her reach in the flight
    ws.hero.pos = E((39., float(ws.hero.pos.v[1])))
    ws.hero.hurtbox = [(38.75, 4.), (39.25, 4.), (39.25, 6.), (38.75, 6.)]
    set_hero(tac, 39.)
    go_(tac, ws, fc)
    note = next(x for x in plan_notes(tac) if x["what"] == "takeoff")
    assert note["route"] == "blocked" and ("does not arrive" in note["reason"] or "in time" in note["reason"]), note
    assert ex.plan is None and ex.status == "blocked"
    # the lure's way back failed and the attack was never feasible: blocked, whatever fits inside the wall
    tac, ws, fc = planned(monkeypatch, xs=(40., 41.), hx=35.)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    go_(tac, ws, fc); go_(tac, ws, fc)
    r = tac.plan_runner
    ex = r.exec
    lure, attack = cand(ex.plan, "lure"), cand(ex.plan, "attack")
    ex.plan = replace(ex.plan, candidates=(lure, replace(attack, feasible=False, reason="not in this plan")))
    take_off(tac, ws, fc, face=-1, vx=-.1)
    ws.hero.pos = E((39., float(ws.hero.pos.v[1])))
    ws.hero.hurtbox = [(38.75, 4.), (39.25, 4.), (39.25, 6.), (38.75, 6.)]
    set_hero(tac, 39.)
    if ex.selected is None:
        ex.select("lure", ws.stamp.t_game_s)
    ex.name = "lure_hold"
    go_(tac, ws, fc)
    note = next(x for x in plan_notes(tac) if x["what"] == "takeoff")
    assert note["route"] == "blocked" and "no prepared retreat" in note["reason"], note


def test_the_retreat_counts_the_whole_coverage_not_only_the_hammer(monkeypatch):
    # past the hammer, inside the rune's coverage, and her owner keeps her until after it lights: no retreat
    tac, ws, fc = planned(monkeypatch, xs=(40., 41.), hx=35.)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    go_(tac, ws, fc); go_(tac, ws, fc)
    r = tac.plan_runner
    plan = r.exec.plan
    assert plan.scene == "cluster" and cand(plan, "attack").feasible
    cast = replace(plan, detail=tuple((k, {"family": "CC_JUMP_CAST", "reach": 13.937}.get(k, v)) for k, v in plan.detail))
    out, land = plan.get("out"), 33.
    assert out == -1
    x = land + out * (plan.get("reach_j") + plan.get("half_in") + .5)
    sc = NS(t=ws.stamp.t_game_s, hx=x, geo={"bodies": {}}, tac=tac)
    m = dict(face=out, land=land, air_at=sc.t)
    o = ws.entities[1]
    monkeypatch.setattr(r, "_arrives", lambda *a: False)
    assert r._resolve_cluster(sc, cast, None, o, m, "attack") == ("blocked", "the retreat does not arrive before the hazard")
    monkeypatch.setattr(r, "_arrives", lambda *a: True)
    assert r._resolve_cluster(sc, cast, None, o, m, "attack")[0] == "retreat"


def test_the_stand_at_the_takeoff_reads_the_written_geometry_not_the_forecast_union(monkeypatch):
    tac, ws, fc = planned(monkeypatch, xs=(19., 44.), hx=30.)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    go_(tac, ws, fc)
    fc.default = 0.                              # the union covers everything near an idle Clapper: no answer about this stance
    take_off(tac, ws, fc, vx=10.)
    go_(tac, ws, fc)
    assert next(x for x in plan_notes(tac) if x["what"] == "takeoff")["route"] == "return"
    # a rune circle of the walker due over the stance is decided: not returned to
    tac, ws, fc = planned(monkeypatch, xs=(19., 44.), hx=30.)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    go_(tac, ws, fc)
    tac.rune[8] = (44., -1., "back off", ws.stamp.t_game_s + 5.)
    take_off(tac, ws, fc, vx=10.)
    go_(tac, ws, fc)
    note = next(x for x in plan_notes(tac) if x["what"] == "takeoff")
    assert note["route"] != "return" and "rune circle" in note["reason"]


@pytest.mark.parametrize("what", ["ground", "input"])
@pytest.mark.parametrize("build", ["middle", "cluster"])
def test_no_l2_candidate_changes_with_her_current_ground_or_input_flag(monkeypatch, what, build):
    """The same hand-back prediction: the flag alone changes no offer, no reason and no plan, in any tactic."""
    def run(flip):
        kw = dict(xs=(19., 39.), hx=35.) if build == "middle" else dict(xs=(36., 37.), hx=30.)
        tac, ws, fc = planned(monkeypatch, **kw)
        if flip and what == "ground":
            ws.hero.contact = E("AIR")
        if flip and what == "input":
            ws.hero.can = {"input": False, "dash": False, "harpoon": False}
            ws.hero.dash_cd_left = E(.2)
        go_(tac, ws, fc)
        antic(tac, ws, fc)
        rows = []
        for k in range(8):
            out = go_(tac, ws, fc)
            ev = tac.last.get("clapper_eval") or {}
            rows.append((tac.last["clapper_winner"], ev.get("tactics"), out.target, out.stance_x,
                         None if out.entry_attack is None else out.entry_attack.kind, tac.plan_runner.exec.name,
                         tac.plan_runner.exec.selected))
        return rows, tac.plan_runner.exec.plan

    a, plan_a = run(False)
    b, plan_b = run(True)
    assert a == b
    assert plan_a is not None and plan_a.candidates == plan_b.candidates and plan_a.selected == plan_b.selected


@pytest.mark.parametrize("flip", ["ground", "input"])
def test_the_other_tactics_ignore_her_flags_too_except_the_returns_landed_confirmation(monkeypatch, flip):
    """Every other unit, through one pick: the near threat, the return between them, the flip, the overhead. The only read of
    her ground flag left in L2 is MiddleReturn's completion (landed in the standing gap), never an admission."""
    from tests.test_middle_return313 import near_attack

    def run(flipped, xs, hx):
        tac, ws, fc = planned(monkeypatch, xs=xs, hx=hx)
        if flipped and flip == "ground":
            ws.hero.contact = E("AIR")
        if flipped and flip == "input":
            ws.hero.can = {"input": False, "dash": False, "harpoon": False}
        go_(tac, ws, fc)
        out = near_attack(tac, ws, fc)        # the shared helper steps the real entry
        return tac.last["clapper_winner"], tac.last["clapper_eval"]["tactics"], out.target, out.stance_x

    for xs, hx in (((20., 34.), 15.), ((20., 22.4), 21.2)):
        assert run(False, xs, hx) == run(True, xs, hx)


def test_the_generator_cannot_read_her_flags():
    names = set(CP.Request.__dataclass_fields__)
    assert not names & {"can", "contact", "grounded", "ground", "accepting", "input"}
    assert not set(CP.Hand.__dataclass_fields__) & {"can", "contact", "grounded", "accepting", "input"}
    import inspect
    src = inspect.getsource(CP.generate) + inspect.getsource(CP._middle_plan) + inspect.getsource(CP._stay) + inspect.getsource(
        CP._under) + inspect.getsource(CP._over) + inspect.getsource(CP._cluster_plan)
    assert "contact" not in src and ".can" not in src and "hero_accepting_input" not in src


def test_her_locked_motion_moves_the_hand_back_not_the_scene():
    # a dash in progress: the hand-back is later and farther on; the same call with the model free is at once
    S0 = hero_state(30., vx=0.)
    m = CP.Roller(S0, np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, TERRAIN)
    free = CP.hand_back(m, 0., 30.)
    assert free.known and free.index == m.off and free.t == pytest.approx(m.off * DT)
    from ssbot.combat.knife_chain_format import MASK_NAMES as B
    locked = CP.Roller(S0, np.full(4, B["R"] | B["DASH"], np.int64), kin.HoldState.idle(1), PARAMS, TERRAIN)
    hb = CP.hand_back(locked, 0., 30.)
    assert hb.known and hb.index > locked.off and hb.x > 30. and hb.t > free.t


def test_cluster_two_plans_through_the_public_selector(monkeypatch):
    tac, ws, fc = planned(monkeypatch, xs=(36., 37.), hx=26.)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    go_(tac, ws, fc)
    out = go_(tac, ws, fc)
    r = tac.plan_runner
    choices = {c["rule"]: c["score"] for c in tac.last["clapper_choices"]}
    assert choices["cluster_lure"] > choices["cluster_attack"] > choices["keep"]
    assert tac.last["clapper_winner"]["rule"] == "cluster_lure" and r.exec.selected == "lure"
    set_hero(tac, 26.)
    take_off(tac, ws, fc, vx=-6., face=-1)
    # ahead of the descent, the walker where it stood: the way back holds (or the retreat, never the middle entries)
    out = go_(tac, ws, fc)
    note = next(x for x in plan_notes(tac) if x["what"] == "takeoff")
    assert note["route"] in ("return", "retreat", "blocked")
    if note["route"] == "return":
        assert r.exec.name == "lure_return" and out.target == 8 and out.entry_attack.kind == "side" and 7 in out.no_hit


def test_cluster_space_missing_goes_to_attack_and_both_missing_is_explicit(monkeypatch):
    tac, ws, fc = planned(monkeypatch, xs=(24., 25.), hx=19.)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    go_(tac, ws, fc)
    out = go_(tac, ws, fc)
    r = tac.plan_runner
    assert r.exec.selected == "attack" and tac.last["clapper_winner"]["rule"] == "cluster_attack"
    assert any(e.get("not_applicable", "").startswith("not feasible") for e in tac.last["clapper_eval"]["tactics"])
    tac, ws, fc = planned(monkeypatch, xs=(24., 25.), hx=19.)
    go_(tac, ws, fc)
    antic(tac, ws, fc, family=G.CC_JUMP_CAST, state="Cast Slam Antic")
    go_(tac, ws, fc)
    go_(tac, ws, fc)
    r = tac.plan_runner
    assert r.exec.plan is None and r.exec.status == "blocked" and "lure:" in r.exec.reason and tac.last["clapper_winner"]["rule"] == "keep"


def test_the_intercept_trigger_stays_and_its_hold_is_a_running_phase(monkeypatch):
    tac, ws, fc = planned(monkeypatch, xs=(20., 28.), hx=25.)
    # not a parent scene at the start: she stands inside the other's span as the jump comes from behind her
    go_(tac, ws, fc)
    tac.goal = G.Goal(G.RUSH, 8, 24., 1., family=G.CC_IDLE)
    change(fc, 7, family=G.CC_JUMP, state="Air", committed=True)
    tac.t_commit[7] = 1.
    tac.jb_land[7] = (20., 1, 24., True)
    ws.entities[0].flip_x = True
    ws.entities[0].dmg_boxes = ws.entities[0].dmg_boxes[:1]
    # outside parent scene for the test: body boxes overlapping her x
    ws.entities[1].dmg_boxes[0].poly = [(24.8, 3.), (29., 3.), (29., 7.), (24.8, 7.)]
    out = go_(tac, ws, fc)
    r = tac.plan_runner
    assert tac.last["clapper_winner"]["rule"] == "intercept" and out.target == 7
    assert r.exec.plan.scene == "intercept" and r.exec.name == "hold"
    # later: the hold continues as the running phase; no separate 140 rule exists in the pool
    out = go_(tac, ws, fc)
    assert tac.last["clapper_winner"]["rule"] == "intercept" and "hold" not in {c["rule"] for c in tac.last["clapper_choices"]}
    # its jump over and no rune circle due: the phase ends by its event
    change(fc, 7, family=G.CC_IDLE, state="Idle", committed=False)
    out = go_(tac, ws, fc)
    assert r.exec.plan is None and r.exec.status == "complete"
    assert any(x["tactic"] == "jump intercept" for x in tac.last.get("clapper_releases", []))


def test_the_takeoff_trigger_records_in_the_executor_history(monkeypatch):
    tac, ws, fc = planned(monkeypatch, xs=(20., 22.4), hx=21.2)
    go_(tac, ws, fc)
    tac.goal = G.Goal(G.RUSH, 7, 24., 1., family=G.CC_IDLE)
    change(fc, 7, family=G.CC_JUMP, state="Jump Antic", committed=True)
    go_(tac, ws, fc)
    change(fc, 7, state="Air")
    out = go_(tac, ws, fc)
    r = tac.plan_runner
    if tac.last["clapper_winner"]["rule"] == "takeoff":
        assert out.target == 8 and r.exec.handled((7, tac.t_commit[7]), "departed")
        assert not any(k == "departed" for k in tac._clapper_priority)     # not a private memory any more


def test_reset_clears_everything_and_a_dead_worker_is_loud_at_reset(monkeypatch):
    tac, ws, fc = planned(monkeypatch)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    go_(tac, ws, fc); go_(tac, ws, fc)
    r = tac.plan_runner
    assert r.exec.plan is not None
    tac.reset()
    assert r.exec.plan is None and r.requests == 0 and r.channel.latest() is None
    r.channel.failure = "boom"
    with pytest.raises(RuntimeError):
        tac.reset()
    # inside a tick a failed worker is only a note: no plan, the generic rules go on, no exception
    r.channel.failure = "boom"
    tac2, ws2, fc2 = planned(monkeypatch)
    tac2.plan_runner.channel.failure = "boom"
    go_(tac2, ws2, fc2)
    antic(tac2, ws2, fc2)
    out = go_(tac2, ws2, fc2); go_(tac2, ws2, fc2)
    assert tac2.plan_runner.worker_failed and tac2.plan_runner.requests == 0 and tac2.last["clapper_winner"]["rule"] == "keep"


# ---- Sol seq 272 B: the action layer's refusal of the over strike takes back what the over_head stage put in, same tick ----


def test_a_withdrawn_stage_gives_back_l2s_own_stance_and_the_targets_weights_before_the_strike():
    from ssbot.combat.tactics.modes import EntryAttack, GoalPrefs, StageWithdraw, entry_attack_prefs, withdrawn_prefs
    entry = EntryAttack(8, "stomp", 7, G.CC_JUMP_CAST, 10.8, 22.1)
    pre = GoalPrefs(mode="RUSH", stance_x=44.2, weights={"hit": 1.}, target=8, hit_w={8: 3., 7: 1.},
                    hit_kw={7: (1., 0., 0., 0.)}, ground_hit=frozenset({7, 8}), no_pogo=frozenset({8}),
                    ground_first=frozenset({7}), no_hit=frozenset({7}), entry_attack=entry)
    struck = replace(entry_attack_prefs(pre), stance_x=29.7)          # the stage's stance: the walker's head
    assert struck.hit_kw[8] == (0., 0., 0., 3.) and 8 not in struck.ground_hit | struck.no_pogo
    w = StageWithdraw(44.2, (8, "stomp", 7), 3701, pre.hit_kw.get(8),
                      (8 in pre.ground_hit, 8 in pre.no_pogo, 8 in pre.ground_first))
    staged = replace(struck, withdraw=w)
    back = withdrawn_prefs(staged)
    assert back.stance_x == 44.2 and back.entry_attack is None and back.withdraw is None
    assert 8 not in back.hit_kw and back.hit_kw[7] == (1., 0., 0., 0.)
    assert back.ground_hit == frozenset({7, 8}) and back.no_pogo == frozenset({8}) and back.ground_first == frozenset({7})
    assert ((back.no_hit, back.hit_w, back.weights, back.target, back.mode)
            == (staged.no_hit, staged.hit_w, staged.weights, staged.target, staged.mode))
    # a weight the target had before the strike comes back as it was
    assert withdrawn_prefs(replace(staged, withdraw=replace(w, kw=(2., 0., 0., 0.)))).hit_kw[8] == (2., 0., 0., 0.)
    assert withdrawn_prefs(struck) is struck                          # nothing to take back


def test_the_stage_frame_is_where_its_generation_and_phase_were_first_read():
    r = object.__new__(CP.PlanRunner)
    r._stage_key = r._stage_f = None
    r.exec = NS(plan=NS(generation=1), name="over_head")
    assert r.stage_frame(NS(frame=100)) == 100 and r.stage_frame(NS(frame=104)) == 100
    r.exec.plan = NS(generation=2)                        # a new plan of the scene: a new stage
    assert r.stage_frame(NS(frame=105)) == 105
    r.exec.name = "over_wait"
    assert r.stage_frame(NS(frame=106)) == 106
    r.exec.name = "over_head"                             # the same name again is a new stage too
    assert r.stage_frame(NS(frame=107)) == 107 and r.stage_frame(NS(frame=None)) == 107
    r.exec.plan = NS(generation=3)
    assert r.stage_frame(NS(frame=None)) is None          # no frame read: nothing to withdraw by


def test_only_the_over_head_stage_names_the_frame_it_began():
    plan = plan_of(request(W=body(2, 28.), hx=24.))
    names = [p.name for p in plan.phases]
    assert "over_head" in names and len(names) > 3
    unit = CT.PlannedMiddle()
    plans = NS(stance=lambda sc, ph: 30., stage_frame=lambda sc: 77)
    for name in names:
        plans.exec = NS(plan=plan, phase=plan.phase(name), name=name)
        ap = unit.apply(NS(plans=plans, geo=None, hx=24., tac=None), "middle_jump", None, NS(iid=2))
        assert ap.withdraw_f == (77 if name == "over_head" else None), name


def test_only_the_over_head_stage_offers_its_stance_and_stomp_for_withdrawal(monkeypatch):
    # the over take-off of test_no_standing_gap_at_the_take_off_runs_the_prepared_route_farther_from_the_wall
    from ssbot.combat.tactics.modes import withdrawn_prefs
    tac, ws, fc = planned(monkeypatch, xs=(19., 31.5), hx=27.)
    ws.stamp.frame = 500
    def step():
        ws.stamp.frame += 1
        return go_(tac, ws, fc)
    assert step().withdraw is None
    antic(tac, ws, fc)
    assert step().withdraw is None and step().withdraw is None        # before the take-off: no strike stage
    r = tac.plan_runner
    land = r.exec.plan.get("landings")[0]
    change(fc, 8, pos=(30., fc.subjects[1].pos[1]))
    ws.entities[1].dmg_boxes[0].poly = [(29., 3.), (31., 3.), (31., 7.), (29., 7.)]
    take_off(tac, ws, fc, vx=(land - 19.) / CP.GAIN)
    out = step()
    assert r.exec.name == "over_head" and out.target == 8 and out.entry_attack.kind == "stomp"
    w, f0 = out.withdraw, ws.stamp.frame
    assert w.entry == (8, "stomp", out.entry_attack.source) and w.stage_f == f0
    assert w.stance_x != pytest.approx(out.stance_x)      # the stage stands on the walker's head, L2's own stance elsewhere
    back = withdrawn_prefs(out)
    assert back.stance_x == w.stance_x and back.entry_attack is None and back.hit_kw.get(8) == w.kw
    assert out.hit_kw[8][:3] == (0., 0., 0.) and back.hit_kw.get(8) != out.hit_kw[8]   # the stomp's weights are the strike's
    assert tuple(8 in s for s in (back.ground_hit, back.no_pogo, back.ground_first)) == w.sets
    assert back.no_hit == out.no_hit and 7 in back.no_hit                  # the jumper's ban is no part of the strike
    out = step()
    assert r.exec.name == "over_head" and out.withdraw.stage_f == f0      # the stage goes on from where it began
    # its real bounce: no second strike asked, nothing to take back
    change(fc, 8, state="Dmg Attack")
    tac.plan_input = CP.HeroInput(hero_state(30.), np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, TERRAIN, bounce=8)
    out = step()
    assert r.exec.plan is not None and r.exec.name != "over_head" and out.withdraw is None


def _gate(monkeypatch, entry=(8, "stomp", 7)):
    """The production air transfer Run of test_dash_lock179 (target 8, caster 7, active air link, its air dash due now) bound to a
    tactical stomp entry: (chain, state, sim, the recoveries it makes, by reason; the real recovery still runs)."""
    from ssbot.combat.tactics.modes import EntryAttack
    from tests.test_dash_lock179 import chain, flight
    r, s, sim = flight()
    n = chain(monkeypatch, r)
    n._entry_attack_goal = EntryAttack(entry[0], entry[1], entry[2], G.CC_JUMP_CAST, 10., 0.)
    recovered = []
    real = n._recover
    monkeypatch.setattr(n, "_recover", lambda why, f: (recovered.append(why), real(why, f))[1])
    return n, s, sim, recovered


def _step_geometry(monkeypatch, step):
    """The B2 geometry: every dash lock scan (through past origin + 2) clear; the current step: "contact" a complete scan with a real
    contact, "incomplete" an incomplete one with none, "unchecked" no geometry."""
    from ssbot.combat import knife_chain_air_native as AN
    from ssbot.combat.knife_chain_commitment import ContactScan, PathContact
    from ssbot.combat.knife_chain_geometry import GeometryUnavailable
    class Geo:
        def __init__(self, *a):
            pass
        def scan(self, path):
            if path.through > path.origin + 2:
                return ContactScan("fixture", path.origin, path.through, (), "all-owner")
            if step == "unchecked":
                raise GeometryUnavailable("fixture: step unchecked")
            hit = (PathContact(path.through, 9, "body"),) if step in ("contact", "partial") else ()
            return ContactScan("fixture", path.origin, path.through, hit, "all-owner", complete=step == "contact")
        preflight = scan
    monkeypatch.setattr(AN, "B2Geometry", Geo)


LOCK_WHY, STEP_WHY = "rune transfer air dash refused: locked motion blocked or unknown", "rune transfer external step blocked"


@pytest.mark.parametrize("case,why,refused", [
    ("lock_contact", LOCK_WHY, True), ("lock_unknown", LOCK_WHY, False),            # one reason string, blocked or unknown
    ("lock_partial", LOCK_WHY, False),                                               # a contact in an incomplete scan
    ("step_contact", STEP_WHY, True), ("step_incomplete", STEP_WHY, False),          # the same
    ("step_partial", STEP_WHY, False), ("step_unchecked", "rune transfer external step unchecked", False),
    ("prefix_unknown", "rune transfer actual queued prefix mismatch", False), ("seam_fallback", None, False),
    ("step_fallback", None, False)])                                                # the seam takes the tick: no recovery
def test_only_a_gates_real_contact_in_its_complete_scan_records_the_refused_strike(monkeypatch, case, why, refused):
    # Sol seq 274 on #344: a recovery for an unknown prefix, scan or context, or one its reason string calls "blocked or unknown",
    # is no evidence that the over route was refused by geometry
    from ssbot.combat.knife_chain_commitment import ContactScan, PathContact
    from tests.test_dash_lock179 import FC, geometry
    n, s, sim, recovered = _gate(monkeypatch)
    fb = NS(stage="active", mask=0)
    if case.startswith("lock") or case in ("prefix_unknown", "seam_fallback"):
        geometry(monkeypatch, None if case == "lock_unknown" else sim.f + 3)    # a contact inside the dash's locked motion
        if case == "lock_unknown":
            n.DASH_LOCK_MAX = 3                                                  # its input return not modelled: no scan
        if case == "lock_partial":
            part = ContactScan("fixture", sim.f, sim.f + 6, (PathContact(sim.f + 3, 7, "move"),), "all-owner", complete=False)
            monkeypatch.setattr(n, "_dash_lock_scan", lambda *a, **k: (part, {"lock": "partial"}))
        if case == "prefix_unknown":
            monkeypatch.setattr(n, "queued_prefix", lambda *a: (None, None))
        if case == "seam_fallback":
            monkeypatch.setattr(n, "_seam_fallback", lambda f, why: fb)
    else:
        _step_geometry(monkeypatch, "contact" if case == "step_fallback" else case.split("_")[1])
        if case == "step_fallback":
            monkeypatch.setattr(n, "_seam_fallback", lambda f, why: fb)
    out = n._transfer_offer(s, 0., sim, FC, NS(target=8), False)
    assert out is (fb if why is None else None) and recovered == ([] if why is None else [why]), recovered
    notes = [e for e in n.events if e["event"] == "transfer_strike_refused"]
    if refused:
        assert n.refused_strike == (sim.f, 8, "stomp", 7) and len(notes) == 1 and notes[0]["first"]["frame"] > sim.f
    else:
        assert n.refused_strike is None and not notes


@pytest.mark.parametrize("case", ["own", "bounced", "return_goal", "other_goal", "other_chain", "run_other", "plan_other",
                                  "no_entry"])
def test_the_refused_strike_is_the_tactical_entrys_own_before_any_bounce(monkeypatch, case):
    from ssbot.combat import knife_chain_transfer as T
    from ssbot.combat.knife_chain_eval import Run
    n, s, sim, _ = _gate(monkeypatch)
    run = Run("vault_idle" if case == "other_chain" else T.PROGRAM, "air",
              {"iid": 9 if case == "run_other" else 8, **({"bounced": True} if case == "bounced" else {})})
    if case == "return_goal":
        n._transfer_goal = T.ReturnGoal(8, 7, 990, None, "SWITCH", None, 990)
    if case == "other_goal":
        n._transfer_goal = T.TransferGoal(8, 6, 990, 0.)
    if case == "no_entry":
        n._entry_attack_goal = None
    n._strike_refused(1000, NS(iid=9 if case == "plan_other" else 8, caster=7), run, {"frame": 1003})
    assert n.refused_strike == ((1000, 8, "stomp", 7) if case == "own" else None)
    # a recovery itself never records one: the supervisor's refusal of a B2 primitive, or any other
    n.refused_strike = None
    n._recover("supervisor primitive disallowed", 1001)
    assert n.refused_strike is None
    n.refused_strike = (1000, 8, "stomp", 7)
    n.reset(1, start_frame=2000)
    assert n.refused_strike is None


def _withdraw_tick(prefs, refusal=None, offer=None, bound=math.inf):
    from ssbot.combat.forum_planner import ForumPlanner
    seen, notes = [], []
    def propose(*a):
        if refusal is not None:
            chain.refused_strike = refusal           # B2's recovery inside its own propose, after L2 decided (#341 3703)
        return offer
    chain = NS(b2=True, arm="B", refused_strike=None, propose=propose, first_allowed=lambda *a: True,
               install=lambda *a: NS(t_ms={}, installed=True), continuation_value_bound=lambda p: bound,
               _note=lambda ev, **k: notes.append((ev, k)))
    res = NS(J=0., S=0, forced_risk=False, t_ms={})
    p = NS(chain_native=chain, ticks=0, scene_field_values=None, _ordinary_tick=lambda *a, **k: (seen.append(a[5]), res)[1])
    out = ForumPlanner.tick(p, NS(stamp=NS(frame=1000)), np.zeros(1), None, None, None, prefs, None)
    return out, seen, notes


def test_the_ordinary_rows_of_the_refusal_tick_read_the_withdrawn_stage():
    from ssbot.combat.tactics.modes import EntryAttack, GoalPrefs, StageWithdraw, withdrawn_prefs
    entry = EntryAttack(8, "stomp", 7, G.CC_JUMP_CAST, 10.8, 22.1)
    w = StageWithdraw(44.2, (8, "stomp", 7), 990, None, (False, False, False))
    staged = GoalPrefs(mode="RUSH", stance_x=29.7, weights={}, target=8, hit_kw={8: (0., 0., 0., 3.)}, entry_attack=entry,
                       withdraw=w)
    out, seen, notes = _withdraw_tick(staged, refusal=(1000, 8, "stomp", 7))
    back = withdrawn_prefs(staged)
    assert len(seen) == 1 and seen[0] is not staged and seen[0].stance_x == back.stance_x == 44.2
    assert seen[0].entry_attack is None and seen[0].withdraw is None and seen[0].hit_kw == back.hit_kw == {}
    assert notes == [("plan_stage_withdrawn", dict(frame=1000, refused_f=1000, stage_f=990, stance_x=44.2, stage_stance_x=29.7))]
    # a later tick of the same stage: the refusal recorded earlier still takes it back
    assert _withdraw_tick(staged, refusal=(995, 8, "stomp", 7))[1][0].stance_x == 44.2
    # nothing taken back: no refusal; one before this stage began; another strike's; B2 offers keys this tick
    for kw in (dict(), dict(refusal=(985, 8, "stomp", 7)), dict(refusal=(1000, 8, "stomp", 9)),
               dict(refusal=(1000, 7, "stomp", 7)), dict(refusal=(1000, 8, "side", 7)),
               dict(refusal=(1000, 8, "stomp", 7), offer=NS(stage="continuation", value=-1.))):
        out, seen, notes = _withdraw_tick(staged, **kw)
        assert len(seen) == 1 and seen[0] is staged and not [n for n in notes if n[0] == "plan_stage_withdrawn"], kw
    # rows already read before B2's propose (a chain with a finite value bound) are not re-read on its refusal
    out, seen, notes = _withdraw_tick(staged, refusal=(1000, 8, "stomp", 7), bound=1e9)
    assert len(seen) == 1 and seen[0] is staged and not [n for n in notes if n[0] == "plan_stage_withdrawn"]


# ---- Sol seq 273: the route checked is the keys the Run sends before it hands back (next_mask's own "arrived") ----


def _run_loop(x0, gx, by_f, f0=100, steps=150, dash_cd=0.):
    """next_mask tick by tick through the model from rest, as the Run: (sim at f0, the mask it sends there, the goal, the keys it
    sends, the tick it ends on, how)."""
    from ssbot.combat import knife_chain_waypoint as WP
    from ssbot.combat.air_chain import ChainSim
    from ssbot.combat.holdfilter import hold_filter_jit
    goal = WP.WaypointGoal(gx, by_f, "retreat", 1, ((1, 0.), 1, "attack_retreat"))
    S, hold, sent, keys, first = hero_state(x0), kin.HoldState.idle(1), [0], [], None
    S[kin.DASH_CD] = dash_cd
    for f in range(f0, f0 + steps):
        prefix = np.array([sent[-1]], np.int64)
        sim = ChainSim(S, prefix, hold, PARAMS, TERRAIN, f, f)
        mask, what = WP.next_mask(sim, goal, f)
        if what in ("arrived", "late"):
            return first, goal, keys, f, what
        if first is None:
            first = (sim, int(mask))
        keys.append(int(mask))
        sent.append(int(mask))
        lat, hold = hold_filter_jit(prefix[None], hold)
        S = np.asarray(kin.rollout(S, lat, PARAMS, TERRAIN).final[:, 0], np.float64)
    return first, goal, keys, None, "no end"


@pytest.mark.parametrize("mirror", [False, True])
@pytest.mark.parametrize("dx,by_f,cd,n_keys,dash_from", [(13., 140, 0., 32, 0), (9., 132, 0., 23, 0), (9., 132, .12, 29, 7),
                                                         (8., 180, 0., 57, None), (6., 160, 0., 43, None), (1.5, 130, 0., 9, None)])
def test_the_route_checked_is_the_keys_the_run_sends_before_it_hands_back(mirror, dx, by_f, cd, n_keys, dash_from):
    # long glides (a dash held into the sprint; 30 -> 43 is Sol's seq 273 case: next_mask's first "arrived" at 132, #343 held its
    # dash to k32, released it at k33 and checked to f146), a dash at its cooldown edge (route()'s branch) and short ones (a run),
    # both ways: route_keys at f100 = the Run's own keys, tick by tick, before the tick it reports "arrived"
    from ssbot.combat import knife_chain_waypoint as WP
    from ssbot.combat.air_chain import ChainSim
    from ssbot.combat.holdfilter import hold_filter_jit
    x0, gx = (30. + dx, 30.) if mirror else (30., 30. + dx)
    (sim, mask), goal, keys, f_end, how = _run_loop(x0, gx, by_f, dash_cd=cd)
    dashes = [k for k, m in enumerate(keys) if m & kin.B_DASH]
    assert how == "arrived" and f_end == 100 + n_keys and (dashes[0] if dashes else None) == dash_from
    assert list(WP.route_keys(sim, goal, 100, mask)) == keys
    # from a later tick of the same Run (its dash held, its run going on): the rest of the same keys
    S, hold, sent = np.asarray(sim.start, np.float64).reshape(-1).copy(), kin.HoldState.idle(1), [0]
    for k in range(n_keys // 2):
        prefix = np.array([sent[-1]], np.int64)
        sent.append(keys[k])
        lat, hold = hold_filter_jit(prefix[None], hold)
        S = np.asarray(kin.rollout(S, lat, PARAMS, TERRAIN).final[:, 0], np.float64)
    f = 100 + n_keys // 2
    later = ChainSim(S, np.array([sent[-1]], np.int64), hold, PARAMS, TERRAIN, f, f)
    m2, what = WP.next_mask(later, goal, f)
    assert what in ("go", "dash") and list(WP.route_keys(later, goal, f, m2)) == keys[n_keys // 2:]


def test_the_hand_back_search_is_the_first_tick_that_arrives():
    from ssbot.combat import knife_chain_waypoint as WP
    for x0, gx, by_f in ((30., 43., 140), (43., 30., 140), (30., 38., 180), (30., 47.5, 160)):
        (sim, mask), goal, keys, f_end, how = _run_loop(x0, gx, by_f)
        m = WP.SimRoller(sim)
        row = np.full(60, mask, np.int64)
        a = WP._arrival(m.xs(row[None])[0][m.off:], gx, 1 if gx > x0 else -1, goal.tol)
        full = WP._arrived_at(m, row, 1, a, gx, goal.tol)
        assert full == f_end - 100 and full <= a
        assert all(WP._handback(m, row, a, gx, goal.tol, span=s) == full for s in (1, 2, 3, 16)), (x0, gx)
        assert WP._arrived_at(m, row, 1, full - 1, gx, goal.tol) is None


@pytest.mark.parametrize("mirror", [False, True])
def test_a_delayed_hazard_after_the_hand_back_is_not_the_runs_and_one_before_it_is(monkeypatch, mirror):
    # Sol seq 273: f100, 30 -> 43, by_f 140, its new dash's lock passing; the Run hands back at 132 (its keys to 133). A small rune at
    # 45.4 (mirrored 27.6), her box centre - 0.9, r 2.166, lit look-ahead 41..46, is met first at f144 only on the glide after that:
    # #343 refused the start for it; bombs met before the hand-back (f115 early in the dash, f127 near its end) still refuse it
    x0, gx = (43., 30.) if mirror else (30., 43.)
    out, chain = _offer(monkeypatch, x0, gx, bombs=[(27.6 if mirror else 45.4, 41, 46)], by=40, lock="pass")
    assert out is not None and out.mask == (kin.B_LEFT if mirror else kin.B_RIGHT) | kin.B_DASH
    assert not any(n["event"] == "waypoint_rejected" for n in chain.notes)
    for bx, on, off, first in ((38., 14, 20, 115), (41.5, 26, 31, 127)):
        out, chain = _offer(monkeypatch, x0, gx, bombs=[(73. - bx if mirror else bx, on, off)], by=40, lock="pass")
        note = next(n for n in chain.notes if n["event"] == "waypoint_rejected")
        assert out is None and note["reason"] == "route meets a delayed hazard" and note["first"]["frame"] == first


def _refused_loop(x0, gx, by_f, f0=100, steps=80):
    """next_mask tick by tick through the model from rest, as the Run whose new dash its lock refuses every tick (the key sent is
    the direction alone): (sim at f0, the mask next_mask asked there, the goal, the keys it sends, the tick it ends on, how)."""
    from ssbot.combat import knife_chain_waypoint as WP
    from ssbot.combat.air_chain import ChainSim
    from ssbot.combat.holdfilter import hold_filter_jit
    goal = WP.WaypointGoal(gx, by_f, "retreat", 1, ((1, 0.), 1, "attack_retreat"))
    S, hold, sent, keys, first = hero_state(x0), kin.HoldState.idle(1), [0], [], None
    for f in range(f0, f0 + steps):
        prefix = np.array([sent[-1]], np.int64)
        sim = ChainSim(S, prefix, hold, PARAMS, TERRAIN, f, f)
        mask, what = WP.next_mask(sim, goal, f)
        if what in ("arrived", "late"):
            return first, goal, keys, f, what
        if first is None:
            first = (sim, int(mask))
        keys.append(int(mask) & ~kin.B_DASH)
        sent.append(keys[-1])
        lat, hold = hold_filter_jit(prefix[None], hold)
        S = np.asarray(kin.rollout(S, lat, PARAMS, TERRAIN).final[:, 0], np.float64)
    return first, goal, keys, None, "no end"


@pytest.mark.parametrize("mirror", [False, True])
@pytest.mark.parametrize("dx,by_f,n_keys,how", [(9., 132, 13, "late"), (13., 140, 3, "late"), (3., 112, 6, "late"),
                                                (5., 121, 13, "late"), (6.75, 119, 1, "late"), (6.75, 122, 7, "late"),
                                                (9.25, 137, 19, "late"), (.5, 103, 1, "arrived")])
def test_a_refused_dash_route_is_the_run_up_to_its_late_or_arrived_hand_back(mirror, dx, by_f, n_keys, how):
    # Sol seq 276: every later new dash refused too, the Run sends the direction key and hands back at next_mask's "late" (its dash
    # from that tick no longer in time) or "arrived", whichever first; 30 -> 39 by 132 is Sol's case (late at 113). 6.75 by 119 /
    # 122 and 9.25 by 137: a dash pressed on some ticks does not start (a later one can still make it), no bisection finds them
    from ssbot.combat import knife_chain_waypoint as WP
    x0, gx = (30. + dx, 30.) if mirror else (30., 30. + dx)
    (sim, mask), goal, keys, f_end, end = _refused_loop(x0, gx, by_f)
    assert mask & kin.B_DASH and end == how and f_end == 100 + n_keys and len(keys) == n_keys
    assert list(WP.route_keys(sim, goal, 100, mask & ~kin.B_DASH, dash_refused=True)) == keys
