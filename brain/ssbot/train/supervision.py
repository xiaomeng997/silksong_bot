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
- kill_prims / next_hit_may_kill (YELLOW / RED: no killing blow, the kill freeze swallows a pause, §3.7.3) are
  derived from STATE unless the planner passes them: the damaging primitives whose one landed hit, at the bound the
  audited loadout gives that attack (combat.hero_damage.HeroDamage: crest, needle level, tools; a "hit" event above
  its kind's bound raises it and alerts), can take the weakest threat root (the entity_support rule, threat_min_hp)
  to 0. Before 2026-10-04 one number stood for every attack, max(hero_hit_floor 5, every "hit" event's dmg this
  attempt): after a Silkspear hit (15) the nail counted 15 too, and at h = 2 with the boss at 15 HP the bot never
  attacked again (task "STUCK at 15 HP", docs/facts/1.0.30000/pause_quit.md §9). hit_dealt (any "hit" event; vision:
  HIT_DEALT) is the supervisor's stalemate progress (QS). Without a loadout read (no hero yet) the old rule stands.
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
- vision=True (training on the simulated final path, DESIGN §3.9.2; task V review, 2026-10-03): the decisions read
  only what the vision view has. The SupervisorInput comes from the delayed WorldState the planner sees
  (supervisor.input_from_world: HUD health, the vision-side pause / quit availability, HIT_TAKEN), kill_prims
  from the view's counted HP (safety_filter.kill_hp_world: hp_est minus 3 sigma, not ents[].hp) against each attack's
  bound from the audited crest and tools (WorldState res.crest / equipped), and the pause
  machine from the vision form of the cues of the delayed STATE (pause_quit.vision_cues_from_state: the dimmer, a
  stopped world, the menu reader; no pause flag, no pause gate). Before, every view's supervisor and pause machine read
  the current oracle STATE: the degraded_dust runs' 0 WOULD_DIE and their pause latency were measured with oracle pause
  timing (the gate cue put the first press on the first open frame) and the oracle's paused flag.
  The PauseWindowMonitor stays on the raw STATE: it is instrumentation, not a decision.
- the post-hit window (Q1 after a hit, DESIGN §3.7.4, the person's rule of 2026-10-03): a hit's freeze shuts the pause
  gate (its STATE opens 0.213-0.267 s after the hit, the first pausable frame is one later), and a press that reaches
  the game before that is dropped (one held into it makes no edge). The pause machine gets the predicted first
  pausable frame (PauseCues.gate_open_at): the oracle cues from the freeze ramp's last shut frame
  (pause_quit.hit_ramp_open_at), the vision view from the capture time of the hit it showed plus POST_HIT_OPEN_MAX_S
  (post_hit_open_at), so the pause lands on or just after the first pausable frame of the window, well inside the
  i-frames (1.10-2.08 s).
"""
import math
from collections.abc import Callable, Mapping, Sequence
from typing import NamedTuple

from ssbot.backends.observability import DEFAULT_ATTACK_DAMAGE
from ssbot.combat.hero_damage import HeroDamage
from ssbot.combat.safety_filter import KillKnowledge, kill_hp_world, kill_scaling
from ssbot.core.primitives import DAMAGING
from ssbot.core.worldstate import Ev, Kind, WorldState
from ssbot.ipc.ents import HAZARD_TYPES
from ssbot.ipc.framing import BIT
from ssbot.safety.hits_to_death import SupportEvent, SupportSet
from ssbot.safety.key_guard import keys_clear
from ssbot.safety.pause_quit import (GOAL_PAUSE, GOAL_QUIT, HELD_STATES, POST_HIT_OPEN_MAX_BIND_S, POST_HIT_OPEN_MAX_S,
                                     UNPAUSED, PauseQuit, PauseQuitConfig, cues_from_state, to_mask,
                                     vision_cues_from_state)
from ssbot.safety.pause_window import PauseWindowMonitor
from ssbot.safety.supervisor import (RESUME_SELF_CHECK, Supervisor, SupervisorConfig, SupervisorDecision,
                                     SupervisorInput, hero_hurt, input_from_state, input_from_world)

SupportFn = Callable[[dict], object]

_I_FRAME_BLOCKED = frozenset(i for i, n in enumerate(HAZARD_TYPES) if n in ("NON_HAZARD", "ENEMY", "EXPLOSION"))
HERO_HIT_FLOOR = 5
# vision: the hero's largest hit is the largest the view prices (ObservabilityFilter attack_damage: the Silk Spear 15,
# the needle 5), and the view's HP is a count with an uncertainty: may kill below hero hit + this many sigma
VISION_HERO_HIT = int(max([HERO_HIT_FLOOR, *DEFAULT_ATTACK_DAMAGE.values()]))
VISION_HP_Z = 3.0


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


def threat_min_hp(s: dict) -> float | None:
    """The least HP of a threat root (next_hit_may_kill's rule, hidden roots included) that is alive: 0 < hp; None:
    no such root. The per-attack damage bounds (combat.hero_damage) turn it into the primitives that may kill."""
    out = None
    for e in s.get("ents") or ():
        hp = e.get("hp")
        if isinstance(hp, (int, float)) and not isinstance(hp, bool) and hp > 0 and not e.get("is_dead") \
                and _threat(e)[0]:
            out = float(hp) if out is None else min(out, float(hp))
    return out


def next_hit_may_kill_world(ws: WorldState, hero_hit: float, z: float = VISION_HP_Z) -> bool:
    """Vision: an enemy or boss the view tracks whose counted HP (Entity.hp_est, hits it saw) the hero's next hit could
    take to zero: 0 < hp_est and hp_est - z sigma <= hero_hit. A missed hit leaves the count high, so the bound looks
    below it; a hidden root counts too (it can come back)."""
    for e in ws.entities:
        h = e.hp_est
        if h is None or e.kind not in (Kind.BOSS, Kind.ENEMY) or h.conf <= 0:
            continue
        sig = h.sigma if math.isfinite(h.sigma) else 0.0
        if 0 < h.v and h.v - z * sig <= hero_hit:
            return True
    return False


def _known_v(e) -> object | None:
    return e.v if e is not None and e.conf > 0 else None


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
                 qpc_freq: float = 1e7, hero_hit_floor: int = HERO_HIT_FLOOR, vision: bool = False,
                 damage: HeroDamage | None = None, needle_level: int | None = 0, needle_audited: bool | None = None,
                 kill_know: KillKnowledge | None = None):
        self.damage0 = damage            # None: from the audited loadout of the first frame (crest, tools)
        # the needle level (nailUpgrades) is not in the per-frame export. The oracle view checks the playbook's at run
        # time (a "hit" event above its bound raises it, observe); the vision view cannot see a hit's damage, so it
        # takes every level unless an inventory audit confirmed the level (needle_audited; default: oracle only)
        audited = (not vision) if needle_audited is None else needle_audited
        self.needle_level = needle_level if audited else None
        self.kill_know = kill_know if kill_know is not None else KillKnowledge.load()
        self.support = support
        self.cfg = cfg
        self.pq_cfg = pq_cfg or PauseQuitConfig(emulate_quit=True)
        self.bit = bit
        self.foreground_sink = foreground_sink
        self.always_quit = always_quit
        self.qpc_freq = qpc_freq
        self.hero_hit_floor = hero_hit_floor
        self._pause_bit = 1 << bit["pause"]
        self.vision = vision
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
        self.damage: HeroDamage | None = self.damage0   # the loadout's bounds at scaling 1 (observe raises them)
        self._kill_in: tuple | None = None               # kill_inputs' frame and result (one value per frame)
        self.alerts: list[str] = []
        self._resume_reason = RESUME_SELF_CHECK
        self._resume_scene: str | None = None
        self._sup_alerted = False
        self._last_ws: WorldState | None = None
        self.t_hit_seen: float | None = None    # vision: capture time (QPC s) of the last hit the view showed
        self._hp_seen: int | None = None
        self._last_seen_ws: WorldState | None = None
        self._binding_seen = False              # the view showed the hero binding on its previous frame
        self.hit_open_s = POST_HIT_OPEN_MAX_S

    def _see_hit(self, ws: WorldState, t_cap: float) -> None:
        """Vision: note the capture time of a hit the delayed view shows: a HIT_TAKEN event, or the HUD's health + blue
        lower than at the last read (a hit on a frame the live loop skipped reaches the supervisor only as the lower
        HUD, and is then timed a frame or two late, which only delays the press), with the hero in the hit's knockback
        (supervisor.hero_hurt). A drop without it is frost or DamageTag damage (DoSpecialDamage's take-health path:
        no freeze, no shut gate, no i-frames), and holding the first press for 0.285 s there would only leave the hero
        vulnerable that long: Q1 then presses at once (fixer review 2026-10-03). The knockback shows on the hit's own
        frame (cState.recoilFrozen in the STATE of 28 of 28 sampled hit frames) and lasts through the freeze and the
        recoil, so a hit seen late still shows it."""
        hp = ws.res.hp
        tot = None if hp is None or hp.conf <= 0 or hp.v is None else int(hp.v) + int(_known_v(ws.res.blue) or 0)
        drop = any(ev.kind == Ev.HIT_TAKEN for ev in ws.events) or \
            (tot is not None and self._hp_seen is not None and tot < self._hp_seen)
        hit = drop and hero_hurt(ws) is True
        if tot is not None:
            self._hp_seen = tot
        if hit:
            self.t_hit_seen = t_cap
            # a hit through a Bind (Q1a's own risk) adds the BindBreak freeze: the gate opened 0.53-0.55 s after it
            self.hit_open_s = POST_HIT_OPEN_MAX_BIND_S if self._binding_seen else POST_HIT_OPEN_MAX_S
        b = ws.hero.binding
        self._binding_seen = b is not None and b.conf > 0 and b.v == "IN_PROGRESS"

    def post_hit_open_at(self, now: float) -> float | None:
        """Vision: when a press may first reach the game after the last hit the view showed: its capture time plus
        the latest first pausable frame measured after a hit, pause_quit.POST_HIT_OPEN_MAX_S (0.285 s: 2138 hits had
        the STATE's gate open 0.213-0.267 s after it, pausable one frame later). The press then lands 0-3 frames after
        the first pausable frame whatever the view's delay k; the blind cadence from the trigger (hit + k + the lead,
        every 6 frames) landed 0-5 after it. The vision view sees
        no gate and no time scale; the hero does not move during the freeze's ramp (recoil starts after it), so a
        motion cue for the ramp is left to M3's measurements. None once the opening is more than gate_trust_s past."""
        t = self.t_hit_seen
        if t is None:
            return None
        at = t + self.hit_open_s
        return at if now - at <= self.pq_cfg.gate_trust_s else None

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

    def kill_inputs(self, s: dict, obs: dict | None = None, ws: WorldState | None = None
                    ) -> tuple[HeroDamage | None, float | None]:
        """(the hero's per-attack damage bounds against this frame's kill targets, the least HP of a kill target): the
        one source both the supervisor's allowlist (kill_prims, QS) and the planner's L0 filter (FilterContext) read
        (fixer round 2026-10-04: the supervisor used to read STATE threat roots and the planner every WorldState boss /
        enemy, and where they disagreed QS was off while the planner vetoed). From the WorldState the decisions read
        (the oracle backend's of this STATE; vision: the delayed view): safety_filter.kill_hp_world (an unknown boss HP
        counts as 0) and the targets' damage scaling (KillKnowledge, unknown types unbounded); without a WorldState,
        the STATE's live entities. The oracle's "hit" events of this STATE raise the bounds first (observe)."""
        key = (id(s), s.get("f"), id(ws), id(s.get("ev")))
        if self._kill_in is not None and self._kill_in[0] == key:
            return self._kill_in[1]
        if self.vision:
            ws = self._last_ws if ws is None else ws
            if self.damage is None and ws is not None:
                self.damage = HeroDamage.from_loadout(_known_v(ws.res.crest), self.needle_level, ws.res.equipped)
        else:
            hero = s.get("hero") or {}
            if self.damage is None and hero.get("crest") is not None:
                self.damage = HeroDamage.from_loadout(hero.get("crest"), self.needle_level, hero.get("tools") or ())
            for ev in s.get("ev") or ():
                if ev.get("k") != "hit":
                    continue
                d = ev.get("d") or {}
                dmg = d.get("dmg")
                if isinstance(dmg, (int, float)) and not isinstance(dmg, bool):
                    self.hero_hit = max(self.hero_hit, int(dmg))
                    if self.damage is not None:
                        new = self.damage.observe(d.get("src"), d.get("attack"), dmg)
                        if new is not self.damage:
                            self._note(f"hero damage: a {new.kind_of(d.get('src'), d.get('attack'))} hit "
                                       f"({d.get('src')}) dealt {dmg}, above the loadout's bound")
                        self.damage = new
        if ws is not None:
            hp, scal = kill_hp_world(ws), kill_scaling(ws, self.kill_know)
        else:
            hp = threat_min_hp(s)
            scal = self.kill_know.scaling(str(e.get("type_key")) for e in s.get("ents") or ()
                                          if isinstance(e.get("hp"), (int, float)) and e["hp"] > 0
                                          and not e.get("is_dead"))
        out = (None if self.damage is None else self.damage.at(scal), hp)
        self._kill_in = (key, out)
        return out

    def h_now(self, s: dict, obs: dict | None = None, ws: WorldState | None = None) -> tuple[int | None, str | None]:
        """(h, basis) the supervisor's step will decide for this STATE (same inputs: the current STATE in oracle mode,
        the delayed view in vision mode), without stepping it (Supervisor.peek_h). The policy's tactics and safety
        filter run before the step and read this, not the decision of the tick before, which on the tick a hit takes
        h to 1 still said h 2 (fixer review 2026-10-03)."""
        if self.vision:
            obs = s if obs is None else obs
            ws = self._last_ws if ws is None else ws
            events, known, empty_ok = _support_of(None if self.support is None else self.support(obs))
            if ws is None:
                inp = SupervisorInput(t=0.0, support=tuple(events or ()), support_known=events is not None and known,
                                      support_empty_ok=events is not None and empty_ok)
            else:
                inp = input_from_world(ws, 0.0, support=events, support_known=known, support_empty_ok=empty_ok)
        else:
            events, known, empty_ok = _support_of(None if self.support is None else self.support(s))
            inp = input_from_state(s, 0.0, support=events, support_known=known, support_empty_ok=empty_ok)
        return self.sup.peek_h(inp)

    def step(self, s: dict, obs: dict | None = None, ws: WorldState | None = None, inflight: Sequence[int] = (),
             **planner) -> Supervised:
        """s: the current STATE (its QPC is the clock the keys go out on). Vision mode: obs is the STATE of the frame
        the view shows and ws its WorldState (the delayed ones); the decisions and the pause machine read only those
        (module docstring). Without ws (a real quit's menus, where the backend is not fed) the supervisor keeps the
        last hero it read.
        inflight: the ACTION masks already sent for the frames after s's frame and before the one the returned
        mask is sent for (training: [mask for f + 1]); the pause loop's first press waits until the key path
        (STATE act.hf) shows no game key can be latched or replayed when it lands (safety.key_guard). The key path is
        the bot's own output (the final inputd sink holds the same filter state), not an observation of the game, so
        the key guard reads the current STATE in every view, the vision views included."""
        t_q = (s.get("q") or 0) / self.qpc_freq
        self.t_last = t_q
        if self.t0 is None:
            self.t0 = t_q
        if self.vision:
            obs = s if obs is None else obs
            # a real quit's menus feed no WorldState: the last one stands (the world is paused), not a lost hero
            # (live 20261003_043306 i0 ep0 ended "Q5: hero lost 4500 ms" after 4.5 s of menus)
            ws = self._last_ws if ws is None else ws
            self._last_ws = ws
            events, known, empty_ok = _support_of(None if self.support is None else self.support(obs))
            if ws is not None and ws is not self._last_seen_ws:
                self._last_seen_ws = ws
                self._see_hit(ws, (obs.get("q") or 0) / self.qpc_freq)
            if ws is not None:
                dmg, kill_hp = self.kill_inputs(s, obs, ws)
                kp = dmg.kill_prims(kill_hp) if dmg is not None else DAMAGING
                planner.setdefault("kill_prims", kp)
                planner.setdefault("next_hit_may_kill", bool(kp))
                planner.setdefault("hit_dealt", any(ev.kind == Ev.HIT_DEALT for ev in ws.events))
                inp = input_from_world(ws, t_q - self.t0, support=events, support_known=known,
                                       support_empty_ok=empty_ok, foreground_sink=self.foreground_sink, **planner)
            else:
                inp = SupervisorInput(t=t_q - self.t0, support=tuple(events or ()),
                                      support_known=events is not None and known,
                                      support_empty_ok=events is not None and empty_ok, **planner)
        else:
            dealt = any(ev.get("k") == "hit" for ev in s.get("ev") or ())
            dmg, kill_hp = self.kill_inputs(s, None, ws)
            events, known, empty_ok = _support_of(None if self.support is None else self.support(s))
            if dmg is not None:
                kp = dmg.kill_prims(kill_hp)
                planner.setdefault("kill_prims", kp)
                planner.setdefault("next_hit_may_kill", bool(kp))
            else:                          # no loadout read (no hero): every damaging primitive, the largest hit
                planner.setdefault("next_hit_may_kill", next_hit_may_kill(s, self.hero_hit))
            planner.setdefault("hit_dealt", dealt)
            if ws is not None:
                planner.setdefault("hurt", hero_hurt(ws))      # the oracle backend's ws is this STATE's frame
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
        cues = vision_cues_from_state(obs, self.qpc_freq) if self.vision else cues_from_state(s, self.qpc_freq)
        if self.vision:
            cues.gate_open_at = self.post_hit_open_at(t_q)
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
