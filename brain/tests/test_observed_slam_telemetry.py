import json
import math
from types import SimpleNamespace as NS
import numpy as np
import pytest
from ssbot.combat import observed_slam as O
from ssbot.combat.planner import PlanResult
from ssbot.train.forum_planner_policy import ForumPlannerPolicy
from ssbot.train.measurement import MeasurementTrace


def context():
    inst=NS(fam='CC_SLAM',states=['Slam 1'],t0=.5,x0=0.,y0=0.,s=1,hero_du=0.)
    row=O.Motion(inst,17,14,.6,1,True,True,True,16)
    clock={'f':17,'fc':14,'fs':1,'dt':1/60,'fdt':.02,'ts':1.}
    rt=NS(now={1:(O.CLAPPER,{'hp':10.},inst)},observed_motion=NS(clock=clock,by_iid={1:row},stops=1))
    f=NS(rs=NS(trk=rt,focus=1),origin_t=1.02,fc=NS(trackers={1:NS(state='Slam 1',t_entry=1.,table=NS(dwell={'Slam 1':(.04,.06)}))}))
    boxes=[NS(name='body',active=True,poly=[(0,0),(1,0),(1,1)]),NS(name='Slam Collider 1',active=True,poly=[(0,0),(1,0),(1,1)])]
    e=NS(id=1,type_key=NS(v=O.CLAPPER),fsm=[('Control','Slam 1',.02)],dmg_boxes=boxes)
    ws=NS(stamp=NS(frame=17),entities=[e])
    return ws,f,rt,inst,row


def test_expiry_telemetry_is_numeric_noop_and_retains_polygon_order():
    ws,f,rt,_,_=context();a={};old=O.seen_expiries(ws,f);new=O.seen_expiries(ws,f,audit=a)
    np.testing.assert_array_equal(new,old)
    assert a['expiry_status']=='evaluated' and a['frame_match'] is True
    assert [(x['index'],x['iid'],x['collider']) for x in a['polygons']]==[(0,1,'body'),(1,1,'Slam Collider 1')]
    assert a['polygons'][0]['expiry_kind']=='infinite' and a['polygons'][0]['expiry_s'] is None
    assert a['polygons'][1]['expiry_s']==new[1] and a['polygons'][1]['reason']=='mapped_latest_with_fixed_guard'
    json.dumps(a,allow_nan=False)


@pytest.mark.parametrize('change,reason',[('scale','scaled_or_frozen_clock'),('phase','tracked_move_or_phase_mismatch'),('owner','not_lifetime_owner'),('age','inner_world_age_mismatch'),('step','unknown_dwell_or_clock')])
def test_infinite_reasons_come_from_actual_expiry_evaluation(change,reason):
    ws,f,rt,_,_=context()
    if change=='scale':rt.observed_motion.clock['ts']=.5
    elif change=='phase':rt.now[1][2].fam='CC_JUMP'
    elif change=='owner':rt.now[2]=(O.CLAPPER,{'hp':10.},NS());f.rs.focus=2
    elif change=='age':f.origin_t=1.07
    else:rt.observed_motion.clock['fdt']=None
    a={};old=O.seen_expiries(ws,f);new=O.seen_expiries(ws,f,audit=a)
    np.testing.assert_array_equal(new,old);assert math.isinf(new[1])
    assert a['polygons'][1]['reason']==reason


def test_mismatched_origin_does_not_fake_infinite_values_or_evaluation():
    ws,f,rt,_,_=context();rt.observed_motion.clock['f']=18;a={}
    assert O.seen_expiries(ws,f,audit=a) is None
    assert a['expiry_status']=='not_evaluated' and a['polygons'] is None
    assert a['reason']=='tracker_frame_mismatch' and a['frame_match'] is False


def test_offset_counts_distinguish_call_from_changed_displacement_and_foreign_instance():
    _,_,rt,i,row=context();tab=NS(position=lambda tp,b,*unused:(min(b,5)*.6,0.))
    before=O.motion_snapshot(rt)
    assert O.predicted_offset(tab,i,None,0,1,row,audit_kind='support')==(0.,0.)
    assert O.predicted_offset(tab,i,None,8,9,row,audit_kind='body')==(0.,0.)
    other=NS(**i.__dict__);O.predicted_offset(tab,other,None,0,1,row,audit_kind='support')
    after=O.motion_snapshot(rt)
    assert before['units'][0]['offset_calls']['support_calls']==0
    assert after['units'][0]['offset_calls']=={'support_calls':1,'support_changes':1,'body_calls':1,'body_changes':0}
    assert after['units'][0]['instance_t0']==.5 and after['units'][0]['stop_f']==16
    json.dumps(after,allow_nan=False)


