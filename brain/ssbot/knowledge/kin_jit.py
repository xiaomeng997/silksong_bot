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
    P_MAXFALL, P_POGO_INV, P_POGO_J, P_POGO_JD, P_QQ, P_RDOWN_HALF, P_REL, P_RSTEPS, P_RUN, P_RV, P_SILK_MAX, P_SKIN, P_SLOP_HI,
    P_SLOP_LO, PHASE, PREV, PX, PY, QQ, QX, QY, RDIR, RSTEPS, SILK, SX, SY, TOL, TOUCH, TS, TT_HEAD, VX, VY, ALO, AHI,
    LANDQ, WF_PH, WF_T, WF_S, WF_DOWN, WF_WAIT, WF_UP, WF_TGT, P_BIND_BREAK, P_WF_BW, P_WF_BU, EV_FZ_BIND_BREAK,
    FREEZE_PRESETS, WF_ORDER)
from ssbot.knowledge.kinematics import (  # Forum loadout (abilities)
    AB_BROLLY, AB_CLING, AB_DASH, AB_HARD_LAND, AB_RPR_DOWN, AB_WALL, AB_WALLSLASH_SLOW, AIRDASHED, B_DASH, CLING,
    CLING_CD, DASH_CD, DASH_T, DQ, FALL_T, GL_CD, HARD, M_DASH, M_GLIDE, M_HARD_LAND, M_RPR_DS, M_SPRINT, P_ABIL,
    P_ADASH_T, P_AFC0, P_AFC1, P_AFC_T, P_ASPR_SPEED, P_ASPR_T, P_DASH_CD, P_DASH_SPEED, P_DASH_T, P_DQ, P_GL_AACC,
    P_GL_ACC, P_GL_ANTIC, P_GL_BRAY, P_GL_BVX, P_GL_CD, P_GL_DEC, P_GL_DEFLATE, P_GL_GRAY, P_GL_INFLATE,
    P_GL_START_VY, P_GL_VMAX, P_GL_VY, P_GL_VYACC, P_HARD_FALL, P_HARD_LAND, P_RPR_ADEC,
    P_RPR_ANTIC, P_RPR_FALL, P_RPR_FALL2, P_RPR_SDEC, P_RPR_SLASH, P_RPR_SPEED, P_SKID_DEC,
    P_SKID_T, P_SPR_ACC, P_SPR_SPEED, P_W_CCD, P_W_CDECEL, P_W_CONTACT, P_W_CVMIN, P_W_RAY, P_W_RAY_B, P_W_SHOVE,
    P_W_SLASH_VMIN, P_W_STICK, P_W_STICKY, P_W_ACCEL, P_W_TRAY, P_WJ_CHAIN, P_WJ_JUMPED, P_WJ_LONG, P_WJ_SHORT,
    P_WJ_SPEED, PREV_GS, SP_X, UNSTICK, WJ_CHAIN, WJ_DIR, WJ_V, WJQ, WLOCK, WSIDE, WSLASH, WSTICK, WTOUCH, WCON, SHOVE,
    RX0, RY0, JBUF,
    M_SCRAMBLE, P_SCR_ANTIC, P_SCR_SPEED, P_SCR_FORCE, P_SCR_FORCE_H, P_SCR_END_VY, P_SCR_END_DEC, P_SCR_END_T,
    P_SCR_ROOF_RAY, P_SCR_ROOF_T, P_SCR_DETACH, P_SPR_SHIFT, P_SPR_GRACE, P_SKID_DEC_MV, P_SKID_VMIN, P_AFC_LAG, P_RPR_TDEC,
    P_RPR_TREACH0, P_RPR_TREACH1, P_RPR_TREACH_T, P_RPR_TLOBE0,
    P_RPR_TLOBE1, AB_THUNK, AB_SLOPES, ATK_KIND, ALT, ALT_T, ATK_PDIR, P_THK_ON, P_THK_OFF, P_THK_OFF_UP, P_THK,
    THK_STRIDE, ALT_ATTACK_RESET, P_SLOPE_CONTACT)

# world freeze presets in start order (kinematics.WF_ORDER): event bit, rampDown, wait, rampUp, target
_WF = np.array([[float(b), *FREEZE_PRESETS[b]] for b in WF_ORDER])
_WF_BB = int(EV_FZ_BIND_BREAK)


@njit(cache=True, inline="always", error_model="numpy")
def f32(a):
    return np.float64(np.float32(a))


@njit(cache=True, inline="always", error_model="numpy")
def ge32(a, c):
    return np.float32(a) >= np.float32(c)


@njit(cache=True, inline="always", error_model="numpy")
def gt32(a, c):
    return np.float32(a) > np.float32(c)


@njit(cache=True, inline="always", error_model="numpy")
def relinq(m):
    return (m == M_DS_ANTIC or m == M_DS_SPIKE or m == M_CAST or m == M_BIND or m == M_LOCKED or m == M_GLIDE
            or m == M_SPRINT or m == M_RPR_DS or m == M_SCRAMBLE)


@njit(cache=True, inline="always", error_model="numpy")
def noinput(m):
    return m == M_HURT_FREEZE or m == M_HURT_RECOIL


# ---- collision ------------------------------------------------------------------------------------------------
# The terrain reaches the kernel as one packed float64 array TT (Terrain2D.packed(): segments plus an x-bucket index,
# each bucket listing the floors / ceilings whose x extent and the walls whose x falls in it); the queries visit only
# the buckets their tests can pass in, and take scalars plus TT so the per-step calls carry one array, not seven.
# TT header (TT_HEAD entries): nh, nv, buckets, x0, 1 / width, bucket starts (h), ids (h), bucket starts (v), ids (v),
# vseg offset, ns, slope offset, bucket starts (slopes), ids (slopes); hseg rows (y, x0, x1) from TT_H, vseg rows
# (x, y0, y1) from TT[9], slope rows (x0, y0, x1, y1) from TT[11] (the rollout does not collide them; the knockback
# bound does, see ssbot.knowledge.knockback).
TT_H = TT_HEAD


@njit(cache=True, inline="always", error_model="numpy")
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


@njit(cache=True, inline="always", error_model="numpy")
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


@njit(cache=True, inline="always", error_model="numpy")
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


@njit(cache=True, inline="always", error_model="numpy")
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


# ---- Forum loadout (HeroParams.abilities != 0) -------------------------------------------------------------------
# One implementation only: these rules exist as scalar code here (the NumPy reference in kinematics.py covers the
# Hunter rules, which take none of these branches while abilities is 0, so the Hunter rollout is unchanged bit for
# bit). Sources, HeroController 1.0.30000 unless noted: wall slide LookForInput 8397-8406, BeginWallSlide 8461-8528,
# Update 2198-2289, FixedUpdate 3118-3181, LateUpdate 3869-3907, CancelWallsliding 9930; wall touch
# OnCollisionStay2D 11469-11507 + WallTouchCache (0.1 u rays at the box side's mid / bottom); wall jump DoWallJump
# 8855-8925, CanWallJump 11260, CanChainWallJumps 11285, TryQueueWallJumpInterrupt 11024, JumpReleased 10298;
# wall slash Attack 4125-4137 (Reaper WallSlashSlowdown), up slash off a wall 4164-4169; dash HeroDash 9058,
# Dash 4334, CanDash 10902, FinishedDashing 10325; then the Sprint FSM (template hornet_sprint: Try, Start Sprint,
# Air Dir, Air Sprint L/R, Air Sprint Loop, Ground Dir, Ground Sprint L/R); glide CanFloat 11069 and the Umbrella
# Float FSM (hornet_umbrella_float: Take Control, Antic, Inflate, Start, Float Idle, Bump L/R, Deflate, Relinquish
# Control, Cooldown); Reaper down slash: the Crest Attacks FSM (crest_attacks: Rpr Downslash Antic / Downslash /
# Fall / Fall 2 / End); hard landing FallCheck 9730, DoHardLanding 8999. FSM actions read the input the frame's
# FixedUpdates see, i.e. the previous frame's (x[PREV]); PlayMaker velocity actions (UmbrellaMotionX, AccelerateToX,
# AccelerateToY, DecelerateV2 / XY, SetVelocity2dConditional) run per physics step, their OnEnter once in the
# Update that enters the state. Animation-timed FSM states end after HeroParams *_t of scaled time counted from the
# frame after their entry (as the Silkspear phases). Wall side: -1 = the wall is on the hero's left.

EPS_F = 1.401298464e-45       # Mathf.Epsilon


@njit(cache=True, inline="always", error_model="numpy")
def grav_off(x):
    """AffectedByGravity(false)."""
    if x[GS] > EPS_F:
        x[PREV_GS] = x[GS]
        x[GS] = 0.0


@njit(cache=True, inline="always", error_model="numpy")
def grav_on(x):
    """AffectedByGravity(true)."""
    if x[GS] <= EPS_F:
        x[GS] = x[PREV_GS]
        x[PREV_GS] = 0.0


@njit(cache=True, error_model="numpy")
def wall_near(px, py, side, reach, P, TT):
    """A wall face on `side` within `reach` of the box side whose y span holds the box's centre or bottom height
    (WallTouchCache's mid and bottom rays)."""
    if TT[1] == 0:
        return False
    edge = px + side * P[P_HW]
    ymid = py + 0.5 * (P[P_HEAD] - P[P_FOOT])
    ybot = py - P[P_FOOT]
    b0, b1 = _buckets(edge - reach - TOL, edge + reach + TOL, TT)
    st, ids, ov = np.int64(TT[7]), np.int64(TT[8]), np.int64(TT[9])
    for b in range(b0, b1 + 1):
        for q in range(np.int64(TT[st + b]), np.int64(TT[st + b + 1])):
            j = ov + 3 * np.int64(TT[ids + q])
            gap = (edge - TT[j]) if side < 0 else (TT[j] - edge)
            if gap < -TOL or gap > reach:
                continue
            if (TT[j + 1] - EPS <= ymid <= TT[j + 2] + EPS) or (TT[j + 1] - EPS <= ybot <= TT[j + 2] + EPS):
                return True
    return False


@njit(cache=True, inline="always", error_model="numpy")
def wall_gaps(px, py, reach, P, TT):
    """(gap to the nearest wall face on the left, on the right) within `reach` of the box sides whose y span holds
    the box's centre or bottom height (np.inf: none); one pass over the walls for both sides."""
    gl = np.inf
    gr = np.inf
    if TT[1] == 0:
        return gl, gr
    hw = P[P_HW]
    ymid = py + 0.5 * (P[P_HEAD] - P[P_FOOT])
    ybot = py - P[P_FOOT]
    b0, b1 = _buckets(px - hw - reach - TOL, px + hw + reach + TOL, TT)
    st, ids, ov = np.int64(TT[7]), np.int64(TT[8]), np.int64(TT[9])
    for b in range(b0, b1 + 1):
        for q in range(np.int64(TT[st + b]), np.int64(TT[st + b + 1])):
            j = ov + 3 * np.int64(TT[ids + q])
            if not ((TT[j + 1] - EPS <= ymid <= TT[j + 2] + EPS) or (TT[j + 1] - EPS <= ybot <= TT[j + 2] + EPS)):
                continue
            s = TT[j]
            g = (px - hw) - s
            if -TOL <= g <= reach and g < gl:
                gl = g
            g = s - (px + hw)
            if -TOL <= g <= reach and g < gr:
                gr = g
    return gl, gr


@njit(cache=True, error_model="numpy")
def hray(x0, y0, side, length, TT):
    """A horizontal ray from (x0, y0) of `length` towards `side` meets a wall segment."""
    if TT[1] == 0:
        return False
    lo = x0 - length if side < 0 else x0
    hi = x0 if side < 0 else x0 + length
    b0, b1 = _buckets(lo - 0.02, hi + 0.02, TT)
    st, ids, ov = np.int64(TT[7]), np.int64(TT[8]), np.int64(TT[9])
    for b in range(b0, b1 + 1):
        for q in range(np.int64(TT[st + b]), np.int64(TT[st + b + 1])):
            j = ov + 3 * np.int64(TT[ids + q])
            d = side * (TT[j] - x0)
            if 0.0 <= d <= length and TT[j + 1] <= y0 <= TT[j + 2]:
                return True
    return False


@njit(cache=True, error_model="numpy")
def vray(x0, y0, length, TT):
    """A downward ray from (x0, y0) of `length` meets a floor segment."""
    if TT[0] == 0:
        return False
    b0, b1 = _buckets(x0 - 0.01, x0 + 0.01, TT)
    st, ids = np.int64(TT[5]), np.int64(TT[6])
    for b in range(b0, b1 + 1):
        for q in range(np.int64(TT[st + b]), np.int64(TT[st + b + 1])):
            j = TT_H + 3 * np.int64(TT[ids + q])
            d = y0 - TT[j]
            if -EPS <= d <= length and TT[j + 1] <= x0 <= TT[j + 2]:
                return True
    return False


