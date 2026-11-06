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
    from .knife_chain_transfer import HOOK_PRESS_AFTER_F, HOOK_LATE_F, retreat_reserve, body_box, control
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
    return {"P": P, "origin":int(sim.f), "target_state":control(enemy)[0],
            "toward": int(toward), "rows": rows, "body": [float(v) for v in body_box(enemy)],
            "iid": int(enemy["iid"]), "reserve": reserve}


def _hooks(row, toward, body, reserve, iid):
    """(dash_f, ctrl_after, ac, world, positions) of every _tracks variant: world 0 the observed body still, 1 moved
    away by the retreat bound; positions from the press (index 0 = P) with the antic heights, as _nominal_hook."""
    from ssbot.knowledge import hero2 as H2
    from ssbot.map2 import strike as SK
    x, bb, vx, vy = row
    S = np.zeros(K.K)
    S[K.PX], S[K.PY], S[K.VX], S[K.VY] = x, bb + SK.FOOT, vx, vy
    b = np.asarray(body, float)
    r = np.asarray(reserve, float)
    worlds = (np.tile(b, (len(r), 1)), b + toward * np.outer(r, [1., 0., 1., 0.]))
    phases = []
    for ac in range(6):         # per physics-step phase only (Task 179 #308: the entry tick builds every slot cold)
        steps = [SK.steps_of(j, ac) for j in range(1, len(r) + 1)]
        phases.append((ac, steps, H2.claw_unhooked(x, bb, vx, vy, toward, steps)))  # its antic heights only, as _nominal_hook
    for dash_f, ctrl_after in _variants():
        var = SK.HookVariant("task170", dash_f, 0., ctrl_after)     # the dash damager stops it, not the gap
        for ac, steps, antic in phases:
            for w, boxes in enumerate(worlds):
                h = SK.claw_hook(S, 0, toward, iid, boxes, var, ac, discrete_stop=True,
                                 hold_steps=sum(steps[:SK.HOOK_THROW_F]), dash_max_steps=SK.DASH_MAX_STEPS,
                                 dash_damager=True, dash_motion_lag=1)
                if not h.ok:
                    raise GeometryUnavailable("transfer hook step unchecked: hooked model " + h.why)
                pos = np.array(h.pos, float)
                t = SK.HOOK_THROW_F
                pos[:t + 1, 1] = antic.bb[:t + 1] + SK.FOOT
                pos[t + 1:, 1] = antic.bb[t] + SK.FOOT
                yield dash_f, ctrl_after, ac, w, pos


@lru_cache(maxsize=32)
def _tracks(row, toward, body, reserve, iid):
    """The model's transform positions per frame from the press (index 0 = P, the free-flight state at P) for every
    variant, deduplicated. A variant the model cannot place raises GeometryUnavailable."""
    out = {}
    for *_, pos in _hooks(row, toward, body, reserve, iid):
        out.setdefault(pos.round(9).tobytes(), pos)
    return tuple(out.values())


@lru_cache(maxsize=32)
def _stop_tracks(row, toward, body, reserve, iid):
    """_tracks plus every stop BETWEEN its two worlds (Task 179 #308 P2: the body may be anywhere from still to the
    retreat bound, and live L3 stopped at x 22.52 between the bounds' 21.0 and 25.2). The hooked dash moves 1.4 u per
    physics step and the damager check comes before each step, so the reachable stops are exactly "k steps" for every
    k from the still world's count to the bound's: such a track is the bound's dash cut at its k-th step (that step's
    frame is the stop frame) and held there to the variant's control (stop + ctrl_after, clamped 23 .. 34, as
    map2.strike.claw_hook). No third body world and no other change: heights, timings and phases are the variant's.
    Returns (i0, positions from index i0): i0 0 for _tracks' own tracks; an intermediate one equals its bound's track
    before its stop frame j, so it starts at j - 1 (its own sweep into the stop stays whole)."""
    from ssbot.map2 import strike as SK
    out, pairs = {}, {}
    for dash_f, ctrl_after, ac, w, pos in _hooks(row, toward, body, reserve, iid):
        out.setdefault((0, pos.round(9).tobytes()), (0, pos))
        pairs.setdefault((dash_f, ctrl_after, ac), {})[w] = pos
    for (dash_f, ctrl_after, ac), w in pairs.items():
        still, far = w[0], w[1]
        hold = float(far[SK.HOOK_THROW_F, 0])
        steps = np.rint((far[:, 0] - hold) * toward / SK.DASH_STEP_U).astype(int)     # dash steps done by each frame
        k0 = int(round((float(still[-1, 0]) - hold) * toward / SK.DASH_STEP_U))
        for k in range(k0 + 1, int(steps[-1])):
            j = int(np.flatnonzero(steps >= k)[0])
            ctrl = min(max(j + ctrl_after, 23), 34)
            if ctrl >= len(far):
                raise GeometryUnavailable("transfer hook entry unchecked: intermediate stop beyond the bound's control")
            track = far[j - 1:ctrl + 1].copy()
            track[1:, 0] = hold + toward * SK.DASH_STEP_U * k
            out.setdefault((j - 1, track.round(9).tobytes()), (j - 1, track))
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


