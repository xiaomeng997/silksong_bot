"""Supervisor v1 (DESIGN §3.7.3-3.7.4, the §3.5.1 supervisor row, the §3.5.6 Bind / parry / down-slash gates; M2 W5):
risk tier, triggers Q1-Q9 and P1, the per-attempt risk integral and unpredicted-hit counter, PAUSE_PENDING, and the
primitive allowlist the planner and tactics must obey. Pure logic, 60 Hz: one Supervisor per attempt.

    sup = Supervisor(SupervisorConfig(worst_known_damage=2))          # Bell Beast: every attack is 2 masks
    d = sup.step(SupervisorInput(t=..., hp=5, max_hp=5, support=(SupportEvent("Bone Beast", 2, instance=iid),),
                                 support_known=True, plan_s=0))
    if d.pause_pending: hand the keyboard to safety.pause_quit.PauseQuit (goal "QUIT" if d.quit_requested)
    candidates = [c for c in candidates if d.allows(c.primitive)]   # or d.allowed_mask[codes] in a numba planner
    # training: ssbot.train.supervision.SupervisedControl does this per STATE

Support is explicit (cross-module decision 4). `support` is what the forecaster puts in support for this frame, and
`support_known` says whether the producer certifies it as a superset of what can land; nothing is inferred from the
support's type or length. An empty support counts as certified only with support_empty_ok as well (a forecaster
dropout that returns no events must not read as "nothing can hurt"). Unknown support (the default: a missing forecast,
a dropped track, an untracked enemy) adds an "unknown" event of max(1, the encounter's worst known damage, the worst
damage taken this attempt) that the mask may not cover, makes Q3 fire at h = 2 and keeps the tier below GREEN: unknown
is never safe, and hits_to_death's UNBOUNDED (nothing can hurt) needs that certified empty support.
worst_known_damage has no default: every caller states the encounter's worst single event (Bell Beast 2, from the
11 676 logged hits; a default of 1 made an unknown support at 3 HP read h = 3 with no Q3 against Bell Beast).
A frame without a hero (STATE "hero" missing: loads, the main menu) is unknown, not 0 HP: h is taken from the last
known hero, and Q5 fires once the hero has been missing for hero_lost_ms with h <= 2 or never seen.

h (SupervisorDecision.h) is hits_to_death against the support; with a certified-empty support (nothing can land within
its 0.8 s, e.g. the Bell Beast underground) the support says UNBOUNDED, yet the encounter's worst event comes back
after the horizon, so h is then counted against that event (worst_known_damage, the worst taken this attempt; an
intact Fractured Mask covers it as it would the visible boss's): h_basis "worst known". Every rule below (tier, Q1,
Q1a, Q3, Q5, Q6, the Bind commit test's worth clause) reads this h. Before 2026-10-03 only Q1 used the floor (10bfb66),
so at 3 HP with the boss underground the tier was GREEN and the Bind commit test refused the Bind as "not worth it"
(HP 3 > max - 3 and h UNBOUNDED > 2) in the one window where it is safest.

Tiers: GREEN h >= 3, the chosen plan has S = 0 and the support is known; YELLOW h = 2, or S = 1 (or no plan yet, or
the support unknown) with h >= 3; RED any trigger. Triggers (§3.7.4, Q1 / Q1a the person's rule of 2026-10-03):
  Q1 h <= 1 (a Fractured Mask just broken at 1 HP included)                  -> PAUSE_PENDING, quit; no Bind attempt
     (the PAUSE_PENDING allowlist is evasive only, and the tactics never ask for a Bind at h <= 1: a model error at
     h <= 1 is death, so the bot bets on its model only where an error is survivable). After a hit (q1_cause "hit":
     a hit within POST_HIT_WINDOW_S) the pause lands in the post-hit window, the one stretch that is both
     invulnerable and pausable: the hit's freeze shuts the gate (the STATE shows it open 0.213-0.267 s after the hit
     on 2138 Bell Beast hits, a press pauses from the frame after) and the i-frames last 1.10-2.08 s; the pause
     machine times its first press for the first pausable frame (pause_quit.PauseCues.gate_open_at). Without a hit (frost, pending damage: q1_cause "no_hit") it presses at once,
     i.e. the pause lands on the first pausable frame. The 10bfb66 rule (Q1 at a certified-empty support against the
     worst known event) is now simply h's definition above.
  Q1a h >= 2 and HP < max: heal first (Restrictions.heal_first; no pause). The tactics Bind in place when the §3.5.6
     commit test passes, else walk to a verified safe spot of the playbook and Bind there, else fight on under the
     other triggers (combat.tactics.modes). Before, heal_first was only a YELLOW / RED flag nothing read, and the
     playbook's hp_missing_min (2) kept the Bind off 4 / 5 HP although h is 2 there
  Q2 I2 broken and no candidate leaves the exposure within 0.2 s              -> PAUSE_PENDING, quit
  Q3 h = 2 with a mask-bypassing, multi-instance, hazard or CriticalDamage threat, or an unknown support
                                                                              -> PAUSE_PENDING, quit
     "Multi-instance" (§3.7.4) is one damage event made of hits the i-frames do not separate (multi-hitters, 1+1 /
     1+1+1 grabs: SupportEvent.hits > 1), not several ENEMY sources in support: enemy hits are 1.0 s of i-frames
     apart, so after one 2-mask Bell Beast hit (3 HP, h = 2) the fight goes on in YELLOW (heal first with silk >= 9,
     punish at most 1 hit, no parry, no new fights). This replaces the stricter reading (any two threat instances in
     support), under which every hit against the Bell Beast ended the attempt (M2 runs 20261002_064001 / 072132: all
     QUITs were Q3 "h = 2 and 2-6 threat instances").
  Q4 two unpredicted hits in one attempt, or the risk integral > 2x the training expectation
                                                                              -> quit at the next pausable GREEN frame,
                                                                                 conservative variant, retrain flag
  Q5 frame age > 50 ms, HUD unreadable > 100 ms (not in ENDING), hero lost > 300 ms with h <= 2, unknown scene,
     OVERLAY_INTRUSION, consecutive tearing                                   -> pause, self-check (resume only with
                                                                                 h >= 3 and the frozen check passing)
  Q6 FORCED_RISK with h <= 2, its best plan meeting the support within H      -> PAUSE_PENDING, quit
     H = q6_horizon_s = 0.8 s, DESIGN §3.5.4's horizon, on which FORCED_RISK is defined. The planner's adaptive
     horizon (a committed charge rolled out to its end plus 0.3 s, up to 2 s) made FORCED_RISK an open-loop statement
     about the whole charge: every gate / live QUIT of 20261002_123347 ... 152649 (37, all Q6 at h = 2) came 93-1214
     frames after the hit, and in the 19 whose trigger tick replays (ssbot.tools.quit_timeline), all in Charge
     Emerge / Emerge Antic C, the best plan stayed clear for 120 of 120 frames (its first contact on the last one,
     where the jump lands beside Charge End); at h >= 3, 13 of 2266 FORCED_RISK streaks starting in Charge Emerge
     (0.6 %) were followed by a hit within 3 s. forced_clear_s is how long the best plan stays out of the support
     (unknown, None, counts as 0), so FORCED_RISK within H is Q6 as before, whatever the planner's horizon (the 9
     Burst / rage-pattern triggers: 0-48 frames, the 2 in a committed lock: 4 and 7)
  Q7 FOCUS_LOST                                                               -> release all, regain focus, pause,
                                                                                 self-check
  Q8 progress watchdog (hook)                                                 -> pause, diagnose, alert
  Q9 capture lost or PERMADEATH (hook)                                        -> stop all input, alert
  P1 planning that needs > 3 ms only in GREEN outside A/B encounters, or in GREEN inside a registered safe window.
  QF a fault injected by the pause stress test (Supervisor.inject)              -> PAUSE_PENDING, quit
Q7 is the active input sink's focus guard (inputd under SendInput / Pico); under OracleInjectSink (TRAIN, 4-6
instances, at most one focused) Application.isFocused says nothing, so input_from_state ignores STATE "focus" unless
foreground_sink is set.

Primitive allowlists over the shared vocabulary (ssbot.core.primitives, DESIGN §3.5.4 + §3.6.3); a name the
vocabulary does not know is never allowed:
  paused or Q9                       nothing
  PAUSE_PENDING, EVADE_EXIT latch    EVASIVE only: MOVE, JUMP, DOUBLEJUMP, DASH, WALLJUMP, GLIDE, WAIT, ABORT. Every
                                     attack (a Wanderer crit is a 0.2 s HeroDamageShort freeze, m0 §2.4), parry / nail
                                     clash, down-slash, tool, silk skill, Bind and Clawline can start a FreezeMoment,
                                     and interactions set BlockingInteractable or disablePause (m0:N15)
  YELLOW / RED otherwise             everything except: DAMAGING (attacks, tools, silk skills, Clawline, HIT_TARGET)
                                     when the next landed hit may kill (the kill freeze swallows a pause); ATTACK(down)
                                     over any hazard; plus the GREEN rules. Restrictions: punish <= 1 hit, no parry,
                                     no new fights (heal first is Q1a's: h >= 2 below max HP, in any tier)
  GREEN                              everything except SILKSKILL below full HP and ATTACK(down) over spikes (§3.5.6)
PAUSE_PENDING is sticky until the pause is confirmed (notify_paused) or the attempt ends: a pause does not end the
threat. After a greyed-Quit "unpause, EVADE out of the room, pause and quit" (§3.7.5 step 4), notify_resumed(EVADE_EXIT)
latches EVADE_EXIT: evasive primitives only and no re-arming of the quit triggers until the scene changes or quit
becomes available, with an alert and re-arming after evade_exit_timeout_s.
"""
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

