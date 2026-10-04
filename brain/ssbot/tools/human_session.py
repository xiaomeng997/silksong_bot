"""Record a person playing the training copy (DESIGN D12): every oracle STATE frame plus a 1080p screen video whose
frames carry exact labels from the oracle's frame marker.

    python -m ssbot.tools.human_session            # launches the game, records until the game is closed
    python -m ssbot.tools.human_video <session>    # the labels again (also for a session whose labelling failed)

The training copy runs with -ssbot-human (the oracle only observes: vanilla keyboard/gamepad/mouse), its own
sandbox save instance (default 9), fullscreen at 1920x1080 render resolution. Before launch and when the game
exits, the golden PlayerPrefs snapshot is applied; on exit ffmpeg is stopped and meta.json written. The gamepad keys
(NativeInput/XInput/AppleMFi), which the player may have to switch on for their controller and which only affect
gamepads (m0:C15; the final run uses no gamepad).

Labels (DESIGN §3.1.4, D12): once the oracle is connected the session turns its frame marker on (marker_on, as every
training session does: a 56 x 16 px pattern at the top right of the 1920x1080 render) and says whether it is on
(printed, and meta.json "marker": on, cell, rect, render size, or why not). The screen video is ffmpeg ddagrab of the
desktop scaled to 1920x1080 through ssbot.tools.human_video.ffmpeg_cmd: the vision mask's rect of that output (and
the marker's box, should the oracle's report map it elsewhere: mask_mismatch) is filled before encoding, so
video.mkv holds no marker pixel as long as the game window keeps the placement it had when the video started, and that
corner alone goes losslessly to corner.mkv. The filter graph is fixed at the start: switching the game between
fullscreen and a window (Alt+Enter, the options menu), changing its resolution or moving it to another monitor
mid-session moves the marker out of the filled rect, so do not change display settings while recording (a change
seen by the 1 s placement poll flags the session mask_mismatch; one undone within a second goes unseen). meta.json "video" records the
output, the render size, the game window's client rect and the desktop size (polled every second: "placements"), the
filled rects and the corner. At the end the marker goes off (also after an error or Ctrl+C; the oracle turns it off
when the link closes anyway), and human_video.labels decodes the corner frame by frame: labels.npz (per video frame:
pts, decoded frame or -1 and why, label frame and source, mask_mismatch) and meta.json "labels" (the marker-labelled
share and the rest). An older SsOracle refuses the marker under -ssbot-human: the session runs as before, masked all
the same, with timestamp labels only (meta.json "labels": {"source": "timestamp", "why": ...}).
"""
import argparse
import ctypes
import json
import queue
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

import zstandard

from ssbot.ipc.oracle_link import OracleError, OracleLink
from ssbot.probes.common import in_gameplay
from ssbot.record.marker import marker_off, marker_on
from ssbot.record.video import inside
from ssbot.tools.human_video import FFMPEG, OUT, ffmpeg_cmd, fills_for, labels, output_box, write_meta
from ssbot.tools.launcher import PrefsGuard, find_window, process_created, set_dpi_aware
from ssbot.vision import mask as vmask

GAME = Path(r"C:\ssbot\game\train\Hollow Knight Silksong.exe")
RENDER = (1920, 1080)       # -screen-width / -screen-height
# Commands from the lead while a person plays (the oracle takes one IPC client at a time, so they go through this
# session's own link): one per line, "load <savestate>" loads that savestate with save suppression on, e.g. to start
# or retry the Forum demo (2026-10-03); "speed <x>" scales the game's time (oracle time.scale, e.g. 0.5 for the
# person's half-speed practice, 1 to restore). The file is consumed when read; every command lands in meta.json
# "commands".
CMD_FILE = Path(r"C:\ssbot\sandbox\human_cmd.txt")


