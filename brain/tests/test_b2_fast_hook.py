"""Opt-in first-J deferral: precise eligibility, real-send ownership and C5 backstop."""
from dataclasses import replace
from types import SimpleNamespace as NS
import numpy as np
import pytest
from ssbot.combat import knife_chain_hook_fast as fast
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.combat.claw_strike import CsPlan
from ssbot.knowledge import kinematics as km
from ssbot.combat.knife_chain_commitment import MoveInstance
from ssbot.combat.knife_chain_eval import ChainObservationNotReady
from tests.test_b2_deferred_dispatch_guard import deferred,stage,MOVE,ORIGIN


HF={'latched':B['R'],'desired':B['R'],'pending':[0]*22,'age':[255]*22}


def eligible(kind='J'):
    """Fresh-check inputs that pass: the wait tick (target J-1) or the first-J tick (target J)."""
    n=deferred();n.profile=replace(n.profile,fast_hook=True);n._fast_j_mode=True
    f=ORIGIN+2 if kind=='J' else ORIGIN+1
    if kind=='J':stage(n,f,B['J'])
    else:stage(n,f,B['R'],target=ORIGIN+1,desired=B['R'])
    n._actual_state['act']['hf']=dict(HF,pending=list(HF['pending']),age=list(HF['age']))
    cs=CsPlan(ORIGIN+4,3,ORIGIN+7,7,wait_mask=B['R']);n.runner.run.v['cs']=cs
    path=n._committed_future;S=np.zeros(km.K);S[km.PX]=35.;S[km.PY]=4.568;S[km.GROUND]=1;S[km.FACE]=-1
    path.states[:]=S[:,None]
    model=NS(start=S,prefix=np.array([B['R']]),f=f,fo=f,hold=km.HoldState.from_hf(HF))
    n._context=((f,n._actual_state,(f-ORIGIN)/60,True,True),model,None,None)
    instance=object();rs=NS(trk=NS(now={7:(None,None,instance)},orphan_hazards={}),haz_raw={},raw={},layers={},bombs=None)
    fc=NS(rs=rs)
    n._fast_j_commit={'move':MOVE,'key':fast.plan_key(cs),'path':path,'instance':instance,'owners':frozenset({7}),
                      'hold_start':km.HoldState.from_hf(HF),'hold_known':True,
                      'target':{'pos':(30.,7.449),'flip':True,'state':'Slam Antic','k':0}}
    return n,fc


def test_eligible_first_J_has_private_context_without_mutating_the_run():
    n,fc=eligible();cs=n.runner.run.v['cs'];r=fast.admit(n,fc)
    assert r['mask']==B['J'] and r['key']==fast.plan_key(cs) and not r['used']
    assert n.runner.run.v['cs'] is cs and not n._jump_start.sent_targets


@pytest.mark.parametrize('which',['move','key','prefix','receipt','latch','owner','target','position','velocity','nonfinite','accepting','state_shape','unknownowners'])
def test_fresh_input_or_instance_mismatch_returns_full_path(which):
    n,fc=eligible();sim=n._context[1]
    if which=='move':n._fast_j_commit['move']=MoveInstance(7,ORIGIN-100,'CC_SLAM')
    elif which=='key':n.runner.run.v['cs'].f_press+=1
    elif which=='prefix':sim.prefix[0]=B['L']
    elif which=='receipt':n._receipts[ORIGIN+1]=B['L']
    elif which=='latch':n._actual_state['act']['hf']['latched']=None
    elif which=='owner':fc.rs.haz_raw[99]=object()
    elif which=='target':fc.rs.trk.now[7]=(None,None,object())
    elif which=='position':sim.start[km.PX]+=.050001
    elif which=='velocity':sim.start[km.VX]+=.500001
    elif which=='nonfinite':sim.start[km.PX]=np.nan
    elif which=='state_shape':sim.start=np.zeros(1)
    elif which=='unknownowners':fc.rs.haz_raw=None
    elif which=='accepting':
        t=n._context[0];n._context=((t[0],t[1],t[2],t[3],False),sim,None,None)
    assert fast.admit(n,fc) is None
    assert n.counts['b2_fast_j_fallback']==1


def test_outside_KEEP_cannot_defer_a_recheck_that_can_abort():
    n,fc=eligible();n.runner.run.v['cs'].f_press=ORIGIN+9
    n._fast_j_commit['key']=fast.plan_key(n.runner.run.v['cs'])
    assert fast.admit(n,fc) is None


def test_waiting_tick_is_eligible_and_keeps_the_stable_wait_key():
    n,fc=eligible('wait');r=fast.admit(n,fc)
    assert r['tick']=='wait' and r['mask']==B['R'] and not n._jump_start.sent_targets
    n,fc=eligible('J');assert fast.admit(n,fc)['tick']=='J'


def test_observation_readiness_is_still_required_for_the_primitive(monkeypatch):
    from ssbot.combat import knife_chain_slam as slam
    cs=CsPlan(10,3,13,7);ctx={'key':fast.plan_key(cs),'used':False}
    x=NS(R=NS(anchor=NS(b2_fast_j=ctx,b2_c5_calls=[])),v={'cs':cs},tmp={})
    monkeypatch.setattr(slam,'_cs_ctx',lambda x:(_ for _ in ()).throw(ChainObservationNotReady('missing current state')))
    with pytest.raises(ChainObservationNotReady):slam.pl_claw(x,'tmp.out',False,True,hop_until=13,p_only=13)
    assert not ctx['used']


