"""Observed dash capability corrects reconstructed spent-air-dash state.

Regression: the watched w13 wall-somersault at f3444 exported CanDash=True
while its reconstructed start still had AIRDASHED=1. Use only same-frame
oracle truth; a false predicate can mean cooldown, so it cannot prove spent.
"""
from types import SimpleNamespace as NS
import numpy as np
import pytest
from ssbot.knowledge import kinematics as K
from ssbot.train.planner_policy import PlannerPolicy


def sample(*, can=True, view="oracle", observed=3444, world=3444):
    p=K.hero2(K.HeroParams.load(K.REPO/"knowledge/1.0.30000/kinematics/hero_wanderer_forum.json"),on=True)
    start=K.initial_state(p,46.43,14.07,facing=-1,ground=False)
    start[K.VX]=-8.25;start[K.VY]=.6;start[K.AIRDASHED]=1.;start[K.DASH_CD]=0.
    policy=PlannerPolicy.__new__(PlannerPolicy);policy.view=view;policy.trk=NS(state=lambda:start)
    policy.raw={};policy.params=p
    ws=NS(stamp=NS(frame=world));raw={"f":observed,"hero":{"can":{"dash":can},"anim":{"clip":"Walljump Somersault"}}}
    return policy,ws,raw,start,p


def test_observed_dash_recovers_the_real_airdash_option_after_wall_somersault():
    policy,ws,raw,original,p=sample()
    corrected=policy._start_state(ws,raw)
    assert np.all(corrected[K.AIRDASHED]==0.)
    assert np.all(original[K.AIRDASHED]==1.)
    expected=original.copy();expected[K.AIRDASHED]=0.;np.testing.assert_array_equal(corrected,expected)
    commands=np.array([[K.B_LEFT|K.B_DASH]+[K.B_LEFT]*7],dtype=np.int64)
    old=K.rollout(original,commands,p,None,backend="numba")
    new=K.rollout(corrected,commands,p,None,backend="numba")
    assert K.M_DASH not in old.mode[0]
    assert K.M_DASH in new.mode[0]
    assert new.final[K.PX,0]<old.final[K.PX,0]


@pytest.mark.parametrize("can",[False,None,1])
def test_unknown_or_blocked_dash_predicate_does_not_invent_resource_state(can):
    policy,ws,raw,original,_=sample(can=can)
    np.testing.assert_array_equal(policy._start_state(ws,raw),original)


@pytest.mark.parametrize("view,observed,world",[("degraded",3444,3444),("oracle",3445,3444)])
def test_camera_or_newer_frame_cannot_supply_privileged_resource_truth(view,observed,world):
    policy,ws,raw,original,_=sample(view=view,observed=observed,world=world)
    np.testing.assert_array_equal(policy._start_state(ws,raw),original)


def test_observed_available_flag_preserves_cooldown_and_all_other_motion_gates():
    policy,ws,raw,original,p=sample();original[K.DASH_CD]=.5
    corrected=policy._start_state(ws,raw)
    assert corrected[K.DASH_CD]==original[K.DASH_CD]
    commands=np.array([[K.B_LEFT|K.B_DASH]+[K.B_LEFT]*7],dtype=np.int64)
    assert K.M_DASH not in K.rollout(corrected,commands,p,None,backend="numba").mode[0]
