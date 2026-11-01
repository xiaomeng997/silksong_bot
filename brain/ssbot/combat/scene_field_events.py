"""Low-frequency event-time ground scene field, independent of action selection.

Ported from the independently checked task-42 builder (sha256 9e66a80dc4d3).
The full three-clock / two-hypothesis / four-capability field uses two fused
Numba kernels and reusable static motion samples. Model arrays are explicit
inputs; this module reads no files, hero position, candidate paths or future
recording states. No running policy imports it yet.

Scope: one locked CC_JUMP_CAST, two Clappers, ground layer and the documented
idle/walk companion assumption. Unsupported states stay unknown. The temporary
illustration total must not be used to compare different arrival times until
its coverage-dependent scale is resolved; component masks remain separate.
Normal planner path safety remains authoritative.

Call warmup() and prepare() during startup, outside measured decisions. Pin one
complete FieldSet for all queries of a tick; SceneFieldSetCache builds it once
per refresh, rather than rebuilding all 72 grids per requested layer. Cache and
preparation are single-owner APIs and introduce no worker thread.

Output selection (task 45): build(select=Selection(...)) makes only the
requested soft-field outputs, e.g. NOMINAL_EGRESS (nominal world, egress, all
four capability layers, both hypotheses). It selects outputs only: every model
world keeps its clock and knots, and hazards, scope, margins, templates and
unknown handling are unchanged; the selected grids and raw arrays are bitwise
those of the full build. Unselected outputs query as NaN / known False /
'not_selected_in_build'. A partial selection is part of cache_key(), so a full
and a partial snapshot never share a key. select=None is the full field.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass, field
from typing import Optional
from types import MappingProxyType

import numpy as np
from numba import njit

CLAPPER = "Song Heavy Sentry"
WORLDS = ("early", "nominal", "late")
HYPS = ("delayed_only", "bounded_hold")
LAYER_BASE = ("ground_wait", "ground_run_L", "ground_run_R")
LAYER_JUMP = ("ground_jump_none", "ground_jump_L", "ground_jump_R")
LAYER_DASH = ("ground_dash_L", "ground_dash_R")
LAYER_SPRINT = ("dash_sprint_L", "dash_sprint_R")
LAYERS = ("ground_run_wait", "ground_jump_ready", "ground_dash_ready", "ground_jump_dash_ready")
COMPONENTS = ("egress", "room", "total")
KNOT_NAMES = ("origin", "seal", "landing_buddy_free", "circle_on", "circle_off")
OTHER_HELD_STATES = ("Idle", "Walk")     # the other's states the bounded hold may stand for (no committed motion)
SELECTION_KEY_VERSION = "task45-output-selection-v1"


@dataclass(frozen=True)
class Selection:
    """Soft-field outputs build() makes (task 45): nonempty subsets, kept in the model order."""
    worlds: tuple = WORLDS
    hyps: tuple = HYPS
    layers: tuple = LAYERS
    components: tuple = COMPONENTS

    def __post_init__(self):
        for name, allowed in (("worlds", WORLDS), ("hyps", HYPS), ("layers", LAYERS), ("components", COMPONENTS)):
            v = getattr(self, name)
            v = (v,) if isinstance(v, str) else tuple(v)
            if not v or len(set(v)) != len(v) or any(x not in allowed for x in v):
                raise ValueError(f"selection {name} must be a nonempty subset of {allowed}, got {v!r}")
            object.__setattr__(self, name, tuple(x for x in allowed if x in v))

    @property
    def is_full(self) -> bool:
        return (self.worlds, self.hyps, self.layers, self.components) == (WORLDS, HYPS, LAYERS, COMPONENTS)

    def key(self) -> tuple:
        """Discrete descriptor (strings only) that cache_key() appends for a partial selection."""
        return (SELECTION_KEY_VERSION, self.worlds, self.hyps, self.layers, self.components)


FULL_SELECTION = Selection()
NOMINAL_EGRESS = Selection(worlds=("nominal",), components=("egress",))   # all four layers, both hypotheses


def _selection(select):
    if select is None:
        return FULL_SELECTION
    if not isinstance(select, Selection):
        raise TypeError("select must be a scene_field_events.Selection or None")
    return select


@dataclass(frozen=True)
class Inputs:
    """Explicit model inputs (no file access here).  Arrays are copied read-only by the loader."""
    frame_time: float              # templates.npz frame_time (nominal rendered frame, s)
    t_names: tuple                 # template names: the 14 of task 34, then the task 40 dash-sprint pair
    t_centre: np.ndarray           # [n, 85, 2] hurtbox-centre path (u); dash-sprint y = the standing centre
    t_vel: np.ndarray              # [n, 85, 2]
    t_ground: np.ndarray           # [n, 85] bool: on the ground in that frame (flags & 1; dash-sprint all True)
    hurtbox_half: tuple            # (0.25, 1.0394) templates model / HERO_HALF_U (hitbox_tables.py:86)
    clock: dict                    # {branch: {"land": {w: s}, "lit": {w: s}}, "lit_duration_s", "ground_centre_y"}
    head_lead_s: dict              # {branch: s}: landing - head-height time (descent40 lead_head_to_L_s p50)
    rune_r: float                  # 7.187 (clapper.py:95 radius; Root's raw CircleCollider r 7.186814 rounds here)
    du_by_face: tuple              # (left, right) 6.48 / 6.75 (clapper.py:95 du_by_face)
    wall_zone: tuple               # (19.5, 45.5) (clapper.py:57 WALL_ZONE): open / wall clock branch
    slam_range_half_x: float       # 8.05 (forum.md 10.2 AlertRange; position_port Constants)
    slam_range_y: tuple            # (-4.46, 3.37) relative to the Clapper pos y
    escape_wall_u: float           # 6.0 (forum.md:159: an evade with a wall within 6 u behind = Escape Jump)
    standing_box_y: tuple          # (3.015, 5.094) the standing hero box y (forum_products FLOOR_Y)
    source: dict = field(default_factory=dict)   # file -> sha256, filled by the loader (identity only)


@dataclass(frozen=True)
class Config:
    x_step: float = 1.0                    # coarse grid (Root's soft stride 2 of the 0.5 u component grid)
    margin: float = 0.5                    # hazard / body margin of Root's conditional_egress
    start_delays: tuple = tuple(float(v) for v in np.arange(6) * .2)   # Root's ground start delays (s)
    count_cap: float = 3.0                 # Root SoftConfig.move_kind_cap
    slack_cap_s: float = 0.8               # Root SoftConfig.ground_delay_cap_s
    count_share: float = 0.5               # Root SoftConfig.count_share
    room_cap_u: float = 16.0               # Root SoftConfig.aim_space_cap_u, reused as the room cap
    smooth_fwhm_u: Optional[float] = None  # None: the other Clapper's body box width in the scene (about 3.59 u)
    smooth_truncate_sigma: float = 2.0
    weights: tuple = (("egress", 0.7), ("room", 0.3))    # TEMPORARY illustration only, not fitted, not tuned
    ground_tolerance_u: float = 0.05       # Root SoftConfig.ground_tolerance_u: a query y this close is the ground row
    # task 41 changes against Root's v0 reference (each can be switched off; all off = Root's v0 numbers):
    sprint_in_dash_layers: bool = True     # the task 40 dash-sprint pair joins the dash layers
    hold_until_buddy_free: bool = True     # the other's body is definite only until buddy free, then unknown region
    caster_from_seal: bool = True          # the caster's landing body from the head-height seal, not the landing
    cap_wait_in_footprint: bool = True     # waiting inside the footprint credited only up to the known horizon
    full_template_eval: bool = True        # check each delayed template to its end (Root's window cut it at the
                                           # circle's end: at late knots "wait d, then run" was only waiting)
    caster_hold_end_after_off_s: Optional[float] = 0.15   # the caster's landing body is definite up to circle off
                                           # + this (Root's window end), then an unknown region; None = never ends
    knots_rel: Optional[tuple] = None      # None: the event knots; a tuple = fixed times after the origin (Root check)
    y0_override: Optional[float] = None    # Root check only: Root's grid y (4.0545) instead of the model's

    def __post_init__(self):
        w = dict(self.weights)
        if set(w) != {"egress", "room"} or any(not (math.isfinite(v) and v >= 0) for v in w.values()):
            raise ValueError("weights must be non-negative for egress and room")
        for v in (self.x_step, self.count_cap, self.slack_cap_s, self.room_cap_u, self.smooth_truncate_sigma):
            if not (math.isfinite(v) and v > 0):
                raise ValueError("non-positive config constant")
        if not (0 <= self.count_share <= 1 and self.margin >= 0 and self.ground_tolerance_u >= 0):
            raise ValueError("invalid config constant")


def _insufficient(reason, detail):
    return {"status": "insufficient_coverage", "reason": reason, "detail": detail}


def _control(row):
    for fs in row.get("fsms") or []:
        if fs.get("name") == "Control":
            return fs.get("state"), fs.get("t")
    return None, None


def project(scene: dict):
    """Origin features only (the digest of this dict is the field identity).  Returns (features, None) or
    (None, insufficient-coverage dict)."""
    rows = [r for r in scene["enemies"]["rows"] if r.get("type_key") == CLAPPER]
    if len(rows) != 2:
        return None, _insufficient("not_two_clappers", f"{len(rows)} Clapper rows")
    aim = scene["aim"]
    if aim.get("pending_unlocked"):
        return None, _insufficient("aim_unlocked", "unlocked aims need aim-window knots and induction (not task 41)")
    locked = [a for a in aim.get("locked") or [] if a.get("family") == "CC_JUMP_CAST"]
    if len(locked) != 1:
        return None, _insufficient("not_one_locked_jump_cast", f"{len(locked)} locked CC_JUMP_CAST")
    if scene["hazards"].get("observed_damager_ents"):
        return None, _insufficient("observed_damagers", "active damagers at the origin are not modelled here")
    a = scene["arena"]
    bodies = []
    for r in sorted(rows, key=lambda r: int(r["iid"])):
        st, t = _control(r)
        bodies.append({"iid": int(r["iid"]), "root": [float(v) for v in r["root"]], "facing_s": int(r["facing_s"]),
                       "body_box": [float(v) for v in r["body_box"]], "control": st,
                       "control_t": None if t is None else float(t)})
    d = locked[0]["decision"]
    feat = {"arena": {"walls_x": [float(v) for v in a["walls_x"]], "floor_y": float(a["floor_y"]),
                      "dome_lower_edge": [[float(p), float(q)] for p, q in a["dome_lower_edge"]]},
            "bodies_now": bodies,
            "locked": {"iid": int(locked[0]["iid"]), "x_land": float(d["x_land"]), "s": int(d["s"]),
                       "decided_frames_ago": float(d["decided_frames_ago"])},
            "small_runes": [{k: float(h[k]) for k in ("x", "y", "r", "on_k", "off_k")}
                            for h in scene["hazards"]["small_runes"]["rows"] or []]}
    if feat["locked"]["iid"] not in {b["iid"] for b in bodies}:
        return None, _insufficient("caster_not_a_live_clapper", str(feat["locked"]["iid"]))
    other = next(b for b in bodies if b["iid"] != feat["locked"]["iid"])
    if other["control"] not in OTHER_HELD_STATES:
        # a committed motion (e.g. Evade Scuttle, #124 K3 / T2) needs its committed overlay first; not task 41
        return None, _insufficient("other_not_idle_or_walk", f"other Control state {other['control']!r}")
    return feat, None


def _digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _intervals_free(lo, hi, blocked):
    """Free sub-intervals of [lo, hi] after removing the union of closed blocked intervals."""
    out, cur = [], lo
    for b0, b1 in sorted((max(b0, lo), min(b1, hi)) for b0, b1 in blocked if b1 > lo and b0 < hi):
        if b0 > cur:
            out.append((cur, b0))
        cur = max(cur, b1)
    if cur < hi:
        out.append((cur, hi))
    return out


def _room(xs, lo, hi, blocked):
    """Length (u) of the free hero-centre interval holding each x; 0 inside an obstacle."""
    room = np.zeros(len(xs))
    for f0, f1 in _intervals_free(lo, hi, blocked):
        inside = (xs >= f0) & (xs <= f1)
        room[inside] = f1 - f0
    return room


def _runs(mask):
    """Connected runs of True along x: list of index arrays."""
    idx = np.flatnonzero(mask)
    if not len(idx):
        return []
    cuts = np.flatnonzero(np.diff(idx) > 1) + 1
    return np.split(idx, cuts)




class FieldSet:
    """Built field: SceneFieldGrid per (world, hypothesis, layer, component) plus raw arrays and coverage.
    query() is the minimal adapter (verbatim field_knots41.FieldSet.query; a task-45 partial selection answers its
    unselected model outputs with 'not_selected_in_build').  cache_key: discrete identity only (see cache_key());
    provenance_id: field_knots41's cache_key value (it holds t_origin_s and the body features); selection: the
    Selection the field was built with (FULL_SELECTION by default)."""

    def __init__(self, grids, meta, raw, y0, tol, cache_key, selection=None):
        self.grids = MappingProxyType(dict(grids))
        self.meta, self.raw, self.y0, self.tol = meta, raw, y0, tol
        self.cache_key = cache_key
        self.provenance_id = ("w13_event_knots41", meta["identity"])
        self.selection = _selection(selection)

    def grid(self, world, layer, hyp, component):
        return self.grids[(world, hyp, layer, component)]

    def query(self, points, *, world, layer, hyp, component):
        p = np.asarray(points, dtype=float)
        if p.ndim != 2 or p.shape[1] != 3:
            raise ValueError("points must have shape [N,3] (x, y, absolute game s)")
        key = (world, hyp, layer, component)
        n = len(p)
        if key not in self.grids:
            why = ("not_selected_in_build" if not self.selection.is_full and world in WORLDS and hyp in HYPS
                   and layer in LAYERS and component in COMPONENTS else "component_or_layer_unavailable")
            return np.full(n, np.nan), np.zeros(n, bool), np.full(n, why, object)
        ground = np.isfinite(p[:, 1]) & (np.abs(p[:, 1] - self.y0) <= self.tol)
        q = p.copy()
        q[ground, 1] = self.y0
        values, known = self.grids[key].query(q)
        values = np.where(ground, values, np.nan)
        known = known & ground
        reason = np.where(~ground, "air_layer_not_built", np.where(known, "ok", "outside_or_unknown")).astype(object)
        return values, known, reason


def _world_clocks(feat, inputs):
    L = feat["locked"]
    xl, s = L["x_land"], L["s"]
    branch = "wall" if (xl < inputs.wall_zone[0] or xl > inputs.wall_zone[1]) else "open"
    age = L["decided_frames_ago"] / 60.0          # tracker age / FT (scene.json convention; Root world_clocks)
    c = inputs.clock[branch]
    out = {}
    for w in WORLDS:
        land = c["land"][w] - age
        on = c["lit"][w] - age
        out[w] = {"branch": branch, "land": land, "on": on, "off": on + inputs.clock["lit_duration_s"],
                  "seal": land - inputs.head_lead_s[branch]}
    cx = xl + s * (inputs.du_by_face[0] if s < 0 else inputs.du_by_face[1])
    return out, {"x": cx, "y": inputs.clock["ground_centre_y"], "r": inputs.rune_r}, branch


# ======================================== task 42: preparer, kernels, build ========================================

KEY_VERSION = "task42-discrete-key-v1"


def _arena_key(arena):
    return (tuple(float(v) for v in arena["walls_x"]), float(arena["floor_y"]),
            tuple((float(p), float(q)) for p, q in arena["dome_lower_edge"]))


def _arange_len(stop, step):
    """len(np.arange(0., stop, step)) for positive finite floats: numpy's own ceil((stop - start) / step)."""
    return max(int(math.ceil((stop - 0.) / step)), 0)


