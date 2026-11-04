"""Manual approach: actual focus, dash timing and jump continuity."""
from copy import deepcopy
from types import SimpleNamespace as NS
import numpy as np
from ssbot.combat.knife_chain_air import load_runner
from ssbot.combat.knife_chain_eval import Run,X
from ssbot.combat.knife_chain_transfer import TransferPlan,render,visible,path_problem
from ssbot.combat.knife_chain_format import MASK_NAMES as B
import pytest


def plan():return TransferPlan(8,7,1000,1000,0.,B["L"],5,12,36,True,1000,0)


def test_transfer_table_walk_dash_jump_and_air_release_dash():
 r=load_runner();p=plan()
 assert render(r,p,0,2).tolist()==[B["L"],B["L"]]
 assert render(r,p,3,1)[0]==B["L"]|B["DASH"]
 assert render(r,p,10,1)[0]==B["L"]|B["DASH"]|B["J"]
 assert render(r,p,12,1,"air")[0]==B["L"]|B["J"]
 assert render(r,p,35,1,"air")[0]==B["L"]


def test_observed_overhead_alone_is_not_a_handoff_or_fake_bounce():
 r=load_runner();p=plan();r.run=Run("rune_transfer","air",p.variables())
 obs=NS(f=1010,F=1012,k=12,target_valid=True,ground=False,overhead=True)
 assert r.eval_link(X(r,r.run,obs))==B['L']|B['J'] and r.run is not None
 assert not r.run.v.get('bounced')


def test_transfer_availability_is_only_ground_cast_entry():
 e=lambda i,st,t:{"iid":i,"type_key":"Song Heavy Sentry","hp":100,"pos":[20.,7.45],"fsms":[{"name":"Control","state":st,"t":t}]}
 s={"hero":{"box":[22.,3.015,22.5,5.1],"hero_accepting_input":True},"ents":[e(7,"Spell Antic",0.),e(8,"Idle",0.)]}
 assert visible(s)
 late=deepcopy(s);late["ents"][0]["fsms"][0]["t"]=.3;assert not visible(late)
 air=deepcopy(s);air["hero"]["box"][1]=5.;assert not visible(air)
 unknown=deepcopy(s);unknown["hero"]["box"][1]=None;assert not visible(unknown)


@pytest.mark.parametrize('target_state',[
 'Idle','Walk','Dmg Attack','Evade Scuttle','Spell Antic','Cast 1','Cast 2',
 'Slam Recover','Slam Antic','Slam 0','Slam 1','Slam 2',
 'Jump Antic','Cast Slam Antic','Jump','Air',
])
def test_visible_cast_records_destination_in_any_live_target_state(target_state):
 # Goal intent is independent of which blade can execute against this move.
 # A later blade adapter must still check the target's actual attack geometry.
 from ssbot.combat.knife_chain_transfer import observe_goal
 r=load_runner();s=cast_scene()
 s['ents'][1]['fsms'][0].update(state=target_state,t=.4)
 goal=observe_goal(s,None,r.chains['rune_transfer'].cfg,set())
 assert goal is not None and goal.target==8 and goal.caster==7


def test_transfer_jump_edge_is_allowed_only_from_ground():
 from ssbot.knowledge import kinematics as K
 states=np.zeros((K.K,4));states[K.GROUND,0]=1.;latched=np.array([B["J"],B["J"],B["J"]])
 hold=K.HoldState.idle(1);p=NS(states=states,latched=latched)
 assert path_problem(p,hold) is None
 states[K.GROUND,0]=0.;assert path_problem(p,hold)=="transfer represses jump in air"
 states[K.GROUND,0]=1.;states[K.MODE,2]=K.M_GLIDE;assert "umbrella" in path_problem(p,hold)



def test_replanned_existing_ground_jump_does_not_spend_air_dash():
 from pathlib import Path
 from ssbot.knowledge import kinematics as K
 from ssbot.combat.air_chain import ChainSim
 from ssbot.combat.knife_chain_transfer import propose
 root=Path(__file__).resolve().parents[2]
 params=K.hero2(K.HeroParams.load(root/"knowledge/1.0.30000/kinematics/hero_wanderer_forum.json"))
 e=lambda i,st,x:{"iid":i,"type_key":"Song Heavy Sentry","hp":100,"pos":[x,7.45],"flipX":True,"fsms":[{"name":"Control","state":st,"t":0.}],"colliders":[{"name":"Song Heavy Sentry","enabled":True,"verts_world":[x-1.4,3.,x+1.9,3.,x+1.9,6.9,x-1.4,6.9]}]}
 s={"f":1060,"hero":{"pos":[30.,4.568],"box":[29.75,3.015,30.25,5.1],"vel":[-8.25,0.],"health":7,"hero_accepting_input":True,"tm":{"dash_cd":0.}},"ents":[e(7,"Cast 2",47.),e(8,"Walk",24.)],"act":{"hf":{"latched":B["L"],"desired":B["L"],"pending":[0]*22,"age":[100]*22}}}
 S=K.initial_state(params,30.,4.568,vx=-8.25,facing=-1,ground=True)
 sim=ChainSim(S,np.array([B["J"]|B["R"]],np.int64),K.HoldState.from_act(s["act"]),params,K.Terrain2D.empty(),1060,1060)
 r=load_runner();r.run=Run("rune_transfer","walk",plan().variables())
 made=propose(r,s,1.,sim,8,True,np.zeros((0,6)),set())
 assert made is not None and made[0] is not None
 assert made[3]&B["J"] and not made[3]&B["DASH"]
 assert not made[1].sprint_jump and path_problem(made[2],sim.hold) is None



def test_transfer_ownership_and_hit_watch_begin_only_after_successful_send():
 from ssbot.combat.knife_chain_air_native import NativeManualAirChain
 from ssbot.combat.knife_chain_b2 import B2Offer
 from ssbot.combat.knife_chain_air import AirAnchor
 r=load_runner();p=plan();draft=r.fork_empty(AirAnchor());draft.run=Run("rune_transfer","walk",p.variables())
 e=lambda i,st:{"iid":i,"type_key":"Song Heavy Sentry","hp":100,"pos":[20.,7.45],"fsms":[{"name":"Control","state":st,"t":0.}]}
 s={"f":1000,"dt":1/60,"hero":{"health":7,"box":[22.,3.015,22.5,5.1],"hero_accepting_input":True},"ents":[e(7,"Spell Antic"),e(8,"Idle")],"act":{"target":1000,"applied":1000,"mask":0,"hf":{"latched":0,"desired":0,"pending":[0]*22,"age":[100]*22}},"ev":[]}
 n=NativeManualAirChain(runner_factory=load_runner,probe_ref="transfer-test");n.reset(0,start_frame=1000);n.begin(s)
 offer=B2Offer("manual_commitment",None,draft,B["L"],0.,p.move,{"manual_air":True,"rune_transfer":True,"caster":7,"cast_fa":1000})
 planner=NS(measurement_enabled=False,jump_until=1100,macro_until=1150)
 res=n.install(offer,planner);assert planner.jump_until==planner.macro_until==-1
 n.planner_result(res);n.final("plan",B["L"])
 n.before_send(frame=1000,target=1002,mask=B["L"],flags=0,received_frame=1000)
 assert n.runner.run is None and n.commitment is None
 n.sent()
 assert n.runner.run.chain=="rune_transfer" and n.commitment['move']==p.move
 assert (7,1000) in n._transfer_finished
 n.reset(1);assert not n._transfer_finished and not n._transfer_ready


