"""Replay a recorded Forum gauntlet through ForumPlannerPolicy open loop (forum_planner_plan R4: the framework check
before a live batch; it also compiles the numba caches of the checkout it runs in).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.forum_policy_replay --run C:/ssbot/data/runs/m2/<run> --instance 0
        --episode 0 [--frames 3000] [--wave-frames 0] --out C:/.../replay.json

The policy acts on every recorded STATE from the battle start (the hero's positions are the recording's, so plans are
not followed: FORCED_RISK and modes are open-loop figures). --frames: STATEs ticked through the planner; after them
(--wave-frames more, 0: to the episode's end) only the backend, the MultiForecaster and the WaveTracker check run.
Prints the policy's stats (tick times, the WaveTracker against room.battles, modes)."""
import argparse
import json
import random
import time
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--episode", type=int, default=0)
    ap.add_argument("--frames", type=int, default=3000)
    ap.add_argument("--wave-frames", type=int, default=0)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    from ssbot.record.recorder import RecordingReader
    from ssbot.train.encounters import ENCOUNTERS
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy
    rows = [json.loads(x) for x in (a.run / f"attempts_i{a.instance}.jsonl").read_text("utf-8").splitlines() if x]
    row = next(r for r in rows if r.get("episode") == a.episode)
    t0 = time.perf_counter()
    pol = ForumPlannerPolicy(threads=a.threads)
    t_load = time.perf_counter() - t0
    t_warm = pol.warmup()
    rd = RecordingReader(row["recording"])
    for _, m in rd.terrain():
        if (m.get("scene_raw") or m.get("scene")) in ("Hang_04", "Hang_04_boss"):
            pol.terrain_msg = m
    pol.reset(random.Random(0), ENCOUNTERS[row["unit"]])
    # open loop: the supervisor still decides (its tiers and triggers are counted) but never takes the keys, so the
    # planner ticks on every STATE (a data-policy recording starts at random HP: Q1 would pause at once)
    import dataclasses
    step0 = pol.sc.step

    def step(*args, **kw):
        r = step0(*args, **kw)
        pol.sc.pq = None
        return r._replace(mask=None, outcome=None) if hasattr(r, "_replace") else             dataclasses.replace(r, mask=None, outcome=None)
    pol.sc.step = step
    f0, f1 = row["f_wake"], row["f_end"]
    n = 0
    t_obs = []
    for s in rd.states(f0, f1):
        if n < a.frames:
            pol.act(s, None)
        else:
            if a.wave_frames and n >= a.frames + a.wave_frames:
                break
            tt = time.perf_counter()
            ws = pol.backend.feed(s)
            if ws is not None:
                pol.raw[s["f"]] = s
                s["_t"] = ws.stamp.t_game_s
                pol.fc.update(ws)
                pol._wave_check(s, ws.stamp.frame)
            pol.raw.pop(s["f"] - 12, None)
            t_obs.append(time.perf_counter() - tt)
        n += 1
    st = pol.stats()
    out = {"run": str(a.run), "instance": a.instance, "episode": a.episode, "outcome": row.get("outcome"),
           "states": n, "ticked": min(n, a.frames), "load_s": round(t_load, 1), "warm_s": round(t_warm, 1),
           **{k: st[k] for k in ("tick_ms_p50", "tick_ms_p99", "plan_ms_p50", "plan_ms_p99", "late_ticks", "modes",
                                 "forced_risk_ticks", "forced_streaks", "per_wave", "wave_check", "wave_bad",
                                 "wave_tracker", "audit", "targets", "binds", "cogfly", "unpredicted",
                                 "unpredicted_unknown", "unpredicted_sources", "follow_ups", "mh_ticks", "hits_taken",
                                 "hit_log")},
           "first_ticks_ms": [round(x, 1) for x in pol.tick_ms[:12]],
           "true_waves": (row.get("gauntlet") or {}).get("waves")}
    js = json.dumps(out, indent=1, default=str)
    if a.out:
        a.out.write_text(js, encoding="utf-8")
    print(js[:6000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
