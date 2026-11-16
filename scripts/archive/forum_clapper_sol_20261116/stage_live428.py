"""Stage the user's fresh 50-bout authorization without changing the owned lifecycle."""
from pathlib import Path
import ast,datetime,hashlib,importlib.util,json,shutil

B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/air_catch428_20261114'
OLD=B/'analysis/w13_50_landing425_20261114';G=B/'analysis/w13_50_air_catch428_20261114';D=B/'sol/demos'/G.name
H='d7cbe1a59cbee1d8fa8d40c53fc57b3ed1bd2b19';S=A/'source_fixed428';SCOPE='AIR_CATCH428_50_W13_HP2_CONTINUOUS'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'));sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def put(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def rewrite(t):
 for old,new in [(OLD.name,G.name),('landing_exit423_20261114','air_catch428_20261114'),
   ('source_fixed424','source_fixed428'),('a81a2597d2e7f04498a7300f14e910ab3259d499',H),
   ('LANDING425_50_W13_HP2_CONTINUOUS',SCOPE)]:t=t.replace(old,new)
 return t

assert not G.exists() and not D.exists()
state=read(B/'sol/STATUS.json')
assert state['current_source']==H and not state['source_review_pending'] and not state['own_offline_jobs'] and not state['live_or_budget_running'] and not state['own_live_session']
assert not (B/'sol/performance/ACTIVE.json').exists()
review=read(A/'SOURCE_REVIEW_AND_P_FINAL.json');audit=read(A/'ROOT_P_AUDIT.json');packet=read(A/'SOURCE_PACKET_FIXED.json')
assert review['accepted'] and audit['finite_measurement_valid'] and audit['actual_cleanup_verified']
assert review['source']==audit['source']==packet['source']==H
assert all(sha(S/n)==v for n,v in {**packet['raw_runtime_files_sha256'],**packet['support_sha256']}.items())
proposal=read(A/'NEW50_PROPOSAL.json');assert proposal['source']==H and proposal['maximum_attempts']==50
G.mkdir()
auth=read(OLD/'USER_NEW50_AUTHORIZATION.json')
auth.update(at=now(),source=H,batch_id=G.name,user_text='授权预热并连打新50盘',
 question_item_id='["request_user_input_async","call_1287eeb16d394511b6ed35526df0a062",0]',
 max_total_bouts_this_authorization=50,started=False,
 provenance={'kind':'Actual structured reply in this current Codex chat','observed_at':now(),
  'question':'连踩修复已通过源审和四窗有限计时，仍有超帧，实机收益尚未验证。上一批50盘授权已用完：是否授权预热并开始新的50盘？固定 d7cbe1a5，沿用上批配置并开启连踩；同一游戏连打、全程录像，2HP保护退出后继续收满，运行故障停批。',
  'answer':'授权预热并连打新50盘'},
 landing_exit_enabled_for_this_batch=True,airstrike_enabled_for_this_batch=True,
 authorization_from_heartbeat_alone=False,prior_paused_batch_reopened=False)
put(G/'USER_NEW50_AUTHORIZATION.json',auth)
sources={p.name:p.read_text(encoding='utf-8-sig') for p in OLD.glob('*.py')}
for name,text in sources.items():(G/name).write_text(rewrite(text),encoding='utf-8')
for name in ['trial.py','run_unattended.py','release.py','root_live_watch.py','capture.py','monitor.py','wait_resources.py','watch_worker.py']:
 assert ast.dump(ast.parse(rewrite(sources[name])),include_attributes=False)==ast.dump(ast.parse((G/name).read_text(encoding='utf-8')),include_attributes=False),name
