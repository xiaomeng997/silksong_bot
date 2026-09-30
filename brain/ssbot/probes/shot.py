"""Grab frames of the game window through Windows Graphics Capture (works while the game is unfocused or covered, not
while it is minimized)."""
import sys
import threading
import time

import cv2
import numpy as np
from windows_capture import WindowsCapture

from ssbot.io import game_window


def grab(path: str) -> None:
    done = threading.Event()
    cap = WindowsCapture(cursor_capture=False, draw_border=False, window_hwnd=game_window.find())

    @cap.event
    def on_frame_arrived(frame, control):
        cv2.imwrite(path, frame.frame_buffer[:, :, :3])
        done.set()
        control.stop()

    @cap.event
    def on_closed():
        done.set()

    cap.start_free_threaded()
    done.wait(3)


def grab_frames(n: int, timeout_s: float = 3.0, hwnd: int | None = None) -> list[tuple[int, np.ndarray]]:
    """The next n frames of the window as (time.perf_counter_ns() when the callback ran, BGR copy of the whole window
    image incl. title bar; crop with game_window.client_in_capture). The callback time is the QPC clock STATE "q" uses;
    Frame.timespan is not (it runs 7-10 ms ahead, probes.md P8). Fewer frames on timeout."""
    frames: list[tuple[int, np.ndarray]] = []
    done = threading.Event()
    cap = WindowsCapture(cursor_capture=False, draw_border=False, window_hwnd=hwnd or game_window.find())

    @cap.event
    def on_frame_arrived(frame, control):
        now = time.perf_counter_ns()
        if len(frames) < n:
            frames.append((now, frame.frame_buffer[:, :, :3].copy()))
        if len(frames) >= n:
            done.set()
            control.stop()

    @cap.event
    def on_closed():
        done.set()

    control = cap.start_free_threaded()
    done.wait(timeout_s)
    if not done.is_set():
        control.stop()
    return list(frames)


if __name__ == "__main__":
    grab(sys.argv[1])
    print("saved", sys.argv[1])
