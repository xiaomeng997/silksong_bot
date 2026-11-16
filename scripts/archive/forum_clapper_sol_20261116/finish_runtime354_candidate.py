"""Finish a staged runtime354 candidate only after its actual bounded user reply."""
from pathlib import Path
import datetime,hashlib,importlib.util,json,os,sys
import psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');G=Path(__file__).resolve().parent;A=B/'analysis/runtime354_20261113';D=B/'sol/demos'/G.name
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def put(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def main():
 spec=read(G/'CANDIDATE_SPEC.json');sr=read(A/'SOURCE_REVIEW_FINAL.json');head=spec['source'];n=spec['planned_bouts']
 assert sr['accepted'] and sr['source']==head and sr['replay_P_not_affected']
 assert not D.exists() and not (G/'ENGINEERING_GATE.json').exists() and not (G/'START_AUTHORIZATION.json').exists()
 auth=read(G/'USER_NEW50_AUTHORIZATION.json');assert auth['planned_bouts']==n and auth['source']==head and auth['batch_id']==G.name
 assert auth['kind']==spec['authorization_kind'] and auth['ready_dialog_required'] is False
 required=[A/'SOURCE_REVIEW_FINAL.json',A/'SOURCE_PACKET.json',A/'VALIDATION_PLAN.json',G/'CANDIDATE_SPEC.json',G/'LIFECYCLE_REVIEW.json',G/'START_GATE_CHECKS.json']
 if n==50:
  proof=A/'REAL_RUNTIME_PROBE_AUDIT.json';p=read(proof)
  assert p['source']==head and p['passed'] and p['physical_cleanup_verified'] and p['actual_gc_threshold_verified'] and p['actual_stop_freeze_verified']
  required.append(proof)
 st=read(B/'sol/STATUS.json');assert st['current_source']==head and not st['source_review_pending']
 assert not st['live_or_budget_running'] and not st.get('own_live_session') and not st.get('own_offline_jobs')
 assert not (B/'sol/performance/ACTIVE.json').exists()
 lc=read(G/'LIFECYCLE_REVIEW.json');assert lc['accepted'] and all(sha(G/k)==v for k,v in lc['files'].items())
 draft=read(G/'TRIAL_CONFIG_DRAFT.json');assert draft['source']==head and draft['user_authorized'] and draft['authorization']==auth['user_text']
 assert draft['environment']['SSBOT_FORUM_CHAIN_B13']==draft['environment']['SSBOT_FORUM_CHAIN_B13B']=='1'
 assert draft['environment']['SSBOT_FORUM_SLAM_NO_NEW_GLIDE']=='0'
 for k in list(os.environ):
  if k.startswith('SSBOT_'):del os.environ[k]
 os.environ.update(draft['environment']);os.environ['NUMBA_NUM_THREADS']='4';sys.path.insert(0,str(A/'source/brain'));sys.path.insert(0,str(G))
 from ssbot.tools import combat_run
 from ssbot.combat import knife_chain_budget
 capture={};saved=combat_run.worker;args=draft['arguments'];sys.argv=['combat_run',*args[args.index('_worker'):]]
 def dry(options):knife_chain_budget.preflight_options(options);capture['conditions']=knife_chain_budget.execution_conditions(options);return 0
 combat_run.worker=dry
 try:assert combat_run.main()==0
 finally:combat_run.worker=saved
 assert capture['conditions']['smoke_limit']=={'continuous_attempts':n}
 put(G/'ROOT_DRY_PREFLIGHT.json',dict(at=now(),source=head,passed=True,conditions=capture['conditions'],game_started=False))
 from ssbot.tools.launcher import Launcher,current_prefs,read_reg_file,prefs_diff
 launch=Launcher(tile=False);launch.preflight([0]);diff=prefs_diff(current_prefs(launch.guard.store),read_reg_file(launch.guard.golden));assert not diff
 reg=launch.guard.status();assert not reg['live'] and not reg.get('restore_pending')
 assert not [p.pid for p in psutil.process_iter(['name']) if 'silksong' in (p.info['name'] or '').lower()]
 import engineering_helpers as eh
 old=B/'analysis/w13_50_b13b404_20261113';assert read(old/'ROOT_CLEANUP.json')['physical_cleanup_complete']
 accepted=sorted(set(read(old/'ENGINEERING_GATE.json')['accepted_opus_numbers'])|set(range(405,411)))
 assert not eh.new_blockers(accepted)
 res=eh.resource_guard();put(G/'ROOT_RESOURCE_PREFLIGHT.json',res);assert not res['blockers'],res['blockers']
 put(G/'ENVIRONMENT_PREFLIGHT.json',dict(at=now(),passed=True,registry=reg,prefs_diff=diff,resource=res,no_game_started=True,golden_sha256=sha('C:/ssbot/sandbox/prefs/golden.reg'),old_demo_sha256=sha('C:/ssbot/sandbox/DEMO_SOON')))
 put(G/'PREPARE_AUTHORIZATION.json',dict(at=now(),batch_id=G.name,source=head,prepare_authorized=True,combat_requires_new_ready=False,user_request=auth['user_text'],authorization_receipt=str(G/'USER_NEW50_AUTHORIZATION.json')))
 evidence={}
 for p,h in read(old/'ENGINEERING_GATE.json')['evidence'].items():
  if Path(p).name in ['EDGE258.json','b2_input_path_i0.json','SsOracle.dll']:
   assert sha(p)==h;evidence[p]=h
 for p in required+[G/'ROOT_DRY_PREFLIGHT.json',G/'ROOT_RESOURCE_PREFLIGHT.json',G/'ENVIRONMENT_PREFLIGHT.json',G/'USER_NEW50_AUTHORIZATION.json',G/'PREPARE_AUTHORIZATION.json',G/'CONTINUOUS_PLAN.json',G/'RESOURCE_BACKGROUND_APPROVAL.json',G/'RESOURCE_BACKGROUND_CLASSIFICATION_CHECKS.json',*G.glob('*.py')]:evidence[str(p)]=sha(p)
 gate=dict(at=now(),planned_id=G.name,batch_id=G.name,scope=spec['scope'],ready=True,user_authorized=True,authorization=auth['user_text'],source=head,execution_head=head,source_packet=str(A/'SOURCE_PACKET.json'),source_review_pass=True,standalone_transport_gate=True,worker_input_gate=True,actual_new_worker_receipt_required=True,full_scheduling_gate_pass=False,smoke8_authorized=False,scoped_engineering_timing_pass=False,replay_P_not_affected=True,accepted_opus_numbers=accepted,evidence=evidence,active_source_at_preflight=head,total_bouts=n,remaining_bouts=n,user_ready_required=False,combat_requires_new_ready=False,combat_start_authorization=spec['authorization_kind'],pending=['Actual warm worker/input/capture/resource gate and GO'],formal_coverage_note='Changed worker lifecycle only; unchanged replay P does not call it. Probe actual quiet GC timing and safe-stop are required before the new50.')
 put(G/'ENGINEERING_GATE.json',gate)
 ms=importlib.util.spec_from_file_location('runtime354_trial',G/'trial.py');m=importlib.util.module_from_spec(ms);ms.loader.exec_module(m);m.prepare();contract=D/'contract.json';m.verify(read(contract))
 put(G/'START_AUTHORIZATION.json',dict(at=now(),kind=spec['authorization_kind'],batch_id=G.name,source=head,contract_sha256=sha(contract),authorization_receipt=str(G/'USER_NEW50_AUTHORIZATION.json'),authorization_receipt_sha256=sha(G/'USER_NEW50_AUTHORIZATION.json'),user_text=auth['user_text']))
 m.check_prepare_authorized(head);m.check_user_ready(head)
 ready=dict(at=now(),source=head,engineering_preparation_complete=True,trial_prepared=True,game_started=False,ready_dialog_required=False,actual_warm_gate_pending=True,bouts=n,contract_sha256=sha(contract))
 put(G/'READY_FOR_WARM_START.json',ready);bs=read(G/'BATCH_SPEC.json');bs.update(state='PREPARED_READY_FOR_WARM_START',ready=True,gate_ready=True);put(G/'BATCH_SPEC.json',bs)
 print(json.dumps(ready,ensure_ascii=False))
if __name__=='__main__':main()
