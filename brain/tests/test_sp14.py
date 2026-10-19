"""SP14: SSBOT_FORUM_TWO_JUMPTRAP (combat.tactics.gauntlet) - the other one's jump move whose landing traps her short of
its far-side obstacle makes the jumper the goal's target until its move (a jump cast: its circle's hold) ends."""
from __future__ import annotations

import pytest

from ssbot.combat.tactics import gauntlet as gt


class S:
    def __init__(self, iid, x, family=None, state="Idle"):
        self.iid, self.type_key, self.alive, self.in_play = iid, gt.CLAPPER, True, True
        self.pos = (x, 7.45)
        self.family, self.state = family, state


class Fc:
    def __init__(self, subs):
        self.subjects = subs


@pytest.fixture
def tac(monkeypatch):
    from tests.test_forum_l2 import l2
    t = l2()
    monkeypatch.setattr(gt, "TWO_JUMPTRAP", True)
    monkeypatch.setattr(gt.GauntletTactics, "_ent", lambda self, ws, iid: None)          # facing = toward her
    monkeypatch.setattr(gt.GauntletTactics, "_body", staticmethod(lambda fc, s: (float(s.pos[0]), 1.0)))
    t.goal = gt.Goal(gt.RUSH, 99, 16.0, 0.0)
    t.t_commit = {7: 1.0, 99: 0.0}
    return t


def test_default_off():
    assert gt.TWO_JUMPTRAP is False                    # the suite runs without SSBOT_FORUM_TWO_JUMPTRAP
    assert gt.JT["gap_u"] == 2.0 and gt.JT["force"] == 0.0 and gt.JT["jc_back_u"] == 8.0


def test_far_jump_with_the_focus_at_her_back_fires(tac):
    # SP13b b2 162817 i1 e0: A (7) at 36.3 jumps at her (19.6), the focus B (99) Idle at 15.4 by the left wall:
    # landing 36.3 - 0.916 * 11.7 = 25.58, its hammer + her half width to 17.57, B box + pad from 16.65: gap 0.92
    fc = Fc([S(7, 36.3, gt.CC_JUMP, "Jump Antic"), S(99, 15.4)])
    assert tac._jt_update(None, fc, 19.6, 1.0) == 7
    jt = tac._jt
    assert jt["kind"] == "jump" and jt["land"] == pytest.approx(25.58, abs=0.01) and jt["gap"] == pytest.approx(0.92, abs=0.02)
    # held through the flight, released after the move; the same move never fires again
    fc.subjects[0].family, fc.subjects[0].state = gt.CC_JUMP, "Air"
    assert tac._jt_update(None, fc, 21.0, 1.5) == 7
    fc.subjects[0].family, fc.subjects[0].state = None, "Idle"
    assert tac._jt_update(None, fc, 21.0, 2.0) is None and tac._jt is None and tac.jt_runs[0]["t_end"] == 2.0


def test_room_on_the_far_side_does_not_fire(tac):
    # her at 26 (landing 31.76, the hammer to 23.75), B's box from 16.65: 7.1 u of floor
    fc = Fc([S(7, 40.0, gt.CC_JUMP, "Jump Antic"), S(99, 15.4)])
    assert tac._jt_update(None, fc, 26.0, 1.0) is None and tac._jt is None
    # force=1 takes it anyway
    gt.JT["force"] = 1.0
    try:
        assert tac._jt_update(None, fc, 26.0, 1.0) == 7
    finally:
        gt.JT["force"] = 0.0


def test_escape_cast_other_jumping_and_target_not_taken(tac):
    # a jump cast with its back 2 u from its wall: the escape cast (TWO_WALLSWITCH / FLIPB)
    fc = Fc([S(7, 16.0, gt.CC_JUMP_CAST, "Cast Slam Antic"), S(99, 30.0)])
    assert tac._jt_update(None, fc, 20.0, 1.0) is None
    # the other one in a jump move too
    fc = Fc([S(7, 36.3, gt.CC_JUMP, "Jump Antic"), S(99, 15.4, gt.CC_JUMP, "Jump Antic")])
    assert tac._jt_update(None, fc, 19.6, 1.0) is None
    # the jumper is the target already
    tac.goal = gt.Goal(gt.RUSH, 7, 30.0, 0.0)
    fc = Fc([S(7, 36.3, gt.CC_JUMP, "Jump Antic"), S(99, 15.4)])
    assert tac._jt_update(None, fc, 19.6, 1.0) is None
    # one Clapper: nothing
    tac.goal = gt.Goal(gt.RUSH, 99, 16.0, 0.0)
    assert tac._jt_update(None, Fc([S(7, 36.3, gt.CC_JUMP, "Jump Antic")]), 19.6, 1.0) is None


def test_far_jump_cast_fires_and_holds_through_the_circle(tac):
    # 171500 i0 e0: A at 39.0 jump-casts at her (26.5), B at 22.7: the circle reaches 13.67 u past the landing
    fc = Fc([S(7, 39.0, gt.CC_JUMP_CAST, "Cast Slam Antic"), S(99, 22.7)])
    assert tac._jt_update(None, fc, 26.5, 1.0) == 7 and tac._jt["kind"] == "jc"
    fc.subjects[0].family, fc.subjects[0].state = None, "Idle"
    tac.rune[7] = (28.0, -1.0, "under and behind", 3.0)        # gauntlet's own circle record (until 3.0)
    assert tac._jt_update(None, fc, 30.0, 2.5) == 7
    assert tac._jt_update(None, fc, 30.0, 3.1) is None


def test_two_focus_targets_the_jumper(tac, monkeypatch):
    seen = {}
    monkeypatch.setattr(gt.GauntletTactics, "_goal", lambda self, ws, c, name, t, score, t_end=None, why="":
                        seen.update(target=c.s.iid, why=why) or seen)
    monkeypatch.setattr(gt.GauntletTactics, "_outer_room", lambda self, c, o: 5.0)

    class C:
        def __init__(self, s):
            self.s, self.x, self.d = s, float(s.pos[0]), abs(float(s.pos[0]) - 19.6)

    a, b = S(7, 36.3, gt.CC_JUMP, "Jump Antic"), S(99, 15.4)
    tac._jt_update(None, Fc([a, b]), 19.6, 1.0)
    tac._two_focus(None, [C(a), C(b)], 1.0, None)
    assert seen["target"] == 7 and seen["why"].startswith("two: jumptrap jump")


def test_fp1_exclusions(tac):
    # the other one slamming / casting at the trigger: its move first (fp1: hit at +5 / +7 by its hammer)
    for st in ("Slam Antic", "Slam 0", "Spell Antic", "Cast 2"):
        fc = Fc([S(7, 36.3, gt.CC_JUMP, "Jump Antic"), S(99, 15.4, "CC_SLAM", st)])
        assert tac._jt_update(None, fc, 19.6, 1.0) is None
    # the other one standing at the spot behind the landing (fp1 185647: landing 22.29, spot 25.79, the other at 27.16)
    tac.goal = gt.Goal(gt.RUSH, 99, 16.0, 0.0)
    fc = Fc([S(7, 23.6, gt.CC_JUMP, "Jump Antic"), S(99, 26.4)])
    assert tac._jt_update(None, fc, 14.6, 1.0) is None
    assert tac.stats["sp7"]["jt_no_o_back"] == 1
