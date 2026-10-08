"""Harness recovery on training instances (ssbot.train.recovery, combat_run, run_episode): a game found paused, in a
pause sub-menu, or in a title sub-menu is brought back with verified taps, or the episode ends HARNESS_FAIL quickly
instead of the worker stalling. A stand-in game models the menus the way 1.0.30000 does (pause menu Continue / Options
/ Quit wrapping, Options with unnamed items above Back, the exit prompt Yes above No, the title's main menu and its
sub-menus, Esc as MenuCancel on the title) and records every key, so the tests check that no Submit lands on anything
but Continue / Back / No, that Esc is never pressed while paused, and that the main menu's Enter is not repeated inside
another menu (20261005_164501_Forum_A_w2_mix_data2_2 i1: Main -> Options -> Game options)."""
import json
from dataclasses import replace

import pytest

from ssbot.ipc.framing import BUTTONS, mask
from ssbot.probes import common
from ssbot.tools import combat_run
from ssbot.train import recovery
from ssbot.train.encounters import BELL_BEAST
from ssbot.train.episode import HARNESS_FAIL, AttemptRecord, EpisodeConfig, make_tap, run_episode

M = recovery
PAUSE_ITEMS = ["continue", "options", "quit"]
OPTIONS_ITEMS = [None] * 5 + ["back"]            # Game, Audio, Video, Controller, Keyboard, Back
GAME_OPTIONS_ITEMS = [None] * 9 + ["back"]
PROMPT_ITEMS = ["yes", "no"]
TITLE_ITEMS = [M.MENU_SAVE_PROFILES, M.MENU_OPTIONS, M.MENU_ACHIEVEMENTS, M.MENU_EXTRAS, M.MENU_QUIT_GAME_PROMPT]
LOCKOUT_FRAMES = 18