def test_transfer_no_takeoff_does_not_hold_dash_until_the_whole_route_times_out():
 r=load_runner();p=plan();r.run=Run('rune_transfer','jump',p.variables())
 obs=NS(f=1040,F=1042,k=42,target_valid=True,ground=True,overhead=False)
 assert r.eval_link(X(r,r.run,obs)) is None and r.run is None
 assert 'without observed takeoff' in r.done[-1].v['why']


def test_real_transfer_bounce_reuses_the_existing_vault_exit_and_keeps_caster_identity():
 from ssbot.combat.knife_chain_air_native import NativeManualAirChain
 from ssbot.combat.knife_chain_vault_native import load_runner as combined
 n=NativeManualAirChain(runner_factory=combined,probe_ref='rune-existing-exit');n.reset(0,start_frame=1000)
 n.begin(cast_scene());p=plan();n.runner.run=Run('rune_transfer','strike',p.variables())
 n._actual_state=cast_scene()  # helper-only fixture; the full hit observer is tested below
 n._hit=1000;n._press=998;n.post_context={'move':p.move,'bounce':1000,'hit':1000,'press':998}
 n._transfer_bounce_exit()
 assert n.runner.run.chain=='vault_idle' and n.runner.run.link=='over'
 assert n.runner.run.v['bounced'] and n.runner.run.v['down_hit_f']==1000
 assert n.runner.run.v['_native_vault']['move']==vars(p.move)
 assert n.runner.run.v['_native_vault']['buddy']==7 and n.post_context is None


def cast_scene():
 e=lambda i,st,x:{"iid":i,"type_key":"Song Heavy Sentry","hp":100,"pos":[x,7.45],"fsms":[{"name":"Control","state":st,"t":0.}]}
 return {"f":1000,"hero":{"health":7,"pos":[30.,8.],"box":[29.75,6.5,30.25,8.6]},"ents":[e(7,"Spell Antic",25.),e(8,"Idle",38.)]}


def test_antic_goal_is_observed_in_air_and_survives_until_landing_after_entry_window():
 from ssbot.combat.knife_chain_transfer import observe_goal
 r=load_runner();cfg=r.chains["rune_transfer"].cfg;s=cast_scene()
 goal=observe_goal(s,None,cfg,set())
 assert (goal.target,goal.caster,goal.cast_fa)==(8,7,1000)
 later=deepcopy(s);later["f"]=1030;later["hero"]["box"][1]=3.015
 later["ents"][0]["fsms"][0].update(state="Cast 1",t=.1)
 assert observe_goal(later,goal,cfg,set())==goal
 assert observe_goal(later,None,cfg,set()) is None
 assert observe_goal(s,None,cfg,{(7,1000)}) is None


def test_selected_destination_preserves_preferences_without_creating_run_or_sent_keys():
 from ssbot.combat.knife_chain_air_native import NativeManualAirChain
 from ssbot.combat.knife_chain_transfer import observe_goal
 from ssbot.combat.tactics.modes import GoalPrefs
 n=NativeManualAirChain(runner_factory=load_runner,probe_ref="goal-test");n.reset(0,start_frame=999)
 s=cast_scene();n._transfer_goal=observe_goal(s,None,n.runner.chains["rune_transfer"].cfg,set())
 old=GoalPrefs(mode="RUSH",stance_x=38.,weights={},target=8,region=(37.,39.,3.,5.,"GROUND"))
 new=n.goal_preferences(s,old,handoff=True)
 assert new.target==8 and new.stance_x==38. and new.region==old.region
 assert old.target==8 and old.stance_x==38. and old.region is not None
 assert n._transfer_ready and n.runner.run is None and n.commitment is None
 assert not n._transfer_finished and not n._receipts
 n.commitment={"move":"previous strike"}
 assert n.goal_preferences(s,old,handoff=True) is old
 assert not n._transfer_ready
 n.commitment=None
 assert n.goal_preferences(s,old,handoff=False) is old
 n.reset(1);assert n._transfer_goal is None


def test_policy_handoff_releases_only_observed_bounced_after_not_incomplete_strike():
 from ssbot.train.forum_planner_policy import ForumPlannerPolicy as Policy
 from ssbot.combat.knife_chain_air_native import NativeManualAirChain
 from ssbot.combat.knife_chain_transfer import observe_goal
 from ssbot.combat.tactics.modes import GoalPrefs
 n=NativeManualAirChain(runner_factory=load_runner,probe_ref="goal-owner");n.reset(0,start_frame=999)
 s=cast_scene();n._transfer_goal=observe_goal(s,None,n.runner.chains["rune_transfer"].cfg,set())
 old=GoalPrefs(mode="RUSH",stance_x=38.,weights={},target=8)
 p=Policy.__new__(Policy);p.chain_native=n;aborted=[]
 p.slam_play=NS(run=NS(phase="air",bounced=False),abort=aborted.append)
 assert p._chain_goal_preferences(s,old) is old and not aborted
 p.slam_play.run.phase="after"
 assert p._chain_goal_preferences(s,old) is old and not aborted
 p.slam_play.run.bounced=True
 assert p._chain_goal_preferences(s,old).target==8
 assert aborted==["observed target transfer: goal handoff"]
 p.chain_native=None
 assert p._chain_goal_preferences(s,old) is old


def test_next_visible_cast_replaces_pending_destination_without_waiting_for_old_expiry():
 from ssbot.combat.knife_chain_transfer import observe_goal
 cfg=load_runner().chains["rune_transfer"].cfg;s=cast_scene();first=observe_goal(s,None,cfg,set())
 s["f"]=1060;s["ents"][0]["fsms"][0].update(state="Idle",t=0.)
 s["ents"][1]["fsms"][0].update(state="Spell Antic",t=0.)
 next_goal=observe_goal(s,first,cfg,set())
 assert (next_goal.target,next_goal.caster,next_goal.cast_fa)==(7,8,1060)


@pytest.mark.parametrize('kind',['Jump Antic','Cast Slam Antic','Jump','Air'])
def test_missing_blade_retains_the_destination_without_exempting_target_attack(kind):
 from ssbot.combat.knife_chain_air_native import NativeManualAirChain
 from ssbot.combat.knife_chain_transfer import observe_goal
 from ssbot.combat.tactics.modes import GoalPrefs
 n=NativeManualAirChain(runner_factory=load_runner,probe_ref='blade-gap');n.reset(0,start_frame=999)
 s=cast_scene();s['ents'][1]['fsms'][0].update(state=kind,t=.4)
 goal=observe_goal(s,None,n.runner.chains['rune_transfer'].cfg,set());n._transfer_goal=goal
 prefs=GoalPrefs(mode='RUSH',stance_x=38.,weights={},target=8)
 assert n.goal_preferences(s,prefs,handoff=True).target==8
 assert n._transfer_goal==goal and not n._transfer_ready
 assert n._transfer_blade[2]=='unavailable' and n.commitment is None


