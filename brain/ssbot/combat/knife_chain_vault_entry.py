"""Bounded nominal entry proposals for the Idle vault family.

This module is a proposal producer, not admission, safety or execution. It does
not turn on the ordinary DSLASH family. Only the direction toward the observed
body is expanded. Target motion/reaction, external hazards, input provenance,
actual hit/bounce and the runtime winner still belong to the receiving adapter.
"""
from dataclasses import dataclass
import time
import numpy as np
from ssbot.knowledge import kinematics as K
from . import dslash, pogo_model as PM


@dataclass(frozen=True)
class NearVaultProposal:
    hold: int
    press: int
    before: str
    direction: int
    contact_index: int
    commands: np.ndarray
    body_assumption: str = "observed body held static; nominal contact only"

    def request_entry(self):
        return {"h":self.hold,"p":self.press,"before":self.before}


_DOWN_POLYS=tuple((face,alt) for face in (-1,1) for alt in (False,True))
_SURE=1e-8  # a verdict here must clear PM.meets' 1e-9 threshold by this much; closer calls go to PM.meets itself


def _axes(p):
    e=np.roll(p,-1,axis=0)-p
    return np.stack([-e[:,1],e[:,0]],axis=1)


def _meets_all(pos,poly):
    """all(PM.meets(PM.slash_poly(face,alt)+pos[i],poly) for both facings and shapes), one array pass per polygon.

    The same separating-axis test: axes from the slash polygon's edges and the box's, projections of the slash
    polygon shifted by pos[i] (equal to PM.meets' own up to rounding, ~1e-12 at these magnitudes). A verdict counts
    only _SURE clear of PM.meets' threshold; anything closer is decided by PM.meets on the original arrays."""
    pos=np.asarray(pos,float).reshape(-1,2)
    # Keep the rearranged projections in the small numerical domain verified
    # for this arena. Larger/nonfinite inputs use the original scalar order.
    if (not np.isfinite(pos).all() or not np.isfinite(poly).all() or
            np.max(np.abs(pos),initial=0.)>128. or np.max(np.abs(poly),initial=0.)>128.):
        return np.array([all(PM.meets(PM.slash_poly(face,alt)+v,poly)
                             for face,alt in _DOWN_POLYS) for v in pos],bool)
    ok=np.ones(len(pos),bool)
    for face,alt in _DOWN_POLYS:
        p=PM.slash_poly(face,alt);ax=np.vstack([_axes(p),_axes(poly)])
        pp,pq,s=p@ax.T,poly@ax.T,pos@ax.T
        d1=(pp.max(0)+s)-(pq.min(0)+1e-9);d2=pq.max(0)-((pp.min(0)+s)+1e-9)
        apart=((d1<=-_SURE)|(d2<=-_SURE)).any(axis=1);overlap=((d1>_SURE)&(d2>_SURE)).all(axis=1)
        for i in np.flatnonzero(~apart&~overlap&ok):
            overlap[i]=PM.meets(p+pos[i],poly)
        ok&=overlap&~apart
    return ok


