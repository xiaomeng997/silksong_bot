"""combat_run.back_into_slot: the way back into the sandbox slot after a real quit is retried (chain H's campaign died
there twice: 20261003_010522, a new game's opening after the slot-select Enter, load_slot waited 120 s for gameplay;
20261003_074533, guards.set timed out on a freshly started game). A stand-in game drives the menus by the taps."""
import pytest

from ssbot.ipc.framing import mask
from ssbot.ipc.oracle_link import OracleError
from ssbot.probes.common import GS_PLAYING, MENU_MAIN, MENU_SAVE_PROFILES
from ssbot.tools import combat_run
from ssbot.train.encounters import BELL_BEAST


class FakeGame:
    """Title -> save select -> slot 1 (or, with `empty_reads`, a new game: Opening_Sequence without a hero, two jump
    taps skip it, Tut_01 with a hero who takes input after a few frames). A wait_state that the game cannot satisfy
    within `steps` frames times out at once (no real waiting)."""

    def __init__(self, empty_reads: int = 0, guards_timeouts: int = 0, steps: int = 40):
        self.f = 1000
        self.phase = "title"
        self.empty_reads = empty_reads
        self.guards_timeouts = guards_timeouts
        self.steps = steps
        self.jumps = 0
        self.wake = 0
        self.closed = False
        self.calls: list[str] = []
        self.loads = 0

    # ---- the game ----
    def snapshot(self) -> dict:
        game = {"gs": 1, "menu": MENU_MAIN, "scene": "Menu_Title", "paused": False, "fading": False}
        hero, pause = None, {"bench": False, "blk": 0}
        if self.phase == "profiles":
            game["menu"] = MENU_SAVE_PROFILES
        elif self.phase == "opening":
            game.update(gs=combat_run.GS_CUTSCENE, menu=MENU_SAVE_PROFILES, scene="Opening_Sequence")
        elif self.phase in ("tut01_wake", "tut01"):
            game.update(gs=GS_PLAYING, menu=MENU_SAVE_PROFILES, scene="Tut_01")
            hero = {"hero_accepting_input": self.phase == "tut01", "pos": [10.0, 5.0]}
        elif self.phase in ("bonetown", "arena"):
            game.update(gs=GS_PLAYING, menu=MENU_SAVE_PROFILES, scene="Bonetown" if self.phase == "bonetown"
                        else BELL_BEAST.scene)
            hero = {"hero_accepting_input": True, "pos": [78.0, 3.57]}
        return {"f": self.f, "game": game, "hero": hero, "pause": pause}

    def step(self) -> None:
        self.f += 1
        if self.phase == "tut01_wake":
            self.wake += 1
            if self.wake >= 5:
                self.phase = "tut01"

    # ---- the link ----
    @property
    def state(self) -> dict:
        return self.snapshot()

    @property
    def frame(self) -> int:
        return self.f

    def wait_state(self, pred=lambda s: True, timeout_s: float = 10.0, newer_than: int | None = None) -> dict:
        for _ in range(self.steps):
            self.step()
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
        if buttons & mask("enter"):
            self.calls.append("enter")
            if self.phase == "title":
                self.phase = "profiles"
            elif self.phase == "profiles":
                if self.empty_reads > 0:            # the save select read slot 1 as empty: a new game
                    self.empty_reads -= 1
                    self.phase = "opening"
                else:
                    self.phase = "bonetown"
        if buttons & mask("jump"):
            self.calls.append("jump")
            if self.phase == "opening":
                self.jumps += 1
                if self.jumps >= 2:
                    self.phase = "tut01_wake"

    def rpc(self, name: str, /, timeout_s: float = 10.0, **args):
        self.calls.append(name)
        if name == "guards.set":
            if self.guards_timeouts > 0:
                self.guards_timeouts -= 1
                raise TimeoutError()
            return {"save_suppression": args.get("save_suppression", False)}
        if name == "savestate.load":
            if self.phase not in ("tut01", "tut01_wake", "bonetown", "arena"):
                raise OracleError("DebugMod needs a loaded game")
            self.loads += 1
            self.phase = "arena"
            return {"ms": 300}
        return {}


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(combat_run, "NEW_GAME_WAIT_S", 5.0)
    monkeypatch.setattr("ssbot.probes.common.time.sleep", lambda s: None)


def test_plain_way_back_needs_one_try(capsys):
    g = FakeGame()
    combat_run.back_into_slot(g, BELL_BEAST, 4)
    assert g.phase == "bonetown" and g.calls.count("guards.set") == 1 and g.loads == 0
    assert "failed" not in capsys.readouterr().out


def test_new_game_after_the_slot_select_is_recovered(capsys):
    """20261003_010522 at 07:13: the Enter on slot 1 began a new game; the first try times out waiting for gameplay,
    the recovery skips the opening and loads the encounter's savestate, the second try finds gameplay."""
    g = FakeGame(empty_reads=1)
    combat_run.back_into_slot(g, BELL_BEAST, 4)
    out = capsys.readouterr().out
    assert "try 1 of 3" in out and "a cutscene without a hero (Opening_Sequence)" in out
    assert "back in the sandbox slot on try 2" in out
    assert g.jumps >= 2 and g.loads == 1 and g.phase == "arena"
    assert g.calls[-1] == "guards.set"


def test_guards_set_timeout_is_retried(capsys):
    """20261003_074533: guards.set timed out (a freshly started game); the next try sets it."""
    g = FakeGame(guards_timeouts=1)
    combat_run.back_into_slot(g, BELL_BEAST, 4)
    assert g.calls.count("guards.set") == 2
    assert "back in the sandbox slot on try 2" in capsys.readouterr().out


def test_gives_up_after_the_last_try():
    g = FakeGame(guards_timeouts=5)
    with pytest.raises(TimeoutError):
        combat_run.back_into_slot(g, BELL_BEAST, 4, tries=3)
    assert g.calls.count("guards.set") == 3


def test_a_closed_link_is_not_retried():
    g = FakeGame(guards_timeouts=1)
    g.closed = True
    with pytest.raises(TimeoutError):
        combat_run.back_into_slot(g, BELL_BEAST, 4)
    assert g.calls.count("guards.set") == 1
