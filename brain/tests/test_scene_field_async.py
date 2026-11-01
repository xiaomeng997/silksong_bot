"""Whole-snapshot publication, bounded pending work, process IPC and cleanup."""
from copy import deepcopy
from pathlib import Path
import threading
import time
from types import SimpleNamespace as NS

import numpy as np
import pytest
from ssbot.combat import scene_field_async as A, scene_field_events as E, scene_field_locked as L
from ssbot.combat.scene_field_event_shadow import SceneFieldEventShadow, _startup_inputs
from ssbot.combat.scene_field_grid import SceneFieldGrid
from tests.test_scene_field_event_shadow import native


def bundle(origin=1., value=.1, selection=None):
    selection=selection or E.Selection(worlds=('nominal',),hyps=('bounded_hold',),components=('egress',))
    grids={}
    for w in selection.worlds:
        for h in selection.hyps:
            for layer in E.LAYERS:
                for c in selection.components:
                    grids[(w,h,layer,c)]=SceneFieldGrid([origin,origin+2.],[0.,70.],[4.],
                        np.full((2,1,2),value),np.ones((2,1,2),bool),[[1,1]])
    meta={'identity':str(value),'t_origin_s':origin,
          'worlds':{w:{'events_rel':[('circle_off',1.)]} for w in selection.worlds}}
    return E.FieldSet(grids,meta,{},4.,.05,('scene',),selection)


def view(now=1., room=4):
    trk,state,arenas=native();trk.T=now;state['room']['seq']=room
    return L.locked_scene(trk,frame=100,room=L.room_of_state(state),arenas=arenas,bombs=[],pend=[])


def local_client():
    # The policy-side state, without a worker. No future/result API exists here.
    x=A.AsyncFieldBuilder.__new__(A.AsyncFieldBuilder)
    x.inputs=_startup_inputs();x.selection=E.Selection(worlds=('nominal',),hyps=('bounded_hold',),components=('egress',))
    x.refresh_s=.25;x.max_age_s=.5;x.buffer=A.DoubleBuffer();x._epoch=x._sequence=0
    x._key=x._last_now=x._requested_at=x._request=x._failure=None
    x._stop=threading.Event()
    return x


def test_two_slots_replace_objects_while_old_tick_keeps_immutable_snapshot():
    b=A.DoubleBuffer();a=b.publish(1,1,('k',),1.,bundle(value=.1),1.)
    b.publish(1,2,('k',),1.1,bundle(1.1,.2),1.)
    c=b.publish(1,3,('k',),1.2,bundle(1.2,.3),1.)
    assert a.slot==c.slot and b.current is c and len(b.slots)==2
    assert all(np.all(g.values==.1) for g in a.field.grids.values())
    with pytest.raises(ValueError):next(iter(a.field.grids.values())).values[:]=4
    with pytest.raises(TypeError):a.field.grids[('bad',)]=None


def test_pack_roundtrip_has_all_layers_and_readonly_arrays():
    f=bundle();wire=A._pack(f);got=A._unpack(wire)
    assert set(got.grids)==set(f.grids)
    for k,g in got.grids.items():
        for n in ('times','xs','ys','values','known','regions'):
            assert np.array_equal(getattr(g,n),getattr(f.grids[k],n),equal_nan=True)
            assert not getattr(g,n).flags.writeable
    for bad in ('partial','duplicate','wrong_shape'):
        q=deepcopy(wire)
        if bad=='partial':q['grids'].pop()
        elif bad=='duplicate':q['grids'].append(q['grids'][0])
        else:q['grids'][0][1][3].resize((1,4),refcheck=False)
        with pytest.raises(ValueError):A._unpack(q)


def test_policy_offer_does_not_build_and_keeps_old_complete_field_during_refresh(monkeypatch):
    x=local_client();monkeypatch.setattr(E,'build',lambda *a,**k:pytest.fail('build in decision thread'))
    v=view();f,why=x.get(v);assert f is None and why=='async_pending'
    request=x._request;old=bundle();x.buffer.publish(*request[:4],old,1.)
    f,why=x.get(view(1.1));assert f is old and why=='ok' and x._sequence==1
    f,why=x.get(view(1.26));assert f is old and why=='ok' and x._sequence==2
    assert x._request[3]==1.26
    assert x.get(view(1.51))[1]=='async_snapshot_stale'


def test_scope_reset_clock_rollback_and_late_old_results_cannot_reenter():
    x=local_client();x.get(view());old=x._request;x.buffer.publish(*old[:4],bundle(),1.)
    assert x.get(view(1.05,room=5))[1]=='async_pending'
    # A response from room4 can arrive after the pointer to room5 was offered.
    x.buffer.publish(*old[:4],bundle(),1.)
    assert x.get(view(1.06,room=5))[1]=='async_pending'
    current=x._request;x.buffer.publish(*current[:4],bundle(1.05),1.)
    assert x.get(view(1.07,room=5))[0] is not None
    assert x.get(view(.95,room=5))[1]=='async_pending'
    x.get({'status':'insufficient','reason':'other_enemy'})
    assert x.buffer.current is None and x._request is None


def test_requests_are_latest_only_and_scene_is_detached():
    x=local_client();v=view();x.get(v);xpos=x._request[4]['enemies']['rows'][0]['root'][0]
    v['scene']['enemies']['rows'][0]['root'][0]+=100
    assert x._request[4]['enemies']['rows'][0]['root'][0]==xpos
    for t in (1.26,1.52,1.78):x.get(view(t))
    assert isinstance(x._request,tuple) and x._request[3]==1.78 and x._sequence==4


