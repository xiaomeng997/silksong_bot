"""Jump-start evidence is independent of send/receipt and later umbrella keys."""
from types import SimpleNamespace
import numpy as np
import pytest
from ssbot.knowledge import kinematics as km
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.combat.knife_chain_jump import JumpStartWatch,grounded_strike
from ssbot.combat.knife_chain_commitment import MoveInstance
from ssbot.combat.knife_chain_nominal import state_names

MOVE=MoveInstance(7,1000,"CC_SLAM")


def path():
    return SimpleNamespace(origin=1000,commands=np.array([B["R"],B["J"],B["L"]|B["J"],0,B["J"],0],np.int64),
        flags=np.array([km.F_GROUND,km.F_GROUND,0,0,0,0,0],np.int64))


def state(f,*,ground=True,attacking=False,clip="Idle",target=None,desired=0,latched=0,applied=None):
    names=state_names();bits=[0,0]
    for name,val in [("onGround",ground),("attacking",attacking)]:
        if val:
            i=names.index(name);bits[i//64]|=1<<(i%64)
    return {"f":f,"hero":{"cstate":bits,"anim":{"clip":clip}},
        "act":{"target":f if target is None else target,"applied":f if applied is None else applied,
               "mask":latched,"hf":{"desired":desired,"latched":latched}}}


def test_only_the_first_contiguous_ground_jump_block_is_watched():
    w=JumpStartWatch.from_path(path(),MOVE,1000,{1002:B["J"],1005:B["J"]})
    assert w.move==MOVE and w.origin==1000 and w.targets==(1002,1003)
    assert w.sent_targets=={1002} and w.seen_frame is None
    assert w.record_send(1003,B["R"]|B["J"]) is True
    assert w.record_send(1005,B["J"]) is False
    assert w.sent_targets=={1002,1003}


@pytest.mark.parametrize("case",["no_j","air_entry","first_j_already_air"])
def test_air_entry_and_later_umbrella_do_not_require_a_new_ground_jump(case):
    p=path()
    if case=="no_j":p.commands[:]=0
    elif case=="air_entry":p.flags[0]=0;p.flags[4]=km.F_GROUND
    else:p.flags[1]=0
    assert JumpStartWatch.from_path(p,MOVE,1000,{}) is None


def test_missed_window_uses_next_send_target_without_moving_the_original_block():
    w=JumpStartWatch.from_path(path(),MOVE,1000,{})
    assert w.failure(1001) is None  # next target1003 is still an original J slot
    assert "window elapsed" in w.failure(1002)  # next target1004 has missed both
    assert not w.record_send(1005,B["J"])  # later umbrella cannot rescue it
    assert "window elapsed" in w.failure(1005)
    assert w.targets==(1002,1003)


def test_send_and_matching_receipt_are_not_observed_takeoff():
    w=JumpStartWatch.from_path(path(),MOVE,1000,{1002:B["J"]})
    assert not w.observe(state(1002,target=1002,desired=B["J"],latched=B["J"]))
    assert w.seen_frame is None
    assert w.failure(1006) is None
    assert "no observed airborne" in w.failure(1007)


def test_actual_airborne_is_credited_once_after_actual_successful_j_target():
    w=JumpStartWatch.from_path(path(),MOVE,1000,{1002:B["J"]})
    assert not w.observe(state(1001,ground=False))  # not this sent jump yet
    assert w.observe(state(1003,ground=False,clip="Airborne")) is True
    assert w.seen_frame==1003
    assert not w.observe(state(1004,ground=False))
    assert w.failure(1100) is None


def test_airborne_without_a_successful_jump_send_has_no_takeoff_credit():
    w=JumpStartWatch.from_path(path(),MOVE,1000,{})
    assert not w.observe(state(1002,ground=False,clip="Airborne"))
    assert w.seen_frame is None and w.failure(1002) is not None


@pytest.mark.parametrize("bits",[None,[],["unknown"],"unknown"])
def test_missing_ground_observation_is_not_interpreted_as_airborne(bits):
    w=JumpStartWatch.from_path(path(),MOVE,1000,{1002:B["J"]})
    s=state(1003,ground=False);s["hero"]["cstate"]=bits
    assert not w.observe(s) and w.seen_frame is None


def test_first_airborne_on_four_frame_boundary_is_valid_but_five_is_too_late():
    w=JumpStartWatch.from_path(path(),MOVE,1000,{1002:B["J"]})
    assert w.observe(state(1006,ground=False)) and w.failure(1006) is None
    late=JumpStartWatch.from_path(path(),MOVE,1000,{1002:B["J"]})
    assert not late.observe(state(1007,ground=False))
    assert late.failure(1007) is not None and late.seen_frame is None


def test_future_known_block_send_extends_only_to_last_actual_j_target_plus_four():
    w=JumpStartWatch.from_path(path(),MOVE,1000,{1002:B["J"],1003:B["J"]})
    assert w.failure(1007) is None and w.failure(1008) is not None
    assert w.targets==(1002,1003)


def test_queued_prefix_j_can_be_bound_only_by_the_successful_send_map():
    p=path();p.commands[:3]=[B["J"],B["J"],0]
    w=JumpStartWatch.from_path(p,MOVE,1000,{1001:B["J"]})
    assert w.targets==(1001,1002) and w.sent_targets=={1001}
    assert w.observe(state(1001,ground=False))


def test_invalid_path_coverage_raises_instead_of_silently_disabling_jump_watch():
    p=path();p.flags=p.flags[:-1]
    with pytest.raises(ValueError,match="coverage"):JumpStartWatch.from_path(p,MOVE,1000,{})


def test_grounded_planned_down_attack_requires_actual_applied_ground_slash():
    s=state(2657,ground=True,attacking=True,clip="SlashAlt",target=2657,desired=B["D"]|B["A"],latched=B["D"]|B["A"])
    assert grounded_strike(s,2657) is True
    s["act"]["applied"]=2659;s["f"]=2659
    assert grounded_strike(s,2657) is True  # late actual report, same target


@pytest.mark.parametrize("case",["idle","down_slash","not_attacking","air","missing_ground","wrong_target",
                                 "unapplied","future_applied","no_desired_a","no_latched_a","no_press"])
def test_ground_idle_receipts_and_unrelated_attacks_do_not_claim_a_grounded_strike(case):
    s=state(2657,ground=True,attacking=True,clip="SlashAlt",target=2657,desired=B["D"]|B["A"],latched=B["D"]|B["A"])
    press=2657
    if case=="idle":s["hero"]["anim"]["clip"]="Idle"
    elif case=="down_slash":s["hero"]["anim"]["clip"]="DownSlashAlt"
    elif case=="not_attacking":s=state(2657,ground=True,clip="SlashAlt",target=2657,desired=B["D"]|B["A"],latched=B["D"]|B["A"])
    elif case=="air":s=state(2657,ground=False,attacking=True,clip="SlashAlt",target=2657,desired=B["D"]|B["A"],latched=B["D"]|B["A"])
    elif case=="missing_ground":s["hero"].pop("cstate")
    elif case=="wrong_target":s["act"]["target"]=2658
    elif case=="unapplied":s["act"]["applied"]=2656
    elif case=="future_applied":s["act"]["applied"]=2658
    elif case=="no_desired_a":s["act"]["hf"]["desired"]=B["D"]
    elif case=="no_latched_a":s["act"]["hf"]["latched"]=B["D"]
    elif case=="no_press":press=None
    else:raise AssertionError(case)
    assert not grounded_strike(s,press)
