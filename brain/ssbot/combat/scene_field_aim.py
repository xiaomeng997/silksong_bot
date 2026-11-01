"""Unlocked-aim induction components as a pure, callable module (Sol task 37; port of the task 35 prototype
aim35.py, whose two scenes' arrays it reproduces).

Scope, as the prototype: a w13 scene with exactly two Clappers (Song Heavy Sentry), one pending, not yet decided
CC_JUMP_CAST aim, hero standing on the floor (ground layer).  Anything else returns an explicit
insufficient-coverage result; unexpected errors are raised, never swallowed.

    res = build_aim(view, grid_x, rules, consts)

view    origin-only facts (view_from_scene() builds it from the scene.json form): the caster's and the other
        Clapper's root and body box now, the pending aim (move, iid, production decision window), and the caster
        instance's age in frames since the antic start.  No hero, no logged cue, no role, no label, nothing after
        the origin.
grid_x  hero hurtbox-centre x positions (1-D, any order, any spacing), the hero standing on the floor.
rules   RuleCallbacks: jump_rule / jump_branch bound by the caller to a source and configuration it owns (in
        production ssbot.combat.are_types.clapper.jump_rule / jump_branch, whose wall push follows
        jump_behind.WALL_PUSH), and that WALL_PUSH value, used only to label the pushed cells.
consts  Constants: every number is passed in; this module reads no file.

Each grid value means: "if the hero's hurtbox centre stands at this x at the caster's aim decision".  The result
carries the remaining decision window (game seconds and model frames FT).  A position that a row reaches only after
that window cannot change this aim; time_validity() classifies a reach time against the window.  There is no
planner and no closed loop here.

Returned: the decided landing (facing, offset, x, branch, clamped, pushed), the rune slam circle centre and the
floor interval it covers for a standing hero box, the usable floor left / right of it (also minus the other's body
now), the current bodies, both Clappers' TWO_FOCUS outer_room (now, and with the caster at that landing), the
nominal / run-lag / dash-lag layers kept apart, per-x changes inside one rule regime, and separate known / reason
flags (induced, inside a current body, backward jump, circle centre beyond a wall).  No weights, no total, no best
position, no reject: free floor is not an escape proof, and small development counts are not probabilities.

Importing this module changes no environment variable, module search path, CPU affinity or priority and reads no
file.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

SCOPE = {"enemy": "Song Heavy Sentry", "n_clappers": 2, "move": "CC_JUMP_CAST", "layer": "ground",
         "reference": "hero hurtbox centre x, standing"}

VALIDITY_RULE = ("a grid value is where the hero stands at the caster's aim decision; a position reached after the "
                 "remaining decision window cannot change this aim (time_validity)")


@dataclass(frozen=True)
class RuleCallbacks:
    """The decision rule, bound by the caller.  jump_rule(x, y, vx, hero_x, hero_y) -> (s, L) is called with vx None
    (not known before the jump) and hero_y None; jump_branch(x, s, L) -> 'open' | 'wall'."""
    jump_rule: Callable
    jump_branch: Callable
    wall_push: bool


@dataclass(frozen=True)
class Constants:
    walls: tuple                  # (WALL_L, WALL_R): core/forum.py
    hero_half: tuple              # (half width, half height): knowledge/hitbox_tables.py HERO_HALF_U
    standing_box_y: tuple         # standing hero box y range: knowledge/forum_products.py FLOOR_Y
    rune_slam_r: float            # are_types/clapper.py rune slam radius
    du_left_right: tuple          # rune slam centre offset in front of the landing, facing left / right
    ground_centre_y: float        # rune slam centre y on the floor
    ft: float                     # model frame time: attack_range.FT
    decision_s: tuple             # forum_v2.DECISION_S['CC_JUMP_CAST'] (s since the antic start)
    jump_gain: float              # clapper.JUMP_GAIN (only to label clamped / pushed cells)
    jump_short: float             # clapper.JUMP_SHORT
    jump_vx_max: float            # clapper.JUMP_VX_MAX
    wall_zone: tuple              # clapper.WALL_ZONE (the wall branch's landing x limits)
    arena_x: tuple                # Forum.yaml arena.x (TWO_FOCUS outer_room)
    wall_bin_edges: tuple = (2.0, 3.5)   # wall-branch landing-to-wall distance bins (the clock's lt2 / 2to3.5 / ge3.5)
    lag_run_u: float = 0.15       # transform-vs-hurtbox render lag band, running
    lag_dash_u: float = 0.52      # the same at dash speed
    clock: Optional[dict] = None  # optional: the conditional clocks ('clocks' of scene_field_motion clock.json)
    support: Optional[dict] = field(default=None)  # optional: development counts for the unsupported regimes


def _insufficient(reason: str, detail: str) -> dict:
    return {"status": "insufficient_coverage", "reason": reason, "detail": detail, "scope": dict(SCOPE)}


def _has(d, *path):
    """True when every key of path exists (dicts only); a present key with a wrong type is the caller's error."""
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return False
        cur = cur[k]
    return True


