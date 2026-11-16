from pathlib import Path
from datetime import datetime,timezone
import copy,hashlib,json,sys

sys.stdout.reconfigure(encoding='utf-8')
B=Path('C:/ssbot/data/m2_play/clapper_plan')
A=B/'analysis/middle_handoff434_20261114';R=B/'analysis/committed388_20261111'
PREV=B/'analysis/w13_50_air_catch429_tv_on_20261114'
G=B/'analysis/w13_50_middle_handoff434_20261114'
H='8e34fb6c71a3338b7652c741b12c5048086c6ae9';PARENT='d7cbe1a59cbee1d8fa8d40c53fc57b3ed1bd2b19'
now=lambda:datetime.now(timezone.utc).isoformat()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=read(A/'ROOT_P_AUDIT.json');review=read(A/'SOURCE_REVIEW_FINAL.json');packet=read(A/'SOURCE_PACKET_FIXED.json')
assert review['accepted'] and p['finite_measurement_valid'] and p['actual_cleanup_verified']
assert p['completion_and_actual_handoff_actions_verified'] and p['source']==H
assert not (B/'sol/performance/ACTIVE.json').exists()
assert not G.exists();G.mkdir()
final=dict(review,at=now(),formal_P_audit=str(A/'ROOT_P_AUDIT.json'),formal_P_completed=True,
           finite_measurement_valid=True,actual_cleanup_verified=True,actual_executor_owned_processes_exited=20,
           bounded_orchestrator_exited=p['bounded_orchestrator_exited'],
           profiles='same source, AS1/LANDING_EXIT1, MH ON/OFF only',
           outputs={k:{n:v for n,v in out.items() if n!='contexts'} for k,out in p['outputs'].items()},
           wire_difference_counts={k:len(v) for k,v in p['wire_differences'].items()},
           performance_budget_pass=False,full_scheduling_gate_pass=False,default_switch_remains_off=True,
           new_game_authorized=False,live_released=False)
put(A/'SOURCE_REVIEW_AND_P_FINAL.json',final)
receipt=dict(final,stage='Source/action/finite P/actual cleanup complete; fresh50 proposal prepared, authorization pending')
put(R/'REVIEW434.json',receipt)
old=read(B/'analysis/air_catch428_20261114/NEW50_PROPOSAL.json')
seeds=read(PREV/'CONTINUOUS_PLAN.json')['seeds'];assert len(seeds)==len(set(seeds))==50
overrides=dict(old['overrides'],SSBOT_FORUM_MIDDLE_HANDOFF='1')
proposal={k:copy.deepcopy(old[k]) for k in ['maximum_attempts','scope','protected_quit','criterion']}
proposal.update(at=now(),batch=G.name,source=H,source_root=packet['source_root'],
                source_packet=str(A/'SOURCE_PACKET_FIXED.json'),source_packet_sha256=sha(A/'SOURCE_PACKET_FIXED.json'),
                source_review=str(A/'SOURCE_REVIEW_AND_P_FINAL.json'),formal_P_audit=str(A/'ROOT_P_AUDIT.json'),
                state='PREPARED_AWAITING_FRESH50_AUTHORIZATION',authorized=False,authorization_receipt=None,
                game_started=False,seeds=seeds,seed_order='same50 as latest TV-on429; compare adjacent d7 version',
                comparison_baseline=str(PREV/'ROOT_50_RESULT.json'),comparison_baseline_source=PARENT,
                configuration='same current AS1/LANDING_EXIT1 continuous-game baseline, add MH=1; one fixed source all50',
                overrides=overrides,prior_batch_authorization_consumed=True,default_switch_remains_off=True,
                preconditions='Only after new approval: current resource/input/exclusivity/capture/readiness/cleanup gates, bounded display lease; startup FPS>=30 before GO.',
                limits='No extra probe, no old batch resume, maximum50; HP<=2 protects each bout and continues, runtime fault stops batch; full video.',
                display='Temporary awake-display request for this batch only; cannot physically switch on a remote-powered-off TV')
def rewrite(v):
    if isinstance(v,str):return v.replace(PREV.name,G.name).replace(PARENT,H).replace(PARENT[:8],H[:8]).replace('AIR_CATCH429_TV_ON50_W13_HP2_CONTINUOUS','MIDDLE_HANDOFF434_W13_HP2_CONTINUOUS')
    if isinstance(v,list):return [rewrite(x) for x in v]
    if isinstance(v,dict):return {k:rewrite(x) for k,x in v.items()}
    return v
plan=rewrite(read(PREV/'CONTINUOUS_PLAN.json'))
plan.update(at=now(),source=H,comparison_baseline_source=PARENT,authorization=None,authorized=False,
            notes='Fresh50 proposed only, auth pending. Same one-game continuous stops/video; new MH=1 only. >=30 startup FPS required. No stopped batch reopened.')
put(G/'CONTINUOUS_PLAN.json',plan)
d=read(PREV/'TRIAL_CONFIG_DRAFT.json')
draft=rewrite({k:d[k] for k in ['environment','arguments','seed','b2','vault','stopping','demonstration','coverage_target','bout_index'] if k in d})
draft['environment']['SSBOT_FORUM_MIDDLE_HANDOFF']='1'
draft.update(at=now(),scope='MIDDLE_HANDOFF434_W13_HP2_CONTINUOUS',source=H,batch_id=G.name,
             user_authorized=False,authorization=None,user_ready_required=True,combat_start_authorization=None,
             purpose='Fresh same50 comparison of normal middle-completion late handoff; source/P accepted, live benefit unknown',
             prepare_game_requires_new_authorization=True)
