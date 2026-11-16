from pathlib import Path
import ast,datetime,hashlib,json,os,shutil,psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');R=B/'analysis/task179_observe310_20261105';D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
S='689b8bc29e67cbcc24a8063418ec50244d0dd44b';OLD=B/'analysis/w13_guard179L3_20261106T012400Z_5df8711e';T=B/'sol/demos/w13_guard179L3_20261106T012400Z_5df8711e'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
rec=read(R/'CHECK_RECEIPT.json');assert rec['returncode']==0 and not rec['foreign'] and not psutil.pid_exists(rec['job']['pid'])
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st['own_offline_jobs']
env={'SSBOT_FORUM_OBSERVE_BOUT':'1','SSBOT_FORUM_REMAINING_HP_QUIT':'0','SSBOT_FORUM_CHAIN_FACE_HOOK':'0','SSBOT_FORUM_CHAIN_BOUNCE_TABLE':'0'}
review=dict(at=now(),source=S,accepted=True,scope='ONE bounded watched observation only, specified profile mandatory',required_environment=env,
 reviewed=['all seven310 runtime changes and existing adjacent supervisor/receipt paths','309 shared adapters with bounce0 and facehook0; inactive new geometry/table not certified','raw714 binding and all264 knowledge files unchanged','L2 actual observed takeoff, fixed2.5 bodywidth start reference, existing wall clamp and ordinary side approach','blocked catastrophe/would_die continue only explicit observation; normal eval/input/resource/fatal paths retained'],
 checks=dict(passed=82,subset_of_opus597=True,foreign=0,source_unchanged=True,actual_job_exited=True),
 limits=['new bait/return is an experimental preference, not a safe path certificate','source310 conditional replay uses recorded NPC after hero diverges; no natural closed-loop proof','return span may be short or none; ground target may retreat and swing may miss','cluster rule admits same-side separated actors too: actual initial spacing must be logged; not only body-overlap domain','wall_room_u may cap to an inward stance if already at wall; no claimed full2.5width in that case','309 bounce contacts and completed vault still unaccepted; keep both new entrances disabled','old performance/deadline limitations are retained; new cost sample is not future latency guarantee'],
 processed_review_applicability={'308':'facehook-specific lock/out issues inactive with FACE_HOOK0; original pending full acceptance retained','309':'shared active adapter increment reviewed; bounce/facehook/vault expansion deferred and disabled; not a broad feature acceptance','310':'active tactic and observation changes accepted for this one profile after targeted82'},new_game_gate=False)
put(R/'SOURCE_REVIEW.json',review)
base=B/'sol/performance/adapters/task179_5df8711e.py';entry=R/'timing_entry310.py';src=base.read_text(encoding='utf-8')
line='    os.environ.update({k: str(v) for k, v in contract["environment"].items() if k.startswith("SSBOT_")})'
assert src.count(line)==1
insert='\n    # Root one-bout310 profile: explicit recorded overrides, no model or ACTION forcing change.\n    os.environ.update('+repr(env)+')'
code=src.replace(line,line+insert);assert code.replace(insert,'')==src;ast.parse(code);entry.write_text(code,encoding='utf-8')
put(R/'ADAPTER_REVIEW.json',dict(at=now(),base=str(base),base_sha256=sha(base),entry_sha256=sha(entry),single_change='four explicit environment profile overrides after recorded contract; inverse exact',forcing_geometry_lifecycle_unchanged=True,guarded_main=True))
for n in ['engineering_helpers.py','resource_background.py','RESOURCE_BACKGROUND_APPROVAL.json']:shutil.copyfile(OLD/n,R/n)
inputs=[T/'contract.json',T/'run/decisions_i0.chain.jsonl',T/'run/b2_input_path_i0.json']
inputs+=list((T/'run/rec').rglob('*'));inputs=[x for x in inputs if x.is_file()]
put(R/'P_INPUT_BINDING.json',dict(at=now(),scope='oldL3 recorded condition labels only, not new live IPC receipt',files={str(x):sha(x) for x in inputs}))
accepted=sorted(set(st['accepted_opus_numbers'])|{308,309,310})
put(R/'REVIEW_APPLICABILITY.json',dict(at=now(),scope='this ONE profile only',processed_numbers_for_scoped_blocker_scan=accepted,conditional_numbers=review['processed_review_applicability'],not_global_acceptance_of_308_309_features=True))
case=dict(source=S,source_root=str(D),source_review_file=str(R/'SOURCE_REVIEW.json'),entry_file=str(entry),entry_sha256=sha(entry),source_packet_file=str(R/'SOURCE_PACKET.json'),source_packet_sha256=sha(R/'SOURCE_PACKET.json'),
 input_binding_file=str(R/'P_INPUT_BINDING.json'),input_binding_sha256=sha(R/'P_INPUT_BINDING.json'),resource_helper_file=str(R/'engineering_helpers.py'),resource_helper_sha256=sha(R/'engineering_helpers.py'),
 git_directory='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd',cache=str(B/'analysis/critical214_20261103/p_prepared_ce81b62c/numba_cache'),
 contexts=[dict(name='cluster_bait_return',trial=str(T),**{'from':2640},last=2725,flags=[])],
 baseline=dict(golden_sha256='fc41b9c5427b4e23ec60af1f16808a6b497507eded5704b90c9224b056ea0469',old_demo_sha256='0455dd550525b4b11ed62eccb47cdfeb802a3ba0a8b0c08d30f8cc961c53cb81',old_demo_mtime_ns=1791523123325081300),
 accepted_reviews=accepted,expected_field_worker=True,required_profile_overrides=env,scope='only affected86tick continuity; actual source/profile/lifecycle; not new geometry certification')
put(R/'P_CASE.json',case)
assert sha(B/'sol/performance/executor_v1.py')=='58ddebd9cae93764d37b9fb4efa75ea7a2484bb6f4337895a245886e86062ffc'
st.update(at=now(),current_source=S,source_review_pending=False,source_review_scope=review['scope'],source_review_file=str(R/'SOURCE_REVIEW.json'),phase='TASK179_OBSERVE310_READY_STARTUP',pending_opus=None)
q=B/'sol/STATUS.review310.tmp';put(q,st);os.replace(q,B/'sol/STATUS.json')
print(json.dumps(dict(source_review=True,scoped_profile=env,case=str(R/'P_CASE.json'),input_files=len(inputs))))