# ---------------------------------------------------------------- views

def view_from_scene(scene: dict) -> dict:
    """The origin view from a task 33 scene.json dict: aim.pending_unlocked, enemies.rows (the Clappers),
    tracker.instances[caster].  Reads nothing else (not the hero, cues, roles, history or labels)."""
    if not _has(scene, "aim", "pending_unlocked"):
        return _insufficient("missing_field", "aim.pending_unlocked")
    pend = scene["aim"]["pending_unlocked"]
    if len(pend) == 0:
        return _insufficient("no_pending", "no unlocked pending aim at the origin")
    if len(pend) > 1:
        return _insufficient("multiple_pending", f"{len(pend)} pending aims; the prototype covers one")
    p = pend[0]
    for k in ("iid", "move", "x", "y"):
        if k not in p:
            return _insufficient("missing_field", f"aim.pending_unlocked[0].{k}")
    if p["move"] != SCOPE["move"]:
        return _insufficient("unsupported_move", f"pending move {p['move']!r}")
    if not _has(scene, "enemies", "rows"):
        return _insufficient("missing_field", "enemies.rows")
    rows = [r for r in scene["enemies"]["rows"] if r.get("type_key") == SCOPE["enemy"]]
    if len(rows) != SCOPE["n_clappers"]:
        return _insufficient("not_two_clappers", f"{len(rows)} Clapper rows")
    ci = int(p["iid"])
    if sum(int(r["iid"]) == ci for r in rows) != 1:
        return _insufficient("missing_field", f"enemies.rows: caster iid {ci}")
    for r in rows:
        for k in ("root", "body_box"):
            if k not in r:
                return _insufficient("missing_field", f"enemies.rows[iid {r.get('iid')}].{k}")
    c = next(r for r in rows if int(r["iid"]) == ci)
    o = next(r for r in rows if int(r["iid"]) != ci)
    if abs(float(p["x"]) - float(c["root"][0])) > 1e-9 or abs(float(p["y"]) - float(c["root"][1])) > 1e-9:
        raise ValueError(f"pending anchor {p['x'], p['y']} is not the caster root {c['root']}")
    if not _has(scene, "tracker", "instances", str(ci)):
        return _insufficient("missing_field", f"tracker.instances[{ci}]")
    inst = scene["tracker"]["instances"][str(ci)]
    if "started_frames_ago" not in inst:
        return _insufficient("missing_field", f"tracker.instances[{ci}].started_frames_ago")
    if inst.get("family") != SCOPE["move"]:
        return _insufficient("unsupported_move", f"tracker family {inst.get('family')!r}")
    if inst.get("decision") is not None:
        return _insufficient("decided", "the caster's landing is already decided (a locked aim, not pending)")

    def row(r):
        return {"iid": int(r["iid"]), "root": [float(r["root"][0]), float(r["root"][1])],
                "body_box": [float(v) for v in r["body_box"]]}

    view = {"caster": row(c), "other": row(o),
            "pending": {"move": p["move"], "iid": ci,
                        "decision_window_frames": ([int(v) for v in p["decision_window_frames"]]
                                                   if "decision_window_frames" in p else None)},
            "age_frames": float(inst["started_frames_ago"])}
    if _has(scene, "origin", "f"):
        view["f"] = int(scene["origin"]["f"])
    return view


