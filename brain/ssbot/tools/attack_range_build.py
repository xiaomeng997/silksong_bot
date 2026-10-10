"""Attack-range estimate (ARE) builder and its estimation error (Task "attack range", the person 2026-10-10:
estimate each enemy's attack range accurately first, with no margin; the margin is a later decision from this error).
The model is ssbot.combat.attack_range (its docstring); one enemy at a time, the Choristor first.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.attack_range_build shapes          # collider polygons (person STATEs)
    ../scripts/uv.cmd run python -m ssbot.tools.attack_range_build build           # R0 dev only -> the table
    ../scripts/uv.cmd run python -m ssbot.tools.attack_range_build eval --set fresh|r2|person|dev [--every 2]
    ../scripts/uv.cmd run python -m ssbot.tools.attack_range_build png             # the person's frames
    ../scripts/uv.cmd run python -m ssbot.tools.attack_range_build report          # eval_*.json -> report.json

Data: the per-fight Forum caches (ssbot.knowledge.forum_cache: every enabled damage collider as an AABB with dealt /
eff) and the person's sessions (their STATEs through forum_cache.extract_states). A cache keeps AABBs only; the
Choristor's colliders are rigid (each name's AABB size is constant), so their exact polygons are the person-session
polygon of that name and flip placed in the AABB ("shapes").

Sets: dev = R0 dev (107 fights, the only build input), fresh = R0 fresh (35), r2 = the R2 fresh fights (187 of
m2_forum_r2/r1/fights.json, their caches in R1c's cache), person = the person's sessions (reported separately), each judged on its own.

Error rows (eval): every `every`-th frame of every family instance and every 6th idle frame of an enemy in play, at
k = 0, 6, 12: the estimate for t + k against the enemy's REAL damage colliders at the first frame whose game time
reaches t + k/60, both in hero-centre space (the hurtbox dilation, the same raster): the precision RATIO (estimate /
real area), the covered share of the real cells, the MISS (real cells outside the estimate: how far beyond it, per
side front / back / up / down / inner relative to the estimate's box in the anchor's facing frame) and the EXCESS
(estimate cells never hit: how far beyond the real damage, per side). Rows where a new family started by t + k (group 2,
not this round) or the enemy was hit / clashed (interrupted) are counted apart, never in the main numbers.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from ssbot.combat.attack_range import (CELL, CHORISTOR, FT, Mask, RangeTable, Segmenter, Template, bin_of, hero_space,
                                       hurts, load_table, on_canvas, poly_mask, save_table, table_path, union)

OUT = Path(r"C:\ssbot\data\m2_forum_are\choristor")
SETS = {
    "dev": [Path(r"C:\ssbot\data\m2_forum_r0\cache")],
    "fresh": [Path(r"C:\ssbot\data\m2_forum_r0\cache_fresh")],
    "r2": [Path(r"C:\ssbot\data\m2_forum_r1c\cache")],         # filtered to the R2 fights (R2_FIGHTS)
}
R2_FIGHTS = Path(r"C:\ssbot\data\m2_forum_r2\r1\fights.json")
HUMAN = Path(r"C:\ssbot\data\human")
PERSON = ("20261004_002749", "20261004_012300", "20261004_091214", "20261004_133855", "20261005_160435",
          "20261008_230220", "20261008_231544", "20261009_085824", "20261009_161454")
SHAPE_SESSIONS = ("20261009_085824", "20261009_161454")
KS = (0, 6, 12)
U_RANGE = (-12.0, 16.0)          # the template canvas around the body (u forward, v up)
V_RANGE = (-10.0, 10.0)
NB_MAX = 240                     # 4 s
SIDES = ("front", "back", "up", "down", "inner")
TBIN = 0.2                       # s: the time buckets of the error tables
IDLE = "CH_IDLE"


def _idle_priority() -> None:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.SetPriorityClass.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        k32.SetPriorityClass(k32.GetCurrentProcess(), 0x40)      # IDLE_PRIORITY_CLASS


# ------------------------------------------------------------------------------------------------ tracks

def tracks_from_cache(c: dict, type_key: str, source: str) -> list[dict]:
    """Per enemy of type_key in one fight cache: its frames in order with state, time in state, position, flip, the
    hero position and its damage colliders [(name, AABB, flip)], the game times it was hit and of nail clashes."""
    types = list(c["types"])
    if type_key not in types:
        return []
    tk = types.index(type_key)
    sel = np.nonzero(c["e_tk"] == tk)[0]
    if not len(sel):
        return []
    names, states = c["names"], c["states"]
    cei = c["c_ei"]
    order = np.argsort(cei, kind="stable")
    ceis = cei[order]
    lo = np.searchsorted(ceis, sel, "left")
    hi = np.searchsorted(ceis, sel, "right")
    crow = {int(r): order[a:b] for r, a, b in zip(sel, lo, hi) if b > a}
    T = c["T"]
    fidx = {int(f): i for i, f in enumerate(c["f"])}
    hits: dict = defaultdict(list)
    clash: list = []
    for ev in c["events"]:
        f, kind, d = ev[0], ev[1], ev[2]
        i = fidx.get(int(f))
        if i is None:
            continue
        if kind == "hit":
            hits[int(d.get("ent", -1))].append(float(T[i]))
        elif kind == "freeze" and d.get("phase") == "start":
            ty = str(d.get("type"))
            if "lash" in ty or "arry" in ty or "Tink" in ty:
                clash.append(float(T[i]))
    out = []
    e_fi, e_iid = c["e_fi"], c["e_iid"]
    for iid in np.unique(e_iid[sel]):
        rows = sel[e_iid[sel] == iid]
        rows = rows[np.argsort(e_fi[rows], kind="stable")]
        fr = e_fi[rows]
        src = c["e_src"][rows]
        cols = []
        for r, sr in zip(rows, src):
            ix = crow.get(int(r))
            if ix is None:
                cols.append([])
                continue
            cols.append([(str(names[c["c_name"][x]]), c["c_box"][x].astype(np.float64))
                         for x in ix if hurts(int(c["c_dealt"][x]), int(c["c_eff"][x]), int(sr))])
        st = c["e_st"][rows]
        out.append(dict(
            source=source, fight=c["meta"].get("id"), iid=int(iid), f=np.asarray(c["f"][fr], np.int64),
            T=np.asarray(T[fr], np.float64), st=[str(states[x]) if x >= 0 else None for x in st],
            tin=c["e_tin"][rows].astype(np.float64), x=c["e_x"][rows].astype(np.float64),
            y=c["e_y"][rows].astype(np.float64), flip=c["e_flip"][rows].astype(np.int8),
            hidden=c["e_hidden"][rows].astype(np.int8), hx=c["hx"][fr].astype(np.float64),
            hy=c["hy"][fr].astype(np.float64), cols=cols, hits=sorted(hits.get(int(iid), [])), clash=sorted(clash)))
    return out


def _cache_files(name: str) -> list[Path]:
    files = []
    for d in SETS[name]:
        files += sorted(d.glob("*.npz"))
    if name == "r2":
        from ssbot.knowledge.forum_cache import cache_name
        ids = {cache_name(f["id"]) for f in json.loads(R2_FIGHTS.read_text("utf-8"))["fights"]}
        files = [f for f in files if f.name in ids or f.stem in ids]
    return files


def load_tracks(name: str, type_key: str = CHORISTOR.type_key, cache_dir: Path | None = None,
                sessions=PERSON) -> list[dict]:
    """The tracks of one set (person: pickled under OUT after the first decode)."""
    from ssbot.knowledge.forum_cache import extract_states, load_cache
    if name != "person":
        out = []
        for f in _cache_files(name):
            out += tracks_from_cache(load_cache(f), type_key, name)
        return out
    from ssbot.tools.forum_human_score import load_segment, segments
    cache_dir = cache_dir or OUT / "person_tracks"
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for sess in sessions:
        p = cache_dir / f"{sess}.pkl"
        if p.exists():
            with open(p, "rb") as fh:
                out += pickle.load(fh)
            continue
        tr = []
        d = HUMAN / sess
        if (d / "state.raw.zst").exists():
            for seg in segments(f"{d}:win", None):
                _, states = load_segment(seg)
                fmap = {int(s["f"]): int(s.get("_f_raw", s["f"])) for s in states}
                c = extract_states(states, {"id": f"{sess}/a{seg['attempt']}"})
                for t in tracks_from_cache(c, type_key, "person"):
                    # the raw frame as the frame number (the video's labels; game frames merged at 0.5x)
                    t["f"] = np.array([fmap.get(int(x), int(x)) for x in t["f"]], np.int64)
                    tr.append(t)
        tmp = p.with_name(p.name + f".{os.getpid()}.tmp")
        with open(tmp, "wb") as fh:
            pickle.dump(tr, fh, protocol=4)
        os.replace(tmp, p)
        out += tr
    return out


# ------------------------------------------------------------------------------------------------ polygons

def shapes_from_states(states, type_key: str = CHORISTOR.type_key) -> dict:
    """{collider name: {flip: rel polygon}}: the exported polygon relative to its AABB's lower-left corner."""
    out: dict = {}
    for s in states:
        for e in s.get("ents") or ():
            if e.get("type_key") != type_key:
                continue
            flip = 1 if e.get("flipX") else 0
            for c in e.get("cols") or e.get("colliders") or ():
                v = c.get("verts_world")
                if not v or len(v) < 6 or not c.get("damage"):
                    continue
                p = np.asarray(v, np.float64).reshape(-1, 2)
                rel = p - p.min(axis=0)
                d = out.setdefault(str(c.get("name")), {})
                if str(flip) not in d:
                    d[str(flip)] = np.round(rel, 4).tolist()
    return out


