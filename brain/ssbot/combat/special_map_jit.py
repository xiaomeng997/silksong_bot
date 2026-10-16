"""The slam map's per-tick work compiled (task 1v1 SG6; forum.md 62): the one-step lookahead on the stored keyed
levels (map_lookahead.decide_keyed + special_map_rt.decide_multi), the map row's rollout over the planner's horizon
(special_map_rt.MapRuntime.plan) as one loop, the readiness of many end states (MapRuntime.readiness_rows, the min
over the slam's phases) as one call, and batched level lookups (the L2 strip, the off-board spot, the swing lock).

Every kernel is the Python reference's arithmetic in the same order (no fastmath), so its values and decisions are
bit-identical (tests/test_special_map_jit.py; open-loop replays, forum.md 62). Only keyed level maps (the SG4 store);
anything else stays on the Python path. Switch: SSBOT_FORUM_SPECIAL_MAP_JIT (default 1 since the replay identity, forum.md 62; 0 = the Python reference).

The tables (special_map_rt.MapRuntime.jit_tables): the levels S{p} [K, 3, NS, NX] and press bits P{p} of all six
phases as tuples of read-only arrays (a missing phase repeats an existing one, never indexed), the tube index, the
hero macros' jump / bounce profiles, the render lag, the slash polygons and the move's nominal targets per frame.
"""
from __future__ import annotations

import os

import numpy as np
from numba import njit

JIT = os.environ.get("SSBOT_FORUM_SPECIAL_MAP_JIT", "1").strip() != "0"

NONE_LEVEL = 254
PRESS_COOL = 19
A_DIR, A_JUMP, A_PRESS, A_SLASH = 0, 1, 2, 3
EV_GROUND, EV_JUMP, EV_BOUNCE = 0, 1, 2
SRC_INPUT, SRC_JUMP, SRC_BOUNCE, SRC_GROUND = 0, 1, 2, 3
MODES = {"none": 0, "exp": 1, "hard": 2, "hard_exp": 3, "hard2": 4}
# ci: integer constants; cf: float constants
CI_K, CI_NX, CI_NS, CI_NJ, CI_MODE, CI_NCB, CI_A0, CI_A1 = range(8)
CF_XLO, CF_STEP, CF_SCALE, CF_WC, CF_CBW, CF_PA, CF_GPY = range(7)
# the loop state (plan's ls): si int64, sf float64
SI_K, SI_EVK, SI_EVKIND, SI_EVSRC, SI_EVJ, SI_EVQ0, SI_EVTUBE, SI_HASLAND, SI_LAND, SI_DIR, SI_FACING, SI_HASSL, \
    SI_SLP, SI_SLFACE, SI_LSD, SI_LP = range(16)
SF_X, SF_YC, SF_H = range(3)
NSI, NSF = 16, 3

_NJ_ = dict(cache=True, error_model="numpy")


@njit(cache=True, inline="always", error_model="numpy")
def _st(p, k):
    """map_lookahead.steps(p, K)[k]: a run step in frame k (frame 0 none)."""
    if k == 0:
        return 0
    return 1 if (k - p) % 6 != 0 else 0


@njit(cache=True, inline="always", error_model="numpy")
def _xi(k, s, x, K, NX, x_lo, step):
    if s < 0 or k < 0 or k >= K:
        return -1
    xi = int(np.rint((x - x_lo) / step))
    if xi < 0 or xi >= NX:
        return -1
    return xi


@njit(cache=True, inline="always", error_model="numpy")
def _lvv(lv, scale):
    if lv >= NONE_LEVEL:
        return -np.inf
    return lv * scale


@njit(cache=True, inline="always", error_model="numpy")
def _S(S, R, k, s, x, c, K, NX, x_lo, step, scale):
    """LevelSource.S (keyed): the node's value with state key c. R: frame -> row (SG7 stage maps; plain: the
    frame)."""
    xi = _xi(k, s, x, K, NX, x_lo, step)
    if xi < 0:
        return -np.inf
    r = R[k]
    if r < 0:
        return -np.inf
    return _lvv(np.int64(S[r, c + 1, s, xi]), scale)


@njit(cache=True, inline="always", error_model="numpy")
def _Smax(S, R, k, s, x, K, NX, x_lo, step, scale):
    xi = _xi(k, s, x, K, NX, x_lo, step)
    if xi < 0:
        return -np.inf
    r = R[k]
    if r < 0:
        return -np.inf
    m = -1
    for c in range(3):
        lv = np.int64(S[r, c, s, xi])
        if lv < NONE_LEVEL and lv > m:
            m = lv
    if m >= 0:
        return m * scale
    return -np.inf


