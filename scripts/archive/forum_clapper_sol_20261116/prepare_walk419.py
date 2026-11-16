from pathlib import Path
import datetime,hashlib,json,os,shutil,subprocess
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/walk_rule418_20261113';P=B/'analysis/cluster_back416_20261113'
W=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');S=A/'source_fixed419';GIT='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe';HEAD='7a43c1edf0148834bb78eff0ebb7da7f9723c718'
read=lambda p:json.loads(Path(p).read_text('utf-8-sig'));sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def put(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf-8')
def git(*args,cwd=W):return subprocess.check_output([GIT,'-C',str(cwd),*args])

def main():
 assert git('rev-parse','HEAD').decode().strip()==HEAD and not git('diff','HEAD','--','brain/ssbot').strip()
 state=read(B/'sol/STATUS.json');assert not state['own_offline_jobs'] and not state['live_or_budget_running'] and state['live_paused_by_user']
 # Match the critical review's exact stable files before reusing it.
 expected={'brain/ssbot/combat/walk_rule.py':'f82aef1ab687ae4147cef311d387f1df41ecdd9611581ec7fd6fc298e6917eac','brain/ssbot/combat/knife_chain_geometry.py':'ddee1165adbcea64dcc354805a7081d1558a0dcb9c68292c7a6b1b09ab93c98f','brain/ssbot/combat/knife_chain_air_native.py':'5083b35788386e21f63cb8f202d85340da41f9de46f22a6872273b2965974a34','brain/ssbot/combat/knife_chain_face_hook.py':'e8408de06b67a7811fb2990946e6794d4e5db2588be2d6b0cf10cd6e6300cb94','brain/ssbot/combat/knife_chain_b2.py':'4e5b8c5002a9bb371b161555db9ba3bf8b6ce414b195058d8b35a11df5f655fe','brain/ssbot/train/forum_planner_policy.py':'933ae2fb5bd27c67834d3bfc43a9d5a0527ce4d9899d1413b4b89ab32e477952','brain/tests/test_walk_rule.py':'82ad235e329e27272d8da29d0d74f8591197dc5da25384ad3e87ba7c1433a74b'}
 assert all(sha(W/n)==h for n,h in expected.items())
 put(A/'ASTRA_REVIEW419.json',dict(at=now(),source=HEAD,reviewer='gpt-6-astra',reasoning_effort='xhigh',accepted=True,original_P2_closed=True,read_before_after_hashes_stable=True,worktree_sha256=expected,raw_git_match_except_CRLF=['brain/ssbot/combat/knife_chain_b2.py','brain/ssbot/train/forum_planner_policy.py'],independent_checks=['same candidate prelude restores full-route interval and suffix contacts','unknown prelude conservative; high end28.5 vs27.433333','alternative union and mixed batch consistent','switch off keeps old occupancy paths','warm argument types/layouts match, no JIT/P run'],scope='Only offset repair; not functional replay or performance approval.'))
 parent=read(A/'SOURCE_PACKET_ORIGINAL.json');old=Path(parent['source_root']);assert not S.exists();S.mkdir()
 for n,h in {**parent['raw_runtime_files_sha256'],**parent['support_sha256']}.items():
  assert sha(old/n)==h;q=S/n;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old/n,q)
 changed=[n for n in git('diff','--name-only',parent['source'],HEAD).decode().splitlines() if n.startswith(('brain/ssbot/','knowledge/'))]
 assert set(changed)=={'brain/ssbot/combat/knife_chain_air_native.py','brain/ssbot/combat/knife_chain_b2.py','brain/ssbot/combat/knife_chain_face_hook.py','brain/ssbot/combat/knife_chain_geometry.py','brain/ssbot/combat/walk_rule.py'}
 for n in changed:
  q=S/n;data=git('show',HEAD+':'+n)
  if b'\r\n' in q.read_bytes():data=data.replace(b'\n',b'\r\n')
  q.write_bytes(data)
 shutil.copytree(old/'.git',S/'.git');git('fetch','--quiet','--no-tags',str(W),HEAD,cwd=S);git('symbolic-ref','HEAD','refs/heads/codex/walk419_freeze',cwd=S);git('update-ref','refs/heads/codex/walk419_freeze',HEAD,cwd=S);git('read-tree',HEAD,cwd=S)
 assert not git('diff','HEAD','--','brain/ssbot','knowledge',cwd=S).strip()
 packet=dict(at=now(),source=HEAD,parent=parent['source'],source_root=str(S),raw_runtime_files_sha256={n:sha(S/n) for n in parent['raw_runtime_files_sha256']},runtime_support_files=parent['runtime_support_files'],support_sha256={n:sha(S/n) for n in parent['support_sha256']},runtime_delta=changed)
 put(A/'SOURCE_PACKET_FIXED.json',packet)
 # Final author pair is real production geometry/wire with identical explicit
 # pre-synthetic recorded keys. No rule gating or forced selection during it.
 evidence={};R=B/'opus/review182/s312/wk/fix359/r'
 for label in ['off','on']:
  p=R/f'wf2_ep1_s10012_{label}';r=read(p/'RESULT.json');m=read(p/'CONFIGURATION_MANIFEST.json')
  assert r['exception'] is None and r['synthetic_from']==10012 and not r['foreign'] and not any(z['f']>=10012 for z in r['forced_planner_ticks'])
  assert all(hashlib.sha256((S/'brain/ssbot'/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==h for n,h in m['source_sha256'].items())
  events=[json.loads(l) for l in (p/'decisions_i0.chain.jsonl').open(encoding='utf-8')]
  note=next(z for z in events if z.get('frame')==10062 and z['event']==('transfer_follow_middle' if label=='on' else 'transfer_follow_middle_blocked'))
  wire=next(z for z in events if z.get('frame')==10062 and z['event']=='transport_sent')
  assert wire['mask']==(1048576 if label=='on' else 2097152) and wire['target']==10064
  evidence[label]=dict(artifact=str(p),source_files_matched=len(m['source_sha256']),synthetic_from=r['synthetic_from'],target_event={k:v for k,v in note.items() if k!='scanned'},actual_wire=wire)
 put(A/'FINAL_SOURCE_PRODUCTION_EVIDENCE.json',dict(at=now(),source=HEAD,pair=evidence,fixture_through=10011,read_only_diagnostic=True,controller_gating=False,late_offset_dynamic_coverage=False,original_late_offset_closed_by='ASTRA component/call-site review, not this replay window',void_pair_retained=str(R/'void_wf_ep1_s10012_on')))
 review=dict(at=now(),source=HEAD,accepted=True,delivery=419,closed_delivery=418,critical_review=str(A/'ASTRA_REVIEW419.json'),production_evidence=str(A/'FINAL_SOURCE_PRODUCTION_EVIDENCE.json'),author_affected_tests_reported=2177,new_test_cases=19,broad_tests_repeated=False,formal_timing_completed=False,formal_timing_pass=False,full_scheduling_gate_pass=False,live_released=False,live_paused_by_user=True)
 put(A/'SOURCE_REVIEW_FINAL.json',review)
 shutil.copy2('C:/modeling/silksong_bot/tmp/walk419_entry.py',A/'entry.py');compile((A/'entry.py').read_text('utf-8'),str(A/'entry.py'),'exec')
 inputs=read(P/'REPLAY_INPUT_BINDING.json')['files'];assert all(sha(Path(n))==h for n,h in inputs.items())
 inputs={n:h for n,h in inputs.items() if '/dx/trials/' not in n.replace('\\','/')};trial=B/'opus/review182/s312/dx/trials/x4_ep1'
 inputs.update({str(p):sha(p) for p in trial.rglob('*') if p.is_file() and '__pycache__' not in p.parts});inputs[str(A/'entry.py')]=sha(A/'entry.py')
 put(A/'REPLAY_INPUT_BINDING.json',dict(at=now(),files=inputs,scope='Unchanged reviewed adapter stack plus bounded pre-synthetic own-recording fixture; no Opus diagnostic patch in P.'))
 for n in ['engineering_helpers.py','resource_background.py','RESOURCE_BACKGROUND_APPROVAL.json']:shutil.copy2(P/n,A/n)
 case=read(P/'CASE_NEW.json');flags=[v for v in case['contexts'][0]['flags'] if not v.startswith(('--opus-synth=','--no-force-from='))]
 flags+=['--opus-synth=10012','--no-force-from=10012','--fixture-recorded-run='+str(trial/'run')+':10011']
 case.update(source=HEAD,source_root=str(S),source_packet_file=str(A/'SOURCE_PACKET_FIXED.json'),source_packet_sha256=sha(A/'SOURCE_PACKET_FIXED.json'),source_review_file=str(A/'SOURCE_REVIEW_FINAL.json'),entry_file=str(A/'entry.py'),entry_sha256=sha(A/'entry.py'),input_binding_file=str(A/'REPLAY_INPUT_BINDING.json'),input_binding_sha256=sha(A/'REPLAY_INPUT_BINDING.json'),resource_helper_file=str(A/'engineering_helpers.py'),resource_helper_sha256=sha(A/'engineering_helpers.py'),accepted_reviews=sorted(set(case['accepted_reviews']+[418,419])))
 for label,enabled in [('ON','1'),('OFF','0')]:
  cc=dict(case,case_id='walk419_'+label.lower(),contexts=[dict(name='RETURN',trial=str(trial),**{'from':10054},last=10112,flags=flags+['--env=SSBOT_FORUM_TWO_WALK_RULE='+enabled])]);put(A/f'CASE_{label}.json',cc)
 put(A/'P_PLAN.json',dict(at=now(),source=HEAD,source_review_accepted=True,per_arm_frames=59,same_source_switch=[0,1],fixture_end=10011,fixture_cleared_at=10012,measurement_from=10054,measurement_last=10112,entry_changed=True,real_zero_tick_check_required=True,full_scheduling_gate_pass=False,game_authorized=False))
 h=read(A/'HANDOFF359.json');h.update(formal_completion_seen=True,formal_delivery=419,source_accepted=True);put(A/'HANDOFF359.json',h)
 r=read(B/'analysis/committed388_20261111/RECEIPT418.json');r.update(closed_by_delivery=419,closure_source=HEAD,original_failed_source_preserved=True);put(B/'analysis/committed388_20261111/RECEIPT418.json',r);put(B/'analysis/committed388_20261111/RECEIPT419.json',review)
 state.update(at=now(),phase='WALK419_SOURCE_ACCEPTED_P_PREPARING_LIVE_PAUSED',current_source=HEAD,candidate_source=HEAD,last_scanned_opus=419,source_review_pending=False,pending_opus=None,opus419_receipt=str(B/'analysis/committed388_20261111/RECEIPT419.json'),next_phase='New bounded pre-synthetic recorded-input fixture entry: check/finalize then59-frame ON/OFF same-source finite P. User game pause remains.')
 put(B/'sol/STATUS.json',state)
 print(json.dumps(dict(source=HEAD,source_accepted=True,runtime_files=len(packet['raw_runtime_files_sha256']),input_files=len(inputs),per_arm_frames=59,game_paused=True),ensure_ascii=False))

if __name__=='__main__':main()
