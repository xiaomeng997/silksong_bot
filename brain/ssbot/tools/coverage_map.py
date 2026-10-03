"""Coverage map and safe pockets (DESIGN §3.5.7: "coverage map = the union of every reachable hitbox over the enemies'
reachable positions; its complement is the verifiable set of safe points"; M2 W8 Forum: "the top of the left wall is
out of reach of the last wave's Choir Clappers").

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.coverage_map <run dir or recording> [...] [--instances 0,1]
        [--episodes 20] [--types "Bone Beast,BoneBeast DropBell L"] [--margin 0.3] [--res 0.05]
        [--json out.json] [--png out.png]

From recordings: every recorded frame's enemy damage colliders (STATE ents, ssbot.ipc.ents.is_threat: enabled, can
cause damage, nonzero damage; hidden entities included), rasterized at --res into one occupancy grid per (enemy
type_key, attack), the attack being the entity's Control FSM state (or its first FSM's). The union over all frames is
the support of that attack as logged: where its hitbox has ever been. The raster is conservative: a cell is marked
when the shape meets it at all (cell-centre fill plus every cell the outline passes through, so slivers thinner than a
cell, 2-point and edge colliders are kept), circles use the oracle's circumscribed octagon, capsules their arcs pushed
out to circumscribe, and each collider also marks the area it swept since the previous frame (vertices moving
linearly; the physics step between two logged frames is not logged), so a box that overlaps a logged shape or its
sweep never reads a positive clearance. Queried for candidate hero positions, each with the hero hurtbox of that pose:
  stand  the hero standing on every floor segment of the scene's terrain (TERRAIN, the room-entry dump), x every
         --step, HeroBox normal;
  wall   the wall slide / cling poses against every wall face that can hold one (kin_jit.facing_near_wall: 1.5 u of
         wall around hero.pos), the hero collider skin off the face, y every --step from where the box bottom touches
         the face's bottom to where its centre leaves the top (the highest cling), HeroBox wall slide;
  air    optional (--air): a grid of free points (HeroBox normal).
HeroBox (the hero's damage receiver, HeroBox.cs: HeroBoxNormal 0.4554 x 2.2498 at (0, -0.3799) from the hero
transform, HeroBoxWallSlide 0.8757 x 1.2805 at (0.2101, -0.2755), x mirrored by the facing; the transform is hero.pos,
1.5527 above the collider bottom). For each point and each group: the clearance, the Euclidean gap between the
hurtbox and the group's union (negative: inside, by how much the box would have to shrink); a point is safe when
every group's clearance is at least --margin. Output: per group the frames seen and area covered; per point the
clearance and the closest attacks; the safe points (the pockets), best first, and per wall face its highest cling
point's clearance.

This is the logged support (what was seen), not a proof: an attack never logged near a pocket can still reach it;
the forecast's own support (behaviour tables) is the planner's check. Use it to choose and verify pockets with data,
then confirm with the planner's forecast at those points.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from numba import njit

HERO_FOOT = 1.5527            # hero.pos (transform) above the collider bottom (kinematics.HeroParams.foot)
HERO_HW = 0.25
HERO_SKIN = 0.015
# HeroBox.cs (local to the hero transform; x mirrored by the facing): (offset x, offset y, width, height)
HB_NORMAL = (0.0, -0.3799, 0.4554, 2.2498)
HB_WALL = (0.2101475, -0.2755051, 0.875695, 1.280464)
# a threat outline moving further than this between two consecutive frames was placed, not moved (respawn, warp):
# no sweep (the Bell Beast's colliders move at most 1.23 u per frame)
SWEEP_MAX = 3.0


# ---- rasterizing ------------------------------------------------------------------------------------------------

@njit(cache=True)
def _mark_segment(grid, x0, y0, res, ax, ay, bx, by):
    """Every cell the segment passes through (supercover): samples res / 4 apart move at most one cell per axis
    between them; a step that changes both indices marks both cells beside the corner it cut."""
    ny, nx = grid.shape
    n = int(math.ceil(math.hypot(bx - ax, by - ay) / (0.25 * res))) + 1
    pi = -(1 << 40)
    pj = -(1 << 40)
    for k in range(n + 1):
        t = k / n
        i = int(math.floor((ax + t * (bx - ax) - x0) / res))
        j = int(math.floor((ay + t * (by - ay) - y0) / res))
        if k > 0 and i != pi and j != pj:
            if 0 <= pi < nx and 0 <= j < ny:
                grid[j, pi] = True
            if 0 <= i < nx and 0 <= pj < ny:
                grid[pj, i] = True
        if 0 <= i < nx and 0 <= j < ny:
            grid[j, i] = True
        pi = i
        pj = j


@njit(cache=True)
def _fill_poly(grid, x0, y0, res, P, closed):
    """Every cell the polygon P [n, 2] meets: even-odd scanline fill of the cells whose centre is inside, plus every
    cell its outline passes through, so a cell that meets the polygon is never left free (a cell that meets it
    either holds a piece of the outline or lies wholly inside). closed False: an open chain (EdgeCollider2D), its
    segments only."""
    ny, nx = grid.shape
    n = P.shape[0]
    if closed and n >= 3:
        ymin, ymax = P[:, 1].min(), P[:, 1].max()
        j0 = max(int(math.floor((ymin - y0) / res - 0.5)), 0)
        j1 = min(int(math.ceil((ymax - y0) / res - 0.5)), ny - 1)
        xs = np.empty(n)
        for j in range(j0, j1 + 1):
            yc = y0 + (j + 0.5) * res
            m = 0
            for i in range(n):
                ax, ay = P[i, 0], P[i, 1]
                bx, by = P[(i + 1) % n, 0], P[(i + 1) % n, 1]
                if (ay > yc) != (by > yc):
                    xs[m] = ax + (yc - ay) * (bx - ax) / (by - ay)
                    m += 1
            xs[:m].sort()
            for k in range(0, m - 1, 2):
                i0 = max(int(math.ceil((xs[k] - x0) / res - 0.5)), 0)
                i1 = min(int(math.floor((xs[k + 1] - x0) / res - 0.5)), nx - 1)
                for i in range(i0, i1 + 1):
                    grid[j, i] = True
    last = n if (closed and n >= 3) else n - 1
    for i in range(last):
        _mark_segment(grid, x0, y0, res, P[i, 0], P[i, 1], P[(i + 1) % n, 0], P[(i + 1) % n, 1])
    if n == 1:
        _mark_segment(grid, x0, y0, res, P[0, 0], P[0, 1], P[0, 0], P[0, 1])


def outline(c: dict) -> tuple[np.ndarray, bool] | None:
    """A threat collider's world outline (points [n, 2], closed) that covers its shape: the oracle's circle octagon
    already circumscribes the circle (ColliderGeometry.AppendCircle); a capsule's two 5-point arcs lie on its circles,
    so they are pushed out from their centres to circumscribe them (the chords would cut up to 0.076 r off); an edge
    collider is an open chain."""
    v = np.asarray(c.get("verts_world") or (), dtype=np.float64).reshape(-1, 2)
    if not len(v):
        return None
    kind = c.get("kind")
    if kind == "edge":
        return v, False
    if kind == "capsule" and len(v) == 10:
        v = v.copy()
        for a in (0, 5):
            cen = 0.5 * (v[a] + v[a + 4])
            v[a:a + 5] = cen + (v[a:a + 5] - cen) / math.cos(math.pi / 8)
    return v, len(v) >= 3


def convex_hull(pts: np.ndarray) -> np.ndarray:
    """Andrew's monotone chain, counter-clockwise, no repeated end point."""
    q = np.unique(np.round(pts, 9), axis=0)
    if len(q) < 3:
        return q

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lo: list = []
    for p in q:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    hi: list = []
    for p in q[::-1]:
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return np.array(lo[:-1] + hi[:-1])


