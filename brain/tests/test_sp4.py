"""Task 1v1 SP4 (forum.md 68): the slam playbook's late start (SSBOT_FORUM_SLAM_PLAY_LATE), the never-flee stance after
the hammer (SSBOT_FORUM_SLAM_AFTER) and the jump-behind sub-switches (SSBOT_FORUM_JB_PASS / _LAND / _NOJUMP /
_CAST_ANTIC / _WALL): each off by default, off nothing changes; on, the documented branch."""
import pytest

from ssbot.combat import jump_behind as jb
from ssbot.combat import slam_play as sp
from ssbot.combat.are_types import clapper as cl
from ssbot.core.worldstate import E
from tests.test_forum_l2 import CC, WinFc, clapper, l2, subj, world
from tests.test_slam_play import keys, simulate, slam_state, state

JMP = dict(y=7.45, family="CC_JUMP", committed=True)
CAST = dict(y=7.45, family="CC_JUMP_CAST", committed=True)


def test_switches_off_by_default():
    assert not sp.LATE and not sp.AFTER and not sp.NODASH and not sp.NOPOGO
    assert not (jb.PASS_HIT or jb.LAND_HIT or jb.NO_JUMP or jb.CAST_ANTIC or jb.WALL_PUSH)


# ---- the playbook's late start ----

def simulate_noinput(x0, until_k, late, flip=False):
    """A toy slam whose hero accepts no input (the sprint's skid) until antic frame until_k, standing at x0."""
    play = sp.SlamPlay(sp.PlayCfg())
    face = 1 if flip else -1
    cx = 31.0
    hx = cx + face * x0
    pending, landed = {}, {}
    air_from = None
    press = None
    for k in range(-5, 120):
        f = 1000 + k
        m = pending.pop(f, None)
        if m is not None:
            landed[k] = m
            if m & sp.M_J and air_from is None:
                air_from = k
            if m & sp.M_A and press is None:
                press = k
            if air_from is None:
                hx += ((1 if m & sp.M_R else 0) - (1 if m & sp.M_L else 0)) * sp.WALK_U
        ground = air_from is None or k > air_from + 60
        st, tin = slam_state(k)
        s = state(f, st, tin, cx=cx, flip=flip, hx=hx, ground=ground,
                  vy=17.0 if press is not None and press + 4 <= k < press + 19 else 0.0)
        acc = k >= until_k
        s["hero"]["hero_accepting_input"] = acc
        out = play.step(f, s, ground, acc)
        if out is not None:
            pending[f + 2] = out
    return play, landed


def test_late_start_after_a_skid(monkeypatch):
    # no input to antic frame 20, 5.1 u in front (the live skids ended at 4.8-5.5 u): off, declined; on, the jump at the
    # script's frame and the press on time
    play, landed = simulate_noinput(5.1, 20, late=False)
    assert not keys(landed, sp.M_A) and play.done[0].why.startswith("no input")
    monkeypatch.setattr(sp, "LATE", True)
    play, landed = simulate_noinput(5.1, 20, late=True)
    c = play.cfg
    assert keys(landed, sp.M_J)[0] == c.k_jump and keys(landed, sp.M_A) == [c.k_press]
    # input back at frame 27 (seen at 27, the key lands at 29): the jump at once, the press 18 frames later (t1: by
    # K_PRESS_MAX_LATE = Slam 0 - 1)
    play, landed = simulate_noinput(5.1, 27, late=True)
    j = keys(landed, sp.M_J)
    assert j and j[0] == 29 and keys(landed, sp.M_A) == [29 + c.press_after_late]
    # back at 6.9 u at frame 18: walks into the band, then jumps (by K_JUMP_LATE2)
    play, landed = simulate_noinput(6.9, 18, late=True)
    j = keys(landed, sp.M_J)
    assert j and j[0] <= c.k_jump_late2 and keys(landed, sp.M_A)
    # too late (input back at 31): no start
    play, landed = simulate_noinput(5.1, 31, late=True)
    assert not keys(landed, sp.M_A)