def test_real_bounce_releases_legacy_after_on_the_same_tick_before_velocity_marker():
 from ssbot.train.forum_planner_policy import ForumPlannerPolicy as Policy
 from ssbot.combat.knife_chain_air_native import NativeManualAirChain
 from ssbot.combat.knife_chain_commitment import MoveInstance
 from ssbot.combat.tactics.modes import GoalPrefs
 n=NativeManualAirChain(runner_factory=load_runner,probe_ref='same-tick-bounce');n.reset(0,start_frame=999)
 s=cast_scene();s['hero']['cstate_int']=[0,8]
 s['ev']=[{'k':'hit','f':1000,'d':{'ent':7,'src':'DownSlashAlt'}}]
 s['ents'][0]['fsms'][0]['state']='Slam 1'
 p=Policy.__new__(Policy);p.chain_native=n;aborted=[]
 p.slam_play=NS(run=NS(iid=7,fa=946,ta=2.,phase='after',bounced=False),abort=aborted.append)
 prefs=GoalPrefs(mode='RUSH',stance_x=38.,weights={},target=8)
 assert p._chain_goal_preferences(s,prefs).target==8 and aborted
 assert n._transfer_goal.source_kind=='BOUNCE' and n._transfer_ready
 assert n._transfer_goal.responsibility==MoveInstance(7,946,'CC_SLAM')
 assert n._transfer_goal.cast_ta==2. and not p.slam_play.run.bounced


@pytest.mark.parametrize('change',['no_hit','harpoon','no_bounce','old_event','other_target','not_after'])
def test_bounce_goal_does_not_release_a_strike_without_matching_actual_evidence(change):
 from ssbot.combat.knife_chain_air_native import NativeManualAirChain
 from ssbot.combat.tactics.modes import GoalPrefs
 n=NativeManualAirChain(runner_factory=load_runner,probe_ref='bounce-negative');n.reset(0,start_frame=999)
 s=cast_scene();s['hero']['cstate_int']=[0,8]
 s['ev']=[{'k':'hit','f':1000,'d':{'ent':7,'src':'DownSlash'}}]
 run=NS(iid=7,fa=946,ta=2.,phase='after')
 if change=='no_hit':s['ev']=[]
 elif change=='harpoon':s['ev'][0]['d']['src']='Harpoon'
 elif change=='no_bounce':s['hero']['cstate_int']=[0,0]
 elif change=='old_event':s['ev'][0]['f']=990
 elif change=='other_target':s['ev'][0]['d']['ent']=8
 elif change=='not_after':run.phase='air'
 assert not n.observe_bounce_goal(s,GoalPrefs(mode='RUSH',stance_x=38.,weights={},target=8),run)
 assert n._transfer_goal is None and n.commitment is None


@pytest.mark.parametrize('retained_hit',[False,True])
def test_native_real_bounce_switches_to_next_goal_instead_of_old_vault_exit(retained_hit):
 from ssbot.combat.knife_chain_air_native import NativeManualAirChain
 from ssbot.combat.knife_chain_transfer import TransferGoal
 from ssbot.combat.knife_chain_commitment import MoveInstance
 from ssbot.combat.tactics.modes import GoalPrefs
 n=NativeManualAirChain(runner_factory=load_runner,probe_ref='native-bounce-next');n.reset(0,start_frame=999)
 s=cast_scene();s['hero']['cstate_int']=[0,8]
 s['ev']=[{'k':'hit','f':1000,'d':{'ent':8,'src':'DownSlashAlt'}}]
 move=plan().move;n.runner.run=Run('rune_transfer','strike',plan().variables())
 n.post_context={'move':move,'bounce':1000,'hit':1000,'ta':0.}
 n._transfer_responsibility[move]=(MoveInstance(7,990,'CC_CAST'),0.)
 if retained_hit:s['ev']=[];n._hit=1000
 prefs=GoalPrefs(mode='RUSH',stance_x=25.,weights={},target=7)
 assert n.observe_bounce_goal(s,prefs)
 assert n.goal_preferences(s,prefs,handoff=True).target==7
 assert n.post_context is None and n.runner.run is None and n._transfer_ready
 assert n._transfer_goal.source_kind=='BOUNCE' and n._transfer_goal.responsibility==MoveInstance(7,990,'CC_CAST')


def test_bounce_without_target_switch_releases_old_after_and_reuses_air_slice():
 from ssbot.train.forum_planner_policy import ForumPlannerPolicy as Policy
 from ssbot.combat.knife_chain_air_native import NativeManualAirChain
 from ssbot.combat.tactics.modes import GoalPrefs
 n=NativeManualAirChain(runner_factory=load_runner,probe_ref='keep-after');n.reset(0,start_frame=999)
 s=cast_scene();s['hero']['cstate_int']=[0,8]
 s['ev']=[{'k':'hit','f':1000,'d':{'ent':7,'src':'DownSlashAlt'}}]
 s['ents'][0]['fsms'][0]['state']='Slam 1'
 p=Policy.__new__(Policy);p.chain_native=n;aborted=[]
 p.slam_play=NS(run=NS(iid=7,fa=946,ta=2.,phase='after',bounced=True),abort=aborted.append)
 prefs=GoalPrefs(mode='RUSH',stance_x=25.,weights={},target=7)
 assert p._chain_goal_preferences(s,prefs).target==7 and aborted
 assert n._transfer_goal.target==n._transfer_goal.caster==7 and n._transfer_ready
 assert n._transfer_blade[2]=='air_contact' and n.commitment is None


def test_ground_pending_destination_does_not_claim_keys_from_a_new_target_attack():
 from ssbot.combat.knife_chain_air_native import NativeManualAirChain
 from ssbot.combat.knife_chain_transfer import observe_goal
 from ssbot.combat.tactics.modes import GoalPrefs
 n=NativeManualAirChain(runner_factory=load_runner,probe_ref="goal-attack-boundary");n.reset(0,start_frame=999)
 s=cast_scene();n._transfer_goal=observe_goal(s,None,n.runner.chains["rune_transfer"].cfg,set())
 s["ents"][1]["fsms"][0]["state"]="Slam Antic"
 s['hero']['box'][1]=3.015
 old=GoalPrefs(mode="RUSH",stance_x=38.,weights={},target=8)
 assert n.goal_preferences(s,old,handoff=True).target==8
 assert not n._transfer_ready and not n.candidate_generation


def test_flight_endpoint_sees_beyond_ordinary_horizon_and_stops_before_landing():
 from ssbot.knowledge import kinematics as K
 from ssbot.combat.knife_chain_transfer import flight_endpoint,head_clearance
 r=load_runner();cfg=r.chains["rune_transfer"].cfg;clear=head_clearance(cfg)
 from ssbot.combat.forum_v2 import FOCUS_M,CELL
 assert clear>=FOCUS_M+2*CELL and cfg["flight_check_frames"]>cfg["lookahead_frames"]
 states=np.zeros((K.K,73));states[K.GROUND,:3]=1.;states[K.GROUND,65:]=1.
 pos=np.zeros((73,2));pos[40:,0]=5.
 box=np.zeros((73,4));box[:,1]=7.+clear+.01
 path=NS(states=states,pos=pos,box=box)
 assert flight_endpoint(path,np.array([4.,3.,6.,7.]),clear)==(40,"overhead")
 box[:,1]=7.+clear-.01
 assert flight_endpoint(path,np.array([4.,3.,6.,7.]),clear)==(65,"landing")
 states[K.GROUND,65:]=0.
 assert flight_endpoint(path,np.array([4.,3.,6.,7.]),clear)==(None,"uncovered")


