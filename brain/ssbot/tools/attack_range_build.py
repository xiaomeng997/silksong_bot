"""Attack-range estimate (ARE) builder and its estimation error (Task "attack range", the person 2026-10-10:
estimate each enemy's attack range accurately first, with no margin; the margin is a later decision from this error).
The model is ssbot.combat.attack_range (its docstring); one enemy type at a time (a module under
ssbot.combat.are_types each: --type <short name>, default the Choristor; outputs under
C:/ssbot/data/m2_forum_are/<short>).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.attack_range_build [--type clapper] shapes   # collider polygons
    ../scripts/uv.cmd run python -m ssbot.tools.attack_range_build [--type clapper] build    # R0 dev only -> table
    ../scripts/uv.cmd run python -m ssbot.tools.attack_range_build [--type ...] eval --set fresh|r2|person|dev
    ../scripts/uv.cmd run python -m ssbot.tools.attack_range_build [--type ...] png          # PNGs of the frames
    ../scripts/uv.cmd run python -m ssbot.tools.attack_range_build [--type ...] hazcheck     # hazards: lit vs hurt
    ../scripts/uv.cmd run python -m ssbot.tools.attack_range_build tracks                    # decode the person's

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
import dataclasses
import json
import math
import os
import pickle
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from ssbot.combat.attack_range import (CELL, CHORISTOR, FT, SPECS, Mask, RangeTable, Segmenter, Template, bin_of,
                                       circle_poly, hazards_at, hero_space, hurts, load_table, on_canvas, poly_mask,
                                       save_table, table_path, type_extra, union)

ARE = Path(r"C:\ssbot\data\m2_forum_are")
OUT = ARE / "choristor"
PERSON_CACHE = ARE / "person_cache"        # the person's sessions as per-attempt Forum caches (every type reads them)
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
STATE_MIN = 2                    # state-gated: a state is kept at a bin when >= 2 R0 dev instances were in it there
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
    """Per enemy of type_key in one fight cache: its frames in order with state, time in state, position, velocity,
    flip, the hero position and its damage colliders [(name, AABB, flip)], the game times it was hit and of nail
    clashes (fi: the cache's frame index of each frame)."""
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
            hy=c["hy"][fr].astype(np.float64), cols=cols, hits=sorted(hits.get(int(iid), [])), clash=sorted(clash),
            fi=np.asarray(fr, np.int64), vx=c["e_vx"][rows].astype(np.float64),
            vy=c["e_vy"][rows].astype(np.float64) if "e_vy" in c else None))
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


def load_tracks(name: str, type_key: str | None = None, cache_dir: Path | None = None, sessions=PERSON,
                spec=None) -> list[dict]:
    """The tracks of one set for one type (person: from the shared per-attempt caches, decoded on first use), with
    the hazards the type owns attached (attach_hazards)."""
    from ssbot.knowledge.forum_cache import load_cache
    spec = spec or SPECS.get(type_key or CHORISTOR.type_key, CHORISTOR)
    files = person_caches(sessions, cache_dir) if name == "person" else _cache_files(name)
    out = []
    for f in files:
        c = load_cache(f)
        trs = tracks_from_cache(c, spec.type_key, name)
        if name == "person" and "f_raw" in c:
            for t in trs:
                # the raw frame as the frame number (the video's labels; game frames merged at 0.5x)
                t["f"] = np.asarray(c["f_raw"][t["fi"]], np.int64)
        if spec.hazards and trs:
            attach_hazards(c, trs, spec)
        att = getattr(_module(spec), "attach", None)
        if att is not None and trs:       # stage B: the type's projectiles (tr["objs"] per frame, "OBJ:" cols)
            att(c, trs, spec)
        out += trs
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
    """The exact polygon of a rigid collider from its AABB (the AABB itself when its shape is unknown); a hazard
    ("HZ:<name>", a circle collider) is its AABB's inscribed circle."""
    x0, y0, x1, y1 = (float(v) for v in box)
    if name.startswith("HZ:"):
        return circle_poly(0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * (x1 - x0))
    rel = (shapes.get(name) or {}).get(str(int(flip)))
    if rel is not None:
        r = np.asarray(rel, np.float64)
        ext = r.max(axis=0)
        if abs(ext[0] - (x1 - x0)) < 0.02 and abs(ext[1] - (y1 - y0)) < 0.02:
            return r + (x0, y0)
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], np.float64)


def frame_polys(tr: dict, j: int, shapes: dict, only=None, hz: bool | None = None) -> list[np.ndarray]:
    """The damage polygons of frame j: all, only those named `only` (a name or names), hz True / False: only the
    hazards' / only the enemy's own."""
    names = None if only is None else ((only,) if isinstance(only, str) else tuple(only))
    # "OBJ:<name>" (stage B): a type module's projectile pieces (attach), hazards like "HZ:" but drawn as AABBs
    return [poly_of(nm, bx, int(tr["flip"][j]), shapes) for nm, bx in tr["cols"][j]
            if (names is None or nm in names) and (hz is None or nm.startswith(("HZ:", "OBJ:")) == hz)]