def poly_of(name: str, box, flip: int, shapes: dict) -> np.ndarray:
    """The exact polygon of a rigid collider from its AABB (the AABB itself when its shape is unknown)."""
    x0, y0, x1, y1 = (float(v) for v in box)
    rel = (shapes.get(name) or {}).get(str(int(flip)))
    if rel is not None:
        r = np.asarray(rel, np.float64)
        ext = r.max(axis=0)
        if abs(ext[0] - (x1 - x0)) < 0.02 and abs(ext[1] - (y1 - y0)) < 0.02:
            return r + (x0, y0)
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], np.float64)


def frame_polys(tr: dict, j: int, shapes: dict, only: str | None = None) -> list[np.ndarray]:
    return [poly_of(nm, bx, int(tr["flip"][j]), shapes) for nm, bx in tr["cols"][j] if only is None or nm == only]


# ------------------------------------------------------------------------------------------------ segmentation

def segment(tr: dict, spec, face_flip1: int) -> tuple[list, np.ndarray]:
    """(instances, per-frame instance index or -1) of one track, with the live tracker's rule."""
    seg = Segmenter(spec)
    insts: list = []
    idx = np.full(len(tr["T"]), -1, np.int32)
    last = None
    for j in range(len(tr["T"])):
        st = tr["st"][j]
        s = face_flip1 if tr["flip"][j] else -face_flip1
        if tr["hidden"][j]:
            st = None
        inst = seg.step(st, float(tr["T"][j]), float(tr["x"][j]), float(tr["y"][j]), s, float(tr["hx"][j]),
                        float(tr["tin"][j]))
        if inst is None:
            last = None
            continue
        if inst is not last:
            insts.append({"inst": inst, "j0": j, "frames": []})
            last = inst
        insts[-1]["frames"].append(j)
        idx[j] = len(insts) - 1
    for r in insts:
        r["j1"] = r["frames"][-1]
        inst = r["inst"]
        t1 = float(tr["T"][r["j1"]])
        r["interrupted"] = any(inst.t0 - 0.05 <= h <= t1 + 0.05 for h in tr["hits"]) or \
            any(inst.t0 - 0.05 <= h <= t1 + 0.05 for h in tr["clash"])
    return insts, idx


