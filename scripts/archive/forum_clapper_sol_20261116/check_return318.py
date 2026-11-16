"""Finite #318 checks and artifact binding; no P or game."""
from pathlib import Path
import datetime,hashlib,json,os,sys,psutil,traceback
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/task179_return318_20261106';D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');S='0b1481774f04838a610e5d31a70acbfcdef623df'
sys.path.insert(0,str(D/'brain'));sys.dont_write_bytecode=True
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,d):
 assert not p.exists(),str(p)
 p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def status(s):
 p=B/'sol/STATUS.return318.tmp';p.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(p,B/'sol/STATUS.json')
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs');A.mkdir(exist_ok=False)
me=psutil.Process();me.cpu_affinity(list(range(24,32)));me.nice(psutil.IDLE_PRIORITY_CLASS);job=dict(pid=me.pid,created=me.create_time(),cpus=me.cpu_affinity(),priority=me.nice(),phase='11 changed Idle-entry component checks and existing artifact equality')
put(A/'ROOT_JOB.json',job);st.update(at=now(),phase='RETURN318_INCREMENTAL_CHECK',candidate_source=S,own_offline_jobs=[job]);status(st)
rc=None;err=None
try:
 old=read(B/'analysis/task179_return317_20261106/SOURCE_PACKET.json')['raw_runtime_files_sha256'];cur={n:sha(D/n) for n in old};changed=[n for n in cur if cur[n]!=old[n]];assert changed==['brain/ssbot/combat/knife_chain_air_native.py'],changed
 put(A/'SOURCE_PACKET.json',dict(source=S,base='c00074ccdd589c0e3c37ba4302234e689a858121',runtime_files=len(cur),changed=changed,raw_runtime_files_sha256=cur,test_sha256=sha(D/'brain/tests/test_strike_evidence317.py')))
 os.environ.update(PYTHONDONTWRITEBYTECODE='1',NUMBA_CACHE_DIR=str(B/'analysis/critical214_20261103/p_prepared_ce81b62c/numba_cache'))
 import pytest
 rc=int(pytest.main([str(D/'brain/tests/test_strike_evidence317.py'),'-q','-p','no:cacheprovider','--basetemp='+str(A/'pytest_tmp'),'--junitxml='+str(A/'CHECKS.xml')]))
 foreign=[getattr(m,'__file__',None) for n,m in list(sys.modules.items()) if n.startswith('ssbot') and getattr(m,'__file__',None) and not Path(m.__file__).resolve().is_relative_to(D)]
 unchanged=all(sha(D/n)==h for n,h in cur.items());assert rc==0 and not foreign and unchanged
 O=B/'opus/review179/l1_317';results=[]
 def sends(p):
  return [(r.get('frame'),r.get('target'),r.get('mask'),r.get('owner')) for line in (p/'decisions_i0.chain.jsonl').open() if (r:=json.loads(line)).get('event')=='transport_sent']
 for left,right in [('a4air8','a4air9'),('n1air8','n1air9'),('n1off7','n1off9'),('a2air7','a2air9'),('w3air7','w3air9')]:
  x,y=sends(O/left),sends(O/right);assert x==y,(left,right)
  r=read(O/right/'RESULT.json');assert r['exception'] is None and not r['foreign']
  assert all(sha(D/'brain/ssbot'/n)==h for n,h in r['source_sha256'].items()),right
  results.append(dict(before=left,after=right,transport_count=len(x),same=True,head=r['knife_head'],dirty=r['knife_brain_dirty'],model_hits=r['model_hits'],hurt_count=len(r['model_hurts'])))
 put(A/'ROOT_ARTIFACT_RECEIPT.json',dict(at=now(),source=S,comparisons=results,scope='Same explicit recorded-reaction scenarios as317; no natural NPC response or repeated-downslash proof'))
 put(A/'CHECK_RECEIPT.json',dict(at=now(),source=S,pytest_rc=rc,checks=11,foreign_modules=foreign,source_unchanged=unchanged,job=job,scope='incremental source/P2 closure only; not formal P/live acceptance'))
except BaseException as exc:
 err=repr(exc);put(A/'ROOT_ERROR.json',dict(at=now(),error=err,traceback=traceback.format_exc()));raise
finally:
 put(A/'ROOT_JOB_END.json',dict(at=now(),job=job,error=err,pytest_rc=rc,formal_P_ticks=0,games_started=0));st=read(B/'sol/STATUS.json');st.update(at=now(),phase='RETURN318_REVIEW_PENDING',own_offline_jobs=[]);status(st)
