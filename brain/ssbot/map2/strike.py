"""Map v2 L3: the STRIKE MODULE and the enemy-bound WINDOWS (docs/plans/forum_map_v2.md section 1 L3 and 1b item 7;
stage M3). Offline / planning code only: nothing in the live bot imports it.

What a strike does, from her exact kin_jit state at the press, against one predicted outcome branch of the Clappers
(ssbot.map2.clapper.Branch), and the next state the search continues from:

  DOWN SLASH   the press frame t (her mask down + attack, airborne, the attack ready); the contact is the first frame
               of t + 3 .. t + 9 where BOTH alternations' polygons (pogo_model DOWN / DOWN_ALT, mirrored by her
               facing; the alternation is not tracked) meet the target's ROBUST body box (the intersection over the
               branch's timing variants: a hit in every variant); landing ends the swing. The bounce: kin_jit's
               EV_POGO on the contact frame (HERO2: the slash's restart, 3.74 u); i-frames contact + 0 .. 8 (M0);
               the next swing from t + 18 (M0: 18 f cadence). The enemy sees a 'down' hit (10 damage) at the contact.
  HOOKED       the Clawline press at P (her mask frame) toward d: the needle hits at P + 8 (M0: 8 / 9; the enemy's
  CLAWLINE     TOOK DAMAGE then: an Idle Clapper reacts in that frame) when the ray meets a body: her centre at the
               throw + d x 0 .. RAY_U, her box bottom held at hero2.hold_bb + 0.5 .. + 1.98 against the body's y
               range; the antic drift (hero2's antic decel of her vx), frozen from the throw, the dash from P + 17 /
               19 at 70 u/s (1.4 u per physics step) until her box front is GAP short of the body front at that frame
               (the body may move: an evade) or 6 steps, control 5 / 6 frames after the stop (M0: control P + 23 ..
               32, p50 26); two hero VARIANTS (early: dash P + 17, gap 1.7, control stop + 5; late: dash P + 19, gap
               2.5, control stop + 6). At control: vy 0, the forced bounce (kin_jit EV_POGO from rest: 4.09 u), NO
               i-frames, the attack cooled 0.15 s (control + 10 / 11), the air dash restored (M4a live: 11 / 11 -
               the hooked path's bounce; the UNHOOKED Clawline does not restore it). The hooked Clapper's BODY does
               not hurt from the dash (SetDamageHeroAndRecord) through control + 12 (M4a live: its first contact
               attempt at the Harpoon FSM's Idle + 1 = control + 13 / 14, 17 / 20 + 2 / 20 overlaps across it; the
               real damage the same); its attacks do. The enemy sees a 'claw' hit (4 damage) at the needle's hit.
  (side / up slashes: not in this version - a missing primitive for the acceptance table when a move needs one)

WINDOWS (bound to the enemy): per branch, Clapper and frame the press regions in her box-centre space (u) that the
strike needs - the down slash's (the Minkowski box of the robust body and the slash polygons' extent, at the contact
frame) and the hooked Clawline's (the ray's reach and the height band at the throw) - as the search's queries into the
envelope (M1). A region is a candidate only; the exact simulation of the concrete keys decides.

Coordinates: her TRANSFORM (kin pos: x, box bottom + 1.5527) for the slash polygons and the Clapper model's HeroPath,
her BOX CENTRE (transform - 0.51325) for the envelope; u world units.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ssbot.knowledge import hero2
from ssbot.knowledge import kinematics as km
from ssbot.map2 import clapper as cm

FLOOR = cm.FLOOR                   # 3.015, the Forum floor (her box bottom standing)
FOOT = 1.5527                      # her transform above her box bottom
HALF_H = 1.03945                   # her box half height
CTR_DY = FOOT - HALF_H             # transform - box centre (0.51325)
HALF_W = 0.25                      # her box half width
# the down slash (pogo_model, live slash.dump; relative to her transform, facing +1)
DOWN = np.array([[-1.742, -0.38], [-1.672, -1.634], [-1.007, -2.353], [-0.109, -2.676], [0.953, -2.403],
                 [1.461, -1.734], [1.481, -0.389]])
DOWN_ALT = np.array([[1.714, -0.368], [1.568, -1.688], [0.91, -2.337], [0.067, -2.602], [-0.903, -2.479],
                     [-1.449, -1.573], [-1.576, -0.395]])
DS_ACTIVE = (3, 9)                 # contact frames after the press (pogo_outcomes; M0: +3 66, +4 40)
DS_IFR = (0, 8)                    # the pogo's i-frames, frames after the contact (M0: contact + 0 .. 8 / 9)
SLASH_NEXT_F = hero2.SLASH_NEXT_F  # 18: the next swing after a press
DS_DMG = cm.NAIL_DMG               # 10
# the hooked Clawline (hero2 / M0, frames from P)
HOOK_HIT_F = 8                     # the needle's hit (8 / 9): the enemy's TOOK DAMAGE
HOOK_THROW_F = 9                   # Harpoon Throw: v 0
RAY_U = 9.75                       # the needle's reach from her centre at the throw (9.25 u ahead + her half width
#                                    and the stop: SP13 used 10.2 u from her centre at the press to the body front)
RAY_BAND = (0.5, 1.98)             # the ray's height over her box bottom (SP13 claw_cal: bb + 0.5 .. + 1.98 meets)
DASH_STEP_U = 1.4                  # 70 u/s per physics step
DASH_MAX_STEPS = 6                 # the dash's Wait 0.1 s
CLAW_DMG = 4
CLAW_ATK_CD = 0.15                 # the attack's extra cooldown at control (s)
HOOK_NEXT_F = hero2.HOOK_NEXT_F    # 12: a second Clawline from control + 12 / 13
HOOK_BODY_OFF = (17, 12)           # M4a: the hooked body harmless from P + 17 (the early dash) to control + 12


@dataclass(frozen=True)
class HookVariant:
    name: str
    dash_f: int                    # the dash's first frame after P
    gap: float                     # her box front short of the body front at the stop (u)
    ctrl_after: int                # control this many frames after the stop frame


HOOK_VARIANTS = (HookVariant("early", 17, 1.7, 5), HookVariant("late", 19, 2.5, 6))


def steps_of(k: int, alpha_c: int = 0) -> int:
    """Physics steps in frame k (5 of every 6 frames; the phase class shifts the empty one)."""
    return 0 if (k + alpha_c) % 6 == 5 else 1


def centre_of(pos: np.ndarray) -> np.ndarray:
    """Her box centre from her transform ([..., 2])."""
    out = np.array(pos, dtype=float, copy=True)
    out[..., 1] -= CTR_DY
    return out


# ---- the target boxes of a branch -----------------------------------------------------------------------------------

def _rec_box(r: tuple, K: cm.Know) -> tuple | None:
    k, a, b, st, j, x, y, face, ham = r
    if st is None or st in cm.NO_BODY or st in cm.DEAD:
        return None
    bx = K.box(st, j)              # the frame's own box (not the neighbours' union: a target must be there)
    xa, xb = x + face * bx[0], x + face * bx[1]
    return (min(xa, xb), y + bx[2], max(xa, xb), y + bx[3])


FAST = [False]                     # E1 (search.Cfg.fast_danger): robust_boxes / union_tops compiled (the same values)


def robust_boxes(br: cm.Branch, iid: int, T: int | None = None) -> np.ndarray:
    """[T + 1, 4] the Clapper's body box per frame that holds in EVERY timing variant of the branch (the
    intersection of the records drawn at that frame; NaN when none / no body / it varies so much that nothing is
    common). Cached on the branch."""
    cache = getattr(br, "_robust", None)
    if cache is None:
        cache = {}
        try:
            br._robust = cache
        except AttributeError:
            pass
    if iid in cache:
        return cache[iid]
    T = br.T if T is None else T
    lo = np.full((T + 1, 4), np.nan)
    from ssbot.map2 import brnum
    if brnum.ON[0]:
        A = brnum.robust_rows(br, iid, T)                 # M4b: the same rows from the record arrays
        rows = len(A)
    else:
        rows = []
        for r in br.recs.get(iid, ()):
            k0, a, b = r[0], r[1], r[2]
            k_lo, k_hi = max(k0 + a, 0), min(k0 + b, T)
            if k_lo > k_hi:
                continue
            bx = _rec_box(r, br.K)
            rows.append((k_lo, k_hi) + ((np.inf, np.inf, -np.inf, -np.inf) if bx is None else bx))
        A = np.asarray(rows, float) if rows else None
    if rows and FAST[0] and brnum.ON[0]:
        # E1: the same intersection in one compiled pass (np.maximum.at / np.minimum.at are slow)
        x0, y0, x1, y1, _ = brnum.frame_minmax(np.ascontiguousarray(A, np.float64), int(T))
        ok = (x0 < x1) & (y0 < y1) & np.isfinite(x0) & np.isfinite(x1)
        lo[ok, 0], lo[ok, 1], lo[ok, 2], lo[ok, 3] = x0[ok], y0[ok], x1[ok], y1[ok]
    elif rows:
        n = (A[:, 1] - A[:, 0] + 1).astype(np.int64)
        idx = np.repeat(A[:, 0].astype(np.int64), n) + (np.arange(int(n.sum())) - np.repeat(np.cumsum(n) - n, n))
        B = np.repeat(A[:, 2:], n, axis=0)
        x0 = np.full(T + 1, -np.inf)
        y0 = np.full(T + 1, -np.inf)
        x1 = np.full(T + 1, np.inf)
        y1 = np.full(T + 1, np.inf)
        np.maximum.at(x0, idx, B[:, 0])
        np.maximum.at(y0, idx, B[:, 1])
        np.minimum.at(x1, idx, B[:, 2])
        np.minimum.at(y1, idx, B[:, 3])
        ok = (x0 < x1) & (y0 < y1) & np.isfinite(x0) & np.isfinite(x1)
        lo[ok, 0], lo[ok, 1], lo[ok, 2], lo[ok, 3] = x0[ok], y0[ok], x1[ok], y1[ok]
    cache[iid] = lo
    return lo


def union_tops(br: cm.Branch, iid: int, T: int | None = None) -> np.ndarray:
    """M4 S1b: [T + 1] the HIGHEST top of the Clapper's body over the records drawn at each frame (robust_boxes takes
    their intersection - the lowest top - where two records of a timing view fall on one frame); NaN: none / no body.
    The side rule's body top (press.side_hit). Cached on the branch."""
    cache = getattr(br, "_utops", None)
    if cache is None:
        cache = {}
        try:
            br._utops = cache
        except AttributeError:
            pass
    if iid in cache:
        return cache[iid]
    T = br.T if T is None else T
    out = np.full(T + 1, np.nan)
    from ssbot.map2 import brnum
    if brnum.ON[0]:
        A = brnum.robust_rows(br, iid, T)
    else:
        rows = []
        for r in br.recs.get(iid, ()):
            k0, a, b = r[0], r[1], r[2]
            k_lo, k_hi = max(k0 + a, 0), min(k0 + b, T)
            if k_lo > k_hi:
                continue
            bx = _rec_box(r, br.K)
            rows.append((k_lo, k_hi) + ((np.inf, np.inf, -np.inf, -np.inf) if bx is None else bx))
        A = np.asarray(rows, float) if rows else None
    if A is not None and len(A) and FAST[0] and brnum.ON[0]:
        top = brnum.frame_minmax(np.ascontiguousarray(A, np.float64), int(T))[4]      # (E1: the same, compiled)
        ok = np.isfinite(top)
        out[ok] = top[ok]
    elif A is not None and len(A):
        n = (A[:, 1] - A[:, 0] + 1).astype(np.int64)
        idx = np.repeat(A[:, 0].astype(np.int64), n) + (np.arange(int(n.sum())) - np.repeat(np.cumsum(n) - n, n))
        y1 = np.repeat(A[:, 5], n)
        top = np.full(T + 1, -np.inf)
        np.maximum.at(top, idx, y1)
        ok = np.isfinite(top)
        out[ok] = top[ok]
    cache[iid] = out
    return out


