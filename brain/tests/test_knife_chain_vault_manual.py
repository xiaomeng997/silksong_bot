"""Fixed action supply and shared hook input watches, not live safety evidence."""
from types import SimpleNamespace as NS
from dataclasses import replace
import numpy as np
import pytest

from ssbot.combat.knife_chain_vault_native import load_runner,manual_entries
from ssbot.combat.knife_chain_air_native import NativeManualAirChain
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.combat import knife_chain_air as AIR,knife_chain_vault_entry as VE
from ssbot.knowledge import kinematics as K


def entry_scene(direction,distance):
    from tests.test_knife_chain_vault_nominal import scene,TARGET,BUDDY
    _,raw,sim,_,_=scene(direction)
    target=raw["ents"][0];new=raw["hero"]["pos"][0]+direction*distance
    dx=new-target["pos"][0];target["pos"][0]=new
    for c in target["colliders"]:c["verts_world"][::2]=[v+dx for v in c["verts_world"][::2]]
    box=AIR.body_box(target)
    n=NativeManualAirChain(runner_factory=load_runner,probe_ref="manual-vault-supply")
    ctx={"target":TARGET,"buddy":BUDDY,"direction":direction,"box":box}
    return n,raw,sim,ctx


@pytest.mark.parametrize("direction",[-1,1])
@pytest.mark.parametrize("distance,press",[(3.4,4),(4.2,8)])
def test_close_walker_has_one_fixed_near_row_not_the_grid(direction,distance,press,monkeypatch):
    n,raw,sim,ctx=entry_scene(direction,distance)
    def checked(*a,**kw):pytest.fail("manual entry expanded a timing search")
    monkeypatch.setattr(VE,"near_proposals",checked)
    entries=manual_entries(n,raw,sim,ctx)
    assert len(entries)==1
    kind,req=entries[0]
    assert kind=="near" and req["near"]=={"h":14,"p":press,"before":"T"} and req["far"] is None


@pytest.mark.parametrize("direction",[-1,1])
def test_far_walker_supplies_small_hop_hook_without_near_expansion(direction,monkeypatch):
    n,raw,sim,ctx=entry_scene(direction,7.)
    monkeypatch.setattr(VE,"near_proposals",lambda *a,**kw:pytest.fail("far hook expanded the near grid"))
    (kind,req),=manual_entries(n,raw,sim,ctx)
    assert kind=="hop_hook" and req["near"] is None
    r=n.runner;r.anchor.open(req)
    r.step(sim.f,raw,True,True,t_game=10.,sim=sim,bombs=np.zeros((0,6)))
    cs=r.run.v["cs"]
    assert cs.hop==3 and cs.f_press-cs.f0==3
    from ssbot.combat.claw_strike import plan_mask
    assert plan_mask(cs,cs.f0,direction)&B["J"]
    assert not plan_mask(cs,cs.f0,direction)&B["CLAW"]
    assert plan_mask(cs,cs.f_press,direction)&B["CLAW"]


@pytest.mark.parametrize("change",["unavailable","no_silk","too_far","past_approach"])
def test_hook_without_its_observed_requirements_is_not_offered(change):
    n,raw,sim,ctx=entry_scene(-1,{"too_far":12.,"past_approach":14.5}.get(change,7.))
    if change=="unavailable":raw["hero"]["can"]["harpoon"]=False
    if change=="no_silk":raw["hero"]["silk"]=0
    # Task 179: past the hook's range but inside APPROACH's bound only the ground approach is offered (no hook)
    assert [kind for kind,_ in manual_entries(n,raw,sim,ctx)]==(["approach"] if change=="too_far" else [])


