"""Task 182 seq 311 (the person 11-09): between the two, the plan on the over branch of a jump cast's aim: the walker's evade -> straight at the first one, then the follow-up from the real take-off."""
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import evade_chase as EC
from ssbot.combat import knife_chain_air_native as AN
from ssbot.combat import knife_chain_waypoint as WP
from ssbot.combat.air_chain import ChainSim
from ssbot.combat.tactics import clapper_plans as CP, gauntlet as G
from ssbot.combat.tactics.l2_plan import Candidate, Phase, Plan, PlanExecutor
from ssbot.knowledge import kinematics as kin
from ssbot.train.forum_planner_policy import ForumPlannerPolicy
from tests.test_clapper_priority import change, manual, scene   # noqa: F401  (autouse manual-B fixture)
from tests.test_l2_plan182 import PARAMS, TERRAIN, antic, body, cand, go_, hero_state, plan_notes, plan_of, planned, request, set_hero, take_off


def cast_request(**kw):
    kw.setdefault("J", body(1, 19., "Cast Slam Antic", "CC_JUMP_CAST", facing=1))
    kw.setdefault("W", body(2, 33.))
    kw.setdefault("hx", 29.)
    return request(**kw)


def in_aim(monkeypatch, xs=(19., 33.), hx=29., family=G.CC_JUMP_CAST, state="Cast Slam Antic", delay=1):
    tac, ws, fc = planned(monkeypatch, xs=xs, hx=hx, delay=delay)
    go_(tac, ws, fc)
    antic(tac, ws, fc, family=family, state=state)
    for _ in range(1 + delay):
        go_(tac, ws, fc)
    return tac, ws, fc, tac.plan_runner


def evade(fc, iid=8):
    change(fc, iid, family="CC_EVADE", state="Evade Scuttle")


def pressing(monkeypatch, **kw):
    tac, ws, fc, r = in_aim(monkeypatch, **kw)
    assert r.exec.selected == "over" and r.exec.name == "aim_attack"
    evade(fc)
    out = go_(tac, ws, fc)
    assert r.exec.name == "aim_press"
    return tac, ws, fc, r, out


# ---- the plan: which plans have the stage ----

def test_only_a_jump_cast_aim_that_chose_over_has_the_press():
    plan = plan_of(cast_request())
    assert plan.selected == "over" and plan.phase("aim_press") is not None and plan.phase("press_next") is not None
    assert plan.phase("aim_attack").on[0] == ("walker_evade", "aim_press")
    press = plan.phase("aim_press")
    assert press.target == 1 and press.suppress_hits and press.go == "press" and not press.replaceable and press.no_chase and press.ground
    assert plan.phase("press_next").adopts_next and plan.phase("press_next").no_chase and plan.phase("press_next").target == 2
    assert not plan.phase("press_next").replaceable and plan.phase("press_next").ground


def test_a_plain_jump_has_no_press():
    plan = plan_of(cast_request(J=body(1, 19., "Jump Antic", "CC_JUMP", facing=1), W=body(2, 28.), hx=24.))
    assert plan.selected == "over" and plan.phase("aim_press") is None
    assert not any(ev == "walker_evade" for p in plan.phases for ev, _ in p.on)


def test_a_plan_that_chose_stay_or_under_has_no_press():
    stay = plan_of(cast_request(W=body(2, 40.), hx=26.))
    assert stay.selected == "stay" and stay.phase("aim_press") is None
    no_room = plan_of(cast_request(W=body(2, 46.8), hx=40.))          # the far side is a wall: over has no room
    assert no_room.selected != "over" and no_room.phase("aim_press") is None


def test_a_flight_stage_plan_has_no_press():
    from dataclasses import replace
    plan = plan_of(replace(flight_q(W=body(2, 36.5)), routes=CP.FOLLOW_UP))      # (over is the choice here: the aim's condition is what keeps the press out)
    assert plan.selected == "over" and plan.phase("aim_press") is None


# ---- the follow-up request ----

def flight_q(hx=24., land=21., W=None, air_at=-.05, t=0., J_x=19.5, **kw):
    q = request(J=body(1, J_x, "Air", "CC_JUMP_CAST", facing=1, vx=3.), W=W if W is not None else body(2, 41.), hx=hx, stage="flight", land=land, air_at=air_at, land_vx=3.,
                antic_at=None, t=t, **kw)
    return q


