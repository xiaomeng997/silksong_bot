"""One all-owner admission of the observed source hammer's remaining tail."""
from dataclasses import replace
from types import SimpleNamespace as NS
from copy import deepcopy

import numpy as np
import pytest

from ssbot.combat import knife_chain_air_native as N
from ssbot.combat.knife_chain_air import AirAnchor, model_path
from ssbot.combat.knife_chain_commitment import MoveInstance, ContactScan, PathContact
from ssbot.combat.knife_chain_eval import Run
from ssbot.combat.knife_chain_transfer import TransferGoal, predicted_tail_end
from ssbot.combat.air_chain import ChainSim
from ssbot.knowledge import kinematics as K
from tests.test_target_entry_attack import native
from tests.test_knife_chain_transfer import cast_scene, plan, transfer_motion_scene


@pytest.mark.parametrize('phase,age,end', [
    ('Slam Antic', 0., 3393), ('Slam 0', 0., 3344),
    ('Slam 1', 0., 3339), ('Slam Effects?', 0., 3336),
    ('Slam 2', .05, 3333), ('Slam Recover', 0., None),
    ('Slam 2', .3, None), ('Slam 1', None, None), ('Slam 1', float('nan'), None),
])
def test_remaining_tail_uses_family_frames_not_global_dwell_or_future(phase, age, end):
    s=cast_scene();s['f']=3330;s['ents'][0]['fsms'][0].update(state=phase,t=age)
    goal=TransferGoal(8,7,3330,0.,'BOUNCE',MoveInstance(7,3276,'CC_SLAM'))
    assert predicted_tail_end(s,goal)==end


def fixture(monkeypatch,*,contact=None,complete=True,shift=0.):
    r,s,old=transfer_motion_scene(K.M_NORMAL);r.run=None
    s['hero'].update(pos=[25.,14.],box=[24.75,12.45,25.25,14.53],vel=[8.25,0.])
    s['ents'][0]['fsms'][0].update(state='Slam 1',t=0.)
    S=K.initial_state(old.params,25.,14.,vx=8.25,ground=False)
    sim=ChainSim(S,old.prefix,old.hold,old.params,old.terrain,1000,1000)
    n=native();n._clock=1.;n.runner=r;n._transfer_ready=True
    n._transfer_goal=TransferGoal(8,7,1000,.1,'BOUNCE',MoveInstance(7,946,'CC_SLAM'))
    n._context=(None,None,None,np.zeros((0,6)))
    fc=NS(rs=NS(trk=NS(T=1.,now={8:(None,None,None),7:(None,None,NS(fam='CC_SLAM',t0=.1+shift))})))
    scans=[];short=[]
    class Geo:
        def __init__(self,*a):pass
        @staticmethod
        def ref(p):return str(p.origin)+':'+str(p.through)
        def scan(self,p):
            if len(p.commands)<=2:
                short.append(p)
                now=getattr(self,'current_contact',None)
                return ContactScan(self.ref(p),p.origin,p.through,() if now is None else (now,),'all-owner current-step fixture')
            scans.append(p)
            return ContactScan(self.ref(p),p.origin,p.through,() if contact is None else (contact,),
                               'all-owner fixture',complete=complete)
        def preflight(self,p):
            raise AssertionError('a post-bounce tail cannot exempt the destination')
    monkeypatch.setattr(N,'B2Geometry',Geo)
    monkeypatch.setattr(n,'queued_prefix',lambda *a:(int(old.prefix[0]),'actual known fixture prefix'))
    def offer(*args,**kw):
        _,state,game,current_sim,*_=args
        p=replace(plan(),ta=1.,origin=state['f'],entry_k=int(round((game-1.)*60.)))
        draft=r.fork_empty(AirAnchor());v=p.variables()
        if n.runner.run is not None:v.update(n.runner.run.v)
        draft.run=Run('rune_transfer','bounce_tail',v)
        path=model_path(current_sim,p,np.array([0],np.int64),game)
        return draft,p,path,0
    monkeypatch.setattr(N.transfer,'propose',offer)
    return n,s,sim,fc,scans,short


