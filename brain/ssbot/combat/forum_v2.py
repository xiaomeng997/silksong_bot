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
from ssbot.combat import jump_behind as _jb
from ssbot.combat import rune_bombs as _rb
from ssbot.core.forum import FLOOR_Y, WALL_L, WALL_R

V2_ON = os.environ.get("SSBOT_FORUM_V2", "0").strip() == "1"
EVERY = int(os.environ.get("SSBOT_FORUM_V2_EVERY", "1") or 1)   # V2Feed: rebuild the support every this many frames
MARGIN_MODE = os.environ.get("SSBOT_FORUM_V2_MARGIN", "focus").strip().lower() or "focus"
# MARGIN_MODE "focus" (the default; the person, 2026-10-11): the focus unit gets a flat FOCUS_M unless the row dashes
# at it (then its "rule" margin), every other unit its "rule" margin. The focus unit is the L2 controller's target
# (GoalPrefs.target) when it is in play, else the only enemy in play, else none (RangeSupport.build's `focus`).
FOCUS_M = 0.5
# the dash exception (SSBOT_FORUM_V2_FOCUS_DASH): "1" (default) a row dashing at the focus unit reads it with its "rule"
# margin; "0" off (focus = flat FOCUS_M for every row); "audit" the dash copy is built (also under other margin modes,
# for the controller's focus) and the planner only records which rows it would make unsafe (last_info["dash_only"])
FOCUS_DASH = os.environ.get("SSBOT_FORUM_V2_FOCUS_DASH", "1").strip().lower() or "1"
# the escape check runs on a carried CONTINUE row too (1v1 live, forum.md 44: a row chosen with an escape kept running
# into a Slam Antic's reach unchecked until no row had one; SSBOT_FORUM_V2_ESC_CARRIED=0: the old skip)
ESC_CARRIED = os.environ.get("SSBOT_FORUM_V2_ESC_CARRIED", "1").strip() != "0"
# the escape that passed for the chosen row is appended to its plan, so the next tick's CONTINUE row runs into it
# instead of idling where the row ends (1v1 live: rows that approached a Slam Antic with an escape were all unsafe a
# few ticks later, none of them carrying that escape; SSBOT_FORUM_V2_ESC_TAIL=0: off)
ESC_TAIL = os.environ.get("SSBOT_FORUM_V2_ESC_TAIL", "1").strip() != "0"
# rows the escape check may look at past the first v2_esc_k when none of those had an escape (SSBOT_FORUM_V2_ESC_MORE;
# off: live 1v1 with 48, hitless kills 42 % vs 65 %, the retreats ran into the corners)
ESC_MORE = int(os.environ.get("SSBOT_FORUM_V2_ESC_MORE", "0") or 0)
# the Clapper's corner (1v1 live, forum.md 44: 16 of 26 slam hits): with its body this close to a wall (u) the strip
# between them is a trap - a slam it starts facing the wall reaches 12 u, so the antic leaves no way out but the wall
# top (y >= 11.8, never hit; forum.md 42). A safe row ending there ranks after every safe row ending elsewhere
# (SSBOT_FORUM_V2_CORNER=0: off)
CORNER_U = float(os.environ.get("SSBOT_FORUM_V2_CORNER", "13") or 0.0)
CORNER_TOP_Y = 11.15                  # the hero's Bounds centre at a wall-top cling (transform y 11.8)
CLAPPER = "Song Heavy Sentry"
# a slam the Clapper may start now (1v1 live, forum.md 44: most slam hits came from a hero that approached an idle /
# evading Clapper, locked in a dash or a swing when the antic began): for a Clapper outside CC_SLAM / CC_JUMP /
# CC_JUMP_CAST, a virtual CC_SLAM anchored now and facing the hero (its antic turns to the hero) is the escape
# check's danger too (samples from ESC_FROM_K on), so a chosen row leaves the hero a way out of a slam started on
# this tick; re-checked every tick (SSBOT_FORUM_V2_VSLAM=1; off by default)
VSLAM = os.environ.get("SSBOT_FORUM_V2_VSLAM", "0").strip() == "1"
# the person's general special rule (combat.special_mode, task 1v1 G1): build() keeps each enemy's hazard parts apart
# (haz_raw) so the special stacks drop a move's estimate but keep the enemy's hazards
SPECIAL_MODE = os.environ.get("SSBOT_FORUM_SPECIAL_MODE", "0").strip() == "1"
VSLAM_FAMS = (None, "CC_EVADE", "CC_CAST")
# SSBOT_FORUM_TWO_COMMIT (task 1v1 SP11-0, default off; two Clappers): under MARGIN_MODE "focus" a Clapper that is not
# the focus gets the "rule" margin (0.5 u to k 12, then 0.3 + 11 t^2: 2.1 u at k 24, 4.3 u at k 36) on everything it
# does - also on a committed move whose place is known: a jump past its Jump Aim (the landing from its take-off and her
# x at the aim, error p50 0.03-0.05 u), its landing (Slam 2 / Slam Recover), and its hazards (the jump cast's rune
# circle: centre landing + 6.48 u, r 7.19, lit 65-77 frames after the landing). (Not a slam: its antic turns to the
# hero, are_types.clapper.) SP10c's T2 (rnjb, 32 episodes): 47 of the 49 planner-owned HP losses came after a FORCED_RISK
# streak (no safe row) of 7-90 frames, 24 of them with the attacker not L2's target (its landing / circle grown by up to
# 4.3 u leaves no row out; at the target switch of 20261017_161806_2_i0_e0 f 4011325 the safe rows went 23 -> 0 in one
# tick). On: those parts get COMMIT_M (default FOCUS_M) like the focus unit; idle bodies, walks, evades, casts and slams
# keep the rule margin. SP11-0 A/B (9789b37, 64 per arm): with it (s11g) hitless clears 12 vs 8 / 64, both killed 48 vs
# 35, HP hits / min 3.11 vs 4.64; without it (s11gr, the script guards alone) 7 / 35 / 4.47 - since then it follows
# SSBOT_FORUM_V2 when unset (=0 off; arm rnsp11_0).
COMMIT = os.environ.get("SSBOT_FORUM_TWO_COMMIT", "1" if V2_ON else "0").strip() == "1"
COMMIT_M = float(os.environ.get("SSBOT_FORUM_TWO_COMMIT_M", "") or FOCUS_M)