def test_after_the_press_only_stay_or_over_may_be_chosen():
    from dataclasses import replace
    plain = plan_of(flight_q())
    q = replace(flight_q(), routes=CP.FOLLOW_UP)
    plan = plan_of(q)
    assert plan.get("followup") is True and plain.get("followup") is False
    assert cand(plan, "under").reason == "not a follow-up of the press" and not cand(plan, "under").feasible
    assert plan.selected == "stay" and plan.candidate("stay").start == "return"
    assert "under" not in plan.get("prepared")
    far_wall = replace(flight_q(W=body(2, 36.5)), routes=CP.FOLLOW_UP)      # no standing room in the middle: over the second one
    plan = plan_of(far_wall)
    assert plan.selected == "over" and plan.candidate("over").start == "over_head"
    assert not cand(plan, "stay").feasible


def test_the_follow_up_stay_counts_her_way_out_of_the_coverage():
    from dataclasses import replace
    # the rune lights in 0.2 s, 6 u of coverage still ahead of her: the middle is not hers in time
    q = replace(flight_q(hx=24., land=21., air_at=-1.8, t=0.), routes=CP.FOLLOW_UP)
    plan = plan_of(q)
    assert not cand(plan, "stay").feasible and "still inside the big rune" in cand(plan, "stay").reason
    # the same, no press behind it: the ordinary flight plan's check is unchanged
    assert cand(plan_of(flight_q(hx=24., land=21., air_at=-1.8, t=0.)), "stay").feasible


def test_neither_follow_up_is_an_explicit_no_plan():
    from dataclasses import replace
    W = body(2, 36.5, "Slam Antic", "CC_SLAM")      # in a near attack: neither the middle nor its head
    plan = plan_of(replace(flight_q(W=W), routes=CP.FOLLOW_UP))
    assert plan.status == "none" and plan.selected is None and "under: not a follow-up" in plan.reason


# ---- the foreground: through the real L2 entry ----

def test_the_walkers_evade_ends_the_attack_on_it_and_she_goes_at_the_first_one(monkeypatch):
    tac, ws, fc, r, out = pressing(monkeypatch)
    assert out.target == 7 and out.entry_attack is None and {7, 8} <= set(out.no_hit)
    assert out.press_walker == 8 and tac.last["clapper_winner"]["rule"] == "middle_jump"
    assert out.stance_x == pytest.approx(19. + 4.)                     # its face stance, in front of it, not behind
    assert out.waypoint is not None and out.waypoint.kind == "press" and out.waypoint.x == pytest.approx(23.) and out.waypoint.source == 7
    assert out.waypoint.by_f == ws.stamp.frame + int(np.ceil((r.exec.plan.get("lock_t") - ws.stamp.t_game_s) * 60.))
    assert any(n["what"] == "press" and n["walker"] == 8 for n in plan_notes(tac))


def test_a_press_never_backs_her_off_the_first_one(monkeypatch):
    tac, ws, fc, r = in_aim(monkeypatch, hx=22.)                       # 3 u from its root, nearer than its front stance
    assert r.exec.selected == "over"
    evade(fc)
    out = go_(tac, ws, fc)
    assert r.exec.name == "aim_press" and out.stance_x == pytest.approx(22.) and out.waypoint is None


def test_no_walker_evade_nothing_changes(monkeypatch):
    tac, ws, fc, r = in_aim(monkeypatch)
    for state, family in (("Walk", G.CC_IDLE), ("Idle", G.CC_IDLE)):
        change(fc, 8, family=family, state=state)
        out = go_(tac, ws, fc)
        assert r.exec.name == "aim_attack" and out.target == 8 and out.press_walker is None


def test_on_the_stay_branch_the_walkers_evade_is_not_this_rule(monkeypatch):
    tac, ws, fc, r = in_aim(monkeypatch, xs=(19., 40.), hx=26.)
    assert r.exec.selected == "stay"
    evade(fc)
    out = go_(tac, ws, fc)
    assert r.exec.name != "aim_press" and out.press_walker is None


def test_a_plain_jumps_aim_is_not_this_rule(monkeypatch):
    tac, ws, fc, r = in_aim(monkeypatch, xs=(19., 28.), hx=24., family=G.CC_JUMP, state="Jump Antic")
    assert r.exec.selected == "over" and r.exec.plan.phase("aim_press") is None
    evade(fc)
    out = go_(tac, ws, fc)
    assert r.exec.name != "aim_press" and out.press_walker is None


