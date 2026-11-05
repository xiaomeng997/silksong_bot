"""A bounded shared strike exit and one same-owner air-dash approach."""
from copy import deepcopy
from types import SimpleNamespace as NS
import numpy as np
import pytest

from ssbot.combat import knife_chain_transfer as T
from ssbot.combat.air_chain import ChainSim
from ssbot.combat.knife_chain_air import body_box
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.knowledge import kinematics as K
from tests.test_knife_chain_transfer import fit_pose,transfer_motion_scene


def flight(*, x=27., y=10.12, vx=0., vy=10.2, target_x=36.5):
    r,s,old=transfer_motion_scene(K.M_NORMAL)
    params=K.hero2(old.params,on=True)
    s['hero'].update(pos=[x,y],box=[x-.25,y-1.553,x+.25,y+.532],vel=[vx,vy])
    s['hero']['tm']['dash_cd']=0.
    s['act']['hf'].update(latched=0,desired=0)
    fit_pose(s['ents'][1],t=20/60,x=target_x)
    r.run.v['idle_in_range']=[8,1000-20,16]  # this Run saw her in range at Idle k16: Will Evade shown False
    start=K.initial_state(params,x,y,vx=vx,vy=vy,ground=False)
    sim=ChainSim(start,np.array([0],np.int64),K.HoldState.from_act(s['act']),params,old.terrain,1000,1000)
    r.run.link='air';r.run.v.update(jump_k=0,jump_until=0,air_entry=True)
    return r,s,sim


def offer(r,s,sim):
    return T.propose(r,s,(s['f']-1000)/60.,sim,8,False,np.zeros((0,6)),set())


def test_far_air_entry_spends_dash_in_same_run_but_query_does_not_mutate_owner():
    r,s,sim=flight();before=deepcopy(r.run.v)
    made=offer(r,s,sim)
    assert made is not None and made[0] is not None
    draft,p,path,mask=made
    assert mask==B['R']|B['DASH']
    assert draft.run.chain=='rune_transfer' and draft.run.link=='air'
    assert p.move==T.TransferPlan(**{k:before[k] for k in T.TransferPlan.__dataclass_fields__
                                   if k in before},origin=1000,entry_k=0).move
    assert draft.run.v['air_dash_decided'] and draft.run.v['approach_recipe']=='air_dash'
    assert r.run.v==before and not path.assumptions['flight_checked']
    assert path.through==1002


@pytest.mark.parametrize('blocked',['spent','cooldown','ground_model','not_accepting','pending','held','queued','unknown_dash'])
def test_air_dash_keeps_actual_availability_and_inflight_edges(blocked):
    r,s,sim=flight()
    if blocked=='spent':sim.start[K.AIRDASHED]=1.
    elif blocked=='cooldown':sim.start[K.DASH_CD]=.2
    elif blocked=='ground_model':sim.start[K.GROUND]=1.
    elif blocked=='not_accepting':s['hero']['hero_accepting_input']=False
    elif blocked=='pending':sim.hold.pending[0,B['DASH'].bit_length()-1]=1
    elif blocked=='held':sim.hold.latched[0,B['DASH'].bit_length()-1]=True
    elif blocked=='queued':sim.prefix[0]=B['DASH']|B['R']
    elif blocked=='unknown_dash':sim.start[K.AIRDASHED]=float('nan')
    made=offer(r,s,sim)
    assert made is None or made[0] is None or not made[3]&B['DASH']


def test_air_dash_decision_is_not_repeated_after_successful_run_adoption():
    r,s,sim=flight();made=offer(r,s,sim);assert made[3]&B['DASH']
    r=made[0]  # production adopts this draft only after the send succeeds
    again=offer(r,s,sim)
    assert not again[3]&B['DASH'] and again[0].run.v['air_dash_decided']


def test_uncovered_coast_does_not_rebuild_a_long_probe_on_every_tick(monkeypatch):
    r,s,sim=flight(y=80.)
    calls=[];roll=sim.roll
    monkeypatch.setattr(sim,'roll',lambda commands:calls.append(commands.shape) or roll(commands))
    x=NS(obs=NS(sim=sim,ground=False,hero=s['hero'],e=s['ents'][1],k=2),
         v=r.run.v,cfg=r.chains['rune_transfer'].cfg)
    assert T.air_approach_keys(x)==B['R']
    assert T.air_approach_keys(x)==B['R']
    assert calls==[(1,r.chains['rune_transfer'].cfg['flight_check_frames'])]
    assert x.v['air_dash_decided'] and not x.v.get('approach_recipe')


def test_coast_that_can_reach_overhead_keeps_dash_and_direct_strike_has_priority():
    r,s,sim=flight(x=30.,y=15.,vx=8.25,vy=12.,target_x=35.)
    made=offer(r,s,sim)
    assert made[0] is not None and not made[3]&B['DASH']
    r,s,sim=flight(x=35.5,y=9.,vx=0.,vy=0.,target_x=36.5)
    row=T.press_now_row(sim,body_box(s['ents'][1]),1002,0,B['R'])
    assert row is not None
    made=offer(r,s,sim)
    assert made[0].run.link=='strike' and not made[3]&B['DASH']


