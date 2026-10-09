"""Inescapable zones of an aimed attack (ICS), offline, and their reader (the person's method, 2026-10-09).

An aimed attack decides its aim at one moment and releases later. For every hero position around the enemy at
that decision, and every hero state, the scan asks: does some escape (an input sequence of that state, started at
the decision plus a latency) avoid the attack, whatever the measured jitter? If none does, the position is
inescapable. The scan runs offline and is stored per (family, hero state, latency) as a grid relative to the enemy,
in fan coordinates (x toward the side the hero is on, which is also the fan the enemy throws into); at run time
the planner only looks it up.

The Reed's pin (RE_THROW), measured on 12,405 released throws (C:/ssbot/data/m2_forum_aimics, forum.md §30):
  - decision = the Throw Aim entry, 15-16 frames after Throw Antic Anim; the stored angle is Reed transform ->
    hero transform (STATE hero.pos) on that frame, clamped to the fan: elevation toward the hero's side in
    [-70, +45] deg (Lock L [135, 250], Lock R [0, 45] / [290, 360]); aim error max 0.49 deg; no lead;
  - release 0.400-0.50 s later (Wait 0.4 = 24-25 frames; +0.067-0.083 s Throw Transition, later = easier);
  - spawn (facing coordinates) (+1.53, -0.54), or (+1.11, +0.48) when the clamped angle is in [10, 170] deg;
  - the Reed drifts from the decision to the release by p50 (-0.137, +0.037) u, p95 0.23 u;
  - pin 31.0 u/s straight, collider 2.0314 x 0.0979 along the flight, centre 0.025 u behind the transform, on the
    spawn frame exported unrotated (both are tested); sticks into the floor / a wall (collider off after that frame).
Family "person" is the person's own timing (release 0.1 s after the decision) with the same geometry.

The hero: the planner's kinematics (knowledge/1.0.30000/kinematics/hero_wanderer_forum.json, no Weighted Anklet:
the bot's Forum_W loadout), escapes = a timing-complete event library per state (measurer B, hero_lib.py: one
move switch, a jump press held 2..14 frames or to the end plus a second press (re-jump / glide), a dash tap / 8
frames / held, every key change at least 2 frames apart as the oracle HoldFilter; starts every 2 frames up to frame
12, every 3 after), rolled out over T frames on the floor (and a wall behind the hero for the wall states), after
T continued ballistically (gravity, max fall, floor, wall). The hit test uses the real HeroBox (HeroBoxNormal,
0.4554 x 2.2498 at transform (0, -0.38)), not the exported hero.Bounds (0.50 x 2.079), against the pin collider
swept from the previous frame's position to this frame's (separating axes). Latency L: the first L frames after the
decision keep the keys latched at the decision (lat0: the first free key on decision + 1 = a pre-planned escape;
lat2: decision + 3 = the bot reacting to the observed Throw Aim entry: seen 1 frame late, 2-frame harness lead).
Worst case inside the measured ranges: one trajectory must escape every combination of aim error (-0.5, 0, +0.5
deg), release frame and Reed drift (0 and the p95 backward drift); the zone is the union over physics phases.

Not modelled: the Reed's body (contact), the far wall beyond the Reed, the roof (the hero cannot reach it), clashes
(a nail clash deflects the pin, 3.7-5.5 % of throws), i-frames.

    cd <checkout>/brain
    ../scripts/uv.cmd run python -m ssbot.tools.aim_ics scan --out C:/ssbot/data/m2_forum_aimics/scan
    ../scripts/uv.cmd run python -m ssbot.tools.aim_ics pack --src C:/ssbot/data/m2_forum_aimics/scan
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
DEFAULT_NPZ = KNOW / "enemies" / "forum" / "aim_ics_Reed.npz"
WANDERER = KNOW / "kinematics" / "hero_wanderer_forum.json"

# ---------------------------------------------------------------------------------------------- geometry
HB_HW, HB_HH = 0.4554 / 2, 2.2498 / 2      # HeroBoxNormal half extents
HB_DY = -0.38                              # HeroBox centre - hero transform
HB_STAND = 4.5677 - 0.38 - 3.0             # standing HeroBox centre above the Forum floor (1.1877 u)
FLOOR_Y = 3.0
REED_Y_MIN, REED_Y_MAX = 4.5, 20.2          # the Reed transform's y at 12,405 decisions: min 4.52, max 20.16

# grid of hero HeroBox-centre positions relative to the enemy transform (fan coordinates, x >= 0 toward the hero)
GRID_DX = 0.1
GRID_X = np.round(np.arange(0.05, 16.0, GRID_DX), 3)          # 160 columns
GRID_Y = np.round(np.arange(-11.95, 8.0, GRID_DX), 3)         # 200 rows


@dataclass(frozen=True)
class AimedAttack:
    """One aimed attack's release and projectile, in the enemy's facing coordinates (+x toward the hero)."""
    name: str
    release_frames: tuple            # frames from the decision to the release (every one must be escaped)
    aim_err_deg: tuple               # aim errors added to the stored angle (every one must be escaped)
    drift: tuple                     # ((dx, dy), ...) the enemy's motion from the decision to the release
    fan_deg: tuple = (-70.0, 45.0)   # the elevation toward the hero's side is clamped into this range
    up_deg: tuple = (10.0, 45.0)     # clamped elevations thrown from the upper spawn point
    spawn_down: tuple = (1.53, -0.54)
    spawn_up: tuple = (1.11, 0.48)
    aim_dy: float = -HB_DY           # aim target above the HeroBox centre (the hero transform)
    speed: float = 31.0
    half_len: float = 2.0314 / 2
    half_thick: float = 0.0979 / 2
    back: float = 0.025              # collider centre behind the transform
    s_max: float = 30.0              # u of flight considered (the arena is 35 u wide)


FAMILIES = {
    "measured": AimedAttack("measured", release_frames=(24, 25), aim_err_deg=(-0.5, 0.0, 0.5),
                            drift=((0.0, 0.0), (-0.22, 0.06))),
    "person": AimedAttack("person", release_frames=(6,), aim_err_deg=(-0.5, 0.0, 0.5),
                          drift=((0.0, 0.0), (-0.22, 0.06))),
}
LATENCIES = (0, 2)
PHASES = (0.0, 0.33, 0.67)

# ---------------------------------------------------------------------------------------------- hero states
# name -> (kind, h above standing, vy, dash ready, wall behind (u from the collider side) or None, dash dir)
# kinds: ground / air / dashing (2 frames into a ground dash, dir +1 = away from the enemy, -1 = toward it)
AIR_H = (0.25, 1.0, 2.5, 5.0)              # bins [0, 0.5), [0.5, 1.5), [1.5, 3.5), >= 3.5 u above standing height
AIR_VY = {"rest": 0.0, "rise": 8.0, "fall": -10.0}   # bins |vy| <= 4, vy > 4, vy < -4 (u/s)


def _state_table() -> dict:
    t = {"ground": ("ground", 0.0, 0.0, True, None, 0), "ground_nd": ("ground", 0.0, 0.0, False, None, 0),
         "dash_toward": ("dashing", 0.0, 0.0, False, None, -1), "dash_away": ("dashing", 0.0, 0.0, False, None, 1)}
    for w in (0.3, 1.5):
        t[f"ground_w{w}"] = ("ground", 0.0, 0.0, True, w, 0)
    for h in AIR_H:
        for vn, vy in AIR_VY.items():
            for d in (True, False):
                t[f"air_h{h}_{vn}_{'d' if d else 'nd'}"] = ("air", h, vy, d, None, 0)
    for h in (1.0, 2.5):
        for d in (True, False):
            for w in (0.3, 1.5):
                t[f"air_h{h}_rest_{'d' if d else 'nd'}_w{w}"] = ("air", h, 0.0, d, w, 0)
    return t


STATES = _state_table()


def air_bin_h(h: float) -> float:
    return AIR_H[0] if h < 0.5 else AIR_H[1] if h < 1.5 else AIR_H[2] if h < 3.5 else AIR_H[3]


def hero_state_key(h: float, vy: float, grounded: bool, can_dash: bool, dashing: int = 0,
                   wall_behind: float | None = None, wall: bool = False) -> str:
    """The table key of a hero state at the decision. h: transform height above standing height (u); vy (u/s);
    dashing: 0, or +1 / -1 = a ground dash away from / toward the enemy; wall_behind: distance (u) from the hero
    collider's side to the wall on the far side from the enemy; wall: sliding / clinging on that wall."""
    w = None
    if wall or (wall_behind is not None and wall_behind < 0.9):
        w = 0.3
    elif wall_behind is not None and wall_behind < 2.5:
        w = 1.5
    if dashing and grounded:
        return "dash_away" if dashing > 0 else "dash_toward"
    if grounded:
        if w is not None and can_dash:
            return f"ground_w{w}"
        return "ground" if can_dash else "ground_nd"
    hb = air_bin_h(h)
    vn = "rise" if vy > 4.0 else "fall" if vy < -4.0 else "rest"
    d = "d" if can_dash else "nd"
    if w is not None and vn == "rest" and hb in (1.0, 2.5):
        return f"air_h{hb}_rest_{d}_w{w}"
    if w is not None and vn == "rest" and hb < 1.0:
        return f"air_h1.0_rest_{d}_w{w}"
    return f"air_h{hb}_{vn}_{d}"


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
    kind, h, vy, dash, wall, ddir = STATES[name]
    tr = terrain(p, wall)
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