@pytest.mark.parametrize('contact,complete,allowed', [
    (None,True,True), (None,False,False),
    (PathContact(1005,7,'move'),True,False),
    (PathContact(1005,8,'body'),True,False),
    (PathContact(1005,99,'delayed'),True,False),
])
def test_first_bounce_scans_whole_neutral_tail_with_no_owner_exemption(monkeypatch,contact,complete,allowed):
    n,s,sim,fc,scans,short=fixture(monkeypatch,contact=contact,complete=complete)
    offer=n._transfer_offer(s,1.,sim,fc,NS(target=8),False)
    assert (offer is not None)==allowed
    assert len(scans)==1 and scans[0].through==1010
    assert np.all(scans[0].commands[1:]==0)
    assert bool(short)==allowed
    if allowed:
        assert offer.draft.run.v['source_tail_admitted']
        assert offer.details['tail_checked_through']==1010
        assert n.runner.run is None and n.commitment is None and not n._transfer_finished
    else:
        assert (7,1000) in n._transfer_finished
    assert not n._receipts  # a query/decline is never a send


@pytest.mark.parametrize('shift', [1.,float('nan')])
def test_fresh_tail_does_not_follow_a_new_or_unknown_source_instance(monkeypatch,shift):
    n,s,sim,fc,scans,short=fixture(monkeypatch,shift=shift)
    assert n._transfer_offer(s,1.,sim,fc,NS(target=8),False) is None
    assert not scans and not short and (7,1000) in n._transfer_finished


def test_declined_or_delayed_bounce_does_not_retry_admission_later(monkeypatch):
    n,s,sim,fc,scans,short=fixture(monkeypatch)
    n._transfer_goal=replace(n._transfer_goal,cast_fa=999)
    assert n._transfer_offer(s,1.,sim,fc,NS(target=8),False) is None
    assert not scans and (7,999) in n._transfer_finished


def test_admitted_run_keeps_current_checks_without_repeating_the_long_scan(monkeypatch):
    n,s,sim,fc,scans,short=fixture(monkeypatch)
    first=n._transfer_offer(s,1.,sim,fc,NS(target=8),False)
    n.runner=first.draft
    s=deepcopy(s);s['f']=1001
    current=ChainSim(sim.start,sim.prefix,sim.hold,sim.params,sim.terrain,1001,1001)
    fc.rs.trk.T=n._clock=1.+1/60.
    second=n._transfer_offer(s,n._clock,current,fc,NS(target=8),False)
    assert second is not None and len(scans)==1 and len(short)==2
    assert second.details['tail_checked_through']==1010


@pytest.mark.parametrize('kind',['body','move','delayed'])
def test_admitted_tail_still_checks_current_destination_and_delayed_dangers(monkeypatch,kind):
    n,s,sim,fc,scans,short=fixture(monkeypatch)
    first=n._transfer_offer(s,1.,sim,fc,NS(target=8),False)
    n.runner=first.draft
    s=deepcopy(s);s['f']=1001
    current=ChainSim(sim.start,sim.prefix,sim.hold,sim.params,sim.terrain,1001,1001)
    fc.rs.trk.T=n._clock=1.+1/60.
    monkeypatch.setattr(N.B2Geometry,'current_contact',PathContact(1002,8,kind),raising=False)
    assert n._transfer_offer(s,n._clock,current,fc,NS(target=8),False) is None
    assert len(scans)==1 and len(short)==2


@pytest.mark.parametrize('facing,key', [(-1, 2097152), (1, 1048576)])
def test_antic_tail_moves_to_sources_back_instead_of_neutral_wait(monkeypatch,facing,key):
    n,s,sim,fc,scans,short=fixture(monkeypatch)
    s['ents'][0]['fsms'][0].update(state='Slam Antic',t=0.)
    fc.rs.trk.now[7][2].s=facing
    offer=n._transfer_offer(s,1.,sim,fc,NS(target=8),False)
    assert offer is not None
    assert offer.mask==key and offer.draft.run.v['source_tail_mask']==key
    assert np.all(scans[0].commands[1:]==key)
    assert short[0].commands[1]==key
    assert offer.details['tail_mask']==key
    assert not key & (1|4|524288)  # no jump, dash or attack in this tail
    assert not n._receipts


