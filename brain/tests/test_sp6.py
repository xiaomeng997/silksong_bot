"""Task 1v1 SP6 (forum.md 70): side slashes on the ground in the early slam antic before the playbook's strike
(SSBOT_FORUM_SLAM_PLAY_EARLY, default off). A toy antic: the Clapper still except the knock-back of a landed slash (0.48 u
away from her), her recoil 0.5 u over 8 frames, the walk WALK_U per frame; the attack cooldown 18 frames (the STATE's
tm.atk_cd)."""
import importlib

import pytest

from ssbot.combat import slam_play as sp
from tests.test_slam_play import slam_state, state

A0 = 48


def run(x0, early=True, cx=31.0, flip=False, cfg=None, monkeypatch=None, cd0=0.0, air_until=None, start_k=-3):
    monkeypatch.setattr(sp, "EARLY", early)
    play = sp.SlamPlay(cfg or sp.PlayCfg())
    face = 1 if flip else -1
    hx = cx + face * x0
    pending, landed, xs = {}, {}, {}
    cd = cd0 * 60.0                                       # frames of attack cooldown left
    recoil = 0
    hits = []
    for k in range(start_k, 40):
        f = 1000 + k
        m = pending.pop(f, None)
        if m is not None:
            landed[k] = m
        m = m or 0
        lr = (1 if m & sp.M_R else 0) - (1 if m & sp.M_L else 0)
        if m & sp.M_A and not (landed.get(k - 1, 0) & sp.M_A) and cd <= 0:
            cd = 18
            # the slash meets its body (front edge 2.25 u) from up to 5.37 u
            if 0 < (hx - cx) * face <= 2.25 + 3.12:
                hits.append(k)
                cx -= face * 0.48
                recoil = 8
        hx += lr * sp.WALK_U
        if recoil:
            hx += face * 0.5 / 8
            recoil -= 1
        cd = max(0.0, cd - 1)
        xs[k] = (hx - cx) * face
        st, tin = slam_state(k, A0)
        air = air_until is not None and k < air_until
        s = state(f, st, tin, cx=cx, flip=flip, hx=hx, ground=not air)
        s["hero"]["tm"] = {"atk_cd": cd / 60.0}
        out = play.step(f, s, not air)
        if out is not None:
            pending[f + 2] = out
    return play, landed, xs, hits


def presses(landed):
    return sorted(k for k, m in landed.items() if m & sp.M_A)


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("SSBOT_FORUM_SLAM_PLAY_EARLY", raising=False)
    try:
        assert importlib.reload(sp).EARLY is False
        monkeypatch.setenv("SSBOT_FORUM_V2", "1")
        assert importlib.reload(sp).EARLY is False      # not part of the v2 defaults until its A/B
        monkeypatch.setenv("SSBOT_FORUM_SLAM_PLAY_EARLY", "1")
        assert importlib.reload(sp).EARLY is True
    finally:
        monkeypatch.delenv("SSBOT_FORUM_SLAM_PLAY_EARLY", raising=False)
        monkeypatch.delenv("SSBOT_FORUM_V2", raising=False)
        importlib.reload(sp)


@pytest.mark.parametrize("x0", [3.4, 4.5, 5.2, 6.0, 7.5])
def test_off_is_the_playbook(x0, monkeypatch):
    # EARLY off: no attack before the jump, the walk / jump as before
    _, landed, xs, hits = run(x0, early=False, monkeypatch=monkeypatch)
    assert [k for k in presses(landed) if k < 26] == [] and hits == []
    assert landed.get(26, 0) & sp.M_J


@pytest.mark.parametrize("flip", [False, True])
def test_two_early_slashes_from_reach(flip, monkeypatch):
    # in reach at the antic entry, the attack ready: a press one frame after the script's first mask, the second one
    # cooldown frames later, each with the key toward it; then the walk into STAND and the jump at 26 inside the band
    play, landed, xs, hits = run(4.4, flip=flip, monkeypatch=monkeypatch)
    pr = [k for k in presses(landed) if k < 26]
    assert len(pr) == 2 and pr[1] - pr[0] == play.cfg.early_cd and pr[1] <= play.cfg.early_k_max
    toward = sp.M_R if flip is False else sp.M_L      # face -1 (flip False): she is left of it, it is to her right
    assert all(landed[k] & toward for k in pr)
    assert hits == pr
    assert landed.get(26, 0) & sp.M_J
    assert play.cfg.band[0] <= xs[26] <= play.cfg.band[1]
    r = play.run or play.done[-1]
    assert r.k_early == pr


def test_walks_into_reach_from_far(monkeypatch):
    # 7.5 u at the entry: walk into EARLY_STAND, one press (the second would come after early_k_max), the jump at 26
    play, landed, xs, hits = run(7.5, monkeypatch=monkeypatch)
    pr = [k for k in presses(landed) if k < 26]
    assert len(pr) == 1 and xs[pr[0] - 1] <= 5.37
    assert landed.get(26, 0) & sp.M_J and play.cfg.band[0] <= xs[26] <= play.cfg.band[1]


def test_cooldown_from_the_state(monkeypatch):
    # a planner slash just before the antic: the first early press waits for the STATE's atk_cd
    _, landed, _, _ = run(4.4, cd0=0.2, start_k=0, monkeypatch=monkeypatch)
    pr = [k for k in presses(landed) if k < 26]
    assert pr and pr[0] >= 12


def test_no_press_in_the_air(monkeypatch):
    # airborne (the land phase) and the frames before landing: no attack
    _, landed, _, _ = run(5.0, air_until=12, start_k=0, monkeypatch=monkeypatch)
    pr = [k for k in presses(landed) if k < 26]
    assert all(k >= 14 for k in pr)


def test_no_press_after_early_k_max(monkeypatch):
    cfg = sp.PlayCfg(early_k_max=8)
    _, landed, _, _ = run(4.4, cfg=cfg, monkeypatch=monkeypatch)
    pr = [k for k in presses(landed) if k < 26]
    assert len(pr) == 1 and pr[0] <= 8


def test_stats(monkeypatch):
    play, _, _, _ = run(4.4, monkeypatch=monkeypatch)
    st = play.stats()
    assert st["early_runs"] == 1 and st["early_press"] == 2