def test_only_the_aim_states_count_as_still_aiming(monkeypatch):
    tac, ws, fc, r = in_aim(monkeypatch)
    assert r.exec.selected == "over"
    change(fc, 7, state="Slam 2")                     # (past its aim although no flight was ever seen)
    evade(fc)
    out = go_(tac, ws, fc)
    assert r.exec.name != "aim_press" and out.press_walker is None


def test_past_the_lock_the_evade_starts_no_press(monkeypatch):
    tac, ws, fc, r = in_aim(monkeypatch)
    lock = r.exec.plan.aim_deadline
    while ws.stamp.t_game_s < lock + 1 / 60.:
        go_(tac, ws, fc)
    assert r.exec.name == "aim_attack"
    evade(fc)
    out = go_(tac, ws, fc)
    assert r.exec.name != "aim_press" and out.press_walker is None


def test_with_the_first_one_off_the_ground_the_evade_starts_no_press(monkeypatch):
    tac, ws, fc, r = in_aim(monkeypatch)
    take_off(tac, ws, fc, vx=8.)
    evade(fc)
    out = go_(tac, ws, fc)
    assert r.exec.name != "aim_press" and out.press_walker is None


def test_out_of_the_middle_the_evade_starts_no_press(monkeypatch):
    tac, ws, fc, r = in_aim(monkeypatch)
    set_hero(tac, 36.)                                # her hand-back is past the walker's body
    ws.hero.pos = ws.hero.pos.__class__((36., ws.hero.pos.v[1]), conf=1.)
    ws.hero.hurtbox = [(35.75, 4.), (36.25, 4.), (36.25, 6.), (35.75, 6.)]
    evade(fc)
    go_(tac, ws, fc)
    assert r.exec.name != "aim_press"


def test_a_new_move_of_the_walker_does_not_end_the_press_and_nothing_is_asked(monkeypatch):
    tac, ws, fc, r, _ = pressing(monkeypatch)
    n = r.requests
    for state, family in (("Idle", G.CC_IDLE), ("Spell Antic", G.CC_CAST), ("Slam Antic", G.CC_SLAM), ("Cast Slam Antic", G.CC_JUMP_CAST)):
        change(fc, 8, family=family, state=state)
        out = go_(tac, ws, fc)
        assert r.exec.name == "aim_press" and out.target == 7 and out.press_walker == 8
    assert r.requests == n


def test_its_place_is_kept_when_the_walker_is_far_past_any_old_prediction(monkeypatch):
    tac, ws, fc, r, _ = pressing(monkeypatch)
    change(fc, 8, pos=(33. + 3. * CP.HARD_WALKER_U, fc.subjects[1].pos[1]))
    go_(tac, ws, fc)
    assert r.exec.name == "aim_press"                 # the walker's slide is what started this stage: no support of the old plan ends it


def test_at_the_real_take_off_one_request_and_she_waits_for_the_answer(monkeypatch):
    tac, ws, fc, r, _ = pressing(monkeypatch, delay=2)
    change(fc, 8, family=G.CC_IDLE, state="Idle")
    n = r.requests
    plan = r.exec.plan
    take_off(tac, ws, fc, vx=2.)
    out = go_(tac, ws, fc)
    assert r.exec.name == "press_next" and r.exec.plan is plan and r.requests == n + 1
    assert out.target == 8 and out.press_walker == 8 and {7, 8} <= set(out.no_hit) and out.entry_attack is None
    assert out.stance_x == pytest.approx(33. - 4.) and out.waypoint is None         # toward the walker's front: where both follow-ups go
    assert any(x["what"] == "request" and x["why"] == CP.PRESS_OVER and x["stage"] == "flight" for x in plan_notes(tac))
    go_(tac, ws, fc)
    assert r.requests == n + 1                        # once


def test_the_follow_up_waits_for_the_walker_to_stand(monkeypatch):
    tac, ws, fc, r, _ = pressing(monkeypatch)
    n = r.requests
    take_off(tac, ws, fc, vx=2.)
    for _ in range(3):
        out = go_(tac, ws, fc)                         # still sliding: nothing is asked, she is on her way, no chase
        assert r.exec.name == "press_next" and r.requests == n and out.press_walker == 8
    change(fc, 8, family=G.CC_IDLE, state="Idle")
    go_(tac, ws, fc)
    assert r.requests == n + 1


