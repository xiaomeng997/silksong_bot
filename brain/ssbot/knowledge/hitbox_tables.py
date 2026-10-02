"""Space-time hitbox templates of enemy attacks (M2 W2; DESIGN §3.5.3 support, §3.5.8 "attack templates, reach
union: collider aggregation", §4.4 attacks.*.hitboxes / reach_union).

A template is the union, over every logged instance of one attack, of the enabled damage colliders the oracle exported
(enabled, with damage, eff != 0; ssbot.knowledge.behaviour_tables.support_threat), rasterised per time bin after a
reference event (the attack start, the entry of one of its states, or the attack's end for what outlives it):

    tpls, extra = load_templates("knowledge/1.0.30000/enemies/BellBeast_hitboxes.npz")
    sup = tpls["support/BB_CHARGE/anchor"]        # raw occupancy dilated by the validated residual and +-1 bin
    plan = planner_templates({k: v for k, v in tpls.items() if k.startswith("support/")})   # + hero hurtbox
    q = SupportQuery(plan)
    q.place("support/BB_BURST/world_all", t_ref=0.4)                       # 0.4 s after the attack start
    q.place("support/BB_CHARGE/anchor", t_ref=1.1, anchor=(75.03, 5.49), mirror=1)
    hit = q.query(cx, cy, tk)     # [N, T] bool: hero collider centres (cx, cy [N, T]) at tk [T] s from now

Frames: "anchor" templates are in the attacker's frame, x' = m * (x - ax), y' = y - ay, where (ax, ay) is the boss's
transform position when it first shows in the instance and m = -1 for an attack made facing left (the per-encounter
direction table of ssbot.knowledge.behaviour_tables), so every directed template faces +x; to_anchor / from_anchor
convert. "world" templates are in world coordinates: arena-fixed hazards (key <family>/world) and, for a support usable
before the anchor (or the side) is known, every collider of the family (key <family>/world_all). Self templates
(ent/<type_key>/self, anchor frame) follow one hazard entity from where it armed: anchor = its transform position on
its first armed frame, mirror 1, t from then. A falling or bouncing bell whose start varies between instances is
covered by its self template wherever it starts (held out by recording, behaviour_tables entities.<tk>.self_template),
while the union of the logged instances only covers the starts that were seen; before it arms, its arm position and
time support (entities.<tk>.arm_pos) swept over the self template (dilated by half the ranges) is the support.

Raster: CELL_U = 0.05 u cells on a lattice anchored at 0 (cell i covers [i, i + 1) * CELL_U), time bins of BIN_S =
1/60 s of game time (bin k holds the samples with round(t / BIN_S) == k; game time stands still in hit-stop, so a
frozen frame lands in the bin of the frame before it). rasterize() marks the cells whose centre a polygon contains plus
every cell its outline passes through (cv2.fillPoly + cv2.polylines at 1/16-cell vertex precision) and then grows that
by one cell (3 x 3): fill + outline alone missed cells that slanted edges only clip (random 3-8-vertex polygons:
interior points up to 0.029 u outside the marked cells, M2 round-1 review), the grown raster is a superset of the
polygon (tests/test_hitbox_tables.py samples interior and edge points of 300 random slanted polygons) and reaches at
most about 2 cells past it (0.1015 u measured: 2 cells plus the fixed-point vertex rounding). Circles arrive as the
oracle's circumscribed octagons, which already over-cover the circle.

Export lag: the exported geometry and the physics contact differ by up to one frame (trial run, 101 hits: 31 overlap
only the geometry of the hit frame, 4 only that of the frame before), so raw templates are queried with tol_bins >= 1
(enforced). Support templates (key prefix "support/", written by the behaviour builder) have the +-1 bin and the
validated contact residual (behaviour_tables, attacks.<A>.residual_u: each logged hero box at its own frame's time,
the pairing this query makes) baked in (t_pad, pad_x / pad_y in the meta);
planner templates are those dilated once more by the hero hurtbox half-extents plus a margin (HERO_HALF_U = 0.25 x
1.0394 u: STATE hero.box is 0.5 x 2.0789 u on all 2.87 M frames of the Bell Beast build, behaviour_tables
coverage.hero_box_u; the kinematics model's half_width and foot + head agree), so testing one point, the hero
collider centre, is a conservative box-overlap test.

Static templates (ambient hazards, armed when a scan started: key _ambient/world) hold one time-invariant bin, the
union over every frame the hazard was armed, and are in support at every time t.

Storage (.npz, no pickle): per template "<key>/bits" (nt, ny, ceil(nx / 8)) uint8 (np.packbits along x, cropped to
the occupied cells) and "<key>/meta" (META_FIELDS); other arrays (boss paths, instance tables) ride along under their
own keys. Accumulation keeps 64 x 64-cell tiles per time bin, so memory follows the occupied area, not the bounding
box of an attack that crosses the whole arena. The Bell Beast file (5.9 MB) holds the logged family templates (for the
viewer) and 71 support templates, 208 MB of packed bits once loaded (the 15 s Rage world templates are most of it).

Planner hot path (DESIGN §3.5.4: <= 512 candidates x 48 frames, p99 <= 3 ms per tick): SupportQuery packs every
template's bits into one buffer once and refuses templates not dilated by the hero hurtbox (a point test on bare
support is a centre-only test); per tick it takes placements (template, time offset, anchor, mirror) and runs one
numba kernel over the candidates time-major (parity with the NumPy reference _query_ref is tested). A placement costs
nothing at time steps outside its stored bins or on empty bins; otherwise every candidate pays a branch-free test
(about 0.09 ms per placement for 512 x 48 candidates inside the template's grid and none flagged), and a time step
whose candidates are mostly flagged already skips them. On the committed Bell Beast support (2026-10-01, i9-13900K,
tests/test_hitbox_tables.py): planner_templates of the 11 family templates takes 0.7 s (all 71: 1.6 s, 234 MB);
512 x 48 centres against 16 world_all placements in their active windows, 91 % flagged: p50 0.7 ms, p99 1.1 ms; 16
Rage placements with no candidate flagged: p50 1.4 ms, p99 1.9 ms. So the query alone fills the 3 ms tick at about 32
placements that are active at the queried times with every candidate in reach: W3 places only what is in support at
those times (one placement per attack instance in support, not one per possible anchor; the anchor support of a
variable-anchor attack is its world_all template).
"""
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numba
import numpy as np

