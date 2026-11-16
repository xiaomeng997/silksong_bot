"""Record the single observation and its first-exit defect; no controller edits or new game."""
from pathlib import Path
import sys,json,datetime,hashlib,os,subprocess,bisect
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/w13_observe_bait_20261106T055356Z';T=B/'sol/demos/w13_observe_bait_20261106T055356Z'
M=Path('C:/modeling/silksong_bot');D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');TV=Path('C:/Users/Meng/.codex/worktrees/forum-tv-prep/silksong_bot')
G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
sys.path.insert(0,str(D/'brain'));sys.dont_write_bytecode=True
from ssbot.record.recorder import RecordingReader
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,d):
    assert not p.exists(),str(p)
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def git(root,*args):return subprocess.check_output([G,'-C',str(root),*args],text=True,encoding='utf-8').strip()
assert read(A/'ROOT_CLEANUP.json')['cleanup_verified'] and read(A/'ROOT_OBSERVATION_VERIFICATION.json')['complete']
s=read(B/'sol/STATUS.json');assert not s['live_or_budget_running'] and not s.get('own_offline_jobs')
a=json.loads((T/'run/attempts_i0.jsonl').read_text().splitlines()[0]);ds=[json.loads(x) for x in (T/'run/decisions_i0.jsonl').read_text().splitlines()];fs=[d['f'] for d in ds]
timeline=[];region=None
for st in RecordingReader(a['recording']).states(2428,3397,keys=('hero','ents','fc')):
    h=st.get('hero') or {};es=[e for e in st.get('ents') or [] if e.get('type_key')=='Song Heavy Sentry'];p=h.get('pos')
    if not p or len(es)!=2:continue
    xs=sorted(e['pos'][0] for e in es);r='left' if p[0]<xs[0] else 'right' if p[0]>xs[1] else 'between'
    j=bisect.bisect_right(fs,st['f'])-1;d=ds[j] if j>=0 else {}
    if r!=region or st['f'] in (2599,2661,2671,2692,2752,2766,2800):
        timeline.append(dict(f=st['f'],physical_fc=st.get('fc'),region_relative_to_enemy_centers=r,hero_xy=p[:2],enemies=[dict(iid=e['iid'],x=e['pos'][0],control=next((f['state'] for f in e['fsms'] if f['name']=='Control'),None)) for e in es],plan=d.get('plan'),tgt=d.get('tgt'),stance=d.get('stance'),middle=d.get('clapper_middle')))
    region=r
