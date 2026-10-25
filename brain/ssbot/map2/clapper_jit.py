"""Map v2 stage M4b: the Clapper model's predict() COMPILED (numba) - an exact port of clapper.Sim and clapper.predict's
particle loop (docs/plans/forum_map_v2.md section 1 L3 'Speed'; HANDOFF 'Task map2 - stage M4' / 'M4b'). Offline /
planning code only (nothing in the live bot imports ssbot.map2).

    P = clapper_jit.predict(obs, mems, hero, K, T=120)      # the same Prediction as clapper.predict(...)

What is ported: one Clapper's machine (Sim.step / _enter and their helpers) on a float64 row per Clapper (the fields
F_*), its log / hazards / pending choices in small arrays; the joint particles of predict() with the same depth-first
fork order (a random choice not fixed yet ends the step with its options; the particle is forked from the copy taken
before the step, the last option first), the same records (one per frame and Clapper, kept as a tree: each particle's
frame points at its parent frame) and the same truncation (a stable sort by -p). The start (Sim.__init__ from the
observation) and the output (the groups by the first move choices, the records' dedupe, the Branch objects) stay in
Python / numba helpers built on the same arithmetic; a state name the tables do not know behaves as in the Python
model (Idle's box, no duration). Anything the port does not cover (a choice where Sim.may_choose said none, an overflow
of the log / hazard arrays) falls back to clapper.predict.

Identity: tests/test_m4b_speed.py and ssbot.tools.m4b_speed predeq compare the branches (p, choices, reveal, records,
hazards) with clapper.predict exactly.
"""
from __future__ import annotations

import math
import time

import numpy as np
from numba import njit, objmode, types
from numba.typed import Dict

from ssbot.map2 import clapper as cm

# ---- one Clapper's row ------------------------------------------------------------------------------------------------
(F_ST, F_J, F_X, F_Y, F_VX, F_VY, F_FACE, F_HP, F_CLIP, F_BUDDY, F_BXOK, F_BX, F_A, F_B, F_DUROK, F_DLO, F_DNOM, F_DHI,
 F_ENTK, F_EA, F_EB, F_RSOK, F_RS, F_NCH, F_ATT, F_WE, F_WFOK, F_WF, F_WDIR, F_JX, F_LANDED, F_DEAD, F_LTURN, F_K,
 F_EVREV, F_PREV, F_RECOIL, F_RECDIR, F_IDLEBUD, F_INRPREV, F_EVADED, F_CHARGED, F_NLOG, F_NHZ, F_NFC, F_IID) = range(46)
F_RUN = 46                     # 12: V4 instance x 3 + its event slot
F_MISS = 58                    # 12
NF = 70
LOGMAX = 40                    # log entries per Clapper (kind, outcome, k, rlo, rhi); NaN = None
HZMAX = 64                     # hazards per Clapper (kind 0 rune / 1 bomb, x, y, r, t0, t1)
FCMAX = 6                      # pending (fixed) choices of the step being re-run: (n_ch, outcome)

# log kinds and their names
KIND_NAMES = ("will_evade", "walk_far", "close", "close_ev", "far", "escape", "hit_idle", "cancel", "walkb", "avoid")
K_WE, K_WF, K_CLOSE, K_CLOSEEV, K_FAR, K_ESC, K_HITIDLE, K_CANCEL, K_WALKB, K_AVOID = range(10)
EVENTS = ("SLAM", "EVADE", "CAST", "JUMP", "JUMP CAST")
V4_NAMES = ("close", "close_ev", "far", "escape")          # V4 instance i: log kind 2 + i

# named states (their ids are passed in the SID array, positions below)
NAMED = ("Idle", "Walk", "Close Range", "Far Range", "Dmg Attack", "After Scuttle", "Evade Scuttle", "Slam 0",
         "Slam 1", "Cast Jump", "Jump Aim", "Jump", "Air", "Charged?", "Slam Effects?", "Slam 2", "Cast 2",
         "Cast Slam Antic", "Jump Antic", "Drop In", "Enter Land", "Start Battle?", "Slam Recover")
(S_IDLE, S_WALK, S_CLOSE, S_FAR, S_DMG, S_AFTER, S_EVADE, S_SLAM0, S_SLAM1, S_CASTJUMP, S_JUMPAIM, S_JUMP, S_AIR,
 S_CHARGED, S_SLAMEFF, S_SLAM2, S_CAST2, S_CSANTIC, S_JANTIC, S_DROPIN, S_ENTERLAND, S_STARTB, S_SLAMREC) = range(23)

# constants (clapper.py)
DT = cm.DT
WALL_L, WALL_R = cm.WALL_L, cm.WALL_R
FLOOR = cm.FLOOR
STAND_Y = cm.STAND_Y
SR_X, SR_Y0, SR_Y1 = cm.SLAM_RANGE
BUDDY_NEAR = cm.BUDDY_NEAR
ESCAPE_RAY = cm.ESCAPE_RAY
TURN_PAUSE = cm.TURN_PAUSE
WALK_SPEED = cm.WALK_SPEED
WALK_DIST, WALK_RANGE = cm.WALK_DIST, cm.WALK_RANGE
EVADE_SPEED = cm.EVADE_SPEED
LUNGE = cm.LUNGE
JUMP_VY = cm.JUMP_VY
GRAV_STEP = cm.GRAV_STEP
JUMP_CLAMP = cm.JUMP_CLAMP
TARGET_U = cm.TARGET_U
RECOIL_V, RECOIL_N = cm.RECOIL_V, cm.RECOIL_N
NAIL_DMG = cm.NAIL_DMG
BOMB_DX, BOMB_DY = cm.BOMB_DX, cm.BOMB_DY
EV_K0, EV_K1, EV_K2 = cm.EV_K
CLOSE_K0, CLOSE_K1, CLOSE_K2 = cm.CLOSE_K
IDLE_K_T = cm.IDLE_K[True]
IDLE_K_F = cm.IDLE_K[False]
WALK_FAR_MIN, WALK_FAR_MAX = cm.WALK_FAR_MIN, cm.WALK_FAR_MAX
NO_FAR = cm.NO_FAR
RANGE_LAG = cm.RANGE_LAG
RANGE_SKIN = cm.RANGE_SKIN
ROOF_L = np.array(cm.ROOF_L, np.float64)
ROOF_R = np.array(cm.ROOF_R, np.float64)

ST_OK, ST_NEED, ST_ERR = 0, 1, 2
_KEY9 = types.UniTuple(types.int64, 9)


# ---- the tables (per Know and state name list) ----------------------------------------------------------------------

