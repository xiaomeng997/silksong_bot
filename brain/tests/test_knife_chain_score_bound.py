"""A losing ordinary score is not ordinary safety; chain owns action memory."""
from types import SimpleNamespace as NS
import math
import numpy as np
import pytest
from ssbot.knowledge import kinematics as kin
from ssbot.combat.knife_chain_score_bound import after_score_bound,ValueDominated,clear_ordinary_action_memo


def bound(scores,**kw):
    args=dict(challenger=7.,hit_weight=12.,whip_penalty=1.,bind_possible=False)
    args.update(kw)
    return after_score_bound(np.asarray(scores),np.zeros(len(scores)),**args)


def test_all_rows_including_high_score_vetoed_rows_must_be_dominated():
    assert bound([-4.,-6.,-8.]).upper_bound<7.
    assert bound([-4.,9.,-8.]) is None
    assert bound([7.,-8.]) is None
    assert bound([0.],challenger=math.nextafter(0.,math.inf)) is None


@pytest.mark.parametrize("change",["bind","negative_hit","negative_whip","negative_hits","nan","inf","unknown"])
def test_unproven_score_inputs_keep_original_checks(change):
    scores=np.array([-4.,-6.]);hits=np.zeros(2);kw=dict(challenger=7.,hit_weight=12.,whip_penalty=1.,bind_possible=False)
    if change=="bind":kw["bind_possible"]=True
    if change=="negative_hit":kw["hit_weight"]=-1.
    if change=="negative_whip":kw["whip_penalty"]=-1.
    if change=="negative_hits":hits[1]=-1.
    if change=="nan":scores[0]=np.nan
    if change=="inf":kw["challenger"]=np.inf
    if change=="unknown":scores=scores.astype(object)
    assert after_score_bound(scores,hits,**kw) is None


def test_positive_whip_deductions_never_break_bound():
    rng=np.random.default_rng(812)
    for _ in range(100):
        scores=rng.normal(-3.,2.,80);hits=rng.uniform(0.,5.,80)
        proof=after_score_bound(scores,hits,challenger=30.,hit_weight=12.,whip_penalty=1.,bind_possible=False)
        assert proof and np.max(scores-12.*(hits+1.))<=proof.upper_bound
        assert not hasattr(proof,"S") and "unchecked" in proof.safety


def test_chain_winner_cancels_unexecuted_action_hints_without_advancing_clock():
    p=NS(ticks=19,jump_until=30,macro_until=40,_prev_sm=object(),_kp="ds",_ds_keep_b=4,_ds_prev=np.array([1]))
    clear_ordinary_action_memo(p)
    assert p.ticks==19 and p.jump_until==p.macro_until==-1
    assert p._prev_sm is p._kp is p._ds_keep_b is p._ds_prev is None


def planner_case(monkeypatch,*,proof=True,allowed=True,stage="commitment",stale=False):
    from ssbot.combat import forum_planner as fp
    p=fp.ForumPlanner.__new__(fp.ForumPlanner);p.ticks=5;p.jump_until=88;p.macro_until=99
    calls=[];notes=[];offer=NS(stage=stage,value=7.,mask=1)
    result=NS(t_ms={},mask=1)
    ordinary=NS(J=-4.,S=0,forced_risk=False,t_ms={},name="normal")
    def work(self,*a,challenger_value=None):
        calls.append(challenger_value)
        if challenger_value is not None and proof:
            return ValueDominated(-3.,8. if stale else challenger_value,12,"after_all_positive_score_credits")
        return ordinary
    monkeypatch.setattr(fp.ForumPlanner,"_ordinary_tick",work)
    monkeypatch.setattr(fp,"_ORDINARY_TICK_AUTHORITY",work)
    def install(offer,parent,*args):
        clear_ordinary_action_memo(parent);parent.last_info={"b2":{}}
        return result
    p.chain_native=NS(b2=True,arm="B",propose=lambda *a:offer,first_allowed=lambda *a:allowed,
        install=install,_note=lambda *a,**k:notes.append((a,k)))
    args=(NS(stamp=NS(frame=1000)),None,None,None,None,None,None)
    return fp,p,args,calls,notes,result,ordinary


