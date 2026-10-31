"""Deferred hook jump dispatch transactions; physics certified separately."""
from types import SimpleNamespace as NS
import pytest
from ssbot.combat.knife_chain_b2 import NativeChainB2,B2Offer
from ssbot.combat.knife_chain_nominal import logical_copy,state_names
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.knowledge import kinematics as km
from tests.test_b2_hook_start import actual,checked_fixture_path,MOVE,ORIGIN
from tests.test_knife_chain_b2 import runner


def deferred():
    n=NativeChainB2(runner_factory=runner,probe_ref='deferred-first-J')
    n.begin(actual(ORIGIN,target=ORIGIN,desired=B['R']));n._receipts[ORIGIN+1]=B['R']
    preview=n.runner.preview(ORIGIN,n._actual_state,True,True,t_game=0.,sim=None)
    draft=preview.draft;draft.run.chain='slam_claw';draft.run.link='pre'
    path=checked_fixture_path();path.commands[:]=0
    path.commands[:3]=B['R'];path.commands[3:6]=B['J'];path.commands[6:8]=B['R']|B['CLAW']
    path.latched=path.commands.copy();path.flags[:4]=km.F_GROUND
    offer=B2Offer('commitment',path,draft,B['R'],10.,MOVE,{})
    n.planner_result(n.install(offer,NS(measurement_enabled=False)));n.final('plan',offer.mask)
    assert n.before_send(frame=ORIGIN,target=ORIGIN+2,mask=B['R'],flags=0,received_frame=ORIGIN) is None
    n.sent()
    assert n._jump_start.targets==(ORIGIN+4,ORIGIN+5,ORIGIN+6)
    assert n._hook_start['targets']==(ORIGIN+7,ORIGIN+8)
    return n


