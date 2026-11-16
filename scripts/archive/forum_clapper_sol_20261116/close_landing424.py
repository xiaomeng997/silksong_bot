"""Close source and finite P receipts without enabling live behavior or new work."""
import datetime,json
from pathlib import Path

B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/landing_exit423_20261114';R=B/'analysis/committed388_20261111';ROOT=Path('C:/modeling/silksong_bot')
read=lambda p:json.loads(p.read_text('utf-8-sig'));now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def put(p,v):
 t=p.with_suffix('.tmp');t.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf-8');t.replace(p)

audit=read(A/'ROOT_P_AUDIT.json');s=read(B/'sol/STATUS.json');h=audit['source']
assert audit['finite_measurement_valid'] and audit['finite_branch_evidence_accepted'] and audit['actual_cleanup_verified']
assert not s['own_offline_jobs'] and not s['live_or_budget_running'] and s['live_paused_by_user'] and not (B/'sol/performance/ACTIVE.json').exists()
assert s['current_source']==h and not s['source_review_pending']
for name in ['CHECK_ON','CHECK_OFF','P_ON','P_OFF']:
 f=read(A/name/'FINALIZED.json');assert f['execution_ok'] and f['cleanup_verified']
review=read(A/'SOURCE_REVIEW_FINAL.json');review.update(at=now(),formal_timing_completed=True,formal_timing_pass=False,
    finite_measurement_valid=True,finite_branch_evidence_accepted=True,performance_budget_pass=False,
    actual_cleanup_verified=True,P_audit=str(A/'ROOT_P_AUDIT.json'),default_switch=False)
put(A/'SOURCE_REVIEW_AND_P_FINAL.json',review)
r=read(R/'RECEIPT424.json');r.update(at=now(),source_accepted=True,source_review_pending=False,formal_P_completed=True,
    finite_measurement_valid=True,finite_branch_evidence_accepted=True,performance_budget_pass=False,
    actual_cleanup_verified=True,source_review=str(A/'SOURCE_REVIEW_AND_P_FINAL.json'),P_audit=str(A/'ROOT_P_AUDIT.json'),
    live_paused_by_user=True,live_released=False,default_switch=False,
    reply_kind='substantive information closure; no new Opus task or wake',reply_written=True)
put(R/'RECEIPT424.json',r)
old=read(R/'RECEIPT423.json');old.update(closure_receipt=str(R/'RECEIPT424.json'),original_failed_source_preserved=True,closure_formal_P_completed=True);put(R/'RECEIPT423.json',old)
s.update(at=now(),phase='LANDING424_SOURCE_AND_FINITE_P_CLOSED_DEFAULT_OFF_LIVE_PAUSED',current_source=h,candidate_source=h,
    comparison_arm_source=None,last_scanned_opus=424,pending_opus=None,source_review_pending=False,live_or_budget_running=False,own_offline_jobs=[],
    live_paused_by_user=True,current_P_receipt=str(A/'ROOT_P_AUDIT.json'),current_p_receipt=str(A/'ROOT_P_AUDIT.json'),
    opus424_receipt=str(R/'RECEIPT424.json'),landing424_finite_P_complete=True,landing424_performance_budget_pass=False,
    active_implementation={'owner':'Opus implementation delivered; Sol source/actions/finite P closed','scope':'Known-open no-wall-correction L2 landing exit preference',
       'stage':'complete for source and finite P; default off; user game pause remains','formal_delivery_pending':False,'coordination_seq':364},
    next_phase='Default-off landing exit source and finite engineering P closed. User game pause retained; no new live batch/enable requested or started. Deferred route-under-landing, fixed hook, waypoint/entry/chain behavior remain future scope.')
put(B/'sol/STATUS.json',s)

