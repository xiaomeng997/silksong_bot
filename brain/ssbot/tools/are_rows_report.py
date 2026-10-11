"""A compact table of an attack-range eval (tools.attack_range_build eval rows_<set>.pkl): per family x k the main rows'
coverage, precision ratio (area, p90, share <= 1.5) and miss p95 per side, split by the decision for decided families
(decided / pending) and by state for chosen families. Stage B's report tool (the forum.md tables).

    ../scripts/uv.cmd run python -m ssbot.tools.are_rows_report --type tiny [--sets fresh,r2,person] [--by-state AT_DIVE]
"""
from __future__ import annotations

import argparse
import json
import pickle
from collections import defaultdict

import numpy as np

from ssbot.tools.attack_range_build import SIDES, out_dir, spec_of


def stats(rs: list) -> dict:
    rs = [r for r in rs if not r["next"] and not r["int"]]
    if not rs:
        return {"n": 0}
    aR = sum(r["aR"] for r in rs)
    wr = [r for r in rs if r["aR"] > 0]
    ratios = [r["aE"] / r["aR"] for r in wr]
    d = {"n": len(rs), "cover": round(sum(r["aI"] for r in rs) / aR, 4) if aR > 0 else None,
         "ratio_area": round(sum(r["aE"] for r in wr) / max(sum(r["aR"] for r in wr), 1e-9), 3) if wr else None,
         "ratio_p90": round(float(np.percentile(ratios, 90)), 2) if ratios else None,
         "ok": round(float(np.mean([x <= 1.5 for x in ratios])), 3) if ratios else None}
    miss = {}
    for sd in SIDES:
        m = [r["miss"][sd][0] for r in rs if sd in r["miss"]]
        if m:
            miss[sd] = round(float(np.percentile(m, 95)), 2)
    d["miss_p95"] = miss
    return d


def report(spec, sets, by_state=()) -> dict:
    out = {}
    for s in sets:
        p = out_dir(spec) / f"rows_{s}.pkl"
        if not p.exists():
            continue
        rows = pickle.load(open(p, "rb"))
        g = defaultdict(list)
        for r in rows:
            if r["k"] not in (0, 12):
                continue
            g[(r["fam"], r["k"], "all")].append(r)
            if "dec" in r:
                g[(r["fam"], r["k"], "decided" if r["dec"] else "pending")].append(r)
            if r["fam"] in by_state:
                g[(r["fam"], r["k"], f"st={r.get('st', '?')}")].append(r)
        out[s] = {f"{fam} k{k} {part}": stats(v) for (fam, k, part), v in sorted(g.items())}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", required=True)
    ap.add_argument("--sets", default="fresh,r2,person")
    ap.add_argument("--by-state", default="")
    a = ap.parse_args(argv)
    spec = spec_of(a.type)
    rep = report(spec, a.sets.split(","), tuple(x for x in a.by_state.split(",") if x))
    (out_dir(spec) / "report.json").write_text(json.dumps(rep, indent=1), "utf-8")
    for s, d in rep.items():
        print(f"== {spec.short} {s}")
        for k, v in d.items():
            if v.get("n"):
                print(f"  {k:32s} n {v['n']:6d} cover {v['cover']} ratio {v['ratio_area']} p90 {v['ratio_p90']} "
                      f"ok {v['ok']} miss95 {v['miss_p95']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
