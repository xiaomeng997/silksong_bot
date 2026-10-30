"""Opt-in synchronous Clawline proposals for the old Forum planner.

The table proposes keys. Its contingent certificate is never inherited by a
fixed row. The first scope is one w7 Clapper, normal time, a down contact past
the planner horizon. No executor, worker, handoff or commitment is introduced.
"""
from __future__ import annotations

from dataclasses import replace
import copy
import os
import time

import numpy as np

from ssbot.knowledge import kinematics as km
from ssbot.map2 import oldwin as ow, oldwin_claw as claw
from ssbot.map2 import clapper as cm

ENV = "SSBOT_FORUM_KNIFE_ROWS"
FREE_MIN = 10
MIN_TARGET_HP = 50


def validate_environment(env=None):
    env = os.environ if env is None else env
    required = {"SSBOT_FORUM_WINDOWS": "1", "SSBOT_FORUM_WINDOWS_CORE": "2",
                "SSBOT_FORUM_WINDOWS_PRESS": "0", "SSBOT_FORUM_SLAM_PLAY": "0",
                "SSBOT_FORUM_CLAWSTRIKE": "0", "SSBOT_FORUM_SLAM_PLAY_PREFS": "1",
                "SSBOT_FORUM_TV": "0", "SSBOT_FORUM_HERO2": "1", "SSBOT_FORUM_V2": "1"}
    required.update(SSBOT_FORUM_MAP2="0", SSBOT_FORUM_REFLEX="0")
    bad = {k: (env.get(k), v) for k, v in required.items() if env.get(k, "0") != v}
    if bad:
        raise ValueError(f"{ENV}=1 incompatible configuration: {bad}")


def fixed_keys(macro, direction, *, drift=None):
    """One proposal, not the table's branch-dependent continuation.

    Use the latest stored attack. A common drift is kept; differing drifts
    propose neutral. Every resulting path must be independently checked.
    """
    if macro.family != "cl" or macro.raw is not None:
        raise ValueError("unsupported macro")
    alternatives = macro.cont or (("fixed", macro.k, macro.dd),)
    if any(k is None for _, k, _ in alternatives):
        raise ValueError("hook-only macro has no down strike")
    k = max(int(k) for _, k, _ in alternatives)
    drifts = {int(dd) for _, _, dd in alternatives}
    dd = next(iter(drifts)) if len(drifts) == 1 else 0
    fixed = replace(macro, k=k, dd=dd if drift is None else int(drift), cont=())
    # Use the existing oldwin table adapter; the combat layer adds no reflex controller.
    raw = ow.rx.render(fixed, direction)
    commands = np.concatenate((raw.pre, raw.post))
    p = len(raw.pre)
    commands[p - 1:p + 1] |= ow.M_CLAW | (km.B_RIGHT if direction > 0 else km.B_LEFT)
    return commands, p, k, fixed


def align_throw(row, prefix, hold, press, direction, length):
    """Bounded fixed-key proposals: turn must reach the wire before the throw.

    A delayed claw keeps the fixed attack time. Its new launch, recovery,
    FREE_MIN, contacts and whole path still require independent checks.
    """
    from ssbot.combat.holdfilter import hold_filter_jit
    row=np.asarray(row,np.int64);prefix=np.asarray(prefix,np.int64)
    want=km.B_RIGHT if direction>0 else km.B_LEFT
    other=km.B_LEFT if direction>0 else km.B_RIGHT
    for delay in range(3):
        candidate=row.copy()
        if delay:
            candidate &= ~ow.M_CLAW
            a=int(press)-1+delay;b=a+2
            if b>len(candidate):continue
            candidate[a:b] &= ~other
            candidate[a:b] |= ow.M_CLAW|want
        raw=np.zeros(length,np.int64)
        if len(prefix)+len(candidate)>length:raise ValueError("fixed row exceeds horizon")
        raw[:len(prefix)]=prefix;raw[len(prefix):len(prefix)+len(candidate)]=candidate
        latched,_=hold_filter_jit(raw[None],hold);wire=latched[0]
        active=(wire&ow.M_CLAW)!=0
        edges=np.flatnonzero(active&~np.r_[False,active[:-1]])
        launch=len(prefix)+int(press)+delay
        if (len(edges)==1 and edges[0]+1==launch and wire[launch-1]&want
                and not wire[launch-1]&other):
            return candidate,int(press)+delay,raw,latched,delay
    raise ValueError("latched throw direction unsupported")


