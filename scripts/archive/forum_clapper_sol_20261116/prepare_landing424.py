"""Freeze accepted #424 and prepare unchanged reviewed entry_v3 finite P."""
import datetime,hashlib,json,shutil,subprocess
from pathlib import Path

B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/landing_exit423_20261114';OLD=B/'analysis/walk_rule418_20261113';R=B/'analysis/committed388_20261111'
W=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');S=A/'source_fixed424'
G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe';H='a81a2597d2e7f04498a7300f14e910ab3259d499'
read=lambda p:json.loads(Path(p).read_text('utf-8-sig'));sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();normsha=lambda p:hashlib.sha256(Path(p).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def put(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf-8')
def git(*args,cwd=W):return subprocess.check_output([G,'-C',str(cwd),*args])

assert git('rev-parse','HEAD').decode().strip()==H and not git('diff','HEAD','--','brain/ssbot').strip()
state=read(B/'sol/STATUS.json');assert not state['own_offline_jobs'] and not state['live_or_budget_running'] and state['live_paused_by_user']
assert not (B/'sol/performance/ACTIVE.json').exists()
assert sha(B/'opus/review182/s312/r3/trees/P6/brain/ssbot/combat/tactics/clapper_priority.py')=='b476b0145f6f5fdfaea2af100a1041da483a9acf8f096b4e9a453ce649bacbe3'
assert sha(B/'opus/review182/s312/r3/trees/P6/brain/tests/test_landing_exit.py')=='cf44afd4e85902a42da783da69e33686acec33cf5f5bd62e9cf8a04d35a7ba9d'
parent=read(OLD/'SOURCE_PACKET_FIXED.json');base=Path(parent['source_root']);assert not S.exists();S.mkdir()
for name,digest in {**parent['raw_runtime_files_sha256'],**parent['support_sha256']}.items():
 assert sha(base/name)==digest
 dest=S/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(base/name,dest)
changes=[n for n in git('diff','--name-only',parent['source'],H).decode().splitlines() if n.startswith(('brain/ssbot/','knowledge/'))]
assert set(changes)=={'brain/ssbot/combat/tactics/clapper_priority.py','brain/ssbot/train/forum_planner_policy.py'}
for name in changes:
 data=git('show',H+':'+name);q=S/name
 if b'\r\n' in q.read_bytes():data=data.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
 q.write_bytes(data)
 shutil.copy2(q,A/Path(name).name)
shutil.copytree(base/'.git',S/'.git')
git('fetch','--quiet','--no-tags',str(W),H,cwd=S);git('symbolic-ref','HEAD','refs/heads/codex/landing424_freeze',cwd=S);git('update-ref','refs/heads/codex/landing424_freeze',H,cwd=S);git('read-tree',H,cwd=S)
assert not git('diff','HEAD','--','brain/ssbot','knowledge',cwd=S).strip()
packet=dict(at=now(),source=H,parent=parent['source'],source_root=str(S),raw_runtime_files_sha256={n:sha(S/n) for n in parent['raw_runtime_files_sha256']},runtime_support_files=parent['runtime_support_files'],support_sha256={n:sha(S/n) for n in parent['support_sha256']},runtime_delta=changes)
put(A/'SOURCE_PACKET_FIXED.json',packet)
evidence={};rr=B/'opus/review182/s312/r3/r'
for arm in ['off','on']:
 p=rr/('p6_ep12_'+arm);d=read(p/'RESULT.json');m=read(p/'CONFIGURATION_MANIFEST.json');prev=read(rr/('p5_ep12_'+arm)/'RESULT.json')
 assert d['exception'] is None and d['synthetic_from']==42144 and d['seed']==428636 and not d['foreign']
 assert not any(x['f']>=42144 for x in d['forced_planner_ticks'])
 assert all(normsha(S/'brain/ssbot'/n)==digest for n,digest in m['source_sha256'].items())
 take=lambda z:[(x['f'],x.get('keys'),x.get('owner'),x.get('hero_x'),x.get('hero_y')) for x in z['rows']]
 wire=lambda z:[(x['f'],x.get('requested')) for x in z['input_frames']]
 assert take(d)==take(prev) and wire(d)==wire(prev)
 ev=[json.loads(l) for l in (p/'decisions_i0.chain.jsonl').open(encoding='utf-8-sig')]
 sent=next(x for x in ev if x.get('event')=='transport_sent' and x.get('frame')==42145)
 assert sent['target']==42147 and sent['mask']==(2097152 if arm=='on' else 0)
 evidence[arm]=dict(artifact=str(p),source_files_matched=len(m['source_sha256']),production_wire=sent,P5_keys_and_trajectory_equal=True,first_model_hurt=d['first_model_hurt'],model_hits=d['model_hits'])
put(A/'FINAL_SOURCE_PRODUCTION_EVIDENCE.json',dict(at=now(),source=H,pair=evidence,fixture_end=42143,synthetic_from=42144,scope='Model production geometry/policy/planner/before-send/sent; not physical-game proof'))
put(A/'ASTRA_REVIEW424.json',dict(at=now(),source=H,reviewer='gpt-6-astra',reasoning_effort='xhigh',accepted=True,original_P2_closed=True,read_before_after_hashes_stable=True,priority_raw_sha='b476b0145f6f5fdfaea2af100a1041da483a9acf8f096b4e9a453ce649bacbe3',test_raw_sha='cf44afd4e85902a42da783da69e33686acec33cf5f5bd62e9cf8a04d35a7ba9d',scope='Only decision-x wall-rule repair, no JIT/tests/replay/P by Astra'))
review=dict(at=now(),source=H,accepted=True,delivery=424,closed_delivery=423,critical_review=str(A/'ASTRA_REVIEW424.json'),production_evidence=str(A/'FINAL_SOURCE_PRODUCTION_EVIDENCE.json'),author_test_cases=32,author_mutants=28,author_broad_tests_repeated=False,formal_timing_completed=False,formal_timing_pass=False,full_scheduling_gate_pass=False,live_released=False,live_paused_by_user=True)
put(A/'SOURCE_REVIEW_FINAL.json',review)
for name in ['entry_v3.py','engineering_helpers.py','resource_background.py','RESOURCE_BACKGROUND_APPROVAL.json']:shutil.copy2(OLD/name,A/name)
inputs=read(OLD/'REPLAY_INPUT_BINDING_V3.json')['files'];assert all(sha(n)==digest for n,digest in inputs.items())
trial=B/'opus/review182/s312/r3/trials/rt_ep12'
inputs.update({str(p):sha(p) for p in trial.rglob('*') if p.is_file() and '__pycache__' not in p.parts});inputs[str(A/'entry_v3.py')]=sha(A/'entry_v3.py')
put(A/'REPLAY_INPUT_BINDING.json',dict(at=now(),files=inputs,scope='Unchanged reviewed adapter/entry_v3 plus this recording own pre-SYN sends. No author patches in P.'))
case=read(OLD/'CASE_ON_V3.json')
flags=[f for f in case['contexts'][0]['flags'] if not f.startswith(('--opus-synth=','--no-force-from=','--fixture-recorded-run=','--env=SSBOT_FORUM_TWO_WALK_RULE='))]
flags+=['--opus-synth=42144','--no-force-from=42144','--fixture-recorded-run='+str(trial/'run')+':42143']
case.update(source=H,source_root=str(S),source_packet_file=str(A/'SOURCE_PACKET_FIXED.json'),source_packet_sha256=sha(A/'SOURCE_PACKET_FIXED.json'),source_review_file=str(A/'SOURCE_REVIEW_FINAL.json'),entry_file=str(A/'entry_v3.py'),entry_sha256=sha(A/'entry_v3.py'),input_binding_file=str(A/'REPLAY_INPUT_BINDING.json'),input_binding_sha256=sha(A/'REPLAY_INPUT_BINDING.json'),resource_helper_file=str(A/'engineering_helpers.py'),resource_helper_sha256=sha(A/'engineering_helpers.py'),accepted_reviews=sorted(set(case['accepted_reviews']+[420,421,422,423,424])))
for arm,enabled in [('ON','1'),('OFF','0')]:
 c=dict(case,case_id='landing424_'+arm.lower(),contexts=[dict(name='EXIT',trial=str(trial),**{'from':42145},last=42221,flags=flags+['--env=SSBOT_FORUM_LANDING_EXIT='+enabled])]);put(A/f'CASE_{arm}.json',c)
put(A/'P_PLAN.json',dict(at=now(),source=H,source_review_accepted=True,per_arm_frames=77,fixture_end=42143,fixture_clear_at=42144,measurement_from=42145,measurement_last=42221,entry_sha256_unchanged_from419=sha(A/'entry_v3.py')==sha(OLD/'entry_v3.py'),same_source_switch=[0,1],full_scheduling_gate_pass=False,game_authorized=False))
old=read(R/'RECEIPT423.json');old.update(closed_by_delivery=424,closure_source=H,original_failed_source_preserved=True,actual_author_start_verified=True);put(R/'RECEIPT423.json',old);put(R/'RECEIPT424.json',review)
state.update(at=now(),phase='LANDING424_SOURCE_ACCEPTED_P_PREPARING_LIVE_PAUSED',current_source=H,candidate_source=H,last_scanned_opus=424,source_review_pending=False,pending_opus=None,next_phase='Unchanged entry_v3: real check/finalize then77frame same-source ON/OFF formal P/finalize. User game pause remains.')
put(B/'sol/STATUS.json',state)
print(json.dumps(dict(source=H,source_accepted=True,runtime_files=len(packet['raw_runtime_files_sha256']),input_files=len(inputs),per_arm_frames=77,game_paused=True),ensure_ascii=False))
