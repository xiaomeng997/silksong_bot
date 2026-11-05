"""Targeted face hook: a sent / in-flight rune_transfer face hook's current step, and its early-jump admission.

Two existing-model helpers for the transfer links (claw / claw_lock). Neither certifies a hook, a hit, a ride or a
flight; both keep "unknown" explicit (GeometryUnavailable, or ok False with why).

step_paths / step_scan
    While the same Move's CLAW is SENT (B2 watch sent_targets) or its Harpoon SEEN, K's two-frame free flight is not
    her motion (K does not simulate the Clawline). The step's rows after the press follow the hooked-Clawline model
    as knife_chain_nominal._nominal_hook calls it (map2.strike.claw_hook: hero2's antic drift and hold, the Throw
    freeze, the hooked dash stopped by the Harpoon Dash Damager on the body, control), anchored on the actual rows at
    or before the press, and go through the same B2 all-owner scan: other owners, delayed hazards (small runes included),
    unknown occupancy; no invulnerability and no protected frame. Variants, not a search: the press (seen, else sent
    + 0 .. 2 late), each existing dash timing (strike.HOOK_VARIANTS early / late and the B2 nominal profile), every
    physics-step phase class, the observed body still or retreating at the bound. The unhooked (empty-needle) branch
    is never used for this targeted hook.

early_jump
    One expansion of the existing jump recipe (transfer.render + air.model_path) with the jump at the NEXT tick's
    first mask frame, and the first later decision on it whose aimed hook passes transfer.face_hook_check from the
    same observation (its retreat reserve counted from that decision, the bomb rows re-based to it). Cached in the
    Run: an ok entry makes the next tick jump without recomputing (nothing is built on a first-J tick); a failed one
    waits for the expansion's own reach deficit at the observed approach speed (at most one expansion horizon) or for
    a new target state.
"""
from dataclasses import replace
from functools import lru_cache
import math

import numpy as np

from ssbot.knowledge import kinematics as K
from .knife_chain_format import MASK_NAMES as B
from .knife_chain_geometry import GeometryUnavailable
from .knife_chain_commitment import ContactScan

TRACK_F = 62             # frames after a press the model's boxes cover (map2.strike.claw_hook stops by P+61)


def _variants():
    """(dash frame, control after the stop): strike.HOOK_VARIANTS and the B2 nominal hook profile."""
    from ssbot.map2 import strike as SK
    from .knife_chain_nominal import NominalProfile
    nominal = NominalProfile()
    return tuple(sorted({(v.dash_f, v.ctrl_after) for v in SK.HOOK_VARIANTS}
                        | {(nominal.hook_dash_frame, nominal.hook_control_after)}))


def press_anchor(sim, toward, F0, enemy):
    """Decision-time inputs of the hook model, kept in the Run: the free-flight press rows (box centre x, box bottom,
    vx, vy) of a press on either CLAW slot applied 0 .. HOOK_LATE_F frames late (P .. P+1+HOOK_LATE_F), the observed
    target body and its retreat bound."""
    from .knife_chain_transfer import HOOK_PRESS_AFTER_F, HOOK_LATE_F, retreat_reserve, body_box
    tk = B["R"] if toward > 0 else B["L"]
    P = int(F0) + HOOK_PRESS_AFTER_F
    slots = HOOK_LATE_F + 2
    ro = sim.roll(np.full((1, HOOK_PRESS_AFTER_F + slots), tk, np.int64))
    j0 = sim.off + HOOK_PRESS_AFTER_F
    rows = [[.5 * float(b[0] + b[2]), float(b[1]), float(v[0]), float(v[1])]
            for b, v in zip(ro.box[0, j0:j0 + slots], ro.vel[0, j0:j0 + slots])]
    if len(rows) != slots:
        return None              # no anchor: every later hook step is "unchecked", never a guess
    ft = float(sim.params.frame_time)
    reserve = [float(retreat_reserve(enemy, (P + j - int(sim.f)) * ft, toward)) for j in range(TRACK_F + slots)]
    return {"P": P, "toward": int(toward), "rows": rows, "body": [float(v) for v in body_box(enemy)],
            "iid": int(enemy["iid"]), "reserve": reserve}