JHOLD = (2, 3, 4, 5, 6, 7, 8, 10, 14, None)
GAP2 = (2, 8)
DHOLD = (2, 8, None)


def starts(T: int) -> list:
    return list(range(0, 12, 2)) + list(range(12, T, 3))


def channels(T: int, jump_held: bool):
    """Move / jump / dash channel masks [*, T] (hero_lib.channels with the two-speed start grid)."""
    km = _km()
    L, R, J, D = km.B_LEFT, km.B_RIGHT, km.B_JUMP, km.B_DASH
    st = starts(T)
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
        for h in JHOLD:
            e = T if h is None else min(T, tj + h)
            m = np.zeros(T, np.int64)
            m[tj:e] = J
            jp.append(m)
            if h is not None and h <= 8:
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
        for h in DHOLD:
            m = np.zeros(T, np.int64)
            m[td:T if h is None else min(T, td + h)] = D
            dp.append(m)
    return (np.unique(np.stack(mv), axis=0), np.unique(np.stack(jp), axis=0), np.unique(np.stack(dp), axis=0))


def build_library(name: str, p, phase: float = 0.0, lat: int = 0, T: int = 42, quant: float = 0.03,
                  threads: int = 4) -> np.ndarray:
    """float32 [N, T, 2]: HeroBox-centre displacement at frames 1..T after the decision (index k - 1), distinct
    trajectories at `quant` u. The first `lat` frames keep the mask latched at the decision."""
    km = _km()
    S, latched = start_state(name, p, phase)
    tr = terrain(p, STATES[name][4])
    mv, jp, dp = channels(T - lat, (latched & km.B_JUMP) != 0)
    jd = (jp[:, None, :] | dp[None, :, :]).reshape(-1, T - lat)
    c0 = None
    trajs, keys = [], []
    for m in mv:
        tail = jd | m[None, :]
        masks = np.empty((len(tail), T), np.int64)
        masks[:, :lat] = latched
        masks[:, lat:] = tail
        masks = np.unique(masks, axis=0)
        r = km.rollout(S, masks, p, tr, threads=threads)
        c = r.centre
        if c0 is None:
            c0 = c[0, 0].copy()
        d = (c[:, 1:] - c0[None, None, :]).astype(np.float32)
        q = np.round(d / quant).astype(np.int16).reshape(len(d), -1)
        _, f = np.unique(q, axis=0, return_index=True)
        trajs.append(d[f])
        keys.append(q[f])
    q = np.concatenate(keys)
    _, f = np.unique(q, axis=0, return_index=True)
    lib = np.concatenate(trajs)[f]
    order = np.argsort(-np.abs(lib[:, -1]).sum(1))          # far-reaching first: escapes are found early
    return np.ascontiguousarray(lib[order])


