"""Support precision (the person 2026-10-09: "export the game's real damage boxes, then check every committed
prediction: at this moment we predict the damage box 0.2 s later; if 0.2 s later there is no real damage box at that
place, the prediction is wrong. 50 % bigger than the real one is margin; now it is about 10000 % bigger").

Recall (tools.multi_recall: no real hit outside the support) says nothing about how much MORE the support covers. This
tool measures that, per frame t x enemy x support layer x look-ahead k (0, 6, 12, 18 frames):

  prediction  the planner's support as tools.zone_overlay ZoneEngine computes it (the viewer's --zones path, the
              switches from the environment, default the round-5 configuration), split by OWNER: each placement group
              of forum_layer_audit.classify, tube box, hazard path on the hero-centre grid at t + k, the enemy's thrown
              hazards (pins, bells, runes, spears) counted as the thrower's. Layers as the replay's support/k<k>/<layer>
              (body, committed, window, not_started, hazard, death), com_all = committed | window, total = the union.
  reference   the enemy's REAL damage at t + k: every enabled collider with damage dealt > 0 of the enemy and of the
              hazards it threw (tools.zone_overlay.damage_colliders: parked members skipped; a hazard goes to the nearest
              enemy of its owner type when it arms), the exact Minkowski sum with the hero hurtbox (HERO_HALF_U) on the
              same grid points the support is queried at. R = frames t+k-1 .. t+k+1 grown by one support cell (CELL_U:
              the support's +-1 bin in time and space), Rs = strictly at t + k. For not_started the reference is R only
              when an attack of the enemy actually started in (t, t + k] (a state of its table's attack_starts entered),
              else empty.
  numbers     P (predicted cells), RATIO = P / R ('false alarm' when R is empty), recall = |P & Rs| / |Rs|, the excess
              P - R split by side of the reference box relative to the enemy's facing (front / back / up / down / inner)
              and how far the prediction reaches past the reference box on each side (u); the enemy's type, family,
              state, time in state, the placement kinds (classify group names; "aim" = an aim template placed).
  interrupted the enemy was hit, staggered (a Stun / Recoil / Clash ... state), killed, or a nail clash happened within
              CLASH_U of it in (t, t + k]: the prediction cannot know; counted apart, never an error.
  ERROR       (the person's rule) a non-empty prediction with RATIO > 1.5, or with an empty reference, not interrupted.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.support_precision run C:/ssbot/data/human/<session>:win[:<attempts>]
        <bot run dir>[:<n eps>] ... --out <dir> [--every 3] [--ks 0,6,12,18] [--w0] [--frames F,F] [--workers 4]
        [--aim 0|1]                                  # one .jsonl per attempt / episode (rows: frame x enemy)
    ../scripts/uv.cmd run python -m ssbot.tools.support_precision summary <dir> [<dir> ...] [--json out.json]
        [--ks 0,12]                                  # the gate: error shares, RATIO quantiles, top causes, recall
    ../scripts/uv.cmd run python -m ssbot.tools.support_precision png <spec> --frames F[,F] [--enemy "Reed 1"]
        [--k 12] --out <dir> [--tag x_]             # world-space PNGs: reference filled, prediction outlined, screen
    ../scripts/uv.cmd run python -m ssbot.tools.support_precision worst <summary.json> --out <dir> [--top 10]

Areas are in grid cells (zone_overlay.CELL = 0.25 u: 1 cell = 0.0625 u^2) in the rows, u^2 in the summary.
"""
import argparse
import json
import math
import os
import re
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

KS = (0, 6, 12, 18)
LAYERS = ("body", "committed", "window", "not_started", "hazard", "death")
DERIVED = ("com_all", "total")
REPORT = ("committed", "window", "com_all", "not_started", "body", "total")
LIMIT = 1.5
STAGGER = re.compile(r"Stun|Stagger|Recoil|Hurt|Knock|Clash|Parried|Bounce|Hit Recover")
CLASH_U = 6.0
OUT_DIR = Path(r"C:\ssbot\data\m2_forum_precision")
CORNERS = ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))
# a layer's stats row: P, |P & R|, |P & Rs|, excess cells front / back / up / down / inner, reach past the reference
# box front / back / up / down (u)
STAT = ("P", "I", "Is", "xf", "xb", "xu", "xd", "xi", "ef", "eb", "eu", "ed")


def _below_normal() -> None:
    if os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)


# ------------------------------------------------------------------------------------------------ geometry

def _ccw_hull(pts: np.ndarray) -> np.ndarray:
    """The convex hull of pts [n, 2], counter-clockwise (y up)."""
    import cv2
    h = cv2.convexHull(np.asarray(pts, np.float32)).reshape(-1, 2).astype(np.float64)
    if len(h) >= 3:
        a = np.sum(h[:, 0] * np.roll(h[:, 1], -1) - np.roll(h[:, 0], -1) * h[:, 1])
        if a < 0:
            h = h[::-1]
    return h


def _convex(poly: np.ndarray) -> bool:
    d = np.roll(poly, -1, axis=0) - poly
    dn = np.roll(d, -1, axis=0)
    c = d[:, 0] * dn[:, 1] - d[:, 1] * dn[:, 0]
    c = c[np.abs(c) > 1e-9]
    return len(c) == 0 or bool((c > 0).all() or (c < 0).all())


def _in_convex(px: np.ndarray, py: np.ndarray, h: np.ndarray) -> np.ndarray:
    """Points inside (or on) the counter-clockwise convex polygon h."""
    ok = np.ones(px.shape, bool)
    n = len(h)
    if n < 3:
        return np.zeros(px.shape, bool)
    for i in range(n):
        ax, ay = h[i]
        bx, by = h[(i + 1) % n]
        ok &= (bx - ax) * (py - ay) - (by - ay) * (px - ax) >= -1e-9
    return ok