def envelope(rollouts, length=None):
    # Different worlds may reference the same immutable motion result. The
    # union of identical objects is unchanged; keep every distinct outcome.
    rollouts = list({id(r): r for r in rollouts}.values())
    bounds = np.concatenate([r.bound[:, :length] for r in rollouts])
    flags = np.concatenate([r.flags_all[:, :length] for r in rollouts])
    bound = np.concatenate((bounds[..., :2].min(axis=0), bounds[..., 2:].max(axis=0)), axis=1)
    return bound, np.bitwise_and.reduce(flags, axis=0)


def slam_body_paths(observation, paths, knowledge):
    """Replace a carried box's shape using the existing Slam animation data.

    Keep the old move-template translations. Intersect the body boxes over
    every supported state-duration outcome; after this Slam ends the body is
    unknown. This predicts no new enemy decision and removes no danger.
    """
    if observation.st != "Slam Antic":
        raise ValueError("unsupported body timeline")
    horizon = len(paths[0])
    active = {(observation.st, int(observation.j))}
    local = []
    for _ in range(horizon):
        boxes = []
        for st, j in active:
            if st == "Idle":
                boxes.append(np.full(4, np.nan))
                continue
            for jj in range(max(0, j - 1), j + 2):
                b = knowledge.box(st, jj)
                xa, xb = observation.face * b[0], observation.face * b[1]
                boxes.append([min(xa, xb), b[2], max(xa, xb), b[3]])
        bs = np.asarray(boxes)
        common = np.array([bs[:, 0].max(), bs[:, 1].max(), bs[:, 2].min(), bs[:, 3].min()])
        if not np.isfinite(common).all() or common[0] >= common[2] or common[1] >= common[3]:
            common[:] = np.nan
        local.append(common)
        following = set()
        for st, j in active:
            if st == "Idle":
                following.add((st, 0))
                continue
            duration = knowledge.durations(st)
            if duration is None:
                raise ValueError("missing Slam duration")
            lo, _, hi = duration
            if j + 1 < hi:
                following.add((st, j + 1))
            if j + 1 >= lo:
                successor = "Slam 2" if st == "Slam 1" else cm.NEXT.get(st)
                if successor is None:
                    raise ValueError("unknown Slam successor")
                following.add((successor, 0))
        active = following
    local = np.asarray(local)
    out = []
    for path in paths:
        displacement = path - path[0]
        root = np.array([observation.x, observation.y, observation.x, observation.y])
        out.append(local + root + displacement)
    return out


def slam_body_variants(observation, paths, knowledge, *, outer=False):
    """Coherent alternatives over the existing duration domain, for contact audits.

    Each yields (duration tuple, body path). No timing alternative is dropped:
    their pointwise intersection equals slam_body_paths. outer=True instead
    encloses the same animation samples, for earliest-possible contact bounds.
    Runtime promotion is separate.
    """
    from itertools import product
    states=("Slam Antic","Slam 0","Slam 1","Slam 2","Slam Recover")
    if observation.st!="Slam Antic":raise ValueError("unsupported body timeline")
    domains=[]
    for st in states:
        dur=knowledge.durations(st)
        if dur is None:raise ValueError("missing Slam duration")
        lo,_,hi=dur
        domains.append(range(lo,hi+1))
    length=len(paths[0]);root=np.array([observation.x,observation.y]*2)
    for durations in product(*domains):
        if observation.j>=durations[0]:continue
        si=0;j=int(observation.j);local=[]
        for _ in range(length):
            if si==len(states):local.append(np.full(4,np.nan));continue
            boxes=[]
            for q in range(max(0,j-1),j+2):
                b=knowledge.box(states[si],q)
                x0,x1=observation.face*b[0],observation.face*b[1]
                boxes.append([min(x0,x1),b[2],max(x0,x1),b[3]])
            boxes=np.asarray(boxes)
            b=(np.r_[boxes[:,:2].min(axis=0),boxes[:,2:].max(axis=0)] if outer else
               np.r_[boxes[:,:2].max(axis=0),boxes[:,2:].min(axis=0)])
            if b[0]>=b[2] or b[1]>=b[3]:b[:]=np.nan
            local.append(b)
            j+=1
            if j>=durations[si]:si+=1;j=0
        local=np.asarray(local)
        for path in paths:yield durations,local+root+(path-path[0])


