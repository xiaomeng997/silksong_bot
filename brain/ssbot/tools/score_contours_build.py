"""Task 1v1 SG3: convert SG2's special maps into score contours (ssbot.combat.score_contours; forum.md 57).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.score_contours_build nodes [--step 0.05] [--tol 1] [--tags ,wf6,wf9,wf12]
    ../scripts/uv.cmd run python -m ssbot.tools.score_contours_build tubes --phases 0-1 [--step 0.05] [--tol 1] [--tag T]

nodes: the stored map (knowledge/.../special_map_CL_SLAM[_<tag>].npz: per phase the ground layer, the 48 apex layers
and the 18 jump-start layers) -> special_map_CL_SLAM[_<tag>]_contours.npz (layers p<p>/ground, p<p>/apex/<i>,
p<p>/jump/<h>; meta: the rows with no node (NaN) per apex layer).
tubes: SG2's full pass of one phase (every macro state; MapBuilder.build(keep_full)) -> special_map_CL_SLAM_tubes_p<p>
[_<tag>].npz: per slice s the score layer S/<s>, the strike layers SV<d+1>/<s> (a slash pressed next frame with key d
held) and the press flags P<d+1>/<s> (the strike is the node's best continuation within 0.01; binary, exact); meta: the
tube index (map_lookahead.TubeIndex). Empty layers (all infeasible) are not stored.
Every layer is checked on every lattice point against its bands (feasibility exact, inner bands within +-tol, nesting,
orientation, tree); reports go to C:/ssbot/data/m2_map/sg3/contours_<what>[_<tag>].json.
"""
from __future__ import annotations

import argparse
import json
import time
import zlib
from pathlib import Path

import numpy as np

from ssbot.combat import map_lookahead as ml
from ssbot.combat import score_contours as sc
from ssbot.combat import special_map as sm

OUT = Path(r"C:\ssbot\data\m2_map\sg3")


def check_layer(lay: sc.ContourLayer, B: np.ndarray, tol: int) -> dict:
    """Every lattice point: feasibility exact, |band - true| <= tol; rings: >= 3 points, orientation (outer CCW with
    the high side inside, holes CW), parents contain their children, ring areas positive per level sum."""
    D = lay.dense()
    diff = D.astype(np.int64) - B
    feas = bool(((D >= 0) == (B >= 0)).all())
    a = lay.areas2()
    ok_ring = all(len(r) >= 3 for r in lay.rings)
    # a ring whose parent is at the same level is a hole iff ... the sign alternates down the tree within a level
    sign_ok = True
    for i, p in enumerate(lay.parent):
        if p >= 0 and lay.level[p] == lay.level[i] and np.sign(a[p]) == np.sign(a[i]):
            sign_ok = False
        if p < 0 and a[i] < 0:
            sign_ok = False                                   # a root ring must be an outer ring
    return {"feasibility_exact": feas, "max_band_diff": int(np.abs(diff).max()) if diff.size else 0,
            "n_off": int((diff != 0).sum()), "n_up": int((diff > 0).sum()), "n_down": int((diff < 0).sum()),
            "rings_ok": ok_ring, "orientation_ok": sign_ok, "within_tol": bool(np.abs(diff).max() <= tol) if diff.size else True}


def convert(name: str, score: np.ndarray, step: float, tol: int, cs: sc.ContourSet, rep: dict, binary: bool = False,
            valid: np.ndarray | None = None):
    B = (np.where(score, 0, -1).astype(np.int16) if binary else sc.to_bands(score, step))
    if valid is not None:
        B = sc.fill_rows(B, valid)
    if B.max() < 0:
        rep["empty"] = rep.get("empty", 0) + 1
        return None
    lay = sc.ContourLayer.from_bands(B, step, simplify=True, tol=0 if binary else tol)
    chk = check_layer(lay, B, 0 if binary else tol)
    cs.add(name, lay)
    agg = rep.setdefault("agg", {"layers": 0, "rings": 0, "points_raw": 0, "points": 0, "seconds": 0.0,
                                 "orientation_flips": 0, "cells": 0, "dense_zlib": 0, "off": 0, "fail": []})
    agg["layers"] += 1
    for k in ("rings", "points_raw", "points", "orientation_flips"):
        agg[k] += lay.stats[k]
    agg["seconds"] += lay.stats["seconds"]
    agg["cells"] += B.size
    agg["dense_zlib"] += len(zlib.compress(B.astype(np.uint8).tobytes(), 6))
    agg["off"] += chk["n_off"]
    chk["tree_kept"] = lay.stats["tree_kept"]
    agg["tree_changed"] = agg.get("tree_changed", 0) + (not lay.stats["tree_kept"])
    if not (chk["feasibility_exact"] and chk["within_tol"] and chk["rings_ok"] and chk["orientation_ok"]
            and chk["tree_kept"]):
        agg["fail"].append({"layer": name, **chk})
    return lay


