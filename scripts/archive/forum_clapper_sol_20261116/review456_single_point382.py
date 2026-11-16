from pathlib import Path
from datetime import datetime, timezone
import json

B = Path('C:/ssbot/data/m2_play/clapper_plan')
R = B / 'analysis/committed388_20261111'
H = 'b74140e0d627fac263606a642461fde27fd44b77'
now = datetime.now(timezone.utc).isoformat()
proof = dict(at=now, delivery=456, scope='Read/parse existing single P15 geometry only, no model/replay rerun',
    file='C:/ssbot/data/m2_play/clapper_plan/opus/review182/s312/r7/r/p15_dump/dump_104247.pkl',
    SHA256='5acbae8a056b3df8d003e0c8c695d31ddf95e3d55b702c5afb85a9bbe190d1f7',
    frame=104247, origin=104247, variants=6, branches=48, lanes=96, static_problems=[],
    minimum_against_fitted_7_776=dict(margin=1.7013309285641274, region='body', index=37,
        lane='physical', throw=8, late=1, catch_shift=0, control=29),
    conditional_only=True, ceiling_bound_certified=False, remaining_full_admission_verified=False,
    source_limitations=['7.776 derived from per-frame median posture table, low-sample rows omitted; dev95 not a maximum',
                        'Know.durations lo filters small-share and cut-short observations; not absolute FSM lower bound',
                        'Original witness has pose/floor/clock domain conditions which a new fallback does not inherit',
                        'earliest() mixes body validity and damage/rune timing; independent hazards remain required'])
