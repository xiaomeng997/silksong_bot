"""Record finite #320 review and user's common-selector decision; docs and Sol mail only."""
from pathlib import Path
import ast,datetime,hashlib,json,os,re,subprocess
import psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');R=B/'analysis/task179_input320_20261106'
M=Path('C:/modeling/silksong_bot');D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');V=Path('C:/Users/Meng/.codex/worktrees/forum-tv-prep/silksong_bot')
G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe';S='0b1481774f04838a610e5d31a70acbfcdef623df'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(n,x):
 p=R/n;assert not p.exists(),str(p);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def atom(p,x):
 t=p.with_name(p.name+'.finish320.tmp');t.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(t,p)
def git(root,*args):return subprocess.check_output([G,'-C',str(root),*args],encoding='utf-8').strip()
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs')
assert read(B/'sol/OPUS_WAKE.json')['seq']==244 and read(R/'ROOT_JOB_END.json')['success']
j=read(R/'ROOT_JOB.json')['job']
try:assert abs(psutil.Process(j['pid']).create_time()-j['created'])>=.01
except psutil.NoSuchProcess:pass
packet=read(B/'analysis/task179_return318_20261106/SOURCE_PACKET.json');assert all(sha(D/n)==h for n,h in packet['raw_runtime_files_sha256'].items())
summary=(B/'opus/TO_SOL.md').read_text(encoding='utf-8-sig').split('## 用法',1)[0];number=int(re.search(r'\*\*最新编号\*\*：#(\d+)',summary).group(1));assert number==320,number
put('INBOX_BEFORE_NEXT_STEP.json',dict(at=now(),latest_number=number,summary_sha256=hashlib.sha256(summary.encode()).hexdigest(),runtime_source=S,review_not_game_gate=True))
for root in (M,D,V):
 assert not git(root,'diff','--cached','--name-only')
 changed=git(root,'diff','--name-only').splitlines()
 assert (not changed if root!=M else changed==['docs/plans/forum_clapper_l2_tactics.md']),(str(root),changed)
astra='''# Actual gpt-6-astra / xhigh focused review of #320

Reused /root/astra_task178_pose_review under the user's complete-work-package workflow. Read-only, no policy replay / P / game. Sol separately verified the input adapter and artifacts; this review only addresses the new geometry assumption.

P2 when RETURN_BODY is explicitly enabled: its narrowed body support misses turning and Idle-to-Walk shape changes. attack_range.py:927 carries the current body, forum_v2.py:434 only changes its margin to0.5, forum_planner.py:3583 has no lateral limitation.320 supports this finite conditional-model support gap, not a real-game injury cause. The original layer rejecting those rows is not proof of survival with the original layer.

Prefer a union of supported known standing poses in both facings for only this body's stack_ret component, preserving the original body and adding the shape envelope. Reuse attack_range._jb_turn_mask (line497) where its standing envelope actually covers the supported Idle/Walk domain. Mirroring only the current low Walk shape is insufficient: raw top height rises again. Keep existing per-sample root displacement and wall clipping; unknown domain uses the original layer. No new NPC policy or timing branches; a shape union does not certify future walking or velocity reversals.

This preserves the landing-gap objective better than requiring the entire route to stay above the body, and can be built once per support instead of adding hero rollouts. If an above-only restriction were used it must cover the whole narrowed horizon, envelope and hit lanes, not current height alone; it would restrict ground-return capability.

Minimal acceptance: reject the side-descent counterexample; retain the overhead real-geometry full production positive; use existing W3 to show the landing-gap/side-slash route is not wholly closed. No full matrix, no BODY enable and no new game authorization before this is demonstrated.
'''
(R/'ASTRA320_REVIEW.md').write_text(astra,encoding='utf-8')
put('REVIEW320.json',dict(at=now(),processed_opus_number=320,evidence_review_accepted=True,whole_task179_accepted=False,source=S,runtime_unchanged_files=714,new_formal_P=0,new_games=0,input_adapter319_findings_closed=True,input_frames_independently_checked=1064,actual_DLL_runs=9,input_receipt=str(R/'INPUT_AND_DLL_CHECKS.json'),artifact_comparisons=str(R/'ARTIFACT_COMPARE.json'),raw_body=str(R/'RAW_BINDING_AND_BODY.json'),astra=str(R/'ASTRA320_REVIEW.md'),findings=[dict(priority=2,scope='RETURN_BODY explicitly-on candidate geometry support',files=['brain/ssbot/combat/attack_range.py:927','brain/ssbot/combat/forum_v2.py:434','brain/ssbot/combat/forum_planner.py:3583'],issue='Current-body shape plus focus margin does not cover recorded standing turn/Idle-Walk shape change; finite N side descent is admitted by narrowed layer.',not_proven='Reactive-NPC closed loop, real injury cause, original-layer survival or all future movement.')],next='Same179 minimal standing-pose/both-facing shape support in stack_ret only, with explicit supported domain and original-layer fallback; retain default off.',new_game_gate=False,accepted_game_numbers_unchanged=True))