@njit(cache=True, error_model="numpy")
def roof_ray(x0, top, length, TT, slopes=False):
    """CharacterBumpCheck.CheckForBump(top)'s wall ray: from (x0, top - 0.1) up 0.1 + `length` meets a horizontal
    segment (or, with `slopes`, a sloped edge: the Forum's roof over the left wall top is one)."""
    if TT[0] > 0:
        b0, b1 = _buckets(x0 - 0.01, x0 + 0.01, TT)
        st, ids = np.int64(TT[5]), np.int64(TT[6])
        for b in range(b0, b1 + 1):
            for q in range(np.int64(TT[st + b]), np.int64(TT[st + b + 1])):
                j = TT_H + 3 * np.int64(TT[ids + q])
                d = TT[j] - top
                if -0.1 <= d <= length and TT[j + 1] <= x0 <= TT[j + 2]:
                    return True
    if slopes and TT[10] > 0:
        b0, b1 = _buckets(x0 - 0.01, x0 + 0.01, TT)
        st, ids, ov = np.int64(TT[12]), np.int64(TT[13]), np.int64(TT[11])
        for b in range(b0, b1 + 1):
            for q in range(np.int64(TT[st + b]), np.int64(TT[st + b + 1])):
                j = ov + 4 * np.int64(TT[ids + q])
                ax, ay, bx, by = TT[j], TT[j + 1], TT[j + 2], TT[j + 3]
                if min(ax, bx) <= x0 <= max(ax, bx) and abs(bx - ax) > 1e-6:
                    d = ay + (x0 - ax) * (by - ay) / (bx - ax) - top
                    if -0.1 <= d <= length:
                        return True
    return False


@njit(cache=True, error_model="numpy")
def rpr_thunk(x, P, TT):
    """The Reaper down slash's terrain thunker (NailSlashTerrainThunk on the DownSlash collider) meets a floor below
    the hero: a floor segment under the slash's forward lobe within the reach below the box centre, which grows as
    the slash's effect plays (fit on the excitation runs: 2.18 u over the first four frames, 2.33 u after). Walls
    beside the hero do not thunk it (no wall-clinging slash high above the floor did)."""
    if TT[0] == 0:
        return False
    cy = x[PY] + 0.5 * (P[P_HEAD] - P[P_FOOT])
    reach = P[P_RPR_TREACH0] if x[MODE_T] < P[P_RPR_TREACH_T] else P[P_RPR_TREACH1]
    a = x[PX] + x[FACE] * P[P_RPR_TLOBE0]
    b = x[PX] + x[FACE] * P[P_RPR_TLOBE1]
    lo, hi = min(a, b), max(a, b)
    b0, b1 = _buckets(lo - 0.01, hi + 0.01, TT)
    st, ids = np.int64(TT[5]), np.int64(TT[6])
    for k in range(b0, b1 + 1):
        for q in range(np.int64(TT[st + k]), np.int64(TT[st + k + 1])):
            j = TT_H + 3 * np.int64(TT[ids + q])
            d = cy - TT[j]
            if 0.0 <= d <= reach and TT[j + 1] < hi and TT[j + 2] > lo:
                return True
    return False


@njit(cache=True, inline="always", error_model="numpy")
def _cross(ax, ay, bx, by, cx, cy):
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


@njit(cache=True, error_model="numpy")
def _seg_meets_poly(ax, ay, bx, by, wx, wy, n):
    """The segment (a, b) meets the polygon (wx, wy)[:n] (as an area: crosses an edge or lies inside)."""
    inside = False
    for i in range(n):
        k = (i + 1) % n
        if (wy[i] > ay) != (wy[k] > ay) and ax < wx[i] + (ay - wy[i]) * (wx[k] - wx[i]) / (wy[k] - wy[i]):
            inside = not inside
    if inside:
        return True
    for i in range(n):
        k = (i + 1) % n
        d1 = _cross(ax, ay, bx, by, wx[i], wy[i])
        d2 = _cross(ax, ay, bx, by, wx[k], wy[k])
        d3 = _cross(wx[i], wy[i], wx[k], wy[k], ax, ay)
        d4 = _cross(wx[i], wy[i], wx[k], wy[k], bx, by)
        if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
            return True
    return False


@njit(cache=True, error_model="numpy")
def slash_thunk(px, py, face, kind, P, TT):
    """The swing's Terrain Thunker (a copy of its damage polygon, P_THK tail) meets terrain the way
    NailSlashTerrainThunk recoils from (TerrainThunkUtils.GenerateTerrainThunk): a side slash (kind 1 / 2) a wall face
    in front of the hero (contact x past hero.pos along the facing, a horizontal surface normal: RecoilLeft / Right),
    an up slash (kind 3) a ceiling or a shallow slope above hero.pos (vertical normal: RecoilDown). Placed at the body
    position the step started from (the thunker's kinematic body is synced to the transform before the step)."""
    base = P_THK + (np.int64(kind) - 1) * THK_STRIDE
    n = np.int64(P[base])
    if n < 3:
        return False
    cx = px
    cy = py + 0.5 * (P[P_HEAD] - P[P_FOOT])
    wx = np.empty(n)
    wy = np.empty(n)
    for i in range(n):
        wx[i] = cx + face * P[base + 1 + 2 * i]
        wy[i] = cy + P[base + 2 + 2 * i]
    x0, x1 = wx.min(), wx.max()
    y0, y1 = wy.min(), wy.max()
    b0, b1 = _buckets(x0 - 0.02, x1 + 0.02, TT)
    if kind <= 2:
        if TT[1] == 0:
            return False
        st, ids, ov = np.int64(TT[7]), np.int64(TT[8]), np.int64(TT[9])
        for b in range(b0, b1 + 1):
            for q in range(np.int64(TT[st + b]), np.int64(TT[st + b + 1])):
                j = ov + 3 * np.int64(TT[ids + q])
                xs = TT[j]
                if face * (xs - px) <= 0.0 or xs < x0 or xs > x1 or TT[j + 2] < y0 or TT[j + 1] > y1:
                    continue
                if _seg_meets_poly(xs, TT[j + 1], xs, TT[j + 2], wx, wy, n):
                    return True
        return False
    if TT[0] > 0:
        st, ids = np.int64(TT[5]), np.int64(TT[6])
        for b in range(b0, b1 + 1):
            for q in range(np.int64(TT[st + b]), np.int64(TT[st + b + 1])):
                j = TT_H + 3 * np.int64(TT[ids + q])
                ys = TT[j]
                if ys <= py or ys < y0 or ys > y1 or TT[j + 2] < x0 or TT[j + 1] > x1:
                    continue
                if _seg_meets_poly(TT[j + 1], ys, TT[j + 2], ys, wx, wy, n):
                    return True
    if TT[10] > 0:
        st, ids, ov = np.int64(TT[12]), np.int64(TT[13]), np.int64(TT[11])
        for b in range(b0, b1 + 1):
            for q in range(np.int64(TT[st + b]), np.int64(TT[st + b + 1])):
                j = ov + 4 * np.int64(TT[ids + q])
                ax, ay, bx, by = TT[j], TT[j + 1], TT[j + 2], TT[j + 3]
                if abs(by - ay) > abs(bx - ax) or max(ay, by) <= py:
                    continue                  # a steep edge (its normal is horizontal) or below hero.pos
                if max(ax, bx) < x0 or min(ax, bx) > x1 or max(ay, by) < y0 or min(ay, by) > y1:
                    continue
                if _seg_meets_poly(ax, ay, bx, by, wx, wy, n):
                    return True
    return False


@njit(cache=True, error_model="numpy")
def _slope_axis(cx, cy, c0x, c0y, ax, ay, bx, by, hw, hh, skin):
    """Box (centre c, half sizes hw, hh) against one sloped edge, as Box2D's polygon-edge manifold picks its reference
    face: the separating axis with the least penetration (into the box inflated by the skin) among the edge normal
    (oriented to the side c0 is on) and the box's x / y axes (an edge end poking into a box face), the edge normal
    preferred within 1 mm. Returns (penetration, axis x, axis y): the direction to push the box; penetration <= 0
    when they are apart."""
    ex = bx - ax
    ey = by - ay
    ln = math.sqrt(ex * ex + ey * ey)
    if ln < 1e-9:
        return 0.0, 0.0, 0.0
    enx = -ey / ln
    eny = ex / ln
    if (c0x - ax) * enx + (c0y - ay) * eny < 0:
        enx = -enx
        eny = -eny
    pen_n = skin - ((cx - ax) * enx + (cy - ay) * eny - (abs(enx) * hw + abs(eny) * hh))
    if pen_n <= 0:
        return 0.0, 0.0, 0.0
    if c0x >= 0.5 * (ax + bx):
        pen_x = max(ax, bx) - (cx - hw) + skin
        sx = 1.0
    else:
        pen_x = (cx + hw) - min(ax, bx) + skin
        sx = -1.0
    if c0y >= 0.5 * (ay + by):
        pen_y = max(ay, by) - (cy - hh) + skin
        sy = 1.0
    else:
        pen_y = (cy + hh) - min(ay, by) + skin
        sy = -1.0
    if pen_x <= 0 or pen_y <= 0:
        return 0.0, 0.0, 0.0
    if pen_n <= pen_x + 1e-3 and pen_n <= pen_y + 1e-3:
        return pen_n, enx, eny
    if pen_y <= pen_x:
        return pen_y, 0.0, sy
    return pen_x, sx, 0.0


@njit(cache=True, error_model="numpy")
def roof_touch(px, py, P, TT):
    """The box top rests against a horizontal ceiling (within the skin and Box2D's 5 mm slop) over the box's x span:
    the contact a step that ended just short of the ceiling makes at the start of the next one."""
    if TT[0] == 0:
        return False
    hw = P[P_HW]
    top = py + P[P_HEAD]
    reach = P[P_SKIN] + P[P_SLOPE_CONTACT]
    b0, b1 = _buckets(px - hw - 0.01, px + hw + 0.01, TT)
    st, ids = np.int64(TT[5]), np.int64(TT[6])
    for b in range(b0, b1 + 1):
        for q in range(np.int64(TT[st + b]), np.int64(TT[st + b + 1])):
            j = TT_H + 3 * np.int64(TT[ids + q])
            if not ((px + hw) > TT[j + 1] + EPS and (px - hw) < TT[j + 2] - EPS):
                continue
            d = TT[j] - top
            if -TOL <= d <= reach:
                return True
    return False


@njit(cache=True, error_model="numpy")
def slope_project(px, py, vx, vy, P, TT):
    """The start of a physics step: a contact with a sloped edge the box already rests against (within the skin and
    Box2D's 5 mm slop) takes the velocity's component into the surface away before the move, so the step slides
    along it (the axis-aligned moves would otherwise meet a wall end the slide passes under: s98200 f770141, sliding
    down Hang_12's 45 deg ceiling under a tile corner 7 mm below it). Returns (vx, vy)."""
    if TT[10] == 0:
        return vx, vy
    hw = P[P_HW]
    hh = 0.5 * (P[P_HEAD] + P[P_FOOT])
    cx = px
    cy = py + 0.5 * (P[P_HEAD] - P[P_FOOT])
    reach = P[P_SKIN] + P[P_SLOPE_CONTACT]
    st, ids, ov = np.int64(TT[12]), np.int64(TT[13]), np.int64(TT[11])
    b0, b1 = _buckets(cx - hw - 0.05, cx + hw + 0.05, TT)
    for b in range(b0, b1 + 1):
        for q in range(np.int64(TT[st + b]), np.int64(TT[st + b + 1])):
            j = ov + 4 * np.int64(TT[ids + q])
            ax, ay, bx, by = TT[j], TT[j + 1], TT[j + 2], TT[j + 3]
            if max(ax, bx) < cx - hw - reach or min(ax, bx) > cx + hw + reach or \
                    max(ay, by) < cy - hh - reach or min(ay, by) > cy + hh + reach:
                continue
            pen, ux, uy = _slope_axis(cx, cy, cx, cy, ax, ay, bx, by, hw, hh, reach)
            if pen <= 0:
                continue
            vn = vx * ux + vy * uy
            if vn < 0:
                vx -= vn * ux
                vy -= vn * uy
    return vx, vy


@njit(cache=True, error_model="numpy")
def slope_push(x0, y0, nx, ny, vx, vy, P, TT):
    """After the step's axis-aligned move from body position (x0, y0) to (nx, ny): a box that went into a sloped
    terrain edge (closer than P_SLOPE_CONTACT) stops at it, out to the skin, and loses the velocity component into the
    surface in the same step (Box2D's time-of-impact sub-step solves the contact: live s98200 f755635, a jump into
    Hang_12's ceiling vertex stopped 0.014 u under it with vy 0; f761658, a jump into its ceiling slope went from
    (8.25, 0.60) after gravity to (7.11, -2.56), the projection on the normal (-0.339, -0.941), no friction; the
    step before, 0.0095 u from the slope, it had not touched). Two passes over the edges in reach. Returns
    (nx, ny, vx, vy, contact: 1 a roof, its normal pointing down 60 deg or more (OnCollisionEnter2D's side "top"),
    2 a floor, 0 none or a side)."""
    if TT[10] == 0:
        return nx, ny, vx, vy, 0
    hw = P[P_HW]
    hh = 0.5 * (P[P_HEAD] + P[P_FOOT])
    off = 0.5 * (P[P_HEAD] - P[P_FOOT])
    skin = P[P_SKIN]
    need = skin - P[P_SLOPE_CONTACT]      # penetration into the skin-inflated box that makes a contact
    c0x = x0
    c0y = y0 + off
    contact = 0
    st, ids, ov = np.int64(TT[12]), np.int64(TT[13]), np.int64(TT[11])
    for _ in range(2):
        b0, b1 = _buckets(nx - hw - 0.05, nx + hw + 0.05, TT)
        for b in range(b0, b1 + 1):
            for q in range(np.int64(TT[st + b]), np.int64(TT[st + b + 1])):
                j = ov + 4 * np.int64(TT[ids + q])
                ax, ay, bx, by = TT[j], TT[j + 1], TT[j + 2], TT[j + 3]
                cx = nx
                cy = ny + off
                if max(ax, bx) < cx - hw - skin or min(ax, bx) > cx + hw + skin or \
                        max(ay, by) < cy - hh - skin or min(ay, by) > cy + hh + skin:
                    continue
                pen, ux, uy = _slope_axis(cx, cy, c0x, c0y, ax, ay, bx, by, hw, hh, skin)
                if pen <= need or pen <= 0:
                    continue
                nx += ux * pen
                ny += uy * pen
                vn = vx * ux + vy * uy
                if vn < 0:
                    vx -= vn * ux
                    vy -= vn * uy
                if uy <= -0.5:
                    contact = 1
                elif uy >= 0.5:
                    contact = 2
    return nx, ny, vx, vy, contact


