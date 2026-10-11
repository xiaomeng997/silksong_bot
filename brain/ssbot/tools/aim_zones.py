"""Composite, terrain-aware inescapable zones of the pending aimed moves (aim zones; the person 2026-10-10,
docs/plans/forum_planner_plan.md sec. 5; the method of tools.aim_ics, group 2 of docs/plans/forum_zones_v2.md).

A pending move decides its aim (side, landing, start point) at one moment; from then on its path is the attack-range
template's (combat.attack_range, the bins from the decision). For an enemy at its decision, a hero position (HeroBox
centre) is in the zone when no escape of the hero's state, started at the decision plus a latency, avoids the move.

THE COMPOSITE (the person's correction): one map around the enemy; every cell uses the table of the hero class its OWN
height implies, not the hero's state now:
  GROUND    HeroBox centre within BAND_GROUND of standing height: the ground state, dash as measured ("ground")
  LOW AIR   BAND_GROUND[1] .. BAND_LOW[1] above standing: the worst of the low-air bins (h 0.25 / 1.0, vy fall / rest /
            rise), NO dash
  HIGH AIR  above: the worst of the high-air bins (h 2.5 / 5.0, every vy), NO dash
A cell is in the zone when ANY state of its class has no escape (worst case). The hero libraries are aim_ics's
(timing-complete event libraries per state, T = 120 frames, the bot's Forum_W kinematics), coarse first, the full
library for the cells the coarse one leaves inescapable (the coarse set is a subset, so its escapes are exact).

THE TERRAIN (precomputed over enemy-position bins, not online: the full search of the zone cells walks a library of
60-300 k rows per state and takes seconds per position, too slow for once per antic in the live overlay; the bins
make the run-time lookup O(cells)):
  floor     exact at each state's representative height (the library is rolled over the floor h below); the enemy's
            own floor (the Reed / Tiny stop at it) from the enemy height bin
  walls     x 14.01 / 48.99 (core.forum): an escape whose HeroBox leaves the arena is not counted (pruned: exact for
            every escape that never touches a wall); next to a wall the state's wall library (aim_ics "<state>_w0.3",
            rolled with a wall 0.3 u behind the hero) adds the wall jumps; the enemy's path is clamped to its walls
            (the ARE meta walls / the arena) as the attack-range estimate does
  dome      core.forum.dome_y: escapes that rise into it are pruned
  bins      enemy x every 1 u (14.5 .. 48.5) x side (+1 / -1), enemy y every Y_STEP of the move, plus "open" (no walls,
            no dome). A zone cell of the open floor stays a zone cell next to a wall (walls only remove escapes); the
            open escapes are tried first at every wall bin.
Not modelled: the physics phase (60 Hz frames, the templates' clock), the enemy's motion during the antic before its
decision (the overlay places the zone at the enemy's position now), clashes, i-frames, the enemy body before the
decision, other enemies.

The moves (MOVES): RE_STAB (the three lunges, decided at the Stab 1 entry, side fixed at the antic entry), MA_SLASH
(side = the hero's side at the Slash 1 entry), CC_JUMP / CC_JUMP_CAST (Jump Aim: landing L = 0.916 clamp(hero dx - 5,
+-12) toward the hero; the jump cast adds the rune slam), AT_DIVE (the Tiny's dive, side = the hero's side at the Fire
entry, start = the Fire-entry position). Not done: the Clawmaiden's teleport arrival (no measured decision moment or
arrival rule in the v2 classification), the Reed's counter sector and the Clawmaiden's slash sides (decision = first
damage, both mirrors are already the attack range).

    cd <checkout>/brain
    ../scripts/uv.cmd run python -m ssbot.tools.aim_zones scan --out C:/ssbot/data/m2_forum_aimics/zones3/scan
    ../scripts/uv.cmd run python -m ssbot.tools.aim_zones pack --src C:/ssbot/data/m2_forum_aimics/zones3/scan
    ../scripts/uv.cmd run python -m ssbot.tools.aim_zones png --out C:/ssbot/data/m2_forum_aimics/zones3
    ../scripts/uv.cmd run python -m ssbot.tools.aim_zones validate --json C:/ssbot/data/m2_forum_aimics/zones3/v.json
"""
from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from ssbot.tools.aim_ics import (CLEAR, FLOOR_Y, HB_HH, HB_HW, HB_STAND, STATES, T_LIB, build_library,
                                 hero_params)

REPO = Path(__file__).resolve().parents[3]
FORUM = REPO / "knowledge" / "1.0.30000" / "enemies" / "forum"
D = 0.1                                    # grid of HeroBox centres (u)
WALL_L, WALL_R = 14.01, 48.99              # core.forum
X_BINS = tuple(np.round(np.arange(14.5, 48.6, 1.0), 2))
SIDES = (1, -1)
LATS = (0, 2)
# HeroBox-centre height above standing height (u): [lo, hi) of each class
BAND_GROUND = (-0.25, 0.25)
BAND_LOW = (0.25, 1.5)
CLASSES = ("ground", "low", "high")
CLASS_STATES = {
    "ground": ("ground",),
    "low": tuple(f"air_h{h}_{v}_nd" for h in (0.25, 1.0) for v in ("rest", "fall", "rise")),
    "high": tuple(f"air_h{h}_{v}_nd" for h in (2.5, 5.0) for v in ("rest", "fall", "rise")),
}
WALL_NEAR = 0.9                            # HeroBox side this close to a wall: the wall library is tried too
DOME_SPAN = 3.0                            # the hero's ceiling: the lowest dome point within this x of the cell
BIG = 1 << 30


def height_class(h: float) -> str | None:
    """The class of a HeroBox centre h u above standing height (None: below the ground band = in the floor)."""
    if h < BAND_GROUND[0]:
        return None
    return "ground" if h < BAND_GROUND[1] else "low" if h < BAND_LOW[1] else "high"


@dataclass(frozen=True)
class Move:
    """One pending aimed move in fan coordinates (x toward the side it attacks into, y up; origin = the enemy
    transform at the decision)."""
    name: str
    type_key: str
    fam: str
    branches: tuple                 # the template branches; the jump picks "wall" when its landing is beyond WALL_ZONE
    aim: str                        # "facing" (side fixed before the decision), "hero" (side = the hero's side), "jump"
    grid_x: tuple
    grid_y: tuple
    y_range: tuple                  # the enemy's y at the decision (bins every y_step)
    y_step: float
    enemy_floor: float | None       # the enemy transform stops at this y (None: the template's v as is)
    enemy_walls: tuple | None       # the enemy transform's x range (None: the ARE meta walls)
    variants: tuple                 # (dL, scale) pairs: aim error / speed jitter, every one escaped
    L: float = 0.0                  # the u extent of a scaled template ("facing": STAB_L)
    j_max: int = T_LIB              # frames after the decision tested (the hero holds its last position after T)
    hazard: tuple = ()              # rune slam: (radius, on, off, du, dv) frames after the decision, from the landing
    decision: str = ""
    pending: tuple = ()             # the enemy states in which the move is pending (the overlay draws the zone)
    refine_air: bool = True         # air states: the full library after the coarse one (False: coarse only, a
    #                                 superset zone; the rune slam's late failures defeat the walk's frame skipping)


