"""Freeze source-reviewed middle handoff and stage only its three ON/OFF P windows."""
from pathlib import Path
from datetime import datetime, timezone
import copy
import hashlib
import json
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
B=Path('C:/ssbot/data/m2_play/clapper_plan')
A=B/'analysis/middle_handoff434_20261114'
OLD=B/'analysis/air_catch428_20261114'
R=B/'analysis/committed388_20261111'
E=B/'opus/review182/s312/r6'
W=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
ROOT=Path('C:/modeling/silksong_bot')
H='8e34fb6c71a3338b7652c741b12c5048086c6ae9'
PARENT='d7cbe1a59cbee1d8fa8d40c53fc57b3ed1bd2b19'
GIT='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
now=lambda:datetime.now(timezone.utc).isoformat()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
norm=lambda data:hashlib.sha256(data.replace(b'\r\n',b'\n')).hexdigest()
def put(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def git(*args,cwd=W):return subprocess.check_output([GIT,'-C',str(cwd),*args])

assert git('rev-parse','HEAD').decode().strip()==H
assert git('rev-parse',H+'^').decode().strip()==PARENT
assert not git('diff','HEAD','--','brain/ssbot','brain/tests/test_middle_handoff.py').strip()
s=read(B/'sol/STATUS.json')
assert not s['own_offline_jobs'] and not s['live_or_budget_running'] and s['own_live_session'] is None
assert not (B/'sol/performance/ACTIVE.json').exists()
assert not A.exists()
A.mkdir();S=A/'source_fixed434';S.mkdir()
parent=read(OLD/'SOURCE_PACKET_FIXED.json');assert parent['source']==PARENT
base=Path(parent['source_root'])
for n,digest in {**parent['raw_runtime_files_sha256'],**parent['support_sha256']}.items():
    assert sha(base/n)==digest,n
    dest=S/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(base/n,dest)
all_changes=git('diff','--name-only',PARENT,H).decode().splitlines()
changes=[n for n in all_changes if n.startswith(('brain/ssbot/','knowledge/'))]
assert set(changes)=={'brain/ssbot/combat/knife_chain_air_native.py','brain/ssbot/combat/slam_play.py','brain/ssbot/train/forum_planner_policy.py'}
assert set(all_changes)==set(changes)|{'brain/tests/test_middle_handoff.py'}
bindings=[]
for n in all_changes:
    data=git('show',H+':'+n);dest=S/n;dest.parent.mkdir(parents=True,exist_ok=True)
    old=dest.read_bytes() if dest.exists() else b''
    dest.write_bytes(data.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n') if b'\r\n' in old else data)
    assert norm(data)==norm((W/n).read_bytes())==norm((E/'trees/F1'/n).read_bytes())==norm(dest.read_bytes()),n
    bindings.append(dict(file=n,commit_lf_sha256=norm(data),fixed_raw_sha256=sha(dest),author_F1_raw_sha256=sha(E/'trees/F1'/n)))
shutil.copytree(base/'.git',S/'.git')
git('fetch','--quiet','--no-tags',str(W),H,cwd=S)
git('symbolic-ref','HEAD','refs/heads/codex/middle-handoff434-freeze',cwd=S)
git('update-ref','refs/heads/codex/middle-handoff434-freeze',H,cwd=S)
git('read-tree',H,cwd=S)
assert not git('diff','HEAD','--','brain/ssbot','knowledge',cwd=S).strip()
support=list(dict.fromkeys([*parent['support_sha256'],'brain/tests/test_middle_handoff.py']))
packet=dict(at=now(),source=H,parent=PARENT,source_root=str(S),runtime_delta=changes,
            raw_runtime_files_sha256={n:sha(S/n) for n in parent['raw_runtime_files_sha256']},
            runtime_support_files=support,support_sha256={n:sha(S/n) for n in support})
put(A/'SOURCE_PACKET_FIXED.json',packet)
evidence=[]
windows=[(0,5178,5234),(22,71299,71360),(30,93175,93240)]
for ep,own,last in windows:
    rr=read(E/'r'/f'f{ep}_on'/'RESULT.json')
    assert rr.get('exception') is None
    assert not [x for x in rr.get('forced_planner_ticks',[]) if x['f']>=own]
    evidence.append(dict(episode=ep,own_from=own,engineering_synth_from=rr.get('synthetic_from'),
                         no_forcing_from_own=True,result=str(E/'r'/f'f{ep}_on'/'RESULT.json')))
review=dict(at=now(),source=H,accepted=True,delivery=434,parent=PARENT,source_binding=bindings,
            independent_source_review='Sol full runtime increment and adjacent completion/source/clock/old handoff paths read; no new P0-P2 found',
            prior_critical_review=str(R/'REVIEW432.json'),prior_critical_scope='Existing normal node D, no mid-link quote70 exception; no repeated Astra call for this bounded increment',
            author_tests=20,author_mutants=14,author_affected_files=9,author_affected_tests=278,
            root_repeated_author_tests=False,engineering_evidence=evidence,
            limitations=['engineering hero-model replay, enemy remains recorded','no prevented-HP or win-rate certification','post-hit model hurt not certified','default off','not generic T-3/T-2 prewarm'],
            source_review_pending=False,game_authorized=False)
put(A/'SOURCE_REVIEW_FINAL.json',review)
put(R/'REVIEW434.json',dict(review,stage='Source accepted; affected formal P prepared not started'))
for name in ['engineering_helpers.py','resource_background.py','RESOURCE_BACKGROUND_APPROVAL.json','entry_v4.py']:
    shutil.copy2(OLD/name,A/name)
inputs=read(OLD/'REPLAY_INPUT_BINDING.json')['files']
assert all(sha(Path(n))==h for n,h in inputs.items())
for ep,own,last in windows:
    trial=E/f'trials/tv_ep{ep}'
    inputs.update({str(p):sha(p) for p in trial.rglob('*') if p.is_file() and '__pycache__' not in p.parts})
inputs[str(A/'entry_v4.py')]=sha(A/'entry_v4.py')
put(A/'REPLAY_INPUT_BINDING.json',dict(at=now(),files=inputs,scope='Unmodified reviewed adapter/stack. Recorded fixture until B-1; own policy B; synthetic hero B+1; no measured forcing.'))
case=read(OLD/'CASE_ON.json')
flags=[f for f in case['contexts'][0]['flags'] if not f.startswith(('--opus-synth=','--no-force-from=','--fixture-recorded-run=','--fixture-own-from=','--env=SSBOT_FORUM_LANDING_EXIT=','--env=SSBOT_FORUM_AIRSTRIKE=','--env=SSBOT_FORUM_MIDDLE_HANDOFF='))]
case.update(source=H,source_root=str(S),source_packet_file=str(A/'SOURCE_PACKET_FIXED.json'),
            source_packet_sha256=sha(A/'SOURCE_PACKET_FIXED.json'),source_review_file=str(A/'SOURCE_REVIEW_FINAL.json'),
            entry_file=str(A/'entry_v4.py'),entry_sha256=sha(A/'entry_v4.py'),
            input_binding_file=str(A/'REPLAY_INPUT_BINDING.json'),input_binding_sha256=sha(A/'REPLAY_INPUT_BINDING.json'),
            resource_helper_file=str(A/'engineering_helpers.py'),resource_helper_sha256=sha(A/'engineering_helpers.py'),
            accepted_reviews=sorted(set(case['accepted_reviews']+[429,430,431,432,433,434])))
for arm,enabled in [('ON','1'),('OFF','0')]:
    contexts=[]
    for ep,own,last in windows:
        trial=E/f'trials/tv_ep{ep}'
        cf=flags+[f'--opus-synth={own+1}',f'--no-force-from={own}',f'--fixture-recorded-run={trial/"run"}:{own-1}',f'--fixture-own-from={own}',
                  '--env=SSBOT_FORUM_LANDING_EXIT=1','--env=SSBOT_FORUM_AIRSTRIKE=1','--env=SSBOT_FORUM_MIDDLE_HANDOFF='+enabled]
        contexts.append(dict(name=f'E{ep}',trial=str(trial),**{'from':own},last=last,flags=cf))
    put(A/f'CASE_{arm}.json',dict(case,case_id='middle_handoff434_'+arm.lower(),contexts=contexts))
put(A/'P_PLAN.json',dict(at=now(),source=H,source_review_accepted=True,adapter='unchanged reviewed entry_v4',
                       per_arm_frames=sum(z-a+1 for _,a,z in windows),windows=[dict(episode=e,own_and_measure_from=a,synthetic_from=a+1,last=z) for e,a,z in windows],
                       profile='current live AS1/LANDING_EXIT1 + MH ON/OFF; same source',performance_budget_pass=False,game_authorized=False))
s.update(at=now(),phase='MIDDLE434_SOURCE_ACCEPTED_P_PREPARED_LIVE_PAUSED',current_source=H,candidate_source=H,source_review_pending=False,
         pending_opus=None,last_scanned_opus=434,opus434_receipt=str(R/'REVIEW434.json'),middle434_source_review=str(A/'SOURCE_REVIEW_FINAL.json'),
         next_phase='Sol fixed executor zero-tick check/finalize then same-source three-window MH ON/OFF formal P/finalize. No game authorization.',
         active_implementation=dict(owner='Sol',scope='Reviewed middle handoff source and affected finite P',stage='P prepared, not started',formal_delivery_pending=False,coordination_seq=372))
put(B/'sol/STATUS.json',s)
p=B/'sol/TO_OPUS.md';text=p.read_text(encoding='utf-8');head='# Sol → Opus 留言队列\n\n'
notice='''## #434源审核收：8e34fb6c进入Sol三窗有限P（信息，不新派工/不唤醒）

Sol已独审3个控制源码增量及完成/真实源/时钟/旧HO邻接路径，未见本包新增P0–P2；20/14变异/278作者证据不重复跑，F1四改动文件与提交规范化哈希核同。三个工程窗动作及OWN后强制0已核，后段模型/HP局限保留，不记实机增益。默认关保持。

下一步归Sol，source_fixed434和未改的已审entry_v4、当前AS1/LANDING_EXIT1/MH开关三窗已备，先零拍启动/清理，再正式计时/清理。不重跑B或旧4窗、不新增游戏。请暂停本包重计算/再改源，P结束前只读收信；有真正阻挡可照原通信送信。无新任务，不再发wake。

---

'''
assert text.startswith(head) and '## #434源审核收：' not in text
p.write_text(head+notice+text[len(head):],encoding='utf-8')
p=ROOT/'docs/plans/forum_clapper_plan.md';t=p.read_text(encoding='utf-8');assert '### 7.370 ' not in t
t+='''

### 7.370 #434固定源8e34fb6c源审/动作核收，Sol三窗MH开关P准备（11-14）

生产D固定提交8e34fb6c在d7上，只改3个控制文件+新测试，默认MH关。Root读全增量和真实弹起来源建立、实际ground/inside完成调用、事件同拍/本局/一次性/reset、策略同游戏时钟设HO以及旧脚本选怪/closed锤/late门，未见本包新增P0–P2。20新例/14变异/278作者测试证据只核不重复；F1四文件规范化SHA与提交核同。ep0拒绝同键、ep22真完成→策略→late jump/71333模型接触、ep30同键/93210接触，OWN后强制0。工程模型敌人不响应/后段锤伤失真不变，不推HP/胜率，也不把T-3/T-2通用预热记作完成。

source_fixed434绑定728运行文件/支持文件、未改已审entry_v4和真实tv0/22/30输入；正式profile为AS1/LANDING_EXIT1，只切MH。先零拍check/finalize，再每臂185拍的三窗measure/finalize，正式B自发/模型B+1，无测量强制键；不重复旧4窗或B。SOURCE_REVIEW_FINAL、SOURCE_PACKET_FIXED、REPLAY_INPUT_BINDING、CASE_ON/OFF、P_PLAN和REVIEW434登记。当前责任已归Sol、Opus仅读P期间来信，无新派工/唤醒。源审通过不当性能预算/全域调度或新50放行，游戏授权仍用完。下一步持续做到实际计时/清理/收据结项。
'''
p.write_text(t,encoding='utf-8')
print(json.dumps(dict(source=H,source_accepted=True,runtime_files=len(packet['raw_runtime_files_sha256']),input_files=len(inputs),per_arm_frames=185,formal_P_not_started=True,no_game=True),ensure_ascii=False))