def state_at(br: cm.Branch, iid: int, k: int) -> tuple | None:
    """(state, frame in state, x, y, face) of the Clapper at frame k in the branch's nominal timing (the record
    whose k is k; None if none)."""
    from ssbot.map2 import brnum
    if brnum.ON[0]:
        return brnum.state_at(br, iid, k)                # M4b: the first record of frame k from the arrays
    for r in br.recs.get(iid, ()):
        if r[0] == k:
            return (r[3], r[4], r[5], r[6], r[7])
    return None


# ---- the down slash ------------------------------------------------------------------------------------------------

def slash_polys(face: int) -> tuple[np.ndarray, np.ndarray]:
    s = np.array([1.0 if face >= 0 else -1.0, 1.0])
    return DOWN * s, DOWN_ALT * s


def _poly_box(p: np.ndarray, b, shrink: float = 0.0) -> bool:
    if shrink > 0.0:
        b = (b[0] + shrink, b[1] + shrink, b[2] - shrink, b[3] - shrink)
        if b[0] >= b[2] or b[1] >= b[3]:
            return False
    return cm.poly_box_hit(p, (b[0], b[1], b[2], b[3]))


def dslash_contact(pos: np.ndarray, face: np.ndarray, ground: np.ndarray, t: int, boxes: np.ndarray,
                   shrink: float = 0.0, c_min: int | None = None) -> int:
    """The first frame c in t + 3 .. t + 9 where both slash alternations at her transform pos[c] meet the robust box
    boxes[c] ([T, 4], NaN rows = none) - each alternation's first contact, the later of the two; -1 when either misses
    (or she lands first: the swing ends). M4 S1b shrink: the box shrunk by this on every side (a contact needs that
    much overlap: press.SHRINK). E2 c_min (a swing carried into a plan's start, t <= 0: search.simulate's swing): the
    frames before c_min are not looked at (her start state already shows no contact there)."""
    n = len(pos)
    first = [-1, -1]
    c0 = t + DS_ACTIVE[0] if c_min is None else max(t + DS_ACTIVE[0], int(c_min))
    for c in range(c0, min(t + DS_ACTIVE[1], n - 1) + 1):
        if ground[c]:
            break
        if c >= len(boxes) or np.isnan(boxes[c, 0]):
            continue
        pa, pb = slash_polys(int(face[c]))
        for i, p in enumerate((pa, pb)):
            if first[i] < 0 and _poly_box(p + pos[c], boxes[c], shrink):
                first[i] = c
        if first[0] >= 0 and first[1] >= 0:
            return max(first)
    return -1


