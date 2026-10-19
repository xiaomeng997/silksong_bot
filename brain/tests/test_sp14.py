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
    assert gt.TWO_JUMPTRAP is False                    # the suite runs without SSBOT_FORUM_TWO_JUMPTRAP / V2
    # SP14 A/B: unset it follows SSBOT_FORUM_V2; =0 turns it off
    assert gt.jumptrap_on({}) is False and gt.jumptrap_on({"SSBOT_FORUM_V2": "1"}) is True
    assert gt.jumptrap_on({"SSBOT_FORUM_V2": "1", "SSBOT_FORUM_TWO_JUMPTRAP": "0"}) is False
    assert gt.jumptrap_on({"SSBOT_FORUM_TWO_JUMPTRAP": "1"}) is True
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


def test_fp2_exclusions(tac):
    # the other one between her and the jumper (fp2 192650: J 35.7, her 46.84, the other 41.92)
    fc = Fc([S(7, 35.7, gt.CC_JUMP_CAST, "Cast Slam Antic"), S(99, 41.92)])
    assert tac._jt_update(None, fc, 46.84, 1.0) is None and tac.stats["sp7"]["jt_no_o_way"] == 1
    # ... or standing at the jumper's front (fp2 193512: J 29.8, the other 29.68, her 19.08)
    fc = Fc([S(7, 29.8, gt.CC_JUMP_CAST, "Cast Slam Antic"), S(99, 29.68)])
    assert tac._jt_update(None, fc, 19.08, 1.0) is None
    # the far-side focus (the trap) still fires
    fc = Fc([S(7, 36.3, gt.CC_JUMP, "Jump Antic"), S(99, 15.4)])
    assert tac._jt_update(None, fc, 19.6, 1.0) == 7


# ---- SSBOT_FORUM_TWO_CLAWAIR (combat.claw_chase: variant A's Clawline started in the air) ----

def test_clawair_default_off():
    from ssbot.combat import claw_chase as cc
    assert cc.CLAWAIR is False and cc.CA["scope"] == "reach"


def test_clawair_starts_in_the_air_only(monkeypatch):
    from ssbot.combat import claw_chase as cc
    from tests.test_sp10c import cstate, J_X
    monkeypatch.setattr(cc, "CLAWAIR", True)
    c = cc.ClawChase(cc.ClawCfg())
    c.step(1000, cstate(1000, "Idle", 0.5, hx=J_X + 10.0, y_air=1.0), False, True)
    s = cstate(1001, "Jump Antic", 1 / 60.0, hx=J_X + 10.0, y_air=1.0)
    s["hero"]["vel"] = [0.0, 0.0]
    m = c.step(1001, s, False, True)
    r = c.run
    assert r is not None and r.why == "air" and r.hop_hold == 0 and r.phase == "air", dict(c.n)
    assert r.k_press == 1001 + cc.SEND_AHEAD + 1 - 1000 and m == cc.M_L    # the turn now, the press next
    # on the ground: the airborne start does not run (variant A's ground start is off)
    c = cc.ClawChase(cc.ClawCfg())
    c.step(1000, cstate(1000, "Idle", 0.5), True, True)
    assert c.step(1001, cstate(1001, "Jump Antic", 1 / 60.0), True, True) is None and c.run is None
    # behind it: no run
    c = cc.ClawChase(cc.ClawCfg())
    c.step(1000, cstate(1000, "Idle", 0.5, hx=J_X - 6.0, y_air=1.0), False, True)
    s = cstate(1001, "Jump Antic", 1 / 60.0, hx=J_X - 6.0, y_air=1.0)
    s["hero"]["vel"] = [0.0, 0.0]
    assert c.step(1001, s, False, True) is None and c.run is None


# ---- SSBOT_FORUM_TWO_FLIPB (combat.two_play: over B on F's escape jump cast) ----

def fb_state(f, st="Cast Slam Antic", tin=0.05, hx=22.0, b_x=30.0, b_st="Idle", y_air=0.0, clip="Idle"):
    from tests.test_sp9 import two_state
    s = two_state(f, st, tin, cx=16.0, flip=True, hx=hx, b_st=b_st, b_x=b_x, ground=y_air <= 0.0)
    h = s["hero"]
    h["silk"], h["can"], h["anim"] = 3, {"harpoon": True, "dash": True}, {"clip": clip}
    if y_air > 0:
        h["box"] = [h["box"][0], h["box"][1] + y_air, h["box"][2], h["box"][3] + y_air]
    return s


def test_flipb_default_off_and_gate():
    from ssbot.combat import two_play as tp
    assert tp.FLIPB is False and tp.FB["trig"] == "nat"
    two = tp.TwoPlay()
    cs = lambda s: (tp.clapper_by(s, 7), tp.clapper_by(s, 99))
    s = fb_state(1000)
    e, o = cs(s)
    assert two._fb_gate(s, e, o, 22.0) == ""                     # B at 30 stands inside the circle's reach: flip
    s = fb_state(1000, b_x=44.0)
    e, o = cs(s)
    assert two._fb_gate(s, e, o, 22.0) in ("room short of b", "b far")
    s = fb_state(1000, b_st="Slam Antic")
    e, o = cs(s)
    assert two._fb_gate(s, e, o, 22.0) == "b busy"
    s = fb_state(1000, y_air=2.0)
    e, o = cs(s)
    assert two._fb_gate(s, e, o, 22.0) == "air"


def test_flipb_keys():
    from ssbot.combat import two_play as tp
    two = tp.TwoPlay()
    two.esc = tp.EscRun(iid=7, other=99, kind="cast", f_a=1000, k_a=3, x0=16.0, face=1, back0=2.0, rel0=6.0,
                        o_st="Idle", o_d=8.0, mode="flipb", hp0=9,
                        fb={"f0": 1000, "phase": "hop", "k_press": 12, "hook": [], "ds": [], "k_ctrl": None,
                            "k_land": None, "x_land": None, "out": None, "end": ""})
    out = {}
    for f in range(1000, 1060):
        k = f + tp.SEND_AHEAD - 1000
        lock = 14 <= k < 44
        y = 0.0 if k < 2 else 3.0
        s = fb_state(f, hx=22.0 if k < 30 else 27.5, y_air=y, clip="Harpoon Dash" if lock else "Airborne")
        out[k] = two._flipb_step(f, s, y <= 0.0, not lock)
    assert all(out[k] == tp.M_J for k in range(2, 10))
    assert out[11] == tp.M_R and out[12] == out[13] == tp.M_CLAW | tp.M_R
    assert all(out[k] == 0 for k in range(14, 44))
    assert two.esc.fb["phase"] == "after" and out[50] in (tp.M_R, tp._sp.M_D | tp.M_A | tp.M_R)
    assert two.rt_critical() is False or tp.FLIPB                # (critical only with the switch on)