def test_transfer_checks_only_the_current_external_step_without_a_coast_retry(monkeypatch):
 from ssbot.combat import knife_chain_air_native as mod
 from ssbot.combat.knife_chain_air import AirAnchor
 n=mod.NativeManualAirChain(runner_factory=load_runner,probe_ref="prejump-coast");n.reset(0,start_frame=1000)
 n._transfer_ready=True;n._context=(None,None,None,None);p=plan();draft=load_runner().fork_empty(AirAnchor());draft.run=Run("rune_transfer","walk",p.variables())
 path=NS(through=1002);calls=[];scanned=[]
 def propose(*args,**kw):
  calls.append(kw)
  return (draft,p,path,B["L"])
 monkeypatch.setattr(mod.transfer,"propose",propose)
 monkeypatch.setattr(mod.B2Geometry,"preflight",lambda self,q:scanned.append(q) or NS(complete=True,contacts=[]))
 monkeypatch.setattr(n,"queued_prefix",lambda *a:(0,"fixture"))
 st=cast_scene();st['act']={"hf":{"latched":0}};sim=NS(prefix=np.array([0]));fc=NS(rs=NS(trk=NS(now={8:(None,None,None)})))
 offer=n._transfer_offer(st,0.,sim,fc,NS(target=8),True)
 assert calls==[{}] and scanned==[path]
 assert offer.mask==B["L"] and offer.stage=='manual_commitment'
 assert n.runner.run is None and n.commitment is None
 monkeypatch.setattr(mod.B2Geometry,"scan",lambda self,q:NS(complete=True,contacts=[NS(frame=1003,owner_iid=8,kind="body")]))
 # contacts are real dataclasses in production; use the real contact object here.
 from ssbot.combat.knife_chain_commitment import PathContact
 monkeypatch.setattr(mod.B2Geometry,"preflight",lambda self,q:NS(complete=True,contacts=[PathContact(1002,7,"delayed")]))
 assert n._transfer_offer(st,0.,sim,fc,NS(target=8),True) is None




def test_spent_transfer_has_no_false_keyboard_availability_but_active_run_can_continue():
 from ssbot.combat.knife_chain_air_native import NativeManualAirChain
 from ssbot.combat.knife_chain_transfer import observe_goal
 from ssbot.combat.tactics.modes import GoalPrefs
 n=NativeManualAirChain(runner_factory=load_runner,probe_ref="spent-cast");n.reset(0,start_frame=999);st=cast_scene()
 goal=observe_goal(st,None,n.runner.chains["rune_transfer"].cfg,set());n._transfer_goal=goal;n._transfer_finished.add((7,1000))
 old=GoalPrefs(mode="RUSH",stance_x=38.,weights={},target=8)
 assert n.goal_preferences(st,old,handoff=True) is old and n._transfer_goal==goal
 assert not n._transfer_ready and not n.candidate_generation
 n._transfer_goal=goal;n.runner.run=Run("rune_transfer","air",plan().variables())
 assert n.goal_preferences(st,old,handoff=True).target==8 and n._transfer_ready


def test_source_new_attack_does_not_erase_the_selected_destination():
 from ssbot.combat.knife_chain_air_native import NativeManualAirChain
 from ssbot.combat.knife_chain_transfer import observe_goal
 from ssbot.combat.tactics.modes import GoalPrefs
 for kind in ("Slam Antic","Jump Antic","Cast Slam Antic"):
  n=NativeManualAirChain(runner_factory=load_runner,probe_ref="caster-move");n.reset(0,start_frame=999);st=cast_scene()
  n._transfer_goal=observe_goal(st,None,n.runner.chains["rune_transfer"].cfg,set());n.runner.run=Run("rune_transfer","air",plan().variables())
  st["ents"][0]["fsms"][0]["state"]=kind
  old=GoalPrefs(mode="RUSH",stance_x=38.,weights={},target=8)
  assert n.goal_preferences(st,old,handoff=True).target==8
  assert n.runner.run is not None and n._transfer_goal is not None and n._transfer_ready


def test_small_rune_does_not_force_abandonment_of_a_good_current_target():
 from ssbot.combat.knife_chain_air_native import NativeManualAirChain
 from ssbot.combat.knife_chain_transfer import observe_goal
 from ssbot.combat.tactics.modes import GoalPrefs
 from ssbot.train.forum_planner_policy import ForumPlannerPolicy as Policy
 n=NativeManualAirChain(runner_factory=load_runner,probe_ref="keep-caster");n.reset(0,start_frame=999);st=cast_scene()
 n._transfer_goal=observe_goal(st,None,n.runner.chains["rune_transfer"].cfg,set())
 old=GoalPrefs(mode="RUSH",stance_x=25.,weights={"hit":1.},target=7,hit_w={7:3.},no_hit=frozenset({9}),no_dash=frozenset({8}))
 p=Policy.__new__(Policy);p.chain_native=n;aborted=[];p.slam_play=NS(run=NS(phase="after",bounced=True),abort=aborted.append)
 assert p._chain_goal_preferences(st,old) is old
 assert old.target==7 and old.hit_w=={7:3.} and old.no_dash==frozenset({8})
 assert not aborted and not n._transfer_ready and not n.candidate_generation


def test_selected_route_keeps_fresh_actor_state_rules_and_weights_exactly():
 from ssbot.combat.knife_chain_air_native import NativeManualAirChain
 from ssbot.combat.knife_chain_transfer import observe_goal
 from ssbot.combat.tactics.modes import GoalPrefs
 n=NativeManualAirChain(runner_factory=load_runner,probe_ref="selected-fresh-prefs");n.reset(0,start_frame=999);st=cast_scene()
 n._transfer_goal=observe_goal(st,None,n.runner.chains["rune_transfer"].cfg,set())
 old=GoalPrefs(mode="RUSH",stance_x=36.,weights={"hit":1.},target=8,hit_w={8:3.},hit_kw={8:(3.,2.,1.,0.)},no_hit=frozenset({7}),ground_hit=frozenset({8}),no_pogo=frozenset({8}),no_dash=frozenset({8}),ground_first=frozenset({8}),rune_exit=("shared",))
 new=n.goal_preferences(st,old,handoff=True)
 assert new is not old and vars(new)==vars(old) and n._transfer_ready


def transfer_motion_scene(mode):
 from pathlib import Path
 from ssbot.knowledge import kinematics as K
 from ssbot.combat.air_chain import ChainSim
 root=Path(__file__).resolve().parents[2]
 params=K.hero2(K.HeroParams.load(root/'knowledge/1.0.30000/kinematics/hero_wanderer_forum.json'))
 key=B['R']|(B['DASH'] if mode in (K.M_DASH,K.M_SPRINT) else 0)
 vel=28. if mode==K.M_DASH else params.sprint_speed if mode==K.M_SPRINT else 8.25
 s={'f':1000,'hero':{'pos':[25.,4.568],'box':[24.75,3.015,25.25,5.1],
    'vel':[vel,0.],'health':7,'hero_accepting_input':True,'tm':{'dash_cd':.25},
    'anim':{'clip':'Dash' if mode==K.M_DASH else 'Sprint' if mode==K.M_SPRINT else 'Run'}},
    'ents':[], 'act':{'hf':{'latched':key,'desired':key,'pending':[0]*22,'age':[100]*22}}}
 for iid,x,st in [(7,12.,'Cast 2'),(8,48.,'Idle')]:
  s['ents'].append({'iid':iid,'type_key':'Song Heavy Sentry','hp':100,'pos':[x,7.45],'vel':[0.,0.],
    'fsms':[{'name':'Control','state':st,'t':.1}],
    'colliders':[{'name':'Song Heavy Sentry','enabled':True,'verts_world':[x-1.4,3.,x+1.9,3.,x+1.9,6.9,x-1.4,6.9]}]})
 S=K.initial_state(params,25.,4.568,vx=vel,mode=mode,ground=True)
 if mode==K.M_DASH:S[K.DASH_T]=.05
 if mode==K.M_SPRINT:S[K.PHASE]=2.;S[K.SP_X]=vel
 terrain=K.Terrain2D.from_boxes([(-100.,-10.,100.,3.015)])
 sim=ChainSim(S,np.array([key],np.int64),K.HoldState.from_act(s['act']),params,terrain,1000,1000)
 r=load_runner();p=TransferPlan(8,7,990,1000,0.,B['R'],10,10000,10000,False,1000,0)
 r.run=Run('rune_transfer','dash' if mode in (K.M_DASH,K.M_SPRINT) else 'walk',p.variables())
 return r,s,sim