def _extend_forecast(forecast, through_frame):
    """Extend this tick's existing support to the complete checked tail.

    Preserve every original sample and owner. One extra endpoint uses the
    same tracker, margins and escape rules; no new enemy model or verdict.
    """
    from ssbot.combat import forum_v2
    rs = forecast.rs
    samples = getattr(rs, "samples", ())
    if not samples or max(samples) + rs.k_shift >= through_frame:
        return forecast
    needed = int(through_frame) - rs.k_shift
    if needed > 120 or not isinstance(rs, forum_v2.RangeSupport):
        raise ValueError("unsupported safety horizon")
    extra = forum_v2.RangeSupport.build(rs.trk, samples=(needed,), k_shift=rs.k_shift,
                inner_fc=rs.fc._inner, margin_mode=rs.margin_mode, canvas=rs.cv, focus=rs.focus)
    layout = forum_v2.LayerSupport(rs.cv, rs.samples + (needed,), rs.k_shift, rs.fc._inner)
    extended = copy.copy(rs)
    extended.samples, extended._lo, extended._hi = layout.samples, layout._lo, layout._hi
    extended.stack = np.concatenate((rs.stack, extra.stack))
    if rs.stack_esc is not None or extra.stack_esc is not None:
        extended.stack_esc = np.concatenate((rs.stack if rs.stack_esc is None else rs.stack_esc,
                                            extra.stack if extra.stack_esc is None else extra.stack_esc))
    offset = len(rs.samples)
    extended.raw = {**rs.raw, **{si + offset: parts for si, parts in extra.raw.items()}}
    extended.layers = {**rs.layers, **{si + offset: parts for si, parts in extra.layers.items()}}
    if rs.stack_dash is not None or extra.stack_dash is not None:
        extended.stack_dash = np.concatenate((np.zeros_like(rs.stack) if rs.stack_dash is None else rs.stack_dash,
                                              np.zeros_like(extra.stack) if extra.stack_dash is None else extra.stack_dash))
    return forum_v2.V2Forecast(forecast._inner, extended)


def _slam_clock_support(rs, iid):
    """Resolve the started Slam's critical bins on its one Antic clock.

    Audit prototype: not promoted into append_rows (cost/geometry gates open).
    Other owners and this owner's spawned hazards keep their original sparse
    occupancy. The core
    keeps the existing spatial template/margin, with the previous game bin
    included for callbacks delivered after the exported arc turns off.
    """
    from ssbot.combat import attack_range as ar, forum_v2 as v2
    if not isinstance(rs, v2.RangeSupport) or rs.focus != iid:
        raise ValueError("Slam clock needs the focused RangeSupport")
    tk_name, _, inst = rs.trk.now[iid]
    if tk_name != v2.CLAPPER or inst is None or inst.fam != "CC_SLAM":
        raise ValueError("Slam clock needs a started CC_SLAM")
    tab = rs.trk.tables[tk_name]
    tp = tab.templates[("CC_SLAM", "main")]
    if rs.haz_raw:
        raise ValueError("unsupported split hazard support")
    if tp.sst is None:
        raise ValueError("missing Slam state clock")
    critical = [b for b, states in enumerate(tp.sst)
                if {"Slam 0", "Slam 1", "Slam 2"}.intersection(states)]
    if not critical:
        raise ValueError("missing Slam critical bins")
    age = ar.bin_of(rs.trk.T - inst.t0)
    # Include a clear endpoint AFTER the last swept bin. Otherwise a last
    # live raster would be held again until the next sparse sample.
    lo, hi = min(critical) - age - 1, max(critical) - age + 2
    dense = range(max(0, lo), min(rs.samples[-1], hi) + 1)
    samples = tuple(sorted(set(rs.samples).union(dense)))
    layer = v2.LayerSupport(rs.cv, samples, rs.k_shift, rs.fc._inner)
    estimates = {}
    def estimate(k):
        if k not in estimates:
            e = rs.trk.estimate(iid, k)
            if e is None or e.core is None:
                raise ValueError("missing separable Slam core")
            estimates[k] = e
        return estimates[k]
    # A core can be replaced only when the original piece is exactly the
    # tracker's complete estimate. Unknown additions must remain a rejection.
    for si, k in enumerate(rs.samples):
        own = [p for p in rs.raw[si] if p[0] == iid]
        if len(own) != 1 or any(p[0] == iid for p in rs.layers[si]):
            raise ValueError("unrecognized Slam support pieces")
        e = estimate(k)
        c, x, y = v2.coarse(e.raw, tab.cell, rs.cv.cell)
        p = own[0]
        if (p[2:4] != (x, y) or not np.array_equal(p[1], c)
                or p[4] != rs.m_of(iid, tk_name, k)):
            raise ValueError("Slam support does not match its tracker")
    for si, k in enumerate(samples):
        a, b = int(rs._lo[k]), int(rs._hi[k])
        for old in sorted({a, b}):
            for owner, mask, x, y in rs.layers[old]:
                layer.add(si, owner, mask, x, y)
            for owner, c, x, y, m, em in rs.raw[old]:
                if owner != iid or k < lo or k > hi:
                    layer.add_raw(si, owner, c, x, y, m, em)
                else:
                    haz = estimate(rs.samples[old]).haz
                    if haz is not None and haz.m.size and haz.m.any():
                        c, x, y = v2.coarse(haz, tab.cell, rs.cv.cell)
                        layer.add_raw(si, owner, c, x, y, m, em)
        if lo <= k <= hi:
            for q in sorted({max(0, k - 1), k}):
                c, x, y = v2.coarse(estimate(q).core, tab.cell, rs.cv.cell)
                m = rs.m_of(iid, tk_name, q)
                layer.add_raw(si, iid, c, x, y, m,
                              m if k + rs.k_shift >= v2.ESC_FROM_K else None)
    layer.finish()
    out = copy.copy(rs)
    for name in ("samples", "_lo", "_hi", "layers", "raw", "stack", "stack_esc"):
        setattr(out, name, getattr(layer, name))
    # These pointwise clocks are unchanged; keep bombs, pending aims and the
    # stricter dash field. No old verdict or future observed clock is reused.
    if rs.stack_dash is not None:
        ks = np.asarray(samples)
        out.stack_dash = rs.stack_dash[rs._lo[ks]] | rs.stack_dash[rs._hi[ks]]
    out.knife_slam_clock = {"iid": iid, "age": age, "dense_from": lo,
                            "dense_through": hi, "previous_game_bin": True}
    return out


