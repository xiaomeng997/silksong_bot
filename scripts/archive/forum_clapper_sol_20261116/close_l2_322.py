"""Close only the authorized limited organization after actual P cleanup."""
from pathlib import Path
import datetime,hashlib,json,os,re,subprocess,sys,psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/task180_l2_322_20261106';M=Path('C:/modeling/silksong_bot');D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');V=Path('C:/Users/Meng/.codex/worktrees/forum-tv-prep/silksong_bot');S='9f6da15674da8c396d729a680f6868d47d9e233f';G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
sys.path.insert(0,str(D/'brain'));sys.dont_write_bytecode=True
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def rows(p):return [json.loads(x) for x in p.read_text(encoding='utf-8-sig').splitlines() if x]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(n,d):
 p=A/n;assert not p.exists(),p;p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def atom(p,d):
 q=p.with_name(p.name+'.close322.tmp');q.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(q,p)
def git(r,*a):return subprocess.check_output([G,'-C',str(r),*a],encoding='utf-8').strip()
def alive(j):
 try:return abs(psutil.Process(j['pid']).create_time()-j['created'])<.01
 except psutil.NoSuchProcess:return False
me=psutil.Process();me.cpu_affinity(list(range(24,32)));me.nice(psutil.IDLE_PRIORITY_CLASS)
st=read(B/'sol/STATUS.json');job=read(A/'ROOT_P_AUDIT_JOB.json');assert st['own_offline_jobs']==[job] and not st['live_or_budget_running'] and not alive(job)
assert read(A/'ROOT_P_AUDIT_JOB_END.json')['error'] is None
audit=read(A/'ROOT_P_AUDIT.json');assert audit['integrity_pass'] and audit['ticks']==23 and not audit['new_game_gate']
assert st['active_work_package']==180 and st['source_frozen_for_P'] and not (B/'sol/performance/ACTIVE.json').exists()
summary=(B/'opus/TO_SOL.md').read_text(encoding='utf-8-sig').split('## 用法',1)[0];assert int(re.search(r'\*\*最新编号\*\*：#(\d+)',summary).group(1))==322 and read(B/'sol/OPUS_WAKE.json')['seq']==249
assert git(D,'rev-parse','HEAD')==st['freeze_execution_head'] and not git(D,'diff','--name-only')
packet=read(A/'SOURCE_PACKET.json');assert all(sha(D/n)==h for n,h in packet['raw_runtime_files_sha256'].items())
from ssbot.tools.launcher import read_reg_file,prefs_diff,RegPrefsStore
golden=Path('C:/ssbot/sandbox/prefs/golden.reg');demo=Path('C:/ssbot/sandbox/DEMO_SOON');reg=read(Path('C:/ssbot/sandbox/prefs/instances.json'));assert reg['instances']==[] and reg['restore_pending'] is False
assert not [p.pid for p in psutil.process_iter(['name']) if 'silksong' in (p.info['name'] or '').lower()]
finals={n:read(A/n/'FINALIZED.json') for n in ['startup','p_N']}
for n,f in finals.items():
 assert f['execution_ok'] and f['cleanup_verified'] and not alive(f) and not any(alive(x) for x in f['fields'])
 env=f['environment'];assert env['games']==[] and env['prefs_diff']==[] and env['registry']['instances']==[] and env['registry']['restore_pending'] is False
 assert sha(golden)==env['golden_sha256'] and sha(demo)==env['old_demo_sha256'] and demo.stat().st_mtime_ns==env['old_demo_mtime_ns']
 assert prefs_diff(read_reg_file(A/n/'FINAL_PREFS.reg'),read_reg_file(golden))==[]
