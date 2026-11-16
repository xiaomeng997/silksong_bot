"""Finite read-only #320 artifact / input component audit. No policy replay, P or game."""
from pathlib import Path
import datetime,hashlib,importlib.util,json,os,subprocess,sys,traceback
import psutil
sys.dont_write_bytecode=True
B=Path('C:/ssbot/data/m2_play/clapper_plan');O=B/'opus/review179';R=B/'analysis/task179_input320_20261106';D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(n,x):
 p=R/n;assert not p.exists(),str(p);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def atom(p,x):
 t=p.with_name(p.name+'.audit320.tmp');t.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(t,p)
def jlines(p):return [json.loads(l) for l in p.read_text(encoding='utf-8-sig').splitlines() if l.strip()]
def chain(p):return jlines(p/'decisions_i0.chain.jsonl')
def sends(p):return [(r.get('frame'),r.get('target'),r.get('mask'),r.get('owner')) for r in chain(p) if r.get('event')=='transport_sent']
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs')
me=psutil.Process();me.cpu_affinity(list(range(24,32)));me.nice(psutil.IDLE_PRIORITY_CLASS)
job=dict(pid=me.pid,created=me.create_time(),phase='320 finite artifact/HF/DLL/raw-collider audit only',cpus=me.cpu_affinity(),priority=me.nice())
R.mkdir(exist_ok=False);put('ROOT_JOB.json',dict(at=now(),job=job,formal_P=0,games_started=0))
st.update(at=now(),phase='320_INDEPENDENT_INPUT_AND_BODY_REVIEW',own_offline_jobs=[job]);atom(B/'sol/STATUS.json',st)
try:
 packet=read(B/'analysis/task179_return318_20261106/SOURCE_PACKET.json')
 different=[n for n,h in packet['raw_runtime_files_sha256'].items() if sha(D/n)!=h];assert not different,different
 names=['a4ref_cs','a4skip','n1late','n1lateoff','n1p99','n1offp99','n1late_rt','n1ref_rt']
 rs={n:read(O/'l1_320'/n/'RESULT.json') for n in names}
 inputfile=O/'l1_320/packet_input.py';hffile=O/'l1_307/hf_cs.py';replayfile=O/'l1_308/replay308.py'
 for n,r in rs.items():
  assert r['exception'] is None and not r['foreign'] and not r['knife_brain_dirty'],n
  assert r['p_entry']['ticks']==0 and not r['p_entry']['formal'],n
  assert all(sha(D/'brain/ssbot'/p)==h for p,h in r['source_sha256'].items()),n
  mo=r['tool']['model_options'];assert mo['packet_input_sha256']==sha(inputfile) and mo['hf_cs_sha256']==sha(hffile),n
  assert r['tool']['replay308_sha256']==sha(replayfile),n
 put('SOURCE_BINDING.json',dict(at=now(),runtime_files=len(packet['raw_runtime_files_sha256']),unchanged=True,source=packet['source'],artifact_source_files=14,artifacts=names,files={str(p):sha(p) for p in [inputfile,hffile,replayfile,O/'l1_320/rettrace320.py',O/'l1_307/dllcheck/Program.cs']},result_hashes={n:sha(O/'l1_320'/n/'RESULT.json') for n in names}))
 spec=importlib.util.spec_from_file_location('root320_packet',inputfile);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 dll=Path('C:/ssbot/game/train/BepInEx/plugins/SsOracle/SsOracle.dll');want='ca7673dbeb8f3a061deca742aa0972f585c5284dd5328e8d2378d064509930ac'
 exe=next((O/'l1_307/dllcheck/bin/Release').rglob('DllCheck.exe'));assert sha(dll)==sha(exe.parent/'SsOracle.dll')==want
 def dll_run(hf,frames,name):
  pending=list(hf['pending'])+[0]*(32-len(hf['pending']));age=list(hf['age'])+[1<<20]*(32-len(hf['age']))
  lines=['restore '+' '.join(map(str,[hf['desired'],hf['latched'],*pending,*age]))];req=hf['desired']
  for fr in frames:
   pairs=[]
   for t,m in fr['due']:pairs.extend([req,m]);req=m
   lines.append(' '.join(map(str,[fr['f'],len(fr['due']),*pairs,req])))
  path=R/(name+'.schedule.txt');path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
  proc=subprocess.Popen([str(exe),str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
  child=psutil.Process(proc.pid)
  try:child.cpu_affinity(list(range(24,32)));child.nice(psutil.IDLE_PRIORITY_CLASS)
  except psutil.NoSuchProcess:pass
  out,err=proc.communicate(timeout=30);assert proc.returncode==0,(name,err)
  lines=out.strip().splitlines();values=[(int(l.split()[0]),int(l.split()[1])) for l in lines[1:]]
  assert len(values)==len(frames),name
  assert values==[(fr['f'],fr['latched']) for fr in frames],name
  return dict(frames=len(values),dll_equal=True,assembly=lines[0],own_child_pid=proc.pid,exit_code=proc.returncode)
 inputchecks={}
 for n in names[:6]:
  r=rs[n];frames=r['input_frames'];inp=mod.PacketInput(r['input_restore'],None,None)
  first=frames[0]['f'];s=read(O/'l1_320'/n/'RESULT.json');ss=sends(O/'l1_320'/n);sent={t:m for f,t,m,owner in ss}
  late={int(k):v for k,v in r['tool']['model_options']['late_tick'].items()};app={};last=None
  for t in sorted(t for t in sent if t>=first):
   a=t+late.get(t-2,0);app[t]=a if last is None else max(last,a);last=app[t]
  for fr in frames:
   due=[[t,sent[t]] for t in sorted(app) if app[t]==fr['f']];assert due==fr['due'],(n,fr['f'],'due')
   lat=inp.frame(fr['f'],due);assert (lat,inp.requested,inp.pending())==(fr['latched'],fr['requested'],fr['pending']),(n,fr['f'],'HF')
   if due or inp.applied is not None:assert [inp.applied,inp.target]==[fr['applied'],fr['target']],(n,fr['f'],'receipt')
  d=dll_run(r['input_restore'],frames,n)
  inputchecks[n]={**d,'multi':[fr['f'] for fr in frames if len(fr['due'])>1],'no_packet':[fr['f'] for fr in frames if not fr['due']],'receipt_changes_from319':[fr['f'] for fr in frames if [fr['applied'],fr['target']]!=fr['old_receipt']]}
 # Independent minimal edge / receipt cases, using the already-reviewed port and the actual DLL.
 components={}
 for n,start,req,frames in [('release_repress',1,1,[(100,[]),(101,[(101,0),(101,1)]),(102,[(102,1)]),(103,[(103,1)])]),('press_release',0,0,[(100,[]),(101,[(101,1),(101,0)]),(102,[(102,0)]),(103,[(103,0)])]),('no_packet_receipt',1,1,[(100,[(100,1)]),(101,[]),(102,[(102,0)])])]:
  hf=dict(desired=req,latched=start,pending=[0]*22,age=[5]*22);inp=mod.PacketInput(hf,99,99);out=[]
  for f,due in frames:
   lat=inp.frame(f,due);out.append(dict(f=f,due=due,latched=lat,pending=inp.pending(),applied=inp.applied,target=inp.target))
  if n=='release_repress':assert [x['latched'] for x in out]==[1,0,0,1]
  if n=='press_release':assert [x['latched'] for x in out]==[0,1,1,0]
  if n=='no_packet_receipt':assert [out[1]['applied'],out[1]['target']]==[100,100]
  components[n]=dict(frames=out,dll=dll_run(hf,out,n))
 put('INPUT_AND_DLL_CHECKS.json',dict(at=now(),dll_sha256=want,dll_helper_sha256=sha(exe),runs=inputchecks,components=components,scope='Plain, hold_frames=0, valid 22-bit masks, <=1 late application, no harness/watchdog; finite replay only'))
 compare={}
 for old,new in [('a4ref','a4ref_cs'),('a4skip','a4skip'),('n1late','n1late'),('n1p99','n1p99'),('n1offp99','n1offp99')]:
  p0=O/'l1_319'/old;p1=O/'l1_320'/new;a=read(p0/'RESULT.json');b=rs[new]
  assert sends(p0)==sends(p1),(old,new,'sends')
  assert a['model_hits']==b['model_hits'] and a['model_hurts']==b['model_hurts'],(old,new,'contacts')
  # Every row field except diagnostic cost, measured outside formal P.
  stripped=lambda row:{k:v for k,v in row.items() if k not in ('act_ms','ms','elapsed_ms','timing','timing_scope')}
  rowdiff=[i for i,(x,y) in enumerate(zip(a['rows'],b['rows'])) if stripped(x)!=stripped(y)]
  assert len(a['rows'])==len(b['rows']) and not rowdiff,(old,new,rowdiff[:4])
  compare[new]=dict(sends=len(sends(p1)),rows=len(b['rows']),equal_sends_rows_hits_hurts=True)
 for name,base in [('n1late_rt','n1late'),('n1ref_rt',None)]:
  if base:assert sends(O/'l1_320'/name)==sends(O/'l1_320'/base)
 a=rs['a4skip'];ev=[r for r in chain(O/'l1_320/a4skip') if 2793<=int(r.get('frame') or -1)<=2833 and r.get('event') in ('b2_selected','b2_strike_accepted','b2_real_bounce_handback','return_request_released','transfer_no_witness_handback')]
 trace={n:jlines(O/'l1_320'/(n+'_rettrace.jsonl')) for n in ('n1late_rt','n1ref_rt')}
 for n,rows in trace.items():
  assert not any('trace_error' in r for r in rows),n
  selected=[r for r in rows if 2813<=r['f']<=2835 and 'chosen' in r]
  assert len(selected)==23 and all(r['chosen']['orig'] and r['chosen']['narrow'] is None for r in selected),n
 put('ARTIFACT_COMPARE.json',dict(at=now(),finite_comparisons=compare,A_reacquisition_events=ev,A_model_hits=a['model_hits'],A_hurts=a['model_hurts'],N_contacts={n:rs[n]['model_hurts'] for n in ['n1late','n1p99','n1lateoff','n1offp99']},trace_first_stage_only={n:dict(rows=len(x),chosen_freed=23,examples=[r for r in x if r['f'] in (2813,2822,2826,2835,2836)]) for n,x in trace.items()},original_layer_not_rescored_or_closed_loop=True))
 sys.path.insert(0,str(D/'brain'))
 from ssbot.record.recorder import RecordingReader
 trial=Path(rs['n1late']['trial']);rec=next((trial/'run/rec').glob('*/TRAIN/*'));reader=RecordingReader(str(rec))
 wanted={2767,2814,2835,2836,2837,2838,2839,2841};raw={s['f']:s for s in reader.states(2767,2842) if s['f'] in wanted}
 for n in names[:6]:
  r=rs[n];s0=raw[r['synthetic_from']-1];hf=s0['act']['hf']
  assert r['input_restore']=={k:hf[k] for k in ('desired','latched','pending','age')},n
  if r['input_frames'][0]['due']:pass
  else:assert [r['input_frames'][0]['applied'],r['input_frames'][0]['target']]==[s0['act']['applied'],s0['act']['target']],n
 body=[]
 for f,s in raw.items():
  if f<2835:continue
  e=next(x for x in s['ents'] if x['iid']==335476)
  boxes=[]
  for c in e.get('colliders') or ():
   v=c.get('verts_world');d=c.get('damage') or {}
   if c.get('enabled') and v and int(d.get('dealt') or 0)>0:
    if isinstance(v[0],(list,tuple)):xy=v
    else:xy=list(zip(v[0::2],v[1::2]))
    boxes.append(dict(name=c.get('name'),box=[min(x[0] for x in xy),min(x[1] for x in xy),max(x[0] for x in xy),max(x[1] for x in xy)]))
  body.append(dict(f=f,pos=e['pos'],flip=e.get('flipX',e.get('flip')),fsm=e.get('fsm'),boxes=boxes))
 by={r['f']:r for r in body};b0=by[2835]['boxes'][0]['box'];b1=by[2836]['boxes'][0]['box'];delta=b1[0]-b0[0]
 assert abs(delta+0.705)<0.01,delta
 contact=rs['n1late']['model_hurts'][0];assert contact['f']==2839 and contact['owner']==335476
 widths={n:min(rs[n]['model_hurts'][0]['hero_box'][2],rs[n]['model_hurts'][0]['collider_box'][2])-max(rs[n]['model_hurts'][0]['hero_box'][0],rs[n]['model_hurts'][0]['collider_box'][0]) for n in ('n1late','n1p99')}
 assert all(x>0 for x in widths.values()),widths
 put('RAW_BINDING_AND_BODY.json',dict(at=now(),recording=str(rec),raw_files={str(p):sha(p) for p in rec.glob('state*')},input_restore_raw_equal=True,body=body,left_edge_change=delta,contact_width_rounded=widths,scope='Fixed recorded NPC states, synthetic hero, A additionally explicit reaction splice; not reactive NPC or real injury proof'))
 assert all(sha(D/n)==h for n,h in packet['raw_runtime_files_sha256'].items())
 put('ROOT_JOB_END.json',dict(at=now(),job=job,success=True,runtime_unchanged=True,formal_P=0,games_started=0,policy_replays=0))
 print(json.dumps(dict(success=True,runtime_files=714,input_frames=sum(len(rs[n]['input_frames']) for n in names[:6]),DLL_runs=9,raw_left_shift=delta,overlap=widths,artifacts=str(R))))
except BaseException:
 put('AUDIT_ERROR.json',dict(at=now(),error=traceback.format_exc(),job=job));raise
