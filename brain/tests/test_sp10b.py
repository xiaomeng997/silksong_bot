"""Task 1v1 SP10b (forum.md 80): the second hammer with two Clappers. SSBOT_FORUM_TWO_HANDOFF - when a strike run on A
closes (her landing), the run on B's slam opens at once as a late start (the jump up to K_JUMP_LATE2 30) instead of
being cut at K_START_MAX 14; SSBOT_FORUM_TWO_TIGHT - B's slam begun before A's Slam 0 + 23: SP1's way out over A to its
far side, no side slash, no key after the landing until B's Slam 2; SSBOT_FORUM_SLAM_REACH_NAME - _in_reach reads the
wave-13 body collider ("Song Heavy Sentry (2)"). Off: unchanged."""
import pytest

from ssbot.combat import slam_play as sp
from tests.test_slam_play import state


def two(f, a_st, a_tin, b_st, b_tin, ax=31.0, bx=40.0, hx=35.0, ground=True, hp=9, vy=0.0, a_flip=True,
        b_flip=False):
    """A at ax (iid 7, facing right toward B by default), B at bx (iid 8, facing left toward A), the hero at hx."""
    s = state(f, a_st, a_tin, cx=ax, flip=a_flip, hx=hx, hp=hp, ground=ground, iid=7, vy=vy)
    s["ents"].append({"type_key": sp.CLAPPER, "iid": 8, "hp": 200, "pos": [bx, 7.45], "flipX": b_flip,
                      "fsms": [{"name": "Control", "state": b_st, "t": b_tin}]})
    return s


def after_run(face=1, ta=10.0, ks0=48, k_press=47):
    """A struck run on A (iid 7) in its way out: bounced, Slam 0 seen."""
    return sp.Run(iid=7, fa=600, face=face, ta=ta, phase="after", k_start=3, k_jump=26, k_press=k_press,
                  bounced=True, s0=648, ks0=ks0, hp0=9, near=1, k_turn=60, k_slash=97)


@pytest.fixture
def two_on(monkeypatch):
    monkeypatch.setattr(sp, "TWO_PLAY", True)
    monkeypatch.setattr(sp, "LATE", True)


@pytest.mark.parametrize("on", [False, True])
def test_handoff_opens_b_as_a_late_start(two_on, monkeypatch, on):
    monkeypatch.setattr(sp, "TWO_HANDOFF", on)
    p = sp.SlamPlay(sp.PlayCfg())
    p.run = after_run()
    # A's antic at t = 10.0 s; her landing at A's antic frame 104 (A Idle); B in Slam Antic since 15 frames
    t = 10.0 + 102 / 60.0
    s = two(700, "Idle", 0.3, "Slam Antic", 15 / 60.0, hx=35.0)
    m = p.step(700, s, True, t_game=t)
    assert p.done[0].iid == 7 and p.done[0].why == "landed"
    if not on:
        assert m is None and p.run is None or p.run.phase == "wait"
        for i in range(1, 4):
            p.step(700 + i, two(700 + i, "Idle", 0.3, "Slam Antic", (15 + i) / 60.0, hx=35.0), True,
                   t_game=t + i / 60.0)
        b = [r for r in p.done if r.iid == 8]
        assert b and b[0].why == "late" and b[0].k_press is None
        return
    # on: B's run opened on the landing tick as a late start, inside the stand (5 u in front of B): walking, no key
    assert p.run is not None and p.run.iid == 8 and p.run.handoff and p.run.late
    assert p.run.phase == "walk" and m == 0
    # it jumps at K_JUMP (26) and presses at K_PRESS (47)
    masks = {}
    for i in range(1, 40):
        k_b = 15 + i
        s = two(700 + i, "Idle", 0.3, "Slam Antic", k_b / 60.0, hx=35.0, ground=k_b < 28)
        masks[k_b + 2] = p.step(700 + i, s, k_b < 28, t_game=t + i / 60.0)
    assert p.run.k_jump == 26 and p.run.k_press == 47
    assert masks[26] & sp.M_J and masks[47] & sp.M_A and masks[47] & sp.M_D
    assert p.stats()["handoff"] == 1


