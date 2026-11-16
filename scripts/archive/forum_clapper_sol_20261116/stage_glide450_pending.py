"""Stage only a reviewable fresh50 proposal; no authorization, processes or game."""
from pathlib import Path
from datetime import datetime,timezone
import ast,hashlib,json,shutil,runpy

B=Path('C:/ssbot/data/m2_play/clapper_plan')
ROOT=Path('C:/modeling/silksong_bot')
OLD=B/'analysis/w13_50_glide_hold445_20261115'
G=B/'analysis/w13_50_glide_danger450_20261115'
D=B/'sol/demos'/G.name
A=B/'analysis/glide_danger450_20261115'
OLD_A=B/'analysis/glide_jump_hold445_20261115'
H='e097f60e42c518eb962782e71c0680ba543016a9'
OLDH='d6a3664416ef84280b214115dc80f2b256782b32'
now=lambda:datetime.now(timezone.utc).isoformat()
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def put(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def rewrite(t):
    for old,new in [(OLD.name,G.name),('GLIDE_HOLD445_W13_HP2_CONTINUOUS','GLIDE_DANGER450_W13_HP2_CONTINUOUS'),
                    (OLD_A.name,A.name),('source_fixed445','source_fixed450'),(OLDH,H),(OLDH[:8],H[:8])]:
        t=t.replace(old,new)
    return t
def obj(x):return json.loads(rewrite(json.dumps(x,ensure_ascii=False)))

assert not G.exists() and not D.exists()
assert read(A/'ROOT_P_AUDIT.json')['finite_measurement_valid']
assert read(A/'ROOT_CLEANUP.json')['actual_cleanup_verified']
assert read(A/'SOURCE_REVIEW_AND_P_FINAL.json')['source']==H
s=read(B/'sol/STATUS.json');assert not s['live_or_budget_running'] and not s.get('own_offline_jobs') and not s.get('own_live_session')
assert not (B/'sol/performance/ACTIVE.json').exists()
G.mkdir();packet=read(A/'SOURCE_PACKET_FIXED.json');S=Path(packet['source_root'])
assert all(sha(S/n)==h for n,h in {**packet['raw_runtime_files_sha256'],**packet['support_sha256']}.items())
for p in OLD.glob('*.py'):
    t=rewrite(p.read_text(encoding='utf-8-sig'))
    if p.name=='finish_preparation.py':
        assert t.count('range(405,446)')==1;t=t.replace('range(405,446)','range(405,451)')
        begin=t.index("formal_coverage_note='");end=t.index("')",begin)
        t=t[:begin]+"formal_coverage_note='Source-reviewed GD cost with attack-cancel repair; unchanged entry_v4, two finite affected windows47 frames per arm ONOFF. Actual replay sends and cleanup verified, not global budget or live benefit. Continuous lifecycle reused.'"+t[end+1:]
    elif p.name=='trial.py':
        needle=' assert e.get("SSBOT_FORUM_GLIDE_JUMP_HOLD")=="1","this batch enables the reviewed glide jump-hold lifecycle fix"'
        assert needle in t;t=t.replace(needle,needle+'\n assert e.get("SSBOT_FORUM_GLIDE_DANGER")=="1","this batch enables the reviewed first-key glide cost"')
    elif p.name=='release.py':
        needle=" assert ip['passed']";assert t.count(needle)==1
        t=t.replace(needle," assert worker.environ().get('SSBOT_FORUM_GLIDE_DANGER')=='1','new worker does not bind GD1'\n"+needle)
        t=t.replace("phase='SEPARATED312_50_RUNNING'","phase='GLIDE450_50_RUNNING'")
    elif p.name=='audit_repeat50.py':
        # Correct known inherited postprocessing assertions before binding a new contract.
        t=t.replace('w13_50_middle_handoff434_20261114/ROOT_50_RESULT.json',OLD.name+'/ROOT_50_RESULT.json')
        needle="        assert row['code_rev'].removesuffix('+dirty') in (gate['source'],gate['source'][:8]),(ep,row['code_rev'],gate['source'])"
        assert needle in t
        t=t.replace(needle,"        revision=row['code_rev'].removesuffix('+dirty')\n        assert 7<=len(revision)<=40 and all(c in '0123456789abcdef' for c in revision) and gate['source'].startswith(revision),(ep,revision,gate['source'])\n        manifest=read(D/f'run/measurement_manifest_i0_e{ep}.json')\n        assert manifest['code']['head_revision']==gate['source'] and manifest['configuration_complete'] and not manifest['unresolved']")
        t=t.replace("row['time_scale_game']==1","row['time_scale_game'] is not None and abs(row['time_scale_game']-1)<=1e-3")
        t=t.replace("phase='GLIDE44550_RAW_AUDIT'","phase='GLIDE45050_RAW_AUDIT'")
    elif p.name=='summarize_current50.py':
        needle="            ('SSBOT_FORUM_GLIDE_JUMP_HOLD', 'ssbot.combat.forum_planner.GLIDE_JUMP_HOLD', True, '1'),"
        assert needle in t;t=t.replace(needle,needle+"\n            ('SSBOT_FORUM_GLIDE_DANGER', 'ssbot.combat.forum_planner.GLIDE_DANGER', True, '1'),")
        t=t.replace('B13B=True, glide_jump_hold=True,','B13B=True, glide_danger=True, glide_jump_hold=True,')
    ast.parse(t);(G/p.name).write_text(t,encoding='utf-8')
for n in ['RESOURCE_BACKGROUND_APPROVAL.json','RESOURCE_BACKGROUND_CLASSIFICATION_CHECKS.json']:
    shutil.copy2(OLD/n,G/n)
reuse=obj(read(OLD/'RUNTIME354_REUSE.json'));reuse.update(at=now(),source=H)
assert all(sha(S/n)==h for n,h in reuse['lifecycle_files_unchanged'].items())
assert sha(reuse['prior_real_probe'])==reuse['prior_real_probe_sha256'];put(G/'RUNTIME354_REUSE.json',reuse)
plan=obj(read(OLD/'CONTINUOUS_PLAN.json'));plan.update(at=now(),source=H,comparison_baseline_source=OLDH,authorization=None,authorized=False,
    notes='Pending fresh50; latest GJH50 same50 seeds/order and MH1/GJH1/AS1/LANDING1, only GD1 added. No launch/preheat without a new actual reply.')
assert plan['seeds']==read(OLD/'CONTINUOUS_PLAN.json')['seeds'] and len(plan['seeds'])==50;put(G/'CONTINUOUS_PLAN.json',plan)
draft=obj(read(OLD/'TRIAL_CONFIG_DRAFT.json'));draft.update(at=now(),source=H,user_authorized=False,authorization=None,purpose='First-controllable-key dangerous-umbrella soft cost, fresh same50 comparison')
draft['environment']['SSBOT_FORUM_GLIDE_DANGER']='1'
assert draft['environment']['SSBOT_FORUM_GLIDE_JUMP_HOLD']=='1' and draft['environment']['SSBOT_FORUM_SLAM_NO_NEW_GLIDE']=='0'
put(G/'TRIAL_CONFIG_DRAFT.json',draft)
normalized_old={k:v.replace(OLD.name,G.name) for k,v in read(OLD/'TRIAL_CONFIG_DRAFT.json')['environment'].items()}
assert {k:(normalized_old.get(k),v) for k,v in draft['environment'].items() if normalized_old.get(k)!=v}=={'SSBOT_FORUM_GLIDE_DANGER':(None,'1')}
candidate=obj(read(OLD/'CANDIDATE_SPEC.json'));candidate.update(at=now(),source=H);put(G/'CANDIDATE_SPEC.json',candidate)
validation=obj(read(OLD/'VALIDATION_PLAN.json'));validation.update(at=now(),user_authorized=False,next_candidate=G.name,
    scope='Pending fresh50; startup>=30fps, all50 actual GD/GJH binding, full main+postkill tails and real protection criteria. No injury benefit inferred from P.');put(G/'VALIDATION_PLAN.json',validation)
checks=obj(read(OLD/'START_GATE_CHECKS.json'))
assert sha(G/'user_authorization.py')==checks['unchanged_user_authorization_sha256']
assert sha(G/'start_gate.py')==checks['unchanged_start_gate_sha256']
checks.update(at=now(),scope='Unchanged authorization/GO predicates; new actual worker/input/recording/resource/FPS and GD/GJH environment gates required after real reply.');put(G/'START_GATE_CHECKS.json',checks)
lc=obj(read(OLD/'LIFECYCLE_REVIEW.json'));lc.update(at=now(),accepted=True,files={p.name:sha(p) for p in G.glob('*.py')},previous_review=str(OLD/'LIFECYCLE_REVIEW.json'),
    changes='Same continuous control and strict stops; new source/path/P coverage metadata and GD1 config/worker assertion. Postprocessing uses current GJH50 baseline and manifest GD binding; valid Git prefix and original runtime timeScale tolerance replace inherited exact formatting assertions. No actual authorization or launch.')
put(G/'LIFECYCLE_REVIEW.json',lc)
auth=obj(read(OLD/'USER_NEW50_AUTHORIZATION.json'));auth.update(at=now(),kind='PENDING_NOT_AUTHORIZED',source=H,batch_id=G.name,user_text=None,question_item_id=None,provenance=None,started=False,
    glide_danger_enabled_for_this_batch=True,physical_tv_on_confirmed_by_user=False,physical_TV_current_state_not_assumed=True)
put(G/'AUTHORIZATION_TEMPLATE_NOT_VALID.json',auth)
put(G/'BATCH_SPEC.json',dict(at=now(),batch=G.name,source=H,planned_bouts=50,state='PENDING_NEW_USER_AUTHORIZATION',ready=False,authorized=False,started=False,
    same_game=True,recording=True,hp2_continue=True,runtime_fault_stops=True,minimum_launch_fps=30,temporary_awake_request_proposed=True,
    physical_TV_current_state_not_assumed=True,only_new_feature='SSBOT_FORUM_GLIDE_DANGER=1',same_other_flags_as=OLD.name,prior_paused_batch_reopened=False))
for src,dst in [('launch_glide445.ps1','launch_glide450.ps1'),('start_display_glide445.ps1','start_display_glide450.ps1'),('watch_glide445_loop.py','watch_glide450_loop.py')]:
    t=rewrite((ROOT/'tmp'/src).read_text(encoding='utf-8-sig')).replace('watch_glide445_loop.py','watch_glide450_loop.py')
    if dst.endswith('.py'):ast.parse(t)
    (ROOT/'tmp'/dst).write_text(t,encoding='utf-8')
resource=runpy.run_path(str(G/'engineering_helpers.py'))['resource_guard']();put(G/'PREAUTH_RESOURCE.json',resource)
proposal=dict(at=now(),source=H,batch=G.name,prepared_without_authorization=True,authorized=False,game_started=False,planned_bouts=50,
    source_and_P=str(A/'SOURCE_REVIEW_AND_P_FINAL.json'),P=str(A/'ROOT_P_AUDIT.json'),baseline=OLD.name,only_new_feature='GD1',same_seeds=True,
    same_game=True,recording=True,hp2_continue=True,fault_stops=True,startup_fps_required=30,full_scheduling_gate_pass=False,performance_budget_pass=False,
    pending='New current-chat explicit new50 reply, then actual final preflight and warm gates before launch/GO',launch_wrapper=str(ROOT/'tmp/launch_then_release.ps1'),
    launch_script=str(ROOT/'tmp/launch_glide450.ps1'),launch_release_wrapper_sha256=sha(ROOT/'tmp/launch_then_release.ps1'))
put(A/'NEW50_PROPOSAL.json',proposal)
assert not D.exists() and not (G/'USER_NEW50_AUTHORIZATION.json').exists() and not (G/'LAUNCH_CLAIM.json').exists()
put(G/'PREAUTH_STAGING.json',dict(proposal,source_files=len(packet['raw_runtime_files_sha256']),lifecycle_files=len(lc['files']),
    seed_plan_sha256=sha(G/'CONTINUOUS_PLAN.json'),draft_sha256=sha(G/'TRIAL_CONFIG_DRAFT.json'),strict_authorization_guards_not_changed=True,
    resource_blockers=resource['blockers'],actual_prepare_and_source_hashes_pending_reply=True))
print(json.dumps(dict(batch=G.name,source=H,staged=True,authorized=False,game_started=False,same50_seeds=True,
    lifecycle_scripts=len(lc['files']),source_files=len(packet['raw_runtime_files_sha256']),resource_blockers=resource['blockers']),ensure_ascii=False))
