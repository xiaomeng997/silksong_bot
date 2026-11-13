"""Task 182 package 2 (SSBOT_FORUM_SLAM_START25; the person 11-12 "继续包1和包2吧", quote 99; docs/plans/forum_clapper_committed_chain.md
7.1, 7.11 C): a start on the ground is bounded by the walk into STAND by K_JUMP - 1, not by K_START_MAX 14. The toy slam of
test_slam_play.simulate (antic 48, a mask for STATE f lands at f + 2): start_k is the first tick the script is stepped (another
owner held the keys before), its first mask lands on antic frame start_k + 2."""
import pytest

from ssbot.combat import slam_play as sp
from tests.test_slam_play import keys, simulate


@pytest.fixture
def start25(monkeypatch):
    monkeypatch.setattr(sp, "START25", True)


@pytest.fixture
def old_window(monkeypatch):
    monkeypatch.setattr(sp, "START25", False)


def struck(play, landed):
    c = play.cfg
    return (keys(landed, sp.M_J) == list(range(c.k_jump, c.k_jump + c.hold)) and keys(landed, sp.M_A) == [c.k_press]
            and play.done[-1].k_jump == c.k_jump)


@pytest.mark.parametrize("start_k", [13, 16, 20, 22])
def test_a_late_first_look_in_the_band_takes_the_slam(start25, start_k):
    play, landed, _ = simulate(5.0, start_k=start_k)
    assert play.done[-1].k_start == start_k + sp.SEND_AHEAD
    assert struck(play, landed)


@pytest.mark.parametrize("start_k", [13, 16, 20, 22])
def test_the_old_window_ends_at_14(old_window, start_k):
    play, landed, _ = simulate(5.0, start_k=start_k)
    assert play.done[-1].why == "late" and play.done[-1].k_start is None and not landed


def test_the_latest_start_is_the_walk_by_k_jump(start25):
    # in the band the walk needs 1 frame: the last start lands on antic frame 24 (24 + 1 <= K_JUMP - 1 = 25)
    play, landed, _ = simulate(5.0, start_k=22)
    assert play.done[-1].k_start == 24 and struck(play, landed)
    play, landed, _ = simulate(5.0, start_k=23)
    assert play.done[-1].k_start is None and play.done[-1].why == "no time to walk" and not landed


def test_a_late_look_that_cannot_walk_in_by_25_declines(start25):
    # 8.6 u in front: (8.6 - 5.6) / WALK_U + 1 = 22.8 frames of walk from antic frame 20
    play, landed, _ = simulate(8.6, start_k=18)
    assert play.done[-1].k_start is None and play.done[-1].why == "no time to walk" and not landed


def test_a_walk_that_fits_from_farther(start25):
    # 6.5 u in front at antic frame 17: (6.5 - 5.6) / WALK_U + 1 = 7.5 frames, in STAND by 25
    play, landed, xs = simulate(6.5, start_k=15)
    assert play.done[-1].k_start == 17 and struck(play, landed)
    assert 4.0 <= xs[play.cfg.k_jump] <= 6.2


def test_landing_late_in_the_antic_still_starts(start25):
    # in the air until antic frame 15 (no airborne entry: the first look at 14 is past K_AIR_MAX 10), on the ground from 16
    play, landed, _ = simulate(5.0, start_k=12, ground_until=15)
    assert play.done[-1].k_air is None and play.done[-1].k_start is not None and struck(play, landed)


def test_landing_late_in_the_old_window_is_late(old_window):
    play, landed, _ = simulate(5.0, start_k=12, ground_until=15)
    assert play.done[-1].k_start is None and play.done[-1].why in ("late", "in the air") and not landed


def test_an_early_look_is_unchanged(start25):
    play, landed, _ = simulate(5.0)
    assert play.done[-1].k_start is not None and play.done[-1].k_start <= play.cfg.k_start_max and struck(play, landed)
