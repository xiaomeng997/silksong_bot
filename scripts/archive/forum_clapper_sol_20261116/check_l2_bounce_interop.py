"""Bounded E-only review checks; no policy replay, P measurement or game."""
from pathlib import Path
import datetime,hashlib,json,os,sys,traceback,psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/l2_bounce_interop_20261106';D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');S='9f6da15674da8c396d729a680f6868d47d9e233f'
sys.path.insert(0,str(D/'brain'));sys.dont_write_bytecode=True
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(n,d):
 p=A/n;assert not p.exists(),p;p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def atom(d):
 p=B/'sol/STATUS.l2bounce.tmp';p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(p,B/'sol/STATUS.json')
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st['source_frozen_for_P'] and not st.get('own_offline_jobs') and st['current_source']==S
assert not A.exists();A.mkdir()
me=psutil.Process();me.cpu_affinity(list(range(24,32)));me.nice(psutil.IDLE_PRIORITY_CLASS)
job=dict(pid=me.pid,created=me.create_time(),cpus=me.cpu_affinity(),priority=me.nice(),phase='bounded existing bounce/target entry checks and actual bounce-handoff component variants')
put('ROOT_JOB.json',job);st.update(at=now(),phase='L2_BOUNCE_INTEROP_REVIEW_CHECKS',own_offline_jobs=[job]);atom(st)
err=None
files=['combat/knife_chain_bounce_table.py','combat/knife_chain_air_native.py','combat/knife_chain_transfer.py','combat/knife_chain_b2.py','combat/tactics/clapper_tactics.py','combat/tactics/clapper_middle.py','train/forum_planner_policy.py']
before={f:sha(D/'brain/ssbot'/f) for f in files}
try:
 import pytest
 names=[
 'test_bounce_table309.py::test_a_real_same_target_bounce_anchors_the_table_with_the_existing_source_responsibility',
 'test_bounce_table309.py::test_outside_the_same_target_domain_the_existing_bounce_goal_stays',
 'test_bounce_table309.py::test_responsibility_follows_the_first_new_antic_and_a_second_new_instance_recovers',
 'test_bounce_table309.py::test_a_late_table_key_is_kept_only_when_it_equals_the_key_before_it',
 'test_bounce_table309.py::test_the_single_row_verification_runs_once_after_the_sighting_send',
 'test_target_entry_attack.py::test_intent_cannot_fabricate_an_entry_or_interrupt_a_commitment',
 'test_target_entry_attack.py::test_side_intent_retains_old_hammer_tail_then_hands_to_ordinary_attacks',
 'test_target_entry_attack.py::test_real_bounce_uses_hit_targets_slam_tail_not_previous_cast_responsibility',
 'test_target_entry_attack.py::test_target_slam_starting_at_actual_bounce_is_bound_or_handed_to_normal_planner',
 'test_target_entry_attack.py::test_delayed_switch_binding_cannot_outlive_its_intent_unless_already_committed']
 rc=pytest.main(['-q','-p','no:cacheprovider','--basetemp='+str(A/'pytest_tmp'),'--junitxml='+str(A/'CHECKS.xml'),*[str(D/'brain/tests'/n) for n in names]])
 assert rc==0,rc
 from types import SimpleNamespace as NS
 from tests.test_bounce_table309 import anchored,scene,prefs,HIT
 from ssbot.combat.knife_chain_commitment import MoveInstance
 from ssbot.combat import knife_chain_bounce_table as BT
 from ssbot.combat import knife_chain_transfer as T
 cases=[]
 for target in (7,8):
  with pytest.MonkeyPatch.context() as mp:
   n,s=anchored(mp);old=n.commitment.copy();n._clock_known=True;n._clock=20.
   # A mid-flight tactical change must not replace the committed old sequence.
   assert n.observe_bounce_goal(s,prefs(target),NS(iid=7,fa=946,ta=19.,phase='after')) is False
   assert n.commitment==old and n._bounce.chain.iid==7
   cases.append(dict(case='active_commitment',target=target,old_table_target=n._bounce.chain.iid,commitment_preserved=True))
 for state in ('Slam 2','Slam Recover'):
  with pytest.MonkeyPatch.context() as mp:
   n,s=anchored(mp);n._clock_known=True;n._clock=20.;f=HIT+14;s=scene(f=f,target_state=state,hit=7)
   # A production-shaped checkpoint of base B2's real-hit+bounce handback. This is a component fixture,
   # not a claim to have driven a full policy/planner/sent continuation or a physical receipt.
   source=MoveInstance(7,946,'CC_SLAM');n.post_context={**n.commitment,'bounce':f,'hit':f,'press':f-7};n.commitment=None
   n.post_context.update(move=source,ta=19.)
   assert n.observe_bounce_goal(s,prefs(8))
   goal=n._transfer_goal
   assert n._bounce is None and goal.target==8 and goal.caster==7 and goal.responsibility==source and goal.cast_ta==19.
   pending=T.bounce_tail_pending(s,goal,20.)
   assert pending==(state=='Slam 2')
   cases.append(dict(case='real_bounce_handoff_checkpoint',state=state,new_target=goal.target,caster=goal.caster,source_move=vars(source),source_clock=goal.cast_ta,old_table_released=True,old_tail_pending=pending,scope='component checkpoint only; base handback state and target preference supplied'))
 assert all(sha(D/'brain/ssbot'/f)==h for f,h in before.items())
 foreign=[str(m.__file__) for k,m in sys.modules.items() if k.startswith('ssbot') and getattr(m,'__file__',None) and not Path(m.__file__).resolve().is_relative_to(D)]
 assert not foreign,foreign
 put('REVIEW_CHECKS.json',dict(at=now(),source=S,pytest_rc=rc,cases=cases,source_files_sha256=before,foreign=foreign,production_policy_replays=0,formal_P=0,games=0,limits=['Existing tests are component fixtures; row verification in bounce_table309 is stubbed','No full L2 policy + repeated real hits + cross-target approach/strike/sent end-to-end witness','Finite same-target bounce table remains default off and does not certify cross-target timing']))
 print(json.dumps(dict(rc=rc,component_variants=len(cases),production_policy_replays=0,formal_P=0,games=0)))
except BaseException as e:
 err=repr(e);put('ERROR.json',dict(at=now(),error=err,traceback=traceback.format_exc()));raise
finally:
 put('ROOT_JOB_END.json',dict(at=now(),job=job,error=err));# Caller clears only after actual exit.
