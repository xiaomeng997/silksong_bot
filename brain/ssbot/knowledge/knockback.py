"""Damage knockback envelope (DESIGN §3.5.2, §3.5.4 Hz(c), §3.5.6 Bind and hazards, §3.7.2 I2): the collider boxes
the hero can occupy after a hit, published as support. Under cross-module decision 2 that means a conservative
superset, checked against every logged hit (ssbot.tools.kin_check, knockback section), not a sample of timings.

    env = knockback_envelope(hit_box, "left", params, terrain)      # one hit: env.union[k], env.swept, env.touches
    swept, per_frame = knockback_boxes(roll.box, "left", params, terrain, per_frame=True)   # every frame of a plan

What the game does (HeroController.StartRecoil / FixedUpdate / Update, 1.0.30000; docs/facts/1.0.30000/m0.md):
StartRecoil zeroes the velocity, switches gravity off, clears onGround and sets hero_state no_input, then waits for
GameManager.FreezeMoment(0, 0.1, 0.1, 0) (0.1 s of unscaled time from the second frame after the hit, then a 0.1 s
ramp of the time scale back to 1); only then is cState.recoiling set, and every physics step moves the body at
recoilVector = (+-RECOIL_VELOCITY, RECOIL_VELOCITY / 2) = (+-15, 7.5) u/s away from the impact side, until the Update
in which recoilTimer (scaled dt summed after the recoil start) has reached RECOIL_DURATION 0.2 s: CancelDamageRecoil,
v = 0, gravity back, control back. The Weighted Anklet multiplies RECOIL_VELOCITY by 0.5 (Gameplay asset). Ground and
air share the law (StartRecoil clears onGround before the first recoil step), so one table per side serves both.

The bound: the body only ever moves along the recoil path P(0..n) (one step per physics step, clipped by walls and
ceilings, never reversed), and the frame in which a step happens is the only thing timing changes. So for frame k
after the hit, the box lies in the hull of P(0) .. P(n_hi[k]), where n_hi[k] is the most recoil steps the timing
model allows by frame k: the physics phase at the recoil start taken at its supremum (just below 1), every frame at
the longest ordinary frame time (HeroParams.frame_time_hi) and up to hitches_per_window hitches of hitch_max placed
wherever they give the most steps (exhaustive over placements), with the game's float32 timer sums. Nothing bounds a
delay: a concurrent FreezeMoment (BindBreak 0.01 / 0.4 / 0.1 with a hit during Bind; BossDeathSlow and EnemyDeath
with a killing blow; hitches) holds the time scale at 0 while the hero sits at P(0) or part way, which the hull
covers because its near end is the hit box itself. Measured 2026-10-01 on the live run i0_000: 4 hits during Bind and
1 BossDeathSlow kill sat still for 13-30 extra frames; the sampled envelope this replaces left them out by 3.0 u.

Validity after control returns: union[k] covers every input only for k < ctl_min (the earliest frame any timing
gives control back, 19 with two hitches, 26 to 28 without). For k >= ctl_min it adds an any-input reach from the
path's possible release points (|vx| <= the fastest modelled horizontal speed, the downspike's 26 u/s; vy up to the
jump speed, down to the maximum fall), not clipped by terrain: a valid superset that grows fast; a planner that
regains control rolls its own candidates out from `release` instead.

Batched form (decision 4): knockback_boxes takes the planner's per-frame hit boxes [..., 4] and runs the clipped
path per query in compiled code (kin_jit's collision against the packed terrain); swept is the hull of the whole
no-input path (what I2 and Hz(c) test against hazards), per_frame the union[k] table per query. In open air the path
is the hit box translated by n * step, so the precomputed offsets of KnockbackTable are exact there.
"""
from __future__ import annotations

import functools
import itertools
import math
from dataclasses import dataclass

import numpy as np

from ssbot.knowledge.kinematics import HeroParams, Terrain2D

FRAMES = 64          # table length: the longest logged no-input period after a hit is 47 frames (live i0_000)


