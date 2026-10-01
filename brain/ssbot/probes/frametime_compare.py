"""Frame time of the training copy vs a near-vanilla baseline (DESIGN C14 / M1 exit: game frame time p99 within
+0.5 ms of vanilla, measured with PresentMon).

PresentMon needs administrator rights, so a person starts it (elevated), for long enough to cover both phases:

    "C:\\ssbot\\tools\\presentmon\\PresentMon-2.6.0-x64.exe" --process_name "Hollow Knight Silksong.exe"
        --output_file C:\\ssbot\\sandbox\\presentmon\\frametime.csv --timed 1800 --terminate_after_timed
        --v2_metrics --no_console_stats

Then, from brain/:

    ..\\scripts\\uv.cmd run python -m ssbot.probes.frametime_compare run [--minutes 10]
    ..\\scripts\\uv.cmd run python -m ssbot.probes.frametime_compare analyze C:\\ssbot\\sandbox\\presentmon\\frametime.csv

run: two phases on instance 0's sandbox slot 1 (Hornet sitting at the Bonetown bench, no input), one window of 1280x720
each time, nothing else running:
  A "baseline": SsOracle in minimal mode (-ssbot-minimal: the save redirect only, nothing per frame) and DebugMod parked
    outside the plugins folder (moved to C:\\ssbot\\sandbox\\parked and always moved back);
  B "training": the full training setup (SsOracle + DebugMod), a brain connected (a STATE recorder) and the frame marker
    on, as in a training session.
Each phase waits for the game to settle, then measures --minutes; the pids and times go to
C:\\ssbot\\sandbox\\presentmon\\phases.json, which analyze uses to split the CSV.

analyze: per phase, PresentMon's frame time (FrameTime / MsBetweenPresents), CPU busy and GPU busy per frame (v2
metrics): mean, p50, p99, p99.9, frames over 25 ms; the training-minus-baseline differences, and the M1 verdict (frame
time p99 difference <= 0.5 ms). With VSync on, frame time sits at the refresh period unless a frame misses it, so CPU
busy (the main thread's work per frame) is the direct measure of the added cost; both are reported.
"""
import argparse
import csv
import json
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

OUT = Path(r"C:\ssbot\sandbox\presentmon")
PHASES = OUT / "phases.json"
TRAIN = Path(r"C:\ssbot\game\train")
DEBUGMOD = TRAIN / "BepInEx" / "plugins" / "DebugMod"
PARKED = Path(r"C:\ssbot\sandbox\parked\DebugMod")
SETTLE_S = 45.0


