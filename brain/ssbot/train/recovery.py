"""Harness recovery on training instances (combat_run workers, run_episode): find where a game the harness did not
expect to be is (paused, a pause sub-menu, a title sub-menu) from the oracle STATE, and bring it back with the fewest
verified key taps, or say why not, so the worker ends the episode as HARNESS_FAIL and goes on instead of stalling.
Training profile only: the formal run's pause / quit path (safety.pause_quit, the supervisor) is not used or changed
here and gains no key.

    w = where(link.state)                 # "game", "pause_menu", "exit_prompt", "pause_submenu", "title", ...
    cause = pause_cause(s)                # why a STATE shows a pause the harness did not ask for
    ok, steps = resume(link)              # paused (any pause menu) -> unpaused, Continue + Submit, never Esc
    ok, steps = title_home(link)          # a title sub-menu (Options, Game options, ...) -> the main menu, Esc only

Failures seen (docs/facts/1.0.30000/pause_quit.md section 11):
- "paused unasked": 60 of the 61 HARNESS_FAILs of 2026-10-02 .. 06 were the oracle's brain-lost watchdog (STATE
  act.lost, the Pause bit in the injected mask on the pause frame, the last ACTION applied 13-15 frames earlier: the
  worker sent no ACTION for 250 ms); the other one (20261006_065605_Lace1_data i0) paused with no Pause key read, no
  lost brain and focus (InputHandler.ControllerDetached is the one other path to PAUSED). unpause() pressed Submit
  blindly, which on a highlight other than Continue opens the Options menu (the pause menu takes mouse hover, probe P7).
- the title's Game options (20261005_164501_..._2 i1, menuState 12 on Menu_Title): load_slot's retried Enter on a main
  menu whose highlight was Options went Main -> Options -> Game options -> a setting; the worker waited 2 x 60 s for
  the main menu and died. A person pressed Esc.

Navigation facts: the pause menu is Continue / Options / Quit, top to bottom, wrapping (MenuButtonList); the exit
prompt lists Yes above No; on Options and its sub-menus the oracle names only Back (MenuExporter "back"), which Down
reaches (pause_quit's UNLABELLED rule); every pause-side Submit lands only on a role read from the STATE ("continue",
"back", "no"); on the title Esc is MenuCancel only (InputHandler toggles a pause only in PLAYING / PAUSED), and Esc
from a title sub-menu goes back one level (UIGoBack); Esc on the main menu itself opens the quit prompt, so it is
never pressed there.
"""
import time

from ssbot.ipc.framing import mask

GS_MAIN_MENU, GS_PLAYING, GS_PAUSED = 1, 4, 5          # GlobalEnums.GameState
UI_PAUSED = 5                                          # GlobalEnums.UIState
# GlobalEnums.MainMenuState
MENU_LOGO, MENU_MAIN, MENU_OPTIONS, MENU_SAVE_PROFILES = 0, 1, 2, 6
MENU_EXIT_PROMPT, MENU_ACHIEVEMENTS, MENU_QUIT_GAME_PROMPT = 10, 13, 14
MENU_PAUSE, MENU_PLAY_MODE, MENU_EXTRAS, MENU_ENGAGE = 17, 18, 19, 22
# the main menu's items top to bottom (MainMenuOptions; Achievements / Extras can be hidden per platform): the menu a
# Submit on each opens
TITLE_ITEM = {MENU_SAVE_PROFILES: 0, MENU_PLAY_MODE: 0, MENU_OPTIONS: 1, MENU_ACHIEVEMENTS: 2, MENU_EXTRAS: 3,
              MENU_QUIT_GAME_PROMPT: 4}
BLK_PAUSE_LOCKOUT, BLK_NOT_ACCEPTING_INPUT = 4, 32      # STATE pause.blk (PauseGate)
PAUSE_BIT = mask("pause")

TAP_FRAMES = 3          # one-shot press (hold_frames > 0: no brain-lost watchdog), >= 2 frames and >= 34 ms
SETTLE_FRAMES = 12      # a menu's reaction is read this many frames after the tap's target frame
READY_ALPHA = 0.99      # the pause menu's canvas has faded in
MAX_NAV = 24            # Up / Down / Esc taps per recovery (a settings sub-menu can list a dozen items above Back)
SEL_WAIT_S = 1.5        # a ready menu with nothing named highlighted: wait this long before navigating anyway