@pytest.mark.parametrize('mode_name',['M_DASH','M_SPRINT'])
def test_delaying_jump_does_not_cancel_the_existing_dash_to_sprint(mode_name):
 from ssbot.knowledge import kinematics as K
 from ssbot.combat.knife_chain_transfer import propose
 r,s,sim=transfer_motion_scene(getattr(K,mode_name))
 made=propose(r,s,0.,sim,8,True,np.zeros((0,6)),set(),defer_jump=True)
 assert made is not None and made[0] is not None
 assert made[3]==B['R']|B['DASH']
 assert made[1].dash_k==10 and made[0].run.link=='dash'
 assert not made[3]&B['J']


def test_delaying_jump_does_not_postpone_a_pending_far_dash():
 from ssbot.knowledge import kinematics as K
 from ssbot.combat.knife_chain_transfer import propose
 r,s,sim=transfer_motion_scene(K.M_NORMAL)
 made=propose(r,s,0.,sim,8,True,np.zeros((0,6)),set(),defer_jump=True)
 assert made is not None and made[1].dash_k==10
 assert made[3]==B['R'] and render(r,made[1],8,1)[0]==B['R']|B['DASH']


def transfer_at_gap(gap,mode=None):
 from ssbot.knowledge import kinematics as K
 r,s,sim=transfer_motion_scene(K.M_NORMAL if mode is None else mode)
 e=s['ents'][1];dx=s['hero']['pos'][0]+gap-e['pos'][0];e['pos'][0]+=dx
 for c in e['colliders']:c['verts_world'][::2]=[v+dx for v in c['verts_world'][::2]]
 s['hero']['tm']['dash_cd']=.025
 r.run.v['dash_k']=2  # the already-planned cooldown expires at this mask frame
 return r,s,sim


@pytest.mark.parametrize('fresh',[False,True])
@pytest.mark.parametrize('gap,dash',[(8.695,False),(12.,False),(12.01,True),(13.,True)])
def test_near_fresh_dash_uses_current_distance_when_cooldown_expires(fresh,gap,dash):
 from ssbot.combat.knife_chain_transfer import propose,TransferGoal
 r,s,sim=transfer_at_gap(gap)
 if fresh:r.run=None
 made=propose(r,s,0.,sim,8,True,np.zeros((0,6)),set(),TransferGoal(8,7,990))
 assert made is not None and made[0] is not None
 assert made[3]==B['R']|(B['DASH'] if dash else 0)


def test_near_ordinary_jump_does_not_wait_for_fresh_dash():
 from ssbot.combat.knife_chain_transfer import propose
 r,s,sim=transfer_at_gap(7.9)
 made=propose(r,s,0.,sim,8,True,np.zeros((0,6)),set())
 assert made is not None and made[3]==B['R']|B['J']
 assert not made[1].sprint_jump


def test_recovering_destination_uses_the_existing_stomp_recipe():
 from ssbot.combat.knife_chain_transfer import propose,TransferGoal
 r,s,sim=transfer_at_gap(7.9);r.run=None
 s['ents'][1]['fsms'][0]['state']='Slam Recover'
 made=propose(r,s,0.,sim,8,True,np.zeros((0,6)),set(),TransferGoal(8,7,990))
 assert made is not None and made[3]==B['R']|B['J']


def test_tail_ending_on_ground_clears_outside_entry_and_does_not_retry_own_miss():
 from ssbot.combat.knife_chain_transfer import propose,TransferGoal,MoveInstance
 r,s,sim=transfer_at_gap(7.9)
 goal=TransferGoal(8,7,990,0.,'BOUNCE',MoveInstance(7,940,'CC_SLAM'))
 r.run.link='bounce_tail';r.run.v.update(jump_k=0,jump_until=0,air_entry=True)
 made=propose(r,s,0.,sim,8,True,np.zeros((0,6)),set(),goal)
 assert made[0] is not None and made[0].run.link=='jump'
 assert not made[0].run.v['air_entry']
 # This is now our own jump. A later landing without a strike must finish it.
 r=made[0];r.run.link='air';s['f']=1010;sim.f=sim.fo=1010
 missed=propose(r,s,10/60,sim,8,True,np.zeros((0,6)),set(),goal)
 assert missed is not None and missed[0] is None


def test_tail_ending_on_ground_uses_the_same_queued_body_guard_as_air_landing():
 from ssbot.combat.knife_chain_transfer import propose,TransferGoal,MoveInstance
 r,s,sim=transfer_at_gap(1.8)
 goal=TransferGoal(8,7,990,0.,'BOUNCE',MoveInstance(7,940,'CC_SLAM'))
 r.run.link='bounce_tail';r.run.v.update(jump_k=0,jump_until=0,air_entry=True)
 made=propose(r,s,0.,sim,8,True,np.zeros((0,6)),set(),goal)
 assert made is not None and made[0] is None


@pytest.mark.parametrize('shift',[-3.2,.1,3.2])
def test_legacy_bounce_origin_is_converted_to_native_clock(shift):
 from ssbot.train.forum_planner_policy import ForumPlannerPolicy as Policy
 from ssbot.combat.knife_chain_air_native import NativeManualAirChain
 from ssbot.combat.tactics.modes import GoalPrefs
 n=NativeManualAirChain(runner_factory=load_runner,probe_ref='bounce-clock');n.reset(0,start_frame=999)
 n._clock=20.+shift;s=cast_scene();s['hero']['cstate_int']=[0,8]
 s['ev']=[{'k':'hit','f':1000,'d':{'ent':7,'src':'DownSlash'}}]
 run=NS(iid=7,fa=946,ta=19.,phase='after')
 run.bounced=False;p=Policy.__new__(Policy);p.chain_native=n;p.slam_play=NS(run=run,abort=lambda why:None)
 prefs=GoalPrefs(mode='RUSH',stance_x=38.,weights={},target=8)
 assert p._chain_goal_preferences(s,prefs,game_time=20.) is not prefs
 assert n._transfer_goal.cast_ta==pytest.approx(19.+shift)


def test_live_bounce_does_not_guess_an_unknown_legacy_clock():
 from ssbot.combat.knife_chain_air_native import NativeManualAirChain
 from ssbot.combat.tactics.modes import GoalPrefs
 n=NativeManualAirChain(runner_factory=load_runner,probe_ref='unknown-source-clock');n.reset(0,start_frame=999)
 n.require_send_clock=True;s=cast_scene();s['hero']['cstate_int']=[0,8]
 s['ev']=[{'k':'hit','f':1000,'d':{'ent':7,'src':'DownSlash'}}]
 run=NS(iid=7,fa=946,ta=19.,phase='after')
 assert not n.observe_bounce_goal(s,GoalPrefs(mode='RUSH',stance_x=38.,weights={},target=8),run)
 assert n._transfer_goal is None


