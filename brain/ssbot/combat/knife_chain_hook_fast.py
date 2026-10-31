"""Optional work deferral on the wait tick (target J-1) and the first-J tick (target J)
of a previously checked B2 hook.

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
FAST_J_TARGET_U=1e-3    # u, the target's position (a Clapper stands still in Slam Antic)
HOLD_AGE_CLASS=2        # hold_filter_jit's min_press / min_release: ages 0, 1 and >=2 behave apart


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



def observed_hold(hf):
    """Exact exported 22-key state; never fill missing fields with parser defaults."""
    if not isinstance(hf,dict):return None
    for name in ("latched","desired"):
        if type(hf.get(name)) is not int or not 0<=hf[name]<(1<<km.N_BUTTONS):return None
    for name,maximum in (("pending",3),("age",1<<20)):
        v=hf.get(name)
        if (not isinstance(v,(list,tuple)) or len(v)!=km.N_BUTTONS or
                any(type(x) is not int or not 0<=x<=maximum for x in v)):return None
    return km.HoldState.from_hf(hf)


def hold_equivalent(a,b):
    """Same future HoldFilter behaviour: latched, desired and pending per key, age by class."""
    return (np.array_equal(a.latched,b.latched) and np.array_equal(a.desired,b.desired) and
            np.array_equal(a.pending,b.pending) and
            np.array_equal(np.minimum(a.age,HOLD_AGE_CLASS),np.minimum(b.age,HOLD_AGE_CLASS)))


def hold_note(h):
    shift=np.arange(h.latched.shape[1],dtype=np.int64)
    return {"latched":int((h.latched[0].astype(np.int64)<<shift).sum()),"desired":int((h.desired[0].astype(np.int64)<<shift).sum()),
            "pending":[int(v) for v in h.pending[0]],"age_class":[int(v) for v in np.minimum(h.age[0],HOLD_AGE_CLASS)]}


def target_obs(e):
    """Known finite target pose and its explicit Control clock, otherwise unknown."""
    if not isinstance(e,dict) or type(e.get("flipX")) is not bool:return None
    pos=e.get("pos")
    if not isinstance(pos,(list,tuple)) or len(pos)<2:return None
    if any(type(x) not in (int,float) or not np.isfinite(x) for x in pos[:2]):return None
    fs=e.get("fsms")
    if not isinstance(fs,(list,tuple)):return None
    ctl=next((m for m in fs if isinstance(m,dict) and m.get("name")=="Control"),None)
    if not isinstance(ctl,dict) or not isinstance(ctl.get("state"),str):return None
    tin=ctl.get("t")
    if type(tin) not in (int,float) or not np.isfinite(tin) or tin<0:return None
    return {"pos":(float(pos[0]),float(pos[1])),"flip":e["flipX"],
            "state":ctl["state"],"k":int(round(tin*60.))}


def inputs(native,forecast):
    """The live inputs the fresh check reads on this tick."""
    tick,sim,guard,bombs=native._context;f,state,game,ground,accepting=tick
    c=native._fast_j_commit;receipt,source=native.queued_prefix(f,state)
    rs=getattr(forecast,"rs",None)
    observed=None if rs is None else getattr(rs.trk,"now",{}).get(c["move"].target_iid)
    e=next((e for e in state.get("ents") or () if e.get("iid")==c["move"].target_iid),None)
    hf=(state.get("act") or {}).get("hf");hold=observed_hold(hf)
    return {"f":f,"state":state,"ground":bool(ground),"accepting":bool(accepting),"sim":sim,
            "receipt":receipt,"receipt_source":source,"hold":hold,"hold_model":sim.hold,
            "hold_known":hold is not None,
            "instance":None if observed is None else observed[2],"owners":owners(forecast),"target":target_obs(e)}


def admit(native,forecast):
    """Wait tick (target J-1) or first-J tick (target J) only: the fresh check. A context
    dict, or None = full path this tick."""
    if native.commitment is None:return None
    jw=native._jump_start;f=native.dispatch.frame;F=f+2
    if jw is None or jw.sent_targets or jw.seen_frame is not None or not jw.targets:return None
    first=min(jw.targets)
    kind="J" if F==first else "wait" if F==first-1 else None
    if kind is None:return None   # not a fast tick: silent, unchanged
    c=native._fast_j_commit
    def fallback(reason,**data):
        native._note("b2_fast_j_fallback",frame=f,tick=kind,reason=reason,
                   path="unchanged full path (C5 recheck + nominal accounting) this tick",**data)
        return None
    if c is None or c["move"]!=native.commitment["move"] or c["key"] is None:
        return fallback("no commitment snapshot for this Move")
    fs=native._fast_j_sent   # only this Move's own skipped wait step may precede a fast first J
    if (native.recovery is not None or native.policy_gate_reason is not None or native.learning_stop is not None
            or native._vetoed_preparation is not None or (fs is not None and not (kind=="J" and fs["move"]==c["move"]
            and fs["deferred"] is None and fs.get("skips")==["wait"]))):
        return fallback("status flag set")
    hs=native._hook_start
    if hs is None or hs["move"]!=c["move"] or hs["sent_targets"] or hs["seen_frame"] is not None:
        return fallback("hook watch not armed for this Move")
    run=native.runner.run
    if run is None or run.lid!="slam_claw.pre":return fallback("runner not in slam_claw.pre")
    cs=run.v.get("cs");key=plan_key(cs)
    if key!=c["key"]:return fallback("CsPlan changed since commitment",now=key,committed=c["key"])
    keep=int(native.runner.cfg0.get("CS_KEEP_F",4))
    if not cs.hop or int(cs.f0)!=first:return fallback("jump watch and CsPlan disagree on the first J")
    if not (int(cs.f_press)-F<=keep and F-int(cs.f_press)<-1):
        # Here this tick's recheck could abort before the J: never skipped.
        return fallback("outside CS_KEEP_F",press=int(cs.f_press),keep=keep)
    if native._context is None:return fallback("no current model context")
    x=inputs(native,forecast);sim=x["sim"];state=x["state"]
    if sim.fo!=f or sim.f!=f or len(sim.prefix)!=1:return fallback("lagged/current model mismatch")
    path=c["path"];i=f-path.origin
    if not 1<=i<len(path.commands)-1:return fallback("frame outside committed nominal")
    want_next=int(path.commands[i]);want=int(path.commands[i+1])   # targets f+1 and f+2
    if want_next&B["J"]:return fallback("committed nominal has a J in flight before the first J")
    if kind=="J" and not want&B["J"]:return fallback("committed nominal has no first J at this target")
    if kind=="wait" and (want&B["J"] or want!=int(getattr(cs,"wait_mask",0))):
        return fallback("committed nominal is not the stable wait key here",nominal=want)
    # Real keys: in-flight prefix and every successful send since the commitment.
    receipt,source=x["receipt"],x["receipt_source"]
    if receipt is None or int(receipt)!=want_next or int(sim.prefix[0])!=want_next:
        return fallback("in-flight prefix differs from committed nominal",receipt=receipt,source=source,nominal=want_next)
    for t in range(path.origin+1,f+2):
        m=native._receipts.get(t)
        if m is not None and int(m)!=int(path.commands[t-path.origin-1]):
            return fallback("successful send differs from committed nominal",target=t,sent=int(m))
    # Input acceptance so far.
    act=state.get("act") or {};hf=act.get("hf") or {}
    at,ap,desired=act.get("target"),act.get("applied"),hf.get("desired")
    latched=hf.get("latched",act.get("mask"))
    if not (type(at) is int and type(ap) is int and type(desired) is int and path.origin<at<=f+1 and at<=ap<=f
            and desired==int(path.commands[at-path.origin-1]) and type(latched) is int and latched==desired):
        return fallback("application report does not match committed nominal",target=at,applied=ap,
                        desired=desired,latched=latched)
    if not (x["accepting"] and x["ground"]):return fallback("hero not grounded and accepting input")
    # HoldFilter: the commitment's hold pushed through the same commanded prefix (frames
    # origin+1..f) by the planner's compiled filter, against this STATE's act.hf.
    if c.get("hold_start") is None or not c.get("hold_known") or not x["hold_known"]:
        return fallback("act.hf not fully exported at commitment or now")
    if not hold_equivalent(x["hold"],x["hold_model"]):return fallback("current model hold differs from actual act.hf")
    from .holdfilter import hold_filter_jit
    try:_,pred=hold_filter_jit(np.asarray(path.commands[:i],np.int64)[None],c["hold_start"],parallel=False)
    except (TypeError,ValueError,IndexError):return fallback("hold state unavailable")
    if not hold_equivalent(pred,x["hold"]):
        return fallback("hold state differs from the commitment hold pushed through the same prefix",
                        predicted=hold_note(pred),actual=hold_note(x["hold"]))
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
    # Same target: tracked instance object, position, facing, Slam Antic one frame per frame.
    if x["instance"] is None or x["instance"] is not c["instance"]:
        return fallback("target tracker instance differs from commitment")
    a,b=c.get("target"),x["target"]
    if (a is None or b is None or b["state"]!="Slam Antic" or b["flip"]!=a["flip"] or b["k"]-a["k"]!=i or
            max(abs(b["pos"][0]-a["pos"][0]),abs(b["pos"][1]-a["pos"][1]))>FAST_J_TARGET_U):
        return fallback("target position, facing or antic clock differs from commitment",committed=a,now=b)
    # New-owner check only: the hazards of existing owners may still have moved or changed timing.
    current_owners=x["owners"]
    if current_owners is None or c["owners"] is None or not current_owners<=c["owners"]:
        return fallback("new owner outside the commitment set",
                        new=None if current_owners is None or c["owners"] is None else sorted(current_owners-c["owners"]))
    return {"tick":kind,"key":key,"mask":want,"used":False,"delta":d,"owners":len(current_owners),
            "application":{"target":at,"applied":ap,"desired":desired,"receipt_source":source}}
