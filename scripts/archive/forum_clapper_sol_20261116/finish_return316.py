"""Close the finite #316 review and send one same-package decision; no runtime edits."""
from pathlib import Path
import datetime, hashlib, json, os, subprocess, sys
import psutil

B=Path('C:/ssbot/data/m2_play/clapper_plan')
M=Path('C:/modeling/silksong_bot')
D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
V=Path('C:/Users/Meng/.codex/worktrees/forum-tv-prep/silksong_bot')
A=B/'analysis/task179_return316_20261106'
G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
S='ac0d87f343778fa6e97fce54b0b55c9a778d8a34'
sys.path.insert(0,str(D/'brain'));sys.dont_write_bytecode=True

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,d):
    assert not p.exists(),str(p)
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def atom(p,d):
    tmp=p.with_name(p.name+'.return316.tmp')
    tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(tmp,p)
def git(r,*args):return subprocess.check_output([G,'-C',str(r),*args],encoding='utf-8').strip()

st=read(B/'sol/STATUS.json')
assert not st['live_or_budget_running'] and not st.get('own_offline_jobs')
assert read(B/'sol/OPUS_WAKE.json')['seq']==239
assert git(D,'rev-parse','HEAD')==S
for root in (M,D,V):assert not git(root,'diff','--name-only') and not git(root,'diff','--cached','--name-only')
pkt=read(A/'SOURCE_PACKET.json');chk=read(A/'CHECK_RECEIPT.json');end=read(A/'ROOT_JOB_END.json')
assert chk['pytest_rc']==0 and not chk['foreign_modules'] and chk['source_unchanged'] and end['error'] is None
assert all(sha(D/n)==h for n,h in pkt['raw_runtime_files_sha256'].items())
j=read(A/'ROOT_JOB.json')
try:alive=abs(psutil.Process(j['pid']).create_time()-j['created'])<.01
except psutil.NoSuchProcess:alive=False
assert not alive
put(A/'ROOT_CHECK_CLEANUP.json',dict(at=now(),actual_job=j,identity_exited=True,runtime_files_unchanged=714,games_started=0,formal_P_ticks=0))

from ssbot.record.recorder import RecordingReader
T=B/'sol/demos/w13_observe_bait_20261106T055356Z'
att=json.loads((T/'run/attempts_i0.jsonl').read_text().splitlines()[0])
raw=[]
for x in RecordingReader(att['recording']).states(2632,2640):
    h=x.get('hero') or {}
    raw.append(dict(f=x['f'],fc=x.get('fc'),fs=x.get('fs'),input=x.get('input'),animation=h.get('anim'),events=x.get('ev'),target=[dict(iid=e['iid'],fsms=e.get('fsms')) for e in x.get('ents',[]) if e.get('iid')==335476]))
assert 'DownSlashAlt' in json.dumps(raw) and any(x['f']==2639 and x['animation']['clip']=='DownSpikeBounce 1' for x in raw)
put(A/'RAW_DOWN_RELEASE_AND_REACTION.json',dict(at=now(),recording=att['recording'],scope='Read-only exact raw STATE2632..2640. Down released2637; actual DownSlashAlt hit+pogo2639. Same hit triggers target Idle->Dmg Attack and immediate reaction; prerecorded Idle after a synthesized hit is not a causal NPC response.',states=raw))

