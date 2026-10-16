"""The slam playbook (task 1v1 SP1, combat.slam_play; forum.md 65): the script's keys frame by frame against a toy slam
(the antic 48 frames, the hero walking 8.25 u/s and stopping dead, a mask for STATE f landing at f + 2), the walk into
the stand band from far and from close, the declines (behind, airborne, too far), no second look at a slam, the abort
on a hit, the Slam 0 rule, the default-off switch and the L2 stance sub-switch."""
import importlib

import pytest

from ssbot.combat import slam_play as sp
from ssbot.knowledge import kinematics as kin

GROUND_I = kin.cstate_names().index("onGround")
NW = (len(kin.cstate_names()) + 63) // 64
STAGES = (("Slam Antic", 48), ("Slam 0", 5), ("Slam 1", 3), ("Slam 2", 5), ("Slam Recover", 15))


def state(f, st, tin, cx=31.0, flip=False, hx=26.0, hp=9, ground=True, vx=0.0, iid=7, vy=0.0):
    cs = [0] * NW
    if ground:
        cs[GROUND_I >> 6] |= 1 << (GROUND_I & 63)
    return {"f": f, "hero": {"pos": [hx, 4.568], "box": [hx - 0.23, 3.015, hx + 0.23, 5.09], "vel": [vx, vy],
                             "health": hp, "cstate": cs, "hero_accepting_input": True},
            "ents": [{"type_key": sp.CLAPPER, "iid": iid, "hp": 200, "pos": [cx, 7.45], "flipX": flip,
                      "fsms": [{"name": "Control", "state": st, "t": tin}]}]}


def slam_state(k, antic=48):
    """The Control state and its time at antic frame k (Idle outside)."""
    if k < 0:
        return "Idle", 1.0
    lens = ((STAGES[0][0], antic),) + STAGES[1:]
    t = k
    for name, n in lens:
        if t < n:
            return name, t / 60.0
        t -= n
    return "Idle", t / 60.0


def simulate(x0, flip=False, antic=48, f0=1000, hurt_at=None, ground_until=None, cfg=None, start_k=-5, cx=31.0,
             bounce=True):
    """Run SlamPlay over a toy slam from antic frame start_k; x0 = the hero's distance in front (centre to centre); the
    bounce: vy 17 from the press + 4 for 15 frames. Returns (play, {landing frame k: mask}, hero x per k (in front, u))."""
    play = sp.SlamPlay(cfg or sp.PlayCfg())
    face = 1 if flip else -1
    press = None
    hx = cx + face * x0
    pending = {}
    landed = {}
    xs = {}
    air_from = None
    for k in range(start_k, 120):
        f = f0 + k
        m = pending.pop(f, None)
        if m is not None:
            landed[k] = m
            lr = (1 if m & sp.M_R else 0) - (1 if m & sp.M_L else 0)
            if m & sp.M_J and air_from is None:
                air_from = k
            if m & sp.M_A and press is None:
                press = k
            if air_from is None:
                hx += lr * sp.WALK_U
        ground = air_from is None or k > air_from + 60
        if ground_until is not None and k <= ground_until:
            ground = False
        xs[k] = (hx - cx) * face
        st, tin = slam_state(k, antic)
        hp = 9 if hurt_at is None or k < hurt_at else 7
        vy = 17.0 if bounce and press is not None and press + 4 <= k < press + 19 else 0.0
        out = play.step(f, state(f, st, tin, cx=cx, flip=flip, hx=hx, hp=hp, ground=ground, vy=vy), ground)
        if out is not None:
            pending[f + 2] = out
    return play, landed, xs


def keys(landed, bit):
    return sorted(k for k, m in landed.items() if m & bit)


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("SSBOT_FORUM_SLAM_PLAY", raising=False)
    monkeypatch.delenv("SSBOT_FORUM_SLAM_PLAY_STANCE", raising=False)
    m = importlib.reload(sp)
    try:
        assert m.ENABLED is False and m.STANCE_U == 0.0
        monkeypatch.setenv("SSBOT_FORUM_SLAM_PLAY", "1")
        monkeypatch.setenv("SSBOT_FORUM_SLAM_PLAY_STANCE", "6")
        m = importlib.reload(sp)
        assert m.ENABLED is True and m.STANCE_U == 6.0
    finally:
        monkeypatch.delenv("SSBOT_FORUM_SLAM_PLAY", raising=False)
        monkeypatch.delenv("SSBOT_FORUM_SLAM_PLAY_STANCE", raising=False)
        importlib.reload(sp)


