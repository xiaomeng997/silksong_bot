"""Queue user-authorized limited L2 organization AFTER current Task179 closeout. No source edits."""
from pathlib import Path
import ast,datetime,hashlib,json,os,re,subprocess
import psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');Q=B/'sol/work_packages/task180'
M=Path('C:/modeling/silksong_bot');D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');V=Path('C:/Users/Meng/.codex/worktrees/forum-tv-prep/silksong_bot')
G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def atom(p,d):
 t=p.with_name(p.name+'.queue180.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(t,p)
def git(root,*args):return subprocess.check_output([G,'-C',str(root),*args],encoding='utf-8').strip()
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs')
assert st['active_work_package']==179 and read(B/'sol/OPUS_WAKE.json')['seq']==245
summary=(B/'opus/TO_SOL.md').read_text(encoding='utf-8-sig').split('## 用法',1)[0]
assert int(re.search(r'\*\*最新编号\*\*：#(\d+)',summary).group(1))==320,'New formal delivery: handle before changing workflow metadata'
assert not Q.exists(),'Do not duplicate queued package'
me=psutil.Process();me.cpu_affinity(list(range(24,32)));me.nice(psutil.IDLE_PRIORITY_CLASS)
before={str(r):dict(head=git(r,'rev-parse','HEAD'),status=git(r,'status','--short')) for r in (M,D,V)}
for root in (M,D,V):
 assert not git(root,'diff','--name-only','--','docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md')
 assert not git(root,'diff','--cached','--name-only','--','docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md')
spec=dict(task=180,title='L2完整战术的有限统一：条件、评分、输出归属一致，公共竞争可检查',state='QUEUED_AFTER_179',authorized_to_start=False,at=now(),implementation_owner='Opus',source_review_owner='Sol',formal_P_live_stop_cleanup_owner='Sol',workspace=str(D),branch='codex/forum-knife-rows',canonical_plan=str(M/'docs/plans/forum_clapper_plan.md'),design=str(M/'docs/plans/forum_clapper_l2_tactics.md'),baseline_source=None,baseline_rule='由Sol在179当前在途修复交付、源审、必要功能与受影响P及真实清理收尾后，绑定最终已核版本并明确启动；不从当前在途a9ff或旧0b擅自起包。',kickoff_gate=dict(current_task=179,current_fix='RETURN_BODY known standing poses / both-facing shape support',source_offline_and_necessary_performance_closeout_required=True,Sol_start_record_required=True,live_uncovered_must_remain_explicit=True,not_require_100_hitless_games=True,new_game_authorization=False),objective='把每条完整战术的适用条件、适用度/评分及完整L2输出放在一起；公共选择器统一竞争。实际消除集中winner分支二次拼装/覆盖输出，不能仅把旧分支搬进helper或加包装类。',scope=[
 '范围限当前双Clapper L2战术组织及必要共用接口/测试；Opus决定合理文件边界，不新造全游戏通用框架。',
 '完整战术可以有多个事件阶段，例如bait到return归同一行为；不硬拆成13个类，也不把阶段每拍重新当独立动作竞争。',
 '候选统一携带适用条件结果/原因、分数及分量、目标、站位/攻击意图和需要的L2输出；明确所属事件、阶段、保持/退出/互斥语义。',
 '场景/几何/观测事实共用；区分观察记忆推进、候选评估与胜出后的提交。未胜出的候选不得产生新的目标或动作承诺，现有观察更新语义不能暗改。',
 '公共选择器不按战术名字另写特判；已有互斥和保持关系可声明化，但不能在结构整理里擅自删除或改变。公共应用仅应用赢家结果与明确共用约束，不再按winner名字拼一遍战术输出。',
 '保留现有评分/适用度/换目标成本/同分保持、触发周期、事件身份、阶段转移和失效条件；原战术不完善处如实记录，发现问题另列，不顺带改打法。',
 '不新增成团第二打法，不改动作链/预测/几何/输入HF/资源门/默认开关，不在此包实现新风险策略。'],
 anti_shell_acceptance=[
 '增加或修改某条战术时，其条件、得分与目标/站位/攻击输出在同一战术单元中可定位，不必再去decide尾部修改一个平行winner分支。',
 '公共选择器和共用应用代码不出现按具体战术ID决定行为的第二份权威规则；确属共用动作/安全约束的后处理须清楚列明。',
 '日志能给出候选未适用/被互斥/评分输赢/保持退出原因及赢家输出，最终实际发键仍由现有动作所有者判断，不能把L2获胜当动作成功。'],
 evidence=dict(offline=[
 '使用179收尾绑定版本和相同真实输入/配置作对照，复用当前测试及明确场景，检查事件跨帧阶段/换目标/返回/失效。',
 '逐拍核目标、站位、EntryAttack、no_hit/攻击偏好、return_body/ReturnRequest等实际生效L2输出，并核必要生产policy/planner/B2/最终按键；不能只比较赢家名字或helper。',
 '记录首次差异；意外差异要修复或作为单独行为变更交Sol裁定，不能为了通过比较抹掉差异。保持当前原始失败数据。',
 '固定输入一致仅是所覆盖路径的回归证据，不证明所有未来状态等价、不以稳定100盘无伤为本包前置，也不冒充完整战术实机通过。'],performance=[
 '事实共享且保持原触发频率；不为每个候选重复建几何/做rollout/深复制场景；不加插件反射或动态配置解析热路径。',
 '先功能再性能；给同场景对照的L2局部成本与完整tick受影响入口，正式P由Sol沿固定executor和原资源/独占门执行，只补确需的窗口，不重跑大矩阵。'],live='本包授权不扩大实机范围；178/179已有未覆盖或失败仍分别保留，结构整理验收不替代它们。'),delivery='一个完整包：源码直接落约定开发树，提交/变更说明、候选映射、相关测试和完整生产路径证据、性能入口、未覆盖/风险说明一并交付；main主计划Sol单写。',completion='按源码/离线/性能/实机分别登记；本次有限结构整理以声明范围实际归拢及受影响检查通过为准，不用整场无伤承诺作替代。',source_entries=['brain/ssbot/combat/tactics/clapper_priority.py','brain/ssbot/combat/tactics/clapper_middle.py','brain/ssbot/combat/tactics/modes.py','brain/ssbot/combat/tactics/gauntlet.py'],tools='复用既有测试、179已修逐包HF夹具与固定性能executor；仅在确需关键阶段/语义裁决时按workflow复用指定Astra/xhigh，不为普通派单额外调用。')
Q.mkdir();(Q/'TASK.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
doc=M/'docs/plans/forum_clapper_l2_tactics.md';text=doc.read_text(encoding='utf-8-sig');assert '## 已授权的有限整理' not in text
marker='## 适用配置与源码入口'
section='''## 已授权的有限整理（Task180，排队）

用户要求先收尾当前 Task179，再由 Opus 做有限整理；当前尚未启动 Task180。唯一任务说明在 `C:/ssbot/data/m2_play/clapper_plan/sol/work_packages/task180/TASK.json`，基准版本由 Sol 在179本次在途修复及必要审核、性能核验和清理收尾后绑定，不提前拿未交付版本开工。

整理须把每条完整战术的适用条件、评分和完整 L2 输出归拢，公共选择器统一竞争；同时明确事件阶段、互斥、保持与退出关系。`bait → return` 可以是同一完整战术的两个阶段，无需硬拆成多个独立竞争者。战术内部可复用现有逻辑，但公共代码不能继续按赢家名字再拼装一遍目标、站位和攻击意图，不能只加包装类或搬函数。

场景事实共享，观察记忆更新、候选评估及赢家提交职责分清；保留已有分数、换目标成本、触发频率、阶段条件及动作所有权。本包不顺带新增成团第二战术或修改打法，也不改刀口链、几何和默认开关。

核对固定输入下的目标、站位、攻击意图、相关 L2 字段及必要最终按键，用来发现所覆盖路径的意外改动；这不等于证明全场行为不变，也不以100盘无伤为整理前提。只补受影响检查及必要性能对照，既有178/179实机未覆盖项单列保留，不用整理完成替代。

'''
assert text.count(marker)==1;text=text.replace(marker,section+marker);doc.write_text(text,encoding='utf-8')
tree=ast.parse((D/'brain/ssbot/combat/tactics/clapper_priority.py').read_text(encoding='utf-8-sig'));scores=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='DEFAULT_SCORES' for t in n.targets));assert {k:float(v) for k,v in re.findall(r'^\| `([^`]+)` \| (\d+) \|',text,re.M)}==scores
plan=M/'docs/plans/forum_clapper_plan.md';p=plan.read_text(encoding='utf-8-sig');assert '进度7.190' not in p
top='2026-10-27 起草（历史审阅与阶段规格保留）。**当前进度（11-06，7.190）：用户已授权L2有限整理，条件、分数、完整输出归同一战术单元，公共择优，不只套壳；Task180排在当前179收尾后，尚未启动。当前仍先收179的RETURN_BODY站立姿态/两朝向身体支持域修复，最新正式交付320已核；开发树已有321在途提交且测试仍在改，不能算已交付/通过。219拍P及原清理记录保留，默认开关和实机权限不因整理授权改变；当前没有新实机启动许可。**'
p,c=re.subn(r'2026-10-27 起草.*?(?=\n\n)',top,p,count=1,flags=re.S);assert c==1
p+='''

#### 用户授权有限整理但须先收当前包；Task180已备完整规格、尚未启动（11-06，进度7.190）

用户明确“条件、分数和输出放到一起，别只套一层壳；先把当前这包收尾，再让Opus做整理”。现仍以179为唯一活动实现包，正式收信停在320；实际刀口树已有a9ff2785的321身体联合提交，test_return_body321.py尚在修改，报告未新交，未读成通过，也未擅自运行其检查/正式P或切换实现任务。179继续按seq245闭合站立姿态/双朝向支持域的N反例、A顶上完整生产正例与W3落缝/侧劈范围，必要受影响P与真实清理仍由Sol负责，既有178/179实机未覆盖项目分别保留。

新增sol/work_packages/task180/TASK.json为一个完整的下一包说明，状态QUEUED_AFTER_179、authorized_to_start=false、baseline_source=null。由Sol在179当前在途范围交付、独审、必要功能/性能核验与清理收尾后绑定最终已核基准并明确启动；不把稳定100盘无伤当整理前提，不拿整理完成替代原实机验收。本次只是授权落地与排队，不写控制源码、不抢Opus实现，不新开聊天/定时任务/实机。

180边界为当前双Clapper L2有限统一：完整战术自含适用条件/适用度和评分、目标/站位/攻击及相关L2输出，明确事件阶段/保持/退出/互斥；公共选择器与应用层不再按winner名字另有第二份权威行为分支。允许复用现有阶段函数，但不能只搬helper或套类。场景事实共享，分清观察记忆推进、候选评估与赢家提交，避免未选战术产生新承诺；保留已有分数/同分保持/切换成本/触发周期和动作所有权。成团bait→return可归同一完整战术，不能硬凑13个类。已有过滤声明化不等于删除硬条件，新增成团第二打法等功能另包。

验收实际检查条件/分数/输出归属及无中央二次战术拼装，复用179收尾后的固定输入对照目标/站位/EntryAttack/no_hit/攻击偏好/return_body/ReturnRequest与必要生产最终键；首次差异明确登记，不能把意外行为变更混作结构整理。固定输入一致只限已有路径，不宣称全状态等价；性能先功能后取受影响L2局部与完整tick同条件对照，不为每候选复制场景或新增rollout，不重复大矩阵。该范围已写入L2现状文档，同main/刀口/TV仅同步文档；源码owner仍Opus、计划Sol单写，原资源/停止/输入/清理/开关与实机许可边界不变。seq246只补当前179收尾顺序与180排队规格，不触发当前实现切换，普通ACK不需唤醒。
'''
plan.write_text(p,encoding='utf-8')
heads={}
for root in (M,D,V):
 for rel in ('docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md'):
  if root!=M:(root/rel).write_bytes((M/rel).read_bytes())
 git(root,'diff','--check','--','docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md')
 git(root,'add','--','docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md')
 git(root,'commit','-m','docs: queue limited L2 organization after current closeout','--','docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md');heads[str(root)]=git(root,'rev-parse','HEAD')
