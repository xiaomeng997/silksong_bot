"""Inescapable zones of aimed attacks (ICS), offline, and their reader (the person's method, 2026-10-09).

An aimed attack decides its aim at one moment and lands later. For every hero position around the enemy at that
decision, and every hero state, the scan asks: does some escape (an input sequence of that state, started at the
decision plus a latency) avoid the attack, whatever the measured jitter? If none does, the position is
inescapable. The scan runs offline and is stored per (family, hero state, latency) as a grid relative to the enemy
origin, in fan coordinates (x toward the side the enemy throws into, y up); at run time the planner only looks it
up (AimICS / zone / hero_state_key).

The generic AimedAttack: decision -> (antic motion of the projectile) -> release -> projectile path (speed profile,
homing as measured) -> terrain end -> an explosion circle with its on-window. Two attacks are stored:

Reed pin (RE_THROW, aim_ics_Reed.npz; 12,405 throws, forum.md §30): decision = the Throw Aim entry; the stored
  angle is Reed transform -> hero transform, clamped to the fan [-70, +45] deg; release 24 / 25 frames later from
  the spawn point (+1.53, -0.54) or (+1.11, +0.48) when the clamped angle is in [10, 45] deg; 31 u/s straight;
  collider 2.0314 x 0.0979 (unrotated on the spawn frame); sticks into the floor / a wall; the Reed drifts by up to
  (-0.22, +0.06) u from the decision to the release; no explosion. Origin: the Reed transform.
Clawmaiden spear (CM spear, aim_ics_Clawmaiden.npz; 1,321 casts, forum.md §31): the Spear's Control FSM.
  Decision = Get Antic Angle (the Clawmaiden's Spear Cast Antic -> Spear Fire frame): GetAngleToTarget2D from the
  spear transform to the hero transform + (0, 0.25); Fire R ClampAngle(-45, 45), Fire L FloatClamp(135, 225), i.e.
  the elevation toward the Clawmaiden's facing side clamped to [-45, +45] (a hero behind her gets the nearer edge).
  Antic Pause 0.15 s (still), Antic 0.7 s: velocity 30 u/s opposite to the aim, x0.875 on entry and per physics
  step (3.645 u back in the open; a wall behind the spear blocks or deflects it). Fire 0.85-0.95 s after the
  decision: 37 u/s along the aim, then ChaseObjectWisp toward the hero transform (force 45 x the clamped-to-1
  offset, mass 1; the speed clamped to [running max, 50] before the step: 37 -> 50.9 u/s). Collider: a triangle,
  tip 3.758 u ahead of the transform, base 1.776 u behind, 1.256 u wide (both mirror sides). The Terrain Detector
  is on from 0.1 s after the Fire entry; contact 1.26-1.64 u ahead of the transform; the explosion circle (r 3.553,
  0.900 u ahead of the transform, +-0.065 across) is on from the Explode frame for 0.067-0.108 s. Origin: the spear
  transform at the decision.

The hero: the planner's kinematics (knowledge/1.0.30000/kinematics/hero_wanderer_forum.json, the bot's Forum_W
loadout), escapes = a timing-complete event library per state (one move switch, a jump press held 2 / 4 / 8 frames
or to the end plus a second press 2 frames after the release, a dash tap / held / tap + a second tap 28 frames
later; every key change at least 2 frames apart as the oracle HoldFilter; starts every 2 frames to frame 12, every
4 to 40, every 8 after), rolled out over T = 120 frames (the horizon both attacks need) on the floor (and a wall
behind the hero for the wall states), positions held after T. Latency L: the first L frames keep the keys latched
at the decision (lat0: first free key on decision + 1 = a pre-planned escape; lat2: decision + 3 = the bot reacting
to the observed decision state); lat2 uses the subset of the lat0 library that starts that way.

The kernel runs on the 50 Hz physics clock: step n happens in frame ceil((n - phase) * 0.02 * 60), the hero and the
projectile both move in it, and every step is swept continuously (sub-steps of at most 0.05 u of relative motion,
the hero box widened by the motion inside the sub-step). An escape needs a clearance of CLEAR = 0.1 u from every
collider (the HeroBox half extents and the explosion radius grow by it). Worst case: one trajectory must escape
every variant (aim error, release / fire frame, drift / antic mode). Zones are the union over the physics phases
0 / 0.33 / 0.67, and then over the neighbouring height / vertical-speed bins (a bin's edge is covered by its
neighbour's representative), so a state between two representatives reads the larger zone. hero_state_key returns
"locked" for states outside the alphabet (bind, recoil, hurt, umbrella / glide, pogo, an air dash in progress, wall
cling / slide); the reader returns every possible cell of a locked state as inescapable.

Not modelled: the enemy's body (contact), the far wall beyond the enemy, the roof, clashes (the pin can be swatted;
the spear cannot: parry 4), i-frames, the spear's antic sliding along a wall (only open / fully blocked).

    cd <checkout>/brain
    ../scripts/uv.cmd run python -m ssbot.tools.aim_ics scan --types Reed Clawmaiden --out C:/ssbot/data/m2_forum_aimics/spear/scan
    ../scripts/uv.cmd run python -m ssbot.tools.aim_ics pack --type Clawmaiden --src C:/ssbot/data/m2_forum_aimics/spear/scan
"""
from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
KNOW = REPO / "knowledge" / "1.0.30000"
FORUM = KNOW / "enemies" / "forum"
DEFAULT_NPZ = FORUM / "aim_ics_Reed.npz"
WANDERER = KNOW / "kinematics" / "hero_wanderer_forum.json"

# ---------------------------------------------------------------------------------------------- geometry
HB_HW, HB_HH = 0.4554 / 2, 2.2498 / 2      # HeroBoxNormal half extents
HB_DY = -0.38                              # HeroBox centre - hero transform
HB_STAND = 4.5677 - 0.38 - 3.0             # standing HeroBox centre above the Forum floor (1.1877 u)
FLOOR_Y = 3.0
FDT = 0.02                                 # physics step (50 Hz)
CLEAR = 0.1                                # an escape keeps at least this far from every collider
SUB_U = 0.05                               # sweep sub-step: relative motion per sub-step at most this
GRID_DX = 0.1
LOCKED = "locked"
T_LIB = 120

# grid of hero HeroBox-centre positions relative to the enemy origin (fan coordinates) and the origin's y range
GRIDS = {
    "Reed": dict(x=(0.05, 16.0), y=(-11.95, 8.0), origin_y=(4.5, 20.2)),        # Reed y at 12,405 decisions
    "Clawmaiden": dict(x=(-7.95, 26.0), y=(-13.95, 6.0), origin_y=(7.0, 20.2)),  # spear y 7.24-19.94 (1,321)
}