def _check_view(view: dict) -> Optional[dict]:
    if not isinstance(view, dict):
        raise TypeError("view must be a dict")
    if view.get("status") == "insufficient_coverage":
        return view
    for path in (("caster", "root"), ("caster", "body_box"), ("other", "root"), ("other", "body_box"),
                 ("pending", "move"), ("age_frames",)):
        if not _has(view, *path):
            return _insufficient("missing_field", "view." + ".".join(path))
    if view["pending"]["move"] != SCOPE["move"]:
        return _insufficient("unsupported_move", f"pending move {view['pending']['move']!r}")
    return None


# ---------------------------------------------------------------- the rule at one x

def _decide(xc: float, yc: float, hx: float, rules: RuleCallbacks, k: Constants) -> dict:
    s, L = rules.jump_rule(xc, yc, None, float(hx), None)
    s, L = int(s), float(L)
    if s not in (-1, 1) or not math.isfinite(L):
        raise ValueError(f"jump_rule returned {(s, L)!r}")
    want = (float(hx) - xc) * s - k.jump_short
    clamped = abs(want) > k.jump_vx_max
    L0 = k.jump_gain * min(max(want, -k.jump_vx_max), k.jump_vx_max)
    pushed = bool(rules.wall_push) and L > L0 + 1e-9
    br = rules.jump_branch(xc, s, L)
    if br not in ("open", "wall"):
        raise ValueError(f"jump_branch returned {br!r}")
    xl = xc + s * L
    cx = xl + s * (k.du_left_right[0] if s < 0 else k.du_left_right[1])
    if br == "wall":
        d = (xl - k.walls[0]) if xl < k.wall_zone[0] else (k.walls[1] - xl)
        wb = 0 if d < k.wall_bin_edges[0] else (1 if d < k.wall_bin_edges[1] else 2)
    else:
        d, wb = float("nan"), -1
    return {"s": s, "L": L, "x_land": xl, "branch": br, "clamped": bool(clamped), "pushed": bool(pushed),
            "cx": cx, "wall_dist": d, "wall_bin": wb}


def _outer_room(x: float, ox: float, k: Constants) -> float:
    """TWO_FOCUS room (tactics/gauntlet.py _outer_room): from a Clapper's x to the arena edge away from the other."""
    x0, x1 = k.arena_x
    return (x - x0) if x < ox else (x1 - x)


