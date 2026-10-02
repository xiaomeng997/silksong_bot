"""hits_to_death (DESIGN §3.7.1): how many worst events of the threat support the hero can still take, the lethal one
included. Everything else in the supervisor (tiers, I1-I3, Q1/Q3, Bind and parry gates) is phrased in it.

    ctx = ctx_from_support([SupportEvent("Bone Beast", damage=2)])   # Bell Beast: every attack is 2 masks
    hits_to_death(hp=5, blue=0, mask_intact=False, ctx=ctx)          # 3   (5 -> 3 -> 1 -> dead)

What it encodes (1.0.30000):
- blue health absorbs first and the overflow goes on into health with the same mask flag; the Fractured Mask check
  comes after the blue absorption (PlayerData.cs:3616-3634, m0 §2.5), so h = health + blue;
- Fractured Mask: equipped with AmountLeft > 0 clamps any lethal hit to 1 HP whatever allowFracturedMaskBreak says;
  the flag only decides whether the mask is used up (m0:C2). A MidChain hit saves without using it; the code below
  always counts the mask used, which is more conservative and kept;
- CriticalDamage leaves 1 HP (TakeHealth(health - 1)), clears blue health, never touches the mask and cannot kill by
  itself (HeroController.cs:5233-5240): in the support it is an event of h - 1 damage;
- hazards and DoSpecialDamage ignore i-frames (m0:N1, N2): they are never dropped from the support during i-frames, and
  pending_dmg holds the frost clock and every active DamageTag (m0:N2, N3). The oracle's hero.tags gives each tag's
  dmg_left, with -1 for a tag that has no hit limit (swimming in frost water; docs/facts/1.0.30000/state_fields_m2.md
  §4): pending_from_tags turns that, or a tag without a readable dmg_left, into lethal pending damage;
- mask_covers = False for Muckroach Maul, Wraith / Slubberlug grabs, claw traps [com10] and the GMS web (unverified),
  until DamageHero / FSM flags are exported (m0:C2);
- a Fractured Mask state of UNKNOWN counts as broken; equipment is believed only from the audit (§3.3.4), which in
  oracle mode is STATE hero.fractured_mask {equipped, amount_left}.

hits_to_death is the §3.7.1 code line for line, plus one guard: a support whose worst event does no damage (D1 < 1
and no CriticalDamage, or CriticalDamage at 1 HP with D1 < 1) would loop forever, so it returns UNBOUNDED. A support
is empty here only when its producer certified that explicitly (SupportSet.certified_empty; cross-module decision 4:
the supervisor adds an "unknown" event of max(1, worst known damage) whenever the support is not certified, so a missing
or dropped forecast never reads as UNBOUNDED).
hits_to_death_batch evaluates the same recurrence for planner rollouts with a numba kernel (the default; numba is a
dependency) or a NumPy fallback; tests/test_hits_to_death.py checks both against the scalar reference on a full grid.
"""
from collections.abc import Iterable
from dataclasses import dataclass, replace

import numba
import numpy as np

UNBOUNDED = 1 << 20   # nothing in the support can hurt (D1 < 1 and no CriticalDamage)

# Fractured Mask states (the audit's view; STATE hero.fractured_mask in oracle mode)
MASK_NONE, MASK_INTACT, MASK_BROKEN, MASK_UNKNOWN = "NONE", "INTACT", "BROKEN", "UNKNOWN"


@dataclass(slots=True, frozen=True)
class Ctx:
    """The support summary hits_to_death needs (§3.7.1 ctx)."""
    D1: int                              # worst single event in the support, all its hits summed (1+1 = 2)
    pending_dmg: int = 0                 # damage still to land from attached DamageTags and the frost clock
    mask_covers: bool = True             # the mask clamps every lethal event of the support (False: grabs, Maul ...)
    pending_mask_covers: bool = False    # the mask would also clamp lethal pending damage (unknown: assume not)
    critical_in_support: bool = False    # a CriticalDamage source (h -> 1, mask untouched) is in the support


