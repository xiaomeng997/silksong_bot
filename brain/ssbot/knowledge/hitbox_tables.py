"""Space-time hitbox templates of enemy attacks (M2 W2; DESIGN §3.5.3 support, §3.5.8 "attack templates, reach
union: collider aggregation", §4.4 attacks.*.hitboxes / reach_union).

A template is the union, over every logged instance of one attack, of the enabled damage colliders the oracle exported
("ents" colliders with damage, ssbot.ipc.ents.is_threat), rasterised per time bin after a reference event (the attack
start, the entry of one of its states, or the attack's end for what outlives it):

    tpls, extra = load_templates("knowledge/1.0.30000/enemies/BellBeast_hitboxes.npz")
    tpl = tpls["BB_CHARGE/anchor"]
    tpl.contains(t, x, y)                    # vectorised point test, t = s of game time after the attack start
    tpl.box_hit(t0, t1, (x0, y0, x1, y1))    # any occupied cell in the box during [t0, t1]
    tpl.boxes(), tpl.polygons()              # conservative covers of the reach union (or of a time window)

Frames: "anchor" templates are in the attacker's frame, x' = m * (x - ax), y' = y - ay, where (ax, ay) is the boss's
position when it first shows in the instance and m = -1 for an attack made facing left (the per-encounter direction
table of ssbot.knowledge.behaviour_tables), so every directed template faces +x; to_anchor / from_anchor convert.
"world" templates hold arena-fixed hazards (Bell Beast's ceiling bells) in world coordinates.

Raster: CELL_U = 0.05 u cells on a lattice anchored at 0 (cell i covers [i, i + 1) * CELL_U), time bins of BIN_S =
1/60 s of game time (bin k holds the samples with round(t / BIN_S) == k; game time stands still in hit-stop, so a
frozen frame lands in the bin of the frame before it, and frame-time jitter can leave a bin empty between two full
ones: queries take tol_bins = 1 neighbours by default). A polygon marks the cells whose centre it contains plus every
cell its outline passes through (cv2.fillPoly + cv2.polylines at 1/16-cell vertex precision), so the raster is within
one cell (0.05 u) of the exact union; the predictor inflates by >= 0.15 u anyway (DESIGN §3.5.3 m). Circles arrive as
the oracle's circumscribed octagons (vertices at r / cos 22.5 deg), which already over-cover the circle.

Storage (.npz, no pickle): per template "<key>/bits" (nt, ny, ceil(nx / 8)) uint8 (np.packbits along x, cropped to
the occupied cells) and "<key>/meta" (META_FIELDS); other arrays (boss paths, instance tables) ride along under their
own keys. Accumulation keeps 64 x 64-cell tiles per time bin, so memory follows the occupied area, not the bounding
box of an attack that crosses the whole arena.

Point queries are the planner's hot path (DESIGN §3.5.4: <= 512 rollouts x 48 steps): _contains_loop is written for
numba and compiled when numba is importable; otherwise (numba is not installed yet) the vectorised NumPy version runs.
"""
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

try:
    import numba
except ImportError:  # the NumPy fallback below is what runs (and what the tests exercise) until numba is installed
    numba = None

CELL_U = 0.05
BIN_S = 1.0 / 60.0
TILE = 64
SHIFT = 4  # cv2 fixed-point fraction bits for vertex coordinates
FRAMES = ("anchor", "world")
META_FIELDS = ("ix0", "iy0", "nx", "ny", "nt", "cell", "bin_s", "t0", "n_instances", "frame")


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


# ---- rasterisation -----------------------------------------------------------------------------------------