def corner_zones(fc) -> list[tuple[float, float]]:
    """[(x0, x1)] the strips between a live Clapper's transform and a wall closer than CORNER_U (hero x)."""
    if CORNER_U <= 0:
        return []
    out = []
    for tr in (getattr(fc, "trackers", None) or {}).values():
        if tr.dead or tr.pos is None or getattr(getattr(tr, "table", None), "type_key", None) != CLAPPER:
            continue
        if _jb.ENABLED and getattr(getattr(tr, "cur", None), "family", None) in _jb.JUMP_FAMS:
            # SSBOT_FORUM_JUMP_BEHIND (task 1v1 SP3): a Clapper in a jump move has no corner - its back side is the
            # stance (it lands >= 4.5 u from the wall behind it)
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
# a constant x u; "zero" none; "focus" (the default) is "rule" here: the focus unit's FOCUS_M is RangeSupport's.
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
# SSBOT_FORUM_V2_AIM_COAST (task 1v1 T2, the Reed): the pending aim's anchor at its decision. "union" (default): the
# zone at the enemy's position now and at that position carried by its velocity decaying AIM_COAST a frame to the
# decision; "pred": the carried one only; "0": the position now (before T2)
AIM_COAST_MODE = os.environ.get("SSBOT_FORUM_V2_AIM_COAST", "union").strip().lower() or "union"
AIM_COAST = {"RE_STAB": 0.9}
# SSBOT_FORUM_V2_AIM_DIL (u, default 0: off): a margin on the pending aims' zones (the person: margins separate from the
# estimate): each anchor is also tried at 8 offsets on a circle of this radius (the zone's union over them: about its
# dilation by the radius). The Reed stab's anchor moves 1.9 / 3.4 u (p50 / p90) through its antic (T2 live).
AIM_DIL = float(os.environ.get("SSBOT_FORUM_V2_AIM_DIL", "0") or 0.0)
LOCK_EXT_F = 24                       # a hero lock at the decision extends the zone test by up to this many frames


