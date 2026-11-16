"""Only nine new #317 component checks plus raw Idle clock binding census; no P/game."""
from pathlib import Path
import datetime,hashlib,json,os,sys,traceback
import psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/task179_return317_20261106'
D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');S='c00074ccdd589c0e3c37ba4302234e689a858121'
sys.path.insert(0,str(D/'brain'));sys.dont_write_bytecode=True
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,d):
 assert not p.exists(),str(p)
 p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def status(st):
 p=B/'sol/STATUS.return317.tmp';p.write_text(json.dumps(st,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(p,B/'sol/STATUS.json')
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs');A.mkdir(exist_ok=False)
me=psutil.Process();me.cpu_affinity(list(range(24,32)));me.nice(psutil.IDLE_PRIORITY_CLASS)
job=dict(pid=me.pid,created=me.create_time(),affinity=me.cpu_affinity(),priority=me.nice(),at=now(),phase='nine new component checks and read-only Idle-clock event binding')
put(A/'ROOT_JOB.json',job);st.update(at=now(),phase='RETURN317_INCREMENTAL_CHECK',candidate_source=S,source_review_pending=True,own_offline_jobs=[job]);status(st)
rc=None;error=None
try:
 base=read(B/'analysis/task179_return316_20261106/SOURCE_PACKET.json')['raw_runtime_files_sha256'];cur={n:sha(D/n) for n in base};changed=[n for n,h in base.items() if h!=cur[n]];assert len(changed)==3,changed
 put(A/'SOURCE_PACKET.json',dict(source=S,base='ac0d87f343778fa6e97fce54b0b55c9a778d8a34',raw_runtime_files_sha256=cur,runtime_files=len(cur),changed=changed,test_sha256=sha(D/'brain/tests/test_strike_evidence317.py')))
 os.environ.update(PYTHONDONTWRITEBYTECODE='1',NUMBA_CACHE_DIR=str(B/'analysis/critical214_20261103/p_prepared_ce81b62c/numba_cache'))
 import pytest
 rc=int(pytest.main([str(D/'brain/tests/test_strike_evidence317.py'),'-q','-p','no:cacheprovider','--basetemp='+str(A/'pytest_tmp'),'--junitxml='+str(A/'CHECKS.xml')]))
 assert rc==0
 from ssbot.record.recorder import RecordingReader
 T=B/'sol/demos/w13_observe_bait_20261106T055356Z';att=json.loads((T/'run/attempts_i0.jsonl').read_text().splitlines()[0]);records=[]
 prev={}
 for x in RecordingReader(att['recording']).states(2428,4856):
  for e in x.get('ents') or []:
   if e.get('type_key')!='Song Heavy Sentry':continue
   c=next((c for c in e.get('fsms',[]) if c.get('name')=='Control'),{})
   iid=e['iid'];before=prev.get(iid);tin=c.get('t');f=x['f']
   if c.get('state')=='Idle' and (before is None or before['state']!='Idle' or (type(tin) in (int,float) and type(before['t']) in (int,float) and tin<before['t']-1e-6)):
    records.append(dict(first_observed_f=f,fc=x.get('fc'),fs=x.get('fs'),iid=iid,t= tin,inferred_update_entry=None if type(tin) not in (int,float) else f-round(tin*60),previous_observation=before,control_events=[ev for ev in x.get('ev') or [] if ev.get('k') in ('fsm','hit') and (ev.get('d') or {}).get('ent')==iid]))
   prev[iid]=dict(f=f,state=c.get('state'),t=tin)
 put(A/'RAW_IDLE_ENTRY_CENSUS.json',dict(at=now(),recording=att['recording'],scope='raw observed Idle transitions only; inferred f-round(t*60) is not assumed to be the true entry',entries=records))
 foreign=[getattr(m,'__file__',None) for n,m in list(sys.modules.items()) if (n=='ssbot' or n.startswith('ssbot.')) and getattr(m,'__file__',None) and str(D/'brain').replace('\\','/').lower() not in m.__file__.replace('\\','/').lower()]
 unchanged=all(sha(D/n)==h for n,h in cur.items())
 put(A/'CHECK_RECEIPT.json',dict(at=now(),source=S,pytest_rc=rc,foreign_modules=foreign,source_unchanged=unchanged,checks=9,job=job,scope='new component checks and raw-clock evidence only; no formal timing or live acceptance'))
 assert not foreign and unchanged
except BaseException as exc:
 error=repr(exc);put(A/'ROOT_ERROR.json',dict(at=now(),error=error,traceback=traceback.format_exc()));raise
finally:
 put(A/'ROOT_JOB_END.json',dict(at=now(),job=job,error=error,pytest_rc=rc,formal_P_ticks=0,games_started=0))
 st=read(B/'sol/STATUS.json');st.update(at=now(),phase='RETURN317_REVIEW_PENDING',own_offline_jobs=[]);status(st)
