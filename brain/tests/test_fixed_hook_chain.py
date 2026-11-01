"""The user-selected fixed hook uses actual observations, no future evaluator."""
from dataclasses import replace
from types import SimpleNamespace as NS
from copy import deepcopy
import json
from pathlib import Path
import numpy as np
import pytest
from ssbot.knowledge import kinematics as km
from ssbot.combat.air_chain import ChainSim
from ssbot.combat.knife_chain_slam import load_runner
from ssbot.combat.knife_chain_nominal import NominalProfile
from ssbot.combat.knife_chain_b2 import NativeChainB2
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from tests.test_knife_chain_b2 import params,terrain,raw,bits


def state(f=1000,**kw):
    s=raw(f);s["fs"]=1
    s["hero"].update(pos=[36.,4.568],box=[35.75,3.015,36.25,5.094],vel=[-8.25,0.])
    s["hero"]["can"]={"harpoon":True}
    s["act"].update(mask=B["L"],hf={"desired":B["L"],"latched":B["L"]})
    s["ents"][0]["fsms"][0]["t"]=(f-1000)/60
    return s


def simulation(s,params,terrain,queued):
    h=s["hero"];f=s["f"]
    S=km.initial_state(params,h["pos"][0],h["pos"][1],ground=True,facing=-1,silk=9)
    return ChainSim(S,np.array([queued],np.int64),km.HoldState.idle(1),params,terrain,f,f)


def fixed():
    return NativeChainB2(runner_factory=lambda:load_runner(fixed_hook=True),probe_ref="fixed-unit",
                        profile=NominalProfile(fixed_hook=True))


def propose(n,s,params,terrain):
    if n.last_observed is None:n._receipts[s["f"]+1]=B["L"]  # known queued fixture prefix
    n.begin(s)
    queued=n._receipts.get(s["f"]+1,s["act"]["hf"]["desired"])
    sim=simulation(s,params,terrain,queued)
    n.prepare(s,ground=s["f"]<1003,accepting=s["hero"].get("hero_accepting_input",True),sim=sim)
    return n.propose(None,None,None,None,None,None,None,None)


def send(n,o):
    planner=NS(measurement_enabled=False)
    res=n.install(o,planner);n.planner_result(res);n.final("plan",o.mask)
    n.before_send(frame=n.dispatch.frame,target=n.dispatch.frame+2,mask=o.mask,flags=0,received_frame=n.dispatch.frame)
    out=n.sent()
    return out,res


def test_old_loader_unchanged_and_new_chain_is_explicit():
    assert "fixed_hook" not in load_runner().chains
    r=load_runner(fixed_hook=True)
    assert "fixed_hook" in r.chains and not r.cfg0["CLAWSTRIKE"]
    assert all(a.status=="unfitted" for a in r.chains["fixed_hook"].admission.values())
    assert NominalProfile().fixed_hook is False
    with pytest.raises(ValueError):replace(NominalProfile(),fixed_hook=1)


def test_no_hook_search_nominal_geometry_or_N2_on_fixed_route(monkeypatch,params,terrain):
    from ssbot.combat import claw_strike,air_chain,knife_chain_b2 as m
    def forbidden(*a,**kw):pytest.fail("heavy hook evaluator ran")
    monkeypatch.setattr(claw_strike.ClawStrike,"plan",forbidden)
    monkeypatch.setattr(air_chain,"evaluate",forbidden)
    monkeypatch.setattr(m,"compile_path",forbidden)
    monkeypatch.setattr(m,"B2Geometry",forbidden)
    n=fixed();o=propose(n,state(),params,terrain)
    assert o.stage=="fixed_commitment" and o.mask==B["J"] and o.path is None
    assert n.commitment is None and n.runner.run is None
    out,res=send(n,o)
    assert n.commitment["fixed_hook"] and out.target_frame==1002
    assert n._hook_start["targets"]==(1004,1005)
    assert res.n_safe==0  # allowed empirical keys, never a fake geometry pass


@pytest.mark.parametrize("bad",["air","unavailable","backwards","turn","hf","close","far","rune"])
def test_entry_declines_unsupported_observation_without_search(bad,params,terrain):
    from ssbot.combat.knife_chain_eval import Run,X
    from ssbot.combat.knife_chain_slam import Obs
    r=load_runner(fixed_hook=True);r.anchor.fixed_hook_enabled=True
    s=state();o=Obs(1000,s,True,True,0,None,None,None,s["ents"][0],"Slam Antic",0)
    v=dict(r.anchor.var_defaults);v.update(iid=7,face=1,k=2)
    x=X(r,Run("fixed_hook","pre",v),o)
    if bad=="air":o.ground=False
    if bad=="unavailable":s["hero"]["can"]["harpoon"]=False
    if bad=="backwards":s["hero"]["vel"][0]=8.25
    if bad=="turn":s["hero"]["facing"]=1
    if bad=="hf":s["act"]["hf"]["latched"]=0
    if bad=="close":s["hero"]["box"][0:3:2]=[34.75,35.25]
    if bad=="far":s["hero"]["box"][0:3:2]=[37.75,38.25]
    if bad=="rune":o.bombs=np.zeros((1,3))
    assert not r.P.guards["fixed_hook_entry"](x)


