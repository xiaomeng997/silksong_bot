"""Numba build of the hero model's frame loop (ssbot.knowledge.kinematics; DESIGN §3.5.4: <= 512 candidates x 48
frames, p99 <= 3 ms per planner tick).

The NumPy functions in kinematics.py (_fixed_step, _apply_events, _update, _simulate) are the reference: array code
over lanes, readable next to the decompiled HeroController. This module is the same rules written per lane as scalar
code, which numba compiles to a tight loop (no temporaries, branches instead of np.where). Statement order follows the
reference line by line, including which values are read before and after an update, so both give the same numbers;
tests/test_kinematics.py checks that on synthetic and logged inputs. Change both together.

Every function is @njit(cache=True): the first import in a fresh environment compiles for a few seconds and writes
the cache next to this file; later processes load it.
"""
from __future__ import annotations

import math

import numpy as np
from numba import njit, prange

from ssbot.knowledge.kinematics import (
    ALPHA, AQ, ATK_CD, ATK_T, ATTACKING, AIRHANG, B_ATTACK, B_BIND, B_DOWN, B_JUMP, B_LEFT, B_QUICKCAST, B_RIGHT,
    B_UP, BOUNCE, DS_HS, DS_REC, EPS, EV_CATCH, EV_HURT_L, EV_HURT_R, EV_LOCK, EV_POGO, EV_RECOIL_DOWN, EV_RECOIL_L,
    EV_RECOIL_R, EV_SILK, EV_UNLOCK, F_ATTACKING, F_GROUND, F_INVULN, F_JUMPING, F_NO_INPUT, F_RECOIL, F_RELINQ, FACE,
    GROUND, GS, GTOL, HVX, HVY, INV_T, JDSTEPS, JHELD, JQ, JSTEPS, JUMPING, LEDGE, M_BIND, M_CAST, M_DS_ANTIC,
    M_DS_SPIKE, M_HURT_FREEZE, M_HURT_RECOIL, M_LOCKED, M_NORMAL, MODE, MODE_N, MODE_T, MOVE, P_AH_ACC, P_AH_G,
    P_AQ, P_ATK_CD, P_ATK_DUR, P_ATK_REC, P_BIND_DECAY, P_BIND_ENDVY, P_BIND_SILK, P_BIND_T, P_BIND_VYCAP,
    P_BIND_VYDOWN, P_BOUNCE, P_CAST_ANTIC, P_CAST_CATCH, P_CAST_CDECAY, P_CAST_CSPEED, P_CAST_DECAY, P_CAST_DECAY_G,
    P_CAST_SILK, P_CAST_THROW, P_CAST_VYCAP, P_DS_ANTIC, P_DS_DECEL, P_DS_ENDVY, P_DS_LREC, P_DS_REC, P_DS_SPEED,
    P_DS_TIME, P_DS_VYMAX, P_DS_VYMIN, P_FDT, P_FOOT, P_G, P_HEAD, P_HURT_RAMP, P_HURT_SKIP, P_HURT_T, P_HURT_V,
    P_HURT_VY, P_HURT_WAIT, P_HW, P_INV_T, P_JQ, P_JSTEPS, P_JSTEPS_MIN, P_JUMP, P_LEDGE, P_LIFT, P_LOCK_DECAY,
    P_MAXFALL, P_POGO_J, P_POGO_JD, P_QQ, P_RDOWN_HALF, P_REL, P_RSTEPS, P_RUN, P_RV, P_SILK_MAX, P_SKIN, P_SLOP_HI,
    P_SLOP_LO, PHASE, PREV, PX, PY, QQ, QX, QY, RDIR, RSTEPS, SILK, SX, SY, TOL, TOUCH, TS, VX, VY)


@njit(cache=True, inline="always")
def f32(a):
    return np.float64(np.float32(a))


@njit(cache=True, inline="always")
def ge32(a, c):
    return np.float32(a) >= np.float32(c)


@njit(cache=True, inline="always")
def gt32(a, c):
    return np.float32(a) > np.float32(c)


