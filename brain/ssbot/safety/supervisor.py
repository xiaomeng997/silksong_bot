"""Supervisor v1 (DESIGN §3.7.3-3.7.4, the §3.5.1 supervisor row, the §3.5.6 Bind / parry / down-slash gates; M2 W5):
risk tier, triggers Q1-Q9 and P1, the per-attempt risk integral and unpredicted-hit counter, PAUSE_PENDING, and the
primitive restrictions the planner and tactics must obey. Pure logic, 60 Hz: one Supervisor per attempt.

    sup = Supervisor(SupervisorConfig(expected_risk_per_s=1e-4))
    d = sup.step(SupervisorInput(t=..., dt=1/60, hp=5, max_hp=5, support=(SupportEvent("Bone Beast", 2),), plan_s=0))
    if d.pause_pending: hand the keyboard to safety.pause_quit.PauseQuit (goal "QUIT" if d.quit_requested)
    candidates = [c for c in candidates if c.primitive not in d.forbidden]
    # training: sup.step(input_from_state(state, t, support=...)) fills HP, mask and availability from STATE

Tiers: GREEN h >= 3 and the chosen plan has S = 0; YELLOW h = 2, or S = 1 (or no plan yet) with h >= 3; RED any
trigger. Triggers (§3.7.4):
  Q1 h <= 1 (a Fractured Mask just broken at 1 HP included)                  -> PAUSE_PENDING, quit
  Q2 I2 broken and no candidate leaves the exposure within 0.2 s              -> PAUSE_PENDING, quit
  Q3 h = 2 with a mask-bypassing, multi-hit / multi-instance, hazard or CriticalDamage threat in the support
                                                                              -> PAUSE_PENDING, quit
  Q4 two unpredicted hits in one attempt, or the risk integral > 2x the training expectation
                                                                              -> quit at the next pausable GREEN frame,
                                                                                 conservative variant, retrain flag
  Q5 frame age > 50 ms, HUD unreadable > 100 ms (not in ENDING), hero lost > 300 ms with h <= 2, unknown scene,
     OVERLAY_INTRUSION, consecutive tearing                                   -> pause, self-check (resume only with
                                                                                 h >= 3 and the frozen check passing)
  Q6 FORCED_RISK with h <= 2                                                  -> PAUSE_PENDING, quit
  Q7 FOCUS_LOST                                                               -> release all, regain focus, pause,
                                                                                 self-check
  Q8 progress watchdog (hook)                                                 -> pause, diagnose, alert
  Q9 capture lost or PERMADEATH (hook)                                        -> stop all input, alert
  P1 planning that needs > 3 ms only in GREEN outside A/B encounters, or in GREEN inside a registered safe window.
Q8 / Q9 come from input flags or from SupervisorConfig.hooks (callables returning trigger ids).

PAUSE_PENDING forbids every action that can start a FreezeMoment (all attacks, including ones that may crit: a
Wanderer crit is a 0.2 s HeroDamageShort freeze, m0 §2.4; parry / nail clash: NailClashEffect; down-slash; tools;
silk skills; Bind; Clawline, which hits enemies) and starting any interaction (talk, doors, pickups, levers, Needolin:
they set BlockingInteractable or disablePause, m0:N15). Only evasive movement stays allowed, and I2 keeps applying.
PAUSE_PENDING is sticky until the pause is confirmed (notify_paused) or the attempt ends: a pause does not end the
threat, the world resumes where it stopped.

YELLOW: heal first; punish with at most 1 hit; no parry; no blow that may kill (the kill freeze swallows a pause);
no down-slash over a hazard; no new fights. Rules that hold at every tier (§3.5.6): silk skills only at full HP;
never down-slash over spikes (any hazard flagged by the planner is treated so).
"""
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from ssbot.safety.hits_to_death import (MASK_UNKNOWN, SupportEvent, ctx_from_support, hits_to_death,
                                        mask_intact, mask_state)
