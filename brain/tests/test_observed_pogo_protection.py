"""Observed remaining pogo protection, not a new hit or a longer safety window."""
from copy import deepcopy
from dataclasses import replace
import math
import numpy as np
import pytest
from ssbot.knowledge import kinematics as k
from tests.test_kinematics import _state

@pytest.fixture(scope="module")
def params():
    return k.hero2(k.HeroParams.load(k.REPO/"knowledge/1.0.30000/kinematics/hero_wanderer_forum.json"),on=True)

def raw(f,n=8,alpha=.3034117519855499,inv=0.):
    s=_state(f,25.,9.,onGround=False,jumping=True,downSpikeBouncing=True)
    h=s["hero"];h.update(alpha=alpha,cstate_int=[31,n,0,0],tm={"inv":inv,"jump_steps":4,"jumped_steps":-20},
        anim={"clip":"DownSpikeBounce 2"},vel=[0.,-10.])
    return s

def tracked(params,s):
    t=k.StateTracker(params);t.push(s);return t

@pytest.mark.parametrize("alpha",[.13591204583644867,.3034117519855499,.6378127336502075,.8043876886367798])
@pytest.mark.parametrize("n",[1,2,4,8])
def test_projected_flags_expire_at_remaining_physics_count(params,n,alpha):
    t=tracked(params,raw(2879,n,alpha));S=t.state()
    assert S[k.POGO_OBS,0] == n
    assert S[k.INV_T,0] == 0
    ro=k.rollout(S,np.zeros((1,13),np.int64),params,None)
    expected=[math.floor(alpha+j*params.frame_time/params.fdt)<n for j in range(14)]
    assert list((ro.flags[0]&k.F_INVULN)!=0)==expected
    assert params.pogo_invul==.16

@pytest.mark.parametrize("with_tm",[False,True])
def test_batch_stream_and_trace_roundtrip_agree(params,with_tm,tmp_path):
    seq=[raw(i,n,alpha) for i,(n,alpha) in enumerate([(8,.3034),(7,.1359),(7,.9692),(6,.8025),(1,.8024),(0,.6357)])]
    if not with_tm:
        for s in seq:s["hero"].pop("tm")
    tr=k.Trace.from_states(seq,params);ref=k.estimate_state(tr,np.arange(len(seq)),params)
    t=k.StateTracker(params)
    for i,s in enumerate(seq):
        t.push(s);np.testing.assert_array_equal(t.S,ref[:,i])
        again=k.StateTracker(params);again.push_row(tr.row(i))
        assert again.S[k.POGO_OBS]==ref[k.POGO_OBS,i]
    file=tmp_path/"pogo.npz";tr.save(file);loaded=k.Trace.load(file)
    np.testing.assert_array_equal(loaded.pogo_steps,tr.pogo_steps)
    np.testing.assert_array_equal(k.estimate_state(loaded,np.arange(len(seq)),params),ref)
    assert ref[k.POGO_OBS,0]==8 and ref[k.POGO_OBS,-1]==0

@pytest.mark.parametrize("bad",[None,[],[31], [31,True], [31,-1], [31,8.0],[31,9],[31,100]])
def test_missing_invalid_or_out_of_profile_counts_do_not_invent_protection(params,bad):
    s=raw(1000);s["hero"]["cstate_int"]=bad
    assert tracked(params,s).S[k.POGO_OBS]==0


def test_zero_count_clears_observed_pogo_even_if_bounce_flag_stays_on(params):
    t=k.StateTracker(params)
    t.push(raw(1000,8));assert t.S[k.POGO_OBS]>0
    t.push(raw(1001,0));assert t.S[k.POGO_OBS]==0
    s=raw(1002);s["hero"].pop("cstate_int");t.push(s);assert t.S[k.POGO_OBS]==0


def test_damage_invulnerability_is_not_shortened(params):
    t=tracked(params,raw(1000,8,inv=.7));assert t.S[k.INV_T]==.7


