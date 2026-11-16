"""Fresh explicitly authorized #425 batch; preserve reviewed lifecycle and stops."""
from pathlib import Path
import ast,datetime,hashlib,importlib.util,json,shutil

B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/landing_exit423_20261114'
OLD=B/'analysis/w13_50_rune_exit411_20261113';G=B/'analysis/w13_50_landing425_20261114';D=B/'sol/demos'/G.name
H='a81a2597d2e7f04498a7300f14e910ab3259d499';S=A/'source_fixed424';SCOPE='LANDING425_50_W13_HP2_CONTINUOUS'
read=lambda p:json.loads(Path(p).read_text('utf-8-sig'));sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def put(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n','utf-8')
def rewrite(t):
 for old,new in [(OLD.name,G.name),('C:/ssbot/data/m2_play/clapper_plan/analysis/rune_exit411_20261113/source',S.as_posix()),('rune_exit411_20261113','landing_exit423_20261114'),('4924058dab50ad9f0d9d6413e769f1aa6a1698cf',H),('RUNE_EXIT411_50_W13_HP2_CONTINUOUS',SCOPE)]:t=t.replace(old,new)
 return t

assert not G.exists() and not D.exists()
state=read(B/'sol/STATUS.json');assert state['current_source']==H and not state['source_review_pending'] and not state['own_offline_jobs'] and not state['live_or_budget_running']
assert not (B/'sol/performance/ACTIVE.json').exists()
review=read(A/'SOURCE_REVIEW_AND_P_FINAL.json');audit=read(A/'ROOT_P_AUDIT.json');packet=read(A/'SOURCE_PACKET_FIXED.json')
assert review['accepted'] and audit['finite_measurement_valid'] and audit['finite_branch_evidence_accepted'] and audit['actual_cleanup_verified']
assert review['source']==audit['source']==packet['source']==H
assert all(sha(S/n)==v for n,v in {**packet['raw_runtime_files_sha256'],**packet['support_sha256']}.items())
authfile=Path('C:/Users/Meng/.claude/projects/C--modeling-silksong-bot/8ae77f05-d535-4cd9-ac78-382cc9b66dd4.jsonl');uid='8f519e28-a1db-4ebb-8074-74b2b2d66103'
with authfile.open('rb') as f:
 f.seek(max(0,authfile.stat().st_size-10*1024*1024));lines=f.read().decode('utf-8',errors='replace').splitlines()
line=next(l for l in lines if uid in l);record=json.loads(line)
assert record['uuid']==uid and record['type']=='user' and record['message']['role']=='user'
content=record['message']['content'][0]['content'];assert '="开跑，落锤出口打开 (Recommended)"' in content and '同种子 50 盘' in content
G.mkdir()
auth=read(OLD/'USER_NEW50_AUTHORIZATION.json');auth.update(at=now(),source=H,batch_id=G.name,user_text='开跑，落锤出口打开 (Recommended)',question_item_id='Opus AskUserQuestion toolu_0131rnuBUpToMy5xnZ3evUrB',max_total_bouts_this_authorization=50,
    provenance={'file':str(authfile),'uuid':uid,'timestamp':record['timestamp'],'record_sha256':hashlib.sha256(line.encode()).hexdigest(),'actual_user_reply':content},
    landing_exit_enabled_for_this_batch=True,authorization_from_heartbeat_alone=False,prior_paused_batch_reopened=False,started=False)
put(G/'USER_NEW50_AUTHORIZATION.json',auth)
sources={p.name:p.read_text('utf-8-sig') for p in OLD.glob('*.py')}
for name,text in sources.items():(G/name).write_text(rewrite(text),'utf-8')
for name in ['trial.py','run_unattended.py','release.py','root_cleanup.py','root_live_watch.py','capture.py','monitor.py','wait_resources.py','watch_worker.py']:
 assert ast.dump(ast.parse(rewrite(sources[name])),include_attributes=False)==ast.dump(ast.parse((G/name).read_text('utf-8')),include_attributes=False),name
for name in ['start_gate.py','user_authorization.py']:assert sha(G/name)==sha(OLD/name)
p=G/'trial.py';text=p.read_text('utf-8');anchor=' assert e.get("SSBOT_FORUM_SLAM_NO_NEW_GLIDE")=="0","user requested extra slam umbrella filter OFF"';assert anchor in text
text=text.replace(anchor,anchor+'\n for key in ("SSBOT_FORUM_LANDING_EXIT","SSBOT_FORUM_TWO_WALK_RULE"):assert e.get(key)=="1",(key,e.get(key))');p.write_text(text,'utf-8')
p=G/'finish_preparation.py';text=p.read_text('utf-8')
replacements=[("sr['scoped_engineering_timing_pass']","sr['finite_measurement_valid']"),("p['scoped_engineering_timing_pass']","p['finite_measurement_valid']"),("A/'SOURCE_REVIEW_FINAL.json'","A/'SOURCE_REVIEW_AND_P_FINAL.json'"),("A/'SOURCE_PACKET.json'","A/'SOURCE_PACKET_FIXED.json'"),("A/'source'/n","A/'source_fixed424'/n"),("A/'source/brain'","A/'source_fixed424/brain'"),("set(range(405,412))","set(range(405,426))")]
for old,new in replacements:assert old in text,old;text=text.replace(old,new)
text=text.replace("Two finite affected E/W async production windows measured with actual wire and cleanup. Unchanged runtime lifecycle reuses parent actual probe and full50. Full scheduling and route safety remain unproved.","Accepted finite same-source ON/OFF77frame ep12 async measurement with actual wire and cleanup; prior411/415/417/419 receipts retained. No performance budget/full scheduling pass. Unchanged runtime lifecycle reuses runtime354 actual probe/full50.")
# Keep the legacy scoped-coverage field while explicitly preserving the measured budget result.
anchor="scoped_engineering_timing_pass=True,replay_P_not_affected=False";assert anchor in text
text=text.replace(anchor,"scoped_engineering_timing_pass=True,finite_measurement_valid=True,performance_budget_pass=False,replay_P_not_affected=False")
p.write_text(text,'utf-8')
for name in ['engineering_helpers.py','resource_background.py','RESOURCE_BACKGROUND_APPROVAL.json','RESOURCE_BACKGROUND_CLASSIFICATION_CHECKS.json']:shutil.copy2(OLD/name,G/name)
plan=read(B/'analysis/w13_50_runtime354_20261113/CONTINUOUS_PLAN.json');assert len(plan['seeds'])==50
plan.update(at=now(),batch=G.name,source=H,authorization=auth['user_text'],comparison_baseline_source='c3a55b7837b7105066fcb0e470b5716626913c28',notes='Only this fresh50; same50 seeds as runtime354; LANDING_EXIT1 for batch, code default remains0; paused rx411 not resumed.')
put(G/'CONTINUOUS_PLAN.json',plan)
draft=json.loads(rewrite(json.dumps(read(OLD/'TRIAL_CONFIG_DRAFT.json'),ensure_ascii=False)))
draft.update(at=now(),source=H,user_authorized=True,authorization=auth['user_text'],purpose='One authorized new50 on current reviewed five-package source; landing exit enabled only in this batch; same seeds as runtime354',coverage_target='All50 HP/actual protects plus landing-exit applied/unknown and handoff owners, full recording; changes not isolated causally')
draft['environment'].update(SSBOT_FORUM_LANDING_EXIT='1',SSBOT_FORUM_TWO_WALK_RULE='1');put(G/'TRIAL_CONFIG_DRAFT.json',draft)
reuse=read(B/'analysis/rune_exit411_20261113/RUNTIME354_REUSE.json');assert all(sha(S/n)==h for n,h in reuse['lifecycle_files_unchanged'].items())
reuse.update(at=now(),source=H,parent='4924058dab50ad9f0d9d6413e769f1aa6a1698cf',scope='Unchanged GC/fault/input/worker lifecycle; reuse actual runtime354 probe/full50, no extra probe authorized.');put(A/'RUNTIME354_REUSE.json',reuse)
put(A/'VALIDATION_PLAN.json',dict(at=now(),source=H,source_review_accepted=True,scoped_P=str(A/'ROOT_P_AUDIT.json'),full_scheduling_gate_pass=False,performance_budget_pass=False,user_authorized=True,planned_bouts=50,next_candidate=G.name,scope='Fresh50 only, same seeds, landing exit on in contract; real2HP continue, strict runtime stops, full video; original paused batch closed.'))
put(G/'CANDIDATE_SPEC.json',dict(at=now(),source=H,scope=SCOPE,batch=G.name,planned_bouts=50,authorization_kind=auth['kind'],source_review=str(A/'SOURCE_REVIEW_AND_P_FINAL.json')))
for p in G.glob('*.py'):compile(p.read_text('utf-8'),str(p),'exec')
put(G/'LIFECYCLE_REVIEW.json',dict(at=now(),accepted=True,source=H,files={p.name:sha(p) for p in G.glob('*.py')},previous_review=str(OLD/'LIFECYCLE_REVIEW.json'),owned_execute_AST_unchanged=True,runtime_control_flow_unchanged=True,changes='New labels/source path and explicit LANDING_EXIT1/WALK_RULE1 assertions; preparation binds current finite-P schema while budget/full scheduling stay false. Start/input/stop/GO/capture/cleanup unchanged.',no_game_started=True))
put(G/'START_GATE_CHECKS.json',dict(at=now(),source=H,passed=True,prior_checks=str(OLD/'START_GATE_CHECKS.json'),unchanged_user_authorization_sha256=sha(G/'user_authorization.py'),unchanged_start_gate_sha256=sha(G/'start_gate.py'),cases=read(OLD/'START_GATE_CHECKS.json')['cases'],scope='Unchanged predicates reused; actual new held worker/input/capture/resource gates still required.'))
put(G/'BATCH_SPEC.json',dict(at=now(),batch=G.name,source=H,planned_bouts=50,state='AUTHORIZED_STAGED_PREPARE_PENDING',ready=False,started=False,authorization=str(G/'USER_NEW50_AUTHORIZATION.json'),landing_exit=True,source_default=False,comparison='runtime354 same50 seeds',prior_paused_batch_reopened=False))
spec=importlib.util.spec_from_file_location('new425_auth',G/'user_authorization.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
try:mod.validate_authorization(G,H)
except RuntimeError as e:assert str(e)=='missing current autonomous start authorization'
else:raise AssertionError('unbound authorization accepted')
state.update(at=now(),phase='LIVE425_AUTH_VERIFIED_STAGING',last_scanned_opus=425,live_paused_by_user=False,live_pause_released_only_for_batch=G.name,authorized_batch=G.name,authorized_bouts=50,
    next_phase='Finish current source/input/resource/recording gates, launch exactly this fresh50 LANDING_EXIT1, restore pause after completion or strict stop; no ready dialog required by actual user start choice.')
put(B/'sol/STATUS.json',state)
put(B/'analysis/committed388_20261111/RECEIPT425.json',dict(at=now(),opus_number=425,source=H,user_authorization_verified=True,actual_user_record=auth['provenance'],fresh_batch=G.name,maximum_attempts=50,landing_exit=True,source_default=False,prior_stopped_batch_reopened=False,stage='staged, no game started',started=False))
print(json.dumps(dict(batch=G.name,source=H,user_authorization_verified=True,bouts=50,seed_count=len(plan['seeds']),landing_exit=True,game_started=False),ensure_ascii=False))
