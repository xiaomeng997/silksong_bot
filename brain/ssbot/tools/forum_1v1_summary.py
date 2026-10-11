"""Clapper 1v1 live summary (task 1v1, forum.md 44): per arm over `forum_remaining_hits collect` episode files.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.forum_remaining_hits collect --manifest s2=C:/ssbot/sandbox/1v1_manifest.txt
        --out <dir>
    ../scripts/uv.cmd run python -m ssbot.tools.forum_1v1_summary <dir> [--json out.json] [--hits]

Per arm: episodes (HARNESS_FAIL left out), outcomes, kills, hitless kills (the Clapper killed - the wave-8 start ends
the episode, Forum_W_w7's end_wave - with no hit taken), hitless episodes, hits per episode, hits per minute, landed
hero hits per second (the hero's own `hit` events with damage, over the episode's in-game time; p50 over episodes and
the ratio of sums), the kill time (in-game seconds from the wave's activation to the wave-8 start, kills only), the
FORCED_RISK and late-tick shares. --hits lists every hit taken: the source collider, the Clapper's control state and
attack family at the contact, the hero (air / attacking / recoil / dash), the planner at the attack's start and the
last tick before the contact (tier, mode, FORCED_RISK, n_safe) and the last tick with a safe row.
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


def load(out: Path) -> dict[str, list[dict]]:
    by = defaultdict(list)
    for p in sorted((out / "eps").glob("*.json")):
        d = json.loads(p.read_text("utf-8"))
        e = {**d["episode"], "hits": d.get("hits") or [], "n_hits": d["episode"].get("hits")}
        if e.get("outcome") == "HARNESS_FAIL":
            continue
        by[f"{e.get('round')}:{e.get('arm')}"].append(e)
    return by


def _killed(e: dict) -> bool:
    return int(e.get("wave") or 0) >= 8 or str(e.get("outcome")) == "CLEAR"


def _pct(xs, q):
    return round(float(np.percentile(xs, q)), 3) if len(xs) else None


def arm_summary(eps: list[dict]) -> dict:
    n = len(eps)
    kills = [e for e in eps if _killed(e)]
    kt = [float((e.get("per_wave") or {}).get("7", {}).get("t") or e["t"]) for e in kills]
    lps = [e["landed"] / e["t"] for e in eps if e["t"] > 0]
    t_sum = sum(e["t"] for e in eps)
    ticks = sum(e.get("ticks") or 0 for e in eps)
    return {
        "episodes": n, "outcomes": dict(Counter(e["outcome"] for e in eps)), "kills": len(kills),
        "hitless_kills": sum(1 for e in kills if e["n_hits"] == 0),
        "hitless_kill_pct": round(100.0 * sum(1 for e in kills if e["n_hits"] == 0) / n, 1) if n else None,
        "hitless_eps": sum(1 for e in eps if e["n_hits"] == 0),
        "hits": sum(e["n_hits"] for e in eps), "masks": sum(e["masks"] for e in eps),
        "hits_per_ep": round(sum(e["n_hits"] for e in eps) / n, 3) if n else None,
        "hits_per_min": round(60.0 * sum(e["n_hits"] for e in eps) / t_sum, 3) if t_sum else None,
        "landed_per_s_p50": _pct(lps, 50), "landed_per_s_pooled": round(sum(e["landed"] for e in eps) / t_sum, 3)
        if t_sum else None,
        "kill_s_p50": _pct(kt, 50), "kill_s_p10": _pct(kt, 10), "kill_s_p90": _pct(kt, 90),
        "t_p50": _pct([e["t"] for e in eps], 50),
        "forced_share": round(sum(e.get("forced") or 0 for e in eps) / ticks, 4) if ticks else None,
        "late_share": round(sum(e.get("late") or 0 for e in eps) / ticks, 4) if ticks else None,
        "hit_states": dict(Counter(f"{h.get('family')}|{h.get('state')}" for e in eps for h in e.get("hits") or ())
                           .most_common()),
    }


def _dec(d):
    if not d:
        return None
    return {k: d.get(k) for k in ("df", "tier", "mode", "forced", "n_safe", "S", "goal", "esc") if k in d}


def hit_rows(eps: list[dict]) -> list[dict]:
    rows = []
    for e in eps:
        for h in e.get("hits") or ():
            rows.append({"run": e["run"], "ep": e["ep"], "t": h.get("t"), "src": h.get("collider") or h.get("path"),
                         "state": h.get("state"), "family": h.get("family"), "f_a": h.get("f_a"),
                         "hero_c": h.get("hero_c"), "dec_a": _dec(h.get("dec_a")), "dec_c": _dec(h.get("dec_c")),
                         "last_safe_f": h.get("last_safe_f"), "win_safe": h.get("win_safe"),
                         "win_forced": h.get("win_forced"), "win_esc_fail": h.get("win_esc_fail"),
                         "dist": h.get("dist"), "body": h.get("body"), "walked_in": h.get("walked_in")})
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--hits", action="store_true")
    ap.add_argument("--arms", default=None)
    a = ap.parse_args(argv)
    by = load(a.out)
    keep = set(a.arms.split(",")) if a.arms else None
    res = {}
    for arm in sorted(by):
        if keep is not None and arm not in keep:
            continue
        res[arm] = arm_summary(by[arm])
        if a.hits:
            res[arm]["hit_rows"] = hit_rows(by[arm])
    print(json.dumps(res, indent=1, default=str))
    if a.json:
        a.json.write_text(json.dumps(res, indent=1, default=str), "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