@njit(cache=True, error_model="numpy")
def forum_swing(x, mask, P):
    """Attack()'s slash bookkeeping (AB_THUNK): the direction, altAttack (cleared past AttackRecoveryTime +
    ALT_ATTACK_RESET since the last slash or on a new direction; a normal / up slash takes the alternate one when it
    is set and toggles it), the swing kind for its terrain thunker, altAttackTime and prevAttackDir."""
    up = (mask & B_UP) != 0
    down = not up and (mask & B_DOWN) != 0 and x[GROUND] <= 0
    dirn = 1.0 if up else (2.0 if down else 0.0)
    if x[ALT_T] > P[P_ATK_REC] + ALT_ATTACK_RESET or dirn != x[ATK_PDIR]:
        x[ALT] = 0.0
    kind = 0.0
    if dirn == 0 and x[WSIDE] != 0:
        kind = 4.0                        # wall slash: the polygon lies behind the facing, never thunks
    elif dirn == 0 or dirn == 1:
        if dirn == 0:
            kind = 2.0 if x[ALT] > 0 else 1.0
        else:
            kind = 3.0
        x[ALT] = 0.0 if x[ALT] > 0 else 1.0
    if dirn != 2:
        x[ALT_T] = 0.0                    # altAttackTime (a Custom down slash is not "slashing")
    x[ATK_PDIR] = dirn
    x[ATK_KIND] = kind


@njit(cache=True, error_model="numpy")
def thunk_step(x, P, TT):
    """After a physics step: the swing's thunker met terrain in it (OnCollisionEnter2D, handled at once): Recoil away
    from the wall (allowed while relinquished, not while already recoiling; it also cancels a dash and the wall
    jump's push) or RecoilDown off a ceiling (CancelJump, the rise stops). One thunk per swing."""
    k = x[ATK_KIND]
    if k <= 0 or k > 3 or x[ATTACKING] <= 0:
        return
    if not ge32(x[ATK_T], P[P_THK_ON]) or ge32(x[ATK_T], P[P_THK_OFF_UP] if k == 3 else P[P_THK_OFF]):
        return
    if not slash_thunk(x[QX], x[QY], x[FACE], k, P, TT):
        return
    x[ATK_KIND] = -k
    if k == 3:
        x[JUMPING] = 0.0
        x[JSTEPS] = 0.0
        x[WLOCK] = -1.0
        if x[VY] > 0 and not relinq(x[MODE]):
            x[VY] = x[VY] * 0.5 if P[P_RDOWN_HALF] > 0 else 0.0
        return
    if x[RDIR] != 0 or noinput(x[MODE]):
        return
    side = -x[FACE]
    if x[MODE] == M_DASH:
        x[MODE] = M_NORMAL
        x[DASH_T] = 0.0
        grav_on(x)
    x[RDIR] = side
    x[RSTEPS] = P[P_RSTEPS]
    x[VX] = side * P[P_RV]
    x[WJ_DIR] = 0.0


@njit(cache=True, error_model="numpy")
def facing_near_wall(x0, y0, face, length, TT):
    """IsFacingNearWall: the ray of `length` from hero.pos along the facing meets a wall, and so do the rays 0.1 u
    apart above and below it over at least 1.5 u in all (each side counted to its first miss, at most 1.4 u;
    float32 sums as the game's loop)."""
    if TT[1] == 0:
        return False
    # the wall segments within reach along the facing, collected once (the 29 rays then test only these)
    lo = x0 - length if face < 0 else x0
    hi = x0 if face < 0 else x0 + length
    b0, b1 = _buckets(lo - 0.02, hi + 0.02, TT)
    st, ids, ov = np.int64(TT[7]), np.int64(TT[8]), np.int64(TT[9])
    ya = np.empty(32)
    yb = np.empty(32)
    m = 0
    for b in range(b0, b1 + 1):
        for q in range(np.int64(TT[st + b]), np.int64(TT[st + b + 1])):
            j = ov + 3 * np.int64(TT[ids + q])
            d = face * (TT[j] - x0)
            if 0.0 <= d <= length and TT[j + 2] >= y0 - 1.5 and TT[j + 1] <= y0 + 1.5 and m < 32:
                ya[m] = TT[j + 1]
                yb[m] = TT[j + 2]
                m += 1
    if not _covered(ya, yb, m, y0):
        return False
    num = np.float32(0.0)
    k = np.float32(0.1)
    while k < np.float32(1.5) and _covered(ya, yb, m, y0 + np.float64(k)):
        num = np.float32(num + np.float32(0.1))
        k = np.float32(k + np.float32(0.1))
    k = np.float32(0.1)
    while k < np.float32(1.5) and _covered(ya, yb, m, y0 - np.float64(k)):
        num = np.float32(num + np.float32(0.1))
        k = np.float32(k + np.float32(0.1))
    return not (num < np.float32(1.5))


@njit(cache=True, inline="always", error_model="numpy")
def _covered(ya, yb, m, y):
    for i in range(m):
        if ya[i] <= y <= yb[i]:
            return True
    return False


@njit(cache=True, inline="always", error_model="numpy")
def rend_x(x):
    return x[QX] + x[ALPHA] * (x[SX] - x[QX])


@njit(cache=True, inline="always", error_model="numpy")
def rend_y(x):
    return x[QY] + x[ALPHA] * (x[SY] - x[QY])


@njit(cache=True, inline="always", error_model="numpy")
def move_of(mask):
    return (1.0 if (mask & B_RIGHT) != 0 else 0.0) - (1.0 if (mask & B_LEFT) != 0 else 0.0)


@njit(cache=True, inline="always", error_model="numpy")
def umbrella_x(vx, mask, acc, dec, vmax):
    """UmbrellaMotionX.DoAccelerate."""
    num = vx
    if (mask & B_RIGHT) != 0:
        if num < vmax:
            num += acc
    elif (mask & B_LEFT) != 0:
        if num > -vmax:
            num -= acc
    elif num > 0.0:
        num -= dec
        if num < 0.0:
            num = 0.0
    elif num < 0.0:
        num += dec
        if num > 0.0:
            num = 0.0
    return min(max(num, -vmax), vmax)


@njit(cache=True, inline="always", error_model="numpy")
def accel_to(v, acc, target):
    """AccelerateToX / AccelerateToY on one axis."""
    if v > target:
        v -= acc
        if v < target:
            v = target
    if v < target:
        v += acc
        if v > target:
            v = target
    return v


@njit(cache=True, inline="always", error_model="numpy")
def decel(v, f):
    """DecelerateV2 / DecelerateXY on one axis (the sign never flips)."""
    if v < 0.0:
        v *= f
        if v > 0.0:
            v = 0.0
    elif v > 0.0:
        v *= f
        if v < 0.0:
            v = 0.0
    return v


@njit(cache=True, inline="always", error_model="numpy")
def chain_ok(x):
    """CanChainWallJumps (dashing down is not modelled)."""
    return x[WLOCK] >= 0 or x[WJ_CHAIN] > 0 or x[MOVE] != 0


@njit(cache=True, error_model="numpy")
def cancel_wallslide(x):
    """CancelWallsliding (gravity back even when not sliding, touch flags cleared)."""
    if x[WSIDE] != 0:
        x[WSIDE] = 0.0
        x[CLING] = 0.0
    grav_on(x)
    x[WTOUCH] = 0.0


@njit(cache=True, error_model="numpy")
def can_start_wallslide(x, falling, P, TT):
    """CanStartWithWallSlide: in the air, falling (or already sliding), not attacking unless wall slashing, facing a
    wall 0.6 u away with enough height (non-slider walls are not in the terrain dump: never)."""
    if x[GROUND] > 0:
        return False
    if not (falling or x[WSIDE] != 0):
        return False
    if x[ATTACKING] > 0 and x[WSLASH] <= 0:
        return False
    return facing_near_wall(rend_x(x), rend_y(x), x[FACE], P[P_W_RAY], TT)


@njit(cache=True, error_model="numpy")
def begin_wallslide(x, require_input, mask):
    """BeginWallSlide; returns whether a slide started."""
    if x[WSIDE] != 0:
        return False
    side = 0.0
    if x[WTOUCH] < 0 and (not require_input or (mask & B_LEFT) != 0):
        side = -1.0
    if x[WTOUCH] > 0 and (not require_input or (mask & B_RIGHT) != 0):
        side = 1.0
    if side == 0:
        return False
    x[FACE] = side
    x[JUMPING] = 0.0                      # CancelJump
    x[JSTEPS] = 0.0
    x[WLOCK] = -1.0
    if x[MODE] == M_DASH:                 # CancelDash
        x[MODE] = M_NORMAL
        x[DASH_T] = 0.0
        grav_on(x)
    x[AIRDASHED] = 0.0
    x[WSIDE] = side
    grav_off(x)
    x[DASH_CD] = 0.0
    return True


@njit(cache=True, error_model="numpy")
def do_wall_jump(x, P):
    """DoWallJump: face away from the wall, x speed locked to WJ_KICKOFF_SPEED decaying to the run speed over
    WJLOCK_STEPS_LONG steps, a full jump (jumped_steps 5, so a release halves vy at once and unlocks)."""
    t = x[WTOUCH] if x[WTOUCH] != 0 else x[WSIDE]
    x[WJQ] = 0.0
    if t < 0:
        x[FACE] = 1.0
        x[WJ_DIR] = 1.0
    elif t > 0:
        x[FACE] = -1.0
        x[WJ_DIR] = -1.0
    cancel_wallslide(x)
    x[AIRDASHED] = 0.0
    x[WJ_V] = P[P_WJ_SPEED]
    x[JUMPING] = 1.0
    x[WLOCK] = 0.0
    x[JQ] = -1.0
    x[JDSTEPS] = P[P_WJ_JUMPED]


@njit(cache=True, error_model="numpy")
def queue_wj_interrupt(x, P, TT):
    """TryQueueWallJumpInterrupt: a jump press near a facing wall (1 u) that cannot act yet becomes a wall jump in
    the next frame's queue check."""
    if x[WJQ] > 0:
        return True
    ab = np.int64(P[P_ABIL])
    if (ab & AB_WALL) != 0 and facing_near_wall(rend_x(x), rend_y(x), x[FACE], P[P_W_RAY_B], TT):
        if not chain_ok(x):
            return False
        x[WJQ] = 1.0
        return True
    return False


@njit(cache=True, error_model="numpy")
def relinquish_nv(x):
    """RelinquishControlNotVelocity (ResetMotionNotVelocity, ResetAttacks, no_input): what every FSM move here
    starts with."""
    x[JUMPING] = 0.0
    x[JSTEPS] = 0.0
    x[WLOCK] = -1.0
    x[BOUNCE] = -1.0
    x[RDIR] = 0.0
    cancel_wallslide(x)
    x[GS] = 1.0                           # ResetGravity
    x[ATTACKING] = 0.0
    x[WSLASH] = 0.0
    x[WTOUCH] = 0.0
    x[DASH_T] = 0.0


@njit(cache=True, error_model="numpy")
def regain(x, mask):
    """RegainControl at the end of an FSM move: control and the move input back."""
    x[MODE] = M_NORMAL
    x[MODE_T] = 0.0
    x[PHASE] = 0.0
    x[HARD] = 0.0
    x[MOVE] = move_of(mask)
    x[JHELD] = 1.0 if (mask & B_JUMP) != 0 else 0.0


@njit(cache=True, error_model="numpy")
def regain_jump(x, mask, P):
    """RegainControl's plain path: control back, and a jump press still in InputHandler's 0.1 s queue
    (GetWasButtonPressedQueued) jumps if the hero can (live: a glide pressed just above the floor lands and jumps
    with the button still held)."""
    regain(x, mask)
    if x[JBUF] > 0 and x[JUMPING] <= 0 and x[BOUNCE] < 0 and x[DS_REC] < 0 and (x[GROUND] > 0 or x[LEDGE] > 0):
        x[JBUF] = 0.0
        hero_jump(x, P)