class Prepared:
    """Static per (inputs, config, arena) data of the build, made once and reused (see the module docstring)."""

    def __init__(self, inputs, config, arena):
        self.inputs, self.config, self.arena_key = inputs, config, _arena_key(arena)
        hx, hy = (float(v) for v in inputs.hurtbox_half)
        walls = [float(v) for v in arena["walls_x"]]
        floor = float(arena["floor_y"])
        dome = np.asarray(arena["dome_lower_edge"], float)
        y_ground = floor + hy + .015                                   # Root ConditionalEgress.ground_y
        y0 = y_ground if config.y0_override is None else float(config.y0_override)
        xs = np.arange(math.ceil((walls[0] + hx) / .5) * .5, math.floor((walls[1] - hx) / .5) * .5 + .01, config.x_step)
        names = list(inputs.t_names)
        idx = {n: i for i, n in enumerate(names)}
        lay = {"ground_run_wait": list(LAYER_BASE), "ground_jump_ready": list(LAYER_BASE + LAYER_JUMP),
               "ground_dash_ready": list(LAYER_BASE + LAYER_DASH), "ground_jump_dash_ready": list(LAYER_BASE + LAYER_JUMP + LAYER_DASH)}
        if config.sprint_in_dash_layers:
            lay["ground_dash_ready"] += list(LAYER_SPRINT)
            lay["ground_jump_dash_ready"] += list(LAYER_SPRINT)
        used = sorted({n for v in lay.values() for n in v}, key=lambda n: idx[n])
        pos = {n: p for p, n in enumerate(used)}
        mem_off, mem_pos, mem_tid = [0], [], []
        for ln in LAYERS:
            mem_pos += [pos[n] for n in lay[ln]]
            mem_tid += [idx[n] for n in lay[ln]]
            mem_off.append(len(mem_pos))
        self.hx, self.hy, self.walls, self.floor, self.dome = hx, hy, walls, floor, dome
        self.y_ground, self.y0, self.xs, self.nx = y_ground, y0, xs, len(xs)
        self.lo, self.hi = walls[0] + hx, walls[1] - hx
        self.names, self.idx, self.lay, self.used = names, idx, lay, used
        self.used_idx = np.array([idx[n] for n in used], np.int64)
        self.mem_off = np.array(mem_off, np.int64)
        self.mem_pos = np.array(mem_pos, np.int64)
        self.mem_tid = np.array(mem_tid, np.int64)
        self.delays = np.asarray(config.start_delays, float)
        self.ft = inputs.frame_time
        self.Lc = 0
        lit_max = max(inputs.clock[b]["lit"][w] for b in ("open", "wall") for w in WORLDS)
        horizon = max(.2, lit_max + inputs.clock["lit_duration_s"] + .15)            # knot 0, age 0
        h_eval = max(horizon, float(self.delays.max()) + 84 * self.ft) if config.full_template_eval else horizon
        self.grow(_arange_len(h_eval + self.ft * .51, self.ft) + 8)
        self.n_grow = 0

    def matches(self, inputs, config, arena):
        return inputs is self.inputs and config == self.config and _arena_key(arena) == self.arena_key

    def grow(self, need):
        """Sample the reference _paths for every used template / delay up to `need` samples (prefix-identical)."""
        if need <= self.Lc:
            return
        inputs, ft, hx, hy, xs = self.inputs, self.ft, self.hx, self.hy, self.xs
        ts = np.arange(0., (need + 1) * ft, ft)                        # ts[i] = i * ft for any stop (numpy's fill)
        nL, nJ, nD = len(ts), len(self.used), len(self.delays)
        DX = np.zeros((nJ, nD, nL))
        Y = np.zeros((nJ, nD, nL))
        GF = np.full((nJ, nD, self.nx), nL, np.int64)
        duration = 84 * ft
        for p, name in enumerate(self.used):
            j = self.idx[name]
            native, vel, gr = inputs.t_centre[j], inputs.t_vel[j], inputs.t_ground[j]
            for di, delay in enumerate(self.delays):
                # the reference _paths body, element-wise on the long vector
                ix = np.minimum(np.floor(np.maximum(ts - delay, 0.) / ft + 1e-7).astype(int), 84)
                xy = native[ix] - native[0]
                beyond = ts > delay + duration
                y = np.where(gr[ix] | beyond, self.y_ground, xy[:, 1] + self.y0)
                dx = xy[:, 0] + np.where(beyond, vel[-1, 0] * (ts - delay - duration), 0.)
                X = np.clip(xs[:, None] + dx[None, :], self.walls[0] + hx, self.walls[1] - hx)
                Yb = np.broadcast_to(y[None, :], X.shape)
                # the reference floor / dome test (the same doubles), as the first failing sample per cell
                roof = np.interp(X, self.dome[:, 0], self.dome[:, 1])
                bad = (Yb - hy < self.floor - 1e-5) | (Yb + hy > roof)
                GF[p, di] = np.where(bad.any(axis=1), bad.argmax(axis=1), nL)
                DX[p, di] = dx
                Y[p, di] = y
        self.ts, self.DX, self.Y, self.GF, self.Lc = ts, DX, Y, GF, nL
        self.n_grow = getattr(self, "n_grow", 0) + 1