@pytest.mark.parametrize('shift,expected',[(-5.,'L'),(5.,'R')])
def test_same_target_air_direction_tracks_observed_target_motion(shift,expected):
 from ssbot.knowledge import kinematics as K
 from ssbot.combat.air_chain import ChainSim
 from ssbot.combat.knife_chain_transfer import propose,TransferGoal,MoveInstance
 r,s,old=transfer_at_gap(0.);r.run.link='air'
 r.run.v.update(caster=8,side=0,jump_k=0,jump_until=0,air_entry=True)
 s['hero'].update(pos=[25.,15.],box=[24.75,13.45,25.25,15.53],vel=[0.,0.])
 s['ents'][1]['pos'][0]+=shift;s['ents'][1]['fsms'][0]['state']='Evade Scuttle'
 for c in s['ents'][1]['colliders']:c['verts_world'][::2]=[x+shift for x in c['verts_world'][::2]]
 S=K.initial_state(old.params,25.,15.,ground=False)
 sim=ChainSim(S,np.array([0]),K.HoldState.idle(1),old.params,old.terrain,1000,1000)
 goal=TransferGoal(8,8,990,0.,'BOUNCE',MoveInstance(8,940,'CC_SLAM'))
 made=propose(r,s,0.,sim,8,False,np.zeros((0,6)),set(),goal)
 assert made is not None and made[0] is not None
 assert made[1].side==B[expected] and made[3]==B[expected]


def test_target_motion_does_not_rewrite_an_already_selected_absolute_strike_row():
 from ssbot.knowledge import kinematics as K
 from ssbot.combat.air_chain import ChainSim
 from ssbot.combat.knife_chain_transfer import propose,TransferGoal,MoveInstance
 r,s,old=transfer_at_gap(5.);r.run.link='strike'
 r.run.v.update(caster=8,side=B['L'],jump_k=0,jump_until=0,air_entry=True,
     row={'F0':1002,'press_F':1003,'contact_frame':1006,'masks':[B['D']|B['L'],B['D']|B['A']|B['L']]})
 s['hero'].update(pos=[25.,15.],box=[24.75,13.45,25.25,15.53],vel=[0.,0.])
 s['ents'][1]['fsms'][0]['state']='Evade Scuttle'
 S=K.initial_state(old.params,25.,15.,ground=False)
 sim=ChainSim(S,np.array([0]),K.HoldState.idle(1),old.params,old.terrain,1000,1000)
 goal=TransferGoal(8,8,990,0.,'BOUNCE',MoveInstance(8,940,'CC_SLAM'))
 made=propose(r,s,0.,sim,8,False,np.zeros((0,6)),set(),goal)
 assert made[0].run.link=='strike' and made[1].side==B['L']
 assert made[3]==B['D']|B['L'] and made[0].run.v['row']['press_F']==1003


@pytest.mark.parametrize('outside',[True,False])
def test_only_outside_air_entry_can_continue_after_landing_without_strike(outside):
 from ssbot.combat.knife_chain_transfer import propose
 r,s,sim=transfer_at_gap(7.9)
 r.run.link='air';r.run.v.update(jump_k=0,jump_until=0,air_entry=outside)
 s['f']=1010;sim.f=sim.fo=1010
 made=propose(r,s,10/60,sim,8,True,np.zeros((0,6)),set())
 assert made is not None
 if outside:
  assert made[0] is not None and made[0].run.link=='jump' and made[3]==B['R']|B['J']
  assert not made[0].run.v['air_entry']
 else:
  assert made[0] is None  # our own failed jump still ends; never hide a miss


@pytest.mark.parametrize('mode_name',['M_DASH','M_SPRINT'])
def test_near_dash_limit_preserves_an_existing_dash_or_sprint(mode_name):
 from ssbot.knowledge import kinematics as K
 from ssbot.combat.knife_chain_transfer import propose
 r,s,sim=transfer_at_gap(8.695,getattr(K,mode_name))
 made=propose(r,s,0.,sim,8,True,np.zeros((0,6)),set())
 assert made is not None and made[3]==B['R']|B['DASH']
 assert made[1].dash_k==2


@pytest.mark.parametrize('where',['queued','latched'])
def test_near_dash_limit_does_not_withdraw_queued_or_latched_dash(where):
 from ssbot.knowledge import kinematics as K
 from ssbot.combat.knife_chain_transfer import propose
 r,s,sim=transfer_at_gap(8.695)
 if where=='queued':sim.prefix[0]|=B['DASH']
 else:
  s['act']['hf']['latched']|=B['DASH'];s['act']['hf']['desired']|=B['DASH']
  sim.hold=K.HoldState.from_act(s['act'])
 made=propose(r,s,0.,sim,8,True,np.zeros((0,6)),set())
 assert made is not None and made[3]==B['R']|B['DASH']
 assert made[1].dash_k==2


def test_suppressed_dash_can_be_scheduled_again_if_target_recedes():
 from ssbot.combat.knife_chain_transfer import propose
 r,s,sim=transfer_at_gap(13.)
 r.run.v['dash_k']=10000
 made=propose(r,s,0.,sim,8,True,np.zeros((0,6)),set())
 assert made is not None and made[3]==B['R']|B['DASH']


@pytest.mark.parametrize('target_state',['Idle','Spell Antic'])
def test_observed_head_goal_requires_actual_downslash_not_an_empty_handoff(target_state,monkeypatch):
 """User-level completion criterion: reaching the destination must supply the
 nail action, including when the new target starts its own small-rune cast.
 Geometry is stubbed; this tests action supply, not a safe/accepted hit.
 """
 from ssbot.knowledge import kinematics as K
 from ssbot.combat.air_chain import ChainSim
 from ssbot.combat import knife_chain_air_native as N
 r,s,oldsim=transfer_motion_scene(K.M_NORMAL)
 s['f']=1040;s['hero'].update(pos=[38.,9.253],box=[37.75,7.7,38.25,9.779],vel=[0.,-2.],
                             silk=9,anim={'clip':'Airborne'},can={'attack':True,'input':True})
 s['hero']['tm']['atk_cd']=0.
 e=s['ents'][1];dx=38.-e['pos'][0];e['pos'][0]=38.;e['fsms'][0]['state']=target_state
 for c in e['colliders']:c['verts_world'][::2]=[v+dx for v in c['verts_world'][::2]]
 S=K.initial_state(oldsim.params,38.,9.253,vy=-2.,ground=False)
 sim=ChainSim(S,np.array([B['R']],np.int64),oldsim.hold,oldsim.params,oldsim.terrain,1040,1040)
 r.run=Run('rune_transfer','air',TransferPlan(8,7,990,1000,0.,B['R'],2,12,36,True,1040,40).variables())
 n=N.NativeManualAirChain(runner_factory=load_runner,probe_ref='whole-head-action-goal');n.runner=r
 monkeypatch.setattr(n,'queued_prefix',lambda *a:(B['R'],'fixture'))
 n._context=((1040,s,40/60,False,True),sim,None,np.zeros((0,6)))
 monkeypatch.setattr(N,'B2Geometry',lambda *a:NS(scan=lambda p:NS(complete=True,contacts=()),
                                                preflight=lambda p:NS(complete=True,contacts=())))
 offer=n._transfer_offer(s,40/60,sim,NS(rs=NS(trk=NS(now={8:(None,None,None)}))),NS(target=8),False)
 assert offer is not None and offer.mask&B['D'] and not offer.mask&B['A']
 row=offer.draft.run.v['row']
 assert row['press_F']==1043 and row['masks'][1]&(B['D']|B['A'])==B['D']|B['A']
 assert n._hit is None and not offer.draft.run.v.get('bounced',False)