@njit(cache=True, error_model="numpy")
def start_glide(x, mask, P):
    """StartFloat -> Umbrella Float FSM Take Control -> Antic (UmbrellaMotionX OnEnter). Ignored while the FSM's
    cooldown runs (the press is spent all the same)."""
    if x[GL_CD] > 0:
        return
    relinquish_nv(x)
    x[MODE] = M_GLIDE
    x[PHASE] = 0.0
    x[MODE_T] = 0.0
    x[VX] = umbrella_x(x[VX], mask, P[P_GL_AACC], P[P_GL_DEC], P[P_GL_VMAX])


@njit(cache=True, error_model="numpy")
def can_float(x, P, TT):
    """CanFloat (Drifter's Cloak), its TryQueueWallJumpInterrupt side effect included."""
    if (np.int64(P[P_ABIL]) & AB_BROLLY) == 0 or x[GROUND] > 0 or x[LEDGE] > 0 or x[WSIDE] != 0:
        return False
    if x[ATTACKING] > 0 and x[ATK_T] < P[P_ATK_REC]:
        return False
    if queue_wj_interrupt(x, P, TT):
        return False
    if x[VY] <= 0:                        # IsApproachingSolidGround: both bottom corners over a floor 1.1 u below
        bot = x[PY] - P[P_FOOT]
        if vray(x[PX] - P[P_HW], bot, P[P_GL_GRAY], TT) and vray(x[PX] + P[P_HW], bot, P[P_GL_GRAY], TT):
            return False
    return True


@njit(cache=True, error_model="numpy")
def can_dash(x, P):
    if (np.int64(P[P_ABIL]) & AB_DASH) == 0 or x[MODE] != M_NORMAL or x[DASH_CD] > 0:
        return False
    if x[ATTACKING] > 0 and x[ATK_T] < P[P_ATK_REC]:
        return False
    return x[GROUND] > 0 or x[AIRDASHED] <= 0 or x[WSIDE] != 0


@njit(cache=True, error_model="numpy")
def hero_dash(x, mask, P):
    """HeroDashPressed -> the wall scramble (sliding and holding towards the wall) or HeroDash. Not modelled (the
    press does nothing here): the down dash and the scuttle."""
    left = (mask & B_LEFT) != 0
    right = (mask & B_RIGHT) != 0
    if x[WSIDE] != 0 and ((x[WSIDE] < 0 and left) or (x[WSIDE] > 0 and right)):
        start_scramble(x, P)              # CanWallScramble: the Wall Scramble FSM
        return
    if (mask & B_DOWN) != 0 and x[GROUND] <= 0 and not left and not right:
        return
    x[ATTACKING] = 0.0
    x[WSLASH] = 0.0
    x[BOUNCE] = -1.0
    x[JUMPING] = 0.0
    x[JSTEPS] = 0.0
    if x[GROUND] > 0:
        x[DASH_T] = P[P_DASH_T]
    else:
        x[DASH_T] = P[P_ADASH_T]
        x[AIRDASHED] = 1.0
    if x[WSIDE] != 0:
        x[FACE] = -x[FACE]
    elif right and not left:
        x[FACE] = 1.0
    elif left and not right:
        x[FACE] = -1.0
    x[MODE] = M_DASH
    x[MODE_T] = 0.0
    x[DQ] = -1.0
    x[WLOCK] = -1.0
    x[DASH_CD] = P[P_DASH_CD]


@njit(cache=True, error_model="numpy")
def start_scramble(x, P):
    """Wall Scramble FSM: Take Control (control taken, the slide ends), Scramble Antic (v = 0, gravity off)."""
    side = x[WSIDE]
    relinquish_nv(x)
    x[MODE] = M_SCRAMBLE
    x[PHASE] = 0.0
    x[MODE_T] = 0.0
    x[SP_X] = side
    x[FACE] = side
    x[VX] = 0.0
    x[VY] = 0.0
    grav_off(x)


@njit(cache=True, error_model="numpy")
def finished_dashing(x, P):
    """FinishedDashing -> Sprint FSM TRY SPRINT -> Start Sprint (gravity 1, control taken) -> the air sprint or,
    on the ground, the sprint at the dash speed."""
    x[DASH_T] = 0.0
    grav_on(x)
    relinquish_nv(x)
    x[MODE] = M_SPRINT
    x[MODE_T] = 0.0
    if x[GROUND] > 0:
        x[PHASE] = 2.0
        x[SP_X] = x[FACE] * P[P_SPR_SPEED]
        x[VX] = x[FACE] * P[P_DASH_SPEED]
    else:
        x[PHASE] = 0.0
        x[SP_X] = x[FACE] * P[P_ASPR_SPEED]


@njit(cache=True, inline="always", error_model="numpy")
def sprint_translate(x, rx, ry, P):
    """Ground Sprint R / L OnEnter: Transform.Translate 0.05 u forward; the body follows the transform from where it
    was drawn (as the scramble's Detach): live, a released ground dash's last step moved 0.179 u at 26.9 u/s."""
    nx = rx + x[FACE] * P[P_SPR_SHIFT]
    x[PX] = nx
    x[QX] = nx
    x[SX] = nx
    x[PY] = ry
    x[QY] = ry
    x[SY] = ry


@njit(cache=True, inline="always", error_model="numpy")
def skid_factor(x, mask, P):
    mv = move_of(mask)
    return P[P_SKID_DEC_MV] if mv != 0 and mv == x[FACE] else P[P_SKID_DEC]


@njit(cache=True, inline="always", error_model="numpy")
def forum_fixed(x, vx, vy, normal, rx0, ry0, P, TT):
    """The Forum loadout's part of FixedUpdate before the terminal-velocity clamp and air hang (after the Hunter
    rules' own velocity of this step; rx0, ry0: where the body was drawn last frame, which a Transform.Translate in
    an FSM moves it from). Returns (vx, vy)."""
    mode = x[MODE]
    pm = np.int64(x[PREV])                # what FSM actions read in FixedUpdate: the previous frame's input
    if normal:
        if x[WJ_CHAIN] > 0:
            x[WJ_CHAIN] -= 1.0
        if x[WLOCK] >= 0:
            vx = x[WJ_DIR] * x[WJ_V]
            x[WLOCK] += 1.0
            if x[WLOCK] > P[P_WJ_LONG]:
                x[WLOCK] = -1.0
                x[WJ_CHAIN] = P[P_WJ_CHAIN]
            x[WJ_V] = x[WJ_V] - (P[P_WJ_SPEED] - P[P_RUN]) / P[P_WJ_LONG]
        if x[WSIDE] != 0:
            away = ((pm & B_RIGHT) != 0 and (pm & B_LEFT) == 0) if x[WSIDE] < 0 else \
                ((pm & B_LEFT) != 0 and (pm & B_RIGHT) == 0)
            x[UNSTICK] = x[UNSTICK] + 1.0 if away else 0.0
            if x[UNSTICK] >= P[P_W_STICKY]:
                x[FACE] = -x[FACE]
                cancel_wallslide(x)
            if x[WSIDE] != 0 and not wall_near(x[PX], x[PY], x[WSIDE], P[P_W_TRAY], P, TT):
                x[FACE] = -x[FACE]
                cancel_wallslide(x)
    elif mode == M_DASH:
        falling = x[VY] <= EPS_F and x[GROUND] <= 0
        if x[WTOUCH] != 0 and can_start_wallslide(x, falling, P, TT) and begin_wallslide(x, False, 0):
            return x[VX], x[VY]
        grav_off(x)
        if x[DASH_T] <= 0:
            finished_dashing(x, P)        # (Dash() leaves the velocity as it was)
            if x[MODE] == M_SPRINT:
                if x[PHASE] == 2:
                    sprint_translate(x, rx0, ry0, P)
                x[VX] = accel_to(x[VX], P[P_SPR_ACC], x[SP_X])   # Air / Ground Sprint: AccelerateToX OnEnter
            return x[VX], x[VY]
        vx = x[FACE] * P[P_DASH_SPEED]
        vy = 0.0
        x[DASH_T] = f32(x[DASH_T] - P[P_FDT])
    elif mode == M_SPRINT:
        ph = x[PHASE]
        vx = accel_to(vx, P[P_SPR_ACC], x[SP_X])
        if ph == 0:
            # Air Sprint: Fall Clamp eased linearly (easeType 21) from air_fall_clamp0 to air_fall_clamp1
            u = min(max(x[MODE_T] - P[P_AFC_LAG], 0.0) / P[P_AFC_T], 1.0)
            vy = max(vy, P[P_AFC0] + (P[P_AFC1] - P[P_AFC0]) * u)
        elif ph == 1:
            vy = max(vy, -P[P_MAXFALL])
        elif ph == 2:
            vx = min(max(vx, -40.0), 40.0)
        elif ph == 3:                     # Skid End 1 / 2: DecelerateXY 0.95 while moving the facing way, else 0.85
            vx = decel(x[VX], skid_factor(x, pm, P))
    elif mode == M_GLIDE:
        ph = x[PHASE]
        if ph == 0:
            vx = umbrella_x(vx, pm, P[P_GL_AACC], P[P_GL_DEC], P[P_GL_VMAX])
        elif ph == 1:                     # Inflate: SetVelocity2dConditional from the vector (0, 0) sets vy 0.5 every
            vy = P[P_GL_START_VY]         # step (its y test sees 0 < 0.05); the hero's UmbrellaWindObject keeps the
            vx = umbrella_x(vx, pm, P[P_GL_ACC], P[P_GL_DEC], P[P_GL_VMAX])   # own x speed UmbrellaMotionX drives
        elif ph == 2:
            vy = accel_to(vy, P[P_GL_VYACC], P[P_GL_VY])
            vx = umbrella_x(vx, pm, P[P_GL_ACC], P[P_GL_DEC], P[P_GL_VMAX])
    elif mode == M_RPR_DS:
        ph = x[PHASE]
        if ph == 0:                       # DecelerateV2 only: the state's DecelerateXY and UmbrellaMotionX are
            vx = decel(vx, P[P_RPR_ADEC])   # disabled in the template (actionEnabled false)
            vy = decel(vy, P[P_RPR_ADEC])
        elif ph == 1 or ph == 4:          # Rpr Downslash / Rpr Downslash Thunk: DecelerateV2
            f = P[P_RPR_SDEC] if ph == 1 else P[P_RPR_TDEC]
            vx = decel(vx, f)
            vy = decel(vy, f)
    elif mode == M_HARD_LAND:
        vx = 0.0
        vy = 0.0
    elif mode == M_SCRAMBLE:
        ph = x[PHASE]
        vx = 0.0
        if ph == 1:                       # AddForce2d down (mass 1), weaker while the dash is held
            vy = vy - (P[P_SCR_FORCE_H] if (pm & B_DASH) != 0 else P[P_SCR_FORCE]) * P[P_FDT]
        elif ph == 2:
            vy = decel(vy, P[P_SCR_END_DEC])
        if ph == 1 or ph == 2:
            # HeroCheckForBumpVertical (after the force / decel in the action list): the top wall ray, as long as
            # the velocity at the step's start covers, sends ROOF: Hit Roof (gravity back this step), Hit Roof Soft
            side = x[SP_X]
            reach = P[P_SCR_ROOF_RAY] + abs(x[VY]) * P[P_FDT]
            if roof_ray(x[PX] + side * (P[P_HW] - 0.2), x[PY] + P[P_HEAD], reach, TT,
                        (np.int64(P[P_ABIL]) & AB_SLOPES) != 0):
                x[PHASE] = 3.0
                x[MODE_T] = 0.0
                grav_on(x)
    if x[DQ] >= 0:
        x[DQ] += 1.0
    return vx, vy


@njit(cache=True, inline="always", error_model="numpy")
def forum_contacts(x, landed, P, TT):
    """After the step's move: OnCollisionStay2D's wall flags (only outside no_input: a contact with a wall within
    the skin, or the floor, refreshes them from the 0.1 u rays; no contact at all clears them, as OnCollisionExit),
    and a landing that was a hard one (DoHardLanding)."""
    mode = x[MODE]
    if mode == M_NORMAL or mode == M_DASH or mode == M_HARD_LAND:
        reach = P[P_SKIN] + P[P_W_CONTACT]
        gl, gr = wall_gaps(x[PX], x[PY], max(reach, P[P_W_TRAY]), P, TT)
        # OnCollisionStay2D refreshes the flags only for a contact that already existed in the step before (its
        # first step is OnCollisionEnter2D, which does not): a jump into a wall touches it a step after contact
        gnow = x[GROUND] > 0
        wnow = gl <= reach or gr <= reach
        prev = np.int64(x[WCON])
        x[WCON] = (1.0 if gnow else 0.0) + (2.0 if wnow else 0.0)
        stay = (gnow and (prev & 1) != 0) or (wnow and (prev & 2) != 0)
        if not (gnow or wnow):
            x[WTOUCH] = 0.0               # OnCollisionExit2D
        elif stay:
            if gl <= P[P_W_TRAY]:
                x[WTOUCH] = -1.0
            elif gr <= P[P_W_TRAY]:
                x[WTOUCH] = 1.0
            else:
                x[WTOUCH] = 0.0
            # the same callback lands a falling hero whose CheckTouchingGround rays (box left / centre / right, 0.16
            # below the box) see a floor, while the body is still above it (s98010 f695370: sliding down the wall,
            # "Land To Run" 0.11 u above the floor, the run starting in the next step)
            if mode == M_NORMAL and not gnow and wnow and x[VY] <= EPS_F:
                bot = x[PY] - P[P_FOOT]
                if vray(x[PX] - P[P_HW], bot, 0.16, TT) or vray(x[PX], bot, 0.16, TT) or                         vray(x[PX] + P[P_HW], bot, 0.16, TT):
                    x[GROUND] = 1.0       # BackOnGround
                    x[JUMPING] = 0.0
                    x[JSTEPS] = 0.0
                    x[LANDQ] = 1.0
    if landed and x[HARD] > 0 and (mode == M_NORMAL or mode == M_DASH or mode == M_SPRINT):
        x[MODE] = M_HARD_LAND
        x[MODE_T] = 0.0
        x[HARD] = 0.0
        x[VX] = 0.0
        x[VY] = 0.0
        x[ATTACKING] = 0.0
        x[DASH_T] = 0.0


