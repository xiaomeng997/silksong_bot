"""Close current179 technical slice honestly; retain live/route/latency limits; dispatch authorized180 after cleanup."""
from pathlib import Path
import datetime,hashlib,json,os,re,subprocess,sys
import psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/task179_body321_20261106';Q=B/'sol/work_packages/task180';M=Path('C:/modeling/silksong_bot');D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');V=Path('C:/Users/Meng/.codex/worktrees/forum-tv-prep/silksong_bot');S='ecc6332b0b977dacd86dfd3d4d3f57d71e0cdd61';G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
sys.path.insert(0,str(D/'brain'));sys.dont_write_bytecode=True
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(n,d):
 p=A/n;assert not p.exists(),str(p);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def atom(p,d):
 t=p.with_name(p.name+'.close321.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(t,p)
def git(root,*args):return subprocess.check_output([G,'-C',str(root),*args],encoding='utf-8').strip()
def alive(j):
 try:return abs(psutil.Process(j['pid']).create_time()-j['created'])<.01
 except psutil.NoSuchProcess:return False
me=psutil.Process();me.cpu_affinity(list(range(24,32)));me.nice(psutil.IDLE_PRIORITY_CLASS)
st=read(B/'sol/STATUS.json');job=read(A/'ROOT_P_AUDIT_JOB.json');assert st['own_offline_jobs']==[job] and not st['live_or_budget_running'] and not alive(job)
assert read(A/'ROOT_P_AUDIT_JOB_END.json')['error'] is None
audit=read(A/'ROOT_P_AUDIT.json');assert audit['integrity_pass'] and audit['ticks']==50 and not audit['new_game_gate']
assert st['active_work_package']==179 and not st['queued_work_package_start_authorized']
assert read(B/'sol/OPUS_WAKE.json')['seq']==247 and not (B/'sol/performance/ACTIVE.json').exists()
summary=(B/'opus/TO_SOL.md').read_text(encoding='utf-8-sig').split('## 用法',1)[0];assert int(re.search(r'\*\*最新编号\*\*：#(\d+)',summary).group(1))==321
assert git(D,'rev-parse','HEAD')==st['freeze_execution_head'] and not git(D,'diff','--name-only')
packet=read(A/'SOURCE_PACKET.json');assert all(sha(D/n)==h for n,h in packet['raw_runtime_files_sha256'].items())
from ssbot.tools.launcher import read_reg_file,prefs_diff
golden=Path('C:/ssbot/sandbox/prefs/golden.reg');demo=Path('C:/ssbot/sandbox/DEMO_SOON');reg=read(Path('C:/ssbot/sandbox/prefs/instances.json'))
assert reg['instances']==[] and reg['restore_pending'] is False
assert not [p.pid for p in psutil.process_iter(['name']) if 'silksong' in (p.info['name'] or '').lower()]
finals={n:read(A/n/'FINALIZED.json') for n in ['startup','p_NW']}
for n,f in finals.items():
 assert f['execution_ok'] and f['cleanup_verified'] and not alive(f)
 assert not any(alive(q) for q in f['fields'])
 env=f['environment'];assert env['games']==[] and env['prefs_diff']==[] and env['registry']['instances']==[] and env['registry']['restore_pending'] is False
 assert sha(golden)==env['golden_sha256'] and sha(demo)==env['old_demo_sha256'] and demo.stat().st_mtime_ns==env['old_demo_mtime_ns']
 assert prefs_diff(read_reg_file(A/n/'FINAL_PREFS.reg'),read_reg_file(golden))==[]
assert all(v['engineering_equal'] and v['signature_unchanged'] and v['trace']['complete'] for v in audit['contexts'].values())
peaks={}
for name in ['N','W']:
 d=read(A/(name+'_FULL_DIAGNOSTICS.json'));t=d['peak_tick'];di=d['footer']['diagnostics'];assert di['complete'] and not di['events_overwritten'] and not di['callback_errors'] and not di['injection_executed']
 starts={};gcs=[]
 for e in di['events']:
  key=(e['kind'],e.get('generation'),e.get('tid'))
  if e['kind']=='gc' and e['status']=='start':starts[key]=e
  elif e['kind']=='gc' and e['status']=='stop' and key in starts:
   begin=starts.pop(key)
   if e.get('f')==d['peak_frame']:gcs.append(dict(generation=e['generation'],wall_ms=(e['wall_ns']-begin['wall_ns'])/1e6,start=begin['wall_ns'],stop=e['wall_ns'],collected=e['collected']))
 peaks[name]=dict(frame=d['peak_frame'],complete_tick_ms=t['total_tick_ms'],phases={x['name']:x['wall_ns']/1e6 for x in t['diagnostic_phases']},overlapping_gc=gcs,interpretation='Recorded GC overlap; peak retained, no subtraction or claim of sole causation')
put('PHASE_SUMMARY.json',dict(at=now(),source=S,peaks=peaks,scope='Full measured peaks, no selective rerun, no predicted future p99'))
put('ROOT_P_AUDIT_CLEANUP.json',dict(at=now(),own_audit=job,actual_audit_exit=True,finalized=finals,source_files_unchanged=714,registry=reg,golden_sha256=sha(golden),old_demo_sha256=sha(demo),old_demo_mtime_ns=demo.stat().st_mtime_ns,prefs_rechecked=True,no_games=True,executor_ACTIVE_absent=True))
close=dict(at=now(),task=179,current_fix='321 known standing body / two-facing support',source=S,source_accepted=True,offline_checks_accepted=True,formal_P_integrity_accepted=True,formal_ticks=50,cleanup_verified=True,current_technical_slice_closed=True,whole_task_live_accepted=False,full_scheduling_gate_pass=False,new_game_gate=False,limits=['Whole W3 approach rejected; only already-over-gap landing/side-slash retained. No extra approach recipe added.','Original178 pose continuation/179 real walking-vault, repeated downslash, natural NPC response and global hitless behavior remain unverified.','N69.188ms peak retained with recorded49.2243ms generation2GC overlap. Serial replay remains conditional; skipping a frame does not prove GC work disappears.','Default BODY/AIR/FACE_HOOK/BOUNCE_TABLE configuration not enabled.'],source_review=str(A/'SOURCE_REVIEW.json'),P_audit=str(A/'ROOT_P_AUDIT.json'),cleanup=str(A/'ROOT_P_AUDIT_CLEANUP.json'))
put('CURRENT_FIX_CLOSEOUT.json',close)
# Real cleanup is now independently verified. Release the freeze before any new documentation commit or180 dispatch.
st.update(at=now(),phase='179_CURRENT_FIX_TECHNICAL_CLOSEOUT',own_offline_jobs=[],source_frozen_for_P=False,source_freeze_released_at=now(),opus321_P_receipt=str(A/'ROOT_P_AUDIT.json'),opus321_cleanup=str(A/'ROOT_P_AUDIT_CLEANUP.json'),current_fix_closeout=str(A/'CURRENT_FIX_CLOSEOUT.json'))
atom(B/'sol/STATUS.json',st)
doc=M/'docs/plans/forum_clapper_l2_tactics.md';text=doc.read_text(encoding='utf-8-sig')
text=text.replace('源审及有限离线证据通过，受影响性能待核；整体返回实机仍未验收。','源审及有限离线证据通过，N23/W27性能记录和实际清理已核；有慢帧，整体返回实机仍未验收。')
text=text.replace('旧源码0b148177完成四窗219拍P及真实清理；#321两源变化正在补N23/W27共50拍，尚未启动。','旧源码0b148177完成四窗219拍P；#321另完成N23/W27共50拍，运行身份、完整trace、发键及实际清理已核；N有69.188ms慢帧。')
text=text.replace('## 已授权的有限整理（Task180，排队）','## 已授权的有限整理（Task180，已派发）')
old='用户要求先收尾当前 Task179，再由 Opus 做有限整理；当前尚未启动 Task180。唯一任务说明在 `C:/ssbot/data/m2_play/clapper_plan/sol/work_packages/task180/TASK.json`，基准版本由 Sol 在179本次在途修复及必要审核、性能核验和清理收尾后绑定，不提前拿未交付版本开工。'
new='用户要求先收尾当前 Task179，再由 Opus 做有限整理。179本次身体支持域修复的源码、有限离线证据、50拍性能记录及实际清理已核，现已派发Task180；基准runtime为`ecc6332b`。唯一任务说明在 `C:/ssbot/data/m2_play/clapper_plan/sol/work_packages/task180/TASK.json`。派发不等于整理已完成，178/179原实机未覆盖、W3整局接近缺口及慢帧风险继续保留。'
assert old in text;text=text.replace(old,new);doc.write_text(text,encoding='utf-8')
plan=M/'docs/plans/forum_clapper_plan.md';t=plan.read_text(encoding='utf-8-sig');assert '进度7.192' not in t
top='2026-10-27 起草（历史审阅与阶段规格保留）。**当前进度（11-06，7.192）：179本次321身体支持域修复已完成有限源审/离线及N23/W27共50拍性能记录核验，并真实全清理；W3整局接近及原实机目标未验收，N保留69.188ms二代GC重叠慢帧，未签全时序。按用户顺序现派发Task180有限L2整理，基准runtime ecc6332b；只归拢条件/分数/完整输出与公共竞争，不只套壳、不加打法。默认开关及无新实机许可保持。**'
t,c=re.subn(r'2026-10-27 起草.*?(?=\n\n)',top,t,count=1,flags=re.S);assert c==1
t+='''

#### 321两窗50拍P与全清理完成；179当前修复技术收尾，按用户顺序派发180有限整理（11-06，进度7.192）

Root沿原固定executor_v1与原timing_entry318（SHA均未变），源审/输入hash匹配后先做实际54892最小启动0测量tick并核其场worker退出、配置/签名预热及真实环境恢复。Opus摘要明确按seq247暂停计算/改源，STATUS先原子true请求独占，冻结runtime ecc6332b和刀口docs HEAD837a62f4；只有匹配startup FINALIZED后才由真实52264执行正式P，N23/W27共50完整_act/trace tick。两场worker20792/54648都真实退出。原资源门两次无阻挡，无自改资源范围/核心进程操作、无游戏、无重测219/A或选较快数字。

analysis/task179_body321_20261106/ROOT_P_AUDIT、SERIAL_SCHEDULE、PHASE_SUMMARY和全部原始trace保存。N2813..2835完整tick中位19.8755ms、峰69.1880ms；W2794..2820中位17.9372ms、峰22.0506ms。全部最终frame/target/mask/owner与当前321对应工程工件逐位同，trace完整/overflow0，外来模块/新签名/运行错误0；实际P0–15/High/Numba4/GetProcessInformation EcoQoS关闭、真实send clock核过。场worker仍E24–31/Idle。配置原始false仅保留BLOCK/ORDER/SCHEDULE三历史账本项，不冒充下一实机完整manifest；两窗是同控制profile同实际父进程的有限样本，不是BODY默认开或全局速度证书。

N峰在2827：observe49.5129ms内记录同帧二代GC49.2243ms，tactics7.2917ms/planner10.8207ms；W峰2805记录一代GC4.5927ms。保留全部峰与GC，未相减、未关GC/新做freeze/重复测量，也不把整个tactics阶段冒充纯L2选择器耗时。仅据诊断确认时间重叠，不推成形状联合独占成本或未来上界。旧receive加新完整cost、全部等待/latestSTATE/双锚与原reserve的历史1.292ms wake算术：N10晚/跳2816、2821、2827、2832，W11晚/跳2801、2808、2815；不是重决策后闭环，GC可能随分配迁移，不因算术跳过2827就证明GC消失。full_scheduling_gate_pass仍false，不据此开局或再加时序分支。

固定执行器startup/P FINALIZED均成功且全清理，Root独核实际父/场/自身audit进程退出、无ACTIVE/子残留/游戏，复核两份FINAL_PREFS与golden无差、golden/旧DEMO hash/mtime原样、当前registry instances空且restore_pendingfalse，714源再核全同；只有全部成立后释放runtime/docs冻结。CURRENT_FIX_CLOSEOUT只关闭179本次seq245/247已约定支持域修复及其必要验证，whole179/live=false。W3全程接近没保住、178姿态接续/179真实走路怪翻越/连续下劈等未覆盖与旧失败仍保留，未把保守拒绝或条件正例改称完整行为已通过。

按用户先收当前再整理的明确授权，Sol现绑定180基准runtime ecc6332b与本次SOURCE_PACKET，更新原TASK.json为已派发/可开始，Opus仍唯一实现owner，Sol普通独审及正式P/实机调度。seq248一次交本次结果/限制及180启动：把每条完整战术的适用条件、分数、完整目标/站位/攻击和相关L2输出真正归同一处，公共择优/应用不按winner名字另写第二份权威规则；事实共享，观察/评估/提交分清，事件阶段/互斥/保持/退出保留。现有评分/时钟/切换成本/动作链/几何/默认开关不顺改，不新增成团第二打法或接近策略；固定输入回归只对应已有路径，不声称全状态不变、不以100盘无伤为前置。下一实机仍未授权，旧观察/AA/STOP不重开。
'''
plan.write_text(t,encoding='utf-8');heads={}
for root in (M,D,V):
 for rel in ('docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md'):
  if root!=M:(root/rel).write_bytes((M/rel).read_bytes())
 git(root,'diff','--check','--','docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md');git(root,'add','--','docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md');git(root,'commit','-m','docs: close bounded body validation and dispatch L2 organization','--','docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md');heads[str(root)]=git(root,'rev-parse','HEAD')
spec=read(Q/'TASK.json');assert spec['state']=='QUEUED_AFTER_179' and not spec['authorized_to_start'] and spec['baseline_source'] is None
spec.update(at=now(),state='DISPATCHED_TO_OPUS',authorized_to_start=True,baseline_source=S,baseline_head=heads[str(D)],baseline_source_packet=str(A/'SOURCE_PACKET.json'),prior_fix_closeout=str(A/'CURRENT_FIX_CLOSEOUT.json'),baseline_rule='179 current known-body support slice source/offline/P integrity and real cleanup closed. Original live/capability/latency limits retained; no claim of whole179 live success.')
atom(Q/'TASK.json',spec)
dispatch=dict(at=now(),task=180,implementation_owner='Opus',review_owner='Sol',source=S,baseline_head=heads[str(D)],source_packet=str(A/'SOURCE_PACKET.json'),spec=str(Q/'TASK.json'),prior_fix_closeout=str(A/'CURRENT_FIX_CLOSEOUT.json'),new_game_authorization=False,seq=248)
atom(Q/'DISPATCH.json',dispatch)
progress=B/'sol/work_packages/task179/PROGRESS.json';prior=read(progress);prior.update(at=now(),current_fix_source=S,current_fix_technical_closeout=str(A/'CURRENT_FIX_CLOSEOUT.json'),current_fix_technical_closed=True,whole_live_accepted=False,successor_package=180,successor_scope='limited L2 organization; original live/route/latency limitations retained');atom(progress,prior)
put('POST_P_PLAN_SYNC.json',dict(at=now(),heads=heads,plan_progress='7.192',plan_sha256=sha(plan),document_sha256=sha(doc),runtime_source=S,source_files_unchanged=714))
mail='''## seq248 / 179当前321修复技术收尾并全清理；按用户顺序启动Task180有限L2整理

50拍P已核且真实清理完毕，runtime ecc6332b与docs冻结现释放。R=analysis/task179_body321_20261106，见ROOT_P_AUDIT/PHASE_SUMMARY/ROOT_P_AUDIT_CLEANUP/CURRENT_FIX_CLOSEOUT。固定executor/entry原字节未改，实际54892 startup0tick后真实52264跑N23/W27，P0–15/High/Numba4/EcoQoS关闭、真send clock、无foreign/新签名/错误、完整trace，全部最终tuple与当前321工程工件同。父/场20792、54648/审计已退出，golden/Prefs/旧DEMO/registry与无ACTIVE独核后才解除冻结。没开游戏/重跑219或A。

完整tick中位/峰N19.8755/69.1880ms，W17.9372/22.0506ms；N2827 observe49.5129ms内有二代GC49.2243ms，W2805有一代GC4.5927ms。所有峰/GC保留，无重复测量取快值/无关GC。整个tactics阶段不是纯L2耗时。历史receive串行算术仍有晚包/跳拍、full_scheduling_gate_pass=false；固定帧成本不证明跳过GC帧能免除GC，不据此开局或加时序分支。只有3旧账本manifest unresolved，亦不当live全配置。

当前只关闭321已约定支持域修复与必要源/离线/P/清理范围，不把whole179/live签通过。W3从头接近未保住、只有到缝上方后落缝/侧劈保留，178姿态/179真实翻走路怪/连续下劈等未覆盖继续保留；不为这些在当前整理包加新打法。

现在按用户已授权顺序启动Task180（不再排队），唯一完整规格sol/work_packages/task180/TASK.json已绑定runtime ecc6332b/当前docs基准及本次SOURCE_PACKET，DISPATCH.json索引。你唯一源码owner，直接在刀口开发树提交实现；先读主计划7.192和L2文档对应段。条件/适用度、分数与完整L2输出要真正归各完整战术，公共选择/应用不按winner名字另有第二份权威行为规则；不能只搬helper/套类。事件阶段/互斥/保持/退出明确、观察/评估/赢家提交分清、场景事实共享；保留旧评分/同分保持/切换成本/触发周期与动作所有权。不要硬凑13类或造全游戏框架，文件边界由你定。

只整理，不新增成团第二打法、接近策略，不改刀口链/几何/输入/资源门/默认开关，不顺带优化GC。复用现有场景核目标/站位/EntryAttack/no_hit/相关L2字段与必要生产最终键，首次差异说明；只称已有路径回归证据，不保证全状态等价、不等100盘无伤才整理。一次交完整源码、映射、相关检查/生产正例和受影响性能入口，避免微ACK反复；正式P/实机仍由Sol安排，当前没有新实机许可。旧raw/AA/STOP与用户未跟踪文件不动。

'''
mp=B/'sol/TO_OPUS.md';mp.write_text(mail+mp.read_text(encoding='utf-8-sig'),encoding='utf-8')
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs')
st.update(at=now(),phase='TASK180_DISPATCHED_AFTER179_CURRENT_FIX_CLOSEOUT',active_work_package=180,implementation_owner='Opus',code_write_owner='Opus',code_handoff=str(Q/'DISPATCH.json'),current_plan='7.192',plan_progress='7.192',current_head=heads[str(D)],current_source=S,candidate_source=S,source_review_pending=False,source_frozen_for_P=False,queued_work_package=None,queued_work_package_start_authorized=True,queued_work_package_state='DISPATCHED_TO_OPUS',task180_spec=str(Q/'TASK.json'),active_blocker=None,pending_evidence_review=None,next_phase='Opus implements limited L2 organization under180; current body fix closed only at source/offline/P integrity/cleanup scope; live/route/latency limits remain.',next_watch_ready=False,next_watch_user_authorized=False,current_fix_closeout=str(A/'CURRENT_FIX_CLOSEOUT.json'))
atom(B/'sol/STATUS.json',st);atom(B/'sol/OPUS_WAKE.json',dict(seq=248,task=180,at=now(),note='179 current321 technical slice and50 P/real cleanup closed, limits retained; freeze released. Begin user-authorized180 limited L2 organization. No new game.'))
put('HANDOFF248.json',dict(dispatch=dispatch,heads=heads,source=S,source_only_cleanup_pass=True,whole179_live_accepted=False,new_games=0,metadata_job=dict(pid=me.pid,created=me.create_time(),cpus=me.cpu_affinity(),priority=me.nice())))
print(json.dumps(dict(plan='7.192',active_task=180,seq=248,source=S,measured_ticks=50,whole179_live=False,heads=heads)))