def test_late_landing_at_28(monkeypatch):
    # airborne at the antic, down at frame 28 (the 7 live aborts): off, "no landing"; on, the jump at 30, press at 48
    # (K_PRESS_MAX_LATE: SP4 t1, jump 30 + press 49 hit the hammer twice at Slam 0 + 1)
    play, landed, _ = simulate(5.2, ground_until=27)
    assert not keys(landed, sp.M_A) and play.done[0].why == "no landing"
    monkeypatch.setattr(sp, "LATE", True)
    play, landed, _ = simulate(5.2, ground_until=27)
    c = play.cfg
    assert keys(landed, sp.M_J)[0] == 30 and keys(landed, sp.M_A) == [c.k_press_max_late] == [48]



def test_late_press_cap(monkeypatch):
    # LATE: every press by K_PRESS_MAX_LATE (48: SP4 t1, a jump at 30 + the press at 49 hit the hammer at Slam 0 + 1);
    # a jump at K_JUMP still presses at K_PRESS
    monkeypatch.setattr(sp, "LATE", True)
    play, landed, _ = simulate(5.2)
    assert keys(landed, sp.M_J)[0] == play.cfg.k_jump and keys(landed, sp.M_A) == [play.cfg.k_press]
    play, landed, _ = simulate(5.2, cfg=sp.PlayCfg(k_jump=30))
    assert keys(landed, sp.M_J)[0] == 30 and keys(landed, sp.M_A) == [48]
    monkeypatch.setattr(sp, "LATE", False)
    play, landed, _ = simulate(5.2, cfg=sp.PlayCfg(k_jump=30))
    assert not keys(landed, sp.M_J) and play.done[0].why == "late jump"          # off: SP1's latest jump is 29


# ---- after the hammer ----

def test_slam_after_stance(monkeypatch):
    sl = dict(y=7.45, family="CC_SLAM", committed=True)
    t = l2()
    t.decide(world(34.0, ents=[clapper(9, 40.0, False)]), WinFc([subj(9, CC, 40.0, state="Slam 2", **sl)]), None, 3)
    assert t.last["goal_why"].endswith("slam: step out")              # off: the old flight
    monkeypatch.setattr(sp, "AFTER", True)
    t = l2()
    p = t.decide(world(34.0, ents=[clapper(9, 40.0, False)]), WinFc([subj(9, CC, 40.0, state="Slam 2", **sl)]), None, 3)
    assert t.last["goal_why"].endswith("slam: outside") and p.stance_x == pytest.approx(40.0 - sp.OUTSIDE_U)
    assert p.hit_w.get(9, 0.0) == 0.0
    p = t.decide(world(32.0, t=10.3, ents=[clapper(9, 40.0, False)]),
                 WinFc([subj(9, CC, 40.0, state="Slam Recover", **sl)]), None, 3)
    assert t.last["goal_why"].endswith("slam: after") and p.stance_x == pytest.approx(40.0 - sp.AFTER_U)
    assert p.hit_w[9] > 0 and p.ground_hit == frozenset({9})
    # the antic and the lunge: unchanged
    p = t.decide(world(34.0, t=10.6, ents=[clapper(9, 40.0, False)]),
                 WinFc([subj(9, CC, 40.0, state="Slam 1", **sl)]), None, 3)
    assert t.last["goal_why"].endswith("slam: step out")


# ---- jump behind ----

@pytest.fixture
def jb_on(monkeypatch):
    monkeypatch.setattr(jb, "ENABLED", True)
    return monkeypatch