def test_real_transaction_template_through_bounce_and_physical_wait(monkeypatch,params,terrain):
    from ssbot.combat import knife_chain_b2 as m
    monkeypatch.setattr(m,"compile_path",lambda *a,**k:pytest.fail("nominal hook ran"))
    n=fixed();emitted={};bounced_at=None;release_at=None
    for f in range(1000,1067):
        s=state(f);h=s["hero"];age=f-1000
        applied=n._receipts.get(f,B["L"])
        s["act"].update(target=f,applied=f,mask=applied,hf={"desired":applied,"latched":applied})
        if 4<=age<29:h["anim"]["clip"]="Harpoon Catch";h["hero_accepting_input"]=False
        if age>=29:h.update(pos=[33.8,7.],box=[33.55,5.5,34.05,8.],vel=[0.,17.4])
        if age>=48:
            st="Slam 0" if age<52 else "Slam 1" if age<55 else "Slam 2" if age<61 else "Slam Recover"
            s["ents"][0]["fsms"][0].update(state=st,t=0.)
        if age==48:h["anim"]["clip"]="DownSlash"
        if age==50:
            h["cstate_int"][1]=8
            s["ev"]=[{"k":"hit","f":f,"d":{"ent":7,"src":"DownSlash"}}]
        # Frozen render frame AFTER Recover cannot spend one of the two steps.
        if age==62:s["fs"]=0;s["dt"]=0.
        o=propose(n,s,params,terrain)
        if age==50:
            assert n.post_context["fixed_hook"] and n.commitment is None
            bounced_at=f
        if o is None:
            if n.post_context is None and age>50:release_at=f;break
            pytest.fail(f"unexpected no proposal at {f}")
        if age>=50:assert o.mask==0
        send(n,o);emitted[f+2]=o.mask
    assert [emitted[k] for k in (1002,1003,1004,1005)]==[B["J"],B["J"]|B["L"],B["CLAW"]|B["L"],B["CLAW"]|B["L"]]
    assert emitted[1046]==B["D"] and emitted[1047]==B["D"]|B["A"]
    assert bounced_at==1050 and release_at==1064
    assert n.runner.run is None


def test_late_first_jump_is_neutral_veto_and_never_slid(params,terrain):
    n=fixed();o=propose(n,state(),params,terrain)
    planner=NS(measurement_enabled=False);r=n.install(o,planner);n.planner_result(r);n.final("plan",o.mask)
    assert n.before_send(frame=1000,target=1002,mask=o.mask,flags=0,received_frame=1002)==0
    n.sent()
    assert o.move in n._failed_hook_moves and n.commitment is None


def test_arm_A_cannot_enter_fixed_table(params,terrain):
    n=NativeChainB2(runner_factory=lambda:load_runner(fixed_hook=True),probe_ref="unit-A",arm="A",profile=NominalProfile(fixed_hook=True))
    assert propose(n,state(),params,terrain) is None
    assert not n.runner.anchor.fixed_hook_enabled


def test_previous_moves_jump_cannot_bypass_new_first_jump_deadline(params,terrain):
    from ssbot.combat.knife_chain_commitment import MoveInstance
    n=fixed();n._fixed_jump_sent_for=MoveInstance(7,999,"CC_SLAM")
    o=propose(n,state(),params,terrain)
    p=NS(measurement_enabled=False);r=n.install(o,p);n.planner_result(r);n.final("plan",o.mask)
    assert n.before_send(frame=1000,target=1002,mask=o.mask,flags=0,received_frame=1002)==0


def test_new_flag_is_bound_in_measurement_and_factory(monkeypatch):
    from ssbot.train import forum_measure_manifest as m
    assert m._CHAIN_ROLES["SSBOT_FORUM_CHAIN_FIXED_HOOK"]=="control"
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_FAST_HOOK","0")
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_FIXED_HOOK","garbage")
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_BATCH","fixed-test")
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_ARM","B")
    with pytest.raises(ValueError,match="FIXED_HOOK"):
        NativeChainB2.from_env(journal="fake.jsonl")


def test_registry_is_private_and_wait_can_be_reused_by_jump():
    from ssbot.combat import knife_chain_slam as F
    names=set(F.P.guards);r=load_runner(fixed_hook=True)
    assert set(F.P.guards)==names and r.P is not F.P
    assert "wait" in r.chains["slam_jump"].links


def test_real_jump_bounce_uses_same_cheap_wait_without_changing_jump_admission(params,terrain,monkeypatch):
    from tests.test_knife_chain_b2 import native_committed,next_state
    from ssbot.combat import knife_chain_b2 as m
    from ssbot.combat.knife_chain_eval import ChainPreview
    n=native_committed(params,terrain);run=n.runner.run
    n.runner=load_runner(fixed_hook=True);n.runner.run=run;n._fixed_hook_mode=True
    n.observe(next_state(1001));n.observe(next_state(1002,counter=8,hit="DownSlash"))
    assert n.commitment is None and n.post_context["simple_wait"]
    assert n.runner.run.lid=="slam_jump.wait"
    n._context=((1002,next_state(1002),n._clock,False,True),None,None,None)
    monkeypatch.setattr(n,"_preview",lambda: (ChainPreview(1002,0,n.runner),n.post_context["move"]))
    monkeypatch.setattr(m,"B2Geometry",lambda *a:pytest.fail("heavy post-bounce geometry ran"))
    o=n.propose(None,None,None,None,None,None,None,None)
    assert o.stage=="active" and o.details["simple_wait"] and not o.details["fixed_hook"]


def test_fixed_mode_changes_bound_digest_and_missing_profile_stays_unknown(tmp_path):
    from tests.test_b2_manifest_bindings import package,env,policy,manifest
    root=package(tmp_path);e=env(SSBOT_FORUM_CHAIN_FIXED_HOOK="0");p=policy(e)
    a=manifest(root,p,e);assert a["configuration_complete"]
    e2={**e,"SSBOT_FORUM_CHAIN_FIXED_HOOK":"1"};q=policy(e2);q.chain_native.profile.fixed_hook=True
    b=manifest(root,q,e2);assert b["configuration_complete"] and a["behavior_sha256"]!=b["behavior_sha256"]
    del q.chain_native.profile.fixed_hook
    assert not manifest(root,q,e2)["configuration_complete"]
