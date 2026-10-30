"""B2 audit fields preserve control rules and actual evidence boundaries."""
from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import pytest
from ssbot.combat.knife_chain_b2 import NativeChainB2,B2Offer
from ssbot.combat.knife_chain_budget import LearningBudget,LearningStop
from ssbot.combat.knife_chain_commitment import MoveInstance
from tests.test_knife_chain_b2 import runner,raw,params,terrain,preview


def new(**kw):
    return NativeChainB2(runner_factory=runner,probe_ref="internal-logs",**kw)


def receipt_state(f,target,desired,applied=None):
    return {"f":f,"act":{"target":target,"applied":target if applied is None else applied,"hf":{"desired":desired}}}


def test_receipt_categories_preserve_pending_resolution_and_acceptance_scope():
    n=new();n._receipts.update({4:1,8:1,10:4});n._pending={4:1}
    n._observe_application(receipt_state(6,4,1,6))
    assert not n._pending and n._receipt_counts=={"lag":1}
    n._pending={7:1};n._observe_application(receipt_state(8,8,1))
    assert n._application[7]["kind"]=="covered_same_key"
    n._pending={9:2};n._observe_application(receipt_state(10,10,4))
    assert n._application[9]["kind"]=="covered_changed_key"
    n._receipts[11]=0;n._pending={11:0};n._observe_application(receipt_state(11,11,0))
    assert n.summary()["receipt_counts"]=={"lag":1,"skip_same_key":1,"skip_key_change":1,"direct":1}
    assert n._accepted is None and n._hit is None and n.post_context is None
    ev=[e for e in n.events if e["event"]=="b2_receipt"]
    assert all("not hero action acceptance" in e["scope"] for e in ev)
    assert ev[0]["lag"]==2 and ev[1]["between"]==[4,8]


def test_timeout_and_mismatch_still_stop_after_logging_exact_category():
    n=new();n._pending={4:1}
    with pytest.raises(LearningStop,match="four-frame"):
        n._observe_application(receipt_state(9,0,0))
    assert n._receipt_counts=={"uncovered_timeout":1}
    assert [e["event"] for e in list(n.events)[-2:]]==["b2_receipt","b2_learning_stop"]
    n=new();n._receipts={4:1};n._pending={4:1}
    with pytest.raises(LearningStop,match="desync"):
        n._observe_application(receipt_state(4,4,2))
    assert n._receipt_counts=={"desired_mismatch":1} and n._pending=={4:1}


def test_missing_context_and_two_clapper_scope_explain_visible_antics(params,terrain):
    n=new();s=raw();n.begin(s)
    assert n._preview() is None
    e=n.events[-1];assert e["event"]=="b2_no_candidate" and e["reason"]=="no current model context"
    assert e["antics"]==[{"iid":7,"fa":None,"observed_state":"Slam Antic","state_time":0.}]
    _,_,s,sim=preview(params,terrain)
    s["ents"].append({**s["ents"][0],"iid":8})
    n._receipts[1001]=0;n.prepare(s,ground=True,accepting=True,sim=sim)
    assert n._preview() is None
    e=n.events[-1];assert e["reason"]=="single live Clapper scope"
    assert [x["iid"] for x in e["antics"]]==[7,8]


def test_proposal_timer_is_bound_to_offer_and_selection_excludes_planner_time(params,terrain,monkeypatch):
    n=new();_,p,s,sim=preview(params,terrain);n.begin(s)
    offer=B2Offer("active",None,p.draft,int(p.mask),0.,MoveInstance(7,1000,"CC_SLAM"),{})
    def propose(*a):
        n._note("b2_unchecked",frame=1000,reason="synthetic event timing only")
        return offer
    monkeypatch.setattr(n,"_propose",propose)
    got=n.propose(*[None]*8)
    assert got is offer and offer.proposal_ms>=0. and n._proposal_started is None
    event=n.events[-1]
    assert event["ms"]>=0. and event["timing_scope"]=="proposal_elapsed_to_event"
    n.install(got,SimpleNamespace(measurement_enabled=False))
    selected=n.events[-1]
    assert selected["event"]=="b2_selected" and selected["ms"]==offer.proposal_ms
    assert "excludes ordinary planner/install/send" in selected["timing_scope"]


def test_proposal_exception_resets_timer_without_suppressing_error(monkeypatch):
    n=new()
    def bad(*a):raise RuntimeError("model defect")
    monkeypatch.setattr(n,"_propose",bad)
    with pytest.raises(RuntimeError,match="model defect"):n.propose(*[None]*8)
    assert n._proposal_started is None


@pytest.mark.parametrize("phase",["approach","commitment","post","recovery","none"])
def test_hp_log_keeps_same_frame_sources_before_budget_can_stop(tmp_path,phase):
    budget=LearningBudget(tmp_path/"ledger.json",batch="logs",revision="r",worker="w")
    n=new(budget=budget);n.reset(0,start_frame=1000);n.observe_learning(raw(1000))
    if phase=="approach":n.runner.run=SimpleNamespace()
    elif phase=="commitment":n.commitment={"test":True}
    elif phase=="post":n.post_context={"test":True}
    elif phase=="recovery":n.recovery={"test":True}
    s=raw(1001);s["hero"]["health"]=5
    s["ev"]=[
        {"f":1000,"k":"damage","d":{"source":"older","can_take":True}},
        {"f":1001,"k":"damage","d":{"source":"blocked","can_take":False}},
        {"f":1001,"k":"damage","d":{"source":"protected","invuln":True}},
        {"f":1001,"k":"hit","d":{"source":"not damage"}},
        {"f":1001,"k":"damage","d":{"source":"Slam Collider 1","can_take":True,"invuln":False}}]
    with pytest.raises(LearningStop):n.observe_learning(s)
    es=list(n.events);hp=next(e for e in es if e["event"]=="b2_hp_loss")
    assert hp["sources"]==["Slam Collider 1"] and hp["phase"]==phase
    assert es.index(hp)<next(i for i,e in enumerate(es) if e["event"]=="b2_learning_stop")
    assert budget.state["stop"] is not None


def test_hp_without_same_frame_damage_does_not_guess_source():
    n=new();n.observe_learning(raw(1000));s=raw(1001);s["hero"]["health"]=6
    s["ev"]=[{"f":1000,"k":"damage","d":{"source":"older"}}]
    n.observe_learning(s)
    assert n.events[-1]["sources"]==["unknown"]
