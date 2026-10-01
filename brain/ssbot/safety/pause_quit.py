"""Pause loop and quit sequence (DESIGN §3.7.5) as a per-frame state machine that turns observed cues into the keys
to hold, plus the pause / quit availability model and an oracle-mode cue adapter.

    pq = PauseQuit(PauseQuitConfig())
    pq.start(t, goal=GOAL_QUIT)                    # the supervisor entered PAUSE_PENDING
    every frame:
        keys = pq.step(cues)                       # cues: vision (screen mode / menu reader) or cues_from_state(s)
        mask = to_mask(keys, framing.BIT)          # the caller owns the button table (safety/ may not import ipc)
    pq.done, pq.outcome                            # QUIT, QUIT_EMULATED, UNPAUSED, DEAD, KILL_REQUESTED, ALERT
                                                   # (holding: PAUSED, GREYED, REFUSED)

Flow (§3.7.5): LOOP presses Pause for >= 2 frames and releases for >= 2 frames, unconditionally, until the earliest
pause cue (paused flag, the dimmer starting to darken, or a pause menu) or a death; then it stops at once and CONFIRMs
the PAUSE_MENU from the menu fade-in within confirm_window_s, else the cue was false and the loop resumes. Once
confirmed it reads the Quit item: available -> highlight "Quit to menu" -> Submit -> the "save and quit?" prompt
(default "No") -> Up to "Yes" -> Submit, reading the highlighted item before every Submit and never navigating by
count; greyed -> stays paused, refreshes the menu once through Options -> Back when the cause may be disableSaveQuit,
then waits for resolve_greyed(); after "Yes", still on the prompt with no fade-out after refusal_s = the Patch 4
refusal: stays paused, never unpauses blindly. Unpausing is Continue + Submit after the 0.3 s lockout, never Esc.
The machine only ever holds pause (in LOOP) or enter / up / down (on a ready menu): Esc also cancels menus, and in
menus Z submits and X / A cancel (m0:N16), so no game key may leak into them.

Timing facts this relies on:
- a Pause press while the pause gate is closed is dropped, not queued (m0:N12): the loop is the retry;
- Esc is both Pause and MenuCancel: once the 0.3 s real-time lockout after a pause has passed, any Esc unpauses
  (m0:C11, C12), so pressing must stop within 230 ms of the real pause (300 ms less one press in flight);
- the dimmer's alpha grows by unscaledDeltaTime x 3.2 from the pause frame (0.053 per 60 fps frame) up to 0.8
  (m0:C11); SendInput Esc -> first darkened capture p50 45.6 ms, max 49.6 ms (probe P8);
- human session 20260930_210337 (oracle STATE, gamepad): the pause lands in the frame of the press; the pause menu
  accepts input 8-9 frames later (133-150 ms: IsFadingMenu false, acceptingInput true); PauseAllowed returns 19 frames
  (317 ms) after the pause; Cancel unpaused 2 frames after the press; after an unpause, 12 frames (200 ms) of HideMenu
  without input and 18-19 frames (0.32 s) until a pause is possible again; Submit on Quit -> the prompt accepts input
  21 frames (350 ms) later; Submit on Yes -> PreventPause the next frame, the menu hides 4 frames later (the save),
  GameManager gone 158 frames (2.63 s) later;
- the Quit item is evaluated once per ShowMenu (greyed while disableSaveQuit or ScenePreloader.HasPendingOperations,
  MenuButtonSaveQuitListCondition) and a greyed item is skipped by Up / Down with wrap-around (m0:N17, C8);
- Patch 4: UIManager.ReturnToMainMenu returns silently while disablePause or disableSaveQuit, the prompt stays
  (m0 §2.4); a failed save shows SAVE_FAILED and the prompt again (m0:C9);
- mouse hover moves the highlight (probe P7): the final run keeps the mouse off the window.

Oracle mode (cues_from_state): STATE exports game.paused / gs / ui (UIState) / menu (MainMenuState) / fading
(IsFadingMenu), ts (timeScale), pause.blk (PauseGate bits), pause.dsq, pause.preload. It does not export the highlighted
item, the Quit item's interactable, the dimmer or menu alpha, or the quit fade; the adapter derives the Quit state from
dsq / preload (the condition the menu evaluates) and the quit start from PreventPause on the prompt, and reads the rest
from a proposed STATE "menu" section {sel, quit_ok, dim, alpha} when the oracle has it. Without "sel" the highlight is
unknown and a real quit never starts (no blind Submit): training uses emulate_quit, where a confirmed pause ends the
episode as QUIT_EMULATED. PreventPause on the prompt also stays set after a SAVE_FAILED (m0:C9), so in oracle mode a
retried Yes looks started at once; the machine still handles a second SAVE_FAILED, but a clean "quit fade started"
needs the proposed export.
"""
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from ssbot.safety import game_codes as gc

