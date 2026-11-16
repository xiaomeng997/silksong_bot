"""Fresh authorized display-held50. No mutation of stopped-batch prerequisites."""
from pathlib import Path
import ast,datetime,hashlib,json,shutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/air_catch428_20261114';OP=B/'analysis/display_start429_20261114'
OLD=B/'analysis/w13_50_air_catch428_20261114';G=B/'analysis/w13_50_air_catch429_display_20261114';D=B/'sol/demos'/G.name
H='d7cbe1a59cbee1d8fa8d40c53fc57b3ed1bd2b19'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'));sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def put(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def rewrite(t):return t.replace(OLD.name,G.name).replace('AIR_CATCH428_50_W13_HP2_CONTINUOUS','AIR_CATCH429_DISPLAY50_W13_HP2_CONTINUOUS')
assert not G.exists() and not D.exists()
s=read(B/'sol/STATUS.json');assert s['current_source']==H and not s['source_review_pending'] and not s['live_or_budget_running'] and not s['own_offline_jobs'] and not s['own_live_session']
assert read(OLD/'ROOT_CLEANUP.json')['complete'] and not (B/'sol/performance/ACTIVE.json').exists()
proposal=read(OP/'NEW50_DISPLAY_PROPOSAL.json');assert proposal['source']==H
packet=read(A/'SOURCE_PACKET_FIXED.json');S=Path(packet['source_root']);assert all(sha(S/n)==h for n,h in {**packet['raw_runtime_files_sha256'],**packet['support_sha256']}.items())
assert read(A/'SOURCE_REVIEW_AND_P_FINAL.json')['accepted'] and read(A/'ROOT_P_AUDIT.json')['finite_measurement_valid']
G.mkdir()
for p in OLD.glob('*.py'):(G/p.name).write_text(rewrite(p.read_text(encoding='utf-8-sig')),encoding='utf-8')
for name in ['trial.py','capture.py','monitor.py','wait_resources.py','watch_worker.py','root_cleanup.py','root_live_watch.py']:
 assert ast.dump(ast.parse((G/name).read_text(encoding='utf-8')),include_attributes=False)==ast.dump(ast.parse(rewrite((OLD/name).read_text(encoding='utf-8-sig'))),include_attributes=False)
for name in ['engineering_helpers.py','resource_background.py','RESOURCE_BACKGROUND_APPROVAL.json','RESOURCE_BACKGROUND_CLASSIFICATION_CHECKS.json']:shutil.copy2(OLD/name,G/name)
for name in ['display_hold429.py','start_gate429.py']:
 assert sha(OP/name)==read(OP/'REVIEW429.json')['operating_helpers'][name]
 shutil.copy2(OP/name,G/name)
auth=read(OLD/'USER_NEW50_AUTHORIZATION.json');auth.update(at=now(),source=H,batch_id=G.name,user_text='允许临时亮屏并开新50盘',
 question_item_id='["request_user_input_async","call_332df21ce9104715b349be44be4684dc",0]',started=False,
 display_awake_for_this_batch=True,maximum_display_seconds=7200,minimum_launch_fps=30,
 provenance={'kind':'Actual structured reply in current Codex chat','observed_at':now(),'answer':'允许临时亮屏并开新50盘',
 'question':'是否允许本批临时让LG电视保持亮着，并另开新50盘？固定d7cbe1a5，预热启动平均帧速达到30FPS才开打，否则取消并清理；同一游戏全程录像，2HP保护后继续，运行故障停批。旧批已停止，不能续剩余49盘。'})