from ssbot.safety.invariants import Verdict
from ssbot.safety.pause_quit import availability_from_state

GREEN, YELLOW, RED = "GREEN", "YELLOW", "RED"
QUIT, DIAGNOSE, SELF_CHECK = "QUIT", "DIAGNOSE", "SELF_CHECK"     # what to do once the pause is confirmed
_ON_PAUSED_RANK = {None: 0, SELF_CHECK: 1, DIAGNOSE: 2, QUIT: 3}

# Planner primitives (§3.5.4), split by what the supervisor may allow.
EVASIVE = frozenset({"MOVE", "JUMP", "DOUBLEJUMP", "DASH", "WALLJUMP", "GLIDE", "WAIT", "ABORT"})
ATTACKS = frozenset({"ATTACK_SIDE", "ATTACK_UP", "ATTACK_DOWN", "ATTACK_CHARGED"})
FREEZE_CAPABLE = ATTACKS | {"PARRY", "TOOL", "SILKSKILL", "BIND", "CLAWLINE"}
INTERACTIONS = frozenset({"INTERACT", "NEEDOLIN", "TAUNT"})
DAMAGING = ATTACKS | {"TOOL", "SILKSKILL", "CLAWLINE"}           # can land a killing blow
PRIMITIVES = EVASIVE | FREEZE_CAPABLE | INTERACTIONS
PAUSE_PENDING_FORBIDDEN = PRIMITIVES - EVASIVE

QUIT_TRIGGERS = ("Q1", "Q2", "Q3", "Q6")

# §3.5.6 constants
BIND_SILK = 9                  # SilkSpool.BindCost (m0 §2.5); IsAnyCursed makes it unpayable
T_BIND_S = 1.37                # Bind duration
T_BIND_INJECTOR_S = 0.89       # with Injector Band
DELTA_B_S = 0.15               # Bind margin, plus the perception margin
DELTA_B_WARDING_S = 0.05       # with Warding Bell (audited equipped), allowing <= 5 % exposure
WARDING_MAX_EXPOSURE = 0.05
PARRY_VISION_MIN = 0.995       # vision G1 success on the attack's tell


@dataclass(slots=True)
class SupervisorConfig:
    q2_escape_s: float = 0.2
    q4_unpredicted_hits: int = 2
    risk_factor: float = 2.0
    expected_risk_per_s: float | None = None   # training expectation of the integral's growth; None: Q4 by hits only
    risk_warmup_s: float = 5.0                 # the expectation is never taken over less than this
    frame_age_ms: float = 50.0
    hud_unreadable_ms: float = 100.0
    hero_lost_ms: float = 300.0
    tear_frames: int = 3
    hooks: tuple[Callable[["SupervisorInput"], Iterable[str]], ...] = ()


@dataclass(slots=True)
class SupervisorInput:
    t: float                                   # real seconds since the attempt started
    dt: float = 1 / 60
    hp: int = 0
    max_hp: int = 0
    blue: int = 0
    mask: str = MASK_UNKNOWN                   # hits_to_death.MASK_* (audit)
    support: Sequence[SupportEvent] = ()       # worst events of the in-support threat tubes now
    pending_dmg: int = 0
    pending_mask_covers: bool = False
    plan_s: int | None = None                  # S of the chosen plan (0/1); None: no plan yet (treated as S = 1)
    forced_risk: bool = False                  # no candidate with S = 0 this frame
    i2_violated: bool = False
    escape_s: float | None = None              # least time any candidate needs to leave the I2 exposure (None: none)
    unpredicted_hits: int = 0                  # hero hits this frame that no in-support tube covered
    p_death: float = 0.0                       # this frame's death risk (sum of p * overlap of the chosen plan)
    pausable: bool = True                      # availability model (pause_quit.availability_* / quit map)
    quittable: bool = True
    frame_age_ms: float = 0.0
    hud_unreadable_ms: float = 0.0
    hero_lost_ms: float = 0.0
    scene_known: bool = True
    overlay_intrusion: bool = False
    tear_streak: int = 0
    ending: bool = False                       # ENDING screen mode: HUD loss is expected there
    focus_lost: bool = False
    watchdog: bool = False                     # Q8
    capture_lost: bool = False                 # Q9
    permadeath: bool = False                   # Q9
    next_hit_may_kill: bool = False            # an enemy in reach could die from the next landed hit
    over_hazard: bool = False                  # a down-slash here passes over a hazard
    in_encounter: bool = False                 # inside an A/B encounter (P1)
    in_safe_window: bool = False               # a registered safe window: stagger, between waves (P1)


