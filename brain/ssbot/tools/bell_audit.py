"""Bell attack audit: in recorded planner episodes, what the planner did with falling drop bells and attack bells it
could hit (M2, the person 2026-10-02: no bell pogo and no side slash on a falling drop bell was ever seen live).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.bell_audit C:/ssbot/data/runs/m2/<run> [--instance 0] [--episodes 6]
        [--only-quits] [--json out.json]

How: each episode's recording is replayed open loop through a fresh PlannerPolicy (oracle view; the planner is
deterministic given the STATEs, so its decisions match the live ones unless a live tick ran late), and per tick with a
registry target (pogo_targets: bells) on a predicted path it counts
  side_bell     ticks with candidates whose first side slash meets a bell (planner.side_bell_rows);
  redirect      ticks with candidates scored on the bell's one redirected path (planner.redirect_rows: a drop bell in
                Air / Bounce Air knocked away from the hitter), of them ticks with a safe one;
  saves         ticks where only redirect candidates are safe (FORCED_RISK without them);
  frees         ticks where a safe redirect candidate exists and the best plan without one has no comfort clearance;
  chosen        ticks whose chosen plan is a redirect candidate;
  bell pogo     ticks with an accepted bell pogo (pogo_log "bell") and ticks whose chosen plan bounces off a bell;
plus FORCED_RISK ticks while a drop bell falls, and the hero's hits by drop bells (hit_sources of the attempt row).
--only-quits replays only QUIT episodes (the acceptance: how many drop-bell QUITs a redirect would have made safe).
"""
import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

import numpy as np


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path)
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--episodes", type=int, default=6)
    ap.add_argument("--only-quits", action="store_true")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    from ssbot.knowledge.kinematics import Terrain2D
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.postmortem import episode_rows, find_recording
    from ssbot.train.encounters import BELL_BEAST
    from ssbot.train.planner_policy import PlannerPolicy
    rows = [r for r in episode_rows(a.run, a.instance) if r.get("recording") and r.get("outcome") != "HARNESS_FAIL"]
    if a.only_quits:
        rows = [r for r in rows if r.get("outcome") == "QUIT"]
    pol = PlannerPolicy(view="oracle", threads=a.threads)
    tot = Counter()
    per_ep = []

    class Tap:
        wake_frame = None

    for row in rows[:a.episodes]:
        r = RecordingReader(find_recording(a.run, row))
        for _, m in r.terrain():
            if m.get("scene_raw") == BELL_BEAST.scene:
                pol.terrain = Terrain2D.from_message(m, pol.params.scene(BELL_BEAST.scene))
        Tap.wake_frame = row.get("f_wake")
        pol.reset(random.Random(row["seed"]), BELL_BEAST)
        c = Counter()
        cases = []
        for s in r.states(row["f_end"] - row["acts"], row["f_end"]):
            pol.act(s, Tap)
            res = pol.planner_last
            if res is None or not pol.forecasts:
                continue
            pl = pol.planner
            fcast = pol.forecasts[-1][1]
            falling = [d for d in fcast.det if d[5] < len(d[0].bounces) or d[6] is None] if fcast.det else []
            if not falling and not pl.side_bell_rows and not pl.pogo_log.get("bell"):
                continue
            c["ticks_bells"] += 1
            c["ticks_drop_bell_exact"] += int(bool(fcast.det))
            c["forced_with_drop_bell"] += int(bool(fcast.det) and res.forced_risk)
            c["side_bell"] += int(pl.side_bell_rows > 0)
            rr = np.asarray(getattr(pl, "redirect_rows", []), np.int64)
            safe = pl.last_safe
            if len(rr):
                c["redirect"] += 1
                rs = safe[rr] if len(safe) > rr.max() else np.zeros(len(rr), bool)
                c["redirect_safe"] += int(rs.any())
                others = safe.copy()
                others[rr] = False
                if rs.any() and not others.any():
                    c["saves"] += 1
                    cases.append(int(s["f"]))
                if res.idx in set(rr.tolist()):
                    c["chosen"] += 1
            c["bell_pogo_accepted"] += int(pl.pogo_log.get("bell", 0) > 0)
            c["bell_pogo_chosen"] += int(pl.pogo_log.get("bell", 0) > 0 and res.idx >= 0
                                         and len(pl._pogo_ok) > res.idx and bool(pl._pogo_ok[res.idx]))
        hs = row.get("hit_sources") or {}
        c["hits_by_drop_bell"] = sum(v for k, v in hs.items() if "DropBell" in k)
        per_ep.append({"seed": row["seed"], "outcome": row["outcome"], "reason": row.get("reason"), **c,
                       "save_frames": cases[:10]})
        tot.update(c)
    out = {"episodes": len(per_ep), "total": dict(tot), "per_episode": per_ep}
    print(json.dumps(out, indent=1))
    if a.json:
        a.json.write_text(json.dumps(out, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
