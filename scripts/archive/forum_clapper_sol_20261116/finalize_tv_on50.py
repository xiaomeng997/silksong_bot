from pathlib import Path
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import hashlib,json,psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');G=B/'analysis/w13_50_air_catch429_tv_on_20261114';D=B/'sol/demos'/G.name
R=B/'analysis/committed388_20261111';ROOT=Path('C:/modeling/silksong_bot');A=B/'analysis/air_catch428_20261114'
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();now=datetime.now(timezone.utc).isoformat()
def put(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
result=read(G/'ROOT_50_RESULT.json');clean=read(G/'ROOT_CLEANUP.json');ver=read(G/'ACTUAL_VERSION_AUDIT.json');gc=read(G/'RUNTIME_GC_AUDIT.json');video=read(G/'VIDEO_RECEIPT.json')
base=read(B/'analysis/w13_50_landing425_20261114/ROOT_50_RESULT.json');hold=read(G/'DISPLAY_HOLD_CLOSED.json');cad=read(G/'STARTUP_CADENCE_GATE.json')
assert result['complete'] and result['bouts']==50 and clean['runtime_batch_complete'] and not result['mixed_source']
assert ver['all_actual_switches_verified'] and gc['actual_quiet_collections']==50 and gc['generation2_in_combat']==0
assert video['ffprobe_verified'] and video['encoder_returncode']==0 and hold['released'] and not hold['error'] and cad['passed']
s=read(B/'sol/STATUS.json');assert not s['live_or_budget_running'] and not s['own_live_session']
for x in s['own_offline_jobs']:
 try:assert abs(psutil.Process(x['pid']).create_time()-x['created'])>.01
 except psutil.NoSuchProcess:pass
assert [x['seed'] for x in result['rows']]==[x['seed'] for x in base['rows']]
paired=[dict(bout=n['bout'],seed=n['seed'],old_pass=o['criterion_pass'],new_pass=n['criterion_pass'],old_HP=o['loss_hp'],new_HP=n['loss_hp'],HP_delta=n['loss_hp']-o['loss_hp']) for o,n in zip(base['rows'],result['rows'])]
comparison=dict(at=now,same_seeds=True,old_source=base['current_source'],new_source=result['current_source'],
 old_pass=base['pass_bouts'],new_pass=result['pass_bouts'],old_HP=base['loss_HP_total'],new_HP=result['loss_HP_total'],
 old_hitless=len(base['hitless_whole_bouts']),new_hitless=len(result['hitless_whole_bouts']),
 old_protects=base['protected_quit_bouts'],new_protects=result['protected_quit_bouts'],
 gained_bouts=[x['bout'] for x in paired if x['new_pass'] and not x['old_pass']],
 lost_bouts=[x['bout'] for x in paired if x['old_pass'] and not x['new_pass']],rows=paired,
 limitation='Single same-seed descriptive batch; changed trajectories and runtime scheduling do not prove a stable causal win-rate gain.')
put(G/'PAIRED_LANDING425_COMPARISON.json',comparison)
ver.update(airstrike_enabled_all50=True,airstrike_binding='ssbot.combat.claw_strike.AIRSTRIKE');put(G/'ACTUAL_VERSION_AUDIT.json',ver)
summary=dict(at=now,batch=G.name,source=result['current_source'],authorized_attempts=50,actual_attempts=50,completed_bouts=50,
 authorization_consumed=True,another_batch_authorized=False,source_default_airstrike=False,batch_actual_airstrike=True,
 pass_bouts=result['pass_bouts'],pass_rate=result['pass_bouts']/50,protected_quit_bouts=result['protected_quit_bouts'],
 both_killed=result['both_killed'],hitless_bouts=result['hitless_whole_bouts'],HP=result['loss_HP_total'],deaths=result['real_deaths'],runtime_faults=0,
 full50_no_protect_criterion=result['criterion_pass'],physical_cleanup=True,actual_owned_exited=len(clean['actual_owned_processes_exited']),
 source_files=clean['runtime_files_unchanged'],prerequisites=clean['prerequisites_unchanged'],
 all50_versions_and_switches_verified=True,display_hold_released=True,startup_fps=cad['fps'],
 gen2_in_combat=0,video=video,comparison=str(G/'PAIRED_LANDING425_COMPARISON.json'),
 evidence={str(p):sha(p) for p in [G/'ROOT_50_RESULT.json',G/'ROOT_CLEANUP.json',G/'RAW_AUDIT_COMPLETION.json',G/'ACTUAL_VERSION_AUDIT.json',G/'RUNTIME_GC_AUDIT.json',G/'VIDEO_RECEIPT.json',G/'SEGMENT_RESULT.json',G/'PAIRED_LANDING425_COMPARISON.json',G/'STARTUP_CADENCE_GATE.json',G/'DISPLAY_HOLD_CLOSED.json']})
put(G/'BATCH_FINAL.json',summary)
spec=read(G/'BATCH_SPEC.json');spec.update(state='COMPLETED50_AUDITED_TARGET_NOT_MET',ready=False,started=True,completed=True,
 attempted=50,completed_bouts=50,pass_bouts=result['pass_bouts'],protected_quit_bouts=result['protected_quit_bouts'],
 loss_HP_total=result['loss_HP_total'],authorization_consumed=True,source_mixed=False,display_request_released=True,updated_at=now);put(G/'BATCH_SPEC.json',spec)
dispatch=dict(at=now,source=result['current_source'],actual_bouts=50,completed=True,all_raw_audits_complete=True,
 physical_cleanup=True,final=str(G/'BATCH_FINAL.json'),video=video['video'],reply_seq=369,
 mail_written=True,wake_enqueued=False,listener_received=False,actual_author_start_verified=False,
 next_scope='Offline real air-catch audit and minimal single-monster no-landing design only; no code or game')
put(R/'RECEIPT429_TV_ON50.json',dispatch)
s.update(at=now,phase='TV_ON50_COMPLETE_AUDITED_PAUSED',own_offline_jobs=[],live_or_budget_running=False,
 own_live_session=None,live_paused_by_user=True,live_pause_released_only_for_batch=None,
 live_tv_on50_authorization_consumed=True,verified=50,attempted=50,batch_complete=True,
 pass_bouts=result['pass_bouts'],both_killed=result['both_killed'],protected_quit_bouts=result['protected_quit_bouts'],
 combat_criterion_pass=result['criterion_pass'],current_source=result['current_source'],source_review_pending=False,
 pending_opus='seq369 real air-catch audit and minimal single-monster no-landing design; code/game not yet authorized',
 live_tv_on50_final=str(G/'BATCH_FINAL.json'),live_tv_on50_video=video['video'],cleanup_verified_at=now,
 next_phase='Opus offline evidence and bounded no-landing design; Sol reviews before implementation. One fresh50 fully consumed, no extra game.',
 active_implementation=dict(owner='Opus next offline analysis/design',scope='Conditional single-monster no-landing next step',stage='Design preparation only, awaiting author receipt',formal_delivery_pending=True,coordination_seq=369))
put(B/'sol/STATUS.json',s)
mail='''## seq369（电视开机后新50完整完成）：37达标/13保护/14无伤/144HP；先核实际连踩并做单怪不落地最小方案

用户当前Sol聊天实际说“电视打开了 继续”，承接此前允许常亮/新50及“你测完手里的50盘，如果效果好的话加个不落地”。新批w13_50_air_catch429_tv_on_20261114，d7cbe1a5，AS1/出口1/WALK_RULE1/RUNE_EXIT_FINAL1/B13/B13B1/SLAM_NO_NEW_GLIDE0，和landing425/runtime354同50种子同序。电视物理打开后启动42.6817fps，30fps门通过，11-14 PST16:44:30实际GO、17:24:49正常结束，同游戏连续50并全程录像。旧428故障1盘、429亮屏取消0盘都排除，不续旧批，不混入本批。

50逐盘原始审计完整：**37/50达标（74%）、37杀双怪，13次真实Q1保护、无杀后保护，14无伤，总144HP，0死/0运行故障**。无伤6/10/12/16/18/19/20/22/27/28/31/34/41/45。前30=23达标/7保护/80HP，后20=14/6/64HP。对照上批a81 landing425：36/50、14保护、10无伤、157HP。净多1达标、少13HP（8.3%）、多4无伤，是小幅正向，不能写大幅改善/稳定胜率提升；原50全不保护门槛仍未通过。

版本/运行：50manifest同d7且实际AS开，所有实际关键开关、728源/39先决保持；18自有进程真实退出（含常亮及监看两对redirector/实进程），Prefs/golden/旧DEMO恢复，常亮显式释放，无外来进程隔离/系统服务设置。50局前quietGC，gen2总52/战斗处理窗内0，gen0/1仍开；107952拍p50/p99=13.27335/22.688731ms、max55.9655、24144超16.67，不签全域调度。RSS首743215104→末worker1013551104字节。原录像40:52.6、58862帧/24fps/h264、encoder0/ffprobe核，未改原件。

请先复用已有日志工具做一个有界的下一包：
1. 核本批实际新空中接锤入口/接管/出刀/命中/主动拒绝与交还，区分只有候选/发键/模型预期和真实ev命中。把保护失败及主要损血对到进入前的选择/接管，不只看挨打一帧；统计单怪阶段的掉血、落地机会及实际受益空间。与上批同种子只作描述性配对，不把全部13HP差都归给连踩；不要为凑收益把机会当已救HP。
2. 按用户有小幅改善后想加“不落地”的方向，先在唯一设计forum_clapper_committed_chain.md原位提出**仅单怪**最小方案。明确“不落地”是可安全续踩时优先还是绝不落地、当前冲锤入口已有覆盖、其它招/待机/接不上/符文墙角时如何处理、谁控键、何时退出；标出还需要用户定的语义，推荐最少规则的安全范围。先从本批实际单怪记录提正反例，别预设要覆盖四招整场或顺手改双怪/L2架构。用户条件的效果仅小幅，不当已放行任意扩大功能。

本轮**只读分析和设计先回，暂不改控制码，不扩模型矩阵/P或开任何游戏**。完成后Sol审核最小方案并给用户看再定实现范围；后续若落地由你继续独占实现。不是让你先写大一统空战控制器。不要为了统计重跑50或重复已过87/701；优先实际高频缺陷和能便宜实现的规则。数据显示单怪不落地收益不足或有冲突要如实说，不硬开工。

G=analysis/w13_50_air_catch429_tv_on_20261114：ROOT_50_RESULT/audits/MEASUREMENT_eN、ACTUAL_VERSION_AUDIT、RUNTIME_GC_AUDIT、VIDEO_RECEIPT、SEGMENT_RESULT、PAIRED_LANDING425_COMPARISON、BATCH_FINAL、ROOT_CLEANUP。D=sol/demos/同名，原run/rec/chain/measurement和D/w13.mp4。POSTPROCESSING_PATH_BINDING说明Root审计副本只改路径/最新baseline，合同绑定原脚本未改。电视开启的这50运行正常支持启动显示条件的重要性，不单凭此宣称唯一驱动机制已证明，不追加显示研究。

当前源仍d7、AS生产默认0、游戏暂停，own_jobs空、授权50全用完，无新局/探针/续停止批权限；冻结AA和原录制保持。写信/原单次信号/实收/实际开工/正式交付分开核，请完成后TO_SOL+原单次通知唤醒本聊天。下一步明确归你做上述离线分析/唯一方案，Sol不重复实现或另派其它聊天。

---

'''
p=B/'sol/TO_OPUS.md';text=p.read_text(encoding='utf-8-sig');head='# Sol → Opus 留言队列\n\n';assert text.startswith(head) and '## seq369' not in text
p.write_text(head+mail+text[len(head):],encoding='utf-8')
gains=comparison['gained_bouts'];losses=comparison['lost_bouts']
p=ROOT/'docs/plans/forum_clapper_plan.md';text=p.read_text(encoding='utf-8-sig');assert '### 7.366 ' not in text
p.write_text(text+f'''

### 7.366 电视打开后新50完整核收：37达标/13保护，144HP；seq369先做单怪不落地最小设计（11-14）

当前聊天明确“电视打开了 继续”，新w13_50_air_catch429_tv_on_20261114，同d7/AS1/出口1及上一批完整配置、同50种子，启动42.6817fps通过30fps门。PST16:44:30GO、17:24:49正常结束，同游戏/录像；旧故障1盘和取消0盘未混入、未续。全50原始审计：37杀双怪且37达标（74%）、13真实Q1保护、无杀后保护，14无伤、144HP、0死/运行故障。前30=23/7/80HP，后20=14/6/64HP。较a81上批36达标/14保护/10无伤/157HP，净+1达标、−13HP，多4无伤，小幅改善、不当稳定显著增益；原50全无保护门槛未过。同种子增{{gains}}、减{{losses}}。

50manifest实际d7/AS开启等全部关键开关核实，728源/39先决保持；18进程真实退出，常亮释放、Prefs/golden/旧DEMO恢复。quietGC50，gen2总52/战斗处理窗0；107952拍p50/p99=13.27335/22.688731ms、max55.9655，非全域调度通过。录像40:52.6、58862帧/24fps/h264，encoder0/ffprobe，原件未动。BATCH_FINAL、ROOT_50_RESULT、RAW_AUDIT_COMPLETION、ACTUAL_VERSION_AUDIT、RUNTIME_GC_AUDIT、VIDEO_RECEIPT、SEGMENT_RESULT、PAIRED_LANDING425_COMPARISON及RECEIPT429_TV_ON50登记；审计副本路径/baseline改动留POSTPROCESSING_PATH_BINDING，原合同脚本未改。

依用户“50后效果好加不落地”，小幅正向后先交Opus有界实际连踩/单怪损血分析与唯一设计中的仅单怪最小方案，区分安全续踩偏好/绝不落地等未定语义、既有冲锤覆盖/其它招/符文墙角/退出/主控；优先用本批实际正反例。只读设计先回给Sol/用户看，不先改码、不扩双怪/L2架构/矩阵/P/新游戏，不硬凑收益。seq369写信/单次信号/实收/开工/交付分核。current仍d7、source审结保持，默认AS0、游戏暂停、own_jobs空，授权50已全用完。旧批/AA/原录制保持。
'''.replace('{gains}',str(gains)).replace('{losses}',str(losses)),encoding='utf-8')
(G/'RESULTS_FOR_USER.md').write_text(f'''# 本批50盘结果\n\n同版d7cbe1a5，连踩开启；37/50达标（74%），13盘保护退出，14盘无伤，总掉血144HP，0死亡和运行故障。上批36/50、157HP；本次小幅改善，原50全无保护门槛未过。\n\n18个自有进程退出，临时常亮释放，设置恢复。\n\n[完整录像40:53]({video['video']})\n\nseq369交Opus先做实际连踩/单怪损血核查与单怪不落地最小设计，暂不写码或开新游戏。\n''',encoding='utf-8')
print(json.dumps(dict(complete=True,bouts=50,pass_bouts=result['pass_bouts'],protects=result['protected_quit_bouts'],HP=result['loss_HP_total'],hitless=len(result['hitless_whole_bouts']),old_pass=base['pass_bouts'],old_HP=base['loss_HP_total'],video=video['duration_display'],gained=gains,lost=losses,seq=369,mail_written=True,wake_enqueued=False),ensure_ascii=False))