# ------------------------------------------------------------------------------------------------ segmentation

def segment(tr: dict, spec, face_flip1: int) -> tuple[list, np.ndarray]:
    """(instances, per-frame instance index or -1) of one track, with the live tracker's rule."""
    seg = Segmenter(spec)
    insts: list = []
    idx = np.full(len(tr["T"]), -1, np.int32)
    last = None
    vx = tr.get("vx")
    for j in range(len(tr["T"])):
        st = tr["st"][j]
        s = face_flip1 if tr["flip"][j] else -face_flip1
        if tr["hidden"][j]:
            st = None
        inst = seg.step(st, float(tr["T"][j]), float(tr["x"][j]), float(tr["y"][j]), s, float(tr["hx"][j]),
                        float(tr["tin"][j]), vx=None if vx is None else float(vx[j]), hero_y=float(tr["hy"][j]))
        if inst is None:
            last = None
            continue
        if inst is not last:
            insts.append({"inst": inst, "j0": j, "frames": []})
            last = inst
        insts[-1]["frames"].append(j)
        idx[j] = len(insts) - 1
    hs = getattr(spec, "hit_started", frozenset())
    for r in insts:
        r["j1"] = r["frames"][-1]
        inst = r["inst"]
        t1 = float(tr["T"][r["j1"]])
        # a hit-started family (stage B: counters) is not interrupted by the hit that starts it
        lo = inst.t0 + 0.05 if inst.fam in hs else inst.t0 - 0.05
        r["interrupted"] = any(lo <= h <= t1 + 0.05 for h in tr["hits"]) or \
            any(lo <= h <= t1 + 0.05 for h in tr["clash"])
    return insts, idx


def facing_of_flip(tracks: list[dict], names=("Slash Hit", "Whip Hit 2"), default: int = 1) -> int:
    """+1 when flipX = 1 means facing +x: from where the attack colliders (names: prefixes) sit relative to the
    enemy (default without any)."""
    votes = 0.0
    names = tuple(names)
    for tr in tracks:
        for j, cols in enumerate(tr["cols"]):
            for nm, bx in cols:
                if nm.startswith(names):
                    d = 0.5 * (bx[0] + bx[2]) - tr["x"][j]
                    votes += math.copysign(1.0, d) * (1 if tr["flip"][j] else -1)
    if votes == 0:
        return default
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