import numpy as np

from ssbot.core.primitives import ALL, DAMAGING, EVASIVE, N_PRIM, Prim
from ssbot.core.primitives import code as prim_code
from ssbot.core.worldstate import FM, Ev, WorldState
from ssbot.safety.hits_to_death import (MASK_BROKEN, MASK_INTACT, MASK_NONE, MASK_UNKNOWN, UNBOUNDED, SupportEvent,
                                        ctx_from_support, hits_to_death,
                                        mask_intact, mask_state, pending_from_tags)
from ssbot.safety.invariants import Verdict
from ssbot.safety.pause_quit import availability_from_state

GREEN, YELLOW, RED = "GREEN", "YELLOW", "RED"
QUIT, DIAGNOSE, SELF_CHECK = "QUIT", "DIAGNOSE", "SELF_CHECK"     # what to do once the pause is confirmed
_ON_PAUSED_RANK = {None: 0, SELF_CHECK: 1, DIAGNOSE: 2, QUIT: 3}
RESUME_SELF_CHECK, RESUME_EVADE_EXIT = "self_check", "evade_exit"   # notify_resumed reasons

QUIT_TRIGGERS = ("Q1", "Q2", "Q3", "Q6", "QF")   # QF: a fault injected by the pause stress test (inject)
UNKNOWN_SOURCE = "unknown support"
WORST_SOURCE = "worst known event"
H_SUPPORT, H_WORST = "support", "worst known"       # SupervisorDecision.h_basis
Q1_HIT, Q1_NO_HIT = "hit", "no_hit"                  # SupervisorDecision.q1_cause
# A Q1 this soon after a hit is the post-hit window's quit: the hit's i-frames last at least this long (pause_window:
# the i-frames end 1.10-2.08 s after the hit on the 2268 hits of 20261001_121446 / 122249; probe P7 "to about 1.2 s")
POST_HIT_WINDOW_S = 1.1
NOTHING: frozenset[Prim] = frozenset()

