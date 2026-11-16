from pathlib import Path
import ast,datetime as dt,hashlib,importlib.util,json,os,subprocess,sys
M=Path('C:/modeling/silksong_bot');W=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');TV=Path('C:/Users/Meng/.codex/worktrees/forum-tv-prep/silksong_bot')
B=Path('C:/ssbot/data/m2_play/clapper_plan');R=B/'analysis/task179_5df8711e_20261105';S='5df8711ea04accff8c03e87560d31b53b2e87a09';GIT='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe';REL='docs/plans/forum_clapper_plan.md';PY=M/'brain/.venv/Scripts/python.exe'
oldtag='w13_walk179L2_20261106T000950Z_1263e9e3';old=B/'analysis'/oldtag;oldsource='1263e9e398859b0fa98e6d3141ac955288e05059'
now=dt.datetime.now(dt.timezone.utc).isoformat();tag='w13_guard179L3_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_5df8711e';A=B/'analysis'/tag;T=B/'sol/demos'/tag
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(root,*args):return subprocess.check_output([GIT,'-C',str(root),*args],text=True,encoding='utf-8').strip()
def write(p,d):
 assert not p.exists(),p
 p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def atomic(p,data):
 t=p.with_name(p.name+'.307.tmp');t.write_bytes(data);os.replace(t,p)
