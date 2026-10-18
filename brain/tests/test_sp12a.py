"""Task 1v1 SP12a: SSBOT_FORUM_TWO_RUNEEXIT (the planner's exit tier for a jump cast's big rune circle still to light)
and SSBOT_FORUM_TWO_STRIKEGUARD (TWO_GUARD on the slam playbook's strike path: the other one's bombs, body, jump / cast
during the walk); both default off."""
import importlib

import numpy as np
import pytest

from ssbot.combat import slam_play as sp
from ssbot.combat import two_play as tp
from tests.test_sp9 import two_state

SW = ("SSBOT_FORUM_TWO_RUNEEXIT", "SSBOT_FORUM_TWO_STRIKEGUARD")
NUM = {"v": 8.25 / 60.0, "buf_f": 8.0, "wall_pad": 0.3}


def test_defaults_off(monkeypatch):
    for k in SW:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SSBOT_FORUM_V2", "1")
    try:
        assert not importlib.reload(tp).RUNEEXIT
        assert not importlib.reload(sp).STRIKEGUARD
        monkeypatch.setenv("SSBOT_FORUM_TWO_RUNEEXIT", "1")
        monkeypatch.setenv("SSBOT_FORUM_TWO_STRIKEGUARD", "1")
        assert importlib.reload(tp).RUNEEXIT and tp.ANY
        assert importlib.reload(sp).STRIKEGUARD
    finally:
        for k in SW + ("SSBOT_FORUM_V2",):
            monkeypatch.delenv(k, raising=False)
        importlib.reload(tp)
        importlib.reload(sp)


def test_exit_late_by_time_wall_and_body():
    # a circle centred at 30, reach 7.72 (edges 22.28 / 37.72), lighting 70 frames after the row's end at k 38
    circ = ((30.0, 7.72, 108.0, 134.0),)
    xs = np.array([30.0, 36.0, 40.0, 24.0])
    # no body: 7.72 u from the centre needs 56 frames + 8 <= 70: in time; outside rows are never late
    assert not tp.rune_exit_late(xs, (circ, (), NUM), 38.0).any()
    # lighting 40 frames after the end: the centre is late, 36.0 (1.72 u from the right edge) is not
    circ2 = ((30.0, 7.72, 78.0, 104.0),)
    late = tp.rune_exit_late(xs, (circ2, (), NUM), 38.0)
    assert late.tolist() == [True, False, False, False]
    # a grounded body at 33 .. 35 blocks the right way for the rows left of it; the left way still in time at 24.0
    body = ((32.45, 35.55, -1e9),)
    late = tp.rune_exit_late(xs, (circ2, body, NUM), 38.0)
    assert late.tolist() == [True, False, False, False]
    late = tp.rune_exit_late(np.array([30.5]), (circ, body, NUM), 38.0)
    assert late.tolist() == [False]                            # left: 8.22 u, 59.8 + 8 <= 70
    late = tp.rune_exit_late(np.array([31.5]), (circ, body, NUM), 38.0)
    assert late.tolist() == [True]                             # left 9.22 u (67 + 8 > 70), right blocked
    # a body that only blocks from frame 200 on (a jumper landing later): the way past it is open
    late = tp.rune_exit_late(np.array([31.5]), (circ, ((32.45, 35.55, 200.0),), NUM), 38.0)
    assert late.tolist() == [False]
    # the right edge past the wall: no way out that side
    circ3 = ((44.0, 7.72, 108.0, 134.0),)
    late = tp.rune_exit_late(np.array([45.0, 41.0]), (circ3, (), NUM), 38.0)
    assert late.tolist() == [True, False]
    # a circle lighting inside the row: the planner's own check (never late here)
    assert not tp.rune_exit_late(xs, (((30.0, 7.72, 20.0, 46.0),), (), NUM), 38.0).any()


def test_rune_exit_circles_from_jump_cast(monkeypatch):
    monkeypatch.setattr(tp, "RUNEEXIT", True)
    monkeypatch.setattr(tp, "GUARD", True)
    two = tp.TwoPlay()
    # B (iid 99) in its jump cast's antic at 40, facing left (toward her at 30); F (iid 7) idle at 20
    s = two_state(100, "Idle", 0.5, cx=20.0, hx=30.0, b_st="Cast Slam Antic", b_x=40.0, b_flip=False)
    two.observe(100, s, 100 / 60.0)
    assert two.rune_exit(100, s, 100 / 60.0) == ()           # no aim yet
    s = two_state(155, "Idle", 0.5, cx=20.0, hx=30.0, b_st="Air", b_x=39.0, b_flip=False)
    two.observe(155, s, 155 / 60.0)
    rx = two.rune_exit(155, s, 155 / 60.0)
    assert rx
    circles, bodies, num = rx
    (cx, reach, k_on, k_off), = circles
    land = 40.0 + 0.92 * max(-12.0, min(12.0, 30.0 + 5.0 - 40.0))
    assert abs(cx - (land - 6.48)) < 1e-6 and abs(reach - 7.72) < 1e-9
    assert abs(k_on - (110 - 55 + 62)) < 1.0 and abs(k_off - (110 - 55 + 88)) < 1.0
    # F's body now; B's around its landing from its landing - 10
    assert any(k_from < -1e8 for _, _, k_from in bodies)
    assert any(abs(0.5 * (lo + hi) - land) < 1e-6 and abs(k_from - 45.0) < 1.0 for lo, hi, k_from in bodies)
    rec = next(iter(two.rx_log.values()))
    assert rec["iid"] == 99 and rec["inside"] == 1
    two.rx_note(155, [3, 10, False])
    assert rec["split"] == 1 and rec["f_split0"] == 155