mail='''## seq246 / 用户顺序约束：继续先收179；有限L2整理已排Task180，当前不要切换

用户明确授权：条件、分数、输出放到一起，不只套壳；先把当前这包收尾，再让Opus整理。主计划7.190和L2清单已同步，下一包唯一规格：sol/work_packages/task180/TASK.json。状态QUEUED_AFTER_179，authorized_to_start=false、基准未绑定；这不是让你现在停179去做180。仍先按seq245交齐当前身体支持域修复的N/A/W3必要证据，Sol完成独审和必要受影响P/清理后再明确放行180。当前见a9ff321在途和测试修改，不当已正式交付或已通过；你保留唯一源码owner，Sol没有改运行源。

180是一个完整的有限整理包：每条完整战术把条件/适用度、分数、目标/站位/攻击及相关L2输出归一处；事件阶段/互斥/保持/退出明确。公共选择和应用不按winner名字另有第二份权威战术输出分支，不能只套类/搬helper。可复用原阶段函数，观察更新与候选评估/赢家提交职责分清，事实共享，不为每候选重做几何/rollout。保留原分数、切换成本、同分保持、触发周期和动作所有权；不顺带新增第二打法、不改刀口链/几何/输入/开关。文件拆分和具体接口由你设计，不硬凑13类或造全游戏框架。

用179收尾最终已核基准对照实际目标/站位/EntryAttack/no_hit/相关字段与必要最终发键；这只是已有路径的回归证据，不承诺全局行为不变，也不等100盘无伤才整理。意外语义差异另列，实机未覆盖继续如实记178/179，不以整理替代。正式P与实机仍由Sol、当前无新局许可；不需要ACK或另开任务/聊天。当前先交179实质收尾结果，别并行改L2。

'''
mp=B/'sol/TO_OPUS.md';mp.write_text(mail+mp.read_text(encoding='utf-8-sig'),encoding='utf-8')
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs') and st['active_work_package']==179
st.update(at=now(),current_plan='7.190',plan_progress='7.190',current_head=heads[str(D)],queued_work_package=180,queued_work_package_spec=str(Q/'TASK.json'),queued_work_package_state='QUEUED_AFTER_179',queued_work_package_start_authorized=False,inflight_implementation_head=before[str(D)]['head'],next_phase='Finish179 current support-domain correction and required review/P/cleanup first; bind final baseline then Sol release queued180 limited L2 organization. No new game permission.')
atom(B/'sol/STATUS.json',st);atom(B/'sol/OPUS_WAKE.json',dict(seq=246,task=179,at=now(),note='User authorized limited L2 organization as queued180 AFTER current179 closeout. Continue179 now; do not switch or parallel-edit L2.'))
receipt=dict(at=now(),task=180,state='QUEUED_AFTER_179',start_authorized=False,baseline_bound=False,current_task=179,source_edits_by_Sol=0,new_formal_P=0,new_games=0,heads=heads,before=before,plan_sha256=sha(plan),L2_doc_sha256=sha(doc),spec_sha256=sha(Q/'TASK.json'),score_rows_verified=len(scores),metadata_job=dict(pid=me.pid,created=me.create_time(),cpus=me.cpu_affinity(),priority=me.nice()),mail_seq=246)
(Q/'QUEUE_RECEIPT.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(plan='7.190',queued=180,active=179,start_authorized=False,seq=246,heads=heads),ensure_ascii=False))
