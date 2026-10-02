"""Acceptance test of the hero kinematics model (M2 exit item, DESIGN §3.5.2) and of the knockback envelope
(cross-module decision 2): over every 30-frame window of logged play, roll the model forward from the state estimated
at the window start and compare the collider centre after 0.5 s with the logged one (hero.box centre: WorldState
HeroState.pos, decision 1; the rendered hero.pos is reported beside it). Target: 99 % of windows within 0.1 u.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.kin_check <source> [<source> ...] [--horizon 30] [--tol 0.1]
        [--scene Bone_05] [--params <json>] [--json report.json] [--worst 20] [--no-windows]

A source is a recording directory (ssbot.record.recorder), a human session (ssbot.tools.human_session:
state.raw.zst) or a fixture .npz (save_fixture). The start state always comes from the frames up to the window start
only (estimate_state, causal phase interval): what the planner knows at decision time (decision 3). Settings:
  planner_events  the planner's timing: every future frame HeroParams.frame_time long, physics steps from the
                  model's own phase and time scale; the logged contact events injected as a stand-in for the threat
                  layer, which has to predict them at run time (nail recoil, recoil down, pogo, damage, silk gain,
                  early Silkspear catch, external lock). The acceptance figure.
  planner_inputs  the same without events: what the buttons alone determine.
  planner_bounds  planner_events with the timing variant lanes (kinematics.BOUNDS: the float32 timer thresholds
                  moved by -+ timer_bias per link of the hit-stop chain, the phase at the ends of its feasible
                  interval, the short and long Silkspear / Bind variants): the logged box must lie inside the lanes'
                  per-frame hull dilated by tol (a support-style check of the variants, reported beside the hull size).
  replay_events   logged dt, udt and physics steps of the future frames plus logged events: the model's own fidelity,
                  with information the planner does not have (reported, never the acceptance figure).
  replay_inputs   logged timing, no events.
Every window lands in exactly one category (first match of the last applicable rule): uncovered:<why> (invalid:
hero absent, paused or not in gameplay; gap: missing frames; slide: a savestate load still moving the hero back;
harness teleports, hazard respawns, scene changes, deaths, control taken by another FSM, no terrain for the scene,
nail-charge arts), world_freeze (the time scale is below 1 outside the hero's own hit-stop: boss stun, boss death
slow-motion, BindBreak after a hit during Bind: the model runs them from the logged freeze starts, EV_FZ_*, and
BindBreak from the hit during the Bind charge), hitch (a
frame longer than the jitter model's frame_time_max: rate 3.1e-5 per frame, left to the residual monitor), hurt (a
damage knockback inside), contact (nail recoil, recoil down, pogo or an early Silkspear catch inside), recovering
(starts in the damage freeze / recoil), bind, cast, downspike, plain:<primitive> (jump, attack, air, run, idle).
Nothing is dropped: uncovered windows are counted by reason and the "all" figures count them as misses; "covered"
leaves out only the uncovered ones. Arena gates (scene overrides "enable") are world state: a window runs
with them closed unless a logged box of that window overlaps one.

The knockback section checks every logged hit (StartRecoil: recoilFrozen onset) against knockback.knockback_boxes
from the logged hit box: every no-input frame k must lie inside union[k] and the swept hull, and the frames after
control returns (up to the table length) inside union[k]; no-input frames past the table (stacked freezes) are
checked against the swept hull and counted. Each escaping hit is listed with its concurrent freezes;
hits that cannot be checked are counted by reason. The exit code is 1 when any hit escapes.

--monitor replays each source through the live path (kinematics.StateTracker + ResidualMonitor, one frame at a time,
about 0.2 ms per frame) and reports what the runtime monitor would have said: windows scored and dropped, the share
inside the lanes' hull per horizon, the lowest rolling share and the most far-off windows in any 600, and the frames
it spent "degraded" (the calibration of MONITOR_ALARM_*).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

from ssbot.knowledge import kinematics as km
from ssbot.knowledge.kinematics import HeroParams, Terrain2D, Trace

STATE_KEYS = ("hero", "input", "act", "game", "fs", "dt", "udt", "ts", "ev", "pause")


# ---- sources --------------------------------------------------------------------------------------------------

def load_source(path: str | Path, params: HeroParams, scene_filter: str | None = None
                ) -> tuple[Trace, dict[str, Terrain2D]]:
    """(trace, {scene: terrain}) from a recording, a human session or a fixture."""
    path = Path(path)
    if path.suffix == ".npz":
        tr, terrains = load_fixture(path)
    elif (path / "state.raw.zst").is_file():
        from ssbot.ipc.framing import MsgType
        from ssbot.tools.raw_session import messages
        states, terr = [], {}
        for t, m in messages(path):
            if t == MsgType.STATE:
                states.append({k: m.get(k) for k in (*STATE_KEYS, "f")})
            elif t == MsgType.TERRAIN and m.get("scene_raw"):
                terr.setdefault(m["scene_raw"], m)
        tr = Trace.from_states(states, params)
    else:
        from ssbot.record.recorder import RecordingReader
        r = RecordingReader(path)
        tr = Trace.from_states(r.states(keys=STATE_KEYS), params)
        terr = {}
        for _, m in r.terrain():
            if isinstance(m, dict) and m.get("scene_raw"):
                terr.setdefault(m["scene_raw"], m)
    if path.suffix != ".npz":
        terrains = {name: Terrain2D.from_message(m, params.scene(name)) for name, m in terr.items()}
    if scene_filter:
        keep = np.array([tr.scenes[i] == scene_filter for i in tr.scene])
        tr.valid = tr.valid & keep
    return tr, terrains


def save_fixture(path: str | Path, tr: Trace, terrains: dict[str, Terrain2D]) -> None:
    """A trace plus its scenes' collision segments in one .npz (tests, offline checks)."""
    extra = {}
    for name, t in terrains.items():
        extra[f"terrain_h::{name}"] = t.hseg
        extra[f"terrain_v::{name}"] = t.vseg
        extra[f"terrain_s::{name}"] = t.slopes
        extra[f"terrain_g::{name}"] = t.gates
        extra[f"terrain_n::{name}"] = np.array(t.n_base, dtype=np.int64)
    d = {}
    from dataclasses import fields
    for f in fields(tr):
        if getattr(tr, f.name) is not None:
            d[f.name] = getattr(tr, f.name)
    meta = {k: d.pop(k) for k in ("clips", "spells", "scenes", "mask_source")}
    np.savez_compressed(path, meta=json.dumps(meta), **d, **extra)


