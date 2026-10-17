"""Task 1v1 SP9c (forum.md 78): the close-only antic switch with two Clappers - SSBOT_FORUM_TWO_ANTICSWITCH (default
off): at F's close slam / cast antic near its wall, L2 on B (lock-in), out of F's hammer, the re-hit on B's Idle
(re-)entry in F's lock, the deciding side slash on B from F's flag-off (ssbot.combat.two_play, slam_play, rune_lowhop,
tactics.gauntlet)."""
import importlib

import pytest

from ssbot.combat import rune_lowhop as rl
from ssbot.combat import slam_play as sp
from ssbot.combat import two_play as tp
from ssbot.combat.tactics import gauntlet as gt
from tests.test_forum_l2 import CC, WinFc, clapper, l2, subj, world
from tests.test_sp9 import two_state

WALL_X = tp.WALL_L + 3.99                 # F at the left wall facing right (flipX): its back 3.99 u from the wall
B_X = WALL_X + 22.0                       # B 22 u from F on its open side


def fstate(f, st, tin=0.0, hx=None, x_rel=4.0, b_st="Idle", b_x=B_X, ground=True, cx=WALL_X, ev=(), atk_cd=0.0,
           facing=None, b_tin=0.1):
    s = two_state(f, st, tin, x_rel=x_rel, cx=cx, flip=True, ground=ground, b_st=b_st, b_x=b_x, hx=hx, ev=ev,
                  atk_cd=atk_cd, facing=facing)
    s["ents"][1]["fsms"][0]["t"] = b_tin
    return s


def step_all(two, ss, focus=99):
    out = []
    for s in ss:
        two.observe(s["f"], s, s["f"] / 60.0)
        out.append(two.step(s["f"], s, sp.on_ground(s), True, focus, s["f"] / 60.0))
    return out


@pytest.fixture
def asw(monkeypatch):
    for k in ("ASW", "ANY"):
        monkeypatch.setattr(tp, k, True)
    for k in ("ESC", "ESC_CORNER", "ESC_SWITCH", "IDLEHIT", "OPEN", "SPACE"):
        monkeypatch.setattr(tp, k, False)
    monkeypatch.setenv("SSBOT_FORUM_TWO_ASW_SET", "first=0")     # (the opening's rule has its own test)
    yield


def test_switch_default_off(monkeypatch):
    monkeypatch.delenv("SSBOT_FORUM_TWO_ANTICSWITCH", raising=False)
    try:
        monkeypatch.setenv("SSBOT_FORUM_V2", "1")
        m = importlib.reload(tp)
        assert not m.ASW                                   # an A/B arm only: off with v2
        two = m.TwoPlay()
        step_all(two, [fstate(1000, "Idle", 0.5), fstate(1001, "Slam Antic")])
        assert two.asw is None and two.asw_skip() == frozenset() and "asw" not in two.stats()
        monkeypatch.setenv("SSBOT_FORUM_TWO_ANTICSWITCH", "1")
        assert importlib.reload(tp).ASW
    finally:
        monkeypatch.delenv("SSBOT_FORUM_V2", raising=False)
        monkeypatch.delenv("SSBOT_FORUM_TWO_ANTICSWITCH", raising=False)
        importlib.reload(tp)


def test_trigger_t81(asw):
    two = tp.TwoPlay()
    step_all(two, [fstate(1000, "Idle", 0.5), fstate(1001, "Slam Antic", 1 / 60)])
    r = two.asw
    assert r is not None and r.mode == "aswitch" and r.kind == "slam" and r.iid == 7 and r.other == 99
    assert r.back0 == pytest.approx(3.99, abs=0.01) and r.k_a == 1 and r.sep0 == pytest.approx(22.0)
    v = two.esc_view()
    assert v["hold"] == 99 and v["no_hit"] == frozenset({99}) and not v["after_land"] and v["mode"] == "aswitch"
    assert two.asw_skip() == frozenset({7})
    # away from the wall (its back 12 u > 8.1): no switch
    two = tp.TwoPlay()
    step_all(two, [fstate(1000, "Idle", 0.5, cx=26.0, b_x=45.0), fstate(1001, "Slam Antic", cx=26.0, b_x=45.0)])
    assert two.asw is None and two.asw_n["no_wall"] == 1
    # a far pick (she 9 u away): not a close move
    two = tp.TwoPlay()
    step_all(two, [fstate(1000, "Idle", 0.5, x_rel=9.0), fstate(1001, "Spell Antic", x_rel=9.0)])
    assert two.asw is None and two.asw_n["no_far_pick"] == 1


