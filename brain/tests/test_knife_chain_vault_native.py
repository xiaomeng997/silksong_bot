"""Optional vault family reuses the native transaction and original tables."""
from types import SimpleNamespace as NS
from copy import deepcopy

import numpy as np
import pytest

from ssbot.combat.knife_chain_vault_native import load_runner, _contacts
from ssbot.combat.knife_chain_air import load_runner as load_air, render, AirPlan
from ssbot.combat.knife_chain_vault import CHAIN, load_vault_runner
from ssbot.combat.knife_chain_eval import Run, X
from ssbot.combat.knife_chain_format import table_digest
from ssbot.combat.knife_chain_commitment import MoveInstance, PathContact, ContactScan
from ssbot.combat.knife_chain_air_native import NativeManualAirChain
from ssbot.combat.knife_chain_nominal import NominalProfile, logical_copy


def test_family_loading_preserves_each_original_table_and_air_key_stream():
    r=load_runner();a=load_air();v,_=load_vault_runner()
    assert set(r.chains)==set(a.chains)|{CHAIN} and r.run is None
    assert table_digest({k:r.chains[k] for k in a.chains})==table_digest(a.chains)
    assert table_digest({CHAIN:r.chains[CHAIN]})==table_digest(v.chains)
    p=AirPlan(7,1000,0.,0,1<<21,26,18,27,30,7,1000,1030)
    assert np.array_equal(render(r,p,0,42),render(a,p,0,42))


def test_each_family_keeps_its_own_clock_and_reset_retains_available_tables():
    r=load_runner()
    r.run=Run(CHAIN,"over",{"F_open":1000})
    assert X(r,r.run,NS(F=1012)).clock("antic")==12
    r.run=Run("air_strike","align",{})
    assert X(r,r.run,NS(k=33)).clock("antic")==33
    r.reset();assert r.run is None and CHAIN in r.chains and "rune_transfer" in r.chains


def test_current_draft_is_private_but_does_not_deepcopy_bound_tables():
    r=load_runner();r.run=Run(CHAIN,"over",{"row":{"masks":[1,2]},"bounced":True})
    draft=logical_copy(r);draft.run.v["row"]["masks"][0]=9
    assert r.run.v["row"]["masks"]==[1,2] and draft.chains is r.chains
    assert draft.anchor is not r.anchor


def test_factory_default_does_not_load_vault_and_explicit_flag_binds_its_table(monkeypatch):
    monkeypatch.delenv("SSBOT_FORUM_CHAIN_VAULT",raising=False)
    assert CHAIN not in NativeManualAirChain.load_program(NominalProfile()).chains
    assert len(NativeManualAirChain.program_tables())==1
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_VAULT","1")
    assert CHAIN in NativeManualAirChain.load_program(NominalProfile()).chains
    assert len(NativeManualAirChain.program_tables())==2
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_VAULT","maybe")
    with pytest.raises(ValueError,match="VAULT"):NativeManualAirChain.load_program(NominalProfile())


def test_buffer_cannot_remove_another_owner_delayed_damage_or_post_hit_body():
    move=MoveInstance(7,1000,"VAULT_IDLE")
    original=(PathContact(1007,7,"body"),PathContact(1008,7,"body"),PathContact(1009,7,"move"),
              PathContact(1009,7,"delayed"),PathContact(1009,8,"body"),PathContact(1011,7,"body"))
    geo=NS(move=move,scan=lambda p:NS(complete=True,contacts=original))
    path=NS(contact_frame=1010)
    assert _contacts(geo,path)==[original[i] for i in (0,3,4,5)]
    path.contact_frame=None
    assert _contacts(geo,path)==list(original)


