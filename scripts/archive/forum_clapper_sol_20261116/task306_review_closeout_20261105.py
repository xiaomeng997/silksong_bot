from pathlib import Path
import datetime as dt,json,os,subprocess
M=Path('C:/modeling/silksong_bot');W=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');TV=Path('C:/Users/Meng/.codex/worktrees/forum-tv-prep/silksong_bot')
B=Path('C:/ssbot/data/m2_play/clapper_plan');R=B/'analysis/task179_5df8711e_20261105';S='5df8711ea04accff8c03e87560d31b53b2e87a09';REL='docs/plans/forum_clapper_plan.md';GIT='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def git(root,*args):return subprocess.check_output([GIT,'-C',str(root),*args],text=True,encoding='utf-8').strip()
def atomic(p,data):
 t=p.with_name(p.name+'.306.tmp');t.write_bytes(data);os.replace(t,p)
def writej(p,d):atomic(p,(json.dumps(d,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
now=dt.datetime.now(dt.timezone.utc).isoformat();status=read(B/'sol/STATUS.json')
assert not status['live_or_budget_running'] and not status.get('own_offline_jobs')
assert git(W,'log','-1','--format=%H','--','brain/ssbot')==S
assert read(R/'oracle_input306/ROOT_ORACLE306_MISMATCH.json')['306_latest_wins_claim_rejected']
for root in (M,W,TV):assert not git(root,'status','--porcelain','--untracked-files=no')
astra='''# Astra focused review: Task179 / delivery306

2026-11-05. Existing `astra_task178_pose_review` resumed under the user-authorized gpt-6-astra/xhigh workflow. Read-only focused decision, no source/P/game. Full response is retained in this conversation; this is the resulting scoped disposition.

- Reject the proposed global extra-DASH packet change:306 collapses due ACTIONs to the latest mask before HoldFilter, whereas deployed Oracle queues every edge before one Step. Root bound actual DLL ca7673... and tested its pure HoldFilter: same-frame DASH+L then J leaves DASH|J for two frames.
- Correct only the offline input adapter: ordered due-batch Push/Queue, one Step per dynamic frame. Do not call the single-frame filter once per packet, which would advance age/physics too often. Preserve original306 artifacts.
- The L2763 late1 body-collision example is not erased by the unrelated DASH-model error. Its coalesced packets are repeated L; it occurs before the old live loss2801 and remains a meaningful conditional ordinary-route counterexample.
- Opt1 is the matching-receipt/stop convention, not a theorem that every ordinary trajectory is damage-free under all late1/2 cases (main plan line1324). Do not expand this finite work into a global h2 safety solver or introduce a new late1-immediately-stop rule.
- After corrected finite cases, if only isolated historical-lag ordinary sensitivity remains while the adopted complete serial scenario still sends key retreat edges on time, Sol may bind one new-namespace, firstloss-stopped engineering game under the existing authorization. This is known-risk exploration, not completed scheduling/safety certification. Keep original false audit; issue a separate finite engineering disposition.
- If corrected adopted serial scenario loses an action, violates absolute clocks, or newly forces handback into known current danger, minimally repair that trigger before live. No user re-authorization needed merely for one already-authorized bounded game.
- Next game tests timely refusal/real handback, actual input/actions and retreat outcome. Main179 walking vault, moving stomp and new same-iid Slam each need actual opportunities;0 opportunity remains uncovered. Keep7HP/firstlossQ1/death/key mismatch/>4withoutvalidmatch/criticallogs/resources/actualcleanup; no old stopped-run retry.
'''
p=R/'ASTRA306_REVIEW.md';assert not p.exists();p.write_text(astra,encoding='utf-8')
writej(R/'OPUS306_REVIEW.json',{'at':now,'delivery':306,'source':S,'source_changed':False,'accepted':False,
 'reason':'latest-mask input adapter contradicts actual deployed ordered queue; dash-loss model and globalinput fix proposal rejected',
 'deployed_proof':str(R/'oracle_input306/ROOT_ORACLE306_MISMATCH.json'),'astra_focused_disposition':str(p),
 'retained':'L1 finite legacy clock result and ordinary lateL route sensitivity subject to correct due-batch verification; old306 untouched',
 'next':'same225 data-only corrected dash cases and necessary repeated/tail equivalence; no source/P rerun or newgame until Root reviews',
 'known_risk_policy':'finite engineering may accept isolated stress-only ordinary sensitivity after corrected adopted serial schedule, with original strict stops; not blanket Opt1 injury-free requirement',
 'new_game_gate':False})
raw=(M/REL).read_bytes();assert all((r/REL).read_bytes()==raw for r in (W,TV))
lines=raw.decode('utf-8').splitlines();assert '当前进度（11-05，7.173）' in lines[2]
lines[2]='2026-10-27 起草（历史审阅与阶段规格保留）。**当前进度（11-05，7.174）：306“迟到冲刺被下一包覆盖”结论被Root实际部署DLL证据否决：真实Oracle逐包入队边沿再锁存，离线模型却只取最后掩码。实际DLL纯过滤器同帧DASH+L→J输出DASH|J两帧，不改全局输入层。Opus同225只修数据目录迟到适配、保留旧306；Astra聚焦裁决同意最小修模型，不要求所有ordinary晚1/2均模型无伤。135拍P/源5df不作废，306关键迟到结论尚未核收，当前无新game gate。**'
section='''

#### #306迟到输入模型与已部署Oracle不一致，拒绝假丢冲刺/全局输入补丁；同包修离线模型（11-05，进度7.174）

306报告L12679R晚1/2功能不变、尾部合并锁存不变；L22763L晚1改ordinary路线碰旧怪身体、2767DASH晚1/2“被下一J覆盖”后开伞中锤，提出全局普通dash多保留一包或按已知风险进工程。Root先核owning源码，发现edges306/replay_late304在每帧先选max(arrived)才调用一次HF，实际ActionScheduler却逐个due ACTION依次TryQueueMask，QueuePlain逐边沿Push，最后动态更新Step一次。不能因最后回执只显示J就推早包DASH从未锁存；也不能逐包Step多推进age/物理帧。

Root进一步核实际部署，非拿开发源冒充运行：train/SsOracle.dll SHA ca7673dbeb8f3a061deca742aa0972f585c5284dd5328e8d2378d064509930ac精确同L2实际manifest，ILSpy只反编译三个类型rc0；实际Scheduler108/120、Filter245等确认同样语义。独立自有PowerShell仅调用DLL纯HoldFilter（不创建Plugin/游戏）：Restore(L,L,pending0,age255)，同帧QueuePlain(L,DASH+L)、QueuePlain(DASH+L,J)，dashpending2；随后Step(J)三次实际输出[5,5,1]，即DASH|J保持2帧。证据analysis/task179_5df8711e_20261105/oracle_input306/含部署hash、反编译文件和ROOT_ORACLE306_MISMATCH。故306该丢失结论及据此全局多发DASH方案不成立；不改运行源/Oracle/全局输入层，不碰Windows核心进程。

按用户workflow复用原gpt-6-astra/xhigh代理做本关键实验门聚焦裁决，结果ASTRA306_REVIEW。认可先仅修离线due-batch Push→单Step，保留旧306工件；DASH+J同帧仍可能改变行为，不能从“不丢DASH”跳到无伤。L2763晚1合并的原本是重复L，不能顺带撤销其旧首损2801前的条件模型身体碰撞。Opt1是相符应用回执/停止口径，不是所有ordinary晚1/2都应模型无伤的全局定理；原forced/n_safe0、未知风险继续披露，不扩h2全知安全求解，也不新增晚1立即停。

同seq225交Opus唯一离线实现owner，复用现成key_guard.Filter或等价已核逐边沿镜像，严格真实22键/HF/前缀，重点更正DASH晚1/2及必要后继、核重复L/R/尾段是否等价，不重复135P/820大套件。运行源5df和成本/准时基线不因离线迟到模型错误自动作废；已核304纯重复保持项与无同帧冲突的准时串行也不扩大撤销。原ROOT_P_AUDIT complete_scheduling_gate=false及306旧结果均保留，新收据逐项注明受影响与不受影响。

Root采纳聚焦裁决的有界工程准则：待更正工件核收，若只剩孤立历史极端lag下的ordinary路线敏感，且采用的完整串行情景仍支持关键撤离边沿准时，可另外绑定一个新namespace/单局/7HP首损Q1的已知风险工程，目的仅验守卫及时拒绝/真实交还、输入动作对应和实际撤离；不是安全认证、不是179完成。若更正后的采用串行情景真丢关键动作/错绝对clock或必然交还进当前已知危险，则先局部修该触发点，不靠风险标签绕门。原死亡/期望键不符/>4无有效匹配/关键STATE与HP日志/资源/真实清理及旧NO_RETRY保持。此刻更正仍待核，当前无新game gate；179翻越/移动踩头/同iid第二锤各需真实机会，178原有限验收不变。
'''
data=('\n'.join(lines).rstrip()+section).encode('utf-8');atomic(M/REL,data);git(M,'add','--',REL);git(M,'commit','-m','docs: reject stale-mask late-input model and scope correction')
heads={str(M):git(M,'rev-parse','HEAD')}
for root in (W,TV):
 atomic(root/REL,data);git(root,'add','--',REL);git(root,'commit','-m','docs: sync deployed input queue proof and bounded gate decision');heads[str(root)]=git(root,'rev-parse','HEAD')
status.update(at=now,phase='TASK179_306_INPUT_MODEL_CORRECTION',current_plan='7.174',current_head=heads[str(W)],current_plan_head=heads[str(W)],
 pending_opus='seq225 correct data-only due-batch model against actual DLL;306 dashloss unaccepted; no runtime source/globaldash change',
 active_blocker='Corrected finite306 artifacts pending. Actual DLL preserves coalesced edge; ordinary lateL risk retained; no newgame gate.',
 astra306_review=str(R/'ASTRA306_REVIEW.md'),opus306_pending_review=str(R/'OPUS306_REVIEW.json'),
 next_phase='review corrected finite due-batch cases, then separate bounded-engineering disposition under unchanged strict stops')
writej(B/'sol/STATUS.json',status)
p=B/'sol/work_packages/task179/PROGRESS.json';pr=read(p);pr.update(at=now,current_head=heads[str(W)],state='306 latest-mask model rejected by actualDLL; data-only correction pending, runtime/P unchanged',
 critical_review=str(R/'ASTRA306_REVIEW.md'),next='seq225 due-batch model finite correction; no globalinput change or blanket ordinary injury-free gate; current no live gate')
writej(p,pr)
mail=B/'sol/TO_OPUS.md';text=mail.read_text(encoding='utf-8-sig');assert 'seq225' in text[:140]
note='''补充同seq225：计划7.174已同步，刀口HEAD {head}，runtime5df不变。原Astra/xhigh聚焦裁决已完：支持拒绝假丢DASH/全局多发包方案；只修due-batch数据适配，原2763晚1普通路线敏感保留。Opt1不是全ordinary无伤定理；更正后若只剩孤立历史lag压力风险而采用完整串行情景关键撤离准时，Sol可另建一次已知风险首损工程，不能涂绿原scheduling false。若 adopted serial真丢关键动作/错绝对clock/新交还必入已知危险，则先局部修。你不必扩大成无伤证明/重做h2；按225有限范围一次交付。Astra摘要在analysis/task179_5df8711e_20261105/ASTRA306_REVIEW.md。当前无新game gate、无新增实现任务。

'''.format(head=heads[str(W)])
parts=text.split('\n\n',1);atomic(mail,(parts[0]+'\n\n'+note+parts[1]).encode('utf-8'))
writej(R/'PLAN_SYNC_306.json',{'at':now,'plan':'7.174','heads':heads,'runtime_source':S,'seq':225,'new_game_gate':False})
print(json.dumps({'plan':'7.174','heads':heads,'seq':225,'source_unchanged':True,'game_gate':False},ensure_ascii=False))