def test_shared_strike_uses_bounded_velocity_variants_and_keeps_selected_absolute_row():
    r,s,sim=flight(x=39.,y=10.,vx=28.,vy=0.,target_x=36.5)
    row=T.press_now_row(sim,body_box(s['ents'][1]),1002,0,B['R'])
    assert row is not None and row['approach_direction'] in (0,-1)
    assert row['contact_frame']>1002 and len(row['contact_velocity'])==2
    made=offer(r,s,sim);assert made[0].run.link=='strike'
    chosen=deepcopy(made[0].run.v['row'])
    # Once the strike row is selected, a later target direction cannot retime it.
    s['f']=1001;sim.fo=sim.f=1001
    later=offer(made[0],s,sim)
    assert later[0].run.v['row']==chosen


def test_airborne_braking_is_not_applied_during_ground_sprint_jump_antic():
    r,s,sim=transfer_motion_scene(K.M_SPRINT)
    e=s['ents'][1];e['pos'][0]=32.
    made=T.propose(r,s,0.,sim,8,True,np.zeros((0,6)),set())
    assert made[0].run.link=='jump' and made[1].sprint_jump
    assert made[3]==B['R']|B['J']|B['DASH']


@pytest.mark.parametrize('owner,kind,complete',[(8,'body',True),(7,'move',True),(99,'delayed',True),(None,'other',False)])
def test_air_dash_does_not_exempt_destination_body_other_moves_or_delayed_hazards(monkeypatch,owner,kind,complete):
    from ssbot.combat import knife_chain_air_native as N
    from ssbot.combat.knife_chain_commitment import ContactScan,PathContact
    from tests.test_target_entry_attack import native
    r,s,sim=flight();r.run=None
    n=native();n.runner=r;n._transfer_ready=True;n._context=(None,None,None,np.zeros((0,6)))
    n._transfer_goal=T.TransferGoal(8,7,990,0.)
    monkeypatch.setattr(n,'queued_prefix',lambda *a:(0,'known test prefix'))
    scans=[]
    class Geo:
        def __init__(self,*a):pass
        def scan(self,path):
            scans.append(path)
            return ContactScan('fixture',path.origin,path.through,(PathContact(1002,owner,kind),),'all-owner',complete=complete)
        def preflight(self,path):raise AssertionError('air dash must not exempt the destination')
    monkeypatch.setattr(N,'B2Geometry',Geo)
    fc=NS(rs=NS(trk=NS(now={8:(None,None,None)})))
    assert n._transfer_offer(s,0.,sim,fc,NS(target=8),False) is None
    assert len(scans)==1 and n.runner.run is None and n.commitment is None and not n._receipts


@pytest.mark.parametrize('extra,complete,allowed',[(None,True,True),
    ((8,'delayed'),True,False),((7,'move'),True,False),(None,False,False)])
def test_air_dash_strike_keeps_original_target_contact_contract_without_false_recovery(monkeypatch,extra,complete,allowed):
    from ssbot.combat import knife_chain_air_native as N
    from ssbot.combat.knife_chain_commitment import ContactScan,PathContact
    from tests.test_target_entry_attack import native
    r,s,sim=flight(x=35.5,y=9.,target_x=36.5,vy=0.)
    r.run.v['approach_recipe']='air_dash'
    n=native();n.runner=r;n._transfer_ready=True;n._context=(None,None,None,np.zeros((0,6)))
    n._transfer_goal=T.TransferGoal(8,7,990,0.)
    monkeypatch.setattr(n,'queued_prefix',lambda *a:(0,'known test prefix'))
    recovered=[];monkeypatch.setattr(n,'_recover',lambda reason,f:recovered.append(reason))
    calls=[]
    class Geo:
        def __init__(self,*a):pass
        def _result(self,path,include_target):
            contacts=[PathContact(path.through,8,'body')] if include_target else []
            if extra is not None:contacts.append(PathContact(path.through,*extra))
            return ContactScan('fixture',path.origin,path.through,tuple(contacts),'contact-boundary fixture',complete=complete)
        def scan(self,path):calls.append('scan');return self._result(path,True)
        def preflight(self,path):calls.append('preflight');return self._result(path,False)
    monkeypatch.setattr(N,'B2Geometry',Geo)
    fc=NS(rs=NS(trk=NS(now={8:(None,None,None)})))
    made=n._transfer_offer(s,0.,sim,fc,NS(target=8),False)
    assert bool(made)==allowed and calls==['preflight']
    assert bool(recovered)==(not allowed)
    if allowed:
        assert made.draft.run.link=='strike' and made.move.target_iid==8
        assert made.draft.run.v['row']['contact_frame']>s['f']
        assert not n._failure_exposures and not n._failed_hook_moves and not n._receipts
