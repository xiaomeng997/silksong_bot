"""Bell Beast underground tells (M2 stage C): screenshots of one instance's window at fixed delays after the boss's
"Control" FSM enters an underground antic, to see whether vision can tell where and how it will come up.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.probes.m2_tells --instance 3 [--episodes 4] [--out C:/ssbot/sandbox/m2_tells]

The fight is played by PlannerPolicy (oracle view) through run_episode, so the boss runs its normal pattern. A
Windows Graphics Capture session on the instance's window (found by the game process's -ssbot-instance argument)
keeps the last frames; when a STATE shows the boss entering Emerge Antic C, Emerge Antic L, Burst Antic or Rage Antic,
the frames arriving first after +0.0 (the entry frame), +0.1, +0.3, +0.6 and +0.9 s are written as
<state>_<n>_<+t>s_x<hidden x>.png, with a JSON sidecar holding the STATE frame, the boss's hidden x and the pixel
column/row where its anchor (x, ground y 5.49) projects with that frame's camera (ssbot.tools.projector). Times are
arrival times of the STATE and of the capture callback (both QPC, time.perf_counter_ns), so a shot is about one
frame late. Drop bells (--what bells): every DropBell entering Antic (it falls about 1.25 s later), the shots named
DropBell_<L|L2|M|M2|R|R2>_<n>, projected at the ceiling (y 13.74) above it. It also dumps the static graphs of the
boss's and a drop bell's Control FSMs (RPC fsm.graph: action type names per state; parameters are not exported).
"""
import argparse
import ctypes
import json
import random
import sys
import threading
import time
from collections import deque
from ctypes import wintypes
from pathlib import Path

import numpy as np

STATES = ("Emerge Antic C", "Emerge Antic L", "Burst Antic", "Rage Antic")
BELL = "BoneBeast DropBell"          # drop bells: Dormant -> Antic (about 1.25 s, not drawn) -> Air (drawn, falls)
BELL_STATES = ("Antic",)
CEILING_Y = 13.74
DELAYS = (0.0, 0.1, 0.3, 0.6, 0.9)
BOSS = "Bone Beast"
GROUND_Y = 5.49


def instance_hwnd(instance: int) -> int:
    """The top-level window of the game process started with -ssbot-instance <instance>."""
    import subprocess
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "Get-CimInstance Win32_Process -Filter \"Name like 'Hollow Knight Silksong%'\" | "
                          "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }"],
                         capture_output=True, text=True, check=True).stdout
    pid = next((int(line.split("\t")[0]) for line in out.splitlines()
                if f"-ssbot-instance {instance} " in line + " "), None)
    if pid is None:
        raise SystemExit(f"no game process for instance {instance}")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    found: list[int] = []
    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    user32.EnumWindows(proto(cb), 0)
    if not found:
        raise SystemExit(f"no visible window for pid {pid}")
    return found[0]


class Shooter:
    """Continuous WGC capture of one window; shots are requested at absolute perf_counter_ns times."""

    def __init__(self, hwnd: int, out: Path):
        from windows_capture import WindowsCapture
        self.out = out
        self.ring: deque = deque(maxlen=4)
        self.pending: list[tuple[int, str, dict]] = []
        self.lock = threading.Lock()
        self.saved: list[str] = []
        cap = WindowsCapture(cursor_capture=False, draw_border=False, window_hwnd=hwnd)

        @cap.event
        def on_frame_arrived(frame, control):
            now = time.perf_counter_ns()
            with self.lock:
                due = [p for p in self.pending if p[0] <= now]
                if not due:
                    return
                self.pending = [p for p in self.pending if p[0] > now]
            img = frame.frame_buffer[:, :, :3].copy()
            for t_req, name, meta in due:
                threading.Thread(target=self._write, args=(img, name, dict(meta, late_ms=(now - t_req) / 1e6)),
                                 daemon=True).start()

        @cap.event
        def on_closed():
            pass

        self.control = cap.start_free_threaded()

    def request(self, t_ns: int, name: str, meta: dict) -> None:
        with self.lock:
            self.pending.append((t_ns, name, meta))

    def _write(self, img: np.ndarray, name: str, meta: dict) -> None:
        import cv2
        cv2.imwrite(str(self.out / f"{name}.png"), img)
        (self.out / f"{name}.json").write_text(json.dumps(meta, indent=1), "utf-8")
        self.saved.append(name)

    def stop(self) -> None:
        try:
            self.control.stop()
        except Exception:
            pass


