"""Freeze reviewed #428 and stage four bounded ON/OFF formal-P contexts."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil
import subprocess

B = Path('C:/ssbot/data/m2_play/clapper_plan')
A = B/'analysis/air_catch428_20261114'
OLD = B/'analysis/landing_exit423_20261114'
R = B/'analysis/committed388_20261111'
W = Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
ROOT = Path('C:/modeling/silksong_bot')
H = 'd7cbe1a59cbee1d8fa8d40c53fc57b3ed1bd2b19'
GIT = 'C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
now = lambda: datetime.now(timezone.utc).isoformat()
read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
normsha = lambda p: hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()

def put(p, d):
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def git(*args, cwd=W):
    return subprocess.check_output([GIT,'-C',str(cwd),*args])

assert git('rev-parse','HEAD').decode().strip()==H
assert not git('diff','HEAD','--','brain/ssbot').strip()
s = read(B/'sol/STATUS.json')
assert not s['own_offline_jobs'] and not s['live_or_budget_running'] and s['own_live_session'] is None
assert not (B/'sol/performance/ACTIVE.json').exists()
# Root writes this concentrated critical acceptance only after receiving Astra's final.
assert read(ROOT/'tmp/ASTRA_ACCEPT428.json')['source_accepted'] is True
assert read(ROOT/'tmp/ASTRA_ACCEPT428.json')['adapter_accepted'] is True
assert not A.exists()
A.mkdir()
S = A/'source_fixed428'
S.mkdir()
parent = read(OLD/'SOURCE_PACKET_FIXED.json')
base = Path(parent['source_root'])
for name,digest in {**parent['raw_runtime_files_sha256'],**parent['support_sha256']}.items():
    assert sha(base/name)==digest
    dest=S/name
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(base/name,dest)
changes=[n for n in git('diff','--name-only',parent['source'],H).decode().splitlines()
         if n.startswith(('brain/ssbot/','knowledge/'))]
assert set(changes)=={'brain/ssbot/combat/air_chain.py','brain/ssbot/combat/slam_play.py','brain/ssbot/train/forum_planner_policy.py'}
for name in changes:
    dest=S/name
    data=git('show',H+':'+name)
    if b'\r\n' in dest.read_bytes():
        data=data.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
    dest.write_bytes(data)
shutil.copytree(base/'.git',S/'.git')
git('fetch','--quiet','--no-tags',str(W),H,cwd=S)
git('symbolic-ref','HEAD','refs/heads/codex/air-catch428-freeze',cwd=S)
git('update-ref','refs/heads/codex/air-catch428-freeze',H,cwd=S)
git('read-tree',H,cwd=S)
assert not git('diff','HEAD','--','brain/ssbot','knowledge',cwd=S).strip()
packet=dict(at=now(),source=H,parent=parent['source'],source_root=str(S),runtime_delta=changes,
    raw_runtime_files_sha256={n:sha(S/n) for n in parent['raw_runtime_files_sha256']},
    runtime_support_files=parent['runtime_support_files'],support_sha256={n:sha(S/n) for n in parent['support_sha256']})
put(A/'SOURCE_PACKET_FIXED.json',packet)

bindings=[]
for rel in [*changes,'brain/tests/test_slam_air_catch.py']:
    p=W/rel;q=B/'opus/review182/s312/r4/trees/C4'/rel
    assert normsha(p)==normsha(q)
    bindings.append(dict(file=str(p),sha256=sha(p),archive=str(q),archive_sha256=sha(q)))
evidence=[]
windows=[(0,5710,5770),(17,57075,57155),(19,63221,63300),(44,135662,135740)]
for ep,own,last in windows:
    p=B/f'opus/review182/s312/r4/r/c4_ep{ep}_on'
    d,m=read(p/'RESULT.json'),read(p/'CONFIGURATION_MANIFEST.json')
    old=read(B/f'opus/review182/s312/r4/r/c3_ep{ep}_on/RESULT.json')
    assert d['exception'] is None and d['synthetic_from']==own+1 and d['last']==last
    assert max(x['f'] for x in d['forced_planner_ticks'])==own-1
    assert all(normsha(S/'brain/ssbot'/n)==h for n,h in m['source_sha256'].items())
    take=lambda v:[(x['f'],x.get('keys'),x.get('owner'),x.get('hero_x'),x.get('hero_y')) for x in v['rows']]
    wire=lambda v:[(x['f'],x.get('requested')) for x in v['input_frames']]
    assert take(d)==take(old) and wire(d)==wire(old)
    evidence.append(dict(episode=ep,artifact=str(p),source_files_matched=len(m['source_sha256']),
        own_from=own,synthetic_from=own+1,fixture_max=own-1,keys_trajectory_equal_C3=True,
        model_hits=d['model_hits'],first_model_hurt=d['first_model_hurt']))
put(A/'FINAL_SOURCE_PRODUCTION_EVIDENCE.json',dict(at=now(),source=H,windows=evidence,
    scope='Existing engineering evidence only; recorded enemies counterfactual. Model hurts retained; not live HP.'))
critical=read(ROOT/'tmp/ASTRA_ACCEPT428.json')
critical.update(source_binding=bindings)
put(A/'ASTRA_REVIEW428.json',critical)
review=dict(at=now(),source=H,accepted=True,delivery=428,closed_delivery=427,
    critical_review=str(A/'ASTRA_REVIEW428.json'),source_binding=bindings,
    author_test_cases=87,author_mutants=32,author_affected=701,root_repeated_author_tests=False,
    formal_timing_completed=False,formal_timing_pass=False,full_scheduling_gate_pass=False,
    live_released=False,live_paused_by_user=True)
put(A/'SOURCE_REVIEW_FINAL.json',review)

for name in ['engineering_helpers.py','resource_background.py','RESOURCE_BACKGROUND_APPROVAL.json']:
    shutil.copy2(OLD/name,A/name)
shutil.copy2(ROOT/'tmp/air_catch427_entry.py',A/'entry_v4.py')
inputs=read(OLD/'REPLAY_INPUT_BINDING.json')['files']
assert all(sha(Path(n))==h for n,h in inputs.items())
for ep,_,_ in windows:
    trial=B/f'opus/review182/s312/r3/trials/rt_ep{ep}'
    inputs.update({str(p):sha(p) for p in trial.rglob('*') if p.is_file() and '__pycache__' not in p.parts})
inputs[str(A/'entry_v4.py')]=sha(A/'entry_v4.py')
put(A/'REPLAY_INPUT_BINDING.json',dict(at=now(),files=inputs,
    scope='Reviewed stable P stack and own recorded input until B-1. New adapter own B / synthetic B+1, no forced measured keys.'))
case=read(OLD/'CASE_ON.json')
flags=[f for f in case['contexts'][0]['flags'] if not f.startswith(('--opus-synth=','--no-force-from=',
        '--fixture-recorded-run=','--env=SSBOT_FORUM_LANDING_EXIT='))]
case.update(source=H,source_root=str(S),source_packet_file=str(A/'SOURCE_PACKET_FIXED.json'),
    source_packet_sha256=sha(A/'SOURCE_PACKET_FIXED.json'),source_review_file=str(A/'SOURCE_REVIEW_FINAL.json'),
    entry_file=str(A/'entry_v4.py'),entry_sha256=sha(A/'entry_v4.py'),
    input_binding_file=str(A/'REPLAY_INPUT_BINDING.json'),input_binding_sha256=sha(A/'REPLAY_INPUT_BINDING.json'),
    resource_helper_file=str(A/'engineering_helpers.py'),resource_helper_sha256=sha(A/'engineering_helpers.py'),
    accepted_reviews=sorted(set(case['accepted_reviews']+[425,426,427,428])))
for arm,enabled in [('ON','1'),('OFF','0')]:
    contexts=[]
    for ep,own,last in windows:
        trial=B/f'opus/review182/s312/r3/trials/rt_ep{ep}'
        context_flags=flags+[f'--opus-synth={own+1}',f'--no-force-from={own}',
            f'--fixture-recorded-run={trial/"run"}:{own-1}',f'--fixture-own-from={own}',
            '--env=SSBOT_FORUM_LANDING_EXIT=0','--env=SSBOT_FORUM_AIRSTRIKE='+enabled]
        contexts.append(dict(name=f'E{ep}',trial=str(trial),**{'from':own},last=last,flags=context_flags))
    put(A/f'CASE_{arm}.json',dict(case,case_id='air_catch428_'+arm.lower(),contexts=contexts))
put(A/'P_PLAN.json',dict(at=now(),source=H,source_review_accepted=True,
    adapter_accepted=True,adapter_guard_checks=36,per_arm_frames=sum(z-a+1 for _,a,z in windows),
    windows=[dict(episode=e,own_and_measure_from=a,synthetic_from=a+1,fixture_max=a-1,last=z) for e,a,z in windows],
    switch=[0,1],full_scheduling_gate_pass=False,game_authorized=False))
prior=read(R/'RECEIPT427.json')
prior.update(actual_author_repair_start_verified=True,formal_repair_delivery=428,repair_all_issues_closed=True,closure_source=H)
put(R/'RECEIPT427.json',prior)
put(R/'RECEIPT428.json',dict(review,stage='Source accepted; bounded formal P prepared, not yet started'))
s.update(at=now(),phase='AIR_CATCH428_SOURCE_ACCEPTED_P_PREPARED_LIVE_PAUSED',current_source=H,
    candidate_source=H,source_review_pending=False,pending_opus=None,last_scanned_opus=428,
    last_opus_scan_number=428,last_scanned_opus_number=428,last_light_opus_scan_number=428,
    latest_opus_delivery=428,last_seen_opus_number=428,last_heartbeat_opus_number=428,
    next_phase='Fixed executor zero-tick check/finalize, same-source four-window ON/OFF P/finalize. No new game authorization.',
    opus428_receipt=str(R/'RECEIPT428.json'),air_catch428_source_review=str(A/'SOURCE_REVIEW_FINAL.json'),
    active_implementation=dict(owner='Sol',scope='Reviewed re-pogo entry source and affected finite P',
        stage='Source/adapter accepted, P prepared not started',formal_delivery_pending=False,coordination_seq=367))
put(B/'sol/STATUS.json',s)
print(json.dumps(dict(source=H,source_accepted=True,runtime_files=len(packet['raw_runtime_files_sha256']),
    input_files=len(inputs),per_arm_frames=sum(z-a+1 for _,a,z in windows),no_game=True)))
