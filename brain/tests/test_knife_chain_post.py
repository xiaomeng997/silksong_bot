"""Prepared key candidates: fresh first step, actual complete physics and no safety reuse."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from ssbot.knowledge import kinematics as km
from ssbot.combat.air_chain import ChainSim
from ssbot.combat.knife_chain_nominal import compile_path,post_paths,NominalProfile,NominalUnsupported
from ssbot.combat.knife_chain_post import PostKeys,reroll_post,KINDS
from ssbot.combat.knife_chain_step import NominalStepper
from ssbot.combat.knife_chain_format import MASK_NAMES
from ssbot.combat.knife_chain_commitment import MoveInstance
from tests.test_knife_chain_b2 import params,terrain,preview,runner


@pytest.mark.parametrize('phase',[.01,.25,.9])
def test_trace_uses_existing_frame_loop_and_preserves_real_protection(params,terrain,phase):
    s=km.initial_state(params,35.,8.,ground=False,facing=-1)
    s[km.ALPHA]=s[km.ALO]=s[km.AHI]=phase;s[km.INV_T]=params.fdt*8
    keys=np.array([km.B_LEFT,0,km.B_JUMP,0,km.B_DASH,km.B_ATTACK]*6,np.int64)
    start=s.copy();game=3.25;states=[s.copy()];boxes=[];positions=[];flags=[];games=[game]
    z=km.rollout(s,np.zeros((1,0),np.int64),params,terrain)
    boxes.append(z.box[0,0]);positions.append(z.pos[0,0]);flags.append(z.flags[0,0])
    for m in keys:
        game+=params.frame_time*float(s[km.TS])*float(s[km.WF_S])
        q=km.rollout(s,np.array([[m]],np.int64),params,terrain);s=q.final[:,0].copy()
        states.append(s.copy());boxes.append(q.box[0,1]);positions.append(q.pos[0,1]);flags.append(q.flags[0,1]);games.append(game)
    got=NominalStepper(params,terrain).trace(start[:,None],keys,3.25)
    for a,b in zip(got,[np.stack(states,axis=1),boxes,positions,flags,games]):np.testing.assert_array_equal(a,b)


def setup(params,terrain):
    _,p,s,sim=preview(params,terrain)
    parent=compile_path(p.draft,s,sim,0.,stage='commitment',first_mask=p.mask)
    paths,errors=post_paths(parent,params,terrain);assert paths,errors
    bs=ChainSim(parent.states[:,-1],np.array([parent.queued_next],np.int64),parent.hold_end,params,terrain,parent.through,parent.through)
    move=MoveInstance(7,1000,'CC_SLAM')
    return parent,paths,bs,move


@pytest.mark.parametrize('kind',KINDS)
def test_prepared_keys_reroll_from_current_state_not_old_path(params,terrain,kind):
    parent,paths,bs,move=setup(params,terrain);full=paths[kind]
    tpl=PostKeys.from_path(full,move=move,kind=kind,source_frame=1000,table_digest=parent.runner_end.binding['table_digest'],profile=NominalProfile())
    before=deepcopy(parent.raw_end)
    cached=reroll_post(tpl,parent.runner_end,parent.raw_end,bs,float(parent.game[-1]),move=move,kind=kind,frame=1000,profile=NominalProfile(),first_mask=0,known_press=parent.press_frame)
    for field in ['commands','latched','states','box','pos','flags','check_flags','game']:
        np.testing.assert_array_equal(getattr(cached,field),getattr(full,field))
    assert parent.raw_end==before and cached.raw_end is None and cached.runner_end is None
    assert cached.first_draft.run.lid==full.first_draft.run.lid
    assert not tpl.commands.flags.writeable
    # A shifted current model really shifts the new path, rather than trusting
    # the cached old positions. The fixed sequence is independently rerolled.
    start=bs.start.copy();start[km.PX]+=.03;start[km.QX]+=.03;start[km.SX]+=.03
    actual=replace(bs,start=start)
    changed=reroll_post(tpl,parent.runner_end,parent.raw_end,actual,float(parent.game[-1]),move=move,kind=kind,frame=1000,profile=NominalProfile(),first_mask=0)
    assert changed.states[km.PX,0]==start[km.PX]
    assert changed.assumptions['old_positions_reused'] is False
    assert changed.assumptions['safety_reused'] is False


@pytest.mark.parametrize('bad',['instance','future','version','profile','first_key'])
def test_cache_rejects_wrong_identity_future_info_and_changed_actual_first_key(params,terrain,bad):
    parent,paths,bs,move=setup(params,terrain);kind='left_landing'
    tpl=PostKeys.from_path(paths[kind],move=move,kind=kind,source_frame=1000,table_digest=parent.runner_end.binding['table_digest'],profile=NominalProfile())
    if bad=='instance':tpl=replace(tpl,move=MoveInstance(7,1001,'CC_SLAM'))
    if bad=='future':tpl=replace(tpl,source_frame=1001)
    if bad=='version':tpl=replace(tpl,table_digest='other')
    if bad=='profile':tpl=replace(tpl,profile=NominalProfile(short_frames=13))
    if bad=='first_key':
        commands=tpl.commands.copy();commands[1]^=km.B_JUMP;tpl=replace(tpl,commands=commands)
    with pytest.raises(NominalUnsupported):
        reroll_post(tpl,parent.runner_end,parent.raw_end,bs,float(parent.game[-1]),move=move,kind=kind,frame=1000,profile=NominalProfile(),first_mask=0)


def test_current_prefix_and_hold_are_reapplied_and_uncovered_tail_is_not_padded(params,terrain):
    from ssbot.combat.holdfilter import hold_filter_jit
    parent,paths,bs,move=setup(params,terrain);kind="left_landing"
    tpl=PostKeys.from_path(paths[kind],move=move,kind=kind,source_frame=1000,table_digest=parent.runner_end.binding["table_digest"],profile=NominalProfile())
    actual=replace(bs,prefix=np.array([km.B_ATTACK],np.int64),hold=km.HoldState.idle(1))
    got=reroll_post(tpl,parent.runner_end,parent.raw_end,actual,float(parent.game[-1]),move=move,kind=kind,frame=1000,profile=NominalProfile(),first_mask=0)
    assert got.commands[0]==km.B_ATTACK
    lat,hold=hold_filter_jit(got.commands[None,:],actual.hold)
    np.testing.assert_array_equal(got.latched,lat[0])
    # Expiring before ground does not acquire a guessed release/ground state.
    with pytest.raises(NominalUnsupported,match="ground handoff"):
        reroll_post(replace(tpl,commands=tpl.commands[:2]),parent.runner_end,parent.raw_end,bs,float(parent.game[-1]),move=move,kind=kind,frame=1000,profile=NominalProfile(),first_mask=0)


def test_cache_instance_lifetime_and_reject_fallback(params,terrain,monkeypatch):
    from ssbot.combat.knife_chain_b2 import NativeChainB2
    import ssbot.combat.knife_chain_b2 as b2
    parent,paths,bs,move=setup(params,terrain);kind="left_landing"
    n=NativeChainB2(runner_factory=runner,probe_ref="post-cache-test")
    n._remember_post_keys(paths[kind],kind,move,1000)
    assert kind in n._post_keys
    calls=[];original=b2.compile_path
    def full(*a,**kw):
        calls.append(kw);return original(*a,**kw)
    monkeypatch.setattr(b2,"compile_path",full)
    # Wrong digest is rejected before use; original complete compiler is used.
    n._post_keys[kind]=replace(n._post_keys[kind],table_digest="invalid")
    got=n._post_path(parent.runner_end,parent.raw_end,bs,float(parent.game[-1]),kind=kind,move=move,frame=1000,mask=0)
    assert len(calls)==1 and got.end=="handback"
    assert n.counts["b2_post_keys_miss"]==1
    n._post_cache_for(MoveInstance(7,1001,"CC_SLAM"));assert not n._post_keys
    n._remember_post_keys(paths[kind],kind,move,1000)
    n.reset(2);assert not n._post_keys and n._post_key_move is None


def test_prepared_template_never_adds_unmodeled_hook(params,terrain):
    parent,paths,bs,move=setup(params,terrain);path=paths["left_landing"]
    commands=path.commands.copy();commands[-1]|=MASK_NAMES["CLAW"]
    with pytest.raises(NominalUnsupported,match="hook motion"):
        PostKeys.from_path(replace(path,commands=commands),move=move,kind="left_landing",source_frame=1000,table_digest=parent.runner_end.binding["table_digest"],profile=NominalProfile())