def _interp(pts, k: float) -> float:
    ks = [p[0] for p in pts]
    ms = [p[1] for p in pts]
    return float(np.interp(k, ks, ms))


def margin(type_key: str, k: int, mode: str | None = None) -> float:
    """m(type, k) in u (module docstring)."""
    mode = MARGIN_MODE if mode is None else mode
    k = min(max(int(k), 0), K_HOLD)
    if mode == "focus":
        mode = "rule"
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
        self.haz_raw: dict = {}     # SPECIAL_MODE: {iid: [(si, coarse, ix0, iy0, m, esc_m)]} the hazard parts of raw
        self.pend: list = []        # pending aims (RangeSupport.build: pending_aims)
        self.stack_esc: np.ndarray | None = None    # the escape check's danger (add_esc), None: the stack
        self.stack_dash: np.ndarray | None = None   # the focus unit with its "rule" margin (rows dashing at it)
        self.focus: int | None = None               # the unit with FOCUS_M (MARGIN_MODE "focus")
        self.dash_focus: int | None = None          # the unit stack_dash holds (FOCUS_DASH)
        self.stack = np.zeros((len(self.samples), canvas.ny, canvas.nx), bool)
        # SSBOT_FORUM_RUNE_BOMB (task 1v1 G2): the small-rune bombs one by one (rune_bombs.frames: owner, x, y, r,
        # on_k, off_k in tracker look-ahead frames), checked on every frame with bomb_m; None: not in this support
        self.bombs: np.ndarray | None = None
        self.bomb_m = _rb.BOMB_M
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
        return self.occ_stack_b(self.stack if self.stack_esc is None else self.stack_esc, x, y, tk)

    def bomb_occ(self, x, y, tk, owners=None) -> np.ndarray | None:
        """The per-bomb small runes (SSBOT_FORUM_RUNE_BOMB) at planner times tk (every frame, not the samples), or
        None without them; owners: only those iids' bombs."""
        if self.bombs is None or not len(self.bombs):
            return None
        k = np.rint(np.asarray(tk, np.float64) / FT).astype(np.int64) - self.k_shift
        return _rb.occupied(self.bombs, x, y, k, self.bomb_m, owners)

    def occ_stack_b(self, stack: np.ndarray, x, y, tk, owners=None) -> np.ndarray:
        """_occ_stack with the per-bomb small runes (the same array when there are none)."""
        o = self._occ_stack(stack, x, y, tk)
        b = self.bomb_occ(x, y, tk, owners)
        return o if b is None else (o | b)

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
        return self.occ_stack_b(self.stack, x, y, tk)

    def occupied_dash(self, x, y, tk) -> np.ndarray | None:
        """The focus unit with its "rule" margin where that exceeds FOCUS_M (a row dashing at it); None: no such
        layer (no focus, or its rule margin is FOCUS_M on every sample)."""
        if self.stack_dash is None:
            return None
        return self._occ_stack(self.stack_dash, x, y, tk)

    def occupied_without(self, x, y, tk, exclude, comfort: bool = False) -> np.ndarray:
        ex = set(exclude) if isinstance(exclude, (set, frozenset, list, tuple)) else {exclude}
        ids = {int(e) for e in ex if isinstance(e, (int, np.integer))}
        own = None if self.bombs is None else {int(o) for o in self.bombs[:, 0] if int(o) not in ids}
        return self.occ_stack_b(self._stack_of(lambda iid: iid not in ids), x, y, tk, own)

    def occupied_only(self, x, y, tk, iids) -> np.ndarray:
        ids = {int(i) for i in iids}
        return self.occ_stack_b(self._stack_of(lambda iid: iid in ids), x, y, tk, ids)

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

    def special_stacks(self, iid: int, extra: list) -> tuple[np.ndarray, np.ndarray]:
        """The special mode's support (combat.special_mode, the person's general rule): every enemy but `iid` as
        built (its moves, bodies and hazards with their margins, the escape check's parts likewise), plus extra raw
        parts [(si, coarse, ix0, iy0, m, esc_m)] (iid's body in its move and its hazards). Returns (stack, the escape
        check's stack)."""
        st = np.zeros(self.stack.shape, bool)
        es = np.zeros(self.stack.shape, bool)
        for si, ls in self.layers.items():
            for i_, m_, x0, y0 in ls:
                if i_ != iid:
                    self.cv.paste(st[si], m_, x0, y0)
        for si, parts in self.raw.items():
            ps = [(c, x0, y0, m, em) for (i_, c, x0, y0, m, em) in parts if i_ != iid]
            ps += [(c, x0, y0, m, em) for (s_, c, x0, y0, m, em) in extra if s_ == si]
            for idx, dst in ((3, st), (4, es)):
                by_m: dict = {}
                for p in ps:
                    if p[idx] is not None:
                        by_m.setdefault(round(float(p[idx]), 4), []).append(p[:3])
                for m, g in by_m.items():
                    d, x0, y0 = dilate_group(g, m, self.cv.cell)
                    self.cv.paste(dst[si], d, x0, y0)
        if self.stack_esc is None:
            es = st.copy()
        return st, es

    def parts_stacks(self, parts: list) -> tuple[np.ndarray, np.ndarray]:
        """Raw parts [(si, coarse, ix0, iy0, m, esc_m)] alone as (stack, escape stack) (the special mode's E body)."""
        st = np.zeros(self.stack.shape, bool)
        es = np.zeros(self.stack.shape, bool)
        for idx, dst in ((4, st), (5, es)):
            by_m: dict = {}
            for p in parts:
                if p[idx] is not None:
                    by_m.setdefault((p[0], round(float(p[idx]), 4)), []).append(p[1:4])
            for (si, m), g in by_m.items():
                d, x0, y0 = dilate_group(g, m, self.cv.cell)
                self.cv.paste(dst[si], d, x0, y0)
        if self.stack_esc is None:
            es = st.copy()
        return st, es

    def reaction(self, iid: int, to_states, j_hit: int, hero_x: float | None) -> "LayerSupport | None":
        """The counters of a hit (RangeSupport: from the estimate's templates); a plain layer support has none."""
        return None

    # ---- pending aims ----

    def aim_fail(self, cx: np.ndarray, cy: np.ndarray, locked: np.ndarray | None = None, skip_iid: int | None = None
                 ) -> np.ndarray:
        """[N] rows whose HeroBox centre (the box centre + HB_DY) is inside a pending aim's zone on a frame of its
        decision window (planner frames; the row's end when it comes later), extended through a lock held then.
        skip_iid: that enemy's aims not checked (the special mode's rows)."""
        N, T1 = cx.shape
        fail = np.zeros(N, bool)
        for p in getattr(self, "pend", ()):
            if skip_iid is not None and p.get("iid") == skip_iid:
                continue
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
            inz = np.zeros((N, T1), bool)
            for ax, ay in p.get("anchors") or ((p["x"], p["y"]),):
                dxw = hx - ax
                if p["aim"] == "facing":
                    side = np.full(cx.shape, p["s"], np.int64)
                else:
                    side = np.where(dxw >= 0, 1, -1)
                for sd in (1, -1):
                    zk = (sd, round(ax, 2), round(ay, 2))
                    z = p["zones"].get(zk)
                    if z is None:
                        z = p["reader"].zone(ax, ay, sd, AIM_LAT)
                        p["zones"][zk] = z
                    if not z.any():
                        continue
                    gx, gy, D = p["reader"].gx, p["reader"].gy, p["D"]
                    with np.errstate(invalid="ignore"):
                        ix = np.floor((dxw * sd - gx[0] + D / 2) / D)
                        iy = np.floor((hy - ay - gy[0] + D / 2) / D)
                        ok = sel & (side == sd) & np.isfinite(ix) & np.isfinite(iy) & (ix >= 0) & (ix < len(gx))                             & (iy >= 0) & (iy < len(gy))
                    if ok.any():
                        inz[ok] |= z[iy[ok].astype(np.int64), ix[ok].astype(np.int64)] > 0
            f_ = inz.any(axis=1)
            p["rows_failed"] = int(f_.sum())
            fail |= f_
        return fail


