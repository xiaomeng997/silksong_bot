"""The special-move table v2 (task 1v1 G4; the person's design of 2026-10-12, plan doc "合并成几十个带冗余的条目" and
"再粗一层：出手窗口"): today's CL_SLAM theory merged into wide entries with slack, at the theory's native resolution.

  build   T1's theory grids (C:/ssbot/data/m2_pogo/theory/region_*.npz: per press frame x dx x dy (0.25 u) x vy class x
          side x key after the press x jump after the press, the outcomes over 9 timing variants) -> the robust share
          per native cell (the minimum over the variants; specials_build.robust_shares). A cell is good when its share
          is >= --thr, bad when a path reaches it and its share is lower (unknown: no path). Groups: cert (both / bounce) x vy class x key along the Clapper's facing (the follow-up the
          theory has: the key held from the press on). Slack: a cell is a CORE cell when the cells of the same group
          from its frame to --late frames LATER (none earlier: the person; live presses 10-11/12 were 78.2 % on time,
          20.4 % +1, 1.3 % +2, 0.2 % +3, 18 of 221,859 early) and within +-(--space) u in dx and dy are all good.
          Regions: the connected core cells of a group (frame x dx x dy); regions under --min-cells are dropped
          (narrow). Each core cell keeps its slack to the region's boundary (late frames still good after it, space to
          the nearest cell that is not good). Windows: every region's cells projected on (frame, dx) only (cert, vy
          class and follow-up ignored) and connected: the table's top level, holding its regions as sub-options.
          Output: knowledge/.../specials_CL_SLAM_v2.json (entries: one per core run along dy, at the native cell; the
          Lut reads them with the native cell size) and --report (regions and windows, JSON).

The follow-ups of the person's design that the theory grids do not hold (keep side switching to away at frame n, the
chained down slash, certification to the move's last frame k 77 and the end state) need a theory rerun (open item in
forum.md 53); here the follow-up is the key held after the press and the hits are 1.

  scripts/uv.cmd run python -m ssbot.tools.specials_v2 build --report C:/ssbot/data/m2_special/g4/v2_report.json
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from ssbot.combat import specials as sp
from ssbot.tools.specials_build import THEORY, robust_shares

# (side index, post index) per key along the Clapper's facing (as specials_build.build): front paths (side 0) move
# 'toward' = -x, behind paths (side 1) +x; post 0 toward, 1 none, 2 away
KEYS = {1: ((0, 2), (1, 0)), -1: ((0, 0), (1, 2)), 0: ((0, 1), (1, 1))}
CERTS = (("both", 4), ("bounce", 2))


def follow_up(key: int, dx: float) -> str:
    """The follow-up the key after the press is, seen from the hero's side at the press: keep the side (away), switch
    sides (toward: over its head), in place."""
    if key == 0:
        return "in place"
    front = dx >= 0
    return "keep side" if (key == 1) == front else "switch sides"


def _erode(g: np.ndarray, late: int, r: int) -> np.ndarray:
    """[K, X, Y] core: g at k .. k + late and within +-r cells in x and y (out of the grid: not good)."""
    K, X, Y = g.shape
    p = np.zeros((K + late, X + 2 * r, Y + 2 * r), bool)
    p[:K, r:r + X, r:r + Y] = g
    out = np.ones((K, X, Y), bool)
    for d in range(late + 1):
        for i in range(2 * r + 1):
            for j in range(2 * r + 1):
                out &= p[d:d + K, i:i + X, j:j + Y]
    return out


def _late_run(g: np.ndarray) -> np.ndarray:
    """[K, X, Y] the number of consecutive good frames after k at the same cell (k itself not counted)."""
    K = g.shape[0]
    run = np.zeros(g.shape, np.int64)
    for k in range(K - 2, -1, -1):
        run[k] = np.where(g[k + 1], run[k + 1] + 1, 0)
    return run


def _space_slack(g: np.ndarray) -> np.ndarray:
    """[K, X, Y] cells (Chebyshev) to the nearest cell that is not good at the same frame (the grid's edge counts):
    repeated 3x3 erosion in (x, y)."""
    out = np.zeros(g.shape, np.int64)
    cur = g.copy()
    d = 0
    while cur.any():
        d += 1
        out[cur] = d
        p = np.zeros((cur.shape[0], cur.shape[1] + 2, cur.shape[2] + 2), bool)
        p[:, 1:-1, 1:-1] = cur
        nxt = np.ones(cur.shape, bool)
        for i in range(3):
            for j in range(3):
                nxt &= p[:, i:i + cur.shape[1], j:j + cur.shape[2]]
        cur = nxt
    return out


def label(m: np.ndarray, structure=None) -> tuple[np.ndarray, int]:
    """Connected components of a boolean array (full connectivity: every neighbour within 1 on every axis)."""
    lab = np.zeros(m.shape, np.int64)
    n = 0
    offs = [o for o in np.ndindex(*(3,) * m.ndim) if any(v != 1 for v in o)]
    offs = [tuple(v - 1 for v in o) for o in offs]
    for start in zip(*np.nonzero(m)):
        if lab[start]:
            continue
        n += 1
        lab[start] = n
        stack = [start]
        while stack:
            c = stack.pop()
            for o in offs:
                q = tuple(a + b for a, b in zip(c, o))
                if all(0 <= q[i] < m.shape[i] for i in range(m.ndim)) and m[q] and not lab[q]:
                    lab[q] = n
                    stack.append(q)
    return lab, n


def build(paths: list[Path], thr: float, late: int, space_u: float, min_cells: int, kmax: int) -> tuple[list, dict]:
    R, meta = robust_shares(paths)
    KP, DX0, DY0, B = meta["KP"], meta["DX0"], meta["DY0"], meta["B"]
    r = int(round(space_u / B))
    K = min(KP, kmax + 1)
    regions, cells = [], []
    s3 = np.ones((3, 3, 3), bool)
    for cert, ch in CERTS:
        for key, combos in KEYS.items():
            # [K, X, Y, vc, combo, jp] -> best over the combos and the jump after the press
            st = np.stack([R[ch][:K, :, :, :, si, pi, :] for si, pi in combos], axis=-2)
            st = np.where(np.isfinite(st), st, -1.0)
            share = st.max(axis=(-2, -1))                         # [K, X, Y, vc]
            jp = st.max(axis=-2).argmax(axis=-1)                  # [K, X, Y, vc]
            for vc in range(3):
                g = share[..., vc] >= thr
                # bad: a cell some path reaches whose share is under thr (cells no path reaches are unknown, not bad:
                # the theory's paths leave holes in dy and vy)
                bad = (share[..., vc] >= 0) & ~g
                if cert == "bounce":
                    # a 'bounce' cell is one whose both-branch share is under thr (as specials_build): kept apart
                    sb = np.stack([R[4][:K, :, :, vc, si, pi, :] for si, pi in combos], axis=-2)
                    g &= ~(np.where(np.isfinite(sb), sb, -1.0).max(axis=(-2, -1)) >= thr)
                if not g.any():
                    continue
                core = g & _erode(~bad, late, r)
                if not core.any():
                    continue
                lab, n = label(core, structure=s3)
                lr = _late_run(g)
                ss = _space_slack(g)
                for li in range(1, n + 1):
                    m = lab == li
                    ncell = int(m.sum())
                    if ncell < min_cells:
                        continue
                    ks, xs, ys = np.nonzero(m)
                    rid = f"{'G' if cert == 'both' else 'Y'}v{vc}k{key:+d}#{len(regions)}"
                    dxs = DX0 + xs * B
                    reg = {"id": rid, "cert": cert, "vy": vc, "key": key, "cells": ncell,
                           "k": [int(ks.min()), int(ks.max())], "dx": [round(float(dxs.min()), 2),
                                                                       round(float(dxs.max() + B), 2)],
                           "dy": [round(float(DY0 + ys.min() * B), 2), round(float(DY0 + (ys.max() + 1) * B), 2)],
                           "follow": follow_up(key, float(np.median(dxs) + 0.5 * B)),
                           "share_min": round(float(share[ks, xs, ys, vc].min()), 3),
                           "late_p50": float(np.median(lr[ks, xs, ys])), "space_p50_u": float(np.median(ss[ks, xs, ys])) * B,
                           "hits": 1}
                    regions.append(reg)
                    for k_, x_, y_ in zip(ks, xs, ys):
                        cells.append((rid, cert, vc, key, int(k_), int(x_), int(y_), float(share[k_, x_, y_, vc]),
                                      int(jp[k_, x_, y_, vc]), int(lr[k_, x_, y_]), float(ss[k_, x_, y_]) * B))
    # windows: every region's cells on (frame, dx) only, connected
    nx = R[4].shape[1]
    win = np.zeros((K, nx), bool)
    for c in cells:
        win[c[4], c[5]] = True
    wl, nw = label(win, structure=np.ones((3, 3), bool))
    windows = []
    wid_of = {}
    for wi in range(1, nw + 1):
        ks, xs = np.nonzero(wl == wi)
        wid = f"W{wi}"
        subs = sorted({c[0] for c in cells if wl[c[4], c[5]] == wi})
        windows.append({"id": wid, "k": [int(ks.min()), int(ks.max())],
                        "dx": [round(float(DX0 + xs.min() * B), 2), round(float(DX0 + (xs.max() + 1) * B), 2)],
                        "cells_kx": int(len(ks)), "regions": subs,
                        "certs": sorted({c[1] for c in cells if wl[c[4], c[5]] == wi}),
                        "follow": sorted({r_["follow"] for r_ in regions if r_["id"] in subs}),
                        "hits": 1})
        for s in subs:
            wid_of.setdefault(s, wid)
    for reg in regions:
        reg["window"] = wid_of.get(reg["id"], "")
    regions.sort(key=lambda r_: (-r_["hits"], -min(r_["late_p50"], 10) - r_["space_p50_u"], -r_["cells"]))
    # the entries: runs along dy of one region's cells at the same (k, dx)
    runs: dict = {}
    for rid, cert, vc, key, k_, x_, y_, sh, jpv, lt, su in cells:
        runs.setdefault((rid, k_, x_), []).append((y_, cert, vc, key, sh, jpv, lt, su))
    ents = []
    for (rid, k_, x_), ys in runs.items():
        ys.sort()
        i = 0
        while i < len(ys):
            j = i
            while j + 1 < len(ys) and ys[j + 1][0] == ys[j][0] + 1:
                j += 1
            seg = ys[i:j + 1]
            y0, cert, vc, key = seg[0][0], seg[0][1], seg[0][2], seg[0][3]
            ents.append(sp.Entry(
                id=f"CL_SLAM2|{rid}|k{k_}|x{x_}|y{y0}", type_key="Song Heavy Sentry", move="CL_SLAM", kind="down",
                k0=k_, k1=k_, dx0=round(DX0 + x_ * B, 3), dx1=round(DX0 + (x_ + 1) * B, 3),
                dy0=round(DY0 + y0 * B, 3), dy1=round(DY0 + (seg[-1][0] + 1) * B, 3), vy=vc, key=key,
                jpost=int(np.bincount([s[5] for s in seg]).argmax()), cert=cert,
                share=round(min(s[4] for s in seg), 3), hits=1, region=rid, window=wid_of.get(rid, ""),
                slack_t=int(min(s[6] for s in seg)), slack_u=round(min(s[7] for s in seg), 3)))
            i = j + 1
    ents.sort(key=lambda e: (e.k0, e.dx0, e.dy0, e.vy, e.key))
    rep = {"thr": thr, "late": late, "space_u": space_u, "min_cells": min_cells, "kmax": kmax, "native_cell": [1, B, B],
           "regions": regions, "windows": windows, "n_cells": len(cells), "n_entries": len(ents)}
    return ents, rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--thr", type=float, default=0.8)
    b.add_argument("--late", type=int, default=3)
    b.add_argument("--space", type=float, default=0.5)
    b.add_argument("--min-cells", type=int, default=40)
    b.add_argument("--kmax", type=int, default=77)
    b.add_argument("--report", type=Path, required=True)
    b.add_argument("--no-save", action="store_true")
    a = ap.parse_args(argv)
    paths = sorted(THEORY.glob("region_a*.npz")) + [THEORY / "region_nominal.npz"]
    t0 = time.time()
    ents, rep = build(paths, a.thr, a.late, a.space, a.min_cells, a.kmax)
    rep["source"] = [p.name for p in paths]
    rep["s"] = round(time.time() - t0, 1)
    a.report.write_text(json.dumps(rep, indent=1), "utf-8")
    if not a.no_save:
        meta = {k: rep[k] for k in ("thr", "late", "space_u", "min_cells", "kmax", "native_cell", "source")}
        meta["windows"] = rep["windows"]
        sp.SpecialTable(ents).save("CL_SLAM", meta=meta, suffix="_v2")
    print(json.dumps({"regions": len(rep["regions"]), "windows": len(rep["windows"]), "cells": rep["n_cells"],
                      "entries": rep["n_entries"], "s": rep["s"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
