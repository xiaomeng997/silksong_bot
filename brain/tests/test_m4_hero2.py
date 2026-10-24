"""Map v2 stage M4a: the HERO2 bits measured on the m4_probe recordings (forum.md 95), the envelope's handling of
them and the search's hooked-body window."""
import numpy as np
import pytest

from ssbot.knowledge import kinematics as kin

WANDERER = kin.REPO / "knowledge" / "1.0.30000" / "kinematics" / "hero_wanderer_forum.json"
M_J, M_DASH, M_R, M_L, M_A, M_D = kin.B_JUMP, kin.B_DASH, kin.B_RIGHT, kin.B_LEFT, kin.B_ATTACK, kin.B_DOWN


@pytest.fixture(scope="module")
def base():
    return kin.HeroParams.load(WANDERER)


@pytest.fixture(scope="module")
def h2(base):
    return kin.hero2(base, on=True)


def _without(p, bit):
    return kin.HeroParams.from_json(dict(p.to_json(), hero2=p.hero2 & ~bit))


def _roll(params, m, ground=True, y=4.568, terrain=None):
    S = kin.initial_state(params, 30.0, y, facing=1, ground=ground)
    return kin.rollout(S, np.array([m], np.int64), params, terrain, backend="numba")


def _first(r, mode, after=0):
    i = np.flatnonzero(r.mode[0, after:] == mode)
    return int(i[0]) + after if len(i) else None


def _att_on(r, after=0):
    a = (r.flags[0] & kin.F_ATTACKING) != 0
    i = np.flatnonzero(a[after:] & ~np.r_[False, a[after:-1]])
    return int(i[0]) + after if len(i) else None


def test_row_layout_and_pad():
    assert kin.K == 85 and kin.ROW_NAMES[kin.ABUF] == "abuf" and kin.ROW_NAMES[kin.XVX] == "xvx"
    assert kin.ROW_NAMES[kin.SHUT] == "shut" and kin.ROW_NAMES[kin.XVXD] == "xvxd"      # (T1b: K 83 -> 85)
    old = np.arange(81.0)
    p = kin.pad_state(old)
    assert p.shape == (85,) and np.array_equal(p[:81], old) and p[81:].sum() == 0
    assert kin.pad_state(np.zeros(85)).shape == (85,)
    assert kin.pad_state(np.ones((83, 3))).shape == (85, 3)


def test_jump_sets_the_dash_cooldown(h2):
    """HeroJump sets dashCooldownTimer 0.05 s: a dash pressed on the jump's next frame and held fires 4 frames after
    the jump (the nominal 0.01665 s frames: 3 Updates leave 5e-5 s), tapped for 2 frames it is lost; the model before
    M4a dashed at once (live m4: 'jd' 10 -> 16 / 16 within 0.1 u, 'dja' 4 -> 27 / 52)."""
    assert h2.hero2 & kin.H2_JUMP_DCD
    old = _without(h2, kin.H2_JUMP_DCD)
    held = [M_J] + [M_J | M_DASH | M_R] * 6 + [M_J] * 10 + [0] * 20
    tap = [M_J] + [M_J | M_DASH | M_R] * 2 + [M_J] * 14 + [0] * 20
    # rollout index 0 is the start frame: the jump is latched at index 1
    assert _first(_roll(old, held), kin.M_DASH) == 2
    assert _first(_roll(h2, held), kin.M_DASH) == 5
    assert _first(_roll(old, tap), kin.M_DASH) == 2
    assert _first(_roll(h2, tap), kin.M_DASH) is None


def test_jump_dcd_off_unchanged(h2):
    old = _without(h2, kin.H2_JUMP_DCD)
    m = [0] * 3 + [M_J] * 12 + [0] * 30
    assert np.array_equal(_roll(old, m).box, _roll(h2, m).box)


def _air_dash(attack_at=None, jump_at=None, after_key=0, T=40):
    """An air dash pressed at index 1 from rest high up (free space), the attack / the jump pressed at a mask index
    (index i of the masks acts in rollout frame i + 1), then after_key held."""
    m = [M_DASH | M_R] * 2 + [after_key] * (T - 2)
    if attack_at is not None:
        m[attack_at] |= M_A
        m[attack_at + 1] |= M_A
    if jump_at is not None:
        for i in range(jump_at, min(jump_at + 20, T)):
            m[i] |= M_J
    return m


