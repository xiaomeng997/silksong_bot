"""Record a person playing the training copy (DESIGN D12): every oracle STATE frame plus a 1080p screen video.

    python -m ssbot.tools.human_session            # launches the game, records until the game is closed

The training copy runs with -ssbot-human (the oracle only observes: vanilla keyboard/gamepad/mouse), its own
sandbox save instance (default 9), fullscreen at 1920x1080 render resolution. Before launch and when the game
exits, the golden PlayerPrefs snapshot is applied; on exit ffmpeg is stopped and meta.json written. The gamepad keys
(NativeInput/XInput/AppleMFi), which the player may have to switch on for their controller and which only affect
gamepads (m0:C15; the final run uses no gamepad).

Labels (DESIGN §3.1.4): the oracle refuses the frame marker under -ssbot-human, so this session's frames carry
timestamp labels only (meta.json "labels": "timestamp"; the camera-trajectory monitor ssbot.record.align flags their
alignment). The screen video is stored as captured: like every image a model sees, its frames get the vision mask
(ssbot.vision.mask.apply, on the full-resolution frame) before any other preprocessing when a dataset is built.
"""
import argparse
import json
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import zstandard

from ssbot.ipc.oracle_link import OracleLink
from ssbot.tools.launcher import PrefsGuard, process_created

GAME = Path(r"C:\ssbot\game\train\Hollow Knight Silksong.exe")
# A copy outside AppData (see brain/uv.toml): the winget install may only exist inside the Claude app's package view.
# ffmpeg 9.0.2: its NVENC API 13.1 needs NVIDIA driver >= 610 (617.14 installed).
FFMPEG = Path(r"C:\ssbot\tools\ffmpeg\bin\ffmpeg.exe")
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", type=int, default=9)
    ap.add_argument("--out", default=r"C:\ssbot\data\human")
    ap.add_argument("--no-video", action="store_true")
    args = ap.parse_args()

    session = Path(args.out) / datetime.now().strftime("%Y%m%d_%H%M%S")
    session.mkdir(parents=True)
    print(f"session: {session}")

    game_args = ["-ssbot-human", "-ssbot-instance", str(args.instance), "-logFile", str(session / "player.log"),
                 "-screen-fullscreen", "1", "-screen-width", "1920", "-screen-height", "1080"]
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
    if not args.no_video:
        cmd = [str(FFMPEG), "-hide_banner", "-loglevel", "warning", "-stats", "-y",
               "-f", "lavfi", "-i", "ddagrab=output_idx=0:framerate=60:draw_mouse=0",
               "-vf", "hwdownload,format=bgra,scale=1920:1080:flags=area,format=nv12",
               "-c:v", "hevc_nvenc", "-preset", "p5", "-tune", "hq", "-rc", "constqp", "-qp", "18", "-g", "120",
               str(session / "video.mkv")]
        video_start_qpc = time.perf_counter_ns()
        video = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=(session / "ffmpeg.log").open("wb"))
        print("recording video ...")

    start = time.time()
    try:
        while game.poll() is None:
            time.sleep(1)
    except KeyboardInterrupt:
        print("stopping (game still running)")
    duration = time.time() - start

    if video is not None:
        try:
            video.communicate(b"q", timeout=20)
        except subprocess.TimeoutExpired:
            video.kill()
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
        # No frame marker under -ssbot-human: timestamp labels only, and the video is unmasked (mask at dataset build).
        "labels": "timestamp",
        "video_masked": False,
        "kept_gamepad_prefs": keep,
    }
    (session / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("duration_s", "state_frames_written", "state_frames_dropped_by_recorder",
                                           "last_oracle_drop_counter", "kept_gamepad_prefs")}, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