def test_handoff_late_jump_up_to_30(two_on, monkeypatch):
    monkeypatch.setattr(sp, "TWO_HANDOFF", True)
    p = sp.SlamPlay(sp.PlayCfg())
    p.run = after_run()
    t = 10.0 + 102 / 60.0
    # B at antic frame 27 at the landing, she 6.0 u in front of it (inside BAND 4.0-6.2): the jump at once (k 29)
    m = p.step(700, two(700, "Idle", 0.3, "Slam Antic", 27 / 60.0, hx=34.0), True, t_game=t)
    r = p.run
    assert r.iid == 8 and r.handoff and r.phase == "jump" and r.k_jump == 29 and m & sp.M_J
    assert r.k_press_plan == 47                       # 29 + 18
    # B at antic frame 31 at the landing: past K_JUMP_LATE2 -> no hand-off, aborted 'late'
    p = sp.SlamPlay(sp.PlayCfg())
    p.run = after_run()
    m = p.step(700, two(700, "Idle", 0.3, "Slam Antic", 31 / 60.0, hx=34.0), True, t_game=t)
    assert m is None and p.done[-1].iid == 8 and p.done[-1].why == "late" and not p.done[-1].handoff


def test_handoff_waits_on_the_others_danger(two_on, monkeypatch):
    monkeypatch.setattr(sp, "TWO_HANDOFF", True)
    p = sp.SlamPlay(sp.PlayCfg())
    p.run = after_run()
    t = 10.0 + 102 / 60.0
    # A jumps (its next move): the run waits (the planner decides), it does not abort before K_JUMP_LATE2
    m = p.step(700, two(700, "Jump Antic", 0.05, "Slam Antic", 15 / 60.0, hx=35.0), True, t_game=t)
    assert m is None and p.run.iid == 8 and p.run.phase == "wait" and p.run.why == "other Jump Antic"
    m = p.step(705, two(705, "Jump Antic", 0.13, "Slam Antic", 20 / 60.0, hx=35.0), True, t_game=t + 5 / 60.0)
    assert p.run is not None and p.run.phase == "wait"


def test_tight_takes_the_far_side_and_holds(two_on, monkeypatch):
    monkeypatch.setattr(sp, "TWO_TIGHT", True)
    monkeypatch.setattr(sp, "NEAR", True)
    p = sp.SlamPlay(sp.PlayCfg())
    r = after_run()
    r.near, r.k_turn, r.k_slash = None, None, None
    p.run = r
    # A0 = 10.0 + 48 / 60; B's antic began at A0 + 12 (tight); tick at A0 + 15 (A in Slam Recover), she in the air
    ta0 = 10.0 + 48 / 60.0
    t = ta0 + 15 / 60.0
    s = two(700, "Slam Recover", 0.05, "Slam Antic", 3 / 60.0, hx=33.0, ground=False, vy=8.0)
    p.step(700, s, False, t_game=t)
    assert r.tight == (8, -1) and r.near == 0 and r.over_dir == -1 and r.side_why == "tight"
    # the way out: the key toward A's far side from Slam 0 + 20, the dash at + 23
    ms = {}
    for i in range(1, 12):
        s = two(700 + i, "Slam Recover", 0.05 + i / 60.0, "Slam Antic", (3 + i) / 60.0, hx=33.0 - 0.2 * i,
                ground=False, vy=2.0)
        ms[15 + i + 2] = p.step(700 + i, s, False, t_game=t + i / 60.0)
    assert ms[22] & sp.M_L and not ms[22] & sp.M_A
    assert any(m & sp.M_DASH for m in ms.values())
    # the landing (B still in its antic): no key; B's Slam 2: the hold ends
    t2 = ta0 + 52 / 60.0
    m = p.step(740, two(740, "Idle", 0.2, "Slam Antic", 40 / 60.0, hx=24.0), True, t_game=t2)
    assert p.done[0].why == "landed" and m == 0 and p._hold is not None
    assert p.step(745, two(745, "Idle", 0.3, "Slam 0", 0.02, hx=24.0), True, t_game=t2 + 5 / 60.0) == 0
    assert p.step(760, two(760, "Idle", 0.5, "Slam 2", 0.02, hx=24.0), True, t_game=t2 + 20 / 60.0) is None
    assert p._hold is None and p.holds[0][3] == "B Slam 2"
    assert p.stats()["tight_away"] == 1