s=read(B/'sol/STATUS.json');assert not s['live_or_budget_running'] and not s.get('own_offline_jobs')
assert s['current_plan']=='7.174' and read(R/'OPUS307_RECEIPT.json')['accepted']
assert read(R/'p_v2/FINALIZED.json')['cleanup_verified'] and read(old/'ROOT_CLEANUP.json')['actual_cleanup']
assert not A.exists() and not T.exists() and git(W,'log','-1','--format=%H','--','brain/ssbot')==S
for root in (M,W,TV):assert not git(root,'status','--porcelain','--untracked-files=no')
packet=read(R/'SOURCE_PACKET.json');assert all(sha(W/n)==h for n,h in packet['raw_runtime_files_sha256'].items())
accepted=sorted(set(s['accepted_opus_numbers'])|{306,307})
sp=importlib.util.spec_from_file_location('read_old_guard307',old/'engineering_helpers.py');h=importlib.util.module_from_spec(sp);sp.loader.exec_module(h);assert not h.new_blockers(accepted)
assert not any((Path('C:/ssbot/sandbox')/n).exists() for n in ('STOP_AGENTS','HUMAN_PRACTICE'))
sys.dont_write_bytecode=True;sys.path.insert(0,str(W/'brain'))
from ssbot.tools.launcher import PrefsGuard,current_prefs,read_reg_file,prefs_diff,running_game_pids
guard=PrefsGuard.default();reg=guard.status();assert not reg.get('instances') and not reg.get('restore_pending') and not reg.get('live') and not running_game_pids()
gold=guard.verify_golden();assert gold=='fc41b9c5427b4e23ec60af1f16808a6b497507eded5704b90c9224b056ea0469' and not prefs_diff(current_prefs(guard.store),read_reg_file(guard.golden))
demo=Path('C:/ssbot/sandbox/DEMO_SOON');assert sha(demo)=='0455dd550525b4b11ed62eccb47cdfeb802a3ba0a8b0c08d30f8cc961c53cb81' and demo.stat().st_mtime_ns==1791523123325081300
assert sha(Path('C:/ssbot/game/train/BepInEx/plugins/SsOracle/SsOracle.dll'))=='ca7673dbeb8f3a061deca742aa0972f585c5284dd5328e8d2378d064509930ac'
raw=(M/REL).read_bytes();assert all((r/REL).read_bytes()==raw for r in (W,TV));lines=raw.decode('utf-8').splitlines();assert '当前进度（11-05，7.174）' in lines[2]
lines[2]='2026-10-27 起草（历史审阅与阶段规格保留）。**当前进度（11-05，7.175）：307修正的逐包入队迟到模型已核，Root独立5组逐帧与实际DLL/现有Filter一致；运行源5df及135拍P不变。迟到DASH与J同时锁存的游戏优先级尚未实测、ordinary迟L路线敏感保留；按Astra聚焦裁决另冻179-L3一局已知风险工程，验提前拒绝/真实交还和撤离，不等同安全或179完成。原首损Q1/输入/日志/资源/真实清理门全部保留，无人为延迟注入。**'
section='''

#### #307逐包入队模型核收，按明确已知风险另建179-L3单局工程（11-05，进度7.175）

307的hf_cs按实际部署QueuePlain/Push→每帧单Step修正，保留306原结果。Root独立复跑5组已保存排程，用部署同hashDLL的纯过滤器工具逐帧比较，Python新移植/现有key_guard.Filter/实际DLL三者全同；准时单包另有与hold_filter_jit一致凭据。DASH晚1时2768/69锁存、晚2时2769/70锁存，与J同帧；丢冲刺旧解释撤销。更正闭环两个变体当前源hash同/无强制planner/异常/外来，HERO2将同帧J+DASH判GLIDE，2800模型中锤仍保留。真实游戏优先级未实测；现有HeroController调用顺序先Jump后独立Dash检查、StartFloat发FSM事件，单凭这段C#不足以把谁胜出签成现场事实。未额外跑一遍准时整policy闭环，准时等价只是单包状态变换/未变业务代码的构造推论，不能虚报实测。OPUS307_RECEIPT保存有限核收口径。

Root沿ASTRA306_REVIEW作明确工程取舍：采用完整实际成本/旧接收双锚的串行情景下关键2679R/2761L/2765DASH仍准时、尾段合并HF等价；孤立历史lag压力下ordinary迟L路线敏感、J+DASH优先级/模型受伤作为已知风险，不要求重做全h2或把Opt1解释为全ordinary无伤定理。不改全局发键、不额外保持DASH、不放开air_direct弹起动画、不重测135P。原ROOT_P_AUDIT complete_scheduling_gate=false、forced/n_safe0和所有失败原件不涂绿，新工程的有限放行依据独立保存；这不是99%保证、真实输入/命中/出口证明或正式样本。

只准备一个新namespace的179-L3，runtime5df针对旧L2的滑行不看前冲时限/太晚交还作新条件改变，不重开旧1263/L1/L2或补坏局。此局主要观察新守卫是否及时拒绝或交还、实际锁存与动作是否一致以及撤离结果；整包179的走路翻越/真实交还、移动踩头、同iid第二Slam各自记机会/覆盖/成功，零机会仍未完成，178原有限验收不替代。J+DASH若自然同帧可登记动作，没机会保持未核，不人为延迟、改input配置或注入场景来凑结果。相同工程profile/seed，源/模型/脚本/新预算与合同重新绑定，真实worker必须自己的OracleLink input.stats零delay/jitter/HF2/2/pending0回执通过，measure协议2/完整配置与日志硬门保持。

原7HP、HP<=6首次受击真实Q1停止，死亡/期望键不符/>4无有效匹配/关键STATE/HP/日志/资源/真实清理失败均按原规则停；Opt1相符晚<=2仍分同键/换键、覆盖不证明动作，不新增“晚1即停”。同因未修不重跑，新的失败要定位后另定条件，tail另账。Sol新数据脚本仅从已核L2生命周期替换namespace/source/阶段并作逆向等价，先同步main/刀口/TV后冻结刀口HEAD到真实全清理。游戏前原子STATUStrue带实际PID、5s静止、30s刷新和原资源/STOP/活动锁/无双起门；途中只读收信，核心Windows进程不操作。唯有实际worker/场/game/golden/Prefs/旧DEMO/registry全核后false；用户无人值守授权不变。
'''
data=('\n'.join(lines).rstrip()+section).encode('utf-8');atomic(M/REL,data);git(M,'add','--',REL);git(M,'commit','-m','docs: accept corrected input model and bind one bounded engineering observation')
heads={str(M):git(M,'rev-parse','HEAD')}
for root in (W,TV):
 atomic(root/REL,data);git(root,'add','--',REL);git(root,'commit','-m','docs: sync corrected input model and known-risk engineering scope');heads[str(root)]=git(root,'rev-parse','HEAD')