PAUSE, ENTER, UP, DOWN = "pause", "enter", "up", "down"
NO_KEYS: frozenset[str] = frozenset()

# PauseCues.menu
M_NONE, M_PAUSE, M_EXIT_PROMPT, M_OPTIONS, M_SAVE_FAILED, M_MAIN_MENU, M_LOADING, M_OTHER = (
    "none", "pause", "exit_prompt", "options", "save_failed", "main_menu", "loading", "other")
PAUSE_MENUS = frozenset({M_PAUSE, M_EXIT_PROMPT, M_OPTIONS, M_SAVE_FAILED})
MENU_ORDER = {M_PAUSE: ("continue", "options", "quit"), M_EXIT_PROMPT: ("yes", "no")}

GOAL_QUIT, GOAL_PAUSE = "QUIT", "PAUSE"
# outcomes
QUIT, QUIT_EMULATED, UNPAUSED, DEAD, KILL_REQUESTED, ALERT = (
    "QUIT", "QUIT_EMULATED", "UNPAUSED", "DEAD", "KILL_REQUESTED", "ALERT")
PAUSED, GREYED, REFUSED = "PAUSED", "GREYED", "REFUSED"
TERMINAL = frozenset({QUIT, QUIT_EMULATED, UNPAUSED, DEAD, KILL_REQUESTED, ALERT})
GREYED_UNPAUSE_EVADE, GREYED_KILL, GREYED_STAY = "UNPAUSE_EVADE", "KILL", "STAY"

LOCKOUT_S = 0.3        # WaitForSecondsRealtime(0.3f) after every pause and unpause (m0:C12)
DIM_RATE = 3.2         # UIManager.MENU_FADE_SPEED, alpha per real second
QUIT_AVAILABLE, QUIT_GREYED = "available", "greyed"


@dataclass(slots=True)
class PauseCues:
    """What the machine observes of one frame. t: real seconds when that frame was produced (monotonic)."""
    t: float
    paused: bool | None = None       # direct pause flag (oracle game.paused); None in vision mode
    dim: float | None = None         # modal dimmer alpha (0 .. 0.8); None when not measured
    frozen: bool | None = None       # world stopped (vision: no motion; oracle: timeScale 0; also true in hit-stop)
    menu: str = M_NONE               # M_* screen
    menu_ready: bool = False         # that menu has faded in and accepts input
    highlight: str | None = None     # "continue" / "options" / "quit", "yes" / "no", "back", "ok"; None: unreadable
    quit_state: str | None = None    # QUIT_AVAILABLE / QUIT_GREYED on a shown pause menu; None: unknown
    quit_cause: str | None = None    # "dsq" (disableSaveQuit) / "preload" / None (unknown) when greyed
    quitting: bool = False           # the quit save / fade-out has started
    dead: bool = False               # DEATH or PERMADEATH