def dslash_region(box, face: int | None = None) -> tuple[float, float, float, float]:
    """Her box-centre region (x0, x1, y0, y1) at the contact frame from which a down slash meets the body box
    (x0, y0, x1, y1): the box minus the polygons' extent (both alternations; facing None: either)."""
    if face is None:
        qx0, qx1 = -1.742, 1.742
    else:
        a, b = slash_polys(face)
        q = np.concatenate([a, b])
        qx0, qx1 = float(q[:, 0].min()), float(q[:, 0].max())
    qy0, qy1 = -2.676, -0.368
    return (box[0] - qx1, box[2] - qx0, box[1] - qy1 - CTR_DY, box[3] - qy0 - CTR_DY)


# ---- the hooked Clawline -------------------------------------------------------------------------------------------

def hold_bb(bb_p: float, vy_p: float) -> float:
    """Her box bottom (world) held through the Clawline from her state at the press (hero2.hold_bb, 7 steps)."""
    return hero2.hold_bb(bb_p, vy_p, 7)


def ray_meets(xc: float, bb: float, d: int, box) -> bool:
    """The needle's ray from her centre xc toward d at her box bottom bb meets the body box."""
    if np.isnan(box[0]):
        return False
    a, b = (xc, xc + d * RAY_U) if d > 0 else (xc - RAY_U, xc)
    if box[2] <= a or box[0] >= b:
        return False
    y0, y1 = bb + RAY_BAND[0], bb + RAY_BAND[1]
    return box[1] < y1 and box[3] > y0