@dataclass(frozen=True, slots=True)
class Timing:
    """Recoil timing bounds from the jitter model (frame k = 0 is the hit frame)."""
    n_hi: np.ndarray       # [F+1] most recoil steps taken by frame k
    n_max: int             # most steps in one recoil
    n_min: int             # fewest (phase 0, shortest frames, no slow-motion)
    ctl_min: int           # earliest frame with control back
    ctl_nominal: tuple     # (earliest, latest) control frame without hitches or concurrent freezes


def _recoil_timing(udts: np.ndarray, alpha_r: float, p: HeroParams) -> tuple[np.ndarray, int | None]:
    """Cumulative recoil steps per frame and the control frame for one frame-time sequence (udts[k]: unscaled frame
    time of frame k, k = 0 the hit frame) and the physics phase at the recoil start, by the same rules as the model
    (kinematics._update: FreezeMoment wait / ramp on unscaled time, recoilTimer on scaled time, float32 sums)."""
    F = len(udts) - 1
    n = np.zeros(F + 1, dtype=np.int64)
    wait, ramp, rt = np.float32(p.hurt_wait), np.float32(p.hurt_ramp), np.float32(p.hurt_recoil_time)
    ph, t, mode_n, k_r = 0, np.float32(0.0), 0, None
    for k in range(F + 1):
        u = np.float32(udts[k])
        wdone = False
        if ph == 0 and mode_n >= p.hurt_wait_skip + 1:
            t = np.float32(t + u)
            if t >= wait:
                ph, t, wdone = 1, np.float32(0.0), True
        if ph == 1 and not wdone:
            t = np.float32(t + u)
            if t >= ramp:
                k_r = k
                break
        mode_n += 1
    if k_r is None:
        return n, None
    alpha, timer, total = alpha_r, np.float32(0.0), 0
    for k in range(k_r + 1, F + 1):
        dt = float(np.float32(udts[k]))
        a = alpha + dt / p.fdt
        s = int(math.floor(a + 1e-9))
        alpha = a - s
        total += s
        n[k] = total
        if timer >= rt:
            n[k:] = total
            return n, k
        timer = np.float32(timer + np.float32(dt))
    return n, None


@functools.lru_cache(maxsize=16)
def _timing_cached(key: tuple) -> Timing:
    p = HeroParams(**dict(key))
    F = FRAMES
    hi, lo = p.frame_time_hi, p.frame_time_lo
    n_hi = np.zeros(F + 1, dtype=np.int64)
    n_max, ctl_min = 0, F + 1
    places = [()] + [(a,) for a in range(2, F + 1)]
    if p.hitches_per_window >= 2:
        places += list(itertools.combinations(range(2, F + 1), 2))
    for pl in places:
        u = np.full(F + 1, hi)
        u[list(pl)] = p.hitch_max
        n, kc = _recoil_timing(u, 1.0 - 1e-12, p)
        np.maximum(n_hi, n, out=n_hi)
        n_max = max(n_max, int(n[-1]))
        if kc is not None:
            ctl_min = min(ctl_min, kc)
    n_lo, kc_lo = _recoil_timing(np.full(F + 1, lo), 0.0, p)
    _, kc_hi = _recoil_timing(np.full(F + 1, hi), 1.0 - 1e-12, p)
    return Timing(n_hi, n_max, int(n_lo[-1]), ctl_min, (kc_hi, kc_lo))


def recoil_timing(params: HeroParams) -> Timing:
    keys = ("fdt", "hurt_wait", "hurt_ramp", "hurt_recoil_time", "hurt_wait_skip", "frame_time_lo", "frame_time_hi",
            "hitch_max", "hitches_per_window")
    return _timing_cached(tuple((k, getattr(params, k)) for k in keys))


@dataclass(frozen=True, slots=True)
class KnockbackTable:
    """Per side and Weighted Anklet: the open-air offsets and the timing bounds behind every query."""
    push: int                # +1 pushed right (impact from the left), -1 pushed left
    weighted: bool
    step: tuple              # (dx, dy) of one recoil step
    timing: Timing
    free: np.ndarray         # [F+1, 4] any-input reach (dx-, dy-, dx+, dy+) after ctl_min, 0 before
    offsets: np.ndarray      # [F+1, 4] union[k] - hit box in open air, no-input part

    @property
    def frames(self) -> int:
        return len(self.free) - 1