def _components(view: dict, hx: float, rules: RuleCallbacks, k: Constants) -> dict:
    half_w = float(k.hero_half[0])
    lo_hx, hi_hx = k.walls[0] + half_w, k.walls[1] - half_w
    xc, yc = float(view["caster"]["root"][0]), float(view["caster"]["root"][1])
    xo = float(view["other"]["root"][0])
    d = _decide(xc, yc, hx, rules, k)                     # at rest the transform x is the hurtbox centre x
    dl, dh = _decide(xc, yc, hx - k.lag_run_u, rules, k), _decide(xc, yc, hx + k.lag_run_u, rules, k)
    ddl, ddh = _decide(xc, yc, hx - k.lag_dash_u, rules, k), _decide(xc, yc, hx + k.lag_dash_u, rules, k)
    reach = k.rune_slam_r + half_w                        # the circle centre y lies inside the standing box's y range
    c_lo, c_hi = d["cx"] - reach, d["cx"] + reach
    fl_lo, fl_hi = lo_hx, min(c_lo, hi_hx)
    fr_lo, fr_hi = max(c_hi, lo_hx), hi_hx
    ox0, _, ox1, _ = (float(v) for v in view["other"]["body_box"])
    kx0, _, kx1, _ = (float(v) for v in view["caster"]["body_box"])
    b_lo, b_hi = ox0 - half_w, ox1 + half_w

    def minus(a, b, u, v):
        return max(0.0, b - a) - max(0.0, min(b, v) - max(a, u))

    o_cx = 0.5 * (ox0 + ox1)
    inside_o, inside_c = b_lo < hx < b_hi, kx0 - half_w < hx < kx1 + half_w
    return {
        "s": d["s"], "L": d["L"], "x_land": d["x_land"], "branch": d["branch"], "clamped": d["clamped"],
        "pushed": d["pushed"], "wall_dist": d["wall_dist"], "wall_bin": d["wall_bin"],
        "circle_cx": d["cx"], "cover_lo": c_lo, "cover_hi": c_hi, "hero_in_cover_if_stays": c_lo <= hx <= c_hi,
        "free_left_lo": fl_lo, "free_left_hi": fl_hi, "free_left_len": max(0.0, fl_hi - fl_lo),
        "free_right_lo": fr_lo, "free_right_hi": fr_hi, "free_right_len": max(0.0, fr_hi - fr_lo),
        "free_left_minus_other_body": minus(fl_lo, fl_hi, b_lo, b_hi),
        "free_right_minus_other_body": minus(fr_lo, fr_hi, b_lo, b_hi),
        "other_body_in_circle_u": max(0.0, min(ox1, d["cx"] + k.rune_slam_r) - max(ox0, d["cx"] - k.rune_slam_r)),
        "other_side": -1 if hx < o_cx else 1,
        "other_gap": (ox0 - (hx + half_w)) if hx < o_cx else ((hx - half_w) - ox1),
        "inside_other_body_x": inside_o, "inside_caster_body_x": inside_c,
        "between_now": min(xc, xo) < hx < max(xc, xo),
        "room_caster_now": _outer_room(xc, xo, k), "room_other_now": _outer_room(xo, xc, k),
        "room_caster_at_landing": _outer_room(d["x_land"], xo, k),
        "room_other_given_landing": _outer_room(xo, d["x_land"], k),
        "lag_x_land_lo": min(dl["x_land"], dh["x_land"], d["x_land"]),
        "lag_x_land_hi": max(dl["x_land"], dh["x_land"], d["x_land"]),
        "lag_branch_flip": len({dl["branch"], d["branch"], dh["branch"]}) > 1,
        "lag_facing_flip": len({dl["s"], d["s"], dh["s"]}) > 1,
        "lag_dash_x_land_lo": min(ddl["x_land"], ddh["x_land"], d["x_land"]),
        "lag_dash_x_land_hi": max(ddl["x_land"], ddh["x_land"], d["x_land"]),
        "lag_dash_branch_flip": len({ddl["branch"], d["branch"], ddh["branch"]}) > 1,
        "lag_dash_facing_flip": len({ddl["s"], d["s"], ddh["s"]}) > 1,
        "in_floor_range": lo_hx - 1e-9 <= hx <= hi_hx + 1e-9,
    }


NUMERIC = ("s", "L", "x_land", "wall_dist", "wall_bin", "circle_cx", "cover_lo", "cover_hi",
           "free_left_lo", "free_left_hi", "free_left_len", "free_right_lo", "free_right_hi", "free_right_len",
           "free_left_minus_other_body", "free_right_minus_other_body", "other_body_in_circle_u", "other_side",
           "other_gap", "room_caster_now", "room_other_now", "room_caster_at_landing", "room_other_given_landing",
           "lag_x_land_lo", "lag_x_land_hi", "lag_dash_x_land_lo", "lag_dash_x_land_hi")
BOOLEAN = ("clamped", "pushed", "hero_in_cover_if_stays", "inside_other_body_x", "inside_caster_body_x",
           "between_now", "lag_branch_flip", "lag_facing_flip", "lag_dash_branch_flip", "lag_dash_facing_flip",
           "in_floor_range")
SLOPED = ("x_land", "circle_cx", "free_left_len", "free_right_len", "room_caster_at_landing")