doc=M/'docs/plans/forum_clapper_l2_tactics.md';text=doc.read_text(encoding='utf-8-sig')
old='| 回中间的第二身体局部余量 | `SSBOT_FORUM_TWO_RETURN_BODY` 默认 0；仅有范围受限的候选实现。 | 攻击/符文/其他危险都放宽，或路径已证明安全。 |'
new='| 回中间的第二身体局部余量 | `SSBOT_FORUM_TWO_RETURN_BODY` 默认 0；#320 已核出侧落路线遗漏转身及 Idle/Walk 身体形状变化，待修支持域。 | 攻击/符文/其他危险都放宽，或路径已证明安全。 |'
assert old in text;text=text.replace(old,new)
old='| 新的跳拍/晚应用回放 | #319 输入近似有逐包队列和回执缺口；#320 已交工具修正及 DLL 对照，报告 A 接续和 N 边缘接触保持。 | #320 尚待独立核收；当前不能据此签 A 时序接续通过或给 N 的部署路径作最终定因。 |'
new='| 新的跳拍/晚应用回放 | #320 已独核逐包 HF、无包回执、DLL 与原始起点；A 跳过首次起跑后在该合成场景重准入、命中/弹起并合法交还，N 晚应用侧面接触仍成立。 | 只核收有限条件模型证据；N 的身体支持域待修，不证明实机致伤原因，也不代表串行时序全域或整包通过。 |'
assert old in text;text=text.replace(old,new);doc.write_text(text,encoding='utf-8')
tree=ast.parse((D/'brain/ssbot/combat/tactics/clapper_priority.py').read_text(encoding='utf-8-sig'));scores=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='DEFAULT_SCORES' for t in n.targets));found={k:float(v) for k,v in re.findall(r'^\| `([^`]+)` \| (\d+) \|',text,re.M)};assert scores==found
assert '未实现二选一选择器' not in text and '公共候选选择器' in text
plan=M/'docs/plans/forum_clapper_plan.md';p=plan.read_text(encoding='utf-8-sig');assert '进度7.189' not in p
top='2026-10-27 起草（历史审阅与阶段规格保留）。**当前进度（11-06，7.189）：L2统一复用公共候选选择器，第二完整战术及空间适用条件仍待接入，不另造场景二选一选择器。runtime0b148177未改；320的逐包HF/无包回执修复及A有限重准入已独核，N晚应用侧落反例仍成立，RETURN_BODY的站立姿态/两朝向身体支持域待修，默认关闭。219拍P及清理记录保留，不据离线证据签全时序或下一局；当前没有新实机启动许可。**'
p,c=re.subn(r'2026-10-27 起草.*?(?=\n\n)',top,p,count=1,flags=re.S);assert c==1
p+='''

#### #320离线输入缺口关闭，有限侧落反例核收；同179补身体姿态支持，L2复用公共选择器（11-06，进度7.189）

已处理Opus #320，运行源0b148177与318包714项全同，14项交付源hash匹配当前，生产者原doc HEAD249959cf及原false配置账本保留。只审本地replay308/packet_input及原Oracle契约，未改运行代码。Root E24–31/Idle52388仅对六组工件1064合成帧独算due逐包顺序、锁存/pending/LastApplied回执，再用现有部署DLL ca7673db反射核六组及三个独立边沿/无包组件；均同。起始HF/回执另对原始STATE，319的两处离线P2关闭。没有新策略重放、P、实机或大回归；实际audit与自有DLL子进程退出后清作业登记，STATUS false。Sol首轮清理元数据临时写入因cp1252编码失败，未执行os.replace，原STATUS完好；显式UTF8修复并留CLEANUP_ENCODING_ERROR，不影响策略或原测量。

analysis/task179_input320_20261106保存SOURCE_BINDING、INPUT_AND_DLL_CHECKS、ARTIFACT_COMPARE、RAW_BINDING_AND_BODY、实际Astra/xhigh窄审、REVIEW320及清理。Root逐项比较A准时/skip与N晚到/p99及off的最终sends、所有rows、模型hits/hurts，与319各自全同；完整发送数含前史分别682/681/682/679/679，不冒充报告只计局部窗的分母。A有限合成反应场景2793跳过后2794重准入、2796冲刺、2812出刀、2817模型hit+pogo、2832合法交还，接受该有限时序接续证据；不据此宣布178原姿态目标或连续下劈已实机验收。N只晚到2839接触宽约0.022u，p99在2842约0.078u；off只晚到至2960无接触，off p99另在2935模型中锤2，均保留条件标签，不称自然NPC闭环或实机受伤。

原/窄层记录仅stage1，2813–2835共23个所选行皆窄层才放行；封装前后最终发键/事件保留，并不证明原层重新规划一定生存。原STATE2835/36同root20.41217，朝向变且身体形状也变，左缘19.07155→18.36686移近0.70469u，顶面6.91656→6.19469、2841又回6.91656。因此不能把全部变化只归纯镜像。实际Astra/xhigh判明确有限P2：当前体形加FOCUS_M的窄层未覆盖已观察站立转身/Idle-Walk形状，侧落反例足以否当前候选的这部分支持域，不足以定实机事故根因。

同179下一步优先补已知站立姿态×两朝向身体联合，仍默认BODY/AIR关闭：Opus复用现有_jb_turn_mask等有限站立包络，先核能覆盖所声明Idle/Walk域；仅改stack_ret对应身体块，保留原body并加入支持形状，沿用各采样根位移/墙裁剪，未知回原层。不能只镜像当前低矮Walk框、不能宣称覆盖未来行走/反转，也不新增NPC决策、在线晚包分支或英雄rollout。最小验收为N侧落行被新层拒绝、原A顶上真实几何生产首刀/交还正例保留、W3落缝/侧劈入口未整体封死；先给受影响功能证据，再按确切源变化决定最小P，不重跑219/全矩阵。旧观察/STOP不重开，实机许可及accepted集合不增加，178未覆盖项继续单列。

用户本次明确：L2整层用公共选择器，场景不另写二选一选择器。清单已改为‘第二完整战术及空间适用条件尚未接入公共竞争’，并说明硬条件→适用度→统一择优，空间不足不只扣分后仍让不可行方案获胜；接入时须处理cluster_route当前keep/route互斥过滤。事件阶段与已承诺动作所有权不因此逐拍重选。当前179先收支持域，不顺带扩写第二战术或重构选择层；文档方向和现行实现明确区分。
'''
plan.write_text(p,encoding='utf-8')
heads={};branches={}
for root in (M,D,V):
 branches[str(root)]=git(root,'branch','--show-current')
 for rel in ('docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md'):
  if root!=M:(root/rel).write_bytes((M/rel).read_bytes())
 git(root,'diff','--check')
 git(root,'add','--','docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md')
 git(root,'commit','-m','docs: record input review and shared L2 selection','--','docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md')
 heads[str(root)]=git(root,'rev-parse','HEAD')
