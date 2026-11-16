from pathlib import Path
import datetime,hashlib,json,os,shutil,subprocess,sys

B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/cluster_back416_20261113';D=B/'analysis/dash_side412_20261113'
W=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');S=A/'source';GIT='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
HEAD='fbf0a3881932d73fe4ba10b3697bb4888d69d503';read=lambda p:json.loads(Path(p).read_text('utf-8-sig'));sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def put(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf-8')
def git(*args,cwd=W):return subprocess.check_output([GIT,'-C',str(cwd),*args])

def main():
 assert git('rev-parse','HEAD').decode().strip()==HEAD and not git('diff','HEAD','--','brain/ssbot').strip()
 status=read(B/'sol/STATUS.json');assert not status['own_offline_jobs'] and not status['live_or_budget_running'] and status['live_paused_by_user']
 # Reuse the immutable accepted parent's runtime export; only the four reviewed
 # runtime files change. Test files are not a runtime prerequisite.
 parent=read(D/'SOURCE_PACKET_FIXED.json');old=Path(parent['source_root']);assert not S.exists();S.mkdir()
 for n,h in {**parent['raw_runtime_files_sha256'],**parent['support_sha256']}.items():
  assert sha(old/n)==h;q=S/n;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old/n,q)
 changed=[n for n in git('diff','--name-only',parent['source'],HEAD).decode().splitlines() if n.startswith(('brain/ssbot/','knowledge/'))]
 assert set(changed)=={'brain/ssbot/combat/tactics/clapper_plans.py','brain/ssbot/combat/tactics/clapper_tactics.py','brain/ssbot/combat/two_play.py','brain/ssbot/train/forum_planner_policy.py'}
 for n in changed:
  q=S/n;data=git('show',HEAD+':'+n)
  if b'\r\n' in q.read_bytes():data=data.replace(b'\n',b'\r\n')
  q.write_bytes(data)
 shutil.copytree(old/'.git',S/'.git')
 git('fetch','--quiet','--no-tags',str(W),HEAD,cwd=S)
 git('symbolic-ref','HEAD','refs/heads/codex/cluster417_freeze',cwd=S);git('update-ref','refs/heads/codex/cluster417_freeze',HEAD,cwd=S);git('read-tree',HEAD,cwd=S)
 assert not git('diff','HEAD','--','brain/ssbot','knowledge',cwd=S).strip()
 packet=dict(at=now(),source=HEAD,parent='114eb8ff19267b7e3f4f3a949126b6f3d5f0ff3e',package_baseline=parent['source'],source_root=str(S),raw_runtime_files_sha256={n:sha(S/n) for n in parent['raw_runtime_files_sha256']},runtime_support_files=parent['runtime_support_files'],support_sha256={n:sha(S/n) for n in parent['support_sha256']},runtime_delta=changed)
 put(A/'SOURCE_PACKET.json',packet)
 # Independently replay the single missing scope counterexample, not the suite.
 p=subprocess.run([sys.executable,'-B','-X','utf8','C:/modeling/silksong_bot/tmp/cluster416_scope_probe.py',str(S)],capture_output=True,text=True,encoding='utf-8');assert p.returncode==0,p.stderr
 probe=json.loads(p.stdout);assert probe['after_lure']['reason']=='other_move' and not probe['after_lure']['skip'] and probe['pending_middle_return']['iid']==8
 put(A/'SCOPE_PROBE_FIXED.json',probe)
 replay=B/'opus/review182/s312/px/r2/p2d_x4_ep1_s9484_PX';m=read(replay/'CONFIGURATION_MANIFEST.json')
 assert all(hashlib.sha256((S/'brain/ssbot'/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==h for n,h in m['source_sha256'].items())
 review=dict(at=now(),source=HEAD,accepted=True,delivery=417,closed_delivery=416,source_review='REVIEW416.md',scoped_exception=True,independent_lure_public_return_preserved=True,author_suite_reported=295,author_suite_repeated=False,new_test_cases=17,previous_file_test_count_corrected_from_16_to_15=True,production_source_files_matched=len(m['source_sha256']),author_same_wire_9484_9600=True,formal_timing_completed=False,formal_timing_pass=False,full_scheduling_gate_pass=False,live_released=False,live_paused_by_user=True)
 put(A/'SOURCE_REVIEW_FINAL.json',review)
 # Entry/executor are unchanged. Bind the exact existing adapters, replacing the
 # unrelated old trials with the one affected 2:03 context.
 inputs=read(D/'REPLAY_INPUT_BINDING.json')['files'];assert all(sha(Path(n))==h for n,h in inputs.items())
 inputs={n:h for n,h in inputs.items() if '/dx/trials/' not in n.replace('\\','/')}
 trial=B/'opus/review182/s312/dx/trials/x4_ep1'
 inputs.update({str(p):sha(p) for p in trial.rglob('*') if p.is_file() and '__pycache__' not in p.parts})
 put(A/'REPLAY_INPUT_BINDING.json',dict(at=now(),files=inputs,scope='Reviewed adapter bytes unchanged; only affected recorded trial added. No input-key fixture.'))
 for n in ['engineering_helpers.py','resource_background.py','RESOURCE_BACKGROUND_APPROVAL.json']:shutil.copy2(D/n,A/n)
 c=read(D/'CASE_NEW.json');draft=read(A/'P_PLAN_DRAFT.json')['context'];context=dict(name=draft['name'],trial=draft['trial'],**{'from':draft['start']},last=draft['last'],flags=draft['flags'])
 c.update(entry_file=str(D/'entry.py'),entry_sha256=sha(D/'entry.py'),input_binding_file=str(A/'REPLAY_INPUT_BINDING.json'),input_binding_sha256=sha(A/'REPLAY_INPUT_BINDING.json'),resource_helper_file=str(A/'engineering_helpers.py'),resource_helper_sha256=sha(A/'engineering_helpers.py'),contexts=[context],accepted_reviews=sorted(set(c['accepted_reviews']+[416,417])))
 for label,head,root,pack,reviewfile in [('NEW',HEAD,S,A/'SOURCE_PACKET.json',A/'SOURCE_REVIEW_FINAL.json'),('BASELINE',parent['source'],old,D/'SOURCE_PACKET_FIXED.json',D/'SOURCE_REVIEW_FINAL.json')]:
  cc=dict(c,source=head,source_root=str(root),source_packet_file=str(pack),source_packet_sha256=sha(pack),source_review_file=str(reviewfile),case_id='cluster416_'+label.lower());put(A/f'CASE_{label}.json',cc)
 hand=read(A/'HANDOFF358.json');hand.update(formal_completion_seen=True,formal_delivery=417,source_accepted=True,source=HEAD);put(A/'HANDOFF358.json',hand)
 original=read(A/'SOURCE_REVIEW.json');original['author_new_tests_source_reviewed']=15;original.update(closed_by_delivery=417,original_test_count_correction='416 stated16 including one external case; file had15, now17.');put(A/'SOURCE_REVIEW.json',original)
 r=read(B/'analysis/committed388_20261111/RECEIPT416.json');r.update(closed_by_delivery=417,closure_source=HEAD,original_source_not_relabelled_accepted=True);put(B/'analysis/committed388_20261111/RECEIPT416.json',r)
 put(B/'analysis/committed388_20261111/RECEIPT417.json',review)
 status.update(at=now(),phase='CLUSTER417_SOURCE_ACCEPTED_P_PREPARING_LIVE_PAUSED',current_source=HEAD,candidate_source=HEAD,last_scanned_opus=417,source_review_pending=False,pending_opus=None,opus417_receipt=str(B/'analysis/committed388_20261111/RECEIPT417.json'),next_phase='Run affected finite BACK P with real lifecycle; source scope repair accepted. User game pause remains.')
 put(B/'sol/STATUS.json',status)
 print(json.dumps(dict(source=HEAD,source_accepted=True,scope_probe_pass=True,runtime_files=len(packet['raw_runtime_files_sha256']),input_files=len(inputs),case_ticks=17,game_paused=True),ensure_ascii=False))

if __name__=='__main__':main()