@njit(cache=True, inline="always")
def relinq(m):
    return m == M_DS_ANTIC or m == M_DS_SPIKE or m == M_CAST or m == M_BIND or m == M_LOCKED


@njit(cache=True, inline="always")
def noinput(m):
    return m == M_HURT_FREEZE or m == M_HURT_RECOIL


# ---- collision ------------------------------------------------------------------------------------------------
# The terrain reaches the kernel as one packed float64 array TT (Terrain2D.packed(): segments plus an x-bucket index,
# each bucket listing the floors / ceilings whose x extent and the walls whose x falls in it); the queries visit only
# the buckets their tests can pass in, and take scalars plus TT so the per-step calls carry one array, not seven.
# TT header: nh, nv, buckets, x0, 1 / width, bucket starts (h), ids (h), bucket starts (v), ids (v), vseg offset;
# hseg rows (y, x0, x1) from TT_H, vseg rows (x, y0, y1) from TT[9].
TT_H = 10


@njit(cache=True, inline="always")
def _buckets(lo, hi, TT):
    """Bucket range [b0, b1] covering x in [lo, hi] (b0 > b1: none)."""
    nb = np.int64(TT[2])
    if nb == 0:
        return np.int64(0), np.int64(-1)
    b0 = np.int64(math.floor((lo - TT[3]) * TT[4]))
    b1 = np.int64(math.floor((hi - TT[3]) * TT[4]))
    if b1 < 0 or b0 >= nb:
        return np.int64(0), np.int64(-1)
    return max(b0, np.int64(0)), min(b1, nb - 1)


@njit(cache=True, inline="always")
def move_x(px, py, dx, hw, skin, foot, head, TT):
    nx = px + dx
    if TT[1] == 0:
        return nx, False
    bot = py - foot
    top = py + head
    rx = np.inf
    lx = -np.inf
    hit = False
    reach = hw + skin + TOL + 0.01
    b0, b1 = _buckets(min(px, nx) - reach, max(px, nx) + reach, TT)
    st = np.int64(TT[7])
    ids = np.int64(TT[8])
    ov = np.int64(TT[9])
    for b in range(b0, b1 + 1):
        for q in range(np.int64(TT[st + b]), np.int64(TT[st + b + 1])):
            j = ov + 3 * np.int64(TT[ids + q])
            if not (top > TT[j + 1] + EPS and bot < TT[j + 2] - EPS):
                continue
            s = TT[j]
            if dx > 0:
                lim = s - skin - hw
                if px <= lim + TOL and nx > lim:
                    hit = True
                    if lim < rx:
                        rx = lim
            elif dx < 0:
                lim = s + skin + hw
                if px >= lim - TOL and nx < lim:
                    hit = True
                    if lim > lx:
                        lx = lim
    return max(min(nx, rx), lx), hit


@njit(cache=True, inline="always")
def move_y(px, py, dy, hw, skin, foot, head, slop_lo, slop_hi, TT):
    ny = py + dy
    if TT[0] == 0:
        return ny, False, False, False
    dn = -np.inf
    up = np.inf
    landed = False
    touch = False
    bumped = False
    b0, b1 = _buckets(px - hw - 0.01, px + hw + 0.01, TT)
    st = np.int64(TT[5])
    ids = np.int64(TT[6])
    for b in range(b0, b1 + 1):
        for q in range(np.int64(TT[st + b]), np.int64(TT[st + b + 1])):
            j = TT_H + 3 * np.int64(TT[ids + q])
            if not ((px + hw) > TT[j + 1] + EPS and (px - hw) < TT[j + 2] - EPS):
                continue
            s = TT[j]
            if dy < 0:
                lim = s + skin + foot
                if py >= lim - TOL and ny < lim + slop_hi:
                    if ny < lim - slop_lo:
                        landed = True
                        if lim > dn:
                            dn = lim
                    else:
                        touch = True
            elif dy > 0:
                lim = s - skin - head
                if py <= lim + TOL and ny > lim:
                    bumped = True
                    if lim < up:
                        up = lim
    return min(max(ny, dn), up), landed, touch and not landed, bumped