def run_commands(link: OracleLink, log: list) -> None:
    """Execute and remove CMD_FILE's commands; a load waits until the person is in gameplay (title screen: refused)."""
    if not CMD_FILE.exists():
        return
    try:
        text = CMD_FILE.read_text(encoding="utf-8-sig")
    finally:
        CMD_FILE.unlink(missing_ok=True)
    for line in text.splitlines():
        parts = line.split()
        entry = {"t_ns": time.perf_counter_ns(), "frame": (link.state or {}).get("f"), "cmd": line.strip()}
        if len(parts) == 2 and parts[0] == "load":
            if not in_gameplay(link.state or {}):
                entry["result"] = "refused: not in gameplay (continue a save slot first)"
            else:
                try:
                    link.rpc("guards.set", save_suppression=True)
                    link.rpc("savestate.load", timeout_s=60, name=parts[1], timeout=50)
                    entry["result"] = "loaded"
                except (OracleError, TimeoutError) as e:
                    entry["result"] = f"failed: {e}"
        elif len(parts) == 2 and parts[0] == "speed":
            try:
                r = link.rpc("time.scale", scale=float(parts[1]))
                entry["result"] = f"speed {r.get('scale')}"
            except (OracleError, TimeoutError, ValueError) as e:
                entry["result"] = f"failed: {e}"
        elif parts:
            entry["result"] = "unknown command"
        if parts:
            print(f"command {entry['cmd']!r}: {entry.get('result')}")
            log.append(entry)
PREFS_KEY = r"HKCU\Software\Team Cherry\Hollow Knight Silksong"
KEEP_PREFIXES = ("NativeInput_h", "XInput_h", "AppleMFi_h")


class StateWriter:
    """Appends raw IPC frames (length-prefixed, as received) to a zstd stream on a background thread."""

    def __init__(self, path: Path):
        self.q: queue.Queue[bytes | None] = queue.Queue(maxsize=3600)
        self.dropped = 0
        self.frames = 0
        self._f = path.open("wb")
        self._z = zstandard.ZstdCompressor(level=3).stream_writer(self._f)
        self._t = threading.Thread(target=self._run, name="StateWriter", daemon=True)
        self._t.start()

    def push(self, msg_type: int, raw: bytes) -> None:
        try:
            self.q.put_nowait(raw)
        except queue.Full:
            self.dropped += 1

    def _run(self) -> None:
        while (raw := self.q.get()) is not None:
            self._z.write(raw)
            self.frames += 1

    def close(self) -> None:
        self.q.put(None)
        self._t.join()
        self._z.flush(zstandard.FLUSH_FRAME)
        self._z.close()


def reg(*args: str) -> None:
    subprocess.run(["reg", *args], capture_output=True, check=True)


def reapply_gamepad_keys(keep: dict[str, str]) -> None:
    """The golden snapshot carries the frozen gamepad backend; keep the player's choice on top of it."""
    for name, dword in keep.items():
        reg("add", PREFS_KEY, "/v", name, "/t", "REG_DWORD", "/d", dword, "/f")


def gamepad_keys() -> dict[str, str]:
    out = subprocess.run(["reg", "query", PREFS_KEY], capture_output=True, text=True).stdout
    keep = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0].startswith(KEEP_PREFIXES) and parts[1] == "REG_DWORD":
            keep[parts[0]] = str(int(parts[2], 16))
    return keep


def turn_marker_on(link) -> dict:
    """The frame marker on, as in every training session; meta.json "marker". A refusal (an older SsOracle under
    -ssbot-human) or a marker no STATE shows in place leaves it off (marker_on turns such a marker off again): the
    session goes on with timestamp labels."""
    try:
        res = marker_on(link, timeout_s=30.0)  # the game may still be loading
    except (OracleError, TimeoutError) as e:
        why = f"{type(e).__name__}: {e}"
        print(f"frame marker not on ({why}): this session gets timestamp labels only")
        return {"on": False, "why": why}
    print(f"frame marker on ({res.get('corner')}, {res.get('cell')} px cells at {res.get('rect')} of a "
          f"{res.get('screen')} render{', cell sent explicitly' if res.get('resent') else ''})")
    return {"on": True, "why": None, "corner": res.get("corner"), "cell": res.get("cell"), "rect": res.get("rect"),
            "screen": res.get("screen"), "resent": bool(res.get("resent"))}