@pytest.mark.parametrize("flip", [False, True])
def test_the_script_at_5u(flip):
    play, landed, xs = simulate(5.0, flip=flip)
    c = play.cfg
    # no direction key before the way out (the hero is inside the stand band), the jump held HOLD frames from K_JUMP
    s0 = 48
    out = keys(landed, sp.M_L | sp.M_R)
    behind = sp.M_L if flip else sp.M_R                    # the way out goes over its body to its back (-face)
    assert out and min(out) == s0 + c.over_s0 and all(landed[k] & behind for k in out)
    assert keys(landed, sp.M_DASH) == [s0 + c.dash_s0, s0 + c.dash_s0 + 1]
    assert keys(landed, sp.M_J) == list(range(c.k_jump, c.k_jump + c.hold))
    assert keys(landed, sp.M_A) == [c.k_press]
    assert keys(landed, sp.M_D) == list(range(c.k_down, c.k_press + c.down_after + 1))
    assert not [k for k in keys(landed, sp.M_J) if k > c.k_press]          # no jump in the air after the press
    assert play.run is None and play.done[-1].phase == "done" and play.done[-1].x_jump == pytest.approx(5.0)
    assert play.stats()["pressed"] == 1 and play.stats()["dashed"] == 1


def test_the_way_out():
    # the wall 4 u behind its centre (facing left: behind = +x): out in front instead; no bounce: abort at once
    play, landed, _ = simulate(5.0, cx=sp.WALL_R - 4.0)
    out = keys(landed, sp.M_L | sp.M_R)
    assert out and all(landed[k] & sp.M_L for k in out if k > 48)
    play, landed, _ = simulate(5.0, bounce=False)
    assert play.done[-1].why == "no bounce" and not keys(landed, sp.M_DASH)
    # over = 0 (SP1 it1): no key after the press
    play, landed, _ = simulate(5.0, cfg=sp.PlayCfg(over=0))
    assert not keys(landed, sp.M_L | sp.M_R) and not keys(landed, sp.M_DASH)


@pytest.mark.parametrize("flip", [False, True])
def test_walks_in_from_far(flip):
    play, landed, xs = simulate(7.6, flip=flip)
    c = play.cfg
    toward = sp.M_R if not flip else sp.M_L                 # facing left (flip False): the hero is at -x, toward = +x
    walk = [k for k in keys(landed, sp.M_L | sp.M_R) if k < c.k_jump]
    assert walk and all(landed[k] & toward for k in walk)
    assert c.stand[0] <= xs[c.k_jump] <= c.stand[1]
    assert keys(landed, sp.M_A) == [c.k_press]


def test_walks_out_from_close():
    play, landed, xs = simulate(3.3)
    c = play.cfg
    walk = [k for k in keys(landed, sp.M_L | sp.M_R) if k < c.k_jump]
    assert walk and all(landed[k] & sp.M_L for k in walk)  # facing left, the hero at -x: away = -x
    assert c.stand[0] <= xs[c.k_jump] <= c.stand[1]
    assert keys(landed, sp.M_A) == [c.k_press]