@njit(cache=True, inline="always")
def on_ground(px, py, hw, skin, foot, TT):
    if TT[0] == 0:
        return False
    b0, b1 = _buckets(px - hw - 0.01, px + hw + 0.01, TT)
    st = np.int64(TT[5])
    ids = np.int64(TT[6])
    for b in range(b0, b1 + 1):
        for q in range(np.int64(TT[st + b]), np.int64(TT[st + b + 1])):
            j = TT_H + 3 * np.int64(TT[ids + q])
            if (px + hw) > TT[j + 1] + EPS and (px - hw) < TT[j + 2] - EPS:
                gap = (py - foot) - (TT[j] + skin)
                if gap >= -GTOL and gap <= GTOL:
                    return True
    return False


# ---- one physics step, contact events, one Update ---------------------------------------------------------------

@njit(cache=True)
def fixed_step(x, P, TT):
    fdt = P[P_FDT]
    hw = P[P_HW]
    skin = P[P_SKIN]
    foot = P[P_FOOT]
    head = P[P_HEAD]
    x[QX] = x[PX]
    x[QY] = x[PY]
    mode = x[MODE]
    normal = mode == M_NORMAL
    rlq = relinq(mode)
    noinp = noinput(mode)

    if x[RDIR] != 0:
        if x[RSTEPS] <= 0:
            x[RDIR] = 0.0
        else:
            x[RSTEPS] = x[RSTEPS] - 1

    mv = 0.0 if (x[DS_REC] >= 0 and x[GROUND] > 0) else x[MOVE]
    vx = mv * P[P_RUN] if normal else x[VX]
    can_turn = normal and not (x[ATTACKING] > 0 and x[ATK_T] < P[P_ATK_REC])
    sg = 1.0 if mv > 0 else (-1.0 if mv < 0 else 0.0)
    if can_turn and mv != 0 and sg != x[FACE]:
        x[FACE] = sg
        x[ATTACKING] = 0.0
    rv = P[P_RV]
    if normal and x[RDIR] < 0:
        vx = -rv if vx > 0 else vx - rv
    elif normal and x[RDIR] > 0:
        vx = rv if vx < 0 else vx + rv
    vy = x[VY]
    jmp = normal and x[JUMPING] > 0
    rise = jmp and x[JSTEPS] <= P[P_JSTEPS]
    if rise:
        vy = P[P_JUMP]
        x[JSTEPS] = x[JSTEPS] + 1
        x[JDSTEPS] = x[JDSTEPS] + 1
    elif jmp:
        x[JSTEPS] = 0.0
        x[JUMPING] = 0.0
    if x[BOUNCE] >= 0:
        x[BOUNCE] = x[BOUNCE] + 1 if x[BOUNCE] <= P[P_BOUNCE] else -1.0

    if mode == M_DS_SPIKE:
        if gt32(x[MODE_T], P[P_DS_TIME]):
            vy = P[P_DS_ENDVY]
            x[GS] = 1.0
            x[DS_REC] = 0.0
            x[MODE] = M_NORMAL
        else:
            vx = x[DS_HS]
            vy = -P[P_DS_SPEED]
            x[MODE_T] = f32(x[MODE_T] + np.float32(fdt))
    mode = x[MODE]
    rlq = relinq(mode)

    if mode == M_DS_ANTIC and not ge32(x[MODE_T], P[P_DS_ANTIC]):
        vx = vx * P[P_DS_DECEL]
        vy = vy * P[P_DS_DECEL]
    if mode == M_HURT_FREEZE:
        vx = 0.0
        vy = 0.0
    elif mode == M_HURT_RECOIL:
        vx = x[HVX]
        vy = x[HVY]
    air = x[GROUND] <= 0
    if mode == M_CAST:
        ph = x[PHASE]
        if ph == 0:
            vx = vx * (P[P_CAST_DECAY] if air else P[P_CAST_DECAY_G])
            vy = vy * P[P_CAST_DECAY] if air else 0.0
        elif ph == 1:
            vx = 0.0
            vy = 0.0
        elif ph == 2:
            vx = vx * P[P_CAST_CDECAY]
    elif mode == M_BIND:
        vx = vx * P[P_BIND_DECAY] if air else 0.0
        vy = vy * P[P_BIND_DECAY] if air else 0.0
    elif mode == M_LOCKED:
        vx = vx * P[P_LOCK_DECAY]

    if not rlq and vy < -P[P_MAXFALL]:
        vy = -P[P_MAXFALL]
    if x[JQ] >= 0:
        x[JQ] = x[JQ] + 1
    if x[AQ] >= 0:
        x[AQ] = x[AQ] + 1
    if x[QQ] >= 0:
        x[QQ] = x[QQ] + 1
    ground = x[GROUND] > 0
    hang = x[AIRHANG] <= 0 and not ground and vy < 0
    if hang and not rlq and not noinp:
        x[GS] = P[P_AH_G]
    if hang:
        x[AIRHANG] = 1.0
    elif ground:
        x[AIRHANG] = 0.0
    ctl = not rlq and not noinp
    gs = x[GS]
    if ctl and gs < 1.0:
        gs = gs + P[P_AH_ACC] * fdt
    if ctl and gs < 1.0 and x[JHELD] <= 0:
        gs = 1.0
    x[GS] = min(gs, 1.0)
    x[LEDGE] = max(x[LEDGE] - 1, 0.0)

    vy = vy - P[P_G] * x[GS] * fdt
    pend = x[TOUCH] > 0
    # (the reference always computes it; it only matters in these cases)
    under = (pend or x[GROUND] > 0 or x[MODE] == M_DS_SPIKE) and on_ground(x[PX], x[PY], hw, skin, foot, TT)
    resolve = pend and vy <= 0 and under
    if resolve or (x[GROUND] > 0 and under and vy < 0):
        vy = 0.0
    nx, hitx = move_x(x[PX], x[PY], vx * fdt, hw, skin, foot, head, TT)
    if hitx:
        vx = 0.0
    ny, landed, touched, bumped = move_y(nx, x[PY], vy * fdt, hw, skin, foot, head, P[P_SLOP_LO], P[P_SLOP_HI],
                                         TT)
    if landed or bumped:
        vy = 0.0
    x[PX] = nx
    x[PY] = ny
    x[SX] = nx
    x[SY] = ny
    x[VX] = vx
    x[VY] = vy
    x[TOUCH] = 1.0 if touched else 0.0
    was = x[GROUND] > 0
    stay = was and vy <= 0 and on_ground(nx, ny, hw, skin, foot, TT)
    lands = (landed or resolve) and not noinp
    now = stay or lands
    x[GROUND] = 1.0 if now else 0.0
    if lands:
        x[JUMPING] = 0.0
        x[JSTEPS] = 0.0
    if was and not now and x[JUMPING] <= 0 and x[MODE] == M_NORMAL:
        x[LEDGE] = P[P_LEDGE]
    land_sp = (landed or resolve or (under and now)) and x[MODE] == M_DS_SPIKE
    if land_sp:
        x[MODE] = M_NORMAL
        x[DS_REC] = 0.0
        x[GS] = 1.0
        x[VY] = P[P_DS_ENDVY]
    if (lands or land_sp) and not was and x[MOVE] == 0:
        x[DS_REC] = -1.0


