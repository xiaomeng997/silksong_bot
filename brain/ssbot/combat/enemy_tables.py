"""Behaviour tables of a multi-enemy arena at run time (Forum plan R2, docs/plans/forum_planner_plan.md §4.3): per enemy
type the Control-state walk (logged dwell ranges and successors), the attack families, and every type's support
templates packed into one store that a single vectorised query tests (the plan's one SupportQuery holding all 9 Forum
types).

    tables = EnemyTables.production()                       # knowledge/1.0.30000/enemies/forum: 107-fight build
    tables = EnemyTables.fold(extra, 1, margins, tubes)     # one fold of behaviour_build --extra (held-out recall)
    tid = tables.store.fine_id("support/RE_STAB/Stab 1/anchor")
    cid = tables.store.coarse_id(tid, kx=4, ky=4, kt=3)     # 0.25 u cells, grown 1 u and +-3 bins (cached)
    hit = tables.store.query(P, x, y, tk)                   # P: PlaceBatch arrays; x, y [N, T]; tk [T]

Two template pools. Fine: the tables' own 0.05 u cells, dilated at load by the hero hurtbox half-extents plus the base
margin plus the family's margin (support_margins.json: the largest held-out residual), exactly what the R0
certification queried (ssbot.knowledge.forum_support.FoldTables). Coarse: built on demand from a fine template by
OR-pooling COARSE_F x COARSE_F cells (a coarse cell is occupied when any fine cell inside it is: a superset, at most one
coarse cell wider) and dilating it by kx, ky coarse cells and kt time bins (SpaceTimeTemplate.dilated: still a
superset), cached per (template, kx, ky, kt) in growing arenas. One coarse placement stands for a whole interval of
entry times (2 kt + 1 bins) and a box of anchors (+-kx, +-ky cells) at once: the walk's states whose entry is only
known to a fraction of a second, and attacks that may start later at a position known only to the idle growth, cost
one placement each instead of one per frame and anchor (the R0 bench placed 28,000 a tick).

Loaded only what the walk queries: per-state anchor templates and _tail, the family templates (t from the attack start:
the family-wide union of the certification), the entry families' world-frame unions and the thrown hazards' self
templates. The behaviour builder imports the oracle IPC (the import firewall), so the tables are read from their JSON
and npz files here, and the static type facts from ssbot.core.forum.
"""
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numba
import numpy as np

from ssbot.combat.fastquery import _query_par
from ssbot.core.forum import ABSENT_FAMILIES, FORUM_TYPES, STRUCTURALLY_ABSENT, ForumType
from ssbot.knowledge import hitbox_tables as hb

KNOWLEDGE = Path(__file__).resolve().parents[3] / "knowledge" / "1.0.30000"
FORUM_DIR = KNOWLEDGE / "enemies" / "forum"
BIN = hb.BIN_S
TAIL = "_tail"
SUP = hb.SUPPORT
COARSE_F = 5                     # coarse cell = 5 fine cells (0.25 u)
COARSE_U = COARSE_F * hb.CELL_U
ARENA_BYTES = 32 << 20           # a coarse arena's capacity
FINE_ARENA_BYTES = 64 << 20      # the fine templates' arenas
CHUNKS = 16


@dataclass(slots=True)
class Family:
    name: str
    states: tuple[str, ...]
    starts: tuple[str, ...]
    entry: dict[str, tuple[float, float]]           # state -> entry time since the attack start (logged min, max)
    damage: int                                     # largest logged damage of its colliders (masks)
    sources: dict[str, frozenset[str]]              # state -> damage source type keys
    hazard_sources: frozenset[str] = frozenset()    # thrown hazard types among its sources


@dataclass(slots=True)
class TypeTable:
    """One enemy type: its static facts (ssbot.core.forum), the walk and the families."""
    spec: ForumType
    attack_starts: dict[str, str]
    decision_states: frozenset[str]
    families: dict[str, Family]
    dwell: dict[str, tuple[float, float]]
    succ: dict[str, tuple[str, ...]]
    p_succ: dict[str, dict[str, float]]             # smoothed transition probabilities (scoring only)
    state_family: dict[str, str] = field(default_factory=dict)
    absent: frozenset[str] = frozenset()            # structurally absent states (never walked)

    @property
    def tk(self) -> str:
        return self.spec.type_key


@dataclass(slots=True)
class PlaceBatch:
    """Placements as arrays: template id, template time at the query's t = 0 (t_ref), anchor (NaN: world frame),
    mirror; one entry per placement."""
    tid: np.ndarray
    t_ref: np.ndarray
    ax: np.ndarray
    ay: np.ndarray
    mirror: np.ndarray

    @classmethod
    def from_rows(cls, rows: list[tuple]) -> "PlaceBatch":
        if not rows:
            z = np.zeros(0)
            return cls(np.zeros(0, np.int64), z, z, z, np.zeros(0, np.int64))
        a = np.array(rows, np.float64)
        return cls(a[:, 0].astype(np.int64), a[:, 1].copy(), a[:, 2].copy(), a[:, 3].copy(),
                   a[:, 4].astype(np.int64))

    def __len__(self) -> int:
        return len(self.tid)

    def take(self, sel: np.ndarray) -> "PlaceBatch":
        return PlaceBatch(self.tid[sel], self.t_ref[sel], self.ax[sel], self.ay[sel], self.mirror[sel])


