import copy
import json
import os
import subprocess
import sys
from types import SimpleNamespace as NS
import numpy as np
import pytest
from ssbot.combat import scene_field_shadow as S
from ssbot.combat import scene_field_aim as A
from ssbot.combat.planner import PlanResult
from ssbot.train import forum_planner_policy as P


def tracker():
    def ent(x,box):
        x0,y0,x1,y1=box
        return {'pos':[x,7.449],'colliders':[{'kind':'box','name':'Song Heavy Sentry','enabled':True,
                'verts_world':[x0,y0,x1,y0,x1,y1,x0,y1]}]}
    inst=NS(fam='CC_JUMP_CAST',dec=None,t0=0.)
    trk=NS(T=.4995,now={1:('Song Heavy Sentry',ent(46.,[44.,3.015,48.,6.917]),inst),
                         2:('Song Heavy Sentry',ent(34.,[32.,3.015,36.,6.917]),None)})
    pending=[{'iid':1,'name':'CC_JUMP_CAST','x':46.,'y':7.449,'d_lo':24,'d_hi':27}]
    return trk,pending


def path(n=37,dy=0.):
    return np.tile([37.25,3.015+dy,37.75,5.094+dy],(n,1))


def test_native_selected_path_filters_continuous_window_and_is_read_only():
    trk,pending=tracker();before=copy.deepcopy(trk);pb=path();old=pb.copy()
    reader=S.SceneFieldShadow.for_forum((14.6,48.4))
    r=reader.inspect(trk,pending,pb,frame=10,origin_frame=10,k_shift=0)
    assert r['status']=='sampled' and r['covered_samples']==3
    assert r['samples'][-1]['reason']=='after_decision_window'
    assert r['samples'][-1]['after_tracker_s']==.45
    assert r['applied_to_ranking'] is False and len(r['samples'])<=8
    assert trk==before and np.array_equal(pb,old)
    json.dumps(r,allow_nan=False)


def test_none_short_air_and_stale_paths_do_not_substitute_the_endpoint():
    trk,pending=tracker();reader=S.SceneFieldShadow.for_forum((14.6,48.4))
    kw={'frame':10,'origin_frame':10,'k_shift':0}
    assert reader.inspect(trk,pending,None,**kw)['status']=='no_path'
    assert reader.inspect(trk,pending,path(10),**kw)['status']=='beyond_row'
    assert reader.inspect(trk,pending,path(),fresh=False,**kw)['status']=='stale_result'
    r=reader.inspect(trk,pending,path(dy=2),**kw);assert r['covered_samples']==0
    assert all(x['reason']=='ground_scope_only' for x in r['samples'])


def test_identical_ordinary_chain_lookup_and_range_guards():
    trk,pending=tracker();reader=S.SceneFieldShadow.for_forum((14.6,48.4));v=S.native_view(trk,pending,reader.consts.ft)
    f=A.build_aim(v,reader.grid,reader.rules,reader.consts);mid=sum(f['time']['remaining_s'])*.5;y=sum(reader.consts.standing_box_y)*.5
    pts=[[37.5,y,mid]]
    assert S.query_aim(f,pts,reader.consts)==S.query_aim(f,copy.deepcopy(pts),reader.consts)
    q=S.query_aim(f,[[-1000,y,mid],[37.5,y,.2],[37.5,y,.6]],reader.consts)
    assert not any(x['known'] for x in q)
    assert [x['reason'] for x in q]==['outside_or_unknown','before_window_requires_hold','after_decision_window']


def bare_policy():
    p=P.ForumPlannerPolicy.__new__(P.ForumPlannerPolicy);p.chain_native=None;p.measurement=NS(detail=True);p.tac=NS(last={})
    trk,pending=tracker();p.v2feed=NS(trk=trk);p._scene_field_reader=S.SceneFieldShadow.for_forum((14.6,48.4));p._scene_field_error=False
    res=PlanResult(0,0,'WAIT',0,False);res.path=path()
    p.planner=NS(measurement_result=res,last_info={})
    forecast=NS(rs=NS(pend=pending,k_shift=0))
    return p,res,forecast


def test_policy_captures_current_shadow_without_changing_result(monkeypatch):
    monkeypatch.setattr(P,'SCENE_FIELD_SHADOW',True);monkeypatch.setattr(P.observed_slam,'ENABLED',False)
    p,res,f=bare_policy();before=(res.mask,res.S,res.J,res.path.copy())
    p._scene_field_after_plan(res,f,10,10,fresh=True)
    p._measure_choice('plan',res.mask,res,frame=10,origin_frame=10)
    e=p.measurement_choice['scene_field_shadow'];assert e['covered_samples']==3 and e['cost_ms']>=0
    assert (res.mask,res.S,res.J)==before[:3] and np.array_equal(res.path,before[3])
    p._measure_choice('plan',res.mask,res,frame=11,origin_frame=11)
    assert 'scene_field_shadow' not in p.measurement_choice