@pytest.mark.parametrize('contact_kind,at_contact,allowed',[
 ('move',True,True),('move',False,False),('delayed',True,False),
])
@pytest.mark.parametrize('source_kind',['BOUNCE','CAST'])
def test_air_slice_checks_attacking_destination_and_keeps_delayed_hazards(contact_kind,at_contact,allowed,monkeypatch,source_kind):
 from ssbot.knowledge import kinematics as K
 from ssbot.combat.air_chain import ChainSim
 from ssbot.combat import knife_chain_air_native as N
 from ssbot.combat.knife_chain_transfer import TransferGoal
 from ssbot.combat.knife_chain_commitment import MoveInstance,PathContact,ContactScan
 r,s,oldsim=transfer_motion_scene(K.M_NORMAL);r.run=None
 s['f']=1040;s['hero'].update(pos=[38.,9.253],box=[37.75,7.7,38.25,9.779],vel=[0.,-2.],
     silk=9,anim={'clip':'Airborne'},can={'attack':True,'input':True})
 s['hero']['tm']['atk_cd']=0.
 e=s['ents'][1];dx=38.-e['pos'][0];e['pos'][0]=38.;e['fsms'][0]['state']='Slam 1'
 for c in e['colliders']:c['verts_world'][::2]=[v+dx for v in c['verts_world'][::2]]
 S=K.initial_state(oldsim.params,38.,9.253,vy=-2.,ground=False)
 sim=ChainSim(S,np.array([B['R']],np.int64),oldsim.hold,oldsim.params,oldsim.terrain,1040,1040)
 n=N.NativeManualAirChain(runner_factory=load_runner,probe_ref='same-target-contact');n.reset(0,start_frame=1040)
 parent=MoveInstance(7,990,'CC_SLAM' if source_kind=='BOUNCE' else 'CC_CAST')
 n._transfer_ready=True;n._transfer_goal=TransferGoal(8,7,1040,0.,source_kind,parent)
 n._clock=1.;n._clock_known=True;n._context=(None,None,None,np.zeros((0,6)))
 seen=deepcopy(s);seen['f']=990;seen['ents'][1]['fsms'][0].update(state='Slam Antic',t=0.)
 n._ticks.append((990,seen,0.,False,True))
 monkeypatch.setattr(n,'queued_prefix',lambda *a:(B['R'],'fixture'))
 scans=[]
 class Geo:
  def __init__(self,*a):pass
  @staticmethod
  def ref(p):return 'contact-path'
  def preflight(self,p):raise AssertionError('attacking target cannot use external-only gate')
  def scan(self,p):
   scans.append(p)
   return ContactScan(self.ref(p),p.origin,p.through,
       (PathContact(p.through if at_contact else p.origin+1,8,contact_kind),),'fixture')
 monkeypatch.setattr(N,'B2Geometry',Geo)
 fc=NS(rs=NS(trk=NS(now={8:(None,None,NS(fam='CC_SLAM',t0=0.))},T=1.)))
 offer=n._transfer_offer(s,0.,sim,fc,NS(target=8),False)
 assert (offer is not None)==allowed
 assert len(scans)==1 and scans[0].through>1042
 if allowed:
  assert offer.draft.run.link=='strike' and not offer.mask&(B['J']|B['DASH'])
  assert offer.details['target_attack_checked'] and offer.draft.run.v['caster']==7
  assert n._transfer_responsibility[offer.move][0]==parent
  assert offer.details['target_move']==vars(MoveInstance(8,990,'CC_SLAM'))
 assert n._hit is None  # model contact never becomes observed hit credit


@pytest.mark.parametrize('state,hammer,pending',[
 ('Slam 1',True,True),('Slam 2',True,True),('Slam Recover',True,True),
 ('Slam Recover',False,False),('Idle',False,False),
])
def test_bounce_tail_waits_for_observed_hammer_two_disappearance(state,hammer,pending):
 from ssbot.combat.knife_chain_transfer import bounce_tail_pending,TransferGoal
 from ssbot.combat.knife_chain_commitment import MoveInstance
 s=cast_scene();source=s['ents'][0];source['fsms'][0]['state']=state
 source['colliders']=[{'name':'Song Heavy Sentry (2)','enabled':True}]
 if hammer:source['colliders'].append({'name':'Slam Collider 2','enabled':True})
 goal=TransferGoal(8,7,1000,0.,'BOUNCE',MoveInstance(7,946,'CC_SLAM'))
 assert bounce_tail_pending(s,goal,1.) is pending
 source['colliders']=None
 assert bounce_tail_pending(s,goal,1.)  # missing observation is not a cleared hammer


def test_same_target_bounce_holds_tail_then_reuses_existing_downslash_without_ground_restart():
 from ssbot.knowledge import kinematics as K
 from ssbot.combat.air_chain import ChainSim
 from ssbot.combat.knife_chain_transfer import propose,TransferGoal,MoveInstance
 r,s,oldsim=transfer_motion_scene(K.M_NORMAL);r.run=None
 s['f']=1040;s['hero'].update(pos=[38.,9.253],box=[37.75,7.7,38.25,9.779],vel=[0.,-2.],
     silk=9,anim={'clip':'Airborne'},can={'attack':True,'input':True})
 s['hero']['tm']['atk_cd']=0.
 e=s['ents'][1];dx=38.-e['pos'][0];e['pos'][0]=38.;e['fsms'][0]['state']='Slam 2'
 for c in e['colliders']:c['verts_world'][::2]=[v+dx for v in c['verts_world'][::2]]
 e['colliders'].append({'name':'Slam Collider 2','enabled':True})
 S=K.initial_state(oldsim.params,38.,9.253,vy=-2.,ground=False)
 sim=ChainSim(S,np.array([B['R']],np.int64),oldsim.hold,oldsim.params,oldsim.terrain,1040,1040)
 goal=TransferGoal(8,8,1040,0.,'BOUNCE',MoveInstance(8,990,'CC_SLAM'))
 first=propose(r,s,0.,sim,8,False,np.zeros((0,6)),set(),goal)
 assert first[0].run.link=='bounce_tail' and first[3]==0
 e['fsms'][0]['state']='Slam Recover';e['colliders'].pop()
 # The next observation clears the actual hammer; the same runner enters the
 # existing press-now downslash row without a J/DASH or a new ground approach.
 made=propose(first[0],s,0.,sim,8,False,np.zeros((0,6)),set(),goal)
 assert made[0].run.link=='strike' and made[3]&B['D']
 assert not made[3]&(B['J']|B['DASH']|B['L']|B['R'])
 assert made[1].contact_frame is not None and not made[0].run.v['bounced']


def test_rune_commitment_requires_its_sent_downslash_hit_and_real_bounce():
 from ssbot.combat.knife_chain_air_native import NativeManualAirChain
 from ssbot.combat.knife_chain_commitment import MoveInstance
 n=NativeManualAirChain(runner_factory=load_runner,probe_ref='rune-real-hit');n.reset(0,start_frame=1000)
 s=cast_scene();s.update(dt=1/60,ev=[],act={'target':1000,'applied':1000,'mask':0,
  'hf':{'latched':0,'desired':0,'pending':[0]*22,'age':[100]*22}})
 s['hero'].update(cstate_int=[0,0],anim={'clip':'Airborne'})
 n.begin(s);p=plan();n.runner.run=Run('rune_transfer','strike',p.variables())
 n.commitment={'move':p.move,'origin':1000,'ta':0.,'predicted_bounce':None}
 n._transfer_responsibility[p.move]=(MoveInstance(7,990,'CC_CAST'),None)
 n._press=1002
 def tick(f,events=(),marker=0):
  raw=deepcopy(s);raw['f']=f;raw['act'].update(target=f,applied=f)
  raw['ev']=list(events);raw['hero']['cstate_int']=[0,marker]
  n.begin(raw)
 tick(1001,[{'k':'hit','f':1001,'d':{'ent':8,'src':'DownSlash'}}],8)
 assert n.post_context is None  # hit before our original press is not ours
 tick(1002,[{'k':'hit','f':1002,'d':{'ent':7,'src':'DownSlash'}}],8)
 assert n.post_context is None
 tick(1003,[{'k':'hit','f':1003,'d':{'ent':8,'src':'Harpoon'}}],8)
 assert n.post_context is None
 tick(1004,[{'k':'hit','f':1004,'d':{'ent':8,'src':'DownSlash'}}])
 assert n.post_context is None and n._hit==1004
 tick(1005,marker=8)
 assert n.commitment is None and n.post_context['hit']==1004
 n._transfer_bounce_exit()
 assert n.runner.run is None and n.post_context is None


