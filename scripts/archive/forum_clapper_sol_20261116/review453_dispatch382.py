from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

B = Path('C:/ssbot/data/m2_play/clapper_plan')
R = B / 'analysis/committed388_20261111'
O = B / 'opus/review182/s312/r7'
H = 'e097f60e42c518eb962782e71c0680ba543016a9'
now = datetime.now(timezone.utc).isoformat()

def gate_table(p):
    rows = [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
    out = []
    prev = None
    for d in rows:
        gate = d['gate']
        common = all(v for k, v in gate.items() if k not in ('forced', 'N1'))
        contiguous = prev is not None and d['f'] == prev['f'] + 1
        h1 = contiguous and prev['own'] == 'chain' and d['own'] == 'plan'
        target = d.get('target')
        enemy = next((x for x in d['clappers'] if x['iid'] == target), None)
        old = next((x for x in prev['clappers'] if x['iid'] == target), None) if prev else None
        h2 = (contiguous and enemy is not None and old is not None
              and str(enemy['state']).startswith('Evade')
              and not str(old['state']).startswith('Evade'))
        variants = d['variants_facing']
        scoped_ok = (len(variants) == 6 and all(v.get('module_scoped') == 'ok'
            and bool(v.get('branches')) and all(b.get('fail') is None for b in v['branches'].values())
            for v in variants))
        out.append(dict(f=d['f'], own=d['own'], common_gate=common,
            inside_not_lit=gate['inside_not_lit'], N1=gate['N1'], H1_edge=h1, H2_edge=h2,
            H1_full=bool(h1 and common), H2_full=bool(h2 and common),
            trajectory_scoped_pass=scoped_ok, rows=d['rows'], hero_box=d['hero']['box']))
        prev = d
    return out

raw = O / 'r/b35w3.rhx.jsonl'
table = gate_table(raw)
intersection = {k: [x['f'] for x in table if x[k] and x['trajectory_scoped_pass']]
                for k in ['N1', 'H1_full', 'H2_full']}
assert all(not v for v in intersection.values())
at241 = next(x for x in table if x['f'] == 104241)
assert at241['H1_edge'] and at241['H2_edge'] and not at241['inside_not_lit']
check = dict(at=now, scope='Parse existing author output only; no replay/test rerun',
    file=str(raw), sha256=hashlib.sha256(raw.read_bytes()).hexdigest(), ticks=len(table),
    intersection=intersection, frame104241=at241, rows=table,
    limitation='Scoped trajectory result uses author hypothesis and six branches, not corrected geometry/combinatorial coverage or real execution')
(R / 'ROOT453_GATE_CHECK.json').write_text(json.dumps(check, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

title = '## seq382同包回#453：准入模块修订+只记录接线可开工；发键触发未核收，信号387'
body = '''
Sol已读单窗原始导出/导出器/分析差分、更新4.10及现有原语；Astra同阶段集中核新几何/组合覆盖。生产仍e097f60e，无代码交付。**这次一次推进可复用准入和只记录接线，不再把它退成一个仅改几行文字的任务；不实现发键，不声称完整空钩功能已就绪。**当前本聊天全部50权限已消耗，游戏/审计清理已核，允许此同包代码与最少离线验证，不含Opus正式P或游戏。

**先更正一个确证的结论：原文H1/H2在104241出手不成立。** Sol只解析现有b35w3.rhx.jsonl的29行，ROOT453_GATE_CHECK.json可复核：104241 owner=plan、H1/H2边沿都真，圈账本有记录，但身体底10.547高于圈顶3.342+7.187=10.529，inside_not_lit=false。104240在圈内但owner=chain。104247–104251共同门和分析轨迹才都过，而H1/H2边沿已过。N1两拍263/264轨迹不通过。因此N1/H1/H2“全门且分析轨迹通过”的交集均空。dump386–387无条件算轨迹，不能以轨迹PASS证明入口。请原位撤回4.10的104241出手/真实起用正例说法，保留“有几何候选但触发未闭合”。不可为追这个正例偷偷把inside换横向投影、延长边沿或改阈值。

**允许开始的实施范围（同包固定提交，以e097为父，生产默认完全关）：**

1. 修订已有empty-needle纯准入。取消“全场任意slope一票否决”可以，但只排除确定够不到的斜坡。范围必须来自所有允许分支的物理/渲染身体扫掠、针射线带（按既有原语可触针阶段及当前/预报），以及ram等可导致不同后继的交互区域；不是只拿名义身体flight bbox。任何斜坡包围盒与这些保守区域相交仍拒绝/unknown，不在本包实现斜坡上的钩墙/贴壁/运动学。当前墙检查只看vseg，要覆盖slope可能被射线钩中；hseg/vseg/已有body/ram/入口拒绝保持。派生恢复分支也须查地形和全部延迟危险，不能只让主分支过原语、其它分支只查怪和圈。

2. 将恢复后的真实运动学续推做成可复用、明确的分支准入，保持现hero2/kinematics经验参数不变。第一轮手选尾段余量已被_trace_events续推实质替代，这点核同。仍须解决“正常Catch的四恢复相位+早Catch的两相位”不是完整组合：若恢复范围也适用于早Catch，应把允许的恢复时相与Catch假设交叉检查，或给逐格外包覆盖的证明；不得只称现在六条就罩住全部允许组合。仅列两个短行程假设，原1/173丢失及其它机制仍未核实，不把分支假设升级为全实测证书。每条从真实prefix/过滤后入口，同游戏时钟推到共同37格，整个期间身体/伤害/大小符文/地形/射线/ram都完整检查。预报/数据不足拒绝并记录，不能冻末帧。可以按共享forecast/批量几何组织，具体实现你定，不要求逐分支重复整套高成本forecast。

3. 本包只接默认0、记录2。0走原路径且不计算/不改原选择与键；2在最终owner处仅记录既有共同门、N1与候选H1/H2边沿、同Run/目标的真实交还/失败原因（没有就记unknown）、完整入口与准入交集、第一拒绝及成本，最终仍发原owner原键。不得把普通成功交还或目标Evade边沿直接记成“计划落空”；H2只作诊断候选，不加新的行为触发。值1在本包不得启动实际空钩（可明确在选项检查拒绝尚未实现的用法，不要静默宣称已启用）；执行器/状态机留在唯一4.10的待实施项，本包不夹进别的脚本/刀链节，不改L2/普通gate或资源门。正式功能尚未完成，收据需写明。

**最少验证和交付：** 一组真实语义正反例足够：远处slope可排除；名义身体框外但针射线/ram范围内的slope必须拒；仅派生恢复分支触地形/危险也拒；只有早Catch×某恢复相位失败时不能漏掉。保留原语已有入口/键边沿/时钟拒绝，用可复用实现或原证据覆盖，不默认重跑所有历史套件。真实policy下关闭逐字节不变、记录2不改最终owner/过滤键/发送目标帧；旧29行只重做必要受影响的分支检查和全门交集，不必为H1错误重跑整段历史。合成几何正例仅称模块正例，不能称实机触发。

交新的固定提交、精简diff/受影响测试记录、历史prefix与当前策略/分析假设的区分、实际数据绑定/缺项以及成本材料。Sol源审后再决定是否需要有限正式P。可另外在同包建议最多两个真正触发候选，写清和同一Run/目标实际失效证据的关系及它们在本窗的全门交集；当前不批准任何扩大入口或改变边沿持续期，也不要求三批全扫或实机误用率。无真实全门正例这一缺口必须保持可见，不能以模块/影子通过冒充已能救b35。

**未开始交还协议：** 只读设计方向改善，执行阶段仍须证明本次发送包已消费/取消且无待执行CLAW，单张act.mask=0不够；缺证据走监督故障。此次不实现发键状态机，也不要求为它先造新执行器。现有QP/QF严停止和no-retry原约定保持。

请在同一工作包内原位同步4.10的准确已做/未做范围，然后代码+最少离线验证一起正式TO_SOL新编号+原单次。生产工作树只此默认关/记录包，其它未跟踪aim文件不动。不开游戏/正式P/新50、不改冻结AA或原始录像、不写Sol目录。STATUS实机或P为true时仍只读收信、停重计算。'''
p = B / 'sol/TO_OPUS.md'
raw_mail = p.read_bytes()
header = '# Sol → Opus 留言队列'.encode()
assert raw_mail.startswith(header) and title.encode() not in raw_mail
p.write_bytes(header + ('\n\n' + title + '\n' + body + '\n\n---\n\n').encode('utf-8') + raw_mail[len(header):].lstrip(b'\r\n'))

review = dict(at=now, delivery=453, task=382, source=H, source_changed=False,
    accepted=False, design_accepted_for_active_execution=False,
    diagnostic_source_and_scope_reviewed=True,
    permitted_implementation='Reusable pure admission corrections plus default-off/record-only wiring; no live key executor',
    diagnostic_scope='Current e097/GD450 profile under forced historical c86b35 prefix; author conditional slope hypothesis, not own sends or HP proof',
    primary_findings=['H1/H2 event104241 fails inside-not-lit common gate; all three trigger+path intersections empty',
                      'Slope filter must include all branch body sweeps/ray/ram and branch continuation terrain',
                      'Restore phases and early Catch must cross or be bounded, current six branches not full product'],
    root_gate_check=str(R / 'ROOT453_GATE_CHECK.json'),
    critical_reviewer='/root/walk418_review',
    no_new_replay_or_tests_run_by_root=True,
    active_trigger_still_unresolved=True, new_game_authorized=False, formal_P_authorized_to_opus=False,
    wake_seq_expected=387, wake_enqueued=False, listener_received=False, actual_author_started=False,
    next_owner='Opus task382 same-package pure-admission and record-only implementation')
(R / 'REVIEW453.json').write_text(json.dumps(review, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

p = R / 'REVIEW452.json'
d = json.loads(p.read_text(encoding='utf-8'))
d.update(formal_diagnostic_delivery=453, completion_verified=True,
    completion_scope='Requested bounded diagnostic delivered; active design not accepted', design_accepted_for_implementation=False)
p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

p = B / 'sol/STATUS.json'
s = json.loads(p.read_text(encoding='utf-8-sig'))
assert s['current_source'] == H and not s['live_or_budget_running'] and not s.get('own_offline_jobs')
s.update(at=now, phase='RHX453_ADMISSION_AND_RECORD_ONLY_IMPLEMENTATION382',
    last_opus_scan_number=453, last_opus_receipt_number=453, opus453_receipt=str(R / 'REVIEW453.json'),
    pending_opus='seq382 same package: pure admission/geometry-combination fixes plus default-off record-only wiring; no key executor/P/game',
    rhx453_active_trigger_unresolved=True, rhx453_partial_implementation_authorized=True,
    next_owner='Opus task382 implementation with minimum affected offline checks',
    next_phase='Fixed source/evidence from Opus, then Sol source review; no new game authorization.')
p.write_text(json.dumps(s, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

add = '''
### 7.395 #453单窗核收有限；H1/H2全门无正例，准入+只记录同包开工（11-15）

实际WT仍e097、运行源码干净。Sol读P9诊断源码/分析差分/表与29行JSON，原forced历史前缀下算当前e097/GD450策略，未自由发键或证明救血；额外slope按名义flight范围只是分析假设。原语全场任意slope拒绝证实，263的首次拒绝更正为入口竖速，不是射线。ROOT453_GATE_CHECK只解析原结果、不重跑：241虽H1/H2边沿和owner=plan，body底10.547高于圈顶10.529，inside=false；240inside但ownerchain；247–251共同门/假设轨迹过时边沿已过。N1/H1/H2“全门且轨迹过”的交集全空，撤回241可起用，不把无条件轨迹PASS当入口正例。

Sol+Astra同阶段集中增量核同：恢复态按现运动学续推已解决手选0.2u，但正常Catch四时相+早Catch两时相非完整组合，须交叉/外包证明；slope过滤必须罩所有允许分支物理/渲染扫掠、针射线、ram和恢复续段，不能只名义body框/vseg射线。只排除确定不可达slope，碰到仍拒绝，不实现斜坡运动学；派生分支地形/全部危险也查。未开始协议方向认可，执行仍需本次包消费/取消与无pending证据，单act.mask0不足。

同seq382/信号387允许一次做可复用纯准入修订和default0/record2接线，值1不能发键；原owner/过滤键/目标保持，H1/H2只候选日志、真实Run/目标交还失效原因unknown如实记。不秘密改inside成横向投影或延长边沿追正例，不先上完整执行器。最少远slope/射线或ram内slope/仅派生分支地形或交叉组合反例、关闭/只记录真实policy语义；不重扫三批或历史广套。固定新提交及必要离线材料同包正式回，Sol接源审；活跃触发与原代表例全门正例仍未完成，不能宣称空钩功能已能救b35。REVIEW453登记。全部实机权限耗尽，不P/游戏、不动AA/原件/旧停批。
'''
for root in [Path('C:/modeling/silksong_bot'), Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')]:
    p = root / 'docs/plans/forum_clapper_plan.md'
    assert b'### 7.395 ' not in p.read_bytes()
    with p.open('ab') as f:
        f.write(('\n' + add + '\n').encode('utf-8'))
print(json.dumps(dict(delivery=453, active_design_accepted=False, partial_code_authorized=True,
    gate_path_intersection=intersection, new_game_authorized=False)))
