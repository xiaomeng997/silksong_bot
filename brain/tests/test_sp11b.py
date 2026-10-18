"""Task 1v1 SP11b (forum.md 84): the focus at its wall - SSBOT_FORUM_TWO_EARLYSWITCH (the antic switch with the spec's
numbers and the predicted-distance gate), SSBOT_FORUM_TWO_WALKOUT (stand off beyond its Slam Range through its Idle while
it walks out), SSBOT_FORUM_TWO_OPENPUSH (no hit on c2 near its wall in the opening), SSBOT_FORUM_TWO_RUNLOCK (the switch
run bounded by the focus's lock end), SSBOT_FORUM_TWO_PUSHMID (F's slam's way out to its wall side, then the herd); each
default off."""
import importlib
from types import SimpleNamespace

import pytest

from ssbot.combat import slam_play as sp
from ssbot.combat import two_play as tp
from tests.test_sp9 import two_state

SW = ("SSBOT_FORUM_TWO_EARLYSWITCH", "SSBOT_FORUM_TWO_WALKOUT", "SSBOT_FORUM_TWO_OPENPUSH", "SSBOT_FORUM_TWO_RUNLOCK",
      "SSBOT_FORUM_TWO_PUSHMID")


def test_defaults_off(monkeypatch):
    for k in SW:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SSBOT_FORUM_V2", "1")
    try:
        m = importlib.reload(tp)
        assert not (m.EARLY or m.WALKOUT or m.OPENPUSH or m.RUNLOCK or m.PUSHMID or m.SP11B)
        assert m.ASW == m.ANTICSWITCH and not m.ASW
        monkeypatch.setenv("SSBOT_FORUM_TWO_EARLYSWITCH", "1")
        m = importlib.reload(tp)
        assert m.EARLY and m.ASW and not m.ANTICSWITCH
        c = m.TwoPlay().acfg
        assert (c.casts, c.trig, c.back_u, c.first, c.sep_slam, c.early) == (0, 0, 8.1, 0, 17.1, 1)
    finally:
        for k in SW + ("SSBOT_FORUM_V2",):
            monkeypatch.delenv(k, raising=False)
        importlib.reload(tp)


@pytest.fixture
def sp11b(monkeypatch):
    for k in ("WALKOUT", "OPENPUSH", "RUNLOCK", "PUSHMID", "SP11B", "ANY", "IDLEHIT", "SPACE"):
        monkeypatch.setattr(tp, k, True)
    monkeypatch.setattr(tp, "GUARD", False)
    yield


def test_walkout_stands_off_and_ends_drawn(sp11b):
    two = tp.TwoPlay()
    # F (iid 7) 4.99 u from the left wall in its Slam Recover, facing her (right); she 4 u in front; B idle at 40
    s = two_state(100, "Slam Recover", 0.1, x_rel=4.0, cx=19.0, flip=True, b_st="Idle", b_x=40.0)
    two.observe(100, s, 100 / 60.0)
    m = two.step(100, s, True, True, 7, 100 / 60.0)
    assert two.wo is not None and two.wo.dir == 1 and abs(two.wo.sx - (19.0 + 8.9)) < 1e-6
    assert m is not None and m & tp.M_R                          # away from F toward the stand
    assert 7 in two.sp11b_nohit(s)                               # no hit on F through the run
    # at the stand: no key (facing F: the turn key first)
    s2 = two_state(101, "Idle", 0.0, hx=27.9, cx=19.0, flip=True, b_st="Idle", b_x=40.0, facing=-1)
    two.observe(101, s2, 101 / 60.0)
    assert two.step(101, s2, True, True, 7, 101 / 60.0) == 0
    # F walks out: its back reaches draw_u -> the run ends
    s3 = two_state(102, "Walk", 0.1, hx=34.5, cx=25.6, flip=True, b_st="Idle", b_x=44.0)
    two.observe(102, s3, 102 / 60.0)
    assert two.wo is None and two.wo_done[-1].end == "drawn" and two.wo_done[-1].walks == 1


def test_walkout_no_start_b_busy_or_far_from_wall(sp11b):
    two = tp.TwoPlay()
    s = two_state(100, "Slam Recover", 0.1, x_rel=4.0, cx=19.0, flip=True, b_st="Slam Antic", b_x=40.0)
    two.observe(100, s, 100 / 60.0)
    two.step(100, s, True, True, 7, 100 / 60.0)
    assert two.wo is None and two.wo_n["no_b busy"] == 1
    two = tp.TwoPlay()
    s = two_state(100, "Slam Recover", 0.1, x_rel=4.0, cx=25.0, flip=True, b_st="Idle", b_x=44.0)
    two.observe(100, s, 100 / 60.0)
    two.step(100, s, True, True, 7, 100 / 60.0)
    assert two.wo is None and not two.wo_n.get("cand")