class _Arena:
    def __init__(self, cap: int):
        self.bits = np.zeros(max(cap, 1), np.uint8)
        self.used = 0
        self.full: list[np.ndarray] = []
        self.nfull = 0
        self._full = np.zeros(0, np.uint8)

    def add(self, t: hb.SpaceTimeTemplate) -> tuple[int, int]:
        b = np.ascontiguousarray(t.bits).ravel()
        off = self.used
        self.bits[off:off + b.size] = b
        self.used += b.size
        t.bits = self.bits[off:off + b.size].reshape(t.bits.shape)     # one copy: the template views the arena
        foff = self.nfull
        f = t.bits.reshape(t.nt, -1).any(axis=1).astype(np.uint8)
        self.full.append(f)
        self.nfull += f.size
        return off, foff

    def full_array(self) -> np.ndarray:
        if self._full.size != self.nfull:
            self._full = np.concatenate(self.full) if self.full else np.zeros(1, np.uint8)
        return self._full

    @property
    def nbytes(self) -> int:
        return int(self.bits.nbytes + self.nfull)


class _Pool:
    """Templates packed in arenas with their metadata rows (one generation of the coarse pool, or the fine pool)."""

    META = ("arena", "boff", "foff", "ix0", "iy0", "nx", "ny", "nt", "rb", "static", "anchored")

    def __init__(self, first: int = 0):
        self.arenas: list[_Arena] = []
        self.imeta: list[tuple] = []
        self.fmeta: list[tuple] = []
        self.tpls: list[hb.SpaceTimeTemplate] = []
        self.cache: dict[tuple, int] = {}
        self._im = np.zeros((0, len(self.META)), np.int64)
        self._fm = np.zeros((0, 3), np.float64)

    def add(self, t: hb.SpaceTimeTemplate, cap: int = ARENA_BYTES) -> int:
        need = int(t.bits.nbytes)
        if not self.arenas or self.arenas[-1].used + need > self.arenas[-1].bits.size:
            self.arenas.append(_Arena(max(cap, need)))
        a = len(self.arenas) - 1
        off, foff = self.arenas[a].add(t)
        self.tpls.append(t)
        self.imeta.append((a, off, foff, t.ix0, t.iy0, t.nx, t.ny, t.nt, t.bits.shape[2], int(t.static),
                           int(t.frame == "anchor")))
        self.fmeta.append((t.t0, t.bin_s, t.cell))
        return len(self.tpls) - 1

    def meta(self) -> tuple[np.ndarray, np.ndarray]:
        if len(self._im) != len(self.imeta):
            self._im = np.array(self.imeta, np.int64).reshape(-1, len(self.META))
            self._fm = np.array(self.fmeta, np.float64).reshape(-1, 3)
        return self._im, self._fm

    @property
    def nbytes(self) -> int:
        return sum(a.nbytes for a in self.arenas)


JMAX = 6                          # time pyramids / sparse tables up to 2^JMAX bins in one lookup
G_BINS = 1200                     # the idle growth table reaches 20 s
EMPTY = (np.inf, np.inf, -np.inf, -np.inf)