@njit(cache=True)
def _hull4(Q):
    """Convex hull (gift wrapping) of a handful of points Q [m, 2], counter-clockwise."""
    m = Q.shape[0]
    out = np.empty((m, 2))
    start = 0
    for i in range(1, m):
        if Q[i, 0] < Q[start, 0] or (Q[i, 0] == Q[start, 0] and Q[i, 1] < Q[start, 1]):
            start = i
    h = 0
    cur = start
    while True:
        out[h] = Q[cur]
        h += 1
        nxt = (cur + 1) % m
        for i in range(m):
            cr = (Q[nxt, 0] - Q[cur, 0]) * (Q[i, 1] - Q[cur, 1]) - (Q[nxt, 1] - Q[cur, 1]) * (Q[i, 0] - Q[cur, 0])
            if cr < 0 or (cr == 0 and (Q[i, 0] - Q[cur, 0]) ** 2 + (Q[i, 1] - Q[cur, 1]) ** 2 >
                          (Q[nxt, 0] - Q[cur, 0]) ** 2 + (Q[nxt, 1] - Q[cur, 1]) ** 2):
                nxt = i
        cur = nxt
        if cur == start or h >= m:
            break
    return out[:h]


@njit(cache=True)
def _fill_swept(grid, x0, y0, res, A, B, closed):
    """The area a collider outline swept between two frames, its vertices moving linearly from A to B (same order):
    the outline at B (A was marked with its own frame) and, per edge, the convex hull of the edge's four end points,
    which holds every intermediate position of that edge (the region the outline swept is bounded by them)."""
    n = A.shape[0]
    _fill_poly(grid, x0, y0, res, B, closed)
    last = n if (closed and n >= 3) else n - 1
    Q = np.empty((4, 2))
    for i in range(max(last, 1 if n == 1 else 0)):
        k = (i + 1) % n
        Q[0] = A[i]
        Q[1] = A[k]
        Q[2] = B[k]
        Q[3] = B[i]
        H = _hull4(Q)
        _fill_poly(grid, x0, y0, res, H, H.shape[0] >= 3)