def safety_forecast(forecast, through_frame, *, slam_iid=None):
    """Complete tail coverage, then knife-only committed Slam timing."""
    extended = _extend_forecast(forecast, through_frame)
    if slam_iid is None:
        return extended
    from ssbot.combat import forum_v2
    return forum_v2.V2Forecast(extended._inner, _slam_clock_support(extended.rs, slam_iid))


def _clear(planner, forecast, rollout, audit=None, label="path"):
    """Use the planner's hull sampler, including its too-wide rejection."""
    bounds = rollout.bound
    flags = rollout.flags_all
    tk = np.arange(bounds.shape[1]) * planner.params.frame_time
    skip = (flags & km.F_INVULN) != 0
    occ = planner._contacts(forecast, bounds, tk, skip)
    if audit is not None:
        frames = np.flatnonzero(occ.any(axis=0))
        audit[label] = {"passed": not bool(len(frames)),
                        "first_contact": None if not len(frames) else int(frames[0]),
                        "last_contact": None if not len(frames) else int(frames[-1])}
    return not bool(occ.any())


def common_escape(planner, forecast, paths, row, prefix, hold, horizon):
    """Historical H-abort prototype, retained only for old diagnostic callers.

    Native proposals use forum_knife_hit.common_escape, never this function.
    One escape command must pass for every hook / post-control outcome.

    Continue from the stored control edges, preserving suffix timing variants.
    This avoids collapsing their end states to the nominal rollout state.
    """
    from ssbot.combat import forum_v2
    from ssbot.combat.holdfilter import hold_filter_jit

    audited_end = max([horizon] + [r.flags.shape[1] - 1 for r in paths if hasattr(r, "flags")])
    length = max(forum_v2.ESC_F, audited_end - horizon)
    samples = getattr(forecast.rs, "samples", None)
    if samples and max(samples) + getattr(forecast.rs, "k_shift", 0) < horizon + length:
        raise ValueError("escape support horizon unavailable")
    options = planner._esc_cmds(length)
    full = np.concatenate((prefix, row[:horizon - len(prefix)]))
    filtered, end_hold = hold_filter_jit(full[None], hold)
    full = filtered[0]
    escape_lat, _ = hold_filter_jit(options, end_hold)
    for e, suffix in enumerate(escape_lat):
        clear = True
        for r in paths:
            groups = {}
            for q, c in enumerate(r.control_frames):
                state = r.control_states[q]
                key = (int(c), state.tobytes())
                groups[key] = (int(c), state)
            for c, state in groups.values():
                commands = np.concatenate((full[c:], suffix))
                rr = km.rollout(state, commands[None], planner.params, planner.terrain,
                                variants="bounds", threads=planner.cfg.threads)
                rr.bound += np.array([-.25, -.25, .25, .25])
                # Preserve the global time origin while checking the suffix.
                offset = horizon - c
                bound = rr.bound[:, offset:]
                flags = rr.flags_all[:, offset:]
                tk = (horizon + np.arange(bound.shape[1])) * planner.params.frame_time
                rs = forecast.rs
                occ = planner._contacts_fn(forecast, bound, tk, (flags & km.F_INVULN) != 0,
                                           lambda x, y: rs.occupied_esc(x, y, tk))
                # The endpoint itself was checked by the row's full envelope.
                if occ.any():
                    clear = False
                    break
            if not clear:
                break
        if clear:
            return int(e)
    return None


