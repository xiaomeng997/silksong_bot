"""Replay a recorded Forum gauntlet through ForumPlannerPolicy open loop (forum_planner_plan R4: the framework check
before a live batch; it also compiles the numba caches of the checkout it runs in).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.forum_policy_replay --run C:/ssbot/data/runs/m2/<run> --instance 0
        --episode 0 [--skip 0] [--frames 3000] [--wave-frames 0] [--deadline-ms 8] [--ticks-out ticks.jsonl]
        --out C:/.../replay.json

The policy acts on every recorded STATE from the battle start (the hero's positions are the recording's, so plans are
not followed: FORCED_RISK and modes are open-loop figures). --frames: STATEs ticked through the planner; after them
(--wave-frames more, 0: to the episode's end) only the backend, the MultiForecaster and the WaveTracker check run.
--skip: STATEs from the battle start fed to the backend and the MultiForecaster only (no tick) before the --frames
(a later wave's situations with the forecast's history). --deadline-ms: ForumConfig.deadline_ms (inf: decisions that
do not depend on the machine's speed, for identity checks such as SSBOT_FORUM_L2=fail:1 against =0). --ticks-out: one
JSON line per tick (mode, L2 goal / target / stance, the plan's name, S, FORCED_RISK, mask, J).
Prints the policy's stats (tick times, the WaveTracker against room.battles, modes, the L2's).
--realtime (map v2 M4c's smoke): the ticked STATEs arrive at 60 per second of wall time and the policy acts on the
newest one (a slow tick skips frames, which reach it through the catch-up path as live: PlannerPolicy._catch_up) -
the background map2 search (SSBOT_FORUM_MAP2) then runs at real latency. --map2-log: map2's per-tick log (JSONL)."""
import argparse
import json
import os
import random
import time
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--episode", type=int, default=0)
    ap.add_argument("--skip", type=int, default=0)
    ap.add_argument("--frames", type=int, default=3000)
    ap.add_argument("--deadline-ms", type=float, default=None)
    ap.add_argument("--ticks-out", type=Path, default=None)
    ap.add_argument("--wave-frames", type=int, default=0)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--crest", default=None, help="the policy's crest (default: the recording's encounter: fo_W "
                                                  "Wanderer, else Reaper)")
    ap.add_argument("--clash", nargs="?", const="on", default="off", choices=("off", "on", "yellow", "cont", "main"),
                    help="the R8 EV_CLASH mode (forum_planner_policy.CLASH_MODES)")
    ap.add_argument("--realtime", action="store_true", help="M4c: STATEs at 60 per second, act on the newest")
    ap.add_argument("--map2-log", type=Path, default=None, help="M4c: map2's per-tick log (SSBOT_FORUM_MAP2=1)")
    a = ap.parse_args(argv)
    from ssbot.record.recorder import RecordingReader
    from ssbot.train.encounters import ENCOUNTERS
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy
    rows = [json.loads(x) for x in (a.run / f"attempts_i{a.instance}.jsonl").read_text("utf-8").splitlines() if x]
    row = next(r for r in rows if r.get("episode") == a.episode)
    t0 = time.perf_counter()
    crest = a.crest or ("Wanderer" if ENCOUNTERS[row["unit"]].savestate == "fo_W" else "Reaper")
    pol = ForumPlannerPolicy(threads=a.threads, crest=crest, clash=a.clash)
    if pol.m2 is not None:
        # M4c: an offline replay - her position is the recording's, not her keys' result (the hero tolerances are
        # logged, not enforced); the log beside the output
        pol.m2.cfg.replay = True
        pol.m2.log_path = a.map2_log
    t_load = time.perf_counter() - t0
    t_warm = pol.warmup()
    rd = RecordingReader(row["recording"])
    for _, m in rd.terrain():
        if (m.get("scene_raw") or m.get("scene")) in ("Hang_04", "Hang_04_boss"):
            pol.terrain_msg = m
    pol.reset(random.Random(0), ENCOUNTERS[row["unit"]])
    if a.deadline_ms is not None:
        pol.planner.fcfg.deadline_ms = a.deadline_ms
    tick_rows = []
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
    rt = None
    if a.realtime:
        import threading
        from collections import deque
        pol._inbox_lock = threading.Lock()
        pol._inbox = deque(maxlen=4096)
        rt = {"t0": None, "late": 0, "acted": 0, "q": []}
    for s in rd.states(f0, f1):
        if rt is not None and a.skip <= n < a.skip + a.frames:
            # M4c: the frames of the ticked range collected, then played at 60 per second (below)
            rt["q"].append(s)
            n += 1
            if n == a.skip + a.frames:
                _realtime(pol, rt, a, tick_rows)
            continue
        if rt is not None and rt["q"] and rt["t0"] is None:
            _realtime(pol, rt, a, tick_rows)
        if a.skip <= n < a.skip + a.frames:
            mask = pol.act(s, None)
            if a.ticks_out is not None and pol.planner_last is not None:
                res = pol.planner_last
                tick_rows.append({"f": s["f"], "mode": pol._mode_last, "goal": pol.tac.last.get("goal"),
                                  "tgt": pol.tac.last.get("target_type"), "plan": res.name, "S": res.S,
                                  "forced": bool(res.forced_risk), "mask": int(mask), "J": round(float(res.J), 6),
                                  "why": pol.tac.last.get("goal_why"), "cands": pol.tac.last.get("l2_cands"),
                                  "hero": (s.get("hero") or {}).get("pos")})
        else:
            if n >= a.skip + a.frames and a.wave_frames and n >= a.skip + a.frames + a.wave_frames:
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
    if rt is not None and rt["q"] and rt["t0"] is None:
        _realtime(pol, rt, a, tick_rows)
    st = pol.stats()
    if pol.m2 is not None:
        pol.m2.stop()
    out = {"run": str(a.run), "instance": a.instance, "episode": a.episode, "outcome": row.get("outcome"),
           "states": n, "skip": a.skip, "ticked": max(0, min(n - a.skip, a.frames)), "load_s": round(t_load, 1),
           "warm_s": round(t_warm, 1), "l2": st.get("l2"), "l2_env": os.environ.get("SSBOT_FORUM_L2"),
           **{k: st[k] for k in ("tick_ms_p50", "tick_ms_p99", "plan_ms_p50", "plan_ms_p99", "tv_ms_p50", "tv_ms_p99",
                                 "terminal", "late_ticks", "modes",
                                 "forced_risk_ticks", "forced_streaks", "per_wave", "wave_check", "wave_bad",
                                 "wave_tracker", "audit", "targets", "binds", "cogfly", "unpredicted",
                                 "unpredicted_unknown", "unpredicted_sources", "follow_ups", "mh_ticks", "hits_taken",
                                 "hit_log")},
           "crest": crest, "clash": a.clash, "crest_seen": pol.crest_seen,
           "first_ticks_ms": [round(x, 1) for x in pol.tick_ms[:12]],
           "true_waves": (row.get("gauntlet") or {}).get("waves"),
           # SP10b: the slam playbook's counts and runs (the hand-off / tight / air chain logs)
           **{k: st[k] for k in ("slam_play", "slam_runs", "slam_holds") if k in st},
           # SP11a: TwoPlay's stats (the escape runs, RUNETIER's rune_tier) when it ran
           **({"two_play": st["two_play"]} if "two_play" in st else {}),
           # SP-AIR1: the air show's stats when it ran
           **({"air_show": st["air_show"]} if "air_show" in st else {}),
           # M4c: map2's stats and the real-time pacing when they ran
           **({"map2": st["map2"]} if "map2" in st else {}),
           **({"realtime": {k: v for k, v in rt.items() if k != "q"}} if rt is not None else {})}
    if a.ticks_out is not None:
        a.ticks_out.write_text("".join(json.dumps(r) + "\n" for r in tick_rows), encoding="utf-8")
    js = json.dumps(out, indent=1, default=str)
    if a.out:
        a.out.write_text(js, encoding="utf-8")
    print(js[:6000])
    return 0