for name in ['start_gate.py','user_authorization.py']:assert sha(G/name)==sha(OLD/name)
p=G/'trial.py';text=p.read_text(encoding='utf-8');anchor=' for key in ("SSBOT_FORUM_LANDING_EXIT","SSBOT_FORUM_TWO_WALK_RULE"):assert e.get(key)=="1",(key,e.get(key))';assert anchor in text
text=text.replace(anchor,anchor+'\n assert e.get("SSBOT_FORUM_AIRSTRIKE")=="1","this authorized batch enables the reviewed re-pogo entry"');p.write_text(text,encoding='utf-8')
p=G/'finish_preparation.py';text=p.read_text(encoding='utf-8');assert 'set(range(405,426))' in text
text=text.replace('set(range(405,426))','set(range(405,429))')
text=text.replace('Accepted finite same-source ON/OFF77frame ep12 async measurement with actual wire and cleanup; prior411/415/417/419 receipts retained. No performance budget/full scheduling pass. Unchanged runtime lifecycle reuses runtime354 actual probe/full50.',
 'Accepted same-source four-window ON/OFF301-frame per arm formal P with own B/synthetic B+1 and actual wire/cleanup; no full budget/scheduling claim. Pending preliminary slash branch is synthetic-test coverage. LANDING_EXIT0 in finite P; this explicitly authorized live batch retains prior live LANDING_EXIT1. Unchanged runtime lifecycle reuses runtime354 actual probe/full50.')
p.write_text(text,encoding='utf-8')
# Correct the known postprocessing-only stale source pointers before binding this fresh contract.
p=G/'root_cleanup.py';text=p.read_text(encoding='utf-8');assert "N/'source/brain'" in text
p.write_text(text.replace("N/'source/brain'","N/'source_fixed428/brain'"),encoding='utf-8')
p=G/'audit_repeat50.py';text=p.read_text(encoding='utf-8');assert "S=B/'analysis/air_catch428_20261114/source'" in text
p.write_text(text.replace("S=B/'analysis/air_catch428_20261114/source'","S=B/'analysis/air_catch428_20261114/source_fixed428'"),encoding='utf-8')
for name in ['engineering_helpers.py','resource_background.py','RESOURCE_BACKGROUND_APPROVAL.json','RESOURCE_BACKGROUND_CLASSIFICATION_CHECKS.json']:shutil.copy2(OLD/name,G/name)
plan=read(OLD/'CONTINUOUS_PLAN.json');assert plan['seeds']==proposal['seeds']
plan.update(at=now(),batch=G.name,source=H,authorization=auth['user_text'],
 comparison_baseline_source='a81a2597d2e7f04498a7300f14e910ab3259d499',
 notes='Only this fresh50; same50 seeds as landing425/runtime354; AIRSTRIKE1, LANDING_EXIT1 for batch, defaults remain off; no stopped batch reopened.')
put(G/'CONTINUOUS_PLAN.json',plan)
draft=json.loads(rewrite(json.dumps(read(OLD/'TRIAL_CONFIG_DRAFT.json'),ensure_ascii=False)))
draft.update(at=now(),source=H,user_authorized=True,authorization=auth['user_text'],
 purpose='One fresh explicitly authorized continuous50 on reviewed re-pogo source; same baseline configuration, AIRSTRIKE enabled',
 coverage_target='All50 HP/protected quits including postkill tail; actual action/owners/umbrella/hammer, full recording; no isolated causal claim')
draft['environment'].update(SSBOT_FORUM_AIRSTRIKE='1',SSBOT_FORUM_LANDING_EXIT='1',SSBOT_FORUM_TWO_WALK_RULE='1')
put(G/'TRIAL_CONFIG_DRAFT.json',draft)
reuse=read(B/'analysis/landing_exit423_20261114/RUNTIME354_REUSE.json')
assert all(sha(S/n)==h for n,h in reuse['lifecycle_files_unchanged'].items())
reuse.update(at=now(),source=H,parent='a81a2597d2e7f04498a7300f14e910ab3259d499',
 scope='Unchanged GC/fault/input/worker lifecycle; reuse actual runtime354 probe/full50; no extra probe authorized.')
