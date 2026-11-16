"""Record the user's execution-state boundary; queue182 after current181, no runtime edit."""
from pathlib import Path
import datetime,json,os,re,subprocess
B=Path('C:/ssbot/data/m2_play/clapper_plan');Q=B/'sol/work_packages/task182';M=Path('C:/modeling/silksong_bot');D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');V=Path('C:/Users/Meng/.codex/worktrees/forum-tv-prep/silksong_bot');G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def git(root,*a):return subprocess.check_output([G,'-C',str(root),*a],encoding='utf-8').strip()
def atom(p,d):
 t=p.with_name(p.name+'.queue182.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(t,p)
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st['source_frozen_for_P'] and not st.get('own_offline_jobs') and st['active_work_package']==181
assert not Q.exists() and read(B/'sol/OPUS_WAKE.json')['seq']==251
summary=(B/'opus/TO_SOL.md').read_text(encoding='utf-8-sig').split('## 用法',1)[0];assert re.search(r'\*\*最新编号\*\*：#322\b',summary)
rel='docs/plans/forum_clapper_l2_tactics.md';old=subprocess.check_output([G,'-C',str(M),'show','HEAD:'+rel]).replace(b'\r\n',b'\n')
assert all((r/rel).read_bytes().replace(b'\r\n',b'\n')==old for r in (D,V))
Q.mkdir()
spec=dict(task=182,title='事件驱动L2方案与规划器前台通用战术执行状态分离',at=now(),state='QUEUED_AFTER_181',authorized_to_start=False,implementation_owner='Opus',source_review_owner='Sol',baseline_source=None,baseline_rule='Sol在181当前有限集成核验及必要修复、审核/检查/实际清理完成后绑定实际源并派发；不提前实现，不需用户重复确认已指定的职责方向。',objective='后台只生成不持有执行进度的分阶段战术方案，前台通用执行器推进真实事件；引导/不引导准备站位与起跳后三去向能表达并接现有动作层，旧takeoff/intercept的规则和执行记忆分离，hold不再是假高分候选。',user_direction='引导是双阶段，执行时记录状态；后台线程算完不维护状态；takeoff/intercept要拆触发规则与状态，hold不应是L2战术，应改通用格式放到规划器一侧。',scope=['保持181原范围，当前不启动182。唯一规格在本文件，设计章节在L2文档。','后台输入快照/必要已承诺段及交还范围，输出完整、不可变且绑定实例/代际/时域/状态支持域的方案；任务算完结束，不写前台执行记忆。','规划器前台一侧设通用战术执行器，保存活动方案/阶段、已处理事件、等待/受阻/过期/完成及合法替换边界；不把怪专用状态散进普通轨迹评分器或刀口链。','takeoff/intercept是有策略含义的触发规则，并非全部只是状态；触发条件迁入方案分支或通用即时应答，departed/intercept持有及结束记忆迁入执行器。不能直接删除触发条件造成漏应答。','拦截hold变为活动阶段的继续执行；middle_jump hold变为条件不足/需重算或有界等待结果，不以95/140分空方案竞争。keep焦点偏好与执行保持要分清。','前摇阶段依据当前动作合法交还时刻/届时位置速度范围及瞄准前可达时间决定引导；不由前摇瞬间GROUND/can.input一票否决。','不引导的准备目标为走路怪朝两怪中间一侧攻击；提前描述留中间、钻跳怪、翻走路怪三个目标站位与适用条件，在实际瞄准锁定/起跳事件轻量确认。','事件驱动、常驻后台、完整发布、同事件最新请求合并；前台每帧非阻塞取结果和身份/时效/支持域检查，不等后台、不逐事件起计算线程。','优先复用现有进程/通信/发布机制；原建场只接锁定后场景，新的锁定前任务要有独立有效域。保留唯一发键权威，不让后台发键或中途覆盖已发输入/旧锤责任。','不新造全游戏DSL/全场模拟器/无界在线搜索。复用现有接近/动作层，不为提供三分支正例放宽未知几何。','迁移验收后清掉被替代的L2私有执行状态与空hold候选，避免永久双权威；旧漏斗评分仅在对应职责确认被接替后关对应项，不顺带删其他场分量。'],acceptance={'design':'先集中核方案/执行状态的归属、有效期与已承诺动作交还接口；按workflow需要时复用Astra/xhigh关键审，不重复普通全面审。','offline':['实际生产L2→前台阶段推进→policy/planner/B2→before_send/sent有限正例，标真实输入/合成部分；每个新增执行分支有实际执行证据。','覆盖引导准备跨空地/不可控段、到位/来不及/未知、瞄准锁定后三分支选择；不可实现的动作明确拒绝，不用Clear桩冒充。','异步晚到/乱序/实例变更/过期/失效、无新结果、重置、worker失败及关闭核验；后台完成不等于结果可采用。','与181证据相接：连续弹起中换意图不串目标时钟/锤尾责任，不改已发前缀。'],'performance':'功能成立后给受影响完整tick入口，由Sol沿固定executor和原资源/独占门只补必要窗口；不能只报后台构建时间。','live':'没有新的实机许可，旧停止/AA/原始录制保持。'},delivery='完整工作包一次交源码、方案/执行映射、必要生产正例与边界、性能入口、未覆盖项；主计划Sol单写。')
atom(Q/'TASK.json',spec)
plan=M/'docs/plans/forum_clapper_plan.md';t=plan.read_text(encoding='utf-8-sig');assert '进度7.196' not in t
top='2026-10-27 起草（历史审阅与阶段规格保留）。**当前进度（11-06，7.196）：181继续核连续弹起对刀叠加L2换目标，Root23检查/4组件变体通过，完整生产证据待交，已核运行源仍9f6da156。用户明确后台L2只生成方案、前台通用执行器持有阶段；takeoff/intercept拆触发与记忆、hold不作独立高分战术。方向已入L2设计，Task182排在181收尾后，尚未启动/绑定源；无新实机许可，原动作责任与默认开关保持。**'
t,c=re.subn(r'2026-10-27 起草.*?(?=\n\n)',top,t,count=1,flags=re.S);assert c==1
t+='''

#### 用户明确L2无执行状态生成/前台通用执行器边界，182排队，181不扩范围（11-06，进度7.196）

用户指出引导有两个阶段，后台在执行前生成方案，计算任务完成即结束；执行状态应放规划器前台的通用格式，takeoff/intercept及hold需厘清归属。Sol已原位补L2文档“后台生成与前台执行分离”，当前空地表仍描述9f同步源码，不把新设计写成已实现。takeoff/intercept保留策略触发含义，其departed/intercept持有/是否处理过某次起跳等历史迁前台；旧拦截hold作为阶段保持，middle_jump无路线hold作为条件不足/重算状态，均不靠95/140空候选获胜。不得纯删触发入口而漏掉背后来跳等应答。

后续182唯一说明sol/work_packages/task182/TASK.json，QUEUED_AFTER_181、authorized_to_start=false、baseline空；181既有完整路径核验及必要修复/审核/清理技术收尾后由Sol绑定真实源一次派发，不要求用户重复确认已给出的职责方向，也不现在改源码。目标是无状态后台事件方案+前台通用阶段执行：准备引导或去走路怪面前砍，按合法交还/届时状态/瞄准余时判断；锁定后三个明确去向及条件可预先表达，前台读完整结果再核实例/代际/时效/状态支持和交还。算完任务结束、worker可常驻，后台不发键。格式保持小且通用，不新造大DSL/全场搜索，不放宽动作几何或把已发前缀/旧锤责任清掉。复用异步框架须处理其原锁定后域，关旧漏斗项须先确认职责被接替，不顺带删其他场分量。

当前181仍唯一活动包，Opus源码owner不变；本次只更新设计/任务队列，源、运行开关、P/实机授权均不变。没有新测试/重计算/游戏。下一阶段核心接口需按workflow集中核设计与关键交还，再给真实生产执行/异步失效证据，不用组件检查冒充闭环或全状态安全。seq252仅让Opus知181继续、182排队勿提前，普通ACK不触发唤醒。
'''
plan.write_text(t,encoding='utf-8');heads={}
for root in (M,D,V):
 for f in ('docs/plans/forum_clapper_plan.md',rel):
  if root!=M:(root/f).write_bytes((M/f).read_bytes())
 git(root,'diff','--check','--','docs/plans/forum_clapper_plan.md',rel);git(root,'add','--','docs/plans/forum_clapper_plan.md',rel);git(root,'commit','-m','docs: separate tactical generation from execution state','--','docs/plans/forum_clapper_plan.md',rel);heads[str(root)]=git(root,'rev-parse','HEAD')
mail='''## seq252 / 181继续原核验；用户指定L2生成/执行分离方向已入182排队，勿提前实现

用户最新要求：引导双阶段，后台L2仅生成，任务算完无执行状态；前台规划器侧通用执行器保存阶段。takeoff/intercept要拆策略触发与departed/持有等执行历史；hold是执行保持/受阻等状态，不宜作为后台高分战术。L2文档新“后台生成与前台执行分离”段记录完整，当前空地表仍是9f源码现状，不改称已实施。

当前Task181唯一活动，继续seq251完整连弹/L2换目标核验与确有反例才最小修复，不扩大异步架构。Task182已建唯一说明sol/work_packages/task182/TASK.json，排队在181当前包必要审核/清理收尾之后，baseline空、不可提前开始；Root届时绑定源派发，无需为此ACK编号唤醒。

182将考虑小型通用事件方案格式：绑定实例/时域/状态支持，准备阶段及三个去向/切换条件；后台不持有执行记忆、不发键，前台记录进度/已处理事件及合法交还。触发条件要保留，不能直接删takeoff/intercept造成漏应答；空hold不能再以95/140赢。现有异步进程/发布可复用，锁定前任务不能沿用原锁定后域。旧场职责被接替才关对应项，已发前缀和锤尾责任不变。当前没有新实机许可。

'''
mp=B/'sol/TO_OPUS.md';mp.write_text(mail+mp.read_text(encoding='utf-8-sig'),encoding='utf-8')
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st['source_frozen_for_P'] and st['active_work_package']==181
st.update(at=now(),current_head=heads[str(D)],current_plan='7.196',plan_progress='7.196',queued_work_package=182,queued_work_package_spec=str(Q/'TASK.json'),queued_work_package_state='QUEUED_AFTER_181',queued_work_package_start_authorized=False,l2_execution_design='Background pure proposal generation; foreground generic executor owns progress/event history, queued182 after181',next_phase='181 integration audit remains active;182 execution-state/async migration queued, not started; no new game.')
atom(B/'sol/STATUS.json',st);atom(B/'sol/OPUS_WAKE.json',dict(seq=252,task=181,at=now(),note='181 remains current task from251. New user execution-state boundary documented;182 queued after181, do not start. No ACK wake.'))
print(json.dumps(dict(plan='7.196',active=181,queued=182,queued_start_authorized=False,seq=252,runtime_changed=False,new_games=0,heads=heads)))