def load_fixture(path: str | Path) -> tuple[Trace, dict[str, Terrain2D]]:
    z = np.load(path, allow_pickle=False)
    meta = json.loads(str(z["meta"]))
    names = [k for k in z.files if k != "meta" and not k.startswith("terrain_")]
    tr = Trace(**{k: z[k] for k in names}, **meta)
    terrains = {}
    for k in z.files:
        if k.startswith("terrain_h::"):
            name = k.split("::", 1)[1]
            g = z[f"terrain_g::{name}"] if f"terrain_g::{name}" in z.files else np.zeros((0, 4))
            nb = tuple(int(x) for x in z[f"terrain_n::{name}"]) if f"terrain_n::{name}" in z.files else (-1, -1)
            sl = z[f"terrain_s::{name}"] if f"terrain_s::{name}" in z.files else np.zeros((0, 4))
            terrains[name] = Terrain2D(z[k], z[f"terrain_v::{name}"], sl, [], g, nb)
    return tr, terrains


# ---- windows --------------------------------------------------------------------------------------------------

SETTINGS = ("planner_events", "planner_inputs", "replay_events", "replay_inputs")
BOUNDS = "planner_bounds"
CONTACT = km.EV_RECOIL_L | km.EV_RECOIL_R | km.EV_POGO | km.EV_CATCH | km.EV_RECOIL_DOWN
HURT = km.EV_HURT_L | km.EV_HURT_R