def facing_of_flip(tracks: list[dict]) -> int:
    """+1 when flipX = 1 means facing +x: from where the attack colliders sit relative to the enemy."""
    votes = 0.0
    for tr in tracks:
        for j, cols in enumerate(tr["cols"]):
            for nm, bx in cols:
                if nm.startswith(("Slash Hit", "Whip Hit 2")):
                    d = 0.5 * (bx[0] + bx[2]) - tr["x"][j]
                    votes += math.copysign(1.0, d) * (1 if tr["flip"][j] else -1)
    return 1 if votes >= 0 else -1


# ------------------------------------------------------------------------------------------------ build

def _rel(polys, x: float, y: float, s: int) -> list[np.ndarray]:
    out = []
    for p in polys:
        q = np.empty_like(p)
        q[:, 0] = (p[:, 0] - x) * s
        q[:, 1] = p[:, 1] - y
        out.append(q)
    return out


def build(tracks: list[dict], spec=CHORISTOR, shapes: dict | None = None) -> tuple[RangeTable, dict]:
    """The table from the dev tracks (clean instances only) and the build report."""
    shapes = shapes or {}
    f1 = facing_of_flip(tracks)
    per: dict = defaultdict(list)            # (fam, branch) -> [(track, instance record)]
    xs = []
    body_rel = None
    for tr in tracks:
        insts, _ = segment(tr, spec, f1)
        for r in insts:
            inst = r["inst"]
            xs += [float(tr["x"][j]) for j in r["frames"]]
            if r["interrupted"]:
                continue
            br = inst.branch if len(spec.branches.get(inst.fam, ())) > 1 else spec.branches[inst.fam][0]
            if br is None:
                continue
            per[(inst.fam, br)].append((tr, r))
            if body_rel is None:
                for j in r["frames"]:
                    bp = frame_polys(tr, j, shapes, spec.body)
                    if bp:
                        body_rel = _rel(bp, tr["x"][j], tr["y"][j], inst.s)
                        break
    walls = (float(np.min(xs)), float(np.max(xs))) if xs else (-1e9, 1e9)
    iu_lo, iu_hi = int(math.floor(U_RANGE[0] / CELL)), int(math.ceil(U_RANGE[1] / CELL))
    iv_lo, iv_hi = int(math.floor(V_RANGE[0] / CELL)), int(math.ceil(V_RANGE[1] / CELL))
    nu, nv = iu_hi - iu_lo, iv_hi - iv_lo
    tps = {}
    report: dict = {"face_flip1": f1, "walls": walls, "families": {}}
    jump_fit, jump_lmax = (1.0, 0.0), 15.0
    for (fam, br), items in sorted(per.items()):
        ends = [bin_of(float(tr["T"][r["j1"]]) - r["inst"].t0) for tr, r in items]
        nb = min(max(ends) + 1, NB_MAX)
        cnt = np.zeros((nb, nv, nu), np.uint16)
        D = np.full((len(items), nb, 2), np.nan)
        for n, (tr, r) in enumerate(items):
            inst = r["inst"]
            done = set()
            last_d, last_j = None, r["j1"]
            for j in r["frames"]:
                b = bin_of(float(tr["T"][j]) - inst.t0)
                if b >= nb or b < 0:
                    continue
                polys = _rel(frame_polys(tr, j, shapes), tr["x"][j], tr["y"][j], inst.s)
                _add(cnt[b], polys, iu_lo, iv_lo)
                D[n, b] = ((tr["x"][j] - inst.x0) * inst.s, tr["y"][j] - inst.y0)
                done.add(b)
            last_d = ((tr["x"][last_j] - inst.x0) * inst.s, tr["y"][last_j] - inst.y0)
            b_end = bin_of(float(tr["T"][last_j]) - inst.t0)
            if body_rel is not None:                 # ended: the idle body at its end position
                for b in range(b_end + 1, nb):
                    _add(cnt[b], body_rel, iu_lo, iv_lo)
                    D[n, b] = last_d
        shape, origin = [], np.zeros((nb, 2), np.int32)
        for b in range(nb):
            m = cnt[b] > 0
            rr, cc = np.nonzero(m)
            if not len(rr):
                shape.append(np.zeros((0, 0), bool))
                continue
            shape.append(m[rr.min():rr.max() + 1, cc.min():cc.max() + 1].copy())
            origin[b] = (iu_lo + cc.min(), iv_lo + rr.min())
        with np.errstate(all="ignore"):
            disp = np.nanmedian(D, axis=0)
        for b in range(nb):                          # a bin no instance had a frame in: the previous value
            if not np.isfinite(disp[b]).all():
                disp[b] = disp[b - 1] if b else (0.0, 0.0)
        ratio = None
        if fam in spec.aim:
            L = np.array([D[n, :, 0][np.isfinite(D[n, :, 0])][-1] for n in range(len(items))])
            du = np.array([r["inst"].hero_du for _, r in items])
            A = np.stack([du, np.ones_like(du)], 1)
            coef, *_ = np.linalg.lstsq(A, L, rcond=None)
            jump_fit = (float(coef[0]), float(coef[1]))
            jump_lmax = float(np.max(np.abs(L)))
            ok = np.abs(L) >= 1.0
            with np.errstate(all="ignore"):
                ratio = np.nanmedian(D[ok, :, 0] / L[ok, None], axis=0)
            ratio = np.where(np.isfinite(ratio), ratio, 0.0)
            res = L - A @ coef
            report["jump"] = {"fit": jump_fit, "lmax": jump_lmax, "n": int(len(L)),
                              "resid_p95": float(np.percentile(np.abs(res), 95)), "resid_max": float(np.abs(res).max())}
        tps[(fam, br)] = Template(nb=nb, shape=shape, origin=origin, disp=disp, ratio=ratio, n=len(items))
        report["families"][f"{fam}|{br}"] = _shape_report(tps[(fam, br)], ends)
    # CH_HOP's direction (Hop Check: forward only when the hero is farther than Hop Distance 6-10 u): certain outside
    # the range of the hero's offsets at the antic start where both directions were recorded
    rule = {}
    fw = [r["inst"].hero_du for _, r in per.get(("CH_HOP", "forward"), [])]
    bk = [r["inst"].hero_du for _, r in per.get(("CH_HOP", "back"), [])]
    if fw and bk:
        rule["CH_HOP"] = {"lo": float(min(fw)), "hi": float(max(bk)), "below": "back", "above": "forward"}
        report["branch_rule"] = rule
    meta = {"face_flip1": f1, "walls": walls, "jump_fit": jump_fit, "jump_lmax": jump_lmax, "shapes": shapes,
            "branch_rule": rule,
            "body_rel": [p.tolist() for p in body_rel] if body_rel is not None else None,
            "source": "R0 dev (C:/ssbot/data/m2_forum_r0/cache), clean instances", "hero_box": [0.4554, 2.2498, -0.38]}
    return RangeTable(spec=spec, templates=tps, meta=meta), report


