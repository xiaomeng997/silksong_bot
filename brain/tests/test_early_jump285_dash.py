"""285: the early-J recipe must match the actually sent wait tick, including existing DASH."""
from dataclasses import replace
import copy
import numpy as np
import pytest
from ssbot.combat import knife_chain_face_hook as FH
from ssbot.combat.knife_chain_transfer import propose
from ssbot.combat.knife_chain_air import _trace_events
from ssbot.combat.air_chain import ChainSim
from ssbot.combat.holdfilter import hold_filter_jit
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.knowledge import kinematics as K
from tests.test_knife_chain_face_hook_step import ground_scene,ground_plan


def ready(gap=11.):
    r,s,sim=ground_scene(gap=gap)
    s['hero']['tm']['dash_cd']=0.;sim.start[K.DASH_CD]=0.
    return r,s,sim


def test_recipe_does_not_start_a_dash_that_would_swallow_its_cached_jump():
    r,s,sim=ready()
    p=replace(ground_plan(),dash_k=12)
    e=FH.early_jump(r,p,sim,1000/60.,s,s['ents'][1],None,10,'walk',False)
    assert e['ok'] and e['jump_k']==13


def advance(s,sim,new_mask):
    # Consume the already-in-flight packet; the new packet remains the next prefix.
    lat,hf=hold_filter_jit(sim.prefix[None],sim.hold)
    st,bx,ps,fl,gm=_trace_events(np.asarray(sim.start).reshape(K.K),lat[0],np.zeros(1,np.int64),
                                s['f']/60.,sim.params.frame_time,sim.params.vector()[None],sim.terrain.packed())
    f=s['f']+1;state=copy.deepcopy(s);S=st[:,1].copy()
    bits=lambda a:sum(1<<i for i,x in enumerate(a) if x)
    state['f']=f
    state['hero'].update(pos=[float(S[K.PX]),float(S[K.PY])],vel=[float(S[K.VX]),float(S[K.VY])],
                         box=bx[1].tolist(),hero_accepting_input=not bool(fl[1]&K.F_NO_INPUT))
    state['hero']['tm']['dash_cd']=float(S[K.DASH_CD])
    state['act'].update(target=f,applied=f,mask=int(lat[0,0]),hf=dict(latched=bits(hf.latched[0]),desired=bits(hf.desired[0]),
                         pending=hf.pending[0].tolist(),age=hf.age[0].tolist()))
    for e in state['ents']:e['fsms'][0]['t']+=sim.params.frame_time
    return state,ChainSim(S,np.array([new_mask],np.int64),hf,sim.params,sim.terrain,f,f),bool(fl[1]&K.F_GROUND)


def test_accepted_wait_packet_really_leaves_room_for_next_cached_jump(monkeypatch):
    # Lower the fixture's dash-distance threshold to exercise the conditional
    # mutual exclusion inside the known reachable 11u jump recipe. The shipped
    # threshold remains12; the nominal14u counterexample is separate below.
    r,s,sim=ready();calls=[];real=FH.early_jump
    monkeypatch.setitem(r.chains['rune_transfer'].cfg['STOMP'],'dash_min_root',10.)
    def observed(*args,**kw):
        calls.append(args[2].f)
        return real(*args,**kw)
    monkeypatch.setattr(FH,'early_jump',observed)
    emitted=[];air=[];ground=True;history=[]
    for _ in range(6):
        made=propose(r,s,s['f']/60.,sim,8,ground,np.zeros((0,6)),set())
        assert made is not None and made[0] is not None
        r.run=made[0].run;emitted.append(made[3]);history.append((s['f'],dict(r.run.v.get('early_hook') or {}),int(np.asarray(sim.start).reshape(K.K)[K.MODE])))
        s,sim,ground=advance(s,sim,made[3]);air.append(not ground)
    assert r.run.v['early_hook']['ok'], history[0][1]['why']
    assert not emitted[0]&(B['DASH']|B['J'])
    assert emitted[1]&B['J'] and calls==[1000]
    assert any(air), 'the actually queued masks must leave the floor'


@pytest.mark.parametrize('case',['prefix','latched','desired','pending','mode'])
def test_expansion_cannot_withdraw_an_inflight_or_existing_dash(case):
    r,s,sim=ready();i=B['DASH'].bit_length()-1
    if case=='prefix':sim.prefix[0]|=B['DASH']
    elif case=='mode':sim.start[K.MODE]=K.M_DASH
    else:getattr(sim.hold,case)[0,i]=1
    before=sim.prefix.copy()
    e=FH.early_jump(r,replace(ground_plan(),dash_k=12),sim,1000/60.,s,s['ents'][1],None,10,'walk',False)
    assert not e['ok'] and 'in-flight dash' in e['why']
    assert np.array_equal(sim.prefix,before)


@pytest.mark.parametrize('disabled',[False,True])
def test_failure_or_disabled_feature_keeps_the_original_new_dash(disabled):
    r,s,sim=ready(gap=30.);r.chains['rune_transfer'].cfg['FACE_HOOK']=not disabled
    made=propose(r,s,1000/60.,sim,8,True,np.zeros((0,6)),set())
    assert made is not None and made[0] is not None and made[3]&B['DASH']
    assert not made[3]&B['J']
    assert disabled or not made[0].run.v['early_hook']['ok']


def test_nominal_far_entry_is_still_reach_limited_and_keeps_its_dash():
    r,s,sim=ready(gap=14.)
    made=propose(r,s,1000/60.,sim,8,True,np.zeros((0,6)),set())
    e=made[0].run.v['early_hook']
    assert not e['ok'] and e['deficit']>0 and 'face out' in e['why']
    assert made[3]&B['DASH']