@dataclass(slots=True, frozen=True)
class Restrictions:
    heal_first: bool = False
    max_punish_hits: int | None = None         # None: no limit
    no_parry: bool = False
    no_killing_blow: bool = False
    no_down_slash_over_hazard: bool = True     # always for spikes; YELLOW for every hazard
    no_new_fights: bool = False


@dataclass(slots=True, frozen=True)
class SupervisorDecision:
    tier: str
    h: int
    pause_pending: bool
    quit_requested: bool
    on_paused: str | None                      # QUIT / DIAGNOSE / SELF_CHECK once the pause is confirmed
    forbidden: frozenset[str]
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


def input_from_state(s: dict, t: float, support: Sequence[SupportEvent] = (), **kw) -> SupervisorInput:
    """Oracle mode (training): the SupervisorInput fields STATE answers exactly (health, blue, max health, the audited
    Fractured Mask, pause / quit availability from the PauseGate, window focus). Planner fields (support, plan_s,
    forced_risk, ...) come from the caller; until W3 / W4 exist an encounter's worst-case support stands in."""
    hero = s.get("hero") or {}
    avail = availability_from_state(s)
    base = dict(t=t, dt=float(s.get("udt") or 1 / 60), hp=int(hero.get("health") or 0),
                max_hp=int(hero.get("max_health") or 0), blue=int(hero.get("health_blue") or 0),
                mask=mask_state(hero.get("fractured_mask")), support=tuple(support), pausable=avail.pause,
                quittable=avail.quit, focus_lost=s.get("focus") is False)
    base.update(kw)
    return SupervisorInput(**base)


def base_tier(h: int, plan_s: int | None) -> str:
    if h >= 3 and plan_s == 0:
        return GREEN
    if h >= 2:
        return YELLOW
    return RED


def q3_threat(support: Sequence[SupportEvent]) -> str | None:
    """Why the support makes h = 2 a quit (Q3), or None."""
    for e in support:
        if not e.mask_covers:
            return f"{e.source} bypasses the mask"
        if e.hits > 1:
            return f"{e.source} is a {e.hits}-hit event"
        if e.hazard:
            return f"{e.source} is a hazard"
        if e.critical:
            return f"{e.source} deals CriticalDamage"
    sources = {e.source for e in support}
    if len(sources) > 1:
        return f"{len(sources)} threat instances in support"
    return None


