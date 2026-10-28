"""Replay unchanged observations through the real policy and ACTION sender.

This is an output-identity check, not a closed-loop combat test. Unlike the old
policy replay, it keeps the supervisor's masks and outcomes. Running this script
by filename with --code-root also permits the untouched frozen baseline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import threading
import time
from collections import deque
from pathlib import Path
from types import SimpleNamespace


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--code-root", type=Path, required=True)
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--episode", type=int, default=0)
    ap.add_argument("--ticks", type=int, default=800)
    ap.add_argument("--pattern", default="1,1,3", help="STATE frame strides between acted observations")
    ap.add_argument("--clock-step", type=float, default=0.00005,
                    help="deterministic seconds per perf_counter read; zero fixes the clock")
    ap.add_argument("--measure", action="store_true")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    sys.path.insert(0, str(a.code_root.resolve() / "brain"))
    # Apply the verified h2 arm before importing modules that resolve defaults.
    for key in list(os.environ):
        if key.startswith("SSBOT_FORUM_"):
            del os.environ[key]
    arm = dict(SSBOT_FORUM_V2="1", SSBOT_FORUM_V2_EVERY="1", SSBOT_FORUM_V2_CORNER="13",
               SSBOT_FORUM_RUNE_NOPRE="1", SSBOT_FORUM_RUNE_BOMB="1", SSBOT_FORUM_RUNE_HOP="1",
               SSBOT_FORUM_NOGLIDE="1", SSBOT_FORUM_RUNE_FACE="3", SSBOT_FORUM_SLAM_PLAY="1",
               SSBOT_FORUM_JUMP_BEHIND="1", SSBOT_FORUM_HERO2="1")
    os.environ.update(arm)
    from ssbot.ipc.oracle_link import OracleLink
    from ssbot.record.recorder import RecordingReader
    from ssbot.train.encounters import ENCOUNTERS
    from ssbot.train.episode import _act
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy
    controller_sources = {}
    for rel in ("ipc/oracle_link.py", "train/episode.py", "train/forum_planner_policy.py", "combat/forum_planner.py"):
        source = (a.code_root / "brain" / "ssbot" / rel).read_bytes()
        controller_sources[rel] = hashlib.sha256(source.replace(b"\r\n", b"\n")).hexdigest()
    attempt = next(json.loads(line) for line in (a.run / f"attempts_i{a.instance}.jsonl").read_text("utf-8").splitlines()
                   if line and json.loads(line).get("episode") == a.episode)
    enc = ENCOUNTERS[attempt["unit"]]
    reader = RecordingReader(attempt["recording"])
    policy = ForumPlannerPolicy(threads=4, crest="Wanderer", clash="main")
    for _, terrain in reader.terrain():
        if (terrain.get("scene_raw") or terrain.get("scene")) in ("Hang_04", "Hang_04_boss"):
            policy.terrain_msg = terrain
    print("warming policy", flush=True)
    policy.warmup()
    policy.reset(random.Random(attempt["seed"]), enc)
    policy._inbox_lock = threading.Lock()
    policy._inbox = deque(maxlen=4096)
    observed = None
    if a.measure:
        from ssbot.train.measurement import MeasurementTrace
        observed = MeasurementTrace()
        observed.start_episode(a.episode)
        policy.measurement = observed
        policy.planner.measurement_enabled = True

    class Socket:
        def __init__(self):
            self.messages = []
        def sendall(self, data):
            self.messages.append(data)

    link = OracleLink.__new__(OracleLink)
    link.sock, link._send_lock, link._seq = Socket(), threading.Lock(), 0
    if a.measure or hasattr(OracleLink, "measurement"):
        link.measurement = observed
    else:
        # The modified sender uses getattr, and the frozen sender ignores it.
        link.measurement = None
    tap = SimpleNamespace(wake_frame=attempt["f_wake"])
    pattern = [int(n) for n in a.pattern.split(",")]
    if not pattern or min(pattern) < 1:
        raise ValueError("pattern must contain positive strides")
    rows, next_f, reads = [], attempt["f_wake"], 0
    real_counter = time.perf_counter
    def counter():
        nonlocal reads
        reads += 1
        return reads * a.clock_step
    print("replaying", flush=True)
    time.perf_counter = counter
    try:
        for sequence, state in enumerate(reader.states(attempt["f_wake"], attempt["f_end"]), 1):
            policy._inbox.append(state)
            if observed is not None:
                observed.received(state["f"], sequence, observed.clock())
            if state["f"] < next_f:
                continue
            if observed is not None:
                observed.begin_tick(state)
            error = None
            try:
                _act(link, state["f"], policy, state, tap)
            except BaseException as exc:
                error = type(exc).__name__
                raise
            finally:
                if observed is not None:
                    observed.end_tick(error=error)
            res = policy.planner_last
            rows.append({"f": state["f"], "target_frame": state["f"] + 2,
                         "wire": link.sock.messages[-1].hex(),
                         "plan": [int(res.idx), res.name, int(res.S), bool(res.forced_risk)] if res is not None else None,
                         "goal": policy.tac.last.get("goal"), "target": policy.tac.last.get("target")})
            next_f = state["f"] + pattern[(len(rows) - 1) % len(pattern)]
            if len(rows) >= a.ticks or policy.episode_outcome is not None:
                break
    finally:
        time.perf_counter = real_counter
    result = {"code_root": str(a.code_root), "measure": a.measure, "arm": arm,
              "run": str(a.run), "instance": a.instance, "episode": a.episode,
              "clock_step": a.clock_step, "clock_reads": reads, "pattern": pattern,
              "interpretation": "open-loop output identity only", "ticks": len(rows), "rows": rows}
    result["controller_sources_sha256"] = controller_sources
    result["identity_sha256"] = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("x", encoding="utf-8") as first:
        json.dump(result, first, indent=1)
    if observed is not None:
        from ssbot.train.measurement import validate_trace
        from ssbot.train.forum_measure_manifest import configuration_manifest
        trace_path = a.out.with_suffix(".trace.jsonl")
        observed.write(trace_path)
        result["trace_check"] = validate_trace(trace_path)
        manifest = configuration_manifest(a.code_root / "brain" / "ssbot", policy)
        a.out.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True), "utf-8")
        result["configuration"] = {k: manifest[k] for k in ("configuration_complete", "unresolved",
                                                           "unknown_environment_switches", "behavior_sha256")}
    a.out.write_text(json.dumps(result, indent=1), "utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