class Tables:
    """The Know tables as arrays over state ids (names: the static list + any name an observation brought)."""

    def __init__(self, K: cm.Know, names: list[str]):
        self.names = list(names)
        self.sid = {n: i for i, n in enumerate(self.names)}
        n = len(self.names)
        idle = K.body.get("Idle")
        JM = max([len(t[0]) for t in K.body.values()] + [1])
        self.BOX = np.zeros((n, JM, 4))
        self.BOXN = np.zeros(n, np.int64)
        self.BOXL = np.zeros((n, 4))
        for i, nm in enumerate(self.names):
            tab, last = K.body.get(nm) or idle
            self.BOX[i, :len(tab)] = tab
            self.BOXN[i] = len(tab)
            self.BOXL[i] = last
        nodur = {"Idle", "Walk", "Air", "Jump", "Drop In"} | set(cm.DEAD)
        self.DHAS = np.zeros(n, np.bool_)
        maxk = max([max(c) for c in K.dur.values() if c] + [0])
        G = maxk + 2                                   # rows gt = -1 .. maxk
        self.DT = np.zeros((n, G, 3), np.int64)
        self.KM = maxk + 1
        self.CNT = np.zeros((n, self.KM), np.int64)
        self.CHAS = np.zeros(n, np.bool_)
        for i, nm in enumerate(self.names):
            c = K.dur.get(nm)
            if c:
                for kk, v in c.items():
                    self.CNT[i, kk] = v
                self.CHAS[i] = True
            if nm in nodur or not c:
                continue
            self.DHAS[i] = True
            for gt in range(-1, maxk + 1):
                r = K.durations(nm, gt=gt)
                self.DT[i, gt + 1] = r
        self.G = G
        fl = lambda s: np.array([nm in s for nm in self.names], np.bool_)  # noqa: E731
        self.ASET = fl(cm.ATTACK_SET)
        self.ACLR = fl(cm.ATTACK_CLR)
        self.INTRO = fl(cm.INTRO)
        self.DEADS = fl(cm.DEAD)
        self.NEXT = np.array([self.sid.get(cm.NEXT.get(nm), -1) if cm.NEXT.get(nm) is not None else -1
                              for nm in self.names], np.int64)
        self.SID = np.array([self.sid[nm] for nm in NAMED], np.int64)
        self.EVST = np.array([self.sid[cm.EV_STATE[e]] for e in EVENTS], np.int64)
        cy, r, l0, l1 = K.rune()
        self.RUNE = np.array([cy, r, l0, l1], np.float64)
        self.BOMBS = np.array(K.bomb_rings(), np.float64).reshape(-1, 3)
        v4 = cm._v4s()
        self.V4N = np.array([len(v4[nm].events) for nm in V4_NAMES], np.int64)
        self.V4E = np.full((4, 3), -1, np.int64)
        self.V4W = np.zeros((4, 3))
        self.V4EMAX = np.zeros((4, 3), np.int64)
        self.V4MMAX = np.zeros((4, 3), np.int64)
        for i, nm in enumerate(V4_NAMES):
            v = v4[nm]
            for j_, e in enumerate(v.events):
                self.V4E[i, j_] = EVENTS.index(e)
                self.V4W[i, j_] = v.w[j_]
                self.V4EMAX[i, j_] = v.emax[j_]
                self.V4MMAX[i, j_] = v.mmax[j_]

    def args(self) -> tuple:
        return (self.BOX, self.BOXN, self.BOXL, self.DHAS, self.DT, self.CNT, self.ASET, self.ACLR, self.INTRO,
                self.DEADS, self.NEXT, self.SID, self.EVST, self.RUNE, self.BOMBS, self.V4N, self.V4E, self.V4W,
                self.V4EMAX, self.V4MMAX, ROOF_L, ROOF_R)


_TABLES: dict = {}


_SNAMES: dict = {}


def static_names(K: cm.Know) -> list[str]:
    r = _SNAMES.get(id(K))
    if r is None:
        r = _static_names(K)
        _SNAMES[id(K)] = r
        _SNAMES[("K", id(K))] = K                 # keep K alive (the key holds its id)
    return r


def _static_names(K: cm.Know) -> list[str]:
    s = set(NAMED) | set(cm.NEXT) | set(v for v in cm.NEXT.values()) | set(cm.ATTACK_SET) | set(cm.ATTACK_CLR) | \
        set(cm.ATTACKING) | set(cm.INTRO) | set(cm.INSTANT) | set(cm.NO_BODY) | set(cm.DEAD) | set(cm.MOVE_OF) | \
        set(cm.EV_STATE.values()) | {"Avoid Type", "Escape Jump"} | set(K.dur) | set(K.body)
    return sorted(s)


def tables(K: cm.Know, extra: tuple = ()) -> Tables:
    key = (id(K), tuple(extra))
    t = _TABLES.get(key)
    if t is None:
        if len(_TABLES) > 16:
            _TABLES.clear()
        t = Tables(K, static_names(K) + [n for n in extra])
        t._K = K                                   # keep K alive (the key holds its id)
        _TABLES[key] = t
    return t


# ---- the machine ------------------------------------------------------------------------------------------------------

@njit(cache=True)
def _box(BOX, BOXN, BOXL, st, j):
    if 0 <= j < BOXN[st]:
        return BOX[st, j]
    return BOXL[st]


@njit(cache=True)
def _at(hx, k):
    n = hx.shape[0]
    return min(max(k, 0), n - 1)


@njit(cache=True)
def _hstep(k, steps, use_steps):
    if not use_steps:
        return 0 if k % 6 == 5 else 1
    return np.int64(steps[min(max(k, 0), steps.shape[0] - 1)])


@njit(cache=True)
def _in_range(r, hbox, k):
    hx = SR_X + RANGE_SKIN
    i = _at(hbox[:, 0], k)
    x = r[F_X]
    y = r[F_Y]
    return (hbox[i, 0] < x + hx and hbox[i, 2] > x - hx and hbox[i, 1] < y + SR_Y1 + RANGE_SKIN and
            hbox[i, 3] > y + SR_Y0 - RANGE_SKIN)


@njit(cache=True)
def _face(r, hx_arr, k, pause):
    hx = hx_arr[_at(hx_arr, k)]
    if hx > r[F_X]:
        want = 1.0
    elif hx < r[F_X]:
        want = -1.0
    else:
        want = r[F_FACE]
    if want != r[F_FACE] and ((not pause) or k - r[F_LTURN] >= TURN_PAUSE):
        r[F_FACE] = want
        r[F_LTURN] = k


@njit(cache=True)
def _clamp_x(r, st, BOX, BOXN, BOXL):
    bx = _box(BOX, BOXN, BOXL, st, np.int64(r[F_J]))
    a = r[F_X] + r[F_FACE] * bx[0]
    b = r[F_X] + r[F_FACE] * bx[1]
    lo = min(a, b)
    hi = max(a, b)
    if lo < WALL_L:
        r[F_X] += WALL_L - lo
    elif hi > WALL_R:
        r[F_X] -= hi - WALL_R


@njit(cache=True)
def _grounded_y(r, steps, BOX, BOXN, BOXL):
    yg = FLOOR - _box(BOX, BOXN, BOXL, np.int64(r[F_ST]), np.int64(r[F_J]))[2]
    if r[F_Y] < yg - 1e-6:
        r[F_Y] = yg
        r[F_VY] = 0.0
    elif r[F_Y] > yg + 1e-6:
        for _ in range(steps):
            r[F_VY] -= GRAV_STEP
            r[F_Y] = max(r[F_Y] + r[F_VY] * DT, yg)
        if r[F_Y] <= yg + 1e-6:
            r[F_Y] = yg
            r[F_VY] = 0.0
    else:
        r[F_VY] = 0.0


@njit(cache=True)
def _timer_offsets(r, k, lo, nom, hi, has_rs, her_rs):
    e_lo = r[F_ENTK] + r[F_EA] + lo
    e_hi = r[F_ENTK] + r[F_EB] + hi
    if has_rs:
        e_lo = max(e_lo, her_rs)
        e_hi = max(e_hi, her_rs + RANGE_LAG)
    r[F_A] = min(e_lo - k, 0)
    r[F_B] = max(e_hi - k, 0)


@njit(cache=True)
def _close_eta(r, hbox, k):
    hx = SR_X + RANGE_SKIN
    j = np.int64(r[F_J])
    x = r[F_X]
    y = r[F_Y]
    for kk in range(k, k + WALK_FAR_MAX - j + 2):
        jj = j + (kk - k)
        if jj < CLOSE_K1:
            continue
        i = _at(hbox[:, 0], kk)
        if hbox[i, 0] < x + hx and hbox[i, 2] > x - hx and hbox[i, 1] < y + SR_Y1 and hbox[i, 3] > y + SR_Y0:
            return jj
    return WALK_FAR_MAX + 1


@njit(cache=True)
def _seg_y(pts, px):
    """(found, y) of the polyline pts over px (clapper.roof_y's inner loop)."""
    n = pts.shape[0]
    if pts[0, 0] <= px <= pts[n - 1, 0]:
        for s in range(n - 1):
            xa, ya, xb, yb = pts[s, 0], pts[s, 1], pts[s + 1, 0], pts[s + 1, 1]
            if xa <= px <= xb:
                return True, ya + (yb - ya) * (px - xa) / max(xb - xa, 1e-9)
    return False, 0.0


@njit(cache=True)
def _roof_y(px, RL, RR):
    ok, y = _seg_y(RL, px)
    if ok:
        return y
    ok, y = _seg_y(RR, px)
    if ok:
        return y
    if px < RL[0, 0]:
        return RL[0, 1]
    if px > RR[RR.shape[0] - 1, 0]:
        return RR[RR.shape[0] - 1, 1]
    return 1e9


