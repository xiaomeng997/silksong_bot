"""L0 safety filter (DESIGN §3.5.1 "veto plans that break an invariant; hazards are walls", §3.5.6, §3.7.2-3.7.4):
hand-written rules over the planner's candidates, never learned.

    ctx = FilterContext.from_world(ws, decision, h, want_bind=prefs.want_bind, damage=hero_damage)
    ok, why = veto(cands, ctx)                       # [N] allowed, [N] first rule that vetoed (0 = none)
    hz, hz_soft = hazard_flags(kb_hull, kb_flags, ctx)   # Hz(c): knockback envelope into a hazard / a soft gate
    may_kill, k_lo, k_hi = kill_frames(latched, roll.flags, roll.mode, P, ctx)
    u = unpausable(may_kill, ctx, kill_certified(S, k_hi, T1, ctx, frame_time))   # U(c): vetoed (R_KILL)

Rules:
  ALLOW     the supervisor's allowlist (PAUSE_PENDING / EVADE_EXIT: evasive only; YELLOW / RED: the damaging
            primitives whose next landed hit may kill, when the support is not certified or h < 2, i.e. when no kill
            can be certified below; ATTACK(down) over spikes never, over any hazard outside GREEN).
  SILK      Silkspear (4 silk) only through supervisor.silk_spend_allowed: silk skills at full HP only, never leaving
            fewer than 9 silk below full HP (the Bind reserve, §3.5.6), nor at full HP when the playbook asks for the
            reserve there too (bind.reserve_at_full_hp, FilterContext.silk_reserve_full_hp).
  BIND      the Bind macro only when the tactics' commit test passed (supervisor.bind_allowed: silk 9, HP <= max - 3
            or h <= 2, T_min >= 1.37 + 0.15 s, not PAUSE_PENDING); the planner's own S check then covers its rollout.
  DOWN      ATTACK(down) never with a hazard under the hero (§3.5.6), and not over any hazard outside GREEN.
  Hz        the candidate's knockback envelope (knockback.knockback_hull over all its frames) touches a hazard (a wall,
            §3.5.6); when h <= 2 the arena gates count as soft hazards (I2). KF_UNKNOWN (frame-time model broken)
            makes every candidate Hz when hazards exist: unknown is never safe.
  U / KILL  I3 for the killing blow, a hard veto (R_KILL): a window where pause / quit is out of reach for more than
            0.5 s may be entered uncertified only in GREEN at full HP with h >= 3 (one worst event later h >= 2;
            §3.7.3: YELLOW forbids a possibly killing blow). Bell Beast's only such window the bot can start itself is
            the boss-death slow motion (1.35-1.38 s real, quit map BossDeathSlow), started by a killing blow.
            Certified kill (task "STUCK at 15 HP", 2026-10-04): otherwise the blow is allowed only when the hero is
            certified safe through the slow motion: h >= 2, the support certified, and the candidate's whole rollout
            (hit effects, both branches) out of every support tube (S = 0) with the latest frame its killing hit can
            land plus KILL_WINDOW_S + KILL_MARGIN_S still inside the rollout. Why that window: from the killing hit to
            the first pausable frame the game advances 0.150-0.167 s of game time (95-101 real frames, 1.65-1.72 s;
            120 kills of run 20261003_175813, BossDeathSlow 0.1 / 1.15 / 0.1 at 0.05 speed), and the support's tubes
            (the boss's attacks, the bells in flight) are in game time. Without it, h = 2 with the boss at or below a
            hit's bound was a deadlock: no attack, no silk, no Bind, YELLOW until the 240 s time box.
            "May kill" (kill_frames) needs no geometry: every damaging press of the candidate (attack and quick-cast
            edges of its hold-filtered stream; the prefix's and an attack running at the start count towards the sum)
            is assumed to land, at the crest's / tools' bound for that attack (combat.hero_damage); the candidate may
            kill once the sum reaches the least HP of an enemy (kill_hp_world: minus 3 sigma of a counted HP; a boss
            whose HP is unknown counts as 0). Its killing hit lands no earlier than the press that reaches the sum and
            no later than the last press's attack onset in the nominal lane (else the press plus the attack queue)
            plus the attack's hit window (planner.WINDOWS v2: side 6, up 8, down spike 16, Silkspear 20 frames) plus
            LANE_SLACK_F for the other timing lanes.
"""
import math
from dataclasses import dataclass, field

