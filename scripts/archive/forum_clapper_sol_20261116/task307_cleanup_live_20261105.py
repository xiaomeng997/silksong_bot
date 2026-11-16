from pathlib import Path
import sys,json,hashlib,os,datetime as dt
import psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan')
TAG='w13_guard179L3_20261106T012400Z_5df8711e'
A=B/'analysis'/TAG;T=B/'sol/demos'/TAG
W=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
sys.dont_write_bytecode=True;sys.path.insert(0,str(W/'brain'))
from ssbot.tools.launcher import PrefsGuard,current_prefs,read_reg_file,prefs_diff,running_game_pids
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):
 with p.open('x',encoding='utf-8') as f:json.dump(d,f,ensure_ascii=False,indent=2);f.write('\n')
s=read(B/'sol/STATUS.json');assert s['live_or_budget_running']
assert read(A/'COORDINATOR_END.json')['error'] is None
c=read(T/'launch/cleanup.json');assert not c['errors'] and c['worker_returncode']==0
workers=list((T/'run').glob('worker_cleanup_*.json'));assert len(workers)==1
assert read(workers[0])['complete']
manifest=read(T/'run/measurement_manifest_i0_e0.json')
ids=[read(A/'WMI_START.json')['pid'],s['own_live_session']['pid'],manifest['runtime_before']['pid']]+[x['pid'] for x in c['own']]
alive=[x for x in ids if psutil.pid_exists(x)]
me=psutil.Process();ignore={me.pid,*[p.pid for p in me.parents()]}
own=[];pythonw=[]
for p in psutil.process_iter(['pid','name','cmdline','create_time']):
 try:
  i=p.info
  if i['pid'] in ignore:continue
  if TAG.lower() in ' '.join(i['cmdline'] or []).lower():own.append(i)
  if (i['name'] or '').lower()=='pythonw.exe':pythonw.append(i)
 except (psutil.NoSuchProcess,psutil.AccessDenied):continue
guard=PrefsGuard.default();reg=guard.status();gold=guard.verify_golden()
games=running_game_pids()
diff=prefs_diff(current_prefs(guard.store),read_reg_file(guard.golden))
demo=Path('C:/ssbot/sandbox/DEMO_SOON')
report={'at':dt.datetime.now(dt.timezone.utc).isoformat(),'actual_cleanup':not any([alive,own,pythonw,games,diff,reg.get('instances'),reg.get('live'),reg.get('restore_pending')]),'owned_pids':ids,'owned_pids_alive':alive,'own_command_residue':own,'all_pythonw_residue':pythonw,'games':games,'registry':reg,'golden_sha256':gold,'prefs_diff':diff,'old_demo_sha256':sha(demo),'old_demo_mtime_ns':demo.stat().st_mtime_ns,'launcher':c,'worker_cleanup':read(workers[0]),'field_pid':'unknown; all pythonw absent and worker close pass required','probe_ancestor_only_excluded':sorted(ignore)}
assert gold=='fc41b9c5427b4e23ec60af1f16808a6b497507eded5704b90c9224b056ea0469'
assert report['old_demo_sha256']=='0455dd550525b4b11ed62eccb47cdfeb802a3ba0a8b0c08d30f8cc961c53cb81'
assert report['old_demo_mtime_ns']==1791523123325081300
write(A/'ROOT_CLEANUP.json',report);assert report['actual_cleanup'],report
write(A/'NO_RETRY.json',{'at':report['at'],'trial':str(T),'source':s['current_source'],'closed':True,'reopen_same_trial':False,'scope':'single engineering bout ended; audit required, no repeat permission'})
s.update(at=report['at'],phase='WALK179_L3_ENDED_AUDIT',live_or_budget_running=False,own_live_session=None,cleanup_verified_at=report['at'],last_game_cleanup=str(A/'ROOT_CLEANUP.json'))
tmp=B/'sol/STATUS.cleanup307.tmp';tmp.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(tmp,B/'sol/STATUS.json')
print(json.dumps({k:report[k] for k in ('actual_cleanup','owned_pids','games','registry','golden_sha256','prefs_diff','old_demo_sha256')},ensure_ascii=False))