put(G/'USER_NEW50_AUTHORIZATION.json',auth)
for name in ['RUNTIME354_REUSE.json','VALIDATION_PLAN.json']:shutil.copy2(A/name,G/name)
v=read(G/'VALIDATION_PLAN.json');v.update(at=now(),next_candidate=G.name,scope='Fresh display-held50 only, launch average>=30fps before GO; prior fault batch remains stopped.');put(G/'VALIDATION_PLAN.json',v)
p=G/'finish_preparation.py';t=p.read_text(encoding='utf-8');t=t.replace("A/'VALIDATION_PLAN.json'","G/'VALIDATION_PLAN.json'").replace("A/'RUNTIME354_REUSE.json'","G/'RUNTIME354_REUSE.json'").replace('set(range(405,429))','set(range(405,430))');p.write_text(t,encoding='utf-8')
# The only runtime guard additions are extra rejects before launching and GO.
p=G/'run_unattended.py';t=p.read_text(encoding='utf-8');anchor='  m.execute()';assert t.count(anchor)==1
t=t.replace(anchor,'  hold=json.loads((HERE/"DISPLAY_HOLD_READY.json").read_text(encoding="utf-8"))\n  assert hold["active"] and not (HERE/"DISPLAY_HOLD_CLOSED.json").exists()\n  hp=psutil.Process(hold["pid"]);assert abs(hp.create_time()-hold["created"])<.01\n'+anchor);p.write_text(t,encoding='utf-8')
p=G/'release.py';t=p.read_text(encoding='utf-8');anchor=" held=dict(at=now(),source=c['source']";assert t.count(anchor)==1
extra=''' from start_gate429 import check as cadence_check
 cadence=cadence_check(D)
 putnew(G/'STARTUP_CADENCE_GATE.json',dict(at=now(),**cadence))
 assert cadence['passed'],'startup game cadence below30fps or invalid: cancel without combat'
 hold=read(G/'DISPLAY_HOLD_READY.json');hp=psutil.Process(hold['pid'])
 assert abs(hp.create_time()-hold['created'])<.01 and not (G/'DISPLAY_HOLD_CLOSED.json').exists()
'''
t=t.replace(anchor,extra+anchor);p.write_text(t,encoding='utf-8')
plan=read(OLD/'CONTINUOUS_PLAN.json');assert plan['seeds']==proposal['seeds'];plan.update(at=now(),batch=G.name,authorization=auth['user_text'],notes='Fresh50, same d7 and50 seeds; awake display request and launch>=30fps; old stopped batch never resumed.');put(G/'CONTINUOUS_PLAN.json',plan)
draft=json.loads(rewrite(json.dumps(read(OLD/'TRIAL_CONFIG_DRAFT.json'),ensure_ascii=False)));draft.update(at=now(),authorization=auth['user_text'],purpose='Fresh50 with explicit temporary display hold and launch cadence pre-GO rejection');put(G/'TRIAL_CONFIG_DRAFT.json',draft)
candidate=read(OLD/'CANDIDATE_SPEC.json');candidate.update(at=now(),batch=G.name,scope='AIR_CATCH429_DISPLAY50_W13_HP2_CONTINUOUS');put(G/'CANDIDATE_SPEC.json',candidate)
for p in G.glob('*.py'):compile(p.read_text(encoding='utf-8'),str(p),'exec')
put(G/'LIFECYCLE_REVIEW.json',dict(at=now(),accepted=True,source=H,files={p.name:sha(p) for p in G.glob('*.py')},
 previous_review=str(OLD/'LIFECYCLE_REVIEW.json'),owned_execute_AST_unchanged=True,
 runtime_control_flow_unchanged=True,changes='Fresh labels/auth; per-batch metadata copies preserve old prerequisites; add display identity reject before execute and reviewed launch>=30fps plus display-alive reject before original GO. Original execute/input/stops/capture/cleanup unchanged.',
 operating_review=str(OP/'REVIEW429.json'),no_game_started=True))
checks=read(OLD/'START_GATE_CHECKS.json');checks.update(at=now(),source=H,new_launch_gate_review=str(OP/'REVIEW429.json'));put(G/'START_GATE_CHECKS.json',checks)
put(G/'BATCH_SPEC.json',dict(at=now(),batch=G.name,source=H,planned_bouts=50,state='AUTHORIZED_STAGED_PREPARE_PENDING',ready=False,started=False,
 authorization=str(G/'USER_NEW50_AUTHORIZATION.json'),display_awake=True,minimum_launch_fps=30,airstrike=True,landing_exit=True,prior_paused_batch_reopened=False))
s.update(at=now(),phase='LIVE429_DISPLAY_AUTH_VERIFIED_STAGING',live_paused_by_user=False,authorized_batch=G.name,authorized_bouts=50,
 live_pause_released_only_for_batch=G.name,live429_authorization_consumed=False,next_phase='Prepare, temporary display request, launch/prewarm then>=30fps original GO gate; cancel/cleanup if slow. No extra dialog required.')
put(B/'sol/STATUS.json',s)
proposal.update(at=now(),authorized=True,display_awake_authorized=True,state='AUTHORIZED_PREPARING',authorization_receipt=str(G/'USER_NEW50_AUTHORIZATION.json'));put(OP/'NEW50_DISPLAY_PROPOSAL.json',proposal)
launch=Path('C:/modeling/silksong_bot/tmp/launch_live428.ps1').read_text(encoding='utf-8');Path('C:/modeling/silksong_bot/tmp/launch_live429.ps1').write_text(rewrite(launch),encoding='utf-8')
print(json.dumps(dict(batch=G.name,source=H,authorized_bouts=50,display_authorized=True,game_started=False)))
