"""OP3 shadow rules must stay opt-in and preserve ordinary dash eligibility."""
from dataclasses import replace
import numpy as np
import pytest
from ssbot.knowledge import kinematics as k

@pytest.fixture(scope="module")
def p():
    return k.hero2(k.HeroParams.load(k.REPO/"knowledge/1.0.30000/kinematics/hero_wanderer_forum.json"),on=True)

def start(p,phase=2,age=0):
    s=k.initial_state(p,30.,14.,ground=False)
    s[k.MODE]=k.M_GLIDE;s[k.PHASE]=phase;s[k.MODE_T]=age*p.frame_time
    s[k.PREV]=k.B_JUMP;s[k.JHELD]=1;s[k.AIRDASHED]=0;s[k.DASH_CD]=0
    return s

def run(p,s,key,n=3):
    return k.rollout(s,np.full((1,n),key,np.int64),p,None)

def test_default_hero2_mask_excludes_both_shadow_rules(p):
    assert p.hero2==k.H2_ALL==16383
    assert not p.hero2&(k.H2_SHADOW_GLIDE_CANCEL_LATE|k.H2_SHADOW_GLIDE_DASH_NOW)

@pytest.mark.parametrize("age,old,new",[(3,False,False),(4,True,False),(5,True,True)])
def test_inflate_attack_boundary_and_neighbor_frames(p,age,old,new):
    a=run(p,start(p,1,age),k.B_JUMP|k.B_ATTACK,n=1)
    b=run(replace(p,hero2=p.hero2|k.H2_SHADOW_GLIDE_CANCEL_LATE),start(p,1,age),k.B_JUMP|k.B_ATTACK,n=1)
    assert bool(a.flags[0,1]&k.F_ATTACKING)==old
    assert bool(b.flags[0,1]&k.F_ATTACKING)==new

def test_dash_cancels_on_press_frame_only_when_explicitly_enabled(p):
    s=start(p);key=k.B_JUMP|k.B_RIGHT|k.B_DASH
    a=run(p,s,key);b=run(replace(p,hero2=p.hero2|k.H2_SHADOW_GLIDE_DASH_NOW),s,key)
    assert a.mode[0,1]==k.M_NORMAL and a.mode[0,2]==k.M_DASH
    assert b.mode[0,1]==k.M_DASH and b.final[k.AIRDASHED,0]==1
    assert b.final[k.DASH_CD,0]<p.dash_cooldown

@pytest.mark.parametrize("blocked",["spent","cooldown","ability"])
def test_shadow_dash_preserves_resource_and_ability_gates(p,blocked):
    s=start(p);p=replace(p,hero2=p.hero2|k.H2_SHADOW_GLIDE_DASH_NOW)
    if blocked=="spent":s[k.AIRDASHED]=1
    elif blocked=="cooldown":s[k.DASH_CD]=1
    else:p=replace(p,abilities=p.abilities&~k.AB_DASH)
    ro=run(p,s,k.B_JUMP|k.B_DASH)
    assert not np.any(ro.mode==k.M_DASH)

def test_release_and_held_dash_do_not_gain_cancel_permission(p):
    p=replace(p,hero2=p.hero2|k.H2_SHADOW_GLIDE_DASH_NOW|k.H2_SHADOW_GLIDE_CANCEL_LATE)
    assert not np.any(run(p,start(p),k.B_DASH).mode==k.M_DASH)
    s=start(p);s[k.PREV]=k.B_JUMP|k.B_DASH
    assert not np.any(run(p,s,k.B_JUMP|k.B_DASH).mode==k.M_DASH)

def test_simultaneous_attack_keeps_existing_attack_priority(p):
    p=replace(p,hero2=p.hero2|k.H2_SHADOW_GLIDE_DASH_NOW)
    ro=run(p,start(p),k.B_JUMP|k.B_ATTACK|k.B_DASH,n=1)
    assert ro.flags[0,1]&k.F_ATTACKING and ro.mode[0,1]!=k.M_DASH

def test_ordinary_control_path_is_identical_with_shadow_bits(p):
    s=k.initial_state(p,30.,14.,ground=False);key=k.B_RIGHT|k.B_DASH
    a=run(p,s,key);b=run(replace(p,hero2=p.hero2|k.H2_SHADOW_GLIDE_DASH_NOW|k.H2_SHADOW_GLIDE_CANCEL_LATE),s,key)
    for name in ("phys","pos","vel","mode","flags","box","final"):
        assert np.array_equal(getattr(a,name),getattr(b,name)),name

