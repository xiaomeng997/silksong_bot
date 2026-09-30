"""Manual driving helper for M0 probes: focus the game, send keys, grab a screenshot.

Usage: python -m ssbot.probes.drive focus | tap KEY [hold_s] | hold KEY seconds | shot PATH | seq KEY,KEY,... [gap_s]
"""
import sys
import time

from PIL import ImageGrab

from ssbot.io import game_window
from ssbot.io.sinks import sendinput


def _hwnd() -> int:
    hwnd = game_window.find()
    if not hwnd:
        sys.exit("game window not found")
    game_window.park_cursor_outside(hwnd)
    if not game_window.is_foreground(hwnd) and not game_window.focus(hwnd):
        time.sleep(0.2)
        if not game_window.is_foreground(hwnd):
            sys.exit("could not focus the game window")
    return hwnd


def main(argv: list[str]) -> None:
    cmd, args = argv[0], argv[1:]
    prev = game_window.foreground()
    hwnd = _hwnd()
    time.sleep(0.1)
    try:
        _run(cmd, args, hwnd)
    finally:
        sendinput.release_all()
        if "--keep-focus" not in args:
            game_window.restore_foreground(prev)


def _run(cmd: str, args: list[str], hwnd: int) -> None:
    args = [a for a in args if a != "--keep-focus"]
    if cmd == "focus":
        print("focused", game_window.rect(hwnd))
    elif cmd == "tap":
        sendinput.tap(args[0], float(args[1]) if len(args) > 1 else sendinput.MIN_HOLD_S)
    elif cmd == "hold":
        sendinput.hold(args[0], float(args[1]))
    elif cmd == "seq":
        gap = float(args[1]) if len(args) > 1 else 0.4
        for key in args[0].split(","):
            sendinput.tap(key, 0.05)
            time.sleep(gap)
    elif cmd == "shot":
        ImageGrab.grab(bbox=game_window.rect(hwnd), all_screens=True).save(args[0])
        print("saved", args[0])
    else:
        sys.exit(f"unknown command {cmd}")


if __name__ == "__main__":
    main(sys.argv[1:])
