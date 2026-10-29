"""A contact belongs to a hook AND a clock; neither may borrow protection."""
from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import pytest
from ssbot.combat import forum_knife_lanes as lanes,forum_knife_hit as hit
from ssbot.knowledge import kinematics as km
from ssbot.map2 import oldwin_claw as claw
from ssbot.combat.holdfilter import hold_filter_jit
from ssbot.ipc.framing import mask


@pytest.fixture
def case():
    from ssbot.map2.envelope import load_params
    params=load_params(hero2=True)
    state=km.initial_state(params,0.,7.,ground=False)
    raw=np.zeros(76,np.int64);raw[:2]=mask("clawline")|km.B_RIGHT
    raw[42:44]=km.B_DOWN|km.B_ATTACK
    hold=km.HoldState.idle();wire=hold_filter_jit(raw[None],hold)[0][0]
    bodies=np.tile([4.,3.,7.,8.],(100,1))
    base=claw.rollout(state,wire,params,None,bodies,7)
    return params,raw,hold,base


def test_no_event_expansion_preserves_all_existing_clock_trajectories(case):
    from ssbot.tools.forum_knife_contact_audit import clock_lanes
    params,_,_,base=case
    old=clock_lanes(base,base.commands,params,None);new=lanes.rollout(base,params)
    assert len(new.hooks)==len(base.hooks)*9
    assert new.clock_names==tuple(v.name for v in km.BOUNDS)
    for name in ("box","mode","flags"):
        assert np.array_equal(getattr(old,name),getattr(new,name)),name
    for q,(h,v) in enumerate(zip(new.hook_indices,new.clock_indices)):
        c=base.control_frames[h]
        for name in ("box","bound","flags_all"):
            assert np.array_equal(getattr(new,name)[q,:c+1],getattr(base,name)[h,:c+1])
        assert v==q%9 and h==q//9
    assert not new.measured_protection.any()


def test_different_contacts_in_different_clocks_match_direct_variant_motion(case):
    params,_,_,base=case;n=len(base.hooks)*9;T=len(base.commands)
    ev=np.zeros((n,T),np.int64);cc=46+np.arange(n)%3
    ev[np.arange(n),cc-1]=km.EV_POGO
    ro=lanes.rollout(base,params,events=ev)
    assert np.array_equal(ro.pogo_events,ev)
    # Independent direct kernel calls: no new grouping code, every clock of
    # two different hook outcomes, including all nominal/alpha/timer choices.
    for h in (0,len(base.hooks)-1):
        c=int(base.control_frames[h]);st=base.control_states[h]
        for v,var in enumerate(km.BOUNDS):
            q=h*9+v
            direct=km.rollout(st,base.commands[None,c:],replace(params,pogo_invul=0.),
                              events=ev[q:q+1,c:],variants=(var,))
            for name in ("phys","pos","vel","mode","box"):
                assert np.array_equal(getattr(ro,name)[q,c+1:],getattr(direct,name)[0,1:]),(h,v,name)
            assert np.array_equal(ro.bound[q,c+1:],direct.box[0,1:]+[-.25,-.25,.25,.25])
            assert not ro.measured_protection[q,:cc[q]].any()
            assert ro.measured_protection[q,cc[q]]
    assert params.pogo_invul==.16


def test_protection_follows_each_lanes_own_fixed_update_steps(case):
    params,_,_,base=case
    commands=base.commands.copy();commands[int(base.control_frames.max())+1:]=km.B_RIGHT
    n=len(base.hooks)*9;T=len(commands);cc=45+np.arange(n)%4
    ev=np.zeros((n,T),np.int64);ev[np.arange(n),cc-1]=km.EV_POGO
    ro=lanes.rollout(base,params,events=ev,commands=commands)
    for q in range(n):
        start=int(cc[q]);left=8
        # Horizontal speed is constant long before these contacts; displacement
        # reveals the physics steps independently of the protection clock.
        steps=np.rint(np.diff(ro.phys[q,start:,0])/(params.run_speed*params.fdt)).astype(int)
        assert np.isin(steps,[0,1]).all()
        expected=[True]
        for fs in steps:left=max(left-int(fs),0);expected.append(left>0)
        assert np.array_equal(ro.measured_protection[q,start:],expected)
        assert np.array_equal((ro.flags_all[q,start:]&km.F_INVULN)!=0,expected)


def test_extension_replays_same_events_without_resetting_protection(case):
    params,_,_,base=case;n=len(base.hooks)*9;T=len(base.commands)
    ev=np.zeros((n,T),np.int64);ev[:,46]=km.EV_POGO
    short=lanes.rollout(base,params,events=ev)
    commands=np.r_[base.commands,np.zeros(14,np.int64)];extended=np.pad(ev,((0,0),(0,14)))
    long=lanes.rollout(base,params,events=extended,commands=commands)
    for name in ("box","flags_all","measured_protection"):
        assert np.array_equal(getattr(short,name),getattr(long,name)[:,:T+1]),name
    assert not long.measured_protection[:,-14:].any()
    assert np.count_nonzero(long.pogo_events)==n


def test_unsupported_events_clocks_and_changed_hook_are_rejected(case):
    params,_,_,base=case;n=len(base.hooks)*9;T=len(base.commands)
    ev=np.zeros((n,T),np.int64);ev[0,0]=km.EV_POGO
    with pytest.raises(ValueError,match="inside hook"):lanes.rollout(base,params,events=ev)
    ev[0,0]=km.EV_HURT_L
    with pytest.raises(ValueError,match="pogo stream"):lanes.rollout(base,params,events=ev)
    ev[:]=0;ev[0,46]=ev[0,50]=km.EV_POGO
    with pytest.raises(ValueError,match="pogo stream"):lanes.rollout(base,params,events=ev)
    commands=base.commands.copy();commands[0]=0
    with pytest.raises(ValueError,match="changed hook"):lanes.rollout(base,params,commands=commands)
    state=base.control_states[0];old=state[km.TS]
    state[km.TS]=.5
    try:
        with pytest.raises(ValueError,match="normal time"):lanes.rollout(base,params)
    finally:state[km.TS]=old


