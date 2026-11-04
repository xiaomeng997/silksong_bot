"""HP responsibility after a sent action or its observed own bounce tail fails.

This is observation bookkeeping, never an action selector, a damage predictor or
an enemy timer. The caller must have a successful-send record, or an actual own
DownSlash hit+bounce joined to that action before a tail admission is declined.
A declined tail is not a new send, accepted attack or predicted-hit receipt. Unknown target/end observations keep it open; frame count alone cannot
end a slam. Actual FSM/game-time evidence, not frame - state_time*60, identifies a
later slam so hit-stop/frozen game time cannot relabel this instance.
"""
from __future__ import annotations

from dataclasses import dataclass,field
import math
from .knife_chain_commitment import MoveInstance

_SLAM_STATES=frozenset({"Slam Antic","Slam 0","Slam 1","Slam Effects?","Slam 2","Slam Recover"})
_JUMP_CAST_STATES=frozenset({"Cast Slam Antic","Cast Slam Antic 2","Cast Jump","Jump Aim","Jump","Air",
                            "Charged?","Slam Effects?","Slam 2","Slam Recover"})
_FAMILIES={"CC_SLAM":(_SLAM_STATES,"Slam Antic"),
           "CC_JUMP_CAST":(_JUMP_CAST_STATES,"Cast Slam Antic"),
           "CC_CAST":(frozenset({"Spell Antic","Cast 1","Cast 2"}),"Spell Antic")}
# Same clock-identity uncertainty already used by the h2 B2 observer. This is
# identity evidence only: it never changes a hazard/protection/attack window.
_CLOCK_IDENTITY_SLOP=3./60.


def _frame(value):
    if type(value) is not int or value<0:raise ValueError("frame must be a nonnegative integer")


def _number(value):
    return type(value) in (int,float) and math.isfinite(value)