def _switch_routing_scene(case,monkeypatch):
    from ssbot.combat import knife_chain_vault_native as VN
    from ssbot.combat.knife_chain_transfer import TransferGoal
    from ssbot.combat.knife_chain_commitment import MoveInstance
    from ssbot.combat.tactics.modes import EntryAttack,GoalPrefs
    from tests.test_knife_chain_vault_nominal import GAME0,BUDDY,TARGET
    direction=-1 if case=="left" else 1
    # Task 179: 12 u is now a ground-approach vault; past APPROACH's 14 u bound the vault is known empty
    n,raw,sim,ctx=entry_scene(direction,15.)
    n.reset(0,start_frame=sim.f)
    raw["act"].update(target=sim.f,applied=sim.f,mask=0)
    n._receipts[sim.f+1]=int(sim.prefix[0]);n.begin(raw)
    n.prepare(raw,ground=True,accepting=True,sim=sim,bombs=np.zeros((0,6)))
    ctx.update(buddy_t0=3.,buddy_ta=GAME0-.2,buddy_lock_until=GAME0+.6)
    monkeypatch.setattr(VN,"locked_context",lambda *a:ctx)
    # These are the ready/bound fields captured at the real 2609 failure.
    # This unit checks routing only; the full _act probe checks their creation.
    n._transfer_ready=case!="not_ready"
    n._transfer_goal=TransferGoal(TARGET,BUDDY,sim.f,GAME0-.2,
        "CAST" if case=="other_source" else "SWITCH",MoveInstance(BUDDY,sim.f-12,"CC_JUMP_CAST"))
    entry=EntryAttack(TARGET+1 if case=="other_target" else TARGET,
                      "side" if case=="side" else "stomp",BUDDY,"CC_JUMP_CAST",9.,GAME0)
    prefs=GoalPrefs(mode="RUSH",stance_x=40.,weights={},target=TARGET,entry_attack=entry)
    if case=="policy_gate":n.policy_gate_reason="critical owner"
    delegated=[];marker=object()
    monkeypatch.setattr(n,"_transfer_offer",lambda *args:delegated.append(args) or marker)
    return n,raw,sim,prefs,delegated,marker


@pytest.mark.parametrize("case", ["left", "right", "policy_gate", "side", "not_ready", "other_source", "other_target"])
def test_known_empty_vault_does_not_mask_a_matching_explicit_switch_stomp(case,monkeypatch):
    n,raw,sim,prefs,delegated,marker=_switch_routing_scene(case,monkeypatch)
    out=n._propose(NS(),None,sim.start,sim.hold,sim.prefix,NS(),prefs,None)
    expected=case in {"left","right","side"}  # existing side approach already routes before vault
    assert (out is marker)==expected and bool(delegated)==expected
    assert n.runner.run is None and n.commitment is None  # no send or fake execution


@pytest.mark.parametrize("kind", ["side","stomp"])
@pytest.mark.parametrize("phase", ["over","fall","ground"])
def test_active_vault_tail_keeps_keys_after_bounce_released_commitment(kind,phase,monkeypatch):
    from ssbot.combat import knife_chain_vault_native as VN
    from ssbot.combat.knife_chain_eval import Run
    n,raw,sim,prefs,delegated,marker=_switch_routing_scene("right",monkeypatch)
    prefs.entry_attack=replace(prefs.entry_attack,kind=kind)
    active=Run("vault_idle",phase,{"iid":prefs.target,"ta":9.7,"bounced":True,"over_dir":1})
    n.runner.run=active
    assert n.commitment is None and n.post_context is None
    vault_marker=object();monkeypatch.setattr(VN,"propose",lambda *args:vault_marker)
    out=n._propose(NS(),None,sim.start,sim.hold,sim.prefix,NS(),prefs,None)
    assert out is vault_marker and not delegated
    assert n.runner.run is active  # route only: no new Run, send, hit or handoff invented


def hook_transaction():
    from tests.test_knife_chain_vault_native import vault_transaction
    n,o=vault_transaction()
    commands=np.array([0,B["J"],B["J"],B["J"],B["CLAW"],B["CLAW"],0],np.int64)
    flags=np.array([K.F_GROUND,K.F_GROUND,0,0,0,0,0,0],np.int64)
    path=replace(o.path,commands=commands,latched=commands.copy(),flags=flags)
    o=replace(o,path=path,details={"manual_air":True,"vault_hook":True,"entry_kind":"hop_hook"})
    n._b2_selected=o
    return n,o