astra='''# Actual gpt-6-astra/xhigh focused #316 review

Reused /root/astra_task178_pose_review under the user workflow; read-only, no additional tests or source writes.

1. Prior315 lock-lane and diagnostic-context defects are closed in this delta. flags_any retains the slow attack lane; identified mode locks retain the original layer for the whole row. S2 and hit use their own rollouts; score-object identity rejects external reindexing. No new definite P2 located in this bounded review.
2. ReturnGoal is finitely accepted as an ended-event attribution entry. Original B2 geometry, send-time dash locks, other owners and hazards remain. Admission idle_no_evade=True is only optimistic screening; actual strike still needs evidence from this Run.
3. Choose required recovery (乙) plus conditional existing timeout (甲). A single absent press_now_row is not permanent impossibility. Expired support or explicit domain loss must hand back at a legal boundary with actual in-flight keys; committed strike remains. Use existing earliest68 only with causal evidence of buddy alive at this Idle ENTRY, otherwise39. Reset on new Idle/hit reaction/posture change.
4. A3 reuses prerecorded Idle after modeled hit, so it proves first modeled strike and continuation wiring only. A minimal existing post-hit reaction input/control is needed; no full NPC simulator.
5. down-release-ok is directionally accepted only with same accepted DownSlash, uncancelled active interval, and body contact; last animation clip alone is insufficient.
'''
(A/'ASTRA316_REVIEW.md').write_text(astra,encoding='utf-8')
put(A/'SOURCE_REVIEW.json',dict(at=now(),source=S,base=pkt['base'],processed_opus_number=316,accepted=False,source_delta_review_pass=True,previous315_findings_closed=True,complete_behavior_accepted=False,runtime_changed=pkt['changed'],independent_affected_checks=34,check_seconds=18.11,checks=str(A/'CHECK_RECEIPT.json'),cleanup=str(A/'ROOT_CHECK_CLEANUP.json'),astra=str(A/'ASTRA316_REVIEW.md'),first_air_strike='conditional A3 modeled hit2816 and pogo/BOUNCE handback; post-hit NPC reaction not modeled',ground_path='conditional W3 landing and side-slash sends retained, no real hit count',open_items=['No second air strike or gap-open-to-ground completion','No-strike continuation retains ownership into descent/body hurt','Idle timeout must bind buddy-at-entry, not current actor count','Post-hit recorded Idle is not causal support'],decision='same179: required legal recovery plus conditional existing buddy-at-entry Idle bound; finite local down-release correction accepted',formal_P=False,game=False,new_live_authorization=False))