_PREPARED = []          # [(Prepared)], newest last; strong references keep `inputs is` identity checks valid


def prepare(inputs, config: Config = Config(), arena=None, scene=None):
    """The Prepared for (inputs, config, arena), reused when one exists (pass the arena dict or a scene)."""
    if arena is None:
        arena = scene["arena"]
    for p in _PREPARED:
        if p.matches(inputs, config, arena):
            return p
    p = Prepared(inputs, config, arena)
    _PREPARED.append(p)
    del _PREPARED[:-4]
    return p


@njit(cache=True)
def _verdicts(xs, lo, hi, ts, DX, Y, GF, Lw, nk, kn, on, off, cfrom, cuntil, hold_end,
              cx, cy, cthr, runes, ob, lb, hx, hy, m, V0, V1):
    """Raw verdicts of field_knots41.build for every used template: V0 delayed_only (0 blocked / 1 clear), V1
    bounded_hold (0 / 1 / 2 unknown), [world, knot, template, delay, cell]."""
    nW, nK = kn.shape
    nJ, nD, nL = DX.shape
    nX = xs.shape[0]
    nR = runes.shape[0]
    nRr = max(nR, 1)
    # sample windows per (world, knot): counts of leading samples outside a suffix set / inside a prefix set
    i_on = np.zeros((nW, nK), np.int64)       # lit = (t >= on) & (t <= off): i_on <= i < i_off
    i_off = np.zeros((nW, nK), np.int64)
    i_cf = np.zeros((nW, nK), np.int64)       # caster: t >= max(caster_from, 0): i >= i_cf
    i_cu = np.zeros((nW, nK), np.int64)       # caster definite: t <= caster_until: i < i_cu
    i_def = np.zeros((nW, nK, nX), np.int64)  # other definite: t <= hold_end[cell]: i < i_def
    r_on = np.zeros((nW, nK, nRr), np.int64)  # rune on = (t * 60 >= on_k) & (t * 60 <= off_k)
    r_off = np.zeros((nW, nK, nRr), np.int64)
    for w in range(nW):
        for k in range(nk[w]):
            a = kn[w, k]
            for i in range(nL):
                t = a + ts[i]
                if not (t >= on[w]):
                    i_on[w, k] += 1
                if t <= off[w]:
                    i_off[w, k] += 1
                if not (t >= cfrom[w]):
                    i_cf[w, k] += 1
                if t <= cuntil[w]:
                    i_cu[w, k] += 1
                for c in range(nX):
                    if t <= hold_end[w, c]:
                        i_def[w, k, c] += 1
                for r in range(nR):
                    if not (t * 60 >= runes[r, 3]):
                        r_on[w, k, r] += 1
                    if t * 60 <= runes[r, 4]:
                        r_off[w, k, r] += 1
    pc = np.zeros(nL + 1, np.int32)           # prefix counts over samples: circle, other's body, landing body, runes
    po = np.zeros(nL + 1, np.int32)
    pl = np.zeros(nL + 1, np.int32)
    pr = np.zeros((nRr, nL + 1), np.int32)
    for j in range(nJ):
        for d in range(nD):
            Lhi = 0
            for w in range(nW):
                for k in range(nk[w]):
                    if Lw[w, k, d] > Lhi:
                        Lhi = Lw[w, k, d]
            for c in range(nX):
                xc = xs[c]
                for i in range(Lhi):
                    x = xc + DX[j, d, i]
                    if x < lo:                # np.clip(x, lo, hi)
                        x = lo
                    if x > hi:
                        x = hi
                    y = Y[j, d, i]
                    ddx = abs(x - cx) - hx    # circle_overlap(X, Y, m)
                    if ddx < 0.:
                        ddx = 0.
                    ddy = abs(y - cy) - hy
                    if ddy < 0.:
                        ddy = 0.
                    pc[i + 1] = pc[i] + (1 if ddx * ddx + ddy * ddy <= cthr else 0)
                    po[i + 1] = po[i] + (1 if (x + hx + m >= ob[0] and x - hx - m <= ob[2]
                                               and y + hy + m >= ob[1] and y - hy - m <= ob[3]) else 0)
                    pl[i + 1] = pl[i] + (1 if (x + hx + m >= lb[0] and x - hx - m <= lb[2]
                                               and y + hy + m >= lb[1] and y - hy - m <= lb[3]) else 0)
                    for r in range(nR):
                        rdx = abs(x - runes[r, 0]) - hx
                        if rdx < 0.:
                            rdx = 0.
                        rdy = abs(y - runes[r, 1]) - hy
                        if rdy < 0.:
                            rdy = 0.
                        pr[r, i + 1] = pr[r, i] + (1 if rdx * rdx + rdy * rdy <= runes[r, 2] else 0)
                g = GF[j, d, c]
                for w in range(nW):
                    for k in range(nk[w]):
                        L = Lw[w, k, d]
                        bad = g < L
                        if not bad:
                            a0 = i_on[w, k]
                            b0 = min(i_off[w, k], L)
                            if a0 < b0 and pc[b0] - pc[a0] > 0:
                                bad = True
                        if not bad:
                            for r in range(nR):
                                a0 = r_on[w, k, r]
                                b0 = min(r_off[w, k, r], L)
                                if a0 < b0 and pr[r, b0] - pr[r, a0] > 0:
                                    bad = True
                                    break
                        q = min(i_def[w, k, c], L)
                        o_def = po[q] > 0
                        o_unk = po[L] - po[q] > 0
                        a1 = i_cf[w, k]
                        b1 = min(i_cu[w, k], L)
                        c_def = a1 < b1 and pl[b1] - pl[a1] > 0
                        a2 = max(a1, i_cu[w, k])
                        c_unk = a2 < L and pl[L] - pl[a2] > 0
                        V0[w, k, j, d, c] = 0 if bad else 1
                        if bad or o_def or c_def:
                            V1[w, k, j, d, c] = 0
                        elif o_unk or c_unk:
                            V1[w, k, j, d, c] = 2
                        else:
                            V1[w, k, j, d, c] = 1