def knockback_table(params: HeroParams, side: str, weighted: bool | None = None) -> KnockbackTable:
    """side: the impact side ("left" / "right", as the oracle "damage" event). weighted None: params.weighted."""
    w = params.weighted if weighted is None else weighted
    p = params.with_weighted(w) if w and not params.weighted else params
    push = 1 if side == "left" else -1
    tm = recoil_timing(p)
    sx = push * p.hurt_velocity * p.fdt
    sy = p.hurt_velocity * p.hurt_vy_ratio * p.fdt
    F = FRAMES
    n = np.minimum(tm.n_hi, tm.n_max)
    off = np.zeros((F + 1, 4))
    off[:, 0] = np.minimum(0.0, n * sx)
    off[:, 2] = np.maximum(0.0, n * sx)
    off[:, 3] = n * sy
    vx = max(p.run_speed + p.recoil_velocity, p.ds_speed, p.cast_catch_speed)
    vy_up = p.jump_speed
    vy_dn = p.max_fall + p.gravity * p.fdt
    free = np.zeros((F + 1, 4))
    for k in range(tm.ctl_min, F + 1):
        j = k - tm.ctl_min
        steps = math.floor(1 + (j * p.frame_time_hi + min(p.hitches_per_window, j) *
                                (p.hitch_max - p.frame_time_hi)) / p.fdt)
        free[k] = (-vx * p.fdt * steps, -vy_dn * p.fdt * steps, vx * p.fdt * steps,
                   vy_up * p.fdt * steps + p.airborne_lift * (j + 1))
    return KnockbackTable(push, w, (sx, sy), tm, free, off)


# ---- compiled path per query ----------------------------------------------------------------------------------

def _kernel():
    from numba import njit

    from ssbot.knowledge.kin_jit import move_x, move_y

    @njit(cache=True)
    def kb_query(boxes, sx, sy, n_max, n_hi, free, ctl_min, n_rel, hw, skin, foot, head, slop_lo, slop_hi, TT,
                 per_frame, swept, frames, release):
        M = boxes.shape[0]
        F = n_hi.shape[0] - 1
        hull = np.empty((n_max + 1, 4))
        for m in range(M):
            x0, y0, x1, y1 = boxes[m, 0], boxes[m, 1], boxes[m, 2], boxes[m, 3]
            px0 = 0.5 * (x0 + x1)
            py0 = y0 + foot
            px, py = px0, py0
            hull[0, 0], hull[0, 1], hull[0, 2], hull[0, 3] = x0, y0, x1, y1
            r0, r1, r2, r3 = np.inf, np.inf, -np.inf, -np.inf
            if n_rel == 0:
                r0, r1, r2, r3 = x0, y0, x1, y1
            for s in range(1, n_max + 1):
                px, _ = move_x(px, py, sx, hw, skin, foot, head, TT)
                py, _, _, _ = move_y(px, py, sy, hw, skin, foot, head, slop_lo, slop_hi, TT)
                bx0, by0 = x0 + (px - px0), y0 + (py - py0)
                bx1, by1 = x1 + (px - px0), y1 + (py - py0)
                hull[s, 0] = min(hull[s - 1, 0], bx0)
                hull[s, 1] = min(hull[s - 1, 1], by0)
                hull[s, 2] = max(hull[s - 1, 2], bx1)
                hull[s, 3] = max(hull[s - 1, 3], by1)
                if s >= n_rel:
                    r0, r1, r2, r3 = min(r0, bx0), min(r1, by0), max(r2, bx1), max(r3, by1)
            for c in range(4):
                swept[m, c] = hull[n_max, c]
            release[m, 0], release[m, 1], release[m, 2], release[m, 3] = r0, r1, r2, r3
            if per_frame:
                for k in range(F + 1):
                    n = min(n_hi[k], n_max)
                    if k >= ctl_min:
                        frames[m, k, 0] = min(hull[n, 0], r0 + free[k, 0])
                        frames[m, k, 1] = min(hull[n, 1], r1 + free[k, 1])
                        frames[m, k, 2] = max(hull[n, 2], r2 + free[k, 2])
                        frames[m, k, 3] = max(hull[n, 3], r3 + free[k, 3])
                    else:
                        for c in range(4):
                            frames[m, k, c] = hull[n, c]

    return kb_query