@dataclass(slots=True, frozen=True)
class SupportEvent:
    """One worst-case event of an in-support threat tube (combat/forecast.py builds these from tube metadata)."""
    source: str                  # what it is (entity type_key, collider), for messages
    damage: int = 1              # total damage of the event: 1+1 combos are one event of 2
    hits: int = 1                # hits making up the event (> 1: multi-hit)
    hazard: bool = False         # hazard type (SPIKES, LAVA, ...: passes i-frames, m0:N1) or a cog crush (+ respawn)
    mask_covers: bool = True     # False for the grab / Maul / claw trap list above
    critical: bool = False       # CriticalDamage (h -> 1)
    instance: int | None = None  # the entity root iid, which every collider of one entity shares (naming only: Q3's
    #                              multi-instance is `hits` > 1, one event of hits the i-frames do not separate)


@dataclass(slots=True, frozen=True)
class SupportSet:
    """What a support producer (the W3 forecaster, a stand-in) hands the supervisor for one frame. `known` certifies
    `events` as a superset of what can land; an empty certified support additionally needs `certified_empty` (a
    dropped forecast that returns no events with known=True is still unknown). Anything else is unknown support."""
    events: tuple[SupportEvent, ...] = ()
    known: bool = False
    certified_empty: bool = False

    @property
    def certified(self) -> bool:
        return self.known and (bool(self.events) or self.certified_empty)


def mask_state(fractured_mask: dict | None) -> str:
    """Audit view of the Fractured Mask from STATE hero.fractured_mask ({equipped, amount_left}; nil before the tool
    asset is readable, equipped nil while the tools are unreadable)."""
    if not isinstance(fractured_mask, dict) or fractured_mask.get("equipped") is None:
        return MASK_UNKNOWN
    if not fractured_mask["equipped"]:
        return MASK_NONE
    left = fractured_mask.get("amount_left")
    if not isinstance(left, int):
        return MASK_UNKNOWN
    return MASK_INTACT if left > 0 else MASK_BROKEN


def mask_intact(state: str) -> bool:
    """Only an audited, equipped mask with uses left counts; UNKNOWN is broken (§3.7.1)."""
    return state == MASK_INTACT


def pending_from_tags(tags: object, hp: int, blue: int) -> tuple[int, bool]:
    """(pending damage, unbounded) from STATE hero.tags ([{kind, dmg_left, t_left}]; nil without a TagDamageTaker,
    [] with no tag). dmg_left >= 0 is an upper bound in masks; -1 (no hit limit), a missing or unreadable value, or an
    unreadable item is unbounded and counts as hp + blue: lethal by itself, never a smaller number."""
    if not isinstance(tags, (list, tuple)):
        return 0, False
    total = 0
    for g in tags:
        d = g.get("dmg_left") if isinstance(g, dict) else None
        if isinstance(d, bool) or not isinstance(d, (int, float)) or d < 0:
            return hp + blue, True
        total += int(d)
    return total, False


def ctx_from_support(events: Iterable[SupportEvent], pending_dmg: int = 0, pending_mask_covers: bool = False) -> Ctx:
    """Ctx for a set of in-support events: D1 is the largest non-critical event; one uncovered event makes the mask
    uncovering for the whole support (it may be the one that lands)."""
    d1, covers, crit = 0, True, False
    for e in events:
        if e.critical:
            crit = True
        else:
            d1 = max(d1, e.damage)
        covers = covers and e.mask_covers
    return Ctx(D1=d1, pending_dmg=pending_dmg, mask_covers=covers, pending_mask_covers=pending_mask_covers,
               critical_in_support=crit)


def hits_to_death(hp: int, blue: int, mask_intact: bool, ctx: Ctx) -> int:
    """How many worst events of the support the hero can still take, the lethal one included (§3.7.1)."""
    h, m = hp + blue - ctx.pending_dmg, mask_intact
    if h < 1:                                    # the pending damage is lethal by itself
        if not (m and ctx.pending_mask_covers):
            return 0
        h, m = 1, False
    n = 0
    while True:
        n += 1
        d = max(ctx.D1, h - 1 if ctx.critical_in_support else 0)   # CriticalDamage: h -> 1, mask untouched
        if d < 1:
            return UNBOUNDED
        if h - d >= 1:
            h -= d
            continue
        if m and ctx.mask_covers:
            h, m = 1, False
            continue
        return n


