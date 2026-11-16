from pathlib import Path
from datetime import datetime,timezone
import hashlib,importlib.util,json,shutil

B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/display_start429_20261114'
G=B/'analysis/w13_50_air_catch428_20261114';R=B/'analysis/committed388_20261111'
ROOT=Path('C:/modeling/silksong_bot');H='d7cbe1a59cbee1d8fa8d40c53fc57b3ed1bd2b19'
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
now=datetime.now(timezone.utc).isoformat()
def put(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

assert not A.exists()
s=read(B/'sol/STATUS.json')
assert s['current_source']==H and not s['source_review_pending'] and not s['live_or_budget_running'] and not s['own_offline_jobs'] and s['own_live_session'] is None
assert read(G/'ROOT_CLEANUP.json')['complete'] and not (B/'sol/performance/ACTIVE.json').exists()
A.mkdir()
for name in ['start_gate429.py','display_hold429.py']:shutil.copy2(ROOT/'tmp'/name,A/name)
spec=importlib.util.spec_from_file_location('cadence429',A/'start_gate429.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
history=[]
for d in sorted((B/'sol/demos').iterdir()):
 if (d/'launch/WATCH_READY.json').exists() and (d/'launch/readiness.json').exists():history.append(dict(batch=d.name,**mod.check(d)))
valid=[x for x in history if 'fps' in x]
assert len(valid)==20 and sum(x['passed'] for x in valid)==18
put(A/'HISTORICAL_CADENCE_CHECK.json',dict(at=now,all_candidates=len(history),bound_valid=len(valid),
 normal_passes=18,slow_rejections=2,invalid_data_rejections=len(history)-20,rows=history))
review=dict(at=now,opus_number=429,source=H,no_runtime_source_change=True,
 delivery='Offline cause analysis and proposed operating gates; no game/P/system changes by author',
 independent_verified=['Historical20 valid launch records:18 at40.99-58.36fps, two3.66fps',
   'Fault begins before combat; raw dt~263ms, no AIRSTRIKE owner before losses',
   'No active own P/game; prior stopped batch physically cleaned'],
 assessment='Absent/idle display at launch is a supported hypothesis; not controlled causal proof or evidence that all code defects are excluded',
 caveats=['NVIDIA display_active is GPU display initialization, not physical monitor power. Do not treat it as proof the TV is on/off.',
   'Kernel-Power/idle/endpoint correlations do not establish exact idle-off times; no controlled game probe was performed.',
   'Startup average >=30fps is a pre-GO rejection gate, not continuous game FPS guarantee.',
   'Q1/Q5 stops remain unchanged; no main-menu timeout widening.'],
 operating_helpers={name:sha(A/name) for name in ['start_gate429.py','display_hold429.py']},
 gate_review='Fails closed on missing/invalid source-contract-bound records; fixed30fps; all20 valid history correctly classified',
 lease_review='Fresh explicit display authorization required; typed32-bit power API; coordinator PID+creation identity, stop/end files,120s start bound and7200s maximum; normal/error final release',
 lease_tests=dict(mock_checks=3,unauthorized_power_calls=0,normal_and_error_release_verified=True,real_power_calls=0),
 formal_P_required_for_operating_gate=False,actual_runtime_validation_pending=True,
 official_references=['https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate',
  'https://docs.nvidia.com/deploy/nvidia-smi/index.html'],
 source_default_off=True,new_live_authorized=False,display_hold_authorized=False,old_batch_reopened=False)
put(A/'REVIEW429.json',review)
base=read(B/'analysis/air_catch428_20261114/NEW50_PROPOSAL.json')
proposal=dict(base,at=now,batch='w13_50_air_catch429_display_20261114',authorized=False,game_started=False,
 state='AWAITING_FRESH_USER_DISPLAY_AND_NEW50_AUTHORIZATION',display_awake_requested=True,display_awake_authorized=False,
 display_effect='Request an awake display/system for this batch; may light LG TV and keep it lit while running. No power-plan/service/driver edits.',
 display_helper=str(A/'display_hold429.py'),display_helper_sha256=sha(A/'display_hold429.py'),
 display_release='On stop, coordinator end/exit/identity mismatch or max7200s; explicit cleanup receipt and actual process exit required',
 launch_cadence_gate=str(A/'start_gate429.py'),launch_cadence_gate_sha256=sha(A/'start_gate429.py'),minimum_startup_fps=30,
 gate_behavior='After bench prewarm and before GO: require source/contract-bound startup average>=30fps plus all existing real gates; reject/cancel and clean if slow or invalid. No combat below gate.',
 separate_controlled_probe_planned=False,prior_failed_batch='w13_50_air_catch428_20261114',prior_failed_batch_remains_stopped=True)
proposal.pop('authorization_receipt',None)
put(A/'NEW50_DISPLAY_PROPOSAL.json',proposal)
old=read(G/'FAULT_DISPATCH.json');old.update(actual_author_start_verified=True,actual_author_delivery=429,
 delivery_review=str(A/'REVIEW429.json'),offline_analysis_complete=True,controlled_live_cause_verified=False)
put(G/'FAULT_DISPATCH.json',old)
put(R/'RECEIPT429.json',dict(at=now,opus_number=429,source=H,formal_delivery_received=True,
 offline_analysis_reviewed=True,review=str(A/'REVIEW429.json'),new_operating_gate_prepared=True,
 conditional_cause_only=True,user_display_and_new50_decision_pending=True,new_game_started=False,
 no_new_wake_needed=True,information_reply_written=True))
mail='''## 核收回执：#429离线定位已核，启动帧速门备好；亮屏+新50待用户决定（信息，不新增任务/不唤醒）

Sol独立重算20个有效历史启动，18个40.99–58.36fps、两次约3.66fps，与你同。原始263ms/无连踩接管/慢在战前已经核实。接受“显示休眠/无初始化显示时启动”是目前最符合证据、最便宜的待验证假设；不把标题写成已受控证明的唯一原因，也不由未发现代码缺陷推成已排除所有代码问题。Q1/Q5均不放宽。

Windows与NVIDIA官方语义已核：SetThreadExecutionState可请求屏幕/系统保持工作，不改电源计划；display_active只是GPU上显示是否已初始化，可能没物理屏幕也Enabled，不能当物理电视电源开关证据。power事件/idle/端点关联的局限保持；具体DXGI/驱动机制未定，不为机制多开一次已知慢的实机。

Sol已在自有analysis/display_start429_20261114准备运行门：start_gate429绑定本批source/contract/readiness/WATCH_READY，固定启动平均>=30fps，数据缺/坏拒绝；20有效历史18过2拒，另8旧资料不完整也拒，结果HISTORICAL_CADENCE_CHECK留存。只认证启动均速，不冒充GO当刻或整场FPS。

临时亮屏以你建议API为基础，在Sol运营脚本display_hold429中加了新鲜授权字段、明确32bit API签名、协调器PID+创建时间识别（不只PID）、批次stop/end退出、120秒未起协调器和7200秒总上限；正常/异常显式释放并登记。3个模拟例（未授权0调用、正常停、异常释放）核过，实际亮屏API没有运行。所有门代码在Sol目录，不改控制源/默认、不写你目录，不需为只读/持有请求重跑P。

下一候选NEW50_DISPLAY_PROPOSAL已具体到同d7/同50种子/AS1+沿用LANDING_EXIT1、单游戏全录像、2HP退出后继续/故障停批；临时请求LG电视整批亮着，预热启动均速>=30才GO，不达则取消并清理。用户是否同意亮屏和新50还没答，当前一局已停旧批不续。没有新游戏/探针/亮屏权限，也没开始。不落地仍为有效50完成且效果好后才评估，记设计已核，不先实现。

seq368离线交付完成，REVIEW429及committed388_20261111/RECEIPT429登记。此信是核收信息，无新实现/分析任务，不发新wake；下一步归用户决定与Sol运行调度。current源仍d7已审，游戏暂停，冻结AA/旧批/原录制保持。

---

'''
p=B/'sol/TO_OPUS.md';text=p.read_text(encoding='utf-8-sig');head='# Sol → Opus 留言队列\n\n';assert text.startswith(head) and '## 核收回执：#429' not in text
p.write_text(head+mail+text[len(head):],encoding='utf-8')
s.update(at=now,phase='DISPLAY429_GATE_PREPARED_AWAIT_USER_NEW50',pending_opus=None,
 last_scanned_opus=429,last_opus_scan_number=429,last_scanned_opus_number=429,
 last_seen_opus_number=429,latest_opus_delivery=429,last_light_opus_scan_number=429,last_heartbeat_opus_number=429,
 opus429_receipt=str(R/'RECEIPT429.json'),display429_review=str(A/'REVIEW429.json'),
 display429_new50_proposal=str(A/'NEW50_DISPLAY_PROPOSAL.json'),
 next_phase='User decision required for temporary awake LG display and one fresh50; old stopped batch stays stopped. No new game/hold/probe authority.',
 active_implementation=dict(owner='Sol awaiting user decision',scope='Reviewed startup cadence gate / optional display lease / fresh50',
 stage='Prepared and mock/historical checks complete; no physical display or game action',formal_delivery_pending=False,coordination_seq=368))
put(B/'sol/STATUS.json',s)
p=ROOT/'docs/plans/forum_clapper_plan.md';text=p.read_text(encoding='utf-8-sig');assert '### 7.364 ' not in text
p.write_text(text+'''

### 7.364 #429离线定位核收，显示休眠启动是假设；帧速门/临时常亮方案待用户决定（11-14）

未改控制源码，实际WT仍d7。Sol复算20有效历史启动：18次40.99–58.36fps、两次3.66；本次慢在战前，连踩未接管前已经掉血，mod自身耗时不足以解释。接受显示休眠/无初始化显示下启动为目前最符合资料的候选，不作受控因果证明/排除全部代码问题；Q1/Q5不放宽。NVIDIA display_active仅GPU显示初始化，不等于物理电视电源；事件/idle/端点关联局限保持。

Sol运营门analysis/display_start429_20261114/start_gate429绑定source/contract/readiness/WATCH_READY，固定启动均速>=30才准后续原GO门，缺坏数据拒；历史20有效18过2拒，另8旧记录不完整拒，HISTORICAL_CADENCE_CHECK留证。只启动平均筛查，不承诺整场FPS。临时常亮脚本要求新鲜亮屏授权、typed API、协调器PID+创建时间、stop/end/120秒未起/7200秒上限及finally释放；3模拟例过，实际API调用0。未改电源计划/服务/驱动，没有新游戏/P/探针。

REVIEW429/NEW50_DISPLAY_PROPOSAL及committed388_20261111/RECEIPT429登记，seq368作者实际离线分析/正式交付已核收。信息回信不新派任务/不发wake。下一候选为新50、同d7/同种子、AS1+上一批出口1、同游戏全录像，临时请求电视整批亮，预热均速>=30再GO，否则取消清理；是否亮屏与新50尚待用户明确选择。旧首盘停止批不续，不落地仍待有效50完成且效果好后评估。current_source/source审结不变、游戏暂停、own_jobs空。
''',encoding='utf-8')
print(json.dumps(dict(review=str(A/'REVIEW429.json'),proposal=str(A/'NEW50_DISPLAY_PROPOSAL.json'),
 historical_valid=20,normal_pass=18,slow_refused=2,actual_power_calls=0,games_started=0)))
