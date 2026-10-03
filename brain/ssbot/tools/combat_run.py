"""Run combat episodes on training instances and summarise them (M2 W0 / W2 / W7).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.launcher -n 4 --detach
    ../scripts/uv.cmd run python -m ssbot.tools.combat_run run --instances 0,1,2,3 --encounter BellBeast --mode data
        --episodes 50 [--hours 2] [--no-record] [--seed 0]
    ../scripts/uv.cmd run python -m ssbot.tools.combat_run summary C:/ssbot/data/runs/m2/<run>
    ../scripts/uv.cmd run python -m ssbot.tools.combat_run stop C:/ssbot/data/runs/m2/<run>     # graceful stop
    ../scripts/uv.cmd run python -m ssbot.tools.combat_run seal C:/ssbot/data/runs/m2/<run>     # after a hard kill

run: one worker process per instance (each has its own link and recorder; the STATE stream is too heavy for one
Python process to decode for four instances). Each worker: load sandbox slot 1 from the title if needed (DebugMod
needs the gameplay HUD before a savestate load), turn save suppression on (encounter savestates carry progress the
sandbox slot must never get), then loops episodes (ssbot.train.episode.run_episode) until --episodes or --hours.
Writes <run>/attempts_i<N>.jsonl (one AttemptRecord per line) and, unless --no-record, the STATE recording
<run>/rec/<date>/TRAIN/i<N>_<k>/ rotated every --rotate episodes (each record has its f_reset / f_end frames).

Modes: "data" (behaviour logging: a lethal hit is counted, play goes on, random HP / silk / position at the wake),
"eval" (a lethal hit ends the episode as WOULD_DIE; HP and silk as the route has them).

Stopping: a worker ends after its current episode when <run>/STOP or the agents' stop file (STOP_FILES) exists
(`stop` writes <run>/STOP); on Ctrl+C / Ctrl+Break it drops the episode in progress. Either way it closes its
recorder on the way out (meta.json status "closed"). A process killed outright (TerminateProcess, taskkill /F)
cannot: `seal` marks such recordings "aborted" (their chunks are intact; the reader rebuilds a missing index from
the data).
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
STOP_FILES = (Path(r"C:\ssbot\sandbox\STOP_AGENTS"),)


def stop_requested(run_dir: Path) -> bool:
    return (run_dir / "STOP").exists() or any(f.exists() for f in STOP_FILES)


def git_rev() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              cwd=Path(__file__).resolve().parents[2], timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def make_policy(name: str, view: str = "oracle", run_dir: Path | None = None, instance: int = 0,
                threads: int = 8, real_quit: float = 0.0, inject_hits: float = 0.0, gauntlet: bool = False):
    if name == "data":
        from ssbot.train.data_policy import DataPolicy, GauntletDataPolicy
        return GauntletDataPolicy() if gauntlet else DataPolicy()
    if name == "planner":
        from ssbot.train.planner_policy import PlannerPolicy
        pol = PlannerPolicy(view=view, threads=threads, log_dir=run_dir, instance=instance, real_quit_p=real_quit)
        if inject_hits > 0:
            # the pause stress test (ssbot.train.hit_injection, ssbot.tools.pause_stress): one fault per episode
            from ssbot.train.hit_injection import HitInjector
            pol = HitInjector(pol, p_event=inject_hits)
        return pol
    raise SystemExit(f"unknown policy {name}")


def mode_config(mode: str, seed: int, timebox_s: float | None = None, silk: tuple[int, int] | None = None,
                hp: tuple[int, int] | None = None):
    """timebox_s overrides the encounter's (the Forum's default is 1500 s: complete gauntlets with the random data
    policy took 714-990 s, 10 episodes of the runs of 2026-10-02, and the finale comes last). silk / hp: eval mode's
    randomize_start silk / health range (--start-silk / --start-hp; None: as loaded). A start at 3 HP (h 2 against the
    Bell Beast's 2-mask hits) makes the boss's first hit the Q1 one: the low-HP check's natural hits, whose freeze
    shapes the injected hits do not vary (pause_quit.md 7.7)."""
    from ssbot.train.episode import EpisodeConfig
    if mode == "data":
        return EpisodeConfig(mode="data", seed=seed, hp=(1, 5), silk=(0, 9), dx=(-6.0, 2.0), facing="random",
                             wait_frames=(0, 30), timebox_s=timebox_s)
    if mode == "eval":
        return EpisodeConfig(mode="eval", seed=seed, hp=hp, silk=silk, dx=(-3.0, 1.0), facing="random",
                             wait_frames=(0, 30), timebox_s=timebox_s)
    raise SystemExit(f"unknown mode {mode}")


def _in_game_without_control(s: dict) -> bool:
    """A save is loaded (a scene, the hero exported, not the title or save-select menus) but Hornet takes no input:
    a cutscene (the post-kill memory scene), a transition or a load. load_slot only knows the menus and gameplay.
    While PLAYING the menu state is not read: UIManager keeps the save-select menuState after a game starts from it
    (instance 4's first start, 2026-10-02: an empty slot 1 began a new game in Tut_01 with menu still SAVE_PROFILES,
    and load_slot pressed Enter there and timed out twice)."""
    from ssbot.probes.common import GS_PLAYING, MENU_MAIN, MENU_SAVE_PROFILES, in_gameplay
    g = s.get("game") or {}
    on_menu = g.get("gs") != GS_PLAYING and g.get("menu") in (MENU_MAIN, MENU_SAVE_PROFILES)
    return bool(g.get("scene")) and bool(s.get("hero")) and not on_menu and not in_gameplay(s)


def worker(a: argparse.Namespace) -> int:
    from ssbot.ipc.oracle_link import OracleLink
    from ssbot.probes.common import load_slot, stand_up
    from ssbot.record.recorder import Recorder
    from ssbot.train.encounters import ENCOUNTERS
    from ssbot.train.episode import AttemptRecord, make_tap, run_episode

    enc = ENCOUNTERS[a.encounter]
    run_dir = Path(a.run_dir)
    out = (run_dir / f"attempts_i{a.instance}.jsonl").open("a", encoding="utf-8", newline="\n")
    link = OracleLink(instance=a.instance, connect_timeout_s=120)
    tap = make_tap(link, enc)
    policy = make_policy(a.policy, a.view, run_dir, a.instance, a.threads, a.real_quit, a.inject_hits,
                         gauntlet=bool(enc.waves))
    if a.silk_reserve:
        pb = getattr(getattr(policy, "inner", policy), "pb", None)
        if pb is not None:
            pb.bind_reserve_at_full_hp = True
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
    s0 = link.wait_state(lambda s: s.get("game") is not None, timeout_s=120)
    if _in_game_without_control(s0):
        # a game is loaded but Hornet takes no input: the post-kill memory scene after a CLEAR (gate run
        # 20261002_150453 i3: the last episode of the chunk before was a kill, and load_slot waited 60 s for a main
        # menu that never came). The encounter's savestate loads from there, as between episodes.
        print(f"[i{a.instance}] in a game without control (scene {(s0.get('game') or {}).get('scene')}): "
              f"loading the savestate", flush=True)
        link.rpc("savestate.load", timeout_s=40, name=enc.savestate, timeout=30)
        from ssbot.train.episode import wait_settled
        wait_settled(link, enc.scene, timeout_s=60)
    load_slot(link, 1)                   # a no-op in gameplay
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
            if stop_requested(run_dir):
                print(f"[i{a.instance}] stop requested, ending after {k} episodes", flush=True)
                break
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
            run_episode(link, enc, tap, policy, mode_config(a.mode, seed, a.timebox or None,
                                                            tuple(a.start_silk) if a.start_silk else None,
                                                            tuple(a.start_hp) if a.start_hp else None), rec)
            d = asdict(rec)
            d["instance"] = a.instance
            d["episode"] = k
            d["recording"] = str(rec_obj.path) if rec_obj else None
            d["t"] = datetime.now().isoformat(timespec="seconds")
            out.write(json.dumps(d) + "\n")
            out.flush()
            counts[rec.outcome] += 1
            if rec.gauntlet is not None:
                g = rec.gauntlet
                atk = {"wave": g.get("wave_reached"), "kills": (g.get("kills") or {}).get("n"),
                       "allies": sorted(g.get("allies") or {})}
            else:
                atk = {s: n for s, n in rec.attacks.items()
                       if s in ("Charge Antic", "Leap Out", "Burst Antic", "Rage Antic")}
            print(f"[i{a.instance} ep{k}] {rec.outcome:12s} {rec.ingame_s or 0:6.1f}s hits {rec.hits} wd {rec.would_die} "
                  f"boss_hp {rec.boss_hp_end} {atk} {rec.reason or ''}", flush=True)
            k += 1
            rq = (d.get("policy") or {}).get("real_quit")
            if rq and (rq.get("main_menu") or rq.get("steps")):
                # a real quit left the game on (or on its way to) the main menu: back into the sandbox slot
                load_slot(link, 1)
                stand_up(link)
                if not link.rpc("guards.set", save_suppression=True)["save_suppression"]:
                    raise SystemExit("save suppression could not be turned on")
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


def new_run_dir(encounter: str, tag: str, root: Path | None = None, now: datetime | None = None) -> Path:
    """Create and return <root>/<timestamp>_<encounter>_<tag>; when another run took that name in the same second,
    <name>_2, _3, ... (two launchers started in the same second collided with FileExistsError, 2026-10-03 07:45).
    The mkdir itself is the claim, so two processes racing for one name cannot both get it."""
    root = RUNS if root is None else root
    base = f"{(now or datetime.now()):%Y%m%d_%H%M%S}_{encounter}_{tag}"
    root.mkdir(parents=True, exist_ok=True)
    for k in range(1, 1000):
        d = root / (base if k == 1 else f"{base}_{k}")
        try:
            d.mkdir()
            return d
        except FileExistsError:
            continue
    raise FileExistsError(f"no free run dir name for {root / base}")


def run(a: argparse.Namespace) -> int:
    tag = a.mode if a.policy == "data" else f"{a.mode}_{a.policy}_{a.view}"
    if a.inject_hits > 0:
        tag += "_inject"
    run_dir = new_run_dir(a.encounter, tag)
    (run_dir / "config.json").write_text(json.dumps(vars(a), indent=1), encoding="utf-8")
    procs = []
    for i in [int(x) for x in a.instances.split(",")]:
        cmd = [sys.executable, "-m", "ssbot.tools.combat_run", "_worker", "--instance", str(i), "--run-dir",
               str(run_dir), "--encounter", a.encounter, "--mode", a.mode, "--policy", a.policy, "--episodes",
               str(a.episodes), "--hours", str(a.hours or 0), "--rotate", str(a.rotate), "--seed", str(a.seed),
               "--view", a.view, "--threads", str(a.threads), "--real-quit", str(a.real_quit),
               "--inject-hits", str(a.inject_hits), "--timebox", str(a.timebox or 0)]
        if a.start_silk:
            cmd += ["--start-silk", str(a.start_silk[0]), str(a.start_silk[1])]
        if a.silk_reserve:
            cmd.append("--silk-reserve")
        if a.start_hp:
            cmd += ["--start-hp", str(a.start_hp[0]), str(a.start_hp[1])]
        if a.no_record:
            cmd.append("--no-record")
        log = (run_dir / f"worker_i{i}.log").open("w", encoding="utf-8")
        procs.append((i, subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env={**os.environ, "PYTHONUNBUFFERED": "1"}), log))
        print(f"worker i{i}: pid {procs[-1][1].pid}", flush=True)
    print(f"run dir: {run_dir}", flush=True)
    rc = 0
    try:
        for i, p, log in procs:
            rc |= p.wait()
            log.close()
    except KeyboardInterrupt:          # Ctrl+C / Ctrl+Break: the workers finish their episode and close up
        (run_dir / "STOP").write_text("interrupted\n", encoding="utf-8")
        for i, p, log in procs:
            try:
                rc |= p.wait()
            except KeyboardInterrupt:
                pass
            log.close()
    summary(run_dir)
    return rc


def seal(run_dir: Path) -> int:
    """Mark recordings a killed worker left "recording" as "aborted" (no live worker may still write them)."""
    n = 0
    for meta_p in sorted((run_dir / "rec").glob("*/*/*/meta.json")):
        m = json.loads(meta_p.read_text(encoding="utf-8"))
        if m.get("status") == "recording":
            m["status"] = "aborted"
            m["error"] = m.get("error") or "worker killed before it closed the recorder (sealed by combat_run seal)"
            meta_p.write_text(json.dumps(m, indent=1), encoding="utf-8")
            print(f"sealed {meta_p.parent}")
            n += 1
    print(f"{n} recording(s) sealed")
    return 0


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
            out["unpredicted_unknown"] = sum(len(p.get("unpredicted_unknown") or ()) for p in pol)
            bh = [p.get("bell_hits") or {} for p in pol]
            out["bell_hit_monitor"] = {k: sum(int(b.get(k) or 0) for b in bh)
                                       for k in ("tinks", "skipped", "evaluated", "violations", "over_template")}
            out["episodes_with_forced_risk"] = sum(1 for p in pol if p.get("forced_risk_ticks"))
            out["forced_risk_ticks"] = sum(p.get("forced_risk_ticks") or 0 for p in pol)
            rq = [p["real_quit"] for p in pol if p.get("real_quit")]
            fired = [q for q in rq if q.get("steps")]
            if rq:
                lat = sorted(q["pause_latency_s"] for q in fired if q.get("pause_latency_s") is not None)
                menu_s = sorted(next((t for t, k, _ in q["steps"] if k == "done"), None) or 0.0 for q in fired)
                out["real_quits"] = {"armed": len(rq), "paused": len(fired),
                                     "main_menu": sum(1 for q in fired if q.get("main_menu")),
                                     "pause_latency_s_p50": lat[len(lat) // 2] if lat else None,
                                     "pause_latency_s_max": lat[-1] if lat else None,
                                     "to_main_menu_s_max": menu_s[-1] if menu_s else None,
                                     "submits": sum(len(q.get("submits") or ()) for q in fired),
                                     "wrong_submits": sum(q.get("wrong_submits") or 0 for q in fired),
                                     "unexpected_unpauses": sum(q.get("unexpected_unpauses") or 0 for q in fired)}
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
        p.add_argument("--timebox", type=float, default=0.0,
                       help="seconds from the wake before STUCK (0: the encounter's timebox_s)")
        p.add_argument("--real-quit", type=float, default=0.0,
                       help="probability that a confirmed supervisor pause quits for real (menu, Yes, main menu), "
                            "then the worker reloads sandbox slot 1 and the savestate")
        p.add_argument("--inject-hits", type=float, default=0.0, metavar="SHARE",
                       help="pause stress test: inject one fault per episode (a hit down to 1 HP through "
                            "hurt.special, a supervisor quit trigger QF, or both on one tick), SHARE of them on the "
                            "hard moments (kill, bounce, Silkspear cast, clash, the pause press), the rest on "
                            "airborne / attack / pogo frames or with planner keys down (0: off); summarise with "
                            "ssbot.tools.pause_stress")
        p.add_argument("--start-silk", type=int, nargs=2, default=None, metavar=("LO", "HI"),
                       help="eval mode: randomize_start's silk range at the wake (default: as loaded)")
        p.add_argument("--start-hp", type=int, nargs=2, default=None, metavar=("LO", "HI"),
                       help="eval mode: randomize_start's health range at the wake (default: as loaded; 3 3 = h 2 "
                            "against the Bell Beast, so its first hit is Q1's: natural post-hit windows)")
        p.add_argument("--silk-reserve", action="store_true",
                       help="planner policy: keep the Bind's 9 silk at full HP too (playbook "
                            "reserve_at_full_hp; the Q1a low-HP check starts with 9 silk and keeps it)")
        if name == "run":
            p.add_argument("--instances", default="0")
        else:
            p.add_argument("--instance", type=int, required=True)
            p.add_argument("--run-dir", required=True)
    s = sub.add_parser("summary")
    s.add_argument("run_dir", type=Path)
    s.add_argument("more", type=Path, nargs="*", help="more runs pooled with the first")
    for name in ("stop", "seal"):
        sub.add_parser(name).add_argument("run_dir", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "run":
        return run(a)
    if a.cmd == "_worker":
        return worker(a)
    if a.cmd == "stop":
        (a.run_dir / "STOP").write_text("requested\n", encoding="utf-8")
        return 0
    if a.cmd == "seal":
        return seal(a.run_dir)
    summary(a.run_dir, a.more)
    return 0


if __name__ == "__main__":
    sys.exit(main())