def vault_transaction():
    from ssbot.combat.knife_chain_b2 import B2Offer
    from ssbot.combat.knife_chain_nominal import NominalPath
    from ssbot.combat.knife_chain_format import MASK_NAMES as B
    from ssbot.knowledge import kinematics as K
    native=NativeManualAirChain(runner_factory=load_runner,probe_ref="vault-transaction-fixture")
    draft=logical_copy(native.runner)
    draft.run=Run(CHAIN,"near",{"iid":7,"ta":0.,"bounced":False})
    cmds=np.array([0,B["J"],B["J"]],np.int64)
    flags=np.array([K.F_GROUND,K.F_GROUND,0,0],np.int64)
    path=NominalPath(1000,"approach",cmds,cmds.copy(),np.zeros((K.K,4)),np.zeros((4,4)),
        np.zeros((4,2)),flags,flags.copy(),np.arange(4)/60,None,None,None,0,"handback",1006,1009,
        {"fixture_only":"transaction input, not an admitted physical path"})
    move=MoveInstance(7,990,"VAULT_IDLE")
    native._vault_responsibility[move]=(MoveInstance(8,990,"CC_JUMP_CAST"),-.2)
    offer=B2Offer("commitment",path,draft,B["J"],0.,move,{"manual_air":True,"vault_near":True})
    native.dispatch.begin_tick(1000)
    res=native.install(offer,NS(measurement_enabled=False))
    native.planner_result(res);native.final("plan",offer.mask)
    return native,offer


def test_vault_draft_and_commitment_promote_only_after_successful_send():
    native,offer=vault_transaction()
    assert native.runner.run is None and native.commitment is None
    native.before_send(frame=1000,target=1002,mask=offer.mask,flags=0,received_frame=1000)
    assert native.runner.run is None and native.commitment is None
    sent=native.sent()
    assert sent.chain_outcome=="sent" and native.runner.run.chain==CHAIN
    assert native.commitment["move"]==offer.move and native._jump_start is not None
    assert set(native.runner.chains)=={CHAIN,"air_strike","air_direct","rune_transfer"}
    native.reset(2,start_frame=2000)
    assert native.runner.run is None and "rune_transfer" in native.runner.chains


def test_failed_transport_does_not_promote_vault_or_remove_other_families():
    native,offer=vault_transaction()
    native.before_send(frame=1000,target=1002,mask=offer.mask,flags=0,received_frame=1000)
    native.send_failed(OSError("fixture"))
    assert native.runner.run is None and native.commitment is None
    assert "rune_transfer" in native.runner.chains


def test_vault_ground_jump_cannot_reuse_an_already_observed_first_slot():
    native,offer=vault_transaction()
    assert native.before_send(frame=1000,target=1002,mask=offer.mask,flags=0,received_frame=1002)==0
    assert native.runner.run is None and native.commitment is None
    assert offer.move in native._failed_hook_moves


def test_production_vault_jump_requires_the_existing_receive_clock():
    from ssbot.combat.knife_chain_budget import LearningStop
    native,offer=vault_transaction();native.require_send_clock=True
    with pytest.raises(LearningStop,match="vault first-J receive clock"):
        native.before_send(frame=1000,target=1002,mask=offer.mask,flags=0,received_frame=1000)


def test_failed_sent_vault_tracks_buddys_real_move_end_instead_of_idle_target():
    native,offer=vault_transaction()
    native.before_send(frame=1000,target=1002,mask=offer.mask,flags=0,received_frame=1000)
    native.sent();native._recover("fixture missing bounce",1004)
    exposure,=native._failure_exposures
    assert exposure.move.target_iid==8 and exposure.move.family=="CC_JUMP_CAST"
    def observation(f,st):
        return {"f":f,"ents":[{"iid":7,"hp":100,"fsms":[{"name":"Control","state":"Idle","t":0.}]},
            {"iid":8,"hp":100,"fsms":[{"name":"Control","state":st,"t":.1}]}]}
    exposure.observe(observation(1005,"Air"),game_time=.1)
    exposure.observe(observation(1048,"Slam Recover"),game_time=.8)
    assert exposure.observed_end_frame is None and exposure.active(1048)
    exposure.observe(observation(1050,"Idle"),game_time=.9)
    assert exposure.through==1050 and exposure.active(1050) and not exposure.active(1051)


