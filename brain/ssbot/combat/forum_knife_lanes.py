"""Audit-only hit paths retaining each hook outcome and every BOUNDS clock.

Events are per logical lane. Protection is the measured eight physics steps,
not the common h2 timer. Extension always re-rolls from the original control
edge; flags carry the measured protection, final.INV_T is not a new initializer.
"""
from __future__ import annotations
from dataclasses import dataclass,field,replace
import numpy as np
from ssbot.knowledge import kinematics as km
from ssbot.map2 import oldwin_claw as claw


@dataclass(slots=True)
class ClockPaths(claw.ClawRollout):
    hook_indices: np.ndarray | None = None
    clock_indices: np.ndarray | None = None
    clock_names: tuple = ()
    pogo_events: np.ndarray | None = None
    measured_protection: np.ndarray | None = None
    query_index: np.ndarray | None = None
    query_inverse: np.ndarray | None = None
    _query_bound: np.ndarray | None = field(default=None,repr=False)
    _query_flags: np.ndarray | None = field(default=None,repr=False)


def _commands(base,commands):
    if isinstance(base,ClockPaths) or base.commands is None or base.control_frames is None:
        raise ValueError("original hook-level rollout required")
    commands=np.asarray(base.commands if commands is None else commands,np.int64)
    if commands.ndim!=1 or len(commands)<=int(np.max(base.control_frames)):
        raise ValueError("unsupported command horizon")
    from ssbot.ipc.framing import mask
    p=base.launch_frame;claw_mask=mask("clawline")
    previous=np.zeros(len(commands),bool);shared=min(len(commands),len(base.commands))
    previous[:shared]=(base.commands[:shared]&claw_mask)!=0
    if (not np.array_equal(commands[:p],base.commands[:p])
            or not np.array_equal((commands&claw_mask)!=0,previous)):
        raise ValueError("changed hook/prefix")
    for c in base.control_frames:
        if np.any(commands[p:int(c)]&km.B_ATTACK):
            raise ValueError("attack held inside uncancellable hook")
    return commands


def _clock_representatives(params):
    # Only normal time, no hurt/world-freeze events are accepted below. The
    # same unused timer links as km._lane_runs may therefore share computation.
    # This removes no logical clock and does not share different event streams.
    rows,ft,sel=km._variant_rows(params,km.BOUNDS)
    rows=rows.copy()
    rows[:,[km.P_HURT_WAIT,km.P_HURT_RAMP,km.P_WF_BW,km.P_WF_BU]]=0.
    seen={};result=[]
    for v in range(len(km.BOUNDS)):
        key=(rows[v].tobytes(),float(ft[v]),int(sel[v]))
        seen.setdefault(key,v);result.append(seen[key])
    return result