def _hook_body_window(v,watch,f,state):
    """Measured target-body-off only, with real hit evidence and an absolute attack bound.

    The current raster calls an attacking owner's body `move`, so only inside
    this bounded window may that label stand for the harmless hooked body.
    Armed colliders/late Antic, delayed hazards and unknown data never qualify.
    """
    from ssbot.map2 import strike as SK
    from .knife_chain_transfer import HOOK_TARGET_STATES,HOOK_CTRL_LAST_F
    from .move_data import load_cl_slam
    a=v.get("hook_press");hit=v.get("hook_hit_f");seen=watch.get("seen_frame")
    if (not isinstance(a,dict) or type(a.get("origin")) is not int
            or a.get("target_state") not in HOOK_TARGET_STATES
            or type(seen) is not int or type(hit) is not int or not seen<=hit<=f
            or not isinstance(state,dict) or state.get("f")!=f):return None
    target=getattr(watch.get("move"),"target_iid",None)
    es=[e for e in state.get("ents") or () if e.get("iid")==target]
    if len(es)!=1:return None
    e=es[0];cols=e.get("colliders")
    if not isinstance(cols,list) or not cols:return None
    if any(str(c.get("name","")).startswith("Slam Collider") and c.get("enabled") is not False for c in cols):return None
    clocks=[c for c in e.get("fsms") or () if isinstance(c,dict) and c.get("name")=="Control"]
    if len(clocks)!=1:return None
    st=clocks[0].get("state");tin=clocks[0].get("t")
    known=HOOK_TARGET_STATES|{"Slam Antic","Spell Antic","Cast 1","Cast 2","Jump Antic","Cast Slam Antic","Cast Slam Antic 2"}
    if (st not in known or type(tin) not in (int,float) or not math.isfinite(tin) or tin<0):return None
    mins={s.name:min(int(n) for n in s.frames) for s in load_cl_slam().states}
    first_hammer=mins["Slam Antic"]+mins["Slam 0"]
    # A natural next move may start before the needle hits: bound from the
    # admission observation, NOT from an assumed hit-triggered Antic.
    last=min(a["origin"]+first_hammer-2,seen+HOOK_CTRL_LAST_F+SK.HOOK_BODY_OFF[1])
    ctrl=v.get("hook_ctrl_f")
    if type(ctrl) is int:
        if not hit<=ctrl<=f:return None
        last=min(last,ctrl+SK.HOOK_BODY_OFF[1])
    else:
        h=state.get("hero") or {}
        if (h.get("hero_accepting_input") is not False
                or "harpoon" not in str((h.get("anim") or {}).get("clip","")).lower()):return None
        last=min(last,f+2+SK.HOOK_BODY_OFF[1])
    if st=="Slam Antic":last=min(last,f+first_hammer-int(math.ceil(tin*60.))-2)
    first=seen+SK.HOOK_BODY_OFF[0]
    return (target,first,last) if first<=last else None


