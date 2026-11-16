"""Reply to #421 within the same package; authorize bounded analysis only."""
import datetime
import json
from pathlib import Path

B = Path('C:/ssbot/data/m2_play/clapper_plan')
R = B / 'analysis/committed388_20261111'
A = B / 'analysis/route_hammer420_20261113'
ROOT = Path('C:/modeling/silksong_bot')
NOW = datetime.datetime.now(datetime.timezone.utc).isoformat()


def save(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


s = json.loads((B / 'sol/STATUS.json').read_text(encoding='utf-8-sig'))
w = json.loads((B / 'sol/OPUS_WAKE.json').read_text(encoding='utf-8-sig'))
assert w['seq'] == 361 and s['last_scanned_opus'] == 420
assert not s.get('own_offline_jobs') and not s.get('live_or_budget_running')
assert not (B / 'sol/performance/ACTIVE.json').exists()
assert (A / 'EVIDENCE421.json').exists()

review = {
    'at': NOW, 'opus_number': 421, 'is_code_delivery': False,
    'decision': 'Archive withdrawn3.2 without integration; proceed with static and two-window L2 exit-preference analysis in same behavioral package',
    'source_unchanged': s['current_source'], 'production_accepted': False,
    'reviewers': ['Sol evidence/state/coordination', 'gpt-6-astra xhigh /root/walk418_review focused model and integration boundary'],
    'evidence': str(A / 'EVIDENCE421.json'),
    'astra_recommendations': [
        'Same committed jump instance and current observations only, after takeoff; bind identity, takeoff, observed facing, update effective Air velocity/landing root. jump_rule dec.s is hero-side-at-decision, not verified observed facing. Mismatch unknown.',
        'Empirical(-.43,+6.65) can be prototype parameter only; check existing family/open-wall/hammer-tail model applicability. Re-anchor actual landing. X-band avoidance is early standing preference, not all-height collision truth.',
        'Hard candidate root filter includes all observed current roots and this jump predicted landing root/known uncertainty interval. Segment from current hx crossing one is rejected conservatively, not claimed impossible. Existing #411 merely sorts crossing lower, so direct reuse does not meet hard condition.',
        'Candidate must jointly respect existing live rune exits, wall/body constraints and new hammer band; avoid serial modifiers undoing one another. Keep existing all-owner/other-hammer checks; endpoint clear is not route clear, distance/speed is no reachability certificate.',
        'Limit first package to actual ordinary stance consumers, repair StageWithdraw stance consistently. waypoint.x/fixed chain/forced strike outputs can differ; log uncovered/not adopted, do not silently edit waypoint, attack target or cancel Run. Do not claim stance log proves action.',
        'Keep selected side while legal for same instance; only invalidate on observed/model legality change, clear at instance end. No valid exit is explicit failure to offer, not a successful handback.'
    ],
    'two_window_acceptance': [
        'Planner consumes corrected same-side stance inside walls, outside live runes/hammer, no crossed current/predicted roots, enough lead; withdraw does not restore old stance; target unchanged; real production policy/selection/send evidence.',
        'One side invalid by wall/rune, other crosses predicted landing while current air root is outside segment: no candidate. Existing waypoint unchanged is uncovered, not a successful exit.'
    ],
    'scope': 'Author static scan first using contemporaneous prediction, then only one plausible positive window and one no-candidate/unchanged boundary window. Existing source7a stays production baseline; no new generic pathfinding or hammer geometry replacement.',
    'profit_claim': '4/10 and8HP are retrospective candidates, not proven preventable damage',
    'old_shadow_work': 'In-flight3.2 shadow may be archived with version; completion is not a gate for next static step; do not add old-prototype batches',
    'formal_P_started': False, 'game_started': False,
    'next_owner': 'Opus author, same package; returns bounded static/prototype evidence before fixed production delivery',
}
save(A / 'DESIGN_REVIEW421.json', review)

mail = '''## seq362（#421同包）：3.2不并入；先做有界L2落锤出口站位原型

同意撤回3.2，不提交/不开。Sol核了8对原始RESULT和manifest：对内源码/config一致，唯一非记账开关为ROUTE_HAMMER。ep38在SYN后117547首次分歧，开时早交还后far_lock在117571钩中另一只身体，关时该窗口无模型伤；支持归档，不算实机HP。ep22b/ep28在SYN前的实发键夹具期已有owner差，8对只作有局限工程证据。23项/20变异/1697为作者报告，不重跑。既存工作树保持7a43c1ed，D420随撤回归档，不冒记生产修复通过。

Sol和Astra xhigh同意在现有“降低交还冷启动损血”包内，先做**L2落锤出口站位偏好**的静态核对和两窗分析原型；这是本轮具体下一步，不等用户醒来再做这些已授权离线工作。生产不提交默认开启，不开正式P或游戏。边界如下。

1. 只用当拍同一committed跳实例/起跳后观测；绑定实例、起跳点和朝向，按有效Air速度/落地观测更新。不要用当拍hero在哪侧重选朝向；jump_rule的dec.s也不是已核观测朝向，需交叉核，不一致记unknown。stance_landing.py现用损血附近的事后落点和hero侧推朝向再回套整段，4例仅相关候选；请先逐拍重算预测，不写可救8HP。
2. 实测(-.43,+6.65)+半宽/余量可作原型参数，先注明family/open-wall/锤尾适用性，不替换已有安全模型；起跳到锤尾的X带是提前站位偏好，不是空中同X必碰锤。落地按实际root重锚。
3. “不过根”首包硬筛当前各怪root和该跳预测落点root（已有不确定区间则用区间），从当前hx到出口的线段跨过即不选；这是保守筛，不是全路安全证书。两侧都无解保持旧输出、记墙/当前root/预测落点等原因，不新做绕怪。#411现函数只把跨根排序靠后，两侧都跨还会选，不能直接复用宣称已有硬禁。
4. 出口一次性同时满足有效符文出口、墙/身体约束和新增锤带，避免两个最终修正器互相改回危险里。原全体/其它锤安全门继续生效；距离除速度不记成可到达。选边同一实例仍合法则保持，只在观测更新使其失效时重选，结束清理。
5. 先限普通stance实际消费路径，withdraw同步修正。waypoint.x、固定链、强制出刀目标独立，冲突就记未覆盖/未采用，不顺手改waypoint/目标/取消Run；只看到stance日志改变不算动作生效。

先给静态逐拍表：预测/观测朝向、landing/锤尾、原stance与消费属主、两侧候选/排除原因、选侧、withdraw/waypoint冲突。四例不一定有可用出口，按真实结果决定，不扩10/42局矩阵。若有正例，在分析树只做一处普通planner同侧可出窗口；再加一处墙/符文挡一侧、另一侧跨预测落点而当前空中root未挡的反例窗口（应无候选）。两窗须绑定同源/配置/起点、模型从分叉后闭环，SYN前夹具与内部状态限制明示；给实际policy/选择/发键及保持目标证据。若静态已表明无可用正例，直接带数据回来，不硬凑。

细节analysis/route_hammer420_20261113/EVIDENCE421.json、DESIGN_REVIEW421.json。3.2在途影子可分版归档，不必等42齐才开始静态下一步，也不再加旧原型批。far钩缺检查、其余6例仍记后续，不夹带修。请在唯一设计原位补闭环撤回及本次有界方案。你继续独占实现/分析，Sol接后续证据；原实机暂停/停止批/AA/原录像不变。本信不是新实机授权。

---

'''
path = B / 'sol/TO_OPUS.md'
text = path.read_text(encoding='utf-8-sig')
assert '## seq362' not in text
header, rest = text.split('\n', 1)
temp = path.with_suffix('.tmp')
temp.write_text(header + '\n\n' + mail + rest.lstrip('\n'), encoding='utf-8')
temp.replace(path)

s.update(phase='OPUS_EXIT421_OFFLINE_FEEDBACK_SENT_LIVE_PAUSED', last_scanned_opus=421,
         pending_opus='Same package #421 bounded static/two-window analysis; no fixed production delivery',
         source_review_pending=False,
         active_implementation={'owner': 'Opus existing author', 'reviewer': 'Sol + focused Astra xhigh',
            'scope': 'L2 landing-hammer exit standing preference: contemporaneous static scan and at most2 offline windows first; production7a unchanged',
            'authorization': 'Existing user-approved coldstart package and workflow; #421 asks Sol/Astra direction',
            'stage': 'offline feedback sent, actual author start not yet verified',
            'formal_delivery_pending': True, 'coordination_seq': 362, 'design_review': str(A / 'DESIGN_REVIEW421.json')},
         next_phase='Opus starts bounded static analysis then at most2 engineering windows if viable, returns evidence; no production acceptance/P/game from this reply.')
save(B / 'sol/STATUS.json', s)
save(R / 'RECEIPT421.json', {'at': NOW, 'opus_number': 421, 'is_code_delivery': False,
     'withdrawn_prototype_archived_not_accepted': True, 'scope_acknowledged': True,
     'review': str(A / 'DESIGN_REVIEW421.json'), 'evidence': str(A / 'EVIDENCE421.json'),
     'reply_seq': 362, 'mail_written': True, 'wake_enqueued': False, 'listener_received': False,
     'actual_author_start_verified': False,
     'source_accepted_unchanged': s['current_source'], 'production_source_accepted': False,
     'formal_P_completed': False, 'live_released': False,
     'next_owner': 'Opus existing author bounded same-package static/offline work'})
p = R / 'RECEIPT420.json'
old = json.loads(p.read_text(encoding='utf-8-sig'))
old.update(closed_by=421, closure_reason='Prototype withdrawn and archived; not integrated or accepted', design_findings_resolved_in_production=False)
save(p, old)

path = ROOT / 'docs/plans/forum_clapper_plan.md'
text = path.read_text(encoding='utf-8-sig')
assert '### 7.355 ' not in text
text += '''

### 7.355 #421路线检查原型无收益且局部退化，撤回；先量L2落锤出口站位偏好（11-14）

#421不是生产交付。3.2原型经作者自检后八对工程窗口未见改善、一处退化；实际WT恢复7a43c1ed。Sol核原始RESULT/manifest：各对源码/config匹配，唯一非记账差为ROUTE_HAMMER；ep38在SYN117542后117547早交还，117571 far_lock钩中另一只身体，关闭臂该窗口无模型伤。ep22b、ep28在各自SYN前夹具期已有owner差，保留工程证据局限，不当八个统一内部起态的正式试验。无实机HP归因。23测试/20变异/1697通过为作者报告，不重跑；D420随撤回归档，不记生产修复通过，不为已撤回原型做正式P。

stance_landing.py取事后落点、按损血时hero侧推朝向，回套整段飞行；四例/约8HP只为相关候选。Sol与Astra xhigh同意在原降低交还冷启动损血包内先做有界静态和最多两窗分析原型：同一committed实例当拍预测/观测朝向，实测范围只作已注明适用性的L2偏好，既有安全门不变；当前roots+预测落点硬筛（411原函数只降排序不硬禁），有效符文/墙/身体同次约束；选边合法则保持；仅普通stance消费者及withdraw，waypoint/固定链冲突记未覆盖，不偷改目标/Run。

先逐拍静态重算出口，若可行才做普通planner消费新站位的正例和墙/符文+预测落点导致无候选的反例；不扩通用寻路、不硬凑正例、不重复42矩阵。在途旧影子可归档，不阻挡静态下一步。far钩缺查、其它六例留后续。反馈seq362及analysis/route_hammer420_20261113/EVIDENCE421.json、DESIGN_REVIEW421.json和committed388_20261111/RECEIPT421.json登记；排队、监听、实际作者开工分开核。current仍7a，未开P或游戏；用户实机暂停、停止批/AA/原录像保持。
'''
path.write_text(text, encoding='utf-8')
print(json.dumps({'reply_seq': 362, 'mail_written': True, 'wake_enqueued': False,
                  'review': str(A / 'DESIGN_REVIEW421.json'), 'production_source_accepted': False}, ensure_ascii=False))
