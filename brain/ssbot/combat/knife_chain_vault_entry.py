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


def near_proposals(sim, target_box, direction, *, max_results=2):
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
    holds=(14,20);presses=range(4,25);length=max(presses)+dslash.POST_F
    rows=[];meta=[]
    for hold in holds:
        for press in presses:
            for before in ("T","N"):
                row=np.zeros(length,np.int64);row[:hold]|=K.B_JUMP
                if before=="T":row[:press]|=key
                dslash.strike(row,press);row[press:]|=key
                rows.append(row);meta.append((hold,press,before))
    cmds=np.asarray(rows,np.int64);ro=sim.roll(cmds);off=len(prefix);poly=np.array([[box[0],box[1]],[box[2],box[1]],[box[2],box[3]],[box[0],box[3]]])
    candidates=[]
    for q,(hold,press,before) in enumerate(meta):
        pj=off+press+1;flags=ro.flags[q]
        if not np.any(flags[pj:pj+2]&K.F_ATTACKING) or flags[pj-1]&K.F_GROUND:
            continue
        for j in range(pj+PM.ACTIVE[0],min(pj+PM.ACTIVE[1]+1,len(flags))):
            if flags[j]&K.F_GROUND:break
            if all(PM.meets(PM.slash_poly(direction,alt)+ro.pos[q,j],poly) for alt in (False,True)):
                row=cmds[q].copy();row.setflags(write=False)
                candidates.append(NearVaultProposal(hold,press,before,direction,j,row));break
    candidates.sort(key=lambda x:(x.contact_index,x.press,x.hold,x.before))
    return tuple(candidates[:max_results]),{"status":"nominal_proposals" if candidates else "no_nominal_contact",
        "generated":len(rows),"contact_rows":len(candidates),"returned":min(len(candidates),max_results),
        "ms":(time.perf_counter()-started)*1000.,"admission_checked":False,"external_path_checked":False}