def build(tracks: list[dict], spec=None, shapes: dict | None = None) -> tuple[RangeTable, dict]:
    """The table from the dev tracks (clean instances only) and the build report. A decided family (spec.decide)
    is aligned at its decision: bins from the median decision bin count frames since the decision, their shapes and
    displacements are taken in the decision's frame (position, facing s) and the u displacement is ratio x L."""
    spec = spec or CHORISTOR
    shapes = shapes or {}
    f1 = facing_of_flip(tracks, spec.face_names or ("Slash Hit", "Whip Hit 2"))
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
            if inst.fam in spec.decide and inst.dec is None:
                continue
            per[(inst.fam, br)].append((tr, r))
            if body_rel is None:
                for j in r["frames"]:
                    bp = frame_polys(tr, j, shapes, spec.body_names)
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
        decided = fam in spec.decide
        b_dec = int(np.median([r["inst"].dec["b"] for _, r in items])) if decided else None

        def tbin(tr, r, j):
            inst = r["inst"]
            t = float(tr["T"][j])
            if decided and t >= inst.dec["t"] - 1e-9:
                return b_dec + bin_of(t - inst.dec["t"]), True
            return bin_of(t - inst.t0), False
        ends = [tbin(tr, r, r["j1"])[0] for tr, r in items]
        nb = min(max(ends) + 1, NB_MAX)
        cnt = np.zeros((nb, nv, nu), np.uint16)
        D = np.full((len(items), nb, 2), np.nan)
        sacc: dict = {}                          # state-gated: (bin, state) -> occupancy
        scnt: dict = defaultdict(set)            # ... and the instances in it
        first: dict = defaultdict(list)          # state -> the first bin of each instance in it
        for n, (tr, r) in enumerate(items):
            inst = r["inst"]
            last_j = r["j1"]
            seen_st: set = set()
            for j in r["frames"]:
                b, post = tbin(tr, r, j)
                if b >= nb or b < 0 or (decided and not post and b >= b_dec):
                    continue
                if post:
                    sd, ax, ay = inst.dec["s"], inst.dec["x"], inst.dec["y"]
                else:
                    sd, ax, ay = inst.s, inst.x0, inst.y0
                polys = _rel(frame_polys(tr, j, shapes, hz=False), tr["x"][j], tr["y"][j], sd)   # own colliders
                _add(cnt[b], polys, iu_lo, iv_lo)
                D[n, b] = ((tr["x"][j] - ax) * sd, tr["y"][j] - ay)
                if spec.state_gate:
                    st = str(tr["st"][j])
                    a_ = sacc.get((b, st))
                    if a_ is None:
                        a_ = sacc[(b, st)] = np.zeros((nv, nu), bool)
                    _add(a_, polys, iu_lo, iv_lo)
                    scnt[(b, st)].add(n)
                    if st not in seen_st:
                        seen_st.add(st)
                        first[st].append(b)
            b_end, post = tbin(tr, r, last_j)
            sd, ax, ay = (inst.dec["s"], inst.dec["x"], inst.dec["y"]) if post else (inst.s, inst.x0, inst.y0)
            last_d = ((tr["x"][last_j] - ax) * sd, tr["y"][last_j] - ay)
            if body_rel is not None:                 # ended: the idle body at its end position
                for b in range(b_end + 1, nb):
                    _add(cnt[b], body_rel, iu_lo, iv_lo)
                    D[n, b] = last_d
                    if spec.state_gate:
                        a_ = sacc.get((b, "<end>"))
                        if a_ is None:
                            a_ = sacc[(b, "<end>")] = np.zeros((nv, nu), bool)
                        _add(a_, body_rel, iu_lo, iv_lo)
                        scnt[(b, "<end>")].add(n)
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
        if decided:
            # the landing: the u displacement from the decision at the end of the move; the rule's L against it
            L = np.array([D[n, b_dec:, 0][np.isfinite(D[n, b_dec:, 0])][-1]
                          if np.isfinite(D[n, b_dec:, 0]).any() else np.nan for n in range(len(items))])
            Lr = np.array([r["inst"].dec["L"] for _, r in items])
            ok = np.isfinite(L) & (np.abs(L) >= 1.0)
            ratio = np.zeros(nb)
            with np.errstate(all="ignore"):
                ratio[b_dec:] = np.nanmedian(D[ok, b_dec:, 0] / L[ok, None], axis=0)
            ratio = np.where(np.isfinite(ratio), ratio, 0.0)
            fin = np.isfinite(L)
            err = np.abs(L[fin] - Lr[fin])
            flips = []
            for tr, r in items:                      # the facing during the move vs the decision's s
                inst = r["inst"]
                for j in r["frames"]:
                    if float(tr["T"][j]) >= inst.dec["t"] + 2 * FT:
                        flips.append((f1 if tr["flip"][j] else -f1) == inst.dec["s"])
            report.setdefault("decisions", {})[f"{fam}|{br}"] = {
                "n": int(len(items)), "b_dec": b_dec,
                "b_dec_range": [int(min(r["inst"].dec["b"] for _, r in items)),
                                int(max(r["inst"].dec["b"] for _, r in items))],
                "landing_err_p50": round(float(np.median(err)), 3) if len(err) else None,
                "landing_err_p95": round(float(np.percentile(err, 95)), 3) if len(err) else None,
                "landing_err_max": round(float(err.max()), 3) if len(err) else None,
                "L_p50": round(float(np.median(L[fin])), 3) if fin.any() else None,     # stage B: the measured extent
                "facing_agrees": round(float(np.mean(flips)), 4) if flips else None}
        sst = order = None
        if spec.state_gate:
            med = {st: float(np.median(v)) for st, v in first.items()}
            ranked = sorted(med, key=lambda q: (med[q], q))
            order = {st: i for i, st in enumerate(ranked)}
            order["<end>"] = len(ranked)
            sst = [dict() for _ in range(nb)]
            dropped = 0
            for (b, st), a_ in sacc.items():
                if len(scnt[(b, st)]) < STATE_MIN:     # one instance alone (a jump cut short under a ledge): not
                    dropped += 1                       # drawn at k > 0; the k = 0 lookup takes the nearest bin
                    continue
                rr, cc = np.nonzero(a_)
                if len(rr):
                    sst[b][st] = (a_[rr.min():rr.max() + 1, cc.min():cc.max() + 1] > 0,
                                  int(iu_lo + cc.min()), int(iv_lo + rr.min()))
            report.setdefault("state_order", {})[f"{fam}|{br}"] = {st: round(med[st] * FT, 3) for st in ranked}
            report.setdefault("state_dropped", {})[f"{fam}|{br}"] = dropped
        tps[(fam, br)] = Template(nb=nb, shape=shape, origin=origin, disp=disp, ratio=ratio, n=len(items),
                                  b_dec=b_dec, sst=sst, order=order)
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
    if spec.hazards:
        meta["hazards"], report["hazards"] = fit_hazards(tracks, spec, f1)
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
    observed position, the first variant). Types with hazards: the estimate and the truth include the hazards (the
    rows of the families / idle), and each hazard has its own rows ("HZ <name>": its estimate against its real
    colliders, whenever either is non-empty)."""
    spec = tab.spec
    f1 = int(tab.meta.get("face_flip1", 1))
    insts, idx = segment(tr, spec, f1)
    T = tr["T"]
    rows = []
    spawned = sorted(((hz, *r["inst"].trig[hz.name]) for r in insts for hz in spec.hazards
                      if hz.name in r["inst"].trig), key=lambda q: q[1])
    ex = type_extra(spec)
    ex_name = getattr(_module(spec), "OBJ_NAME", "extra") if ex is not None else None
    objs = tr.get("objs")

    def hz_rows(j, jt, k, inst, base: dict):
        if not spec.hazards and ex is None:
            return None
        view = _active_view(inst, float(T[j]))
        pos = (float(tr["x"][j]), float(tr["y"][j]))
        sp = [q for q in spawned if q[1] <= T[j] + 1e-9]
        tt = float(T[jt])
        tot = []
        for hz in spec.hazards:
            Eh = hazards_at(tab, [q for q in sp if q[0] is hz], view, float(T[j]), pos, tt, only=hz.name)
            Rh = poly_mask(frame_polys(tr, jt, shapes, only=f"HZ:{hz.name}"))
            tot.append(Eh)
            if (Eh.m.size and Eh.m.any()) or (Rh.m.size and Rh.m.any()):
                rows.append({**base, "fam": f"HZ {hz.name}", "br": base["fam"], **compare(Eh, Rh, inst.s if inst
                                                                                          else 1)})
        if ex is not None:              # stage B: the type's own part (the Reed's pin) vs its "OBJ:" colliders
            Eh = ex(tab, view, float(T[j]), pos, tt, (objs[j] if objs is not None else ()))
            Rh = poly_mask(frame_polys(tr, jt, shapes, only=f"OBJ:{ex_name}"))
            tot.append(Eh)
            if (Eh.m.size and Eh.m.any()) or (Rh.m.size and Rh.m.any()):
                rows.append({**base, "fam": f"HZ {ex_name}", "br": base["fam"], **compare(Eh, Rh, inst.s if inst
                                                                                         else 1)})
        return union(tot)
    for n, r in enumerate(insts):
        inst = r["inst"]
        for j in r["frames"][::every]:
            b = bin_of(float(T[j]) - inst.t0)
            br = inst.branch if (inst.branch_t is not None and inst.branch_t <= T[j] + 1e-9) else None
            dec = inst.dec if (inst.dec is not None and inst.dec["t"] <= T[j] + 1e-9) else None
            for k in ks:
                jt = _target(T, j, k)
                if jt is None:
                    continue
                nxt = bool(((idx[j:jt + 1] >= 0) & (idx[j:jt + 1] != n)).any())
                # the estimate for the game time of the real frame compared (the first frame reaching t + k/60 can be
                # a frame later: comparing bin b + k with it would count that frame-sampling jitter as error)
                bt = bin_of(float(T[jt]) - inst.t0)
                E = tab.place(inst.fam, br, bt, (inst.x0, inst.y0), inst.s, inst.hero_du,
                              now=None if antic_anchor else (float(tr["x"][j]), float(tr["y"][j])), b_now=b, dec=dec,
                              st_now=tr["st"][j], vel=_vel(tr, j))
                base = {"fam": inst.fam, "br": inst.branch, "known": br is not None, "k": k, "b": b,
                        "t": round(bt * FT, 4), "next": bool(nxt), "int": bool(r["interrupted"]),
                        "f": int(tr["f"][j]), "fight": tr["fight"], "iid": tr["iid"]}
                if spec.decide.get(inst.fam) is not None:
                    base["dec"] = dec is not None
                Eh = hz_rows(j, jt, k, inst, base)
                if Eh is not None:
                    E = union([E, Eh])
                R = poly_mask(frame_polys(tr, jt, shapes))
                c = compare(E, R, inst.s)
                rows.append({**base, **c})
    # idle: the exact body now, for every k
    for j in range(0, len(T), idle_every):
        if idx[j] >= 0 or tr["hidden"][j] or tr["st"][j] is None:
            continue
        st = str(tr["st"][j])
        if any(w in st for w in spec.parked):
            continue
        body = frame_polys(tr, j, shapes, spec.body_names)
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
            base = {"fam": IDLE, "br": st, "known": True, "k": k, "b": 0, "t": round(k * FT, 4), "next": nxt,
                    "int": hit, "f": int(tr["f"][j]), "fight": tr["fight"], "iid": tr["iid"]}
            Eh = hz_rows(j, jt, k, None, base)
            Ek = E if Eh is None else union([E, Eh])
            R = poly_mask(frame_polys(tr, jt, shapes))
            c = compare(Ek, R, s)
            rows.append({**base, **c})
    return rows


def _vel(tr: dict, j: int) -> tuple | None:
    """The enemy's velocity at frame j (stage B: EnemySpec.coast states), None when the track has no vy."""
    return (float(tr["vx"][j]), float(tr["vy"][j])) if tr.get("vy") is not None else None


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
    spec = spec_of(a.type)
    mod = _module(spec)
    shapes: dict = {}
    for sess in getattr(mod, "SESSIONS", SHAPE_SESSIONS):
        for seg in segments(f"{HUMAN / sess}:win", None):
            _, states = load_segment(seg)
            for nm, d in shapes_from_states(states, spec.type_key).items():
                for fl, p in d.items():
                    shapes.setdefault(nm, {}).setdefault(fl, p)
    p = out_dir(spec) / "shapes.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(shapes), "utf-8")
    print(f"{p}: {', '.join(f'{k} {sorted(v)}' for k, v in sorted(shapes.items()))}")
    return 0


