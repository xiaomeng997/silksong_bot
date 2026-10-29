"""Full hit paths and a shared post-bounce exit for experimental knife rows.

Not connected to append_rows until contact/geometry/continuation gates pass.
Never checks a missed strike or replaces the planned strike with an H abort.
"""
from dataclasses import dataclass
import numpy as np
from ssbot.knowledge import kinematics as km
from ssbot.map2 import oldwin_claw as claw


def hit_events(base, first, last, length=None):
    """Cover every integer first-contact time in every modeled hook outcome."""
    n=len(base.hooks);first=np.asarray(first,np.int64);last=np.asarray(last,np.int64)
    length=len(base.commands) if length is None else int(length)
    if (first.shape!=(n,) or last.shape!=(n,) or np.any(first>last)
            or np.any(first<=base.control_frames) or np.any(last>length)):
        raise ValueError("unsupported first-contact interval")
    for k in range(int(first.min()),int(last.max())+1):
        contact=np.clip(k,first,last)
        events=np.zeros((n,length),np.int64)
        events[np.arange(n),contact-1]=km.EV_POGO
        yield contact,events


def full_contacts(planner, forecast, rollout, *, start=0, escape=False):
    """Same hull sampler/width rejection, including the first queried frame."""
    from ssbot.combat.planner import _hull_points
    bound=rollout.bound[:,start:];flags=rollout.flags_all[:,start:]
    tk=np.arange(start,start+bound.shape[1])*planner.params.frame_time
    hx,hy=forecast.fc.half
    x,y,rows,wide=_hull_points(np.ascontiguousarray(bound),hx,hy,planner.cfg.max_points)
    hit=(forecast.rs.occupied_esc(x,y,tk) if escape else forecast.occupied(x,y,tk,False))
    if hit is None:raise ValueError("occupancy unavailable")
    n=len(bound);occ=hit[:n].copy()
    if len(rows):occ[rows]|=hit[n:].reshape(-1,len(rows),hit.shape[1]).any(axis=0)
    occ|=wide
    occ &= (flags&km.F_INVULN)==0
    return occ


@dataclass
class HitExit:
    start: int
    through: int
    option: int
    raw: np.ndarray
    latched: np.ndarray
    paths: list
    contacts: list


def common_escape(planner, forecast, base, first, last, raw, hold, *, audit=None):
    """Re-roll the full original prefix, pogo and exit; never restart protection.

    The common exit begins at J after the latest possible bounce. Retain every
    contact time, the hook's recovery states and all BOUNDS lanes at each time.
    A shared command must pass for every outcome. No across-tick verdict cache.
    """
    from ssbot.combat.holdfilter import hold_filter_jit
    raw=np.asarray(raw,np.int64)
    if raw.shape!=base.commands.shape:raise ValueError("raw/fixed command length mismatch")
    wire,_=hold_filter_jit(raw[None],hold)
    if not np.array_equal(wire[0],base.commands):raise ValueError("latched prefix mismatch")
    events=list(hit_events(base,first,last))
    branches=[claw.with_events(base,planner.params,planner.terrain,ev,threads=planner.cfg.threads)
              for _,ev in events]
    # Start only after every bounce and once all modeled outcomes accept input.
    j=int(np.max(last))+1
    while j<len(raw) and any(np.any(r.flags_any[:,j]&(km.F_NO_INPUT|km.F_RELINQ)) for r in branches):j+=1
    if j>=len(raw):raise ValueError("no supported post-bounce input edge")
    length=max(24,len(raw)-j);through=j+length
    if max(forecast.rs.samples)+forecast.rs.k_shift<through:
        raise ValueError("post-hit escape support horizon unavailable")
    if audit is not None:audit.update(start=j,through=through,contact_cases=len(events),options=[])
    # An exit cannot repair an unsafe approach. This covers frame zero, hook,
    # strike and bounce; no miss branch is examined.
    for ro in branches:
        prefix=full_contacts(planner,forecast,ro)[:,:j+1]
        if prefix.any():
            if audit is not None:audit["prefix_unsafe"]=np.flatnonzero(prefix.any(axis=0)).tolist()
            return None
    for option,suffix in enumerate(planner._esc_cmds(length)):
        full=np.concatenate((raw[:j],suffix))
        latched,_=hold_filter_jit(full[None],hold);latched=latched[0]
        if not np.array_equal(latched[:j],base.commands[:j]):raise ValueError("exit changed strike prefix")
        paths=[];fail=[]
        for contact,_ in events:
            ev=np.zeros((len(base.hooks),through),np.int64)
            ev[np.arange(len(base.hooks)),contact-1]=km.EV_POGO
            ro=claw.with_events(base,planner.params,planner.terrain,ev,threads=planner.cfg.threads,commands=latched)
            occ=full_contacts(planner,forecast,ro)
            esc=full_contacts(planner,forecast,ro,start=j,escape=True)
            bad=np.union1d(np.flatnonzero(occ.any(axis=0)),j+np.flatnonzero(esc.any(axis=0)))
            fail.extend(map(int,bad));paths.append(ro)
        if audit is not None:audit["options"].append(dict(option=option,unsafe_frames=sorted(set(fail))))
        if not fail:return HitExit(j,through,option,full,latched,paths,[c for c,_ in events])
    return None