def _add(acc: np.ndarray, polys, iu_lo: int, iv_lo: int) -> None:
    m = poly_mask(polys)
    if not m.m.size:
        return
    r0, c0 = m.iy0 - iv_lo, m.ix0 - iu_lo
    nv, nu = acc.shape
    a0, b0 = max(r0, 0), max(c0, 0)
    a1, b1 = min(r0 + m.m.shape[0], nv), min(c0 + m.m.shape[1], nu)
    if a1 > a0 and b1 > b0:
        acc[a0:a1, b0:b1] += m.m[a0 - r0:a1 - r0, b0 - c0:b1 - c0]


def _shape_report(tp: Template, ends: list) -> dict:
    """Per family / branch: instances, duration, and per 0.1 s the raw extent of the union relative to the anchor
    (front / back / up / down, u, with the median displacement) and its area (u^2)."""
    rows = []
    for b in range(0, tp.nb, 6):
        sh = tp.shape[b]
        if not sh.size:
            continue
        u0 = tp.origin[b, 0] * CELL + tp.disp[b, 0]
        v0 = tp.origin[b, 1] * CELL + tp.disp[b, 1]
        rows.append({"t": round(b * FT, 2), "front": round(float(u0 + sh.shape[1] * CELL), 2),
                     "back": round(float(-u0), 2), "up": round(float(v0 + sh.shape[0] * CELL), 2),
                     "down": round(float(-v0), 2), "area": round(float(sh.sum()) * CELL * CELL, 2),
                     "disp": [round(float(tp.disp[b, 0]), 2), round(float(tp.disp[b, 1]), 2)]})
    e = np.asarray(ends) * FT
    return {"n": tp.n, "bins": tp.nb, "dur_p50": round(float(np.median(e)), 3), "dur_max": round(float(e.max()), 3),
            "extent": rows}