class MenuGame:
    """The game's menus as far as the harness sees them. mode "game" (playing in the arena), "paused" (menu PAUSE /
    OPTIONS / GAME_OPTIONS / EXIT_PROMPT with a highlighted index), "title" (MAIN / a sub-menu / SAVE_PROFILES), "slot"
    (the sandbox slot loaded: gameplay in Bonetown). Keys act at once; every wait_state advances frames."""

    def __init__(self, mode: str = "game", menu: int | None = None, idx: int = 0, steps: int = 40,
                 lockout: int = 0, title_idx: int = 0, sel_none_frames: int = 0, stuck_sel: bool = False):
        self.f = 5000
        self.mode = mode
        self.menu = menu
        self.idx = idx
        self.title_idx = title_idx
        self.steps = steps
        self.lock_until = self.f + lockout
        self.sel_none_until = self.f + sel_none_frames
        self.stuck_sel = stuck_sel          # a highlight that never reads (no "back" ever)
        self.keys: list[tuple[str, int | None, object]] = []   # (key, menu, highlight) at the press
        self.calls: list[str] = []
        self.closed = False
        self.loads = 0

    # ---- the game ----
    def items(self):
        return {M.MENU_PAUSE: PAUSE_ITEMS, M.MENU_OPTIONS: OPTIONS_ITEMS, 12: GAME_OPTIONS_ITEMS,
                M.MENU_EXIT_PROMPT: PROMPT_ITEMS}.get(self.menu, [None])

    def sel(self):
        if self.mode != "paused" or self.f < self.sel_none_until:
            return None
        if self.stuck_sel:
            return None
        it = self.items()
        return it[self.idx % len(it)]

    def snapshot(self) -> dict:
        f = self.f
        if self.mode in ("game", "slot"):
            scene = BELL_BEAST.scene if self.mode == "game" else "Bonetown"
            return {"f": f, "game": {"gs": M.GS_PLAYING, "ui": 4, "menu": M.MENU_PAUSE, "paused": False,
                                     "fading": False, "scene": scene},
                    "menu": None, "pause": {"blk": 0, "bench": False},
                    "hero": {"hero_accepting_input": True, "pos": [78.0, 3.57]}}
        if self.mode == "paused":
            blk = M.BLK_PAUSE_LOCKOUT if f < self.lock_until else 0
            return {"f": f, "game": {"gs": M.GS_PAUSED, "ui": M.UI_PAUSED, "menu": self.menu, "paused": True,
                                     "fading": False, "scene": BELL_BEAST.scene},
                    "menu": {"sel": self.sel(), "quit_ok": True, "dim": 0.8, "alpha": 1.0, "ignore_unpause": False,
                             "quitting": False},
                    "pause": {"blk": blk | 64, "bench": False}, "hero": {"hero_accepting_input": True,
                                                                         "pos": [78.0, 3.57]}}
        if self.mode == "quitting":         # the quit's scene on the way to the title (20261002_080522 i0)
            return {"f": f, "game": {"gs": 6, "ui": 2, "menu": M.MENU_PAUSE, "paused": False, "fading": False,
                                     "scene": M.QUIT_SCENE}, "menu": None, "pause": None, "hero": None}
        return {"f": f, "game": {"gs": M.GS_MAIN_MENU, "ui": 1, "menu": self.menu, "paused": False, "fading": False,
                                 "scene": "Menu_Title"}, "menu": None, "pause": None, "hero": None}

    def press(self, key: str) -> None:
        self.keys.append((key, self.menu if self.mode != "game" else None, self.sel()))
        if self.mode == "paused":
            self._paused_key(key)
        elif self.mode == "title":
            self._title_key(key)

    def _paused_key(self, key: str) -> None:
        it = self.items()
        if key in ("up", "down"):
            self.idx = (self.idx + (-1 if key == "up" else 1)) % len(it)
            return
        if key == "pause":
            raise AssertionError("Esc pressed while paused")
        if key != "enter":
            return
        sel = it[self.idx % len(it)] if not self.stuck_sel else None
        if self.menu == M.MENU_PAUSE:
            if sel == "continue":
                if self.f >= self.lock_until:
                    self.mode, self.menu = "game", M.MENU_PAUSE
            elif sel == "options":
                self.menu, self.idx = M.MENU_OPTIONS, 0
            elif sel == "quit":
                self.menu, self.idx = M.MENU_EXIT_PROMPT, 1          # the prompt opens on No
        elif self.menu == M.MENU_EXIT_PROMPT:
            if sel == "yes":
                raise AssertionError("Submit on Yes: a real quit")
            self.menu, self.idx = M.MENU_PAUSE, 2
        elif self.menu == M.MENU_OPTIONS:
            if sel == "back":
                self.menu, self.idx = M.MENU_PAUSE, 1                # back on the pause menu, Options highlighted
            else:
                raise AssertionError(f"Submit on an Options item ({self.idx})")
        elif self.menu == 12:
            if sel == "back":
                self.menu, self.idx = M.MENU_OPTIONS, 0
            else:
                raise AssertionError("Submit on a game setting")

    def _title_key(self, key: str) -> None:
        if self.menu == M.MENU_MAIN:
            if key in ("up", "down"):
                self.title_idx = max(0, min(len(TITLE_ITEMS) - 1, self.title_idx + (-1 if key == "up" else 1)))
            elif key == "enter":
                self.menu = TITLE_ITEMS[self.title_idx]
                self.idx = 0
            elif key == "pause":
                self.menu = M.MENU_QUIT_GAME_PROMPT                   # Cancel on the main menu: the quit prompt
        elif self.menu == M.MENU_SAVE_PROFILES:
            if key == "enter":
                self.mode = "slot"
        else:
            if key == "enter":
                if self.menu == M.MENU_OPTIONS:
                    self.menu = 12                                    # Options -> Game options
                elif self.menu == M.MENU_QUIT_GAME_PROMPT:
                    raise AssertionError("Submit on the quit-game prompt")
                else:
                    self.calls.append(f"enter in title menu {self.menu}")
            elif key == "pause":                                      # MenuCancel: one level back
                self.menu = M.MENU_OPTIONS if self.menu == 12 else M.MENU_MAIN

    # ---- the link ----
    @property
    def state(self) -> dict:
        return self.snapshot()

    @property
    def frame(self) -> int:
        return self.f

    def wait_state(self, pred=lambda s: True, timeout_s: float = 10.0, newer_than: int | None = None) -> dict:
        for _ in range(self.steps):
            self.f += 1
            if self.mode == "quitting" and self.f >= self.lock_until:
                self.mode, self.menu = "title", M.MENU_MAIN
            s = self.snapshot()
            if newer_than is not None and s["f"] <= newer_than:
                continue
            try:
                if pred(s):
                    return s
            except (KeyError, TypeError):
                pass
        raise TimeoutError(f"state condition not met within {timeout_s}s (last frame {self.f})")

    def act(self, target: int, buttons: int, hold_frames: int = 0, ack_seq: int = 0, flags: int = 0) -> None:
        for name in BUTTONS:
            if buttons & mask(name):
                self.press(name)

    def rpc(self, name: str, /, timeout_s: float = 10.0, **args):
        self.calls.append(name)
        if name == "guards.set":
            return {"save_suppression": True}
        if name == "savestate.load":
            self.loads += 1
            self.mode = "game"
            return {"ms": 300}
        return {}

    def submits(self) -> list[tuple[int | None, object]]:
        return [(m, sel) for k, m, sel in self.keys if k == "enter"]


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr("ssbot.probes.common.time.sleep", lambda s: None)
    monkeypatch.setattr("ssbot.train.recovery.SEL_WAIT_S", 0.0)


