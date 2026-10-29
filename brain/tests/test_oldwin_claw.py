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
    assert len(hooks) == 48 and all(h.ok for h in hooks)
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


def test_visible_body_outside_ray_reach_does_not_create_a_hook():
    state, boxes = fixture()
    boxes[:, [0, 2]] += 20.0
    assert all(not h.ok and h.why == "ray" for h in oldwin_claw.hook_variants(state, 1, 7, boxes))
