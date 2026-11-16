"""Correct the design for user review; no Opus message, wake, dispatch or runtime edit."""
from pathlib import Path
import datetime,json,os,re,subprocess,hashlib
B=Path('C:/ssbot/data/m2_play/clapper_plan');M=Path('C:/modeling/silksong_bot');D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');V=Path('C:/Users/Meng/.codex/worktrees/forum-tv-prep/silksong_bot');Q=B/'sol/work_packages/task182';G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe';REL='docs/plans/forum_clapper_l2_tactics.md'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(r,*a):return subprocess.check_output([G,'-C',str(r),*a],encoding='utf-8').strip()
def atom(p,d):
 t=p.with_name(p.name+'.userreview.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(t,p)
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st['source_frozen_for_P'] and not st.get('own_offline_jobs') and st['active_work_package']==181
assert read(B/'sol/OPUS_WAKE.json')['seq']==252
summary=(B/'opus/TO_SOL.md').read_text(encoding='utf-8-sig').split('## 用法',1)[0];assert re.search(r'\*\*最新编号\*\*：#322\b',summary)
communications={n:sha(B/'sol'/n) for n in ('TO_OPUS.md','OPUS_WAKE.json')}
old=subprocess.check_output([G,'-C',str(M),'show','HEAD:'+REL]).replace(b'\r\n',b'\n');assert all((r/REL).read_bytes().replace(b'\r\n',b'\n')==old for r in (D,V))
text=(M/REL).read_text(encoding='utf-8-sig');proposal=text.split('## 拟议设计 待用户审阅',1)[1].split('## 当前实现状态的含义',1)[0]
assert '全部在瞄准阶段完成' in proposal and '整个L2的所有战术条目都不设大黄蜂的空地准入要求' in proposal
assert '前台不能在起跳时重新给三个分支报分择优' in proposal and '用户明确确认前，不向Opus派发Task182' in proposal
assert '瞄准锁定/起跳后，在' not in text
width=None
for line in text.splitlines():
 if line.startswith('|'):
  n=len(line.split('|'))-2
  if width is None:width=n
  else:assert n==width,line
 else:width=None
# The existing internal queue record becomes a blocked draft. It is not dispatched or sent.
spec=read(Q/'TASK.json');assert spec['state']=='QUEUED_AFTER_181' and not spec['authorized_to_start'] and spec['baseline_source'] is None
spec.update(at=now(),state='DRAFT_AWAITING_USER_DESIGN_REVIEW',authorized_to_start=False,user_design_approval_required=True,user_design_approved=False,auto_dispatch_after_181=False,design_document=str(M/REL),baseline_rule='先由用户审阅并明确确认设计，再由Sol在181必要收尾后绑定实际源和派发；不能仅因181完成而自动启动。',objective='后台L2无执行进度地生成方案；整个L2不设英雄空地准入门；两怪中间一只起跳的三分支目标、适用比较和选择全部在瞄准阶段确定，前台只推进已选路线。',user_direction='三个分支必须都在瞄准阶段确定；整个L2没有任何条目需要检查大黄蜂空地要求。设计先写给用户看好，再给Opus任务。')
spec['scope']=[s for s in spec['scope'] if not s.startswith('前摇阶段依据') and not s.startswith('不引导的准备目标')]
spec['scope'][0]='当前仅为待用户审阅的内部草案，不向Opus派发，不允许提前实现；181继续原核验。'
spec['scope'].extend(['整个L2所有战术条目不得以英雄当前GROUND/AIR为准入门；当前can.input也不能直接否决整段方案。具体姿态可达性与执行完成确认归前台/动作模型。','瞄准阶段完成引导/不引导准备方案，以及留中间/钻跳怪/翻走路怪三候选的确定站位、适用性、比较和选择；方案锁定前已有selected_branch，起跳事件不能再做正常三选一。','实际观测超出计划支持域时方案失效并走通用保护/请求重算，不把这种异常处理当作把正常选择延期到起跳后的理由。'])
spec['acceptance']['offline']=[s.replace('覆盖引导准备跨空地/不可控段、到位/来不及/未知、瞄准锁定后三分支选择；不可实现的动作明确拒绝，不用Clear桩冒充。','覆盖引导准备跨空地/不可控段、到位/来不及/未知；记录瞄准锁定前已完成三候选及选择，锁定/起跳后只执行已选路线。具体动作不可达要明确，不用Clear桩冒充。') for s in spec['acceptance']['offline']]
spec['acceptance']['offline'].append('在相同交还/可达预测结果下，单独改变英雄当前空地标志不得导致任一L2候选被准入门拒绝；检查不限于guide，也覆盖over等所有条目。')
atom(Q/'TASK.json',spec)
plan=M/'docs/plans/forum_clapper_plan.md';p=plan.read_text(encoding='utf-8-sig');assert '进度7.197' not in p
top='2026-10-27 起草（历史审阅与阶段规格保留）。**当前进度（11-06，7.197）：181继续原连弹/L2换目标核验，已核源仍9f6da156。L2设计已按用户纠正：三分支站位/适用性/比较选择全部在瞄准阶段确定，整个L2不设英雄空地准入门；锁定/起跳只推进已选路线。Task182改为待用户审阅设计的内部草案，未确认不派发、不因181完成自动启动。当前仅改文档，无新源码/P/game。**'
p,c=re.subn(r'2026-10-27 起草.*?(?=\n\n)',top,p,count=1,flags=re.S);assert c==1
p+='''

#### 用户纠正三分支决策时刻与全L2空地门，先看设计后派任务（11-06，进度7.197）

用户明确：英雄在两怪中间且一只起跳，三个分支必须都在瞄准阶段确定；整个L2不应有任何战术条目检查英雄空地要求。随后要求先把设计写给用户看好，再给Opus任务。Sol上一版仍写锁定/起跳后选分支，且只写“前摇瞬间不一票否决”，未准确落实；本次纠正为瞄准阶段完成三确定站位、适用性/比较及selected_branch，正常起跳时不重做三选一。整个L2无GROUND/AIR资格门，当前可输入状态不能替代合法交还到截止前的可达性；具体动作/落地完成确认归执行层。实际变化越出支持域才失效/请求重算，不借异常处理将正常决策延后。

L2文档改为“战术设计与实现状态”，将拟议设计置于当前源码清单之前，两条硬要求明确列出。原9f空地表继续作为待迁移的现有代码限制，不篡改为实现已完成。前台执行器只推进已选阶段，takeoff/intercept拆规则与事件记忆、hold退出高分候选等方向保留。旧漏斗评分的退休仍需确认职责接替，不顺删其他分量。

Task182内部记录由QUEUED_AFTER_181改DRAFT_AWAITING_USER_DESIGN_REVIEW，authorized_to_start=false、user_design_approved=false、auto_dispatch_after_181=false；原“181完成后无需重复确认自动绑定派发”的安排被本次用户审阅要求覆盖。181仍当前唯一任务。此次不改Sol→Opus邮件/OPUS_WAKE，不发新任务/消息/唤醒；只供用户先审设计。无运行源码/开关/测试/性能/游戏变更，旧实验边界保持。
'''
plan.write_text(p,encoding='utf-8');heads={}
for root in (M,D,V):
 for rel in ('docs/plans/forum_clapper_plan.md',REL):
  if root!=M:(root/rel).write_bytes((M/rel).read_bytes())
 git(root,'diff','--check','--','docs/plans/forum_clapper_plan.md',REL);git(root,'add','--','docs/plans/forum_clapper_plan.md',REL);git(root,'commit','-m','docs: clarify pre-aim L2 design for user review','--','docs/plans/forum_clapper_plan.md',REL);heads[str(root)]=git(root,'rev-parse','HEAD')
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st['source_frozen_for_P'] and st['active_work_package']==181
st.update(at=now(),current_head=heads[str(D)],current_plan='7.197',plan_progress='7.197',queued_work_package_state='DRAFT_AWAITING_USER_DESIGN_REVIEW',queued_work_package_start_authorized=False,l2_design_user_review_required=True,l2_design_user_approved=False,l2_execution_design='DRAFT: all three routes decided during aim; no hero ground/air admission gates anywhere in L2; foreground only executes selected stages',next_phase='181 original integration review remains active.182 draft awaits explicit user design review before any dispatch; no new game.')
atom(B/'sol/STATUS.json',st)
assert all(sha(B/'sol'/n)==h for n,h in communications.items())
assert (M/REL).read_bytes()==(D/REL).read_bytes()==(V/REL).read_bytes()
print(json.dumps(dict(plan='7.197',design=str(M/REL),state=spec['state'],opus_message_changed=False,opus_wake_changed=False,active=181,heads=heads),ensure_ascii=False))