def test_cast_antic_slash(jb_on):
    t = l2()
    p = t.decide(world(26.0, t=10.0, ents=[clapper(9, 35.0, False)]),
                 WinFc([subj(9, CC, 35.0, state="Cast Slam Antic", **CAST)]), None, 3)
    assert t.last["goal_why"].endswith("jump: aim stance") and p.no_hit == frozenset({9})     # off
    jb_on.setattr(jb, "CAST_ANTIC", True)
    t = l2()
    p = t.decide(world(26.0, t=10.0, ents=[clapper(9, 35.0, False)]),
                 WinFc([subj(9, CC, 35.0, state="Cast Slam Antic", **CAST)]), None, 3)
    assert t.last["goal_why"].endswith("jump: cast antic slash")
    assert p.stance_x == pytest.approx(35.0 - jb.CFG["cast_u"]) and p.ground_hit == frozenset({9}) and p.hit_w[9] > 0
    # past cast_slash_s: the aim stance again
    p = t.decide(world(30.7, t=10.0 + jb.CFG["cast_slash_s"] + 0.05, ents=[clapper(9, 35.0, False)]),
                 WinFc([subj(9, CC, 35.0, state="Cast Slam Antic 2", **CAST)]), None, 3)
    assert t.last["goal_why"].endswith("jump: aim stance") and p.no_hit == frozenset({9})
    # the jump slam's antic: unchanged
    t = l2()
    t.decide(world(26.0, t=10.0, ents=[clapper(9, 35.0, False)]),
             WinFc([subj(9, CC, 35.0, state="Jump Antic", **JMP)]), None, 3)
    assert t.last["goal_why"].endswith("jump: aim stance")


def _flight(t, vy, hx=29.8, tt=10.5, cy=8.2):
    e = clapper(9, 35.0, False)
    e.vel = E((-0.5, vy))
    return t.decide(world(hx, t=tt, ents=[e]),
                    WinFc([subj(9, CC, 35.0, y=cy, state="Air", family="CC_JUMP", committed=True)]), None, 3)


def test_pass_and_land(jb_on):
    t = l2()
    t.decide(world(26.0, t=10.0, ents=[clapper(9, 35.0, False)]),
             WinFc([subj(9, CC, 35.0, state="Jump Antic", **JMP)]), None, 3)
    p = _flight(t, 20.0)
    assert p.no_hit == frozenset({9})                                   # off: no hit in the flight
    p = _flight(t, -20.0, tt=10.9)
    assert p.no_hit == frozenset({9})
    jb_on.setattr(jb, "LAND_HIT", True)
    p = _flight(t, 20.0, tt=11.0)
    assert p.no_hit == frozenset({9})                                   # rising: still none
    p = _flight(t, -20.0, tt=11.1)
    assert t.last["goal_why"].endswith("(falling)") and p.ground_hit == frozenset({9}) and p.no_hit == frozenset()
    jb_on.setattr(jb, "LAND_HIT", False)
    jb_on.setattr(jb, "PASS_HIT", True)
    p = _flight(t, 20.0, tt=11.2)
    assert t.last["goal_why"].endswith("(flight)") and p.ground_hit == frozenset({9}) and p.no_hit == frozenset()


def test_nojump_ground_first(jb_on):
    t = l2()
    land = dict(y=7.45, family="CC_JUMP", committed=True)
    t.decide(world(26.0, t=10.0, ents=[clapper(9, 35.0, False)]),
             WinFc([subj(9, CC, 35.0, state="Jump Antic", **JMP)]), None, 3)
    p = t.decide(world(38.0, t=11.4, ents=[clapper(9, 34.6, False)]),
                 WinFc([subj(9, CC, 34.6, state="Slam 2", **land)]), None, 3)
    assert p.ground_first == frozenset()
    jb_on.setattr(jb, "NO_JUMP", True)
    p = t.decide(world(38.0, t=11.5, ents=[clapper(9, 34.6, False)]),
                 WinFc([subj(9, CC, 34.6, state="Slam Recover", **land)]), None, 3)
    assert p.ground_first == frozenset({9}) and p.ground_hit == frozenset({9})


def test_wall_push_in_the_estimate(monkeypatch):
    # its back 2 u from the left wall facing right, vx 0.5: the formula lands 0.46 u out; the push 4.4 u from the wall
    x = jb.WALL_L + 2.0
    s, L = cl.jump_rule(x, 7.45, 0.5, x + 5.5, 4.5)
    assert s == 1 and L == pytest.approx(0.916 * 0.5)
    monkeypatch.setattr(jb, "WALL_PUSH", True)
    s, L = cl.jump_rule(x, 7.45, 0.5, x + 5.5, 4.5)
    assert s == 1 and L == pytest.approx(4.4 - 2.0)
    # the right wall, facing left; and away from the walls: unchanged
    x = jb.WALL_R - 3.0
    s, L = cl.jump_rule(x, 7.45, -0.2, x - 5.0, 4.5)
    assert s == -1 and L == pytest.approx(4.4 - 3.0)
    s, L = cl.jump_rule(30.0, 7.45, -3.0, 25.0, 4.5)
    assert L == pytest.approx(0.916 * 3.0)


