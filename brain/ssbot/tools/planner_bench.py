"""Planner tick latency on logged fights (M2 W4 stage A; DESIGN §3.5.4 budget p99 <= 3 ms per tick): replay a recording
through OracleBackend, StateTracker, the forecaster, the tactics and the planner (open loop: the logged actions drive
the game, the planner only plans) and time every tick.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.planner_bench C:/ssbot/data/runs/m2/<run>/rec/<date>/TRAIN/i2_002
        [--frames 20000] [--start F] [--threads 4] [--view oracle|ve] [--json out.json]

Reports p50 / p99 / max of the whole tick (forecast + tactics + planner) and of each planner phase, the share of
ticks with FORCED_RISK and the modes. The first 50 ticks (numba compilation, caches) are left out.
"""
import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recording", type=Path)
    ap.add_argument("--frames", type=int, default=20000)
    ap.add_argument("--start", type=int, default=None)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--view", default="oracle")
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)

    import numba

    from ssbot.backends.observability import ObservabilityFilter
    from ssbot.backends.oracle_backend import OracleBackend
    from ssbot.combat.boss_model import BossModel
    from ssbot.combat.forecast import Forecaster
    from ssbot.combat.planner import Planner, PlannerConfig
    from ssbot.combat.safety_filter import FilterContext
    from ssbot.combat.tactics import Tactics, load_playbook
    from ssbot.core.bosses import BELL_BEAST
    from ssbot.core.worldstate import ORACLE, VISION_EQUIVALENT
    from ssbot.knowledge.kinematics import HeroParams, HoldState, StateTracker, Terrain2D
    from ssbot.record.recorder import RecordingReader

    numba.set_num_threads(a.threads)
    r = RecordingReader(a.recording)
    params = HeroParams.load()
    terrain = None
    for _, m in r.terrain():
        if m.get("scene_raw") == "Bone_05" or m.get("scene") == "Bone_05":
            terrain = Terrain2D.from_message(m, params.scene("Bone_05"))
    terrain = terrain or Terrain2D.empty()
    model = BossModel.load()
    view = ORACLE if a.view == "oracle" else VISION_EQUIVALENT
    fc = Forecaster(model, view, margin=(0.15, 0.25))
    pb = load_playbook()
    tac = Tactics(pb)
    planner = Planner(params, terrain, PlannerConfig(threads=a.threads))
    backend = OracleBackend(bosses=[BELL_BEAST])
    filt = ObservabilityFilter(bosses=[BELL_BEAST]) if view != ORACLE else None
    trk = StateTracker(params, terrain)
    f0 = a.start if a.start is not None else r.index("state")[0].get("f0", 0)
    totals, phases, modes, forced, names = [], {}, Counter(), 0, Counter()
    n = 0
    prev = None
    for s in r.states(f0, f0 + a.frames + 1):
        if prev is None:
            prev = s
            continue
        ws = backend.feed(prev)
        if filt is not None:
            ws = filt.apply(ws)
        trk.push(prev)
        if ws.game.scene.v != "Bone_05" or not prev.get("hero"):
            prev = s
            continue
        t0 = time.perf_counter()
        fc.update(ws)
        f = fc.forecast(2.0)
        prefs = tac.decide(ws, f, None, 3)
        ctx = FilterContext.from_world(ws, None, 3, want_bind=prefs.want_bind)
        hold = HoldState.from_act(prev.get("act"))
        prefix = np.array([int((s.get("act") or {}).get("mask") or 0)])
        res = planner.tick(ws, trk.state(), hold, prefix, f, prefs, ctx)
        dt = (time.perf_counter() - t0) * 1e3
        n += 1
        if n > 50:
            totals.append(dt)
            for k, v in res.t_ms.items():
                phases.setdefault(k, []).append(v)
            modes[prefs.mode] += 1
            forced += res.forced_risk
            names[res.name.split("+")[0]] += 1
        prev = s
    q = lambda v: {"p50": round(float(np.percentile(v, 50)), 3), "p99": round(float(np.percentile(v, 99)), 3),  # noqa
                   "max": round(float(np.max(v)), 3)} if v else {}
    out = {"ticks": len(totals), "tick_ms": q(totals), "phases_ms": {k: q(v) for k, v in phases.items()},
           "forced_risk_share": round(forced / max(1, len(totals)), 4), "modes": dict(modes),
           "first_primitives": dict(names.most_common(12)), "threads": a.threads, "view": a.view}
    print(json.dumps(out, indent=1))
    if a.json:
        a.json.write_text(json.dumps(out, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
