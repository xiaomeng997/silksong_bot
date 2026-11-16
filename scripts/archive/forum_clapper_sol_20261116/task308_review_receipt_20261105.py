from pathlib import Path
import json,hashlib,datetime as dt,subprocess,os,psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');W=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');R=B/'analysis/task179_fd68690b_20261105';O=B/'opus/review179/l1_308'
GIT='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe';S='fd68690beb30757e25ddf2d96f7203561cb770f7'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output([GIT,'-C',str(W),*args],text=True,encoding='utf-8').strip()
def write(p,d):
 assert not p.exists(),p
 p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
assert git('rev-parse','HEAD')==S and not git('status','--porcelain','--untracked-files=no')
check=read(R/'ROOT_CHECK_JOB.json');assert check['exit_code']==0 and not check['foreign'] and check['source_files_unchanged']
assert not psutil.pid_exists(check['pid'])
old=read(B/'analysis/task179_5df8711e_20261105/SOURCE_PACKET.json')['raw_runtime_files_sha256'];current={n:sha(W/n) for n in old};changed=[n for n in old if old[n]!=current[n]]
expected={'brain/ssbot/combat/'+x for x in ('knife_chain_air_native.py','knife_chain_face_hook.py','knife_chain_geometry.py','knife_chain_transfer.py')}
assert set(changed)==expected,changed
for n in changed:
 committed=subprocess.check_output([GIT,'-C',str(W),'show',S+':'+n])
 assert (W/n).read_bytes().replace(b'\r\n',b'\n')==committed.replace(b'\r\n',b'\n')
final=read(O/'final/CMPFINAL308.json');assert all(x['sends_equal'] and x['events_equal'] and not x['result_diffs'] and x['knife_head']==S and not x['knife_brain_dirty'] for x in final.values())
sources={}
for name in ('l1','l2','l3'):
 d=read(O/'final'/name/'RESULT.json')
 assert d['knife_head']==S and not d['knife_brain_dirty'] and d['exception'] is None and not d['foreign'] and not d['forced_planner_ticks']
 bad=[n for n,h in d['source_sha256'].items() if sha(W/'brain/ssbot'/n)!=h]
 assert not bad,bad
 sources[name]={'bound_source_files':len(d['source_sha256']),'all_recorded_source_hashes_current':True,'divergence':d['divergence_tick'],'model_hurt':d['first_model_hurt'],'forced':[],'foreign':[],'exception':None}
now=dt.datetime.now(dt.timezone.utc).isoformat()
write(R/'SOURCE_PACKET.json',{'at':now,'source':S,'source_root':str(W),'raw_runtime_files_sha256':current,'changed_vs5df':changed,'scope':'current710, exactly4runfiles changed, existing model files unchanged; no startup gate'})
write(R/'OPUS308_RECEIPT_DRAFT.json',{'at':now,'source':S,'accepted':False,'status':'ordinary increment and artifacts reviewed; key scheme review pending, true-geometry positive and continuous retreat coverage not closed',
 'independent_checks':'17 new direct components passed;87.85s includes coldJIT; subset of Opus1115 not added','actual_root_check_pid':check['pid'],'root_check_actual_exited':True,
 'source710_bound':True,'loaded11hashes_match':sources,'increment_review':'4runfiles and17tests reviewed; original owner/hazard/unknown/instance guards retained in batch and no runtime safety margin relaxation found in ordinary increment review',
 'actual_L3_cause':'low-hop targeted hook lacked whole-lock and forced-bounce admission;2712/13 control bounce later hit airborne335470 at2721; target retreat observed but needle causation unproven',
 'L3_negative':'new2682entry refusal beforeCLAW; firstwirediv2683; modelcontinuation to2760 nohurt, recordedNPC conditions only, not real injury-free withdrawal',
 'new_positive':'only stub support and monkeypatched transfer.propose; no true geometry fullpolicy/before_send/sent admission positive',
 'key_gap':'endpoint retreat worlds and their control points do not certify continuous intermediate stop/control coverage; both endpoints failing does not imply middle failure',
 'P':'not started; new31msIdle is engineering component cost, second24ms is estimate; need positive full branch before affected formalP',
 'continuous_table':'not online; finite same-target148 domain remains, cross-target preexistingAntic is different domain',
 'high_hook':'not implemented; held>=2 conditionalL3 branch collides with otherAir, not universal failure of higherhook',
 'new_game_gate':False,'original_failed_runs_unchanged':True,'focused_astra':'existing astra_task178_pose_review final pending'})
status=read(B/'sol/STATUS.json');assert not status['live_or_budget_running'] and not status.get('own_offline_jobs')
status.update(at=now,phase='TASK179_308_FINITE_SOURCE_REVIEW',candidate_source=S,source_review_pending=True,last_opus_scan_number=308,opus308_receipt=str(R/'OPUS308_RECEIPT_DRAFT.json'),pending_opus='308 key hypothesis/scope review; no formalP/game until complete positive and retreat coverage decision')
t=B/'sol/STATUS.308review.tmp';t.write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(t,B/'sol/STATUS.json')
print(json.dumps({'source':S,'runtime_files':len(current),'changed':changed,'independent17':True,'formalP_started':False,'live_gate':False,'accepted':False},ensure_ascii=False))
