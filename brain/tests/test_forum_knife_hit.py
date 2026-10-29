"""The experimental hit/exit path must retain strikes, clocks and hazards."""
from types import SimpleNamespace
import numpy as np
import pytest
from ssbot.combat import forum_knife_hit as hit
from ssbot.combat.holdfilter import hold_filter_jit
from ssbot.ipc.framing import mask
from ssbot.knowledge import kinematics as km
from ssbot.map2 import oldwin_claw as claw


@pytest.fixture
def scenario():
    from ssbot.map2.envelope import load_params
    params=load_params(hero2=True)
    state=km.initial_state(params,0.,6.,ground=False)
    raw=np.zeros(70,np.int64);raw[:2]=mask("clawline")|km.B_RIGHT
    raw[42:44]=km.B_DOWN|km.B_ATTACK
    hold=km.HoldState.idle();latched=hold_filter_jit(raw[None],hold)[0][0]
    boxes=np.tile([4.,3.,7.,8.],(100,1))
    base=claw.rollout(state,latched,params,None,boxes,7)
    planner=SimpleNamespace(params=params,terrain=None,cfg=SimpleNamespace(threads=1,max_points=2),
        _esc_cmds=lambda length:np.zeros((1,length),np.int64))
    rs=SimpleNamespace(samples=(0,100),k_shift=0,occupied_esc=lambda x,y,t:np.zeros(x.shape,bool))
    forecast=SimpleNamespace(fc=SimpleNamespace(half=(.5,1.2)),rs=rs,
        occupied=lambda x,y,t,c:np.zeros(x.shape,bool))
    return params,state,raw,hold,base,boxes,planner,forecast


def test_event_family_covers_every_contact_time_for_every_outcome():
    base=SimpleNamespace(hooks=[None,None],commands=np.zeros(60,np.int64),control_frames=np.array([20,22]))
    events=list(hit.hit_events(base,[40,42],[42,44]))
    for q,(lo,hi) in enumerate([(40,42),(42,44)]):
        assert {int(np.flatnonzero(ev[q])[0])+1 for _,ev in events}==set(range(lo,hi+1))
    with pytest.raises(ValueError,match="first-contact interval"):
        list(hit.hit_events(base,[20,42],[42,44]))


def test_extended_hit_reroll_matches_complete_integration_without_resetting_protection(scenario):
    params,state,raw,hold,base,boxes,_,_=scenario
    commands=np.r_[base.commands,np.full(20,km.B_RIGHT,np.int64)]
    n=len(base.hooks);events=np.zeros((n,len(commands)),np.int64);events[:,47]=km.EV_POGO
    reused=claw.with_events(base,params,None,events,commands=commands)
    direct=claw.rollout(state,commands,params,None,boxes,7,events=events)
    for name in ("phys","pos","vel","mode","flags","box","bound","flags_all","flags_any","final"):
        assert np.array_equal(getattr(reused,name),getattr(direct,name)),name
    assert not (reused.flags_any[:,-20:]&km.F_INVULN).any()
    changed=commands.copy();changed[-1]|=mask("clawline")
    with pytest.raises(ValueError,match="changed hook/prefix"):
        claw.with_events(base,params,None,events,commands=changed)


def test_complete_contacts_checks_frame_zero_and_keeps_invulnerability_and_width_rules(scenario):
    *_,planner,forecast=scenario
    ro=SimpleNamespace(bound=np.tile([0.,0.,.5,2.],(1,3,1)),flags_all=np.zeros((1,3),np.int64))
    forecast.occupied=lambda x,y,t,c:np.broadcast_to(t==0,x.shape)
    assert hit.full_contacts(planner,forecast,ro).tolist()==[[True,False,False]]
    ro.flags_all[0,0]=km.F_INVULN
    assert not hit.full_contacts(planner,forecast,ro).any()
    forecast.occupied=lambda x,y,t,c:np.zeros(x.shape,bool)
    ro.bound[0,2,2]=10.
    assert hit.full_contacts(planner,forecast,ro)[0,2]


def test_common_exit_begins_after_all_bounces_and_keeps_the_planned_strike(scenario):
    _,_,raw,hold,base,_,planner,forecast=scenario
    n=len(base.hooks);audit={}
    world=hit.HitWorld("single",forecast,base,np.full(n,43),np.full(n,48),np.full(n,50),np.ones(n,bool))
    cert=hit.common_escape(planner,[world],raw,hold,horizon=37,audit=audit)
    assert cert is not None and cert.start==51 and cert.through>=75
    assert np.array_equal(cert.raw[:cert.start],raw[:cert.start])
    assert cert.raw[42]&km.B_ATTACK
    assert len(cert.paths)==3 and len(cert.contacts)==3
    assert all(not (p.flags_any[:,-10:]&km.F_INVULN).any() for p in cert.paths)
    forecast.occupied=lambda x,y,t,c:np.broadcast_to(t==0,x.shape)
    assert hit.common_escape(planner,[world],raw,hold,horizon=37) is None
    forecast.occupied=lambda x,y,t,c:np.zeros(x.shape,bool)
    forecast.rs.occupied_esc=lambda x,y,t:np.ones(x.shape,bool)
    assert hit.common_escape(planner,[world],raw,hold,horizon=37) is None