def tracker_k_shift(trk_frame: int | None, origin_frame: int | None) -> int:
    """The planner's frame j is the tracker's look-ahead j - shift (the tracker may be ahead of the observed frame)."""
    if trk_frame is None or origin_frame is None:
        return 0
    return max(int(trk_frame) - int(origin_frame), 0)


def dash_at(mode: np.ndarray, vel: np.ndarray, centre: np.ndarray, fx: float) -> np.ndarray:
    """[N] rows of a rollout (mode [N, T], vel / centre [N, T, 2]) with a dash frame moving towards x = fx (the focus
    unit's position at the origin): the rows the focus margin reads with the unit's "rule" margin."""
    from ssbot.knowledge.kinematics import M_DASH
    d = mode == M_DASH
    if not d.any():
        return np.zeros(mode.shape[0], bool)
    toward = np.sign(vel[..., 0]) * np.sign(fx - centre[..., 0]) > 0
    return (d & toward).any(axis=1)


def jb_dash_free(rs) -> bool:
    """SSBOT_FORUM_JUMP_BEHIND (task 1v1 SP3): the focus unit is a Clapper in a jump's flight or landing (past its Jump
    Aim: the arc and the landing are known, error p50 0.03 u off the walls): a row dashing at it reads it with the focus
    margin like every other row, not the "rule" margin (the flier curve, 4.3 u at k 36, which keeps every dash out from
    under it; the person dashes under it 15-27 frames past its Jump Aim, the run alone does not clear it in time)."""
    if not _jb.ENABLED or rs is None or getattr(rs, "dash_focus", None) is None:
        return False
    x = (getattr(getattr(rs, "trk", None), "now", None) or {}).get(rs.dash_focus)
    inst = x[2] if x else None
    return (inst is not None and x[0] == _jb.CLAPPER and getattr(inst, "fam", None) in _jb.JUMP_FAMS
            and bool(getattr(inst, "states", None)) and inst.states[-1] in _jb.AIR_STATES + _jb.LANDED_STATES)


