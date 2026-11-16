from pathlib import Path
import bisect,datetime as dt,hashlib,json,sys
import numpy as np
import psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');R=B/'analysis/task179_5df8711e_20261105';W=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
me=psutil.Process();me.cpu_affinity(list(range(24,32)));me.nice(psutil.IDLE_PRIORITY_CLASS);sys.dont_write_bytecode=True;sys.path.insert(0,str(W/'brain'))
from ssbot.train.measurement import validate_trace
from ssbot.knowledge import kinematics as K
from ssbot.combat.knife_chain_deadline import FRAME_NS,PREVIOUS_STATE_WINDOW_NS,SEND_RESERVE_NS
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def rows(p):return [json.loads(l) for l in p.read_text(encoding='utf-8-sig').splitlines() if l]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
case=read(B/'sol/performance/cases/task179_5df8711e.json');final=read(R/'p_v2/FINALIZED.json');packet=read(R/'SOURCE_PACKET.json')
assert final['execution_ok'] and final['cleanup_verified']
assert not read(B/'sol/STATUS.json')['live_or_budget_running']
assert all(sha(W/n)==h for n,h in packet['raw_runtime_files_sha256'].items())
out={'at':dt.datetime.now(dt.timezone.utc).isoformat(),'source':case['source'],'entry_sha256':case['entry_sha256'],'contexts':{},'actual_cleanup':final,
     'integrity_pass':True,'critical_point_pass':True,'complete_scheduling_gate_pass':False,'new_game_gate':False,
     'scope':'135 actual measured complete calls on two changed model/conditional-NPC continuations; no new live action proof; original postloss enemy trace may be paused',
     'old_v1':'0 measured ticks blocked by Defender1.2128cores; preserved and finalized, no control performance failure'}