def world_slow(tr: Trace, modes: np.ndarray) -> np.ndarray:
    """Frames whose time scale is below 1 for a reason the hero model does not own: a FreezeMoment other than its
    damage hit-stop (the logged ts outside M_HURT_FREEZE, one started in the frame, or a whole hit-stop that another
    freeze overlapped: BossDeathSlow with the killing blow held one 9 frames past its own end, live i1_000 f 73485)."""
    other = (tr.marks & km.MK_FREEZE) != 0
    out = ((tr.ts < 0.999) & (modes != km.M_HURT_FREEZE)) | other
    fr = modes == km.M_HURT_FREEZE
    for a in np.flatnonzero(km._onset(fr)):
        b = a
        while b + 1 < len(fr) and fr[b + 1]:
            b += 1
        if other[max(a - 1, 0):b + 2].any():
            out[a:b + 2] = True
    return out


def categorize(tr: Trace, horizon: int, modes: np.ndarray, events: np.ndarray, terrains: dict,
               frame_time_max: float = 0.018) -> tuple[np.ndarray, np.ndarray]:
    """(starts, label per window) for every row i with i + horizon inside the trace (see the module docstring)."""
    n = len(tr)
    starts = np.arange(max(n - horizon, 0))
    I = starts[:, None] + np.arange(0, horizon + 1)[None, :]
    lab = np.full(len(starts), "plain:run", dtype=object)
    if not len(starts):
        return starts, lab
    mw = modes[I]
    ew = events[I[:, 1:]]
    mk = tr.marks[I]
    valid = tr.valid & np.isfinite(tr.box[:, 0])
    gap = np.r_[False, np.diff(tr.f) != 1]
    scene_ok = np.array([tr.scenes[s] in terrains for s in tr.scene[starts]])
    centre = 0.5 * (tr.box[:, :2] + tr.box[:, 2:])
    c = centre[I]
    with np.errstate(invalid="ignore"):
        moved = np.nanmax(np.linalg.norm(c - c[:, :1], axis=2), axis=1)
    air = ~tr.flag("onGround")
    j_on = km._onset(tr.flag("jumping"))
    a_on = km._onset(tr.flag("attacking") | tr.flag("upAttacking"))
    order = [  # later entries win
        ("plain:air", air[I].any(axis=1)),
        ("plain:attack", a_on[I[:, 1:]].any(axis=1)),
        ("plain:jump", j_on[I[:, 1:]].any(axis=1)),
        ("plain:idle", ~(moved > 0.1)),
        ("downspike", np.isin(mw, (km.M_DS_ANTIC, km.M_DS_SPIKE)).any(axis=1)),
        ("cast", (mw == km.M_CAST).any(axis=1)),
        ("bind", (mw == km.M_BIND).any(axis=1)),
        ("recovering", np.isin(mw[:, 0], (km.M_HURT_FREEZE, km.M_HURT_RECOIL))),
        ("contact", (ew & CONTACT).any(axis=1)),
        ("hurt", (ew & HURT).any(axis=1)),
        ("world_freeze", world_slow(tr, modes)[I].any(axis=1)),
        ("hitch", (tr.udt[I[:, 1:]] > frame_time_max).any(axis=1)),
        ("uncovered:nail_charge", tr.flag("nailCharging")[I].any(axis=1)),
        ("uncovered:locked", (mw == km.M_LOCKED).any(axis=1)),
        ("uncovered:scene", (mk & km.MK_SCENE).any(axis=1)),
        ("uncovered:death", (mk & km.MK_DEATH).any(axis=1)),
        ("uncovered:hazard", (mk & km.MK_HAZARD).any(axis=1)),
        ("uncovered:harness", (mk & km.MK_HARNESS).any(axis=1)),
        ("uncovered:slide", (mk & km.MK_SLIDE).any(axis=1)),
        ("uncovered:no_terrain", ~scene_ok),
        ("uncovered:gap", gap[I[:, 1:]].any(axis=1)),
        ("uncovered:invalid", ~valid[I].all(axis=1)),
    ]
    for name, sel in order:
        lab[sel] = name
    return starts, lab