current=A/'ROOT_FINAL_PREFS.reg';assert not current.exists();RegPrefsStore().export(current);assert prefs_diff(read_reg_file(current),read_reg_file(golden))==[]
assert audit['contexts']['N']['engineering_equal'] and audit['contexts']['N']['signature_unchanged'] and audit['contexts']['N']['trace']['complete']
diag=read(A/'N_FULL_DIAGNOSTICS.json');assert diag['footer']['diagnostics']['complete'] and not diag['footer']['diagnostics']['events_overwritten'] and not diag['footer']['diagnostics']['callback_errors']
trace=rows(A/'p_N/N/measurement_trace.jsonl');oldtrace=rows(B/'analysis/task179_body321_20261106/p_NW/N/measurement_trace.jsonl')
def costs(tr):return {r['f']:(r['tick_end_ns']-r['tick_start_ns'])/1e6 for r in tr if r.get('kind')=='tick'}
newcost,oldcost=costs(trace),costs(oldtrace);assert set(newcost)==set(oldcost)
phase=dict(frame=diag['peak_frame'],complete_tick_ms=diag['peak_tick']['total_tick_ms'],phases={r['name']:r['wall_ns']/1e6 for r in diag['peak_tick']['diagnostic_phases']})
put('PHASE_SUMMARY.json',dict(at=now(),source=S,peak=phase,gc_events=diag['footer']['diagnostics']['events'],same_frame_costs=[dict(f=f,new_ms=newcost[f],old_ms=oldcost[f],difference_ms=newcost[f]-oldcost[f]) for f in sorted(newcost)],interpretation='Two separate finite executions. No attribution of changed peaks to L2, no claim GC fixed or future upper bound; entire tactics phase is not pure L2 cost.'))
put('ROOT_P_AUDIT_CLEANUP.json',dict(at=now(),audit_job=job,actual_audit_exit=True,finalized=finals,source_files_unchanged=len(packet['raw_runtime_files_sha256']),registry=reg,golden_sha256=sha(golden),old_demo_sha256=sha(demo),old_demo_mtime_ns=demo.stat().st_mtime_ns,prefs_rechecked=True,no_games=True,executor_ACTIVE_absent=True))
completion=dict(at=now(),task=180,state='COMPLETE_LIMITED_ORGANIZATION',source=S,baseline='ecc6332b0b977dacd86dfd3d4d3f57d71e0cdd61',source_accepted=True,finite_offline_accepted=True,formal_P_integrity_accepted=True,formal_ticks=23,cleanup_verified=True,new_game_gate=False,full_scheduling_gate_pass=False,scope='11 complete L2 tactic units /13 rule IDs; conditions/scores/output/events colocated, generic selection/application; no behavior extension',checks=16,artifact_calls=3670,limits=['Only covered paths compared, not universal behavioral equivalence','Preexisting178/179 route/live/serial timing gaps remain','N23 median19.4504ms and peak21.3278ms are finite samples; old69.1880ms GC peak retained; no claim of a GC fix','No new live authorization or next package; BODY/AIR/FACE_HOOK/BOUNCE_TABLE defaults unchanged'],P_audit=str(A/'ROOT_P_AUDIT.json'),source_review=str(A/'SOURCE_REVIEW.json'),cleanup=str(A/'ROOT_P_AUDIT_CLEANUP.json'))
put('COMPLETION.json',completion)
st.update(at=now(),phase='TASK180_LIMITED_ORGANIZATION_COMPLETE',own_offline_jobs=[],source_frozen_for_P=False,source_freeze_released_at=now(),opus322_P_receipt=str(A/'ROOT_P_AUDIT.json'),opus322_cleanup=str(A/'ROOT_P_AUDIT_CLEANUP.json'),task180_completion=str(A/'COMPLETION.json'));atom(B/'sol/STATUS.json',st)
doc=M/'docs/plans/forum_clapper_l2_tactics.md';t=doc.read_text(encoding='utf-8-sig');t=t.replace('## 有限整理（Task180，源码及有限回归已核，性能待核）','## 有限整理（Task180，已完成范围内核验）')
t=t.replace('现只准备与321同一N窗口的23拍完整tick性能，源与文档冻结到实际全清理。','已沿固定执行器完成与321同一N窗口23拍完整tick，配置/签名/trace及最终发送与321一致，实际执行器/场worker、Prefs/golden/旧DEMO/registry和自有审计全部核清后释放冻结。完整tick中位19.4504ms、峰21.3278ms；是两次独立有限样本，不证明GC已修或全时序门通过，旧69.1880ms峰继续保留。')
t=t.replace('当前没有新实机许可；178/179原未覆盖、W3接近与串行慢帧缺口继续单列。','Task180的有限整理至此核收；当前没有新实机许可，未另开下一包。178/179原未覆盖、W3接近与串行慢帧缺口继续单列。')
t=t.replace('详细进度和实验规格以[主计划](forum_clapper_plan.md)为准。','几何口径：怪的位置基准点只用于左右关系等判断；“两怪间可站空隙”指身体边缘之间的间隙，并需考虑英雄宽度及安全余量，不能用两个基准点的距离直接代替。\n\n详细进度和实验规格以[主计划](forum_clapper_plan.md)为准。')
doc.write_text(t,encoding='utf-8')
plan=M/'docs/plans/forum_clapper_plan.md';t=plan.read_text(encoding='utf-8-sig');assert '进度7.194' not in t
top='2026-10-27 起草（历史审阅与阶段规格保留）。**当前进度（11-06，7.194）：Task180有限L2整理已完成范围内核验：11完整战术归拢13规则的条件/分数/输出/事件，公共竞争应用无第二份赢家分支；16局部检查、8场景3670次既有对照、集中语义审及N23完整tick/真实全清理已核。N中位19.4504ms、峰21.3278ms，旧69.1880ms峰保留，不声称GC修复或全时序通过。源9f6da156冻结已释放，不开下一包/实机；原178/179路线与未覆盖、默认关保持。**'
t,c=re.subn(r'2026-10-27 起草.*?(?=\n\n)',top,t,count=1,flags=re.S);assert c==1
t+='''

#### Task180 N23完整tick与真实清理核完，有限整理收尾（11-06，进度7.194）

Opus摘要明确按seq249暂停计算/源码/docs后，Root复用原executor_v1和timing_entry318，先实际24764最小启动0测量tick、场59672退出并finalize，再由独立真实51920执行N2813..2835共23完整tick，场59920退出；源/docs始终冻结，不并跑其他计算，无游戏。原资源门无阻挡，P0–15/High/Numba4/EcoQoS关闭及真正send clock核实，foreign/新签名/运行错误0，trace完整/overflow0。所有最终frame/target/mask/owner与321同窗口逐位同，不重复旧50/219或八场策略重放。

完整tick中位19.4504ms、峰21.3278ms。旧321同窗中位19.8755ms、峰69.1880ms均保留；两次独立有限进程样本，不把差异当结构提速或GC修复，不删旧峰，不补跑挑快值。当前N仍普通规划，整个tactics阶段含其他支持建模，不冒称纯L2控制器时间。原receive+全部等待/latestSTATE/双锚/reserve与历史1.292ms wake有限串行算术仍有9晚/跳2817、2821、2828、2833；未重模拟跳包后的控制决策，不构成新实机时间线、未来概率保证或全串行门通过。

固定startup/P的FINALIZED成功后，Root E24–31/Idle只读审计实际41416退出再独核其身份、真实执行器/场及child退出；当前无游戏/ACTIVE，registry instances空且restore_pendingfalse，重新导出Prefs与golden无差，golden/旧DEMO的hash/mtime原样，716运行文件全同。ROOT_P_AUDIT_CLEANUP/PHASE_SUMMARY/COMPLETION保存于analysis/task180_l2_322_20261106，全部真实核完才原子清E登记并释放源/docs冻结。

Task180仅标有限结构整理完成，不把178/179旧路线、原姿态接续、走路怪翻越、持续下劈或实机无伤验收偷换成通过。条件/评分/输出已归拢且公共选择不再按名字拼第二份行为；原互斥/阶段/分数/几何/默认开关未扩。用户询问“两怪根部之间”的口径，L2文档补明：位置基准点只描述左右关系，可站空隙应取身体边缘再扣英雄宽度与余量，不把根坐标距离当可站间隙。seq250只通知本包完成及解除暂停，不开启新包/实机，不要求ACK唤醒。
'''
plan.write_text(t,encoding='utf-8');heads={}
for root in (M,D,V):
 for rel in ('docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md'):
  if root!=M:(root/rel).write_bytes((M/rel).read_bytes())
 git(root,'diff','--check','--','docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md');git(root,'add','--','docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md');git(root,'commit','-m','docs: close limited L2 organization and retain live gaps','--','docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md');heads[str(root)]=git(root,'rev-parse','HEAD')
