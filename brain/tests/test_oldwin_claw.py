import numpy as np

from ssbot.knowledge import kinematics as km
from ssbot.map2 import oldwin_claw, strike


def fixture():
    params = km.HeroParams()
    state = km.initial_state(params, 0.0, 6.0, ground=False)
    state[km.QX], state[km.QY] = -0.1, 5.9
    boxes = np.tile([4.0, 3.0, 7.0, 8.0], (80, 1))
    return state, boxes


def test_legacy_default_keeps_its_old_exact_stop():
    state, boxes = fixture()
    old = strike.claw_hook(state, 0, 1, 7, boxes, strike.HOOK_VARIANTS[0])
    explicit = strike.claw_hook(state, 0, 1, 7, boxes, strike.HOOK_VARIANTS[0],
                                discrete_stop=False, hold_steps=7)
    assert old.ok and abs(old.x_stop - 2.05) < 1e-10
    assert np.array_equal(old.pos, explicit.pos)
    assert old.ctrl == explicit.ctrl


def test_new_component_moves_whole_physics_steps_and_bounds_rendering():
    state, boxes = fixture()
    hooks = oldwin_claw.hook_variants(state, 1, 7, boxes)
    assert sum(len(h.alias_variants) for h in hooks) == 48 and all(h.ok for h in hooks)
    for h in hooks:
        assert abs(h.x_stop - 1.4) < 1e-10  # first full step puts the 3u damager into the body
        assert abs(h.x_stop / 1.4 - round(h.x_stop / 1.4)) < 1e-10
        assert np.isfinite(h.physical).all()
    starts = np.stack([h.pos[0] for h in hooks])
    assert starts.min(axis=0).tolist() == [-0.1, 5.9]
    assert starts.max(axis=0).tolist() == [0.0, 6.0]


def test_missing_ray_body_is_an_explicit_miss():
    state, boxes = fixture()
    boxes[:] = np.nan
    hooks = oldwin_claw.hook_variants(state, 1, 7, boxes)
    assert hooks and all(not h.ok and h.why == "ray" for h in hooks)


def test_damager_overlap_is_delivered_after_first_fixed_step():
    state, boxes = fixture()
    boxes[:, 0] = 1.0  # already within the newly enabled 3u damager
    hooks = oldwin_claw.hook_variants(state, 1, 7, boxes)
    assert all(h.ok and abs(h.x_stop - 1.4) < 1e-10 for h in hooks)


def test_unsupported_launch_is_rejected_instead_of_assuming_free_control():
    state, _ = fixture()
    assert oldwin_claw.launch_supported(state)
    assert not oldwin_claw.launch_supported(state, locked=True)
    state[km.GROUND] = 1
    assert not oldwin_claw.launch_supported(state)
    state[km.GROUND] = 0
    state[km.MODE] = km.M_GLIDE
    assert not oldwin_claw.launch_supported(state)
    state[km.MODE] = km.M_NORMAL
    state[km.WF_PH] = 0
    assert not oldwin_claw.launch_supported(state)
    state[km.WF_PH] = -1
    state[km.GS] = .5
    assert not oldwin_claw.launch_supported(state)


def test_visible_body_outside_ray_reach_does_not_create_a_hook():
    state, boxes = fixture()
    boxes[:, [0, 2]] += 20.0
    assert all(not h.ok and h.why == "ray" for h in oldwin_claw.hook_variants(state, 1, 7, boxes))


def test_hook_recovery_has_no_nail_pogo_invulnerability():
    from types import SimpleNamespace
    params = km.HeroParams()
    hook = SimpleNamespace(x_stop=10.0, y_hold=6.0, d=1)
    state = oldwin_claw.control_state(params, hook)
    assert state[km.INV_T] == 0
    assert abs(state[km.ATK_CD] - .15) < 1e-6
    assert abs(state[km.DS_REC] - (.1 + params.frame_time)) < 1e-6
    assert state[km.VY] == params.ds_end_vy


def test_fixed_row_splices_every_hook_outcome_and_keeps_endpoint_state():
    from ssbot.ipc.framing import mask
    from ssbot.map2.envelope import load_params
    params = load_params(hero2=True)
    state = km.initial_state(params, 0, 6, ground=False)
    commands = np.zeros(70, np.int64)
    commands[:2] = mask("clawline") | km.B_RIGHT
    boxes = np.tile([4.0, 3.0, 7.0, 8.0], (90, 1))
    ro = oldwin_claw.rollout(state, commands, params, None, boxes, 7)
    assert sum(len(h.alias_variants) for h in ro.hooks) >= 48
    assert ro.pos.shape == (len(ro.hooks), 71, 2)
    assert ro.final.shape == (km.K, len(ro.hooks))
    assert (ro.flags & km.F_INVULN == 0).all()
    assert np.all(ro.bound[..., :2] <= ro.box[..., :2])
    assert np.all(ro.bound[..., 2:] >= ro.box[..., 2:])
    for q, c in enumerate(ro.control_frames):
        assert (ro.flags[q, 2:c + 1] & km.F_RELINQ != 0).all()
        assert ro.final[km.MODE, q] == km.M_NORMAL
    assert {h.physics_phase for h in ro.hooks} == set(range(6))
    assert len({round(float(s[km.ALPHA]), 5) for s in ro.control_states.values()}) >= 6


def test_fixed_row_rejects_attack_inside_uncancellable_hook():
    from ssbot.ipc.framing import mask
    from ssbot.map2.envelope import load_params
    import pytest
    params = load_params(hero2=True)
    state = km.initial_state(params, 0, 6, ground=False)
    commands = np.zeros(70, np.int64)
    commands[:2] = mask("clawline")
    commands[10:12] = mask("attack") | mask("down")
    boxes = np.tile([4.0, 3.0, 7.0, 8.0], (90, 1))
    with pytest.raises(ValueError, match="inside uncancellable"):
        oldwin_claw.rollout(state, commands, params, None, boxes, 7)


def test_target_on_right_cannot_silently_turn_a_left_wire_press():
    from ssbot.ipc.framing import mask
    from ssbot.map2.envelope import load_params
    import pytest
    params = load_params(hero2=True)
    state = km.initial_state(params, 0, 6, ground=False)
    commands = np.zeros(70, np.int64)
    commands[:2] = mask("clawline") | km.B_LEFT
    boxes = np.tile([4., 3., 7., 8.], (90, 1))
    with pytest.raises(ValueError, match="ray"):
        oldwin_claw.rollout(state, commands, params, None, boxes, 7)