def stage(n,f,mask,*,ground=True,clip='Idle',vy=0.,target=None,desired=None):
    raw=actual(f,target=ORIGIN+2 if target is None else target,desired=B['R'] if desired is None else desired,clip=clip)
    i=state_names().index('onGround')
    if ground:raw['hero']['cstate'][i//64]|=1<<(i%64)
    else:raw['hero']['cstate'][i//64]&=~(1<<(i%64))
    raw['hero']['vel']=[0.,vy]
    # Decision ticks may be skipped; critical STATE observations may not. These
    # synthetic receipts apply our own recorded sends exactly on their targets.
    history=[]
    for k in range(n.last_observed+1,f):
        t=max(t for t in n._receipts if t<=k)
        history.append(actual(k,target=t,desired=n._receipts[t]))
    n.begin(raw,history=history)
    assert n.runner.run is not None, list(n.events)[-12:]
    offer=B2Offer('active',None,logical_copy(n.runner),mask,0.,MOVE,{})
    n.planner_result(n.install(offer,NS(measurement_enabled=False)));n.final('plan',mask)
    return n


def test_active_first_J_already_received_is_vetoed_before_any_jump_send():
    n=deferred();watch=n._jump_start;stage(n,ORIGIN+2,B['J'])
    assert n.before_send(frame=ORIGIN+2,target=ORIGIN+4,mask=B['J'],flags=0,received_frame=ORIGIN+4)==0
    assert n.commitment is None and MOVE in n._failed_hook_moves
    assert watch.sent_targets==set() and n.counts['b2_controller_defect']==1
    assert n.sent().desired_mask==0 and n._receipts[ORIGIN+4]==0
    assert len(n._failure_exposures)==1


@pytest.mark.parametrize('shift',[1,2,3])
def test_skipped_first_J_is_not_retried_as_a_shorter_hop(shift):
    n=deferred();watch=n._jump_start;f=ORIGIN+2+shift
    stage(n,f,B['J'])
    assert n.before_send(frame=f,target=f+2,mask=B['J'],flags=0,received_frame=f)==0
    assert watch.sent_targets==set() and n.commitment is None and MOVE in n._failed_hook_moves
    reason=next(v['reason'] for v in n.events if v['event']=='b2_jump_send_veto')
    assert 'first' in reason and 'skipped' in reason
    assert n.sent().desired_mask==0 and len(n._failure_exposures)==1


def test_timely_first_J_then_real_Tplus1_jump_allows_original_CLAW():
    n=deferred();stage(n,ORIGIN+2,B['J'])
    assert n.before_send(frame=ORIGIN+2,target=ORIGIN+4,mask=B['J'],flags=0,received_frame=ORIGIN+2) is None
    n.sent();assert n._jump_start.sent_targets=={ORIGIN+4}
    n.begin(actual(ORIGIN+3,target=ORIGIN+2,desired=B['R']))
    stage(n,ORIGIN+4,B['J'],target=ORIGIN+4,desired=B['J'])
    assert n._jump_start.seen_frame is None
    assert n.before_send(frame=ORIGIN+4,target=ORIGIN+6,mask=B['J'],flags=0,received_frame=ORIGIN+4) is None
    n.sent()
    stage(n,ORIGIN+5,B['R']|B['CLAW'],ground=False,clip='Airborne',vy=18.6,target=ORIGIN+4,desired=B['J'])
    assert n._jump_start.seen_frame==ORIGIN+5
    assert n.before_send(frame=ORIGIN+5,target=ORIGIN+7,mask=B['R']|B['CLAW'],flags=0,received_frame=ORIGIN+5) is None
    n.sent();assert n._hook_start['sent_targets']=={ORIGIN+7}
    assert n.counts['b2_jump_send_veto']==0 and not n._failure_exposures


def test_wait_key_before_J_is_not_mistaken_for_skipped_jump():
    n=deferred();stage(n,ORIGIN+1,B['R'],target=ORIGIN+1,desired=B['R'])
    assert n.before_send(frame=ORIGIN+1,target=ORIGIN+3,mask=B['R'],flags=0,received_frame=ORIGIN+2) is None
    assert n.sent().desired_mask==B['R'] and not n._jump_start.sent_targets


def test_sent_jump_hold_is_not_treated_as_an_unsent_first_edge():
    n=deferred();stage(n,ORIGIN+2,B['J'])
    n.before_send(frame=ORIGIN+2,target=ORIGIN+4,mask=B['J'],flags=0,received_frame=ORIGIN+2);n.sent()
    stage(n,ORIGIN+3,B['J'],target=ORIGIN+2,desired=B['R'])
    assert n.before_send(frame=ORIGIN+3,target=ORIGIN+5,mask=B['J'],flags=0,received_frame=ORIGIN+3) is None
    n.sent();assert n._jump_start.sent_targets=={ORIGIN+4,ORIGIN+5}


def test_neutral_after_CLAW_send_keeps_existing_observation_wait_window():
    n=deferred();stage(n,ORIGIN+2,B['J'])
    n.before_send(frame=ORIGIN+2,target=ORIGIN+4,mask=B['J'],flags=0,received_frame=ORIGIN+2);n.sent()
    stage(n,ORIGIN+5,B['R']|B['CLAW'],ground=False,clip='Airborne',vy=18.6,target=ORIGIN+4,desired=B['J'])
    n.before_send(frame=ORIGIN+5,target=ORIGIN+7,mask=B['R']|B['CLAW'],flags=0,received_frame=ORIGIN+5);n.sent()
    stage(n,ORIGIN+6,0,ground=False,clip='Airborne',vy=17.,target=ORIGIN+4,desired=B['J'])
    assert n._hook_start['seen_frame'] is None and n._hook_start['sent_targets']=={ORIGIN+7}
    assert n.before_send(frame=ORIGIN+6,target=ORIGIN+8,mask=0,flags=0,received_frame=ORIGIN+8) is None
    assert n.commitment is not None and n.counts['b2_hook_send_veto']==0