def test_the_follow_up_takes_over_and_the_press_is_over(monkeypatch):
    tac, ws, fc, r, _ = _force_press(monkeypatch)
    take_off(tac, ws, fc, vx=2.)
    go_(tac, ws, fc)
    out = go_(tac, ws, fc)
    out = go_(tac, ws, fc)
    assert r.exec.name in ("return", "over_head") and r.exec.plan.get("followup") is True
    assert out.press_walker is None and out.target == 8


def _force_press(monkeypatch):
    """A plan on the over branch by hand: the over-only plan of the scene the follow-up is tested in."""
    tac, ws, fc, r = in_aim(monkeypatch)
    assert r.exec.selected == "over"
    evade(fc)
    out = go_(tac, ws, fc)
    assert r.exec.name == "aim_press"
    change(fc, 8, family=G.CC_IDLE, state="Idle")
    return tac, ws, fc, r, out


def test_a_stale_plan_never_takes_over_from_the_wait(monkeypatch):
    tac, ws, fc, r, _ = _force_press(monkeypatch)
    plan = r.exec.plan
    take_off(tac, ws, fc, vx=2.)
    r.exec.pending = plan.__class__(**{**plan.__dict__, "generation": plan.generation + 50})      # made before the take-off: no followup mark
    go_(tac, ws, fc)
    assert r.exec.name == "press_next" and r.exec.plan is plan


def test_the_jump_she_pressed_counts_as_left_once_it_is_off_the_ground(monkeypatch):
    tac, ws, fc, r, _ = _force_press(monkeypatch)
    assert not r.exec.handled(r.exec.plan.instance, "departed")
    take_off(tac, ws, fc, vx=2.)
    go_(tac, ws, fc)
    assert r.exec.name == "press_next" and r.exec.handled(r.exec.plan.instance, "departed")
    assert r.departed(tac._clapper_priority and NS(subjects=fc.subjects, tac=tac)) == r.exec.plan.instance


def test_no_follow_up_ends_the_stage_and_says_why(monkeypatch):
    tac, ws, fc, r, _ = _force_press(monkeypatch)
    take_off(tac, ws, fc, vx=2.)
    change(fc, 8, family=G.CC_SLAM, state="Slam Antic")
    seen = []
    for _ in range(3):
        go_(tac, ws, fc)
        seen += plan_notes(tac)
    ended = [n for n in seen if n["what"] == "ended" and n["phase"] == "press_next"]
    assert ended and ended[0]["status"] == "blocked" and "follow-up" in ended[0]["reason"]
    assert r.exec.plan is None                                           # the public rules go on from here, and they do not hold the jump she left


def test_no_answer_in_time_releases_the_scene(monkeypatch):
    tac, ws, fc, r, _ = _late_press(monkeypatch)
    take_off(tac, ws, fc, vx=2.)
    go_(tac, ws, fc)
    t0 = ws.stamp.t_game_s
    seen = []
    while ws.stamp.t_game_s < t0 + CP.PRESS_WAIT_S + .05 and not any(n["what"] == "ended" for n in seen):
        out = go_(tac, ws, fc)
        seen += plan_notes(tac)
    ended = next(n for n in seen if n["what"] == "ended")
    assert ended["status"] == "blocked" and ended["reason"] == "next_late" and ended["phase"] == "press_next"
    assert out.press_walker is None


def _late_press(monkeypatch):
    tac, ws, fc, r, out = _force_press(monkeypatch)
    r.channel.request = lambda key, q: 10 ** 7          # no result ever comes for it
    return tac, ws, fc, r, out


def test_no_scene_left_ends_the_stage_at_once(monkeypatch):
    tac, ws, fc, r, _ = _force_press(monkeypatch)
    n = r.requests
    take_off(tac, ws, fc, vx=2.)
    ws.hero.pos = ws.hero.pos.__class__((36., ws.hero.pos.v[1]), conf=1.)        # she herself and her hand-back are past the walker's body: no middle to ask about
    ws.hero.hurtbox = [(35.75, 4.), (36.25, 4.), (36.25, 6.), (35.75, 6.)]
    set_hero(tac, 36.)
    go_(tac, ws, fc)
    ended = next(x for x in plan_notes(tac) if x["what"] == "ended")
    assert ended["status"] == "blocked" and r.requests == n and "no scene left" in ended["reason"]


