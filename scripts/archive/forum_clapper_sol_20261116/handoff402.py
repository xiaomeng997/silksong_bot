from pathlib import Path
import datetime,hashlib,json,os,shutil

B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/b13b_402_20261113';R=B/'analysis/committed388_20261111'
SRC='b394463dee3f947b702b7f6abb6a52ca98efff13';now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def put(p,d):
 p=Path(p);q=p.with_name(p.name+'.tmp');q.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(q,p)

A.mkdir(exist_ok=True)
for n in ['b13b_review_probe.py','b13b_review_probe.json']:
 p=Path('C:/modeling/silksong_bot/tmp')/n;q=A/n;assert not q.exists();shutil.copy2(p,q)
review='''# Sol #402 独立源审：B13B选中的安全行没有落实到实际按键

固定 b394463dee3f947b702b7f6abb6a52ca98efff13，父61560c93。设计原话111“你决定顺序”已核；当前为小符文近身地面接近/踩后保护期出身体同包，不扩到其它后手、接口或低跳。Source review不通过，先修同包接线；本轮没有P或游戏。

## 一项阻挡

transfer.b13b_sprint_jump约913行：三行分别原冲刺跳、只松DASH、松DASH及侧键；any(row1/row2安全)便返回release，没有保存获准行。propose约2076行只置p.sprint_jump=False，实际继续带plan.side，等于只执行row1。row2-only安全时被错误放行了row1。

Sol独核代码及Astra重点审核的真实propose/render/ChainSim短探针（无helper/几何stub）：地面Sprint phase2、MODE_T=.1，英雄x25、vx17.5，Idle目标root28，PREV/在途R+DASH。原行F1003入身/F1009起跳；row1只松DASH F1002起跳、F1003入身；row2松DASH和侧键 F1002起跳、无入身。返回release，实际proposal=R+J(2097153)，获准行应J(1)。Idle且非over时，native casting_side_held_back不会替它修正；F1002才观察升空，再发键最早F1004，晚于模型F1003入身。这是选行与执行不一致，不是一个要死磕实机精确帧的新策略。

探针b13b_review_probe.py/json已冻结到analysis/b13b_402_20261113。生产形态合成模型、真实过滤和前缀，非录像/实况，未经过完整policy/发送，不据此声称实际掉血可救。E24–31/Idle、禁JIT/单线程，未重跑1514项。

## 其余审阅及范围

新保护期判断使用每条真实roll的F_INVULN，无新模型时间坐标。inside用全段首次比较存在“早先保护期接触后离开，再外部进入”可能误分类的语义疑点；本次少量真实roll没得到可触发见证，不列第二项阻挡、不扩矩阵。

已核已有12项多数把b13b_sprint_jump或render/roll stub后只断言是否含DASH，未核row2获准时实际仍带侧键。B13B关保留父版本行为；旧B13已核结果不作本包通过。Opus的F-25闭环修正明确说明旧F-12起点缺冲刺跳锁定，故旧37例模型31→14不推广成新实机收益。

同包要求：保存获准行及其侧键选择，使实际发送、后续渲染/路线预测和接受检查一致；用上述真实row2-only场景及row1本来安全的正例/开关关闭补关键回归，并给实际生产/发键的受影响场景入口。不要为了这一处重跑47文件/1514或34整局/37全量；无新影响才不扩大。源审通过后Sol继续真实路径和受影响P，再按有效授权及原门安排同种子50。剩余统计可继续，P前需让出重计算资源。
'''
(R/'REVIEW402.md').write_text(review,encoding='utf-8')
receipt=dict(at=now(),delivery=402,source=SRC,source_review_accepted=False,review=str(R/'REVIEW402.md'),
 blocking=['row2-only accepted but proposal sends row1'],independent_probe={n:sha(A/n) for n in ['b13b_review_probe.py','b13b_review_probe.json']},
 nonblocking=['inside global-first comparison has no reachable witness from bounded probe'],formal_P_started=False,new_game_started=False,
 next_owner='Opus same-package selected-row wiring fix',handoff=dict(wake_seq=351,mail_written=False,wake_enqueued=False,listener_received=False,mail_read_verified=False,work_started_verified=False,completion_verified=False))