def rasterize(verts, cell: float = CELL_U) -> tuple[int, int, np.ndarray] | None:
    """Cells covered by one polygon (k, 2) (k = 2: a segment, k = 1: a point): (ix0, iy0, patch), patch[iy - iy0,
    ix - ix0] True for covered cells. None for no points or non-finite ones."""
    v = np.asarray(verts, dtype=np.float64).reshape(-1, 2)
    if len(v) == 0 or not np.isfinite(v).all():
        return None
    p = v / cell - 0.5  # the centre of cell i lands on pixel coordinate i
    lo = np.floor(p.min(axis=0)).astype(np.int64) - 1
    hi = np.ceil(p.max(axis=0)).astype(np.int64) + 1
    patch = np.zeros((int(hi[1] - lo[1]) + 1, int(hi[0] - lo[0]) + 1), np.uint8)
    q = p - lo
    if len(v) == 1:
        patch[int(round(q[0, 1])), int(round(q[0, 0]))] = 1
    else:
        pts = np.round(q * (1 << SHIFT)).astype(np.int32).reshape(-1, 1, 2)
        if len(v) >= 3:
            cv2.fillPoly(patch, [pts], 1, lineType=cv2.LINE_8, shift=SHIFT)
        cv2.polylines(patch, [pts], len(v) >= 3, 1, lineType=cv2.LINE_8, shift=SHIFT)
    return int(lo[0]), int(lo[1]), patch.astype(bool)


class TemplateAccumulator:
    """Union of rasterised polygons per time bin, kept as TILE x TILE cell tiles keyed (bin, tile_y, tile_x)."""

    def __init__(self, key: str, frame: str, cell: float = CELL_U, bin_s: float = BIN_S):
        if frame not in FRAMES:
            raise ValueError(f"frame {frame!r} not in {FRAMES}")
        self.key, self.frame, self.cell, self.bin_s = key, frame, cell, bin_s
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
        """OR a rasterised patch (from rasterize, possibly shared between templates) into bin b."""
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
                                 n_instances=len(self.instances))


# ---- queries -----------------------------------------------------------------------------------------------

def _contains_loop(bits: np.ndarray, nx: int, ib: np.ndarray, iy: np.ndarray, ix: np.ndarray, tol: int,
                   out: np.ndarray) -> np.ndarray:
    """Per-point loop (numba-compatible): out[i] = any occupied bit at (bin ib[i] +- tol, iy[i], ix[i])."""
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


_contains = numba.njit(cache=True)(_contains_loop) if numba is not None else _contains_np


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