@njit(cache=True, inline="always", error_model="numpy")
def _SV(S, P, R, k, s, x, d, K, NX, NS, x_lo, step, scale):
    """LevelSource.SV (keyed): the strike with key d held, if the node takes it (press bit)."""
    xi = _xi(k, s, x, K, NX, x_lo, step)
    if xi < 0:
        return -np.inf
    r = R[k]
    if r < 0:
        return -np.inf
    idx = ((r * 3 + d + 1) * NS + s) * NX + xi
    if (np.int64(P[idx >> 3]) >> (7 - (idx & 7))) & 1:
        return _lvv(np.int64(S[r, d + 1, s, xi]), scale)
    return -np.inf


@njit(cache=True, inline="always", error_model="numpy")
def _slice(tube, j, TS0, TN):
    """TubeIndex.slice_of for an airborne event in tube `tube`."""
    if j < TN[tube]:
        return TS0[tube] + j
    return -1


@njit(cache=True, error_model="numpy")
def _kq(S, P, R, p, k, s1, x1, c, d, nmode, nbase, tube, j, land, has_land, ci, cf, pl, gp, TS0, TN):
    """map_lookahead.keyed_q. nmode: 0 ground (slice 0), 1 a jump start (nbase + 1 + m), 2 the event in `tube`
    (slice_of(j + 1 + m), 0 once landed)."""
    K, NX = ci[CI_K], ci[CI_NX]
    mode = ci[CI_MODE]
    x_lo, step, scale = cf[CF_XLO], cf[CF_STEP], cf[CF_SCALE]
    v1 = _S(S, R, k + 1, s1, x1, d, K, NX, x_lo, step, scale)
    if d == c or mode == 0 or not np.isfinite(v1):
        return v1
    br0 = -np.inf
    br1 = -np.inf
    br2 = -np.inf
    ok = _Smax(S, R, k + 1, s1, x1, K, NX, x_lo, step, scale) > -np.inf
    xx = x1
    s = s1
    for m in range(1, 4):
        b = -np.inf
        if ok:
            xx = xx + c * step * _st(p, k + 1 + m)
            if nmode == 0:
                s = 0
            elif nmode == 1:
                s = nbase + 1 + m
            else:
                jj = j + 1 + m
                if (not has_land) or jj < land:
                    s = _slice(tube, jj, TS0, TN)
                else:
                    s = 0
            v = _S(S, R, k + 1 + m, s, xx, d, K, NX, x_lo, step, scale) if s >= 0 else -np.inf
            if np.isfinite(v):
                b = gp[m] * v
            if m < 3:
                ok = s >= 0 and _Smax(S, R, k + 1 + m, s, xx, K, NX, x_lo, step, scale) > -np.inf
        if m == 1:
            br0 = b
        elif m == 2:
            br1 = b
        else:
            br2 = b
    if mode == 2:
        return min(v1, br0)
    if mode == 4:
        return min(v1, min(br0, br1))
    z0 = br0 if np.isfinite(br0) else 0.0
    z1 = br1 if np.isfinite(br1) else 0.0
    z2 = br2 if np.isfinite(br2) else 0.0
    if mode == 1:
        return pl[0] * v1 + pl[1] * z0 + pl[2] * z1 + pl[3] * z2
    if not np.isfinite(br0):
        return -np.inf
    return pl[0] * v1 + pl[1] * br0 + pl[2] * z1 + pl[3] * z2