class Supervisor:
    """Per-attempt state: risk integral, unpredicted hits, and the PAUSE_PENDING / Q4 latches."""

    def __init__(self, cfg: SupervisorConfig | None = None):
        self.cfg = cfg or SupervisorConfig()
        self.reset()

    def reset(self) -> None:
        """A new attempt."""
        self.risk_integral = 0.0
        self.unpredicted = 0
        self.pending = False
        self.on_paused: str | None = None
        self.q4: str | None = None              # latched Q4 reason
        self.paused = False
        self.release_needed = False
        self.alerted = False
        self.reasons_latched: list[str] = []

    def notify_paused(self) -> None:
        """The pause loop confirmed the pause (PAUSE_MENU seen)."""
        self.paused = True
        self.pending = False

    def notify_resumed(self) -> None:
        """A self-check resume (Continue + Submit) took effect; the attempt goes on."""
        self.paused = False
        self.on_paused = None
        self.release_needed = False

    def _expected_risk(self, t: float) -> float | None:
        r = self.cfg.expected_risk_per_s
        if r is None or r <= 0:
            return None
        return r * max(t, self.cfg.risk_warmup_s)

    def _triggers(self, inp: SupervisorInput, h: int) -> list[tuple[str, str]]:
        cfg = self.cfg
        out: list[tuple[str, str]] = []
        if h <= 1:
            out.append(("Q1", f"hits_to_death {h}"))
        if inp.i2_violated and (inp.escape_s is None or inp.escape_s > cfg.q2_escape_s):
            out.append(("Q2", "I2 broken, no escape within "
                              f"{cfg.q2_escape_s} s" + ("" if inp.escape_s is None else f" ({inp.escape_s:.2f} s)")))
        if h == 2:
            why = q3_threat(inp.support)
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
        if inp.hero_lost_ms > cfg.hero_lost_ms and h <= 2:
            q5.append(f"hero lost {inp.hero_lost_ms:.0f} ms at h {h}")
        if not inp.scene_known:
            q5.append("unknown scene")
        if inp.overlay_intrusion:
            q5.append("OVERLAY_INTRUSION")
        if inp.tear_streak >= cfg.tear_frames:
            q5.append(f"{inp.tear_streak} torn frames")
        if q5:
            out.append(("Q5", ", ".join(q5)))
        if inp.forced_risk and h <= 2:
            out.append(("Q6", f"FORCED_RISK at h {h}"))
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
        return out

    def _arm(self, on_paused: str) -> None:
        self.pending = True
        if _ON_PAUSED_RANK[on_paused] > _ON_PAUSED_RANK[self.on_paused]:
            self.on_paused = on_paused

    def step(self, inp: SupervisorInput) -> SupervisorDecision:
        ctx = ctx_from_support(inp.support, inp.pending_dmg, inp.pending_mask_covers)
        h = hits_to_death(inp.hp, inp.blue, mask_intact(inp.mask), ctx)
        self.risk_integral += max(0.0, inp.p_death)
        self.unpredicted += max(0, inp.unpredicted_hits)

        fired = self._triggers(inp, h)
        ids = {tid for tid, _ in fired}
        reasons = [f"{tid}: {why}" for tid, why in fired]
        tier0 = base_tier(h, inp.plan_s)

        if "Q9" in ids:
            self.alerted = True
            return SupervisorDecision(
                tier=RED, h=h, pause_pending=False, quit_requested=False, on_paused=None, forbidden=PRIMITIVES,
                restrictions=Restrictions(), triggers=tuple(sorted(ids)), reasons=tuple(reasons), paused=self.paused,
                stop_input=True, release_all=True, alert=True, risk_integral=self.risk_integral,
                unpredicted_hits=self.unpredicted)

        if not self.paused:
            if ids & set(QUIT_TRIGGERS):
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
            if self.q4 is not None and not self.pending and tier0 == GREEN and inp.pausable:
                self._arm(QUIT)
        if self.q4 is not None:
            ids.add("Q4")

        triggered = bool(ids) or self.pending or self.paused
        tier = RED if triggered else tier0
        if self.pending or self.paused:
            self.reasons_latched.extend(r for r in reasons if r not in self.reasons_latched)

        forbidden = set()
        if inp.hp < inp.max_hp:
            forbidden.add("SILKSKILL")
        if inp.over_hazard:
            forbidden.add("ATTACK_DOWN")
        careful = tier in (YELLOW, RED)
        if careful:
            forbidden.add("PARRY")
            if inp.next_hit_may_kill:
                forbidden |= DAMAGING
        if self.pending:
            forbidden |= PAUSE_PENDING_FORBIDDEN
        if self.paused:
            forbidden = set(PRIMITIVES)
        restr = Restrictions(heal_first=careful, max_punish_hits=1 if careful else None, no_parry=careful,
                             no_killing_blow=careful, no_down_slash_over_hazard=True, no_new_fights=careful)
        return SupervisorDecision(
            tier=tier, h=h, pause_pending=self.pending, quit_requested=self.on_paused == QUIT,
            on_paused=self.on_paused, forbidden=frozenset(forbidden), restrictions=restr,
            triggers=tuple(sorted(ids)), reasons=tuple(reasons if reasons else self.reasons_latched[-3:]),
            paused=self.paused, release_all=self.release_needed and self.pending, regain_focus="Q7" in ids,
            alert=self.alerted or self.on_paused == DIAGNOSE, mark_retrain=self.q4 is not None,
            conservative_variant=self.q4 is not None,
            long_planning_ok=tier == GREEN and not self.pending and (not inp.in_encounter or inp.in_safe_window),
            risk_integral=self.risk_integral, unpredicted_hits=self.unpredicted)