class TemplateStore:
    """The planner templates, three ways (query by placement kind):
      fine      the tables' templates (0.05 u cells, hero hurtbox and margins dilated in), one placement per entry
                time (PlaceBatch; the planner's parallel kernel, ssbot.combat.fastquery);
      window    a template's coarse base (OR-pooled to COARSE_U cells) as a time pyramid (level j holds the OR of
                2^j consecutive bins): one placement stands for every entry in [e0, e1] (WinBatch, _query_win_par:
                two lookups per point at the level that tiles the window);
      bbox      a template's per-bin bounding box as a sparse table (level j: the union of 2^j bins), grown by an
                anchor box: one placement per anchor box and entry window (multi_forecast's bounding-box rows), for
                anchors only known to a box (attacks that may start later).
    Ids >= 0 are the fine templates; < 0 the coarse-only bases (family-wide unions) and bbox-only tables (family walk
    templates: MultiForecaster.family_walk_bbox)."""

    def __init__(self, fine: dict[str, hb.SpaceTimeTemplate], hero_half=hb.HERO_HALF_U,
                 coarse_only: dict[str, hb.SpaceTimeTemplate] | None = None):
        for k, t in list(fine.items()) + list((coarse_only or {}).items()):
            if t.t_pad < 1:
                raise ValueError(f"{k}: needs the +-1 bin of export lag baked in")
            if t.pad_x < hero_half[0] - 1e-9 or t.pad_y < hero_half[1] - 1e-9:
                raise ValueError(f"{k}: dilated less than the hero hurtbox half-extents")
        self.keys: list[str] = list(fine)
        self.ids: dict[str, int] = {k: i for i, k in enumerate(self.keys)}
        self.fine = _Pool()
        size = sum(int(t.bits.nbytes) for t in fine.values())
        for t in fine.values():
            self.fine.add(t, cap=size)
        self.tpls = self.fine.tpls
        self.n_fine = len(self.keys)
        self._pooled: dict[int, hb.SpaceTimeTemplate] = {}
        self.coarse_keys: dict[str, int] = {}
        self._base_key: dict[int, str] = {}
        for k, t in (coarse_only or {}).items():
            self.add_coarse_base(k, coarsen(t, COARSE_F))
        # time pyramids of coarse bases
        self._pyr: dict[int, tuple] = {}
        self._pyr_arenas: list[_Arena] = []
        self._pyr_meta: dict[int, np.ndarray] = {}
        # bounding-box sparse tables
        self._bb: dict[int, tuple] = {}            # id -> (level offsets [JMAX + 1], nt, t0)
        self._bb_list: list[np.ndarray] = []
        self._bb_n = 0
        self._bb_arr = np.zeros((0, 4))

    # ---- ids ----

    def add_coarse_base(self, key: str, t: hb.SpaceTimeTemplate | None) -> int:
        """Register a template on the coarse grid (cell COARSE_U) as a coarse-only base (None: a bbox-only id whose
        table is given to add_bbox). A key registered before keeps its id (a new id would take the next key's)."""
        i = self.coarse_keys.get(key)
        if i is not None:
            if t is not None:
                self._pooled[i] = t
            return i
        i = -(len(self.coarse_keys) + 1)
        self.coarse_keys[key] = i
        self._base_key[i] = key
        if t is not None:
            self._pooled[i] = t
        return i

    def base_id(self, key: str) -> int | None:
        """A fine id (>= 0) or a coarse-only base id (< 0)."""
        i = self.ids.get(key)
        return i if i is not None else self.coarse_keys.get(key)

    def fine_id(self, key: str) -> int | None:
        return self.ids.get(key)

    def base(self, tid: int) -> hb.SpaceTimeTemplate:
        """The coarse base of an id (pooled once)."""
        b = self._pooled.get(tid)
        if b is None:
            b = self._pooled[tid] = coarsen(self.tpls[tid], COARSE_F)
        return b

    def template(self, tid: int) -> hb.SpaceTimeTemplate:
        return self.tpls[tid] if tid >= 0 else self._pooled[tid]

    def span(self, tid: int) -> tuple[float, float]:
        """(t0, t1) template times of an id (a bbox-only id: its table's)."""
        if tid >= 0 or tid in self._pooled:
            t = self.template(tid)
            return t.t0, t.t1
        _, nt, t0 = self._bb[tid]
        return t0, t0 + (nt - 1) * BIN

    # ---- time pyramids ----

    def pyramid(self, tid: int) -> tuple:
        """(arena, level offsets [JMAX + 1], meta (ix0, iy0, nx, ny, nt, rb, anchored, static), (t0, bin, cell)) of
        the coarse base's time pyramid, built once."""
        r = self._pyr.get(tid)
        if r is not None:
            return r
        t = self.base(tid)
        # the family-wide unions are placed at the attack's start only (one-bin windows): no levels above 0
        key = self.keys[tid] if tid >= 0 else self._base_key.get(tid, "")
        jm = 0 if (tid < 0 and key.count("/") == 2 and key.endswith("/anchor")) else JMAX
        levels = [np.ascontiguousarray(t.bits)]
        for j in range(1, jm + 1):
            s = 1 << (j - 1)
            prev = levels[-1]
            nxt = prev.copy()
            if s < t.nt:
                nxt[:-s] |= prev[s:]
            levels.append(nxt)
        need = sum(int(x.nbytes) for x in levels)
        if not self._pyr_arenas or self._pyr_arenas[-1].used + need > self._pyr_arenas[-1].bits.size:
            self._pyr_arenas.append(_Arena(max(ARENA_BYTES, need)))
        a = self._pyr_arenas[-1]
        offs = np.zeros(JMAX + 1, np.int64)
        for j, lv in enumerate(levels):
            offs[j] = a.used
            b = lv.ravel()
            a.bits[a.used:a.used + b.size] = b
            a.used += b.size
        offs[len(levels):] = offs[len(levels) - 1]
        r = self._pyr[tid] = (len(self._pyr_arenas) - 1, offs,
                              np.array([t.ix0, t.iy0, t.nx, t.ny, t.nt, t.bits.shape[2], int(t.frame == "anchor"),
                                        int(t.static), jm], np.int64), (t.t0, t.bin_s, t.cell))
        return r

    # ---- bounding boxes ----

    def bbox_level0(self, tid: int) -> tuple[np.ndarray, float]:
        """Per-bin bounding box of the coarse base (template frame; EMPTY rows for empty bins), and its t0."""
        t = self.base(tid)
        planes = np.unpackbits(t.bits, axis=2, count=t.nx).astype(bool)
        ax_ = planes.any(axis=1)
        ay_ = planes.any(axis=2)
        ne = ax_.any(axis=1)
        boxes = np.tile(np.array(EMPTY), (t.nt, 1))
        if ne.any():
            x0 = np.argmax(ax_, axis=1)
            x1 = t.nx - 1 - np.argmax(ax_[:, ::-1], axis=1)
            y0 = np.argmax(ay_, axis=1)
            y1 = t.ny - 1 - np.argmax(ay_[:, ::-1], axis=1)
            c = t.cell
            boxes[ne] = np.stack([(t.ix0 + x0) * c, (t.iy0 + y0) * c, (t.ix0 + x1 + 1) * c, (t.iy0 + y1 + 1) * c],
                                 axis=1)[ne]
        return boxes, t.t0

    def add_bbox(self, tid: int, boxes: np.ndarray, t0: float) -> tuple:
        """The sparse table of a level-0 bbox table (rows per bin; EMPTY for empty bins)."""
        levels = [np.asarray(boxes, np.float64)]
        nt = len(boxes)
        for j in range(1, JMAX + 1):
            s = 1 << (j - 1)
            prev = levels[-1]
            nxt = prev.copy()
            if s < nt:
                sh = prev[s:]
                nxt[:-s, 0] = np.minimum(prev[:-s, 0], sh[:, 0])
                nxt[:-s, 1] = np.minimum(prev[:-s, 1], sh[:, 1])
                nxt[:-s, 2] = np.maximum(prev[:-s, 2], sh[:, 2])
                nxt[:-s, 3] = np.maximum(prev[:-s, 3], sh[:, 3])
            levels.append(nxt)
        offs = np.zeros(JMAX + 1, np.int64)
        for j, lv in enumerate(levels):
            offs[j] = self._bb_n
            self._bb_list.append(lv)
            self._bb_n += nt
        r = self._bb[tid] = (offs, nt, float(t0))
        return r

    def bbox_table(self, tid: int) -> tuple:
        """(level offsets [JMAX + 1] into bb_rows(), bins, t0) of an id's bounding-box sparse table (built once)."""
        r = self._bb.get(tid)
        if r is None:
            boxes, t0 = self.bbox_level0(tid)
            r = self.add_bbox(tid, boxes, t0)
        return r

    def active_span(self, tid: int) -> tuple[float, float]:
        """(t0, t1) of the bins of an id's bounding-box table that hold a box (span() covers the empty ones too: a
        family walk of a parked Tiny spans from -332 s; forum.md 15.2), cached."""
        c = self._active.get(tid) if hasattr(self, "_active") else None
        if c is None:
            if not hasattr(self, "_active"):
                self._active = {}
            offs, nt, t0 = self.bbox_table(tid)
            b = self.bb_rows()[int(offs[0]):int(offs[0]) + nt]
            nz = np.flatnonzero(b[:, 2] >= b[:, 0])
            c = (t0 + float(nz[0]) * BIN, t0 + float(nz[-1]) * BIN) if len(nz) else (math.inf, -math.inf)
            self._active[tid] = c
        return c

    def bb_rows(self) -> np.ndarray:
        if self._bb_arr.shape[0] != self._bb_n:
            self._bb_arr = np.ascontiguousarray(np.concatenate(self._bb_list)) if self._bb_list \
                else np.zeros((0, 4))
        return self._bb_arr

    def nbytes(self) -> int:
        return self.fine.nbytes + sum(a.nbytes for a in self._pyr_arenas) + \
            sum(int(t.bits.nbytes) for t in self._pooled.values()) + self._bb_n * 32

    # ---- queries ----

    def query(self, P: PlaceBatch, x, y, tk, out: np.ndarray | None = None) -> np.ndarray:
        """Fine placements: [N, T] bool, hero hurtbox centres x, y [N, T] at tk [T] s from the origin inside one (OR
        into out when given). NaN points are skipped."""
        x = np.asarray(x, np.float64)
        y = np.asarray(y, np.float64)
        tk = np.ascontiguousarray(tk, np.float64)
        if out is None:
            out = np.zeros(x.shape, bool)
        if not len(P):
            return out
        xt, yt, cbox, chunks = _cand(x, y)
        res = np.zeros(xt.shape, np.bool_)
        im_all, fm_all = self.fine.meta()
        tid = P.tid
        ar = im_all[tid, 0]
        for a in np.unique(ar):
            sel = np.flatnonzero(ar == a)
            imt = im_all[tid[sel]]
            fmt = fm_all[tid[sel]]
            anchored = (imt[:, 10] != 0) & ~np.isnan(P.ax[sel])
            im = np.empty((len(sel), 10), np.int64)
            im[:, 0:6] = imt[:, 3:9]
            im[:, 6] = np.where(anchored, P.mirror[sel], 1)
            im[:, 7] = anchored
            im[:, 8] = imt[:, 9]
            im[:, 9] = imt[:, 2]
            fm = np.empty((len(sel), 6), np.float64)
            fm[:, 0:3] = fmt
            fm[:, 3] = np.where(anchored, P.ax[sel], 0.0)
            fm[:, 4] = np.where(anchored, P.ay[sel], 0.0)
            fm[:, 5] = P.t_ref[sel]
            pbox = _pbox(imt[:, 3], imt[:, 4], imt[:, 5], imt[:, 6], fmt[:, 2], im[:, 6], fm[:, 3], fm[:, 4])
            arena = self.fine.arenas[int(a)]
            _query_par(arena.bits[:max(arena.used, 1)], np.ascontiguousarray(imt[:, 1]), im, fm,
                       arena.full_array(), tk, xt, yt, res, chunks, pbox, cbox)
        out |= res.T
        return out

    def query_win(self, W: "WinBatch", x, y, tk, out: np.ndarray | None = None) -> np.ndarray:
        """Window placements (coarse time pyramids): [N, T] bool, OR into out when given."""
        x = np.asarray(x, np.float64)
        y = np.asarray(y, np.float64)
        tk = np.ascontiguousarray(tk, np.float64)
        if out is None:
            out = np.zeros(x.shape, bool)
        if not len(W):
            return out
        xt, yt, cbox, chunks = _cand(x, y)
        res = np.zeros(xt.shape, np.bool_)
        pyr = [self.pyramid(int(t)) for t in W.tid]
        ar = np.array([p[0] for p in pyr], np.int64)
        for a in np.unique(ar):
            sel = np.flatnonzero(ar == a)
            meta = np.stack([pyr[i][2] for i in sel])
            loff = np.ascontiguousarray(np.stack([pyr[i][1] for i in sel]))
            fmt = np.array([pyr[i][3] for i in sel], np.float64)
            anchored = (meta[:, 6] != 0) & ~np.isnan(W.ax[sel])
            im = np.empty((len(sel), 9), np.int64)
            im[:, 0:6] = meta[:, 0:6]
            im[:, 6] = np.where(anchored, W.mirror[sel], 1)
            im[:, 7] = anchored
            im[:, 8] = meta[:, 8]
            fm = np.empty((len(sel), 7), np.float64)
            fm[:, 0:3] = fmt
            fm[:, 3] = np.where(anchored, W.ax[sel], 0.0)
            fm[:, 4] = np.where(anchored, W.ay[sel], 0.0)
            fm[:, 5] = W.e0[sel]
            fm[:, 6] = W.e1[sel]
            pbox = _pbox(meta[:, 0], meta[:, 1], meta[:, 2], meta[:, 3], fmt[:, 2], im[:, 6], fm[:, 3], fm[:, 4])
            arena = self._pyr_arenas[int(a)]
            _query_win_par(arena.bits[:max(arena.used, 1)], loff, im, fm, tk, xt, yt, res, chunks, pbox, cbox)
        out |= res.T
        return out