A.mkdir()
for name in ('engineering_helpers.py','resource_background.py','RESOURCE_BACKGROUND_APPROVAL.json'):(A/name).write_bytes((old/name).read_bytes())
src=(old/'trial.py').read_text(encoding='utf-8-sig');new=src.replace(oldtag,tag);assert new.replace(tag,oldtag)==src;ast.parse(new);(A/'trial.py').write_text(new,encoding='utf-8')
src=(old/'run_unattended.py').read_text(encoding='utf-8-sig');new=src.replace(oldsource,S).replace('WALK179_L2','WALK179_L3');assert new.replace(S,oldsource).replace('WALK179_L3','WALK179_L2')==src;ast.parse(new);(A/'run_unattended.py').write_text(new,encoding='utf-8')
write(A/'SCRIPT_PORT_RECEIPT.json',{'at':now,'source':S,'origin':str(old),'trial_inverse_exact':True,'coordinator_inverse_exact':True,'helpers_byte_equal':True,'syntax_valid':True,'old_trials_changed':False})
draft=json.loads(json.dumps(read(old/'TRIAL_CONFIG_DRAFT.json')).replace(oldtag,tag).replace(oldsource,S));draft.update(purpose='179-L3 one known-risk observation of timely transfer refusal/real handback and retreat; package179 walking goals separately',coverage_target='Early guard/real handback/retreat/input-action correspondence; walking-vault/moving-stomp/new same-iid Slam each opportunity ledger; no forced J+DASH probe;178 prior finite accepted')
write(A/'TRIAL_CONFIG_DRAFT.json',draft)
accept={'at':now,'planned_id':'179-L3','source':S,'execution_head':heads[str(W)],'trial':str(T),'primary_observation':'timely transfer rejection/real handback, actual latch-to-action and retreat outcome',
 'package179_still_required':'walking-target vault and true handback;0opportunity remains uncovered','auxiliary':['moving Walk-supported strike','same-iid secondSlam','natural J+DASH only if it happens'],
 'task178':'prior finite acceptance unchanged; noR1','known_risks':['ordinary delayedL conditional body collision','sameframe lateDASH/J modeledGLIDE priority not live-certified','conditional NPC and postoldloss pause limit','forced/n_safe0 retained'],
 'limits':'exactly one new namespace,7HP/firstlossQ1/death/keymismatch/>4withoutvalidmatch/log/resource/actualcleanup; no replacement/injection','not_formal_sample':True}
write(A/'ACCEPTANCE.json',accept)
disposition={'at':now,'source':S,'accepted_for':'one bounded known-risk engineering observation only','source_review':str(R/'SOURCE_REVIEW.json'),'P':str(R/'p_v2/ROOT_P_AUDIT.json'),'input_model_receipt':str(R/'OPUS307_RECEIPT.json'),'focused_astra':str(R/'ASTRA306_REVIEW.md'),
 'original_scheduling_false_preserved':True,'blanket_late1_2_injury_free_claim':False,'adopted_serial_key_edges_timely':True,'extreme_singlelag_ordinary_risk_accepted':True,'actual_priority_unknown':True,'physical_safety_certified':False,'engineering_budget_gate':True}
write(A/'ENGINEERING_DISPOSITION.json',disposition)
gate=read(old/'ENGINEERING_GATE.json');gate.update(at=now,source=S,execution_head=heads[str(W)],source_packet=str(R/'SOURCE_PACKET.json'),source_review=305,accepted_opus_numbers=accepted,planned_id='179-L3',p_scope=str(R/'p_v2/ROOT_P_AUDIT.json'),budget_scope='135 affected completeP + corrected307 due-batch and knownrisk disposition; inherited unchanged paths provenance; no future timing guarantee',known_limits='known ordinary stress sensitivity and unknown actual J/DASH precedence retained; firstloss-limited engineering, not safe-exit/whole179 certificate')
for p in [R/'SOURCE_PACKET.json',R/'SOURCE_REVIEW.json',R/'CHECKS.xml',R/'ADAPTER_REVIEW.json',R/'p_v2/ROOT_P_AUDIT.json',R/'p_v2/FINALIZED.json',R/'ASTRA306_REVIEW.md',R/'OPUS307_RECEIPT.json',R/'oracle_input306/ROOT_ORACLE306_MISMATCH.json',B/'sol/performance/checks/20261105_task179_5df8711e/FINALIZED.json',A/'SCRIPT_PORT_RECEIPT.json',A/'run_unattended.py',A/'resource_background.py',A/'RESOURCE_BACKGROUND_APPROVAL.json',A/'ACCEPTANCE.json',A/'ENGINEERING_DISPOSITION.json']:
 gate['evidence'][str(p)]=sha(p)