def _in_poly(px: np.ndarray, py: np.ndarray, poly: np.ndarray) -> np.ndarray:
    """Even-odd point in polygon (any simple polygon)."""
    inside = np.zeros(px.shape, bool)
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if y1 == y2:
            continue
        c = (y1 > py) != (y2 > py)
        xi = x1 + (py - y1) * (x2 - x1) / (y2 - y1)
        inside ^= c & (px < xi)
    return inside


def _grown(poly: np.ndarray, hx: float, hy: float) -> np.ndarray:
    return _ccw_hull(np.concatenate([poly + (sx * hx, sy * hy) for sx, sy in CORNERS]))


def hero_centre_mask(grid, polys, hx: float, hy: float, out: np.ndarray | None = None) -> np.ndarray:
    """[ny, nx] bool: the grid's hero centres whose box (half extents hx, hy) meets one of the polygons (world u):
    the exact Minkowski sum (a convex polygon: the hull of its copies at the box corners; any other: the polygon itself
    and every edge's hull), tested at the grid points, as the support is queried."""
    m = np.zeros(grid.shape, bool) if out is None else out
    for poly in polys:
        poly = np.asarray(poly, np.float64).reshape(-1, 2)
        if len(poly) < 2:
            continue
        lo = poly.min(axis=0) - (hx, hy)
        hi = poly.max(axis=0) + (hx, hy)
        c0 = max(int(math.ceil((lo[0] - grid.x0) / grid.cell - 1e-9)), 0)
        c1 = min(int(math.floor((hi[0] - grid.x0) / grid.cell + 1e-9)), grid.nx - 1)
        r0 = max(int(math.ceil((lo[1] - grid.y0) / grid.cell - 1e-9)), 0)
        r1 = min(int(math.floor((hi[1] - grid.y0) / grid.cell + 1e-9)), grid.ny - 1)
        if c1 < c0 or r1 < r0:
            continue
        px, py = np.meshgrid(grid.xs[c0:c1 + 1], grid.ys[r0:r1 + 1])
        if len(poly) <= 2 or _convex(poly):
            hit = _in_convex(px, py, _grown(poly, hx, hy))
        else:
            hit = _in_poly(px, py, poly)
            for i in range(len(poly)):
                hit |= _in_convex(px, py, _grown(poly[[i, (i + 1) % len(poly)]], hx, hy))
        m[r0:r1 + 1, c0:c1 + 1] |= hit
    return m


# ------------------------------------------------------------------------------------------------ the truth

def hazard_type(e: dict) -> str | None:
    """A recorded entity's thrown-hazard type (core.forum HAZARD_OWNER key; "damager" told apart by circle radius as
    combat.projectiles.hazard_type), None when it is not one."""
    from ssbot.core.forum import ALIAS_TOL_U, HAZARD_ALIASES, HAZARD_OWNER
    tk = str(e.get("type_key") or e.get("name") or "")
    alias = HAZARD_ALIASES.get(tk)
    if alias:
        for c in e.get("cols") or e.get("colliders") or ():
            v = c.get("verts_world")
            if c.get("damage") and v and len(v) >= 6:
                xs = v[0::2]
                r = 0.5 * (max(xs) - min(xs))
                for r0, name in alias:
                    if abs(r - r0) <= max(ALIAS_TOL_U, 0.05 * r0):
                        return name
        return None
    return tk if tk in HAZARD_OWNER else None


def _armed(e: dict) -> bool:
    for c in e.get("cols") or e.get("colliders") or ():
        d = c.get("damage")
        if d and c.get("enabled") and (d.get("dealt") or 0) > 0:
            return True
    return False


def _hero_xy(s: dict) -> tuple | None:
    b = (s.get("hero") or {}).get("box")
    return (0.5 * (b[0] + b[2]), 0.5 * (b[1] + b[3])) if b else None