@njit(cache=True)
def _clearance(grid, x0, y0, res, bx0, by0, bx1, by1, edge_i, edge_j):
    """Euclidean gap between the box (bx0, by0, bx1, by1) and the occupied cells (as res squares); negative when the
    box covers an occupied cell: minus the depth (the largest gap inside, measured the same way from the outside
    cells... approximated by -res times the number of occupied cells' rows it would have to give up, at least -res)."""
    ny, nx = grid.shape
    i0 = max(int(math.floor((bx0 - x0) / res)), 0)
    i1 = min(int(math.floor((bx1 - x0) / res)), nx - 1)
    j0 = max(int(math.floor((by0 - y0) / res)), 0)
    j1 = min(int(math.floor((by1 - y0) / res)), ny - 1)
    inside = 0
    for j in range(j0, j1 + 1):
        for i in range(i0, i1 + 1):
            if grid[j, i]:
                inside += 1
    if inside > 0:
        return -res * math.sqrt(inside)
    best = 1e9
    for q in range(edge_i.shape[0]):
        cx0 = x0 + edge_i[q] * res
        cy0 = y0 + edge_j[q] * res
        dx = max(cx0 - bx1, bx0 - (cx0 + res), 0.0)
        dy = max(cy0 - by1, by0 - (cy0 + res), 0.0)
        d = math.sqrt(dx * dx + dy * dy)
        if d < best:
            best = d
    return best