PAUSED_PLACES = ("pause_menu", "exit_prompt", "pause_submenu", "pause_opening")


def _game(s: dict | None) -> dict:
    return (s or {}).get("game") or {}


def is_paused(s: dict | None) -> bool:
    g = _game(s)
    return bool(g.get("paused")) or g.get("gs") == GS_PAUSED or (g.get("gs") != GS_MAIN_MENU and g.get("ui") == UI_PAUSED)


def where(s: dict | None) -> str:
    """Where the game is, for the harness:
    "no_game" (no GameManager: boot, or the Save & Quit gap), "title" (the main menu), "save_select",
    "title_submenu" (Options and its sub-menus, Achievements, Extras, the quit-game prompt, the play-mode menu),
    "title_other" (logo / engage screen), "pause_opening" (paused, the menu still fading in or ignoring input: wait),
    "pause_menu", "exit_prompt", "pause_submenu" (Options or deeper while paused), "game" (anything else: gameplay,
    a cutscene, a load)."""
    g = _game(s)
    if not g:
        return "no_game"
    gs, menu = g.get("gs"), g.get("menu")
    if gs == GS_MAIN_MENU:
        if menu == MENU_MAIN:
            return "title"
        if menu == MENU_SAVE_PROFILES:
            return "save_select"
        if menu in (MENU_LOGO, MENU_ENGAGE, None):
            return "title_other"
        return "title_submenu"
    if not is_paused(s):
        return "game"
    m = (s or {}).get("menu") or {}
    blk = ((s or {}).get("pause") or {}).get("blk") or 0
    # menuState is stale for the first frames of a pause (ShowMenu sets it after the fade-in: 8 frames in the person's
    # session), and the menus take no input while they fade or GoToPauseMenu runs
    if (g.get("fading") or m.get("ignore_unpause") or blk & BLK_NOT_ACCEPTING_INPUT
            or (menu == MENU_PAUSE and m and (m.get("alpha") or 0.0) < READY_ALPHA)):
        return "pause_opening"
    if menu == MENU_PAUSE:
        return "pause_menu"
    if menu == MENU_EXIT_PROMPT:
        return "exit_prompt"
    return "pause_submenu"


def pause_cause(s: dict | None) -> str:
    """Why the game paused, from the first paused STATE (its "act" section: the oracle's injected keys and the
    brain-lost watchdog; "input": what the game read): the watchdog (the worker sent no ACTION for 250 ms and 6
    frames, ActionScheduler), a Pause key the harness did not inject (a person's Esc, a gamepad's Start), or no Pause
    key at all (InputHandler.ControllerDetached: a gamepad that went away pauses the game)."""
    s = s or {}
    a = s.get("act") or {}
    if a.get("lost") or (a.get("mask") or 0) & PAUSE_BIT:
        applied = a.get("applied")
        age = f", last ACTION applied {s.get('f') - applied} frames before" if isinstance(applied, int) and \
            isinstance(s.get("f"), int) else ""
        return f"brain-lost watchdog{age}"
    if ((s.get("input") or {}).get("mask") or 0) & PAUSE_BIT:
        return "a Pause key the harness did not press"
    return "no Pause key (a gamepad detach?)"


def tap(link, key: str, hold_frames: int = TAP_FRAMES) -> int:
    """One-shot press two frames ahead; returns the frame its effect can be read from."""
    target = link.frame + 2
    link.act(target, mask(key), hold_frames=hold_frames)
    return target + hold_frames + SETTLE_FRAMES


def _wait_frame(link, f: int, timeout_s: float = 3.0) -> dict:
    try:
        return link.wait_state(lambda s: s["f"] >= f, timeout_s=timeout_s)
    except TimeoutError:
        return link.state or {}


def _release(link) -> None:
    try:
        link.rpc("input.release", timeout_s=10)
    except Exception:  # noqa: BLE001 - best effort: a closed link or a slow oracle must not mask the recovery's result
        pass


