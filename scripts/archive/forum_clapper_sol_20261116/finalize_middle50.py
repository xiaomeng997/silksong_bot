from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,psutil

B=Path('C:/ssbot/data/m2_play/clapper_plan');G=B/'analysis/w13_50_middle_handoff434_20261114';D=B/'sol/demos'/G.name
A=B/'analysis/middle_handoff434_20261114';R=B/'analysis/committed388_20261111';PREV=B/'analysis/w13_50_air_catch429_tv_on_20261114'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'));sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
now=datetime.now(timezone.utc).isoformat()
def put(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
result=read(G/'ROOT_50_RESULT.json');clean=read(G/'ROOT_CLEANUP.json');ver=read(G/'ACTUAL_VERSION_AUDIT.json');gc=read(G/'RUNTIME_GC_AUDIT.json');video=read(G/'VIDEO_RECEIPT.json');base=read(PREV/'ROOT_50_RESULT.json')
assert clean['complete'] and clean['runtime_batch_complete'] and result['complete'] and not result['mixed_source']
assert ver['all_actual_switches_verified'] and all(r['middle_handoff'] for r in ver['rows'])
assert gc['actual_quiet_collections']==50 and gc['generation2_in_combat']==0
hold=read(G/'DISPLAY_HOLD_CLOSED.json');assert hold['released'] and not hold['error']
assert video['ffprobe_verified'] and video['encoder_returncode']==0
s=read(B/'sol/STATUS.json');assert not s['live_or_budget_running'] and not s['own_live_session']
for x in s['own_offline_jobs']:
 try:assert abs(psutil.Process(x['pid']).create_time()-x['created'])>.01
 except psutil.NoSuchProcess:pass
assert [x['seed'] for x in result['rows']]==[x['seed'] for x in base['rows']]
paired=[dict(bout=n['bout'],seed=n['seed'],old_pass=o['criterion_pass'],new_pass=n['criterion_pass'],old_HP=o['loss_hp'],new_HP=n['loss_hp'],HP_delta=n['loss_hp']-o['loss_hp']) for o,n in zip(base['rows'],result['rows'])]
comparison=dict(at=now,same_seeds=True,old_source=base['current_source'],new_source=result['current_source'],old_pass=base['pass_bouts'],new_pass=result['pass_bouts'],
 old_HP=base['loss_HP_total'],new_HP=result['loss_HP_total'],old_hitless=len(base['hitless_whole_bouts']),new_hitless=len(result['hitless_whole_bouts']),
 old_protects=base['protected_quit_bouts'],new_protects=result['protected_quit_bouts'],gained_bouts=[x['bout'] for x in paired if x['new_pass'] and not x['old_pass']],
 lost_bouts=[x['bout'] for x in paired if x['old_pass'] and not x['new_pass']],rows=paired,limitation='One same-seed descriptive batch; not deterministic pairing or causal attribution of aggregate HP to MH.')
put(G/'PAIRED_TV429_COMPARISON.json',comparison)
ready=read(D/'launch/WATCH_READY.json');go=read(D/'launch/WATCH_GO.json')
delay=(datetime.fromisoformat(go['at'])-datetime.fromisoformat(ready['at'])).total_seconds()
put(G/'START_RELEASE_DELAY.json',dict(at=now,ready_at=ready['at'],go_at=go['at'],ready_to_GO_seconds=delay,
 actual_worker_warmup_s=7.7,cause='Sol launched the read-only monitor but omitted the reviewed release.py invocation; later ran all original checks and atomic GO',
 original_video_unchanged=True,not_controller_warmup_delay=True,followup_wrapper='C:/modeling/silksong_bot/tmp/launch_then_release.ps1',
 wrapper_syntax_checked=True,wrapper_runtime_tested=False,note='Use bounded launch-then-reviewed-release pipeline for future newly authorized batches; completed batches refuse relaunch.'))
binding={}
for old,new in [('tmp/audit_tv_on50.py','tmp/audit_middle50.py'),('tmp/summarize_tv_on50.py','tmp/summarize_middle50.py')]:
 binding[new]=dict(original=old,original_sha256=sha(Path('C:/modeling/silksong_bot')/old),copy_sha256=sha(Path('C:/modeling/silksong_bot')/new))
put(G/'POSTPROCESSING_PATH_BINDING.json',dict(at=now,files=binding,changes='Current source/batch paths, latest adjacent d7 baseline, stronger actual MH binding assertion; contract-bound scripts and raw recordings unchanged'))
summary=dict(at=now,batch=G.name,source=result['current_source'],authorized_attempts=50,actual_attempts=50,completed_bouts=50,authorization_consumed=True,
 another_batch_authorized=False,production_default_MH=False,batch_MH=True,pass_bouts=result['pass_bouts'],pass_rate=result['pass_bouts']/50,
 both_killed=result['both_killed'],protected_quit_bouts=result['protected_quit_bouts'],postkill_protected_bouts=result['postkill_protected_quit_bouts'],
 hitless_bouts=result['hitless_whole_bouts'],HP=result['loss_HP_total'],deaths=result['real_deaths'],runtime_faults=0,criterion_pass=result['criterion_pass'],
 all_source_and_switches_verified=True,actual_cleanup=True,video=video,comparison=comparison,
 next_owner='Opus seq373 bounded D event/outcome audit; no code or game before review',
 evidence={str(p):sha(p) for p in [G/'ROOT_50_RESULT.json',G/'ROOT_CLEANUP.json',G/'ACTUAL_VERSION_AUDIT.json',G/'RAW_AUDIT_COMPLETION.json',G/'RUNTIME_GC_AUDIT.json',G/'VIDEO_RECEIPT.json',G/'SEGMENT_RESULT.json',G/'PAIRED_TV429_COMPARISON.json',G/'START_RELEASE_DELAY.json']})
put(G/'BATCH_FINAL.json',summary);put(R/'RECEIPT434_MH50.json',summary)
spec=read(G/'BATCH_SPEC.json');spec.update(state='COMPLETED50_AUDITED_TARGET_NOT_MET',ready=False,started=True,completed=True,criterion_pass=False,
 pass_bouts=result['pass_bouts'],both_killed=result['both_killed'],protected_quit_bouts=result['protected_quit_bouts'],loss_HP_total=result['loss_HP_total'],authorization_consumed=True,display_request_released=True,updated_at=now);put(G/'BATCH_SPEC.json',spec)
proposal=read(A/'NEW50_PROPOSAL.json');proposal.update(state='COMPLETED50_AUTHORIZATION_CONSUMED',game_started=True,completed=True,authorization_consumed=True,final_result=str(G/'BATCH_FINAL.json'));put(A/'NEW50_PROPOSAL.json',proposal)
author=read(G/'USER_NEW50_AUTHORIZATION.json');author.update(started=True,completed=True,actual_attempts=50,authorization_consumed=True,completed_at=now);put(G/'USER_AUTHORIZATION_CONSUMPTION.json',author)
s.update(at=now,phase='MIDDLE434_50_COMPLETE_AUDITED_PAUSED',own_offline_jobs=[],live_or_budget_running=False,own_live_session=None,pending_user=None,
 authorized_batch=None,authorized_bouts=0,new50_authorized=False,live_pause_released_only_for_batch=None,middle434_authorization_consumed=True,
 pending_opus='seq373 actual D ready/late receiver/real hit/abort/loss causal audit; analysis first, no code/game',
 next_phase='Opus bounded D event audit and cheapest next cause proposal; Sol review. Current50 fully consumed, no new game.',
 current_batch=G.name,current_demo=str(D),middle434_final_receipt=str(R/'RECEIPT434_MH50.json'),
 active_implementation=dict(owner='Opus',scope='Actual MH50 event outcomes and bounded next cause',stage='Dispatched, actual start not yet verified',coordination_seq=373))
put(B/'sol/STATUS.json',s)
task=f'''## seq373（MH新50完整核收）：36达标/37双杀/14保护/162HP，先核D实际接手与退出风险，不按总胜场归因

当前Sol实际用户call_18e09a8d8f5f483180836394fe7c0711授权已执行完50盘。新批{G.name}固定8e34fb6c、MH1，其他同d7电视开机那批、同50种子同序；同一游戏全程录像，故障停、2HP续。GO 2026-11-15T05:31:05.538056Z，正常结束06:13:03.818259Z，运行故障/死亡0，未续任何旧停止批。

50逐盘原始审计已全完成（含尾窗）：**37双杀，36/50达标（72%），14次真实保护退出，其中第43盘是双杀后退出；8盘无伤，总162HP**。无伤{result['hitless_whole_bouts']}。相邻d7：37达标/37双杀/13保护/14无伤/144HP，本批少1达标、多18HP、少6无伤；单批结果没有改善，但不能把18HP全归D。首次按attempts粗报37CLEAR/13QUIT，尾窗审计补出第43盘真实Q1；保留两层口径，不把CLEAR当必达标，也别漏尾窗1HP（上一包已遇过）。前30=19达标/11保护/105HP；后20=17达标/3保护/57HP、18双杀。

按你#435及Sol补充，现在下一步归你做**有界只读事件审计/下一项建议**：
1. 复用现成工具/日志，ready/none/expired全计、按本局源A/bounce_f/完成f去重；ready只是资格，不是拿键。把4帧同游戏时钟内B的新run/实际walk或jump持键、按劈、真实Slam0命中+弹起、中途放弃/交回规划器、完成后90帧损血分开。k>=26不能单独证明是D新增，旧LATE/air-entry/旧HO也可能给资格；没有导出run.handoff时如实写可识别候选/未知，不伪造确认。实际候选先列明对应证据和已知门，不为统计改源码。
2. 特别列“D就绪后接走→放弃→之后掉血”，核损血前选择而不是只看撞击帧；对方新招、落地时站位/截止、锁/已发前缀、到出刀的剩余时间。90f窗重叠损血只计一次、归属与关联分开、尾窗保留。历史11/22分组的数因接收属主改变而减少不当已消除问题。
3. 区分D实际新增接住、原来普通起手也能接、没有接手和未知。从实际D接手的坏例/好例选最少代表，先2坏1好或真实数量更少；和d7仅作机会/结果描述，不开全批闭环矩阵，不按预估最多3次或正负3/4胜写统计界。
4. 回一份有限结论：本包是否有明确新增风险/是否有触发收益证据，默认关保持，是否需要同包最便宜的修正，或回第3项下一个最高频便宜原因。源/模型证据不足则保留未验证，不为了赢这轮数据硬改。**本轮只读分析/唯一设计原位状态与最小方案，先回Sol，不写控制码、不扩接口/新招、不P/不游戏。** 用户全50不保护目标未过；这批授权全部消耗。

运行/清理核：50实际manifest均8e34fb6c/MH1及全部关键开关，728运行文件/39先决未变；18自有进程真实退出，Prefs/golden/旧DEMO恢复，registry空、常亮明确释放，无外来进程隔离/系统设置。50quietGC、gen2总52、战斗处理窗0；112399拍p50/p99=13.3027/23.025526ms、max62.0445，非全域预算。录像68243帧/24fps，ffprobe/encoder0，{video['duration_display']}，原件不动。原始审计支持第43盘CLEAR+真实退出的补充尾窗，初始CLI收据保留。

开打前额外待机约5分27秒是Sol漏跑release.py，不是bot预热；后补所有原检查后GO，启动平均49.4588fps。START_RELEASE_DELAY留真实ready/GO和局限；录像前约5分半待机。后续Root新launch_then_release包装把已审的launch→release串起，语法核过但未新增实机测试，旧已结束批拒绝重开。不要拿这段待机解释战斗输赢。

G={G}：ROOT_50_RESULT、audits/MEASUREMENT_eN（含原CLI及补充尾窗）、RAW_AUDIT_COMPLETION、ACTUAL_VERSION_AUDIT、RUNTIME_GC_AUDIT、VIDEO_RECEIPT、SEGMENT_RESULT、PAIRED_TV429_COMPARISON、BATCH_FINAL及ROOT_CLEANUP。D={D}/run为原rec/measurement/chain/attempts，w13.mp4原录像。相邻基线{PREV}。RECEIPT434_MH50全路径绑定，POSTPROCESSING_PATH_BINDING记Root副本只改路径/最新baseline/新增MH实绑校验，合同脚本原件未改。

此任务独占归你，完成TO_SOL+原单次通知本聊天，Sol收到接审。写信、单次信号、实收、实际开工、正式交付分开核；Sol不代发其它聊天、不写Opus目录，不重开已停批、不动冻结AA/原录制。当前游戏/P都已结束，可做上述离线分析。

---

'''
q=B/'sol/TO_OPUS.md';t=q.read_text(encoding='utf-8');head='# Sol → Opus 留言队列\n\n';assert t.startswith(head) and '## seq373（' not in t;q.write_text(head+task+t[len(head):],encoding='utf-8')
receipt=read(R/'RECEIPT434_MH50.json');receipt.update(next_task=373,mail_written=True,wake_enqueued=False,listener_received=False,actual_author_start_verified=False);put(R/'RECEIPT434_MH50.json',receipt)
p=Path('C:/modeling/silksong_bot/docs/plans/forum_clapper_plan.md');t=p.read_text(encoding='utf-8');t+=f'''

### 7.373 MH新50完整核收：36达标/37双杀/14保护/162HP，seq373核D真实事件（11-14）

用户实际授权的一批{G.name}固定8e34fb6c/MH1，其余/种子同相邻d7，05:31:05Z GO、06:13:03Z正常结束。37双杀，其中第43盘杀后真实保护退出，所以达标36/50（72%）、保护14、无伤8、162HP、0死亡/运行故障。原先attempts粗报37CLEAR/13QUIT已用原始尾窗审计补正，不把CLEAR等同达标。相邻d7 37达标/13保护/14无伤/144HP，本批少1达标、多18HP，单批结果未改善，不作D因果断言。前30=19/11/105HP，后20=17/3/57HP（18双杀）；全50无保护目标未过。

50原始审计完成（原CLI/补充尾窗都保留）；50实际manifest H/MH等关键开关核同，728源/39先决保持，18进程真实退出、Prefs/golden/旧DEMO恢复、常亮释放/registry空。quietGC50，gen2总52/战斗窗0；112399拍p50/p99=13.3027/23.025526、max62.0445，不签全域预算。原录像{video['duration_display']}、68243帧/24fps/encoder0/ffprobe，原件未改。开打前额外5分27秒是Sol漏执行release.py，已补所有原门后GO、启动49.46fps；真实延迟原因单列，不伪称预热慢、不归战斗因果；后续launch→release包装语法核过、未增实机测试。

RECEIPT434_MH50/BATCH_FINAL/PAIRED_TV429等登记。seq373交Opus复用日志先做D触发分母、4帧实际接收、真出刀/弹起、放弃后损血去重和最少正反例；k>=26不独作归因，所有实际ready都保留，避免因属主变化假消除历史11/22组。仅分析/唯一设计最小方案先回，无生产/P/新游戏，不夹带开伞/闪身/不落地。默认MH关保持，50授权已消耗，当前暂停；下一步明确归Opus，正式交付后Sol接审。写信/单次/实收/实际开工分核，停止批/AA/原件保持。
''';p.write_text(t,encoding='utf-8')
(G/'RESULTS_FOR_USER.md').write_text(f'50盘完成：36达标，37双杀（第43盘双杀后保护退出），14保护、8无伤、162HP，0死亡/运行故障。\n\n相邻d7：37达标、13保护、14无伤、144HP。本批多18HP，不能单按胜场归因D。\n\n录像：{video["video"]}（{video["duration_display"]}，前约5分半为放行前待机，原件未改）。\n\nseq373：Opus核实际D接手、真命中、放弃后风险；先分析方案、不改控制码。\n',encoding='utf-8')
print(json.dumps(dict(complete=True,bouts=50,pass_bouts=result['pass_bouts'],both_killed=result['both_killed'],protects=result['protected_quit_bouts'],HP=result['loss_HP_total'],hitless=len(result['hitless_whole_bouts']),old_pass=base['pass_bouts'],old_HP=base['loss_HP_total'],gained=comparison['gained_bouts'],lost=comparison['lost_bouts'],video=video['duration_display'],seq=373,mail_written=True,wake_enqueued=False),ensure_ascii=False))