def grid(type_name: str):
    g = GRIDS[type_name]
    return (np.round(np.arange(g["x"][0], g["x"][1], GRID_DX), 3), np.round(np.arange(g["y"][0], g["y"][1], GRID_DX),
                                                                             3))


GRID_X, GRID_Y = grid("Reed")


@dataclass(frozen=True)
class AimedAttack:
    """One aimed attack in the enemy's fan coordinates (+x toward the side it throws into, origin = the enemy
    origin at the decision). kind "pin": straight, sticks; kind "spear": antic, homing, explodes."""
    name: str
    kind: str
    release_frames: tuple            # decision -> release (pin) / Fire entry (spear), frames (every one escaped)
    aim_err_deg: tuple               # aim errors added to the stored angle (every one escaped)
    drift: tuple = ((0.0, 0.0),)     # the origin's motion from the decision to the release (pin)
    fan_deg: tuple = (-70.0, 45.0)   # the elevation toward the fan side is clamped into this range
    up_deg: tuple = (10.0, 45.0)     # clamped elevations thrown from the upper spawn point (pin)
    spawn_down: tuple = (0.0, 0.0)
    spawn_up: tuple = (0.0, 0.0)
    aim_dy: float = -HB_DY           # aim target above the HeroBox centre
    speed: float = 31.0              # launch speed
    speed_max: float = 31.0
    accel: float = 0.0               # homing force / mass toward the hero transform (u/s^2)
    home_dy: float = -HB_DY          # homing target above the HeroBox centre
    body: tuple = ()                 # pin: (half_len, half_thick, centre behind the transform); spear: triangle
    contact: float = 0.0             # terrain contact point ahead of the transform (spear)
    detect_s: float = 0.0            # terrain detection starts this long after the release (spear)
    antic_frames: tuple = (0,)       # decision -> antic entry (spear)
    antic_modes: tuple = (0,)        # 0 no antic motion, 1 open (flies back), 2 blocked behind (y motion only)
    antic_speed: float = 0.0
    antic_decel: float = 1.0
    expl_r: float = 0.0              # explosion radius (worst case), 0 = none
    expl_along: float = 0.0
    expl_s: float = 0.0              # explosion collider on-time
    s_max: float = 30.0              # pin: u of flight considered
    flight_max_s: float = 1.5        # spear: flights longer than this are counted as escaped (none recorded > 0.87)


PIN = dict(kind="pin", fan_deg=(-70.0, 45.0), up_deg=(10.0, 45.0), spawn_down=(1.53, -0.54), spawn_up=(1.11, 0.48),
           speed=31.0, speed_max=31.0, body=(2.0314 / 2, 0.0979 / 2, 0.025))
SPEAR = dict(kind="spear", fan_deg=(-45.0, 45.0), up_deg=(99.0, 99.0), aim_dy=-HB_DY + 0.25, speed=37.0,
             speed_max=50.0, accel=45.0, body=(3.759, 1.776, 0.628), contact=1.45, detect_s=0.1,
             antic_frames=(9,), antic_modes=(1, 0), antic_speed=30.0, antic_decel=0.875,
             expl_r=3.553 + 0.0654 + 0.19, expl_along=0.9, expl_s=0.108)
FAMILIES_BY_TYPE = {
    "Reed": {
        "measured": AimedAttack("measured", release_frames=(24, 25), aim_err_deg=(-0.5, 0.0, 0.5),
                                drift=((0.0, 0.0), (-0.22, 0.06)), **PIN),
        "person": AimedAttack("person", release_frames=(6,), aim_err_deg=(-0.5, 0.0, 0.5),
                              drift=((0.0, 0.0), (-0.22, 0.06)), **PIN),
    },
    "Clawmaiden": {
        "measured": AimedAttack("measured", release_frames=(51, 54), aim_err_deg=(-1.0, 0.0, 1.0), **SPEAR),
    },
}
FAMILIES = FAMILIES_BY_TYPE["Reed"]
LATENCIES = (0, 2)
PHASES = (0.0, 0.33, 0.67)

# ---------------------------------------------------------------------------------------------- hero states
# name -> (kind, h above standing, vy, dash ready, wall behind (u from the collider side) or None, dash dir)
# kinds: ground / air / dashing (2 frames into a ground dash, dir +1 = away from the enemy, -1 = toward it)
AIR_H = (0.25, 1.0, 2.5, 5.0)              # bins [0, 0.5), [0.5, 1.5), [1.5, 3.5), >= 3.5 u above standing height
AIR_VY = {"rest": 0.0, "rise": 8.0, "fall": -10.0}   # bins |vy| <= 4, vy > 4, vy < -4 (u/s)
VY_ORDER = ("fall", "rest", "rise")


def _state_table() -> dict:
    t = {"ground": ("ground", 0.0, 0.0, True, None, 0), "ground_nd": ("ground", 0.0, 0.0, False, None, 0),
         "dash_toward": ("dashing", 0.0, 0.0, False, None, -1), "dash_away": ("dashing", 0.0, 0.0, False, None, 1),
         "ground_w0.3": ("ground", 0.0, 0.0, True, 0.3, 0), "ground_w1.5": ("ground", 0.0, 0.0, True, 1.5, 0),
         "ground_nd_w0.3": ("ground", 0.0, 0.0, False, 0.3, 0)}
    for h in AIR_H:
        for vn, vy in AIR_VY.items():
            for d in (True, False):
                t[f"air_h{h}_{vn}_{'d' if d else 'nd'}"] = ("air", h, vy, d, None, 0)
                t[f"air_h{h}_{vn}_{'d' if d else 'nd'}_w0.3"] = ("air", h, vy, d, 0.3, 0)
    for h in (1.0, 2.5):
        for d in (True, False):
            t[f"air_h{h}_rest_{'d' if d else 'nd'}_w1.5"] = ("air", h, 0.0, d, 1.5, 0)
    return t


STATES = _state_table()
# on the wall (the person 2026-10-11: clinging at the wall top is safe from the Clapper): clinging (Ascendant's Grip)
# to a wall touching the collider on +x, h above standing height, no dash. Not table states of this module (the
# measured "wallcling" is LOCKED here); the aim zones' wall column (tools.aim_zones CLING_STATES) only.
CLING = {f"cling_h{h}": ("cling", h, 0.0, False, 0.0, 0) for h in AIR_H}


def state_spec(name: str) -> tuple:
    """(kind, h, vy, dash, wall, dash dir) of a table state or a cling state."""
    return STATES[name] if name in STATES else CLING[name]
SPECIAL = ("bind", "recoil", "hurt", "umbrella", "glide", "pogo", "airdash", "wallcling", "wallslide", "attack_lock")


def air_bin_h(h: float) -> float:
    return AIR_H[0] if h < 0.5 else AIR_H[1] if h < 1.5 else AIR_H[2] if h < 3.5 else AIR_H[3]