@njit(cache=True)
def _reduce(V0, V1, allowed, delays, nk, mem_off, mem_pos, mem_tid, count, latest, witness, n_unk, lat_by):
    """field_knots41's per-layer reduction for all (world, hypothesis, layer, knot, cell) from the shared verdicts."""
    nW = V0.shape[0]
    nD = V0.shape[3]
    nX = V0.shape[4]
    nLay = mem_off.shape[0] - 1
    for w in range(nW):
        for h in range(2):
            for lay in range(nLay):
                for k in range(nk[w]):
                    for c in range(nX):
                        cnt = 0.
                        lat = -1.
                        wit = -1
                        nu = 0
                        for mi in range(mem_off[lay], mem_off[lay + 1]):
                            jj = mem_pos[mi]
                            seen = False
                            unk = False
                            best = -1.
                            for d in range(nD):
                                if allowed[w, k, d, c]:
                                    v = V0[w, k, jj, d, c] if h == 0 else V1[w, k, jj, d, c]
                                    if v == 1:
                                        seen = True
                                        if delays[d] > best:
                                            best = delays[d]
                                    elif v == 2:
                                        unk = True
                            if seen:
                                cnt += 1.
                            elif unk:
                                nu += 1
                            lat_by[w, h, lay, k, mi - mem_off[lay], c] = best
                            if best > lat:
                                wit = mem_tid[mi]
                                lat = best
                        count[w, h, lay, k, c] = cnt
                        latest[w, h, lay, k, c] = lat
                        witness[w, h, lay, k, c] = wit
                        n_unk[w, h, lay, k, c] = nu