def test_counter_does_not_change_motion_or_add_contact_events(params):
    s=raw(1000);base=deepcopy(s);base["hero"].pop("cstate_int")
    old=tracked(params,base);new=tracked(params,s)
    keep=[i for i in range(k.K) if i!=k.POGO_OBS]
    np.testing.assert_array_equal(old.S[keep],new.S[keep]);assert old.events==new.events
    commands=np.zeros((1,20),np.int64)
    a=k.rollout(old.state(),commands,params,None);b=k.rollout(new.state(),commands,params,None)
    for name in ("phys","pos","vel","box","mode"):np.testing.assert_array_equal(getattr(a,name),getattr(b,name))


def test_counter_obeys_explicit_steps_freeze_and_hitch(params):
    S=tracked(params,raw(1000,4)).state()
    masks=np.zeros((1,6),np.int64)
    fs=np.array([0,0,1,0,2,1])
    dt=np.array([0.,0.,.001,.001,.04,.02])
    ro=k.rollout(S,masks,params,None,dt=dt,fs=fs)
    assert list((ro.flags[0]&k.F_INVULN)!=0)==[True,True,True,True,True,True,False]


@pytest.mark.parametrize("alpha",[.4999,.9066666317321206,.9566666538570019,.9999])
@pytest.mark.parametrize("n",[1,2,6,8])
def test_all_clock_lanes_consume_their_own_steps(params,n,alpha):
    S=tracked(params,raw(1000,n,alpha)).state()
    # Include the high-phase >1 boundary and former float32 timer counterexamples.
    for scale in (1.,.1,.01):
        p=replace(params,frame_time=params.frame_time*scale)
        T=1100 if scale==.01 else 110 if scale==.1 else 12
        ro=k.rollout(S,np.zeros((1,T),np.int64),p,None,variants="bounds",lanes=True)
        variants=k.BOUNDS
        for vi,var in enumerate(variants):
            phase=alpha if var.alpha=="est" else max(0.,alpha-p.alpha_margin) if var.alpha=="lo" else alpha+p.alpha_margin
            ft=float(np.float32(p.frame_time))
            expected=[]
            for j in range(T+1):
                expected.append(j == 0 or math.floor(phase+j*ft/p.fdt+1e-10)<n)
            assert list((ro.var_flags[0,vi]&k.F_INVULN)!=0)==expected


def test_hunter_model_keeps_original_estimate(params):
    hunter=replace(params,abilities=0,hero2=0)
    a=raw(1000);b=deepcopy(a);b["hero"].pop("cstate_int")
    np.testing.assert_array_equal(tracked(hunter,a).S,tracked(hunter,b).S)


def test_prepacked_b2_step_and_trace_keep_exact_counter(params):
    from ssbot.combat.knife_chain_step import NominalStepper
    terrain=k.Terrain2D.from_boxes([])
    S=tracked(params,raw(1000,8,.9999)).state()[:,0]
    masks=np.zeros(20,np.int64)
    ref=k.rollout(S,masks[None],params,terrain)
    states,box,pos,flags,game=NominalStepper(params,terrain).trace(S,masks,0.)
    np.testing.assert_array_equal(flags,ref.flags[0])
    np.testing.assert_array_equal(box,ref.box[0])
    np.testing.assert_array_equal(states[:,-1],ref.final[:,0])
    assert states[k.POGO_OBS,0]==8 and states[k.POGO_OBS,-1]==0


def test_counter_reference_and_compiled_backend_agree(params):
    p=replace(params,abilities=0,hero2=0)
    S=k.initial_state(p,25.,9.,ground=False)
    S[k.POGO_OBS]=8
    S[k.ALPHA]=S[k.ALO]=S[k.AHI]=.9999
    masks=np.zeros((1,20),np.int64)
    a=k.rollout(S,masks,p,None,backend="numba",variants="bounds",lanes=True)
    b=k.rollout(S,masks,p,None,backend="numpy",variants="bounds",lanes=True)
    for name in ("phys","pos","vel","box","flags","final","var_flags"):
        np.testing.assert_array_equal(getattr(a,name),getattr(b,name))