@lru_cache(maxsize=32)
def _tracks(row, toward, body, reserve, iid):
    """The model's transform positions per frame from the press (index 0 = P, the free-flight state at P) for every
    variant, deduplicated. A variant the model cannot place raises GeometryUnavailable."""
    from ssbot.knowledge import hero2 as H2
    from ssbot.map2 import strike as SK
    x, bb, vx, vy = row
    S = np.zeros(K.K)
    S[K.PX], S[K.PY], S[K.VX], S[K.VY] = x, bb + SK.FOOT, vx, vy
    b = np.asarray(body, float)
    r = np.asarray(reserve, float)
    worlds = (np.tile(b, (len(r), 1)), b + toward * np.outer(r, [1., 0., 1., 0.]))
    out = {}
    for dash_f, ctrl_after in _variants():
        var = SK.HookVariant("task170", dash_f, 0., ctrl_after)     # the dash damager stops it, not the gap
        for ac in range(6):
            steps = [SK.steps_of(j, ac) for j in range(1, len(r) + 1)]
            antic = H2.claw_unhooked(x, bb, vx, vy, toward, steps)    # its antic heights only, as _nominal_hook
            for boxes in worlds:
                h = SK.claw_hook(S, 0, toward, iid, boxes, var, ac, discrete_stop=True,
                                 hold_steps=sum(steps[:SK.HOOK_THROW_F]), dash_max_steps=SK.DASH_MAX_STEPS,
                                 dash_damager=True, dash_motion_lag=1)
                if not h.ok:
                    raise GeometryUnavailable("transfer hook step unchecked: hooked model " + h.why)
                pos = np.array(h.pos, float)
                t = SK.HOOK_THROW_F
                pos[:t + 1, 1] = antic.bb[:t + 1] + SK.FOOT
                pos[t + 1:, 1] = antic.bb[t] + SK.FOOT
                out.setdefault(pos.round(9).tobytes(), pos)
    return tuple(out.values())


def step_paths(path, v, watch, f):
    """The current external step's variant paths (frames f .. f+2) for a SENT / seen same-Move hook. Rows at or before
    the press stay K's (claw_hook's index 0 is the free flight at P); later rows move from that actual anchor by the
    model's increments. Past the model's control both "at rest" and K's free flight are kept. Unknown raises."""
    from .knife_chain_transfer import HOOK_LATE_F
    a = v.get("hook_press")
    if not isinstance(a, dict):
        raise GeometryUnavailable("transfer hook step unchecked: no press anchor")
    if watch is None:
        raise GeometryUnavailable("transfer hook step unchecked: no hook watch")
    if watch["seen_frame"] is not None:
        presses = (int(watch["seen_frame"]),)
    elif watch["sent_targets"]:
        presses = tuple(min(watch["sent_targets"]) + d for d in range(HOOK_LATE_F + 1))
    else:
        raise GeometryUnavailable("transfer hook step unchecked: no sent CLAW")
    from .knife_chain_transfer import HOOK_LATE_F
    move=watch.get("move");sent=watch.get("sent_targets") or set()
    expected=(int(a["P"]),int(a["P"])+1)
    if (getattr(move,"target_iid",None)!=a.get("iid") or tuple(watch.get("targets",()))!=expected
            or any(type(t) is not int or t not in expected for t in sent)):
        raise GeometryUnavailable("transfer hook step unchecked: same-Move planned slots mismatch")
    if (watch["seen_frame"] is not None and
            not any(0<=int(watch["seen_frame"])-t<=HOOK_LATE_F for t in sent)):
        raise GeometryUnavailable("transfer hook step unchecked: seen hook outside sent-slot late bound")
    box = np.asarray(path.box, float)
    if path.origin != f or box.shape != (3, 4) or not np.isfinite(box).all():
        raise GeometryUnavailable("transfer hook step unchecked: external step rows")
    rows_out, free = {}, False
    for P in presses:
        d = P - int(a["P"])
        if not 0 <= d < len(a["rows"]):
            raise GeometryUnavailable("transfer hook step unchecked: press outside its planned slots")
        r0, t0 = max(0, P - f), max(0, f - P)
        if r0 >= 2:
            free = True          # the press is the step's last frame: K's rows are her motion
            continue
        for tr in _tracks(tuple(a["rows"][d]), int(a["toward"]), tuple(a["body"]),
                          tuple(a["reserve"][d:d + TRACK_F]), int(a["iid"])):
            if t0 >= len(tr) - 1:
                free = True      # the model's control is behind: K's free flight
                continue
            rows = box.copy()
            for i in range(r0 + 1, 3):
                t = t0 + i - r0
                if t >= len(tr):
                    t, free = len(tr) - 1, True      # at rest after the model's control, and K's flight too
                rows[i] = box[r0] + np.tile(tr[t] - tr[t0], 2)
            rows_out.setdefault(rows.round(9).tobytes(), rows)
    zero = {"flags": np.zeros_like(path.flags), "check_flags": np.zeros_like(path.check_flags)}
    out = [replace(path, box=r, stage="transfer_hook_step", **zero,
                   assumptions={**path.assumptions, "basis": "hooked-Clawline model rows after the actual press",
                                "protection": "none", "safety": "current external step only"})
           for r in rows_out.values()]
    if free or not out:
        out.append(replace(path, **zero))
    return out


def step_scan(geo, path, v, watch, f):
    """One ContactScan over every variant path through the same B2 all-owner scan (rejection only)."""
    scans = [geo.scan(q) for q in step_paths(path, v, watch, f)]
    return ContactScan(scans[0].path_ref, min(s.first_frame for s in scans), max(s.last_frame for s in scans),
                       tuple(c for s in scans for c in s.contacts),
                       f"transfer hook step: {len(scans)} variant path(s) of the hooked-Clawline model; "
                       "B2 all-owner scan; no protection", all(s.complete for s in scans))


def early_jump_due(cache, k, target_state):
    """A cached ok expansion jumps on exactly the tick it was computed for (its J at this tick's first mask frame)."""
    return bool(isinstance(cache, dict) and cache.get("ok") and cache.get("jump_k") == k + 2
                and cache.get("state") == target_state)