def test_native_consumer_counts_tick_once_and_reports_unchecked_not_safe(monkeypatch):
    fp,p,args,calls,notes,result,_=planner_case(monkeypatch)
    assert fp.ForumPlanner.tick(p,*args) is result and calls==[7.] and p.ticks==6
    assert p.last_sel is p.last_safe is p.last_cs is None
    assert p.jump_until==p.macro_until==-1
    info=p.last_info["b2"]["ordinary_value_bound"]
    assert "unchecked" in info["ordinary_safety"] and "S" not in info
    assert notes[0][0][0]=="b2_ordinary_value_pruned"


def test_unadmitted_chain_never_skips_ordinary(monkeypatch):
    fp,p,args,calls,notes,_,ordinary=planner_case(monkeypatch,allowed=False)
    assert fp.ForumPlanner.tick(p,*args) is ordinary and calls==[None]


def test_post_bounce_is_not_this_commitment_prune(monkeypatch):
    fp,p,args,calls,notes,result,_=planner_case(monkeypatch,stage="continuation")
    assert fp.ForumPlanner.tick(p,*args) is result and calls==[None]


def test_stale_value_proof_cannot_select_chain(monkeypatch):
    fp,p,args,calls,notes,_,_=planner_case(monkeypatch,stale=True)
    with pytest.raises(RuntimeError,match="does not match"):fp.ForumPlanner.tick(p,*args)


@pytest.mark.parametrize("with_ordinary",[False,True])
def test_actual_commit_install_clears_memos_even_without_prune(with_ordinary):
    from tests.test_knife_chain_b2 import runner,raw
    from ssbot.combat.knife_chain_b2 import NativeChainB2,B2Offer
    from ssbot.combat.knife_chain_eval import Run
    from ssbot.combat.knife_chain_commitment import MoveInstance
    n=NativeChainB2(runner_factory=runner,probe_ref="score-test");n.begin(raw())
    draft=runner();draft.run=Run("slam_jump","jump",{})
    offer=B2Offer("commitment",None,draft,1,7.,MoveInstance(7,1000,"CC_SLAM"),{})
    p=NS(ticks=5,measurement_enabled=False,jump_until=88,macro_until=99,_kp="ds",_prev_sm=object(),_ds_keep_b=2,_ds_prev=np.array([1]))
    ordinary=NS(J=-4.,name="unused jump") if with_ordinary else None
    n.install(offer,p,ordinary)
    assert p.jump_until==p.macro_until==-1 and p.ticks==5
    assert p._kp is p._prev_sm is p._ds_keep_b is p._ds_prev is None


def early(**changes):
    from ssbot.combat.knife_chain_score_bound import zero_hit_bound
    args=dict(weights={},kind_weights=np.zeros((1,4)),challenger=7.,candidates=508,
        risk_x=np.array([0.,1.,2.]),risk=np.array([0.,.4,.2]),max_hits=None,continuation=True,
        under_upper=0.,eml_bonus_upper=0.,whip_penalty=1.)
    args.update(changes);return zero_hit_bound(**args)


def test_zero_kind_weights_yield_conservative_nonhit_bound_with_witness():
    q=early(weights={"face":.3,"ground":.2,"cont":.15})
    assert q and .65<q.upper_bound<.65001 and q.phase=="zero_effective_hit_weight_upper"
    assert dict(q.witness)["all_effective_kind_weights_zero"]==[[0.,0.,0.,0.]]
    assert dict(q.witness)["terminal_disabled"] is True


@pytest.mark.parametrize("change",["kind","negative_cost","nan","unsorted","mismatch","extra_gain","negative_max","negative_whip"])
def test_early_bound_unknown_or_competing_values_do_not_prune(change):
    kw={}
    if change=="kind":kw["kind_weights"]=np.array([[0.,0.,0.,.1]])
    if change=="negative_cost":kw["weights"]={"stance":-1.}
    if change=="nan":kw["risk"]=np.array([0.,np.nan,1.])
    if change=="unsorted":kw["risk_x"]=np.array([1.,0.,2.])
    if change=="mismatch":kw["risk"]=np.zeros(2)
    if change=="extra_gain":kw["under_upper"]=8.
    if change=="negative_max":kw["max_hits"]=-1.
    if change=="negative_whip":kw["whip_penalty"]=-1.
    assert early(**kw) is None
    # Even max_hits=0 does not authorize ignoring positive kind weights here.
    assert early(kind_weights=np.ones((1,4)),max_hits=0.) is None


