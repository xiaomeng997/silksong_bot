"""Forum planner v2-lite (SSBOT_FORUM_V2=1; docs/plans/forum_zones_v2.md, the person's decisions of 2026-10-09 .. 11 in
docs/plans/forum_planner_plan.md sec. 5): the planner's safe test on the per-enemy attack-range estimate
(combat.attack_range, approved for all ten types) instead of the MultiForecast support. Off (the default) nothing here
runs and ForumPlanner is the earlier planner bit for bit.

What a row must satisfy under v2 (ForumPlanner.tick with a V2Forecast):
  decided danger  every frame of the row (nominal lane, then the bounds_lo envelope) keeps the hero's HeroBox out of
                  every enemy's attack-range estimate at that look-ahead, dilated by the margin m(type, k) (MARGINS
                  below; the person: the margin is a decision separate from the estimate, taken from the error
                  statistics). Idle / moving bodies are the body now carried by its velocity (IDLE_CARRY) plus the
                  margin; a not-started attack is not in it (it cannot hurt before its antic ends; the next ticks see
                  the antic); counters only after a hit (the hit branch below).
  hit branch      a row with a predicted nail hit is rolled out again with the hit's effect (recoil / bounce,
                  combat.kinematics events) and checked against the same estimate plus the hit enemy's reaction (the
                  family its TOOK DAMAGE exit starts, its attack-range template placed from the hit frame, both
                  facings): S = miss branch | hit branch.
  pending aims    an enemy in a pending aimed antic (tools.aim_zones: Reed stab, Maestro slash side, Clapper jump /
                  jump cast, Tiny dive) decides its aim at a measured time after the antic start (DECISION_S): on every
                  frame of that window inside the row (or at the row's end when the decision comes after it), and on
                  through a hero lock that holds then, the hero's HeroBox centre must be outside the move's composite
                  inescapable zone (each cell by its own height class, terrain-aware), lat 2.
  escape ready    the chosen row's end leaves an escape: one of the escape commands (stay, run either way, a full jump
                  either way, a dash either way then run) keeps the nominal box out of the estimate for ESC_F frames
                  past the end (ForumPlanner._escape_fail_v2); a chosen row without one is S = 1. Past the end an
                  idle body counts with ESC_IDLE_M only (idle enemies have no inescapable zone; the growing margin
                  is the replanning's business), moves under way and hazards with their margin.
  objective       safety first (the lexicographic keys before it unchanged), then the most landed hits on real enemies
                  in the horizon, the earliest first hit, then J.

The estimate is sampled at SAMPLE_KS look-aheads (frames from the tracker's last frame); a frame between two samples
reads the union of both (a conservative bracket). Rasters: CELL u over the arena (CANVAS), hero-centre space for the
planner's box centre (the kinematics box = STATE hero.box = HeroController.Bounds 0.5 x 2.079; the real hurtbox
HeroBox 0.4554 x 2.2498 is centred HB_DY above the Bounds centre: p50 of the person's 20261004_133855 attempt 1, box
centre - transform -0.513, HeroBox centre = transform - 0.38).
"""
from __future__ import annotations

import copy
import math
import os
import time

import numpy as np

from ssbot.combat.attack_range import (FT, Mask, RangeTracker, _first_state, body_polys, carry_body, empty_mask,
                                       union)
from ssbot.core.forum import FLOOR_Y, WALL_L, WALL_R

V2_ON = os.environ.get("SSBOT_FORUM_V2", "0").strip() == "1"
EVERY = int(os.environ.get("SSBOT_FORUM_V2_EVERY", "1") or 1)   # V2Feed: rebuild the support every this many frames
MARGIN_MODE = os.environ.get("SSBOT_FORUM_V2_MARGIN", "rule").strip().lower() or "rule"
# the escape check runs on a carried CONTINUE row too (1v1 live, forum.md 44: a row chosen with an escape kept running
# into a Slam Antic's reach unchecked until no row had one; SSBOT_FORUM_V2_ESC_CARRIED=0: the old skip)
ESC_CARRIED = os.environ.get("SSBOT_FORUM_V2_ESC_CARRIED", "1").strip() != "0"
# the Clapper's corner (1v1 live, forum.md 44: 16 of 26 slam hits): with its body this close to a wall (u) the strip
# between them is a trap - a slam it starts facing the wall reaches 12 u, so the antic leaves no way out but the wall
# top (y >= 11.8, never hit; forum.md 42). A safe row ending there ranks after every safe row ending elsewhere
# (SSBOT_FORUM_V2_CORNER=0: off)
CORNER_U = float(os.environ.get("SSBOT_FORUM_V2_CORNER", "13") or 0.0)
CORNER_TOP_Y = 11.15                  # the hero's Bounds centre at a wall-top cling (transform y 11.8)
CLAPPER = "Song Heavy Sentry"


