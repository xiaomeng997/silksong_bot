"""Local hooked-motion support for synchronous old-planner rows.

No search, input owner, or background work. The render endpoints represent the
unknown interpolation fraction between successive physics poses. Callers must
check the full envelope, not choose the most favorable variant.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from itertools import product

import numpy as np
import numba

from ssbot.knowledge import hero2
from ssbot.knowledge import kinematics as km
from ssbot.map2 import strike as sk

COMPONENT_MARGIN_U = .25


@dataclass(slots=True)
class ClawRollout(km.Rollout):
    hooks: list = field(default_factory=list)
    control_frames: np.ndarray | None = None
    control_states: dict = field(default_factory=dict)
    launch_frame: int = 0
    commands: np.ndarray | None = None


def launch_supported(state: np.ndarray, *, locked: bool = False) -> bool:
    """First integration scope: airborne normal control, outside hook lock.

    Ground launch/umbrella/sprint support must be validated before expansion.
    A caller must also verify the target, ray and every trajectory's safety.
    """
    state = np.asarray(state, dtype=float).reshape(km.K)
    return bool(not locked and state[km.GROUND] <= 0 and int(state[km.MODE]) == km.M_NORMAL
                and state[km.WF_PH] < 0 and abs(state[km.GS] - 1.) < 1e-6
                and abs(state[km.TS] - 1.) < 1e-6)


def control_state(params, hook, terrain=None, *, alpha=None) -> np.ndarray:
    """The observed control edge, using h2 ClawStrike._ctrl_sim semantics.

    This is an initializer, not a script. Unlike a nail pogo, the forced hook
    bounce grants no invulnerability and starts downspike recovery at .1s.
    """
    return control_states(params, [hook], terrain, alphas=None if alpha is None else [alpha])[:, 0]


def control_states(params, hooks, terrain=None, *, alphas=None):
    """Batch the same h2 recovery initializer; no cross-outcome state sharing."""
    n = len(hooks)
    starts = np.stack([km.initial_state(params, h.x_stop, h.y_hold, ground=False, facing=h.d)
                       for h in hooks], axis=1)
    starts[km.ATK_CD] = sk.CLAW_ATK_CD + params.frame_time
    result = km.rollout(starts, np.zeros((n, 1), np.int64), params, terrain,
                        events=np.full((n, 1), km.EV_POGO, np.int64)).final.copy()
    result[km.INV_T] = 0.
    result[km.DS_REC] = .1 + params.frame_time
    if alphas is not None:
        result[km.ALPHA] = result[km.ALO] = result[km.AHI] = np.asarray(alphas)
    return result


def hook_variants(state: np.ndarray, direction: int, iid: int, boxes: np.ndarray) -> list:
    """All existing hook timings / physics phases and both rendered endpoints.

    State is the free-flight state at the end of press-frame physics, before
    entering Harpoon. Target boxes start at that same frame. These trajectories
    end at control; attack acceptance and post-control paths require separate
    checks. An unsuccessful ray stays unsuccessful, never a safe empty path.
    """
    state = np.asarray(state, dtype=float).reshape(km.K)
    out = []
    seen = {}
    phase_steps = {phase: [sk.steps_of(k, phase) for k in range(1, 41)] for phase in range(6)}
    antics = {phase: hero2.claw_unhooked(float(state[km.PX]), float(state[km.PY]) - sk.FOOT,
                                        float(state[km.VX]), float(state[km.VY]), direction, steps)
              for phase, steps in phase_steps.items()}
    for timing, phase, max_steps in product(sk.HOOK_VARIANTS, range(6), (5, 6)):
        steps = phase_steps[phase]
        # The FSM's .1s dash spans five FixedUpdates at .02s, with
        # the boundary step included in the longer timing outcome.
        hook = sk.claw_hook(state, 0, direction, iid, boxes, timing, phase,
                            discrete_stop=True, hold_steps=sum(steps[:sk.HOOK_THROW_F]),
                            dash_max_steps=max_steps, dash_damager=True, dash_motion_lag=1)
        hook.variant = f"{timing.name}/phase{phase}/steps{max_steps}"
        if not hook.ok:
            out.append(hook)
            continue
        antic = antics[phase]
        physical = hook.pos.copy()
        throw = sk.HOOK_THROW_F
        physical[:throw + 1, 1] = antic.bb[:throw + 1] + sk.FOOT
        physical[throw + 1:, 1] = antic.bb[throw] + sk.FOOT
        # Equal positions need not have the same future FixedUpdate clock.
        # Never merge phases merely because their hook positions coincide.
        identity = (phase, hook.ctrl, hook.x_stop, hook.y_hold, physical.tobytes())
        if identity in seen:
            for rendered_hook in seen[identity]:
                tag = rendered_hook.variant.rsplit("/", 1)[1]
                rendered_hook.alias_variants.append(f"{hook.variant}/{tag}")
            continue
        moved = np.r_[False, np.asarray(steps[:len(physical) - 1], bool)]
        latest = np.maximum.accumulate(np.where(moved, np.arange(len(physical)), 0))
        before = physical[np.maximum(latest - 1, 0)].copy()
        after = physical[latest].copy()
        before[latest == 0] = state[[km.QX, km.QY]]
        after[latest == 0] = state[[km.SX, km.SY]]
        seen[identity] = []
        for tag, rendered in (("q", before), ("s", after)):
            rendered_hook = replace(hook, variant=f"{hook.variant}/render{tag}",
                                    pos=np.asarray(rendered), y_hold=float(physical[-1, 1]))
            # Physical pose remains explicit for future rollout splicing;
            # x_stop / y_hold are physics, pos is rendered transform.
            rendered_hook.physical = physical
            rendered_hook.physics_phase = phase
            rendered_hook.alias_variants = [rendered_hook.variant]
            seen[identity].append(rendered_hook)
            out.append(rendered_hook)
    return out


@numba.njit(cache=True)
def _pogo_clock(alphas, events, dt, fdt):
    """Eight FixedUpdates AFTER a contact; reset is after that frame's physics.

    Three phase clocks match the ordinary bounds lanes (nominal, low, high).
    Timing-threshold variants share these clocks in this normal-time scope.
    """
    n, V, T = alphas.shape[0], alphas.shape[1], events.shape[1]
    protected = np.zeros((n, V, T + 1), np.bool_)
    for q in range(n):
        for v in range(V):
            alpha, left = alphas[q, v], 0
            for t in range(T):
                a = alpha + dt / fdt
                steps = int(np.floor(a + 1e-9))
                if steps > 1:
                    raise ValueError("multi-step contact clock not validated")
                alpha = min(max(a - steps, 0.), 1.)
                left = max(left - steps, 0)
                if events[q, t] & km.EV_POGO:
                    left = 8
                protected[q, v, t + 1] = left > 0
    return protected


def pogo_protection(starts, events, params):
    """Nominal / every-lane / any-lane protection, independent of motion hulls."""
    starts = np.asarray(starts).reshape(km.K, -1)
    clocks = starts[[km.ALPHA, km.ALO, km.AHI, km.TS, km.WF_PH, km.WF_S]]
    if (not np.isfinite(clocks).all() or not np.isfinite([params.frame_time, params.fdt]).all()
            or params.frame_time <= 0 or params.fdt <= 0
            or np.any(starts[km.ALPHA] < 0) or np.any(starts[km.ALPHA] > 1)
            or np.any(starts[km.ALO] < 0) or np.any(starts[km.AHI] > 1)
            or np.any(starts[km.ALO] > starts[km.AHI])):
        raise ValueError("invalid pogo physics clock")
    if (np.any(np.abs(starts[km.TS] - 1.) > 1e-6)
            or np.any(starts[km.WF_PH] >= 0)
            or np.any(np.abs(starts[km.WF_S] - 1.) > 1e-6)):
        raise ValueError("pogo physics clock requires normal time")
    ev = np.asarray(events, np.int64)
    if (ev.ndim != 2 or ev.shape[0] != starts.shape[1] or np.any(ev & ~km.EV_POGO)
            or np.any(np.count_nonzero(ev & km.EV_POGO, axis=1) > 1)):
        raise ValueError("unsupported pogo events")
    alphas = np.stack((starts[km.ALPHA], np.maximum(starts[km.ALO] - params.alpha_margin, 0.),
                       starts[km.AHI] + params.alpha_margin), axis=1)
    dt = float(np.float32(params.frame_time))
    protected = _pogo_clock(alphas, ev, dt, params.fdt)
    return protected[:, 0], protected.all(axis=1), protected.any(axis=1)


def _recovery_rollout(starts, commands, params, terrain, events, threads):
    if not np.any(events & km.EV_POGO):
        return km.rollout(starts, commands, params, terrain, events=events,
                          variants="bounds", threads=threads)
    nominal, every, any_lane = pogo_protection(starts, events, params)
    # The common h2 timer stays untouched. Only this experimental component
    # replaces its pogo timer with the measured physics-step protection.
    motion_params = replace(params, pogo_invul=0.)
    ro = km.rollout(starts, commands, motion_params, terrain, events=events,
                    variants="bounds", threads=threads)
    ro.flags |= np.where(nominal, km.F_INVULN, 0)
    ro.flags_all |= np.where(every, km.F_INVULN, 0)
    ro.flags_any |= np.where(any_lane, km.F_INVULN, 0)
    return ro


def rollout(state, masks, params, terrain, boxes, iid, *, events=None, threads=1):
    """Splice one fixed synchronous row: normal prefix, hook, normal recovery.

    Returns one Rollout row per supported hook outcome. Every ray must meet,
    the hook must finish before this horizon, and attacks during the block are
    rejected. There is no key executor or contingent continuation here.
    """
    from ssbot.ipc.framing import mask

    commands = np.asarray(masks, np.int64).reshape(-1)
    claw = mask("clawline")
    down_attack = mask("attack")
    on = (commands & claw) != 0
    edges = np.flatnonzero(on & ~np.r_[False, on[:-1]])
    if len(edges) != 1:
        raise ValueError("one claw press edge required")
    p = int(edges[0]) + 1
    T = len(commands)
    boxes = np.asarray(boxes, float)
    if boxes.ndim != 2 or boxes.shape[1] != 4 or len(boxes) < p + 63:
        raise ValueError("complete target-box horizon required")
    prefix = commands[:p].copy()
    prefix[-1] &= ~claw
    pre = km.rollout(state, prefix[None], params, terrain, variants="bounds", threads=threads)
    prefixes, hooks, seen = [], [], set()
    for v, variant in enumerate(pre.variants or km.NOMINAL):
        alternative = pre if v == 0 else km.rollout(state, prefix[None], params, terrain,
                                                   variants=(variant,), threads=threads)
        free = alternative.final[:, 0]
        key = free.tobytes()
        if key in seen:
            continue
        seen.add(key)
        if not launch_supported(free) or free[km.ATTACKING] > 0:
            raise ValueError("unsupported launch state in a prefix outcome")
        # The wire's direction decides the throw, not the desired target.
        left, right = bool(commands[p - 1] & km.B_LEFT), bool(commands[p - 1] & km.B_RIGHT)
        if left and right:
            raise ValueError("ambiguous claw direction")
        direction = (-1 if left else 1) if left or right else (1 if free[km.FACE] >= 0 else -1)
        index = len(prefixes)
        prefixes.append(alternative)
        for hook in hook_variants(free, direction, iid, boxes[p:]):
            hook.prefix_index = index
            hook.variant = f"prefix{index}/{hook.variant}"
            hooks.append(hook)
    if not hooks or any(not h.ok for h in hooks):
        raise ValueError("not every hook ray is supported")
    controls = np.array([p + h.ctrl for h in hooks], np.int64)
    if controls.max() >= T:
        raise ValueError("hook not over before row endpoint")
    for c in controls:
        if np.any(commands[p:int(c)] & down_attack):
            raise ValueError("attack held inside uncancellable hook")
    n = len(hooks)
    ev = np.zeros((n, T), np.int64) if events is None else np.asarray(events, np.int64)
    if ev.ndim == 1:
        ev = np.broadcast_to(ev, (n, T))
    if ev.shape != (n, T) or np.any(ev[:, :int(controls.max())]):
        raise ValueError("unsupported event inside hook/prefix")
    # Group post-control states by their frame: variable-length suffixes keep
    # an exact endpoint state for the ordinary h2 escape checks.
    post = {}
    initial = {}
    for c in sorted(set(controls.tolist())):
        rows = np.flatnonzero(controls == c)
        unique, inverse = [], []
        for q in rows:
            h = hooks[int(q)]
            # steps_of's zero step is (j + phase) % 6 == 5. Its
            # initial accumulator lies in this sixth of a physics step.
            alpha0 = ((4 - h.physics_phase) % 6 + .5) / 6.0
            alpha = (alpha0 + h.ctrl * params.frame_time / params.fdt) % 1.0
            key = (h.x_stop, h.y_hold, h.d, alpha, bytes(ev[q, c:]))
            keys = [x[0] for x in unique]
            if key not in keys:
                unique.append((key, h, int(q), alpha))
            inverse.append([x[0] for x in unique].index(key))
        alphas = np.array([x[3] for x in unique])
        starts = control_states(params, [x[1] for x in unique], terrain, alphas=alphas)
        starts[km.ALO] = np.maximum(0., alphas - 1 / 12)
        starts[km.AHI] = np.minimum(1., alphas + 1 / 12)
        cmds = np.broadcast_to(commands[c:], (len(unique), T - c)).copy()
        suffix_events = np.stack([ev[x[2], c:] for x in unique])
        ro = _recovery_rollout(starts, cmds, params, terrain, suffix_events, threads)
        for j, q in enumerate(rows):
            post[int(q)] = (ro, inverse[j], c)
            initial[int(q)] = starts[:, inverse[j]]
    arrays = {nm: [] for nm in ("phys", "pos", "vel", "mode", "flags", "box", "bound", "flags_all", "flags_any")}
    finals = []
    for q, h in enumerate(hooks):
        ro, j, c = post[q]
        before_hook = prefixes[h.prefix_index]
        m = h.ctrl
        physical = h.physical[1:]
        box = np.column_stack((physical[:, 0] - params.half_width, physical[:, 1] - params.foot,
                               physical[:, 0] + params.half_width, physical[:, 1] + params.head))
        speed = np.diff(h.physical, axis=0) / params.fdt
        mode = np.full(m, km.M_NORMAL, np.int64)
        flags = np.full(m, km.F_RELINQ | km.F_NO_INPUT, np.int64)
        bound = box + np.array([-COMPONENT_MARGIN_U, -COMPONENT_MARGIN_U,
                                COMPONENT_MARGIN_U, COMPONENT_MARGIN_U])
        middle = {"phys": physical, "pos": h.pos[1:], "vel": speed, "mode": mode,
                  "flags": flags, "box": box, "bound": bound,
                  "flags_all": flags, "flags_any": flags}
        for nm in arrays:
            tail_values = getattr(ro, nm)
            if tail_values is None:
                tail_values = ro.box if nm == "bound" else ro.flags
            tail = tail_values[j, 1:]
            if nm == "bound":
                # The component's positional residual does not disappear when
                # normal control resumes; carry it into subsequent checks.
                tail = tail + np.array([-COMPONENT_MARGIN_U, -COMPONENT_MARGIN_U,
                                        COMPONENT_MARGIN_U, COMPONENT_MARGIN_U])
            head_values = getattr(before_hook, nm)
            if head_values is None:
                head_values = before_hook.box if nm == "bound" else before_hook.flags
            arrays[nm].append(np.concatenate((head_values[0], middle[nm], tail), axis=0))
        finals.append(ro.final[:, j])
    return ClawRollout(**{nm: np.stack(values) for nm, values in arrays.items()},
                       final=np.stack(finals, axis=1), hooks=hooks,
                       control_frames=controls, control_states=initial, launch_frame=p,
                       commands=commands.copy())



def with_events(base: ClawRollout, params, terrain, events, *, threads=1, commands=None):
    """Re-roll post-control physics of this exact fixed row, retaining its hook.

    Events cannot change the hook or its prefix. Every outcome keeps its own
    recovery pose, physics phase and timing bounds. No safety verdict is reused.
    """
    if base.commands is None or base.control_frames is None:
        raise ValueError("fixed row commands and recovery states required")
    if commands is None:
        commands = base.commands
    else:
        from ssbot.ipc.framing import mask
        commands = np.asarray(commands, np.int64).reshape(-1)
        p = base.launch_frame
        claw = mask("clawline")
        if (len(commands) <= int(base.control_frames.max())
                or not np.array_equal(commands[:p], base.commands[:p])
                or not np.array_equal((commands & claw) != 0, (base.commands[:len(commands)] & claw) != 0)):
            raise ValueError("changed hook/prefix or unsupported endpoint")
        for c in base.control_frames:
            if np.any(commands[p:int(c)] & km.B_ATTACK):
                raise ValueError("attack held inside uncancellable hook")
    n, T = len(base.hooks), len(commands)
    ev = np.asarray(events, np.int64)
    if ev.ndim == 1:
        ev = np.broadcast_to(ev, (n, T))
    if ev.shape != (n, T) or np.any(ev[:, :int(base.control_frames.max())]):
        raise ValueError("unsupported event inside hook/prefix")
    groups = {}
    for q, c in enumerate(base.control_frames):
        state = base.control_states[q]
        key = (int(c), state.tobytes(), ev[q, int(c):].tobytes())
        groups.setdefault(int(c), {}).setdefault(key, []).append(q)
    names = ("phys", "pos", "vel", "mode", "flags", "box", "bound", "flags_all", "flags_any")
    arrays = {nm: np.empty((n, T + 1) + getattr(base, nm).shape[2:],
                           dtype=getattr(base, nm).dtype) for nm in names}
    final = np.empty_like(base.final)
    for c, by_state in groups.items():
        row_groups = list(by_state.values())
        first = [qs[0] for qs in row_groups]
        starts = np.stack([base.control_states[q] for q in first], axis=1)
        masks = np.broadcast_to(commands[c:], (len(first), T - c)).copy()
        ro = _recovery_rollout(starts, masks, params, terrain, ev[first, c:].copy(), threads)
        for j, qs in enumerate(row_groups):
            for nm in names:
                tail = getattr(ro, nm)[j, 1:]
                if nm == "bound":
                    tail = tail + np.array([-COMPONENT_MARGIN_U, -COMPONENT_MARGIN_U,
                                            COMPONENT_MARGIN_U, COMPONENT_MARGIN_U])
                for q in qs:
                    arrays[nm][q, :c + 1] = getattr(base, nm)[q, :c + 1]
                    arrays[nm][q, c + 1:] = tail
            final[:, qs] = ro.final[:, j:j + 1]
    return ClawRollout(**arrays, final=final, hooks=base.hooks,
                       control_frames=base.control_frames, control_states=base.control_states,
                       launch_frame=base.launch_frame, commands=commands.copy())



def with_commands(base: ClawRollout, commands, params, terrain, *, threads=1):
    """Reuse an identical hook with new post-control keys, never a verdict."""
    ev = np.zeros((len(base.hooks), len(commands)), np.int64)
    return with_events(base, params, terrain, ev, threads=threads, commands=commands)