@dataclass(slots=True)
class SpaceTimeTemplate:
    """Bit-packed occupancy (nt, ny, nx) of one attack (or state) in its frame. Cell (iy, ix) of bin b covers
    [(ix0 + ix) * cell, (ix0 + ix + 1) * cell) x [(iy0 + iy) * cell, ...) at t = t0 + b * bin_s."""
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

    def bin_of(self, t) -> np.ndarray:
        return np.rint((np.asarray(t, np.float64) - self.t0) / self.bin_s).astype(np.int64)

    def cells_of(self, x, y) -> tuple[np.ndarray, np.ndarray]:
        ix = np.floor(np.asarray(x, np.float64) / self.cell).astype(np.int64) - self.ix0
        iy = np.floor(np.asarray(y, np.float64) / self.cell).astype(np.int64) - self.iy0
        return ix, iy

    def plane(self, b: int) -> np.ndarray:
        """Bin b as a (ny, nx) bool mask (empty outside the stored bins)."""
        if not 0 <= b < self.nt:
            return np.zeros((self.ny, self.nx), bool)
        return np.unpackbits(self.bits[b], axis=1, count=self.nx).astype(bool)

    def occupancy(self, t0: float | None = None, t1: float | None = None, tol_bins: int = 1) -> np.ndarray:
        """Union over the bins of [t0, t1] (+- tol_bins); both None = the reach union."""
        if t0 is None and t1 is None:
            return self.reach()
        t0 = self.t0 if t0 is None else t0
        t1 = t0 if t1 is None else t1
        b0 = max(0, int(self.bin_of(t0)) - tol_bins)
        b1 = min(self.nt - 1, int(self.bin_of(t1)) + tol_bins)
        if b1 < b0:
            return np.zeros((self.ny, self.nx), bool)
        packed = np.bitwise_or.reduce(self.bits[b0:b1 + 1], axis=0)
        return np.unpackbits(packed, axis=1, count=self.nx).astype(bool)

    def reach(self) -> np.ndarray:
        """reach_union: every cell occupied at any time (DESIGN §3.5.3 support)."""
        if self._reach is None:
            packed = np.bitwise_or.reduce(self.bits, axis=0)
            self._reach = np.unpackbits(packed, axis=1, count=self.nx).astype(bool)
        return self._reach

    def contains(self, t, x, y, tol_bins: int = 1) -> np.ndarray:
        """Occupied at (t, x, y)? Broadcasts t, x, y (template-frame coordinates)."""
        t, x, y = np.broadcast_arrays(np.asarray(t, np.float64), np.asarray(x, np.float64),
                                      np.asarray(y, np.float64))
        ib = self.bin_of(t).ravel()
        ix, iy = self.cells_of(x.ravel(), y.ravel())
        out = np.zeros(ib.shape[0], np.bool_)
        _contains(self.bits, self.nx, ib, iy, ix, int(tol_bins), out)
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
        """Any occupied cell touching the box (x0, y0, x1, y1) at any bin of [t0, t1] (+- tol_bins)?"""
        b0 = max(0, int(self.bin_of(min(t0, t1))) - tol_bins)
        b1 = min(self.nt - 1, int(self.bin_of(max(t0, t1))) + tol_bins)
        ix0, iy0 = self.cells_of(min(box[0], box[2]), min(box[1], box[3]))
        ix1, iy1 = self.cells_of(max(box[0], box[2]), max(box[1], box[3]))
        ix0, iy0 = max(0, int(ix0)), max(0, int(iy0))
        ix1, iy1 = min(self.nx - 1, int(ix1)), min(self.ny - 1, int(iy1))
        if b1 < b0 or ix1 < ix0 or iy1 < iy0:
            return False
        sub = np.bitwise_or.reduce(self.bits[b0:b1 + 1, iy0:iy1 + 1, ix0 >> 3:(ix1 >> 3) + 1], axis=0)
        cols = np.unpackbits(sub, axis=1)[:, (ix0 & 7):(ix0 & 7) + ix1 - ix0 + 1]
        return bool(cols.any())

    def active(self) -> tuple[float, float] | None:
        """(first, last) time with any occupied cell."""
        nz = np.flatnonzero(self.bits.reshape(self.nt, -1).any(axis=1))
        if len(nz) == 0:
            return None
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
                         self.n_instances, FRAMES.index(self.frame)], np.float64)

    @classmethod
    def from_arrays(cls, key: str, bits: np.ndarray, meta: np.ndarray) -> "SpaceTimeTemplate":
        m = dict(zip(META_FIELDS, meta.tolist()))
        return cls(key=key, frame=FRAMES[int(m["frame"])], ix0=int(m["ix0"]), iy0=int(m["iy0"]), nx=int(m["nx"]),
                   ny=int(m["ny"]), t0=float(m["t0"]), bits=np.ascontiguousarray(bits, np.uint8),
                   cell=float(m["cell"]), bin_s=float(m["bin_s"]), n_instances=int(m["n_instances"]))


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


def load_templates(path: str | Path) -> tuple[dict[str, SpaceTimeTemplate], dict[str, np.ndarray]]:
    """(templates by key, the other arrays by key)."""
    templates, extra = {}, {}
    with np.load(Path(path), allow_pickle=False) as z:
        keys = set(z.files)
        for k in sorted(keys):
            if k.endswith("/bits") and k[:-5] + "/meta" in keys:
                base = k[:-5]
                templates[base] = SpaceTimeTemplate.from_arrays(base, z[k], z[base + "/meta"])
            elif not (k.endswith("/meta") and k[:-5] + "/bits" in keys):
                extra[k] = z[k]
    return templates, extra


def union(templates: Iterable[SpaceTimeTemplate], key: str) -> SpaceTimeTemplate | None:
    """One template holding the union of several of the same frame, bin size and cell (e.g. a family's states)."""
    ts = list(templates)
    if not ts:
        return None
    if len({(t.frame, t.cell, t.bin_s) for t in ts}) != 1:
        raise ValueError("union of templates with different frame, cell or bin size")
    acc = TemplateAccumulator(key, ts[0].frame, ts[0].cell, ts[0].bin_s)
    for t in ts:
        b_off = int(round(t.t0 / t.bin_s))
        for b in range(t.nt):
            plane = t.plane(b)
            if plane.any():
                acc.add_patch(b + b_off, t.ix0, t.iy0, plane)
    out = acc.finish()
    if out is not None:
        out.n_instances = max(t.n_instances for t in ts)
    return out