def after_event(hp: int, blue: int, mask_intact: bool, event: Ctx) -> tuple[int, bool] | None:
    """(h, mask_intact) after the pending damage and then one worst event of `event` (its D1 / critical / covers), or
    None when that event kills. Used for "h after the worst event of a window" (I3)."""
    h, m = hp + blue - event.pending_dmg, mask_intact
    if h < 1:
        if not (m and event.pending_mask_covers):
            return None
        h, m = 1, False
    d = max(event.D1, h - 1 if event.critical_in_support else 0)
    if h - d >= 1:
        return h - d, m
    if m and event.mask_covers:
        return 1, False
    return None


def hits_to_death_after(hp: int, blue: int, mask_intact: bool, event: Ctx, ctx: Ctx) -> int:
    """hits_to_death once one worst event of `event` has landed (0 when it kills); `ctx` describes what follows."""
    r = after_event(hp, blue, mask_intact, event)
    if r is None:
        return 0
    return hits_to_death(r[0], 0, r[1], replace(ctx, pending_dmg=0))


# ---- batch evaluation (planner rollouts) ------------------------------------------------------------------------

def _kernel(hp: int, blue: int, m: bool, d1: int, pending: int, covers: bool, pending_covers: bool,
            crit: bool) -> int:
    """hits_to_death on plain scalars, written for numba (no objects, no Python-only constructs)."""
    h = hp + blue - pending
    if h < 1:
        if not (m and pending_covers):
            return 0
        h = 1
        m = False
    n = 0
    while True:
        n += 1
        d = d1
        if crit and h - 1 > d:
            d = h - 1
        if d < 1:
            return UNBOUNDED
        if h - d >= 1:
            h -= d
        elif m and covers:
            h = 1
            m = False
        else:
            return n


_kernel_jit = numba.njit(cache=True)(_kernel)


@numba.njit(cache=True)
def _batch_nb(hp, blue, m, d1, pending, covers, pending_covers, crit, out):
    for i in range(hp.size):
        out[i] = _kernel_jit(hp[i], blue[i], m[i], d1[i], pending[i], covers[i], pending_covers[i], crit[i])


def _batch_numpy(hp, blue, m, d1, pending, covers, pending_covers, crit) -> np.ndarray:
    h = hp + blue - pending
    out = np.zeros(h.shape, np.int64)
    alive = np.ones(h.shape, bool)
    lethal_pending = h < 1
    saved = lethal_pending & m & pending_covers
    alive &= ~(lethal_pending & ~saved)                    # out stays 0 there
    h = np.where(saved, 1, h)
    m = m & ~saved
    n = np.zeros(h.shape, np.int64)
    # every live step lowers h by >= 1 or uses the mask, so max(h) + 2 steps finish every element
    for _ in range(int(h.max(initial=1)) + 3):
        if not alive.any():
            break
        n += alive
        d = np.maximum(d1, np.where(crit, h - 1, 0))
        unbounded = alive & (d < 1)
        out[unbounded] = UNBOUNDED
        alive &= ~unbounded
        survive = alive & (h - d >= 1)
        use_mask = alive & ~survive & m & covers
        dead = alive & ~survive & ~use_mask
        out[dead] = n[dead]
        h = np.where(survive, h - d, np.where(use_mask, 1, h))
        m = m & ~use_mask
        alive &= ~dead
    return out


def hits_to_death_batch(hp, blue, mask_intact, d1, pending=0, mask_covers=True, pending_mask_covers=False,
                        critical=False, use_numba: bool | None = None) -> np.ndarray:
    """hits_to_death element-wise over broadcast arrays (int64 result, same shape as the broadcast inputs); the numba
    kernel unless use_numba is False (the NumPy reference)."""
    arrs = np.broadcast_arrays(np.asarray(hp, np.int64), np.asarray(blue, np.int64), np.asarray(mask_intact, bool),
                               np.asarray(d1, np.int64), np.asarray(pending, np.int64), np.asarray(mask_covers, bool),
                               np.asarray(pending_mask_covers, bool), np.asarray(critical, bool))
    if use_numba is False:
        return _batch_numpy(*(np.array(a) for a in arrs))
    flat = [np.ascontiguousarray(a).ravel() for a in arrs]
    out = np.empty(flat[0].size, np.int64)
    _batch_nb(*flat, out)
    return out.reshape(arrs[0].shape)