class _Smoother:
    """field_knots41._smooth with the runs per mask and the weights per run computed once per build (the same
    expressions); each value vector still gets its own matrix-vector product, as in the reference."""

    def __init__(self, xs, sigma, trunc):
        self.xs, self.sigma, self.trunc = xs, sigma, trunc
        self.runs, self.weights = {}, {}
        self.n_calls = self.n_runs_built = self.n_weights_built = 0
        self.t = 0.

    def __call__(self, values, known):
        t0 = time.perf_counter()
        self.n_calls += 1
        key = known.tobytes()
        runs = self.runs.get(key)
        if runs is None:
            runs = self.runs[key] = _runs(known)
            self.n_runs_built += 1
        out = np.array(values, dtype=float, copy=True)
        for run in runs:
            wk = (int(run[0]), len(run))
            ws = self.weights.get(wk)
            if ws is None:
                x = self.xs[run]
                d = x[:, None] - x[None, :]
                w = np.exp(-0.5 * (d / self.sigma) ** 2) * (np.abs(d) <= self.trunc * self.sigma)
                ws = self.weights[wk] = (w, w.sum(axis=1))
                self.n_weights_built += 1
            out[run] = (ws[0] @ values[run]) / ws[1]
        self.t += time.perf_counter() - t0
        return out


_STATIC_DIGESTS = []     # [(inputs, config, digest)]


def _static_digest(config, inputs):
    """Digest of the static model identity (config + input files / constants); computed once per pair."""
    for i, c, dg in _STATIC_DIGESTS:
        if i is inputs and c == config:
            return dg
    src = None if inputs is None else {
        "source": inputs.source, "frame_time": inputs.frame_time, "t_names": list(inputs.t_names),
        "hurtbox_half": list(inputs.hurtbox_half), "clock": inputs.clock, "head_lead_s": inputs.head_lead_s,
        "rune_r": inputs.rune_r, "du_by_face": list(inputs.du_by_face), "wall_zone": list(inputs.wall_zone),
        "slam_range_half_x": inputs.slam_range_half_x, "slam_range_y": list(inputs.slam_range_y),
        "escape_wall_u": inputs.escape_wall_u, "standing_box_y": list(inputs.standing_box_y)}
    dg = _digest({"key_version": KEY_VERSION, "config": asdict(config), "inputs": src})[:16]
    _STATIC_DIGESTS.append((inputs, config, dg))
    del _STATIC_DIGESTS[:-8]
    return dg


def cache_key(scene: dict, config: Config = Config(), inputs=None, lock_id: Optional[int] = None, select=None):
    """Discrete cache key of the field build() makes from this origin; None when it is out of scope.  The d62b6e43
    SceneFieldCache holds one SceneFieldGrid, so a cache of one selected grid uses key + (world, hyp, layer, component).

    Holds: the key version, the static digest (config, input files, constants), the caster and the other's iid, the
    locked family, the lock's discrete decision fields (s, b), the layer set and an optional integer lock_id from the
    native adapter (e.g. the tracker frame of the lock, to tell two casts of one caster apart).  Never t_origin_s,
    control_t, decided_frames_ago or a continuous position: a field is reused for the cache's refresh time even while
    the bodies move (low-frequency build), and a new lock, a layer set or a config change gives a new key.  A
    partial output selection (task 45) appends its discrete Selection.key(); the full field keeps the old key."""
    sel = _selection(select)
    feat, bad = project(scene)
    if bad is not None:
        return None
    L = feat["locked"]
    other = next(b["iid"] for b in feat["bodies_now"] if b["iid"] != L["iid"])
    dec = next(a for a in scene["aim"]["locked"] if a.get("family") == "CC_JUMP_CAST" and int(a["iid"]) == L["iid"])
    b = dec["decision"].get("b")
    key = ("w13_event_knots42", KEY_VERSION, _static_digest(config, inputs), L["iid"], other, "CC_JUMP_CAST",
           int(L["s"]), None if b is None else int(b), LAYERS, None if lock_id is None else int(lock_id))
    return key if sel.is_full else key + (sel.key(),)