@njit(cache=True, error_model="numpy")
def forum_fall_check(x, dt, P):
    """FallCheck at the start of Update: whether the hero is falling, and the hard-landing fall timer."""
    falling = x[VY] <= EPS_F and x[GROUND] <= 0
    if (np.int64(P[P_ABIL]) & AB_HARD_LAND) != 0:
        m = x[MODE]
        ctl = not relinq(m) or m == M_SPRINT
        if falling and ctl and x[VY] <= -P[P_MAXFALL] and x[WSIDE] == 0:
            x[FALL_T] = f32(x[FALL_T] + dt)
        else:
            x[FALL_T] = 0.0
        if x[FALL_T] > P[P_HARD_FALL]:
            x[HARD] = 1.0
    return falling


@njit(cache=True, error_model="numpy")
def forum_look_for_input(x, mask, pressed, falling, P, TT):
    """LookForInput's wall part (after the move input is read): start a slide when pressing into a touched wall,
    a down press drops off, pressing back after WJLOCK_STEPS_SHORT ends a wall jump's lock."""
    if x[MODE] != M_NORMAL:
        return
    ab = np.int64(P[P_ABIL])
    if (ab & AB_WALL) != 0 and x[WTOUCH] != 0 and x[ATTACKING] <= 0 and can_start_wallslide(x, falling, P, TT):
        begin_wallslide(x, True, mask)
    left = (mask & B_LEFT) != 0
    right = (mask & B_RIGHT) != 0
    if x[WSIDE] != 0 and (pressed & B_DOWN) != 0 and not (x[WTOUCH] < 0 and left) and not (x[WTOUCH] > 0 and right):
        cancel_wallslide(x)
        x[FACE] = -x[FACE]
    if x[WLOCK] >= P[P_WJ_SHORT] and ((x[WJ_DIR] < 0 and right) or (x[WJ_DIR] > 0 and left)):
        x[WLOCK] = -1.0


@njit(cache=True, error_model="numpy")
def forum_jump_press(x, mask, pressed, P, TT):
    """LookForQueueInput's jump part that the Hunter rules do not have: a queued wall-jump interrupt, a wall jump,
    the glide, and the interrupt queue. Returns True when the press (or the queue) was used here."""
    if x[MODE] != M_NORMAL:
        return False
    ab = np.int64(P[P_ABIL])
    if x[WJQ] > 0:
        x[WJQ] = 0.0
        if (ab & AB_WALL) != 0:             # TryDoWallJumpFromMove: CanWallJump(false), ForceTouchingWall
            x[WTOUCH] = x[FACE]
            do_wall_jump(x, P)
        return True
    if (pressed & B_JUMP) == 0:
        return False
    if (ab & AB_WALL) != 0 and (x[WSIDE] != 0 or (x[WTOUCH] != 0 and x[GROUND] <= 0 and chain_ok(x))):
        do_wall_jump(x, P)
        return True
    can_jump = x[JUMPING] <= 0 and x[BOUNCE] < 0 and x[DS_REC] < 0 and (x[GROUND] > 0 or x[LEDGE] > 0)
    if can_jump:
        return False
    if x[WLOCK] < 0 and can_float(x, P, TT):
        start_glide(x, mask, P)
        return True
    return queue_wj_interrupt(x, P, TT)


@njit(cache=True, error_model="numpy")
def forum_dash_input(x, mask, pressed, P):
    """LookForQueueInput's dash part: a press, or a queued one (DASH_QUEUE_STEPS) still held."""
    if (np.int64(P[P_ABIL]) & AB_DASH) == 0:
        return
    if (mask & B_DASH) == 0:
        x[DQ] = -1.0                      # LookForInput: released -> not queuing
        return
    if (pressed & B_DASH) != 0:
        if can_dash(x, P):
            hero_dash(x, mask, P)
        else:
            x[DQ] = 0.0
    elif 0 <= x[DQ] <= P[P_DQ] and can_dash(x, P):
        hero_dash(x, mask, P)


@njit(cache=True, error_model="numpy")
def forum_after_queue(x, mask, pressed, mode0, dt, P, TT):
    """After LookForQueueInput: the wall slide checks and the cling, the FSM-driven moves' Update side (phase
    timers and transitions), cooldowns, and LateUpdate's wall velocity."""
    ab = np.int64(P[P_ABIL])
    if x[WSIDE] != 0:
        x[AIRDASHED] = 0.0
        if x[GROUND] > 0 or x[WTOUCH] == 0:
            x[FACE] = -x[FACE]
            cancel_wallslide(x)
        elif x[MODE] != M_NORMAL or not can_start_wallslide(x, True, P, TT):
            cancel_wallslide(x)
        if x[WSIDE] != 0:
            was = x[CLING] > 0
            mv = move_of(mask)
            cl = (x[CLING_CD] <= 0 and (ab & AB_CLING) != 0
                  and ((x[WSIDE] < 0 and mv < 0) or (x[WSIDE] > 0 and mv > 0)))
            x[CLING] = 1.0 if cl else 0.0
            if cl:
                grav_off(x)
            elif was:
                x[CLING_CD] = P[P_W_CCD]
    else:
        x[WSTICK] = 0.0
        if x[WSLASH] > 0:                 # CancelAttack
            x[WSLASH] = 0.0
            x[ATTACKING] = 0.0
    # cooldowns (Update)
    if x[CLING_CD] > 0:
        x[CLING_CD] = f32(x[CLING_CD] - dt)
    if x[DASH_CD] > 0:
        x[DASH_CD] = f32(x[DASH_CD] - dt)
    if x[GL_CD] > 0:
        x[GL_CD] = f32(x[GL_CD] - dt)
    mode = x[MODE]
    if mode0 == mode and (mode == M_GLIDE or mode == M_SPRINT or mode == M_RPR_DS or mode == M_HARD_LAND
                          or mode == M_SCRAMBLE):
        x[MODE_T] = f32(x[MODE_T] + dt)
    if mode == M_GLIDE:
        ph = x[PHASE]
        if x[GROUND] > 0:                 # LAND -> Land -> Relinquish Control
            regain_jump(x, mask, P)
            x[GL_CD] = P[P_GL_CD]
        elif ph == 0 and ge32(x[MODE_T], P[P_GL_ANTIC]):
            x[PHASE] = 1.0                # Damager? -> Inflate: gravity off, v = (0, 0.5) OnEnter, then UmbrellaMotionX
            x[MODE_T] = 0.0               # OnEnter takes its own x speed from that 0 (live: 0, then -2, -3 ... -8.5)
            grav_off(x)
            x[VY] = P[P_GL_START_VY]
            x[VX] = umbrella_x(0.0, mask, P[P_GL_ACC], P[P_GL_DEC], P[P_GL_VMAX])
        elif ph == 1 and ge32(x[MODE_T], P[P_GL_INFLATE]):
            x[PHASE] = 2.0                # Start (vy 0.5) -> Float Idle (AccelerateToY, UmbrellaMotionX OnEnter)
            x[MODE_T] = 0.0
            x[VY] = accel_to(P[P_GL_START_VY], P[P_GL_VYACC], P[P_GL_VY])
            x[VX] = umbrella_x(x[VX], mask, P[P_GL_ACC], P[P_GL_DEC], P[P_GL_VMAX])
        elif (ph == 2 or ph == 5) and (mask & B_JUMP) == 0:
            x[PHASE] = 3.0                # END -> Deflate: gravity back
            x[MODE_T] = 0.0
            grav_on(x)
        elif ph == 5:
            x[PHASE] = 2.0                # Bump L / R -> Float Idle (AccelerateToY, UmbrellaMotionX from the next step)
            x[MODE_T] = 0.0
        elif ph == 3 and ge32(x[MODE_T], P[P_GL_DEFLATE]):
            regain_jump(x, mask, P)
            x[GL_CD] = P[P_GL_CD]
        if x[MODE] == M_GLIDE and (x[PHASE] == 2 or (x[PHASE] == 1 and x[MODE_T] >= 0.075) or x[PHASE] == 3
                                   or x[PHASE] == 5):
            if (pressed & B_ATTACK) != 0 or ((pressed & B_DASH) != 0 and (ab & AB_DASH) != 0):
                regain(x, mask)           # Attack Cancel / Dash Cancel: control back, the press acts this frame
                x[GL_CD] = P[P_GL_CD]
        if x[MODE] == M_GLIDE and (x[PHASE] == 1 or x[PHASE] == 2):
            rx, ry = rend_x(x), rend_y(x)
            bl = hray(rx, ry, -1.0, P[P_GL_BRAY], TT)
            br = hray(rx, ry, 1.0, P[P_GL_BRAY], TT)
            if bl != br:                  # Bump L / R: into a wall slide, or pushed off the wall
                side = -1.0 if bl else 1.0
                toward = (mask & (B_LEFT if bl else B_RIGHT)) != 0
                if (ab & AB_WALL) != 0 and toward:
                    regain(x, mask)       # SetStartWithWallslide: the slide starts from the touch
                    x[FACE] = side
                    x[GL_CD] = P[P_GL_CD]
                else:
                    x[VX] = -side * P[P_GL_BVX]
                    if bl:
                        x[VY] = min(x[VY], -0.5)
                    # the Bump state: no velocity action of its own; a release goes on to Deflate from it (s98000
                    # f405707: pushed off the right wall in the inflate, released a frame later: vy kept 0.5, then
                    # gravity)
                    x[PHASE] = 5.0
                    x[MODE_T] = 0.0
    elif mode == M_SPRINT:
        ph = x[PHASE]
        if ph == 0 and ge32(x[MODE_T], P[P_ASPR_T]):
            x[PHASE] = 1.0
        ph = x[PHASE]
        wall = wall_near(x[PX], x[PY], x[FACE], P[P_SKIN] + P[P_W_CONTACT], P, TT)
        if ph <= 1:
            if x[GROUND] > 0:             # LAND -> Land: sprint on if the dash is held
                if (mask & B_DASH) != 0:
                    x[PHASE] = 2.0
                    x[MODE_T] = 0.0
                    x[SP_X] = x[FACE] * P[P_SPR_SPEED]
                    # LAND comes from the landing step's collision callback, where the transform sits at the body
                    # (live: the landing frame moved the step's 17.0 u/s x 0.02 + 0.05)
                    sprint_translate(x, x[PX], x[PY], P)
                    x[VX] = accel_to(x[VX], P[P_SPR_ACC], x[SP_X])
                else:
                    regain_jump(x, mask, P)
            elif wall or (ph == 1 and (mask & B_DASH) == 0):
                regain_jump(x, mask, P)   # END
            elif (pressed & (B_ATTACK | B_JUMP)) != 0:
                regain(x, mask)           # Attack Cancel / Queue Sprint Jump: control back, the press acts
        elif ph == 2:
            if (mask & B_DASH) == 0:      # released: SKID END
                if not ge32(x[MODE_T], P[P_SPR_GRACE]) or abs(x[VX]) < P[P_SKID_VMIN]:
                    regain_jump(x, mask, P)   # Sprint Timer under Sprint Grace (or slower than 4): no skid, Regain
                else:                     # Control To Idle
                    x[PHASE] = 3.0        # Skid End 1 (DecelerateXY OnEnter)
                    x[MODE_T] = 0.0
                    x[VX] = decel(x[VX], skid_factor(x, mask, P))
            elif x[GROUND] <= 0:
                x[PHASE] = 0.0            # Allow Air Jump -> Air Sprint (the ground target speed kept)
                x[MODE_T] = 0.0
            elif (pressed & (B_ATTACK | B_JUMP)) != 0 or wall:
                regain(x, mask)
        elif ph == 3 and ge32(x[MODE_T], P[P_SKID_T]):
            regain_jump(x, mask, P)
    elif mode == M_RPR_DS:
        ph = x[PHASE]
        if ph == 0 and ge32(x[MODE_T], P[P_RPR_ANTIC]):
            x[PHASE] = 1.0                # Rpr Downslash: v = 0, then SetVelocityByScale (forward, down)
            x[MODE_T] = 0.0
            x[VX] = x[FACE] * P[P_RPR_SPEED]
            x[VY] = -P[P_RPR_SPEED]
        elif (ph == 1 or ph == 4) and ge32(x[MODE_T], P[P_RPR_SLASH]):
            x[PHASE] = 2.0                # Fall (the same clip trigger ends the Thunk): gravity back
            x[MODE_T] = 0.0
            grav_on(x)
        elif ph == 2 and ge32(x[MODE_T], P[P_RPR_FALL]):
            x[PHASE] = 3.0
            x[MODE_T] = 0.0
        elif ph == 3 and ge32(x[MODE_T], P[P_RPR_FALL2]):
            regain(x, mask)               # End (FinishDownspike: the downspike recovery starts, ResetGravity,
            x[DS_REC] = 0.0               # vy = -10)
            x[GS] = 1.0
            x[VY] = P[P_DS_ENDVY]
        if x[MODE] == M_RPR_DS and (x[PHASE] == 2 or x[PHASE] == 3) and (pressed & B_DASH) != 0 and \
                (ab & AB_DASH) != 0:
            regain(x, mask)               # Rpr DashCancel
    elif mode == M_SCRAMBLE:
        ph = x[PHASE]
        side = x[SP_X]
        if ph == 0 and ge32(x[MODE_T], P[P_SCR_ANTIC]):
            x[PHASE] = 1.0                # Start Scramble: vy up; Scramble Up's AddForce2d OnEnter adds to the next
            x[MODE_T] = 0.0               # step's force (VY carries it from here)
            x[VY] = P[P_SCR_SPEED] - (P[P_SCR_FORCE_H] if (mask & B_DASH) != 0 else P[P_SCR_FORCE]) * P[P_FDT]
            # HeroCheckForBumpVertical's OnEnter, in this Update, with the start speed in the ray: a roof within
            # reach is Hit Roof now, its End clip timed from this frame as a FixedUpdate entry's (run A s98010:
            # f696151 / f716016 detached 5 frames after the start frame, as the FixedUpdate roofs)
            if roof_ray(x[PX] + side * (P[P_HW] - 0.2), x[PY] + P[P_HEAD],
                        P[P_SCR_ROOF_RAY] + P[P_SCR_SPEED] * P[P_FDT], TT, (ab & AB_SLOPES) != 0):
                x[PHASE] = 3.0
                x[MODE_T] = f32(dt)
                grav_on(x)
        elif (ph == 1 or ph == 2) and (pressed & B_JUMP) != 0:
            regain(x, mask)               # Wall Jump: SetStartWithWallJump, control back
            x[WTOUCH] = side
            do_wall_jump(x, P)
        elif ph == 1 and (pressed & B_DASH) != 0 and ((side < 0 and (mask & B_LEFT) != 0) or
                                                   (side > 0 and (mask & B_RIGHT) != 0)):
            x[PHASE] = 0.0                # REPEAT DASH from Scramble Up as from End (s98000 f419074: vy 1.84 -> antic)
            x[MODE_T] = 0.0
            x[VX] = 0.0
            x[VY] = 0.0
        elif ph == 1 and x[VY] < P[P_SCR_END_VY]:
            x[PHASE] = 2.0                # Scramble End (DecelerateXY OnEnter)
            x[MODE_T] = 0.0
            x[VY] = decel(x[VY], P[P_SCR_END_DEC])
        elif ph == 1 and not facing_near_wall(rend_x(x), rend_y(x), side, P[P_W_RAY], TT):
            regain(x, mask)               # MANTLE over the top (the Mantle FSM is not modelled)
        elif ph == 2 and ge32(x[MODE_T], P[P_SCR_END_T]):
            regain(x, mask)               # To Wall Slide: control back, sliding from the touch; brakeOnExit: vy 0
            x[VY] = 0.0
            x[WTOUCH] = side
            begin_wallslide(x, False, 0)
        elif ph == 2 and (pressed & B_DASH) != 0 and ((side < 0 and (mask & B_LEFT) != 0) or
                                                   (side > 0 and (mask & B_RIGHT) != 0)):
            x[PHASE] = 0.0                # REPEAT DASH: Scramble Antic again
            x[MODE_T] = 0.0
            x[VX] = 0.0
            x[VY] = 0.0
        elif ph == 3 and ge32(x[MODE_T], P[P_SCR_ROOF_T]):
            # Detach: Translate x by scale.x * 0.2 (scale.x = -facing) moves the transform from where it is
            # drawn, and the body follows it (the logged box jumps to the interpolated height), then Return Control
            # (gravity stays on, no wall slide)
            nx = rend_x(x) - side * P[P_SCR_DETACH]
            ny = rend_y(x)
            x[PX] = nx
            x[QX] = nx
            x[SX] = nx
            x[PY] = ny
            x[QY] = ny
            x[SY] = ny
            regain_jump(x, mask, P)
    elif mode == M_HARD_LAND:
        if gt32(x[MODE_T], P[P_HARD_LAND]):
            x[MODE] = M_NORMAL
            x[MODE_T] = 0.0
    # LateUpdate: the wall slide's own vertical velocity (per rendered frame)
    if x[WSIDE] != 0:
        vy = x[VY]
        if x[CLING] > 0:
            if vy < P[P_W_CVMIN]:
                vy = P[P_W_CVMIN]
            if vy < 0:
                vy = f32(vy + P[P_W_CDECEL] * dt)
            elif vy > 0:
                vy = 0.0
            x[WSTICK] = 0.0
        elif x[WSTICK] < P[P_W_STICK]:
            vy = 0.0
            x[WSTICK] = f32(x[WSTICK] + dt)
        else:
            vy = f32(vy + P[P_W_ACCEL] * dt)
        x[VY] = vy