def test_planner_ground_first_key():
    """The ranking key itself: with GoalPrefs.ground_first a safe ground row beats a safe jump row of equal hits."""
    import numpy as np
    B_JUMP = sp.M_J
    cmd = np.zeros((3, 10), np.int64)
    cmd[0, :4] = B_JUMP
    safe = np.array([True, True, False])
    jr = safe & ((cmd & B_JUMP) != 0).any(axis=1)
    J = np.array([5.0, 1.0, 9.0])
    nh = np.array([0.0, 0.0, 0.0])
    order = np.lexsort((-J, jr.astype(np.int64), -nh, ~safe))
    assert int(order[0]) == 1


def test_nodash_prefs(monkeypatch):
    # SSBOT_FORUM_SLAM_PLAY_NODASH: near the idle / evading Clapper GoalPrefs.no_dash = its iid; off, far, or in a move: none
    monkeypatch.setattr(sp, "ENABLED", True)
    t = l2()
    p = t.decide(world(29.0, t=10.0, ents=[clapper(9, 35.0, False)]), WinFc([subj(9, CC, 35.0, y=7.45)]), None, 3)
    assert p.no_dash == frozenset()                                     # off
    monkeypatch.setattr(sp, "NODASH", True)
    p = t.decide(world(29.0, t=10.1, ents=[clapper(9, 35.0, False)]), WinFc([subj(9, CC, 35.0, y=7.45)]), None, 3)
    assert p.no_dash == frozenset({9})
    p = t.decide(world(29.0, t=10.2, ents=[clapper(9, 35.0, False)]),
                 WinFc([subj(9, CC, 35.0, y=7.45, state="Evade Scuttle", family="CC_EVADE")]), None, 3)
    assert p.no_dash == frozenset({9})
    p = t.decide(world(20.0, t=10.3, ents=[clapper(9, 35.0, False)]), WinFc([subj(9, CC, 35.0, y=7.45)]), None, 3)
    assert p.no_dash == frozenset()                                     # 15 u away
    p = t.decide(world(29.0, t=10.4, ents=[clapper(9, 35.0, False)]),
                 WinFc([subj(9, CC, 35.0, y=7.45, state="Slam Antic", family="CC_SLAM", committed=True)]), None, 3)
    assert p.no_dash == frozenset()                                     # in its slam: the playbook / the planner


def test_planner_nodash_key():
    """The ranking key: with no_dash a safe row without a dash beats a safe dash row with more landed hits; an unsafe
    row stays last."""
    import numpy as np
    cmd = np.zeros((3, 30), np.int64)
    cmd[0, 2:5] = sp.M_DASH
    safe = np.array([True, True, False])
    dr = safe & ((cmd[:, :sp.NODASH_F] & sp.M_DASH) != 0).any(axis=1)
    J = np.array([5.0, 1.0, 9.0])
    nh = np.array([-2.0, 0.0, -3.0])                                    # v2_nh: minus the landed hits
    order = np.lexsort((-J, nh, dr.astype(np.int64), ~safe))
    assert list(order) == [1, 0, 2]


def test_nopogo_prefs(monkeypatch):
    # SSBOT_FORUM_SLAM_PLAY_NOPOGO: the idle / evading Clapper's iid in GoalPrefs.no_pogo; off or in a move: none
    monkeypatch.setattr(sp, "ENABLED", True)
    t = l2()
    p = t.decide(world(29.0, t=10.0, ents=[clapper(9, 35.0, False)]), WinFc([subj(9, CC, 35.0, y=7.45)]), None, 3)
    assert p.no_pogo == frozenset()
    monkeypatch.setattr(sp, "NOPOGO", True)
    p = t.decide(world(29.0, t=10.1, ents=[clapper(9, 35.0, False)]), WinFc([subj(9, CC, 35.0, y=7.45)]), None, 3)
    assert p.no_pogo == frozenset({9})
    p = t.decide(world(29.0, t=10.4, ents=[clapper(9, 35.0, False)]),
                 WinFc([subj(9, CC, 35.0, y=7.45, state="Slam Antic", family="CC_SLAM", committed=True)]), None, 3)
    assert p.no_pogo == frozenset()