# ---- where / pause_cause ------------------------------------------------------------------------------------------

def test_where_reads_the_menus():
    assert M.where(MenuGame("game").state) == "game"
    assert M.where(MenuGame("paused", M.MENU_PAUSE).state) == "pause_menu"
    assert M.where(MenuGame("paused", M.MENU_OPTIONS).state) == "pause_submenu"
    assert M.where(MenuGame("paused", 12).state) == "pause_submenu"
    assert M.where(MenuGame("paused", M.MENU_EXIT_PROMPT).state) == "exit_prompt"
    assert M.where(MenuGame("title", M.MENU_MAIN).state) == "title"
    assert M.where(MenuGame("title", M.MENU_SAVE_PROFILES).state) == "save_select"
    assert M.where(MenuGame("title", 12).state) == "title_submenu"         # 20261005_164501 i1
    assert M.where(MenuGame("title", M.MENU_QUIT_GAME_PROMPT).state) == "title_submenu"
    assert M.where({"f": 1, "game": None}) == "no_game"
    # the pause menu still fading in, GoToPauseMenu running, or a stale menuState in the first paused frames: wait
    s = MenuGame("paused", M.MENU_PAUSE).state
    s["menu"]["alpha"] = 0.4
    assert M.where(s) == "pause_opening"
    s = MenuGame("paused", M.MENU_SAVE_PROFILES).state
    s["menu"]["ignore_unpause"] = True
    assert M.where(s) == "pause_opening"
    # menuState still SAVE_PROFILES from the title, the pause menu already up with Continue: the role decides
    s["menu"].update(ignore_unpause=False, sel="continue")
    assert M.where(s) == "pause_menu"
    s["menu"]["sel"] = "no"
    assert M.where(s) == "exit_prompt"
    # past the quit's save (menu.quitting), or the Quit_To_Menu scene: nothing to press
    s["menu"]["quitting"] = True
    assert M.where(s) == "quitting"


def test_pause_cause_from_the_first_paused_state():
    """The 60 brain-lost pauses of 2026-10-02 .. 06 show act.lost and the injected Pause bit on the pause frame; the
    Lace 1 one (20261006_065605 i0) neither (no Pause key read, no lost brain)."""
    s = {"f": 31537, "act": {"lost": True, "mask": mask("pause"), "applied": 31524}, "input": {"mask": mask("pause")}}
    assert M.pause_cause(s) == "brain-lost watchdog, last ACTION applied 13 frames before"
    s = {"f": 10, "act": {"lost": False, "mask": mask("right")}, "input": {"mask": mask("pause", "right")}}
    assert M.pause_cause(s) == "a Pause key the harness did not press"
    s = {"f": 3064606, "act": {"lost": False, "mask": mask("right", "jump"), "applied": 3064606},
         "input": {"mask": mask("right", "jump")}}
    assert M.pause_cause(s).startswith("no Pause key")


# ---- resume -------------------------------------------------------------------------------------------------------

def _resume(g: MenuGame):
    ok, steps = M.resume(g, timeout_s=5.0)
    assert all(k != "pause" for k, _, _ in g.keys), "Esc while paused"
    assert all(sel in ("continue", "back", "no") for _, sel in g.submits()), g.submits()
    return ok, steps