def test_the_follow_up_is_asked_from_where_she_stands(monkeypatch):
    tac, ws, fc, r, _ = _force_press(monkeypatch)
    n = r.requests
    take_off(tac, ws, fc, vx=2.)
    set_hero(tac, 10.)                                # a key in flight: the predicted hand-back is past the body, she herself is between the two
    go_(tac, ws, fc)
    assert r.exec.name == "press_next" and r.requests == n + 1


def test_a_tick_without_body_geometry_does_not_end_the_wait(monkeypatch):
    tac, ws, fc, r, _ = _force_press(monkeypatch)
    take_off(tac, ws, fc, vx=2.)
    box = ws.hero.hurtbox
    ws.hero.hurtbox = []                              # (L2's geometry is unknown this tick)
    go_(tac, ws, fc)
    assert r.exec.name == "press_next"
    ws.hero.hurtbox = box
    n = r.requests
    go_(tac, ws, fc)
    assert r.exec.name == "press_next" and r.requests == n + 1


def test_later_requests_for_a_pressed_jump_still_choose_only_the_follow_ups(monkeypatch):
    tac, ws, fc, r, _ = _force_press(monkeypatch)
    take_off(tac, ws, fc, vx=2.)
    seen = []
    orig = r.channel.request
    r.channel.request = lambda key, q: (seen.append(q), orig(key, q))[1]
    go_(tac, ws, fc)
    assert seen and seen[-1].routes == CP.FOLLOW_UP and seen[-1].stage == "flight"
    go_(tac, ws, fc)
    go_(tac, ws, fc)
    assert r.exec.plan.get("followup") is True
    r.exec.end("invalid", "test", ws.stamp.t_game_s)
    change(fc, 8, pos=(39., fc.subjects[1].pos[1]))
    n = len(seen)
    go_(tac, ws, fc)
    assert len(seen) == n + 1 and seen[-1].routes == CP.FOLLOW_UP


def test_a_new_jump_is_a_new_scene_with_every_route(monkeypatch):
    tac, ws, fc, r, _ = _force_press(monkeypatch)
    r.exec.end("invalid", "test", ws.stamp.t_game_s)
    tac.t_commit[7] = ws.stamp.t_game_s + 1.
    change(fc, 8, family=G.CC_IDLE, state="Idle")
    seen = []
    orig = r.channel.request
    r.channel.request = lambda key, q: (seen.append(q), orig(key, q))[1]
    go_(tac, ws, fc)
    assert seen and seen[-1].routes is None


# ---- the second one already aiming its own jump (Sol's review of #374) ----

def _second_aims(tac, ws, fc, family=G.CC_JUMP_CAST, state="Cast Slam Antic", elapsed=.05):
    antic(tac, ws, fc, iid=8, family=family, state=state, elapsed=elapsed)


def test_the_follow_up_is_judged_with_the_second_one_aiming(monkeypatch):
    tac, ws, fc, r, _ = _force_press(monkeypatch)
    n = r.requests
    take_off(tac, ws, fc, vx=2.)
    _second_aims(tac, ws, fc)
    seen = []
    orig = r.channel.request
    r.channel.request = lambda key, q: (seen.append(q), orig(key, q))[1]
    go_(tac, ws, fc)
    assert r.exec.name == "press_next" and r.requests == n + 1 and seen[-1].routes == CP.FOLLOW_UP
    assert seen[-1].other.state == "Cast Slam Antic" and seen[-1].other_antic_at is not None and seen[-1].jumper.state == "Air"


def test_two_in_the_air_is_no_follow_up(monkeypatch):
    tac, ws, fc, r, _ = _force_press(monkeypatch)
    take_off(tac, ws, fc, vx=2.)
    take_off(tac, ws, fc, iid=8, vx=-3.)
    change(fc, 8, family=G.CC_JUMP_CAST)
    go_(tac, ws, fc)
    ended = next(x for x in plan_notes(tac) if x["what"] == "ended")
    assert ended["status"] == "blocked" and "no scene left" in ended["reason"]