def test_worker_failure_is_explicit_not_a_silent_old_field_or_inline_rebuild():
    x=local_client();x._failure='build failed'
    with pytest.raises(RuntimeError,match='build failed'):x.get(view())


def delayed_worker(conn,input_path,arena,selection):
    # Real spawned IPC with a deliberately slow builder, no model computation.
    conn.send(('ready',{'pid':__import__('os').getpid(),'fixture':True}))
    try:
        while True:
            req=conn.recv();time.sleep(.2)
            field=bundle(req[3],float(req[1]),selection)
            conn.send(('field',req[:4],A._pack(field),200.))
    except (EOFError,BrokenPipeError):pass
    finally:conn.close()


def wait_for(fn,timeout=4.):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        result=fn()
        if result:return result
        time.sleep(.005)
    pytest.fail('background publication did not complete')


def test_real_slow_process_does_not_hold_policy_and_discards_old_scope(monkeypatch):
    monkeypatch.setattr(A,'_worker',delayed_worker)
    inputs=_startup_inputs();_,_,arenas=native()
    x=A.AsyncFieldBuilder(inputs,'unused',arenas['Hang_04'],bundle().selection)
    try:
        t=time.perf_counter();assert x.get(view())[1]=='async_pending'
        assert time.perf_counter()-t<.1  # background sleeps .2s
        pinned=wait_for(lambda:x.get(view())[0]);old_values=next(iter(pinned.grids.values())).values.copy()
        assert x.get(view(1.26))[0] is pinned
        assert x.get(view(1.27,room=5))[1]=='async_pending'
        current=wait_for(lambda:x.get(view(1.27,room=5))[0])
        assert current is not pinned and x.status()['slot'] in (0,1)
        assert np.array_equal(next(iter(pinned.grids.values())).values,old_values)
    finally:x.close()
    assert not x._process.is_alive() and not x._thread.is_alive()
    x.close()


def test_real_model_process_matches_reference_queries_and_closes():
    inputs=_startup_inputs();_,_,arenas=native();arena=arenas['Hang_04']
    path=Path(__file__).resolve().parents[2]/'knowledge/1.0.30000/scene_field/scene_field_inputs43.json'
    selection=bundle().selection;x=A.AsyncFieldBuilder(inputs,path,arena,selection)
    try:
        v=view();assert x.get(v)[1]=='async_pending'
        field=wait_for(lambda:x.get(v)[0],timeout=15.)
        expected=E.build(v['scene'],inputs,SceneFieldGrid,E.Config(),t_origin_s=1.,prepared=E.prepare(inputs,arena=arena),select=selection)
        assert set(field.grids)==set(expected.grids)
        for k,g in field.grids.items():
            for n in ('times','xs','ys','values','known','regions'):
                assert np.array_equal(getattr(g,n),getattr(expected.grids[k],n),equal_nan=True),(k,n)
        assert x.worker_info['cpus']==list(range(24,32)) and x.worker_info['pid']!=__import__('os').getpid()
        assert Path(x.worker_info['exe']).name.lower()=='pythonw.exe'
    finally:x.close()
    assert not x._process.is_alive() and not x._thread.is_alive()


def test_worker_cleanup_closes_async_builder_and_continues_owned_resources(tmp_path,monkeypatch):
    from ssbot.tools import combat_run as C
    from tests.test_b2_worker_batch import options
    monkeypatch.setenv('SSBOT_FORUM_CHAIN_B2','0')
    calls=[]
    def fail():calls.append('field');raise RuntimeError('child cleanup failed')
    policy=NS(_scene_field_event_reader=NS(close=fail))
    link=NS(closed=False,close=lambda:calls.append('ipc'))
    out=NS(close=lambda:calls.append('attempts'))
    result=C._close_worker(options(tmp_path),link=link,recorder=None,out=out,diagnostics=None,policy=policy,
        stage='episodes',primary_error='original error')
    assert calls==['field','attempts','ipc'] and not result['complete']
    assert result['primary_error']=='original error'


def test_policy_ranking_and_shadow_pin_the_same_complete_snapshot(monkeypatch):
    from ssbot.train import forum_planner_policy as P
    from ssbot.combat.scene_field_values import SceneFieldValues
    trk,state,arenas=native();reader=SceneFieldEventShadow(_startup_inputs(),arenas)
    field=bundle();field.meta['weights_TEMPORARY']={}
    calls=[]
    def offer(v):calls.append(v);return field,'ok'
    reader.async_builder=NS(get=offer,status=lambda:{'mode':'async_double_buffer'})
    p=P.ForumPlannerPolicy.__new__(P.ForumPlannerPolicy)
    p.crest='Wanderer';p.v2feed=NS(trk=trk);p.params=NS(frame_time=1/60,abilities=0)
    p._scene_field_event_reader=reader;p._scene_field_rank_type=SceneFieldValues
    p.planner=NS(scene_field_values=None);p.measurement=NS(detail=True);p._scene_field_error=False
    rs=NS(scene_field_bombs=[],scene_field_bombs_T=1.,pend=[],k_shift=0)
    monkeypatch.setattr(P.kin,'hero2_on',lambda:True)
    monkeypatch.setattr(P,'SCENE_FIELD_RANK',True)
    p._scene_field_before_plan(NS(rs=rs),state,100)
    assert p.planner.scene_field_values.field is field and len(calls)==1
    reader.async_builder.get=lambda v:pytest.fail('shadow fetched a different snapshot in the same tick')
    path=np.tile([15.25,3.015,15.75,5.0938],(37,1))
    p._scene_field_after_plan(NS(path=path),NS(rs=rs),100,100,fresh=True,state=state)
    assert not p._scene_field_error and p._scene_field_current['snapshot_id']==field.meta['identity']