def test_resume_from_continue_is_one_submit():
    g = MenuGame("paused", M.MENU_PAUSE, idx=0)
    ok, steps = _resume(g)
    assert ok and g.mode == "game" and [k for k, _, _ in g.keys] == ["enter"]
    assert g.calls.count("input.release") == 2          # before (no watchdog re-arm) and after


def test_resume_waits_out_the_lockout():
    g = MenuGame("paused", M.MENU_PAUSE, idx=0, lockout=LOCKOUT_FRAMES)
    ok, _ = _resume(g)
    assert ok and [k for k, _, _ in g.keys] == ["enter"]       # no Submit dropped into the lockout


@pytest.mark.parametrize("idx,ups", [(1, 1), (2, 2)])
def test_resume_moves_off_options_and_quit_before_the_submit(idx, ups):
    """Mouse hover moves the highlight (probe P7): the old blind Submit opened Options from here."""
    g = MenuGame("paused", M.MENU_PAUSE, idx=idx)
    ok, _ = _resume(g)
    assert ok and [k for k, _, _ in g.keys] == ["up"] * ups + ["enter"]


def test_resume_from_the_options_menu_goes_back_first():
    g = MenuGame("paused", M.MENU_OPTIONS, idx=0)
    ok, steps = _resume(g)
    assert ok and g.mode == "game"
    assert g.submits() == [(M.MENU_OPTIONS, "back"), (M.MENU_PAUSE, "continue")]
    assert [k for k, _, _ in g.keys].count("down") == 5 and steps[-1].endswith("enter")


def test_resume_from_a_settings_sub_menu_backs_out_twice():
    g = MenuGame("paused", 12, idx=3)
    ok, _ = _resume(g)
    assert ok and g.submits() == [(12, "back"), (M.MENU_OPTIONS, "back"), (M.MENU_PAUSE, "continue")]


def test_resume_from_the_exit_prompt_says_no():
    g = MenuGame("paused", M.MENU_EXIT_PROMPT, idx=0)       # Yes highlighted
    ok, _ = _resume(g)
    assert ok and g.submits() == [(M.MENU_EXIT_PROMPT, "no"), (M.MENU_PAUSE, "continue")]
    assert g.keys[0][0] == "down"


def test_resume_waits_for_a_highlight_then_gives_up_without_a_blind_submit():
    """A sub-menu whose Back never reads: Down up to MAX_NAV times, no Submit, (False, steps): the caller ends the
    episode HARNESS_FAIL instead of hanging."""
    g = MenuGame("paused", M.MENU_OPTIONS, stuck_sel=True)
    ok, steps = _resume(g)
    assert not ok and g.submits() == [] and steps[-1].startswith("gave up")
    assert sum(1 for k, _, _ in g.keys if k == "down") == M.MAX_NAV


def test_resume_is_a_no_op_when_not_paused():
    g = MenuGame("game")
    assert M.resume(g) == (True, []) and g.keys == []


# ---- title ----------------------------------------------------------------------------------------------------------

def test_title_home_backs_out_of_game_options_with_esc():
    """20261005_164501_Forum_A_w2_mix_data2_2 i1: Menu_Title with menuState 12 (Game options)."""
    g = MenuGame("title", 12)
    ok, steps = M.title_home(g)
    assert ok and g.menu == M.MENU_MAIN and [k for k, _, _ in g.keys] == ["pause", "pause"]


def test_title_home_never_presses_esc_on_the_main_menu():
    g = MenuGame("title", M.MENU_MAIN)
    assert M.title_home(g) == (True, []) and g.keys == []


def test_load_slot_does_not_repeat_enter_inside_another_menu():
    """The main menu highlights Options: one Enter opens Options, then MenuError, not two more Enters into Game options
    and a setting (the old press_until retried until the save select)."""
    g = MenuGame("title", M.MENU_MAIN, title_idx=1)
    with pytest.raises(common.MenuError) as e:
        common.load_slot(g, 1)
    assert e.value.menu == M.MENU_OPTIONS and [k for k, _, _ in g.keys] == ["enter"]