def aiming_q(W_x=41., antic=-.1, family="CC_JUMP_CAST", state="Cast Slam Antic", **kw):
    from dataclasses import replace
    return replace(flight_q(W=body(2, W_x, state, family), **kw), routes=CP.FOLLOW_UP, other_antic_at=antic)


def test_with_the_second_one_aiming_no_strike_on_it_and_the_middle_counts_its_clock():
    plan = plan_of(aiming_q())
    stay, over = cand(plan, "stay"), cand(plan, "over")
    assert not over.feasible and "aiming its own jump" in over.reason
    assert stay.feasible and plan.selected == "stay" and stay.start == "return"
    assert stay.get("second_lock_t") == pytest.approx(-.1 + .88) and stay.get("second_land_t") == pytest.approx(-.1 + .88 + CP.FLIGHT_S)
    assert stay.get("second_bite_t") == pytest.approx(stay.get("second_land_t") + CP.RUNE_ON_S)
    assert stay.get("second_ways") in ("side", "side/behind", "/behind")
    assert plan.phase("return").on[0] == ("other_off", "done")


def test_a_second_one_not_aiming_changes_nothing():
    from dataclasses import replace
    plan = plan_of(replace(flight_q(), routes=CP.FOLLOW_UP))
    assert plan.selected == "stay" and not cand(plan, "stay").get("second_lock_t")
    assert all(ev != "other_off" for ev, _ in plan.phase("return").on)


def test_a_second_one_near_its_hammer_only_uses_the_plain_jump_clock():
    plan = plan_of(aiming_q(family="CC_JUMP", state="Jump Antic", hx=35.))
    stay = cand(plan, "stay")
    assert stay.feasible and stay.get("second_lock_t") == pytest.approx(-.1 + .48)
    assert stay.get("second_bite_t") == pytest.approx(stay.get("second_land_t"))         # its hammer: no rune to wait for


def test_a_way_out_through_the_first_ones_rune_is_closed_only_while_it_is_lit():
    # (its rune here lights at land_t + 1.083 and is over by land_t + 1.367; the second one's bite falls in those frames: this side is not open then)
    q = aiming_q(antic=-.88, hx=35.5)                   # reachable in time: only its rune being lit there closes this side
    stay = cand(plan_of(q), "stay")
    assert stay.get("second_bite_t") == pytest.approx(0. + CP.FLIGHT_S + CP.RUNE_ON_S, abs=.01)
    assert q.air_at + CP.FLIGHT_S + CP.RUNE_ON_S - .05 <= stay.get("second_bite_t") <= q.air_at + CP.FLIGHT_S + CP.RUNE_OVER_S
    assert "side" not in str(stay.get("second_ways"))
    other = cand(plan_of(aiming_q(antic=-.1, hx=35.5)), "stay")
    assert "side" in str(other.get("second_ways"))              # its bite after that rune is over: this side is open


def test_the_second_ones_clock_unknown_is_no_middle():
    plan = plan_of(aiming_q(antic=None))
    assert not cand(plan, "stay").feasible and "aim clock is unknown" in cand(plan, "stay").reason


def test_no_way_out_of_the_second_ones_coverage_is_no_middle():
    plan = plan_of(aiming_q(antic=-1.55))              # its aim is long done, its rune bites at once: neither way is open
    assert not cand(plan, "stay").feasible and "no way out of the middle" in cand(plan, "stay").reason
    assert plan.status == "none" and plan.selected is None
    assert "no way out of the middle" in plan.reason and "aiming its own jump" in plan.reason


def test_the_middle_ends_when_the_second_one_is_off_the_ground(monkeypatch):
    tac, ws, fc, r, _ = _force_press(monkeypatch)
    take_off(tac, ws, fc, vx=2.)
    _second_aims(tac, ws, fc)
    go_(tac, ws, fc)
    plan = plan_of(aiming_q())
    inst = r.exec.plan.instance
    from dataclasses import replace
    now = ws.stamp.t_game_s
    plan = replace(plan, instance=inst, generation=r.exec.plan.generation + 5, made_t=now, valid_until=now + 5., support=(), detail=tuple(dict(plan.detail, other=8, followup=True).items()))
    assert r.exec.offer(plan, now, inst, {})[0] == "pending"
    take_off(tac, ws, fc, iid=8, vx=-3.)
    go_(tac, ws, fc)
    assert r.exec.plan is None and r.exec.status == "complete" and r.exec.reason == "other_off"