CELL_U = 0.05
BIN_S = 1.0 / 60.0
TILE = 64
SHIFT = 4  # cv2 fixed-point fraction bits for vertex coordinates
FRAMES = ("anchor", "world")
META_FIELDS = ("ix0", "iy0", "nx", "ny", "nt", "cell", "bin_s", "t0", "n_instances", "frame", "t_pad", "pad_x",
               "pad_y", "static")
HERO_HALF_U = (0.25, 1.0394)   # STATE hero.box half-extents (0.5 x 2.0789 u on every logged frame)
SUPPORT = "support/"


# ---- frames ------------------------------------------------------------------------------------------------

def to_anchor(xy, anchor: Sequence[float], mirror: int) -> np.ndarray:
    """World (..., 2) -> anchor frame: x' = mirror * (x - ax), y' = y - ay."""
    xy = np.asarray(xy, dtype=np.float64)
    out = np.empty_like(xy)
    out[..., 0] = mirror * (xy[..., 0] - anchor[0])
    out[..., 1] = xy[..., 1] - anchor[1]
    return out


def from_anchor(xy, anchor: Sequence[float], mirror: int) -> np.ndarray:
    xy = np.asarray(xy, dtype=np.float64)
    out = np.empty_like(xy)
    out[..., 0] = anchor[0] + mirror * xy[..., 0]
    out[..., 1] = anchor[1] + xy[..., 1]
    return out


def box_to_anchor(box: Sequence[float], anchor: Sequence[float], mirror: int) -> tuple[float, float, float, float]:
    """An axis-aligned world box (x0, y0, x1, y1) in the anchor frame (still axis-aligned; x flips with the mirror)."""
    a = mirror * (box[0] - anchor[0])
    b = mirror * (box[2] - anchor[0])
    return min(a, b), box[1] - anchor[1], max(a, b), box[3] - anchor[1]


# ---- rasterisation -----------------------------------------------------------------------------------------

_GROW = np.ones((3, 3), np.uint8)


def rasterize(verts, cell: float = CELL_U) -> tuple[int, int, np.ndarray] | None:
    """Cells covering one polygon (k, 2) (k = 2: a segment, k = 1: a point), a superset: (ix0, iy0, patch),
    patch[iy - iy0, ix - ix0] True for covered cells. None for no points or non-finite ones."""
    v = np.asarray(verts, dtype=np.float64).reshape(-1, 2)
    if len(v) == 0 or not np.isfinite(v).all():
        return None
    p = v / cell - 0.5  # the centre of cell i lands on pixel coordinate i
    lo = np.floor(p.min(axis=0)).astype(np.int64) - 2
    hi = np.ceil(p.max(axis=0)).astype(np.int64) + 2
    patch = np.zeros((int(hi[1] - lo[1]) + 1, int(hi[0] - lo[0]) + 1), np.uint8)
    q = p - lo
    if len(v) == 1:
        patch[int(round(q[0, 1])), int(round(q[0, 0]))] = 1
    else:
        pts = np.round(q * (1 << SHIFT)).astype(np.int32).reshape(-1, 1, 2)
        if len(v) >= 3:
            cv2.fillPoly(patch, [pts], 1, lineType=cv2.LINE_8, shift=SHIFT)
        cv2.polylines(patch, [pts], len(v) >= 3, 1, lineType=cv2.LINE_8, shift=SHIFT)
    patch = cv2.dilate(patch, _GROW)
    return int(lo[0]), int(lo[1]), patch.astype(bool)