MOVES = {
    "RE_STAB": Move("RE_STAB", "Song Reed", "RE_STAB", ("main",), "facing", (-6.0, 20.0), (-9.0, 7.0), (4.5, 14.0),
                    0.5, 4.6, None, ((-1.0, 1.0), (0.0, 1.0), (1.0, 1.0)), L=10.0, j_max=72,
                    decision="Stab 1 entry (first damage); side = the facing fixed at the Stab Antic entry",
                    pending=("Stab Antic",)),
    "MA_SLASH": Move("MA_SLASH", "Song Pilgrim Maestro", "MA_SLASH", ("main",), "hero", (0.0, 12.0), (-8.0, 7.0),
                     (5.0, 16.0), 1.0, None, None, ((0.0, 1.0),), j_max=40,
                     decision="Slash 1 entry (first damage); side = the hero's side then",
                     pending=("Fire Antic",)),
    "CC_JUMP": Move("CC_JUMP", "Song Heavy Sentry", "CC_JUMP", ("open", "wall"), "jump", (0.0, 26.0), (-6.0, 13.0),
                    (6.0, 7.0), 0.5, None, None, ((-0.4, 1.0), (0.0, 1.0), (0.4, 1.0)), j_max=80,
                    decision="Jump Aim; landing L = 0.916 clamp(hero dx - 5, +-12) toward the hero",
                    pending=("Jump Antic", "Jump Aim")),
    "CC_JUMP_CAST": Move("CC_JUMP_CAST", "Song Heavy Sentry", "CC_JUMP_CAST", ("open",), "jump", (0.0, 26.0),
                         (-6.0, 13.0), (6.0, 7.0), 0.5, None, None, ((-0.4, 1.0), (0.0, 1.0), (0.4, 1.0)), j_max=132,
                         hazard=(7.187, 79, 130, 6.48, -3.27), refine_air=False,
                         decision="Jump Aim (same rule) + the rune slam r 7.187 at the landing + 6.48 u",
                         pending=("Cast Slam Antic", "Cast Slam Antic 2", "Jump Aim")),
    "AT_DIVE": Move("AT_DIVE", "Song Automaton Tiny", "AT_DIVE", ("main",), "hero", (0.0, 26.0), (-17.0, 3.0),
                    (6.0, 20.0), 1.0, 5.0, (WALL_L + 0.5, WALL_R - 0.5), ((0.0, 0.96), (0.0, 1.0), (0.0, 1.04)),
                    j_max=T_LIB, decision="Fire entry; side = the hero's side then, start = the Fire-entry position",
                    pending=("Fire Ready",)),
}
NOT_DONE = {
    "CM teleport": "no measured decision moment or arrival rule (the v2 classification has none)",
    "RE_COUNTER sector / CM_SLASH side": "decision = first damage: every option is already in the attack range",
}


def grid(mv: Move) -> tuple[np.ndarray, np.ndarray]:
    """Cell centres (fan x, y) of a move's grid."""
    nx = int(round((mv.grid_x[1] - mv.grid_x[0]) / D))
    ny = int(round((mv.grid_y[1] - mv.grid_y[0]) / D))
    return (np.round(mv.grid_x[0] + (np.arange(nx) + 0.5) * D, 3),
            np.round(mv.grid_y[0] + (np.arange(ny) + 0.5) * D, 3))


def y_bins(mv: Move) -> np.ndarray:
    return np.round(np.arange(mv.y_range[0], mv.y_range[1] + 1e-6, mv.y_step), 3)


def x_bin_keys() -> list:
    """"open" and (x, side) for every wall bin."""
    return ["open"] + [(float(x), s) for x in X_BINS for s in SIDES]


def bin_name(b) -> str:
    return "open" if b == "open" else f"x{b[0]}{'R' if b[1] > 0 else 'L'}"


