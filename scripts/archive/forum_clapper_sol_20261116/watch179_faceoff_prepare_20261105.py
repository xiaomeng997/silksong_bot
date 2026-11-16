from pathlib import Path
import ast,datetime as dt,hashlib,importlib.util,json,os,subprocess,sys
B=Path('C:/ssbot/data/m2_play/clapper_plan');M=Path('C:/modeling/silksong_bot')
W=Path('C:/Users/Meng/.codex/worktrees/forum-watch-approved-5df/silksong_bot');DEV=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
S='5df8711ea04accff8c03e87560d31b53b2e87a09';GIT='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
OLD=B/'analysis/w13_guard179L3_20261106T012400Z_5df8711e';R=B/'analysis/task179_5df8711e_20261105';PY=M/'brain/.venv/Scripts/python.exe'
now=dt.datetime.now(dt.timezone.utc).isoformat();tag='w13_watch_faceoff_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_5df8711e';A=B/'analysis'/tag;T=B/'sol/demos'/tag
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def atomic(p,b):
 q=p.with_name(p.name+'.watch.tmp');q.write_bytes(b);os.replace(q,p)
def put(p,d):
 assert not p.exists(),p
 p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def git(*a):return subprocess.check_output([GIT,'-C',str(W),*a],text=True,encoding='utf-8').strip()
s=read(B/'sol/STATUS.json');assert not s['live_or_budget_running'] and not s.get('own_offline_jobs')
assert git('rev-parse','HEAD')==S and not git('status','--porcelain','--untracked-files=no')
A.mkdir();packet=read(R/'SOURCE_PACKET.json');fixed=[]
for n,h in packet['raw_runtime_files_sha256'].items():
 p=W/n;raw=p.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=h:
  lf=raw.replace(b'\r\n',b'\n');choices=(lf,lf.replace(b'\n',b'\r\n'))
  chosen=next((x for x in choices if hashlib.sha256(x).hexdigest()==h),None)
  assert chosen is not None,('unreviewed source',n)
  p.write_bytes(chosen);fixed.append(n)
