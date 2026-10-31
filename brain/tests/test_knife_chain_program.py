"""Model-only selected strike program never replaces actual per-tick checks."""
from types import SimpleNamespace
from copy import deepcopy
import pytest
from ssbot.combat.knife_chain_eval import ChainRunner,store
from ssbot.combat.knife_chain_program import selected_claw_projection
from ssbot.combat.air_chain import Plan
from ssbot.combat.knife_chain_b2 import NativeChainB2,B2Offer
from ssbot.combat.knife_chain_native import NativeChainAuditError
from ssbot.combat.knife_chain_nominal import logical_copy
from ssbot.combat.knife_chain_commitment import MoveInstance
from tests.test_knife_chain_b2 import runner


def fixture(check=True,search=True):
    calls=[];p=Plan(20,0,20,None,None,47,47,7,c_strike=50)
    def ck(x,store,plan):
        calls.append(("check",x.obs.f));globals()["store"](x,store,check)
    def find(x,store):
        calls.append(("search",x.obs.f));globals()["store"](x,store,deepcopy(p) if search else None)
    r=ChainRunner.__new__(ChainRunner);r.P=SimpleNamespace(acts={"strike_check":ck,"strike_search":find});r.anchor=SimpleNamespace()
    r.run=SimpleNamespace(v={"iid":7,"fa":0,"ta":0.,"face":-1})
    x=SimpleNamespace(v=r.run.v,tmp={},obs=SimpleNamespace(f=30),R=r)
    x.v["plan"]=p
    return r,x,p,calls


CHECK={"a":"strike_check","store":"var.tmp.ok","plan":"var.plan"}
SEARCH={"a":"strike_search","store":"var.tmp.best"}


def test_private_model_holds_plan_validated_by_original_control_search():
    r,x,p,calls=fixture();table=r.P;selected_claw_projection(r)
    r._act(x,SEARCH);x.v["plan"]=x.tmp["best"]
    x.obs.f=31;r._act(x,CHECK);x.obs.f=32;r._act(x,CHECK)
    assert calls==[("search",30)] and x.tmp["ok"] is True
    assert r._selected_strike_info["control_searches"]==1
    assert r._selected_strike_info["model_rechecks_omitted"]==2
    assert r.P is table and r._nominal_projection_only


def test_unvalidated_or_changed_model_plan_still_calls_original_check():
    r,x,p,calls=fixture(check=False);selected_claw_projection(r)
    r._act(x,CHECK);r._act(x,CHECK)
    assert x.tmp["ok"] is False and len(calls)==2
    r._act(x,SEARCH);x.v["plan"]=x.tmp["best"];x.v["plan"].dirk=1
    r._act(x,CHECK)
    assert calls[-1]==("check",30) and not x.tmp["ok"]
    x.v["iid"]=8;r._act(x,CHECK)
    assert calls[-1]==("check",30)


def test_runtime_runner_checks_are_not_omitted_or_global_registry_modified():
    real,x,p,calls=fixture();before=dict(real.P.acts)
    model=ChainRunner.__new__(ChainRunner);model.__dict__.update(real.__dict__);selected_claw_projection(model)
    model._act(x,SEARCH);model._act(x,CHECK)
    assert type(real) is ChainRunner and not hasattr(real,"_nominal_projection_only")
    real._act(x,CHECK);real._act(x,CHECK)
    assert calls==[("search",30),("check",30),("check",30)]
    assert real.P.acts==before


def test_model_draft_cannot_own_live_input_even_if_an_offer_is_constructed():
    n=NativeChainB2(runner_factory=runner,probe_ref="model-isolation")
    model=selected_claw_projection(logical_copy(n.runner))
    offer=B2Offer("commitment",None,model,0,10.,MoveInstance(7,1000,"CC_SLAM"),{})
    with pytest.raises(NativeChainAuditError,match="model-only"):
        n.install(offer,SimpleNamespace(measurement_enabled=False))
    assert n.runner.run is None and n._b2_selected is None