@njit(cache=True, error_model="numpy")
def forum_attack(x, mask, P):
    """Attack's wall and Reaper parts, after DoAttack decided the direction: a side slash while wall sliding is the
    wall slash (Reaper: vy halved, at least -5; the slide goes on), an up slash shoves 0.8 u off the wall and ends
    the slide, a down attack ends it; the Reaper down attack is the Crest Attacks FSM's Rpr Downslash. Returns True
    when it started the Reaper down slash."""
    ab = np.int64(P[P_ABIL])
    up = (mask & B_UP) != 0
    down = not up and (mask & B_DOWN) != 0 and x[GROUND] <= 0
    if x[WSIDE] != 0:
        if not up and not down:
            if (ab & AB_WALLSLASH_SLOW) != 0:
                x[VY] = x[VY] / 2.0
                if x[VY] < P[P_W_SLASH_VMIN]:
                    x[VY] = P[P_W_SLASH_VMIN]
            x[WSLASH] = 1.0
        else:
            if up:                        # MovePosition 0.8 u off the wall: done by the next physics step
                x[SHOVE] = -x[FACE] * P[P_W_SHOVE]
            x[FACE] = -x[FACE]
            cancel_wallslide(x)
    if down and (ab & AB_RPR_DOWN) != 0:
        relinquish_nv(x)
        grav_off(x)
        x[MODE] = M_RPR_DS
        x[PHASE] = 0.0
        x[MODE_T] = 0.0
        x[VX] = decel(x[VX], P[P_RPR_ADEC])   # Rpr Downslash Antic OnEnter: DecelerateV2 once
        x[VY] = decel(x[VY], P[P_RPR_ADEC])
        return True
    return False


# ---- one physics step, contact events, one Update ---------------------------------------------------------------

@njit(cache=True, inline="always", error_model="numpy")
def fixed_step(x, P, TT):
    fdt = P[P_FDT]
    hw = P[P_HW]
    skin = P[P_SKIN]
    foot = P[P_FOOT]
    head = P[P_HEAD]
    rx0 = x[RX0]
    ry0 = x[RY0]
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

    ab = np.int64(P[P_ABIL])
    mv = 0.0 if (x[DS_REC] >= 0 and x[GROUND] > 0) else x[MOVE]
    vx = mv * P[P_RUN] if normal else x[VX]
    can_turn = normal and not (x[ATTACKING] > 0 and x[ATK_T] < P[P_ATK_REC])
    if ab != 0 and normal and (x[WSIDE] != 0 or x[WLOCK] >= 0):
        can_turn = False                  # DoMovement: no turning while wall sliding or wall locked
        if x[WSIDE] != 0:
            vx = x[VX]                    # Move: no input velocity while wall sliding
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
        if ab != 0:
            x[WLOCK] = -1.0               # Jump() past JUMP_STEPS: CancelJump ends a wall jump's lock too
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
    if ab != 0:
        if mode != M_NORMAL or x[WSIDE] != 0 or x[WLOCK] >= 0 or x[WJ_CHAIN] > 0 or x[DQ] >= 0:
            vx, vy = forum_fixed(x, vx, vy, mode == M_NORMAL, rx0, ry0, P, TT)
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
    if ab != 0 and x[WSIDE] != 0:
        ctl = False                       # gravity scale is left alone while wall sliding
    gs = x[GS]
    if ctl and gs < 1.0:
        gs = gs + P[P_AH_ACC] * fdt
    if ctl and gs < 1.0 and x[JHELD] <= 0:
        gs = 1.0
    x[GS] = min(gs, 1.0)
    x[LEDGE] = max(x[LEDGE] - 1, 0.0)

    shove = 0.0
    sv_x = 0.0
    sv_y = 0.0
    if ab != 0 and x[SHOVE] != 0:
        # rb2d.MovePosition: this step moves the body by the offset (plus gravity's share in y) instead of its
        # velocity, which the step then leaves as it was (live: x -0.8 exactly, y -g fdt^2, vy still 0)
        shove = x[SHOVE]
        x[SHOVE] = 0.0
        sv_x, sv_y = vx, vy
        vx = shove / fdt
        vy = 0.0
    vy = vy - P[P_G] * x[GS] * fdt
    roof0 = False
    if (ab & AB_SLOPES) != 0:
        vx, vy = slope_project(x[PX], x[PY], vx, vy, P, TT)
        if vy > 0 and roof_touch(x[PX], x[PY], P, TT):
            vy = 0.0                      # the contact the last step parked at (below)
            roof0 = True
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
    if bumped and (ab & AB_SLOPES) != 0 and x[PY] + vy * fdt <= ny + skin - P[P_SLOPE_CONTACT]:
        # a rise that ends just short of a ceiling (closer than the skin, not within Box2D's slop) parks there with
        # its velocity: the contact is made in the next step (as the late floor contacts, land_slop; live s98010
        # f708617: a scramble's top 0.0099 u under the ceiling, vy 16.96 kept, 0 a step later)
        ny = x[PY] + vy * fdt
        bumped = False
    if landed or bumped:
        vy = 0.0
    if (ab & AB_SLOPES) != 0:
        nx, ny, vx, vy, sc = slope_push(x[PX], x[PY], nx, ny, vx, vy, P, TT)
        bumped = bumped or sc == 1 or roof0
        if bumped and not noinp:
            # OnCollisionEnter2D, side top (normal y <= -0.5): CancelJump (the rise does not press on into the roof)
            x[JUMPING] = 0.0
            x[JSTEPS] = 0.0
            x[WLOCK] = -1.0
    if shove != 0:
        vx, vy = sv_x, sv_y
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
    if (lands or land_sp) and not was:
        x[LANDQ] = 1.0
    if ab != 0:
        if (ab & AB_WALL) != 0 or (lands and x[HARD] > 0):
            forum_contacts(x, lands, P, TT)
        if x[MODE] == M_RPR_DS and x[PHASE] == 1 and rpr_thunk(x, P, TT):
            x[PHASE] = 4.0                # THUNKED DOWN in the step's collision: Rpr Downslash Thunk, DecelerateV2
            x[VX] = decel(x[VX], P[P_RPR_TDEC])   # OnEnter (the step's own x0.7 already done)
            x[VY] = decel(x[VY], P[P_RPR_TDEC])
        if (ab & AB_THUNK) != 0 and x[ATK_KIND] > 0:
            thunk_step(x, P, TT)


@njit(cache=True, inline="always", error_model="numpy")
def lerp32(a, b, t):
    t = min(max(t, 0.0), 1.0)
    a32, b32 = np.float32(a), np.float32(b)
    return np.float64(a32 + (b32 - a32) * np.float32(t))


@njit(cache=True, inline="always", error_model="numpy")
def wf_start(x, down, wait, up, tgt):
    x[WF_DOWN] = down
    x[WF_WAIT] = wait
    x[WF_UP] = up
    x[WF_TGT] = tgt
    x[WF_T] = 0.0
    if down > 0:
        x[WF_PH] = 10.0
        x[WF_S] = 1.0
    else:
        x[WF_PH] = 11.0
        x[WF_S] = f32(tgt)


@njit(cache=True, inline="always", error_model="numpy")
def wf_step(x, udt, P):
    ph = x[WF_PH]
    if ph >= 10:
        x[WF_PH] = ph - 10
        return
    if ph < 0:
        return
    t = f32(x[WF_T] + udt)
    tgt = x[WF_TGT]
    if ph == 0:
        if np.float32(t) < np.float32(x[WF_DOWN]):
            x[WF_S] = lerp32(1.0, tgt, t / max(x[WF_DOWN], 1e-12))
            x[WF_T] = t
        else:
            x[WF_S] = f32(tgt)
            x[WF_T] = 0.0
            x[WF_PH] = 1.0
    elif ph == 1:
        if ge32(t, x[WF_WAIT] + P[P_WF_BW]):
            x[WF_T] = 0.0
            if x[WF_UP] <= 0:
                x[WF_S] = 1.0
                x[WF_PH] = -1.0
            else:
                x[WF_S] = f32(tgt)
                x[WF_PH] = 2.0
        else:
            x[WF_T] = t
    elif ph == 2:
        if ge32(t, x[WF_UP] + P[P_WF_BU]):
            x[WF_S] = 1.0
            x[WF_PH] = -1.0
            x[WF_T] = t
        else:
            x[WF_S] = lerp32(tgt, 1.0, t / max(x[WF_UP], 1e-12))
            x[WF_T] = t