def nodes(a) -> dict:
    out = {}
    for tag in a.tags.split(","):
        suf = f"_{tag}" if tag else ""
        src = sm.MAP_DIR / f"special_map_CL_SLAM{suf}.npz"
        if not src.exists():
            continue
        m = sm.SpecialMap(src)
        G, A, J = m._ground, m.apex, m.jump_start
        cs = sc.ContourSet(m.K, m.NX, a.step, {"source": src.name, "x_lo": m.x_lo, "lattice_step": m.step, "fill": a.fill,
                                               "tol": a.tol, "classes": m.classes, "jump_holds": m.holds,
                                               "map_meta": m.meta})
        rep = {}
        none_rows = {}
        t0 = time.time()
        for p in range(G.shape[0]):
            convert(f"p{p}/ground", G[p], a.step, a.tol, cs, rep)
            for i in range(A.shape[1]):
                nr = np.isnan(A[p, i]).all(1)
                if nr.any():
                    none_rows[f"p{p}/apex/{i}"] = np.flatnonzero(nr).tolist()
                convert(f"p{p}/apex/{i}", A[p, i], a.step, a.tol, cs, rep, valid=~nr if a.fill else None)
            for i, h in enumerate(m.holds):
                convert(f"p{p}/jump/{h:g}", J[p, i], a.step, a.tol, cs, rep)
        cs.meta["none_rows"] = none_rows
        dst = sm.MAP_DIR / f"special_map_CL_SLAM{suf}_contours{a.suffix}.npz"
        info = cs.save(dst)
        dense_bytes = src.stat().st_size
        ag = rep["agg"]
        r = {"file": str(dst), "bytes": info["bytes"], "source_npz_bytes": dense_bytes, "layers": ag["layers"],
             "empty_layers": rep.get("empty", 0), "rings": ag["rings"], "points_raw": ag["points_raw"],
             "points": ag["points"], "cells": ag["cells"], "dense_uint8_bytes": ag["cells"],
             "dense_bands_zlib_bytes": ag["dense_zlib"], "ratio_vs_dense_uint8": round(ag["cells"] / info["bytes"], 2),
             "ratio_vs_dense_zlib": round(ag["dense_zlib"] / info["bytes"], 3),
             "simplify_keep": round(ag["points"] / max(ag["points_raw"], 1), 3), "orientation_flips": ag["orientation_flips"], "tree_changed": ag.get("tree_changed", 0),
             "lattice_points_off_by_one": ag["off"], "share_off": round(ag["off"] / ag["cells"], 4),
             "failures": ag["fail"][:20], "n_failures": len(ag["fail"]), "seconds": round(time.time() - t0, 1)}
        r["timing"] = timing(cs, [nm for nm in cs.layers if nm.startswith("p0/")])
        out[tag or "open"] = r
        print(json.dumps({k: v for k, v in r.items() if k != "failures"}, default=float))
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / f"contours_nodes_s{a.step:g}_t{a.tol}{a.suffix}.json").write_text(json.dumps(out, indent=1, default=float), "utf-8")
    return out


def timing(cs: sc.ContourSet, names: list, n: int = 3000, seed: int = 57) -> dict:
    """Single lattice queries (compiled winding + level binary search) over random (layer, k, x): p50 / p99 (us)."""
    rng = np.random.default_rng(seed)
    lays = [cs.layers[nm] for nm in names]
    for L in lays[:3]:
        L.query(0, 0)                                          # compile / warm
    ts = []
    for _ in range(n):
        L = lays[int(rng.integers(len(lays)))]
        k, x = int(rng.integers(cs.nk)), int(rng.integers(cs.nx))
        t0 = time.perf_counter()
        L.query(k, x)
        ts.append(time.perf_counter() - t0)
    t = np.array(ts) * 1e6
    return {"single_us_p50": round(float(np.median(t)), 2), "single_us_p99": round(float(np.quantile(t, 0.99)), 2),
            "n": n}