def test_declines():
    # behind it, too far: the planner decides (no key ever), one look per slam
    for kw in ({"x0": -5.0}, {"x0": 10.5}):
        play, landed, _ = simulate(**kw)
        assert not landed, kw
        assert len(play.done) == 1 and play.done[0].k_start is None
    # in the air past the start: air = 0 never takes it; air = 1 holds no key in the air (in STAND) and gives it
    # back at K_JUMP - 4 without a landing
    play, landed, _ = simulate(5.0, ground_until=30, cfg=sp.PlayCfg(air=0))
    assert not landed and play.done[0].why == "in the air"
    play, landed, _ = simulate(5.0, ground_until=30)
    assert landed and not any(landed.values()) and play.done[0].why == "no landing"
    # down at frame 25 inside the jump band (seen at 25, the key lands at 27): the jump at once, the press 20 later
    play, landed, _ = simulate(5.0, ground_until=24)
    c = play.cfg
    j = keys(landed, sp.M_J)
    assert j and c.k_jump < j[0] <= c.k_jump_late and keys(landed, sp.M_A) == [min(j[0] + c.press_after, c.k_press_max)]
    # airborne at the sighting but down by frame 8: it starts late and still walks / jumps in time
    play, landed, _ = simulate(6.5, ground_until=6)
    assert keys(landed, sp.M_A) == [play.cfg.k_press]


def test_air_entry():
    # in the air 8 u in front until antic frame 12: steered toward STAND in the air, the strike on time
    play, landed, xs = simulate(8.0, ground_until=12)
    c = play.cfg
    early = [k for k in keys(landed, sp.M_L | sp.M_R) if k <= 12]
    assert early and all(landed[k] & sp.M_R for k in early)       # facing left: toward = +x
    assert c.stand[0] <= xs[c.k_jump] <= c.stand[1]
    assert keys(landed, sp.M_A) == [c.k_press] and play.stats()["air_entry"] == 1
    assert not keys(landed, sp.M_J)[0] < c.k_jump                  # never a jump before the script's own


def test_abort_on_a_hit():
    play, landed, _ = simulate(5.0, hurt_at=30)
    assert play.done[-1].phase == "abort" and play.done[-1].why == "hurt"
    assert not keys(landed, sp.M_A) and max(landed) < 32


def test_slam0_rule():
    # Slam 0 seen before the press: the press goes out at once (its frame Slam 0 + 2 here, not the planned 52)
    cfg = sp.PlayCfg(k_press=52, k_down=48, k_press_max=60)
    play, landed, _ = simulate(5.0, antic=47, cfg=cfg)
    assert keys(landed, sp.M_A) == [47 + 2]
    # a script whose press would come past Slam 0 + press_late_max: abort, no press into the hammer
    cfg = sp.PlayCfg(k_press=60, k_down=55, k_press_max=60)
    play, landed, _ = simulate(5.0, antic=47, cfg=cfg)
    assert not keys(landed, sp.M_A)
    assert play.done[-1].why == "press window missed"


def test_cfg_from_env(monkeypatch):
    monkeypatch.setenv("SSBOT_FORUM_SLAM_PLAY_SET", "k_jump=27,hold=15,stand=4.8:5.4")
    c = sp.PlayCfg.from_env()
    assert (c.k_jump, c.hold, c.stand) == (27, 15, (4.8, 5.4))


def test_stance_sub_switch(monkeypatch):
    from tests.test_forum_l2 import WinFc, clapper, l2, subj, world
    s = [subj(9, "Song Heavy Sentry", 30.0, y=7.45)]
    monkeypatch.setattr(sp, "STANCE_U", 0.0)
    p = l2().decide(world(24.0, ents=[clapper(9, 30.0, False)]), WinFc(s), None, 3)
    assert p.stance_x == pytest.approx(26.0)                       # rn: the face, 4 u
    monkeypatch.setattr(sp, "STANCE_U", 6.0)
    t = l2()
    p = t.decide(world(24.0, ents=[clapper(9, 30.0, False)]), WinFc(s), None, 3)
    assert p.stance_x == pytest.approx(24.0) and t.last.get("goal_why", "").endswith("slam stance")
    # a slam: the stance rule leaves it (rn's slam branch)
    s = [subj(9, "Song Heavy Sentry", 30.0, y=7.45, state="Slam Antic", family="CC_SLAM", committed=True)]
    p = l2().decide(world(24.0, ents=[clapper(9, 30.0, False)]), WinFc(s), None, 3)
    assert p.stance_x != pytest.approx(24.0)