@pytest.mark.parametrize('facing',[None,0,float('nan'),True])
def test_antic_tail_with_unknown_facing_cannot_choose_a_side(monkeypatch,facing):
    n,s,sim,fc,scans,short=fixture(monkeypatch)
    s['ents'][0]['fsms'][0].update(state='Slam Antic',t=0.)
    fc.rs.trk.now[7][2].s=facing
    assert n._transfer_offer(s,1.,sim,fc,NS(target=8),False) is None
    assert not scans and not short and not n._receipts


@pytest.mark.parametrize('owner,kind', [(7,'move'),(8,'body'),(99,'delayed')])
def test_moving_antic_tail_still_requires_all_owner_whole_path_scan(monkeypatch,owner,kind):
    n,s,sim,fc,scans,short=fixture(monkeypatch,contact=PathContact(1005,owner,kind))
    s['ents'][0]['fsms'][0].update(state='Slam Antic',t=0.)
    fc.rs.trk.now[7][2].s=-1
    assert n._transfer_offer(s,1.,sim,fc,NS(target=8),False) is None
    assert len(scans)==1 and not short and not n._receipts
    assert np.all(scans[0].commands[1:]==2097152)


def test_admitted_moving_tail_holds_original_key_without_another_long_scan(monkeypatch):
    n,s,sim,fc,scans,short=fixture(monkeypatch)
    s['ents'][0]['fsms'][0].update(state='Slam Antic',t=0.)
    fc.rs.trk.now[7][2].s=-1
    first=n._transfer_offer(s,1.,sim,fc,NS(target=8),False)
    assert first is not None and first.mask==2097152
    n.runner=first.draft
    s=deepcopy(s);s['f']=1001
    current=ChainSim(sim.start,sim.prefix,sim.hold,sim.params,sim.terrain,1001,1001)
    fc.rs.trk.T=n._clock=1.+1/60.
    # A later facing value cannot silently change the already admitted recipe.
    fc.rs.trk.now[7][2].s=1
    second=n._transfer_offer(s,n._clock,current,fc,NS(target=8),False)
    assert second is not None and second.mask==2097152
    assert len(scans)==1 and len(short)==2
    assert second.draft.run.v['source_tail_mask']==2097152


@pytest.mark.parametrize('tail_mask',[0,1048576,2097152])
def test_real_tail_table_reproduces_admitted_mask(tail_mask):
    from ssbot.combat.knife_chain_transfer import propose
    r,s,old=transfer_motion_scene(K.M_NORMAL)
    s['hero'].update(pos=[25.,14.],box=[24.75,12.45,25.25,14.53],vel=[8.25,0.])
    s['ents'][0]['fsms'][0].update(state='Slam 1',t=0.)
    S=K.initial_state(old.params,25.,14.,vx=8.25,ground=False)
    sim=ChainSim(S,old.prefix,old.hold,old.params,old.terrain,1000,1000)
    variables=plan().variables();variables.update(side=2097152,source_tail_mask=tail_mask,source_tail_admitted=True,air_entry=True)
    r.run=Run('rune_transfer','bounce_tail',variables)
    goal=TransferGoal(8,7,1000,.1,'BOUNCE',MoveInstance(7,946,'CC_SLAM'))
    made=propose(r,s,1.,sim,8,False,np.zeros((0,6)),set(),goal)
    assert made is not None and made[0].run.link=='bounce_tail'
    assert made[3]==tail_mask and made[2].commands[1]==tail_mask
    # Once the actual source hammer is gone, its old movement key must not leak
    # into the destination's existing approach/strike generator.
    s['ents'][0]['fsms'][0].update(state='Idle',t=0.)
    s['ents'][0]['colliders']=[{'name':'Song Heavy Sentry (2)','enabled':True}]
    made=propose(made[0],s,1.,sim,8,False,np.zeros((0,6)),set(),goal)
    assert made is not None and made[0].run.link!='bounce_tail'
    assert not made[3]&1048576  # destination is to our right
