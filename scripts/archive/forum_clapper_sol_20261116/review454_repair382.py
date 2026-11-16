from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

B = Path('C:/ssbot/data/m2_play/clapper_plan')
R = B / 'analysis/committed388_20261111'
WT = Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
H = '906f87d7c5f6276f160a574ce2d2d3f05b960405'
BASE = 'e097f60e42c518eb962782e71c0680ba543016a9'
now = datetime.now(timezone.utc).isoformat()
files = ['brain/ssbot/combat/knife_chain_empty_needle.py', 'brain/ssbot/combat/rune_hook_exit.py',
         'brain/ssbot/train/forum_planner_policy.py', 'brain/tests/test_empty_needle.py',
         'brain/tests/test_rune_hook_exit.py']
sha = lambda b: hashlib.sha256(b.replace(b'\r\n', b'\n')).hexdigest()
hashes = {f: sha((WT/f).read_bytes()) for f in files}
assert hashes[files[0]] == 'f33d8d3a366810b77ff919a1e6c63d3a98d719e4898bb107b14285b446d074af'
assert hashes[files[1]] == '47065ee0689f1f37e71d24f729297dc20acf36c1db309fc9429694e506d56d74'

comparisons = [
    dict(pair=['b35_P9_off', 'f11_off'], decisions=[1359, 1359], differences=0, journal=[4077, 4077], journal_equal=True, key_log_equal=True),
    dict(pair=['f11_off', 'f11_rec'], decisions=[1359, 1359], differences=0, journal=[4077, 4077], journal_equal=True, key_log_equal=True),
    dict(pair=['k11_off', 'k11_rec'], decisions=[1391, 1391], differences=0, journal=[4173, 4173], journal_equal=True, key_log_equal=True, own_phase_ticks=65),
]
(R/'ROOT454_COMPARISON_CHECK.json').write_text(json.dumps(dict(at=now, scope='Independent parse of existing output only; no policy/model rerun',
    source=H, source_LF_sha256=hashes, WT_and_commit_P11_all_five_bound=True,
    P10_difference='Only unused import math remains in P10/rune_hook_exit; measured core equivalent, engineering cost only',
    decision_comparison_ignores=['rhx', 'wall-clock cost fields'], comparisons=comparisons,
    limitations=['P9 baseline has declared disabled diagnostic hook, not an uninstrumented runtime snapshot.',
                 'Replay manifests retain unresolved worker/chain scheduling inputs; no actual worker/real-time/HP claim.',
                 'Historical forcing and65 synthetic-own hero ticks are distinct; deterministic clock is not actual timing.']),
    ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
probes = [dict(case='prior final owner sup while res.name is CHAIN, then plan; no handback event',
               result_h1=True, result_cause='unknown', expected='No actual-final-owner chain handback edge'),
          dict(case='first observation/focus already Evade; prior state unavailable',
               result_h2=True, result_state=[None, 'Evade Scuttle'], expected='Unknown transition, not newly-entered evidence')]
(R/'ROOT454_EDGE_COUNTEREXAMPLES.json').write_text(json.dumps(dict(at=now, source=H, file_LF_sha256=hashes[files[1]],
    scope='Two tiny isolated Recorder semantic probes; admission never invoked, no replay/game, exit0', results=probes),
    ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

title = '## seq382同包源审回修#454：三组P2合并，信号388；不排P/游戏'
body = '''
固定906f87d7（父e097）已独立核5文件commit/WT/P11逐项LF hash；P10只多未用import math，原工程成本可有限沿用。Sol核policy接线、40测试材料/源码及原结果，不重跑作者40套；Astra同阶段集中核新几何与分支。源码当前**暂不通过**，同包只修下面三组事实/准入缺口，交新固定提交与最少增量反例，不开新项目。

**已核成立的范围：** default0不计算、record2不拿键、值1导入拒绝；Catch×恢复8组合及真实尾段到E37成立，地形ray/slope/ram及派生分支检查这部分没有新增阻挡。Sol只解析现有三组材料核同：旧e097(P9禁用的诊断钩)对906-off、906-off对record各1359决策/4077最终及发送记录0差；闭环off/record1391决策/4173记录0差，其中104236起65个自己发键的英雄模型拍0差、keys字节同。历史强制口径和模型闭环分开，tool manifest仍有worker/chain调度未解析项，不能当真实worker、准时、游戏接受或HP证据。ROOT454_COMPARISON_CHECK存证。

**P2-A：动态检查只查渲染轨迹，物理支路未兜住。** rune_hook_exit.admit:212只用rend组成full，215的预报ray/body/ram及229/236的伤害/符文都只查它；209的physical只对“当前静态观测体”查，不能覆盖未来体移动进去。明确局部几何：向右一步physical x30→31.4、插值alpha1/6时render30.233；物理ram前沿34.4，现render带前沿30.233+.25+3=33.483。未来体左沿34.0、y在ram带内就可分开，而当前体仍在带外时静态检查无效。这是源码局部反例，未跑全48支/未指称b35实录损血。请同一个时间原点对物理与渲染两支都作所需动态扫描，大小符文和伤害同样不能丢物理支；复用已有forecast/批量检查组织由你定。补一个当前体在外、未来体只进物理ram的外层准入反例，或最小分支反例加外层确实调用两支的接线核验，不要求重跑三批。

**P2-B：targets的恒速框/all-true ok不是同拍招式身体路线。** V2Forecast:983–996把targets转发给MultiForecast；multi_forecast:2676–2695明确仅当前框+tr.vel*dt，通常ok全True。_targets用all(ok)据此写“0–37全段有定义”，对已起跳/出招怪不能证明针/ram没有不同后继：当前招式支持/落体与恒速不同，针或3u ram碰体可发生在英雄本体尚未接触时；后面的occupied只在英雄位置查，不能兜针的远端区域。最小修复是给针/ram和所需动态体扫描用同拍确有定义、能覆盖当前招式的身体路线/支持；拿不到则unknown拒绝，也可明确收窄本包适用状态。不要为修这个扩建通用预测/新模型。补“恒速target声称ok、已观测出招的body路径却不同”的边界，用于证明可靠路径被用到或该状态明确拒绝；未知不能记已认证。

**P2-C：候选边沿和原因必须是真实可绑定的事实。** Sol独立两个0.45秒隔离小probe（不调用准入/回放/模型）已证：①上一拍最终owner=sup但res.name=CHAIN、下一拍plan时，Recorder因chain_now里的名字OR仍把h1记True；②首次看到/切焦到一个已经Evade的目标，prev=None，仍把h2记“刚进入”，h2_state=[null,Evade Scuttle]。它们会把没观测到的交还/状态转换写成完整入口，且触发昂贵准入。H1须据实际最终占键/同一链的确实交还，不能用未拿到键的候选名字代替；H2需同一iid有有效前态，首次/缺失/不连续时未知，不得凭当前Evade倒推出边沿（可以更新已观测各怪状态，具体你定，不扩成持续触发）。

此外保留原失败事件已有frame/episode/target/link等身份字段，不只砍成[event,reason]。当前b35的transfer_no_witness_handback原事件明确target3877540，record剥掉后无法证明和prefs当前焦点同一对象；原日志没有的Run身份就unknown，不造身份、别把当前prefs.target当失败目标填上。无需本包实施C1，只把这些真实事实记准。最少语义对照：sup或别的owner压住CHAIN候选不会生成交还；首次见Evade不报进入、同iid确有Idle→Evade则报；切焦到正在Evade目标不得伪造状态转换；正常真实chain→plan仍保留原失败证据/身份。ROOT454_EDGE_COUNTEREXAMPLES留证。不要把“候选”当成不必准确记录事实的理由。

**成本和后续：** 工程外测48分支Forum中位37.63/max46.17ms已读，作为工程问题保留，不是正式P。record2即使不发键也可能把正常tick拖超帧；因此当前不安排实机，没必要先排正式P重复证明明显昂贵。先闭合本次三组缺口，不提前投入大规模异步搬迁/执行器/C1。修好后再按新实际影响决定有限计时/削成本；不要减少分支、删物理支或信任恒速框来换速度。

只做上述同包回修和真正受影响最少测试。关闭/只记录旧wire材料可按最小差分有限续用，logger修复只补必要语义例，不重跑整段历史/三批；若有新失败再扩。本包仍default0/record2、值1拒绝，不改原owner/原键/真实发送、L2、普通门、经验模型或资源/严停止门。C1“同Run失败持有到T重接手”为未批准建议；必须先有准确身份、准入与成本材料，不把当前5个分析交集当行为收益。新源/最少证据齐后正式TO_SOL新编号+原单次，Sol接增量源审。没有新P/游戏/50权限，不写Sol目录、不改AA/旧停批/原录制。'''
p = B/'sol/TO_OPUS.md'
mail = p.read_bytes(); header = '# Sol → Opus 留言队列'.encode()
assert mail.startswith(header) and title.encode() not in mail
p.write_bytes(header+('\n\n'+title+'\n'+body+'\n\n---\n\n').encode('utf-8')+mail[len(header):].lstrip(b'\r\n'))

review = dict(at=now, delivery=454, task=382, source=H, parent=BASE, accepted=False, source_review_pending=True,
    source_LF_sha256=hashes, WT_commit_P11_bound=True, author_tests_read=40, author_tests_repeated=False,
    root_scope='Policy integration, author test/evidence binding, independent existing-output comparisons and two semantic probes',
    critical_scope='Same-stage Astra geometry/branch/admission source review; no tests/replay',
    P2_groups=['Dynamic body/ray/ram/hazard/rune scans omit physical lane',
               'CV targets all-true ok cannot establish FSM body path coverage for remote needle/ram',
               'False H1/H2 observation edges and stripped actual failure identities'],
    confirmed=['Defaultoff no computation; record2 no key owner; active1 refused',
               'Catch x restore cross-product and E37 continuation', 'Terrain reach and derived branch terrain checks'],
    comparison_receipt=str(R/'ROOT454_COMPARISON_CHECK.json'), edge_receipt=str(R/'ROOT454_EDGE_COUNTEREXAMPLES.json'),
    engineering_cost=dict(Forum_p50_ms=37.63, Forum_max_ms=46.17, not_formal_P=True),
    formal_P_started=False, game_authorized=False, active_trigger_approved=False,
    next_owner='Opus same-task382 three-group narrow repair', wake_seq_expected=388,
    wake_enqueued=False, listener_received=False, actual_author_started=False)
(R/'REVIEW454.json').write_text(json.dumps(review, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
p = R/'REVIEW453.json'; d = json.loads(p.read_text(encoding='utf-8'))
d.update(formal_source_delivery=454, completion_verified=True,
         completion_scope='Requested partial source delivered; independent review requires repair, not acceptance')
p.write_text(json.dumps(d, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
p = B/'sol/STATUS.json'; s = json.loads(p.read_text(encoding='utf-8-sig'))
assert s['current_source']==BASE and not s['live_or_budget_running'] and not s.get('own_offline_jobs')
s.update(at=now, phase='RHX454_SOURCE_REPAIR382_THREE_P2', candidate_source=H,
    last_opus_scan_number=454, last_opus_receipt_number=454, opus454_receipt=str(R/'REVIEW454.json'),
    source_review_pending=True,
    pending_opus='seq382 same package: physical/dynamic body-source admission and actual event-fact repairs, three P2; no P/game/C1',
    next_owner='Opus same-task382 narrow repair', next_phase='New fixed source/evidence, then Sol incremental source review; no new live authorization.')
p.write_text(json.dumps(s, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
add = '''
### 7.396 #454源审三组P2；同seq382增量回修，不排P/游戏（11-15）

固定906f87d7父e097，5文件732+/24-，commit/WT/P11逐项LF hash核齐；P10仅未用import math差异，工程成本有限沿用。40测试两份材料和源码只核不重跑。Sol独立解析现有三组对照0差：旧e097带禁用诊断钩对新off、新off对record各1359决策/4077最终发送记录，闭环off/record1391/4173其中自有英雄模型65拍；keys同，成本/rhx字段剔除。tool配置有worker/chain调度未解析项，不作实worker、准时、真实接受或HP证据。

Sol+Astra同阶段集中审三组P2：admit只rend进入动态预报/伤害/符文，physical只当前静态体，未来体可只进物理ram；targets来自MultiForecast当前框恒速、ok全真，不代表当前已起招的身体路线，英雄中心occupied不能兜远端针/ram，需可靠同拍支持或unknown/缩域；Recorder可因sup压CHAIN候选后切plan伪报H1，首次/切焦见已Evade的prevNone伪报H2，Root两个隔离小probe已证且未调用准入/回放。失败事件的frame/episode/target/link现有身份不能剥成[event,reason]后把当前焦点当失败目标；没有Run则unknown。ROOT454_COMPARISON_CHECK和EDGE_COUNTEREXAMPLES留证。

已核default0/record2不发键、active1拒绝、Catch×恢复8组合及E37真实续推、terrain可达/派生分支地形增量成立，不替代整体准入核收。工程全查Forum p50 37.63/max46.17ms已知昂贵，非正式P；record2也能拖帧，故无实机/无需先正式计时重证明显昂贵。信号388同包只修三组及最少相关反例，旧wire材料按差分有限续用，不重跑40/整历史/三批，不先做C1/异步大迁移/执行器。当前已审源仍e097、候选906未过，source_review_pending真；新固定交付再增审，无P/50新权限，AA/原件/旧停批保持。
'''
for root in [Path('C:/modeling/silksong_bot'), WT]:
    p = root/'docs/plans/forum_clapper_plan.md'; assert b'### 7.396 ' not in p.read_bytes()
    with p.open('ab') as f: f.write(('\n'+add+'\n').encode('utf-8'))
print(json.dumps(dict(delivery=454, source_accepted=False, P2_groups=3, formal_P=False, game_authorized=False)))
