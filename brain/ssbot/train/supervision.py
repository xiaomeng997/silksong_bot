"""Training glue between the oracle episode loop (train/episode.py) and the safety supervisor (M2 W5): per STATE,
build the SupervisorInput (support from a caller-provided callable), step the Supervisor, and while a pause is pending
or under way run the pause loop and quit sequence, whose keys replace the policy's action.

    sc = SupervisedControl(support=lambda s: entity_support(s, worst_damage=2),
                           cfg=SupervisorConfig(worst_known_damage=2))       # Bell Beast: every hit is 2 masks
    sc.reset()                                     # every episode, once the random start is done
    every STATE s:
        r = sc.step(s)                             # planner fields (plan_s, forced_risk, ...) as keywords (W4)
        link.act(s["f"] + 2, policy.act(s, tap) if r.mask is None else r.mask, hold_frames=0)
        log r.alerts; if r.outcome in TERMINAL: end the episode (QUIT for the emulated quits)
        if sc.held: decide: sc.quit() or, after a frozen-state check (W3), sc.resume()

Why each piece:
- support: a callable STATE -> SupportSet (hits_to_death), (events, known) or anything else. Support is certified only
  explicitly (cross-module decision 4, round-2 review): a bare sequence, None or a known-but-empty result without
  SupportSet.certified_empty is unknown, so a forecaster dropout or a callable not wired yet never reads as "nothing can
  hurt". Unknown support adds an event of max(1, the encounter's worst known damage) and keeps the tier below GREEN.
  entity_support() is the stand-in until the W3 forecaster: one event per damaging entity root (instance = iid, so the
  body's colliders are one instance; hidden roots such as the Bell Beast underground count, it can emerge), reported
  unknown unless the caller certifies it. Bell Beast's worst known damage is 2: all 11 676 "damage" events in Bone_05
  of the trial and live runs (20261001_121446, 20261001_122249) are 2 masks, ENEMY, flags None, from the body's
  colliders, the attack bells and six DropBells. cfg has no default: SupervisorConfig.worst_known_damage is required.
- next_hit_may_kill (YELLOW / RED: no killing blow, the kill freeze swallows a pause, §3.7.3) is derived from STATE
  unless the planner passes it: a threat root (the entity_support rule) with 0 < hp <= the largest hit the hero can
  deal, which is max(hero_hit_floor, every "hit" event's dmg this attempt). The floor 5 is Bell Beast's measured nail
  hit (trial run: 56 of 56 hits dealt 5, docs/facts/1.0.30000/state_fields_m2.md §8).
- the pause machine runs with emulate_quit (training never quits for real: a confirmed pause ends the attempt as
  QUIT_EMULATED, or QUIT_EMULATED_GREYED / REFUSED_EMULATED / QUIT_EMULATED_UNKNOWN when the real quit would have been
  greyed, refused or unreadable), and with always_quit every supervisor pause (Q5 / Q7 / Q8 included) ends the attempt:
  there is no frozen-state check to resume with before the W3 tubes exist. Without always_quit a goal-PAUSE pause holds
  (sc.held) until the harness calls quit() or resume(); an UNPAUSED end notifies the supervisor and drops the machine,
  so the next PAUSE_PENDING starts a new loop.
- the clock is the STATE's end-of-frame QPC (s["q"]); keys are held from that frame (the harness applies them at
  frame + 2, so PauseQuitConfig's input_latency_max_s must cover 2-3 frames plus the oracle DelayLine).
- menu key guard (safety.key_guard): the caller passes the masks it already sent for the frames before the returned
  one lands (step(s, inflight=...)); while the loop presses, PauseCues.keys_clear says whether a Pause press sent now
  lands with no game key latched or queued on the key path (STATE act.hf replayed through them), and the loop's next
  press waits until it does (a held or replayed planner key would otherwise reach the pause menu: Z submits, X / A
  cancel, m0:N16).
- STATE "focus" counts only with a foreground sink (Q7): TRAIN instances run unfocused under OracleInjectSink.
- PauseWindowMonitor measures every hit's Q1 pause window [disablePause cleared, i-frames end] and alerts when one is
  shorter than detection + loop latency (DESIGN §3.7.5); its alerts, the supervisor's and the pause machine's are
  returned in Supervised.alerts.
"""
from collections.abc import Callable, Mapping, Sequence
from typing import NamedTuple