@pytest.mark.parametrize("x0,d", [(5.0, 4.5), (7.7, 6.0), (5.0, 6.5)])
def test_no_back_and_forth(x0, d):
    # a stand band only 0.24 wide (the probe's --pin): one walk direction, the hero inside it at the jump
    cfg = sp.PlayCfg(stand=(d - 0.12, d + 0.12), band=(3.5, 7.5))
    play, landed, xs = simulate(x0, cfg=cfg)
    walk = [k for k in keys(landed, sp.M_L | sp.M_R) if k < cfg.k_jump]
    assert walk and len({landed[k] & (sp.M_L | sp.M_R) for k in walk}) == 1
    assert d - 0.12 <= xs[cfg.k_jump] <= d + 0.12


def simulate_freeze(x0, freeze_g, n_frozen, clock=True, f0=1000, antic=48):
    """SP2: a hit stop of n_frozen STATE frames when the game reaches antic frame freeze_g: the STATE frames run on,
    the game (the Clapper's state time, the hero, the keys) stands still; the game takes the keys of the STATE frame
    in which it moves into a new game frame. clock: the game clock passed to the playbook (the policy's
    Stamp.t_game_s), else the STATE frame count of SP1. Returns {game frame: the mask it took}."""
    play = sp.SlamPlay(sp.PlayCfg())
    face = -1
    cx = 31.0
    hx = cx + face * x0
    pending, landed = {}, {}
    g, frozen, press, air_from = -5, 0, None, None
    for i in range(400):
        f = f0 + i
        m = pending.pop(f, None)
        if i > 0:
            if g == freeze_g and frozen < n_frozen:
                frozen += 1                                   # the freeze: the game does not move
            else:
                g += 1
                if m is not None:
                    landed[g] = m
                    lr = (1 if m & sp.M_R else 0) - (1 if m & sp.M_L else 0)
                    if m & sp.M_J and air_from is None:
                        air_from = g
                    if m & sp.M_A and press is None:
                        press = g
                    if air_from is None:
                        hx += lr * sp.WALK_U
        if g >= 120:
            break
        ground = air_from is None or g > air_from + 60
        st, tin = slam_state(g, antic)
        vy = 17.0 if press is not None and press + 4 <= g < press + 19 else 0.0
        out = play.step(f, state(f, st, tin, cx=cx, hx=hx, ground=ground, vy=vy), ground,
                        t_game=(g / 60.0 if clock else None))
        if out is not None:
            pending[f + 2] = out
    return play, landed


@pytest.mark.parametrize("freeze_g", [3, 20, 44])
def test_a_hit_stop_in_the_antic(freeze_g):
    # SP2 live (forum.md 66): a hit across the Clapper's 80 HP froze the game 12 frames at antic +1; the frame count
    # moved the jump and the press 12 game frames ahead (the press at Slam 0 - 15: no bounce, Slam 1's body hit).
    # On the game clock the keys land on the same game frames as without the freeze.
    c = sp.PlayCfg()
    _, ref = simulate_freeze(5.0, -99, 0)
    _, got = simulate_freeze(5.0, freeze_g, 12)
    assert keys(got, sp.M_J) == keys(ref, sp.M_J) == list(range(c.k_jump, c.k_jump + c.hold))
    assert keys(got, sp.M_A) == keys(ref, sp.M_A) == [c.k_press]
    assert keys(got, sp.M_DASH) == keys(ref, sp.M_DASH) == [48 + c.dash_s0, 48 + c.dash_s0 + 1]
    if freeze_g < c.k_jump:
        _, old = simulate_freeze(5.0, freeze_g, 12, clock=False)
        assert keys(old, sp.M_A) and keys(old, sp.M_A)[0] < c.k_press - 8      # the SP1 frame count: far too early


def test_game_clock_switch(monkeypatch):
    monkeypatch.setenv("SSBOT_FORUM_SLAM_PLAY_CLOCK", "0")
    try:
        assert importlib.reload(sp).GAME_CLOCK is False
        monkeypatch.delenv("SSBOT_FORUM_SLAM_PLAY_CLOCK")
        assert importlib.reload(sp).GAME_CLOCK is True
    finally:
        monkeypatch.delenv("SSBOT_FORUM_SLAM_PLAY_CLOCK", raising=False)
        importlib.reload(sp)
