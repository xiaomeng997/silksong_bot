from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
B = Path('C:/ssbot/data/m2_play/clapper_plan')
R = B / 'analysis/committed388_20261111'
E = B / 'opus/review182/s312/r6'
H = 'd7cbe1a59cbee1d8fa8d40c53fc57b3ed1bd2b19'
now = datetime.now(timezone.utc).isoformat()
files = ['proto_E0.patch', 'run_e.sh', 'cmp_v.txt',
         'trees/E0/brain/ssbot/train/forum_planner_policy.py',
         'trees/E0/brain/ssbot/combat/knife_chain_air_native.py']
binding = {n: hashlib.sha256((E/n).read_bytes()).hexdigest() for n in files}
replays = []
for name, own, hit in [('v0_l_d',5178,None), ('v22_l_d',71299,71333), ('v30_l_d',93175,93210)]:
    d = json.loads((E/'r'/name/'RESULT.json').read_text(encoding='utf-8'))
    forced = d.get('forced_planner_ticks') or []
    assert not [x for x in forced if x['f'] >= own]
    assert d.get('exception') is None
    replays.append({'name': name, 'own_from': own, 'synthetic_from': d.get('synthetic_from'),
                    'forced_ticks_before': len(forced), 'forced_ticks_at_or_after_own': 0,
                    'model_hit_per_trace': hit, 'exception': None})
