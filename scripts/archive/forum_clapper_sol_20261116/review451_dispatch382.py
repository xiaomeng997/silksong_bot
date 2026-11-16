from pathlib import Path
from datetime import datetime, timezone
import json

B = Path('C:/ssbot/data/m2_play/clapper_plan')
R = B / 'analysis/committed388_20261111'
H = 'e097f60e42c518eb962782e71c0680ba543016a9'
now = datetime.now(timezone.utc).isoformat()
title = '## seq382：#451空钩出圈设计回修，三项合并；只改设计，尚不写生产代码'
body = '''
用户“先做空钩”的方向可以继续；Sol已读4.10、原语/共享圈检查/估算脚本，Astra同阶段集中窄审完成。**#451原文暂不通过实施前设计审**，不是拒绝空钩方向。请同一包改唯一设计文档4.10并正式回新编号；不拆测试/收据小单，不写代码/P/游戏。当前已审源仍e097f60e，GD450新50待本聊天实际答复，不把空钩夹进去。

**1. 本次动作生命周期必须闭合。** 起用后到按键生效前仍可输入、动画仍非Harpoon，不能据此立即认为“恢复”。写清待发送→已发送待本次开始→实际看到本次开始→实际恢复的证据与所属目标帧；出钩脉冲过期不得重排。35+3只是失败看门狗，不是恢复证据；没有真实恢复应交安全监督/既有运行故障处理，不能当正常完成交还。真实完成再核实际身体框横向出圈；异常钩怪/墙与受伤按缺陷登记。1137删“以后不会再进圈、不用再推演”的保证：离心的当前终点不约束交还后规划器。首包只承诺真实出圈交还，后续重入/亮时位置另记，不扩全局接管规则。请明确锁定时仍跑普通plan的整拍成本与保持tracker/监督/必要预报的方式，不能一面每拍plan、一面写起用后零成本。

**2. 已有模块只给unchecked轨迹，准入覆盖完整实测不确定性和时钟。** compile_empty:3–7/127–180明确全程安全和真实控制归调用者。六变体的实际prefix/过滤、身体/射线/ram/地形/全部伤害/两种符文须共用同一时间原点，检查到最晚真实恢复；预报不足或未知分支就拒绝/unknown，不能把末帧身体冻结充作已知安全。rune_life.rows是STATE游戏时钟相对帧，需写出与path.games、实际发键/activation_delay、forecast索引的换算，不能直接用实录帧差替游戏时间。当前面对方向也须在各变体P入口一致、确有依据；不增加未测转身。

已知1/173短行程必须先核实，不要仅凭CLAW_DASH_STEPS=6断言现模型遗漏，也别直接忽略：hero2.claw_unhooked:95–108按7个渲染帧fs积分，某些格点已可能有5物理步。请只用那一个已知短行程说明：是现有lattice/throw/delay已覆盖，还是额外Catch提前分支；后者需覆盖整段或明确无法准入，不能只把终点减1.4u当全程验证。不为它重扫173或凭空改经验模型。

**3. 首包收窄到N1，N2先不作为起用门。** 把整条res.cmd锁完再接8条逃生，只能证明这组固定续段没找到路，不能证明规划器途中改走也没路；超预报身体冻结同样不是必堵证据。exit_veto本来是一键后对比现在是否丢失出口，且有invuln/strike例外，不能直接继承为本包全程无豁免的准入。首包只在最终plan所有权+forced_risk及原入口门满足时检查朝向侧6变体；N2留设计后续/离线诊断，生产不必每拍算8x80；反向也无需生产再算6次，只留离线候选。只收横向出圈、default0/只记2/启用1同意。将来N2按实际选中行命中来保守skip，可以叫“命中后路径未检查”，不能记成已证明普通可走。

**最少证据即可，不要首包扫三批每个圈每一拍。** 设计先列c86 b35 F104263一个真实入口窗口，配本次未开始的生命周期/预报不足拒绝、已知短行程覆盖说明；实现获审后只补真正影响的正反例、真实policy所有权/过滤键/发送目标帧和受影响计时。三批53被炸/37估计可出/158空中未中均非可救HP或误用标签：bigrune_escape使用已录怪未来、简单飞行且hook传全1物理步，估算用途限机会筛选。实际策略可用性/安全和收益要另核，不强制重算三批或把统计当验收真值。

请在同包新版设计写清上述生命周期、短分支覆盖结论与时钟映射、N1首包接口/成本及最少验收后回信。审过再实现；本次无游戏/P/新50权限、不重开旧停批、不动AA/原录制，不写Sol目录。若Sol实际P/游戏开始，按STATUS只读收信、停重计算。Sol不改你设计正文，仅登记审阅及本任务。''' 

