"""Idle velocity compensation of the attack-range estimate (the person 2026-10-10, forum.md §38): an idle / moving
non-attack body (walks, flights, chases between attacks) at look-ahead k is the body now carried by its velocity now x
k / 60 s, kept inside the arena (ssbot.combat.attack_range.carry_body), then a small FIXED margin m is a decision-time
choice. This measures, on data not used to build (R0 fresh, R2, the person's sessions; each set apart), per type x k
in KS, the body-only error of four variants:
  now   the body now (the approved rule before this task; the reference)
  vel   the body carried by the exported velocity of the frame (the default, IDLE_CARRY)
  fd    ... by the position difference over the last FD_N frames (a smoothed velocity)
  acc   ... by the velocity and its acceleration over the last FD_N frames (constant acceleration, |a| <= ACC_MAX)
Rows: every `every`-th frame of an enemy in play outside every family (the eval's idle rows) and, for the types in
CARRIED, the frames of those non-attack families (the Clawmaiden's Fly); a row at k counts when no family started
(idle) / the family did not change (carried) by the real frame compared and the enemy was not hit from 0.3 s before
to that frame. The truth is the enemy's own colliders at the first frame reaching t + k / 60 (no hazards /
projectiles: those keep their own rows in attack_range_build), the estimate is carried to that frame's game time;
both in hero-centre space (the hurtbox dilation). Per row and margin m in MS (the estimate dilated by a disc of m):
the real cells covered, the estimate's area; the miss distance per side (front / back / up / down / inner of the
estimate's box in the facing frame) and the row's largest miss (= the margin that covers the row entirely).

    cd brain       (2026-10-10: person every 6, fresh every 24, r2 every 12 as --part 0/2 and 1/2; ~25 min each)
    ../scripts/uv.cmd run python -m ssbot.tools.are_idlevel run --sets person --threads 4
    ../scripts/uv.cmd run python -m ssbot.tools.are_idlevel run --sets fresh --every 24 --threads 4
    ../scripts/uv.cmd run python -m ssbot.tools.are_idlevel run --sets r2 --every 12 --threads 4 --part 0/2   (1/2)
    ../scripts/uv.cmd run python -m ssbot.tools.are_idlevel summary         # -> OUT/summary.md / .json
    ../scripts/uv.cmd run python -m ssbot.tools.are_idlevel png             # -> OUT/png (before / after)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from ssbot.combat.attack_range import (CELL, SPECS, carry_shift, contours, hero_space, load_table, on_canvas,
                                       poly_mask, table_path, union)
from ssbot.tools.attack_range_build import (PERSON, _attach, _cache_files, _idle_priority, _module, _target,
                                            frame_polys, person_caches, segment, tracks_from_cache)

OUT = Path(r"C:\ssbot\data\m2_forum_are\idlevel")
KS = (1, 6, 12, 18, 30, 36)
MS = (0.0, 0.25, 0.5, 0.75, 1.0, 1.5)       # 1.5 u: half a nail length (the uniform dilation reference)
VARIANTS = ("now", "vel", "fd", "acc")
SIDES = ("front", "back", "up", "down", "inner")
FD_N = 3                                    # frames: the position difference / acceleration window
ACC_MAX = 150.0                             # u/s^2: larger is a collision (a wall, the floor), not steering
CARRIED = {"Song Handmaiden": frozenset({"CM_FLY"})}
PNG_K = 30
PAD = int(math.ceil(max(MS) / CELL)) + 2


# ------------------------------------------------------------------------------------------------ one row

def measure(E, R, s: int) -> tuple:
    """(aR cells, covered cells per m, estimate cells per m, miss per side (u, 0: none), the row's largest miss) of the
    raw estimate E against the raw truth R, in hero-centre space."""
    import cv2
    HE, HR = hero_space(E), hero_space(R)
    U = union([HE, HR])
    ny, nx = U.m.shape
    ix0, iy0 = U.ix0 - PAD, U.iy0 - PAD
    shape = (ny + 2 * PAD, nx + 2 * PAD)
    e = on_canvas(HE, ix0, iy0, shape)
    r = on_canvas(HR, ix0, iy0, shape)
    dist = cv2.distanceTransform((~e).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE) * CELL
    cov = np.array([int((r & (dist <= m + 1e-6)).sum()) for m in MS], np.int32)
    area = np.array([int((dist <= m + 1e-6).sum()) for m in MS], np.int32)
    side = np.zeros(len(SIDES), np.float32)
    miss = r & ~e
    big = 0.0
    if miss.any():
        rr, cc = np.nonzero(e)
        r0, r1, c0, c1 = rr.min(), rr.max(), cc.min(), cc.max()
        yy, xx = np.nonzero(miss)
        dxp, dxn = xx - c1, c0 - xx
        fr, bk = (dxp, dxn) if s >= 0 else (dxn, dxp)
        st = np.stack([fr, bk, yy - r1, r0 - yy], 0)
        sd = np.where(st.max(0) > 0, np.argmax(st, 0), 4)
        d = dist[yy, xx]
        for i in range(len(SIDES)):
            q = sd == i
            if q.any():
                side[i] = float(d[q].max())
        big = float(d.max())
    return int(r.sum()), cov, area, side, big


def velocities(tr: dict, j: int) -> dict:
    """The (vx, vy) of each carried variant at frame j (acc: the mean velocity over the look-ahead is v + a tau / 2,
    returned as (vx, vy, ax, ay))."""
    vx, vy = float(tr["vx"][j]), float(tr["vy"][j]) if tr.get("vy") is not None else 0.0
    out = {"vel": (vx, vy), "fd": (vx, vy), "acc": (vx, vy, 0.0, 0.0)}
    j0 = j - FD_N
    if j0 >= 0 and not tr["hidden"][j0]:
        dt = float(tr["T"][j] - tr["T"][j0])
        if 0.0 < dt < 0.2:
            out["fd"] = ((float(tr["x"][j]) - float(tr["x"][j0])) / dt, (float(tr["y"][j]) - float(tr["y"][j0])) / dt)
            if tr.get("vy") is not None:
                ax = (vx - float(tr["vx"][j0])) / dt
                ay = (vy - float(tr["vy"][j0])) / dt
                out["acc"] = (vx, vy, ax if abs(ax) <= ACC_MAX else 0.0, ay if abs(ay) <= ACC_MAX else 0.0)
    return out


def shifted(body, var: str, vs: dict, tau: float) -> tuple:
    if var == "now":
        return 0.0, 0.0
    v = vs[var]
    if var == "acc":
        v = (v[0] + 0.5 * v[2] * tau, v[1] + 0.5 * v[3] * tau)
    return carry_shift(body, v, tau)


def eval_track(tr: dict, tab, shapes: dict, every: int, png: list) -> list:
    spec = tab.spec
    f1 = int(tab.meta.get("face_flip1", 1))
    insts, idx = segment(tr, spec, f1)
    T = tr["T"]
    carried = CARRIED.get(spec.type_key, frozenset())
    hits = np.asarray(tr["hits"], np.float64)
    rows = []
    for j in range(0, len(T), every):
        if tr["hidden"][j] or tr["st"][j] is None:
            continue
        n = int(idx[j])
        if n >= 0 and insts[n]["inst"].fam not in carried:
            continue
        st = str(tr["st"][j])
        if n < 0 and any(w in st for w in spec.parked):
            continue
        body = frame_polys(tr, j, shapes, spec.body_names)
        if not body:
            continue
        s = f1 if tr["flip"][j] else -f1
        vs = velocities(tr, j)
        sp = math.hypot(*vs["vel"])
        for k in KS:
            jt = _target(T, j, k)
            if jt is None:
                continue
            nxt = bool((idx[j:jt + 1] != n).any())
            hit = bool(len(hits) and ((hits >= T[j] - 0.3) & (hits <= T[jt] + 0.05)).any())
            if nxt or hit:
                continue
            tau = float(T[jt] - T[j])
            R = poly_mask(frame_polys(tr, jt, shapes, hz=False))
            rec = {"k": k, "g": 0 if n < 0 else 1, "st": st, "sp": sp, "tau": tau}
            for var in VARIANTS:
                dx, dy = shifted(body, var, vs, tau)
                E = poly_mask([p + (dx, dy) for p in body])
                aR, cov, area, side, big = measure(E, R, s)
                rec[var] = (cov, area, side, big)
                rec["aR"] = aR
                if var == "vel":
                    rec["shift"] = (dx, dy)
            rows.append(rec)
            if k == PNG_K and sp >= 2.0 and rec["now"][3] > 0.3:
                png.append({"sp": sp, "big_now": rec["now"][3], "big_vel": rec["vel"][3], "st": st, "k": k,
                            "body": [p.copy() for p in body], "real": frame_polys(tr, jt, shapes, hz=False),
                            "shift": rec["shift"], "v": vs["vel"], "fight": tr.get("fight"), "f": int(tr["f"][j]),
                            "iid": int(tr["iid"]), "hero": (float(tr["hx"][j]), float(tr["hy"][j]))})
    return rows


# ------------------------------------------------------------------------------------------------ run

def _tables() -> dict:
    out = {}
    for tk, sp in SPECS.items():
        p = table_path(sp)
        if p.exists():
            out[tk] = load_table(p, sp)
    return out


def _files(name: str) -> list[Path]:
    return person_caches(PERSON) if name == "person" else _cache_files(name)


def run_set(name: str, tabs: dict, every: int, threads: int, part: tuple = (0, 1)) -> dict:
    """Rows per type of one set, streaming its caches (each loaded once for every type); part (i, n): only the files
    i, i + n, i + 2n, ... (n processes side by side)."""
    from ssbot.knowledge.forum_cache import load_cache
    rows: dict = defaultdict(list)
    png: dict = defaultdict(list)
    files = _files(name)[part[0]::part[1]]
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max(1, threads)) as ex:
        for i, f in enumerate(files):
            c = load_cache(f)
            jobs = []
            for tk, tab in tabs.items():
                trs = tracks_from_cache(c, tk, name)
                if not trs:
                    continue
                if name == "person" and "f_raw" in c:
                    for t in trs:
                        t["f"] = np.asarray(c["f_raw"][t["fi"]], np.int64)
                att = getattr(tab.spec, "attach", None) or getattr(_module(tab.spec), "attach", None)
                if att is not None:
                    _attach(att, c, trs, tab.spec)
                for tr in trs:
                    jobs.append((tk, tr))

            def one(job):
                tk, tr = job
                pl: list = []
                tab = tabs[tk]
                return tk, eval_track(tr, tab, tab.meta.get("shapes") or {}, every, pl), pl
            for tk, rr, pl in ex.map(one, jobs):
                rows[tk] += rr
                if pl:
                    for q in pl:
                        q["set"] = name
                    png[tk] += pl
                    png[tk] = sorted(png[tk], key=lambda q: -q["sp"])[:60]
            if i % 10 == 0:
                print(f"{name} {i + 1}/{len(files)} rows {sum(len(v) for v in rows.values())} "
                      f"({time.time() - t0:.0f} s)", flush=True)
    return {"rows": dict(rows), "png": dict(png)}


def pack(rows: list) -> dict:
    """Rows as arrays: k, g, sp, tau, aR, st (names), and per variant cov / area [n, len(MS)], side [n, 5], big [n]."""
    out = {"k": np.array([r["k"] for r in rows], np.int16), "g": np.array([r["g"] for r in rows], np.int8),
           "sp": np.array([r["sp"] for r in rows], np.float32), "tau": np.array([r["tau"] for r in rows], np.float32),
           "aR": np.array([r["aR"] for r in rows], np.int32), "st": [r["st"] for r in rows]}
    for v in VARIANTS:
        out[f"{v}_cov"] = np.array([r[v][0] for r in rows], np.int32).reshape(-1, len(MS))
        out[f"{v}_area"] = np.array([r[v][1] for r in rows], np.int32).reshape(-1, len(MS))
        out[f"{v}_side"] = np.array([r[v][2] for r in rows], np.float32).reshape(-1, len(SIDES))
        out[f"{v}_big"] = np.array([r[v][3] for r in rows], np.float32)
    return out


def cmd_run(a) -> int:
    _idle_priority()
    try:
        import cv2
        cv2.setNumThreads(1)
    except Exception:
        pass
    tabs = _tables()
    if a.types:
        want = {x.strip().lower() for x in a.types.split(",")}
        tabs = {tk: t for tk, t in tabs.items() if t.spec.short.lower() in want or tk.lower() in want}
    OUT.mkdir(parents=True, exist_ok=True)
    i, n = (int(x) for x in a.part.split("/"))
    for name in a.sets.split(","):
        t0 = time.time()
        res = run_set(name, tabs, a.every, a.threads, (i, n))
        packed = {tk: pack(rr) for tk, rr in res["rows"].items() if rr}
        with open(OUT / (f"rows_{name}.pkl" if n == 1 else f"rows_{name}.part{i}of{n}.pkl"), "wb") as fh:
            pickle.dump({"rows": packed, "png": res["png"], "every": a.every, "ks": KS, "ms": MS}, fh, protocol=4)
        print(f"{name}: done ({time.time() - t0:.0f} s): "
              + ", ".join(f"{tabs[tk].spec.short} {len(p['k'])}" for tk, p in packed.items()), flush=True)
    return 0


# ------------------------------------------------------------------------------------------------ summary

def _q(v, ps=(50, 95, 99, 100)) -> dict | None:
    v = np.asarray(v, np.float64)
    if not len(v):
        return None
    return {("max" if p == 100 else f"p{p}"): round(float(np.percentile(v, p)), 2) for p in ps}


def stats(P: dict, sel: np.ndarray) -> dict:
    """Per variant over the selected rows: pooled coverage and area ratio per m, the miss per side (rows missing there:
    share, p50 / p95 / p99 / max) and the row's largest miss over all rows (p50 / p95 / p99 / max)."""
    aR = float(P["aR"][sel].sum())
    d = {"n": int(sel.sum()), "sp": _q(P["sp"][sel], (50, 95))}
    for v in VARIANTS:
        cov = P[f"{v}_cov"][sel].sum(0).astype(np.float64)
        area = P[f"{v}_area"][sel].sum(0).astype(np.float64)
        side = P[f"{v}_side"][sel]
        big = P[f"{v}_big"][sel]
        d[v] = {"cover": [round(100.0 * c / aR, 2) if aR else None for c in cov],
                "ratio": [round(x / aR, 2) if aR else None for x in area],
                "rows_full": [round(100.0 * float((big <= m + 1e-6).mean()), 2) for m in MS],
                "big": _q(big),
                "side": {nm: {"rows": round(100.0 * float((side[:, i] > 0).mean()), 2),
                              **(_q(side[side[:, i] > 0, i]) or {})} for i, nm in enumerate(SIDES)
                         if (side[:, i] > 0).any()}}
    return d


def load_rows(sets=("fresh", "r2", "person")) -> dict:
    """{set: {"rows": {type key: packed rows}, "png": ...}}: rows_<set>.pkl, or its parts (run --part i/n) merged."""
    out = {}
    for name in sets:
        ps = [OUT / f"rows_{name}.pkl"]
        if not ps[0].exists():
            ps = sorted(OUT.glob(f"rows_{name}.part*.pkl"))
        for p in ps:
            if not p.exists():
                continue
            with open(p, "rb") as fh:
                D = pickle.load(fh)
            if name not in out:
                out[name] = D
                continue
            for tk, P in D["rows"].items():
                Q = out[name]["rows"].get(tk)
                out[name]["rows"][tk] = P if Q is None else {
                    key: (Q[key] + P[key] if isinstance(P[key], list) else np.concatenate([Q[key], P[key]]))
                    for key in P}
            for tk, pl in D["png"].items():
                out[name]["png"][tk] = out[name]["png"].get(tk, []) + pl
    return out


def _m_need(d: dict, v: str, target: float = 99.5) -> str:
    """The smallest m in MS whose pooled coverage reaches target (%), or '>1.5'."""
    for m, c in zip(MS, d[v]["cover"]):
        if c is not None and c >= target:
            return f"{m:g}"
    return ">1.5"


def cmd_summary(a) -> int:
    data = load_rows()
    shorts = {tk: sp.short for tk, sp in SPECS.items()}
    js: dict = {}
    lines = ["# Idle velocity compensation (forum.md §38)", "",
             "Body-only rows (no hazards / projectiles), hero-centre space; cover = pooled share of the real body "
             "cells inside the estimate dilated by m (u); ratio = estimate area / real area at that m; big = the "
             "row's largest miss (u) = the margin that covers the row entirely; m99.5 = the smallest m of "
             f"{', '.join(f'{m:g}' for m in MS)} with cover >= 99.5 %. now = the body now, vel = carried by the "
             "velocity now (the default), fd = by the position difference over 3 frames, acc = constant "
             "acceleration. now + 1.5 = the uniform dilation by half a nail length.", ""]
    hdr = ("| type | grp | set | k | n | speed p50/p95 | now m0 | vel m0 | vel +0.25 | vel +0.5 | vel +0.75 | "
           "vel +1.0 | ratio vel +0.5 | now +1.5 cover / ratio | vel big p50/p95/p99/max | m99.5 vel | m99.5 now |")
    lines += ["## Per type x set x k (vel = the default)", "", hdr, "|" + "---|" * 17]
    var_lines = ["## Variants (cover at m 0 / row's largest miss p95, u)", "",
                 "| type | grp | set | k | now | vel | fd | acc |", "|---|---|---|---|---|---|---|---|"]
    side_lines = ["## Residual miss per side after compensation (vel, m 0): rows missing there % / p50 / p95 / p99 / "
                  "max", "", "| type | grp | set | k | front | back | up | down | inner |",
                  "|---|---|---|---|---|---|---|---|---|"]
    for tk in SPECS:
        for g, gname in ((0, "idle"), (1, "fly")):
            for name, D in data.items():
                P = D["rows"].get(tk)
                if P is None:
                    continue
                for k in KS:
                    sel = (P["k"] == k) & (P["g"] == g)
                    if sel.sum() < 20:
                        continue
                    d = stats(P, sel)
                    js.setdefault(shorts[tk], {}).setdefault(gname, {}).setdefault(name, {})[f"k{k}"] = d
                    vc, nc = d["vel"]["cover"], d["now"]["cover"]
                    b = d["vel"]["big"]
                    lines.append(f"| {shorts[tk]} | {gname} | {name} | {k} | {d['n']} | "
                                 f"{d['sp']['p50']}/{d['sp']['p95']} | {nc[0]} | {vc[0]} | {vc[1]} | {vc[2]} | "
                                 f"{vc[3]} | {vc[4]} | {d['vel']['ratio'][2]} | {nc[5]} / {d['now']['ratio'][5]} | "
                                 f"{b['p50']}/{b['p95']}/{b['p99']}/{b['max']} | {_m_need(d, 'vel')} | "
                                 f"{_m_need(d, 'now')} |")
                    var_lines.append(f"| {shorts[tk]} | {gname} | {name} | {k} | " + " | ".join(
                        f"{d[v]['cover'][0]} / {d[v]['big']['p95']}" for v in VARIANTS) + " |")
                    sd = d["vel"]["side"]
                    side_lines.append(f"| {shorts[tk]} | {gname} | {name} | {k} | " + " | ".join(
                        (f"{sd[s]['rows']} / {sd[s]['p50']} / {sd[s]['p95']} / {sd[s]['p99']} / {sd[s]['max']}"
                         if s in sd else "-") for s in SIDES) + " |")
    ans = ["## The question: compensation + 0.5 u per k", "",
           "Each cell: cover with vel + 0.5 u (%) / the margin that covers 99 % of the rows entirely (the row's "
           "largest miss p99, u) / the body now's cover at m 0 (%).", "",
           "| type | grp | set | " + " | ".join(f"k{k} ({k / 60:.2f} s)" for k in KS) + " |",
           "|---|---|---|" + "---|" * len(KS)]
    for sh, G in js.items():
        for gname, S in G.items():
            for name, K in S.items():
                cells = []
                for k in KS:
                    d = K.get(f"k{k}")
                    cells.append("-" if d is None else
                                 f"{d['vel']['cover'][2]} / {d['vel']['big']['p99']} / {d['now']['cover'][0]}")
                ans.append(f"| {sh} | {gname} | {name} | " + " | ".join(cells) + " |")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(js, indent=1), "utf-8")
    (OUT / "summary.md").write_text("\n".join(lines[:4] + ans + [""] + lines[4:] + [""] + var_lines + [""] + side_lines)
                                    + "\n", "utf-8")
    print(OUT / "summary.md")
    return 0


