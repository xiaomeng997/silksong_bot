"""Idle enemies: the inescapable zone of an attack committed now (task "idle enemies: the inescapable zone", forum.md
Â§26; the person 2026-10-08). Measurement only: nothing here changes the planner or the forecast.

The person's definition: an enemy that has not started an attack needs no dodging. For each attack it could start,
assume it commits NOW; take its damage boxes over time (the family template, hero-centre configuration space: the
hero hurtbox centres a collider meets), start from its last damage frame and go backwards, each frame eroding the
region by the hero's escape reach for one frame and uniting it with that frame's own boxes, down to the commit. The
result (the inescapable zone, ICS) is where the hero must not stand now.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.forum_ics zones --out C:/ssbot/data/m2_forum_ics [--lat 1] [--margin]
    ../scripts/uv.cmd run python -m ssbot.tools.forum_ics replay <run dir | human seg> ... --out <dir> [--every 6]
    ../scripts/uv.cmd run python -m ssbot.tools.forum_ics summary <dir> [--zones <zones dir>] --json <out>

zones (task 2). Per Forum family (the anchor-frame family template support/<fam>/anchor of the behaviour tables: the
logged instances' union over the time since their start, with the certified residual and +-1 bin baked in, dilated
here by the hero hurtbox half extents; option --margin adds the family's support margin) and per hero lock state at
the commit (free: standing on the floor; attack: a Wanderer swing pressed on the commit frame, toward the enemy: no
turn / dash for its 0.10 s recovery; dash: a ground dash toward the enemy pressed on the commit frame; air: mid-air at
rest (vy 0) at heights 0.5 .. 8 u above standing height), with the Wanderer Forum loadout (hero_wanderer_forum.json,
Weighted Anklet = the Weighted Belt: max fall 38 u/s) on an open floor (no walls), two bounds of the zone:
  upper (ub)  start positions from which no trajectory of a library escapes: every trajectory meets the template
              at some frame from the commit to the template's last bin. The library (LIB_SIZE command sequences,
              rolled out with the planner's kinematics from the lock state): stand / run / sprint either way, full /
              short jumps, dashes, a jump with an air dash, a dash then a jump, each after a wait of 0 .. 30 frames,
              then a turn (stop, either way, with or without a new jump) at 24 / 45 / 75 frames. The hero reacts
              `lat` frames after the commit (oracle 1 frame; --lat 12: a human-like 0.2 s). A superset of the true
              zone (more escapes could exist);
  lower (lb)  the person's backward erosion with a one-frame reach box that holds every move of the model
              (|dx| <= dash speed / 60, dy in [-max fall, +jump speed] / 60), the floor solid: a subset of the true
              zone (the box ignores momentum and gravity).
Facing: the attack faces the hero at its commit (the instances' mirror equals the hero's side at their start for
every family but the Tiny's AT_DEFEND / AT_LEAVE, the Maestro's MA_SUMMON and the entries), so a hero at (dx, dy)
from the anchor sees the template mirrored to its side: the zone in the world is ub(|dx|, dy); the non-facing
families take both mirrors. The body: the template's cells at the commit (bins of t <= 1 frame), "beyond the body"
= outside them. Special cases: the Reed's throw (RE_THROW: the template is every pin ever thrown) also with the aimed
pin model of the planner (ForumPlanner._pin_contacts: 31 u/s from 1.6 u off the Reed, aimed at where the hero was 20
frames before the release, +-15 deg); the re-arms (CB_THROW, RE_THROW, CC_CAST whose least commit -> first damage is
a hazard of an earlier instance) are hazards already in flight, the hazard layer's (not an idle enemy's).

replay (tasks 1 and 3): recorded episodes (bot runs: <run dir>; the person: <session>:win:<attempts> /
<session>:w0[:<attempts>] as tools.forum_human_score) replayed open loop through ForumPlannerPolicy (the planner's
switches are the environment's, as in forum_human_score); every `every`-th frame:
  idle      every enemy in play, alive and in its idle family (no attack committed): its placements alone (owner
            filter) queried with the forecast's own occupancy (MultiForecast placements / boxes) on a hero-centre
            grid over the arena (IDLE_U cells, hero centres from standing height up) at plan frames 1, 6, 12, 18,
            24, 36, split by layer (forum_layer_audit.classify): body (idle tube, collider tube, current idle
            states), not_started (later attacks / idle instances), window (window placements, family-wide union),
            committed (fine, bbox, chain), tail; and the margins (the same tick's forecast on tables with every margin
            x 0: the area only the margins add). Body = the enemy's last seen damage box dilated by the hero hurtbox.
  whatif    the planner's known, allowed rows (nominal box centres, frames 1 .. T, invulnerable frames clear): S now
            (the whole support), S without the not-started layer (level 1, forum_layer_audit), and S with the
            not-started layer replaced by the ICS (ub, per family x the row's lock state at that frame, placed on
            every in-play enemy's anchor dead-reckoned to the frame, mirrored to the hero's side, from the enemy's
            earliest possible start t_strike on); FORCED_RISK (no row with S = 0) under each; for the person's
            recordings the person's own keys rolled out from the tick's state (forum_human_score's keys row) judged
            the same three ways, with its hindsight (the recorded colliders).
"""
import argparse
import json
import math
import random
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numba
import numpy as np

REPO = Path(__file__).resolve().parents[3]
FORUM_DIR = REPO / "knowledge" / "1.0.30000" / "enemies" / "forum"
WANDERER = REPO / "knowledge" / "1.0.30000" / "kinematics" / "hero_wanderer_forum.json"
LOCKS = ("free", "attack", "dash", "air")
AIR_H = tuple(np.round(np.arange(0.5, 8.01, 0.5), 2))      # air starts: u above the standing hurtbox centre
LAT_F = 1                                                    # oracle sensing latency (multi_forecast.REACT_LATENCY_S)
DX_STEP = 0.1                                                # zone grid (u) along x
AIR_DX_STEP = 0.25
WAITS = (0, 6, 12, 20, 30)
JUMP_STEP_F = 4                                              # timed jumps every this many frames (2: the same
#                                                              zones for CC_SLAM, CB_EVADE, RE_EVADE, EN_SLASH)
TURNS = (24, 45, 75)
ACTS = ("none", "jump_full", "jump_short", "dash", "sprint", "jump_airdash", "dash_jump")
FACING_EXCEPT = frozenset({"AT_DEFEND", "AT_LEAVE", "MA_SUMMON"})   # instances' mirror != the hero's side often
RE_ARMS = frozenset({"CB_THROW", "RE_THROW", "CC_CAST"})
RUNE_LEFTOVERS = frozenset({"CC_CAST", "CC_JUMP_CAST"})     # templates holding earlier casts' runes (summary split)
PIN_FAMS = frozenset({"RE_THROW"})
PLAN_F = (1, 6, 12, 18, 24, 36)
LATE_F = 6                                                   # a zone point the best escape survives this long past
#                                                              the reaction: the attack itself, not contact at commit
IDLE_U = 0.5                                                  # task 1 grid (u)
LIB_SIZE = None                                              # set by commands()


# ------------------------------------------------------------------------------------------------ the hero


def hero_params():
    from ssbot.knowledge.kinematics import HeroParams
    return HeroParams.load(WANDERER).with_weighted()


def commands(K: int, lat: int) -> tuple[np.ndarray, list]:
    """[N, K] escape command masks (frame j's command in column j: index 0 = the first frame after the start) for a
    hero facing -x (the enemy at -x: "away" = +x); the lock's own commands are or-ed in by library()."""
    from ssbot.knowledge import kinematics as kin
    D = {-1: kin.B_LEFT, 0: 0, 1: kin.B_RIGHT}
    seqs, names = [], []

    def jump(m, a, n):
        if a < K:
            if a > 0:
                m[a - 1] &= ~kin.B_JUMP
            m[a:min(K, a + n)] |= kin.B_JUMP

    for d1 in (1, -1, 0):
        for act in ACTS:
            for w in (WAITS if act != "none" else (0,)):
                turns = [(None, None, False)] + [(t2, d2, j2) for t2 in TURNS for d2 in (1, -1, 0)
                                                 for j2 in (False, True) if not (d2 == d1 and not j2)]
                for t2, d2, j2 in turns:
                    m = np.zeros(K, np.int64)
                    m[lat:] |= D[d1]
                    a = lat + w
                    if act == "jump_full":
                        jump(m, a, 40)
                    elif act == "jump_short":
                        jump(m, a, 6)
                    elif act == "dash":
                        m[a:a + 3] |= kin.B_DASH
                    elif act == "sprint":
                        m[a:a + 60] |= kin.B_DASH
                    elif act == "jump_airdash":
                        jump(m, a, 40)
                        m[a + 12:a + 15] |= kin.B_DASH
                    elif act == "dash_jump":
                        m[a:a + 3] |= kin.B_DASH
                        jump(m, a + 8, 40)
                    if t2 is not None:
                        a2 = lat + t2
                        if a2 < K:
                            m[a2:] &= ~(kin.B_LEFT | kin.B_RIGHT)
                            m[a2:] |= D[d2]
                            if j2:
                                jump(m, a2, 40)
                    seqs.append(m)
                    names.append(f"{d1:+d}:{act}:w{w}" + ("" if t2 is None else f":t{t2}{d2:+d}{'j' if j2 else ''}"))
    # timed jumps: run / sprint / stand, then a full jump at any 4th frame (waves along the floor, late slams)
    for d1 in (1, -1, 0):
        for mode in ("run", "sprint"):
            if mode == "sprint" and d1 == 0:
                continue
            for j in range(0, 160, JUMP_STEP_F):
                m = np.zeros(K, np.int64)
                m[lat:] |= D[d1]
                if mode == "sprint":
                    m[lat:lat + 400] |= kin.B_DASH
                jump(m, lat + j, 40)
                seqs.append(m)
                names.append(f"{d1:+d}:{mode}:jump@{j}")
    return np.stack(seqs), names