# ---------------------------------------------------------------------------------------------- the scan kernel
@lru_cache(maxsize=1)
def _kernel():
    import numba

    @numba.njit(cache=True, inline="always")
    def _hit(cx, cy, hx, hy, mx, my, ux, uy, a, b):
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
    def _pos(lib, i, k, cx0, cy0, floor_c, wall_c, g2, vmax):
        """HeroBox centre at frame k (1-based); after the library horizon: ballistic continuation."""
        T = lib.shape[1]
        if k <= T:
            return cx0 + lib[i, k - 1, 0], cy0 + lib[i, k - 1, 1]
        x, y = cx0 + lib[i, T - 1, 0], cy0 + lib[i, T - 1, 1]
        vx = lib[i, T - 1, 0] - lib[i, T - 2, 0]
        vy = lib[i, T - 1, 1] - lib[i, T - 2, 1]
        for _ in range(k - T):
            vy = max(vy - g2, -vmax)
            x += vx
            y += vy
            if y < floor_c:
                y = floor_c
                vy = 0.0
            if x > wall_c:
                x = wall_c
        return x, y

    @numba.njit(cache=True)
    def _escapes(lib, i, cx0, cy0, floor_c, wall_c, ux_a, uy_a, px_a, py_a, rel_a, sstop_a, step, hx, hy, hl, ht,
                 back, g2, vmax):
        for v in range(ux_a.shape[0]):
            ux, uy, px, py, rel, sstop = ux_a[v], uy_a[v], px_a[v], py_a[v], rel_a[v], sstop_a[v]
            k = rel
            while True:
                s1 = min((k - rel) * step, sstop)
                s0 = s1 if k == rel else min((k - 1 - rel) * step, sstop)
                cx, cy = _pos(lib, i, k, cx0, cy0, floor_c, wall_c, g2, vmax)
                lo, hi = s0 - back - hl, s1 - back + hl
                sm = 0.5 * (lo + hi)
                if _hit(cx, cy, hx, hy, px + ux * sm, py + uy * sm, ux, uy, 0.5 * (hi - lo), ht):
                    return False
                if k == rel:            # the spawn frame's collider as exported: unrotated, horizontal
                    sx = 1.0 if ux >= 0 else -1.0
                    if _hit(cx, cy, hx, hy, px - sx * back, py, 1.0, 0.0, hl, ht):
                        return False
                if s1 >= sstop:
                    break
                k += 1
        return True

    @numba.njit(cache=True, parallel=True)
    def scan(lib, cells, floor_c, wall_c, ux_a, uy_a, px_a, py_a, rel_a, sstop_a, step, hx, hy, hl, ht, back, g2,
             vmax, nchunk):
        """cells [C, 2] HeroBox centre rel. the enemy; per-cell pin variants [C, V] (direction, spawn point,
        release frame, flight until it sticks). Returns [C] the first escaping trajectory, -1 = inescapable."""
        C = cells.shape[0]
        N = lib.shape[0]
        out = np.full(C, -1, np.int64)
        per = (C + nchunk - 1) // nchunk
        for ch in numba.prange(nchunk):
            last = -1
            for ci in range(ch * per, min(C, (ch + 1) * per)):
                if floor_c[ci] > 1e8:          # not a possible position
                    out[ci] = -2
                    continue
                cx0, cy0, fc, wc = cells[ci, 0], cells[ci, 1], floor_c[ci], wall_c[ci]
                ux, uy, px, py, rl, ss = ux_a[ci], uy_a[ci], px_a[ci], py_a[ci], rel_a[ci], sstop_a[ci]
                if last >= 0 and _escapes(lib, last, cx0, cy0, fc, wc, ux, uy, px, py, rl, ss, step, hx, hy, hl, ht,
                                          back, g2, vmax):
                    out[ci] = last
                    continue
                for i in range(N):
                    if _escapes(lib, i, cx0, cy0, fc, wc, ux, uy, px, py, rl, ss, step, hx, hy, hl, ht, back, g2,
                                vmax):
                        out[ci] = i
                        last = i
                        break
        return out

    return scan, _escapes