def hero_state_key(h: float, vy: float, grounded: bool, can_dash: bool, dashing: int = 0,
                   wall_behind: float | None = None, wall: bool = False, special: str | None = None) -> str:
    """The table key of a hero state at the decision. h: transform height above standing height (u); vy (u/s);
    dashing: 0, or +1 / -1 = a ground dash away from / toward the enemy; wall_behind: distance (u) from the hero
    collider's side to the wall on the far side from the enemy; wall: touching that wall; special: a state outside
    the escape model (SPECIAL, e.g. "bind", "recoil", "hurt", "umbrella", "pogo", "airdash", "wallcling") ->
    LOCKED, which the reader treats as inescapable everywhere."""
    if special:
        return LOCKED
    w = None
    if wall or (wall_behind is not None and wall_behind < 0.9):
        w = 0.3
    elif wall_behind is not None and wall_behind < 2.5:
        w = 1.5
    if dashing and grounded:
        if dashing > 0 and w is not None:
            return "ground_nd_w0.3"          # dashing into the wall behind: no dash, cornered
        return "dash_away" if dashing > 0 else "dash_toward"
    if grounded:
        if w is None:
            return "ground" if can_dash else "ground_nd"
        if not can_dash:
            return "ground_nd_w0.3"          # the nearest wall variant without a dash (closer = less room)
        return f"ground_w{w}"
    hb = air_bin_h(h)
    vn = "rise" if vy > 4.0 else "fall" if vy < -4.0 else "rest"
    k = f"air_h{hb}_{vn}_{'d' if can_dash else 'nd'}"
    if w is None:
        return k
    if w == 1.5 and f"{k}_w1.5" in STATES:
        return f"{k}_w1.5"
    return f"{k}_w0.3"


def neighbours(name: str) -> list:
    """The state and its neighbouring height / vertical-speed bins (same dash and wall), whose zones cover the bin's
    edges."""
    kind, h, vy, d, w, _ = STATES[name]
    if kind != "air":
        return [name]
    vn = next(k for k, v in AIR_VY.items() if v == vy)
    ih, iv = AIR_H.index(h), VY_ORDER.index(vn)
    out = []
    for jh in (ih - 1, ih, ih + 1):
        for jv in (iv - 1, iv, iv + 1):
            if 0 <= jh < len(AIR_H) and 0 <= jv < len(VY_ORDER):
                k = f"air_h{AIR_H[jh]}_{VY_ORDER[jv]}_{'d' if d else 'nd'}" + (f"_w{w}" if w is not None else "")
                if k not in STATES and w == 1.5:
                    k = k[:-4] + "w0.3"
                if k in STATES:
                    out.append(k)
    return out


# ---------------------------------------------------------------------------------------------- escape library
def _km():
    from ssbot.knowledge import kinematics as km
    return km


def hero_params(weighted: bool = False):
    km = _km()
    p = km.HeroParams.load(WANDERER)
    return p.with_weighted() if weighted else p


def terrain(p, wall: float | None):
    km = _km()
    boxes = [(-600.0, FLOOR_Y - 10.0, 600.0, FLOOR_Y)]
    if wall is not None:
        x = p.half_width + wall
        boxes.append((x, FLOOR_Y - 10.0, x + 5.0, FLOOR_Y + 40.0))
    return km.Terrain2D.from_boxes(boxes)


def start_state(name: str, p, phase: float = 0.0):
    """(model state at the decision, the latched mask at the decision) for a table state."""
    km = _km()
    kind, h, vy, dash, wall, ddir = state_spec(name)
    tr = terrain(p, wall)
    if kind == "cling":
        # in the air against the wall, held toward it until the Grip's cling holds (5 frames, 0.09 u lower in the
        # model); the hero keeps holding toward the wall through the latency
        S = km.initial_state(p, 0.0, FLOOR_Y + p.foot + h, vx=0.0, vy=0.0, facing=1, ground=False)
        S = km.rollout(S, np.full((1, CLING_SETTLE), km.B_RIGHT, np.int64), p, tr).final[:, 0].copy()
        if S[km.ROW_NAMES.index("cling")] < 0.5:
            raise RuntimeError(f"{name}: no cling after {CLING_SETTLE} frames (abilities {p.abilities})")
        S[km.ALPHA] = S[km.ALO] = S[km.AHI] = phase
        return S, km.B_RIGHT
    if kind == "air":
        S = km.initial_state(p, 0.0, FLOOR_Y + p.foot + h, vx=0.0, vy=vy, facing=1, ground=False)
        latched = 0
    else:
        S = km.initial_state(p, 0.0, FLOOR_Y + p.foot, facing=1, ground=True)
        S = km.rollout(S, np.zeros((1, 3), np.int64), p, tr).final[:, 0].copy()      # settle on the floor
        latched = 0
        if kind == "dashing":
            key = km.B_DASH | (km.B_RIGHT if ddir > 0 else km.B_LEFT)
            S = km.rollout(S, np.full((1, 2), key, np.int64), p, tr).final[:, 0].copy()
            latched = key
    if not dash:
        if kind == "air":
            S[km.ROW_NAMES.index("airdashed")] = 1.0
        else:
            S[km.ROW_NAMES.index("dash_cd")] = max(float(S[km.ROW_NAMES.index("dash_cd")]), p.dash_cooldown)
    S[km.ALPHA] = S[km.ALO] = S[km.AHI] = phase
    return S, latched


CLING_SETTLE = 12                          # frames held toward the wall to start a "cling" state
JHOLD = (2, 4, 8, None)
GAP2 = (2,)
DASH2 = 28                                 # a second dash tap this many frames after the first (cooldown 0.425 s)


COARSE_STARTS = (0, 4, 8, 12, 20, 28, 40, 56, 72, 88, 104)


def starts(T: int, coarse: bool = False) -> list:
    if coarse:
        return [s for s in COARSE_STARTS if s < T]
    return [s for s in list(range(0, 13, 2)) + list(range(16, 41, 4)) + list(range(48, T, 8)) if s < T]