# ------------------------------------------------------------------------------------------------ the error

def compare(E: Mask, R: Mask, s: int, cell: float = CELL) -> dict:
    """Estimate E against the real damage R (raw rasters) in hero-centre space: areas (u^2), the miss (real cells
    outside E: how far, u, by side of E's box in the facing frame) and the excess (E cells outside R: how far beyond
    R, by side of R's box)."""
    import cv2
    HE, HR = hero_space(E, cell), hero_space(R, cell)
    U = union([HE, HR])
    if not U.m.size:
        return {"aE": 0.0, "aR": 0.0, "aI": 0.0, "miss": {}, "exc": {}}
    e = on_canvas(HE, U.ix0, U.iy0, U.m.shape)
    r = on_canvas(HR, U.ix0, U.iy0, U.m.shape)
    a2 = cell * cell
    out = {"aE": float(e.sum()) * a2, "aR": float(r.sum()) * a2, "aI": float((e & r).sum()) * a2}

    def by_side(sel, ref):
        if not sel.any():
            return {}
        if not ref.any():
            return {"inner": [99.0, float(sel.sum()) * a2]}
        pad = np.pad((~ref).astype(np.uint8), 1, constant_values=1)
        dist = cv2.distanceTransform(pad, cv2.DIST_L2, 5)[1:-1, 1:-1] * cell
        rr, cc = np.nonzero(ref)
        r0, r1, c0, c1 = rr.min(), rr.max(), cc.min(), cc.max()
        yy, xx = np.nonzero(sel)
        dxp, dxn = xx - c1, c0 - xx
        dy_u, dy_d = yy - r1, r0 - yy
        fr, bk = (dxp, dxn) if s >= 0 else (dxn, dxp)
        stack = np.stack([fr, bk, dy_u, dy_d], 0)
        k = np.argmax(stack, 0)
        side = np.where(stack.max(0) > 0, k, 4)
        d = dist[yy, xx]
        res = {}
        for i, nm in enumerate(SIDES):
            q = side == i
            if q.any():
                res[nm] = [round(float(d[q].max()), 3), round(float(q.sum()) * a2, 4)]
        return res
    out["miss"] = by_side(r & ~e, e)
    out["exc"] = by_side(e & ~r, r)
    return out


