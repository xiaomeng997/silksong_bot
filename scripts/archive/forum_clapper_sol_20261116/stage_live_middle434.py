"""Stage the actually approved fresh50 using the already reviewed continuous lifecycle."""
from pathlib import Path
from datetime import datetime,timezone
import ast,hashlib,json,shutil

B=Path('C:/ssbot/data/m2_play/clapper_plan');ROOT=Path('C:/modeling/silksong_bot')
OLD=B/'analysis/w13_50_air_catch429_tv_on_20261114';G=B/'analysis/w13_50_middle_handoff434_20261114';D=B/'sol/demos'/G.name
PA=B/'analysis/air_catch428_20261114';A=B/'analysis/middle_handoff434_20261114'
OLDH='d7cbe1a59cbee1d8fa8d40c53fc57b3ed1bd2b19';H='8e34fb6c71a3338b7652c741b12c5048086c6ae9'
TEXT='开始预热并连打新50盘（推荐）';QID='["request_user_input_async","call_18e09a8d8f5f483180836394fe7c0711",0]'
now=lambda:datetime.now(timezone.utc).isoformat();sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
def put(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def rewrite(t):
 for old,new in [(OLD.name,G.name),('AIR_CATCH429_TV_ON50_W13_HP2_CONTINUOUS','MIDDLE_HANDOFF434_W13_HP2_CONTINUOUS'),
                 ('air_catch428_20261114','middle_handoff434_20261114'),('source_fixed428','source_fixed434'),(OLDH,H),(OLDH[:8],H[:8])]:t=t.replace(old,new)
 return t
def obj(d):return json.loads(rewrite(json.dumps(d,ensure_ascii=False)))
assert G.exists() and not D.exists() and not (G/'USER_NEW50_AUTHORIZATION.json').exists()
s=read(B/'sol/STATUS.json');assert s['current_source']==H and not s['source_review_pending'] and not s['live_or_budget_running'] and not s['own_offline_jobs'] and not s['own_live_session']
assert not (B/'sol/performance/ACTIVE.json').exists() and read(OLD/'ROOT_CLEANUP.json')['complete']
packet=read(A/'SOURCE_PACKET_FIXED.json');S=Path(packet['source_root']);assert all(sha(S/n)==h for n,h in {**packet['raw_runtime_files_sha256'],**packet['support_sha256']}.items())
assert read(A/'SOURCE_REVIEW_AND_P_FINAL.json')['accepted'] and read(A/'ROOT_P_AUDIT.json')['finite_measurement_valid']
for p in OLD.glob('*.py'):
 t=rewrite(p.read_text(encoding='utf-8-sig'))
 if p.name=='finish_preparation.py':
  assert t.count('range(405,430)')==1;t=t.replace('range(405,430)','range(405,436)')
  start=t.index("formal_coverage_note='");end=t.index("')",start)
  t=t[:start]+"formal_coverage_note='Accepted same-source three-window MH ON/OFF185 frames per arm formal P, AS1/LANDING_EXIT1, own B/model B+1, wire and actual cleanup verified; not full budget/scheduling or live benefit. Unchanged runtime lifecycle reuses actual runtime354 probe and prior continuous50.'"+t[end+1:]
 if p.name=='trial.py':
  needle=' assert e.get("SSBOT_FORUM_AIRSTRIKE")=="1","this authorized batch enables the reviewed re-pogo entry"'
  assert needle in t;t=t.replace(needle,needle+'\n assert e.get("SSBOT_FORUM_MIDDLE_HANDOFF")=="1","this authorized batch enables the reviewed normal-middle handoff"')
 compile(t,str(G/p.name),'exec');(G/p.name).write_text(t,encoding='utf-8')
for n in ['RESOURCE_BACKGROUND_APPROVAL.json','RESOURCE_BACKGROUND_CLASSIFICATION_CHECKS.json']:
 shutil.copy2(OLD/n,G/n)
reuse=obj(read(OLD/'RUNTIME354_REUSE.json'));reuse.update(at=now(),source=H)
assert all(sha(S/n)==h for n,h in reuse['lifecycle_files_unchanged'].items())
assert sha(reuse['prior_real_probe'])==reuse['prior_real_probe_sha256']
put(G/'RUNTIME354_REUSE.json',reuse)
auth=obj(read(OLD/'USER_NEW50_AUTHORIZATION.json'))
auth.update(at=now(),source=H,batch_id=G.name,user_text=TEXT,question_item_id=QID,started=False,
 provenance=dict(kind='Actual current-chat async question reply',observed_at=now(),user_text=TEXT,question_item_id=QID,
                 scope='One fresh50 on8e34fb6c with MH1, same seeds/config, full video, HP2 continue/fault stop; temporary awake lease and >=30FPS startup gate'),
 middle_handoff_enabled_for_this_batch=True,physical_tv_on_confirmed_by_user=False,physical_TV_current_state_not_assumed=True)
put(G/'USER_NEW50_AUTHORIZATION.json',auth)
plan=obj(read(OLD/'CONTINUOUS_PLAN.json'));plan.update(at=now(),source=H,comparison_baseline_source=OLDH,authorization=TEXT,authorized=True,
 notes='Fresh authorized50, same seeds/order and one continuous game, MH1; temporary display request, startup>=30FPS beforeGO. Old batches stay closed.')
put(G/'CONTINUOUS_PLAN.json',plan)
draft=obj(read(OLD/'TRIAL_CONFIG_DRAFT.json'));draft.update(at=now(),source=H,user_authorized=True,authorization=TEXT,user_ready_required=False,combat_requires_new_ready=False,
 combat_start_authorization='explicit_user_chat_unattended_new50',purpose='Normal-middle-completion late handoff same50 live validation')
draft['environment']['SSBOT_FORUM_MIDDLE_HANDOFF']='1';put(G/'TRIAL_CONFIG_DRAFT.json',draft)
candidate=obj(read(OLD/'CANDIDATE_SPEC.json'));candidate.update(at=now(),source=H,authorization_kind='explicit_user_chat_unattended_new50');put(G/'CANDIDATE_SPEC.json',candidate)
for n in ['VALIDATION_PLAN.json','START_GATE_CHECKS.json']:
 d=obj(read(OLD/n));d['at']=now()
 if 'next_candidate' in d:d['next_candidate']=G.name
 put(G/n,d)
lc=obj(read(OLD/'LIFECYCLE_REVIEW.json'));lc.update(at=now(),accepted=True,files={p.name:sha(p) for p in G.glob('*.py')},
 previous_review=str(OLD/'LIFECYCLE_REVIEW.json'),changes='Same reviewed lifecycle/strict stops/input/capture/cleanup; only new source/batch/path labels and accepted review numbers/coverage metadata, plus explicit MH1 contract assertion. Actual current authorization separately bound.')
put(G/'LIFECYCLE_REVIEW.json',lc)
put(G/'BATCH_SPEC.json',dict(at=now(),batch=G.name,source=H,planned_bouts=50,state='AUTHORIZED_STAGED_PREPARE_PENDING',ready=False,started=False,
 authorization=str(G/'USER_NEW50_AUTHORIZATION.json'),display_awake=True,minimum_launch_fps=30,middle_handoff=True,airstrike=True,landing_exit=True,prior_paused_batch_reopened=False))
for src,dst in [('launch_tv_on50.ps1','launch_middle434.ps1'),('start_display_tv_on50.ps1','start_display_middle434.ps1'),('watch_tv_on50_loop.py','watch_middle434_loop.py')]:
 t=rewrite((ROOT/'tmp'/src).read_text(encoding='utf-8')).replace('watch_tv_on50_loop.py','watch_middle434_loop.py')
 (ROOT/'tmp'/dst).write_text(t,encoding='utf-8')
proposal=read(A/'NEW50_PROPOSAL.json');proposal.update(at=now(),authorized=True,state='AUTHORIZED_PREPARING',authorization_receipt=str(G/'USER_NEW50_AUTHORIZATION.json'),
 continuous_plan_sha256=sha(G/'CONTINUOUS_PLAN.json'),trial_config_sha256=sha(G/'TRIAL_CONFIG_DRAFT.json'));put(A/'NEW50_PROPOSAL.json',proposal)
audit=dict(at=now(),delivery=435,disposition='nonblocking supplementary post-run audit accepted; no source/flag change',source=H,
 notes=['User all50-without-protect criterion and wins/HP remain primary; trigger audit supplements outcomes',
 'k>=26 alone cannot prove incremental D attribution; inspect source actor/run and old late conditions, label candidates if flag not exported',
 'Match receivers within existing4-frame game-clock handoff window, not just ready frame',
 'ready is eligibility event, not executable admission/press/real hit; expired is expected0 not asserted impossible',
 'Separate ready -> receiver -> press -> real Slam0 hit+bounce -> abort -> subsequent HP; deduplicate overlapping90f losses',
 '11/22 historical group may shrink just because ownership label changes; keep all ready events as denominator',
 'No fixed +-3/4 wins uncertainty bound or max3 preventable events established; descriptive only'],new_task=False,new_wake=False)
put(B/'analysis/committed388_20261111/REVIEW435.json',audit);put(G/'D_EVENT_AUDIT_PLAN.json',audit)
s.update(at=now(),phase='MIDDLE434_NEW50_AUTHORIZED_STAGING',last_scanned_opus=435,opus435_receipt=str(B/'analysis/committed388_20261111/REVIEW435.json'),
 authorized_batch=G.name,authorized_bouts=50,new50_authorized=True,live_paused_by_user=False,live_pause_released_only_for_batch=G.name,
 pending_user=None,next_phase='Finish preparation, bounded display hold, startup>=30FPS and original gates thenGO automatically; one fresh50 only.',
 middle434_authorization_consumed=False)
put(B/'sol/STATUS.json',s)
q=B/'sol/TO_OPUS.md';t=q.read_text(encoding='utf-8');head='# Sol → Opus 留言队列\n\n';note='''## #435补充核收；用户已授权新MH50，Sol准备开跑（信息，不新派工/不唤醒）

补充作为赛后事件审计接受，不阻挡、不给这批加码。仍保留用户全50不保护的主要验收及每局胜负/HP。ready不等于接管/出刀/真弹起，k>=26不单独当D因果证明；按实际run/源身份和原HO4帧窗口查，标候选/未知，重叠90f损血去重，不因属主变化误报消除缺陷。噪声正负3/4、最多接3例只作粗估，不能当置信界或收益上限。

当前Sol真实回复call_18e09a8d8f5f483180836394fe7c0711选“开始预热并连打新50盘（推荐）”，已为w13_50_middle_handoff434_20261114绑定8e34fb6c、MH1、同50种子/同游戏录像、2HP续/运行故障停、临时常亮和30FPS启动门，只这一批。Sol接实际调度，不另确认，不重开旧批；运行期间你只读收信，不做大计算/改源。正式结果后再排下一项。本信无新Opus任务、不发wake。

---

''';assert t.startswith(head);q.write_text(head+note+t[len(head):],encoding='utf-8')
p=ROOT/'docs/plans/forum_clapper_plan.md';t=p.read_text(encoding='utf-8');t+='\n\n### 7.372 #435非阻挡赛后口径核收，用户授权MH新50（11-14）\n\n#435不改源/开关、不拦开跑；ready分母、HO4帧实际接管、真下劈弹起、退出后风险/90帧HP去重追加审计，不用k>=26单独归因，不以属主分类减少当救血；主验收仍全50无保护及每局结果。用户当前call_18e09a8d8f5f483180836394fe7c0711实际选“开始预热并连打新50盘（推荐）”，新批w13_50_middle_handoff434_20261114固定8e34fb6c/MH1，其他及50种子沿用d7；源审/有限P已结、授权原文与合同独立绑定。当前只做准备、临时常亮和启动>=30FPS，原实机/录像/资源门过后直接GO，不再额外确认；2HP保护续满、运行故障停、旧批不续/AA原件保持。REVIEW435及D_EVENT_AUDIT_PLAN留存，Opus本包无新任务/唤醒，实机期间只读收信。\n';p.write_text(t,encoding='utf-8')
print(json.dumps(dict(batch=G.name,source=H,authorized50=True,actual_question_item=QID,game_started=False)))