plan=M/'docs/plans/forum_clapper_plan.md'
text='''

#### #316慢lane及诊断隔离修复核过；空中首刀模型接通，续接与命中后反应仍须同179闭合（11-06，进度7.184）

已处理Opus #316，runtime ac0d87f3（父ee9b735b文档，上个runtime dfab）。六运行文件/两测试；Root714绑定仅六源变，完整增量及相邻入口已审；实际E24–31/Idle48056/create1793965205.6763313独跑34受影响检查18.11s全过，foreign0/714全同、实际身份退出后清任务。未重复1667/两个旧失败，0P/0game。analysis/task179_return316_20261106保存SOURCE_PACKET、CHECK_RECEIPT、ROOT_CHECK_CLEANUP、ASTRA316_REVIEW、原始松Down/受击反应摘录与SOURCE_REVIEW：source_delta_review_pass=true，完整行为accepted=false，316不进实机accepted集合。

实际Astra/xhigh复用原代理窄审：315两项已闭合。_v2_lane_lock_end以flags_any覆盖慢出刀lane，模式锁边界不可逐lane确证时整行原层，S2/hit各取自身rollout；_v2_bound绑定实际sc对象，外部重编号默认原层。默认关RETURN_AIR只将L2当前air返回赢家的已观察结束近程招绑成ReturnRequest/ReturnGoal；来源历史不复活原招，不改cast_fa/时钟或豁免。准入还查实际S0/HF/在途键的既有冲刺锁段、越身及到达下劈证人，失效在接近合法边界交还，已承诺strike保留。准入idle_no_evade=True只是乐观起跑筛选，不能替代本Run实际出刀证明。

A3是明确合成输入：470左移2.5u，2790起拼其原始2733的新鲜Idle，476另拼原始Idle。最终2793起跑、2795既有冲刺扫描通过并越476、2812发下劈、2816模型hit470+pogo并既有BOUNCE交还；第二刀未发，续接中性下落2863模型碰伤、2870才恢复，2903开缝时已到外侧。该结果只证明首刀及接续接线，不是空中连续完成或自然闭环。特别是2816模型hit后NPC仍按原录像Idle到2859，不能以此证明第二刀的真实状态支持。W3条件地面2869落地与2874等plan侧劈按键保留；A2停钟/原窄缝Walk未起跑且发送同BODY-only，默认全关364拍与旧路径同；原成功2601..2638前缀不变，均只按其工件范围核收。

Sol同179一次裁定：乙必修，甲条件化可同时做，不是二选一。已到目标上方而证人过期/支持域明确不可能时应在真实合法交还点释放接近所有权，不能中性持有到坠落；不能因某拍暂无press_now_row就宣称永久无解，亦不能撤销已承诺strike/真实forcedbounce/未完锤尾或丢弃在途键。甲只取现有IDLE_K的有伙伴最早68帧，前提是该次Idle入口时伙伴存活有因果证据（map2.clapper的idle_buddy明确按ENTRY读取），未知仍39；新Idle重新绑定、hit反应/姿态变化使旧证据失效，不以当前len2延长。没有要求新拟合或全场NPC模型。

Root只读实际2632..2640：2632 A+Down开始DownSlash，2637/38锁存0仍DownSlash，2639/fc2238锁存0且真实DownSlashAlt命中335476、伤10并DownSpikeBounce1；同帧Idle→Dmg Attack→CloseRange后进入新招。故本地replay308的--down-release-ok默认关修正方向接受，保留同次已接受下劈、未取消有效攻击段、ACTIVE窗口/非地面/身体接触与一次命中限制，不能仅凭旧动画clip注入hit。旧输出/raw不回改、注明模型版本。新增命中后的状态须用已有反应接口或明确兼容的已录状态组合，至少给真实反应使旧证据撤回/重新准入反例；冻结旧Idle不算持续正例。

Opus仍唯一源码owner，同包完成必要恢复/条件时钟与有效生产形状的首刀→实际模型hit+pogo→下一刀或合法交还→开缝地面接续；交付前自查真实policy/planner/B2几何/before_send/sent分支，不再重复大回归或微ACK。功能闭合后才给受影响连续P；FACE_HOOK/BOUNCE_TABLE/DSLASH保持关，无新game gate、旧观察不重开，墙角新打法延后，输入/资源/全清理门不变。
'''
old=plan.read_text(encoding='utf-8-sig');assert '进度7.184' not in old
plan.write_text(old+text,encoding='utf-8')
heads={}
for root in (M,D,V):
    p=root/'docs/plans/forum_clapper_plan.md'
    if root!=M:p.write_bytes(plan.read_bytes())
    git(root,'add','--','docs/plans/forum_clapper_plan.md')
    git(root,'commit','-m','docs: record return316 entry and bound continuation recovery','--','docs/plans/forum_clapper_plan.md')
    heads[str(root)]=git(root,'rev-parse','HEAD')
put(A/'PLAN_SYNC.json',dict(at=now(),heads=heads,plan_sha256=sha(plan),runtime_unchanged=True))