def test_small_hop_hook_uses_the_existing_watch_after_successful_jump_send():
    n,o=hook_transaction()
    n.before_send(frame=1000,target=1002,mask=B["J"],flags=0,received_frame=1000)
    assert n.sent().chain_outcome=="sent"
    assert n._hook_start["targets"]==(1005,1006)
    assert n._jump_start.sent_targets=={1002}
    assert n._hit is None and n._accepted is None


def test_no_observed_takeoff_cannot_dispatch_the_vault_hook():
    n,o=hook_transaction()
    n.before_send(frame=1000,target=1002,mask=B["J"],flags=0,received_frame=1000);n.sent()
    n.dispatch.begin_tick(1003);n.final("plan",B["CLAW"])
    n._b2_selected=replace(o,stage="active",mask=B["CLAW"])
    result=n.before_send(frame=1003,target=1005,mask=B["CLAW"],flags=0,received_frame=1003)
    assert result==0
    assert any(e.get("reason")=="pre-hook ground jump not observed before CLAW dispatch" for e in n.events)
    assert o.move in n._failed_hook_moves


@pytest.mark.parametrize("clip",["Harpoon Dash","Airborne"])
def test_observed_hook_lock_keeps_neutral_under_the_same_owner(clip,monkeypatch):
    from ssbot.combat import knife_chain_vault_native as VN
    from tests.test_knife_chain_vault_nominal import GAME0,BUDDY,TARGET
    n,raw,sim,ctx=entry_scene(-1,7.)
    (kind,req),=manual_entries(n,raw,sim,ctx)
    n.runner.anchor.open(req)
    n.runner.step(sim.f,raw,True,True,t_game=GAME0,sim=sim,bombs=np.zeros((0,6)))
    move=VN.MoveInstance(TARGET,1000,"VAULT_IDLE")
    n.runner.run.link="far_lock"
    n.runner.run.v["_native_vault"]={"move":vars(move),"buddy":BUDDY,"buddy_t0":3.,"buddy_ta":GAME0-.2,"entry_kind":"hop_hook"}
    n.commitment={"move":move,"predicted_bounce":1050}
    n._hook_start={"move":move,"sent_targets":{1005},"seen_frame":1007}
    raw["f"]=1008;raw["hero"]["hero_accepting_input"]=False;raw["hero"]["anim"]["clip"]=clip
    n._receipts[1009]=0
    sim.f=sim.fo=1008
    n._context=((1008,raw,GAME0+.13,False,False),sim,None,np.zeros((0,6)))
    monkeypatch.setattr(VN,"B2Geometry",lambda *a:pytest.fail("uncancellable lock invented a fresh free-flight proof"))
    offer=VN.propose(n,NS(),NS(rs=NS(trk=NS(now={}))),NS())
    assert offer.stage=="active" and offer.mask==0 and offer.path is None
    assert offer.draft.run.chain=="vault_idle" and offer.draft.run.link=="far_lock"
    assert not offer.draft.run.v["bounced"] and n._hit is None


def test_manual_family_warms_fixed_near_and_existing_hook_control_models():
    from ssbot.combat.knife_chain_vault_native import warm
    from tests.test_knife_chain_vault_nominal import P
    result=warm(P)
    assert result["proposal_rows_warmed"]==1 and result["hook_control_warmed"] is True


