import copy
import json
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import scene_field_event_shadow as S, scene_field_events as E, scene_field_locked as L
from ssbot.combat.scene_field_inputs import load_inputs
from ssbot.core import forum as F
from ssbot.train import forum_planner_policy as P


@pytest.fixture(scope='module')
def inputs():
    E.warmup()
    return S._startup_inputs()


def native():
    def entity(i,x,state):
        box=[x-1.8,3.,x+1.8,3.,x+1.8,10.,x-1.8,10.]
        return {'iid':i,'type_key':E.CLAPPER,'category':'enemy','pos':[x,7.5,0.], 'vel':[0.,0.], 'flipX':True,
                'fsms':[{'name':'cosmetic','state':'not_Control','t':0.}, {'name':'Control','state':state,'t':.1}],
                'colliders':[{'kind':'box','name':E.CLAPPER,'enabled':True,'verts_world':box}]}
    a,b=entity(1,38.,'Air'),entity(2,24.,'Idle')
    inst=NS(fam='CC_JUMP_CAST',t0=.1,dec={'t':.9,'x':38.,'y':7.5,'s':-1,'L':4.,'b':56})
    trk=NS(T=1.,ents=[a,b],now={1:(E.CLAPPER,a,inst),2:(E.CLAPPER,b,None)},tables={E.CLAPPER:NS(facing=lambda flip:1)})
    state={'game':{'scene':'Hang_04'},'room':{'seq':4}}
    arena=L.forum_arena(F.WALL_L,F.WALL_R,F.FLOOR_Y,F.DOME)
    return trk,state,{'Hang_04':arena}


def test_package_is_portable_checked_once_and_arrays_are_readonly(inputs,tmp_path):
    assert inputs is S._startup_inputs()
    assert inputs.t_centre.shape==(16,85,2)
    assert all(not getattr(inputs,n).flags.writeable for n in ['t_centre','t_vel','t_ground'])
    root=Path(S.__file__).resolve().parents[3]/'knowledge/1.0.30000/scene_field'
    meta=json.loads((root/'scene_field_inputs43.json').read_text())
    (tmp_path/'model.json').write_text(json.dumps(meta))
    raw=(root/meta['npz_file']).read_bytes()
    (tmp_path/meta['npz_file']).write_bytes(raw[:-1]+bytes([raw[-1]^1]))
    with pytest.raises(ValueError,match='sha256'):load_inputs(tmp_path/'model.json',E.Inputs)
    meta['npz_file']='../x.npz';(tmp_path/'model.json').write_text(json.dumps(meta))
    with pytest.raises(ValueError,match='bare file'):load_inputs(tmp_path/'model.json',E.Inputs)


def test_native_view_uses_named_control_and_discrete_room_move_lock_key(inputs):
    trk,state,arenas=native()
    def view():return L.locked_scene(trk,room=L.room_of_state(state),arenas=arenas,bombs=np.empty((0,6)),pend=[])
    v=view();assert v['status']=='ok'
    k=L.field_key(E.cache_key,v['scene'],v['lock'],E.Config(),inputs)
    trk.T+=1/60;trk.now[1][1]['pos'][0]+=.2
    q=view();assert L.field_key(E.cache_key,q['scene'],q['lock'],E.Config(),inputs)==k
    trk.now[1][2].dec['t']+=.01
    q=view();assert L.field_key(E.cache_key,q['scene'],q['lock'],E.Config(),inputs)!=k
    state['room']['seq']+=1
    q=view();assert L.field_key(E.cache_key,q['scene'],q['lock'],E.Config(),inputs)!=k


def test_missing_or_truncated_hazards_remain_unknown(inputs):
    trk,state,arenas=native();kw=dict(room=L.room_of_state(state),arenas=arenas,pend=[])
    assert L.locked_scene(trk,**kw)['reason']=='small_runes_unknown'
    assert L.locked_scene(trk,bombs=[],bombs_complete=False,**kw)['reason']=='small_runes_truncated'
    assert L.locked_scene(trk,bombs=[[1.,np.nan,0.,1.,0.,5.]],**kw)['reason']=='small_runes_unknown'
    trk.ents=None
    assert L.locked_scene(trk,bombs=[],**kw)['reason']=='entities_unknown'


def test_low_frequency_shadow_queries_one_complete_field_and_reports_refresh_delta(inputs,monkeypatch):
    trk,state,arenas=native();reader=S.SceneFieldEventShadow(inputs,arenas)
    path=np.tile([15.25,3.015,15.75,5.0938],(37,1))
    calls=[];build=E.build
    def counted(*a,**k):calls.append(1);return build(*a,**k)
    monkeypatch.setattr(E,'build',counted)
    def inspect():return reader.inspect(trk,state,[],path,frame=100,origin_frame=100,k_shift=0,bombs=np.empty((0,6)),bombs_T=trk.T)
    a=inspect();assert a['status']=='sampled' and a['rebuilt'] and a['grids']==72
    assert not a['applied_to_ranking'] and not a['cross_time_total_ranking_allowed']
    assert not a['actual_endpoint_capability_checked']
    trk.T+=.1;b=inspect();assert not b['rebuilt'] and b['snapshot_origin_s']==a['snapshot_origin_s'] and len(calls)==1
    trk.T+=.16;c=inspect();assert c['rebuilt'] and len(calls)==2
    assert set(c['refresh_delta'])==set(E.COMPONENTS)
    json.dumps(c,allow_nan=False)
    trk.T+=4.;assert inspect()['status']=='lock_event_over' and len(calls)==2