@dataclass(slots=True)
class PauseQuitConfig:
    press_frames: int = 2
    release_frames: int = 2
    press_min_s: float = 0.030       # 2 frames at 60 fps less jitter slack (m0:N37: >= 2 sampled frames)
    release_min_s: float = 0.030
    dim_cue: float = 0.03            # dimmer alpha that is a pause cue (one 60 fps frame of fade = 0.053)
    confirm_window_s: float = 0.15   # earliest cue -> PAUSE_MENU confirmed within this, else a false cue
    budget_s: float = 0.23           # pressing must stop within this of the real pause
    loop_alert_s: float = 5.0        # still looping this long: alert (and keep looping)
    settle_frames: int = 2           # frames after a menu key's release before the highlight counts again
    stable_frames: int = 2           # the highlight must read the same on this many consecutive frames
    menu_wait_s: float = 1.5         # a menu expected after a Submit must be ready within this (measured 0.35 s)
    read_wait_s: float = 0.5         # Quit state / highlight unreadable this long on a ready menu: unknown
    max_nav: int = 10                # navigation taps toward one target
    max_submits: int = 3             # Submits of one step (a lost Submit is retried)
    max_save_retries: int = 2        # SAVE_FAILED -> OK -> Yes again
    refusal_s: float = 0.5           # after Yes, no quit start within this = Patch 4 refusal
    quit_wait_s: float = 10.0        # quit start -> main menu (measured 2.63 s)
    unpause_margin_s: float = 0.05   # Continue only this long after the estimated end of the lockout
    unpause_confirm_s: float = 0.5
    emulate_quit: bool = False       # training: a confirmed pause ends a GOAL_QUIT run as QUIT_EMULATED
    emulate_wait_s: float = 0.5      # ... after reading the Quit state for at most this long
    refresh_greyed: bool = True      # greyed by disableSaveQuit or unknown cause: Options -> Back once


@dataclass(slots=True)
class _Tap:
    key: str
    t0: float
    down: bool = True
    n: int = 0
    done: bool = False


@dataclass(slots=True)
class _Step:
    menu: str
    target: str
    expect: str            # menu expected after the Submit, or "quitting" / "unpaused"
    navs: int = 0
    submits: int = 0


def loop_budget_ok(detect_max_s: float, input_latency_max_s: float, cfg: PauseQuitConfig | None = None) -> bool:
    """Worst case from the real pause to the last Pause press reaching the game: a press emitted just before the cue is
    seen lands detect + input latency after the pause. It must stay within the budget (0.3 s lockout - one press)."""
    cfg = cfg or PauseQuitConfig()
    return detect_max_s + input_latency_max_s <= cfg.budget_s


def to_mask(keys: Iterable[str], bit: Mapping[str, int]) -> int:
    """Key names -> ACTION button mask, with the caller's bit table (ssbot.ipc.framing.BIT)."""
    m = 0
    for k in keys:
        m |= 1 << bit[k]
    return m