put(A/'ROOT_FIRST_EXIT.json',dict(at=now(),human_observation='第一次离开两怪中间是躲一个冲锤，没有回去',finding='At Slam0 f2599 still between; first root-center crossing f2671 follows DASH(L) f2661 during left Cast Slam Antic2. No stable ground return. Brief upper-air center crossing f2813..2826 is not ground occupation.',limits='enemy center relation is descriptive only, not a path-safety or available-standing-gap certificate; hold logs do not alone prove a cache defect',timeline=timeline))
put(A/'NO_AUTO_NEXT_BOUT.json',dict(at=now(),completed_bouts=1,max_bouts=1,new_bout_authorized=False,old_trial_never_reopened=True))
raw={str(p.relative_to(T)):sha(p) for p in T.rglob('*') if p.is_file()}
put(A/'ORIGINAL_FILES_SHA256.json',dict(at=now(),files=raw,source_files_unchanged=714))
plan=M/'docs/plans/forum_clapper_plan.md'
text='''

#### 单局观察已实跑并全清理；首要缺口是外出避险后的返回接续（11-05，进度7.180）

已处理 Opus #310/#311/#312，仅本次明确配置范围：runtime/execution HEAD b4615f25，OBSERVE_BOUT1/HPfloor0/FACE_HOOK0/BOUNCE_TABLE0、原7HP、seed314169、仅一盘；308/309未启用部分与原有限边界不据此全面接受。310观察/L2独核82过、311实际监督器增量18过；固定执行器唯一85拍P已清理，p50 12.6473/max18.7066ms。312仅元数据登记变化，其余714项中713运行文件与P逐字节同，真实policy配置正例complete，故复用原成本，不重复P。source_review312及本局ENGINEERING_GATE保存全部范围/证据。

新sol/demos/w13_observe_bait_20261106T055356Z实际WMI请求24992、协调器54148、worker包装25724/实际59336、场50544、game33340。只一次WMI成功调用；先前准备未创建game或启动claim，不算一局重跑。worker自己的OracleLink input.stats为0delay/jitter、HF2/2、pending0，实际TRAIN LethalBlock=block/健康，不改DLL或全程无敌。实际两目标死亡4790/4856，协议2 fight T42.503829451s，实际损6HP（3397/3612/4063各2），尾2.01213212s损0；4517一次blocked catastrophe，1HP继续到结束，无未拦致死。因此CLEAR仅保命观察结果，不能签正常生存/无伤胜利，12条damage调用也不能充12次实际扣血。

Root观察模式独立重建窗口与online逐项同、HP守恒，配置/trace/原始连续性complete、overflow0/unresolved空，trace2678tick/2824action/3006receive，raw3304连续无drop。未改原始文件；正常死亡审核原样保存在normal_mortality_audit，因4517拦致死会提前封窗而产生4项在线窗口差异，不能删除这个结果或拿它代替带observe_lethal=True的新核验。ROOT_OBSERVATION_VERIFICATION/ROOT_BEHAVIOR_AUDIT/ROOT_RAW_EVENTS保存具体分母和事实，不把覆盖/预测hit当真实动作。

用户观看后指出第一次离开中间避险后没回来。Root逐帧核：2599左怪Slam0时H20.2496仍在左15.363/右29.390之间；随后左怪跳大符文前摇Cast Slam Antic2，2661规划DASH(L)，2671/physical_fc2264横越左怪中心到外侧（H18.738/左18.963/右28.110）。2692实际起跳时H14.735，2752跳怪SlamRecover时H14.273/y13.332；2813..2826只是上空短暂横越两中心，不能称恢复中间落地站位。同期clapper_middle持续hold/readiness unknown，具体责任在L2状态或普通动作延续还待定，不能仅凭缓存日志断言。ROOT_FIRST_EXIT保存可复核帧/实际fc/目标/stance/plan/怪状态。第一优先是这段外出后的真实返回，不继续以调后撤2.5宽或堆新刀表代替它；其他三次扣血和成团回冲不稳定也保留，不先签新路线成功。

实际Launcher清理06:37:36.796Z，Root独立核24992/54148/25724/59336/50544/33340原身份全部退出，无残留game/自有helper，场worker等worker资源complete无error；registry151/instances与live空/restore_pendingfalse、golden/Prefs无差、旧DEMO原hash+mtime原样、714源全同，才解除STATUS独占。ROOT_CLEANUP与全原始hash保存。用户仅授权这一盘，本目录不重开、不自动第二盘。当前源写权清理后归Opus，同Task179只围绕首次外出→避险结束→返回可站中间的完整接续查因/最小修复；保留中间无空间和新危险时既有应对，不扩全场模型/新动作池，新的完整源再按受影响窗口核验；本观察不替代178原独立有限验收。
'''
assert '进度7.180' not in plan.read_text(encoding='utf-8')
plan.write_text(plan.read_text(encoding='utf-8')+text,encoding='utf-8')
hashes={}
for root in (M,D,TV):
    rel='docs/plans/forum_clapper_plan.md';target=root/rel
    if root!=M:
        assert not git(root,'diff','HEAD','--',rel),'concurrent plan edit'
        target.write_bytes(plan.read_bytes())
    git(root,'add','--',rel);git(root,'commit','-m','docs: record one protected w13 observation and first return defect','--',rel)
    hashes[str(root)]=git(root,'rev-parse','HEAD')
