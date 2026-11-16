"""Sol-reviewed freeze and two conditional live candidates; no user authorization or game launch."""
from pathlib import Path
import ast,datetime,hashlib,importlib.util,json,os,shutil,subprocess,sys
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/runtime354_20261113';P=B/'analysis/b13b_402_20261113';OLD=B/'analysis/w13_50_b13b404_20261113'
WT=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');GIT='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
HEAD='c3a55b7837b7105066fcb0e470b5716626913c28';read=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'));sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
stamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
def put(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def git(*args,cwd=WT):return subprocess.check_output([GIT,*args],cwd=cwd)
def main():
 assert git('rev-parse','HEAD').decode().strip()==HEAD and not A.exists()
 A.mkdir();root=A/'source';root.mkdir();old=read(P/'SOURCE_PACKET.json')
 for n,h in {**old['raw_runtime_files_sha256'],**old['support_sha256']}.items():
  p=P/'source'/n;assert sha(p)==h;q=root/n;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
 names=set(old['raw_runtime_files_sha256']);delta=git('diff','--name-only',old['source'],HEAD).decode().splitlines()
 changed=[n for n in delta if n.startswith('brain/ssbot/') or n.startswith('knowledge/')]
 assert set(changed)=={'brain/ssbot/combat/knife_chain_air.py','brain/ssbot/combat/runtime_gc.py','brain/ssbot/tools/combat_run.py','brain/ssbot/train/episode.py'}
 for n in changed:
  q=root/n;q.parent.mkdir(parents=True,exist_ok=True);data=git('show',HEAD+':'+n)
  if q.exists() and b'\r\n' in q.read_bytes():data=data.replace(b'\n',b'\r\n')
  q.write_bytes(data);names.add(n)
 shutil.copytree(P/'source/.git',root/'.git');git('symbolic-ref','HEAD','refs/heads/codex/runtime354_freeze',cwd=root);git('update-ref','refs/heads/codex/runtime354_freeze',HEAD,cwd=root);git('read-tree','HEAD',cwd=root)
 assert not git('diff','HEAD','--','brain/ssbot','knowledge',cwd=root).strip()
 packet=dict(at=stamp,source=HEAD,parent=old['source'],source_root=str(root),runtime_files=len(names),raw_runtime_files_sha256={n:sha(root/n) for n in sorted(names)},runtime_support_files=old['runtime_support_files'],support_sha256={n:sha(root/n) for n in old['support_sha256']},runtime_delta=changed)
 put(A/'SOURCE_PACKET.json',packet)
 put(A/'SOURCE_REVIEW_FINAL.json',dict(at=stamp,source=HEAD,accepted=True,source_component_verified=True,opus_number=410,reviewed_files=changed,new_tests_reviewed=18,author_affected_suite_reported_passed=612,author_mutations_caught=8,source_review='C:/ssbot/data/m2_play/clapper_plan/analysis/committed388_20261111/REVIEW410.md',replay_P_not_affected=True,formal_timing_pass=False,live_released=False,actual_stop_freeze_verified=False,real_runtime_probe_required=True,limitations=['RPC fakes are component evidence only.','Threshold10000 suppresses automatic gen2 for this measured bounded workload; runtime diagnostics still need checking.','Heap retention source not established.']))
 put(A/'VALIDATION_PLAN.json',dict(at=stamp,source=HEAD,scope='Only runtime worker lifecycle changed. Existing replay P never calls these changed startup/bout/fault paths; not rerun or counted as proof.',probe=dict(batch='w13_runtime354_probe_20261113',maximum_attempts=1,stall_ms=160,stall_tick=200,stall_episode=0,purpose='Actual startup threshold/GC receipt, then a short deliberately induced integrity stop: real release/freeze RPC before persistence, physical cleanup. Preserve expected failure and never reopen it.'),conditional50=dict(batch='w13_50_runtime354_20261113',attempts=50,condition='REAL_RUNTIME_PROBE_AUDIT.json passed, matching source and actual cleanup/GC/freeze checks',same_seeds=True),user_authorization_present=False,max_additional_attempts_if_approved=51))
 candidates=[]
 for n,batch,scope,kind in [(1,'w13_runtime354_probe_20261113','RUNTIME354_PROBE1_W13_HP2','explicit_user_chat_runtime_probe1'),(50,'w13_50_runtime354_20261113','RUNTIME354_50_W13_HP2_CONTINUOUS','explicit_user_chat_unattended_new50')]:
  G=B/'analysis'/batch;D=B/'sol/demos'/batch;assert not G.exists() and not D.exists();G.mkdir()
  def rewrite(text):
   for oldv,new in [(OLD.name,batch),('b13b_402_20261113','runtime354_20261113'),('e7e975f38c85b8f4a2aae47399a5425ff46a1d6b',HEAD),('B13B404_50_W13_HP2_CONTINUOUS',scope),('explicit_user_chat_unattended_new50',kind)]:text=text.replace(oldv,new)
   return text
  for p in OLD.glob('*.py'):
   if p.name=='finish_preparation.py':continue
   text=rewrite(p.read_text(encoding='utf-8'))
   if n==1:
    if p.name=='user_authorization.py':text=text.replace('auth.get("planned_bouts")==50','auth.get("planned_bouts")==1')
    if p.name=='trial.py':text=text.replace('a[a.index("--episodes")+1]=="50"','a[a.index("--episodes")+1]=="1"').replace('time.monotonic()-t>9000','time.monotonic()-t>600')
    if p.name=='root_cleanup.py':text=text.replace('len(rows)==50','len(rows)==1')
   # Check the owned execute lifecycle, including the deliberately tighter probe timeout.
   if p.name=='trial.py':
    expected=rewrite(p.read_text(encoding='utf-8'))
    if n==1:expected=expected.replace('time.monotonic()-t>9000','time.monotonic()-t>600')
    get=lambda t:next(v for v in ast.parse(t).body if isinstance(v,ast.FunctionDef) and v.name=='execute')
    assert ast.dump(get(expected),include_attributes=False)==ast.dump(get(text),include_attributes=False)
   (G/p.name).write_text(text,encoding='utf-8')
  shutil.copy2(Path(__file__).with_name('finish_runtime354_candidate.py'),G/'finish_preparation.py')
  # A fresh held worker must expose the actual new GC settings, not just a source flag.
  p=G/'release.py';text=p.read_text(encoding='utf-8');anchor="assert ip['passed'] and ip['worker_pid']==worker.pid and warm['trace_signatures']>0 and warm['vault_near']['hook_control_warmed'] and gc['frozen']>0";assert anchor in text
  text=text.replace(anchor,anchor+"\n assert gc['threshold']==gc['threshold_before'][:2]+[10000] and gc['gc_enabled'] is True")
  p.write_text(text,encoding='utf-8')
  for name in ['engineering_helpers.py','resource_background.py','RESOURCE_BACKGROUND_APPROVAL.json','RESOURCE_BACKGROUND_CLASSIFICATION_CHECKS.json']:shutil.copy2(OLD/name,G/name)
  plan=read(OLD/'CONTINUOUS_PLAN.json');plan.update(at=stamp,batch=batch,source=HEAD,attempts=n,target_bouts=n,seeds=plan['seeds'][:n],authorization='PENDING_CURRENT_BOUNDED_AUTHORIZATION',notes='One fault-protection validation probe.' if n==1 else 'Fresh50 only after runtime probe passes; previous stopped40 stays closed. Same tactics/B13/B13B.');put(G/'CONTINUOUS_PLAN.json',plan)
  draft=json.loads(rewrite(json.dumps(read(OLD/'TRIAL_CONFIG_DRAFT.json'),ensure_ascii=False)))
  args=draft['arguments'];args[args.index('--episodes')+1]=str(n)
  if n==1:args.extend(['--measure-stall-ms','160','--measure-stall-tick','200','--measure-stall-episode','0'])
  draft.update(at=stamp,user_authorized=False,authorization='PENDING_CURRENT_BOUNDED_AUTHORIZATION',purpose=plan['notes'],source=HEAD);put(G/'TRIAL_CONFIG_DRAFT.json',draft)
  for p in G.glob('*.py'):compile(p.read_text(encoding='utf-8'),str(p),'exec')
  spec=dict(at=stamp,source=HEAD,scope=scope,batch=batch,planned_bouts=n,authorization_kind=kind,probe_required_before_50=n==50,real_probe_proof=str(A/'REAL_RUNTIME_PROBE_AUDIT.json'),source_review=str(A/'SOURCE_REVIEW_FINAL.json'))
  put(G/'CANDIDATE_SPEC.json',spec)
  put(G/'LIFECYCLE_REVIEW.json',dict(at=stamp,accepted=True,source=HEAD,files={p.name:sha(p) for p in G.glob('*.py')},previous_review=str(OLD/'LIFECYCLE_REVIEW.json'),launch_action_stop_capture_cleanup_reused=True,changes='Batch/source/scope labels; probe planned count1 and a tighter600s total worker bound. New actual startup GC readback assertion. Preparation requires current authorization and (for50) successful real probe. No stop relaxation.',no_game_started=True))
  oldchecks=read(OLD/'START_GATE_CHECKS.json');put(G/'START_GATE_CHECKS.json',dict(at=stamp,syntax_pass=True,source=HEAD,existing_cases_reused_from=str(OLD/'START_GATE_CHECKS.json'),cases=oldchecks['cases'],verification='Authorization/release predicates unchanged except explicit probe kind/count1 constants; fresh missing-authorization rejection tested.',no_game_started=True))
  ms=importlib.util.spec_from_file_location('missing_auth_'+str(n),G/'user_authorization.py');m=importlib.util.module_from_spec(ms);ms.loader.exec_module(m)
  try:m.validate_authorization(G,HEAD)
  except RuntimeError as e:assert str(e)=='missing current autonomous start authorization'
  else:raise AssertionError('unapproved candidate accepted')
  put(G/'BATCH_SPEC.json',dict(at=stamp,batch=batch,source=HEAD,planned_bouts=n,state='STAGED_AWAIT_BOUNDED_AUTHORIZATION',ready=False,started=False,authorization=None,no_game_started=True,conditional_on_probe=n==50))
  candidates.append(dict(batch=batch,bouts=n,game_started=False))
 put(A/'CANDIDATES.json',dict(at=stamp,source=HEAD,candidates=candidates,total_maximum_bouts=51,user_authorized=False))
 print(json.dumps(dict(source=HEAD,runtime_files=len(names),candidates=candidates,no_game_started=True),ensure_ascii=False))
if __name__=='__main__':main()
