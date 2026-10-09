"""Idle enemies: the inescapable zone of an attack committed now (task "idle enemies: the inescapable zone", forum.md
§26; the person 2026-10-08). Measurement only: nothing here changes the planner or the forecast.

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
            grid over the arena (GRID_U cells, hero centres from standing height up) at plan frames 1, 6, 12, 18,
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
TURNS = (24, 45, 75)
ACTS = ("none", "jump_full", "jump_short", "dash", "sprint", "jump_airdash", "dash_jump")
FACING_EXCEPT = frozenset({"AT_DEFEND", "AT_LEAVE", "MA_SUMMON"})   # instances' mirror != the hero's side often
RE_ARMS = frozenset({"CB_THROW", "RE_THROW", "CC_CAST"})
PIN_FAMS = frozenset({"RE_THROW"})
PLAN_F = (1, 6, 12, 18, 24, 36)
GRID_U = 0.25
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


def body_mask(t) -> np.ndarray:
    """(ny, nx) the template's cells at the commit (t <= one frame): the body (and anything already out then)."""
    b1 = int(np.rint((1.0 / 60.0 - t.t0) / t.bin_s))
    return np.unpackbits(np.bitwise_or.reduce(t.bits[:max(1, b1 + 1)], axis=0), axis=1, count=t.nx).astype(bool)


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


def pin_zone(px: np.ndarray, py: np.ndarray, disp: np.ndarray, use: np.ndarray, t_rel_f: tuple = (40, 60, 80)
             ) -> np.ndarray:
    """Inescapable start points of an aimed Reed pin (the planner's model, forum.md §23.7): released t_rel_f frames
    after the commit (strikes.json: least 0.667 s, p5 0.667 s = 40 frames), from PIN_SPAWN_U off the Reed (at the
    anchor), PIN_SPEED, aimed at where the hero is PIN_AIM_F frames before the release (+-15 deg), segment of
    2 x PIN_HALF_U grown by the hero hurtbox and PIN_SKIN; a start is inescapable when every trajectory is hit by one
    of the releases' rays (any release: the Reed picks the moment)."""
    from ssbot.combat.forum_planner import PIN_AIM_F, PIN_HALF_U, PIN_SKIN, PIN_SPAWN_U, PIN_SPEED, PIN_SPREAD
    from ssbot.knowledge import hitbox_tables as hb
    hx, hy = hb.HERO_HALF_U[0] + PIN_SKIN, hb.HERO_HALF_U[1] + PIN_SKIN
    K = disp.shape[1]
    seg = np.array([-1.0, -0.5, 0.0, 0.5, 1.0]) * PIN_HALF_U
    dt = 1.0 / 60.0
    out = np.ones(len(px), bool)
    D = disp[use].astype(np.float64)
    for p in range(len(px)):
        sg = 1.0 if px[p] >= 0 else -1.0
        cx = px[p] + sg * D[:, :, 0]
        cy = py[p] + D[:, :, 1]
        hit_any = np.zeros(len(D), bool)
        for kr in t_rel_f:
            if kr >= K:
                continue
            ka = max(kr - PIN_AIM_F, 0)
            ks = np.arange(kr, min(K, kr + 90))
            s = PIN_SPEED * (ks - kr) * dt
            for ang in PIN_SPREAD:
                ax_, ay_ = cx[:, ka], cy[:, ka]
                nrm = np.maximum(np.hypot(ax_, ay_), 1e-6)
                ca, sa = math.cos(ang), math.sin(ang)
                ux, uy = (ax_ * ca - ay_ * sa) / nrm, (ax_ * sa + ay_ * ca) / nrm
                ox, oy = PIN_SPAWN_U * ux, PIN_SPAWN_U * uy
                qx = ox[:, None, None] + ux[:, None, None] * (s[None, :, None] + seg[None, None, :])
                qy = oy[:, None, None] + uy[:, None, None] * (s[None, :, None] + seg[None, None, :])
                hit = ((np.abs(qx - cx[:, ks, None]) <= hx) & (np.abs(qy - cy[:, ks, None]) <= hy)).any(axis=(1, 2))
                hit_any |= hit
        out[p] = bool(hit_any.all())
    return out


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