# §3.5.6 constants
BIND_SILK = 9                  # SilkSpool.BindCost (m0 §2.5); IsAnyCursed makes it unpayable
T_BIND_S = 1.37                # Bind duration
T_BIND_INJECTOR_S = 0.89       # with Injector Band
DELTA_B_S = 0.15               # Bind margin, plus the perception margin
DELTA_B_WARDING_S = 0.05       # with Warding Bell (audited equipped), plus the perception margin; <= 5 % exposure
WARDING_MAX_EXPOSURE = 0.05
PARRY_VISION_MIN = 0.995       # vision G1 success on the attack's tell


@dataclass(slots=True)
class SupervisorConfig:
    worst_known_damage: int                    # the encounter's / scene's worst single event (Bell Beast 2): the
    #                                            floor of an unknown support's D1; required, no default
    q2_escape_s: float = 0.2
    q4_unpredicted_hits: int = 2
    risk_factor: float = 2.0
    expected_risk_per_s: float | None = None   # training expectation of the integral's growth; None: Q4 by hits only
    risk_warmup_s: float = 5.0                 # the expectation is never taken over less than this
    frame_age_ms: float = 50.0
    hud_unreadable_ms: float = 100.0
    hero_lost_ms: float = 300.0
    q6_horizon_s: float = 0.8                  # DESIGN §3.5.4 H: Q6 counts FORCED_RISK whose best plan meets the support
    #                                            within this (SupervisorInput.forced_clear_s; the module docstring)
    tear_frames: int = 3
    unknown_mask_covers: bool = False          # may the Fractured Mask be trusted against an unknown threat (grabs ...)
    evade_exit_timeout_s: float = 20.0
    hooks: tuple[Callable[["SupervisorInput"], Iterable[str]], ...] = ()


@dataclass(slots=True)
class SupervisorInput:
    t: float                                   # real seconds since the attempt started
    dt: float = 1 / 60
    hp: int | None = None                      # None: the hero was not read this frame (unknown, not 0)
    max_hp: int | None = None
    blue: int = 0
    mask: str = MASK_UNKNOWN                   # hits_to_death.MASK_* (audit)
    support: Sequence[SupportEvent] = ()       # worst events of the in-support threat tubes now
    support_known: bool = False                # the producer certifies `support` as a superset of what can land
    support_empty_ok: bool = False             # ... and, when `support` is empty, certifies that nothing can land
    pending_dmg: int = 0
    pending_mask_covers: bool = False
    plan_s: int | None = None                  # S of the chosen plan (0/1); None: no plan yet (treated as S = 1)
    forced_risk: bool = False                  # no candidate with S = 0 this frame
    forced_clear_s: float | None = None        # FORCED_RISK only: how long the best allowed plan stays out of the
    #                                            support after the decision frame, i-frames counted (None: unknown,
    #                                            taken as 0); the planner's horizon can be longer than H
    i2_violated: bool = False
    escape_s: float | None = None              # least time any candidate needs to leave the I2 exposure (None: none)
    unpredicted_hits: int = 0                  # hero hits this frame that no in-support tube covered
    damage_taken: int = 0                      # damage the hero took this frame (raises the unknown-support floor)
    p_death: float = 0.0                       # this frame's death risk (sum of p * overlap of the chosen plan)
    pausable: bool | None = None               # availability model (pause_quit.availability_* / quit map); None:
    quittable: bool | None = None              # unknown
    frame_age_ms: float = 0.0
    hud_unreadable_ms: float = 0.0
    hero_lost_ms: float = 0.0
    scene_known: bool = True
    scene: str | None = None
    overlay_intrusion: bool = False
    tear_streak: int = 0
    ending: bool = False                       # ENDING screen mode: HUD loss is expected there
    focus_lost: bool = False
    watchdog: bool = False                     # Q8
    capture_lost: bool = False                 # Q9
    permadeath: bool = False                   # Q9
    next_hit_may_kill: bool = False            # an enemy in reach could die from the next landed hit
    over_spikes: bool = False                  # a down-slash here passes over spikes (never, §3.5.6)
    over_hazard: bool = False                  # ... over any other hazard (only in GREEN, §3.7.3)
    in_encounter: bool = False                 # inside an A/B encounter (P1)
    in_safe_window: bool = False               # a registered safe window: stagger, between waves (P1)


@dataclass(slots=True, frozen=True)
class Restrictions:
    heal_first: bool = False
    max_punish_hits: int | None = None         # None: no limit
    no_parry: bool = False
    no_killing_blow: bool = False
    no_down_slash_over_hazard: bool = True     # always for spikes; outside GREEN for every hazard
    no_new_fights: bool = False


