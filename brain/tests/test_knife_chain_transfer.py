"""Manual approach: actual focus, dash timing and jump continuity."""
from copy import deepcopy
from types import SimpleNamespace as NS
import numpy as np
from ssbot.combat.knife_chain_air import load_runner
from ssbot.combat.knife_chain_eval import Run,X
from ssbot.combat.knife_chain_transfer import TransferPlan,render,visible,path_problem
from ssbot.combat.knife_chain_format import MASK_NAMES as B


def plan():return TransferPlan(8,7,1000,1000,0.,B["L"],5,12,36,True,1000,0)


def test_transfer_table_walk_dash_jump_and_air_release_dash():
 r=load_runner();p=plan()
 assert render(r,p,0,2).tolist()==[B["L"],B["L"]]
 assert render(r,p,3,1)[0]==B["L"]|B["DASH"]
 assert render(r,p,10,1)[0]==B["L"]|B["DASH"]|B["J"]
 assert render(r,p,12,1,"air")[0]==B["L"]|B["J"]
 assert render(r,p,35,1,"air")[0]==B["L"]


def test_observed_overhead_is_a_real_handoff_without_attack_or_fake_bounce():
 r=load_runner();p=plan();r.run=Run("rune_transfer","air",p.variables())
 obs=NS(f=1010,F=1012,k=12,target_valid=True,ground=False,overhead=True)
 assert r.eval_link(X(r,r.run,obs)) is None and r.run is None
 assert r.done[-1].closed=="done"


def test_transfer_availability_is_only_ground_cast_entry():
 e=lambda i,st,t:{"iid":i,"type_key":"Song Heavy Sentry","hp":100,"pos":[20.,7.45],"fsms":[{"name":"Control","state":st,"t":t}]}
 s={"hero":{"box":[22.,3.015,22.5,5.1],"hero_accepting_input":True},"ents":[e(7,"Spell Antic",0.),e(8,"Idle",0.)]}
 assert visible(s)
 late=deepcopy(s);late["ents"][0]["fsms"][0]["t"]=.3;assert not visible(late)
 air=deepcopy(s);air["hero"]["box"][1]=5.;assert not visible(air)
 unknown=deepcopy(s);unknown["hero"]["box"][1]=None;assert not visible(unknown)


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



def test_transfer_run_is_owned_only_after_successful_send_without_hit_commitment():
 from ssbot.combat.knife_chain_air_native import NativeManualAirChain
 from ssbot.combat.knife_chain_b2 import B2Offer
 from ssbot.combat.knife_chain_air import AirAnchor
 r=load_runner();p=plan();draft=r.fork_empty(AirAnchor());draft.run=Run("rune_transfer","walk",p.variables())
 e=lambda i,st:{"iid":i,"type_key":"Song Heavy Sentry","hp":100,"pos":[20.,7.45],"fsms":[{"name":"Control","state":st,"t":0.}]}
 s={"f":1000,"dt":1/60,"hero":{"health":7,"box":[22.,3.015,22.5,5.1],"hero_accepting_input":True},"ents":[e(7,"Spell Antic"),e(8,"Idle")],"act":{"target":1000,"applied":1000,"mask":0,"hf":{"latched":0,"desired":0,"pending":[0]*22,"age":[100]*22}},"ev":[]}
 n=NativeManualAirChain(runner_factory=load_runner,probe_ref="transfer-test");n.reset(0,start_frame=1000);n.begin(s)
 offer=B2Offer("approach",None,draft,B["L"],0.,p.move,{"manual_air":True,"rune_transfer":True,"caster":7,"cast_fa":1000})
 planner=NS(measurement_enabled=False,jump_until=1100,macro_until=1150)
 res=n.install(offer,planner);assert planner.jump_until==planner.macro_until==-1
 n.planner_result(res);n.final("plan",B["L"])
 n.before_send(frame=1000,target=1002,mask=B["L"],flags=0,received_frame=1000)
 assert n.runner.run is None and n.commitment is None
 n.sent()
 assert n.runner.run.chain=="rune_transfer" and n.commitment is None
 assert (7,1000) in n._transfer_finished
 n.reset(1);assert not n._transfer_finished and not n._transfer_ready


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


