"""Damage knockback envelope (DESIGN §3.5.2, §3.5.4 Hz(c), §3.5.6 Bind and hazards, §3.7.2 I2): the collider boxes
the hero can occupy after a hit, published as support. Under cross-module decision 2 that is a conservative superset,
checked against every logged hit (ssbot.tools.kin_check, knockback section), not a sample of timings.

    env = knockback_envelope(hit_box, "left", params, terrain)    # one hit: env.union[k], env.swept, env.touches
    swept, per_frame, flags = knockback_boxes(roll.box, "left", params, terrain)   # every frame of every plan
    table = knockback_table(params, "left"); roll.box + table.swept_offset          # open air, no call at all

What the game does (HeroController.StartRecoil / FixedUpdate / Update, 1.0.30000, decompiled HeroController.cs
9611-9661): StartRecoil zeroes the velocity, switches gravity off, clears onGround and sets hero_state no_input, then
waits for GameManager.FreezeMoment(0, 0.1, 0.1, 0) (0.1 s of unscaled time from the second frame after the hit, then a
0.1 s ramp of the time scale back to 1); only then is cState.recoiling set, and every physics step moves the body at
recoilVector = (+-RECOIL_VELOCITY, RECOIL_VELOCITY / 2) = (+-15, 7.5) u/s away from the impact side (zero for a top or
bottom impact), until the Update in which recoilTimer (scaled dt summed after the recoil start) has reached
RECOIL_DURATION 0.2 s: CancelDamageRecoil, v = 0, gravity back, control back. The Weighted Anklet multiplies
RECOIL_VELOCITY by Gameplay.WeightedAnkletDmgKnockbackMult 0.5 (crests.json "weighted_anklet", probe P17). Ground and
air share the law (StartRecoil clears onGround before the first recoil step), so one table per side serves both.

The bound. The body only moves along the recoil path P(0..n), one step per physics step, stopped by walls and
ceilings, never reversed; timing only decides by which frame a step happens. So the box of frame k after the hit
(k = 0 the hit frame) lies in the hull of P(0) .. P(n_hi[k]), where n_hi[k] is the most recoil steps the timing model
allows by then: the physics phase at the recoil start at its supremum (just below 1), every frame at the jitter
model's frame_time_max and up to hitches_per_window frames of hitch_max placed wherever they give the most steps
(exhaustive over placements), with the game's float32 timer sums. The jitter model (kin_fit over 2.83 M gameplay
frames of the 13 bot recordings) has no frame above 0.0369 s and never more than 2 frames above 0.018 s in any 65.
Nothing bounds a delay: a concurrent FreezeMoment (BindBreak 0.01 / 0.4 / 0.1 after a hit during Bind, BossDeathSlow with a killing blow) holds
the time scale at 0 while the hero sits somewhere on the path, which the hull covers because its near end is the hit
box. Three effects the axis-aligned path does not carry are added (all seen in the 11 561 logged hits of the 13 bot
recordings and the person's session): Box2D depenetration and skin intrusion move the box up to 0.0108 u off the path (a hit while landing
pushed back out of the floor once the steps resume, a recoil into an arena gate stopping 9 mm short of the skin), so
every box is dilated by CONTACT_SLOP; a sloped ceiling turns the recoil along itself (i2_002 f 693717, a hit in Bind
under Bone_05's "Roof Collider": v = (12.98, -2.60), downwards, which is exactly the projection of (15, 7.5) on
the slope's tangent); a blocker the terrain dump does not have (an enemy body, a gate missing from the dump: human
session, Ant_05b) can stop the path at any point, which the hull already covers before control returns.

Slopes. DoRecoilMovement sets the velocity to the recoil vector s every step and the contact solver (static terrain,
no friction, rotation frozen) leaves its projection on the cone of allowed velocities; such a projection p satisfies
p . (s - p) = 0 (Moreau), i.e. lies on the circle with diameter [0, s]. So n steps move the box by a point of the
disk with centre n s / 2 and radius n |s| / 2, whatever walls, ceilings and slopes it meets, and the disks of
fewer steps lie inside it. From the last step before the walked axis-aligned path can touch a slope, the bound is the
box there plus that disk of the remaining steps (bounding box), then CONTACT_SLOP. Pushed right from the start:
x from -0.25 to 4.45 u, y from -1.30 to 3.40 u after the 14 steps of n_max, against 0 to 4.2 u and 0 to 2.1 u in
open air.

Validity after control returns: union[k] covers every input only for k < ctl_min (the earliest frame any timing gives
control back: 23 with two hitches, 26 to 29 without). From ctl_min on it is the swept hull grown by an any-input reach
(|vx| <= the fastest modelled horizontal speed, the downspike's 26 u/s; vy up to the jump speed, down to the maximum
fall), not clipped by terrain: a valid superset that grows fast up to the table's FRAMES; a planner that regains
control rolls its own candidates out from the observed state instead. Beyond FRAMES the table does not hold.

Batched form (decision 4). knockback_table holds the open-air offsets per side (and Weighted Anklet): union[k] =
hit box + offsets[k], swept = hit box + swept_offset; unclipped, so a superset of the clipped path wherever no slope
is in reach. knockback_boxes runs the compiled per-query kernel: open air from the table, the clipped path (and the
slope rule) for the queries that have terrain in reach (flags say which): 512 x 49 hit boxes take 7.7 ms on one
core (13900K), 1.7 ms on four. knockback_hull is the planner's per-tick form: per candidate the hull of its frames
plus the swept offsets of both sides (the slope disk when a slope is in reach), 0.15 ms (p99 0.3 ms) for 512 x 49
on one core; a planner refines with knockback_boxes only the candidates whose hull touches a hazard.
"""
from __future__ import annotations