@pytest.mark.parametrize("direction",[-1,1])
def test_send_and_observed_bounce_keep_the_original_vault_exit(direction,monkeypatch):
    """Model feedback/receipt integration; geometry is deliberately stubbed.

    This is not admission or live action evidence. It catches losing the vault
    run at real-bounce handling, or trying to synthesize another strike edge.
    """
    from tests.test_knife_chain_vault_nominal import scene, GAME0, BUDDY, TARGET
    from ssbot.combat.knife_chain_vault_nominal import compile_near
    from ssbot.combat.knife_chain_nominal import _hero
    from ssbot.combat.holdfilter import hold_filter_jit
    from ssbot.combat.air_chain import ChainSim
    from ssbot.combat.knife_chain_b2 import B2Offer
    from ssbot.combat import knife_chain_vault_native as VN
    from ssbot.knowledge import kinematics as K
    _,raw,sim,request,_=scene(direction)
    n=NativeManualAirChain(runner_factory=load_runner,probe_ref="vault-model-feedback")
    full=compile_near(n.runner,raw,sim,GAME0,request=request,buddy_iid=BUDDY,buddy_lock_until=GAME0+.85)
    move=MoveInstance(TARGET,990,"VAULT_IDLE")
    saved={"move":vars(move),"buddy":BUDDY,"buddy_ta":GAME0-.2,"buddy_lock_until":GAME0+.85}
    full.first_draft.run.v.update(ta=GAME0,_native_vault=saved)
    n._vault_responsibility[move]=(MoveInstance(BUDDY,990,"CC_JUMP_CAST"),GAME0-.2)
    n._receipts[1001]=0
    class SafeGeometry:
        def __init__(self,*args):self.move=move
        def scan(self,path):return NS(complete=True,contacts=())
    monkeypatch.setattr(VN,"B2Geometry",SafeGeometry)
    forecast=NS(rs=NS(trk=NS(now={TARGET:(None,None,None)})))
    prefs=NS(weights={},risk_x=[],risk=[],stance_x=30.,boss_x=None)
    planner=NS(measurement_enabled=False,scene_field_values=None)
    closed=None
    for k in range(len(full.commands)+1):
        f=1000+k;s=deepcopy(raw);s["f"]=f
        _hero(s,full.states[:,k],full.box[k],full.pos[k],full.states[[K.VX,K.VY],k],int(full.flags[k]))
        s["hero"].pop("cstate_int",None)
        if float(full.game[k])>=GAME0+.85:s["ents"][1]["fsms"][0]["state"]="Slam 2"
        s["ev"]=[{"k":"hit","f":f,"d":{"iid":TARGET,"src":"DownSlash" if h["kind"]=="down" else "Slash"}}
                 for h in full.assumptions["contacts"] if h["F"]==f]
        _,hold=hold_filter_jit(full.commands[None,:k],sim.hold) if k else (None,sim.hold.copy())
        def mask(values):return sum(1<<i for i,v in enumerate(values) if v)
        desired=mask(hold.desired[0]);latched=mask(hold.latched[0])
        target=f if f>=1002 else 1000
        s["act"]={"target":target,"applied":target,"mask":latched,"hf":{
            "latched":latched,"desired":desired,"pending":hold.pending[0].tolist(),"age":hold.age[0].tolist()}}
        n.begin(s)
        if k==0:n._clock=GAME0
        queued,_=n.queued_prefix(f,s)
        assert queued==int(full.commands[k] if k<len(full.commands) else full.queued_next)
        follow=ChainSim(full.states[:,k],np.array([queued],np.int64),hold,sim.params,sim.terrain,f,f)
        n.prepare(s,ground=bool(full.flags[k]&K.F_GROUND),accepting=s["hero"]["hero_accepting_input"],sim=follow,bombs=np.zeros((0,6)))
        offer=(B2Offer("commitment",full,full.first_draft,int(full.offered[0]),0.,move,
                      {"manual_air":True,"vault_near":True}) if k==0 else n.propose(planner,None,follow.start,hold,follow.prefix,forecast,prefs,None))
        if offer is None:
            closed=f;break
        assert offer.mask==int(full.commands[k+1] if k+1<len(full.commands) else full.queued_next)
        res=n.install(offer,planner);n.planner_result(res);n.final("plan",offer.mask)
        n.before_send(frame=f,target=f+2,mask=offer.mask,flags=0,received_frame=f)
        assert n.sent().chain_outcome=="sent"
    assert closed is not None and n.runner.run is None and n.commitment is None
    assert any(e["event"]=="vault_real_bounce_exit" for e in n.events)
    assert any(e["event"]=="vault_observed_handoff" for e in n.events)
    assert "rune_transfer" in n.runner.chains