import numba
import numpy as np

from ssbot.combat.candidates import CandidateSet
from ssbot.combat.hero_damage import HeroDamage
from ssbot.core.primitives import N_PRIM, Prim
from ssbot.core.worldstate import IFRAME_BLOCKED, Kind, WorldState
from ssbot.knowledge.kinematics import (B_ATTACK, B_DOWN, B_QUICKCAST, B_UP, F_ATTACKING, M_CAST, M_DS_ANTIC,
                                        M_DS_SPIKE)
from ssbot.knowledge.knockback import KF_UNKNOWN
from ssbot.safety.supervisor import GREEN, SupervisorDecision, silk_spend_allowed

SILKSPEAR_COST = 4
R_ALLOW, R_SILK, R_BIND, R_DOWN, R_KILL = 1, 2, 3, 4, 5
REASONS = {0: "", R_ALLOW: "supervisor allowlist", R_SILK: "silk reserve", R_BIND: "bind commit test",
           R_DOWN: "down-slash over a hazard", R_KILL: "uncertified killing blow"}
KILL_WINDOW_S = 0.17        # game s from the killing hit to the first pausable frame (measured max 0.167 s)
KILL_MARGIN_S = 0.15        # the support "empty for the freeze plus margin"
LANE_SLACK_F = 4            # attack onsets of the other timing lanes around the nominal one
QUEUE_F = 10                # a press that cannot act waits in the attack queue (attack_queue_steps 8 at 50 Hz) + 1
HIT_END_F = (6, 8, 16, 20)  # a hit lands at most this many frames after the onset: side, up, down spike, Silkspear
VISION_HP_Z = 3.0           # a counted HP (vision) may be this many sigma lower
_BIT = {p: 1 << int(p) for p in Prim}


@dataclass
class FilterContext:
    allowed_mask: np.ndarray
    hp: int = 0
    max_hp: int = 0
    silk: int = 0
    h: int | None = None
    tier: str = "YELLOW"
    pause_pending: bool = False
    want_bind: bool = False
    silk_reserve_full_hp: bool = False   # playbook bind.reserve_at_full_hp: keep 9 silk at full HP too
    hazards: list[tuple[float, float, float, float]] = field(default_factory=list)
    soft: list[tuple[float, float, float, float]] = field(default_factory=list)
    hero_x: float = 0.0
    support_known: bool = False             # the supervisor's support certification (SupervisorDecision.support_known)
    kill_hp: float | None = None            # least HP an enemy may have now (kill_hp_world); None: none can die
    damage: HeroDamage | None = None        # per-attack bounds; None: unknown, every press may kill

    @classmethod
    def from_world(cls, ws: WorldState, d: SupervisorDecision | None, h: int | None, want_bind: bool = False,
                   damage: HeroDamage | None = None) -> "FilterContext":
        allowed = d.allowed_mask if d is not None else np.ones(N_PRIM, bool)
        hazards = []
        for e in ws.entities:
            for b in e.dmg_boxes:
                if b.active and b.hazard not in IFRAME_BLOCKED and b.poly:
                    p = np.asarray(b.poly, np.float64)
                    hazards.append((p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()))
        soft = []
        if h is not None and h <= 2:
            for g in ws.terrain.gates or ():
                if g.enabled:
                    soft.append(tuple(g.box))
        return cls(allowed_mask=allowed, hp=int(ws.res.hp.v or 0), max_hp=int(ws.res.hp_max.v or 0),
                   silk=int(ws.res.silk.v or 0), h=h, tier=d.tier if d is not None else "YELLOW",
                   pause_pending=bool(d is not None and d.pause_pending), want_bind=want_bind, hazards=hazards,
                   soft=soft, hero_x=float(ws.hero.pos.v[0]), support_known=bool(d is not None and d.support_known),
                   kill_hp=kill_hp_world(ws), damage=damage)


