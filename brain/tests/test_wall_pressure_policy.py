"""The policy asks L2 after the same-focus real bounce, before Native owns keys."""
from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from ssbot.combat.tactics import modes as M
from ssbot.train.forum_planner_policy import ForumPlannerPolicy as Policy


def transaction(*, real=True, pressure=None, goal=None, phase="after", bounced=False):
    events = []
    policy = Policy.__new__(Policy)
    state, ws, forecast = {"f": 100}, object(), object()
    prefs = M.GoalPrefs(mode="RUSH", stance_x=4., weights={"risk": 2.}, target=7,
                        hit_w={7: 3.}, no_hit=frozenset({9}), no_dash=frozenset({9}))
    pressure = M.WallPressure(7, "side", -1, (.25, .75)) if pressure is None else pressure
    run = NS(phase=phase, bounced=bounced)
    policy.slam_play = NS(run=run, abort=lambda reason: events.append(("abort", reason)))
    policy._play_tick = "retained"

    def observe(st, pr, legacy, *, game_time):
        assert st is state and pr is prefs and legacy is run and game_time == 10.
        events.append(("observe",))
        return real

    def candidate(w, fc, target, *, observed_bounce):
        assert w is ws and fc is forecast and observed_bounce is True
        events.append(("candidate", target))
        return pressure

    def apply(st, pr, *, handoff):
        assert st is state
        events.append(("apply", pr, handoff))
        return pr

    policy.chain_native = NS(observe_bounce_goal=observe, goal_preferences=apply,
                            _transfer_goal=goal or NS(source_kind="BOUNCE", caster=7, target=7))
    policy.tac = NS(wall_pressure_candidate=candidate, rules=NS(reach_u=1.8))
    return policy, state, prefs, ws, forecast, events


def call(tx):
    policy, state, prefs, ws, forecast, _ = tx
    return policy._chain_goal_preferences(state, prefs, game_time=10., ws=ws, forecast=forecast)


@pytest.mark.parametrize("phase,bounced,handoff", [("after", False, True), ("after", True, True), ("air", False, False)])
def test_observe_then_l2_then_native_with_unchanged_handoff(phase, bounced, handoff):
    tx = transaction(phase=phase, bounced=bounced)
    policy, _, prefs, _, _, events = tx
    out = call(tx)
    assert [e[0] for e in events] == ["observe", "candidate", "apply"]
    assert events[-1][2] is handoff and events[-1][1] is out
    assert out.target == prefs.target == 7 and out.wall_pressure.target == 7
    assert out.hit_kw[7] == (3., 0., 0., 0.) and out.stance_x == .5
    assert out.weights == prefs.weights and out.no_dash == prefs.no_dash and out.no_hit == prefs.no_hit
    assert policy._play_tick == "retained"  # adding an intent is not a target-handoff abort


@pytest.mark.parametrize("missing", ["not_real", "ws", "forecast", "entry", "existing", "no_hit", "target"])
def test_existing_intent_and_missing_real_boundary_skip_l2(missing):
    tx = list(transaction(real=missing != "not_real"))
    policy, state, prefs, ws, forecast, events = tx
    if missing == "ws": ws = None
    elif missing == "forecast": forecast = None
    elif missing == "entry": prefs.entry_attack = M.EntryAttack(7, "stomp", 8, "CC_CAST", 10., 10.)
    elif missing == "existing": prefs.wall_pressure = M.WallPressure(7, "stomp", -1)
    elif missing == "no_hit": prefs.no_hit = frozenset({7})
    elif missing == "target": prefs.target = None
    out = policy._chain_goal_preferences(state, prefs, game_time=10., ws=ws, forecast=forecast)
    assert [e[0] for e in events] == ["observe", "apply"] and out is prefs


@pytest.mark.parametrize("source_kind,caster,target", [("SWITCH", 7, 7), ("CAST", 7, 7), ("BOUNCE", 8, 7), ("BOUNCE", 7, 8)])
def test_a_to_b_switch_never_borrows_as_bounce_exception(source_kind, caster, target):
    tx = transaction(goal=NS(source_kind=source_kind, caster=caster, target=target))
    out = call(tx)
    assert out.wall_pressure is None
    assert [e[0] for e in tx[-1]] == ["observe", "apply"]


def test_foreign_candidate_cannot_select_a_new_target():
    tx = transaction(pressure=M.WallPressure(8, "stomp", 1))
    out = call(tx)
    assert out is tx[2] and out.target == 7 and out.wall_pressure is None


def test_real_native_goal_handoff_still_aborts_after_apply():
    tx = transaction()
    policy, _, _, _, _, events = tx
    def apply(st, pr, *, handoff):
        events.append(("apply", pr, handoff))
        return replace(pr, mode="NATIVE_HANDOFF")
    policy.chain_native.goal_preferences = apply
    assert call(tx).mode == "NATIVE_HANDOFF"
    assert [e[0] for e in events] == ["observe", "candidate", "apply", "abort"]
    assert policy._play_tick is None


def test_legacy_two_argument_call_stays_supported():
    policy, state, prefs, _, _, events = transaction()
    assert policy._chain_goal_preferences(state, prefs, game_time=10.) is prefs
    assert [e[0] for e in events] == ["observe", "apply"]


@pytest.mark.parametrize("kind,expected", [("side", (3., 0., 0., 0.)), ("stomp", (0., 0., 0., 3.))])
def test_shared_helper_only_applies_matching_contact_preferences(kind, expected):
    prefs = M.GoalPrefs(mode="RUSH", stance_x=4., weights={}, target=7, hit_w={7: 3.},
                        ground_hit=frozenset({7, 8}), no_pogo=frozenset({7, 8}), ground_first=frozenset({7, 8}))
    pressure = M.WallPressure(7, kind, -1, (.25, .75) if kind == "side" else None)
    out = M.wall_pressure_prefs(prefs, pressure)
    assert out.wall_pressure is pressure and out.hit_kw[7] == expected
    assert (7 in out.ground_hit) == (7 in out.no_pogo) == (7 in out.ground_first) == (kind == "side")
    assert 8 in out.ground_hit and 8 in out.no_pogo and 8 in out.ground_first
    assert out.stance_x == (.5 if kind == "side" else 4.)
    assert M.wall_pressure_prefs(replace(prefs, target=8), pressure).wall_pressure is None