def _stats(err: np.ndarray, tol: float) -> dict:
    """Share within tol over all entries (NaN, a window that could not be run, counts as a miss)."""
    if len(err) == 0:
        return {"n": 0}
    ok = np.isfinite(err)
    e = err[ok]
    out = {"n": int(len(err)), "within": round(float(np.mean(np.where(ok, err, np.inf) <= tol)), 5)}
    if len(e):
        out.update({"p50": round(float(np.percentile(e, 50)), 4), "p95": round(float(np.percentile(e, 95)), 4),
                    "p99": round(float(np.percentile(e, 99)), 4), "max": round(float(e.max()), 3)})
    if not ok.all():
        out["not_run"] = int((~ok).sum())
    return out


def _groups(tr: Trace, starts: np.ndarray, horizon: int, terrains: dict) -> list[tuple[np.ndarray, Terrain2D]]:
    """Window index groups that share a terrain: per scene, gates closed unless a logged box of the window overlaps
    one (the hero walked through an open gate)."""
    out = []
    for scene_i in np.unique(tr.scene[starts]):
        sel = np.flatnonzero(tr.scene[starts] == scene_i)
        terrain = terrains.get(tr.scenes[scene_i], Terrain2D.empty())
        closed = np.ones(len(sel), dtype=bool)
        for g in terrain.gates:
            b = tr.box[starts[sel][:, None] + np.arange(0, horizon + 1)[None, :]]
            with np.errstate(invalid="ignore"):
                hit = (b[..., 2] > g[0]) & (b[..., 0] < g[2]) & (b[..., 3] > g[1]) & (b[..., 1] < g[3])
            closed &= ~hit.any(axis=1)
        out.append((sel[closed], terrain))
        out.append((sel[~closed], terrain.open()))
    return [(s, t) for s, t in out if len(s)]


def check_trace(tr: Trace, terrains: dict[str, Terrain2D], params: HeroParams, horizon: int = 30,
                tol: float = 0.1, settings: tuple[str, ...] = SETTINGS, bounds: bool = True,
                batch: int = 16384) -> dict:
    """Run every covered window of one trace in each setting; returns the per-window errors (NaN: not run)."""
    modes = km.classify_modes(tr)
    events = km.derive_events(tr, modes)
    starts, labels = categorize(tr, horizon, modes, events, terrains, params.frame_time_max)
    run = np.flatnonzero([not lab.startswith("uncovered:") or lab in ("uncovered:locked", "uncovered:harness",
                                                                      "uncovered:hazard", "uncovered:scene",
                                                                      "uncovered:nail_charge", "uncovered:death",
                                                                      "uncovered:slide", "uncovered:no_terrain")
                          for lab in labels])
    # windows that cannot be run at all (an invalid frame or a gap inside) stay NaN; the other uncovered ones are run
    # and reported, so their figures show what the model does there
    run = run[np.isfinite(tr.box[starts[run], 0]) & tr.valid[starts[run]]]
    table = km.state_table(tr, params, modes)
    out: dict = {"starts": starts, "labels": labels}
    names = list(settings) + ([BOUNDS] if bounds else [])
    for s in names:
        out[s] = {"phys": np.full(len(starts), np.nan), "pos": np.full(len(starts), np.nan)}
    if bounds:
        out[BOUNDS]["spread"] = np.full(len(starts), np.nan)
    centre = 0.5 * (tr.box[:, :2] + tr.box[:, 2:])
    for sel, terrain in _groups(tr, starts[run], horizon, terrains):
        for b0 in range(0, len(sel), batch):
            part = run[sel[b0:b0 + batch]]
            st = starts[part]
            S = km.estimate_state(tr, st, params, terrain=terrain, table=table)
            I = st[:, None] + np.arange(1, horizon + 1)[None, :]
            end = st + horizon
            for s in names:
                ev = None if s.endswith("inputs") else events[I]
                if s.startswith("replay"):
                    r = km.rollout(S, tr.mask[I], params, terrain, events=ev, dt=tr.dt[I], fs=tr.fs[I],
                                   udt=tr.udt[I])
                elif s == BOUNDS:
                    r = km.rollout(S, tr.mask[I], params, terrain, events=ev, variants="bounds")
                else:
                    r = km.rollout(S, tr.mask[I], params, terrain, events=ev)
                if s == BOUNDS:
                    b, lb = r.bound[:, horizon], tr.box[end]
                    exc = np.maximum.reduce([b[:, 0] - lb[:, 0], b[:, 1] - lb[:, 1], lb[:, 2] - b[:, 2],
                                             lb[:, 3] - b[:, 3], np.zeros(len(b))])
                    out[s]["phys"][part] = exc
                    out[s]["spread"][part] = np.maximum(b[:, 2] - b[:, 0], b[:, 3] - b[:, 1]) - \
                        np.maximum(lb[:, 2] - lb[:, 0], lb[:, 3] - lb[:, 1])
                    out[s]["pos"][part] = exc
                    continue
                out[s]["phys"][part] = np.linalg.norm(r.centre[:, horizon] - centre[end], axis=1)
                out[s]["pos"][part] = np.linalg.norm(r.pos[:, horizon] - tr.pos[end], axis=1)
    return out


