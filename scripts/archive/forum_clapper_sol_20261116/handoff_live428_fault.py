from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
import json,sys,hashlib
import numpy as np

B=Path('C:/ssbot/data/m2_play/clapper_plan');G=B/'analysis/w13_50_air_catch428_20261114';D=B/'sol/demos'/G.name
A=B/'analysis/air_catch428_20261114';R=B/'analysis/committed388_20261111';ROOT=Path('C:/modeling/silksong_bot')
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'));now=datetime.now(timezone.utc).isoformat()
def put(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
assert read(B/'sol/OPUS_WAKE.json')['seq']==367
cleanup=read(G/'ROOT_CLEANUP.json');assert cleanup['complete'] and not cleanup['runtime_batch_complete']
row=read(D/'run/attempts_i0.jsonl');audit=read(G/'audits/MEASUREMENT_e0.json')
assert row['episode']==0 and row['outcome']=='QUIT' and row['policy']['real_quit']['outcome']=='ALERT'
assert audit['complete'] and audit['metrics']['L']==6
trace=[json.loads(l) for l in (D/'run/measurement_i0_e0.jsonl').open(encoding='utf-8')]
ticks=[x for x in trace if x.get('kind')=='tick'];combat=[x for x in ticks if 510<=x['f']<=548]
sys.path.insert(0,str(A/'source_fixed428/brain'))
from ssbot.record.recorder import RecordingReader
from ssbot.record import formats
states=[]
for _,recv,_,flags,_,payload in RecordingReader(row['recording']).records('state'):
 st=formats.peek(payload,('f','dt','hero','game'),flags)
 if isinstance(st.get('f'),int) and 510<=st['f']<=624:states.append((recv,st))
dts=[st['dt'] for _,st in states if st['f']<=548]
owners=dict(Counter(x['owner'] for x in combat))
assert not any('slam' in owner for owner in owners)
fact=dict(at=now,batch=G.name,source=row['code_rev'],attempted=1,planned=50,completed50=False,
 batch_stopped_no_retry=True,reason=row['reason'],real_quit=row['policy']['real_quit'],
 all14_owned_processes_exited=True,cleanup=str(G/'ROOT_CLEANUP.json'),
 actual_HP_lost=6,losses=audit['metrics']['losses'],measurement_raw_audit_complete=True,
 raw_audit_complete_does_not_mean_runtime_success=True,
 window=audit['window'],raw_recording=row['recording'],video=str(D/'w13.mp4'),
 video_capture_frames=2770,video_encoder_returncode=0,
 actual_GO=read(D/'launch/WATCH_GO.json')['at'],actual_end=read(G/'COORDINATOR_END.json')['at'],
 raw_combat_dt_seconds=dict(min=min(dts),median=float(np.median(dts)),p99=float(np.percentile(dts,99)),max=max(dts)),
 combat_tick_count=len(combat),combat_tick_ms=dict(p50=float(np.median([x['total_tick_ms'] for x in combat])),max=max(x['total_tick_ms'] for x in combat)),
 whole_trace_tick_count=len(ticks),whole_trace_max_ms=max(x['total_tick_ms'] for x in ticks),combat_owners=owners,
 loop_gap_ms_max=row['loop_gap_ms_max'],loop_gaps_250=row['loop_gaps_250'],late_states=row['late_states'],
 quit_scene_at595=next(st['game'] for _,st in states if st['f']==595),
 missing_hero_game_frames=[596,624],
 cause_status='Unknown: actual ~0.263s game/state cadence precedes losses; not attributed to AIRSTRIKE or any named foreign process',
 authority='This batch stopped strictly; no remaining49 restart or additional live probe/new50 authorized',
 user_followup='After completing a valid50, if results good, consider single-monster no-landing; not part of current fault repair')
put(G/'FAULT_HANDOFF.json',fact)
put(G/'ROOT_PARTIAL_RESULT.json',dict(at=now,source=row['code_rev'],attempted=1,planned=50,
 complete=False,runtime_fault=True,successful_protected_quit=False,HP_lost=6,
 aborted_not_a_win_rate_sample=True,raw_audit=str(G/'audits/MEASUREMENT_e0.json'),video=str(D/'w13.mp4'),fault=str(G/'FAULT_HANDOFF.json')))
bs=read(G/'BATCH_SPEC.json');bs.update(state='STOPPED_RUNTIME_FAULT_FIRST_BOUT',ready=False,started=True,completed=False,
 attempted=1,completed_bouts=0,authorization_consumed_for_stopped_batch=True,restart_allowed=False,updated_at=now)
put(G/'BATCH_SPEC.json',bs)
mail='''## seq368（#428新50首盘运行故障）：先查约263ms原始帧节奏和退出未确认；不改连踩/不落地、不续旧批

用户在当前Sol聊天真实选择call_1287eeb16d394511b6ed35526df0a062“授权预热并连打新50盘”，仅新批w13_50_air_catch428_20261114。固定d7cbe1a5，AIRSTRIKE1、沿用上批LANDING_EXIT1、同50种子，原严格停止。前置门/原启动流程通过，19:19:04.980812Z实际GO并ack；19:19:52.149933Z首盘故障结束。实际只尝试1盘，不是完成50，也不续剩余49。

首盘seed314183，f_wake510/end624；原始审计loss6HP：525右怪Slam Collider2、537/548身体，各2HP，HP7→1。real_quit是ALERT（不是已完成真实Q1）：正确选quit/yes、wrong_submits0，但启动退出后10秒未确认主菜单，main_menu false；最后理由叠Q1和Q5“hero lost7363ms”。595原始scene Quit_To_Menu，596到624 hero/game为空，raw audit能标real_quit_unload但这不代表主菜单退出成功。故continuous plan按约定LearningStop；没有放宽为正常2HP继续。

**首要新事实：原始战斗dt中位约0.2630502s，p99约0.267064s，最高0.267602s；非只某个规划长拍。** trace103拍最高28.8594ms，掉血前510–548属主two:open2/plan19/two:idle2/chain3/sup1，没有slam接管。row loop_gap_max334ms、250ms以上94次，late_states0。原始f仍连续更新；wave13已醒，dt一开始就在约263ms。先辨实际游戏渲染/主线程节奏 vs 发布/读取/录制、前后台/窗口/进程调度/Unity帧率设置/显卡或环境；不要未经证据归因连踩、GC、defender或股票进程。原TrainingEnvironment有runInBackground=true，capture是原Windows capture事件流不是PrintWindow（根未改），这两点不能直接排除环境问题。首盘还没测到新增连踩效能，别据6HP判断它变差或无伤。

请继续同一运行问题包：先读原始证据和实际拥有源码，定位最便宜且证据支持的原因，再给具体修复/验证方案；确证代码缺陷可同包离线修复并交固定源/必要测试，Sol续独审。不要通过加大Q1超时/去Q5/吞故障掩盖异常节奏；若是环境/窗口状态则给对应实机前的最小可审检查/处理，不擅改系统服务/驱动/他项目，也不要重跑模型矩阵。新实机探针或新50另由用户明确授权，旧批不能续。当前没有任何额外局数权限。

全证据G=analysis/w13_50_air_catch428_20261114，D=sol/demos/同名：G/FAULT_HANDOFF.json、ROOT_PARTIAL_RESULT.json、ROOT_CLEANUP.json、audits/MEASUREMENT_e0.json、COORDINATOR_END、RELEASE_PRECHECK/ROOT_RESOURCE_PREFLIGHT/ENGINEERING_GATE；D/run原始recording、attempts/measurement_i0_e0.jsonl/manifest/chain/worker cleanup；D/launch/game_logs/player_0.log、WATCH_READY/CAPTURE_READY/cleanup及D/w13.mp4。14实际自有进程已退出、728源/37先决未变、Prefs/golden/旧DEMO恢复，encoder0、2770帧录像保留。没对外国进程做隔离/服务设置。

用户刚补“你测完手里的50盘，如果效果好的话加个不落地”：记为**有效50完成且效果好后才评估的候选**，本次故障没50结果，不先实现、不扩大本包。连踩当前能空中接单怪冲锤，不保证全场不落地。唯一设计只需原位记这个条件，不假定已授权马上做。

current_source仍已审d7，source_review_pending=false；本次是实机运行失败不撤销有限P记录，不签实机效果。游戏暂停、own_jobs空、无新GO。seq368写信/原单次通知/监听/实际分析开工/交付分开核，请完成再TO_SOL+原单次唤醒本聊天。别掉回只确认已读；下一步归你做离线定位/必要同包修复，Sol保留源审与运行门。

---

'''
p=B/'sol/TO_OPUS.md';text=p.read_text(encoding='utf-8-sig');head='# Sol → Opus 留言队列\n\n';assert text.startswith(head) and '## seq368' not in text
p.write_text(head+mail+text[len(head):],encoding='utf-8')
put(G/'FAULT_DISPATCH.json',dict(at=now,seq=368,mail_written=True,wake_enqueued=False,listener_received=False,
 actual_author_start_verified=False,next_owner='Opus offline cause analysis and necessary same-package repair',fault=str(G/'FAULT_HANDOFF.json')))
s=read(B/'sol/STATUS.json');s.update(at=now,phase='LIVE428_STOPPED_FIRST_BOUT_FAULT_CLEANED_PAUSED',
 live_paused_by_user=True,live_or_budget_running=False,own_live_session=None,own_offline_jobs=[],
 live_pause_released_only_for_batch=None,live428_authorization_consumed=True,
 live428_partial_result=str(G/'ROOT_PARTIAL_RESULT.json'),live428_fault=str(G/'FAULT_HANDOFF.json'),
 live428_video=str(D/'w13.mp4'),pending_opus='seq368 first-bout runtime/state-cadence fault; offline cause analysis/necessary repair',
 next_phase='Stopped batch remains stopped. Opus offline cause analysis; Sol source re-review. New live probe or fresh50 requires new explicit user approval.',
 no_landing_followup={'condition':'After valid50 completed and good effect','authorized_now':False,'implementation_pending':False})
put(B/'sol/STATUS.json',s)
p=ROOT/'docs/plans/forum_clapper_plan.md';text=p.read_text(encoding='utf-8-sig');assert '### 7.363 ' not in text
p.write_text(text+'''

### 7.363 用户授权新50，首盘运行故障严格停批；14进程实退，seq368先查帧节奏（11-14）

当前聊天call_1287eeb16d394511b6ed35526df0a062明确“授权预热并连打新50盘”；新批w13_50_air_catch428_20261114固定d7、AIRSTRIKE1及上批LANDING_EXIT1、同50种子，静态/资源/实际输入/录像门通过。19:19:04.980812Z GO/ack，19:19:52.149933Z首盘故障结束，不续剩余49。只尝试1盘、非50完成；7→1HP共6，525锤2/537及548身体各2HP，real_quit ALERT、main_menu false，正确quit/yes后10秒未确认主菜单，叠Q5 hero lost7363ms。raw audit窗口complete与实际退出失败分开，不能把unload当主菜单保护退出成功。

首要证据：战斗原始dt中位0.2630502s/p99约0.267064、最大0.267602；trace103拍最高28.8594ms，受伤前无slam属主，loop_gap_max334ms/250ms以上94次、late_states0。先辨游戏/发布/窗口前后台/调度/环境节奏，不未经证据甩给连踩、GC、defender或他项目。运行/退出四文件生命周期与已验runtime354不变，无额外探针授权。G/FAULT_HANDOFF、ROOT_PARTIAL_RESULT、ROOT_CLEANUP、audits/MEASUREMENT_e0及D全部原录/录像留证。

14自有进程实际退出，728源/37先决未变，Prefs/golden/旧DEMO恢复，encoder0、2770帧录像保留，没有外来隔离。seq368交Opus离线定位与证实代码缺陷时必要同包修复，不放宽Q1/Q5/吞失败，不改系统/他项目，不自动新实机/续旧批。current仍已审d7、有限P结论保留但不签实机效果；游戏暂停恢复，写信/单次通知/监听/开工/交付分核。

用户补充“你测完手里的50盘，如果效果好的话加个不落地”，登记为有效50完成且效果好后评估的候选，本次仅1盘故障不满足条件，不先实现。当前连踩可空中接单怪冲锤，未承诺单怪全场不落地。
''',encoding='utf-8')
print(json.dumps(dict(attempted=1,planned=50,strictly_stopped=True,cleaned_owned=14,HP_lost=6,
 raw_dt_median_s=float(np.median(dts)),combat_owners=owners,seq=368,wake_enqueued=False),ensure_ascii=False))
