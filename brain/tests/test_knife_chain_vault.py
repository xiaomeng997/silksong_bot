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
    assert report["table_digest"]=="b525fe59c6ee430a332aea3c6e3cc0c5e3b94e273b0490e6cc9e1c8b124b19c8"
    assert runner.run is None and set(KS.P.guards)==old
    assert len(runner.chains["vault_idle"].links)==8


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