def test_shared_exit_can_keep_lane_specific_contacts_and_one_command(case):
    params,raw,hold,base=case;paths=lanes.rollout(base,params);n=len(paths.hooks)
    first=46+np.arange(n)%3;last=first+1
    planner=SimpleNamespace(params=params,terrain=None,cfg=SimpleNamespace(threads=1,max_points=2),
        _esc_cmds=lambda length:np.zeros((1,length),np.int64))
    forecast=SimpleNamespace(fc=SimpleNamespace(half=(.5,1.2)),
        rs=SimpleNamespace(knife_coupled_world=dict(iid=7,durations=(47,4,3,4,14),shift=0),samples=(0,100),k_shift=0,occupied_esc=lambda x,y,t:np.zeros(x.shape,bool)),
        occupied=lambda x,y,t,c:np.zeros(x.shape,bool))
    audit={}
    world=hit.HitWorld((7,(47,4,3,4,14),0),forecast,paths,np.full(n,43),first,last,np.ones(n,bool),
        reroll=lambda ev,commands:lanes.rollout(base,params,events=ev,commands=commands))
    cert=escape(planner,[world],raw,hold,horizon=37,audit=audit)
    assert cert is not None and cert.start==int(last.max())+1 and cert.through>=cert.start+24
    assert all(np.count_nonzero(p.pogo_events)==n for p in cert.paths)
    for p,cc in zip(cert.paths,cert.contacts):
        assert np.array_equal(np.argmax(p.pogo_events,axis=1)+1,cc)
        assert np.array_equal(p.commands,cert.latched)


def test_exit_cannot_swap_clock_identity_even_if_row_count_is_unchanged(case):
    params,raw,hold,base=case;paths=lanes.rollout(base,params);n=len(paths.hooks)
    planner=SimpleNamespace(params=params,terrain=None,cfg=SimpleNamespace(threads=1,max_points=2))
    def swapped(ev,commands):
        ro=lanes.rollout(base,params,events=ev,commands=commands)
        ro.clock_indices=np.roll(ro.clock_indices,1)
        return ro
    with pytest.raises(ValueError,match="outcome identity"):
        world=hit.HitWorld((7,(47,4,3,4,14),0),SimpleNamespace(rs=SimpleNamespace(knife_coupled_world=dict(iid=7,durations=(47,4,3,4,14),shift=0))),paths,np.full(n,43),np.full(n,47),np.full(n,47),np.ones(n,bool),swapped)
        escape(planner,[world],raw,hold,horizon=37)


def test_uniform_contacts_reunite_to_the_original_bounds_and_protection(case):
    params,_,_,base=case;nh=len(base.hooks);T=len(base.commands)
    events=np.zeros((nh,T),np.int64);events[:,46]=km.EV_POGO
    old=claw.with_events(base,params,None,events)
    new=lanes.rollout(base,params,events=np.repeat(events,9,axis=0))
    boxes=new.bound.reshape(nh,9,T+1,4)
    union=np.concatenate((boxes[...,:2].min(axis=1),boxes[...,2:].max(axis=1)),axis=-1)
    flags=new.flags.reshape(nh,9,T+1)
    assert np.array_equal(union,old.bound)
    assert np.array_equal(np.bitwise_and.reduce(flags,axis=1),old.flags_all)
    assert np.array_equal(np.bitwise_or.reduce(flags,axis=1),old.flags_any)
    assert np.array_equal(new.box[::9],old.box)


def test_geometry_query_dedup_keeps_every_verdict_and_invalidates_on_replacement(case):
    params,_,_,base=case;n=len(base.hooks)*9;T=len(base.commands)
    events=np.zeros((n,T),np.int64);events[:,46]=km.EV_POGO
    paths=lanes.rollout(base,params,events=events)
    assert len(paths.query_index)<n
    planner=SimpleNamespace(params=params,cfg=SimpleNamespace(max_points=2))
    calls=[]
    def occupied(x,y,t,*args):
        calls.append(len(x))
        return (x>1)&(y<12)&(t[None,:]>.1)
    forecast=SimpleNamespace(fc=SimpleNamespace(half=(.5,1.2)),
        rs=SimpleNamespace(occupied_esc=occupied),occupied=occupied)
    plain=SimpleNamespace(bound=paths.bound.copy(),flags_all=paths.flags_all.copy())
    for start,escape in ((0,False),(52,True)):
        expected=hit.full_contacts(planner,forecast,plain,start=start,escape=escape)
        full_count=calls[-1]
        actual=hit.full_contacts(planner,forecast,paths,start=start,escape=escape)
        assert np.array_equal(actual,expected) and actual.shape[0]==n
        assert calls[-1]<full_count
    with pytest.raises(ValueError):paths.bound[0,0,0]+=1
    paths.bound=paths.bound.copy();paths.bound[0,:,0:4:2]+=20
    actual=hit.full_contacts(planner,forecast,paths)
    plain.bound=paths.bound.copy()
    assert np.array_equal(actual,hit.full_contacts(planner,forecast,plain))


def escape(planner, worlds, raw, hold, **kwargs):
    """Small synthetic domain for these component tests, not a runtime factory."""
    kwargs.setdefault("expected_worlds", tuple(w.key for w in worlds))
    return hit.common_escape(planner, worlds, raw, hold, **kwargs)
