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


HOOK={"a":"claw_plan","store":"var.tmp.hook","ground":False,"accepting":True,"p_only":23}


def hook_fixture():
    from ssbot.combat.claw_strike import CsPlan,CsCfg
    r,x,_,calls=fixture();x.run=r.run
    p=CsPlan(20,3,23,3,4,[1,1,1,1],1.,(45,46,45,46),[["witness"] for _ in range(4)])
    r.run.v["cs"]=p;r.run.v["cs_toward"]=1;r.anchor.csx=SimpleNamespace(cfg=CsCfg())
    def plan(x,store,**kwargs):
        calls.append(("claw_plan",x.obs.f));globals()["store"](x,store,None)
    r.P.acts["claw_plan"]=plan
    return r,x,p,calls


def test_private_model_holds_current_all_control_hook_program_only():
    r,x,p,calls=hook_fixture();selected_claw_projection(r)
    r._act(x,HOOK)
    assert not calls and x.tmp["hook"]==p and x.tmp["hook"] is not p
    assert x.tmp["hook"].var_ok is not p.var_ok
    assert r._selected_strike_info["model_hook_rechecks_omitted"]==1
    x.tmp["hook"].var_ok[0]=9
    assert p.var_ok==[1,1,1,1]


@pytest.mark.parametrize("change",["press","target","direction","witness","count","fallback"])
def test_changed_hook_program_or_unfixed_search_keeps_original_check(change):
    r,x,p,calls=hook_fixture();selected_claw_projection(r);action=dict(HOOK)
    if change=="press":p.f_press+=1
    elif change=="target":x.v["iid"]=8
    elif change=="direction":x.v["cs_toward"]=-1
    elif change=="witness":p.strike[0][0]="changed"
    elif change=="count":p.var_ok[0]=2
    elif change=="fallback":action["p_only"]=None
    r._act(x,action)
    assert calls==[("claw_plan",30)] and x.tmp["hook"] is None
    assert r._selected_strike_info["model_hook_rechecks_omitted"]==0


@pytest.mark.parametrize("bad",["zero","missing_control","missing_witness","wrong_sum"])
def test_hook_without_complete_current_witness_cannot_skip_model_check(bad):
    r,x,p,calls=hook_fixture()
    if bad=="zero":p.var_ok[0]=0;p.n_ok=3
    elif bad=="missing_control":p.var_ok.pop();p.n_ok=3
    elif bad=="missing_witness":p.strike[0]=None
    else:p.n_ok=3
    selected_claw_projection(r);r._act(x,HOOK)
    assert calls==[("claw_plan",30)] and x.tmp["hook"] is None


def test_live_hook_recheck_is_never_replaced_by_model_program():
    real,x,p,calls=hook_fixture()
    model=ChainRunner.__new__(ChainRunner);model.__dict__.update(real.__dict__)
    selected_claw_projection(model);model._act(x,HOOK)
    real._act(x,HOOK);real._act(x,HOOK)
    assert calls==[("claw_plan",30),("claw_plan",30)]
    assert type(real) is ChainRunner and not hasattr(real,"_nominal_projection_only")


@pytest.mark.parametrize("bad",["witness","context","cfg"])
def test_unknown_initial_hook_metadata_uses_original_search(bad):
    r,x,p,calls=hook_fixture()
    if bad=="witness":p.strike[0][0]=object()
    elif bad=="context":x.v["fa"]=object()
    else:r.anchor.csx.cfg=SimpleNamespace(gaps=object(),ctrl=(25,27))
    selected_claw_projection(r);r._act(x,HOOK)
    assert calls==[("claw_plan",30)] and x.tmp["hook"] is None
    assert r._selected_hook is None


@pytest.mark.parametrize("bad",["witness","context","missing_context"])
def test_unknown_later_hook_metadata_cannot_match_a_known_program(bad):
    r,x,p,calls=hook_fixture();selected_claw_projection(r)
    if bad=="witness":p.strike[0][0]=object()
    elif bad=="context":x.v["fa"]=object()
    else:x.v.pop("cs_toward")
    r._act(x,HOOK)
    assert calls==[("claw_plan",30)] and x.tmp["hook"] is None
    assert r._selected_strike_info["model_hook_rechecks_omitted"]==0


def test_held_hook_equals_fresh_recheck_after_original_plan_adopt():
    from ssbot.combat.knife_chain_slam import pl_adopt
    r,x,committed,_=hook_fixture();selected_claw_projection(r);r._act(x,HOOK)
    held=x.tmp["hook"]
    rechecked=deepcopy(committed);rechecked.f0=30;rechecked.hop=0
    pl_adopt(x,"var.tmp.adopted",rechecked,committed)
    assert x.tmp["adopted"]==held and rechecked is not held
    assert rechecked.f0==committed.f0 and rechecked.hop==committed.hop