def step_scan(geo,path,v,watch,f,state=None):
    """Scan every owner; exempt only the evidence-bound harmless hooked body.

    This never sets an invulnerability flag. Target delayed/armed/unknown and
    every other owner stay in the scan, including before/after the body window.
    """
    scans=[geo.scan(q) for q in step_paths(path,v,watch,f)]
    window=_hook_body_window(v,watch,f,state)
    contacts=tuple(c for scan in scans for c in scan.contacts
        if not (window is not None and c.owner_iid==window[0]
                and c.kind in {"body","move"} and window[1]<=c.frame<=window[2]))
    return ContactScan(scans[0].path_ref,min(s.first_frame for s in scans),max(s.last_frame for s in scans),
        contacts,f"transfer hook step: {len(scans)} variant path(s); all-owner scan; "
        f"measured hooked-body window {window}; no protection",all(s.complete for s in scans))


def _entry(path, v, f):
    """entry_paths' variant paths (_stop_tracks: every stop from the still body to the retreat bound), each with its
    hooked-body window (P + HOOK_BODY_OFF[0] .. control + HOOK_BODY_OFF[1]) and its control point (frame, x, y: the
    model's stop and hold height)."""
    from ssbot.map2 import strike as SK
    from .knife_chain_transfer import HOOK_LATE_F
    a = v.get("hook_press")
    if not isinstance(a, dict):
        raise GeometryUnavailable("transfer hook entry unchecked: no press anchor")
    box = np.asarray(path.box, float)
    P = int(a["P"])
    if path.origin != f or box.shape != (3, 4) or not np.isfinite(box).all() or not 1 <= P - f <= 3:
        raise GeometryUnavailable("transfer hook entry unchecked: external step rows or press slot")
    w, h = float(box[0, 2] - box[0, 0]), float(box[0, 3] - box[0, 1])

    def boxes(tr):                      # transform positions -> boxes of the current step's size (bottom = y - FOOT)
        x, bottom = tr[:, 0], tr[:, 1] - SK.FOOT
        return np.column_stack([x - .5 * w, bottom, x + .5 * w, bottom + h])
    head = box[:P - f]
    out = {}
    for d in range(HOOK_LATE_F + 1):
        if d >= len(a["rows"]):
            raise GeometryUnavailable("transfer hook entry unchecked: press slot outside the anchor")
        pre = np.asarray([[r[0] - .5 * w, r[1], r[0] + .5 * w, r[1] + h] for r in a["rows"][:d]], float).reshape(-1, 4)
        for i0, tr in _stop_tracks(tuple(a["rows"][d]), int(a["toward"]), tuple(a["body"]),
                                   tuple(a["reserve"][d:d + TRACK_F]), int(a["iid"])):
            # an intermediate stop's track is its bound's before i0 + 1: its rows from P + d + i0 only
            origin, rows = (f, np.vstack([head, pre, boxes(tr)])) if i0 == 0 else (P + d + i0, boxes(tr))
            ctrl = P + d + i0 + len(tr) - 1
            out.setdefault((origin, rows.round(9).tobytes()),
                           (origin, rows, (P + d + SK.HOOK_BODY_OFF[0], ctrl + SK.HOOK_BODY_OFF[1]),
                            (ctrl, round(float(tr[-1][0]), 6), round(float(tr[-1][1]), 6))))
    from types import SimpleNamespace
    basis = {**path.assumptions, "basis": "hooked-Clawline model through the locked hook", "protection": "none",
             "safety": "whole locked hook, all owners"}
    paths = []
    for origin, rows, window, control in out.values():   # the fields B2Geometry reads; no protection flag
        n = len(rows) - 1
        zero = np.zeros(n + 1, np.int64)
        paths.append((SimpleNamespace(origin=origin, stage="transfer_hook_entry", box=rows, commands=zero[:n],
                                      latched=zero[:n], flags=zero, check_flags=zero, through=origin + n,
                                      assumptions=basis), window, control))
    return paths