def test_not_taken(asw):
    for kw, why in (({"b_x": WALL_X + 14.0}, "sep"), ({"b_st": "Slam Recover"}, "b busy"),
                    ({"b_x": WALL_X + 30.0}, "far")):
        two = tp.TwoPlay()
        b_x = kw.get("b_x", B_X)
        step_all(two, [fstate(1000, "Idle", 0.5, **kw), fstate(1001, "Slam Antic", **kw)])
        assert two.asw is None and two.asw_done[-1].why == why and two.asw_done[-1].mode is None, (kw, b_x)
    # a cast with B 14 u away: sep >= 4 is enough
    two = tp.TwoPlay()
    step_all(two, [fstate(1000, "Idle", 0.5, b_x=WALL_X + 14.0), fstate(1001, "Spell Antic", b_x=WALL_X + 14.0)])
    assert two.asw is not None and two.asw.kind == "cast"


def test_no_switch_on_the_first_attack(asw, monkeypatch):
    monkeypatch.delenv("SSBOT_FORUM_TWO_ASW_SET")
    two = tp.TwoPlay()
    step_all(two, [fstate(1000, "Idle", 0.5), fstate(1001, "Slam Antic", 1 / 60)])
    assert two.asw is None and two.asw_done[-1].why == "first"            # the opening's A1: punish it
    step_all(two, [fstate(1100, "Idle", 0.5), fstate(1101, "Spell Antic", 1 / 60)])
    assert two.asw is not None and two.asw.kind == "cast"                 # its second attack: the switch


def test_trigger_pred(asw, monkeypatch):
    monkeypatch.setenv("SSBOT_FORUM_TWO_ASW_SET", "trig=1,first=0")
    try:
        c = tp._asw_cfg()
        assert c.trig == 1
        assert tp.pred_back(c, 3.99, "slam") == pytest.approx(3.99 + 3.1 - 2.1 - 0.48)
        # a slam 6 u from the wall: the lunge carries it out (6.52 >= 5.4) - no switch (T8.1 would switch)
        two = tp.TwoPlay()
        cx = tp.WALL_L + 6.0
        step_all(two, [fstate(1000, "Idle", 0.5, cx=cx), fstate(1001, "Slam Antic", cx=cx)])
        assert two.asw is None and two.asw_n["no_wall"] == 1
        # a cast 8.5 u from the wall: 8.5 - 1.5 - 2.1 - 0.48 = 4.42 < 5.4 - switch (T8.1 would not)
        two = tp.TwoPlay()
        cx = tp.WALL_L + 8.5
        step_all(two, [fstate(1000, "Idle", 0.5, cx=cx), fstate(1001, "Spell Antic", cx=cx)])
        assert two.asw is not None and two.asw.pred == pytest.approx(4.42, abs=0.01)
    finally:
        monkeypatch.setenv("SSBOT_FORUM_TWO_ASW_SET", "first=0")