@dataclass(slots=True, frozen=True)
class SupervisorDecision:
    tier: str
    h: int | None                              # None: no hero read yet this attempt
    pause_pending: bool
    quit_requested: bool
    on_paused: str | None                      # QUIT / DIAGNOSE / SELF_CHECK once the pause is confirmed
    allowed: frozenset[Prim]                   # the primitive allowlist (codes of ssbot.core.primitives)
    restrictions: Restrictions
    triggers: tuple[str, ...]                  # fired this frame, plus latched Q4
    reasons: tuple[str, ...]
    paused: bool = False
    stop_input: bool = False                   # Q9: release everything and press nothing
    release_all: bool = False                  # Q7
    regain_focus: bool = False                 # Q7
    alert: bool = False
    mark_retrain: bool = False                 # Q4
    conservative_variant: bool = False         # Q4
    long_planning_ok: bool = False             # P1
    risk_integral: float = 0.0
    unpredicted_hits: int = 0
    support_known: bool = False
    hero_known: bool = True
    evade_exit: bool = False                   # the EVADE_EXIT latch is on: leave the room, evasive primitives only
    h_basis: str | None = None                 # H_SUPPORT, or H_WORST (certified-empty support: the encounter's worst)
    q1_cause: str | None = None                # Q1 this frame: Q1_HIT (post-hit window) or Q1_NO_HIT (first pausable)
    t_hit: float | None = None                 # SupervisorInput.t of the last hit seen this attempt

    def allows(self, primitive: "Prim | int | str") -> bool:
        """A primitive (code, int or text name such as "ATTACK(down)") is allowed; unknown names never are."""
        c = prim_code(primitive)
        return c is not None and c in self.allowed

    @property
    def allowed_mask(self) -> np.ndarray:
        """bool[N_PRIM], indexed by primitive code, for a numba planner."""
        m = np.zeros(N_PRIM, np.bool_)
        for p in self.allowed:
            m[int(p)] = True
        return m


def input_from_state(s: dict, t: float, support: Sequence[SupportEvent] | None = None, *, support_known: bool,
                     support_empty_ok: bool = False, foreground_sink: bool = False, **kw) -> SupervisorInput:
    """Oracle mode (training): the SupervisorInput fields STATE answers exactly (health, blue, max health, the audited
    Fractured Mask, pending DamageTag damage from hero.tags when exported, pause / quit availability from the
    PauseGate, the scene, damage taken this frame). A missing hero section leaves hp None (unknown). support_known is
    required and never inferred: support None is unknown whatever it says, and an empty support needs support_empty_ok
    too (Supervisor.support_certified). hero.tags dmg_left -1 (no hit limit) or unreadable is lethal pending damage
    (hits_to_death.pending_from_tags). focus counts only with a foreground sink (SendInput / Pico); under
    OracleInjectSink the training instances run unfocused. Planner fields (plan_s, forced_risk, ...) come from the
    caller."""
    hero = s.get("hero")
    hp = max_hp = None
    blue, mask, pending = 0, MASK_UNKNOWN, 0
    if isinstance(hero, dict) and hero.get("health") is not None:
        hp = int(hero["health"])
        max_hp = int(hero["max_health"]) if hero.get("max_health") is not None else None
        blue = int(hero.get("health_blue") or 0)
        mask = mask_state(hero.get("fractured_mask"))
        pending, _ = pending_from_tags(hero.get("tags"), hp, blue)
    avail = availability_from_state(s) if s.get("pause") else None
    dmg = sum(int((ev.get("d") or {}).get("amount") or 0) for ev in s.get("ev") or () if ev.get("k") == "damage")
    base = dict(t=t, dt=float(s.get("udt") or 1 / 60), hp=hp, max_hp=max_hp, blue=blue, mask=mask,
                support=tuple(support or ()), support_known=support is not None and bool(support_known),
                support_empty_ok=support is not None and bool(support_empty_ok), pending_dmg=pending,
                damage_taken=dmg, pausable=None if avail is None else avail.pause,
                quittable=None if avail is None else avail.quit, scene=(s.get("game") or {}).get("scene"),
                focus_lost=foreground_sink and s.get("focus") is False)
    base.update(kw)
    return SupervisorInput(**base)


_FM_MASK = {FM.NOT_EQUIPPED: MASK_NONE, FM.INTACT: MASK_INTACT, FM.BROKEN: MASK_BROKEN, FM.UNKNOWN: MASK_UNKNOWN}


def _known(e) -> object | None:
    """An estimate's value, None when it is unknown (conf 0)."""
    return e.v if e is not None and e.conf > 0 else None


