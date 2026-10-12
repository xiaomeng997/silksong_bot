"""Per-tick cost of the Forum planner policy (ForumPlannerPolicy.act: the forecaster, v2's attack-range tracker and
support, the tactics, the planner, the supervisor) on recorded segments, open loop with the recording's keys and the
LIVE deadlines (deadline_ms 8, escape / clash deadline_ms + 2): what a 60 Hz tick costs. SSBOT_FORUM_V2 picks the arm
(forum.md §43). Run it at a quiet moment (the numbers are wall clock); the process lowers itself to Idle.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.forum_v2_bench --seg C:/ssbot/data/human/<session>:win:1
        [--seg ...] [--limit-s 0] [--threads 4] [--json out.json]

Reports per segment and pooled: act (the whole tick) p50 / p95 / p99 / max, the share over 16.7 ms, the planner part,
the v2 support build, by the number of enemies the attack-range tracker holds, and FORCED_RISK / S = 1 shares.
"""
import argparse
import json
import random
import time
from pathlib import Path

import numpy as np

from ssbot.tools.forum_human_score import _policy, clear_latches, load_segment, segments


def _q(v) -> dict | None:
    if not len(v):
        return None
    a = np.asarray(v, np.float64)
    return {"n": int(len(a)), "p50": round(float(np.percentile(a, 50)), 2), "p95": round(float(np.percentile(a, 95)), 2),
            "p99": round(float(np.percentile(a, 99)), 2), "max": round(float(a.max()), 2),
            "over_16_7": round(float((a > 16.7).mean()), 4)}


def bucket(n: int) -> str:
    return "0" if n == 0 else "1" if n == 1 else "2-3" if n <= 3 else "4-5" if n <= 5 else "6+"


def run(seg: dict, threads: int, limit_s: float) -> dict:
    from ssbot.train.encounters import ENCOUNTERS
    crest = seg["crest"] if seg["crest"] in ("Wanderer", "Reaper") else "Reaper"
    pol, _, _ = _policy(crest, threads, "off", ())
    terrain, states = load_segment(seg)
    if limit_s:
        states = states[:int(limit_s * 60)]
    pol.terrain_msg = terrain
    pol.reset(random.Random(0), ENCOUNTERS["Forum"])
    pl = pol.planner
    rows = []
    for i, s in enumerate(states):
        if i + 1 < len(states):
            pol.sent[int(states[i + 1]["f"])] = int(states[i + 1]["act"]["mask"])
        clear_latches(pl)
        n_plan = len(pol.plan_ms)
        t0 = time.perf_counter()
        pol.act(s, None)
        ms = (time.perf_counter() - t0) * 1e3
        if len(pol.plan_ms) == n_plan or i < 60:
            continue                         # no planner tick (no world state yet) / warm-up
        res = pol.planner_last
        fd = pol.v2feed
        rows.append({"act": ms, "plan": pol.plan_ms[-1], "v2": fd.ms[-1] if fd is not None and fd.ms else None,
                     "n": len(fd.trk.now) if fd is not None else len(getattr(pol.fc, "trackers", {}) or {}),
                     "forced": bool(res.forced_risk), "S": int(res.S), "move": _in_move(fd), "cast": _in_cast(fd)})
    return {"seg": {k: seg[k] for k in ("session", "attempt", "kind")}, "rows": rows,
            "fcfg": {"v2": pl.fcfg.v2, "deadline_ms": pl.fcfg.deadline_ms}}


def _in_move(fd) -> bool:
    """An enemy in a move the special-move table knows (combat.specials: the Clapper's slam) is tracked."""
    from ssbot.combat import specials
    if fd is None:
        return False
    for tk, e, _ in fd.trk.now.values():
        if specials.enemy_move({"type_key": e.get("type_key") or tk, "fsms": e.get("fsms")}) is not None:
            return True
    return False


def _in_cast(fd) -> bool:
    """A Clapper in its small-rune cast (CC_CAST), or its bombs on the field (task 1v1 G2)."""
    if fd is None:
        return False
    for tk, e, inst in fd.trk.now.values():
        if inst is not None and inst.fam == "CC_CAST":
            return True
    from ssbot.combat.rune_bombs import bomb_ents
    return bool(bomb_ents(fd.trk.ents))


def summarize(rows: list) -> dict:
    out = {"ticks": len(rows), "act_ms": _q([r["act"] for r in rows]), "plan_ms": _q([r["plan"] for r in rows]),
           "v2_ms": _q([r["v2"] for r in rows if r["v2"] is not None]),
           "forced": round(float(np.mean([r["forced"] for r in rows])), 4) if rows else None,
           "S1": round(float(np.mean([r["S"] for r in rows])), 4) if rows else None, "by_enemies": {},
           "in_move": {"act_ms": _q([r["act"] for r in rows if r.get("move")]),
                       "plan_ms": _q([r["plan"] for r in rows if r.get("move")])},
           "in_cast": {"act_ms": _q([r["act"] for r in rows if r.get("cast")]),
                       "plan_ms": _q([r["plan"] for r in rows if r.get("cast")])}}
    for b in ("0", "1", "2-3", "4-5", "6+"):
        rr = [r for r in rows if bucket(r["n"]) == b]
        if rr:
            out["by_enemies"][b] = {"act_ms": _q([r["act"] for r in rr]),
                                    "v2_ms": _q([r["v2"] for r in rr if r["v2"] is not None])}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seg", action="append", required=True)
    ap.add_argument("--demo-cache", default="C:/ssbot/data/m2_forum_w0f/demo_cache")
    ap.add_argument("--limit-s", type=float, default=0.0)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    try:
        import psutil
        psutil.Process().nice(psutil.IDLE_PRIORITY_CLASS)
    except Exception:  # noqa: BLE001
        pass
    segs = []
    for sp in a.seg:
        segs += segments(sp, Path(a.demo_cache) if a.demo_cache else None)
    res, allr = [], []
    for seg in segs:
        r = run(seg, a.threads, a.limit_s)
        allr += r["rows"]
        res.append({"seg": r["seg"], "fcfg": r["fcfg"], **summarize(r["rows"])})
        print(json.dumps(res[-1]), flush=True)
    out = {"segments": res, "pooled": summarize(allr)}
    print(json.dumps(out["pooled"], indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