def family_zone(t, hq3: tuple, face: float, fam: str, libs: dict, params, lat: int) -> dict:
    """One family's zones (module docstring): per lock state the ub zone on the floor row (ground locks) or the
    air grid, beyond-the-body extents, and the lb zone."""
    act = t.active()
    res = {"active_s": None if act is None else [round(act[0], 3), round(act[1], 3)],
           "facing": round(face, 3), "anchor_h": [round(x, 2) for x in hq3], "locks": {}}
    if act is None:
        return res
    bm = body_mask(t)
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
            pts, inesc = [], []
            for h in hs:
                disp, _, use = libs[(lock, h)]
                step = AIR_DX_STEP if lock == "air" else DX_STEP
                xx = xs if lock != "air" else np.round(np.arange(xs[0], xs[-1] + 1e-9, step), 3)
                yy = np.full(len(xx), dy0 + h)
                z, _ = zone_ub(t, xx, yy, disp, use)
                if both:
                    zm, _ = zone_ub(t, -xx, yy, disp, use)
                    z = z | zm
                pts.append(np.stack([xx, yy], axis=1))
                inesc.append(z)
            P = np.concatenate(pts)
            Z = np.concatenate(inesc)
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
            rec = {"anchor_h": round(hq, 2), "n_beyond": int(bw.sum()),
                   ("area_u2" if lock == "air" else "length_u"): round(area, 2),
                   "max_dist_u": round(float(d.max()), 2) if len(d) else 0.0,
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
    if a.only:
        tpl = {k: v for k, v in tpl.items() if k[1] in a.only}
    for (tk, fam), (t, hq3, face, m) in sorted(tpl.items()):
        t1 = time.perf_counter()
        r = family_zone(t, hq3, face, fam, libs, params, a.lat)
        r["margin_u"] = m
        st = strike_table().get((tk, fam))
        r["strike_min_p5_s"] = None if st is None else [round(st[0], 3), round(st[1], 3)]
        r["re_arm"] = fam in RE_ARMS
        if fam in PIN_FAMS:
            # the aimed pin (the planner's model) instead of the template's every-direction union
            hq = hq3[1]
            dy0 = _ground_dy(hq)
            pr = {}
            for lock in ("free", "attack", "dash"):
                disp, _, use = libs[(lock, 0.0)]
                xx = np.round(np.arange(-16.0, 16.0 + 1e-9, 0.25), 3)
                z = pin_zone(xx, np.full(len(xx), dy0), disp, use)
                pr[lock] = {"n": int(z.sum()), "runs": _runs(xx, z, 0.25)[:8]}
            r["aimed_pin"] = pr
        # the floor row as text (free lock, median anchor height)
        disp, _, use = libs[("free", 0.0)]
        dy0 = _ground_dy(hq3[1])
        xs = np.round(np.arange(-20.0, 20.0 + 1e-9, DX_STEP), 3)
        z, _ = zone_ub(t, xs, np.full(len(xs), dy0), disp, use)
        bm = body_mask(t)
        ix = np.floor(xs / t.cell).astype(np.int64) - t.ix0
        iy = int(math.floor(dy0 / t.cell)) - t.iy0
        body = np.zeros(len(xs), bool)
        ok = (ix >= 0) & (ix < t.nx) & (0 <= iy < t.ny)
        body[ok] = bm[iy, ix[ok]]
        r["row_free"] = ascii_row(xs, z & ~body, body)
        res["families"][f"{tk}/{fam}"] = r
        lk = r["locks"]
        print(f"{tk:22s} {fam:13s} act {r['active_s']} beyond-body ub: " + ", ".join(
            f"{L} {max((x['max_dist_u'] for x in lk[L]), default=0):.2f}u" for L in LOCKS)
            + f" lb {max((x['max_dist_u'] for x in r['lb']), default=0):.2f}u ({time.perf_counter() - t1:.1f} s)",
            flush=True)
    p = out / f"zones_lat{a.lat}{'_margin' if a.margin else ''}.json"
    p.write_text(json.dumps(res, indent=1), "utf-8")
    print(f"wrote {p} ({time.perf_counter() - t0:.0f} s)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
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
    return 1


if __name__ == "__main__":
    sys.exit(main())
