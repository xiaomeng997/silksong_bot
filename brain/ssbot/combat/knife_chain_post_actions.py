"""Ordinary left/right/dash candidates at a conditional bounce; never an input owner.

The N=2 policy counts executable action TYPES, not future script decisions.
These are ordinary commanded-key rows stepped by the original HERO2/HoldFilter.
No state, event, target admission or safety verdict is shared across queries.
Actual bounce arbitration and real chain execution are unchanged.
"""
import numpy as np
from ssbot.knowledge import kinematics as km
from .knife_chain_nominal import NominalPath,NominalUnsupported,NominalProfile
from .knife_chain_step import NominalStepper
from .holdfilter import hold_filter_jit
from .knife_chain_format import MASK_NAMES as B


def ordinary_post(parent,params,terrain,*,kind,profile=None,full=False):
    profile=profile or NominalProfile()
    if parent.end!="bounce" or parent.stage!="commitment":
        raise NominalUnsupported("ordinary post needs conditional bounce")
    if kind not in {"left_landing","right_landing","dash_out"}:
        raise ValueError("unknown ordinary post type")
    origin=parent.through;frames=profile.max_frames if full else profile.short_frames
    if kind=="left_landing":direction=B["L"]
    elif kind=="right_landing":direction=B["R"]
    else:
        target=next((e for e in parent.raw_end.get("ents") or () if e.get("iid")==parent.runner_end.run.v["iid"]),None)
        if target is None or not target.get("pos"):
            raise NominalUnsupported("ordinary dash needs observed modeled target side")
        direction=B["R"] if parent.states[km.PX,-1]>=float(target["pos"][0]) else B["L"]
    commands=np.full(frames,direction,np.int64)
    commands[0]=parent.queued_next
    if kind=="dash_out":commands[1:min(frames,3)]|=B["DASH"]
    latched,hold=hold_filter_jit(commands[None,:],parent.hold_end);latched=latched[0]
    states,box,pos,flags,games=NominalStepper(params,terrain).trace(parent.states[:,-1],latched,parent.game[-1])
    ground=np.flatnonzero(((flags&km.F_GROUND)!=0)&((flags&km.F_NO_INPUT)==0)&(np.arange(len(flags))>=2))
    end="handback" if len(ground) else "short"
    n=int(ground[0]) if len(ground) else frames
    if full and not len(ground):raise NominalUnsupported("ordinary post has no ground/input handback within original horizon")
    next_key=int(commands[n]) if n<len(commands) else direction
    if n<len(commands):
        commands=commands[:n];latched,hold=hold_filter_jit(commands[None,:],parent.hold_end);latched=latched[0]
    return NominalPath(origin,"continuation",commands.copy(),latched.copy(),states[:,:n+1].copy(),
        box[:n+1].copy(),pos[:n+1].copy(),flags[:n+1].copy(),flags[:n+1].copy(),games[:n+1].copy(),
        hold,None,None,next_key,end,parent.press_frame,None,
        {"projection":"ordinary_post_action_type","kind":kind,"input_owner":False,
         "events":"none","start":"conditional bounce/prefix/Hold","full":full},first_draft=None)