@pytest.mark.parametrize("distance",[3.4,7.])
def test_runtime_entries_only_query_the_current_external_step(distance,monkeypatch):
    from ssbot.combat import knife_chain_vault_native as VN,knife_chain_vault_nominal as NM
    from tests.test_knife_chain_vault_nominal import GAME0,TARGET,BUDDY
    n,raw,sim,ctx=entry_scene(-1,distance)
    ctx.update(buddy_t0=3.,buddy_ta=GAME0-.2,buddy_lock_until=GAME0+.8)
    n._receipts[1001]=0
    n._context=((1000,raw,GAME0,True,True),sim,None,np.zeros((0,6)))
    monkeypatch.setattr(VN,"locked_context",lambda *a:ctx)
    def forbidden(*a,**kw):pytest.fail("manual action performed whole-skill/search/N2 prediction")
    monkeypatch.setattr(VE,"near_proposals",forbidden)
    monkeypatch.setattr(NM,"compile_near",forbidden)
    monkeypatch.setattr(n,"_continuations",forbidden)
    checked=[]
    class CurrentOnly:
        def __init__(self,*a):pass
        def preflight(self,path):
            checked.append(path)
            assert len(path.commands)==2 and path.contact_frame is None
            return NS(complete=True,contacts=())
    monkeypatch.setattr(VN,"B2Geometry",CurrentOnly)
    offer=VN.propose(n,NS(),NS(rs=NS(trk=NS(now={TARGET:(None,None,None)}))),NS(target=TARGET))
    assert len(checked)==1 and offer.stage=="manual_commitment" and offer.path is None
    assert offer.mask&B["J"] and not offer.draft.run.v["bounced"]
    assert offer.details["predicted_bounce"] is None
    assert n.runner.run is None and n.commitment is None
    n.dispatch.begin_tick(1000)
    result=n.install(offer,NS(measurement_enabled=False));n.planner_result(result);n.final("plan",offer.mask)
    n.before_send(frame=1000,target=1002,mask=offer.mask,flags=0,received_frame=1000)
    assert n.commitment is None
    assert n.sent().chain_outcome=="sent" and n.commitment["move"]==offer.move
    assert n._jump_start.sent_targets=={1002}
    if distance==7.:assert n._hook_start["targets"]==(1005,1006)


def missed_near(*,hit=False,marker=False,late_window=False):
    from tests.test_knife_chain_vault_nominal import GAME0
    n,raw,sim,ctx=entry_scene(-1,3.4)
    (_,req),=manual_entries(n,raw,sim,ctx)
    n.runner.anchor.open(req)
    n.runner.step(1000,raw,True,True,t_game=GAME0,sim=sim,bombs=np.zeros((0,6)))
    row=n.runner.run.v["row"];press=row["press_F"]
    raw["f"]=press+(11 if late_window else 13)
    raw["hero"]["box"][1:4:2]=[4.,6.079]
    raw["hero"]["vel"][1]=-2.
    raw["hero"]["cstate_int"][1]=8 if marker else 0
    if hit:raw["ev"]=[{"k":"hit","f":press+3,"d":{"iid":ctx["target"],"src":"DownSlash"}}]
    # The same observed target steps back while Hornet is airborne.
    e=raw["ents"][0];e["fsms"][0]["state"]="Walk"
    e["pos"][0]-=1.
    for c in e["colliders"]:c["verts_world"][::2]=[x-1. for x in c["verts_world"][::2]]
    m=n.runner.step(raw["f"],raw,False,True,t_game=GAME0+.4,sim=sim,bombs=np.zeros((0,6)))
    return n,raw,ctx,press,m


def test_retreating_idle_target_miss_branches_once_without_a_second_jump():
    n,raw,ctx,press,mask=missed_near()
    run=n.runner.run
    assert run.link=="far" and run.v["fallback_hook"] and run.v["near_miss_press"]==press
    assert run.v["cs"].hop==0 and not mask&B["J"]
    assert run.v["down_hit_f"] is None and not run.v["bounced"]
    assert run.v["iid"]==ctx["target"] and run.v["F_open"]==1002
    # This leg cannot loop into another hook if its own slash later misses.
    assert "vault_miss_hook_plan" not in str(n.runner.chains["vault_idle"].links["far_strike"])


def test_late_allowed_hit_window_is_not_already_a_miss():
    n,raw,ctx,press,mask=missed_near(late_window=True)
    assert n.runner.run.link=="near" and not n.runner.run.v["fallback_hook"]