def pin_variants(att: AimedAttack, cells: np.ndarray, floor_rel: np.ndarray, wall_rel: np.ndarray):
    """Per cell and variant (aim error x release x drift): pin direction, spawn point, release frame and the flight
    length until the pin's front reaches the floor or the wall (it sticks)."""
    tx, ty = cells[:, 0], cells[:, 1] + att.aim_dy
    e = np.degrees(np.arctan2(ty, tx))
    V = [(o, r, d) for o in att.aim_err_deg for r in att.release_frames for d in att.drift]
    C = len(cells)
    ux, uy, px, py, rel, ss = (np.zeros((C, len(V))) for _ in range(6))
    rel = rel.astype(np.int64)
    front = att.half_len - att.back
    for j, (o, r, d) in enumerate(V):
        ec = np.clip(e + o, *att.fan_deg)
        up = (ec >= att.up_deg[0]) & (ec <= att.up_deg[1])
        a = np.radians(ec)
        ux[:, j], uy[:, j] = np.cos(a), np.sin(a)
        px[:, j] = np.where(up, att.spawn_up[0], att.spawn_down[0]) + d[0]
        py[:, j] = np.where(up, att.spawn_up[1], att.spawn_down[1]) + d[1]
        rel[:, j] = r
        s = np.full(C, att.s_max)
        with np.errstate(divide="ignore", invalid="ignore"):
            sf = np.where(uy[:, j] < -1e-9, (floor_rel - py[:, j]) / uy[:, j] - front, np.inf)
            sw = np.where(ux[:, j] > 1e-9, (wall_rel - px[:, j]) / ux[:, j] - front, np.inf)
        ss[:, j] = np.maximum(0.0, np.minimum(s, np.minimum(sf, sw)))
    return ux, uy, px, py, rel, ss