def test_tight_no_room_keeps_the_way(two_on, monkeypatch):
    monkeypatch.setattr(sp, "TWO_TIGHT", True)
    p = sp.SlamPlay(sp.PlayCfg())
    r = after_run()
    r.near, r.k_turn, r.k_slash = None, None, None
    p.run = r
    ta0 = 10.0 + 48 / 60.0
    # A at 18 (4 u from the left wall): no room on its far side
    s = two(700, "Slam Recover", 0.05, "Slam Antic", 3 / 60.0, ax=18.0, bx=27.0, hx=21.0, ground=False, vy=8.0)
    p.step(700, s, False, t_game=ta0 + 15 / 60.0)
    assert r.tight == (8, 0) and r.near is None and r.over_dir is None


def test_tight_not_when_b_starts_after_the_apex(two_on, monkeypatch):
    monkeypatch.setattr(sp, "TWO_TIGHT", True)
    p = sp.SlamPlay(sp.PlayCfg())
    r = after_run()
    p.run = r
    ta0 = 10.0 + 48 / 60.0
    # B's antic at A0 + 25
    s = two(700, "Idle", 0.05, "Slam Antic", 2 / 60.0, hx=33.0, ground=False, vy=-2.0)
    p.step(700, s, False, t_game=ta0 + 27 / 60.0)
    assert r.tight is None


@pytest.mark.parametrize("on", [False, True])
def test_reach_name_reads_the_wave13_body(monkeypatch, on):
    monkeypatch.setattr(sp, "REACH_NAME", on)
    # a Slam Recover body (front 3.37 u from its centre at 31, facing right): she 6.0 u in front, facing it
    e = {"pos": [31.0, 7.45], "colliders": [{"name": "Song Heavy Sentry (2)", "enabled": True,
                                              "verts_world": [29.81, 3.0, 34.37, 3.0, 34.37, 6.6, 29.81, 6.6]}]}
    got = sp.SlamPlay._in_reach(e, 31.0, 1, 37.2, -1)
    # the real front 34.37 is in the slash's reach from 37.2 (34.08 .. 37.01); BODY_FRONT 2.25 (33.25) is not
    assert got == on
    e["colliders"][0]["name"] = sp.CLAPPER
    assert sp.SlamPlay._in_reach(e, 31.0, 1, 37.2, -1)


# ---- SSBOT_FORUM_TWO_AIRCHAIN (combat.air_chain) ----

def test_chain_plan_cmds_matches_the_tick_by_tick_masks():
    import random

    import numpy as np

    from ssbot.combat import air_chain as ac
    rnd = random.Random(1)
    for _ in range(1500):
        F0 = 100
        fd = rnd.choice([None, F0 + rnd.randint(-3, 20)])
        fu = rnd.choice([None, F0 + rnd.randint(-3, 40)])
        fp = F0 + rnd.randint((fd - F0 + 19) if fd is not None else 0, 70)
        p = ac.Plan(F0, rnd.choice([0, ac.M_L, ac.M_R]), F0 + rnd.randint(-5, 40), fd, fu, fp, 47, 8)
        if fd is not None and fd < F0 and rnd.random() < 0.3:
            p.pressed_down = fd
        assert (ac.plan_cmds(p, F0, 90) == ac._plan_cmds_loop(p, F0, 90)).all()


def _chain_world(x=37.0, y=4.8, vy=-19.0):
    import numpy as np

    from ssbot.combat import air_chain as ac
    from ssbot.knowledge import kinematics as kin
    from ssbot.train.forum_planner_policy import CREST_PARAMS
    p = kin.HeroParams.load(CREST_PARAMS["Wanderer"])
    terr = kin.Terrain2D.from_boxes([(-200.0, 3.015 - 10.0, 260.0, 3.015), (0.0, 0.0, 14.01, 40.0),
                                     (48.99, 0.0, 70.0, 40.0)])
    S = kin.initial_state(p, x, 4.568 + y, vy=vy, facing=1, ground=False)
    return ac.ChainSim(S, np.zeros(1, np.int64), kin.HoldState.idle(1), p, terr, 1000, 1000)