def input_from_world(ws: WorldState, t: float, support: Sequence[SupportEvent] | None = None, *,
                     support_known: bool, support_empty_ok: bool = False, foreground_sink: bool = False,
                     **kw) -> SupervisorInput:
    """Vision mode (the final path, and training on its simulation, DESIGN §3.9.2): the SupervisorInput from the
    WorldState the planner sees, not from the oracle STATE: the HUD's health, blue masks and max health (unread: hp
    None), the Fractured Mask as the inventory audit has it, pending damage from the visible statuses
    (Resources.pending_dmg; conf 0, an unbounded status, reads as lethal: health + blue), the masks the HUD lost in this
    frame (HIT_TAKEN), pause / quit availability from the vision-side model (Game.pause_available / quit_available,
    ObservabilityFilter._pause; conf 0, e.g. quit without a quit map, is unknown: None), the scene. On the simulated
    final path the WorldState is the delayed one (2-4 frames), so every trigger fires as late as vision would see it."""
    r, g = ws.res, ws.game
    hp = _known(r.hp)
    max_hp = _known(r.hp_max)
    blue = int(_known(r.blue) or 0)
    hp = None if hp is None else int(hp)
    pending = int(r.pending_dmg.v) if r.pending_dmg.conf > 0 else (hp or 0) + blue
    dmg = sum(int(getattr(ev.data, "amount", 0) or 0) for ev in ws.events if ev.kind == Ev.HIT_TAKEN)
    pause, quit_ = _known(g.pause_available), _known(g.quit_available)
    base = dict(t=t, dt=1 / 60, hp=hp, max_hp=None if max_hp is None else int(max_hp), blue=blue,
                mask=_FM_MASK.get(r.fractured_mask.v, MASK_UNKNOWN) if r.fractured_mask.conf > 0 else MASK_UNKNOWN,
                support=tuple(support or ()), support_known=support is not None and bool(support_known),
                support_empty_ok=support is not None and bool(support_empty_ok), pending_dmg=pending,
                damage_taken=dmg, pausable=None if pause is None else bool(pause),
                quittable=None if quit_ is None else bool(quit_), scene=_known(g.scene) or None,
                focus_lost=foreground_sink and not g.focus_ok)
    base.update(kw)
    return SupervisorInput(**base)


def base_tier(h: int | None, plan_s: int | None, support_known: bool = True) -> str:
    if h is not None and h >= 3 and plan_s == 0 and support_known:
        return GREEN
    if h is None or h >= 2:
        return YELLOW
    return RED


def q3_threat(support: Sequence[SupportEvent], support_known: bool = True) -> str | None:
    """Why the support makes h = 2 a quit (Q3), or None."""
    if not support_known:
        return "the support is unknown"
    for e in support:
        if not e.mask_covers:
            return f"{e.source} bypasses the mask"
        if e.hits > 1:
            return f"{e.source} is a {e.hits}-hit event"
        if e.hazard:
            return f"{e.source} is a hazard"
        if e.critical:
            return f"{e.source} deals CriticalDamage"
    return None


def down_slash_ok(over_spikes: bool, over_hazard: bool, tier: str) -> str | None:
    """None when a down-slash is allowed here, else why not (§3.5.6 never over spikes; §3.7.3 YELLOW: no down-slash
    over a hazard, so outside GREEN over any hazard)."""
    if over_spikes:
        return "over spikes"
    if over_hazard and tier != GREEN:
        return f"over a hazard in {tier}"
    return None


@dataclass(slots=True)
class _EvadeExit:
    scene: str | None
    t0: float


@dataclass(slots=True)
class _Hero:
    hp: int
    max_hp: int
    blue: int
    mask: str
    missing_s: float = 0.0


