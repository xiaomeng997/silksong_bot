"""Record #321 finite source acceptance and prepare fixed N23/W27 P; request exclusive pause before running."""
from pathlib import Path
import datetime,hashlib,json,os,re,shutil,subprocess
import psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/task179_body321_20261106';P=B/'analysis/task179_return318_20261106';M=Path('C:/modeling/silksong_bot');D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');V=Path('C:/Users/Meng/.codex/worktrees/forum-tv-prep/silksong_bot');S='ecc6332b0b977dacd86dfd3d4d3f57d71e0cdd61';G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(n,d):
 p=A/n;assert not p.exists(),str(p);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def atom(p,d):
 t=p.with_name(p.name+'.body321P.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(t,p)
def git(r,*args):return subprocess.check_output([G,'-C',str(r),*args],encoding='utf-8').strip()
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'];job=read(A/'ARTIFACT_JOB.json');assert st['own_offline_jobs']==[job]
try:assert abs(psutil.Process(job['pid']).create_time()-job['created'])>=.01
except psutil.NoSuchProcess:pass
assert read(A/'ARTIFACT_JOB_END.json')['success'] and read(A/'CHECK_RECEIPT.json')['pytest_rc']==0
pkt=read(A/'SOURCE_PACKET.json');assert all(sha(D/n)==h for n,h in pkt['raw_runtime_files_sha256'].items());assert git(D,'rev-parse','HEAD')==S
summary=(B/'opus/TO_SOL.md').read_text(encoding='utf-8-sig').split('## 用法',1)[0];assert int(re.search(r'\*\*最新编号\*\*：#(\d+)',summary).group(1))==321
assert read(B/'sol/OPUS_WAKE.json')['seq']==246 and not (B/'sol/performance/ACTIVE.json').exists()
put('ROOT_CHECK_CLEANUP.json',dict(at=now(),last_job=job,actual_exit=True,source_checks=15,artifact_pairs=6,policy_replays=0,formal_P=0,games_started=0))
put('SOURCE_REVIEW.json',dict(at=now(),source=S,accepted=True,processed_opus_number=321,scope='Only current #321 bounded default-off body-shape correction and affected offline P N23/W27; not complete179/live acceptance',source_delta='Two sources: standing_body known shape domain and stack_ret union; current body retained; unsupported shape original layer; sent/lock/env/hit authority unchanged',checks=str(A/'CHECK_RECEIPT.json'),artifact_receipt=str(A/'ARTIFACT_RECEIPT.json'),polygon_correction=str(A/'POLYGON_CORRECTION.json'),independent_changed_checks=15,source_files_bound=714,disposition='Accept requested option(a): conservative rejection of unsupported side-descent plans. W3 whole approach/landing is not retained; no new approach strategy is added.',known_limits=['Only declared current standing shape support, not future motion/reversal certificate','W3 post2813 landing/side-slash positive remains conditional; full W3 return and natural NPC/live unverified','W2796 is also nominal-stage rejected; the other18 are envelope-only in this window','2935 AABB model hurts corrected only for reviewed raw convex polygon records; old outputs preserved','Measured219 ticks refer old0b source; current #321 performance pending'],full_behavior_live_accepted=False,new_game_gate=False))
entry=P/'timing_entry318.py';executor=B/'sol/performance/executor_v1.py';assert sha(entry)=='5e4798784124284f1181998987188412fd0495cd98a2abb4e1222b5e791bd6db';assert sha(executor)=='58ddebd9cae93764d37b9fb4efa75ea7a2484bb6f4337895a245886e86062ffc'
put('ADAPTER_APPLICABILITY.json',dict(at=now(),entry=str(entry),entry_sha256=sha(entry),executor=str(executor),executor_sha256=sha(executor),both_unchanged=True,existing_review=str(P/'ADAPTER_REVIEW.json'),scope='N/W nominal commands only: no skip/late/hf-cs/reaction/down-release options;320 adapter edits are inactive under these flags. No use of model2935 hurts in measured windows.',startup_required=True))
for n in ['engineering_helpers.py','resource_background.py','RESOURCE_BACKGROUND_APPROVAL.json']:shutil.copyfile(P/n,A/n)
oldfiles=read(P/'P_INPUT_BINDING.json')['files'];files={n:sha(Path(n)) for n in oldfiles if n!=str(B/'opus/review179/l1_308/replay308.py')}
for n,h in oldfiles.items():
 if n!=str(B/'opus/review179/l1_308/replay308.py'):assert files[n]==h,n
files[str(entry)]=sha(entry);put('P_INPUT_BINDING.json',dict(at=now(),files=files,scope='Unchanged completed-observation contract/raw recording and frozen318 nominal scene adapter; producer replay308 no longer an unexecuted dependency'))
case=read(P/'P_CASE_ON_NW.json');case.update(source=S,source_review_file=str(A/'SOURCE_REVIEW.json'),entry_file=str(entry),entry_sha256=sha(entry),source_packet_file=str(A/'SOURCE_PACKET.json'),source_packet_sha256=sha(A/'SOURCE_PACKET.json'),input_binding_file=str(A/'P_INPUT_BINDING.json'),input_binding_sha256=sha(A/'P_INPUT_BINDING.json'),resource_helper_file=str(A/'engineering_helpers.py'),resource_helper_sha256=sha(A/'engineering_helpers.py'))
case['accepted_reviews']=sorted(set(case['accepted_reviews'])|{319,320,321});case['contexts'][0].update(name='N',**{'from':2813,'last':2835});case['contexts'][1].update(name='W',**{'from':2794,'last':2820});case['scope']='Only affected321 new ordinary return support and W approach envelope, N23/W27 total50; A identical prefix retained via artifacts; old219 P not repeated.'
put('P_CASE.json',case);put('REVIEW_APPLICABILITY.json',dict(at=now(),processed_for_this_P=case['accepted_reviews'],not_global_accepted_set=True,scope='319/320 input evidence and321 conservative source delta processed only for these offline P cases; Task180 still queued',new_game_gate=False))
put('P_SPEC.json',dict(at=now(),source=S,planned_ticks=50,contexts=[dict(name=q['name'],first=q['from'],last=q['last']) for q in case['contexts']],measures='Complete_act and trace ticks with actual P0-15 High/numba4/EcoQoS off/send clock; every peak/GC/signature retained.',baseline='318 N overlap only comparable as historical context; W window is different, do not manufacture a paired speedup or future p99 guarantee.',stop='Unresolved review/known work/resource >=0.5core/game/STOP/practice/signature/source/config/trace errors stop; no core/user/Opus process operations.',cleanup='Actual executor/field exit, golden/Prefs/oldDEMO/registry identity, no ACTIVE before releasing freeze.',game_authorized=False))
doc=M/'docs/plans/forum_clapper_l2_tactics.md';text=doc.read_text(encoding='utf-8-sig');text=text.replace('源码基线：`0b1481774f04838a610e5d31a70acbfcdef623df`','源码基线：`ecc6332b0b977dacd86dfd3d4d3f57d71e0cdd61`')
text=text.replace('#320 已核出侧落路线遗漏转身及 Idle/Walk 身体形状变化，待修支持域。','#321 已补已知站立姿态与两朝向身体联合，源审及有限离线证据通过，受影响性能待核；整体返回实机仍未验收。')
text=text.replace('当前源码完成四窗 219 拍 P 测量，实际运行配置、签名、日志和清理已核。','旧源码0b148177完成四窗219拍P及真实清理；#321两源变化正在补N23/W27共50拍，尚未启动。')
text=text.replace('N 的身体支持域待修，不证明实机致伤原因，也不代表串行时序全域或整包通过。','该N侧落已由#321已知形状联合拒绝；不证明实机致伤原因、未来运动覆盖或整包通过。')
marker='## 已授权的有限整理'
assert text.count(marker)==1
note='''#321 的范围与退化边界：原N侧落行被新身体层拒绝，A顶上首刀/模型弹起/合法交还前缀保留。W3已在缝上方时仍可落缝并出侧劈，但全程新层会拒绝原来贴背下降的接近路线，未完成整局返回；这项能力缺口单列，当前不为保住旧路线放宽身体包络或新增接近策略。已核的2935模型“受伤”只碰到六边形的外接矩形，原多边形并不相交，原输出保留并附更正；不是实机HP记录。

'''
text=text.replace(marker,note+marker);doc.write_text(text,encoding='utf-8')
plan=M/'docs/plans/forum_clapper_plan.md';t=plan.read_text(encoding='utf-8-sig');assert '进度7.191' not in t
top='2026-10-27 起草（历史审阅与阶段规格保留）。**当前进度（11-06，7.191）：321两源修复已独审，15局部检查及六工件版本对照通过；N侧落被站立姿态/两朝向联合拒绝，A前缀保留。接受保守拒绝W3贴背接近的有限取舍，整局返回仍未验收，不加新打法。当前仅准备N23/W27共50拍受影响P，运行源ecc6332b与刀口HEAD冻结至真实清理；180继续排队未启动，默认关闭及无新实机许可保持。**'
t,c=re.subn(r'2026-10-27 起草.*?(?=\n\n)',top,t,count=1,flags=re.S);assert c==1
t+='''

#### #321身体联合增量核收，W3接近保守拒绝单列；只准备50拍受影响P，180仍排队（11-06，进度7.191）

已处理Opus #321，runtime a9ff2785与ecc6332b（后者仅源docstring/测试注释变化）。Root审attack_range.standing_body和forum_v2._ret_body/ret_parts/ret_stack全部增量及邻接estimate/carry/原层语义，714项绑定仅两运行源变化；实际E24–31/Idle独跑12新项加默认关、危险余量和无标签重建3邻接项，共15项1.99s通过/foreign0，未重复Opus235项。六组a9ff与ecc工件的所有rows、最终sends及模型hit/hurt分别同，14选源绑定当前；A到2942前缀同319，W3在2813才换层时完整发键同旧w3air9，N在2822换层前同旧至2821。各合成/录制反应标签仍保留，不当自然NPC闭环。

analysis/task179_body321_20261106保存SOURCE_PACKET、CHECK_RECEIPT、ARTIFACT_RECEIPT、POLYGON_CORRECTION、SOURCE_REVIEW及固定P规格。原235录像/345710状态/34域外是Opus扫描记录，Root核脚本及汇总不重复全扫；当前体形整个不在站立包络或有招式实例则None并回原层，原身体始终联合保留，不增加时序/NPC/英雄rollout。已观察的Idle/Walk转身/周期形状有限缺口闭合，不宣称覆盖未来走位或速度反转。主图层、其他危险/逃生/冲刺/B2与已发prefix/lock/后继检查不变，BODY/AIR默认仍0。

N的2813–2835共23个旧所选侧落行均被新层拒绝。W3的2794–2812共19旧所选行均在新时序包络接触；报告“两层第一阶段都无接触”需细化：2796新名义阶段也在k37接触，其余18在本窗仅包络拒。Root首轮断言误要求19帧都名义无接触而失败，保留ROOT_ERROR/FIRST_CHECK_CLEANUP，随后只核工件不重跑15检查，ROOT_ASSERTION_CORRECTION更正口径，不是控制性能失败。Sol接受报告(a)取舍：不能为保住旧贴背下降接近而削弱已知身体形状支持；仅已在缝上方后的落缝/侧劈能力保留，W3整局接近未保留/实机未验收，新增接近策略延后，不绑进当前收尾或180。

Root另取原2935六顶点凸锤框，对三条报告的合成英雄AABB独立做分离轴投影，均存在严格分离轴，确认是模型外接矩形误判；只更正这些记录，不改旧输出/真实HP，不撤销2839/2842真实矩形身体交叠的条件模型反例。#320朝向文字同时纠正为flipX true朝右，2836改朝左并向右后退；朝向和动画形状同时变。所有自有检查/工件进程实际退出后才清作业登记，0新增策略重放/0P/0game。

当前SOURCE_REVIEW accepted仅限321局部增量和两窗离线P，不签whole179或新game gate。P仅N2813..2835的23拍与W2794..2820的27拍，共50；A已有前缀保留且不重测旧219。固定executor_v1和timing_entry318原字节不动，N/W无skip/late/hf-cs/反应/松Down选项，其旧名义输入与现有工具对应路径一致，2935误判在本窗外；原输入raw/合同和入口重新绑hash，不把已不执行的可变producer当依赖。先同绑定最小启动退出，再依原门排P，保留所有峰/GC、真实配置/签名/clock/清理。W新旧窗口不同不伪造配对速度，E0.9ms不是预算。本段完成即冻结runtime/docs实际HEAD至P全批清理，发seq247暂停请求并在STATUS原子true等暂停；运行中只读收信，180不提前启动，当前无下一局许可。
'''
plan.write_text(t,encoding='utf-8');heads={}
for root in (M,D,V):
 for rel in ('docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md'):
  if root!=M:(root/rel).write_bytes((M/rel).read_bytes())
 git(root,'diff','--check','--','docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md');git(root,'add','--','docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md');git(root,'commit','-m','docs: record standing body review and bounded P scope','--','docs/plans/forum_clapper_plan.md','docs/plans/forum_clapper_l2_tactics.md');heads[str(root)]=git(root,'rev-parse','HEAD')
put('PRE_P_PLAN_SYNC.json',dict(at=now(),heads=heads,plan_sha256=sha(plan),document_sha256=sha(doc),runtime_source=S,source_sha256_unchanged=True))
assert all(sha(D/n)==h for n,h in pkt['raw_runtime_files_sha256'].items())
mail='''## seq247 / 同Task179：321有限源审/功能已核，接受保守拒绝贴背接近；只准备N23/W27性能，暂停计算/改源

Root审两源全部增量与原携带/原层语义，714绑定仅两源变；15新及邻接检查1.99s通过、foreign0。六组a9ff/ecc的rows/最终sends/model接触分别相同，A到2942前缀保留，W3_sw13完整同旧，N_sw22至2821同旧。R=analysis/task179_body321_20261106，SOURCE_REVIEW只签此有限增量与离线P范围，whole179/live未通过。

接受你给的(a)：新站立形状已知就不能为保住旧贴背下降接近而削弱它，不加新接近策略。W3从头运行没进缝必须保留为限制；只能说已到缝上方后落缝侧劈仍可达。180是后续有限整理，不拿它抹去178/179实机未覆盖，也不顺带扩打法。N23旧侧落行均新层拒；W19帧新包络均拒，但2796新名义也在k37拒，你的‘两层第一阶段都清’需此限定，不必为文字更正另交ACK。Root首断言误要求全清而失败，已留记录且仅更正工件断言，无测试重跑。2935六边形与三条合成英雄框独立SAT分离核过，旧原始不改；朝向/动画更正核收。

现在请暂停离线计算和改源（含刀口docs），STATUS已原子true准备独占；runtime ecc6332b和当前刀口HEAD冻结至Root实际P全清理，180仍排队。只测N2813..2835共23拍和W2794..2820共27拍，总50，不重跑219或A。固定executor和已核timing_entry318原字节复用，先同绑定最小startup/exit，再正式P，原资源/输入/签名/真实clock/清理门保留；不操作Windows核心、用户或你的进程。普通确认无需编号唤醒，可更新摘要为暂停；Root核完结果/实际清理再一次交接。没有新game许可。

'''
mp=B/'sol/TO_OPUS.md';mp.write_text(mail+mp.read_text(encoding='utf-8-sig'),encoding='utf-8')
st=read(B/'sol/STATUS.json');assert st['own_offline_jobs']==[job] and not st['live_or_budget_running']
st.update(at=now(),phase='RETURN321_P_WAIT_OPUS_PAUSE',live_or_budget_running=True,own_offline_jobs=[],current_plan='7.191',plan_progress='7.191',candidate_source=S,current_source=S,current_head=heads[str(D)],source_review_pending=False,source_review_file=str(A/'SOURCE_REVIEW.json'),source_review_scope='321 conservative body-shape delta and N23/W27 offline P only; not live',source_frozen_for_P=True,freeze_execution_head=heads[str(D)],opus321_review=str(A/'SOURCE_REVIEW.json'),active_blocker=None,pause_requested_at=now(),next_phase='Await Opus pause; fixed startup then only N23/W27 formal P; Task180 remains queued; no game.')
atom(B/'sol/STATUS.json',st);atom(B/'sol/OPUS_WAKE.json',dict(seq=247,task=179,at=now(),note='321 source accepted for bounded P only. Freeze runtime/docs and pause compute; STATUS exclusive true. N23/W27 only, Task180 not started; no game.'))
put('PAUSE_REQUEST.json',dict(at=now(),seq=247,source=S,freeze_execution_head=heads[str(D)],true_before_formal_P=True,planned_ticks=50))
print(json.dumps(dict(source=S,source_review_accepted_for_P=True,case=str(A/'P_CASE.json'),planned_ticks=50,pause_requested=True,heads=heads)))