@njit(cache=True, error_model="numpy")
def _decide1(S, P, R, p, k, kind, ev_k, tube, land, has_land, x, c, last_press, lam, ci, cf, pl, gp, TS0, TN, JS0,
             val, off):
    """map_lookahead.decide_keyed on one phase: the candidates' values into val (offered: off). Action codes: d + 1
    (dir d), 3 + 3 i + bd + 1 (jump hold i, first key bd), 3 + 3 NJ + c + 1 (press)."""
    K, NX, NS, NJ = ci[CI_K], ci[CI_NX], ci[CI_NS], ci[CI_NJ]
    x_lo, step, scale, wc = cf[CF_XLO], cf[CF_STEP], cf[CF_SCALE], cf[CF_WC]
    for a in range(off.shape[0]):
        off[a] = False
    j = k - ev_k
    x1 = x + c * step * _st(p, k + 1)
    if kind == EV_GROUND:
        top = -np.inf
        for d in range(-1, 2):
            v = _kq(S, P, R, p, k, 0, x1, c, d, 0, 0, tube, j, land, has_land, ci, cf, pl, gp, TS0, TN)
            cv = v - lam * (d != c)
            val[d + 1] = cv
            off[d + 1] = True
            if d == -1 or cv > top:
                top = cv
        v0 = np.empty(NJ)
        for i in range(NJ):
            v0[i] = _S(S, R, k, JS0[i], x, c, K, NX, x_lo, step, scale)
        done = np.zeros(NJ, np.bool_)
        for _ in range(NJ):
            bi = -1
            for i in range(NJ):
                if not done[i] and (bi < 0 or v0[i] > v0[bi]):
                    bi = i
            done[bi] = True
            vv = v0[bi]
            if not vv > wc + 1e-3 or vv - lam <= top:
                continue
            s0 = JS0[bi]
            best = -np.inf
            bd = c
            for d in range(-1, 2):
                v = _kq(S, P, R, p, k, s0 + 1, x1, c, d, 1, s0, tube, j, land, has_land, ci, cf, pl, gp, TS0,
                        TN) - lam * (d != c)
                if v > best:
                    best = v
                    bd = d
            cvv = min(vv, best + lam * (bd != c)) - lam
            a = 3 + 3 * bi + bd + 1
            val[a] = cvv
            off[a] = True
            if cvv > top:
                top = cvv
    else:
        s_now = _slice(tube, j, TS0, TN)
        pressed = False
        if k + 1 - last_press >= PRESS_COOL and s_now >= 0:
            sv = _SV(S, P, R, k, s_now, x, c, K, NX, NS, x_lo, step, scale)
            if np.isfinite(sv) and sv >= _S(S, R, k, s_now, x, c, K, NX, x_lo, step, scale) - 1e-3:
                a = 3 + 3 * NJ + c + 1
                val[a] = np.inf
                off[a] = True
                pressed = True
        if not pressed:
            if (not has_land) or j + 1 < land:
                s1 = _slice(tube, j + 1, TS0, TN)
            else:
                s1 = 0
            for d in range(-1, 2):
                v = _kq(S, P, R, p, k, s1, x1, c, d, 2, 0, tube, j, land, has_land, ci, cf, pl, gp, TS0, TN)
                val[d + 1] = v - lam * (d != c)
                off[d + 1] = True


@njit(cache=True, error_model="numpy")
def _decide(Ss, Ps, ph, RM, k, kind, ev_k, tube, land, has_land, x, c, last_press, lam, ci, cf, pl, gp, TS0, TN,
            JS0, val, off, acc, acc_off):
    """special_map_rt.decide_multi (one phase: map_lookahead.decide): per action the minimum over the phases (an
    action a phase does not offer is out), the first best in the candidates' order; nothing feasible: retreat on the
    ground, keep the key in the air. (value, kind, a, b): dir (d), jump (hold index, first key), press (key)."""
    NJ = ci[CI_NJ]
    NA = acc.shape[0]
    K = ci[CI_K]
    for q in range(ph.shape[0]):
        p = ph[q]
        # SG7: a source with the same phase and the same rows over the frames this decision reads (k .. k + 4) as
        # an earlier one gives the same values: skip it (the minimum is unchanged)
        dup = False
        for q2 in range(q):
            if ph[q2] != p:
                continue
            same = True
            for kk in range(k, min(k + 5, K)):
                if RM[q2, kk] != RM[q, kk]:
                    same = False
                    break
            if same:
                dup = True
                break
        if dup:
            continue
        _decide1(Ss[p], Ps[p], RM[q], p, k, kind, ev_k, tube, land, has_land, x, c, last_press, lam, ci, cf, pl, gp,
                 TS0, TN, JS0, val, off)
        if q == 0:
            for a in range(NA):
                acc[a] = val[a]
                acc_off[a] = off[a]
        else:
            for a in range(NA):
                if acc_off[a]:
                    if off[a]:
                        if val[a] < acc[a]:
                            acc[a] = val[a]
                    else:
                        acc_off[a] = False
    ba = -1
    bv = -np.inf
    for a in range(NA):
        if acc_off[a] and (ba < 0 or acc[a] > bv):
            ba = a
            bv = acc[a]
    fb = (1 if x >= 0 else -1) if kind == EV_GROUND else c
    if ba < 0:
        return -np.inf, A_DIR, fb, 0
    if not np.isfinite(bv) and bv < 0:
        return bv, A_DIR, fb, 0
    if ba < 3:
        return bv, A_DIR, ba - 1, 0
    if ba < 3 + 3 * NJ:
        return bv, A_JUMP, (ba - 3) // 3, (ba - 3) % 3 - 1
    return bv, A_PRESS, ba - 3 - 3 * NJ - 1, 0