def corner_zones(fc) -> list[tuple[float, float]]:
    """[(x0, x1)] the strips between a live Clapper's transform and a wall closer than CORNER_U (hero x)."""
    if CORNER_U <= 0:
        return []
    out = []
    for tr in (getattr(fc, "trackers", None) or {}).values():
        if tr.dead or tr.pos is None or getattr(getattr(tr, "table", None), "type_key", None) != CLAPPER:
            continue
        x = float(tr.pos[0])
        if x - WALL_L < CORNER_U:
            out.append((WALL_L - 1.0, x))
        if WALL_R - x < CORNER_U:
            out.append((x, WALL_R + 1.0))
    return out

CELL = 0.1
CANVAS = (WALL_L - 2.0, FLOOR_Y - 3.0, WALL_R + 2.0, 27.0)      # x0, y0, x1, y1 (u)
BOUNDS_HALF = (0.25, 1.0394)          # the kinematics box half extents (STATE hero.box)
HB_HX, HB_HY = 0.2277, 1.1249         # HeroBox half extents
HB_DY = 0.133                         # HeroBox centre - Bounds centre (y)
# look-ahead samples (frames; the escape check reads past the horizon): 16 (forum_v2_bench: 23 cost 5.5 / 19.5 ms p50
# with all / 6+ enemies)
SAMPLE_KS = (0, 2, 4, 6, 9, 12, 15, 18, 22, 26, 31, 36, 42, 48, 55, 62)
ESC_F = 24                            # frames past the row's end an escape must stay clear
ESC_FROM_K = 30                       # samples from this planner frame on get the escape check's rasters
ESC_IDLE_M = 0.5                      # the escape check's margin of an idle body (the estimate's k <= 12 margin)
K_HOLD = 36                           # the margin's k stops growing here (the error statistics end at k 36)

# the margin m(type, k) in u (MARGIN_MODE "rule", the default; C:/ssbot/data/m2_forum_are/idlevel/summary.md): the
# body carried by its velocity + 0.5 u covers >= 99.3 % up to k 12 for every flier / walker; beyond, the fliers need
# about 0.3 + 11 t^2 u; the walkers (Envoy, Choristor) stay within their measured 99 % row margin (<= 1.05 u at k 36).
# The Clapper's measured row margin is larger (3.2 / 4.75 / 7.65 / 9.25 u at k 12 / 18 / 30 / 36: Idle -> Walk at 8
# u/s and walk reversals): "rule" gives it the fliers' curve (the planner replans every frame, the escape requirement
# covers the rest); "table" uses every type's measured 99 % row margin (max over fresh / R2 / person) as it is; "flat:x"
# a constant x u; "zero" none.
WALKERS = {"Song Pilgrim 01": ((0, 0.5), (36, 0.5)),
           "Song Pilgrim 03": ((0, 0.5), (12, 0.5), (18, 0.5), (30, 0.91), (36, 1.05))}
TABLE_M99 = {   # type key -> ((k, m99 u), ...) from the idle-velocity summary (max over the three sets)
    "Pilgrim 03 Song": ((1, 0.14), (6, 0.25), (12, 0.64), (18, 1.18), (30, 2.9), (36, 3.93)),
    "Song Pilgrim 03": ((1, 0.0), (6, 0.05), (12, 0.05), (18, 0.49), (30, 0.91), (36, 1.05)),
    "Song Heavy Sentry": ((1, 0.79), (6, 1.6), (12, 3.2), (18, 4.75), (30, 7.65), (36, 9.25)),
    "Song Handmaiden": ((1, 0.14), (6, 0.28), (12, 0.78), (18, 1.56), (30, 3.71), (36, 4.99)),
    "Song Pilgrim 01": ((1, 0.05), (6, 0.05), (12, 0.05), (18, 0.05), (30, 0.27), (36, 0.35)),
    "Song Pilgrim Maestro": ((1, 0.13), (6, 0.28), (12, 0.81), (18, 1.5), (30, 3.28), (36, 4.05)),
    "Song Administrator": ((1, 0.18), (6, 1.05), (12, 1.49), (18, 1.67), (30, 2.22), (36, 2.67)),
    "Song Reed": ((1, 0.4), (6, 0.47), (12, 0.74), (18, 1.36), (30, 2.98), (36, 3.94)),
    "Song Automaton Tiny": ((1, 0.11), (6, 0.21), (12, 0.57), (18, 1.05), (30, 2.29), (36, 3.12)),
}

