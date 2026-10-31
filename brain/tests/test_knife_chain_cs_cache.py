"""Exact same-step ClawStrike reuse: full inputs, private mutable results, no leak."""
from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import pytest
from ssbot.knowledge import kinematics as km
from ssbot.combat.air_chain import ChainSim,Plan
from ssbot.combat.claw_strike import ClawStrike,CsCfg,CsCtx
from ssbot.combat.knife_chain_cs_cache import exact_cs_step


@pytest.fixture
def problem(monkeypatch):
    from ssbot.combat import air_chain as AC
    calls=[]
    def evaluate(sim,ctx,plans,F0):
        calls.append((sim,ctx,len(plans),F0))
        out=[plans[0],plans[-1]]
        for p in out:p.c_strike=p.f_press+3
        return out
    monkeypatch.setattr(AC,"evaluate",evaluate)
    cs=ClawStrike(CsCfg(),params=object(),terrain=object())
    anchor=SimpleNamespace(csx=cs)
    start=np.zeros(km.K);start[km.PX]=35.
    sim=ChainSim(start,np.zeros(0,np.int64),km.HoldState.idle(1),cs.params,cs.terrain,129,130)
    ctx=CsCtx(7,30.,7.45,1,29,35.,-1,(28.,3.,29.,7.),[object(),object()])
    return anchor,sim,ctx,calls


def run(anchor,sim,ctx,*,entry=100,toward=-1,coarse=True):
    return anchor.csx.eval_strike(sim,ctx,entry,toward,coarse)


def test_default_and_disabled_use_original_grid_and_result_identity(problem):
    anchor,sim,ctx,calls=problem;original=anchor.csx
    assert original._exact_cs_step_cache is None
    run(anchor,sim,ctx);run(anchor,sim,ctx)
    assert len(calls)==2
    with exact_cs_step(anchor,enabled=False) as cache:
        assert cache is None and anchor.csx is original
        run(anchor,sim,ctx)
    assert len(calls)==3 and original._exact_cs_step_cache is None


def test_exact_repeat_reuses_full_evaluation_but_never_shares_returned_plan_mutations(problem):
    anchor,sim,ctx,calls=problem;original=anchor.csx
    with exact_cs_step(anchor) as cache:
        assert anchor.csx is not original
        assert anchor.csx.params is original.params and anchor.csx.terrain is original.terrain
        first=run(anchor,sim,ctx);contact=first[0].c_strike
        first[0].c_strike=-1;first.append(Plan(0,0,0,None,None,0,0,7))
        second=run(anchor,sim,ctx)
        assert len(calls)==1 and len(second)==2 and second[0].c_strike==contact
        assert second[0] is not first[0]
        second[0].pressed=999
        assert run(anchor,sim,ctx)[0].pressed is None
        assert cache.stats()["hits"]==2 and cache.stats()["misses"]==1
    assert anchor.csx._exact_cs_step_cache is None
    assert original._exact_cs_step_cache is None
    assert not cache.active and not cache._entries and not cache._readonly


@pytest.mark.parametrize("changed",[
    "start","prefix","hold_latched","hold_desired","hold_pending","hold_age","f","fo",
    "s_iid","s_x","s_y","s_face","kb0","hero_x","face","other_box","other_box_mutation",
    "entry","toward","coarse","cfg","params","terrain","tls","tls_order","start_dtype",
])
def test_any_key_input_change_recomputes_original_evaluation(problem,changed):
    anchor,sim,ctx,calls=problem;kw={}
    if changed=="other_box_mutation":ctx.other_box=np.array(ctx.other_box)
    with exact_cs_step(anchor) as cache:
        run(anchor,sim,ctx)
        if changed=="start":sim.start[km.PX]+=.001
        elif changed=="prefix":sim.prefix=np.array([0],np.int64)
        elif changed.startswith("hold_"):
            lane=getattr(sim.hold,changed[5:])
            lane[0,0]=not lane[0,0] if lane.dtype==bool else lane[0,0]+1
        elif changed in {"f","fo"}:setattr(sim,changed,getattr(sim,changed)+1)
        elif changed in {"s_iid","s_x","s_y","kb0","hero_x"}:setattr(ctx,changed,getattr(ctx,changed)+1)
        elif changed in {"s_face","face"}:setattr(ctx,changed,-getattr(ctx,changed))
        elif changed=="other_box":ctx.other_box=(27.,3.,29.,7.)
        elif changed=="other_box_mutation":ctx.other_box[0]-=.001
        elif changed=="entry":kw["entry"]=101
        elif changed=="toward":kw["toward"]=1
        elif changed=="coarse":kw["coarse"]=False
        elif changed=="cfg":anchor.csx.cfg=replace(anchor.csx.cfg,pre_press=(46,50))
        elif changed=="params":sim.params=object()
        elif changed=="terrain":sim.terrain=object()
        elif changed=="tls":ctx.tls=[object(),ctx.tls[1]]
        elif changed=="tls_order":ctx.tls.reverse()
        elif changed=="start_dtype":sim.start=sim.start.astype(np.float32)
        else:raise AssertionError(changed)
        run(anchor,sim,ctx,**kw)
        assert len(calls)==2 and cache.hits==0 and cache.misses==2


def test_empty_grid_is_cached_as_empty_not_as_pass(problem):
    anchor,sim,ctx,calls=problem
    with exact_cs_step(anchor) as cache:
        assert run(anchor,sim,ctx,entry=0)==[]
        assert run(anchor,sim,ctx,entry=0)==[]
        assert calls==[] and cache.hits==1 and cache.misses==1


def test_new_actual_step_recomputes_and_exception_always_releases_cache(problem,monkeypatch):
    from ssbot.combat import air_chain as AC
    anchor,sim,ctx,calls=problem
    with exact_cs_step(anchor):run(anchor,sim,ctx)
    with exact_cs_step(anchor):run(anchor,sim,ctx)
    assert len(calls)==2
    def fail(*a):raise RuntimeError("original evaluation failure")
    monkeypatch.setattr(AC,"evaluate",fail)
    with pytest.raises(RuntimeError,match="original evaluation failure"):
        with exact_cs_step(anchor) as cache:run(anchor,sim,ctx)
    assert anchor.csx._exact_cs_step_cache is None and not cache.active
    assert not cache._entries and not cache._readonly


def test_unknown_key_representation_falls_back_without_hiding_original_evaluation(problem):
    anchor,sim,ctx,calls=problem;ctx.s_iid=object()
    with exact_cs_step(anchor) as cache:
        run(anchor,sim,ctx);run(anchor,sim,ctx)
        assert len(calls)==2 and cache.uncacheable==2 and cache.hits==0


def test_missing_cs_instance_uses_normal_env_cfg_and_never_keeps_step_cache():
    anchor=SimpleNamespace(csx=None)
    with exact_cs_step(anchor) as cache:
        assert isinstance(anchor.csx,ClawStrike)
        assert anchor.csx.cfg==CsCfg.from_env()
        assert anchor.csx._exact_cs_step_cache is cache
    assert anchor.csx._exact_cs_step_cache is None and not cache.active
