"""Bind the reviewed Task180 package, request pause, reuse the fixed executor."""
from pathlib import Path
import datetime,hashlib,json,os,re,shutil,subprocess,psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/task180_l2_322_20261106';P=B/'analysis/task179_body321_20261106';M=Path('C:/modeling/silksong_bot');D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');V=Path('C:/Users/Meng/.codex/worktrees/forum-tv-prep/silksong_bot');S='9f6da15674da8c396d729a680f6868d47d9e233f';G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(n,d):
 p=A/n;assert not p.exists(),p;p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def atom(p,d):
 t=p.with_name(p.name+'.l2322.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(t,p)
def git(r,*a):return subprocess.check_output([G,'-C',str(r),*a],encoding='utf-8').strip()
st=read(B/'sol/STATUS.json');job=read(A/'ROOT_JOB.json');assert not st['live_or_budget_running'] and st['own_offline_jobs']==[job]
try:assert abs(psutil.Process(job['pid']).create_time()-job['created'])>=.01
except psutil.NoSuchProcess:pass
assert read(A/'ROOT_JOB_END.json')['error'] is None
pkt=read(A/'SOURCE_PACKET.json');assert all(sha(D/n)==h for n,h in pkt['raw_runtime_files_sha256'].items())
assert git(D,'rev-parse','HEAD')==S and not git(D,'diff','--name-only')
summary=(B/'opus/TO_SOL.md').read_text(encoding='utf-8-sig').split('## 用法',1)[0];assert int(re.search(r'\*\*最新编号\*\*：#(\d+)',summary).group(1))==322
assert read(B/'sol/OPUS_WAKE.json')['seq']==248 and not (B/'sol/performance/ACTIVE.json').exists()
put('ROOT_CHECK_CLEANUP.json',dict(at=now(),job=job,actual_exit=True,checks=16,artifact_calls=3670,formal_P=0,games_started=0))
(A/'ASTRA322_REVIEW.md').write_text('''# Task180 #322 concentrated critical semantic review

Actual reviewer: existing gpt-6-astra / xhigh agent /root/astra_task178_pose_review. Read-only review of ecc6332b to 9f6da156, no tests/P/game.

No new P0-P2 blocker found in reviewed normal paths. Only winner commit precedes releases; intercept uses original jump identity/rune expiry and new commitments are not released by stale snapshots. Losing middle evaluation changes only the same baseline decision/observation memory. Candidate/observation order, cluster exclusion, unpicked winner hold and event expiry match. Shared contact/entry/stomp/no-hit/TA ordering remains. Moving MiddleJump finish ahead of MiddleReturn aftermath has no conflicting current fields; earlier back_live/exit_until assignment has no added normal-path reader.

Limits: source semantic comparison only. Finite replay does not cover every future state, unrepresented live winners or prove safety/performance. No concrete counterexample requiring a larger matrix was identified.
''',encoding='utf-8')
put('SOURCE_REVIEW.json',dict(at=now(),source=S,accepted=True,processed_opus_number=322,task=180,baseline='ecc6332b0b977dacd86dfd3d4d3f57d71e0cdd61',scope='Limited L2 organization, 11 complete units /13 rule IDs, conditions/scores/output/event hooks colocated; generic selection/application, unchanged common constraints. Source and finite offline accepted; N23 formal P pending.',independent_checks=16,artifact_calls=3670,source_files_bound=716,artifacts=str(A/'ARTIFACT_RECEIPT.json'),structure=str(A/'STRUCTURE_RECEIPT.json'),critical_review=str(A/'ASTRA322_REVIEW.md'),known_limits=['No proof of all-state equivalence or live survival','Opus broad suite had6 failures+2 errors; reported baseline reproduction was not independently rerun by Root; changed-source checks passed','Engineering eight-scene timings are concurrent E samples, not formal P or proof all outliers are noise','Original178/179 live/route/scheduling gaps retained; no new tactics or live permission'],new_game_gate=False))
entry=B/'analysis/task179_return318_20261106/timing_entry318.py';ex=B/'sol/performance/executor_v1.py'
assert sha(entry)=='5e4798784124284f1181998987188412fd0495cd98a2abb4e1222b5e791bd6db' and sha(ex)=='58ddebd9cae93764d37b9fb4efa75ea7a2484bb6f4337895a245886e86062ffc'
for n in ('engineering_helpers.py','resource_background.py','RESOURCE_BACKGROUND_APPROVAL.json'):shutil.copyfile(P/n,A/n)
binding=read(P/'P_INPUT_BINDING.json');assert all(sha(Path(n))==h for n,h in binding['files'].items());put('P_INPUT_BINDING.json',dict(at=now(),files=binding['files'],scope='Unchanged recording/contract and frozen nominal entry318'))
case=read(P/'P_CASE.json');case.update(source=S,source_review_file=str(A/'SOURCE_REVIEW.json'),source_packet_file=str(A/'SOURCE_PACKET.json'),source_packet_sha256=sha(A/'SOURCE_PACKET.json'),input_binding_file=str(A/'P_INPUT_BINDING.json'),input_binding_sha256=sha(A/'P_INPUT_BINDING.json'),resource_helper_file=str(A/'engineering_helpers.py'),resource_helper_sha256=sha(A/'engineering_helpers.py'))
case['contexts']=case['contexts'][:1];assert case['contexts'][0]['name']=='N';case['accepted_reviews']=sorted(set(case['accepted_reviews'])|{322});case['scope']='Task180 limited organization: one N2813..2835 full-tick window exactly matching321 baseline,23 ticks. Eight functional scene artifacts already compared; no larger matrix/live.';put('P_CASE.json',case)
put('P_SPEC.json',dict(at=now(),source=S,ticks=23,context=case['contexts'],reason='L2 generic hot loop changed; one matching complete-tick sample supplements16 targeted checks and3670 existing comparisons. No new hero rollouts or per-tactic geometry.',executor_sha256=sha(ex),entry_sha256=sha(entry),baseline=str(P/'p_NW/N'),timing_limits='Finite unpaired process samples; retain all peaks/GC; no p99/probability claim or removal of prior scheduling limits.',new_games=0))
doc=M/'docs/plans/forum_clapper_l2_tactics.md';t=doc.read_text(encoding='utf-8-sig');t=t.replace('源码基线：`ecc6332b0b977dacd86dfd3d4d3f57d71e0cdd61`','源码基线：`9f6da15674da8c396d729a680f6868d47d9e233f`')
t=t.replace('## 已授权的有限整理（Task180，已派发）','## 有限整理（Task180，源码及有限回归已核，性能待核）')
start=t.index('用户要求先收尾当前 Task179，再由 Opus 做有限整理。',t.index('## 有限整理'))
end=t.index('## 适用配置与源码入口',start)
t=t[:start]+'''Task180已在开发树实现：11个完整战术单元承载13个规则标识，`intercept/hold`与`bait/return`分别保留同一事件的阶段。各单元同时拥有适用条件、最高分/适用度、胜出承诺、目标和站位/攻击输出、退出及日志；公共选择器只作声明互斥、分数/切换成本/同分保持和统一应用，不再按赢家名字拼装第二份输出。场景几何每次共享一次；公共接触/EntryAttack有效期/TA等限制保留。

Root核过源与716项运行文件，16项新增及未被回放覆盖的邻接测试通过；8个既有场景3670次L2调用的旧输出/完整记忆与相关计数逐位一致，只排除新增诊断与测时字段。相关生产行、发键及模型接触对照一致。集中Astra关键语义审阅未定位新增P0–P2。证据限这些路径，不证明所有未来状态或实机等价；Opus广套件6失败/2错误报告为基线已存在，Root未重跑该旧失败组。

现只准备与321同一N窗口的23拍完整tick性能，源与文档冻结到实际全清理。并行E场景内局部L2配对中位差约+0.03385ms，峰16.8605ms保留；它不是隔离P，不能将所有差值归因于噪声，也不当完整决策预算。当前没有新实机许可；178/179原未覆盖、W3接近与串行慢帧缺口继续单列。本包不改评分/打法/刀口/几何/默认开关，不新增成团第二战术。

'''+t[end:]
t=t.replace('- [外层竞争与成团路线](C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot/brain/ssbot/combat/tactics/clapper_priority.py)：`DEFAULT_SCORES`、`cluster_route`、`middle_return`、`decide`。','- [公共选择与应用](C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot/brain/ssbot/combat/tactics/clapper_priority.py)：`_pick`、`decide`、`_apply`。\n- [完整战术单元](C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot/brain/ssbot/combat/tactics/clapper_tactics.py)：条件、评分、输出与阶段/保持/退出；`TACTICS`、`OBSERVE`及生成的`DEFAULT_SCORES`。\n- [共享场景事实](C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot/brain/ssbot/combat/tactics/clapper_scene.py)：`Scene`及几何/可站/攻击入口。')
doc.write_text(t,encoding='utf-8')
plan=M/'docs/plans/forum_clapper_plan.md';t=plan.read_text(encoding='utf-8-sig');assert '进度7.193' not in t
top='2026-10-27 起草（历史审阅与阶段规格保留）。**当前进度（11-06，7.193）：Task180有限L2整理源码9f6da156已独审：11战术单元归拢13规则的条件/分数/输出与事件，公共竞争/应用无第二份赢家分支。16局部检查及8场景3670次既有工件对照通过，集中关键语义审无新增P0–P2。仅准备与321同N窗口23拍完整tick，等Opus暂停后沿固定执行器最小启动再P，源/docs冻结至真实全清理。不是所有状态或实机通过；原178/179路线/时序缺口与默认关、无新实机许可保持。**'
t,c=re.subn(r'2026-10-27 起草.*?(?=\n\n)',top,t,count=1,flags=re.S);assert c==1
t+='''

#### Task180 #322有限结构源审与3670调用对照核收，只补N23完整tick（11-06，进度7.193）

runtime9f6da156实际仅五文件：重组clapper_priority、新增clapper_tactics/clapper_scene、policy三行诊断日志和七项测试。与ecc基准之间其他docs是Sol既有提交，不算Opus改计划。Root716文件全绑定，16新/未回放路径邻接检查1.69s通过，未重复190/1851广套件或8场景策略重跑；独比8场景3670完整L2 prefs/goal/旧日志/记忆/计数，仅除新增eval/releases和测时，生产rows除cost/timing外全字段、相关链/发送/model接触同。缺失实际轨迹的胜者通过旧路径测试补最小触达，不冒称实机覆盖。Opus广套件6失败2错误称旧基线复现，Root核未改涉及源而未复跑该失败组，结论不写成全套通过。

条件/适用度/评分、输出与事件hooks实际归11单元，13规则两对阶段共单元；场景facts共享，公共选择只声明互斥/评分/保持，公共应用不含具体winner名字另拼行为。保留原观察候选更新及仅赢家动作承诺。Root普通结构审加实际Astra/xhigh窄审commit/release/事件失效/未重选拍保持/收尾次序，未定位新增P0–P2；支持范围是代码语义与有限路径，不承诺全状态等价或改好旧打法。analysis/task180_l2_322_20261106保存所有收据与Astra原意记录。

并行E旧新局部计时3670调用差中位+0.03385ms/均值+0.04544ms，新峰16.8605、旧峰10.489ms均保留；这是同时运行工程样本，不能称全部outlier是噪声，亦不能代完整tick。只补N2813..2835共23拍，和321同配置同输入原窗口，覆盖受影响普通L2热路径；其余功能已有8场景对照不扩矩阵。原executor_v1/timing_entry318字节、资源门、真clock/签名/配置/清理要求不改，先绑定后的最小启动退出再P。新seq249仅请求暂停计算/改源，STATUS原子true及刀口实际HEAD冻结到真实全清理，期间只读收信。SOURCE_REVIEW只接受此结构及有限离线范围；原179/178未覆盖、W3整局接近缺口、69ms旧慢帧与全串行门false保留，无新game gate。
'''
plan.write_text(t,encoding='utf-8');heads={}
for root in (M,D,V):
 for rel in ('docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md'):
  if root!=M:(root/rel).write_bytes((M/rel).read_bytes())
 git(root,'diff','--check','--','docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md');git(root,'add','--','docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md');git(root,'commit','-m','docs: record limited L2 review and bounded timing scope','--','docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md');heads[str(root)]=git(root,'rev-parse','HEAD')
put('PRE_P_PLAN_SYNC.json',dict(at=now(),heads=heads,source=S,plan='7.193'))
mail='''## seq249 / Task180 #322源码/有限回归核收；只补N23完整tick，暂停计算和改源

Root独比716源、16增量/未回放路径邻接检查通过，8既有场景3670完整L2旧输出/记忆/计数全同；生产rows除timing/cost全字段、发送与model接触同。11单元承载13规则，条件/分数/输出与事件确实归拢，公共择优/应用没有第二套winner分支。实际Astra/xhigh集中窄审commit/release/失效/保持/收尾未见新增P0–P2。SOURCE_REVIEW仅有限结构/所覆盖路径，不签所有状态/实机；广套件6fail+2error只注明你报告基线复现，Root未再跑。R=analysis/task180_l2_322_20261106。

局部并行E差中位+0.03385ms、均值+0.04544ms，新峰16.8605ms保留，不拿工程噪声解释所有峰。现在仅补与321同N2813..2835共23完整tick，不重复广矩阵/8场策略回放，原固定executor/entry字节和全部资源/真实clock/清理门不变，先同绑定最小startup/退出再正式P。

请暂停离线计算和改源（含docs），仅更新摘要明确按seq249暂停即可，无需ACK编号/唤醒。STATUS已原子true请求独占，runtime9f6da156及刀口实际docs HEAD冻结至Root全清理；不操作你的或核心进程。Root核P/清理后一次交结果。178/179原实机/路线/串行缺口与所有默认关保持，当前无新game许可，不开下一包。

'''
mp=B/'sol/TO_OPUS.md';mp.write_text(mail+mp.read_text(encoding='utf-8-sig'),encoding='utf-8')
st.update(at=now(),phase='TASK180_P_WAIT_OPUS_PAUSE',live_or_budget_running=True,own_offline_jobs=[],current_plan='7.193',plan_progress='7.193',current_source=S,candidate_source=S,current_head=heads[str(D)],source_review_pending=False,source_review_file=str(A/'SOURCE_REVIEW.json'),source_frozen_for_P=True,freeze_execution_head=heads[str(D)],opus322_review=str(A/'SOURCE_REVIEW.json'),pause_requested_at=now(),next_phase='Await pause, fixed startup then23 N ticks only; no live/new package.')
atom(B/'sol/STATUS.json',st);atom(B/'sol/OPUS_WAKE.json',dict(seq=249,task=180,at=now(),note='322 limited source accepted. Pause compute/source/docs for fixed startup+N23 P; no game/new package.'))
put('PAUSE_REQUEST.json',dict(at=now(),seq=249,source=S,freeze_execution_head=heads[str(D)],planned_ticks=23))
print(json.dumps(dict(source=S,checks=16,artifact_calls=3670,P_planned=23,pause_requested=True,heads=heads)))