def say(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def park_debugmod() -> None:
    if DEBUGMOD.exists():
        PARKED.parent.mkdir(parents=True, exist_ok=True)
        if PARKED.exists():
            raise SystemExit(f"refusing: {PARKED} already exists (a previous run did not restore it?)")
        shutil.move(str(DEBUGMOD), str(PARKED))
        say(f"DebugMod parked at {PARKED}")


def restore_debugmod() -> None:
    if PARKED.exists() and not DEBUGMOD.exists():
        shutil.move(str(PARKED), str(DEBUGMOD))
        say("DebugMod restored")


def shot(name: str) -> None:
    """A WGC screenshot of the game window at the start of a phase, to check by eye that both sit at the bench."""
    try:
        from ssbot.probes import shot as grab

        grab.grab(str(OUT / f"{name}.png"))
    except Exception as e:  # noqa: BLE001 - a missing screenshot must not stop the measurement
        say(f"screenshot failed: {e}")


def phase_baseline(minutes: float) -> dict:
    from ssbot.tools.launcher import Launcher

    ln = Launcher(extra=("-ssbot-minimal", "-ssbot-minimal-load", "1"), listening=lambda port, pid: True)
    ln.preflight([0])
    x = ln.start([0])[0]
    try:
        ln.wait_ready(timeout_s=120)
        say(f"baseline: pid {x.pid}, minimal mode, loading slot 1; settling {SETTLE_S:.0f} s")
        time.sleep(SETTLE_S)
        shot("baseline")
        t0 = time.time()
        say(f"baseline: measuring {minutes:.1f} min")
        time.sleep(minutes * 60)
        t1 = time.time()
        if x.proc.poll() is not None:
            raise RuntimeError(f"baseline game exited early ({x.proc.returncode})")
        return {"name": "baseline", "pid": x.pid, "t0": t0, "t1": t1}
    finally:
        ln.terminate(grace_s=10)


def phase_training(minutes: float) -> dict:
    from ssbot.ipc.oracle_link import OracleLink
    from ssbot.probes.common import load_slot
    from ssbot.record import marker as mk
    from ssbot.record.recorder import Recorder
    from ssbot.tools.launcher import Launcher

    ln = Launcher()
    ln.preflight([0])
    x = ln.start([0])[0]
    try:
        ln.wait_ready(timeout_s=180)
        link = OracleLink(instance=0, connect_timeout_s=120)
        rec = Recorder(link, profile="FRAMETIME", episode=f"frametime_{time.strftime('%H%M%S')}").start()
        try:
            load_slot(link, 1)      # Hornet sits at the bench, as in the baseline
            on = mk.marker_on(link)
            say(f"training: pid {x.pid}, recorder on, marker {on.get('rect')}; settling {SETTLE_S:.0f} s")
            time.sleep(SETTLE_S)
            shot("training")
            t0 = time.time()
            say(f"training: measuring {minutes:.1f} min")
            time.sleep(minutes * 60)
            t1 = time.time()
            if x.proc.poll() is not None:
                raise RuntimeError(f"training game exited early ({x.proc.returncode})")
            return {"name": "training", "pid": x.pid, "t0": t0, "t1": t1, "recording": str(rec.path)}
        finally:
            try:
                mk.marker_off(link)
            except Exception:  # noqa: BLE001 - the link closes anyway
                pass
            rec.close()
            link.close()
    finally:
        ln.terminate(grace_s=10)


def run(minutes: float) -> int:
    from ssbot.tools.launcher import running_game_pids

    if running_game_pids():
        raise SystemExit("refusing: a game process is running")
    OUT.mkdir(parents=True, exist_ok=True)
    phases = []
    try:
        park_debugmod()
        phases.append(phase_baseline(minutes))
    finally:
        restore_debugmod()
    time.sleep(5)
    phases.append(phase_training(minutes))
    PHASES.write_text(json.dumps({"minutes": minutes, "phases": phases}, indent=1), encoding="utf-8")
    say(f"done; wrote {PHASES}")
    subprocess.run(["reg", "query", r"HKCU\Software\Team Cherry\Hollow Knight Silksong"], capture_output=True)
    return 0


# ---- analysis -------------------------------------------------------------------------------------------------------

def _col(header: list[str], *names: str) -> int | None:
    low = [h.strip().lower() for h in header]
    for n in names:
        if n.lower() in low:
            return low.index(n.lower())
    return None


def _stats(xs: list[float]) -> dict:
    if not xs:
        return {}
    s = sorted(xs)

    def q(p):
        return round(s[min(len(s) - 1, int(len(s) * p))], 3)

    return {"n": len(s), "mean": round(statistics.fmean(s), 3), "p50": q(0.5), "p99": q(0.99), "p999": q(0.999),
            "max": round(s[-1], 3), "over_25ms": sum(1 for v in s if v > 25.0)}


def analyze(csv_path: Path, trim_s: float = 5.0) -> int:
    meta = json.loads(PHASES.read_text(encoding="utf-8"))
    by_pid = {int(p["pid"]): p for p in meta["phases"]}
    rows: dict[int, list[list[str]]] = {pid: [] for pid in by_pid}
    with open(csv_path, newline="", encoding="utf-8", errors="replace") as f:
        r = csv.reader(f)
        header = next(r)
        c_pid = _col(header, "ProcessID")
        c_time = _col(header, "CPUStartTime", "TimeInSeconds")
        c_frame = _col(header, "FrameTime", "MsBetweenPresents")
        c_cpu = _col(header, "CPUBusy")
        c_gpu = _col(header, "GPUBusy", "MsGPUActive")
        if c_pid is None or c_time is None or c_frame is None:
            raise SystemExit(f"unexpected PresentMon columns: {header}")
        for row in r:
            try:
                pid = int(row[c_pid])
            except (ValueError, IndexError):
                continue
            if pid in rows:
                rows[pid].append(row)
    out = {}
    for pid, rs in rows.items():
        name = by_pid[pid]["name"]
        if not rs:
            out[name] = {"error": f"no PresentMon rows for pid {pid}"}
            continue
        # v2 metrics: CPUStartTime is in ms since the capture started; the v1 TimeInSeconds is in s.
        scale = 1e-3 if header[c_time].strip().lower() == "cpustarttime" else 1.0
        t = [float(x[c_time]) * scale for x in rs]
        # The CSV's time is relative to the capture's start; the phase's own wall-clock window is known, and the
        # PID's last frame is the game being terminated: keep the measured window counted back from the last frame.
        dur = by_pid[pid]["t1"] - by_pid[pid]["t0"]
        end = max(t)
        keep = [x for x, ti in zip(rs, t) if end - (dur + trim_s) <= ti <= end - trim_s]

        def num(x, c):
            try:
                return float(x[c])
            except (ValueError, IndexError, TypeError):
                return None

        ft = [v for v in (num(x, c_frame) for x in keep) if v is not None]
        cpu = [v for v in (num(x, c_cpu) for x in keep) if v is not None] if c_cpu is not None else []
        gpu = [v for v in (num(x, c_gpu) for x in keep) if v is not None] if c_gpu is not None else []
        out[name] = {"pid": pid, "frame_ms": _stats(ft), "cpu_busy_ms": _stats(cpu), "gpu_busy_ms": _stats(gpu)}
    print(json.dumps(out, indent=1))
    b, tr = out.get("baseline", {}), out.get("training", {})
    if b.get("frame_ms") and tr.get("frame_ms"):
        d99 = tr["frame_ms"]["p99"] - b["frame_ms"]["p99"]
        dmean = tr["frame_ms"]["mean"] - b["frame_ms"]["mean"]
        dcpu = (tr["cpu_busy_ms"].get("p50", 0) - b["cpu_busy_ms"].get("p50", 0)) if b.get("cpu_busy_ms") and tr.get("cpu_busy_ms") else None
        dcpu99 = (tr["cpu_busy_ms"].get("p99", 0) - b["cpu_busy_ms"].get("p99", 0)) if b.get("cpu_busy_ms") and tr.get("cpu_busy_ms") else None
        print(f"\nframe time: mean {dmean:+.3f} ms, p99 {d99:+.3f} ms (training - baseline)")
        if dcpu is not None:
            print(f"CPU busy per frame: p50 {dcpu:+.3f} ms, p99 {dcpu99:+.3f} ms")
        ok = d99 <= 0.5
        print(f"{'PASS' if ok else 'FAIL'}: frame time p99 difference {d99:+.3f} ms (limit +0.5 ms)")
        (OUT / "frametime_result.json").write_text(json.dumps({"phases": out, "d_p99": d99, "d_mean": dmean,
                                                                 "d_cpu_p50": dcpu, "d_cpu_p99": dcpu99, "pass": ok},
                                                                indent=1), encoding="utf-8")
        return 0 if ok else 1
    return 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--minutes", type=float, default=10.0)
    a_ = sub.add_parser("analyze")
    a_.add_argument("csv", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "run":
        return run(a.minutes)
    return analyze(a.csv)


if __name__ == "__main__":
    sys.exit(main())