def _py_hypot(a: float, b: float) -> float:
    return math.hypot(a, b)


@njit(cache=True)
def _roof_normal(px, RL, RR):
    e = 0.05
    s = (_roof_y(px + e, RL, RR) - _roof_y(px - e, RL, RR)) / (2 * e)
    with objmode(n="float64"):              # Python's math.hypot (correctly rounded; the C one may differ by an ulp)
        n = _py_hypot(s, 1.0)
    return s / n, -1.0 / n


@njit(cache=True)
def _log(r, L, kind, outcome, k, rlo, rhi):
    n = np.int64(r[F_NLOG])
    if n >= LOGMAX:
        return False
    L[n, 0] = kind
    L[n, 1] = outcome
    L[n, 2] = k
    L[n, 3] = rlo
    L[n, 4] = rhi
    r[F_NLOG] = n + 1
    return True


@njit(cache=True)
def _decided(r, L, kind, outcome, k):
    return _log(r, L, kind, outcome, k, k + r[F_A], k + r[F_B])


@njit(cache=True)
def _hazard(r, H, kind, x, y, rad, t0, t1):
    n = np.int64(r[F_NHZ])
    if n >= HZMAX:
        return False
    H[n, 0] = kind
    H[n, 1] = x
    H[n, 2] = y
    H[n, 3] = rad
    H[n, 4] = t0
    H[n, 5] = t1
    r[F_NHZ] = n + 1
    return True


@njit(cache=True)
def _rune(r, H, k, RUNE):
    cy, rad, l0, l1 = RUNE[0], RUNE[1], RUNE[2], RUNE[3]
    face = r[F_FACE]
    dx = 6.75 if face > 0 else 6.48
    a = np.int64(r[F_A])
    b = np.int64(r[F_B])
    return _hazard(r, H, 0.0, r[F_X] + face * dx, cy, rad, k + a + np.int64(math.floor(l0)),
                   k + b + np.int64(math.ceil(l1)))


@njit(cache=True)
def _bombs(r, H, k, BOMBS):
    x0 = r[F_X]
    y0 = r[F_Y] + BOMB_DY
    a = np.int64(r[F_A])
    b = np.int64(r[F_B])
    for q in range(BOMBS.shape[0]):
        m = np.int64(BOMBS[q, 0])
        t0 = BOMBS[q, 1]
        t1 = BOMBS[q, 2]
        for si in range(1 if m == 0 else 2):
            sx = 0 if m == 0 else (-1 if si == 0 else 1)
            x = x0 + sx * BOMB_DX * m
            if x < WALL_L - 2.2 or x > WALL_R + 2.2:
                continue
            if not _hazard(r, H, 1.0, x, y0, 2.166, k + a + np.int64(math.floor(t0)),
                           k + b + np.int64(math.ceil(t1))):
                return False
    return True


@njit(cache=True)
def _dur(r, st, gt, DHAS, DURT):
    """Sim._dur into the row's dur fields."""
    if not DHAS[st]:
        r[F_DUROK] = 0.0
        return
    G = DURT.shape[1]
    if gt + 1 < G:
        r[F_DLO] = DURT[st, gt + 1, 0]
        r[F_DNOM] = DURT[st, gt + 1, 1]
        r[F_DHI] = DURT[st, gt + 1, 2]
    else:
        r[F_DLO] = gt + 1
        r[F_DNOM] = gt + 1
        r[F_DHI] = gt + 1
    r[F_DUROK] = 1.0


@njit(cache=True)
def _p_ended(st, j, dlo, dhi, CNT):
    tot = 0
    s = 0
    KM = CNT.shape[1]
    for kk in range(KM):
        c = CNT[st, kk]
        if c == 0:
            continue
        if dlo <= kk <= dhi:
            tot += c
            if kk <= j:
                s += c
    if tot == 0:
        return 0.5
    v = s / tot
    return min(max(v, 0.0), 1.0)


@njit(cache=True)
def _choose(r, FC, n_opts, opt_p, opt_o, need):
    """Sim._choose: (outcome, status): a fixed (pending) choice for this key, the only option, or NEED (the options
    are in opt_p / opt_o [0 .. n_opts), need[0] = n_opts)."""
    key = np.int64(r[F_NCH])
    r[F_NCH] = key + 1
    for i in range(np.int64(r[F_NFC])):
        if np.int64(FC[i, 0]) == key:
            return FC[i, 1], ST_OK
    if n_opts == 1:
        return opt_o[0], ST_OK
    need[0] = n_opts
    need[1] = key
    return 0.0, ST_NEED


@njit(cache=True)
def _pysum(a, n):
    """Python's sum() of n floats from the int 0 (Python >= 3.12: Neumaier's compensated summation)."""
    if n == 0:
        return 0.0
    f = a[0]
    c = 0.0
    for i in range(1, n):
        x = a[i]
        t = f + x
        if abs(f) >= abs(x):
            c += (f - t) + x
        else:
            c += (x - t) + f
        f = t
    if c != 0.0 and math.isfinite(c):
        f += c
    return f


@njit(cache=True)
def _v4_dist(r, inst, V4N, V4E, V4W, V4EMAX, V4MMAX, opt_p, opt_o):
    n = V4N[inst]
    forced = -1
    for i in range(n):
        if r[F_MISS + 3 * inst + i] >= V4MMAX[inst, i]:
            forced = i
    if forced >= 0:
        opt_p[0] = 1.0
        opt_o[0] = V4E[inst, forced]
        return 1
    m = 0
    ws = np.zeros(3)
    for i in range(n):
        if r[F_RUN + 3 * inst + i] < V4EMAX[inst, i]:
            ws[m] = V4W[inst, i]
            m += 1
    s = _pysum(ws, m)
    if m == 0:
        opt_p[0] = 1.0
        opt_o[0] = V4E[inst, 0]
        return 1
    m = 0
    for i in range(n):
        if r[F_RUN + 3 * inst + i] < V4EMAX[inst, i]:
            opt_p[m] = V4W[inst, i] / s
            opt_o[m] = V4E[inst, i]
            m += 1
    return m


@njit(cache=True)
def _v4_take(r, inst, ev, V4N, V4E):
    n = V4N[inst]
    i = -1
    for q in range(n):
        if V4E[inst, q] == ev:
            i = q
    rr = r[F_RUN + 3 * inst + i] + 1
    for q in range(n):
        r[F_RUN + 3 * inst + q] = 0.0
        r[F_MISS + 3 * inst + q] += 1.0
    r[F_RUN + 3 * inst + i] = rr
    r[F_MISS + 3 * inst + i] = 0.0


@njit(cache=True)
def _walk_bins(j0, j_close, opt_p, opt_o):
    width = 15
    lo = max(WALK_FAR_MIN, j0 + 1)
    hi = WALK_FAR_MAX
    if lo >= hi:
        opt_p[0] = 1.0
        opt_o[0] = lo
        return 1
    top = min(hi, j_close)
    n = 0
    a = lo
    while a < top:
        b = min(a + width, top)
        opt_p[n] = (b - a) / (hi - lo)
        opt_o[n] = (a + b) // 2
        n += 1
        a = b
    rest = 1.0 - _pysum(opt_p, n)
    if rest > 1e-9:
        opt_p[n] = rest
        opt_o[n] = -1.0
        n += 1
    return n


