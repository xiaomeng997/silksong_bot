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
COARSE_BUDGET = 384 << 20        # a coarse generation larger than this is dropped (TemplateStore.trim)
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


class TemplateStore:
    """Fine and coarse planner templates in packed arenas, with per-template metadata for vectorised placement
    arrays; query() runs the planner's parallel kernel (ssbot.combat.fastquery) once per arena. Ids below n_fine are
    fine templates; the others index the current coarse generation (coarse_id), which is dropped and rebuilt on
    demand when it outgrows COARSE_BUDGET (a forecast keeps the generation it was built with: gen)."""

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
        self.gen = _Pool()
        self.generations = 1
        self._pooled: dict[int, hb.SpaceTimeTemplate] = {}
        # coarse-only templates (the large family-wide unions, the family walk templates): base ids < 0
        self.coarse_keys: dict[str, int] = {}
        self._base_key: dict[int, str] = {}
        for k, t in (coarse_only or {}).items():
            self.add_coarse_base(k, coarsen(t, COARSE_F))
        self._bb: dict[int, tuple] = {}
        self._bb_list: list[np.ndarray] = []
        self._bb_n = 0
        self._bb_arr = np.zeros((0, 4))

    def add_coarse_base(self, key: str, t: hb.SpaceTimeTemplate) -> int:
        """Register a template already on the coarse grid (cell COARSE_U) as a coarse-only base."""
        i = -(len(self.coarse_keys) + 1)
        self.coarse_keys[key] = i
        self._base_key[i] = key
        self._pooled[i] = t
        return i

    def base_id(self, key: str) -> int | None:
        """A fine id (>= 0) or a coarse-only base id (< 0: only coarse_id takes it)."""
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

    def coarse_id(self, tid: int, kx: int = 0, ky: int = 0, kt: int = 0) -> int:
        """The coarse version of template tid (fine id or coarse base) grown by kx, ky coarse cells and kt bins,
        built once per generation."""
        ck = (tid, kx, ky, kt)
        g = self.gen
        i = g.cache.get(ck)
        if i is not None:
            return i
        base = self.base(tid)
        name = self.keys[tid] if tid >= 0 else self._base_key[tid]
        t = base.dilated(rx=kx * COARSE_U, ry=ky * COARSE_U, t_bins=kt, key=f"{name}~{kx},{ky},{kt}") \
            if (kx or ky or kt) else hb.SpaceTimeTemplate(**{f: getattr(base, f) for f in (
                "key", "frame", "ix0", "iy0", "nx", "ny", "t0", "bits", "cell", "bin_s", "n_instances", "t_pad",
                "pad_x", "pad_y", "static")})
        i = self.n_fine + g.add(t)
        g.cache[ck] = i
        return i

    def bbox_table(self, tid: int) -> tuple[int, int, float]:
        """(row offset, bins, t0) of template tid's per-bin bounding box in bb_rows() (template frame, from its
        coarse base: a superset by at most one coarse cell; NaN rows for empty bins), built once."""
        r = self._bb.get(tid)
        if r is None:
            t = self.base(tid)
            planes = np.unpackbits(t.bits, axis=2, count=t.nx).astype(bool)
            ax_ = planes.any(axis=1)
            ay_ = planes.any(axis=2)
            ne = ax_.any(axis=1)
            boxes = np.full((t.nt, 4), np.nan)
            if ne.any():
                x0 = np.argmax(ax_, axis=1)
                x1 = t.nx - 1 - np.argmax(ax_[:, ::-1], axis=1)
                y0 = np.argmax(ay_, axis=1)
                y1 = t.ny - 1 - np.argmax(ay_[:, ::-1], axis=1)
                c = t.cell
                boxes[ne] = np.stack([(t.ix0 + x0) * c, (t.iy0 + y0) * c, (t.ix0 + x1 + 1) * c,
                                      (t.iy0 + y1 + 1) * c], axis=1)[ne]
            off = self._bb_n
            self._bb_list.append(boxes)
            self._bb_n += t.nt
            r = self._bb[tid] = (off, t.nt, t.t0)
        return r

    def bb_rows(self) -> np.ndarray:
        if self._bb_arr.shape[0] != self._bb_n:
            self._bb_arr = np.ascontiguousarray(np.concatenate(self._bb_list)) if self._bb_list \
                else np.zeros((0, 4))
        return self._bb_arr

    def template(self, tid: int, gen: _Pool | None = None) -> hb.SpaceTimeTemplate:
        if tid < 0:
            return self._pooled[tid]
        if tid < self.n_fine:
            return self.tpls[tid]
        return (gen or self.gen).tpls[tid - self.n_fine]

    def trim(self, budget: int = COARSE_BUDGET) -> bool:
        """Start a new coarse generation when this one holds more than budget bytes (call between forecasts)."""
        if self.gen.nbytes > budget:
            self.gen = _Pool()
            self.generations += 1
            return True
        return False

    def nbytes(self) -> int:
        return self.fine.nbytes + self.gen.nbytes + sum(int(t.bits.nbytes) for t in self._pooled.values())

    # ---- query ----

    def query(self, P: PlaceBatch, x, y, tk, out: np.ndarray | None = None, gen: _Pool | None = None) -> np.ndarray:
        """[N, T] bool: hero hurtbox centres x, y [N, T] at tk [T] s from the origin inside some placement (OR into
        out when given). NaN points are skipped. gen: the coarse generation the placements were made in."""
        x = np.asarray(x, np.float64)
        y = np.asarray(y, np.float64)
        tk = np.ascontiguousarray(tk, np.float64)
        if out is None:
            out = np.zeros(x.shape, bool)
        if not len(P):
            return out
        gen = gen or self.gen
        xt = np.ascontiguousarray(x.T)
        yt = np.ascontiguousarray(y.T)
        res = np.zeros(xt.shape, np.bool_)
        cbox = np.ascontiguousarray(np.stack([np.fmin.reduce(xt, axis=1), np.fmin.reduce(yt, axis=1),
                                              np.fmax.reduce(xt, axis=1), np.fmax.reduce(yt, axis=1)], 1))
        cbox[np.isnan(cbox)] = 0.0
        chunks = min(CHUNKS, max(1, xt.shape[1] // 8))
        coarse = P.tid >= self.n_fine
        for pool, sel_mask, off in ((self.fine, ~coarse, 0), (gen, coarse, self.n_fine)):
            if not sel_mask.any():
                continue
            im_all, fm_all = pool.meta()
            idx = np.flatnonzero(sel_mask)
            tid = P.tid[idx] - off
            ar = im_all[tid, 0]
            for a in np.unique(ar):
                s2 = ar == a
                sel = idx[s2]
                imt = im_all[tid[s2]]
                fmt = fm_all[tid[s2]]
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
                boff = np.ascontiguousarray(imt[:, 1])
                cell = fmt[:, 2]
                gx0, gx1 = imt[:, 3] * cell, (imt[:, 3] + imt[:, 5]) * cell
                gy0, gy1 = imt[:, 4] * cell, (imt[:, 4] + imt[:, 6]) * cell
                mir = im[:, 6]
                wx0, wx1 = fm[:, 3] + mir * gx0, fm[:, 3] + mir * gx1
                pbox = np.ascontiguousarray(np.stack([np.minimum(wx0, wx1), fm[:, 4] + gy0, np.maximum(wx0, wx1),
                                                      fm[:, 4] + gy1], 1))
                arena = pool.arenas[int(a)]
                _query_par(arena.bits[:max(arena.used, 1)], boff, im, fm, arena.full_array(), tk, xt, yt, res,
                           chunks, pbox, cbox)
        out |= res.T
        return out


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
    planes = np.unpackbits(t.bits, axis=2, count=t.nx).astype(bool)
    buf = np.zeros((t.nt, NY * f, NX * f), bool)
    buf[:, py:py + t.ny, px:px + t.nx] = planes
    pooled = buf.reshape(t.nt, NY, f, NX, f).any(axis=(2, 4))
    bits = np.packbits(pooled, axis=2)
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
                        family_wide: bool = True) -> dict[str, hb.SpaceTimeTemplate]:
    """The wanted support templates of one type's npz, dilated by the hero hurtbox half-extents plus base plus the
    family's margin (or the hazard's: margins ("ent", hazard))."""
    raw, _ = hb.load_templates(npz, prefix=SUP)
    out = {}
    for k, t in raw.items():
        if not wanted_key(k, spec, family_wide):
            continue
        p = k.split("/")
        m = base + (margins.get(("ent", p[2]), 0.0) if p[1] == "ent" else margins.get((spec.type_key, p[1]), 0.0))
        out[k] = t.dilated(rx=hb.HERO_HALF_U[0] + m, ry=hb.HERO_HALF_U[1] + m, key=k)
    return out


@dataclass(slots=True)
class Tubes:
    """The idle body tube and the current-collider tube's calibration (support_recall: production_tubes): per type
    the idle growth g[1/60 s bin of game time] (u), the top speed (u/s, the growth past the calibrated bins and of
    the collider tube) and the body hull relative to the transform (x0, y0, x1, y1)."""
    growth: dict[str, list[float]]
    speed: dict[str, float]
    hull: dict[str, tuple[float, float, float, float]]

    @classmethod
    def from_doc(cls, d: dict) -> "Tubes":
        return cls({k: list(map(float, v)) for k, v in (d.get("idle_growth") or {}).items()},
                   {k: float(v) for k, v in (d.get("tube_speed") or {}).items()},
                   {k: tuple(map(float, v)) for k, v in (d.get("body_hull") or {}).items()})

    def g(self, tk: str, dt) -> np.ndarray:
        """Idle growth after dt game s since the sighting (the bins of forum_support.tube_bin; past the calibration
        at the type's top speed)."""
        g = self.growth.get(tk)
        dt = np.maximum(np.asarray(dt, np.float64), 0.0)
        if not g:
            return self.speed.get(tk, 60.0) * dt
        k = np.maximum(0, np.ceil(dt / BIN - 0.05)).astype(np.int64)
        n = len(g) - 1
        ga = np.asarray(g, np.float64)
        return np.where(k <= n, ga[np.minimum(k, n)], ga[-1] + self.speed.get(tk, 60.0) * (k - n) * BIN)


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
            for k, t in tpls.items():
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
