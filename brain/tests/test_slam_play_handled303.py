"""Task 179 #303 (live 179-L1 w13_walk179_20261105T222716Z_8f9e9629, runtime 8f9e9629): the slam playbook's handled
mark names a slam instance (its antic entry on the clock), not a Clapper.

Live: the playbook ran 335476's first slam (2475-2525); the B2 goal handoff aborted it at 2526 (_close: handled).
The B2 chain then owned the keys until 2683 (candidate_generation True), so SlamPlay.step was never called while
335476 left that slam (Idle, Spell Antic, Cast, Evade Scuttle). 335476 entered a new Slam Antic at 2675. From the
B2 recovery at 2683 step ran every tick, but _two_pick still held 335476 as handled and picked the walking 335470:
no run, the ordinary planner jumped, opened the umbrella and took Slam 1 at 2731 (HP 7 -> 5).
"""
import pytest

from ssbot.combat import slam_play as sp
from tests.test_slam_play import slam_state, state
from tests.test_sp9 import two_state

F0 = 1000          # the first slam's antic entry
F1 = F0 + 200      # the same Clapper's next Slam Antic entry (B2 owned the keys in between)


@pytest.fixture
def two(monkeypatch):
    monkeypatch.setattr(sp, "TWO_PLAY", True)
    yield


def tick(play, f, st, tin, x_rel, two_clappers=True):
    s = two_state(f, st, tin, x_rel=x_rel) if two_clappers else state(f, st, tin, hx=31.0 - x_rel)
    return play.step(f, s, True, True, t_game=f / 60.0)


def handled_then_aborted(two_clappers=True):
    """The playbook starts on F's first slam; the B2 goal handoff then aborts it (policy _chain_goal_preferences)."""
    play = sp.SlamPlay(sp.PlayCfg())
    for k in range(0, 6):
        tick(play, F0 + k, "Slam Antic", k / 60.0, 5.0, two_clappers)
    assert play.run is not None and play.run.iid == 7 and play.active()
    play.abort("observed target transfer: goal handoff")
    assert play.run is None and play._closed_iid == 7
    return play


def test_a_new_slam_after_unstepped_ticks_starts_a_run(two):
    play = handled_then_aborted()
    assert 7 in play._closed
    # not stepped from F0 + 6 to F1 + 9 (B2 owned the keys); the first tick after the hand-back sees F at antic 10
    masks = [tick(play, F1 + k, "Slam Antic", k / 60.0, 3.8) for k in range(10, 14)]
    assert play.run is not None and play.run.iid == 7 and play.run.fa == F1
    assert play.run.phase == "walk" and any(m is not None for m in masks)
    assert 7 not in play._closed and play._closed_iid is None


def test_the_handled_slam_still_gets_no_second_look(two):
    play = handled_then_aborted()
    # stepped again later in the SAME slam (antic entry unchanged): the rest of the antic, Slam 0 .. Slam Recover
    for k in range(20, 90):
        st, tin = slam_state(k)
        if st == "Idle":
            break
        assert tick(play, F0 + k, st, tin, 5.0) is None, k
        assert play.run is None and 7 in play._closed, k


def test_leaving_the_slam_while_stepped_is_unchanged(two):
    play = handled_then_aborted()
    assert tick(play, F0 + 120, "Idle", 0.5, 5.0) is None and 7 not in play._closed
    tick(play, F1 + 2, "Slam Antic", 2 / 60.0, 5.0)
    assert play.run is not None and play.run.fa == F1


def test_single_clapper_path_same_rule(monkeypatch):
    monkeypatch.setattr(sp, "TWO_PLAY", False)
    play = handled_then_aborted(two_clappers=False)
    for k in range(20, 40):
        assert tick(play, F0 + k, "Slam Antic", k / 60.0, 5.0, two_clappers=False) is None
        assert play.run is None and play._closed_iid == 7
    tick(play, F1 + 10, "Slam Antic", 10 / 60.0, 3.8, two_clappers=False)
    assert play.run is not None and play.run.fa == F1 and play._closed_iid is None