def build(scene: dict, inputs: Inputs, grid_cls, config: Config = Config(), t_origin_s: float = 0.0,
          prepared: Optional[Prepared] = None, stats: Optional[dict] = None, select: Optional[Selection] = None):
    """field_knots41.build, same arguments and outputs (plus prepared=, an optional stats dict to fill and the task
    45 output selection; select=None is the full field).  A selection restricts only the outputs: the verdict kernel
    runs for the selected worlds (each world's verdicts are independent of the others'), and only the selected
    hypotheses / layers / components are reduced, smoothed and built; knots, scope and descriptors stay complete."""
    sel = _selection(select)
    if not math.isfinite(t_origin_s):
        raise ValueError("t_origin_s must be finite")
    marks = [("start", time.perf_counter())]
    feat, bad = project(scene)
    if bad is not None:
        return bad
    P = prepared if prepared is not None else prepare(inputs, config, feat["arena"])
    if not P.matches(inputs, config, feat["arena"]):
        raise ValueError("prepared data belongs to other inputs / config / arena")
    marks.append(("project_prepare", time.perf_counter()))
    hx, hy = P.hx, P.hy
    walls = feat["arena"]["walls_x"]
    floor = feat["arena"]["floor_y"]
    y_ground = P.y_ground
    y0 = P.y0
    lo_x, hi_x = walls[0] + hx, walls[1] - hx
    xs = P.xs
    nx = len(xs)
    clocks, circle, branch = _world_clocks(feat, inputs)
    L = feat["locked"]
    caster = next(b for b in feat["bodies_now"] if b["iid"] == L["iid"])
    other = next(b for b in feat["bodies_now"] if b["iid"] != L["iid"])
    cb = caster["body_box"]
    land_box = [L["x_land"] + cb[0] - caster["root"][0], floor + .015,
                L["x_land"] + cb[2] - caster["root"][0], floor + .015 + (cb[3] - cb[1])]   # Root's assumed landing box
    ob = other["body_box"]
    m = config.margin
    names = P.names

    def overlap(X, Y, box, mm):
        return (X + hx + mm >= box[0]) & (X - hx - mm <= box[2]) & (Y + hy + mm >= box[1]) & (Y - hy - mm <= box[3])

    # ---- static per-cell descriptors (recomputed for every hypothetical cell; nothing frozen from the hero) ----
    ox = other["root"][0]
    hero_side = np.sign(xs - ox).astype(np.int8)                 # +1: cell right of the other
    evade_dir = (-hero_side).astype(np.int8)                     # an evade backs away from the hero (forum.md:159)
    back_wall = np.where(evade_dir < 0, ox - walls[0], np.where(evade_dir > 0, walls[1] - ox, np.nan))
    escape_open = np.where(hero_side == 0, -1, (back_wall < inputs.escape_wall_u).astype(np.int8)).astype(np.int8)
    sr = [ox - inputs.slam_range_half_x, other["root"][1] + inputs.slam_range_y[0],
          ox + inputs.slam_range_half_x, other["root"][1] + inputs.slam_range_y[1]]
    sy = inputs.standing_box_y
    in_slam_range = ((xs + hx) >= sr[0]) & ((xs - hx) <= sr[2]) & bool(sy[1] >= sr[1] and sy[0] <= sr[3])

    def circle_overlap(X, Y, mm):
        dx = np.maximum(np.abs(X - circle["x"]) - hx, 0.)
        dy = np.maximum(np.abs(Y - circle["y"]) - hy, 0.)
        return dx * dx + dy * dy <= (circle["r"] + mm) ** 2

    foot_geom = circle_overlap(xs, y_ground, 0.)
    foot_haz = circle_overlap(xs, y_ground, m)
    fg = np.flatnonzero(foot_geom)
    foot_geom_x = [float(xs[fg[0]]), float(xs[fg[-1]])] if len(fg) else None
    # the hero-centre footprint interval (margin 0) for room, exact (not the grid samples)
    dyc = max(abs(y_ground - circle["y"]) - hy, 0.)
    half = math.sqrt(max(circle["r"] ** 2 - dyc ** 2, 0.)) + hx
    foot_iv = (circle["x"] - half, circle["x"] + half)
    inside_now = np.zeros(nx, bool)
    for b in feat["bodies_now"]:
        inside_now |= overlap(xs, y0, b["body_box"], m)          # Root: time-zero current-body cells uncredited
    marks.append(("descriptors", time.perf_counter()))

    # ---- knots ----
    worlds = {}
    for w in WORLDS:
        ck = clocks[w]
        free_rel = np.where(escape_open == 1, 0.0, ck["land"])  # buddy40 buddy_free_from (lock bypassed: now)
        danger = np.where(foot_haz, ck["on"], np.inf)
        horizon_known = np.minimum(danger, free_rel)
        if config.knots_rel is None:
            ev = [("origin", 0.0), ("seal", ck["seal"]), ("landing_buddy_free", ck["land"]),
                  ("circle_on", ck["on"]), ("circle_off", ck["off"])]
            ev = [e for e in ev if e[0] == "origin" or e[1] > 1e-9]
        else:
            ev = [(f"t{i}", float(t)) for i, t in enumerate(config.knots_rel)]
        kn = np.array([t for _, t in ev])
        if np.any(np.diff(kn) <= 0):
            raise ValueError(f"knots not increasing: {ev}")
        worlds[w] = {"clock": ck, "events": ev, "knots_rel": kn, "free_rel": free_rel,
                     "known_horizon_rel": horizon_known, "danger_rel": danger}
    marks.append(("knots", time.perf_counter()))

    # ---- layers (prepared) ----
    lay = P.lay
    delays = P.delays
    nd = len(delays)

    # ---- egress verdicts: one kernel for every selected (world, knot, template, delay, cell), both hypotheses ----
    kw = sel.worlds                                                # the full field: WORLDS
    nW = len(kw)
    nks = np.array([len(worlds[w]["knots_rel"]) for w in kw], np.int64)
    nK = int(nks.max())
    kn_a = np.full((nW, nK), np.nan)
    Lw = np.zeros((nW, nK, nd), np.int64)
    on_a, off_a, cfrom_a, cuntil_a = (np.zeros(nW) for _ in range(4))
    hold_a = np.zeros((nW, nx))
    for wi, w in enumerate(kw):
        W = worlds[w]
        ck = W["clock"]
        for k, a in enumerate(W["knots_rel"]):
            kn_a[wi, k] = a
            horizon = max(.2, ck["off"] - a + .15)                 # Root conditional_egress.build
            for di, d in enumerate(delays):
                h_eval = max(horizon, d + 84 * inputs.frame_time) if config.full_template_eval else horizon
                Lw[wi, k, di] = _arange_len(h_eval + inputs.frame_time * .51, inputs.frame_time)
        hold_a[wi] = W["free_rel"] if config.hold_until_buddy_free else np.full(nx, np.inf)
        caster_from = ck["seal"] if config.caster_from_seal else ck["land"]
        cfrom_a[wi] = max(caster_from, 0.)
        cuntil_a[wi] = (np.inf if config.caster_hold_end_after_off_s is None
                        else ck["off"] + config.caster_hold_end_after_off_s)
        on_a[wi], off_a[wi] = ck["on"], ck["off"]
    P.grow(int(Lw.max()))
    runes = np.array([[h["x"], h["y"], (h["r"] + m) ** 2, h["on_k"], h["off_k"]] for h in feat["small_runes"]],
                     float).reshape(-1, 5)
    nJ = len(P.used)
    V0 = np.zeros((nW, nK, nJ, nd, nx), np.int8)
    V1 = np.zeros((nW, nK, nJ, nd, nx), np.int8)
    marks.append(("verdict_args", time.perf_counter()))
    _verdicts(xs, P.lo, P.hi, P.ts, P.DX, P.Y, P.GF, Lw, nks, kn_a, on_a, off_a, cfrom_a, cuntil_a, hold_a,
              float(circle["x"]), float(circle["y"]), float((circle["r"] + m) ** 2), runes,
              np.asarray(ob, float), np.asarray(land_box, float), hx, hy, float(m), V0, V1)
    marks.append(("verdict_kernel", time.perf_counter()))
    raw = {}
    for wi, w in enumerate(kw):
        nk = int(nks[wi])
        raw[w] = {}
        for hyp, V in (("delayed_only", V0), ("bounded_hold", V1)):
            if hyp in sel.hyps:
                r = np.zeros((nk, len(names), nd, nx), np.int8)
                r[:, P.used_idx] = V[wi, :nk]
                raw[w][hyp] = r
    marks.append(("verdict_scatter", time.perf_counter()))

    # ---- reduce per layer (one kernel; the footprint wait masks once per (world, knot)) ----
    allowed = np.zeros((nW, nK, nd, nx), np.bool_)
    for wi, w in enumerate(kw):
        W = worlds[w]
        for k, a in enumerate(W["knots_rel"]):
            if config.cap_wait_in_footprint:
                cap = np.where(foot_haz, np.maximum(W["known_horizon_rel"] - a, 0.), np.inf)
            else:
                cap = np.full(nx, np.inf)
            allowed[wi, k] = delays[:, None] <= cap[None, :] + 1e-9                  # [delay, x]
    nLay = len(LAYERS)
    mmax = int(np.diff(P.mem_off).max())
    count = np.zeros((nW, 2, nLay, nK, nx))
    latest = np.full((nW, 2, nLay, nK, nx), -1.)
    witness = np.full((nW, 2, nLay, nK, nx), -1, np.int16)
    n_unk = np.zeros((nW, 2, nLay, nK, nx), np.int16)
    lat_by = np.full((nW, 2, nLay, nK, mmax, nx), -1.)
    marks.append(("reduce_args", time.perf_counter()))
    _reduce(V0, V1, allowed, delays, nks, P.mem_off, P.mem_pos, P.mem_tid, count, latest, witness, n_unk, lat_by)
    marks.append(("reduce_kernel", time.perf_counter()))
    out = {}
    for wi, w in enumerate(kw):
        nk = int(nks[wi])
        for hi_, hyp in enumerate(HYPS):
            if hyp not in sel.hyps:
                continue
            for li, ln in enumerate(LAYERS):
                if ln not in sel.layers:
                    continue
                members = lay[ln]
                out[(w, hyp, ln)] = {"count": count[wi, hi_, li, :nk].copy(), "latest": latest[wi, hi_, li, :nk].copy(),
                                     "witness": witness[wi, hi_, li, :nk].copy(),
                                     "n_unknown": n_unk[wi, hi_, li, :nk].copy(),
                                     "latest_by_template": lat_by[wi, hi_, li, :nk, :len(members)].copy(),
                                     "members": members}
    marks.append(("reduce_out", time.perf_counter()))

    # ---- known masks, room, smoothing, totals ----
    fwhm = config.smooth_fwhm_u if config.smooth_fwhm_u is not None else (ob[2] - ob[0])
    sigma = fwhm / (2 * math.sqrt(2 * math.log(2)))
    wts = dict(config.weights)
    grids, comp = {}, {}
    o_cells = overlap(xs, y0, ob, m)
    c_cells = overlap(xs, y0, land_box, m)
    rooms = {}
    smooth = _Smoother(xs, sigma, config.smooth_truncate_sigma)
    t_grid, n_grid = 0., 0
    # the reference evaluates these two rows once per knot with the same obstacles; once here
    obst = [foot_iv, (land_box[0] - hx, land_box[2] + hx), (ob[0] - hx, ob[2] + hx)]
    room_row = _room(xs, lo_x, hi_x, obst)                         # after buddy free: kept only as a raw descriptor
    room_bodies_row = _room(xs, lo_x, hi_x, [(b["body_box"][0] - hx, b["body_box"][2] + hx)
                                             for b in feat["bodies_now"]])
    need_e = "egress" in sel.components or "total" in sel.components   # the smoothed egress feeds the total
    need_r = "room" in sel.components or "total" in sel.components
    for w in kw:
        W = worlds[w]
        ck = W["clock"]
        nk = len(W["knots_rel"])
        caster_from = ck["seal"] if config.caster_from_seal else ck["land"]
        # body cells per knot (the physical obstacles that split the floor into smoothing regions): the current
        # bodies at the origin, the other's box (held, then an unknown region), the caster's landing box from the seal
        body_cells = np.zeros((nk, nx), bool)
        body_cells[0] |= inside_now
        body_cells |= o_cells[None, :]
        body_cells |= c_cells[None, :] & (W["knots_rel"][:, None] >= caster_from)
        room_u = np.zeros((nk, nx))
        room_bodies_only = np.zeros((nk, nx))
        room_u[:] = room_row
        room_bodies_only[:] = room_bodies_row
        # after buddy free the other's position is unknown, so the free floor is unknown too (coverage); it is
        # neither frozen at the old body nor dropped (dropping it would raise the room exactly when the buddy is free)
        room_known = np.broadcast_to((W["knots_rel"] <= ck["land"] + 1e-9)[:, None], (nk, nx)).copy()
        rooms[w] = {"room_u": room_u, "room_bodies_now_only_u": room_bodies_only, "body_cells": body_cells,
                    "room_known": room_known}
        if need_r:
            room_n = np.where(room_known, np.minimum(room_u, config.room_cap_u) / config.room_cap_u, 0.)
            room_s = np.stack([np.where(body_cells[k] | ~room_known[k], room_n[k],
                                        smooth(room_n[k], ~body_cells[k] & room_known[k])) for k in range(nk)])
        times = t_origin_s + W["knots_rel"]
        for hyp in sel.hyps:
            for ln in sel.layers:
                r = out[(w, hyp, ln)]
                known = np.ones((nk, nx), bool)
                known[0] &= ~inside_now                            # Root: time-zero current-body cells uncredited
                if hyp == "bounded_hold":
                    known &= ~body_cells                           # held body / unknown region / landed caster
                e_raw = (config.count_share * np.minimum(r["count"] / config.count_cap, 1.)
                         + (1 - config.count_share) * np.minimum(np.maximum(r["latest"], 0.) / config.slack_cap_s, 1.))
                e_raw = np.where(known, e_raw, 0.)
                c = {"egress_raw": e_raw}
                if need_e:
                    e_s = np.stack([np.where(known[k] & ~body_cells[k],
                                             smooth(e_raw[k], known[k] & ~body_cells[k]), e_raw[k]) for k in range(nk)])
                    e_s = np.where(known, e_s, 0.)
                    c["egress_smoothed"] = e_s
                c["known"] = known
                vals = {}
                if "egress" in sel.components:
                    vals["egress"] = (e_s, known)
                if "room" in sel.components:
                    vals["room"] = (room_s, room_known)
                if "total" in sel.components:
                    total = np.where(known, wts["egress"] * e_s + wts["room"] * room_s, 0.)
                    c["total"] = total
                    vals["total"] = (total, known)
                tg = time.perf_counter()
                for cname, (val, kk) in vals.items():
                    grids[(w, hyp, ln, cname)] = grid_cls(times, xs, [y0], val[:, None, :], kk[:, None, :],
                                                          np.ones((1, nx), dtype=np.int16))
                    n_grid += 1
                t_grid += time.perf_counter() - tg
                comp[(w, hyp, ln)] = c
        if need_r:
            rooms[w]["room_norm"] = room_n
            rooms[w]["room_smoothed"] = room_s
    marks.append(("room_smooth_totals_grids", time.perf_counter()))

    # ---- coverage (separate layer: unknown future, missing capability, no witness, relies on waiting) ----
    coverage = {}
    for w in kw:
        W = worlds[w]
        kn = W["knots_rel"][:, None]
        relies = foot_haz[None, :] & (kn >= W["known_horizon_rel"][None, :] - 1e-9) & (kn < W["clock"]["on"])
        buddy_free_now = kn > W["free_rel"][None, :] + 1e-9
        for hyp in sel.hyps:
            for ln in sel.layers:
                r = out[(w, hyp, ln)]
                kk = comp[(w, hyp, ln)]["known"]
                coverage[(w, hyp, ln)] = {"no_witness_in_library": kk & (r["count"] == 0),
                                          "n_unknown_templates": r["n_unknown"],
                                          "relies_on_wait_until_lit": relies, "buddy_free_now": buddy_free_now,
                                          "room_unknown_buddy_free": ~rooms[w]["room_known"]}
    marks.append(("coverage", time.perf_counter()))

    ident = {"version": "task41-event-knots-v1", "features": feat, "config": asdict(config),
             "inputs": inputs.source, "t_origin_s": t_origin_s}
    if not sel.is_full:
        ident["output_selection"] = [list(v) for v in sel.key()[1:]]
    identity = _digest(ident)
    meta = {"identity": identity, "features_digest": _digest(feat), "branch": branch, "circle": circle,
            "time_base": "absolute game s = tracker seconds; t_origin_s + clock seconds after the origin",
            "t_origin_s": t_origin_s, "xs": xs, "y0": y0, "y_ground_model": y_ground,
            "worlds": {w: {"events": [(n, t_origin_s + t) for n, t in worlds[w]["events"]],
                           "events_rel": worlds[w]["events"], "clock_rel": worlds[w]["clock"]} for w in WORLDS},
            "layers": {k: list(v) for k, v in lay.items()}, "template_names": names,
            "caster": {"iid": L["iid"], "x_land": L["x_land"], "s": L["s"], "landing_box_assumed": land_box,
                       "control_now": caster["control"]},
            "other": {"iid": other["iid"], "root_x": ox, "body_box_now": ob, "control_now": other["control"],
                      "control_t": other["control_t"]},
            "footprint_hero_centre_x_m0": list(foot_iv), "footprint_grid_m0": foot_geom_x,
            "smoothing": {"fwhm_u": fwhm, "sigma_u": sigma, "truncate_sigma": config.smooth_truncate_sigma,
                          "scope": "inside connected runs of known, body-free cells of one knot / world / hypothesis / layer"},
            "weights_TEMPORARY": wts, "config": asdict(config)}
    if not sel.is_full:
        meta["output_selection"] = {"key_version": SELECTION_KEY_VERSION, "worlds": list(sel.worlds),
                                    "hyps": list(sel.hyps), "layers": list(sel.layers),
                                    "components": list(sel.components)}
    descriptors = {"hero_side_of_other": hero_side, "evade_dir": evade_dir, "back_wall_u_for_evade": back_wall,
                   "escape_jump_open": escape_open, "in_other_slam_range_standing": in_slam_range,
                   "in_footprint_m0": foot_geom, "in_footprint_hazard_margin": foot_haz,
                   "inside_body_now": inside_now, "in_other_box_margin": o_cells, "in_landing_box_margin": c_cells,
                   "buddy_free_from_abs": {w: t_origin_s + worlds[w]["free_rel"] for w in WORLDS},
                   "known_horizon_abs": {w: t_origin_s + worlds[w]["known_horizon_rel"] for w in WORLDS}}
    rawd = {"verdicts": raw, "reduced": out, "components": comp, "rooms": rooms, "coverage": coverage,
            "descriptors": descriptors, "worlds": worlds}
    marks.append(("meta_identity", time.perf_counter()))
    key = cache_key(scene, config, inputs, select=sel)
    marks.append(("cache_key", time.perf_counter()))
    if stats is not None:
        stats.update({"selection": sel.key(), "kernel_worlds": nW,
                      "kernel_calls": 2, "verdict_cells": int(nW * nK * nJ * nd * nx), "grid_keys": len(grids),
                      "grids_constructed": n_grid, "grid_construct_ms": t_grid * 1e3, "room_calls": 2,
                      "smooth_calls": smooth.n_calls, "smooth_ms": smooth.t * 1e3,
                      "smooth_runs_built": smooth.n_runs_built, "smooth_weights_built": smooth.n_weights_built,
                      "prepared_samples": P.Lc, "prepared_grows": P.n_grow, "max_samples_used": int(Lw.max()),
                      "sections_ms": {n: (t - marks[i][1]) * 1e3 for i, (n, t) in enumerate(marks[1:])},
                      "total_ms": (marks[-1][1] - marks[0][1]) * 1e3})
    return FieldSet(grids, meta, rawd, y0, config.ground_tolerance_u, key, selection=sel)