def _shapes(spec=None) -> dict:
    p = out_dir(spec) / "shapes.json"
    return json.loads(p.read_text("utf-8")) if p.exists() else {}


def cmd_build(a) -> int:
    _idle_priority()
    spec = spec_of(a.type)
    t0 = time.time()
    tracks = load_tracks("dev", spec=spec)
    print(f"dev tracks: {len(tracks)} ({time.time() - t0:.0f} s)")
    tab, rep = build(tracks, spec, _shapes(spec))
    p = save_table(tab, Path(a.out) if a.out else table_path(spec))
    rep["table"] = str(p)
    rep["bytes"] = p.stat().st_size
    rep["left_out"] = [list(x) for x in spec.left_out]
    jp = p.with_suffix(".json")
    jp.write_text(json.dumps(rep, indent=1), "utf-8")
    print(f"{p} ({p.stat().st_size} B), report {jp}; families "
          + ", ".join(f"{k} n {v['n']} dur {v['dur_p50']}/{v['dur_max']} s" for k, v in rep["families"].items()))
    for k in ("jump", "decisions", "hazards"):
        if k in rep:
            print(k, json.dumps(rep[k])[:3000])
    return 0


def cmd_eval(a) -> int:
    _idle_priority()
    spec = spec_of(a.type)
    out = out_dir(spec)
    tab = load_table(Path(a.table) if a.table else None, spec)
    shapes = tab.meta.get("shapes") or {}
    t0 = time.time()
    tracks = load_tracks(a.set, spec=spec)
    print(f"{a.set}: {len(tracks)} tracks ({time.time() - t0:.0f} s)", flush=True)
    rows = []
    # threads: cv2 / numpy release the GIL; map keeps the track order (the same rows as one thread)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max(1, a.threads)) as ex:
        for i, rr in enumerate(ex.map(lambda tr: eval_track(tr, tab, shapes, every=a.every,
                                                             idle_every=a.idle_every), tracks)):
            rows += rr
            if i % 50 == 0:
                print(f"  {i}/{len(tracks)} rows {len(rows)} ({time.time() - t0:.0f} s)", flush=True)
    summ = summarize(rows)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"eval_{a.set}.json").write_text(json.dumps({"set": a.set, "rows": len(rows), "every": a.every,
                                                        "idle_every": a.idle_every, "summary": summ}, indent=1),
                                            "utf-8")
    with open(out / f"rows_{a.set}.pkl", "wb") as fh:
        pickle.dump(rows, fh, protocol=4)
    for fam, d in summ.items():
        for kk in ("k0", "k12"):
            x = d.get(kk) or {}
            print(f"{fam:9s} {kk:3s} main {x.get('main')} ratio_area {x.get('ratio_area')} ratio {x.get('ratio')} "
                  f"ok {x.get('ratio_ok')} cover {x.get('cover')} miss_rows {x.get('miss_rows')}")
    print(f"done ({time.time() - t0:.0f} s)")
    return 0


