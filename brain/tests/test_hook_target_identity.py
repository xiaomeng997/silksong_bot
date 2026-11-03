"""Present-observation hook identity; no empty-needle timing or hit credit."""
from copy import deepcopy
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat.knife_chain_hook_target import first_ray_body
from ssbot.combat.knife_chain_b2 import NativeChainB2,B2Offer
from ssbot.combat.knife_chain_commitment import MoveInstance
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.knowledge import kinematics as K
from tests.test_knife_chain_b2 import runner
from tests.test_shared_strike_approach import flight


def test_sp13_recorded_nearer_body_wins_over_planned_far_body():
    # Task105's existing fp3914780 control, in coordinates relative to floor.
    h=[35.063,2.94,35.563,5.019]
    bodies=[(22215358,[22.06,0.,25.65,4.63]),(22215352,[28.94,0.,32.53,3.90])]
    before=deepcopy((h,bodies))
    hit=first_ray_body(h,-1,bodies)
    assert hit[0]==22215352 and hit[1]==pytest.approx(2.783)
    assert (h,bodies)==before
    assert first_ray_body(h,-1,list(reversed(bodies)))==hit


def test_sp13_recorded_unobstructed_target_and_mirror_are_identified():
    h=[36.063,3.322,36.563,5.401];body=[22.69,0.,26.26,4.63]
    assert first_ray_body(h,-1,[(21638276,body)])[0]==21638276
    mirror=lambda b:[-b[2],b[1],-b[0],b[3]]
    assert first_ray_body(mirror(h),1,[(21638276,mirror(body))])[0]==21638276


@pytest.mark.parametrize('bodies',[
    [(1,[12.,0.,14.,4.])],  # behind the left-facing hero
    [(1,[-20.,0.,-18.,4.])],  # out of reach
    [(1,[7.,8.,9.,12.])],  # above the ray band
])
def test_empty_ray_does_not_identify_a_target(bodies):
    assert first_ray_body([9.75,1.,10.25,3.],-1,bodies) is None


@pytest.mark.parametrize('bodies',[
    [(1,None)],[(True,[7.,0.,9.,4.])],[(1,[7.,0.,9.,float('nan')])],
    [(1,[7.,0.,9.,4.]),(1,[3.,0.,5.,4.])],
    [(1,[7.,0.,9.,4.]),(2,[7.,0.,9.,4.])],
])
def test_unknown_or_tied_first_identity_is_not_resolved_by_entity_order(bodies):
    with pytest.raises(ValueError):first_ray_body([9.75,1.,10.25,3.],-1,bodies)


def setup_hook():
    _,s,sim=flight(x=35.313,y=7.508,target_x=23.8)
    for e,x0,x1,top in [(s['ents'][0],28.94,32.53,6.915),(s['ents'][1],22.06,25.65,7.645)]:
        e['pos']=[.5*(x0+x1),7.45]
        e['colliders']=[{'name':'Song Heavy Sentry','enabled':True,
                        'verts_world':[x0,3.015,x1,3.015,x1,top,x0,top]}]
    sim.start[K.FACE]=-1
    n=NativeChainB2(runner_factory=runner,probe_ref='first-hook-body')
    n.reset(0,start_frame=1000);n._actual_state=s;n._context=(None,sim,None,None)
    n._receipts[1001]=0
    move=MoveInstance(8,990,'CC_SLAM')
    draft=NS(run=NS(chain='slam_claw',link='pre',v={'cs':NS(f0=1000,f_press=1002)}))
    offer=B2Offer('active',None,draft,B['L']|B['CLAW'],0.,move,{})
    return n,s,sim,offer


@pytest.mark.parametrize('chain,stage,details',[
    ('slam_claw','active',{}),('vault_idle','active',{'distance_vault':True}),
    ('fixed_hook','fixed_commitment',{'fixed_hook':True}),
])
def test_common_before_send_veto_cannot_be_bypassed_by_hook_entry_or_old_plan(monkeypatch,chain,stage,details):
    n,s,sim,offer=setup_hook();offer.draft.run.chain=chain;offer.stage=stage;offer.details=details
    n._b2_selected=offer;n._fixed_jump_sent_for=offer.move
    calls=[]
    def veto(selected,**kw):calls.append((selected,kw));return 0
    monkeypatch.setattr(n,'_abort_hook_dispatch',veto)
    assert n.before_send(frame=1000,target=1002,mask=offer.mask,flags=0,received_frame=1000)==0
    assert calls[0][1]['event']=='b2_hook_target_veto'
    assert calls[0][1]['planned_target']==8 and calls[0][1]['first_target']==7
    assert n._receipts=={1001:0}  # a veto/query creates no successful send


def test_guard_allows_correct_first_body_and_skips_held_claw_without_retesting(monkeypatch):
    n,s,sim,offer=setup_hook();offer.move=MoveInstance(7,990,'CC_SLAM')
    reason,info=n._hook_target_check(offer,1000,1002,offer.mask)
    assert reason is None and info['first_target']==7
    n._receipts[1001]=B['CLAW'];n._context=None
    assert n._hook_target_check(offer,1000,1002,offer.mask) is None


@pytest.mark.parametrize('unknown',['missing_body','stale_model','no_model','prefix'])
def test_multi_clapper_hook_does_not_infer_unknown_identity(unknown):
    n,s,sim,offer=setup_hook()
    if unknown=='missing_body':s['ents'][0]['colliders']=[]
    elif unknown=='stale_model':sim.f=999
    elif unknown=='no_model':n._context=None
    else:n._receipts[1001]=B['R']
    reason,_=n._hook_target_check(offer,1000,1002,offer.mask)
    assert reason is not None and 'unchecked' in reason


def test_single_clapper_keeps_its_existing_admission():
    n,s,sim,offer=setup_hook();s['ents']=s['ents'][:1];n._context=None
    assert n._hook_target_check(offer,1000,1002,offer.mask) is None


@pytest.mark.parametrize('already_committed',[False,True])
def test_wrong_target_neutral_send_retains_failure_responsibility_without_hook_credit(already_committed):
    n,s,sim,offer=setup_hook();n.dispatch.frame=1000
    if already_committed:n.commitment={'move':offer.move,'origin':990,'ta':0.}
    else:offer.stage='commitment'
    n._b2_selected=offer;n.final('plan',offer.mask)
    assert n.before_send(frame=1000,target=1002,mask=offer.mask,flags=0,received_frame=1000)==0
    assert n.commitment is None and offer.move in n._failed_hook_moves
    assert len(n._failure_exposures)==int(already_committed)
    sent=n.sent()
    assert sent.desired_mask==0 and n._receipts[1002]==0
    assert len(n._failure_exposures)==1
    assert n._hook_start is None and n._press is None and n._hit is None
