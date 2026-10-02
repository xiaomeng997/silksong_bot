"""Safe-window map: how long a hero standing (or hanging) at a spot stays outside the forecast's support, over
recorded fights, and whether the forecast walk is cut short at long horizons (DESIGN 3.5.6, the Bind commit test's
T_min; M2 plan: is a Bind window there, and does the planner use it).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.safe_windows C:/ssbot/data/runs/m2/<run> [--instances 0,1]
        [--episodes 4] [--every 30] [--views oracle,degraded_dust] [--horizon 3.0] [--json out.json]

How: each episode's recording is replayed through the view's backend and forecaster (PlannerPolicy's, without the
planner); every --every-th frame, Forecast.t_min for the floor (x 70..100 every 1 u at the standing hurtbox centre) and
two air heights (y 6 and 9) up to --horizon (one occupied() query for all points), and the walk's truncation counter
(branches inside the horizon cut by MAX_NODES / the depth limit: a cut branch is support left out). Summary per view
and boss state at the frame: frames sampled, share of floor spots with T_min >= 1.52 s (Bind 1.37 s + delta_b 0.15),
>= 0.89 s (Injector Band) and >= 3 s, the share of frames with at least one such spot, and forecasts truncated. Also
the Binds the bot made (hero Bind clips) per boss state, beside the frames with a window.
"""
import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

FLOOR_Y = 3.0544          # the hurtbox centre of a standing hero in Bone_05
AIR_Y = (6.0, 9.0)
XS = np.arange(70.0, 100.01, 1.0)
LIMITS = (0.89, 1.52, 3.0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path)
    ap.add_argument("--instances", default="0")
    ap.add_argument("--episodes", type=int, default=4)
    ap.add_argument("--every", type=int, default=30)
    ap.add_argument("--views", default="oracle,degraded_dust")
    ap.add_argument("--horizon", type=float, default=3.0)
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    from ssbot.combat.forecast import BIN
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.postmortem import episode_rows, find_recording
    from ssbot.train.encounters import BELL_BEAST
    from ssbot.train.planner_policy import PlannerPolicy
    tk = np.arange(0, int(a.horizon / BIN) + 1) * BIN
    ys = np.concatenate([np.full(len(XS), FLOOR_Y)] + [np.full(len(XS), y) for y in AIR_Y])
    xs = np.tile(XS, 1 + len(AIR_Y))
    X = np.repeat(xs[:, None], len(tk), axis=1)
    Y = np.repeat(ys[:, None], len(tk), axis=1)
    out = {}
    for view in a.views.split(","):
        pol = PlannerPolicy(view=view, threads=1)
        agg = defaultdict(lambda: defaultdict(float))
        binds = defaultdict(int)
        for inst in (int(x) for x in a.instances.split(",")):
            for row in episode_rows(a.run, inst)[:a.episodes]:
                if not row.get("recording") or row.get("outcome") == "HARNESS_FAIL":
                    continue
                pol.reset(random.Random(row["seed"]), BELL_BEAST)
                prev_clip = ""

                class Tap:
                    wake_frame = row.get("f_wake")
                for i, s in enumerate(RecordingReader(find_recording(a.run, row)).states(row["f_end"] - row["acts"],
                                                                                          row["f_end"])):
                    ws = pol.backend.feed(s)
                    if ws is None:
                        continue
                    pol._wake(ws, s, Tap)
                    pol.fc.update(ws)
                    st = str(pol.fc.tracker.state)
                    clip = str(((s.get("hero") or {}).get("anim") or {}).get("clip", ""))
                    if clip.startswith("Bind") and not prev_clip.startswith("Bind"):
                        binds[st] += 1
                    prev_clip = clip
                    if i % a.every:
                        continue
                    f = pol.fc.forecast(a.horizon)
                    occ = f.occupied(X, Y, tk)
                    first = np.where(occ.any(axis=1), np.argmax(occ, axis=1) * BIN, np.inf)
                    fl = first[:len(XS)]
                    g = agg[st]
                    g["frames"] += 1
                    g["truncated"] += int(f.truncated > 0)
                    for lim in LIMITS:
                        g[f"floor_share_ge_{lim}"] += float((fl >= lim).mean())
                        g[f"frames_with_spot_ge_{lim}"] += float((fl >= lim).any())
                    g["air_share_ge_1.52"] += float((first[len(XS):] >= 1.52).mean())
        rows = {}
        for st, g in sorted(agg.items(), key=lambda kv: -kv[1]["frames"]):
            n = g["frames"]
            rows[st] = {"frames": int(n), "truncated": int(g["truncated"]), "binds": binds.get(st, 0),
                        **{k: round(v / n, 3) for k, v in g.items() if k not in ("frames", "truncated")}}
        out[view] = rows
    print(json.dumps(out, indent=1))
    if a.json:
        a.json.write_text(json.dumps(out, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
