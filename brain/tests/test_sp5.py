"""Task 1v1 SP5 (forum.md 69): the slam playbook's way out after the bounce - the side by the person's rule
(SSBOT_FORUM_SLAM_PLAY_SIDE: one Clapper, between it and the nearer wall; two, between them) and the closer landing with
a side slash before it (SSBOT_FORUM_SLAM_PLAY_NEAR). Both off by default (SP1's way out unchanged); on, the documented
keys against a toy slam with the bounce's air motion (the probes' numbers: apex Slam 0 + 23, the landing ~+52)."""
import importlib

import pytest

from ssbot.combat import slam_play as sp
from tests.test_slam_play import keys, slam_state, state

A0 = 48                     # the toy antic's length: Slam 0 at antic frame 48


def run(x0=5.0, cx=31.0, flip=False, near=True, side=True, cfg=None, others=(), monkeypatch=None):
    """The playbook over a toy slam: the hero x0 in front on the ground, the jump at the script's frame, the press at
    y 4.4 above the standing y, the bounce at the press + 6 (vy 17.4 four frames, then -1.2 per frame: the apex ~Slam 0 + 24), the air key
    moving her NEAR_V per frame, the dash 0.5 u per frame for 10 frames, the Clapper lunging 3.6 u toward her over Slam
    0 / 1. Returns (play, {landing frame k: mask}, {k: (hero x rel. its centre, + in front; y)}, the Clapper's x)."""
    monkeypatch.setattr(sp, "NEAR", near)
    monkeypatch.setattr(sp, "SIDE", side)
    play = sp.SlamPlay(cfg or sp.PlayCfg())
    face = 1 if flip else -1
    hx = cx + face * x0
    y, vy = 0.0, 0.0
    air = False
    press = None
    dash_left = 0
    pending, landed, xs = {}, {}, {}
    for k in range(-5, 130):
        f = 1000 + k
        m = pending.pop(f, None)
        if m is not None:
            landed[k] = m
        m = m or 0
        lr = (1 if m & sp.M_R else 0) - (1 if m & sp.M_L else 0)
        if m & sp.M_J and not air and press is None:
            air, y, vy = True, 0.5, 0.0
        if m & sp.M_A and press is None and air:
            press = k
        if m & sp.M_DASH and air and dash_left == 0:
            dash_left = 10
        if not air:
            hx += lr * sp.WALK_U
        else:
            hx += lr * sp.NEAR_V + (0.5 * lr if dash_left else 0.0)
            dash_left = max(0, dash_left - 1)
            if press is None:
                y = 4.4
            elif k == press + 6:
                vy = 17.4
            elif k > press + 9:
                vy -= 1.2
            if press is not None:
                y += vy / 60.0
                if k > press + 10 and y <= 0.0:
                    air, y, vy = False, 0.0, 0.0
        if A0 <= k < A0 + 8:
            cx += face * 0.45                              # the lunge (Slam 0 / 1)
        xs[k] = ((hx - cx) * face, y)
        st, tin = slam_state(k, A0)
        s = state(f, st, tin, cx=cx, flip=flip, hx=hx, ground=not air, vy=vy if air else 0.0)
        s["hero"]["pos"][1] = sp.FLOOR_Y + y
        for i, ox in enumerate(others):
            s["ents"].append({"type_key": sp.CLAPPER, "iid": 100 + i, "hp": 200, "pos": [ox, 7.45], "flipX": False,
                              "fsms": [{"name": "Control", "state": "Idle", "t": 1.0}]})
        out = play.step(f, s, not air)
        if out is not None:
            pending[f + 2] = out
    return play, landed, xs, cx


def landing(xs, after):
    return next((k, x) for k, (x, y) in sorted(xs.items()) if k > after and y == 0.0)


def test_switches_off_by_default(monkeypatch):
    for n in ("SSBOT_FORUM_SLAM_PLAY_SIDE", "SSBOT_FORUM_SLAM_PLAY_NEAR"):
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setenv("SSBOT_FORUM_V2", "1")
    try:
        m = importlib.reload(sp)
        assert m.SIDE is False and m.NEAR is False
        monkeypatch.setenv("SSBOT_FORUM_SLAM_PLAY_SIDE", "1")
        monkeypatch.setenv("SSBOT_FORUM_SLAM_PLAY_NEAR", "1")
        m = importlib.reload(sp)
        assert m.SIDE is True and m.NEAR is True
    finally:
        for n in ("SSBOT_FORUM_SLAM_PLAY_SIDE", "SSBOT_FORUM_SLAM_PLAY_NEAR", "SSBOT_FORUM_V2"):
            monkeypatch.delenv(n, raising=False)
        importlib.reload(sp)


@pytest.mark.parametrize("flip", [False, True])
def test_off_is_sp1(monkeypatch, flip):
    # both off: the dash way out over its body exactly as before (the key from Slam 0 + 20, the dash at + 23)
    play, landed, xs, _ = run(flip=flip, near=False, side=False, monkeypatch=monkeypatch)
    c = play.cfg
    out = keys(landed, sp.M_L | sp.M_R)
    behind = sp.M_L if flip else sp.M_R
    assert out and min(out) == A0 + c.over_s0 and all(landed[k] & behind for k in out)
    assert keys(landed, sp.M_DASH) == [A0 + c.dash_s0, A0 + c.dash_s0 + 1]
    assert keys(landed, sp.M_A) == [c.k_press]


