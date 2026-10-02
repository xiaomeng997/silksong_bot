"""A simulated game for the pause loop and quit sequence (tests/test_pause_loop.py): the 1.0.30000 pause and pause-menu
rules that ssbot.safety.pause_quit depends on, one rendered frame at a time, with input and observation latency,
capture stalls, frame-time jitter and false cues.

Rules modelled (m0 §2.4, §2.6, C11, C12, N12, N17; probe P7; human session 20260930_210337):
- keys are sampled once per frame, by time (InControl polling): an emission arrives input_lat frames (plus jitter)
  after it was sent, in order, and a frame sees the last key set that arrived by its time, so a press and its release
  that both arrive between two frame samples are never seen (2 % of frames last 33 ms);
- a Pause edge while PLAYING pauses only when the gate is open and PauseAllowed; otherwise it is dropped (not queued);
- pause and unpause each start a 0.3 s real-time lockout (PauseAllowed false);
- while PAUSED, any Pause (Esc) edge after the lockout unpauses (InputHandler or PauseMenuButton.OnCancel), menu
  ready or not: the worst case of C11;
- the pause menu accepts input menu_ready_frames after the pause (measured 8-9); Up / Down move the highlight over the
  active items, with wrap-around on the pause menu and, when configured, on the prompt and Options; a greyed Quit is
  not active; Enter acts on the highlighted item;
- Continue unpauses one frame after Submit and only after the lockout; Quit opens the "save and quit?" prompt (Yes
  above No, ready 21 frames later, "No" highlighted); Yes starts the quit (main menu quit_frames later) unless refused
  (Patch 4) or the save fails (SAVE_FAILED, OK -> the prompt again, m0:C9); Options opens the options menu, whose Back
  returns to the pause menu and recomputes the Quit item;
- the dimmer grows by udt x 3.2 from the pause frame to 0.8, on top of any dark baseline; the menu becomes visible to
  a reader 3 frames in.
Observation: the machine sees the frame obs_lat frames back; a capture stall repeats the last seen frame for up to
stall_max steps, then the view jumps forward. Cues come in oracle form (paused flag, no dimmer) or vision form (no
paused flag: dimmer, menu, frozen world). False cues (vision): a 4-frame dark flash, a constant dark baseline, a fade
that rises like the dimmer and stays, a pause menu misread over the running game, world freezes (hit-stop).
"""
import random
from dataclasses import dataclass, field

from ssbot.safety.pause_quit import (M_EXIT_PROMPT, M_MAIN_MENU, M_NONE, M_OPTIONS, M_PAUSE, M_SAVE_FAILED,
                                     QUIT_AVAILABLE, QUIT_GREYED, PauseCues)

PAUSE_ITEMS = ("continue", "options", "quit")
PROMPT_ITEMS = ("yes", "no")
OPTIONS_ITEMS = ("game", "audio", "video", "controller", "keyboard", "back")
FRAME_S = 1 / 60


@dataclass
class SimConfig:
    seed: int = 0
    gate_closed_frames: int = 0                 # the pause gate is closed from frame 0 for this many frames
    closures: tuple[tuple[int, int], ...] = ()  # more closed intervals [f0, f1)
    input_lat: float = 2                        # frames from emission to arrival at the game's input sampling
    input_jitter_s: float = 0.002               # plus uniform(0, this)
    obs_lat: int = 2                            # frames from a game frame to the machine seeing it
    stall_p: float = 0.0                        # per step, chance that the capture stalls (repeats the last frame)
    stall_max: int = 0                          # ... for 1..stall_max steps
    frame_s: float = FRAME_S
    jitter_s: float = 0.0015
    long_frame_p: float = 0.02                  # chance of a 33 ms frame
    vision: bool = False
    start_paused: bool = False                  # the game pauses on frame 0 (navigation-only trials)
    quit_greyed: bool = False
    greyed_cause: str = "preload"               # "dsq" | "preload"
    dsq_clears_on_refresh: bool = False
    refuse_yes: bool = False
    save_fails: int = 0                         # the first n accepted Yes end in SAVE_FAILED (OK -> the prompt again)
    initial_highlight: str = "continue"
    highlight_visible: bool = True
    prompt_wraps: bool = True
    options_wraps: bool = True
    menu_ready_frames: int = 9
    prompt_ready_frames: int = 21
    options_ready_frames: int = 20
    quit_frames: int = 158
    false_dim_at: int | None = None             # a dark flash (vision dim 0.1, no pause) for 4 frames
    dark_base: float = 0.0                      # a constant dark baseline added to the vision dim
    false_fade_at: int | None = None            # from this frame a fade rising like the dimmer, up to false_fade_to,
    false_fade_to: float = 0.4                  # and staying there
    false_menu: tuple[int, int] | None = None   # frames [f0, f1) where the reader misreads a pause menu while playing
    freezes: tuple[tuple[int, int], ...] = ()   # frames [f0, f1) of a world freeze (hit-stop), gate closed
    death_at: int | None = None