# ---- knockback ------------------------------------------------------------------------------------------------

def check_knockback(tr: Trace, terrains: dict[str, Terrain2D], params: HeroParams, tol: float = 2e-3,
                    modes: np.ndarray | None = None) -> dict:
    """Every logged hit (recoilFrozen onset) against the envelope from its logged hit box: per hit, the no-input
    frames inside union[k] and the swept hull (past the table length, stacked freezes: the swept hull only, counted
    as beyond_table_frames), the later frames (control back, up to the table length) inside union[k]. tol absorbs
    float noise in the logged boxes only (2 mm)."""
    from ssbot.knowledge.knockback import knockback_boxes, knockback_table

    modes = km.classify_modes(tr) if modes is None else modes
    n = len(tr)
    frozen = tr.flag("recoilFrozen")
    hits = np.flatnonzero(km._onset(frozen))
    valid = tr.valid & np.isfinite(tr.box[:, 0])
    noinp = np.isin(modes, km.NO_INPUT)
    stop = (tr.marks & (km.MK_HARNESS | km.MK_HAZARD | km.MK_SCENE | km.MK_DEATH | km.MK_SLIDE)) != 0
    skipped: Counter = Counter()
    todo: dict[tuple, list] = {}
    for i in hits:
        side = tr.dmg[i] if tr.dmg[i] != 0 else (tr.dmg[i - 1] if i > 0 else 0)
        if not valid[i]:
            skipped["invalid_hit_frame"] += 1
            continue
        if side == 0:
            skipped["no_damage_side"] += 1
            continue
        terrain = terrains.get(tr.scenes[tr.scene[i]])
        if terrain is None:
            skipped["no_terrain"] += 1
            terrain = Terrain2D.empty()        # unclipped: a superset of the clipped path, still checked
        k_end = i
        while k_end + 1 < n and valid[k_end + 1] and noinp[k_end + 1] and not stop[k_end + 1]:
            k_end += 1
        b = tr.box[i:k_end + 1]
        opened = any(((b[:, 2] > g[0]) & (b[:, 0] < g[2]) & (b[:, 3] > g[1]) & (b[:, 1] < g[3])).any()
                     for g in terrain.gates)
        key = (tr.scenes[tr.scene[i]], opened, "left" if side < 0 else "right")
        todo.setdefault(key, []).append((i, k_end, terrain.open() if opened else terrain))
    res = {"hits": int(len(hits)), "checked": 0, "skipped": dict(skipped), "frames": 0, "after_frames": 0,
           "misses": [], "after_misses": 0, "worst_excursion_u": 0.0, "worst_after_u": 0.0, "tol_u": tol,
           "delayed_hits": 0, "slope_bound": 0, "concurrent_freezes": {}, "beyond_table_frames": 0}
    conc: Counter = Counter()
    for (scene, opened, side), items in todo.items():
        terrain = items[0][2]
        table = knockback_table(params, side)
        F = table.frames
        idx = np.array([it[0] for it in items])
        swept, frames, flags = knockback_boxes(tr.box[idx], side, params, terrain, per_frame=True, table=table)
        for m, (i, k_end, _) in enumerate(items):
            res["checked"] += 1
            res["slope_bound"] += int((flags[m] & 2) != 0)
            fz = 0
            if tr.freeze is not None:
                fz = int(np.bitwise_or.reduce(tr.freeze[i:min(k_end + 2, n)]))
            for bit, name in km.FZ_NAMES.items():
                if fz & bit and bit not in (km.FZ_RECOIL, km.FZ_ENEMY_DEATH):
                    conc[name] += 1
            if k_end - i > table.timing.ctl_nominal[1] + 1:
                res["delayed_hits"] += 1
            worst, worst_k = 0.0, -1
            for k in range(0, k_end - i + 1):
                j = i + k
                bj, s = tr.box[j], swept[m]
                u = frames[m, k] if k <= F else s       # past the table: the swept hull holds every no-input frame
                exc = max(u[0] - bj[0], u[1] - bj[1], bj[2] - u[2], bj[3] - u[3],
                          s[0] - bj[0], s[1] - bj[1], bj[2] - s[2], bj[3] - s[3], 0.0)
                res["frames"] += 1
                res["beyond_table_frames"] += int(k > F)
                if exc > worst:
                    worst, worst_k = exc, k
            res["worst_excursion_u"] = max(res["worst_excursion_u"], worst)
            if worst > tol:
                res["misses"].append({"f": int(tr.f[i]), "k": worst_k, "excursion_u": round(worst, 4),
                                      "side": side, "no_input_frames": int(k_end - i + 1),
                                      "freezes": [nm for bit, nm in km.FZ_NAMES.items() if fz & bit]})
            for k in range(k_end - i + 1, F + 1):
                j = i + k
                if j >= n or not valid[j] or stop[j] or tr.scene[j] != tr.scene[i]:
                    break
                bj, u = tr.box[j], frames[m, k]
                exc = max(u[0] - bj[0], u[1] - bj[1], bj[2] - u[2], bj[3] - u[3], 0.0)
                res["after_frames"] += 1
                res["after_misses"] += int(exc > tol)
                res["worst_after_u"] = max(res["worst_after_u"], exc)
    res["concurrent_freezes"] = dict(conc)
    res["worst_excursion_u"] = round(res["worst_excursion_u"], 4)
    res["worst_after_u"] = round(res["worst_after_u"], 4)
    res["ok"] = not res["misses"] and res["after_misses"] == 0
    return res