def _slopes(x: np.ndarray, f: dict) -> dict:
    """Per-x changes inside one rule regime (facing, branch, clamped, pushed, wall bin), on the sorted distinct x;
    a step across a regime edge is not a slope (NaN where a point has no same-regime neighbour)."""
    ux, inv = np.unique(x, return_inverse=True)
    first = np.zeros(len(ux), dtype=int)
    first[inv[::-1]] = np.arange(len(x))[::-1]
    key = np.stack([f["s"][first], f["branch_wall"][first].astype(float), f["clamped"][first].astype(float),
                    f["pushed"][first].astype(float), f["wall_bin"][first]], 1)
    n = len(ux)
    same_next = np.r_[np.all(key[1:] == key[:-1], axis=1), False] if n > 1 else np.array([False])
    same_prev = np.r_[False, same_next[:-1]] if n > 1 else np.array([False])
    out = {}
    for name in SLOPED:
        v = f[name][first]
        d = np.full(n, np.nan)
        for i in range(n):
            if same_prev[i] and same_next[i]:
                d[i] = (v[i + 1] - v[i - 1]) / (ux[i + 1] - ux[i - 1])
            elif same_next[i]:
                d[i] = (v[i + 1] - v[i]) / (ux[i + 1] - ux[i])
            elif same_prev[i]:
                d[i] = (v[i] - v[i - 1]) / (ux[i] - ux[i - 1])
        out["d_" + name + "_dhx"] = d[inv]
    return out


# ---------------------------------------------------------------- time

def decision_window(view: dict, k: Constants) -> dict:
    """The remaining decision window of the pending aim: game seconds and model frames FT (the prototype's
    recomputation), the production window as given, and, if a clock is configured, the conditional open / wall
    landing and lighting layers, kept apart."""
    age = float(view["age_frames"]) * k.ft
    lo_s, hi_s = k.decision_s[0] - age, k.decision_s[1] - age
    d_lo = max(int(math.ceil((k.decision_s[0] - age) / k.ft - 1e-6)), 0)
    d_hi = max(int(math.ceil((k.decision_s[1] - age) / k.ft - 1e-6)), d_lo)
    out = {"age_s": round(age, 4), "remaining_s": [round(lo_s, 4), round(hi_s, 4)], "remaining_ft": [d_lo, d_hi],
           "production_window_frames": view["pending"].get("decision_window_frames"),
           "decision_s": list(k.decision_s), "validity": VALIDITY_RULE}
    if k.clock is not None:
        bd = k.clock["before_decision"]
        dec = {q: round(bd["decision_after_start"][q] - age, 4) for q in ("early", "nominal", "late")}
        out["remaining_to_decision_s"] = dec
        out["branch"] = {}
        for br in ("open", "wall"):
            out["branch"][br] = {
                "remaining_to_landing_s": {q: round(bd["landing_after_start"][br][q] - age, 4)
                                           for q in ("early", "nominal", "late")},
                "remaining_to_lit_start_s": {q: round(bd["lit_start_after_start"][br][q] - age, 4)
                                             for q in ("early", "nominal", "late")},
                "n": bd["landing_after_start"][br]["n"]}
        wl = k.clock["decided_wall"]["by_decided_landing_wall_dist_u"]
        lit = k.clock["landed"]["lit_start_after_landing"]
        bins = {}
        for code, key in ((0, "lt2"), (1, "2to3.5"), (2, "ge3.5")):
            t = wl[key]["D_to_L_t"]
            land = {"early": dec["early"] + t["min"], "nominal": dec["nominal"] + t["p50"],
                    "late": dec["late"] + t["max"]}
            bins[key] = {"code": code, "n": wl[key]["n"],
                         "remaining_to_landing_s": {q: round(v, 4) for q, v in land.items()},
                         "remaining_to_lit_start_s": {q: round(land[q] + lit[q], 4) for q in ("early", "nominal", "late")}}
        out["wall_by_landing_wall_dist"] = bins
        out["clock_note"] = ("development-data support, not a guarantee; the branch a position causes picks its layer; "
                             "the layers are never merged into one reject")
    return out