from ssbot.ipc.ents import HAZARD_TYPES
from ssbot.ipc.framing import BIT
from ssbot.safety.hits_to_death import SupportEvent, SupportSet
from ssbot.safety.key_guard import keys_clear
from ssbot.safety.pause_quit import (GOAL_PAUSE, GOAL_QUIT, HELD_STATES, UNPAUSED, PauseQuit, PauseQuitConfig,
                                     cues_from_state, to_mask)
from ssbot.safety.pause_window import PauseWindowMonitor
from ssbot.safety.supervisor import (RESUME_SELF_CHECK, Supervisor, SupervisorConfig, SupervisorDecision,
                                     input_from_state)

SupportFn = Callable[[dict], object]

_I_FRAME_BLOCKED = frozenset(i for i, n in enumerate(HAZARD_TYPES) if n in ("NON_HAZARD", "ENEMY", "EXPLOSION"))
HERO_HIT_FLOOR = 5


class Supervised(NamedTuple):
    mask: int | None                 # ACTION mask replacing the policy's (None: the policy acts)
    decision: SupervisorDecision
    outcome: str | None              # PauseQuit outcome once the pause machine has one (pause_quit.TERMINAL, ...)
    alerts: tuple[str, ...] = ()     # every alert of this attempt so far (pause-window monitor, supervisor, machine)


def _threat(e: dict) -> tuple[bool, int, bool]:
    """(can hurt now or come back, its colliders' damage, a hazard type that passes i-frames)."""
    dmg, hazard, threat = 0, False, bool(e.get("hidden"))
    for c in e.get("colliders") or ():
        d = c.get("damage")
        if not (c.get("enabled") and d and d.get("can_cause_damage")):
            continue
        threat = True
        dmg = max(dmg, int(d.get("dealt") or 0), int(d.get("eff") or 0))
        hazard |= d.get("hazard_type") is not None and d["hazard_type"] not in _I_FRAME_BLOCKED
    return threat, dmg, hazard


def entity_support(s: dict, worst_damage: int = 1, known: bool = False) -> SupportSet:
    """Stand-in support from STATE ents: one event per entity root that can hurt now (an enabled collider with damage)
    or that is a hidden HealthManager root (ents[].hidden: it can come back), damage max(its colliders' damage,
    worst_damage), hazard when a collider's hazard type passes i-frames. Not a validated superset of what can land
    within the horizon, so it is reported unknown unless `known` (and an empty result is never certified empty)."""
    out = []
    for e in s.get("ents") or ():
        threat, dmg, hazard = _threat(e)
        if threat:
            out.append(SupportEvent(str(e.get("type_key")), max(dmg, worst_damage, 1), hazard=hazard,
                                    instance=e.get("iid")))
    return SupportSet(tuple(out), known)


def next_hit_may_kill(s: dict, hero_hit: int) -> bool:
    """A threat root (entity_support's rule, hidden roots included) whose HP the hero's next landed hit could take to
    zero: 0 < hp <= hero_hit."""
    for e in s.get("ents") or ():
        hp = e.get("hp")
        if isinstance(hp, (int, float)) and not isinstance(hp, bool) and 0 < hp <= hero_hit and not e.get("is_dead") \
                and _threat(e)[0]:
            return True
    return False


def _support_of(r: object) -> tuple[tuple[SupportEvent, ...] | None, bool, bool]:
    """(events, known, certified empty) of a support callable's result; only explicit certifications count."""
    if isinstance(r, SupportSet):
        return r.events, r.known, r.certified_empty
    if isinstance(r, tuple) and len(r) == 2 and isinstance(r[1], bool):
        return tuple(r[0]), r[1], False
    if r is None:
        return None, False, False
    return tuple(r), False, False              # a bare sequence is not a certification