class PauseQuit:
    def __init__(self, cfg: PauseQuitConfig | None = None):
        self.cfg = cfg or PauseQuitConfig()
        self.state = "IDLE"
        self.outcome: str | None = None
        self.goal = GOAL_QUIT
        self.alert = False
        self.log: list[tuple[float, str, str]] = []
        self.t_start: float | None = None
        self.t_cue: float | None = None           # earliest pause cue seen
        self.t_pause_est: float | None = None     # estimated real pause time
        self.t_confirm: float | None = None
        self.last_press_t: float | None = None    # last frame a Pause press began
        self.presses = 0
        self.false_cues = 0
        self.unexpected_unpauses = 0
        self.quit_state_seen: str | None = None
        self.unpause_lockout_until: float | None = None
        self._tap: _Tap | None = None
        self._plan: list[_Step] = []
        self._phase = ""
        self._phase_t = 0.0
        self._settle = 0
        self._stable = 0
        self._last_hl: str | None = None
        self._read_t = 0.0
        self._refreshed = False
        self._save_retries = 0
        self._after_plan = ""

    # ---- control ------------------------------------------------------------------------------------------------

    def start(self, t: float, goal: str = GOAL_QUIT) -> None:
        """Enter the pause loop (PAUSE_PENDING). Restarting a finished machine is allowed."""
        self.goal = goal
        self.state = "LOOP"
        self.outcome = None
        self.alert = False
        self.t_start = t
        self.t_cue = self.t_pause_est = self.t_confirm = None
        self._tap = None
        self._plan = []
        self._refreshed = False
        self._save_retries = 0
        self._note(t, "start", goal)

    def request_quit(self, t: float) -> bool:
        """From a held pause (goal PAUSE, greyed or refused): read the Quit item again and quit if it is available."""
        if self.state not in ("HOLD", "GREYED", "REFUSED"):
            return False
        self.goal = GOAL_QUIT
        if self.state == "REFUSED":
            self._begin_plan(t, [_Step(M_EXIT_PROMPT, "yes", "quitting")], "quit")
        else:
            self._enter(t, "READ_QUIT")
        return True

    def request_unpause(self, t: float) -> bool:
        """Continue + Submit (never Esc) once the lockout has passed. The caller ran the frozen-state check."""
        if self.state not in ("HOLD", "GREYED", "REFUSED"):
            return False
        self._enter(t, "UNPAUSE")
        return True

    def resolve_greyed(self, t: float, choice: str) -> bool:
        """§3.7.5 step 4, greyed: UNPAUSE_EVADE (the frozen check passed: unpause, evade out of the room, pause again),
        KILL (D13 enabled and its conditions hold; the kill itself is safety/last_resort), or STAY (alert, wait)."""
        if self.state != "GREYED":
            return False
        if choice == GREYED_UNPAUSE_EVADE:
            return self.request_unpause(t)
        if choice == GREYED_KILL:
            self._finish(t, KILL_REQUESTED)
            return True
        self.alert = True
        self._note(t, "greyed_stay", "")
        return True

    @property
    def done(self) -> bool:
        return self.outcome in TERMINAL

    @property
    def pressing(self) -> bool:
        return self.state == "LOOP"

    # ---- per frame ------------------------------------------------------------------------------------------------

    def step(self, c: PauseCues) -> frozenset[str]:
        st = self.state
        if st in ("IDLE", "DONE"):
            return NO_KEYS
        if c.dead:
            self._finish(c.t, DEAD)
            return NO_KEYS
        if st == "LOOP":
            return self._loop(c)
        if st == "CONFIRM":
            return self._confirm(c)
        if st == "QUITTING":
            if c.menu == M_MAIN_MENU:
                self._finish(c.t, QUIT)
            elif c.menu == M_SAVE_FAILED:
                self._save_failed(c)
            elif c.t - self._phase_t > self.cfg.quit_wait_s:
                self._fail(c.t, "main menu not reached after the quit started")
            return NO_KEYS
        if self._unpaused(c) and not (st == "MENU" and self._plan and self._plan[0].expect == "unpaused"):
            self.unexpected_unpauses += 1
            self.alert = True
            self._note(c.t, "unexpected_unpause", st)
            self.state = "LOOP"           # the world runs: pause again (presses are dropped for the 0.3 s lockout)
            self.t_cue = self.t_pause_est = self.t_confirm = None
            self._tap = None
            self._plan = []
            return self._loop(c)
        if st == "READ_QUIT":
            return self._read_quit(c)
        if st == "UNPAUSE":
            return self._unpause_wait(c)
        if st == "MENU":
            return self._menu(c)
        return NO_KEYS   # HOLD, GREYED, REFUSED: stay paused, press nothing

    # ---- states ---------------------------------------------------------------------------------------------------

    def _hint(self, c: PauseCues) -> bool:
        return (c.paused is True or c.menu in PAUSE_MENUS
                or (c.dim is not None and c.dim >= self.cfg.dim_cue))

    def _loop(self, c: PauseCues) -> frozenset[str]:
        cfg = self.cfg
        if self._hint(c):
            self.t_cue = c.t
            back = max(0.0, c.dim / DIM_RATE - 1 / 60) if c.dim else 0.0
            self.t_pause_est = c.t - back
            self.state = "CONFIRM"
            self._tap = None
            self._note(c.t, "cue", f"paused={c.paused} dim={c.dim} menu={c.menu}")
            return NO_KEYS
        if self.t_start is not None and c.t - self.t_start > cfg.loop_alert_s and not self.alert:
            self.alert = True
            self._note(c.t, "loop_alert", f"{c.t - self.t_start:.1f} s")
        keys = self._tap_keys(c.t) if self._tap is not None and not self._tap.done else NO_KEYS
        if self._tap is None or self._tap.done:
            self._tap = _Tap(PAUSE, c.t)
            self.presses += 1
            self.last_press_t = c.t
            keys = self._tap_keys(c.t)
        return keys

    def _confirm(self, c: PauseCues) -> frozenset[str]:
        if c.paused is True or c.menu in PAUSE_MENUS:
            self.t_confirm = c.t
            self._note(c.t, "confirmed", c.menu)
            self._enter(c.t, "READ_QUIT")
            return NO_KEYS
        if c.t - self.t_cue > self.cfg.confirm_window_s:
            self.false_cues += 1
            self._note(c.t, "false_cue", "")
            self.state = "LOOP"
            self.t_cue = self.t_pause_est = None
            return self._loop(c)
        return NO_KEYS

    def _read_quit(self, c: PauseCues) -> frozenset[str]:
        cfg = self.cfg
        emulate = cfg.emulate_quit and self.goal == GOAL_QUIT
        ready = c.menu == M_PAUSE and c.menu_ready
        if emulate and (c.t - self._phase_t > cfg.emulate_wait_s or (ready and c.quit_state is not None)):
            self.quit_state_seen = c.quit_state if ready else None
            self._finish(c.t, QUIT_EMULATED)
            return NO_KEYS
        if not ready:
            if c.t - self._phase_t > cfg.menu_wait_s:
                self._fail(c.t, "pause menu not ready")
            return NO_KEYS
        if c.quit_state is None and c.t - self._phase_t < cfg.read_wait_s:
            return NO_KEYS
        self.quit_state_seen = c.quit_state or "unknown"
        if self.goal == GOAL_PAUSE:
            self.outcome = PAUSED
            self._enter(c.t, "HOLD")
            return NO_KEYS
        if c.quit_state == QUIT_AVAILABLE:
            self._begin_plan(c.t, [_Step(M_PAUSE, "quit", M_EXIT_PROMPT), _Step(M_EXIT_PROMPT, "yes", "quitting")],
                             "quit")
            return self._menu(c)
        if cfg.refresh_greyed and not self._refreshed and c.quit_cause in (None, "dsq"):
            self._refreshed = True
            self._note(c.t, "greyed_refresh", str(c.quit_cause))
            self._begin_plan(c.t, [_Step(M_PAUSE, "options", M_OPTIONS), _Step(M_OPTIONS, "back", M_PAUSE)],
                             "refresh")
            return self._menu(c)
        self.outcome = GREYED
        self.alert = True
        self._note(c.t, "greyed", str(c.quit_cause))
        self._enter(c.t, "GREYED")
        return NO_KEYS

    def _unpause_wait(self, c: PauseCues) -> frozenset[str]:
        """Continue is refused during the lockout and while the menu is not ready (PauseMenuButton.OnSubmit checks
        PauseAllowed; m0 §2.4), so wait for both. From the quit prompt: "No" first, back to the pause menu."""
        lockout_end = (self.t_pause_est if self.t_pause_est is not None else self._phase_t) + LOCKOUT_S
        ready = c.menu in (M_PAUSE, M_EXIT_PROMPT) and c.menu_ready
        if c.t < lockout_end + self.cfg.unpause_margin_s or not ready:
            if c.t - self._phase_t > LOCKOUT_S + self.cfg.menu_wait_s and not ready:
                self._fail(c.t, "pause menu not ready for Continue")
            return NO_KEYS
        plan = [_Step(M_PAUSE, "continue", "unpaused")]
        if c.menu == M_EXIT_PROMPT:
            plan.insert(0, _Step(M_EXIT_PROMPT, "no", M_PAUSE))
        self._begin_plan(c.t, plan, "unpause")
        return self._menu(c)

    def _menu(self, c: PauseCues) -> frozenset[str]:
        cfg = self.cfg
        s = self._plan[0]
        ph = self._phase
        if ph == "wait":
            if c.menu == s.menu and c.menu_ready:
                self._read_phase(c.t)
                ph = "read"
            else:
                if c.t - self._phase_t > cfg.menu_wait_s:
                    self._fail(c.t, f"menu {s.menu} not ready")
                return NO_KEYS
        if ph in ("read", "nav") and not (c.menu == s.menu and c.menu_ready):
            self._phase, self._phase_t = "wait", c.t     # the menu went away under us: wait for it again
            return NO_KEYS
        if ph == "read":
            if self._settle > 0:
                self._settle -= 1
                return NO_KEYS
            hl = c.highlight
            if hl is None:
                if c.t - self._read_t > cfg.read_wait_s:
                    self._fail(c.t, f"highlight unreadable on {s.menu}")
                return NO_KEYS
            self._stable = self._stable + 1 if hl == self._last_hl else 1
            self._last_hl = hl
            if self._stable < cfg.stable_frames:
                return NO_KEYS
            if hl == s.target:
                s.submits += 1
                self._note(c.t, "submit", f"{s.menu}:{hl}")
                self._phase, self._tap = "submit", _Tap(ENTER, c.t)
                return self._tap_keys(c.t)
            if s.navs >= cfg.max_nav:
                self._fail(c.t, f"{s.target} not reached on {s.menu} (at {hl})")
                return NO_KEYS
            s.navs += 1
            key = _direction(s.menu, hl, s.target)
            self._note(c.t, "nav", f"{s.menu}:{hl}->{s.target} {key}")
            self._phase, self._tap = "nav", _Tap(key, c.t)
            return self._tap_keys(c.t)
        if ph == "nav":
            keys = self._tap_keys(c.t)
            if self._tap.done:
                self._read_phase(c.t)
            return keys
        if ph == "submit":
            keys = self._tap_keys(c.t)
            if self._tap.done:
                self._phase, self._phase_t = "effect", c.t
            return keys
        return self._effect(c, s)

    def _effect(self, c: PauseCues, s: _Step) -> frozenset[str]:
        cfg = self.cfg
        waited = c.t - self._phase_t
        if s.expect == "quitting":
            if c.quitting or c.menu in (M_MAIN_MENU, M_LOADING):
                self._note(c.t, "quitting", "")
                self._plan.pop(0)
                self._enter(c.t, "QUITTING")
                return NO_KEYS
            if c.menu == M_SAVE_FAILED:
                self._save_failed(c)
                return NO_KEYS
            if waited > cfg.refusal_s and c.menu == M_EXIT_PROMPT:
                self.outcome = REFUSED
                self.alert = True
                self._note(c.t, "refused", "Patch 4: still on the prompt")
                self._enter(c.t, "REFUSED")
            return NO_KEYS
        if s.expect == "unpaused":
            if self._unpaused(c):
                self.unpause_lockout_until = c.t + LOCKOUT_S
                self._finish(c.t, UNPAUSED)
                return NO_KEYS
        elif c.menu == s.expect and c.menu_ready:
            self._plan.pop(0)
            if self._plan:
                self._phase, self._phase_t = "wait", c.t
                return self._menu(c)
            if self._after_plan == "refresh":
                self._enter(c.t, "READ_QUIT")
                return NO_KEYS
            self._fail(c.t, f"plan {self._after_plan} ended without its effect")
            return NO_KEYS
        if waited > (cfg.unpause_confirm_s if s.expect == "unpaused" else cfg.menu_wait_s):
            if c.menu == s.menu and c.menu_ready and s.submits < cfg.max_submits:
                self._note(c.t, "submit_lost", f"{s.menu}:{s.target}")
                self._read_phase(c.t)        # the Submit was dropped: read the highlight again, then retry
            else:
                self._fail(c.t, f"no effect of {s.menu}:{s.target} (now {c.menu})")
        return NO_KEYS

    def _save_failed(self, c: PauseCues) -> None:
        """SAVE_FAILED during the quit (m0:C9): the world stays frozen and Esc / Continue do nothing; OK brings the
        prompt back, then Yes again, a bounded number of times, else alert and wait."""
        if self._save_retries >= self.cfg.max_save_retries:
            self._fail(c.t, "SAVE_FAILED again")
            return
        self._save_retries += 1
        self._note(c.t, "save_failed", str(self._save_retries))
        self._begin_plan(c.t, [_Step(M_SAVE_FAILED, "ok", M_EXIT_PROMPT), _Step(M_EXIT_PROMPT, "yes", "quitting")],
                         "quit")

    # ---- helpers --------------------------------------------------------------------------------------------------

    def _unpaused(self, c: PauseCues) -> bool:
        """Evidence that the world runs: the oracle's flag, or (vision) no menu and a moving world."""
        if c.paused is not None:
            return c.paused is False and c.menu not in PAUSE_MENUS
        return c.menu == M_NONE and c.frozen is False

    def _tap_keys(self, t: float) -> frozenset[str]:
        """Hold the current tap's key on >= press_frames frames spanning >= press_min_s, then keep it released as long.
        On the frame the release is complete the tap is done and holds nothing (a next tap may start that frame)."""
        tap, cfg = self._tap, self.cfg
        if tap.down:
            if tap.n >= cfg.press_frames and t - tap.t0 >= cfg.press_min_s:
                tap.down, tap.n, tap.t0 = False, 0, t
            else:
                tap.n += 1
                return frozenset((tap.key,))
        elif tap.n >= cfg.release_frames and t - tap.t0 >= cfg.release_min_s:
            tap.done = True
            return NO_KEYS
        tap.n += 1
        return NO_KEYS

    def _read_phase(self, t: float) -> None:
        self._phase, self._phase_t, self._read_t = "read", t, t
        self._settle, self._stable, self._last_hl = self.cfg.settle_frames, 0, None

    def _begin_plan(self, t: float, plan: list[_Step], name: str) -> None:
        self._plan, self._after_plan = plan, name
        self.state = "MENU"
        self._phase, self._phase_t = "wait", t

    def _enter(self, t: float, state: str) -> None:
        self.state = state
        self._phase_t = t
        self._note(t, "state", state)

    def _finish(self, t: float, outcome: str) -> None:
        self.outcome = outcome
        self.state = "DONE"
        self._note(t, "done", outcome)

    def _fail(self, t: float, why: str) -> None:
        """Stay paused and alert; never press anything to recover blindly."""
        self.alert = True
        self._note(t, "fail", why)
        self._finish(t, ALERT)

    def _note(self, t: float, kind: str, detail: str) -> None:
        self.log.append((round(t, 4), kind, detail))


