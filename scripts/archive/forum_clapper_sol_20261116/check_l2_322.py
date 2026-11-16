"""Task180 independent incremental checks and existing full-output artifact receipts; no replay/P/game."""
from pathlib import Path
import ast,datetime,hashlib,json,os,statistics,subprocess,sys,traceback,xml.etree.ElementTree as ET
import psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/task180_l2_322_20261106';O=B/'opus/review180';D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');S='9f6da15674da8c396d729a680f6868d47d9e233f';G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
sys.path.insert(0,str(D/'brain'));sys.dont_write_bytecode=True
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(n,d):
 p=A/n;assert not p.exists(),str(p);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def atom(p,d):
 t=p.with_name(p.name+'.322.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(t,p)
def git(*args):return subprocess.check_output([G,'-C',str(D),*args],encoding='utf-8').strip()
def jl(p):return [json.loads(l) for l in p.read_text(encoding='utf-8-sig').splitlines() if l.strip()]
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs') and st['active_work_package']==180
assert git('rev-parse','HEAD')==S and not git('diff','--name-only')
A.mkdir(exist_ok=False);me=psutil.Process();me.cpu_affinity(list(range(24,32)));me.nice(psutil.IDLE_PRIORITY_CLASS);job=dict(pid=me.pid,created=me.create_time(),cpus=me.cpu_affinity(),priority=me.nice(),phase='322 incremental7new+unreplayed-path checks and8 existing artifact full-output comparisons only')
put('ROOT_JOB.json',job);st.update(at=now(),phase='TASK180_322_SOURCE_AND_ARTIFACT_REVIEW',candidate_source=S,source_review_pending=True,own_offline_jobs=[job]);atom(B/'sol/STATUS.json',st)
try:
 old=read(B/'analysis/task179_body321_20261106/SOURCE_PACKET.json')['raw_runtime_files_sha256'];cur={n:sha(D/n) for n in old};changed=[n for n,h in old.items() if cur[n]!=h]
 assert changed==['brain/ssbot/combat/tactics/clapper_priority.py','brain/ssbot/train/forum_planner_policy.py'],changed
 added=['brain/ssbot/combat/tactics/clapper_scene.py','brain/ssbot/combat/tactics/clapper_tactics.py'];cur.update({n:sha(D/n) for n in added})
 inventory=git('ls-files','--','brain/ssbot').splitlines();assert not [n for n in inventory if n not in cur], 'missing runtime binding'
 blob=subprocess.check_output([G,'-C',str(D),'show','ecc6332b:brain/ssbot/combat/tactics/clapper_priority.py']).decode('utf-8')
 assert blob.replace('\r\n','\n')==(O/'baseline_clapper_priority.py').read_text(encoding='utf-8-sig').replace('\r\n','\n')
 put('SOURCE_PACKET.json',dict(source=S,base='ecc6332b0b977dacd86dfd3d4d3f57d71e0cdd61',runtime_files=len(cur),changed=changed,added=added,raw_runtime_files_sha256=cur,test_sha256=sha(D/'brain/tests/test_clapper_tactics180.py'),baseline_module_sha256=sha(O/'baseline_clapper_priority.py')))
 os.environ.update(PYTHONDONTWRITEBYTECODE='1',NUMBA_CACHE_DIR=str(B/'analysis/critical214_20261103/p_prepared_ce81b62c/numba_cache'))
 import pytest
 args=[str(D/'brain/tests/test_clapper_tactics180.py')]
 for file,names in [('test_clapper_priority.py',['test_rear_jumper_is_intercepted_then_kept_after_landing','test_takeoff_between_the_two_switches_with_a_stomp_entry','test_outside_jump_retreat_is_not_overwritten_by_escape_or_wall_pressure']),('test_clapper_middle.py',['test_only_guide_when_arrival_and_future_middle_room_both_fit','test_locked_landing_with_room_selects_standing_monster_from_either_focus','test_under_wins_when_its_declared_wall_room_is_larger'])]:
  args.extend(str(D/'brain/tests'/file)+'::'+n for n in names)
 rc=int(pytest.main([*args,'-q','-p','no:cacheprovider','--basetemp='+str(A/'pytest_tmp'),'--junitxml='+str(A/'CHECKS.xml')]))
 foreign=[getattr(m,'__file__',None) for n,m in list(sys.modules.items()) if n.startswith('ssbot') and getattr(m,'__file__',None) and not Path(m.__file__).resolve().is_relative_to(D)]
 assert rc==0 and not foreign and all(sha(D/n)==h for n,h in cur.items())
 tests=sum(int(x.attrib['tests']) for x in ET.parse(A/'CHECKS.xml').getroot().findall('testsuite'))
 put('CHECK_RECEIPT.json',dict(at=now(),source=S,pytest_rc=rc,checks=tests,foreign_modules=foreign,source_unchanged=True,job=job,scope='7new structural/commit checks plus selected original unreplayed intercept/hold/takeoff/retreat/guide/stand/under cases. Not190/1851 repeated tests.'))
 # Independent comparator: only the four explicit logging/timing fields are exempt.
 def norm(r):
  r=dict(r);r.pop('ns',None);r.pop('impl',None)
  if isinstance(r.get('last'),dict):r['last']={k:v for k,v in r['last'].items() if k not in ['clapper_eval','clapper_releases']}
  return r
 drop={'ms','timing_scope','elapsed_ms','send_return_ns','ts','t_ns','recv_ns','episode'}
 def chain(p):return [{k:v for k,v in r.items() if k not in drop} for r in jl(p/'decisions_i0.chain.jsonl')]
 scenes=['ob_off','ob_a4','ob_w3','ob_n1','g3','w2','p786','w1'];out={};total=0;oldns=[];newns=[]
 for n in scenes:
  base,new=O/'base'/n,O/'final'/n;x=jl(O/'base'/(n+'_l2dump.jsonl'));y=jl(O/'final'/(n+'_l2dump.jsonl'))
  assert len(x)==len(y) and all(norm(a)==norm(b) for a,b in zip(x,y)),n+' L2 full output/state difference'
  assert not any('dump_error' in a for a in x+y),n
  for a,b in zip(x,y):
   newlog=(b.get('last') or {}).get('clapper_eval')
   if newlog is not None:
    assert len(newlog['tactics'])==11 and sum(k in rec for rec in newlog['tactics'] for k in ['offers','not_applicable','excluded_by'])==11
  ca,cb=chain(base),chain(new);assert ca==cb,n+' chain'
  ra,rb=read(base/'RESULT.json'),read(new/'RESULT.json');assert rb['knife_head']==S and not rb['knife_brain_dirty'] and rb['exception'] is None and not rb['foreign'] and rb['p_entry']['ticks']==0
  assert all(sha(D/'brain/ssbot'/k)==h for k,h in rb['source_sha256'].items()),n+' source'
  strip=lambda row:{k:v for k,v in row.items() if k not in ['act_ms','ms','elapsed_ms','timing','timing_scope']}
  assert [strip(z) for z in ra['rows']]==[strip(z) for z in rb['rows']],n+' rows'
  assert ra['model_hits']==rb['model_hits'] and ra['model_hurts']==rb['model_hurts'],n+' contacts'
  timing=jl(O/'oldimpl'/(n+'_l2dump.jsonl'));assert len(timing)==len(y) and all(a['f']==b['f'] for a,b in zip(timing,y))
  oldns.extend(z['ns'] for z in timing);newns.extend(z['ns'] for z in y)
  total+=len(x);out[n]=dict(calls=len(x),same_full_outputs_goal_legacy_logs_memory_counters=True,chain_events=len(ca),sends=sum(r.get('event')=='transport_sent' for r in ca),rows=len(rb['rows']),model_hits=rb['model_hits'],model_hurts=rb['model_hurts'],new_log_pick_calls=sum('clapper_eval' in (z.get('last') or {}) for z in y),files={str(p):sha(p) for p in [new/'RESULT.json',O/'base'/(n+'_l2dump.jsonl'),O/'final'/(n+'_l2dump.jsonl')]})
 assert total==3670,total
 put('ARTIFACT_RECEIPT.json',dict(at=now(),source=S,scenes=out,total_decide_calls=total,scope='Only8 declared recorded/synthetic scenarios, no natural NPC or global equivalence; no policy rerun. Unreplayed winners remain explicit.'))
 diffs=[(b-a)/1e6 for a,b in zip(oldns,newns)];reported=read(O/'TIME322.json')['all']
 calc=dict(calls=len(diffs),paired_median_ms=statistics.median(diffs),paired_mean_ms=statistics.mean(diffs),new_max_ms=max(newns)/1e6,old_max_ms=max(oldns)/1e6)
 assert abs(round(calc['paired_median_ms'],4)-reported['new_minus_old_ms']['p50'])<1e-6
 put('ENGINEERING_TIMING_RECEIPT.json',dict(at=now(),source=S,calculated=calc,source_report=str(O/'TIME322.json'),source_report_sha256=sha(O/'TIME322.json'),method='8concurrent engineering jobs per batch; co-run E16-23 old/new. Not isolated/formal or evidence that all outliers are noise.',formal_P=False,full_tick_measured_here=False))
 # Direct structural check complements the supplied string-name test: winner calls only its own output hooks.
 cp=ast.parse((D/'brain/ssbot/combat/tactics/clapper_priority.py').read_text(encoding='utf-8-sig'));classes=ast.parse((D/'brain/ssbot/combat/tactics/clapper_tactics.py').read_text(encoding='utf-8-sig'))
 put('STRUCTURE_RECEIPT.json',dict(at=now(),new_units=11,rule_ids=13,public_functions=[x.name for x in cp.body if isinstance(x,ast.FunctionDef)],tactic_classes=[x.name for x in classes.body if isinstance(x,ast.ClassDef)],scope='Conditions/scores/outputs co-located in units; public compare/apply use declarations/hooks. Shared default/contact constraints remain explicit. No new gameplay certified.'))
 assert all(sha(D/n)==h for n,h in cur.items())
 put('ROOT_JOB_END.json',dict(at=now(),job=job,error=None,checks=tests,artifact_calls=total,source_unchanged=True,formal_P=0,games_started=0,policy_replays=0))
 print(json.dumps(dict(source=S,checks=tests,artifact_calls=total,scenes=8,runtime_files=len(cur),timing=calc,formal_P=0,games=0)))
except BaseException:
 put('ROOT_ERROR.json',dict(at=now(),error=traceback.format_exc()));raise
