"""A certificate needs one exit for all worlds, on the caller's real horizon."""
from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import pytest
from ssbot.combat import forum_knife_hit as hit
from ssbot.combat.holdfilter import hold_filter_jit
from ssbot.knowledge import kinematics as k


@pytest.fixture
def case():
    raw=np.zeros(80,np.int64);raw[42:44]=k.B_DOWN|k.B_ATTACK
    hold=k.HoldState.idle();wire=hold_filter_jit(raw[None],hold)[0][0]
    hook=object()
    base=SimpleNamespace(hooks=[hook],commands=wire,control_frames=np.array([20]),
                         control_states={0:np.zeros(k.K)})
    def reroll(ev,commands):
        x=np.r_[0,np.cumsum(((commands&k.B_RIGHT)!=0).astype(int)
                            -((commands&k.B_LEFT)!=0).astype(int))]
        bound=np.tile([0.,0.,.5,2.],(1,len(commands)+1,1))
        bound[0,:,0]+=x;bound[0,:,2]+=x
        flags=np.zeros(bound.shape[:2],np.int64)
        return SimpleNamespace(hooks=base.hooks,commands=commands.copy(),bound=bound,
            flags_all=flags.copy(),flags_any=flags.copy(),control_frames=base.control_frames.copy(),
            control_states={q:s.copy() for q,s in base.control_states.items()},pogo_events=ev.copy())
    def forecast(forbidden):
        def occupied(x,y,t,*args):return forbidden(x,y,t)
        return SimpleNamespace(fc=SimpleNamespace(half=(.5,1.2)),
            occupied=occupied,rs=SimpleNamespace(samples=(0,100),k_shift=0,occupied_esc=occupied))
    left=forecast(lambda x,y,t:x>.5)
    right=forecast(lambda x,y,t:x<0)
    durations=(47,4,3,4,14)
    for fc, shift in ((left,-1),(right,1)):
        fc.rs.knife_coupled_world=dict(iid=7,durations=durations,shift=shift)
    worlds=[hit.HitWorld((7,durations,shift),fc,base,np.array([43]),np.array([47]),np.array([47]),
                         np.array([True]),reroll) for shift,fc in ((-1,left),(1,right))]
    planner=SimpleNamespace(params=SimpleNamespace(frame_time=1/60),terrain=None,
        cfg=SimpleNamespace(threads=1,max_points=2),
        _esc_cmds=lambda n:np.array([[k.B_LEFT]*n,[k.B_RIGHT]*n],np.int64))
    return planner,worlds,raw,hold,reroll


def test_individually_valid_exits_do_not_make_a_common_exit(case):
    planner,worlds,raw,hold,_=case
    assert escape(planner,[worlds[0]],raw,hold,horizon=37).option==0
    assert escape(planner,[worlds[1]],raw,hold,horizon=37).option==1
    audit={}
    assert escape(planner,worlds,raw,hold,horizon=37,audit=audit) is None
    assert audit["status"]=="failed" and audit["reason"]=="no_common_exit"
    assert [r["failed_worlds"] for r in audit["options"]]==[[1],[0]]


def test_same_third_option_and_wire_is_checked_in_every_world(case):
    planner,worlds,raw,hold,_=case
    planner._esc_cmds=lambda n:np.array([[k.B_LEFT]*n,[k.B_RIGHT]*n,[0]*n],np.int64)
    cert=escape(planner,worlds,raw,hold,horizon=37)
    assert cert.option==2 and cert.start==48 and cert.world_keys==[w.key for w in worlds]
    assert all(np.array_equal(p.commands,cert.latched) for p in cert.paths)


def test_later_input_lock_moves_the_one_global_J(case):
    planner,worlds,raw,hold,reroll=case
    def delayed(ev,commands):
        ro=reroll(ev,commands);ro.flags_any[:,48:50]|=k.F_NO_INPUT
        return ro
    worlds=[worlds[0],replace(worlds[1],reroll=delayed)]
    planner._esc_cmds=lambda n:np.zeros((1,n),np.int64)
    cert=escape(planner,worlds,raw,hold,horizon=37)
    assert cert.start==50
    assert np.array_equal(cert.raw[:50],raw[:50])
    assert cert.through>=cert.start+24


def test_delayed_J_requires_the_longer_supported_tail(case):
    planner,worlds,raw,hold,reroll=case
    def delayed(ev,commands):
        ro=reroll(ev,commands);ro.flags_any[:,48:60]|=k.F_NO_INPUT
        return ro
    w=replace(worlds[0],reroll=delayed)
    w.forecast.rs.samples=(0,80);audit={}
    with pytest.raises(ValueError,match="support horizon"):
        escape(planner,[w],raw,hold,horizon=37,audit=audit)
    assert audit["status"]=="unchecked" and audit["start"]==60 and audit["through"]==84


@pytest.mark.parametrize("H,passed",[(33,True),(37,True),(42,True),(47,False)])
def test_real_H_changes_the_contact_gate(case,H,passed):
    planner,worlds,raw,hold,_=case
    planner._esc_cmds=lambda n:np.zeros((1,n),np.int64)
    audit={}
    cert=escape(planner,worlds,raw,hold,horizon=H,audit=audit)
    assert (cert is not None)==passed and audit["horizon"]==H
    if not passed:assert audit["reason"]=="contact_gate"


