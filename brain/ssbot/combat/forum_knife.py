"""Opt-in synchronous Clawline proposals for the old Forum planner.

The table proposes keys. Its contingent certificate is never inherited by a
fixed row. The first scope is one w7 Clapper, normal time, a down contact past
the planner horizon. No executor, worker, handoff or commitment is introduced.
"""
from __future__ import annotations

from dataclasses import replace
import os
import time

import numpy as np

from ssbot.knowledge import kinematics as km
from ssbot.map2 import oldwin as ow, oldwin_claw as claw, reflex as rx
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
    raw = rx.render(fixed, direction)
    commands = np.concatenate((raw.pre, raw.post))
    p = len(raw.pre)
    commands[p - 1:p + 1] |= ow.M_CLAW | (km.B_RIGHT if direction > 0 else km.B_LEFT)
    return commands, p, k, fixed


def envelope(rollouts, length=None):
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
    """One escape command must pass for every hook / post-control outcome.

    Continue from the stored control edges, preserving suffix timing variants.
    This avoids collapsing their end states to the nominal rollout state.
    """
    from ssbot.combat import forum_v2
    from ssbot.combat.holdfilter import hold_filter_jit

    audited_end = max([horizon] + [r.flags.shape[1] - 1 for r in paths if hasattr(r, "flags")])
    length = max(forum_v2.ESC_F, audited_end - horizon)
    samples = getattr(forecast.rs, "samples", None)
    if samples and max(samples) - getattr(forecast.rs, "k_shift", 0) < horizon + length:
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
                            "elapsed_ms": (time.perf_counter_ns() - real_start) / 1e6}
    return result