def tubes(a) -> dict:
    from ssbot.tools.special_map_build import setup
    cfg = sm.MapConfig()
    if a.wall_front is not None:
        cfg.wall_front = a.wall_front
    geo = setup(cfg)
    ti = ml.TubeIndex.from_geometry(geo)
    b = sm.MapBuilder(geo)
    lo, hi = (int(v) for v in a.phases.split("-"))
    res = {}
    for p in range(lo, hi + 1):
        t0 = time.time()
        pm = b.build(p, keep_full=True)
        tb = time.time() - t0
        S = pm.S
        SV = pm.SV
        cs = sc.ContourSet(geo.K, geo.NX, a.step, {"phase": p, "tubes": ti.to_dict(), "tol": a.tol, "fill": a.fill,
                                                    "config": geo.cfg.key(), "what": "tubes"})
        rep = {}
        t1 = time.time()
        for s in range(geo.NS):
            Ss = S[:, s, :].astype(np.float32)
            vr = ti.valid_rows(p, s) if a.fill else None
            convert(f"S/{s}", Ss, a.step, a.tol, cs, rep, valid=vr)
            for di in range(3):
                sv = SV[:, s, :, di].astype(np.float32)
                if not np.isfinite(sv).any():
                    continue
                convert(f"SV{di}/{s}", sv, a.step, a.tol, cs, rep, valid=vr)
                pf = np.isfinite(sv) & (sv >= Ss - ml.PRESS_EPS)
                convert(f"P{di}/{s}", pf, a.step, a.tol, cs, rep, binary=True, valid=vr)
        suf = f"_{a.tag}" if a.tag else ""
        dst = sm.MAP_DIR / f"special_map_CL_SLAM_tubes_p{p}{suf}{a.suffix}.npz"
        info = cs.save(dst)
        ag = rep["agg"]
        q = sm.quantize(S.astype(np.float32))
        dense_z = len(zlib.compress(q.tobytes(), 6)) + len(zlib.compress(sm.quantize(SV.astype(np.float32)).tobytes(), 6))
        r = {"phase": p, "file": str(dst), "bytes": info["bytes"], "build_pass_s": round(tb, 1),
             "contour_s": round(time.time() - t1, 1), "layers": ag["layers"], "empty_layers": rep.get("empty", 0),
             "rings": ag["rings"], "points_raw": ag["points_raw"], "points": ag["points"], "cells": ag["cells"],
             "dense_float16_bytes": S.nbytes + SV.nbytes, "dense_levels_zlib_bytes": dense_z,
             "ratio_vs_float16": round((S.nbytes + SV.nbytes) / info["bytes"], 2),
             "ratio_vs_levels_zlib": round(dense_z / info["bytes"], 3), "orientation_flips": ag["orientation_flips"], "tree_changed": ag.get("tree_changed", 0),
             "lattice_points_off_by_one": ag["off"], "share_off": round(ag["off"] / ag["cells"], 4),
             "n_failures": len(ag["fail"]), "failures": ag["fail"][:20]}
        r["timing"] = timing(cs, [nm for nm in cs.layers if nm.startswith("S/")])
        res[p] = r
        print(json.dumps({k: v for k, v in r.items() if k != "failures"}, default=float), flush=True)
        del pm, S, SV, cs
    a.out.mkdir(parents=True, exist_ok=True)
    suf = f"_{a.tag}" if a.tag else ""
    (a.out / f"contours_tubes_p{lo}-{hi}{suf}{a.suffix}.json").write_text(json.dumps(res, indent=1, default=float), "utf-8")
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=("nodes", "tubes"))
    ap.add_argument("--step", type=float, default=0.05)
    ap.add_argument("--tol", type=int, default=1)
    ap.add_argument("--tags", default=",wf6,wf9,wf12")
    ap.add_argument("--phases", default="0-5")
    ap.add_argument("--tag", default="")
    ap.add_argument("--wall-front", type=float, default=None)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--no-fill", dest="fill", action="store_false", help="keep the rows with no node as infeasible")
    ap.add_argument("--suffix", default="", help="file suffix of a trial build (e.g. _s0.1)")
    a = ap.parse_args(argv)
    (nodes if a.what == "nodes" else tubes)(a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