def test_back_into_slot_recovers_from_a_highlight_on_options(capsys):
    g = MenuGame("title", M.MENU_MAIN, title_idx=1)
    combat_run.back_into_slot(g, BELL_BEAST, 1)
    out = capsys.readouterr().out
    assert g.mode == "slot" and "MenuError" in out and "back in the sandbox slot on try 2" in out
    assert [k for k, _, _ in g.keys] == ["enter", "pause", "up", "enter", "enter"]   # Options, Esc, Up, Start, slot


def test_back_into_slot_starts_from_a_title_sub_menu(capsys):
    """The worker found the title in Game options (a person had to press Esc): load_slot leaves it with Esc first."""
    g = MenuGame("title", 12)
    combat_run.back_into_slot(g, BELL_BEAST, 1)
    assert g.mode == "slot" and [k for k, _, _ in g.keys] == ["pause", "pause", "enter", "enter"]
    assert "failed" not in capsys.readouterr().out


def test_back_into_slot_from_the_achievements_item_moves_up_twice():
    g = MenuGame("title", M.MENU_MAIN, title_idx=2)
    combat_run.back_into_slot(g, BELL_BEAST, 1)
    assert g.mode == "slot" and [k for k, _, _ in g.keys] == ["enter", "pause", "up", "up", "enter", "enter"]


# ---- worker -----------------------------------------------------------------------------------------------------------

def test_after_harness_fail_by_place(capsys):
    g = MenuGame("paused", M.MENU_OPTIONS)
    assert combat_run.after_harness_fail(g, BELL_BEAST, 1).startswith("pause_submenu: unpaused")
    assert g.mode == "game"
    g = MenuGame("title", M.MENU_MAIN)            # a quit nobody asked for (20261002_080522 i0, Quit_To_Menu)
    assert combat_run.after_harness_fail(g, BELL_BEAST, 1) == "title: back into the sandbox slot"
    assert g.mode == "slot"
    g = MenuGame("game")
    assert combat_run.after_harness_fail(g, BELL_BEAST, 1) is None and g.keys == []


def test_after_harness_fail_lets_a_quit_reach_the_title_first():
    """20261002_080522 i0: "left the scene: Quit_To_Menu", then three episodes failed "savestate.load: no game
    loaded". Now the worker waits for the title and goes back into the sandbox slot."""
    g = MenuGame("quitting", lockout=25)          # the title comes 25 frames on
    assert M.where(g.state) == "quitting"
    assert combat_run.after_harness_fail(g, BELL_BEAST, 1) == "title: back into the sandbox slot"
    assert g.mode == "slot" and [k for k, _, _ in g.keys] == ["enter", "enter"]


def test_a_paused_game_is_not_a_game_without_control():
    """_unstick used to load the savestate under a pause menu (DebugMod clears isPaused, the menu stays up)."""
    assert not combat_run._in_game_without_control(MenuGame("paused", M.MENU_PAUSE).state)


def test_unstick_resumes_a_paused_game_instead_of_loading():
    g = MenuGame("paused", M.MENU_OPTIONS)
    combat_run._unstick(g, BELL_BEAST, lambda m: None)
    assert g.mode == "game" and g.loads == 0