def policy(monkeypatch,enabled,stale=False):
    monkeypatch.setattr(O,'ENABLED',enabled);ws,f,rt,_,_=context()
    p=ForumPlannerPolicy.__new__(ForumPlannerPolicy);p.chain_native=None;p.raw={17: {'f':17}}
    p.measurement=NS(detail=True);p.v2feed=NS(trk=rt);p.tac=NS(last={})
    res=PlanResult(0,0,'WAIT',0,False)
    audit=O.audit_start(ws,f)
    if stale:audit['origin_frame']=16
    p.planner=NS(measurement_result=res,last_info={},observed_slam_audit=audit)
    return p,res


def test_policy_logs_actual_empty_evaluations_without_claiming_finite_or_safe(monkeypatch):
    p,res=policy(monkeypatch,True);p._measure_choice('plan',0,res,frame=17,origin_frame=17)
    evidence=p.measurement_choice['observed_slam']
    assert evidence['status']=='captured' and evidence['seen_evaluations']==[]
    assert evidence['seen_status']=='not_evaluated' and evidence['captured_at']=='choice_before_send'
    assert evidence['motion_after']['units'][0]['stopped'] is True
    assert p.measurement_choice['candidate_S']==0 and p.measurement_choice['planner_mask']==0


def test_stale_policy_context_is_not_attributed_to_new_tick(monkeypatch):
    p,res=policy(monkeypatch,True,True);p._measure_choice('plan',0,res,frame=17,origin_frame=17)
    e=p.measurement_choice['observed_slam']
    assert e['status']=='no_current_planner_context' and e['seen_evaluations'] is None
    assert e['previous_context_frame']==16


def test_default_off_policy_does_not_add_trace_fields(monkeypatch):
    p,res=policy(monkeypatch,False);p._measure_choice('plan',0,res,frame=17,origin_frame=17)
    assert 'observed_slam' not in p.measurement_choice


def test_real_measurement_serializes_model_evidence_on_each_tick(monkeypatch,tmp_path):
    p,res=policy(monkeypatch,True);p._measure_choice('plan',0,res,frame=17,origin_frame=17)
    trace=MeasurementTrace(protocol_version=2);trace.start_episode(0)
    trace.begin_tick({'f':17,'dt':1/60,'hero':{},'act':{}})
    trace.decision(p.measurement_choice,returned_mask=0,flags=0);trace.end_tick()
    target=tmp_path/'trace.jsonl';trace.write(target)
    tick=next(x for x in map(json.loads,target.read_text().splitlines()) if x['kind']=='tick')
    assert tick['observed_slam']['motion_after']['tracker_frame']==17
    assert tick['observed_slam']['seen_evaluations']==[] and tick['returned_mask']==0


def test_missing_monitor_reports_unknown_without_reconstructing_a_stop():
    ws,f,rt,_,_=context();rt.observed_motion=None
    snapshot=O.motion_snapshot(rt)
    assert snapshot['monitor_available'] is False and snapshot['tracker_frame'] is None
    assert snapshot['units'][0]['same_instance'] is False
    assert snapshot['units'][0]['offset_calls']['support_calls'] is None
    json.dumps(snapshot,allow_nan=False)


def test_motion_snapshot_does_not_retain_live_state_graphs():
    _,_,rt,inst,row=context();snapshot=O.motion_snapshot(rt)
    row.stop_f=99;inst.states.append('Idle');rt.observed_motion.clock['f']=19
    assert snapshot['units'][0]['stop_f']==16 and snapshot['units'][0]['phase']=='Slam 1'
    assert snapshot['tracker_frame']==17


def test_policy_frame_is_separate_from_forecast_origin(monkeypatch):
    p,res=policy(monkeypatch,True)
    p._measure_choice('plan',0,res,frame=19,origin_frame=17)
    e=p.measurement_choice['observed_slam']
    assert e['status']=='captured' and e['origin_frame']==17 and e['policy_frame']==19


def test_early_return_without_forecast_origin_does_not_reuse_context(monkeypatch):
    p,res=policy(monkeypatch,True)
    p._measure_choice('no_world_state',0,frame=18)
    e=p.measurement_choice['observed_slam']
    assert e['status']=='no_current_planner_context' and e['seen_evaluations'] is None
    assert e['origin_frame'] is None and e['policy_frame']==18


def test_act_early_quit_clears_previous_planner_context(monkeypatch):
    p,res=policy(monkeypatch,True)
    p._begin_chain_native=lambda s:None
    p._real_quit_step=lambda s,f:0
    p.real_quit=True;p.sc=NS(pq=NS(t_confirm=0))
    p.measurement.diagnostics=None
    assert p.act({'f':18})==0
    e=p.measurement_choice['observed_slam']
    assert p.planner.observed_slam_audit is None
    assert e['previous_context_frame'] is None and e['policy_frame']==18