def test_disabled_choice_has_no_additional_field(monkeypatch):
    monkeypatch.setattr(P,'SCENE_FIELD_SHADOW',False);monkeypatch.setattr(P.observed_slam,'ENABLED',False)
    p,res,_=bare_policy();p._scene_field_current={'policy_frame':10,'status':'should_not_appear'}
    p._measure_choice('plan',0,res,frame=10,origin_frame=10)
    assert 'scene_field_shadow' not in p.measurement_choice


def test_noncontrolling_error_is_reported_once_and_never_takes_keys():
    p,res,f=bare_policy();calls=[]
    def broken(*args,**kwargs):calls.append(1);raise RuntimeError('probe failure')
    p._scene_field_reader=NS(inspect=broken)
    p._scene_field_after_plan(res,f,10,10,fresh=True)
    assert p._scene_field_current['status']=='error' and p._scene_field_error
    p._scene_field_after_plan(res,f,11,11,fresh=True)
    assert len(calls)==1 and res.mask==0


def test_default_off_does_not_import_field_modules():
    env=dict(os.environ);env.pop('SSBOT_FORUM_SCENE_FIELD_SHADOW',None)
    result=subprocess.run([sys.executable,'-B','-c',"import sys;from ssbot.train import forum_planner_policy as p;assert not p.SCENE_FIELD_SHADOW;assert 'ssbot.combat.scene_field_aim' not in sys.modules;assert 'ssbot.combat.scene_field_shadow' not in sys.modules"],env=env,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr


def test_switch_is_bound_in_measurement_manifest(tmp_path):
    from ssbot.train.forum_measure_manifest import configuration_manifest
    root=tmp_path/'ssbot';(root/'train').mkdir(parents=True)
    (root/'train/forum_planner_policy.py').write_text("import os\nSCENE_FIELD_SHADOW=os.environ.get('SSBOT_FORUM_SCENE_FIELD_SHADOW','0')=='1'\n")
    modules={'ssbot.train.forum_planner_policy':NS(SCENE_FIELD_SHADOW=True)}
    m=configuration_manifest(root,NS(chain_native=None),environ={'SSBOT_FORUM_SCENE_FIELD_SHADOW':'1'},modules=modules)
    e=m['switches']['SSBOT_FORUM_SCENE_FIELD_SHADOW'];assert e['resolution']=='runtime_binding'
    assert e['effective']=={'ssbot.train.forum_planner_policy.SCENE_FIELD_SHADOW':True}


def test_shadow_setting_cannot_share_one_b2_budget_revision(tmp_path,monkeypatch):
    from ssbot.combat import knife_chain_b2 as B,knife_chain_slam as SL
    from ssbot.combat.knife_chain_budget import LearningStop
    monkeypatch.setattr(SL,'load_runner',lambda:NS(cfg0={}))
    class Bare(B.NativeChainB2):
        def __init__(self,**kwargs):self.__dict__.update(kwargs)
    for key,value in {'SSBOT_FORUM_CHAIN_B2':'1','SSBOT_FORUM_CHAIN_BATCH':'test-shadow-profile',
        'SSBOT_FORUM_CHAIN_ARM':'A','SSBOT_FORUM_CHAIN_BUDGET':str(tmp_path/'budget.json'),
        'SSBOT_FORUM_CHAIN_FAST_HOOK':'0','SSBOT_FORUM_SCENE_FIELD_SHADOW':'0'}.items():monkeypatch.setenv(key,value)
    Bare.from_env(journal=str(tmp_path/'first.jsonl'))
    before=(tmp_path/'budget.json').read_bytes();monkeypatch.setenv('SSBOT_FORUM_SCENE_FIELD_SHADOW','1')
    with pytest.raises(LearningStop,match='revision'):Bare.from_env(journal=str(tmp_path/'second.jsonl'))
    assert (tmp_path/'budget.json').read_bytes()==before


def test_nonfinite_query_is_explicit_unknown_and_strict_json_safe():
    trk,pending=tracker();r=S.SceneFieldShadow.for_forum((14.6,48.4));f=A.build_aim(S.native_view(trk,pending,r.consts.ft),r.grid,r.rules,r.consts)
    out=S.query_aim(f,[[np.nan,4.0545,.4],[37.5,np.inf,.4],[37.5,4.0545,np.nan]],r.consts)
    assert not any(p['known'] for p in out)
    json.dumps(out,allow_nan=False)