def append_rows(planner, win, ws, f, start, hold, prefix, prefs, T, posture, ds):
    """At most three ordinary drift proposals, and at most one accepted row."""
    real_start = time.perf_counter_ns()
    attempts = []
    memo = {}  # this tick only; no forecast/state cache survives the call
    for drift in (None, -1, 1):
        result = _append_once(planner, win, ws, f, start, hold, prefix, prefs, T, posture, ds,
                              drift=drift, memo=memo)
        info = planner._knife_info
        attempts.append(info)
        if result is not ds or "proposal" not in info:
            break
    planner._knife_info = {**info, "attempts": attempts,
                            "contract_rejections": sum(a.get("contract_rejections", 0) for a in attempts),
                            "elapsed_ms": (time.perf_counter_ns() - real_start) / 1e6}
    return result



def contract_reject(info, stage, reason, *, identity=None):
    """A malformed/unsupported certificate is visible, never a coverage miss."""
    info["contract_rejections"] = info.get("contract_rejections", 0) + 1
    info.setdefault("checks", []).append(dict(check="knife_contract", status="failed",
        stage=stage, reason=str(reason), identity=identity))


def certify_hook(planner, win, ws, forecast, start, hold, prefix, prefs, T,
                 obs, raw, wire, launch, info, memo):
    """Native all-world hook proposal -> full hit paths -> one shared exit.

    Declare the reference domain before inspecting any candidate contact. The
    existing body, duration, shift, residual, danger and protection models are
    unchanged. Physical-hook motion may be shared only after all target worlds
    prove the same hook-supporting body, not by dropping an unsupported world.
    """
    from ssbot.combat import forum_knife_coupled as coupled
    from ssbot.combat import forum_knife_hit as hit, forum_knife_lanes as lanes
    from ssbot.combat.forum_knife_plan import CheckedTail
    H, L = len(prefix) + T, len(raw)
    knowledge = win.knife_knowledge
    stage = "expected_domain"
    phase_begin = time.perf_counter_ns()
    phases = info.setdefault("phase_ms", {})
    def phase(name):
        nonlocal phase_begin
        now = time.perf_counter_ns()
        phases[name] = (now - phase_begin) / 1e6
        phase_begin = now
    try:
        expected = hit._expected_domain(coupled.expected_slam_worlds(obs, knowledge))
    except ValueError as exc:
        contract_reject(info, stage, exc, identity=int(obs.iid))
        return None
    info["expected_world_count"] = len(expected)
    phase("expected_domain")
    # J can be delayed to L-1; every common exit is at least 24 frames long.
    support_end = L + 24
    try:
        cache_key = ("hook_support", support_end, int(obs.iid))
        if cache_key not in memo:
            tk = np.arange(support_end + 1) * planner.params.frame_time
            boxes, _, _, keep = planner._forum_targets(ws, forecast, tk, prefs)
            ti = next((i for i, t in enumerate(keep) if t.iid == obs.iid and not t.hazard), None)
            paths = planner._ds_move_paths(forecast.rs.trk, keep, boxes)
            if ti is None or ti not in paths or len(paths[ti]) != 1:
                info["gate"] = "unsupported_target_translation_domain"
                return None
            paths = paths[ti]
            body = slam_body_paths(obs, paths, knowledge)[0]
            safe = safety_forecast(forecast, support_end)
            roots = np.array([obs.x, obs.y]) + paths[0][:, :2] - paths[0][0, :2]
            memo[cache_key] = paths, body, safe, roots
        paths, body, safe, roots = memo[cache_key]
        hook_key = ("native_hook", L, int(obs.iid), wire[:launch].tobytes())
        if hook_key not in memo:
            memo[hook_key] = claw.rollout(start, wire, planner.params, planner.terrain, body,
                                          obs.iid, threads=planner.cfg.threads)
        hook_base = memo[hook_key]
        if H <= int(hook_base.control_frames.max()):
            info["gate"] = "unsupported_main_endpoint_inside_hook"
            return None
        base = lanes.rollout(hook_base, planner.params, planner.terrain,
                             commands=wire, threads=planner.cfg.threads)
        def reroll(events, commands):
            return lanes.rollout(hook_base, planner.params, planner.terrain, events,
                                 commands=commands, threads=planner.cfg.threads)
        # This check proves that reuse of one hook path is valid in every
        # contact world. A differing support is unsupported, never a survivor.
        hook_end = int(hook_base.control_frames.max()) + 1
        hook_start = hook_base.launch_frame + claw.sk.HOOK_HIT_F
        inner = list(slam_body_variants(obs, paths, knowledge))
        outer = list(slam_body_variants(obs, paths, knowledge, outer=True))
    except ValueError as exc:
        info["checks"].append(dict(check="hook_model", status="unchecked", reason=str(exc)))
        return None
    phase("support_hook_clocks_bodies")
    stage = "contact_worlds"
    try:
        pairs = {}
        for (dur, small), (dur2, large) in zip(inner, outer, strict=True):
            if dur != dur2 or tuple(dur) in pairs:
                raise ValueError("body duration identity changed")
            pairs[tuple(dur)] = small, large
        expected_durations = {key[1] for key in expected}
        if set(pairs) != expected_durations:
            raise ValueError("body duration domain differs from independent expected domain")
        probes = []
        for iid, durations, shift in expected:
            small, large = pairs[durations]
            ix = np.clip(np.arange(len(body)) + shift, 0, len(body) - 1)
            if not all(np.array_equal(b[ix][hook_start:hook_end], body[hook_start:hook_end], equal_nan=True)
                       for b in (small, large)):
                info["checks"].append(dict(check="hook_world_support", status="unchecked",
                    identity=(iid, durations, shift), reason="world changes hook-supporting body"))
                return None
            swing, first, last, robust = coupled.contact_bounds(planner, base, wire,
                1 if np.asarray(start).reshape(km.K)[km.FACE] >= 0 else -1,
                small[:L + 1], large[:L + 1], shift)
            probe = hit.HitWorld((iid, durations, shift), None, base, swing, first, last, robust, reroll)
            probes.append(probe)
            if not hit.contacts_fit(probe, H, L):
                info.update(gate="contact_gate", contact_worlds_checked=len(probes))
                info["checks"].append(dict(check="robust_contact", status="failed", identity=probe.key,
                    first=first.tolist(), last=last.tolist(), robust=robust.tolist()))
                return None  # cheap denial, not a truncated reference domain
        phase("contact_worlds")
        stage = "paired_forecasts"
        worlds = []
        for probe in probes:
            key = ("paired_forecast", support_end, probe.key)
            if key not in memo:
                memo[key] = coupled.conditioned_slam(safe, obs, probe.key[1], probe.key[2], roots)
            worlds.append(replace(probe, forecast=memo[key]))
        phase("paired_forecasts")
        stage = "common_escape"
        audit = {}
        cert = hit.common_escape(planner, worlds, raw, hold, horizon=H,
                                 expected_worlds=expected, audit=audit)
        phase("common_escape")
        # Keep the production tick log bounded. Detailed per-world motion and
        # occupancy are diagnostic output, not per-ACTION logging payload.
        info["hit_exit"] = {k: v for k, v in audit.items() if k not in ("worlds", "options")}
        info["hit_exit"]["options"] = [dict(option=a["option"], failed_world_count=len(a["failed_worlds"]),
            failed_world_sample=a["failed_worlds"][:4], unsafe_frames=a["unsafe_frames"]) for a in audit["options"]]
        if cert is None:
            info["gate"] = audit.get("reason", "hit_exit_failed")
            return None
        stage = "checked_tail"
        tail = CheckedTail.from_exit(cert, frame=int(ws.stamp.frame), start=start, hold=hold,
            prefix=prefix, T=T, world_keys=expected, runtime_source=(forecast, knowledge))
    except ValueError as exc:
        contract_reject(info, stage, exc, identity=int(obs.iid))
        return None
    phase("checked_tail")
    info["checks"].append(dict(check="all_world_hit_exit", status="passed", worlds=len(expected),
        paths=len(cert.paths), J=cert.start, through=cert.through, H=H))
    return cert, tail, hook_base