mail='''## seq240 / 同Task179：316增量核过；乙为必修恢复，甲限Idle入口证据，合成命中后反应要有效

Root已处理ac0d六源，34增量检查18.11s通过、foreign0/714项全同，E48056真实退出；315慢lane锁段与外部重编号两项关闭。原实际Astra/xhigh复用窄审未定位新确定P2。主计划7.184仅文档三树同步；analysis/task179_return316_20261106保存SOURCE_REVIEW/source packet/check/cleanup/Astra/原始证据。完整行为仍accepted=false，未给P/game入口，不重复1667及两个旧失败。你仍唯一运行源码owner，同179一包继续，不需要逐项ACK。

决定：乙必修，甲条件化同时允许，两者不是互斥。续接/转移在air中已到上方却证人过期或支持域明确不能出刀时，在真实合法边界交还，保留实际锁存/在途键；不能中性占有到坠落。不要把单拍暂无press_now_row当永远无解；已承诺strike/真实forcedbounce/源锤尾等原责任不撤销、同Move禁重试与失败暴露保持。准入idle_no_evade=True仅乐观筛选，不是已证明能出刀，实际仍须本Run证明。

甲仅复用既有IDLE_K[True]最早68，但条件是该次Idle ENTRY时伙伴存活的因果证据，不能只看当前len2。map2/clapper.py:378/627/731明确idle_buddy在入口读取，未知保留39；新Idle重新绑定，hit反应/姿态变化撤旧证据。保留早Evade/真实状态时钟/几何，别全局随当前两只延长，更不新拟合。

你A3首刀2816模型hit+pogo/BOUNCE接线有限保留，不称连续成功。关键更正：hit2816后目标继续原录像Idle到2859，不是会响应这刀的新NPC状态，不能用该70帧静态Idle证明第二刀安全。Root原始2639可见hit同帧Idle->Dmg Attack->CloseRange->…->CastSlamAntic。下一有效场景优先复用已有反应接口或明确兼容的已录反应状态组合，至少给命中后撤旧证据/重新准入局部反例，不扩全场NPC模拟器；所有拼接/未建模行为明示。完整交付仍需连续接续或合法恢复、随后有缝转地面，别再用冻结反应的首刀充整包闭合。

本地--down-release-ok修正方向接受：Root实际STATE2632 A+Down开始，2637/38 latched0仍DownSlash，2639/fc2238 latched0、DownSlashAlt真hit335476伤10并DownSpikeBounce1。RAW_DOWN_RELEASE_AND_REACTION.json保存原摘录。维持同次真正接受的下劈、未取消有效攻击段、ACTIVE/非地面/双向接触/一次命中等现有检查；不能用最后clip或过期/取消攻击补hit。默认关与旧输出不动，新结果记工具hash/模型选项及NPC响应边界。

保留默认关364发送、首成功2601..2638前缀和W3地面按键正例；A2停钟与N1 Walk起跑拒绝反例保持。先完成上述同一完整行为再提供受影响连续P；仅新的更改/失败才加针对检查，不跑旧大套件。RETURN_BODY/AIR继续默认关，FACE_HOOK/BOUNCE_TABLE/DSLASH不顺带开，当前没有下一盘授权、旧STOP/观察不重开。源码/资源/输入/清理边界不变。

'''
mp=B/'sol/TO_OPUS.md';mp.write_text(mail+mp.read_text(encoding='utf-8-sig'),encoding='utf-8')
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs')
st.update(at=now(),phase='RETURN316_RECOVERY_AND_CONDITIONAL_IDLE_HANDOFF',current_plan='7.184',plan_progress='7.184',current_head=heads[str(D)],candidate_source=S,source_review_pending=True,source_review_file=str(A/'SOURCE_REVIEW.json'),opus316_review=str(A/'SOURCE_REVIEW.json'),astra316_review=str(A/'ASTRA316_REVIEW.md'),next_watch_user_authorized=False,next_watch_ready=False,active_blocker='Return air first modeled hit only: subsequent strike/legal recovery and gap-open landing remain incomplete; post-hit NPC reaction must invalidate old Idle support',next_phase='Same179 Opus completion of legal no-strike recovery and entry-bound Idle evidence; no P/game until complete package')
st['return_middle_preference']['implementation']='conditional ground command positive and first modeled air hit; full post-hit continuation/recovery and gap-open landing pending'
atom(B/'sol/STATUS.json',st)
atom(B/'sol/OPUS_WAKE.json',dict(seq=240,task=179,at=now(),note='316 delta/34 checks accepted finitely; required no-strike recovery + conditional buddy-at-Idle-entry existing bound; valid post-hit reaction evidence. Same179 complete package; no P/game.'))
put(A/'HANDOFF240.json',dict(at=now(),seq=240,task=179,heads=heads,source=S,complete_behavior_accepted=False,games_started=0,formal_P_ticks=0))
print(json.dumps(dict(review='finite delta only',checks=34,heads=heads,next_seq=240,new_P_or_game=False),ensure_ascii=False))