def test_stale_or_missing_bomb_origin_never_builds(inputs):
    trk,state,arenas=native();reader=S.SceneFieldEventShadow(inputs,arenas)
    kw=dict(frame=1,origin_frame=1,k_shift=0,bombs=np.empty((0,6)))
    assert reader.inspect(trk,state,[],None,bombs_T=None,**kw)['status']=='small_runes_unknown'
    assert reader.inspect(trk,state,[],None,bombs_T=0.,**kw)['status']=='small_runes_stale'
    assert reader.inspect(trk,state,[],None,bombs_T=trk.T,fresh=False,**kw)['status']=='stale_result'
    assert reader.cache._field is None


def test_policy_hook_observes_without_changing_result_or_predicting(inputs):
    trk,state,arenas=native();trk.rune=NS(predict=lambda *a:pytest.fail('observer called predictor'))
    p=P.ForumPlannerPolicy.__new__(P.ForumPlannerPolicy)
    p.measurement=NS(detail=True);p.v2feed=NS(trk=trk);p._scene_field_error=False
    p._scene_field_event_reader=S.SceneFieldEventShadow(inputs,arenas)
    path=np.tile([15.25,3.015,15.75,5.0938],(37,1));res=NS(path=path,mask=4,S=0,J=2.)
    rs=NS(pend=[],k_shift=0,scene_field_bombs=np.empty((0,6)),scene_field_bombs_T=trk.T)
    before=path.copy();p._scene_field_after_plan(res,NS(rs=rs),3,3,fresh=True,state=state)
    assert p._scene_field_current['status']=='sampled' and not p._scene_field_error
    assert (res.mask,res.S,res.J)==(4,0,2.) and np.array_equal(path,before)


def test_native_pool_and_full_forecast_are_not_rejected_as_unknown_damagers():
    trk,state,arenas=native()
    pool={'iid':-1,'type_key':'damager','category':'hazard','pos':[12.,3.],
          'colliders':[{'kind':'circle','enabled':False,'r':2.166}]}
    active=copy.deepcopy(pool);active['iid']=-2;active['pos']=[16.,3.]
    active['colliders'][0].update(enabled=True,r=2.1661725)
    trk.ents.extend([pool,active]);bombs=[[2.,16.,3.,2.166,0.,6.]]
    v=L.locked_scene(trk,room=L.room_of_state(state),arenas=arenas,bombs=bombs,pend=[])
    assert v['status']=='ok'
    assert v['aux']['hazard_split']=={'inactive':[-1],'small_rune_rows':[-2],'unmodelled':[]}
    assert len(v['aux']['observed_damager_ents'])==2
    assert v['scene']['hazards']['observed_damager_ents']==[]
    assert v['scene']['hazards']['small_runes']['rows']==[{'owner':2,'x':16.,'y':3.,'r':2.166,'on_k':0,'off_k':6}]
    q=L.locked_scene(trk,room=L.room_of_state(state),arenas=arenas,bombs=[],pend=[])
    assert q['reason']=='observed_damagers' and q['aux']['hazard_split']['unmodelled']==[-2]


@pytest.mark.parametrize('change', ['missing_colliders','unknown_enabled','box','big_circle','shifted',
                                    'radius_mismatch','not_lit_yet','already_off','nonfinite'])
def test_unmodelled_or_unknown_hazards_still_refuse_the_soft_field(change):
    trk,state,arenas=native()
    h={'iid':-3,'category':'hazard','type_key':'damager','pos':[16.,3.],
       'colliders':[{'kind':'circle','enabled':True,'r':2.166}]}
    bombs=[[2.,16.,3.,2.166,0.,6.]]
    if change=='missing_colliders':h['colliders']=[]
    elif change=='unknown_enabled':h['colliders'][0].pop('enabled')
    elif change=='box':h['colliders'][0]['kind']='box'
    elif change=='big_circle':h['colliders'][0]['r']=7.187
    elif change=='shifted':h['pos'][0]+=.01
    elif change=='radius_mismatch':h['colliders'][0]['r']+=.01
    elif change=='not_lit_yet':bombs[0][4]=1.
    elif change=='already_off':bombs[0][5]=-1.
    elif change=='nonfinite':h['colliders'][0]['r']=float('nan')
    trk.ents.append(h)
    v=L.locked_scene(trk,room=L.room_of_state(state),arenas=arenas,bombs=bombs,pend=[])
    assert v['reason']=='observed_damagers'
    assert v['aux']['hazard_split']['unmodelled']==[-3]