# pending aims: the decision's window (s since the antic start: tools.aim_zones MOVES / forum_zones_v2 3.1)
DECISION_S = {"RE_STAB": (0.633, 0.667), "MA_SLASH": (0.683, 0.733), "CC_JUMP": (0.483, 0.517),
              "CC_JUMP_CAST": (0.883, 0.933), "AT_DIVE": (0.699, 0.766)}
AIM_LAT = 2
LOCK_EXT_F = 24                       # a hero lock at the decision extends the zone test by up to this many frames


def _interp(pts, k: float) -> float:
    ks = [p[0] for p in pts]
    ms = [p[1] for p in pts]
    return float(np.interp(k, ks, ms))


def margin(type_key: str, k: int, mode: str | None = None) -> float:
    """m(type, k) in u (module docstring)."""
    mode = MARGIN_MODE if mode is None else mode
    k = min(max(int(k), 0), K_HOLD)
    if mode == "zero":
        return 0.0
    if mode.startswith("flat:"):
        return float(mode.split(":", 1)[1])
    if mode == "table":
        return _interp(TABLE_M99.get(type_key, ((0, 0.5), (36, 0.5))), k)
    if type_key in WALKERS:
        return max(0.5, _interp(WALKERS[type_key], k))
    if k <= 12:
        return 0.5
    t = k * FT
    return max(0.5, 0.3 + 11.0 * t * t)


def box_kernel(m: float, cell: float = CELL) -> tuple[np.ndarray, tuple[int, int]]:
    """(cv2 kernel, anchor) taking a raw damage raster (row 0 lowest y) to Bounds-centre space with margin m: cell p
    is set when, for some point of p's cell, the HeroBox there grown by m meets an occupied cell q (a CELL square).
    Offsets n = q - p (cells) with (n +- 0.5) c meeting [A, B]: x A = -(HB_HX + m + c/2), B = -A; y A = HB_DY - HB_HY -
    m - c/2, B = HB_DY + HB_HY + m + c/2."""
    ax = HB_HX + m + cell / 2
    nx_lo, nx_hi = int(math.ceil(-ax / cell - 0.5 - 1e-9)), int(math.floor(ax / cell + 0.5 + 1e-9))
    ay0, ay1 = HB_DY - HB_HY - m - cell / 2, HB_DY + HB_HY + m + cell / 2
    ny_lo, ny_hi = int(math.ceil(ay0 / cell - 0.5 - 1e-9)), int(math.floor(ay1 / cell + 0.5 + 1e-9))
    # cv2.dilate: dst(p) = max over kernel (i, j) of src(p + (j, i) - anchor): j - ax_ = n_x
    return np.ones((ny_hi - ny_lo + 1, nx_hi - nx_lo + 1), np.uint8), (-nx_lo, -ny_lo)