@njit(cache=True, error_model="numpy")
def decide_k(Ss, Ps, ph, RM, k, kind, ev_k, tube, land, has_land, x, c, last_press, lam, ci, cf, pl, gp, TS0, TN,
             JS0):
    NA = 3 + 3 * ci[CI_NJ] + 3
    val = np.empty(NA)
    off = np.zeros(NA, np.bool_)
    acc = np.empty(NA)
    acc_off = np.zeros(NA, np.bool_)
    return _decide(Ss, Ps, ph, RM, k, kind, ev_k, tube, land, has_land, x, c, last_press, lam, ci, cf, pl, gp, TS0,
                   TN, JS0, val, off, acc, acc_off)


@njit(cache=True, error_model="numpy")
def _clip_band(poly, y0, y1):
    """pogo_slam.clip_band: (ok, x min, x max) of a convex polygon clipped to y0 <= y <= y1."""
    n0 = poly.shape[0]
    cap = 4 * n0 + 8
    ax = np.empty(cap)
    ay = np.empty(cap)
    bx = np.empty(cap)
    by = np.empty(cap)
    n = n0
    for i in range(n0):
        ax[i] = poly[i, 0]
        ay[i] = poly[i, 1]
    for pas in range(2):
        lim = y0 if pas == 0 else y1
        m = 0
        for i in range(n):
            a0, a1 = ax[i], ay[i]
            i2 = (i + 1) % n
            b0, b1 = ax[i2], ay[i2]
            if pas == 0:
                ina = a1 >= lim
                inb = b1 >= lim
            else:
                ina = a1 <= lim
                inb = b1 <= lim
            if ina:
                bx[m] = a0
                by[m] = a1
                m += 1
            if ina != inb:
                t = (lim - a1) / (b1 - a1)
                bx[m] = a0 + t * (b0 - a0)
                by[m] = lim
                m += 1
        n = m
        if n == 0:
            return False, 0.0, 0.0
        for i in range(n):
            ax[i] = bx[i]
            ay[i] = by[i]
    lo = ax[0]
    hi = ax[0]
    for i in range(1, n):
        if ax[i] < lo:
            lo = ax[i]
        if ax[i] > hi:
            hi = ax[i]
    return True, lo, hi


@njit(cache=True, error_model="numpy")
def _land_bounce(yc, q0, BY, BLEN, BAPEX):
    """MapRuntime.land_of for a bounce at contact height yc from cycle q0."""
    n = BLEN[q0]
    for i in range(BAPEX[q0], n):
        if yc + BY[q0, i] <= 0.0:
            return i
    return n


