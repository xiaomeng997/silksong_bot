from pathlib import Path
import datetime, hashlib, json, os, shutil

B=Path('C:/ssbot/data/m2_play/clapper_plan')
A=B/'analysis/b13_399_20261112'
R=B/'analysis/committed388_20261111'
SRC='0e3d65936ae195ad1da4c64f48344461bd958d6f'
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def put(p,d):
    p=Path(p);q=p.with_name(p.name+'.tmp');q.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(q,p)

A.mkdir(exist_ok=True);R.mkdir(exist_ok=True)
for n in ['b13_review_probe.py','b13_review_probe.json']:
    src=Path('C:/modeling/silksong_bot/tmp')/n;dst=A/n
    assert not dst.exists()
    shutil.copy2(src,dst)
review='''# Sol 独立源审 #399：B13 同包两项侧移接线修复

固定源 0e3d65936ae195ad1da4c64f48344461bd958d6f，父 ec95ccce。按用户原话110先做 committed chain，当前只审第一包 transfer 静止目标身体守卫；通用走位、空中接冲锤专项、翻越和地面接近不扩入。本次源审未通过，不运行正式P或新实机。

## 需修复

1. **侧移生命周期跨落地泄漏。** transfer:968–971持续采用 b13_steer，1947–1958外部空中入口落地仍续用同一个Run，2012–2014继承active.v，未清除上一次飞行的侧移。最小合成生产形态序列：f1000 guard真实选L（预计1007入身、lead5），f1012落地转jump发R+J仍留L，f1016再升空发L+J且b13记录仍是1000；同状态删除旧steer后发J/新steer0。它应只管当前空中避让，不能在新起跳恢复旧决定。hook释放1834–1848也应核对相同动作边界，尚未单独实测hook失败。

2. **检查另一只身体的未来路线未采用持续侧移。** native:1216–1222后续键按plan.side构造，只有第一帧采用真实mask；实际guard draft里plan.side=R、steer=L，_route_keys=[L,R,R,...]而air_approach_keys=[L,L,L,...]。1719–1730普通非seam、非opening空中路径仍进入_route_ahead。差异路线若包含另一只怪且未先被目标接近区间截断，可能错拒或漏查。机器收据证明键预测不一致，不宣称已经证明具体实况新增伤害。

复现脚本和机器结果：analysis/b13_399_20261112/b13_review_probe.py、b13_review_probe.json。真实transfer.propose和路线键helper，人工串接有效形态状态；无几何/发送全闭环，无实机或P结论。E24–31/Idle、禁JIT、单线程，未改交付源码。Sol逐处独核，Astra只做关键模型/接线重点审核，没有重跑Opus1356项。

## 已核和保留边界

fo/off、prefix/hold、contact-2区间一致；提前出刀仍留no_strike、seam/bound、被命中Idle限制。另两批23例此后已完成；cmp_b13.json共37例，按body非空重算B0=31、B13=14，与补充一致。敌人仍按录像走、英雄模型替代；不当作可救回17次实机伤害或胜率预测。影子成功101刀、既有1356项及变异结果归Opus证据，本次未重复跑。

已在身体内、踩中后持续重叠、vault、地面接近、走路目标仍是明列后续，不能称完整B13已修。现三运行文件已绑定；同包修复后只补这两处动作边界与真实路线的关键回归及受影响P，不增加无关矩阵。
'''
(R/'REVIEW399.md').write_text(review,encoding='utf-8')
w=json.loads((B/'sol/OPUS_WAKE.json').read_text(encoding='utf-8'));assert w['seq']==348
seq=349
receipt=dict(at=now(),delivery=399,source=SRC,source_review_accepted=False,review=str(R/'REVIEW399.md'),
    blocking=['b13_steer survives landing/rejump','route future keys ignore persistent b13_steer'],
    independent_probe={n:sha(A/n) for n in ['b13_review_probe.py','b13_review_probe.json']},
    reported_closed_loop_cases=37,recomputed_model_body_cases={'B0':31,'B13':14},
    formal_P_started=False,new_game_started=False,live_released=False,
    next_owner='Opus same-package repair',handoff=dict(wake_seq=seq,mail_written=False,wake_enqueued=False,listener_received=False,mail_marked_seen=False,work_started_verified=False,completion_verified=False))