put(R/'RECEIPT402.json',receipt)
p=B/'sol/TO_OPUS.md';old=p.read_text(encoding='utf-8');title='# Sol → Opus 留言队列\n\n';assert old.startswith(title)
task='''## #402同包回修：把获准的松键行落实到实际按键（Sol seq351）

已独审b394463d，不接受/P/开游戏。唯一确定blocking：b13b_sprint_jump允许只row2（松DASH+侧键）安全也返回release，而propose仅关sprint_jump仍发row1（方向+跳）。真实无mock探针：地面Sprint phase2/MODE_T=.1，英雄x25/vx17.5，Idle目标root28，在途R+DASH；原行1003入身/1009起跳，row1 1002起跳/1003入身，row2 1002起跳且无入身；实际proposal R+J，获准应J。Idle非over没有native侧键抑制补救，升空后再守卫已晚。不是新战术或精确边界专项。

REVIEW402.md在analysis/committed388_20261111，探针.py/json在analysis/b13b_402_20261113。请同包保留获准候选，并使当前实际按键、后续render/route预测和被检查行一致；不是只改一拍看起来像的mask。补row2-only真实模型回归、row1本来安全/关闭开关对照，必要实际生产路径/受影响P入口（可复用已有回放entry，场景98805 release、7098 inside；缺真实正例可明确合成有效形态，不用Clear桩当完整通过）。完整提供固定SHA/已完成证据/限制，Sol收到即续审和受影响P。

不要默认再跑47文件1514或34/37全量；本修仅覆盖选行/发送接线，有新影响才扩大。inside全段首次比较有语义疑点，但少量真实roll没复现，不列第二项阻挡，不为它扩测。你后续第3项可做离线统计，不改下一包代码；正式P前停止新增重计算并让资源。不开P/游戏，不改AA/原录制/旧停止批。

---

'''
q=p.with_suffix('.md.tmp');q.write_text(title+task+old[len(title):],encoding='utf-8');os.replace(q,p)
p=B/'sol/OPUS_WAKE.json';assert json.loads(p.read_text())['seq']==350
put(p,dict(seq=351,at=now(),note='#402 same-package selected-row execution fix: row2-only safe but proposal sends row1. Read REVIEW402 + Sol-owned real model probe. Preserve selected row through send/render/route. Bounded regressions/production entry only; no suite/P/game or broader tactic.'))
receipt['handoff'].update(mail_written=True,wake_enqueued=True,mail_sha256=sha(B/'sol/TO_OPUS.md'));put(R/'RECEIPT402.json',receipt)
p=B/'sol/STATUS.json';s=json.loads(p.read_text());assert not s['live_or_budget_running'] and not s.get('own_offline_jobs')
s.update(at=now(),phase='B13B_402_SOURCE_REPAIR_WAIT',last_scanned_opus_number=402,source_review_pending=True,measurement_candidate_source=SRC,
 opus402_state='source_rejected_one_selected_row_wiring_defect',opus402_review=str(R/'REVIEW402.md'),opus402_receipt=str(R/'RECEIPT402.json'),opus402_handoff=receipt['handoff'],
 pending_opus=dict(seq=351,delivery=402,task='B13B selected-row execution wiring same-package repair',state='enqueued_not_yet_listener_verified'),
 implementation_scope_exception='user quote111 delegates order to Opus: B13B ground near approach + protection-expiry body exit; later cold-handoff stats read-only',
 next_action='Verify seq351 actual receipt/work and formal repaired source delivery; then Sol affected production/P. No P/game now, no broad new code or repeated suite.')
put(p,s)
p=Path('C:/modeling/silksong_bot/docs/plans/forum_clapper_plan.md')
with p.open('a',encoding='utf-8') as f:f.write('''\n### 7.334 #402 B13B尾项源审：一项选行/发键缺陷，同包回修（11-13）

用户原话111“你决定顺序”及设计7.1后续顺序已收，本包b394463d（父61560c93）为近身地面冲刺跳/踩后保护期出身体；不扩其它策略。新增12项/1514开关组合是Opus证据，Sol不默认重跑，Astra按workflow仅审关键接线和少量真实模型探针。

一项blocking：b13b_sprint_jump任row1或row2安全就release，但propose只关sprint_jump仍按方向。真实propose/render/ChainSim已证row2-only：Sprint地面x25/vx17.5，Idle目标root28，MODE_T=.1/在途R+DASH；row1跳起1002、入身1003，row2跳起1002且不入身，实际仍发R+J而获准行是J。非casting/over无适配补救，空中再发最早1004已晚。合成有效形态模型，非实况或完整policy/发键，不当可救HP。

inside全段首次比较的二次进入疑点无实际可达见证，不列第二项阻挡/不扩矩阵。F-25模型起点修正及剩余范围限制保留。REVIEW402/RECEIPT402在analysis/committed388_20261111；失败探针在analysis/b13b_402_20261113。Sol TO_OPUS同包选行/发送/render/route一致修复已入队seq351，监听/开工/正式交付另核，不能以入队当完成。当前没有P/游戏，旧61560有限P仍仅适用父版，不把它冒充B13B通过。\n''')
print(json.dumps(dict(source=SRC,review_accepted=False,mail_written=True,wake_seq=351,probe_copied=True,P_started=False),ensure_ascii=False))