def early_jump_stale(cache, f, target_state):
    return (not isinstance(cache, dict) or f >= int(cache.get("next_f", f)) or cache.get("state") != target_state)


def early_jump(runner, p, sim, game, state, enemy, bombs, k, link, held_dash):
    """The Run's cache entry for one expansion of the existing jump recipe from the next tick (see the module doc)."""
    from .knife_chain_transfer import (render, face_hook_check, clappers, body_box, control, PROGRAM,
                                       HOOK_PRESS_AFTER_F, HOOK_LATE_F)
    from .knife_chain_air import model_path
    from .holdfilter import hold_filter_jit
    from .air_chain import ChainSim
    cfg = runner.chains[PROGRAM].cfg
    n, f, (st, _) = int(cfg["lookahead_frames"]), int(sim.f), control(enemy)
    toward = 1 if p.side == B["R"] else -1 if p.side == B["L"] else 0
    jump_k = k + 3
    entry = {"f": f, "state": st, "jump_k": jump_k, "ok": False, "why": "", "next_f": f + n}
    if toward == 0:
        entry["why"] = "no approach side"
        return entry
    try:
        bodies = [(e.get("iid"), body_box(e)) for e in clappers(state)]
        body = body_box(enemy)
    except (TypeError, ValueError, OverflowError):
        entry["why"] = "observed bodies unknown"
        return entry
    if body is None:
        entry["why"] = "observed body unknown"
        return entry
    pj = replace(p, jump_k=jump_k, jump_until=jump_k + int(cfg["STOMP"]["jump_hold"]), sprint_jump=bool(held_dash))
    masks = render(runner, pj, k, n, link)
    path = model_path(sim, pj, masks, game)
    full = np.asarray(path.commands, np.int64)
    front = float(body[0] if toward > 0 else body[2])
    hero = state.get("hero") or {}
    rows = None if bombs is None else np.asarray(bombs, float).reshape(-1, 6)
    deficits, reasons = [], {}
    for d in range(1, len(full) - HOOK_PRESS_AFTER_F - HOOK_LATE_F - 1):   # decide at f+d; F0 f+d+2; P f+d+3
        iP = d + 2 + HOOK_PRESS_AFTER_F
        if path.flags[iP] & K.F_GROUND:
            continue
        xP = .5 * float(path.box[iP, 0] + path.box[iP, 2])
        near = (front - xP) * toward                       # her x at P is the recipe's: the claw keys keep its side
        if near < .5:
            break
        # Beyond the B2 identity ray at P, the same check runs with the target that much nearer: a phase that then
        # passes (or only misses the modeled ray) is reach-limited, any other failure is not fixed by approaching.
        shift = max(0., near - 10.5)
        e, bs = (enemy, bodies) if shift == 0. else _nearer(enemy, bodies, toward, shift)
        hold = hold_filter_jit(full[None, :d], sim.hold)[1]
        sd = ChainSim(np.asarray(path.states[:, d], float), full[d:d + 1].copy(), hold, sim.params, sim.terrain,
                      f + d, f + d)
        hd = {**hero, "hero_accepting_input": not bool(path.flags[d] & K.F_NO_INPUT)}
        bd = None
        if rows is not None:
            bd = rows.copy()
            bd[:, 4:6] -= d
        ok, why, info = face_hook_check(sd, hd, e, f + d + 2, toward, bd, bs)
        if ok and shift == 0.:
            entry.update(ok=True, why="ok", next_f=f + 1, decide_f=f + d, press_F=f + d + 3,
                         **{key: float(val) for key, val in info.items()
                            if key in ("ray_margin", "retreat_reserve", "bb_press", "x_press", "held_bb")})
            return entry
        if ok:
            deficits.append(shift)
            why = "beyond the B2 identity ray at P"
        elif why.startswith("face out of the modeled ray"):
            deficits.append(shift - float(info["ray_margin"]))
        reasons[why] = reasons.get(why, 0) + 1
    entry["why"] = "; ".join(f"{w} x{c}" for w, c in reasons.items()) or "no airborne decision in range"
    vel = hero.get("vel") or [0., 0.]
    speed = toward * float(vel[0]) if type(vel[0]) in (int, float) and math.isfinite(vel[0]) else 0.
    if deficits and speed > 0:
        entry["next_f"] = f + max(1, min(n, int(math.ceil(min(deficits) / speed * 60.))))
    entry["deficit"] = min(deficits) if deficits else None
    return entry


def _nearer(enemy, bodies, toward, shift):
    """The observed target (its colliders, transform and body list entry) moved `shift` u toward her, for a deficit."""
    dx = -toward * shift
    e = {**enemy, "pos": [enemy["pos"][0] + dx, *enemy["pos"][1:]],
         "colliders": [{**c, "verts_world": [v + dx if i % 2 == 0 else v for i, v in enumerate(c["verts_world"])]}
                       for c in enemy.get("colliders") or ()]}
    return e, [(i, b if i != enemy["iid"] or b is None else b + np.array([dx, 0., dx, 0.])) for i, b in bodies]