def test_the_second_ones_new_move_between_request_and_adoption_is_read(monkeypatch):
    tac, ws, fc, r, _ = _force_press(monkeypatch, )
    take_off(tac, ws, fc, vx=2.)
    n = r.requests
    go_(tac, ws, fc)                                    # asked with the second one standing
    assert r.requests == n + 1
    _second_aims(tac, ws, fc)                           # it starts its own jump before the answer is adopted
    seen = []
    for _ in range(3):
        go_(tac, ws, fc)
        seen += plan_notes(tac)
    assert any(x["what"] == "ended" for x in seen)      # the follow-up made for a standing one does not run: other_move / the second one's real state ends it


# ---- the run ----

def press_sim(x, f=100, prefix=0, cd=0., **kw):
    S = hero_state(x, **kw)
    S[kin.DASH_CD] = cd
    return ChainSim(S, np.array([prefix], np.int64), kin.HoldState.idle(1), PARAMS, TERRAIN, f, f)


def press_goal(x=23., by=120, kind="press"):
    return WP.WaypointGoal(float(x), by, kind, 7, ((7, 0.), 1, "aim_press"), family="CC_JUMP_CAST")


def test_a_press_owes_no_arrival_it_goes_as_far_as_it_can():
    sim = press_sim(32.)
    # far beyond a run's and a dash's reach by its frame: the other kinds are "late", the press dashes
    assert WP.next_mask(sim, press_goal(by=112, kind="guide"), 100) == (None, "late")
    mask, what = WP.next_mask(sim, press_goal(by=112), 100)
    assert what == "dash" and mask == kin.B_LEFT | kin.B_DASH


def test_a_press_runs_while_the_dash_is_not_ready():
    mask, what = WP.next_mask(press_sim(32., cd=.5), press_goal(by=112), 100)
    assert what == "go" and mask == kin.B_LEFT


def test_a_press_near_enough_runs_and_at_its_place_is_done():
    mask, what = WP.next_mask(press_sim(24.), press_goal(by=130), 100)
    assert what == "go" and mask == kin.B_LEFT
    assert WP.next_mask(press_sim(23.05), press_goal(by=130), 100) == (0, "arrived")


def test_a_press_toward_the_right_goes_right():
    mask, what = WP.next_mask(press_sim(32.), press_goal(x=44., by=112), 100)
    assert mask == kin.B_RIGHT | kin.B_DASH and what == "dash"


def test_the_route_a_press_counts_on_is_its_key_up_to_its_frame_and_no_long_gone_route():
    sim = press_sim(32.)
    keys = WP.route_keys(sim, press_goal(by=112), 100, kin.B_LEFT)
    assert keys is not None and len(keys) == 11 and np.all(keys == kin.B_LEFT)
    assert WP.route_keys(sim, press_goal(by=112, kind="guide"), 100, kin.B_LEFT) is None
    keys = WP.route_keys(sim, press_goal(by=112), 100, kin.B_LEFT, dash_refused=True)
    assert len(keys) == 11 and np.all(keys == kin.B_LEFT)
    near = WP.route_keys(press_sim(24.), press_goal(by=130), 100, kin.B_LEFT)
    assert near is not None and len(near) < 28                       # it does arrive: the route stops at its hand-back


# ---- every real key owner ----

def test_the_chase_neither_starts_nor_goes_on_in_the_press():
    stub = NS(two=None)
    assert ForumPlannerPolicy._chase_block(stub, 100, NS(press_walker=8)) == "plan press"
    assert ForumPlannerPolicy._chase_block(stub, 100, NS(press_walker=None)) is None
    assert ForumPlannerPolicy._chase_block(stub, 100, NS()) is None
    ec = EC.EvadeChase(one=False, two=True)
    ec.run = EC.Chase(iid=8, face=-1, f0=90, k0=0, x0=5., ground0=True, hp0=9)
    assert ec.step(100, dict(f=100, hero=dict(health=9), ents=[]), True, block="plan press") is None
    assert ec.run is None and ec.done[-1].why == "plan press"