def out_dir(spec=None) -> Path:
    """The type's output folder: C:/ssbot/data/m2_forum_are/<short> (the Choristor's is OUT)."""
    return ARE / (spec or CHORISTOR).short.lower()


def spec_of(name: str | None):
    """The EnemySpec by short name / module / type key (None: the Choristor)."""
    if not name:
        return CHORISTOR
    from ssbot.combat.are_types import module_of
    return module_of(name).SPEC


def attach_hazards(c: dict, tracks: list[dict], spec, f1: int | None = None) -> dict:
    """Adds the real colliders of the hazards each enemy of the fight owns to its track's cols, named
    "HZ:<hazard>" (a circle collider: the AABB's inscribed circle). A hazard collider is an AABB of width and height
    box_w (+-0.03) dealing damage on an entity of another type (the pooled "damager" objects); its episodes (runs of
    frames, gaps <= 2) go to the owner whose trigger before the episode puts it there: row - a whole number of
    spacings from the trigger x (residual <= 0.8 u, abs(m) <= m_max), circle - within 1.5 u of x + s du; both within
    1.5 u of y + dv and 4 s; with a spawn-rule timing (HazardSpec.on0) the trigger whose timing fits best (within
    on_tol frames: a bomb still lit from an earlier cast or another Clapper's is not this cast's), else the latest.
    Records tr["hz_eps"] (per episode: hazard, trigger, ring, centre, frames) and returns the attribution counts."""
    stats: dict = {hz.name: {"episodes": 0, "attributed": 0} for hz in spec.hazards}
    if not tracks or not spec.hazards:
        return stats
    if f1 is None:
        f1 = facing_of_flip(tracks, spec.face_names or ("Slash Hit", "Whip Hit 2"))
    trig = []                                          # (hz name, t, x, y, s, track index)
    for n, tr in enumerate(tracks):
        tr.setdefault("hz_eps", [])
        insts, _ = segment(tr, spec, f1)
        for r in insts:
            for name, (t, x, y, s) in r["inst"].trig.items():
                trig.append((name, t, x, y, s, n))
    trig.sort(key=lambda q: q[1])
    types = list(c["types"])
    own = types.index(spec.type_key) if spec.type_key in types else -1
    box = c["c_box"]
    w = box[:, 2] - box[:, 0]
    h = box[:, 3] - box[:, 1]
    ei = c["c_ei"]
    T = c["T"]
    pos = {n: {int(fi): j for j, fi in enumerate(tr["fi"])} for n, tr in enumerate(tracks)}
    for hz in spec.hazards:
        sel = np.nonzero((np.abs(w - hz.box_w) < 0.03) & (np.abs(h - hz.box_w) < 0.03) & (c["c_dealt"] > 0)
                         & (c["e_tk"][ei] != own))[0]
        if not len(sel):
            continue
        fis = c["e_fi"][ei[sel]]
        iids = c["e_iid"][ei[sel]]
        cand = [q for q in trig if q[0] == hz.name]
        for iid in np.unique(iids):
            rows = sel[iids == iid]
            rows = rows[np.argsort(c["e_fi"][ei[rows]], kind="stable")]
            ff = c["e_fi"][ei[rows]]
            cuts = np.nonzero(np.diff(ff) > 2)[0] + 1
            for part in np.split(np.arange(len(rows)), cuts):
                rr = rows[part]
                fr = ff[part]
                stats[hz.name]["episodes"] += 1
                cx = float(np.median(0.5 * (box[rr, 0] + box[rr, 2])))
                cy = float(np.median(0.5 * (box[rr, 1] + box[rr, 3])))
                te = float(T[fr[0]])
                best = None
                for name, t, x, y, s, n in cand:
                    if t > te + 1e-6 or te - t > 4.0 or abs(cy - (y + hz.dv)) > 1.5:
                        continue
                    if hz.shape == "row":
                        m = int(round((cx - x) / hz.spacing))
                        if abs(m) > hz.m_max or abs(cx - x - hz.spacing * m) > 0.8:
                            continue
                        ring = abs(m)
                    else:
                        if abs(cx - (x + s * hz.du)) > 1.5:
                            continue
                        ring = 0
                    if hz.on0 is None:
                        best = (0.0, t, x, y, s, n, ring)        # the latest trigger wins (cand is sorted by t)
                        continue
                    res = abs((te - t) / FT - (hz.on0 + hz.on_step * ring))
                    if res <= hz.on_tol and (best is None or res < best[0]):
                        best = (res, t, x, y, s, n, ring)       # the trigger that fits the spawn rule's timing
                if best is None:
                    continue
                _, t, x, y, s, n, ring = best
                tr = tracks[n]
                js = []
                for r_, f_ in zip(rr, fr):
                    j = pos[n].get(int(f_))
                    if j is not None:
                        tr["cols"][j].append((f"HZ:{hz.name}", box[r_].astype(np.float64)))
                        js.append(j)
                tr["hz_eps"].append({"hz": hz.name, "t": t, "x": x, "y": y, "s": s, "ring": ring, "cx": cx, "cy": cy,
                                     "t_on": te, "t_off": float(T[fr[-1]]), "n": len(fr), "frames": js})
                stats[hz.name]["attributed"] += 1
    return stats