@njit(cache=True)
def _enter(r, L, H, FC, st, hx_arr, hbox, k, buddy_att, tabs, opt_p, opt_o, need):
    """Sim._enter: ST_OK / ST_NEED / ST_ERR (a log / hazard overflow)."""
    (BOX, BOXN, BOXL, DHAS, DURT, CNT, ASET, ACLR, INTRO, DEADS, NEXT, SID, EVST, RUNE, BOMBS, V4N, V4E, V4W, V4EMAX,
     V4MMAX, RL, RR) = tabs
    prev = np.int64(r[F_ST])
    r[F_PREV] = r[F_ST]
    for _ in range(16):
        r[F_ST] = st
        r[F_J] = 0.0
        if ASET[st]:
            r[F_ATT] = 1.0
            r[F_EVADED] = 0.0
        if ACLR[st]:
            r[F_ATT] = 0.0
        if st == SID[S_IDLE]:
            r[F_VX] = 0.0
            r[F_WE] = -1.0
            r[F_EVREV] = 0.0
            r[F_IDLEBUD] = r[F_BXOK]
            _face(r, hx_arr, k, True)
            if r[F_BXOK] > 0 and abs(r[F_BX] - r[F_X]) < BUDDY_NEAR:
                hr = hx_arr[_at(hx_arr, k)] > r[F_X]
                br = r[F_BX] > r[F_X]
                st = SID[S_EVADE] if hr == br else SID[S_WALK]
                if not _decided(r, L, K_AVOID, st, k):
                    return ST_ERR
                prev = -2                                   # "Avoid Type"
                continue
        elif st == SID[S_WALK]:
            r[F_WFOK] = 0.0
            hx = hx_arr[_at(hx_arr, k)]
            r[F_WDIR] = -1.0 if abs(hx - r[F_X]) < WALK_DIST else 1.0
            r[F_VX] = WALK_SPEED * r[F_WDIR] * (1 if hx > r[F_X] else -1)
            r[F_CLIP] = 1.0 if r[F_WDIR] > 0 else 2.0
        elif st == SID[S_CLOSE]:
            if buddy_att:
                if not _decided(r, L, K_CANCEL, SID[S_IDLE], k):
                    return ST_ERR
                st = SID[S_IDLE]
                prev = SID[S_CLOSE]
                continue
            if r[F_CLIP] == 2.0 and prev == SID[S_WALK]:
                if not _decided(r, L, K_WALKB, 0.0, k):
                    return ST_ERR
                st = EVST[0]
                prev = SID[S_CLOSE]
                continue
            inst = 1 if r[F_EVADED] > 0 else 0
            n = _v4_dist(r, inst, V4N, V4E, V4W, V4EMAX, V4MMAX, opt_p, opt_o)
            evf, s_ = _choose(r, FC, n, opt_p, opt_o, need)
            if s_ != ST_OK:
                return s_
            ev = np.int64(evf)
            _v4_take(r, inst, ev, V4N, V4E)
            if not _decided(r, L, K_CLOSE + inst, ev, k):
                return ST_ERR
            st = EVST[ev]
            prev = SID[S_CLOSE]
            continue
        elif st == SID[S_FAR]:
            if buddy_att:
                if not _decided(r, L, K_CANCEL, SID[S_IDLE], k):
                    return ST_ERR
                st = SID[S_IDLE]
                prev = SID[S_FAR]
                continue
            n = _v4_dist(r, 2, V4N, V4E, V4W, V4EMAX, V4MMAX, opt_p, opt_o)
            evf, s_ = _choose(r, FC, n, opt_p, opt_o, need)
            if s_ != ST_OK:
                return s_
            ev = np.int64(evf)
            _v4_take(r, 2, ev, V4N, V4E)
            if not _decided(r, L, K_FAR, ev, k):
                return ST_ERR
            st = EVST[ev]
            prev = SID[S_FAR]
            continue
        elif st == SID[S_DMG]:
            prev = st
            st = SID[S_CLOSE] if (_in_range(r, hbox, k) or r[F_INRPREV] > 0) else SID[S_FAR]
            continue
        elif st == SID[S_AFTER]:
            prev = st
            st = SID[S_CLOSE] if _in_range(r, hbox, k) else SID[S_FAR]
            continue
        elif st == SID[S_EVADE]:
            r[F_EVADED] = 1.0
            back = (r[F_X] - WALL_L) if r[F_FACE] > 0 else (WALL_R - r[F_X])
            if back < ESCAPE_RAY:
                n = _v4_dist(r, 3, V4N, V4E, V4W, V4EMAX, V4MMAX, opt_p, opt_o)
                evf, s_ = _choose(r, FC, n, opt_p, opt_o, need)
                if s_ != ST_OK:
                    return s_
                ev = np.int64(evf)
                _v4_take(r, 3, ev, V4N, V4E)
                if not _decided(r, L, K_ESC, ev, k):
                    return ST_ERR
                st = EVST[ev]
                prev = -3                                   # "Escape Jump"
                continue
            _face(r, hx_arr, k, False)
            r[F_VX] = -EVADE_SPEED * r[F_FACE]
        elif ASET[st]:
            _face(r, hx_arr, k, False)
            r[F_VX] = 0.0
            if st == SID[S_CSANTIC]:
                r[F_CHARGED] = 1.0
            elif st == SID[S_JANTIC]:
                r[F_CHARGED] = 0.0
        elif st == SID[S_SLAM0] or st == SID[S_SLAM1]:
            r[F_VX] = LUNGE * r[F_FACE]
        elif st == SID[S_CASTJUMP]:
            _face(r, hx_arr, k, False)
            prev = st
            st = SID[S_JUMPAIM]
            continue
        elif st == SID[S_JUMPAIM]:
            _face(r, hx_arr, k, False)
            tgt = hx_arr[_at(hx_arr, k)] - TARGET_U * r[F_FACE]
            v = tgt - r[F_X]
            r[F_JX] = min(max(v, -JUMP_CLAMP), JUMP_CLAMP)
            prev = st
            st = SID[S_JUMP]
            continue
        elif st == SID[S_JUMP]:
            r[F_VX] = r[F_JX]
            r[F_VY] = JUMP_VY
        elif st == SID[S_CHARGED]:
            if r[F_CHARGED] > 0:
                r[F_CHARGED] = 0.0
                if not _rune(r, H, k, RUNE):
                    return ST_ERR
            prev = st
            st = SID[S_SLAMEFF]
            continue
        elif st == SID[S_SLAMEFF]:
            prev = st
            st = SID[S_SLAM2]
            continue
        elif st == SID[S_SLAM2]:
            r[F_VX] = 0.0
        elif st == SID[S_CAST2]:
            if not _bombs(r, H, k, BOMBS):
                return ST_ERR
        elif DEADS[st]:
            r[F_DEAD] = 1.0
        break
    r[F_ENTK] = k
    r[F_EA] = r[F_A]
    r[F_EB] = r[F_B]
    _dur(r, np.int64(r[F_ST]), -1, DHAS, DURT)
    return ST_OK


