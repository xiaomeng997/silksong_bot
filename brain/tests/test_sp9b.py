"""Task 1v1 SP9b (forum.md 77): the focus's escape jump at a wall with two Clappers - arm A SSBOT_FORUM_TWO_CORNER (the
antic slashes, the way under to the corner, its back, then off the wall: the hop over it after its evade coin / the
jump cast's rune burst) and arm B SSBOT_FORUM_TWO_WALLSWITCH (L2 on the other one, no hit on it during the focus's lock,
the deciding hit in the focus's tail); both default off (ssbot.combat.two_play, cast_stab, tactics.gauntlet)."""
import importlib

import pytest

from ssbot.combat import cast_stab as cs
from ssbot.combat import slam_play as sp
from ssbot.combat import two_play as tp
from ssbot.combat.tactics import gauntlet as gt
from tests.test_forum_l2 import CC, WinFc, clapper, l2, subj, world
from tests.test_sp9 import two_state

WALL_X = tp.WALL_L + 3.99                 # F at the left wall facing right (flipX): its back 3.99 u from the wall


def fstate(f, st, tin=0.0, hx=None, x_rel=4.0, b_st="Idle", b_x=40.0, ground=True, facing=None, ev=(), ents=()):
    s = two_state(f, st, tin, x_rel=x_rel, cx=WALL_X, flip=True, ground=ground, b_st=b_st, b_x=b_x, hx=hx,
                  facing=facing, ev=ev)
    s["ents"] += list(ents)
    return s


def step_all(two, ss, focus=7):
    out = []
    for s in ss:
        two.observe(s["f"], s, s["f"] / 60.0)
        out.append(two.step(s["f"], s, sp.on_ground(s), True, focus, s["f"] / 60.0))
    return out


@pytest.fixture
def corner(monkeypatch):
    for k in ("ESC", "ESC_CORNER", "ANY"):
        monkeypatch.setattr(tp, k, True)
    monkeypatch.setattr(tp, "ESC_SWITCH", False)
    yield


@pytest.fixture
def switch(monkeypatch):
    for k in ("ESC", "ESC_SWITCH", "ANY"):
        monkeypatch.setattr(tp, k, True)
    monkeypatch.setattr(tp, "ESC_CORNER", False)
    yield


