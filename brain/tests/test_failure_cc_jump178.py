"""Task 178 live 786766c3: a SWITCH stomp entry bound to the source's plain jump (CC_JUMP) keeps its HP liability.

2607 the tactical entry bound target 335470 (Walk) to source 335476's CC_JUMP (Jump Antic 2549); at 2625 the
transfer's external step met that jump's landing (2627) and _recover raised: FailureExposure had no CC_JUMP family.
"""
import pytest
from ssbot.combat import knife_chain_failure as KF
from ssbot.combat.knife_chain_commitment import MoveInstance
from ssbot.combat.tactics import gauntlet as G
from ssbot.combat.tactics.modes import EntryAttack, GoalPrefs
from tests.test_knife_chain_transfer import cast_scene
from tests.test_target_entry_attack import native


def jump_state(f, st, t, iid=7):
    return {"f": f, "ents": [{"iid": iid, "hp": 100, "fsms": [{"name": "Control", "state": st, "t": t}]}]}


def test_plain_jump_family_is_the_clapper_spec_and_ends_when_control_leaves_it():
    from ssbot.combat.are_types.clapper import SPEC
    states, primary = KF._FAMILIES["CC_JUMP"]
    assert states == SPEC.fam_states["CC_JUMP"] and primary == SPEC.primary["CC_JUMP"] == "Jump Antic"
    x = KF.FailureExposure(MoveInstance(7, 2549, "CC_JUMP"), 2607, 2625, 41.0)
    for f, st in ((2625, "Air"), (2628, "Slam 2"), (2640, "Slam Recover")):   # live 786: Air from 2580, Slam 2 2628
        x.observe(jump_state(f, st, 0.1), game_time=41.0 + (f - 2549) / 60)
        assert x.through is None and x.active(f)
    x.observe(jump_state(2660, "Idle", 0.0), game_time=41.0 + 111 / 60)
    assert (x.observed_end_reason, x.observed_end_source) == ("same-move end observed", "actual Control left jump states")
    assert x.through == 2660 and not x.active(2661)


def test_a_new_jump_antic_ends_the_old_jump():
    x = KF.FailureExposure(MoveInstance(7, 2549, "CC_JUMP"), 2607, 2625, 41.0)
    x.observe(jump_state(2626, "Air", 0.75), game_time=41.0 + 77 / 60)
    x.observe(jump_state(2700, "Jump Antic", 0.05), game_time=41.0 + 151 / 60)
    assert x.observed_end_reason == "new Jump Antic observed" and x.through == 2700


@pytest.mark.parametrize("family", ["CC_EVADE", "RUNE_TRANSFER", "VAULT_IDLE", "CC_JUMPX"])
def test_unsupported_families_still_raise(family):
    with pytest.raises(ValueError, match="supported observed move family"):
        KF.FailureExposure(MoveInstance(7, 2549, family), 2607, 2625, 41.0)


def test_switch_entry_from_a_plain_jump_recovers_with_the_jump_liability():
    """The cross-entry contract: SWITCH binding (goal_preferences) -> transfer responsibility -> _recover."""
    n = native()
    s = cast_scene()
    s["ents"][0]["fsms"][0].update(state="Jump Antic", t=.25)      # source 7's plain jump, antic at 985
    entry = EntryAttack(8, "stomp", 7, G.CC_JUMP, 4., 10.)
    n.goal_preferences(s, GoalPrefs(mode="RUSH", stance_x=38., weights={}, target=8, entry_attack=entry), handoff=True)
    goal = n._transfer_goal
    assert goal.source_kind == "SWITCH" and goal.responsibility == MoveInstance(7, 985, "CC_JUMP")
    move = MoveInstance(8, 1000, "RUNE_TRANSFER")
    n._transfer_responsibility[move] = (goal.responsibility, goal.cast_ta)   # as _transfer_offer records it
    n.commitment = {"move": move, "origin": 1000, "ta": None}
    n._actual_state = s
    n._recover("rune transfer external step blocked", 1018)
    (x,) = n._failure_exposures
    assert x.move == MoveInstance(7, 985, "CC_JUMP") and (x.origin, x.failed_frame, x.ta) == (1000, 1018, 19.75)
    assert x.active(1018) and x.through is None and n.commitment is None
