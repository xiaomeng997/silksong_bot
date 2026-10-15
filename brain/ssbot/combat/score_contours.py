"""Score contours of a (k, x) score layer (task 1v1 SG3; the person's storage design S7, spec_notes_zh parts 88 / 91 /
96; forum.md 57). SG2's maps (ssbot.combat.special_map) are dense (k, x) arrays per layer; this module stores a layer as
the closed contour rings of its score bands and answers lattice queries from the rings.

Bands. A layer's score s at the lattice point (k, i) (k = frame, i = x lattice index) becomes the integer band
b = floor(s / step) (>= 0; capped at n_levels - 1) or -1 for infeasible / no node (-inf, NaN). Level m (0 .. top) is the
region {b >= m}; level 0 is the feasibility region. The band at a point is the highest level whose region contains it.

Rings (marching squares). Per level the grid is padded with one infeasible cell on every side, so every ring closes.
A ring vertex lies on a lattice edge whose two end values straddle the level (linear interpolation at m - 0.5 between
the end bands); a saddle cell joins its two high corners iff the mean of its four bands is >= m - 0.5 (monotone in m,
so the rings of different levels nest). Coordinates are integers in COORD = 100 units per frame (k) and per lattice
step (x): the lattice points sit on multiples of 100 and no vertex coincides with one (interpolated positions are
distinct for up to 100 levels per edge), so the integer winding test is exact on the lattice.

Orientation: in the plane (X = k, Y = x) the higher band lies on the left of the walking direction: an outer ring (a
high region inside) runs counter-clockwise (signed shoelace area > 0), a hole clockwise (< 0). The builder checks every
ring against the bands at its first edge and reverses a ring that runs the wrong way (count reported; 0 by
construction). A point is in level m's region iff the summed winding number of level m's rings is != 0; the signed
areas of one level sum to the region's net area. The ring tree: parent = the smallest ring that contains the ring.

Simplification (the person's lattice rule): the layer is defined on the lattice only and queries snap to it, so a ring
may move anywhere between lattice points. Greedy Visvalingam-Whyatt vertex removal, each removal accepted only if
  * level 0 (feasibility): no lattice point changes side;
  * inner levels: a lattice point may change side only by one band (tol 1; 0 = exact everywhere), and a point may
    move one way only (never one band down at its own level and one up at the next: the bands stay nested on the
    lattice);
  * no vertex of any ring lies in the removed triangle and no lattice point on the new edge: rings never cross or
    touch, so nesting, siblings' disjointness and the tree are kept (checked again by the tests).
Storage: per ring the level, the point count, the parent, the first point (int32) and the deltas (int16); the MATLAB
contourc two-row layout (header column [level; n], then the points, sorted by level) is available via contourc().
"""
from __future__ import annotations

import heapq
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

try:
    from numba import njit
except Exception:  # noqa: BLE001
    njit = None

COORD = 100                       # integer units per frame (k) and per lattice step (x)


def to_bands(score: np.ndarray, step: float, n_levels: int | None = None) -> np.ndarray:
    """int16 bands: floor(score / step) for finite scores >= 0 (negative finite scores count as 0), -1 otherwise."""
    s = np.asarray(score, np.float64)
    fin = np.isfinite(s)
    b = np.full(s.shape, -1, np.int16)
    v = np.floor(np.maximum(s[fin], 0.0) / step + 1e-9)
    if n_levels is not None:
        v = np.minimum(v, n_levels - 1)
    b[fin] = v.astype(np.int16)
    return b


# ---- marching squares ----
# corners of the square (i, j) in counter-clockwise order in the plane (X = k, Y = x):
# p0 (i, j), p1 (i+1, j), p2 (i+1, j+1), p3 (i, j+1); edges e0 p0-p1, e1 p1-p2, e2 p2-p3, e3 p3-p0.
# A segment runs from the edge where the CCW walk goes high -> low to the edge where it goes low -> high (the high
# side on its left). Saddles: 5 (p0, p2 high), 10 (p1, p3 high); "joined" = the high diagonal connected.
_SEG = {c: [] for c in range(16)}
for _c in range(1, 15):
    if _c in (5, 10):
        continue
    hi = [(_c >> n) & 1 for n in range(4)]
    tf = [n for n in range(4) if hi[n] and not hi[(n + 1) % 4]]
    ft = [n for n in range(4) if not hi[n] and hi[(n + 1) % 4]]
    _SEG[_c] = [(tf[0], ft[0])]
_SADDLE = {(5, True): [(0, 1), (2, 3)], (5, False): [(0, 3), (2, 1)],
           (10, True): [(3, 0), (1, 2)], (10, False): [(1, 0), (3, 2)]}


