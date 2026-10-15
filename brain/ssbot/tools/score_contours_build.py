"""Task 1v1 SG3 / SG3b: convert SG2's special maps into score contours (ssbot.combat.score_contours; forum.md 57-58).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.score_contours_build nodes [--bands 5 --scope layer] [--tags ,wf6,wf9,wf12]
    ../scripts/uv.cmd run python -m ssbot.tools.score_contours_build tubes --phases 0-1 [--bands 3,4,5 --scope layer,frame --tol 0,1]
    ../scripts/uv.cmd run python -m ssbot.tools.score_contours_build tubes --phases 0-1 --step 0.05 [--suffix _s0.05]

Two band modes:
  equal_area (default; SG3b, the person 2026-10-15): the feasibility ring (score 0 vs > 0) exact, inside n bands of
    equal area (score_contours.equal_area_edges: the most equal partition of the feasible cells' scores, a score
    value never split). Scope "layer": one set of edges per 2-D layer over its whole (k, x) plane; scope "frame": one
    set per frame k shared by every layer of the file (the tube files: pooled over the S layers of every slice that is
    a state at k; the strike layers SV use the same edges, so S and SV order alike at one frame; the node file: per
    phase over its ground, apex and jump-start layers). A band stands for its lower edge (band 0: 0.0). Inner rings
    exact on the lattice (--tol 0, default) or +-1 band (--tol 1). Files: <base>_ea<n><l|f>[_t1].npz; meta.banding
    holds the mode, the bands, the scope, the tol and the edges (frame scope: per frame in meta and in the array
    x_edges; layer scope: the array x_edges [layer, n - 1] in the order of meta.names; +inf / null: no such edge).
  step (SG3): band = floor(score / step), inner rings +-tol; --step S selects it (files <base>[--suffix]).

nodes: the stored map (knowledge/.../special_map_CL_SLAM[_<tag>].npz: per phase the ground layer, the 48 apex layers
and the 18 jump-start layers) -> special_map_CL_SLAM[_<tag>]_contours<suffix>.npz (layers p<p>/ground, p<p>/apex/<i>,
p<p>/jump/<h>; meta: the rows with no node (NaN) per apex layer).
tubes: SG2's full pass of one phase (every macro state; MapBuilder.build(keep_full)) -> special_map_CL_SLAM_tubes_p<p>
[_<tag>]<suffix>.npz: per slice s the score layer S/<s>, the strike layers SV<d+1>/<s> (a slash pressed next frame with
key d held) and the press flags P<d+1>/<s> (the strike is the node's best continuation within 0.01; binary, exact);
meta: the tube index (map_lookahead.TubeIndex). Empty layers (all infeasible) are not stored. One pass serves every
requested variant (the binary press layers are contoured once).
Checks: every layer on every lattice point against its bands, once in memory and once more after the file is written
and read back (the integer coordinate encoding): feasibility exact, inner bands exact (tol 0) or within +-tol; rings,
orientation, tree. Reports: C:/ssbot/data/m2_map/sg3b/contours_<what>[_<tag>]<suffix>.json.
"""
from __future__ import annotations

import argparse
import json
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ssbot.combat import map_lookahead as ml
from ssbot.combat import score_contours as sc
from ssbot.combat import special_map as sm

OUT = Path(r"C:\ssbot\data\m2_map\sg3b")
DEFAULT_BANDS = 5                 # SG3b's recommendation (forum.md 58): 5 bands, one set of edges per layer,
DEFAULT_SCOPE = "layer"           # inner rings exact (--tol 0)
SCOPES = ("layer", "frame")