def claw_region(box, d: int, vy: float = 0.0) -> tuple[float, float, float, float]:
    """Her box-centre region (x0, x1, y0, y1) at the press from which the hooked Clawline toward d meets the body box
    at the throw: the ray's reach (minus the antic drift's ~1 u, both ways loose) and the band (her box bottom held:
    centre - HALF_H + 0.0774 clamp(vy))."""
    dh = 0.0774 * min(max(vy, -10.0), 5.0)
    y0 = box[1] - RAY_BAND[1] + HALF_H - dh
    y1 = box[3] - RAY_BAND[0] + HALF_H - dh
    if d > 0:
        return (box[0] - RAY_U - 1.5, box[2], y0, y1)
    return (box[0], box[2] + RAY_U + 1.5, y0, y1)


@dataclass
class Hook:
    """One hooked Clawline in one branch and hero variant: her transform per frame P .. ctrl (index 0 = P), the hit
    frame, control, the stop, the target."""
    P: int
    d: int
    iid: int
    variant: str
    pos: np.ndarray                # [ctrl - P + 1, 2] her transform
    hit: int                       # frame of the needle's hit (P + 8)
    ctrl: int                      # frame of control
    x_stop: float
    y_hold: float                  # her transform y held
    ok: bool = True
    why: str = ""