@dataclass
class FailureExposure:
    """Observed source responsibility after an executed action or own bounce-tail failure.

    With an observed end E, active through max(E, failed_frame+30), inclusive.
    Without E, stays active indefinitely. Death supplies observed end evidence;
    it does not silently shorten the 30-frame minimum. This does not classify a
    particular collider as the cause of injury or change tail accounting.
    """
    move: MoveInstance
    origin: int
    failed_frame: int
    ta: float | None
    observed_end_frame: int | None=field(default=None,init=False)
    observed_end_reason: str | None=field(default=None,init=False)
    observed_end_source: str | None=field(default=None,init=False)
    last_frame: int | None=field(default=None,init=False)
    last_control: str | None=field(default=None,init=False)
    last_game_time: float | None=field(default=None,init=False)
    new_antic_entry_time: float | None=field(default=None,init=False)
    unknown_reason: str | None=field(default="same-move end not observed",init=False)
    _seen_non_antic: bool=field(default=False,init=False,repr=False)
    _clock_uncertain: bool=field(default=False,init=False,repr=False)

    def __post_init__(self):
        if not isinstance(self.move,MoveInstance) or self.move.family not in _FAMILIES:
            raise ValueError("failure exposure requires a supported observed move family")
        _frame(self.origin);_frame(self.failed_frame)
        if self.origin<self.move.antic_frame or self.failed_frame<self.origin:
            raise ValueError("failure exposure precedes its sent move/origin")
        if self.ta is not None and not _number(self.ta):raise ValueError("invalid antic game-time origin")
        if self.ta is not None:self.ta=float(self.ta)

    @property
    def minimum_through(self):
        return self.failed_frame+30

    @property
    def through(self):
        return None if self.observed_end_frame is None else max(self.minimum_through,self.observed_end_frame)

    def active(self,frame):
        _frame(frame)
        return frame>=self.origin and (self.through is None or frame<=self.through)

    def _end(self,frame,reason,source):
        self.observed_end_frame=frame
        self.observed_end_reason=reason;self.observed_end_source=source
        self.unknown_reason=None

    def observe(self,state,game_time=None):
        """Accept a causal actual STATE, return self; never infer a missing end.

        game_time, when given, must be the caller's actual cumulative game clock
        on the same lane as ta. Unscaled/render time is not a substitute. Missing,
        malformed, duplicate or older observations cannot close this exposure.
        """
        if not isinstance(state,dict) or type(state.get("f")) is not int or state["f"]<self.origin:
            self.unknown_reason="invalid/older observation frame";return self
        f=state["f"]
        if self.last_frame is not None and f<=self.last_frame:return self
        self.last_frame=f
        if self.observed_end_frame is not None:return self # never bind/extend to a later move
        current_game=float(game_time) if _number(game_time) else None
        clock_regressed=(current_game is not None and self.last_game_time is not None
                         and current_game<self.last_game_time-_CLOCK_IDENTITY_SLOP)
        if clock_regressed:self._clock_uncertain=True
        if current_game is not None:self.last_game_time=current_game
        # A visible dead entity or an actual observed killing hit is end evidence.
        # Missing/removed entities alone are not: ents=None can be a reporting gap.
        for ev in state.get("ev") or ():
            if not isinstance(ev,dict):continue
            d=ev.get("d") or {}
            ef=ev.get("f",f)
            event_iid=(d.get("ent") if type(d.get("ent")) is int else d.get("iid")) if isinstance(d,dict) else None
            if (isinstance(d,dict) and ev.get("k")=="hit" and d.get("dead") is True
                    and type(event_iid) is int and event_iid==self.move.target_iid
                    and type(ef) is int and self.origin<=ef<=f):
                self._end(f,"target death observed","actual killing hit");return self
        matches=[e for e in state.get("ents") or () if isinstance(e,dict)
                 and type(e.get("iid")) is int and e["iid"]==self.move.target_iid]
        if len(matches)!=1:
            self.unknown_reason="target observation missing or ambiguous";return self
        e=matches[0];hp=e.get("hp")
        if e.get("is_dead") is True or (_number(hp) and hp<=0):
            self._end(f,"target death observed","actual target is_dead/HP");return self
        controls=[fs for fs in e.get("fsms") or () if isinstance(fs,dict) and fs.get("name")=="Control"]
        if len(controls)!=1 or not isinstance(controls[0].get("state"),str) or not controls[0]["state"]:
            self.unknown_reason="target Control state unavailable";return self
        st=controls[0]["state"];tin=controls[0].get("t")
        states,primary=_FAMILIES[self.move.family]
        if st not in states:
            self.last_control=st
            source={"CC_SLAM":"actual Control left slam states","CC_JUMP_CAST":"actual Control left jump-cast states",
                    "CC_CAST":"actual Control left small-rune cast states"}[self.move.family]
            self._end(f,"same-move end observed",source);return self
        if st==primary:
            if self._clock_uncertain:
                self.unknown_reason="game clock regressed; antic identity unknown"
            else:
                entry=current_game-float(tin) if current_game is not None and _number(tin) and tin>=0 else None
                if entry is not None and self.ta is not None and entry>self.ta+_CLOCK_IDENTITY_SLOP:
                    self.new_antic_entry_time=entry
                    self._end(f,"new "+primary+" observed","actual game_time minus Control.t");return self
                if self._seen_non_antic:
                    self.new_antic_entry_time=entry
                    source="observed slam phase returned to Antic" if self.move.family=="CC_SLAM" else "observed jump-cast phase returned to Antic"
                    self._end(f,"new "+primary+" observed",source);return self
                self.unknown_reason=("antic clock before bound instance; end unknown" if entry is not None
                    and self.ta is not None and entry<self.ta-_CLOCK_IDENTITY_SLOP else "same-move end not observed")
        else:
            self._seen_non_antic=True
            self.unknown_reason="same-move end not observed"
        self.last_control=st
        return self

    def as_dict(self):
        return {"move":{"target_iid":self.move.target_iid,"antic_frame":self.move.antic_frame,"family":self.move.family},
            "origin":self.origin,"failed_frame":self.failed_frame,"ta":self.ta,
            "minimum_through":self.minimum_through,"through":self.through,
            "end_status":"unknown" if self.observed_end_frame is None else "observed",
            "observed_end_frame":self.observed_end_frame,"observed_end_reason":self.observed_end_reason,
            "observed_end_source":self.observed_end_source,"last_frame":self.last_frame,
            "last_control":self.last_control,"last_game_time":self.last_game_time,
            "clock_identity_uncertain":self._clock_uncertain,
            "new_antic_entry_time":self.new_antic_entry_time,"unknown_reason":self.unknown_reason,
            "scope":"HP responsibility only; not collider causality, action acceptance or safety"}