def test_early_bound_covers_negative_risk_under_and_eml_bonuses():
    q=early(weights={"risk":3.},risk=np.array([-1.,0.,.4]),under_upper=1.,eml_bonus_upper=1.,challenger=9.)
    assert q and 5.5<q.upper_bound<5.5001


def test_nonhit_formula_stays_below_bound_for_interpolated_risk_and_penalties():
    rng=np.random.default_rng(2026)
    for _ in range(100):
        w={k:float(rng.uniform(0.,3.)) for k in ("hit","waste","jump","stance","risk","face","ground","cont")}
        rx=np.arange(5,dtype=float);rv=rng.normal(size=5);uu=float(rng.uniform(0.,2.));eu=float(rng.uniform(0.,2.))
        q=early(weights=w,risk_x=rx,risk=rv,under_upper=uu,eml_bonus_upper=eu,challenger=100.)
        xs=rng.uniform(-2.,6.,200);r=np.interp(xs,rx,rv)
        values=(-w["waste"]*rng.uniform(0.,5.,200)-w["jump"]*rng.integers(0,3,200)-w["stance"]*rng.uniform(0.,8.,200)
                -w["risk"]*r+w["face"]*rng.integers(0,2,200)+w["ground"]*rng.integers(0,2,200)+w["cont"]
                +rng.uniform(0.,uu,200)+rng.uniform(0.,eu,200))
        assert q and float(values.max())<=q.upper_bound


def early_native(monkeypatch,*,tw=0.,tv=None,wu=2.,eml=4.):
    from ssbot.combat import forum_planner as fp,forum_v2 as fv
    p=fp.ForumPlanner.__new__(fp.ForumPlanner);p.tv=tv
    from ssbot.knowledge import kinematics as kin
    p.params=kin.HeroParams();p.terrain=kin.Terrain2D.empty()
    p.fcfg=NS(tac={"under","eml"},under_dx_u=.5,w_under=wu,eml_hits_per_mask=eml,eml_mask=1.,w_whip_clash=1.)
    inner=fp._NATIVE_MULTI_FORECAST.__new__(fp._NATIVE_MULTI_FORECAST)
    object.__setattr__(inner,"boss_fc",None)
    f=fv.V2Forecast(inner,NS());calls=[]
    data=(np.zeros((1,38,4)),np.ones((1,38),bool),np.full((1,4),tw),[NS(hazard=False,type_key="clapper")])
    def targets(self,*a):calls.append(None);return data
    monkeypatch.setattr(fp.ForumPlanner,"_forum_targets",targets);monkeypatch.setattr(fp,"_FORUM_TARGETS_AUTHORITY",targets)
    gains=lambda:({"clapper":0.},{("clapper","CC_SLAM"):0.})
    monkeypatch.setattr(fp,"under_gains",gains);monkeypatch.setattr(fp,"_UNDER_GAINS_AUTHORITY",gains)
    prefs=NS(stance_x=35.,boss_x=30.,weights={"hit":12.,"face":.3,"ground":.2,"cont":.15},risk_x=np.arange(3,dtype=float),risk=np.zeros(3),max_hits=None)
    return p,f,prefs,calls,data


def test_native_early_proof_reads_actual_kind_overrides_and_reuses_targets_on_miss(monkeypatch):
    p,f,prefs,calls,data=early_native(monkeypatch,tw=.5)
    q,prepared=p._zero_hit_value_bound(None,f,prefs,None,start=np.zeros(kin.K),P=1,T=36,N=508,cont=True,challenger=7.)
    assert q is None and prepared is data and len(calls)==1


