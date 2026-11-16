"""Close Root's bounded E checks and dispatch the requested integration audit only."""
from pathlib import Path
import datetime,hashlib,json,os,re,subprocess,psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/l2_bounce_interop_20261106';Q=B/'sol/work_packages/task181';M=Path('C:/modeling/silksong_bot');D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');V=Path('C:/Users/Meng/.codex/worktrees/forum-tv-prep/silksong_bot');S='9f6da15674da8c396d729a680f6868d47d9e233f';G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,d):
 assert not p.exists(),p;p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def atom(p,d):
 t=p.with_name(p.name+'.interop181.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(t,p)
def git(r,*args):return subprocess.check_output([G,'-C',str(r),*args],encoding='utf-8').strip()
st=read(B/'sol/STATUS.json');job=read(A/'ROOT_JOB.json');assert not st['live_or_budget_running'] and not st['source_frozen_for_P'] and st['own_offline_jobs']==[job]
try:assert abs(psutil.Process(job['pid']).create_time()-job['created'])>=.01
except psutil.NoSuchProcess:pass
assert read(A/'ROOT_JOB_END.json')['error'] is None and read(A/'REVIEW_CHECKS.json')['pytest_rc']==0
packet=read(B/'analysis/task180_l2_322_20261106/SOURCE_PACKET.json');assert all(sha(D/n)==h for n,h in packet['raw_runtime_files_sha256'].items())
summary=(B/'opus/TO_SOL.md').read_text(encoding='utf-8-sig').split('## 用法',1)[0];assert re.search(r'\*\*最新编号\*\*：#322\b',summary) and read(B/'sol/OPUS_WAKE.json')['seq']==250
assert not Q.exists() and st['active_work_package'] is None and not git(D,'diff','--name-only')
put(A/'ROOT_CHECK_CLEANUP.json',dict(at=now(),job=job,actual_exit=True,pytest_passed=23,component_variants=4,source_files_unchanged=716,new_games=0,formal_P=0))
st.update(at=now(),phase='L2_BOUNCE_INTEROP_COMPONENT_CHECKS_CLEAN',own_offline_jobs=[]);atom(B/'sol/STATUS.json',st)
Q.mkdir()
spec=dict(task=181,title='连续弹起对刀与L2换目标的真实交还及发键组合核验',state='DISPATCHED_TO_OPUS',authorized_to_start=True,at=now(),implementation_owner='Opus',source_review_owner='Sol',formal_P_live_owner='Sol',workspace=str(D),baseline_source=S,baseline_source_packet=str(B/'analysis/task180_l2_322_20261106/SOURCE_PACKET.json'),objective='核清同目标连续表运行期间与真实弹起交还时L2换目标，是否遗漏或串用旧目标时序、旧刀/锤尾责任和已发键；发现具体bug则在同包最小修复，未发现也交明确有限证据和实际生效边界。',user_request='冲锤的空中对刀在连弹的时候，叠加上L2换目标需要看看有没有bug',scope=['只做这组集成核验及确有反例的必要修复，不在此包迁移整个L2异步、不新增跳跃打法或改评分。','复用309连续表、target_entry_attack及现有生产输入/回放接口。连续表仍明确同目标、默认关闭；有限表的跨目标能力不得虚报。','至少覆盖连续表已持有时收到新目标、真实下一刀命中弹起时接新目标，以及旧锤2未结束/已结束两种责任边界。','已发送/待生效输入不可撤回或平移；L2目标意图何时实际生效须明确，不能把意图变化等同抢占已承诺动作。','旧目标与新目标的招式实例/时钟/命中/保护窗口不得互借。换怪后仍核当前几何、旧锤尾及新怪实际状态。','未发现具体反例不为测试通过顺改控制行为；源/日志/失败原件和默认开关保留。'],existing_checks=str(A/'REVIEW_CHECKS.json'),existing_check_scope='Root E24-31/Idle23 existing checks +4 component checkpoint variants passed; no full policy replay/P/game; table verification stubbed in those unit tests.',acceptance={'offline':['给经过实际L2目标输出、policy/planner/B2几何、before_send/sent的有限完整正例，至少一条确实发出下一段动作；不是只改prefs或helper返回正确。','对暂缓换目标的情况记录旧行继续、实际交还/失效理由与新意图有效期；到可交还处不丢新目标，且不复用旧目标刀时序。','组件可补必要边界，但Clear几何桩不算生产正例，合成与记录条件必须标明；不将模型命中当实机。','检查默认关闭路径和原同目标正例。只有新增改动/反例才扩最小邻接测试，不重复190/1851或全部历史P。'],'performance':'只有源码运行路径确实改变且功能通过后才给受影响完整tick入口，Sol决定是否补必要P；纯证据包不重复P。','live':'没有新游戏许可。旧停止批次/AA/raw均不动。'},delivery='一次完整交付：审计结论/明确反例或未发现、源码版本（若改）、完整生产路径证据、事件/目标/承诺/发键时间线和未覆盖边界；无需中间ACK唤醒。',completion='按有限集成证据核收，不扩成所有跨怪高度/距离时序的安全证书。')
put(Q/'TASK.json',spec)
put(A/'ASYNC_DISCUSSION.json',dict(at=now(),state='DESIGN_DISCUSSION_ONLY_NOT_IMPLEMENTATION_DISPATCH',proposal='事件驱动，常驻后台计算，前台每帧非阻塞取完整结果并验证实例/代际/交还/时域/支持域；最新请求合并，旧结果不覆盖新目标。',existing_worker='scene_field_async.AsyncFieldBuilder uses worker process plus broker thread and complete publication, not per-event thread creation',limits=['No migration of L2 into async is assigned in Task181','Completed does not mean valid; geometric/contact/send checks remain foreground action authority','Python compute threads share the GIL in the current normal runtime; prefer reuse of the process framework unless actual compute releases it']))
doc=M/'docs/plans/forum_clapper_l2_tactics.md';t=doc.read_text(encoding='utf-8-sig');marker='现有精确按键承诺、几何否决和实际发键检查继续生效。';assert t.count(marker)==1
note='''连续表与换目标的交互：当前连续表只接同一目标的真实下劈命中/弹起；运行中的承诺不能被L2新意图直接改写。Root已核23项相关检查及4个组件交还变体，覆盖旧承诺保持、新目标不借旧目标时钟及锤尾仍保留。它们没有经过整段L2→生产发键路径，不能据此签整个组合通过；Task181正在补这项有限集成证据。连续表默认仍关，无新实机许可。

'''
t=t.replace(marker,note+marker);doc.write_text(t,encoding='utf-8')
plan=M/'docs/plans/forum_clapper_plan.md';t=plan.read_text(encoding='utf-8-sig');assert '进度7.195' not in t
top='2026-10-27 起草（历史审阅与阶段规格保留）。**当前进度（11-06，7.195）：Task180有限整理已核收，runtime仍9f6da156。按用户新要求检查连续弹起对刀叠加L2换目标：Root23相关检查及4组件变体通过，尚缺完整生产路径组合证据，现派发Task181只补该集成核验及有反例才必要修复。异步L2事件驱动仍是设计讨论，不在181改架构；无新实机许可，原路线/时序缺口及默认关闭保持。**'
t,c=re.subn(r'2026-10-27 起草.*?(?=\n\n)',top,t,count=1,flags=re.S);assert c==1
t+='''

#### 连弹对刀叠加L2换目标：组件核验过，派发181补完整生产路径；异步仅讨论（11-06，进度7.195）

用户要求核查冲锤空中对刀/连续弹起叠加L2换目标，并讨论事件驱动后台计算、前台逐帧取完成结果并查过期。Root实际E24–31/Idle有限23项既有检查6.40s通过，另4个组件检查覆盖活动连续表不被新意图改承诺、真实弹起交还检查点的跨目标意图释放旧表/保留旧目标实例与时钟，以及Slam2尾未消失/Recover后已消失。7关键源hash/外来模块核过，716绑定源全同，真实检查进程退出后才清自身登记；0策略重放/0P/0game，产物analysis/l2_bounce_interop_20261106。组件含预置交还检查点及309单测verification桩，不能当完整L2/几何/下一动作sent正例，也不能宣称整个组合无bug。

Task181唯一说明sol/work_packages/task181/TASK.json，Opus实现owner：复用原生产夹具，核连续表活动中换意图与真实下劈命中弹起时换目标，分别处理旧锤尾未消失/已消失，明确意图实际生效边界。已发前缀不改/时钟保护不串目标/原责任不丢，至少一个真实L2→policy/planner/B2几何→before_send/sent离线完整正例。实际接近/出刀必须执行，不用Clear桩或预置prefs代替。无具体反例不为测试顺改代码；如确需修复留在181，功能先过再由Sol定必要完整tickP，纯证据不重测。

异步讨论记录ASYNC_DISCUSSION.json：可事件触发常驻后台求值，前台每帧非阻塞读完整结果，核实例/代际/有效期/支持域/交还；完成不等于有效，最新请求合并而非每个事件起线程、旧结果不覆盖新意图。当前独立建场进程与broker/完整双缓冲机制可复用，但没有在本包实现L2异步迁移、引导改法或三分支新打法，也没有关旧漏斗评分。当前运行源、默认BOUNCE_TABLE/FACE_HOOK/BODY/AIR开关与原即时几何/发键门均不变；旧raw/AA/STOP不动，无新game gate。
'''
plan.write_text(t,encoding='utf-8');heads={}
for root in (M,D,V):
 for rel in ('docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md'):
  if root!=M:(root/rel).write_bytes((M/rel).read_bytes())
 git(root,'diff','--check','--','docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md');git(root,'add','--','docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md');git(root,'commit','-m','docs: scope bounce and L2 handoff integration review','--','docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md');heads[str(root)]=git(root,'rev-parse','HEAD')
mail='''## seq251 / Task181：按用户要求核连续弹起对刀叠加L2换目标，只补集成及有反例才修

180已收尾，runtime仍9f6da156，最新docs已同步主计划7.195；当前无在途P/game/冻结/自身E作业。用户说“冲锤的空中对刀在连弹的时候，叠加上L2换目标需要看看有没有bug”。请按唯一说明sol/work_packages/task181/TASK.json做此有限完整包，你仍唯一源码owner，直接刀口树。

Root源审未发现直接串目标的明确反例，23既有相关检查+4组件检查点变体通过，A=analysis/l2_bounce_interop_20261106；但不能据组件签整个组合通过，309里的verification是桩，交还检查点是预置。请补真实L2输出→policy/planner/B2几何→before_send/sent的有限完整正例，至少有下一段动作实际发出，覆盖连续表活动中L2新意图/真实下一刀弹起后换怪、旧锤尾未完/已完。关注已发前缀不可改、源/目标身份和时钟/保护不互借、新意图实际生效边界及可交还时不丢目标。默认表仍同目标且关闭，不能宣布跨怪套表已覆盖。

无具体反例不要顺手改打法；有bug在181最小修复，保留旧正例/失败。复用生产夹具，不用Clear或helper改prefs代替整个路径，也不扩全场模拟/大矩阵。纯证据不重跑P；确有运行源变更且功能过后交受影响完整tick入口，由Root调P。当前无新实机许可。

用户还在讨论L2事件驱动异步：可复用现有后台进程/发布机制，前台逐帧非阻塞取完整结果并核实例/代际/时域/支持域/交还；不要每事件创建计算线程。此处是讨论，181不迁移异步架构、不改引导/三分支、不关旧场评分。请一次交完整证据/结论/必要修复，无需ACK编号唤醒。

'''
mp=B/'sol/TO_OPUS.md';mp.write_text(mail+mp.read_text(encoding='utf-8-sig'),encoding='utf-8');dispatch=dict(at=now(),task=181,seq=251,baseline_source=S,baseline_head=heads[str(D)],spec=str(Q/'TASK.json'),scope='Only requested integration review and necessary proven-bug fix; async discussion not implementation',new_game_authorization=False);put(Q/'DISPATCH.json',dispatch)
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs')
st.update(at=now(),phase='TASK181_BOUNCE_L2_INTEROP_DISPATCHED',active_work_package=181,current_head=heads[str(D)],current_source=S,current_plan='7.195',plan_progress='7.195',code_write_owner='Opus',implementation_owner='Opus',task181_spec=str(Q/'TASK.json'),code_handoff=str(Q/'DISPATCH.json'),next_phase='Opus bounded continuous bounce/L2 switch integration evidence; no async implementation or new game.',l2_bounce_component_checks=str(A/'REVIEW_CHECKS.json'),l2_bounce_component_cleanup=str(A/'ROOT_CHECK_CLEANUP.json'),next_watch_user_authorized=False)
atom(B/'sol/STATUS.json',st);atom(B/'sol/OPUS_WAKE.json',dict(seq=251,task=181,at=now(),note='Requested bounce/L2 switch full-path audit only; no new async implementation/game. No ACK wake.'))
print(json.dumps(dict(task=181,seq=251,source=S,plan='7.195',root_checks=23,component_variants=4,source_changed=False,new_games=0,heads=heads)))