def _append_once(planner, win, ws, f, start, hold, prefix, prefs, T, posture, ds, *, drift=None, memo=None):
    """Check a fixed proposal; failed and unchecked rows never reach ranking."""
    from ssbot.combat import dslash
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
    wt = rx.WINDOWS["claw_slam0"]
    if not rx.in_states(o.st, o.j, wt.anchor):
        info["gate"] = "window"
        return ds
    memo = {} if memo is None else memo
    if "prefix_state" not in memo:
        pre_lat, _ = hold_filter_jit(np.asarray(prefix)[None], hold)
        memo["prefix_state"] = km.rollout(start, pre_lat, planner.params, planner.terrain,
                            threads=planner.cfg.threads).final[:, 0] if P else np.asarray(start).reshape(km.K)
    state = memo["prefix_state"]
    key = rx.cell_of(state, o, wt)
    if key is None:
        info["gate"] = "cell"
        return ds
    pk = rx.pack_key(key)
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
    # First path integration: no attack inside the main horizon, so h2's
    # in-horizon hit-reaction replay cannot silently use a no-hook path.
    if P + attack <= H:
        info["gate"] = "contact_scope"
        return ds
    L = max(H + 1, P + len(row), P + press + 63) + 4
    raw = np.zeros(L, np.int64)
    raw[:P], raw[P:P + len(row)] = prefix, row
    lat, _ = hold_filter_jit(raw[None], hold)
    differences = np.flatnonzero(lat[0] != raw)
    info["checks"].append({"check": "latched_keys", "status": "passed",
                            "changed_frames": differences.tolist(),
                            "meaning": "all subsequent models use the filtered wire keys"})
    tk = np.arange(L + 1) * planner.params.frame_time
    if L not in memo:
        tbox, tok, _, keep = planner._forum_targets(ws, f, tk, prefs)
        ti = next((i for i, t in enumerate(keep) if t.iid == o.iid and not t.hazard), None)
        paths = planner._ds_move_paths(f.rs.trk, keep, tbox)
        if ti is not None and ti in paths:
            try:
                paths[ti] = slam_body_paths(obs[0], paths[ti], win.knife_knowledge)
            except ValueError as exc:
                info["checks"].append({"check": "body_timeline", "status": "unchecked", "reason": str(exc)})
                return ds
        memo[L] = ti, paths
    ti, paths = memo[L]
    if ti is None or ti not in paths:
        info["checks"].append({"check": "target_paths", "status": "unchecked"})
        return ds
    info["body_source"] = "old move translations + clapper_m2 per-frame body intersection; full danger unchanged"
    rollouts = []
    contacts = []
    try:
        for body in paths[ti]:
            miss = claw.rollout(start, lat[0], planner.params, planner.terrain, body, o.iid,
                                threads=planner.cfg.threads)
            n = len(miss.hooks)
            masks = np.broadcast_to(lat, (n, L)).copy()
            sw, cc, tt, robust = planner._ds_hits(
                miss, masks, 1 if state[km.FACE] >= 0 else -1,
                body[None], np.isfinite(body[:, 0])[None], np.ones(1, bool),
                np.full(n, P + 1, np.int64), 0., dslash.CERT_SHIFTS)
            info.setdefault("strikes", []).append({"start": sw.tolist(), "contact": cc.tolist(),
                                                    "robust": robust.tolist(),
                                                    "controls": miss.control_frames.tolist()})
            if (not robust.all() or np.any(cc <= H) or np.any(cc >= L - dslash.POST_F)
                    or np.any(sw - miss.control_frames < FREE_MIN)):
                ks = range(max(1, int(sw.min())), min(L, int(sw.max()) + 11))
                info["contact_probe"] = [
                    {"k": k, "hero_box_lo": miss.box[:, k].min(axis=0).tolist(),
                     "hero_box_hi": miss.box[:, k].max(axis=0).tolist(),
                     "body": body[k].tolist(), "flags": sorted(set(miss.flags[:, k].tolist())),
                     "mode": sorted(set(miss.mode[:, k].tolist()))} for k in ks]
                raise ValueError("down_contact_or_FREE_MIN")
            ev = np.zeros((n, L), np.int64)
            ev[np.arange(n), cc - 1] = km.EV_POGO
            hit = claw.rollout(start, lat[0], planner.params, planner.terrain, body, o.iid,
                               events=ev, threads=planner.cfg.threads)
            # Full danger remains, on both miss and bounce paths. A table cell
            # never removes the target's body or the rest of the world.
            safety = {}
            miss_clear = _clear(planner, f, miss, safety, "miss")
            hit_clear = _clear(planner, f, hit, safety, "hit")
            info.setdefault("path_safety", []).append(safety)
            if not miss_clear or not hit_clear:
                raise ValueError("full_path")
            rollouts.extend((miss, hit))
            contacts.extend(cc.tolist())
        info["checks"].append({"check": "all_paths_and_strikes", "status": "passed",
                                "outcomes": sum(len(r.hooks) for r in rollouts)})
        e = common_escape(planner, f, rollouts[::2], row, np.asarray(prefix), hold, H)
        if e is None:
            raise ValueError("common_escape")
        info["checks"].append({"check": "escape", "status": "passed", "command": e,
                                "through_frame": max(H + 24, L)})
    except ValueError as exc:
        info["checks"].append({"check": str(exc), "status": "failed"})
        info["checks"].append({"check": "escape", "status": "unchecked", "reason": "upstream path rejected"})
        info["ms"] = (time.perf_counter() - t0) * 1000
        return ds
    bound, flags = envelope(rollouts, H + 1)
    nominal = rollouts[0]
    data = {"nominal": {nm: getattr(nominal, nm)[0, :H + 1] for nm in
                         ("phys", "pos", "vel", "mode", "flags", "box")},
            "final": None, "bound": bound, "flags_all": flags, "escape": e,
            "checks": info["checks"], "latched": lat[0, :H].copy()}
    # The main endpoint is computed at exactly H, not at the longer audit tail.
    end = claw.rollout(start, lat[0, :H], planner.params, planner.terrain, paths[ti][0], o.iid,
                        threads=planner.cfg.threads)
    data["final"] = end.final[:, 0]
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
    claw.rollout(state, masks, planner.params, planner.terrain, body, 1,
                 events=ev, threads=planner.cfg.threads)
    # Hook rows carry explicit int64 block flags; normal h2 warm-up uses
    # int32 flags, a different Numba signature. Warm this real path too.
    n = len(initial.hooks)
    planner._ds_hits(initial, np.broadcast_to(masks, (n, len(masks))).copy(), 1,
                      body[:len(masks) + 1][None].copy(), np.ones((1, len(masks) + 1), bool),
                      np.ones(1, bool), np.ones(n, np.int64), 0., np.array([-2, -1, 1, 2], np.int64))