def entry_paths(path, v, f):
    """Task 179 #308 (live 179-L3 w13_guard179L3 5df8711e: the 2682 face hook on the walking 335476 locked her
    2685-2712, ended short of the retreating target, and its forced bounce rose into the other Clapper's jump, Sentry
    (3) at 2721; only single steps had been scanned). The WHOLE locked hook before its CLAW is sent: the current step's
    K rows up to the planned press P, then for each CLAW slot applied 0 .. HOOK_LATE_F late the free-flight press rows
    and every hooked-model variant track (_tracks as step_paths: dash timings, physics-step phases, the observed body
    still or retreating at the bound; plus every stop between those two, _stop_tracks) up to the model's control.
    Unknown raises."""
    return [p for p, _, _ in _entry(path, v, f)]


def entry_scan(geo, path, v, f):
    """All owners and delayed hazards over entry_paths (one B2Geometry.scan_batch pass); only the target's own BODY
    inside each variant's hooked-body window (strike.HOOK_BODY_OFF: the hooked dash stops on it by design) is exempt;
    its attack (move), its body outside the window, other owners, small runes and unknown occupancy all count. Also
    returns the distinct control points (frame, x, y) for entry_outs."""
    items = _entry(path, v, f)
    iid = int(v["hook_press"]["iid"])
    scans = list(zip(geo.scan_batch([q for q, _, _ in items]), (window for _, window, _ in items)))
    contacts = tuple(c for s, (lo, hi) in scans for c in s.contacts
                     if not (c.owner_iid == iid and c.kind == "body" and lo <= c.frame <= hi))
    return (ContactScan(scans[0][0].path_ref, min(s.first_frame for s, _ in scans),
                        max(s.last_frame for s, _ in scans), contacts,
                        f"transfer hook entry: {len(scans)} variant path(s) through the locked hook; all-owner scan; "
                        "target body exempt only in the hooked-body window; no protection",
                        all(s.complete for s, _ in scans)),
            tuple(sorted({c for _, _, c in items})))


def _control_holds(sim, v, f, frames):
    """The key filter state after each control frame F and the key queued for F + 1, DERIVED from the keys the hook
    commits (Task 179 #308, Sol seq 229): the actual in-flight prefix for f + 1, the CsPlan's turn and CLAW keys
    (claw_strike.plan_mask), then the lock's zero keys (claw_lock sends none) through the existing hold_filter_jit
    from the actual HF. Unknown committed keys raise; whatever the filter then holds is used as it is, never replaced
    by an idle default."""
    from .claw_strike import plan_mask
    from .holdfilter import hold_filter_jit
    cs, a = v.get("cs"), v.get("hook_press")
    if cs is None or not isinstance(a, dict) or len(sim.prefix) != 1 or not frames or min(frames) <= f:
        raise GeometryUnavailable("transfer hook entry unchecked: committed keys before the control unknown")
    toward = int(a["toward"])
    keys = np.array([int(sim.prefix[0])] + [plan_mask(cs, F, toward) for F in range(f + 2, max(frames) + 2)], np.int64)
    out = {}
    for F in frames:                                   # keys[i] is the key for frame f + 1 + i
        out[F] = (hold_filter_jit(keys[None, :F - f], sim.hold)[1], int(keys[F - f]))
    return out


def _control_starts(sim, v, f, controls):
    """oldwin_claw.control_states at every control point: the hooked Clawline's forced bounce (EV_POGO at control, no
    invulnerability, downspike recovery), facing the hook, the physics phase advanced from the actual one."""
    from types import SimpleNamespace
    from ssbot.map2.oldwin_claw import control_states
    S0 = np.asarray(sim.start, float).reshape(K.K)
    step = float(sim.params.frame_time) / float(sim.params.fdt)
    toward = int(v["hook_press"]["toward"])
    return control_states(sim.params, [SimpleNamespace(x_stop=x, y_hold=y, d=toward) for _, x, y in controls],
                          sim.terrain, alphas=[(float(S0[K.ALPHA]) + (F - f) * step) % 1. for F, _, _ in controls])