class Truth:
    """The real damage per enemy over one attempt's game-frame STATEs: per frame the damage colliders by enemy (its
    thrown hazards included), its Control state, and what interrupts a prediction (hits, stagger states, death,
    nail clashes)."""

    def __init__(self, states: list[dict]):
        from ssbot.core.forum import FORUM_TYPES, HAZARD_OWNER
        from ssbot.tools.zone_overlay import damage_colliders, parked
        self.n = len(states)
        self.polys: list[dict] = []
        self.ctrl: list[dict] = []
        self.hero: list = []
        self.epos: list[dict] = []
        self.hits: dict = defaultdict(set)
        self.stag: dict = defaultdict(set)
        self.dead: dict = {}
        self.clash: set = set()
        self.thrower: dict = {}
        self.idx = {int(s["f"]): j for j, s in enumerate(states)}
        self.raw = [int(s.get("_f_raw", s["f"])) for s in states]
        was_armed: set = set()
        for j, s in enumerate(states):
            ents = s.get("ents") or ()
            ctrl, pos = {}, {}
            for e in ents:
                tk = str(e.get("type_key") or "")
                sp = FORUM_TYPES.get(tk)
                if sp is None or e.get("iid") is None or parked(e):
                    continue
                iid = int(e["iid"])
                st = next((f.get("state") for f in e.get("fsms") or () if f.get("name") == sp.control_fsm), None)
                ctrl[iid] = st
                p = e.get("pos") or (0.0, 0.0)
                pos[iid] = (float(p[0]), float(p[1]), tk)
                if st is not None and STAGGER.search(str(st)):
                    self.stag[iid].add(j)
                if (e.get("is_dead") or (e.get("hp") is not None and e["hp"] <= 0)
                        or (st is not None and st in sp.death_states)) and iid not in self.dead:
                    self.dead[iid] = j
            armed_now = set()
            for e in ents:
                ht = hazard_type(e)
                if ht is None or e.get("iid") is None or not _armed(e):
                    continue
                hid = int(e["iid"])
                armed_now.add(hid)
                if hid in was_armed and hid in self.thrower:
                    continue
                owner_tk = HAZARD_OWNER.get(ht)
                p = e.get("pos") or (0.0, 0.0)
                cand = [(math.hypot(q[0] - p[0], q[1] - p[1]), iid) for iid, q in pos.items() if q[2] == owner_tk
                        and iid not in self.dead]
                if cand:
                    self.thrower[hid] = min(cand)[1]
            was_armed = armed_now
            per: dict = defaultdict(list)
            for poly, _clash, _label, _vel, o in damage_colliders(s):
                o = self.thrower.get(o, o)
                per[o].append(poly)
            self.polys.append(dict(per))
            self.ctrl.append(ctrl)
            self.epos.append(pos)
            self.hero.append(_hero_xy(s))
            for ev in s.get("ev") or ():
                d = ev.get("d") or {}
                if ev.get("k") == "hit" and d.get("ent") is not None:
                    self.hits[int(d["ent"])].add(j)
                elif ev.get("k") == "freeze" and "Clash" in str(d.get("type") or "") and d.get("phase") == "start":
                    self.clash.add(j)
        self._cache: dict = {}

    def owner(self, o: int) -> int:
        return self.thrower.get(int(o), int(o))

    def mask(self, grid, j: int, iid: int, pad: float) -> np.ndarray | None:
        """The enemy's real damage at frame index j in hero-centre space (hero box grown by pad), None when none."""
        if not (0 <= j < self.n):
            return None
        key = (j, iid, pad)
        if key not in self._cache:
            from ssbot.knowledge import hitbox_tables as hb
            polys = self.polys[j].get(iid)
            m = None
            if polys:
                m = hero_centre_mask(grid, polys, hb.HERO_HALF_U[0] + pad, hb.HERO_HALF_U[1] + pad) & grid.inside
                if not m.any():
                    m = None
            self._cache[key] = m
        return self._cache[key]

    def reference(self, grid, j: int, iid: int) -> tuple[np.ndarray, np.ndarray]:
        """(R: frames j-1 .. j+1 grown by one support cell, Rs: exactly frame j) [ny, nx] bool."""
        from ssbot.knowledge import hitbox_tables as hb
        r = np.zeros(grid.shape, bool)
        for jj in (j - 1, j, j + 1):
            m = self.mask(grid, jj, iid, hb.CELL_U)
            if m is not None:
                r |= m
        ms = self.mask(grid, j, iid, 0.0)
        return r, (ms if ms is not None else np.zeros(grid.shape, bool))

    def interrupted(self, iid: int, j0: int, j1: int) -> list[str]:
        """What happened to the enemy in frames (j0, j1] that no prediction at j0 can know."""
        out = []
        rng = range(j0 + 1, j1 + 1)
        if any(j in self.hits.get(iid, ()) for j in rng):
            out.append("hit")
        if any(j in self.stag.get(iid, ()) for j in rng):
            out.append("stagger")
        d = self.dead.get(iid)
        if d is not None and j0 < d <= j1:
            out.append("killed")
        for j in rng:
            if j in self.clash and j < self.n:
                h, p = self.hero[j], self.epos[j].get(iid)
                if h is not None and p is not None and math.hypot(h[0] - p[0], h[1] - p[1]) <= CLASH_U:
                    out.append("clash")
                    break
        return out

    def started(self, iid: int, j0: int, j1: int, starts) -> str | None:
        """The attack start state the enemy entered in frames (j0, j1], if any."""
        prev = self.ctrl[j0].get(iid) if 0 <= j0 < self.n else None
        for j in range(j0 + 1, min(j1, self.n - 1) + 1):
            st = self.ctrl[j].get(iid)
            if st is not None and st != prev and st in starts:
                return st
            prev = st
        return None


# ------------------------------------------------------------------------------------------------ the prediction

def owner_layers(fcast, cx, cy, tk, owner_of, ks) -> tuple[dict, dict]:
    """({owner: {layer: [R, F] bool}}, {owner: {k: {"kinds": [group names], "aim": bool}}}) of a MultiForecast on the
    query points: forum_layer_audit.group_occ split by placement owner (a hazard's placements, tubes and paths to its
    thrower by owner_of; None = left out, e.g. a later wave's entry)."""
    from ssbot.tools.forum_layer_audit import BOX_LAYER, _key_name, classify
    from ssbot.tools.zone_overlay import LAYER_OF
    store = fcast.fc.tables.store
    metas = {"pm": (fcast.pm, fcast.P.tid, fcast._fine_occ), "wm": (fcast.wm, fcast.W.tid, fcast._win_occ),
             "bb": (fcast.bb, fcast.bb["tid"], fcast._bbox_occ)}
    occ: dict = defaultdict(dict)
    info: dict = defaultdict(lambda: {k: {"kinds": set(), "aim": False} for k in ks})

    def add(o, group, m, aim=False):
        if o is None or not m.any():
            return
        lay = LAYER_OF.get(group, "death")
        d = occ[o]
        d[lay] = d[lay] | m if lay in d else m
        for j, k in enumerate(ks):
            if m[:, j].any():
                info[o][k]["kinds"].add(group)
                info[o][k]["aim"] |= aim
    for key, kind, sel in classify(fcast):
        meta, tids, fn = metas[kind]
        own = np.asarray(meta["owner"]).astype(np.int64)
        for o in np.unique(own[sel]).tolist():
            sub = sel & (own == o)
            aim = any("aim@" in _key_name(store, tids[i]) for i in np.flatnonzero(sub))
            add(owner_of(o), key[0], fn(cx, cy, tk, sub), aim)
    for o, kind in sorted({(int(b[0]), b[1]) for b in fcast.boxes}):
        add(owner_of(o), BOX_LAYER.get(kind, kind), fcast._box_occ(cx, cy, tk, kinds=(kind,), only={o}))
    for p in fcast.paths:
        add(owner_of(int(p.iid)), "haz_path", fcast._path_occ(cx, cy, tk, only={int(p.iid)}))
    return occ, info


