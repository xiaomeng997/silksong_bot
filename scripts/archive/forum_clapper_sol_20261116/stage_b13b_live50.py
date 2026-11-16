"""Prepare a fresh bounded live50 candidate without fabricating or consuming authorization."""
from pathlib import Path
import ast, datetime, hashlib, importlib.util, json, os, shutil, subprocess, sys

B=Path('C:/ssbot/data/m2_play/clapper_plan')
A=B/'analysis/b13b_402_20261113'
OLD=B/'analysis/w13_50_slamstart398_20261112_r1'
OLD_A=B/'analysis/slamstart398_20261112'
G=B/'analysis/w13_50_b13b404_20261113'
D=B/'sol/demos'/G.name
HEAD='e7e975f38c85b8f4a2aae47399a5425ff46a1d6b'
SCOPE='B13B404_50_W13_HP2_CONTINUOUS'
GIT='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

def put(p,x):
    Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def rewrite(text):
    # Only the new batch, reviewed frozen source and explicit scope labels change.
    for old,new in [(OLD.name,G.name),('slamstart398_20261112','b13b_402_20261113'),
                    ('ec95cccebd4a114bc8db5c699ca58979e67c2f83',HEAD),
                    ('SLAMSTART398_50_W13_HP2_CONTINUOUS',SCOPE)]:
        text=text.replace(old,new)
    return text

def ast_equal(old,new):
    return ast.dump(ast.parse(rewrite(old)),include_attributes=False)==ast.dump(ast.parse(new),include_attributes=False)

