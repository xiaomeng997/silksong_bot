"""Record #314's limited L2 acceptance and one bounded next implementation decision."""
from pathlib import Path
import json,datetime,os,subprocess,hashlib,psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/task179_return314_20261106';M=Path('C:/modeling/silksong_bot');D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');V=Path('C:/Users/Meng/.codex/worktrees/forum-tv-prep/silksong_bot');S='e137055c14294f1580bc69ad680decd786c90388'
G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(p,*args):return subprocess.check_output([G,'-C',str(p),*args],text=True,encoding='utf-8').strip()
def put(p,d):
    assert not p.exists(),str(p)
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def save(p,d):
    t=p.with_suffix('.return314.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(t,p)
s=read(B/'sol/STATUS.json');assert not s['live_or_budget_running'] and not s.get('own_offline_jobs')
assert git(D,'rev-parse','HEAD')==S
assert '**最新编号**：#314' in (B/'opus/TO_SOL.md').read_text(encoding='utf-8').split('## 用法',1)[0]
packet=read(A/'SOURCE_PACKET.json');assert all(sha(D/n)==h for n,h in packet['raw_runtime_files_sha256'].items())
probe=read(A/'ROOT_L2_REPRO.json');end=read(A/'ROOT_JOB_END.json');assert probe['component_pass'] and end['error'] is None
pid=probe['job']['pid'];created=probe['job']['created']
try:assert abs(psutil.Process(pid).create_time()-created)>.02,'own E job still exists'
except psutil.NoSuchProcess:pass
put(A/'ROOT_PROBE_CLEANUP.json',dict(at=now(),pid=pid,created=created,actual_job_released=True,source_unchanged=True,formal_P=0,game=0))
astratext='''# Astra/xhigh 同179第二次窄裁定（#314，实际延续原代理）

实际代理/root/astra_task178_pose_review，沿用gpt-6-astra/xhigh，仅只读，无计算/写源/游戏。建议同179默认关闭的G1-a局部候选加G3既有动作分段正例；不改全局余量，不加G2着地奖励，未进入P或游戏。

forum_v2.py139..157/182..199的增长余量承担未决定移动、转向和重规划的不确定性，同时关注两只不会使其物理不确定性变小。314归因只证明指定合成条件下首挡，下一工件需直接实际决策frame，不能由t反推。

局部收窄仅在返回中间、两只当前可见且满足Idle/Walk支持条件时，对非焦点可分离身体层用FOCUS_M；其余保持。不能改共享m_of：689..724/787..829还用于危险/反击。新增第二对象不会自动得到原仅dash_focus的冲刺rule补回，必须保留该对象原冲刺检查。状态改变应在下一承诺前失效，不能用失效门兜底已发不可撤回段。

最小正例先越过身体边缘再下降或接缝下劈，复用原水平接近和下劈/落地行，真实交还点重评。原几何余量/全owner/后继检查不变，不截短检查窗口。可明确合成有效宽缝走完整生产路径，后对原窄缝给通过或明确失败；G3第4帧真实身体冲突仍硬拒绝。无地面缝保持未完成、重评现有空中下劈；若仍无完整正例给第一阻断及最小接近段缺口，不等待全局预测/统计标定/自然录像。

这只是有界行为开发决定，尚未证明双对象FOCUS_M更准确或原窄缝有安全解。
'''
assert not (A/'ASTRA314_REVIEW.md').exists();(A/'ASTRA314_REVIEW.md').write_text(astratext,encoding='utf-8')
attrp=B/'opus/review179/l1_313/v2A_v2attr.json';attr=read(attrp)
summary=[]
for f,r in attr['frames'].items():
    summary.append(dict(label=f,focus=r.get('focus'),rows=r.get('rows'),land_rows=r.get('land',{}).get('n'),land_free=r.get('land',{}).get('free'),pogo_rows=r.get('pogo',{}).get('n'),pogo_free=r.get('pogo',{}).get('free'),first_land_example=r.get('land',{}).get('examples',[])[:1]))
put(A/'ROOT_V2_ATTRIBUTION_SCOPE.json',dict(at=now(),artifact=str(attrp),sha256=sha(attrp),selected=attr.get('selected'),brief=summary,actual_scope='v2A.out explicitly delays entity335470 sixty Updates from2800; first divergence2812, synthetic hero from2814. Conditional production-configuration replay, not original closed-loop episode.',frame_scope='attrv2_314.py CUR f=round(2650+(t-6.5168)*60), labels not independently proven actual decision/raw frames. Next evidence must bind real frame.',runtime_path='forum_planner_policy1127 V2Feed.support ->1184 planner.tick fplan; V2Forecast.occupied_split -> RangeSupport. MultiForecast remains used by other consumers, not this S1 attribution.'))
put(A/'SOURCE_REVIEW.json',dict(at=now(),source=S,base='830cc00951fbaf9b39fcb2b50c6451b8bd1a53d4',source_delta_review_pass=True,l2_two_P2_fixed=True,complete_behavior_accepted=False,accepted=False,processed_opus_number=314,runtime_changed=packet['changed'],root_probe=str(A/'ROOT_L2_REPRO.json'),root_cleanup=str(A/'ROOT_PROBE_CLEANUP.json'),astra=str(A/'ASTRA314_REVIEW.md'),formal_P_started=False,game_started=False,remaining='ground return and no-gap airborne continuation lack successful complete production paths',development_decision='same179 default-off local G1-a separable-body candidate plus existing G3 segmented approach; no global margin/G2/rune-tail changes'))
rel='docs/plans/forum_clapper_plan.md';p=M/rel
for tree in (M,D,V):assert not git(tree,'diff','HEAD','--',rel) and (tree/rel).read_bytes()==p.read_bytes()
doc='''

#### #314两项L2回修有限核过；实际V2阻挡与默认关的局部G1/G3候选，同179继续（11-06，进度7.182）

已处理 Opus #314，runtime e137055c（父6457f17b）。只改clapper_priority一运行文件及原测试。Root独审全增量/相邻姿态与完成门，714原运行项绑定仅此一项变；E24–31/Idle真实35948/create1793956577.4011312独跑原两个边界加未知接触/真实GROUND完成，foreign0/源全同/错误0，实际进程退出后清任务。H20.75/y9、根20/21.5现正确给接缝20.75/空中stomp；开缝仍空中不完成、合缝恢复air/stomp，unknown contact不完成，GROUND落进可站缝才清back。两个313 P2有限关闭；source_delta_review_pass与full behavior分开，完整返回仍未通过，314不进实机accepted集合。Opus71专项通过、相关497过/2败仅记录，Root不重复跑；两失败是旧map2静态扫描/钟目标断言，原件tests314/314b保留，不宣称全套绿。

关键归因更正：合同V2=1，forum_planner_policy1127以V2Feed.support构fplan、1184传planner.tick，第一阶段用V2Forecast/RangeSupport，不是此前查的MultiForecast层。已交v2A逐候选归因中落地/接缝下劈行首冲突来自非焦点Idle的rule余量（样例1.403/1.916/2.527u；源曲线k36为4.3），focus0.5；该有限层级结论核收。v2A.out明确335470自2800延后60帧、2812首动作分歧、2814后英雄合成，不能称原局自然闭环定因；attr标签由固定T0反算frame而非真实决策帧，下一工件必须直绑实际frame。ROOT_V2_ATTRIBUTION_SCOPE保留实际2807/2826/2830/2836标签与行数/首冲突，不用报告另一组帧名替换工件。MultiForecast实际尾朝向与hazard生命周期问题列后续，未当此S1的首阻挡，也不统一截尾或删双向闪避。

当前两个完整生产正例仍无：原窄缝即使诊断宽放所有层，部分落地行在二阶段第4步仍碰越过怪的身体上方；合成宽缝有安全落地行但高悬排序更优；试加ground分只改FORCED平局且条件模型中新增受伤，未提交。Root不为未完成功能测P，不以诊断余量/静态NPC后段的模型hurt签实机率。SOURCE_REVIEW、ROOT_L2_REPRO、ROOT_PROBE_CLEANUP和ASTRA314_REVIEW保存。

按用户workflow复用实际Astra/xhigh窄审G1数值语义与G3下一步，Sol裁定同179推进默认关闭的G1-a局部候选，不全局修改Clapper margin/table/共享m_of，不加入G2着地奖励。只在当前实际生效的回中间意图、两只可见且符合Idle/Walk支持域时，对非焦点可分离身体层用既有FOCUS_M；攻击/反击/符文/其他危险及unknown原值保持，e.raw不能分离则保留原余量。新增第二对象须同样保留原朝怪冲刺的rule检查，不能只沿旧dash_focus一只漏护。状态变化在下个承诺前作废候选，已发不可撤回段仍完整原检查；不可拿逐tick失效当事先安全保证。此为有界行为开发候选，尚未证明双对象0.5更准确，默认关闭、真实清单绑定要在同包给齐，不转生产默认。

G3复用既有水平接近→越身体边缘→下降/接缝下劈，在真实交还点重评；保留全owner/真实几何/未结束危险/后继/原时钟与预算，不截短时域或改危险成安全凑正例。先给明确合成有效宽缝的地面返回、无地面缝空中接续完整policy/planner/B2/before_send/sent正例，再对原窄缝给通过或确切首阻断/最小缺口，不扩全局预测或新池、不等自然局。71/497套件与原85拍P不重跑；功能成立后才交受影响连续窗口。FACE_HOOK0/BOUNCE_TABLE0、无下一局许可、旧观察不重开、墙角打法延后不变。以上同seq238一次反馈，Opus仍唯一运行源码owner，无需逐项ACK。
'''
assert '进度7.182' not in p.read_text(encoding='utf-8');p.write_text(p.read_text(encoding='utf-8')+doc,encoding='utf-8')
heads={}
for tree in (M,D,V):
    if tree!=M:(tree/rel).write_bytes(p.read_bytes())
    git(tree,'add','--',rel);git(tree,'commit','-m','docs: accept return state repairs and bound local G1 G3 candidate','--',rel);heads[str(tree)]=git(tree,'rev-parse','HEAD')
put(A/'PLAN_SYNC.json',dict(at=now(),heads=heads,runtime_source=S))
mail='''## seq238 / 同Task179：#314两项L2回修核过；裁定默认关的G1-a局部身体层候选＋G3已有动作接续，一包继续

Root独审e137全部增量，714运行项仅1变，原两个边界/未知contact/真实GROUND完成小探针独跑过，foreign0/源全同/自有E35948实际已退出。两个313 P2有限关闭；SOURCE_REVIEW source_delta_review_pass=true，但完整行为accepted=false，source314不进game accepted集合。analysis/task179_return314_20261106/有Root探针/源码包/清理与实际Astra/xhigh窄裁定。主计划7.182三树仅文档同步；不重复71/497、旧85P，不开game。

先更正证据适用性：你现在查V2/RangeSupport的方向对，Root核policy1127/1184实际fplan；但v2A.out明确entity470从2800延后60帧、2812首分歧/2814后hero合成，所以报告2.2不能叫原局自然闭环。实际JSON标签是2807/2826/2830/2836，工具用T0=6.5168/F0=2650从t反推f；下一工件直接绑定实际decision/raw frame，别用线性时钟换算冒充精确物理帧。本包只需把原件标清条件、修下一次记录，不重跑所有旧对照。尾朝向/路径生命周期列后续，不先改MultiForecast；当前首挡是限定条件下非焦点rule，不等于已证明是模型bug。

G1选择a，但仅做开发树默认关闭的局部候选（同179，不新立预测包，不再等用户选参数）：当前实际生效的middle return意图、两只当前可见且满足Idle/Walk支持域，对非焦点可分离身体层使用FOCUS_M。这不是证明其位置不确定性变小，也不改全局MARGIN_MODE/table/共享m_of。m_of还影响hazards/reaction，不能复制原--diag-back-margin的所有层宽放；e.core/body无法分开则不收窄。攻击/反击/符文/延迟危险及其他owner/unknown维持原值。新收窄的第二对象不会自动拥有旧dash_focus的rule补回，必须给它保留朝怪冲刺的原检查/保守回退（不是只护住L2 target一只）。状态改变须在下一承诺前作废，已发不可撤回段仍须原全检查，不能用下一拍能重规划豁免当前锁段。开关/行为元数据/实际绑定同包交齐，默认关路径逐位保持；名称/最小接口由你选，不需再ACK。

G3同一包用已有水平接近→越过身体边缘→下降/接缝下劈，真实交还点再重评。全owner/真实几何余量/后继/未结束危险/原时钟及预算保持，二阶段第4步若仍撞身体硬否，不能靠评分、减检查窗口或局部Margin覆盖。先明确合成、输入有效的宽缝各给地面返回和无地面缝空中接续完整policy/planner/B2/before_send/sent局部正例；再对原窄缝给能过或确切首阻断及最小接近段缺口。可复用已有行和接近段，不搞新池/在线搜索、全局预测重做或等自然录像。不要把挑到stomp风格当连续下劈，BOUNCE_TABLE仍0；若公共下劈接续无完整入口，直接指出最小缺口而不是继续给只选意图的验收。

G2不加。已有生产余量下ground加分只改FORCED平局且新增hurt的反例保留；不为凑落地调高奖励让危险行赢。原成功2601–2638前缀保持。两个相关老测试失败原样记，不顺手扩包修map2/钟，不声称大套件全绿。

这是有界开发决定，不是把双对象FOCUS_M签为更准确，也没有原窄缝安全解/下一局许可。完整功能正例成立后才给受影响连续P入口，Sol再审/测；旧观察局不重开，FACE_HOOK0/BOUNCE_TABLE0/原输入与资源清理门及墙角打法延后保持。你继续唯一实现owner，同包一次交完整修复和边界，不再拆为每项等待批准的小轮。

'''
mp=B/'sol/TO_OPUS.md';tmp=mp.with_suffix('.return314.tmp');tmp.write_text(mail+mp.read_text(encoding='utf-8'),encoding='utf-8');os.replace(tmp,mp)
wp=B/'sol/OPUS_WAKE.json';w=read(wp);assert w['seq']==237;w.update(seq=238,task=179,at=now(),note='314 two L2 P2 fixed+independently checked. Same179: default-off local separable-body G1-a with second-object dash guard, plus existing G3 segmented return; no global margin/G2/tail expansion. Full branch positives before P; no next live.');save(wp,w)
s=read(B/'sol/STATUS.json');s.update(at=now(),phase='RETURN314_L2_FIXED_G1_G3_LOCAL_CANDIDATE',current_plan='7.182',plan_progress='7.182',candidate_source=S,source_review_pending=True,source_review_file=str(A/'SOURCE_REVIEW.json'),opus314_review=str(A/'SOURCE_REVIEW.json'),astra314_review=str(A/'ASTRA314_REVIEW.md'),next_watch_ready=False,next_watch_user_authorized=False)
s['return_middle_preference']['implementation']='two L2 lifecycle defects fixed and independently checked; complete action paths pending local G1/G3 candidate'
save(B/'sol/STATUS.json',s)
print(json.dumps(dict(recorded=True,l2_P2_fixed=True,complete_behavior_accepted=False,seq=238,heads=heads,formal_P=False,game=False),ensure_ascii=False))
