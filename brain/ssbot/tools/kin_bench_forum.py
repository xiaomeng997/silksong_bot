"""Rollout cost with the Forum loadout (DESIGN §3.5.4: <= 512 candidates x 48 frames, p99 <= 3 ms per planner tick):
512 random button sequences of 48 frames from a start next to a tall wall (run, jump, hold towards the wall, wall
jumps, glides, dashes, attacks incl. the Reaper down slash), nominal and "bounds" lanes, threads 4, against the same
masks with the Hunter parameters (whose rules skip the new branches).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.kin_bench_forum [--reps 300] [--threads 4] [--terrain <recording>]
"""
from __future__ import annotations

import argparse
import sys
import time

import numpy as np


def masks(rng: np.random.Generator, n: int, T: int, d: int) -> np.ndarray:
    from ssbot.knowledge import kinematics as km
    md = km.B_RIGHT if d > 0 else km.B_LEFT
    mo = km.B_LEFT if d > 0 else km.B_RIGHT
    pool = np.array([0, md, mo, km.B_JUMP | md, km.B_JUMP, km.B_JUMP | mo, km.B_ATTACK, km.B_ATTACK | km.B_DOWN,
                     km.B_ATTACK | km.B_UP, km.B_DASH | md, km.B_DASH, km.B_ATTACK | md], dtype=np.int64)
    out = np.zeros((n, T), dtype=np.int64)
    for i in range(n):
        t = 0
        while t < T:
            k = rng.integers(2, 16)
            out[i, t:t + k] = pool[rng.integers(len(pool))]
            t += k
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reps", type=int, default=300)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--n", type=int, default=512)
    ap.add_argument("--T", type=int, default=48)
    ap.add_argument("--lanes", default="nominal,bounds", help="comma-separated lane sets (kinematics.VARIANT_SETS)")
    a = ap.parse_args(argv)
    from ssbot.knowledge import kinematics as km
    from ssbot.probes.kin_excite_forum import forum_params
    fp = forum_params()
    hp = km.HeroParams.load()
    # a room: floor y 0 over x 0..40, a 20 u wall at x 0..2 (face x 2), a ceiling at y 25
    terr = km.Terrain2D.from_boxes([(-5, -5, 45, 0), (-5, 0, 2, 20), (-5, 25, 45, 30), (40, 0, 45, 25)])
    rng = np.random.default_rng(98000)
    out = {}
    for name, p in (("forum", fp), ("hunter", hp)):
        for lanes in [x.strip() for x in a.lanes.split(",") if x.strip()]:
            ts = []
            for r in range(a.reps + 5):
                x = 2.265 + rng.uniform(0, 8)
                y = rng.choice([0.015 + p.foot, rng.uniform(3, 15)])
                S = km.initial_state(p, x, y, facing=-1, ground=y < 2, vy=0.0 if y < 2 else rng.uniform(-10, 10))
                if y >= 2 and rng.random() < 0.5 and p.abilities:   # some starts in a wall slide
                    S[km.WSIDE] = S[km.WTOUCH] = -1.0
                    S[km.PX] = S[km.QX] = S[km.SX] = 2.265
                m = masks(rng, a.n, a.T, -1)
                t0 = time.perf_counter()
                km.rollout(S, m, p, terr, variants=None if lanes == "nominal" else lanes, threads=a.threads)
                dt = (time.perf_counter() - t0) * 1e3
                if r >= 5:
                    ts.append(dt)
            ts = np.array(ts)
            out[(name, lanes)] = ts
            print(f"{name:7s} {lanes:8s} {a.n} x {a.T}: p50 {np.percentile(ts, 50):.2f} ms  p99 "
                  f"{np.percentile(ts, 99):.2f} ms  max {ts.max():.2f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