def test_sprint_attack_cancel_gate_and_buffer(h2):
    """The air sprint's Attack Cancel: the attack queue (a press seen 1 .. 7 frames later) and the state's 0.08 s:
    a press in the dash swings 4 frames after the Air Sprint's entry (live 30 / 30), a later press a frame after it
    (live 27 / 27), a press 4 frames before the entry expires (live 2 / 2: the sprint runs on)."""
    r = _roll(h2, _air_dash(), ground=False, y=20.0)
    AS = _first(r, kin.M_SPRINT)
    assert AS is not None and _att_on(r) is None
    # the press with the dash (mask index 0 -> frame 1): AS - 3 or AS - 4
    for i_press in range(AS - 3, AS + 4):
        if i_press < 0:
            continue
        rr = _roll(h2, _air_dash(attack_at=i_press - 1), ground=False, y=20.0)
        assert _att_on(rr) == AS + 4, (i_press, AS)
    for i_press in (AS + 4, AS + 6, AS + 9):
        rr = _roll(h2, _air_dash(attack_at=i_press - 1), ground=False, y=20.0)
        assert _att_on(rr) == i_press + 1
    rr = _roll(h2, _air_dash(attack_at=AS - 4 - 1), ground=False, y=20.0) if AS - 5 >= 0 else None
    if rr is not None:
        assert _att_on(rr) is None or _att_on(rr) > AS + 10
    # the model before: the cancel on the press frame itself
    old = _without(h2, kin.H2_SPR_ATK)
    ro = _roll(old, _air_dash(attack_at=AS + 6 - 1), ground=False, y=20.0)
    assert _first(ro, kin.M_NORMAL, AS) == AS + 6


def test_sprint_attack_extra_velocity(h2):
    """Retain Extra Velocity: after the cancel, with no key held she keeps moving at the sprint's speed decaying x0.8
    per physics step; with the key toward it, the run speed (live: 18.10 -> 8.25 held -> 11.58, 9.27, 7.41, ...)."""
    AS = _first(_roll(h2, _air_dash(), ground=False, y=20.0), kin.M_SPRINT)
    i_press = AS + 6
    free = _roll(h2, _air_dash(attack_at=i_press - 1, after_key=0), ground=False, y=20.0)
    held = _roll(h2, _air_dash(attack_at=i_press - 1, after_key=M_R), ground=False, y=20.0)
    old = _roll(_without(h2, kin.H2_SPR_ATK), _air_dash(attack_at=i_press - 1, after_key=0), ground=False, y=20.0)
    k = i_press + 1                        # the cancel frame
    vx_free = free.vel[0, k + 1:k + 9, 0]
    v = vx_free[np.r_[True, np.diff(vx_free) != 0]]   # (a frame without a physics step keeps the velocity)
    assert v[0] > 10.0 and np.allclose(v[1:4] / v[:3], 0.8, atol=1e-3)            # decaying x0.8, not the run
    assert np.allclose(held.vel[0, k + 2:k + 8, 0], h2.run_speed)
    assert free.centre[0, k + 10, 0] - free.centre[0, k, 0] > 1.0
    assert abs(old.centre[0, k + 10, 0] - old.centre[0, k + 1, 0]) < 0.6           # the model before: no extra


def test_sprint_jump_umbrella(h2):
    """Queue Sprint Jump?: a jump pressed in the air sprint opens the umbrella at once; pressed on the dash's last
    frame it acts at the sprint's first frame (the state's FixedUpdate entry reads the frame before), pressed two
    frames before the entry it does nothing (live 6 / 6)."""
    r = _roll(h2, _air_dash(), ground=False, y=20.0)
    AS = _first(r, kin.M_SPRINT)
    g = _roll(h2, _air_dash(jump_at=AS + 2 - 1), ground=False, y=20.0)
    assert _first(g, kin.M_GLIDE) == AS + 2
    g = _roll(h2, _air_dash(jump_at=AS - 1 - 1), ground=False, y=20.0)
    assert _first(g, kin.M_GLIDE) == AS
    g = _roll(h2, _air_dash(jump_at=AS - 2 - 1), ground=False, y=20.0)
    assert _first(g, kin.M_GLIDE) is None or _first(g, kin.M_GLIDE) > AS + 10