def _append_once(planner, win, ws, f, start, hold, prefix, prefs, T, posture, ds, *, drift=None, memo=None):
    """Check a fixed proposal; failed and unchecked rows never reach ranking."""
    from ssbot.combat.forum_planner import DsRows
    from ssbot.combat.holdfilter import hold_filter_jit

    t0 = time.perf_counter()
    info = {"scope": "w7 single Clapper; fixed proposal; no contingent certificate",
            "checks": [], "rows": 0}
    planner._knife_info = info
    if not getattr(win, "knife_scope", False):
        info["gate"] = "encounter"
        return ds
    obs = [o for o in win.obs() if o.hp > 0]
    P, H = len(prefix), len(prefix) + T
    if (len(obs) != 1 or win.harpoon or win.lat_s & ow.M_CLAW
            or np.any(np.asarray(prefix) & ow.M_CLAW)
            or win.fo is None or win.last_freeze is not None and win.fo - win.last_freeze < 8):
        info["gate"] = "control_or_clock"
        return ds
    if obs[0].hp <= MIN_TARGET_HP:
        info["gate"] = "target_hp"
        return ds
    # Every real enemy, including distant ones excluded by the scorer.
    all_targets = [t for t in f.targets(np.array([0.])) if not t.hazard]
    if {t.iid for t in all_targets} != {obs[0].iid}:
        info["gate"] = "multiple_or_unknown_targets"
        return ds
    o = ow._advance(obs[0], P)
    wt = ow.rx.WINDOWS["claw_slam0"]
    if not ow.rx.in_states(o.st, o.j, wt.anchor):
        info["gate"] = "window"
        return ds
    memo = {} if memo is None else memo
    if "prefix_state" not in memo:
        pre_lat, _ = hold_filter_jit(np.asarray(prefix)[None], hold)
        memo["prefix_state"] = km.rollout(start, pre_lat, planner.params, planner.terrain,
                            threads=planner.cfg.threads).final[:, 0] if P else np.asarray(start).reshape(km.K)
    state = memo["prefix_state"]
    key = ow.rx.cell_of(state, o, wt)
    if key is None:
        info["gate"] = "cell"
        return ds
    pk = ow.rx.pack_key(key)
    if not win._has_full(np.array([pk]))[0]:
        info["gate"] = "cell_absent_or_partial"
        return ds
    entry = win._entry(pk)
    if entry is None or not bool(win._margin(np.array([pk]))[0]):
        info["gate"] = "full_margin"
        return ds
    direction = 1 if o.x >= state[km.PX] else -1
    row, press, attack, fixed = fixed_keys(entry.macro, direction, drift=drift)
    info["proposal"] = {"cell": key.short(), "table_macro": entry.macro.label(),
                        "fixed_macro": fixed.label(), "press": P + press, "attack": P + attack}
    if P + attack <= H:
        # This checkpoint supplies new hook entries only. The native scorer
        # still needs the owned-strike bridge before accepting an in-H press;
        # this is unsupported execution scope, not a miss/abort safety rule.
        info["gate"] = "unsupported_strike_inside_main_horizon"
        return ds
    L = max(H + 1, P + len(row), P + press + 63) + 4
    try:
        row,press,raw,lat,delay=align_throw(row,prefix,hold,press,direction,L)
    except ValueError as exc:
        info["checks"].append({"check":"launch_direction","status":"failed","reason":str(exc)})
        return ds
    info["proposal"].update(press=P+press,launch_delay=delay)
    differences = np.flatnonzero(lat[0] != raw)
    info["checks"].append({"check": "latched_keys", "status": "passed",
                            "changed_frames": differences.tolist(),
                            "meaning": "all subsequent models use the filtered wire keys"})
    certified = certify_hook(planner, win, ws, f, start, hold, prefix, prefs,
                             T, obs[0], raw, lat[0], P + press, info, memo)
    if certified is None:
        info["ms"] = (time.perf_counter() - t0) * 1000
        return ds
    cert, tail, hook_base = certified
    # Keep the entire newly checked strike/exit. Main-row motion comes from
    # the hit paths; no miss-path safety check or H abort is performed.
    bound, flags = envelope(cert.paths, H + 1)
    nominal = cert.paths[0]
    contacts = np.concatenate(cert.contacts)
    row = cert.raw[P:].copy()
    # Contact is outside H for a new proposal. Re-roll the same logical clocks
    # to exactly H for the score endpoint, without inventing an H initializer.
    from ssbot.combat import forum_knife_lanes as lanes
    end = lanes.rollout(hook_base, planner.params, planner.terrain,
                        commands=cert.latched[:H], threads=planner.cfg.threads)
    data = {"nominal": {nm: getattr(nominal, nm)[0, :H + 1] for nm in
                         ("phys", "pos", "vel", "mode", "flags", "box")},
            "final": end.final[:, 0], "bound": bound, "flags_all": flags,
            "escape": cert.option, "checked_tail": tail,
            "checks": info["checks"], "latched": cert.latched[:H].copy()}
    base = 0 if ds is None else len(ds.cmd)
    cand = ow.Cand("now", "claw_slam0", o.iid, row, 0, min(contacts), max(contacts),
                   key.short(), fixed.label(), len(row), pk=pk, macro=fixed, cert=True)
    wr = DsRows(row[None, :T], [f"WIN knife claw_slam0 {fixed.label()}"], [row],
                np.zeros((1, H), np.int64), np.zeros(1, bool), np.array([min(contacts)]),
                np.array([-1]), np.array([o.iid]), np.ones(1, np.int64), None,
                custom={base: data})
    if ds is not None:
        wr = DsRows(np.concatenate((ds.cmd, wr.cmd)), list(ds.names) + wr.names, list(ds.ext) + wr.ext,
                    np.concatenate((ds.ev, wr.ev)), np.r_[ds.cert, wr.cert], np.r_[ds.c1, wr.c1],
                    np.r_[ds.c2, wr.c2], np.r_[ds.tgt, wr.tgt], np.r_[ds.extra, wr.extra], ds.lane,
                    ds.n_tpl, ds.n_pass, ds.n_chain, ds.ms, custom={**(ds.custom or {}), base: data})
    old = getattr(planner, "_win_c", None)
    if not old:
        planner._win_off = base
        planner._win_c = [cand]
    else:
        planner._win_c = list(old) + [cand]
    info.update(rows=1, ms=(time.perf_counter() - t0) * 1000)
    return wr