class SupervisedControl:
    def __init__(self, cfg: SupervisorConfig, support: SupportFn | None = None, pq_cfg: PauseQuitConfig | None = None,
                 bit: Mapping[str, int] = BIT, foreground_sink: bool = False, always_quit: bool = True,
                 qpc_freq: float = 1e7, hero_hit_floor: int = HERO_HIT_FLOOR):
        self.support = support
        self.cfg = cfg
        self.pq_cfg = pq_cfg or PauseQuitConfig(emulate_quit=True)
        self.bit = bit
        self.foreground_sink = foreground_sink
        self.always_quit = always_quit
        self.qpc_freq = qpc_freq
        self.hero_hit_floor = hero_hit_floor
        self._pause_bit = 1 << bit["pause"]
        self.reset()

    def reset(self) -> None:
        """A new attempt."""
        self.sup = Supervisor(self.cfg)
        self.pq: PauseQuit | None = None
        self.windows = PauseWindowMonitor(qpc_freq=self.qpc_freq)
        self.t0: float | None = None
        self.t_last = 0.0
        self.first_pending_f: int | None = None
        self.hero_hit = self.hero_hit_floor
        self.alerts: list[str] = []
        self._resume_reason = RESUME_SELF_CHECK
        self._resume_scene: str | None = None
        self._sup_alerted = False

    @property
    def held(self) -> bool:
        """The game is held paused (goal PAUSE, Quit greyed, a refused quit): the harness decides quit() / resume()."""
        return self.pq is not None and self.pq.state in HELD_STATES

    def quit(self) -> bool:
        """From a held pause: read the Quit item again and quit (emulated in training) if it is available."""
        return self.pq is not None and self.pq.request_quit(self.t_last)

    def resume(self, reason: str = RESUME_SELF_CHECK, scene: str | None = None) -> bool:
        """From a held pause, after the caller's frozen-state check: Continue + Submit; on UNPAUSED the supervisor is
        notified (reason / scene as Supervisor.notify_resumed) and the next PAUSE_PENDING starts a new loop."""
        if self.pq is None or not self.pq.request_unpause(self.t_last):
            return False
        self._resume_reason, self._resume_scene = reason, scene
        return True

    def _note(self, msg: str) -> None:
        if msg not in self.alerts:
            self.alerts.append(msg)

    def inject_fault(self, tid: str = "QF", why: str = "injected fault") -> None:
        """The pause stress test: a quit trigger on the next step, with no damage (Supervisor.inject)."""
        self.sup.inject(tid, why)

    def step(self, s: dict, inflight: Sequence[int] = (), **planner) -> Supervised:
        """inflight: the ACTION masks already sent for the frames after s's frame and before the one the returned
        mask is sent for (training: [mask for f + 1]); the pause loop's first press waits until the key path
        (STATE act.hf) shows no game key can be latched or replayed when it lands (safety.key_guard)."""
        t_q = (s.get("q") or 0) / self.qpc_freq
        self.t_last = t_q
        if self.t0 is None:
            self.t0 = t_q
        for ev in s.get("ev") or ():
            if ev.get("k") == "hit":
                d = (ev.get("d") or {}).get("dmg")
                if isinstance(d, (int, float)) and not isinstance(d, bool):
                    self.hero_hit = max(self.hero_hit, int(d))
        events, known, empty_ok = _support_of(None if self.support is None else self.support(s))
        planner.setdefault("next_hit_may_kill", next_hit_may_kill(s, self.hero_hit))
        inp = input_from_state(s, t_q - self.t0, support=events, support_known=known, support_empty_ok=empty_ok,
                               foreground_sink=self.foreground_sink, **planner)
        d = self.sup.step(inp)
        self.windows.update(s)
        for a in self.windows.alerts:
            self._note(f"pause window: {a}")
        if d.alert and not self._sup_alerted:
            self._sup_alerted = True
            self._note(f"supervisor: {'; '.join(d.reasons) or 'alert'}")
        pq = self.pq
        if pq is None and d.pause_pending:
            pq = self.pq = PauseQuit(self.pq_cfg)
            pq.start(t_q, GOAL_QUIT if d.quit_requested or self.always_quit else GOAL_PAUSE)
            if self.first_pending_f is None:
                self.first_pending_f = s.get("f")
        elif pq is not None and d.quit_requested and pq.goal != GOAL_QUIT:
            pq.upgrade_to_quit(t_q)
        if d.stop_input:
            return Supervised(0, d, None if pq is None else pq.outcome, tuple(self.alerts))
        if pq is None:
            return Supervised(None, d, None, tuple(self.alerts))
        cues = cues_from_state(s, self.qpc_freq)
        if pq.pressing:
            cues.keys_clear = keys_clear((s.get("act") or {}).get("hf"), inflight, self._pause_bit)
        keys = pq.step(cues, t_q)
        if pq.confirmed and not self.sup.paused:
            self.sup.notify_paused()
        if pq.alert:
            fail = next((f"{k}: {x}" for _, k, x in reversed(pq.log) if k in ("fail", "loop_alert", "false_cue_alert",
                                                                              "greyed", "refused",
                                                                              "unexpected_unpause")), "alert")
            self._note(f"pause machine: {fail}")
        outcome = pq.outcome
        if outcome == UNPAUSED:
            self.sup.notify_resumed(self._resume_reason, self._resume_scene, t_q - self.t0)
            self.pq = None
        return Supervised(to_mask(keys, self.bit), d, outcome, tuple(self.alerts))