def test_pending_goal_changes_preferences_without_creating_run_or_sent_keys():
 from ssbot.combat.knife_chain_air_native import NativeManualAirChain
 from ssbot.combat.knife_chain_transfer import observe_goal
 from ssbot.combat.tactics.modes import GoalPrefs
 n=NativeManualAirChain(runner_factory=load_runner,probe_ref="goal-test");n.reset(0,start_frame=999)
 s=cast_scene();n._transfer_goal=observe_goal(s,None,n.runner.chains["rune_transfer"].cfg,set())
 old=GoalPrefs(mode="RUSH",stance_x=25.,weights={},target=7,region=(24.,26.,3.,5.,"GROUND"))
 new=n.goal_preferences(s,old,handoff=True)
 assert new.target==8 and new.stance_x==38. and new.region is None
 assert old.target==7 and old.stance_x==25. and old.region is not None
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
 old=GoalPrefs(mode="RUSH",stance_x=25.,weights={},target=7)
 p=Policy.__new__(Policy);p.chain_native=n;aborted=[]
 p.slam_play=NS(run=NS(phase="air",bounced=False),abort=aborted.append)
 assert p._chain_goal_preferences(s,old) is old and not aborted
 p.slam_play.run.phase="after"
 assert p._chain_goal_preferences(s,old) is old and not aborted
 p.slam_play.run.bounced=True
 assert p._chain_goal_preferences(s,old).target==8
 assert aborted==["observed rune antic: transfer goal handoff"]
 p.chain_native=None
 assert p._chain_goal_preferences(s,old) is old


def test_next_visible_cast_replaces_pending_destination_without_waiting_for_old_expiry():
 from ssbot.combat.knife_chain_transfer import observe_goal
 cfg=load_runner().chains["rune_transfer"].cfg;s=cast_scene();first=observe_goal(s,None,cfg,set())
 s["f"]=1060;s["ents"][0]["fsms"][0].update(state="Idle",t=0.)
 s["ents"][1]["fsms"][0].update(state="Spell Antic",t=0.)
 next_goal=observe_goal(s,first,cfg,set())
 assert (next_goal.target,next_goal.caster,next_goal.cast_fa)==(7,8,1060)


def test_pending_destination_does_not_claim_keys_from_a_new_target_attack():
 from ssbot.combat.knife_chain_air_native import NativeManualAirChain
 from ssbot.combat.knife_chain_transfer import observe_goal
 from ssbot.combat.tactics.modes import GoalPrefs
 n=NativeManualAirChain(runner_factory=load_runner,probe_ref="goal-attack-boundary");n.reset(0,start_frame=999)
 s=cast_scene();n._transfer_goal=observe_goal(s,None,n.runner.chains["rune_transfer"].cfg,set())
 s["ents"][1]["fsms"][0]["state"]="Slam Antic"
 old=GoalPrefs(mode="RUSH",stance_x=25.,weights={},target=7)
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


def test_prejump_failure_uses_one_checked_coast_offer_and_does_not_force_keys(monkeypatch):
 from ssbot.combat import knife_chain_air_native as mod
 from ssbot.combat.knife_chain_air import AirAnchor
 n=mod.NativeManualAirChain(runner_factory=load_runner,probe_ref="prejump-coast");n.reset(0,start_frame=1000)
 n._transfer_ready=True;n._context=(None,None,None,None);p=plan();draft=load_runner().fork_empty(AirAnchor());draft.run=Run("rune_transfer","walk",p.variables())
 path=NS(through=1036,assumptions={"flight_checked":False,"flight_endpoint":"uncovered"});calls=[];scanned=[]
 def propose(*args,**kw):
  calls.append(kw["defer_jump"])
  return (draft,p,path,B["L"]) if kw["defer_jump"] else None
 monkeypatch.setattr(mod.transfer,"propose",propose)
 monkeypatch.setattr(mod.B2Geometry,"scan",lambda self,q:scanned.append(q) or NS(complete=True,contacts=[]))
 st={"f":1000,"act":{"hf":{"latched":0}}};sim=NS(prefix=np.array([0]));fc=NS(rs=NS(trk=NS(now={8:(None,None,None)})))
 offer=n._transfer_offer(st,0.,sim,fc,NS(target=8),True)
 assert calls==[False,True] and scanned==[path]
 assert offer.mask==B["L"] and offer.details["jump_deferred"]
 assert n.runner.run is None and n.commitment is None
 monkeypatch.setattr(mod.B2Geometry,"scan",lambda self,q:NS(complete=True,contacts=[NS(frame=1003,owner_iid=8,kind="body")]))
 # contacts are real dataclasses in production; use the real contact object here.
 from ssbot.combat.knife_chain_commitment import PathContact
 monkeypatch.setattr(mod.B2Geometry,"scan",lambda self,q:NS(complete=True,contacts=[PathContact(1003,8,"body")]))
 assert n._transfer_offer(st,0.,sim,fc,NS(target=8),True) is None


