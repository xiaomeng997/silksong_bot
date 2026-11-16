"""Fold the user's airborne-middle preference into the active Task179 specification."""
from pathlib import Path
import json,os,datetime,subprocess
B=Path('C:/ssbot/data/m2_play/clapper_plan');M=Path('C:/modeling/silksong_bot');D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');TV=Path('C:/Users/Meng/.codex/worktrees/forum-tv-prep/silksong_bot')
G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def git(root,*args):return subprocess.check_output([G,'-C',str(root),*args],text=True,encoding='utf-8').strip()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs')
rel='docs/plans/forum_clapper_plan.md';p=M/rel
for root in (M,D,TV):assert not git(root,'diff','HEAD','--',rel),'concurrent plan edit'
for root in (M,D,TV):assert (root/rel).read_bytes()==p.read_bytes(),'plans diverged'
text=p.read_text(encoding='utf-8')
old='当前源写权清理后归Opus，同Task179只围绕首次外出→避险结束→返回可站中间的完整接续查因/最小修复；保留中间无空间和新危险时既有应对，不扩全场模型/新动作池，新的完整源再按受影响窗口核验；本观察不替代178原独立有限验收。'
new='当前源写权清理后归Opus，同Task179只围绕首次外出→避险结束→返回两怪中间的完整接续查因/最小修复。用户随后明确：躲完近程招，两怪中间有地面空隙就落地平砍；没有地面空隙就回到两怪之间的空中连续下劈，等它们让开，出现可站空隙再落地砍。因此地面无空隙不能直接把目标降为留在外侧等待；中间目标同时允许地面与空中姿态，不能强迫先落地才返回，也不把短暂从中间上空掠过当完成。L2指定回中间及姿态意图，动作层复用既有接近/下劈/真实弹起接续；当前未结束危险、真实命中/动作可行性、在途已发段与输入门保持，不能把无地面空隙当作任意空中路线的安全证明。此为待实现验收规格，不声称连续下劈或未核连续表已上线；FACE_HOOK/BOUNCE_TABLE仍按原审阅范围保持关闭，不扩全场模型/新动作池，新的完整源再按受影响窗口核验；本观察不替代178原独立有限验收。'
assert text.count(old)==1
p.write_text(text.replace(old,new),encoding='utf-8')
heads={}
for root in (M,D,TV):
    if root!=M:(root/rel).write_bytes(p.read_bytes())
    git(root,'add','--',rel);git(root,'commit','-m','docs: clarify airborne middle return when ground gap is closed','--',rel)
    heads[str(root)]=git(root,'rev-parse','HEAD')
mail='''### 同seq233 / 同Task179 用户补充：地面无空隙时回中间连续下劈，等怪分开

用户原话：“躲完近程招，如果两怪中间没有空隙的话，在两怪中间下劈，等怪让开”。这条立即并入当前首次外出后返回接续包，不另立任务/不逐项ACK。

返回目标分两种姿态：有地面空隙→回中间落地平砍；无地面空隙→回到两怪之间的空中连续下劈，等两怪分开，有可站空隙再落地。不能再因地面没缝就默认留在外侧或等怪收招后继续外侧砍，也不要求先落地才算可返回。L2给回中间+地面/空中意图，动作层复用既有接近/下劈/弹起接续，不复制新动作池；中间不是锁死两怪根坐标中点，需实际下劈可达/命中范围。当前未结束危险、已发承诺段、实际命中/保护及输入门保持，不能由无缝推出空中任意路线安全。

交付同一个完整返回行为正例，补一个无地面缝→实际回中间下劈→等怪分开→可落地接平砍的分支证据；若既有动作接口不支持，先明确具体最小缺口，不假装BOUNCE_TABLE0也已有完整连续表。当前FACE_HOOK0/BOUNCE_TABLE0仍保持，不因这条战术要求启用尚未审核的表。不重复原85拍P/大套件，不增加游戏，源改后只交受影响路径与窗口。主计划7.180已原位更正相应规格，三树仅文档同步。

'''
mp=B/'sol/TO_OPUS.md';txt=mp.read_text(encoding='utf-8');assert '### 同seq233 / 同Task179 用户补充：地面无空隙时' not in txt
tmp=mp.with_suffix('.middle.tmp');tmp.write_text(mail+txt,encoding='utf-8');os.replace(tmp,mp)
wp=B/'sol/OPUS_WAKE.json';wake=read(wp);assert wake['seq']==233
wake.update(seq=234,at=now(),task=179,note='Same Task179 user clarification: after near-attack escape, return between monsters; ground gap open => side slash, closed => stay airborne between and repeat downslash until they separate. Fold into current return package; no new game or unreviewed table enablement.')
tmp=wp.with_suffix('.middle.tmp');tmp.write_text(json.dumps(wake,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(tmp,wp)
st=read(B/'sol/STATUS.json');st.update(at=now(),return_middle_preference={'ground_gap_open':'return between, land and side slash','ground_gap_closed':'return airborne between, repeat downslash until a ground gap opens','implementation':'pending in active Task179','live_authorization_added':False})
tmp=B/'sol/STATUS.middle.tmp';tmp.write_text(json.dumps(st,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(tmp,B/'sol/STATUS.json')
print(json.dumps({'recorded':True,'same_task':179,'wake':234,'docs_heads':heads,'controller_changed':False,'game_started':False},ensure_ascii=False))