@functools.lru_cache(maxsize=1)
def _kb_query():
    return _kernel()


def knockback_boxes(hit_boxes: np.ndarray, side: str, params: HeroParams, terrain: Terrain2D | None = None,
                    weighted: bool | None = None, per_frame: bool = False, table: KnockbackTable | None = None
                    ) -> tuple[np.ndarray, np.ndarray | None, np.ndarray]:
    """For hit boxes [..., 4] (the hero collider in the frame of a hit, e.g. Rollout.box): (swept [..., 4] the hull
    of the whole no-input path, per_frame [..., F+1, 4] union[k] or None, release [..., 4] the hull of the path's
    possible control-return points)."""
    table = table or knockback_table(params, side, weighted)
    hb = np.asarray(hit_boxes, dtype=np.float64)
    shape = hb.shape[:-1]
    flat = np.ascontiguousarray(hb.reshape(-1, 4))
    M = len(flat)
    tm = table.timing
    F = table.frames
    swept = np.empty((M, 4))
    release = np.empty((M, 4))
    frames = np.empty((M, F + 1, 4)) if per_frame else np.empty((0, F + 1, 4))
    p = params
    _kb_query()(flat, table.step[0], table.step[1], tm.n_max, np.ascontiguousarray(tm.n_hi), table.free,
                tm.ctl_min, tm.n_min, p.half_width, p.skin, p.foot, p.head, p.land_slop_lo, p.land_slop_hi,
                (terrain or Terrain2D.empty()).packed(), per_frame, swept, frames, release)
    return (swept.reshape(shape + (4,)), frames.reshape(shape + (F + 1, 4)) if per_frame else None,
            release.reshape(shape + (4,)))


@dataclass(slots=True)
class Envelope:
    """One hit: union[k] the boxes reachable k frames after the hit frame (k = 0), swept the no-input path hull,
    release where control can come back, ctl_min the earliest frame it can (union[k] holds for any input only
    before it; after it the any-input reach from release is added)."""
    side: str
    union: np.ndarray        # [F+1, 4]
    swept: np.ndarray        # [4]
    release: np.ndarray      # [4]
    ctl_min: int
    n_hi: np.ndarray         # [F+1]

    def control_frame(self) -> int:
        return self.ctl_min

    def contains(self, box: np.ndarray, k: int, tol: float = 0.0) -> bool:
        u = self.union[min(k, len(self.union) - 1)]
        return bool(box[0] >= u[0] - tol and box[1] >= u[1] - tol and box[2] <= u[2] + tol and box[3] <= u[3] + tol)

    def excursion(self, box: np.ndarray, k: int) -> float:
        """How far the box sticks out of union[k] (0 inside)."""
        u = self.union[min(k, len(self.union) - 1)]
        return float(max(u[0] - box[0], u[1] - box[1], box[2] - u[2], box[3] - u[3], 0.0))

    def touches(self, region) -> bool:
        """safety.invariants EnvelopeTouches: Region.geom an AABB (x0, y0, x1, y1); the no-input path."""
        g = getattr(region, "geom", region)
        if g is None:
            return True                       # unknown geometry: assume the worst
        x0, y0, x1, y1 = (float(v) for v in g)
        s = self.swept
        return bool(s[0] < x1 and x0 < s[2] and s[1] < y1 and y0 < s[3])


def knockback_envelope(hit_box: np.ndarray, side: str, params: HeroParams, terrain: Terrain2D | None = None,
                       weighted: bool | None = None) -> Envelope:
    """Envelope of one hit taken from `side` ("left" / "right": the impact side, as in the oracle "damage" event)
    by a hero whose collider in the hit frame is hit_box (x0, y0, x1, y1), e.g. Rollout.box[i, t] or STATE hero.box."""
    table = knockback_table(params, side, weighted)
    swept, frames, release = knockback_boxes(np.asarray(hit_box, dtype=np.float64)[None], side, params, terrain,
                                             per_frame=True, table=table)
    return Envelope(side, frames[0], swept[0], release[0], table.timing.ctl_min, table.timing.n_hi.copy())