# ---- runtime monitor ------------------------------------------------------------------------------------------

def check_monitor(tr: Trace, terrains: dict[str, Terrain2D], params: HeroParams) -> dict:
    """The trace through StateTracker + ResidualMonitor frame by frame, a fresh pair per scene."""
    H = 30
    scored: Counter = Counter()
    inside: Counter = Counter()
    nominal: Counter = Counter()
    states: Counter = Counter()
    dropped = 0
    roll_within, roll_far, misses_max, far_max = [], [], 0, 0
    trk = mon = None
    scene = None
    terrain = None
    for i in range(len(tr)):
        if tr.scene[i] != scene:
            if mon is not None:
                scored.update(mon.scored)
                inside.update(mon.inside)
                nominal.update(mon.nominal_inside)
                dropped += mon.dropped
            scene = tr.scene[i]
            terrain = terrains.get(tr.scenes[scene])
            trk, mon = km.StateTracker(params, terrain), km.ResidualMonitor(params, terrain)
        r = tr.row(i)
        if terrain is None:
            r["valid"] = False
        trk.push_row(r)
        k0 = mon.scored[H]
        mon.update(trk)
        if mon.scored[H] > k0:
            st = mon.status()
            states[st["state"]] += 1
            a = st["horizons"][H]
            misses_max, far_max = max(misses_max, a["misses"]), max(far_max, a["far"])
            if a["n"] >= mon.window:
                roll_within.append(a["within"])
                roll_far.append(a["far"])
    if mon is not None:
        scored.update(mon.scored)
        inside.update(mon.inside)
        nominal.update(mon.nominal_inside)
        dropped += mon.dropped
    out = {"frames": len(tr), "scored": {int(h): n for h, n in scored.items()}, "dropped": dropped,
           "inside": {int(h): round(inside[h] / n, 5) for h, n in scored.items() if n},
           "nominal_inside": {int(h): round(nominal[h] / n, 5) for h, n in scored.items() if n},
           "states": dict(states), "misses_max": misses_max, "far_max": far_max}
    if roll_within:
        out["rolling_within_min"] = round(float(min(roll_within)), 4)
        out["rolling_far_max"] = int(max(roll_far))
    return out