def test_slam_run_dash_hold_then_decide(asw):
    two = tp.TwoPlay()
    hx = WALL_X + 4.0
    out = step_all(two, [fstate(1000, "Idle", 0.5, hx=hx), fstate(1001, "Slam Antic", 1 / 60, hx=hx)])
    r = two.asw
    hold = B_X - 8.8                                              # beyond the hammer line (x0 + 12.3)
    assert r.tx == pytest.approx(hold) and out[1] == sp.M_R
    # the run alone is late for the line: the dash (the previous mask held the key) held into the sprint
    out = step_all(two, [fstate(1002, "Slam Antic", 2 / 60, hx=hx + 0.14), fstate(1003, "Slam Antic", 3 / 60,
                                                                                  hx=hx + 0.28)])
    assert out == [sp.M_R | sp.M_DASH, sp.M_R | sp.M_DASH] and r.dash == [4]
    # released inside Sprint Grace when her travel reaches the target (closed loop), then no key until control
    s = fstate(1012, "Slam Antic", 12 / 60, hx=hold - 0.5)
    s["hero"]["vel"] = [20.0, 0.0]
    s["hero"]["anim"] = {"clip": "Sprint"}
    assert step_all(two, [s]) == [0]
    s = fstate(1013, "Slam Antic", 13 / 60, hx=hold - 0.1)
    s["hero"]["anim"] = {"clip": "Sprint"}
    assert step_all(two, [s]) == [0]
    # control again at the hold point; the step-in (from k 24: 3.85 u to the press point by F's flag-off - 4)
    out = step_all(two, [fstate(1014, "Slam Antic", 14 / 60, hx=hold)])
    assert out == [0] and r.dash_end == 1014 and r.k_hold == 16
    press = B_X - 2.25 - 2.7
    out = step_all(two, [fstate(1024, "Slam Antic", 24 / 60, hx=hold)])
    assert r.tx == pytest.approx(hold) and out == [0]             # outside B's Slam Range until the step-in
    # the step-in 4 frames before F's predicted flag-off (k 52): a walk (the dash kept for B's evade)
    out = step_all(two, [fstate(1049, "Slam Antic", 49 / 60, hx=hold), fstate(1050, "Slam Antic", 50 / 60, hx=hold),
                         fstate(1051, "Slam 0", 0.0, hx=hold + 0.14)])
    assert out == [0, sp.M_R, sp.M_R] and r.tx == pytest.approx(press) and r.dash == [4]
    # F's flag-off (Slam 2): she reaches the press point facing F - the turn, then the deciding press
    out = step_all(two, [fstate(1061, "Slam 2", 0.0, hx=press)])
    assert r.f_off == 1061 and r.phase == "tail" and out == [sp.M_R]
    out = step_all(two, [fstate(1062, "Slam 2", 1 / 60, hx=press, facing=1)])
    assert out == [sp.M_A | sp.M_R] and r.presses[-1][1] == "decide"
    assert step_all(two, [fstate(1063, "Slam 2", 2 / 60, hx=press, facing=1)]) == [sp.M_A | sp.M_R]
    # the hit lands and B decides (Slam Antic): the run ends, B's next recorded
    hit = {"k": "hit", "d": {"type_key": sp.CLAPPER, "ent": 99, "dealt": 13}}
    step_all(two, [fstate(1066, "Slam Recover", 0.0, hx=press, b_st="Slam Antic", b_tin=0.0, ev=(hit,))])
    assert two.asw is None
    d = two.asw_done[-1]
    assert d.end == "B move" and d.b_next == "Slam Antic" and d.k_next == 5 and d.hit_b == 5
    st = two.stats()["asw"]
    assert st["runs"] == 1 and st["asw_runs"][0]["hit_in_tail"] and st["asw_runs"][0]["dash"] == [4]


def test_slam_press_waits_for_the_hammer(asw):
    b_x = WALL_X + 17.0                                           # the press point 12.05 u from x0: inside the hammer
    two = tp.TwoPlay()
    step_all(two, [fstate(1000, "Idle", 0.5, b_x=b_x), fstate(1001, "Slam Antic", 1 / 60, b_x=b_x)])
    r = two.asw
    line = WALL_X + 12.3
    step_all(two, [fstate(1040, "Slam Antic", 40 / 60, hx=line, b_x=b_x, facing=1)])
    assert r.tx == pytest.approx(line)
    # late, still inside the line at its Slam 2: no press from the hammer, out first
    out = step_all(two, [fstate(1056, "Slam 2", 0.0, hx=line - 0.5, b_x=b_x, facing=1)])
    assert out == [sp.M_R] and not r.presses
    out = step_all(two, [fstate(1062, "Slam Recover", 0.0, hx=line - 0.5, b_x=b_x, facing=1)])
    assert r.f_rec == 1062 and out == [sp.M_A | sp.M_R] and r.presses[-1][1] == "decide"


def test_lock_rehit_only_inside_the_coin_window(asw):
    two = tp.TwoPlay()
    hx = B_X - 4.9                       # she is at B already (F casts, she 17 u in front of it: a far pick is not
    #                                      checked here - start the run with her near F, then move)
    step_all(two, [fstate(1000, "Idle", 0.5), fstate(1001, "Spell Antic", 1 / 60)])
    r = two.asw
    assert r.kind == "cast"
    # B walks; then its Idle entry (cancelled by F's flag): the re-hit within lock_win frames
    step_all(two, [fstate(1010, "Spell Antic", 10 / 60, hx=hx, b_st="Walk", facing=1)])
    out = step_all(two, [fstate(1011, "Spell Antic", 11 / 60, hx=hx, b_st="Idle", b_tin=0.0, facing=1)])
    assert out == [sp.M_A | sp.M_R] and r.presses[-1][1] == "lock" and r.b_idle == [10]
    # a later Idle entry pressed too late (more than lock_win frames after it): no press
    step_all(two, [fstate(1030, "Spell Antic", 30 / 60, hx=hx, b_st="Walk", facing=1)])
    step_all(two, [fstate(1031, "Spell Antic", 31 / 60, hx=hx, b_st="Idle", b_tin=0.0, facing=1, atk_cd=0.3)])
    out = step_all(two, [fstate(1031 + tp.AswCfg.lock_win + 1, "Spell Antic", (32 + tp.AswCfg.lock_win) / 60, hx=hx,
                                b_st="Idle", b_tin=(tp.AswCfg.lock_win + 1) / 60, facing=1)])
    assert out[0] != sp.M_A | sp.M_R and len(r.presses) == 1