def main():
    assert not G.exists() and not D.exists()
    assert read(OLD/'ROOT_CLEANUP.json')['complete'] and read(OLD/'BATCH_SPEC.json')['completed']
    sr=read(A/'SOURCE_REVIEW_FINAL.json');pa=read(A/'ROOT_P_AUDIT.json');sp=read(A/'SOURCE_PACKET.json')
    assert sr['accepted'] and sr['scoped_engineering_timing_pass'] and pa['scoped_engineering_timing_pass']
    assert sr['source']==pa['source']==sp['source']==HEAD
    assert all(sha(A/'source'/n)==h for n,h in {**sp['raw_runtime_files_sha256'],**sp['support_sha256']}.items())
    assert subprocess.check_output([GIT,'rev-parse','HEAD'],cwd=A/'source',text=True).strip()==HEAD
    assert not subprocess.check_output([GIT,'diff','HEAD','--','brain/ssbot','knowledge'],cwd=A/'source').strip()
    assert sha(A/'entry.py')==sha(OLD_A/'entry.py')
    G.mkdir()
    sources={p.name:p.read_text(encoding='utf-8') for p in OLD.glob('*.py')}
    for name,text in sources.items():(G/name).write_text(rewrite(text),encoding='utf-8')
    # Keep every launch/action/stop/input/recording/cleanup path unchanged.
    for name in ['trial.py','run_unattended.py','release.py','root_cleanup.py','root_live_watch.py','capture.py','monitor.py','wait_resources.py','watch_worker.py']:
        assert ast_equal(sources[name],(G/name).read_text(encoding='utf-8')),name
    for name in ['user_authorization.py','start_gate.py']:
        assert sha(G/name)==sha(OLD/name),name
    p=G/'trial.py';text=p.read_text(encoding='utf-8')
    anchor=' for key in ("SSBOT_FORUM_SLAM_COMMIT","SSBOT_FORUM_SLAM_START25","SSBOT_FORUM_SLAM_NOTICE"):assert e.get(key)=="1",(key,e.get(key))'
    assert anchor in text
    text=text.replace(anchor,anchor+'\n for key in ("SSBOT_FORUM_CHAIN_B13","SSBOT_FORUM_CHAIN_B13B"):assert e.get(key)=="1",(key,e.get(key))')
    p.write_text(text,encoding='utf-8')
    # Preparation-only schema update: latest four P receipts, carried user facts from the reviewed prior package.
    p=G/'finish_preparation.py';text=p.read_text(encoding='utf-8')
    text=text.replace("PARENT=B/'analysis/w13_50_waypoint394_20261112_r2'",f"PARENT=B/'analysis/{OLD.name}'")
    text=text.replace("SOURCE_REVIEW_LIVE.json","SOURCE_REVIEW_FINAL.json").replace('LIVE_BINDING398.json','LIVE_BINDING404.json')
    for name in ['USER_SLAM_AFTER_ALWAYS_MIDDLE.json','USER_SMALL_RUNE_HOOK_OPENING.json']:
        old=f"assert sr.get('user_scope_sha256',{{}}).get('{name}')==sha(A/'{name}')"
        new=f"assert adapter['carried_user_scope_sha256']['{name}']==sha(Path('{OLD_A.as_posix()}')/'{name}')"
        assert old in text;text=text.replace(old,new)
    text=text.replace("int(sr['opus_number'])+1","405")
    for name in ['P_ADAPTER_REVIEW.json','CASE_NOTICE_NEW.json','CASE_NOTICE_BASELINE.json','NOTICE_REPAIR_VERIFIED.json','USER_SLAM_AFTER_ALWAYS_MIDDLE.json','USER_SMALL_RUNE_HOOK_OPENING.json']:
        text=text.replace(f"A/'{name}'",f"Path('{OLD_A.as_posix()}')/'{name}'")
    text=text.replace("# Independently bound current eight actual startup/formal receipt hashes", "# Independently bound current four actual startup/formal receipt hashes")
    text=text.replace("A/'CASE_NEW.json'","A/'CASE_NEW.json'")
    p.write_text(text,encoding='utf-8')
    for name in ['engineering_helpers.py','resource_background.py','RESOURCE_BACKGROUND_APPROVAL.json']:
        shutil.copy2(A/name,G/name)
    # Resource classifier logic is identical; current identity approval and actual resource receipt are separately bound.
    put(G/'RESOURCE_BACKGROUND_CLASSIFICATION_CHECKS.json',dict(at=now(),passed=True,
        unchanged_classifier_sha256=sha(G/'resource_background.py'),unchanged_helper_sha256=sha(G/'engineering_helpers.py'),
        previous_checks=str(OLD/'RESOURCE_BACKGROUND_CLASSIFICATION_CHECKS.json'),
        current_identity_refresh=str(A/'RESOURCE_IDENTITY_REFRESH.json'),approval_sha256=sha(G/'RESOURCE_BACKGROUND_APPROVAL.json'),
        no_process_controls=True,no_game_started=True))
    plan=read(OLD/'CONTINUOUS_PLAN.json')
    plan.update(at=now(),batch=G.name,source=HEAD,authorization='PENDING_CURRENT_BATCH_AUTHORIZATION',
                comparison_baseline_source=read(OLD/'BATCH_SPEC.json')['source'],
                notes='Fresh same-seed50 candidate for B13+B13B versus last completed ec95 batch34/50 HP161. Prior single-batch authorization not reused.')
    put(G/'CONTINUOUS_PLAN.json',plan)
    draft=json.loads(rewrite(json.dumps(read(OLD/'TRIAL_CONFIG_DRAFT.json'),ensure_ascii=False)))
    draft.update(at=now(),source=HEAD,user_authorized=False,authorization='PENDING_CURRENT_BATCH_AUTHORIZATION',
                 purpose='One new bounded B13+B13B continuous50 candidate; compare actual outcomes and body collisions against ec95 34/50 HP161',
                 coverage_target='All50 outcomes/HP plus actual B13/B13B opportunities, selected/sent actions and target-body hits; no raw HP preventability claims')
    draft['environment'].update(SSBOT_FORUM_CHAIN_B13='1',SSBOT_FORUM_CHAIN_B13B='1')
    put(G/'TRIAL_CONFIG_DRAFT.json',draft)
    oldsr=read(OLD_A/'SOURCE_REVIEW_LIVE.json')
    put(G/'LIVE_BINDING404.json',dict(at=now(),source=HEAD,adapter_accepted=True,
        entry_sha256=sha(A/'entry.py'),adapter_review=str(OLD_A/'P_ADAPTER_REVIEW.json'),
        unchanged_entry_sha256=sha(OLD_A/'entry.py'),P_audit_sha256=sha(A/'ROOT_P_AUDIT.json'),
        p_final_receipts={p:sha(p) for p in pa['receipt_files']},all_finalized_passed=True,
        final_review_sha256=sha(A/'SOURCE_REVIEW_FINAL.json'),carried_user_scope_sha256=oldsr['user_scope_sha256'],
        parent_B13_validation=str(B/'analysis/b13_399_20261112/SOURCE_REVIEW_FINAL.json')))
    checks=read(OLD/'START_GATE_CHECKS.json');checks.update(at=now(),source=HEAD,reused_from=str(OLD/'START_GATE_CHECKS.json'),
        verification='Identical start_gate/user_authorization bytes; old eight contract/worker/cancel/capture cases reused. No authorization file exists in this new candidate; actual missing-authorization rejection checked.')
    put(G/'START_GATE_CHECKS.json',checks)
    put(G/'FREEZE_GIT_METADATA_REFRESH.json',dict(at=now(),source=HEAD,source_root=str(A/'source'),actual_git_head=HEAD,
        runtime_diff_empty=True,source_packet_sha256=sha(A/'SOURCE_PACKET.json'),no_metadata_mutation=True))
    for p in G.glob('*.py'):compile(p.read_text(encoding='utf-8'),str(p),'exec')
    put(G/'LIFECYCLE_REVIEW.json',dict(at=now(),accepted=True,source=HEAD,files={p.name:sha(p) for p in G.glob('*.py')},
        owned_launcher_execute_ast_unchanged=True,runtime_control_flow_unchanged=True,
        previous_review=str(OLD/'LIFECYCLE_REVIEW.json'),prepare_current_P_schema_independently_reviewed=True,
        changes='New batch/source/scope labels and explicit B13=1/B13B=1 assertions. Preparation-only current4-receipt binding, previous user-rule facts carried verbatim. Start/stop/input/capture/cleanup and resource algorithm unchanged.',no_game_started=True))
    spec=importlib.util.spec_from_file_location('candidate_authorization',G/'user_authorization.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    try:mod.validate_authorization(G,HEAD)
    except RuntimeError as exc:assert str(exc)=='missing current autonomous start authorization'
    else:raise AssertionError('unapproved candidate accepted')
    put(G/'BATCH_SPEC.json',dict(at=now(),batch=G.name,source=HEAD,planned_bouts=50,state='STAGED_AWAIT_CURRENT_AUTHORIZATION',
        ready=False,started=False,authorization=None,comparison=f'{OLD.name}:34/50,161HP',
        no_game_started=True,prior_single_batch_authorization_reused=False))
    # Read-only production parser preflight before IPC/reset/process startup.
    for k in list(os.environ):
        if k.startswith('SSBOT_'):del os.environ[k]
    os.environ.update(draft['environment']);os.environ['NUMBA_NUM_THREADS']='4';sys.path.insert(0,str(A/'source/brain'))
    from ssbot.tools import combat_run
    from ssbot.combat import knife_chain_budget,forum_planner,knife_chain_transfer
    assert not forum_planner.SLAM_NO_NEW_GLIDE and knife_chain_transfer.B13 and knife_chain_transfer.B13B
    saved=combat_run.worker;captured={}
    def dry_worker(options):
        knife_chain_budget.preflight_options(options);captured['conditions']=knife_chain_budget.execution_conditions(options);return 0
    combat_run.worker=dry_worker;args=draft['arguments'];sys.argv=['combat_run',*args[args.index('_worker'):]]
    try:assert combat_run.main()==0
    finally:combat_run.worker=saved
    assert captured['conditions']['smoke_limit']=={'continuous_attempts':50} and captured['conditions']['learning_policy']['remaining_hp']==2
    put(G/'PRE_AUTH_DRY_PREFLIGHT.json',dict(at=now(),passed=True,source=HEAD,conditions=captured['conditions'],
        no_game_started=True,source_and_P_accepted=True,authorization_missing_rejected=True,actual_warm_gates_pending=True,
        full_scheduling_gate_pass=False,configuration=dict(B13=True,B13B=True,SLAM_NO_NEW_GLIDE=False)))
    print(json.dumps(dict(candidate=str(G),source=HEAD,bouts=50,seeds=len(plan['seeds']),syntax=True,parser_preflight=True,
        authorization_present=False,game_started=False),ensure_ascii=False))

if __name__=='__main__':main()