def _pause_key(w: str, sel) -> str:
    """The one key that moves a paused game towards Continue + Submit from (where, highlight)."""
    if w == "pause_menu":
        return "enter" if sel == "continue" else "up"           # Quit -> Options -> Continue
    if w == "exit_prompt":
        return "enter" if sel == "no" else "down"               # Yes above No
    return "enter" if sel == "back" else "down"                 # Options and deeper: Back by Down


def resume(link, timeout_s: float = 30.0, log=None) -> tuple[bool, list[str]]:
    """Unpause a paused game from any pause menu: Back out of Options (and deeper) and the exit prompt (No), then
    Continue + Submit once the 0.3 s lockout has passed; never Esc (it is also MenuCancel and toggles the pause from
    any screen, unpause_check), never a Submit on a highlight not read as continue / back / no. One tap at a time, each
    read SETTLE_FRAMES after it lands. input.release first and last: the oracle stops treating the link as driving, so
    its brain-lost watchdog cannot pause the game again 250 ms after the last tap. Returns (unpaused, the steps taken);
    not paused at all is (True, [])."""
    steps: list[str] = []
    deadline = time.monotonic() + timeout_s
    navs = 0
    sel_since = None
    if where(link.state) in PAUSED_PLACES:
        _release(link)
    try:
        while time.monotonic() < deadline and not getattr(link, "closed", False):
            s = link.state or {}
            w = where(s)
            if w not in PAUSED_PLACES:
                return True, steps
            if w == "pause_opening":
                _wait_frame(link, (s.get("f") or 0) + 2, timeout_s=1.0)
                continue
            sel = ((s.get("menu") or {}).get("sel"))
            blk = (s.get("pause") or {}).get("blk") or 0
            key = _pause_key(w, sel)
            if key == "enter" and w == "pause_menu" and blk & BLK_PAUSE_LOCKOUT:
                _wait_frame(link, (s.get("f") or 0) + 2, timeout_s=1.0)   # Continue is ignored in the lockout
                continue
            if sel is None and w != "pause_submenu":
                # nothing highlighted yet (a Submit deselects; ShowMenu highlights after its fade): wait a little
                sel_since = sel_since if sel_since is not None else time.monotonic()
                if time.monotonic() - sel_since < SEL_WAIT_S:
                    _wait_frame(link, (s.get("f") or 0) + 2, timeout_s=1.0)
                    continue
            sel_since = None
            if key != "enter":
                navs += 1
                if navs > MAX_NAV:
                    steps.append(f"gave up on {w} (highlight {sel})")
                    return False, steps
            steps.append(f"{w}:{sel}:{key}")
            if log:
                log(f"recovery: {w}, highlight {sel}: {key}")
            _wait_frame(link, tap(link, key))
        s = link.state or {}
        return where(s) not in PAUSED_PLACES, steps
    finally:
        _release(link)


def title_home(link, timeout_s: float = 20.0, log=None) -> tuple[bool, list[str]]:
    """From a title sub-menu (Options, Game options, ..., Achievements, Extras, the quit-game prompt) back to the main
    menu with Esc (MenuCancel: one level back per tap, UIGoBack; on the title InputHandler never toggles a pause).
    Never pressed on the main menu itself (its Cancel opens the quit-game prompt). Returns (on the main menu or the
    save select, the steps)."""
    steps: list[str] = []
    deadline = time.monotonic() + timeout_s
    try:
        while time.monotonic() < deadline and not getattr(link, "closed", False):
            s = link.state or {}
            w = where(s)
            if w != "title_submenu":
                return w in ("title", "save_select"), steps
            if _game(s).get("fading"):
                _wait_frame(link, (s.get("f") or 0) + 2, timeout_s=1.0)
                continue
            if len(steps) >= MAX_NAV:
                return False, steps
            menu = _game(s).get("menu")
            steps.append(f"title menu {menu}: pause")
            if log:
                log(f"recovery: title menu {menu}: Esc")
            f_ready = tap(link, "pause")
            try:   # the menu changes after its fade-out: wait for the change, not a fixed frame count
                link.wait_state(lambda s: (s.get("game") or {}).get("menu") != menu and s["f"] >= f_ready,
                                timeout_s=3.0)
            except TimeoutError:
                pass
        return where(link.state) in ("title", "save_select"), steps
    finally:
        _release(link)