mail = B / 'sol/TO_OPUS.md'
raw = mail.read_bytes()
assert title.encode() not in raw
header = '# Sol → Opus 留言队列'.encode()
assert raw.startswith(header)
tail = raw[len(header):].lstrip(b'\r\n')
mail.write_bytes(header + ('\n\n' + title + '\n' + body + '\n\n---\n\n').encode('utf-8') + tail)

review = dict(at=now, delivery=451, source=H, source_changed=False,
    accepted=False, design_accepted_for_implementation=False,
    scope='empty hook out of big rune, sole design 4.10; no production change',
    independent_review='Sol primary-source inspection plus Astra same-stage concentrated review',
    reviewer='/root/walk418_review', task=382, wake_seq_expected=385,
    blockers=['per-action actual-start/restore lifecycle and timeout fault handoff',
              'whole path coverage/forecast horizon/game-time alignment/known short-flight branch',
              'N2 overclaims no-way and repeats expensive row search; first package N1 only'],
    decisions=['facing only, horizontal exit only, default0/shadow2/active1',
               'N1 first package; N2 and opposite direction offline later',
               'revise design in one package before production implementation'],
    evidence=['knife_chain_empty_needle.py:1-7,127-180',
              'hero2.py:76-111', 'rune_life.py:128-176,232-284',
              'bigrune_escape.py:1-16,92-101'],
    estimates_not_preventable_HP=True, new_tests_run=False, new_replay_run=False,
    new_P_run=False, game_authorized=False,
    pending_GD45050_authorization_unchanged=True,
    next_owner='Opus task382 design revision only',
    wake_enqueued=False, listener_received=False, actual_author_started=False)
(R/'REVIEW451.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

sfile=B/'sol/STATUS.json'; s=json.loads(sfile.read_text(encoding='utf-8-sig'))
assert s['current_source']==H and s['live_or_budget_running'] is False
assert s['new50_authorized'] is False and s['authorized_batch'] is None
s.update(at=now, phase='GD450_NEW50_PERMISSION_PENDING_RHX451_DESIGN_REVISION382',
    last_opus_scan_number=451, last_opus_receipt_number=451,
    opus451_receipt=str(R/'REVIEW451.json'),
    pending_opus='seq382: #451 design revision only; no code/P/game; formal new delivery pending',
    next_phase='Opus revises RHX design; Sol awaits existing GD45050 actual reply; no game before reply.',
    rhx451_design_review_pending=True, rhx451_design_accepted=False)
sfile.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

paragraph='''
### 7.391 #451空钩出圈设计暂不核收；seq382三项合并回修（11-15）

实际WT仍e097f60e、运行代码干净，仅4.10设计新增。Sol读原语/hero2格点/共享圈时钟和exit_veto/机会估算，Astra同阶段集中关键审同：须先看到本次真实开始再认真实恢复，35+3只能失败看门狗；恢复时核实际横向出圈，删终点离心就保证交还后不重入的承诺。全程身体/射线/ram/符文/伤害须同prefix/游戏时钟并罩到最晚恢复，预报不足unknown、不冻结末帧冒称已知安全；1/173短行程只核该例是否已在现有格点内，不凭常量或只缩终点断言覆盖。整条res.cmd加8逃生失败不等于规划器无路，首包定N1/朝向侧六变体，N2及反向留离线后续；default0/shadow2/active1、横向出圈同意。每拍仍规划就不能声称锁定成本零。

seq382一包改唯一设计后正式回新号，审过再实现；先取b35 F104263与关键生命周期/未知拒绝、已知短行程覆盖，不要求三批每圈逐拍重算。53/37/158仅机会筛选，估算使用已录怪未来与全1物理步，不算可救HP或误用真值。REVIEW451存证，发送/实收/真实开工分别登记，不把排队当完成。GD45050先前准备框仍待实际答复，源/50种子/开关不夹本设计，无新游戏/亮屏/P权限，不重开旧停批/AA/原录制。
'''
for root in [Path('C:/modeling/silksong_bot'),Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')]:
    p=root/'docs/plans/forum_clapper_plan.md'
    assert b'### 7.391 ' not in p.read_bytes()
    with p.open('ab') as f: f.write(('\n'+paragraph+'\n').encode('utf-8'))
print(json.dumps({'written':True,'task':382,'delivery':451,'review':str(R/'REVIEW451.json'),
                  'design_accepted':False,'production_source':H,'GD450_permission_pending':True}))
