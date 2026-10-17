"""Task 1v1 SP9a (forum.md 76): two Clappers - the focus's evade chase (TWO_CHASE), the hit at its Idle entry
(TWO_IDLEHIT), the low hop on its close cast (TWO_CAST), the stance spacing (TWO_SPACE), the opening (TWO_OPEN); every
switch default off (ssbot.combat.two_play, evade_chase, rune_lowhop)."""
import copy
import importlib

import pytest

from ssbot.combat import evade_chase as ec
from ssbot.combat import rune_lowhop as rl
from ssbot.combat import slam_play as sp
from ssbot.combat import two_play as tp
from ssbot.combat.tactics.modes import GoalPrefs
from tests.test_slam_play import state

SW = ("SSBOT_FORUM_TWO_CHASE", "SSBOT_FORUM_TWO_IDLEHIT", "SSBOT_FORUM_TWO_CAST", "SSBOT_FORUM_TWO_SPACE",
      "SSBOT_FORUM_TWO_OPEN")


def two_state(f, st, tin, x_rel=4.0, cx=31.0, flip=False, ground=True, atk_cd=0.0, facing=None, b_st="Idle",
              b_x=46.0, b_flip=False, ev=(), hx=None):
    """F (iid 7) in Control state st at its state time tin, her centre x_rel in front of it; B (iid 99) at b_x."""
    face = 1 if flip else -1
    s = state(f, st, tin, cx=cx, flip=flip, hx=cx + face * x_rel if hx is None else hx, ground=ground)
    h = s["hero"]
    h["anim"] = {"clip": "Idle"}
    h["tm"] = {"dash_cd": 0.0, "atk_cd": atk_cd}
    h["facing"] = -face if facing is None else facing
    s["ents"][0]["vel"] = [0.0, 0.0]
    o = copy.deepcopy(s["ents"][0])
    o["iid"] = 99
    o["pos"] = [b_x, 7.45]
    o["flipX"] = b_flip
    o["fsms"] = [{"name": "Control", "state": b_st, "t": 0.1}]
    s["ents"].append(o)
    s["ev"] = list(ev)
    return s


@pytest.fixture
def on(monkeypatch):
    for k in ("CHASE", "IDLEHIT", "CAST", "SPACE", "OPEN", "ANY"):
        monkeypatch.setattr(tp, k, True)
    yield