def _trace_py(succ, starts):
    nE = succ.shape[0]
    seen = np.zeros(nE, np.bool_)
    order = np.empty(starts.shape[0], np.int64)
    ring_start = []
    n = 0
    for s in starts:
        if seen[s]:
            continue
        ring_start.append(n)
        e = s
        while not seen[e]:
            seen[e] = True
            order[n] = e
            n += 1
            e = succ[e]
    ring_start.append(n)
    return order[:n], np.array(ring_start, np.int64)


if njit is not None:
    @njit(cache=True)
    def _trace_nb(succ, starts):
        nE = succ.shape[0]
        seen = np.zeros(nE, np.bool_)
        order = np.empty(starts.shape[0], np.int64)
        ring_start = np.empty(starts.shape[0] + 1, np.int64)
        n = 0
        r = 0
        for s in starts:
            if seen[s]:
                continue
            ring_start[r] = n
            r += 1
            e = s
            while not seen[e]:
                seen[e] = True
                order[n] = e
                n += 1
                e = succ[e]
        ring_start[r] = n
        return order[:n], ring_start[:r + 1]
    _trace = _trace_nb
else:
    _trace = _trace_py


def trace_level(P: np.ndarray, m: int) -> list[np.ndarray]:
    """The rings of level m of the padded band grid P [H, W] (int): int64 [n, 2] (X = k, Y = x) in COORD units of the
    unpadded lattice, the higher bands on the left."""
    H, W = P.shape
    T = P >= m
    v0, v1, v2, v3 = P[:-1, :-1], P[1:, :-1], P[1:, 1:], P[:-1, 1:]
    code = (T[:-1, :-1] * 1 + T[1:, :-1] * 2 + T[1:, 1:] * 4 + T[:-1, 1:] * 8).astype(np.int64)
    ii, jj = np.nonzero((code > 0) & (code < 15))
    if not len(ii):
        return []
    cc = code[ii, jj]
    joined = (v0[ii, jj] + v1[ii, jj] + v2[ii, jj] + v3[ii, jj]).astype(np.float64) / 4.0 >= m - 0.5
    nxe = H * W
    # global edge ids of the local edges e0..e3 of square (i, j)
    eid = np.stack([nxe + ii * W + jj,            # e0: k-edge (i, j)
                    (ii + 1) * W + jj,            # e1: x-edge (i + 1, j)
                    nxe + ii * W + jj + 1,        # e2: k-edge (i, j + 1)
                    ii * W + jj], axis=1)         # e3: x-edge (i, j)
    fr, to = [], []
    for c in range(1, 15):
        if c in (5, 10):
            for jn in (True, False):
                sel = np.flatnonzero((cc == c) & (joined == jn))
                if len(sel):
                    for a, b in _SADDLE[(c, jn)]:
                        fr.append(eid[sel, a])
                        to.append(eid[sel, b])
            continue
        sel = np.flatnonzero(cc == c)
        if len(sel):
            a, b = _SEG[c][0]
            fr.append(eid[sel, a])
            to.append(eid[sel, b])
    fr = np.concatenate(fr)
    to = np.concatenate(to)
    succ = np.full(2 * nxe, -1, np.int64)
    succ[fr] = to
    order, rs = _trace(succ, np.sort(fr))
    # vertex coordinates of the edges
    isx = order < nxe
    e = np.where(isx, order, order - nxe)
    i, j = e // W, e % W
    va = P[i, j].astype(np.float64)
    vb = np.where(isx, P[i, np.minimum(j + 1, W - 1)], P[np.minimum(i + 1, H - 1), j]).astype(np.float64)
    t = (m - 0.5 - va) / (vb - va)
    X = np.where(isx, (i - 1) * COORD, np.rint((i - 1 + t) * COORD)).astype(np.int64)
    Y = np.where(isx, np.rint((j - 1 + t) * COORD), (j - 1) * COORD).astype(np.int64)
    pts = np.stack([X, Y], 1)
    return [pts[rs[r]:rs[r + 1]] for r in range(len(rs) - 1)]