class TellPolicy:
    """PlannerPolicy plus the screenshot trigger on Control state entries."""

    def __init__(self, inner, shooter: Shooter, hwnd: int, link=None, what: str = "all"):
        self.inner = inner
        self.shooter = shooter
        self.hwnd = hwnd
        self.link = link
        self.what = what
        self.prev: str | None = None
        self.count: dict[str, int] = {s: 0 for s in STATES + ("DropBell",)}
        self.bell_prev: dict[int, str] = {}
        self.graphs: dict[str, object] = {}

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def reset(self, rng, enc) -> None:
        self.prev = None
        self.bell_prev = {}
        self.inner.reset(rng, enc)

    def _shoot(self, s: dict, t_ns: int, tag: str, n: int, x: float, y: float, extra: dict) -> None:
        from ssbot.io.game_window import client_in_capture
        from ssbot.tools.projector import project_cam
        px = None
        if s.get("cam"):
            xy, _ = project_cam([(x, y)], s["cam"])
            px = [round(float(v), 1) for v in xy[0]]
        meta = dict(extra, f=s.get("f"), x=round(x, 3), y=round(y, 3), px_render=px,
                    render_screen=(s.get("cam") or {}).get("screen"),
                    client_in_capture=list(client_in_capture(self.hwnd)), hero=(s.get("hero") or {}).get("pos"))
        for d in DELAYS:
            self.shooter.request(t_ns + int(d * 1e9), f"{tag}_{n:02d}_+{d:.1f}s_x{x:.1f}", dict(meta, delay_s=d))

    def _graph(self, key: str, iid: int) -> None:
        if key not in self.graphs and self.link is not None:
            self.graphs[key] = self.link.rpc_async("fsm.graph", iid=iid, fsm="Control")

    def act(self, s: dict, tap):
        t_ns = time.perf_counter_ns()
        boss = next((e for e in s.get("ents") or () if e.get("type_key") == BOSS), None)
        st = (boss.get("fsms") or [{}])[0].get("state") if boss else None
        for e in s.get("ents") or ():
            tk = e.get("type_key") or ""
            if not tk.startswith(BELL):
                continue
            bst = (e.get("fsms") or [{}])[0].get("state")
            if bst != self.bell_prev.get(e["iid"]) and bst in BELL_STATES and self.what in ("all", "bells"):
                self.count["DropBell"] += 1
                self._graph("DropBell", e["iid"])
                self._shoot(s, t_ns, "DropBell_" + tk[len(BELL):].strip().replace(" ", ""), self.count["DropBell"],
                            float(e["pos"][0]), CEILING_Y, {"state": bst, "type_key": tk})
            self.bell_prev[e["iid"]] = bst
        if boss is not None:
            self._graph("Bone Beast", boss["iid"])
        if st != self.prev and st in STATES and self.what in ("all", "boss"):
            from ssbot.io.game_window import client_in_capture
            from ssbot.tools.projector import project_cam
            self.count[st] += 1
            x = float(boss["pos"][0])
            px = None
            if s.get("cam"):
                xy, _ = project_cam([(x, GROUND_Y)], s["cam"])
                px = [round(float(v), 1) for v in xy[0]]
            meta = {"state": st, "f": s.get("f"), "hidden_x": round(x, 3), "anchor_px_render": px,
                    "render_screen": (s.get("cam") or {}).get("screen"),
                    "client_in_capture": list(client_in_capture(self.hwnd)),
                    "hero": ((s.get("hero") or {}).get("pos"))}
            tag = st.replace(" ", "_")
            for d in DELAYS:
                self.shooter.request(t_ns + int(d * 1e9), f"{tag}_{self.count[st]:02d}_+{d:.1f}s_x{x:.1f}",
                                     dict(meta, delay_s=d))
        if st is not None:
            self.prev = st
        return self.inner.act(s, tap)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instance", type=int, default=3)
    ap.add_argument("--episodes", type=int, default=4)
    ap.add_argument("--out", type=Path, default=Path("C:/ssbot/sandbox/m2_tells"))
    ap.add_argument("--what", choices=("all", "boss", "bells"), default="all")
    ap.add_argument("--min-bells", type=int, default=12)
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)

    from ssbot.ipc.oracle_link import OracleLink
    from ssbot.probes.common import load_slot, stand_up
    from ssbot.train.encounters import BELL_BEAST
    from ssbot.train.episode import AttemptRecord, EpisodeConfig, FightTap, run_episode, unpause
    from ssbot.train.planner_policy import PlannerPolicy

    hwnd = instance_hwnd(a.instance)
    link = OracleLink(instance=a.instance, connect_timeout_s=120)
    s0 = link.wait_state(lambda s: s.get("game") is not None, timeout_s=60)
    if (s0.get("game") or {}).get("paused"):
        unpause(link)
        time.sleep(0.6)
    load_slot(link, 1)
    stand_up(link)
    if not link.rpc("guards.set", save_suppression=True)["save_suppression"]:
        raise SystemExit("save suppression could not be turned on")
    inner = PlannerPolicy(view="oracle", threads=4)
    inner.attach(link)
    print(f"warm-up {inner.warmup():.1f} s", flush=True)
    shooter = Shooter(hwnd, a.out)
    pol = TellPolicy(inner, shooter, hwnd, link, a.what)
    tap = FightTap(link, BELL_BEAST)
    graphs_done = False
    try:
        for k in range(a.episodes):
            rec = AttemptRecord(unit="BellBeast", stage="PROBE", profile="TRAIN", build="1.0.30000", code_rev="",
                                config_fp="", start_kind="savestate", mode="data", seed=9000 + k)
            run_episode(link, BELL_BEAST, tap, pol, EpisodeConfig(mode="data", seed=9000 + k, dx=(-3.0, 1.0)), rec)
            print(f"ep{k}: {rec.outcome} {rec.ingame_s}s shots so far {dict(pol.count)}", flush=True)
            if not graphs_done and pol.graphs:
                out = {}
                for key, fut in pol.graphs.items():
                    try:
                        g = fut.result(timeout=10)
                        out[key] = {st["name"]: st.get("actions") for st in g.get("states", [])}
                    except Exception as e:
                        out[key] = f"error: {e}"
                (a.out / "control_actions.json").write_text(json.dumps(out, indent=1), "utf-8")
                graphs_done = True
            boss_ok = all(pol.count[s] >= 3 for s in ("Emerge Antic C", "Emerge Antic L")) or a.what == "bells"
            bells_ok = pol.count["DropBell"] >= a.min_bells or a.what == "boss"
            if boss_ok and bells_ok:
                break
    finally:
        time.sleep(1.2)
        shooter.stop()
        link.close()
    print(f"saved {len(shooter.saved)} shots to {a.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