assert not git('diff','HEAD','--','brain/ssbot','knowledge')
assert all(sha(W/n)==h for n,h in packet['raw_runtime_files_sha256'].items())
put(A/'SOURCE_PACKET.json',{**packet,'at':now,'source_root':str(W),'scope':'isolated exact same reviewed710 bytes, FACE_HOOK0 watched engineering; not new308source'})
draft=read(OLD/'TRIAL_CONFIG_DRAFT.json');draft=json.loads(json.dumps(draft).replace(OLD.name,tag))
draft['environment']['SSBOT_FORUM_CHAIN_FACE_HOOK']='0';draft.update(source_pending=S,purpose='User requested one watched w13 bout; isolated reviewed5df with known-failed cross-target facehook disabled',demonstration=True,user_present_request='太费劲了。你再开一盘我看看',coverage_target='watched existing non-facehook behavior; not new highhook/bounce-table certification')
for name in ('engineering_helpers.py','resource_background.py','RESOURCE_BACKGROUND_APPROVAL.json'):(A/name).write_bytes((OLD/name).read_bytes())
helper_spec=importlib.util.spec_from_file_location('watch_preflight_helpers',A/'engineering_helpers.py');helper=importlib.util.module_from_spec(helper_spec);helper_spec.loader.exec_module(helper)
missing=helper.new_blockers(s['accepted_opus_numbers']);nums=[int(x.split('|')[1].strip()) for x in missing]
assert set(nums)<={308},nums
put(A/'REVIEW_APPLICABILITY.json',{'at':now,'unaccepted_numbers':nums,'not_applicable':{'308':'Only targeted facehook lock/retreat failure; source is original reviewed5df with FACE_HOOK0 so facehook/early-jump branches unreachable'},'accepted_308':False,'all_other_affected_reviews_required':True})
src=(OLD/'trial.py').read_text(encoding='utf-8-sig');code=src.replace(OLD.name,tag).replace(str(DEV).replace('\\','/'),str(W).replace('\\','/'))
assert code.replace(tag,OLD.name).replace(str(W).replace('\\','/'),str(DEV).replace('\\','/'))==src
(A/'trial.py').write_text(code,encoding='utf-8');ast.parse(code)
src=(OLD/'run_unattended.py').read_text(encoding='utf-8-sig')
oldcheck="assert d['current_source']=='5df8711ea04accff8c03e87560d31b53b2e87a09' and not d['source_review_pending']"
newcheck="assert d.get('watch_source')=='5df8711ea04accff8c03e87560d31b53b2e87a09' and d.get('watch_contract_ready') is True"
assert src.count(oldcheck)==1
co=src.replace(oldcheck,newcheck).replace('UNATTENDED_WALK179_L3_LIVE','WATCH179_FACEOFF_LIVE')
(A/'run_unattended.py').write_text(co,encoding='utf-8');ast.parse(co)
put(A/'SCRIPT_PORT_RECEIPT.json',{'at':now,'source':S,'origin':str(OLD),'trial_lifecycle_inverse_exact':True,'changes':'namespace and isolated CODE only; coordinator validates independent watch contract, preserving development source_review_pending','line_endings_restored_to_reviewed_bytes':fixed,'no_runtime_algorithm_edit':True})
put(A/'TRIAL_CONFIG_DRAFT.json',draft)
put(A/'ACCEPTANCE.json',{'at':now,'scope':'one watched engineering bout only','source':S,'facehook':False,'old_failures_reopened':False,'changed_condition':'SSBOT_FORUM_CHAIN_FACE_HOOK=0 removes L3 hooked flight/forcedbounce failure path','stopping':'original7HP, first any loss HP<=6 actualQ1,1episode,death/key/criticallog/resource/cleanup gates','not_formal_or_repaired_feature_acceptance':True})
put(A/'ENGINEERING_DISPOSITION.json',{'at':now,'authority':'fresh human request in current turn to open one bout for viewing; user informed isolated reviewed build and facehook off','source_review':str(R/'SOURCE_REVIEW.json'),'P_provenance':str(R/'p_v2/ROOT_P_AUDIT.json'),'original_scheduling_false_preserved':True,'new_P_claim':False,'scope':'bounded watched engineering with already-reviewed source and targeted-hook branch disabled; remaining ordinary risks retained','engineering_budget_gate':True,'physical_safety_certified':False})
put(A/'WATCH_PROFILE_REVIEW.json',{'at':now,'source':S,'reviewed710_exact':True,'FACE_HOOK':'0','path_proof':['NativeManualAirChain.reset reads SSBOT_FORUM_CHAIN_FACE_HOOK and cfg FACE_HOOK false','transfer_face_hook returns before model/CLAW when cfg false','early_jump construction and dispatch guarded by same cfg','fixed_hook0/fast_hook0 retained'],'runtime_changes':[],'source_review_308_pending_independently':True,'purpose':'one separately bound watched engineering, not repeat failed facehook condition'})
gate=read(OLD/'ENGINEERING_GATE.json');gate.update(at=now,source=S,execution_head=S,source_packet=str(A/'SOURCE_PACKET.json'),planned_id='179-WATCH-FACEOFF',authorization={'text':'太费劲了。你再开一盘我看看','scope':'one watched fresh namespace with known failed facehook disabled, explicit update in commentary'},known_limits='current developer source308 remains unaccepted and unused; no facehook/highhook/online-table success claim; original ordinary stress risks retained')
gate['evidence']={str(p):sha(p) for p in [R/'SOURCE_REVIEW.json',R/'p_v2/ROOT_P_AUDIT.json',R/'p_v2/FINALIZED.json',R/'OPUS307_RECEIPT.json',OLD/'ROOT_CLEANUP.json',A/'SOURCE_PACKET.json',A/'WATCH_PROFILE_REVIEW.json',A/'REVIEW_APPLICABILITY.json',A/'SCRIPT_PORT_RECEIPT.json',A/'ACCEPTANCE.json',A/'ENGINEERING_DISPOSITION.json',A/'run_unattended.py',A/'resource_background.py',A/'RESOURCE_BACKGROUND_APPROVAL.json']}
put(A/'ENGINEERING_GATE.json',gate)
sys.dont_write_bytecode=True;sys.path.insert(0,str(W/'brain'))
from ssbot.tools.launcher import PrefsGuard,current_prefs,read_reg_file,prefs_diff,running_game_pids
guard=PrefsGuard.default();reg=guard.status();assert not reg.get('instances') and not reg.get('restore_pending') and not reg.get('live') and not running_game_pids()
assert guard.verify_golden()=='fc41b9c5427b4e23ec60af1f16808a6b497507eded5704b90c9224b056ea0469' and not prefs_diff(current_prefs(guard.store),read_reg_file(guard.golden))
demo=Path('C:/ssbot/sandbox/DEMO_SOON');assert sha(demo)=='0455dd550525b4b11ed62eccb47cdfeb802a3ba0a8b0c08d30f8cc961c53cb81' and demo.stat().st_mtime_ns==1791523123325081300
assert not any((demo.parent/x).exists() for x in ('STOP_AGENTS','HUMAN_PRACTICE'))
assert sha(Path('C:/ssbot/game/train/BepInEx/plugins/SsOracle/SsOracle.dll'))=='ca7673dbeb8f3a061deca742aa0972f585c5284dd5328e8d2378d064509930ac'
subprocess.run([str(PY),'-X','utf8','-B',str(A/'trial.py')],cwd=W,check=True)
put(A/'ROOT_PREFLIGHT_STATIC.json',{'at':now,'source':S,'head':git('rev-parse','HEAD'),'source_files':710,'face_hook':0,'registry':reg,'prefs_diff':[],'games':[],'old_demo_sha256':sha(demo),'old_demo_mtime_ns':demo.stat().st_mtime_ns,'source_and_lifecycle_bound':True,'game_started':False})
note='''### 同seq229：观看单局用隔离已审5df/FACE_HOOK0；当前事故先纠正战术适用域

用户最新明确：L3当时两怪同侧挤着、英雄外侧，这不适用“夹中后翻另一怪”；不要以把错误翻怪路线修到能通过为目标。先纠正L2适用条件，成团压角起跳后向开阔侧撤；仅夹中才考虑翻走路怪，仍保留中间能站则留中间。暂停继续为这个错误场景扩救场/包络规模；已做工件保留，通用不可取消段检查只按正确动作域必要项处理，不为本案堆候选。高位钩与同目标有限表按原计划在正确场景复用，原源审/输入/危险/时钟门不削弱。

用户又明确要求现在再开一盘观看。Root使用新隔离worktree forum-watch-approved-5df，精确710字节已审5df，FACE_HOOK=0，停用导致L3失败的换怪飞针入口，其他既有动作保留；不是你的当前半改树/308修复版，不重开原停止局。一个新namespace、原7HP/首损Q1/measure2/全部输入资源清理门，Root将原子STATUStrue等5s/刷新30s后独占运行；你看到true请暂停重计算，只读收信，不操作核心进程。无须ACK，false前不跑重活。当前开发源review_pending保持，watch_contract单独绑定，不把308签通过；Root不会改你的源文件或索引。

'''
mail=B/'sol/TO_OPUS.md';atomic(mail,(note+mail.read_text(encoding='utf-8-sig')).encode('utf-8'))
s=read(B/'sol/STATUS.json');assert not s['live_or_budget_running'] and not s.get('own_offline_jobs')
s.update(at=now,phase='WATCH179_FACEOFF_PREPARED',watch_source=S,watch_code=str(W),watch_trial=str(T),watch_analysis=str(A),watch_contract_ready=True,next_watch_user_authorized=True,watch_request='太费劲了。你再开一盘我看看',watch_face_hook=0,watch_scope='separate exact reviewedsource, oldknown facehook failure disabled; new308 source remains pending')
atomic(B/'sol/STATUS.json',(json.dumps(s,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
put(B/'sol/work_packages/task179/WATCH_FACEOFF_BINDING.json',{'at':now,'tag':tag,'analysis':str(A),'trial':str(T),'code':str(W),'source':S,'execution_head':S,'face_hook':0,'game_started':False})
print(json.dumps({'tag':tag,'analysis':str(A),'trial':str(T),'source':S,'source_exact710':True,'prepared':True,'game_started':False},ensure_ascii=False))