@dataclass
class SimLog:
    pauses: list[float] = field(default_factory=list)            # real time of each pause
    esc_unpauses: list[float] = field(default_factory=list)      # unpauses by a Pause key edge (never intended)
    continue_unpauses: list[float] = field(default_factory=list)
    submits: list[tuple[str, str]] = field(default_factory=list)  # (menu, highlighted item) at each Enter edge
    navs: int = 0                                                 # Up / Down edges seen on a ready menu
    pause_edges: int = 0                                          # Pause edges the game sampled at all
    dropped_pause_edges: int = 0
    pause_edges_while_paused: list[float] = field(default_factory=list)  # (t - pause time) of Pause edges in PAUSED


class PauseSim:
    def __init__(self, cfg: SimConfig):
        self.cfg = cfg
        self.r = random.Random(cfg.seed)
        self.f = -1
        self.t = 0.0
        self.gs = "PLAYING"
        self.pause_allowed_at = 0.0
        self.pause_t: float | None = None
        self.paused_f: int | None = None
        self.menu = M_NONE
        self.menu_ready_f = 0
        self.hl = 0
        self.items: tuple[str, ...] = ()
        self.dim = 0.0
        self.fade = 0.0
        self.greyed = cfg.quit_greyed
        self.save_fails = 0
        self.quit_f: int | None = None
        self.continue_at_f: int | None = None
        self.dead = False
        self.held: frozenset[str] = frozenset()
        self.prev: frozenset[str] = frozenset()
        self.emits: list[tuple[float, frozenset[str]]] = []
        self._last_arrival = 0.0
        self.cues: list[PauseCues] = []
        self.times: list[float] = []
        self._seen: PauseCues | None = None
        self._stall = 0
        self.log = SimLog()

    # ---- input path ------------------------------------------------------------------------------------------------

    def emit(self, keys: frozenset[str], now: float | None = None) -> None:
        """Keys the machine chose at `now` (default: this frame's time); they arrive input_lat frames later, in
        order."""
        cfg = self.cfg
        now = self.t if now is None else now
        arrival = max(self._last_arrival, now + cfg.input_lat * cfg.frame_s + self.r.uniform(0, cfg.input_jitter_s))
        self._last_arrival = arrival
        self.emits.append((arrival, keys))

    def _keys_at(self, t: float) -> frozenset[str]:
        held = self.held
        while self.emits and self.emits[0][0] <= t:
            held = self.emits.pop(0)[1]
        return held

    # ---- game ------------------------------------------------------------------------------------------------------

    def gate_open(self, f: int) -> bool:
        if f < self.cfg.gate_closed_frames:
            return False
        return not any(a <= f < b for a, b in self.cfg.closures + self.cfg.freezes)

    def active_items(self) -> tuple[str, ...]:
        if self.menu == M_PAUSE and self.greyed:
            return ("continue", "options")
        return self.items

    def wraps(self) -> bool:
        return {M_EXIT_PROMPT: self.cfg.prompt_wraps, M_OPTIONS: self.cfg.options_wraps}.get(self.menu, True)

    def _show(self, menu: str, ready_frames: int, items: tuple[str, ...], hl: str) -> None:
        self.menu, self.menu_ready_f, self.items = menu, self.f + ready_frames, items
        self.hl = items.index(hl)

    def _pause(self, dt: float) -> None:
        cfg = self.cfg
        self.gs, self.pause_t, self.paused_f = "PAUSED", self.t, self.f
        self.pause_allowed_at = self.t + 0.3
        self.dim = dt * 3.2
        self._show(M_PAUSE, cfg.menu_ready_frames, PAUSE_ITEMS, cfg.initial_highlight)
        self.log.pauses.append(self.t)

    def advance(self) -> None:
        cfg = self.cfg
        self.f += 1
        f = self.f
        dt = cfg.frame_s * (2 if self.r.random() < cfg.long_frame_p else 1)
        dt += self.r.uniform(-cfg.jitter_s, cfg.jitter_s)
        self.t += dt
        self.prev, self.held = self.held, self._keys_at(self.t)
        edge = self.held - self.prev
        self.log.pause_edges += "pause" in edge
        if cfg.false_fade_at is not None and f >= cfg.false_fade_at:
            self.fade = min(cfg.false_fade_to, self.fade + dt * 3.2)
        if cfg.death_at is not None and f >= cfg.death_at and self.gs == "PLAYING":
            self.dead = True
        if self.dead:
            self._record()
            return
        if f == 0 and cfg.start_paused:
            self._pause(dt)
        elif self.continue_at_f is not None and f >= self.continue_at_f:
            self.continue_at_f = None
            self._unpause()
            self.log.continue_unpauses.append(self.t)
        elif self.gs == "PLAYING":
            if "pause" in edge:
                if self.gate_open(f) and self.t >= self.pause_allowed_at:
                    self._pause(dt)
                else:
                    self.log.dropped_pause_edges += 1
        elif self.gs == "PAUSED":
            self.dim = min(0.8, self.dim + dt * 3.2)
            if "pause" in edge:
                self.log.pause_edges_while_paused.append(self.t - self.pause_t)
                if self.t >= self.pause_allowed_at:
                    self._unpause()
                    self.log.esc_unpauses.append(self.t)
            if self.gs == "PAUSED" and f >= self.menu_ready_f and self.menu != M_NONE:
                self._menu_input(edge)
        elif self.gs == "QUITTING" and f >= self.quit_f:
            self.gs, self.menu = "MAIN_MENU", M_MAIN_MENU
        self._record()

    def _unpause(self) -> None:
        self.gs = "PLAYING"
        self.pause_allowed_at = self.t + 0.3
        self.menu, self.dim, self.items = M_NONE, 0.0, ()

    def _menu_input(self, edge: frozenset[str]) -> None:
        act = self.active_items()
        cur = self.items[self.hl]
        if cur not in act:   # a greyed item never holds the highlight
            cur = act[0]
        if "up" in edge or "down" in edge:
            self.log.navs += 1
            i = act.index(cur) + (-1 if "up" in edge else 1)
            if 0 <= i < len(act) or self.wraps():
                self.hl = self.items.index(act[i % len(act)])
            return
        if "enter" not in edge:
            return
        self.log.submits.append((self.menu, cur))
        cfg = self.cfg
        if self.menu == M_PAUSE:
            if cur == "continue":
                if self.t >= self.pause_allowed_at:
                    self.continue_at_f = self.f + 1
            elif cur == "options":
                self._show(M_OPTIONS, cfg.options_ready_frames, OPTIONS_ITEMS, "game")
            elif cur == "quit":
                self._show(M_EXIT_PROMPT, cfg.prompt_ready_frames, PROMPT_ITEMS, "no")
        elif self.menu == M_EXIT_PROMPT:
            if cur == "yes" and not cfg.refuse_yes:
                if self.save_fails < cfg.save_fails:
                    self.save_fails += 1
                    self._show(M_SAVE_FAILED, 10, ("ok",), "ok")
                else:
                    self.gs, self.quit_f = "QUITTING", self.f + cfg.quit_frames
            elif cur == "no":
                self._show(M_PAUSE, cfg.prompt_ready_frames, PAUSE_ITEMS, "continue")
        elif self.menu == M_SAVE_FAILED:
            self._show(M_EXIT_PROMPT, 2, PROMPT_ITEMS, "no")
        elif self.menu == M_OPTIONS and cur == "back":
            if self.greyed and cfg.greyed_cause == "dsq" and cfg.dsq_clears_on_refresh:
                self.greyed = False
            self._show(M_PAUSE, cfg.prompt_ready_frames, PAUSE_ITEMS, "continue")

    # ---- observation -----------------------------------------------------------------------------------------------

    def _record(self) -> None:
        cfg = self.cfg
        f = self.f
        paused = self.gs in ("PAUSED", "QUITTING", "MAIN_MENU")
        frozen = paused or any(a <= f < b for a, b in cfg.freezes)
        ready = paused and self.menu in (M_PAUSE, M_EXIT_PROMPT, M_OPTIONS, M_SAVE_FAILED) \
            and f >= self.menu_ready_f and self.gs == "PAUSED"
        menu = self.menu if paused or self.menu == M_MAIN_MENU else M_NONE
        if cfg.vision and menu == M_PAUSE and self.paused_f is not None and f - self.paused_f < 3:
            menu = M_NONE                     # the menu is still too faint for the reader
        if cfg.vision and not paused and cfg.false_menu is not None and cfg.false_menu[0] <= f < cfg.false_menu[1]:
            menu = M_PAUSE                    # misread: a pause menu over the running game (never ready)
        hl = None
        if ready and cfg.highlight_visible:
            act = self.active_items()
            cur = self.items[self.hl]
            hl = cur if cur in act else act[0]
        quit_state = cause = None
        if self.menu == M_PAUSE and ready:
            quit_state = QUIT_GREYED if self.greyed else QUIT_AVAILABLE
            cause = cfg.greyed_cause if self.greyed else None
        dim = (self.dim if paused else 0.0) + cfg.dark_base + self.fade
        if cfg.false_dim_at is not None and cfg.false_dim_at <= f < cfg.false_dim_at + 4 and not paused:
            dim += 0.1
        self.cues.append(PauseCues(
            t=self.t, paused=None if cfg.vision else paused, dim=round(dim, 6) if cfg.vision else None,
            frozen=frozen, menu=menu, menu_ready=ready, highlight=hl,
            quit_state=quit_state, quit_cause=cause, quitting=self.gs == "QUITTING", dead=self.dead))
        self.times.append(self.t)

    def cue(self) -> PauseCues:
        """What the machine sees now: the frame obs_lat frames back (the first frame repeats at the start), or during a
        capture stall the last frame it saw."""
        cfg = self.cfg
        if self._stall > 0 and self._seen is not None:
            self._stall -= 1
            return self._seen
        if cfg.stall_max and self.r.random() < cfg.stall_p and self._seen is not None:
            self._stall = self.r.randint(1, cfg.stall_max) - 1
            return self._seen
        self._seen = self.cues[max(0, self.f - cfg.obs_lat)]
        return self._seen


@dataclass
class Run:
    sim: PauseSim
    press_starts: list[float]          # real time of the steps where a Pause press began
    steps: int


def run(machine, sim: PauseSim, max_steps: int, until=None, on_step=None) -> Run:
    """Drive machine and sim: each step the game advances one frame, the machine sees a (latent) cue and emits keys
    at the current game time."""
    press_starts: list[float] = []
    prev: frozenset[str] = sim.emits[-1][1] if sim.emits else frozenset()
    k = 0
    for k in range(max_steps):
        sim.advance()
        keys = machine.step(sim.cue(), sim.t)
        assert keys <= {"pause", "enter", "up", "down"}, keys
        assert len(keys) <= 1, keys
        if "pause" in keys and "pause" not in prev:
            press_starts.append(sim.t)
        prev = keys
        sim.emit(keys)
        if on_step is not None:
            on_step(k, machine, sim)
        if until is not None and until(machine, sim):
            break
    return Run(sim, press_starts, k + 1)
