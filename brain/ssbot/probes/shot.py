"""Grab one frame of the game window through Windows Graphics Capture (works while the game is unfocused)."""
import sys
import threading

import cv2
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


if __name__ == "__main__":
    grab(sys.argv[1])
    print("saved", sys.argv[1])
