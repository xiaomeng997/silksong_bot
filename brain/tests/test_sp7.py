"""Task 1v1 SP7 (forum.md 71): two Clappers. SSBOT_FORUM_TWO_PLAY - the slam playbook follows the Clapper entering Slam
Antic (not the first of the STATE), does not start while the other one can reach the stand point, and does not look at
a handled slam again; SSBOT_FORUM_TWO_FOCUS - L2's RUSH on the focus (the one farther from the wall on its side away from
the other), the switch only when the other has more room AND will not jump while she runs to it. Off: unchanged."""
import pytest

from ssbot.combat import slam_play as sp
from ssbot.combat.tactics import gauntlet as gt
from tests.test_forum_l2 import CC, WinFc, clapper, l2, subj, world
from tests.test_slam_play import slam_state, state


def two_state(f, k, cx=31.0, ox=20.0, ost="Idle", hx=26.0, first_slams=False, oflip=True):
    """A STATE with the slamming Clapper (iid 7, at antic frame k, facing left: the hero at hx in front) listed second
    and the other one (iid 8, its state ost) first - or first_slams: the slamming one first."""
    st, tin = slam_state(k)
    s = state(f, st, tin, cx=cx, hx=hx)
    other = {"type_key": sp.CLAPPER, "iid": 8, "hp": 200, "pos": [ox, 7.45], "flipX": oflip,
             "fsms": [{"name": "Control", "state": ost, "t": 0.5}]}
    s["ents"] = s["ents"] + [other] if first_slams else [other] + s["ents"]
    return s


def test_off_follows_the_first_clapper(monkeypatch):
    monkeypatch.setattr(sp, "TWO_PLAY", False)
    p = sp.SlamPlay(sp.PlayCfg())
    for k in range(0, 6):
        p.step(1000 + k, two_state(1000 + k, k, hx=26.0), True)
    assert p.run is None                                  # the first Clapper (the other one) idles: no slam seen


def test_on_follows_the_slamming_clapper(monkeypatch):
    monkeypatch.setattr(sp, "TWO_PLAY", True)
    p = sp.SlamPlay(sp.PlayCfg())
    out = [p.step(1000 + k, two_state(1000 + k, k, hx=26.0, ox=10.0), True) for k in range(0, 6)]
    assert p.run is not None and p.run.iid == 7 and p.run.phase == "walk"
    assert any(m is not None for m in out)


@pytest.mark.parametrize("ost,why", [("Jump Antic", "other Jump Antic"), ("Air", "other Air"),
                                     ("Slam 2", "other Slam 2"), ("Cast 2", "other Cast 2")])
def test_on_waits_while_the_other_can_reach(monkeypatch, ost, why):
    monkeypatch.setattr(sp, "TWO_PLAY", True)
    p = sp.SlamPlay(sp.PlayCfg())
    # the stand point ~26 u (5 u in front of 31); the other at 20 u (6 u from it: hammer / small runes reach)
    out = [p.step(1000 + k, two_state(1000 + k, k, hx=26.0, ox=20.0, ost=ost), True) for k in range(0, 6)]
    assert all(m is None for m in out)
    assert p.run is not None and p.run.phase == "wait" and p.run.why == why
    # far enough (the hammer reaches 12 u, the runes 9 u): the jump states still wait (its landing aims at her)
    p = sp.SlamPlay(sp.PlayCfg())
    out = [p.step(1000 + k, two_state(1000 + k, k, hx=26.0, ox=10.0, ost=ost), True) for k in range(0, 6)]
    assert (p.run.phase == "wait") == (ost in sp.TWO_JUMP_ST)


def test_on_waits_for_the_other_ones_rune_circle(monkeypatch):
    monkeypatch.setattr(sp, "TWO_PLAY", True)
    p = sp.SlamPlay(sp.PlayCfg())
    f = 960
    # the other one (at 18 u, facing right: flipX) lands a jump cast; its circle spans 16.8 .. 32.2 u
    for st in ("Cast Slam Antic", "Air", "Slam 2"):
        s = two_state(f, -5, hx=26.0, ox=18.0, ost=st)
        p.step(f, s, True, t_game=f / 60.0)
        f += 1
    assert 8 in p._rune
    out = [p.step(1000 + k, two_state(1000 + k, k, hx=26.0, ox=18.0, ost="Idle"), True, t_game=(1000 + k) / 60.0)
           for k in range(0, 4)]
    assert all(m is None for m in out) and p.run.why == "other rune circle"
    # 1.45 s after the landing it has burst: the script starts
    p2 = sp.SlamPlay(sp.PlayCfg())
    p2._rune[8] = (18.0, 1, 0.0)
    out = [p2.step(1000 + k, two_state(1000 + k, k, hx=26.0, ox=18.0), True, t_game=10.0 + k / 60.0)
           for k in range(0, 4)]
    assert p2.run.phase == "walk"