def test_summary_groups_harness_fails_and_loop_gaps(tmp_path):
    rows = [{"outcome": "HARNESS_FAIL", "reason": f"paused unasked at frame {f} (brain-lost watchdog, last ACTION "
                                                  "applied 13 frames before)", "config_fp": "a", "ingame_s": 1.0,
             "wall_s": 2.0, "hits": 0, "would_die": 0, "attacks": {}, "loop_gap_ms_max": g, "loop_gaps_250": n}
            for f, g, n in ((31537, 260.0, 1), (199470, 17.0, 0))]
    rows.append({**rows[1], "outcome": "CLEAR", "reason": None, "loop_gap_ms_max": 20.0})
    (tmp_path / "attempts_i0.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    out = combat_run.summary(tmp_path, write=False)
    assert out["harness_fails"] == {"paused unasked at frame N (brain-lost watchdog, last ACTION applied 13 frames "
                                    "before)": 2}
    assert out["loop_gap_ms"] == {"p50": 20.0, "max": 260.0, "episodes_over_250": 1}


# ---- episode --------------------------------------------------------------------------------------------------------

class _Link:
    """Scripted STATEs (as tests/test_episode_post_clear.py); records RPCs."""

    def __init__(self, states):
        self.states, self.i, self.subs, self.state, self.calls = states, 0, [], None, []

    @property
    def frame(self):
        return self.state["f"] if self.state else 0

    def subscribe_state(self, fn):
        self.subs.append(fn)

    def wait_state(self, pred=None, newer_than=None, timeout_s=2.0):
        while self.i < len(self.states):
            s = self.states[self.i]
            self.i += 1
            self.state = s
            for fn in self.subs:
                fn(s)
            if (newer_than is None or s["f"] > newer_than) and (pred is None or pred(s)):
                return s
        raise TimeoutError("script exhausted")

    def rpc(self, method, **kw):
        self.calls.append(method)
        return {"seed": kw.get("seed")} if method == "randomize_start" else {}

    def act(self, f, m, hold_frames=0, flags=0):
        pass


class _Policy:
    def reset(self, rng, enc):
        pass

    def act(self, s, tap):
        return 0


def _st(f, scene, paused=False, act=None, ev=()):
    return {"f": f, "game": {"scene": scene, "paused": paused, "gs": M.GS_PAUSED if paused else M.GS_PLAYING},
            "hero": {"pos": [30.0, 4.57, 0.0], "hero_accepting_input": True}, "ev": list(ev), "act": act or {},
            "input": {}}


def _intro(ctx):
    while ctx.tap.wake_frame is None:
        ctx.link.wait_state(newer_than=ctx.link.frame)
    return ctx.tap.wake_frame


WAKE = {"k": "fsm", "d": {"obj": "Bone Beast", "fsm": "Control", "to": "Emerge", "from": "Dormant"}}


def _episode(states, start=None):
    enc = replace(BELL_BEAST, intro=_intro)
    link = _Link(states)
    link.state = start
    tap = make_tap(link, enc)
    rec = AttemptRecord(unit="t", stage="t", profile="t", build="t", code_rev=None, config_fp="", start_kind="t",
                        mode="data", seed=1)
    run_episode(link, enc, tap, _Policy(), EpisodeConfig(mode="data", seed=1, facing=None), rec)
    return rec, link


def test_paused_unasked_names_the_brain_lost_watchdog():
    scene = BELL_BEAST.scene
    states = [_st(f, scene) for f in range(1, 15)] + [_st(15, scene, ev=[WAKE])]
    states += [_st(f, scene) for f in range(16, 60)]
    states.append(_st(60, scene, paused=True, act={"lost": True, "mask": mask("pause"), "applied": 47}))
    rec, _ = _episode(states)
    assert rec.outcome == HARNESS_FAIL
    assert rec.reason == "paused unasked at frame 60 (brain-lost watchdog, last ACTION applied 13 frames before)"
    assert rec.loop_gap_ms_max is not None and rec.loop_gaps_250 == 0


def test_a_pause_that_does_not_end_fails_the_episode_before_the_reset(monkeypatch):
    """The episode's start finds the game paused in a menu resume cannot leave: HARNESS_FAIL at once, no savestate
    load under the pause menu, no hang."""
    monkeypatch.setattr(M, "resume", lambda link, **kw: (False, ["pause_submenu:None:down"] * 3))
    start = _st(1, BELL_BEAST.scene, paused=True)
    rec, link = _episode([], start=start)
    assert rec.outcome == HARNESS_FAIL and rec.reason.startswith("RuntimeError: still paused before the reset")
    assert "savestate.load" not in link.calls


def test_a_pause_found_at_the_start_is_resumed_and_the_episode_runs(monkeypatch):
    seen = []
    monkeypatch.setattr(M, "resume", lambda link, **kw: (seen.append(1), (True, ["pause_menu:continue:enter"]))[1])
    scene = BELL_BEAST.scene
    states = [_st(f, scene) for f in range(2, 15)] + [_st(15, scene, ev=[WAKE])] + [_st(f, scene) for f in range(16, 40)]
    rec, link = _episode(states, start=_st(1, scene, paused=True))
    assert seen == [1] and "savestate.load" in link.calls and rec.f_wake == 15