def warmup():
    """Compile (or load from the Numba cache) both kernels on tiny arrays; returns the elapsed seconds."""
    t0 = time.perf_counter()
    f = np.zeros(1)
    i1 = np.ones(1, np.int64)
    V = np.zeros((1, 1, 1, 1, 1), np.int8)
    _verdicts(f, -1., 1., np.zeros(2), np.zeros((1, 1, 2)), np.zeros((1, 1, 2)), np.zeros((1, 1, 1), np.int64),
              np.ones((1, 1, 1), np.int64), i1, np.zeros((1, 1)), f, f, f, f, np.zeros((1, 1)),
              0., 0., 1., np.zeros((0, 5)), np.zeros(4), np.zeros(4), .25, 1., .5, V, V.copy())
    _reduce(V, V.copy(), np.ones((1, 1, 1, 1), np.bool_), np.zeros(1), i1, np.array([0, 1], np.int64),
            np.zeros(1, np.int64), np.zeros(1, np.int64), np.zeros((1, 2, 1, 1, 1)), np.zeros((1, 2, 1, 1, 1)),
            np.zeros((1, 2, 1, 1, 1), np.int16), np.zeros((1, 2, 1, 1, 1), np.int16), np.zeros((1, 2, 1, 1, 1, 1)))
    return time.perf_counter() - t0