put(A/'RUNTIME354_REUSE.json',reuse)
put(A/'VALIDATION_PLAN.json',dict(at=now(),source=H,source_review_accepted=True,scoped_P=str(A/'ROOT_P_AUDIT.json'),
 full_scheduling_gate_pass=False,performance_budget_pass=False,user_authorized=True,planned_bouts=50,next_candidate=G.name,
 scope='Fresh50 only; AIRSTRIKE1 plus prior baseline LANDING_EXIT1; real2HP continue, strict fault stops, full video; old stopped batches closed.'))
put(G/'CANDIDATE_SPEC.json',dict(at=now(),source=H,scope=SCOPE,batch=G.name,planned_bouts=50,
 authorization_kind=auth['kind'],source_review=str(A/'SOURCE_REVIEW_AND_P_FINAL.json')))
for p in G.glob('*.py'):compile(p.read_text(encoding='utf-8'),str(p),'exec')
put(G/'LIFECYCLE_REVIEW.json',dict(at=now(),accepted=True,source=H,files={p.name:sha(p) for p in G.glob('*.py')},
 previous_review=str(OLD/'LIFECYCLE_REVIEW.json'),owned_execute_AST_unchanged=True,runtime_control_flow_unchanged=True,
 changes='Labels/source paths, AIRSTRIKE1 assertion, reviewed delivery coverage and current P description; fix known cleanup/audit source paths before contract binding. Launcher/GO/input/capture/stops/cleanup control flow unchanged.',no_game_started=True))
put(G/'START_GATE_CHECKS.json',dict(at=now(),source=H,passed=True,prior_checks=str(OLD/'START_GATE_CHECKS.json'),
 unchanged_user_authorization_sha256=sha(G/'user_authorization.py'),unchanged_start_gate_sha256=sha(G/'start_gate.py'),
 cases=read(OLD/'START_GATE_CHECKS.json')['cases'],scope='Unchanged gate predicates reused; actual new held worker/input/capture/resource gates remain required.'))
put(G/'BATCH_SPEC.json',dict(at=now(),batch=G.name,source=H,planned_bouts=50,state='AUTHORIZED_STAGED_PREPARE_PENDING',
 ready=False,started=False,authorization=str(G/'USER_NEW50_AUTHORIZATION.json'),landing_exit=True,airstrike=True,
 source_default=False,comparison='landing425/runtime354 same50 seeds',prior_paused_batch_reopened=False))
spec=importlib.util.spec_from_file_location('live428_auth',G/'user_authorization.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
try:mod.validate_authorization(G,H)
except RuntimeError as e:assert str(e)=='missing current autonomous start authorization'
else:raise AssertionError('unbound authorization accepted')
state.update(at=now(),phase='LIVE428_AUTH_VERIFIED_STAGING',live_paused_by_user=False,
 live_pause_released_only_for_batch=G.name,authorized_batch=G.name,authorized_bouts=50,
 live428_authorization_consumed=False,next_phase='Finish gates, prewarm and start exactly this fresh50; current user explicitly authorized direct start. Restore pause at end/fault.')
put(B/'sol/STATUS.json',state)
put(G/'USER_AUTHORIZATION_BINDING.json',dict(at=now(),actual_current_chat_reply=True,authorization=auth['user_text'],question_item_id=auth['question_item_id'],source=H,maximum_bouts=50))
proposal.update(authorized=True,state='AUTHORIZED_PREPARING',authorization_receipt=str(G/'USER_NEW50_AUTHORIZATION.json'))
put(A/'NEW50_PROPOSAL.json',proposal)
launch=Path('C:/modeling/silksong_bot/tmp/launch_live425.ps1').read_text(encoding='utf-8')
Path('C:/modeling/silksong_bot/tmp/launch_live428.ps1').write_text(rewrite(launch),encoding='utf-8')
print(json.dumps(dict(batch=G.name,source=H,authorized_bouts=50,game_started=False),ensure_ascii=False))
