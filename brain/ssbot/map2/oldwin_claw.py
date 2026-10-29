"""Local hooked-motion support for synchronous old-planner rows.

No search, input owner, or background work. The render endpoints represent the
unknown interpolation fraction between successive physics poses. Callers must
check the full envelope, not choose the most favorable variant.
"""
from __future__ import annotations

from dataclasses import replace
from itertools import product

import numpy as np

from ssbot.knowledge import hero2
from ssbot.knowledge import kinematics as km
from ssbot.map2 import strike as sk


def launch_supported(state: np.ndarray, *, locked: bool = False) -> bool:
    """First integration scope: airborne normal control, outside hook lock.

    Ground launch/umbrella/sprint support must be validated before expansion.
    A caller must also verify the target, ray and every trajectory's safety.
    """
    state = np.asarray(state, dtype=float).reshape(km.K)
    return bool(not locked and state[km.GROUND] <= 0 and int(state[km.MODE]) == km.M_NORMAL)


def hook_variants(state: np.ndarray, direction: int, iid: int, boxes: np.ndarray) -> list:
    """All existing hook timings / physics phases and both rendered endpoints.

    State is the free-flight state at the end of press-frame physics, before
    entering Harpoon. Target boxes start at that same frame. These trajectories
    end at control; attack acceptance and post-control paths require separate
    checks. An unsuccessful ray stays unsuccessful, never a safe empty path.
    """
    state = np.asarray(state, dtype=float).reshape(km.K)
    out = []
    for timing, phase, max_steps in product(sk.HOOK_VARIANTS, range(6), (5, 6)):
        steps = [sk.steps_of(k, phase) for k in range(1, 41)]
        # The FSM's .1s dash spans five FixedUpdates at .02s, with
        # the boundary step included in the longer timing outcome.
        hook = sk.claw_hook(state, 0, direction, iid, boxes, timing, phase,
                            discrete_stop=True, hold_steps=sum(steps[:sk.HOOK_THROW_F]),
                            dash_max_steps=max_steps, dash_damager=True, dash_motion_lag=1)
        hook.variant = f"{timing.name}/phase{phase}/steps{max_steps}"
        if not hook.ok:
            out.append(hook)
            continue
        antic = hero2.claw_unhooked(float(state[km.PX]), float(state[km.PY]) - sk.FOOT,
                                    float(state[km.VX]), float(state[km.VY]), direction, steps)
        physical = hook.pos.copy()
        throw = sk.HOOK_THROW_F
        physical[:throw + 1, 1] = antic.bb[:throw + 1] + sk.FOOT
        physical[throw + 1:, 1] = antic.bb[throw] + sk.FOOT
        q = np.array([state[km.QX], state[km.QY]])
        s = np.array([state[km.SX], state[km.SY]])
        before, after = [q.copy()], [s.copy()]
        for k in range(1, len(physical)):
            if steps[k - 1]:
                q, s = physical[k - 1].copy(), physical[k].copy()
            before.append(q.copy())
            after.append(s.copy())
        for tag, rendered in (("q", before), ("s", after)):
            rendered_hook = replace(hook, variant=f"{hook.variant}/render{tag}",
                                    pos=np.asarray(rendered), y_hold=float(physical[-1, 1]))
            # Physical pose remains explicit for future rollout splicing;
            # x_stop / y_hold are physics, pos is rendered transform.
            rendered_hook.physical = physical
            out.append(rendered_hook)
    return out
