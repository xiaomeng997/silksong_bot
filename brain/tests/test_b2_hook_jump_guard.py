"""Critical pre-hook jump acceptance is stricter than transport coverage."""
from types import SimpleNamespace
import numpy as np
from ssbot.knowledge import kinematics as km
from ssbot.combat.knife_chain_b2 import NativeChainB2,B2Offer
from ssbot.combat.knife_chain_nominal import logical_copy,state_names
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from tests.test_b2_hook_start import actual,checked_fixture_path,MOVE,ORIGIN
from tests.test_knife_chain_b2 import runner


def prepared():
 n=NativeChainB2(runner_factory=runner,probe_ref="pre-hook-jump-guard")
 n.begin(actual(ORIGIN,target=ORIGIN,desired=B["R"]));n._receipts[ORIGIN+1]=B["R"]
 preview=n.runner.preview(ORIGIN,n._actual_state,True,True,t_game=0.,sim=None)
 draft=preview.draft;draft.run.chain="slam_claw";draft.run.link="pre"
 path=checked_fixture_path();path.flags[:2]=km.F_GROUND
 offer=B2Offer("commitment",path,draft,B["J"],10.,MOVE,{})
 n.planner_result(n.install(offer,SimpleNamespace(measurement_enabled=False)));n.final("plan",offer.mask)
 return n


def test_real_2973_equal_target_deadline_rejects_first_pre_hook_jump():
 n=prepared()
 # Same relative frame/target/received relation as actual2973 -> target2975,
 # received2975; an equal-frame STATE means that input Update already happened.
 replacement=n.before_send(frame=ORIGIN,target=ORIGIN+2,mask=B["J"],flags=0,received_frame=ORIGIN+2)
 assert replacement==0 and n.commitment is None and n._b2_selected is None
 assert MOVE in n._failed_hook_moves
 assert n.counts["b2_jump_send_veto"]==1 and n.counts["b2_controller_defect"]==1
 assert n._jump_start is None and n._hook_start is None
 assert n.sent().desired_mask==0
 assert n._receipts[ORIGIN+2]==0


def test_pre_hook_jump_before_target_stays_original_and_is_not_claimed_accepted():
 n=prepared()
 assert n.before_send(frame=ORIGIN,target=ORIGIN+2,mask=B["J"],flags=0,received_frame=ORIGIN+1) is None
 n.sent()
 assert n.commitment is not None and n._jump_start.seen_frame is None
 assert n._jump_start.sent_targets=={ORIGIN+2}


def at_hook(n,clip="Idle",air=False,vy=0.):
 n.begin(actual(ORIGIN+1))
 s=actual(ORIGIN+2,target=ORIGIN+2,desired=B["J"],clip=clip)
 names=state_names();i=names.index("onGround")
 if air:s["hero"]["cstate"][i//64]&=~(1<<(i%64))
 s["hero"]["vel"]=[0.,vy];n.begin(s)
 offer=B2Offer("active",None,logical_copy(n.runner),B["R"]|B["CLAW"],0.,MOVE,{})
 n.planner_result(n.install(offer,SimpleNamespace(measurement_enabled=False)));n.final("plan",offer.mask)
 return n.before_send(frame=ORIGIN+2,target=ORIGIN+4,mask=offer.mask,flags=0,received_frame=ORIGIN+2)


def test_claw_needs_takeoff_not_a_matching_jump_receipt():
 n=prepared();n.before_send(frame=ORIGIN,target=ORIGIN+2,mask=B["J"],flags=0,received_frame=ORIGIN);n.sent()
 assert at_hook(n)==0
 assert n.commitment is None and MOVE in n._failed_hook_moves
 assert n.counts["b2_jump_send_veto"]==1 and n.counts["b2_hook_start_sent"]==0


def test_harpoon_animation_cannot_launder_missing_jump_into_claw_acceptance():
 n=prepared();n.before_send(frame=ORIGIN,target=ORIGIN+2,mask=B["J"],flags=0,received_frame=ORIGIN);n.sent()
 assert at_hook(n,clip="Harpoon Antic",air=True)==0
 assert n.counts["b2_jump_start_seen"]==0 and n.commitment is None


def test_real_airborne_before_claw_preserves_original_hook_dispatch():
 n=prepared();n.before_send(frame=ORIGIN,target=ORIGIN+2,mask=B["J"],flags=0,received_frame=ORIGIN);n.sent()
 assert at_hook(n,clip="Airborne",air=True)==None
 assert n._jump_start.seen_frame==ORIGIN+2
 assert n.counts["b2_jump_send_veto"]==0 and n.commitment is not None
 n.sent();assert n._hook_start["sent_targets"]=={ORIGIN+4}


def test_ordinary_equal_frame_send_is_logged_late_without_changing_opt1():
 n=NativeChainB2(runner_factory=runner,probe_ref="late-diagnostic")
 n.begin(actual(ORIGIN,target=ORIGIN,desired=B["R"]));n.final("plan",B["R"])
 assert n.before_send(frame=ORIGIN,target=ORIGIN+2,mask=B["R"],flags=0,received_frame=ORIGIN+2) is None
 e=next(e for e in n.events if e["event"]=="b2_send_late")
 assert e["target_already_observed"] and n.learning_stop is None