def warm(planner):
    """Compile new memory layouts before a live episode, never on first use."""
    state = km.initial_state(planner.params, 30., 8., ground=False)
    masks = np.zeros(80, np.int64)
    masks[:2] = ow.M_CLAW | km.B_RIGHT
    body = np.tile([34., 3., 37., 10.], (100, 1))
    initial = claw.rollout(state, masks, planner.params, planner.terrain, body, 1,
                           threads=planner.cfg.threads)
    ev = np.zeros((len(initial.hooks), len(masks)), np.int64)
    ev[:, 50] = km.EV_POGO
    claw.with_events(initial, planner.params, planner.terrain, ev, threads=planner.cfg.threads)
    from ssbot.combat import forum_knife_lanes as lanes
    expanded = lanes.rollout(initial, planner.params, planner.terrain, threads=planner.cfg.threads)
    lane_events = np.zeros((len(expanded.hooks), len(masks)), np.int64)
    lane_events[:, 50] = km.EV_POGO
    lanes.rollout(initial, planner.params, planner.terrain, lane_events, threads=planner.cfg.threads)
    changed = masks.copy()
    changed[2:] |= km.B_LEFT
    claw.with_commands(initial, changed, planner.params, planner.terrain, threads=planner.cfg.threads)
    # Hook rows carry explicit int64 block flags; normal h2 warm-up uses
    # int32 flags, a different Numba signature. Warm this real path too.
    n = len(initial.hooks)
    planner._ds_hits(initial, np.broadcast_to(masks, (n, len(masks))).copy(), 1,
                      body[:len(masks) + 1][None].copy(), np.ones((1, len(masks) + 1), bool),
                      np.ones(1, bool), np.ones(n, np.int64), 0., np.array([-2, -1, 1, 2], np.int64))