def _box_of(m: np.ndarray):
    rr, cc = np.nonzero(m)
    return (int(cc.min()), int(cc.max()), int(rr.min()), int(rr.max())) if len(rr) else None


def layer_stats(P: np.ndarray, R: np.ndarray, Rs: np.ndarray, facing: int, rbox, cell: float) -> list:
    """STAT of one predicted mask against the reference (rbox: the reference's (c0, c1, r0, r1) in grid cells, or the
    enemy's own cell when it has none)."""
    n = int(P.sum())
    if not n:
        return [0] * len(STAT)
    c0, c1, r0, r1 = rbox
    rr, cc = np.nonzero(P & ~R)
    front = cc > c1 if facing >= 0 else cc < c0
    back = cc < c0 if facing >= 0 else cc > c1
    hor = front | back
    up = ~hor & (rr > r1)
    dn = ~hor & (rr < r0)
    pr, pc = np.nonzero(P)
    ef = (pc - c1) if facing >= 0 else (c0 - pc)
    eb = (c0 - pc) if facing >= 0 else (pc - c1)
    return [n, int((P & R).sum()), int((P & Rs).sum()), int(front.sum()), int(back.sum()), int(up.sum()),
            int(dn.sum()), int((~hor & ~up & ~dn).sum()),
            round(max(0, int(ef.max())) * cell, 2), round(max(0, int(eb.max())) * cell, 2),
            round(max(0, int((pr - r1).max())) * cell, 2), round(max(0, int((r0 - pr).max())) * cell, 2)]


def frame_rows(eng, truth: Truth, j0: int, ks, grid) -> list[dict]:
    """The rows (one per named enemy in play) of the forecast made at frame index j0."""
    from ssbot.combat.enemy_tracker import FACES_LEFT
    fcast = eng.fcast
    if fcast is None:
        return []
    F = len(ks)
    tk = np.asarray(ks, np.float64) / 60.0
    cx = np.ascontiguousarray(np.repeat(grid.gx, F, axis=1))
    cy = np.ascontiguousarray(np.repeat(grid.gy, F, axis=1))
    enemies = eng.enemies()
    names = {iid: name for iid, name, *_ in enemies}

    def owner_of(o):
        o = truth.owner(o)
        return o if o in names else None
    occ, info = owner_layers(fcast, cx, cy, tk, owner_of, ks)
    subj = {s.iid: s for s in fcast.subjects}
    mf = eng.pol.fc
    rows = []
    for iid, name, st, pos, _col in enemies:
        tr = mf.trackers.get(iid)
        s = subj.get(iid)
        if tr is None or s is None:
            continue
        facing = FACES_LEFT[int(bool(tr.flip))] if tr.flip is not None else 1
        epos = truth.epos[j0].get(iid) if 0 <= j0 < truth.n else None
        ecell = None
        if epos is not None:
            c = int(round((epos[0] - grid.x0) / grid.cell))
            r = int(round((epos[1] - grid.y0) / grid.cell))
            ecell = (c, c, r, r)
        starts = set(getattr(tr.table, "attack_starts", {}) or {})
        row = {"iid": int(iid), "name": name, "type": s.type_key, "fam": s.family, "state": st,
               "tis": round(float(fcast.origin_t - tr.t_entry), 3) if tr.t_entry is not None else None,
               "com": bool(s.committed), "facing": int(facing),
               "pos": [round(float(pos[0]), 2), round(float(pos[1]), 2)] if pos is not None else None, "k": {}}
        layers = occ.get(iid, {})
        for jk, k in enumerate(ks):
            j = j0 + k
            R, Rs = truth.reference(grid, j, iid)
            rbox = _box_of(R) or ecell or (0, 0, 0, 0)
            masks = {lay: layers[lay][:, jk].reshape(grid.shape) & grid.inside for lay in LAYERS if lay in layers}
            com = [masks[x] for x in ("committed", "window") if x in masks]
            if com:
                masks["com_all"] = com[0] | com[1] if len(com) == 2 else com[0]
            tot = np.zeros(grid.shape, bool)
            for lay in LAYERS:
                if lay in masks:
                    tot |= masks[lay]
            masks["total"] = tot
            st_att = truth.started(iid, j0, j, starts) if k > 0 else None
            ent = {"R": int(R.sum()), "Rs": int(Rs.sum()), "in": truth.interrupted(iid, j0, j),
                   "kinds": sorted(info[iid][k]["kinds"]) if iid in info else [],
                   "aim": bool(info[iid][k]["aim"]) if iid in info else False,
                   "L": {lay: layer_stats(m, R, Rs, facing, rbox, grid.cell) for lay, m in masks.items()
                         if m.any() or lay == "total"}}
            if st_att is not None:
                ent["started"] = st_att
                Rn = R
            else:
                Rn = np.zeros(grid.shape, bool)
            if "not_started" in masks:
                ent["Rns"] = int(Rn.sum())
                ent["L"]["not_started"] = layer_stats(masks["not_started"], Rn, Rn & Rs, facing,
                                                      _box_of(Rn) or ecell or (0, 0, 0, 0), grid.cell)
            row["k"][k] = ent
        rows.append(row)
    return rows


# ------------------------------------------------------------------------------------------------ running

_ENG = None


def _engine(threads: int):
    global _ENG
    if _ENG is None:
        from ssbot.tools.zone_overlay import ZoneEngine
        _ENG = ZoneEngine(crest="Wanderer", threads=threads)
    return _ENG