def person_caches(sessions=PERSON, root: Path | None = None) -> list[Path]:
    """The per-attempt Forum caches of the person's sessions (decoded once into PERSON_CACHE; every type reads
    them; f_raw = the raw frame of each game frame: the video's labels)."""
    from ssbot.knowledge.forum_cache import extract_states, save_cache
    root = root or PERSON_CACHE
    root.mkdir(parents=True, exist_ok=True)
    out = []
    for sess in sessions:
        done = root / f"{sess}.done"
        if done.exists():
            out += [root / x for x in json.loads(done.read_text("utf-8"))]
            continue
        from ssbot.tools.forum_human_score import load_segment, segments
        d = HUMAN / sess
        names = []
        if (d / "state.raw.zst").exists():
            for seg in segments(f"{d}:win", None):
                _, states = load_segment(seg)
                fmap = {int(s["f"]): int(s.get("_f_raw", s["f"])) for s in states}
                c = extract_states(states, {"id": f"{sess}/a{seg['attempt']}"})
                c["f_raw"] = np.array([fmap.get(int(x), int(x)) for x in c["f"]], np.int64)
                p = root / f"{sess}_a{seg['attempt']}.npz"
                save_cache(c, p)
                names.append(p.name)
        done.write_text(json.dumps(names), "utf-8")
        out += [root / x for x in names]
    return out