@njit(cache=True, inline="always", error_model="numpy")
def apply_events(x, ev, P):
    mode = x[MODE]
    bb = (ev & (EV_HURT_L | EV_HURT_R)) != 0 and mode == M_BIND and x[MODE_T] < P[P_BIND_BREAK]
    for j in range(_WF.shape[0]):
        bit = np.int64(_WF[j, 0])
        if (ev & bit) != 0 or (bb and bit == _WF_BB):
            wf_start(x, _WF[j, 1], _WF[j, 2], _WF[j, 3], _WF[j, 4])
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
        x[INV_T] = max(x[INV_T], P[P_POGO_INV])
    for b in range(2):
        bit = EV_HURT_L if b == 0 else EV_HURT_R
        side = -1.0 if b == 0 else 1.0
        if (ev & bit) != 0:
            if P[P_ABIL] != 0:            # the damage ends a wall slide, a glide, a dash or an FSM move
                cancel_wallslide(x)
                x[WLOCK] = -1.0
                x[DASH_T] = 0.0
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


@njit(cache=True, inline="always", error_model="numpy")
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


@njit(cache=True, inline="always", error_model="numpy")
def do_attack(x, mask, P):
    want = 1.0 if (mask & B_RIGHT) != 0 else (-1.0 if (mask & B_LEFT) != 0 else 0.0)
    if want != 0:
        x[FACE] = want
    if (np.int64(P[P_ABIL]) & AB_THUNK) != 0:
        forum_swing(x, mask, P)
    if P[P_ABIL] != 0 and forum_attack(x, mask, P):
        x[ATK_T] = 0.0                    # Reaper down slash: DidAttack's cooldown, the FSM has control
        x[ATK_CD] = P[P_ATK_CD]
        x[AQ] = -1.0
        return
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


@njit(cache=True, inline="always", error_model="numpy")
def update(x, mask, ev, dt, udt, P, TT):
    mode = x[MODE]
    mode0 = mode
    prev = np.int64(x[PREV])
    pressed = mask & ~prev
    normal = mode == M_NORMAL
    accept = normal or noinput(mode)
    ab = np.int64(P[P_ABIL])
    falling = False
    if ab != 0:
        if (ab & AB_THUNK) != 0:
            x[ALT_T] = f32(x[ALT_T] + dt)  # Time.timeSinceLevelLoad - altAttackTime
        if (pressed & B_JUMP) != 0:       # InputHandler.UpdateButtonQueueing (before the hero's Update)
            x[JBUF] = 0.1
        elif x[JBUF] > 0:
            x[JBUF] = f32(x[JBUF] - udt)
        falling = x[VY] <= EPS_F and x[GROUND] <= 0
        if (ab & AB_HARD_LAND) != 0:
            forum_fall_check(x, dt, P)
        if mode == M_DASH or mode == M_HARD_LAND:
            accept = True                 # hero_state is not no_input: LookForInput reads the move input

    move = (1.0 if (mask & B_RIGHT) != 0 else 0.0) - (1.0 if (mask & B_LEFT) != 0 else 0.0)
    jheld = (mask & B_JUMP) != 0
    if accept:
        x[MOVE] = move
        x[JHELD] = 1.0 if jheld else 0.0
        if ab != 0:
            if x[WTOUCH] != 0 or x[WSIDE] != 0 or x[WLOCK] >= 0:
                forum_look_for_input(x, mask, pressed, falling, P, TT)
        if not jheld:
            if x[VY] > 0 and x[JDSTEPS] >= P[P_JSTEPS_MIN]:
                x[VY] = x[VY] * P[P_REL]
                x[JUMPING] = 0.0
                x[JSTEPS] = 0.0
                if ab != 0:
                    x[WLOCK] = -1.0       # CancelJump ends a wall jump's lock
            x[JQ] = -1.0
        if (mask & B_ATTACK) == 0:
            x[AQ] = -1.0
        if (mask & B_QUICKCAST) == 0:
            x[QQ] = -1.0
    if x[LANDQ] > 0 and x[MOVE] == 0:
        x[DS_REC] = -1.0
    x[LANDQ] = 0.0

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
            if ab != 0:
                x[WSLASH] = 0.0           # ResetAttacks

    used = False
    if ab != 0:
        if (pressed & B_JUMP) != 0 or x[WJQ] > 0:
            used = forum_jump_press(x, mask, pressed, P, TT)
    normal = x[MODE] == M_NORMAL
    ground = x[GROUND] > 0
    can_jump = normal and x[JUMPING] <= 0 and x[BOUNCE] < 0 and x[DS_REC] < 0 and (ground or x[LEDGE] > 0)
    jp = (pressed & B_JUMP) != 0 and not used
    if jp and not can_jump:
        x[JQ] = 0.0
    if jp and can_jump:
        hero_jump(x, P)
    if ab != 0:
        if (ab & AB_DASH) != 0 and ((mask & B_DASH) != 0 or x[DQ] >= 0):
            forum_dash_input(x, mask, pressed, P)
        normal = x[MODE] == M_NORMAL
    downish = (mask & B_DOWN) != 0 and (mask & B_UP) == 0
    can_down = x[BOUNCE] < 0 and x[DS_REC] < 0
    bind_first = normal and (pressed & B_BIND) != 0 and x[SILK] >= P[P_BIND_SILK]
    can_attack = normal and x[ATTACKING] <= 0 and x[ATK_CD] <= 0 and (not downish or can_down) and not bind_first
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
        if ab != 0:
            cancel_wallslide(x)
            x[WLOCK] = -1.0
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
    can_attack = normal and x[ATTACKING] <= 0 and x[ATK_CD] <= 0 and (not downish or can_down) and not bind_first
    if normal and (mask & B_ATTACK) != 0 and x[AQ] >= 0 and x[AQ] <= P[P_AQ] and can_attack:
        do_attack(x, mask, P)
    normal = x[MODE] == M_NORMAL
    if normal and (pressed & B_BIND) != 0 and x[SILK] >= P[P_BIND_SILK]:
        if ab != 0:
            cancel_wallslide(x)
            x[WLOCK] = -1.0
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
    if ab != 0:
        if (x[WSIDE] != 0 or x[WSLASH] > 0 or x[WSTICK] > 0 or x[CLING_CD] > 0 or x[DASH_CD] > 0 or x[GL_CD] > 0
                or x[MODE] >= M_GLIDE):
            forum_after_queue(x, mask, pressed, mode0, dt, P, TT)

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
    wf_step(x, udt, P)


@njit(cache=True, inline="always", error_model="numpy")
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
# Lane i runs command sequence r = i // V under variant v = i % V. Inputs broadcast instead of being copied per lane:
# S0 [K, n] or [K, 1]; events [n, T] or [0, 0] (none); udts [1 or n, 1 or T]; dts / fss [n, T] (logged timing) or
# [0, 0]; per variant v: P[v] (parameter row), ft_v[v] (> 0: that unscaled frame time for every frame) and
# alpha_sel[v] (0 the estimate, 1 the low end of the phase interval minus alpha_margin, 2 the high end plus it).

@njit(cache=True, error_model="numpy")
def lane(i, V, S0, masks, events, dts, fss, udts, ft_v, alpha_sel, alpha_margin, P, TT,
         phys, rend, vel, modes, flags, box, final, nob, nof):
    run_lane(i // V, i % V, i, S0, masks, events, dts, fss, udts, ft_v, alpha_sel, alpha_margin, P, TT,
             phys, rend, vel, modes, flags, box, final, nob, nof, nof)


@njit(cache=True, error_model="numpy")
def run_lane(r, v, o, S0, masks, events, dts, fss, udts, ft_v, alpha_sel, alpha_margin, P, TT,
             phys, rend, vel, modes, flags, box, final, bound, f_all, f_any):
    """Command sequence r under variant v. o >= 0: write the full per-frame outputs to row o; bound / f_all / f_any
    with rows: fold this lane's box into bound[r] (min / max) and its flags into f_all[r] (AND) / f_any[r] (OR)."""
    x = S0[:, r if S0.shape[1] > 1 else 0].copy()
    if alpha_sel[v] == 1:
        x[ALPHA] = max(x[ALO] - alpha_margin, 0.0)
    elif alpha_sel[v] == 2:
        x[ALPHA] = x[AHI] + alpha_margin
    p = P[v] if P.shape[0] > 1 else P[0]
    T = masks.shape[1]
    logged = dts.shape[1] == T and T > 0
    has_ev = events.shape[0] > 0
    ur = r if udts.shape[0] > 1 else 0
    uc = udts.shape[1] > 1
    fdt = p[P_FDT]
    hw, foot, head = p[P_HW], p[P_FOOT], p[P_HEAD]
    for t in range(T + 1):
        if t > 0:
            m = masks[r, t - 1]
            ev = events[r, t - 1] if has_ev else np.int64(0)
            udt = ft_v[v] if ft_v[v] > 0 else udts[ur, t - 1 if uc else 0]
            if p[P_ABIL] != 0:            # the drawn position this frame's FixedUpdates start from
                x[RX0] = x[QX] + x[ALPHA] * (x[SX] - x[QX])
                x[RY0] = x[QY] + x[ALPHA] * (x[SY] - x[QY])
            if logged:
                dt = dts[r, t - 1]
                steps = np.int64(fss[r, t - 1])
                x[ALPHA] = x[ALPHA] + dt / fdt - steps
            else:
                dt = f32(udt * (x[TS] if x[WF_S] == 1.0 else x[TS] * x[WF_S]))
                a = x[ALPHA] + dt / fdt
                steps = np.int64(math.floor(a + 1e-9))
                x[ALPHA] = a - steps
            x[ALPHA] = min(max(x[ALPHA], 0.0), 1.0)
            for _ in range(steps):
                fixed_step(x, p, TT)
            apply_events(x, ev, p)
            update(x, m, ev, dt, udt, p, TT)
        fl = flags_of(x)
        if o >= 0:
            phys[o, t, 0] = x[PX]
            phys[o, t, 1] = x[PY]
            rend[o, t, 0] = x[QX] + x[ALPHA] * (x[SX] - x[QX])
            rend[o, t, 1] = x[QY] + x[ALPHA] * (x[SY] - x[QY])
            vel[o, t, 0] = x[VX]
            vel[o, t, 1] = x[VY]
            modes[o, t] = np.int32(x[MODE])
            flags[o, t] = fl
            box[o, t, 0] = x[PX] - hw
            box[o, t, 1] = x[PY] - foot
            box[o, t, 2] = x[PX] + hw
            box[o, t, 3] = x[PY] + head
        if bound.shape[0] > 0:
            bound[r, t, 0] = min(bound[r, t, 0], x[PX] - hw)
            bound[r, t, 1] = min(bound[r, t, 1], x[PY] - foot)
            bound[r, t, 2] = max(bound[r, t, 2], x[PX] + hw)
            bound[r, t, 3] = max(bound[r, t, 3], x[PY] + head)
            f_all[r, t] &= fl
            f_any[r, t] |= fl
    if o >= 0:
        final[:, o] = x


@njit(cache=True, error_model="numpy")
def _alloc(nl, T, K):
    return (np.empty((nl, T + 1, 2)), np.empty((nl, T + 1, 2)), np.empty((nl, T + 1, 2)),
            np.empty((nl, T + 1), dtype=np.int32), np.empty((nl, T + 1), dtype=np.int32), np.empty((nl, T + 1, 4)),
            np.empty((K, nl)))


@njit(cache=True, error_model="numpy")
def simulate(S0, masks, events, dts, fss, udts, ft_v, alpha_sel, alpha_margin, P, TT):
    V = ft_v.shape[0]
    nl = masks.shape[0] * V
    phys, rend, vel, modes, flags, box, final = _alloc(nl, masks.shape[1], S0.shape[0])
    nob, nof = np.zeros((0, 1, 4)), np.zeros((0, 1), dtype=np.int32)
    for i in range(nl):
        lane(i, V, S0, masks, events, dts, fss, udts, ft_v, alpha_sel, alpha_margin, P, TT,
             phys, rend, vel, modes, flags, box, final, nob, nof)
    return phys, rend, vel, modes, flags, box, final


@njit(cache=True, parallel=True, error_model="numpy")
def simulate_par(S0, masks, events, dts, fss, udts, ft_v, alpha_sel, alpha_margin, P, TT):
    V = ft_v.shape[0]
    nl = masks.shape[0] * V
    phys, rend, vel, modes, flags, box, final = _alloc(nl, masks.shape[1], S0.shape[0])
    nob, nof = np.zeros((0, 1, 4)), np.zeros((0, 1), dtype=np.int32)
    for i in prange(nl):
        lane(i, V, S0, masks, events, dts, fss, udts, ft_v, alpha_sel, alpha_margin, P, TT,
             phys, rend, vel, modes, flags, box, final, nob, nof)
    return phys, rend, vel, modes, flags, box, final


# The planner's form of the timing lanes: per command sequence, the nominal lane (variant 0) in full and every lane
# folded into the per-frame hull and flag AND / OR, without per-lane arrays. run[r, v] False skips a lane that
# duplicates another for that sequence (kinematics.rollout decides: lanes that differ only in the hit-stop links when
# the sequence never enters the hit-stop).

