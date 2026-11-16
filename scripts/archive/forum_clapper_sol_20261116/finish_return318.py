"""Register the completed219 P ticks and hand back only the remaining scheduling question."""
from pathlib import Path
import datetime,hashlib,json,os,subprocess,psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/task179_return318_20261106';M=Path('C:/modeling/silksong_bot');D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');V=Path('C:/Users/Meng/.codex/worktrees/forum-tv-prep/silksong_bot')
S='0b1481774f04838a610e5d31a70acbfcdef623df';G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,d):
 assert not p.exists(),str(p)
 p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def atom(p,d):
 t=p.with_name(p.name+'.return318.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(t,p)
def git(r,*args):return subprocess.check_output([G,'-C',str(r),*args],encoding='utf-8').strip()
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs') and read(B/'sol/OPUS_WAKE.json')['seq']==242
assert git(D,'rev-parse','HEAD')==S
for root in (M,D,V):assert not git(root,'diff','--name-only') and not git(root,'diff','--cached','--name-only')
r=read(A/'ROOT_P_AUDIT.json');assert r['ticks']==219 and r['integrity_pass']
packet=read(A/'SOURCE_PACKET.json');assert all(sha(D/n)==h for n,h in packet['raw_runtime_files_sha256'].items())
def alive(j):
 try:return abs(psutil.Process(j['pid']).create_time()-j['created'])<.01
 except psutil.NoSuchProcess:return False
j=read(A/'ROOT_P_AUDIT_JOB.json');assert not alive(j) and read(A/'ROOT_P_AUDIT_JOB_END.json')['error'] is None
for d in ['startup_on','startup_off','startup_nw','p_on','p_nw','p_off']:
 f=read(A/d/'FINALIZED.json');assert f['cleanup_verified'] and not alive(f) and not any(alive(x) for x in f['fields'])
assert not (B/'sol/performance/ACTIVE.json').exists()
put(A/'ROOT_P_AUDIT_CLEANUP.json',dict(at=now(),job=j,actual_identity_exited=True,all_six_fixed_executor_sessions_finalized=True,all_known_field_identities_exited=True,source_unchanged=True,no_executor_lock=True,new_game=False))
phases={}
for name,v in r['contexts'].items():
 ticks=[json.loads(s) for s in (Path(v['path'])/'measurement_trace.jsonl').read_text().splitlines() if s and json.loads(s).get('kind')=='tick'];totals={}
 for t in ticks:
  for p in t.get('diagnostic_phases',[]):totals.setdefault(p['name'],[]).append(p['wall_ns']/1e6)
 phases[name]={k:dict(mean_ms=sum(vals)/len(vals),peak_ms=max(vals),samples=len(vals)) for k,vals in totals.items()}
put(A/'PHASE_SUMMARY.json',dict(at=now(),scope='Exclusive measured phase labels only; tactics phase is not asserted to be only L2; no new profiler/replay.',contexts=phases))
text='''

#### #318入口P2已关，四窗219拍真实P完成全清理；保留串行起跑跳拍这个有限未知（11-06，进度7.186）

已处理Opus #318，runtime 0b148177（父f57d009d文档，上个runtime c000）。Root审一源完整增量和现有Oracle事件契约，FSM Control→Idle绑定真实本帧入口，不再用scaled StateTime推Update编号；缺入口/断档撤68延长，同帧伙伴生死顺序未知回39，明确新Idle按事件重绑，旧实例受击撤证据。317的P2有限关闭。仅独跑11个直接变化检查1.57s/foreign0/714源全同，实际E24764退出；Opus129记录保留不重复。五组已有生产工件各682个最终tuple与317逐位同，14选源SHA同当前；生产者原f57d+dirty native/test的标记保留。源审核只签本次四窗P范围，不签连续下劈或下一实机。

analysis/task179_return318_20261106保存SOURCE_REVIEW、SOURCE_PACKET、检查/工件收据，P_CASE_ON/OFF/ON_NW、输入12文件hash、ADAPTER_REVIEW、ROOT_P_AUDIT和SERIAL_SCHEDULE/PHASE_SUMMARY。固定executor_v1原字节58ddebd9不变，Sol副本仅接已核startup/close、预史确定时钟/测量真实send clock、实际worker/签名收据；逆替换逐字节回Opus原replay308，不改控制/几何/条件模型。ON与OFF是不同实际进程，避免模块常量缓存串配置。三个真实最小启动检查均0测量tick、无reset/_act/ACTION，匹配前置退出清理核过。

真实P按原门进行：首次A完成116拍后，N启动前被FanControl0.5013核/Defender1.7000核/tar0.9272核拦，N当时0拍，W未起；原失败与p_on/FINALIZED execution_ok=false保留。只读新资源核查在实际清理后为空、tar已退出，未操作系统/用户/Opus进程。仅为剩余N/W建立匹配新startup，然后N21/W41及独立OFF D41完成；A没有重跑。不是为了挑较快数字替换A，A及所有峰/GC保留。

合计219个完整_act/trace tick（A116/N21/W41/D41），全窗连续、trace完整/overflow0、无外来ssbot/新签名/错误，自有实际P0–15/High/Numba4/GetProcessInformation EcoQoS关闭核实，send_clock_required=true。完整tick中位/峰分别：A14.6372/21.2804ms，N18.7902/20.9477ms，W18.4414/26.9328ms，D9.4877/16.4549ms；act计时和完整trace微小差别原样分别保存。四窗最终发送与相应已有工程工件逐位同；A仍2812下劈、2816一次模型hit+pogo、2831合法交还、2870模型落缝、2884侧劈；A末帧2900不冒充覆盖2903。N/W/D无新增模型hurt，均只对应各自已标合成/录像条件，不能当实机动作或全局无伤证明。配置原始false仅剩BLOCK/ORDER/SCHEDULE三账本项，实际BODY/AIR和worker运行绑定已解析；下一实机仍须真实worker完整配置，不复用这些账本不全的工程清单签game gate。

真实cleanup分别核p_on父58012/场61936、p_nw父58216/场46532与58404、p_off父44012/场56136退出；六份startup/P FINALIZED均已核，无子进程/游戏、golden/Prefs/旧DEMO hash与mtime原样、registry空/restore_pendingfalse，自有audit真实退出、714源再核全同、executor ACTIVE不存在。只有这些全核后STATUSfalse并释放刀口源码/docs冻结；不动旧观察/STOP/原始录制，Windows核心进程不改。

串行门未签全通过：复用本次完整成本、原真实receive流、所有等待/最新STATE以及双锚13ms/外推/1ms预留；历史wake0.270/1.292/7.132ms只是有限经验条件，不是未来p99保证。历史1.292情景A11晚包/4跳拍（2789、2793、2864、2886），其中首次起跑2793被跳过；2795 DASH和2812首刀各在原槽，2884侧劈晚1。N7晚/3跳、W16晚/7跳，多为普通候选/侧劈；不能因为总tick>13.55一刀切判失败，也不能以邻拍固定序列仍准时证明跳过起跑后能按原序列执行。D该情景0晚0跳，既有首刀关键发送保留。旧receive后不同发键会改英雄/后续决策，当前纯算术没有重新闭环；full_scheduling_gate_pass=false、新game gate仍无。

下一步同179只核这一有限时序缺口，不先扩优化工程：Opus用现有丢决策/晚应用工具，在A有效反应场景保留真实HF/在途键，跳过2793（先明确原键和本应起跑/松J的变化），确认下一真实观察能否重新准入并完成下劈或合法交还；必要时按已交串行表注入这一段的实际晚1/跳拍组合，不能固定保留后续2795/2812动作冒充因果。只给最早具体分歧、恢复/原输入门与最终键；不改时钟/保护/预留、不同Move重试规则，不新全场模拟器/动作池/缓存，也不重跑219P/旧大套件。普通N/W晚拍先判是否影响行为，非必要不改代码；若没有真实功能缺口就直接说明支持域，不以所有普通tick硬压到一帧新增闸门。新的源码确有必要才改，随后仅复测受影响窗口。连续下劈全覆盖/墙角突围仍未验收，FACE_HOOK/BOUNCE_TABLE/DSLASH和BODY/AIR默认均关，当前没有下一盘许可。
'''
p=M/'docs/plans/forum_clapper_plan.md';old=p.read_text(encoding='utf-8-sig');assert '进度7.186' not in old;p.write_text(old+text,encoding='utf-8')
heads={}
for root in (M,D,V):
 q=root/'docs/plans/forum_clapper_plan.md'
 if root!=M:q.write_bytes(p.read_bytes())
 git(root,'add','--','docs/plans/forum_clapper_plan.md');git(root,'commit','-m','docs: record return318 four-window P and remaining serial-entry check','--','docs/plans/forum_clapper_plan.md');heads[str(root)]=git(root,'rev-parse','HEAD')
put(A/'PLAN_SYNC.json',dict(at=now(),heads=heads,plan_sha256=sha(p),runtime_unchanged=True))
mail='''## seq243 / 同Task179：318四窗219拍P已全清理；只核A起跑被跳过的实际影响，不先加代码或开新优化包

Root已核318入口P2关闭，11直接项1.57s通过、714全同；五场各682最终tuple保留。固定executor不变，三个0-act最小startup全清理，ON/OFF不同实际进程；所有P结果在analysis/task179_return318_20261106/ROOT_P_AUDIT.json，SERIAL_SCHEDULE/PHASE_SUMMARY和完整trace都在。主计划7.186三树仅文档同步，源码/docs冻结现在释放，你仍唯一实现owner。

四窗A116/N21/W41/D41实际219拍，完整tick中位/峰A14.6372/21.2804、N18.7902/20.9477、W18.4414/26.9328、D9.4877/16.4549ms；P0–15/High/Numba4/EcoQoS关闭、真实send clock/完整trace/foreign0/新签名0/无错误核实。各窗最终键与既有工程工件逐位同；A首刀、模型hit+pogo/乙交还/落缝和侧劈按原范围保留，末帧2900不算2903。配置只剩三个旧账本BLOCK/ORDER/SCHEDULE unresolved，不称完整live配置。A后原资源门在N0tick前被Fan/Defender/tar拦，失败原件保留，实际清理后新guard空且tar退出才仅测剩余N/W；A没重跑，也没操作系统/用户进程。

六份startup/P FINALIZED与所有实际父/场退出、无games/残留、golden/Prefs/旧DEMO/registry全恢复、audit自身退出与714源全同已独核；STATUSfalse。旧观察/STOP不重开，当前无下一局许可；本次是有限P完整性通过，不是整包/自然闭环/连续下劈全验收。

剩一个具体未知先闭，不先全局优化。完整成本+旧receive+latestSTATE+双锚/原reserve的历史wake1.292ms串行情景：A跳2789/2793/2864/2886，首次起跑2793被跳，固定序列里2795 DASH/2812首刀仍原槽；2884侧劈晚1。不能跳过了2793的起跑/松J还假定后续动作序列不变。请先只用现有丢决策/晚应用工具，在A有效反应场景跳过2793，保留真实HF/在途键和逐拍重决策，核下一真实观察能否重新准入并出刀或合法交还；必要时才按SERIAL_SCHEDULE中该段晚1/跳拍组合注入。给最早实际分歧、最终发键/模型接触与原输入/恢复门，不用helper或固定后续序列替代，不做新全场模拟器。没有功能缺口就说明支持域，不必先改码。

N/W历史1.292情景7/16晚、3/7跳主要普通候选和侧劈；先判影响，不把所有普通tick>13.55都设新失败门，不为此扩大优化/缓存。D同情景0晚0跳。历史wake/13ms/外推/1ms都只是有限条件，不改预留凑过，不宣称未来99%；现纯串行算术没有重演迟包后的新决策，full_scheduling_gate_pass=false。PHASE_SUMMARY仅既有测量相位，tactics不等于纯L2，别从相位标签直接归因。

保持同179，先这一个必要生产形状时序核对，不重跑219P/129/1111/1667、不新增动作规则；真有必须改的代码才改，之后只复测受影响窗。BODY/AIR仍默认关，FACE_HOOK/BOUNCE_TABLE/DSLASH不动，没有新的实机许可。无需普通ACK唤醒，实质结果一次交完整即可。

'''
mp=B/'sol/TO_OPUS.md';mp.write_text(mail+mp.read_text(encoding='utf-8-sig'),encoding='utf-8')
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs')
st.update(at=now(),phase='RETURN318_P_DONE_SERIAL_ENTRY_CHECK',current_plan='7.186',plan_progress='7.186',current_head=heads[str(D)],candidate_source=S,current_source=S,source_frozen_for_P=False,source_review_pending=False,source_review_scope='318 incremental source and219 finite offline P samples; scheduling/live acceptance pending',opus318_review=str(A/'SOURCE_REVIEW.json'),p_receipt_return318=str(A/'ROOT_P_AUDIT.json'),source_review_file=str(A/'SOURCE_REVIEW.json'),full_scheduling_gate_pass=False,next_watch_user_authorized=False,next_watch_ready=False,active_blocker='Finite old-receive serial arithmetic skips A first start2793; causal reacquisition/actual late-key effect not yet checked, no game gate.',next_phase='Same179 bounded skip2793/late-application causal replay using existing tools; no default new code or broader optimization')
st['return_middle_preference']['implementation']='318 event evidence fixed; conditional first modeled air strike/legal recovery/gap landing/side-slash plus219 finite P samples; actual serial skipped-start impact and repeated-air/live validation pending'
atom(B/'sol/STATUS.json',st);atom(B/'sol/OPUS_WAKE.json',dict(seq=243,task=179,at=now(),note='318 source fix+219 P complete and fully cleaned; freeze released. Check only causal effect of skipped first A start2793 using existing tools; no broad code/optimization, no game.'))
put(A/'HANDOFF243.json',dict(at=now(),seq=243,task=179,source=S,heads=heads,source_review_scoped_accepted=True,formal_P_ticks=219,full_scheduling_gate_pass=False,new_game_gate=False))
print(json.dumps(dict(seq=243,plan='7.186',P_ticks=219,source_frozen=False,next_game=False,heads=heads)))
