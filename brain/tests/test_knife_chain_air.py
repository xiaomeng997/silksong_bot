"""Manual air cut-in: one table, separate release/strike, real receipt ownership."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import pytest
from ssbot.combat.knife_chain_air import load_runner,AirPlan,render,entry_context,advance,complete_hf
from ssbot.combat.knife_chain_eval import Run
from ssbot.combat.knife_chain_format import MASK_NAMES as B,load_chains,table_digest
from ssbot.combat.knife_chain_air_native import NativeManualAirChain
from ssbot.combat.knife_chain_b2 import B2Offer
from ssbot.combat.knife_chain_budget import LearningStop


def raw(f=1000):
    v=[27.,3.,30.2,3.,30.2,6.9,27.,6.9]
    target={"iid":7,"type_key":"Song Heavy Sentry","hp":130,"flipX":False,"pos":[28.9,7.45],
        "fsms":[{"name":"Control","state":"Slam Antic","t":0.}],
        "colliders":[{"name":"Song Heavy Sentry (1)","enabled":True,"verts_world":v}]}
    return {"f":f,"dt":1/60,"hero":{"health":7,"silk":9,"pos":[23.9,12.],"box":[23.65,10.4,24.15,12.5],
        "vel":[2.,-6.],"facing":1,"anim":{"clip":"Umbrella Turn"},"hero_accepting_input":False,
        "can":{"input":False,"attack":False},"tm":{"atk_cd":0.},"cstate":[0,0],"cstate_int":[0,0,0,0]},
        "ents":[target],"ev":[],"act":{"target":f,"applied":f,"mask":B["J"],
        "hf":{"latched":B["J"],"desired":B["J"],"pending":[0]*22,"age":[100]*22}}}


def plan():return AirPlan(7,1000,0.,0,B["R"],26,18,27,30,7,1000,1030)


def test_table_binds_without_changing_existing_format():
    r=load_runner();assert set(r.chains["air_strike"].links)=={"align","fall","strike","observe"}
    assert r.binding["table_digest"]==table_digest(r.chains)
    assert all(a.status=="unfitted" for a in r.chains["air_strike"].admission.values())


def test_one_table_controls_release_fall_and_separate_attack():
    r=load_runner();p=plan();a=render(r,p,0,42)
    # Commands begin at antic k2 (not observation k0).
    assert a[23]&B["J"] and not a[24]&B["J"]
    assert a[24]&B["D"] and not a[24]&B["A"]
    assert a[25]==B["D"]|B["A"]|B["R"]
    assert a[26]==B["D"] and a[27]==B["D"]
    assert not np.any(a[28:]&B["J"])
    assert r.run is None and not r.done


def test_cloak_can_input_false_does_not_forbid_observable_air_entry():
    s=raw();before=deepcopy(s);ctx=entry_context(s,0.,load_runner())
    assert ctx is not None and ctx[0].ready and s==before


@pytest.mark.parametrize("mutation",["short_hf","missing_cd","nonfloat","other_attacking","no_body","old_antic"])
def test_unknown_or_outside_manual_scope_does_not_silently_enter(mutation):
    s=raw()
    if mutation=="short_hf":s["act"]["hf"]["age"]=[0]
    elif mutation=="missing_cd":s["hero"]["tm"]={}
    elif mutation=="nonfloat":s["hero"]["anim"]["clip"]="Umbrella Inflate Antic"
    elif mutation=="other_attacking":
        e=deepcopy(s["ents"][0]);e["iid"]=8;e["fsms"][0]["state"]="Jump Antic";s["ents"].append(e)
    elif mutation=="no_body":s["ents"][0]["colliders"]=[]
    else:s["ents"][0]["fsms"][0]["t"]=1.
    assert entry_context(s,1.,load_runner()) is None


def test_same_enemy_new_slam_is_a_different_instance():
    r=load_runner();p=plan();r.run=Run("air_strike","fall",p.variables());s=raw(1020)
    assert advance(r,p,s,20/60) is None and r.run is None


def test_current_move_continues_by_game_clock_not_raw_frame_count():
    r=load_runner();p=plan();r.run=Run("air_strike","align",p.variables());s=raw(1050)
    # Frozen game clock: raw sequence advanced, current move time did not.
    assert advance(r,p,s,0.)==B["J"]|B["R"]


def committed():
    n=NativeManualAirChain(runner_factory=load_runner,probe_ref="manual-air-test");n.reset(0,start_frame=1000)
    n.begin(raw());p=plan();n._air_plan=p
    draft=load_runner();draft.run=Run("air_strike","align",p.variables())
    offer=B2Offer("manual_commitment",None,draft,B["J"]|B["R"],0.,p.move,
        {"manual_air":True,"predicted_bounce":1030,"safety_basis":"test fixture, not checked"})
    res=n.install(offer,NS(measurement_enabled=False))
    assert res.n_safe==0 and n.commitment is None and n.runner.run is None
    n.planner_result(res);n.final("plan",offer.mask)
    n.before_send(frame=1000,target=1002,mask=offer.mask,flags=0,received_frame=1000)
    assert n.commitment is None
    n.sent();assert n.commitment is not None and not n.commitment["fixed_hook"]
    return n


def test_manual_commitment_promotes_only_after_successful_send():
    n=committed();assert n.runner.run.chain=="air_strike" and n._press is None


def test_predicted_bounce_or_other_target_hit_cannot_handoff():
    n=committed();n._press=1002;s=raw(1001);s["hero"]["anim"]["clip"]="DownSlash"
    n.observe(s)
    s=raw(1002);s["hero"]["anim"]["clip"]="DownSlash";s["hero"]["cstate_int"][1]=8
    s["act"]["hf"]["desired"]=B["J"]|B["R"];s["act"]["target"]=1002
    s["ev"]=[{"k":"hit","f":1002,"d":{"iid":8,"src":"DownSlash"}}];n.observe(s)
    assert n.commitment is not None and n.post_context is None


def test_actual_target_downslash_plus_bounce_hands_back():
    n=committed();n._press=1002;n.observe(raw(1001));s=raw(1002)
    s["hero"]["anim"]["clip"]="DownSlash";s["hero"]["cstate_int"][1]=8
    s["act"]["hf"]["desired"]=B["J"]|B["R"]
    s["ev"]=[{"k":"hit","f":1002,"d":{"iid":7,"src":"DownSlashAlt"}}];n.observe(s)
    assert n.commitment is None and n.post_context["bounce"]==1002


def test_ground_h2_is_not_suppressed_when_air_family_has_no_entry():
    n=NativeManualAirChain(runner_factory=load_runner,probe_ref="test");s=raw();s["hero"]["anim"]["clip"]="Idle"
    n.begin(s);assert not n.candidate_generation


def test_program_digest_is_bound_to_air_table_not_ground_slam():
    assert [p.name for p in NativeManualAirChain.program_tables()]==["knife_chain_air_v01.json"]


def test_late_first_attack_is_neutralized_and_move_is_not_retried():
    n=committed();p=plan();n._b2_selected=B2Offer("active",None,n.runner,B["D"]|B["A"],0.,p.move,{"manual_air":True})
    n.dispatch.begin_tick(1025)
    mask=n.before_send(frame=1025,target=1027,mask=B["D"]|B["A"],flags=0,received_frame=1027)
    assert mask==0 and p.move in n._air_finished and n.commitment is None


def test_post_bounce_scans_use_the_current_forecast_origin_and_keep_target(monkeypatch):
    from ssbot.combat.knife_chain_commitment import ContactScan,PathContact
    from ssbot.combat.knife_chain_nominal import NominalProfile
    import ssbot.combat.knife_chain_post_actions as post
    n=NativeManualAirChain(runner_factory=load_runner,probe_ref="test");move=plan().move
    parent=NS(through=1030)
    # replace() takes a dataclass; keep the real nominal container for the parent.
    from ssbot.combat.knife_chain_nominal import NominalPath
    parent=NominalPath(1000,"air_manual",np.zeros(30,np.int64),np.zeros(30,np.int64),
        np.zeros((86,31)),np.zeros((31,4)),np.zeros((31,2)),np.zeros(31,np.int64),
        np.zeros(31,np.int64),np.arange(31)/60,None,None,None,0,"bounce",1027,1030,{})
    def make(parent,params,terrain,kind,profile,full=False):
        return NS(origin=1030,through=1042,end="handback" if full else "short",commands=np.zeros(12),kind=kind)
    monkeypatch.setattr(post,"ordinary_post",make)
    monkeypatch.setattr(n,"continuation_executable",lambda kind,p:True)
    class Geo:
        origin=1000
        def ref(self,p):return p.kind
        def scan(self,p):
            # Left hits this target AFTER the predicted bounce. It must remain.
            return ContactScan(self.ref(p),p.origin,p.through,
                (PathContact(1040,move.target_iid,"move",move),) if p.kind=="left_landing" else (),"test")
    out=n._continuations(parent,NS(params=None,terrain=None),Geo(),move)
    assert out.verdict=="pass" and out.mode=="full_exit" and out.qualifying_kinds==("right_landing",)
    assert out.full_checked==("right_landing",)


def test_production_factory_keeps_explicit_profile_and_binds_manual_table(tmp_path,monkeypatch):
    for k,v in dict(SSBOT_FORUM_CHAIN_B2="1",SSBOT_FORUM_CHAIN_BATCH="air-factory-test",SSBOT_FORUM_CHAIN_ARM="B",
        SSBOT_FORUM_CHAIN_PROBE="manual-air-unfitted",SSBOT_FORUM_CHAIN_BUDGET=str(tmp_path/"b.json"),
        SSBOT_FORUM_CHAIN_FAST_HOOK="0",SSBOT_FORUM_CHAIN_FIXED_HOOK="0").items():monkeypatch.setenv(k,v)
    n=NativeManualAirChain.from_env(journal=str(tmp_path/"chain.jsonl"))
    assert n.require_send_clock and n.budget is not None
    assert set(n.runner.chains)=={"air_strike"} and n.profile.short_frames>9
    n.reset(1);assert n.runner.run is None and not n._air_finished


def test_same_move_can_have_different_clock_epochs_but_not_different_age():
    n=NativeManualAirChain(runner_factory=load_runner,probe_ref="test");n._clock=10.
    inst=NS(fam="CC_SLAM",t0=199.8)
    fc=NS(rs=NS(trk=NS(T=200.,now={7:(None,None,inst)})))
    assert n._geometry(fc,plan().move,1000,ta=9.8).instance is inst
    inst.t0=199.
    from ssbot.combat.knife_chain_geometry import GeometryUnavailable
    with pytest.raises(GeometryUnavailable,match="another instance"):
        n._geometry(fc,plan().move,1000,ta=9.8)


def test_w13_preflight_requires_explicit_air_probe_and_recording(tmp_path,monkeypatch):
    from ssbot.combat.knife_chain_budget import preflight_environment
    for k,v in dict(SSBOT_FORUM_CHAIN_B2="1",SSBOT_FORUM_CHAIN_NATIVE="1",SSBOT_FORUM_CHAIN_BATCH="test",
        SSBOT_FORUM_CHAIN_PROBE="manual-air",SSBOT_FORUM_CHAIN_ARM="B",SSBOT_FORUM_CHAIN_BUDGET=str(tmp_path/"b.json")).items():monkeypatch.setenv(k,v)
    monkeypatch.delenv("SSBOT_FORUM_CHAIN_AIR_MANUAL",raising=False)
    with pytest.raises(LearningStop,match="allowed encounter"):preflight_environment("Forum_W_w13")
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_AIR_MANUAL","1")
    preflight_environment("Forum_W_w13")
    with pytest.raises(LearningStop,match="allowed encounter"):preflight_environment("Forum_W_w13",no_record=True)
    with pytest.raises(LearningStop,match="allowed encounter"):preflight_environment("Forum_W_w14")