def test_openpush_nohit_c2_near_its_wall(sp11b):
    two = tp.TwoPlay()
    two.open["f_wake"] = 50
    s = two_state(60, "Enter Land", 0.1, x_rel=4.2, cx=20.8, flip=True, b_st="Enter Land", b_x=42.0)
    two.observe(60, s, 1.0)
    assert two.op["c2"] == 7 and 7 in two.sp11b_nohit(s)
    s2 = two_state(61, "Slam Antic", 0.0, x_rel=4.2, cx=20.8, flip=True, b_st="Idle", b_x=42.0)
    two.observe(61, s2, 61 / 60.0)
    assert two.op["end"] == "move" and 7 not in two.sp11b_nohit(s2)


def test_runlock_bound():
    from ssbot.combat.tactics import gauntlet as gt
    stub = SimpleNamespace(rune={}, _two_idle={})
    f = SimpleNamespace(s=SimpleNamespace(iid=1, family=gt.CC_SLAM, committed=True, t_free=0.6))
    o = SimpleNamespace(s=SimpleNamespace(iid=2, family=gt.CC_IDLE), d=7.0 + 8.25 * 0.4)    # need 0.4 s
    old = tp.RUNLOCK
    try:
        tp.RUNLOCK = False
        assert gt.GauntletTactics._two_run_ok(stub, f, o, 0.0) == (True, "focus committed")
        tp.RUNLOCK = True                                  # lock end: 0.6 - (1.2583 - 0.92) = 0.26 s < 0.4
        assert gt.GauntletTactics._two_run_ok(stub, f, o, 0.0)[0] is False
    finally:
        tp.RUNLOCK = old


def test_pushmid_start_hint_and_herd(sp11b):
    two = tp.TwoPlay()
    # F (7) at 22 facing right (room to the left wall 7.99 u), she 4 u in front, B (99) idle at 44 (room 4.99 ... no:
    # B's outer room is to the right wall 4.99 u) -> F has the larger room: no run
    s = two_state(200, "Slam Antic", 0.0, x_rel=4.0, cx=22.0, flip=True, b_st="Idle", b_x=44.0)
    two.observe(200, s, 200 / 60.0)
    assert two.pm is None
    # B at 36 (outer room 12.99 u > F's 7.99 + 1), she 4 u in front of F: the run to B (10 u) misses F's lock -> run
    two = tp.TwoPlay()
    s = two_state(200, "Slam Antic", 0.0, x_rel=4.0, cx=22.0, flip=True, b_st="Idle", b_x=37.0)
    two.observe(200, s, 200 / 60.0)
    assert two.pm is None and two.pm_n["no_run ok"] == 1     # 15 - 4 = 11 u to B: need (11 - 7) / 8.25 < 0.88 s
    two = tp.TwoPlay()
    s = two_state(200, "Slam Antic", 0.6, x_rel=4.0, cx=22.0, flip=True, b_st="Idle", b_x=40.0)
    s["prev_hack"] = True
    two.prev[7] = ("Idle", 0.5)
    two.observe(200, s, 200 / 60.0)
    assert two.pm is not None and two.pm.wdir == -1 and two.pm_hint() == {7: -1}
    v = two.pm_view()
    assert v["hold"] == 7 and v["phase"] == "strike"
    play = sp.SlamPlay()
    play.side_hint = two.pm_hint()
    e = s["ents"][0]
    r = SimpleNamespace(face=1)
    assert play._side_pref(r, s, e, 22.0) == (-1, "pushmid")
    # she landed behind F (its wall side) after its slam: the herd; ret 1 ends at F's next antic
    s2 = two_state(260, "Idle", 0.2, hx=18.5, cx=22.5, flip=False, b_st="Idle", b_x=40.0)
    two.observe(260, s2, 260 / 60.0)
    assert two.pm is not None and two.pm.phase == "herd"
    s3 = two_state(300, "Spell Antic", 0.0, hx=18.5, cx=23.0, flip=False, b_st="Idle", b_x=40.0)
    two.observe(300, s3, 300 / 60.0)
    assert two.pm is None and two.pm_done[-1].end == "f move" and two.pm_done[-1].next_st == "Spell Antic"