def _job_states(job: dict, w0: bool, pad_f: int) -> tuple:
    """(terrain, states, index of the first frame not evaluated) of a zone_share job."""
    from ssbot.tools.zone_overlay import battle
    from ssbot.tools.zone_share import _states
    terrain, states = _states(job)
    stop = len(states)
    if w0:
        for i, s in enumerate(states):
            b = battle(s)
            if b is not None and b.get("started") and (b.get("wave") or 0) >= 1:
                stop = i
                break
        states = states[:stop + pad_f]
    return terrain, states, stop


def run_job(job: dict, ks, every: int, w0: bool, frames: set, threads: int = 4, stop_raw: int | None = None,
            only_frames: bool = False) -> tuple[list[dict], dict]:
    """The rows of one attempt / episode (every `every`-th game frame and the raw frames asked for, +-1)."""
    eng = _engine(threads)
    terrain, states, stop = _job_states(job, w0, max(ks) + 2)
    crest = (job.get("seg") or {}).get("crest")
    eng.crest = crest if crest in ("Wanderer", "Reaper") else eng.crest
    truth = Truth(states)
    grid = eng.grid
    eng.start(terrain)
    rows = []
    t_fc = 0.0
    want = sorted(frames)
    for i, s in enumerate(states):
        if i >= stop:
            break
        eng.feed(s)
        raw = int(s.get("_f_raw", s["f"]))
        if stop_raw is not None and raw > stop_raw:
            break
        asked = any(abs(raw - w) <= 1 for w in want)
        if asked:
            want = [w for w in want if abs(raw - w) > 1]
        if not asked and (only_frames or s["f"] % every):
            continue
        if eng.ws is None or not eng.running:
            continue
        j0 = truth.idx.get(int(eng.ws.stamp.frame), i)
        if j0 + max(ks) + 1 >= truth.n:
            continue
        t0 = time.perf_counter()
        eng.forecast()
        rs = frame_rows(eng, truth, j0, ks, grid)
        t_fc += time.perf_counter() - t0
        for r in rs:
            r["f"] = raw
            r["fo"] = truth.raw[j0]
            if asked:
                r["asked"] = True
        rows.extend(rs)
        if only_frames and not want:
            break
    return rows, {"config": eng.config_text(), "seconds": round(t_fc, 1), "frames": len(states)}


def _run_one(job: dict, out: str, ks, every: int, w0: bool, frames, threads: int) -> str:
    from ssbot.tools.zone_share import job_name
    _below_normal()
    name = job_name(job)
    t0 = time.perf_counter()
    rows, meta = run_job(job, ks, every, w0, set(frames), threads)
    p = Path(out) / f"{name}.jsonl"
    p.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows), "utf-8")
    (Path(out) / "config.json").write_text(json.dumps({"config": meta["config"], "ks": list(ks), "every": every,
                                                       "w0": w0}), "utf-8")
    return f"{name}: {len(rows)} rows ({time.perf_counter() - t0:.0f} s) {meta['config']}"


def cmd_run(a) -> int:
    from ssbot.tools.zone_share import _jobs, job_name
    _below_normal()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    ks = tuple(int(x) for x in a.ks.split(","))
    frames = [int(x) for x in a.frames.split(",") if x] if a.frames else []
    cache = Path(a.demo_cache) if a.demo_cache else None
    jobs = [j for spec in a.specs for j in _jobs(spec, cache)]
    jobs = [j for j in jobs if a.force or not (out / f"{job_name(j)}.jsonl").exists()]
    if a.workers <= 1:
        for j in jobs:
            print(_run_one(j, str(out), ks, a.every, a.w0, frames, a.threads), flush=True)
        return 0
    with ProcessPoolExecutor(a.workers) as ex:
        futs = [ex.submit(_run_one, j, str(out), ks, a.every, a.w0, frames, a.threads) for j in jobs]
        for f in as_completed(futs):
            print(f.result(), flush=True)
    return 0


# ------------------------------------------------------------------------------------------------ summary

def _q(v: list) -> dict:
    if not v:
        return {"n": 0}
    a = np.asarray(v, np.float64)
    return {"n": len(v), "p50": round(float(np.percentile(a, 50)), 2), "p90": round(float(np.percentile(a, 90)), 2),
            "p99": round(float(np.percentile(a, 99)), 2), "max": round(float(a.max()), 2)}


def judge(ent: dict, lay: str) -> tuple | None:
    """(P, R, ratio or None (false alarm), error, interrupted) of one layer at one k; None when nothing predicted."""
    st = ent["L"].get(lay)
    if st is None or not st[0]:
        return None
    R = ent.get("Rns", 0) if lay == "not_started" else ent["R"]
    intr = bool(ent.get("in"))
    ratio = st[0] / R if R else None
    err = (ratio is None or ratio > LIMIT) and not intr
    return st[0], R, ratio, err, intr


def _kinds_key(ent: dict, lay: str) -> str:
    from ssbot.tools.zone_overlay import LAYER_OF
    ks = [x for x in ent.get("kinds") or () if LAYER_OF.get(x, "death") == lay or (lay == "com_all" and LAYER_OF.get(
        x) in ("committed", "window")) or lay == "total"]
    return "+".join(ks) + ("+aim" if ent.get("aim") and lay in ("committed", "window", "com_all", "total") else "")


