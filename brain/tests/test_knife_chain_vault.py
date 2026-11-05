"""Packaged vault family and bounded nominal inputs; no runtime admission claim."""
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import pytest
from ssbot.knowledge import kinematics as K
from ssbot.core import forum as F
from ssbot.combat.air_chain import ChainSim
from ssbot.combat.knife_chain_vault import load_vault_runner
from ssbot.combat.knife_chain_vault_entry import near_proposals
from ssbot.combat import knife_chain_slam as KS


@pytest.fixture(scope="module")
def params():
    root=Path(__file__).resolve().parents[2]
    return K.hero2(K.HeroParams.load(root/"knowledge/1.0.30000/kinematics/hero_wanderer_forum.json"),on=True)


def sim(params,direction):
    box=[27.75,F.FLOOR_Y,32.25,6.9166]
    x=box[0]-3.25 if direction>0 else box[2]+3.25
    start=K.initial_state(params,x,F.FLOOR_Y+params.foot,ground=True,facing=direction)
    start[K.ATK_CD]=0.
    terrain=K.Terrain2D.from_boxes([(-200.,F.FLOOR_Y-10.,260.,F.FLOOR_Y)])
    return ChainSim(start,np.zeros(1,np.int64),K.HoldState.idle(),params,terrain,1000,1000),box


def test_packaged_table_binds_existing_interpreter_without_opening_a_run():
    old=set(KS.P.guards)
    runner,report=load_vault_runner()
    # Task 179: the ground approach link vault_idle.approach and its APPROACH bounds
    assert report["table_digest"]=="92debc0bd6bb8831d1098f77c4ae7cc2d6c6de11713091e121386500d8dccb1c"
    assert runner.run is None and set(KS.P.guards)==old
    assert len(runner.chains["vault_idle"].links)==9


@pytest.mark.parametrize("direction",[-1,1])
def test_target_directed_nominal_rows_keep_inputs_and_request_shape(params,direction):
    s,b=sim(params,direction);state=s.start.copy();hold=s.hold.copy()
    rows,diag=near_proposals(s,b,direction)
    assert rows and diag["generated"]==84 and diag["returned"]<=2
    assert not diag["admission_checked"] and not diag["external_path_checked"]
    assert np.array_equal(s.start,state) and np.array_equal(s.hold.age,hold.age)
    for r in rows:
        assert r.direction==direction and r.body_assumption and not r.commands.flags.writeable
        assert set(r.request_entry())=={"h","p","before"}
        assert 3<=r.contact_index-(len(s.prefix)+r.press+1)<=9


def test_cooldown_or_far_body_does_not_fabricate_contact(params):
    s,b=sim(params,1);s.start[K.ATK_CD]=10.
    assert not near_proposals(s,b,1)[0]
    s,b=sim(params,1);b=np.asarray(b)+[30,0,30,0]
    assert not near_proposals(s,b,1)[0]


def test_incompatible_prefix_declines_before_any_expansion(params):
    s,b=sim(params,1)
    bad=NS(**s.__dict__);bad.prefix=np.array([K.B_DASH],np.int64)
    bad.roll=lambda rows:pytest.fail("unsupported prefix expanded")
    rows,diag=near_proposals(bad,b,1)
    assert not rows and diag["generated"]==0


def test_invalid_geometry_and_direction_cannot_be_a_nominal_entry(params):
    s,b=sim(params,1)
    with pytest.raises(ValueError):near_proposals(s,[0.,0.,float("nan"),1.],1)
    with pytest.raises(ValueError):near_proposals(s,b,True)


