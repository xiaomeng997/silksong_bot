from pathlib import Path
from datetime import datetime, timezone
import json
import hashlib

B=Path('C:/ssbot/data/m2_play/clapper_plan')
A=B/'analysis/air_catch428_20261114'
R=B/'analysis/committed388_20261111'
ROOT=Path('C:/modeling/silksong_bot')
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
now=datetime.now(timezone.utc).isoformat()

def put(p,d):
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

audit=read(A/'ROOT_P_AUDIT.json')
assert audit['finite_measurement_valid'] and audit['actual_cleanup_verified']
assert audit['actual_owned_processes_exited']==24
s=read(B/'sol/STATUS.json')
assert not s['own_offline_jobs'] and not s['live_or_budget_running'] and s['own_live_session'] is None
assert not (B/'sol/performance/ACTIVE.json').exists()
review=read(A/'SOURCE_REVIEW_FINAL.json')
combined=dict(review,closed_at=now,formal_timing_completed=True,finite_measurement_valid=True,
    actual_cleanup_verified=True,performance_budget_pass=False,full_scheduling_gate_pass=False,
    formal_P_audit=str(A/'ROOT_P_AUDIT.json'),new_live_authorization=False,default_switch_remains_off=True)
put(A/'SOURCE_REVIEW_AND_P_FINAL.json',combined)
receipt=read(R/'RECEIPT428.json')
receipt.update(combined,stage='Source and finite P complete; user game pause remains',
    actual_owned_processes_exited=24,information_reply_written=True,no_new_wake_needed=True,closed_seq=367)
put(R/'RECEIPT428.json',receipt)
for num in [426,427]:
    r=read(R/f'RECEIPT{num}.json')
    r.update(repair_all_issues_closed=True,closed_by_delivery=428,closure_source=audit['source'],
        closure_review=str(A/'SOURCE_REVIEW_AND_P_FINAL.json'))
    put(R/f'RECEIPT{num}.json',r)

paired=read(B/'analysis/w13_50_landing425_20261114/PAIRED_RUNTIME354_COMPARISON.json')
seeds=[r['seed'] for r in paired['rows']]
assert len(seeds)==len(set(seeds))==50
proposal=dict(at=now,batch='w13_50_air_catch428_20261114',source=audit['source'],
    source_root=read(A/'SOURCE_PACKET_FIXED.json')['source_root'],
    source_packet=str(A/'SOURCE_PACKET_FIXED.json'),source_packet_sha256=hashlib.sha256((A/'SOURCE_PACKET_FIXED.json').read_bytes()).hexdigest(),
    source_review=str(A/'SOURCE_REVIEW_AND_P_FINAL.json'),formal_P_audit=str(A/'ROOT_P_AUDIT.json'),
    state='AWAITING_NEW_USER_AUTHORIZATION',authorized=False,game_started=False,
    maximum_attempts=50,seeds=seeds,seed_order='Same50 as landing425/runtime354',
    configuration='Same continuous-game baseline as landing425, with AIRSTRIKE=1; freeze one source for all50',
    overrides={'SSBOT_FORUM_AIRSTRIKE':'1','SSBOT_FORUM_LANDING_EXIT':'1',
        'SSBOT_FORUM_CHAIN_B13':'1','SSBOT_FORUM_CHAIN_B13B':'1','SSBOT_FORUM_RUNE_EXIT_FINAL':'1',
        'SSBOT_FORUM_SLAM_NO_NEW_GLIDE':'0','SSBOT_FORUM_TWO_PLAN_INLINE':''},
    scope='Fresh batch, one game continuously, full recording. No old stopped batch resumed.',
    protected_quit='HP<=2: protect that bout, continue to fill50; runtime fault: strict stop batch',
    criterion='All50 without HP<=2 protected quit, including postkill tail',
    preconditions='After explicit approval: original source/action/resources/exclusivity/readiness/recording/cleanup gates; no live permissions from heartbeat',
    limits='Finite P used LANDING_EXIT=0; proposal keeps the prior live batch LANDING_EXIT=1. No all-switch or live-win-rate claim.',
    prior_batch_authorization_consumed=True,default_switch_remains_off=True)