@njit(cache=True, error_model="numpy")
def plan_k(Ss, Ps, ph, RM, si, sf, L, lam, face, ci, cf, pl, gp, TS0, TN, JS0, JT, JH, BT, JLAND, JY, JPY, JLEN, BY,
           BPY, BLEN, BAPEX, LAG, POLY, TGT, NTGT, BITS):
    """MapRuntime.plan's loop from the loop state (si, sf): the masks, the hero's x / y per frame, the action and
    value per decision, the state before each frame and the final state. BITS: B_RIGHT, B_LEFT, B_JUMP, B_DOWN,
    B_ATTACK, DOWN_PRE, DOWN_LEN, PRESS."""
    K = ci[CI_K]
    NJ = ci[CI_NJ]
    NCB = ci[CI_NCB]
    A0, A1 = ci[CI_A0], ci[CI_A1]
    step = cf[CF_STEP]
    cb_w = cf[CF_CBW]
    pa = cf[CF_PA]
    gpy = cf[CF_GPY]
    B_RIGHT, B_LEFT, B_JUMP, B_DOWN, B_ATTACK = BITS[0], BITS[1], BITS[2], BITS[3], BITS[4]
    DOWN_PRE, DOWN_LEN, PRESS = BITS[5], BITS[6], BITS[7]
    p0 = ph[0]
    NA = 3 + 3 * NJ + 3
    val = np.empty(NA)
    off = np.zeros(NA, np.bool_)
    acc = np.empty(NA)
    acc_off = np.zeros(NA, np.bool_)
    masks = np.zeros(L, np.int64)
    xs = np.zeros(L)
    ys = np.zeros(L)
    act = np.zeros((L, 3), np.int64)
    vals = np.zeros(L)
    sti = np.zeros((L, NSI), np.int64)
    stf = np.zeros((L, NSF))
    press = np.zeros(L, np.bool_)
    cont = np.zeros(L, np.bool_)
    s = si.copy()
    f = sf.copy()
    n = 0
    has_first = False
    v_first = -np.inf
    first = np.zeros(3, np.int64)
    for t in range(L):
        k = s[SI_K]
        if k >= K - 5:
            break
        for i in range(NSI):
            sti[t, i] = s[i]
        for i in range(NSF):
            stf[t, i] = f[i]
        jump_now = -1
        press_now = False
        dir_cur = s[SI_DIR]
        new_dir = dir_cur
        if s[SI_HASSL] == 0:
            v, ak, aa, ab = _decide(Ss, Ps, ph, RM, k, s[SI_EVKIND], s[SI_EVK], s[SI_EVTUBE], s[SI_LAND],
                                    s[SI_HASLAND] != 0, f[SF_X], dir_cur, s[SI_LP], lam, ci, cf, pl, gp, TS0, TN, JS0,
                                    val, off, acc, acc_off)
            vals[t] = v
            if not has_first:
                has_first = True
                v_first = v
                first[0], first[1], first[2] = ak, aa, ab
            act[t, 0], act[t, 1], act[t, 2] = ak, aa, ab
            if ak == A_DIR:
                new_dir = aa
            elif ak == A_JUMP:
                jump_now = aa
                new_dir = ab
            else:
                press_now = True
        else:
            act[t, 0] = A_SLASH
            vals[t] = np.nan
        # frame k + 1: the body moves by the key read in frame k
        if _st(p0, k + 1):
            f[SF_X] += dir_cur * step
            s[SI_LSD] = dir_cur
        if jump_now >= 0:
            s[SI_EVKIND] = EV_JUMP
            s[SI_EVSRC] = SRC_JUMP
            s[SI_EVJ] = jump_now
            s[SI_EVK] = k
            s[SI_EVQ0] = (p0 - k) % 6
            s[SI_EVTUBE] = JT[jump_now]
            f[SF_H] = JH[jump_now]
            s[SI_LAND] = JLAND[jump_now, s[SI_EVQ0]]
            s[SI_HASLAND] = 1
        dir_cur = new_dir
        s[SI_DIR] = dir_cur
        if dir_cur != 0:
            s[SI_FACING] = dir_cur
        k += 1
        s[SI_K] = k
        j = k - s[SI_EVK]
        if s[SI_EVKIND] != EV_GROUND and s[SI_HASLAND] != 0 and j >= s[SI_LAND]:
            s[SI_EVKIND] = EV_GROUND
            s[SI_EVSRC] = SRC_GROUND
            s[SI_EVK] = k
            s[SI_HASLAND] = 0
        kind = s[SI_EVKIND]
        if kind == EV_JUMP:
            ji = s[SI_EVJ]
            q0 = s[SI_EVQ0]
            jc = min(j, JLEN[ji, q0] - 1)
            y = JY[ji, q0, jc]
            py = JPY[ji, q0, jc]
        elif kind == EV_BOUNCE:
            q0 = s[SI_EVQ0]
            jc = min(j, BLEN[q0] - 1)
            y = f[SF_YC] + BY[q0, jc]
            py = BPY[q0, jc]
        else:
            y = 0.0
            py = gpy
        xs[t] = f[SF_X]
        ys[t] = y
        km = dir_cur * face
        if km > 0:
            masks[t] |= B_RIGHT
        elif km < 0:
            masks[t] |= B_LEFT
        if kind == EV_JUMP and 1 <= j and j <= f[SF_H]:
            masks[t] |= B_JUMP
        if press_now:
            press[t] = True
            s[SI_LP] = k
            if kind != EV_GROUND:
                s[SI_HASSL] = 1
                s[SI_SLP] = k
                s[SI_SLFACE] = s[SI_FACING]
            lo = max(t - DOWN_PRE, 0)
            hi = min(t - DOWN_PRE + DOWN_LEN, L)
            for u in range(lo, hi):
                masks[u] |= B_DOWN
            for u in range(t, min(t + PRESS, L)):
                masks[u] |= B_ATTACK
        if s[SI_HASSL] != 0:
            i = k - s[SI_SLP]
            if kind == EV_GROUND or i > A1:
                s[SI_HASSL] = 0
            elif i >= A0:
                lag = LAG[p0, 12 + (k - 12) % 6]
                xr = f[SF_X] - lag * s[SI_LSD] * step
                yr = y + py
                pi = 0 if s[SI_SLFACE] >= 0 else 1
                for bb in range(NTGT[k]):
                    ok, r0, r1 = _clip_band(POLY[pi], TGT[k, bb, 2] + pa - yr, TGT[k, bb, 3] + pa - yr)
                    if ok and TGT[k, bb, 0] - r1 < xr and xr < TGT[k, bb, 1] - r0:
                        cont[t] = True
                        s[SI_EVKIND] = EV_BOUNCE
                        s[SI_EVSRC] = SRC_BOUNCE
                        s[SI_EVK] = k
                        q0 = (p0 - k) % 6
                        s[SI_EVQ0] = q0
                        f[SF_YC] = y
                        cb = np.floor(y / cb_w)
                        if cb < 0:
                            cb = 0.0
                        if cb > NCB - 1:
                            cb = NCB - 1.0
                        s[SI_EVTUBE] = BT[int(cb)]
                        s[SI_LAND] = _land_bounce(y, q0, BY, BLEN, BAPEX)
                        s[SI_HASLAND] = 1
                        s[SI_HASSL] = 0
                        break
        n = t + 1
    return masks, xs, ys, act, vals, sti, stf, press, cont, n, s, f, has_first, v_first, first


