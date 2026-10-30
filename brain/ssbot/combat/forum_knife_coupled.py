"""Pair one started Slam's contact and danger clocks for opt-in knife rows.

No new enemy policy or margin reduction. Within-state
geometry remains a conservative union of the existing template's state masks.
"""
from __future__ import annotations
import copy
import numpy as np
from ssbot.combat import attack_range as ar, forum_v2 as v2

STATES=("Slam Antic","Slam 0","Slam 1","Slam 2","Slam Recover")


def world_clock(observation,durations,length,shift=0):
    durations=tuple(map(int,durations))
    if (observation.st!=STATES[0] or len(durations)!=5 or min(durations)<=0
            or not 0<=int(observation.j)<durations[0] or length<0):
        raise ValueError("unsupported Slam world clock")
    si=0;j=int(observation.j);clock=[]
    for _ in range(length+1):
        clock.append((STATES[si],j) if si<len(STATES) else None)
        if si<len(STATES):
            j+=1
            if j>=durations[si]:si+=1;j=0
    ix=np.clip(np.arange(length+1)+int(shift),0,length)
    return [clock[int(k)] for k in ix]


def contact_bounds(planner,rollout,commands,face,inner,outer,shift=0,residual=.25):
    """One timing world only; preserve the hero residual and every clock lane."""
    n=len(rollout.hooks);length=len(commands)
    if residual<0 or inner.shape!=outer.shape or inner.shape!=(length+1,4):
        raise ValueError("invalid contact world bounds")
    ix=np.clip(np.arange(length+1)+int(shift),0,length)
    lower=inner[ix].copy();upper=outer[ix].copy()
    lower[:,:2]+=residual;lower[:,2:]-=residual
    upper[:,:2]-=residual;upper[:,2:]+=residual
    starts=[];contacts=[]
    masks=np.broadcast_to(commands,(n,length)).copy()
    for body in (upper,lower):
        valid=np.isfinite(body).all(axis=1)&(body[:,0]<body[:,2])&(body[:,1]<body[:,3])
        sw,cc,_,_=planner._ds_hits(rollout,masks,face,body[None],valid[None],np.ones(1,bool),
            np.full(n,2,np.int64),0.,np.zeros(0,np.int64))
        starts.append(sw);contacts.append(cc)
    first,last=contacts
    ok=(first>=0)&(last>=0)&(first<=last)&(starts[0]==starts[1])
    for q,start in enumerate(starts[0]):
        if not ok[q]:continue
        lo=max(0,int(start)+int(planner.shapes[3][3,0]))
        if not np.isfinite(upper[lo:int(last[q])+1]).all():ok[q]=False
    return starts[0],first,last,ok