def cell_geometry(name: str, p, cells: np.ndarray):
    """Per cell: the floor's HeroBox-centre clip (rel. the enemy), the floor y and the far wall x (rel. the enemy);
    impossible enemy positions (below / above its recorded y range) get floor_c = 1e9."""
    kind, h, vy, dash, wall, _ = STATES[name]
    floor_rel = cells[:, 1] - (HB_STAND + h)
    floor_c = floor_rel + HB_STAND
    reed_y = FLOOR_Y + HB_STAND + h - cells[:, 1]
    bad = (reed_y < REED_Y_MIN) | (reed_y > REED_Y_MAX)
    floor_c = np.where(bad, 1e9, floor_c)
    if wall is None:
        wall_rel = np.full(len(cells), 1e6)
        wall_c = np.full(len(cells), 1e6)
    else:
        wall_rel = cells[:, 0] + p.half_width + wall
        wall_c = wall_rel - HB_HW
    return floor_rel, floor_c, wall_rel, wall_c


def scan_state(lib: np.ndarray, name: str, att: AimedAttack, p, nchunk: int = 64) -> np.ndarray:
    """int8 [len(GRID_Y), len(GRID_X)]: 1 inescapable, 0 escapable, -1 impossible enemy position."""
    scan, _ = _kernel()
    gx, gy = np.meshgrid(GRID_X, GRID_Y)
    cells = np.stack([gx.ravel(), gy.ravel()], 1).astype(np.float64)
    floor_rel, floor_c, wall_rel, wall_c = cell_geometry(name, p, cells)
    ux, uy, px, py, rel, ss = pin_variants(att, cells, floor_rel, wall_rel)
    ft = p.frame_time
    g2 = p.gravity * ft * ft
    vmax = p.max_fall * ft
    first = scan(lib.astype(np.float32), cells, floor_c, wall_c, ux, uy, px, py, rel, ss, att.speed * ft,
                 HB_HW, HB_HH, att.half_len, att.half_thick, att.back, g2, vmax, nchunk)
    z = np.where(first == -2, -1, np.where(first < 0, 1, 0)).astype(np.int8)
    return z.reshape(len(GRID_Y), len(GRID_X))