@njit(cache=True, inline="always")
def apply_events(x, ev, P):
    mode = x[MODE]
    rlq = relinq(mode)
    rec_ok = x[RDIR] == 0 and not rlq and not noinput(mode)
    if rec_ok and (ev & EV_RECOIL_L) != 0:
        x[RDIR] = -1.0
        x[RSTEPS] = P[P_RSTEPS]
        x[VX] = -1.0 * P[P_RV]
    if rec_ok and (ev & EV_RECOIL_R) != 0:
        x[RDIR] = 1.0
        x[RSTEPS] = P[P_RSTEPS]
        x[VX] = 1.0 * P[P_RV]
    if (ev & EV_RECOIL_DOWN) != 0 and not rlq:
        x[JUMPING] = 0.0
        x[JSTEPS] = 0.0
        if x[VY] > 0:
            x[VY] = x[VY] * 0.5 if P[P_RDOWN_HALF] > 0 else 0.0
    if (ev & EV_POGO) != 0:
        x[MODE] = M_NORMAL
        x[JUMPING] = 1.0
        x[JSTEPS] = P[P_POGO_J]
        x[JDSTEPS] = P[P_POGO_JD]
        x[BOUNCE] = 0.0
        x[DS_REC] = 0.0
        x[GS] = 1.0
        x[VY] = P[P_DS_ENDVY]
        if x[GROUND] > 0:
            x[PY] = x[PY] + P[P_LIFT]
        x[GROUND] = 0.0
        x[JQ] = -1.0
    for b in range(2):
        bit = EV_HURT_L if b == 0 else EV_HURT_R
        side = -1.0 if b == 0 else 1.0
        if (ev & bit) != 0:
            x[MODE] = M_HURT_FREEZE
            x[MODE_T] = 0.0
            x[MODE_N] = 0.0
            x[HVX] = -side * P[P_HURT_V]
            x[HVY] = P[P_HURT_V] * P[P_HURT_VY]
            x[FACE] = side
            x[VX] = 0.0
            x[VY] = 0.0
            x[GS] = 0.0
            x[RDIR] = 0.0
            x[ATTACKING] = 0.0
            x[JUMPING] = 0.0
            x[GROUND] = 0.0
            x[INV_T] = P[P_INV_T]
            x[PHASE] = 0.0
            x[TS] = 0.0
    if (ev & EV_SILK) != 0:
        x[SILK] = min(x[SILK] + 1, P[P_SILK_MAX])
    if (ev & EV_LOCK) != 0:
        x[MODE] = M_LOCKED
        x[MODE_T] = 0.0
    if (ev & EV_UNLOCK) != 0 and x[MODE] == M_LOCKED:
        x[MODE] = M_NORMAL


