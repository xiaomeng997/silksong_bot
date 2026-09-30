"""P3: drive the training copy through the oracle's in-engine keyboard injection, without focus.

Main menu -> load slot 1 -> walk right -> pause -> unpause via Continue -> walk left and jump.
Works from the title screen or from gameplay. Prints each checkpoint.
"""
import time

from ssbot.io import game_window
from ssbot.io.sinks.oracle_inject import OracleClient

MENU_SETTLE_S = 0.3  # the menu ignores input while it fades; wait a little past the fade


def step(name: str, s: dict) -> None:
    print(f"{name:<24} state={s.get('state')} menu={s.get('menu')} focused={s.get('focused')} "
          f"frame={s.get('frame')} playTime={s.get('playTime')} hero={s.get('hero')}")


def menu_ready(c: OracleClient, screen: str, timeout_s: float) -> dict:
    s = c.wait_for(lambda s: s.get("menu") == screen and not s.get("menuFading"), timeout_s)
    time.sleep(MENU_SETTLE_S)
    return s


def load_slot_one(c: OracleClient) -> dict:
    step("title", menu_ready(c, "MAIN_MENU", 60))
    c.tap("enter")  # Start game -> save select
    step("save select", menu_ready(c, "SAVE_PROFILES", 10))
    c.tap("enter")  # the highlighted slot (1)
    return c.wait_for(lambda s: s.get("state") == "PLAYING" and s.get("hero") is not None, 60)


def main() -> None:
    c = OracleClient()
    hwnd = game_window.find()
    c.own(True)

    s = c.state()
    if s.get("state") != "PLAYING":
        s = load_slot_one(c)
    step("playing", s)
    time.sleep(1.0)

    x0 = c.state()["hero"][0]
    c.keys("right")
    time.sleep(1.5)
    c.keys()
    time.sleep(0.5)
    s = c.state()
    step("walked right", s)
    print(f"  dx = {s['hero'][0] - x0:+.3f}")

    c.tap("pause")
    s = c.wait_for(lambda s: s.get("state") == "PAUSED", 3)
    t_paused = s["playTime"]
    time.sleep(2.0)
    s = c.state()
    step("paused 2s", s)
    print(f"  playTime advanced while paused: {s['playTime'] - t_paused:.3f}s")

    time.sleep(0.5)  # past the 0.3 s re-pause lockout and the menu fade-in
    c.tap("enter")   # Continue is highlighted by default when the mouse is not involved
    s = c.wait_for(lambda s: s.get("state") == "PLAYING", 3)
    step("unpaused via Continue", s)

    y_ground = c.state()["hero"][1]
    c.keys("left")
    time.sleep(0.6)
    c.keys("left", "jump")
    peak = y_ground
    for _ in range(30):
        time.sleep(1 / 60)
        peak = max(peak, c.state()["hero"][1])
    c.keys()
    time.sleep(0.8)
    step("left + jump", c.state())
    print(f"  jump height = {peak - y_ground:.3f}")
    print("game is foreground:", game_window.is_foreground(hwnd))
    c.close()


if __name__ == "__main__":
    main()