def claw_hook(S_P: np.ndarray, P: int, d: int, iid: int, boxes: np.ndarray, var: HookVariant,
              alpha_c: int = 0) -> Hook:
    """The hooked Clawline from her kin state at the end of frame P's physics (the free flight's state at P), toward
    d, at the Clapper whose robust body boxes per frame are `boxes` (absolute frames). ok False with why when the ray
    misses at the hit frame or the dash cannot reach the stop."""
    x0, py0 = float(S_P[km.PX]), float(S_P[km.PY])
    vx0, vy0 = float(S_P[km.VX]), float(S_P[km.VY])
    bb0 = py0 - FOOT
    bbh = hold_bb(bb0, vy0)
    # the antic: hero2's per-step decel of the clamped velocity (x), the height to the hold
    vx = min(max(vx0, -20.0), 20.0) * hero2.CLAW_ANTIC_DECEL[0]
    xs, ys = [x0], [py0]
    x = x0
    for j in range(1, HOOK_THROW_F + 1):
        for _ in range(steps_of(P + j, alpha_c)):
            vx *= hero2.CLAW_ANTIC_DECEL[0]
            x += vx * hero2.FDT
        xs.append(x)
        ys.append(py0 + (bbh - bb0) * min(j / 7.0, 1.0))
    hit = P + HOOK_HIT_F
    hb = boxes[hit] if hit < len(boxes) else np.full(4, np.nan)
    if not ray_meets(xs[HOOK_HIT_F], bbh, d, hb):
        return Hook(P, d, iid, var.name, np.array(list(zip(xs, ys))), hit, -1, x, bbh + FOOT, False, "ray")
    y_hold = bbh + FOOT
    # frozen until the dash, then 1.4 u per step toward the body's front at that frame
    stop_f, n_steps = None, 0
    j = HOOK_THROW_F
    while True:
        j += 1
        k = P + j
        if j < var.dash_f:
            xs.append(x), ys.append(y_hold)
            continue
        bx = boxes[k] if k < len(boxes) else boxes[-1]
        front = (bx[0] if d > 0 else bx[2]) if not np.isnan(bx[0]) else None
        target = None if front is None else front - d * (var.gap + HALF_W)
        for _ in range(steps_of(k, alpha_c)):
            if target is not None and (target - x) * d <= 0:
                break
            if n_steps >= DASH_MAX_STEPS:
                break
            step = DASH_STEP_U if target is None else min(DASH_STEP_U, (target - x) * d)
            x += d * max(step, 0.0)
            n_steps += 1
        xs.append(x), ys.append(y_hold)
        if (target is not None and (target - x) * d <= 1e-9) or n_steps >= DASH_MAX_STEPS:
            stop_f = j
            break
        if j > 60:
            break
    if stop_f is None:
        return Hook(P, d, iid, var.name, np.array(list(zip(xs, ys))), hit, -1, x, y_hold, False, "dash")
    ctrl_j = min(max(stop_f + var.ctrl_after, 23), 34)
    while len(xs) <= ctrl_j:
        xs.append(x), ys.append(y_hold)
    return Hook(P, d, iid, var.name, np.array(list(zip(xs, ys)))[:ctrl_j + 1], hit, P + ctrl_j, x, y_hold)