@njit(cache=True, inline="always")
def hero_jump(x, P):
    x[JUMPING] = 1.0
    x[JSTEPS] = 0.0
    x[JDSTEPS] = 0.0
    x[JQ] = -1.0
    x[DS_REC] = -1.0
    if x[GROUND] > 0:
        if x[VY] < 0:
            x[VY] = 0.0
        x[PY] = x[PY] + P[P_LIFT]
    x[GROUND] = 0.0
    x[LEDGE] = 0.0
    if x[ATTACKING] > 0 and x[ATK_T] >= P[P_ATK_REC]:
        x[ATTACKING] = 0.0


@njit(cache=True, inline="always")
def do_attack(x, mask, P):
    want = 1.0 if (mask & B_RIGHT) != 0 else (-1.0 if (mask & B_LEFT) != 0 else 0.0)
    if want != 0:
        x[FACE] = want
    down = (mask & B_UP) == 0 and (mask & B_DOWN) != 0 and x[GROUND] <= 0
    if not down:
        x[ATTACKING] = 1.0
    x[ATK_T] = 0.0
    x[ATK_CD] = P[P_ATK_CD]
    x[AQ] = -1.0
    if down:
        x[MODE] = M_DS_ANTIC
        x[MODE_T] = 0.0
        x[DS_HS] = x[FACE] * P[P_DS_SPEED]
        x[VY] = min(max(x[VY], P[P_DS_VYMIN]), P[P_DS_VYMAX])
        x[GS] = 0.0
        x[JUMPING] = 0.0
        x[JSTEPS] = 0.0


