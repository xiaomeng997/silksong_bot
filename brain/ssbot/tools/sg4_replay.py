"""Task 1v1 SG4 part 3: summary of the open-loop replays with the map on (C:/ssbot/data/m2_map/sg4/ident_map.py jsonl,
one line per planner tick with last_info["map"]; forum.md 59).

    ../scripts/uv.cmd run python -m ssbot.tools.sg4_replay <id_*.jsonl ...> [--trace f0-f1] [--out json]

Per slam (consecutive ticks of one Clapper's CL_SLAM with the map's state): ticks, with a map row, taken, safe, the
reasons for no row (off the macros, mode, deviation, wall, past the move), the rows not taken (stage-1 contact on the
special support, the envelope / aims, the keys not allowed, the escape check moved the pick), the full support's
cross-check, the map's first value and its planned presses; the tick cost on slam ticks and on all ticks; the
readiness penalty's ticks.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np


def load(paths: list[str]) -> list[dict]:
    out = []
    for p in paths:
        for i, x in enumerate(Path(p).read_text("utf-8").splitlines()):
            if x.strip():
                d = json.loads(x)
                d["_file"] = Path(p).stem
                out.append(d)
    return out


def slams(rows: list[dict]) -> list[list[dict]]:
    """Consecutive ticks of one Clapper's slam: the same file and Clapper, its move frame not going back (the anchor
    follows it through the antic, so x0 is no key)."""
    out, cur, key, kp = [], [], None, None
    for r in rows:
        m = r.get("map") or {}
        k_ = (r["_file"], m.get("iid")) if "k" in m else None
        new = k_ is None or k_ != key or (kp is not None and m.get("k", 0) < kp - 3)
        if new:
            if cur:
                out.append(cur)
            cur, key = ([r], k_) if k_ is not None else ([], None)
        else:
            cur.append(r)
        kp = m.get("k") if k_ is not None else None
    if cur:
        out.append(cur)
    return out


def q(v, p):
    return round(float(np.percentile(v, p)), 2) if len(v) else None


def summarize(rows: list[dict]) -> dict:
    sl = slams(rows)
    why, rej = Counter(), Counter()
    per = []
    for s in sl:
        on = [r for r in s if r["map"].get("on")]
        tk = [r for r in on if r["map"].get("taken")]
        sf = [r for r in on if r["map"].get("safe")]
        for r in s:
            if not r["map"].get("on"):
                why[str(r["map"].get("why"))] += 1
        for r in on:
            m = r["map"]
            if m.get("taken"):
                continue
            if not m.get("ok", True):
                rej["keys not allowed"] += 1
            elif m.get("s1"):
                rej["stage 1 (special support)"] += 1
            elif not m.get("safe"):
                rej["envelope / aims"] += 1
            elif m.get("first"):
                rej["escape / tail moved the pick"] += 1
            else:
                rej["safe, not first"] += 1
        f0 = on[0]["map"] if on else None
        per.append({"file": s[0]["_file"], "f0": s[0].get("f"), "k0": s[0]["map"].get("k"), "ticks": len(s),
                    "on": len(on), "taken": len(tk), "safe": len(sf),
                    "xcheck": sum(1 for r in on if r["map"].get("xcheck")),
                    "v_first": None if f0 is None else f0.get("v"),
                    "presses_first": None if f0 is None else len(f0.get("presses") or ()),
                    "exit": next((r["map"]["why"] for r in s if r["map"].get("why") in ("deviation", "wall")), None)})
    slam_ms = [r["ms"] for s in sl for r in s]
    all_ms = [r["ms"] for r in rows]
    row_ms = [r["map"]["total_ms"] for s in sl for r in s if r["map"].get("total_ms") is not None]
    rd = [r["map"]["ready"] for r in rows if (r.get("map") or {}).get("ready")]
    n_on = sum(p["on"] for p in per)
    return {"ticks": len(rows), "slams": len(sl), "slam_ticks": len(slam_ms),
            "row_ticks": n_on, "taken": sum(p["taken"] for p in per), "safe": sum(p["safe"] for p in per),
            "xcheck": sum(p["xcheck"] for p in per),
            "taken_share_of_rows": round(sum(p["taken"] for p in per) / max(n_on, 1), 3),
            "slams_with_a_row": sum(1 for p in per if p["on"]), "slams_with_a_taken_row": sum(1 for p in per if p["taken"]),
            "no_row_why": dict(why.most_common()), "not_taken_why": dict(rej.most_common()),
            "v_first_p50": q([p["v_first"] for p in per if p["v_first"] is not None and np.isfinite(p["v_first"])], 50),
            "presses_first_mean": round(float(np.mean([p["presses_first"] for p in per if p["presses_first"] is not None]
                                                      or [0])), 3),
            "ms_slam_p50_p95": [q(slam_ms, 50), q(slam_ms, 95)], "ms_all_p50_p95": [q(all_ms, 50), q(all_ms, 95)],
            "row_ms_p50_p95": [q(row_ms, 50), q(row_ms, 95)],
            "ready_ticks": len(rd), "ready_changed": sum(1 for r in rd if r.get("changed")),
            "ready_ms_p50_p95": [q([r["ms"] for r in rd], 50), q([r["ms"] for r in rd], 95)],
            "per_slam": per}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--trace", default="")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    rows = load(a.files)
    res = summarize(rows)
    if a.trace:
        f0, f1 = (int(v) for v in a.trace.split("-"))
        res["trace"] = [{"f": r.get("f"), "name": r["name"], "S": r["S"], "map": r.get("map")} for r in rows
                        if r.get("f") is not None and f0 <= r["f"] <= f1]
    if a.out:
        a.out.write_text(json.dumps(res, indent=1, default=float), "utf-8")
    print(json.dumps({k: v for k, v in res.items() if k not in ("per_slam", "trace")}, indent=1, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
