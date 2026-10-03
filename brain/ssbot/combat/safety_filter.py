"""L0 safety filter (DESIGN §3.5.1 "veto plans that break an invariant; hazards are walls", §3.5.6, §3.7.2-3.7.4):
hand-written rules over the planner's candidates, never learned.

    ctx = FilterContext.from_world(ws, decision, h, want_bind=prefs.want_bind)
    ok, why = veto(cands, ctx)                       # [N] allowed, [N] first rule that vetoed (0 = none)
    hz, hz_soft = hazard_flags(kb_hull, kb_flags, ctx)   # Hz(c): knockback envelope into a hazard / a soft gate
    u = unpausable(may_kill, ctx)                    # U(c): a killing blow outside the I3 conditions

Rules:
  ALLOW     the supervisor's allowlist (PAUSE_PENDING / EVADE_EXIT: evasive only; YELLOW / RED: no damaging primitive
            when the next landed hit may kill; ATTACK(down) over spikes never, over any hazard outside GREEN).
  SILK      Silkspear (4 silk) only through supervisor.silk_spend_allowed: silk skills at full HP only, never leaving
            fewer than 9 silk below full HP (the Bind reserve, §3.5.6), nor at full HP when the playbook asks for the
            reserve there too (bind.reserve_at_full_hp, FilterContext.silk_reserve_full_hp).
  BIND      the Bind macro only when the tactics' commit test passed (supervisor.bind_allowed: silk 9, HP <= max - 3
            or h <= 2, T_min >= 1.37 + 0.15 s, not PAUSE_PENDING); the planner's own S check then covers its rollout.
  DOWN      ATTACK(down) never with a hazard under the hero (§3.5.6), and not over any hazard outside GREEN.
  Hz        the candidate's knockback envelope (knockback.knockback_hull over all its frames) touches a hazard (a wall,
            §3.5.6); when h <= 2 the arena gates count as soft hazards (I2). KF_UNKNOWN (frame-time model broken)
            makes every candidate Hz when hazards exist: unknown is never safe.
  U         I3: a window where pause / quit is out of reach for more than 0.5 s may be entered only at full HP with
            h >= 3 (one worst event later h >= 2). Bell Beast's only such window the bot can start itself is the
            boss-death slow motion (1.35-1.38 s, quit map BossDeathSlow), started by a killing blow.
"""
from dataclasses import dataclass, field

import numpy as np

from ssbot.combat.candidates import CandidateSet
from ssbot.core.primitives import N_PRIM, Prim
from ssbot.core.worldstate import IFRAME_BLOCKED, WorldState
from ssbot.knowledge.knockback import KF_UNKNOWN
from ssbot.safety.supervisor import GREEN, SupervisorDecision, silk_spend_allowed

SILKSPEAR_COST = 4
R_ALLOW, R_SILK, R_BIND, R_DOWN = 1, 2, 3, 4
REASONS = {0: "", R_ALLOW: "supervisor allowlist", R_SILK: "silk reserve", R_BIND: "bind commit test",
           R_DOWN: "down-slash over a hazard"}
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

    @classmethod
    def from_world(cls, ws: WorldState, d: SupervisorDecision | None, h: int | None, want_bind: bool = False
                   ) -> "FilterContext":
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
                   soft=soft, hero_x=float(ws.hero.pos.v[0]))


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


def unpausable(may_kill: np.ndarray, ctx: FilterContext) -> np.ndarray:
    """U(c) for the boss-death slow motion: a candidate that may land the killing blow, unless I3 allows entering
    (full HP and h >= 3)."""
    allow = ctx.max_hp > 0 and ctx.hp >= ctx.max_hp and ctx.h is not None and ctx.h >= 3
    return np.asarray(may_kill, bool) & (not allow)