# ---------------------------------------------------------------------------------------------- the move's frames
def hero_shape(sh: np.ndarray, iu0: int, iv0: int, cell: float = 0.05):
    """A template raster (cell iu covers u in [iu cell, (iu + 1) cell), row 0 lowest) dilated by the HeroBox half
    extents plus CLEAR and pooled to the D lattice: (uint8 [nr, nc], ix0, iy0) of HeroBox centres that touch it."""
    import cv2
    if sh is None or not sh.size or not sh.any():
        return None
    kx, ky = int(math.ceil((HB_HW + CLEAR) / cell - 1e-9)), int(math.ceil((HB_HH + CLEAR) / cell - 1e-9))
    a = np.pad(sh.astype(np.uint8), ((ky, ky), (kx, kx)))
    a = cv2.dilate(a, np.ones((2 * ky + 1, 2 * kx + 1), np.uint8))
    u0, v0 = iu0 - kx, iv0 - ky
    f = int(round(D / cell))
    pu, pv = u0 % f, v0 % f
    a = np.pad(a, ((pv, (-(a.shape[0] + pv)) % f), (pu, (-(a.shape[1] + pu)) % f)))
    u0, v0 = u0 - pu, v0 - pv
    b = a.reshape(a.shape[0] // f, f, a.shape[1] // f, f).max(axis=(1, 3))
    return np.ascontiguousarray(b, np.uint8), u0 // f, v0 // f


@dataclass
class Frames:
    """Per branch fs and frame j after the decision: the hero-space raster (bits[off:off + nr nc]), its lattice
    origin, the enemy's position u (x L when scaled) and v."""
    bits: np.ndarray        # uint8
    fi: np.ndarray          # int64 [F, J, 5]: off, nr, nc, ix0, iy0 (nr 0 = nothing)
    ff: np.ndarray          # float64 [F, J, 2]: u (or ratio), v
    nj: np.ndarray          # int64 [F]
    scaled: np.ndarray      # int64 [F]
    hz: np.ndarray          # float64 [F, 6]: radius (0 none), on, off, du, dv, the landing frame
    walls: tuple


@lru_cache(maxsize=8)
def move_frames(name: str) -> Frames:
    from ssbot.combat import attack_range as ar
    mv = MOVES[name]
    tab = ar.load_table(None, ar.SPECS[mv.type_key])
    F = len(mv.branches)
    J = mv.j_max + 1
    fi = np.zeros((F, J, 5), np.int64)
    ff = np.zeros((F, J, 2))
    nj = np.zeros(F, np.int64)
    sc = np.zeros(F, np.int64)
    hz = np.zeros((F, 6))
    bits, off = [], 0
    for f, br in enumerate(mv.branches):
        tp = tab.templates[(mv.fam, br)]
        b0 = tp.b_dec or 0
        scaled = tp.ratio is not None and mv.aim in ("jump", "facing")
        sc[f] = int(scaled)
        n = min(J, tp.nb - b0)
        nj[f] = n
        for j in range(n):
            b = b0 + j
            hs = hero_shape(tp.shape[b], int(tp.origin[b, 0]), int(tp.origin[b, 1]), tab.cell)
            ff[f, j] = (float(tp.ratio[b]) if scaled else float(tp.disp[b, 0]), float(tp.disp[b, 1]))
            if hs is None:
                continue
            m, ix0, iy0 = hs
            fi[f, j] = (off, m.shape[0], m.shape[1], ix0, iy0)
            bits.append(m.ravel())
            off += m.size
        if mv.hazard:
            r, on, off_, du, dv = mv.hazard
            land = int(np.argmax(tp.ratio[b0:b0 + n] >= 0.999)) if tp.ratio is not None else n - 1
            hz[f] = (r + CLEAR, on, off_, du, dv, land)
    walls = mv.enemy_walls or tab.walls
    return Frames(np.concatenate(bits) if bits else np.zeros(1, np.uint8), fi, ff, nj, sc, hz,
                  (float(walls[0]), float(walls[1])))


# ---------------------------------------------------------------------------------------------- the kernel
# per-cell floats: L, enemy x lo / hi, enemy y min, hero x lo / hi, hero y hi (HeroBox centre, fan coordinates)
C_L, C_EXLO, C_EXHI, C_EYMIN, C_HXLO, C_HXHI, C_HYHI, C_NF = range(8)


@lru_cache(maxsize=1)
def _kernel():
    import numba

    @numba.njit(cache=True, inline="always")
    def _hit(bits, fi, f, j, hx, hy, px, py):
        nr = fi[f, j, 1]
        if nr == 0:
            return False
        nc = fi[f, j, 2]
        c = int(math.floor((hx - px) / 0.1)) - fi[f, j, 3]
        if c < 0 or c >= nc:
            return False
        r = int(math.floor((hy - py) / 0.1)) - fi[f, j, 4]
        if r < 0 or r >= nr:
            return False
        return bits[fi[f, j, 0] + r * nc + c] != 0

    @numba.njit(cache=True, inline="always")
    def _epos(ff, scaled, f, j, Lv, s, cf):
        u = ff[f, j, 0] * (Lv if scaled[f] else 1.0) * s
        v = ff[f, j, 1] * s
        return min(max(u, cf[C_EXLO]), cf[C_EXHI]), max(v, cf[C_EYMIN])

    @numba.njit(cache=True)
    def _sim(q, quant, ext, i, cx, cy, mir, f, cf, var, bits, fi, ff, nj, scaled, hz, jmax):
        """-1: trajectory i escapes every variant; BIG: it leaves the arena (pruned); else the last hero frame the
        first failing variant used (0 = the decision frame: no trajectory escapes)."""
        T = q.shape[1]
        if mir > 0:
            x0, x1 = cx + ext[i, 0] * quant, cx + ext[i, 1] * quant
        else:
            x0, x1 = cx - ext[i, 1] * quant, cx - ext[i, 0] * quant
        if x0 < cf[C_HXLO] or x1 > cf[C_HXHI] or cy + ext[i, 2] * quant > cf[C_HYHI]:
            return 1 << 30
        n_end = nj[f]
        for v in range(var.shape[0]):
            Lv = cf[C_L] + var[v, 0]
            s = var[v, 1]
            px0, py0 = _epos(ff, scaled, f, 0, Lv, s, cf)
            if _hit(bits, fi, f, 0, cx, cy, px0, py0):
                return 0
            hx0, hy0 = cx, cy
            lx, ly = 0.0, 0.0
            if hz[f, 0] > 0:
                lx, ly = _epos(ff, scaled, f, int(hz[f, 5]), Lv, s, cf)
            j_last = n_end
            if hz[f, 0] > 0:
                j_last = max(j_last, int(hz[f, 2]))
            for j in range(1, min(jmax, j_last) + 1):
                k = j if j < T else T
                hx1 = cx + mir * q[i, k - 1, 0] * quant
                hy1 = cy + q[i, k - 1, 1] * quant
                a0 = j - 1 < n_end
                a1 = j < n_end
                haz = hz[f, 0] > 0 and hz[f, 1] <= j <= hz[f, 2]
                px1, py1 = px0, py0
                if a1:
                    px1, py1 = _epos(ff, scaled, f, j, Lv, s, cf)
                dm = max(abs((hx1 - hx0) - (px1 - px0)), abs((hy1 - hy0) - (py1 - py0)))     # relative motion
                ns = 2 * (int(dm / 0.1) + 1)
                # the physics step between frames j - 1 and j can fall anywhere in it: the first half of the hero's
                # motion against frame j - 1's colliders, the second half against frame j's, each moved along the
                # enemy's own motion in the frame
                dpx, dpy = px1 - px0, py1 - py0
                for t in range(ns + 1):
                    a = t / ns
                    sx, sy = hx0 + (hx1 - hx0) * a, hy0 + (hy1 - hy0) * a
                    if a <= 0.5 and a0 and _hit(bits, fi, f, j - 1, sx, sy, px0 + dpx * a, py0 + dpy * a):
                        return k
                    if a >= 0.5 and a1 and _hit(bits, fi, f, j, sx, sy, px1 - dpx * (1 - a), py1 - dpy * (1 - a)):
                        return k
                if haz:
                    ox, oy = lx + hz[f, 3] * s, ly + hz[f, 4] * s
                    dx = max(abs(ox - hx1) - (HB_HW + CLEAR), 0.0)
                    dy = max(abs(oy - hy1) - (HB_HH + CLEAR), 0.0)
                    if dx * dx + dy * dy <= hz[f, 0] * hz[f, 0]:
                        return k
                hx0, hy0, px0, py0 = hx1, hy1, px1, py1
        return -1

    @numba.njit(cache=True, parallel=True)
    def scan(q, quant, div, elig, use_elig, probes, ext, cells, cfl, cint, hints, var, bits, fi, ff, nj, scaled, hz,
             jmax, nchunk):
        """cells [C, 2] HeroBox centre (fan, rel. the enemy at the decision); cfl [C, C_NF]; cint [C, 2] (branch,
        mirror of the library). Returns [C]: the first escaping trajectory, -1 = inescapable."""
        C = cells.shape[0]
        N = q.shape[0]
        out = np.full(C, -1, np.int64)
        per = (C + nchunk - 1) // nchunk
        for ch in numba.prange(nchunk):
            last = -1
            for ci in range(ch * per, min(C, (ch + 1) * per)):
                cx, cy, cf = cells[ci, 0], cells[ci, 1], cfl[ci]
                f, mir = cint[ci, 0], float(cint[ci, 1])
                found = -1
                for h in (hints[ci], last):
                    if found < 0 and 0 <= h < N and (not use_elig or elig[h]):
                        if _sim(q, quant, ext, h, cx, cy, mir, f, cf, var, bits, fi, ff, nj, scaled, hz, jmax) < 0:
                            found = h
                if found < 0:
                    for pi in range(probes.shape[0]):
                        i = probes[pi]
                        if use_elig and not elig[i]:
                            continue
                        if _sim(q, quant, ext, i, cx, cy, mir, f, cf, var, bits, fi, ff, nj, scaled, hz, jmax) < 0:
                            found = i
                            break
                if found < 0:
                    i = 0
                    while i < N:
                        if use_elig and not elig[i]:
                            i += 1
                            continue
                        kf = _sim(q, quant, ext, i, cx, cy, mir, f, cf, var, bits, fi, ff, nj, scaled, hz, jmax)
                        if kf < 0:
                            found = i
                            break
                        if kf == 0:
                            break
                        j = i + 1
                        while j < N and div[j] >= kf:       # same frames 1..kf: fails the same way
                            j += 1
                        i = j
                out[ci] = found
                if found >= 0:
                    last = found
        return out

    return scan


def lib_ext(lib) -> np.ndarray:
    """Per trajectory: min / max x and max y displacement (quant units) over its frames."""
    q = lib.q
    return np.ascontiguousarray(np.stack([q[:, :, 0].min(1), q[:, :, 0].max(1), q[:, :, 1].max(1)], 1)
                                .astype(np.float64))


# ---------------------------------------------------------------------------------------------- cells per bin
@lru_cache(maxsize=1)
def _dome_table() -> tuple[np.ndarray, np.ndarray]:
    from ssbot.core.forum import dome_y
    xs = np.arange(WALL_L - DOME_SPAN, WALL_R + DOME_SPAN + 0.25, 0.25)
    ys = np.array([dome_y(float(x)) for x in xs])
    k = int(round(DOME_SPAN / 0.25))
    return xs, np.array([ys[max(0, i - k):i + k + 1].min() for i in range(len(xs))])


def dome_ceiling(xw: np.ndarray) -> np.ndarray:
    """The lowest dome point within DOME_SPAN of each world x."""
    xs, lo = _dome_table()
    return np.interp(xw, xs, lo)


def band_cells(mv: Move, cls: str, ye: float, xb) -> tuple[np.ndarray, np.ndarray]:
    """The grid cells (flat indices, (fan x, y)) of a class at enemy height ye, inside the arena of bin xb."""
    gx, gy = grid(mv)
    h = gy + ye - FLOOR_Y - HB_STAND
    lo, hi = {"ground": BAND_GROUND, "low": BAND_LOW, "high": (BAND_LOW[1], 1e9)}[cls]
    rows = np.nonzero((h >= lo) & (h < hi))[0]
    X, Y = np.meshgrid(gx, gy[rows])
    idx = (rows[:, None] * len(gx) + np.arange(len(gx))[None, :]).ravel()
    cells = np.stack([X.ravel(), Y.ravel()], 1)
    if xb != "open":
        xe, s = xb
        xw = xe + s * cells[:, 0]
        ok = (xw >= WALL_L + HB_HW) & (xw <= WALL_R - HB_HW) & (cells[:, 1] + ye + HB_HH <= dome_ceiling(xw))
        idx, cells = idx[ok], cells[ok]
    if mv.aim == "hero":                       # the side is the hero's: cells behind the enemy are mirrored ones
        keep = cells[:, 0] >= 0
        idx, cells = idx[keep], cells[keep]
    return idx.astype(np.int64), np.ascontiguousarray(cells)


def cell_params(mv: Move, fr: Frames, cells: np.ndarray, ye: float, xb, wall_lib: bool = False):
    """(cfl [C, C_NF], cint [C, 2]) of the cells: the aim L, the enemy's and the hero's bounds, the branch and the
    library mirror (wall_lib: the wall on the cell's nearer side, the library's wall on +x)."""
    C = len(cells)
    cf = np.zeros((C, C_NF))
    ci = np.zeros((C, 2), np.int64)
    ci[:, 1] = 1
    if mv.aim == "jump":
        from ssbot.combat.are_types.clapper import JUMP_GAIN, JUMP_SHORT, JUMP_VX_MAX
        cf[:, C_L] = JUMP_GAIN * np.clip(cells[:, 0] - JUMP_SHORT, -JUMP_VX_MAX, JUMP_VX_MAX)
    else:
        cf[:, C_L] = mv.L
    cf[:, C_EYMIN] = -1e9 if mv.enemy_floor is None else mv.enemy_floor - ye
    if xb == "open":
        cf[:, C_EXLO], cf[:, C_EXHI] = -1e9, 1e9
        cf[:, C_HXLO], cf[:, C_HXHI], cf[:, C_HYHI] = -1e9, 1e9, 1e9
        return cf, ci
    xe, s = xb
    wl, wr = fr.walls

    def fan(a, b):
        return (a - xe, b - xe) if s > 0 else (xe - b, xe - a)
    cf[:, C_EXLO], cf[:, C_EXHI] = fan(wl, wr)
    cf[:, C_HXLO], cf[:, C_HXHI] = fan(WALL_L + HB_HW, WALL_R - HB_HW)
    xw = xe + s * cells[:, 0]
    cf[:, C_HYHI] = dome_ceiling(xw) - ye - HB_HH
    if "wall" in mv.branches:
        from ssbot.combat.are_types.clapper import WALL_ZONE
        xl = xe + s * cf[:, C_L]
        ci[:, 0] = np.where((xl < WALL_ZONE[0]) | (xl > WALL_ZONE[1]), mv.branches.index("wall"), 0)
    if wall_lib:
        near_hi = cf[:, C_HXHI] - cells[:, 0]
        near_lo = cells[:, 0] - cf[:, C_HXLO]
        ci[:, 1] = np.where(near_hi <= near_lo, 1, -1)
    return cf, ci


def near_wall(cfl: np.ndarray, cells: np.ndarray) -> np.ndarray:
    return np.minimum(cfl[:, C_HXHI] - cells[:, 0], cells[:, 0] - cfl[:, C_HXLO]) < WALL_NEAR


# ---------------------------------------------------------------------------------------------- the scan driver
class Scanner:
    """Runs a library over cells of one move (the numba kernel), keeping the move's frames."""

    def __init__(self, name: str, nchunk: int = 64):
        self.mv = MOVES[name]
        self.fr = move_frames(name)
        self.var = np.ascontiguousarray(np.array(self.mv.variants, np.float64))
        self.nchunk = nchunk

    def run(self, lib, ext, cells, cfl, cint, lat: int, hints=None) -> np.ndarray:
        if not len(cells):
            return np.zeros(0, np.int64)
        scan = _kernel()
        fr = self.fr
        h = np.full(len(cells), -1, np.int64) if hints is None else np.ascontiguousarray(hints, np.int64)
        return scan(lib.q, float(lib.quant), lib.div, lib.elig2, lat >= 2, lib.probes, ext,
                    np.ascontiguousarray(cells, np.float64), np.ascontiguousarray(cfl), np.ascontiguousarray(cint),
                    h, self.var, fr.bits, fr.fi, fr.ff, fr.nj, fr.scaled, fr.hz, int(self.mv.j_max), self.nchunk)


def scan_state(out: Path, state: str, moves: list, p, lats=LATS, bins=None, log=print) -> None:
    """One hero state over every move, enemy height bin, latency and x bin. Open floor: the coarse library, then the
    full library for the cells the coarse one left inescapable. Each wall bin: an open-floor zone cell stays a zone
    cell; the others try their open escape first (coarse, or the full one where only the full library escaped), then
    the full library, then (next to a wall) the wall library. Saves z_<move>__<state>.npz: per (lat, y bin, x bin)
    the inescapable flat grid indices of the state's class band."""
    cls = next(c for c, ss in CLASS_STATES.items() if state in ss)
    bins = bins or x_bin_keys()
    t0 = time.perf_counter()
    co = build_library(state, p, 0.0, T_LIB, coarse=True)
    cext = lib_ext(co)
    fu = build_library(state, p, 0.0, T_LIB, coarse=False)
    fext = lib_ext(fu)
    log(f"{state}: libraries coarse {len(co)} / full {len(fu)} rows ({time.perf_counter() - t0:.0f} s)")
    wl = {}

    def wall_lib(coarse: bool):
        if coarse not in wl:
            lib = build_library(f"{state}_w0.3", p, 0.0, T_LIB, coarse=coarse)
            wl[coarse] = (lib, lib_ext(lib))
            log(f"{state}: wall library {len(lib)} rows ({time.perf_counter() - t0:.0f} s)")
        return wl[coarse]

    for name in moves:
        sc = Scanner(name)
        mv = sc.mv
        coarse_only = cls != "ground" and not mv.refine_air
        fl, fx = (co, cext) if coarse_only else (fu, fext)
        arrs = {}
        n_cells = 0
        for yi, ye in enumerate(y_bins(mv)):
            ye = float(ye)
            for lat in lats:
                idx0, cells0 = band_cells(mv, cls, ye, "open")
                n_cells += len(idx0)
                cf, ci = cell_params(mv, sc.fr, cells0, ye, "open")
                # zones only grow with the latency (lat 2 escapes are a subset of lat 0's): reuse the smaller one's
                prev = None if lat == lats[0] else lats[lats.index(lat) - 1]
                known0 = (np.isin(idx0, arrs[f"{prev}|{yi}|open"]) if prev is not None
                          else np.zeros(len(idx0), bool))
                c_first = np.full(len(idx0), -1, np.int64)
                c_first[~known0] = sc.run(co, cext, cells0[~known0], cf[~known0], ci[~known0], lat)
                f_first = np.full(len(idx0), -1, np.int64)
                sel = np.nonzero((c_first < 0) & ~known0)[0]
                if len(sel) and not coarse_only:
                    f_first[sel] = sc.run(fu, fext, cells0[sel], cf[sel], ci[sel], lat)
                zone0 = (c_first < 0) & (f_first < 0)
                arrs[f"{lat}|{yi}|open"] = idx0[zone0].astype(np.int32)
                pos = {i: n for n, i in enumerate(idx0.tolist())}
                for b in bins[1:]:
                    idx, cells = band_cells(mv, cls, ye, b)
                    if not len(idx):
                        arrs[f"{lat}|{yi}|{bin_name(b)}"] = np.zeros(0, np.int32)
                        continue
                    k = np.array([pos[i] for i in idx.tolist()], np.int64)
                    cf, ci = cell_params(mv, sc.fr, cells, ye, b)
                    z = zone0[k].copy()
                    if prev is not None:
                        z |= np.isin(idx, arrs[f"{prev}|{yi}|{bin_name(b)}"])
                    use_c = (~z) & (c_first[k] >= 0)
                    use_f = (~z) & (c_first[k] < 0)
                    if use_c.any():
                        s1 = np.nonzero(use_c)[0]
                        r = sc.run(co, cext, cells[s1], cf[s1], ci[s1], lat, c_first[k][s1])
                        use_f[s1[r < 0]] = True
                    if use_f.any():
                        s2 = np.nonzero(use_f)[0]
                        if coarse_only:                 # the coarse walk above already failed
                            s3 = s2
                        else:
                            h = np.where(c_first[k][s2] < 0, f_first[k][s2], -1)
                            r = sc.run(fl, fx, cells[s2], cf[s2], ci[s2], lat, h)
                            s3 = s2[r < 0]
                        s3w = s3[near_wall(cf[s3], cells[s3])]
                        z[np.setdiff1d(s3, s3w)] = True
                        if len(s3w):
                            lib, ext = wall_lib(coarse_only)
                            cf2, ci2 = cell_params(mv, sc.fr, cells[s3w], ye, b, wall_lib=True)
                            r = sc.run(lib, ext, cells[s3w], cf2, ci2, lat)
                            z[s3w[r < 0]] = True
                    arrs[f"{lat}|{yi}|{bin_name(b)}"] = idx[z].astype(np.int32)
        np.savez_compressed(out / f"z_{name}__{state}.npz", **arrs)
        a = {k: len(v) for k, v in arrs.items() if k.endswith("open")}
        log(f"{state} {name}: {n_cells} open cells, open zone cells per (lat|y bin) {a} "
            f"({time.perf_counter() - t0:.0f} s)")


# ---------------------------------------------------------------------------------------------- pack and read
def cmd_pack(args) -> None:
    src = Path(args.src)
    for name in args.moves:
        mv = MOVES[name]
        gx, gy = grid(mv)
        yb = y_bins(mv)
        keys = [bin_name(b) for b in x_bin_keys()]
        parts, offs = [], []
        areas = {}
        missing: set = set()
        n_parts = 0
        for lat in LATS:
            for yi in range(len(yb)):
                zo = None
                for bn in keys:
                    z = np.zeros(len(gx) * len(gy), np.int8)
                    for cls, ss in CLASS_STATES.items():
                        for st in ss:
                            f = src / f"z_{name}__{st}.npz"
                            if not f.exists():
                                if args.partial:
                                    missing.add(st)
                                    continue
                                raise FileNotFoundError(f)
                            a = _load(str(f))
                            k = f"{lat}|{yi}|{bn}"
                            if k in a:
                                z[a[k]] = CLASSES.index(cls) + 1
                    for c in range(3):
                        areas[f"{lat}|{yb[yi]}|{bn}|{CLASSES[c]}"] = round(float((z == c + 1).sum()) * D * D, 2)
                    if zo is None:
                        zo = z                      # "open" (first): stored whole
                        nz = np.nonzero(z)[0]
                    else:                           # a wall bin: only its cells beyond the open zone
                        nz = np.nonzero((z != 0) & (zo == 0))[0]
                    offs.append(n_parts)
                    parts.append(np.stack([nz, z[nz]], 1).astype(np.int32) if len(nz) else np.zeros((0, 2), np.int32))
                    n_parts += len(nz)
        offs.append(n_parts)
        meta = {"move": asdict(mv), "grid_dx": D, "y_bins": yb.tolist(), "x_bins": keys, "lats": list(LATS),
                "classes": list(CLASSES), "bands": {"ground": BAND_GROUND, "low": BAND_LOW,
                                                    "high": (BAND_LOW[1], None)},
                "class_states": CLASS_STATES, "coords": "fan x (toward the attacked side) and y of the HeroBox centre "
                "relative to the enemy transform at the decision", "values": "1 ground, 2 low air, 3 high air",
                "storage": "per (lat, y bin): the open-floor zone, then per wall bin only its cells beyond it (the "
                           "reader adds them and clears the cells outside the arena)",
                "source": "ssbot.tools.aim_zones", "missing_states": sorted(missing)}
        npz = Path(args.npz_dir or FORUM) / f"aim_zones_{name}.npz"
        cells = np.concatenate(parts) if parts else np.zeros((0, 2), np.int32)
        np.savez_compressed(npz, meta=np.array(json.dumps(meta)), grid_x=gx, grid_y=gy, cells=cells,
                            offs=np.array(offs, np.int64))
        npz.with_suffix(".json").write_text(json.dumps({"meta": {k: meta[k] for k in ("grid_dx", "y_bins", "lats",
                                                                                      "bands", "values")},
                                                        "area_u2": areas}, indent=0), "utf-8")
        print(f"packed {name} -> {npz} ({len(cells)} zone cells over {len(offs) - 1} bins)")


@lru_cache(maxsize=64)
def _load(path: str):
    z = np.load(path)
    return {k: z[k] for k in z.files}


class AimZones:
    """Reader of aim_zones_<move>.npz: the composite zone of an enemy at (x, y) attacking toward side s."""

    def __init__(self, path: str | Path):
        z = np.load(path, allow_pickle=False)
        self.meta = json.loads(str(z["meta"]))
        self.name = self.meta["move"]["name"]
        self.gx, self.gy = z["grid_x"], z["grid_y"]
        self.cells, self.offs = z["cells"], z["offs"]
        self.yb = np.array(self.meta["y_bins"])
        self.xkeys = self.meta["x_bins"]
        self.lats = list(self.meta["lats"])
        self._xi = {k: i for i, k in enumerate(self.xkeys)}
        self._last = None

    def bin_index(self, x: float | None, side: int) -> int:
        if x is None:
            return 0
        xb = float(min(X_BINS, key=lambda b: abs(b - x)))
        return self._xi.get(bin_name((xb, 1 if side >= 0 else -1)), 0)

    def zone(self, x: float | None, y: float, side: int, lat: int = 2) -> np.ndarray:
        """int8 [len(grid_y), len(grid_x)] in fan coordinates (x toward the side, y up; HeroBox centre rel. the enemy):
        0 none, 1 ground, 2 low air, 3 high air. x None: the open floor (no walls)."""
        key = (None if x is None else round(float(x), 2), round(float(y), 2), 1 if side >= 0 else -1, int(lat))
        if self._last is not None and self._last[0] == key:
            return self._last[1]
        li = self.lats.index(lat)
        yi = int(np.argmin(np.abs(self.yb - y)))
        k0 = (li * len(self.yb) + yi) * len(self.xkeys)
        z = np.zeros(len(self.gx) * len(self.gy), np.int8)
        for k in ((k0,) if x is None else (k0, k0 + self.bin_index(x, side))):
            c = self.cells[self.offs[k]:self.offs[k + 1]]
            z[c[:, 0]] = c[:, 1]
        z = z.reshape(len(self.gy), len(self.gx))
        if x is not None:                       # the arena: walls (HeroBox side) and the dome (HeroBox top)
            sd = 1 if side >= 0 else -1
            xw = x + sd * self.gx
            out_x = (xw < WALL_L + HB_HW) | (xw > WALL_R - HB_HW)
            z[:, out_x] = 0
            z[(y + self.gy[:, None] + HB_HH) > dome_ceiling(xw)[None, :]] = 0
        self._last = (key, z)
        return z

    def area(self, x: float | None, y: float, side: int, lat: int = 2) -> dict:
        z = self.zone(x, y, side, lat)
        return {c: round(float((z == i + 1).sum()) * D * D, 2) for i, c in enumerate(CLASSES)}

    def inescapable(self, hero_hb: tuple, enemy: tuple, side: int, lat: int = 2) -> int:
        """The class code (0 = not in the zone) of the hero's HeroBox centre (world) for an enemy at `enemy`."""
        dx = (hero_hb[0] - enemy[0]) * (1 if side >= 0 else -1)
        dy = hero_hb[1] - enemy[1]
        ix = int(math.floor((dx - self.gx[0] + D / 2) / D))
        iy = int(math.floor((dy - self.gy[0] + D / 2) / D))
        if not (0 <= ix < len(self.gx) and 0 <= iy < len(self.gy)):
            return 0
        return int(self.zone(enemy[0], enemy[1], side, lat)[iy, ix])

    def world_polys(self, x: float, y: float, side: int, lat: int = 2) -> dict:
        """{class: [world polygon [n, 2]]} of the zone placed at the enemy (x, y) facing side (cell-corner outlines)."""
        from ssbot.combat.attack_range import Mask, contours
        z = self.zone(x, y, side, lat)
        ix0 = int(round((self.gx[0] - D / 2) / D))
        iy0 = int(round((self.gy[0] - D / 2) / D))
        sd = 1 if side >= 0 else -1
        out = {}
        for i, c in enumerate(CLASSES):
            m = z == i + 1
            if m.any():
                out[c] = [np.stack([x + sd * q[:, 0], y + q[:, 1]], 1) for q in contours(Mask(m, ix0, iy0), D)]
        return out


@lru_cache(maxsize=1)
def readers(root: str | None = None) -> dict:
    """{move name: AimZones} of the packed tables that exist."""
    out = {}
    for name in MOVES:
        p = Path(root or FORUM) / f"aim_zones_{name}.npz"
        if p.exists():
            out[name] = AimZones(p)
    return out


def pending_move(type_key: str, state: str | None) -> str | None:
    """The move pending in an enemy state (None: none)."""
    for name, mv in MOVES.items():
        if mv.type_key == type_key and state in mv.pending:
            if name == "CC_JUMP" and state == "Jump Aim":
                continue                         # the jump cast shares it; the tracker's family decides (overlay)
            return name
    return None


# ---------------------------------------------------------------------------------------------- CLI
def cmd_scan(args) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    p = hero_params(False)
    states = args.states or [s for ss in CLASS_STATES.values() for s in ss]
    for st in states:
        if st not in STATES:
            raise KeyError(st)
        todo = [m for m in args.moves if not (out / f"z_{m}__{st}.npz").exists()]
        if todo:
            scan_state(out, st, todo, p, log=lambda s: print(s, flush=True))


def class_tables(moves: dict, lat: int = 2, p=None, coarse: bool = False, log=print) -> dict:
    """{(move, class): bool [ny, nx]}: the zone over the whole grid with EVERY cell using one class (open floor, the
    enemy at moves[move] = its y), the PNGs' class tables. Per state: the coarse library, then the full one for the
    cells the coarse one left inescapable (coarse: the coarse library only, a superset); the class's zone is the union
    over its states."""
    p = p or hero_params(False)
    out = {}
    jobs = []
    for name, ye in moves.items():
        sc = Scanner(name)
        gx, gy = grid(sc.mv)
        X, Y = np.meshgrid(gx, gy)
        cells = np.stack([X.ravel(), Y.ravel()], 1)
        ok = cells[:, 1] + ye - FLOOR_Y - HB_STAND >= BAND_GROUND[0]           # above the floor
        if sc.mv.aim == "hero":
            ok &= cells[:, 0] >= 0
        cf, ci = cell_params(sc.mv, sc.fr, cells, ye, "open")
        jobs.append((name, sc, cells, ok, cf, ci, (len(gy), len(gx))))
        for cls in CLASSES:
            out[(name, cls)] = np.zeros(len(cells), bool)
    for cls, states in CLASS_STATES.items():
        for st in states:
            co = build_library(st, p, 0.0, T_LIB, coarse=True)
            fu = co if coarse else build_library(st, p, 0.0, T_LIB, coarse=False)
            ce = lib_ext(co)
            fe = ce if coarse else lib_ext(fu)
            for name, sc, cells, ok, cf, ci, _ in jobs:
                z = out[(name, cls)]
                sel = np.nonzero(ok & ~z)[0]
                r = sc.run(co, ce, cells[sel], cf[sel], ci[sel], lat)
                sel = sel[r < 0]
                if len(sel) and not coarse:
                    r = sc.run(fu, fe, cells[sel], cf[sel], ci[sel], lat)
                    sel = sel[r < 0]
                z[sel] = True
            log(f"class tables: {st} done")
            del co, fu
    shapes = {j[0]: j[6] for j in jobs}
    return {k: v.reshape(shapes[k[0]]) for k, v in out.items()}


PNG_AT = {"RE_STAB": 7.0, "MA_SLASH": 6.0, "CC_JUMP": 6.5, "CC_JUMP_CAST": 6.5, "AT_DIVE": 14.0}
PNG_X = {"open floor (x 31.5)": (31.5, 1), "wall 2 u ahead (x 16.5, toward the left wall)": (16.5, -1),
         "wall 2 u behind (x 16.5, away from it)": (16.5, 1)}


def cmd_png(args) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rd = readers(args.npz_dir)
    moves = {m: PNG_AT[m] for m in args.moves if m in rd}
    ct = (class_tables(moves, args.lat, coarse=True, log=lambda q: print(q, flush=True)) if args.class_tables
          else {})
    cm = ListedColormap(["#ffffff", "#d62728", "#ff9f1c", "#1f77b4"])
    summary = {}
    for name, ye in moves.items():
        r = rd[name]
        mv = MOVES[name]
        ext = [r.gx[0] - D / 2, r.gx[-1] + D / 2, r.gy[0] - D / 2, r.gy[-1] + D / 2]
        fig, axs = plt.subplots(2, 3, figsize=(18, 10.5))
        summary[name] = {}
        for ax, (lab, (xe, sd)) in zip(axs[0], PNG_X.items()):
            z = r.zone(xe, ye, sd, args.lat)
            ax.imshow(z, origin="lower", extent=ext, cmap=cm, vmin=0, vmax=3, interpolation="nearest")
            a = r.area(xe, ye, sd, args.lat)
            summary[name][lab] = a
            ax.set_title(f"{lab}\nG {a['ground']:.2f} / L {a['low']:.2f} / H {a['high']:.2f} u2", fontsize=9)
            _png_terrain(ax, mv, ye, xe, sd, ext)
        for ax, cls in zip(axs[1], CLASSES):
            z = ct.get((name, cls))
            if z is not None:
                ax.imshow(np.where(z, CLASSES.index(cls) + 1, 0), origin="lower", extent=ext, cmap=cm, vmin=0, vmax=3,
                          interpolation="nearest")
                a = float(z.sum()) * D * D
                summary[name][f"class table {cls}"] = round(a, 2)
                ax.set_title(f"class table {cls.upper()} (every cell, open floor, coarse library): {a:.2f} u2",
                             fontsize=9)
            else:
                ax.set_title(f"class table {cls} (not computed)", fontsize=9)
            _png_terrain(ax, mv, ye, None, 1, ext)
        fig.suptitle(f"{name} aim zone, lat {args.lat}, enemy y {ye} ({mv.decision}). HeroBox-centre cells relative to "
                     f"the enemy at the decision, x toward the attacked side. red = ground band (-0.25..+0.25 u of "
                     f"standing), orange = low air 0.25-1.5 u no dash, blue = high air >= 1.5 u no dash", fontsize=9)
        fig.tight_layout()
        fig.savefig(out / f"aimzone_{name}.png", dpi=90)
        plt.close(fig)
        print(f"png {name}", flush=True)
    (out / "png_summary.json").write_text(json.dumps(summary, indent=1), "utf-8")


def _png_terrain(ax, mv: Move, ye: float, xe, sd: int, ext) -> None:
    fl = FLOOR_Y + HB_STAND - ye
    for h, ls in ((BAND_GROUND[0], "-"), (BAND_GROUND[1], ":"), (BAND_LOW[1], ":")):
        ax.axhline(fl + h, color="0.4", lw=0.8, ls=ls)
    ax.axhline(FLOOR_Y - ye, color="k", lw=1.5)
    if xe is not None:
        for w in (WALL_L, WALL_R):
            ax.axvline(sd * (w - xe), color="k", lw=2.0)
    ax.plot([0], [0], "k+", ms=12)
    ax.set_xlim(ext[0], ext[1])
    ax.set_ylim(ext[2], ext[3])
    ax.set_aspect("equal")
    ax.grid(alpha=0.2)


VALIDATE = {   # move -> (the decision state(s), the antic state(s) right before it)
    "RE_STAB": ("Stab 1", ("Stab Antic",)),
    "MA_SLASH": ("Slash 1", ("Fire Antic",)),
    "CC_JUMP": ("Jump Aim|Jump|Air", ("Jump Antic",)),
    "CC_JUMP_CAST": ("Jump Aim|Jump|Air", ("Cast Slam Antic", "Cast Slam Antic 2")),
    "AT_DIVE": ("Fire", ("Fire Ready",)),
}


def _count(rows, f) -> int:
    return sum(1 for q in rows if f(q))


def cmd_validate(args) -> None:
    """At every recorded decision (the first frame of the decision state after the antic), the hero's HeroBox centre
    in the composite zone (its own height class) vs whether this enemy hit the hero within the move (j_max frames)."""
    from ssbot.combat import attack_range as ar
    from ssbot.knowledge.forum_cache import load_cache
    from ssbot.tools.aim_ics import HB_DY
    from ssbot.tools.attack_range_build import _cache_files, tracks_from_cache
    rd = readers(args.npz_dir)

    def hero_hits(c) -> dict:
        """obj name -> game times the hero took (or was saved by i-frames from) damage from it."""
        names = {}
        for ev in c["events"]:
            if ev[1] == "fsm" and ev[2].get("obj"):
                names[int(ev[2].get("ent", -1))] = str(ev[2]["obj"])
        T = c["T"]
        fidx = {int(f): i for i, f in enumerate(c["f"])}
        out: dict = {}
        for ev in c["events"]:
            if ev[1] in ("damage", "damage_blocked") and ev[2].get("hazard") == "ENEMY":
                i = fidx.get(int(ev[2].get("first_f", ev[0])))
                if i is not None:
                    for part in str(ev[2].get("source", "")).split("/"):
                        out.setdefault(part, []).append(float(T[i]))
        return names, out
    res = {}
    for name in args.moves:
        if name not in rd:
            continue
        mv = MOVES[name]
        r = rd[name]
        spec = ar.SPECS[mv.type_key]
        tab = ar.load_table(None, spec)
        dec, antic = VALIDATE[name]
        decs = dec.split("|")
        rows = []
        tracks = []
        for src in args.sets:
            for f in _cache_files(src):
                c = load_cache(f)
                names, hh = hero_hits(c)
                for tr in tracks_from_cache(c, spec.type_key, src):
                    tr["hero_hits"] = hh.get(names.get(tr["iid"], "?"), [])
                    tracks.append(tr)
        for tr in tracks:
            src = tr["source"]
            st = tr["st"]
            for j in range(1, len(st)):
                if not (st[j] in decs and st[j - 1] in antic):
                    continue
                x, y = float(tr["x"][j]), float(tr["y"][j])
                hx, hy = float(tr["hx"][j]), float(tr["hy"][j]) + HB_DY
                side = tab.facing(bool(tr["flip"][j])) if mv.aim == "facing" else (1 if hx >= x else -1)
                t0, t1 = float(tr["T"][j]) - 1e-6, float(tr["T"][j]) + mv.j_max / 60.0
                row = {"src": src, "fight": tr.get("fight"), "f": int(tr["f"][j]), "x": round(x, 2),
                       "y": round(y, 2), "side": side, "hx": round(hx, 2), "hy": round(hy, 2),
                       "hit": any(t0 <= h <= t1 for h in tr["hero_hits"]),
                       "enemy_hit": any(t0 - 0.5 <= h <= t1 for h in tr["hits"]),
                       "clash": any(t0 <= h <= t1 for h in tr["clash"])}
                for lat in LATS:
                    row[f"zone{lat}"] = r.inescapable((hx, hy), (x, y), side, lat)
                rows.append(row)
        out = {"decisions": len(rows), "hit": _count(rows, lambda q: q["hit"])}
        for lat in LATS:
            k = f"zone{lat}"
            out[f"lat{lat}"] = {
                "in_zone": _count(rows, lambda q: q[k] > 0),
                "in_zone_hit": _count(rows, lambda q: q[k] > 0 and q["hit"]),
                "in_zone_not_hit": _count(rows, lambda q: q[k] > 0 and not q["hit"]),
                "in_zone_not_hit_no_clash": _count(rows, lambda q: q[k] > 0 and not q["hit"] and not q["clash"]),
                "in_zone_not_hit_undisturbed": _count(rows, lambda q: q[k] > 0 and not q["hit"] and not q["clash"]
                                                      and not q["enemy_hit"]),
                "by_class": {c: _count(rows, lambda q, i=i: q[k] == i + 1) for i, c in enumerate(CLASSES)},
                "undisturbed_by_class": {c: _count(rows, lambda q, i=i: q[k] == i + 1 and not q["hit"]
                                                   and not q["clash"] and not q["enemy_hit"])
                                         for i, c in enumerate(CLASSES)},
                "out_zone_hit": _count(rows, lambda q: q[k] == 0 and q["hit"])}
        out["examples_in_zone_not_hit"] = [q for q in rows if q["zone2"] > 0 and not q["hit"]][:12]
        res[name] = out
        print(name, json.dumps({k: v for k, v in out.items() if k != "examples_in_zone_not_hit"}), flush=True)
    Path(args.json).write_text(json.dumps(res, indent=1), "utf-8")


def main():
    try:
        import psutil
        psutil.Process().nice(psutil.IDLE_PRIORITY_CLASS)
    except Exception:  # noqa: BLE001  (not Windows / no psutil: normal priority)
        pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("scan")
    a.add_argument("--out", required=True)
    a.add_argument("--moves", nargs="+", default=list(MOVES))
    a.add_argument("--states", nargs="*")
    b = sub.add_parser("pack")
    b.add_argument("--src", required=True)
    b.add_argument("--moves", nargs="+", default=list(MOVES))
    b.add_argument("--npz-dir")
    b.add_argument("--partial", type=int, default=0, help="1: pack without the states not scanned yet (a test)")
    c = sub.add_parser("png")
    c.add_argument("--out", required=True)
    c.add_argument("--moves", nargs="+", default=list(MOVES))
    c.add_argument("--lat", type=int, default=2)
    c.add_argument("--class-tables", type=int, default=1)
    c.add_argument("--npz-dir")
    v = sub.add_parser("validate")
    v.add_argument("--json", required=True)
    v.add_argument("--moves", nargs="+", default=list(MOVES))
    v.add_argument("--sets", nargs="+", default=["dev"])
    v.add_argument("--npz-dir")
    args = ap.parse_args()
    {"scan": cmd_scan, "pack": cmd_pack, "png": cmd_png, "validate": cmd_validate}[args.cmd](args)


if __name__ == "__main__":
    main()