def library(params, lock: str, K: int, lat: int, h: float = 0.0) -> tuple[np.ndarray, list, np.ndarray]:
    """(displacements [N, K + 1, 2] float32 of the hurtbox centre from its start, the command names, ok [N]: the
    sequence is a different path) for a hero facing -x (toward an enemy at -x) in lock state `lock` (air: h u above
    the standing centre, at rest)."""
    from ssbot.core.forum import FLOOR_Y
    from ssbot.knowledge import kinematics as kin
    cmds, names = commands(K, lat)
    if lock == "attack":
        cmds[:, 0] |= kin.B_ATTACK | kin.B_LEFT
        cmds[:, 1:3] &= ~kin.B_ATTACK
    elif lock == "dash":
        cmds[:, :3] |= kin.B_DASH | kin.B_LEFT
        cmds[:, :3] &= ~kin.B_RIGHT
    terrain = kin.Terrain2D.from_boxes([(-600.0, FLOOR_Y - 10.0, 600.0, FLOOR_Y)])
    y = FLOOR_Y + params.foot + (h if lock == "air" else 0.0)
    S = kin.initial_state(params, 0.0, y, facing=-1, ground=lock != "air")
    ro = kin.rollout(S, cmds, params, terrain, threads=4)
    c = 0.5 * (ro.box[..., :2] + ro.box[..., 2:])
    d = (c - c[:, :1]).astype(np.float32)
    # deduplicate identical paths (many commands do the same in a lock)
    q = np.round(d[:, ::3] / 0.02).astype(np.int32).reshape(len(d), -1)
    _, first = np.unique(q, axis=0, return_index=True)
    ok = np.zeros(len(d), bool)
    ok[first] = True
    return d, names, ok


# ------------------------------------------------------------------------------------------------ templates


def family_templates(margin: bool = False) -> dict:
    """{(type key, family): (hero-centre template (SpaceTimeTemplate, anchor frame), anchor height above the floor
    q05 / q50 / q95, facing share, margin u)}."""
    from ssbot.core.forum import FLOOR_Y, FORUM_TYPES
    from ssbot.knowledge import hitbox_tables as hb
    md = json.loads((FORUM_DIR / "support_margins.json").read_text("utf-8"))
    by_fam = md.get("by_family") or {}
    out = {}
    for tk, sp in FORUM_TYPES.items():
        d = json.loads((FORUM_DIR / f"{sp.enemy}.json").read_text("utf-8"))
        cols = {c: i for i, c in enumerate(d["templates"]["instance_columns"])}
        with np.load(FORUM_DIR / d["templates"]["file"]) as z:
            files = set(z.files)
            for fam in sorted({f.split("/")[1] for f in files if f.startswith("support/") and f.count("/") == 3}):
                k = f"support/{fam}/anchor"
                if k + "/bits" not in files or fam == sp.entry_family:
                    continue
                t = hb.SpaceTimeTemplate.from_arrays(k, z[k + "/bits"], z[k + "/meta"])
                m = float(by_fam.get(f"{tk}/{fam}", 0.0)) if margin else 0.0
                t = t.dilated(rx=hb.HERO_HALF_U[0] + m, ry=hb.HERO_HALF_U[1] + m, key=k)
                inst = z[f"{fam}/instances"] if f"{fam}/instances" in files else np.zeros((0, len(cols)))
                if len(inst):
                    ay = inst[:, cols["anchor_y"]] - FLOOR_Y
                    hq = tuple(float(x) for x in np.nanpercentile(ay, [5, 50, 95]))
                    side = np.sign(inst[:, cols["hero_x"]] - inst[:, cols["anchor_x"]])
                    okk = side != 0
                    face = float(np.mean(inst[okk, cols["mirror"]] == side[okk])) if okk.any() else 1.0
                else:
                    hq, face = (0.0, 0.0, 0.0), 1.0
                out[(tk, fam)] = (t, hq, face, m)
    return out


_HULLS: dict = {}


def body_mask(t, tk: str | None = None) -> np.ndarray:
    """(ny, nx) on the template's grid: the enemy's body collider (production_tubes body_hull, relative to the
    transform = the anchor) dilated by the hero hurtbox half extents; without a hull, the template's cells at the
    commit (t <= one frame)."""
    from ssbot.knowledge import hitbox_tables as hb
    if not _HULLS:
        md = json.loads((FORUM_DIR / "support_margins.json").read_text("utf-8"))
        _HULLS.update({k: tuple(v) for k, v in (md.get("production_tubes") or {}).get("body_hull", {}).items()})
    h = _HULLS.get(tk) if tk else None
    if h is None:
        b1 = int(np.rint((1.0 / 60.0 - t.t0) / t.bin_s))
        return np.unpackbits(np.bitwise_or.reduce(t.bits[:max(1, b1 + 1)], axis=0), axis=1, count=t.nx).astype(bool)
    c = t.cell
    xs = (np.arange(t.nx) + t.ix0 + 0.5) * c
    ys = (np.arange(t.ny) + t.iy0 + 0.5) * c
    rx, ry = hb.HERO_HALF_U
    inx = (xs >= min(h[0], -h[2]) - rx) & (xs <= max(h[2], -h[0]) + rx)
    iny = (ys >= h[1] - ry) & (ys <= h[3] + ry)
    return iny[:, None] & inx[None, :]


@numba.njit(cache=True, parallel=True)
def _ics_kernel(bits, nx, ny, nt, ix0, iy0, cell, b_off, px, py, sgn, disp, use, k_end, out, best):
    """out[p]: no used trajectory n keeps (px[p] + sgn[p] * disp[n, k, 0], py[p] + disp[n, k, 1]) out of the
    template's bin k + b_off for every k in 0 .. k_end."""
    P = px.shape[0]
    N = disp.shape[0]
    for p in numba.prange(P):
        esc = -1
        for n in range(N):
            if not use[n]:
                continue
            ok = True
            for k in range(k_end + 1):
                b = k + b_off
                if b < 0 or b >= nt:
                    continue
                x = px[p] + sgn[p] * disp[n, k, 0]
                y = py[p] + disp[n, k, 1]
                ix = int(math.floor(x / cell)) - ix0
                iy = int(math.floor(y / cell)) - iy0
                if 0 <= ix < nx and 0 <= iy < ny:
                    if (bits[b, iy, ix >> 3] >> (7 - (ix & 7))) & 1:
                        ok = False
                        break
            if ok:
                esc = n
                break
        out[p] = esc < 0
        best[p] = esc


@numba.njit(cache=True, parallel=True)
def _survive_kernel(bits, nx, ny, nt, ix0, iy0, cell, b_off, px, py, sgn, disp, use, k_end, out):
    """out[p]: the latest first contact frame over the used trajectories (k_end + 1: one escapes)."""
    P = px.shape[0]
    N = disp.shape[0]
    for p in numba.prange(P):
        best = -1
        for n in range(N):
            if not use[n]:
                continue
            first = k_end + 1
            for k in range(k_end + 1):
                b = k + b_off
                if b < 0 or b >= nt:
                    continue
                x = px[p] + sgn[p] * disp[n, k, 0]
                y = py[p] + disp[n, k, 1]
                ix = int(math.floor(x / cell)) - ix0
                iy = int(math.floor(y / cell)) - iy0
                if 0 <= ix < nx and 0 <= iy < ny:
                    if (bits[b, iy, ix >> 3] >> (7 - (ix & 7))) & 1:
                        first = k
                        break
            if first > best:
                best = first
                if best > k_end:
                    break
        out[p] = best


def survival(t, px: np.ndarray, py: np.ndarray, disp: np.ndarray, use: np.ndarray) -> np.ndarray:
    """[P] the longest any trajectory stays clear from each start (frames; past the template's end: escapes)."""
    act = t.active()
    out = np.zeros(len(px), np.int64)
    if act is None or not len(px):
        return out
    k_end = min(int(np.ceil(act[1] * 60.0 - 1e-6)) + 1, disp.shape[1] - 1)
    b_off = int(np.rint((0.0 - t.t0) / t.bin_s))
    sgn = np.where(px >= 0, 1.0, -1.0)
    _survive_kernel(t.bits, t.nx, t.ny, t.nt, t.ix0, t.iy0, t.cell, b_off, np.ascontiguousarray(px, np.float64),
                    np.ascontiguousarray(py, np.float64), sgn, np.ascontiguousarray(disp), use, k_end, out)
    return out