def test_on_a_handled_slam_is_not_looked_at_again(monkeypatch):
    monkeypatch.setattr(sp, "TWO_PLAY", True)
    p = sp.SlamPlay(sp.PlayCfg())
    # too far (9.5 u): the start window passes, the run aborts ("late"); no new run for the same slam afterwards
    for k in range(0, 30):
        p.step(1000 + k, two_state(1000 + k, k, cx=31.0, hx=21.5, ox=45.0), True)
    assert p.run is None and len(p.done) == 1 and 7 in p._closed
    # it leaves the slam: forgotten
    s = two_state(1100, -5, cx=31.0, hx=21.5, ox=45.0)
    p.step(1100, s, True)
    assert 7 not in p._closed


def _claps(ox=40.0, fx=25.0, ofam=None, ffam=None, fcommit=False, ft_free=0.0):
    return [subj(1, CC, fx, y=7.45, family=ffam, committed=fcommit, t_free=ft_free),
            subj(2, CC, ox, y=7.45, family=ofam)]


def test_focus_off_is_unchanged(monkeypatch):
    monkeypatch.setattr(gt, "TWO_FOCUS", False)
    t = l2()
    s = _claps(fx=30.0, ox=36.0)
    p = t.decide(world(33.0, ents=[clapper(1, 30.0, True), clapper(2, 36.0, False)]), WinFc(s, t_min=9.0), None, 3)
    assert p.goal == gt.KITE                                  # the two within 8 u: the old KITE


def test_focus_picks_the_one_farther_from_its_wall(monkeypatch):
    monkeypatch.setattr(gt, "TWO_FOCUS", True)
    t = l2()
    # arena 14.01 .. 48.99: the left one at 25 has 11 u to the left wall, the right one at 40 has 9 u to the right wall
    s = _claps(fx=25.0, ox=40.0)
    ents = [clapper(1, 25.0, True), clapper(2, 40.0, False)]
    p = t.decide(world(32.0, ents=ents), WinFc(s, t_min=0.1), None, 3)
    assert p.goal == gt.RUSH and p.target == 1
    assert p.stance_x == pytest.approx(29.0)                  # its face, 4 u on her side: between them


def test_focus_switch_needs_both_conditions(monkeypatch):
    monkeypatch.setattr(gt, "TWO_FOCUS", True)
    t = l2()
    ents = [clapper(1, 25.0, True), clapper(2, 40.0, False)]
    p = t.decide(world(30.0, ents=ents), WinFc(_claps(fx=25.0, ox=40.0), t_min=0.1), None, 3)
    assert p.target == 1
    # the focus backs off to 20 (6 u of room), the other one at 36 has 13 u: more room, but it is free -> keep
    for i in range(6):
        p = t.decide(world(26.0, t=10.1 + i * 0.1, ents=ents), WinFc(_claps(fx=20.0, ox=36.0), t_min=0.1), None, 3)
    assert p.target == 1
    # the focus commits (its slam antic: the other one cannot start a move) and she reaches the other in time -> switch
    for i in range(6):
        p = t.decide(world(26.0, t=11.0 + i * 0.1, ents=ents),
                     WinFc(_claps(fx=20.0, ox=36.0, ffam=gt.CC_SLAM, fcommit=True, ft_free=1.2), t_min=0.1), None, 3)
    assert p.target == 2 and t.stats["sp7"]["switch_focus committed"] >= 1
    # the other one in a jump move: never
    t2 = l2()
    t2.decide(world(30.0, ents=ents), WinFc(_claps(fx=25.0, ox=40.0), t_min=0.1), None, 3)
    for i in range(6):
        p = t2.decide(world(26.0, t=11.0 + i * 0.1, ents=ents),
                      WinFc(_claps(fx=20.0, ox=36.0, ofam=gt.CC_JUMP, ffam=gt.CC_SLAM, fcommit=True, ft_free=1.2),
                            t_min=0.1), None, 3)
    assert p.target == 1