def time_validity(t_reach_s: float, time: dict) -> str:
    """Whether a position reached t_reach_s after the origin can be where the hero stands at the decision:
    'before_window' (it can), 'inside_window' (only if the decision comes after it: the caller decides),
    'after_window' (it cannot change this aim)."""
    lo, hi = time["remaining_s"]
    if t_reach_s <= lo:
        return "before_window"
    if t_reach_s <= hi:
        return "inside_window"
    return "after_window"


# ---------------------------------------------------------------- the field

def build_aim(view: dict, grid_x, rules: RuleCallbacks, consts: Constants) -> dict:
    """The raw induction components on grid_x (hero hurtbox-centre x, standing).  Insufficient coverage (no / several
    pending aims, another move, not two Clappers, missing core fields, an already passed window) returns
    {'status': 'insufficient_coverage', ...}; any other error is raised."""
    bad = _check_view(view)
    if bad is not None:
        return bad
    y0, y1 = consts.standing_box_y
    cy, oct_b = consts.ground_centre_y, consts.rune_slam_r * math.tan(math.pi / 8.0)
    if not (y0 <= cy <= y1 and y1 - cy <= oct_b and cy - y0 <= oct_b):
        raise ValueError("the floor-cover formula needs the circle centre y inside the standing box y range "
                         "(and within the octagon's flat sides)")
    time = decision_window(view, consts)
    if time["remaining_s"][1] <= 0.0:
        return _insufficient("window_passed", f"age {time['age_s']} s is past the decision window {consts.decision_s}")
    x = np.asarray(grid_x, dtype=float).reshape(-1)
    if x.size == 0 or not np.all(np.isfinite(x)):
        raise ValueError("grid_x must be a non-empty finite 1-D array")
    rows = [_components(view, float(hx), rules, consts) for hx in x]
    f = {"grid_hx": x.copy()}
    for name in NUMERIC:
        f[name] = np.asarray([r[name] for r in rows], dtype=float)
    for name in BOOLEAN:
        f[name] = np.asarray([bool(r[name]) for r in rows], dtype=bool)
    f["branch"] = np.asarray([r["branch"] for r in rows])
    f["branch_wall"] = f["branch"] == "wall"
    f.update(_slopes(x, f))
    walls = consts.walls
    flags = {
        "induced": ~(f["clamped"] | f["pushed"]),
        "inside_current_body": f["inside_caster_body_x"] | f["inside_other_body_x"],
        "backward_jump": f["L"] < 0.0,
        "circle_beyond_wall": (f["circle_cx"] < walls[0]) | (f["circle_cx"] > walls[1]),
    }
    flags["no_high_value"] = flags["inside_current_body"] | flags["backward_jump"] | flags["circle_beyond_wall"]
    reasons = {
        "induced": "the landing follows the hero's x here (not clamped, not wall-pushed); elsewhere moving the hero "
                   "does not move the landing and the induction gradient is 0 within that regime",
        "inside_current_body": "the standing hero box overlaps a Clapper's current body x range: not a usable "
                               "standing position now (the bodies may move; no claim beyond now)",
        "backward_jump": "the landing is on the far side of the caster from the hero (L < 0): rare in development "
                         "data (see support), its clock and circle are unsupported: unknown, never a high value",
        "circle_beyond_wall": "the circle centre is beyond a wall: where the circle appears is unsupported (see "
                              "support): unknown, never a high value",
        "no_high_value": "any of inside_current_body / backward_jump / circle_beyond_wall; not a reject",
    }
    return {"status": "ok", "scope": dict(SCOPE), "time": time, "fields": f, "flags": flags, "reasons": reasons,
            "circle_cy": cy, "circle_r": consts.rune_slam_r,
            "bodies_now": {"caster": list(view["caster"]["body_box"]), "other": list(view["other"]["body_box"])},
            "lag_layers": {"nominal": "x_land / branch / s", "run": f"+-{consts.lag_run_u} u: lag_*",
                           "dash": f"+-{consts.lag_dash_u} u: lag_dash_*"},
            "support": None if consts.support is None else dict(consts.support),
            "not_claims": "raw components only: no weights, no total, no best position, no reject; free floor is "
                          "not an escape proof; small development counts are not probabilities"}