def test_frozen_game_clock_cannot_turn_a_failed_lock_into_a_new_opportunity(monkeypatch):
    from tests.test_knife_chain_vault_nominal import scene,GAME0,BUDDY,TARGET
    from ssbot.combat import knife_chain_vault_native as VN,knife_chain_vault_entry as VE
    _,raw,sim,_,box=scene(-1)
    n=NativeManualAirChain(runner_factory=load_runner,probe_ref="vault-freeze-identity")
    epoch=[3.];expanded=[]
    def context(state,forecast,target,game):
        return {"target":TARGET,"buddy":BUDDY,"buddy_t0":epoch[0],"buddy_ta":GAME0-1.,
                "buddy_lock_until":GAME0+1.,"direction":-1,"box":np.array(box),
                "move":MoveInstance(TARGET,state["f"],"VAULT_IDLE")}
    def proposals(*args,**kw):
        expanded.append(1);return (),{"generated":0}
    monkeypatch.setattr(VN,"locked_context",context);monkeypatch.setattr(VE,"near_proposals",proposals)
    for i in range(3):
        s=deepcopy(raw);s["f"]=1000+i;s["dt"]=0.
        s["act"].update(target=1000,applied=1000,mask=0)
        n._receipts[1001+i]=0;n.begin(s)
        follow=NS(**sim.__dict__);follow.f=follow.fo=s["f"]
        n.prepare(s,ground=True,accepting=True,sim=follow,bombs=np.zeros((0,6)))
        if i==1:n._failed_hook_moves.add(MoveInstance(TARGET,1000,"VAULT_IDLE"))
        if i==2:epoch[0]=4.  # a genuinely different observed tracker instance
        assert n.propose(NS(),None,follow.start,follow.hold,follow.prefix,NS(),NS(target=TARGET),None) is None
    assert len(expanded)==2


def test_unknown_delayed_hazard_rows_do_not_start_the_vault(monkeypatch):
    from tests.test_knife_chain_vault_nominal import scene,TARGET
    from ssbot.combat import knife_chain_vault_native as VN
    _,raw,sim,_,_=scene(-1)
    raw["act"].update(target=1000,applied=1000,mask=0)
    n=NativeManualAirChain(runner_factory=load_runner,probe_ref="vault-unknown-hazards")
    n._receipts[1001]=0;n.begin(raw)
    n.prepare(raw,ground=True,accepting=True,sim=sim,bombs=None)
    monkeypatch.setattr(VN,"locked_context",lambda *a:pytest.fail("unknown bomb rows reached entry expansion"))
    assert n.propose(NS(),None,sim.start,sim.hold,sim.prefix,NS(),NS(target=TARGET),None) is None


@pytest.mark.parametrize("direction",[-1,1])
def test_current_buffer_requires_the_blade_to_still_reach_on_its_active_frame(direction):
    from tests.test_knife_chain_vault_nominal import scene,GAME0,BUDDY,TARGET
    from ssbot.combat.knife_chain_vault_nominal import compile_near
    from ssbot.combat.knife_chain_air import model_path
    from ssbot.combat.knife_chain_vault_native import _current_contact
    from ssbot.knowledge import kinematics as K
    runner,raw,sim,request,box=scene(direction)
    future=compile_near(runner,raw,sim,GAME0,request=request,buddy_iid=BUDDY,buddy_lock_until=GAME0+.85)
    plan=NS(iid=TARGET,move=MoveInstance(TARGET,990,"VAULT_IDLE"),origin=sim.f,entry_k=0,
            press_k=future.press_frame-sim.f,contact_frame=future.contact_frame)
    current=model_path(sim,plan,future.offered[:future.contact_frame-sim.f-1],GAME0)
    assert _current_contact(current,future.contact_frame,np.array(box),future.press_frame)==future.contact_frame
    assert _current_contact(current,future.contact_frame,np.array(box),future.contact_frame-1) is None
    assert _current_contact(current,future.contact_frame,np.array(box)+np.array([10.,0.,10.,0.]),future.press_frame) is None
    current.flags[-1]&=~K.F_ATTACKING
    current.states[K.ATTACKING,-1]=0.
    assert _current_contact(current,future.contact_frame,np.array(box),future.press_frame) is None