class TemplateAccumulator:
    """Union of rasterised polygons per time bin, kept as TILE x TILE cell tiles keyed (bin, tile_y, tile_x)."""

    def __init__(self, key: str, frame: str, cell: float = CELL_U, bin_s: float = BIN_S, static: bool = False):
        if frame not in FRAMES:
            raise ValueError(f"frame {frame!r} not in {FRAMES}")
        self.key, self.frame, self.cell, self.bin_s, self.static = key, frame, cell, bin_s, static
        self.tiles: dict[tuple[int, int, int], np.ndarray] = {}
        self.instances: set = set()
        self.polys = 0

    def bin_of(self, t: float) -> int:
        return int(round(t / self.bin_s))

    def add(self, t: float, verts, instance=None) -> None:
        r = rasterize(verts, self.cell)
        if r is not None:
            self.add_patch(self.bin_of(t), *r, instance=instance)

    def add_patch(self, b: int, ix0: int, iy0: int, patch: np.ndarray, instance=None) -> None:
        """OR a rasterised patch (from rasterize, possibly shared between templates) into bin b (bin 0 when static)."""
        if self.static:
            b = 0
        if instance is not None:
            self.instances.add(instance)
        self.polys += 1
        h, w = patch.shape
        for ty in range(iy0 // TILE, (iy0 + h - 1) // TILE + 1):
            y0, y1 = max(iy0, ty * TILE), min(iy0 + h, (ty + 1) * TILE)
            for tx in range(ix0 // TILE, (ix0 + w - 1) // TILE + 1):
                x0, x1 = max(ix0, tx * TILE), min(ix0 + w, (tx + 1) * TILE)
                sub = patch[y0 - iy0:y1 - iy0, x0 - ix0:x1 - ix0]
                if not sub.any():
                    continue
                tile = self.tiles.get((b, ty, tx))
                if tile is None:
                    tile = self.tiles[(b, ty, tx)] = np.zeros((TILE, TILE), bool)
                tile[y0 - ty * TILE:y1 - ty * TILE, x0 - tx * TILE:x1 - tx * TILE] |= sub

    def finish(self) -> "SpaceTimeTemplate | None":
        """The dense, cropped, bit-packed template (None when nothing was added)."""
        if not self.tiles:
            return None
        ix_lo = iy_lo = 1 << 62
        ix_hi = iy_hi = -(1 << 62)
        for (_, ty, tx), tile in self.tiles.items():
            rows = np.flatnonzero(tile.any(axis=1))
            cols = np.flatnonzero(tile.any(axis=0))
            iy_lo, iy_hi = min(iy_lo, ty * TILE + rows[0]), max(iy_hi, ty * TILE + rows[-1])
            ix_lo, ix_hi = min(ix_lo, tx * TILE + cols[0]), max(ix_hi, tx * TILE + cols[-1])
        bins = sorted({b for b, _, _ in self.tiles})
        b0 = bins[0]
        nt, ny, nx = bins[-1] - b0 + 1, int(iy_hi - iy_lo + 1), int(ix_hi - ix_lo + 1)
        bits = np.zeros((nt, ny, (nx + 7) // 8), np.uint8)
        by_bin: dict[int, list] = {}
        for (b, ty, tx), tile in self.tiles.items():
            by_bin.setdefault(b, []).append((ty, tx, tile))
        for b, tiles in by_bin.items():
            plane = np.zeros((ny, nx), bool)
            for ty, tx, tile in tiles:
                gy0, gx0 = ty * TILE - iy_lo, tx * TILE - ix_lo
                sy0, sx0 = max(0, -gy0), max(0, -gx0)
                sy1, sx1 = min(TILE, ny - gy0), min(TILE, nx - gx0)
                if sy1 > sy0 and sx1 > sx0:
                    plane[gy0 + sy0:gy0 + sy1, gx0 + sx0:gx0 + sx1] |= tile[sy0:sy1, sx0:sx1]
            bits[b - b0] = np.packbits(plane, axis=1)
        return SpaceTimeTemplate(key=self.key, frame=self.frame, ix0=int(ix_lo), iy0=int(iy_lo), nx=nx, ny=ny,
                                 t0=b0 * self.bin_s, bits=bits, cell=self.cell, bin_s=self.bin_s,
                                 n_instances=len(self.instances), static=self.static)


# ---- queries -----------------------------------------------------------------------------------------------

def _contains_loop(bits: np.ndarray, nx: int, ib: np.ndarray, iy: np.ndarray, ix: np.ndarray, tol: int,
                   out: np.ndarray) -> np.ndarray:
    """Per-point loop: out[i] = any occupied bit at (bin ib[i] +- tol, iy[i], ix[i])."""
    nt, ny = bits.shape[0], bits.shape[1]
    for i in range(ib.shape[0]):
        x, y = ix[i], iy[i]
        hit = False
        if 0 <= x < nx and 0 <= y < ny:
            for d in range(-tol, tol + 1):
                b = ib[i] + d
                if 0 <= b < nt and (bits[b, y, x >> 3] >> (7 - (x & 7))) & 1:
                    hit = True
                    break
        out[i] = hit
    return out


def _contains_np(bits: np.ndarray, nx: int, ib: np.ndarray, iy: np.ndarray, ix: np.ndarray, tol: int,
                 out: np.ndarray) -> np.ndarray:
    """NumPy reference of _contains_loop (parity test)."""
    nt, ny = bits.shape[0], bits.shape[1]
    out[:] = False
    inside = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
    byte = np.where(inside, ix >> 3, 0)
    shift = (7 - (ix & 7)).astype(np.uint8)
    for d in range(-tol, tol + 1):
        b = ib + d
        ok = inside & (b >= 0) & (b < nt)
        if ok.any():
            out[ok] |= ((bits[b[ok], iy[ok], byte[ok]] >> shift[ok]) & 1).astype(bool)
    return out


_contains = numba.njit(cache=True)(_contains_loop)


def mask_boxes(mask: np.ndarray) -> np.ndarray:
    """Exact cover of a (ny, nx) bool mask by axis-aligned rectangles, in cell units (n, 4) [ix0, iy0, ix1, iy1)
    (half-open): row runs, merged with the identical run of the row below."""
    out: list[list[int]] = []
    open_runs: dict[tuple[int, int], int] = {}  # (x0, x1) -> index in out
    m = np.asarray(mask, bool)
    for y in range(m.shape[0]):
        row = np.concatenate(([False], m[y], [False]))
        edges = np.flatnonzero(row[1:] != row[:-1])
        runs = list(zip(edges[::2].tolist(), edges[1::2].tolist()))
        nxt: dict[tuple[int, int], int] = {}
        for r in runs:
            i = open_runs.get(r)
            if i is None:
                out.append([r[0], y, r[1], y + 1])
                i = len(out) - 1
            else:
                out[i][3] = y + 1
            nxt[r] = i
        open_runs = nxt
    return np.array(out, np.int64).reshape(-1, 4)


def mask_polygons(mask: np.ndarray) -> list[np.ndarray]:
    """Outer contours (cell units, (k, 2) float) of a (ny, nx) bool mask, conservative: traced through the centres of
    the boundary cells of the mask dilated by one cell, so every covered cell lies inside its polygon with >= 0.5 cell
    to spare (holes are dropped, which only adds cover)."""
    m = np.asarray(mask, bool)
    if not m.any():
        return []
    padded = np.zeros((m.shape[0] + 4, m.shape[1] + 4), np.uint8)
    padded[2:-2, 2:-2] = m
    grown = cv2.dilate(padded, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(grown, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return [c.reshape(-1, 2).astype(np.float64) - 2.0 + 0.5 for c in contours]


def disk_kernel(r: float, cell: float = CELL_U) -> np.ndarray:
    """Cell offsets within r of a cell, conservatively: (di, dj) with distance(square 0, square (di, dj)) <= r, so a
    raster dilated by it contains every cell any point within r of the raster lies in. r <= 0: the single cell."""
    if r <= 0.0:
        return np.ones((1, 1), np.uint8)
    k = int(math.ceil(r / cell)) + 1
    d = np.arange(-k, k + 1)
    g = np.maximum(np.abs(d) - 1, 0) * cell
    return ((g[:, None] ** 2 + g[None, :] ** 2) <= r * r + 1e-12).astype(np.uint8)


def rect_cells(h: float, cell: float = CELL_U) -> int:
    """Cells k such that a box of half-extent h centred anywhere in cell j overlaps cell i only if |i - j| <= k."""
    return max(0, int(math.ceil(h / cell - 1e-9)))


@dataclass(slots=True)
class SpaceTimeTemplate:
    """Bit-packed occupancy (nt, ny, nx) of one attack (or state) in its frame. Cell (iy, ix) of bin b covers
    [(ix0 + ix) * cell, (ix0 + ix + 1) * cell) x [(iy0 + iy) * cell, ...) at t = t0 + b * bin_s. t_pad > 0: each bin
    already holds the union of its +-t_pad neighbours; pad_x / pad_y: spatial dilation already applied (u). static:
    one time-invariant bin, occupied at every t (ambient hazards: the union over every frame they were armed)."""
    key: str
    frame: str
    ix0: int
    iy0: int
    nx: int
    ny: int
    t0: float
    bits: np.ndarray
    cell: float = CELL_U
    bin_s: float = BIN_S
    n_instances: int = 0
    t_pad: int = 0
    pad_x: float = 0.0
    pad_y: float = 0.0
    static: bool = False
    _reach: np.ndarray | None = field(default=None, repr=False)

    @property
    def nt(self) -> int:
        return int(self.bits.shape[0])

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """(x0, y0, x1, y1) of the stored grid."""
        c = self.cell
        return self.ix0 * c, self.iy0 * c, (self.ix0 + self.nx) * c, (self.iy0 + self.ny) * c

    @property
    def t1(self) -> float:
        return self.t0 + (self.nt - 1) * self.bin_s

    def _tol(self, tol_bins: int) -> int:
        if tol_bins + self.t_pad < 1:
            raise ValueError(f"{self.key}: tol_bins={tol_bins} on a template without the +-1 bin of export lag "
                             f"(t_pad={self.t_pad}); use tol_bins >= 1")
        return int(tol_bins)

    def bin_of(self, t) -> np.ndarray:
        if self.static:
            return np.zeros(np.shape(t), np.int64)
        return np.rint((np.asarray(t, np.float64) - self.t0) / self.bin_s).astype(np.int64)

    def cells_of(self, x, y) -> tuple[np.ndarray, np.ndarray]:
        inv = 1.0 / self.cell   # the planner kernel's arithmetic (1 / 0.05 is exactly 20)
        ix = np.floor(np.asarray(x, np.float64) * inv).astype(np.int64) - self.ix0
        iy = np.floor(np.asarray(y, np.float64) * inv).astype(np.int64) - self.iy0
        return ix, iy

    def plane(self, b: int) -> np.ndarray:
        """Bin b as a (ny, nx) bool mask (empty outside the stored bins)."""
        if not 0 <= b < self.nt:
            return np.zeros((self.ny, self.nx), bool)
        return np.unpackbits(self.bits[b], axis=1, count=self.nx).astype(bool)

    def _occupancy(self, t0: float, t1: float, tol: int) -> np.ndarray:
        b0 = max(0, int(self.bin_of(t0)) - tol)
        b1 = min(self.nt - 1, int(self.bin_of(t1)) + tol)
        if b1 < b0:
            return np.zeros((self.ny, self.nx), bool)
        packed = np.bitwise_or.reduce(self.bits[b0:b1 + 1], axis=0)
        return np.unpackbits(packed, axis=1, count=self.nx).astype(bool)

    def occupancy(self, t0: float | None = None, t1: float | None = None, tol_bins: int = 1) -> np.ndarray:
        """Union over the bins of [t0, t1] (+- tol_bins); both None = the reach union."""
        if t0 is None and t1 is None:
            return self.reach()
        t0 = self.t0 if t0 is None else t0
        t1 = t0 if t1 is None else t1
        return self._occupancy(t0, t1, self._tol(tol_bins))

    def reach(self) -> np.ndarray:
        """reach_union: every cell occupied at any time (DESIGN §3.5.3 support)."""
        if self._reach is None:
            packed = np.bitwise_or.reduce(self.bits, axis=0)
            self._reach = np.unpackbits(packed, axis=1, count=self.nx).astype(bool)
        return self._reach

    def contains(self, t, x, y, tol_bins: int = 1) -> np.ndarray:
        """Occupied at (t, x, y)? Broadcasts t, x, y (template-frame coordinates). A point test is an overlap test
        of the hero hurtbox only on planner templates (planner_templates); on others it tests the point alone."""
        tol = self._tol(tol_bins)
        t, x, y = np.broadcast_arrays(np.asarray(t, np.float64), np.asarray(x, np.float64),
                                      np.asarray(y, np.float64))
        ib = self.bin_of(t).ravel()
        ix, iy = self.cells_of(x.ravel(), y.ravel())
        out = np.zeros(ib.shape[0], np.bool_)
        _contains(self.bits, self.nx, ib, iy, ix, tol, out)
        return out.reshape(t.shape)

    def contains_world(self, t, x, y, anchor: Sequence[float] | None = None, mirror: int = 1,
                       tol_bins: int = 1) -> np.ndarray:
        """contains() for world coordinates; an anchor template needs the instance's anchor and mirror."""
        if self.frame == "anchor":
            if anchor is None:
                raise ValueError(f"{self.key}: an anchor template needs the anchor")
            x = mirror * (np.asarray(x, np.float64) - anchor[0])
            y = np.asarray(y, np.float64) - anchor[1]
        return self.contains(t, x, y, tol_bins)

    def box_hit(self, t0: float, t1: float, box: Sequence[float], tol_bins: int = 1) -> bool:
        """Any occupied cell touching the box (x0, y0, x1, y1) at any bin of [t0, t1] (+- tol_bins)? Offline helper
        (~15 us per call); the planner uses SupportQuery on planner templates."""
        tol = self._tol(tol_bins)
        b0 = max(0, int(self.bin_of(min(t0, t1))) - tol)
        b1 = min(self.nt - 1, int(self.bin_of(max(t0, t1))) + tol)
        ix0, iy0 = self.cells_of(min(box[0], box[2]), min(box[1], box[3]))
        ix1, iy1 = self.cells_of(max(box[0], box[2]), max(box[1], box[3]))
        ix0, iy0 = max(0, int(ix0)), max(0, int(iy0))
        ix1, iy1 = min(self.nx - 1, int(ix1)), min(self.ny - 1, int(iy1))
        if b1 < b0 or ix1 < ix0 or iy1 < iy0:
            return False
        sub = np.bitwise_or.reduce(self.bits[b0:b1 + 1, iy0:iy1 + 1, ix0 >> 3:(ix1 >> 3) + 1], axis=0)
        cols = np.unpackbits(sub, axis=1)[:, (ix0 & 7):(ix0 & 7) + ix1 - ix0 + 1]
        return bool(cols.any())

    def box_distance(self, t: float, box: Sequence[float], tol_bins: int = 1, r_max: float = 1.0) -> float:
        """Distance (u) from the box (x0, y0, x1, y1) to the nearest occupied cell in the bins of t +- tol_bins
        (0 when they overlap or touch); inf when nothing is within r_max."""
        tol = self._tol(tol_bins)
        b = int(self.bin_of(t))
        b0, b1 = max(0, b - tol), min(self.nt - 1, b + tol)
        if b1 < b0:
            return math.inf
        c = self.cell
        x0, y0, x1, y1 = min(box[0], box[2]), min(box[1], box[3]), max(box[0], box[2]), max(box[1], box[3])
        jx0 = max(0, int(math.floor((x0 - r_max) / c)) - self.ix0)
        jx1 = min(self.nx - 1, int(math.floor((x1 + r_max) / c)) - self.ix0)
        jy0 = max(0, int(math.floor((y0 - r_max) / c)) - self.iy0)
        jy1 = min(self.ny - 1, int(math.floor((y1 + r_max) / c)) - self.iy0)
        if jx1 < jx0 or jy1 < jy0:
            return math.inf
        sub = np.bitwise_or.reduce(self.bits[b0:b1 + 1, jy0:jy1 + 1, jx0 >> 3:(jx1 >> 3) + 1], axis=0)
        occ = np.unpackbits(sub, axis=1)[:, (jx0 & 7):(jx0 & 7) + jx1 - jx0 + 1]
        iy, ix = np.nonzero(occ)
        if len(ix) == 0:
            return math.inf
        cx0 = (ix + jx0 + self.ix0) * c
        cy0 = (iy + jy0 + self.iy0) * c
        dx = np.maximum(np.maximum(cx0 - x1, x0 - (cx0 + c)), 0.0)
        dy = np.maximum(np.maximum(cy0 - y1, y0 - (cy0 + c)), 0.0)
        d = float(np.sqrt(dx * dx + dy * dy).min())
        return d if d <= r_max else math.inf

    def dilated(self, rx: float = 0.0, ry: float = 0.0, r_disk: float = 0.0, t_bins: int = 0,
                key: str | None = None) -> "SpaceTimeTemplate":
        """Minkowski dilation, conservative at the cell level: each bin grown by the disk of radius r_disk, then by
        the rectangle [-rx, rx] x [-ry, ry], then OR-ed with its t_bins neighbours on each side (the template gains
        t_bins bins at both ends). With rx, ry = the hero hurtbox half-extents, a point test of the hurtbox centre is
        an overlap test of the hurtbox against the original occupancy. A static template keeps its single bin (it
        already holds every t) and records t_bins in t_pad."""
        disk = disk_kernel(r_disk, self.cell)
        kx, ky = rect_cells(rx, self.cell), rect_cells(ry, self.cell)
        rect = np.ones((2 * ky + 1, 2 * kx + 1), np.uint8)
        gy, gx = disk.shape[0] // 2 + ky, disk.shape[1] // 2 + kx
        ny, nx = self.ny + 2 * gy, self.nx + 2 * gx
        tb = 0 if self.static else t_bins
        nt = self.nt + 2 * tb
        planes = np.zeros((self.nt, ny, (nx + 7) // 8), np.uint8)
        buf = np.zeros((ny, nx), np.uint8)
        for b in range(self.nt):
            p = self.plane(b)
            if not p.any():
                continue
            buf[:] = 0
            buf[gy:gy + self.ny, gx:gx + self.nx] = p
            g = buf
            if disk.size > 1:   # two passes = the Minkowski sum of both kernels; the rectangle one is separable
                g = cv2.dilate(g, disk, borderType=cv2.BORDER_CONSTANT, borderValue=0)
            if rect.size > 1:
                g = cv2.dilate(g, rect, borderType=cv2.BORDER_CONSTANT, borderValue=0)
            planes[b] = np.packbits(g > 0, axis=1)
        bits = np.zeros((nt, ny, (nx + 7) // 8), np.uint8)
        for d in range(2 * tb + 1):
            bits[d:d + self.nt] |= planes
        return SpaceTimeTemplate(key=key or self.key, frame=self.frame, ix0=self.ix0 - gx, iy0=self.iy0 - gy, nx=nx,
                                 ny=ny, t0=self.t0 - tb * self.bin_s, bits=bits, cell=self.cell,
                                 bin_s=self.bin_s, n_instances=self.n_instances, t_pad=self.t_pad + t_bins,
                                 pad_x=self.pad_x + r_disk + rx, pad_y=self.pad_y + r_disk + ry, static=self.static)

    def active(self) -> tuple[float, float] | None:
        """(first, last) time with any occupied cell ((-inf, inf) for a static template that has any)."""
        nz = np.flatnonzero(self.bits.reshape(self.nt, -1).any(axis=1))
        if len(nz) == 0:
            return None
        if self.static:
            return -math.inf, math.inf
        return self.t0 + nz[0] * self.bin_s, self.t0 + nz[-1] * self.bin_s

    def extent(self, mask: np.ndarray | None = None) -> tuple[float, float, float, float] | None:
        """(x0, y0, x1, y1) of the occupied cells of mask (default: the reach union)."""
        m = self.reach() if mask is None else mask
        rows, cols = np.flatnonzero(m.any(axis=1)), np.flatnonzero(m.any(axis=0))
        if len(rows) == 0:
            return None
        c = self.cell
        return ((self.ix0 + cols[0]) * c, (self.iy0 + rows[0]) * c, (self.ix0 + cols[-1] + 1) * c,
                (self.iy0 + rows[-1] + 1) * c)

    def boxes(self, t0: float | None = None, t1: float | None = None, tol_bins: int = 1) -> np.ndarray:
        """Rectangles (n, 4) [x0, y0, x1, y1] that cover exactly the occupied cells of [t0, t1] (default: reach)."""
        b = mask_boxes(self.occupancy(t0, t1, tol_bins)).astype(np.float64)
        b[:, [0, 2]] += self.ix0
        b[:, [1, 3]] += self.iy0
        return b * self.cell

    def polygons(self, t0: float | None = None, t1: float | None = None, tol_bins: int = 1) -> list[np.ndarray]:
        """Conservative outer polygons (template coordinates) of the occupancy of [t0, t1] (default: reach)."""
        return [(p + (self.ix0, self.iy0)) * self.cell for p in mask_polygons(self.occupancy(t0, t1, tol_bins))]

    def meta(self) -> np.ndarray:
        return np.array([self.ix0, self.iy0, self.nx, self.ny, self.nt, self.cell, self.bin_s, self.t0,
                         self.n_instances, FRAMES.index(self.frame), self.t_pad, self.pad_x, self.pad_y,
                         float(self.static)], np.float64)

    @classmethod
    def from_arrays(cls, key: str, bits: np.ndarray, meta: np.ndarray) -> "SpaceTimeTemplate":
        m = dict(zip(META_FIELDS, meta.tolist()))  # files from before t_pad / pad_* / static lack the last fields
        return cls(key=key, frame=FRAMES[int(m["frame"])], ix0=int(m["ix0"]), iy0=int(m["iy0"]), nx=int(m["nx"]),
                   ny=int(m["ny"]), t0=float(m["t0"]), bits=np.ascontiguousarray(bits, np.uint8),
                   cell=float(m["cell"]), bin_s=float(m["bin_s"]), n_instances=int(m["n_instances"]),
                   t_pad=int(m.get("t_pad", 0)), pad_x=float(m.get("pad_x", 0.0)), pad_y=float(m.get("pad_y", 0.0)),
                   static=bool(m.get("static", 0.0)))


def save_templates(path: str | Path, templates: dict[str, SpaceTimeTemplate],
                   extra: dict[str, np.ndarray] | None = None) -> Path:
    arrays: dict[str, np.ndarray] = {}
    for key, t in templates.items():
        arrays[f"{key}/bits"] = t.bits
        arrays[f"{key}/meta"] = t.meta()
    for k, v in (extra or {}).items():
        if k.endswith(("/bits", "/meta")):
            raise ValueError(f"extra key {k!r} collides with the template layout")
        arrays[k] = v
    path = Path(path)
    np.savez_compressed(path, **arrays)
    return path


def load_templates(path: str | Path, prefix: str | None = None) -> tuple[dict[str, SpaceTimeTemplate],
                                                                         dict[str, np.ndarray]]:
    """(templates by key, the other arrays by key); prefix: only the templates whose key starts with it."""
    templates, extra = {}, {}
    with np.load(Path(path), allow_pickle=False) as z:
        keys = set(z.files)
        for k in sorted(keys):
            if k.endswith("/bits") and k[:-5] + "/meta" in keys:
                base = k[:-5]
                if prefix is None or base.startswith(prefix):
                    templates[base] = SpaceTimeTemplate.from_arrays(base, z[k], z[base + "/meta"])
            elif not (k.endswith("/meta") and k[:-5] + "/bits" in keys):
                extra[k] = z[k]
    return templates, extra


def union(templates: Iterable[SpaceTimeTemplate], key: str) -> SpaceTimeTemplate | None:
    """One template holding the union of several of the same frame, bin size and cell (e.g. a family's states)."""
    ts = list(templates)
    if not ts:
        return None
    if len({(t.frame, t.cell, t.bin_s, t.t_pad, t.static) for t in ts}) != 1:
        raise ValueError("union of templates with different frame, cell, bin size, time padding or static flag")
    acc = TemplateAccumulator(key, ts[0].frame, ts[0].cell, ts[0].bin_s, static=ts[0].static)
    for t in ts:
        b_off = int(round(t.t0 / t.bin_s))
        for b in range(t.nt):
            plane = t.plane(b)
            if plane.any():
                acc.add_patch(b + b_off, t.ix0, t.iy0, plane)
    out = acc.finish()
    if out is not None:
        out.n_instances = max(t.n_instances for t in ts)
        out.t_pad = ts[0].t_pad
        out.pad_x, out.pad_y = min(t.pad_x for t in ts), min(t.pad_y for t in ts)
    return out


# ---- planner-facing batched query --------------------------------------------------------------------------

def planner_templates(support: dict[str, SpaceTimeTemplate], hx: float = HERO_HALF_U[0], hy: float = HERO_HALF_U[1],
                      margin: float = 0.0) -> dict[str, SpaceTimeTemplate]:
    """Support templates dilated by the hero hurtbox half-extents plus margin: a point test of the hero collider
    centre on the result is a conservative overlap test of the (margin-grown) hurtbox. Needs the +-1 bin baked in."""
    out = {}
    for k, t in support.items():
        if t.t_pad < 1:
            raise ValueError(f"{k}: not a support template (no +-1 bin of export lag baked in)")
        out[k] = t.dilated(rx=hx + margin, ry=hy + margin, key=k)
    return out


@numba.njit(cache=True)
def _query_kernel(bits: np.ndarray, boff: np.ndarray, imeta: np.ndarray, fmeta: np.ndarray, full: np.ndarray,
                  tk: np.ndarray, xt: np.ndarray, yt: np.ndarray, out: np.ndarray) -> None:
    """out[k, n] = any placement p occupied at (xt[k, n], yt[k, n]) and template time fmeta[p, 5] + tk[k] (time-major:
    the inner loop over candidates reads contiguous memory). imeta[p] = (ix0, iy0, nx, ny, nt, row bytes, mirror,
    anchored, static, offset of the template's bins in full); fmeta[p] = (t0, bin_s, cell, ax, ay, t_ref);
    full[offset + b] = 0 when bin b is empty (skipped). A time step with most candidates still clear takes a
    branch-free (vectorised) pass; one with most already flagged skips them one by one."""
    n_t, n_c = xt.shape
    cnt = np.zeros(n_t, np.int64)   # flagged candidates per time step
    for p in range(boff.shape[0]):
        ix0, iy0, nx, ny, nt, rb = imeta[p, 0], imeta[p, 1], imeta[p, 2], imeta[p, 3], imeta[p, 4], imeta[p, 5]
        mirror, anchored, static, fo = imeta[p, 6], imeta[p, 7], imeta[p, 8], imeta[p, 9]
        inv = 1.0 / fmeta[p, 2]
        ax, ay = fmeta[p, 3], fmeta[p, 4]
        if not anchored:
            mirror, ax, ay = 1, 0.0, 0.0
        for k in range(n_t):
            b = 0 if static else int(np.rint((fmeta[p, 5] + tk[k] - fmeta[p, 0]) / fmeta[p, 1]))
            if b < 0 or b >= nt or full[fo + b] == 0 or cnt[k] == n_c:
                continue
            base = boff[p] + b * ny * rb
            c = 0
            if 2 * cnt[k] > n_c:
                for n in range(n_c):
                    if out[k, n]:
                        c += 1
                        continue
                    fx = mirror * (xt[k, n] - ax) * inv - ix0
                    fy = (yt[k, n] - ay) * inv - iy0
                    if fx < 0.0 or fy < 0.0 or fx >= nx or fy >= ny:
                        continue
                    ix = int(fx)
                    if (bits[base + int(fy) * rb + (ix >> 3)] >> (7 - (ix & 7))) & 1:
                        out[k, n] = True
                        c += 1
            else:
                for n in range(n_c):
                    fx = mirror * (xt[k, n] - ax) * inv - ix0
                    fy = (yt[k, n] - ay) * inv - iy0
                    ok = (fx >= 0.0) & (fy >= 0.0) & (fx < nx) & (fy < ny)
                    ix = min(max(int(fx), 0), nx - 1)
                    iy = min(max(int(fy), 0), ny - 1)
                    v = (bits[base + iy * rb + (ix >> 3)] >> (7 - (ix & 7))) & 1
                    o = out[k, n] | (ok & (v != 0))
                    out[k, n] = o
                    c += o
            cnt[k] = c


def _query_ref(tpls: list["SpaceTimeTemplate"], place: list[tuple], tk: np.ndarray, x: np.ndarray,
               y: np.ndarray) -> np.ndarray:
    """NumPy reference of _query_kernel (parity test): place = [(template index, t_ref, anchor | None, mirror)]."""
    out = np.zeros(x.shape, bool)
    for i, t_ref, anchor, mirror in place:
        t = tpls[i]
        tt = np.broadcast_to(t_ref + np.asarray(tk, np.float64)[None, :], x.shape)
        if anchor is None:
            out |= t.contains(tt, x, y, tol_bins=0)
        else:
            out |= t.contains(tt, mirror * (x - anchor[0]), y - anchor[1], tol_bins=0)
    return out


class SupportQuery:
    """Batched point test of hero collider centres against placed planner templates (one numba kernel per tick).

    Templates are packed once; per tick: clear(), place(key, t_ref, anchor, mirror) for every attack in support
    (t_ref = template time at the query's t = 0: s since the attack start, the state's entry or the attack's end),
    then query(x, y, tk) with x, y [N, T] collider centres and tk [T] s from now."""

    def __init__(self, templates: dict[str, SpaceTimeTemplate], hero_half: tuple[float, float] = HERO_HALF_U):
        for k, t in templates.items():
            if t.t_pad < 1:
                raise ValueError(f"{k}: SupportQuery needs templates with the +-1 bin baked in (planner_templates)")
            if t.pad_x < hero_half[0] - 1e-9 or t.pad_y < hero_half[1] - 1e-9:
                raise ValueError(f"{k}: dilated by ({t.pad_x:.4f}, {t.pad_y:.4f}) u, less than the hero hurtbox "
                                 f"half-extents {tuple(hero_half)}: a point test would miss overlaps "
                                 f"(planner_templates)")
        self.keys = list(templates)
        self.index = {k: i for i, k in enumerate(self.keys)}
        self.tpls = [templates[k] for k in self.keys]
        offs, foffs, chunks, fulls, o, fo = [], [], [], [], 0, 0
        for t in self.tpls:
            offs.append(o)
            foffs.append(fo)
            chunks.append(np.ascontiguousarray(t.bits).ravel())
            fulls.append(t.bits.reshape(t.nt, -1).any(axis=1).astype(np.uint8))
            o += chunks[-1].size
            fo += t.nt
        self.bits = np.concatenate(chunks) if chunks else np.zeros(0, np.uint8)
        self.full = np.concatenate(fulls) if fulls else np.zeros(0, np.uint8)
        self.offs = np.array(offs, np.int64)
        self.foffs = np.array(foffs, np.int64)
        self.clear()

    def clear(self) -> None:
        self._place: list[tuple] = []

    def place(self, key: str, t_ref: float, anchor: Sequence[float] | None = None, mirror: int = 1) -> None:
        i = self.index[key]
        if (self.tpls[i].frame == "anchor") != (anchor is not None):
            raise ValueError(f"{key}: anchor templates need an anchor, world templates take none")
        self._place.append((i, float(t_ref), None if anchor is None else (float(anchor[0]), float(anchor[1])),
                            int(mirror)))

    def arrays(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        n = len(self._place)
        boff = np.zeros(n, np.int64)
        im = np.zeros((n, 10), np.int64)
        fm = np.zeros((n, 6), np.float64)
        for j, (i, t_ref, anchor, mirror) in enumerate(self._place):
            t = self.tpls[i]
            boff[j] = self.offs[i]
            im[j] = (t.ix0, t.iy0, t.nx, t.ny, t.nt, t.bits.shape[2], mirror, anchor is not None, t.static,
                     self.foffs[i])
            fm[j] = (t.t0, t.bin_s, t.cell, *(anchor or (0.0, 0.0)), t_ref)
        return boff, im, fm

    def query(self, x, y, tk) -> np.ndarray:
        """[N, T] bool: x, y [N, T] hero collider centres at tk [T] s from now (template time t_ref + tk)."""
        xt = np.ascontiguousarray(np.asarray(x, np.float64).T)
        yt = np.ascontiguousarray(np.asarray(y, np.float64).T)
        tk = np.ascontiguousarray(tk, np.float64)
        out = np.zeros(xt.shape, np.bool_)
        if self._place:
            boff, im, fm = self.arrays()
            _query_kernel(self.bits, boff, im, fm, self.full, tk, xt, yt, out)
        return np.ascontiguousarray(out.T)