@dataclass(slots=True)
class WinBatch:
    """Window placements as arrays: base id (fine or coarse-only: its coarse base's pyramid), entry window
    [e0, e1] (s from the origin), anchor (NaN: world frame), mirror."""
    tid: np.ndarray
    e0: np.ndarray
    e1: np.ndarray
    ax: np.ndarray
    ay: np.ndarray
    mirror: np.ndarray

    @classmethod
    def from_rows(cls, rows: list[tuple]) -> "WinBatch":
        if not rows:
            z = np.zeros(0)
            return cls(np.zeros(0, np.int64), z, z, z, z, np.zeros(0, np.int64))
        a = np.array(rows, np.float64)
        return cls(a[:, 0].astype(np.int64), a[:, 1].copy(), a[:, 2].copy(), a[:, 3].copy(), a[:, 4].copy(),
                   a[:, 5].astype(np.int64))

    def __len__(self) -> int:
        return len(self.tid)

    def take(self, sel: np.ndarray) -> "WinBatch":
        return WinBatch(self.tid[sel], self.e0[sel], self.e1[sel], self.ax[sel], self.ay[sel], self.mirror[sel])


def _cand(x: np.ndarray, y: np.ndarray):
    xt = np.ascontiguousarray(x.T)
    yt = np.ascontiguousarray(y.T)
    cbox = np.ascontiguousarray(np.stack([np.fmin.reduce(xt, axis=1), np.fmin.reduce(yt, axis=1),
                                          np.fmax.reduce(xt, axis=1), np.fmax.reduce(yt, axis=1)], 1))
    cbox[np.isnan(cbox)] = 0.0
    return xt, yt, cbox, min(CHUNKS, max(1, xt.shape[1] // 8))


def _pbox(ix0, iy0, nx, ny, cell, mirror, ax, ay) -> np.ndarray:
    gx0, gx1 = ix0 * cell, (ix0 + nx) * cell
    gy0, gy1 = iy0 * cell, (iy0 + ny) * cell
    wx0, wx1 = ax + mirror * gx0, ax + mirror * gx1
    return np.ascontiguousarray(np.stack([np.minimum(wx0, wx1), ay + gy0, np.maximum(wx0, wx1), ay + gy1], 1))


@numba.njit(cache=True, parallel=True)
def _query_win_par(bits, loff, imeta, fmeta, tk, xt, yt, out, chunks, pbox, cbox):
    """out[k, n] |= some window placement p occupied at (xt[k, n], yt[k, n]) for an entry in [e0, e1]: the template
    bins of tk[k] - e1 .. tk[k] - e0, tiled by two lookups at pyramid level j (2^j <= the window's bins), more for a
    window longer than 2^jmax. imeta[p] = (ix0, iy0, nx, ny, nt, row bytes, mirror, anchored, jmax); fmeta[p] = (t0,
    bin_s, cell, ax, ay, e0, e1)."""
    n_t, n_c = xt.shape
    n_p = loff.shape[0]
    for ch in numba.prange(chunks):
        c0 = ch * n_c // chunks
        c1 = (ch + 1) * n_c // chunks
        if c1 <= c0:
            continue
        for p in range(n_p):
            ix0, iy0, nx, ny, nt, rb = imeta[p, 0], imeta[p, 1], imeta[p, 2], imeta[p, 3], imeta[p, 4], imeta[p, 5]
            mirror, anchored, jmax = imeta[p, 6], imeta[p, 7], imeta[p, 8]
            t0, bs, inv = fmeta[p, 0], fmeta[p, 1], 1.0 / fmeta[p, 2]
            ax, ay = fmeta[p, 3], fmeta[p, 4]
            if not anchored:
                mirror, ax, ay = 1, 0.0, 0.0
            plane = ny * rb
            for k in range(n_t):
                b_lo = int(np.rint((tk[k] - fmeta[p, 6] - t0) / bs))
                b_hi = int(np.rint((tk[k] - fmeta[p, 5] - t0) / bs))
                if b_hi < 0 or b_lo >= nt:
                    continue
                if b_lo < 0:
                    b_lo = 0
                if b_hi > nt - 1:
                    b_hi = nt - 1
                if (pbox[p, 0] > cbox[k, 2] or pbox[p, 2] < cbox[k, 0] or pbox[p, 1] > cbox[k, 3]
                        or pbox[p, 3] < cbox[k, 1]):
                    continue
                for n in range(c0, c1):
                    if out[k, n] or xt[k, n] != xt[k, n]:
                        continue
                    fx = mirror * (xt[k, n] - ax) * inv - ix0
                    fy = (yt[k, n] - ay) * inv - iy0
                    if fx < 0.0 or fy < 0.0 or fx >= nx or fy >= ny:
                        continue
                    ix = int(fx)
                    cell = int(fy) * rb + (ix >> 3)
                    sh = 7 - (ix & 7)
                    b = b_lo
                    hit = False
                    while b <= b_hi and not hit:
                        L = b_hi - b + 1
                        j = 0
                        while j < jmax and (1 << (j + 1)) <= L:
                            j += 1
                        if (bits[loff[p, j] + b * plane + cell] >> sh) & 1:
                            hit = True
                        elif L <= (1 << (j + 1)):
                            b2 = b_hi - (1 << j) + 1
                            if (bits[loff[p, j] + b2 * plane + cell] >> sh) & 1:
                                hit = True
                            break
                        b += 1 << j
                    if hit:
                        out[k, n] = True


def shifted_union(parts: list[tuple[hb.SpaceTimeTemplate, float]], key: str) -> hb.SpaceTimeTemplate | None:
    """One template (same frame and cell) holding every part's bins shifted by its dt (s): parts [(template, dt)]."""
    parts = [(t, dt) for t, dt in parts if t is not None]
    if not parts:
        return None
    cell, bs = parts[0][0].cell, parts[0][0].bin_s
    ix0 = min(t.ix0 for t, _ in parts)
    iy0 = min(t.iy0 for t, _ in parts)
    ix1 = max(t.ix0 + t.nx for t, _ in parts)
    iy1 = max(t.iy0 + t.ny for t, _ in parts)
    b0s = [int(round((t.t0 + dt) / bs)) for t, dt in parts]
    b0 = min(b0s)
    b1 = max(b + t.nt for b, (t, _) in zip(b0s, parts))
    acc = np.zeros((b1 - b0, iy1 - iy0, ix1 - ix0), bool)
    for b, (t, _) in zip(b0s, parts):
        pl = np.unpackbits(t.bits, axis=2, count=t.nx).astype(bool)
        acc[b - b0:b - b0 + t.nt, t.iy0 - iy0:t.iy0 - iy0 + t.ny, t.ix0 - ix0:t.ix0 - ix0 + t.nx] |= pl
    return hb.SpaceTimeTemplate(key=key, frame=parts[0][0].frame, ix0=ix0, iy0=iy0, nx=ix1 - ix0, ny=iy1 - iy0,
                                t0=b0 * bs, bits=np.ascontiguousarray(np.packbits(acc, axis=2)), cell=cell, bin_s=bs,
                                t_pad=min(t.t_pad for t, _ in parts), pad_x=min(t.pad_x for t, _ in parts),
                                pad_y=min(t.pad_y for t, _ in parts))


def coarsen(t: hb.SpaceTimeTemplate, f: int) -> hb.SpaceTimeTemplate:
    """OR-pool f x f cells: coarse cell (i, j) covers fine cells f i .. f i + f - 1 of the world grid (aligned to
    multiples of f cells), occupied when any of them is."""
    cx0, cy0 = t.ix0 // f, t.iy0 // f
    px, py = t.ix0 - cx0 * f, t.iy0 - cy0 * f
    NX, NY = -(-(px + t.nx) // f), -(-(py + t.ny) // f)
    bits = np.zeros((t.nt, NY, (NX + 7) // 8), np.uint8)
    step = max(1, (64 << 20) // max(1, NY * f * NX * f))         # bins per chunk: ~64 MB of booleans at most
    buf = np.zeros((min(step, t.nt), NY * f, NX * f), bool)
    for b0 in range(0, t.nt, step):
        b1 = min(t.nt, b0 + step)
        buf[:] = False
        buf[:b1 - b0, py:py + t.ny, px:px + t.nx] = np.unpackbits(t.bits[b0:b1], axis=2, count=t.nx).astype(bool)
        bits[b0:b1] = np.packbits(buf[:b1 - b0].reshape(b1 - b0, NY, f, NX, f).any(axis=(2, 4)), axis=2)
    return hb.SpaceTimeTemplate(key=t.key, frame=t.frame, ix0=cx0, iy0=cy0, nx=NX, ny=NY, t0=t.t0,
                                bits=np.ascontiguousarray(bits), cell=t.cell * f, bin_s=t.bin_s,
                                n_instances=t.n_instances, t_pad=t.t_pad, pad_x=t.pad_x, pad_y=t.pad_y,
                                static=t.static)


def _family(name: str, a: dict, spec: ForumType) -> Family:
    srcs: dict[str, set[str]] = {}
    damage = 1
    for h in a.get("hitboxes") or ():
        srcs.setdefault(h["state"], set()).add(h["source"].split(":")[0])
        damage = max([damage] + [int(v) for v in h.get("dmg") or ()])
    entry = {s: (float(q["min"]), float(q["max"])) for s, q in (a.get("state_entry_s") or {}).items() if q.get("n")}
    hz = frozenset(x for v in srcs.values() for x in v if x in spec.hazards)
    return Family(name, tuple(a.get("states") or ()), tuple(a.get("start_states") or ()), entry, damage,
                  {k: frozenset(v) for k, v in srcs.items()}, hz)


def type_table(d: dict, spec: ForumType, walk: dict | None = None) -> TypeTable:
    """A type's table from its behaviour JSON (production) or with another walk (a fold's dwell / successors from
    behaviour_build --extra build.json). Structurally absent states (ssbot.core.forum) are dropped from the walk."""
    absent = STRUCTURALLY_ABSENT.get(spec.type_key, frozenset())
    absent_f = ABSENT_FAMILIES.get(spec.type_key, frozenset())
    fams = {f: _family(f, a, spec) for f, a in d["attacks"].items() if f not in absent_f}
    starts = {s: f for s, f in d["spec"]["attack_starts"].items() if s not in absent and f not in absent_f}
    deaths = set(spec.death_states)
    if walk is None:
        dwell = {s: (float(q.get("min", 0.0)), float(q.get("max", 0.0))) for s, q in d["dwell_s"].items()}
        succ = {s: tuple(t for t in v if t not in deaths) for s, v in d["support_transitions"].items()}
    else:
        dwell = {s: (float(v[0]), float(v[1])) for s, v in walk["dwell"].items()}
        succ = {s: tuple(t for t in v if t not in deaths) for s, v in walk["succ"].items()}
    succ = {s: tuple(t for t in v if t not in absent) for s, v in succ.items() if s not in absent}
    p_succ: dict[str, dict[str, float]] = {}
    for e in d["graph"]["edges"]:
        if e["to"] in deaths or e["to"] in absent:
            continue
        p_succ.setdefault(e["from"], {})[e["to"]] = float(e.get("p") or 0.0)
    for s, row in p_succ.items():
        tot = sum(row.values()) or 1.0
        p_succ[s] = {k: v / tot for k, v in row.items()}
    sf = {}
    for f in fams.values():
        for s in f.states:
            sf.setdefault(s, f.name)
    return TypeTable(spec, starts, frozenset(d["spec"]["decision_states"]) - absent, fams, dwell, succ, p_succ, sf,
                     frozenset(absent))


def wanted_key(k: str, spec: ForumType, family_wide: bool = True) -> bool:
    """The template keys the walk queries: per-state anchor (and _tail), family anchor (family-wide union), the entry
    family's world-frame unions, the hazards' self templates."""
    p = k.split("/")
    if not k.startswith(SUP):
        return False
    if len(p) == 4 and p[1] == "ent":
        return p[3] == "self"
    absent_f = ABSENT_FAMILIES.get(spec.type_key, frozenset())
    absent_s = STRUCTURALLY_ABSENT.get(spec.type_key, frozenset())
    if p[1] in absent_f:
        return False
    if len(p) == 4:
        if p[2] in absent_s:
            return False
        return p[3] == "anchor" or (p[3] == "world_all" and p[1] == spec.entry_family)
    if len(p) == 3:
        return (p[2] == "anchor" and family_wide) or (p[2] == "world_all" and p[1] == spec.entry_family)
    return False


def load_type_templates(npz: Path, spec: ForumType, margins: dict, base: float = 0.0,
                        family_wide: bool = True):
    """The wanted support templates of one type's npz, one at a time (key, template), each dilated by the hero
    hurtbox half-extents plus base plus the family's margin (or the hazard's: margins ("ent", hazard)); the npz is
    read lazily, so only one raw and one dilated template are held at a time."""
    with np.load(Path(npz), allow_pickle=False) as z:
        keys = sorted(f[:-5] for f in z.files if f.endswith("/bits") and f[:-5] + "/meta" in z.files)
        for k in keys:
            if not wanted_key(k, spec, family_wide):
                continue
            t = hb.SpaceTimeTemplate.from_arrays(k, z[k + "/bits"], z[k + "/meta"])
            p = k.split("/")
            m = base + (margins.get(("ent", p[2]), 0.0) if p[1] == "ent" else
                        margins.get((spec.type_key, p[1]), 0.0))
            yield k, t.dilated(rx=hb.HERO_HALF_U[0] + m, ry=hb.HERO_HALF_U[1] + m, key=k)


@dataclass(slots=True)
class Tubes:
    """The idle body tube and the current-collider tube's calibration (support_recall: production_tubes): per type
    the idle growth g[1/60 s bin of game time] (u), the top speed (u/s, the growth past the calibrated bins and of
    the collider tube) and the body hull relative to the transform (x0, y0, x1, y1)."""
    growth: dict[str, list[float]]
    speed: dict[str, float]
    hull: dict[str, tuple[float, float, float, float]]
    _tab: dict = field(default_factory=dict)

    @classmethod
    def from_doc(cls, d: dict) -> "Tubes":
        return cls({k: list(map(float, v)) for k, v in (d.get("idle_growth") or {}).items()},
                   {k: float(v) for k, v in (d.get("tube_speed") or {}).items()},
                   {k: tuple(map(float, v)) for k, v in (d.get("body_hull") or {}).items()})


    def g(self, tk: str, dt) -> np.ndarray:
        """Idle growth after dt game s since the sighting (the bins of forum_support.tube_bin; past the calibration
        at the type's top speed): a table lookup."""
        tab = self._tab.get(tk)
        if tab is None:
            g = self.growth.get(tk)
            k = np.arange(G_BINS + 1)
            if not g:
                tab = self.speed.get(tk, 60.0) * k * BIN
            else:
                n = len(g) - 1
                ga = np.asarray(g, np.float64)
                tab = np.where(k <= n, ga[np.minimum(k, n)], ga[-1] + self.speed.get(tk, 60.0) * (k - n) * BIN)
            self._tab[tk] = tab
        dt = np.asarray(dt, np.float64)
        k = np.clip(np.ceil(dt / BIN - 0.05), 0, G_BINS).astype(np.int64)
        return tab[k]


class EnemyTables:
    """Every Forum type's table and one template store (see the module docstring). The family templates (t from the
    attack start, the family-wide union: 426 of 791 MB of the production tables at 0.05 u) are kept only coarse."""

    def __init__(self, types: dict[str, TypeTable], store: TemplateStore, tubes: Tubes, margins: dict,
                 certified: bool, source: str, chains: dict | None = None):
        self.types = types
        self.store = store
        self.tubes = tubes
        self.margins = dict(margins)
        self.certified = certified
        self.source = source
        self.chains = chains or {}
        self._keys: dict[tuple, int | None] = {}

    def key_id(self, fam: str, state: str | None, frame: str = "anchor") -> int | None:
        """Id of support/<fam>/<state>/<frame> (state None: the family template support/<fam>/<frame>): a fine id
        (>= 0) or a coarse-only base id (< 0)."""
        k = (fam, state, frame)
        i = self._keys.get(k, 0.5)
        if i == 0.5:
            key = f"{SUP}{fam}/{state}/{frame}" if state is not None else f"{SUP}{fam}/{frame}"
            i = self._keys[k] = self.store.base_id(key)
        return i

    def template(self, tid: int) -> hb.SpaceTimeTemplate:
        """The fine template, the coarse base of a coarse-only id, or a coarse one of the current generation."""
        return self.store.template(tid)

    def self_id(self, hazard: str) -> int | None:
        return self.key_id("ent", hazard, "self")

    # ---- loaders ----

    @staticmethod
    def _store(per_type) -> TemplateStore:
        """Build the store type by type (the peak holds one type's dilated templates, not all nine)."""
        store = TemplateStore({})
        for tpls in per_type:
            for k, t in (tpls.items() if isinstance(tpls, dict) else tpls):
                if k.count("/") == 2:
                    store.add_coarse_base(k, coarsen(t, COARSE_F))
                else:
                    store.keys.append(k)
                    store.ids[k] = len(store.keys) - 1
                    store.fine.add(t, cap=FINE_ARENA_BYTES)
            store.n_fine = len(store.keys)
        return store

    @classmethod
    def production(cls, root: Path | None = None, margins_path: Path | None = None, base: float = 0.0,
                   types: tuple[str, ...] | None = None, family_wide: bool = True) -> "EnemyTables":
        """The committed tables (knowledge/.../enemies/forum/<enemy>.json + the generated _hitboxes.npz) with the
        production margins and tubes of support_margins.json (R0 certification, forum.md §12.2)."""
        root = Path(root) if root else FORUM_DIR
        mp = Path(margins_path) if margins_path else root / "support_margins.json"
        md = json.loads(mp.read_text("utf-8"))
        margins = parse_margins(md.get("by_family") or {})
        tubes = Tubes.from_doc(md.get("production_tubes") or {})
        tts = {}

        def per_type():
            for tk, spec in FORUM_TYPES.items():
                if types is not None and tk not in types:
                    continue
                d = json.loads((root / f"{spec.enemy}.json").read_text("utf-8"))
                tts[tk] = type_table(d, spec)
                yield load_type_templates(root / d["templates"]["file"], spec, margins, base, family_wide)
        store = cls._store(per_type())
        return cls(tts, store, tubes, margins, bool(md.get("certified")), f"production:{root}",
                   load_chains(root / "chains.json"))

    @classmethod
    def fold(cls, extra: Path, fold: int, margins: dict, tubes: Tubes, root: Path | None = None, base: float = 0.0,
             types: tuple[str, ...] | None = None, family_wide: bool = True) -> "EnemyTables":
        """One fold of a behaviour_build --extra directory: <enemy>_support_fold<k>.npz and build.json's walk of that
        fold, the families from the committed JSON tables (the same build), margins and tubes as given."""
        root = Path(root) if root else FORUM_DIR
        extra = Path(extra)
        build = json.loads((extra / "build.json").read_text("utf-8"))
        tts = {}

        def per_type():
            for tk, spec in FORUM_TYPES.items():
                if types is not None and tk not in types:
                    continue
                d = json.loads((root / f"{spec.enemy}.json").read_text("utf-8"))
                w = build["walk"].get(tk) or {}
                walk = {"dwell": (w.get("dwell") or {}).get(str(fold), {}),
                        "succ": (w.get("succ") or {}).get(str(fold), {})}
                tts[tk] = type_table(d, spec, walk)
                npz = extra / f"{spec.enemy}_support_fold{fold}.npz"
                yield load_type_templates(npz, spec, margins, base, family_wide) if npz.exists() else {}
        store = cls._store(per_type())
        return cls(tts, store, tubes, margins, True, f"fold{fold}:{extra}", load_chains(root / "chains.json"))


def parse_margins(by_family: dict) -> dict:
    """{"<type>/<family>": u, "ent/<hazard>": u} -> {(type, family) | ("ent", hazard): u}."""
    out = {}
    for k, v in by_family.items():
        a, b = k.split("/", 1)
        out[(a, b)] = float(v)
    return out


def load_chains(path: Path) -> dict:
    """Multi-hit chains (forum_products chains.json, by_source): {collider name: (max hits, max masks)}."""
    try:
        d = json.loads(Path(path).read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for src, row in (d.get("by_source") or {}).items():
        hits = row.get("max_hits") or row.get("hits_max") or 0
        dmg = row.get("max_damage") or row.get("damage_max") or 0
        if not hits:
            dist = row.get("hits") or {}
            hits = max((int(k) for k in dist), default=0) if isinstance(dist, dict) else 0
        if not dmg:
            dist = row.get("damage") or {}
            dmg = max((int(k) for k in dist), default=0) if isinstance(dist, dict) else 0
        out[src] = (int(hits), int(dmg))
    return out