def test_rune_failure_responsibility_uses_real_caster_not_a_fictitious_slam():
 from ssbot.combat.knife_chain_air_native import NativeManualAirChain
 from ssbot.combat.knife_chain_commitment import MoveInstance
 n=NativeManualAirChain(runner_factory=load_runner,probe_ref='rune-failure');n.reset(0)
 p=plan();n._transfer_responsibility[p.move]=(MoveInstance(7,990,'CC_CAST'),1.)
 exposure=n._failure_exposure(p.move,1000,1010,0.)
 assert exposure.move==MoveInstance(7,990,'CC_CAST') and exposure.minimum_through==1040
 raw=cast_scene();raw['f']=1011
 exposure.observe(raw,game_time=1.)
 assert exposure.through is None
 raw['f']=1012;raw['ents'][0]['fsms'][0]['state']='Idle'
 exposure.observe(raw,game_time=1.02)
 assert exposure.observed_end_frame==1012 and exposure.through==1040
 assert exposure.active(1040) and not exposure.active(1041)


def test_fresh_air_transfer_never_inherits_an_outside_held_jump():
 from ssbot.knowledge import kinematics as K
 from ssbot.combat.air_chain import ChainSim
 from ssbot.combat.knife_chain_transfer import propose
 r,s,sim0=transfer_motion_scene(K.M_NORMAL)
 r.run=None
 s['hero']['pos'][1]=8.;s['hero']['vel'][1]=1.
 s['act']['hf'].update(latched=B['R']|B['J'],desired=B['R']|B['J'])
 S=K.initial_state(sim0.params,30.,8.,vy=1.,ground=False)
 S[K.JUMPING]=1.;S[K.JSTEPS]=9.;S[K.JHELD]=1.;S[K.PREV]=B['R']|B['J']
 sim=ChainSim(S,np.array([B['R']|B['J']]),K.HoldState.from_act(s['act']),sim0.params,sim0.terrain,1000,1000)
 from ssbot.combat.knife_chain_transfer import TransferGoal
 made=propose(r,s,0.,sim,8,False,np.zeros((0,6)),set(),TransferGoal(8,7,990))
 assert made is not None and made[3]==B['R'] and made[0].run.link=='air'


@pytest.mark.parametrize('fresh',[False,True])
def test_external_air_transfer_ends_on_landing_before_walking_into_the_body(fresh):
 from ssbot.knowledge import kinematics as K
 from ssbot.combat.air_chain import ChainSim
 from ssbot.combat.knife_chain_transfer import propose,TransferGoal
 r,s,sim0=transfer_motion_scene(K.M_NORMAL)
 if fresh:r.run=None
 s['hero'].update(pos=[30.,8.],vel=[0.,1.])
 S=K.initial_state(sim0.params,30.,8.,vy=1.,ground=False)
 sim=ChainSim(S,np.array([B['R']]),sim0.hold,sim0.params,sim0.terrain,1000,1000)
 made=propose(r,s,0.,sim,8,False,np.zeros((0,6)),set(),TransferGoal(8,7,990))
 assert made is not None and made[0].run.link=='air'
 r=made[0];s['f']=1030;s['hero'].update(pos=[46.2,4.568],vel=[8.25,0.])
 S=K.initial_state(sim0.params,46.2,4.568,vx=8.25,ground=True)
 sim=ChainSim(S,np.array([B['R']]),sim0.hold,sim0.params,sim0.terrain,1030,1030)
 landed=propose(r,s,.5,sim,8,True,np.zeros((0,6)),set(),TransferGoal(8,7,990))
 assert landed is not None and landed[0] is None


def test_vetoed_transfer_first_jump_spends_cast_without_faking_action_execution():
 from ssbot.combat.knife_chain_air_native import NativeManualAirChain
 from ssbot.combat.knife_chain_b2 import B2Offer
 from ssbot.combat.knife_chain_commitment import MoveInstance
 from ssbot.combat.knife_chain_transfer import propose
 from ssbot.knowledge import kinematics as K
 from ssbot.combat.air_chain import ChainSim
 r,s,sim0=transfer_motion_scene(K.M_NORMAL)
 n=NativeManualAirChain(runner_factory=load_runner,probe_ref='rune-veto-no-retry');n.reset(0,start_frame=1000);n.begin(s)
 p=TransferPlan(8,7,1000,1000,0.,B['R'],2,2,26,False,1000,0)
 draft=load_runner();draft.run=Run('rune_transfer','jump',{**draft.chains['rune_transfer'].vars,**p.variables()})
 n._transfer_responsibility[p.move]=(MoveInstance(7,1000,'CC_CAST'),None)
 mask=B['R']|B['J'];offer=B2Offer('manual_commitment',None,draft,mask,0.,p.move,
  {'manual_air':True,'rune_transfer':True,'caster':7,'cast_fa':1000})
 res=n.install(offer,NS(measurement_enabled=False));n.planner_result(res);n.final('plan',mask)
 assert n.before_send(frame=1000,target=1002,mask=mask,flags=0,received_frame=1002)==0
 assert n.commitment is None and not n._failure_exposures
 n.sent()  # only this successful neutral replacement creates preparation exposure
 assert len(n._failure_exposures)==1 and n._failure_exposures[0].move.family=='CC_CAST'
 assert n._receipts[1002]==0 and (7,1000) in n._transfer_finished
 s['f']=1001;s['ents'][0]['fsms'][0].update(state='Spell Antic',t=1/60)
 sim=ChainSim(sim0.start,np.array([B['R']]),sim0.hold,sim0.params,sim0.terrain,1001,1001)
 assert propose(load_runner(),s,1/60,sim,8,True,np.zeros((0,6)),n._transfer_finished) is None


@pytest.mark.parametrize('sprint,grace',[(False,4),(True,11)])
def test_transfer_takeoff_deadline_includes_only_actual_jump_antic_and_receipt_grace(sprint,grace):
 r=load_runner();p=TransferPlan(8,7,990,1000,0.,B['R'],2,10,34,sprint,1000,0)
 def evaluate(elapsed,ground):
  r.run=Run('rune_transfer','jump',{**r.chains['rune_transfer'].vars,**p.variables()})
  obs=NS(f=1010+elapsed,F=1012+elapsed,k=12+elapsed,target_valid=True,ground=ground,overhead=False)
  return r.eval_link(X(r,r.run,obs))
 assert evaluate(grace,True) is not None
 assert evaluate(grace+1,True) is None
 assert evaluate(grace+1,False) is not None  # real takeoff is never rejected by this ground-only guard