def fit_hazards(tracks: list[dict], spec, f1: int) -> tuple[dict, dict]:
    """The hazards' measured parameters from the dev tracks' attributed episodes (attach_hazards): per ring the
    window [first, last] frame it hurt after its trigger (the union over R0 dev), the centre offsets (median), the x
    intervals where a row hazard ever stood (gaps > 1.5 u split them), and each trigger family's trigger bins after
    its antic start (the pre-trigger prediction)."""
    params, rep = {}, {}
    for hz in spec.hazards:
        eps = [e for tr in tracks for e in tr.get("hz_eps", ()) if e["hz"] == hz.name]
        if not eps:
            continue
        nring = (hz.m_max + 1) if hz.shape == "row" else 1
        on = [[] for _ in range(nring)]
        off = [[] for _ in range(nring)]
        dur = []
        for e in eps:
            on[e["ring"]].append((e["t_on"] - e["t"]) / FT)
            off[e["ring"]].append((e["t_off"] - e["t"]) / FT)
            dur.append(e["n"])
        win = [[int(math.floor(min(a) + 1e-6)), int(math.ceil(max(b) - 1e-6))] if a else None
               for a, b in zip(on, off)]
        P: dict = {"win": win, "dv": float(np.median([e["cy"] - e["y"] for e in eps]))}
        R: dict = {"episodes": len(eps), "lit_frames": _q(dur, (5, 50, 95, 100)),
                   "rings": [{"ring": i, "n": len(on[i]), "on": _q(on[i], (0, 50, 100)),
                              "off": _q(off[i], (0, 50, 100))}
                             for i in range(nring) if on[i]]}
        if hz.shape == "row":
            res = [e["cx"] - e["x"] - hz.spacing * round((e["cx"] - e["x"]) / hz.spacing) for e in eps]
            P["dx"] = float(np.median(res))
            R["dx"] = _q(res, (0, 50, 100))
            xs = np.sort([e["cx"] for e in eps])
            cuts = np.nonzero(np.diff(xs) > 1.5)[0] + 1
            P["x_ok"] = [[float(p[0]), float(p[-1])] for p in np.split(xs, cuts)]
        else:
            du = [(e["cx"] - e["x"]) * e["s"] for e in eps]
            P["du"] = float(np.median(du))
            R["du"] = _q(du, (0, 50, 100))
        R["dv"] = _q([e["cy"] - e["y"] for e in eps], (0, 50, 100))
        trig: dict = defaultdict(list)
        for tr in tracks:
            insts, _ = segment(tr, spec, f1)
            for r in insts:
                tt = r["inst"].trig.get(hz.name)
                if tt is not None:
                    trig[r["inst"].fam].append(bin_of(tt[0] - r["inst"].t0))
        P["trig"] = {fam: [int(min(v)), int(max(v))] for fam, v in trig.items()}
        R["trig"] = {fam: _q(v, (0, 50, 100)) for fam, v in trig.items()}
        params[hz.name] = P
        rep[hz.name] = R
    return params, rep


def _active_view(inst, t: float):
    """The instance as the tracker saw it at game time t (its decision and hazard triggers up to t)."""
    if inst is None:
        return None
    dec = inst.dec if inst.dec is not None and inst.dec["t"] <= t + 1e-9 else None
    return dataclasses.replace(inst, dec=dec, trig={k: v for k, v in inst.trig.items() if v[0] <= t + 1e-9})


def _module(spec):
    from ssbot.combat.are_types import module_of
    return module_of(spec.type_key)


def _hero_gap(cx: float, cy: float, r: float, hx: float, hy: float) -> float:
    """Distance from the hero hurtbox (HeroBox at the transform) to a circle collider: < 0 = they overlap (by how
    much, along the nearest axis when the centre is outside the box)."""
    from ssbot.combat.attack_range import HERO_DY, HERO_HALF
    dx = abs(cx - hx) - HERO_HALF[0]
    dy = abs(cy - (hy + HERO_DY)) - HERO_HALF[1]
    if dx <= 0 and dy <= 0:
        return -r + max(dx, dy)
    return math.hypot(max(dx, 0.0), max(dy, 0.0)) - r