put(G/'TRIAL_CONFIG_DRAFT.json',draft)
proposal.update(continuous_plan=str(G/'CONTINUOUS_PLAN.json'),continuous_plan_sha256=sha(G/'CONTINUOUS_PLAN.json'),
                trial_config=str(G/'TRIAL_CONFIG_DRAFT.json'),trial_config_sha256=sha(G/'TRIAL_CONFIG_DRAFT.json'))
put(A/'NEW50_PROPOSAL.json',proposal)
put(G/'CANDIDATE_SPEC.json',dict(at=now(),source=H,batch=G.name,planned_bouts=50,
                              authorized=False,source_review=str(A/'SOURCE_REVIEW_AND_P_FINAL.json'),
                              proposal=str(A/'NEW50_PROPOSAL.json'),game_started=False))
s=read(B/'sol/STATUS.json');assert not s['own_offline_jobs'] and not s['live_or_budget_running']
question='D交接修复的源审、三窗正式计时及清理已完成。上一批50盘授权已用完：是否授权预热并连打新的50盘？固定8e34fb6c并开启MH，其余沿用上一批；同一游戏、全程录像，2HP保护后继续收满，运行故障停批。临时保持电视亮屏，启动帧速不足30FPS则在开打前取消。当前游戏未启动。'
s.update(at=now(),phase='MIDDLE434_SOURCE_P_CLEAN_AWAIT_NEW50_AUTH',last_scanned_opus=434,
         source_review_pending=False,pending_opus=None,own_offline_jobs=[],own_live_session=None,live_or_budget_running=False,
         authorized_batch=None,authorized_bouts=0,live_pause_released_only_for_batch=None,new50_authorized=False,
         pending_user=question,next_phase='User fresh50 authorization; proposal/config/seeds/source/recording scope prepared. No game before answer.',
         opus434_receipt=str(R/'REVIEW434.json'),middle434_source_and_P=str(A/'SOURCE_REVIEW_AND_P_FINAL.json'),
         middle434_new50_proposal=str(A/'NEW50_PROPOSAL.json'),middle434_candidate_batch=G.name,
         middle_handoff_production_default=False,active_implementation=dict(owner='Sol',scope='D handoff bounded live validation',stage='Await fresh50 authorization; all independent source/P work complete',formal_delivery_pending=False))
put(B/'sol/STATUS.json',s)
q=B/'sol/TO_OPUS.md';t=q.read_text(encoding='utf-8');head='# Sol → Opus 留言队列\n\n'
note='''## #434正式计时/清理结项：MH三窗370拍有效，待新50授权（信息，无新任务/不唤醒）

源8e34fb6c、AS1/LANDING_EXIT1、仅MH开关；未改已审entry_v4，自发B/模型B+1，零拍check/finalize与measure/finalize两臂均完成。每臂185拍；ON p50/p99=11.5741/17.359576ms，OFF=11.7064/19.971352ms，max约54.7/54.3ms，超16.67为6/8。动作/属主不同，不当孤立helper成本或预算/全域调度通过。

源码728及输入238保持，配置实际绑定、B以后无强制、无新JIT签名、所有动作wire/回执核同；E0/E30开关实际wire全同，E22真完成设锚→slam接管生效（62拍wire不同），ON模型接住一次/OFF没有。英雄模型/敌人回放和后段锤伤局限不变，不推HP或胜率。20执行器自有进程及有限协调器均真实退出，Prefs/golden/旧DEMO恢复，registry空、无游戏。

analysis/middle_handoff434_20261114/ROOT_P_AUDIT、SOURCE_REVIEW_AND_P_FINAL、NEW50_PROPOSAL与REVIEW434已登记。默认MH仍关；新50拟固定此源、只加MH1、沿用最新d7同50种子，独立授权尚未给，当前不启动游戏。无新Opus任务，不再发wake；等这批验收后再按计划择下一原因。

---

'''
assert t.startswith(head) and '## #434正式计时/清理结项：' not in t
q.write_text(head+note+t[len(head):],encoding='utf-8')
pfile=Path('C:/modeling/silksong_bot/docs/plans/forum_clapper_plan.md');t=pfile.read_text(encoding='utf-8');assert '### 7.371 ' not in t
t+='''

### 7.371 #434三窗正式P/实际清理结项，新50配置准备、待独立授权（11-14）

8e34fb6c同源AS1/LANDING_EXIT1仅MH ON/OFF，每臂185拍；未改entry_v4、B自发/B+1英雄模型，两臂零拍check+finalize和measure+finalize实际完成。ON p50/p99=11.5741/17.359576ms、max54.6949、6拍超16.67；OFF=11.7064/19.971352ms、max54.2544、8拍超。动作/属主不同，非孤立helper成本，不签预算或全域调度。E0/E30 wire全同，E22真完成→late slam生效、62拍wire不同；ON模型接触1/OFF0，后段模型与实录不符仍保留，不推HP/胜率。

Root完整核728源/支持文件和238输入未变、实际配置、无测量强制/新JIT、按键回执一致、诊断完整，所有20执行器自有进程及有限协调器真实退出；Prefs/golden/旧DEMO恢复，registry空/无游戏。ROOT_P_AUDIT、SOURCE_REVIEW_AND_P_FINAL和REVIEW434登记。下一步已离线备w13_50_middle_handoff434_20261114连续计划/配置：50同种子、固定此源只加MH1、单游戏全录像、2HP保护后续/故障停、保持临时显示及>=30启动门；proposal authorized=false，游戏未启动，上一批授权用完，待本聊天新的50授权。默认MH仍关。Opus信息结项无新任务/唤醒，未重开任何停止批/AA/原录制。
'''
pfile.write_text(t,encoding='utf-8')
print(json.dumps(dict(source=H,source_and_finite_P_complete=True,actual_cleanup=True,new50_proposal=str(A/'NEW50_PROPOSAL.json'),authorized=False,game_started=False),ensure_ascii=False))