def test_target_hit_without_real_bounce_is_not_success_or_a_new_hook():
    n,raw,ctx,press,mask=missed_near(hit=True)
    assert mask is None and n.runner.run is None
    assert n.runner.done[-1].closed=="abort" and not n.runner.done[-1].v["bounced"]
    assert not n.runner.done[-1].v["fallback_hook"]


def test_real_target_hit_and_bounce_uses_exit_instead_of_miss_hook():
    n,raw,ctx,press,mask=missed_near(hit=True,marker=True)
    assert n.runner.run.link=="over" and n.runner.run.v["bounced"]
    assert not n.runner.run.v["fallback_hook"]


@pytest.mark.parametrize("transport_ok",[False,True])
def test_miss_exposure_is_retained_only_after_the_branch_was_sent(transport_ok):
    from ssbot.combat.knife_chain_b2 import B2Offer
    from ssbot.combat.knife_chain_commitment import MoveInstance
    from tests.test_knife_chain_vault_nominal import GAME0
    n,raw,ctx,press,mask=missed_near()
    move=MoveInstance(ctx["target"],1000,"VAULT_IDLE")
    n._vault_responsibility[move]=(MoveInstance(ctx["buddy"],1000,"CC_JUMP_CAST"),GAME0-.2)
    n.commitment={"move":move,"origin":1000,"ta":GAME0,"predicted_bounce":None}
    n._press=press;n._accepted=press;n._actual_state=raw;n._clock=GAME0+.4
    draft=n.runner;n.runner=load_runner()
    offer=B2Offer("active",None,draft,mask,0.,move,{"distance_vault":True,"manual_air":True,"vault_hook":True})
    f=raw["f"];n.dispatch.begin_tick(f)
    result=n.install(offer,NS(measurement_enabled=False));n.planner_result(result);n.final("plan",mask)
    n.before_send(frame=f,target=f+2,mask=mask,flags=0,received_frame=f)
    if not transport_ok:
        n.send_failed(OSError("fixture failed before send"))
        assert n._press==press and n._failure_exposures==[]
        return
    assert n.sent().chain_outcome=="sent"
    assert n.runner.run.v["near_miss_recorded"] and n._press is None and n._hit is None
    exposure,=n._failure_exposures
    assert exposure.move.target_iid==ctx["buddy"] and exposure.active(f+29)
    assert n.commitment["move"]==move and n.commitment["origin"]==1000
    assert n._hook_start["targets"]==(f+3,f+4)


def test_declined_first_step_can_retry_when_cooldown_clears(monkeypatch):
    from ssbot.combat import knife_chain_vault_native as VN
    from ssbot.combat.air_chain import ChainSim
    from tests.test_knife_chain_vault_nominal import GAME0,TARGET
    n,raw,sim,ctx=entry_scene(-1,3.4)
    ctx.update(buddy_t0=3.,buddy_ta=GAME0-.2,buddy_lock_until=GAME0+.8)
    monkeypatch.setattr(VN,"locked_context",lambda *a:ctx)
    monkeypatch.setattr(VN,"B2Geometry",lambda *a:NS(preflight=lambda p:NS(complete=True,contacts=())))
    original=n.runner;forecast=NS(rs=NS(trk=NS(now={TARGET:(None,None,None)})))
    for f,cd in [(1000,None),(1001,0.)]:
        raw["f"]=f;raw["hero"]["tm"]["atk_cd"]=cd;n._receipts[f+1]=0
        follow=ChainSim(sim.start,sim.prefix,sim.hold,sim.params,sim.terrain,f,f)
        n._context=((f,raw,GAME0,True,True),follow,None,np.zeros((0,6)))
        offer=VN.propose(n,NS(),forecast,NS(target=TARGET))
        if cd is None:
            assert offer is None and not n._vault_completed and n.runner is original
            assert not any(e['event']=='vault_observed_handoff' for e in n.events)
        else:assert offer is not None and offer.move.antic_frame==1000