@njit(cache=True)
def update(x, mask, ev, dt, udt, P):
    mode = x[MODE]
    mode0 = mode
    prev = np.int64(x[PREV])
    pressed = mask & ~prev
    normal = mode == M_NORMAL
    accept = normal or noinput(mode)

    move = (1.0 if (mask & B_RIGHT) != 0 else 0.0) - (1.0 if (mask & B_LEFT) != 0 else 0.0)
    jheld = (mask & B_JUMP) != 0
    if accept:
        x[MOVE] = move
        x[JHELD] = 1.0 if jheld else 0.0
        if not jheld:
            if x[VY] > 0 and x[JDSTEPS] >= P[P_JSTEPS_MIN]:
                x[VY] = x[VY] * P[P_REL]
                x[JUMPING] = 0.0
                x[JSTEPS] = 0.0
            x[JQ] = -1.0
        if (mask & B_ATTACK) == 0:
            x[AQ] = -1.0
        if (mask & B_QUICKCAST) == 0:
            x[QQ] = -1.0

    if mode == M_HURT_RECOIL:
        if ge32(x[MODE_T], P[P_HURT_T]):
            x[MODE] = M_NORMAL
            x[VX] = 0.0
            x[VY] = 0.0
            x[GS] = 1.0
        else:
            x[MODE_T] = f32(x[MODE_T] + dt)
    if normal and x[ATTACKING] > 0:
        x[ATK_T] = f32(x[ATK_T] + dt)
        if ge32(x[ATK_T], P[P_ATK_DUR]):
            x[ATTACKING] = 0.0

    normal = x[MODE] == M_NORMAL
    ground = x[GROUND] > 0
    can_jump = normal and x[JUMPING] <= 0 and x[BOUNCE] < 0 and x[DS_REC] < 0 and (ground or x[LEDGE] > 0)
    jp = (pressed & B_JUMP) != 0
    if jp and not can_jump:
        x[JQ] = 0.0
    if jp and can_jump:
        hero_jump(x, P)
    downish = (mask & B_DOWN) != 0 and (mask & B_UP) == 0
    can_down = x[BOUNCE] < 0 and x[DS_REC] < 0
    can_attack = normal and x[ATTACKING] <= 0 and x[ATK_CD] <= 0 and (not downish or can_down)
    ap = (pressed & B_ATTACK) != 0
    if ap and not can_attack:
        x[AQ] = 0.0
    if ap and can_attack:
        do_attack(x, mask, P)
    mode = x[MODE]
    normal = mode == M_NORMAL
    qp = (pressed & B_QUICKCAST) != 0
    queued = (mask & B_QUICKCAST) != 0 and x[QQ] >= 0 and x[QQ] <= P[P_QQ]
    spike = mode == M_DS_SPIKE
    able = (normal and x[ATTACKING] <= 0) or spike
    cast = able and (qp or queued) and x[SILK] >= P[P_CAST_SILK]
    if qp and not cast:
        x[QQ] = 0.0
    elif cast:
        x[QQ] = -1.0
    if cast:
        if spike:
            x[VX] = 0.0
            x[VY] = P[P_DS_ENDVY]
            x[GROUND] = 0.0
        want = 1.0 if (mask & B_RIGHT) != 0 else (-1.0 if (mask & B_LEFT) != 0 else 0.0)
        if want != 0:
            x[FACE] = want
        x[MODE] = M_CAST
        x[MODE_T] = 0.0
        x[PHASE] = 0.0
        x[SILK] = x[SILK] - P[P_CAST_SILK]
        x[GS] = 0.0
        x[JUMPING] = 0.0
        cair = x[GROUND] <= 0
        x[VX] = x[VX] * (P[P_CAST_DECAY] if cair else P[P_CAST_DECAY_G])
        x[VY] = min(max(x[VY], -P[P_CAST_VYCAP]), P[P_CAST_VYCAP]) * P[P_CAST_DECAY] if cair else 0.0
    normal = x[MODE] == M_NORMAL
    ground = x[GROUND] > 0
    can_jump = normal and x[JUMPING] <= 0 and x[BOUNCE] < 0 and x[DS_REC] < 0 and (ground or x[LEDGE] > 0)
    if normal and jheld and x[JQ] >= 0 and x[JQ] <= P[P_JQ] and can_jump:
        hero_jump(x, P)
    can_attack = normal and x[ATTACKING] <= 0 and x[ATK_CD] <= 0 and (not downish or can_down)
    if normal and (mask & B_ATTACK) != 0 and x[AQ] >= 0 and x[AQ] <= P[P_AQ] and can_attack:
        do_attack(x, mask, P)
    normal = x[MODE] == M_NORMAL
    if normal and (pressed & B_BIND) != 0 and x[SILK] >= P[P_BIND_SILK]:
        x[MODE] = M_BIND
        x[MODE_T] = 0.0
        x[SILK] = x[SILK] - P[P_BIND_SILK]
        x[GS] = 0.0
        x[JUMPING] = 0.0
        x[ATTACKING] = 0.0
        if x[GROUND] <= 0:
            x[VX] = x[VX] * P[P_BIND_DECAY]
            x[VY] = min(max(x[VY], -P[P_BIND_VYDOWN]), P[P_BIND_VYCAP]) * P[P_BIND_DECAY]
        else:
            x[VX] = 0.0
            x[VY] = 0.0

    # timers
    if x[ATK_CD] > 0:
        x[ATK_CD] = f32(x[ATK_CD] - dt)
    if x[DS_REC] >= 0:
        lim = P[P_DS_LREC] if x[GROUND] > 0 else P[P_DS_REC]
        if ge32(x[DS_REC], lim):
            x[DS_REC] = -1.0
        else:
            x[DS_REC] = f32(x[DS_REC] + dt)
    mode = x[MODE]
    if mode == M_DS_ANTIC:
        if ge32(x[MODE_T], P[P_DS_ANTIC]):
            x[MODE] = M_DS_SPIKE
            x[MODE_T] = 0.0
        else:
            x[MODE_T] = f32(x[MODE_T] + dt)
    if mode == M_HURT_FREEZE:
        wdone = False
        if x[PHASE] == 0 and x[MODE_N] >= P[P_HURT_SKIP] + 1:
            x[MODE_T] = f32(x[MODE_T] + udt)
            if ge32(x[MODE_T], P[P_HURT_WAIT]):
                wdone = True
                x[PHASE] = 1.0
                x[MODE_T] = 0.0
        if x[PHASE] == 1 and not wdone:
            x[MODE_T] = f32(x[MODE_T] + udt)
            x[TS] = min(x[MODE_T] / P[P_HURT_RAMP], 1.0)
            if ge32(x[MODE_T], P[P_HURT_RAMP]):
                x[TS] = 1.0
                x[MODE] = M_HURT_RECOIL
                x[MODE_T] = 0.0
        x[MODE_N] = x[MODE_N] + 1
    ca_end = False
    if mode0 == M_CAST:
        x[MODE_T] = f32(x[MODE_T] + dt)
        ph = x[PHASE]
        if ph == 0 and ge32(x[MODE_T], P[P_CAST_ANTIC]):
            x[PHASE] = 1.0
            x[MODE_T] = 0.0
            x[VX] = 0.0
            x[VY] = 0.0
        if (ph == 1 and ge32(x[MODE_T], P[P_CAST_THROW])) or ((ev & EV_CATCH) != 0 and ph < 2):
            x[PHASE] = 2.0
            x[MODE_T] = 0.0
            x[VX] = -x[FACE] * P[P_CAST_CSPEED]
            x[VY] = 0.0
            x[GS] = 1.0
        if ph == 2 and ge32(x[MODE_T], P[P_CAST_CATCH]):
            ca_end = True
            x[MODE] = M_NORMAL
            x[GS] = 1.0
    bi_end = False
    if mode0 == M_BIND:
        x[MODE_T] = f32(x[MODE_T] + dt)
        if ge32(x[MODE_T], P[P_BIND_T]):
            bi_end = True
            x[MODE] = M_NORMAL
            x[VY] = P[P_BIND_ENDVY]
            x[GS] = 1.0
    if ca_end or bi_end:
        x[MOVE] = move
        x[JHELD] = 1.0 if jheld else 0.0
    if x[MODE] == M_LOCKED:
        x[MODE_T] = f32(x[MODE_T] + dt)
    x[INV_T] = max(f32(x[INV_T] - dt), 0.0)
    x[PREV] = np.float64(mask)


