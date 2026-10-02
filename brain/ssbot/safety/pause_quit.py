"""Pause loop and quit sequence (DESIGN §3.7.5) as a per-frame state machine that turns observed cues into the keys
to hold, plus the pause / quit availability model and an oracle-mode cue adapter.

    pq = PauseQuit(PauseQuitConfig(input_latency_max_s=..., obs_latency_max_s=...))
    pq.start(now, goal=GOAL_QUIT)                  # the supervisor entered PAUSE_PENDING
    every frame:
        keys = pq.step(cues, now)                  # cues: vision (screen mode / menu reader) or cues_from_state(s);
                                                   # now: the clock the keys are emitted on (cues.t's clock)
        mask = to_mask(keys, framing.BIT)          # the caller owns the button table (safety/ may not import ipc)
    pq.done, pq.outcome                            # QUIT, QUIT_EMULATED[_GREYED|_UNKNOWN], REFUSED_EMULATED, UNPAUSED,
                                                   # DEAD, KILL_REQUESTED, ALERT (holding: PAUSED, GREYED, REFUSED)

Flow (§3.7.5): LOOP presses Pause for >= 2 frames and >= 34 ms, releases as long, unconditionally, until the earliest
pause cue or a death; then it stops at once and CONFIRMs the pause before the lockout ends, else the cue was false and
the loop resumes. Once confirmed it reads the Quit item: available -> highlight "Quit to menu" -> Submit -> the "save
and quit?" prompt (default "No") -> Up to "Yes" -> Submit; greyed -> stays paused, refreshes the menu once through
Options -> Back when the cause may be disableSaveQuit, then waits for resolve_greyed(); after "Yes", still on the prompt
with no fade-out refusal_s after the Submit took effect = the Patch 4 refusal: stays paused, never unpauses blindly.
Unpausing is Continue + Submit after the 0.3 s lockout, never Esc. The machine only ever holds pause (in LOOP) or
enter / up / down (on a ready menu): Esc also cancels menus, and in menus Z submits and X / A cancel (m0:N16).

Cues. The earliest cue is one of: the oracle's paused flag; a pause menu over a frozen world (vision; with the dimmer
up when it is measured); the dimmer's alpha-rise signature, alpha >= dim_cue after dim_rise_frames consecutive rises
of about DIM_RATE x the capture interval (0.053 per 60 fps frame; m0:C11). A dark room, a fade or a low-health effect
reads as a constant or differently rising "dim" and never makes a cue, and an additive dark baseline does not hide a
real pause (the rise is relative). A cue source that proved false (no confirmation within confirm_window_s of capture
time) is ignored until it clears (dim stops rising, the menu reading changes, the flag drops), so a persistent false
cue cannot stop the loop; loop_alert_s and false_cue_alert raise the alert from LOOP and CONFIRM alike.

Latency. Every observation has a capture time t, every key an emission time now (the same clock). A menu decision uses
only fresh frames (capture time strictly later than the last frame used) captured after the last tap's release plus
input_latency_max_s plus one frame, i.e. frames that must already show every key sent; repeated stale frames never
count twice. The guarantee is as good as that bound: the tests run the machine with its bounds at the sim's maxima,
and again at the 0.1 s defaults against up to 24 frames as a stress check. After a navigation tap the highlight must
be seen to change from its pre-tap value; when it reads the same on stable_frames such frames and the round trip (input + observation latency maxima + nav_margin_s) has passed, the tap
had no effect (the end of a non-wrapping list, or a dropped tap) and the direction flips for that step. The exit prompt
lists Yes above No, so No -> Yes is Up (probe P7); ties on a wrapping list go the direct way. tests/test_pause_loop.py
runs 10^4 randomized full quits (input + observation latency up to 14 frames, capture stalls, time-based key sampling
with 33 ms frames, prompts that do or do not wrap, false cues) and 2x10^3 menu walks on an already paused game with up
to 24 frames and stalls repeating a frame for up to 4 steps (non-wrapping Options included): no wrong Submit, no
unintended unpause. Without the post-tap cut the same 14-frame quits Submit a wrong item in 1025 of 2000 (335 unpause).

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
- InControl samples keys once per frame: a press shorter than a frame gap can be missed, so presses and releases last
  >= 34 ms and >= 2 frames (§3.7.5, §4.5 min_hold), longer than a 33 ms long frame;
- the Quit item is evaluated once per ShowMenu (greyed while disableSaveQuit or ScenePreloader.HasPendingOperations,
  MenuButtonSaveQuitListCondition) and a greyed item is skipped by Up / Down with wrap-around (m0:N17, C8);
- Patch 4: UIManager.ReturnToMainMenu returns silently while disablePause or disableSaveQuit, the prompt stays
  (m0 §2.4); a failed save shows SAVE_FAILED and the prompt again (m0:C9);
- mouse hover moves the highlight (probe P7): the final run keeps the mouse off the window.

Oracle mode (cues_from_state) reads the STATE "menu" section while paused {sel, quit_ok, dim, alpha, ignore_unpause,
quitting} when present and falls back to derived values without it: the Quit state from pause.dsq / pause.preload (the
condition the menu evaluates), the quit start from PreventPause on the prompt (which also stays set after a SAVE_FAILED,
m0:C9). Without "sel" the highlight is unknown and a real quit never starts (no blind Submit): training uses
emulate_quit, where a confirmed pause ends a GOAL_QUIT run as QUIT_EMULATED, or QUIT_EMULATED_GREYED /
REFUSED_EMULATED / QUIT_EMULATED_UNKNOWN when the real quit would have been greyed, refused (disablePause set) or
could not be read, so training does not overstate quit success.
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
MENU_ORDER = {M_PAUSE: ("continue", "options", "quit"), M_EXIT_PROMPT: ("yes", "no")}   # top to bottom (probe P7)
MENU_WRAPS = {M_PAUSE: True}   # MenuButtonList wraps (decompiled); the prompt's navigation is prefab data: unknown

GOAL_QUIT, GOAL_PAUSE = "QUIT", "PAUSE"
# outcomes
QUIT, QUIT_EMULATED, UNPAUSED, DEAD, KILL_REQUESTED, ALERT = (
    "QUIT", "QUIT_EMULATED", "UNPAUSED", "DEAD", "KILL_REQUESTED", "ALERT")
QUIT_EMULATED_GREYED, QUIT_EMULATED_UNKNOWN, REFUSED_EMULATED = (
    "QUIT_EMULATED_GREYED", "QUIT_EMULATED_UNKNOWN", "REFUSED_EMULATED")
PAUSED, GREYED, REFUSED = "PAUSED", "GREYED", "REFUSED"
UNLABELLED = "?"   # a ready menu's selected item that has no role name (oracle: Options items other than Back)
EMULATED = frozenset({QUIT_EMULATED, QUIT_EMULATED_GREYED, QUIT_EMULATED_UNKNOWN, REFUSED_EMULATED})
TERMINAL = frozenset({QUIT, UNPAUSED, DEAD, KILL_REQUESTED, ALERT}) | EMULATED
GREYED_UNPAUSE_EVADE, GREYED_KILL, GREYED_STAY = "UNPAUSE_EVADE", "KILL", "STAY"
HELD_STATES = ("HOLD", "GREYED", "REFUSED")

LOCKOUT_S = 0.3        # WaitForSecondsRealtime(0.3f) after every pause and unpause (m0:C12)
DIM_RATE = 3.2         # UIManager.MENU_FADE_SPEED, alpha per real second
DIM_PLATEAU = 0.7      # the modal dimmer stops at 0.8 (m0:C11): at or above this it is up, not starting
QUIT_AVAILABLE, QUIT_GREYED = "available", "greyed"


@dataclass(slots=True)
class PauseCues:
    """What the machine observes of one frame. t: real seconds when that frame was captured / produced (monotonic, the
    clock `now` is on); a repeated stale frame repeats its t."""
    t: float
    paused: bool | None = None       # direct pause flag (oracle game.paused); None in vision mode
    dim: float | None = None         # modal dimmer alpha (0 .. 0.8, plus any dark baseline); None when not measured
    frozen: bool | None = None       # world stopped (vision: no motion; oracle: timeScale 0; also true in hit-stop)
    menu: str = M_NONE               # M_* screen
    menu_ready: bool = False         # that menu has faded in and accepts input
    highlight: str | None = None     # "continue" / "options" / "quit", "yes" / "no", "back", "ok"; None: unreadable
    quit_state: str | None = None    # QUIT_AVAILABLE / QUIT_GREYED on a shown pause menu; None: unknown
    quit_cause: str | None = None    # "dsq" (disableSaveQuit) / "preload" / None (unknown) when greyed
    quitting: bool = False           # the quit save / fade-out has started
    dead: bool = False               # DEATH or PERMADEATH
    menu_alpha: float | None = None  # current menu canvas alpha
    disable_pause: bool | None = None   # PauseGate DISABLE_PAUSE (Patch 4 refuses Yes while set); None: unknown
    unpause_blocked: bool | None = None  # UIManager.ignoreUnpause (Continue does nothing while set)


@dataclass(slots=True)
class PauseQuitConfig:
    press_frames: int = 2
    release_frames: int = 2
    press_min_s: float = 0.034       # §3.7.5 ">= 34 ms (2 frames)", above a 33 ms long frame
    release_min_s: float = 0.034
    dim_cue: float = 0.03            # dimmer alpha that may be a pause cue (one 60 fps frame of fade = 0.053)
    dim_rise_frames: int = 2         # consecutive dimmer-rate rises that make the dim cue
    dim_rate_lo: float = 0.5         # accepted rise / (DIM_RATE x capture interval); up to 3x: the dimmer over a
    dim_rate_hi: float = 3.0         # fade that happens to run at the same time
    dim_base_window_s: float = 1.0   # the dimmer baseline is the lowest reading over this long before a frame
    menu_dim_rise: float = 0.1       # a vision menu cue needs the dim this far above the baseline (when measured)
    dim_drop_tol: float = 0.1        # a paused dimmer never falls: this far below its peak since the cue is no pause
    plateau_min: float = 0.65        # ... and it reaches base + 0.8 by 0.25 s: base + this by plateau_check_s after
    plateau_check_s: float = 0.4     # the cue, else no pause
    moving_reject_frames: int = 2    # fresh frames of a moving world (frozen False) that reject a cue
    confirm_hold_s: float = 0.6      # two detectors agreeing this long confirm without the third (longer than any
    #                                  hit-stop: the BindBreak freeze, 0.55 s, is the longest in the quit map)
    confirm_max_s: float = 2.0       # a cue neither confirmed nor contradicted this long: confirmed if a second
    #                                  detector (menu, stopped world) agreed at least once, else rejected
    budget_s: float = 0.23           # pressing must stop within this of the real pause
    loop_alert_s: float = 5.0        # still looping this long: alert (and keep looping)
    false_cue_alert: int = 3         # this many false cues: alert (and keep looping)
    input_latency_max_s: float = 0.10   # p99.9 key emission -> capture time of the first frame that can show its
    #                                     effect, on the active input path (probe P8, Esc -> first darkened capture:
    #                                     max 49.6 ms); frames captured later than tap end + this + frame_s count
    obs_latency_max_s: float = 0.10     # p99.9 capture -> this machine, capture stalls included (waits only)
    frame_s: float = 1 / 60          # one game frame (the frame that samples a key, before it shows the effect)
    stable_frames: int = 2           # fresh, post-tap frames that must read the same highlight
    nav_margin_s: float = 0.15       # beyond the round trip before a navigation tap counts as having had no effect
    flip_settle_rtts: float = 2.0    # after a no-effect flip: the reading must hold this many round trips (plus the
    #                                  margin) past the last tap before the next tap or Submit; a change meanwhile
    #                                  means the latency bound was exceeded -> ALERT, never a Submit
    menu_wait_s: float = 1.5         # a menu expected after a Submit must be ready within this (measured 0.35 s)
    read_wait_s: float = 0.5         # Quit state / highlight unreadable this long on a ready menu: unknown
    max_nav: int = 12                # navigation taps toward one target
    max_submits: int = 3             # Submits of one step (a lost Submit is retried)
    max_save_retries: int = 2        # SAVE_FAILED -> OK -> Yes again
    refusal_s: float = 0.5           # after Yes took effect, still on the prompt this long = Patch 4 refusal
    quit_wait_s: float = 10.0        # quit start -> main menu (measured 2.63 s)
    unpause_margin_s: float = 0.05   # Continue only this long after the estimated end of the lockout
    unpause_confirm_s: float = 0.5
    emulate_quit: bool = False       # training: a confirmed pause ends a GOAL_QUIT run as QUIT_EMULATED*
    emulate_wait_s: float = 0.5      # ... after reading the Quit state for at most this long
    refresh_greyed: bool = True      # greyed by disableSaveQuit or unknown cause: Options -> Back once

    @property
    def rtt_s(self) -> float:
        return self.input_latency_max_s + self.frame_s + self.obs_latency_max_s


@dataclass(slots=True)
class _Tap:
    key: str
    t0: float
    down: bool = True
    n: int = 0
    done: bool = False
    t_end: float = 0.0     # emission time of the release's end (valid once done)


@dataclass(slots=True)
class _Step:
    menu: str
    target: str
    expect: str            # menu expected after the Submit, or "quitting" / "unpaused"
    navs: int = 0
    submits: int = 0
    dir: str | None = None # navigation direction, fixed for the step once chosen (flipped when a tap does nothing)
    flipped: bool = False  # a tap of this step was judged to have had no effect


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
        self.t_start: float | None = None         # emission clock
        self.t_cue: float | None = None           # capture time of the earliest pause cue
        self.t_pause_est: float | None = None     # estimated real pause time (capture clock)
        self.t_confirm: float | None = None
        self.last_press_t: float | None = None    # last emission time a Pause press began
        self.presses = 0
        self.false_cues = 0
        self.unexpected_unpauses = 0
        self.nav_flips = 0
        self.quit_state_seen: str | None = None
        self.unpause_lockout_until: float | None = None
        self.now = 0.0
        self._last_t = float("-inf")      # capture time of the last fresh frame
        self._tap: _Tap | None = None
        self._cut = float("-inf")         # frames captured after this reflect every key sent so far
        self._plan: list[_Step] = []
        self._phase = ""
        self._phase_t = 0.0               # emission clock
        self._read_t0: float | None = None   # capture time of the first usable frame of this read
        self._stable = 0
        self._last_hl: str | None = None
        self._pre_hl: str | None = None   # highlight read before the last navigation tap
        self._same = 0
        self._effect_t0: float | None = None
        self._refreshed = False
        self._save_retries = 0
        self._after_plan = ""
        self._quit_t0 = 0.0
        self._dims: list[tuple[float, float]] = []
        self._dim_hist: list[tuple[float, float]] = []   # fresh LOOP / CONFIRM readings, dim_base_window_s long
        self._sig_t: float | None = None  # capture time of the last frame with the dimmer's rise signature
        self._cue_src: frozenset[str] = frozenset()
        self._suppressed: set[str] = set()
        self._run_frames = 0
        self._cue_base: float | None = None   # dimmer baseline before the cue (None: not measured / no history)
        self._cue_max = 0.0
        self._moving = 0
        self._hold_menu: float | None = None  # capture time since when menu + stopped world held in CONFIRM
        self._hold_dim: float | None = None   # ... since when the full dimmer rise + stopped world held
        self._second = False                  # a detector other than the cue's agreed since the cue
        self._settle: tuple[float, str] | None = None   # (until, reading) after a flip
        self._settle_armed = False

    # ---- control ------------------------------------------------------------------------------------------------

    def start(self, t: float, goal: str = GOAL_QUIT) -> None:
        """Enter the pause loop (PAUSE_PENDING); t on the emission clock. Restarting a finished machine is allowed."""
        self.goal = goal
        self.state = "LOOP"
        self.outcome = None
        self.alert = False
        self.t_start = t
        self.now = t
        self.t_cue = self.t_pause_est = self.t_confirm = None
        self._tap = None
        self._plan = []
        self._refreshed = False
        self._save_retries = 0
        self._dims = []
        self._dim_hist = []
        self._sig_t = None
        self._suppressed = set()
        self._cue_base = None
        self._settle = None
        self._note(t, "start", goal)

    def upgrade_to_quit(self, t: float) -> bool:
        """The supervisor asked for a quit after the loop started for a pause (a self-check that became a quit)."""
        if self.goal == GOAL_QUIT or self.done:
            return False
        if self.state in HELD_STATES:
            return self.request_quit(t)
        self.goal = GOAL_QUIT
        self._note(t, "goal", GOAL_QUIT)
        return True

    def request_quit(self, t: float) -> bool:
        """From a held pause (goal PAUSE, greyed or refused): read the Quit item again and quit if it is available."""
        if self.state not in HELD_STATES:
            return False
        self.goal = GOAL_QUIT
        self.now = max(self.now, t)
        if self.state == "REFUSED":
            self._begin_plan([_Step(M_EXIT_PROMPT, "yes", "quitting")], "quit")
        else:
            self._enter(t, "READ_QUIT")
        return True

    def request_unpause(self, t: float) -> bool:
        """Continue + Submit (never Esc) once the lockout has passed. The caller ran the frozen-state check."""
        if self.state not in HELD_STATES:
            return False
        self._enter(t, "UNPAUSE")
        return True

    def resolve_greyed(self, t: float, choice: str) -> bool:
        """§3.7.5 step 4, greyed: UNPAUSE_EVADE (the frozen check passed: unpause, evade out of the room, pause again;
        the supervisor latches EVADE_EXIT), KILL (D13 enabled and its conditions hold; the kill itself is
        safety/last_resort), or STAY (alert, wait)."""
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

    @property
    def confirmed(self) -> bool:
        """The pause was confirmed and has not been lost since."""
        return self.t_confirm is not None and self.state not in ("IDLE", "LOOP", "CONFIRM")

    # ---- per frame ------------------------------------------------------------------------------------------------

    def step(self, c: PauseCues, now: float | None = None) -> frozenset[str]:
        """Keys to hold from `now` (emission clock; default c.t: the frame is handled as it is captured)."""
        now = c.t if now is None else max(now, c.t)
        self.now = now
        fresh = c.t > self._last_t
        if fresh:
            self._last_t = c.t
        st = self.state
        if st in ("IDLE", "DONE"):
            return NO_KEYS
        if c.dead:
            self._finish(now, DEAD)
            return NO_KEYS
        if st in ("LOOP", "CONFIRM"):
            if fresh:
                self._observe_dim(c)
            self._loop_alerts(now)
            return self._loop(c, fresh) if st == "LOOP" else self._confirm(c, fresh)
        if st == "QUITTING":
            return self._quitting(c, fresh)
        if fresh and self._ending(c) and st in HELD_STATES + ("READ_QUIT", "UNPAUSE"):
            self._note(now, "quitting", f"seen in {st}")   # e.g. a slow save read as a refusal
            self._enter(now, "QUITTING")
            self._quit_t0 = now
            return self._quitting(c, fresh)
        if fresh:
            moving = c.frozen is False and not self._ending(c)
            self._run_frames = self._run_frames + 1 if (self._unpaused(c) or (moving and c.paused is None)) else 0
        expecting = st == "MENU" and self._plan and self._plan[0].expect == "unpaused"
        if self._world_runs(c) and not expecting:
            self.unexpected_unpauses += 1
            self.alert = True
            self._note(now, "unexpected_unpause", st)
            self.state = "LOOP"           # the world runs: pause again (presses are dropped for the 0.3 s lockout)
            self.t_cue = self.t_pause_est = self.t_confirm = None
            self._tap = None
            self._plan = []
            self._run_frames = 0
            return self._loop(c, False)
        if st == "READ_QUIT":
            return self._read_quit(c, fresh)
        if st == "UNPAUSE":
            return self._unpause_wait(c, fresh)
        if st == "MENU":
            return self._menu(c, fresh)
        return NO_KEYS   # HOLD, GREYED, REFUSED: stay paused, press nothing

    # ---- cues -----------------------------------------------------------------------------------------------------

    def _dim_rising(self, k: int) -> bool:
        """The last k capture intervals each raised the dim by DIM_RATE x the interval (within the tolerance)."""
        h, cfg = self._dims, self.cfg
        if len(h) < k + 1:
            return False
        for (t0, d0), (t1, d1) in zip(h[-k - 1:-1], h[-k:]):
            exp = DIM_RATE * (t1 - t0)
            if exp <= 0 or not cfg.dim_rate_lo <= (d1 - d0) / exp <= cfg.dim_rate_hi:
                return False
        return True

    def _base(self, t: float) -> float | None:
        """The dimmer baseline: the lowest reading over dim_base_window_s before capture time t (None: no history)."""
        prior = [d for tt, d in self._dim_hist if tt < t]
        return min(prior) if prior else None

    def _menu_cue(self, c: PauseCues) -> bool:
        """Vision: a pause menu over a world seen stopped (frozen None, an unmeasured world, is not stopped) with, when
        the dimmer is measured, the dim at least menu_dim_rise above the pre-cue baseline. A misread menu over a dark
        room or a static scene therefore never stops the loop; only on the loop's first frame (no history: the game
        may already be paused, where a press would unpause it) does an absolute dim at the 0.8 plateau stand in."""
        if c.paused is not None or c.menu not in PAUSE_MENUS or c.frozen is not True:
            return False
        if c.dim is None:
            return True
        base = self._base(c.t)
        if base is None:
            return c.dim >= DIM_PLATEAU
        return c.dim - base >= self.cfg.menu_dim_rise

    def _observe_dim(self, c: PauseCues) -> None:
        """A fresh frame's dimmer reading: keep the last dim_rise_frames + 1 and the baseline window, and note the rise
        signature."""
        cfg = self.cfg
        if c.dim is None:
            self._dims = []
            return
        self._dims = (self._dims + [(c.t, c.dim)])[-(cfg.dim_rise_frames + 1):]
        self._dim_hist = [(t, d) for t, d in self._dim_hist if t >= c.t - cfg.dim_base_window_s] + [(c.t, c.dim)]
        if c.dim >= cfg.dim_cue and self._dim_rising(cfg.dim_rise_frames):
            self._sig_t = c.t

    def _sources(self, c: PauseCues, fresh: bool) -> set[str]:
        cfg = self.cfg
        src = set()
        if c.paused is True:
            src.add("paused")
        if self._menu_cue(c):
            src.add("menu")
        if c.dim is not None and self._sig_t == c.t:
            src.add("dim")
        sup = self._suppressed
        if sup and fresh:   # a source that proved false counts again once it has cleared
            if "paused" in sup and c.paused is not True:
                sup.discard("paused")
            if "menu" in sup and c.menu not in PAUSE_MENUS:
                sup.discard("menu")
            if "dim" in sup and (c.dim is None or c.dim < cfg.dim_cue or not self._dim_rising(1)):
                sup.discard("dim")
        return src - sup

    def _trajectory(self, c: PauseCues) -> str:
        """The dimmer since the cue against a real pause (alpha + 3.2/s from the pause frame to base + 0.8, then flat,
        never falling while paused; m0:C11): "none" (not measured, or no baseline), "broken" (fell more than
        dim_drop_tol below its peak, or still under base + plateau_min plateau_check_s after the cue), "full" (at
        base + plateau_min or above), else "rising"."""
        b, cfg = self._cue_base, self.cfg
        if c.dim is None or b is None:
            return "none"
        self._cue_max = max(self._cue_max, c.dim)
        if c.dim < self._cue_max - cfg.dim_drop_tol:
            return "broken"
        if c.dim - b >= cfg.plateau_min:
            return "full"
        return "broken" if c.t - self.t_cue >= cfg.plateau_check_s else "rising"

    def _verdict(self, c: PauseCues) -> str | None:
        """CONFIRM on a fresh frame: "confirm", "reject" (resume pressing) or None (keep waiting, pressing nothing).
        Oracle: the paused flag decides. Vision: a cue is rejected only on positive evidence that the game is not
        paused (the world moving on moving_reject_frames frames, or the dimmer leaving the pause trajectory), never on
        a timer: once the 0.3 s lockout is over a press would unpause a real pause whose menu the reader has not seen
        yet (round-2 review: readers slower than about 10 frames unpaused up to 400 of 400 trials with the old 0.15 s
        confirm window). Confirmation needs two independent detectors: the menu reader with the dimmer on its pause
        trajectory; or, for confirm_hold_s (longer than any hit-stop), the reader or the full dimmer rise with a world
        seen stopped. After confirm_max_s with nothing against it, the pause is taken as real when a second detector
        agreed at least once (READ_QUIT then alerts if the menu never becomes readable), else the cue was a lone
        detector's (a dimmer-like fade with motion unmeasured) and the loop resumes."""
        cfg = self.cfg
        if c.paused is not None:
            return "confirm" if c.paused else "reject"
        self._moving = self._moving + 1 if c.frozen is False else 0
        if self._moving >= cfg.moving_reject_frames:
            return "reject"
        tr = self._trajectory(c)
        if tr == "broken":
            return "reject"
        menu, stopped = c.menu in PAUSE_MENUS, c.frozen is True
        if menu and tr in ("rising", "full"):
            return "confirm"
        self._second |= menu or stopped
        self._hold_menu = (self._hold_menu if self._hold_menu is not None else c.t) if menu and stopped else None
        self._hold_dim = (self._hold_dim if self._hold_dim is not None else c.t) if tr == "full" and stopped else None
        if any(h is not None and c.t - h >= cfg.confirm_hold_s for h in (self._hold_menu, self._hold_dim)):
            return "confirm"
        if c.t - self.t_cue > cfg.confirm_max_s:
            return "confirm" if self._second else "reject"
        return None

    def _loop_alerts(self, now: float) -> None:
        cfg = self.cfg
        if self.alert:
            return
        if self.t_start is not None and now - self.t_start > cfg.loop_alert_s:
            self.alert = True
            self._note(now, "loop_alert", f"{now - self.t_start:.1f} s")
        elif self.false_cues >= cfg.false_cue_alert:
            self.alert = True
            self._note(now, "false_cue_alert", str(self.false_cues))

    # ---- states ---------------------------------------------------------------------------------------------------

    def _loop(self, c: PauseCues, fresh: bool) -> frozenset[str]:
        src = self._sources(c, fresh)
        if src:
            self.t_cue = c.t
            base = self._dims[0][1] if "dim" in src and self._dims else 0.0
            back = max(0.0, (c.dim - base) / DIM_RATE - self.cfg.frame_s) if "dim" in src else 0.0
            self.t_pause_est = c.t - back
            self._cue_src = frozenset(src)
            self._cue_base = None if c.dim is None else self._base(c.t)
            self._cue_max = c.dim or 0.0
            self._moving = 0
            self._hold_menu = self._hold_dim = None
            self._second = "menu" in src      # the menu cue is already the reader plus a stopped world
            self.state = "CONFIRM"
            self._tap = None
            self._note(self.now, "cue", f"{'+'.join(sorted(src))} paused={c.paused} dim={c.dim} menu={c.menu}")
            return NO_KEYS
        now = self.now
        if self._tap is not None and not self._tap.done:
            keys = self._tap_keys(now)
            if not self._tap.done:
                return keys
        self._tap = _Tap(PAUSE, now)     # the frame a release completes starts the next press
        self.presses += 1
        self.last_press_t = now
        return self._tap_keys(now)

    def _confirm(self, c: PauseCues, fresh: bool) -> frozenset[str]:
        if not fresh:
            return NO_KEYS
        v = self._verdict(c)
        if v == "confirm":
            self.t_confirm = c.t
            self._note(self.now, "confirmed", f"{c.menu} dim={c.dim} frozen={c.frozen}")
            self._enter(self.now, "READ_QUIT")
            return NO_KEYS
        if v == "reject":
            self.false_cues += 1
            self._suppressed |= self._cue_src - {"menu"}   # the menu cue needs a stopped world: it re-arms only when
            #                                               the world stops again (one cue per hit-stop, never stuck)
            self._note(self.now, "false_cue", "+".join(sorted(self._cue_src)))
            self.state = "LOOP"
            self.t_cue = self.t_pause_est = None
            self._loop_alerts(self.now)
            return self._loop(c, False)
        return NO_KEYS

    def _read_quit(self, c: PauseCues, fresh: bool) -> frozenset[str]:
        cfg = self.cfg
        if not fresh:
            return self._stalled("pause menu")
        if self._read_t0 is None:
            self._read_t0 = c.t
        waited = c.t - self._read_t0
        emulate = cfg.emulate_quit and self.goal == GOAL_QUIT
        ready = c.menu == M_PAUSE and c.menu_ready
        if emulate and (waited > cfg.emulate_wait_s or (ready and c.quit_state is not None)):
            self.quit_state_seen = c.quit_state if ready else None
            if self.quit_state_seen == QUIT_GREYED:
                out = QUIT_EMULATED_GREYED
            elif c.disable_pause:
                out = REFUSED_EMULATED
            elif self.quit_state_seen is None:
                out = QUIT_EMULATED_UNKNOWN
            else:
                out = QUIT_EMULATED
            self._finish(self.now, out)
            return NO_KEYS
        if not ready:
            if waited > cfg.menu_wait_s:
                self._fail("pause menu not ready")
            return NO_KEYS
        if c.quit_state is None and waited < cfg.read_wait_s:
            return NO_KEYS
        self.quit_state_seen = c.quit_state or "unknown"
        if self.goal == GOAL_PAUSE:
            self.outcome = PAUSED
            self._enter(self.now, "HOLD")
            return NO_KEYS
        if c.quit_state == QUIT_AVAILABLE:
            self._begin_plan([_Step(M_PAUSE, "quit", M_EXIT_PROMPT), _Step(M_EXIT_PROMPT, "yes", "quitting")], "quit")
            return self._menu(c, True)
        if cfg.refresh_greyed and not self._refreshed and c.quit_cause in (None, "dsq"):
            self._refreshed = True
            self._note(self.now, "greyed_refresh", str(c.quit_cause))
            self._begin_plan([_Step(M_PAUSE, "options", M_OPTIONS), _Step(M_OPTIONS, "back", M_PAUSE)], "refresh")
            return self._menu(c, True)
        self.outcome = GREYED
        self.alert = True
        self._note(self.now, "greyed", str(c.quit_cause))
        self._enter(self.now, "GREYED")
        return NO_KEYS

    def _unpause_wait(self, c: PauseCues, fresh: bool) -> frozenset[str]:
        """Continue is refused during the lockout, while the menu is not ready (PauseMenuButton.OnSubmit checks
        PauseAllowed; m0 §2.4) and while ignoreUnpause is set, so wait for all three. From the quit prompt: "No" first,
        back to the pause menu."""
        cfg = self.cfg
        lockout_end = (self.t_pause_est if self.t_pause_est is not None else self._phase_t) + LOCKOUT_S
        ready = c.menu in (M_PAUSE, M_EXIT_PROMPT) and c.menu_ready and not c.unpause_blocked
        if not fresh or c.t < lockout_end + cfg.unpause_margin_s or not ready:
            if self.now - self._phase_t > LOCKOUT_S + cfg.menu_wait_s + cfg.rtt_s:
                self._fail("pause menu not ready for Continue")
            return NO_KEYS
        plan = [_Step(M_PAUSE, "continue", "unpaused")]
        if c.menu == M_EXIT_PROMPT:
            plan.insert(0, _Step(M_EXIT_PROMPT, "no", M_PAUSE))
        self._begin_plan(plan, "unpause")
        return self._menu(c, True)

    def _menu(self, c: PauseCues, fresh: bool) -> frozenset[str]:
        """One plan step: wait for its menu, read the highlight on fresh post-tap frames, navigate, Submit, see the
        effect. Keys of a tap in progress are always finished first."""
        cfg = self.cfg
        if self._tap is not None and not self._tap.done:
            keys = self._tap_keys(self.now)
            if self._tap.done:
                self._cut = self._tap_cut(self._tap.t_end)
                if self._settle_armed:
                    self._settle_armed = False
                    self._settle = (self._tap.t_end + cfg.nav_margin_s + cfg.flip_settle_rtts * cfg.rtt_s, "")
            return keys
        s = self._plan[0]
        ph = self._phase
        if ph == "effect":
            return self._effect(c, s, fresh)
        usable = fresh and c.t > self._cut
        if not usable:
            return self._stalled(f"menu {s.menu}")
        if self._read_t0 is None:
            self._read_t0 = c.t
        if not (c.menu == s.menu and c.menu_ready):
            if ph == "read":   # the menu went away under us: wait for it again
                self._phase, self._read_t0 = "wait", c.t
            elif c.t - self._read_t0 > cfg.menu_wait_s:
                self._fail(f"menu {s.menu} not ready")
            return NO_KEYS
        if ph == "wait":
            self._read_phase(c.t)
        hl = c.highlight
        if hl is None:
            if c.t - self._read_t0 > cfg.read_wait_s:
                self._fail(f"highlight unreadable on {s.menu}")
            return NO_KEYS
        if self._settling(c, hl):
            return NO_KEYS
        if self._unmoved(hl):
            self._same += 1                 # not moved (yet): the tap had no effect only after a full round trip
            self._stable = 0
            if self._same < cfg.stable_frames or self.now - self._tap_end_t < cfg.rtt_s + cfg.nav_margin_s:
                return NO_KEYS
            if hl != UNLABELLED:            # an unlabelled item may have moved to another one: go on the same way
                s.dir = UP if s.dir == DOWN else DOWN
                s.flipped = True
                self.nav_flips += 1
                self._note(self.now, "nav_no_effect", f"{s.menu}:{hl} flip to {s.dir}")
        else:
            self._stable = self._stable + 1 if hl == self._last_hl else 1
            self._last_hl = hl
            if self._stable < cfg.stable_frames:
                return NO_KEYS
        if hl == s.target:
            s.submits += 1
            self._note(self.now, "submit", f"{s.menu}:{hl}")
            self._phase, self._effect_t0 = "effect", None
            return self._start_tap(ENTER)
        if s.navs >= cfg.max_nav:
            self._fail(f"{s.target} not reached on {s.menu} (at {hl})")
            return NO_KEYS
        s.navs += 1
        if s.dir is None:
            s.dir = _direction(s.menu, hl, s.target)
        self._note(self.now, "nav", f"{s.menu}:{hl}->{s.target} {s.dir}")
        self._read_phase(None)
        self._pre_hl = hl
        self._settle_armed = s.flipped   # every later decision of this step waits for the reading to settle
        return self._start_tap(s.dir)

    def _effect(self, c: PauseCues, s: _Step, fresh: bool) -> frozenset[str]:
        cfg = self.cfg
        if not (fresh and c.t > self._cut):
            return self._stalled(f"effect of {s.menu}:{s.target}")
        if self._effect_t0 is None:
            self._effect_t0 = c.t
        waited = c.t - self._effect_t0
        if s.expect == "quitting":
            if self._ending(c):
                self._note(self.now, "quitting", "")
                self._plan.pop(0)
                self._enter(self.now, "QUITTING")
                self._quit_t0 = self.now
                return NO_KEYS
            if c.menu == M_SAVE_FAILED:
                self._save_failed()
                return NO_KEYS
            if waited > cfg.refusal_s and c.menu == M_EXIT_PROMPT:
                if c.menu_ready and c.highlight == s.target and s.submits < cfg.max_submits:
                    self._note(self.now, "submit_lost", f"{s.menu}:{s.target}")   # a press a long frame swallowed
                    self._read_phase(c.t)
                    self._pre_hl = None
                    return NO_KEYS
                self.outcome = REFUSED
                self.alert = True
                self._note(self.now, "refused", "Patch 4: still on the prompt")
                self._enter(self.now, "REFUSED")
                return NO_KEYS
            if waited > cfg.quit_wait_s:
                self._fail("Yes: neither a quit nor the prompt")
            return NO_KEYS
        if s.expect == "unpaused":
            if self._unpaused(c):
                self.unpause_lockout_until = c.t + LOCKOUT_S
                self._finish(self.now, UNPAUSED)
                return NO_KEYS
        elif c.menu == s.expect and c.menu_ready:
            self._plan.pop(0)
            self._settle = None
            if self._plan:
                self._phase, self._read_t0, self._pre_hl = "wait", c.t, None
                return self._menu(c, True)
            if self._after_plan == "refresh":
                self._enter(self.now, "READ_QUIT")
                return NO_KEYS
            self._fail(f"plan {self._after_plan} ended without its effect")
            return NO_KEYS
        if waited > (cfg.unpause_confirm_s if s.expect == "unpaused" else cfg.menu_wait_s):
            if c.menu == s.menu and c.menu_ready and s.submits < cfg.max_submits:
                self._note(self.now, "submit_lost", f"{s.menu}:{s.target}")
                self._read_phase(c.t)        # the Submit was dropped: read the highlight again, then retry
                self._pre_hl = None
            else:
                self._fail(f"no effect of {s.menu}:{s.target} (now {c.menu})")
        return NO_KEYS

    def _quitting(self, c: PauseCues, fresh: bool) -> frozenset[str]:
        if fresh and c.menu == M_MAIN_MENU:
            self._finish(self.now, QUIT)
        elif fresh and c.menu == M_SAVE_FAILED:
            self._save_failed()
        elif self.now - self._quit_t0 > self.cfg.quit_wait_s:
            self._fail("main menu not reached after the quit started")
        return NO_KEYS

    def _save_failed(self) -> None:
        """SAVE_FAILED during the quit (m0:C9): the world stays frozen and Esc / Continue do nothing; OK brings the
        prompt back, then Yes again, a bounded number of times, else alert and wait."""
        if self._save_retries >= self.cfg.max_save_retries:
            self._fail("SAVE_FAILED again")
            return
        self._save_retries += 1
        self._note(self.now, "save_failed", str(self._save_retries))
        self._begin_plan([_Step(M_SAVE_FAILED, "ok", M_EXIT_PROMPT), _Step(M_EXIT_PROMPT, "yes", "quitting")], "quit")

    # ---- helpers --------------------------------------------------------------------------------------------------

    @staticmethod
    def _ending(c: PauseCues) -> bool:
        return c.quitting or c.menu in (M_MAIN_MENU, M_LOADING)

    def _dim_gone(self, c: PauseCues) -> bool:
        """The dimmer is back at the pre-pause baseline (absolute 0 when no baseline was measured)."""
        base = self._cue_base if self._cue_base is not None else 0.0
        return c.dim is not None and c.dim - base < self.cfg.dim_cue

    def _unpaused(self, c: PauseCues) -> bool:
        """Evidence that the world runs: the oracle's flag; vision: a moving world with no pause menu or no dimmer,
        or, while motion is unmeasured (frozen None), the menu gone and the dimmer back at its pre-cue baseline."""
        if self._ending(c):
            return False
        if c.paused is not None:
            return c.paused is False and c.menu not in PAUSE_MENUS
        if c.frozen is False:
            return c.menu == M_NONE or c.dim is None or self._dim_gone(c)
        return c.frozen is None and c.menu == M_NONE and self._cue_base is not None and self._dim_gone(c)

    def _world_runs(self, c: PauseCues) -> bool:
        """Consecutive fresh frames prove the game is not paused: oracle 1; vision 2 with the menu and dimmer gone, or
        6 of a moving world whatever a menu / dimmer reading says (a paused world never moves: a pause menu misread
        over the running game must not hold the machine in a menu state)."""
        if c.paused is not None:
            return self._run_frames >= 1
        return self._run_frames >= (2 if self._unpaused(c) else 6)

    def _stalled(self, what: str) -> frozenset[str]:
        """No usable frame: alert if none came for far longer than any expected wait."""
        cfg = self.cfg
        if self.now - self._phase_t > cfg.menu_wait_s + cfg.quit_wait_s + cfg.rtt_s:
            self._fail(f"no usable frame for {what}")
        return NO_KEYS

    def _start_tap(self, key: str) -> frozenset[str]:
        self._tap = _Tap(key, self.now)
        self._phase_t = self.now
        return self._tap_keys(self.now)

    def _tap_cut(self, t_end: float) -> float:
        """Frames captured after this reflect every key sent so far (when input_latency_max_s holds)."""
        return t_end + self.cfg.input_latency_max_s + self.cfg.frame_s

    def _unmoved(self, hl: str) -> bool:
        """The change-wait: the highlight still reads what it read before the last navigation tap."""
        return self._pre_hl is not None and hl == self._pre_hl

    def _settling(self, c: PauseCues, hl: str) -> bool:
        """After a no-effect flip, the latency bound is in doubt (round-2 review: past it, a late first tap and the
        flipped counter-tap both act, and a Submit lands on the wrong item, Continue included). The reading must then
        hold on every fresh post-cut frame until the settle time; a change meanwhile, with no tap in flight, means a
        key acted later than input_latency_max_s allows: ALERT, never a Submit."""
        st = self._settle
        if st is None:
            return False
        until, seen = st
        if not seen:
            self._settle = (until, hl)
        elif hl != seen:
            self._settle = None
            self._fail(f"highlight moved {seen} -> {hl} with no tap in flight: latency above the configured bound")
            return True
        if c.t < until:
            return True
        self._settle = None
        return False

    @property
    def _tap_end_t(self) -> float:
        return self._tap.t_end if self._tap is not None else float("-inf")

    def _tap_keys(self, now: float) -> frozenset[str]:
        """Hold the current tap's key on >= press_frames frames spanning >= press_min_s, then keep it released as long.
        On the frame the release is complete the tap is done and holds nothing (a next tap may start that frame)."""
        tap, cfg = self._tap, self.cfg
        if tap.down:
            if tap.n >= cfg.press_frames and now - tap.t0 >= cfg.press_min_s:
                tap.down, tap.n, tap.t0 = False, 0, now
            else:
                tap.n += 1
                return frozenset((tap.key,))
        elif tap.n >= cfg.release_frames and now - tap.t0 >= cfg.release_min_s:
            tap.done = True
            tap.t_end = now
            return NO_KEYS
        tap.n += 1
        return NO_KEYS

    def _read_phase(self, t0: float | None) -> None:
        self._phase, self._read_t0 = "read", t0
        self._stable, self._last_hl, self._same = 0, None, 0

    def _begin_plan(self, plan: list[_Step], name: str) -> None:
        self._plan, self._after_plan = plan, name
        self._settle, self._settle_armed = None, False
        self.state = "MENU"
        self._phase, self._phase_t, self._read_t0, self._pre_hl = "wait", self.now, None, None

    def _enter(self, t: float, state: str) -> None:
        self.state = state
        self._phase_t = t
        if state == "READ_QUIT":
            self._read_t0 = None          # the read waits on frames from now on
        self._note(t, "state", state)

    def _finish(self, t: float, outcome: str) -> None:
        self.outcome = outcome
        self.state = "DONE"
        self._tap = None
        self._note(t, "done", outcome)

    def _fail(self, why: str) -> None:
        """Stay paused and alert; never press anything to recover blindly."""
        self.alert = True
        self._note(self.now, "fail", why)
        self._finish(self.now, ALERT)

    def _note(self, t: float, kind: str, detail: str) -> None:
        self.log.append((round(t, 4), kind, detail))


