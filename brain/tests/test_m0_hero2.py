"""Map v2 stage M0: SSBOT_FORUM_HERO2 (kinematics.hero2, the kin_jit H2_* bits, hero_macros' bounce, claw_strike's
hold height, knowledge.hero2's Clawline carve-out) and the m0_probe's trial generators. forum.md 91."""
import random

import numpy as np
import pytest

from ssbot.knowledge import kinematics as kin

WANDERER = kin.REPO / "knowledge" / "1.0.30000" / "kinematics" / "hero_wanderer_forum.json"
M_J, M_A, M_D = kin.B_JUMP, kin.B_ATTACK, kin.B_DOWN


@pytest.fixture(scope="module")
def base():
    return kin.HeroParams.load(WANDERER)


def _seg(m, n):
    return [m] * n


def _float_masks(press_at_release: bool):
    """A full jump, the umbrella opened and held 30 frames into its float, then the attack: held (jump kept) or on the
    release frame."""
    m = _seg(M_J, 16) + _seg(0, 4) + _seg(M_J, 36)
    if press_at_release:
        m += _seg(M_D | M_A, 3) + _seg(0, 40)
    else:
        m += _seg(M_J | M_D | M_A, 3) + _seg(M_J, 40)
    return np.array([m], np.int64)


def _roll(params, masks, ev=None):
    S = kin.initial_state(params, 30.0, 4.568, facing=1, ground=True)
    return kin.rollout(S, masks, params, None, events=ev)


def test_hero2_off_is_the_same_object(base, monkeypatch):
    monkeypatch.delenv(kin.HERO2_ENV, raising=False)
    assert kin.hero2(base) is base
    monkeypatch.setenv(kin.HERO2_ENV, "1")
    p2 = kin.hero2(base)
    assert p2 is not base and p2.hero2 == kin.H2_ALL
    assert kin.hero2(kin.HeroParams(), on=True).hero2 == 0          # no Forum abilities: unchanged


def test_hero2_bits_zero_rollout_unchanged(base):
    """The new parameter slots at 0 (the default) leave every rollout as it was (the bits gate every new rule)."""
    masks = _float_masks(False)
    a = _roll(base, masks)
    b = _roll(kin.HeroParams.from_json(dict(base.to_json(), hero2=0)), masks)
    assert np.array_equal(a.box, b.box) and np.array_equal(a.flags, b.flags)


def test_glide_attack_cancel_gravity_and_frame(base):
    """Float Idle, jump held, attack: live the slash comes on the press frame and gravity is back at once (-1.2 per
    step); the old model swung a frame late and ramped the gravity as an air hang."""
    masks = _float_masks(False)
    press = 16 + 4 + 36
    old = _roll(base, masks)
    new = _roll(kin.hero2(base, on=True), masks)
    att_new = np.flatnonzero((new.flags[0] & kin.F_ATTACKING) != 0)
    att_old = np.flatnonzero((old.flags[0] & kin.F_ATTACKING) != 0)
    assert att_new[0] == press + 1                                    # index 0 = the start state: mask i is frame i+1
    assert att_old[0] == press + 2
    dv = np.diff(new.vel[0, press + 1:press + 8, 1])
    assert np.all((np.abs(dv + 1.2) < 1e-6) | (np.abs(dv) < 1e-9))    # full gravity (frames without a step: 0)
    dv_old = np.diff(old.vel[0, press + 1:press + 8, 1])
    assert np.abs(dv_old[np.abs(dv_old) > 1e-9]).min() < 1.0          # the air-hang ramp


def test_release_frame_press_lost(base):
    """The jump released on the attack's press frame: the Deflate, no slash (live 0 / 20)."""
    masks = _float_masks(True)
    old = _roll(base, masks)
    new = _roll(kin.hero2(base, on=True), masks)
    assert (old.flags[0] & kin.F_ATTACKING).any()
    assert not (new.flags[0] & kin.F_ATTACKING).any()


