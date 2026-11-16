"""Publish requested current L2 checklist and finite #319 offline-input review; no runtime edits."""
from pathlib import Path
import ast,datetime,hashlib,importlib.util,json,os,re,subprocess,psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/task179_schedule319_20261106';M=Path('C:/modeling/silksong_bot');D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');V=Path('C:/Users/Meng/.codex/worktrees/forum-tv-prep/silksong_bot')
S='0b1481774f04838a610e5d31a70acbfcdef623df';G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,d):
 assert not p.exists(),str(p)
 p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def atom(p,d):
 t=p.with_name(p.name+'.doc319.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(t,p)
def git(r,*args):return subprocess.check_output([G,'-C',str(r),*args],encoding='utf-8').strip()
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs') and read(B/'sol/OPUS_WAKE.json')['seq']==243
for root in (M,D,V):assert not git(root,'diff','--name-only') and not git(root,'diff','--cached','--name-only')
packet=B/'analysis/task179_return318_20261106/SOURCE_PACKET.json';source=read(packet);assert all(sha(D/n)==h for n,h in source['raw_runtime_files_sha256'].items())
A.mkdir(exist_ok=False);me=psutil.Process();me.cpu_affinity(list(range(24,32)));me.nice(psutil.IDLE_PRIORITY_CLASS);job=dict(pid=me.pid,created=me.create_time(),phase='small input-adapter component counterexample and documentation only',cpus=me.cpu_affinity(),priority=me.nice())
put(A/'ROOT_JOB.json',job);st.update(at=now(),phase='L2_DOCUMENT_AND319_INPUT_REVIEW',own_offline_jobs=[job]);atom(B/'sol/STATUS.json',st)
port=B/'opus/review179/l1_307/hf_cs.py';spec=importlib.util.spec_from_file_location('readonly_verified_hf307',port);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
def init():
 h=mod.HoldFilterCS();h.restore(1,1,[0]*32,[5]*32);return h
queued=init();queued.queue_plain(1,0);queued.queue_plain(0,1);actual=queued.step(1)
collapsed=init();approx=collapsed.step(1)
assert actual==0 and approx==1 and (0 & ~1)==0
put(A/'HF_QUEUE_COUNTEREXAMPLE.json',dict(at=now(),kind='component synthetic counterexample, not live data',helper=str(port),helper_sha256=sha(port),initial_desired=1,initial_latched=1,age=5,due_packets=[0,1],actual_queue_then_one_step=dict(latched=actual,pending_bit0=queued.pending[0]),collapsed_latest_only=dict(latched=approx,pending_bit0=collapsed.pending[0]),old_overwritten_press_note=False,proves='No overwritten-press note does not establish full HoldFilter queue equivalence.'))
astra='''# Actual gpt-6-astra/xhigh focused #319 review

Completed on the reused /root/astra_task178_pose_review. Read-only; no new policy replay, P or source edits.

The offline late adapter remains latest-wins: replay308.py887-900 feeds only the last due packet into HF. Deployed QueuePlain queues each due packet before one Step. Its note misses a release/repress when J was already held. N model contacts0.02/0.08u therefore remain sensitivity evidence in an approximate adapter, not a proved deployed-path defect.

The skip-only adapter at1007-1009 sets act.applied=act.target=f when no fresh packet exists; FrameExporter.cs169-171 reads LastAppliedFrame/LastAppliedTarget, which do not advance without an application. The skip/inbox idea is right, but A receipt-driven reacquisition must be rechecked after fixing this.

Reuse the previously checked l1_307/hf_cs.py per-packet queue and correct no-packet receipts. Check only the affected A reacquisition and N late edge through first contact with the same-condition off control. Do not rerun219 P or add online timing branches first. bounds_lo physical timing is not ACTION delivery delay. If N persists under correct input, compare the existing original/narrowed layer offline; keep BODY off without a causally observable validated admission rule.
'''
(A/'ASTRA319_REVIEW.md').write_text(astra,encoding='utf-8')
put(A/'REVIEW319.json',dict(at=now(),source=S,runtime_changed=False,runtime_packet=str(packet),runtime_packet_sha256=sha(packet),runtime_files_unchanged=714,processed_opus_number=319,accepted=False,findings=[dict(priority=2,scope='offline input adapter',file='opus/review179/l1_308/replay308.py',line=887,issue='Same-frame due ACTIONs collapsed before HF; missing overwritten-press note is insufficient',component_evidence=str(A/'HF_QUEUE_COUNTEREXAMPLE.json')),dict(priority=2,scope='offline input adapter',file='opus/review179/l1_308/replay308.py',line=1007,issue='skip-only frame with no new application advances applied/target receipt')],astra=str(A/'ASTRA319_REVIEW.md'),next='Fix local replay input/receipt adapter only, then finite affected A/N/off checks; no production or219 P rerun',new_game_gate=False,formal_P=0))

doc=M/'docs/plans/forum_clapper_l2_tactics.md';content=doc.read_text();tree=ast.parse((D/'brain/ssbot/combat/tactics/clapper_priority.py').read_text());scores=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='DEFAULT_SCORES' for t in n.targets));found={k:float(v) for k,v in re.findall(r'^\| `([^`]+)` \| (\d+) \|',content,re.M)};assert found==scores
links=re.findall(r'\]\(([^)]+)\)',content)
for target in links:assert (Path(target) if re.match(r'^[A-Za-z]:/',target) else doc.parent/target).exists(),target
put(A/'DOCUMENT_REVIEW.json',dict(at=now(),document=str(doc),source=S,score_rows_verified=13,links_checked=len(links),all_links_exist=True,missing_second_branch_explicit=True,source_pending_vs_verified_separate=True,run_tests_or_game_for_document=False))
plan=M/'docs/plans/forum_clapper_plan.md';text=plan.read_text(encoding='utf-8-sig');assert '进度7.187' not in text
newtop='2026-10-27 起草（历史审阅与阶段规格保留）。**当前进度（11-06，7.187）：L2现状总表已建立，明确区分已实现、部分实现、默认关闭和未实现；成团贴砍后撤第二分支仍未实现。runtime0b148177的入口P2已修、四窗219拍P已完成并全清理，串行门未签全过。319只改离线工具，新跳拍/晚应用结论因逐包HF与无包回执适配缺口待回修，不据此改生产或签下一局。当前没有新实机启动许可。**'
text,count=re.subn(r'2026-10-27 起草.*?(?=\n\n)',newtop,text,count=1,flags=re.S);assert count==1
text,count=re.subn(r'> \*\*实机授权（用户最新决定，11-03，覆盖11-01到场等待）\*\*：[^\n]+','> **当前实机边界（11-06核对）**：最近一次用户限定为一盘保护观察，该盘已经结束并全清理；当前没有下一盘启动许可。历史11-03不在家时的自主测试授权，执行时仍受随后单盘限定约束。另行绑定的新局须保留源审、实际输入、STOP、退出、完整日志与真实清理门；旧停止批次不重开。',text,count=1);assert count==1
marker='> **共享进度入口**'
assert text.count(marker)==1
text=text.replace(marker,'> **L2战术现状总表**：见[双怪L2战术现状](forum_clapper_l2_tactics.md)，按场景列出实现状态、分数、互斥条件、默认开关和验证缺口。\n\n'+marker)
text+='''

#### 用户要求建立L2实现总表；319仅离线适配待修，不据近似晚包结果新增在线成本（11-06，进度7.187）

新增docs/plans/forum_clapper_l2_tactics.md，基线runtime0b148177，只列当前双Clapper manual-B路径；按用户关心的场景逐条区分已实现/部分实现/未实现、默认关闭与实际验证。13个分值逐项与当前DEFAULT_SCORES一致，所有源码/主计划/证据链接存在；采用当前仓库Markdown格式，已回读检查。本页是当前L2清单，后续原位维护，不以历史交付替代当前状态。尤其明确：成团前摇贴砍→起跳后撤→落地再砍的第二完整分支，以及按空间选择它和后撤引导的二选一，均未实现；当前不足空间仅clamp后撤目标。中间跳跃的guide/stand/under/over内部选择、外层竞争互斥、EntryAttack和动作层责任、RETURN_BODY/AIR默认0和连续踩头/走路怪完整翻越/墙角突围未验收分别记载。当前没有因用户问文档而新增战术代码或开局。

已读并处理Opus #319的交付，运行源码未改；714项同318包。报告A只skip2793或整段旧排程后2794再起跑、2812出刀/2817模型hit+pogo、2832交还，W侧劈少；N只晚应用时模型身体擦0.02u、整段0.08u，只跳拍无hurt；off该段无hurt但窗口外另有模型hurt。这些保留为条件模型结果，不作为生产定因或时序验收通过。

Root读新增skip/late适配与Oracle实际WriteAction、复用实际Astra/xhigh作关键假设窄审，确定两个离线证据P2：replay308.py887..900把同帧到达包折成最后mask才进HF，原‘无覆盖press note’不足以证明逐包等价；1007..1009在只skip但无新包时仍写act.applied/target=f，部署FrameExporter读LastApplied*，无新应用不前移。Root用原已核l1_307/hf_cs的纯组件反例复现：J已保持、同帧依次松J再按J，逐包QueuePlain→一次Step输出松J/还有一个pending边沿；折叠最新包保持J，旧note仍false。它是合成组件证明，不是该N帧已经发生此边沿或实机受击证明。

analysis/task179_schedule319_20261106保存REVIEW319 accepted=false、ASTRA319_REVIEW、HF_QUEUE_COUNTEREXAMPLE、文档检查与源码绑定，0新P/0game，无运行源码变化。下一步同179只让Opus复用已核307逐包Push/Step和无包回执，修自己的离线工具，再有限核A重准入及N晚到边沿至首接触、同条件off对照；不重跑219P/全矩阵，不先加在线时序分支/缓存/新打法。修后N若仍成立才沿现有rollout/原层与收窄路径作局部对照；bounds_lo物理时序不冒充ACTION到达变体，在无可观察已验证准入条件前BODY仍默认off。原P样本/清理与原始STOP不改，当前无下一局许可。以上连同新L2文档一次seq244交接，Opus仍唯一源码owner。
'''
plan.write_text(text,encoding='utf-8')
heads={}
for root in (M,D,V):
 for rel in ['docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md']:
  if root!=M:(root/rel).write_bytes((M/rel).read_bytes())
 git(root,'add','--','docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md')
 git(root,'commit','-m','docs: add current L2 tactic implementation checklist','--','docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md');heads[str(root)]=git(root,'rev-parse','HEAD')