for q in case['contexts']:
 d=R/'p_v2'/q['name'];result=read(d/'RESULT.json');manifest=read(d/'CONFIGURATION_MANIFEST.json');validation=validate_trace(d/'measurement_trace.jsonl')
 ts=rows(d/'measurement_trace.jsonl');tick={v['f']:v for v in ts if v.get('kind')=='tick'};act={v['f']:v for v in ts if v.get('kind')=='action'};frames=sorted(tick)
 assert frames==list(range(q['from'],q['last']+1)) and set(tick)==set(act)
 assert validation['complete'] and result['functional_validation']['passed'] and result['exception'] is None and result['foreign']==[]
 timing=result['p_entry']['timing'];runtime=timing['runtime']
 assert runtime['cpu_affinity']==list(range(16)) and runtime['priority']==128 and not runtime['query_errors'] and runtime['power_throttling']['execution_speed_throttled'] is False
 assert timing['send_clock_required'] is True
 assert timing['signatures_before']==result['signatures_after']
 assert all(sha(W/'brain/ssbot'/n)==h for n,h in result['source_sha256'].items())
 assert manifest['unresolved']==['SSBOT_FORUM_CHAIN_BLOCK','SSBOT_FORUM_CHAIN_ORDER','SSBOT_FORUM_CHAIN_SCHEDULE']
 receives={}
 for x in rows(Path(q['trial'])/'run/measurement_i0_e0.jsonl'):
  if x.get('kind')=='receive':receives.setdefault(x['f'],x['recv_ns'])
 rf=sorted(receives);rn=[receives[f] for f in rf];assert rn==sorted(rn)
 cost={f:tick[f]['tick_end_ns']-tick[f]['tick_start_ns'] for f in frames};send={f:act[f]['send_done_ns']-tick[f]['tick_start_ns'] for f in frames}
 def schedule(wake,stress=None):
  free=-float('inf');last=frames[0]-1;schedule_rows=[]
  while last<frames[-1]:
   pending=[f for f in frames if f>last];ready=[f for f in pending if receives[f]<=free];f=max(ready) if ready else pending[0]
   start=max(free,receives[f])+wake*1e6+(15.782995-wake)*1e6*(f==stress)
   sent=start+send[f];latest=rf[bisect.bisect_right(rn,sent)-1];applied=None
   for target in range(f+2,f+11):
    deadline=min(receives[target-2]+PREVIOUS_STATE_WINDOW_NS+FRAME_NS,receives[target-1]+PREVIOUS_STATE_WINDOW_NS)
    if latest<target and sent+SEND_RESERVE_NS<deadline:applied=target;break
   assert applied is not None
   schedule_rows.append({'f':f,'mask':int(act[f]['mask']),'target':f+2,'applied':applied,'late':applied-(f+2),'lag_ms':(start-receives[f])/1e6,'slack_ms':(deadline-sent-SEND_RESERVE_NS)/1e6,'skipped':[g for g in pending if g<f]})
   free,last=start+cost[f],f
  return schedule_rows
 summaries={}
 for name,wake in [('idle_p50',.270),('idle_p99',1.292),('idle_max',7.132)]:
  rr=schedule(wake);summaries[name]={'ticks':len(rr),'late':[v for v in rr if v['late']],'skipped':[f for v in rr for f in v['skipped']],
    'minimum_slack_ms':min(v['slack_ms'] for v in rr),'key_rows':[v for v in rr if v['f'] in (2679,2699,2720,2761,2765)]}
 # Isolated historical lag stress at changed direction/escape edge, preserving all intervening measured costs.
 stressframes=[2679] if q['name']=='l1_early_handoff' else [2761,2765]
 stress={str(f):{'late':[v for v in schedule(.270,f) if v['late']],'skipped':[g for v in schedule(.270,f) for g in v['skipped']]} for f in stressframes}
 vals=[v['total_tick_ms'] for v in tick.values()];critical=[tick[f] for f in (2699,2720) if f in tick]
 if any(v['total_tick_ms']>13.5503383333333 for v in critical):out['critical_point_pass']=False
 out['contexts'][q['name']]={'ticks':len(frames),'range':[frames[0],frames[-1]],'p50_ms':float(np.percentile(vals,50)),'p99_ms':float(np.percentile(vals,99)),'peak_ms':max(vals),
  'over_point':[{'f':f,'owner':tick[f]['owner'],'mask':act[f]['mask'],'total_ms':tick[f]['total_tick_ms'],'send_ms':send[f]/1e6} for f in frames if tick[f]['total_tick_ms']>13.5503383333333],
  'key_ticks':[{'f':f,'owner':tick[f]['owner'],'mask':act[f]['mask'],'ms':tick[f]['total_tick_ms'],'hold_filter':tick[f]['hold_filter'],'prefix':tick[f]['inflight_prefix']} for f in (2679,2699,2720,2761,2765) if f in tick],
  'functional':result['functional_validation'],'trace':validation,'runtime':runtime,'field_worker':timing['field_worker'],
  'configuration_complete_raw':manifest['configuration_complete'],'unresolved_raw':manifest['unresolved'],'signatures_unchanged':True,
  'serial':summaries,'isolated_lag_p99':stress,'strict_model_hurt':result['first_model_hurt'],'physical_hit_or_safe_exit_proven':False,
  'serial_scope':'old actual receive timestamps; start idle at measured boundary then latestSTATE; fixed historical .270/1.292 calibration as304; no GIL/clock future guarantee; does not replay changed policy after delayed packets'}
out['pending']='review actual escape-direction/DASH edge lateness and necessary successor; do not optimize merely because ordinary tick exceeds13.55 or shift absolute J/D'
p=R/'p_v2/ROOT_P_AUDIT.json';assert not p.exists();p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'audit':str(p),'integrity':True,'critical_point_pass':out['critical_point_pass'],'contexts':{n:{'ticks':v['ticks'],'peak_ms':v['peak_ms'],'p99_ms':v['p99_ms'],'serial_p99_late':v['serial']['idle_p99']['late'],'serial_p99_skipped':v['serial']['idle_p99']['skipped'],'isolated_lag_p99':v['isolated_lag_p99']} for n,v in out['contexts'].items()}},ensure_ascii=False))
