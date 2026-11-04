"""A straight side approach cannot take ownership of crossing its old source."""
from types import SimpleNamespace as NS
import numpy as np
import pytest
from ssbot.combat.air_chain import ChainSim
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.combat import knife_chain_transfer as T
from ssbot.knowledge import kinematics as K
from tests.test_target_side_approach import fixture,check_gate


def scene(hx,*,active=False,mirror=False):
    n,s,old,p,fc=fixture(active=active)
    z=old.start.copy().reshape(K.K);z[K.PX]=hx;z[K.VX]=0.
    s['hero']['pos'][0]=hx;s['hero']['box'][0]=hx-.25;s['hero']['box'][2]=hx+.25;s['hero']['vel'][0]=0.
    if mirror:
        hx=60.-hx;z[K.PX]=hx;z[K.FACE]*=-1
        s['hero']['pos'][0]=hx;s['hero']['box'][0]=hx-.25;s['hero']['box'][2]=hx+.25
        for e in s['ents']:
            e['pos'][0]=60.-e['pos'][0]
            for c in e['colliders']:c['verts_world'][::2]=[60.-x for x in c['verts_world'][::2]]
        s['act']['hf']['latched']=s['act']['hf']['desired']=B['L']
        if active:n.runner.run.v['side']=B['L']
    mask=B['L'] if mirror else B['R']
    sim=ChainSim(z,np.array([mask],np.int64),K.HoldState.from_act(s['act']),old.params,old.terrain,1000,1000)
    n._context=((1000,s,.1,True,True),sim,None,None)
    if active:n.commitment={'move':T.MoveInstance(8,1000,'RUNE_TRANSFER'),'origin':1000,'ta':0.}
    return n,s,sim,p,fc


@pytest.mark.parametrize('hx,cd',[(8.,0.),(5.,.25),(12.,0.),(13.9,0.)])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('active',[False,True])
def test_source_body_on_path_declines_or_hands_back_without_new_keys(monkeypatch,hx,cd,mirror,active):
    n,s,sim,p,fc=scene(hx,active=active,mirror=mirror);s['hero']['tm']['dash_cd']=cd
    check_gate(monkeypatch,n,sim)
    before=sim.prefix.copy();hold=sim.hold.latched.copy()
    assert n._transfer_offer(s,.1,sim,fc,p,True) is None
    assert n.runner.run is None and n.commitment is None and not n._failure_exposures
    assert np.array_equal(sim.prefix,before) and np.array_equal(sim.hold.latched,hold)


@pytest.mark.parametrize('mirror',[False,True])
def test_source_entirely_behind_preserves_existing_approach(monkeypatch,mirror):
    n,s,sim,p,fc=scene(16.,mirror=mirror)
    check_gate(monkeypatch,n,sim)
    assert n._transfer_offer(s,.1,sim,fc,p,True) is not None


@pytest.mark.parametrize('missing',['source','pos','nonfinite','body','disabled','malformed'])
@pytest.mark.parametrize('active',[False,True])
def test_unknown_source_is_not_fabricated_as_a_planned_crossing(monkeypatch,missing,active):
    n,s,sim,p,fc=scene(25.,active=active);source=s['ents'][0]
    if missing=='source':s['ents'].pop(0)
    elif missing=='pos':source['pos']=None
    elif missing=='nonfinite':source['pos'][0]=float('nan')
    elif missing=='body':source['colliders']=[]
    elif missing=='disabled':source['colliders'][0]['enabled']=False
    else:source['colliders'][0]['verts_world']=[1.,2.,3.]
    reasons=[];monkeypatch.setattr(n,'_recover',lambda reason,f:reasons.append(reason))
    check_gate(monkeypatch,n,sim)
    assert n._transfer_offer(s,.1,sim,fc,p,True) is None
    assert bool(reasons)==active
    assert not n._failure_exposures  # this probe stubs _recover; it cannot credit real exposure


def test_known_arrival_remains_a_planned_boundary_with_unknown_source(monkeypatch):
    n,s,sim,p,fc=scene(42.,active=True);s['ents'][0]['colliders']=[]
    monkeypatch.setattr(n,'_recover',lambda *a:pytest.fail('arrival converted to failure'))
    assert n._transfer_offer(s,.1,sim,fc,p,True) is None
    assert n.runner.run is None and n.commitment is None