assert all(sha(D/n)==h for n,h in packet['raw_runtime_files_sha256'].items())
q=B/'sol/work_packages/task180';spec=read(q/'TASK.json');assert spec['state']=='DISPATCHED_TO_OPUS';spec.update(at=now(),state='COMPLETE_LIMITED_ORGANIZATION',completion=str(A/'COMPLETION.json'),accepted_source=S);atom(q/'TASK.json',spec);atom(q/'COMPLETION.json',completion)
mail='''## seq250 / Task180有限整理核收完成，N23与真实全清理已核；冻结解除，不开新包

R=analysis/task180_l2_322_20261106，SOURCE_REVIEW/ASTRA322_REVIEW/ROOT_P_AUDIT/ROOT_P_AUDIT_CLEANUP/COMPLETION已保存。11完整单元/13规则的条件/分数/输出/事件真正归拢，公共选择应用无第二份winner行为权威；16局部检查、8场景3670次完整旧输出/记忆对照及相关生产发键同，集中关键审无新增P0–P2。只完成本有限整理，不签所有状态/旧行为实机。

沿固定原字节executor/entry，24764 startup0tick后51920测N23，真实场59672/59920及自身审计41416全部退出；配置P0–15/High/Numba4/EcoQoS关闭/sendclock、完整trace、无foreign/新签名/错误核过，最终tuple与321逐位同。完整tick中位19.4504/峰21.3278ms，旧69.1880ms峰保留；不同独立样本不当结构提速/GC修复，串行算术仍9晚及跳拍，不签全时序/新game。

Root再核当前Prefs/golden/旧DEMO hash和mtime/registry空且restore_pendingfalse、无游戏/ACTIVE及716源同后，已解除runtime/docs冻结；计划7.194与L2文档三树同步。TASK180已标有限整理完成。没有下一包任务或新实机授权，178/179原缺口及默认开关保持；无需发ACK编号或再唤醒。请仅更新摘要为本包完成、等新任务，避免确认循环。

'''
mp=B/'sol/TO_OPUS.md';mp.write_text(mail+mp.read_text(encoding='utf-8-sig'),encoding='utf-8')
st.update(at=now(),phase='TASK180_LIMITED_ORGANIZATION_COMPLETE',active_work_package=None,last_completed_work_package=180,current_plan='7.194',plan_progress='7.194',current_head=heads[str(D)],current_source=S,candidate_source=S,source_review_pending=False,source_review_scope='322 limited L2 organization accepted;16 checks/3670 calls/N23 fulltick+real cleanup; not178/179 live or scheduling acceptance',l2_tactic_document_source=S,queued_work_package_state='COMPLETE_LIMITED_ORGANIZATION',queued_work_package_start_authorized=False,next_phase='Task180 complete. Await authorized next package; no new game, retain179 route/live/scheduling gaps.',next_watch_ready=False,next_watch_user_authorized=False)
atom(B/'sol/STATUS.json',st);atom(B/'sol/OPUS_WAKE.json',dict(seq=250,task=180,at=now(),note='180 limited organization complete, N23 integrity/actual cleanup verified; freeze released. No new package/game or ACK wake needed.'))
put('POST_P_PLAN_SYNC.json',dict(at=now(),heads=heads,plan='7.194',source=S,source_unchanged=716,new_games=0))
print(json.dumps(dict(task180='complete_limited_organization',plan='7.194',ticks=23,p50_ms=audit['contexts']['N']['p50_ms'],peak_ms=audit['contexts']['N']['peak_ms'],cleanup=True,new_games=0,heads=heads)))