def clean_near_row(sim, target_box, direction, *, walker_v=0., turned_box=None, min_press=0, hold=14, presses=range(3,21)):
    """Task 182 (SSBOT_FORUM_TWO_PLAN only, Sol seq 255 F2): the near vault row for THIS start, from the model: her actual height,
    speed and resources against the body, moved at the walker's speed. A row counts when its slash meets the body in its active
    frames (all four shapes, as near_proposals) and her box never overlaps the body before that contact; the earliest such
    contact wins. turned_box: the same body turned toward her (an Idle Clapper with her at its back turns, #321), which her box
    must clear too. (request entry dict or None, diagnostics). None: no such row: this start is not supported, not guessed."""
    from . import dslash as _d
    box=np.asarray(target_box,float)
    start=np.asarray(sim.start,float).reshape(-1)
    prefix=np.asarray(sim.prefix)
    if box.shape!=(4,) or not np.isfinite(box).all() or start.shape!=(K.K,) or not np.isfinite(start).all() or prefix.shape!=(1,):
        return None,{"status":"unknown_state","rows":0}
    if start[K.GROUND]<=0 or int(start[K.MODE])!=K.M_NORMAL or start[K.JHELD]>0 or int(prefix[0])&~(K.B_LEFT|K.B_RIGHT):
        return None,{"status":"unsupported_hero_state","rows":0}
    key=K.B_RIGHT if direction>0 else K.B_LEFT
    entries=[(hold,p,b) for p in presses if p>=min_press for b in ("T","N")]
    if not entries:return None,{"status":"attack_not_ready","rows":0}
    length=max(p for _,p,_ in entries)+_d.POST_F
    rows=[]
    for h,p,b in entries:
        row=np.zeros(length,np.int64);row[:h]|=K.B_JUMP
        if b=="T":row[:p]|=key
        _d.strike(row,p);row[p:]|=key
        rows.append(row)
    ro=sim.roll(np.asarray(rows,np.int64));off=len(prefix)
    dt=float(sim.params.frame_time)
    poly=np.array([[box[0],box[1]],[box[2],box[1]],[box[2],box[3]],[box[0],box[3]]])
    bodies=[box] if turned_box is None else [box,np.asarray(turned_box,float)]
    best=None;contacts=clean=0
    windows=[]
    for q,(h,p,b) in enumerate(entries):
        pj=off+p+1;flags=ro.flags[q]
        if not np.any(flags[pj:pj+2]&K.F_ATTACKING) or flags[pj-1]&K.F_GROUND:continue
        js=[j for j in range(pj+PM.ACTIVE[0],min(pj+PM.ACTIVE[1]+1,len(flags))) if not flags[j]&K.F_GROUND]
        if js:windows.append((q,js))
    shift=walker_v*dt*np.arange(ro.flags.shape[1])
    qs=np.array([q for q,js in windows for _ in js],np.int64);fs=np.array([j for _,js in windows for j in js],np.int64)
    # one array pass over every row's active frames (a row at a time costs ~19 ms: the entry's tick)
    hit=_meets_all(ro.pos[qs,fs]-np.stack([shift[fs],np.zeros(len(fs))],axis=1),poly) if len(qs) else np.zeros(0,bool)
    i=0
    for q,js in windows:
        h,p,b=entries[q]
        first=np.flatnonzero(hit[i:i+len(js)]);i+=len(js)
        if not len(first):continue
        contacts+=1
        c=js[int(first[0])]
        bx=ro.box[q,:c+1]
        clear=True
        for body in bodies:
            s=shift[:c+1]
            if np.any((bx[:,0]<=body[2]+s)&(bx[:,2]>=body[0]+s)&(bx[:,1]<=body[3])&(bx[:,3]>=body[1])):
                clear=False;break
        if not clear:continue
        clean+=1
        if best is None or c<best[0]:best=(c,h,p,b)
    diag={"status":"clean_row" if best else "no_clean_row","rows":len(entries),"contacts":contacts,"clean":clean}
    if best is None:return None,diag
    return {"h":best[1],"p":best[2],"before":best[3]},dict(diag,contact_index=best[0])


