"""Optional first-J work deferral for a previously checked B2 hook.

Only the h2 CS_KEEP_F region is eligible. This is neither a new path certificate
nor a fresh geometry scan; new-owner checks cannot validate a changed hazard of
an existing owner. Default off and not eligible for live use until integration
and the complete tick/dispatch budget are verified.
"""
import numpy as np
from ssbot.knowledge import kinematics as km
from .knife_chain_format import MASK_NAMES as B

FAST_J_POS_U=0.05
FAST_J_VEL_U=0.5


def plan_key(cs):
    return None if cs is None else (int(cs.f0),int(cs.hop),int(cs.f_press),int(getattr(cs,"wait_mask",0)))


def owners(forecast):
    # New owners only; no claim that existing-owner geometry was refreshed.
    rs=getattr(forecast,"rs",None)
    if rs is None or not hasattr(rs,"trk"):return None
    try:
        found=set(getattr(rs.trk,"now",{}))|set(getattr(rs.trk,"orphan_hazards",{}))|set(rs.haz_raw)
        found|={int(p[0]) for parts in rs.raw.values() for p in parts}
        found|={int(p[0]) for parts in rs.layers.values() for p in parts}
        if rs.bombs is not None:found|={int(i) for i in rs.bombs[:,0]}
        return frozenset(int(i) for i in found)
    except (AttributeError,TypeError,ValueError,IndexError):
        return None  # unknown owner metadata cannot enable the fast path



def admit(native,forecast):
    """J-dispatch tick only: the fresh check. A context dict, or None = full path this tick."""
    if native.commitment is None:return None
    jw=native._jump_start;f=native.dispatch.frame
    if (jw is None or jw.sent_targets or jw.seen_frame is not None or not jw.targets or
            f+2!=min(jw.targets)):return None   # not the J-dispatch tick: silent, unchanged
    c=native._fast_j_commit
    def fallback(reason,**data):
        native._note("b2_fast_j_fallback",frame=f,reason=reason,
                   path="unchanged full path (C5 recheck + nominal accounting) this tick",**data)
        return None
    if c is None or c["move"]!=native.commitment["move"] or c["key"] is None:
        return fallback("no commitment snapshot for this Move")
    if (native.recovery is not None or native.policy_gate_reason is not None or native.learning_stop is not None
            or native._vetoed_preparation is not None or native._fast_j_sent is not None):
        return fallback("status flag set")
    hs=native._hook_start
    if hs is None or hs["move"]!=c["move"] or hs["sent_targets"] or hs["seen_frame"] is not None:
        return fallback("hook watch not armed for this Move")
    run=native.runner.run
    if run is None or run.lid!="slam_claw.pre":return fallback("runner not in slam_claw.pre")
    cs=run.v.get("cs");key=plan_key(cs)
    if key!=c["key"]:return fallback("CsPlan changed since commitment",now=key,committed=c["key"])
    F=f+2;keep=int(native.runner.cfg0.get("CS_KEEP_F",4))
    if not cs.hop or int(cs.f0)!=F:return fallback("this target is not the planned first J frame")
    if not (int(cs.f_press)-F<=keep and F-int(cs.f_press)<-1):
        # Here this tick's recheck could abort before the J: never skipped.
        return fallback("outside CS_KEEP_F",press=int(cs.f_press),keep=keep)
    if native._context is None:return fallback("no current model context")
    tick,sim,guard,bombs=native._context;_,state,game,ground,accepting=tick
    if sim.fo!=f or sim.f!=f or len(sim.prefix)!=1:return fallback("lagged/current model mismatch")
    path=c["path"];i=f-path.origin
    if not 1<=i<len(path.commands)-1:return fallback("frame outside committed nominal")
    want_next=int(path.commands[i]);want_j=int(path.commands[i+1])   # targets f+1 and f+2
    if not want_j&B["J"] or want_next&B["J"]:return fallback("committed nominal has no first J at this target")
    # Real keys: in-flight prefix and every successful send since the commitment.
    receipt,source=native.queued_prefix(f,state)
    if receipt is None or int(receipt)!=want_next or int(sim.prefix[0])!=want_next:
        return fallback("in-flight prefix differs from committed nominal",receipt=receipt,source=source,nominal=want_next)
    for t in range(path.origin+1,f+2):
        m=native._receipts.get(t)
        if m is not None and int(m)!=int(path.commands[t-path.origin-1]):
            return fallback("successful send differs from committed nominal",target=t,sent=int(m))
    # Input acceptance so far. Full pending/age equivalence is a separate integration requirement.
    act=state.get("act") or {};hf=act.get("hf") or {}
    at,ap,desired=act.get("target"),act.get("applied"),hf.get("desired")
    latched=hf.get("latched",act.get("mask"))
    if not (type(at) is int and type(ap) is int and type(desired) is int and path.origin<at<=f+1 and at<=ap<=f
            and desired==int(path.commands[at-path.origin-1]) and type(latched) is int and latched==desired):
        return fallback("application report does not match committed nominal",target=at,applied=ap,
                        desired=desired,latched=latched)
    if not (bool(accepting) and bool(ground)):return fallback("hero not grounded and accepting input")
    # Hero state vs the committed nominal at this frame.
    try:S=np.asarray(sim.start,float).reshape(km.K).copy();N=np.asarray(path.states[:,i],float)
    except (TypeError,ValueError,IndexError):return fallback("hero state unavailable")
    if not all(np.isfinite(S[j]) and np.isfinite(N[j]) for j in (km.PX,km.PY,km.VX,km.VY)):
        return fallback("hero state nonfinite")
    d={k:float(S[j]-N[j]) for k,j in (("px",km.PX),("py",km.PY),("vx",km.VX),("vy",km.VY))}
    same=all(float(S[j])==float(N[j]) for j in (km.FACE,km.GROUND,km.MODE))
    if (not same or max(abs(d["px"]),abs(d["py"]))>FAST_J_POS_U or max(abs(d["vx"]),abs(d["vy"]))>FAST_J_VEL_U):
        return fallback("hero state outside fast-J tolerance",delta=d,discrete_equal=same,
                        tol={"pos_u":FAST_J_POS_U,"vel_u_s":FAST_J_VEL_U})
    # Same tracked target instance; no owner outside the commitment check set.
    rs=getattr(forecast,"rs",None)
    observed=None if rs is None else getattr(rs.trk,"now",{}).get(c["move"].target_iid)
    instance=None if observed is None else observed[2]
    if instance is None or instance is not c["instance"]:
        return fallback("target tracker instance differs from commitment")
    current_owners=owners(forecast)
    if current_owners is None or c["owners"] is None or not current_owners<=c["owners"]:
        return fallback("hazard/owner outside commitment check set",
                        new=None if current_owners is None or c["owners"] is None else sorted(current_owners-c["owners"]))
    return {"key":key,"mask":want_j,"used":False,"delta":d,"owners":len(current_owners),
            "application":{"target":at,"applied":ap,"desired":desired,"receipt_source":source}}
