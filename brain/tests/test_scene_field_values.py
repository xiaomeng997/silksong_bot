from types import SimpleNamespace as NS
import numpy as np
import pytest
from ssbot.knowledge import kinematics as K
from ssbot.combat.scene_field_grid import SceneFieldGrid
from ssbot.combat.scene_field_events import FieldSet
from ssbot.combat.scene_field_values import SceneFieldValues
from ssbot.combat.forum_planner import ForumPlanner
from ssbot.combat.knife_chain_b2 import NativeChainB2


def field():
    grids={}
    vals={'ground_run_wait':.1,'ground_jump_ready':.3,'ground_dash_ready':.6,'ground_jump_dash_ready':.9}
    for name,value in vals.items():
        grids[('nominal','bounded_hold',name,'egress')]=SceneFieldGrid([0.,2.],[0.,10.],[4.],np.full((2,1,2),value),np.ones((2,1,2),bool),[[1,1]])
    return FieldSet(grids,{'identity':'test','t_origin_s':0.},{},4.,.05,('test',))


def rollout():
    box=np.tile([4.75,3.,5.25,5.],(5,31,1));flags=np.full((5,31),K.F_GROUND);flags[4]=0
    mode=np.full((5,31),K.M_NORMAL);final=np.zeros((K.K,5))
    final[K.JHELD]=[1,0,1,0,0];final[K.DASH_CD]=[1,1,0,0,0]
    return NS(box=box,flags=flags,mode=mode,final=final)


def reader(shift=0,abilities=K.AB_DASH):
    return SceneFieldValues(field(),now_s=0.,k_shift=shift,frame_time=.02,abilities=abilities,weight_hits=1.,frame=42)


def test_same_world_component_and_model_capability_select_layers_in_batches():
    ro=rollout();before=ro.final.copy();r=reader();v,k=r.score_rollout(ro)
    assert np.allclose(v,[.1,.3,.6,.9,0.]) and k.tolist()==[True,True,True,True,False]
    assert r.last['known_rows']==4 and r.last['horizon_from_tracker_s']==pytest.approx(.6)
    assert set(r.last['layers'])=={'ground_run_wait','ground_jump_ready','ground_dash_ready','ground_jump_dash_ready'}
    assert np.array_equal(before,ro.final) and not r.last['path_safety_certified']


def test_unknown_and_out_of_time_endpoints_have_no_bonus_and_stay_unknown():
    ro=rollout();ro.box[0,:,0]+=100;ro.box[0,:,2]+=100;ro.final[:,1]=np.nan
    r=reader();v,k=r.score_rollout(ro);assert not k[0] and not k[1] and v[0]==v[1]==0.
    r=SceneFieldValues(field(),now_s=2.,k_shift=0,frame_time=.02,abilities=K.AB_DASH)
    v,k=r.score_rollout(rollout());assert not k.any() and not v.any()


def test_dash_capability_is_not_credited_when_the_model_has_no_dash():
    v,k=reader(abilities=0).score_rollout(rollout());assert np.allclose(v,[.1,.3,.1,.3,0.])


def test_prefix_shift_uses_absolute_tracker_time_without_moving_knots():
    r=reader(shift=2);times=r.field.grid('nominal','ground_run_wait','bounded_hold','egress').times.copy()
    r.score_rollout(rollout());assert r.last['horizon_from_tracker_s']==pytest.approx(.56)
    assert np.array_equal(times,r.field.grid('nominal','ground_run_wait','bounded_hold','egress').times)


def test_chain_endpoint_uses_the_same_field_as_an_ordinary_endpoint():
    ro=rollout();r=reader();v,k=r.score_rollout(ro)
    state=np.zeros((K.K,31));state[:,-1]=ro.final[:,0];state[K.MODE]=K.M_NORMAL
    path=NS(box=ro.box[0],flags=ro.flags[0],states=state)
    prefs=NS(weights={'hit':10.,'stance':0.,'risk':0.,'ground':0.,'face':0.},risk_x=[],risk=[],stance_x=5.,boss_x=None)
    planner=NS(scene_field_values=r)
    assert r.path_bonus(path,prefs)==pytest.approx(v[0]*10)
    assert NativeChainB2._endpoint(planner,path,prefs)==pytest.approx(v[0]*10)
    assert NativeChainB2._endpoint(NS(),path,prefs)==0.


def test_positive_field_disables_narrow_ordinary_value_proof():
    planner=ForumPlanner.__new__(ForumPlanner);planner.scene_field_values=object()
    assert planner._zero_hit_value_bound(None,None,None,None,start=None,P=0,T=0,N=0,cont=False,challenger=0.)==(None,None)


@pytest.mark.parametrize('weight',[float('nan'),float('inf'),-1.])
def test_invalid_weights_are_rejected(weight):
    with pytest.raises(ValueError):SceneFieldValues(field(),now_s=0.,k_shift=0,frame_time=.02,abilities=0,weight_hits=weight)


@pytest.mark.parametrize('field_present',[False,True])
def test_continuation_value_bound_remains_valid_with_optional_field(field_present,monkeypatch):
    from ssbot.combat import observed_slam
    monkeypatch.setattr(observed_slam,'ENABLED',False)
    calls=[]
    class Chain:
        b2=True
        arm='B'
        def continuation_value_bound(self,prefs):
            calls.append('bound')
            return 0.
        def propose(self,*args):calls.append('propose');return None
        def _note(self,*args,**kw):pass
    p=ForumPlanner.__new__(ForumPlanner);p.scene_field_values=object() if field_present else None
    p.chain_native=Chain();p.measurement_enabled=False
    result=NS(S=0,forced_risk=False,J=2.,t_ms={})
    p._ordinary_tick=lambda *args,**kw:result
    assert p.tick(NS(stamp=NS(frame=10)),None,None,None,None,None,None) is result
    assert calls==(['propose'] if field_present else ['bound'])


def test_ground_sprint_receives_position_utility_without_fake_jump_or_dash_readiness():
    ro=rollout();ro.flags[4]=K.F_GROUND;ro.mode[4]=K.M_SPRINT
    r=reader();v,k=r.score_rollout(ro)
    assert k[4] and v[4]==pytest.approx(.1)
    assert r.last_layers[4]=='ground_run_wait' and not r.last_points.flags.writeable
    before=r.last_points
    r.score_rollout(rollout())
    assert before is not r.last_points and not before.flags.writeable