def summarize(dirs, ks=(0, 12), cell: float = 0.25) -> dict:
    from ssbot.tools.zone_overlay import SHORT_NAMES
    a2 = cell * cell
    res: dict = {"dirs": [str(d) for d in dirs], "limit": LIMIT, "cell_u": cell, "k": {}}
    acc = {k: {lay: {"pop": 0, "err": 0, "fa": 0, "intr": 0, "intr_err": 0, "ratio": [], "groups": defaultdict(list),
                     "causes": defaultdict(lambda: [0, 0, 0.0, [], [0.0] * 4, [0.0] * 4])}
               for lay in REPORT} for k in ks}
    rec = {k: {"rows": 0, "full": 0, "cells": 0, "cov": 0, "miss": defaultdict(int)} for k in ks}
    worst = []
    files = 0
    for d in dirs:
        for p in sorted(Path(d).glob("*.jsonl")):
            files += 1
            for line in p.read_text("utf-8").splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                short = SHORT_NAMES.get(r["type"], r["type"])
                for k in ks:
                    ent = r["k"].get(str(k))
                    if ent is None:
                        continue
                    if ent["Rs"]:
                        tot = ent["L"]["total"]
                        q = rec[k]
                        q["rows"] += 1
                        q["cells"] += ent["Rs"]
                        q["cov"] += tot[2]
                        if tot[2] >= ent["Rs"]:
                            q["full"] += 1
                        else:
                            q["miss"][f"{short}/{r['fam']}/{r['state']}"] += 1
                    for lay in REPORT:
                        j = judge(ent, lay)
                        if j is None:
                            continue
                        P, R, ratio, err, intr = j
                        g = acc[k][lay]
                        if intr:
                            g["intr"] += 1
                            g["intr_err"] += int(ratio is None or ratio > LIMIT)
                            continue
                        g["pop"] += 1
                        g["err"] += int(err)
                        if ratio is None:
                            g["fa"] += 1
                        else:
                            g["ratio"].append(ratio)
                        kk = _kinds_key(ent, lay)
                        g["groups"][f"{short}|{r['fam']}|{r['state']}|{kk}"].append(ratio if ratio is not None
                                                                                    else float("inf"))
                        if err:
                            st = ent["L"][lay]
                            c = g["causes"][f"{short}|{r['fam']}|{r['state']}|{kk}"]
                            c[0] += 1
                            c[1] += int(ratio is None)
                            c[2] += (P - st[1]) * a2
                            c[3].append(ratio if ratio is not None else float("inf"))
                            for i in range(4):
                                c[4][i] += st[3 + i] * a2
                                c[5][i] = max(c[5][i], st[8 + i])
                            if lay in ("com_all", "not_started") and k == ks[-1]:
                                worst.append([round((P - st[1]) * a2, 2), p.stem, r["f"], r["name"], lay, k,
                                              None if ratio is None else round(ratio, 2),
                                              f"{short}/{r['fam']}/{r['state']}"])
    res["files"] = files
    for k in ks:
        out = res["k"][str(k)] = {}
        for lay in REPORT:
            g = acc[k][lay]
            fin = [x for x in g["ratio"]]
            groups = {}
            for key, v in g["groups"].items():
                f = [x for x in v if math.isfinite(x)]
                groups[key] = dict(_q(f), n_all=len(v), fa=len(v) - len(f))
            causes = []
            for key, c in g["causes"].items():
                f = [x for x in c[3] if math.isfinite(x)]
                causes.append({"group": key, "errors": c[0], "false_alarms": c[1], "excess_u2": round(c[2], 1),
                               "ratio_p50": round(float(np.median(f)), 2) if f else None,
                               "excess_u2_side": dict(zip(("front", "back", "up", "down"),
                                                          [round(x, 1) for x in c[4]])),
                               "reach_max_u": dict(zip(("front", "back", "up", "down"), c[5]))})
            causes.sort(key=lambda c: -c["excess_u2"])
            out[lay] = {"population": g["pop"], "errors": g["err"],
                        "error_pct": round(100.0 * g["err"] / g["pop"], 2) if g["pop"] else None,
                        "false_alarms": g["fa"], "interrupted": g["intr"], "interrupted_over": g["intr_err"],
                        "ratio": _q(fin), "groups": dict(sorted(groups.items(), key=lambda kv: -kv[1]["n_all"])),
                        "causes": causes[:40]}
        q = rec[k]
        out["recall"] = {"rows": q["rows"], "rows_full_pct": round(100.0 * q["full"] / q["rows"], 3) if q["rows"]
                         else None, "cells_pct": round(100.0 * q["cov"] / q["cells"], 3) if q["cells"] else None,
                         "missed_by": dict(sorted(q["miss"].items(), key=lambda kv: -kv[1])[:20])}
    # the worst (frame, enemy) per layer: the largest excess area, one per (attempt, enemy, family / state) so one
    # enemy standing still for seconds does not fill the list
    for lay in ("com_all", "not_started"):
        seen = set()
        out = res["worst" if lay == "com_all" else "worst_ns"] = []
        for w in sorted((w for w in worst if w[4] == lay), key=lambda x: -x[0]):
            if (w[1], w[3], w[7]) in seen:
                continue
            seen.add((w[1], w[3], w[7]))
            out.append(w)
            if len(out) >= 20:
                break
    # and the worst of each enemy type x family (the largest excess area is mostly the Tinies' whole-arena union)
    seen = set()
    res["worst_fam"] = []
    for w in sorted((w for w in worst if w[4] == "com_all"), key=lambda x: -x[0]):
        fam = tuple(w[7].split("/")[:2])
        if fam not in seen:
            seen.add(fam)
            res["worst_fam"].append(w)
    return res


def cmd_summary(a) -> int:
    ks = tuple(int(x) for x in a.ks.split(","))
    res = summarize([Path(d) for d in a.dirs], ks)
    print(f"{res['files']} files; ERROR = predicted area > {LIMIT} x the real one (or a real one empty), "
          f"not interrupted")
    for k in ks:
        r = res["k"][str(k)]
        print(f"k = {k} ({k / 60:.2f} s): recall of the total {r['recall']['rows_full_pct']} % of (frame, enemy) with "
              f"real damage fully covered, {r['recall']['cells_pct']} % of the cells")
        for lay in REPORT:
            x = r[lay]
            q = x["ratio"]
            print(f"  {lay:11s} pred {x['population']:7d}  ERROR {x['error_pct']} %  (false alarms {x['false_alarms']},"
                  f" interrupted apart {x['interrupted']})  RATIO p50 {q.get('p50')} p90 {q.get('p90')} "
                  f"p99 {q.get('p99')} max {q.get('max')}")
        for lay in ("com_all", "not_started"):
            print(f"  top causes {lay} (excess u^2, errors, ratio p50, reach past the real box f/b/u/d u):")
            for c in r[lay]["causes"][:a.top]:
                rm = c["reach_max_u"]
                print(f"    {c['group']:60s} {c['excess_u2']:9.0f} {c['errors']:6d}  p50 {c['ratio_p50']}  "
                      f"{rm['front']:.1f}/{rm['back']:.1f}/{rm['up']:.1f}/{rm['down']:.1f}")
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1), "utf-8")
    return 0