def path_escapes(path: np.ndarray, rel_xy: tuple, name: str, att: AimedAttack, p) -> bool:
    """Does a given HeroBox-centre displacement path [T, 2] (frames 1..T after the decision) from the cell rel_xy
    escape every pin variant? (The validation's test of a recorded path.)"""
    _, esc = _kernel()
    cells = np.array([rel_xy], np.float64)
    floor_rel, floor_c, wall_rel, wall_c = cell_geometry(name, p, cells)
    floor_c = np.where(floor_c > 1e8, floor_rel + HB_STAND, floor_c)
    ux, uy, px, py, rel, ss = pin_variants(att, cells, floor_rel, wall_rel)
    ft = p.frame_time
    lib = np.ascontiguousarray(np.asarray(path, np.float32)[None])
    return bool(esc(lib, 0, cells[0, 0], cells[0, 1], floor_c[0], wall_c[0], ux[0], uy[0], px[0], py[0], rel[0],
                    ss[0], att.speed * ft, HB_HW, HB_HH, att.half_len, att.half_thick, att.back,
                    p.gravity * ft * ft, p.max_fall * ft))


# ---------------------------------------------------------------------------------------------- the stored table
class AimICS:
    """Reader of aim_ics_<type>.npz: zone grids per (family, hero state, latency), union over physics phases."""

    def __init__(self, path: str | Path = DEFAULT_NPZ):
        z = np.load(path, allow_pickle=False)
        self.meta = json.loads(str(z["meta"]))
        self.gx = z["grid_x"]
        self.gy = z["grid_y"]
        self._z = {k: z[k] for k in z.files if k.startswith("z|")}

    def zone(self, family: str, hero_state: str, latency: int) -> np.ndarray:
        """int8 [len(grid_y), len(grid_x)] in fan coordinates: x = (hero HeroBox centre - enemy).x toward the
        hero's side (the fan the enemy throws into: mirror for the left fan), y = up; 1 inescapable, 0 escapable,
        -1 impossible enemy position."""
        return self._z[f"z|{family}|{hero_state}|{latency}"]

    def keys(self) -> list:
        return [tuple(k.split("|")[1:]) for k in self._z]

    def inescapable(self, family: str, hero_state: str, latency: int, hero_hb: tuple, enemy: tuple) -> bool:
        """Is the hero (HeroBox centre, world) inside the zone of an enemy at `enemy` (transform, world)?"""
        dx = abs(hero_hb[0] - enemy[0])
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
    """The zone grid of an enemy type (only "Reed" is stored), see AimICS.zone."""
    return _reader(str(path or KNOW / "enemies" / "forum" / f"aim_ics_{type_name}.npz")).zone(family, hero_state,
                                                                                                latency)


@lru_cache(maxsize=4)
def _reader(path: str) -> AimICS:
    return AimICS(path)