def _target(T: np.ndarray, j: int, k: int) -> int | None:
    t = T[j] + k * FT - 1e-6
    jt = int(np.searchsorted(T, t, "left"))
    return jt if jt < len(T) else None


def eval_track(tr: dict, tab: RangeTable, shapes: dict, every: int = 2, idle_every: int = 6, ks=KS,
               antic_anchor: bool = False) -> list[dict]:
    """Error rows of one track; antic_anchor: the position from the antic start alone (no re-anchoring at the
    observed position, the first variant)."""
    spec = tab.spec
    f1 = int(tab.meta.get("face_flip1", 1))
    insts, idx = segment(tr, spec, f1)
    T = tr["T"]
    rows = []
    for n, r in enumerate(insts):
        inst = r["inst"]
        for j in r["frames"][::every]:
            b = bin_of(float(T[j]) - inst.t0)
            br = inst.branch if (inst.branch_t is not None and inst.branch_t <= T[j] + 1e-9) else None
            for k in ks:
                jt = _target(T, j, k)
                if jt is None:
                    continue
                nxt = bool(((idx[j:jt + 1] >= 0) & (idx[j:jt + 1] != n)).any())
                # the estimate for the game time of the real frame compared (the first frame reaching t + k/60 can be
                # a frame later: comparing bin b + k with it would count that frame-sampling jitter as error)
                bt = bin_of(float(T[jt]) - inst.t0)
                E = tab.place(inst.fam, br, bt, (inst.x0, inst.y0), inst.s, inst.hero_du,
                              now=None if antic_anchor else (float(tr["x"][j]), float(tr["y"][j])), b_now=b)
                R = poly_mask(frame_polys(tr, jt, shapes))
                c = compare(E, R, inst.s)
                rows.append({"fam": inst.fam, "br": inst.branch, "known": br is not None, "k": k, "b": b,
                             "t": round(bt * FT, 4), "next": bool(nxt), "int": bool(r["interrupted"]),
                             "f": int(tr["f"][j]), "fight": tr["fight"], "iid": tr["iid"], **c})
    # idle: the exact body now, for every k
    for j in range(0, len(T), idle_every):
        if idx[j] >= 0 or tr["hidden"][j] or tr["st"][j] is None:
            continue
        st = str(tr["st"][j])
        if any(w in st for w in ("Ready", "Dormant", "Sleep", "Wait")):
            continue
        body = frame_polys(tr, j, shapes, spec.body)
        if not body:
            continue
        s = f1 if tr["flip"][j] else -f1
        E = poly_mask(body)
        hit = any(abs(h - T[j]) < 0.3 for h in tr["hits"])
        for k in ks:
            jt = _target(T, j, k)
            if jt is None:
                continue
            nxt = bool((idx[j:jt + 1] >= 0).any())
            R = poly_mask(frame_polys(tr, jt, shapes))
            c = compare(E, R, s)
            rows.append({"fam": IDLE, "br": st, "known": True, "k": k, "b": 0, "t": round(k * FT, 4), "next": nxt,
                         "int": hit, "f": int(tr["f"][j]), "fight": tr["fight"], "iid": tr["iid"], **c})
    return rows