# ------------------------------------------------------------------------------------------------ pictures

def draw(grid, cam, ref: np.ndarray, refs: np.ndarray, masks: dict, polys, hero, label: str, lines: list[str],
         px_u: float = 24.0) -> np.ndarray:
    """A world-space picture (y up) of one enemy at one k: the real damage (hero-centre space) filled red (strict:
    darker), the prediction's layers outlined in the overlay's colours, the real colliders white, the hero centre,
    the camera's screen rectangle (the STATE camera at z = 0) yellow."""
    import cv2
    from ssbot.tools.zone_overlay import COLORS, RENDER, homography
    W, H = int(grid.nx * grid.cell * px_u) + 40, int(grid.ny * grid.cell * px_u) + 40 + 18 * (len(lines) + 1)
    img = np.full((H, W, 3), 24, np.uint8)
    top = 18 * (len(lines) + 1)

    def to_px(x, y):
        return (int(round(20 + (x - grid.x0) * px_u)), int(round(top + 20 + (grid.y0 + (grid.ny - 1) * grid.cell - y)
                                                                      * px_u)))

    def cells(m, col):
        rr, cc = np.nonzero(m)
        s = max(1, int(round(grid.cell * px_u)))
        for r, c in zip(rr, cc):
            x, y = to_px(grid.xs[c], grid.ys[r])
            cv2.rectangle(img, (x - s // 2, y - s // 2), (x + s // 2, y + s // 2), col, -1)
    ins = grid.inside
    cells(ins, (40, 40, 40))
    cells(ref, (60, 60, 200))
    cells(refs, (30, 30, 150))
    for lay, m in masks.items():
        if m is None or not m.any():
            continue
        col = COLORS.get(lay, (255, 255, 255)) if lay not in DERIVED else (255, 255, 255)
        cs, _ = cv2.findContours(m[::-1].astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cs:
            pts = [to_px(grid.xs[int(p[0][0])], grid.ys[grid.ny - 1 - int(p[0][1])]) for p in c]
            cv2.polylines(img, [np.asarray(pts, np.int32)], True, col, 2 if lay != "total" else 1, cv2.LINE_AA)
    for poly in polys:
        pts = [to_px(x, y) for x, y in poly]
        cv2.polylines(img, [np.asarray(pts, np.int32)], True, (235, 235, 235), 1, cv2.LINE_AA)
    if cam is not None and cam.get("V"):
        Hw, _ = homography(grid, cam, RENDER)
        Hi = np.linalg.inv(Hw)
        sc = np.array([[0, 0, 1], [RENDER[0], 0, 1], [RENDER[0], RENDER[1], 1], [0, RENDER[1], 1]], np.float64) @ Hi.T
        sc = sc[:, :2] / sc[:, 2:3]
        cv2.polylines(img, [np.asarray([to_px(x, y) for x, y in sc], np.int32)], True, (60, 230, 255), 2, cv2.LINE_AA)
    if hero is not None:
        cv2.circle(img, to_px(*hero), 5, (255, 255, 255), -1, cv2.LINE_AA)
    for i, t in enumerate([label] + lines):
        cv2.putText(img, t, (10, 16 + 18 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (235, 235, 235), 1, cv2.LINE_AA)
    return img


def render_frames(spec: str, frames, k: int, out: Path, tag: str = "", enemy: str | None = None,
                  threads: int = 4, demo_cache: Path | None = None, w0: bool = False) -> int:
    """PNGs of the given raw frames of one attempt / episode spec (one per enemy with a prediction at k)."""
    import cv2
    from ssbot.tools.zone_share import _jobs, job_name
    spec, _, one = spec.partition("#")
    jobs = _jobs(spec, demo_cache)
    if one:                                     # "<run dir>#i<inst>ep<episode>": that bot episode only
        m = re.match(r"i(\d+)ep(\d+)$", one)
        jobs = [j for j in jobs if m and j.get("inst") == int(m.group(1))
                and int(j["row"].get("episode", -1)) == int(m.group(2))]
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    eng = _engine(threads)
    for job in jobs:
        terrain, states, stop = _job_states(job, w0, k + 2)
        raws = [int(s.get("_f_raw", s["f"])) for s in states]
        want = [f for f in frames if raws and raws[0] - 1 <= f <= raws[-1] + 1]
        if not want:
            continue
        truth = Truth(states)
        grid = eng.grid
        eng.start(terrain)
        last = max(want)
        for i, s in enumerate(states):
            eng.feed(s)
            raw = raws[i]
            if raw > last + 1:
                break
            hit = [w for w in want if abs(raw - w) <= 1]
            if not hit or eng.ws is None:
                continue
            want = [w for w in want if w not in hit]
            j0 = truth.idx.get(int(eng.ws.stamp.frame), i)
            if j0 + k + 1 >= truth.n:
                continue
            eng.forecast()
            tk = np.asarray([k], np.float64) / 60.0
            cx, cy = grid.gx.copy(), grid.gy.copy()
            names = {iid: nm for iid, nm, *_ in eng.enemies()}
            occ, info = owner_layers(eng.fcast, cx, cy, tk,
                                     lambda o: (truth.owner(o) if truth.owner(o) in names else None), (k,))
            for iid, nm, st, pos, _c in eng.enemies():
                if enemy and nm != enemy:
                    continue
                lays = occ.get(iid, {})
                masks = {lay: lays[lay][:, 0].reshape(grid.shape) & grid.inside for lay in LAYERS if lay in lays}
                if not masks:
                    continue
                R, Rs = truth.reference(grid, j0 + k, iid)
                a2 = grid.cell ** 2
                ref_a = R.sum() * a2
                lines = [f"real damage (hero-centre space, +-1 f): {ref_a:.1f} u^2 (filled red; strict at t+k darker)"]
                for lay, m in masks.items():
                    pa = m.sum() * a2
                    lines.append(f"{lay}: {pa:.1f} u^2  RATIO {pa / ref_a:.1f}" if ref_a else
                                 f"{lay}: {pa:.1f} u^2  (no real damage: false alarm)")
                tr = eng.pol.fc.trackers.get(iid)
                fam = next((x.family for x in eng.fcast.subjects if x.iid == iid), None)
                kinds = sorted(info[iid][k]["kinds"]) if iid in info else []
                intr = truth.interrupted(iid, j0, j0 + k)
                lines.append(f"kinds {'+'.join(kinds)}{' aim' if iid in info and info[iid][k]['aim'] else ''}"
                             + (f"  INTERRUPTED {','.join(intr)}" if intr else ""))
                label = (f"{Path(str((job.get('seg') or {}).get('session', job.get('run', '')))).name} f {raw} "
                         f"(origin {truth.raw[j0]}) k {k} ({k / 60:.2f} s)  {nm} {st} fam {fam} "
                         f"t in state {(eng.fcast.origin_t - tr.t_entry) if tr and tr.t_entry else 0:.2f} s")
                img = draw(grid, s.get("cam"), R, Rs, masks, truth.polys[min(j0 + k, truth.n - 1)].get(iid, []),
                           truth.hero[min(j0 + k, truth.n - 1)], label, lines)
                fn = out / f"{tag}{job_name(job)}_f{raw}_k{k}_{nm.replace(' ', '_')}.png"
                cv2.imwrite(str(fn), img)
                n += 1
            if not want:
                break
    return n


def cmd_png(a) -> int:
    n = render_frames(a.spec, [int(x) for x in a.frames.split(",")], a.k, Path(a.out), a.tag, a.enemy, a.threads,
                      Path(a.demo_cache) if a.demo_cache else None, a.w0)
    print(json.dumps({"pngs": n, "out": a.out}))
    return 0


def cmd_worst(a) -> int:
    """PNGs of a summary's worst (frame, enemy) predictions (the largest excess area at its last k)."""
    res = json.loads(Path(a.summary).read_text("utf-8"))
    n = 0
    for w in res[a.list][:a.top] + res.get("worst_ns", [])[:a.top_ns]:
        excess, stem, f, name, lay, k, ratio = w[:7]
        spec = _spec_of(stem, a.runs_root)
        if spec is None:
            print(f"no spec for {stem}")
            continue
        n += render_frames(spec, [f], k, Path(a.out), "worst_", name, a.threads,
                           Path(a.demo_cache) if a.demo_cache else None, a.w0)
    print(json.dumps({"pngs": n, "out": a.out}))
    return 0


def _spec_of(stem: str, runs_root: str) -> str | None:
    """A job spec from a row file's stem ("20261009_085824_a0" or "<run>_i<inst>_ep<n>")."""
    m = re.match(r"^(\d{8}_\d{6})_a(\d+)$", stem)
    if m:
        return f"C:/ssbot/data/human/{m.group(1)}:win:{m.group(2)}"
    m = re.match(r"^(.*)_i(\d+)_ep(\d+)$", stem)
    if m:
        return f"{Path(runs_root) / m.group(1)}#i{m.group(2)}ep{m.group(3)}"
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="support_precision")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("specs", nargs="+")
    r.add_argument("--out", required=True)
    r.add_argument("--every", type=int, default=3)
    r.add_argument("--ks", default=",".join(map(str, KS)))
    r.add_argument("--w0", action="store_true")
    r.add_argument("--frames", default="")
    r.add_argument("--workers", type=int, default=1)
    r.add_argument("--threads", type=int, default=4)
    r.add_argument("--aim", default=None, help="SSBOT_FORUM_AIM for this run (default: the environment / overlay)")
    r.add_argument("--demo-cache", default=r"C:\ssbot\data\m2_forum_overlay\demo_cache")
    r.add_argument("--force", action="store_true")
    s = sub.add_parser("summary")
    s.add_argument("dirs", nargs="+")
    s.add_argument("--ks", default="0,12")
    s.add_argument("--json")
    s.add_argument("--top", type=int, default=12)
    for name in ("png", "worst"):
        p = sub.add_parser(name)
        if name == "png":
            p.add_argument("spec")
            p.add_argument("--frames", required=True)
            p.add_argument("--k", type=int, default=12)
            p.add_argument("--enemy")
            p.add_argument("--tag", default="")
        else:
            p.add_argument("summary")
            p.add_argument("--top", type=int, default=10)
            p.add_argument("--top-ns", type=int, default=5)
            p.add_argument("--list", default="worst", choices=("worst", "worst_fam"))
            p.add_argument("--runs-root", default=r"C:\ssbot\data\runs\m2")
        p.add_argument("--out", required=True)
        p.add_argument("--threads", type=int, default=4)
        p.add_argument("--aim", default=None)
        p.add_argument("--w0", action="store_true")
        p.add_argument("--demo-cache", default=r"C:\ssbot\data\m2_forum_overlay\demo_cache")
    a = ap.parse_args(argv)
    if getattr(a, "aim", None) is not None:
        os.environ["SSBOT_FORUM_AIM"] = a.aim
    return {"run": cmd_run, "summary": cmd_summary, "png": cmd_png, "worst": cmd_worst}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