def _bomb(iid, bx, lit=False, by=3.67):
    import math
    R = 2.166
    vs = [v for a in range(8) for v in (bx + R * math.cos(a * math.pi / 4), by + R * math.sin(a * math.pi / 4))]
    return {"type_key": "damager", "iid": iid, "pos": [bx, by], "colliders": [{"enabled": lit, "verts_world": vs}]}


def test_bomb_hop_over_f_runes(asw):
    two = tp.TwoPlay()
    hx = B_X - 8.8                                                # at the hold point
    stale = _bomb(554, hx + 0.2)                                  # an earlier cast's unlit leftover under her
    s0 = fstate(1000, "Idle", 0.5)
    s1 = fstate(1001, "Spell Antic", 1 / 60)
    s1["ents"].append(stale)
    step_all(two, [s0, s1])
    r = two.asw
    s = fstate(1050, "Cast 2", 0.0, hx=hx, b_st="Walk")
    s["ents"].append(stale)
    step_all(two, [s])
    assert r.f_off == 1050 and not two.asw_critical()             # the stale bomb is no threat
    # a new bomb of F's row at her x (k 52): the hop over its lit window; she stands still until the press
    outs, crit = [], []
    for f in range(1052, 1090):
        s = fstate(f, "Cast 2" if f < 1075 else "Idle", (f - 1050) / 60, hx=hx, b_st="Walk", ground=True)
        s["ents"] += [stale, _bomb(555, hx, lit=1071 <= f <= 1077)]
        two.observe(f, s, f / 60.0)
        crit.append(two.asw_critical())
        outs.append(two.step(f, s, r.hop_P is None, True, 99, f / 60.0))
    assert all(crit[:15])
    j = outs.index(sp.M_J)
    assert set(outs[:j]) == {0} and r.hops and r.hops[0][1] == r.hop_H
    assert outs[j:j + r.hop_H] == [sp.M_J] * r.hop_H and outs[j + r.hop_H] == 0
    w0 = 52 + 20 - 1
    P, H = r.hops[0][0], r.hops[0][1]
    from ssbot.combat import rune_lowhop as rl_
    assert all(rl_.HOP_LO[H][kk - P] >= 2.94 for kk in range(w0, 52 + 27 + 2))


def test_skip_slam_play_and_low_hop(monkeypatch):
    play = sp.SlamPlay(sp.PlayCfg())
    s = fstate(1001, "Slam Antic", 1 / 60)
    assert play.step(1001, s, True, True, skip=frozenset({7})) is None and play.run is None
    lh = rl.RuneLowHop(two=True)
    s = fstate(1001, "Spell Antic", 1 / 60)
    assert lh.step(1001, s, True, True, skip=frozenset({7})) is None and lh.run is None and lh.n_cast == 0


def test_gauntlet_holds_b(monkeypatch):
    monkeypatch.setattr(gt, "TWO_FOCUS", True)
    monkeypatch.setattr(tp, "ASW", True)
    ents = [clapper(1, 25.0, True), clapper(2, 42.0, False)]
    fc = [subj(1, CC, 25.0, y=7.45), subj(2, CC, 42.0, y=7.45)]
    t = l2()
    t.decide(world(29.0, ents=ents), WinFc(fc, t_min=0.1), None, 3)
    assert t.goal.target == 1
    t.two_esc = {"iid": 1, "other": 2, "mode": "aswitch", "hold": 2, "no_hit": frozenset({2}), "after_land": False,
                 "corner_aim": False, "corner_side": False, "stance": 30.3}
    fc = [subj(1, CC, 25.0, y=7.45, state="Slam Antic", family=gt.CC_SLAM, committed=True, t_free=0.9),
          subj(2, CC, 42.0, y=7.45)]
    p = t.decide(world(29.0, t=10.1, ents=ents), WinFc(fc, t_min=0.1), None, 3)
    assert p.target == 2 and 2 in p.no_hit and p.stance_x == pytest.approx(30.3)
    assert t.stats["sp7"]["esc_aswitch"] == 1
