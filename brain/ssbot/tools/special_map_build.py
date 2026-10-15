"""Task 1v1 SG2: build the backward score map of the Clapper slam (ssbot.combat.special_map; forum.md 56).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.special_map_build [--out C:/ssbot/data/m2_map/sg2] [--phases 0-5]
        [--no-save] [--wall-front U] [--wall-back U] [--tag NAME]

Writes knowledge/1.0.30000/enemies/forum/special_map_CL_SLAM[_<tag>].npz (levels, see special_map.quantize; meta:
lattice, gamma, robustness, source commits), <out>/build_report.json (build time, size, feasible share per layer, the
strike windows) and <out>/png/*.png (k x x heat maps per layer with the strike region, the person's late-antic
window and the v2 windows).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

import numpy as np

from ssbot.combat import special_map as sm
from ssbot.combat.hero_macros import HeroMacros
from ssbot.combat.move_data import SLAM_TEMPLATE, load_cl_slam

OUT = Path(r"C:\ssbot\data\m2_map\sg2")
# the person's late-antic window (press frame, hero centre to Clapper centre along its facing; forum.md 46 / 53)
PERSON_WINDOW = {"k": (42, 47), "dx": (2.5, 5.0)}
# table v2's windows (G4, forum.md 53): press frame range, dx relative to the Clapper's position at the press
V2_WINDOWS = {"W1": {"k": (0, 42), "dx": (-2.5, -2.0)}, "W2": {"k": (0, 48), "dx": (-1.5, 5.25)},
              "W3": {"k": (57, 74), "dx": (-3.5, 4.25)}}


def setup(cfg: sm.MapConfig | None = None):
    from ssbot.tools.pogo_theory import load_kin
    params, terrain = load_kin()
    hm = HeroMacros(params, terrain)
    spec = load_cl_slam()
    geo = sm.Geometry(spec, hm, cfg or sm.MapConfig())
    return geo


def git_head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              cwd=Path(__file__).resolve().parent, timeout=20).stdout.strip()
    except Exception:  # noqa: BLE001
        return "?"


def sha1(path: Path) -> str:
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()[:12]


def nominal_disp(geo: sm.Geometry) -> np.ndarray:
    """The nominal timing's lunge displacement per frame (to express x relative to the Clapper's position now)."""
    return geo.spec.timeline(K=geo.K + 2).disp


def components(mask: np.ndarray) -> list[np.ndarray]:
    """4-connected components of a 2D boolean mask: a list of index arrays [(k, x)]."""
    lab = np.zeros(mask.shape, np.int64)
    out = []
    for start in zip(*np.nonzero(mask)):
        if lab[start]:
            continue
        lab[start] = len(out) + 1
        stack, cells = [start], []
        while stack:
            a, b = stack.pop()
            cells.append((a, b))
            for da, db in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                u, v = a + da, b + db
                if 0 <= u < mask.shape[0] and 0 <= v < mask.shape[1] and mask[u, v] and not lab[u, v]:
                    lab[u, v] = len(out) + 1
                    stack.append((u, v))
        out.append(np.array(cells))
    return out


def windows(geo: sm.Geometry, strike: np.ndarray, min_cells: int = 4) -> list[dict]:
    """The strike windows: connected regions of (press frame, node x) with a robust strike."""
    disp = nominal_disp(geo)
    out = []
    for cells in components(strike > 0):
        if len(cells) < min_cells:
            continue
        ks, xi = cells[:, 0], cells[:, 1]
        x = geo.xs[xi]
        rel = x - disp[np.clip(ks, 0, len(disp) - 1)]
        sc = strike[ks, xi]
        out.append({"k": [int(ks.min()), int(ks.max())], "x_anchor": [round(float(x.min()), 2), round(float(x.max()), 2)],
                    "dx_now": [round(float(rel.min()), 2), round(float(rel.max()), 2)], "cells": int(len(cells)),
                    "score_mean": round(float(sc.mean()), 3), "deep_cells": int((sc >= 1.99).sum())})
    out.sort(key=lambda w: (w["k"][0], w["x_anchor"][0]))
    return out


def per_frame_ranges(geo: sm.Geometry, strike: np.ndarray, k0: int, k1: int) -> list[dict]:
    disp = nominal_disp(geo)
    rows = []
    for k in range(k0, k1 + 1):
        xi = np.flatnonzero(strike[k] > 0)
        if not len(xi):
            rows.append({"k": k, "n": 0})
            continue
        # contiguous runs
        runs, s = [], xi[0]
        for a, b in zip(xi[:-1], xi[1:]):
            if b != a + 1:
                runs.append((s, a))
                s = b
        runs.append((s, xi[-1]))
        rows.append({"k": k, "n": int(len(xi)),
                     "runs_dx_now": [[round(float(geo.xs[a] - disp[k]), 2), round(float(geo.xs[b] - disp[k]), 2)]
                                     for a, b in runs]})
    return rows


def window_overlap(geo: sm.Geometry, strike: np.ndarray, w: dict) -> dict:
    disp = nominal_disp(geo)
    tot = hit = 0
    for k in range(w["k"][0], w["k"][1] + 1):
        rel = geo.xs - disp[k]
        sel = (rel >= w["dx"][0]) & (rel <= w["dx"][1])
        tot += int(sel.sum())
        hit += int((strike[k][sel] > 0).sum())
    return {"cells": tot, "strike_cells": hit, "share": round(hit / max(tot, 1), 3)}


# ---- PNGs ----
SX, SK = 4, 6                       # px per x cell, per frame


def heat(geo: sm.Geometry, layer: np.ndarray, kmax: int, title: str, strike: np.ndarray | None, path: Path,
         vmax: float = 4.0, marks: bool = True):
    import cv2
    a = layer[:kmax + 1]
    h, w = a.shape
    v = np.clip(np.nan_to_num(a, nan=0.0, neginf=0.0) / vmax, 0, 1)
    img = cv2.applyColorMap((v * 255).astype(np.uint8), cv2.COLORMAP_VIRIDIS)
    img[np.isneginf(a)] = (40, 20, 110)          # infeasible: dark red (BGR)
    img[np.isnan(a)] = (90, 90, 90)              # no node of this class
    img = cv2.resize(img, (w * SX, h * SK), interpolation=cv2.INTER_NEAREST)
    if strike is not None:
        m = (strike[:kmax + 1] > 0).astype(np.uint8)
        m = cv2.resize(m, (w * SX, h * SK), interpolation=cv2.INTER_NEAREST)
        cs, _ = cv2.findContours(m, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        cv2.drawContours(img, cs, -1, (255, 255, 255), 1)
    disp = nominal_disp(geo)

    def xpx(x):
        return int(round((x - geo.cfg.x_lo) / geo.step * SX + SX / 2))

    if marks:
        def rect_now(win, col):
            for k in range(win["k"][0], min(win["k"][1], kmax) + 1):
                x0, x1 = win["dx"][0] + disp[k], win["dx"][1] + disp[k]
                cv2.line(img, (xpx(x0), k * SK), (xpx(x0), k * SK + SK), col, 1)
                cv2.line(img, (xpx(x1), k * SK), (xpx(x1), k * SK + SK), col, 1)
            for k in (win["k"][0], min(win["k"][1], kmax) + 1):
                kk = min(k, kmax)
                cv2.line(img, (xpx(win["dx"][0] + disp[kk]), k * SK), (xpx(win["dx"][1] + disp[kk]), k * SK), col, 1)
        for nm, win in V2_WINDOWS.items():
            rect_now(win, (255, 255, 0))
            cv2.putText(img, nm, (xpx(win["dx"][0] + disp[win["k"][0]]) + 2, win["k"][0] * SK + 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 0), 1)
        rect_now(PERSON_WINDOW, (0, 230, 255))
    # axes: x ticks every 2 u, k ticks every 10 frames
    pad = np.full((30, img.shape[1], 3), 255, np.uint8)
    for x in range(int(np.ceil(geo.cfg.x_lo)) + 2, int(geo.cfg.x_hi) + 1, 2):
        cv2.line(img, (xpx(x), 0), (xpx(x), 4), (255, 255, 255), 1)
        cv2.putText(pad, f"{x}", (xpx(x) - 6, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.33, (0, 0, 0), 1)
    cv2.putText(pad, title, (4, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 0, 0), 1)
    side = np.full((img.shape[0], 34, 3), 255, np.uint8)
    for k in range(0, kmax + 1, 10):
        cv2.putText(side, f"{k}", (2, k * SK + 8), cv2.FONT_HERSHEY_SIMPLEX, 0.33, (0, 0, 0), 1)
    body = np.hstack([side, img])
    top = np.hstack([np.full((30, 34, 3), 255, np.uint8), pad])
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), np.vstack([top, body]))


def pngs(geo: sm.Geometry, maps: list[sm.PhaseMap], out: Path) -> list[str]:
    kmax = geo.end_max + 12
    strike = np.stack([m.strike for m in maps]).max(0)
    ground = np.stack([m.ground for m in maps]).min(0)
    files = []
    heat(geo, ground, kmax, "ground layer (min over the 6 physics phases); white: strike region (press frame, x); "
         "yellow: the person's window; cyan: v2 W1-W3", strike, out / "ground.png")
    heat(geo, np.where(strike > 0, strike, np.nan), kmax, "strike score 1 + depth by press frame and node x (any "
         "layer, any phase)", strike, out / "strike.png", vmax=2.0)
    files += ["ground.png", "strike.png"]
    for ti, t in enumerate(geo.tubes):
        if t.kind == "ground":
            continue
        a = np.stack([m.apex[ti] for m in maps])
        layer = np.where(np.isnan(a).all(0), np.nan, np.nanmin(np.where(np.isnan(a), np.inf, a), axis=0))
        layer[np.isposinf(layer)] = np.nan
        nm = f"apex_{t.kind}_{t.param:g}.png"
        lab = (f"apex layer: ground jump hold {t.param:g} (apex {t.y[0, t.apex[0]]:.2f} u)" if t.kind == "jump" else
               f"apex layer: bounce, contact height {t.param:g} u (apex {t.param + 4.09:.2f} u)")
        heat(geo, layer, kmax, lab + " - min over phases", strike, out / nm)
        files.append(nm)
    return files


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--phases", default="0-5")
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--no-png", action="store_true")
    ap.add_argument("--wall-front", type=float, default=None)
    ap.add_argument("--wall-back", type=float, default=None)
    ap.add_argument("--tag", default="")
    a = ap.parse_args(argv)
    lo, hi = (int(v) for v in a.phases.split("-")) if "-" in a.phases else (int(a.phases), int(a.phases))
    t0 = time.time()
    cfg = sm.MapConfig(wall_front=a.wall_front, wall_back=a.wall_back)
    geo = setup(cfg)
    b = sm.MapBuilder(geo)
    maps = [b.build(p) for p in range(lo, hi + 1)]
    build_s = time.time() - t0
    strike = np.stack([m.strike for m in maps]).max(0)
    strike_all = np.stack([m.strike for m in maps]).min(0)
    kend = geo.end_max
    rep = {"seconds": round(build_s, 1), "geometry_seconds": round(geo.seconds, 1),
           "per_phase_seconds": [m.stats["seconds"] for m in maps], "K": geo.K, "NX": geo.NX, "NS": geo.NS,
           "end_min": geo.end_min, "end_max": geo.end_max, "variants": len(geo.variants), "config": cfg.key()}
    ground = np.stack([m.ground for m in maps])
    rep["feasible_share"] = {"ground": round(float(np.isfinite(ground[:, :kend + 1]).mean()), 3)}
    rep["strike_reach_share"] = {"ground": round(float((ground[:, :kend + 1] >= 0.5).mean()), 3)}
    for ti, t in enumerate(geo.tubes):
        if t.kind == "ground":
            continue
        A = np.stack([m.apex[ti, :kend + 1] for m in maps])
        node = ~np.isnan(A)
        nm = f"{t.kind}_{t.param:g}"
        rep["feasible_share"][nm] = round(float(np.isfinite(A[node]).mean()), 3) if node.any() else None
        rep["strike_reach_share"][nm] = round(float((A[node] >= 0.5).mean()), 3) if node.any() else None
    rep["windows_any_phase"] = windows(geo, strike)
    rep["windows_all_phases"] = windows(geo, strike_all)
    rep["per_frame_38_56"] = per_frame_ranges(geo, strike, 38, 56)
    rep["person_window"] = PERSON_WINDOW | window_overlap(geo, strike, PERSON_WINDOW)
    rep["v2_windows"] = {nm: w | window_overlap(geo, strike, w) for nm, w in V2_WINDOWS.items()}
    rep["readiness_k0"] = {f"{x:g}": round(float(np.nanmin(ground[:, 0, geo.x_index(x)])), 3)
                           for x in (-6, -4, -3, -2.5, 2.5, 3, 4, 5, 6, 8, 10, 11, 12, 13)}
    meta = {"enemy": "Song Heavy Sentry", "move": "CL_SLAM", "source_commit": git_head(),
            "inputs": {"slam_template": f"{SLAM_TEMPLATE.name}@{sha1(SLAM_TEMPLATE)}",
                       "move_data": "ssbot.combat.move_data.load_cl_slam (SG1 6f21763)",
                       "hero_macros": "ssbot.combat.hero_macros (SG1 6f21763), Wanderer params, Forum terrain"},
            "robust_share": 1.0, "variant_policy": cfg.variants, "phases": list(range(lo, hi + 1)),
            "built": time.strftime("%Y-%m-%d %H:%M:%S"),
            "frame": "k: frame from the antic entry (state at the end of frame k); x: hero box centre along the "
                     "Clapper's facing relative to its position at k = 0 (u); one map per physics phase p (the "
                     "hero's 50 Hz cycle position at k = 0)"}
    if not a.no_save:
        path = sm.MAP_DIR / f"special_map_CL_SLAM{('_' + a.tag) if a.tag else ''}.npz"
        sm.save_map(path, geo, maps, meta)
        rep["file"] = str(path)
        rep["file_bytes"] = path.stat().st_size
    if not a.no_png:
        rep["png"] = pngs(geo, maps, a.out / "png" / (a.tag or "open"))
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / f"build_report{('_' + a.tag) if a.tag else ''}.json").write_text(json.dumps(rep, indent=1), "utf-8")
    print(json.dumps({k: rep[k] for k in ("seconds", "per_phase_seconds", "feasible_share", "windows_any_phase",
                                          "person_window", "v2_windows", "readiness_k0") if k in rep}, indent=1))
    print("file", rep.get("file"), rep.get("file_bytes"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
