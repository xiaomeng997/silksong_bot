"""One summary of every attack-range type's eval (tools.attack_range_build eval rows_<set>.pkl, R0 fresh / R2 / the
person's sessions): per type and per family at k = 0 and 12 the main rows' coverage (real damage cells inside the
estimate), the miss p95 per side (u, over the rows missing on that side) and the precision RATIO (estimate / real area
in hero-centre space: p50 and the share <= 1.5). Per type the attack families are pooled ("moves"), the hazards /
projectiles ("HZ ...") and idle ("CH_IDLE": the body now) are kept apart. Writes summary.md / summary.json beside the
type folders.

    ../scripts/uv.cmd run python -m ssbot.tools.are_summary [--types clapper,reed] [--sets fresh,r2,person]
"""
from __future__ import annotations

import argparse
import json
import pickle
from collections import defaultdict

import numpy as np

from ssbot.tools.attack_range_build import ARE, IDLE, out_dir, spec_of

TYPES = ("clapper", "choristor", "envoy", "clawmaiden", "spear", "reed", "minister", "bellbearer", "maestro", "tiny")
SETS = ("fresh", "r2", "person")
SIDES4 = ("front", "back", "up", "down")
LIMIT = 1.5


def stats(rs: list) -> dict:
    """Main rows (not next, not interrupted) of one group at one k."""
    rs = [r for r in rs if not r["next"] and not r["int"]]
    if not rs:
        return {"n": 0}
    aR = sum(r["aR"] for r in rs)
    ratios = [r["aE"] / r["aR"] for r in rs if r["aR"] > 0]
    d = {"n": len(rs), "cover": round(sum(r["aI"] for r in rs) / aR, 4) if aR > 0 else None,
         "ratio_p50": round(float(np.median(ratios)), 3) if ratios else None,
         "ratio_ok": round(float(np.mean([x <= LIMIT for x in ratios])), 3) if ratios else None}
    d["miss_p95"] = {sd: round(float(np.percentile(m, 95)), 2)
                     for sd in SIDES4 for m in [[r["miss"][sd][0] for r in rs if sd in r["miss"]]] if m}
    return d


def group_of(fam: str) -> str:
    if fam == IDLE:
        return "idle"
    if fam.startswith("HZ"):
        return "hazards"
    return "moves"


def summarize_type(short: str, sets=SETS) -> dict:
    spec = spec_of(short)
    out = {}
    for s in sets:
        p = out_dir(spec) / f"rows_{s}.pkl"
        if not p.exists():
            continue
        with open(p, "rb") as fh:
            rows = pickle.load(fh)
        g = defaultdict(list)
        for r in rows:
            if r["k"] not in (0, 12):
                continue
            g[(group_of(r["fam"]), r["k"])].append(r)
            g[(r["fam"], r["k"])].append(r)
            if "dec" in r:
                g[(f"{r['fam']} ({'decided' if r['dec'] else 'pending'})", r["k"])].append(r)
        out[s] = {f"{name}|k{k}": stats(v) for (name, k), v in sorted(g.items())}
    return out


def _fmt(d: dict | None) -> str:
    if not d or not d.get("n"):
        return "- | - | -"
    c = "-" if d["cover"] is None else f"{100 * d['cover']:.1f}"
    r = "-" if d["ratio_p50"] is None else f"{d['ratio_p50']:.2f} / {100 * d['ratio_ok']:.0f}%"
    m = " ".join(f"{sd[0]}{v:.1f}" for sd, v in d["miss_p95"].items()) or "-"
    return f"{c} | {r} | {m}"


def markdown(rep: dict) -> str:
    lines = ["# Attack-range estimate: every type (stage C)", "",
             "Main rows (not interrupted, the next move not started before t + k). cover = real damage area inside the "
             "estimate (%); ratio = estimate / real area in hero-centre space, p50 / share <= 1.5; miss p95 = u, per "
             "side (f front, b back, u up, d down), over the rows that miss on that side. moves = every attack family "
             "pooled; hazards = hazards / projectiles; idle = the body now (approved rule).", ""]
    hdr = ("| type | group | set | n k12 | cover k0 | ratio k0 | miss p95 k0 | cover k12 | ratio k12 | miss p95 k12 |\n"
           "|---|---|---|---|---|---|---|---|---|---|")
    lines += ["## Per type", "", hdr]
    for t, by_set in rep.items():
        for grp in ("moves", "hazards", "idle"):
            for s, d in by_set.items():
                a, b = d.get(f"{grp}|k0"), d.get(f"{grp}|k12")
                if not (a and a.get("n")) and not (b and b.get("n")):
                    continue
                lines.append(f"| {t} | {grp} | {s} | {(b or {}).get('n', 0)} | {_fmt(a)} | {_fmt(b)} |")
    lines += ["", "## Per family", ""]
    for t, by_set in rep.items():
        lines += [f"### {t}", "", hdr.replace("| type | group |", "| type | family |")]
        names = sorted({k.rsplit("|", 1)[0] for d in by_set.values() for k in d}
                       - {"moves", "hazards", "idle"})
        for nm in names:
            for s, d in by_set.items():
                a, b = d.get(f"{nm}|k0"), d.get(f"{nm}|k12")
                if not (a and a.get("n")) and not (b and b.get("n")):
                    continue
                lines.append(f"| {t} | {nm} | {s} | {(b or {}).get('n', 0)} | {_fmt(a)} | {_fmt(b)} |")
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--types", default=",".join(TYPES))
    ap.add_argument("--sets", default=",".join(SETS))
    a = ap.parse_args(argv)
    rep = {}
    for t in [x for x in a.types.split(",") if x]:
        rep[t] = summarize_type(t, a.sets.split(","))
        print(t, {s: len(d) for s, d in rep[t].items()}, flush=True)
    (ARE / "summary.json").write_text(json.dumps(rep, indent=1), "utf-8")
    (ARE / "summary.md").write_text(markdown(rep), "utf-8")
    print(ARE / "summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
