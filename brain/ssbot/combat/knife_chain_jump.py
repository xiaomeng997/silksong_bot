"""Evidence-only watch for the FIRST planned jump from ground.

No keys, physics, recovery, HP policy or retry decisions live here. The owner
binds this object to one Move and feeds successful sends, never a held/predicted
receipt. Later umbrella J blocks cannot extend or rescue the initial jump.
"""
from __future__ import annotations
from dataclasses import dataclass,field
import numpy as np
from ssbot.knowledge import kinematics as km
from .knife_chain_format import MASK_NAMES as B
from .knife_chain_nominal import state_names


def _observed_flag(state,name):
    """Tri-state: missing cState data is unknown, never observed airborne."""
    names=state_names()
    if name not in names:return None
    bits=((state or {}).get("hero") or {}).get("cstate")
    index=names.index(name);word=index//64
    if not isinstance(bits,(list,tuple)) or len(bits)<=word:return None
    value=bits[word]
    if not isinstance(value,(int,np.integer)) or isinstance(value,(bool,np.bool_)):return None
    return bool((int(value)>>(index%64))&1)


@dataclass
class JumpStartWatch:
    move: object
    origin: int
    targets: tuple[int,...]
    sent_targets: set[int]=field(default_factory=set)
    seen_frame: int | None=None

    @classmethod
    def from_path(cls,path,move,origin,receipts):
        """A ground-start path's first contiguous desired-J block, or None.

        Path flags are model evidence ONLY for identifying the proposed first
        ground jump. Only observe() can credit actual takeoff. A path starting
        airborne, or whose first J is already airborne, does not require a new
        ground jump (in particular, do not reinterpret its umbrella as one).
        `receipts` must be the owner's successful-send map {target: desired}.
        """
        if type(origin) is not int or origin<0:raise ValueError("invalid jump-watch origin")
        commands=np.asarray(path.commands)
        flags=np.asarray(path.flags)
        if commands.ndim!=1 or flags.ndim!=1 or len(flags)!=len(commands)+1:
            raise ValueError("jump-watch path coverage differs")
        if not len(commands) or not int(flags[0])&km.F_GROUND:return None
        first=next((i for i,m in enumerate(commands) if int(m)&B["J"]),None)
        if first is None or not int(flags[first])&km.F_GROUND:return None
        end=first+1
        while end<len(commands) and int(commands[end])&B["J"]:end+=1
        targets=tuple(int(path.origin)+i+1 for i in range(first,end))
        watch=cls(move,origin,targets)
        for target,mask in (receipts or {}).items():watch.record_send(target,mask)
        return watch

    def record_send(self,target,mask):
        """Record a successful desired-J send in the first block, not acceptance."""
        if type(target) is not int or type(mask) is not int:raise ValueError("invalid successful jump send")
        if target in self.targets and mask&B["J"]:
            self.sent_targets.add(target)
            return True
        return False

    def observe(self,state):
        """Return True once for explicit actual airborne after an own J target."""
        if self.seen_frame is not None or not self.sent_targets:return False
        f=(state or {}).get("f")
        if type(f) is not int or f<max(self.origin,min(self.sent_targets)):return False
        if f>max(self.sent_targets)+4:return False  # a first late observation cannot revive an expired jump
        if _observed_flag(state,"dead") or _observed_flag(state,"hazardDeath"):return False
        if _observed_flag(state,"onGround") is False:
            self.seen_frame=f
            return True
        return False

    def failure(self,frame):
        """No shifts/retries: missing original block or no takeoff after T+4."""
        if type(frame) is not int or frame<0:raise ValueError("invalid jump decision frame")
        if self.seen_frame is not None:return None
        if not self.sent_targets:
            if frame+2>max(self.targets):return "planned ground-jump window elapsed without successful J send"
        elif frame>max(self.sent_targets)+4:
            return "sent J had no observed airborne within four-frame upper bound"
        return None


def grounded_strike(state,press):
    """Observed ground Slash under THIS applied D|A, not an idle-ground guess.

    This stateless helper requires the current report to bind the successful
    planned strike target. A later report with no such binding remains unknown;
    the owner may separately use its action-acceptance history. Sending/receipts
    alone cannot prove this defect: ground + attacking + Slash animation must
    also be observed. DownSlash landing/recovery is not ordinary ground Slash.
    """
    f=(state or {}).get("f")
    if type(press) is not int or type(f) is not int or f<press:return False
    if _observed_flag(state,"onGround") is not True or _observed_flag(state,"attacking") is not True:return False
    hero=(state or {}).get("hero") or {};clip=str((hero.get("anim") or {}).get("clip") or "")
    if not clip.startswith("Slash"):return False
    act=(state or {}).get("act") or {};hf=act.get("hf") or {}
    applied=act.get("applied");desired=hf.get("desired");latched=hf.get("latched",act.get("mask"))
    if act.get("target")!=press or type(applied) is not int or not press<=applied<=f:return False
    if type(desired) is not int or type(latched) is not int:return False
    down_attack=B["D"]|B["A"]
    return desired&down_attack==down_attack and latched&down_attack==down_attack