@pytest.mark.parametrize("on", [False, True])
def test_chain_replaces_the_way_out(two_on, monkeypatch, on):
    """She falls toward A's Idle body 2.4 u in front of it after the strike (A0 + 40), B in Slam Antic since 5 frames
    8.6 u away facing her: on, the chain's down slash on A now (its bounce) and B's strike planned at K_PRESS 47."""
    from ssbot.combat import air_chain as ac
    monkeypatch.setattr(ac, "AIRCHAIN", on)
    monkeypatch.setattr(sp, "NEAR", True)
    p = sp.SlamPlay(sp.PlayCfg())
    r = after_run(face=1, ta=10.0)
    r.near, r.k_turn, r.k_slash = None, None, None
    p.run = r
    ta0 = 10.0 + 48 / 60.0
    s = two(1000, "Idle", 0.2, "Slam Antic", 5 / 60.0, ax=34.6, bx=44.0, hx=37.0, ground=False, vy=-19.0)
    s["hero"]["pos"] = [37.0, 4.568 + 4.8]
    s["hero"]["facing"] = 1
    m = p.step(1000, s, False, t_game=ta0 + 40 / 60.0, sim=_chain_world())
    if not on:
        assert r.chain is None and not r.chain_log
        return
    assert r.chain is not None and r.chain.b_iid == 8 and r.chain.k_press == 47
    assert r.chain.f_down is not None and m & sp.M_D
    assert r.chain_log[0][1] == "plan" and p.stats()["chain_plan"] == 1


@pytest.mark.parametrize("on", [False, True])
def test_handoff_aims_the_landing_at_bs_stand(two_on, monkeypatch, on):
    """B (12 u in front of A) in Slam Antic during A's way out: on, NEAR's landing between them moves from 3.7 u in
    front of A to B's stand (12 - 5.1 = 6.9 u in front of A)."""
    monkeypatch.setattr(sp, "TWO_HANDOFF", on)
    monkeypatch.setattr(sp, "NEAR", True)
    monkeypatch.setattr(sp, "SIDE", True)
    p = sp.SlamPlay(sp.PlayCfg())
    r = after_run(face=1, ta=10.0)
    r.near, r.k_turn, r.k_slash = None, None, None
    p.run = r
    ta0 = 10.0 + 48 / 60.0
    for i, kb in enumerate(range(0, 30, 2)):
        s = two(1000 + i, "Slam Recover", 0.1, "Slam Antic", kb / 60.0, ax=30.0, bx=42.0, hx=31.5 + 0.2 * i,
                ground=False, vy=2.0)
        p.step(1000 + i, s, False, t_game=ta0 + (12 + 2 * i) / 60.0)
    assert r.near == 1
    assert r.near_u == pytest.approx(6.9 if on else 3.7)
    assert (r.side_why == "ho_aim") == on


def test_handoff_aims_again_after_the_turn(two_on, monkeypatch):
    """B's antic begins after her turn key at NEAR's 3.7 u: the turn is undone, the landing moves to B's stand."""
    monkeypatch.setattr(sp, "TWO_HANDOFF", True)
    monkeypatch.setattr(sp, "NEAR", True)
    monkeypatch.setattr(sp, "SIDE", True)
    p = sp.SlamPlay(sp.PlayCfg())
    r = after_run(face=1, ta=10.0)
    r.near, r.near_u, r.k_turn, r.k_slash, r.side_why = 1, 3.7, 70, None, "two"
    p.run = r
    ta0 = 10.0 + 48 / 60.0
    s = two(1000, "Idle", 0.1, "Slam Antic", 2 / 60.0, ax=30.0, bx=42.0, hx=33.7, ground=False, vy=-2.0)
    m = p.step(1000, s, False, t_game=ta0 + 30 / 60.0)
    assert r.near_u == pytest.approx(6.9) and r.k_turn is None and m & sp.M_R


@pytest.mark.parametrize("v2,ho,want", [("1", None, True), ("1", "0", False), ("0", None, False), (None, None, False)])
def test_handoff_and_reach_follow_v2(monkeypatch, v2, ho, want):
    """Since the SP10b A/B: TWO_HANDOFF and SLAM_REACH_NAME follow SSBOT_FORUM_V2 when unset (=0 off); TWO_TIGHT and
    TWO_AIRCHAIN stay off."""
    import importlib

    from ssbot.combat import air_chain
    for k, v in (("SSBOT_FORUM_V2", v2), ("SSBOT_FORUM_TWO_HANDOFF", ho), ("SSBOT_FORUM_SLAM_REACH_NAME", ho)):
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    monkeypatch.delenv("SSBOT_FORUM_TWO_TIGHT", raising=False)
    monkeypatch.delenv("SSBOT_FORUM_TWO_AIRCHAIN", raising=False)
    try:
        m = importlib.reload(sp)
        a = importlib.reload(air_chain)
        assert m.TWO_HANDOFF == want and m.REACH_NAME == want
        assert not m.TWO_TIGHT and not a.AIRCHAIN
    finally:
        monkeypatch.undo()
        importlib.reload(air_chain)
        importlib.reload(sp)
