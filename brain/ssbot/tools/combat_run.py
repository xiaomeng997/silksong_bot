"""Run combat episodes on training instances and summarise them (M2 W0 / W2 / W7).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.launcher -n 4 --detach
    ../scripts/uv.cmd run python -m ssbot.tools.combat_run run --instances 0,1,2,3 --encounter BellBeast --mode data
        --episodes 50 [--hours 2] [--no-record] [--seed 0]
    ../scripts/uv.cmd run python -m ssbot.tools.combat_run summary C:/ssbot/data/runs/m2/<run>

run: one worker process per instance (each has its own link and recorder; the STATE stream is too heavy for one
Python process to decode for four instances). Each worker: load sandbox slot 1 from the title if needed (DebugMod
needs the gameplay HUD before a savestate load), turn save suppression on (encounter savestates carry progress the
sandbox slot must never get), then loops episodes (ssbot.train.episode.run_episode) until --episodes or --hours.
Writes <run>/attempts_i<N>.jsonl (one AttemptRecord per line) and, unless --no-record, the STATE recording
<run>/rec/<date>/TRAIN/i<N>_<k>/ rotated every --rotate episodes (each record has its f_reset / f_end frames).

Modes: "data" (behaviour logging: a lethal hit is counted, play goes on, random HP / silk / position at the wake),
"eval" (a lethal hit ends the episode as WOULD_DIE; HP and silk as the route has them).
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

RUNS = Path(r"C:\ssbot\data\runs\m2")


def git_rev() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              cwd=Path(__file__).resolve().parents[2], timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def make_policy(name: str, view: str = "oracle", run_dir: Path | None = None, instance: int = 0,
                threads: int = 8):
    if name == "data":
        from ssbot.train.data_policy import DataPolicy
        return DataPolicy()
    if name == "planner":
        from ssbot.train.planner_policy import PlannerPolicy
        return PlannerPolicy(view=view, threads=threads, log_dir=run_dir, instance=instance)
    raise SystemExit(f"unknown policy {name}")


def mode_config(mode: str, seed: int):
    from ssbot.train.episode import EpisodeConfig
    if mode == "data":
        return EpisodeConfig(mode="data", seed=seed, hp=(1, 5), silk=(0, 9), dx=(-6.0, 2.0), facing="random",
                             wait_frames=(0, 30))
    if mode == "eval":
        return EpisodeConfig(mode="eval", seed=seed, hp=None, silk=None, dx=(-3.0, 1.0), facing="random",
                             wait_frames=(0, 30))
    raise SystemExit(f"unknown mode {mode}")


def worker(a: argparse.Namespace) -> int:
    from ssbot.ipc.oracle_link import OracleLink
    from ssbot.probes.common import load_slot, stand_up
    from ssbot.record.recorder import Recorder
    from ssbot.train.encounters import ENCOUNTERS
    from ssbot.train.episode import AttemptRecord, FightTap, run_episode

    enc = ENCOUNTERS[a.encounter]
    run_dir = Path(a.run_dir)
    out = (run_dir / f"attempts_i{a.instance}.jsonl").open("a", encoding="utf-8", newline="\n")
    link = OracleLink(instance=a.instance, connect_timeout_s=120)
    tap = FightTap(link, enc)
    policy = make_policy(a.policy, a.view, run_dir, a.instance, a.threads)
    if hasattr(policy, "attach"):
        policy.attach(link)
    if hasattr(policy, "warmup"):
        print(f"[i{a.instance}] policy warm-up {policy.warmup():.1f} s", flush=True)
    rev = git_rev()
    fp = hashlib.sha256(json.dumps([enc.name, a.policy, a.mode, a.view, rev], sort_keys=True).encode()).hexdigest()[:12]
    from ssbot.train.episode import unpause
    deadline = time.monotonic() + 30     # a previous run may have left it paused (a QUIT, or the oracle's
    while time.monotonic() < deadline:   # brain-lost watchdog, which pauses a moment after the last ACTION)
        s0 = link.wait_state(lambda s: s.get("game") is not None, timeout_s=120)
        if not ((s0.get("game") or {}).get("paused") and (s0.get("game") or {}).get("scene")):
            break
        unpause(link)
        time.sleep(0.6)
    load_slot(link, 1)
    stand_up(link)
    if not link.rpc("guards.set", save_suppression=True)["save_suppression"]:
        raise SystemExit("save suppression could not be turned on")
    rec_obj = None
    deadline = time.monotonic() + a.hours * 3600 if a.hours else None
    counts: Counter = Counter()
    k = 0
    fails_in_row = 0
    try:
        while k < a.episodes and (deadline is None or time.monotonic() < deadline):
            if not a.no_record and k % a.rotate == 0:
                if rec_obj is not None:
                    rec_obj.close()
                rec_obj = Recorder(link, out_dir=run_dir / "rec", profile="TRAIN",
                                   episode=f"i{a.instance}_{k // a.rotate:03d}",
                                   config={"encounter": enc.name, "mode": a.mode, "policy": a.policy,
                                           "view": a.view}).start()
            seed = a.seed + a.instance * 1_000_000 + k
            rec = AttemptRecord(unit=enc.name, stage="TRAIN", profile="TRAIN" if a.view == "oracle" else "SIM_FINAL",
                                build="1.0.30000", code_rev=rev,
                                config_fp=fp, start_kind="savestate", mode=a.mode, seed=seed)
            run_episode(link, enc, tap, policy, mode_config(a.mode, seed), rec)
            d = asdict(rec)
            d["instance"] = a.instance
            d["episode"] = k
            d["recording"] = str(rec_obj.path) if rec_obj else None
            d["t"] = datetime.now().isoformat(timespec="seconds")
            out.write(json.dumps(d) + "\n")
            out.flush()
            counts[rec.outcome] += 1
            atk = {s: n for s, n in rec.attacks.items() if s in ("Charge Antic", "Leap Out", "Burst Antic", "Rage Antic")}
            print(f"[i{a.instance} ep{k}] {rec.outcome:12s} {rec.ingame_s or 0:6.1f}s hits {rec.hits} wd {rec.would_die} "
                  f"boss_hp {rec.boss_hp_end} {atk} {rec.reason or ''}", flush=True)
            k += 1
            fails_in_row = fails_in_row + 1 if rec.outcome == "HARNESS_FAIL" else 0
            if fails_in_row >= 5:
                print(f"[i{a.instance}] 5 harness failures in a row, stopping", flush=True)
                break
            if link.closed:
                break
    finally:
        if rec_obj is not None:
            rec_obj.close()
        out.close()
        link.close()
    print(f"[i{a.instance}] done: {dict(counts)}", flush=True)
    return 0


def run(a: argparse.Namespace) -> int:
    tag = a.mode if a.policy == "data" else f"{a.mode}_{a.policy}_{a.view}"
    run_dir = RUNS / f"{datetime.now():%Y%m%d_%H%M%S}_{a.encounter}_{tag}"
    run_dir.mkdir(parents=True)
    (run_dir / "config.json").write_text(json.dumps(vars(a), indent=1), encoding="utf-8")
    procs = []
    for i in [int(x) for x in a.instances.split(",")]:
        cmd = [sys.executable, "-m", "ssbot.tools.combat_run", "_worker", "--instance", str(i), "--run-dir",
               str(run_dir), "--encounter", a.encounter, "--mode", a.mode, "--policy", a.policy, "--episodes",
               str(a.episodes), "--hours", str(a.hours or 0), "--rotate", str(a.rotate), "--seed", str(a.seed),
               "--view", a.view, "--threads", str(a.threads)]
        if a.no_record:
            cmd.append("--no-record")
        log = (run_dir / f"worker_i{i}.log").open("w", encoding="utf-8")
        procs.append((i, subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env={**os.environ, "PYTHONUNBUFFERED": "1"}), log))
        print(f"worker i{i}: pid {procs[-1][1].pid}", flush=True)
    print(f"run dir: {run_dir}", flush=True)
    rc = 0
    for i, p, log in procs:
        rc |= p.wait()
        log.close()
    summary(run_dir)
    return rc


def load_attempts(run_dir: Path) -> list[dict]:
    rows = []
    for p in sorted(run_dir.glob("attempts_i*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def summary(run_dir: Path, more: list[Path] | None = None, write: bool = True) -> dict:
    """Outcome counts and the planner's numbers of one run (written to <run>/summary.json), or of several pooled
    (`summary RUN [RUN ...]`, printed only)."""
    rows = load_attempts(run_dir) + [r for d in more or () for r in load_attempts(d)]
    out: dict = {"episodes": len(rows), "outcomes": dict(Counter(r["outcome"] for r in rows))}
    if rows:
        attacks: Counter = Counter()
        for r in rows:
            attacks.update(r.get("attacks") or {})
        out["control_state_entries"] = dict(attacks.most_common())
        ing = sorted(r["ingame_s"] for r in rows if r.get("ingame_s") is not None)
        out["ingame_s_p50"] = ing[len(ing) // 2] if ing else None
        out["wall_s_mean"] = round(sum(r["wall_s"] or 0 for r in rows) / len(rows), 1)
        out["reset_ms_max"] = max((r.get("reset_ms") or 0) for r in rows)
        out["hits_mean"] = round(sum(r["hits"] for r in rows) / len(rows), 2)
        out["would_die_episodes"] = sum(1 for r in rows if r["would_die"])
        out["late_states_mean"] = round(sum(r.get("late_states", 0) for r in rows) / len(rows), 1)
        out["reasons"] = dict(Counter(r["reason"] for r in rows if r.get("reason")).most_common(10))
        n = len(rows)
        out["clear_pct"] = round(100.0 * sum(r["outcome"] == "CLEAR" for r in rows) / n, 1)
        clear = sorted(r["ingame_s"] for r in rows if r["outcome"] == "CLEAR" and r.get("ingame_s") is not None)
        out["time_to_kill_s"] = {"p50": clear[len(clear) // 2], "min": clear[0], "max": clear[-1]} if clear else None
        out["hits_per_episode"] = dict(sorted(Counter(r["hits"] for r in rows).items()))
        pol = [r.get("policy") or {} for r in rows]
        if any(p.get("view") for p in pol):
            out["unpredicted_hits"] = sum(len(p.get("unpredicted") or ()) for p in pol)
            out["episodes_with_forced_risk"] = sum(1 for p in pol if p.get("forced_risk_ticks"))
            out["forced_risk_ticks"] = sum(p.get("forced_risk_ticks") or 0 for p in pol)
            p99 = sorted(p["plan_ms_p99"] for p in pol if p.get("plan_ms_p99") is not None)
            p50 = sorted(p["plan_ms_p50"] for p in pol if p.get("plan_ms_p50") is not None)
            out["plan_ms_p50_median"] = p50[len(p50) // 2] if p50 else None
            out["plan_ms_p99_median"] = p99[len(p99) // 2] if p99 else None
            out["plan_ms_p99_max"] = p99[-1] if p99 else None
            out["quit_reasons"] = dict(Counter((r.get("reason") or "")[:80] for r in rows
                                               if r["outcome"] == "QUIT").most_common(10))
    if write and not more:
        (run_dir / "summary.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "_worker"):
        p = sub.add_parser(name)
        p.add_argument("--encounter", default="BellBeast")
        p.add_argument("--mode", choices=("data", "eval"), default="data")
        p.add_argument("--policy", default="data")
        p.add_argument("--episodes", type=int, default=10)
        p.add_argument("--hours", type=float, default=0.0)
        p.add_argument("--rotate", type=int, default=25)
        p.add_argument("--seed", type=int, default=0)
        p.add_argument("--no-record", action="store_true")
        p.add_argument("--view", choices=("oracle", "degraded", "degraded_dust", "degraded_tell"), default="oracle")
        p.add_argument("--threads", type=int, default=8)
        if name == "run":
            p.add_argument("--instances", default="0")
        else:
            p.add_argument("--instance", type=int, required=True)
            p.add_argument("--run-dir", required=True)
    s = sub.add_parser("summary")
    s.add_argument("run_dir", type=Path)
    s.add_argument("more", type=Path, nargs="*", help="more runs pooled with the first")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        return run(a)
    if a.cmd == "_worker":
        return worker(a)
    summary(a.run_dir, a.more)
    return 0


if __name__ == "__main__":
    sys.exit(main())
