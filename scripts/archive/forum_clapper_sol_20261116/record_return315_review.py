"""Record #315's partial ground-path evidence and one consolidated safety/air-entry correction."""
from pathlib import Path
import json,datetime,os,subprocess,hashlib,psutil,xml.etree.ElementTree as ET
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/task179_return315_20261106';M=Path('C:/modeling/silksong_bot');D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');V=Path('C:/Users/Meng/.codex/worktrees/forum-tv-prep/silksong_bot');S='dfab63a43923635337a79f565a917e64f4b2a55d'
G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe';O=B/'opus/review179/l1_315'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(p,*a):return subprocess.check_output([G,'-C',str(p),*a],text=True,encoding='utf-8').strip()
def put(p,d):
    assert not p.exists(),str(p)
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def save(p,d):
    t=p.with_suffix('.return315.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(t,p)
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs') and git(D,'rev-parse','HEAD')==S
assert '**最新编号**：#315' in (B/'opus/TO_SOL.md').read_text(encoding='utf-8').split('## 用法',1)[0]
packet=read(A/'SOURCE_PACKET.json');assert all(sha(D/n)==h for n,h in packet['raw_runtime_files_sha256'].items())
checks=read(A/'CHECK_RECEIPT.json');assert checks['pytest_rc']==0 and checks['source_unchanged'] and not checks['foreign_modules']
suite=ET.parse(A/'CHECKS.xml').getroot().find('testsuite');assert int(suite.attrib['tests'])==16 and int(suite.attrib['failures'])==0 and int(suite.attrib['errors'])==0
pid=checks['job']['pid'];created=checks['job']['created']
try:assert abs(psutil.Process(pid).create_time()-created)>.02,'own E job remains'
except psutil.NoSuchProcess:pass
put(A/'ROOT_CHECK_CLEANUP.json',dict(at=now(),pid=pid,created=created,released=True,source_unchanged=True,tests=16,formal_P=0,game=0))
astra='''# Astra/xhigh #315窄源审（实际延续原代理，只读）

实际/root/astra_task178_pose_review、原gpt-6-astra/xhigh，只读，不测试/写源/游戏。主层、m_of、haz_raw、其他owner与随后反击层的分离读源成立；S1 fr与S2/命中lane均以起点0计，未见基本索引错位；朝第二怪dash的名义行全段保留原层。

P2：forum_planner3579..3580只从名义r1取lock_end，3609/3630直接用于命中及S2全变体包络。既有bounds_lo允许攻击/控制计时慢一帧（kinematics1638..1673）；名义已解锁、慢lane仍锁的一帧会提前读stack_ret，违反当前锁段原层。未证交付正例实际发生。最小修法S2/命中按自身支持lane锁止边界保留原层；边界未知的锁段行原层，补名义解锁而慢lane未解锁的局部回归。

诊断隔离缺口：3596只以行号未越界判本拍；forum_human_score.verdict会将任意行重编号0后调用_hit_branch，可能套旧候选0的边界。在线内部当前都传本拍全局号，未见该在线误用；建议显式本拍收窄上下文，外部调用默认不用。

空中入口优先a，但不能只补EntryAttack。现绑定需要来源仍处招式且几何核实例匹配，应明确返回意图来源已结束的有限入口语义再复用SWITCH执行，不伪造旧招active，不全局开DSLASH/BOUNCE_TABLE。
'''
assert not (A/'ASTRA315_REVIEW.md').exists();(A/'ASTRA315_REVIEW.md').write_text(astra,encoding='utf-8')
wa=read(O/'w3fin/RESULT.json');na=read(O/'n1fin/RESULT.json')
diff=subprocess.check_output([G,'-C',str(D),'diff','ee170d2515178c1cbddd022efd9410f08bb4a0fa',S,'--','brain',':(exclude)brain/tests/test_return_body315.py'])
dh=hashlib.sha256(diff).hexdigest()[:16];assert dh==wa['knife_diff_sha256_16']==na['knife_diff_sha256_16']
assert all(sha(D/'brain/ssbot'/n)==h for n,h in wa['source_sha256'].items())
selected=[r for r in wa['rows'] if r['f'] in (2869,2874,2881,2892,2899)]
put(A/'ROOT_EXISTING_EVIDENCE.json',dict(at=now(),source=S,ground_positive_artifact=str(O/'w3fin/RESULT.json'),artifact_sha256=sha(O/'w3fin/RESULT.json'),producer_head=wa['knife_head'],producer_dirty=wa['knife_brain_dirty'],producer_selected_sha256_match=len(wa['source_sha256']),reconstructed_five_runtime_diff_sha16=dh,scope='synthetic target placement and idle timing; no NPC reaction to new hero; commands and geometric side-slash reach, no live/side-hit count certificate',notes=wa['notes'],selected=selected,model_hits=wa['model_hits'],first_model_hurt=wa['first_model_hurt'],configuration_complete=wa['configuration_complete'],configuration_unresolved=wa['configuration_unresolved'],new_flag_unresolved='SSBOT_FORUM_TWO_RETURN_BODY' in wa['configuration_unresolved'],prefix2601_2638={'transport_sends_each':38,'first_difference':None,'B2_event_difference':None},producer_frame_scope='l2trace315 binds ws.stamp.frame; send target remains decision+2.'))
findings=[dict(priority=2,file='brain/ssbot/combat/forum_planner.py',line=3579,trigger='supported slower timing lane remains locked after nominal r1 lock_end',effect='S2 envelope/hit lane can read narrowed stack one frame early',observed_live_failure=False),dict(priority=3,file='brain/ssbot/combat/forum_planner.py',line=3596,trigger='external diagnostic reindexes another row to zero',effect='index bounds alone do not prove ownership of this tick narrowing context',known_consumer='brain/ssbot/tools/forum_human_score.py:378')]
put(A/'SOURCE_REVIEW.json',dict(at=now(),source=S,base='e137055c14294f1580bc69ad680decd786c90388',accepted=False,complete_behavior_accepted=False,processed_opus_number=315,runtime_changed=packet['changed'],independent_new_checks=16,checks=str(A/'CHECK_RECEIPT.json'),cleanup=str(A/'ROOT_CHECK_CLEANUP.json'),findings=findings,astra=str(A/'ASTRA315_REVIEW.md'),ground_path='conditional production-interface positive retained, subject to safety boundary repair',air_path='no positive; B2 return entry missing, ordinary DSLASH family off',next_decision='same179 fix timing-lane lock boundary and explicit context; prioritize finite ended-source return entry using existing B2 execution; no global DSLASH/BOUNCE_TABLE',formal_P=False,game=False))
rel='docs/plans/forum_clapper_plan.md';p=M/rel
for tree in (M,D,V):assert not git(tree,'diff','HEAD','--',rel) and (tree/rel).read_bytes()==p.read_bytes()
doc='''

#### #315合成地面返回有按键正例；慢时序锁段门与空中入口仍缺，同179收口（11-06，进度7.183）

已处理 Opus #315，runtime dfab63a4（父ee170d25）。五运行文件/一新测试，RETURN_BODY默认0；Root审完整增量及相邻goal/binder，714绑定仅五源变。E24–31/Idle实际53860/create1793960464.620201仅独跑新test_return_body315，16过9.81s、foreign0/源全同，进程真实退出；不是重复631（其两个旧失败原件保留）。analysis/task179_return315_20261106保存SOURCE_PACKET、CHECKS.xml/CHECK_RECEIPT、ROOT_CHECK_CLEANUP、ASTRA315_REVIEW和SOURCE_REVIEW accepted=false。0P/0game，无新启动许可。

默认关闭/原成功前缀有限核收：原局n1off/n1fin在2601–2638各38个transport/B2事件同；Opus364拍关闭路径逐位同记录保留。w3fin提交前HEAD是ee170且五源dirty，Root重构该五源diff指纹e11ae0dd133993e9与原件同、所记11个源SHA256也逐项同当前dfab；保留生产者原HEAD/dirty/选择性清单边界，不改写成当时已经提交dfab。当前714源码另完整绑定。w3fin新开关已解析，原configuration_complete=false的5个账本/工程worker字段原样保留，不能当正式P或live配置已过。

G1-a只另建可分离身体stack_ret，主层/m_of/危险/反击/其他owner不变；默认关，只有返回实际赢家、或原位着地后仍在可站缝的0.5s侧劈承接期且两只可见Idle/Walk才命名第二对象，构建重核、不复用旧收窄层。普通候选和CONTINUE的可撤回段才读，朝第二怪dash原层、B2/族/特殊/地图/铃行仍原层。这是有界行为候选，未签物理预测更准确；G2未加。

新增地面正例是明确合成生产接口：470右移1.5u并延后120帧、476用既有Idle片段，身体缝约5.6u；w3fin模型2869在x24.424落地，2874发A+R目标2876、后续2881/2892等地面A与侧劈动画/朝向/1.9–2.73u射程相符，owner plan；对照关时高悬/后FORCED落地、够不到侧劈。它证明该条件下落地和出刀指令可经完整policy/planner/before_send/sent，不是NPC响应新英雄的自然闭环，不把按A保持帧数充多次命中（模型ground hit未实现）。原窄缝仍在24–30步擦过被越身体右上角、窗口结束前未返回；无地面缝558候选没有预测命中，回中间entry_attack空且DSLASH族关，完整空中连续下劈正例仍无。A2圆形符文外接矩形的条件hurt误报明确列边界，不为当前扩全场模拟器。

实际Astra/xhigh按workflow仅重点审315锁段/变体保护，Root审普通接口/证据。发现安全P2：forum_planner3579仅从名义r1算lock_end，3609/3630直接用于命中和S2全变体包络；既有bounds_lo允许控制/攻击计时慢一帧，名义已解锁而慢lane仍锁时会提前读stack_ret，不能声称锁段全保原层。未证明在本正例发生，仍须同包按参与lane可靠锁止边界修；未知边界行原层，局部真实慢lane回归。另诊断隔离：仅行号未越界不能证明本拍，forum_human_score378会把任意行重编号0后_hit_branch而误用旧候选0；在线全局行号暂未见误用，但后续证据需显式当前收窄上下文，外部默认原层。新16测试没覆盖慢lane/外部重编号，不当已证明无此问题。

Sol裁空中入口选a方向，同179复用现有B2接近/下劈执行，不全局打开DSLASH/FACE_HOOK/BOUNCE_TABLE，也不新动作池。不能只给EntryAttack(stomp)：_observed_transfer_move要求source仍在相应招式，返回来源已经结束会被拒。明确有限“已观察近程招结束后的返回意图”入口、真实结束/实例/目标与当前S0/HF/在途键；来源历史只作归属，不伪造active/新前摇/免疫或放宽旧SWITCH。请求需当前air返回赢家、失效即停止新准入、已发段按原所有权；实际hit+pogo后用既有真实弹起交还重评接续，不能失败重试同Move或假造连续表。须给真实几何完整生产空中正例，包含真实模型下劈命中/弹起/下一次接续、开缝后地面意图交还；只能一次出刀时明确有限覆盖，不叫连续完成。原窄缝复用水平接近先越身体边缘再降，保留身体硬否及原全owner/后继/clock/预算。两项边界修复与入口同包完整交后才给受影响连续P，不重跑631/旧85P，不开新局；墙角打法延后、旧观察不重开、输入资源及真实清理门不变。
'''
assert '进度7.183' not in p.read_text(encoding='utf-8');p.write_text(p.read_text(encoding='utf-8')+doc,encoding='utf-8')
heads={}
for tree in (M,D,V):
    if tree!=M:(tree/rel).write_bytes(p.read_bytes())
    git(tree,'add','--',rel);git(tree,'commit','-m','docs: retain return315 ground positive and bound air-entry correction','--',rel);heads[str(tree)]=git(tree,'rev-parse','HEAD')
put(A/'PLAN_SYNC.json',dict(at=now(),heads=heads,runtime_source=S))
mail='''## seq239 / 同Task179：315地面正例有限核收；修慢lane锁段与诊断上下文，空中选a接现有B2有限返回入口

Root完整审dfab五源，714绑定仅五项变；只独跑新增test_return_body315的16项，9.81s/foreign0/源全同、E53860已退出，不重复631。SOURCE_REVIEW accepted=false、CHECK_RECEIPT/ROOT_CHECK_CLEANUP、实际Astra/xhigh窄审在analysis/task179_return315_20261106/，主计划7.183三树仅文档同步。你仍唯一源码owner；以下同179一次修完整，不再拆ACK，0P/game、无下一局许可。

地面正例保留：Root核w3fin2869着地、2874实际plan发A+R→2876及对应朝向/射程等，合成5.6u缝，按键/接口正例成立；不能把保持A帧或几何够得着算6次真实命中，ground hit模型没实现、NPC也不响应新英雄。w3fin生产者HEAD ee170/五源dirty，Root重构五源diff16 e11ae0dd133993e9匹配、原件11个SHA同当前，默认关成功前缀2601..2638各38发送/B2事件同。原metadata false账本/工程worker5字段保留，RETURN_BODY本身已解析；下一完整P/live驱动仍需实际已构造policy/账本/worker全绑定，别复用这份不完整工程清单。

必修安全P2（Astra读源，Root核原Variant支持域）：forum_planner3579..3580仅按名义r1算lock_end，3609/3630直接沿用到命中lane和S2所有时序包络。bounds_lo允许控制/攻击慢一帧，名义已解锁、慢lane仍锁时该帧会提前读stack_ret。当前16单测未覆盖，不是已证明在w3发生，但违反你承诺的“当前锁段原层”。按实际参与lane的可靠锁止边界保留原层；拿不到边界的锁段行保守原层，不盲给名义+1充所有lane证明。补一个名义解锁而实际受支持慢lane未解锁的局部回归即可，不重跑矩阵。

同时修诊断隔离：_v2_return_hit3596只row<数组长不足以证明本拍。forum_human_score.verdict378把任意行重新编号0再_hit_branch，会套用旧候选0边界。在线内部当前传全局号未见此用法，先用显式本拍候选上下文/来源绑定，外部调用默认原层，勿只靠长度；局部重编号反例即可。S1 fr与全lane起点0本身一致，主层/m_of/hazards/其他owner/随后reaction保留读源成立，不重做已对的部分。

空中选择a方向，别开全局DSLASH或BOUNCE_TABLE、FACE_HOOK，不新动作池。但不能只补EntryAttack：Root读_observed_transfer_move，source Idle已不在允许相位会拒，几何也核实例。请明确有限“已观察近程招结束后的当前返回意图”入口，再复用已有SWITCH/transfer接近和下劈执行；可给明确返回请求/来源标记，最小接口由你定。不伪造旧招active/新前摇、不重写cast_fa或时钟凑准入、不放宽普通SWITCH旧门。来源历史只作可追溯归属，不授予当前伤害豁免。绑定真实结束/实例/目标和当前S0/HF/在途键，只有当前air返回意图实际赢家才新准入，目标/姿态/状态变化撤新请求，已发有效段按原所有权走完。默认关闭候选范围保持，下一包元数据/开关同包绑齐。

完整空中正例应经真实policy/planner/B2几何/before_send/sent，并在明确合成有效模型里见下劈接触、真实模型hit+pogo→既有交还/下一次下劈接续，开地面缝后转地面意图。不要把给出stomp/一刀变成“连续下劈已完成”；表仍关，持续段须使用已有实际弹起重锚/后缀接续，不因未中而同Move无界重试。一次打不出后续则给第一个明确断点，不能把入口接不上留给自然实机。

原窄缝继续复用水平接近先过右缘再降，在真实交还点重评，保留第24–30步身体硬否、全owner/后继/原clock预算。不为凑通过缩时域或用G1替B2几何，也不加G2 ground奖励。A2矩形hurt误报只按真实圆形对应局部注明，不借机扩模拟器。已有地面正例/默认关364发/老成功前缀保留，只重核受影响增量。功能完整后一次交受影响连续P入口；仍未获新game许可，旧观察不重开。

'''
mp=B/'sol/TO_OPUS.md';tmp=mp.with_suffix('.return315.tmp');tmp.write_text(mail+mp.read_text(encoding='utf-8'),encoding='utf-8');os.replace(tmp,mp)
wp=B/'sol/OPUS_WAKE.json';w=read(wp);assert w['seq']==238;w.update(seq=239,task=179,at=now(),note='315 conditional ground command positive retained; fix nominal-vs-slower-lane lock boundary and diagnostic row context. Air path: finite ended-source return request into existing B2, no global DSLASH/BOUNCE_TABLE. Same179 complete package before P; no next live.');save(wp,w)
st=read(B/'sol/STATUS.json');st.update(at=now(),phase='RETURN315_GROUND_POSITIVE_AIR_ENTRY_AND_LOCK_FIX',current_plan='7.183',plan_progress='7.183',candidate_source=S,source_review_pending=True,source_review_file=str(A/'SOURCE_REVIEW.json'),opus315_review=str(A/'SOURCE_REVIEW.json'),astra315_review=str(A/'ASTRA315_REVIEW.md'),next_watch_ready=False,next_watch_user_authorized=False)
st['return_middle_preference']['implementation']='conditional synthesized ground landing+side-slash command positive; timing-lane boundary correction and full airborne continuation pending'
save(B/'sol/STATUS.json',st)
print(json.dumps(dict(recorded=True,new_checks=16,ground_command_positive=True,complete_behavior_accepted=False,seq=239,heads=heads,formal_P=False,game=False),ensure_ascii=False))
