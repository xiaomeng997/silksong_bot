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
 st={"f":1000,"act":{"hf":{"latched":0}}};sim=NS(prefix=np.array([0]));fc=NS(rs=NS(trk=NS(now={8:(None,None,None)})))
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
  old=GoalPrefs(mode="RUSH",stance_x=38.,weights={},target=8)
  assert n.goal_preferences(st,old,handoff=True) is old
  assert n.runner.run is None and n._transfer_goal is None and not n.candidate_generation


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
  s['ents'].append({'iid':iid,'type_key':'Song Heavy Sentry','hp':100,'pos':[x,7.45],
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
 s['hero']['pos'][1]=8.;s['hero']['vel'][1]=1.
 s['act']['hf'].update(latched=B['R']|B['J'],desired=B['R']|B['J'])
 S=K.initial_state(sim0.params,30.,8.,vy=1.,ground=False)
 S[K.JUMPING]=1.;S[K.JSTEPS]=9.;S[K.JHELD]=1.;S[K.PREV]=B['R']|B['J']
 sim=ChainSim(S,np.array([B['R']|B['J']]),K.HoldState.from_act(s['act']),sim0.params,sim0.terrain,1000,1000)
 from ssbot.combat.knife_chain_transfer import TransferGoal
 made=propose(r,s,0.,sim,8,False,np.zeros((0,6)),set(),TransferGoal(8,7,990))
 assert made is not None and made[3]==B['R'] and made[0].run.link=='air'