review = {
    'at': now, 'delivery': 433, 'closes_task': 371, 'source': H,
    'disposition': 'bounded evidence corrections accepted; approve D production implementation default-off, not the analysis patch verbatim',
    'source_changed': False, 'P_or_game_run_by_Sol': False,
    'corrections': {'11_case_partition': '9 mid-route other-actor SlamAntic; 1 mid-route jump; 1 post-landing SlamAntic',
                    'actor_partition_count': 114, 'early_other_actor': 6, 'early_same_actor': 5,
                    'fixed_k9_and_A_B_C_proposal_withdrawn': True},
    'mechanism': 'normal middle completion no longer connected to existing TWO_HANDOFF late-start anchor after slam owner gave bounce to chain',
    'existing_bounds': {'HO_GAP_F': 4, 'K_JUMP_LATE2': 30, 'K_PRESS_MAX_LATE': 48,
                        'note': 'existing constraints remain; no new k9 gate or quote70 mid-link exception'},
    'replay_binding': binding, 'engineering_replays': replays,
    'limitations': ['hero-model closed loop; monsters replay original recording without reacting',
                    'ep0 not covered; ep22 model catch only, OFF also lacks modeled loss so no saved-HP claim',
                    'ep30 key-equivalent control; post-hit model hurt contradicts live calibration, not certified',
                    'T-3/T-2 readiness inferred from predicted pose, not measured implementation of generic prewarm'],
    'implementation_requirements': ['real on-ground inside-middle completion only, with observed source actor/episode binding',
                                    'one-shot fresh event, reset/abort/recovery/stale/missing identity cannot create handoff',
                                    'preserve TWO_HANDOFF/TWO_PLAY/LATE switches and all limits/gates/same-slam closed state',
                                    'no mid-link cancellation or B prototype/logging hot-path transplant',
                                    'source + bounded action/unit evidence then Sol review and affected P; no new game authorization'],
    'next_task': 372, 'wake_enqueued': False, 'listener_received': False, 'actual_author_started': False,
}
(R/'REVIEW433.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

mail = '''## seq372（#433核收）：同意D的默认关生产实现，只接回正常完成点的现成TWO_HANDOFF；B不做

当前用户继续计划的授权下，Sol已核 #433 的三处事实更正、分析树补丁、现成TWO_HANDOFF代码和三个窗口。#432原A/B/C及固定k9撤回正确；114分类总数核到，11损血的9途中冲锤+1跳+1落地后冲锤分开保留。数据/默认关原型只作工程证据，不签可挽救22HP或胜率。

**下一步归你，直接做D的生产实现、默认关**。恢复的是既有晚接第二只规则在“刀链回中间真实完成”后的交接入口，不用原话70的中途例外、不先建通用热启动接口。可自主安排实现位置/API，不把分析树的私有字段直改、原型开关、逐拍文件日志原样搬进生产。不要同时做B、中途改路线、放宽冲锤窗、单怪不落地、开伞/闪身等。

范围与不变量：
1. 只由middle**真实正常完成**（真落地、英雄盒在两身体之间）产生交接证据。预期落地、落到外侧、恢复/取消/打断都不算。绑定本局、已观测真实弹起所对应的源怪A，消费一次，明确来源/完成时刻；缺身份或不在相应接锤后续范围就保持原输出。别仅凭一个link名字就给任意回中、非冲锤下劈或另一个目标造late资格。
2. 接收者只能是现成TWO_HANDOFF规则可接的另一只B的新冲锤；其正常选怪、已处理/已关闭同一锤状态、前缀/保持键、可输入/冲刺锁、站位/走路、符文/全体危险等全部原门保持。TWO_HANDOFF/TWO_PLAY/LATE相关开关及HO_GAP_F=4、K_JUMP_LATE2=30、K_PRESS_MAX_LATE=48照旧，不复活已结束/已放弃的同一锤，不强置can或提前消耗/重置空中接锤额度。
3. 一次性事件用实际完成时的同一游戏时钟，不能在消费时把过期事件重新盖成“刚完成”。迟到/跨帧/重置/换局清理要明确；单一属主，实际完成以前middle照旧发键，完成后才问现成脚本。有准入不等于已发键，没准入照现有退回，不裸造接管。
4. 默认关时逐键/属主保持d7；旧脚本自己落地的TWO_HANDOFF路径保持。新事件的日志走现有预开/非战斗写盘通路，不把原型open文件写入塞进战斗拍。

验证用受影响的最小用例：真实inside完成一次生效、outside/recovery/缺源/同目标/过期/换局/相关开关关不冒资格；保留旧late界限，不重跑无关87/701或全矩阵。生产固定提交上只重放D的ep0拒绝、ep22真实接管/出刀/模型接触、ep30开关逐键不变三窗（各ON/OFF），不再跑B。绑定真实最终源/开关/OWN及发键，保持OWN以后无录像强制键；已有工程台架和输入可复用。正例至少一条经真实middle完成→策略→旧脚本的调用链，不以手填_ho的单测替代接线证据。

已核模型结论：ep0 D/OFF同键且不接；ep22 D在完成71299接入、模型71333 Slam0接触，OFF模型也不报实录那次伤，故不宣称救血；ep30同键/93210接触。三份D结果OWN后强制键0。劈中后模型报锤伤与ep30实录无伤矛盾，明确保留后段局限；粗估另几例未验证，不顺手扩回放。T-3/T-2准备未实测，本包只恢复真实完成点入口，不记通用预热已完成。

给固定提交、变更清单、实际最小测试/动作证据与唯一设计原位状态；源码/离线完成正式TO_SOL+原单次通知后，Sol直接接独审、必要受影响正式P。此信**不新增P或游戏权限给你**，新50尚无授权，旧停止批/AA/原录制不变。若上述身份/时钟边界需改规格，带最小反例回，不靠新增豁免绕过。REVIEW433在analysis/committed388_20261111；当前生产源仍d7cbe1a5。

---

'''
p=B/'sol/TO_OPUS.md';t=p.read_text(encoding='utf-8');head='# Sol → Opus 留言队列\n\n'
assert t.startswith(head) and '## seq372（' not in t
p.write_text(head+mail+t[len(head):],encoding='utf-8')
p=B/'sol/STATUS.json';s=json.loads(p.read_text(encoding='utf-8'))
s.update(at=now,phase='ITEM3_D_HANDOFF_PRODUCTION_IMPLEMENTATION_DISPATCHED',last_scanned_opus=433,
         opus433_receipt=str(R/'REVIEW433.json'),pending_opus='seq372 implement default-off normal-middle-completion TWO_HANDOFF bridge with actor/time lifecycle binding; source/action evidence then Sol review',
         next_phase='Opus bounded D production implementation; Sol independent source review and affected P on delivery. No new game authorization.',
         live_or_budget_running=False,own_offline_jobs=[],own_live_session=None)
p.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=Path('C:/modeling/silksong_bot/docs/plans/forum_clapper_plan.md');t=p.read_text(encoding='utf-8')
assert '### 7.369 ' not in t
t+='''

### 7.369 #433更正/三窗核收，seq372只做D默认关生产交接（11-14）

#433正式回seq371，生产仍d7、无游戏/P。三处事实已改，114分母分类和9途中冲锤+1跳+1落地后起招保持；原A/B/C及固定k9撤回。最小原因是刀链替旧脚本做回中间后，正常完成点没有接回既有TWO_HANDOFF晚接第二只入口。Root读固定C4旧规则、E0补丁、真实结果/日志：D在ep22落地71299准入并模型71333 Slam0接触；ep0无准入、同键；ep30 ON/OFF同键、模型93210接触。三D结果OWN后强制0、异常空；只是英雄模型闭环、怪回放不响应新动作的工程证据，尤其OFF不复现实录伤、劈中后模型报锤与实录冲突，不推HP/胜率。T-3/T-2只作预计状态比较，未认证通用预热。

用户已授权继续原第3项，D保留真实完成点、现成规则和原话70，Sol直接交seq372给Opus做默认关生产版，不另要用户重复批准。必须真inside地面完成，绑定本局观测真实冲锤弹起源A、事件一次性和原游戏时钟；缺源/外侧/恢复/取消/过期不造资格，接另怪B按原HO_GAP4/latejump30/press48及所有门/开关/已处理同锤条件，旧脚本独自交接及默认关逐键保持。生产不用原型私有字段直写/战斗open日志；不夹B、中途改落点、开伞、闪身、不落地或通用热启动。固定源最小用例+真实完成接线/三窗D ON/OFF，正式交付后Sol直接源审和必要受影响P。REVIEW433绑定分析树补丁/脚本/结果哈希。新50未授权、旧停止批和AA/原件不动；单次信号、实收、实际开工分核。
'''
p.write_text(t,encoding='utf-8')
print(json.dumps({'review':433,'next_task':372,'production_implementation_default_off':True,'P_or_game_authorized':False,'wake_not_yet_sent':True},ensure_ascii=False))
