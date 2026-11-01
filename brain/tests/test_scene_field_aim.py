"""Offline preview of portable aim API tests; no game or recording inputs."""
import builtins
import copy
import numpy as np
import pytest
from ssbot.combat import scene_field_aim as SF
from ssbot.combat.are_types import clapper as CL
from ssbot.combat import jump_behind as JB

@pytest.fixture
def model():
    rules=SF.RuleCallbacks(CL.jump_rule,CL.jump_branch,bool(JB.WALL_PUSH))
    k=SF.Constants(walls=(14.01,48.99),hero_half=(.25,1.0394),standing_box_y=(3.015,5.094),
      rune_slam_r=7.187,du_left_right=(6.48,6.75),ground_centre_y=3.34,ft=1/60,
      decision_s=(.883,.933),jump_gain=CL.JUMP_GAIN,jump_short=CL.JUMP_SHORT,
      jump_vx_max=CL.JUMP_VX_MAX,wall_zone=tuple(CL.WALL_ZONE),arena_x=(14.6,48.4))
    scene={'aim':{'pending_unlocked':[{'iid':1,'move':'CC_JUMP_CAST','x':46.,'y':7.449,'decision_window_frames':[23,26]}]},
      'enemies':{'rows':[{'iid':1,'type_key':'Song Heavy Sentry','root':[46.,7.449],'body_box':[44.,3.,48.,7.]},
                         {'iid':2,'type_key':'Song Heavy Sentry','root':[34.,7.449],'body_box':[32.,3.,36.,7.]}]},
      'tracker':{'instances':{'1':{'family':'CC_JUMP_CAST','decision':None,'started_frames_ago':30.}}}}
    return scene,rules,k

def test_view_ignores_actor_goal_and_future_labels(model):
    scene,_,_=model;other=copy.deepcopy(scene)
    other.update(hero={'pos':[0,99]},cues={'goal':'fake'},roles={'winner':True},labels_future={'health':0})
    assert SF.view_from_scene(scene)==SF.view_from_scene(other)

def test_explicit_time_window_and_late_arrival(model):
    scene,rules,k=model;r=SF.build_aim(SF.view_from_scene(scene),[30.,40.],rules,k)
    assert r['status']=='ok'
    assert SF.time_validity(.2,r['time'])=='before_window'
    assert SF.time_validity(.408,r['time'])=='inside_window'
    assert SF.time_validity(.6,r['time'])=='after_window'
    assert r['time']['production_window_frames']==[23,26]

def test_grid_order_does_not_change_components(model):
    scene,rules,k=model;view=SF.view_from_scene(scene)
    x=np.array([30.,44.,17.,40.,30.,46.5]);order=np.array([5,2,0,4,1,3]);inv=np.argsort(order)
    a=SF.build_aim(view,x,rules,k);b=SF.build_aim(view,x[order],rules,k)
    for key,u in a['fields'].items():
        v=b['fields'][key][inv]
        if u.dtype.kind in 'f':assert np.array_equal(u,v,equal_nan=True),key
        else:assert np.array_equal(u,v),key

def test_absent_and_expired_window_are_explicit(model):
    scene,rules,k=model
    assert SF.view_from_scene({'aim':{'pending_unlocked':[]}})['reason']=='no_pending'
    view=SF.view_from_scene(scene);view['age_frames']=60.
    r=SF.build_aim(view,[30.],rules,k)
    assert r['status']=='insufficient_coverage' and r['reason']=='window_passed'

def test_unexpected_rule_error_is_not_coverage(model):
    scene,_,k=model
    def broken(*args):raise RuntimeError('rule defect')
    with pytest.raises(RuntimeError,match='rule defect'):
        SF.build_aim(SF.view_from_scene(scene),[30.],SF.RuleCallbacks(broken,CL.jump_branch,False),k)

def test_invalid_branch_and_grid_raise(model):
    scene,rules,k=model;view=SF.view_from_scene(scene)
    with pytest.raises(ValueError,match='jump_branch'):
        SF.build_aim(view,[30.],SF.RuleCallbacks(rules.jump_rule,lambda *a:'invalid',False),k)
    with pytest.raises(ValueError,match='finite'):
        SF.build_aim(view,[np.nan],rules,k)

def test_build_reads_no_files_or_mutates_input(model,monkeypatch):
    scene,rules,k=model;view=SF.view_from_scene(scene);before=copy.deepcopy(view)
    def forbidden(*args,**kwargs):raise AssertionError('field must not read files')
    monkeypatch.setattr(builtins,'open',forbidden)
    r=SF.build_aim(view,[30.,40.],rules,k)
    assert r['status']=='ok' and view==before