put(A/'PLAN_SYNC.json',dict(at=now(),heads=hashes,plan_sha256=sha(plan),runtime_unchanged=True))
mail='''## seq233 / 同Task179：唯一观察局已结束全清理；优先闭合首次外出后的返回，不再扩后撤模型

310/311/312本次明确OBS1/HP0/FACE0/BOUNCE0范围已核，b461唯一盘实际完成，源码714全同，真实全清理后STATUSfalse。主计划7.180三树已仅文档同步；本盘不补局/不重开。analysis/w13_observe_bait_20261106T055356Z/有ROOT_CLEANUP、ROOT_OBSERVATION_VERIFICATION、ROOT_BEHAVIOR_AUDIT、ROOT_FIRST_EXIT、ROOT_RAW_EVENTS及原始hash。原始run在同名sol/demos目录。fight42.503829451s/实际6HP、尾0、4517一次健康死亡拦截；观察CLEAR不当正常通关，12个damage调用不等于12次扣血。正常审核4项窗口差异原样保留，观察模式重建逐项同，trace/config/continuity全核无errors。

用户最新指出“第一次离开两怪中间是躲一个冲锤，没有回去”。精确raw序列：2599 Slam0时仍在中间；2661左怪Cast Slam Antic2时planner DASH(L)，2671/physical_fc2264到左外侧，2692跳怪起跳时H14.735，2752收招H14.273/y13.332。2813..2826从中间上空掠过不算恢复可站中间。clapper_middle持续hold/guide movement readiness unknown，tgt335476、stance19.56，普通计划CONTINUE，来源责任请实际定因，不从日志持久化直接推断缓存bug。ROOT_FIRST_EXIT有精确位置/状态/决策。当前优先修这一段，不能只说后撤引导跑通，也不把外侧继续砍近怪当返回完成。

你仍唯一运行源码owner，清理后可继续同179这个最小完整行为：明确此次为什么出到外侧、已发段何时结束、为何没在原安全/可达条件成立后重择回两怪中间，以及最小复用现有入口的修复。给真实policy/planner/B2几何和最终键的完整正例，含已经在外侧、返回中间有空间的情况；中间没空间/原危险未结束/新危险仍走既有应对，不能硬穿。别新增打法池/全场NPC模型、盲加优先级或重跑全部套件，保留这局实际成功攻击前缀。仅受影响生产路径与连续计时窗口入口；先一包交完整定因+必要最小修复，不逐项ACK，也不再为当前观察重做85拍P/源码审。FACE_HOOK和BOUNCE_TABLE仍0，其未验收部分不顺势启用。没有下一盘授权；待用户下一次指令。新旁支先记录，别拖住这条返回接续。

'''
mp=B/'sol/TO_OPUS.md';mp.write_text(mail+mp.read_text(encoding='utf-8'),encoding='utf-8')
wp=B/'sol/OPUS_WAKE.json';tmp=wp.with_suffix('.observation.tmp');tmp.write_text(json.dumps(dict(seq=233,task=179,at=now(),note='ONE protected observation complete+clean. Existing Task179 first external escape did not restore stable middle: ROOT_FIRST_EXIT. Fix only minimal return continuation with real production evidence; no next game, no broad model/table work.'),ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(tmp,wp)
s=read(B/'sol/STATUS.json');s.update(at=now(),phase='ONE_OBSERVATION_COMPLETE_FIRST_RETURN_FIX',current_plan='7.180',plan_progress='7.180',last_game_cleanup=str(A/'ROOT_CLEANUP.json'),last_game_root_audit=str(A/'ROOT_BEHAVIOR_AUDIT.json'),latest_actual_event_audit=str(A/'ROOT_BEHAVIOR_AUDIT.json'),latest_episode_verification=str(A/'ROOT_OBSERVATION_VERIFICATION.json'),last_game_observed_prefix_hp_loss=6,last_game_full_hp_unknown=False,next_watch_user_authorized=False,next_watch_ready=False,source_review_scope='completed ONE protected observation; no next live gate')
s['accepted_opus_numbers']=sorted(set(s['accepted_opus_numbers'])|{310,311,312});s['observation_one_bout'].update(result='protected CLEAR only',actual_hp_loss=6,lethal_vetoes=1,verification_complete=True)
tmp=B/'sol/STATUS.observation_final.tmp';tmp.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(tmp,B/'sol/STATUS.json')
print(json.dumps(dict(recorded=True,heads=hashes,mail_seq=233,no_next_bout=True),ensure_ascii=False))