def test_jump_spends_the_press(h2):
    """A jump then an air dash 4 frames later: the sprint's first frame does not see the jump's press (HeroJump's
    ClearJumpInputState) - it runs to its end (live 'jd' 16 / 16)."""
    m = [M_J] * 12 + [0] * 40
    m[4] |= M_DASH | M_R
    m[5] |= M_DASH | M_R
    r = _roll(h2, m)
    AS = _first(r, kin.M_SPRINT)
    assert AS is not None and _first(r, kin.M_GLIDE) is None
    assert np.all(r.mode[0, AS:AS + 10] == kin.M_SPRINT)


def test_dash_end_reads_the_frame_before(h2):
    """A ground dash tapped, the key pressed again on its end frame (the first not dashing) and held: no sprint
    (the sprint FSM's states entered in FixedUpdate read the frame before's key: live 9 / 9 at re 0 .. +1); held
    through the end frame: the sprint."""
    from ssbot.map2 import envelope as env
    terr = env.floor_terrain()
    y0 = env.FLOOR_BB + h2.foot
    m0 = [M_DASH | M_R] * 2 + [M_R] * 40
    r0 = _roll(h2, m0, y=y0, terrain=terr)
    end = _first(r0, kin.M_NORMAL, 2)                   # the dash's end frame in the model (no sprint: released)
    assert end is not None
    re = list(m0)
    for i in range(end - 1, 40):
        re[i] |= M_DASH
    old = _without(h2, kin.H2_DASH_END)
    assert abs(_roll(old, re, y=y0, terrain=terr).vel[0, end + 4, 0]) > 15.0
    assert abs(_roll(h2, re, y=y0, terrain=terr).vel[0, end + 4, 0]) == pytest.approx(h2.run_speed)
    held = [M_DASH | M_R] * 40
    assert abs(_roll(h2, held, y=y0, terrain=terr).vel[0, 20, 0]) > 15.0


def test_m0_rules_unchanged_without_the_m4_bits(h2):
    """The M0 bits alone give the M0 rollouts (the M4a bits gate every new rule)."""
    m0only = kin.HeroParams.from_json(dict(h2.to_json(), hero2=kin.H2_GLIDE_GRAV | kin.H2_REL_LOSS | kin.H2_POGO_RS
                                             | kin.H2_GLIDE_ATK | kin.H2_INFL_END))
    m = [M_J] * 16 + [0] * 4 + [M_J] * 30 + [M_D | M_A] * 2 + [0] * 30
    a = _roll(m0only, m)
    b = _roll(kin.HeroParams.from_json(dict(h2.to_json(), hero2=m0only.hero2)), m)
    assert np.array_equal(a.box, b.box)


# ---- the envelope (ssbot.map2.env_jit) --------------------------------------------------------------------------

def test_envelope_holds_the_extra_velocity():
    """After the air sprint's Attack Cancel a member without a key moves faster than the run lane: the envelope's
    lane is extended by it (xvx_extra) and holds the no-key rollout; the attack in the ground sprint and the jump in
    the ground dash are not taken (the reference drops them as the engine does)."""
    from ssbot.map2 import envelope as env
    from ssbot.map2 import env_jit as ej
    from ssbot.tools import m1_envelope as me
    eng = env.Engine()
    assert eng.params.hero2 & kin.H2_SPR_ATK
    S = kin.initial_state(eng.params, 0.0, 20.0, ground=False)
    st = eng.start_state(S)
    T = 22
    fw = eng.forward(st, T, max_events=3)
    masks = []
    for a in range(3, 12):
        for key in (0, kin.B_RIGHT):
            m = [kin.B_DASH | kin.B_RIGHT] * 2 + [key] * (T - 2)
            m[a] |= kin.B_ATTACK
            masks.append(m)
    masks = np.array(masks, np.int64)
    xy, _ = eng.rollouts(np.repeat(S[None], len(masks), 0), np.repeat(st.cu[None], len(masks), 0), masks)
    fidx = me.frame_index(fw)
    for i in range(len(masks)):
        for t in range(1, T + 1):
            assert me.point_dist(fw, fidx, t, xy[i, t, 0], xy[i, t, 1]) == 0, (i, t)
    # the no-key rollouts do pass the key-held ones (the extension matters)
    assert max(float(np.max(xy[2 * j, :, 0] - xy[2 * j + 1, :, 0])) for j in range(9)) > 0.3
    assert ej.xvx_extra(18.0, 0.0, 1, eng.P) > 0 and ej.xvx_extra(-18.0, 0.0, 1, eng.P) < 0
    assert ej.xvx_extra(5.0, 0.0, 1, eng.P) == 0
    # (T1b: the lane's own decay - ShuttleCockCancel's 5 / s keeps the extra above the run longer)
    assert ej.xvx_extra(18.0, 5.0, 3, eng.P) > ej.xvx_extra(18.0, 0.0, 3, eng.P)