@dataclass
class Banding:
    """How a score layer becomes integer bands (see the module doc)."""
    mode: str = "equal_area"       # equal_area | step
    n: int = DEFAULT_BANDS
    scope: str = DEFAULT_SCOPE     # layer | frame
    tol: int = 0                   # inner rings: 0 exact on the lattice, 1 +-1 band
    step: float = 0.0              # step mode only
    fedges: dict = field(default_factory=dict)      # frame scope: group (phase) -> [K, n - 1] (+inf padded)
    ledges: dict = field(default_factory=dict)      # layer scope: layer name -> [m]

    @property
    def suffix(self) -> str:
        if self.mode == "step":
            return ""
        return f"_ea{self.n}{self.scope[0]}" + (f"_t{self.tol}" if self.tol else "")

    def set_frame_edges(self, group, pools: list):
        """pools[k]: the feasible scores at frame k of every layer of the group."""
        self.fedges[group] = sc.pad_edges([sc.equal_area_edges(v, self.n) for v in pools], self.n - 1)

    def bands(self, name: str, score: np.ndarray, valid: np.ndarray | None = None, group=None) -> np.ndarray:
        """The bands of one layer (rows not in `valid` are not part of the layer: they do not enter the layer
        scope's edges)."""
        if self.mode == "step":
            return sc.to_bands(score, self.step)
        if self.scope == "frame":
            return sc.bands_from_edges(score, self.fedges[group])
        if name not in self.ledges:
            v = score[valid] if valid is not None else score
            self.ledges[name] = sc.equal_area_edges(v, self.n)
        return sc.bands_from_edges(score, self.ledges[name])

    def store(self, cs: sc.ContourSet):
        """The thresholds and the scope into the file (meta.banding; the arrays x_edges / x_edges_<group>)."""
        if self.mode == "step":
            cs.meta["banding"] = {"mode": "step", "step": self.step, "tol": self.tol}
            return
        b = {"mode": "equal_area", "bands": self.n, "scope": self.scope, "tol": self.tol,
             "value": "the band's lower edge (band 0: 0.0)", "edge_rule": "score_contours.equal_area_edges"}
        if self.scope == "frame":
            b["edges"] = {str(g): [[None if not np.isfinite(t) else float(t) for t in row] for row in E]
                          for g, E in self.fedges.items()}
            b["edges_arrays"] = {str(g): f"x_edges_{g}" for g in self.fedges}
            for g, E in self.fedges.items():
                cs.arrays[f"edges_{g}"] = E.astype(np.float32)
        else:
            names = list(cs.layers)
            cs.arrays["edges"] = sc.pad_edges([self.ledges.get(nm, np.zeros(0)) for nm in names],
                                              self.n - 1).astype(np.float32)
            b["edges_array"] = "x_edges: [layer (meta.names order), n - 1]"
        cs.meta["banding"] = b


def check_layer(lay: sc.ContourLayer, B: np.ndarray, tol: int) -> dict:
    """Every lattice point: feasibility exact, |band - true| <= tol; rings: >= 3 points, orientation (outer CCW with
    the high side inside, holes CW), parents contain their children, ring areas positive per level sum."""
    D = lay.dense()
    diff = D.astype(np.int64) - B
    feas = bool(((D >= 0) == (B >= 0)).all())
    a = lay.areas2()
    ok_ring = all(len(r) >= 3 for r in lay.rings)
    sign_ok = True
    for i, p in enumerate(lay.parent):
        if p >= 0 and lay.level[p] == lay.level[i] and np.sign(a[p]) == np.sign(a[i]):
            sign_ok = False
        if p < 0 and a[i] < 0:
            sign_ok = False                                   # a root ring must be an outer ring
    return {"feasibility_exact": feas, "max_band_diff": int(np.abs(diff).max()) if diff.size else 0,
            "n_off": int((diff != 0).sum()), "n_up": int((diff > 0).sum()), "n_down": int((diff < 0).sum()),
            "rings_ok": ok_ring, "orientation_ok": sign_ok,
            "within_tol": bool(np.abs(diff).max() <= tol) if diff.size else True}


