"""Value cannot veto admitted N=2; full-exit unknown is per candidate."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import math
import numpy as np
import pytest
from ssbot.combat.knife_chain_commitment import (
    ContinuationUnavailable,ContinuationResult,Continuation,FullContinuationScan,ContactScan,MoveInstance,PathContact,
    assess_continuations,
)
from ssbot.combat.knife_chain_value import handback_value


def admitted(*kinds):
    return ContinuationResult("pass","lower_bound",tuple(kinds),(),(),"N=2 already passed",())


def short(value):return SimpleNamespace(end="short",value=value)
def full(value):return SimpleNamespace(end="handback",value=value)
def endpoint(p):return p.value


def test_unavailable_first_kind_does_not_veto_and_all_qualified_handbacks_compete():
    paths={"left_landing":short(-3.),"right_landing":short(-2.),"dash_out":short(-1.)}
    exits=admitted(*paths);before=repr(exits);calls=[]
    def finish(k):
        calls.append(k)
        if k=="left_landing":raise ContinuationUnavailable("left wall; never lands")
        return full(4. if k=="right_landing" else 6.)
    value,info=handback_value(paths,exits,finish,endpoint)
    assert value==6. and info["kind"]=="dash_out" and calls==list(paths)
    assert info["full_unavailable"][0]["kind"]=="left_landing"
    assert not info["value_fallback"] and info["admission_unchanged"] and repr(exits)==before


def test_nonqualified_type_never_competes_and_ties_are_stable():
    paths={"left_landing":short(1.),"right_landing":short(2.),"dash_out":short(100.)}
    calls=[]
    def finish(k):calls.append(k);return full(3.)
    value,info=handback_value(paths,admitted("left_landing","right_landing"),finish,endpoint)
    assert value==3. and info["kind"]=="left_landing" and calls==["left_landing","right_landing"]


def test_all_full_unavailable_uses_best_qualified_short_endpoint_and_preserves_pass():
    paths={"left_landing":short(-4.),"right_landing":short(-2.)};exits=admitted(*paths)
    def unavailable(_):raise ContinuationUnavailable("no handback within160")
    value,info=handback_value(paths,exits,unavailable,endpoint)
    assert value==-2. and info["kind"]=="right_landing" and info["value_fallback"]
    assert info["mode"]=="short_endpoint_fallback" and len(info["full_unavailable"])==2
    assert exits.verdict=="pass" and exits.mode=="lower_bound"


def test_explicit_unscored_zero_is_not_fabricated_handback_or_safety_evidence():
    paths={"left_landing":short(None),"right_landing":short(None)}
    def unavailable(_):raise ContinuationUnavailable("model unavailable")
    value,info=handback_value(paths,admitted(*paths),unavailable,unavailable)
    assert value==0. and info["value_fallback"] and info["unscored"] and info["stance_evidence"]=="none"
    assert info["kind"] is None and not info["full_values"] and not info["short_values"]
    assert "not safety/contact certificates" in info["scope"]


@pytest.mark.parametrize("where",["finish","endpoint"])
@pytest.mark.parametrize("error",[RuntimeError("adapter bug"),ValueError("invalid shape"),TypeError("bad endpoint")])
def test_unknown_programming_defects_are_not_relabelled_coverage_or_zero(where,error):
    paths={"left_landing":short(0.),"right_landing":short(1.)}
    def defect(_):raise error
    with pytest.raises(type(error),match=str(error)):
        handback_value(paths,admitted(*paths),defect if where=="finish" else lambda _:full(2.),
                       defect if where=="endpoint" else endpoint)


def test_named_model_not_ready_is_caught_without_swallowing_other_runtime_errors():
    class ModelNotReady(RuntimeError):pass
    paths={"left_landing":short(-2.),"right_landing":short(-1.)}
    def finish(_):raise ModelNotReady("known missing model")
    value,info=handback_value(paths,admitted(*paths),finish,endpoint,unavailable_errors=(ModelNotReady,))
    assert value==-1. and info["value_fallback"]
    assert info["full_unavailable"][0]["type"]=="ModelNotReady"


def test_nonfinite_handback_is_an_explicit_estimation_gap_not_a_ranking_nan():
    paths={"left_landing":short(-2.),"right_landing":short(-1.)}
    value,info=handback_value(paths,admitted(*paths),lambda _:full(float("nan")),endpoint)
    assert value==-1. and math.isfinite(value) and info["value_fallback"]


@pytest.mark.parametrize("bad",[(Exception,),(ValueError,),(RuntimeError,),[ContinuationUnavailable]])
def test_broad_or_invalid_catch_sets_are_rejected(bad):
    with pytest.raises(TypeError,match="specific exception"):
        handback_value({"left_landing":short(0.)},admitted("left_landing"),lambda _:full(1.),endpoint,unavailable_errors=bad)


def test_unpassed_admission_and_missing_qualified_paths_are_programming_errors():
    paths={"left_landing":short(0.)}
    with pytest.raises(ValueError,match="passed continuation"):
        handback_value(paths,replace(admitted("left_landing"),verdict="unchecked"),lambda _:full(1.),endpoint)
    with pytest.raises(ValueError,match="paths missing"):
        handback_value(paths,admitted("left_landing","right_landing"),lambda _:full(1.),endpoint)


def scan(ref,last=160,contacts=()):return ContactScan(ref,100,last,tuple(contacts),"fixture full/short coverage")
def dash_option(name):return Continuation(name,"dash_out","bounce",name,160,True,"pass",scan(name,112))
def assess(opts,full_scan,**kwargs):
    return assess_continuations(tuple(opts),target_move=MoveInstance(7,50,"CC_SLAM"),bounce_state_ref="bounce",
                               bounce_frame=100,short_frames=12,full_scan=full_scan,**kwargs)


def test_full_exit_one_unavailable_candidate_does_not_prevent_later_safe_candidate():
    calls=[]
    def full_scan(o):
        calls.append(o.option_id)
        if o.option_id=="first":raise ContinuationUnavailable("wall hold")
        return scan(o.path_ref)
    result=assess([dash_option("first"),dash_option("second")],full_scan)
    assert result.verdict=="pass" and result.mode=="full_exit" and calls==["first","second"]
    assert result.unknown_options==("first",)
    assert result.checks[-2].verdict=="unchecked" and "wall hold" in result.checks[-2].reason


def test_full_exit_unavailable_does_not_relax_remaining_full_path_coverage_or_hazards():
    def full_scan(o):
        if o.option_id=="first":raise ContinuationUnavailable("wall hold")
        return scan(o.path_ref,120) # only partial coverage; cannot stand in for160
    result=assess([dash_option("first"),dash_option("second")],full_scan)
    assert result.verdict=="unchecked" and result.mode!="full_exit"
    blocked=assess([dash_option("one")],lambda o:scan(o.path_ref,160,(PathContact(150,8,"body"),)))
    assert blocked.verdict=="reject"


def test_full_exit_unknown_programming_errors_still_propagate():
    def bad(_):raise RuntimeError("geometry bug")
    with pytest.raises(RuntimeError,match="geometry bug"):assess([dash_option("one")],bad)
    def bad_identity(o):return FullContinuationScan(scan(o.path_ref,161),161)
    with pytest.raises(ValueError,match="handback differs"):assess([dash_option("one")],bad_identity)


# Rounded anchor fields copied from Opus review_ae44cdf1/claw_regress:
# ep04_14152545, ep06_14156854, ep09_14170292, ep10_14182860.
# Remaining K/Hold/alpha lanes are MODEL-initialized with the existing EV_POGO.
# This is self-contained regression of the wall/no-handback failure, not exact
# replay of all original K/Hold fields or a revalidation of foreign-hazard safety.
_CLAW_ANCHORS=[(4,14152545,14152596,19.349,9.748),(6,14156854,14156905,19.083,9.736),
               (9,14170292,14170343,19.406,9.748),(10,14182860,14182911,19.749,9.736)]


@pytest.fixture(scope="module")
def model():
    from ssbot.knowledge import kinematics as km
    base=km.HeroParams.load(Path(__file__).resolve().parents[2]/"knowledge/1.0.30000/kinematics/hero_wanderer_forum.json")
    params=km.HeroParams.from_json({**base.to_json(),**km.HERO2_OVERRIDES})
    terrain=km.Terrain2D.from_boxes([(-100,0,100,3.015),(0,0,14,40),(49,0,100,40)])
    return params,terrain


@pytest.mark.parametrize("ep,fa,bounce,x,y",_CLAW_ANCHORS)
def test_four_claw_wall_anchors_still_get_value_after_n2_pass(model,ep,fa,bounce,x,y):
    from ssbot.knowledge import kinematics as km
    from ssbot.combat.knife_chain_nominal import NominalUnsupported
    from ssbot.combat.knife_chain_post_actions import ordinary_post
    params,terrain=model
    s=km.initial_state(params,x,y,vy=-10.,ground=False,facing=-1,silk=9)
    ro=km.rollout(s,np.zeros((1,1),np.int64),params,terrain,events=np.full((1,1),km.EV_POGO,np.int64))
    s=ro.final[:,0].copy()
    s[[km.PX,km.QX,km.SX]]+=x-s[km.PX];s[[km.PY,km.QY,km.SY]]+=y-s[km.PY]
    s[km.VX]=0.;s[km.VY]=-10.
    parent=SimpleNamespace(end="bounce",stage="commitment",through=bounce,states=s[:,None],queued_next=0,
        hold_end=km.HoldState.idle(1),game=np.array([0.]),press_frame=bounce-4,
        raw_end={"ents":[{"iid":7,"pos":[30.,7.449]}]},runner_end=SimpleNamespace(run=SimpleNamespace(v={"iid":7})))
    kinds=("left_landing","right_landing")
    paths={k:ordinary_post(parent,params,terrain,kind=k) for k in kinds}
    assert all(len(p.commands)==12 for p in paths.values())
    options=[]
    for k in kinds:
        direction=-1 if k=="left_landing" else 1
        executable=bool(np.any(paths[k].states[km.VX,1:]*direction>0.))
        options.append(Continuation(k,k,"anchor-bounce",k,None,executable,"pass",
            ContactScan(k,bounce,bounce+12,(),"stored N2 qualification / model fixture clear scan")))
    exits=assess_continuations(tuple(options),target_move=MoveInstance(7,fa,"CC_SLAM"),
        bounce_state_ref="anchor-bounce",bounce_frame=bounce,short_frames=12,
        full_scan=lambda _:pytest.fail("N=2 pass must not query full safety"))
    assert exits.verdict=="pass" and exits.mode=="lower_bound"
    # The old representative=first code threw here, losing an admitted claw.
    with pytest.raises(NominalUnsupported,match="no ground/input"):
        ordinary_post(parent,params,terrain,kind="left_landing",full=True)
    finish=lambda k:ordinary_post(parent,params,terrain,kind=k,full=True)
    def value(p):
        centre=.5*(p.box[-1,0]+p.box[-1,2])
        return -.6*abs(centre-x)+(.2 if p.flags[-1]&km.F_GROUND else 0.)
    stance,info=handback_value(paths,exits,finish,value)
    assert math.isfinite(stance) and info["kind"]=="right_landing" and not info["value_fallback"]
    assert info["full_unavailable"][0]["kind"]=="left_landing" and exits.verdict=="pass"
