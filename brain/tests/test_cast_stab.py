"""Task 1v1 SP6 (forum.md 70): the Wanderer dash slash in the jump cast's antic (SSBOT_FORUM_JB_DASH_SLASH, default off;
ssbot.combat.cast_stab): the stab model and the script's keys against a toy antic."""
import importlib

import pytest

from ssbot.combat import cast_stab as cs
from ssbot.combat import slam_play as sp
from tests.test_slam_play import state


def test_off_by_default(monkeypatch):
    # off without v2; since the SP8a A/B it follows SSBOT_FORUM_V2 (=0 off, with STOP=0 too: nothing runs)
    # (since the lead's note of 2026-10-17 JB_SLAM_DASH / JB_CORNER follow v2 too: =0 here)
    for k in ("SSBOT_FORUM_JB_DASH_SLASH", "SSBOT_FORUM_JB_DASH_STOP", "SSBOT_FORUM_V2"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SSBOT_FORUM_JB_SLAM_DASH", "0")
    monkeypatch.setenv("SSBOT_FORUM_JB_CORNER", "0")
    importlib.reload(cs._jb)
    try:
        assert importlib.reload(cs).ENABLED is False
        monkeypatch.setenv("SSBOT_FORUM_V2", "1")
        assert importlib.reload(cs).ENABLED is True
        monkeypatch.setenv("SSBOT_FORUM_JB_DASH_SLASH", "0")
        monkeypatch.setenv("SSBOT_FORUM_JB_DASH_STOP", "0")
        assert importlib.reload(cs).ENABLED is False
        monkeypatch.setenv("SSBOT_FORUM_JB_DASH_SLASH", "1")
        assert importlib.reload(cs).ENABLED is True
    finally:
        for k in ("SSBOT_FORUM_JB_DASH_SLASH", "SSBOT_FORUM_JB_DASH_STOP", "SSBOT_FORUM_V2", "SSBOT_FORUM_JB_SLAM_DASH",
                  "SSBOT_FORUM_JB_CORNER"):
            monkeypatch.delenv(k, raising=False)
        importlib.reload(cs._jb)
        importlib.reload(cs)


def test_stab_path():
    # the dash 2.8 u, the stab's collider from its 7th frame: from 9.2 u the hit on the window's first frame, 3.0 u
    # from its centre (her box front 0.5 u outside its body front), the recoil ~3.2 u back and ~2.1 u up
    # (SP8: she lunges on 2 frames after the hit, and the hit may register a frame late: xmin 3 sprint frames short)
    p = cs.stab_path(9.2)
    assert p["hit"] == cs.STAB_START + cs.STAB_ON
    x_hit = next(x for j, x, y in p["path"] if j == p["hit"])
    assert 2.8 < x_hit < 3.2 and 2.0 < p["top"] < 2.3
    assert p["xmin"] == pytest.approx(x_hit - (cs.HIT_WAIT + cs.HIT_LAG) * cs.STAB_V / 60.0)
    assert p["path"][-1][1] - (x_hit - cs.HIT_WAIT * cs.STAB_V / 60.0) == pytest.approx(3.2, abs=0.2)
    assert p["path"][-1][2] == 0.0
    # nearer: deeper into its body at the window's first frame; far: the hit later, at the tip's reach
    assert cs.stab_path(8.0)["xmin"] < cs.BODY_FRONT + cs.HALF_W + 0.25
    far = cs.stab_path(12.0)
    x_far = next(x for j, x, y in far["path"] if j == far["hit"])
    assert far["hit"] > p["hit"] and x_far == pytest.approx(cs.BODY_FRONT + cs.STAB_REACH, abs=0.3)
    assert cs.stab_path(20.0)["hit"] is None


def antic_state(f, k, x0, cx=31.0, flip=False, ground=True, tm=None, hp=9, ev=()):
    st, tin = ("Cast Slam Antic", k / 60.0) if k < 16 else ("Cast Slam Antic 2", (k - 16) / 60.0)
    face = 1 if flip else -1
    s = state(f, st, tin, cx=cx, flip=flip, hx=cx + face * x0, ground=ground, hp=hp)
    s["hero"]["tm"] = tm or {"dash_cd": 0.0, "atk_cd": 0.0}
    s["ev"] = list(ev)
    return s


@pytest.mark.parametrize("flip", [False, True])
def test_the_script(flip):
    c = cs.CastStab()
    face = 1 if flip else -1
    toward = sp.M_R if -face > 0 else sp.M_L
    masks = {}
    for k in range(0, 40):
        ev = [{"k": "hit", "d": {"type_key": sp.CLAPPER, "src": "DashStab"}}] if k == 14 else []
        m = c.step(1000 + k, antic_state(1000 + k, k, 10.4, flip=flip, ground=k < 2 or k > 36, ev=ev), k < 2 or k > 36)
        if m is not None:
            masks[k + 2] = m
    ks = sorted(masks)
    j0 = ks[0]
    # the dash held (the sprint) with the key toward it until the hit, the attack on the dash's last frames
    assert all(masks[j0 + j] & sp.M_DASH and masks[j0 + j] & toward for j in range(0, 13))
    assert [j - j0 for j in ks if masks[j] & sp.M_A] == [5, 6]
    assert all(masks[j] == 0 for j in ks if j > 16)            # the recoil: no key
    st = c.stats()
    assert st["stabs"] == 1 and st["hit"] == 1


@pytest.mark.parametrize("x0,why", [(6.0, "distance"), (13.5, "distance"), (-9.0, "behind")])
def test_no_start(x0, why):
    c = cs.CastStab()
    assert c.step(1000, antic_state(1000, 2, x0), True) is None
    assert c.stats().get(f"no_{why}") == 1


def test_waits_for_the_ground_and_late():
    c = cs.CastStab()
    assert c.step(1000, antic_state(1000, 1, 9.2, ground=False), False) is None   # airborne: look again
    assert c.step(1020, antic_state(1020, 20, 9.2), True) is None                 # Cast Slam Antic 2: no start
    c2 = cs.CastStab()
    assert c2.step(1000, antic_state(1000, 12, 9.2), True) is None                # the mask's frame 14 > k_max
    assert c2.stats().get("no_late") == 1


def test_miss_hands_back():
    c = cs.CastStab()
    out = [c.step(1000 + k, antic_state(1000 + k, k, 10.4), True) for k in range(0, 30)]
    assert out[0] is not None and out[-1] is None and 0 in out      # the miss releases the dash, then hands back
    assert c.stats().get("why_miss") == 1


def test_hurt_aborts():
    c = cs.CastStab()
    assert c.step(1000, antic_state(1000, 0, 10.4), True) is not None
    assert c.step(1001, antic_state(1001, 1, 10.4, hp=7), True) is None
    assert c.stats().get("why_hurt") == 1
