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



def test_reused_hook_hit_branch_is_exactly_the_full_rollout():
    from ssbot.ipc.framing import mask
    from ssbot.map2.envelope import load_params
    params = load_params(hero2=True)
    state = km.initial_state(params, 0, 6, ground=False)
    commands = np.zeros(75, np.int64)
    commands[:2] = mask("clawline") | km.B_RIGHT
    commands[43:45] = km.B_ATTACK | km.B_DOWN
    boxes = np.tile([4., 3., 7., 8.], (90, 1))
    base = oldwin_claw.rollout(state, commands, params, None, boxes, 7)
    original = base.bound.copy()
    events = np.zeros((len(base.hooks), len(commands)), np.int64)
    # Distinct contacts, including a late event: every phase and suffix must
    # stay attached to its own hook, not the first or most favorable outcome.
    for q in range(len(events)):
        events[q, 49 + q % 3] = km.EV_POGO
    direct = oldwin_claw.rollout(state, commands, params, None, boxes, 7, events=events)
    reused = oldwin_claw.with_events(base, params, None, events)
    for name in ("phys", "pos", "vel", "mode", "flags", "box", "bound", "flags_all", "flags_any", "final"):
        assert np.array_equal(getattr(direct, name), getattr(reused, name)), name
    assert np.array_equal(base.bound, original)
    assert not (base.flags & km.F_INVULN).any()
    assert (reused.flags_all & km.F_INVULN).any()
    for q, c in enumerate(base.control_frames):
        assert np.array_equal(reused.bound[q, :c + 1], base.bound[q, :c + 1])


def test_reused_hook_rejects_events_that_could_change_the_hook():
    import pytest
    state, boxes = fixture()
    params = km.HeroParams()
    commands = np.zeros(70, np.int64)
    commands[:2] = (1 << 4) | km.B_RIGHT
    base = oldwin_claw.rollout(state, commands, params, None, boxes, 7)
    events = np.zeros_like(commands)
    events[10] = km.EV_POGO
    with pytest.raises(ValueError, match="inside hook/prefix"):
        oldwin_claw.with_events(base, params, None, events)



def test_reused_hook_with_a_new_drift_and_shorter_endpoint_is_exact():
    from ssbot.ipc.framing import mask
    from ssbot.map2.envelope import load_params
    import pytest
    params = load_params(hero2=True)
    state = km.initial_state(params, 0, 6, ground=False)
    keys = np.zeros(75, np.int64)
    keys[:2] = mask("clawline") | km.B_RIGHT
    boxes = np.tile([4., 3., 7., 8.], (90, 1))
    base = oldwin_claw.rollout(state, keys, params, None, boxes, 7)
    for length, direction in ((75, km.B_RIGHT), (75, km.B_LEFT), (38, km.B_RIGHT)):
        commands = keys[:length].copy()
        commands[2:] |= direction
        direct = oldwin_claw.rollout(state, commands, params, None, boxes, 7)
        reused = oldwin_claw.with_commands(base, commands, params, None)
        for name in ("phys", "pos", "vel", "mode", "flags", "box", "bound", "flags_all", "flags_any", "final"):
            assert np.array_equal(getattr(direct, name), getattr(reused, name)), name
    changed = keys.copy(); changed[0] ^= km.B_RIGHT | km.B_LEFT
    with pytest.raises(ValueError, match="changed hook/prefix"):
        oldwin_claw.with_commands(base, changed, params, None)
    changed = keys.copy(); changed[10] = km.B_ATTACK
    with pytest.raises(ValueError, match="uncancellable hook"):
        oldwin_claw.with_commands(base, changed, params, None)



def test_pogo_physics_clock_keeps_zero_step_frames_and_requires_every_phase():
    params = km.HeroParams()
    state = km.initial_state(params, 0., 10., ground=False)
    state[km.ALPHA] = .25; state[km.ALO] = .1; state[km.AHI] = .9
    events = np.zeros((1, 24), np.int64); events[0, 2] = km.EV_POGO
    nominal, every, any_lane = oldwin_claw.pogo_protection(state, events, params)
    assert not any_lane[:, :3].any()  # no protection before the contact
    assert (every <= nominal).all() and (nominal <= any_lane).all()
    assert not every[0, -1] and not any_lane[0, -1]
    assert (any_lane & ~every).any()  # an advantageous phase cannot shield all lanes
    # A near-zero dt does not spend a FixedUpdate or expire the counter.
    alphas = np.array([[.1, .2, .3]])
    slow = oldwin_claw._pogo_clock(alphas, events, .00001, params.fdt)
    assert slow[:, :, 3:].all()


