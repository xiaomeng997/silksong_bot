"""Task 1v1 SG7 (4): the 2026-10-12 live slam hits (sg2_check's set: m2_live_g s1 / s2 hit rows + the 203232 demo
run) on a stored map (forum.md 63).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.sg7_live --tag sg7 --out C:/ssbot/data/m2_map/sg7/live_sg7.json

Per hit, every frame from the antic entry to the hp loss on the map: ground, or the airborne macro states whose
heights match this frame and the HIST - 1 before (sg2_check.LiveCheck's rule), the value = the best key's, the minimum
over the phases and (SG7 stage maps) over the row maps consistent with the stage entries seen by that frame (the
recording's Control states; a timing no variant has: every row map). A hit the map would have walked into has every
located state before it feasible; SG2's count: 44 of 46 passed through an infeasible state first.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from ssbot.tools.sg2_check import EXTRA_RUNS, HIST, live_hits, rec_dirs

STAGES = ("Slam 0", "Slam 1", "Slam 2", "Slam Recover")


def frames_by_k(sl: dict) -> list:
    byk: dict = {}
    for f in sl["frames"]:
        byk[int(round(float(f.get("t") or 0.0) * 60))] = f
    return [byk.get(kk, byk[max(k_ for k_ in byk if k_ <= kk)]) for kk in range(max(byk) + 1)]


def main(argv=None) -> int:
    from ssbot.combat import special_map_rt as smrt
    from ssbot.tools.pogo_theory import load_kin, scan
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", default="sg7")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    params, terrain = load_kin()
    rt = smrt.MapRuntime(params, terrain, smrt.map_path(a.tag))
    ti = rt.ti
    floor = rt.hm.stand_y0
    phases = sorted(rt.srcs)

    def value(k, s, x):
        srcs = rt._srcs(phases)
        return min(max(src.S(k, s, x, c) for c in (-1, 0, 1)) for src in srcs)

    def airborne(k, ys, x, tol=0.06):
        best, n = -np.inf, 0
        for p in phases:
            for s in rt.locate(k, ys, p, tol):
                n += 1
                best = max(best, value(k, s, x))
        return n, (best if n else None)

    hits = live_hits()
    by_run: dict = {}
    for h in hits:
        by_run.setdefault(h["run"], []).append(h)
    todo = []
    for run, hs in by_run.items():
        slams = []
        for d in rec_dirs(run):
            try:
                slams += scan(d)
            except Exception:  # noqa: BLE001
                pass
        for h in hs:
            sl = next((s for s in slams if abs(s["f0"] - h["f_a"]) <= 3), None)
            todo.append((h, sl))
    for run in EXTRA_RUNS:
        for d in rec_dirs(run):
            try:
                sls = scan(d)
            except Exception:  # noqa: BLE001
                continue
            for sl in sls:
                lost = [f for f in sl["frames"] if f.get("hpl")]
                if lost:
                    todo.append(({"arm": "demo", "run": run, "f_a": sl["f0"], "src": str(lost[0]["hpl"][0])}, sl))
    out = []
    for h, sl in todo:
        if sl is None:
            out.append({"hit": h, "error": "slam not found"})
            continue
        fr = frames_by_k(sl)
        cx0 = fr[0]["pos"][0]
        face = 1 if fr[0]["flip"] else -1
        seen: dict = {}
        rows, k_hit = [], None
        for k, f in enumerate(fr):
            st = f.get("st")
            if st in STAGES and st not in seen:
                seen[st] = k
            if k_hit is None and f.get("hpl"):
                k_hit = k
            hb = f.get("hbox")
            if not hb or k >= ti.K - 1:
                continue
            rt.observe(dict(seen), k) if rt.stage else None
            x = (0.5 * (hb[0] + hb[2]) - cx0) * face
            y = hb[1] - floor
            ys = [(fr[k - i]["hbox"][1] - floor) for i in range(HIST) if k - i >= 0 and fr[k - i].get("hbox")]
            yprev = ys[1] if len(ys) > 1 else y
            ground = abs(y) < 0.03 and abs(y - yprev) < 0.01
            umb = "Umbrella" in str(f.get("clip_h") or "") or "Float" in str(f.get("clip_h") or "")
            if ground:
                sc, n = value(k, 0, x), 1
            elif umb or len(ys) < HIST:
                sc, n = None, 0
            else:
                n, sc = airborne(k, ys, x)
            rows.append({"k": k, "x": round(x, 2), "y": round(y, 2), "ground": ground, "match": n, "score": sc})
        rt.observe(None)
        k_hit = k_hit if k_hit is not None else (rows[-1]["k"] if rows else 0)
        pre = [r for r in rows if r["k"] <= k_hit]
        fi = next((r["k"] for r in pre if r["score"] is not None and not np.isfinite(r["score"])), None)
        loc = [r for r in pre if r["score"] is not None]
        out.append({"hit": h, "k_hit": k_hit, "seen": seen, "first_infeasible_k": fi,
                    "lead_frames": (k_hit - fi) if fi is not None else None,
                    "k0": pre[0] if pre else None, "located": len(loc),
                    "all_located_feasible": bool(loc) and all(np.isfinite(r["score"]) for r in loc),
                    "off_map_airborne": sum(1 for r in pre if not r["ground"] and not r["match"])})
    ok = [r for r in out if "error" not in r]
    summ = {"tag": a.tag, "hits": len(out), "located": len(ok),
            "infeasible_before_hit": sum(1 for r in ok if r["first_infeasible_k"] is not None),
            "walked_into": sum(1 for r in ok if r["first_infeasible_k"] is None and r["located"]),
            "k0_feasible": sum(1 for r in ok if r["k0"] and r["k0"]["score"] is not None and np.isfinite(r["k0"]["score"])),
            "k0_airborne": sum(1 for r in ok if r["k0"] and not r["k0"]["ground"]),
            "lead_median": float(np.median([r["lead_frames"] for r in ok if r["lead_frames"] is not None]))
            if any(r["lead_frames"] is not None for r in ok) else None}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps({"summary": summ, "rows": out}, indent=1, default=float), "utf-8")
    print(json.dumps(summ))
    for r in ok:
        if r["first_infeasible_k"] is None:
            print("walked into:", r["hit"], r["k_hit"], r["seen"], r["located"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
