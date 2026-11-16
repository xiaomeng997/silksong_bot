from pathlib import Path
import datetime as dt,hashlib,importlib.util,json,subprocess,sys
import psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');R=B/'analysis/task179_5df8711e_20261105';O=B/'opus/review179/l1_307';W=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
me=psutil.Process();me.cpu_affinity(list(range(24,32)));me.nice(psutil.IDLE_PRIORITY_CLASS);sys.dont_write_bytecode=True;sys.path.insert(0,str(W/'brain'))
from ssbot.safety.key_guard import Filter
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
sp=importlib.util.spec_from_file_location('review307_hf_cs',O/'hf_cs.py');mod=importlib.util.module_from_spec(sp);sp.loader.exec_module(mod)
dll=Path('C:/ssbot/game/train/BepInEx/plugins/SsOracle/SsOracle.dll');exe=O/'dllcheck/bin/Release/net472/DllCheck.exe';copy=exe.with_name('SsOracle.dll')
assert sha(dll)==sha(copy)=='ca7673dbeb8f3a061deca742aa0972f585c5284dd5328e8d2378d064509930ac'
check=read(O/'CHECK307.json');assert check['port_equals_jit_on_time'] and all(d['port_equals_dll'] for d in check['cases'].values())
cases={}
for name in check['cases']:
 p=O/('sched_'+name+'.txt');lines=p.read_text(encoding='utf-8-sig').splitlines();initial=list(map(int,lines[0].split()[1:]))
 assert len(initial)==66
 h=mod.HoldFilterCS();h.restore(initial[0],initial[1],initial[2:34],initial[34:66])
 ref=Filter.from_hf({'desired':initial[0],'latched':initial[1],'pending':initial[2:34],'age':initial[34:66]})
 port=[];reference=[];frames=[]
 for l in lines[1:]:
  v=list(map(int,l.split()));f,n=v[:2];frames.append(f)
  for i in range(n):
   previous,want=v[2+2*i:4+2*i]
   h.queue_plain(previous,want);ref.push(previous);ref.push(want)
  req=v[2+2*n];port.append(h.step(req));reference.append(ref.step(req))
 assert port==reference
 proc=subprocess.run([str(exe),str(p)],capture_output=True,text=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
 assert proc.returncode==0,proc.stderr
 actual=[int(l.split()[1]) for l in proc.stdout.splitlines()[1:]];assert actual==port
 cases[name]={'frames':len(frames),'root_port_equals_existing_Filter':True,'root_port_equals_actual_DLL':True,'dash_at':{str(f):bool(m&4) for f,m in zip(frames,actual) if 2766<=f<=2771}}
artifacts={}
for name,delay in [('l2_2767_d1',1),('l2_2767_d2',2)]:
 d=read(O/name/'RESULT.json');assert d['exception'] is None and d['foreign']==[] and not d['forced_planner_ticks']
 assert d['knife_brain_dirty']=='' and d['divergence_tick']==2761 and d['synthetic_from']==2763
 assert all(sha(W/'brain/ssbot'/n)==h for n,h in d['source_sha256'].items())
 rows={r['f']:r for r in d['rows']};fs=[2767+delay,2768+delay]
 assert all('DASH' in rows[f]['latched'] and 'J' in rows[f]['latched'] for f in fs)
 assert d['first_model_hurt']['f']==2800
 artifacts[name]={'source_hashes_match':True,'latched_J_DASH_frames':fs,'model_GLIDE':all(rows[f]['mode']=='GLIDE' for f in fs),'model_hurt_kept':d['first_model_hurt'],'actual_priority_certified':False}
receipt={'at':dt.datetime.now(dt.timezone.utc).isoformat(),'delivery':307,'source':'5df8711ea04accff8c03e87560d31b53b2e87a09','accepted':True,
 'scope':'corrected offline ordered-due-batch component and finite model effects; not actual J/DASH precedence or injury-free certification',
 'source_changed':False,'DLL_sha256':sha(dll),'component_cases':cases,'closed_loop_artifacts':artifacts,
 'on_time_whole_policy_replay_rerun':False,'on_time_basis':'same single-packet transitions checked versus JIT and DLL, unchanged main/act/physics; complete replay identity is inferred, not separately measured',
 'retained_ordinary_risk':'2763 L late1 conditional model hits old335476 body2795; no new-safe-route claim',
 'adopted_serial_scope':'full135 measured costs + original receive timestamps, latestSTATE and reserve; key escape edges timely at measured idle_p99 scenario; stress-only risks retained, no future GIL/lag guarantee',
 'disposition':'Following focused Astra306: permit constructing one separate known-risk firstloss-stopped engineering gate; do not alter globalinput or redo135P; actual new gate still must be prepared and checked',
 'experimental_acceptance':{'main':'early refusal/real handback and actual retreat/input-action correspondence','walking_vault':'separate opportunity and actual crossing/handback, zero remains uncovered','moving_stomp':'separate','new_same_iid_slam':'separate','task178':'previous finite acceptance retained'},
 'preserved':'original306/rejected dashloss and ROOT_P_AUDIT complete_scheduling=false unchanged',
 'priority_source_note':'cached game HeroController.LookForQueueInput handles Jump then separate Dash check; StartFloat emits FSM event; this alone does not certify actual precedence',
 'no_new_stop_rule':True,'original_strict_stops_unchanged':True,'new_game_gate':False,
 'inputs_sha256':{str(p):sha(p) for p in [O/'CHECK307.json',O/'hf_cs.py',O/'make_replay_late307.py',O/'replay_late307.py',R/'ASTRA306_REVIEW.md',R/'p_v2/ROOT_P_AUDIT.json']}}
dest=R/'OPUS307_RECEIPT.json';assert not dest.exists();dest.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'receipt':str(dest),'accepted':True,'component_cases':len(cases),'runtime_changed':False,'actual_J_DASH_precedence_known':False},ensure_ascii=False))
