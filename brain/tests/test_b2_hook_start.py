"""B2 must not advance an unstarted planned hook by its old clock.

Synthetic transaction fixtures test send/observation provenance and bounded
recovery. They do not certify the nominal hook model or a successful live retry.
"""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from ssbot.knowledge import kinematics as km
from ssbot.combat.knife_chain_b2 import NativeChainB2,B2Offer
from ssbot.combat.knife_chain_nominal import NominalPath,logical_copy
from ssbot.combat.knife_chain_commitment import MoveInstance
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.combat.air_chain import ChainSim
from tests.test_knife_chain_b2 import runner,raw,params,terrain

ORIGIN=2610
MOVE=MoveInstance(7,ORIGIN,"CC_SLAM")


def actual(f,*,target=None,desired=None,clip="Idle",accepting=True):
    s=raw(f);s["ents"][0]["fsms"][0]["t"]=(f-ORIGIN)/60
    if target is None:target=ORIGIN+1
    if desired is None:desired=B["R"]
    s["act"].update(target=target,applied=target,mask=desired,hf={"desired":desired})
    s["hero"]["anim"]={"clip":clip};s["hero"]["hero_accepting_input"]=accepting
    return s


def checked_fixture_path(*,hook=True):
    # A synthetic already-checked path isolates the transaction guard. The exact
    # live failure had CLAW mask targets 2614 and 2615 after a J at 2612.
    commands=np.zeros(51,np.int64)
    commands[:3]=[B["R"],B["J"],B["R"]|B["J"]]
    if hook:commands[3:5]=B["R"]|B["CLAW"]
    n=len(commands)
    return NominalPath(ORIGIN,"commitment",commands,commands.copy(),np.zeros((km.K,n+1)),
        np.tile([34.75,3.015,35.25,5.094],(n+1,1)),np.zeros((n+1,2)),np.zeros(n+1,np.int64),
        np.zeros(n+1,np.int64),np.arange(n+1)/60,None,None,None,0,"bounce",2657,2661,{},None,None)


def commit(*,hook=True):
    n=NativeChainB2(runner_factory=runner,probe_ref="hook-start-unit")
    s=actual(ORIGIN,target=ORIGIN,desired=B["R"]);n.begin(s);n._receipts[ORIGIN+1]=B["R"]
    preview=n.runner.preview(ORIGIN,s,True,True,t_game=0.,sim=None)
    draft=preview.draft
    assert draft.run is not None
    if hook:draft.run.chain="slam_claw";draft.run.link="pre"
    path=checked_fixture_path(hook=hook)
    offer=B2Offer("commitment",path,draft,B["J"],10.,MOVE,{})
    result=n.install(offer,SimpleNamespace(measurement_enabled=False))
    n.planner_result(result);n.final("plan",offer.mask)
    n.before_send(frame=ORIGIN,target=ORIGIN+2,mask=offer.mask,flags=0,received_frame=ORIGIN)
    assert n._hook_start is None  # install/prepared is not a successful send
    n.sent()
    return n


def send_claw(n,decision=2612):
    # Successful own send in the declared window, without claiming acceptance.
    target=decision+2
    n.begin(actual(decision,target=2612 if decision>=2612 else 2611,desired=B["J"] if decision>=2612 else B["R"]),
            history=[actual(2611)] if decision>2611 else [])
    offer=B2Offer("active",None,logical_copy(n.runner),B["R"]|B["CLAW"],0.,MOVE,{})
    result=n.install(offer,SimpleNamespace(measurement_enabled=False))
    n.planner_result(result);n.final("plan",offer.mask)
    n.before_send(frame=decision,target=target,mask=offer.mask,flags=0,received_frame=decision);n.sent()


def test_exact_2610_to_2614_gap_misses_both_hook_targets_and_recovers_before_preview(monkeypatch):
    n=commit()
    assert n._hook_start["targets"]==(2614,2615)
    assert n._hook_start["sent_targets"]==set()
    n.begin(actual(2614),history=[actual(f) for f in range(2611,2614)])
    monkeypatch.setattr(n,"_preview",lambda:pytest.fail("must recover before planned lock preview"))
    assert n.propose(None,None,None,None,None,None,None,None) is None
    assert n.commitment is None and n.runner.run is None and n.recovery is None
    assert MOVE in n._failed_hook_moves and n._hook_start is None
    defect=next(e for e in n.events if e["event"]=="b2_controller_defect")
    assert defect["planned_targets"]==[2614,2615] and defect["sent_targets"]==[]
    assert defect["no_retry_same_move"] is True