def _direction(menu: str, at: str, target: str) -> str:
    """Up or Down toward target on a menu with a known order (wrap-around; a greyed item is skipped by the game, which
    only shortens the way). Unknown order (Options): Up for "back", the last item, else Down. The highlight is read
    again after every tap, so a wrong guess costs taps, never a wrong Submit."""
    order = MENU_ORDER.get(menu)
    if not order or at not in order or target not in order:
        return UP if target == "back" else DOWN
    i, j, n = order.index(at), order.index(target), len(order)
    return DOWN if (j - i) % n <= (i - j) % n else UP


# ---- availability (§3.7.5 "pause_available / quit_available") ----------------------------------------------------

@dataclass(slots=True, frozen=True)
class Availability:
    pause: bool
    quit: bool
    reason: str = ""


def availability(screen: str, t: float, *, unpause_lockout_until: float = 0.0, blocked_until: float = 0.0,
                 p_pause: float | None = None, p_quit: float | None = None, min_p: float = 0.99) -> Availability:
    """The runtime estimate: gameplay screen; not inside the 0.3 s after an unpause; not inside a detected blocker
    (a freeze start or hit plus its measured blocked duration); and the quit map's P(pause) / P(quit) for this scene
    and state at least min_p (no data = not available)."""
    if screen != "GAMEPLAY":
        return Availability(False, False, f"screen {screen}")
    if t < unpause_lockout_until:
        return Availability(False, False, "unpause lockout")
    if t < blocked_until:
        return Availability(False, False, "blocked (freeze / hit)")
    if p_pause is None or p_pause < min_p:
        return Availability(False, False, f"quit map P(pause) {p_pause}")
    if p_quit is None or p_quit < min_p:
        return Availability(True, False, f"quit map P(quit) {p_quit}")
    return Availability(True, True)


