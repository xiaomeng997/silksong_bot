"""One same179 feedback for the Idle-entry evidence defect; no P or runtime writes."""
from pathlib import Path
import datetime,hashlib,json,os,subprocess
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/task179_return317_20261106'
M=Path('C:/modeling/silksong_bot');D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');V=Path('C:/Users/Meng/.codex/worktrees/forum-tv-prep/silksong_bot')
S='c00074ccdd589c0e3c37ba4302234e689a858121';G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,d):
 assert not p.exists(),str(p)
 p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def atom(p,d):
 t=p.with_name(p.name+'.return317.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(t,p)
def git(r,*args):return subprocess.check_output([G,'-C',str(r),*args],encoding='utf-8').strip()
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs')
assert read(B/'sol/OPUS_WAKE.json')['seq']==240 and git(D,'rev-parse','HEAD')==S
for r in (M,D,V):assert not git(r,'diff','--name-only') and not git(r,'diff','--cached','--name-only')
pkt=read(A/'SOURCE_PACKET.json');assert all(sha(D/n)==h for n,h in pkt['raw_runtime_files_sha256'].items())
assert read(A/'CHECK_RECEIPT.json')['pytest_rc']==0 and read(A/'ROOT_CHECK_CLEANUP.json')['identity_exited']
assert not (A/'ASTRA317_REVIEW.md').exists()
(A/'ASTRA317_REVIEW.md').write_text('''# Actual gpt-6-astra/xhigh focused #317 review (completed)

Reused /root/astra_task178_pose_review under the user workflow. Read-only; no source edits or extra tests.

One P2 in the Idle evidence contract at air_native.py1112-1115. Control.t is scaled StateTime, which can stop; f-round(t*60) is not a witnessed ENTRY. Freeze, long Update and nonzero first-entry timer invalidate the conversion; fs0 does not preclude an FSM transition. Root raw3147/3183/3339 show same-frame new Idle but the algorithm refers to the previous frame. With both buddies alive the sample result can coincide accidentally. Clock decrease alone also misses same-frame reentry or an observation gap when the new clock is no lower.

Two unexecuted synthetic counterexamples (not real game observations):
1. f100 buddy alive / target not Idle; f101 buddy dies then target enters Idle, final t=1/60. The code selects f100 and permits68; actual entry requires39.
2. f100 target Idle t0 and buddy alive; f101 missing while buddy dies and target leaves/reenters; f102 new Idle t>=0. Old buddy=True survives and permits68.

Minimal correction: bind the observed ordered Control->Idle event and its actual-entry buddy evidence. Missing entry, observation gap, or ambiguous same-frame life/death order means unknown ->39. Assign hit/reentry by event ordering rather than timer rollback. No new clock model.

Recovery (乙) is finitely accepted: uncommitted air approach only, above-target explicit loss of support, through _recover. Committed strike, source tail and hook links retained. A4 is a conditional legal recovery/gap-open landing/side-slash example, not successful repeated downslash. This focused review did not re-audit the query-grouping optimization (Root reviewed that delta).
''',encoding='utf-8')
finding=dict(priority=2,file='brain/ssbot/combat/knife_chain_air_native.py',line=1113,issue='Scaled Control StateTime is converted to update frame f-round(t*60); presence in alive history is incorrectly treated as observing this Idle ENTRY. A new Idle without decreasing observed time can inherit the previous instance across a gap.',raw_examples=[3147,3183,3339],source_contract='oracle/src/Entities/EntityExporter.cs:25-27',effect='The 68-frame witness may use a buddy alive before the true entry, or preserve a prior instance; it is not the required causal entry evidence.',actual_live_failure_proven=False,minimal_fix='Bind observed Control->Idle transition event to its actual frame and buddy-at-entry; invalidate on missing entry or observation gap; unknown keeps39. Do not build another clock model.')
put(A/'SOURCE_REVIEW.json',dict(at=now(),source=S,base=pkt['base'],processed_opus_number=317,accepted=False,source_delta_review_pass=False,complete_behavior_accepted=False,runtime_changed=pkt['changed'],independent_new_checks=9,check_seconds=1.52,checks=str(A/'CHECK_RECEIPT.json'),cleanup=str(A/'ROOT_CHECK_CLEANUP.json'),artifact_receipt=str(A/'ROOT_ARTIFACT_RECEIPT.json'),astra=str(A/'ASTRA317_REVIEW.md'),findings=[finding],finite_acceptance=['air-only legal no-witness recovery, committed strike/source tail retained','batched pushed-target contacts preserve per-row result in reviewed delta and existing artifacts','conditional recorded-reaction A4 production-path hit/pogo, recovery and ground/slash sends'],not_proven=['Repeated downslash until opening','Natural NPC response and no-hit survival','Formal P/deadline acceptance'],formal_P=False,game=False,new_live_authorization=False))
text='''

#### #317合法恢复与条件地面接续正例保留；Idle入口证据错锚须最小修复，正式P未启动（11-06，进度7.185）

已处理Opus #317，runtime 2f43a7e9+c00074cc（父8cda5ef8文档，上个runtime ac0d）。三运行文件/九新增测试；Root审全部增量与相邻observe/recover/锁段，714绑定仅三源变；实际E24–31/Idle45000/create1793967893.864541仅跑九新项1.52s通过，foreign0/源全同，进程真实退出。Opus1111专项记录保留不重复、不相加。analysis/task179_return317_20261106保存SOURCE_PACKET、CHECK_RECEIPT、ROOT_CHECK_CLEANUP、ROOT_ARTIFACT_RECEIPT、32个原始Idle转换的RAW_IDLE_ENTRY_CENSUS和实际Astra/xhigh窄审。SOURCE_REVIEW accepted=false，317不进实机accepted集合；0P/0game，原观察不重开。

乙的有限实现核收：仅活动transfer的air link且已在目标上方，对过期Idle/撤证据、域外Walk或无拟合静止姿态才经_recover交还；不是任意一拍无press_now_row即放弃，原strike/bounce_tail/钩段不入新门，已发键与失败责任/同招不重试保留。前版在2612过早丢续接的问题已收回，既有成功前缀保留。c000将RETURN_BODY命中重查按被击退iid分组，与原_contacts_only输入逐行语义一致；Root独立比A4与N1新旧各682个最终frame/target/mask/owner tuple全同，W3按共同2260..2900的622条全同。首次核对误拿不同末帧的682与622整段比较失败，原ARTIFACT_HARNESS_BOUNDARY保留；修正仅比较明确共同窗，非控制失败。

A4新增有效反应拼接的有限正例：2816模型hit470+pogo后接它自己3339真实受击反应片段，绕根镜像并明示NPC仍不响应后续英雄；2831目标Evade时合法交还，2836 L2转地面，2870模型落进缝，2884/2903现有rune_lowhop发朝470侧劈，之前evade_chase接近，非普通规划器地面行完成。仅一次模型hit、到2960条件模型hurt0；该样本新Idle仅15帧即闪避，不能第二刀，合法恢复正例不等于连续下劈/实机生存证明。Root14项源码SHA同当前c000，生产者原HEAD2f43/dirty planner差分从Git重构14c0b051fd5ecf22匹配，工具hashf385dd2f3097匹配；不改写成当时已提交。五个旧配置账本/worker字段unresolved仍保留，不能直接当正式P清单全过。

甲仍有确定P2：_observe_idle_evidence1113以f-round(Control.t*60)回推某个Update帧，只要alive_hist有该编号就当观察到了本次Idle ENTRY，1112仅用t下降判新实例。Oracle EntityExporter25明确t是scaled FsmState.StateTime且可停，不是Update帧年龄；Root真实3147/3183/3339均当帧Control Idle→Dmg Attack→Close Range→Idle且t约1/60，回推却锚到前一帧旧Idle，A4因此把2816新Idle记成2815。当前伙伴均活时未证明改变该样本结果，但不能把它当入口条件已满足；若伙伴在实际入口前死去、或缺帧中同iid转出再入且新t不小于旧t，可能借用旧伙伴/旧撤销状态延长证人。实际Astra/xhigh窄审同意该证据契约缺口，不拿九个现有单测冒充覆盖。

同179只做最小事件绑定：使用现有已观察的Control→Idle事件与真实事件帧/本次实例、当帧伙伴存活；无确切入口事件或观测断档不能证明同实例时，延长证据未知回39，不由scaled t另造时钟模型，也不从当前两只推入口。显式同帧受击后新Idle须重绑而非撤新实例，旧实例受击仍撤证据。保留乙、分组提速、正反例与成功前缀；只补缺帧/入口伙伴变化的局部反例和受影响生产窗，不重跑1111/旧1667。四窗P入口已交但未准入，修好上述后才由固定executor最小startup→真实P；BODY/AIR on与默认off必须不同实际进程，防模块常量缓存串配置。当前不再扩打法/模拟器、不开新局，FACE_HOOK/BOUNCE_TABLE/DSLASH仍关，源码owner仍Opus，原资源/输入/停止/全清理门不变。
'''
text=text.replace('无确切入口事件或观测断档不能证明同实例时','同帧伙伴生死顺序无法确定、无确切入口事件或观测断档不能证明同实例时')
p=M/'docs/plans/forum_clapper_plan.md';old=p.read_text(encoding='utf-8-sig');assert '进度7.185' not in old;p.write_text(old+text,encoding='utf-8')
heads={}
for root in (M,D,V):
 q=root/'docs/plans/forum_clapper_plan.md'
 if root!=M:q.write_bytes(p.read_bytes())
 git(root,'add','--','docs/plans/forum_clapper_plan.md');git(root,'commit','-m','docs: bound return317 recovery and correct Idle entry evidence','--','docs/plans/forum_clapper_plan.md');heads[str(root)]=git(root,'rev-parse','HEAD')
put(A/'PLAN_SYNC.json',dict(at=now(),heads=heads,plan_sha256=sha(p),runtime_unchanged=True))
mail='''## seq241 / 同Task179：317合法恢复与分组提速有限核收；只修Idle入口P2，再测既交四窗P

Root九项新测试1.52s全过、foreign0/714全同，E45000真实退出；三源增量和实际Astra/xhigh窄审完成。主计划7.185三树仅文档同步，R=analysis/task179_return317_20261106/保存SOURCE_REVIEW accepted=false、原始Idle转换、checks/cleanup及生产工件收据。乙air-only的明确无证人交还有限核收，不重审316旧锁段；c000命中按iid分组有限核收，A4/N1新旧682tuple各全同，W3共同2260..2900的622tuple全同。14源hash同当前，A4air8生产者原2f43+dirty planner差分14c0b051fd5ecf22已从Git重构，保留原标记。

A4经命中后真实录像反应拼接，2816模型hit+pogo→2831乙交还→2836地面意图→2870落缝→现有evade_chase/rune_lowhop侧劈键，条件正例保留；不是普通规划器地面行完成，只有一次模型hit，不签连续下劈或自然实机安全。五个旧配置unresolved字段原样保留。你已给四窗P，Root不要求重做场景或扩大打法；但甲有一个确定P2必须先修，故正式P尚未启动。

_observe_idle_evidence1112..1115以f-round(Control.t*60)推ENTRY，只因alive_hist有那个编号就说已观察入口，不能成立。Oracle EntityExporter.cs25的StateTime是scaled、可停；真实raw3147/3183/3339当帧Control Idle->DmgAttack->CloseRange->Idle、tin约1/60，却锚到前一帧旧Idle。A4同样2816新Idle记2815。当前两只都活未改变这份结果，但伙伴在实际入口前死去时会错误用68；缺帧中转出再入且新tin>=旧tin也会继承前实例。九单测没覆盖，不能先给P通过。

最小修法直接绑定已有Control->Idle事件的真实帧/本次实例及该入口当帧伙伴存活；缺确切入口事件/观测断档无法确认同实例则68证据未知回39。别用scaled t重建另一个时钟模型、不以当前len2推入口。新Idle显式事件无论新t比旧t大小都重绑；同帧受击后进入新Idle按事件顺序绑定，新实例别误撤，旧实例的受击仍撤证据。只补这两类局部反例，保留已好的乙/成功前缀/A4与拒绝例/分组，不再重跑1111/1667或新矩阵；给原完整包回修即可，不逐项ACK。

源闭合后Root复用你现有四窗和固定executor，先startup再正式P，不再另搭执行器。BODY/AIR on的A/N/W与默认off的D要不同实际进程，避免ssbot模块常量缓存串配置；源/工具/实际配置/输入和完整串行成本照旧绑定。当前源码仍由你唯一写，RETURN_BODY/AIR默认关，FACE_HOOK/BOUNCE_TABLE/DSLASH不变，没有下一盘授权、旧停止批次不重开；原资源/输入/全清理门不变。

'''
mail=mail.replace('缺确切入口事件/观测断档无法确认同实例则68证据未知回39','同帧伙伴生死顺序未知、缺确切入口事件/观测断档无法确认同实例则68证据未知回39')
mp=B/'sol/TO_OPUS.md';mp.write_text(mail+mp.read_text(encoding='utf-8-sig'),encoding='utf-8')
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs')
st.update(at=now(),phase='RETURN317_IDLE_ENTRY_EVENT_FIX',current_plan='7.185',plan_progress='7.185',current_head=heads[str(D)],candidate_source=S,source_review_pending=True,source_review_file=str(A/'SOURCE_REVIEW.json'),opus317_review=str(A/'SOURCE_REVIEW.json'),astra317_review=str(A/'ASTRA317_REVIEW.md'),next_watch_user_authorized=False,next_watch_ready=False,active_blocker='P2: Idle ENTRY cannot be inferred from scaled StateTime and update-frame subtraction; exact transition event/continuity required before extending witness to68. Formal P not started.',next_phase='Same179 minimal entry-event/continuity correction -> existing four windows via fixed executor; no next game')
st['return_middle_preference']['implementation']='conditional A4 modeled first hit/legal recovery/gap landing and existing side-slash sends; Idle entry causal evidence repair pending; repeated-air and live validation incomplete'
atom(B/'sol/STATUS.json',st);atom(B/'sol/OPUS_WAKE.json',dict(seq=241,task=179,at=now(),note='317 recovery/per-target grouping finite accepted; fix only causal Idle-entry event/continuity P2, then existing four-window P. No game.'))
put(A/'HANDOFF241.json',dict(at=now(),seq=241,task=179,source=S,heads=heads,accepted=False,formal_P_ticks=0,games_started=0))
print(json.dumps(dict(seq=241,plan='7.185',checks=9,accepted=False,heads=heads)))