@pytest.mark.parametrize("direction",[-1,1])
def test_unobserved_facing_cannot_certify_asymmetric_edge_contact(params,direction):
    from ssbot.combat import pogo_model as PM
    # At this narrow edge both slash alternations meet only for one facing.
    box=np.array([-1.57,-.45,-1.55,-.40])
    if direction<0:box=np.array([-box[2],box[1],-box[0],box[3]])
    poly=np.array([[box[0],box[1]],[box[2],box[1]],[box[2],box[3]],[box[0],box[3]]])
    assert all(PM.meets(PM.slash_poly(direction,a),poly) for a in (False,True))
    assert not all(PM.meets(PM.slash_poly(-direction,a),poly) for a in (False,True))
    s,_=sim(params,direction)
    def rollout(rows):
        flags=np.zeros((len(rows),len(rows[0])+2),np.int64)
        # The neutral-before-press candidate alone has a modeled swing. Its
        # rollout intentionally supplies no per-frame facing, as in production.
        flags[1,6:8]=K.F_ATTACKING
        return NS(flags=flags,pos=np.zeros((*flags.shape,2)))
    s.roll=rollout
    rows,diag=near_proposals(s,box,direction)
    assert not rows and diag["contact_rows"]==0


@pytest.mark.parametrize("direction",[-1,1])
def test_batched_contact_keeps_the_original_order_and_first_contact(params,direction,monkeypatch):
    from ssbot.combat import knife_chain_vault_entry as V, pogo_model as PM
    s,box=sim(params,direction)
    fast,diag=V.near_proposals(s,box,direction,max_results=8)
    def scalar(pos,poly):
        return np.array([all(PM.meets(PM.slash_poly(face,alt)+p,poly)
                             for face,alt in V._DOWN_POLYS) for p in pos],bool)
    monkeypatch.setattr(V,"_meets_all",scalar)
    old,old_diag=V.near_proposals(s,box,direction,max_results=8)
    assert {k:v for k,v in diag.items() if k!="ms"}=={k:v for k,v in old_diag.items() if k!="ms"}
    assert len(fast)==len(old)>0
    for a,b in zip(fast,old):
        assert (a.hold,a.press,a.before,a.direction,a.contact_index)==(b.hold,b.press,b.before,b.direction,b.contact_index)
        np.testing.assert_array_equal(a.commands,b.commands)


def test_batched_contact_uses_original_predicate_at_the_touch_boundary(monkeypatch):
    from ssbot.combat import knife_chain_vault_entry as V, pogo_model as PM
    poly=np.array([[-.1,-.8],[.1,-.8],[.1,-.5],[-.1,-.5]])
    original=PM.meets
    def scalar(p):
        return all(original(PM.slash_poly(face,alt)+p,poly) for face,alt in V._DOWN_POLYS)
    lo,hi=0.,4.
    assert scalar(np.array([lo,0.])) and not scalar(np.array([hi,0.]))
    for _ in range(60):
        mid=.5*(lo+hi)
        if scalar(np.array([mid,0.])):lo=mid
        else:hi=mid
    points=np.array([[lo+d,0.] for d in (-1e-6,-1e-10,-1e-12,0.,1e-12,1e-10,1e-6)])
    expected=np.array([scalar(p) for p in points])
    calls=[]
    def exact(a,b):calls.append(1);return original(a,b)
    monkeypatch.setattr(PM,"meets",exact)
    np.testing.assert_array_equal(V._meets_all(points,poly),expected)
    assert calls, "the close-call path must execute the original floating-point predicate"


@pytest.mark.parametrize("offset",[-100000.,100000.])
def test_batched_contact_outside_arena_numerical_domain_falls_back(offset,monkeypatch):
    from ssbot.combat import knife_chain_vault_entry as V, pogo_model as PM
    poly=np.array([[offset-1.,-2.],[offset+1.,-2.],[offset+1.,0.],[offset-1.,0.]])
    points=np.array([[offset,0.],[offset+8.,0.],[offset-8.,0.]])
    original=PM.meets;calls=[]
    expected=np.array([all(original(PM.slash_poly(face,alt)+p,poly)
                           for face,alt in V._DOWN_POLYS) for p in points])
    def exact(a,b):calls.append(1);return original(a,b)
    monkeypatch.setattr(PM,"meets",exact)
    np.testing.assert_array_equal(V._meets_all(points,poly),expected)
    assert len(calls)>=len(points)