def veto(cands: CandidateSet, ctx: FilterContext) -> tuple[np.ndarray, np.ndarray]:
    """([N] allowed, [N] reason code of the first rule that vetoed)."""
    why = np.zeros(len(cands.prim_bits), np.int64)
    ok = cands.allowed(ctx.allowed_mask)
    why[~ok] = R_ALLOW
    spear = (cands.prim_bits & _BIT[Prim.SILKSKILL]) != 0
    if spear.any() and not silk_spend_allowed(ctx.silk, SILKSPEAR_COST, ctx.hp, ctx.max_hp, skill=True,
                                              reserve_at_full_hp=ctx.silk_reserve_full_hp).ok:
        why[ok & spear] = R_SILK
        ok &= ~spear
    bind = (cands.prim_bits & _BIT[Prim.BIND]) != 0
    if bind.any() and (not ctx.want_bind or ctx.pause_pending):
        why[ok & bind] = R_BIND
        ok &= ~bind
    down = (cands.prim_bits & _BIT[Prim.ATTACK_DOWN]) != 0
    if down.any() and ctx.hazards:
        under = any(b[0] - 2.0 <= ctx.hero_x <= b[2] + 2.0 for b in ctx.hazards)
        if under or ctx.tier != GREEN:
            why[ok & down] = R_DOWN
            ok &= ~down
    return ok, why


def _touch(hull: np.ndarray, boxes: list[tuple[float, float, float, float]]) -> np.ndarray:
    out = np.zeros(len(hull), bool)
    valid = hull[:, 0] <= hull[:, 2]
    for b in boxes:
        out |= valid & (hull[:, 0] < b[2]) & (hull[:, 2] > b[0]) & (hull[:, 1] < b[3]) & (hull[:, 3] > b[1])
    return out


def hazard_flags(kb_hull: np.ndarray | None, kb_flags: np.ndarray | None, ctx: FilterContext
                 ) -> tuple[np.ndarray, np.ndarray]:
    """(Hz [N], Hz_soft [N]) from the per-candidate knockback hull [N, 4]."""
    if kb_hull is None:
        return np.zeros(0, bool), np.zeros(0, bool)
    hz = _touch(kb_hull, ctx.hazards)
    if ctx.hazards and kb_flags is not None:
        hz |= (kb_flags & KF_UNKNOWN) != 0
    return hz, _touch(kb_hull, ctx.soft)


def i3_kill_allowed(ctx: FilterContext) -> bool:
    """I3 lets the hero enter the boss-death slow motion uncertified: GREEN, full HP and h >= 3."""
    return ctx.tier == GREEN and ctx.max_hp > 0 and ctx.hp >= ctx.max_hp and ctx.h is not None and ctx.h >= 3


def unpausable(may_kill: np.ndarray, ctx: FilterContext, certified: np.ndarray | None = None) -> np.ndarray:
    """U(c) for the boss-death slow motion: a candidate that may land the killing blow, unless I3 allows entering
    (GREEN, full HP and h >= 3) or the candidate is certified safe through it (kill_certified)."""
    u = np.asarray(may_kill, bool) & (not i3_kill_allowed(ctx))
    if certified is not None:
        u &= ~np.asarray(certified, bool)
    return u


def kill_window_frames(frame_time: float) -> int:
    """Rollout frames the support must stay off the hero after the latest killing hit: the slow motion plus margin."""
    return int(math.ceil((KILL_WINDOW_S + KILL_MARGIN_S) / frame_time - 1e-9))


def kill_certified(S: np.ndarray, k_hi: np.ndarray, T1: int, ctx: FilterContext, frame_time: float) -> np.ndarray:
    """[N]: certified safe through the kill's slow motion (module docstring): h >= 2, the support certified, S = 0
    over the whole rollout, and the latest killing hit plus the window inside the rollout's T1 frames."""
    S = np.asarray(S, bool)
    if ctx.h is None or ctx.h < 2 or not ctx.support_known:
        return np.zeros(len(S), bool)
    k_hi = np.asarray(k_hi, np.int64)
    return ~S & (k_hi >= 0) & (k_hi + kill_window_frames(frame_time) <= T1 - 1)