def test_last_original_hook_slot_remains_sendable_without_shifting_plan():
    n=commit()
    assert n._check_hook_start(2613) is False  # target2615 is still original slot
    assert n._hook_start["targets"]==(2614,2615)
    assert n._check_hook_start(2614) is True
    assert MOVE in n._failed_hook_moves


def test_sent_hook_is_not_accepted_and_waits_only_through_target_plus_four():
    n=commit();send_claw(n)
    assert n._hook_start["sent_targets"]=={2614}
    assert n._hook_start["seen_frame"] is None
    assert n._accepted is None and n._hit is None
    for f in range(2613,2619):
        n.begin(actual(f,target=2612 if f<2614 else 2614,desired=B["J"] if f<2614 else B["R"]|B["CLAW"]))
        assert n._check_hook_start(f) is False
    n.begin(actual(2619,target=2614,desired=B["R"]|B["CLAW"]))
    assert n._check_hook_start(2619) is True
    assert n.commitment is None and n._hook_start is None and MOVE in n._failed_hook_moves
    assert n.counts["b2_hook_start_sent"]==1 and n.counts["b2_hook_start_seen"]==0


def test_real_harpoon_observation_keeps_existing_inflight_recovery_not_ordinary_handoff():
    n=commit();send_claw(n)
    n.begin(actual(2613,target=2612,desired=B["J"]))
    n.begin(actual(2614,target=2614,desired=B["R"]|B["CLAW"],clip="Harpoon Antic",accepting=False))
    n.begin(actual(2615,target=2614,desired=B["R"]|B["CLAW"],clip="Harpoon Catch",accepting=False))
    assert n._hook_start["seen_frame"]==2614
    assert n._check_hook_start(2640) is False
    assert n.commitment is not None and n._hit is None and n.post_context is None
    n._recover("other actual interruption",2615)
    assert n.recovery is not None
    assert n.recovery["move"]==MOVE and n._hook_start is None
    assert MOVE not in n._failed_hook_moves


def test_non_hook_commitment_keeps_original_path():
    n=commit(hook=False)
    assert n._hook_start is None
    assert n._check_hook_start(2664) is False and n.commitment is not None
    assert not n._failed_hook_moves and n.counts["b2_controller_defect"]==0


def test_failed_hook_move_cannot_reenter_after_abandon_but_new_antic_can(params,terrain):
    def primed(f):
        n=NativeChainB2(runner_factory=runner,probe_ref="failed-move-unit")
        n._failed_hook_moves.add(MOVE)
        s=raw(f);n.begin(s);n._receipts[f+1]=0
        start=km.initial_state(params,35.,4.568,ground=True,facing=-1,silk=9)
        sim=ChainSim(start,np.zeros(1,np.int64),km.HoldState.idle(1),params,terrain,f,f)
        n.prepare(s,ground=True,accepting=True,sim=sim)
        return n
    old=primed(ORIGIN)
    assert old.runner.run is None and old._preview() is None
    assert old.counts["b2_no_candidate"]==1
    fresh=primed(2700)
    result=fresh._preview()
    assert result is not None and result[1]==MoveInstance(7,2700,"CC_SLAM")
    fresh.reset(1)
    assert not fresh._failed_hook_moves and fresh._hook_start is None


def test_old_hook_watch_does_not_attach_to_a_new_same_iid_slam():
    n=commit()
    n.commitment={**n.commitment,"move":MoveInstance(7,2700,"CC_SLAM")}
    assert n._check_hook_start(2700) is False
    assert n._hook_start is None and not n._failed_hook_moves


def test_actual_early_claw_from_same_commitment_is_not_ignored_when_harpoon_is_observed():
    n=commit();send_claw(n,decision=2611)  # actual target2613, planned2614/2615
    assert n._hook_start["sent_targets"]=={2613}
    event=next(e for e in n.events if e["event"]=="b2_hook_start_sent")
    assert event["in_planned_window"] is False
    assert n._hook_start["seen_frame"] is None
    n.begin(actual(2612,target=2612,desired=B["J"]))
    n.begin(actual(2613,target=2613,desired=B["R"]|B["CLAW"],clip="Harpoon Antic",accepting=False))
    assert n._hook_start["seen_frame"]==2613
    assert n._check_hook_start(2618) is False
    assert n.commitment is not None and not n._failed_hook_moves and n.post_context is None
