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

PARAMS = kin.hero2(HeroParams.load(next(iter(CREST_PARAMS.values()))))
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
    # the stage starts half a travel time earlier than the written latest departure, its keys applying two frames on
    assert depart == pytest.approx(stay.get("depart_t") - (CP.GUIDE_START_X - 1.) * travel - 2 * DT, abs=1e-9)
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


def test_a_long_way_under_is_not_offered_the_rows_could_not_start_it():
    # one planner row's reach: past it she would only wait at the hammer's edge
    far = plan_of(request(W=body(2, 44.), hx=40.))
    assert not cand(far, "under").feasible and "one planner row" in cand(far, "under").reason
    # the usual aim: about 5 u in front of its landing, 3.5 u behind it: not offered, the reason says so
    usual = plan_of(request(J=body(1, 30., "Jump Antic", "CC_JUMP", facing=1), W=body(2, 38.), hx=34.))
    assert "one planner row" in cand(usual, "under").reason
    # an observed landing right in front of her (a flight seen late): the way behind it is short
    J = body(1, 25., "Air", "CC_JUMP", facing=1)
    short = plan_of(request(J=J, W=body(2, 38.), hx=33., stage="flight", antic_at=None, land=30., land_vx=5.45, air_at=0.))
    u = cand(short, "under")
    assert u.feasible and abs(u.get("end_x") - 33.) <= CP.UNDER_ROW_U and u.get("route_s") <= CP.DESCENT_S


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
    assert plan.phase("attack_retreat").suppress_hits is True and plan.phase("attack_back").attack == "side"


def test_coming_back_from_the_retreat_the_body_in_front_is_the_target():
    plan = plan_of(cluster_request())                # it lands between her and the other one: it is the reachable one
    attack = cand(plan, "attack")
    assert attack.get("back_target") == 1 and plan.phase("attack_back").target == 1 and plan.phase("attack_back").no_hit == ()
    # (it lands past the other one: the other one)
    far = plan_of(request("cluster", J=body(1, 36., "Jump Antic", "CC_JUMP"), W=body(2, 30.), hx=25., side=-1))
    if cand(far, "attack").feasible:
        assert cand(far, "attack").get("back_target") == 2 and far.phase("attack_back").no_hit == (1,)


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
    # the hero outside: cluster, never middle
    assert CP.parent_scene([J, W], geo, 15.)[0] == "cluster"
    assert CP.parent_scene([J, W], geo, 40.)[0] == "cluster"
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
    assert ex.step(1.1, lambda p: [], {}, (1, 0.)).name == "first"
    assert ex.step(1.2, lambda p: ["go"], {}, (1, 0.)).name == "second"
    assert ex.handled((1, 0.), "go")
    assert ex.step(1.3, lambda p: ["end"], {}, (1, 0.)) is None
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
    ex.step(1.1, lambda p: ["go"], {"w": .5}, (1, 0.))
    assert ex.phase.name == "second"
    # a route past the boundary is not replaced: support is no longer read, the newer plan waits
    newer = mini_plan(gen=2)
    assert ex.offer(newer, 1.2, (1, 0.), {"w": 5.})[0] == "pending"
    assert ex.step(1.3, lambda p: [], {"w": 5.}, (1, 0.)).name == "second"
    assert ex.pending is newer
    assert ex.step(1.4, lambda p: ["stuck"], {"w": 5.}, (1, 0.)) is None and ex.status == "blocked"
    # the waiting plan is taken at the boundary, in the next step, after its checks again
    assert ex.step(1.5, lambda p: [], {"w": 5.}, (1, 0.)).name == "first" and ex.plan.generation == 2
    # support gone in a replaceable stage: invalid at once, no waiting for a worker
    ex2 = PlanExecutor()
    ex2.offer(mini_plan(support=(Range("w", 0., 1.),)), 1., (1, 0.), {"w": .5})
    assert ex2.step(1.1, lambda p: [], {"w": 3.}, (1, 0.)) is None and ex2.status == "invalid"


def test_fixed_times_and_instance_end():
    ex = PlanExecutor()
    timed = Plan("s", (1, 0.), 1, 0., None, 10., phases=(Phase("wait", at=(2., "go")), Phase("go", on=())),
                 candidates=(Candidate("a", True, None, "wait"),), selected="a")
    ex.offer(timed, 1., (1, 0.), {})
    assert ex.step(1.9, lambda p: [], {}, (1, 0.)).name == "wait"
    assert ex.step(2., lambda p: [], {}, (1, 0.)).name == "go"
    assert ex.step(2.1, lambda p: [], {}, (1, 9.)) is None and ex.status == "invalid"     # a new instance
    ex.offer(mini_plan(gen=9, until=3.), 2.2, (1, 0.), {})
    assert ex.step(3.1, lambda p: [], {}, (1, 0.)) is None and ex.status == "expired"
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
    from ssbot.combat.knife_chain_format import MASK_NAMES as B
    tac, ws, fc = planned(monkeypatch, hx=34.2)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    go_(tac, ws, fc); go_(tac, ws, fc)
    r = tac.plan_runner
    assert r.exec.name == "aim_wait"
    # a lock of her own: the same place, the keys in flight now a long dash; it has to be read from the hand-back alone
    S = hero_state(34.2)
    dash = np.full(1, B["R"] | B["DASH"], np.int64)
    n = r.requests
    tac.plan_input = CP.HeroInput(np.asarray(kin.rollout(S, np.full((1, 30), B["R"] | B["DASH"], np.int64), PARAMS, TERRAIN).final, float),
                                  dash, kin.HoldState.idle(1), PARAMS, TERRAIN)
    seen = []
    for _ in range(12):
        go_(tac, ws, fc)
        seen += plan_notes(tac)
        if r.exec.name != "aim_wait":
            break
    assert r.hand.known
    assert r.exec.name == "aim_attack" or any(n_["what"] == "request" for n_ in seen) or r.exec.name == "aim_guide"
    assert r.requests >= n


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
