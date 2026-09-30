"""P5 on the vanilla final copy: buy the Magnetite Brooch from Pebb in slot 2 -> FIRST_TOOL through Steam.

No oracle here (the final copy is vanilla), so every step is SendInput with a foreground check plus a WGC
screenshot for review.   python -m ssbot.probes.p5_final walk | shop | buy
"""
import sys
import time

from ssbot.io import game_window
from ssbot.io.sinks import sendinput
from ssbot.probes.shot import grab

OUT = r"C:\ssbot\sandbox"


def press(key: str, hold: float = 0.06) -> None:
    hwnd = game_window.find()
    game_window.park_cursor_outside(hwnd)  # the vanilla menus follow mouse hover
    if not game_window.focus(hwnd):
        raise SystemExit("could not focus the game; no key sent")
    sendinput.tap(key, hold)


def quit_to_menu() -> None:
    press("pause")
    time.sleep(0.9)           # 0.3 s lockout + menu fade-in
    press("down"); time.sleep(0.25)
    press("down"); time.sleep(0.3)
    grab(rf"{OUT}\p5f_quit_sel.png")
    press("enter"); time.sleep(0.8)
    press("up"); time.sleep(0.3)   # the confirm dialog defaults to 否
    grab(rf"{OUT}\p5f_quit_confirm.png")
    press("enter")
    time.sleep(8.0)
    grab(rf"{OUT}\p5f_menu.png")


def steel_soul_code() -> None:
    """Main menu -> 额外内容 (Extras) -> Up Down Up Down Left Right Left Right (m0:N32)."""
    for _ in range(3):
        press("down"); time.sleep(0.25)
    grab(rf"{OUT}\p5f_extras_sel.png")
    press("enter"); time.sleep(1.5)
    grab(rf"{OUT}\p5f_extras.png")
    for key in ("up", "down", "up", "down", "left", "right", "left", "right"):
        press(key, 0.08)
        time.sleep(0.15)
    time.sleep(2.0)
    grab(rf"{OUT}\p5f_code.png")


def walk() -> None:
    press("enter")            # title: Start game
    time.sleep(2.0)
    grab(rf"{OUT}\p5f_saves.png")
    press("right")            # slot 2
    time.sleep(0.5)
    press("enter")
    time.sleep(12.0)          # load + bench wake-up
    grab(rf"{OUT}\p5f_loaded.png")
    press("right", 4.5)       # bench at x~238.8, Pebb's talk range at x~274.8, run speed 8.25 u/s
    time.sleep(0.8)
    grab(rf"{OUT}\p5f_at_pebb.png")


def shop() -> None:
    press("up", 0.1)          # talk
    time.sleep(1.5)
    for _ in range(3):
        press("jump", 0.08)   # advance dialogue (Z is Submit on keyboard)
        time.sleep(1.2)
    grab(rf"{OUT}\p5f_shop.png")


def buy() -> None:
    press("jump", 0.08)       # buy the highlighted item (Magnetite Brooch)
    time.sleep(1.2)
    grab(rf"{OUT}\p5f_confirm.png")
    press("jump", 0.08)       # 是 (Yes) is the default in the purchase prompt
    time.sleep(3.0)
    grab(rf"{OUT}\p5f_bought.png")


if __name__ == "__main__":
    prev = game_window.foreground()
    try:
        {"walk": walk, "shop": shop, "buy": buy, "quit": quit_to_menu, "code": steel_soul_code}[sys.argv[1]]()
    finally:
        sendinput.release_all()
        game_window.restore_foreground(prev)