def channels(T: int, jump_held: bool, coarse: bool = False):
    """Move / jump / dash channel masks [*, T]. The coarse set is a subset of the full one (its starts, jump holds
    2 / 8 / held, dash tap / held), so a coarse zone contains the full zone: a state whose coarse zone is empty
    needs no full library."""
    km = _km()
    L, R, J, D = km.B_LEFT, km.B_RIGHT, km.B_JUMP, km.B_DASH
    st = starts(T, coarse)
    jholds = (2, 8, None) if coarse else JHOLD
    mv = []
    for d1 in (0, L, R):
        mv.append(np.full(T, d1, np.int64))
        for t2 in st[1:]:
            for d2 in (0, L, R):
                if d2 != d1:
                    m = np.full(T, d1, np.int64)
                    m[t2:] = d2
                    mv.append(m)
    jp = [np.zeros(T, np.int64)]
    for tj in st:
        for h in jholds:
            e = T if h is None else min(T, tj + h)
            m = np.zeros(T, np.int64)
            m[tj:e] = J
            jp.append(m)
            if h is not None:
                for gp in GAP2:
                    if e + gp < T:
                        m2 = m.copy()
                        m2[e + gp:] = J
                        jp.append(m2)
    if jump_held:
        for r in st:
            m = np.zeros(T, np.int64)
            m[:r] = J
            jp.append(m)
        jp.append(np.full(T, J, np.int64))
    dp = [np.zeros(T, np.int64)]
    for td in st:
        for h in (2, None):
            m = np.zeros(T, np.int64)
            m[td:T if h is None else min(T, td + h)] = D
            dp.append(m)
        if td + DASH2 + 2 <= T and not coarse:
            m = np.zeros(T, np.int64)
            m[td:td + 2] = D
            m[td + DASH2:td + DASH2 + 2] = D
            dp.append(m)
    return (np.unique(np.stack(mv), axis=0), np.unique(np.stack(jp), axis=0), np.unique(np.stack(dp), axis=0))


@dataclass
class Library:
    """Escape trajectories of one state and phase: q [N, T, 2] int16 HeroBox-centre displacement / quant at frames
    1..T (index k - 1), sorted lexicographically in time; div [N] frames shared with the previous row; elig2 [N]
    reachable with 2 latched frames (lat2); probes: far-reaching rows tried first."""
    q: np.ndarray
    quant: float
    div: np.ndarray
    elig2: np.ndarray
    probes: np.ndarray

    def __len__(self):
        return len(self.q)

    def disp(self, i: int) -> np.ndarray:
        return self.q[i].astype(np.float64) * self.quant


