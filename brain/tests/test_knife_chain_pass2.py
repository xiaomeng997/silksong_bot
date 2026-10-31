"""B2 no-event physics reuse retains each timeline's contacts and hit physics."""
from copy import deepcopy
from dataclasses import asdict
import numpy as np
import pytest
from ssbot.combat import air_chain as ac,pogo_slam as ps
from ssbot.knowledge import kinematics as kin


@pytest.fixture
def problem():
    from ssbot.train.forum_planner_policy import CREST_PARAMS
    params=kin.HeroParams.load(CREST_PARAMS["Wanderer"])
    terrain=kin.Terrain2D.from_boxes([(0.,ps.FLOOR_Y-5.,80.,ps.FLOOR_Y)])
    s=kin.initial_state(params,35.,15.,vy=-1.,facing=-1,ground=False)
    sim=ac.ChainSim(s,np.zeros(1,np.int64),kin.HoldState.idle(1),params,terrain,100,100)
    ctx=ac.Ctx(7,30.,7.45,1,30,None,35.,-1,tls=[ps.SlamTimeline.load(antic=48,s0=4,phase=0.),ps.SlamTimeline.load(antic=49,s0=5,phase=.5)])
    plans=[ac.Plan(102,ac.M_L if d else 0,102+d,None,None,fp,fp-70,7) for fp in (118,120,122) for d in (0,3)]
    return sim,ctx,plans


def rows(result):return [asdict(p) for p in result]


def watch_rows(monkeypatch,sim):
    calls=[];original=ac._pass2_rows
    def checked(ro,sel):
        got=original(ro,sel);calls.append(tuple(sel))
        assert got.variants==()
        for name in ("phys","pos","vel","mode","flags","box"):
            assert np.array_equal(getattr(got,name),getattr(ro,name)[sel])
        assert np.array_equal(got.final,ro.final[:,sel])
        return got
    monkeypatch.setattr(ac,"_pass2_rows",checked)
    return calls


def test_native_physics_reuse_with_survivor_subset_keeps_all_fields(problem,monkeypatch):
    sim,ctx,plans=problem;calls=watch_rows(monkeypatch,sim)
    def contact(ro,pi,faces,context,tl,targets):
        # The first timeline rejects row zero; the next must use precisely the
        # remaining lanes of the same no-event physics, with fresh contact work.
        j=np.asarray(pi)+3
        if tl is ctx.tls[0] and targets=="b":j[0]=-1
        return j
    monkeypatch.setattr(ac,"_contacts",contact)
    monkeypatch.setattr(ac,"_CONTACTS_AUTHORITY",contact) # controlled pure contact oracle for this lane-subset test
    safe=lambda ro,*a,**k:np.full(ro.flags.shape[0],-1)
    monkeypatch.setattr(ac,"_first_unsafe",safe)
    monkeypatch.setattr(ac,"_UNSAFE_AUTHORITY",safe)
    expected=ac.evaluate(sim,ctx,deepcopy(plans),102)
    got=ac.evaluate(sim,ctx,deepcopy(plans),102,reuse_no_event=True)
    assert rows(got)==rows(expected) and got
    assert calls and calls[0]==tuple(range(1,len(plans)))


@pytest.mark.parametrize("x",[31.,34.,37.,40.])
def test_real_timeline_geometry_keeps_plan_contacts_and_order(problem,monkeypatch,x):
    sim,ctx,plans=problem;sim.start[kin.PX]=x;ctx.hero_x=x
    calls=watch_rows(monkeypatch,sim)
    expected=ac.evaluate(sim,ctx,deepcopy(plans),102)
    got=ac.evaluate(sim,ctx,deepcopy(plans),102,reuse_no_event=True)
    assert rows(got)==rows(expected)


def test_optional_earlier_downslash_never_reuses_pass2(problem,monkeypatch):
    sim,ctx,plans=problem;plans[0].f_down=104
    calls=watch_rows(monkeypatch,sim)
    assert rows(ac.evaluate(sim,ctx,deepcopy(plans),102,reuse_no_event=True))==rows(ac.evaluate(sim,ctx,deepcopy(plans),102))
    assert not calls


@pytest.mark.parametrize("adapter",["sim","roll","physics","contacts","unsafe"])
def test_unknown_rollout_authority_retains_original_calls(problem,monkeypatch,adapter):
    sim,ctx,plans=problem
    if adapter=="sim":
        class Adapter(ac.ChainSim):pass
        sim=Adapter(**vars(sim))
    elif adapter=="roll":
        old=ac.ChainSim.roll
        monkeypatch.setattr(ac.ChainSim,"roll",lambda self,*a,**k:old(self,*a,**k))
    elif adapter=="physics":
        old=kin.rollout
        monkeypatch.setattr(kin,"rollout",lambda *a,**k:old(*a,**k))
    else:
        name="_contacts" if adapter=="contacts" else "_first_unsafe"
        old=getattr(ac,name)
        monkeypatch.setattr(ac,name,lambda *a,**k:old(*a,**k))
    calls=watch_rows(monkeypatch,sim)
    assert rows(ac.evaluate(sim,ctx,deepcopy(plans),102,reuse_no_event=True))==rows(ac.evaluate(sim,ctx,deepcopy(plans),102))
    assert not calls


def test_default_does_not_reuse_and_empty_timelines_keep_behavior(problem,monkeypatch):
    sim,ctx,plans=problem;calls=watch_rows(monkeypatch,sim)
    ac.evaluate(sim,ctx,deepcopy(plans),102);assert not calls
    ctx.tls=[]
    assert rows(ac.evaluate(sim,ctx,deepcopy(plans),102,reuse_no_event=True))==rows(ac.evaluate(sim,ctx,deepcopy(plans),102))
    assert ac.evaluate(sim,ctx,[],102,reuse_no_event=True)==[]


@pytest.mark.parametrize("lanes",["start","hold"])
def test_multiple_origin_lanes_keep_original_shape_failure(problem,monkeypatch,lanes):
    sim,ctx,plans=problem
    if lanes=="start":sim.start=np.repeat(sim.start[:,None],2,axis=1)
    else:sim.hold=kin.HoldState.idle(2)
    calls=watch_rows(monkeypatch,sim)
    with pytest.raises(ValueError):ac.evaluate(sim,ctx,deepcopy(plans),102)
    with pytest.raises(ValueError):ac.evaluate(sim,ctx,deepcopy(plans),102,reuse_no_event=True)
    assert not calls
