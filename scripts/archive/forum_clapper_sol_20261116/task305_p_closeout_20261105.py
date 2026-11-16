from pathlib import Path
import datetime as dt,json,os,subprocess
M=Path('C:/modeling/silksong_bot');W=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');TV=Path('C:/Users/Meng/.codex/worktrees/forum-tv-prep/silksong_bot')
B=Path('C:/ssbot/data/m2_play/clapper_plan');R=B/'analysis/task179_5df8711e_20261105';S='5df8711ea04accff8c03e87560d31b53b2e87a09';GIT='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe';REL='docs/plans/forum_clapper_plan.md'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def git(root,*args):return subprocess.check_output([GIT,'-C',str(root),*args],text=True,encoding='utf-8').strip()
def atomic(p,b):
 t=p.with_name(p.name+'.p305.tmp');t.write_bytes(b);os.replace(t,p)
def writej(p,d):atomic(p,(json.dumps(d,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
status=read(B/'sol/STATUS.json');p=read(R/'p_v2/ROOT_P_AUDIT.json');now=dt.datetime.now(dt.timezone.utc).isoformat()
assert not status['live_or_budget_running'] and not status.get('own_offline_jobs')
assert p['integrity_pass'] and p['critical_point_pass'] and p['actual_cleanup']['cleanup_verified']
assert sum(v['ticks'] for v in p['contexts'].values())==135
assert git(W,'log','-1','--format=%H','--','brain/ssbot')==S
for root in (M,W,TV):assert not git(root,'status','--porcelain','--untracked-files=no')
raw=(M/REL).read_bytes();assert all((r/REL).read_bytes()==raw for r in (W,TV))
lines=raw.decode('utf-8').splitlines();assert '当前进度（11-05，7.172）' in lines[2]
lines[2]='2026-10-27 起草（历史审阅与阶段规格保留）。**当前进度（11-05，7.173）：305新源5df的两个连续窗口正式P共135完整拍已核，实际运行/功能断言/源/trace/签名及真实清理通过，首J12.4689ms/出刀12.4286ms在原有限点内。撤离/ordinary有超点，按完整串行接收时间线，L2尾段有3包晚1与1跳帧；单拍历史lag压力使2679换向、2761撤离及2765冲刺晚1。只补这些有限迟应用/后继边界，不为超点盲加优化、不放行新游戏。原Defender资源拒测0tick已核销保留，未操作系统进程。**'
section='''

#### #305正式P135完整拍/真实清理已核；只补撤离发键与串行尾段有限迟应用（11-05，进度7.173）

固定executor_v1本体hash58ddebd9...未改。当前源5df/入口1b839e8b...匹配startup-only，真实worker61952及场worker均ready/close、0测量tick，finalize核清。第一次正式尝试p_v1在Defender/MsMpEng5688占1.2128核被原资源门拒绝，0场景/0测量tick；原EXECUTION/RESOURCE/FINALIZED保留，属于资源条件，不是控制性能失败。未操作/豁免系统进程。等待后只读重采无blockers，才在全新p_v2用同一case/预检测量；原独占/5s静止/30s pulse/资源门照旧。

实际Pworker58240，场worker62116/60972，同profile串行L12673..2735共63、L22759..2830共72，合计135实际完整调用，全部协议2 trace完整/0overflow、0异常/外来/新签名，当前710hash与实际加载源同，send_clock_required真；实际P0–15/High/Numba4/GetProcessInformation EcoQoSoff。路由断言L1的2679slam/R、2699slam/J、2720slam/A+D和L2的2761真实dash扫描拒绝→最终plan/L均通过，未强制回旧脚本。原manifest false只三项未请求analysis accounting字段，原false保持，不能代替现场完整清单。FINALIZED核实际worker/两场及所有环境恢复后STATUSfalse/无活动锁。

L1整tick峰16.8177ms，首J2699=12.4689、出刀2720=12.4286，在原13.550338ms有限点内；首次提前交还2679=16.4176。L2峰21.7069ms（ordinary2804），首次撤离2761=18.7633、真实左dash2765=16.4695，多处ordinary超过有限点照录，不只选链拍报预算。额外计算仍需同完整后继排队核，不以关键两拍通过宣布整预算通过。原source/P严格无hit/modelhurt以及录制敌人/合成英雄/HF/receive限制保留，实际伤后NPC可能停表的尾段也不作新路线安全证明。

Root按当前P全部中间tick_start/send_done/tick_end、旧实机真实接收双锚、reserve1ms和忙时latestSTATE独立算串行：L1 idle_p99情景0晚/0跳；L2同情景2822/23/24三个J包晚1、跳过2825，不能仅因J相同就豁免（2821是R+J，2822还含松R边沿）。单独让开工承受历史lag15.782995ms，L12679 R及下一R2680晚1；L22761 L晚1并跳2762；L22765 DASH+L及下一J2766晚1并跳2767。它们是导航/撤离真实边沿，与304三个纯重复保持包不同；所有原J/D/ta绝对clock不顺延。ROOT_P_AUDIT保存这些完整实际cost/serial/stress，complete_scheduling_gate仍false，未把待核涂绿。

同179只给Opus一次有限迟应用核：重用既有FIFO/实际HF与前缀及原点，2679 R、2761 L、2765 DASH分别迟1/2（准时基线复用当前P结果），并核L2尾段实际三晚1+2825跳过的合并输入效果/必要后继。保持原2699/2720等绝对时钟，不把neutral当刹车、不把动作回执当命中，不扩全局普通planner优化/新动作/大矩阵。先判功能和必要域，确实不安全或未知给最小取舍，只有证据要求才改源码；无新P/游戏任务，不重复135。主179走路翻越/moving stomp/同iid第二Slam现场仍未覆盖，178原有限验收不变；当前无新game gate，原L1/L2失败/STOP/NO_RETRY保留。
'''
data=('\n'.join(lines).rstrip()+section).encode('utf-8');atomic(M/REL,data);git(M,'add','--',REL);git(M,'commit','-m','docs: record affected P and narrow escape timing follow-up')
heads={str(M):git(M,'rev-parse','HEAD')}
for root in (W,TV):
 atomic(root/REL,data);git(root,'add','--',REL);git(root,'commit','-m','docs: sync affected P and escape timing status');heads[str(root)]=git(root,'rev-parse','HEAD')
status.update(at=now,phase='TASK179_305_FINITE_ESCAPE_TIMING',current_plan='7.173',current_head=heads[str(W)],current_plan_head=heads[str(W)],
 pending_opus='seq224 same179 finite direction/DASH late-input and merged serial-tail check; no source/P/game requested',
 p_receipt=str(R/'p_v2/ROOT_P_AUDIT.json'),p_receipt_task179_5df=str(R/'p_v2/ROOT_P_AUDIT.json'),
 active_blocker='305 P integrity/critical points pass; finite escape edges2679/2761/2765 and L2tail serial late1/skip classification pending. No game gate.',
 next_phase='Opus bounded existing FIFO/HF model effects; source stays static unless evidence requests minimal change',
 next_watch_ready=False,next_trial=None)
writej(B/'sol/STATUS.json',status)
prp=B/'sol/work_packages/task179/PROGRESS.json';pr=read(prp);pr.update(at=now,source=S,candidate_source=S,current_head=heads[str(W)],
 state='305 source and formal135 integrity/critical points pass; finite escape-edge late-input classification pending',
 source_review_receipt=str(R/'SOURCE_REVIEW.json'),p_directory=str(R/'p_v2'),p_receipt=str(R/'p_v2/ROOT_P_AUDIT.json'),
 performance='135 actual complete ticks, peak L1 16.8177/L2 21.7069; J12.4689/D12.4286; full scheduling pending',
 next='seq224 one finite FIFO/HF check for new retreat direction/dash edges; no blind optimization/no game')
writej(prp,pr)
letter='''## 305正式P135完整拍已核；只补撤离边沿及一个合并尾段的有限迟应用（seq224）

真实P/环境清理已结束，STATUSfalse/ownjobs空/无活动锁。计划7.173已同步，刀口HEAD {head}、运行5df不变，Sol已结束该树文档索引写。你可以在自己E16–23Idle做这个同179有限核，不开新任务/打法，不默认改源。Source_review和新P原件在analysis/task179_5df8711e_20261105/。

固定executor匹配startup/退出核完；p_v1被Defender5688的1.2128核原门拦、0测量tick，已真实finalize，未操作系统进程。等待后资源复采空，p_v2才测到实际worker58240、field62116/60972，两个窗63+72=135完整tick；实际P0–15High/Numba4/EcoQoSoff/send-clock真、0外来/新签名/异常/trace缺漏，当前source/function断言都过，FINALIZED清理true。原false清单仅3个未请求accounting不改。首J2699整12.4689ms/出刀2720整12.4286均过原13.55有限点；L1峰16.8177、2679恢复16.4176，L2峰21.7069/首次撤离2761整18.7633/首左dash2765整16.4695。不要只看新guard时间或关键J/D，把ordinary和后手开销藏掉。

Root已自行复算完整串行，不需你再造计时模型：p_v2/ROOT_P_AUDIT.json每context有实际over_point、key_ticks HF/prefix、serial与isolated_lag_p99。全cost+原实际receive+latestSTATE+双锚/reserve，p99空闲开工1.292ms时L1全准时无跳，L2在2822/23/24晚1、跳2825。这里2821是R+J，2822起J还包括松R边沿，别直接说全是相同J。单独历史lag15.782995压力：L12679R和2680R晚1；L22761L晚1/跳2762；L22765 DASH+L和下一J2766晚1/跳2767。完整P时序与输入门仍待此有限分类，不改已核原JSON布尔涂绿。

你只做这些输入对功能/必要后继的影响：沿现成replay_late304/n2604 FIFO和真实S0/HF/在途prefix，2679R、2761L、2765DASH各迟1/2（准时基线复用新P，别重复E0或135正式P）；按实际合并serial schedule核L2尾段2822–24晚1加2825跳过的锁存/方向变化，必要时一条合并闭环，不扩笛卡尔积。原J2699/D2720/ta和所有已经发送的绝对键不顺延。根因是新方向/冲刺边沿需要有限Opt1迟到证明，不是所有ordinary>13.55都必须优化。先判断是否真需加代码；无法判/不安全给精确最小取舍，不放宽门或全局重做planner。

当前功能核仅条件英雄/HF/录制NPC，旧实机在2801已受伤退出，所以后面NPC可能停表；不能用模型尾段无伤签真实安全。新Macro撤离后的forced/n_safe0也要如实保留，不把它改称安全路径。实际是否正确撤离仍待此门核后新条件有界实机。主179翻越/移动踩头与同iid第二Slam仍未现场覆盖，178有限验收不变；旧L1/L2不重开。source保持5df静止，只有明确证据要求才提必要改动；无新P/游戏任务，不扩大air_direct/动作池。完成或实质阻挡一次合包交付/唤醒，无ACK，原STOP/Opt1/首损/资源/核心进程与真实清理门不变。

'''.format(head=heads[str(W)])
mail=B/'sol/TO_OPUS.md';atomic(mail,(letter+mail.read_text(encoding='utf-8-sig')).encode('utf-8'))
writej(B/'sol/OPUS_WAKE.json',{'seq':224,'at':now,'task':179,'note':'305 formal135 integrity/critical points pass, actualcleanup complete. Only finite FIFO/HF escape edges2679R/2761L/2765DASH late1/2 plus merged L2tail serial late/skip effects. No blind source/P/game/newtactic; one delivery.'})
writej(R/'PLAN_SYNC_P_RESULT.json',{'at':now,'plan':'7.173','heads':heads,'source':S,'seq':224,'new_game_gate':False})
print(json.dumps({'plan':'7.173','heads':heads,'seq':224,'source':S,'exclusive':False,'new_game_gate':False},ensure_ascii=False))
