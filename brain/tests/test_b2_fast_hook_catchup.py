"""Real proposal wiring across a skipped decision, with synthetic STATEs.

The stubbed solver cases verify dispatch/KEEP ownership, not hit prediction.
A separate case invokes the real C5 and verifies an actual rollout occurred.
"""
from types import SimpleNamespace as NS
import numpy as np
import pytest
from ssbot.combat.air_chain import ChainSim
from ssbot.combat.claw_strike import CsPlan, ClawStrike
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.knowledge import kinematics as km
from tests.test_b2_fast_hook import HF
from dataclasses import replace
from ssbot.combat.knife_chain_hook_fast import plan_key
from tests.test_b2_deferred_dispatch_guard import deferred, MOVE, ORIGIN
from ssbot.combat.knife_chain_nominal import state_names
from tests.test_b2_hook_start import actual
from tests.test_knife_chain_b2 import params, terrain


def stage(n,f,mask,*,ground=True,clip='Idle',vy=0.,target=None,desired=None):
    # Observe a new decision without pre-installing any fabricated offer.
    raw=actual(f,target=target,desired=desired,clip=clip)
    i=state_names().index('onGround')
    if ground:raw['hero']['cstate'][i//64]|=1<<(i%64)
    else:raw['hero']['cstate'][i//64]&=~(1<<(i%64))
    raw['hero']['vel']=[0.,vy]
    history=[]
    for k in range(n.last_observed+1,f):
        t=max(t for t in n._receipts if t<=k)
        history.append(actual(k,target=t,desired=n._receipts[t]))
    n.begin(raw,history=history)


def context(n,f,params,terrain,*,air=False):
    s=n._actual_state
    S=km.initial_state(params,35.,4.568,ground=not air,facing=-1,silk=9,vy=18.6 if air else 0.)
    prefix,source=n.queued_prefix(f,s)
    assert prefix is not None,source
    sim=ChainSim(S,np.array([prefix],np.int64),km.HoldState.from_act(s.get("act")),params,terrain,f,f)
    n.prepare(s,ground=not air,accepting=True,sim=sim)
    return sim


def prepared(monkeypatch,params,terrain):
    # A synthetic prior checked commitment; this J itself must go through the
    # actual propose -> family fast primitive -> install -> send transaction.
    n=deferred();n.profile=replace(n.profile,fast_hook=True);n._fast_j_mode=True
    cs=CsPlan(ORIGIN+4,3,ORIGIN+7,7,wait_mask=B['R'])
    n.runner.run.v.update(cs=cs,cs_toward=1)
    s0=actual(ORIGIN,target=ORIGIN,desired=B['R'])
    n._ticks.append((ORIGIN,s0,1/60.,True,True));n._history_antic=7
    stage(n,ORIGIN+2,B['J'],target=ORIGIN+2,desired=B['R'])
    n._actual_state['act']['hf']={k:list(v) if isinstance(v,list) else v for k,v in HF.items()}
    sim=context(n,ORIGIN+2,params,terrain)
    path=n._committed_future;path.states[:]=sim.start[:,None]
    instance=object()
    fc=NS(rs=NS(trk=NS(now={7:(None,None,instance)},orphan_hazards={}),haz_raw={},raw={},layers={},bombs=None))
    n._fast_j_commit={'move':MOVE,'key':plan_key(cs),'path':path,'instance':instance,'owners':frozenset({7}),
        'hold_start':km.HoldState.from_hf(HF),'hold_known':True,
        'target':{'pos':(30.,7.449),'flip':True,'state':'Slam Antic','k':0}}
    monkeypatch.setattr(n,'_prepare_post_keys',lambda *a:None)  # unrelated fixture tail has no physics
    offer=n.propose(None,None,None,None,None,fc,None,None)
    assert offer is not None and offer.mask==B['J'] and n.counts['b2_fast_j']==1
    assert offer.details['fast_j']['tick']=='J' and not n._last_c5_calls
    n.planner_result(n.install(offer,NS(measurement_enabled=False)));n.final('plan',offer.mask)
    assert n.before_send(frame=ORIGIN+2,target=ORIGIN+4,mask=offer.mask,flags=0,received_frame=ORIGIN+2) is None
    n.sent()
    assert n._fast_j_sent['deferred'] is None and n._jump_start.sent_targets=={ORIGIN+4}
    return n,fc


@pytest.mark.parametrize('passed',[True,False])
def test_propose_catches_up_at_P_minus_one_then_original_CLAW_can_send(monkeypatch,params,terrain,passed):
    n,fc=prepared(monkeypatch,params,terrain);calls=[]
    prior=n.runner.run.v['cs']
    def solve(self,sim,ctx,ground,accepting,**kwargs):
        calls.append((sim.f,ctx.s_iid,ground,accepting,kwargs))
        return prior if passed else None
    monkeypatch.setattr(ClawStrike,'plan',solve)
    # No decision at ORIGIN+3, but all STATE observations remain intact.
    stage(n,ORIGIN+4,B['J'],target=ORIGIN+4,desired=B['J'])
    context(n,ORIGIN+4,params,terrain)
    offer=n.propose(None,None,None,None,None,fc,None,None)
    assert offer is not None,list(n.events)[-10:]
    assert offer.stage=='active' and offer.mask==B['R']|B['J']
    assert len(calls)==1 and calls[0][:4]==(ORIGIN+4,7,False,True)
    assert calls[0][4]['p_only']==ORIGIN+7 and calls[0][4]['hop_until']==ORIGIN+7
    assert calls[0][4]['hop_from']==ORIGIN+4 and calls[0][4]['hop_wait_mask']==B['R']
    assert n._fast_j_sent['deferred']['outcome']==('p_only_pass' if passed else 'lost_plan_kept')
    assert offer.draft.run.v['cs'] is not None and offer.draft.run.v['cs'].f_press==ORIGIN+7
    n.planner_result(n.install(offer,NS(measurement_enabled=False)));n.final('plan',offer.mask)
    assert n.before_send(frame=ORIGIN+4,target=ORIGIN+6,mask=offer.mask,flags=0,received_frame=ORIGIN+4) is None
    n.sent()
    stage(n,ORIGIN+5,B['R']|B['CLAW'],ground=False,clip='Airborne',vy=18.6,target=ORIGIN+4,desired=B['J'])
    context(n,ORIGIN+5,params,terrain,air=True)
    offer=n.propose(None,None,None,None,None,fc,None,None)
    assert offer.mask==B['R']|B['CLAW'] and len(calls)==1
    n.planner_result(n.install(offer,NS(measurement_enabled=False)));n.final('plan',offer.mask)
    assert n.before_send(frame=ORIGIN+5,target=ORIGIN+7,mask=offer.mask,flags=0,received_frame=ORIGIN+5) is None
    n.sent()
    assert n._hook_start['sent_targets']=={ORIGIN+7} and not n._failure_exposures
    assert n.counts['b2_fast_j_claw_veto']==0
    event=next(e for e in n.events if e['event']=='b2_fast_j_deferred_check')
    assert event['verdict']=='ran' and event['calls'][0]['source']=='late_fixed_plan_recheck'


def test_late_catchup_invokes_real_C5_rollout(monkeypatch,params,terrain):
    n,fc=prepared(monkeypatch,params,terrain)
    stage(n,ORIGIN+4,B['J'],target=ORIGIN+4,desired=B['J'])
    sim=context(n,ORIGIN+4,params,terrain)
    real=ChainSim.roll;rolls=[]
    def roll(self,commands,*a,**kw):
        rolls.append((self.f,np.asarray(commands).shape))
        return real(self,commands,*a,**kw)
    monkeypatch.setattr(ChainSim,'roll',roll)
    offer=n.propose(None,None,None,None,None,fc,None,None)
    assert offer is not None,list(n.events)[-10:]
    assert any(f==ORIGIN+4 and shape[0]>0 for f,shape in rolls)
    assert n._last_c5_calls and n._fast_j_sent['deferred'] is not None


def test_catchup_is_not_invented_after_the_fixed_P_is_no_longer_checkable(monkeypatch,params,terrain):
    n,fc=prepared(monkeypatch,params,terrain)
    stage(n,ORIGIN+5,B['R']|B['CLAW'],ground=False,clip='Airborne',vy=18.6,target=ORIGIN+4,desired=B['J'])
    context(n,ORIGIN+5,params,terrain,air=True)
    monkeypatch.setattr(ClawStrike,'plan',lambda *a,**kw:pytest.fail('fixed P is before the C5 candidate floor'))
    offer=n.propose(None,None,None,None,None,fc,None,None)
    assert offer is not None,list(n.events)[-10:]
    assert n._fast_j_sent['deferred'] is None
    n.planner_result(n.install(offer,NS(measurement_enabled=False)));n.final('plan',offer.mask)
    assert n.before_send(frame=ORIGIN+5,target=ORIGIN+7,mask=offer.mask,flags=0,received_frame=ORIGIN+5)==0
    assert n.counts['b2_fast_j_claw_veto']==1


@pytest.mark.parametrize('reason',['off','already_checked','other_move'])
def test_no_late_solver_without_this_moves_outstanding_obligation(monkeypatch,params,terrain,reason):
    from ssbot.combat.knife_chain_commitment import MoveInstance
    n,fc=prepared(monkeypatch,params,terrain)
    if reason=='off':n._fast_j_mode=False
    elif reason=='already_checked':n._fast_j_sent['deferred']={'frame':ORIGIN+3,'outcome':'p_only_pass'}
    else:n._fast_j_sent['move']=MoveInstance(99,ORIGIN,'CC_SLAM')
    stage(n,ORIGIN+4,B['R']|B['J'],target=ORIGIN+4,desired=B['J'])
    context(n,ORIGIN+4,params,terrain)
    monkeypatch.setattr(ClawStrike,'plan',lambda *a,**kw:pytest.fail('no outstanding deferred C5 for this Move'))
    assert n.propose(None,None,None,None,None,fc,None,None) is not None


def test_normal_J_plus_one_uses_table_recheck_once_without_catchup(monkeypatch,params,terrain):
    from dataclasses import replace
    n,fc=prepared(monkeypatch,params,terrain);calls=[];prior=n.runner.run.v['cs']
    def solve(self,sim,ctx,ground,accepting,**kwargs):
        calls.append(sim.f);return replace(prior)
    monkeypatch.setattr(ClawStrike,'plan',solve)
    stage(n,ORIGIN+3,B['J'],target=ORIGIN+2,desired=B['R'])
    context(n,ORIGIN+3,params,terrain)
    assert n.propose(None,None,None,None,None,fc,None,None) is not None
    assert calls==[ORIGIN+3] and n._fast_j_sent['deferred']['outcome']=='p_only_pass'
    assert 'source' not in n._last_c5_calls[0]
