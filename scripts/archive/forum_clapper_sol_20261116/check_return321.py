"""Incremental #321 source/artifact checks, E cores only; no policy replay, P or game."""
from pathlib import Path
import datetime,hashlib,json,os,subprocess,sys,traceback
import psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/task179_body321_20261106';D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');O=B/'opus/review179/l1_321';S='ecc6332b0b977dacd86dfd3d4d3f57d71e0cdd61'
G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe';sys.path.insert(0,str(D/'brain'));sys.dont_write_bytecode=True
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(n,d):
 p=A/n;assert not p.exists(),str(p);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def atom(p,d):
 t=p.with_name(p.name+'.321.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(t,p)
def chain(p):return [json.loads(l) for l in (p/'decisions_i0.chain.jsonl').read_text(encoding='utf-8-sig').splitlines() if l.strip()]
def sends(p,last=10**9):return [(r.get('frame'),r.get('target'),r.get('mask'),r.get('owner')) for r in chain(p) if r.get('event')=='transport_sent' and int(r.get('frame') or -1)<=last]
def rows(r):return [{k:v for k,v in q.items() if k not in ('act_ms','ms','elapsed_ms','timing','timing_scope')} for q in r['rows']]
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs')
assert subprocess.check_output([G,'-C',str(D),'rev-parse','HEAD'],text=True).strip()==S
assert not subprocess.check_output([G,'-C',str(D),'diff','--name-only'],text=True).strip()
A.mkdir(exist_ok=False);me=psutil.Process();me.cpu_affinity(list(range(24,32)));me.nice(psutil.IDLE_PRIORITY_CLASS)
job=dict(pid=me.pid,created=me.create_time(),cpus=me.cpu_affinity(),priority=me.nice(),phase='321 12 new body-shape checks plus3 adjacent and finite artifact/raw-polygon receipt')
put('ROOT_JOB.json',job);st.update(at=now(),phase='RETURN321_SOURCE_ARTIFACT_REVIEW',candidate_source=S,source_review_pending=True,own_offline_jobs=[job]);atom(B/'sol/STATUS.json',st)
rc=None;err=None
try:
 old=read(B/'analysis/task179_return318_20261106/SOURCE_PACKET.json')['raw_runtime_files_sha256'];cur={n:sha(D/n) for n in old};changed=[n for n in cur if cur[n]!=old[n]]
 assert changed==['brain/ssbot/combat/attack_range.py','brain/ssbot/combat/forum_v2.py'],changed
 put('SOURCE_PACKET.json',dict(source=S,base='0b1481774f04838a610e5d31a70acbfcdef623df',runtime_files=len(cur),changed=changed,raw_runtime_files_sha256=cur,test_sha256={n:sha(D/'brain/tests'/n) for n in ['test_return_body315.py','test_return_body321.py']}))
 os.environ.update(PYTHONDONTWRITEBYTECODE='1',NUMBA_CACHE_DIR=str(B/'analysis/critical214_20261103/p_prepared_ce81b62c/numba_cache'))
 import pytest
 rc=int(pytest.main([str(D/'brain/tests/test_return_body321.py'),*[str(D/'brain/tests/test_return_body315.py')+'::'+n for n in ['test_off_by_default_nothing_is_built_and_the_stacks_are_unchanged','test_hazards_keep_their_margin_and_an_inseparable_estimate_is_not_narrowed','test_ret_stack_rebuilds_the_stack_exactly_without_tags']],'-q','-p','no:cacheprovider','--basetemp='+str(A/'pytest_tmp'),'--junitxml='+str(A/'CHECKS.xml')]))
 foreign=[getattr(m,'__file__',None) for n,m in list(sys.modules.items()) if n.startswith('ssbot') and getattr(m,'__file__',None) and not Path(m.__file__).resolve().is_relative_to(D)]
 assert rc==0 and not foreign and all(sha(D/n)==h for n,h in cur.items())
 put('CHECK_RECEIPT.json',dict(at=now(),source=S,checks=15,pytest_rc=rc,foreign_modules=foreign,source_unchanged=True,job=job,scope='12 new shape checks + off/hazard/no-tag adjacent paths, not235 repeated tests or live acceptance'))
 names=['n1late_new','n1ref_new','a4_new','w3_new','n1late_sw22','w3_sw13'];matches=[];results={}
 for name,final in zip(names,['f_n1late','f_n1ref','f_a4','f_w3','f_n1late_sw22','f_w3_sw13']):
  p,q=O/name,O/final;x,y=read(p/'RESULT.json'),read(q/'RESULT.json');assert sends(p)==sends(q) and rows(x)==rows(y),(name,final)
  assert x['model_hits']==y['model_hits'] and x['model_hurts']==y['model_hurts'],name
  assert y['exception'] is None and not y['foreign'] and not y['knife_brain_dirty'] and not y['p_entry']['formal'] and y['p_entry']['ticks']==0
  assert all(sha(D/'brain/ssbot'/n)==h for n,h in y['source_sha256'].items()),final
  results[final]=y;matches.append(dict(before=name,final=final,sends=len(sends(q)),rows=len(y['rows']),source_head=y['knife_head'],model_hits=y['model_hits'],model_hurts=y['model_hurts']))
 assert sends(O/'f_a4',2942)==sends(B/'opus/review179/l1_319/a4ref',2942)
 assert sends(O/'f_w3_sw13')==sends(B/'opus/review179/l1_317/w3air9')
 assert sends(O/'f_n1late_sw22',2821)==sends(B/'opus/review179/l1_320/n1late',2821)
 def jlines(p):return [json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]
 nd=jlines(O/'n1late_dual_dual.jsonl');wd=jlines(O/'w3_dual2_dual.jsonl')
 ns=[r for r in nd if 2813<=r.get('f',-1)<=2835];ws=[r for r in wd if 2794<=r.get('f',-1)<=2812]
 assert len(ns)==23 and all(r['chosen']['n315'] is None and isinstance(r['chosen']['n321'],dict) for r in ns)
 assert len(ws)==19 and all(r['chosen']['n315'] is None and r['chosen']['n321'] is None and r['chosen']['env315'] is None and r['chosen']['env321'] is not None for r in ws)
 census=read(O/'STANDING321.json');n=sum(r['n'] for r in census['by_state_facing'].values());out=sum(r['outside'] for r in census['by_state_facing'].values());assert n==345710 and out==34 and len(census['outside_first_200'])==34
 put('ARTIFACT_RECEIPT.json',dict(at=now(),source=S,comment_only_version_pairs=matches,A_prefix_same_through2942=True,W3_switched2813_same_as_old=True,N_switch_prefix_same_through2821=True,N_prior_selected_side_rows_rejected=len(ns),W3_prior_selected_envelope_rows_rejected=len(ws),W3_whole_route_landing_not_retained=True,scope_disposition='Accept(a) conservative known-body-shape rejection; do not add approach recipes in this package. Only post2813 W3 landing/side-slash capability retained; whole live objective remains unverified.',census=dict(recordings=census['recordings'],frames=n,outside=out,independently_rescanned_235=False),diagnostic_files={str(p):sha(p) for p in [O/'STANDING321.json',O/'standing321.py',O/'swap321.py',O/'dual321.py',O/'dual2_321.py']}))
 # Independently check the reported AABB false positives against their actual six-vertex collider.
 import numpy as np
 from ssbot.record.recorder import RecordingReader
 trial=Path(results['f_n1late']['trial']);rec=next((trial/'run/rec').glob('*/TRAIN/*'));raw=next(s for s in RecordingReader(str(rec)).states(2935,2935))
 ent=next(e for e in raw['ents'] if e['iid']==335470);col=next(c for c in ent['colliders'] if c.get('enabled') and c.get('name')=='Slam Collider 2');poly=np.asarray(col['verts_world'],float).reshape(-1,2)
 assert len(poly)==6
 def sat_sep(p,b):
  box=np.array([[b[0],b[1]],[b[2],b[1]],[b[2],b[3]],[b[0],b[3]]]);sep=[]
  for q in (p,box):
   for i in range(len(q)):
    e=q[(i+1)%len(q)]-q[i];axis=np.array([-e[1],e[0]])
    if not np.any(axis):continue
    x,y=p@axis,box@axis
    if x.max()<y.min() or y.max()<x.min():sep.append(dict(axis=axis.tolist(),poly=[float(x.min()),float(x.max())],hero=[float(y.min()),float(y.max())]))
  return sep
 cross=[float(np.cross(poly[(i+1)%6]-poly[i],poly[(i+2)%6]-poly[(i+1)%6])) for i in range(6)]
 assert all(x>=-1e-6 for x in cross) or all(x<=1e-6 for x in cross),'SAT assumes convex collider'
 cases={k:[h for h in r['model_hurts'] if h['f']==2935 and h['owner']==335470] for k,r in results.items()}
 old=read(B/'opus/review179/l1_320/n1offp99/RESULT.json');cases['320_n1offp99']=[h for h in old['model_hurts'] if h['f']==2935]
 sat=[]
 for name,hs in cases.items():
  for h in hs:
   b=h['hero_box'];sep=sat_sep(poly,b);assert sep,(name,b)
   sat.append(dict(name=name,reported=h,polygon_intersection=False,separating_axes=sep))
 assert len(sat)>=3
 put('POLYGON_CORRECTION.json',dict(at=now(),source='Raw2935 collider vs synthetic hero boxes; not real HP',recording=str(rec),frame=2935,collider=col['name'],vertices=poly.tolist(),convex_crosses=cross,cases=sat,old_outputs_unchanged=True,scope='Only reviewed2935 records; body contacts2839/2842 are not reclassified'))
 assert all(sha(D/n)==h for n,h in cur.items())
 put('ROOT_JOB_END.json',dict(at=now(),job=job,error=None,pytest_rc=rc,formal_P_ticks=0,games_started=0,policy_replays=0,source_unchanged=True))
 print(json.dumps(dict(checks=15,rc=rc,source=S,source_files_changed=changed,artifact_pairs=6,N_side_rejections=23,W_envelope_rejections=19,polygon_false_positives=len(sat),formal_P=0,games=0)))
except BaseException:
 err=traceback.format_exc();put('ROOT_ERROR.json',dict(at=now(),error=err,pytest_rc=rc));raise