def test_late_fall_abort(monkeypatch):
    # LATE: an airborne entry whose free fall lands after K_JUMP_LATE2 hands the slam back at once (a pogo bounce 4 u
    # above the floor rising at 17.4: ~39 frames); a hop (rising, the key released) is not judged by its vy
    s = state(1000, "Slam Antic", 0.05, cx=31.0, flip=False, hx=31.0 - 3.6, ground=False, vy=17.4)
    s["hero"]["pos"] = [27.4, sp.FLOOR_Y + 4.0]
    s["hero"]["anim"] = {"clip": "DownSpikeBounce 2"}
    assert sp._fall_frames(s) > 35
    s["hero"]["anim"] = {"clip": "Airborne"}
    assert sp._fall_frames(s) < 25
    monkeypatch.setattr(sp, "LATE", True)
    play = sp.SlamPlay(sp.PlayCfg())
    s["hero"]["anim"] = {"clip": "DownSpikeBounce 2"}
    play.step(1000, s, False, True)                     # the airborne entry (phase land) ...
    s2 = state(1001, "Slam Antic", 0.067, cx=31.0, flip=False, hx=31.0 - 3.6, ground=False, vy=17.4)
    s2["hero"]["pos"] = [27.4, sp.FLOOR_Y + 4.2]
    s2["hero"]["anim"] = {"clip": "DownSpikeBounce 2"}
    assert play.step(1001, s2, False, True) is None     # ... handed back on the next tick
    assert play.done and play.done[-1].why == "no landing (fall)"


def test_idle_family_cc_idle(monkeypatch):
    # the tracker's subject reads CC_IDLE while it idles: NODASH / NOPOGO apply there (NOPOGO also adds ground_hit)
    monkeypatch.setattr(sp, "ENABLED", True)
    monkeypatch.setattr(sp, "NODASH", True)
    monkeypatch.setattr(sp, "NOPOGO", True)
    t = l2()
    p = t.decide(world(29.0, t=10.0, ents=[clapper(9, 35.0, False)]),
                 WinFc([subj(9, CC, 35.0, y=7.45, state="Idle", family="CC_IDLE")]), None, 3)
    assert p.no_dash == frozenset({9}) and p.no_pogo == frozenset({9}) and 9 in p.ground_hit


def test_sp4_defaults_follow_v2():
    """SP4 A/B (forum.md 68.5): unset, the SP4 switches follow SSBOT_FORUM_V2; =0 turns each off; the JB subs only with
    JUMP_BEHIND."""
    import os
    import subprocess
    import sys

    def flags(env):
        e = {k: v for k, v in os.environ.items() if not k.startswith("SSBOT_FORUM_")}
        e.update(env)
        code = ("from ssbot.combat import slam_play as sp, jump_behind as jb; "
                "print(''.join(str(int(v)) for v in (sp.LATE, sp.AFTER, sp.NODASH, sp.NOPOGO, jb.PASS_HIT, jb.LAND_HIT, "
                "jb.NO_JUMP, jb.CAST_ANTIC, jb.WALL_PUSH)))")
        return subprocess.run([sys.executable, "-c", code], env=e, capture_output=True, text=True).stdout.strip()

    assert flags({}) == "000000000"
    assert flags({"SSBOT_FORUM_V2": "1"}) == "111111111"
    assert flags({"SSBOT_FORUM_V2": "1", "SSBOT_FORUM_SLAM_AFTER": "0", "SSBOT_FORUM_JB_WALL": "0"}) == "101111110"
    assert flags({"SSBOT_FORUM_V2": "1", "SSBOT_FORUM_JUMP_BEHIND": "0"}) == "111100000"