def committed(inst) -> bool:
    """SSBOT_FORUM_TWO_COMMIT: a Clapper's move instance whose place is known - a jump / jump cast past its Jump Aim or
    landed (jump_behind's AIR / LANDED states)."""
    if inst is None or not getattr(inst, "states", None):
        return False
    return inst.fam in _jb.JUMP_FAMS and inst.states[-1] in _jb.AIR_STATES + _jb.LANDED_STATES


def focus_iid(trk: RangeTracker, target: int | None) -> int | None:
    """The focus unit (MARGIN_MODE "focus"): the controller's target (GoalPrefs.target) when the tracker has it, else
    the only enemy in play, else None (every unit then gets its "rule" margin)."""
    now = getattr(trk, "now", None) or {}
    if target is not None and int(target) in now:
        return int(target)
    if len(now) == 1:
        return int(next(iter(now)))
    return None


class RangeSupport(LayerSupport):
    """One tick's v2 support from a fed RangeTracker (module docstring): build() fills the samples; pending() the
    aims; reaction() the hit branch's counters."""

    @classmethod
    def build(cls, trk: RangeTracker, samples: tuple = SAMPLE_KS, k_shift: int = 0, inner_fc=None,
              margin_mode: str | None = None, canvas: Canvas | None = None, focus: int | None = None) -> "RangeSupport":
        """focus: the controller's target iid under MARGIN_MODE "focus" (focus_iid: else the only enemy in play); the
        focus unit's layers get FOCUS_M and a copy with its "rule" margin goes into stack_dash (occupied_dash: the
        rows that dash at it)."""
        t0 = time.perf_counter()
        cv = canvas or Canvas()
        rs = cls(cv, samples, k_shift, inner_fc)
        rs.trk = trk
        rs.margin_mode = margin_mode
        mode_ = margin_mode or MARGIN_MODE
        rs.focus = focus_iid(trk, focus) if mode_ == "focus" else None
        rs.dash_focus = focus_iid(trk, focus) if (FOCUS_DASH == "audit" or (mode_ == "focus" and FOCUS_DASH == "1"))             else None
        rs.n_vslam = 0
        n_est = 0
        dash_parts: dict = {}
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
                m = rs.m_of(iid, tk_name, k)
                c, ix0, iy0 = coarse(e.raw, tab.cell, cv.cell)
                if iid == rs.dash_focus:
                    md = round(margin(tk_name, k, "rule"), 4)
                    if md > m + 1e-6:
                        dash_parts.setdefault((si, md), []).append((c, ix0, iy0))
                        if e.haz is not None and e.haz.m.size and e.haz.m.any():
                            dash_parts[(si, md)].append(coarse(e.haz, tab.cell, cv.cell))
                esc = k + k_shift >= ESC_FROM_K
                # the escape check's danger: an idle body with ESC_IDLE_M only (idle enemies have no inescapable zone:
                # the margin's growth is the replanning's business), moves and hazards with their margin
                idle = e.fam is None
                if COMMIT and tk_name == CLAPPER and iid != rs.focus and m > COMMIT_M:
                    # SSBOT_FORUM_TWO_COMMIT: a committed move (whole estimate) / its hazards with COMMIT_M
                    if committed(trk.now[iid][2]):
                        rs.add_raw(si, iid, c, ix0, iy0, COMMIT_M, COMMIT_M if esc else None)
                        rs.n_commit = getattr(rs, "n_commit", 0) + 1
                        continue
                    if e.haz is not None and e.haz.m.size and e.haz.m.any() and e.core is not None:
                        cc, cx0, cy0 = coarse(e.core, tab.cell, cv.cell)
                        rs.add_raw(si, iid, cc, cx0, cy0, m, (ESC_IDLE_M if idle else m) if esc else None)
                        ch, hx0, hy0 = coarse(e.haz, tab.cell, cv.cell)
                        rs.add_raw(si, iid, ch, hx0, hy0, COMMIT_M, COMMIT_M if esc else None)
                        rs.n_commit = getattr(rs, "n_commit", 0) + 1
                        continue
                rs.add_raw(si, iid, c, ix0, iy0, m, (ESC_IDLE_M if idle else m) if esc else None)
                if SPECIAL_MODE and e.haz is not None and e.haz.m.size and e.haz.m.any():
                    ch_, hx_, hy_ = coarse(e.haz, tab.cell, cv.cell)
                    rs.haz_raw.setdefault(iid, []).append((si, ch_, hx_, hy_, m, m if esc else None))
                if esc and idle and e.haz is not None and e.haz.m.size and e.haz.m.any():
                    ch, hx0, hy0 = coarse(e.haz, tab.cell, cv.cell)
                    rs.add_raw(si, iid, ch, hx0, hy0, None, m)
        if VSLAM and trk.hero is not None:
            for iid in sorted(trk.now):
                tk_name, e, inst = trk.now[iid]
                if tk_name != CLAPPER or (inst is not None and inst.fam not in VSLAM_FAMS):
                    continue
                p = e.get("pos") or None
                if not p:
                    continue
                x, y = float(p[0]), float(p[1])
                sd = 1 if float(trk.hero[0]) >= x else -1
                tab = trk.tables[tk_name]
                for si, k in enumerate(rs.samples):
                    if k + k_shift < ESC_FROM_K:
                        continue
                    vm = tab.place("CC_SLAM", "main", k + k_shift, (x, y), sd, (float(trk.hero[0]) - x) * sd)
                    if vm.m.size and vm.m.any():
                        c, ix0, iy0 = coarse(vm, tab.cell, cv.cell)
                        rs.add_raw(si, iid, c, ix0, iy0, None, rs.m_of(iid, tk_name, k))
                        rs.n_vslam += 1
        rs.finish()
        if dash_parts:
            rs.stack_dash = np.zeros(rs.stack.shape, bool)
            for (si, md), ps in dash_parts.items():
                d, x0, y0 = dilate_group(ps, md, cv.cell)
                cv.paste(rs.stack_dash[si], d, x0, y0)
        rs.n_est = n_est
        rune = getattr(trk, "rune", None)
        if rune is not None and (_rb.BOMB or _rb.HOP):
            bk = _rb.frames(rune.predict(trk.T), trk.T)
            rs.bombs_all = bk[(bk[:, 5] >= -1) & (bk[:, 4] <= 130)]    # (the hop rows' timing: SSBOT_FORUM_RUNE_HOP)
            if _rb.BOMB:
                rs.bombs = rs.bombs_all
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
            m, ix0, iy0 = dilate(union(parts), tab.cell, self.m_of(iid, tk_name, k), self.cv.cell)
            out.add(si, iid, m, ix0, iy0)
        return out

    def m_of(self, iid: int, type_key: str, k: int) -> float:
        """The margin of enemy iid at look-ahead k: FOCUS_M for the focus unit (MARGIN_MODE "focus"), else margin()."""
        if iid is not None and iid == getattr(self, "focus", None):
            return FOCUS_M
        return margin(type_key, k, self.margin_mode)

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
        x, y = float(p[0]), float(p[1])
        anchors = ((x, y),)
        if name in AIM_COAST and AIM_COAST_MODE != "0":
            # the enemy keeps moving through its antic: its velocity now decays by AIM_COAST[name] a frame (the Reed's
            # Stab Antic: DecelerateV2 0.95 + DistanceFly; fitted 0.9 on the live T2 antics: the anchor error at the
            # Stab 1 entry p50 / p90 1.4 / 2.8 u against 2.3 / 3.7 u standing still)
            v = e.get("vel") or (0.0, 0.0)
            dec = AIM_COAST[name]
            n = max(d_lo, 0)
            c = (1.0 - dec ** n) / (1.0 - dec) * FT
            pred = (x + float(v[0]) * c, y + float(v[1] or 0.0) * c if len(v) > 1 else y)
            anchors = (pred,) if AIM_COAST_MODE == "pred" else ((x, y), pred)
        if AIM_DIL > 0.0:
            r = AIM_DIL
            ring = [(r * math.cos(k * math.pi / 4), r * math.sin(k * math.pi / 4)) for k in range(8)]
            anchors = tuple(anchors) + tuple((ax + dx, ay + dy) for ax, ay in anchors for dx, dy in ring)
        out.append({"iid": iid, "name": name, "reader": rd[name], "x": x, "y": y, "anchors": anchors,
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

    def support(self, fcast, origin_frame: int | None, focus: int | None = None) -> V2Forecast:
        """focus: the controller's target iid (RangeSupport.build); a changed one rebuilds."""
        if (self.every > 1 and self.last is not None and self.f_fed is not None and origin_frame is not None
                and 0 <= self.f_fed - self.last_f < self.every and getattr(self.last, "focus_arg", None) == focus):
            rs = copy.copy(self.last)             # the stacks shared; its look-ahead k = j - (build frame - origin)
            rs.k_shift = int(self.last_f) - int(origin_frame)
            rs.ms = 0.0
            rs.fc = _Half(getattr(fcast, "fc", None), BOUNDS_HALF)
            self.reused += 1
        else:
            rs = RangeSupport.build(self.trk, k_shift=tracker_k_shift(self.f_fed, origin_frame),
                                    inner_fc=getattr(fcast, "fc", None), margin_mode=self.margin_mode, focus=focus)
            rs.focus_arg = focus
            self.last, self.last_f = rs, self.f_fed
        self.ms.append(rs.ms)
        return V2Forecast(fcast, rs)


__all__ = ["V2_ON", "MARGIN_MODE", "FOCUS_M", "focus_iid", "dash_at", "margin", "box_kernel", "dilate", "Canvas", "LayerSupport", "RangeSupport",
           "V2Forecast", "V2Feed", "pending_aims", "SAMPLE_KS", "ESC_F", "carry_body", "body_polys", "empty_mask"]