def availability_from_state(s: dict) -> Availability:
    """Oracle mode, exact: a Pause press pauses now (pause.blk == 0) and the Quit item would be enabled."""
    p = s.get("pause")
    if not p:
        return Availability(False, False, "no game")
    blk = p.get("blk") or 0
    if blk:
        return Availability(False, False, "+".join(gc.blk_names(blk)))
    if p.get("dsq") or p.get("preload"):
        return Availability(True, False, "disableSaveQuit" if p.get("dsq") else "scene preload pending")
    return Availability(True, True)


# ---- oracle-mode cue adapter --------------------------------------------------------------------------------------

_SEL_NAMES = {"continue", "options", "quit", "yes", "no", "back", "ok"}
_DEATH_EVENTS = {"hero_dead", "player_dead", "permadeath_dead"}


def cues_from_state(s: dict, qpc_freq: float = 1e7) -> PauseCues:
    """PauseCues from one oracle STATE (training only). t is the frame's end-of-frame QPC in seconds."""
    t = (s.get("q") or 0) / qpc_freq
    g = s.get("game")
    if g is None:   # no GameManager: the Save & Quit gap (or a boot); the quit is under way
        return PauseCues(t=t, menu=M_LOADING, quitting=True)
    p = s.get("pause") or {}
    blk = p.get("blk") or 0
    gs, ui, ms = g.get("gs"), g.get("ui"), g.get("menu")
    if gs == gc.GS_MAIN_MENU:
        menu = M_MAIN_MENU
    elif blk & gc.BLK_MSG_CANVAS:   # GenericMessageCanvas: SAVE_FAILED (a bench save outside a pause: §3.6.8)
        menu = M_SAVE_FAILED if ui == gc.UI_PAUSED else M_OTHER
    elif ui == gc.UI_PAUSED:
        menu = {gc.MENU_PAUSE_MENU: M_PAUSE, gc.MENU_EXIT_PROMPT: M_EXIT_PROMPT,
                gc.MENU_OPTIONS_MENU: M_OPTIONS}.get(ms, M_OTHER)
    else:
        menu = M_NONE
    ready = ui == gc.UI_PAUSED and not g.get("fading") and not blk & gc.BLK_NOT_ACCEPTING_INPUT
    extra = s.get("menu") or {}       # proposed oracle section (see the module docstring)
    sel = extra.get("sel")
    highlight = sel if sel in _SEL_NAMES else None
    quit_state = quit_cause = None
    if menu == M_PAUSE:
        if "quit_ok" in extra:
            quit_state = QUIT_AVAILABLE if extra["quit_ok"] else QUIT_GREYED
        else:   # MenuButtonSaveQuitListCondition.IsFulfilled, evaluated on frozen state
            quit_state = QUIT_GREYED if p.get("dsq") or p.get("preload") else QUIT_AVAILABLE
        if quit_state == QUIT_GREYED:
            quit_cause = "dsq" if p.get("dsq") else "preload" if p.get("preload") else None
    dead = g.get("pd_mode") == gc.PD_DEAD or any(ev.get("k") in _DEATH_EVENTS for ev in s.get("ev") or ())
    ts = s.get("ts")
    return PauseCues(
        t=t, paused=bool(g.get("paused")), dim=extra.get("dim"), frozen=None if ts is None else ts == 0,
        menu=menu, menu_ready=ready, highlight=highlight, quit_state=quit_state, quit_cause=quit_cause,
        quitting=menu == M_EXIT_PROMPT and bool(blk & gc.BLK_PAUSE_LOCKOUT), dead=dead)