def build_library(name: str, p, phase: float = 0.0, T: int = T_LIB, quant: float = 0.03, threads: int = 4,
                  n_probe: int = 256, coarse: bool = False, delay: int = 0) -> Library:
    """delay: the first `delay` frames keep the decision's latched keys (the latency sweep: a key L frames late)."""
    km = _km()
    S, latched = start_state(name, p, phase)
    tr = terrain(p, state_spec(name)[4])
    mv, jp, dp = channels(T - delay, (latched & km.B_JUMP) != 0, coarse)
    pad = lambda a: np.concatenate([np.full((len(a), delay), latched, np.int64), a], 1)  # noqa: E731
    mv, jp, dp = pad(mv), pad(jp), pad(dp)
    mv[:, :delay] = latched & (km.B_LEFT | km.B_RIGHT)
    jp[:, :delay] = latched & km.B_JUMP
    dp[:, :delay] = latched & km.B_DASH
    jd = (jp[:, None, :] | dp[None, :, :]).reshape(-1, T)
    c0 = None
    keys, eligs = [], []
    for m in mv:
        masks = np.unique(jd | m[None, :], axis=0)
        r = km.rollout(S, masks, p, tr, threads=threads)
        c = r.centre
        if c0 is None:
            c0 = c[0, 0].copy()
        qk = np.round((c[:, 1:] - c0[None, None, :]) / quant).astype(np.int16).reshape(len(masks), -1)
        e = np.all(masks[:, :2] == latched, axis=1)
        u, inv = np.unique(qk, axis=0, return_inverse=True)
        eu = np.zeros(len(u), bool)
        np.logical_or.at(eu, inv.ravel(), e)
        keys.append(u)
        eligs.append(eu)
    u, inv = np.unique(np.concatenate(keys), axis=0, return_inverse=True)
    el = np.zeros(len(u), bool)
    np.logical_or.at(el, inv.ravel(), np.concatenate(eligs))
    q = np.ascontiguousarray(u.reshape(len(u), T, 2))
    div = np.zeros(len(q), np.int16)
    if len(q) > 1:
        diff = (q[1:] != q[:-1]).any(axis=2)
        div[1:] = np.argmax(diff, axis=1)
    reach = np.abs(q[:, -1].astype(np.float64)).sum(1) + 0.5 * np.abs(q[:, T // 2].astype(np.float64)).sum(1)
    probes = np.argsort(-reach)[:n_probe].astype(np.int64)
    return Library(q, quant, div, el, probes)


# ---------------------------------------------------------------------------------------------- the scan kernel
# prm indices (float64 vector)
(P_KIND, P_PHASE, P_RATIO, P_SPEED, P_VMAX, P_ACC, P_HOMEDY, P_B0, P_B1, P_B2, P_CONTACT, P_DETECT, P_ASPEED,
 P_ADECEL, P_ER, P_EALONG, P_ESTEPS, P_HX, P_HY, P_FDT, P_MAXSTEPS, P_SUB, P_SMAX, P_QUANT, P_T, P_NP) = range(26)


def attack_params(att: AimedAttack, phase: float, ft: float, quant: float, T: int) -> np.ndarray:
    prm = np.zeros(P_NP)
    prm[P_KIND] = 0.0 if att.kind == "pin" else 1.0
    prm[P_PHASE] = phase
    prm[P_RATIO] = FDT / ft
    prm[P_SPEED], prm[P_VMAX], prm[P_ACC], prm[P_HOMEDY] = att.speed, att.speed_max, att.accel, att.home_dy
    prm[P_B0], prm[P_B1], prm[P_B2] = att.body
    prm[P_CONTACT] = att.contact
    prm[P_DETECT] = att.detect_s
    prm[P_ASPEED], prm[P_ADECEL] = att.antic_speed, att.antic_decel
    prm[P_ER] = att.expl_r + CLEAR if att.expl_r > 0 else 0.0
    prm[P_EALONG] = att.expl_along
    prm[P_ESTEPS] = att.expl_s
    prm[P_HX], prm[P_HY] = HB_HW + CLEAR, HB_HH + CLEAR
    prm[P_FDT] = FDT
    prm[P_MAXSTEPS] = att.flight_max_s / FDT
    prm[P_SUB] = SUB_U
    prm[P_SMAX] = att.s_max
    prm[P_QUANT] = quant
    prm[P_T] = T
    return prm


@lru_cache(maxsize=1)
def _kernel():
    import numba

    @numba.njit(cache=True, inline="always")
    def _obb(cx, cy, hx, hy, mx, my, ux, uy, a, b):
        """AABB (centre cx, cy, half hx, hy) vs a box centred at (mx, my) with axis (ux, uy), half a x b."""
        nx, ny = -uy, ux
        dx, dy = mx - cx, my - cy
        if abs(dx) > hx + a * abs(ux) + b * abs(nx):
            return False
        if abs(dy) > hy + a * abs(uy) + b * abs(ny):
            return False
        if abs(dx * ux + dy * uy) > a + hx * abs(ux) + hy * abs(uy):
            return False
        if abs(dx * nx + dy * ny) > b + hx * abs(nx) + hy * abs(ny):
            return False
        return True

    @numba.njit(cache=True)
    def _tri(cx, cy, hx, hy, px, py, ux, uy, tip, base, half_w):
        """AABB vs the spear triangle (transform px, py; flight dir ux, uy): tip ahead, base behind, half width."""
        nx, ny = -uy, ux
        ax, ay = px + ux * tip, py + uy * tip
        bx, by = px - ux * base + nx * half_w, py - uy * base + ny * half_w
        qx, qy = px - ux * base - nx * half_w, py - uy * base - ny * half_w
        if max(ax, bx, qx) < cx - hx or min(ax, bx, qx) > cx + hx:
            return False
        if max(ay, by, qy) < cy - hy or min(ay, by, qy) > cy + hy:
            return False
        for e in range(3):
            if e == 0:
                ex, ey, ox, oy, rx, ry = bx - ax, by - ay, qx, qy, ax, ay
            elif e == 1:
                ex, ey, ox, oy, rx, ry = qx - bx, qy - by, ax, ay, bx, by
            else:
                ex, ey, ox, oy, rx, ry = ax - qx, ay - qy, bx, by, qx, qy
            mx_, my_ = -ey, ex
            t0 = (rx - cx) * mx_ + (ry - cy) * my_
            t2 = (ox - cx) * mx_ + (oy - cy) * my_
            lo, hi = min(t0, t2), max(t0, t2)
            rr = hx * abs(mx_) + hy * abs(my_)
            if lo > rr or hi < -rr:
                return False
        return True

    @numba.njit(cache=True, inline="always")
    def _circ(cx, cy, hx, hy, ox, oy, r):
        dx = max(abs(ox - cx) - hx, 0.0)
        dy = max(abs(oy - cy) - hy, 0.0)
        return dx * dx + dy * dy <= r * r

    @numba.njit(cache=True, inline="always")
    def _frame(n, prm):
        return int(math.ceil((n - prm[P_PHASE]) * prm[P_RATIO] - 1e-9))

    @numba.njit(cache=True, inline="always")
    def _hp(lib, i, k, cx0, cy0, prm, mir):
        if k <= 0:
            return cx0, cy0
        T = lib.shape[1]
        if k > T:
            k = T
        return cx0 + mir * lib[i, k - 1, 0] * prm[P_QUANT], cy0 + lib[i, k - 1, 1] * prm[P_QUANT]

    @numba.njit(cache=True)
    def _pin(lib, i, cx0, cy0, mir, ux, uy, px, py, relf, sstop, prm):
        hx, hy = prm[P_HX], prm[P_HY]
        hl, ht, back = prm[P_B0], prm[P_B1], prm[P_B2]
        n = 1
        while _frame(n, prm) <= relf:
            n += 1
        hxp, hyp = _hp(lib, i, _frame(n - 1, prm) if n > 1 else 0, cx0, cy0, prm, mir)
        sx = 1.0 if ux >= 0 else -1.0
        if _obb(hxp, hyp, hx, hy, px - sx * back, py, 1.0, 0.0, hl, ht):     # the unrotated spawn-frame box
            return max(relf, 1)
        sp = prm[P_SPEED] * prm[P_FDT]
        s0 = 0.0
        m = 0
        while True:
            k = _frame(n, prm)
            hx1, hy1 = _hp(lib, i, k, cx0, cy0, prm, mir)
            m += 1
            s1 = min(m * sp, sstop)
            ddx, ddy = hx1 - hxp, hy1 - hyp
            J = int(math.ceil(max(math.hypot(ddx, ddy), s1 - s0) / prm[P_SUB])) + 1
            ex, ey = abs(ddx) / (2 * J), abs(ddy) / (2 * J)
            for j in range(J):
                tm = (j + 0.5) / J
                sa, sb = s0 + (s1 - s0) * j / J, s0 + (s1 - s0) * (j + 1) / J
                lo, hi = sa - back - hl, sb - back + hl
                sm = 0.5 * (lo + hi)
                if _obb(hxp + ddx * tm, hyp + ddy * tm, hx + ex, hy + ey, px + ux * sm, py + uy * sm, ux, uy,
                        0.5 * (hi - lo), ht):
                    return max(k, 1)
            if s1 >= sstop or s1 >= prm[P_SMAX]:
                return 0
            s0 = s1
            hxp, hyp = hx1, hy1
            n += 1

    @numba.njit(cache=True)
    def _spear(lib, i, cx0, cy0, floor_c, wall_c, mir, ux, uy, px, py, firef, anticf, amode, prm):
        hx, hy = prm[P_HX], prm[P_HY]
        tip, base, hw = prm[P_B0], prm[P_B1], prm[P_B2]
        fdt = prm[P_FDT]
        Px, Py = px, py
        vx, vy = 0.0, 0.0
        n = 1
        # Antic Pause (still) and Antic (flies back, decelerating); the hero moves, the spear is harmless
        while _frame(n, prm) <= anticf:
            n += 1
        if amode > 0:
            vx, vy = -ux * prm[P_ASPEED] * prm[P_ADECEL], -uy * prm[P_ASPEED] * prm[P_ADECEL]
            if amode == 2:
                vx = 0.0
        while _frame(n, prm) <= firef:
            vx *= prm[P_ADECEL]
            vy *= prm[P_ADECEL]
            Px += vx * fdt
            Py += vy * fdt
            if Py < floor_c + 0.5:
                Py = floor_c + 0.5
                vy = 0.0
            n += 1
        hxp, hyp = _hp(lib, i, _frame(n - 1, prm), cx0, cy0, prm, mir)
        # Fire entry: 37 u/s along the aim, the first homing force (OnEnter), the running minimum speed
        vx, vy = ux * prm[P_SPEED], uy * prm[P_SPEED]
        dx, dy = hxp - Px, hyp + prm[P_HOMEDY] - Py
        d = math.hypot(dx, dy)
        if d > 1.0:
            dx, dy = dx / d, dy / d
        Fx, Fy = prm[P_ACC] * dx, prm[P_ACC] * dy
        smin = prm[P_SPEED]
        m = 0
        n_det = prm[P_DETECT] / fdt - 1e-6
        while True:
            k = _frame(n, prm)
            hx1, hy1 = _hp(lib, i, k, cx0, cy0, prm, mir)
            m += 1
            dx, dy = hxp - Px, hyp + prm[P_HOMEDY] - Py
            d = math.hypot(dx, dy)
            if d > 1.0:
                dx, dy = dx / d, dy / d
            Fx += prm[P_ACC] * dx
            Fy += prm[P_ACC] * dy
            s = math.hypot(vx, vy)
            if s > prm[P_VMAX]:
                vx, vy = vx * prm[P_VMAX] / s, vy * prm[P_VMAX] / s
                s = prm[P_VMAX]
            if s < smin:
                vx, vy = vx * smin / s, vy * smin / s
                s = smin
            smin = max(smin, s)
            vx += Fx * fdt
            vy += Fy * fdt
            Fx, Fy = 0.0, 0.0
            P1x, P1y = Px + vx * fdt, Py + vy * fdt
            s = math.hypot(vx, vy)
            dux, duy = vx / s, vy / s
            # the body, swept with the hero
            ddx, ddy = hx1 - hxp, hy1 - hyp
            rx, ry = (P1x - Px) - ddx, (P1y - Py) - ddy
            J = int(math.ceil(math.hypot(rx, ry) / prm[P_SUB])) + 1
            ex, ey = abs(rx) / (2 * J), abs(ry) / (2 * J)
            for j in range(J):
                tm = (j + 0.5) / J
                if _tri(hxp + ddx * tm, hyp + ddy * tm, hx + ex, hy + ey, Px + (P1x - Px) * tm,
                        Py + (P1y - Py) * tm, dux, duy, tip, base, hw):
                    return max(k, 1)
            # the terrain (after the detector delay): the contact point past the floor / the wall
            if m >= n_det:
                cx_, cy_ = P1x + dux * prm[P_CONTACT], P1y + duy * prm[P_CONTACT]
                pen = -1.0
                if cy_ <= floor_c and duy < 0:
                    pen = (floor_c - cy_) / -duy
                if (cx_ - wall_c) * mir >= 0 and dux * mir > 0:
                    pen = max(pen, (cx_ - wall_c) / dux)
                if pen >= 0:
                    pen = min(pen, s * fdt)
                    ox = P1x - dux * pen + dux * prm[P_EALONG]
                    oy = P1y - duy * pen + duy * prm[P_EALONG]
                    r = prm[P_ER]
                    if _circ(hx1, hy1, hx, hy, ox, oy, r):
                        return max(k, 1)
                    tend = (n - prm[P_PHASE]) * fdt + prm[P_ESTEPS]
                    hxp, hyp = hx1, hy1
                    n += 1
                    while (n - prm[P_PHASE]) * fdt <= tend + 1e-9:
                        k = _frame(n, prm)
                        hx1, hy1 = _hp(lib, i, k, cx0, cy0, prm, mir)
                        ddx, ddy = hx1 - hxp, hy1 - hyp
                        if _circ(hxp + 0.5 * ddx, hyp + 0.5 * ddy, hx + 0.5 * abs(ddx), hy + 0.5 * abs(ddy), ox, oy,
                                 r):
                            return max(k, 1)
                        hxp, hyp = hx1, hy1
                        n += 1
                    return 0
            if m > prm[P_MAXSTEPS]:
                return 0
            Px, Py = P1x, P1y
            hxp, hyp = hx1, hy1
            n += 1

    @numba.njit(cache=True)
    def _sim(lib, i, cx0, cy0, floor_c, wall_c, mir, vf, vi, prm):
        """0 = trajectory i escapes every variant; else the last hero frame the first failing variant used. mir -1:
        the hero library is mirrored (a wall state's wall on the -x side) and the wall test looks to -x."""
        for v in range(vf.shape[0]):
            if prm[P_KIND] == 0.0:
                r = _pin(lib, i, cx0, cy0, mir, vf[v, 0], vf[v, 1], vf[v, 2], vf[v, 3], vi[v, 0], vf[v, 4], prm)
            else:
                r = _spear(lib, i, cx0, cy0, floor_c, wall_c, mir, vf[v, 0], vf[v, 1], vf[v, 2], vf[v, 3], vi[v, 0],
                           vi[v, 1], vi[v, 2], prm)
            if r > 0:
                return r
        return 0

    @numba.njit(cache=True, parallel=True)
    def scan(lib, div, elig, use_elig, probes, cells, floor_c, wall_c, mirs, vf, vi, prm, nchunk):
        """cells [C, 2] HeroBox centre rel. the enemy origin; per-cell variants vf [C, V, 5], vi [C, V, 3].
        Returns [C]: the first escaping trajectory, -1 = inescapable, -2 = impossible origin position."""
        C = cells.shape[0]
        N = lib.shape[0]
        out = np.full(C, -1, np.int64)
        per = (C + nchunk - 1) // nchunk
        for ch in numba.prange(nchunk):
            last = -1
            for ci in range(ch * per, min(C, (ch + 1) * per)):
                if floor_c[ci] > 1e8:
                    out[ci] = -2
                    continue
                cx0, cy0, fc, wc, mr = cells[ci, 0], cells[ci, 1], floor_c[ci], wall_c[ci], mirs[ci]
                found = -1
                if last >= 0 and _sim(lib, last, cx0, cy0, fc, wc, mr, vf[ci], vi[ci], prm) == 0:
                    found = last
                if found < 0:
                    for pi in range(probes.shape[0]):
                        i = probes[pi]
                        if use_elig and not elig[i]:
                            continue
                        if _sim(lib, i, cx0, cy0, fc, wc, mr, vf[ci], vi[ci], prm) == 0:
                            found = i
                            break
                if found < 0:
                    i = 0
                    while i < N:
                        if use_elig and not elig[i]:
                            i += 1
                            continue
                        kf = _sim(lib, i, cx0, cy0, fc, wc, mr, vf[ci], vi[ci], prm)
                        if kf == 0:
                            found = i
                            break
                        j = i + 1
                        while j < N and div[j] >= kf:       # same frames 1..kf: fails the same way
                            j += 1
                        i = j
                out[ci] = found
                if found >= 0:
                    last = found
        return out

    return scan, _sim


def fan_clamp(e: np.ndarray, fan: tuple) -> np.ndarray:
    """Elevation (deg, (-180, 180]) toward the fan side clamped into the fan; a target behind (|e| > 90) gets the
    nearer edge by angle (the spear's ClampAngle; the Reed always faces the hero)."""
    return np.clip(e, fan[0], fan[1])


def variants(att: AimedAttack, cells: np.ndarray, floor_rel: np.ndarray, wall_rel: np.ndarray):
    """Per cell and variant: vf [C, V, 5] (dir x, dir y, spawn x, spawn y, pin flight until it sticks) and
    vi [C, V, 3] (release / fire frame, antic frame, antic mode)."""
    tx, ty = cells[:, 0], cells[:, 1] + att.aim_dy
    e = np.degrees(np.arctan2(ty, tx))
    V = [(o, r, d, a, am) for o in att.aim_err_deg for r in att.release_frames for d in att.drift
         for a in att.antic_frames for am in att.antic_modes]
    C = len(cells)
    vf = np.zeros((C, len(V), 5))
    vi = np.zeros((C, len(V), 3), np.int64)
    front = att.body[0] - att.body[2] if att.kind == "pin" else 0.0
    for j, (o, r, d, a, am) in enumerate(V):
        ec = fan_clamp(e + o, att.fan_deg)
        up = (ec >= att.up_deg[0]) & (ec <= att.up_deg[1])
        rad = np.radians(ec)
        ux, uy = np.cos(rad), np.sin(rad)
        px = np.where(up, att.spawn_up[0], att.spawn_down[0]) + d[0]
        py = np.where(up, att.spawn_up[1], att.spawn_down[1]) + d[1]
        s = np.full(C, att.s_max)
        with np.errstate(divide="ignore", invalid="ignore"):
            sf = np.where(uy < -1e-9, (floor_rel - py) / uy - front, np.inf)
            sw = np.where(ux > 1e-9, (wall_rel - px) / ux - front, np.inf)
        vf[:, j] = np.stack([ux, uy, px, py, np.maximum(0.0, np.minimum(s, np.minimum(sf, sw)))], 1)
        vi[:, j] = (r, a, am)
    return vf, vi


def cell_geometry(type_name: str, name: str, p, cells: np.ndarray):
    """Per cell: the floor y, the far wall x (rel. the enemy origin, fan coordinates; the wall is on the hero's far
    side from the enemy: +x, or -x for a hero behind the fan side, where the hero library is mirrored: mir -1) and
    the impossible-origin flag (the origin's y outside its recorded range: floor_c = 1e9)."""
    kind, h, vy, dash, wall, _ = STATES[name]
    floor_rel = cells[:, 1] - (HB_STAND + h)
    oy = FLOOR_Y + HB_STAND + h - cells[:, 1]
    lo, hi = GRIDS[type_name]["origin_y"]
    floor_c = np.where((oy < lo) | (oy > hi), 1e9, floor_rel)
    if wall is None:
        return floor_rel, floor_c, np.full(len(cells), 1e6), np.ones(len(cells))
    mir = np.where(cells[:, 0] < 0, -1.0, 1.0)
    return floor_rel, floor_c, cells[:, 0] + mir * (p.half_width + wall), mir


def scan_state(lib: Library, type_name: str, name: str, att: AimedAttack, p, phase: float, lat: int,
               nchunk: int = 64) -> np.ndarray:
    """int8 [len(grid y), len(grid x)]: 1 inescapable, 0 escapable, -1 impossible origin position. lat 0 or 2 (a
    latency sweep builds the library with delay=L and scans it at lat 0)."""
    if lat not in (0, 2):
        raise ValueError("latency must be 0 or 2; for a sweep use build_library(..., delay=L) and lat 0")
    scan, _ = _kernel()
    gxa, gya = grid(type_name)
    gx, gy = np.meshgrid(gxa, gya)
    cells = np.stack([gx.ravel(), gy.ravel()], 1).astype(np.float64)
    floor_rel, floor_c, wall_rel, mir = cell_geometry(type_name, name, p, cells)
    vf, vi = variants(att, cells, floor_rel, np.where(mir > 0, wall_rel, 1e6))
    prm = attack_params(att, phase, p.frame_time, lib.quant, lib.q.shape[1])
    first = scan(lib.q, lib.div, lib.elig2, lat >= 2, lib.probes, cells, floor_c, wall_rel, mir, vf, vi, prm,
                 nchunk)
    z = np.where(first == -2, -1, np.where(first < 0, 1, 0)).astype(np.int8)
    return z.reshape(len(gya), len(gxa))


def path_escapes(path: np.ndarray, rel_xy: tuple, floor_rel: float, wall_rel: float, att: AimedAttack, p,
                 phase: float = 0.0, vf: np.ndarray | None = None, vi: np.ndarray | None = None,
                 mir: float = 1.0) -> bool:
    """Does a HeroBox-centre displacement path [n, 2] (frames 1..n after the decision) from the cell rel_xy escape
    every variant (or the given vf [V, 5] / vi [V, 3], e.g. a recorded spear)? (The validation's test.)"""
    _, sim = _kernel()
    cells = np.array([rel_xy], np.float64)
    if vf is None:
        vf, vi = variants(att, cells, np.array([floor_rel]), np.array([wall_rel]))
        vf, vi = vf[0], vi[0]
    lib = np.ascontiguousarray(np.asarray(path, np.float32)[None])
    prm = attack_params(att, phase, p.frame_time, 1.0, lib.shape[1])
    return sim(lib, 0, float(rel_xy[0]), float(rel_xy[1]), float(floor_rel), float(wall_rel), float(mir),
               np.ascontiguousarray(vf, np.float64), np.ascontiguousarray(vi, np.int64), prm) == 0


# ---------------------------------------------------------------------------------------------- the stored table
class AimICS:
    """Reader of aim_ics_<type>.npz: zone grids per (family, hero state, latency), union over physics phases and
    neighbouring bins."""

    def __init__(self, path: str | Path = DEFAULT_NPZ):
        z = np.load(path, allow_pickle=False)
        self.meta = json.loads(str(z["meta"]))
        self.gx = z["grid_x"]
        self.gy = z["grid_y"]
        self._z = {k: z[k] for k in z.files if k.startswith("z|")}
        self._possible = None

    def _locked(self) -> np.ndarray:
        if self._possible is None:
            pos = np.zeros((len(self.gy), len(self.gx)), bool)
            for v in self._z.values():
                pos |= v != -1
            self._possible = np.where(pos, 1, -1).astype(np.int8)
        return self._possible

    def zone(self, family: str, hero_state: str, latency: int) -> np.ndarray:
        """int8 [len(grid_y), len(grid_x)] in fan coordinates: x = (hero HeroBox centre - enemy origin).x toward the
        fan side, y = up; 1 inescapable, 0 escapable, -1 impossible origin position. A LOCKED state (or one not in
        the table) is inescapable wherever the origin is possible."""
        z = self._z.get(f"z|{family}|{hero_state}|{int(latency)}")
        return self._locked() if z is None else z

    def keys(self) -> list:
        return [tuple(k.split("|")[1:]) for k in self._z]

    def inescapable(self, family: str, hero_state: str, latency: int, hero_hb: tuple, enemy: tuple,
                    side: int | None = None) -> bool:
        """Is the hero (HeroBox centre, world) inside the zone of an enemy origin at `enemy` (world)? side: the fan
        side (+1 right, -1 left; the spear: the Clawmaiden's facing); None = the hero's side (the Reed)."""
        dx = hero_hb[0] - enemy[0]
        dx = abs(dx) if side is None else dx * (1 if side >= 0 else -1)
        dy = hero_hb[1] - enemy[1]
        ix = int(round((dx - self.gx[0]) / GRID_DX))
        iy = int(round((dy - self.gy[0]) / GRID_DX))
        if not (0 <= ix < len(self.gx) and 0 <= iy < len(self.gy)):
            return False
        return bool(self.zone(family, hero_state, int(latency))[iy, ix] == 1)

    def area(self, family: str, hero_state: str, latency: int) -> float:
        """u^2 of the inescapable zone (one fan)."""
        return float((self.zone(family, hero_state, latency) == 1).sum() * GRID_DX * GRID_DX)


def zone(type_name: str, family: str, hero_state: str, latency: int, path: str | Path | None = None) -> np.ndarray:
    """The zone grid of an enemy type ("Reed", "Clawmaiden"), see AimICS.zone."""
    return _reader(str(path or FORUM / f"aim_ics_{type_name}.npz")).zone(family, hero_state, latency)


@lru_cache(maxsize=4)
def _reader(path: str) -> AimICS:
    return AimICS(path)


# ---------------------------------------------------------------------------------------------- CLI
def cmd_scan(args):
    """Per (phase, state): a coarse library first; the full library only where a coarse zone is not empty (the
    coarse library is a subset of the full one, so its empty zones are exact)."""
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    p = hero_params(bool(args.weighted))
    names = args.states or list(STATES)
    for phase in args.phases:
        for name in names:
            todo = [(t, f, lat) for t in args.types for f in (args.families or FAMILIES_BY_TYPE[t])
                    if f in FAMILIES_BY_TYPE[t] for lat in args.lats
                    if not (out / f"z_{t}__{f}__{name}__lat{lat}__ph{phase}.npy").exists()]
            if not todo:
                continue
            for coarse in ((True, False) if args.coarse_first else (False,)):
                t0 = time.perf_counter()
                lib = build_library(name, p, phase, args.T, coarse=coarse)
                tb = time.perf_counter() - t0
                left = []
                for t, fam, lat in todo:
                    t1 = time.perf_counter()
                    z = scan_state(lib, t, name, FAMILIES_BY_TYPE[t][fam], p, phase, lat)
                    a = (z == 1).sum() * GRID_DX ** 2
                    print(f"{t} {fam} {name} lat{lat} ph{phase} {'coarse' if coarse else 'full'}: lib {len(lib)} "
                          f"({tb:.0f} s), zone {a:.2f} u2 ({time.perf_counter() - t1:.0f} s)", flush=True)
                    if coarse and a > 0:
                        left.append((t, fam, lat))
                    else:
                        np.save(out / f"z_{t}__{fam}__{name}__lat{lat}__ph{phase}.npy", z)
                del lib
                todo = left
                if not todo:
                    break


def cmd_pack(args):
    src = Path(args.src)
    t = args.type
    raw, phases_by = {}, {}
    for f in sorted(src.glob(f"z_{t}__*__*__lat*__ph*.npy")):
        _, fam, name, lat, ph = f.stem[2:].split("__")
        key = (fam, name, int(lat[3:]))
        z = np.load(f)
        raw[key] = z if key not in raw else np.where((raw[key] == 1) | (z == 1), 1, raw[key]).astype(np.int8)
        phases_by.setdefault(key, []).append(float(ph[2:]))
    zs = {}
    for (fam, name, lat), z in raw.items():
        u = z.copy()
        for nb in neighbours(name):
            o = raw.get((fam, nb, lat))
            if o is not None:
                u = np.where((u == 1) | ((o == 1) & (u != -1)), 1, u).astype(np.int8)
        zs[f"z|{fam}|{name}|{lat}"] = u
    gx, gy = grid(t)
    meta = {"type": t, "attack": {"Reed": "RE_THROW", "Clawmaiden": "CM spear"}[t], "grid_dx": GRID_DX,
            "coords": "x = (hero HeroBox centre - enemy origin).x toward the fan side, y up; origin: "
                      + {"Reed": "the Reed transform (fan = the hero's side)",
                         "Clawmaiden": "the spear transform at Get Antic Angle (fan = the Clawmaiden's facing)"}[t],
            "hero_box": [2 * HB_HW, 2 * HB_HH, HB_DY], "clearance": CLEAR,
            "families": {k: v.__dict__ for k, v in FAMILIES_BY_TYPE[t].items()},
            "states": {k: dict(zip(("kind", "h", "vy", "dash_ready", "wall_behind", "dash_dir"), v))
                       for k, v in STATES.items()},
            "latencies": "first free key on decision + 1 + latency",
            "phases": {"|".join(map(str, k)): sorted(v) for k, v in phases_by.items()},
            "union": "physics phases, then the neighbouring height / vy bins (aim_ics.neighbours)",
            "locked": "states outside the alphabet: inescapable wherever the origin is possible",
            "values": "1 inescapable, 0 escapable, -1 impossible origin position", "source": "ssbot.tools.aim_ics"}
    npz = Path(args.npz or FORUM / f"aim_ics_{t}.npz")
    np.savez_compressed(npz, meta=np.array(json.dumps(meta)), grid_x=gx, grid_y=gy, **zs)
    summ = {"meta": {k: meta[k] for k in ("type", "attack", "grid_dx", "coords", "hero_box", "clearance",
                                          "latencies", "union", "locked", "values")},
            "area_u2": {k[2:]: round(float((v == 1).sum() * GRID_DX ** 2), 2) for k, v in sorted(zs.items())},
            "area_u2_before_bin_union": {"|".join(map(str, k)): round(float((v == 1).sum() * GRID_DX ** 2), 2)
                                         for k, v in sorted(raw.items())},
            "max_dist_u": {k[2:]: _max_dist(v, gx, gy) for k, v in sorted(zs.items())},
            "phases": meta["phases"]}
    npz.with_suffix(".json").write_text(json.dumps(summ, indent=1), "utf-8")
    print(f"packed {len(zs)} zones -> {npz}")


def _max_dist(z: np.ndarray, gx: np.ndarray, gy: np.ndarray) -> float:
    iy, ix = np.nonzero(z == 1)
    if not len(ix):
        return 0.0
    return round(float(np.hypot(gx[ix], gy[iy]).max()), 2)


def main():
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:  # noqa: BLE001  (not Windows / no psutil: normal priority)
        pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("scan")
    a.add_argument("--out", required=True)
    a.add_argument("--types", nargs="+", default=["Reed", "Clawmaiden"])
    a.add_argument("--states", nargs="*")
    a.add_argument("--families", nargs="*")
    a.add_argument("--lats", nargs="+", type=int, default=list(LATENCIES))
    a.add_argument("--phases", nargs="+", type=float, default=list(PHASES))
    a.add_argument("--T", type=int, default=T_LIB)
    a.add_argument("--weighted", type=int, default=0)
    a.add_argument("--coarse-first", type=int, default=1)
    b = sub.add_parser("pack")
    b.add_argument("--type", required=True)
    b.add_argument("--src", required=True)
    b.add_argument("--npz")
    args = ap.parse_args()
    {"scan": cmd_scan, "pack": cmd_pack}[args.cmd](args)


if __name__ == "__main__":
    main()
