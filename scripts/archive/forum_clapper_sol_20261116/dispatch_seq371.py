from pathlib import Path
from datetime import datetime, timezone
import json
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
B = Path('C:/ssbot/data/m2_play/clapper_plan')
R = B / 'analysis/committed388_20261111'
H = 'd7cbe1a59cbee1d8fa8d40c53fc57b3ed1bd2b19'
git = 'C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
wt = 'C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot'
head = subprocess.check_output([git, '-C', wt, 'rev-parse', 'HEAD'], text=True).strip()
assert head == H, head
now = datetime.now(timezone.utc).isoformat()
findings = {
    'at': now, 'delivery': 432, 'closes_task': 370, 'source': H,
    'disposition': 'direction supported; proposed production specification not accepted; bounded evidence/prototype repair requested',
    'new_P_or_game': False, 'production_code_authorized_by_this_task': False,
    'astra_review': {'agent': '/root/walk418_review', 'role': 'existing Astra critical-assumption review',
                     'conclusion': 'no fixed k9 gate or naked early handback; first normal-node readiness diagnostic D, bounded offline comparison'},
    'root_independent_evidence': [
        {'issue': 'same-cause cohort contains a post-handoff start', 'episode': 24,
         'landing': 76539, 'Slam_Antic': 76540, 'damage': 76597, 'HP': 2,
         'owners': 'two:idle at landing; slam from +1; plan from +55',
         'evidence': 'r6/between_all_tv429.json and between_tv429.txt',
         'conclusion': 'not a middle route holding keys throughout an already-started new windup'},
        {'issue': 'k<=9 sample mixes attack ownership', 'reported': 11,
         'same_bounced_actor_restarts': [[8,29181],[13,44758],[19,62496],[24,76445],[37,112424]],
         'other_actor_remaining': 6, 'evidence': 'r6/between_scope_tv429.txt',
         'conclusion': 'not 11 independent examples of other-actor early windup'},
        {'issue': 'known positive above k9', 'episode': 30, 'landing': 93175, 'windup_k': 17,
         'root_distance_u': 5.58, 'outcome': 'ground script takes over and hits Slam0',
         'conclusion': 'fixed k9 is not a demonstrated feasibility boundary'},
    ],
    'specification_cautions': [
        'Quote135 concerns the initiation during recovery/overhead, not an established whole-link recovery invariant',
        '111 already-free-at-landing examples do not establish 111 invalid entries',
        '20-40 frames remaining does not prove receiver admission; include prefix, pose, cooldown, other-state/runes and same-slam budget',
        'Do not invent new mid-link nodes and call them normal completion',
        'No demonstrated preventable HP quantity; same-seed batch differences remain descriptive',
    ],
    'next_task': 371, 'wake_enqueued': False, 'listener_received': False, 'actual_author_started': False,
}
(R / 'REVIEW432.json').write_text(json.dumps(findings, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
mail = '''## seq371（#432同包窄修）：先纠正分类，再做2坏1好正常节点/接管就绪离线对照；不批准固定k9或裸交还

用户继续按计划的授权不变；第3项仍由你负责。Sol及既有Astra重点审核已完成：方向有证据，但#432目前不能直接定B、不能给用户“9帧后接不住”的选择。此为seq370同一包的审核跟进，不加新功能/游戏/P；当前源已核仍d7cbe1a5。

请先原位更正唯一设计/交付的三处事实（复用现成小表，不重跑114整组）：
1. ep24：L76539，另一只2554514在76540（落地后1帧）才Slam Antic，76597撞身体。between_all_tv429中owners是落地two:idle、+1 slam、+55 plan；between_tv429也显示land=-58、SlamAntic=-57。不能把这2HP也写成middle途中起招、脚本一直没被问，11例不是已经证明的同一种可修原因。其余逐例保留，跳招/冲锤/交还前后别混。
2. <=9的11例里，e8 L29181、e13 L44758、e19 L62496、e24 L76445、e37 L112424是被踩slammer自己再Slam Antic，other为Idle/Walk等。不能全记成“另一只冲锤”的早接对照。给正确actor绑定和未知项；114中2例认不出原slammer和1例仍后摇等统计分母单列，别漏组。
3. ep30 L93175 k17在5.58u成功接住，已经说明k9不是可行性边界。A把原话135的发起时后摇/头顶，强化成了落地或全程仍后摇；111例落地已自由不能证明111例发起超范围。不要让用户在这个错误二选一上决定。

然后在**分析树/离线原型**只做ep0、ep22坏例和ep30正例，不先做10+11矩阵，不改生产树。按Astra的D和明确标注反事实的B比较：
- D最小项：沿用middle的真实完成点——实际落地且英雄盒在两怪身体间。只在既定T-3/T-2提前问询/准备后手，从包含已发键/保持键的预计交还状态问现成接锤；实际完成时再核姿态/可输入/接收者/候选有效性并单一属主交接。此轮不需要先建通用热启动大接口；先有界量“真实/已有预测交还状态下，旧脚本究竟能不能接、早准备能省什么”，区分查询、准入、发键、模型命中。ep22几何/时刻已经不行的要如实保留未覆盖。
- D第二层仅作证据检查：尚未安装middle、上一刀真的到已定弹起最高点且锁已结束时，能否改选既有后手。9–15帧选路点不能自动称最高点，不能把任意中途增设为正常节点。
- B只作离线反事实：观测另一只新冲锤时，从实际状态及真实已发prefix问现成后手，看谁能接、何时能接、拒绝原因；有可执行接收者才比较交接，不因k>9强制裸交还。现有全体身体/符文/危险、非目标Idle/Walk、输入/冲刺锁、同一锤预算照旧，不能撤门或强置can字段制造可接。提前20–40帧不是准入证据。没有接收者明确记失败/未知，不宣称省血。

原话70仍有效：已承诺middle途中对另一只新招改选/抢占，是实质规格例外，**本任务只许分析树离线，不许生产启用**。如D不足、建议B，给用户的精确待定例外应是“纯移动middle已承诺后，另一只启动冲锤，是否允许在无锁且接收方通过全部原门、确认可执行时改选既有后手并提前换手”，不是全局取消承诺/任意抢键。报告D覆盖和未覆盖、B反事实结果与代价，再给Sol审后请用户定这个例外。无需用户先为离线诊断重复批准。

这不是要求三例都必须救回或填满全部架构，已有工具能给的最小证据就交；若真实反应/停招反馈不可模拟，明确不能认证，不硬跑开环当闭环。下劈改变怪的招式/顿帧后用录像原轨迹的局限继续保留。不做开伞14帧门、退闪身检查、不落地、隔怪移植等旁支；不重开旧批/新游戏/P、不动AA/原录制。完成后正式TO_SOL+原单次通知，Sol直接接窄审核。

证据和审核定位：analysis/committed388_20261111/REVIEW432.json；r6/between_all_tv429.json、between_tv429.txt、between_scope_tv429.txt；固定C4 air_native的_follow_landed 1871–1885、slam_play._as_hazard 798–812；唯一设计原话70/135/136、2.5和第二包。本包真实实现/正式计时/实机均未放行。

---

'''
p = B / 'sol/TO_OPUS.md'; t = p.read_text(encoding='utf-8'); head = '# Sol → Opus 留言队列\n\n'
assert t.startswith(head) and '## seq371（' not in t
p.write_text(head + mail + t[len(head):], encoding='utf-8')
p = B / 'sol/STATUS.json'; s = json.loads(p.read_text(encoding='utf-8'))
s.update(at=now, phase='ITEM3_REVIEW432_BOUNDED_OFFLINE_REPAIR_DISPATCHED', last_scanned_opus=432,
         opus432_receipt=str(R / 'REVIEW432.json'),
         pending_opus='seq371 correct mixed causal cohort/ownership and bounded D vs B offline diagnostic on ep0/22/30; no production/P/game',
         next_phase='Opus bounded evidence/prototype repair; Sol reviews before concrete user decision on quote70 exception',
         own_offline_jobs=[], own_live_session=None, live_or_budget_running=False)
p.write_text(json.dumps(s, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
p = Path('C:/modeling/silksong_bot/docs/plans/forum_clapper_plan.md'); t = p.read_text(encoding='utf-8')
assert '### 7.368 ' not in t
t += '''

### 7.368 #431/432核收与Astra重点审核：先补分类和正常节点可接性，不以k9切生产（11-14）

#431确认用户原话145暂不做单怪不落地，继续第3项；与seq370合并。#432正式交付第二包设计，生产码未动、无P/游戏。方向是回中间期间新招开始、落地时接管姿态/窗口不匹配；Root和既有Astra重点核后，原方案暂未接受。三处事实需改：ep24落地76539后1帧才SlamAntic，且旧脚本实际接管，不属于middle一直压住新招的同一因果；<=9共11个对照中5例是被踩怪自己再次冲锤，不能都当另一只起招；ep30 k17/5.58u成功接住，固定9非可行边界。111例落地已自由不证明发起时都违反原话135，不能把发起条件加强成全程仍后摇。时间关联22HP仍不当可救量。

seq371同包交Opus先修统计/唯一设计口径，再只在分析树以ep0/22坏、ep30好核D正常完成节点接管就绪与B提前换手反事实；不先做10+11矩阵或通用接口。D保持真落地且盒在中间才完成，T-3/T-2预计状态包含已发prefix，实际交接再验；B必须保留所有既有门和锁、已确认可执行的接收者，不能固定k9裸交还。中途新设退出点不当正常节点，20–40帧不等于可接。若仍需B，属于原话70例外，离线结果具体后才请用户决定，不以“继续计划”默改承诺规则。现源码d7仍已接受，待修是候选设计/证据；无生产新码、P、新游戏授权。REVIEW431/432登记，seq371单次信号/实收/实际开工分核。
'''
p.write_text(t, encoding='utf-8')
print(json.dumps({'review': 432, 'next_task': 371, 'source': head if False else H, 'writes_verified': True, 'wake_not_yet_sent': True}))