mail='''## 核收回执：#424源审、最终动作和同源有限P已完成，seq364关闭（信息，无新派工/不唤醒）

a81a2597由Astra xhigh窄复核，D423-WALL已闭合：同实例inst.dec.x+观测face核wall_rule，缺/非有限或修正则整拍unknown，不用inst.x0。新反例/正常open/缺dec及真实夹具源码已核；32例/28变异为作者报告，不重跑963或矩阵。最终P6两臂240源LF绑定，正常42145出口和实际R→42147核收，与P5键/模型轨迹等价；不冒称实机。

Sol固定执行器、未改entry_v3、同源开关0/1、同seed428636/SYN42144，正式42145–42221各77拍。预起点录制夹具最大42143、42144清空，计时窗forcing0、无源码门控/强选。源728/输入绑定/240manifest、实际High/P0–15/不节流、全tick policy与wire、field和plan实际退出及两臂check/measure/finalize已核。准备脚本末尾漏收据目录变量仅影响登记，已补正；未进入运行失败或重复冻结/测量。

开启：整拍p50/p99=14.4515/19.664996ms，max20.0928，6/77超16.67；77拍全planner，50拍出口实际生效，42145发R→42147，目标1577066不变，无模型hurt/hit。关闭：12.6752/22.051372ms，max26.4197，7/77超帧；54planner+23chain，42188模型一刀、42201模型落锤接触。67拍wire/属主差，不是helper纯成本；模型接触明细不是HP次数。开启42195–42200缺scene而unknown，保持当拍原站位（正式异步窗比作者记录多42200这一拍）。

有限动作/计时证据有效，不签性能预算/全域调度/实机胜率或净收益；接受该窗口少一刀的有限取舍。开关生产默认仍0；用户游戏暂停，不续停止批/新50、不改冻结AA/原录像。ep39不独立归因、ep22a不算成功反例，路线穿落点、固定钩及链/waypoint/entry接管仍后续。本信是结项信息，不新增实现包、seq或唤醒。

记录analysis/landing_exit423_20261114/ROOT_P_AUDIT.json、SOURCE_REVIEW_AND_P_FINAL.json，committed388_20261111/RECEIPT424.json。current_source已核a81，own_jobs空，ACTIVE不存在。

---

'''
path=B/'sol/TO_OPUS.md';old=path.read_text('utf-8-sig');assert '## 核收回执：#424源审' not in old
header,rest=old.split('\n',1);tmp=path.with_suffix('.tmp');tmp.write_text(header+'\n\n'+mail+rest.lstrip('\n'),'utf-8');tmp.replace(path)
text='''

### 7.358 #424墙门闭合；最终源同源开关有限P已结项，默认关、游戏暂停（11-14）

a81a2597父844，Astra xhigh窄源核收D423-WALL：inst.dec.x+观测face核wall_rule，缺/非有限或规则改写则整拍unknown，两个站位保留、不用inst.x0。新反例/正常open/缺dec及真实夹具已核，32例/28变异为作者报告，未重跑963或矩阵。最终P6两臂240源LF指纹匹配，42145出口/plan实际R→42147核；与P5键和模型轨迹等价。

Sol用固定executor、原entry_v3，同一源码开关0/1、seed428636/SYN42144，正式42145–42221各77拍。夹具仅录制实发键到42143，42144清空，计时中forcing0、无规则门控/强选；728运行源、输入绑定、240manifest、实际High/P0–15/不节流、逐拍wire和双辅助进程真实退出/四次finalize核实。准备脚本收据目录漏定义只影响登记，补正尾部后继续，未重复冻结或测量，无运行失败。

开启整拍p50/p99=14.4515/19.664996ms，max20.0928、6/77超16.67；77拍全planner，50拍出口生效，目标1577066不变，无模型伤/命中。关闭12.6752/22.051372，max26.4197、7/77超帧；54planner+23chain，42188模型一刀、42201落锤接触。67拍wire/属主差，不当helper纯开销；模型接触明细不算HP次数。开启42195–42200缺scene记unknown保留，正式异步窗比作者记录多42200。此窗少一刀换无模型锤接触作有限功能证据，不能推胜率/净收益；计时有效，不签性能预算/全域调度。

ROOT_P_AUDIT、SOURCE_REVIEW_AND_P_FINAL、RECEIPT424登记，423原失败保留由424闭合。seq364写信/单次信号/01:29:48监听实收/实际修复交付/源审/有限P分级核。current_source已核a81、own_jobs空、ACTIVE无。仅写信息核收，不另派任务或唤醒。生产开关仍默认0，用户游戏暂停；未增加实机/新50或续停止批，不改AA/原录像。ep39/ep22a限制、路线穿落点及固定钩/链/waypoint/entry后续项保持。
'''
path=ROOT/'docs/plans/forum_clapper_plan.md';old=path.read_text('utf-8-sig');assert '### 7.358 ' not in old;path.write_text(old+text,'utf-8')
put(A/'CLOSURE.json',dict(at=now(),source=h,source_accepted=True,finite_P_complete=True,actual_cleanup=True,default_switch=False,live_released=False,information_reply_written=True,new_wake_sent=False,next_owner='No running author task; user game pause remains',input_files=len(read(A/'REPLAY_INPUT_BINDING.json')['files'])))
print(json.dumps(dict(source=h,source_and_finite_P_closed=True,actual_cleanup=True,default_switch=False,live_released=False,info_reply_written=True,input_files=len(read(A/'REPLAY_INPUT_BINDING.json')['files'])),ensure_ascii=False))
