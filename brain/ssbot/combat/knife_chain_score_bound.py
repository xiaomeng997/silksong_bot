"""Value dominance only. No ordinary safety/escape verdict is issued here."""
from dataclasses import dataclass
import math
import numpy as np


@dataclass(frozen=True)
class ValueDominated:
    upper_bound: float
    challenger: float
    candidates: int
    phase: str
    safety: str = "unchecked; value-dominated ordinary checks not run"
    witness: tuple = ()


def after_score_bound(scores,hits,*,challenger,hit_weight,whip_penalty,bind_possible):
    """After all positive credits, only a nonnegative whip deduction remains.

    Include ALL rows, including currently vetoed rows. Unknown signs/NaNs or
    independent BIND (J=1000) lose the optimization, never the original checks.
    """
    if bind_possible or type(scores) is not np.ndarray or type(hits) is not np.ndarray:return None
    if scores.ndim!=1 or not len(scores) or hits.shape!=scores.shape:return None
    if scores.dtype.kind not in "fiu" or hits.dtype.kind not in "fiu":return None
    vals=(challenger,hit_weight,whip_penalty)
    if any(type(v) not in (int,float) and not (isinstance(v,np.generic) and v.dtype.kind in "fiu") for v in vals):return None
    if not all(math.isfinite(float(v)) for v in vals) or hit_weight<0 or whip_penalty<0:return None
    if not np.isfinite(scores).all() or not np.isfinite(hits).all() or (hits<0).any():return None
    upper=math.nextafter(float(np.max(scores)),math.inf)
    if not upper<float(challenger):return None
    return ValueDominated(upper,float(challenger),len(scores),"after_all_positive_score_credits")


def clear_ordinary_action_memo(planner):
    """A winning chain owns its action program, including early recovery.

    An ordinary row evaluated only for comparison was never executed. Its jump,
    macro or kept-action hints must not leak into the chain's next real handoff.
    This is an explicit B2 state-ownership correction, not state equivalence to
    the older implementation which retained the losing row's side effects.
    """
    planner.jump_until=planner.macro_until=-1
    planner._prev_sm=planner._kp=planner._ds_keep_b=planner._ds_prev=None


def score_number(v):
    if type(v) not in (int,float) and not (isinstance(v,np.generic) and type(v) is v.dtype.type and v.dtype.kind in "fiu"):raise ValueError("unknown score scalar")
    v=float(v)
    if not math.isfinite(v) or abs(v)>1e8:raise ValueError("score scalar outside numerical domain")
    return v


def zero_hit_bound(weights,kind_weights,*,challenger,candidates,risk_x,risk,max_hits,
                   continuation,under_upper,eml_bonus_upper,whip_penalty):
    """Native kernel upper bound when EVERY effective target/kind weight is zero.

    Extra special/DS credits and terminal values must be excluded by the caller.
    No position, trajectory, ordinary safety or guessed default target is used.
    """
    if type(weights) is not dict or type(kind_weights) is not np.ndarray:return None
    if kind_weights.ndim!=2 or kind_weights.shape[1]!=4 or kind_weights.dtype.kind not in "fiu":return None
    if not np.isfinite(kind_weights).all() or np.any(kind_weights!=0):return None
    number=score_number
    try:
        w={k:number(weights.get(k,d)) for k,d in (("hit",10.),("waste",.6),("jump",.15),("stance",.6),("risk",3.),("face",.3),("ground",.2),("cont",0.))}
        if any(w[k]<0 for k in ("hit","waste","jump","stance","risk")):return None
        ch=number(challenger);uu=number(under_upper);eu=number(eml_bonus_upper);wp=number(whip_penalty)
        if min(uu,eu,wp)<0:return None
        cap=None if max_hits is None else number(max_hits)
        if cap is not None and cap<0:return None
        if type(candidates) is not int or candidates<=0 or type(continuation) is not bool:return None
        if any(type(a) is not np.ndarray or a.ndim!=1 or a.dtype.kind not in "fiu" for a in (risk_x,risk)):return None
        if not len(risk_x) and not len(risk):rx=rv=np.zeros(1)
        elif len(risk_x)!=len(risk) or not len(risk_x):return None
        else:rx,rv=risk_x,risk
        rx=np.asarray(rx,dtype=np.float64);rv=np.asarray(rv,dtype=np.float64)
        if not np.isfinite(rx).all() or not np.isfinite(rv).all() or max(np.max(np.abs(rx)),np.max(np.abs(rv)))>1e8:return None
        dx=np.diff(rx)
        if len(dx) and not (dx>0).all():return None
        ratio=max(1.,float(np.max(np.abs(rx)))/(float(np.min(dx)) if len(dx) else 1.))
        ru=max(0.,-w["risk"]*float(np.min(rv)))
        upper=max(0.,w["face"])+max(0.,w["ground"])+(max(0.,w["cont"]) if continuation else 0.)+ru+uu+eu
        # Conservative positive roundoff reserve for interpolation/multiply/add;
        # the normal Forum grid is far inside this restricted numerical domain.
        reserve=1e-10*(1.+sum(abs(v) for v in w.values())+uu+eu+w["risk"]*max(1.,float(np.max(np.abs(rv))))*ratio)
        upper=math.nextafter(upper+reserve,math.inf)
        if not math.isfinite(upper) or not upper<ch:return None
        witness=(("all_effective_kind_weights_zero",kind_weights.tolist()),("cost_weights",w),
                 ("risk_min",float(np.min(rv))),("risk_upper",ru),("under_upper",uu),
                 ("eml_bonus_upper",eu),("max_hits",cap),("continuation",continuation),
                 ("bind_possible",False),("terminal_disabled",True),("extra_credit_rows",0),("roundoff_reserve",reserve))
        return ValueDominated(upper,ch,candidates,"zero_effective_hit_weight_upper",witness=witness)
    except (ValueError,TypeError,AttributeError,OverflowError):return None