assert all(sha(Path(p))==h for p,h in gate['evidence'].items())
write(A/'ENGINEERING_GATE.json',gate)
subprocess.run([str(PY),'-X','utf8','-B',str(A/'trial.py')],cwd=W,check=True)
write(A/'ROOT_PREFLIGHT_STATIC.json',{'at':now,'source':S,'heads':heads,'source_files':len(packet['raw_runtime_files_sha256']),'registry':reg,'games':[],'golden_sha256':gold,'prefs_diff':[],'old_demo_sha256':sha(demo),'old_demo_mtime_ns':demo.stat().st_mtime_ns,'source_and_lifecycle_bound':True,'game_started':False})
s.update(at=now,phase='WALK179_L3_PREPARED',current_plan='7.175',current_head=heads[str(W)],current_plan_head=heads[str(W)],accepted_opus_numbers=accepted,
 pending_opus='seq226 Root knownrisk179L3 onebout prepared; source/index static, readonly duringgame, no implementationtask',active_blocker='none for one knownrisk179L3 only; live goals/priority remain unverified',next_phase='L3 lastresourcepreflight and detached singlecoordinator',next_trial=str(T),next_watch_ready=True,next_watch_user_authorized=True,engineering_gate=str(A/'ENGINEERING_GATE.json'),opus307_receipt=str(R/'OPUS307_RECEIPT.json'))
atomic(B/'sol/STATUS.json',(json.dumps(s,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
letter='''## #307有限核收，按已知风险只准备新179-L3一局；源码静止（seq226）

Root独立五组保存排程逐帧核hf_cs/现有Filter/同hash部署DLL全同；更正模型sourcehash当前同、无强制/异常/外来。收据analysis/task179_5df8711e_20261105/OPUS307_RECEIPT。DASH并未丢，和J同帧后的真实优先级仍未知；旧2763晚1路线敏感、模型hurt/forced/n_safe0保留。准时整policy未额外E0重放，单包组件构造等价不冒称实测。

按原Astra聚焦裁决，Root接受这些孤立历史lag下ordinary风险用于一次首损停止工程，不要求全h2迟1/2模型无伤，不改全局输入/不扩大air_direct/不重测135P；原scheduling false不涂绿。计划7.175已同步，刀口HEAD {head}，运行5df不变，新namespace {tag}。工程只验及时拒绝/真实交还、输入动作和实际撤离；整包walking-vault/移动踩头/同iid第二Slam仍各记真实机会，0机会不完成；178旧有限验收不变。无人为迟到注入，同帧J/DASH只自然机会登记，没遇到仍未知。

新合同/新预算/source/P/307/已知风险取舍和原输入/7HP首损Q1/日志/资源/清理全绑定，Sol做最后资源核后才启动一次。刀口HEAD现在冻结到真实清理；你无新实现任务，STATUStrue时只读、停重活，不用ACK/唤醒。旧L1/L2/306原件不动，不重开。原Windows核心进程/STOP/Opt1/期望键及所有严门保持。

'''.format(head=heads[str(W)],tag=tag)
mail=B/'sol/TO_OPUS.md';atomic(mail,(letter+mail.read_text(encoding='utf-8-sig')).encode('utf-8'))
atomic(B/'sol/OPUS_WAKE.json',(json.dumps({'seq':226,'at':now,'task':179,'note':'307 corrected model accepted finite. One knownrisk179L3 prepared under unchanged source/strictgates; source/index freeze and readonly duringgame, no implementation/ACK.'},ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
write(B/'sol/work_packages/task179/LIVE179_L3_BINDING.json',{'at':now,'tag':tag,'source':S,'analysis':str(A),'trial':str(T),'execution_head':heads[str(W)],'game_started':False})
print(json.dumps({'tag':tag,'analysis':str(A),'trial':str(T),'head':heads[str(W)],'plan':'7.175','prepared':True,'game_started':False},ensure_ascii=False))
