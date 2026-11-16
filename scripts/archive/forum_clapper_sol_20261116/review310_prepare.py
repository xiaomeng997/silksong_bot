from pathlib import Path
import os,sys,json,hashlib,subprocess,datetime
import psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
R=B/'analysis/task179_observe310_20261105';G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
S='689b8bc29e67cbcc24a8063418ec50244d0dd44b'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def put(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*a):return subprocess.check_output([G,'-C',str(D),*a],text=True,encoding='utf-8').strip()
def update(**kw):
 p=B/'sol/STATUS.json';s=read(p);s.update(kw);q=p.with_name('STATUS.review310.tmp');put(q,s);os.replace(q,p)
R.mkdir(exist_ok=True)
assert git('rev-parse','HEAD')==S
assert not git('diff','HEAD','--','brain/ssbot','knowledge')
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs')
old=read(B/'analysis/task179_5df8711e_20261105/SOURCE_PACKET.json')['raw_runtime_files_sha256']
added=git('diff','--diff-filter=A','--name-only','5df8711e',S,'--','brain/ssbot','knowledge').splitlines()
files={n:sha(D/n) for n in sorted(set(old)|set(added))}
models=[n for n in old if n.startswith('knowledge/')]
assert all(files[n]==old[n] for n in models),'model changed'
put(R/'SOURCE_PACKET.json',dict(at=now(),source=S,source_root=str(D),raw_runtime_files_sha256=files,
 changed_vs5df=[n for n,h in files.items() if old.get(n)!=h],model_files_unchanged=len(models),
 scope='only one explicit observation; FACE_HOOK0 BOUNCE_TABLE0; no full309 feature acceptance'))
p=psutil.Process();p.cpu_affinity(list(range(24,32)));p.nice(psutil.IDLE_PRIORITY_CLASS)
job=dict(pid=p.pid,created=p.create_time(),phase='310 targeted E checks',directory=str(R),cpus=p.cpu_affinity())
put(R/'ROOT_CHECK_JOB.json',job);update(phase='TASK179_OBSERVE310_TARGETED_CHECKS',current_source=S,source_review_pending=True,own_offline_jobs=[job],last_opus_scan_number=310)
os.environ.update(PYTHONDONTWRITEBYTECODE='1',NUMBA_NUM_THREADS='4',NUMBA_CACHE_DIR=str(R/'numba_cache'),
 SSBOT_FORUM_REMAINING_HP_QUIT='0',SSBOT_FORUM_CHAIN_FACE_HOOK='0',SSBOT_FORUM_CHAIN_BOUNCE_TABLE='0')
sys.path.insert(0,str(D/'brain'));sys.dont_write_bytecode=True
rc=99
try:
 import pytest
 with (R/'CHECKS.out').open('w',encoding='utf-8',buffering=1) as log:
  saved=sys.stdout,sys.stderr;sys.stdout=sys.stderr=log
  try:rc=pytest.main(['-q','-p','no:cacheprovider','--basetemp='+str(R/'pytest_tmp'),'--junitxml='+str(R/'CHECKS.xml'),
    str(D/'brain/tests/test_observe_bout310.py'),str(D/'brain/tests/test_clapper_priority.py')])
  finally:sys.stdout,sys.stderr=saved
 foreign=[str(m.__file__) for n,m in list(sys.modules.items()) if (n=='ssbot' or n.startswith('ssbot.')) and getattr(m,'__file__',None) and not Path(m.__file__).resolve().is_relative_to(D)]
 assert not foreign,foreign
 assert all(sha(D/n)==h for n,h in files.items()),'source drift during check'
 put(R/'CHECK_RECEIPT.json',dict(at=now(),source=S,returncode=rc,foreign=foreign,source_unchanged=True,job=job))
finally:update(phase='TASK179_OBSERVE310_REVIEW',own_offline_jobs=[])
print(json.dumps(dict(source=S,files=len(files),model_files_unchanged=len(models),returncode=rc,dir=str(R))))
raise SystemExit(int(rc))