# ------------------------------------------------------------------------------------------------ PNGs

def cmd_png(a) -> int:
    """Per type a few moving idles at k = PNG_K (before / after): the real body at t + k (red), the body now (grey),
    carried by its velocity (blue) and that + 0.5 u (light blue), in world space (1 u grid)."""
    import cv2
    data = load_rows()
    shorts = {tk: sp.short for tk, sp in SPECS.items()}
    out = OUT / "png"
    out.mkdir(parents=True, exist_ok=True)
    n_out = 0
    r_px = int(round(0.5 / CELL))
    disc = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r_px + 1, 2 * r_px + 1))
    for tk in SPECS:
        cands = [q for D in data.values() for q in D["png"].get(tk, ())]
        if not cands:
            continue
        # the candidates are the fastest moving idles of each set; shown: the fastest, then by the miss left after
        # the compensation, its median, p90 and worst (the before / after of a typical and a bad case)
        cands.sort(key=lambda q: -q["sp"])
        pick = [cands[0]]
        by = sorted(cands[1:], key=lambda q: q["big_vel"])
        for f in (0.5, 0.9, 1.0)[:max(a.per_type - 1, 0)]:
            if by:
                q = by[min(int(f * (len(by) - 1) + 0.5), len(by) - 1)]
                if all(q is not x for x in pick):
                    pick.append(q)
        for i, q in enumerate(pick):
            now = poly_mask(q["body"])
            car = poly_mask([p + q["shift"] for p in q["body"]])
            img = np.zeros((car.m.shape[0] + 2 * r_px + 2, car.m.shape[1] + 2 * r_px + 2), np.uint8)
            img[r_px + 1:r_px + 1 + car.m.shape[0], r_px + 1:r_px + 1 + car.m.shape[1]] = car.m
            dil = type(car)(cv2.dilate(img, disc).astype(bool), car.ix0 - r_px - 1, car.iy0 - r_px - 1)
            pts = np.vstack(list(q["body"]) + [p + q["shift"] for p in q["body"]] + list(q["real"]))
            x0, y0 = np.floor(pts.min(0)) - 1.5
            x1, y1 = np.ceil(pts.max(0)) + 1.5
            S, top = 40.0, 70
            w, h = int((x1 - x0) * S), int((y1 - y0) * S) + top
            im = np.full((h, max(w, 560)), 255, np.uint8)
            im = cv2.cvtColor(im, cv2.COLOR_GRAY2BGR)

            def px(p):
                p = np.asarray(p, np.float64).reshape(-1, 2)
                return np.stack([(p[:, 0] - x0) * S, h - (p[:, 1] - y0) * S], 1).round().astype(np.int32)
            for gx in range(int(x0), int(x1) + 1):
                cv2.line(im, tuple(px((gx, y0))[0]), tuple(px((gx, y1))[0]), (235, 235, 235), 1)
            for gy in range(int(y0), int(y1) + 1):
                cv2.line(im, tuple(px((x0, gy))[0]), tuple(px((x1, gy))[0]), (235, 235, 235), 1)
            over = im.copy()
            for p in q["real"]:
                cv2.fillPoly(over, [px(p)], (90, 90, 230))
            im = cv2.addWeighted(over, 0.55, im, 0.45, 0)
            for m, col, th in ((dil, (235, 190, 120), 1), (now, (90, 90, 90), 2), (car, (200, 110, 20), 2)):
                for c in contours(m):
                    cv2.polylines(im, [px(c)], True, col, th, cv2.LINE_AA)
            c0 = np.vstack(q["body"]).mean(0)
            c1 = c0 + np.asarray(q["v"]) * q["k"] / 60.0
            cv2.arrowedLine(im, tuple(px(c0)[0]), tuple(px(c1)[0]), (200, 110, 20), 1, cv2.LINE_AA, tipLength=0.08)
            txt = (f"{shorts[tk]} {q['st']}  k {q['k']} ({q['k'] / 60:.2f} s)  v ({q['v'][0]:.1f}, {q['v'][1]:.1f}) "
                   f"u/s  miss {q['big_now']:.2f} -> {q['big_vel']:.2f} u",
                   f"{q['set']} {q['fight']} f {q['f']} iid {q['iid']}",
                   "red: real body at t+k  grey: body now  blue: carried by v  light blue: carried + 0.5 u")
            for n_t, t in enumerate(txt):
                cv2.putText(im, t, (6, 18 + 20 * n_t), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
            p = out / f"{shorts[tk].lower()}_{i}_{q['st'].replace(' ', '_').replace('?', '')}_k{q['k']}.png"
            cv2.imwrite(str(p), im)
            n_out += 1
    print(f"{n_out} PNGs in {out}")
    return 0


def main(argv=None) -> int:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--sets", default="fresh,r2,person")
    r.add_argument("--types", default="")
    r.add_argument("--every", type=int, default=6)
    r.add_argument("--threads", type=int, default=4)
    r.add_argument("--part", default="0/1", help="i/n: only every n-th cache file from the i-th (n processes)")
    sub.add_parser("summary")
    pg = sub.add_parser("png")
    pg.add_argument("--per-type", type=int, default=4)
    a = ap.parse_args(argv)
    return {"run": cmd_run, "summary": cmd_summary, "png": cmd_png}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