import functools
import itertools
import math
from dataclasses import dataclass

import numpy as np

from ssbot.knowledge.kinematics import HeroParams, Terrain2D

FRAMES = 64          # table length: the longest logged no-input period after a hit is 47 frames (live i0_000)
CONTACT_SLOP = 0.02  # u: Box2D depenetration / skin intrusion; max observed 0.0108 u over 11 561 logged hits
KF_TERRAIN, KF_SLOPE = 1, 2   # knockback_boxes flags: clipped path computed, slope in reach (bound dilated)
SIDES = {"left": 1, "right": -1, "top": 0, "bottom": 0}   # impact side -> push direction


@dataclass(frozen=True, slots=True)
class Timing:
    """Recoil timing bounds from the jitter model (frame k = 0 is the hit frame)."""
    n_hi: np.ndarray       # [F+1] most recoil steps taken by frame k
    n_max: int             # most steps in one recoil
    n_min: int             # fewest at ordinary frame times (phase 0, shortest frames, no slow-motion)
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


_TIMING_KEYS = ("fdt", "hurt_wait", "hurt_ramp", "hurt_recoil_time", "hurt_wait_skip", "frame_time_lo",
                "frame_time_hi", "frame_time_max", "hitch_max", "hitches_per_window")


@functools.lru_cache(maxsize=16)
def _timing_cached(key: tuple) -> Timing:
    p = HeroParams(**dict(key))
    F = FRAMES
    hi, lo = p.frame_time_max, p.frame_time_lo
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
    _, kc_hi = _recoil_timing(np.full(F + 1, p.frame_time_hi), 1.0 - 1e-12, p)
    return Timing(n_hi, n_max, int(n_lo[-1]), ctl_min, (kc_hi, kc_lo))


def recoil_timing(params: HeroParams) -> Timing:
    if params.hitches_per_window > 2:
        raise ValueError("the exhaustive hitch placement covers at most 2 hitches per recoil")
    return _timing_cached(tuple((k, getattr(params, k)) for k in _TIMING_KEYS))


@dataclass(frozen=True, slots=True)
class KnockbackTable:
    """Per side and Weighted Anklet: the timing bounds and the open-air offsets behind every query (CONTACT_SLOP
    included). offsets[k] + hit box = union[k] and swept_offset + hit box = swept wherever no slope is in reach."""
    push: int                # +1 pushed right (impact from the left), -1 pushed left, 0 no recoil vector
    weighted: bool
    step: tuple              # (dx, dy) of one recoil step
    timing: Timing
    free: np.ndarray         # [F+1, 4] any-input reach (dx-, dy-, dx+, dy+) from ctl_min on, 0 before
    offsets: np.ndarray      # [F+1, 4] open-air union[k] - hit box (x0, y0, x1, y1 offsets)
    swept_offset: np.ndarray  # [4] open-air swept hull - hit box
    margin: float

    @property
    def frames(self) -> int:
        return len(self.free) - 1