def convert(name: str, B: np.ndarray, cs: sc.ContourSet, rep: dict, tol: int, lay: sc.ContourLayer | None = None):
    """Contour the (row-filled) bands B of one layer into cs (or add a layer already contoured) and check it."""
    agg = rep.setdefault("agg", {"layers": 0, "rings": 0, "points_raw": 0, "points": 0, "seconds": 0.0,
                                 "orientation_flips": 0, "cells": 0, "dense_zlib": 0, "off": 0, "fail": [],
                                 "tree_changed": 0})
    if B.max() < 0:
        rep["empty"] = rep.get("empty", 0) + 1
        return None
    if lay is None:
        lay = sc.ContourLayer.from_bands(B, cs.step, simplify=True, tol=tol)
        chk = check_layer(lay, B, tol)
        chk["tree_kept"] = lay.stats["tree_kept"]
        lay.stats["check"] = chk
    chk = lay.stats["check"]
    cs.add(name, lay)
    agg["layers"] += 1
    for k in ("rings", "points_raw", "points", "orientation_flips"):
        agg[k] += lay.stats[k]
    agg["seconds"] += lay.stats["seconds"]
    agg["cells"] += B.size
    agg["dense_zlib"] += len(zlib.compress(B.astype(np.uint8).tobytes(), 6))
    agg["off"] += chk["n_off"]
    agg["tree_changed"] += not chk["tree_kept"]
    if not (chk["feasibility_exact"] and chk["within_tol"] and chk["rings_ok"] and chk["orientation_ok"]
            and chk["tree_kept"]):
        agg["fail"].append({"layer": name, **chk})
    return lay


def verify_file(path: Path, bands_of, names: list, tol: int) -> dict:
    """Read the written file back and check every layer on every lattice point against its bands (the integer
    coordinate encoding included): feasibility exact; inner bands exact (tol 0) or within +-tol. A layer named but
    not stored must be all infeasible."""
    t0 = time.time()
    cs = sc.ContourSet.load(path)
    out = {"layers": 0, "points": 0, "feasibility_mismatch": 0, "inner_mismatch": 0, "beyond_tol": 0,
           "missing_not_empty": 0, "bad_layers": []}
    for nm in names:
        B = bands_of(nm)
        lay = cs.layers.get(nm)
        if lay is None:
            if B.max() >= 0:
                out["missing_not_empty"] += 1
                out["bad_layers"].append(nm)
            continue
        D = lay.dense()
        out["layers"] += 1
        out["points"] += B.size
        fm = int(((D >= 0) != (B >= 0)).sum())
        diff = np.abs(D.astype(np.int64) - B)
        out["feasibility_mismatch"] += fm
        out["inner_mismatch"] += int((diff != 0).sum())
        out["beyond_tol"] += int((diff > tol).sum())
        if fm or (diff > tol).any():
            out["bad_layers"].append(nm)
    out["bad_layers"] = out["bad_layers"][:20]
    out["ok"] = not (out["feasibility_mismatch"] or out["beyond_tol"] or out["missing_not_empty"])
    out["seconds"] = round(time.time() - t0, 1)
    return out


def share_stats(units: list, n: int) -> dict:
    """units: per scope unit (a layer or a frame) the cell count per band (feasible cells of the rows that are
    states). Mean shares, the units whose lowest band is larger than 1 / n (an atom: the plateau), and per unit the
    largest |share - 1 / (bands present)| over its bands, p50 / p90 / max."""
    C = np.array([u for u in units if np.sum(u) > 0], np.float64)
    if not len(C):
        return {}
    S = C / C.sum(1, keepdims=True)
    nb = (C > 0).sum(1)
    dev = np.abs(S - 1.0 / nb[:, None]) * (C > 0)
    md = dev.max(1)
    return {"units": len(C), "mean_shares": np.round(S.mean(0), 4).tolist(),
            "bands_present_mean": round(float(nb.mean()), 2),
            "units_band0_over_1_n": int((S[:, 0] > 1.0 / n + 1e-9).sum()),
            "max_dev_p50": round(float(np.median(md)), 4), "max_dev_p90": round(float(np.quantile(md, 0.9)), 4),
            "max_dev_max": round(float(md.max()), 4)}