put(A/'PLAN_SYNC.json',dict(at=now(),heads=heads,plan_sha256=sha(plan),document_sha256=sha(doc),runtime_unchanged=True))
mail='''## seq244 / 同Task179：用户要求的L2实现总表已落库；319先修离线逐包输入与无包回执，不改生产源

新文档main/docs/plans/forum_clapper_l2_tactics.md已与刀口/TV同步，主计划7.187。它列场景、已实现/部分/未实现、13规则分数/互斥、动作接口和默认开关/验收范围；13分值及全部链接已核。成团贴砍后撤第二分支和空间二选一明确写未实现，当前别顺带扩战术代码，先收当前179。以后对应规则变化原位维护本页，main主计划仍单写。运行源还是0b148177、714项未变，219P/全清理保持。

319报告已读，A重准入、W少侧劈和N晚1擦0.02/0.08u都保留，但accepted=false：实际Astra/xhigh窄审与Root核Oracle契约发现本地输入适配两处P2。R=analysis/task179_schedule319_20261106，见REVIEW319/ASTRA319_REVIEW/HF_QUEUE_COUNTEREXAMPLE。

1) late-tick仍在replay308887..900把所有同帧包折成最新mask再进HF。‘无覆盖press note’不证明逐包等价。Root用已核307 HoldFilterCS实跑纯组件：原J已按、同帧0再J，逐包QueuePlain→Step先松J并留一个pending；latest-only继续J，旧note为false。此为契约反例，不宣称恰是N事故实际边沿。
2) 只skip而LATE_TICK空时1007..1009仍act.applied=target=f。部署FrameExporter169..171读Scheduler.LastAppliedFrame/Target，无新应用不会前移；所以A的收据驱动再准入仍须修这处后复核。

最小下一步只修自己的离线输入/收据适配：复用已核l1_307/hf_cs.py及其实际逐包队列，每个到达包依次Push/QueuePlain，动态帧只Step一次；无包保留真实LastApplied*，HF/在途键/STATE历史仍原路径。不要只改note或在no-note时宣称等价。给一个release/repress组件对照和无新包回执对照，再只核A跳2793的重准入到交还、N所交晚应用边沿到首接触并同条件off；不用再跑219P/129/1111/1667或整矩阵，W旧近似结果先留原边界。

先不改运行源码、不加在线时序分支/成本或新的risk-admission。N在修正后若仍成立，再用现有rollout/几何对该处原层与收窄行作有限离线对照；bounds_lo改变物理计时不等于覆盖ACTION晚应用。没有可观察/已核条件前，RETURN_BODY继续默认off，不能凭预计不会晚而收窄。FACE_HOOK/BOUNCE_TABLE/DSLASH等原配置不动，没有新game许可、旧观察/STOP不重开。实质结果一次交完整，无需ACK唤醒。

'''
mp=B/'sol/TO_OPUS.md';mp.write_text(mail+mp.read_text(encoding='utf-8-sig'),encoding='utf-8')
assert all(sha(D/n)==h for n,h in source['raw_runtime_files_sha256'].items())
put(A/'ROOT_JOB_END.json',dict(at=now(),job=job,errors=[],runtime_unchanged=True,formal_P=0,games_started=0))
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and st['own_offline_jobs'][0]['pid']==me.pid
st.update(at=now(),phase='L2_DOC_PUBLISHED_319_OFFLINE_INPUT_FIX',own_offline_jobs=[],current_plan='7.187',plan_progress='7.187',current_head=heads[str(D)],l2_tactic_document=str(doc),l2_tactic_document_source=S,opus319_review=str(A/'REVIEW319.json'),astra319_review=str(A/'ASTRA319_REVIEW.md'),pending_evidence_review=319,active_blocker='319 local replay collapses due packets before HF and advances no-packet receipts; delay conclusions provisional; fix offline adapter before online changes.',next_phase='Same179 offline per-packet HF/no-packet receipt fix, finite A reacquisition and N edge/off check; no production changes/P/game.',next_watch_user_authorized=False)
atom(B/'sol/STATUS.json',st);atom(B/'sol/OPUS_WAKE.json',dict(seq=244,task=179,at=now(),note='Requested L2 implementation/status checklist published.319 offline input adapter has queue+receipt gaps; fix tool only, finite A/N checks, no online source/P/game.'))
put(A/'HANDOFF244.json',dict(at=now(),seq=244,task=179,heads=heads,document=str(doc),accepted319=False,source=S))
print(json.dumps(dict(document=str(doc),lines=len(content.splitlines()),rules=len(scores),links=len(links),heads=heads,seq=244,runtime_changed=False),ensure_ascii=False))