@pytest.mark.parametrize("flip", [False, True])
def test_near_behind(monkeypatch, flip):
    # NEAR alone: behind (SP1's side), no dash, the key over its body from Slam 0 + 8, the turn, one side slash after
    # the cooldown while low, the landing ~3.7 u behind its centre
    play, landed, xs, _ = run(flip=flip, near=True, side=False, monkeypatch=monkeypatch)
    c = play.cfg
    r = play.done[-1]
    assert r.near == -r.face and r.side_why == "behind" and not keys(landed, sp.M_DASH)
    over = sp.M_L if flip else sp.M_R
    toward = sp.M_R if flip else sp.M_L
    mv = keys(landed, over)
    assert mv and min(mv) == A0 + c.near_s0_behind
    assert keys(landed, toward) == [r.k_turn] and r.k_turn > max(mv)
    sl = [k for k in keys(landed, sp.M_A) if k > c.k_press]
    assert sl == [r.k_slash] and r.k_slash > r.k_turn and r.k_slash >= c.k_press + c.slash_cd
    assert xs[r.k_slash + 1][1] <= c.slash_y + 0.3                # low enough: the slash meets its body
    kl, xl = landing(xs, c.k_press + 8)
    assert r.k_slash < kl and xl == pytest.approx(-c.near_u_behind, abs=0.2)
    # passed its back (the turned front + her half width + 0.3) while still high
    k_cross = next(k for k in sorted(xs) if k > c.k_press and xs[k][0] <= -c.near_cross_u)
    assert k_cross <= A0 + c.near_cross_s0 and xs[k_cross][1] > 4.0
    st = play.stats()
    assert st["side_behind"] == 1 and st["near_slash"] == 1


def test_side_rule_one_clapper(monkeypatch):
    # facing right (the hero to its right): the left wall nearer -> behind it (between it and that wall)
    play, landed, xs, cx = run(cx=22.0, flip=True, monkeypatch=monkeypatch)
    r = play.done[-1]
    assert r.near == -1 and r.side_why == "wall"
    kl, xl = landing(xs, play.cfg.k_press + 8)
    assert xl == pytest.approx(-3.7, abs=0.2)
    # the right wall nearer (in front, behind the hero) -> keep side: land 3.7 u in front, the slash facing it
    play, landed, xs, cx = run(cx=40.0, flip=True, monkeypatch=monkeypatch)
    r = play.done[-1]
    c = play.cfg
    assert r.near == 1 and r.side_why == "wall"
    away = keys(landed, sp.M_R)
    assert away and min(away) == A0 + c.near_s0_front
    assert keys(landed, sp.M_L) == [r.k_turn]
    kl, xl = landing(xs, c.k_press + 8)
    assert xl == pytest.approx(c.near_u_front, abs=0.2) and r.k_slash is not None and r.k_slash < kl
    assert play.stats()["side_front"] == 1


def test_side_rule_two_clappers(monkeypatch):
    # the nearer wall is behind it (left), but the other Clapper stands to the right: end between them (in front)
    play, _, xs, _ = run(cx=22.0, flip=True, others=(36.0,), monkeypatch=monkeypatch)
    r = play.done[-1]
    assert r.near == 1 and r.side_why == "two"
    # the other one to the left: behind it
    play, _, xs, _ = run(cx=34.0, flip=True, others=(20.0,), monkeypatch=monkeypatch)
    r = play.done[-1]
    assert r.near == -1 and r.side_why == "two"


def test_room_and_clearance(monkeypatch):
    # its back 3.9 u from the left wall after the lunge: behind still fits, nearer (room - pad)
    play, _, xs, cx = run(cx=sp.WALL_L + 3.9 + 3.6, flip=False, x0=5.0, monkeypatch=monkeypatch)
    # (facing left: behind = right; the right wall is far, the left wall nearer = in front -> keep side)
    assert play.done[-1].near == -1
    play, _, xs, cx = run(cx=sp.WALL_L + 3.9 - 3.6, flip=True, x0=5.0, monkeypatch=monkeypatch)
    r = play.done[-1]
    assert r.near == -1 and r.near_u == pytest.approx(3.9 - play.cfg.wall_pad, abs=0.01) and r.side_why == "wall"
    # 3.5 u of room behind: no spot behind -> in front ("room")
    play, _, xs, cx = run(cx=sp.WALL_L + 3.5 - 3.6, flip=True, x0=5.0, monkeypatch=monkeypatch)
    r = play.done[-1]
    assert r.near == 1 and r.side_why == "room"
    # she is still 5.5 u in front at Slam 0 + 8 (no lunge reached her): behind cannot clear its back -> in front
    cfg = sp.PlayCfg(stand=(7.0, 7.2), band=(4.0, 7.5))
    play, _, xs, cx = run(cx=22.0, flip=True, x0=7.1, cfg=cfg, monkeypatch=monkeypatch)
    r = play.done[-1]
    assert r.near == 1 and r.side_why == "clear"


def test_force_and_side_with_the_dash(monkeypatch):
    play, _, _, _ = run(cx=22.0, flip=True, cfg=sp.PlayCfg(side_force=1), monkeypatch=monkeypatch)
    assert play.done[-1].near == 1 and play.done[-1].side_why == "force"
    play, _, _, _ = run(cx=40.0, flip=True, cfg=sp.PlayCfg(side_force=-1), monkeypatch=monkeypatch)
    assert play.done[-1].near == -1
    # SIDE with SP1's dash way out (NEAR off): the right wall nearer -> the dash away from it (in front)
    play, landed, _, _ = run(cx=36.0, flip=True, near=False, side=True, monkeypatch=monkeypatch)
    r = play.done[-1]
    assert r.over_dir == 1 and r.side_why == "wall" and keys(landed, sp.M_DASH)
    assert not keys(landed, sp.M_L)
