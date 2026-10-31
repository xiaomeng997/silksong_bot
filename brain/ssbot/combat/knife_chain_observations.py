"""Actual B2 pogo observations; no model, controller or mutable hit history.

A DownSlash event is not by itself proof of an actual bounce. These helpers only
read the supplied STATE. A controller retaining a press-bound earlier hit must
join that history to pogo_marker separately, never invent another hit event.
"""
from __future__ import annotations
from functools import lru_cache
from ssbot.knowledge import kinematics as kin


@lru_cache(maxsize=1)
def _pogo_bits():
    names=kin.cstate_names()
    return tuple(divmod(names.index(name),64) for name in
                 ("downSpikeBouncing","downSpikeBouncingShort") if name in names)


def pogo_marker(state) -> bool:
    """Observed bounce bit or a positive downspikeInvulnerabilitySteps counter.

    Velocity, an animation name, an intended key and generic damage invulnerability
    do not identify a pogo. Unknown/malformed observation lanes provide no proof.
    """
    if not isinstance(state,dict):return False
    hero=state.get("hero")
    if not isinstance(hero,dict):return False
    counters=hero.get("cstate_int")
    if isinstance(counters,(list,tuple)) and len(counters)>1:
        value=counters[1]
        if type(value) is int and value>0:return True
    words=hero.get("cstate")
    if isinstance(words,(list,tuple)):
        for lane,bit in _pogo_bits():
            if lane<len(words) and type(words[lane]) is int and ((words[lane]>>bit)&1):return True
    return False


def target_pogo_hit(state, iid, *, since=None) -> bool:
    """A causal target DownSlash hit AND a marker in this supplied STATE.

    since is an optional inclusive absolute hit-event frame lower bound (e.g.
    the actual planned press). Events after STATE.f never count. A hit missing
    its own frame uses the enclosing known STATE frame, as the existing oracle
    event reader does; an explicitly invalid frame is unknown and rejected.
    No cross-STATE history is retained and no hit is inferred from the marker.
    """
    if iid is None or not pogo_marker(state):return False
    frame=state.get("f")
    if type(frame) is not int or (since is not None and type(since) is not int):return False
    if since is not None and since>frame:return False
    events=state.get("ev")
    if not isinstance(events,(list,tuple)):return False
    for event in events:
        if not isinstance(event,dict) or event.get("k")!="hit":continue
        data=event.get("d")
        if not isinstance(data,dict):continue
        target=data.get("ent") if data.get("ent") is not None else data.get("iid")
        source=data.get("src")
        if target!=iid or not isinstance(source,str) or "DownSlash" not in source or "Harpoon" in source:continue
        ef=event.get("f",frame)
        if type(ef) is int and ef<=frame and (since is None or ef>=since):return True
    return False
