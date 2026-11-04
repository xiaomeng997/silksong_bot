"""Side intent reuses approach keys, then hands back before an attack."""
from dataclasses import replace
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import knife_chain_transfer as T
from ssbot.combat import knife_chain_air_native as N
from ssbot.combat.air_chain import ChainSim
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.combat.tactics.modes import EntryAttack, GoalPrefs
from ssbot.knowledge import kinematics as K
from tests.test_target_entry_attack import native
from tests.test_knife_chain_transfer import transfer_motion_scene


def fixture(*,air=False,active=False):
    r,s,sim=transfer_motion_scene(K.M_NORMAL)
    s['ents'][0]['fsms'][0].update(state='Slam Antic',t=.1)
    if not active:r.run=None
    else:r.run.v['_approach_only']=True
    if air:
        z=sim.start.copy().reshape(K.K);z[K.GROUND]=0;z[K.PY]=8.;z[K.VY]=-2.
        s['hero']['pos'][1]=8.;s['hero']['box'][1]=6.5;s['hero']['box'][3]=8.6
        s['hero']['vel'][1]=-2.
        sim=ChainSim(z,sim.prefix,sim.hold,sim.params,sim.terrain,1000,1000)
        if active:r.run.link='air';r.run.v['air_entry']=True;r.run.v['jump_until']=0
    n=native();n.runner=r;n._clock=.1
    entry=EntryAttack(8,'side',7,'CC_SLAM',4.,10.)
    p=GoalPrefs(mode='RUSH',stance_x=44.,weights={},target=8,entry_attack=entry)
    n.goal_preferences(s,p,handoff=True)
    n._context=(None,sim,None,None)
    n._transfer_goal=n._transfer_goal or T.TransferGoal(8,7,994,0.,'SWITCH',T.MoveInstance(7,994,'CC_SLAM'))
    fc=NS(rs=NS(trk=NS(T=.1,now={8:(None,None,None),7:(None,None,NS(fam='CC_SLAM',t0=0.))})))
    return n,s,sim,p,fc


def check_gate(monkeypatch,n,sim,blocked=False):
    monkeypatch.setattr(n,'queued_prefix',lambda *a:(int(sim.prefix[0]),'actual fixture prefix'))
    checks=[]
    monkeypatch.setattr(N.B2Geometry,'preflight',lambda self,path:
        checks.append(('external',path)) or NS(complete=not blocked,contacts=[]))
    monkeypatch.setattr(N.B2Geometry,'scan',lambda self,path:
        checks.append(('all owners',path)) or NS(complete=not blocked,contacts=[]))
    return checks


def test_side_binds_observed_source_and_reaches_actual_existing_route(monkeypatch):
    n,s,sim,p,fc=fixture();assert n._transfer_ready
    checks=check_gate(monkeypatch,n,sim)
    o=n._transfer_offer(s,.1,sim,fc,p,True)
    assert o is not None and o.draft.run.v['_approach_only'] and checks
    assert checks[0][0]=='all owners'
    assert not o.mask&(B['J']|B['A'])
    assert n.runner.run is None and n.commitment is None and not n._receipts


@pytest.mark.parametrize('mode',[K.M_DASH,K.M_SPRINT])
def test_side_keeps_inflight_dash_and_sprint_without_adding_jump(mode):
    r,s,sim=transfer_motion_scene(mode)
    made=T.propose(r,s,0.,sim,8,True,None,set(),approach_only=True)
    # An already active stomp is not reclassified by a fresh tactical intent.
    assert not made[0].run.v.get('_approach_only')
    r.run.v['_approach_only']=True
    made=T.propose(r,s,0.,sim,8,True,None,set())
    assert made[3]==B['R']|B['DASH'] and made[0].run.v['_approach_only']
    assert made[1].dash_k==10


def test_side_air_uses_actual_prefix_and_never_calls_stomp_search(monkeypatch):
    n,s,sim,p,fc=fixture(air=True)
    monkeypatch.setattr(T,'press_now_row',lambda *a,**k:pytest.fail('side searched a stomp'))
    checks=check_gate(monkeypatch,n,sim)
    o=n._transfer_offer(s,.1,sim,fc,p,False)
    assert o is not None and not o.mask&(B['J']|B['A']) and checks
    assert o.draft.run.link=='air'