def test_switches_default_off(monkeypatch):
    for k in ("SSBOT_FORUM_TWO_CORNER", "SSBOT_FORUM_TWO_WALLSWITCH"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SSBOT_FORUM_V2", "1")
    try:
        m = importlib.reload(tp)
        assert not (m.ESC or m.ESC_CORNER or m.ESC_SWITCH)                # not even with v2 (until their A/B)
        assert not importlib.reload(cs).TWO_CORNER
        two = m.TwoPlay()
        s = fstate(1000, "Jump Antic")
        two.observe(1000, s, 1000 / 60.0)
        assert two.esc is None and two.esc_view() is None and "esc" not in two.stats()
    finally:
        monkeypatch.delenv("SSBOT_FORUM_V2", raising=False)
        importlib.reload(tp)
        importlib.reload(cs)


def test_detect_only_at_a_wall_and_near(corner):
    two = tp.TwoPlay()
    step_all(two, [fstate(1000, "Idle", 0.5), fstate(1001, "Jump Antic")])
    r = two.esc
    assert r is not None and r.mode == "corner" and r.kind == "jump" and r.iid == 7 and r.other == 99
    assert r.back0 == pytest.approx(3.99, abs=0.01) and r.rel0 == pytest.approx(4.0, abs=0.01)
    # away from the wall (its back 12 u): not an escape jump
    two = tp.TwoPlay()
    s0, s1 = two_state(1000, "Idle", 0.5, cx=26.0, flip=True), two_state(1001, "Jump Antic", 0.0, cx=26.0, flip=True)
    step_all(two, [s0, s1])
    assert two.esc is None and two.esc_n["no_wall"] == 1
    # she nearer to the other one: not hers
    two = tp.TwoPlay()
    step_all(two, [fstate(1000, "Idle", 0.5, x_rel=7.5, b_x=WALL_X + 10.0),
                   fstate(1001, "Jump Antic", x_rel=7.5, b_x=WALL_X + 10.0)])
    assert two.esc is None and two.esc_n["no_near"] == 1


def test_corner_view_phases_and_hop(corner):
    two = tp.TwoPlay()
    step_all(two, [fstate(1000, "Idle", 0.5), fstate(1001, "Jump Antic")])
    v = two.esc_view()
    assert v["hold"] == 7 and v["corner_aim"] and not v["no_hit"] and not v["after_land"]
    behind = WALL_X - 3.5                                         # she went under to the corner: 3.5 u behind it
    step_all(two, [fstate(1031, "Jump", hx=behind, ground=False), fstate(1080, "Slam 2", hx=behind)])
    r = two.esc
    assert r.phase == "landed" and r.f_land == 1080 and r.u_land == pytest.approx(-3.5, abs=0.01)
    v = two.esc_view()
    assert v["after_land"] and not v["corner_aim"] and not v["no_hit"]       # its back slashed in Slam 2 / Recover
    out = step_all(two, [fstate(1086, "Slam Recover", 6 / 60, hx=behind), fstate(1100, "Idle", 0.0, hx=behind)])
    assert out == [None, None] and two.esc.phase == "idle" and two.esc_view()["no_hit"] == frozenset({7})
    # its coin moment passes with it still idle: the hop (b 3.5: H 28, the key from 14, the dash at 26)
    out = step_all(two, [fstate(1114, "Idle", 14 / 60, hx=behind)])
    assert out == [None]                                          # mask frame Idle + 16 < coin_f 17
    keys = step_all(two, [fstate(1115 + j, "Idle", (15 + j) / 60, hx=behind, ground=j < 2) for j in range(40)])
    H, d0, jd = tp.hop_plan(3.5)
    assert (H, d0, jd) == (28, 14, 26)
    assert keys[0] == sp.M_J and keys[d0] == sp.M_J | sp.M_R and keys[jd] == sp.M_J | sp.M_R | sp.M_DASH
    assert keys[jd + 1] == sp.M_J | sp.M_R | sp.M_DASH and keys[jd + 2] == sp.M_R and keys[H] == sp.M_R
    assert two.esc.exit == "hop" and two.esc.hop["b"] == pytest.approx(3.5, abs=0.01)
    # she lands: the run ends
    step_all(two, [fstate(1160, "Idle", 1.0, hx=WALL_X + 5.8, ground=True)])
    assert two.esc is None and two.esc_done[-1].end == "hop" and two.esc_done[-1].hop["end"] == "landed"


def test_corner_hop_needs_room_and_idle(corner):
    # 1.8 u behind it: no hop (its turned body reaches 2.25 u; the table starts at 2.5)
    two = tp.TwoPlay()
    hx = WALL_X - 1.8
    step_all(two, [fstate(1000, "Idle", 0.5), fstate(1001, "Jump Antic"), fstate(1080, "Slam 2", hx=hx),
                   fstate(1100, "Idle", 0.0, hx=hx), fstate(1116, "Idle", 16 / 60, hx=hx),
                   fstate(1117, "Idle", 17 / 60, hx=hx)])
    assert two.esc is None and two.esc_done[-1].end == "near"
    # it evades (its coin) before the moment: no hop, the run ends ("moved")
    two = tp.TwoPlay()
    hx = WALL_X - 3.5
    step_all(two, [fstate(1000, "Idle", 0.5), fstate(1001, "Jump Antic"), fstate(1080, "Slam 2", hx=hx),
                   fstate(1100, "Idle", 0.0, hx=hx), fstate(1115, "Evade Scuttle", 0.0, hx=hx),
                   fstate(1116, "Evade Scuttle", 1 / 60, hx=hx)])
    assert two.esc is None and two.esc_done[-1].end == "moved"


def _rune(x, lit):
    r = tp._cs.RUNE_R
    return {"type_key": "damager", "iid": -5, "pos": [x, 3.34],
            "colliders": [{"enabled": lit, "verts_world": [x - r, 3.34, x + r, 3.34, x, 3.34 + r, x, 3.34 - r]}]}


def test_corner_jump_cast_waits_for_the_burst(corner):
    two = tp.TwoPlay()
    hx = WALL_X - 3.5
    c = WALL_X + 6.48
    step_all(two, [fstate(1000, "Idle", 0.5), fstate(1001, "Cast Slam Antic"), fstate(1056, "Jump", hx=hx, ground=False),
                   fstate(1110, "Slam 2", hx=hx), fstate(1130, "Idle", 0.0, hx=hx, ents=[_rune(c, False)])])
    out = step_all(two, [fstate(1150, "Idle", 20 / 60, hx=hx, ents=[_rune(c, False)])])
    assert out == [None] and two.esc.exit is None and two.esc_view()["no_hit"] == frozenset({7})   # no hop, no hit
    step_all(two, [fstate(1175, "Idle", 45 / 60, hx=hx, ents=[_rune(c, True)]),
                   fstate(1182, "Idle", 52 / 60, hx=hx, ents=[_rune(c, False)])])
    assert two.esc.rune == {"seen": 20, "lit": 65, "burst": 72} and two.esc.exit == "rune"
    step_all(two, [fstate(1183, "Idle", 53 / 60, hx=hx)])
    assert two.esc is None and two.esc_done[-1].end == "rune"


def test_switch_lock_then_deciding_hit(switch):
    two = tp.TwoPlay()
    step_all(two, [fstate(1000, "Idle", 0.5, b_x=30.0), fstate(1001, "Jump Antic", b_x=30.0)])
    v = two.esc_view()
    assert v["mode"] == "switch" and v["hold"] == 99 and v["no_hit"] == frozenset({99})   # B's hits off: F's lock
    # F lands; she stands 3.5 u in front of B (B faces left: its front edge at 27.75), facing it
    out = step_all(two, [fstate(1031, "Jump", hx=26.5, b_x=30.0, facing=1),
                         fstate(1080, "Slam 2", hx=26.5, b_x=30.0, facing=1),
                         fstate(1081, "Slam 2", 1 / 60, hx=26.5, b_x=30.0, facing=1)])
    assert out[0] is None and out[1] == sp.M_A | sp.M_R and out[2] == sp.M_A | sp.M_R
    assert not two.esc_view()["no_hit"] and two.esc.press["f"] == 0
    hit = [{"k": "hit", "d": {"type_key": sp.CLAPPER, "ent": 99, "dealt": 10}}]
    step_all(two, [fstate(1083, "Slam 2", 3 / 60, hx=26.5, b_x=30.0, facing=1, ev=hit),
                   fstate(1084, "Slam 2", 4 / 60, hx=26.5, b_x=30.0, b_st="Slam Antic", facing=1)])
    r = two.esc_done[-1]
    assert two.esc is None and r.end == "B move" and r.press["hit"] == 3 and r.press["b_next"] == "Slam Antic"


def test_switch_not_onto_a_jumping_other(switch):
    two = tp.TwoPlay()
    step_all(two, [fstate(1000, "Idle", 0.5, b_x=30.0, b_st="Air"), fstate(1001, "Jump Antic", b_x=30.0, b_st="Air")])
    assert two.esc is not None and two.esc.mode is None and two.esc.why == "other jumping"
    assert two.esc_view() is None


def _cs_state(f, st, tin, hx, ground=True):
    s = fstate(f, st, tin, hx=hx, ground=ground)
    s["ents"] = s["ents"][::-1]                                   # the other one first in the STATE
    return s


def test_cast_stab_corner_with_two(monkeypatch):
    monkeypatch.setattr(cs, "TWO_CORNER", True)
    esc = {"iid": 7, "mode": "corner", "back_u": 6.2}
    c = cs.CastStab(dash_slash=True, combo=True, stop=True, slam_dash=False, corner=False)
    hx = WALL_X + 4.3
    c.step(1001, _cs_state(1001, "Jump Antic", 0.0, hx), True, True, 1001 / 60.0, esc=esc)
    assert c.run is not None and c.run.iid == 7 and c.run.corner and c.run.kind == "jump" and c.run.phase == "slash"
    # no escape run: the two-Clapper gate as before
    c = cs.CastStab(dash_slash=True, combo=True, stop=True, slam_dash=False, corner=False)
    c.step(1001, _cs_state(1001, "Jump Antic", 0.0, hx), True, True, 1001 / 60.0)
    assert c.run is None
    # the way under from its take-off (the jump cast: no antic script from 7 u, the take-off under)
    c = cs.CastStab(dash_slash=True, combo=True, stop=True, slam_dash=False, corner=False)
    c.step(1001, _cs_state(1001, "Cast Slam Antic", 0.0, WALL_X + 7.0), True, True, 1001 / 60.0, esc=esc)
    assert c.run is None
    m = c.step(1056, _cs_state(1056, "Jump", 0.0, WALL_X + 4.5), True, True, 1056 / 60.0, esc=esc)
    assert c.run is not None and c.run.mode == "under" and m is not None and m & sp.M_L


def test_cast_stab_off_ignores_esc(monkeypatch):
    monkeypatch.setattr(cs, "TWO_CORNER", False)
    c = cs.CastStab(dash_slash=True, combo=True, stop=True, slam_dash=False, corner=False)
    c.step(1001, _cs_state(1001, "Jump Antic", 0.0, WALL_X + 4.3), True, True, 1001 / 60.0,
           esc={"iid": 7, "mode": "corner", "back_u": 6.2})
    assert c.run is None


def _claps(fx=20.0, ox=36.0, ffam=None, ofam=None):
    return [subj(1, CC, fx, y=7.45, family=ffam, committed=ffam is not None, t_free=1.4 if ffam else 0.0),
            subj(2, CC, ox, y=7.45, family=ofam)]


def test_gauntlet_hold_and_no_hit(monkeypatch):
    monkeypatch.setattr(gt, "TWO_FOCUS", True)
    monkeypatch.setattr(gt.jump_behind, "ENABLED", True)
    monkeypatch.setattr(tp, "ESC", True)
    ents = [clapper(1, 25.0, True), clapper(2, 40.0, False)]
    # arm B: the hold on the other one (2) through the focus's jump, its hits off until the landing
    t = l2()
    t.decide(world(29.0, ents=ents), WinFc(_claps(fx=25.0, ox=40.0), t_min=0.1), None, 3)
    assert t.goal.target == 1
    t.two_esc = {"iid": 1, "other": 2, "mode": "switch", "hold": 2, "no_hit": frozenset({2}), "after_land": False,
                 "corner_aim": False}
    p = t.decide(world(29.0, t=10.1, ents=ents), WinFc(_claps(fx=25.0, ox=40.0, ffam=gt.CC_JUMP), t_min=0.1), None, 3)
    assert p.target == 2 and 2 in p.no_hit and t.stats["sp7"]["esc_switch"] == 1
    # arm A: the hold on the focus with the corner stance in its antic (4.4 u in front)
    ents = [clapper(1, 20.0, True), clapper(2, 36.0, False)]
    t = l2()
    t.decide(world(24.0, ents=ents), WinFc(_claps(), t_min=0.1), None, 3)
    t.two_esc = {"iid": 1, "other": 2, "mode": "corner", "hold": 1, "no_hit": frozenset(), "after_land": False,
                 "corner_aim": True}
    fc = _claps(ffam=gt.CC_JUMP)
    fc[0] = subj(1, CC, 20.0, y=7.45, state="Jump Antic", family=gt.CC_JUMP, committed=True, t_free=1.4)
    p = t.decide(world(24.0, t=10.1, ents=ents), WinFc(fc, t_min=0.1), None, 3)
    assert p.target == 1 and p.stance_x == pytest.approx(24.4) and "esc corner" in t.last["goal_why"]