def near_proposals(sim, target_box, direction, *, max_results=2, recipes=None):
    """One batched HERO2 rollout; no pogo is injected without blade contact.

    Return proposals + bounded diagnostics. Their commands begin at f+2, after
    the supplied one-frame prefix. This first entry scope is a grounded normal
    hero, a new jump edge and a movement-only prefix. Broader airborne cut-in is
    intentionally not guessed here. The body is a caller-selected Idle target.
    """
    started=time.perf_counter()
    if type(direction) is not int or direction not in (-1,1):
        raise ValueError("vault direction must be -1 or +1")
    if type(max_results) is not int or not 1<=max_results<=8:
        raise ValueError("vault proposal limit must be 1..8")
    box=np.asarray(target_box,float)
    if box.shape!=(4,) or not np.isfinite(box).all() or box[0]>=box[2] or box[1]>=box[3]:
        raise ValueError("finite ordered target body required")
    prefix=np.asarray(sim.prefix)
    if sim.fo!=sim.f or prefix.shape!=(1,) or not np.issubdtype(prefix.dtype,np.integer):
        raise ValueError("vault needs the current origin and one known in-flight mask")
    start=np.asarray(sim.start)
    if start.shape!=(K.K,) or not np.isfinite(start).all():
        raise ValueError("finite single hero model state required")
    if start[K.GROUND]<=0 or int(start[K.MODE])!=K.M_NORMAL:
        return (),{"status":"unsupported_hero_state","generated":0}
    if int(prefix[0])<0 or int(prefix[0])&~(K.B_LEFT|K.B_RIGHT) or start[K.JHELD]>0:
        return (),{"status":"incompatible_inflight_or_jump_hold","generated":0}
    key=K.B_RIGHT if direction>0 else K.B_LEFT
    # A small target-directed subset, not 132 ordinary DSLASH rows or a global
    # per-tick family. Request only at this family's observed entry opportunity.
    # Explicit manual callers supply table rows. The old bounded grid remains
    # available only to offline calibration callers, never as a runtime retry.
    entries=([(h,p,b) for h in (14,20) for p in range(4,25) for b in ("T","N")]
             if recipes is None else [(r["hold"],r["press"],r["before"]) for r in recipes])
    if not entries or any(type(h) is not int or type(p) is not int or
                          not 1<=h<=30 or not 1<=p<=30 or b not in {"T","N"} for h,p,b in entries):
        raise ValueError("invalid manual near-vault recipe")
    length=max(p for _,p,_ in entries)+dslash.POST_F
    rows=[];meta=[]
    for hold,press,before in entries:
        row=np.zeros(length,np.int64);row[:hold]|=K.B_JUMP
        if before=="T":row[:press]|=key
        dslash.strike(row,press);row[press:]|=key
        rows.append(row);meta.append((hold,press,before))
    cmds=np.asarray(rows,np.int64);ro=sim.roll(cmds);off=len(prefix);poly=np.array([[box[0],box[1]],[box[2],box[1]],[box[2],box[3]],[box[0],box[3]]])
    windows=[]
    for q,(hold,press,before) in enumerate(meta):
        pj=off+press+1;flags=ro.flags[q]
        if not np.any(flags[pj:pj+2]&K.F_ATTACKING) or flags[pj-1]&K.F_GROUND:
            continue
        js=[]
        for j in range(pj+PM.ACTIVE[0],min(pj+PM.ACTIVE[1]+1,len(flags))):
            if flags[j]&K.F_GROUND:break
            js.append(j)
        windows.append((q,js))
    # Rollout has no per-frame facing. A requested direction is not
    # proof that the HoldFilter/attack recovery already let her turn.
    # Require both mirrors until the receiving adapter knows the face.
    qs=np.array([q for q,js in windows for _ in js],np.int64);fs=np.array([j for _,js in windows for j in js],np.int64)
    hit=_meets_all(ro.pos[qs,fs],poly) if len(qs) else np.zeros(0,bool)
    candidates=[];i=0
    for q,js in windows:
        first=np.flatnonzero(hit[i:i+len(js)]);i+=len(js)
        if len(first):
            hold,press,before=meta[q]
            row=cmds[q].copy();row.setflags(write=False)
            candidates.append(NearVaultProposal(hold,press,before,direction,js[int(first[0])],row))
    candidates.sort(key=lambda x:(x.contact_index,x.press,x.hold,x.before))
    return tuple(candidates[:max_results]),{"status":"nominal_proposals" if candidates else "no_nominal_contact",
        "generated":len(rows),"contact_rows":len(candidates),"returned":min(len(candidates),max_results),
        "ms":(time.perf_counter()-started)*1000.,"admission_checked":False,"external_path_checked":False}
