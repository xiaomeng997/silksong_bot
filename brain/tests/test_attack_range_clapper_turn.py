"""Predict Clapper post-slam turn before its Idle body is first reported."""
from types import SimpleNamespace as NS
import numpy as np
import pytest
from ssbot.combat import attack_range as ar,jump_behind as jb

CC=jb.CLAPPER
ROOT=17.512


def forecast(monkeypatch,fam,state,enabled=True):
    monkeypatch.setattr(jb,"ENABLED",enabled)
    tab=ar.RangeTable(spec=ar.SPECS[CC],templates={},meta={})
    # Recorded last Recover body (6.42); the right edge before turning is 18.853.
    raw=ar.poly_mask([np.array([[ROOT-2.252,3.0],[ROOT+1.341,3.0],
                                [ROOT+1.341,6.607],[ROOT-2.252,6.607]])])
    monkeypatch.setattr(tab,"place",lambda *args,**kwargs:raw)
    monkeypatch.setattr(ar,"hazards_at",lambda *args,**kwargs:ar.empty_mask())
    monkeypatch.setattr(ar,"type_extra",lambda spec:None)
    trk=ar.RangeTracker(tables={CC:tab})
    inst=NS(fam=fam,branch=None,t0=0.,x0=ROOT,y0=7.45,s=-1.,hero_du=3.,dec=None,states=[state])
    trk.now={9:(CC,{"pos":[ROOT,7.45]},inst)}
    return trk,raw


@pytest.mark.parametrize("state",["Slam 2","Slam Recover"])
@pytest.mark.parametrize("k",[0,1,12,36,62])
def test_slam_tail_covers_actual_turned_body_before_idle(monkeypatch,state,k):
    trk,raw=forecast(monkeypatch,"CC_SLAM",state)
    got=trk.estimate(9,k)
    # Actual TurnToIdle body at f2905/2906, including its taller top and 0.911u edge shift.
    turned=ar.poly_mask([np.array([[ROOT-1.341,3.0],[ROOT+2.252,3.0],
                                   [ROOT+2.252,6.917],[ROOT-1.341,6.917]])])
    assert np.all(ar.on_canvas(got.raw,turned.ix0,turned.iy0,turned.m.shape)[turned.m])
    assert not ar.same_mask(got.raw,raw)
    assert ar.same_mask(got.core,got.raw) if ar.COMMIT_CORE else got.core is None


@pytest.mark.parametrize("fam,state",[("CC_SLAM","Slam Antic"),("CC_SLAM","Slam 0"),
    ("CC_SLAM","Slam 1"),("CC_SLAM","Slam Effects?"),("CC_SLAM","Charged?"),
    ("CC_CAST","Slam Recover"),("CC_EVADE","Slam 2")])
def test_extension_does_not_add_turn_before_slam_tail_or_to_other_families(monkeypatch,fam,state):
    trk,raw=forecast(monkeypatch,fam,state)
    assert ar.same_mask(trk.estimate(9,36).raw,raw)


def test_existing_switch_off_keeps_original_slam_estimate(monkeypatch):
    trk,raw=forecast(monkeypatch,"CC_SLAM","Slam Recover",False)
    assert ar.same_mask(trk.estimate(9,36).raw,raw)


@pytest.mark.parametrize("fam",["CC_JUMP","CC_JUMP_CAST"])
def test_existing_jump_turn_mask_is_unchanged(monkeypatch,fam):
    trk,raw=forecast(monkeypatch,fam,"Slam Recover")
    expected=ar.union([raw,ar._jb_turn_mask(ROOT)])
    assert ar.same_mask(trk.estimate(9,36).raw,expected)