put(A/'NEW50_PROPOSAL.json',proposal)
mail='''## 核收回执：#428连踩源审与四窗同源有限P完成，seq367关闭（信息，无新派工/不唤醒）

d7cbe1a5/C4窄源复核通过，D427两项关闭：strict不读inv_until；真实prefix/start swing计算待接触，ev_pre与命令事件索引一致，观测POGO_OBS有生产来源；sent先绑定再验证/危险检查，成功续行回填本拍contacts。旧claw/SP10b保持。KEEP仍是旧fallback，不说它strict验证通过。87测试/32变异/701受影响为作者报告，未重跑；四窗没有垫刀，新增pending分支动态证据仍为合成测试，不冒充真实四窗覆盖。

Sol审核的entry_v4明确B−1录制夹具、B自控且计时起点、B+1模型，36隔离边界检查通过；执行实际核到B是决策tick，timing.start=B、B帧policy/计时前清空原FORCE_RUN，>=B强制键0。源728/支持4、输入207及八份240源manifest绑定保持。固定executor未改：ON/OFF各有零拍check+实际finalize，然后四窗各301拍测量及实际finalize。High/P0–15/不节流、逐拍policy与wire、无新JIT签名、24个自有进程真实退出和环境恢复均核实。

ON整拍p50/p99=13.5995/20.5307ms、max34.2818，49/301超16.67；OFF13.1658/21.2470ms、max28.2924，19/301超帧。ON属主136plan/116slam/49chain；OFF297plan/2slam/2two:idle。实际wire/owner差E0=46、E17=81、E19=60、E44=76，轨迹和属主变化，不拿分位差当search/helper纯开销，不签性能预算或全域调度门。

正式实际动作：ON E0/E17/E44模型各一刀命中，OFF四窗无命中；E19先接管后另一只Evade Scuttle拒，未当接住。E0/E44后续模型锤接触保留，不删录像旧顿帧后冒称无伤；E17/E19该窗无模型伤。录像怪不响应新英雄、四窗选择偏倚及无垫刀覆盖均保留。不是实机HP/胜率证据。

记录analysis/air_catch428_20261114/ROOT_P_AUDIT.json、SOURCE_REVIEW_AND_P_FINAL.json、P_PLAN和committed388_20261111/RECEIPT428。426/427由428闭合，原失败源和证据保留。current_source=d7、source_review_pending=false、own_jobs空/ACTIVE无；AIRSTRIKE默认仍0，游戏暂停，上一50授权已用完，无新增实机或续旧批权限。

本信仅结项信息，不给你新分析/实现任务、不发新wake。Sol已备NEW50_PROPOSAL（同50种子/单游戏/全录像，连踩开，落锤出口沿用上批1；有限P此轮为出口0的边界明确记），等用户决定是否预热新50。别自动开游戏或顺手改其它打法/旧飞针规则。

---

'''
p=B/'sol/TO_OPUS.md';text=p.read_text(encoding='utf-8-sig');head='# Sol → Opus 留言队列\n\n'
assert text.startswith(head) and '## 核收回执：#428' not in text
p.write_text(head+mail+text[len(head):],encoding='utf-8')
s.update(at=now,phase='AIR_CATCH428_SOURCE_AND_FINITE_P_COMPLETE_LIVE_PAUSED',source_review_pending=False,
    current_source=audit['source'],candidate_source=audit['source'],pending_opus=None,
    next_phase='Source/finite P complete. NEW50_PROPOSAL awaiting new explicit user authorization; no game/prewarm started.',
    air_catch428_finite_P_complete=True,air_catch428_performance_budget_pass=False,
    air_catch428_P=str(A/'ROOT_P_AUDIT.json'),air_catch428_next50_proposal=str(A/'NEW50_PROPOSAL.json'),
    live_paused_by_user=True,live_or_budget_running=False,own_offline_jobs=[],own_live_session=None,
    active_implementation=dict(owner='Sol',scope='Re-pogo source/finite P closed; next50 decision only',
        stage='Completed source and finite P; no extra live authority',formal_delivery_pending=False,coordination_seq=367))
put(B/'sol/STATUS.json',s)
p=ROOT/'docs/plans/forum_clapper_plan.md';text=p.read_text(encoding='utf-8-sig')
assert '### 7.362 ' not in text
p.write_text(text+'''

### 7.362 #428连踩续行源审闭合；四窗同源有限P完成，默认关/游戏暂停（11-14）

d7cbe1a5/C4由Sol与Astra xhigh窄复核：strict不读inv_until；实际prefix/起始挥刀算待接触与ev_pre弹起，索引对齐，观测POGO_OBS有生产来源；sent先绑定再验证/危险检查，续行回填本拍contacts，D427两项闭合。旧claw/SP10b语义保持，KEEP只是旧fallback非strict通过。87测试/32变异/701为作者报告不重跑；四窗没有垫刀，新增pending分支动态证据仍限作者合成测试。

Sol审新entry_v4及36隔离边界检查，固定executor未改，实际B是决策tick、B−1录制夹具/B自控且timing.start/B+1模型，B帧policy和计时前清空FORCE_RUN，计时内强制0。ON/OFF各零拍check+finalize、四窗各301拍measure+finalize；728源/支持4/输入207/八份240manifest、High/P0–15/不节流、逐拍wire、无新JIT签名、24自有进程实际退出及环境恢复核实。

ON整拍p50/p99=13.5995/20.5307ms、max34.2818，49/301超16.67；OFF13.1658/21.2470、max28.2924，19/301超帧。ON136plan/116slam/49chain，OFF297plan/2slam/2two:idle；动作/属主改变，不当纯helper成本，不签性能预算/全域调度。ON E0/E17/E44各模型命中一刀；E19接管后因另一只Evade Scuttle拒，不当接住；OFF四窗无命中。E0/E44后续模型接触保留，录像怪反事实、无垫刀覆盖及窗口偏倚不改写成实机HP/胜率。

analysis/air_catch428_20261114/ROOT_P_AUDIT、SOURCE_REVIEW_AND_P_FINAL、P_PLAN和committed388_20261111/RECEIPT428登记；426/427由428关闭、原失败源保留。信息核收回信不新增派工/seq/wake。current已核d7、source_review_pending=false、own_jobs空/ACTIVE无。NEW50_PROPOSAL已具体到同50种子、同游戏全录像、2HP退出后继续/故障停批、连踩1并沿用上批落锤出口1；本轮有限P为出口0的配置边界明确保留。上一50授权已用完，游戏暂停、默认仍关，无预热/新局/续旧停止批/改AA或原录像；等用户明确决定新50。
''',encoding='utf-8')
print(json.dumps(dict(source_and_finite_P_complete=True,new50_proposal=str(A/'NEW50_PROPOSAL.json'),
    new_live_authorized=False,default_off=True,game_paused=True)))
