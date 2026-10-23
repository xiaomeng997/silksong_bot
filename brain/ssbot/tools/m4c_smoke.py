"""Map v2 stage M4c: THE OFFLINE REAL-TIME SMOKE of SSBOT_FORUM_MAP2 (HANDOFF 'Task map2 - stage M4' / 'M4c'). No game
is touched: recorded w7 / w13 episodes replayed through the policy at 60 STATEs per second of wall time
(forum_policy_replay --realtime: a slow tick skips frames, which reach the policy through its catch-up path as live), two
at a time (the two instances' bots), the replay process boosted like the live bot (High, the P-cores, EcoQoS off) and
map2's search workers boosted by themselves - so the workers run at real latency against the bot's own load.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.m4c_smoke run --out <dir> [--frames 4000] [--arms map2,off]
        [--set parts=2] [--co <checkout root>]
    ../scripts/uv.cmd run python -m ssbot.tools.m4c_smoke report --out <dir>

Arms: map2 (SSBOT_FORUM_MAP2=1, SSBOT_FORUM_HERO2=1 on the default arm rnjb) and off (HERO2 only: the bot's tick times
without map2, the control). The open loop: her position is the recording's - map2's plans are not followed - so the
per-frame check's hero tolerance is logged, not enforced (LiveCfg.replay), and 'in control' means: committed after
the exact re-simulation and its Clappers still consistent with the recording.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

REC = [("20261012_192006_Forum_W_w7_eval_planner_oracle_clashM", 0, 1, "w7a"),
       ("20261016_144051_Forum_W_w13_eval_planner_oracle_clashM", 1, 0, "w13a"),
       ("20261016_084036_Forum_W_w7_eval_planner_oracle_clashM_2", 1, 0, "w7b"),
       ("20261017_102908_Forum_W_w13_eval_planner_oracle_clashM", 0, 0, "w13b")]
RNJB = {"SSBOT_FORUM_FR": "seen_cf", "SSBOT_FORUM_REACT": "escape+n+g", "SSBOT_FORUM_MARGIN": "state",
        "SSBOT_FORUM_V2": "1", "SSBOT_FORUM_V2_EVERY": "1", "SSBOT_FORUM_V2_CORNER": "13", "SSBOT_FORUM_RUNE_NOPRE": "1",
        "SSBOT_FORUM_RUNE_BOMB": "1", "SSBOT_FORUM_RUNE_HOP": "1", "SSBOT_FORUM_NOGLIDE": "1",
        "SSBOT_FORUM_RUNE_FACE": "3", "SSBOT_FORUM_SLAM_PLAY": "1", "SSBOT_FORUM_JUMP_BEHIND": "1"}
ARMS = {"map2": {"SSBOT_FORUM_HERO2": "1", "SSBOT_FORUM_MAP2": "1"}, "off": {"SSBOT_FORUM_HERO2": "1"}}


def _boost(pid: int) -> str:
    try:
        import ctypes
        import psutil
        p = psutil.Process(pid)
        p.nice(psutil.HIGH_PRIORITY_CLASS)
        p.cpu_affinity([c for c in range(16) if c < (psutil.cpu_count() or 0)])

        class _PT(ctypes.Structure):
            _fields_ = [("Version", ctypes.c_uint32), ("ControlMask", ctypes.c_uint32), ("StateMask", ctypes.c_uint32)]
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x0200 | 0x1000, False, pid)        # PROCESS_SET_INFORMATION | QUERY_LIMITED
        st = _PT(1, 1, 0)
        ok = k32.SetProcessInformation(ctypes.c_void_p(h), 4, ctypes.byref(st), ctypes.sizeof(st))
        k32.CloseHandle(h)
        return f"High, P-cores, throttling {'off' if ok else 'unchanged'}"
    except Exception as e:  # noqa: BLE001
        return f"boost failed: {e}"


def cmd_run(a) -> int:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    co = Path(a.co) if a.co else Path(__file__).resolve().parents[3]
    uv = co / "scripts" / "uv.cmd"
    recs = [r for r in REC if not a.only or r[3] in a.only.split(",")]
    arms = [x for x in a.arms.split(",") if x]
    pairs = [recs[i:i + 2] for i in range(0, len(recs), 2)]
    log = (out / "run.log").open("a", encoding="utf-8")
    for arm in arms:
        for pair in pairs:
            procs = []
            for (run, inst, ep, tag) in pair:
                t = f"{arm}_{tag}"
                env = {k: v for k, v in os.environ.items() if not k.startswith("SSBOT_FORUM")}
                env.update(RNJB)
                env.update(ARMS[arm])
                env.update({"NUMBA_NUM_THREADS": "4", "PYTHONIOENCODING": "utf-8"})
                if a.set and arm == "map2":
                    env["SSBOT_FORUM_MAP2_SET"] = a.set
                cmd = [str(uv), "run", "python", "-m", "ssbot.tools.forum_policy_replay", "--run",
                       f"C:/ssbot/data/runs/m2/{run}", "--instance", str(inst), "--episode", str(ep), "--frames",
                       str(a.frames), "--wave-frames", "1", "--crest", "Wanderer", "--clash", "main", "--realtime",
                       "--ticks-out", str(out / f"ticks_{t}.jsonl"), "--out", str(out / f"rep_{t}.json")]
                if arm == "map2":
                    cmd += ["--map2-log", str(out / f"map2_{t}.jsonl")]
                fh = (out / f"log_{t}.txt").open("w", encoding="utf-8")
                p = subprocess.Popen(cmd, cwd=str(co / "brain"), env=env, stdout=fh, stderr=subprocess.STDOUT)
                procs.append((t, p, fh))
                log.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} start {t} pid {p.pid}\n")
                log.flush()
            # boost the replays (the bot's process; uv's child python included) once they run
            time.sleep(3.0)
            try:
                import psutil
                for (t, p, _) in procs:
                    for q in [psutil.Process(p.pid)] + psutil.Process(p.pid).children(recursive=True):
                        if "python" in (q.name() or "").lower() and "spawn_main" not in " ".join(q.cmdline()):
                            log.write(f"  boost {t} {q.pid}: {_boost(q.pid)}\n")
            except Exception as e:  # noqa: BLE001
                log.write(f"  boost failed: {e}\n")
            log.flush()
            for (t, p, fh) in procs:
                rc = p.wait()
                fh.close()
                log.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} end {t} exit {rc}\n")
                log.flush()
            if Path(r"C:\ssbot\sandbox\STOP_AGENTS").exists():
                log.write("STOP_AGENTS: stop\n")
                return 1
    return 0


def _pct(v, qs=(50, 90, 99)):
    v = [x for x in v if x is not None]
    return [round(float(np.percentile(v, q)), 2) for q in qs] if v else None


def report(out: Path) -> dict:
    res = {}
    for rp in sorted(out.glob("rep_*.json")):
        t = rp.stem[4:]
        d = json.loads(rp.read_text("utf-8"))
        lg = (out / f"log_{t}.txt")
        tb = lg.read_text("utf-8", errors="ignore").count("Traceback") if lg.exists() else None
        r = {"ticks": d.get("ticked"), "tick_ms_p50": d.get("tick_ms_p50"), "tick_ms_p99": d.get("tick_ms_p99"),
             "late_ticks": d.get("late_ticks"), "realtime": d.get("realtime"), "tracebacks": tb}
        m = d.get("map2")
        if m:
            r.update({k: m.get(k) for k in ("share_m2", "pre_ms_p50", "pre_ms_p99", "post_ms_p50", "post_ms_p99",
                                            "check_ms_p50", "check_ms_p99", "search_ms_p50", "search_ms_p90",
                                            "commit_age_p50", "commit_age_p90", "bridge_followed")})
            r["counts"] = m.get("counts")
            r["errors"] = len(m.get("errors") or [])
            r["workers"] = {k: v.get("boost") for k, v in (m.get("workers") or {}).items()}
        ml = out / f"map2_{t}.jsonl"
        if ml.exists():
            rows = [json.loads(x) for x in ml.read_text("utf-8").splitlines() if x]
            own = Counter(x.get("own") for x in rows)
            why = Counter(x.get("why") for x in rows)
            busy = Counter(x.get("busy") for x in rows if x.get("busy"))
            chk = Counter(c[2] for x in rows for c in x.get("chk") or ())
            wst = Counter(str((x.get("w") or {}).get("status")).split(":")[0] for x in rows if x.get("w"))
            wms = [(x.get("w") or {}).get("ms") for x in rows if (x.get("w") or {}).get("ms")]
            commits = [x["commit"] for x in rows if x.get("commit")]
            runs, cur = [], 0
            for x in rows:
                if x.get("m2"):
                    cur += 1
                elif cur:
                    runs.append(cur)
                    cur = 0
            if cur:
                runs.append(cur)
            dh = [abs(x["dh"][0]) for x in rows if x.get("dh")]
            # per commit: its plan, its check, how long it kept the keys and why it ended
            plans = []
            cur_p = None
            for x in rows:
                if x.get("commit"):
                    c = x["commit"]
                    ck = next((q for q in x.get("chk") or () if q[0] == c["pid"]), None)
                    cur_p = {"f": x["f"], "pid": c["pid"], "age": x.get("age"), "origin": c["origin"],
                             "value": c["value"], "hits": c["hits"], "outs": c["outs"], "alive": c["alive"],
                             "search_ms": c["ms"], "check": None if ck is None else ck[2:8], "ticks": 0,
                             "end": None, "contacts": len(c.get("cp") or ()), "bridge": c.get("bridge")}
                    plans.append(cur_p)
                if cur_p is not None:
                    if x.get("m2") and x.get("pid") == cur_p["pid"]:
                        cur_p["ticks"] += 1
                    elif cur_p["end"] is None and x["f"] > cur_p["f"]:
                        cur_p["end"] = x.get("why")
                        cur_p = None
            r.update({"rows": len(rows), "own": dict(own.most_common()), "why": dict(why.most_common()),
                      "busy": dict(busy.most_common()), "checks": dict(chk.most_common()),
                      "worker_status": dict(wst.most_common()), "worker_ms": _pct(wms),
                      "commits": len(commits), "commit_origin": dict(Counter(c["origin"] for c in commits)),
                      "commits_bridge_ok": sum(1 for c in commits if c.get("bridge")),
                      "commit_hits": round(float(np.mean([c["hits"] for c in commits])), 3) if commits else None,
                      "commit_value": round(float(np.mean([c["value"] for c in commits])), 3) if commits else None,
                      "control_runs": _pct(runs, (50, 90, 100)), "n_runs": len(runs),
                      "dh_abs": _pct(dh), "bot_ms_map2": _pct([x.get("ms") for x in rows]),
                      "plans": plans, "plan_end": dict(Counter(p_["end"] for p_ in plans).most_common())})
        res[t] = r
    return res


def cmd_report(a) -> int:
    out = Path(a.out)
    res = report(out)
    (out / "report.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    for t, r in res.items():
        print(t, json.dumps(r, default=str)[:3000])
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--out", required=True)
    r.add_argument("--frames", type=int, default=4000)
    r.add_argument("--arms", default="map2,off")
    r.add_argument("--set", default="")
    r.add_argument("--co", default="")
    r.add_argument("--only", default="")
    p = sub.add_parser("report")
    p.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    return cmd_run(a) if a.cmd == "run" else cmd_report(a)


if __name__ == "__main__":
    sys.exit(main())
