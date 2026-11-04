"""Side approach does not borrow a strike recipe's irreversible air impulse."""
from copy import deepcopy
from types import SimpleNamespace as NS
import numpy as np
import pytest
from ssbot.combat import knife_chain_transfer as T
from ssbot.combat.air_chain import ChainSim
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.knowledge import kinematics as K
from tests.test_target_side_approach import fixture,check_gate


def placed(x,*,active=False):
    n,s,old,p,fc=fixture(air=True,active=active)
    z=old.start.copy().reshape(K.K);z[K.PX]=x
    s['hero']['pos'][0]=x;s['hero']['box'][0]=x-.25;s['hero']['box'][2]=x+.25
    sim=ChainSim(z,old.prefix,old.hold,old.params,old.terrain,1000,1000)
    n._context=((1000,s,.1,False,True),sim,None,None)
    return n,s,sim,p,fc


def test_far_side_releases_jump_then_still_never_spends_an_air_dash(monkeypatch):
    n,s,sim,p,fc=placed(38.)
    check_gate(monkeypatch,n,sim)
    o=n._transfer_offer(s,.1,sim,fc,p,False)
    assert o is not None and o.mask==B['R']
    assert not o.draft.run.v.get('air_dash_decided')
    n.runner=o.draft
    o=n._transfer_offer(s,.1,sim,fc,p,False)
    assert o is not None and o.mask==B['R']
    assert not o.draft.run.v.get('air_dash_decided')


@pytest.mark.parametrize('x',[40.,41.,44.5])
@pytest.mark.parametrize('active',[False,True])
def test_air_near_hands_back_before_toward_keys_can_cross_body(monkeypatch,x,active):
    n,s,sim,p,fc=placed(x,active=active)
    if active:n.commitment={'move':T.MoveInstance(8,990,'RUNE_TRANSFER'),'origin':990,'ta':0.}
    check_gate(monkeypatch,n,sim)
    assert n._transfer_offer(s,.1,sim,fc,p,False) is None
    assert n.runner.run is None and n.commitment is None and not n._failure_exposures


def test_fresh_side_does_not_enter_a_bounce_source_tail(monkeypatch):
    n,s,sim,p,fc=fixture()
    s['ents'][0]['fsms'][0].update(state='Slam 1',t=0.)
    n._transfer_goal=T.TransferGoal(8,7,1000,0.,'BOUNCE',T.MoveInstance(7,994,'CC_SLAM'))
    n.goal_preferences(s,p,handoff=True)
    assert n._transfer_ready
    n._context=((1000,s,.1,False,True),sim,None,None)
    monkeypatch.setattr(n,'_transfer_offer',lambda *a:pytest.fail('side borrowed fresh BOUNCE tail'))
    assert n._propose(None,None,None,None,None,fc,p,None) is None
    assert n.runner.run is None and not n._failure_exposures


@pytest.mark.parametrize('near',[False,True])
def test_time_limit_does_not_override_a_real_boundary_but_unfinished_route_stays_strict(monkeypatch,near):
    n,s,sim,p,fc=placed(41. if near else 25.,active=True)
    move=T.MoveInstance(8,1000,'RUNE_TRANSFER')
    n.commitment={'move':move,'origin':1000,'ta':0.}
    n._transfer_responsibility[move]=(T.MoveInstance(7,994,'CC_SLAM'),0.)
    n._clock=fc.rs.trk.T=2.2
    check_gate(monkeypatch,n,sim)
    assert n._transfer_offer(s,2.2,sim,fc,p,False) is None
    assert bool(n._failure_exposures)==(not near)
    assert (move in n._failed_hook_moves)==(not near)


def test_successful_send_then_air_near_handoff_preserves_queued_keys_and_no_reclaim(monkeypatch):
    n,s,sim,p,fc=placed(38.)
    s.update(dt=1/60);s['act'].update(target=1000,applied=1000,mask=B['R'])
    n.begin(s);n._clock=.1;n._clock_known=True
    n.goal_preferences(s,p,handoff=True)
    n._context=((1000,s,.1,False,True),sim,None,None)
    queued=n.queued_prefix
    check_gate(monkeypatch,n,sim)
    offer=n._transfer_offer(s,.1,sim,fc,p,False);assert offer is not None
    planner=NS(measurement_enabled=False,jump_until=-1,macro_until=-1)
    result=n.install(offer,planner);n.planner_result(result);n.final('plan',offer.mask)
    n.before_send(frame=1000,target=1002,mask=offer.mask,flags=0,received_frame=1000)
    assert not n._transfer_finished and n.runner.run is None
    n.sent()
    key=(offer.details['caster'],offer.details['cast_fa'])
    assert key in n._transfer_finished and n.commitment is not None
    s2=deepcopy(s);s2['f']=1001;s2['hero']['pos'][0]=41.;s2['hero']['box'][0]=40.75;s2['hero']['box'][2]=41.25;s2['act'].update(target=1001,applied=1001,mask=B['R'])
    assert queued(1001,s2)[0]==offer.mask
    n.begin(s2);n._clock=.1+1/60
    z=sim.start.copy().reshape(K.K);z[K.PX]=41.
    sim2=ChainSim(z,np.array([offer.mask],np.int64),K.HoldState.from_act(s2['act']),sim.params,sim.terrain,1001,1001)
    monkeypatch.setattr(n,'queued_prefix',queued)
    n._context=((1001,s2,n._clock,False,True),sim2,None,None)
    assert n._transfer_offer(s2,n._clock,sim2,fc,p,False) is None
    assert n.runner.run is None and n.commitment is None and not n._failure_exposures
    n.final('ordinary',B['R']);n.before_send(frame=1001,target=1003,mask=B['R'],flags=0,received_frame=1001);n.sent()
    assert not n._failure_exposures and not n._failed_hook_moves
    far=deepcopy(s2);far['hero']['pos'][0]=25.;n.goal_preferences(far,p,handoff=True)
    assert not n._transfer_ready