def nodes(a) -> dict:
    out = {}
    for tag in a.tags.split(","):
        suf = f"_{tag}" if tag else ""
        src = sm.MAP_DIR / f"special_map_CL_SLAM{suf}.npz"
        if not src.exists():
            continue
        m = sm.SpecialMap(src)
        G, A, J = m._ground, m.apex, m.jump_start
        for band in a.variants:
            fsuf = band.suffix if band.mode != "step" else a.suffix
            cs = sc.ContourSet(m.K, m.NX, band.step, {"source": src.name, "x_lo": m.x_lo, "lattice_step": m.step,
                                                      "fill": a.fill, "tol": band.tol, "classes": m.classes,
                                                      "jump_holds": m.holds, "map_meta": m.meta})
            rep = {}
            none_rows = {}
            specs = {}
            t0 = time.time()
            units = []
            for p in range(G.shape[0]):
                lays = [(f"p{p}/ground", G[p], None)]
                for i in range(A.shape[1]):
                    nr = np.isnan(A[p, i]).all(1)
                    if nr.any():
                        none_rows[f"p{p}/apex/{i}"] = np.flatnonzero(nr).tolist()
                    lays.append((f"p{p}/apex/{i}", A[p, i], ~nr if a.fill else None))
                for i, h in enumerate(m.holds):
                    lays.append((f"p{p}/jump/{h:g}", J[p, i], None))
                if band.mode != "step" and band.scope == "frame":
                    band.set_frame_edges(p, [np.concatenate([L[k][np.isfinite(L[k])] for _, L, _ in lays])
                                             for k in range(m.K)])
                fcount = np.zeros((m.K, max(band.n, 1)), np.int64)
                for nm, L, vr in lays:
                    B0 = band.bands(nm, L, None if vr is None else vr, group=p)
                    if band.mode != "step":
                        if band.scope == "layer":
                            units.append(np.bincount(B0[B0 >= 0], minlength=band.n)[:band.n])
                        else:
                            for k in range(m.K):
                                r = B0[k][B0[k] >= 0]
                                fcount[k] += np.bincount(r, minlength=band.n)[:band.n]
                    B = sc.fill_rows(B0, vr) if vr is not None else B0
                    specs[nm] = B
                    convert(nm, B, cs, rep, band.tol)
                if band.mode != "step" and band.scope == "frame":
                    units += list(fcount)
            cs.meta["none_rows"] = none_rows
            band.store(cs)
            dst = sm.MAP_DIR / f"special_map_CL_SLAM{suf}_contours{fsuf}.npz"
            info = cs.save(dst)
            ver = verify_file(dst, lambda nm: specs[nm], list(specs), band.tol)
            ag = rep["agg"]
            r = {"file": str(dst), "bytes": info["bytes"], "source_npz_bytes": src.stat().st_size,
                 "layers": ag["layers"], "empty_layers": rep.get("empty", 0), "rings": ag["rings"],
                 "points_raw": ag["points_raw"], "points": ag["points"], "cells": ag["cells"],
                 "dense_bands_zlib_bytes": ag["dense_zlib"],
                 "ratio_vs_dense_zlib": round(ag["dense_zlib"] / info["bytes"], 3),
                 "simplify_keep": round(ag["points"] / max(ag["points_raw"], 1), 3),
                 "orientation_flips": ag["orientation_flips"], "tree_changed": ag["tree_changed"],
                 "lattice_points_off": ag["off"], "share_off": round(ag["off"] / ag["cells"], 4),
                 "failures": ag["fail"][:20], "n_failures": len(ag["fail"]), "verify_after_encoding": ver,
                 "band_areas": share_stats(units, band.n) if band.mode != "step" else None,
                 "seconds": round(time.time() - t0, 1)}
            r["timing"] = timing(cs, [nm for nm in cs.layers if nm.startswith("p0/")])
            out[(tag or "open") + fsuf] = r
            print(json.dumps({k: v for k, v in r.items() if k != "failures"}, default=float), flush=True)
    a.out.mkdir(parents=True, exist_ok=True)
    vs = "_".join(b.suffix.strip("_") or f"s{b.step:g}" for b in a.variants)
    (a.out / f"contours_nodes_{vs}{a.suffix}.json").write_text(json.dumps(out, indent=1, default=float), "utf-8")
    return out