def test_primitive_only_reuses_the_exact_p_only_hop_request(monkeypatch):
    from ssbot.combat import knife_chain_slam as slam
    cs=CsPlan(10,3,13,7);ctx={'key':fast.plan_key(cs),'used':False};calls=[]
    x=NS(R=NS(anchor=NS(b2_fast_j=ctx,b2_c5_calls=calls,b2_strict_observations=False)),v={'cs':cs},tmp={},obs=NS(sim=None))
    monkeypatch.setattr(slam,'_cs_ctx',lambda x:None)
    monkeypatch.setattr(slam,'_csx',lambda x:pytest.fail('no full C5 on exact fast request'))
    slam.pl_claw(x,'tmp.out',False,True,hop_until=13,p_only=13)
    assert ctx['used'] and x.tmp['out'] is cs and not calls


def test_different_p_only_executes_actual_full_solver_and_records_failure(monkeypatch):
    from ssbot.combat import knife_chain_slam as slam
    cs=CsPlan(10,3,13,7);ctx={'key':fast.plan_key(cs),'used':False};calls=[]
    x=NS(R=NS(anchor=NS(b2_fast_j=ctx,b2_c5_calls=calls,b2_strict_observations=False)),v={'cs':cs},tmp={},obs=NS(sim=None))
    monkeypatch.setattr(slam,'_cs_ctx',lambda x:None)
    monkeypatch.setattr(slam,'_csx',lambda x:NS(params=object(),plan=lambda *a,**k:None))
    slam.pl_claw(x,'tmp.out',False,True,hop_until=13,p_only=14)
    assert not ctx['used'] and x.tmp['out'] is None and calls==[{'p_only':14,'ok':False}]


def sent_fast_J():
    n=deferred();n.profile=replace(n.profile,fast_hook=True);n._fast_j_mode=True
    stage(n,ORIGIN+2,B['J']);n._b2_selected.details['fast_j']={'key':[ORIGIN+4,3,ORIGIN+7,B['R']]}
    n.before_send(frame=ORIGIN+2,target=ORIGIN+4,mask=B['J'],flags=0,received_frame=ORIGIN+2);n.sent()
    assert n._fast_j_sent['deferred'] is None
    return n


def test_no_CLAW_without_a_later_full_C5_after_a_fast_J():
    n=sent_fast_J();stage(n,ORIGIN+5,B['R']|B['CLAW'],ground=False,clip='Airborne',vy=18.6,target=ORIGIN+4,desired=B['J'])
    assert n.before_send(frame=ORIGIN+5,target=ORIGIN+7,mask=B['R']|B['CLAW'],flags=0,received_frame=ORIGIN+5)==0
    assert n.sent().desired_mask==0 and len(n._failure_exposures)==1 and n._fast_j_sent is None


def test_actual_full_failure_is_recorded_ran_and_KEEP_is_not_called_pass():
    n=sent_fast_J();n._last_c5_calls=[{'p_only':ORIGIN+7,'ok':False},{'p_only':None,'ok':False}]
    n._fast_j_record_deferred(ORIGIN+3,MOVE)
    assert n._fast_j_sent['deferred']['outcome']=='lost_plan_kept'
    row=next(e for e in n.events if e['event']=='b2_fast_j_deferred_check')
    assert row['verdict']=='ran'
    stage(n,ORIGIN+5,B['R']|B['CLAW'],ground=False,clip='Airborne',vy=18.6,target=ORIGIN+4,desired=B['J'])
    assert n.before_send(frame=ORIGIN+5,target=ORIGIN+7,mask=B['R']|B['CLAW'],flags=0,received_frame=ORIGIN+5) is None


def test_different_move_or_same_frame_full_call_cannot_pay_back_the_skip():
    n=sent_fast_J();n._last_c5_calls=[{'p_only':ORIGIN+7,'ok':True}]
    n._fast_j_record_deferred(ORIGIN+2,MOVE)
    n._fast_j_record_deferred(ORIGIN+3,MoveInstance(99,ORIGIN,'CC_SLAM'))
    assert n._fast_j_sent['deferred'] is None


def test_feature_defaults_off_and_A_never_uses_it():
    from ssbot.combat.knife_chain_b2 import NativeChainB2
    from ssbot.combat.knife_chain_nominal import NominalProfile
    from tests.test_knife_chain_b2 import runner
    assert not deferred()._fast_j_mode
    n=NativeChainB2(runner_factory=runner,probe_ref='test',arm='A',profile=NominalProfile(fast_hook=True))
    assert not n._fast_j_mode and n._fast_j_sent is None


def test_fast_hook_is_a_bound_control_value_and_changes_the_behavior_digest(tmp_path):
    from tests.test_b2_manifest_bindings import package,env,policy,manifest
    root=package(tmp_path);e=env(SSBOT_FORUM_CHAIN_FAST_HOOK="0");p=policy(e)
    a=manifest(root,p,e)
    assert a['configuration_complete']
    effective=a['switches']['SSBOT_FORUM_CHAIN_FAST_HOOK']['effective']
    assert effective=={'policy.chain_native.profile.fast_hook':False}
    e2={**e,'SSBOT_FORUM_CHAIN_FAST_HOOK':'1'};q=policy(e2);q.chain_native.profile.fast_hook=True
    b=manifest(root,q,e2)
    assert b['configuration_complete'] and a['behavior_sha256']!=b['behavior_sha256']
