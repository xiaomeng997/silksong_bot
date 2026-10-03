"""One kin_check window rolled out from the state estimated at its start, printed frame by frame beside the log: the
tool every Forum-loadout model fix of 2026-10-02/03 came from (docs/facts/1.0.30000/movement_kinematics.md section 5:
each failing window of the held-out runs read against the log until the rule behind it showed).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.kin_window <recording> <start frame> [--frames 30]
        [--params <json>] [--replay] [--state]

Columns: k, frame, button mask, physics steps in the frame, the logged box (x centre, bottom y), velocity, wall slide /
cling / jumping / ground / hero.wall flags, the classified mode and clip | the model's box, velocity and mode. With
--replay the rollout takes the logged frame times, physics steps and contact events (kin_check's replay_events); by
default the planner's own timing with the logged events (planner_events). --state prints the estimated start state.
"""
from __future__ import annotations

import argparse
import sys

import numpy as np

from ssbot.knowledge import kinematics as km


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recording")
    ap.add_argument("frame", type=int)
    ap.add_argument("--frames", type=int, default=30)
    ap.add_argument("--params", default=str(km.DEFAULT_PARAMS.parent / "hero_reaper_forum.json"))
    ap.add_argument("--replay", action="store_true")
    ap.add_argument("--state", action="store_true")
    a = ap.parse_args(argv)
    from ssbot.tools.kin_check import load_source
    p = km.HeroParams.load(a.params)
    tr, terrains = load_source(a.recording, p)
    hit = np.flatnonzero(tr.f == a.frame)
    if not len(hit):
        print(f"frame {a.frame} not in the recording")
        return 1
    i0, H = int(hit[0]), a.frames
    if i0 + H >= len(tr):
        H = len(tr) - 1 - i0
    terrain = terrains[tr.scenes[tr.scene[i0]]]
    modes = km.classify_modes(tr, forum=bool(p.abilities))
    ev = km.derive_events(tr, modes)
    S = km.estimate_state(tr, [i0], p, terrain=terrain)
    if a.state:
        print(km.describe_state(S, 0))
    I = np.arange(i0 + 1, i0 + H + 1)
    kw = {"dt": tr.dt[I][None], "fs": tr.fs[I][None], "udt": tr.udt[I][None]} if a.replay else {}
    r = km.rollout(S, tr.mask[I][None], p, terrain, events=ev[I][None], **kw)
    flag = {n: tr.flag(n) for n in ("wallSliding", "wallClinging", "jumping", "onGround")}
    clips = np.array(tr.clips, dtype=object)[tr.clip]
    for k in range(H + 1):
        i = i0 + k
        lb, mb = tr.box[i], r.box[0, k]
        w = tr.wall[i] if tr.wall is not None else "-"
        print(f"{k:2d} f{tr.f[i]} m{int(tr.mask[i]):8d} fs{tr.fs[i]} log x{0.5 * (lb[0] + lb[2]):7.3f} y{lb[1]:7.3f} "
              f"v({tr.vel[i, 0]:6.2f},{tr.vel[i, 1]:6.2f}) sl{int(flag['wallSliding'][i])} "
              f"cl{int(flag['wallClinging'][i])} j{int(flag['jumping'][i])} g{int(flag['onGround'][i])} w{w} "
              f"md{modes[i]:2d} {clips[i]:18s}| mod x{0.5 * (mb[0] + mb[2]):7.3f} y{mb[1]:7.3f} "
              f"v({r.vel[0, k, 0]:6.2f},{r.vel[0, k, 1]:6.2f}) md{r.mode[0, k]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
