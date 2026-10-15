"""Task 1v1 SG1: the hero event macros (ssbot.combat.hero_macros) against full kinematic rollouts (the full grid:
ssbot.tools.sg1_validate, forum.md 55)."""
import numpy as np
import pytest

from ssbot.combat import hero_macros as hmod
from ssbot.combat import pogo_slam as ps
from ssbot.knowledge import kinematics as kin


@pytest.fixture(scope="module")
def hm():
    from ssbot.train.forum_planner_policy import CREST_PARAMS
    params = kin.HeroParams.load(CREST_PARAMS["Wanderer"])
    terrain = kin.Terrain2D.from_boxes([(0.0, ps.FLOOR_Y - 5.0, 80.0, ps.FLOOR_Y)])
    return hmod.HeroMacros(params, terrain, x_world=40.0)


def _node(hm, q, key0=0):
    S = kin.initial_state(hm.params, 40.0, hm.stand_py, vx=key0 * hm.params.run_speed, facing=key0 or 1,
                          ground=True, alpha=hmod.ALPHAS[q])
    S[kin.MOVE] = key0
    S[kin.PREV] = hmod.key_mask(key0)
    return S


def _masks(keys, h=0, press=None):
    m = np.array([hmod.key_mask(int(k)) for k in keys], np.int64)
    m[:h] |= kin.B_JUMP
    if press is not None:
        m[max(press - 3, 0):press + 3] |= kin.B_DOWN
        m[press] |= kin.B_ATTACK
    return m


def test_step_cycle(hm):
    for q in range(6):
        assert hm.st[q, 1:13].sum() == 10                                  # 5 steps in 6 frames
        assert hm.q_after(q, 6) == q
    assert hm.step_u == pytest.approx(0.165, abs=1e-6)


@pytest.mark.parametrize("q", range(6))
def test_jump_macro_is_the_rollout(hm, q):
    for h, m, d, r, key0 in ((0, 10, 1, 0, 0), (5, 6, -1, 0, 1), (12, 15, 1, 4, 0), (30, 25, -1, 0, -1)):
        keys, _ = hm.solve_keys(q, m, d, 70, r)
        sw, _ = hm.sweep(40.0, q, keys, "jump" if h else "stand", max(h, 1), key0)
        ro = kin.rollout(_node(hm, q, key0), _masks(keys, h)[None], hm.params, hm.terrain)
        n = len(sw.box)
        np.testing.assert_allclose(sw.box[1:], ro.box[0, 1:n], atol=1e-6)
        np.testing.assert_allclose(sw.pos[1:], ro.pos[0, 1:n], atol=0.02)
        if h:
            assert sw.land == np.flatnonzero((ro.flags[0, 2:] & kin.F_GROUND) != 0)[0] + 2


@pytest.mark.parametrize("q", (0, 3))
def test_down_slash_contact_and_bounce(hm, q):
    cy = ps.FLOOR_Y + 4.434
    T = 100
    for h, a, d, off in ((8, 10, 1, 0.0), (20, 18, 0, -1.0), (30, 30, -1, 1.0)):
        keys = np.full(T, d, np.int64)
        M = _masks(keys, h, a)[None]
        S = _node(hm, q)
        miss = kin.rollout(S, M, hm.params, hm.terrain)
        cx = miss.box[0, a + 1, 0] + hm.hw + off
        box = np.array([cx - 1.341, cx + 1.873, cy - 4.434, cy - 0.532])
        face = d or 1
        c_r = hm.contact(hmod.Sweep(miss.box[0], miss.pos[0], miss.flags[0], -1), a + 1, face, lambda j: [box])
        sw, c_m = hm.sweep(40.0, q, keys, "jump", h, press=a, face=face, targets=lambda j: [box], n=T + 1)
        assert c_r == c_m >= 0
        ev = np.zeros((1, T), np.int64)
        ev[0, c_r - 1] = kin.EV_POGO
        hit = kin.rollout(S, M, hm.params, hm.terrain, events=ev)
        np.testing.assert_allclose(sw.box, hit.box[0], atol=0.005)
        inv = np.flatnonzero((hit.flags[0, c_r:c_r + 20] & kin.F_INVULN) != 0)
        assert (inv[0], inv[-1]) == hmod.IFRAMES == hm.iframes((q - c_r) % 6)


def test_bounce_is_one_class_and_cooldown(hm):
    heights = {round(float(b.y[b.apex]), 3) for b in hm.bounces.values()}
    assert heights == {4.092} and {b.apex for b in hm.bounces.values()} <= {22, 23}
    assert {hm.cooldown(q) for q in range(6)} == {hmod.COOLDOWN_F}


def test_apex_node_and_cone(hm):
    nd = hm.apex_node(40.0, 2, 20, 41.5)
    assert nd is not None and abs(nd["x"] - 41.5) <= hm.step_u / 2 + 1e-9
    assert hm.apex_node(40.0, 2, 1, 45.0) is None                         # out of a short hop's reach
    lo, hi = hm.cone(2, 30)
    assert lo == -hi and hi == pytest.approx(hm.step_u * hm.reach_steps(2, 30))