def test_unknown_H_and_noninteger_contact_are_not_defaulted(case):
    planner,worlds,raw,hold,_=case
    with pytest.raises(ValueError,match="integer contact horizon"):
        escape(planner,worlds,raw,hold,horizon=None)
    with pytest.raises(ValueError,match="contact identity"):
        escape(planner,[replace(worlds[0],first=np.array([47.5]))],raw,hold,horizon=37)


def test_one_world_without_robust_contact_refuses_before_integrating(case):
    planner,worlds,raw,hold,_=case
    def forbidden(*args):raise AssertionError("contact gate must run first")
    worlds=[replace(worlds[0],reroll=forbidden),
            replace(worlds[1],robust=np.array([False]),reroll=forbidden)]
    audit={}
    assert escape(planner,worlds,raw,hold,horizon=37,audit=audit) is None
    assert audit["failed_worlds"]==[1]


def test_duplicate_or_forecast_world_identity_cannot_be_substituted(case):
    planner,worlds,raw,hold,_=case
    with pytest.raises(ValueError,match="duplicate target world"):
        escape(planner,[worlds[0],worlds[0]],raw,hold,horizon=37)
    worlds[0].forecast.rs.knife_coupled_world=dict(iid=7,durations=(47,4,3,4,14),shift=-2)
    with pytest.raises(ValueError,match="forecast target world"):
        escape(planner,[worlds[0]],raw,hold,horizon=37)


def test_same_indices_cannot_hide_a_different_hook_or_control_state(case):
    planner,worlds,raw,hold,reroll=case
    def changed_state(ev,commands):
        ro=reroll(ev,commands);ro.control_states[0][0]=1
        return ro
    with pytest.raises(ValueError,match="control state identity"):
        escape(planner,[replace(worlds[0],reroll=changed_state)],raw,hold,horizon=37)
    def changed_hook(ev,commands):
        ro=reroll(ev,commands);ro.hooks=[object()]
        return ro
    with pytest.raises(ValueError,match="hook identity"):
        escape(planner,[replace(worlds[0],reroll=changed_hook)],raw,hold,horizon=37)


def test_frame_zero_hazard_is_not_repaired_by_an_exit(case):
    planner,worlds,raw,hold,_=case
    worlds[0].forecast.occupied=lambda x,y,t,*a:np.broadcast_to(t==0,x.shape)
    audit={}
    assert escape(planner,worlds,raw,hold,horizon=37,audit=audit) is None
    assert audit["reason"]=="prefix_unsafe" and 0 in audit["prefix_unsafe"]


def test_a_checked_exit_can_replace_only_the_future_fixed_tail(case):
    planner,worlds,raw,hold,reroll=case
    raw=raw.copy();raw[60:70]=k.B_RIGHT
    commands=hold_filter_jit(raw[None],hold)[0][0]
    worlds[0].base.commands=commands
    audit={}
    cert=escape(planner,[worlds[0]],raw,hold,horizon=37,audit=audit)
    assert cert is not None and audit["fixed_unsafe"]
    assert min(audit["fixed_unsafe"])>cert.start and not audit["prefix_unsafe"]
    assert np.array_equal(cert.raw[:cert.start],raw[:cert.start])


def test_FREE_MIN_is_not_weakened_by_world_expansion(case):
    planner,worlds,raw,hold,_=case
    w=replace(worlds[0],swing=np.array([29]))
    audit={}
    assert escape(planner,[w],raw,hold,horizon=37,audit=audit) is None
    assert audit["reason"]=="contact_gate"



def test_invalid_contact_order_or_missing_world_is_not_a_certificate(case):
    planner,worlds,raw,hold,_=case
    assert escape(planner,[replace(worlds[0],swing=np.array([55]))],raw,hold,horizon=37) is None
    with pytest.raises(ValueError,match="world identity unavailable"):
        escape(planner,[replace(worlds[0],key=None)],raw,hold,horizon=37)


def test_delaying_J_does_not_hide_a_newly_included_prefix_hazard(case):
    planner,worlds,raw,hold,reroll=case
    def delayed(ev,commands):
        ro=reroll(ev,commands);ro.flags_any[:,48:50]|=k.F_NO_INPUT
        return ro
    worlds=[worlds[0],replace(worlds[1],reroll=delayed)]
    worlds[0].forecast.occupied=lambda x,y,t,*a:np.broadcast_to(np.isclose(t,49/60),x.shape)
    audit={}
    assert escape(planner,worlds,raw,hold,horizon=37,audit=audit) is None
    assert audit["start"]==50 and 49 in audit["prefix_unsafe"] and not audit["options"]


def test_reroll_cannot_move_the_pogo_event(case):
    planner,worlds,raw,hold,reroll=case
    def moved(ev,commands):
        ro=reroll(ev,commands);ro.pogo_events=np.roll(ro.pogo_events,1,axis=1)
        return ro
    with pytest.raises(ValueError,match="changed pogo events"):
        escape(planner,[replace(worlds[0],reroll=moved)],raw,hold,horizon=37)


def escape(planner, worlds, raw, hold, **kwargs):
    """Small synthetic domain for these component tests, not a runtime factory."""
    kwargs.setdefault("expected_worlds", tuple(w.key for w in worlds))
    return hit.common_escape(planner, worlds, raw, hold, **kwargs)