(R/'ROOT456_SINGLE_POINT_READ.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
review = dict(at=now, delivery=456, task=382, source=H, source_changed=False,
    accepted=False, new_body_bound_accepted=False, active_trigger_approved=False,
    accepted_facts=['Existing body APIs do not directly cover the original case', 'Single-point conditional region-height arithmetic verified'],
    source_inspection='Sol scripts/data/design and producer/Know contracts; same-stage Astra concentrated new-bound/FSM review',
    primary_gaps=['Median pose max and filtered lo cannot be labelled universal body/time bounds',
                  'Independent physical/rendered hazard/rune/full-exit checks not completed',
                  'C1 lifetime and Run/circle identity unresolved, no implementation approval'],
    root_proof=str(R/'ROOT456_SINGLE_POINT_READ.json'),
    permitted_next='F104247 one-context bound-evidence closure and full conditional admission; design only, no source implementation',
    three_batch_scan_authorized=False, formal_P=False, game_authorized=False,
    next_owner='Opus same-task382 one-point conditional prototype and evidence/design correction',
    wake_seq_expected=390, wake_enqueued=False, listener_received=False, actual_author_started=False)
(R/'REVIEW456.json').write_text(json.dumps(review, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
p = R/'REVIEW455.json'; d = json.loads(p.read_text(encoding='utf-8'))
d.update(formal_applicability_delivery=456, completion_verified=True,
    completion_scope='Requested existing-interface feasibility delivered; new height-bound proposal not accepted')
p.write_text(json.dumps(d, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

title = '## seq382回#456：只取F104247补边界与完整条件检查，不扫三批（信号390）'
body = '''
只读答复已收。现有接口分类及原case缺整段支持的事实有用；高度方向可继续作为**分析假设**，但本轮不核收新身体上界/活跃触发，不改生产源。b741离线限定核收保持，已实机源e097不变，全部50权限余0。Sol读脚本/设计/已有导出，Astra同阶段集中核新上界/FSM；不重做原准入包/不跑旧测试。

**先不要扫三批53次或37个机会。** 先把F104247这一个上下文做成可审阅的完整条件结果，暂不纳104251/252同伴距离推断、253/254贴边扩展或新模型。Sol独立只解析dump_104247：6变体、48分支、96路，static_problem空；相对7.776的最小高度差1.7013309u，在physical第37格、throw8 late1、catch0、control29，数值核同。但这只证明“若7.776是上界，则该几何集合高于它”，不等于完整准入、触发或救血。ROOT456_SINGLE_POINT_READ.json留证。

**边界证据须分清：**
1. 7.776是拟合姿势**中位表**的max，不是所有真实碰撞体的上界。m2_clapper.py:428–443逐帧取median，样本<8不收，另存dev95；Know.box只返回该表。原witness另有当前pose/贴地/有限时钟门；恰在这些门失败时换天花板，不能因“同一张表”就继承原合同。请只核本点可达地面姿势的真实身体最高顶、根高/贴地约束及已有数据能支持到哪种上界；没有可核界限就如实保持假设，不任意加余量或把p95当max，也不先组织新实机/新测量。
2. Know.durations.lo还筛掉占比<0.5%和<0.6*mode的时长，不能称FSM绝对下限。分开原FSM的路径顺序、时间动作/时钟口径、筛选实测lo及模型假设，绑定两怪本拍状态/clock/根高、可达后继和在途攻击/反应。原FSM支持逃跳仍先进Jump/Charged前摇，不是瞬间离地；本点右怪x31.974，即按15u/s继续37帧到41.224，距右墙48.99仍7.766>6、Centre横偏0，可作这个单点的局部排除，不推到近墙Evade或其它位置。
3. earliest()要明确是**身体高度有效期**的候选界，不能说它证明期间无全部危险。现Spell Antic/Cast1/2分支只算施法结束再跳，没有本次Cast2小符文最早亮；Recover k0也可能还有既存锤尾。即便身体高度成立，真实伤害支持、大小符文等必须独立原样查。若某分支无法排除就unknown，不因body高就删别的门。

**在同一个F104247上下文补齐其余准入**：复用现有48分支两路，完整保留静态原语/地形/坡面/针/ram、两路伤害支持、真实账本大小符文、每分支恢复时横向出圈和输入/时钟门。身体替代只作为显式的“高度假设成立”这一条件，不得顺便忽略其它体/危险；列第一个拒绝与最小余量。上界证据若尚未闭合，可以先报告条件性剩余检查是否都过及依赖项，仍不得记真实准入通过。尽量复用已有材料；确实需要重建时只重建这一个上下文，不重算三批/每圈逐拍/广测成本。分析改动只在新分析树，输出绑定b741、历史真实prefix和同拍预报；录像未来仍只许作标签。

**C1只需把设计语义说清，不实施：**“同一Run”到底是什么对象？失败交还是否已经结束它？104241本身在圈顶外，247才重新满足inside；“这次进圈结束”不能含糊到一方面241就清事件，另一方面又让旧事件跨任意未来圈。请给一份候选状态/失效条件，明确事件frame/episode/target与圈的创建身份、同一次空中阶段的关系，以及落地、其它链重新拿键、目标消失、监督接管/场景结束、圈消失怎样清理；原始事件没有Run就unknown，不造id。仍不改变inside或默默延长边沿，不把这种C1作用域当已批准。

一次同包正式答复：上界来源及未核项、该单点完整**条件**检查、准确的最小原case方案。唯一4.10原位改正“已证明”“不造模型”等过强表述：新增不可达规则仍要有独立域和证据。先确认一个完整而诚实的候选，再谈适用面统计、性能或执行器。现43ms工程成本保留，不重做正式P。源码保持b741，当前仅只读分析/设计改文；无新代码实现、C1、性能迁移、P/游戏/50权限，不碰AA/原录制/旧停批，不写Sol目录。'''
p = B/'sol/TO_OPUS.md'; raw = p.read_bytes(); header = '# Sol → Opus 留言队列'.encode()
assert raw.startswith(header) and title.encode() not in raw
p.write_bytes(header+('\n\n'+title+'\n'+body+'\n\n---\n\n').encode('utf-8')+raw[len(header):].lstrip(b'\r\n'))
p = B/'sol/STATUS.json'; s = json.loads(p.read_text(encoding='utf-8-sig'))
assert not s['live_or_budget_running'] and not s.get('own_offline_jobs') and not s['new50_authorized']
s.update(at=now, phase='RHX456_SINGLE_POINT_BOUND_AND_CONDITIONAL_ADMISSION382',
    last_opus_scan_number=456, last_opus_receipt_number=456, opus456_receipt=str(R/'REVIEW456.json'),
    pending_opus='seq382 F104247 only: bound evidence and full conditional admission, C1 lifetime clarification; no code/P/game',
    rhx456_new_bound_accepted=False, rhx456_three_batch_scan_authorized=False,
    next_owner='Opus same-task382 one-point analysis/design',
    next_phase='Single-context full conditional result and bound provenance, then review; no new source or live permission.')
p.write_text(json.dumps(s, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
add = '''
### 7.398 #456高度筛选只是条件假设；同包先核F104247，不扫三批（11-15）

源码仍b741、工作树运行码未变，原离线限定核收不撤。Sol读接口/geom脚本/生成器和源数据合同，Astra集中审新界限。Root只解析P15单点dump：6变体48分支96路、静态问题空，对拟合7.776的最小差1.7013309u，physical E37/throw8 late1/catch0/control29，数值核同。未调用模型或回放，未检查完整伤害/符文/出圈；ROOT456_SINGLE_POINT_READ/REVIEW456存证，不把几何筛选当准入或救血。

7.776来自逐帧median且少样本行删去、dev95非max；原witness当前姿势/贴地/时钟域不能自动继承。Know.durations.lo筛小占比和cut-short，非FSM绝对时限。原FSM顺序支持escape仍先进前摇；单点右怪37帧向右最多9.25u后距墙7.766>6的局部排除可用，不推广近墙。earliest混称全部危险不对：Cast2本次小符文/Recover0锤尾仍须独立查。高度界与最早时刻尚待证，不核收为硬不可达规则。

信号390同seq382只做F104247上界来源/根高/时钟/可达后继及在途反应，补所有48×两路剩余真实准入的条件检查；证据未闭合就明确按假设报告、unknown保留，不扫三批53/37或扩251/252同伴事实，不正式P重证高成本。C1仅澄清Run/圈创建身份/同一空中阶段及清理语义：241在顶外、247才门内，旧事件不能立即误清也不能跨任意未来圈；不实施或默改inside/持续期。原case有一个完整诚实候选后再谈适用面/性能/执行器。下一步归Opus只读分析与唯一设计更新，无新源、P/游戏/50权限，已实机源e097和AA/原件/旧停批保持。
'''
for root in [Path('C:/modeling/silksong_bot'), Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')]:
    p = root/'docs/plans/forum_clapper_plan.md'; assert b'### 7.398 ' not in p.read_bytes()
    with p.open('ab') as f: f.write(('\n'+add+'\n').encode('utf-8'))
print(json.dumps(dict(delivery=456, source_changed=False, new_body_bound_accepted=False,
                     next_scope='F104247 one-context conditional analysis/design', three_batch_scan=False, game_authorized=False)))