@njit(cache=True, error_model="numpy")
def ready_k(Ss, pe, xm, kd, gnd, yb, yp, tol, K0S, K0Y0, K0Y1, K0N, x_lo, step, NX, scale):
    """The minimum over the phases pe of MapRuntime.readiness_rows (k = 0): rows with the same key as an earlier row
    (np.unique's first occurrence: x / step, key, ground, the heights / 0.01) take that row's value."""
    N = xm.shape[0]
    key = np.empty((N, 5))
    for i in range(N):
        key[i, 0] = np.rint(xm[i] / step)
        key[i, 1] = kd[i]
        key[i, 2] = 1.0 if gnd[i] else 0.0
        key[i, 3] = 0.0 if gnd[i] else np.rint(yb[i] / 0.01)
        key[i, 4] = 0.0 if gnd[i] else np.rint(yp[i] / 0.01)
    R = np.empty(N)
    hi = x_lo + step * (NX - 1)
    for i in range(N):
        rep = -1
        for jj in range(i):
            if key[jj, 0] == key[i, 0] and key[jj, 1] == key[i, 1] and key[jj, 2] == key[i, 2] and \
                    key[jj, 3] == key[i, 3] and key[jj, 4] == key[i, 4]:
                rep = jj
                break
        if rep >= 0:
            R[i] = R[rep]
            continue
        xi = np.int64(np.rint((xm[i] - x_lo) / step))
        if xi < 0:
            xi = 0
        if xi > NX - 1:
            xi = NX - 1
        inside = xm[i] >= x_lo and xm[i] <= hi
        c = kd[i] + 1
        r = np.inf
        for q in range(pe.shape[0]):
            p = pe[q]
            S = Ss[p]
            if gnd[i]:
                v = _lvv(np.int64(S[0, c, 0, xi]), scale)
            else:
                v = np.inf
                hit = False
                for m in range(K0N[p]):
                    if abs(yb[i] - K0Y0[p, m]) <= tol and abs(yp[i] - K0Y1[p, m]) <= tol:
                        vv = _lvv(np.int64(S[0, c, K0S[p, m], xi]), scale)
                        if not hit or vv < v:
                            v = vv
                        hit = True
                if not hit:
                    v = 0.0
            if not inside:
                v = -np.inf
            if v < r:
                r = v
        R[i] = r
    return R


@njit(cache=True, error_model="numpy")
def smin_k(Ss, ph, RM, ks, ss, xs, cs, K, NX, x_lo, step, scale):
    """[n] the minimum over the sources (phase ph[q], row map RM[q]) of LevelSource.S(k, s, x, c) (keyed)."""
    n = xs.shape[0]
    out = np.empty(n)
    for i in range(n):
        v = np.inf
        for q in range(ph.shape[0]):
            vv = _S(Ss[ph[q]], RM[q], ks[i], ss[i], xs[i], cs[i], K, NX, x_lo, step, scale)
            if q == 0 or vv < v:
                v = vv
        out[i] = v
    return out


def wr(a, dtype) -> np.ndarray:
    """A writable C-contiguous copy when needed (a read-only argument would compile a second specialisation)."""
    a = np.ascontiguousarray(a, dtype)
    return a if a.flags.writeable else a.copy()


def _ro(a: np.ndarray) -> np.ndarray:
    a = np.ascontiguousarray(np.asarray(a))
    if a.flags.writeable:
        a = a.view()
        a.flags.writeable = False
    return a


