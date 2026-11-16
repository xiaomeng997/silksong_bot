from pathlib import Path
from datetime import datetime, timezone
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
B = Path('C:/ssbot/data/m2_play/clapper_plan')
R = B / 'analysis/committed388_20261111'
now = datetime.now(timezone.utc).isoformat()
source = 'd7cbe1a59cbee1d8fa8d40c53fc57b3ed1bd2b19'
receipt = {
    'at': now, 'delivery': 430, 'closes_task': 369,
    'review': 'offline evidence/design reviewed with bounded independent source and aggregate checks; no new live/P',
    'source': source, 'runtime_changed': False,
    'official_result': {'pass': 37, 'protected_quit': 13, 'hitless': 14, 'HP': 144},
    'author_event_table': {'events': 74, 'HP': 143, 'scope': 'main-window losses only'},
    'missing_event_located': {'episode': 47, 'bout': 48, 'f': 141537, 'HP': 1,
                             'source': 'rune bomb small(Clone)/damager', 'section': 'tail.metrics.losses',
                             'evidence': str(B / 'analysis/w13_50_air_catch429_tv_on_20261114/audits/MEASUREMENT_e47.json')},
    'phase_totals': {'dual_alive_HP': 133, 'single_alive_HP': 10, 'postkill_tail_HP': 1,
                     'note': 'single-phase aggregate checked against author definition; tail independently located; not 134 HP dual'},
    'air_catch_check': {'plans': 41, 'real_Slam0_hits': 20,
                        'note': 'author broad real_catch=21 includes one Slam1 after abort; do not merge with active plan Slam0 hits'},
    'next_candidate_cohort': {'event': 'bounce follow-up done: landed between the two bodies',
                              'later_damage_within_frames': 90, 'loss_events': 11, 'HP': 22,
                              'meaning': 'temporal cohort, not established causal/preventable damage'},
    'review_cautions': [
        '11-13 vs >=14 umbrella frames is a small observational sample, not a proven threshold or repair',
        'Retreat handling must preserve actual other body/attack/rune safety; no late-windup blanket exemption',
        'air_chain is a charge-hammer timeline search, not already a generic Idle/Walk pogo planner; rune checks are external',
        'Observed single-phase 10 HP does not bound future behavior or prove preventable benefit',
    ],
    'user_current_instruction': '问题还是不少，继续按照计划弄吧',
    'decision': 'continue existing item3 one cause at a time; defer single-monster no-landing and unrelated changes',
    'next_task': 370, 'dispatch_written': True, 'wake_enqueued': False,
    'listener_received': False, 'actual_author_started': False,
}
R.mkdir(parents=True, exist_ok=True)
(R / 'REVIEW430.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

mail = '''## seq370（用户“问题还是不少，继续按照计划弄吧”）：回原计划第3项，先收“落回两怪中间后交还”这一类

#430 的 seq369 分析/候选设计已核收。固定源仍 d7cbe1a5，50实机37达标/13保护/144HP，全部授权已消耗。13保护有12发生在双怪阶段；单怪不落地暂后排，保留候选，不先加功能。继续唯一设计第7节第1项第3步“交还冷启动，按原因一次收一个”，不另起大一统控制器。

Sol复用你 loss_owner_tv429 表核出当前第一条具体线索：`bounce follow-up done: landed between the two bodies` 交还规划器后90帧内掉血11次、22HP。这只是时间关联，不是已证实11次都是交还造成、更不等于能救22HP。请**独占接下一小包**：先从这11例选2个典型损血和1个同条件无伤对照，沿交还前的实际站位/可输入状态/下一招前摇/最终发键，查清为什么落回中间后规划器S=1、哪一个共同原因能最便宜修。不要只凭S=1就延长握键，也不要取消危险检查。原设计“刀链自己选后手，不临时交还”仍是方向；安全落地已经完成本节时，不得无条件延长/锁焦点。

把这一原因的具体触发、控制者、后手、实际完成/退出条件、打空及已发键前缀如何处理，原位写进唯一设计的第3步。若原因和现行规格明确且无需新增战术/安全豁免，可以直接实现**这一项**、默认保守、给固定提交和最小正反动作证据；若要改变既定规格或根因尚不明，先交最小方案/阻点由Sol续决，不扩矩阵、不等用户重复催。不要同时做开伞门槛、泛化闪身处理、单怪不落地或隔怪移植2–4。Sol随后独审，必要时才补关键假设审核/受影响P；不先开游戏。

#430两点核收更正请原位改回设计：
1. 143vs144已定位：第48盘(ep47)尾窗 f141537 小符文1HP，在 audits/MEASUREMENT_e47.json 的 tail.metrics.losses；a50_loss_owner只读取metrics.losses而漏尾窗。全批144=双怪133+单怪10+双杀后尾窗1，不是双怪134。尾窗单列，勿算作单怪阶段或随意归属。无需重跑全批。
2. `air_chain strict` 当前按冲锤kb0/47档/SlamTimeline搜索，不是现成的待机/走路通用续踩；符文是在SlamPlay外层_hazard查，不在strict内自带。4.4b第2点不能写成已具备的通用能力；候选先留未实现。

开伞11–13帧5次中3次失败、>=14帧9次全中，是小样本关联，不证明把阈值改14就能治；若后排再处理，要区分伞高度模型/实际出刀可用性/接触豁免。另一只闪身后撤同样不能用“前摇过某帧忽略它”代替查身体/招式/符文。两项留候选，不夹进本包。

证据：G=analysis/w13_50_air_catch429_tv_on_20261114，D=sol/demos/同名/run；你r6的loss_owner_tv429、protect_map_tv429及as_audit；Sol analysis/committed388_20261111/REVIEW430.json。保持用户严停止/2HP条件、原录制/冻结AA不变；不重开已停止批、不加任何游戏/探针/P权限；不动其它项目或系统设置。完成正式交付TO_SOL+原单次唤醒本聊天，Sol接着审核。

---

'''
p = B / 'sol/TO_OPUS.md'
old = p.read_text(encoding='utf-8')
assert '## seq370（' not in old
head = '# Sol → Opus 留言队列\n\n'
assert old.startswith(head)
p.write_text(head + mail + old[len(head):], encoding='utf-8')

p = B / 'sol/STATUS.json'
s = json.loads(p.read_text(encoding='utf-8'))
s.update(at=now, phase='ITEM3_LANDED_MIDDLE_NEXT_PACKAGE_DISPATCHED',
         last_scanned_opus=430, opus430_receipt=str(R / 'REVIEW430.json'),
         pending_opus='seq370 item3 landed-between-two handback: bounded causal check then one specified fix; no game/P',
         next_phase='Opus item3 single-cause package; Sol independent review on delivery. No-landing deferred.',
         live_or_budget_running=False, own_offline_jobs=[], own_live_session=None)
p.write_text(json.dumps(s, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

p = Path('C:/modeling/silksong_bot/docs/plans/forum_clapper_plan.md')
text = p.read_text(encoding='utf-8')
assert '### 7.367 ' not in text
text += '''

### 7.367 #430分析核收，按用户要求继续第3项：落回两怪中间后交还（11-14）

用户“问题还是不少，继续按照计划弄吧”。#430/seq369只读分析和单怪不落地候选已审核，源码仍d7cbe1a5，无新游戏/P。13保护中12在双怪，单怪10HP，故单怪不落地暂后排，回唯一设计第7节第1项第3步，按原因一次收一个。Sol复用r6逐损血表核得“bounce follow-up done: landed between the two bodies”交还后90帧内11次/22HP，仅时间关联，未证明均由交还导致或可挽救。seq370交Opus先2损血1无伤对照查共同原因、原位明确后手/属主/实际结束，再按现有规格做这一小项；规格需变先交Sol，不混开伞阈值、闪身放宽、不落地及隔怪移植。正式交付后Sol源审、必要受影响验证，游戏另按实际授权安排。

143与144差已独立定位：ep47第48盘双杀后尾窗f141537小符文1HP，原作者工具只取主窗；全批144=双怪133+单怪10+双杀后尾窗1。作者后续需原位更正“双怪134”，不改原件。41接管计划中Slam0实中20次；不把放弃后的Slam1补刀混成在跑方案接住。11–13帧开伞小样本相关不能定为必然因果/14帧修法；闪身不得靠晚前摇忽略另一只。air_chain为冲锤时间线搜索、符文检查在外层，不把它当已有通用待机续踩能力。REVIEW430保存证据及局限。新派工、单次通知、listener实收、实际开工分别登记；旧停止批/冻结AA/原录像保持，50授权已用完，不增实机权限。
'''
p.write_text(text, encoding='utf-8')
print(json.dumps({'receipt': str(R / 'REVIEW430.json'), 'task': 370, 'mail_written': True,
                  'status_updated': True, 'main_plan': '7.367', 'wake_not_yet_sent': True}, ensure_ascii=False))
