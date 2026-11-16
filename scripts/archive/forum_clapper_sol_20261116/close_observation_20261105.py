"""Read actual one-bout completion, independently verify cleanup, then release ownership."""
from pathlib import Path
import sys,json,hashlib,datetime,os,psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan')
A=B/'analysis/w13_observe_bait_20261106T055356Z'
T=B/'sol/demos/w13_observe_bait_20261106T055356Z'
D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
sys.dont_write_bytecode=True
sys.path.insert(0,str(D/'brain'))
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def put(p,d):
    assert not p.exists(),str(p)
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
me=psutil.Process();me.cpu_affinity(list(range(24,32)));me.nice(psutil.IDLE_PRIORITY_CLASS)
end=read(A/'COORDINATOR_END.json');cl=read(T/'launch/cleanup.json')
assert end['error'] is None and cl['failure'] is None and cl['worker_returncode']==0
assert cl['errors']==[] and cl['prefs_diff']==[] and cl['old_demo_restored']
wc=list((T/'run').glob('worker_cleanup_i0_*.json'));assert len(wc)==1
worker_cleanup=read(wc[0])
from ssbot.tools.launcher import PrefsGuard,current_prefs,read_reg_file,prefs_diff,running_game_pids
g=PrefsGuard.default();reg=g.status();games=running_game_pids()
diff=prefs_diff(current_prefs(g.store),read_reg_file(g.golden));golden=g.verify_golden()
assert reg.get('instances')==[] and reg.get('live')==[] and reg.get('restore_pending') is False
assert not games and diff==[]
assert golden=='fc41b9c5427b4e23ec60af1f16808a6b497507eded5704b90c9224b056ea0469'
demo=Path('C:/ssbot/sandbox/DEMO_SOON')
assert sha(demo)=='0455dd550525b4b11ed62eccb47cdfeb802a3ba0a8b0c08d30f8cc961c53cb81'
assert demo.stat().st_mtime_ns==1791523123325081300
known={24992:1793946938.689371,54148:1793946938.6972568,33340:1793946952.215643,25724:1793946963.014240,59336:1793946963.053346,50544:1793946983.456883}
identities=[]
for pid,created in known.items():
    try:
        q=psutil.Process(pid);actual=q.create_time()
        identities.append(dict(pid=pid,expected_created=created,current_created=actual,same_identity=abs(actual-created)<.02))
        assert abs(actual-created)>=.02,('own process remains',pid)
    except psutil.NoSuchProcess:identities.append(dict(pid=pid,expected_created=created,exists=False))
left=[]
for q in psutil.process_iter(['name','cmdline']):
    if q.pid==me.pid:continue
    if not (q.info['name'] or '').lower().startswith(('python','hollow knight')):continue
    try:
        command=' '.join(q.info['cmdline'] or [])
        if str(A).lower() in command.lower() or str(T).lower() in command.lower() or 'multiprocessing.spawn' in command:
            left.append(dict(pid=q.pid,created=q.create_time(),command=command))
    except psutil.NoSuchProcess:pass
assert not left,('unresolved helpers',left)
c=read(T/'contract.json');changed=[n for n,h in c['files'].items() if sha(D/n)!=h]
assert not changed,changed
r=dict(at=now(),cleanup_verified=True,worker_cleanup=worker_cleanup,coordinator=end,own_processes=identities,residual_helpers=left,games=games,registry=reg,golden_sha256=golden,prefs_diff=diff,old_demo_sha256=sha(demo),old_demo_mtime_ns=demo.stat().st_mtime_ns,source=c['source'],runtime_files_unchanged=len(c['files']))
put(A/'ROOT_CLEANUP.json',r)
st=read(B/'sol/STATUS.json');assert st['live_or_budget_running'] and st['own_live_session']['pid']==54148
st.update(at=now(),phase='ONE_OBSERVATION_ENDED_ANALYSIS_PENDING',live_or_budget_running=False,own_live_session=None,last_game_source=c['source'],last_game_cleanup=str(A/'ROOT_CLEANUP.json'),live_cleanup_verified_at=r['at'],next_watch_user_authorized=False,next_watch_ready=False)
st['observation_one_bout'].update(completed=True,no_auto_next_bout=True,cleanup=str(A/'ROOT_CLEANUP.json'))
tmp=B/'sol/STATUS.observation_cleanup.tmp';tmp.write_text(json.dumps(st,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(tmp,B/'sol/STATUS.json')
a=json.loads((T/'run/attempts_i0.jsonl').read_text(encoding='utf-8').splitlines()[0])
out={k:v for k,v in a.items() if k not in ('measurement','trace','decisions','config','effective_config','diagnostics')}
for k,v in list(out.items()):
    if isinstance(v,(dict,list)) and len(json.dumps(v))>5000:out[k]=dict(type=type(v).__name__,keys=list(v)[:40] if isinstance(v,dict) else len(v))
put(A/'ROOT_ATTEMPT_SUMMARY.json',out)
print(json.dumps(dict(cleanup_verified=True,source_unchanged=len(c['files']),worker_cleanup=worker_cleanup,attempt_keys=list(a),summary=out),ensure_ascii=False))