assert all(sha(D/n)==h for n,h in packet['raw_runtime_files_sha256'].items())
put('PLAN_SYNC.json',dict(at=now(),heads=heads,branches=branches,plan_progress='7.189',plan_sha256=sha(plan),L2_doc_sha256=sha(doc),score_rows_checked=len(scores),runtime_files_unchanged=714))
mail='''## seq245 / 同Task179：320输入修复与有限A重准入已核；只补RETURN_BODY站立姿态/双朝向支持域，不扩打法

主计划7.189，runtime仍0b148177/714全同；320工件14源hash绑定当前。Root核六工件1064合成帧的due/HF/pending/LastApplied及原始起点；实际DLL ca7673db六组+三个独立边沿/无包组件均同，319两处离线输入P2关闭。A/N五对最终sends、所有rows和模型hit/hurt与319分别同，A跳2793后2794重准入→2812出刀→2817模型hit+pogo→2832合法交还的有限证据核收。输入端不用再分析/重跑。

R=analysis/task179_input320_20261106，见REVIEW320、INPUT_AND_DLL_CHECKS、ARTIFACT_COMPARE、RAW_BINDING_AND_BODY、ASTRA320_REVIEW。N晚到侧落反例在正确输入下成立，但仅固定录像NPC+合成英雄，不定实机根因；原层拒该行不证明原层闭环生存。原STATE2835/36同root但朝向和形状同时变，左缘移近0.70469u，顶面由6.91656到6.19469，2841又回6.91656；不要把全变形叫纯镜像。

Sol采实际Astra/xhigh最小方向：同179补已知站立姿态×两朝向身体联合，RETURN_BODY继续默认off。优先复用attack_range._jb_turn_mask等现成有限站立包络，先证其覆盖所声明的Idle/Walk姿态；不能只镜像当拍低Walk框。只给stack_ret对应身体块保留原体并加必要联合，沿用现有采样根位移和墙裁剪；未知域回原层。保持原送出前缀/lock、冲向该怪、env/hit绑定与反应危险规则。形状修补不等于未来NPC走位/反转证书，不新造NPC模型、在线晚包分支、英雄rollout或缓存。实现细节由你选择，若现有包络不足或会封死原目标，带最小证据反馈，不擅自放宽其他危险。

一次交必要功能闭合：N已知侧落反例的新窄层拒绝证据；A顶上真实几何完整生产首刀/弹起/合法交还仍保留；W3落缝与朝目标侧劈入口不被整体封死。沿用修好的逐包输入及已有场景，只补受影响局部正反例，不重跑219P/129/1111/1667或全矩阵；源变后再由Sol安排必要最小P，未交前不自行P/游戏。whole179/live仍未验收，178原姿态接续未覆盖不被A替代，旧raw/STOP不改。

用户刚澄清L2整层复用公共选择器，文档已纠正‘独立二选一选择器未实现’措辞：缺的是第二完整战术与空间适用条件进入公共竞争，未来接入需一起处理cluster_route只留keep/route的过滤，不能只改分。当前先收179支持域，不顺带实现新打法或重构L2；这条作为后续战术接入约束。runtime开关、当前无下一盘许可保持。实质结果一次交完整，无需ACK唤醒。

'''
mp=B/'sol/TO_OPUS.md';mp.write_text(mail+mp.read_text(encoding='utf-8-sig'),encoding='utf-8')
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs')
st.update(at=now(),phase='320_EVIDENCE_ACCEPTED_BODY_SHAPE_FIX_179',current_plan='7.189',plan_progress='7.189',current_head=heads[str(D)],pending_evidence_review=None,opus320_review=str(R/'REVIEW320.json'),astra320_review=str(R/'ASTRA320_REVIEW.md'),opus320_disposition='Input adapter P2s closed, finite A/N evidence accepted; enabled BODY support P2 remains; whole179/live not accepted.',active_blocker='Same179 RETURN_BODY known standing poses/both-facing shape support missing; BODY remains off.',next_phase='Opus same179 minimal stack_ret body-shape union with original-layer unknown fallback; affected N/A/W3 evidence; no new P/game yet.',next_watch_user_authorized=False)
atom(B/'sol/STATUS.json',st);atom(B/'sol/OPUS_WAKE.json',dict(seq=245,task=179,at=now(),note='320 input adapter and finite evidence accepted; same179 only fix narrowed-body standing pose/two-facing support, keep default off; no P/game.'))
put('HANDOFF245.json',dict(at=now(),seq=245,task=179,heads=heads,source=S,evidence_accepted320=True,whole179_accepted=False,new_game_gate=False))
print(json.dumps(dict(progress='7.189',seq=245,heads=heads,runtime_changed=False,formal_P=0,games_started=0),ensure_ascii=False))