def timing(cs: sc.ContourSet, names: list, n: int = 3000, seed: int = 57) -> dict:
    """Single lattice queries (compiled winding + level binary search) over random (layer, k, x): p50 / p99 (us)."""
    rng = np.random.default_rng(seed)
    lays = [cs.layers[nm] for nm in names]
    if not lays:
        return {}
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
    suf = f"_{a.tag}" if a.tag else ""
    res = {}
    for p in range(lo, hi + 1):
        t0 = time.time()
        pm = b.build(p, keep_full=True)
        tb = time.time() - t0
        S, SV = pm.S, pm.SV
        VR = np.stack([ti.valid_rows(p, s) for s in range(geo.NS)], 1) if a.fill else None    # [K, NS]
        q = sm.quantize(S.astype(np.float32))
        dense_z = len(zlib.compress(q.tobytes(), 6)) + len(zlib.compress(sm.quantize(SV.astype(np.float32)).tobytes(), 6))
        del q
        # the press flags: binary, the same in every variant (contoured once)
        plays, pflags = {}, {}
        t1 = time.time()
        for s in range(min(geo.NS, a.max_slices)):
            Ss = S[:, s, :].astype(np.float32)
            for di in range(3):
                sv = SV[:, s, :, di].astype(np.float32)
                if not np.isfinite(sv).any():
                    continue
                B = np.where(np.isfinite(sv) & (sv >= Ss - ml.PRESS_EPS), 0, -1).astype(np.int16)
                if VR is not None:
                    B = sc.fill_rows(B, VR[:, s])
                pflags[f"P{di}/{s}"] = B
                if B.max() >= 0:
                    L = sc.ContourLayer.from_bands(B, 0.0, simplify=True, tol=0)
                    L.stats["check"] = dict(check_layer(L, B, 0), tree_kept=L.stats["tree_kept"])
                    plays[f"P{di}/{s}"] = L
        tp = time.time() - t1
        res[p] = {"phase": p, "build_pass_s": round(tb, 1), "press_layers_s": round(tp, 1),
                  "dense_float16_bytes": S.nbytes + SV.nbytes, "dense_levels_zlib_bytes": dense_z, "variants": {}}
        for band in a.variants:
            t2 = time.time()
            if band.mode != "step" and band.scope == "frame":
                pools = []
                for k in range(geo.K):
                    row = S[k].astype(np.float32)                  # [NS, NX]
                    msk = np.isfinite(row) & (VR[k][:, None] if VR is not None else True)
                    pools.append(row[msk])
                band.set_frame_edges(p, pools)
            band.ledges = {}
            cs = sc.ContourSet(geo.K, geo.NX, band.step, {"phase": p, "tubes": ti.to_dict(), "tol": band.tol,
                                                          "fill": a.fill, "config": geo.cfg.key(), "what": "tubes"})
            rep = {}
            units = []
            fcount = np.zeros((geo.K, band.n), np.int64) if band.mode != "step" else None

            def raw(nm):
                kind, s = nm.split("/")
                s = int(s)
                if kind == "S":
                    return S[:, s, :].astype(np.float32), s
                return SV[:, s, :, int(kind[2:])].astype(np.float32), s

            def bands_of(nm, _band=band):
                if nm.startswith("P"):
                    return pflags[nm]
                sc_, s = raw(nm)
                vr = VR[:, s] if VR is not None else None
                B0 = _band.bands(nm, sc_, vr, group=p)
                return sc.fill_rows(B0, vr) if vr is not None else B0

            names = []
            for s in range(min(geo.NS, a.max_slices)):
                vr = VR[:, s] if VR is not None else None
                for nm in [f"S/{s}"] + [f"SV{di}/{s}" for di in range(3)]:
                    sc_, _ = raw(nm)
                    if nm.startswith("SV") and not np.isfinite(sc_).any():
                        continue
                    B0 = band.bands(nm, sc_, vr, group=p)
                    if band.mode != "step":
                        Bv = B0 if vr is None else np.where(vr[:, None], B0, -1)
                        if band.scope == "layer":
                            units.append(np.bincount(Bv[Bv >= 0], minlength=band.n)[:band.n])
                        elif nm.startswith("S/"):
                            kk, xx = np.nonzero(Bv >= 0)
                            np.add.at(fcount, (kk, Bv[kk, xx]), 1)
                    B = sc.fill_rows(B0, vr) if vr is not None else B0
                    names.append(nm)
                    convert(nm, B, cs, rep, band.tol)
                for di in range(3):
                    nm = f"P{di}/{s}"
                    if nm in pflags:
                        names.append(nm)
                        if nm in plays:
                            convert(nm, pflags[nm], cs, rep, 0, lay=plays[nm])
            if fcount is not None and band.scope == "frame":
                units = list(fcount)
            band.store(cs)
            fsuf = band.suffix if band.mode != "step" else a.suffix
            dst = sm.MAP_DIR / f"special_map_CL_SLAM_tubes_p{p}{suf}{fsuf}.npz"
            info = cs.save(dst)
            ver = verify_file(dst, bands_of, names, band.tol)
            ag = rep["agg"]
            r = {"file": str(dst), "bytes": info["bytes"], "contour_s": round(time.time() - t2, 1),
                 "layers": ag["layers"], "empty_layers": rep.get("empty", 0), "rings": ag["rings"],
                 "points_raw": ag["points_raw"], "points": ag["points"], "cells": ag["cells"],
                 "ratio_vs_float16": round((S.nbytes + SV.nbytes) / info["bytes"], 2),
                 "ratio_vs_levels_zlib": round(dense_z / info["bytes"], 3),
                 "orientation_flips": ag["orientation_flips"], "tree_changed": ag["tree_changed"],
                 "lattice_points_off": ag["off"], "share_off": round(ag["off"] / ag["cells"], 4),
                 "n_failures": len(ag["fail"]), "failures": ag["fail"][:20], "verify_after_encoding": ver,
                 "band_areas": share_stats(units, band.n) if band.mode != "step" else None}
            r["timing"] = timing(cs, [nm for nm in cs.layers if nm.startswith("S/")])
            res[p]["variants"][fsuf or f"s{band.step:g}"] = r
            print(json.dumps({"p": p, "variant": fsuf, **{k: v for k, v in r.items() if k != "failures"}},
                             default=float), flush=True)
            del cs
        del pm, S, SV
        a.out.mkdir(parents=True, exist_ok=True)
        vs = "_".join(b_.suffix.strip("_") or f"s{b_.step:g}" for b_ in a.variants)
        (a.out / f"contours_tubes_p{lo}-{hi}{suf}_{vs}{a.suffix}.json").write_text(
            json.dumps(res, indent=1, default=float), "utf-8")
    return res