@njit(cache=True)
def _step(r, L, H, FC, k, hx_arr, hbox, steps_a, use_steps, hk, hd, buddy_att, has_bx, bx_val, tabs, opt_p, opt_o,
          need):
    """Sim.step: ST_OK / ST_NEED (need[0] options in opt_p / opt_o) / ST_ERR."""
    (BOX, BOXN, BOXL, DHAS, DURT, CNT, ASET, ACLR, INTRO, DEADS, NEXT, SID, EVST, RUNE, BOMBS, V4N, V4E, V4W, V4EMAX,
     V4MMAX, RL, RR) = tabs
    r[F_K] = k
    r[F_BXOK] = 1.0 if has_bx else 0.0
    r[F_BX] = bx_val if has_bx else 0.0
    if r[F_DEAD] > 0:
        return ST_OK
    steps = _hstep(k, steps_a, use_steps)
    st = np.int64(r[F_ST])
    # ---- physics ----
    if st == SID[S_JUMP] or st == SID[S_AIR]:
        bx = _box(BOX, BOXN, BOXL, SID[S_AIR], 0)
        for _ in range(steps):
            r[F_VY] -= GRAV_STEP
            nx = r[F_X] + r[F_VX] * DT
            ny = r[F_Y] + r[F_VY] * DT
            lo = nx + min(r[F_FACE] * bx[0], r[F_FACE] * bx[1])
            hi = nx + max(r[F_FACE] * bx[0], r[F_FACE] * bx[1])
            cx = lo if nx < 0.5 * (WALL_L + WALL_R) else hi
            ry = _roof_y(cx, RL, RR)
            if ny + bx[3] > ry and r[F_VY] > 0:
                n0, n1 = _roof_normal(cx, RL, RR)
                vn = r[F_VX] * n0 + r[F_VY] * n1
                if vn < 0:
                    vx2 = r[F_VX] - vn * n0
                    vy2 = r[F_VY] - vn * n1
                    r[F_VX] = vx2
                    r[F_VY] = vy2
                ny = ry - bx[3]
            r[F_X] = nx
            r[F_Y] = ny
            _clamp_x(r, SID[S_AIR], BOX, BOXN, BOXL)
            if r[F_Y] + bx[2] <= FLOOR and r[F_VY] < 0:
                r[F_Y] = FLOOR - bx[2]
                r[F_LANDED] = 1.0
                break
    elif st == SID[S_DROPIN]:
        for _ in range(steps):
            r[F_Y] = max(r[F_Y] - 48.0 * DT, STAND_Y)
    else:
        if r[F_VX] != 0 and steps:
            r[F_X] += r[F_VX] * DT * steps
            _clamp_x(r, np.int64(r[F_ST]), BOX, BOXN, BOXL)
        if not INTRO[st]:
            _grounded_y(r, steps, BOX, BOXN, BOXL)
    if r[F_RECOIL] > 0 and steps and r[F_RECDIR] == 2.0:
        # t1 S3 (clapper.UP_RECOIL): an up slash's recoil - up while airborne, none on the ground
        n = min(steps, np.int64(r[F_RECOIL]))
        r[F_RECOIL] -= n
        if st == SID[S_JUMP] or st == SID[S_AIR]:
            bx = _box(BOX, BOXN, BOXL, SID[S_AIR], 0)
            if r[F_Y] + bx[2] > FLOOR + 1e-9:
                r[F_Y] += RECOIL_V * DT * n
                lo = r[F_X] + min(r[F_FACE] * bx[0], r[F_FACE] * bx[1])
                hi = r[F_X] + max(r[F_FACE] * bx[0], r[F_FACE] * bx[1])
                ry = _roof_y(lo if r[F_X] < 0.5 * (WALL_L + WALL_R) else hi, RL, RR)
                if r[F_Y] + bx[3] > ry:
                    r[F_Y] = ry - bx[3]
    elif r[F_RECOIL] > 0 and steps:
        n = min(steps, np.int64(r[F_RECOIL]))
        r[F_RECOIL] -= n
        r[F_X] += r[F_RECDIR] * RECOIL_V * DT * n
        _clamp_x(r, SID[S_AIR] if (st == SID[S_JUMP] or st == SID[S_AIR]) else np.int64(r[F_ST]), BOX, BOXN, BOXL)
    # her run inside Slam Range (her physics box against its trigger after this frame's motion)
    r[F_INRPREV] = r[F_RSOK]
    if _in_range(r, hbox, k):
        if r[F_RSOK] == 0:
            r[F_RSOK] = 1.0
            r[F_RS] = k
    else:
        r[F_RSOK] = 0.0
    # ---- the update ----
    r[F_J] += 1.0
    hkind = hk[k] if k < hk.shape[0] else 0
    if hkind != 0:
        if hkind == 1:                                    # a side slash: the recoil
            r[F_RECOIL] = RECOIL_N
            r[F_RECDIR] = 1.0 if r[F_X] > hx_arr[_at(hx_arr, k)] else -1.0
        elif hkind == 3 and (st == SID[S_JUMP] or st == SID[S_AIR]):
            r[F_RECOIL] = RECOIL_N                        # t1 S3: an up slash in the air - up (RECDIR 2)
            r[F_RECDIR] = 2.0
        r[F_HP] -= hd[k]
        if r[F_HP] <= 0:
            r[F_DEAD] = 1.0
            r[F_ST] = SID[S_STARTB]
            r[F_J] = 0.0
            r[F_ATT] = 0.0
            return ST_OK
    if hkind != 0 and st == SID[S_IDLE]:
        r[F_A] = 0.0
        r[F_B] = 0.0
        return _enter(r, L, H, FC, SID[S_DMG], hx_arr, hbox, k, buddy_att, tabs, opt_p, opt_o, need)
    if hkind != 0 and NEXT[st] == SID[S_IDLE] and r[F_DUROK] > 0 and r[F_J] + r[F_A] >= r[F_DLO]:
        p_idle = _p_ended(st, np.int64(r[F_J] + r[F_A]), np.int64(r[F_DLO]), np.int64(r[F_DHI]), CNT)
        opt_p[0] = p_idle
        opt_o[0] = 1.0
        opt_p[1] = 1.0 - p_idle
        opt_o[1] = 0.0
        v, s_ = _choose(r, FC, 2, opt_p, opt_o, need)
        if s_ != ST_OK:
            return s_
        if v > 0:
            if not _log(r, L, K_HITIDLE, 1.0, k, k, k):
                return ST_ERR
            r[F_A] = 0.0
            r[F_B] = 0.0
            s_ = _enter(r, L, H, FC, SID[S_IDLE], hx_arr, hbox, k, buddy_att, tabs, opt_p, opt_o, need)
            if s_ != ST_OK:
                return s_
            return _enter(r, L, H, FC, SID[S_DMG], hx_arr, hbox, k, buddy_att, tabs, opt_p, opt_o, need)
    if st == SID[S_IDLE]:
        _face(r, hx_arr, k, True)
        if r[F_IDLEBUD] > 0:
            lo, nom, hi = IDLE_K_T
        else:
            lo, nom, hi = IDLE_K_F
        if r[F_J] >= nom:
            _timer_offsets(r, k, lo, nom, hi, False, 0)
            return _enter(r, L, H, FC, SID[S_WALK], hx_arr, hbox, k, buddy_att, tabs, opt_p, opt_o, need)
        if r[F_J] >= EV_K1 and r[F_RSOK] > 0 and r[F_EVREV] == 0:
            r[F_EVREV] = 1.0
            if r[F_WE] < 0:
                opt_p[0] = 0.5
                opt_o[0] = 1.0
                opt_p[1] = 0.5
                opt_o[1] = 0.0
                v, s_ = _choose(r, FC, 2, opt_p, opt_o, need)
                if s_ != ST_OK:
                    return s_
                r[F_WE] = v
            if r[F_WE] > 0:
                _timer_offsets(r, k, EV_K0, EV_K1, EV_K2, True, np.int64(r[F_RS]))
                if not _log(r, L, K_WE, 1.0, k, k + r[F_A], k + r[F_B]):
                    return ST_ERR
                return _enter(r, L, H, FC, SID[S_EVADE], hx_arr, hbox, k, buddy_att, tabs, opt_p, opt_o, need)
            if not _log(r, L, K_WE, 0.0, k, k, k):
                return ST_ERR
        return ST_OK
    if st == SID[S_WALK]:
        _face(r, hx_arr, k, True)
        hx = hx_arr[_at(hx_arr, k)]
        d = abs(hx - r[F_X])
        if d < WALK_DIST - WALK_RANGE:
            r[F_WDIR] = -1.0
        elif d > WALK_DIST + WALK_RANGE:
            r[F_WDIR] = 1.0
        elif r[F_WDIR] == 0:
            r[F_WDIR] = 1.0 if d > WALK_DIST else -1.0
        toward = 1 if hx > r[F_X] else -1
        r[F_VX] = WALK_SPEED * r[F_WDIR] * toward
        r[F_CLIP] = 1.0 if r[F_WDIR] > 0 else 2.0
        if r[F_J] >= CLOSE_K1 and r[F_RSOK] > 0:
            _timer_offsets(r, k, CLOSE_K0, CLOSE_K1, CLOSE_K2, True, np.int64(r[F_RS]))
            return _enter(r, L, H, FC, SID[S_CLOSE], hx_arr, hbox, k, buddy_att, tabs, opt_p, opt_o, need)
        if r[F_WFOK] > 0 and r[F_WF] >= NO_FAR and r[F_J] > r[F_WF] - NO_FAR + 8:
            r[F_WFOK] = 0.0
        if r[F_WFOK] == 0 and r[F_J] >= WALK_FAR_MIN - 1:
            jc = _close_eta(r, hbox, k)
            n = _walk_bins(np.int64(r[F_J]), jc, opt_p, opt_o)
            v, s_ = _choose(r, FC, n, opt_p, opt_o, need)
            if s_ != ST_OK:
                return s_
            if v >= 0:
                r[F_WF] = v
            else:
                r[F_WF] = NO_FAR + jc
            r[F_WFOK] = 1.0
            if not _log(r, L, K_WF, v, k, np.nan, np.nan):
                return ST_ERR
        if r[F_WFOK] > 0 and r[F_WF] < NO_FAR and r[F_J] >= r[F_WF]:
            w = 8
            wf = np.int64(r[F_WF])
            _timer_offsets(r, k, wf - w, wf, wf + w, False, 0)
            return _enter(r, L, H, FC, SID[S_FAR], hx_arr, hbox, k, buddy_att, tabs, opt_p, opt_o, need)
        return ST_OK
    if st == SID[S_AIR]:
        if r[F_LANDED] > 0:
            r[F_LANDED] = 0.0
            return _enter(r, L, H, FC, SID[S_CHARGED], hx_arr, hbox, k, buddy_att, tabs, opt_p, opt_o, need)
        return ST_OK
    if st == SID[S_JUMP]:
        r[F_ST] = SID[S_AIR]
        r[F_J] = 0.0
        return ST_OK
    if st == SID[S_DROPIN]:
        if r[F_Y] <= STAND_Y + 1e-6:
            return _enter(r, L, H, FC, SID[S_ENTERLAND], hx_arr, hbox, k, buddy_att, tabs, opt_p, opt_o, need)
        return ST_OK
    if r[F_DUROK] > 0 and r[F_J] >= r[F_DNOM]:
        dlo = r[F_DLO]
        dnom = r[F_DNOM]
        dhi = r[F_DHI]
        r[F_A] += dlo - dnom
        r[F_B] += dhi - dnom
        nxt = NEXT[st]
        if nxt >= 0:
            return _enter(r, L, H, FC, nxt, hx_arr, hbox, k, buddy_att, tabs, opt_p, opt_o, need)
    return ST_OK