class Supervisor:
    """Per-attempt state: risk integral, unpredicted hits, the last known hero, and the PAUSE_PENDING / Q4 /
    EVADE_EXIT latches."""

    def __init__(self, cfg: SupervisorConfig):
        self.cfg = cfg
        self.reset()

    def reset(self) -> None:
        """A new attempt."""
        self.risk_integral = 0.0
        self.unpredicted = 0
        self.worst_seen = 0
        self.pending = False
        self.on_paused: str | None = None
        self.q4: str | None = None              # latched Q4 reason
        self.paused = False
        self.release_needed = False
        self.alerted = False
        self.evade: _EvadeExit | None = None
        self.hero: _Hero | None = None
        self.never_seen_s = 0.0
        self.reasons_latched: list[str] = []
        self.injected: list[tuple[str, str]] = []
        self.t_hit: float | None = None         # the last frame with a hit (damage taken, or health + blue down)
        self._hp_tot: int | None = None

    def inject(self, tid: str = "QF", why: str = "injected fault") -> None:
        """Fire trigger `tid` on the next step (the pause stress test, DESIGN §3.7.5 G1 fault injection: a quit
        trigger at a chosen frame, with no damage, so the pause loop runs from any moment of the fight)."""
        self.injected.append((tid, why))

    def notify_paused(self) -> None:
        """The pause loop confirmed the pause (PAUSE_MENU seen)."""
        self.paused = True
        self.pending = False

    def notify_resumed(self, reason: str = RESUME_SELF_CHECK, scene: str | None = None, t: float = 0.0) -> None:
        """An unpause (Continue + Submit) took effect; the attempt goes on. RESUME_SELF_CHECK: a Q5 / Q7 self-check
        passed (h >= 3 and the frozen check). RESUME_EVADE_EXIT: Quit was greyed and the frozen check passed (§3.7.5
        step 4): latch EVADE_EXIT in `scene` from t."""
        self.paused = False
        self.pending = False
        self.on_paused = None
        self.release_needed = False
        if reason == RESUME_EVADE_EXIT:
            self.evade = _EvadeExit(scene, t)

    def _expected_risk(self, t: float) -> float | None:
        r = self.cfg.expected_risk_per_s
        if r is None or r <= 0:
            return None
        return r * max(t, self.cfg.risk_warmup_s)

    def _hero(self, inp: SupervisorInput) -> _Hero | None:
        """The hero this frame, or the last known one while it is not read (with how long it has been missing)."""
        if inp.hp is not None and inp.max_hp is not None:
            self.hero = _Hero(inp.hp, inp.max_hp, inp.blue, inp.mask)
        elif self.hero is not None:
            self.hero.missing_s += inp.dt
        else:
            self.never_seen_s += inp.dt
        return self.hero

    @staticmethod
    def support_certified(inp: SupervisorInput) -> bool:
        """The support is known: certified by its producer, and when empty, certified empty as well."""
        return inp.support_known and (len(inp.support) > 0 or inp.support_empty_ok)

    def _support(self, inp: SupervisorInput, known: bool) -> tuple[SupportEvent, ...]:
        ev = tuple(inp.support)
        if known:
            return ev
        floor = max(1, self.cfg.worst_known_damage, self.worst_seen, max((e.damage for e in ev), default=0))
        return ev + (SupportEvent(UNKNOWN_SOURCE, floor, mask_covers=self.cfg.unknown_mask_covers),)

    def _h(self, inp: SupervisorInput, hero: _Hero, support: Sequence[SupportEvent]) -> tuple[int, str]:
        """(h, basis): hits_to_death against the support; against the encounter's worst known event when the support
        is certified empty (module docstring). Pause stress chunk 20261002_232051 ep 35: a hit to 1 HP with the boss
        submerged left h UNBOUNDED, the tier GREEN and the planner fighting for 15 frames, until a Q4 paused it."""
        h = hits_to_death(hero.hp, hero.blue, mask_intact(hero.mask),
                          ctx_from_support(support, inp.pending_dmg, inp.pending_mask_covers))
        if h != UNBOUNDED:
            return h, H_SUPPORT
        floor = SupportEvent(WORST_SOURCE, max(1, self.cfg.worst_known_damage, self.worst_seen))
        return hits_to_death(hero.hp, hero.blue, mask_intact(hero.mask),
                             ctx_from_support((floor,), inp.pending_dmg, inp.pending_mask_covers)), H_WORST

    def q1_cause(self, t: float) -> str:
        """Q1_HIT when a hit came within POST_HIT_WINDOW_S of t (the quit belongs in its post-hit window), else
        Q1_NO_HIT (frost, pending damage, a start at low HP: the first pausable frame)."""
        return Q1_HIT if self.t_hit is not None and 0.0 <= t - self.t_hit <= POST_HIT_WINDOW_S else Q1_NO_HIT

    def _triggers(self, inp: SupervisorInput, h: int | None, hero: _Hero | None, support: Sequence[SupportEvent],
                  known: bool, basis: str | None = None) -> list[tuple[str, str]]:
        cfg = self.cfg
        out: list[tuple[str, str]] = []
        if h is not None and h <= 1:
            why = f"hits_to_death {h}" + (" against the worst known event (support empty now)" if basis == H_WORST
                                          else "")
            out.append(("Q1", why + ("; after a hit: pause in the post-hit window"
                                     if self.q1_cause(inp.t) == Q1_HIT else "; no hit: first pausable frame")))
        if inp.i2_violated and (inp.escape_s is None or inp.escape_s > cfg.q2_escape_s):
            out.append(("Q2", "I2 broken, no escape within "
                              f"{cfg.q2_escape_s} s" + ("" if inp.escape_s is None else f" ({inp.escape_s:.2f} s)")))
        if h == 2:
            why = q3_threat(support, known)
            if why:
                out.append(("Q3", f"h = 2 and {why}"))
        if self.unpredicted >= cfg.q4_unpredicted_hits:
            out.append(("Q4", f"{self.unpredicted} unpredicted hits"))
        exp = self._expected_risk(inp.t)
        if exp is not None and self.risk_integral > cfg.risk_factor * exp:
            out.append(("Q4", f"risk integral {self.risk_integral:.3g} > {cfg.risk_factor} x {exp:.3g}"))
        q5 = []
        if inp.frame_age_ms > cfg.frame_age_ms:
            q5.append(f"frame age {inp.frame_age_ms:.0f} ms")
        if inp.hud_unreadable_ms > cfg.hud_unreadable_ms and not inp.ending:
            q5.append(f"HUD unreadable {inp.hud_unreadable_ms:.0f} ms")
        lost_ms = max(inp.hero_lost_ms, 1000.0 * (hero.missing_s if hero is not None else self.never_seen_s))
        if lost_ms > cfg.hero_lost_ms and (h is None or h <= 2):
            q5.append(f"hero lost {lost_ms:.0f} ms at h {h}")
        if not inp.scene_known:
            q5.append("unknown scene")
        if inp.overlay_intrusion:
            q5.append("OVERLAY_INTRUSION")
        if inp.tear_streak >= cfg.tear_frames:
            q5.append(f"{inp.tear_streak} torn frames")
        if q5:
            out.append(("Q5", ", ".join(q5)))
        if inp.forced_risk and h is not None and h <= 2:
            clear = inp.forced_clear_s
            if clear is None or clear <= cfg.q6_horizon_s:
                out.append(("Q6", f"FORCED_RISK at h {h}" + ("" if clear is None else f", clear {clear:.2f} s")))
        if inp.focus_lost:
            out.append(("Q7", "FOCUS_LOST"))
        if inp.watchdog:
            out.append(("Q8", "progress watchdog"))
        if inp.capture_lost:
            out.append(("Q9", "capture lost"))
        if inp.permadeath:
            out.append(("Q9", "PERMADEATH"))
        for hook in cfg.hooks:
            for tid in hook(inp) or ():
                out.append((tid, f"hook {getattr(hook, '__name__', 'hook')}"))
        out.extend(self.injected)
        self.injected = []
        return out

    def _arm(self, on_paused: str) -> None:
        self.pending = True
        if _ON_PAUSED_RANK[on_paused] > _ON_PAUSED_RANK[self.on_paused]:
            self.on_paused = on_paused

    def _evade_latch(self, inp: SupervisorInput) -> str | None:
        """Clear the EVADE_EXIT latch when its job is done; returns why it ended (None: still on, or not latched)."""
        ev = self.evade
        if ev is None:
            return None
        why = None
        if inp.scene is not None and ev.scene is not None and inp.scene != ev.scene:
            why = f"left {ev.scene}"
        elif inp.quittable is True:
            why = "quit available"
        elif inp.t - ev.t0 > self.cfg.evade_exit_timeout_s:
            why = f"EVADE_EXIT timeout {self.cfg.evade_exit_timeout_s:.0f} s"
            self.alerted = True
        if why is not None:
            self.evade = None
        return why

    def step(self, inp: SupervisorInput) -> SupervisorDecision:
        cfg = self.cfg
        self.worst_seen = max(self.worst_seen, inp.damage_taken)
        # a hit: damage reported, or the hero's health + blue lower than at the last read (the vision view's HIT_TAKEN
        # can fall on a frame the live loop skipped; degraded_dust check 20261003_114708 ep 0 labelled such a Q1
        # "no hit" while the pause machine, which also reads the HUD drop, timed it as one)
        tot = None if inp.hp is None else inp.hp + inp.blue
        if inp.damage_taken > 0 or (tot is not None and self._hp_tot is not None and tot < self._hp_tot):
            self.t_hit = inp.t
        if tot is not None:
            self._hp_tot = tot
        hero = self._hero(inp)
        known = self.support_certified(inp)
        support = self._support(inp, known)
        h = basis = None
        if hero is not None:
            h, basis = self._h(inp, hero, support)
        self.risk_integral += max(0.0, inp.p_death)
        self.unpredicted += max(0, inp.unpredicted_hits)

        fired = self._triggers(inp, h, hero, support, known, basis)
        evade_end = self._evade_latch(inp)
        if evade_end is not None:
            fired.append(("EVADE_EXIT", f"ended: {evade_end}"))
        ids = {tid for tid, _ in fired}
        reasons = [f"{tid}: {why}" for tid, why in fired]
        ids.discard("EVADE_EXIT")
        tier0 = base_tier(h, inp.plan_s, known)

        if "Q9" in ids:
            self.alerted = True
            return SupervisorDecision(
                tier=RED, h=h, pause_pending=False, quit_requested=False, on_paused=None, allowed=NOTHING,
                restrictions=Restrictions(), triggers=tuple(sorted(ids)), reasons=tuple(reasons), paused=self.paused,
                stop_input=True, release_all=True, alert=True, risk_integral=self.risk_integral,
                unpredicted_hits=self.unpredicted, support_known=known, hero_known=inp.hp is not None,
                evade_exit=self.evade is not None)

        if not self.paused:
            if ids & set(QUIT_TRIGGERS) and self.evade is None:
                self._arm(QUIT)
            if "Q7" in ids:
                self.release_needed = True
                self._arm(SELF_CHECK)
            if "Q5" in ids:
                self._arm(SELF_CHECK)
            if "Q8" in ids:
                self.alerted = True
                self._arm(DIAGNOSE)
            if "Q4" in ids and self.q4 is None:
                self.q4 = next(why for tid, why in fired if tid == "Q4")
            if self.q4 is not None and not self.pending and tier0 == GREEN and inp.pausable is True:
                self._arm(QUIT)
        if self.q4 is not None:
            ids.add("Q4")

        triggered = bool(ids) or self.pending or self.paused
        tier = RED if triggered else tier0
        if self.pending or self.paused:
            self.reasons_latched.extend(r for r in reasons if r not in self.reasons_latched)

        careful = tier in (YELLOW, RED)
        if self.paused:
            allowed = NOTHING
        elif self.pending or self.evade is not None:
            allowed = EVASIVE
        else:
            allowed = set(ALL)
            if hero is None or hero.hp < hero.max_hp:
                allowed.discard(Prim.SILKSKILL)
            if down_slash_ok(inp.over_spikes, inp.over_hazard, tier) is not None:
                allowed.discard(Prim.ATTACK_DOWN)
            if careful and inp.next_hit_may_kill:
                allowed -= DAMAGING
            allowed = frozenset(allowed)
        # Q1a (the person's rule, 2026-10-03): h >= 2 below max HP -> heal first, in any tier (combat.tactics.modes)
        heal_first = hero is not None and h is not None and h >= 2 and hero.hp < hero.max_hp
        restr = Restrictions(heal_first=heal_first, max_punish_hits=1 if careful else None, no_parry=careful,
                             no_killing_blow=careful, no_down_slash_over_hazard=True, no_new_fights=careful)
        return SupervisorDecision(
            tier=tier, h=h, pause_pending=self.pending, quit_requested=self.on_paused == QUIT,
            on_paused=self.on_paused, allowed=allowed, restrictions=restr,
            triggers=tuple(sorted(ids)), reasons=tuple(reasons if reasons else self.reasons_latched[-3:]),
            paused=self.paused, release_all=self.release_needed and self.pending, regain_focus="Q7" in ids,
            alert=self.alerted or self.on_paused == DIAGNOSE, mark_retrain=self.q4 is not None,
            conservative_variant=self.q4 is not None,
            long_planning_ok=tier == GREEN and not self.pending and (not inp.in_encounter or inp.in_safe_window),
            risk_integral=self.risk_integral, unpredicted_hits=self.unpredicted, support_known=known,
            hero_known=inp.hp is not None, evade_exit=self.evade is not None, h_basis=basis,
            q1_cause=self.q1_cause(inp.t) if "Q1" in ids else None, t_hit=self.t_hit)