def test_the_slam_script_leaves_the_walker_alone_in_the_press():
    assert ForumPlannerPolicy._press_skip(None, NS(press_walker=None)) is None
    assert ForumPlannerPolicy._press_skip(None, NS(press_walker=8)) == frozenset({8})
    assert ForumPlannerPolicy._press_skip(frozenset({7}), NS(press_walker=8)) == frozenset({7, 8})
    keep = frozenset({7})
    assert ForumPlannerPolicy._press_skip(keep, NS()) is keep


def _chain():
    cls = next(c for c in vars(AN).values() if isinstance(c, type) and "_waypoint_offer" in vars(c))
    chain = object.__new__(cls)
    chain.arm, chain.budget, chain.dispatch, chain.policy_gate_reason, chain.recovery = "B", None, NS(frame=100), None, None
    chain._bounce, chain._wall_pressure, chain.post_context, chain.commitment = None, None, None, None
    chain.runner = NS(run=None)
    chain._check_hook_start = lambda f: False
    chain._transfer_ready, chain._context, chain._transfer_goal = True, ((0, "state", 1., True), "sim", None, None), NS(source_kind="SWITCH")
    chain._transfer_offer = lambda *a: "new strike"
    return chain


def test_the_chain_starts_no_new_strike_in_the_press():
    entry = NS(target=8, kind="side")
    free = NS(waypoint=None, press_walker=None, wall_pressure=None, entry_attack=entry, target=8)
    press = NS(waypoint=None, press_walker=8, wall_pressure=None, entry_attack=entry, target=8)
    assert _chain()._propose(None, None, None, None, None, None, free, None) == "new strike"
    assert _chain()._propose(None, None, None, None, None, None, press, None) is None


def test_a_committed_strike_runs_on_past_the_stage():
    chain = _chain()
    chain.commitment = {"move": 1}
    entry = NS(target=8, kind="side")
    press = NS(waypoint=None, press_walker=8, wall_pressure=None, entry_attack=None, target=8)
    # the gate is for a new start only: with a commitment the chain goes on past it (its own steps then ask the context)
    chain.vault_enabled, chain._vault_ready, chain._context = False, False, None
    assert chain._propose(None, None, None, None, None, None, press, None) is None and entry


def test_the_executor_takes_only_a_marked_follow_up_at_the_wait():
    wait = Phase("press_next", target=2, replaceable=False, adopts_next=True)
    next_ = Phase("return", target=2, on=(("x", "done"),))
    cand_ = Candidate("stay", True, None, "return")
    plan = Plan("middle", (1, 0.), 1, 0., None, 10., phases=(wait,), candidates=(Candidate("over", True, None, "press_next"),), selected="over")
    follow = Plan("middle", (1, 0.), 2, 0., None, 10., phases=(next_,), candidates=(cand_,), selected="stay", detail=(("followup", True),))
    stale = Plan("middle", (1, 0.), 3, 0., None, 10., phases=(next_,), candidates=(cand_,), selected="stay")
    ex = PlanExecutor()
    assert ex.offer(plan, 0., (1, 0.), {})[0] == "adopted" and ex.name == "press_next"
    assert ex.offer(stale, 0., (1, 0.), {})[0] == "pending"
    ex.step(0., lambda ph: [], lambda p: {}, lambda p: (1, 0.))
    assert ex.plan is plan
    assert ex.offer(Plan(**{**follow.__dict__, "generation": 4}), 0., (1, 0.), {})[0] == "pending"
    ex.step(0., lambda ph: [], lambda p: {}, lambda p: (1, 0.))
    assert ex.plan.generation == 4 and ex.name == "return"


def test_a_stage_without_the_mark_does_not_take_a_follow_up():
    wait = Phase("press", target=2, replaceable=False)
    next_ = Phase("return", target=2, on=(("x", "done"),))
    plan = Plan("middle", (1, 0.), 1, 0., None, 10., phases=(wait,), candidates=(Candidate("over", True, None, "press"),), selected="over")
    follow = Plan("middle", (1, 0.), 2, 0., None, 10., phases=(next_,), candidates=(Candidate("stay", True, None, "return"),), selected="stay", detail=(("followup", True),))
    ex = PlanExecutor()
    ex.offer(plan, 0., (1, 0.), {})
    ex.offer(follow, 0., (1, 0.), {})
    ex.step(0., lambda ph: [], lambda p: {}, lambda p: (1, 0.))
    assert ex.plan is plan