def coarse(m: Mask, from_cell: float, cell: float = CELL) -> tuple[np.ndarray, int, int]:
    """A lattice raster at from_cell (0.05) on the CELL lattice (an integer multiple): any-pooling (conservative)."""
    r = int(round(cell / from_cell))
    if r <= 1:
        return m.m, m.ix0, m.iy0
    ix0 = m.ix0 // r
    iy0 = m.iy0 // r
    px, py = m.ix0 - ix0 * r, m.iy0 - iy0 * r
    ny = -(-(m.m.shape[0] + py) // r)
    nx = -(-(m.m.shape[1] + px) // r)
    big = np.zeros((ny * r, nx * r), bool)
    big[py:py + m.m.shape[0], px:px + m.m.shape[1]] = m.m
    return big.reshape(ny, r, nx, r).any(axis=(1, 3)), ix0, iy0


class Canvas:
    """The arena on the CELL lattice: cell (i, j) covers x in [x0 + j c, ...), y in [y0 + i c, ...)."""

    def __init__(self, cell: float = CELL, box=CANVAS):
        self.cell = cell
        self.x0, self.y0, x1, y1 = box
        self.jx0 = int(math.floor(self.x0 / cell))
        self.iy0 = int(math.floor(self.y0 / cell))
        self.nx = int(math.ceil(x1 / cell)) - self.jx0
        self.ny = int(math.ceil(y1 / cell)) - self.iy0

    def zeros(self) -> np.ndarray:
        return np.zeros((self.ny, self.nx), bool)

    def paste(self, dst: np.ndarray, src: np.ndarray, ix0: int, iy0: int) -> None:
        r0, c0 = iy0 - self.iy0, ix0 - self.jx0
        a0, b0 = max(r0, 0), max(c0, 0)
        a1, b1 = min(r0 + src.shape[0], self.ny), min(c0 + src.shape[1], self.nx)
        if a1 > a0 and b1 > b0:
            dst[a0:a1, b0:b1] |= src[a0 - r0:a1 - r0, b0 - c0:b1 - c0]

    def index(self, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(row, col, valid) of world points (NaN / outside: not valid; row / col 0 there)."""
        with np.errstate(invalid="ignore"):
            col = np.floor(x / self.cell).astype(np.float64) - self.jx0
            row = np.floor(y / self.cell).astype(np.float64) - self.iy0
            ok = np.isfinite(col) & np.isfinite(row) & (col >= 0) & (col < self.nx) & (row >= 0) & (row < self.ny)
        col = np.where(ok, col, 0).astype(np.int64)
        row = np.where(ok, row, 0).astype(np.int64)
        return row, col, ok


def dilate_group(parts, m: float, cell: float = CELL) -> tuple[np.ndarray, int, int]:
    """Coarse rasters [(mask, ix0, iy0)] on the CELL lattice, one dilation for all (the same margin m)."""
    import cv2
    parts = [p for p in parts if p[0].size]
    if not parts:
        return np.zeros((0, 0), bool), 0, 0
    x0 = min(p[1] for p in parts)
    y0 = min(p[2] for p in parts)
    x1 = max(p[1] + p[0].shape[1] for p in parts)
    y1 = max(p[2] + p[0].shape[0] for p in parts)
    k, (axn, ayn) = box_kernel(m, cell)
    kh, kw = k.shape
    img = np.zeros((y1 - y0 + 2 * kh, x1 - x0 + 2 * kw), np.uint8)
    for c, ix0, iy0 in parts:
        r, q = iy0 - y0 + kh, ix0 - x0 + kw
        img[r:r + c.shape[0], q:q + c.shape[1]] |= c.view(np.uint8)
    d = cv2.dilate(img, k, anchor=(axn, ayn), borderType=cv2.BORDER_CONSTANT, borderValue=0)
    return d.view(bool), x0 - kw, y0 - kh


def dilate(raw: Mask, from_cell: float, m: float, cell: float = CELL) -> tuple[np.ndarray, int, int]:
    """A raw estimate (from_cell lattice) in Bounds-centre space on the CELL lattice with margin m: (mask, ix0, iy0)."""
    import cv2
    if raw is None or not raw.m.size or not raw.m.any():
        return np.zeros((0, 0), bool), 0, 0
    c, ix0, iy0 = coarse(raw, from_cell, cell)
    k, (axn, ayn) = box_kernel(m, cell)
    kh, kw = k.shape
    img = np.zeros((c.shape[0] + 2 * kh, c.shape[1] + 2 * kw), np.uint8)
    img[kh:kh + c.shape[0], kw:kw + c.shape[1]] = c
    d = cv2.dilate(img, k, anchor=(axn, ayn), borderType=cv2.BORDER_CONSTANT, borderValue=0)
    return d.astype(bool), ix0 - kw, iy0 - kh


class _Half:
    """What Planner._contacts reads of a support's forecaster (fc.half: the hull points' spacing) and the rest of the
    wrapped one's (model, tables, ...)."""

    def __init__(self, inner, half):
        self._inner = inner
        self.half = half

    def __getattr__(self, name):
        if name == "_inner":
            raise AttributeError(name)
        return getattr(self._inner, name)


class LayerSupport:
    """Sampled per-enemy rasters (Bounds-centre space, margins in) and their union per sample: the occupancy of
    planner points [n, T] at tk s from the origin. layers: {sample index: [(iid, mask, ix0, iy0)]}."""

    def __init__(self, canvas: Canvas, samples: tuple, k_shift: int = 0, inner_fc=None):
        self.cv = canvas
        self.samples = tuple(int(k) for k in samples)
        self.k_shift = int(k_shift)
        self.layers: dict = {i: [] for i in range(len(self.samples))}
        self.raw: dict = {i: [] for i in range(len(self.samples))}     # add_raw: (iid, coarse, ix0, iy0, m, esc_m)
        self.pend: list = []        # pending aims (RangeSupport.build: pending_aims)
        self.stack_esc: np.ndarray | None = None    # the escape check's danger (add_esc), None: the stack
        self.stack = np.zeros((len(self.samples), canvas.ny, canvas.nx), bool)
        self.fc = _Half(inner_fc, BOUNDS_HALF)
        smax = self.samples[-1] if self.samples else 0
        js = np.arange(smax + 1)
        si = np.searchsorted(np.array(self.samples), js)            # the first sample >= j
        si = np.minimum(si, len(self.samples) - 1)
        lo = np.where(np.array(self.samples)[si] == js, si, np.maximum(si - 1, 0))
        self._lo, self._hi = lo.astype(np.int64), si.astype(np.int64)

    def add(self, si: int, iid: int, mask: np.ndarray, ix0: int, iy0: int) -> None:
        if not mask.size:
            return
        self.layers[si].append((iid, mask, ix0, iy0))
        self.cv.paste(self.stack[si], mask, ix0, iy0)

    def add_raw(self, si: int, iid: int, c: np.ndarray, ix0: int, iy0: int, m: float | None,
                esc_m: float | None = None) -> None:
        """A coarse raw raster (CELL lattice, not dilated) of enemy iid at sample si, dilated by m into the stack and
        by esc_m into the escape check's stack (None: not in that one) when finish() runs: one dilation per (sample,
        margin) for all enemies."""
        if c.size and c.any():
            self.raw[si].append((iid, c, ix0, iy0, m, esc_m))

    def finish(self) -> None:
        for si, parts in self.raw.items():
            for which, idx in ((0, 4), (1, 5)):
                by_m: dict = {}
                for p in parts:
                    if p[idx] is not None:
                        by_m.setdefault(round(float(p[idx]), 4), []).append((p[1], p[2], p[3]))
                for m, ps in by_m.items():
                    d, x0, y0 = dilate_group(ps, m, self.cv.cell)
                    if which == 0:
                        self.cv.paste(self.stack[si], d, x0, y0)
                    else:
                        if self.stack_esc is None:
                            self.stack_esc = np.zeros(self.stack.shape, bool)
                        self.cv.paste(self.stack_esc[si], d, x0, y0)

    def add_esc(self, si: int, mask: np.ndarray, ix0: int, iy0: int) -> None:
        """A raster of the escape check's danger (occupied_esc; without any, the escape reads the full support)."""
        if not mask.size:
            return
        if self.stack_esc is None:
            self.stack_esc = np.zeros(self.stack.shape, bool)
        self.cv.paste(self.stack_esc[si], mask, ix0, iy0)

    def occupied_esc(self, x, y, tk) -> np.ndarray:
        """The escape check's danger past the row's end (RangeSupport.build: idle bodies with ESC_IDLE_M only)."""
        return self._occ_stack(self.stack if self.stack_esc is None else self.stack_esc, x, y, tk)

    def _sample_of(self, tk: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        j = np.rint(np.asarray(tk, np.float64) / FT).astype(np.int64) - self.k_shift
        j = np.clip(j, 0, len(self._lo) - 1)
        return self._lo[j], self._hi[j]

    def _occ_stack(self, stack: np.ndarray, x, y, tk) -> np.ndarray:
        x = np.asarray(x, np.float64)
        y = np.asarray(y, np.float64)
        lo, hi = self._sample_of(tk)
        row, col, ok = self.cv.index(x, y)
        shp = x.shape
        a = np.broadcast_to(lo, shp)
        b = np.broadcast_to(hi, shp)
        return ok & (stack[a, row, col] | stack[b, row, col])

    def occupied(self, x, y, tk, comfort: bool = False) -> np.ndarray:
        return self._occ_stack(self.stack, x, y, tk)

    def occupied_without(self, x, y, tk, exclude, comfort: bool = False) -> np.ndarray:
        ex = set(exclude) if isinstance(exclude, (set, frozenset, list, tuple)) else {exclude}
        ids = {int(e) for e in ex if isinstance(e, (int, np.integer))}
        return self._occ_stack(self._stack_of(lambda iid: iid not in ids), x, y, tk)

    def occupied_only(self, x, y, tk, iids) -> np.ndarray:
        ids = {int(i) for i in iids}
        return self._occ_stack(self._stack_of(lambda iid: iid in ids), x, y, tk)

    def _stack_of(self, keep) -> np.ndarray:
        st = np.zeros(self.stack.shape, bool)
        for si, ls in self.layers.items():
            for iid, m, ix0, iy0 in ls:
                if keep(iid):
                    self.cv.paste(st[si], m, ix0, iy0)
        for si, parts in self.raw.items():
            by_m: dict = {}
            for iid, c, ix0, iy0, m, _ in parts:
                if m is not None and keep(iid):
                    by_m.setdefault(round(float(m), 4), []).append((c, ix0, iy0))
            for m, ps in by_m.items():
                d, x0, y0 = dilate_group(ps, m, self.cv.cell)
                self.cv.paste(st[si], d, x0, y0)
        return st

    def area(self, si: int) -> float:
        return float(self.stack[si].sum()) * self.cv.cell ** 2

    def reaction(self, iid: int, to_states, j_hit: int, hero_x: float | None) -> "LayerSupport | None":
        """The counters of a hit (RangeSupport: from the estimate's templates); a plain layer support has none."""
        return None

    # ---- pending aims ----

    def aim_fail(self, cx: np.ndarray, cy: np.ndarray, locked: np.ndarray | None = None) -> np.ndarray:
        """[N] rows whose HeroBox centre (the box centre + HB_DY) is inside a pending aim's zone on a frame of its
        decision window (planner frames; the row's end when it comes later), extended through a lock held then."""
        N, T1 = cx.shape
        fail = np.zeros(N, bool)
        for p in getattr(self, "pend", ()):
            a = p["d_lo"] + self.k_shift
            b = p["d_hi"] + self.k_shift
            if a >= T1 - 1:
                a = b = T1 - 1
            b = min(b, T1 - 1)
            js = np.arange(a, b + 1)
            sel = np.zeros((N, T1), bool)
            sel[:, js] = True
            if locked is not None and b + 1 < T1:
                ext = np.cumprod(locked[:, b:min(T1, b + LOCK_EXT_F)], axis=1).astype(bool)
                sel[:, b + 1:b + ext.shape[1]] |= ext[:, :-1] if ext.shape[1] > 1 else False
            hx = cx
            hy = cy + HB_DY
            dxw = hx - p["x"]
            if p["aim"] == "facing":
                side = np.full(cx.shape, p["s"], np.int64)
            else:
                side = np.where(dxw >= 0, 1, -1)
            inz = np.zeros((N, T1), bool)
            for sd in (1, -1):
                z = p["zones"].get(sd)
                if z is None:
                    z = p["reader"].zone(p["x"], p["y"], sd, AIM_LAT)
                    p["zones"][sd] = z
                if not z.any():
                    continue
                gx, gy, D = p["reader"].gx, p["reader"].gy, p["D"]
                with np.errstate(invalid="ignore"):
                    ix = np.floor((dxw * sd - gx[0] + D / 2) / D)
                    iy = np.floor((hy - p["y"] - gy[0] + D / 2) / D)
                    ok = sel & (side == sd) & np.isfinite(ix) & np.isfinite(iy) & (ix >= 0) & (ix < len(gx)) \
                        & (iy >= 0) & (iy < len(gy))
                if ok.any():
                    inz[ok] = z[iy[ok].astype(np.int64), ix[ok].astype(np.int64)] > 0
            f_ = inz.any(axis=1)
            p["rows_failed"] = int(f_.sum())
            fail |= f_
        return fail


def tracker_k_shift(trk_frame: int | None, origin_frame: int | None) -> int:
    """The planner's frame j is the tracker's look-ahead j - shift (the tracker may be ahead of the observed frame)."""
    if trk_frame is None or origin_frame is None:
        return 0
    return max(int(trk_frame) - int(origin_frame), 0)


class RangeSupport(LayerSupport):
    """One tick's v2 support from a fed RangeTracker (module docstring): build() fills the samples; pending() the
    aims; reaction() the hit branch's counters."""

    @classmethod
    def build(cls, trk: RangeTracker, samples: tuple = SAMPLE_KS, k_shift: int = 0, inner_fc=None,
              margin_mode: str | None = None, canvas: Canvas | None = None) -> "RangeSupport":
        t0 = time.perf_counter()
        cv = canvas or Canvas()
        rs = cls(cv, samples, k_shift, inner_fc)
        rs.trk = trk
        rs.margin_mode = margin_mode
        n_est = 0
        for iid in sorted(trk.now):
            tk_name = trk.now[iid][0]
            tab = trk.tables[tk_name]
            for si, k in enumerate(rs.samples):
                e = trk.estimate(iid, k)
                if e is None:
                    continue
                if not e.raw.m.size or not e.raw.m.any():
                    continue
                n_est += 1
                m = margin(tk_name, k, margin_mode)
                c, ix0, iy0 = coarse(e.raw, tab.cell, cv.cell)
                esc = k + k_shift >= ESC_FROM_K
                # the escape check's danger: an idle body with ESC_IDLE_M only (idle enemies have no inescapable zone:
                # the margin's growth is the replanning's business), moves and hazards with their margin
                idle = e.fam is None
                rs.add_raw(si, iid, c, ix0, iy0, m, (ESC_IDLE_M if idle else m) if esc else None)
                if esc and idle and e.haz is not None and e.haz.m.size and e.haz.m.any():
                    ch, hx0, hy0 = coarse(e.haz, tab.cell, cv.cell)
                    rs.add_raw(si, iid, ch, hx0, hy0, None, m)
        rs.finish()
        rs.n_est = n_est
        rs.pend = pending_aims(trk)
        rs.ms = (time.perf_counter() - t0) * 1e3
        return rs

    # ---- the hit branch's counters ----

    def reaction(self, iid: int, to_states, j_hit: int, hero_x: float | None) -> "LayerSupport | None":
        """The counters a hit at planner frame j_hit starts (to_states: the TOOK DAMAGE exits,
        MultiForecaster.reaction_states): each one that starts an attack-range family is that family's template from
        the hit frame on, anchored at the enemy carried to the hit, both facings, with the margin; None: no family."""
        trk = getattr(self, "trk", None)
        if trk is None or iid not in trk.now:
            return None
        tk_name, e, _ = trk.now[iid]
        tab = trk.tables[tk_name]
        sp = tab.spec
        fams = []
        for st in to_states:
            fam = sp.start.get(st)
            if fam is None:
                fam = next((f for f, sts in sp.fam_states.items() if st in sts), None)
            if fam is not None and fam not in fams:
                fams.append(fam)
        if not fams:
            return None
        p = e.get("pos") or (0.0, 0.0)
        v = e.get("vel") or (0.0, 0.0)
        tau = max(j_hit - self.k_shift, 0) * FT
        ax = min(max(float(p[0]) + float(v[0]) * tau, tab.walls[0]), tab.walls[1])
        ay = float(p[1]) + float(v[1] or 0.0) * tau if len(v) > 1 else float(p[1])
        out = LayerSupport(self.cv, self.samples, self.k_shift, self.fc._inner)
        for si, k in enumerate(self.samples):
            b = k + self.k_shift - j_hit
            if b < 0:
                continue
            parts = []
            for fam in fams:
                for s in (1, -1):
                    du = 0.0 if hero_x is None else (hero_x - ax) * s
                    parts.append(tab.place(fam, None, b, (ax, ay), s, du))
            m, ix0, iy0 = dilate(union(parts), tab.cell, margin(tk_name, k, self.margin_mode), self.cv.cell)
            out.add(si, iid, m, ix0, iy0)
        return out

def pending_aims(trk: RangeTracker) -> list[dict]:
    """The enemies in a pending aimed antic with a packed zone table: {iid, name, reader, x, y, s, aim, d_lo, d_hi
    (tracker frames to the decision window), D, zones (side -> int8 zone, filled lazily)}."""
    try:
        from ssbot.tools import aim_zones as az
        rd = az.readers()
    except Exception:  # noqa: BLE001  (no tables: no pending check)
        return []
    out = []
    for iid, (tk, e, inst) in sorted(trk.now.items()):
        st, tin = _first_state(e)
        name = az.pending_move(tk, st)
        if st == "Jump Aim" and inst is not None and inst.fam in ("CC_JUMP", "CC_JUMP_CAST"):
            name = inst.fam
        if name is None or name not in rd or name not in DECISION_S:
            continue
        if inst is not None and inst.dec is not None:
            continue                       # decided: the estimate draws it
        age = (trk.T - inst.t0) if inst is not None else float(tin)
        lo, hi = DECISION_S[name]
        d_lo = max(int(math.ceil((lo - age) / FT - 1e-6)), 0)
        d_hi = max(int(math.ceil((hi - age) / FT - 1e-6)), d_lo)
        p = e.get("pos") or (0.0, 0.0)
        mv = az.MOVES[name]
        out.append({"iid": iid, "name": name, "reader": rd[name], "x": float(p[0]), "y": float(p[1]),
                    "s": trk.tables[tk].facing(e.get("flipX")), "aim": mv.aim, "d_lo": d_lo, "d_hi": d_hi,
                    "D": az.D, "zones": {}})
    return out


class V2Forecast:
    """The MultiForecast a ForumPlanner tick gets under v2: the safe-test reads (occupied, occupied_split,
    occupied_without, occupied_only, prob, fc.half) answer from the RangeSupport; everything else (targets, the
    forecaster for reactions / knockback / pins / waves, origin, horizon) from the wrapped forecast."""

    v2 = True

    def __init__(self, inner, rs: RangeSupport):
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "rs", rs)
        object.__setattr__(self, "fc", _Half(getattr(inner, "fc", None), BOUNDS_HALF))

    def __getattr__(self, name):
        return getattr(self.__dict__["_inner"], name)

    def __setattr__(self, name, value):
        setattr(self.__dict__["_inner"], name, value)

    def occupied(self, x, y, tk, comfort: bool = False) -> np.ndarray:
        return self.rs.occupied(x, y, tk)

    def occupied_split(self, x, y, tk):
        o = self.rs.occupied(x, y, tk)
        return o, o, np.zeros_like(o)

    def occupied_without(self, x, y, tk, exclude, comfort: bool = False) -> np.ndarray:
        return self.rs.occupied_without(x, y, tk, exclude)

    def occupied_only(self, x, y, tk, iids) -> np.ndarray:
        return self.rs.occupied_only(x, y, tk, iids)

    def occupied_redirect(self, *a, **k):
        return None

    def redirect_occ(self, *a, **k):
        return None

    def bell_redirected(self, x, y, tk, iid: int, t_hit: float, d: int):
        """A bell knocked back: the support without it (its redirected path does not hurt the hero)."""
        return self.rs.occupied_without(x, y, tk, iid)

    def prob(self, x, y, tk) -> np.ndarray:
        return self.rs.occupied(x, y, tk).mean(axis=-1)


class V2Feed:
    """The policy's side of v2: a RangeTracker fed every game frame (in order, each once) and the tick's support.
    every > 1 (SSBOT_FORUM_V2_EVERY): the support is rebuilt only every that many fed frames; a tick in between reads
    the last one shifted to its origin (the estimate as of up to every - 1 frames ago: a move starting or decided in
    between is seen that much later; its margins stay those of the build's look-ahead)."""

    def __init__(self, margin_mode: str | None = None, every: int | None = None):
        self.trk = RangeTracker()
        self.f_fed: int | None = None
        self.margin_mode = margin_mode
        self.every = max(int(EVERY if every is None else every), 1)
        self.ms: list = []
        self.last: RangeSupport | None = None
        self.last_f: int | None = None
        self.reused = 0

    def reset(self) -> None:
        self.trk.reset()
        self.f_fed = None
        self.ms = []
        self.last = None
        self.last_f = None
        self.reused = 0

    def feed(self, frames: dict, f: int) -> None:
        """Feeds the frames after the last fed one up to f from `frames` ({frame: STATE}); a gap restarts nothing (the
        tracker's game time advances by each STATE's dt)."""
        if self.f_fed is not None and f <= self.f_fed:
            return
        start = f if self.f_fed is None else self.f_fed + 1
        for g in range(start, f + 1):
            s = frames.get(g)
            if s is not None:
                self.trk.feed(s)
        self.f_fed = f

    def support(self, fcast, origin_frame: int | None) -> V2Forecast:
        if (self.every > 1 and self.last is not None and self.f_fed is not None and origin_frame is not None
                and 0 <= self.f_fed - self.last_f < self.every):
            rs = copy.copy(self.last)             # the stacks shared; its look-ahead k = j - (build frame - origin)
            rs.k_shift = int(self.last_f) - int(origin_frame)
            rs.ms = 0.0
            rs.fc = _Half(getattr(fcast, "fc", None), BOUNDS_HALF)
            self.reused += 1
        else:
            rs = RangeSupport.build(self.trk, k_shift=tracker_k_shift(self.f_fed, origin_frame),
                                    inner_fc=getattr(fcast, "fc", None), margin_mode=self.margin_mode)
            self.last, self.last_f = rs, self.f_fed
        self.ms.append(rs.ms)
        return V2Forecast(fcast, rs)


__all__ = ["V2_ON", "MARGIN_MODE", "margin", "box_kernel", "dilate", "Canvas", "LayerSupport", "RangeSupport",
           "V2Forecast", "V2Feed", "pending_aims", "SAMPLE_KS", "ESC_F", "carry_body", "body_polys", "empty_mask"]
