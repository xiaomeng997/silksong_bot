"""What a Wanderer down slash pressed at a given frame does (task 1v1 T1(b), forum.md 46): the hero's two branches
(hit-bounce and miss) and the enemy's outcome. No margins here: this is the estimate the special-move table and the
planner's safety checks read; its errors are measured by ssbot.tools.pogo_check.

The slash. Attacks/Wanderer/DownSlash and DownSlashAlt (alternating; slash.dump live, pogo_probe 2026-10-11, 1,586
samples, no spread): 7-point polygons relative to the hero transform (STATE hero.pos), mirrored with the facing; y from
-0.37 to -2.68 below the transform, x about +-1.75. A hit lands on the 3rd to 9th frame after the press frame (the
frame whose input mask has down + attack: the clip turns DownSlash / DownSlashAlt there): ACTIVE.

What bounces (ssbot.tools.pogo_outcomes over the person's recordings and the bot's 1v1 runs): an enemy hurtbox (layer
11 collider of an entity with a HealthManager: a 'hit', 9 damage) and a clashable attack collider (layer 22, damage
parry bits 5: the Choristor's Spin Hit / whips, the Envoy's Charge Damager: no damage, a tink) bounce the hero; a
counter-only attack collider (parry 4: the Clapper's Slam Collider 1 / 2, the hammer) does not: the slash passes
through it and the hammer hurts. The bounce: vy -10 for one step on the contact, then the pogo (kinematics EV_POGO:
jump steps from 4, i-frames against enemies pogo_invul 0.16 s); the model puts EV_POGO on the contact frame + EV_OFF.

    pm = PogoModel(params, terrain)
    br = pm.branches(start, masks, press_j, targets)     # targets(j) -> [(poly [n, 2], kind)] at rollout index j
    br.contact_j, br.kind, br.miss (Rollout), br.hit (Rollout or None)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ssbot.knowledge import kinematics as kin

# facing +1 (hero.facing 1); facing -1 mirrors x (pogo_probe slash.dump, relative to hero.pos)
DOWN = np.array([[-1.742, -0.38], [-1.672, -1.634], [-1.007, -2.353], [-0.109, -2.676], [0.953, -2.403],
                 [1.461, -1.734], [1.481, -0.389]])
DOWN_ALT = np.array([[1.714, -0.368], [1.568, -1.688], [0.91, -2.337], [0.067, -2.602], [-0.903, -2.479],
                     [-1.449, -1.573], [-1.576, -0.395]])
ACTIVE = (3, 9)          # frames after the press frame on which the slash can land (pogo_outcomes: hits at +3 .. +9)
EV_OFF = 0               # EV_POGO's index relative to the contact frame's (pogo_check calibration)
# what a collider does to the slash (pogo_outcomes): its kind from the layer and the damage parry bits
K_HURT, K_TINK = "hurtbox", "tink"


def collider_kind(layer: int | None, parry: int | None, has_hm: bool) -> str | None:
    """hurtbox: an enemy's layer-11 collider with a HealthManager (hit + bounce); tink: a clashable attack collider
    (layer 22 with the clash bit, parry 5: bounce, no damage); None: the slash passes (the Clapper's hammer, parry 4,
    triggers, terrain)."""
    if layer == 11 and has_hm:
        return K_HURT
    if layer == 22 and parry is not None and int(parry) & 1:
        return K_TINK
    return None


def slash_poly(facing: int, alt: bool | None = None) -> np.ndarray:
    """The slash polygon relative to hero.pos; alt None: the hull of both (the alternation unknown)."""
    if alt is None:
        p = np.concatenate([DOWN, DOWN_ALT])
        p = _hull(p)
    else:
        p = DOWN_ALT if alt else DOWN
    return p if facing >= 0 else p * np.array([-1.0, 1.0])


def _hull(pts: np.ndarray) -> np.ndarray:
    pts = sorted(map(tuple, np.round(pts, 6)))

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.array(lower[:-1] + upper[:-1])


def meets(a: np.ndarray, b: np.ndarray) -> bool:
    """Two convex polygons overlap (separating axis test; touching edges do not count)."""
    for poly in (a, b):
        n = len(poly)
        for i in range(n):
            e = poly[(i + 1) % n] - poly[i]
            ax = np.array([-e[1], e[0]])
            pa = a @ ax
            pb = b @ ax
            if pa.max() <= pb.min() + 1e-9 or pb.max() <= pa.min() + 1e-9:
                return False
    return True


@dataclass
class Branches:
    contact_j: int               # rollout index of the first contact (-1: none in the active window)
    kind: str | None             # K_HURT / K_TINK / None
    miss: kin.Rollout
    hit: kin.Rollout | None      # the bounce branch from contact_j (None without a contact)


class PogoModel:
    def __init__(self, params: kin.HeroParams, terrain: kin.Terrain2D | None = None, ev_off: int = EV_OFF):
        self.params = params
        self.terrain = terrain
        self.ev_off = ev_off

    def contact(self, pos: np.ndarray, facing: int, press_j: int, targets, alt: bool | None = None
                ) -> tuple[int, str | None]:
        """The first rollout index j in press_j + ACTIVE where the slash at pos[j] meets a target (targets(j): [(poly,
        kind)]); hurtboxes before tinks on the same frame."""
        sp = slash_poly(facing, alt)
        for j in range(press_j + ACTIVE[0], min(press_j + ACTIVE[1], len(pos) - 1) + 1):
            p = sp + pos[j]
            hit = None
            for poly, kind in targets(j):
                if kind is None:
                    continue
                if meets(p, poly):
                    if kind == K_HURT:
                        return j, kind
                    hit = hit or kind
            if hit is not None:
                return j, hit
        return -1, None

    def rollout(self, start: np.ndarray, masks: np.ndarray, contact_j: int | None = None, **kw) -> kin.Rollout:
        """One branch: masks [T] (index 0 = the frame after start); contact_j: EV_POGO at rollout index contact_j
        (+ ev_off; the events' index 0 is rollout index 1)."""
        m = np.asarray(masks, np.int64)[None]
        ev = None
        if contact_j is not None and contact_j >= 0:
            ev = np.zeros(m.shape, np.int64)
            e = min(max(contact_j - 1 + self.ev_off, 0), m.shape[1] - 1)
            ev[0, e] = kin.EV_POGO
        return kin.rollout(start, m, self.params, self.terrain, events=ev, **kw)

    def branches(self, start: np.ndarray, masks: np.ndarray, press_j: int, targets, facing: int,
                 alt: bool | None = None, **kw) -> Branches:
        """press_j: the rollout index of the press frame (masks[press_j - 1] has down + attack). No contact unless the
        rollout swings there airborne (F_ATTACKING on the press frame or the next, not on the ground the frame before:
        a grounded down + attack is a side slash, a cooldown no swing)."""
        miss = self.rollout(start, masks, None, **kw)
        fl = miss.flags[0]
        lo = max(press_j - 1, 0)
        swung = bool(((fl[press_j:press_j + 2] & kin.F_ATTACKING) != 0).any()) and not bool(fl[lo] & kin.F_GROUND)
        # the swing ends on landing (HeroController.BackOnGround resets the attack): no contact from the first
        # grounded frame after the press on
        g = np.flatnonzero((fl[press_j:] & kin.F_GROUND) != 0)
        last = press_j + int(g[0]) - 1 if len(g) else len(fl) - 1
        j, kind = self.contact(miss.pos[0, :last + 1], facing, press_j, targets, alt) if swung else (-1, None)
        hit = self.rollout(start, masks, j, **kw) if j >= 0 else None
        return Branches(j, kind, miss, hit)


# ---- the enemy's side (pogo_outcomes / pogo_check, forum.md 46) ----
# per type: what a landed down slash does to the enemy (damage = the nail's; knockback: ssbot.knowledge.knockback,
# down slashes do not move ground enemies) and to its current move. Filled from the measurements in forum.md 46.
ENEMY_OUTCOME = {
    "Song Heavy Sentry": {"hurtbox": "hit (no knockback); the slam / jump goes on unchanged; the hammer still hurts "
                                     "once the pogo i-frames end", "hammer": "no bounce (parry 4): the slash passes"},
}


__all__ = ["DOWN", "DOWN_ALT", "ACTIVE", "EV_OFF", "K_HURT", "K_TINK", "collider_kind", "slash_poly", "meets",
           "Branches", "PogoModel", "ENEMY_OUTCOME"]
