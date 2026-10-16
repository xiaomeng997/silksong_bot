"""Task 1v1 SG5 parts 1 and 4: summary of the open-loop replays (C:/ssbot/data/m2_map/sg5/ident_chase.py: one line
per planner tick with the Clapper's family, the hero's distance, the L2 stance, the rows that slash in reach and the
check or key that rejected them; forum.md 61).

Per family (idle / walk split into "after an evade" (<= POST_EV_F frames since an evade ended) and the rest; evade;
jump slam; jump cast; cast; slam; other = the entry): ticks, the recorded distance (centre to centre, u), the L2
branch (goal_why) and stance distance, ticks with a slash row (the planner's own predicted landed hit, nh > 0), ticks
whose chosen row slashes, the reasons the best slash row lost (stage or ranking key), the chosen row's plan (end
distance, mean distance over its frames, presses, predicted landed hits; plan hits/s = nh / the horizon), FORCED_RISK
share, tick ms. With two tags (off / on) the same per family side by side, and the decision identity on the ticks
(the chosen row's command hash).

    ../scripts/uv.cmd run python -m ssbot.tools.sg5_replay --dir C:/ssbot/data/m2_map/sg5 --tags off[,on]
        [--out C:/ssbot/data/m2_map/sg5/replay.json]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np

POST_EV_F = 60              # idle / walk ticks this many frames after an evade ended: "after an evade"
HORIZON_S = 37 / 60.0       # the plan's frames (T 36 + the first) in s: plan hits/s = nh / this
FAMS = ("idle_walk", "post_evade", "evade", "jump_slam", "jump_cast", "other", "cast", "slam")


def load(d: Path, tag: str) -> dict[str, list[dict]]:
    out = {}
    for p in sorted(d.glob(f"id_{tag}_*.jsonl")):
        rows = [json.loads(x) for x in p.read_text("utf-8").splitlines() if x.strip()]
        if rows:
            out[p.stem[len(f"id_{tag}_"):]] = rows
    return out


def fam_of(r: dict) -> str:
    f = r.get("fam") or "other"
    if f == "idle_walk" and r.get("since_ev") is not None and 0 <= int(r["since_ev"]) <= POST_EV_F:
        return "post_evade"
    return f


def _q(v, p):
    return round(float(np.percentile(v, p)), 2) if len(v) else None


def family_stats(rows: list[dict]) -> dict:
    out = {}
    for fam in FAMS:
        X = [r for r in rows if fam_of(r) == fam]
        if not X:
            continue
        A = [r for r in X if "n_slash" in r]
        d = [abs(r["d"]) for r in X if "d" in r]
        why = Counter(str(r.get("why")).split("; ")[-1] for r in X)
        lost = Counter()
        for r in A:
            if r["n_slash"] > 0 and not (r.get("ch_nh") or 0) > 0:
                if "best_slash" in r:
                    lost.update(r["best_slash"]["why"].keys())
                else:
                    lost["no safe slash row: " + "+".join(sorted(r.get("st_slash", {})))] += 1
        nh = [float(r.get("ch_nh") or 0.0) for r in A]
        far = [r for r in A if "d" in r and abs(r["d"]) > 5.4 and r.get("ch_dend") is not None]
        out[fam] = {
            "ticks": len(X), "analysed": len(A),
            "d_p10_50_90": [_q(d, 10), _q(d, 50), _q(d, 90)],
            "in_reach_share": round(float(np.mean([3.5 <= x <= 5.4 for x in d])), 3) if d else None,
            "l2_branch": dict(why.most_common(8)),
            "stance_d_p50": _q([abs(r["stance_d"]) for r in X if "stance_d" in r], 50),
            "hw0_share": round(float(np.mean([(r.get("hw") or 0) == 0 for r in X])), 3),
            "slash_row_ticks": sum(r["n_slash"] > 0 for r in A),
            "safe_slash_ticks": sum("best_slash" in r or (r.get("ch_nh") or 0) > 0 for r in A),
            "chosen_slash_ticks": sum((r.get("ch_nh") or 0) > 0 for r in A),
            "reach_row_ticks": sum(r.get("n_reach", 0) > 0 for r in A),
            "chosen_reach_ticks": sum(bool(r.get("ch_reach")) for r in A),
            "lost": dict(lost.most_common(12)),
            "plan_end_d_p50": _q([abs(r["ch_dend"]) for r in A if r.get("ch_dend") is not None], 50),
            "plan_mean_d_p50": _q([r["ch_dmean"] for r in A if r.get("ch_dmean") is not None], 50),
            "plan_presses_mean": round(float(np.mean([r.get("ch_press", 0) for r in A])), 3) if A else None,
            "plan_hits_per_s": round(float(np.mean(nh)) / HORIZON_S, 3) if nh else None,
            "far_approach_p50": _q([abs(r["d"]) - abs(r["ch_dend"]) for r in far], 50),
            "far_ticks": len(far),
            "forced_share": round(float(np.mean([bool(r.get("forced")) for r in X])), 4),
            "ms_p50_p95": [_q([r["ms"] for r in X], 50), _q([r["ms"] for r in X], 95)],
        }
    return out


def examples(rows: list[dict], fam: str, n: int = 4) -> list[dict]:
    out = []
    for r in rows:
        if fam_of(r) != fam or "best_slash" not in r or (r.get("ch_nh") or 0) > 0:
            continue
        out.append({k: r.get(k) for k in ("f", "st", "d", "air", "why", "stance_d", "name", "ch_dend", "best_slash",
                                          "pen_ch")})
        if len(out) >= n:
            break
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=Path("C:/ssbot/data/m2_map/sg5"))
    ap.add_argument("--tags", default="off")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    tags = a.tags.split(",")
    res = {"tags": tags}
    data = {t: load(a.dir, t) for t in tags}
    for t in tags:
        rows = [r for eps in data[t].values() for r in eps]
        res[t] = {"episodes": len(data[t]), "ticks": len(rows), "families": family_stats(rows),
                  "forced_share": round(float(np.mean([bool(r.get("forced")) for r in rows])), 4) if rows else None,
                  "ms_p50_p95_p99": [_q([r["ms"] for r in rows], p) for p in (50, 95, 99)],
                  "plan_hits_per_s": round(float(np.mean([float(r.get("ch_nh") or 0) for r in rows
                                                          if "ch_nh" in r])) / HORIZON_S, 3) if rows else None,
                  "examples": {f: examples(rows, f) for f in ("idle_walk", "post_evade", "evade", "jump_cast")},
                  "errors": sum("err" in r for r in rows)}
    if len(tags) == 2:
        a0, b0 = data[tags[0]], data[tags[1]]
        same, tot, by_fam = 0, 0, Counter()
        for ep in sorted(set(a0) & set(b0)):
            for x, y in zip(a0[ep], b0[ep]):
                tot += 1
                if x.get("cmd") == y.get("cmd") and x.get("name") == y.get("name"):
                    same += 1
                else:
                    by_fam[fam_of(x)] += 1
        res["identity"] = {"same": same, "ticks": tot, "changed_by_family": dict(by_fam)}
    txt = json.dumps(res, indent=1)
    if a.out:
        a.out.write_text(txt, "utf-8")
    print(txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
