from pathlib import Path
import os,sys,json,datetime as dt,hashlib,time
import psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');W=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');R=B/'analysis/task179_fd68690b_20261105'
R.mkdir(exist_ok=True)
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def atomic(p,d):
 t=p.with_suffix('.sol308.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(t,p)
me=psutil.Process();me.cpu_affinity(list(range(24,32)));me.nice(psutil.IDLE_PRIORITY_CLASS)
status=read(B/'sol/STATUS.json');assert not status['live_or_budget_running'] and not status.get('own_offline_jobs')
job={'pid':me.pid,'create_time':me.create_time(),'phase':'Sol independent 17 direct308 checks E24-31Idle; not P','source':'fd68690beb30757e25ddf2d96f7203561cb770f7'}
status.update(at=dt.datetime.now(dt.timezone.utc).isoformat(),phase='TASK179_308_INDEPENDENT_E_CHECKS',own_offline_jobs=[job],source_review_pending=True)
atomic(B/'sol/STATUS.json',status);atomic(R/'ROOT_CHECK_JOB.json',job)
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1';os.environ['NUMBA_CACHE_DIR']=str(R/'numba_cache');os.environ['NUMBA_NUM_THREADS']='4'
sys.dont_write_bytecode=True;sys.path.insert(0,str(W/'brain'));os.chdir(W/'brain')
base=read(B/'analysis/task179_5df8711e_20261105/SOURCE_PACKET.json')['raw_runtime_files_sha256'];before={n:hashlib.sha256((W/n).read_bytes()).hexdigest() for n in base}
rc=99;error=None;t0=time.monotonic()
try:
 import pytest
 with (R/'CHECKS.out').open('x',encoding='utf-8',buffering=1) as log:
  sys.stdout=sys.stderr=log
  rc=pytest.main(['-q','-p','no:cacheprovider','-o','addopts=','--junitxml='+str(R/'CHECKS.xml'),'tests/test_hook_entry_bounce308.py'])
except BaseException as exc:error=repr(exc)
finally:
 sys.stdout=sys.__stdout__;sys.stderr=sys.__stderr__
 foreign={n:getattr(m,'__file__','') for n,m in sys.modules.items() if n.startswith('ssbot') and getattr(m,'__file__',None) and not Path(m.__file__).resolve().is_relative_to((W/'brain').resolve())}
 unchanged=before=={n:hashlib.sha256((W/n).read_bytes()).hexdigest() for n in base}
 job.update(at=dt.datetime.now(dt.timezone.utc).isoformat(),exit_code=int(rc),error=error,foreign=foreign,source_files_unchanged=unchanged,elapsed_s=time.monotonic()-t0,scope='17 new direct component cases; stub geometry not production positive, no P/game')
 atomic(R/'ROOT_CHECK_JOB.json',job)
 status=read(B/'sol/STATUS.json');status['own_offline_jobs']=[x for x in status.get('own_offline_jobs',[]) if x.get('pid')!=me.pid or x.get('create_time')!=me.create_time()]
 status.update(at=job['at'],phase='TASK179_308_SOURCE_REVIEW');atomic(B/'sol/STATUS.json',status)
 print(json.dumps(job,ensure_ascii=False))
assert rc==0 and not foreign and unchanged and error is None
