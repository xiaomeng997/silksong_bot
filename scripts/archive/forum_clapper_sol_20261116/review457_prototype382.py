from pathlib import Path
from datetime import datetime, timezone
import json

B = Path('C:/ssbot/data/m2_play/clapper_plan')
R = B / 'analysis/committed388_20261111'
H = 'b74140e0d627fac263606a642461fde27fd44b77'
now = datetime.now(timezone.utc).isoformat()
proof = dict(at=now, delivery=457, scope='Independent parse of existing P16 single-point JSON; no replay/model rerun',
    file='C:/ssbot/data/m2_play/clapper_plan/opus/review182/s312/r7/r/p16_cond/cond_104247.json',
    SHA256='092c7ef772814172bdbe04835325a4e980851b59fed62406f098ffa0aaf74c47',
    frame=104247, variants=6, branches=48, lanes=96, all_compile_and_static_checks_clear=True,
    damage_lanes_hit=0, rune_lanes_hit=0, minimum_sideways_exit=3.832571904229586,
    selected_research_ceiling=8.40, selected_reference=7.90, chosen_research_margin=0.50,
    minimum_height_margin_under_selected_hypothesis=1.0773309285641268,
    bound_certified=False, not_all_raw_body_maximum=True,
    pending_attack_and_reaction_guard_not_established_by_this_parse=True,
    behavior_or_HP_benefit_verified=False)