def test_unhooked_claw_control_keeps_the_air_dash():
    """The unhooked Clawline does not restore the air dash (live: can.dash false at control 23 / 24 after one)."""
    from ssbot.map2 import env_jit as ej
    x = np.zeros(kin.K)
    x[kin.AIRDASHED] = 1.0
    ej.claw_control(x)
    assert x[kin.AIRDASHED] == 1.0
    x[kin.AIRDASHED] = 0.0
    ej.claw_control(x)
    assert x[kin.AIRDASHED] == 0.0


def test_hooked_body_window():
    """The hooked Clapper's body is harmless from P + 17 through control + 12 (live: its first contact attempt /
    damage at the Harpoon FSM's Idle + 1 = control + 13 / 14); an unhooked Clawline has no window; the control state
    keeps the air dash used for an unhooked one."""
    from ssbot.map2 import strike as sk
    h = sk.Hook(P=10, d=1, iid=7, variant="early", pos=np.zeros((27, 2)), hit=18, ctrl=36, x_stop=0.0, y_hold=4.0)
    assert sk.hook_body_off([h], 26) == ()
    assert sk.hook_body_off([h], 27) == (7,)
    assert sk.hook_body_off([h], 48) == (7,)
    assert sk.hook_body_off([h], 49) == ()
    u = sk.Hook(P=10, d=1, iid=7, variant="unhooked", pos=np.zeros((27, 2)), hit=-1, ctrl=42, x_stop=0.0,
                y_hold=4.0, ok=False, why="ray")
    assert sk.hook_body_off([u], 30) == ()
    p = kin.HeroParams.load(WANDERER)
    assert sk.control_state(p, h, airdashed=1.0)[kin.AIRDASHED] == 0.0
    assert sk.control_state(p, u, airdashed=1.0)[kin.AIRDASHED] == 1.0


def test_t1b_sprint_jump():
    """HERO2 T1b (H2_SHUTTLE): a ground dash held into the sprint with a jump pressed in it -> the sprint FSM's Jump
    Antic (7 frames, her x speed kept) -> the sprint (shuttlecock) jump: 18 u/s along her facing while rising, the
    extra air velocity after its apex; with the bit off the old model (no antic)."""
    base = kin.HeroParams.load(kin.REPO / "knowledge" / "1.0.30000" / "kinematics" / "hero_wanderer_forum.json")
    on = kin.hero2(base, on=True)
    off = kin.HeroParams.from_json(dict(on.to_json(), hero2=int(on.hero2) & ~kin.H2_SHUTTLE))
    terr = kin.Terrain2D.from_boxes([(-1.0e4, 1.0, 1.0e4, 3.015)])
    masks = np.array([kin.B_DASH | kin.B_RIGHT] * 12 + [kin.B_DASH | kin.B_RIGHT | kin.B_JUMP] * 14 +
                     [kin.B_RIGHT] * 20, dtype=np.int64)
    res = {}
    for nm, prm in (("on", on), ("off", off)):
        S = kin.initial_state(prm, 20.0, 3.015 + prm.foot, ground=True, alpha=0.5)
        res[nm] = kin.rollout(S, masks[None], prm, terr)
    xs = res["on"].centre[0, :, 0]
    ys = res["on"].centre[0, :, 1]
    lift = 5 + int(np.flatnonzero(ys[5:] > ys[5] + 0.01)[0])      # (the start settles onto the floor first)
    dx = np.diff(xs)
    # the antic before the lift: her x speed constant (steps of one size, frames without a step 0)
    a = dx[lift - 7:lift - 1]
    a = a[a > 0]
    assert len(a) >= 4 and np.ptp(a) < 1e-9 and a[0] > 0.3
    # rising: 18 u/s
    r = dx[lift + 1:lift + 6]
    r = r[r > 0]
    assert np.allclose(r, 18.0 * on.fdt, atol=1e-6)
    # the bit off: no sprint jump (the press is not offered there; the old model's x differs)
    assert not np.allclose(res["off"].centre[0, :, 0], xs)