def test_focus_switch_after_the_others_attack(monkeypatch):
    monkeypatch.setattr(gt, "TWO_FOCUS", True)
    t = l2()
    ents = [clapper(1, 20.0, True), clapper(2, 33.0, False)]
    t.decide(world(26.0, ents=ents), WinFc(_claps(fx=20.0, ox=33.0, ofam=gt.CC_CAST), t_min=0.1), None, 3)
    # focus: room 5.99 vs 15.99 -> the right one is picked first (farther from its wall)
    assert t.goal.target == 2
    t = l2()
    ents = [clapper(1, 30.0, True), clapper(2, 37.0, False)]
    t.decide(world(33.0, ents=ents), WinFc(_claps(fx=30.0, ox=37.0, ofam=gt.CC_CAST), t_min=0.1), None, 3)
    assert t.goal.target == 1                                 # 16 u vs 12 u: the left one
    # the left one backs off to 21 (7 u); the right one ends its cast (idle now) 8 u from her: she gets within 7 u in
    # 0.12 s -> switch
    p = None
    for i in range(7):
        p = t.decide(world(29.0, t=10.1 + i * 0.1, ents=ents), WinFc(_claps(fx=21.0, ox=37.0), t_min=0.1), None, 3)
    assert p.target == 2 and t.stats["sp7"].get("switch_other just ended a move", 0) >= 1


def test_side_two_away(monkeypatch):
    # the struck one at 31 facing left (the hero in front at 26); the other at 20, idle: the landing between them (27.3)
    # is 7.3 u from it: TWO_SIDE lands on the far side (behind the struck one, +x: 14.7 u from it); busy or far:
    # between them (-x); closer: the far side's dash way out
    monkeypatch.setattr(sp, "TWO_SIDE", True)
    monkeypatch.setattr(sp, "SIDE", True)
    monkeypatch.setattr(sp, "NEAR", True)
    p = sp.SlamPlay(sp.PlayCfg())
    s = two_state(1000, 60, hx=30.0, ox=20.0, ost="Idle")
    r = sp.Run(iid=7, fa=950, face=-1)
    e = next(o for o in s["ents"] if o["iid"] == 7)
    assert p._side_pref(r, s, e, 31.0) == (1, "two-away")
    s = two_state(1000, 60, hx=30.0, ox=20.0, ost="Cast 2")
    assert p._side_pref(r, s, e, 31.0) == (-1, "two")
    s = two_state(1000, 60, hx=30.0, ox=10.0, ost="Idle")
    assert p._side_pref(r, s, e, 31.0) == (-1, "two")              # 21 u apart: between them is out of its reach
    s = two_state(1000, 60, hx=30.0, ox=25.0, ost="Slam Antic")
    assert p._side_pref(r, s, e, 31.0) == (1, "two-far")           # 6 u apart: 3.7 u behind is in its reach too
    # NEAR's decision: two-far -> SP1's dash way out on that side (room 18 u behind it)
    r.ks0, r.near = 0, None
    assert p._near(r, 12, 1000, s, e, 31.0) == 0 and r.near == 0 and r.over_dir == 1 and r.side_why == "two-far"
    monkeypatch.setattr(sp, "TWO_SIDE", False)
    s = two_state(1000, 60, hx=30.0, ox=20.0, ost="Idle")
    assert p._side_pref(r, s, e, 31.0) == (-1, "two")


def test_jumper_is_the_target(monkeypatch):
    monkeypatch.setattr(gt, "TWO_FOCUS", True)
    monkeypatch.setattr(gt, "TWO_JUMPER", True)
    t = l2()
    ents = [clapper(1, 25.0, True), clapper(2, 40.0, False)]
    p = t.decide(world(30.0, ents=ents), WinFc(_claps(fx=25.0, ox=40.0), t_min=0.1), None, 3)
    assert p.target == 1
    for i in range(6):
        p = t.decide(world(30.0, t=10.1 + i * 0.1, ents=ents),
                     WinFc([subj(1, CC, 25.0, y=7.45), subj(2, CC, 40.0, y=7.45, state="Jump Antic", family=gt.CC_JUMP,
                                                         committed=True)], t_min=0.1), None, 3)
    assert p.target == 2 and t.stats["sp7"]["jumper"] >= 1 and "jump" in t.last["goal_why"]
    monkeypatch.setattr(gt, "TWO_JUMPER", False)
    t = l2()
    t.decide(world(30.0, ents=ents), WinFc(_claps(fx=25.0, ox=40.0), t_min=0.1), None, 3)
    for i in range(6):
        p = t.decide(world(30.0, t=10.1 + i * 0.1, ents=ents),
                     WinFc([subj(1, CC, 25.0, y=7.45), subj(2, CC, 40.0, y=7.45, state="Jump Antic", family=gt.CC_JUMP,
                                                         committed=True)], t_min=0.1), None, 3)
    assert p.target == 1