@njit(cache=True)
def _may_choose(r, k, hk, SID):
    if r[F_DEAD] > 0:
        return False
    st = np.int64(r[F_ST])
    if st == SID[S_IDLE] or st == SID[S_WALK]:
        return True
    if k < hk.shape[0] and hk[k] != 0:
        return True
    return r[F_DUROK] > 0 and r[F_J] + 1 >= r[F_DNOM]


@njit(cache=True)
def _rec(r, out, SID):
    """Sim.rec: (k, a, b, st, j, x, y, face, ham)."""
    st = np.int64(r[F_ST])
    ham = 0
    if st == SID[S_SLAM1]:
        ham = 1
    elif st == SID[S_SLAM2]:
        ham = 2 | (1 if (r[F_J] == 0 and np.int64(r[F_PREV]) == SID[S_SLAM1]) else 0)
    elif st == SID[S_SLAMREC] and r[F_J] == 0:
        ham = 2
    out[0] = r[F_K]
    out[1] = r[F_A]
    out[2] = r[F_B]
    out[3] = r[F_ST]
    out[4] = r[F_J]
    out[5] = r[F_X]
    out[6] = r[F_Y]
    out[7] = r[F_FACE]
    out[8] = ham


@njit(cache=True)
def _grow2(a, n):
    if n <= a.shape[0]:
        return a
    m = max(n, 2 * a.shape[0])
    shp = (m,) + a.shape[1:]
    b = np.empty(shp, a.dtype)
    b[:a.shape[0]] = a
    return b


@njit(cache=True)
def run_particles(F0, L0, H0, T, hx_arr, hbox, steps_a, use_steps, HK, HD, tabs, max_particles):
    """predict()'s particle loop. Returns (status, the final particles' slots in order and their p, the slots' rows /
    logs / hazards, the history (parent, records), the leaf node of each final particle, n_max)."""
    SID = tabs[11]
    ns = F0.shape[0]
    cap = 64
    PF = np.zeros((cap, ns, NF))
    PL = np.zeros((cap, ns, LOGMAX, 5))
    PH = np.zeros((cap, ns, HZMAX, 6))
    PFC = np.zeros((cap, ns, FCMAX, 2))
    PCUR = np.zeros((cap, ns, 9))
    PHIST = np.zeros(cap, np.int64)
    n_slots = 1
    PF[0] = F0
    PL[0] = L0
    PH[0] = H0
    ncap = 4096
    NPAR = np.zeros(ncap, np.int64)
    NREC = np.zeros((ncap, ns, 9))
    n_nodes = 1
    NPAR[0] = -1
    for i in range(ns):
        _rec(PF[0, i], NREC[0, i], SID)
    PHIST[0] = 0
    parts_s = np.zeros(1, np.int64)
    parts_p = np.ones(1)
    n_max = 1
    opt_p = np.zeros(16)
    opt_o = np.zeros(16)
    need = np.zeros(2, np.int64)
    snap_r = np.zeros(NF)
    snap_L = np.zeros((LOGMAX, 5))
    snap_H = np.zeros((HZMAX, 6))
    snap_FC = np.zeros((FCMAX, 2))
    st_s = np.zeros(64, np.int64)                # the stack: slot, p, i
    st_p = np.zeros(64)
    st_i = np.zeros(64, np.int64)
    for k in range(1, T + 1):
        new_s = np.zeros(max(16, 2 * parts_s.shape[0]), np.int64)
        new_p = np.zeros(new_s.shape[0])
        n_new = 0
        for pi in range(parts_s.shape[0]):
            sp = 0
            st_s[0] = parts_s[pi]
            st_p[0] = parts_p[pi]
            st_i[0] = 0
            sp = 1
            while sp > 0:
                sp -= 1
                slot = st_s[sp]
                pp = st_p[sp]
                i = st_i[sp]
                if i >= ns:
                    # the particle's frame done: its history node
                    if n_nodes >= NPAR.shape[0]:
                        NPAR = _grow2(NPAR, n_nodes + 1)
                        NREC = _grow2(NREC, n_nodes + 1)
                    NPAR[n_nodes] = PHIST[slot]
                    NREC[n_nodes] = PCUR[slot]
                    PHIST[slot] = n_nodes
                    n_nodes += 1
                    if n_new >= new_s.shape[0]:
                        new_s = _grow2(new_s, n_new + 1)
                        new_p = _grow2(new_p, n_new + 1)
                    new_s[n_new] = slot
                    new_p[n_new] = pp
                    n_new += 1
                    continue
                r = PF[slot, i]
                if ns == 2:
                    o = PF[slot, 1 - i]
                    b_att = (o[F_ATT] > 0) and not (o[F_DEAD] > 0)
                    has_bx = not (o[F_DEAD] > 0)
                    bx_val = o[F_X]
                else:
                    b_att = False
                    has_bx = False
                    bx_val = 0.0
                may = _may_choose(r, k, HK[i], SID)
                if may:
                    snap_r[:] = r
                    snap_L[:] = PL[slot, i]
                    snap_H[:] = PH[slot, i]
                    snap_FC[:] = PFC[slot, i]
                s_ = _step(r, PL[slot, i], PH[slot, i], PFC[slot, i], k, hx_arr, hbox, steps_a, use_steps, HK[i],
                           HD[i], b_att, has_bx, bx_val, tabs, opt_p, opt_o, need)
                if s_ == ST_OK:
                    r[F_NFC] = 0.0
                    _rec(r, PCUR[slot, i], SID)
                    if sp >= st_s.shape[0]:
                        st_s = _grow2(st_s, sp + 1)
                        st_p = _grow2(st_p, sp + 1)
                        st_i = _grow2(st_i, sp + 1)
                    st_s[sp] = slot
                    st_p[sp] = pp
                    st_i[sp] = i + 1
                    sp += 1
                    continue
                if s_ == ST_ERR or not may:
                    return 1, parts_s, parts_p, PF, PL, PH, NPAR, NREC, PHIST, n_max, n_nodes
                n_opts = need[0]
                key = need[1]
                for q in range(n_opts):
                    qp = opt_p[q]
                    if qp <= 0:
                        continue
                    # a new particle: every Clapper copied, this one from the snapshot with the choice fixed
                    if n_slots >= PF.shape[0]:
                        PF = _grow2(PF, n_slots + 1)
                        PL = _grow2(PL, n_slots + 1)
                        PH = _grow2(PH, n_slots + 1)
                        PFC = _grow2(PFC, n_slots + 1)
                        PCUR = _grow2(PCUR, n_slots + 1)
                        PHIST = _grow2(PHIST, n_slots + 1)
                        r = PF[slot, i]
                    ns2 = n_slots
                    n_slots += 1
                    PF[ns2] = PF[slot]
                    PL[ns2] = PL[slot]
                    PH[ns2] = PH[slot]
                    PFC[ns2] = PFC[slot]
                    PCUR[ns2] = PCUR[slot]
                    PHIST[ns2] = PHIST[slot]
                    PF[ns2, i] = snap_r
                    PL[ns2, i] = snap_L
                    PH[ns2, i] = snap_H
                    PFC[ns2, i] = snap_FC
                    nfc = np.int64(snap_r[F_NFC])
                    if nfc >= FCMAX:
                        return 1, parts_s, parts_p, PF, PL, PH, NPAR, NREC, PHIST, n_max, n_nodes
                    PFC[ns2, i, nfc, 0] = key
                    PFC[ns2, i, nfc, 1] = opt_o[q]
                    PF[ns2, i, F_NFC] = nfc + 1
                    if sp >= st_s.shape[0]:
                        st_s = _grow2(st_s, sp + 1)
                        st_p = _grow2(st_p, sp + 1)
                        st_i = _grow2(st_i, sp + 1)
                    st_s[sp] = ns2
                    st_p[sp] = pp * qp
                    st_i[sp] = i
                    sp += 1
        parts_s = new_s[:n_new].copy()
        parts_p = new_p[:n_new].copy()
        n_max = max(n_max, n_new)
        if n_new > max_particles:
            o_ = np.argsort(-parts_p, kind="mergesort")[:max_particles]
            parts_s = parts_s[o_]
            parts_p = parts_p[o_]
    return 0, parts_s, parts_p, PF, PL, PH, NPAR, NREC, PHIST, n_max, n_nodes