# ---------------------------------------------------------------------------------------------- CLI
def cmd_scan(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    p = hero_params(bool(args.weighted))
    names = args.states or list(STATES)
    for phase in args.phases:
        for name in names:
            for lat in args.lats:
                tag = f"{name}|{lat}|{phase}"
                done = [f for f in args.families if (out / f"z_{f}__{name}__lat{lat}__ph{phase}.npy").exists()]
                if len(done) == len(args.families):
                    continue
                t0 = time.perf_counter()
                lib = build_library(name, p, phase, lat, args.T)
                tb = time.perf_counter() - t0
                for fam in args.families:
                    f = out / f"z_{fam}__{name}__lat{lat}__ph{phase}.npy"
                    if f.exists():
                        continue
                    t1 = time.perf_counter()
                    z = scan_state(lib, name, FAMILIES[fam], p)
                    np.save(f, z)
                    print(f"{tag} {fam}: lib {len(lib)} ({tb:.0f} s), zone {(z == 1).sum() * GRID_DX ** 2:.2f} u2 "
                          f"({time.perf_counter() - t1:.0f} s)", flush=True)


def cmd_pack(args):
    src = Path(args.src)
    zs, phases_by = {}, {}
    for f in sorted(src.glob("z_*__*__lat*__ph*.npy")):
        fam, name, lat, ph = f.stem[2:].split("__")
        key = f"z|{fam}|{name}|{int(lat[3:])}"
        z = np.load(f)
        if key in zs:
            zs[key] = np.where((zs[key] == 1) | (z == 1), 1, zs[key]).astype(np.int8)
        else:
            zs[key] = z.astype(np.int8)
        phases_by.setdefault(key, []).append(float(ph[2:]))
    meta = {"type": "Reed", "attack": "RE_THROW", "grid_dx": GRID_DX,
            "coords": "x = |hero HeroBox centre - enemy transform|.x toward the hero's side (= the fan), y up",
            "hero_box": [2 * HB_HW, 2 * HB_HH, HB_DY], "families": {k: v.__dict__ for k, v in FAMILIES.items()},
            "states": {k: dict(zip(("kind", "h", "vy", "dash_ready", "wall_behind", "dash_dir"), v))
                       for k, v in STATES.items()},
            "latencies": "first free key on decision + 1 + latency", "phases": {k: sorted(v) for k, v in
                                                                                 phases_by.items()},
            "values": "1 inescapable, 0 escapable, -1 impossible enemy position", "source": "ssbot.tools.aim_ics"}
    npz = Path(args.npz)
    np.savez_compressed(npz, meta=np.array(json.dumps(meta)), grid_x=GRID_X, grid_y=GRID_Y, **zs)
    summ = {"meta": {k: meta[k] for k in ("type", "attack", "grid_dx", "coords", "hero_box", "latencies", "values")},
            "area_u2": {k[2:]: round(float((v == 1).sum() * GRID_DX ** 2), 2) for k, v in sorted(zs.items())},
            "max_dist_u": {k[2:]: _max_dist(v) for k, v in sorted(zs.items())},
            "phases": meta["phases"]}
    npz.with_suffix(".json").write_text(json.dumps(summ, indent=1), "utf-8")
    print(f"packed {len(zs)} zones -> {npz}")


def _max_dist(z: np.ndarray) -> float:
    iy, ix = np.nonzero(z == 1)
    if not len(ix):
        return 0.0
    return round(float(np.hypot(GRID_X[ix], GRID_Y[iy]).max()), 2)


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
    a.add_argument("--states", nargs="*")
    a.add_argument("--families", nargs="+", default=list(FAMILIES))
    a.add_argument("--lats", nargs="+", type=int, default=list(LATENCIES))
    a.add_argument("--phases", nargs="+", type=float, default=list(PHASES))
    a.add_argument("--T", type=int, default=42)
    a.add_argument("--weighted", type=int, default=0)
    b = sub.add_parser("pack")
    b.add_argument("--src", required=True)
    b.add_argument("--npz", default=str(DEFAULT_NPZ))
    args = ap.parse_args()
    {"scan": cmd_scan, "pack": cmd_pack}[args.cmd](args)


if __name__ == "__main__":
    main()