def zone_ub(t, px: np.ndarray, py: np.ndarray, disp: np.ndarray, use: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(inescapable [P], the first escaping trajectory [P] or -1) of start points (anchor frame, mirror +1); a start
    at x >= 0 faces -x (the library's frame), one at x < 0 faces +x (the library mirrored)."""
    act = t.active()
    if act is None:
        return np.zeros(len(px), bool), np.full(len(px), -1)
    k_end = int(np.ceil(act[1] * 60.0 - 1e-6)) + 1
    k_end = min(k_end, disp.shape[1] - 1)
    b_off = int(np.rint((0.0 - t.t0) / t.bin_s))
    out = np.zeros(len(px), np.bool_)
    best = np.zeros(len(px), np.int64)
    sgn = np.where(px >= 0, 1.0, -1.0)
    _ics_kernel(t.bits, t.nx, t.ny, t.nt, t.ix0, t.iy0, t.cell, b_off, np.ascontiguousarray(px, np.float64),
                np.ascontiguousarray(py, np.float64), sgn, np.ascontiguousarray(disp), use, k_end, out, best)
    return out, best


def zone_lb(t, params, y_floor_rel: float, lat: int) -> tuple[np.ndarray, tuple]:
    """The person's backward erosion on the template's own cells: Z_end = D_end; Z_k = D_k | erode(Z_k+1, B) with B
    the one-frame reach box of every move (dash speed sideways, jump speed up, max fall down), cells below the
    floor (hero centre lower than standing: y < y_floor_rel) solid; for the first `lat` frames the hero stands.
    Returns (Z_0 [ny, nx] bool on the template grid extended by a margin, (ix0, iy0) of that grid)."""
    import cv2
    act = t.active()
    if act is None:
        return np.zeros((t.ny, t.nx), bool), (t.ix0, t.iy0)
    cell = t.cell
    ft = 1.0 / 60.0
    ax = int(math.ceil(params.dash_speed * ft / cell))
    up = int(math.ceil(params.jump_speed * ft / cell))
    dn = int(math.ceil(params.max_fall * ft / cell))
    pad = 4
    ny, nx = t.ny + 2 * pad, t.nx + 2 * pad
    gx0, gy0 = t.ix0 - pad, t.iy0 - pad
    yy = (np.arange(ny) + gy0 + 0.5) * cell
    solid = (yy < y_floor_rel - cell)[:, None] & np.ones((1, nx), bool)
    k_end = int(np.ceil(act[1] * 60.0 - 1e-6)) + 1
    b_off = int(np.rint((0.0 - t.t0) / t.bin_s))
    kern = np.ones((up + dn + 1, 2 * ax + 1), np.uint8)

    def plane(k):
        b = k + b_off
        p = np.zeros((ny, nx), bool)
        if 0 <= b < t.nt:
            p[pad:pad + t.ny, pad:pad + t.nx] = t.plane(b)
        return p
    Z = plane(k_end) | solid
    for k in range(k_end - 1, lat - 1, -1):
        e = cv2.erode(Z.astype(np.uint8), kern, anchor=(ax, dn), borderType=cv2.BORDER_CONSTANT, borderValue=0)
        Z = plane(k) | solid | (e > 0)
    for k in range(lat - 1, -1, -1):
        Z = Z | plane(k)
    return Z & ~solid, (gx0, gy0)


# ------------------------------------------------------------------------------------------------ pins (aimed)


def aimed_zone(px: np.ndarray, py: np.ndarray, disp: np.ndarray, use: np.ndarray, release_f: tuple, aim_lag_f: int,
               speed: float, spawn_u: float, seg: np.ndarray, hx: float, hy: float, spread: tuple, flight_f: int,
               body: tuple | None = None) -> np.ndarray:
    """Inescapable start points of an aimed straight-line strike (anchor at the origin): released at a frame of
    release_f after the commit (any: the enemy picks), from spawn_u off the anchor toward where the hero was aim_lag_f
    frames before the release (rotated by each of `spread`), moving at `speed` for flight_f frames; the strike's
    sample points (offsets `seg` along the flight) meet the hero when within (hx, hy) of its hurtbox centre (the
    hero's half extents included). body (x0, y0, x1, y1) in hero-centre terms: the enemy's body until the release
    (a start inside it is inescapable). A start is inescapable when every trajectory is hit."""
    out = np.zeros(len(px), np.bool_)
    bd = np.array(body if body is not None else (np.inf, np.inf, -np.inf, -np.inf), np.float64)
    _aimed_kernel(np.ascontiguousarray(px, np.float64), np.ascontiguousarray(py, np.float64),
                  np.ascontiguousarray(disp[use]), np.array(release_f, np.int64), int(aim_lag_f), float(speed),
                  float(spawn_u), np.asarray(seg, np.float64), float(hx), float(hy), np.array(spread, np.float64),
                  int(flight_f), bd, out)
    return out


@numba.njit(cache=True, parallel=True)
def _aimed_kernel(px, py, D, rel, lag, speed, spawn, seg, hx, hy, spread, flight, bd, out):
    P, N, K = px.shape[0], D.shape[0], D.shape[1]
    dt = 1.0 / 60.0
    k_body = min(K, rel.max() + 1)
    for p in numba.prange(P):
        sg = 1.0 if px[p] >= 0 else -1.0
        escaped = False
        for n in range(N):
            hit = False
            for k in range(k_body):
                x = px[p] + sg * D[n, k, 0]
                y = py[p] + D[n, k, 1]
                if bd[0] <= x <= bd[2] and bd[1] <= y <= bd[3]:
                    hit = True
                    break
            if not hit:
                for r in range(rel.shape[0]):
                    kr = rel[r]
                    if kr >= K:
                        continue
                    ka = max(kr - lag, 0)
                    axx = px[p] + sg * D[n, ka, 0]
                    ayy = py[p] + D[n, ka, 1]
                    nrm = max(math.hypot(axx, ayy), 1e-6)
                    for a in range(spread.shape[0]):
                        ca, sa = math.cos(spread[a]), math.sin(spread[a])
                        ux = (axx * ca - ayy * sa) / nrm
                        uy = (axx * sa + ayy * ca) / nrm
                        for k in range(kr, min(K, kr + flight)):
                            s = speed * (k - kr) * dt
                            cx = px[p] + sg * D[n, k, 0]
                            cy = py[p] + D[n, k, 1]
                            for q in range(seg.shape[0]):
                                qx = (spawn + s + seg[q]) * ux
                                qy = (spawn + s + seg[q]) * uy
                                if abs(qx - cx) <= hx and abs(qy - cy) <= hy:
                                    hit = True
                                    break
                            if hit:
                                break
                        if hit:
                            break
                    if hit:
                        break
            if not hit:
                escaped = True
                break
        out[p] = not escaped


def pin_zone(px, py, disp, use, release_f: tuple = (40, 60, 80)) -> np.ndarray:
    """The Reed's aimed pin (the planner's model, forum.md Â§23.7): released 40+ frames after the commit (strikes.json:
    p5 0.667 s), from PIN_SPAWN_U off the Reed, PIN_SPEED, aimed at where the hero is PIN_AIM_F frames before the
    release (+-15 deg), its 2 x PIN_HALF_U segment grown by PIN_SKIN."""
    from ssbot.combat.forum_planner import PIN_AIM_F, PIN_HALF_U, PIN_SKIN, PIN_SPAWN_U, PIN_SPEED, PIN_SPREAD
    from ssbot.knowledge import hitbox_tables as hb
    return aimed_zone(px, py, disp, use, release_f, PIN_AIM_F, PIN_SPEED, PIN_SPAWN_U,
                      np.array([-1.0, -0.5, 0.0, 0.5, 1.0]) * PIN_HALF_U, hb.HERO_HALF_U[0] + PIN_SKIN,
                      hb.HERO_HALF_U[1] + PIN_SKIN, PIN_SPREAD, 90)


# the Tiny's dive (AT_FIRE, body only): Fire 0.70 s (q5) after the commit, 39.4 u/s (every instance), in the anchor
# frame toward the hero (26 deg median off its position at the commit: aimed later), until Brake (>= 0.72 s)
TINY_FIRE_F = (42, 48)
TINY_SPEED = 39.4
TINY_FLIGHT_F = 60


def tiny_zone(px, py, disp, use, hull: tuple, aim_lag_f: int = 0) -> np.ndarray:
    from ssbot.knowledge import hitbox_tables as hb
    rx, ry = hb.HERO_HALF_U
    hx, hy = 0.5 * (hull[2] - hull[0]) + rx, 0.5 * (hull[3] - hull[1]) + ry
    body = (hull[0] - rx, hull[1] - ry, hull[2] + rx, hull[3] + ry)
    return aimed_zone(px, py, disp, use, TINY_FIRE_F, aim_lag_f, TINY_SPEED, 0.0, np.zeros(1), hx, hy,
                      tuple(math.radians(a) for a in (-15.0, 0.0, 15.0)), TINY_FLIGHT_F, body)


# ------------------------------------------------------------------------------------------------ zones (task 2)


def _heights(hq3: tuple) -> tuple:
    """The anchor heights a family's zone is computed at: its median, and q05 / q95 when they differ (fliers)."""
    if abs(hq3[2] - hq3[0]) < 0.25:
        return (hq3[1],)
    return tuple(hq3)


def _ground_dy(hq: float) -> float:
    """The standing hero's centre relative to an anchor hq u above the floor."""
    from ssbot.knowledge import hitbox_tables as hb
    return hb.HERO_HALF_U[1] - hq


def _runs(x: np.ndarray, m: np.ndarray, step: float) -> list:
    """[(x0, x1)] runs of m along x."""
    out = []
    i = 0
    while i < len(m):
        if m[i]:
            j = i
            while j + 1 < len(m) and m[j + 1]:
                j += 1
            out.append((round(float(x[i]) - step / 2, 2), round(float(x[j]) + step / 2, 2)))
            i = j + 1
        else:
            i += 1
    return out


def _dist_to(mask_xy: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Distance (u) of points [P, 2] to the nearest point of mask_xy [M, 2] (inf: none)."""
    if not len(mask_xy) or not len(pts):
        return np.full(len(pts), np.inf)
    out = np.empty(len(pts))
    for i in range(0, len(pts), 512):
        d = np.hypot(pts[i:i + 512, None, 0] - mask_xy[None, :, 0], pts[i:i + 512, None, 1] - mask_xy[None, :, 1])
        out[i:i + 512] = d.min(axis=1)
    return out


def family_zone(t, hq3: tuple, face: float, fam: str, libs: dict, params, lat: int, tk: str | None = None) -> dict:
    """One family's zones (module docstring): per lock state the ub zone on the floor row (ground locks) or the
    air grid, beyond-the-body extents, and the lb zone."""
    act = t.active()
    res = {"active_s": None if act is None else [round(act[0], 3), round(act[1], 3)],
           "facing": round(face, 3), "anchor_h": [round(x, 2) for x in hq3], "locks": {}}
    if act is None:
        return res
    bm = body_mask(t, tk)
    c = t.cell
    by, bx = np.nonzero(bm)
    body_xy = np.stack([(bx + t.ix0 + 0.5) * c, (by + t.iy0 + 0.5) * c], axis=1)
    x0, _, x1, _ = t.bounds
    xs = np.round(np.arange(math.floor(x0) - 2.0, math.ceil(x1) + 2.0 + 1e-9, DX_STEP), 3)
    # first damage beyond the body: the first bin with a cell outside the commit-time cells
    first_beyond = None
    for b in range(t.nt):
        p = t.plane(b)
        if (p & ~bm).any():
            first_beyond = round(t.t0 + b * t.bin_s, 3)
            break
    res["first_beyond_body_s"] = first_beyond
    both = face < 0.9 or fam in FACING_EXCEPT
    res["both_mirrors"] = bool(both)
    for lock in LOCKS:
        per_h = []
        hs = AIR_H if lock == "air" else (0.0,)
        for hq in _heights(hq3):
            dy0 = _ground_dy(hq)
            pts, inesc, survs = [], [], []
            for h in hs:
                disp, _, use = libs[(lock, h)]
                step = AIR_DX_STEP if lock == "air" else DX_STEP
                xx = xs if lock != "air" else np.round(np.arange(xs[0], xs[-1] + 1e-9, step), 3)
                yy = np.full(len(xx), dy0 + h)
                z, _ = zone_ub(t, xx, yy, disp, use)
                sv = np.full(len(xx), 10 ** 6)
                if z.any():
                    sv[z] = survival(t, xx[z], yy[z], disp, use)
                if both:
                    zm, _ = zone_ub(t, -xx, yy, disp, use)
                    if zm.any():
                        sm = np.full(len(xx), 10 ** 6)
                        sm[zm] = survival(t, -xx[zm], yy[zm], disp, use)
                        sv = np.minimum(sv, sm)
                    z = z | zm
                pts.append(np.stack([xx, yy], axis=1))
                inesc.append(z)
                survs.append(sv)
            P = np.concatenate(pts)
            Z = np.concatenate(inesc)
            SV = np.concatenate(survs)
            res.setdefault("_arrays", {})[(lock, round(hq, 2))] = (
                xx, np.asarray(hs, np.float64), np.stack(inesc), dy0,
                np.stack(inesc) & (np.stack(survs) >= lat + LATE_F))
            # the body at the start points: their cell in the commit-time mask
            ix = np.floor(P[:, 0] / c).astype(np.int64) - t.ix0
            iy = np.floor(P[:, 1] / c).astype(np.int64) - t.iy0
            inb = (ix >= 0) & (ix < t.nx) & (iy >= 0) & (iy < t.ny)
            in_body = np.zeros(len(P), bool)
            in_body[inb] = bm[iy[inb], ix[inb]]
            if both:
                ixm = np.floor(-P[:, 0] / c).astype(np.int64) - t.ix0
                inbm = (ixm >= 0) & (ixm < t.nx) & (iy >= 0) & (iy < t.ny)
                in_body[inbm] |= bm[iy[inbm], ixm[inbm]]
            beyond = Z & ~in_body
            front = P[:, 0] >= 0 if not both else np.ones(len(P), bool)
            bw = beyond & front
            d = _dist_to(body_xy, P[bw]) if bw.any() else np.zeros(0)
            step = AIR_DX_STEP if lock == "air" else DX_STEP
            area = float(bw.sum()) * step * (0.5 if lock == "air" else 1.0)
            late = SV[bw] >= lat + LATE_F
            rec = {"anchor_h": round(hq, 2), "n_beyond": int(bw.sum()),
                   ("area_u2" if lock == "air" else "length_u"): round(area, 2),
                   "max_dist_u": round(float(d.max()), 2) if len(d) else 0.0,
                   # zone points the best trajectory leaves only after LATE_F frames (the rest: already there at the
                   # commit, contact or a hazard of an earlier instance in the union)
                   "late_n": int(late.sum()), "late_max_dist_u": round(float(d[late].max()), 2) if late.any() else 0.0,
                   "surv_max_f": int(SV[bw].max()) if bw.any() else 0,
                   "max_dx_u": round(float(np.abs(P[bw, 0]).max()), 2) if bw.any() else 0.0,
                   "inescapable_total": int(Z.sum())}
            if lock != "air":
                rec["runs_beyond"] = _runs(P[:, 0], beyond & front, DX_STEP)[:8]
                rec["runs_all"] = _runs(P[:, 0], Z & front, DX_STEP)[:8]
            per_h.append(rec)
        res["locks"][lock] = per_h
    # lower bound: the person's erosion on the floor row and in the air (median anchor height)
    lbs = []
    for hq in _heights(hq3):
        dy0 = _ground_dy(hq)
        Zl, (gx0, gy0) = zone_lb(t, params, dy0 - 1e-6, lat)
        yy, xx = np.nonzero(Zl)
        P = np.stack([(xx + gx0 + 0.5) * c, (yy + gy0 + 0.5) * c], axis=1)
        ix = np.floor(P[:, 0] / c).astype(np.int64) - t.ix0
        iy = np.floor(P[:, 1] / c).astype(np.int64) - t.iy0
        inb = (ix >= 0) & (ix < t.nx) & (iy >= 0) & (iy < t.ny)
        in_body = np.zeros(len(P), bool)
        in_body[inb] = bm[iy[inb], ix[inb]]
        beyond = ~in_body & (P[:, 0] >= 0 if not both else True)
        floor_row = np.abs(P[:, 1] - dy0) < c
        sub = P[beyond][::7] if beyond.sum() > 4000 else P[beyond]
        d = _dist_to(body_xy, sub)
        lbs.append({"anchor_h": round(hq, 2), "area_u2": round(float(beyond.sum()) * c * c, 2),
                    "floor_len_u": round(float((beyond & floor_row).sum()) * c, 2),
                    "max_dist_u": round(float(d.max()), 2) if len(d) else 0.0})
    res["lb"] = lbs
    return res


def ascii_row(xs: np.ndarray, z: np.ndarray, body: np.ndarray, step: float = 0.5) -> str:
    """One floor row as text: '#' body, 'X' inescapable beyond the body, '.' free (every `step` u)."""
    out = []
    for x in np.arange(xs[0], xs[-1] + 1e-9, step):
        i = int(np.argmin(np.abs(xs - x)))
        out.append("#" if body[i] else ("X" if z[i] else "."))
    return "".join(out)


def cmd_zones(a) -> int:
    from ssbot.combat.multi_forecast import strike_table
    from ssbot.knowledge import hitbox_tables as hb
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass
    numba.set_num_threads(a.threads)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    params = hero_params()
    t0 = time.perf_counter()
    tpl = family_templates(margin=a.margin)
    K = int(min(a.k_max, max(int(np.ceil(t.active()[1] * 60)) + 2 for t, *_ in tpl.values() if t.active())))
    print(f"{len(tpl)} families, K {K} frames ({time.perf_counter() - t0:.1f} s)", flush=True)
    libs = {}
    for lock in LOCKS:
        for h in (AIR_H if lock == "air" else (0.0,)):
            d, names, ok = library(params, lock, K, a.lat, h)
            # order: the trajectories that escape most often first (away moves), duplicates off
            libs[(lock, h)] = (d, names, ok)
    n_lib = len(next(iter(libs.values()))[1])
    print(f"libraries: {len(libs)} starts x {n_lib} sequences ({time.perf_counter() - t0:.1f} s)", flush=True)
    res = {"lat_f": a.lat, "margin": bool(a.margin), "K": K, "lib_size": n_lib,
           "air_h": list(AIR_H), "families": {}}
    arrays: dict = {}
    if a.only:
        tpl = {k: v for k, v in tpl.items() if k[1] in a.only}
    for (tk, fam), (t, hq3, face, m) in sorted(tpl.items()):
        t1 = time.perf_counter()
        r = family_zone(t, hq3, face, fam, libs, params, a.lat, tk)
        r["margin_u"] = m
        st = strike_table().get((tk, fam))
        r["strike_min_p5_s"] = None if st is None else [round(st[0], 3), round(st[1], 3)]
        r["re_arm"] = fam in RE_ARMS
        if fam in PIN_FAMS or fam == "AT_FIRE":
            # an aimed model instead of the template's every-direction union: the Reed's pin (the planner's model),
            # the Tiny's dive (TINY_*; the body until the release): the extent beyond the body hull per lock
            hull = _HULLS.get(tk) or (-0.5, -0.5, 0.5, 0.5)
            rx, ry = hb.HERO_HALF_U
            pr = {}
            xx = np.round(np.arange(-16.0, 16.0 + 1e-9, 0.25), 3)
            for lock in LOCKS:
                worst = {"n_beyond": 0, "max_dx_u": 0.0}
                for hq in _heights(hq3):
                    dy0 = _ground_dy(hq)
                    hs_a = AIR_H[::2] if lock == "air" else (0.0,)
                    zs = []
                    for h in hs_a:
                        disp, _, use = libs[(lock, h)]
                        yy = np.full(len(xx), dy0 + h)
                        z = pin_zone(xx, yy, disp, use) if fam in PIN_FAMS else tiny_zone(xx, yy, disp, use, hull)
                        zs.append(z)
                        inb = (np.abs(xx) <= max(abs(hull[0]), hull[2]) + rx) & (yy >= hull[1] - ry) & (yy <= hull[3] + ry)
                        zb = z & ~inb
                        worst["n_beyond"] += int(zb.sum())
                        if zb.any():
                            worst["max_dx_u"] = max(worst["max_dx_u"], round(float(np.abs(xx[zb]).max()), 2))
                            worst.setdefault("runs", []).append([round(hq, 2), h, _runs(xx, zb, 0.25)[:4]])
                    r.setdefault("_arrays_aimed", {})[(lock, round(hq, 2))] = (xx, np.asarray(hs_a, np.float64),
                                                                               np.stack(zs), dy0)
                pr[lock] = worst
            r["aimed"] = pr
        # the floor row as text (free lock, median anchor height)
        disp, _, use = libs[("free", 0.0)]
        dy0 = _ground_dy(hq3[1])
        xs = np.round(np.arange(-20.0, 20.0 + 1e-9, DX_STEP), 3)
        z, _ = zone_ub(t, xs, np.full(len(xs), dy0), disp, use)
        bm = body_mask(t, tk)
        ix = np.floor(xs / t.cell).astype(np.int64) - t.ix0
        iy = int(math.floor(dy0 / t.cell)) - t.iy0
        body = np.zeros(len(xs), bool)
        ok = (ix >= 0) & (ix < t.nx) & (0 <= iy < t.ny)
        body[ok] = bm[iy, ix[ok]]
        r["row_free"] = ascii_row(xs, z & ~body, body)
        for tag in ("_arrays", "_arrays_aimed"):
            for (lock, hq), (xx, hs, zg, dy0, *zl) in (r.pop(tag, None) or {}).items():
                key = f"{tk}|{fam}|{lock}|{hq:.2f}|{'aimed' if tag == '_arrays_aimed' else 'ub'}"
                arrays[key + "|x"], arrays[key + "|h"], arrays[key + "|z"] = xx, hs, np.packbits(zg, axis=1)
                # the late part (the attack itself, not the cells already there at the commit): Zones' default
                arrays[key + "|zl"] = np.packbits(zl[0] if zl else zg, axis=1)
                arrays[key + "|meta"] = np.array([dy0, zg.shape[1], float(r["both_mirrors"])])
        res["families"][f"{tk}/{fam}"] = r
        lk = r["locks"]
        print(f"{tk[-10:]:10s} {fam:13s} ub beyond body (all/late): " + ", ".join(
            f"{L} {max((x['max_dist_u'] for x in lk[L]), default=0):.1f}/"
            f"{max((x['late_max_dist_u'] for x in lk[L]), default=0):.1f}" for L in LOCKS)
            + ("" if "aimed" not in r else " aimed " + "/".join(f"{r['aimed'][L]['max_dx_u']:.1f}" for L in LOCKS))
            + f" lb {max((x['max_dist_u'] for x in r['lb']), default=0):.2f}u ({time.perf_counter() - t1:.1f} s)",
            flush=True)
    p = out / f"zones_lat{a.lat}{'_margin' if a.margin else ''}.json"
    p.write_text(json.dumps(res, indent=1), "utf-8")
    np.savez_compressed(p.with_suffix(".npz"), **arrays)
    print(f"wrote {p} ({time.perf_counter() - t0:.0f} s)")
    return 0


# ------------------------------------------------------------------------------------------------ replay (tasks 1, 3)

CAT = {"body": "body", "collider": "body", "idle_now": "body", "idle": "body",
       "start_attack": "not_started", "start_idle": "not_started", "entry_later": "entry",
       "com_win": "window", "com_fam": "window", "chain_win": "window",
       "com_fine": "committed", "com_bbox": "committed", "chain_fine": "committed", "chain_bbox": "committed",
       "tail": "tail", "entry_now": "entry", "death": "other", "arena": "other",
       "haz_self": "hazard", "haz_path": "hazard", "haz_tube": "hazard"}
IDLE_CATS = ("body", "not_started", "window", "committed", "tail", "other", "margins")
NS_REPLACED = ("start_attack", "start_idle")          # the not-started layer the what-if replaces by the ICS
REL_DX = np.round(np.arange(-12.0, 12.0 + 1e-9, IDLE_U), 3)
REL_H = np.round(np.arange(0.0, 12.0 + 1e-9, IDLE_U), 3)    # above the standing hurtbox centre
LOCK_CODE = {"free": 0, "attack": 1, "dash": 2, "air": 3}


class Zones:
    """The zones file of cmd_zones as lookups: per (type, family) the ub (or the aimed model's) inescapable zone per
    lock state and anchor height."""

    def __init__(self, path: Path, late: bool = True):
        z = np.load(path)
        groups = defaultdict(dict)
        for f in z.files:
            key, part = f.rsplit("|", 1)
            groups[key][part] = z[f]
        self.fams: dict = defaultdict(dict)       # tk -> fam -> lock -> [(hq, x, h, Z, dy0, both)]
        aimed = {tuple(k.split("|")[:2]) for k in groups if k.endswith("|aimed")}
        for key, d in groups.items():
            tk, fam, lock, hq, kind = key.split("|")
            if kind == "ub" and (tk, fam) in aimed:
                continue
            nx = int(d["meta"][1])
            Z = np.unpackbits(d["zl" if late and "zl" in d else "z"], axis=1, count=nx).astype(bool)
            self.fams[tk].setdefault(fam, {}).setdefault(lock, []).append(
                (float(hq), d["x"], d["h"], Z, float(d["meta"][0]), bool(d["meta"][2])))

    def occ(self, tk: str, idle_fam: str, entry_fam: str, a_h: float, dx: np.ndarray, hrel: np.ndarray,
            lock: np.ndarray, skip: frozenset = frozenset()) -> np.ndarray:
        """[n] in some family's zone (not the idle / entry family, not `skip`): dx hero centre - anchor x, hrel the
        hero centre above standing height, lock codes (LOCK_CODE), a_h the anchor's height above the floor."""
        out = np.zeros(len(dx), bool)
        for fam, by_lock in self.fams.get(tk, {}).items():
            if fam in (idle_fam, entry_fam) or fam in skip:
                continue
            for L, code in LOCK_CODE.items():
                m = lock == code
                if not m.any() or L not in by_lock:
                    continue
                rows = by_lock[L]
                hq, x, hs, Z, dy0, both = min(rows, key=lambda r: abs(r[0] - a_h))
                v = dx[m] if both else np.abs(dx[m])
                step = float(x[1] - x[0]) if len(x) > 1 else 1.0
                ix = np.rint((v - x[0]) / step).astype(np.int64)
                if both:
                    ix2 = np.rint((-v - x[0]) / step).astype(np.int64)
                    bad = (ix < 0) | (ix >= len(x))
                    ix = np.where(bad, ix2, ix)
                ok = (ix >= 0) & (ix < len(x))
                if L == "air" and len(hs) > 1:
                    ih = np.clip(np.rint((hrel[m] - hs[0]) / float(hs[1] - hs[0])), 0, len(hs) - 1).astype(np.int64)
                else:
                    ih = np.zeros(int(m.sum()), np.int64)
                hit = np.zeros(int(m.sum()), bool)
                hit[ok] = Z[ih[ok], ix[ok]]
                out[m] |= hit
        return out


def _lock_codes(flags: np.ndarray, mode: np.ndarray, cx: np.ndarray, ax: np.ndarray) -> np.ndarray:
    """[R, F] lock state of each row frame: dash toward the enemy (a dash away: free), attack on the ground, air,
    free."""
    from ssbot.knowledge import kinematics as kin
    ground = (flags & kin.F_GROUND) != 0
    att = (flags & kin.F_ATTACKING) != 0
    dash = mode == kin.M_DASH
    vx = np.gradient(cx, axis=1) if cx.shape[1] > 1 else np.zeros_like(cx)
    toward = np.sign(vx) == -np.sign(cx - ax)
    out = np.where(~ground, 3, np.where(dash & toward, 2, np.where(att, 1, 0)))
    return out.astype(np.int64)


def _box_dist(px, py, b) -> np.ndarray:
    dx = np.maximum(np.maximum(b[0] - px, px - b[2]), 0.0)
    dy = np.maximum(np.maximum(b[1] - py, py - b[3]), 0.0)
    return np.hypot(dx, dy)


def idle_maps(pol, fcast, vs, groups, ws_hero) -> list:
    """Task 1 on one tick: every in-play, alive, idle enemy's own placements on the relative grid at PLAN_F."""
    from ssbot.core.forum import FLOOR_Y, FORUM_TYPES, WALL_L, WALL_R
    from ssbot.knowledge import hitbox_tables as hb
    from ssbot.train.planner_policy import HORIZON_S
    mf = pol.fc
    tk_f = np.array(PLAN_F, np.float64) / 60.0
    hero_cy = FLOOR_Y + hb.HERO_HALF_U[1]
    rx, ry = hb.HERO_HALF_U
    subs = [s for s in fcast.subjects if s.alive and s.in_play and not s.committed and s.pos is not None
            and s.family is not None and FORUM_TYPES.get(s.type_key) is not None
            and s.family == FORUM_TYPES[s.type_key].idle_family]
    if not subs:
        return []
    f2 = None
    out = []
    for s in subs:
        tr = mf.trackers.get(s.iid)
        if tr is None or tr.pos is None:
            continue
        px0, py0 = float(tr.pos[0]), float(tr.pos[1])
        X = px0 + REL_DX[None, :] + 0 * REL_H[:, None]
        Y = hero_cy + REL_H[:, None] + 0 * REL_DX[None, :]
        inside = (X >= WALL_L + rx) & (X <= WALL_R - rx)
        x = np.repeat(X.reshape(-1, 1), len(tk_f), axis=1)
        y = np.repeat(Y.reshape(-1, 1), len(tk_f), axis=1)
        b = tr.seen_box
        if b is None:
            h = mf.tables.tubes.hull.get(s.type_key) or (-0.5, -0.5, 0.5, 0.5)
            b = (px0 + h[0], py0 + h[1], px0 + h[2], py0 + h[3])
        bd = (b[0] - rx, b[1] - ry, b[2] + rx, b[3] + ry)
        dist = _box_dist(X, Y, bd).reshape(-1)
        cats = {c: np.zeros(x.shape, bool) for c in IDLE_CATS}
        fn = {"pm": fcast._fine_occ, "wm": fcast._win_occ, "bb": fcast._bbox_occ}
        meta = {"pm": fcast.pm, "wm": fcast.wm, "bb": fcast.bb}
        # a Tiny group row stands for every Tiny of its cluster (MultiForecast.meta_group)
        owners = [s.iid] + [o for o, mem in (getattr(fcast, "meta_group", None) or {}).items() if s.iid in mem]
        for key, kind, sel in groups:
            own = sel & np.isin(np.asarray(meta[kind]["owner"]), owners)
            if not own.any():
                continue
            cats[CAT.get(key[0], "other") if CAT.get(key[0]) in IDLE_CATS else "other"] |= fn[kind](x, y, tk_f, own)
        for kind in ("idle", "collider", "death", "arena"):
            cats["body" if kind in ("idle", "collider") else "other"] |= fcast._box_occ(x, y, tk_f, kinds=(kind,),
                                                                                      only={s.iid})
        tot = np.zeros(x.shape, bool)
        for c in IDLE_CATS:
            tot |= cats[c]
        # the planner's own query for this enemy alone (the check: tot == occupied_only up to hazards)
        own_q = fcast.occupied_only(x, y, tk_f, {s.iid})
        # margins: the same tick on tables with every margin x 0 (forum_layer_audit.Variants m0)
        if vs is not None:
            if f2 is None:
                try:
                    vs.swap("m0")
                    f2 = mf.forecast(HORIZON_S, origin_t=fcast.origin_t)
                finally:
                    vs.restore()
            m0 = f2.occupied_only(x, y, tk_f, {s.iid})
            cats["margins"] = tot & ~m0
        ok = inside.reshape(-1)[:, None] & (dist[:, None] > 0)
        rec = {"tk": s.type_key, "iid": int(s.iid), "state": s.state, "pos": [round(px0, 2), round(py0, 2)],
               "h_anchor": round(py0 - FLOOR_Y, 2),
               "hero_d": None if ws_hero is None else round(math.hypot(ws_hero[0] - px0, ws_hero[1] - py0), 2),
               "others8": int(sum(1 for o in fcast.subjects if o.alive and o.in_play and o.iid != s.iid
                                  and o.pos is not None and math.hypot(o.pos[0] - px0, o.pos[1] - py0) < 8.0)),
               "t_strike": None if not math.isfinite(s.t_strike) else round(s.t_strike, 3),
               "body_box": [round(v, 2) for v in bd], "frames": list(PLAN_F)}
        a_cell = IDLE_U * IDLE_U
        for c in ("total", "own_q") + IDLE_CATS:
            o = tot if c == "total" else own_q if c == "own_q" else cats[c]
            ob = o & ok
            rec[c] = [[round(float(ob[:, j].sum()) * a_cell, 3),
                       round(float(dist[ob[:, j]].max()), 2) if ob[:, j].any() else 0.0] for j in range(len(tk_f))]
        # exclusive: the cells only this category covers (the leave-one-out of the area)
        rec["only"] = {}
        for c in IDLE_CATS:
            if c == "margins":
                continue
            rest = np.zeros(x.shape, bool)
            for c2 in IDLE_CATS:
                if c2 not in (c, "margins"):
                    rest |= cats[c2]
            rec["only"][c] = [round(float((cats[c] & ~rest & ok)[:, j].sum()) * a_cell, 3) for j in range(len(tk_f))]
        rec["_maps"] = {c: (tot if c == "total" else cats[c]).reshape(len(REL_H), len(REL_DX), len(tk_f))
                        for c in ("total",) + IDLE_CATS}
        rec["_inside"] = inside
        out.append(rec)
    return out


def whatif(pol, fcast, groups, dbg, zones: Zones, keys_row=None) -> dict:
    """Task 3 on one tick: the rows' S under the whole support, without the not-started layer (NS_REPLACED), and with
    it replaced by the ICS (module docstring); keys_row (box, flags, mode, inv): the person's own keys judged alike."""
    from ssbot.core.forum import FLOOR_Y, FORUM_TYPES
    from ssbot.knowledge import hitbox_tables as hb
    from ssbot.knowledge.kinematics import F_INVULN
    from ssbot.tools.forum_layer_audit import group_occ
    mf = pol.fc
    hero_cy = FLOOR_Y + hb.HERO_HALF_U[1]
    rows = np.flatnonzero(dbg["ok"] & dbg["known"])
    box, flags, mode = dbg["box"], dbg["flags"], dbg["mode"]
    T1 = box.shape[1]
    fr = np.arange(1, T1)
    tk = dbg["tk"][fr]

    def judge(bx, fl, md):
        cx, cy = 0.5 * (bx[..., 0] + bx[..., 2]), 0.5 * (bx[..., 1] + bx[..., 3])
        live = (fl & F_INVULN) == 0
        occ = group_occ(fcast, cx, cy, tk, live, groups)
        now = np.zeros(cx.shape, bool)
        l1 = np.zeros(cx.shape, bool)
        for k, o in occ.items():
            now |= o
            if k[0] not in NS_REPLACED:
                l1 |= o
        ics = np.zeros(cx.shape, bool)
        for s in fcast.subjects:
            if not (s.alive and s.in_play) or not math.isfinite(s.t_strike):
                continue
            tr = mf.trackers.get(s.iid)
            sp = FORUM_TYPES.get(s.type_key)
            if tr is None or tr.pos is None or sp is None:
                continue
            age = fcast.origin_t - tr.seen_T
            ax = tr.pos[0] + tr.vel[0] * (age + tk)
            ay = tr.pos[1] + tr.vel[1] * (age + tk)
            m = (tk[None, :] >= s.t_strike - 1e-9) & live
            if not m.any():
                continue
            lock = _lock_codes(fl, md, cx, ax[None, :])
            hrel = cy - hero_cy
            lock = np.where((lock < 3) & (hrel > 0.25), 3, lock)
            a_h = float(np.median(ay)) - FLOOR_Y
            dx = cx - ax[None, :]
            sel = m & (np.abs(dx) < 45.0)
            if sel.any():
                ics[sel] |= zones.occ(s.type_key, sp.idle_family, sp.entry_family, a_h, dx[sel], hrel[sel], lock[sel])
        wi = l1 | ics
        return now.any(axis=1), l1.any(axis=1), wi.any(axis=1), (ics & ~l1).any(axis=1)

    if len(rows):
        s_now, s_l1, s_wi, ics_only = judge(box[rows][:, fr], flags[rows][:, fr], mode[rows][:, fr])
    else:
        s_now = s_l1 = s_wi = ics_only = np.zeros(0, bool)
    S_pl = np.asarray(pol.planner.last_info.get("S"))
    res = {"R": int(len(rows)), "safe_now": int((~s_now).sum()), "safe_l1": int((~s_l1).sum()),
           "safe_wi": int((~s_wi).sum()), "ics_only_rows": int(ics_only.sum()),
           "pl_safe": int((S_pl[rows] == 0).sum()) if len(rows) and S_pl.ndim else None}
    if keys_row is not None:
        kb, kf, kmode = keys_row
        a, b_, c, d = judge(kb[None, 1:T1], kf[None, 1:T1], kmode[None, 1:T1])
        res["keys"] = [bool(a[0]), bool(b_[0]), bool(c[0]), bool(d[0])]
    return res


def _episodes(spec: str, demo_cache) -> list[dict]:
    """A bot run dir (every episode of attempts_i*.jsonl) or a human segment spec (forum_human_score)."""
    if len(spec) > 2 and spec[1] == ":" and spec.count(":") >= 2:
        from ssbot.tools.forum_human_score import segments
        return [{"kind": "human", "seg": s} for s in segments(spec, demo_cache)]
    run = Path(spec)
    out = []
    for f in sorted(run.glob("attempts_i*.jsonl")):
        inst = int(f.stem.split("_i")[1])
        for x in f.read_text("utf-8").splitlines():
            if not x.strip():
                continue
            r = json.loads(x)
            if r.get("outcome") == "HARNESS_FAIL" or not r.get("recording"):
                continue
            r.pop("acts", None)
            r["_inst"] = inst
            out.append({"kind": "bot", "run": run.name, "row": r})
    return out


def _ep_name(ep: dict) -> str:
    if ep["kind"] == "human":
        s = ep["seg"]
        return f"{Path(s['session']).name}_a{s['attempt']}_{s['kind']}"
    return f"{ep['run']}_i{ep['row']['_inst']}_ep{ep['row']['episode']}"


_RP: dict = {}


def _replay_policy(crest: str, threads: int, clash: str):
    if crest in _RP:
        return _RP[crest]
    import dataclasses
    from ssbot.tools.forum_layer_audit import Variants
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy
    pol = ForumPlannerPolicy(threads=threads, crest=crest, clash=clash)
    pol.warmup()
    step0 = pol.sc.step

    def step(*args, **kw):
        r = step0(*args, **kw)
        pol.sc.pq = None
        return r._replace(mask=None, outcome=None) if hasattr(r, "_replace") else \
            dataclasses.replace(r, mask=None, outcome=None)
    pol.sc.step = step
    vs = Variants(pol.fc, ("m0",))
    _RP[crest] = (pol, {"wrapped": False}, vs)
    return _RP[crest]


def replay_episode(job: dict) -> dict:
    from ssbot.knowledge import kinematics as kin
    from ssbot.knowledge.kinematics import F_INVULN
    from ssbot.tools.forum_human_score import _hind, _wrap, clear_latches, frame_info, load_segment
    from ssbot.tools.forum_hit_forensics import FramePolys, _mask_of
    from ssbot.tools.forum_layer_audit import classify
    from ssbot.train.encounters import ENCOUNTERS
    ep = job["ep"]
    t0 = time.perf_counter()
    if ep["kind"] == "human":
        seg = ep["seg"]
        crest = seg["crest"] if seg["crest"] in ("Wanderer", "Reaper") else "Reaper"
        terrain, states = load_segment(seg)
        unit = "Forum"
    else:
        from ssbot.record.recorder import RecordingReader
        row = ep["row"]
        rd = RecordingReader(row["recording"])
        terrain = None
        for _, m in rd.terrain():
            if (m.get("scene_raw") or m.get("scene")) in ("Hang_04", "Hang_04_boss"):
                terrain = m
        states = list(rd.states(row["f_wake"], row["f_end"]))
        crest = "Wanderer" if ENCOUNTERS[row["unit"]].savestate == "fo_W" else "Reaper"
        unit = row["unit"]
    if job.get("limit_s"):
        states = states[:int(job["limit_s"] * 60)]
    pol, cap, vs = _replay_policy(crest, job["threads"], job["clash"])
    zones = Zones(Path(job["zones"]))
    pol.terrain_msg = terrain
    pol.reset(random.Random(0), ENCOUNTERS[unit])
    _wrap(pol, cap)
    pl = pol.planner
    pl.debug = True
    pl.fcfg.deadline_ms = math.inf
    pl.fcfg.esc_deadline_ms = math.inf
    pl.fcfg.clash_deadline_ms = math.inf
    human = ep["kind"] == "human"
    fp = FramePolys(states) if human else None
    fi = frame_info(states) if human else None
    idle, wi, errors = [], [], []
    maps: dict = {}
    for i, s in enumerate(states):
        nxt = states[i + 1] if i + 1 < len(states) else None
        if nxt is not None:
            pol.sent[int(nxt["f"])] = _mask_of(nxt) if not human else int(nxt["act"]["mask"])
        if human:
            clear_latches(pl)
        pol.act(s, None)
        if i < 3 or i % job["every"]:
            continue
        li = pl.last_info or {}
        dbg = li.get("dbg")
        res = pol.planner_last
        if dbg is None or res is None or not pol.forecasts or pol.forecasts[-1][0] != int(s["f"]):
            continue
        fcast = pol.forecasts[-1][1]
        try:
            groups = classify(fcast)
            hero = (s.get("hero") or {}).get("pos")
            if i % job["every_idle"] == 0:
                for r in idle_maps(pol, fcast, vs, groups, hero):
                    mp = r.pop("_maps")
                    ins = r.pop("_inside")
                    acc = maps.setdefault(r["tk"], {"n": 0, "inside": np.zeros(ins.shape, np.int32),
                                                    **{c: np.zeros(v.shape, np.int32) for c, v in mp.items()}})
                    acc["n"] += 1
                    acc["inside"] += ins
                    for c, v in mp.items():
                        acc[c] += v
                    r["i"] = i
                    idle.append(r)
            keys_row, kinfo = None, None
            if human and cap.get("args") is not None:
                _, start, _, _, _, _, _ = cap["args"]
                T1 = dbg["box"].shape[1]
                if i + T1 <= len(states):
                    pm = np.zeros(T1 - 1, np.int64)
                    seg_m = fi["mask"][i + 1:i + T1]
                    pm[:len(seg_m)] = seg_m
                    rk = kin.rollout(start, pm[None], pl.params, pl.terrain, threads=pl.cfg.threads)
                    keys_row = (rk.box[0], rk.flags[0], rk.mode[0])
                    pb = fi["box"][i:i + T1]
                    pcx, pcy = 0.5 * (pb[:, 0] + pb[:, 2]), 0.5 * (pb[:, 1] + pb[:, 3])
                    kc = 0.5 * (rk.box[0, :, :2] + rk.box[0, :, 2:])
                    d = np.hypot(kc[1:19, 0] - pcx[1:19], kc[1:19, 1] - pcy[1:19])
                    kinfo = [round(float(np.nanmean(d)), 3),
                             _hind(fp, rk.box[0], (rk.flags[0] & F_INVULN) != 0, int(s["f"]))]
            w = whatif(pol, fcast, groups, dbg, zones, keys_row)
            w.update({"i": i, "forced": bool(res.forced_risk), "n_safe": int(res.n_safe),
                      "wave": (s.get("room") or {}).get("battles") and next(
                          (b.get("wave") for b in s["room"]["battles"] if b.get("name") == "Battle Scene"), None)})
            if kinfo is not None:
                w["kerr18"], w["khind"] = kinfo
            wi.append(w)
        except Exception:
            import traceback
            errors.append([i, traceback.format_exc()[-1500:]])
    name = _ep_name(ep)
    if maps:
        np.savez_compressed(Path(job["out"]) / f"{name}_maps.npz",
                            **{f"{tk}|{c}": v for tk, d in maps.items() for c, v in d.items() if c != "n"},
                            **{f"{tk}|n": np.array([d["n"]]) for tk, d in maps.items()})
    return {"name": name, "kind": ep["kind"], "crest": crest, "fcfg": pol.stats().get("fcfg"),
            "n_states": len(states), "idle": idle, "whatif": wi, "errors": errors[:10], "n_errors": len(errors),
            "secs": round(time.perf_counter() - t0, 1)}


def _rp_init(threads: int) -> None:
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass
    numba.set_num_threads(threads)


def _rp_safe(job: dict) -> dict:
    try:
        return replay_episode(job)
    except Exception:
        import traceback
        return {"name": _ep_name(job["ep"]), "error": traceback.format_exc()[-3000:]}


def cmd_replay(a) -> int:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    eps = []
    for spec in a.specs:
        e = _episodes(spec, a.demo_cache)
        eps += e[:a.limit] if a.limit else e
    jobs = [{"ep": e, "every": a.every, "every_idle": a.every_idle, "threads": a.threads, "clash": a.clash,
             "zones": a.zones, "out": str(out), "limit_s": a.limit_s}
            for e in eps if not (out / f"{_ep_name(e)}.json").exists()]
    jobs.sort(key=lambda j: -((j["ep"]["seg"]["f1"] - j["ep"]["seg"]["f0"]) if j["ep"]["kind"] == "human" else 0))
    print(f"{len(jobs)} episodes", flush=True)
    t0 = time.perf_counter()

    def write(res):
        p = out / f"{res['name']}.json"
        p.write_text(json.dumps(res, default=str), "utf-8")
        print(f"{p.name} {'ERROR ' + res['error'][-400:] if 'error' in res else ''} {res.get('secs')} s "
              f"({time.perf_counter() - t0:.0f} s)", flush=True)
    if a.workers <= 1:
        _rp_init(a.threads)
        for j in jobs:
            write(_rp_safe(j))
    else:
        with ProcessPoolExecutor(a.workers, initializer=_rp_init, initargs=(a.threads,)) as ex:
            for res in ex.map(_rp_safe, jobs):
                write(res)
    return 0


# ------------------------------------------------------------------------------------------------ summary


def _ascii_map(occ: np.ndarray, inside: np.ndarray, n: int) -> list[str]:
    """Rows (top = highest) of the share of ticks a cell was occupied: '#' >= 50 %, '+' >= 10 %, '.' less, ' '
    outside the arena; 'E' the enemy's column at standing height."""
    out = []
    j0 = int(np.argmin(np.abs(REL_DX)))
    for i in range(occ.shape[0] - 1, -1, -1):
        s = []
        for j in range(occ.shape[1]):
            v = occ[i, j] / max(n, 1)
            ins = inside[i, j] / max(n, 1)
            ch = " " if ins < 0.5 else ("#" if v >= 0.5 else "+" if v >= 0.1 else ".")
            if i == 0 and j == j0 and ch == ".":
                ch = "E"
            s.append(ch)
        out.append("".join(s))
    return out


def summarize_idle(files: list[Path]) -> dict:
    by = defaultdict(list)
    for p in files:
        d = json.loads(p.read_text("utf-8"))
        for r in d.get("idle") or ():
            by[r["tk"]].append(r)
    out = {}
    for tk, rs in sorted(by.items()):
        lone = [r for r in rs if r["others8"] == 0]
        res = {"ticks": len(rs), "lone_ticks": len(lone)}
        for tag, sub in (("all", rs), ("lone", lone)):
            if not sub:
                continue
            row = {}
            for c in ("total",) + IDLE_CATS:
                a = np.array([r[c] for r in sub])          # [n, F, 2]
                row[c] = {"area_mean_u2": [round(float(x), 2) for x in a[:, :, 0].mean(axis=0)],
                          "area_p50_u2": [round(float(x), 2) for x in np.median(a[:, :, 0], axis=0)],
                          "dmax_p50_u": [round(float(x), 2) for x in np.median(a[:, :, 1], axis=0)],
                          "dmax_p90_u": [round(float(x), 2) for x in np.percentile(a[:, :, 1], 90, axis=0)],
                          "share_nonzero": [round(float(x), 3) for x in (a[:, :, 0] > 0).mean(axis=0)]}
            row["only_mean_u2"] = {c: [round(float(x), 2) for x in np.mean([r["only"][c] for r in sub], axis=0)]
                                   for c in IDLE_CATS if c != "margins"}
            row["own_q_vs_total_max_diff_u2"] = round(float(max(abs(np.array(r["own_q"])[:, 0]
                                                                 - np.array(r["total"])[:, 0]).max() for r in sub)), 3)
            row["h_anchor_p50"] = round(float(np.median([r["h_anchor"] for r in sub])), 2)
            res[tag] = row
        out[tk] = res
    return out


def summarize_maps(dirs: list[Path], frames=(0, 2, 5), zones: "Zones | None" = None,
                   anchor_h: dict | None = None) -> dict:
    acc: dict = {}
    for d in dirs:
        for p in sorted(Path(d).glob("*_maps.npz")):
            z = np.load(p)
            for k in z.files:
                tk, c = k.split("|")
                v = z[k]
                cur = acc.setdefault(tk, {})
                cur[c] = cur.get(c, 0) + v
    out = {}
    for tk, d in acc.items():
        n = int(np.asarray(d.get("n", [0])).ravel()[0])
        m = {}
        for c in ("total", "body", "not_started", "margins"):
            if c not in d:
                continue
            m[c] = {f"f{PLAN_F[j]}": _ascii_map(d[c][:, :, j], d["inside"], n) for j in frames}
        out[tk] = {"n": n, "maps": m}
        if zones is not None and n:
            vi = _vs_ics(tk, d, n, zones, (anchor_h or {}).get(tk))
            ics = vi.pop("_ics")
            m["ics"] = {"static": _ascii_map(ics.astype(np.int64) * n, d["inside"], n)}
            out[tk]["vs_ics"] = vi
    return out


def _vs_ics(tk: str, d: dict, n: int, zones: "Zones", a_h: float | None) -> dict:
    """The support's mean occupancy around a lone idle enemy (the maps) against the ICS of every family it could
    start (free on the floor row, at rest in the air above it; the type's median anchor height): the mean area per
    plan frame beyond the body inside / outside the ICS (outside = the false-alarm area) and the ICS's own area
    beyond the body."""
    from ssbot.core.forum import FLOOR_Y, FORUM_TYPES
    from ssbot.knowledge import hitbox_tables as hb
    sp = FORUM_TYPES[tk]
    if a_h is None:
        a_h = 2.0
    rx, ry = hb.HERO_HALF_U
    md = json.loads((FORUM_DIR / "support_margins.json").read_text("utf-8"))
    hull = ((md.get("production_tubes") or {}).get("body_hull") or {}).get(tk) or (-0.5, -0.5, 0.5, 0.5)
    DX, H = np.meshgrid(REL_DX, REL_H)
    dy = (FLOOR_Y + hb.HERO_HALF_U[1] + H) - (FLOOR_Y + a_h)
    body = (np.abs(DX) <= max(abs(hull[0]), hull[2]) + rx) & (dy >= hull[1] - ry) & (dy <= hull[3] + ry)
    lock = np.where(H < 0.25, 0, 3)
    ins = d["inside"] / n >= 0.5
    cell = IDLE_U * IDLE_U
    tot = d["total"]
    res = {"a_h": round(a_h, 2)}
    # the Clapper's casts: their templates hold the runes of earlier casts still out (the hazard layer's)
    for tag, skip in (("", frozenset()), ("_no_runes", RUNE_LEFTOVERS)):
        if tag and not (set(zones.fams.get(tk, {})) & skip):
            continue
        ics = zones.occ(tk, sp.idle_family, sp.entry_family, a_h, DX.ravel(), H.ravel(), lock.ravel(),
                        skip).reshape(DX.shape)
        res["ics_beyond_body_u2" + tag] = round(float((ics & ~body & ins).sum()) * cell, 2)
        res["in_ics_u2" + tag], res["outside_ics_u2" + tag] = [], []
        for j in range(tot.shape[2]):
            occ = tot[:, :, j] / n
            res["in_ics_u2" + tag].append(round(float((occ * (ics & ~body & ins)).sum()) * cell, 2))
            res["outside_ics_u2" + tag].append(round(float((occ * (~ics & ~body & ins)).sum()) * cell, 2))
        if not tag:
            res["_ics"] = ics & ~body & ins
    return res


def summarize_whatif(files: list[Path], close_u: float = 0.35) -> dict:
    out = {}
    for p in files:
        d = json.loads(p.read_text("utf-8"))
        src = "human" if d.get("kind") == "human" else "bot"
        acc = out.setdefault(src, {"ticks": 0, "pl_forced": 0, "fr_now": 0, "fr_l1": 0, "fr_wi": 0,
                                   "keys": 0, "k_now": 0, "k_l1": 0, "k_wi": 0, "k_ics_only": 0,
                                   "k_now_fa": 0, "k_l1_fa": 0, "k_wi_fa": 0, "k_hit": 0, "k_now_miss": 0,
                                   "k_l1_miss": 0, "k_wi_miss": 0, "rows": 0, "rows_safe_now": 0,
                                   "rows_safe_l1": 0, "rows_safe_wi": 0, "by_wave": {}})
        for w in d.get("whatif") or ():
            if not w["R"]:
                continue
            acc["ticks"] += 1
            acc["pl_forced"] += int(w["forced"])
            acc["fr_now"] += int(w["safe_now"] == 0)
            acc["fr_l1"] += int(w["safe_l1"] == 0)
            acc["fr_wi"] += int(w["safe_wi"] == 0)
            acc["rows"] += w["R"]
            for k in ("now", "l1", "wi"):
                acc[f"rows_safe_{k}"] += w[f"safe_{k}"]
            bw = acc["by_wave"].setdefault(str(w.get("wave")), [0, 0, 0, 0, 0])
            bw[0] += 1
            bw[1] += int(w["forced"])
            bw[2] += int(w["safe_now"] == 0)
            bw[3] += int(w["safe_l1"] == 0)
            bw[4] += int(w["safe_wi"] == 0)
            if "keys" in w and w.get("kerr18") is not None and w["kerr18"] <= close_u:
                a, b, c, e = w["keys"]
                hit = w["khind"] >= 0
                acc["keys"] += 1
                acc["k_hit"] += int(hit)
                for nm, v in (("now", a), ("l1", b), ("wi", c)):
                    acc[f"k_{nm}"] += int(v)
                    acc[f"k_{nm}_fa"] += int(v and not hit)
                    acc[f"k_{nm}_miss"] += int((not v) and hit)
                acc["k_ics_only"] += int(e)
    for src, a in out.items():
        t = max(a["ticks"], 1)
        k = max(a["keys"], 1)
        a["share"] = {"pl_forced": round(a["pl_forced"] / t, 4), "forced_now": round(a["fr_now"] / t, 4),
                      "forced_l1": round(a["fr_l1"] / t, 4), "forced_wi": round(a["fr_wi"] / t, 4),
                      "rows_safe_now": round(a["rows_safe_now"] / max(a["rows"], 1), 4),
                      "rows_safe_l1": round(a["rows_safe_l1"] / max(a["rows"], 1), 4),
                      "rows_safe_wi": round(a["rows_safe_wi"] / max(a["rows"], 1), 4)}
        if a["keys"]:
            a["share"].update({f"keys_unsafe_{n}": round(a[f"k_{n}"] / k, 4) for n in ("now", "l1", "wi")})
            a["share"].update({f"keys_fa_of_unsafe_{n}": round(a[f"k_{n}_fa"] / max(a[f"k_{n}"], 1), 4)
                               for n in ("now", "l1", "wi")})
            a["share"].update({f"keys_miss_of_safe_{n}": round(a[f"k_{n}_miss"] / max(a["keys"] - a[f"k_{n}"], 1), 4)
                               for n in ("now", "l1", "wi")})
            a["share"]["keys_hit"] = round(a["k_hit"] / k, 4)
            a["share"]["keys_ics_only"] = round(a["k_ics_only"] / k, 4)
    return out


def cmd_summary(a) -> int:
    res = {}
    zones = Zones(Path(a.zones)) if a.zones else None
    for d in a.dirs:
        files = sorted(p for p in Path(d).glob("*.json"))
        idle = summarize_idle(files)
        ah = {tk: v.get("all", {}).get("h_anchor_p50") for tk, v in idle.items()}
        res[Path(d).name] = {"episodes": len(files), "errors": sum(json.loads(p.read_text("utf-8")).get("n_errors", 0)
                                                                  for p in files),
                             "idle": idle, "whatif": summarize_whatif(files),
                             "maps": summarize_maps([Path(d)], zones=zones, anchor_h=ah)}
    Path(a.json).write_text(json.dumps(res, indent=1), "utf-8")
    # the maps as text: per arm, type, layer and plan frame (the enemy's column 'E' at standing height; x from
    # -12 to +12 u, every IDLE_U; rows from standing height up)
    lines = []
    for arm, r in res.items():
        for tk, m in r["maps"].items():
            for c, fr in m["maps"].items():
                for f, rows in fr.items():
                    lines += [f"== {arm} | {tk} | {c} | plan frame {f[1:]} | {m['n']} idle ticks", *rows, ""]
    Path(a.json).with_suffix(".maps.txt").write_text("\n".join(lines), "utf-8")
    print(f"wrote {a.json}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("summary")
    s.add_argument("dirs", nargs="+")
    s.add_argument("--json", required=True)
    s.add_argument("--zones", default=None)
    r = sub.add_parser("replay")
    r.add_argument("specs", nargs="+")
    r.add_argument("--out", required=True)
    r.add_argument("--zones", required=True)
    r.add_argument("--every", type=int, default=6)
    r.add_argument("--every-idle", type=int, default=12)
    r.add_argument("--workers", type=int, default=1)
    r.add_argument("--threads", type=int, default=4)
    r.add_argument("--clash", default="off")
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--limit-s", type=float, default=0.0)
    r.add_argument("--demo-cache", type=Path, default=None)
    z = sub.add_parser("zones")
    z.add_argument("--out", required=True)
    z.add_argument("--lat", type=int, default=LAT_F)
    z.add_argument("--margin", action="store_true")
    z.add_argument("--k-max", type=int, default=600)
    z.add_argument("--threads", type=int, default=4)
    z.add_argument("--only", type=lambda s: [x for x in s.split(",") if x], default=None)
    a = ap.parse_args(argv)
    if a.cmd == "zones":
        return cmd_zones(a)
    if a.cmd == "replay":
        return cmd_replay(a)
    if a.cmd == "summary":
        return cmd_summary(a)
    return 1


if __name__ == "__main__":
    sys.exit(main())
