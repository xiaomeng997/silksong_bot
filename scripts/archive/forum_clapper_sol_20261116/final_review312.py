from pathlib import Path
import json,hashlib,os,sys,subprocess,datetime,runpy,psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');R=B/'analysis/task179_observe312_20261105';P=B/'analysis/task179_observe311_20261105'
G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe';S='b4615f2528edf339d0a8b9e61de21681d5910289'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def put(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*a):return subprocess.check_output([G,'-C',str(D),*a],text=True,encoding='utf-8').strip()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def status(**v):
 p=B/'sol/STATUS.json';s=read(p);s.update(v);q=p.with_name('STATUS.meta312.tmp');put(q,s);os.replace(q,p)
R.mkdir(exist_ok=True)
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs')
assert git('rev-parse','HEAD')==S and not git('diff','HEAD','--','brain/ssbot','knowledge')
old=read(P/'SOURCE_PACKET.json');files={n:sha(D/n) for n in old['raw_runtime_files_sha256']}
delta=[n for n,h in files.items() if h!=old['raw_runtime_files_sha256'][n]]
assert delta==['brain/ssbot/train/forum_measure_manifest.py'],delta
put(R/'SOURCE_PACKET.json',dict(at=now(),source=S,source_root=str(D),raw_runtime_files_sha256=files,changed_vs_P_source=delta,scope='one explicit observation; only metadata changed since measured05b8'))
base=B/'opus/review179/l1_308/manifest311.py';src=base.read_text(encoding='utf-8')
src=src.replace('list(range(16, 24))','list(range(24, 32))').replace('E16-23','E24-31')
line='os.environ["NUMBA_CACHE_DIR"] = str(Path(__file__).resolve().parents[1] / "review178" / "diag_live" / "numba_cache")'
assert src.count(line)==1;src=src.replace(line,'os.environ["NUMBA_CACHE_DIR"] = '+repr(str(B/'analysis/critical214_20261103/p_prepared_ce81b62c/numba_cache')))
src=src.replace('os.environ.update(env)','env.update(SSBOT_WORKER_BOOST="0", SSBOT_WORKER_CPUS="24-31")\nos.environ.update(env)')
entry=R/'manifest_positive.py';entry.write_text(src,encoding='utf-8')
p=psutil.Process();p.cpu_affinity(list(range(24,32)));p.nice(psutil.IDLE_PRIORITY_CLASS)
job=dict(pid=p.pid,created=p.create_time(),phase='metadata-only actual policy positive',directory=str(R));put(R/'ROOT_METADATA_JOB.json',job);status(own_offline_jobs=[job],phase='OBSERVE312_METADATA_POSITIVE',last_opus_scan_number=312)
try:
 sys.argv=[str(entry),str(R/'positive'),'1'];os.environ['NUMBA_NUM_THREADS']='4';sys.dont_write_bytecode=True
 runpy.run_path(str(entry),run_name='__main__')
 m=read(R/'positive/SUMMARY.json');assert m['configuration_complete'] and m['unresolved']==[] and m['unknown']==[]
 assert m['observe_only']==['Q1','Q3','Q4','Q6'] and m['budget_policy']=='observe-one-bout-v1' and m['bounce_mode'] is False
 assert all(sha(D/n)==h for n,h in files.items()),'source drift'
 foreign=[str(x.__file__) for n,x in list(sys.modules.items()) if n.startswith('ssbot.') and getattr(x,'__file__',None) and not Path(x.__file__).resolve().is_relative_to(D)]
 assert not foreign,foreign
 put(R/'METADATA_POSITIVE_RECEIPT.json',dict(at=now(),source=S,configuration_complete=True,unresolved=[],unknown=[],actual_policy_summary=str(R/'positive/SUMMARY.json'),foreign=[],actual_objects=['ForumPlannerPolicy','prepared/bound LearningBudget','reset supervisor config','native runner'],scope='new bindings under live control knobs; scene field disabled only for this pure configuration check; actual live worker manifest still required'))
finally:status(own_offline_jobs=[])
env={'SSBOT_FORUM_OBSERVE_BOUT':'1','SSBOT_FORUM_REMAINING_HP_QUIT':'0','SSBOT_FORUM_CHAIN_FACE_HOOK':'0','SSBOT_FORUM_CHAIN_BOUNCE_TABLE':'0'}
put(R/'SOURCE_REVIEW.json',dict(at=now(),source=S,accepted=True,scope='ONE watched observation only; specified environment mandatory',required_environment=env,metadata_positive_receipt=str(R/'METADATA_POSITIVE_RECEIPT.json'),processed_opus_numbers=[308,309,310,311,312],review_applicability={'308':'facehook checks inactive FACE_HOOK0; full feature not accepted','309':'new bounce table/vault work unaccepted and disabled; shared adapters reviewed','310':'tactic + observation source reviewed; 82 retained','311':'supervisor and actual guard startup reviewed; 18 passed and85P cleaned','312':'only16 metadata binding lines, actual-policy configuration complete positive; no repeatP'},p_reuse={'source':old['source'],'audit':str(P/'ROOT_P_AUDIT.json'),'actual_ticks':85,'max_ms':18.7066,'p50_ms':12.6473,'all_other_runtime_files_bitwise_identical':True,'changed_file':delta[0],'why_no_repeat':'only read-only configuration serialization bindings; no action/simulator/input/timing code changed'},limits=['observation only, no mortality/no-hit claim','old P configuration had missing metadata, retained raw; actual current-worker manifest must be complete','conditional NPC replay not natural closed loop','wall cap and target retreat can prevent intended displacement/hit','85point costs do not guarantee future timing']))
status(current_source=S,source_review_pending=False,source_review_file=str(R/'SOURCE_REVIEW.json'),phase='OBSERVE312_READY_BIND',pending_opus=None)
print(json.dumps(dict(reviewed=True,source=S,dir=str(R),metadata_complete=True,repeat_P=False)))