def test_retarget_intent_moves_all_iid_fields_together_preserving_unrelated_data():
 from ssbot.combat.tactics.modes import GoalPrefs
 fields={"no_hit":frozenset({7,9}),"ground_hit":frozenset({8}),"no_pogo":frozenset({7}),"no_dash":frozenset({8,9}),"ground_first":frozenset({7,8})}
 p=GoalPrefs(mode="RUSH",stance_x=25.,weights={"hit":1.},target=7,hit_w={7:3.,8:1.,9:.5},hit_kw={7:(3.,2.,1.,0.),9:(1.,1.,1.,1.)},rune_exit=("shared",),**fields)
 q=p.retarget_intent(8,stance_x=38.,boss_x=38.)
 assert q.hit_w=={8:3.,7:1.,9:.5} and q.hit_kw[8]==p.hit_kw[7]
 assert q.no_hit==frozenset({8,9}) and q.ground_hit==frozenset({7})
 assert q.no_pogo==frozenset({8}) and q.no_dash==frozenset({7,9}) and q.ground_first==frozenset({7,8})
 assert q.rune_exit==p.rune_exit and q.weights==p.weights and p.hit_w[7]==3.
 assert q.hit_w is not p.hit_w and q.hit_kw is not p.hit_kw


def test_spent_transfer_has_no_false_keyboard_availability_but_active_run_can_continue():
 from ssbot.combat.knife_chain_air_native import NativeManualAirChain
 from ssbot.combat.knife_chain_transfer import observe_goal
 from ssbot.combat.tactics.modes import GoalPrefs
 n=NativeManualAirChain(runner_factory=load_runner,probe_ref="spent-cast");n.reset(0,start_frame=999);st=cast_scene()
 goal=observe_goal(st,None,n.runner.chains["rune_transfer"].cfg,set());n._transfer_goal=goal;n._transfer_finished.add((7,1000))
 old=GoalPrefs(mode="RUSH",stance_x=25.,weights={},target=7)
 assert n.goal_preferences(st,old,handoff=True) is old and n._transfer_goal is None
 assert not n._transfer_ready and not n.candidate_generation
 n._transfer_goal=goal;n.runner.run=Run("rune_transfer","air",plan().variables())
 assert n.goal_preferences(st,old,handoff=True).target==8 and n._transfer_ready


def test_caster_new_attack_releases_pending_and_active_uncommitted_transfer():
 from ssbot.combat.knife_chain_air_native import NativeManualAirChain
 from ssbot.combat.knife_chain_transfer import observe_goal
 from ssbot.combat.tactics.modes import GoalPrefs
 for kind in ("Slam Antic","Jump Antic","Cast Slam Antic"):
  n=NativeManualAirChain(runner_factory=load_runner,probe_ref="caster-move");n.reset(0,start_frame=999);st=cast_scene()
  n._transfer_goal=observe_goal(st,None,n.runner.chains["rune_transfer"].cfg,set());n.runner.run=Run("rune_transfer","air",plan().variables())
  st["ents"][0]["fsms"][0]["state"]=kind
  old=GoalPrefs(mode="RUSH",stance_x=25.,weights={},target=7)
  assert n.goal_preferences(st,old,handoff=True) is old
  assert n.runner.run is None and n._transfer_goal is None and not n.candidate_generation