def _direction(menu: str, at: str, target: str) -> str:
    """Up or Down toward target. Known order: the direct way (Up when the target is above), or the shorter way round
    on a list known to wrap, ties the direct way (the exit prompt: No -> Yes is Up, probe P7, whether or not it wraps).
    Unknown order (Options): Up for "back", the last item, else Down. The highlight is read again after every tap and a
    tap that moves nothing flips the direction, so a wrong guess costs taps, never a wrong Submit."""
    order = MENU_ORDER.get(menu)
    if at == UNLABELLED:
        return DOWN    # Back is the last item: Down reaches it whether the list wraps or not, with no flip to read
    if not order or at not in order or target not in order:
        return UP if target == "back" else DOWN
    i, j, n = order.index(at), order.index(target), len(order)
    direct = UP if j < i else DOWN
    if not MENU_WRAPS.get(menu):
        return direct
    down, up = (j - i) % n, (i - j) % n
    return direct if down == up else DOWN if down < up else UP


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

_DEATH_EVENTS = {"hero_dead", "player_dead", "permadeath_dead"}


def cues_from_state(s: dict, qpc_freq: float = 1e7) -> PauseCues:
    """PauseCues from one oracle STATE (training only). t is the frame's end-of-frame QPC in seconds. The STATE "menu"
    section (exported while paused: sel, quit_ok, dim, alpha, ignore_unpause, quitting) is read when present; without
    it the Quit state and the quit start are derived from the PauseGate and the menu state."""
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
    extra = s.get("menu") or {}
    sel = extra.get("sel")
    highlight = sel if isinstance(sel, str) and sel else None
    if highlight is None and menu == M_OPTIONS and ready and isinstance(s.get("menu"), dict):
        highlight = UNLABELLED   # MenuExporter names only Back on Options (sel nil for Game, Audio, ...)
    quit_state = quit_cause = None
    if menu == M_PAUSE:
        if extra.get("quit_ok") is not None:
            quit_state = QUIT_AVAILABLE if extra["quit_ok"] else QUIT_GREYED
        else:   # MenuButtonSaveQuitListCondition.IsFulfilled, evaluated on frozen state
            quit_state = QUIT_GREYED if p.get("dsq") or p.get("preload") else QUIT_AVAILABLE
        if quit_state == QUIT_GREYED:
            quit_cause = "dsq" if p.get("dsq") else "preload" if p.get("preload") else None
    if extra.get("quitting") is not None:
        quitting = bool(extra["quitting"])
    else:
        quitting = menu == M_EXIT_PROMPT and bool(blk & gc.BLK_PAUSE_LOCKOUT)
    dead = g.get("pd_mode") == gc.PD_DEAD or any(ev.get("k") in _DEATH_EVENTS for ev in s.get("ev") or ())
    ts = s.get("ts")
    ign = extra.get("ignore_unpause")
    return PauseCues(
        t=t, paused=bool(g.get("paused")), dim=extra.get("dim"), frozen=None if ts is None else ts == 0,
        menu=menu, menu_ready=ready, highlight=highlight, quit_state=quit_state, quit_cause=quit_cause,
        quitting=quitting, dead=dead, menu_alpha=extra.get("alpha"),
        disable_pause=bool(blk & gc.BLK_DISABLE_PAUSE) if "blk" in p else None,
        unpause_blocked=None if ign is None else bool(ign))