def variants_of(a) -> list:
    if a.step is not None:
        return [Banding(mode="step", step=a.step, tol=int(t), n=0, scope="") for t in str(a.tol).split(",")]
    out = []
    for n in str(a.bands).split(","):
        for scope in a.scope.split(","):
            if scope not in SCOPES:
                raise SystemExit(f"--scope: {scope} not in {SCOPES}")
            for t in str(a.tol).split(","):
                out.append(Banding(mode="equal_area", n=int(n), scope=scope, tol=int(t)))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=("nodes", "tubes"))
    ap.add_argument("--bands", default=str(DEFAULT_BANDS), help="equal-area bands (comma list: one file each)")
    ap.add_argument("--scope", default=DEFAULT_SCOPE, help="layer | frame (comma list)")
    ap.add_argument("--step", type=float, default=None, help="fixed score step (SG3's mode) instead of equal areas")
    ap.add_argument("--tol", default=None, help="inner rings: 0 exact (equal-area default), 1 +-1 band (step default)")
    ap.add_argument("--tags", default=",wf6,wf9,wf12")
    ap.add_argument("--phases", default="0-5")
    ap.add_argument("--tag", default="")
    ap.add_argument("--wall-front", type=float, default=None)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--no-fill", dest="fill", action="store_false", help="keep the rows with no node as infeasible")
    ap.add_argument("--max-slices", type=int, default=10 ** 9, help="tubes: the first N slices only (smoke test)")
    ap.add_argument("--suffix", default="", help="step mode: the file suffix of a trial build (e.g. _s0.1)")
    a = ap.parse_args(argv)
    if a.tol is None:
        a.tol = "1" if a.step is not None else "0"
    a.variants = variants_of(a)
    (nodes if a.what == "nodes" else tubes)(a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