def test_pogo_restart_rise(base):
    """A down slash pressed 3 frames before the contact: the bounce restarts at the slash's Bounce event (live rise
    3.74 u over the contact frame's box in 79 % of 115 contacts, 4.09 in 16 %); the old model rose ~0.5 u higher."""
    T = 60
    m = np.zeros((1, T), np.int64)
    m[0, 0:2] = M_D | M_A
    ev = np.zeros((1, T), np.int64)
    ev[0, 3] = kin.EV_POGO
    S = kin.initial_state(base, 30.0, 14.0, vy=-6.0, facing=1, ground=False)
    rises = {}
    for lab, p in (("old", base), ("new", kin.hero2(base, on=True))):
        r = kin.rollout(S, m, p, None, events=ev)
        y = r.box[0, 4:, 1] - r.box[0, 4, 1]
        rises[lab] = (float(y.max()), int(np.argmax(y)))
    assert rises["new"][0] == pytest.approx(3.74, abs=0.4)
    assert rises["old"][0] - rises["new"][0] > 0.3
    assert 20 <= rises["new"][1] <= 23


def test_hero_macros_bounce_hero2(base):
    from ssbot.combat.hero_macros import HeroMacros
    hm = HeroMacros(kin.hero2(base, on=True), None, T=60, holds=range(1, 3))
    b = hm.bounce(0)
    assert b.y.max() == pytest.approx(3.74, abs=0.4) and 19 <= b.apex <= 23


def test_claw_hold_and_track():
    from ssbot.knowledge import hero2 as h2
    assert h2.hold_bb(2.0, 0.0) == pytest.approx(2.0)
    assert h2.hold_bb(2.0, 17.4, 7) == pytest.approx(2.0 + 0.02 * 5 * 0.875 * sum(0.875 ** k for k in range(1, 8)))
    assert h2.hold_bb(2.0, -25.0, 8) < 2.0 - 0.7                    # clamped at -10
    fs = [0 if j % 6 == 0 else 1 for j in range(1, 60)]
    tr = h2.claw_unhooked(20.0, 3.0, 0.0, 0.0, 1, fs)
    assert tr.ctrl == h2.CLAW_CTRL_F and len(tr.x) == h2.CLAW_CTRL_F + 1
    assert tr.x[h2.CLAW_DASH_F] == pytest.approx(20.0)              # the dash moves from the frame after its entry
    assert 9.0 <= tr.x[-1] - 20.0 <= 11.5                            # live pull 9.4 .. 10.8 (p10 .. p90)
    assert tr.vy[-1] == 0.0 and tr.vx[-1] == pytest.approx(12.46, abs=0.02)
    assert np.allclose(tr.bb, 3.0)


def test_claw_strike_hold_off_is_the_old_fit(monkeypatch):
    from ssbot.combat import claw_strike as cs
    monkeypatch.setattr(cs, "HERO2", False)
    assert cs.hold_bb(2.0, 3.0) == 2.0 + cs.DY0 + cs.DYV * 3.0
    assert not cs.vy_ok(12.0)
    monkeypatch.setattr(cs, "HERO2", True)
    assert cs.hold_bb(2.0, 17.0) == pytest.approx(2.0 + cs.H2_HOLD_K * 5.0)
    assert cs.vy_ok(-20.0)


def test_m0_probe_generators():
    from ssbot.probes import m0_probe as mp
    rng = random.Random(3)
    for kind in ("fl_atk", "fl_claw"):
        for _ in range(50):
            ms, p = mp.trial_fl(rng, kind)
            assert len(ms) < mp.PRE_SPAWN_F and p["v"]
    for _ in range(50):
        assert len(mp.trial_drift(rng)[0]) < mp.PRE_SPAWN_F
        assert len(mp.trial_whiff(rng)[0]) < mp.PRE_SPAWN_F
        assert len(mp.trial_dash(rng, 1)[0]) < mp.PRE_SPAWN_F