def control_state(params: km.HeroParams, hook: Hook, alpha: float = 0.0, airdashed: float = 0.0) -> np.ndarray:
    """Her kin state at the hooked Clawline's control (before the forced bounce: the caller rolls on with EV_POGO
    in the first frame): at rest at the stop, facing d, airborne, the attack cooled CLAW_ATK_CD, the air dash free
    (hooked: its bounce restores it). For an UNHOOKED Clawline the caller passes airdashed = the state before it (M4a:
    not restored)."""
    S = km.initial_state(params, hook.x_stop, hook.y_hold, ground=False, facing=hook.d, alpha=alpha)
    S[km.ATK_CD] = CLAW_ATK_CD
    S[km.AIRDASHED] = 0.0 if hook.ok else float(airdashed)
    return S


def hook_body_off(hooks, k: int) -> tuple:
    """The Clappers (iid) whose body does not hurt at frame k: each hooked Clawline's window P + 17 .. control + 12
    (HOOK_BODY_OFF; M4a)."""
    return tuple(h.iid for h in hooks if h.ok and h.P + HOOK_BODY_OFF[0] <= k <= h.ctrl + HOOK_BODY_OFF[1])


# ---- her keys -> facing per frame ----------------------------------------------------------------------------------

def facing_track(face0: int, masks: np.ndarray) -> np.ndarray:
    """Her facing per rollout index (0 = start): the last direction key held (a press turns her at once)."""
    f = np.empty(len(masks) + 1, dtype=np.int64)
    cur = 1 if face0 >= 0 else -1
    f[0] = cur
    for i, m in enumerate(masks):
        m = int(m)
        if m & km.B_RIGHT and not m & km.B_LEFT:
            cur = 1
        elif m & km.B_LEFT and not m & km.B_RIGHT:
            cur = -1
        f[i + 1] = cur
    return f


__all__ = ["union_tops", "DOWN", "DOWN_ALT", "DS_ACTIVE", "DS_IFR", "SLASH_NEXT_F", "HOOK_HIT_F", "HOOK_VARIANTS", "HookVariant",
           "Hook", "robust_boxes", "state_at", "dslash_contact", "dslash_region", "claw_region", "ray_meets",
           "claw_hook", "control_state", "facing_track", "centre_of", "hold_bb", "CTR_DY", "FOOT", "HALF_H",
           "HOOK_BODY_OFF", "hook_body_off"]
