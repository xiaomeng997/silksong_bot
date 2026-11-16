"""Audit the two already completed #321 P windows; arithmetic only, no policy rerun/game."""
from pathlib import Path
import bisect,datetime,hashlib,json,os,sys,psutil,traceback
import numpy as np
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/task180_l2_322_20261106';D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
sys.path.insert(0,str(D/'brain'));sys.dont_write_bytecode=True
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def rows(p):return [json.loads(x) for x in p.read_text(encoding='utf-8-sig').splitlines() if x]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,d):
 assert not p.exists(),str(p)
 p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def status(st):
 p=B/'sol/STATUS.audit322.tmp';p.write_text(json.dumps(st,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(p,B/'sol/STATUS.json')
me=psutil.Process();me.cpu_affinity(list(range(24,32)));me.nice(psutil.IDLE_PRIORITY_CLASS)
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs');job=dict(pid=me.pid,created=me.create_time(),cpus=me.cpu_affinity(),priority=me.nice(),phase='read completed23 P ticks, source/cleanup and finite historical receive arithmetic')
put(A/'ROOT_P_AUDIT_JOB.json',job);st.update(at=now(),phase='TASK180_P_RECEIPT_AUDIT',own_offline_jobs=[job]);status(st)
err=None
try:
 from ssbot.train.measurement import validate_trace
 from ssbot.combat.knife_chain_deadline import FRAME_NS,PREVIOUS_STATE_WINDOW_NS,SEND_RESERVE_NS
 packet=read(A/'SOURCE_PACKET.json');assert all(sha(D/n)==h for n,h in packet['raw_runtime_files_sha256'].items())
 finals={n:read(A/n/'FINALIZED.json') for n in ['startup','p_N']};assert all(f['cleanup_verified'] and f['execution_ok'] for f in finals.values())
 assert finals['startup']['pid']!=finals['p_N']['pid']
 trial=B/'sol/demos/w13_observe_bait_20261106T055356Z';rx={}
 for r in rows(trial/'run/measurement_i0_e0.jsonl'):
  if r.get('kind')=='receive':rx.setdefault(r['f'],r['recv_ns'])
 rf=sorted(rx);rn=[rx[f] for f in rf];assert rn==sorted(rn)
 O=B/'analysis/task179_body321_20261106';stats={};serial_full={};total=0
 for name,folder,lo,hi,expected,keys,eng in [('N','p_N/N',2813,2835,23,[2813,2819,2822,2824,2830,2835],'p_NW/N')]:
  p=A/folder;r=read(p/'RESULT.json');m=read(p/'CONFIGURATION_MANIFEST.json');val=validate_trace(p/'measurement_trace.jsonl');tr=rows(p/'measurement_trace.jsonl');ticks={x['f']:x for x in tr if x.get('kind')=='tick'};actions={x['f']:x for x in tr if x.get('kind')=='action'};fs=sorted(ticks)
  assert fs==list(range(lo,hi+1)) and set(fs)==set(actions) and len(fs)==expected
  assert val['complete'] and r['exception'] is None and not r['foreign'] and not r['children_left']
  timing=r['p_entry']['timing'];rt=timing['runtime'];assert rt['cpu_affinity']==list(range(16)) and rt['priority']==128 and not rt['query_errors'] and rt['power_throttling']['execution_speed_throttled'] is False
  assert timing['send_clock_required'] and timing['signatures_before']==r['signatures_after']
  assert all(sha(D/'brain/ssbot'/n)==h for n,h in r['source_sha256'].items())
  assert m['unresolved']==['SSBOT_FORUM_CHAIN_BLOCK','SSBOT_FORUM_CHAIN_ORDER','SSBOT_FORUM_CHAIN_SCHEDULE']
  for flag in ['SSBOT_FORUM_TWO_RETURN_BODY','SSBOT_FORUM_TWO_RETURN_AIR']:
   assert m['switches'][flag]['resolution']=='runtime_binding'
   assert m['switches'][flag]['raw']==('0' if name=='D' else '1')
  cost={f:ticks[f]['tick_end_ns']-ticks[f]['tick_start_ns'] for f in fs};send={f:actions[f]['send_done_ns']-ticks[f]['tick_start_ns'] for f in fs}
  def schedule(wake):
   free=-float('inf');last=lo-1;out=[]
   while last<hi:
    pending=[f for f in fs if f>last];ready=[f for f in pending if rx[f]<=free];f=max(ready) if ready else pending[0]
    start=max(free,rx[f])+wake*1e6;sent=start+send[f];latest=rf[bisect.bisect_right(rn,sent)-1];applied=None
    for target in range(f+2,f+12):
     deadline=min(rx[target-2]+PREVIOUS_STATE_WINDOW_NS+FRAME_NS,rx[target-1]+PREVIOUS_STATE_WINDOW_NS)
     if latest<target and sent+SEND_RESERVE_NS<deadline:applied=target;break
    assert applied is not None
    out.append(dict(f=f,target=f+2,applied=applied,late=applied-f-2,mask=int(actions[f]['mask']),owner=ticks[f].get('owner'),lag_ms=(start-rx[f])/1e6,slack_ms=(deadline-sent-SEND_RESERVE_NS)/1e6,skipped=[g for g in pending if g<f]))
    free,last=start+cost[f],f
   return out
  ss={}
  for label,wake in [('historical_idle_p50',.270),('historical_idle_p99',1.292),('historical_idle_max',7.132)]:
   sr=schedule(wake);serial_full[name+':'+label]=sr;present={q['f']:q for q in sr}
   ss[label]=dict(wake_ms=wake,rows=len(sr),late=[q for q in sr if q['late']],skipped=[g for q in sr for g in q['skipped']],key_rows=[present.get(f,dict(f=f,skipped=True)) for f in keys],minimum_slack_ms=min(q['slack_ms'] for q in sr))
  def sent(p):return [(x['frame'],x.get('target'),x.get('mask'),x.get('owner')) for x in rows(p/'decisions_i0.chain.jsonl') if x.get('event')=='transport_sent' and lo<=x.get('frame',-1)<=hi]
  actual,prior=sent(p),sent(O/eng);diff=[dict(index=i,actual=x,engineering=prior[i] if i<len(prior) else None) for i,x in enumerate(actual) if i>=len(prior) or x!=prior[i]]
  vals=[cost[f]/1e6 for f in fs];critical=[dict(f=f,owner=ticks[f].get('owner'),mask=actions[f]['mask'],total_ms=cost[f]/1e6,send_ms=send[f]/1e6) for f in keys]
  footer=tr[-1];peakf=max(fs,key=lambda f:cost[f]);
  put(A/(name+'_FULL_DIAGNOSTICS.json'),dict(at=now(),peak_frame=peakf,peak_tick=ticks[peakf],peak_action=actions[peakf],footer=footer))
  stats[name]=dict(path=str(p),ticks=expected,p50_ms=float(np.percentile(vals,50)),p99_ms=float(np.percentile(vals,99)),peak_ms=max(vals),runtime=rt,field=timing['field_worker'],trace=val,signature_unchanged=True,source_unchanged=True,configuration_complete_raw=m['configuration_complete'],unresolved_raw=m['unresolved'],model_hits=r['model_hits'],model_hurts=r['model_hurts'],key_ticks=critical,serial=ss,engineering_send_count=len(prior),P_send_count=len(actual),engineering_send_differences=diff[:12],engineering_equal=actual==prior,diagnostic_event_count=len(footer.get('diagnostics',{}).get('events',[])))
  total+=expected
 assert total==23
 put(A/'SERIAL_SCHEDULE.json',dict(at=now(),source=packet['source'],scope='Measured complete costs + old actual receive stream, latest STATE and both deadline anchors, reserve unchanged; fixed historical wake calibrations only. No resimulation of policy after late/skipped keys, no future probability guarantee.',rows=serial_full))
 put(A/'ROOT_P_AUDIT.json',dict(at=now(),source=packet['source'],ticks=total,contexts=stats,actual_cleanup=finals,source_unchanged=True,integrity_pass=True,full_scheduling_gate_pass=False,new_game_gate=False,resource_interruption=None,scope='N23 finite affectedP on322; not whole-task performance/latency pass or live certificate. Old50/219 samples not repeated. All peaks and diagnostics preserved.'))
 print(json.dumps(dict(ticks=total,contexts={n:dict(ticks=v['ticks'],p50=v['p50_ms'],peak=v['peak_ms'],engineering_equal=v['engineering_equal'],serial_p99_late=len(v['serial']['historical_idle_p99']['late']),serial_p99_skipped=v['serial']['historical_idle_p99']['skipped'],serial_p99_keys=v['serial']['historical_idle_p99']['key_rows']) for n,v in stats.items()}),ensure_ascii=False))
except BaseException as exc:
 err=repr(exc);put(A/'ROOT_P_AUDIT_ERROR.json',dict(at=now(),error=err,traceback=traceback.format_exc()));raise
finally:
 put(A/'ROOT_P_AUDIT_JOB_END.json',dict(at=now(),job=job,error=err));# Keep own E job registered until the caller confirms actual exit.
 pass