# ---- report ---------------------------------------------------------------------------------------------------

def summarize(results: list[dict], tol: float, horizon: int) -> dict:
    labels = np.concatenate([r["labels"] for r in results]) if results else np.array([], dtype=object)
    rep: dict = {"horizon_frames": horizon, "tol_u": tol, "windows": int(len(labels)),
                 "categories": dict(Counter(labels.tolist()).most_common()),
                 "knockback": [r["knockback"] for r in results if "knockback" in r]}
    covered = np.array([not lab.startswith("uncovered") for lab in labels], dtype=bool)
    names = [s for s in (*SETTINGS, BOUNDS) if results and s in results[0]]
    for setting in names:
        e_phys = np.concatenate([r[setting]["phys"] for r in results])
        e_pos = np.concatenate([r[setting]["pos"] for r in results])
        s = {"all": {"phys": _stats(e_phys, tol), "pos": _stats(e_pos, tol)},
             "covered": {"phys": _stats(e_phys[covered], tol), "pos": _stats(e_pos[covered], tol)},
             "by_category": {}}
        if setting == BOUNDS:
            sp = np.concatenate([r[setting]["spread"] for r in results])[covered]
            sp = sp[np.isfinite(sp)]
            if len(sp):
                s["hull_spread_u"] = {"p50": round(float(np.percentile(sp, 50)), 4),
                                      "p95": round(float(np.percentile(sp, 95)), 4),
                                      "p99": round(float(np.percentile(sp, 99)), 4)}
        plain = np.array([lab.startswith("plain:") for lab in labels], dtype=bool)
        s["by_category"]["plain"] = {"phys": _stats(e_phys[plain], tol), "pos": _stats(e_pos[plain], tol)}
        for cat in sorted(set(labels.tolist())):
            m = labels == cat
            s["by_category"][cat] = {"phys": _stats(e_phys[m], tol), "pos": _stats(e_pos[m], tol)}
        rep[setting] = s
    return rep