@njit(cache=True, error_model="numpy")
def _bound_one(ri, run, S0, masks, events, dts, fss, udts, ft_v, alpha_sel, alpha_margin, P, TT,
               phys, rend, vel, modes, flags, box, final, bound, f_all, f_any):
    r = np.int64(ri)                  # a prange index can be unsigned: keep `r or -1` an integer
    for t in range(bound.shape[1]):
        bound[r, t, 0] = np.inf
        bound[r, t, 1] = np.inf
        bound[r, t, 2] = -np.inf
        bound[r, t, 3] = -np.inf
        f_all[r, t] = -1
        f_any[r, t] = 0
    for v in range(ft_v.shape[0]):
        if run[r, v]:
            o = r if v == 0 else np.int64(-1)
            run_lane(r, v, o, S0, masks, events, dts, fss, udts, ft_v, alpha_sel, alpha_margin, P, TT,
                     phys, rend, vel, modes, flags, box, final, bound, f_all, f_any)


@njit(cache=True, error_model="numpy")
def _alloc_bound(n, T, K):
    return (np.empty((n, T + 1, 4)), np.empty((n, T + 1), dtype=np.int32), np.empty((n, T + 1), dtype=np.int32))


@njit(cache=True, error_model="numpy")
def simulate_bound(S0, masks, events, dts, fss, udts, ft_v, alpha_sel, alpha_margin, P, TT, run):
    n, T = masks.shape
    phys, rend, vel, modes, flags, box, final = _alloc(n, T, S0.shape[0])
    bound, f_all, f_any = _alloc_bound(n, T, S0.shape[0])
    for r in range(n):
        _bound_one(r, run, S0, masks, events, dts, fss, udts, ft_v, alpha_sel, alpha_margin, P, TT,
                   phys, rend, vel, modes, flags, box, final, bound, f_all, f_any)
    return phys, rend, vel, modes, flags, box, final, bound, f_all, f_any


@njit(cache=True, parallel=True, error_model="numpy")
def simulate_bound_par(S0, masks, events, dts, fss, udts, ft_v, alpha_sel, alpha_margin, P, TT, run):
    n, T = masks.shape
    phys, rend, vel, modes, flags, box, final = _alloc(n, T, S0.shape[0])
    bound, f_all, f_any = _alloc_bound(n, T, S0.shape[0])
    for r in prange(n):
        _bound_one(r, run, S0, masks, events, dts, fss, udts, ft_v, alpha_sel, alpha_margin, P, TT,
                   phys, rend, vel, modes, flags, box, final, bound, f_all, f_any)
    return phys, rend, vel, modes, flags, box, final, bound, f_all, f_any


# ---- knockback bound per query (ssbot.knowledge.knockback) -----------------------------------------------------

@njit(cache=True, inline="always", error_model="numpy")
def seg_box(ax, ay, bx, by, x0, y0, x1, y1):
    """Segment (a, b) meets the box (closed)."""
    if max(ax, bx) < x0 or min(ax, bx) > x1 or max(ay, by) < y0 or min(ay, by) > y1:
        return False
    dx, dy = bx - ax, by - ay
    s0 = dx * (y0 - ay) - dy * (x0 - ax)
    s1 = dx * (y0 - ay) - dy * (x1 - ax)
    s2 = dx * (y1 - ay) - dy * (x0 - ax)
    s3 = dx * (y1 - ay) - dy * (x1 - ax)
    if s0 > 0 and s1 > 0 and s2 > 0 and s3 > 0:
        return False
    if s0 < 0 and s1 < 0 and s2 < 0 and s3 < 0:
        return False
    return True


@njit(cache=True, error_model="numpy")
def near(x0, y0, x1, y1, TT, axis):
    """(an axis-aligned segment meets the box (only looked for when axis), a slope segment meets it)."""
    b0, b1 = _buckets(x0, x1, TT)
    hit_axis = False
    if axis:
        st, ids = np.int64(TT[5]), np.int64(TT[6])
        for b in range(b0, b1 + 1):
            for q in range(np.int64(TT[st + b]), np.int64(TT[st + b + 1])):
                j = TT_H + 3 * np.int64(TT[ids + q])
                if y0 <= TT[j] <= y1 and TT[j + 1] <= x1 and TT[j + 2] >= x0:
                    hit_axis = True
                    break
            if hit_axis:
                break
        if not hit_axis:
            st, ids, ov = np.int64(TT[7]), np.int64(TT[8]), np.int64(TT[9])
            for b in range(b0, b1 + 1):
                for q in range(np.int64(TT[st + b]), np.int64(TT[st + b + 1])):
                    j = ov + 3 * np.int64(TT[ids + q])
                    if x0 <= TT[j] <= x1 and TT[j + 1] <= y1 and TT[j + 2] >= y0:
                        hit_axis = True
                        break
                if hit_axis:
                    break
    if TT[10] == 0:
        return hit_axis, False
    st, ids, os_ = np.int64(TT[12]), np.int64(TT[13]), np.int64(TT[11])
    for b in range(b0, b1 + 1):
        for q in range(np.int64(TT[st + b]), np.int64(TT[st + b + 1])):
            j = os_ + 4 * np.int64(TT[ids + q])
            if seg_box(TT[j], TT[j + 1], TT[j + 2], TT[j + 3], x0, y0, x1, y1):
                return hit_axis, True
    return hit_axis, False


@njit(cache=True, error_model="numpy")
def kb_one(m, boxes, sx, sy, n_max, n_hi, offsets, swept_off, free, ctl_min, hw, skin, foot, head, slop_lo,
           slop_hi, TT, margin, clip, per_frame, swept, frames, flags, hull):
    """One query of knockback.knockback_boxes (the rules are documented there)."""
    F = n_hi.shape[0] - 1
    x0, y0, x1, y1 = boxes[m, 0], boxes[m, 1], boxes[m, 2], boxes[m, 3]
    r = skin + 0.06 + margin          # room for move_x's TOL and the skin around the unclipped path
    axis, slope = near(x0 + min(0.0, n_max * sx) - r, y0 + min(0.0, n_max * sy) - r,
                       x1 + max(0.0, n_max * sx) + r, y1 + max(0.0, n_max * sy) + r, TT, clip)
    if not axis and not slope:
        flags[m] = 0
        for c in range(4):
            swept[m, c] = boxes[m, c] + swept_off[c]
        if per_frame:
            for k in range(F + 1):
                for c in range(4):
                    frames[m, k, c] = boxes[m, c] + offsets[k, c]
        return
    flags[m] = 1
    L = math.hypot(sx, sy)
    g = skin + margin
    px0 = 0.5 * (x0 + x1)
    py0 = y0 + foot
    px, py = px0, py0
    hull[0, 0], hull[0, 1], hull[0, 2], hull[0, 3] = x0, y0, x1, y1
    sc = n_max                        # the last step known to be clear of every slope
    if slope:
        _, touch = near(x0 - g, y0 - g, x1 + g, y1 + g, TT, False)
        if touch:
            sc = 0
    bx0, by0, bx1, by1 = x0, y0, x1, y1
    for s in range(1, n_max + 1):
        if s <= sc:
            qx0, qy0, qx1, qy1 = bx0, by0, bx1, by1
            px, _ = move_x(px, py, sx, hw, skin, foot, head, TT)
            py, _, _, _ = move_y(px, py, sy, hw, skin, foot, head, slop_lo, slop_hi, TT)
            bx0, by0 = x0 + (px - px0), y0 + (py - py0)
            bx1, by1 = x1 + (px - px0), y1 + (py - py0)
            if slope:
                _, touch = near(min(qx0, bx0) - g, min(qy0, by0) - g, max(qx1, bx1) + g, max(qy1, by1) + g,
                                TT, False)
                if touch:
                    sc = s - 1
                    bx0, by0, bx1, by1 = qx0, qy0, qx1, qy1
        if s <= sc:
            hull[s, 0] = min(hull[s - 1, 0], bx0)
            hull[s, 1] = min(hull[s - 1, 1], by0)
            hull[s, 2] = max(hull[s - 1, 2], bx1)
            hull[s, 3] = max(hull[s - 1, 3], by1)
        else:                         # along a slope: the last clear box plus the disk of j contact-projected steps
            j = s - sc
            cx, cy, rr = 0.5 * j * sx, 0.5 * j * sy, 0.5 * j * L
            hull[s, 0] = min(hull[sc, 0], bx0 + cx - rr)
            hull[s, 1] = min(hull[sc, 1], by0 + cy - rr)
            hull[s, 2] = max(hull[sc, 2], bx1 + cx + rr)
            hull[s, 3] = max(hull[sc, 3], by1 + cy + rr)
    if sc < n_max:
        flags[m] |= 2
    swept[m, 0], swept[m, 1] = hull[n_max, 0] - margin, hull[n_max, 1] - margin
    swept[m, 2], swept[m, 3] = hull[n_max, 2] + margin, hull[n_max, 3] + margin
    if per_frame:
        for k in range(F + 1):
            if k >= ctl_min:
                for c in range(4):
                    frames[m, k, c] = swept[m, c] + free[k, c]
            else:
                n = min(n_hi[k], n_max)
                frames[m, k, 0], frames[m, k, 1] = hull[n, 0] - margin, hull[n, 1] - margin
                frames[m, k, 2], frames[m, k, 3] = hull[n, 2] + margin, hull[n, 3] + margin


@njit(cache=True, error_model="numpy")
def kb_query(boxes, sx, sy, n_max, n_hi, offsets, swept_off, free, ctl_min, hw, skin, foot, head, slop_lo, slop_hi,
             TT, margin, clip, per_frame, swept, frames, flags):
    hull = np.empty((n_max + 1, 4))
    for m in range(boxes.shape[0]):
        kb_one(m, boxes, sx, sy, n_max, n_hi, offsets, swept_off, free, ctl_min, hw, skin, foot, head, slop_lo,
               slop_hi, TT, margin, clip, per_frame, swept, frames, flags, hull)


@njit(cache=True, parallel=True, error_model="numpy")
def kb_query_par(boxes, sx, sy, n_max, n_hi, offsets, swept_off, free, ctl_min, hw, skin, foot, head, slop_lo,
                 slop_hi, TT, margin, clip, per_frame, swept, frames, flags, chunks):
    M = boxes.shape[0]
    size = (M + chunks - 1) // chunks
    for c in prange(chunks):
        hull = np.empty((n_max + 1, 4))
        for m in range(c * size, min(M, (c + 1) * size)):
            kb_one(m, boxes, sx, sy, n_max, n_hi, offsets, swept_off, free, ctl_min, hw, skin, foot, head, slop_lo,
                   slop_hi, TT, margin, clip, per_frame, swept, frames, flags, hull)


@njit(cache=True, error_model="numpy")
def kb_hull_one(i, boxes, valid, sx, sy, n_max, swept_off, skin, TT, margin, out, flags):
    """knockback.knockback_hull for candidate i: the frame hull of its boxes plus every side's open-air swept offset;
    when a slope lies within that bound, plus every side's contact-projection disk of n_max steps instead."""
    T1 = boxes.shape[1]
    S = sx.shape[0]
    use_valid = valid.shape[0] > 0
    h0, h1, h2, h3 = np.inf, np.inf, -np.inf, -np.inf
    for t in range(T1):
        if use_valid and not valid[i, t]:
            continue
        h0 = min(h0, boxes[i, t, 0])
        h1 = min(h1, boxes[i, t, 1])
        h2 = max(h2, boxes[i, t, 2])
        h3 = max(h3, boxes[i, t, 3])
    flags[i] = 0
    if h0 > h2:                       # no frame a hit can land on
        out[i, 0], out[i, 1], out[i, 2], out[i, 3] = h0, h1, h2, h3
        return
    o0, o1, o2, o3 = np.inf, np.inf, -np.inf, -np.inf
    for s in range(S):
        o0 = min(o0, swept_off[s, 0])
        o1 = min(o1, swept_off[s, 1])
        o2 = max(o2, swept_off[s, 2])
        o3 = max(o3, swept_off[s, 3])
    r = skin + 0.06 + margin
    _, slope = near(h0 + o0 - r, h1 + o1 - r, h2 + o2 + r, h3 + o3 + r, TT, False)
    if slope:
        flags[i] = 2
        for s in range(S):
            n = n_max[s]
            L = math.hypot(sx[s], sy[s])
            cx, cy, rr = 0.5 * n * sx[s], 0.5 * n * sy[s], 0.5 * n * L
            o0 = min(o0, cx - rr - margin)
            o1 = min(o1, cy - rr - margin)
            o2 = max(o2, cx + rr + margin)
            o3 = max(o3, cy + rr + margin)
    out[i, 0], out[i, 1], out[i, 2], out[i, 3] = h0 + o0, h1 + o1, h2 + o2, h3 + o3


@njit(cache=True, error_model="numpy")
def kb_hull(boxes, valid, sx, sy, n_max, swept_off, skin, TT, margin, out, flags):
    for i in range(boxes.shape[0]):
        kb_hull_one(i, boxes, valid, sx, sy, n_max, swept_off, skin, TT, margin, out, flags)


@njit(cache=True, parallel=True, error_model="numpy")
def kb_hull_par(boxes, valid, sx, sy, n_max, swept_off, skin, TT, margin, out, flags):
    for i in prange(boxes.shape[0]):
        kb_hull_one(i, boxes, valid, sx, sy, n_max, swept_off, skin, TT, margin, out, flags)