def area2(ring: np.ndarray) -> int:
    """Twice the signed shoelace area (X = k, Y = x); > 0 counter-clockwise."""
    x, y = ring[:, 0], ring[:, 1]
    return int(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def winding(ring: np.ndarray, px, py) -> np.ndarray:
    """Winding number of the points (px, py) (arrays, integer coords) with respect to the closed ring (exact integer
    arithmetic; points on the ring are not expected)."""
    px = np.atleast_1d(np.asarray(px, np.int64))[:, None]
    py = np.atleast_1d(np.asarray(py, np.int64))[:, None]
    x0, y0 = ring[:, 0][None], ring[:, 1][None]
    x1, y1 = np.roll(ring[:, 0], -1)[None], np.roll(ring[:, 1], -1)[None]
    cr = (x1 - x0) * (py - y0) - (px - x0) * (y1 - y0)
    up = (y0 <= py) & (y1 > py) & (cr > 0)
    dn = (y0 > py) & (y1 <= py) & (cr < 0)
    return up.sum(1) - dn.sum(1)


# ---- simplification (greedy Visvalingam-Whyatt under the lattice rule) ----
def _simplify_py(X, Y, ring_of, prv, nxt, ring_lvl, ring_n, bands, state, tol, cell_head, cell_next, ncx, ncy,
                 max_area2):
    """In place on the vertex arrays (alive = prv >= 0). bands [NK, NX] true bands of the lattice, state [NK, NX] int8
    (computed band - true band). Returns the number of removed vertices."""
    NK, NX = bands.shape
    nv = X.shape[0]
    alive = np.ones(nv, np.bool_)
    ver = np.zeros(nv, np.int64)
    heap = [(0.0, np.int64(0), np.int64(0))]
    heap.pop()
    for v in range(nv):
        a, c = prv[v], nxt[v]
        ar = abs(float((X[v] - X[a]) * (Y[c] - Y[a]) - (X[c] - X[a]) * (Y[v] - Y[a])))
        heapq.heappush(heap, (ar, np.int64(v), np.int64(0)))
    removed = 0
    fl_k = np.empty(4096, np.int64)
    fl_x = np.empty(4096, np.int64)
    fl_s = np.empty(4096, np.int64)
    while heap:
        ar, v, vv = heapq.heappop(heap)
        if not alive[v] or vv != ver[v]:
            continue
        if ar > max_area2:
            break
        r = ring_of[v]
        if ring_n[r] <= 3:
            continue
        a, c = prv[v], nxt[v]
        ax, ay, bx, by, cx, cy = X[a], Y[a], X[v], Y[v], X[c], Y[c]
        s = (cx - ax) * (by - ay) - (cy - ay) * (bx - ax)      # > 0: v right of a->c ... sign of cross(c-a, v-a) negated
        # s = cross(v - a, c - a) * -1 ; cross(c - a, v - a) = (cx-ax)*(by-ay) - (cy-ay)*(bx-ax) = s
        # s > 0: v left of a->c: the triangle enters the region (points included); s < 0: excluded
        ok = True
        nfl = 0
        lvl = ring_lvl[r]
        k0 = max(0, (min(ax, bx, cx) + COORD - 1) // COORD) if min(ax, bx, cx) >= 0 else 0
        k1 = min(NK - 1, max(ax, bx, cx) // COORD)
        x0 = max(0, (min(ay, by, cy) + COORD - 1) // COORD) if min(ay, by, cy) >= 0 else 0
        x1 = min(NX - 1, max(ay, by, cy) // COORD)
        if s != 0:
            sg = 1 if s > 0 else -1
            for kk in range(k0, k1 + 1):
                px = kk * COORD
                for xx in range(x0, x1 + 1):
                    py = xx * COORD
                    # on the new edge a-c: forbidden
                    e = (cx - ax) * (py - ay) - (cy - ay) * (px - ax)
                    if e == 0 and min(ax, cx) <= px <= max(ax, cx) and min(ay, cy) <= py <= max(ay, cy):
                        ok = False
                        break
                    # strictly inside the triangle (a, v, c)?
                    d1 = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
                    d2 = (cx - bx) * (py - by) - (cy - by) * (px - bx)
                    d3 = (ax - cx) * (py - cy) - (ay - cy) * (px - cx)
                    if (d1 > 0 and d2 > 0 and d3 > 0) or (d1 < 0 and d2 < 0 and d3 < 0):
                        b = bands[kk, xx]
                        st = state[kk, xx]
                        if sg > 0:                              # included into level lvl
                            if lvl == b + 1 and st == 0 and lvl >= 1 and tol >= 1:
                                ns = 1
                            elif lvl == b and st == -1:
                                ns = 0
                            else:
                                ok = False
                                break
                        else:                                   # excluded from level lvl
                            if lvl == b and st == 0 and lvl >= 1 and tol >= 1:
                                ns = -1
                            elif lvl == b + 1 and st == 1:
                                ns = 0
                            else:
                                ok = False
                                break
                        if nfl >= 4096:
                            ok = False
                            break
                        fl_k[nfl] = kk
                        fl_x[nfl] = xx
                        fl_s[nfl] = ns
                        nfl += 1
                if not ok:
                    break
        else:
            # collinear: v must lie between a and c
            if not (min(ax, cx) <= bx <= max(ax, cx) and min(ay, cy) <= by <= max(ay, cy)):
                ok = False
        if ok:
            # no other vertex in the closed triangle
            gx0 = max(0, (min(ax, bx, cx) // COORD) + 1)
            gx1 = min(ncx - 1, (max(ax, bx, cx) // COORD) + 1)
            gy0 = max(0, (min(ay, by, cy) // COORD) + 1)
            gy1 = min(ncy - 1, (max(ay, by, cy) // COORD) + 1)
            for gx in range(gx0, gx1 + 1):
                for gy in range(gy0, gy1 + 1):
                    w = cell_head[gx * ncy + gy]
                    while w >= 0:
                        if alive[w] and w != a and w != v and w != c:
                            px, py = X[w], Y[w]
                            d1 = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
                            d2 = (cx - bx) * (py - by) - (cy - by) * (px - bx)
                            d3 = (ax - cx) * (py - cy) - (ay - cy) * (px - cx)
                            if (d1 >= 0 and d2 >= 0 and d3 >= 0) or (d1 <= 0 and d2 <= 0 and d3 <= 0):
                                ok = False
                                break
                        w = cell_next[w]
                    if not ok:
                        break
                if not ok:
                    break
        if not ok:
            continue
        for f in range(nfl):
            state[fl_k[f], fl_x[f]] = fl_s[f]
        alive[v] = False
        nxt[a] = c
        prv[c] = a
        prv[v] = -1
        ring_n[r] -= 1
        removed += 1
        for u in (a, c):
            ver[u] += 1
            ua, uc = prv[u], nxt[u]
            au = abs(float((X[u] - X[ua]) * (Y[uc] - Y[ua]) - (X[uc] - X[ua]) * (Y[u] - Y[ua])))
            heapq.heappush(heap, (au, np.int64(u), ver[u]))
    return removed


_simplify = njit(cache=True)(_simplify_py) if njit is not None else _simplify_py


def _inside_lvl(seg, rso, rbb, a, b, px, py):
    """Winding of (px, py) over the rings a..b-1 of one level (ray toward +X): a ring whose bbox misses the ray
    (py outside [ymin, ymax) or px > xmax) is skipped."""
    w = 0
    for r in range(a, b):
        if py < rbb[r, 2] or py >= rbb[r, 3] or px > rbb[r, 1]:
            continue
        for i in range(rso[r], rso[r + 1]):
            x0, y0, x1, y1 = seg[i, 0], seg[i, 1], seg[i, 2], seg[i, 3]
            if y0 <= py:
                if y1 > py and (x1 - x0) * (py - y0) - (px - x0) * (y1 - y0) > 0:
                    w += 1
            elif y1 <= py and (x1 - x0) * (py - y0) - (px - x0) * (y1 - y0) < 0:
                w -= 1
    return w != 0


def _band_query_py(seg, rso, rbb, lvl_off, top, px, py):
    """The band at (px, py) (COORD units): binary search over the nested levels. seg [ns, 4] the segments ring by
    ring, rso [nr + 1] each ring's segment offset, rbb [nr, 4] (xmin, xmax, ymin, ymax), lvl_off [top + 2] each
    level's ring offset (rings sorted by level)."""
    if top < 0 or not _inside_lvl(seg, rso, rbb, lvl_off[0], lvl_off[1], px, py):
        return -1
    lo, hi = 0, top
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _inside_lvl(seg, rso, rbb, lvl_off[mid], lvl_off[mid + 1], px, py):
            lo = mid
        else:
            hi = mid - 1
    return lo


def _tree_py(X, Y, off, bb, ar):
    """parent[i] = the smallest-area ring (larger than i, bbox containing i's) whose winding at i's first vertex != 0."""
    n = off.shape[0] - 1
    parent = np.full(n, -1, np.int32)
    for i in range(n):
        px, py = X[off[i]], Y[off[i]]
        best, ba = -1, np.inf
        for c in range(n):
            if c == i or ar[c] <= ar[i] or ar[c] >= ba:
                continue
            if bb[c, 0] > bb[i, 0] or bb[c, 1] < bb[i, 1] or bb[c, 2] > bb[i, 2] or bb[c, 3] < bb[i, 3]:
                continue
            w = 0
            a0, a1 = off[c], off[c + 1]
            for v in range(a0, a1):
                x0, y0 = X[v], Y[v]
                if v + 1 < a1:
                    x1, y1 = X[v + 1], Y[v + 1]
                else:
                    x1, y1 = X[a0], Y[a0]
                cr = (x1 - x0) * (py - y0) - (px - x0) * (y1 - y0)
                if y0 <= py:
                    if y1 > py and cr > 0:
                        w += 1
                elif y1 <= py and cr < 0:
                    w -= 1
            if w != 0:
                best, ba = c, ar[c]
        parent[i] = best
    return parent


def fill_rows(a: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Rows (frames) with no node are not part of the layer (the lattice rule: nothing is ever queried there); copy
    the nearest earlier valid row into them (the first valid row before the first), so they add no rings."""
    valid = np.asarray(valid, bool)
    if valid.all() or not valid.any():
        return a
    idx = np.where(valid, np.arange(len(valid)), -1)
    idx = np.maximum.accumulate(idx)
    idx[idx < 0] = int(np.flatnonzero(valid)[0])
    return a[idx]


if njit is not None:
    _tree = njit(cache=True)(_tree_py)
    _inside_lvl = njit(cache=True)(_inside_lvl)
else:
    _tree = _tree_py
if njit is not None:
    _band_query = njit(cache=True)(_band_query_py)
else:
    _band_query = _band_query_py


# ---- one layer ----
@dataclass
class ContourLayer:
    nk: int
    nx: int
    step: float                    # score per band
    top: int                       # the highest level present (-1: all infeasible)
    rings: list                    # int64 [n, 2] (X = k, Y = x) in COORD units, sorted by level
    level: np.ndarray              # int16 [n_rings]
    parent: np.ndarray             # int32 [n_rings] (-1: root)
    stats: dict = field(default_factory=dict)
    _lv: dict | None = None        # level -> (segments x0, y0, x1, y1, bbox per ring...)

    # ---- construction ----
    @classmethod
    def from_bands(cls, bands: np.ndarray, step: float, simplify: bool = True, tol: int = 1,
                   max_area_cells: float = 400.0) -> "ContourLayer":
        t0 = time.time()
        B = np.asarray(bands, np.int16)
        nk, nx = B.shape
        top = int(B.max()) if B.size else -1
        P = np.full((nk + 2, nx + 2), -1, np.int64)
        P[1:-1, 1:-1] = B
        if top >= 0:
            jumps = max(int(np.abs(np.diff(P, axis=0)).max()), int(np.abs(np.diff(P, axis=1)).max()))
            if jumps >= COORD:
                raise ValueError(f"a band jump of {jumps} levels on one lattice edge exceeds COORD {COORD}")
        rings, lvls = [], []
        flips = 0
        for m in range(0, top + 1):
            for r in trace_level(P, m):
                # orientation check: the first vertex's edge, its high end must lie on the left
                X0, Y0 = int(r[0, 0]), int(r[0, 1])
                X1, Y1 = int(r[1 % len(r), 0]), int(r[1 % len(r), 1])
                if X0 % COORD == 0:                    # x-edge at k = X0 / COORD
                    k, j = X0 // COORD, Y0 // COORD
                    ends = [(k, j), (k, j + 1)]
                else:
                    k, j = X0 // COORD, Y0 // COORD
                    ends = [(k, j), (k + 1, j)]
                hi = [e for e in ends if 0 <= e[0] < nk and 0 <= e[1] < nx and B[e] >= m]
                if hi:
                    hx, hy = hi[0][0] * COORD, hi[0][1] * COORD
                    if (X1 - X0) * (hy - Y0) - (Y1 - Y0) * (hx - X0) < 0:
                        r = r[::-1].copy()
                        flips += 1
                rings.append(r)
                lvls.append(m)
        lay = cls(nk, nx, step, top, rings, np.array(lvls, np.int16), np.full(len(rings), -1, np.int32))
        n0 = sum(len(r) for r in rings)
        removed = 0
        lay._build_tree()
        tree_kept = True
        if simplify and rings:
            raw_parent = lay.parent.copy()
            removed = lay._simplify(B, tol, max_area_cells)
            lay._build_tree()
            tree_kept = bool((raw_parent == lay.parent).all())
        lay.stats = {"rings": len(rings), "points_raw": n0, "points": sum(len(r) for r in lay.rings),
                     "removed": removed, "orientation_flips": flips, "tree_kept": tree_kept,
                     "seconds": round(time.time() - t0, 4)}
        return lay

    def _simplify(self, B: np.ndarray, tol: int, max_area_cells: float) -> int:
        rings = self.rings
        n = np.array([len(r) for r in rings], np.int64)
        off = np.concatenate([[0], np.cumsum(n)])
        allp = np.concatenate(rings).astype(np.int64)
        X, Y = allp[:, 0].copy(), allp[:, 1].copy()
        nv = len(X)
        ring_of = np.repeat(np.arange(len(rings)), n).astype(np.int64)
        idx = np.arange(nv, dtype=np.int64)
        prv = idx - 1
        nxt = idx + 1
        prv[off[:-1]] = off[1:] - 1
        nxt[off[1:] - 1] = off[:-1]
        # spatial hash of the vertices by cell (shifted by one cell for the padding)
        ncx, ncy = self.nk + 3, self.nx + 3
        gx = np.clip(X // COORD + 1, 0, ncx - 1)
        gy = np.clip(Y // COORD + 1, 0, ncy - 1)
        cell = gx * ncy + gy
        cell_head = np.full(ncx * ncy, -1, np.int64)
        cell_next = np.full(nv, -1, np.int64)
        for v in range(nv):                                  # small python loop: linked lists per cell
            cell_next[v] = cell_head[cell[v]]
            cell_head[cell[v]] = v
        state = np.zeros(B.shape, np.int8)
        ring_lvl = self.level.astype(np.int64)
        ring_n = n.copy()
        removed = _simplify(X, Y, ring_of, prv, nxt, ring_lvl, ring_n, B.astype(np.int64), state, int(tol),
                            cell_head, cell_next, ncx, ncy, float(max_area_cells * COORD * COORD * 2))
        out = []
        for r in range(len(rings)):
            v0 = off[r]
            while prv[v0] < 0:                                # the first vertex may be gone
                v0 += 1
            seq = [v0]
            w = nxt[v0]
            while w != v0:
                seq.append(w)
                w = nxt[w]
            out.append(np.stack([X[seq], Y[seq]], 1))
        self.rings = out
        self._lv = None
        self._fl = None
        return int(removed)

    def _build_tree(self):
        n = len(self.rings)
        self.parent = np.full(n, -1, np.int32)
        if not n:
            return
        bb = self.bbox()
        ar = np.array([abs(area2(r)) for r in self.rings], np.float64)
        P = np.concatenate(self.rings).astype(np.int64)
        off = np.concatenate([[0], np.cumsum([len(r) for r in self.rings])]).astype(np.int64)
        self.parent = _tree(np.ascontiguousarray(P[:, 0]), np.ascontiguousarray(P[:, 1]), off, bb, ar)

    # ---- geometry ----
    def bbox(self) -> np.ndarray:
        """[n, 4] (kmin, kmax, xmin, xmax) in COORD units; the frame range of a ring is kmin..kmax / COORD."""
        if not self.rings:
            return np.zeros((0, 4), np.int64)
        return np.array([[r[:, 0].min(), r[:, 0].max(), r[:, 1].min(), r[:, 1].max()] for r in self.rings], np.int64)

    def areas2(self) -> np.ndarray:
        return np.array([area2(r) for r in self.rings], np.int64)

    def net_area(self) -> dict:
        """Per level the summed signed area (lattice cells; holes subtract)."""
        a = self.areas2()
        return {int(m): float(a[self.level == m].sum()) / 2 / COORD ** 2 for m in np.unique(self.level)}

    def _levels(self):
        if self._lv is None:
            lv = {}
            for m in range(self.top + 1):
                ids = np.flatnonzero(self.level == m)
                if not len(ids):
                    continue
                segs = []
                for i in ids:
                    r = self.rings[i]
                    segs.append(np.concatenate([r, np.roll(r, -1, axis=0)], 1))
                S = np.concatenate(segs).astype(np.int64)            # [ns, 4] x0 y0 x1 y1
                # sort by min X for the row scans
                lo = np.minimum(S[:, 0], S[:, 2])
                hi = np.maximum(S[:, 0], S[:, 2])
                lv[m] = (S, lo, hi)
            self._lv = lv
        return self._lv

    # ---- queries (lattice) ----
    def _inside(self, m: int, px: int, py: int) -> bool:
        lv = self._levels().get(m)
        if lv is None:
            return False
        S, lo, hi = lv
        sel = (S[:, 1] <= py) != (S[:, 3] <= py)                    # the segment straddles Y = py
        if not sel.any():
            return False
        s = S[sel]
        cr = (s[:, 2] - s[:, 0]) * (py - s[:, 1]) - (px - s[:, 0]) * (s[:, 3] - s[:, 1])
        up = (s[:, 1] <= py) & (cr > 0)
        dn = (s[:, 1] > py) & (cr < 0)
        return int(up.sum()) - int(dn.sum()) != 0

    def _flat(self):
        if getattr(self, "_fl", None) is None:
            order = np.argsort(self.level, kind="stable")             # rings by level (already sorted when built)
            rings = [self.rings[i] for i in order]
            n = np.array([len(r) for r in rings], np.int64)
            seg = (np.concatenate([np.concatenate([r, np.roll(r, -1, axis=0)], 1) for r in rings]).astype(np.int64)
                   if rings else np.zeros((0, 4), np.int64))
            rso = np.concatenate([[0], np.cumsum(n)]).astype(np.int64)
            rbb = (np.array([[r[:, 0].min(), r[:, 0].max(), r[:, 1].min(), r[:, 1].max()] for r in rings], np.int64)
                   if rings else np.zeros((0, 4), np.int64))
            lv = self.level[order].astype(np.int64)
            lvl_off = np.searchsorted(lv, np.arange(self.top + 2)).astype(np.int64)
            self._fl = (np.ascontiguousarray(seg), rso, np.ascontiguousarray(rbb), lvl_off)
        return self._fl

    def query(self, k: int, xi: int) -> int:
        """The band at the lattice point (k, xi) (compiled winding test + binary search on the level); -1 outside."""
        if not (0 <= k < self.nk and 0 <= xi < self.nx) or self.top < 0:
            return -1
        seg, rso, rbb, lvl_off = self._flat()
        return int(_band_query(seg, rso, rbb, lvl_off, self.top, k * COORD, xi * COORD))

    def band(self, k: int, xi: int) -> int:
        """The band at the lattice point (k, xi) by a binary search on the level (the regions are nested; the numpy
        reference of query())."""
        if not (0 <= k < self.nk and 0 <= xi < self.nx) or self.top < 0:
            return -1
        px, py = k * COORD, xi * COORD
        if not self._inside(0, px, py):
            return -1
        lo, hi = 0, self.top                                          # inside(lo) holds
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self._inside(mid, px, py):
                lo = mid
            else:
                hi = mid - 1
        return lo

    def row(self, k: int) -> np.ndarray:
        """[nx] bands of frame k by a scan line (every level's crossings with X = k)."""
        out = np.full(self.nx, -1, np.int16)
        if not 0 <= k < self.nk:
            return out
        px = k * COORD
        ys = np.arange(self.nx) * COORD
        for m, (S, lo, hi) in sorted(self._levels().items()):
            sel = (S[:, 0] <= px) != (S[:, 2] <= px)
            if not sel.any():
                break
            s = S[sel]
            # crossing Y of each segment with X = px; direction: +1 if X increases
            t = (px - s[:, 0]) / (s[:, 2] - s[:, 0])
            yc = s[:, 1] + t * (s[:, 3] - s[:, 1])
            d = np.where(s[:, 2] > s[:, 0], 1, -1)
            # winding of (px, y) for the ray toward -Y ... use the count of crossings below y with signs
            o = np.argsort(yc)
            yc, d = yc[o], d[o]
            # a point (px, py) is inside iff the signed count of crossings with yc < py is != 0
            cum = np.concatenate([[0], np.cumsum(d)])
            pos = np.searchsorted(yc, ys, side="left")
            ins = cum[pos] != 0
            out[ins] = m
            if not ins.any():
                break
        return out

    def dense(self) -> np.ndarray:
        """[nk, nx] bands of every lattice point: per level the winding numbers by a difference array along x (each
        segment adds its direction to the points above its crossing with every frame line it spans)."""
        out = np.full((self.nk, self.nx), -1, np.int16)
        for m, (S, lo, hi) in sorted(self._levels().items()):
            k0 = -(-lo // COORD)                                       # ceil(lo / COORD): first frame line >= lo
            k1 = -(-hi // COORD)                                       # lines < hi
            n = np.maximum(k1 - k0, 0)
            if not n.sum():
                continue
            si = np.repeat(np.arange(len(S)), n)
            kk = np.repeat(k0, n) + (np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n))
            s = S[si]
            px = kk * COORD
            yc = s[:, 1] + (px - s[:, 0]) * (s[:, 3] - s[:, 1]) / (s[:, 2] - s[:, 0])
            d = np.where(s[:, 2] > s[:, 0], 1, -1)
            ok = (kk >= 0) & (kk < self.nk)
            xi = np.clip(np.floor(yc / COORD).astype(np.int64) + 1, 0, self.nx)
            diff = np.zeros((self.nk, self.nx + 1), np.int64)
            np.add.at(diff, (kk[ok], xi[ok]), d[ok])
            ins = np.cumsum(diff, axis=1)[:, :self.nx] != 0
            out[ins] = m
        return out

    # ---- the contourc layout and the encoding ----
    def contourc(self) -> np.ndarray:
        """int64 [2, n_rings + n_points]: per ring a header column [level; n] followed by its points (k; x) in COORD
        units, the rings sorted by level (MATLAB contourc's two-row layout)."""
        cols = []
        for m, r in zip(self.level, self.rings):
            cols.append(np.array([[m], [len(r)]], np.int64))
            cols.append(r.T.astype(np.int64))
        return np.concatenate(cols, 1) if cols else np.zeros((2, 0), np.int64)

    def encode(self) -> dict:
        n = np.array([len(r) for r in self.rings], np.int32)
        first = np.array([r[0] for r in self.rings], np.int32).reshape(-1, 2)
        d = [np.diff(r, axis=0) for r in self.rings]
        D = np.concatenate(d).astype(np.int64) if d else np.zeros((0, 2), np.int64)
        if D.size and np.abs(D).max() > 32767:
            raise ValueError("delta out of int16 range")
        return {"n": n, "level": self.level.astype(np.int16), "parent": self.parent.astype(np.int32), "first": first,
                "delta": D.astype(np.int16)}

    @classmethod
    def decode(cls, e: dict, nk: int, nx: int, step: float, top: int) -> "ContourLayer":
        rings = []
        o = 0
        for i, n in enumerate(e["n"]):
            n = int(n)
            r = np.empty((n, 2), np.int64)
            r[0] = e["first"][i]
            if n > 1:
                r[1:] = r[0] + np.cumsum(e["delta"][o:o + n - 1].astype(np.int64), axis=0)
            o += n - 1
            rings.append(r)
        return cls(nk, nx, step, top, rings, np.asarray(e["level"], np.int16), np.asarray(e["parent"], np.int32))


# ---- a set of layers in one file ----
class ContourSet:
    """Named layers sharing (nk, nx, step); saved as one npz: concatenated encodings + per-layer offsets."""

    def __init__(self, nk: int, nx: int, step: float, meta: dict | None = None):
        self.nk, self.nx, self.step = nk, nx, step
        self.meta = meta or {}
        self.layers: dict[str, ContourLayer] = {}

    def add(self, name: str, lay: ContourLayer):
        self.layers[name] = lay

    def prepare(self) -> float:
        """Build every layer's query arrays now (else on its first query); returns the seconds it took."""
        t0 = time.time()
        for lay in self.layers.values():
            lay._flat()
        return time.time() - t0

    def save(self, path: Path) -> dict:
        names = list(self.layers)
        enc = [self.layers[nm].encode() for nm in names]
        cat = {}
        for key in ("n", "level", "parent", "first", "delta"):
            parts = [e[key] for e in enc]
            cat[key] = np.concatenate(parts) if parts else np.zeros(0)
        nring = np.array([len(e["n"]) for e in enc], np.int64)
        npt = np.array([len(e["delta"]) for e in enc], np.int64)
        top = np.array([self.layers[nm].top for nm in names], np.int32)
        meta = dict(self.meta, nk=self.nk, nx=self.nx, step=self.step, coord=COORD, names=names)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, n=cat["n"].astype(np.int32), level=cat["level"].astype(np.int16),
                            parent=cat["parent"].astype(np.int32), first=cat["first"].astype(np.int32).reshape(-1, 2),
                            delta=cat["delta"].astype(np.int16).reshape(-1, 2), nring=nring, npt=npt, top=top,
                            meta=json.dumps(meta))
        return {"bytes": Path(path).stat().st_size, "rings": int(nring.sum()), "points": int(cat["n"].sum())}

    @classmethod
    def load(cls, path: Path) -> "ContourSet":
        z = np.load(path, allow_pickle=False)
        meta = json.loads(str(z["meta"]))
        cs = cls(meta["nk"], meta["nx"], meta["step"], meta)
        ro = np.concatenate([[0], np.cumsum(z["nring"])])
        po = np.concatenate([[0], np.cumsum(z["npt"])])
        n, level, parent, first, delta = z["n"], z["level"], z["parent"], z["first"], z["delta"]
        for li, nm in enumerate(meta["names"]):
            a, b = ro[li], ro[li + 1]
            e = {"n": n[a:b], "level": level[a:b], "parent": parent[a:b], "first": first[a:b],
                 "delta": delta[po[li]:po[li + 1]]}
            cs.layers[nm] = ContourLayer.decode(e, cs.nk, cs.nx, cs.step, int(z["top"][li]))
        return cs


__all__ = ["COORD", "to_bands", "trace_level", "area2", "winding", "ContourLayer", "ContourSet"]