def summarize(rows: list[dict], ks=KS, limit: float = 1.5) -> dict:
    """Per family x k: main rows (not next, not interrupted): RATIO, coverage, miss and excess per side, and the same
    per time bucket (t = (b + k) / 60 s since the antic start)."""
    out: dict = {}
    groups: dict = defaultdict(list)
    for r in rows:
        groups[(r["fam"], r["k"])].append(r)
    for (fam, k), rs in sorted(groups.items()):
        main = [r for r in rs if not r["next"] and not r["int"]]
        d = {"rows": len(rs), "main": len(main), "next": sum(r["next"] for r in rs),
             "interrupted": sum(r["int"] and not r["next"] for r in rs)}
        d.update(_stats(main, limit))
        allr = [r for r in rs if not r["next"]]
        d["with_interrupted"] = {"cover": _cov(allr), "miss_rows": _share([bool(r["miss"]) for r in allr])}
        if fam != IDLE:
            tb: dict = defaultdict(list)
            for r in main:
                tb[round(math.floor(r["t"] / TBIN) * TBIN, 2)].append(r)
            d["by_time"] = {str(t): _stats(v, limit, brief=True) for t, v in sorted(tb.items())}
            known = [r for r in main if r["known"]]
            if len(known) != len(main):
                d["branch_known"] = _stats(known, limit, brief=True)
        out.setdefault(fam, {})[f"k{k}"] = d
    return out


def _share(v) -> float | None:
    return round(float(np.mean(v)), 4) if len(v) else None


def _cov(rs) -> float | None:
    aR = sum(r["aR"] for r in rs)
    return round(sum(r["aI"] for r in rs) / aR, 5) if aR > 0 else None


def _q(v, ps=(50, 90, 95, 100)) -> dict | None:
    v = [x for x in v if x is not None and np.isfinite(x)]
    if not v:
        return None
    return {("max" if p == 100 else f"p{p}"): round(float(np.percentile(v, p)), 3) for p in ps}


def _stats(rs: list[dict], limit: float, brief: bool = False) -> dict:
    if not rs:
        return {"n": 0}
    with_r = [r for r in rs if r["aR"] > 0]
    ratios = [r["aE"] / r["aR"] for r in with_r]
    d = {"n": len(rs), "ratio_area": round(sum(r["aE"] for r in with_r) / max(sum(r["aR"] for r in with_r), 1e-9), 3),
         "ratio": _q(ratios), "ratio_ok": _share([x <= limit for x in ratios]), "cover": _cov(rs),
         "miss_rows": _share([bool(r["miss"]) for r in rs])}
    miss, exc = {}, {}
    for side in SIDES:
        m = [r["miss"][side][0] for r in rs if side in r["miss"]]
        if m:
            miss[side] = {"rows": round(len(m) / len(rs), 4), "dist": _q(m, (50, 95, 100))}
        x = [r["exc"][side][1] / r["aE"] for r in rs if r["aE"] > 0 and side in r["exc"]]
        xd = [r["exc"][side][0] for r in rs if side in r["exc"]]
        if x:
            exc[side] = {"share_p50": round(float(np.median(x)), 3), "dist": _q(xd, (50, 95, 100))}
    d["miss"] = miss
    d["excess"] = exc
    if not brief:
        d["excess_share"] = _q([1.0 - r["aI"] / r["aE"] for r in rs if r["aE"] > 0], (50, 90))
        d["empty_real"] = sum(r["aR"] == 0 for r in rs)
    return d


