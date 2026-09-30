"""P15 setup: create a sandbox Steel Soul save in slot 3 of the training copy and keep a template of it.

Title -> Extras -> Steel Soul code -> back -> Start -> empty slot 3 -> Steel Soul -> wait through the opening
-> first gameplay -> Save & Quit -> copy user3.dat to C:/ssbot/sandbox/p15_template/. Screenshots at each step.
"""
import shutil
import time
from pathlib import Path

from ssbot.io.sinks.oracle_inject import OracleClient
from ssbot.probes.p3_inject import menu_ready, step
from ssbot.probes.shot import grab
from ssbot.tools.savefile import decode

SANDBOX = Path(r"C:\ssbot\sandbox\saves\0\default")
OUT = Path(r"C:\ssbot\sandbox")


def quit_to_menu(c: OracleClient) -> None:
    c.tap("pause", 0.08)
    c.wait_for(lambda s: s.get("state") == "PAUSED" and s.get("menu") == "PAUSE_MENU" and not s.get("menuFading"), 5)
    time.sleep(0.3)
    c.tap("down", 0.08); time.sleep(0.25); c.tap("down", 0.08); time.sleep(0.3)
    c.tap("enter", 0.08); time.sleep(0.8)
    c.tap("up", 0.08); time.sleep(0.3)
    c.tap("enter", 0.08)
    c.wait_for(lambda s: s.get("state") == "MAIN_MENU" and s.get("menu") == "MAIN_MENU", 20)


def main() -> None:
    if (SANDBOX / "user3.dat").exists():
        raise SystemExit("slot 3 already exists in the sandbox; move it away first")
    c = OracleClient()
    c.own(True)
    step("title", menu_ready(c, "MAIN_MENU", 60))

    for _ in range(3):
        c.tap("down", 0.08); time.sleep(0.25)
    c.tap("enter", 0.08)
    menu_ready(c, "EXTRAS_MENU", 10)
    for key in ("up", "down", "up", "down", "left", "right", "left", "right"):
        c.tap(key, 0.08); time.sleep(0.15)
    time.sleep(1.0)
    shared = decode(SANDBOX / "shared.dat")
    print("sandbox shared.dat:", shared)
    c.tap("pause", 0.08)  # Esc = menu cancel -> back to the title
    menu_ready(c, "MAIN_MENU", 10)
    for _ in range(3):
        c.tap("up", 0.08); time.sleep(0.25)

    c.tap("enter", 0.08)
    menu_ready(c, "SAVE_PROFILES", 10)
    c.tap("right", 0.08); time.sleep(0.3); c.tap("right", 0.08); time.sleep(0.4)
    grab(str(OUT / "p15_slot3.png"))
    c.tap("enter", 0.08)
    s = menu_ready(c, "PLAY_MODE_MENU", 10)
    step("mode menu", s)
    grab(str(OUT / "p15_mode_0.png"))
    c.tap("down", 0.08); time.sleep(0.4)  # Classic -> Steel Soul (verified on the screenshot)
    grab(str(OUT / "p15_mode_1.png"))
    print("check p15_mode_1.png shows Steel Soul highlighted, then run with --go")


def go() -> None:
    c = OracleClient()
    c.tap("enter", 0.08)
    s = c.wait_for(lambda s: s.get("state") == "PLAYING" and s.get("hero") is not None, 600)
    step("first gameplay", s)
    print("permadeath:", s.get("permadeath"), "scene:", s.get("scene"))
    time.sleep(3)
    grab(str(OUT / "p15_ingame.png"))
    quit_to_menu(c)
    dst = OUT / "p15_template"
    dst.mkdir(exist_ok=True)
    shutil.copy2(SANDBOX / "user3.dat", dst / "user3.dat")
    save = decode(dst / "user3.dat")["playerData"]
    print("template saved:", {k: save.get(k) for k in ("permadeathMode", "playTime", "health", "respawnScene")})
    c.close()


if __name__ == "__main__":
    import sys
    go() if "--go" in sys.argv else main()
