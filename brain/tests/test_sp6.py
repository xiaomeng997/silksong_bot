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
    """The attack's rising edges (the early press is held two frames: one attack)."""
    return sorted(k for k, m in landed.items() if m & sp.M_A and not landed.get(k - 1, 0) & sp.M_A)


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
    away = sp.M_L if toward == sp.M_R else sp.M_R
    # the key toward it the frame before and on both press frames; nothing away from it within 3 frames of a press
    assert all(landed[k] & toward and landed[k - 1] & toward and landed[k + 1] & toward and landed[k + 1] & sp.M_A
               for k in pr)
    assert not any(landed.get(j, 0) & away for k in pr for j in range(k - 3, k + 4))
    assert hits == pr
    assert landed.get(26, 0) & sp.M_J
    assert play.cfg.band[0] <= xs[26] <= play.cfg.band[1]
    r = play.run or play.done[-1]
    assert r.k_early == pr


def test_walks_into_reach_from_far(monkeypatch):
    # 6.5 u at the entry: walk into EARLY_STAND, one press before early_late_k (the second would come after
    # early_k_max), the jump at 26 inside the band; 7.5 u: in reach only after early_late_k, from farther than
    # early_late_u (its recoil would run on into the jump): no early press
    play, landed, xs, hits = run(6.5, monkeypatch=monkeypatch)
    pr = [k for k in presses(landed) if k < 26]
    assert len(pr) == 1 and pr[0] < play.cfg.early_late_k and xs[pr[0] - 1] <= 5.37
    assert landed.get(26, 0) & sp.M_J and play.cfg.band[0] <= xs[26] <= play.cfg.band[1]
    play, landed, xs, hits = run(7.5, monkeypatch=monkeypatch)
    assert [k for k in presses(landed) if k < 26] == [] and landed.get(26, 0) & sp.M_J


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


@pytest.mark.parametrize("early,x_rel,want", [(False, 2.0, "behind"), (True, 2.0, "front"), (True, 1.7, "behind"),
                                              (False, 2.3, "front")])
def test_near_clearance_under_early(early, x_rel, want, monkeypatch):
    # NEAR's behind clearance at Slam 0 + 10: SP5's NEAR_V (0.165 u / frame, past 2.8 u) when EARLY is off; under EARLY
    # the measured 0.138 u / frame and 2.3 u (x at Slam 0 + 10 <= 1.84 u in front)
    monkeypatch.setattr(sp, "EARLY", early)
    monkeypatch.setattr(sp, "SIDE", True)
    play = sp.SlamPlay(sp.PlayCfg(side_force=-1))
    cx, face = 31.0, -1
    r = sp.Run(iid=7, fa=900, face=face, ks0=40, k_press=38, bounced=True)
    play.run = r
    s = state(1000, "Slam 1", 0.1, cx=cx, flip=False, hx=cx + face * x_rel, ground=False)
    play._near(r, 50, 1000, s, s["ents"][0], cx)
    assert ("behind" if r.near == -face else "front") == want


@pytest.mark.parametrize("x0", [4.25, 4.0, 3.7])
def test_late_window_never_walks_in(x0, monkeypatch):
    # the A/B's abc block (74174bd): a planner slash just before the antic pushed the first press past early_late_k; the
    # key toward it before a press that stayed out of the late window walked her from 4.25 to 3.3-3.4 u (no strike,
    # the hammer). Now: never nearer than the window's low edge from a walk toward it, the jump at 26 inside BAND
    play, landed, xs, hits = run(x0, cd0=0.3, start_k=0, monkeypatch=monkeypatch)
    lo = min(x0, play.cfg.early_late_lo) - 0.01
    assert min(xs[k] for k in range(2, 26)) >= lo - sp.WALK_U
    assert landed.get(26, 0) & sp.M_J
    assert all(xs[k] >= play.cfg.early_late_lo - 0.3 for k in [k for k in presses(landed) if k < 26])