def _bombs(owner, xs, on_k, off_k, y=3.65):
    return np.array([[owner, x, y, 2.166, on_k, off_k] for x in xs], np.float64)


def test_strikeguard_bomb_on_path_declines(monkeypatch):
    monkeypatch.setattr(sp, "STRIKEGUARD", True)
    monkeypatch.setattr(sp, "TWO_PLAY", True)
    play = sp.SlamPlay()
    play.reset()
    # F (iid 7) in Slam Antic at 31 facing left, her 6 u in front; B (iid 99) idle at 46 with a bomb lit over the
    # stand point (31 - 5.1) from frame 5 to 12 (she still walks / stands there)
    s = two_state(1000, "Slam Antic", 0.0, x_rel=6.0, cx=31.0, b_st="Idle", b_x=46.0)
    bk = _bombs(99, [25.9], 5, 12)
    m = play.step(1000, s, True, True, t_game=1000 / 60.0, bombs=bk)
    assert m is None and play.run.why == "other bomb"
    assert play.sg and play.sg[0][3] == "other bomb" and play.sg[0][4] == "decline"
    # the same bomb lit at frame 60 (she is 6.3 u up in the bounce over the stand point): no decline
    play = sp.SlamPlay()
    play.reset()
    bk = _bombs(99, [25.9], 60, 66)
    play.step(1000, s, True, True, t_game=1000 / 60.0, bombs=bk)
    assert not play.sg
    # the slammer's own bombs do not count
    play = sp.SlamPlay()
    play.reset()
    play.step(1000, s, True, True, t_game=1000 / 60.0, bombs=_bombs(7, [25.9], 5, 12))
    assert not play.sg


def test_strikeguard_off_ignores_bombs(monkeypatch):
    monkeypatch.setattr(sp, "STRIKEGUARD", False)
    monkeypatch.setattr(sp, "TWO_PLAY", True)
    play = sp.SlamPlay()
    play.reset()
    s = two_state(1000, "Slam Antic", 0.0, x_rel=6.0, cx=31.0, b_st="Idle", b_x=46.0)
    a = play.step(1000, s, True, True, t_game=1000 / 60.0, bombs=_bombs(99, [25.9], 5, 12))
    play2 = sp.SlamPlay()
    play2.reset()
    b = play2.step(1000, s, True, True, t_game=1000 / 60.0)
    assert a == b and not play.sg


def test_strikeguard_body_and_walk_abort(monkeypatch):
    monkeypatch.setattr(sp, "STRIKEGUARD", True)
    monkeypatch.setattr(sp, "TWO_PLAY", True)
    # B's body on her way to the stand point: declined
    play = sp.SlamPlay()
    play.reset()
    s = two_state(1000, "Slam Antic", 0.0, x_rel=8.0, cx=31.0, b_st="Idle", b_x=24.0)
    play.step(1000, s, True, True, t_game=1000 / 60.0)
    assert play.run.why == "other body"
    # a started walk aborts when B enters its jump antic before her jump
    play = sp.SlamPlay()
    play.reset()
    s = two_state(1000, "Slam Antic", 0.0, x_rel=6.0, cx=31.0, b_st="Idle", b_x=46.0)
    m = play.step(1000, s, True, True, t_game=1000 / 60.0)
    if play.run is None or play.run.phase != "walk":
        pytest.skip("the playbook did not start its walk in this synthetic state")
    s2 = two_state(1010, "Slam Antic", 10 / 60.0, x_rel=5.5, cx=31.0, b_st="Jump Antic", b_x=46.0)
    m2 = play.step(1010, s2, True, True, t_game=1010 / 60.0)
    assert m2 is None and play.done[-1].phase == "abort" and play.done[-1].why.startswith("sg other Jump Antic")
    assert play.sg[-1][4] == "abort"


def test_strikeguard_bomb_part_off(monkeypatch):
    monkeypatch.setattr(sp, "STRIKEGUARD", True)
    monkeypatch.setattr(sp, "SG_BOMBS", False)
    monkeypatch.setattr(sp, "TWO_PLAY", True)
    play = sp.SlamPlay()
    play.reset()
    s = two_state(1000, "Slam Antic", 0.0, x_rel=6.0, cx=31.0, b_st="Idle", b_x=46.0)
    play.step(1000, s, True, True, t_game=1000 / 60.0, bombs=_bombs(99, [25.9], 5, 12))
    assert not play.sg                                         # the bomb part off: no decline
    play = sp.SlamPlay()
    play.reset()
    s = two_state(1000, "Slam Antic", 0.0, x_rel=8.0, cx=31.0, b_st="Idle", b_x=24.0)
    play.step(1000, s, True, True, t_game=1000 / 60.0)
    assert play.run.why == "other body"                        # the body part stays