def _tick_row(pol, s: dict, mask: int) -> dict | None:
    if pol.planner_last is None:
        return None
    res = pol.planner_last
    r = {"f": s["f"], "mode": pol._mode_last, "goal": pol.tac.last.get("goal"),
         "tgt": pol.tac.last.get("target_type"), "plan": res.name, "S": res.S,
         "forced": bool(res.forced_risk), "mask": int(mask), "J": round(float(res.J), 6),
         "why": pol.tac.last.get("goal_why"), "cands": pol.tac.last.get("l2_cands"),
         "hero": (s.get("hero") or {}).get("pos")}
    if pol.m2 is not None and getattr(pol, "_m2_final", None) is not None:
        r["own"] = pol._m2_final[0]
    return r


def _realtime(pol, rt: dict, a, tick_rows: list) -> None:
    """M4c: the collected STATEs at 60 per second of wall time; each tick acts on the newest arrived one, the frames
    a slow tick skipped reach the policy through its inbox (the catch-up path, as live)."""
    q = rt["q"]
    rt["t0"] = time.perf_counter()
    j = 0          # the next frame not acted on
    put = 0        # frames put in the inbox
    while j < len(q):
        due = int((time.perf_counter() - rt["t0"]) * 60.0)
        if due < j:
            time.sleep(max(0.0, (j - due) / 60.0 - 0.0005))
            continue
        newest = min(due, len(q) - 1)
        with pol._inbox_lock:
            while put <= newest:
                pol._inbox.append(q[put])
                put += 1
        rt["late"] += newest - j
        s = q[newest]
        mask = pol.act(s, None)
        rt["acted"] += 1
        if a.ticks_out is not None:
            r = _tick_row(pol, s, mask)
            if r is not None:
                tick_rows.append(r)
        j = newest + 1
    rt["wall_s"] = round(time.perf_counter() - rt["t0"], 2)
    rt["frames"] = len(q)
    rt["q"] = []


if __name__ == "__main__":
    raise SystemExit(main())