@functools.lru_cache(maxsize=32)
def _table_cached(key: tuple, side: str, weighted: bool) -> KnockbackTable:
    p = HeroParams(**dict(key))
    p = p.with_weighted(True) if weighted else p
    push = SIDES[side]
    tm = recoil_timing(p)
    sx = push * p.hurt_velocity * p.fdt
    sy = abs(push) * p.hurt_velocity * p.hurt_vy_ratio * p.fdt
    F = FRAMES
    m = CONTACT_SLOP
    n = np.minimum(tm.n_hi, tm.n_max)
    off = np.zeros((F + 1, 4))
    off[:, 0] = np.minimum(0.0, n * sx) - m
    off[:, 1] = np.minimum(0.0, n * sy) - m
    off[:, 2] = np.maximum(0.0, n * sx) + m
    off[:, 3] = np.maximum(0.0, n * sy) + m
    sw = np.array([min(0.0, tm.n_max * sx) - m, min(0.0, tm.n_max * sy) - m, max(0.0, tm.n_max * sx) + m,
                   max(0.0, tm.n_max * sy) + m])
    vx = max(p.run_speed + p.recoil_velocity, p.ds_speed, p.cast_catch_speed, p.hurt_velocity)
    vy_up = max(p.jump_speed, p.hurt_velocity * p.hurt_vy_ratio)
    vy_dn = max(p.max_fall, p.ds_speed) + p.gravity * p.fdt
    free = np.zeros((F + 1, 4))
    for k in range(tm.ctl_min, F + 1):
        j = k - tm.ctl_min
        steps = math.floor(1 + (j * p.frame_time_max + min(p.hitches_per_window, j) *
                                (p.hitch_max - p.frame_time_max)) / p.fdt)
        free[k] = (-vx * p.fdt * steps, -vy_dn * p.fdt * steps, vx * p.fdt * steps,
                   vy_up * p.fdt * steps + p.airborne_lift * (j + 1))
        off[k] = sw + free[k]
    return KnockbackTable(push, weighted, (sx, sy), tm, free, off, sw, m)


_TABLE_KEYS = _TIMING_KEYS + ("hurt_velocity", "hurt_vy_ratio", "run_speed", "recoil_velocity", "ds_speed",
                              "cast_catch_speed", "jump_speed", "max_fall", "gravity", "airborne_lift",
                              "weighted_knockback_mult", "weighted_invuln_mult", "weighted_recoil_steps",
                              "max_fall_weighted", "weighted")


def knockback_table(params: HeroParams, side: str, weighted: bool | None = None) -> KnockbackTable:
    """side: the impact side ("left" / "right" / "top" / "bottom", as the oracle "damage" event). weighted None:
    params.weighted (an already weighted params is used as it is)."""
    w = params.weighted if weighted is None else weighted
    if side not in SIDES:
        raise ValueError(f"side {side!r}")
    return _table_cached(tuple((k, getattr(params, k)) for k in _TABLE_KEYS), side, bool(w and not params.weighted))


# ---- compiled per-query kernel (kin_jit.kb_one) ----------------------------------------------------------------

def knockback_boxes(hit_boxes: np.ndarray, side: str, params: HeroParams, terrain: Terrain2D | None = None,
                    weighted: bool | None = None, per_frame: bool = False, clip: bool = True,
                    table: KnockbackTable | None = None, threads: int = 1
                    ) -> tuple[np.ndarray, np.ndarray | None, np.ndarray]:
    """For hit boxes [..., 4] (the hero collider in the frame of a hit, e.g. Rollout.box): (swept [..., 4] the hull
    of the whole no-input path, per_frame [..., F+1, 4] union[k] or None, flags [...] KF_* bits). clip False keeps
    the open-air table wherever no slope is in reach (cheaper, looser near walls and ceilings)."""
    table = table or knockback_table(params, side, weighted)
    hb = np.asarray(hit_boxes, dtype=np.float64)
    shape = hb.shape[:-1]
    flat = np.ascontiguousarray(hb.reshape(-1, 4))
    M = len(flat)
    tm = table.timing
    F = table.frames
    swept = np.empty((M, 4))
    frames = np.empty((M, F + 1, 4)) if per_frame else np.empty((0, F + 1, 4))
    flags = np.zeros(M, dtype=np.int32)
    p = params
    from ssbot.knowledge import kin_jit
    args = (flat, table.step[0], table.step[1], tm.n_max, np.ascontiguousarray(tm.n_hi), table.offsets,
            table.swept_offset, table.free, tm.ctl_min, p.half_width, p.skin, p.foot, p.head, p.land_slop_lo,
            p.land_slop_hi, (terrain or Terrain2D.empty()).packed(), table.margin, clip, per_frame, swept, frames, flags)
    if threads > 1:
        import numba
        numba.set_num_threads(threads)
        kin_jit.kb_query_par(*args, threads)
    else:
        kin_jit.kb_query(*args)
    return (swept.reshape(shape + (4,)), frames.reshape(shape + (F + 1, 4)) if per_frame else None,
            flags.reshape(shape))