def cmd_hazcheck(a) -> int:
    """The hazards' real colliders checked against the damage they did (as the spear explosion was): per lit window
    (the exported collider dealing damage) the hero hurtbox's distance to the circle each frame, and the damage /
    damage_blocked events whose source names the hazard: do hits happen only while it is lit and only when the
    hurtbox overlaps, and what happened in the windows where it overlapped without a hit."""
    from ssbot.knowledge.forum_cache import load_cache
    _idle_priority()
    spec = spec_of(a.type)
    res: dict = {}
    for set_name in a.sets.split(","):
        files = person_caches() if set_name == "person" else _cache_files(set_name)
        for f in files:
            c = load_cache(f)
            trs = tracks_from_cache(c, spec.type_key, set_name)
            if not trs:
                continue
            attach_hazards(c, trs, spec)
            fnum = c["f"]
            evs = [(int(ev[0]), ev[1], ev[2]) for ev in c["events"] if ev[1] in ("damage", "damage_blocked")]
            for hz in spec.hazards:
                R = res.setdefault(hz.name, {"windows": 0, "frames": 0, "hits": [], "blocked": defaultdict(int),
                                             "outcome": defaultdict(int), "hit_gap": [], "hit_off": [],
                                             "events": 0, "events_matched": 0, "gap_min": [], "none_cases": []})
                hev = [e for e in evs if hz.name in str(e[2].get("source", ""))]
                R["events"] += len(hev)
                wins = []                   # (track, episode, {cache frame: hurtbox gap}, first / last cache frame)
                for tr in trs:
                    for ep in tr.get("hz_eps", ()):
                        if ep["hz"] != hz.name or not ep["frames"]:
                            continue
                        js = ep["frames"]
                        gaps = {int(fnum[tr["fi"][j]]): _hero_gap(ep["cx"], ep["cy"], hz.radius, float(tr["hx"][j]),
                                                                  float(tr["hy"][j])) for j in js}
                        wins.append((tr, ep, gaps, int(fnum[tr["fi"][js[0]]]), int(fnum[tr["fi"][js[-1]]])))
                got: dict = defaultdict(list)
                for ef0, kind, d in hev:
                    # a blocked contact is logged when it ends: its first frame is when it touched
                    ef = int(d.get("first_f") or ef0) if kind == "damage_blocked" else ef0
                    best = None
                    for n, (tr, ep, gaps, f_on, f_off) in enumerate(wins):
                        if not (f_on - 1 <= ef <= f_off + 2):
                            continue
                        g = min(gaps.get(x, 99.0) for x in (ef, ef - 1, ef - 2))
                        g = g if g < 99.0 else min(gaps.values())
                        if best is None or g < best[0]:
                            best = (g, n)   # simultaneous windows (a row of bombs): the one nearest the hero
                    if best is None:
                        R["unmatched_events"] = R.get("unmatched_events", 0) + 1
                        if len(R.setdefault("unmatched", [])) < 12:
                            R["unmatched"].append({"fight": c["meta"].get("id"), "f": ef, "kind": kind,
                                                   "why": d.get("why")})
                        continue
                    R["events_matched"] += 1
                    got[best[1]].append((kind, d, ef, best[0]))
                for n, (tr, ep, gaps, f_on, f_off) in enumerate(wins):
                    R["windows"] += 1
                    R["frames"] += len(gaps)
                    gmin = min(gaps.values())
                    R["gap_min"].append(gmin)
                    out_ = None
                    for kind, d, ef, g in got.get(n, ()):
                        if kind == "damage":
                            out_ = "damage"
                            R["hit_gap"].append(g)
                            R["hit_off"].append(ef - f_on)
                        else:
                            out_ = out_ or f"blocked {d.get('why')}"
                            R["blocked"][str(d.get("why"))] += 1
                    band = "overlap>0.3" if gmin < -0.3 else ("overlap" if gmin < 0 else "clear")
                    R["outcome"][f"{band}: {out_ or 'none'}"] += 1
                    if band == "overlap>0.3" and out_ is None and len(R["none_cases"]) < 12:
                        R["none_cases"].append({"fight": tr["fight"], "f_on": int(tr["f"][ep["frames"][0]]),
                                                "f_off": int(tr["f"][ep["frames"][-1]]), "gap": round(gmin, 3)})
        print(f"{set_name} done", flush=True)
    out = {}
    for name, R in res.items():
        out[name] = {"windows": R["windows"], "lit_frames": R["frames"], "events": R["events"],
                     "events_in_windows": R["events_matched"], "events_outside": R.get("unmatched_events", 0),
                     "outcome": dict(R["outcome"]), "blocked": dict(R["blocked"]),
                     "hit_gap": _q(R["hit_gap"], (0, 50, 95, 100)), "hit_off": _q(R["hit_off"], (0, 50, 95, 100)),
                     "window_gap_min": _q(R["gap_min"], (0, 5, 50)), "none_cases": R["none_cases"],
                     "unmatched": R.get("unmatched", [])}
    p = out_dir(spec) / "hazcheck.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=1), "utf-8")
    print(json.dumps(out, indent=1)[:6000])
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--type", default=None, help="the enemy type (are_types module / short name / type key; "
                                                 "default the Choristor)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("shapes")
    b = sub.add_parser("build")
    b.add_argument("--out", default=None)
    e = sub.add_parser("eval")
    e.add_argument("--set", required=True, choices=("dev", "fresh", "r2", "person"))
    e.add_argument("--every", type=int, default=2)
    e.add_argument("--idle-every", type=int, default=6)
    e.add_argument("--threads", type=int, default=1)
    e.add_argument("--table", default=None)
    pg = sub.add_parser("png")
    pg.add_argument("--out", default=None)
    pg.add_argument("--worst", type=int, default=8, help="also the worst frames of the person / fresh rows")
    hc = sub.add_parser("hazcheck")
    hc.add_argument("--sets", default="dev,fresh,r2")
    tk = sub.add_parser("tracks", help="decode the person's sessions into the shared per-attempt caches")
    tk.add_argument("--sessions", default=",".join(PERSON))
    a = ap.parse_args(argv)
    if a.cmd == "tracks":
        _idle_priority()
        fs = person_caches([x for x in a.sessions.split(",") if x])
        print(f"{len(fs)} attempt caches")
        return 0
    if a.cmd == "shapes":
        return cmd_shapes(a)
    if a.cmd == "build":
        return cmd_build(a)
    if a.cmd == "eval":
        return cmd_eval(a)
    if a.cmd == "hazcheck":
        return cmd_hazcheck(a)
    if a.cmd == "png":
        from ssbot.tools.attack_range_png import cmd_png
        return cmd_png(a)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