class SceneFieldSetCache:
    """Single-owner cache publishing one complete set of read-only query grids.

    The caller supplies a discrete move/lock key, calls get once per tick and
    shares the returned snapshot across candidates. A rebuild failure raises;
    it never returns the old event as if it belonged to a new key. No partial
    grid-set is published. Unknown future endpoints remain unknown in query().
    With a task-45 output selection the published set is the selected grids:
    until / cover-now apply to them, and the key must carry the selection
    (cache_key / field_key do). Use one cache per selection.
    """
    def __init__(self, refresh_s):
        if not math.isfinite(refresh_s) or refresh_s <= 0:
            raise ValueError("refresh_s must be finite and positive")
        self.refresh_s = float(refresh_s)
        self.clear()

    def clear(self):
        self._key = self._at = self._field = None
        self._until = None

    def get(self, key, now_s, build):
        if key is None:
            raise ValueError("unsupported scene has no cache key")
        hash(key)
        now_s = float(now_s)
        if not math.isfinite(now_s):
            raise ValueError("game time must be finite")
        expired = self._field is None or self._key != key
        if self._at is not None:
            expired |= now_s < self._at or now_s >= self._at + self.refresh_s or now_s > self._until
        if expired:
            field = build()
            if not isinstance(field, FieldSet) or not field.grids:
                raise TypeError("builder must return a nonempty FieldSet")
            if not all(g.times[0] <= now_s <= g.times[-1] for g in field.grids.values()):
                raise ValueError("all new field grids must cover current game time")
            until = min(g.times[-1] for g in field.grids.values())
            self._field, self._key, self._at, self._until = field, key, now_s, until
        return self._field