@pytest.mark.parametrize('why',['arrived','expired','target','slam','jump'])
def test_active_side_approach_planned_handoff_clears_owner_without_failure(monkeypatch,why):
    n,s,sim,p,fc=fixture(active=True)
    check_gate(monkeypatch,n,sim)
    n.commitment={'move':T.MoveInstance(8,990,'RUNE_TRANSFER'),'origin':990,'ta':0.}
    n._press=997;n._accepted=998;n._hit=None
    if why=='arrived':s['hero']['pos'][0]=42.
    elif why=='expired':p=replace(p,entry_attack=None)
    elif why=='target':p=replace(p,target=7)
    else:s['ents'][1]['fsms'][0]['state']='Slam Antic' if why=='slam' else 'Jump Antic'
    monkeypatch.setattr(T,'propose',lambda *a,**k:pytest.fail('handoff emitted another approach key'))
    assert n._transfer_offer(s,.1,sim,fc,p,True) is None
    assert n.runner.run is None and n.commitment is None
    assert n._press is n._accepted is n._hit is None and not n._failure_exposures


def test_ground_near_side_does_not_claim_keyboard_or_send(monkeypatch):
    n,s,sim,p,fc=fixture();s['hero']['pos'][0]=42.
    monkeypatch.setattr(T,'propose',lambda *a,**k:pytest.fail('already arrived'))
    assert n._transfer_offer(s,.1,sim,fc,p,True) is None
    assert n.runner.run is None and n.commitment is None and not n._receipts


def test_side_current_step_unknown_keeps_existing_active_recovery(monkeypatch):
    n,s,sim,p,fc=fixture(active=True)
    check_gate(monkeypatch,n,sim,blocked=True)
    reasons=[];monkeypatch.setattr(n,'_recover',lambda reason,f:reasons.append(reason))
    assert n._transfer_offer(s,.1,sim,fc,p,True) is None
    assert reasons==['rune transfer external step blocked']


@pytest.mark.parametrize('missing',['clock','source','hf','prefix'])
def test_side_intent_cannot_override_missing_actual_evidence(monkeypatch,missing):
    n,s,sim,p,fc=fixture()
    check_gate(monkeypatch,n,sim)
    if missing=='clock':fc.rs.trk.now[7]=(None,None,NS(fam='CC_SLAM',t0=10.))
    elif missing=='source':fc.rs.trk.now.pop(7)
    elif missing=='hf':s['act']['hf'].pop('age')
    else:monkeypatch.setattr(n,'queued_prefix',lambda *a:(B['L'],'mismatch'))
    assert n._transfer_offer(s,.1,sim,fc,p,True) is None
    assert n.commitment is None and not n._receipts


def test_side_proposal_front_door_reaches_approach_adapter(monkeypatch):
    n,s,sim,p,fc=fixture()
    n._context=((1000,s,.1,True,True),sim,None,None)
    got=[];sentinel=object()
    monkeypatch.setattr(n,'_transfer_offer',lambda *a:got.append(a) or sentinel)
    assert n._propose(None,None,None,None,None,fc,p,None) is sentinel
    assert got[0][0] is s and got[0][-1] is True


def test_fresh_ground_side_does_not_erase_a_queued_jump():
    n,s,sim,p,fc=fixture()
    sim=ChainSim(sim.start,np.array([B['R']|B['J']],np.int64),sim.hold,sim.params,sim.terrain,1000,1000)
    assert T.propose(n.runner,s,.1,sim,8,True,None,set(),n._transfer_goal,approach_only=True) is None


def test_air_side_releases_existing_jump_without_claiming_a_new_jump_or_strike():
    n,s,sim,p,fc=fixture(air=True)
    s['act']['hf']['latched']|=B['J'];s['act']['hf']['desired']|=B['J']
    z=sim.start.copy().reshape(K.K);z[K.JUMPING]=1.;z[K.JSTEPS]=9.;z[K.JHELD]=1.;z[K.PREV]=B['R']|B['J']
    sim=ChainSim(z,np.array([B['R']|B['J']],np.int64),K.HoldState.from_act(s['act']),sim.params,sim.terrain,1000,1000)
    made=T.propose(n.runner,s,.1,sim,8,False,None,set(),n._transfer_goal,approach_only=True)
    assert made is not None and made[0] is not None
    assert made[0].run.link=='air' and not made[3]&(B['J']|B['A'])


def test_side_air_landing_keeps_dash_route_without_scheduling_a_stomp():
    n,s,sim,p,fc=fixture(active=True)
    n.runner.run.link='air';n.runner.run.v['air_entry']=True;n.runner.run.v['jump_until']=0
    made=T.propose(n.runner,s,.1,sim,8,True,None,set(),n._transfer_goal)
    assert made is not None and made[0] is not None
    assert made[0].run.link=='walk' and made[0].run.v['_approach_only']
    assert not made[3]&(B['J']|B['A'])
