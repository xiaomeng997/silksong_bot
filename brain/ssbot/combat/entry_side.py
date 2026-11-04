"""Bounded first-side-hit preference: existing rows and checks, no key owner."""
from dataclasses import replace
import numpy as np
from .tactics.modes import EntryAttack
from ssbot.knowledge import kinematics as kin


def target_of(prefs):
    entry = getattr(prefs, "entry_attack", None)
    target = getattr(prefs, "target", None)
    if (not isinstance(entry, EntryAttack) or entry.kind != "side" or entry.target != target
            or target in (getattr(prefs, "no_hit", ()) or ()) or getattr(prefs, "want_bind", False)):
        return None
    weights = (getattr(prefs, "hit_kw", None) or {}).get(target)
    weight = weights[0] if weights is not None else (getattr(prefs, "hit_w", None) or {}).get(target, 1.)
    return target if np.isfinite(weight) and weight > 0 else None


def immediate_set(cs):
    """Move only the existing side first-piece press one slot earlier, once at init.

    Core/movement/other attacks/continuations and the row count stay identical.
    Actual turning, hold filtering, cooldown, acceptance and hit geometry are
    still computed by the ordinary rollout; this does not append A after checks.
    """
    names = list(cs.first_names)
    firsts = [i for i, name in enumerate(names) if name in
              {"ATTACK(side)N", "ATTACK(side)L", "ATTACK(side)R"}]
    rows = np.isin(cs.first, firsts)
    cmd = cs.cmd.copy()
    cmd[rows, :4] &= ~kin.B_ATTACK
    cmd[rows, :3] |= kin.B_ATTACK
    for i in firsts:
        names[i] += "[entry-now]"
    return replace(cs, cmd=cmd, first_names=names)


def hit_times(sc, target, admitted, T1, *, ground_only=False, flags=None):
    """First NEW modelled side contact on this target; no old active-swing credit.

    Scorer first_* already comes from actual model attack-on transitions. A
    different first body, blocked/forbidden hit or ground-only air swing cannot
    promote a row. Missing is tied; safety/commitment/escape keys remain higher.
    """
    times = np.full(len(admitted), T1 + 1, np.int64)
    if target is None:
        return times
    targets = sc.get("targets") or ()
    slots = [i for i, t in enumerate(targets) if t.iid == target
             and not getattr(t, "hazard", False) and not getattr(t, "blocked", False)]
    eligible = (admitted & np.isin(sc["first_t"], slots) & (sc["first_k"] == 1)
                & (sc["first_f"] >= 0) & (sc["hits"] > 0))
    if ground_only:
        k = np.clip(sc["sw_f"] - 1, 0, T1 - 1)
        eligible &= ((sc["sw_f"] >= 1) & (sc["sw_k"] == 1)
                     & ((flags[np.arange(len(times)), k] & kin.F_GROUND) != 0))
    times[eligible] = sc["first_f"][eligible]
    return times