@pytest.mark.parametrize("field",["tv","under_nan","eml_nan"])
def test_native_early_cannot_hide_terminal_or_nan_score_terms(monkeypatch,field):
    kw={"tv":object()} if field=="tv" else {"wu":float("nan")} if field=="under_nan" else {"eml":float("nan")}
    p,f,prefs,calls,data=early_native(monkeypatch,**kw)
    q,prepared=p._zero_hit_value_bound(None,f,prefs,None,start=np.zeros(kin.K),P=1,T=36,N=508,cont=True,challenger=7.)
    assert q is None
    if field=="tv":assert not calls and prepared is None


def test_native_early_proof_reads_zero_kind_weights_and_bounded_terms(monkeypatch):
    p,f,prefs,calls,data=early_native(monkeypatch)
    q,prepared=p._zero_hit_value_bound(None,f,prefs,None,start=np.zeros(kin.K),P=1,T=36,N=508,cont=True,challenger=7.)
    assert q and .65<q.upper_bound<.65001 and prepared is data


def test_unknown_ordinary_adapter_cannot_feed_a_valid_looking_carrier(monkeypatch):
    fp,p,args,calls,notes,_,_=planner_case(monkeypatch)
    # Native authority is different, so even a matching carrier from this
    # adapter was not authorized by the current admitted-offer call.
    monkeypatch.setattr(fp,"_ORDINARY_TICK_AUTHORITY",object())
    p._ordinary_tick=lambda *a:ValueDominated(-3.,7.,12,"after_all_positive_score_credits")
    with pytest.raises(RuntimeError,match="does not match"):fp.ForumPlanner.tick(p,*args)


@pytest.mark.parametrize("field",["stance_nan","stance_none","boss_text","under_text","under_dx_nan","kernel","terminal","rollout","start_nan","boss_proxy"])
def test_early_domain_or_adapter_errors_keep_original_route(monkeypatch,field):
    from ssbot.combat import forum_planner as fp
    from ssbot.knowledge import kinematics as kin
    p,f,prefs,calls,_=early_native(monkeypatch);start=np.zeros(kin.K)
    if field=="stance_nan":prefs.stance_x=float("nan")
    if field=="stance_none":prefs.stance_x=None
    if field=="boss_text":prefs.boss_x="30"
    if field=="under_text":p.fcfg.w_under="2"
    if field=="under_dx_nan":p.fcfg.under_dx_u=float("nan")
    if field=="kernel":monkeypatch.setattr(fp,"_forum_score_kernel",lambda *a:None)
    if field=="terminal":p._terminal=lambda *a:(object(),{})
    if field=="rollout":monkeypatch.setattr(kin,"rollout",lambda *a:None)
    if field=="start_nan":start[kin.PX]=float("nan")
    if field=="boss_proxy":object.__setattr__(f._inner,"boss_fc",object())
    q,_=p._zero_hit_value_bound(None,f,prefs,None,start=start,P=1,T=36,N=508,cont=True,challenger=7.)
    assert q is None


@pytest.mark.parametrize("active",["none","jump","macro","kept","bind"])
def test_native_ordinary_only_prunes_when_no_active_program_or_bind(active):
    from tests.test_forum_planner import _reed_forecaster,_world,_prefs,_ctx
    from ssbot.combat.forum_planner import ForumPlanner,ForumConfig
    from ssbot.combat.planner import PlannerConfig,PlanResult
    params=kin.HeroParams();terrain=kin.Terrain2D.from_boxes([(0.,0.,80.,3.)])
    p=ForumPlanner(params,terrain,PlannerConfig(T=24,threads=1),ForumConfig(v2=False,deadline_ms=float("inf")))
    p.win=None
    if active=="jump":p.jump_until=p.ticks+4
    if active=="macro":p.macro_until=p.ticks+4
    if active=="kept":p._kp="ds"
    ctx=_ctx();prefs=_prefs(x=27.)
    if active=="bind":prefs.want_bind=True;ctx.want_bind=True
    f=_reed_forecaster(stab_at=None).forecast(.8)
    start=kin.initial_state(params,27.,3.+params.foot)
    q=p._ordinary_tick(_world(27.),start,kin.HoldState.idle(1),np.zeros(1,np.int64),f,prefs,ctx,challenger_value=1e6)
    assert isinstance(q,ValueDominated if active=="none" else PlanResult)