def test_switches_follow_v2(monkeypatch):
    for k in SW:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("SSBOT_FORUM_V2", raising=False)
    try:
        m = importlib.reload(tp)
        assert not (m.CHASE or m.IDLEHIT or m.CAST or m.SPACE or m.OPEN or m.ANY)       # no v2: off
        monkeypatch.setenv("SSBOT_FORUM_V2", "1")
        m = importlib.reload(tp)
        assert m.CHASE and m.IDLEHIT and m.CAST and m.SPACE and m.OPEN and m.ANY        # since the SP9a A/B
        assert importlib.reload(sp).TWO_PLAY
        from ssbot.combat.tactics import gauntlet as gt
        assert importlib.reload(gt).TWO_FOCUS
        for k in SW + ("SSBOT_FORUM_TWO_PLAY", "SSBOT_FORUM_TWO_FOCUS"):
            monkeypatch.setenv(k, "0")
        m = importlib.reload(tp)
        assert not (m.CHASE or m.IDLEHIT or m.CAST or m.SPACE or m.OPEN or m.ANY)       # =0: off (arm rnsp9a0)
        assert not importlib.reload(sp).TWO_PLAY and not importlib.reload(gt).TWO_FOCUS
    finally:
        for k in SW + ("SSBOT_FORUM_TWO_PLAY", "SSBOT_FORUM_TWO_FOCUS"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.delenv("SSBOT_FORUM_V2", raising=False)
        importlib.reload(tp)
        importlib.reload(sp)
        from ssbot.combat.tactics import gauntlet as gt
        importlib.reload(gt)


def run(two, ss, focus=7, two_enc=False, wake_f=None):
    out = []
    for s in ss:
        two.observe(s["f"], s, s["f"] / 60.0)
        g = sp.on_ground(s)
        out.append(two.step(s["f"], s, g, True, focus, s["f"] / 60.0, wake_f=wake_f, two_enc=two_enc))
    return out


def test_idle_entry_press(on):
    two = tp.TwoPlay()
    out = run(two, [two_state(1000, "Slam Recover", 0.3), two_state(1001, "Idle", 0.0), two_state(1002, "Idle", 1 / 60)])
    assert out[0] is None
    assert out[1] == sp.M_A | sp.M_R           # F is to her right: the key toward it with the press
    assert out[2] == sp.M_A | sp.M_R           # the press's second frame
    st = two.stats()
    assert st["idle_runs"] == 1 and st["idle_press"] == 1


def test_idle_reentry_press(on):
    two = tp.TwoPlay()
    out = run(two, [two_state(1000, "Idle", 0.30, atk_cd=0.5), two_state(1001, "Idle", 0.31, atk_cd=0.5),
                    two_state(1002, "Idle", 0.0)])
    assert out[2] == sp.M_A | sp.M_R           # its state time started again: a re-entry
    assert two.idle.re


def test_idle_turn_first(on):
    two = tp.TwoPlay()
    out = run(two, [two_state(1000, "Walk", 0.3, facing=-1), two_state(1001, "Idle", 0.0, facing=-1),
                    two_state(1002, "Idle", 1 / 60, facing=1)])
    assert out[1] == sp.M_R                    # she faces away: the turn key first
    assert out[2] == sp.M_A | sp.M_R


def test_idle_walk_in_and_far(on):
    two = tp.TwoPlay()
    out = run(two, [two_state(1000, "Walk", 0.3, x_rel=7.0), two_state(1001, "Idle", 0.0, x_rel=7.0)])
    assert out[1] == sp.M_R                    # out of reach: the walk toward it
    two = tp.TwoPlay()
    out = run(two, [two_state(1000, "Walk", 0.3, x_rel=13.0), two_state(1001, "Idle", 0.0, x_rel=13.0)])
    assert out[1] is None                      # no reach within the window: the planner
    assert two.idle.why == "far"


def test_idle_no_start_other_slam_or_air(on):
    two = tp.TwoPlay()
    # B 9 u from her in its Slam Antic facing her (flip False: it faces left; she is left of it)
    out = run(two, [two_state(1000, "Walk", 0.3), two_state(1001, "Idle", 0.0, b_st="Slam Antic", b_x=36.0)])
    assert out[1] is None and two.idle.why.startswith("other")
    two = tp.TwoPlay()
    out = run(two, [two_state(1000, "Walk", 0.3), two_state(1001, "Idle", 0.0, ground=False)])
    assert out[1] is None and two.idle.why == "air"


def test_idle_not_the_other(on):
    two = tp.TwoPlay()
    # the focus is B (iid 99, Idle far away): F's Idle entry does not start a run
    out = run(two, [two_state(1000, "Walk", 0.3, b_st="Walk"), two_state(1001, "Idle", 0.0, b_st="Walk")], focus=99)
    assert out[1] is None and two.idle is None


def test_opening(on):
    two = tp.TwoPlay()
    s0 = two_state(1000, "Idle", 0.0, hx=28.0)
    s0["ents"] = []
    out = run(two, [s0], two_enc=True, wake_f=1000)
    assert out[0] == sp.M_L                    # no Clapper yet: the walk to OPEN_X
    s1 = two_state(1100, "Idle", 0.0, hx=tp.OPEN_X)
    s1["ents"] = []
    assert run(two, [s1], two_enc=True, wake_f=1000)[0] == 0
    # c2 in Enter Land at 21.03 (faces right toward her), c3 at 42.03: the slash
    s2 = two_state(1150, "Enter Land", 0.05, cx=21.03, flip=True, hx=tp.OPEN_X, b_x=42.03, b_st="Enter Land",
                   facing=-1)
    out = run(two, [s2], two_enc=True, wake_f=1000)
    assert out[0] == sp.M_A | sp.M_L
    # c2's Idle: the opening ends
    s3 = two_state(1180, "Idle", 0.0, cx=21.03, flip=True, hx=tp.OPEN_X, b_x=42.03, b_st="Idle", facing=-1,
                   atk_cd=0.2)
    run(two, [s3], two_enc=True, wake_f=1000)
    assert two.open["done"] == "c2 idle"


def test_space_slam_other_and_jump(on):
    two = tp.TwoPlay()
    s = two_state(1000, "Idle", 0.0, cx=30.0, x_rel=3.0, b_st="Slam Antic", b_x=40.0)
    two.observe(1000, s, 1000 / 60.0)
    p = two.space(GoalPrefs(mode="RUSH", weights={}, stance_x=31.5), s, 1000 / 60.0, 7)
    assert not (30.0 - 4.25 < p.stance_x < 30.0 + 4.25)
    # B 20 u away: no slam span
    s = two_state(1000, "Idle", 0.0, cx=30.0, x_rel=3.0, b_st="Slam Antic", b_x=47.0)
    p = two.space(GoalPrefs(mode="RUSH", weights={}, stance_x=33.5), s, 1000 / 60.0, 7)
    assert p.stance_x == 33.5
    # B's jump: take-off at 40 facing left, her x 34 at its aim -> landing 40 + 0.92 * (34 + 5 - 40) = 39.08; the
    # band 4-8.3 u in front (left): 30.78 .. 35.08
    two = tp.TwoPlay()
    for f, st in ((1000, "Jump Antic"), (1030, "Jump"), (1031, "Air")):
        s = two_state(f, "Idle", 0.0, cx=22.0, hx=34.0, b_st=st, b_x=40.0)
        two.observe(f, s, f / 60.0)
    p = two.space(GoalPrefs(mode="RUSH", weights={}, stance_x=33.0), s, 1031 / 60.0, 7)
    assert p.stance_x < 30.78 - 0.2 or p.stance_x > 35.08 + 0.2


def test_chase_two_focus_only():
    ch = ec.EvadeChase(one=False, two=True)
    s = two_state(1000, ec.EVADE, 3 / 60.0, x_rel=4.0)
    assert ch.step(1000, s, True, True, focus=99) is None        # the other one is the focus: no chase
    m = ch.step(1001, two_state(1001, ec.EVADE, 4 / 60.0, x_rel=4.2), True, True, focus=7)
    assert m is not None and ch.run is not None
    # one live Clapper with one=False: no chase
    ch = ec.EvadeChase(one=False, two=True)
    s = two_state(1000, ec.EVADE, 3 / 60.0, x_rel=4.0)
    s["ents"] = s["ents"][:1]
    assert ch.step(1000, s, True, True, focus=7) is None
    # the default (one=True, two=False) with two: "two"
    ch = ec.EvadeChase()
    assert ch.step(1000, two_state(1000, ec.EVADE, 3 / 60.0), True, True) is None
    assert ch.why_not.get("two") == 1


def test_lowhop_two_picks_the_caster():
    hop = rl.RuneLowHop(two=True)
    s = two_state(1000, "Spell Antic", 2 / 60.0, x_rel=4.0)
    hop.step(1000, s, True, True, t_game=1000 / 60.0)
    assert hop.run is not None and hop.run.iid == 7
    hop = rl.RuneLowHop(two=True)
    s = two_state(1000, "Spell Antic", 2 / 60.0, x_rel=4.0, b_st="Slam Antic", b_x=36.0)
    hop.step(1000, s, True, True, t_game=1000 / 60.0)
    assert hop.run is None and hop.why_not.get("other") == 1
    hop = rl.RuneLowHop()                       # the default: one live Clapper only
    hop.step(1000, two_state(1000, "Spell Antic", 2 / 60.0, x_rel=4.0), True, True, t_game=1000 / 60.0)
    assert hop.run is None and hop.why_not.get("two") == 1


def test_intro_keys():
    s = two_state(1000, "Idle", 0.0, hx=40.0)
    assert tp.intro_keys(s) == sp.M_L
    s = two_state(1000, "Idle", 0.0, hx=26.0)
    assert tp.intro_keys(s) == 0


def test_idle_hit_seen_while_another_script_has_the_keys(on):
    two = tp.TwoPlay()
    run(two, [two_state(1000, "Slam Recover", 0.3), two_state(1001, "Idle", 0.0), two_state(1002, "Idle", 1 / 60)])
    # the hit shows with its next move begun (another script takes the keys: no step this tick)
    s = two_state(1004, "Spell Antic", 0.0, ev=[{"k": "hit", "d": {"ent": 7, "type_key": sp.CLAPPER, "dealt": 9}}])
    two.observe(1004, s, 1004 / 60.0)
    assert two.idle is None and two.idle_done[-1].k_hit == 3 and two.idle_done[-1].why == "hit"
