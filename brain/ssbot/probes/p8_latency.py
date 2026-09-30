"""P8: Windows Graphics Capture timing and the SendInput -> captured-frame loopback latency.

  python -m ssbot.probes.p8_latency capture [seconds]   frame rate, jitter, capture->callback delay (no focus needed)
  python -m ssbot.probes.p8_latency loop [trials]       Esc -> first frame showing the pause dim (needs focus)

Frame.timespan is SystemRelativeTime in 100 ns units on the QPC clock, the same clock as time.perf_counter_ns.
Run against the training copy in gameplay (state PLAYING); `loop` turns the oracle's keyboard ownership off
so real SendInput keys reach the game, and turns it back on at the end.
"""
import statistics
import sys
import threading
import time

import numpy as np
from windows_capture import WindowsCapture

from ssbot.io import game_window
from ssbot.io.sinks import sendinput
from ssbot.io.sinks.oracle_inject import OracleClient


class Capture:
    def __init__(self, hwnd: int):
        self.lock = threading.Lock()
        self.frames: list[tuple[int, int, float]] = []  # (timespan_ns, callback_ns, mean luma of the centre)
        self.stop = False
        self.cap = WindowsCapture(cursor_capture=False, draw_border=False, window_hwnd=hwnd)

        @self.cap.event
        def on_frame_arrived(frame, control):
            now = time.perf_counter_ns()
            buf = frame.frame_buffer
            h, w = buf.shape[:2]
            centre = buf[h // 4: 3 * h // 4: 8, w // 4: 3 * w // 4: 8, :3]
            with self.lock:
                self.frames.append((frame.timespan * 100, now, float(centre.mean())))
            if self.stop:
                control.stop()

        @self.cap.event
        def on_closed():
            pass

        self.control = self.cap.start_free_threaded()

    def close(self) -> None:
        self.stop = True
        self.control.stop()

    def since(self, t_ns: int) -> list[tuple[int, int, float]]:
        with self.lock:
            return [f for f in self.frames if f[0] >= t_ns]


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def run_capture(seconds: float) -> None:
    cap = Capture(game_window.find())
    time.sleep(seconds)
    cap.close()
    fr = cap.frames[5:]
    ts = [f[0] for f in fr]
    gaps = [(b - a) / 1e6 for a, b in zip(ts, ts[1:])]
    delays = [(f[1] - f[0]) / 1e6 for f in fr]
    dur = (ts[-1] - ts[0]) / 1e9
    print(f"frames {len(fr)} in {dur:.2f}s -> {len(fr) / dur:.1f} fps")
    print(f"frame interval ms  p50 {pct(gaps, 50):.2f}  p99 {pct(gaps, 99):.2f}  max {max(gaps):.2f}  "
          f"(>25 ms: {sum(g > 25 for g in gaps)})")
    print(f"capture->callback  p50 {pct(delays, 50):.2f}  p99 {pct(delays, 99):.2f}  max {max(delays):.2f} ms")


def run_loop(trials: int) -> None:
    oracle = OracleClient()
    oracle.own(False)
    hwnd = game_window.find()
    prev = game_window.foreground()
    game_window.park_cursor_outside(hwnd)
    cap = Capture(hwnd)
    lat_frame, lat_cb = [], []
    try:
        for i in range(trials):
            if not game_window.focus(hwnd):
                print("could not bring the game to the foreground; aborting before sending any key")
                break
            oracle.wait_for(lambda s: s.get("state") == "PLAYING" and s.get("focused"), 5)
            time.sleep(0.6)
            base = cap.since(time.perf_counter_ns() - 300_000_000)
            base_luma = statistics.median(f[2] for f in base)
            if not game_window.is_foreground(hwnd):
                print("lost the foreground; aborting before sending any key")
                break
            t0 = time.perf_counter_ns()
            sendinput.send([("pause", True)])
            time.sleep(0.05)
            sendinput.send([("pause", False)])
            # The pause menu fades in: `onset` is the first frame that is darker at all (the true pipeline
            # latency plus the game's own reaction), `dim` the first frame dimmed by 30 %.
            base_noise = max(abs(f[2] - base_luma) for f in base) / max(base_luma, 1.0)
            onset = dim = None
            deadline = time.perf_counter() + 1.5
            while dim is None and time.perf_counter() < deadline:
                for f in cap.since(t0):
                    if onset is None and f[2] < (0.98 - base_noise) * base_luma:
                        onset = f
                    if f[2] < 0.7 * base_luma:
                        dim = f
                        break
                time.sleep(0.002)
            if onset and dim:
                lat_frame.append((onset[1] - t0) / 1e6)
                lat_cb.append((dim[1] - t0) / 1e6)
                print(f"trial {i + 1:2d}: key->onset {lat_frame[-1]:6.1f} ms   key->30% dim {lat_cb[-1]:6.1f} ms"
                      f"   (baseline noise {base_noise:.3%})")
            else:
                print(f"trial {i + 1:2d}: no change detected")
            oracle.wait_for(lambda s: s.get("state") == "PAUSED", 3)
            time.sleep(0.6)  # 0.3 s lockout + menu fade
            if not game_window.is_foreground(hwnd):
                print("lost the foreground while paused; aborting")
                break
            sendinput.tap("enter", 0.05)  # Continue
            oracle.wait_for(lambda s: s.get("state") == "PLAYING", 3)
    finally:
        cap.close()
        sendinput.release_all()
        oracle.own(True)
        game_window.restore_foreground(prev)
    if lat_frame:
        print(f"key->onset (callback)    p50 {pct(lat_frame, 50):.1f}  p90 {pct(lat_frame, 90):.1f}  max {max(lat_frame):.1f} ms")
        print(f"key->30% dim (callback)  p50 {pct(lat_cb, 50):.1f}  p90 {pct(lat_cb, 90):.1f}  max {max(lat_cb):.1f} ms")


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "capture":
        run_capture(float(sys.argv[2]) if len(sys.argv) > 2 else 10)
    elif mode == "loop":
        run_loop(int(sys.argv[2]) if len(sys.argv) > 2 else 20)