put(R/'RECEIPT399.json',receipt)
mail=B/'sol/TO_OPUS.md';old=mail.read_text(encoding='utf-8')
task='''## #399 同包退回：只修 B13 侧移生命周期和路线预测（Sol，11-12；seq349）

已独审0e3d6593，暂不接受/P/开游戏。不是新增战术包。两处确定接线缺陷详见analysis/committed388_20261111/REVIEW399.md；最小production-shaped复现脚本/JSON在analysis/b13_399_20261112。

1. b13_steer没有在落地续Run→再起跳失效。guard在f1000实际选L，落地转jump发R+J，f1016升空却因旧steer发L+J；删除旧steer同状态发J。请按当前飞行避让的生命周期清理，顺带核hook释放/重新起跳等同类动作边界；不在每拍清掉仍有效的避让。
2. native._route_keys(1216–22)仍按plan.side生成后续键，只首拍用真实mask：同一实际guard draft检查[L,R,R,...]、air_keys执行[L,L,L,...]。请使_route_ahead读取该Run真正会继续发的方向/余留J及现有滤除规则；保留原几何和范围。机器收据未证明具体伤害，不需为此做新全局策略。

请同包给固定SHA、上述两个最小回归（松键0和反向、落地再跳；动作边界按必要性）、真实最终按键与route一致的证据，并核正常提前下劈不退化。复用已有1356/101正例证据，不默认重跑整套或37例全量，变化影响才加。不开P/游戏、不改AA/录制；Sol收到正式交付后继续生产路径及受影响P。新完成37例模型body计数31→14已收，不能抵消上述接线缺口。

---

'''
title='# Sol → Opus 留言队列\n\n';tail=old[len(title):] if old.startswith(title) else old
q=mail.with_suffix('.md.tmp');q.write_text(title+task+tail,encoding='utf-8');os.replace(q,mail)
put(B/'sol/OPUS_WAKE.json',dict(seq=seq,at=now(),note='#399 same-package B13 steer lifecycle and route-key integration repair; see Sol TO_OPUS and REVIEW399. No P/game or broad tactics.'))
receipt['handoff'].update(mail_written=True,wake_enqueued=True,mail_sha256=sha(mail));put(R/'RECEIPT399.json',receipt)
s=json.loads((B/'sol/STATUS.json').read_text(encoding='utf-8'))
assert not s['live_or_budget_running'] and not s.get('own_offline_jobs')
s.update(at=now(),phase='B13_399_REPAIR_WAIT',last_scanned_opus_number=399,source_review_pending=True,
    measurement_candidate_source=SRC,opus399_state='source_rejected_two_steer_integration_defects',
    opus399_review=str(R/'REVIEW399.md'),opus399_receipt=str(R/'RECEIPT399.json'),opus399_handoff=receipt['handoff'],
    pending_opus=dict(seq=seq,delivery=399,task='B13 same-package steer lifecycle/route repair',state='enqueued_not_yet_listener_verified'),
    next_action='Opus fixes two B13 steer wiring defects in same package; Sol verifies receipt and formal delivery then affected production/P. No new live release.',
    implementation_scope_exception='user quote110: committed-chain first B13 package only; generic positioning remains deferred')
put(B/'sol/STATUS.json',s)
plan=Path('C:/modeling/silksong_bot/docs/plans/forum_clapper_plan.md')
with plan.open('a',encoding='utf-8') as f:f.write('''\n### 7.331 #399 B13第一包独审：两项侧移接线缺口，同包回修（11-12）

用户原话110先做committed chain，Opus交0e3d6593的transfer静止目标身体守卫；并非完整B13/vault/地面接近。Sol独核源码和证据，Astra按workflow只审关键接线；没有重跑1356项。37例模型结果按cmp_b13.json重算body非空B0=31、B13=14，不当实机可救伤害或胜率。

源审未过：b13_steer跨落地续Run泄漏到下一次跳跃；native路线预测后续仍按plan.side，未按持续松键/反向。真实transfer.propose合成有效形态序列已复现旧L决定在新起跳重现；同draft检查[L,R,R,...]而执行[L,L,L,...]。不宣称完整几何/发送/实况新增伤害。复现和收据在analysis/b13_399_20261112；独审REVIEW399.md、RECEIPT399.json在analysis/committed388_20261111。

同包两修已写Sol TO_OPUS并单次唤醒seq349；入队不当收件/完成，待核监听和正式交付。P/新50均未启动，未增加实机权限；旧停止批、AA和原录制不动。已在身体内/踩后保护期结束等范围缺口仍列后续。收到修订后只补受影响动作边界、生产路径和P，继续执行。\n''')
print(json.dumps(dict(review=str(R/'REVIEW399.md'),receipt=str(R/'RECEIPT399.json'),mail_written=True,wake_seq=seq,enqueue_verified=json.loads((B/'sol/OPUS_WAKE.json').read_text())['seq']==seq,mail_sha256=sha(mail)),ensure_ascii=False))