# ---- §3.5.6 gates ------------------------------------------------------------------------------------------------

def bind_allowed(silk: int, hp: int, max_hp: int, h: int, t_min_s: float, *, injector_band: bool = False,
                 warding_bell: bool = False, perception_margin_s: float = 0.0, p_exposed: float = 0.0,
                 collapsing_ground: bool = False, hazard_in_envelope: bool = False, pause_pending: bool = False,
                 cursed: bool = False) -> Verdict:
    """Bind commit test (§3.5.6). t_min_s: earliest time any in-support tube can reach the hero; p_exposed: the
    probability that one does during the Bind (must be 0 without Warding Bell, <= 5 % with it; equipment audited).
    δ_b = 0.15 s, or 0.05 s with Warding Bell, plus the perception margin either way."""
    why = []
    if pause_pending:
        why.append("PAUSE_PENDING")
    if cursed:
        why.append("cursed (Bind cost unpayable)")
    if silk < BIND_SILK:
        why.append(f"silk {silk} < {BIND_SILK}")
    if not (hp <= max_hp - 3 or h <= 2):
        why.append(f"HP {hp}/{max_hp} and h {h}: not worth a Bind")
    t_bind = T_BIND_INJECTOR_S if injector_band else T_BIND_S
    delta = (DELTA_B_WARDING_S if warding_bell else DELTA_B_S) + perception_margin_s
    if t_min_s < t_bind + delta:
        why.append(f"T_min {t_min_s:.2f} s < {t_bind + delta:.2f} s")
    if p_exposed > (WARDING_MAX_EXPOSURE if warding_bell else 0.0):
        why.append(f"exposure p {p_exposed:.3f}")
    if collapsing_ground:
        why.append("collapsing ground")
    if hazard_in_envelope:
        why.append("hazard in the knockback envelope")
    return Verdict(not why, "BIND", "; ".join(why))


