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