# ------------------------------------------------------------------------------------------------ commands

def cmd_shapes(a) -> int:
    from ssbot.tools.forum_human_score import load_segment, segments
    shapes: dict = {}
    for sess in SHAPE_SESSIONS:
        for seg in segments(f"{HUMAN / sess}:win", None):
            _, states = load_segment(seg)
            for nm, d in shapes_from_states(states).items():
                for fl, p in d.items():
                    shapes.setdefault(nm, {}).setdefault(fl, p)
    p = OUT / "shapes.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(shapes), "utf-8")
    print(f"{p}: {', '.join(f'{k} {sorted(v)}' for k, v in sorted(shapes.items()))}")
    return 0


def _shapes() -> dict:
    p = OUT / "shapes.json"
    return json.loads(p.read_text("utf-8")) if p.exists() else {}


def cmd_build(a) -> int:
    _idle_priority()
    t0 = time.time()
    tracks = load_tracks("dev")
    print(f"dev tracks: {len(tracks)} ({time.time() - t0:.0f} s)")
    tab, rep = build(tracks, CHORISTOR, _shapes())
    p = save_table(tab, Path(a.out) if a.out else table_path(CHORISTOR))
    rep["table"] = str(p)
    rep["bytes"] = p.stat().st_size
    jp = p.with_suffix(".json")
    jp.write_text(json.dumps(rep, indent=1), "utf-8")
    print(f"{p} ({p.stat().st_size} B), report {jp}; families "
          + ", ".join(f"{k} n {v['n']} dur {v['dur_p50']}/{v['dur_max']} s" for k, v in rep["families"].items()))
    if "jump" in rep:
        print("jump", rep["jump"])
    return 0


def cmd_eval(a) -> int:
    _idle_priority()
    tab = load_table(Path(a.table) if a.table else None)
    shapes = tab.meta.get("shapes") or {}
    t0 = time.time()
    tracks = load_tracks(a.set)
    print(f"{a.set}: {len(tracks)} tracks ({time.time() - t0:.0f} s)", flush=True)
    rows = []
    for i, tr in enumerate(tracks):
        rows += eval_track(tr, tab, shapes, every=a.every)
        if i % 50 == 0:
            print(f"  {i}/{len(tracks)} rows {len(rows)} ({time.time() - t0:.0f} s)", flush=True)
    summ = summarize(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"eval_{a.set}.json").write_text(json.dumps({"set": a.set, "rows": len(rows), "summary": summ}, indent=1),
                                            "utf-8")
    with open(OUT / f"rows_{a.set}.pkl", "wb") as fh:
        pickle.dump(rows, fh, protocol=4)
    for fam, d in summ.items():
        for kk in ("k0", "k12"):
            x = d.get(kk) or {}
            print(f"{fam:9s} {kk:3s} main {x.get('main')} ratio_area {x.get('ratio_area')} ratio {x.get('ratio')} "
                  f"ok {x.get('ratio_ok')} cover {x.get('cover')} miss_rows {x.get('miss_rows')}")
    print(f"done ({time.time() - t0:.0f} s)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("shapes")
    b = sub.add_parser("build")
    b.add_argument("--out", default=None)
    e = sub.add_parser("eval")
    e.add_argument("--set", required=True, choices=("dev", "fresh", "r2", "person"))
    e.add_argument("--every", type=int, default=2)
    e.add_argument("--table", default=None)
    pg = sub.add_parser("png")
    pg.add_argument("--out", default=str(OUT / "png"))
    tk = sub.add_parser("tracks", help="decode the person's sessions into OUT/person_tracks (pickles)")
    tk.add_argument("--sessions", default=",".join(PERSON))
    a = ap.parse_args(argv)
    if a.cmd == "tracks":
        _idle_priority()
        tr = load_tracks("person", sessions=[x for x in a.sessions.split(",") if x])
        print(f"{len(tr)} tracks")
        return 0
    if a.cmd == "shapes":
        return cmd_shapes(a)
    if a.cmd == "build":
        return cmd_build(a)
    if a.cmd == "eval":
        return cmd_eval(a)
    if a.cmd == "png":
        from ssbot.tools.attack_range_png import cmd_png
        return cmd_png(a)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