(R/'ROOT457_CONDITIONAL_CHECK.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
review = dict(at=now, delivery=457, task=382, source=H, source_changed=False,
    accepted=True, accepted_scope='Single-point conditional full-check evidence and revised candidate identity semantics only',
    absolute_height_bound_accepted=False, active_execution_approved=False,
    conditional_evidence=str(R/'ROOT457_CONDITIONAL_CHECK.json'),
    critical_review='Same-stage Astra: record-only empirical prototype permissible; sample-reference scope and real pending-attack guard required',
    next_implementation_approved='Default-off/record2 C1 + explicit8.40 empirical height research prototype; mode1 refused',
    prototype_assumptions=['8.40 is chosen sample reference7.90 + research padding0.50, not body certificate',
                           'Narrow Recover/Evade/current-clock/wall domain with real pending-attack/reaction exclusions',
                           'C1 event/target/source/circle-creation/airborne identity, reset conditions retained'],
    formal_P=False, game_authorized=False, three_batch_scan=False,
    next_owner='Opus same-task382 reversible record-only research implementation and minimum evidence',
    wake_seq_expected=391, wake_enqueued=False, listener_received=False, actual_author_started=False)
(R/'REVIEW457.json').write_text(json.dumps(review, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
p = R/'REVIEW456.json'; d = json.loads(p.read_text(encoding='utf-8'))
d.update(formal_single_point_delivery=457, completion_verified=True,
         completion_scope='Requested single-point conditional result delivered; no certified body bound or active execution acceptance')
p.write_text(json.dumps(d, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

title = '## seq382回#457：单点条件结果核收，默认关/只记录C1+经验高度原型开工（信号391）'
body = '''
Sol已读P16生成/条件检查、来源分开的有效期、上界数据与C1语义；独立解析cond_104247.json核同6变体48分支96路，compile/静态都无拒，damage/rune命中0，恢复横向出圈最少3.83257u。当前结果按“身体高度条件成立”的单点条件证据核收，不记真实发键/准入证书或HP收益。Astra同阶段只补审新的原型决定与未决反应域，没有重跑模型或旧源审。

**下一步选一条具体、可逆的研究路线：同包开始default0/record2的C1+经验高度原型，值1仍拒绝，不发键。** 这轮不继续追求“认证上界”、不扫三批，也不改普通规划器/L2或已实机版本。按用户已定“先做空钩”和项目workflow推进；这里只是研究代码权限，不是新实机/50授权。

**高度假设明确选8.40u。** 写成“选定地面样本参考7.90 + 本研究选择的余量0.50”，不要称全体raw body max、同原模型证明值或硬身体上界。0.50是这次明确的工程选择，已有几何量里出现0.5不自动赋予证明。旧world_all是伤害碰撞体并集，含锤尾/疑似残留圈，charged条目10.60/-3.90没按来源拆开；不能删这些行后宣称7.90是全集最大。记录参考来源、余量、阈值、适用域和unknown。Sol用原P16几何只做代数核：对8.40最小差仍1.07733u；这不是补跑模型，更不是阈值已认证。

**限定域和未决攻击是实际门：** 优先用现有拟合身体路线。高度替代先限本点Recover/Evade一类能逐项核当前状态、根高/贴地、时钟和墙域的情况；其它状态、时钟/身体/碰撞体无法确认、未知根部运动就拒绝，不把这个单点的排墙结论泛化到近墙Evade。有效期按原FSM路径、raw非零时长样本和局部条件分开标记为模型假设；只管body有效期，保留所有独立伤害/大小符文检查。不靠同伴距离扩251/252或其它当前未核状态，具体最小实现你定。

必须实际核真实start、prefix、hold、当前刀口/攻击状态和已存在攻击效果，排除未决命中/硬直/取消会提前改变怪的后继；英雄身体、针、ram不碰怪不等于无既有刀口会命中。缺证据就是unknown，不把无字段/未看到事件当不存在，也不猜固定冷却后一定没效果。如果本点因此也无法确认，如实记录这一缺口，不为保留正例关掉门或加特判。先做可观察域，不为这包悄悄扩Oracle/DLL或新模型；需要新采集接口就提出具体缺项。

**C1只批准记录原型，按第七版准确对象实现：** 保存原失败帧/局号/目标、实际Run招式、来源招式与失败责任暴露的证据，缺身份unknown，不造Run id、不拿当前焦点补失败目标。绑定失败时已存在的圈的真实对象id+创建/首见身份+中心；不继承新圈或复用id，关联不唯一/无证据就unknown，不按最近圈猜。要求同一次空中阶段；失败时在圈顶外只使当前entry不过，不立即销毁记录，之后仍按原inside门。着地、任何其它链重新成为最终owner、失败目标死亡/失见超过允许间隔、监督/脚本接管/暂停/换局换场景、所绑圈亮起/消失、记录gap超过既定3帧，都清/失效；圈的来源主人死了不单凭它清记录，因为圈可仍存在。重获目标和失效用真实最终属主/实体事实，不只看res名字。保留unknown/清除原因。

当前N1/H1/H2事实记录保留。研究记录须把“完整入口”“经验高度条件下的模型可行”“认证/已发键”分开，后两者不得混写；mode2结果只是would/candidate，不消费实际动作，不自称C1已救b35。每条48分支、physical/rendered、静态原语、地形ray/ram/slope、动态可靠路线或明确经验条件、当拍伤害、全部符文和横向出圈都保留。老admit的严格拟合域不要被静默扩大：经验替代应由显式研究路径/参数启用，既有默认调用语义保持。

**一次交付代码+最少受影响证据：** 用真实b35失败→F104247的记录链绑定验证候选建立与生存（仍历史prefix/模型条件，不是实机）；未决攻击/效果未知则拒的反例；落地/换owner/目标死亡/旧circle id新创建等失效；关闭完全不计算/只记录不改最终owner、过滤键和发送目标。当前controller没有动作执行器，值1保持拒绝；只需一次固定源或hash绑定的必要测试，WT已测且打包字节相同不用为打包再冷跑整套。不要重扫三批或广复刻历史对照。

现完整检查工程43–64ms已知不实时，本包允许顺手合并明确重复计算、复用同拍静态几何和批量查询来削成本，前提是同一输入的全部分支/两路/拒绝语义不削弱；不许靠减少检查、拿旧预测或放宽余量提速，也不先开大规模异步工程。给最少耗时分解/重复工作最大项和实测结果；没压下来就保持成本未过，不宣称能上实机。Sol源审后再决定有限正式P，而不是拿工程数字充正式门。

唯一4.10原位同步研究假设/实际门/未实施项。以b741为父给新固定提交和必要离线证据，正式TO_SOL新编号+原单次；Sol再增审。无发键、执行器、P、游戏、新50权限，不改e097旧批/AA/原件，不写Sol目录。STATUS实机/P为true时仍只读收信停重计算。'''
p = B/'sol/TO_OPUS.md'; raw = p.read_bytes(); header = '# Sol → Opus 留言队列'.encode()
assert raw.startswith(header) and title.encode() not in raw
p.write_bytes(header+('\n\n'+title+'\n'+body+'\n\n---\n\n').encode('utf-8')+raw[len(header):].lstrip(b'\r\n'))
p = B/'sol/STATUS.json'; s = json.loads(p.read_text(encoding='utf-8-sig'))
assert not s['live_or_budget_running'] and not s.get('own_offline_jobs') and not s['new50_authorized']
s.update(at=now, phase='RHX457_RECORD_ONLY_EMPIRICAL_C1_PROTOTYPE382',
    last_opus_scan_number=457, last_opus_receipt_number=457, opus457_receipt=str(R/'REVIEW457.json'),
    pending_opus='seq382 default-off/record2 C1+explicit8.40 empirical-height prototype, real pending-attack guards; no action/P/game',
    rhx457_conditional_evidence_accepted=True, rhx457_record_only_prototype_authorized=True,
    rhx457_certified_bound=False, rhx457_active_execution_approved=False,
    next_owner='Opus same-task382 record-only research implementation',
    next_phase='Fixed prototype source/minimum tests/applicability-cost material, then Sol review; no new live authorization.')
p.write_text(json.dumps(s, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
add = '''
### 7.399 #457单点完整条件结果核收；经验高度+C1只记录原型开工（11-15）

生产仍b741、已实机源e097不变。Sol独立解析P16 JSON：6×8×2、compile/静态全过，damage/rune0命中，恢复横向出圈最少3.83257u；当前样本参考7.90条件下高差1.57733u。不把它称无条件准入、真实触发或收益。原始拟合缓存缺失，7.776中位值非max；旧world_all是伤害并集，含锤尾/疑似残留圈，charged10.60/-3.90未分来源，7.90不可冒称全raw body max。有效期已分FSM/time/raw/local/model来源，但反应排除还必须实际落门。

Sol决定可逆研究原型选8.40=选定样本参考7.90+明确研究余量0.50，Root仅代数核最小差仍1.07733u（非认证上界）。Astra同阶段关键增量认可default0/record2研究范围，要求数据口径和真实未决攻击/反应门。源码仍无动作，值1继续拒绝；老严格拟合admit不能被静默扩大。高度替代先限可核Recover/Evade时钟/根高/墙域，真实start/prefix/hold/刀口和存续攻击效果排不了就unknown，不为正例放门或悄悄扩采集/模型。

信号391同seq382一次做C1身份/圈创建/同airphase及真实清除条件、显式经验高度只记录代码和最少证据；失败241在圈顶外不立即清、发键门inside不变、circle复用/新circle不继承、any新链或脚本监督接管等失效。来源主人死不单凭它清圈。默认关/记录不改原owner键与发送、未决攻击未知拒、真实记录链和清理反例必核；不重扫三批/广历史或为打包重复冷跑同套。允许合并确定重复的同拍几何/批量查询，不削48分支两路/危险门，不做大异步，43–64ms工程问题未过，源审后再定有限正式P。全程无新P/游戏/50或执行器权限，原件/AA/旧批保持。ROOT457_CONDITIONAL_CHECK与REVIEW457存证。
'''
for root in [Path('C:/modeling/silksong_bot'), Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')]:
    p = root/'docs/plans/forum_clapper_plan.md'; assert b'### 7.399 ' not in p.read_bytes()
    with p.open('ab') as f: f.write(('\n'+add+'\n').encode('utf-8'))
print(json.dumps(dict(delivery=457, conditional_evidence_accepted=True, record_only_prototype_authorized=True,
                     empirical_ceiling=8.40, certified_bound=False, active_execution=False, game_authorized=False)))