def parry_allowed(clash_logged: bool, hp: int, blue: int, damage: int, tier: str, pause_pending: bool, *,
                  pending_dmg: int = 0, vision_success: float | None = None, lace_guard: bool = False) -> Verdict:
    """Parry whitelist (§3.5.6) for one attack: a clash was seen in the logs, vision tells it reliably (None in oracle
    mode), a failed parry is survivable without the mask (HP + blue - pending damage - D >= 2), never into Lace's guard,
    never in YELLOW / RED or PAUSE_PENDING (the clash freeze swallows a pause; parry i-frames are 0.15 s and stop no
    hazard, probe P11)."""
    why = []
    if not clash_logged:
        why.append("no clash in the logs")
    if vision_success is not None and vision_success < PARRY_VISION_MIN:
        why.append(f"vision success {vision_success:.4f} < {PARRY_VISION_MIN}")
    left = hp + blue - pending_dmg - damage
    if left < 2:
        why.append(f"a failed parry leaves {left} HP")
    if lace_guard:
        why.append("Lace guard stance")
    if tier != GREEN:
        why.append(f"tier {tier}")
    if pause_pending:
        why.append("PAUSE_PENDING")
    return Verdict(not why, "PARRY", "; ".join(why))


def down_slash_allowed(over_spikes: bool, over_hazard: bool, tier: str, pause_pending: bool) -> Verdict:
    """The same rule Supervisor.step applies to ATTACK(down) (down_slash_ok), plus PAUSE_PENDING."""
    why = []
    r = down_slash_ok(over_spikes, over_hazard, tier)
    if r is not None:
        why.append(r)
    if pause_pending:
        why.append("PAUSE_PENDING")
    return Verdict(not why, "DOWN_SLASH", "; ".join(why))


def silk_spend_allowed(silk: int, cost: int, hp: int, max_hp: int, skill: bool = True,
                       reserve_at_full_hp: bool = False) -> Verdict:
    """Keep the Bind silk (§3.5.6): below full HP silk never drops under 9; silk skills only at full HP.
    reserve_at_full_hp (playbook bind.reserve_at_full_hp, off by default): never under 9 at full HP either, so the
    first hit always finds a Bind's silk. Why it is there: with a 9-silk spool the Silkspear at full HP left silk 0-6
    at the hit in all 37 gate / live QUITs (20261002_123347 ... 152649; 3-5 casts, 12-20 silk a fight in run 152649
    i0 / i1), while 26 of them had a Bind-sized window (commit test and the planner's Bind rollout, hero in control)
    within 2 s of the hit. The price is the Silkspear's damage (15 per cast at full HP), to be weighed in a live A/B."""
    why = []
    if silk < cost:
        why.append(f"silk {silk} < cost {cost}")
    if skill and hp < max_hp:
        why.append("silk skill below full HP")
    if hp < max_hp and silk - cost < BIND_SILK:
        why.append(f"would leave {silk - cost} < {BIND_SILK} silk below full HP")
    elif reserve_at_full_hp and silk - cost < BIND_SILK:
        why.append(f"would leave {silk - cost} < {BIND_SILK} silk (Bind reserve at full HP)")
    return Verdict(not why, "SILK", "; ".join(why))