def knockback_hull(boxes: np.ndarray, params: HeroParams, terrain: Terrain2D | None = None,
                   sides: tuple[str, ...] = ("left", "right"), weighted: bool | None = None,
                   valid: np.ndarray | None = None, threads: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """The planner's Hz(c) query (DESIGN §3.5.4), one call per tick: for candidate boxes [N, T+1, 4] (Rollout.box),
    (hull [N, 4], flags [N]): per candidate the union, over its frames and the given impact sides, of the no-input
    swept hull of a hit in that frame. valid [N, T+1] bool limits the frames a hit can land on (None: all; e.g.
    ~(Rollout.flags & F_INVULN) for damage that respects i-frames, all frames for hazards). A candidate with no valid
    frame gets an empty box (x0 > x1). Unclipped open air (frame hull + swept offsets: walls and ceilings only shorten
    the path) unless a slope lies within that; then the frame hull plus the projection disk of n_max steps per side
    (flags KF_SLOPE; see the module docstring). The frames after control returns are not in it: a planner that is
    hit replans from the observed state."""
    b = np.ascontiguousarray(np.asarray(boxes, dtype=np.float64))
    if b.ndim == 2:
        b = b[None]
    tables = [knockback_table(params, s, weighted) for s in sides]
    sx = np.array([t.step[0] for t in tables])
    sy = np.array([t.step[1] for t in tables])
    n_max = np.array([t.timing.n_max for t in tables], dtype=np.int64)
    swept_off = np.ascontiguousarray(np.stack([t.swept_offset for t in tables]))
    v = np.zeros((0, 0), dtype=np.bool_) if valid is None else np.ascontiguousarray(np.broadcast_to(
        np.asarray(valid, dtype=np.bool_), b.shape[:2]))
    out = np.empty((len(b), 4))
    flags = np.zeros(len(b), dtype=np.int32)
    from ssbot.knowledge import kin_jit
    args = (b, v, sx, sy, n_max, swept_off, params.skin, (terrain or Terrain2D.empty()).packed(), CONTACT_SLOP, out,
            flags)
    if threads > 1:
        import numba
        numba.set_num_threads(threads)
        kin_jit.kb_hull_par(*args)
    else:
        kin_jit.kb_hull(*args)
    return out, flags


@dataclass(slots=True)
class Envelope:
    """One hit: union[k] the boxes reachable k frames after the hit frame (k = 0), swept the no-input path hull,
    ctl_min the earliest frame control can come back (union[k] is the no-input reach before it, any-input after)."""
    side: str
    union: np.ndarray        # [F+1, 4]
    swept: np.ndarray        # [4]
    ctl_min: int
    n_hi: np.ndarray         # [F+1]
    flags: int               # KF_* bits

    def control_frame(self) -> int:
        return self.ctl_min

    def contains(self, box: np.ndarray, k: int, tol: float = 0.0) -> bool:
        if k >= len(self.union):
            raise ValueError(f"frame {k} is past the envelope's {len(self.union) - 1} frames")
        u = self.union[k]
        return bool(box[0] >= u[0] - tol and box[1] >= u[1] - tol and box[2] <= u[2] + tol and box[3] <= u[3] + tol)

    def excursion(self, box: np.ndarray, k: int) -> float:
        """How far the box sticks out of union[k] (0 inside)."""
        u = self.union[k]
        return float(max(u[0] - box[0], u[1] - box[1], box[2] - u[2], box[3] - u[3], 0.0))

    def touches(self, region) -> bool:
        """safety.invariants EnvelopeTouches: Region.geom an AABB (x0, y0, x1, y1), tested against the no-input path
        (the swept hull); unknown geometry counts as touching."""
        g = getattr(region, "geom", region)
        if g is None:
            return True
        x0, y0, x1, y1 = (float(v) for v in g)
        s = self.swept
        return bool(s[0] < x1 and x0 < s[2] and s[1] < y1 and y0 < s[3])


def knockback_envelope(hit_box: np.ndarray, side: str, params: HeroParams, terrain: Terrain2D | None = None,
                       weighted: bool | None = None) -> Envelope:
    """Envelope of one hit taken from `side` ("left" / "right": the impact side, as in the oracle "damage" event)
    by a hero whose collider in the hit frame is hit_box (x0, y0, x1, y1), e.g. Rollout.box[i, t] or STATE hero.box."""
    table = knockback_table(params, side, weighted)
    swept, frames, flags = knockback_boxes(np.asarray(hit_box, dtype=np.float64)[None], side, params, terrain,
                                           per_frame=True, table=table)
    return Envelope(side, frames[0], swept[0], table.timing.ctl_min, table.timing.n_hi.copy(), int(flags[0]))