@pytest.mark.parametrize('cd,press',[(.21666833758354187,13),(.2000003457069397,12),(.3,17)])
def test_near_jump_starts_now_and_waits_for_current_attack_cooldown(cd,press,monkeypatch):
    from tests.test_knife_chain_vault_nominal import GAME0
    n,raw,sim,ctx=entry_scene(-1,4.2)
    raw['hero']['tm']['atk_cd']=cd
    monkeypatch.setattr(VE,'near_proposals',lambda *a,**kw:pytest.fail('cooldown introduced timing search'))
    (_,req),=manual_entries(n,raw,sim,ctx)
    assert req['near']=={'h':14,'p':press,'before':'T'}
    n.runner.anchor.open(req)
    mask=n.runner.step(1000,raw,True,True,t_game=GAME0,sim=sim,bombs=np.zeros((0,6)))
    assert mask==B['L']|B['J'] and n.runner.run.link=='near'
    row=n.runner.run.v['row']
    assert row['press_F']==1002+press
    assert not any(m&B['A'] for m in row['masks'][:press])
    assert all(m&B['L'] for m in row['masks'][:press+1])
    assert row['masks'][press]&(B['D']|B['A'])==B['D']|B['A']


def test_pending_hook_preserves_the_second_planned_claw(monkeypatch):
    from ssbot.combat import knife_chain_vault_native as VN
    from ssbot.combat.air_chain import ChainSim
    from tests.test_knife_chain_vault_nominal import GAME0,TARGET,BUDDY
    n,raw,sim,ctx=entry_scene(-1,7.)
    (_,req),=manual_entries(n,raw,sim,ctx);n.runner.anchor.open(req)
    n.runner.step(1000,raw,True,True,t_game=GAME0,sim=sim,bombs=np.zeros((0,6)))
    cs=n.runner.run.v['cs'];move=VN.MoveInstance(TARGET,1000,'VAULT_IDLE')
    n.runner.run.v['_native_vault']={'move':vars(move),'buddy':BUDDY,'buddy_t0':3.,'buddy_ta':GAME0-.2}
    n.commitment={'move':move,'origin':1000,'ta':GAME0,'predicted_bounce':None}
    n._hook_start={'move':move,'origin':1000,'targets':(cs.f_press,cs.f_press+1),
                   'sent_targets':{cs.f_press},'seen_frame':None}
    f=cs.f_press-1;raw['f']=f;raw['hero']['anim']['clip']='Airborne'
    n._receipts[f+1]=B['CLAW']
    follow=ChainSim(sim.start,np.array([B['CLAW']],np.int64),sim.hold,sim.params,sim.terrain,f,f)
    n._context=((f,raw,GAME0+.05,False,True),follow,None,np.zeros((0,6)))
    monkeypatch.setattr(VN,'B2Geometry',lambda *a:pytest.fail('pending hook invented a free-flight proof'))
    offer=VN.propose(n,NS(),NS(),NS())
    assert offer is not None and offer.mask&B['CLAW']


def test_missed_near_does_not_hook_away_from_a_target_behind():
    from tests.test_knife_chain_vault_nominal import GAME0
    n,raw,sim,ctx=entry_scene(-1,3.4)
    (_,req),=manual_entries(n,raw,sim,ctx);n.runner.anchor.open(req)
    n.runner.step(1000,raw,True,True,t_game=GAME0,sim=sim,bombs=np.zeros((0,6)))
    press=n.runner.run.v['row']['press_F'];raw['f']=press+13
    far=min(raw['ents'][0]['colliders'][0]['verts_world'][::2])
    raw['hero']['pos'][0]=far-2.;raw['hero']['box']=[far-2.25,4.,far-1.75,6.079]
    raw['hero']['vel'][1]=-2.
    mask=n.runner.step(raw['f'],raw,False,True,t_game=GAME0+.4,sim=sim,bombs=np.zeros((0,6)))
    assert mask is None and n.runner.run is None and not n.runner.done[-1].v['fallback_hook']