def entry_outs(geo, sim, v, f, controls, short_frames):
    """The forced bounce at every control point of entry_scan against the existing N=2 continuation lower bound's
    short pass (NativeManualAirChain._continuations): both ordinary post types, left and right landing
    (knife_chain_post_actions.ordinary_post's keys after the queued key, from the filter state, both derived from the
    committed keys by _control_holds), executable (continuation_executable's rule) and clear of every owner, delayed
    hazard and unknown occupancy over short_frames or up to their ground handback. One rollout per type and control
    frame (bit-identical to ordinary_post's trace) and one geometry pass. A control below the bound rejects the hook
    at its entry: the full-exit fallback of _continuations is not run here (entry_bounces gives its exact parents), so
    this is a conservative short lower bound, not an exit guarantee. The hooked target's BODY stays exempt up to
    control + HOOK_BODY_OFF[1] (measured: harmless from P + 17 to control + 12, as in entry_scan); its attack (move) and
    every other owner count. Returns (None or the first failure, paths)."""
    from types import SimpleNamespace
    from .holdfilter import hold_filter_jit
    if not controls:
        raise GeometryUnavailable("transfer hook entry unchecked: no control point")
    holds = _control_holds(sim, v, f, sorted({F for F, _, _ in controls}))
    starts = _control_starts(sim, v, f, controls)
    paths, meta = [], []
    for kind, bit, direction in (("left_landing", B["L"], -1), ("right_landing", B["R"], 1)):
        groups = {}                     # control frames whose keys latch alike share one rollout
        for F, (hold, queued) in holds.items():
            commands = np.full(short_frames, bit, np.int64)
            commands[0] = queued
            latched = hold_filter_jit(commands[None, :], hold)[0][0]
            groups.setdefault((commands.tobytes(), latched.tobytes()), (commands, latched, set()))[2].add(F)
        for commands, latched, frames in groups.values():
            idx = [j for j, c in enumerate(controls) if c[0] in frames]
            ro = K.rollout(starts[:, idx], np.repeat(latched[None, :], len(idx), axis=0), sim.params, sim.terrain)
            fl = np.asarray(ro.flags, np.int64)
            at = np.arange(fl.shape[1])
            land = ((fl & K.F_GROUND) != 0) & ((fl & K.F_NO_INPUT) == 0) & (at >= 2)
            ns = np.where(land.any(axis=1), land.argmax(axis=1), short_frames)        # ground handback or the horizon
            on = [i for i in range(1, short_frames) if int(latched[i]) & bit]
            if on:              # continuation_executable: the key latched before the handback moves her within 4 frames
                i, vx = on[0], ro.vel[:, :, 0]
                near = (at >= i + 1) & (at < i + 5) & (at[None, :] < ns[:, None] + 1)
                moved = (direction * (vx - vx[:, i:i + 1]) > 0) | (direction * vx > 0)
                executable = (ns >= 2) & (i < ns) & (moved & near).any(axis=1)
            else:
                executable = np.zeros(len(idx), bool)
            for r, j in enumerate(idx):
                n, F = int(ns[r]), controls[j][0]
                paths.append(SimpleNamespace(origin=F, stage="continuation", box=ro.box[r, :n + 1],
                                             flags=fl[r, :n + 1], check_flags=fl[r, :n + 1], commands=commands[:n],
                                             through=F + n))
                meta.append((controls[j], kind, bool(executable[r])))
    from ssbot.map2 import strike as SK
    iid = int(v["hook_press"]["iid"])
    for (control, kind, executable), scan in zip(meta, geo.scan_batch(paths)):
        bad = [c for c in scan.contacts
               if not (c.owner_iid == iid and c.kind == "body" and c.frame <= control[0] + SK.HOOK_BODY_OFF[1])]
        if not executable or bad or not scan.complete:
            return ({"control": control, "kind": kind, "executable": bool(executable), "complete": scan.complete,
                     "first": bad[0] if bad else None}, len(paths))
    return None, len(paths)


