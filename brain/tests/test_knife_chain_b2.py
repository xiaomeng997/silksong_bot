"""B2 nominal future, in-flight transaction and real-bounce handback tests."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from ssbot.knowledge import kinematics as km
from ssbot.combat.air_chain import ChainSim
from ssbot.combat.knife_chain_format import chains_from_json, MASK_NAMES as B
from ssbot.combat.knife_chain_slam import make_runner
from ssbot.combat.knife_chain_nominal import compile_path,post_paths,NominalProfile
from ssbot.combat.knife_chain_b2 import NativeChainB2
from ssbot.combat.knife_chain_budget import LearningBudget,LearningStop


@pytest.fixture(scope="module")
def params():
    return km.hero2(km.HeroParams.load(Path(__file__).resolve().parents[2]/"knowledge/1.0.30000/kinematics/hero_wanderer_forum.json"),on=True)


@pytest.fixture(scope="module")
def terrain():
    return km.Terrain2D.from_boxes([(-100,0,100,3.015),(0,0,14,40),(49,0,100,40)])


def runner():
    from ssbot.combat import knife_chain_slam as f
    chains=chains_from_json(json.loads(Path(f.__file__).with_name("knife_chain_slam_v01.json").read_text(encoding="utf-8")))
    cfg=dict(chains["slam_jump"].cfg)
    cfg.update(CLAWSTRIKE=False,EARLY=False)
    for c in chains.values():c.cfg=cfg.copy()
    return make_runner(chains)


def raw(f=1000):
    return {"f":f,"dt":1/60,"hero":{"health":7,"silk":9,"pos":[35.,4.568],"box":[34.75,3.015,35.25,5.094],
        "vel":[0.,0.],"facing":-1,"hero_accepting_input":True,"anim":{"clip":"Idle"},
        "tm":{"atk_cd":0.,"dash_cd":0.},"cstate":[0,0],"cstate_int":[0,0,0,0]},
        "ents":[{"iid":7,"type_key":"Song Heavy Sentry","hp":130,"flipX":True,"pos":[30.,7.449],
                 "fsms":[{"name":"Control","state":"Slam Antic","t":0.}]}],
        "ev":[],"act":{"target":f,"applied":f,"mask":0,"hf":{"desired":0}}}


def preview(params,terrain):
    r=runner();s=raw();S=km.initial_state(params,35.,4.568,ground=True,facing=-1,silk=9)
    sim=ChainSim(S,np.zeros(1,np.int64),km.HoldState.idle(1),params,terrain,1000,1000)
    p=r.preview(1000,s,True,True,t_game=0.,sim=sim)
    assert p.mask is not None and p.draft.run is not None
    return r,p,s,sim


def test_nominal_future_uses_full_chain_not_first_key_ordinary_tail(params,terrain):
    r,p,s,sim=preview(params,terrain)
    before=deepcopy(p.draft.run.v)
    path=compile_path(p.draft,s,sim,0.,stage="commitment",first_mask=p.mask)
    assert path.end=="bounce" and path.contact_frame>path.origin+36
    assert (path.commands & B["J"]).any()
    assert ((path.commands & (B["A"]|B["D"]))==(B["A"]|B["D"])).any()
    assert path.contact_frame==path.press_frame+4
    assert not path.check_flags[-1]&km.F_INVULN
    assert path.flags[-1]&km.F_INVULN
    assert path.approach is not None and path.approach.end=="decision"
    assert path.approach.through<path.press_frame
    assert p.draft.run.v==before and r.run is None
    assert s["f"]==1000 and s["hero"]["health"]==7


def test_three_post_programs_start_at_same_conditional_bounce(params,terrain):
    _,p,s,sim=preview(params,terrain)
    path=compile_path(p.draft,s,sim,0.,stage="commitment",first_mask=p.mask)
    branches,errors=post_paths(path,params,terrain)
    assert branches,errors
    assert all(p.origin==path.contact_frame and p.stage=="continuation" for p in branches.values())
    assert all(p.contact_frame is None and p.end=="handback" for p in branches.values())
    assert all(p.first_draft is not None for p in branches.values())


def test_budget_is_cumulative_across_episodes_and_tail_is_separate(tmp_path):
    b=LearningBudget(tmp_path/"budget.json",batch="b1",revision="r1",worker="i0")
    b.observe(episode=0,frame=1,arm="B",hp_loss=1)
    b.observe(episode=1,frame=2,arm="B",hp_loss=3,tail=True)
    assert b.state["b_fight_hp"]==1 and b.state["tail_hp"]==3
    with pytest.raises(LearningStop,match="2 HP"):
        b.observe(episode=2,frame=3,arm="B",hp_loss=1)
    assert b.state["b_fight_hp"]==2


def test_first_chain_injury_stops_even_at_one_hp(tmp_path):
    b=LearningBudget(tmp_path/"budget.json",batch="b1",revision="r1",worker="i0")
    with pytest.raises(LearningStop,match="chain-related"):
        b.observe(episode=0,frame=5,arm="B",hp_loss=1,chain_related=True)
    assert b.state["b_fight_hp"]==1


def test_budget_revision_cannot_replace_failures(tmp_path):
    path=tmp_path/"budget.json"
    b=LearningBudget(path,batch="b1",revision="r1",worker="i0")
    b.observe(episode=0,frame=1,arm="B",hp_loss=1)
    before=path.read_bytes()
    with pytest.raises(LearningStop,match="NEW batch"):
        LearningBudget(path,batch="b1",revision="r2",worker="i0")
    assert path.read_bytes()==before


def bits(s, **values):
    names=km.cstate_names()
    for name,val in values.items():
        i=names.index(name)
        if val:s["hero"]["cstate"][i//64]|=1<<(i%64)
        else:s["hero"]["cstate"][i//64]&=~(1<<(i%64))
    return s


def native_committed(params,terrain):
    from ssbot.combat.knife_chain_b2 import B2Offer
    from ssbot.combat.knife_chain_commitment import MoveInstance
    r,p,s,sim=preview(params,terrain)
    path=compile_path(p.draft,s,sim,0.,stage="commitment",first_mask=p.mask)
    native=NativeChainB2(runner_factory=runner,probe_ref="unit-b2")
    native.begin(s)
    native._receipts[1001]=0  # the verified zero queued prefix supplied by this fixture's ChainSim
    offer=B2Offer("commitment",path,p.draft,B["D"]|B["A"],10.,MoveInstance(7,1000,"CC_SLAM"),{})
    planner=SimpleNamespace(measurement_enabled=False)
    result=native.install(offer,planner)
    assert native.commitment is None and native.runner.run is None
    native.planner_result(result);native.final("plan",offer.mask)
    native.before_send(frame=1000,target=1002,mask=offer.mask,flags=0,received_frame=1000)
    assert native.commitment is None
    native.sent()
    assert native.commitment is not None and native._press==1002
    return native


def next_state(f,*,counter=0,hit=None,dead=False):
    s=raw(f);s["ents"][0]["fsms"][0]["t"]=(f-1000)/60
    s["hero"]["cstate_int"][1]=counter
    s["act"].update(target=f,applied=f,hf={"desired":0 if f==1001 else B["D"]|B["A"]})
    if hit:s["ev"]=[{"f":f,"k":"hit","d":{"iid":7,"src":hit}}]
    if dead:s["ents"][0]["hp"]=0
    return s


def test_real_bounce_needs_target_downslash_not_hook_or_predicted_clock(params,terrain):
    n=native_committed(params,terrain)
    n.observe(next_state(1001,counter=8,hit="Harpoon"))
    assert n.commitment is not None and n.post_context is None
    n.observe(next_state(1002,counter=8))
    assert n.commitment is not None
    n.observe(next_state(1003,counter=8,hit="DownSlash"))
    assert n.commitment is None and n.post_context["bounce"]==1003
    assert n.post_context["hit"]==1003
    assert n.counts["b2_real_bounce_handback"]==1


def test_killing_downslash_bounce_hands_back_before_death_recovery(params,terrain):
    n=native_committed(params,terrain)
    n.observe(next_state(1001))
    n.observe(next_state(1002,counter=8,hit="DownSlash",dead=True))
    assert n.commitment is None and n.post_context is not None
    assert n.counts["b2_recovery"]==0


def test_hit_without_observed_bounce_does_not_handoff(params,terrain):
    n=native_committed(params,terrain)
    n.observe(next_state(1001));n.observe(next_state(1002,hit="DownSlash"))
    assert n.commitment is not None and n.post_context is None


def test_mismatched_application_is_fatal(params,terrain):
    n=native_committed(params,terrain)
    n.observe(next_state(1001))
    s=next_state(1002);s["act"]["hf"]["desired"]=0
    with pytest.raises(LearningStop,match="desync"):n.observe(s)


def test_state_gap_is_fatal(params,terrain):
    n=native_committed(params,terrain)
    with pytest.raises(LearningStop,match="STATE"):n.observe(next_state(1002))


def test_nominal_never_earns_real_bounce_receipt(params,terrain):
    n=native_committed(params,terrain)
    assert n._hit is None and n.post_context is None
    # Passing the conditional estimate alone changes no physical evidence.
    n.commitment["predicted_bounce"]=1001
    n.observe(next_state(1001))
    assert n.commitment is not None and n.post_context is None


def test_deleted_budget_is_not_a_new_batch(tmp_path):
    path=tmp_path/"budget.json"
    LearningBudget(path,batch="b",revision="r",worker="w")
    path.unlink()
    with pytest.raises(LearningStop,match="deleted"):
        LearningBudget(path,batch="b",revision="r",worker="w")


def test_stopped_budget_preflight_before_game_connection(tmp_path,monkeypatch):
    from ssbot.combat.knife_chain_budget import preflight_environment
    p=tmp_path/"b.json"
    b=LearningBudget(p,batch="b",revision="r",worker="w")
    with pytest.raises(LearningStop):b.observe(episode=0,frame=1,arm="B",hp_loss=2)
    for key,val in dict(SSBOT_FORUM_CHAIN_B2="1",SSBOT_FORUM_CHAIN_NATIVE="1",SSBOT_FORUM_CHAIN_BATCH="b",
        SSBOT_FORUM_CHAIN_ARM="B",SSBOT_FORUM_CHAIN_BUDGET=str(p),SSBOT_FORUM_CHAIN_PROBE="probe").items():monkeypatch.setenv(key,val)
    with pytest.raises(LearningStop,match="prior batch stopped"):preflight_environment("Forum_W_w7")


def test_harness_budget_catchup_respects_episode_fence_and_kill_inclusive(tmp_path):
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy
    from threading import Lock
    from collections import deque
    b=LearningBudget(tmp_path/"b.json",batch="b",revision="r",worker="w")
    n=NativeChainB2(runner_factory=runner,probe_ref="test",budget=b)
    n.reset(0,start_frame=1000)
    h=[raw(999),raw(1000),raw(1001),raw(1002)]
    h[0]["hero"]["health"]=1
    h[-1]["hero"]["health"]=5
    p=SimpleNamespace(chain_native=n,_inbox=deque(h),_inbox_lock=Lock())
    # Damage AFTER kill is reported as tail and must not end the fight batch.
    ForumPlannerPolicy.learning_check(p,h[-1],SimpleNamespace(death_frame=1001,lethal=[]))
    assert b.state["b_fight_hp"]==0 and b.state["tail_hp"]==2
    n.reset(1,start_frame=2000)
    a,c=raw(2000),raw(2001);c["hero"]["health"]=5
    p._inbox=deque([a,c])
    with pytest.raises(LearningStop,match="2 HP"):
        ForumPlannerPolicy.learning_check(p,c,SimpleNamespace(death_frame=2001,lethal=[]))


def test_planner_disabled_path_is_same_object_and_args(monkeypatch):
    from ssbot.combat.forum_planner import ForumPlanner
    sentinel=object();calls=[]
    p=SimpleNamespace(chain_native=None,_ordinary_tick=lambda *a:(calls.append(a),sentinel)[1])
    args=tuple(object() for _ in range(7))
    assert ForumPlanner.tick(p,*args) is sentinel
    assert calls==[args]


@pytest.fixture
def geometry():
    from ssbot.combat.knife_chain_geometry import B2Geometry
    from ssbot.combat.knife_chain_commitment import MoveInstance
    inst=SimpleNamespace(fam="CC_SLAM")
    def shape(x,y,tk):return np.zeros(np.asarray(x).shape,bool)
    rs=SimpleNamespace(k_shift=0,samples=(0,62),margin_mode="rule",focus=7,
        trk=SimpleNamespace(now={7:(0,0,inst),8:(0,0,SimpleNamespace(fam="CC_JUMP"))},orphan_hazards={}),
        haz_raw={},raw={},layers={},bombs=None,cv=SimpleNamespace(cell=.5,index=lambda x,y:(x,y,np.ones(np.asarray(x).shape,bool))),
        occupied=shape,occupied_only=lambda x,y,t,ids:shape(x,y,t),occupied_hazards=lambda x,y,t,ids:shape(x,y,t))
    path=SimpleNamespace(origin=1000,through=1003,stage="commitment",box=np.tile([20.,5.,20.5,7.],(4,1)),
        commands=np.zeros(3,np.int64),flags=np.zeros(4,np.int64),check_flags=np.zeros(4,np.int64))
    return B2Geometry(SimpleNamespace(rs=rs),1000,MoveInstance(7,990,"CC_SLAM"),inst),rs,path


def contact_at(k):
    def query(x,y,t,ids):
        a=np.zeros(np.asarray(x).shape,bool)
        if 7 in ids:a[:,k]=True
        return a
    return query


def test_delayed_own_hazard_survives_current_move_admission_and_preflight(geometry):
    from ssbot.combat.knife_chain_commitment import TargetMoveAdmission,check_external_path
    geo,rs,p=geometry;rs.occupied_only=contact_at(2);rs.occupied_hazards=contact_at(2)
    admission=TargetMoveAdmission(geo.move,1000,1003,"h2","pass")
    scan=geo.scan(p)
    decision=check_external_path(scan,path_ref=geo.ref(p),target_move=geo.move,first_frame=1000,last_frame=1003,
        stage="commitment",admission=admission)
    assert decision.verdict=="reject" and decision.retained[0].kind=="delayed"
    assert geo.preflight(p).contacts[0].kind=="delayed"


def test_target_same_move_exemption_does_not_follow_real_bounce(geometry):
    from ssbot.combat.knife_chain_commitment import TargetMoveAdmission,check_external_path
    geo,rs,p=geometry;rs.occupied_only=contact_at(2)
    admission=TargetMoveAdmission(geo.move,1000,1003,"h2","pass")
    scan=geo.scan(p)
    assert check_external_path(scan,path_ref=geo.ref(p),target_move=geo.move,first_frame=1000,last_frame=1003,
        stage="commitment",admission=admission).verdict=="pass"
    assert not geo.preflight(p).contacts
    p.stage="continuation"
    scan=geo.scan(p)
    assert check_external_path(scan,path_ref=geo.ref(p),target_move=geo.move,first_frame=1000,last_frame=1003,
        stage="continuation").verdict=="reject"


def test_same_iid_new_move_cannot_inherit_admission(geometry):
    from ssbot.combat.knife_chain_geometry import GeometryUnavailable
    geo,rs,p=geometry;rs.trk.now[7]=(0,0,SimpleNamespace(fam="CC_SLAM"))
    with pytest.raises(GeometryUnavailable,match="instance"):geo.scan(p)


def test_dynamic_coverage_rebuilds_instead_of_clamping_77_to_62(geometry,monkeypatch):
    from ssbot.combat.forum_v2 import RangeSupport
    geo,rs,p=geometry;seen=[]
    monkeypatch.setattr(RangeSupport,"build",lambda *a,**kw:(seen.append(kw),rs)[1])
    assert geo.support(77) is rs
    assert 77 in seen[0]["samples"] and max(seen[0]["samples"])>=77


def test_future_pogo_protection_does_not_erase_contact_endpoint_hazard(geometry):
    geo,rs,p=geometry;rs.occupied_hazards=contact_at(3);rs.occupied_only=contact_at(3)
    p.flags[-1]=km.F_INVULN
    assert geo.scan(p).contacts
    p.stage="continuation"
    assert not geo.scan(p).contacts


def test_active_commitment_is_not_auctioned_against_ordinary_tail():
    from ssbot.combat.forum_planner import ForumPlanner
    offer=SimpleNamespace(stage="active")
    chosen=SimpleNamespace(t_ms={})
    chain=SimpleNamespace(b2=True,arm="B",propose=lambda *a:offer,first_allowed=lambda *a:True,
        install=lambda *a:chosen)
    p=SimpleNamespace(chain_native=chain,ticks=0,_ordinary_tick=lambda *a:pytest.fail("reauctioned commitment"))
    args=(SimpleNamespace(stamp=SimpleNamespace(frame=1000)),np.zeros(km.K),None,None,None,None,None)
    assert ForumPlanner.tick(p,*args) is chosen and p.ticks==1


def test_post_bounce_offers_compete_normally_and_can_lose():
    from ssbot.combat.forum_planner import ForumPlanner
    ordinary=SimpleNamespace(J=30.,S=0,forced_risk=False,t_ms={})
    offer=SimpleNamespace(stage="continuation",value=20.)
    notes=[]
    chain=SimpleNamespace(b2=True,arm="B",propose=lambda *a:offer,first_allowed=lambda *a:True,
        install=lambda *a:pytest.fail("forced post-bounce keys"),_note=lambda *a,**k:notes.append((a,k)))
    p=SimpleNamespace(chain_native=chain,_ordinary_tick=lambda *a:ordinary)
    args=(SimpleNamespace(stamp=SimpleNamespace(frame=1000)),np.zeros(km.K),None,None,None,None,None)
    assert ForumPlanner.tick(p,*args) is ordinary and notes


def test_nominal_unsupported_is_rejected_without_hiding_other_defects(params,terrain,monkeypatch):
    from ssbot.combat import knife_chain_b2 as mod
    from ssbot.combat.knife_chain_commitment import MoveInstance
    from ssbot.combat.knife_chain_nominal import NominalUnsupported
    _,p,s,sim=preview(params,terrain)
    n=NativeChainB2(runner_factory=runner,probe_ref="test")
    n.begin(s);n.prepare(s,ground=True,accepting=True,sim=sim)
    move=MoveInstance(7,1000,"CC_SLAM")
    monkeypatch.setattr(n,"_preview",lambda:(p,move))
    fc=SimpleNamespace(rs=SimpleNamespace(trk=SimpleNamespace(now={7:(0,0,SimpleNamespace(fam="CC_SLAM"))})))
    def fail(*a,**k):raise NominalUnsupported("model unavailable")
    monkeypatch.setattr(mod,"compile_path",fail)
    assert n.propose(None,None,sim.start,sim.hold,sim.prefix,fc,None,None) is None
    assert n.counts["b2_unchecked"]==1
    def defect(*a,**k):raise RuntimeError("program defect")
    monkeypatch.setattr(mod,"compile_path",defect)
    with pytest.raises(RuntimeError,match="defect"):
        n.propose(None,None,sim.start,sim.hold,sim.prefix,fc,None,None)


def test_neutral_wait_before_branch_action_does_not_fake_unavailable(params,terrain):
    _,p,s,sim=preview(params,terrain)
    path=compile_path(p.draft,s,sim,0.,stage="commitment",first_mask=p.mask)
    paths,errors=post_paths(path,params,terrain)
    # Canonical exits include the table's wait until its direction/dash clock.
    usable=[k for k,q in paths.items() if NativeChainB2.continuation_executable(k,q)]
    assert len(usable)>=2,(usable,errors)


def test_complete_candidate_generation_with_clear_external_geometry(params,terrain,geometry,monkeypatch):
    from ssbot.combat.knife_chain_commitment import MoveInstance
    _,initial,s,sim=preview(params,terrain)
    r=initial.draft
    s["f"]=1024;s["ents"][0]["fsms"][0]["t"]=24/60
    sim=ChainSim(sim.start,sim.prefix,sim.hold,params,terrain,1024,1024)
    p=r.preview(1024,s,True,True,t_game=24/60,sim=sim)
    assert p.draft.run.link=="jump"
    n=NativeChainB2(runner_factory=runner,probe_ref="unit")
    n.begin(s);n._clock=24/60;n.prepare(s,ground=True,accepting=True,sim=sim)
    move=MoveInstance(7,1000,"CC_SLAM")
    monkeypatch.setattr(n,"_preview",lambda:(p,move))
    geo,rs,_=geometry
    prefs=SimpleNamespace(weights={"hit":10.},stance_x=35.,boss_x=None,risk_x=np.array([]),risk=np.array([]))
    offer=n.propose(None,None,sim.start,sim.hold,sim.prefix,SimpleNamespace(rs=rs),prefs,None)
    assert offer is not None and offer.stage=="commitment",list(n.events)[-3:]
    assert offer.details["continuations"]["verdict"]=="pass"
    assert len(offer.details["continuations"]["qualifying_kinds"])>=2
    assert n.commitment is None and n._hit is None


def test_fight_budget_ends_at_real_clapper_kill_not_delayed_wave_change(tmp_path):
    b=LearningBudget(tmp_path/"b.json",batch="b",revision="r",worker="w")
    n=NativeChainB2(runner_factory=runner,probe_ref="test",budget=b)
    n.reset(0,start_frame=1000)
    n.observe_learning(raw(1000))
    s=raw(1001);s["ents"][0]["hp"]=0
    s["ev"]=[{"f":1001,"k":"hit","d":{"ent":7,"type_key":"Song Heavy Sentry","dead":True}}]
    n.observe_learning(s)
    a=raw(1002);a["hero"]["health"]=5
    n.observe_learning(a,kill_frame=1030)
    assert n._kill_frame==1001
    assert b.state["b_fight_hp"]==0 and b.state["tail_hp"]==2


def test_bootstrap_integrity_halt_is_persistent_without_a_constructed_budget(tmp_path,monkeypatch):
    from ssbot.combat.knife_chain_budget import mark_integrity_halt,preflight_environment
    path=tmp_path/"b.json"
    for key,val in dict(SSBOT_FORUM_CHAIN_B2="1",SSBOT_FORUM_CHAIN_NATIVE="1",SSBOT_FORUM_CHAIN_BATCH="b",
        SSBOT_FORUM_CHAIN_ARM="B",SSBOT_FORUM_CHAIN_BUDGET=str(path),SSBOT_FORUM_CHAIN_PROBE="test").items():monkeypatch.setenv(key,val)
    mark_integrity_halt("missing config/log")
    before=path.with_name(path.name+".halt").read_bytes()
    mark_integrity_halt("second failure")
    assert path.with_name(path.name+".halt").read_bytes()==before
    with pytest.raises(LearningStop,match="halt"):preflight_environment("Forum_W_w7")


def test_a_arm_keeps_ordinary_planner_and_no_chain_candidates():
    from ssbot.combat.forum_planner import ForumPlanner
    n=NativeChainB2(runner_factory=runner,probe_ref="test",arm="A")
    assert n.candidate_generation is False and n.rows() is None
    sentinel=object();p=SimpleNamespace(chain_native=n,_ordinary_tick=lambda *a:sentinel)
    assert ForumPlanner.tick(p,*[None]*7) is sentinel


def test_decision_boundary_is_independent_of_link_and_is_early_for_close_entry():
    from ssbot.combat.knife_chain_nominal import is_committing,NominalProfile
    r=SimpleNamespace(chain="slam_jump",link="walk",v={"x_start":5.,"k":22})
    assert not is_committing(r)
    r.v["k"]=23
    assert is_committing(r)  # observed antic k=21, not the later jump link
    r.v.update(k=2,x_start=3.)
    assert is_committing(r)
    r.v.update(x_start=5.);r.chain="slam_claw";r.link="look"
    assert is_committing(r)
    with pytest.raises(ValueError):NominalProfile(short_frames=9)


def test_b2_both_arms_use_measured_poly_and_default_path_stays_original(monkeypatch):
    from ssbot.combat.attack_range import table_path,load_table
    from ssbot.combat.are_types.clapper import SPEC
    monkeypatch.delenv("SSBOT_FORUM_CHAIN_B2",raising=False)
    old=load_table(spec=SPEC)
    assert table_path(SPEC).name=="attack_range_clapper.npz"
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_B2","1")
    for arm in ["A","B"]:
        monkeypatch.setenv("SSBOT_FORUM_CHAIN_ARM",arm)
        assert table_path(SPEC).name=="attack_range_clapper_poly.npz"
    new=load_table(spec=SPEC)
    for key,a in old.templates.items():
        b=new.templates[key]
        assert a.n==b.n and a.nb==b.nb and a.order==b.order and a.b_dec==b.b_dec
        np.testing.assert_array_equal(a.disp,b.disp)
        if a.ratio is not None:np.testing.assert_array_equal(a.ratio,b.ratio)
    def at(tab,st,x,y):
        tp=tab.templates[("CC_SLAM","main")];sh,u,v=tab._shape(tp,60,True,st)
        ix=int(np.floor(x/tab.cell))-u;iy=int(np.floor(y/tab.cell))-v
        return 0<=iy<sh.shape[0] and 0<=ix<sh.shape[1] and sh[iy,ix]
    assert at(old,"Slam 2",1.,2.5) and not at(new,"Slam 2",1.,2.5)
    assert at(new,"Slam 2",5.,0.) # the actual hammer interior remains dangerous


def test_late_send_is_stopped_before_transport(params,terrain):
    n=native_committed(params,terrain)
    n.begin(next_state(1001));n.final("plan",0)
    with pytest.raises(LearningStop,match="deadline"):
        n.before_send(frame=1001,target=1003,mask=0,flags=0,received_frame=1008)
    assert n.dispatch.sent_for(1003) is None


def test_logical_fork_only_appends_to_private_audit_lists(params,terrain):
    from ssbot.combat.knife_chain_nominal import logical_copy
    _,p,s,sim=preview(params,terrain)
    r=p.draft
    r.run.trace.append(["old"]);r.run.path.append(["old"]);r.run.sent.append((1,0))
    q=logical_copy(r)
    q.run.trace.append(["new"]);q.run.path.append(["new"]);q.run.sent.append((2,1))
    q.run.v["tmp_mutable"]={"new":True}
    assert len(r.run.trace)+1==len(q.run.trace)
    assert len(r.run.path)+1==len(q.run.path)
    assert len(r.run.sent)+1==len(q.run.sent)
    assert "tmp_mutable" not in r.run.v


def test_policy_opt_in_b2_constructs_once_and_reuses_persistent_budget(tmp_path,monkeypatch):
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy
    from ssbot.train import forum_planner_policy as policy_module
    for key,val in dict(SSBOT_FORUM_CHAIN_B2="1",SSBOT_FORUM_CHAIN_NATIVE="1",SSBOT_FORUM_CHAIN_BATCH="b",
        SSBOT_FORUM_CHAIN_ARM="B",SSBOT_FORUM_CHAIN_BUDGET=str(tmp_path/"b.json"),SSBOT_FORUM_CHAIN_PROBE="test").items():monkeypatch.setenv(key,val)
    monkeypatch.setattr(policy_module.kin,"hero2_on",lambda:True)
    p=SimpleNamespace(crest="Wanderer",clash="off",m2=None,air_show=None,wpress=None,chain_native=None,
        planner=None,episode=0,log_path=tmp_path/"decisions.jsonl",_fcfg=lambda c:SimpleNamespace(v2=True),
        link=SimpleNamespace(frame=1000,state=raw(1000)))
    ForumPlannerPolicy._reset_chain_native(p)
    n=p.chain_native
    assert type(n) is NativeChainB2 and n.budget is not None and n._budget_hp==7
    p.link.state["hero"]["health"]=5
    p.episode=1
    ForumPlannerPolicy._reset_chain_native(p)
    assert p.chain_native is n and n.episode==1 and n._budget_hp==5
    assert n.budget.state["batch"]=="b"


def test_shifted_cached_geometry_rebuilt_for_current_instance(geometry,monkeypatch):
    from ssbot.combat.forum_v2 import RangeSupport
    geo,rs,p=geometry;rs.k_shift=-1;calls=[]
    monkeypatch.setattr(RangeSupport,"build",lambda *a,**k:(calls.append(k),rs)[1])
    geo.support(10);geo.support(10)
    assert len(calls)==1 and "k_shift" not in calls[0]


def test_corrupt_budget_is_integrity_stop_not_counter_reset(tmp_path):
    p=tmp_path/"b.json";b=LearningBudget(p,batch="b",revision="r",worker="w")
    p.write_text("broken")
    with pytest.raises(LearningStop,match="corrupt"):b.check()
    assert p.read_text()=="broken"


def test_known_late_application_two_frames_is_accepted_without_pogo_credit(params,terrain):
    n=native_committed(params,terrain)
    for f in [1001,1002,1003]:
        s=next_state(f);s["act"].update(target=1000,applied=1000,hf={"desired":0});n.observe(s)
    s=next_state(1004);s["act"].update(target=1002,applied=1004,hf={"desired":B["D"]|B["A"]})
    n.observe(s)
    assert n._pending=={} and n.counts["b2_application_late"]==1
    assert n._accepted is None and n._hit is None and n.post_context is None


def test_skipped_target_bracket_compares_skipped_key_to_covering_report(params,terrain):
    n=native_committed(params,terrain);wanted=B["D"]|B["A"]
    n._receipts[1003]=wanted
    n.observe(next_state(1001))
    s=next_state(1002);s["act"].update(target=1000,applied=1000,hf={"desired":0});n.observe(s)
    n.observe(next_state(1003))
    assert 1002 not in n._pending
    assert n._application[1002]["kind"]=="covered_same_key"
    assert n._application[1002]["applied"] is None
    assert n.counts["b2_application_skipped"]==1


def test_changed_key_reporting_gap_is_covered_without_acceptance_credit(params,terrain):
    n=native_committed(params,terrain)
    n._receipts[1003]=0
    n.observe(next_state(1001))
    s=next_state(1002);s["act"].update(target=1001,applied=1001,hf={"desired":0});n.observe(s)
    s=next_state(1003);s["act"].update(target=1003,applied=1003,hf={"desired":0});n.observe(s)
    assert n._application[1002]["kind"]=="covered_changed_key"
    assert n._application[1002]["applied"] is None and n._accepted is None
    assert n.counts["b2_application_skipped_changed_key"]==1


def test_no_cover_times_out_after_four_frames_and_missing_anchor_is_not_a_bracket(params,terrain):
    n=native_committed(params,terrain)
    for f in range(1001,1007):
        s=next_state(f);s["act"].update(target=1000,applied=1000,hf={"desired":0});n.observe(s)
    s=next_state(1007);s["act"].update(target=1000,applied=1000,hf={"desired":0})
    with pytest.raises(LearningStop,match="four-frame"):n.observe(s)


def test_held_prefix_uses_observed_own_desired_not_invented_zero(params,terrain):
    n=native_committed(params,terrain)
    s=next_state(1002)
    desired,source=n.queued_prefix(1002,s)
    assert desired==B["D"]|B["A"] and source=="held_observed_desired_no_queued_send"
    s["act"]["hf"]["desired"]=0
    assert n.queued_prefix(1002,s)[0] is None


def test_missing_entry_distance_is_not_close_entry():
    from ssbot.combat.knife_chain_nominal import is_committing
    for value in [None]:
        r=SimpleNamespace(chain="slam_jump",link="land",v={"x_start":value,"k":4})
        assert not is_committing(r)
        r.v["k"]=23
        assert is_committing(r)


def test_hook_recovery_wait_keeps_normal_planner_out_until_observed_control(params,terrain):
    from ssbot.combat.forum_planner import ForumPlanner
    n=native_committed(params,terrain)
    s=next_state(1001);s["hero"]["anim"]["clip"]="Harpoon Dash";s["hero"]["hero_accepting_input"]=False
    n.observe(s);n._recover("missing model prefix",1001)
    assert n.recovery is not None and n.commitment is None
    p=SimpleNamespace(chain_native=n,ticks=0,measurement_enabled=False,
       _ordinary_tick=lambda *a:pytest.fail("ordinary planner used during unsupported hook"))
    ctx=SimpleNamespace(allowed_mask=np.ones(64,bool));ws=SimpleNamespace(stamp=SimpleNamespace(frame=1001))
    r=ForumPlanner.tick(p,ws,np.zeros(km.K),None,np.zeros(1,np.int64),None,None,ctx)
    assert r.S==1 and r.forced_risk and r.mask==0
    s=next_state(1002);s["hero"]["hero_accepting_input"]=True
    n.observe(s)
    assert n.recovery is None and n.counts["b2_hook_recovery_handoff"]==1


def test_same_key_gap_requires_later_matching_report(params,terrain):
    n=native_committed(params,terrain);wanted=B["D"]|B["A"]
    n._receipts[1001]=wanted;n._receipts[1003]=wanted
    s=next_state(1001);s["act"].update(target=1001,applied=1001,hf={"desired":wanted});n.observe(s)
    s=next_state(1002);s["act"].update(target=1001,applied=1001,hf={"desired":wanted});n.observe(s)
    assert 1002 in n._pending
    n.observe(next_state(1003))
    assert n._application[1002]["kind"]=="covered_same_key"
    assert n._application[1002]["applied"] is None
    assert n.counts["b2_application_skipped_same_key"]==1


def test_b2_warmup_exercises_model_signatures_without_real_run(params,terrain):
    from ssbot.combat.knife_chain_nominal import warm_nominal,compiled_signatures
    report=warm_nominal(params)
    assert report["jump_to_bounce"]>36 and report["post_paths"]==3 and report["hook_control"]>0
    before=compiled_signatures()
    _,p,s,sim=preview(params,terrain)
    path=compile_path(p.draft,s,sim,0.,stage="commitment",first_mask=p.mask)
    post_paths(path,params,terrain)
    after=compiled_signatures()
    assert all(before.get(k,())==v for k,v in after.items()),{k:v for k,v in after.items() if before.get(k,())!=v}


def test_measured_entry_distance_is_carried_independently_of_missing_legacy_record():
    from ssbot.combat.knife_chain_nominal import is_committing
    r=SimpleNamespace(chain="slam_jump",link="land",v={"x_start":None,"k":4,"_b2_entry_distance":3.7})
    assert not is_committing(r)
    r.v["_b2_entry_distance"]=2.8
    assert is_committing(r)


def test_matching_later_report_can_cover_at_four_frame_boundary(params,terrain):
    n=native_committed(params,terrain);n._receipts[1004]=0
    n.observe(next_state(1001))
    for f in range(1002,1006):
        st=next_state(f);st["act"].update(target=1001,applied=1001,hf={"desired":0});n.observe(st)
    st=next_state(1006);st["act"].update(target=1004,applied=1006,hf={"desired":0});n.observe(st)
    assert n._pending=={} and n._application[1002]["kind"]=="covered_changed_key"
    assert n._application[1002]["between"]==[1001,1004]


def test_a_later_match_without_an_earlier_match_is_not_a_bracket(params,terrain):
    n=native_committed(params,terrain);n._receipts.pop(1001);n._receipts[1003]=0
    for f in range(1001,1003):
        st=next_state(f);st["act"].update(target=1000,applied=1000,hf={"desired":0});n.observe(st)
    for f in range(1003,1007):
        st=next_state(f);st["act"].update(target=1003,applied=1003,hf={"desired":0});n.observe(st)
    assert 1002 in n._pending
    st=next_state(1007);st["act"].update(target=1003,applied=1003,hf={"desired":0})
    with pytest.raises(LearningStop,match="four-frame"):n.observe(st)


def test_first_cover_after_four_frame_deadline_does_not_revive_pending(params,terrain):
    n=native_committed(params,terrain);n._receipts[1005]=0
    n.observe(next_state(1001))
    for f in range(1002,1007):
        st=next_state(f);st["act"].update(target=1001,applied=1001,hf={"desired":0});n.observe(st)
    st=next_state(1007);st["act"].update(target=1005,applied=1007,hf={"desired":0})
    with pytest.raises(LearningStop,match="four-frame"):n.observe(st)
    assert 1002 in n._pending and 1002 not in n._application