def _boundary(grid: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(i, j) of occupied cells with a free 4-neighbour (or on the grid's edge)."""
    g = grid
    pad = np.pad(g, 1, constant_values=False)
    inner = pad[1:-1, :-2] & pad[1:-1, 2:] & pad[:-2, 1:-1] & pad[2:, 1:-1]
    e = g & ~inner
    j, i = np.nonzero(e)
    return i.astype(np.int64), j.astype(np.int64)


# ---- the map ----------------------------------------------------------------------------------------------------

@dataclass
class Group:
    type_key: str
    attack: str
    frames: int = 0
    colliders: int = 0
    grid: np.ndarray | None = None
    edge: tuple | None = None


@dataclass
class CoverageMap:
    x0: float
    y0: float
    x1: float
    y1: float
    res: float
    groups: dict = field(default_factory=dict)      # (type_key, attack) -> Group
    frames: int = 0
    sources: list = field(default_factory=list)
    swept: int = 0                    # outlines rasterized with their sweep from the previous frame
    teleports: int = 0                # outlines that jumped more than SWEEP_MAX in a frame (no sweep)
    _prev: dict = field(default_factory=dict, repr=False)
    _prev_f: int | None = None

    def shape(self) -> tuple[int, int]:
        return int(math.ceil((self.y1 - self.y0) / self.res)), int(math.ceil((self.x1 - self.x0) / self.res))

    def group(self, tk: str, attack: str) -> Group:
        g = self.groups.get((tk, attack))
        if g is None:
            g = self.groups[(tk, attack)] = Group(tk, attack, grid=np.zeros(self.shape(), dtype=np.bool_))
        return g

    def add_state(self, s: dict, fsm_name: str = "Control", types: set | None = None) -> int:
        """Rasterize one STATE's threat colliders, and the area each swept since the previous frame (a collider
        seen in frame f - 1 under the same entity, index, kind and vertex count, moved by at most SWEEP_MAX: a
        frame holds up to two 50 Hz physics steps, and the step between two logged frames is where the outline
        passed, not where it was logged); returns how many were added. Hidden entities count too (an enabled
        damage collider hurts whether or not the renderer is on)."""
        from ssbot.ipc.ents import is_threat
        n = 0
        seen = set()
        f = s.get("f")
        cur: dict = {}
        for ei, e in enumerate(s.get("ents") or ()):
            tk = e.get("type_key") or "?"
            if types and tk not in types:
                continue
            cols = [(ci, c) for ci, c in enumerate(e.get("colliders") or ()) if is_threat(c)]
            if not cols:
                continue
            fs = e.get("fsms") or []
            fm = next((x for x in fs if x.get("name") == fsm_name), fs[0] if fs else None)
            g = self.group(tk, str(fm.get("state")) if fm else "-")
            if (tk, g.attack) not in seen:
                g.frames += 1
                seen.add((tk, g.attack))
            for ci, c in cols:
                o = outline(c)
                if o is None:
                    continue
                v, closed = o
                v = np.ascontiguousarray(v)
                key = (e.get("iid", ei), ci, c.get("kind"), len(v))
                cur[key] = (v, closed)
                prev = self._prev.get(key) if (f is not None and self._prev_f is not None and
                                               f == self._prev_f + 1) else None
                if prev is not None and float(np.abs(prev[0] - v).max()) <= SWEEP_MAX:
                    _fill_swept(g.grid, self.x0, self.y0, self.res, prev[0], v, closed)
                    self.swept += 1
                else:
                    _fill_poly(g.grid, self.x0, self.y0, self.res, v, closed)
                    self.teleports += int(prev is not None)
                g.colliders += 1
                n += 1
        self._prev, self._prev_f = cur, f
        self.frames += 1
        return n

    def finish(self) -> None:
        for g in self.groups.values():
            g.edge = _boundary(g.grid)

    def extent(self, pad: float = 0.0) -> tuple[float, float, float, float]:
        """(x0, y0, x1, y1) of every occupied cell of every group, grown by pad."""
        occ = np.zeros(self.shape(), dtype=bool)
        for g in self.groups.values():
            occ |= g.grid
        j, i = np.nonzero(occ)
        if not len(i):
            return self.x0, self.y0, self.x1, self.y1
        return (self.x0 + i.min() * self.res - pad, self.y0 + j.min() * self.res - pad,
                self.x0 + (i.max() + 1) * self.res + pad, self.y0 + (j.max() + 1) * self.res + pad)

    def clearance(self, box: tuple[float, float, float, float]) -> dict:
        """(type_key, attack) -> clearance of the box (x0, y0, x1, y1)."""
        out = {}
        for k, g in self.groups.items():
            if g.edge is None:
                g.edge = _boundary(g.grid)
            if not len(g.edge[0]):
                continue
            out[k] = float(_clearance(g.grid, self.x0, self.y0, self.res, *box, g.edge[0], g.edge[1]))
        return out


def hurtbox(px: float, py: float, face: int, kind: str = "normal") -> tuple[float, float, float, float]:
    """HeroBox in world (x0, y0, x1, y1) for the hero transform (px, py) and facing (+1 right)."""
    ox, oy, w, h = HB_WALL if kind == "wall" else HB_NORMAL
    cx = px - face * ox             # local +x is the hero's left-facing forward (localScale.x = +1 facing left)
    cy = py + oy
    return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2


# ---- candidate points -------------------------------------------------------------------------------------------

def candidate_points(terrain, x0: float, x1: float, y0: float, y1: float, step: float = 0.25, air: bool = False
                     ) -> list[dict]:
    """Hero poses to query: standing on floors, wall slide / cling poses, optionally a free-air grid. Each: kind,
    pos (hero transform), face, box (HeroBox)."""
    from ssbot.knowledge import kin_jit
    from ssbot.knowledge.kinematics import HeroParams
    p = HeroParams()
    TT = terrain.packed()
    pts: list[dict] = []
    for y, a, b in terrain.hseg:
        if not (y0 <= y <= y1) or b < x0 or a > x1:
            continue
        for x in np.arange(max(a, x0) + p.half_width, min(b, x1) - p.half_width + 1e-9, step):
            py = y + p.skin + p.foot
            if kin_jit.on_ground(x, py, p.half_width, p.skin, p.foot, TT) and not _inside_solid(terrain, x, py, p):
                pts.append({"kind": "stand", "pos": [float(x), float(py)], "face": 1,
                            "box": hurtbox(x, py, 1, "normal")})
    for xw, ya, yb in terrain.vseg:
        if not (x0 - 1 <= xw <= x1 + 1) or yb - ya < 1.0:
            continue
        for side in (-1.0, 1.0):           # side: where the wall is relative to the hero
            px = xw - side * (p.half_width + p.skin)
            if not (x0 <= px <= x1):
                continue
            # the box bottom at the face's bottom ... the box centre at the face's top
            lo = ya + p.foot
            hi = yb - 0.5 * (p.head - p.foot)
            for py in np.arange(lo, hi + 1e-9, step):
                if not (y0 <= py <= y1):
                    continue
                if not kin_jit.facing_near_wall(px, py, side, p.wall_ray, TT):
                    continue
                if not kin_jit.wall_near(px, py, side, p.skin + p.wall_contact, kin_jit_params(p), TT):
                    continue
                if _inside_solid(terrain, px, py, p):
                    continue
                pts.append({"kind": "wall", "pos": [float(px), float(py)], "face": int(side), "wall": float(xw),
                            "top": float(yb), "box": hurtbox(px, py, int(side), "wall")})
    if air:
        for x in np.arange(x0, x1, step * 2):
            for y in np.arange(y0, y1, step * 2):
                if not _inside_solid(terrain, x, y, p):
                    pts.append({"kind": "air", "pos": [float(x), float(y)], "face": 1,
                                "box": hurtbox(x, y, 1, "normal")})
    seen, out = set(), []
    for q in pts:                     # outlines of adjacent solids repeat segments
        key = (q["kind"], round(q["pos"][0], 3), round(q["pos"][1], 3), q["face"])
        if key not in seen:
            seen.add(key)
            out.append(q)
    return out


def kin_jit_params(p) -> np.ndarray:
    return p.vector()


def _inside_solid(terrain, x: float, y: float, p) -> bool:
    """The hero collider at transform (x, y) overlaps a floor or wall segment (crosses terrain)."""
    bx0, by0, bx1, by1 = x - p.half_width, y - p.foot, x + p.half_width, y + p.head
    h = terrain.hseg
    if len(h) and ((h[:, 0] > by0 + 1e-3) & (h[:, 0] < by1 - 1e-3) & (h[:, 1] < bx1 - 1e-3) & (h[:, 2] > bx0 + 1e-3)).any():
        return True
    v = terrain.vseg
    if len(v) and ((v[:, 0] > bx0 + 1e-3) & (v[:, 0] < bx1 - 1e-3) & (v[:, 1] < by1 - 1e-3) &
                   (v[:, 2] > by0 + 1e-3)).any():
        return True
    # wholly inside a solid: the outlines are closed, so a ray to +x from the box centre crosses an odd number of
    # wall or slope segments
    cx, cy = 0.5 * (bx0 + bx1), 0.5 * (by0 + by1)
    n = int(((v[:, 0] > cx) & (v[:, 1] <= cy) & (v[:, 2] > cy)).sum()) if len(v) else 0
    for xa, ya, xb, yb in terrain.slopes:
        if (ya > cy) != (yb > cy) and cx < xa + (cy - ya) * (xb - xa) / (yb - ya):
            n += 1
    return n % 2 == 1


# ---- building from recordings -----------------------------------------------------------------------------------

def recordings(paths: list[Path], instances: list[int], episodes: int) -> list[tuple[Path, int | None, int | None]]:
    """(recording, f0, f1) to read: a run dir's episodes (attempts_i<k>.jsonl, HARNESS_FAIL skipped) or a recording
    as a whole."""
    from ssbot.tools.postmortem import episode_rows, find_recording
    out = []
    for p in paths:
        if (p / "meta.json").exists() and (p / "state.index.jsonl").exists():
            out.append((p, None, None))
            continue
        for k in instances:
            if not (p / f"attempts_i{k}.jsonl").exists():
                continue
            rows = [r for r in episode_rows(p, k) if r.get("recording") and r.get("outcome") != "HARNESS_FAIL"]
            for r in rows[:episodes]:
                out.append((find_recording(p, r), r["f_end"] - r["acts"], r["f_end"]))
    return out


def build(srcs: list[tuple[Path, int | None, int | None]], bounds: tuple[float, float, float, float], res: float,
          types: set | None, fsm: str) -> tuple[CoverageMap, dict | None, str | None]:
    """The coverage map of the given recording spans, and the TERRAIN payload / scene of the first one."""
    from ssbot.record.recorder import RecordingReader
    cm = CoverageMap(*bounds, res)
    terrain_msg, scene = None, None
    for path, f0, f1 in srcs:
        rr = RecordingReader(path)
        for s in rr.states(f0, f1, keys=("ents", "game")):
            sc = (s.get("game") or {}).get("scene")
            if scene is None and sc:
                scene = sc
            if sc == scene:
                cm.add_state(s, fsm, types)
        if terrain_msg is None:
            for _, msg in rr.terrain():
                if isinstance(msg, dict) and msg.get("scene_raw", msg.get("scene")) == scene:
                    terrain_msg = msg
        cm.sources.append({"recording": str(path), "f0": f0, "f1": f1})
    cm.finish()
    return cm, terrain_msg, scene


def evaluate(cm: CoverageMap, pts: list[dict], margin: float, top: int = 3) -> list[dict]:
    for q in pts:
        c = cm.clearance(tuple(q["box"]))
        q["clearance"] = min(c.values()) if c else float("inf")
        q["closest"] = [{"type_key": k[0], "attack": k[1], "clearance": round(v, 3)}
                        for k, v in sorted(c.items(), key=lambda kv: kv[1])[:top]]
        q["safe"] = bool(q["clearance"] >= margin)
    return pts


def render_png(cm: CoverageMap, pts: list[dict], terrain, path: Path, scale: int = 20) -> None:
    import cv2
    ny, nx = cm.shape()
    union = np.zeros((ny, nx), dtype=np.uint8)
    for g in cm.groups.values():
        union = np.maximum(union, g.grid.astype(np.uint8))
    img = np.full((ny, nx, 3), 255, dtype=np.uint8)
    img[union > 0] = (80, 80, 230)
    img = cv2.resize(img[::-1], (int((cm.x1 - cm.x0) * scale), int((cm.y1 - cm.y0) * scale)),
                     interpolation=cv2.INTER_NEAREST)

    def px(x, y):
        return int((x - cm.x0) * scale), int((cm.y1 - y) * scale)

    if terrain is not None:
        for y, a, b in terrain.hseg:
            cv2.line(img, px(a, y), px(b, y), (0, 0, 0), 1)
        for x, a, b in terrain.vseg:
            cv2.line(img, px(x, a), px(x, b), (0, 0, 0), 1)
    for q in pts:
        col = (0, 170, 0) if q["safe"] else (0, 0, 0) if q["clearance"] < 0 else (0, 165, 255)
        cv2.circle(img, px(*q["pos"]), 2, col, -1)
    cv2.imwrite(str(path), img)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--instances", default="0,1,2,3")
    ap.add_argument("--episodes", type=int, default=10)
    ap.add_argument("--types", default="", help="comma-separated type_keys (default: every enemy with threats)")
    ap.add_argument("--fsm", default="Control")
    ap.add_argument("--bounds", type=float, nargs=4, default=None, help="x0 y0 x1 y1 (default: the terrain's)")
    ap.add_argument("--res", type=float, default=0.05)
    ap.add_argument("--step", type=float, default=0.25)
    ap.add_argument("--margin", type=float, default=0.3)
    ap.add_argument("--pad", type=float, default=3.0, help="candidates this far around the threats' extent")
    ap.add_argument("--air", action="store_true")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--png", type=Path, default=None)
    a = ap.parse_args(argv)
    from ssbot.knowledge.kinematics import HeroParams, Terrain2D
    srcs = recordings(a.paths, [int(x) for x in a.instances.split(",")], a.episodes)
    if not srcs:
        print("no recordings")
        return 1
    types = {t.strip() for t in a.types.split(",") if t.strip()} or None
    bounds = tuple(a.bounds) if a.bounds else (-200.0, -50.0, 400.0, 200.0)
    if a.bounds is None:              # bounds from the first recording's terrain
        from ssbot.record.recorder import RecordingReader
        rr = RecordingReader(srcs[0][0])
        msg = next((m for _, m in rr.terrain()), None)
        if msg is not None:
            t = Terrain2D.from_message(msg)
            xs = np.r_[t.hseg[:, 1], t.hseg[:, 2], t.vseg[:, 0]]
            ys = np.r_[t.hseg[:, 0], t.vseg[:, 1], t.vseg[:, 2]]
            bounds = (float(xs.min()) - 1, float(ys.min()) - 1, float(xs.max()) + 1, float(ys.max()) + 1)
    cm, tmsg, scene = build(srcs, bounds, a.res, types, a.fsm)
    p = HeroParams.load()
    terrain = Terrain2D.from_message(tmsg, p.scene(scene)) if tmsg else None
    # candidates: within --bounds, else around everything the threats ever covered (the arena) plus --pad
    q = bounds if a.bounds else cm.extent(a.pad)
    pts = candidate_points(terrain, q[0], q[2], q[1], q[3], a.step, a.air) if terrain else []
    evaluate(cm, pts, a.margin)
    groups = sorted(cm.groups.values(), key=lambda g: (g.type_key, g.attack))
    print(f"{len(srcs)} recording spans, {cm.frames} frames, scene {scene}, {len(groups)} groups, "
          f"{cm.swept} outlines swept from the previous frame, {cm.teleports} jumps > {SWEEP_MAX} u not swept")
    for g in groups:
        print(f"  {g.type_key:28s} {g.attack:22s} frames {g.frames:6d} colliders {g.colliders:7d} "
              f"area {g.grid.sum() * cm.res ** 2:7.1f} u2")
    ex = cm.extent(0.0)
    inner = [q for q in pts if ex[0] <= q["pos"][0] <= ex[2] and ex[1] <= q["pos"][1] <= ex[3]]
    safe = sorted((q for q in inner if q["safe"]), key=lambda q: -q["clearance"])
    print(f"{len(pts)} candidate poses ({len(inner)} inside the threats' extent x {ex[0]:.1f}..{ex[2]:.1f} y "
          f"{ex[1]:.1f}..{ex[3]:.1f}), {sum(q['safe'] for q in pts)} safe at margin {a.margin}, {len(safe)} inside")
    for q in safe[:15]:
        print(f"  {q['kind']:5s} pos ({q['pos'][0]:.2f}, {q['pos'][1]:.2f}) face {q['face']:+d} clearance "
              f"{q['clearance']:.2f}  closest {q['closest'][:2]}")
    walls = defaultdict(list)
    for q in pts:
        if q["kind"] == "wall":
            walls[(q["wall"], q["face"], q["top"])].append(q)
    for (xw, f, top), qs in sorted(walls.items()):
        hq = max(qs, key=lambda q: q["pos"][1])
        print(f"  wall x {xw:.2f} ({'left' if f < 0 else 'right'} of the hero) top {top:.2f}: highest cling "
              f"y {hq['pos'][1]:.2f} clearance {hq['clearance']:.2f} closest {hq['closest'][:1]}")
    if a.json:
        out = {"scene": scene, "bounds": bounds, "res": cm.res, "frames": cm.frames, "sources": cm.sources,
               "margin": a.margin, "swept": cm.swept, "teleports": cm.teleports,
               "groups": [{"type_key": g.type_key, "attack": g.attack, "frames": g.frames, "colliders": g.colliders,
                           "area": float(g.grid.sum() * cm.res ** 2)} for g in groups],
               "points": [{k: v for k, v in q.items() if k != "box"} | {"box": [round(c, 4) for c in q["box"]]}
                          for q in pts]}
        a.json.write_text(json.dumps(out, indent=1), encoding="utf-8")
    if a.png:
        render_png(cm, pts, terrain, a.png)
    return 0


if __name__ == "__main__":
    sys.exit(main())