def kill_hp_world(ws: WorldState, z: float = VISION_HP_Z) -> float | None:
    """The least HP an enemy may have now: over the bosses and enemies with an HP estimate, hp - z sigma (the oracle's
    is exact; a counted HP misses hits); a boss without one counts as 0 (unknown is never safe); None: none."""
    out = None
    for e in ws.entities:
        if e.kind not in (Kind.BOSS, Kind.ENEMY):
            continue
        h = e.hp_est
        if h is None or h.conf <= 0 or h.v is None:
            if e.kind == Kind.BOSS:
                out = 0.0
            continue
        if h.v <= 0:
            continue
        sig = h.sigma if math.isfinite(h.sigma) else float(h.v)
        v = max(0.0, float(h.v) - z * sig)
        out = v if out is None else min(out, v)
    return out


def kill_frames(latched: np.ndarray, flags: np.ndarray, mode: np.ndarray, P: int, ctx: FilterContext
                ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(may_kill [N], k_lo [N], k_hi [N]): the candidate's own presses may land the killing blow; the earliest and the
    latest rollout frame that blow can land (module docstring). latched [N, P + T] is the hold-filtered stream (frame k
    applies latched[:, k - 1], P of them the prefix), flags / mode [N, T1] the nominal lane's."""
    N = latched.shape[0]
    may = np.zeros(N, np.bool_)
    lo = np.full(N, -1, np.int64)
    hi = np.full(N, -1, np.int64)
    if ctx.kill_hp is None or N == 0:
        return may, lo, hi
    dmg = ctx.damage
    nail = math.inf if dmg is None else float(dmg.nail)
    spear = math.inf if dmg is None else float(dmg.spear)
    _kill_kernel(np.ascontiguousarray(latched, np.int64), np.ascontiguousarray(flags, np.int64),
                 np.ascontiguousarray(mode, np.int64), int(P), nail, spear, float(ctx.kill_hp), QUEUE_F, LANE_SLACK_F,
                 np.array(HIT_END_F, np.int64), may, lo, hi)
    return may, lo, hi


@numba.njit(cache=True)
def _kill_kernel(latched, flags, mode, P, nail, spear, hp, queue_f, slack, ends, may, lo, hi):
    N, L = latched.shape
    T1 = flags.shape[1]
    for c in range(N):
        cum = 0.0
        own = False
        k_lo = -1
        k_hi = -1
        m0 = mode[c, 0]
        # an attack or a cast already running at the start: one more hit, from frame 1 on
        if (flags[c, 0] & F_ATTACKING) != 0 or m0 == M_DS_ANTIC or m0 == M_DS_SPIKE or m0 == M_CAST:
            cum += spear if m0 == M_CAST else nail
            if cum >= hp:
                k_lo = 1
                k_hi = (ends[3] if m0 == M_CAST else ends[2]) + slack
        for j in range(L):
            a = latched[c, j]
            prev = latched[c, j - 1] if j > 0 else 0
            atk = (a & B_ATTACK) != 0 and (prev & B_ATTACK) == 0
            cst = (a & B_QUICKCAST) != 0 and (prev & B_QUICKCAST) == 0
            if not (atk or cst):
                continue
            fr = j + 1
            if cst:
                d = spear
                end = ends[3]
            else:
                d = nail
                if (a & B_DOWN) != 0 and (a & B_UP) == 0:
                    end = ends[2]
                elif (a & B_UP) != 0:
                    end = ends[1]
                else:
                    end = ends[0]
            # the nominal lane's onset of this press's attack, else the press waits in the queue at most queue_f
            on = -1
            for k in range(max(fr, 1), min(T1, fr + queue_f + 1)):
                if cst:
                    if mode[c, k] == M_CAST and mode[c, k - 1] != M_CAST:
                        on = k
                        break
                elif ((flags[c, k] & F_ATTACKING) != 0 and (flags[c, k - 1] & F_ATTACKING) == 0) or (
                        (mode[c, k] == M_DS_ANTIC or mode[c, k] == M_DS_SPIKE)
                        and not (mode[c, k - 1] == M_DS_ANTIC or mode[c, k - 1] == M_DS_SPIKE)):
                    on = k
                    break
            e = (on if on >= 0 else fr + queue_f) + end + slack
            cum += d
            if j >= P:
                own = True
            if k_lo < 0 and cum >= hp:
                k_lo = fr
            if k_lo >= 0:
                k_hi = max(k_hi, e)
        if own and k_lo >= 0:
            may[c] = True
            lo[c] = k_lo
            hi[c] = k_hi
