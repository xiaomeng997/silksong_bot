"""B2 proves takeoff before C=J+3; the complete candidate is searched again."""
from types import SimpleNamespace as NS
import numpy as np
import pytest
from ssbot.combat import claw_strike as cs,knife_chain_slam as ks
from ssbot.combat.knife_chain_jump import B2_HOOK_JUMP_LEAD


def search(monkeypatch):
    cfg=cs.CsCfg(hops=(3,))
    owner=cs.ClawStrike(cfg)
    def roll(cmd):
        n,T=cmd.shape
        box=np.zeros((n,T+3,4));box[:]=[34.77,4.0,35.23,6.2]
        return NS(box=box,vel=np.zeros((n,T+3,2)),flags=np.zeros((n,T+3),np.int64))
    sim=NS(f=1000,fo=1000,off=2,roll=roll)
    ctx=cs.CsCtx(s_iid=7,s_x=42.,s_y=7.45,s_face=-1,kb0=0,hero_x=35.,face=1)
    monkeypatch.setattr(owner,"_ctrl_sim",lambda *a:None)
    monkeypatch.setattr(owner,"eval_strike",lambda *a,**kw:[NS(row=lambda:["validated sample"]) for _ in range(4)])
    return owner,sim,ctx


def test_absolute_floor_changes_search_domain_before_ray_and_control_tests(monkeypatch):
    owner,sim,ctx=search(monkeypatch)
    legacy=owner.plan(sim,ctx,True,True)
    delayed=owner.plan(sim,ctx,True,True,p_min=1005)
    assert legacy.f0==delayed.f0==1002
    assert legacy.hop==delayed.hop==3
    assert legacy.f_press==1004 and delayed.f_press==1005
    assert len(delayed.var_ok)==4 and delayed.n_ok==16
    assert all(n==4 for n in delayed.var_ok)


def test_fixed_press_below_floor_is_rejected_not_silently_shifted(monkeypatch):
    owner,sim,ctx=search(monkeypatch)
    assert owner.plan(sim,ctx,True,True,p_only=1004,p_min=1005) is None
    assert owner.plan(sim,ctx,True,True,p_only=1005,p_min=1005).f_press==1005


@pytest.mark.parametrize("p_min",[True,1.5,-1,"1005"])
def test_invalid_floor_is_not_an_admission_bypass(monkeypatch,p_min):
    owner,sim,ctx=search(monkeypatch)
    with pytest.raises(ValueError,match="absolute first-Clawline floor"):
        owner.plan(sim,ctx,True,True,p_min=p_min)


def adapter(monkeypatch,*,strict=True,ground=True,accepting=True,prior=None,f=1000,p_only=None):
    calls=[]
    class FakeCs:
        params=object()
        def plan(self,sim,ctx,g,a,**kw):calls.append(kw);return None
    monkeypatch.setattr(ks,"_csx",lambda x:FakeCs())
    monkeypatch.setattr(ks,"_cs_ctx",lambda x:None)
    x=NS(R=NS(anchor=NS(b2_strict_observations=strict)),v={"cs":prior},tmp={},
         obs=NS(sim=NS(f=f)))
    ks.pl_claw(x,"var.tmp.plan",ground,accepting,
               hop_until=None if prior is None else prior.f0+prior.hop,p_only=p_only)
    assert x.tmp["plan"] is None
    return calls[0]


def test_initial_b2_ground_hop_has_three_frame_jump_lead(monkeypatch):
    assert B2_HOOK_JUMP_LEAD==3
    assert adapter(monkeypatch)["p_min"]==1005


@pytest.mark.parametrize("p_only",[1004,None])
def test_recheck_and_fallback_preserve_original_jump_floor(monkeypatch,p_only):
    prior=NS(f0=1002,hop=3)
    kw=adapter(monkeypatch,ground=False,prior=prior,f=1001,p_only=p_only)
    assert kw["p_min"]==1005 and kw["p_only"]==p_only
    assert kw["hop_until"]==1005


@pytest.mark.parametrize("ground,accepting,prior",[(False,True,None),(True,False,None),
    (False,True,NS(f0=1002,hop=0))])
def test_no_ground_jump_does_not_add_a_takeoff_floor(monkeypatch,ground,accepting,prior):
    assert "p_min" not in adapter(monkeypatch,ground=ground,accepting=accepting,prior=prior)


def test_legacy_family_adapter_has_no_new_keyword_or_domain(monkeypatch):
    assert adapter(monkeypatch,strict=False,prior=NS(f0=1002,hop=3))=={"hop_until":1005,"p_only":None}


def test_first_feasible_still_requires_every_control_variant(monkeypatch):
    owner,sim,ctx=search(monkeypatch);calls=[]
    def evaluate(*a,**kw):
        calls.append(None)
        # First candidate fails its second control variant; the next has one
        # actual passing strike per variant and must be recomputed completely.
        return [] if len(calls)==2 else [NS(row=lambda:["witness"])]
    monkeypatch.setattr(owner,"eval_strike",evaluate)
    p=owner.plan(sim,ctx,True,True,p_min=1005,first_feasible=True)
    assert p.f_press==1006 and p.var_ok==[1,1,1,1] and len(calls)==6


def test_first_feasible_changes_quality_preference_not_the_feasibility_gate(monkeypatch):
    owner,sim,ctx=search(monkeypatch);calls=[]
    def evaluate(*a,**kw):
        calls.append(None);count=1 if len(calls)<=4 else 4
        return [NS(row=lambda:["witness"]) for _ in range(count)]
    monkeypatch.setattr(owner,"eval_strike",evaluate)
    first=owner.plan(sim,ctx,True,True,p_min=1005,first_feasible=True)
    assert first.f_press==1005 and first.var_ok==[1]*4 and len(calls)==4
    calls.clear()
    legacy=owner.plan(sim,ctx,True,True,p_min=1005)
    assert legacy.f_press==1006 and legacy.var_ok==[4]*4 and len(calls)==8


@pytest.mark.parametrize("value",[None,1,"yes"])
def test_invalid_first_feasible_preference_is_rejected(monkeypatch,value):
    owner,sim,ctx=search(monkeypatch)
    with pytest.raises(ValueError,match="first-feasible"):
        owner.plan(sim,ctx,True,True,first_feasible=value)


def test_b2_only_sets_first_feasible_for_the_ground_jump_family(monkeypatch):
    assert adapter(monkeypatch)["first_feasible"] is True
    assert adapter(monkeypatch,ground=False,prior=NS(f0=1002,hop=3))["first_feasible"] is True
    assert "first_feasible" not in adapter(monkeypatch,ground=False)
    assert "first_feasible" not in adapter(monkeypatch,strict=False)