def client_on_screen(hwnd: int) -> list[int] | None:
    """The window's client rect on the desktop, [x, y, w, h] in physical px (the process is DPI-aware); None while
    it has no area (minimised)."""
    user32 = ctypes.windll.user32
    pt, rc = wintypes.POINT(0, 0), wintypes.RECT()
    if not user32.ClientToScreen(hwnd, ctypes.byref(pt)) or not user32.GetClientRect(hwnd, ctypes.byref(rc)):
        return None
    w, h = rc.right - rc.left, rc.bottom - rc.top
    return [pt.x, pt.y, w, h] if w > 0 and h > 0 and pt.x > -10000 else None


def placement(pid: int) -> dict | None:
    """Where the game's image is: its window's client rect on the desktop and the size of the desktop ddagrab
    captures (output 0: the primary monitor). None without a visible window."""
    user32 = ctypes.windll.user32
    hwnd = find_window(pid)
    client = client_on_screen(hwnd) if hwnd else None
    if client is None:
        return None
    return {"client": client, "desktop": [user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", type=int, default=9)
    ap.add_argument("--out", default=r"C:\ssbot\data\human")
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--no-marker", action="store_true", help="leave the frame marker off (timestamp labels only)")
    ap.add_argument("--savestate", default=None,
                    help="load this savestate once the person is in gameplay (save suppression on); later loads "
                         f"through {CMD_FILE}")
    ap.add_argument("--speed", type=float, default=None, help="game speed once in gameplay (time.scale), e.g. 0.5")
    args = ap.parse_args()
    if args.savestate or args.speed:
        CMD_FILE.write_text((f"load {args.savestate}\n" if args.savestate else "")
                            + (f"speed {args.speed}\n" if args.speed else ""), encoding="utf-8")
    commands: list = []

    session = Path(args.out) / datetime.now().strftime("%Y%m%d_%H%M%S")
    session.mkdir(parents=True)
    print(f"session: {session}")

    game_args = ["-ssbot-human", "-ssbot-instance", str(args.instance), "-logFile", str(session / "player.log"),
                 "-screen-fullscreen", "1", "-screen-width", str(RENDER[0]), "-screen-height", str(RENDER[1])]
    # Register with the training launcher's PrefsGuard, so a human session and bot instances never race on the shared
    # PlayerPrefs: it refuses while other game processes run, and restores the golden snapshot once, when the last
    # registered instance is gone. We also start from the frozen settings, whatever the registry holds now (the
    # player's own launches, or a registry view that differs between the Claude app and Explorer).
    guard = PrefsGuard.default()
    keep = gamepad_keys()
    game_holder: dict = {}

    def start() -> tuple[int, float | None]:
        guard.store.restore(guard.golden)
        reapply_gamepad_keys(keep)
        game_holder["p"] = subprocess.Popen([str(GAME), *game_args], cwd=GAME.parent)
        return game_holder["p"].pid, process_created(game_holder["p"].pid)

    guard.launch(start, instance=args.instance)
    game = game_holder["p"]
    print("game started; waiting for the oracle ...")

    link = OracleLink(instance=args.instance, connect_timeout_s=120)
    states = StateWriter(session / "state.raw.zst")
    link.subscribe_raw(states.push)
    print(f"oracle connected: {link.hello['plugin']} on {link.hello['game']}, instance {link.hello['instance']}")

    video = None
    video_start_qpc = None
    marker = {"on": False, "why": "--no-marker"}
    vmeta: dict = {}
    start = time.time()
    try:  # whatever happens, the marker goes off and the streams are closed
        if not args.no_marker:
            marker = turn_marker_on(link)
        set_dpi_aware()  # window and desktop rects in physical px, as ddagrab captures them
        desktop = [ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)]
        # No visible window yet: assume what the arguments ask for, a fullscreen window over the whole desktop.
        placements = [placement(game.pid) or {"client": [0, 0, *desktop], "desktop": desktop, "assumed": True}]
        render = tuple(marker.get("screen") or RENDER)
        mask = vmask.mask_rect(*OUT)
        box = output_box(marker["rect"], render, tuple(placements[0]["client"]), tuple(placements[0]["desktop"])) \
            if marker["on"] else None
        fills = fills_for([box])
        if box is not None and not inside(box, mask):
            print(f"WARNING mask_mismatch: the marker lands at {list(box)} of the {OUT[0]}x{OUT[1]} video, outside "
                  f"the vision mask {list(mask)}; filled too, but these frames are not training data")
        vmeta = {"out": list(OUT), "render": list(render), "placements": placements, "mask": list(mask),
                 "marker_box": list(box) if box else None, "fills": fills,
                 "corner": list(mask) if marker["on"] else None}
        if not args.no_video:
            cmd = ffmpeg_cmd(session, fills, mask if marker["on"] else None)
            video_start_qpc = time.perf_counter_ns()
            video = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=(session / "ffmpeg.log").open("wb"))
            print("recording video (masked; the marker's corner to corner.mkv) ..." if marker["on"]
                  else "recording video (masked) ...")
        try:
            while game.poll() is None:
                time.sleep(1)
                if CMD_FILE.exists() and (not (args.savestate or args.speed) or in_gameplay(link.state or {}) or commands):
                    run_commands(link, commands)
                p = placement(game.pid)
                if p is not None and all((p["client"], p["desktop"]) != (q["client"], q["desktop"])
                                         for q in placements):
                    print(f"game window moved: client {p['client']} on a {p['desktop']} desktop")
                    placements.append(dict(p, t_ns=time.perf_counter_ns()))
        except KeyboardInterrupt:
            print("stopping (game still running)")
    finally:
        duration = time.time() - start
        if video is not None:
            try:
                video.communicate(b"q", timeout=20)
            except subprocess.TimeoutExpired:
                video.kill()
        if marker["on"]:
            try:
                marker_off(link)
            except (OracleError, TimeoutError, OSError):  # the game is gone: it went off with the link
                pass
        link.close()
        states.close()

    keep = gamepad_keys()
    if guard.release(game.pid):  # golden restored: this was the last registered instance
        reapply_gamepad_keys(keep)

    meta = {
        "started": datetime.fromtimestamp(start).isoformat(timespec="seconds"),
        "duration_s": round(duration, 1),
        "instance": args.instance,
        "hello": link.hello,
        "game_args": game_args,
        "state_frames_written": states.frames,
        "state_frames_dropped_by_recorder": states.dropped,
        "last_oracle_drop_counter": (link.state or {}).get("drop"),
        "video_start_qpc_ns": video_start_qpc,
        "video_cmd": video.args if video is not None else None,
        "video_masked": video is not None,       # the vision mask's rect (and any marker box outside it) filled
        "video": vmeta,
        "marker": marker,
        "labels": {"source": "none", "why": "--no-video"} if video is None else
        {"source": "timestamp", "why": marker["why"]} if not marker["on"] else {"source": "marker", "pending": True},
        "kept_gamepad_prefs": keep,
        "commands": commands,
    }
    write_meta(session, meta)
    print(json.dumps({k: meta[k] for k in ("duration_s", "state_frames_written", "state_frames_dropped_by_recorder",
                                           "last_oracle_drop_counter", "kept_gamepad_prefs")}, ensure_ascii=False))
    if video is not None and marker["on"]:
        print("labelling the video frames from the marker's corner ...")
        try:
            summary = labels(session)
            print(json.dumps(summary, ensure_ascii=False))
        except Exception as e:  # noqa: BLE001 - the recording is kept; python -m ssbot.tools.human_video redoes this
            print(f"labelling failed ({e!r}); run: python -m ssbot.tools.human_video {session}")
            meta["labels"] = {"source": "marker", "pending": True, "error": repr(e)}
            write_meta(session, meta)
    sys.exit(0)


if __name__ == "__main__":
    main()
