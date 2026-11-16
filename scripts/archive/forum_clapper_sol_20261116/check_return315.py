"""Run only #315's new support/lock-boundary checks in the owned offline lane."""
from pathlib import Path
import sys,json,datetime,os,hashlib,psutil,traceback
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/task179_return315_20261106';D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');S='dfab63a43923635337a79f565a917e64f4b2a55d'
sys.path.insert(0,str(D/'brain'));sys.dont_write_bytecode=True
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,d):
    assert not p.exists(),str(p)
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def status(s):
    p=B/'sol/STATUS.return315.tmp';p.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(p,B/'sol/STATUS.json')
me=psutil.Process();me.cpu_affinity(list(range(24,32)));me.nice(psutil.IDLE_PRIORITY_CLASS)
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs');A.mkdir(exist_ok=False)
job=dict(pid=me.pid,created=me.create_time(),phase='new return-body support/lock checks only',affinity=me.cpu_affinity(),priority=me.nice(),at=now())
put(A/'ROOT_JOB.json',job);st.update(at=now(),phase='RETURN315_INCREMENTAL_CHECK',candidate_source=S,source_review_pending=True,own_offline_jobs=[job]);status(st)
rc=None;error=None
try:
    base=read(B/'analysis/task179_return314_20261106/SOURCE_PACKET.json')['raw_runtime_files_sha256'];current={n:sha(D/n) for n in base};changed=[n for n,h in base.items() if current[n]!=h]
    assert len(changed)==5,changed
    put(A/'SOURCE_PACKET.json',dict(source=S,base='e137055c14294f1580bc69ad680decd786c90388',runtime_files=len(current),changed=changed,raw_runtime_files_sha256=current,new_test_sha256=sha(D/'brain/tests/test_return_body315.py')))
    os.environ.update(PYTHONDONTWRITEBYTECODE='1',NUMBA_CACHE_DIR=str(B/'analysis/critical214_20261103/p_prepared_ce81b62c/numba_cache'))
    import pytest
    rc=int(pytest.main([str(D/'brain/tests/test_return_body315.py'),'-q','-p','no:cacheprovider','--basetemp='+str(A/'pytest_tmp'),'--junitxml='+str(A/'CHECKS.xml')]))
    foreign=[]
    for name,mod in list(sys.modules.items()):
        p=getattr(mod,'__file__',None)
        if p and (name=='ssbot' or name.startswith('ssbot.')) and str(D/'brain').replace('\\','/').lower() not in p.replace('\\','/').lower():foreign.append(p)
    unchanged=all(sha(D/n)==h for n,h in current.items())
    put(A/'CHECK_RECEIPT.json',dict(at=now(),source=S,pytest_rc=rc,foreign_modules=foreign,source_unchanged=unchanged,job=job,scope='new component checks only, not ground/air complete-path or formal timing/live acceptance'))
    assert rc==0 and not foreign and unchanged
except BaseException as exc:
    error=repr(exc);put(A/'ROOT_ERROR.json',dict(at=now(),error=error,traceback=traceback.format_exc()));raise
finally:
    put(A/'ROOT_JOB_END.json',dict(at=now(),job=job,error=error,pytest_rc=rc,formal_P_ticks=0,games_started=0))
    st=read(B/'sol/STATUS.json');st.update(at=now(),phase='RETURN315_REVIEW_PENDING',own_offline_jobs=[]);status(st)
