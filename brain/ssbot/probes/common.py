"""Shared helpers for in-game probes that drive the training copy over IPC v1."""
import time

from ssbot.ipc.framing import mask
from ssbot.ipc.oracle_link import OracleLink

GS_PLAYING = 4
MENU_MAIN = 1
MENU_SAVE_PROFILES = 6


def tap(link: OracleLink, button: str, hold_frames: int = 4) -> int:
    """One-shot press a couple of frames ahead (does not arm the brain-lost watchdog). Returns the target frame."""
    target = link.frame + 2
    link.act(target, mask(button), hold_frames=hold_frames)
    return target


def menu_ready(link: OracleLink, menu: int, timeout_s: float = 60.0, settle_s: float = 0.3) -> dict:
    """Wait until `menu` is shown and no menu fade is running, then a little longer (fading menus drop input)."""
    s = link.wait_state(lambda s: s["game"]["menu"] == menu and not s["game"].get("fading"), timeout_s=timeout_s)
    time.sleep(settle_s)
    return s


def press_until(link: OracleLink, button: str, done, tries: int = 3, wait_s: float = 5.0) -> dict:
    """Tap `button` until done(state) holds; a press during a fade or a transition is silently dropped by the game."""
    for attempt in range(tries):
        tap(link, button)
        try:
            return link.wait_state(done, timeout_s=wait_s)
        except TimeoutError:
            if attempt == tries - 1:
                raise
    raise AssertionError("unreachable")


def in_gameplay(s: dict) -> bool:
    """Playing with a hero who either takes input or sits on a bench (control stays with the game until a key)."""
    if (s.get("game") or {}).get("gs") != GS_PLAYING or not s.get("hero"):
        return False
    return bool(s["hero"].get("hero_accepting_input") or (s.get("pause") or {}).get("bench"))


def stand_up(link: OracleLink, button: str = "left", timeout_s: float = 10.0) -> dict:
    """Leave the bench (any direction gets Hornet up) and wait until she takes input."""
    s = link.wait_state(in_gameplay, timeout_s=timeout_s)
    if s["hero"].get("hero_accepting_input") and not s["pause"].get("bench"):
        return s
    return press_until(link, button, lambda s: s["hero"]["hero_accepting_input"] and not s["pause"]["bench"], wait_s=3.0)


def load_slot(link: OracleLink, slot: int = 1, timeout_s: float = 120.0) -> dict:
    """From the title screen: Start game -> save select -> slot `slot` (1-4, moving right from the first slot) ->
    wait until Hornet accepts input. Returns the first such STATE. No-op if already in gameplay."""
    s = link.wait_state(lambda s: s.get("game") is not None, timeout_s=timeout_s)  # no GameManager during boot
    if in_gameplay(s):
        return s
    if s["game"]["menu"] != MENU_SAVE_PROFILES:
        menu_ready(link, MENU_MAIN)
        press_until(link, "enter", lambda s: s["game"]["menu"] == MENU_SAVE_PROFILES)
    menu_ready(link, MENU_SAVE_PROFILES)
    for _ in range(slot - 1):
        tap(link, "right")
        time.sleep(0.35)
    press_until(link, "enter", lambda s: s["game"]["gs"] != 1 or s["game"]["menu"] != MENU_SAVE_PROFILES)
    return link.wait_state(in_gameplay, timeout_s=timeout_s)