# ---- §3.5.6 gates ------------------------------------------------------------------------------------------------

def bind_allowed(silk: int, hp: int, max_hp: int, h: int, t_min_s: float, *, injector_band: bool = False,
                 warding_bell: bool = False, perception_margin_s: float = 0.0, p_exposed: float = 0.0,
                 collapsing_ground: bool = False, hazard_in_envelope: bool = False, pause_pending: bool = False,
                 cursed: bool = False) -> Verdict:
    """Bind commit test (§3.5.6). t_min_s: earliest time any in-support tube can reach the hero; p_exposed: the
    probability that one does during the Bind (must be 0 without Warding Bell, <= 5 % with it; equipment audited)."""
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
    delta = DELTA_B_WARDING_S if warding_bell else DELTA_B_S + perception_margin_s
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
                  vision_success: float | None = None, lace_guard: bool = False) -> Verdict:
    """Parry whitelist (§3.5.6) for one attack: a clash was seen in the logs, vision tells it reliably (None in oracle
    mode), a failed parry is survivable without the mask (HP - D >= 2), never into Lace's guard, never in YELLOW / RED
    or PAUSE_PENDING (the clash freeze swallows a pause; parry i-frames are 0.15 s and stop no hazard, probe P11)."""
    why = []
    if not clash_logged:
        why.append("no clash in the logs")
    if vision_success is not None and vision_success < PARRY_VISION_MIN:
        why.append(f"vision success {vision_success:.4f} < {PARRY_VISION_MIN}")
    if hp + blue - damage < 2:
        why.append(f"a failed parry leaves {hp + blue - damage} HP")
    if lace_guard:
        why.append("Lace guard stance")
    if tier != GREEN:
        why.append(f"tier {tier}")
    if pause_pending:
        why.append("PAUSE_PENDING")
    return Verdict(not why, "PARRY", "; ".join(why))


def down_slash_allowed(over_spikes: bool, over_hazard: bool, tier: str, pause_pending: bool) -> Verdict:
    why = []
    if over_spikes:
        why.append("over spikes")
    if over_hazard and tier != GREEN:
        why.append(f"over a hazard in {tier}")
    if pause_pending:
        why.append("PAUSE_PENDING")
    return Verdict(not why, "DOWN_SLASH", "; ".join(why))


def silk_spend_allowed(silk: int, cost: int, hp: int, max_hp: int, skill: bool = True) -> Verdict:
    """Keep the Bind silk (§3.5.6): below full HP silk never drops under 9; silk skills only at full HP."""
    why = []
    if silk < cost:
        why.append(f"silk {silk} < cost {cost}")
    if skill and hp < max_hp:
        why.append("silk skill below full HP")
    if hp < max_hp and silk - cost < BIND_SILK:
        why.append(f"would leave {silk - cost} < {BIND_SILK} silk below full HP")
    return Verdict(not why, "SILK", "; ".join(why))
