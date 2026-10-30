"""Prepared post-bounce COMMAND candidates, never cached safety certificates.

Only keys and their causal instance/version travel between ticks. Each query
steps the current table once, requires its first key to match, rerolls every
physics frame from the current start/prefix/Hold, and requires modeled ground
control at handback. The caller always queries the current complete geometry.
Future feedback choices can differ from a freshly interpreted future: these are
MPC candidates (like CONTINUE), not a claim of full closed-loop equivalence.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from ssbot.knowledge import kinematics as km
from .knife_chain_format import MASK_NAMES
from .knife_chain_nominal import (NominalPath,NominalProfile,NominalUnsupported,
    logical_copy,begin_post_branch)
from .knife_chain_step import NominalStepper

KINDS=("left_landing","right_landing","dash_out")


@dataclass(frozen=True)
class PostKeys:
    move: object
    kind: str
    source_frame: int
    origin: int
    commands: np.ndarray
    queued_next: int
    table_digest: str
    profile: NominalProfile

    @classmethod
    def from_path(cls,path,*,move,kind,source_frame,table_digest,profile):
        if kind not in KINDS or path.stage!="continuation" or path.end!="handback" or len(path.commands)<2:
            raise NominalUnsupported("post template lacks an offered action/handoff")
        commands=np.asarray(path.commands,np.int64).copy()
        if np.any(commands&MASK_NAMES["CLAW"]):raise NominalUnsupported("post template contains unsupported hook motion")
        commands.flags.writeable=False
        return cls(move,kind,int(source_frame),path.origin,commands,int(path.queued_next),table_digest,profile)


def reroll_post(template,seed,raw,sim,game,*,move,kind,frame,profile,first_mask,
                continuing=False,observed_history=None,known_press=None):
    """Use only a causal key template; never its old positions or verdict."""
    if (template.move!=move or template.kind!=kind or template.source_frame>frame or
            template.table_digest!=seed.binding["table_digest"] or template.profile!=profile):
        raise NominalUnsupported("prepared post identity/version differs")
    if sim.fo!=sim.f or len(sim.prefix)!=1:raise NominalUnsupported("prepared post needs current one-key prefix")
    # Absolute mask-frame slots. No guessed releases, neutral padding, shifting
    # an old clock to a more favorable window or fresh pogo events.
    off=sim.f-template.origin+1
    if off<1 or off>=len(template.commands):raise NominalUnsupported("prepared post does not cover next offered frame")
    R=logical_copy(seed)
    if observed_history is not None:R.anchor.hist=observed_history
    if not continuing:R,first_mask=begin_post_branch(R,raw,sim,game,kind)
    if R.run is None or R.run.v["iid"]!=move.target_iid or int(R.run.v["fa"])!=move.antic_frame:
        raise NominalUnsupported("prepared post live Run instance differs")
    if int(first_mask)!=int(template.commands[off]):
        raise NominalUnsupported("prepared post first key differs from current table")
    commands=np.r_[np.asarray(sim.prefix,np.int64),template.commands[off:]]
    if len(commands)>profile.max_frames:raise NominalUnsupported("prepared post exceeds existing horizon")
    from .holdfilter import hold_filter_jit
    latched,hold=hold_filter_jit(commands[None,:],sim.hold)
    latched=latched[0]
    states,box,pos,flags,games=NominalStepper(sim.params,sim.terrain).trace(sim.start,latched,game)
    grounded=np.flatnonzero(((flags&km.F_GROUND)!=0)&((flags&km.F_NO_INPUT)==0)&(np.arange(len(flags))>=2))
    if not len(grounded):raise NominalUnsupported("prepared post has no modeled ground handoff; regenerate")
    n=int(grounded[0])
    next_key=int(commands[n]) if n<len(commands) else template.queued_next
    if n<len(commands):
        commands=commands[:n];latched,hold=hold_filter_jit(commands[None,:],sim.hold);latched=latched[0]
    assumptions={"projection":"prepared_table_keys_rerolled","template_source":template.source_frame,
        "template_origin":template.origin,"move":vars(move),"kind":kind,"first_key":"fresh table step",
        "initial_state":"current model/prefix/Hold" if sim.f==frame else "conditional bounce model/prefix/Hold",
        "projection_origin":sim.f,"actual_decision_frame":frame,"handoff":"modeled ground and input",
        "old_positions_reused":False,"safety_reused":False,"events":"none; observed/model start protection only"}
    return NominalPath(sim.f,"continuation",commands.copy(),latched.copy(),states[:,:n+1].copy(),box[:n+1].copy(),
        pos[:n+1].copy(),flags[:n+1].copy(),flags[:n+1].copy(),games[:n+1].copy(),hold,None,None,next_key,
        "handback",known_press,None,assumptions,first_draft=R)