@njit(cache=True)
def chain(NPAR, NREC, leaf, sim, out):
    """The records of one Clapper along a particle's history (frame 0 .. T) into out [T + 1, 9]."""
    n = out.shape[0]
    g = leaf
    i = n - 1
    while g >= 0 and i >= 0:
        out[i] = NREC[g, sim]
        g = NPAR[g]
        i -= 1


@njit(cache=True)
def _r3(v):
    """round(v, 3) as an integer key (Python's correctly rounded decimal; an exact half tie in the double product is
    settled by Python's round)."""
    p = v * 1000.0
    f = math.floor(p)
    if abs((p - f) - 0.5) < 1e-6:
        with objmode(q="int64"):
            q = int(round(round(v, 3) * 1000.0))
        return q
    return np.int64(np.round(p))


@njit(cache=True)
def dedupe(recs, starts):
    """predict()'s merge of a group's record lists (recs [n, 9]; list b = rows starts[b] .. starts[b + 1] - 1): the
    first occurrence of each (k, a, b, st, j, round(x, 3), round(y, 3), face, ham) in order. Returns the rows kept."""
    seen = Dict.empty(key_type=_KEY9, value_type=types.int64)
    keep = np.zeros(recs.shape[0], np.int64)
    m = 0
    for i in range(recs.shape[0]):
        r = recs[i]
        kk = (np.int64(r[0]), np.int64(r[1]), np.int64(r[2]), np.int64(r[3]), np.int64(r[4]), _r3(r[5]), _r3(r[6]),
              np.int64(r[7]), np.int64(r[8]))
        if kk in seen:
            continue
        seen[kk] = 1
        keep[m] = i
        m += 1
    return keep[:m]


# ---- the Python side: the start, the output -------------------------------------------------------------------------

def _pack(s: cm.Sim, tb: Tables) -> tuple:
    r = np.zeros(NF)
    r[F_ST] = tb.sid[s.st]
    r[F_J] = s.j
    r[F_X], r[F_Y], r[F_VX], r[F_VY] = s.x, s.y, s.vx, s.vy
    r[F_FACE] = s.face
    r[F_HP] = s.hp
    r[F_CLIP] = 1.0 if s.clip == "Walk F" else 2.0 if s.clip == "Walk B" else 0.0
    r[F_BUDDY] = 1.0 if s.buddy else 0.0
    r[F_BXOK] = 0.0 if s.buddy_x is None else 1.0
    r[F_BX] = 0.0 if s.buddy_x is None else s.buddy_x
    r[F_A], r[F_B] = s.a, s.b
    if s.dur is not None:
        r[F_DUROK], r[F_DLO], r[F_DNOM], r[F_DHI] = 1.0, s.dur[0], s.dur[1], s.dur[2]
    r[F_ENTK], r[F_EA], r[F_EB] = s.entry_k, s.ea, s.eb
    if s.rs is not None:
        r[F_RSOK], r[F_RS] = 1.0, s.rs
    r[F_NCH] = s.n_ch
    r[F_ATT] = 1.0 if s.attacking else 0.0
    r[F_WE] = -1.0 if s.will_evade is None else (1.0 if s.will_evade else 0.0)
    if s.walk_far is not None:
        r[F_WFOK], r[F_WF] = 1.0, s.walk_far
    r[F_WDIR] = s.walk_dir
    r[F_JX] = s.jump_x
    r[F_LANDED] = 1.0 if s.landed else 0.0
    r[F_DEAD] = 1.0 if s.dead else 0.0
    r[F_LTURN] = s.last_turn
    r[F_K] = s.k
    r[F_EVREV] = 1.0 if s.ev_revealed else 0.0
    r[F_PREV] = -1.0 if s.prev_st is None else tb.sid[s.prev_st]
    r[F_RECOIL], r[F_RECDIR] = s.recoil, s.rec_dir
    r[F_IDLEBUD] = 1.0 if s.idle_bud else 0.0
    r[F_INRPREV] = 1.0 if s.inr_prev else 0.0
    r[F_EVADED] = 1.0 if s.mem.evaded else 0.0
    r[F_CHARGED] = 1.0 if s.mem.charged else 0.0
    r[F_IID] = s.iid
    for i, nm in enumerate(V4_NAMES):
        v = s.mem.v4[nm]
        for j_ in range(len(v.events)):
            r[F_RUN + 3 * i + j_] = v.run[j_]
            r[F_MISS + 3 * i + j_] = v.miss[j_]
    L = np.zeros((LOGMAX, 5))
    if len(s.log) > LOGMAX:
        raise OverflowError("log")
    for n_, (kind, out, k, rlo, rhi) in enumerate(s.log):
        kd = KIND_NAMES.index(kind)
        L[n_] = (kd, _out_code(kd, out, tb), k, np.nan if rlo is None else rlo, np.nan if rhi is None else rhi)
    r[F_NLOG] = len(s.log)
    H = np.zeros((HZMAX, 6))
    if len(s.hazards) > HZMAX:
        raise OverflowError("hazards")
    for n_, h in enumerate(s.hazards):
        H[n_] = (0.0 if h[0] == "rune" else 1.0,) + tuple(h[1:])
    r[F_NHZ] = len(s.hazards)
    return r, L, H


def _out_code(kd: int, out, tb: Tables) -> float:
    if kd in (K_WE, K_HITIDLE):
        return 1.0 if out else 0.0
    if kd == K_WF:
        return -1.0 if out is None else float(out)
    if kd in (K_CLOSE, K_CLOSEEV, K_FAR, K_ESC, K_WALKB):
        return float(EVENTS.index(out))
    if kd == K_CANCEL:
        return float(tb.sid[out])
    return float(tb.sid[out])                     # avoid: a state


def _out_value(kd: int, code: float, tb: Tables):
    if kd in (K_WE, K_HITIDLE):
        return code > 0
    if kd == K_WF:
        return None if code < 0 else int(code)
    if kd in (K_CLOSE, K_CLOSEEV, K_FAR, K_ESC):
        return EVENTS[int(code)]
    if kd == K_WALKB:
        return "SLAM"
    if kd == K_CANCEL:
        return "Idle"
    return tb.names[int(code)]


def _unpack_log(L: np.ndarray, n: int, tb: Tables) -> list:
    out = []
    for i in range(n):
        kd = int(L[i, 0])
        rlo, rhi = L[i, 3], L[i, 4]
        out.append([KIND_NAMES[kd], _out_value(kd, L[i, 1], tb), int(L[i, 2]),
                    None if np.isnan(rlo) else int(rlo), None if np.isnan(rhi) else int(rhi)])
    return out