def tables(rt) -> dict | None:
    """The compiled kernels' tables for a MapRuntime (None: not a keyed level map, the Python path)."""
    from ssbot.combat import dslash
    from ssbot.combat.pogo_model import ACTIVE
    from ssbot.knowledge import kinematics as kin
    srcs = rt.srcs
    if not rt.keyed or not srcs or any(getattr(s, "_P", None) is None for s in srcs.values()):
        return None
    ti, hm = rt.ti, rt.hm
    any_p = sorted(srcs)[0]
    Ss = tuple(_ro(srcs[p]._S if p in srcs else srcs[any_p]._S) for p in range(6))
    Ps = tuple(_ro(srcs[p]._P if p in srcs else srcs[any_p]._P) for p in range(6))
    s0 = srcs[any_p]
    NJ = len(ti.jump_h)
    ci = np.array([ti.K, ti.NX, s0.NS, NJ, MODES[s0.mode], ti.ncb,
                   ACTIVE[0], ACTIVE[1]], np.int64)
    cf = np.array([s0._x_lo, s0._step, s0.scale, ti.wc, ti.cb_w, rt.pa, float(hm.jumps[(1, 0)].py[0])], np.float64)
    gp = np.array([1.0] + [s0.gamma ** m for m in (1, 2, 3)], np.float64)
    pl = np.array(s0.pl, np.float64)
    TS0 = np.asarray(ti.s0, np.int64)
    TN = np.asarray(ti.n, np.int64)
    JS0 = np.array([ti.s0_of[h] for h in ti.jump_h], np.int64)
    JT = np.array([ti._jt[float(h)] for h in ti.jump_h], np.int64)
    JH = np.array([float(h) for h in ti.jump_h], np.float64)
    BT = np.asarray(ti.bounce_t, np.int64)
    jl = max(len(hm.jumps[(int(h), q)].y) for h in ti.jump_h for q in range(6))
    JY = np.zeros((NJ, 6, jl))
    JPY = np.zeros((NJ, 6, jl))
    JLEN = np.zeros((NJ, 6), np.int64)
    JLAND = np.zeros((NJ, 6), np.int64)
    for i, h in enumerate(ti.jump_h):
        for q in range(6):
            pr = hm.jumps[(int(h), q)]
            n = len(pr.y)
            JY[i, q, :n] = pr.y
            JPY[i, q, :n] = pr.py
            JLEN[i, q] = n
            JLAND[i, q] = int(pr.land)
    bl = max(len(hm.bounces[q].y) for q in range(6))
    BY = np.zeros((6, bl))
    BPY = np.zeros((6, bl))
    BLEN = np.zeros(6, np.int64)
    BAPEX = np.zeros(6, np.int64)
    for q in range(6):
        b = hm.bounces[q]
        BY[q, :len(b.y)] = b.y
        BPY[q, :len(b.py)] = b.py
        BLEN[q] = len(b.y)
        BAPEX[q] = int(b.apex)
    LAG = np.array(hm.lag, np.float64, order="C")
    POLY = np.stack([rt.polys[(1, False)], rt.polys[(-1, False)]]).astype(np.float64)
    KT = len(rt.disp_lo)
    tg = [np.asarray(rt.tl.targets(k), np.float64).reshape(-1, 4) for k in range(KT)]
    nb = max(1, max(len(t) for t in tg))
    TGT = np.zeros((KT, nb, 4))
    NTGT = np.zeros(KT, np.int64)
    for k, t in enumerate(tg):
        TGT[k, :len(t)] = t
        NTGT[k] = len(t)
    BITS = np.array([kin.B_RIGHT, kin.B_LEFT, kin.B_JUMP, kin.B_DOWN, kin.B_ATTACK, dslash.DOWN_PRE, dslash.DOWN_LEN,
                     dslash.PRESS], np.int64)
    k0 = {}
    for p in srcs:
        k0[p] = rt._k0_slices(p)
    M = max(1, max(len(v[0]) for v in k0.values()))
    K0S = np.zeros((6, M), np.int64)
    K0Y0 = np.zeros((6, M))
    K0Y1 = np.zeros((6, M))
    K0N = np.zeros(6, np.int64)
    for p, (s, y0, y1) in k0.items():
        K0S[p, :len(s)] = s
        K0Y0[p, :len(s)] = y0
        K0Y1[p, :len(s)] = y1
        K0N[p] = len(s)
    return {"Ss": Ss, "Ps": Ps, "ci": ci, "cf": cf, "pl": pl, "gp": gp, "TS0": TS0, "TN": TN, "JS0": JS0, "JT": JT,
            "JH": JH, "BT": BT, "JLAND": JLAND, "JY": JY, "JPY": JPY, "JLEN": JLEN, "BY": BY, "BPY": BPY, "BLEN": BLEN,
            "BAPEX": BAPEX, "LAG": LAG, "POLY": POLY, "TGT": TGT, "NTGT": NTGT, "BITS": BITS, "K0S": K0S,
            "K0Y0": K0Y0, "K0Y1": K0Y1, "K0N": K0N, "KT": KT,
            "jidx": {int(h): i for i, h in enumerate(ti.jump_h)}}