def format_report(rep: dict) -> str:
    lines = [f"windows {rep['windows']} (horizon {rep['horizon_frames']} frames, tol {rep['tol_u']} u)"]
    for kb in rep.get("knockback", ()):
        lines.append(f"knockback: {kb['hits']} hits, {kb['checked']} checked (skipped {kb['skipped']}), "
                     f"{kb['frames']} no-input frames, {len(kb['misses'])} hits escape (worst {kb['worst_excursion_u']}"
                     f" u); after control {kb['after_frames']} frames, {kb['after_misses']} outside; "
                     f"{kb['delayed_hits']} delayed hits, {kb.get('beyond_table_frames', 0)} no-input frames past the "
                     f"table, {kb['slope_bound']} with a slope in reach, concurrent freezes "
                     f"{kb['concurrent_freezes']}")
        for m in kb["misses"][:20]:
            lines.append(f"   escape f={m['f']} k={m['k']} by {m['excursion_u']} u ({m['side']}, "
                         f"{m['no_input_frames']} no-input frames, freezes {m['freezes']})")
    for setting in (*SETTINGS, BOUNDS):
        if setting not in rep:
            continue
        s = rep[setting]
        a, c = s["all"], s["covered"]
        extra = f"  hull spread {s['hull_spread_u']}" if "hull_spread_u" in s else ""
        lines.append(f"{setting}: all {a['phys'].get('within', 0):.4f}  covered {c['phys'].get('within', 0):.4f}"
                     f" (pos {c['pos'].get('within', 0):.4f}, n={c['phys'].get('n', 0)}){extra}")
        for cat, v in s["by_category"].items():
            p = v["phys"]
            if not p.get("n"):
                continue
            lines.append(f"   {cat:24s} n={p['n']:7d} within={p.get('within', 0):.4f} p50={p.get('p50', 0):.4f} "
                         f"p99={p.get('p99', 0):.3f} max={p.get('max', 0):.2f}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sources", nargs="+")
    ap.add_argument("--params", default=str(km.DEFAULT_PARAMS))
    ap.add_argument("--horizon", type=int, default=30)
    ap.add_argument("--tol", type=float, default=0.1)
    ap.add_argument("--scene", default=None, help="only windows in this scene")
    ap.add_argument("--json", default=None, help="write the report here")
    ap.add_argument("--worst", type=int, default=10, help="list the worst covered windows (planner_events)")
    ap.add_argument("--no-windows", action="store_true", help="knockback section only")
    ap.add_argument("--monitor", action="store_true", help="also replay the runtime residual monitor")
    a = ap.parse_args(argv)
    params = HeroParams.load(a.params)
    results = []
    for src in a.sources:
        t0 = time.time()
        tr, terrains = load_source(src, params, a.scene)
        res = check_trace(tr, terrains, params, a.horizon, a.tol) if not a.no_windows else \
            {"labels": np.array([], dtype=object)}
        res["knockback"] = check_knockback(tr, terrains, params)
        if a.monitor:
            res["monitor"] = check_monitor(tr, terrains, params)
            print(f"   monitor {json.dumps(res['monitor'])}", file=sys.stderr)
        res["source"] = src
        results.append(res)
        print(f"{src}: {len(tr)} frames, {len(res['labels'])} windows, {time.time() - t0:.1f} s", file=sys.stderr)
        if a.worst and not a.no_windows:
            e = res["planner_events"]["phys"]
            cov = np.array([not lab.startswith("uncovered") for lab in res["labels"]])
            order = np.argsort(-np.where(cov & np.isfinite(e), e, -1))[:a.worst]
            for k in order:
                if e[k] > a.tol:
                    print(f"   worst f={int(tr.f[res['starts'][k]])} err={e[k]:.3f} {res['labels'][k]}",
                          file=sys.stderr)
    rep = summarize(results, a.tol, a.horizon) if not a.no_windows else \
        {"knockback": [r["knockback"] for r in results], "windows": 0, "horizon_frames": a.horizon, "tol_u": a.tol}
    if a.monitor:
        rep["monitor"] = [r["monitor"] for r in results]
    rep["sources"] = a.sources
    rep["params"] = a.params
    print(format_report(rep))
    if a.json:
        Path(a.json).write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8")
    return 0 if all(kb["ok"] for kb in rep["knockback"]) else 1


if __name__ == "__main__":
    sys.exit(main())