def rollout(base,params,terrain=None,events=None,*,commands=None,threads=1):
    """Return one row per (hook, clock), with its own pogo event stream.

    No cached safety verdict, selected contact time, or per-lane escape keys.
    Commands are a single common latched sequence. Each event row may contain
    at most one pogo after that hook's control edge. Other events are unknown.
    """
    commands=_commands(base,commands)
    n=len(base.hooks);nv=len(km.BOUNDS);length=len(commands);total=n*nv
    if n==0 or len(base.control_frames)!=n:raise ValueError("missing hook outcomes")
    ev=np.zeros((total,length),np.int64) if events is None else np.asarray(events,np.int64)
    if (ev.shape!=(total,length) or np.any(ev&~km.EV_POGO)
            or np.any(np.count_nonzero(ev,axis=1)>1)):
        raise ValueError("one supported pogo stream per logical clock required")
    representatives=_clock_representatives(params);groups={}
    for h,c in enumerate(base.control_frames):
        c=int(c);state=np.asarray(base.control_states[h],float)
        if (state.shape!=(km.K,) or not np.isfinite(state).all()
                or int(state[km.MODE])!=km.M_NORMAL):
            raise ValueError("unsupported recovery state")
        for v,representative in enumerate(representatives):
            q=h*nv+v
            if np.any(ev[q,:c]):raise ValueError("event inside hook/prefix")
            key=(state.tobytes(),ev[q,c:].tobytes())
            groups.setdefault((c,representative),{}).setdefault(key,[]).append(q)
    names=("phys","pos","vel","mode","flags","box","bound","flags_all","flags_any")
    arrays={name:np.empty((total,length+1)+getattr(base,name).shape[2:],getattr(base,name).dtype)
            for name in names}
    final=np.empty((km.K,total));protected=np.zeros((total,length+1),bool)
    for (c,v),unique in groups.items():
        rows=list(unique.values());first=[qs[0] for qs in rows]
        starts=np.stack([base.control_states[q//nv] for q in first],axis=1)
        events_here=np.ascontiguousarray(ev[first,c:])
        # Keep the public component's clock/event validation, including normal
        # time and the measured single-physics-step scope, then pick THIS phase.
        claw.pogo_protection(starts,events_here,params)
        variant=km.BOUNDS[v]
        alpha=(starts[km.ALPHA] if variant.alpha=="est" else
               np.maximum(starts[km.ALO]-params.alpha_margin,0.) if variant.alpha=="lo" else
               starts[km.AHI]+params.alpha_margin)
        protection=claw._pogo_clock(alpha[:,None],events_here,
                                    float(np.float32(params.frame_time)),params.fdt)[:,0]
        masks=np.broadcast_to(commands[c:],(len(first),length-c)).copy()
        motion_params=replace(params,pogo_invul=0.) if events_here.any() else params
        ro=km.rollout(starts,masks,motion_params,terrain,events=events_here,
                      variants=(variant,),threads=threads)
        for j,qs in enumerate(rows):
            for name in names:
                value=getattr(ro,name)
                if value is None:value=ro.box if name=="bound" else ro.flags
                tail=value[j,1:]
                if name=="bound":
                    tail=tail+np.array([-claw.COMPONENT_MARGIN_U]*2+[claw.COMPONENT_MARGIN_U]*2)
                elif name in ("flags","flags_all","flags_any"):
                    tail=tail|np.where(protection[j,1:],km.F_INVULN,0)
                for q in qs:
                    arrays[name][q,:c+1]=getattr(base,name)[q//nv,:c+1]
                    arrays[name][q,c+1:]=tail
            for q in qs:protected[q,c+1:]=protection[j,1:]
            final[:,qs]=ro.final[:,j:j+1]
    # Equal geometry and immunity require the same occupancy query, regardless
    # of clock label. Keep all logical rows; never reuse an occupancy verdict.
    # Read-only arrays and identity checks invalidate this shortcut on replacement.
    seen={};index=[];inverse=[]
    for q in range(total):
        key=(arrays["bound"][q].tobytes(),((arrays["flags_all"][q]&km.F_INVULN)!=0).tobytes())
        if key not in seen:seen[key]=len(index);index.append(q)
        inverse.append(seen[key])
    arrays["bound"].setflags(write=False);arrays["flags_all"].setflags(write=False)
    controls=np.repeat(base.control_frames,nv)
    return ClockPaths(**arrays,final=final,hooks=[h for h in base.hooks for _ in range(nv)],
        control_frames=controls,control_states={q:base.control_states[q//nv].copy() for q in range(total)},
        launch_frame=base.launch_frame,commands=commands.copy(),hook_indices=np.repeat(np.arange(n),nv),
        clock_indices=np.tile(np.arange(nv),n),clock_names=tuple(v.name for v in km.BOUNDS),
        pogo_events=ev.copy(),measured_protection=protected,query_index=np.asarray(index),
        query_inverse=np.asarray(inverse),_query_bound=arrays["bound"],_query_flags=arrays["flags_all"])