def plan_args(T: dict, tgt: tuple | None = None) -> tuple:
    TGT, NTGT = tgt if tgt is not None else (T["TGT"], T["NTGT"])
    return (T["ci"], T["cf"], T["pl"], T["gp"], T["TS0"], T["TN"], T["JS0"], T["JT"], T["JH"], T["BT"], T["JLAND"],
            T["JY"], T["JPY"], T["JLEN"], T["BY"], T["BPY"], T["BLEN"], T["BAPEX"], T["LAG"], T["POLY"], TGT,
            NTGT, T["BITS"])


def warm() -> float:
    """Compile (or load from numba's cache) every kernel with the run-time types on a tiny synthetic map: the
    planner's construction calls it, so neither the first tick with the arena nor the first slam tick pays for it."""
    import time
    t0 = time.perf_counter()
    K, NS, NX, NJ = 12, 4, 6, 1
    S = _ro(np.full((K, 3, NS, NX), 10, np.uint8))
    P = _ro(np.zeros((K * 3 * NS * NX + 7) // 8, np.uint8))
    Ss, Ps = (S,) * 6, (P,) * 6
    ci = np.array([K, NX, NS, NJ, 2, 1, 3, 9], np.int64)
    cf = np.array([-1.0, 0.25, 0.025, 1.0, 0.2, 4.4, 0.0], np.float64)
    pl = np.array([0.785, 0.2, 0.01, 0.005])
    gp = np.array([1.0, 0.99, 0.99 ** 2, 0.99 ** 3])
    TS0 = np.array([0, 1, 3], np.int64)
    TN = np.array([1, 2, 1], np.int64)
    JS0 = np.array([1], np.int64)
    JT = np.array([1], np.int64)
    JH = np.array([1.0])
    BT = np.array([2], np.int64)
    JLAND = np.full((NJ, 6), 2, np.int64)
    JY = np.zeros((NJ, 6, 3))
    JLEN = np.full((NJ, 6), 3, np.int64)
    BY = np.zeros((6, 3))
    BLEN = np.full(6, 3, np.int64)
    BAPEX = np.zeros(6, np.int64)
    LAG = np.zeros((6, 20))
    POLY = np.zeros((2, 4, 2))
    TGT = np.zeros((K + 2, 1, 4))
    NTGT = np.zeros(K + 2, np.int64)
    BITS = np.array([1, 2, 4, 8, 16, 1, 6, 3], np.int64)
    ph = np.array([0, 1], np.int64)
    RM = np.ascontiguousarray(np.tile(np.arange(K, dtype=np.int64), (2, 1)))
    si = np.zeros(NSI, np.int64)
    si[SI_LP] = -100
    sf = np.zeros(NSF)
    plan_k(Ss, Ps, ph, RM, si, sf, 4, 0.02, 1, ci, cf, pl, gp, TS0, TN, JS0, JT, JH, BT, JLAND, JY, JY, JLEN, BY, BY,
           BLEN, BAPEX, LAG, POLY, TGT, NTGT, BITS)
    decide_k(Ss, Ps, ph, RM, 2, 0, 2, 0, 0, False, 0.0, 0, -100, 0.02, ci, cf, pl, gp, TS0, TN, JS0)
    z = np.zeros(2)
    ready_k(Ss, ph, z, np.zeros(2, np.int64), np.array([True, False]), z, z, 0.08, np.zeros((6, 1), np.int64),
            np.zeros((6, 1)), np.zeros((6, 1)), np.zeros(6, np.int64), -1.0, 0.25, NX, 0.025)
    smin_k(Ss, ph, RM, np.zeros(2, np.int64), np.zeros(2, np.int64), z, np.zeros(2, np.int64), K, NX, -1.0, 0.25,
           0.025)
    return (time.perf_counter() - t0) * 1e3


__all__ = ["JIT", "tables", "plan_k", "decide_k", "ready_k", "smin_k", "warm", "plan_args"]