def test_pogo_physics_clock_rejects_unvalidated_freezes_and_multi_step_contact():
    import pytest
    params = km.HeroParams()
    state = km.initial_state(params, 0., 10., ground=False)
    events = np.zeros((1, 24), np.int64); events[0, 2] = km.EV_POGO
    state[km.TS] = .5
    with pytest.raises(ValueError, match="normal time"):
        oldwin_claw.pogo_protection(state, events, params)
    with pytest.raises(ValueError, match="multi-step"):
        oldwin_claw._pogo_clock(np.zeros((1, 3)), events, .05, .02)


def test_new_pogo_flag_changes_no_motion_and_leaves_the_shared_params_unchanged():
    from ssbot.map2.envelope import load_params
    params = load_params(hero2=True)
    state = km.initial_state(params, 0., 10., ground=False)[:, None]
    commands = np.zeros((1, 28), np.int64)
    events = np.zeros_like(commands); events[0, 3] = km.EV_POGO
    old = km.rollout(state, commands, params, events=events, variants="bounds")
    new = oldwin_claw._recovery_rollout(state, commands, params, None, events, 1)
    for name in ("phys", "pos", "vel", "mode", "box", "bound"):
        assert np.array_equal(getattr(old, name), getattr(new, name)), name
    assert params.pogo_invul == .16
    assert not (new.flags_all[:, :4] & km.F_INVULN).any()



def test_pogo_phase_flags_match_fixed_updates_observed_in_kinematics_motion():
    from dataclasses import replace
    from ssbot.map2.envelope import load_params
    from ssbot.tools.forum_knife_pogo_audit import counter_after_steps
    params = load_params(hero2=True)
    commands = np.full((1, 26), km.B_RIGHT, np.int64)
    events = np.zeros_like(commands); events[0, 2] = km.EV_POGO
    for phase in np.linspace(.05, .95, 6):
        state = km.initial_state(params, 5., 12., ground=False)
        state[km.VX] = params.run_speed
        state[km.ALPHA] = phase
        state[km.ALO], state[km.AHI] = max(phase-.08, 0.), min(phase+.08, 1.)
        # Read actual physics steps from horizontal displacement of the old
        # kinematics kernel, independently of the new phase integrator.
        ro = km.rollout(state, commands, replace(params,pogo_invul=0.), events=events,
                        variants="bounds", lanes=True)
        steps = np.rint(np.diff(ro.var_box[0,:,:,0],axis=1)/(params.run_speed*params.fdt)).astype(int)
        assert np.isin(steps, [0,1]).all()
        protected = np.zeros((len(steps),27), bool)
        for v, fs in enumerate(steps):
            protected[v,3] = True
            protected[v,4:] = counter_after_steps(8,fs[3:]) > 0
        nominal, every, any_lane = oldwin_claw.pogo_protection(state,events,params)
        assert np.array_equal(nominal[0],protected[0])
        assert np.array_equal(every[0],protected.all(axis=0))
        assert np.array_equal(any_lane[0],protected.any(axis=0))



def test_invalid_pogo_clock_cannot_create_a_protected_tail():
    import pytest
    params = km.HeroParams()
    events = np.zeros((1,20),np.int64);events[0,1] = km.EV_POGO
    for field,value in ((km.ALPHA,np.nan),(km.AHI,np.inf),(km.ALO,1.1)):
        state = km.initial_state(params,0.,10.,ground=False);state[field] = value
        with pytest.raises(ValueError,match="invalid pogo"):
            oldwin_claw.pogo_protection(state,events,params)
    state = km.initial_state(params,0.,10.,ground=False)
    events[0,10] = km.EV_POGO
    with pytest.raises(ValueError,match="unsupported pogo events"):
        oldwin_claw.pogo_protection(state,events,params)