@njit(cache=True, inline="always")
def flags_of(x):
    m = x[MODE]
    f = 0
    if x[GROUND] > 0:
        f |= F_GROUND
    if x[JUMPING] > 0:
        f |= F_JUMPING
    if x[ATTACKING] > 0:
        f |= F_ATTACKING
    if x[RDIR] != 0:
        f |= F_RECOIL
    if relinq(m):
        f |= F_RELINQ
    ni = noinput(m)
    if x[INV_T] > 0 or ni:
        f |= F_INVULN
    if ni:
        f |= F_NO_INPUT
    return f


# ---- the frame loop -------------------------------------------------------------------------------------------

@njit(cache=True)
def lane(i, S0, masks, events, dts, fss, udts, P, TT, phys, rend, vel, modes, flags, final):
    x = S0[:, i].copy()
    p = P[i] if P.shape[0] > 1 else P[0]
    T = masks.shape[1]
    logged = dts.shape[1] == T and T > 0
    fdt = p[P_FDT]
    for t in range(T + 1):
        if t > 0:
            m = masks[i, t - 1]
            ev = events[i, t - 1]
            udt = udts[i, t - 1]
            if logged:
                dt = dts[i, t - 1]
                steps = np.int64(fss[i, t - 1])
                x[ALPHA] = x[ALPHA] + dt / fdt - steps
            else:
                dt = f32(udt * x[TS])
                a = x[ALPHA] + dt / fdt
                steps = np.int64(math.floor(a + 1e-9))
                x[ALPHA] = a - steps
            x[ALPHA] = min(max(x[ALPHA], 0.0), 1.0)
            for _ in range(steps):
                fixed_step(x, p, TT)
            apply_events(x, ev, p)
            update(x, m, ev, dt, udt, p)
        phys[i, t, 0] = x[PX]
        phys[i, t, 1] = x[PY]
        rend[i, t, 0] = x[QX] + x[ALPHA] * (x[SX] - x[QX])
        rend[i, t, 1] = x[QY] + x[ALPHA] * (x[SY] - x[QY])
        vel[i, t, 0] = x[VX]
        vel[i, t, 1] = x[VY]
        modes[i, t] = np.int32(x[MODE])
        flags[i, t] = flags_of(x)
    final[:, i] = x


@njit(cache=True)
def simulate(S0, masks, events, dts, fss, udts, P, TT):
    n, T = masks.shape
    phys = np.empty((n, T + 1, 2))
    rend = np.empty((n, T + 1, 2))
    vel = np.empty((n, T + 1, 2))
    modes = np.empty((n, T + 1), dtype=np.int32)
    flags = np.empty((n, T + 1), dtype=np.int32)
    final = np.empty_like(S0)
    for i in range(n):
        lane(i, S0, masks, events, dts, fss, udts, P, TT, phys, rend, vel, modes, flags, final)
    return phys, rend, vel, modes, flags, final


@njit(cache=True, parallel=True)
def simulate_par(S0, masks, events, dts, fss, udts, P, TT):
    n, T = masks.shape
    phys = np.empty((n, T + 1, 2))
    rend = np.empty((n, T + 1, 2))
    vel = np.empty((n, T + 1, 2))
    modes = np.empty((n, T + 1), dtype=np.int32)
    flags = np.empty((n, T + 1), dtype=np.int32)
    final = np.empty_like(S0)
    for i in prange(n):
        lane(i, S0, masks, events, dts, fss, udts, P, TT, phys, rend, vel, modes, flags, final)
    return phys, rend, vel, modes, flags, final