def entry_bounces(sim, v, f, game, controls):
    """entry_outs' control points as B2 conditional-bounce parents for NativeManualAirChain._continuations (the exact
    N=2 lower bound with its full-exit fallback): the reference entry_outs' short pass is checked against. The parent
    hold and queued key are _control_holds' derived ones."""
    from .knife_chain_nominal import NominalPath
    from .knife_chain_step import NominalStepper
    holds = _control_holds(sim, v, f, sorted({F for F, _, _ in controls}))
    starts = _control_starts(sim, v, f, controls)
    dt = float(sim.params.frame_time)
    stepper = NominalStepper(sim.params, sim.terrain)
    out = []
    for j, (F, x, y) in enumerate(controls):
        S = starts[:, j].copy()
        ro = stepper.run(S, frames=0)
        g = float(game) + (F - f) * dt
        fl = np.full(2, int(ro.flags[0, 0]), np.int64)
        hold, queued = holds[F]
        out.append(NominalPath(F - 1, "commitment", np.zeros(1, np.int64), np.zeros(1, np.int64),
                               np.stack([S, S], axis=1), np.stack([ro.box[0, 0]] * 2), np.stack([ro.pos[0, 0]] * 2),
                               fl, fl.copy(), np.array([g - dt, g]), hold, None, None, queued, "bounce",
                               None, None, {"basis": "hooked Clawline forced bounce at the model's control",
                                            "control": (F, x, y), "protection": "none"}))
    return out


def early_jump_due(cache, k, target_state):
    """A cached ok expansion jumps on exactly the tick it was computed for (its J at this tick's first mask frame)."""
    return bool(isinstance(cache, dict) and cache.get("ok") and cache.get("jump_k") == k + 2
                and cache.get("state") == target_state)


def early_jump_stale(cache, f, target_state):
    return (not isinstance(cache, dict) or f >= int(cache.get("next_f", f)) or cache.get("state") != target_state)


def early_jump(runner, p, sim, game, state, enemy, bombs, k, link, held_dash, high_band=False):
    """The Run's cache entry for one expansion of the existing jump recipe from the next tick (see the module doc).
    high_band: the entry_attack=stomp switch's high held band (face_hook_check), so the first passing decision is the
    earliest one at its middle (Task 179 #308)."""
    from .knife_chain_transfer import (render, face_hook_check, clappers, body_box, control, PROGRAM,
                                       HOOK_PRESS_AFTER_F, HOOK_LATE_F)
    from .knife_chain_air import model_path
    from .holdfilter import hold_filter_jit
    from .air_chain import ChainSim
    cfg = runner.chains[PROGRAM].cfg
    n, f, (st, _) = int(cfg["lookahead_frames"]), int(sim.f), control(enemy)
    toward = 1 if p.side == B["R"] else -1 if p.side == B["L"] else 0
    jump_k = k + 3
    entry = {"f": f, "state": st, "jump_k": jump_k, "ok": False, "why": "", "next_f": f + n, "high_band": bool(high_band)}
    if toward == 0:
        entry["why"] = "no approach side"
        return entry
    dash_i = B["DASH"].bit_length() - 1
    current = np.asarray(sim.start).reshape(K.K)
    if (held_dash or int(current[K.MODE]) in (K.M_DASH, K.M_SPRINT) or int(sim.prefix[0]) & B["DASH"]
            or sim.hold.latched[0, dash_i] or sim.hold.desired[0, dash_i] or sim.hold.pending[0, dash_i]):
        entry.update(why="in-flight dash must finish before early jump", next_f=f + 1)
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
    # A new dash before next tick's cached J would swallow that J. Model the
    # same no-new-dash wait packet that the caller adopts only if this passes.
    pj = replace(p, dash_k=k + 10000, jump_k=jump_k,
                 jump_until=jump_k + int(cfg["STOMP"]["jump_hold"]), sprint_jump=False)
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
        ok, why, info = face_hook_check(sd, hd, e, f + d + 2, toward, bd, bs, high_band=high_band)
        if ok and shift == 0.:
            entry.update(ok=True, why="ok", defer_new_dash=True, next_f=f + 1, decide_f=f + d, press_F=f + d + 3,
                         **{key: float(val) for key, val in info.items()
                            if key in ("ray_margin", "retreat_reserve", "bb_press", "x_press", "held_bb", "band_lo",
                                       "band_hi", "band_mid", "held_low", "held_high")})
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