def _unpack_hz(H: np.ndarray, n: int) -> list:
    return [("rune" if H[i, 0] == 0 else "bomb", float(H[i, 1]), float(H[i, 2]), float(H[i, 3]), int(H[i, 4]),
             int(H[i, 5])) for i in range(n)]


def _rec_tuple(r, names) -> tuple:
    return (int(r[0]), int(r[1]), int(r[2]), names[int(r[3])], int(r[4]), float(r[5]), float(r[6]), int(r[7]),
            int(r[8]))


STATS = {"jit": 0, "fallback": 0}


class JBranch(cm.Branch):
    """A Branch whose records are kept as arrays: _arr {iid: [n, 9] float64 rows (k, a, b, state id, j, x, y, face,
    ham)} in the records' order, _names the state ids' names; the tuples (recs) are made on first use only (the
    search reads the arrays: ssbot.map2.search's M4b paths)."""

    @property
    def recs(self):
        r = self.__dict__.get("_recs_t")
        if r is None:
            names = self._names
            r = {iid: [_rec_tuple(x, names) for x in a] for iid, a in self._arr.items()}
            self.__dict__["_recs_t"] = r
        return r

    @recs.setter
    def recs(self, v):
        if v is not None:
            self.__dict__["_recs_t"] = v


def predict(obs: list, mems: dict, hero: cm.HeroPath, K: cm.Know, T: int = 120, max_choices: int = 2,
            max_particles: int = 2000, group: bool = True, hazards: list | None = None) -> cm.Prediction:
    """clapper.predict, compiled: the same Prediction (falls back to clapper.predict when the port does not cover
    the case)."""
    t0 = time.perf_counter()
    extra = list(hazards or ())
    alive = [o for o in obs if o.hp > 0 and o.st not in cm.DEAD]
    buddy = len(alive) > 1
    sims0 = [cm.Sim(o, mems.get(o.iid) or cm.Memory(), K, buddy) for o in alive]
    for s in sims0:
        s.buddy_x = None
    if not sims0 or len(sims0) > 2:
        STATS["fallback"] += 1
        return cm.predict(obs, mems, hero, K, T=T, max_choices=max_choices, max_particles=max_particles,
                          group=group, hazards=hazards)
    base = static_names(K)
    unknown = sorted({n for s in sims0 for n in (s.st, s.prev_st) if n is not None and n not in base})
    tb = tables(K, tuple(unknown))
    try:
        rows = [_pack(s, tb) for s in sims0]
    except (OverflowError, KeyError, ValueError):
        STATS["fallback"] += 1
        return cm.predict(obs, mems, hero, K, T=T, max_choices=max_choices, max_particles=max_particles,
                          group=group, hazards=hazards)
    ns = len(sims0)
    F0 = np.stack([r[0] for r in rows])
    L0 = np.stack([r[1] for r in rows])
    H0 = np.stack([r[2] for r in rows])
    hx = np.ascontiguousarray(hero.x, np.float64)
    hb = np.ascontiguousarray(hero.box, np.float64).reshape(-1, 4)
    use_steps = hero.steps is not None
    steps_a = np.asarray(hero.steps if use_steps else np.zeros(1), np.int64)
    HK = np.zeros((ns, T + 2), np.int64)
    HD = np.zeros((ns, T + 2), np.float64)
    for i, s in enumerate(sims0):
        for k, h in (hero.hits.get(s.iid) or {}).items():
            if 0 <= k <= T + 1 and h is not None:
                kind, dmg = (h, cm.NAIL_DMG) if isinstance(h, str) else (h[0], h[1])
                HK[i, k] = 1 if kind == "side" else 3 if (kind == "up" and cm.UP_RECOIL[0]) else 2
                HD[i, k] = int(dmg)
    status, ps, pp, PF, PL, PH, NPAR, NREC, PHIST, n_max, n_nodes = run_particles(
        F0, L0, H0, T, hx, hb, steps_a, use_steps, HK, HD, tb.args(), max_particles)
    if status != 0:
        STATS["fallback"] += 1
        return cm.predict(obs, mems, hero, K, T=T, max_choices=max_choices, max_particles=max_particles,
                          group=group, hazards=hazards)
    STATS["jit"] += 1
    iids = [s.iid for s in sims0]
    names = tb.names
    # the final particles: p, logs, hazards, leaf node
    parts = []
    for slot, p in zip(ps, pp):
        logs = [_unpack_log(PL[slot, i], int(PF[slot, i, F_NLOG]), tb) for i in range(ns)]
        hzs = [_unpack_hz(PH[slot, i], int(PF[slot, i, F_NHZ])) for i in range(ns)]
        parts.append((float(p), logs, hzs, int(PHIST[slot])))
    buf = np.zeros((T + 1, 9))
    if not group:
        out = []
        order = sorted(range(len(parts)), key=lambda q: -parts[q][0])
        for q in order:
            p, logs, hzs, leaf = parts[q]
            recs = {}
            for i, iid in enumerate(iids):
                chain(NPAR, NREC, leaf, i, buf)
                recs[iid] = [_rec_tuple(r, names) for r in buf]
            chs = {iid: [c for c in logs[i] if c[0] in cm.CHOICE_KINDS] for i, iid in enumerate(iids)}
            rv = [c[3] for ch in chs.values() for c in ch if c[3] is not None]
            b = cm.Branch(p, chs, min(rv) if rv else None, recs,
                          [(iid, h) for i, iid in enumerate(iids) for h in hzs[i]] + extra, K, T, 1)
            b.logs = {iid: logs[i] for i, iid in enumerate(iids)}
            out.append(b)
        return cm.Prediction(out, T, int(n_max), (time.perf_counter() - t0) * 1000.0)
    groups: dict = {}
    for q, (p, logs, hzs, leaf) in enumerate(parts):
        key, chs = [], {}
        for i, iid in enumerate(iids):
            lg = logs[i]
            moves = [c for c in lg if c[0] in cm.MOVE_KINDS][:max_choices]
            evs = [c for c in lg if c[0] == "will_evade" and c[3] is not None and
                   (not moves or c[2] <= moves[-1][2])]
            key.append((iid, tuple((c[0], c[1]) for c in moves), tuple(c[1] for c in evs)))
            chs[iid] = sorted(moves + evs, key=lambda c: c[2])
        key = tuple(key)
        g = groups.get(key)
        if g is None:
            rv = [c[3] for ch in chs.values() for c in ch if c[3] is not None]
            groups[key] = g = {"p": 0.0, "q": [], "haz": [], "choices": chs, "reveal": min(rv) if rv else None,
                               "n": 0}
        g["p"] += p
        g["n"] += 1
        if g["n"] == 1:
            g["haz"].extend(extra)
        g["q"].append(q)
        for i, iid in enumerate(iids):
            g["haz"].extend((iid, h) for h in hzs[i])
    branches = []
    for key, g in sorted(groups.items(), key=lambda kv: -kv[1]["p"]):
        arr = {}
        for i, iid in enumerate(iids):
            if len(g["q"]) == 1:
                a_ = np.zeros((T + 1, 9))
                chain(NPAR, NREC, parts[g["q"][0]][3], i, a_)
                arr[iid] = a_
                continue
            allr = np.zeros((len(g["q"]) * (T + 1), 9))
            for n_, q in enumerate(g["q"]):
                chain(NPAR, NREC, parts[q][3], i, allr[n_ * (T + 1):(n_ + 1) * (T + 1)])
            arr[iid] = allr[dedupe(allr, np.zeros(1, np.int64))]
        hz = list({(h[0],) + tuple(round(v, 3) if isinstance(v, float) else v for v in h[1]): h
                   for h in g["haz"]}.values())
        b = JBranch(g["p"], g["choices"], g["reveal"], None, hz, K, T, g["n"])
        b._arr = arr
        b._names = names
        b._tb = tb
        branches.append(b)
    return cm.Prediction(branches, T, int(n_max), (time.perf_counter() - t0) * 1000.0)


__all__ = ["predict", "tables", "Tables", "STATS", "JBranch"]