def conditioned_slam(forecast,observation,durations,shift,roots):
    """Pair only the target core with its body clock; preserve every other layer.

    roots[k] is the same existing target displacement used by contact bodies,
    before applying the SAME shift. State geometry is not narrowed within a
    state. Unknown post-Slam decisions retain the original core, not empty air.
    """
    rs=forecast.rs;iid=observation.iid;roots=np.asarray(roots,float);length=len(roots)-1
    if (not isinstance(rs,v2.RangeSupport) or rs.focus!=iid or rs.k_shift!=0
            or roots.shape!=(length+1,2) or not np.isfinite(roots).all()
            or rs.samples[-1]<length or rs.haz_raw):
        raise ValueError("unsupported coupled support/origin")
    tk,_,inst=rs.trk.now[iid];tab=rs.trk.tables[tk]
    if tk!=v2.CLAPPER or inst is None or inst.fam!="CC_SLAM" or inst.s!=observation.face:
        raise ValueError("coupling requires the same observed started Slam")
    tp=tab.templates[("CC_SLAM","main")]
    if tp.sst is None:raise ValueError("missing state geometry")
    clock=world_clock(observation,durations,length,shift)
    shapes={}
    for state in {x[0] for x in clock if x is not None}:
        parts=[ar.Mask(mask,x,y) for states in tp.sst if state in states
               for mask,x,y in [states[state]]]
        if not parts:raise ValueError("missing state geometry: "+state)
        shapes[state]=ar.union(parts)
    estimates={}
    def estimate(k):
        if k not in estimates:
            e=rs.trk.estimate(iid,k)
            if e is None or e.core is None:raise ValueError("missing separable target core")
            estimates[k]=e
        return estimates[k]
    # Require exact provenance before removing any original target core.
    for si,k in enumerate(rs.samples):
        own=[p for p in rs.raw[si] if p[0]==iid]
        if len(own)!=1 or any(p[0]==iid for p in rs.layers[si]):
            raise ValueError("unrecognized target support pieces")
        c,x,y=v2.coarse(estimate(k).raw,tab.cell,rs.cv.cell);p=own[0]
        if p[2:4]!=(x,y) or not np.array_equal(p[1],c) or p[4]!=rs.m_of(iid,tk,k):
            raise ValueError("target support does not match tracker")
    samples=tuple(range(length+1));layer=v2.LayerSupport(rs.cv,samples,0,rs.fc._inner)
    ix=np.clip(np.arange(length+1)+int(shift),0,length)
    for si,k in enumerate(samples):
        # Preserve the old sparse bracket for unrelated owners and target hazards.
        for old in sorted({int(rs._lo[k]),int(rs._hi[k])}):
            for owner,mask,x,y in rs.layers[old]:layer.add(si,owner,mask,x,y)
            for owner,c,x,y,m,em in rs.raw[old]:
                if owner!=iid:layer.add_raw(si,owner,c,x,y,m,em)
                else:
                    hazard=estimate(rs.samples[old]).haz
                    if hazard is not None and hazard.m.size and hazard.m.any():
                        hc,hx,hy=v2.coarse(hazard,tab.cell,rs.cv.cell)
                        layer.add_raw(si,owner,hc,hx,hy,m,em)
        # Same one-bin callback sweep, on this world's clock and displacement.
        for q in sorted({max(0,k-1),k}):
            state=clock[q]
            if state is None:core=estimate(q).core
            else:
                shape=shapes[state[0]];px,py=roots[ix[q]]
                core=ar.place_shape(shape.m,shape.ix0,shape.iy0,px,py,inst.s,tab.cell)
            c,x,y=v2.coarse(core,tab.cell,rs.cv.cell);m=rs.m_of(iid,tk,q)
            layer.add_raw(si,iid,c,x,y,m,m if k>=v2.ESC_FROM_K else None)
    layer.finish();out=copy.copy(rs)
    for name in ("samples","_lo","_hi","layers","raw","stack","stack_esc"):
        setattr(out,name,getattr(layer,name))
    if rs.stack_dash is not None:
        ks=np.asarray(samples);out.stack_dash=rs.stack_dash[rs._lo[ks]]|rs.stack_dash[rs._hi[ks]]
    out.knife_coupled_world=dict(iid=iid,durations=tuple(durations),shift=int(shift),
        callback_sweep=1,within_state_geometry="full existing union",position="same contact root path",runtime_promoted=False)
    return v2.V2Forecast(forecast._inner,out)


def expected_slam_worlds(observation, knowledge):
    """Declare the full domain independently of candidates/contact survivors.

    Same duration ranges and shifts as the existing body/timing proposal family.
    An observed Antic age only removes durations already contradicted by that
    observation. This is not a calibration-based pruning rule.
    """
    from itertools import product
    from ssbot.combat.dslash import CERT_SHIFTS
    age = observation.j
    if (observation.st != STATES[0] or isinstance(age, (bool, np.bool_))
            or not isinstance(age, (int, np.integer)) or age < 0):
        raise ValueError("supported observed Slam Antic age required")
    domains = []
    for state in STATES:
        duration = knowledge.durations(state)
        if (duration is None or len(duration) != 3
                or any(isinstance(x, (bool, np.bool_)) or not isinstance(x, (int, np.integer)) for x in duration)):
            raise ValueError("complete integer Slam duration domain required")
        lo, mid, hi = map(int, duration)
        if not 0 < lo <= mid <= hi:
            raise ValueError("ordered positive Slam duration domain required")
        domains.append(range(lo, hi + 1))
    shifts = tuple(sorted({0, *map(int, CERT_SHIFTS)}))
    worlds = tuple((int(observation.iid), tuple(d), s)
                   for d in product(*domains) if age < d[0] for s in shifts)
    if not worlds:
        raise ValueError("observed age contradicts every declared Slam world")
    return worlds
