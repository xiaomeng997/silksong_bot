"""Training glue between the oracle episode loop (train/episode.py) and the safety supervisor (M2 W5): per STATE,
build the SupervisorInput (support from a caller-provided callable), step the Supervisor, and while a pause is pending
or under way run the pause loop and quit sequence, whose keys replace the policy's action.

    sc = SupervisedControl(support=lambda s: entity_support(s, worst_damage=2),
                           cfg=SupervisorConfig(worst_known_damage=2))       # Bell Beast: every hit is 2 masks
    sc.reset()                                     # every episode, once the random start is done
    every STATE s:
        mask, d, outcome = sc.step(s)              # planner fields (plan_s, forced_risk, ...) as keywords (W4)
        link.act(s["f"] + 2, policy.act(s, tap) if mask is None else mask, hold_frames=0)
        if outcome is not None and outcome in TERMINAL: end the episode (QUIT for the emulated quits)

Why each piece:
- support: a callable STATE -> events (certified), (events, known) or None (unknown). Unknown support is never safe
  (cross-module decision 4): the supervisor then adds an event of max(1, the encounter's worst known damage) and keeps
  the tier below GREEN. entity_support() is the stand-in until the W3 forecaster: one event per damaging entity root
  (instance = iid, so the body's colliders are one instance; hidden roots such as the Bell Beast underground count, it
  can emerge), reported unknown unless the caller certifies it. Bell Beast's worst known damage is 2: all 11 676
  "damage" events in Bone_05 of the trial and live runs (20261001_121446, 20261001_122249) are 2 masks, ENEMY, flags
  None, from the body's colliders, the attack bells and six DropBells.
- the pause machine runs with emulate_quit (training never quits for real: a confirmed pause ends the attempt as
  QUIT_EMULATED, or QUIT_EMULATED_GREYED / REFUSED_EMULATED / QUIT_EMULATED_UNKNOWN when the real quit would have been
  greyed, refused or unreadable), and with always_quit every supervisor pause (Q5 / Q7 / Q8 included) ends the attempt:
  there is no frozen-state check to resume with before the W3 tubes exist.
- the clock is the STATE's end-of-frame QPC (s["q"]); keys are held from that frame (the harness applies them at
  frame + 2, so PauseQuitConfig's input_latency_max_s must cover 2-3 frames plus the oracle DelayLine).
- STATE "focus" counts only with a foreground sink (Q7): TRAIN instances run unfocused under OracleInjectSink.
- PauseWindowMonitor measures every hit's Q1 pause window [disablePause cleared, i-frames end] and alerts when one is
  shorter than detection + loop latency (DESIGN §3.7.5).
"""
from collections.abc import Callable, Mapping, Sequence
from typing import NamedTuple

from ssbot.ipc.ents import HAZARD_TYPES
from ssbot.ipc.framing import BIT
from ssbot.safety.hits_to_death import SupportEvent
from ssbot.safety.pause_quit import GOAL_PAUSE, GOAL_QUIT, PauseQuit, PauseQuitConfig, cues_from_state, to_mask
from ssbot.safety.pause_window import PauseWindowMonitor
from ssbot.safety.supervisor import Supervisor, SupervisorConfig, SupervisorDecision, input_from_state

SupportResult = Sequence[SupportEvent] | tuple[Sequence[SupportEvent], bool] | None
SupportFn = Callable[[dict], SupportResult]

_I_FRAME_BLOCKED = frozenset(i for i, n in enumerate(HAZARD_TYPES) if n in ("NON_HAZARD", "ENEMY", "EXPLOSION"))


class Supervised(NamedTuple):
    mask: int | None                 # ACTION mask replacing the policy's (None: the policy acts)
    decision: SupervisorDecision
    outcome: str | None              # PauseQuit outcome once the pause machine has one (pause_quit.TERMINAL, ...)


def entity_support(s: dict, worst_damage: int = 1, known: bool = False) -> tuple[tuple[SupportEvent, ...], bool]:
    """Stand-in support from STATE ents: one event per entity root that can hurt now (an enabled collider with damage)
    or that is a hidden HealthManager root (ents[].hidden: it can come back), damage max(its colliders' damage,
    worst_damage), hazard when a collider's hazard type passes i-frames. Not a validated superset of what can land
    within the horizon, so it is reported unknown unless `known`."""
    out = []
    for e in s.get("ents") or ():
        dmg, hazard, threat = 0, False, bool(e.get("hidden"))
        for c in e.get("colliders") or ():
            d = c.get("damage")
            if not (c.get("enabled") and d and d.get("can_cause_damage")):
                continue
            threat = True
            dmg = max(dmg, int(d.get("dealt") or 0), int(d.get("eff") or 0))
            hazard |= d.get("hazard_type") is not None and d["hazard_type"] not in _I_FRAME_BLOCKED
        if threat:
            out.append(SupportEvent(str(e.get("type_key")), max(dmg, worst_damage, 1), hazard=hazard,
                                    instance=e.get("iid")))
    return tuple(out), known


class SupervisedControl:
    def __init__(self, support: SupportFn | None = None, cfg: SupervisorConfig | None = None,
                 pq_cfg: PauseQuitConfig | None = None, bit: Mapping[str, int] = BIT, foreground_sink: bool = False,
                 always_quit: bool = True, qpc_freq: float = 1e7):
        self.support = support
        self.cfg = cfg or SupervisorConfig()
        self.pq_cfg = pq_cfg or PauseQuitConfig(emulate_quit=True)
        self.bit = bit
        self.foreground_sink = foreground_sink
        self.always_quit = always_quit
        self.qpc_freq = qpc_freq
        self.reset()

    def reset(self) -> None:
        """A new attempt."""
        self.sup = Supervisor(self.cfg)
        self.pq: PauseQuit | None = None
        self.windows = PauseWindowMonitor(qpc_freq=self.qpc_freq)
        self.t0: float | None = None
        self.first_pending_f: int | None = None

    def _support(self, s: dict) -> tuple[Sequence[SupportEvent] | None, bool | None]:
        if self.support is None:
            return None, None
        r = self.support(s)
        if r is None:
            return None, False
        if isinstance(r, tuple) and len(r) == 2 and isinstance(r[1], bool):
            return tuple(r[0]), r[1]
        return tuple(r), True

    def step(self, s: dict, **planner) -> Supervised:
        t_q = (s.get("q") or 0) / self.qpc_freq
        if self.t0 is None:
            self.t0 = t_q
        events, known = self._support(s)
        inp = input_from_state(s, t_q - self.t0, support=events, support_known=known,
                               foreground_sink=self.foreground_sink, **planner)
        d = self.sup.step(inp)
        self.windows.update(s)
        pq = self.pq
        if pq is None and d.pause_pending:
            pq = self.pq = PauseQuit(self.pq_cfg)
            pq.start(t_q, GOAL_QUIT if d.quit_requested or self.always_quit else GOAL_PAUSE)
            self.first_pending_f = s.get("f")
        elif pq is not None and d.quit_requested and pq.goal != GOAL_QUIT:
            pq.upgrade_to_quit(t_q)
        if d.stop_input:
            return Supervised(0, d, None if pq is None else pq.outcome)
        if pq is None:
            return Supervised(None, d, None)
        keys = pq.step(cues_from_state(s, self.qpc_freq))
        if pq.confirmed and not self.sup.paused:
            self.sup.notify_paused()
        return Supervised(to_mask(keys, self.bit), d, pq.outcome)
