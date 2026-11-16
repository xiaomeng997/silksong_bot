"""Freeze reviewed GD450, then stage two finite executor_v2 contexts. No game API."""
from pathlib import Path
from datetime import datetime,timezone
import ast,hashlib,json,runpy,shutil,subprocess

B=Path('C:/ssbot/data/m2_play/clapper_plan')
A=B/'analysis/glide_danger450_20261115'
OLD=B/'analysis/glide_jump_hold445_20261115'
R=B/'analysis/committed388_20261111'
E=B/'opus/review182/s312/r7'
W=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
ROOT=Path('C:/modeling/silksong_bot')
H='e097f60e42c518eb962782e71c0680ba543016a9'
BASE='d6a3664416ef84280b214115dc80f2b256782b32'
PARENT='8beb58acbcc6e9b6771d1315c612fba6bfca6dd1'
GIT='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
now=lambda:datetime.now(timezone.utc).isoformat()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
norm=lambda b:hashlib.sha256(b.replace(b'\r\n',b'\n')).hexdigest()
def put(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def git(*args,cwd=W):return subprocess.run([GIT,'-C',str(cwd),*args],capture_output=True,check=True).stdout

assert git('rev-parse','HEAD').decode().strip()==H
assert git('rev-parse',H+'^').decode().strip()==PARENT
assert not git('diff','HEAD','--','brain/ssbot','brain/tests/test_glide_danger383.py').strip()
s=read(B/'sol/STATUS.json')
assert not s['live_or_budget_running'] and not s['own_offline_jobs'] and not s['own_live_session']
assert not (B/'sol/performance/ACTIVE.json').exists() and not A.exists()
review=read(R/'REVIEW450.json');assert review['accepted'] and review['source']==H
A.mkdir();S=A/'source_fixed450';S.mkdir()
parent=read(OLD/'SOURCE_PACKET_FIXED.json');assert parent['source']==BASE
base=Path(parent['source_root'])
for n,h in {**parent['raw_runtime_files_sha256'],**parent['support_sha256']}.items():
    assert sha(base/n)==h,n
    dst=S/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(base/n,dst)
changes=git('diff','--name-only',BASE,H).decode().splitlines()
runtime=[n for n in changes if n.startswith(('brain/ssbot/','knowledge/'))]
assert set(runtime)=={'brain/ssbot/combat/forum_planner.py','brain/ssbot/train/forum_planner_policy.py'}
assert set(changes)==set(runtime)|{'brain/tests/test_glide_danger383.py'}
bindings=[]
for n in changes:
    data=git('show',H+':'+n);dst=S/n;dst.parent.mkdir(parents=True,exist_ok=True)
    old=dst.read_bytes() if dst.exists() else b''
    dst.write_bytes(data.replace(b'\n',b'\r\n') if b'\r\n' in old else data)
    assert norm(data)==norm((W/n).read_bytes())==norm(dst.read_bytes()),n
    bindings.append(dict(file=n,commit_lf_sha256=norm(data),fixed_raw_sha256=sha(dst)))
git('init','--quiet',cwd=S)
git('fetch','--quiet','--no-tags','--depth=1',str(W),H,cwd=S)
git('symbolic-ref','HEAD','refs/heads/codex/glide-danger450-freeze',cwd=S)
git('update-ref','refs/heads/codex/glide-danger450-freeze',H,cwd=S)
git('read-tree',H,cwd=S)
assert not git('diff','HEAD','--','brain/ssbot','knowledge',cwd=S).strip()
support=[*parent['support_sha256'],'brain/tests/test_glide_danger383.py']
packet=dict(at=now(),source=H,parent=BASE,commit_parent=PARENT,source_root=str(S),runtime_delta=runtime,
    raw_runtime_files_sha256={n:sha(S/n) for n in parent['raw_runtime_files_sha256']},
    runtime_support_files=support,support_sha256={n:sha(S/n) for n in support})
put(A/'SOURCE_PACKET_FIXED.json',packet)
review.update(source_binding=bindings,source_review_pending=False,source_root=str(S))
put(A/'SOURCE_REVIEW_FINAL.json',review);put(R/'REVIEW450.json',review)
for name in ['engineering_helpers.py','resource_background.py','RESOURCE_BACKGROUND_APPROVAL.json','entry_v4.py']:
    shutil.copy2(OLD/name,A/name)
inputs=read(OLD/'REPLAY_INPUT_BINDING.json')['files']
assert all(sha(Path(n))==h for n,h in inputs.items())
for tr in ['mh_ep38','mh_ep9']:
    trial=E/'trials'/tr;assert trial.exists()
    inputs.update({str(p):sha(p) for p in trial.rglob('*') if p.is_file() and '__pycache__' not in p.parts})
inputs[str(A/'entry_v4.py')]=sha(A/'entry_v4.py')
inputs[str(ROOT/'tmp/run_glide450_p.py')]=sha(ROOT/'tmp/run_glide450_p.py')
put(A/'REPLAY_INPUT_BINDING.json',dict(at=now(),files=inputs,
    scope='Unchanged reviewed entry_v4; recorded fixture throughB-1, own policy/sends fromB, synthetic heroB+1; no measured forcing.'))
case=read(OLD/'CASE_ON.json')
drop=('--opus-synth=','--no-force-from=','--fixture-recorded-run=','--fixture-own-from=',
      '--env=SSBOT_FORUM_GLIDE_JUMP_HOLD=','--env=SSBOT_FORUM_GLIDE_DANGER=')
flags=[x for x in case['contexts'][0]['flags'] if not x.startswith(drop)]
flags+=['--env=SSBOT_FORUM_GLIDE_JUMP_HOLD=1']
case.update(source=H,source_root=str(S),source_packet_file=str(A/'SOURCE_PACKET_FIXED.json'),source_packet_sha256=sha(A/'SOURCE_PACKET_FIXED.json'),
    source_review_file=str(A/'SOURCE_REVIEW_FINAL.json'),entry_file=str(A/'entry_v4.py'),entry_sha256=sha(A/'entry_v4.py'),
    input_binding_file=str(A/'REPLAY_INPUT_BINDING.json'),input_binding_sha256=sha(A/'REPLAY_INPUT_BINDING.json'),
    resource_helper_file=str(A/'engineering_helpers.py'),resource_helper_sha256=sha(A/'engineering_helpers.py'),
    accepted_reviews=sorted(set(case['accepted_reviews'])|set(range(446,451))))
windows=[('OPEN','mh_ep38',38,135004,135019),('FLOAT','mh_ep9',9,51210,51240)]
for arm,on in [('ON','1'),('OFF','0')]:
    contexts=[]
    for name,tr,ep,own,last in windows:
        trial=E/'trials'/tr
        cf=flags+[f'--opus-synth={own+1}',f'--no-force-from={own}',f'--fixture-recorded-run={trial/"run"}:{own-1}',
            f'--fixture-own-from={own}',f'--env=SSBOT_FORUM_GLIDE_DANGER={on}']
        contexts.append(dict(name=name,trial=str(trial),**{'from':own},last=last,flags=cf))
    put(A/f'CASE_{arm}.json',dict(case,case_id='glide_danger450_'+arm.lower(),contexts=contexts))
put(A/'P_PLAN.json',dict(at=now(),source=H,source_review_accepted=True,adapter='unchanged reviewed entry_v4/executor_v2',
    per_arm_frames=sum(z-f+1 for _,_,_,f,z in windows),
    windows=[dict(name=n,episode=ep,own_and_measure_from=f,synthetic_from=f+1,last=z) for n,tr,ep,f,z in windows],
    profile='Latest completed GJH50 profile AS1/LANDING_EXIT1/MH1/GJH1; only GD ON/OFF; old NO_NEW_GLIDE0',
    performance_budget_pass=False,game_authorized=False,
    scope='Affected finite whole-policy/tick cost, runtime classification and actual replay sends; not global scheduling, real-game acceptance or savedHP.'))
helper=runpy.run_path(str(A/'engineering_helpers.py'));resource=helper['resource_guard']();put(A/'RESOURCE_INITIAL.json',resource)
s.update(at=now(),phase='GLIDE450_SOURCE_ACCEPTED_FINITE_P_PREPARED',current_source=H,candidate_source=H,source_review_pending=False,
    last_opus_scan_number=450,last_opus_receipt_number=450,opus450_receipt=str(R/'REVIEW450.json'),pending_opus=None,
    next_phase='Sol check/finalize and two-window GD ON/OFF measure/finalize; no game permission.',
    active_implementation=dict(owner='Sol',scope='Reviewed GD source and affected finiteP',stage='Prepared, not executed',coordination_seq=381))
put(B/'sol/STATUS.json',s)
p=B/'sol/TO_OPUS.md';text=p.read_text(encoding='utf-8-sig');heading='## #450源审核收：e097f60e归Sol有限P，期间只读收信（信息，无新任务/不唤醒）'
assert heading not in text
head='# Sol → Opus 留言队列';assert text.startswith(head)
notice=f'''{heading}

攻击收伞P2已由Sol及同阶段Astra增量核同，14测试红绿和固定源证据已读，不重跑广套；累计3文件/提交/WT/新冻结hash绑定。当前由Sol用未改entry_v4/executor_v2做两个受影响窗口：ep38 OPEN16拍、ep9 FLOAT31拍，GD1/0各47拍，GJH/MH/AS/LANDING1、旧禁伞0，B起自有policy/wire、英雄B+1合成，先check/finalize再measure/finalize。

请本包源码静止；P期间不要重计算（三批出圈两法也先停计算），仅读信，既有guard照旧。此为信息，无新派工、不发wake。必要新阻挡按原通信给Sol。当前未授权游戏/新50，旧批/AA/原件不动；有限P不作预算全域或HP通过。

---

'''
p.write_text(head+'\n\n'+notice+text[len(head):].lstrip(),encoding='utf-8')
put(A/'PREPARATION.json',dict(at=now(),source=H,source_files=len(packet['raw_runtime_files_sha256']),input_files=len(inputs),
    per_arm_frames=47,resource_blockers=resource['blockers'],formal_P_not_started=True,no_game=True))
print(json.dumps(dict(source=H,source_accepted=True,runtime_files=len(packet['raw_runtime_files_sha256']),input_files=len(inputs),
    per_arm_frames=47,resource_blockers=resource['blockers'],formal_P_not_started=True,no_game=True),ensure_ascii=False))
