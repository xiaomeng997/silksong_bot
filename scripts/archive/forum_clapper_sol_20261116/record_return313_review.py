"""Record bounded #313 review and return one consolidated correction to the implementation owner."""
from pathlib import Path
import sys,json,datetime,os,subprocess,hashlib
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/task179_return313_20261105';M=Path('C:/modeling/silksong_bot');D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');V=Path('C:/Users/Meng/.codex/worktrees/forum-tv-prep/silksong_bot')
G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe';SOURCE='830cc00951fbaf9b39fcb2b50c6451b8bd1a53d4'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,d):
    assert not p.exists(),str(p)
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def git(p,*a):return subprocess.check_output([G,'-C',str(p),*a],text=True,encoding='utf-8').strip()
def save(p,d):
    t=p.with_suffix('.return313.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(t,p)
s=read(B/'sol/STATUS.json');assert not s['live_or_budget_running'] and not s.get('own_offline_jobs')
assert git(D,'rev-parse','HEAD')==SOURCE
mail_current=(B/'opus/TO_SOL.md').read_text(encoding='utf-8').split('## 用法',1)[0]
assert '**最新编号**：#313' in mail_current
packet=read(A/'SOURCE_PACKET.json');assert all(sha(D/n)==h for n,h in packet['raw_runtime_files_sha256'].items())
findings=[dict(priority=2,file='brain/ssbot/combat/tactics/clapper_priority.py',line=114,trigger='near attack ends while hero root is between enemy roots, but no standing body gap exists',observed='no back state; old overhead at root20 instead of seam20.75',impact='misses requested airborne middle continuation',evidence=str(A/'ROOT_L2_REPRO.json')),dict(priority=2,file='brain/ssbot/combat/tactics/clapper_priority.py',line=125,trigger='standing horizontal gap opens while hero remains airborne; gap closes again before landing',observed='clears back at hero_y9; gap recloses -> keep stance19 outside, no stomp weights',impact='false return completion and loss of airborne continuation',evidence=str(A/'ROOT_L2_REPRO.json'))]
astra='''# Astra/xhigh 同179关键假设审核（延续原代理，只读）

实际代理 /root/astra_task178_pose_review，沿用原 gpt-6-astra/xhigh。未运行测试/游戏，不写生产代码，不派新代理。结论：继续同179局部闭合，不另立全局预测包，不先做+b加统一截尾。

_tails用inst.t_end-origin推进尾模板，TAIL_KEEP_S只保留实例，不能据结束64帧后仍有占据认时钟错；近2766还存在CC_CAST归因偏差。现有facts21.7.6记录尾符文启动p95=2.67s，L2 rune_hold_s1s不是危险上界。只对2766/2800/2830记录具体实例、模板键、结束/落地时刻、anchor、query bin与来源，核原始符文生成/激活/终止。错锚修锚，已确认该实例危险终止才撤相应尾层；未知保留。

CC_EVADE在进入时才朝向英雄，所以未开始分支取决于未来启动时英雄侧。只在既有可达范围证明整个启动窗口不会换侧时收窄；未知仍双向。核t=0的起始窗口、时间膨胀和身体可达界；不把未来整段位移充当前身体、不全局启用+b。

Root两个真实L2探针已足以确认两项P2：line114根之间并不代表有地面缝；line125未实际落地即完成。已有有效攻击承诺按原所有权继续。修后给地面返回与无缝空中接续各一个真几何完整policy->最终键局部正例，保留未熄符文/方向未知反例。可明确合成有效场景，不必新开游戏等机会；4.07u空隙、静止NPC重放、几个占据点都不是整条路线安全证书。当前不进入P/游戏。
'''
assert not (A/'ASTRA313_REVIEW.md').exists();(A/'ASTRA313_REVIEW.md').write_text(astra,encoding='utf-8')
put(A/'SOURCE_REVIEW.json',dict(at=now(),source=SOURCE,base='b4615f2528edf339d0a8b9e61de21681d5910289',accepted=False,processed_opus_number=313,scope='L2 intention delta reviewed, full return behavior not achieved; no P/live gate',runtime_files=packet['runtime_files'],runtime_changed=packet['changed'],findings=findings,independent_probes=str(A/'ROOT_L2_REPRO.json'),probe_infrastructure_failure=str(A/'ROOT_PROBE_INFRA_FAILURE.json'),foreign_modules=[],formal_P_started=False,game_started=False,performance_deferred_reason='required functional branches lack successful complete production execution',astra_review=str(A/'ASTRA313_REVIEW.md'),model_disposition='local instance attribution first; no global+b or uniform tail truncation'))
trace=Path('C:/ssbot/data/m2_play/clapper_plan/opus/review179/l1_313/scnAp3_l2trace.jsonl');rows=[json.loads(x) for x in trace.read_text().splitlines()]
selected=[min((r for r in rows if 'hx' in r),key=lambda r:abs(r['t']-t)) for t in (8.5667,9.1333,9.6333)]
put(A/'ROOT_EXISTING_EVIDENCE.json',dict(at=now(),trace_sha256=sha(trace),selected=[{k:r.get(k) for k in ('n','t','hx','hy','subj','geo','fine_fam','bbox_fam','committed_only')} for r in selected],prefix_2601_2638={'transport_sends_each':38,'first_difference':None,'B2_event_difference':None},scnA0_vs_scnA={'whole_transport_sends_each':682,'first_difference':None,'scope':'recorded NPC timing delayed 60 Updates after2800; synthetic hero after divergence; not natural live evidence'},limits='Layer-point attribution identifies supports, not which swept candidate row first fails. Near2766 CC_CAST at0 vs CC_JUMP_CAST at.6 is retained, not replaced by report prose.'))
p=M/'docs/plans/forum_clapper_plan.md';rel='docs/plans/forum_clapper_plan.md'
for tree in (M,D,V):assert not git(tree,'diff','HEAD','--',rel) and (tree/rel).read_bytes()==p.read_bytes()
doc='''

#### #313意图增量未验收：两个L2状态缺口与预测占据有限归因，同179局部闭合（11-05，进度7.181）

已处理 Opus #313：刀口830cc009（父b4615f25）只改clapper_priority/决策日志两个运行文件与一个测试；Root714原运行项绑定，其他源和模型无变。Opus相关563过是其交付证据，Root未重跑；独审全部增量，两个真实L2合成入口探针foreign0/源全同。首次Root探针自己的foreign扫描把C:/ssbot/tools下stdlib误判，失败原件保留、修为仅查ssbot模块名后小探针完成；0P/0game，不算算法失败。analysis/task179_return313_20261105/保存SOURCE_PACKET、ROOT_L2_REPRO、SOURCE_REVIEW（accepted=false）和ASTRA313_REVIEW。

两个P2不允许签完整返回：clapper_priority114在近程招结束时仅hx不在两根之间才记back；H20.75/y9、根20/21.5、无地面缝的真实L2合成例只出旧overhead根20，漏接缝空中意图。125仅水平region middle+ground pose便清back；原外侧触发air back后H21.5/y9、两根20/23，另一只到28开缝即记in the standing gap、未落地便完成；再合到23时只keep/stance19且无stomp权重，退回外侧目标。应按身体可站缝区分地面/空中，完成需要实际落地证据，不能靠空中横坐标入缝；原有效攻击承诺及成功内半边前缀按所有权保持。

独立只读复核Opus已有工件：base_tr/fix1在2601–2638各38个transport发送及指定B2事件同；scnA0/scnA整个各682个已记录发送同，新增回中间意图未改变该条件路径的动作结果。原NPC相位推迟60帧后及首动作分歧后英雄属合成，不能当自然闭环。分层支持确实盖住地面/下劈区域，但几个静态点非完整落地路径认证；近2766/t8.5667实际fine的CC_CAST/c从0覆盖，CC_JUMP_CAST/c从.6s，9.1334/9.6167才有jump/c从0，报告两项已精确定因须收窄。它说明挡路层，不足以断定时钟错误或危险已消失。

按用户workflow复用实际gpt-6-astra/xhigh原代理作关键预测语义裁定，不重复Root普通源审/计算：multi_forecast._tails1487按inst.t_end-origin推进，7s实例保留不是尾危险时长；现有facts21.7.6含尾符文启动p95=2.67s，L2 rune_hold_s1s不是危险上界。不能统一截尾或全局打开+b。仅对2766/2800/2830取具体instance/template/bin/anchor/结束与落地时刻，对原始符文生成/激活/终止和真正被否候选首冲突归因；错锚修锚，生命周期确证结束才撤该实例层，未知保留。未开始Evade在进入时才朝英雄，未来英雄换侧时两向可能均有因果支持；仅现有可达范围能证明启动窗口不换侧才局部收窄CC_EVADE方向，其他情况保留。t0占据另核起始窗、时间膨胀及身体可达界，不把未来整段位移当当前身体。

同179一次反馈Opus修两个L2缺口和上述局部归因，不另立全局预测包/墙角打法，不先+b加任意1s截断。交付必须补地面返回、无缝空中连续接续各一真几何完整policy/planner/B2/before_send/sent局部正例，允许明确合成生产形状，不等自然游戏机会；保留未熄符文、方向未知、已有有效攻击承诺反例。若仍缺既有动作能力给具体最小缺口，不用L2单测/安全行0当行为通过。当前不测新P、不启动游戏；FACE_HOOK0/BOUNCE_TABLE0和原未知/输入/资源/清理门保持，313不进accepted集合，STATUS记录待修。观察局不重开，下一盘仍无许可。
'''
assert '进度7.181' not in p.read_text(encoding='utf-8');p.write_text(p.read_text(encoding='utf-8')+doc,encoding='utf-8')
heads={}
for tree in (M,D,V):
    if tree!=M:(tree/rel).write_bytes(p.read_bytes())
    git(tree,'add','--',rel);git(tree,'commit','-m','docs: record bounded return313 review and local forecast questions','--',rel);heads[str(tree)]=git(tree,'rev-parse','HEAD')
put(A/'PLAN_SYNC.json',dict(at=now(),heads=heads,runtime_source=SOURCE))
mail='''## seq237 / 同Task179：#313未验收，两个L2实证缺口及预测层局部取证一次反馈；不另立全局预测包

Root已审830cc009全部增量，714源绑定/foreign0；不重跑563、不做P或新game。当前SOURCE_REVIEW accepted=false、ROOT_L2_REPRO和ASTRA313_REVIEW在analysis/task179_return313_20261105/。实际Astra/xhigh同阶段重点裁定完毕，普通L2审阅由Root做，未重复全面审核。主计划7.181已三树仅文档同步；你继续唯一实现owner，同179一次修完整，不逐项ACK。

先修两个明确P2（无需再为触发争论开大套件）：
1. clapper_priority114只在近程招结束时hx不在两根之间才记back。H20.75/y9、根20/21.5时，近程招结束依然无地面缝，真实L2只选旧overhead根20，漏掉用户要求的接缝连续下劈。不能把两根之间等同无需姿态意图；区分真正可站身体缝，保住原宽缝内半边有效攻击前缀即可。
2. 125只水平region middle+ground pose就清back，不核真实落地。Root同场景外侧触发air back后H21.5/y9，根20/23；8到28开缝就记in the standing gap、清待返回；再到23合缝，变keep/stance19/无stomp权重。不能人在半空便算已站回中间。用实际地面/接触证据完成，开缝未落地时保留接续，重合恢复空中意图；在途有效承诺按原所有权保持。

预测层裁定（请自主推进这点局部取证，不再等用户、也不另立预测包）：不是先+b加统一截尾。_tails1487的e=inst.t_end-origin已经按年龄推进；7s只是实例保存。facts/forum21.7.6已有尾符文启动p95=2.67s，L2 rune_hold_s1s不当危险上界。原scnAp3近2766/t8.5667是CC_CAST/c从0占据，CC_JUMP_CAST/c首覆盖.6；9.1334/9.6167才jump/c从0，不能把这些合成单一已过期jump尾的定论。

只补2766/2800/2830具体实例、模板键/查询bin、结束/落地时刻、anchor/朝向，以及与真实符文生成/激活/终止的对应；同时定位一条实际被否落地/下劈候选的首冲突（静态地面4点不够）。若是错锚/相位就最小修锚/相位；若已证明该实例所有对应危险终止，才按生命周期撤相应尾层，仍活/未知保留，不砍所有尾模板。未开始CC_EVADE进入时才向英雄，方向取决于未来启动时英雄侧；只当现有reach/启动窗口证明不换侧时收窄，否则两向保留。还需核t0是否由时间膨胀、启动窗或未来整段身体盒前置产生。复用已有支撑接口，只Clapper/该家庭局部，不全局+b、无新NPC模拟器，无需大量回放或用户先看叠图。

以上同一个返回行为包收尾：真几何完整policy/planner/B2/before_send/sent中，地面返回和无缝空中接续各一个最终实际键正例（明确合成合法场景即可，不等自然机会）；保留未熄符文、未来换侧未知、有效攻击承诺的拒绝或保持反例。连续弹起表仍未验收且BOUNCE_TABLE0，不得把选stomp当连续已完成。确有最小能力缺口直接带具体证据。原2601–2638成功前缀38包/B2事件Root逐项核同；scnA0/scnA全682发送同的有限条件事实也保留。

先完成功能再给受影响连续P入口，不测尚不会落地/出刀的版本；不重做原85拍/563/全场预测或墙角新打法。没有下一盘授权，旧观察局不重开。Source313不进accepted_opus_numbers，metadata312和旧单局实际清理结论不撤销。

'''
mp=B/'sol/TO_OPUS.md';tmp=mp.with_suffix('.return313.tmp');tmp.write_text(mail+mp.read_text(encoding='utf-8'),encoding='utf-8');os.replace(tmp,mp)
wp=B/'sol/OPUS_WAKE.json';w=read(wp);assert w['seq']==236;w.update(seq=237,task=179,at=now(),note='313 not accepted: two proven L2 lifecycle gaps plus local forecast instance attribution. Astra/xhigh: no global+b/uniform1s tail truncation/new global prediction package. Finish ground and air full-path branch positives before P; no next live.');save(wp,w)
s=read(B/'sol/STATUS.json');s.update(at=now(),phase='RETURN313_CORRECTION_WITH_LOCAL_FORECAST_ATTRIBUTION',current_plan='7.181',plan_progress='7.181',candidate_source=SOURCE,source_review_pending=True,source_review_file=str(A/'SOURCE_REVIEW.json'),opus313_review=str(A/'SOURCE_REVIEW.json'),astra313_review=str(A/'ASTRA313_REVIEW.md'),next_watch_ready=False,next_watch_user_authorized=False)
save(B/'sol/STATUS.json',s)
print(json.dumps(dict(recorded=True,accepted=False,findings=2,same_task=179,mail_seq=237,heads=heads,formal_P=False,game=False),ensure_ascii=False))
