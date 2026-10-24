"""Map v2 stage T1: THE A1_n RECURSIVE TABLES - the no-dash table library (docs/plans/forum_map_v2.md, section 'THE
A1_n RECURSIVE TABLES' and the recursion paragraph 'THE COLLAPSE AND THE RECURSION'; the person's decision of
2026-10-23 after the failed w7 gate: 'build the recursive tables directly'; HANDOFF 'Task map2 - A1_n recursive
tables - stage T1', forum.md 103). Offline / planning code: nothing in the live bot imports it.

    from ssbot.map2 import tables as tb
    lib = tb.Lib.load()                                  # knowledge/1.0.30000/kinematics/a1n_tables_v1.npz
    fw = lib.forward(S, T=60, danger=boxes, floor=True)  # envelope.Fwd: the same clusters as Engine.forward with
    #                                                      opts OPT_NO_ADASH (the air dash off), only no physics
    lib.table(node, alpha)                               # the spec's table view: continue reference + frame-0 actions

THE RECURSIVE ELEMENT. A NODE is one cluster state of the M1 engine (ssbot.map2.env_jit) made RELATIVE: both lanes'
full kin_jit states with x relative to each lane's own x (the interval end it carries) and y relative to her height
(a 'free' node: the tables assume infinite height), or y absolute over the terrain (a 'floor instance': the ground,
and a free node within CLEAR of the floor / CLEAR_UP of the ceiling, where the terrain changes the frame). Its
identity is the engine's own merge key (env_jit.vkey, the floor-strict variant) without the heights, plus each lane's
horizontal state (vx, the extra air velocity, facing, move, the left / right keys held, the last step's x offsets,
...): everything that changes where she can be later (a ground dash's floor instance also holds QY / SY: its end
translates her from the drawn position). The air dash used is NOT in it (no table key: a segment property, carried
per pass; T2's bridge).

Per node, per frame STEP COUNT s (0 or 1: 50 Hz physics in 60 fps frames; the physics phase is a global clock, so the
node is phase-free and only the edges depend on s) and per PASS KIND (free space / over the terrain: the engine's two
merge keys and dominance filters) the node holds its EDGES: every child of the engine's frame (env_jit._children on
the node's representative lanes: the same candidates - gen_cands with the air dash off -, the same dominance filter)
with (child node, candidate code, the lane displacements [dlo, dhi] = the x OFFSET INTERVAL - with a phase slope where
the drawn position moves her -, dy, the events it spends, the QY / SY rules); a list for 'every choice' and one for
'the event limit reached'. A1_0 'continue' -> A1_1 is the going-on edge (one step later, widened by +-0.165 u in the
instant run; a frame without a step keeps the node): NO REDUNDANCY - a press at frame 10 lives in the node reached at
frame 10, not in A1_0. References compose by interval addition; a node's x reach through [a, b] is
[x_lo + a, x_hi + b] (the WIDEN of the state: the instant run's +-0.165 u / step, the float's lanes from its vx
interval - the lane states are in the node). A frame that depends on the phase beyond x (a recorded ground start
settling onto the floor) is expanded per cluster at her exact phase and QY / SY (a phase instance).

THE CHAIN (forward): from her exact state (ENTRY FROM ANY STATE: a steady state's node is in the library; a
transitional one - mid dash, down slash, Clawline, umbrella antic / inflate / deflate, bounce, sprint jump - is
expanded on the fly with the engine's kernel over its remaining choices until its branches meet the library's nodes),
frame by frame: each cluster (node, PY / QY / SY, x interval set, events) maps through its node's edges for the frame's
s; children with the engine's merge key (the class and the three heights' bits) merge as the engine merges them (the
sets unite, the fewest events, the extreme lane velocities). Danger boxes cut each child at its height, walls clip
(optional, the spec's use-time rule; the search cuts walls as danger), the terrain routes a cluster near it through
its floor instance. Back-pointers are kept on clusters (pieces), never on a flattened map. Nodes / edges missing from
the library are expanded on the fly and kept.

EXACTNESS: every edge is the engine's own per-cluster frame on the node's representative lanes and the chain merges
on the engine's key, so the chain's clusters are the engine's (heights bit-equal; x equal to the rounding of relative
vs absolute coordinates, < 1e-13 u). THE CLOSURE DOES NOT CONVERGE: exact vertical states multiply with the event
history (the float's close / attack cancel, the Clawline's antic decay, the hang leave off-lattice vy), so the library
is the memoised engine - a depth-limited core plus the nodes the search's own passes meet -, not a few hundred tables.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np
from numba import njit

from ssbot.knowledge import kinematics as km
from ssbot.knowledge.kin_jit import f32, ge32, update
from ssbot.knowledge.kinematics import (
    K, PX, PY, QX, QY, SX, SY, VX, VY, ALPHA, FACE, GROUND, MODE, MODE_T, PHASE, MOVE, PREV, XVX, DS_HS, HVX, SP_X,
    ATK_KIND, TS, WF_S, WF_PH, RX0, RY0, HARD, AIRDASHED, ATTACKING, ATK_T, ATK_PDIR, INV_T,
    B_JUMP, B_ATTACK, B_DASH, B_LEFT, B_RIGHT, B_DOWN, M_DASH, M_SPRINT, P_FDT, P_HEAD, P_FOOT, P_SPR_GRACE)
from ssbot.map2 import env_jit as ej
from ssbot.map2.env_jit import _children, vkey, khash, keq, cond_of, claw_allowed, NKEY, NC, C_EV, C_CJ

VERSION = 1
TABLES_PATH = km.REPO / "knowledge" / "1.0.30000" / "kinematics" / f"a1n_tables_v{VERSION}.npz"


def tables_path(claw: bool = True, terrain: str = "floor") -> Path:
    """The knowledge file of a library: the Clawline in (the spec's frame-0 actions) and the floor by default; the
    search's passes run without the Clawline over the floor and the ceiling ('arena')."""
    if claw and terrain == "floor":
        return TABLES_PATH
    return TABLES_PATH.with_name(f"a1n_tables_v{VERSION}_{terrain}{'' if claw else '_noclaw'}.npz")
FLOOR_TOP = 3.015          # the Forum floor (her box bottom standing; envelope.FLOOR_BB, strike.FLOOR)
CEIL_BOT = 15.15           # the Forum's flat ceiling (search.CEIL: its bottom, her box top bumps there)
CLEAR = 2.5                # a free node's frame is the floor's own when her box bottom is >= CLEAR over the floor: the
#                            landing (<= 0.6 u per step), the umbrella's ground ray (1.1 u), a slash's terrain thunk
#                            (~1.2 u under her feet) - validated against the engine on the floor (t1_tables exact)
CLEAR_UP = 1.0             # ... and the ceiling's when her box top is >= CLEAR_UP under it (a rise <= 0.37 u per step)
TERRAINS = ("floor", "arena")   # the floor (envelope.floor_terrain, M1's validation) / the floor and the ceiling
#                                 (search.arena_terrain: the search's passes; its walls are danger boxes)
OPTS = ej.OPT_CLAW | ej.OPT_TF8 | ej.OPT_NO_ADASH      # the engine's defaults with the air dash off

# ---- the node identity ------------------------------------------------------------------------------------------
_HD = np.array([VX, XVX, FACE, MOVE, PREV, QX, SX, DS_HS, HVX, SP_X, ATK_KIND], dtype=np.int64)
NHD = _HD.shape[0]
NIDK = NKEY + 2 * NHD + 5
_KPY, _KQY, _KSY = 0, 1, 2                    # vkey's slots of PY, QY, SY (env_jit asserts the order)
_ADS = ej._ADS
_FT = ej._FT
_MT = ej._MT
# node int columns (I_CLS: the merge class with the floor-strict key - the floor passes; I_CLSF: the engine's
# free-space key - the free passes merge as the engine does there)
I_HASH, I_CLS, I_ABS, I_COND, I_MODE, I_PHASE, I_GROUND, I_KIND, I_CLSF, I_ADEP = range(10)
NINTC = 10
# node float columns: the representative's vy, and a PHASE INSTANCE's physics phase (-1: none). A node whose frame
# depends on the phase beyond its x (the drawn position read by a ground sprint's start when her y is still settling:
# a recorded ground start a little off the model's rest height) gets I_ADEP's bit s; the chain then expands it at
# her exact phase (a phase instance) instead of using its edges for that step count
V_VY, V_ALF = 0, 1
# edge columns
EI_CH, EI_CAND, EI_YABS = range(3)
# T2: the child's air dash used after the frame (EI_AD: the lanes' AIRDASHED - the dash fired, or a landing restored
# it, HERO2 H2_LAND_DASH) and EI_ENT: a BRIDGE ENTRY (the full candidates' air-dash children: a dash pressed / held /
# queued in the air - every candidate OPT_NO_ADASH drops)
EI_AD, EI_ENT = 3, 4
NEI = 5
# T2: the edge lists per node and step count: EOFF[n, s, 4 du + 2 fl + lim] - du 0: no air dash (T1: OPT_NO_ADASH, the
# air dash unused), du 1: every candidate with the air dash unused (the entries marked), du 2: every candidate with
# the air dash used (the lanes' AIRDASHED set: the dash's own frames, the umbrella's dash press that only closes it, a
# queued dash) - fl the pass kind, lim the event limit reached
NDU = 3
EF_DLO, EF_DHI, EF_DY, EF_SLO, EF_SHI, EF_NEV, EF_QM, EF_QV, EF_SM, EF_SV = range(10)
NEF = 10
# the child's QY / SY (the engine's key holds them absolute) from the parent's: QM 0 QY kept, 1 QY = the parent's PY
# (a physics step: FixedUpdate's start), 2 QY = the child's PY (the Clawline's control), 4 QY = the drawn y (a ground
# sprint's start: QY + phase (SY - QY)), 3 QY = the child's PY + QV (none of these: counted); SM 0 SY kept, 1 SY = the
# child's PY, 2 SY = the PY after the steps (SV: absolute for a floor instance's edge, else the step's dy), 3 the
# child's PY + SV (counted)
# counters
C_NODES, C_EDGES, C_CLS, C_OVF, C_AVDEP, C_DYUPD, C_SLOPE, C_INST, C_MERGE, C_EXP, C_QSFB = range(11)
NCNT = 11
# press flags per node and step count (the state after the frame's steps, before its Update: what a press meets)
PF_CLAW, PF_ATK, PF_DSLASH, PF_DASH, PF_AIR = 1, 2, 4, 8, 16
ALPHA_S = ((0.05, 0.15, 0.1), (0.5, 0.9, 0.7))    # the phase used for s = 0 / 1 (and the slope / its check)


@njit(cache=True, error_model="numpy")
def vkey_rel(L, cu, P, floor, absy, out):
    """The engine's merge key (env_jit.vkey; floor: the floor-strict variant) of lanes L without the height (absy:
    with it: PY) and without the previous / last step's heights (QY / SY: the chain carries them per cluster, as it
    carries PY) and the air dash used (constant in a no-dash pass: the chain carries it). Nothing else is
    canonicalised beyond the engine's own (the raw fall timer and the ground sprint's time stay, as in the engine:
    its merges - and with an event limit the events a merged cluster keeps - are reproduced exactly)."""
    vkey(L[1], cu, P, floor, out)
    out[_KPY] = L[1, PY] if absy else 0.0
    out[_KQY] = 0.0
    out[_KSY] = 0.0
    out[_ADS] = 0.0


@njit(cache=True, error_model="numpy")
def ident(L, cu, P, absy, alf, out):
    """The node identity of the relative lanes L [2, K] (y relative unless absy) and cu: vkey_rel (floor-strict),
    + each lane's horizontal state, the time scale, a phase instance's phase (alf, -1: none)."""
    vkey_rel(L, cu, P, True, absy, out)
    if absy and L[1, MODE] == M_DASH and L[1, GROUND] > 0:
        # the ground dash: its end translates her from the DRAWN position (QY + phase (SY - QY): the previous / last
        # step's heights - a recorded ground start a little off the rest height still settles there), so a ground
        # dash's floor instance holds them (absolute, as the engine's key); a phase dependence they leave (QY != SY)
        # makes the expansion's phase runs differ: phase instances (I_ADEP)
        out[_KQY] = L[1, QY] + 0.0
        out[_KSY] = L[1, SY] + 0.0
    o = NKEY
    for ln in range(2):
        for i in range(NHD):
            f = _HD[i]
            v = L[ln, f]
            if f == PREV:
                v = np.float64(np.int64(v) & (B_LEFT | B_RIGHT))
            out[o] = v + 0.0
            o += 1
    out[o] = L[1, TS] + 0.0
    out[o + 1] = L[1, WF_S] + 0.0
    out[o + 2] = L[1, WF_PH] + 0.0
    out[o + 3] = 1.0 if absy else 0.0
    out[o + 4] = alf + 0.0


@njit(cache=True, error_model="numpy")
def rel_x(L):
    for ln in range(2):
        px = L[ln, PX]
        L[ln, PX] = 0.0
        L[ln, QX] -= px
        L[ln, SX] -= px
        L[ln, RX0] -= px


@njit(cache=True, error_model="numpy")
def rel_y(L):
    for ln in range(2):
        py = L[ln, PY]
        L[ln, PY] = 0.0
        L[ln, QY] -= py
        L[ln, SY] -= py
        L[ln, RY0] -= py


@njit(cache=True, error_model="numpy")
def _hfind(HT, h, NID, key, NINT):
    """Slot of key (hash h) in the node hash table HT: (slot, node id or -1)."""
    m = HT.shape[0] - 1
    slot = h & m
    while True:
        j = HT[slot]
        if j < 0:
            return slot, -1
        if NINT[j, I_HASH] == h and keq(NID[j], key):
            return slot, j
        slot = (slot + 1) & m


@njit(cache=True, error_model="numpy")
def _cls_get(CHT, CK, CH, CNT, key):
    """The merge class of a vkey row (the identity's first NKEY slots, height zeroed): its id (new ones appended)."""
    h = khash(key)
    m = CHT.shape[0] - 1
    slot = h & m
    while True:
        j = CHT[slot]
        if j < 0:
            break
        if CH[j] == h and keq(CK[j], key):
            return j
        slot = (slot + 1) & m
    n = CNT[C_CLS]
    if n >= CK.shape[0] or 2 * (n + 1) > CHT.shape[0]:
        CNT[C_OVF] |= 4
        return -1
    CK[n, :] = key
    CH[n] = h
    CHT[slot] = n
    CNT[C_CLS] = n + 1
    return n


@njit(cache=True, error_model="numpy")
def node_get(L, cu, absy, alf, P, NL, NCU, NID, NINT, NVY, EOFF, HT, CHT, CK, CH, CNT, key, ckey):
    """The node of relative lanes L / cu (absy: a floor instance, y absolute; alf >= 0: a phase instance): its id,
    appended when new (-1 when a table is full: CNT[C_OVF] set)."""
    ident(L, cu, P, absy, alf, key)
    h = khash(key)
    slot, j = _hfind(HT, h, NID, key, NINT)
    if j >= 0:
        return j
    n = CNT[C_NODES]
    if n >= NL.shape[0] or 2 * (n + 1) > HT.shape[0]:
        CNT[C_OVF] |= 1
        return -1
    for i in range(NKEY):
        ckey[i] = key[i]
    ckey[_KPY] = 0.0
    c = _cls_get(CHT, CK, CH, CNT, ckey)
    if c < 0:
        return -1
    vkey_rel(L, cu, P, False, False, ckey)
    cf = _cls_get(CHT, CK, CH, CNT, ckey)
    if cf < 0:
        return -1
    NL[n, 0, :] = L[0]
    NL[n, 1, :] = L[1]
    NL[n, 0, AIRDASHED] = 0.0
    NL[n, 1, AIRDASHED] = 0.0
    NCU[n, :] = cu
    NCU[n, C_EV] = 0.0
    NID[n, :] = key
    NINT[n, I_HASH] = h
    NINT[n, I_CLS] = c
    NINT[n, I_ABS] = 1 if absy else 0
    NINT[n, I_COND] = cond_of(NL[n, 1], NCU[n], P)
    NINT[n, I_MODE] = np.int64(L[1, MODE])
    NINT[n, I_PHASE] = np.int64(L[1, PHASE])
    NINT[n, I_GROUND] = 1 if L[1, GROUND] > 0 else 0
    NINT[n, I_KIND] = -1
    NINT[n, I_CLSF] = cf
    NINT[n, I_ADEP] = 0
    NVY[n, V_VY] = L[1, VY]
    NVY[n, V_ALF] = alf
    for s in range(2):
        for md in range(4 * NDU):
            EOFF[n, s, md, 0] = -1
            EOFF[n, s, md, 1] = 0
    HT[slot] = n
    CNT[C_NODES] = n + 1
    return n


@njit(cache=True, error_model="numpy")
def _press_flags(x0, cu, dt, udt, P, TT):
    """What a press meets after the frame's steps (x0: lane 1 then; press.py's rules): the Clawline (claw_allowed),
    an attack that starts in this Update, a down slash that starts, an air dash that starts (with the air dash
    restored: 'a dash press allowed' - whether it is used is the segment's), airborne."""
    pf = 0
    if x0[GROUND] <= 0:
        pf |= PF_AIR
    if cu[C_CJ] >= 0:
        return pf                                    # the Clawline block: no Update
    if claw_allowed(x0, cu, P):
        pf |= PF_CLAW
    held = np.int64(x0[PREV]) & (B_JUMP | B_DASH)
    for k in range(3):
        x = x0.copy()
        if k < 2:
            x[PREV] = np.float64(held)
            pre = x[ATTACKING] > 0 and x[ATK_T] == 0.0
            m = held | B_ATTACK | (B_DOWN if k == 1 else 0)
            update(x, m, 0, dt, udt, P, TT)
            st = x[ATTACKING] > 0 and x[ATK_T] == 0.0 and not pre
            if st and k == 0:
                pf |= PF_ATK
            if st and k == 1 and x[ATK_PDIR] == 2.0:
                pf |= PF_DSLASH
        else:
            x[AIRDASHED] = 0.0
            h2 = held & ~B_DASH
            x[PREV] = np.float64(h2)
            update(x, h2 | B_DASH | B_RIGHT, 0, dt, udt, P, TT)
            if x[MODE] == M_DASH and x[GROUND] <= 0:
                pf |= PF_DASH
    return pf


@njit(cache=True, error_model="numpy")
def expand(n, s, fl, du, P, udt, TTf, TTg, opts, hh, NL, NCU, NID, NINT, NVY, EOFF, PFL, EI, EF, HT, CHT, CK, CH,
           CNT):
    """The node's edges for step count s (both the full list and the one with the event limit reached), as the
    engine's frame (env_jit._children) on its representative lanes, for a pass kind fl (1: over the terrain - the
    engine's floor-strict merge key and dominance filter -, 0: free space - its free-space key) and dash status du
    (T2: 0 no air dash - T1's lists -, 1 every candidate with the air dash unused, 2 with it used):
    EOFF[n, s, 4 du + 2 fl + lim]. Returns False when a table is full."""
    base = 4 * du + 2 * fl
    if EOFF[n, s, base, 0] >= 0:
        return True
    if du > 0:
        opts = opts & ~ej.OPT_NO_ADASH
    MK = 48
    absy = NINT[n, I_ABS] == 1
    TT = TTg if absy else TTf
    tmp = np.empty((2, K))
    tcu = np.empty(NC)
    cands = np.empty(32, dtype=np.int64)
    kid = np.empty((MK, 2, K))
    kcu = np.empty((MK, NC))
    kkey = np.empty((MK, NKEY))
    kkeep = np.empty(MK, dtype=np.bool_)
    kcand = np.empty(MK, dtype=np.int64)
    kuse = np.empty(MK, dtype=np.int64)
    key1 = np.empty(NKEY)
    key2 = np.empty(NKEY)
    olo = np.empty(64)
    ohi = np.empty(64)
    wlo = np.empty(64)
    whi = np.empty(64)
    npc = np.zeros(MK, dtype=np.int64)
    plo = np.empty((MK, 64))
    phi = np.empty((MK, 64))
    dl = np.empty(MK)
    dh = np.empty(MK)
    st = np.zeros(2, dtype=np.int64)
    boxes = np.zeros((0, 4))
    IV = np.zeros((1, 2))
    key = np.empty(NIDK)
    ckey = np.empty(NKEY)
    L = np.empty((2, K))
    dl2 = np.empty(MK)
    dh2 = np.empty(MK)
    py2 = np.empty(MK)
    cnd2 = np.empty(MK, dtype=np.int64)
    fdt = P[P_FDT]
    dt = f32(udt)
    alf = NVY[n, V_ALF]
    a1 = ALPHA_S[s][0] if alf < 0 else alf
    a2 = ALPHA_S[s][1] if alf < 0 else alf
    # both edge lists are written, then committed together (a table filling up between them must not leave the
    # first one set and the event-limit one empty: the retry redoes both)
    e_start = CNT[C_EDGES]
    oe0 = np.zeros(2, dtype=np.int64)
    on = np.zeros(2, dtype=np.int64)
    for md in range(2):
        cu0 = NCU[n].copy()
        o = opts
        if md == 1:
            cu0[C_EV] = 1.0                       # the event limit reached: only the free choices (gen_cands)
            o = opts | (1 << 8)
        # the slope run first (a second phase of the same step count): the drawn position (a ground dash's end
        # translates from it) is the only phase dependence in the frame
        nk2 = 0
        for rep in range(2):
            a = a2 if rep == 0 else a1
            L[0, :] = NL[n, 0]
            L[1, :] = NL[n, 1]
            L[0, ALPHA] = a
            L[1, ALPHA] = a
            if du == 2:
                L[0, AIRDASHED] = 1.0
                L[1, AIRDASHED] = 1.0
            cu = cu0.copy()
            nk = _children(L[0], L[1], cu, udt, P, TT, o, fl == 1, boxes, 0, 0, IV, 0, 1, hh, tmp, tcu, cands, kid,
                           kcu, kkey, kkeep, kcand, kuse, key1, key2, olo, ohi, wlo, whi, npc, plo, phi, dl, dh, st)
            if rep == 0:
                nk2 = nk
                for k in range(nk):
                    dl2[k] = dl[k] if kkeep[k] else 0.0
                    dh2[k] = dh[k] if kkeep[k] else 0.0
                    py2[k] = kid[k, 1, PY] if kkeep[k] else 0.0
                    cnd2[k] = kcand[k] if kkeep[k] else -1
        steps = np.int64(math.floor(a1 + dt / fdt + 1e-9))
        if steps != s:
            CNT[C_OVF] |= 8                          # (the phase choice does not give s steps: a parameter error)
        if md == 0 and du == 0:
            PFL[n, s] = _press_flags(tmp[1], tcu, dt, udt, P, TT)
        air_st = tmp[1, GROUND] <= 0                 # (after the frame's steps: an entry is a dash candidate there)
        e0 = CNT[C_EDGES]
        ne = 0
        ypar = NL[n, 1, PY]
        ystep = tmp[1, PY]
        for k in range(nk):
            if not kkeep[k] or npc[k] == 0:
                continue
            if k >= nk2 or cnd2[k] != kcand[k] or py2[k] != kid[k, 1, PY]:
                if (NINT[n, I_ADEP] & (1 << s)) == 0:
                    CNT[C_AVDEP] += 1                # the frame depends on the phase beyond x: phase instances
                NINT[n, I_ADEP] |= 1 << s
            C = kid[k].copy()
            ccu = kcu[k].copy()
            cad = 1 if C[1, AIRDASHED] > 0 else 0
            ent = 1 if (du == 1 and (kcand[k] & ej.CB_D) != 0 and air_st) else 0
            # the QY / SY rules (bit-checked on the representative, the natural rule of the step count first)
            pyp, qyp, syp = L[1, PY], L[1, QY], L[1, SY]
            cq, cs, cp = C[1, QY], C[1, SY], C[1, PY]
            qm = 3
            qv = cq - cp
            for cand_m in ((0, 2, 1, 4) if s == 0 else (1, 2, 0, 4)):
                v = qyp if cand_m == 0 else (pyp if cand_m == 1 else (cp if cand_m == 2 else qyp + a1 * (syp - qyp)))
                if v == cq:
                    qm = cand_m
                    qv = 0.0
                    break
            sm = 3
            sv = cs - cp
            for cand_m in ((0, 1, 2) if s == 0 else (1, 2, 0)):
                v = syp if cand_m == 0 else (cp if cand_m == 1 else ystep)
                if v == cs:
                    sm = cand_m
                    sv = 0.0 if cand_m != 2 else (ystep if absy else ystep - ypar)
                    break
            if qm == 3 or sm == 3:
                CNT[C_QSFB] += 1
            nev = ccu[C_EV] - cu0[C_EV]
            ccu[C_EV] = 0.0
            gnd = C[1, GROUND] > 0
            yabs = absy
            dy = C[1, PY] if absy else C[1, PY] - ypar
            if not absy and C[1, PY] != ystep:
                CNT[C_DYUPD] += 1                    # the Update moved y in free space (never expected)
            rel_x(C)
            if not (absy and gnd):
                rel_y(C)                             # a free node (a floor instance's airborne child: y absolute in
            #                                          the edge; the chain routes it back near the floor)
            cid = node_get(C, ccu, absy and gnd, -1.0, P, NL, NCU, NID, NINT, NVY, EOFF, HT, CHT, CK, CH, CNT, key,
                           ckey)
            if cid < 0:
                CNT[C_EDGES] = e_start
                return False
            e = e0 + ne
            if e >= EI.shape[0]:
                CNT[C_OVF] |= 2
                CNT[C_EDGES] = e_start
                return False
            # the lane displacements at the two phases: equal, or the drawn-position slope (affine in the phase)
            slo = 0.0
            shi = 0.0
            if a2 != a1 and (dl2[k] != dl[k] or dh2[k] != dh[k]):
                slo = (dl2[k] - dl[k]) / (a2 - a1)
                shi = (dh2[k] - dh[k]) / (a2 - a1)
                CNT[C_SLOPE] += 1
            EI[e, EI_CH] = cid
            EI[e, EI_CAND] = kcand[k]
            EI[e, EI_YABS] = 1 if yabs else 0
            EI[e, EI_AD] = cad
            EI[e, EI_ENT] = ent
            EF[e, EF_DLO] = dl[k] - slo * a1
            EF[e, EF_DHI] = dh[k] - shi * a1
            EF[e, EF_DY] = dy
            EF[e, EF_SLO] = slo
            EF[e, EF_SHI] = shi
            EF[e, EF_NEV] = nev
            EF[e, EF_QM] = qm
            EF[e, EF_QV] = qv
            EF[e, EF_SM] = sm
            EF[e, EF_SV] = sv
            ne += 1
        CNT[C_EDGES] = e0 + ne
        oe0[md] = e0
        on[md] = ne
    for md in range(2):
        EOFF[n, s, base + md, 0] = oe0[md]
        EOFF[n, s, base + md, 1] = on[md]
    CNT[C_EXP] += 1
    return True


@njit(cache=True, error_model="numpy")
def closure(i0, i1, P, udt, TTf, TTg, opts, hh, NL, NCU, NID, NINT, NVY, EOFF, PFL, EI, EF, HT, CHT, CK, CH, CNT):
    """Expand nodes i0 .. (every node appended meanwhile) for both step counts, up to node i1: the library's closure
    (a breadth-first pass: ids are in discovery order). Returns the next node to expand (< CNT[C_NODES] when a table
    filled up)."""
    i = i0
    while i < CNT[C_NODES] and i < i1:
        for s in range(2):
            if not expand(i, s, 1, 0, P, udt, TTf, TTg, opts, hh, NL, NCU, NID, NINT, NVY, EOFF, PFL, EI, EF, HT, CHT,
                          CK, CH, CNT):
                return i
        i += 1
    return i


# ---- the chain ----------------------------------------------------------------------------------------------------

@njit(cache=True, error_model="numpy")
def _cond(c, dbit):
    """A node's end-condition bits with the pass's air-dash-used bit (env_jit.cond_of: not inside a Clawline block,
    whose bits are the block's alone)."""
    return c if (c & ej.COND_CLAWBLK) != 0 else c | dbit

@njit(cache=True, error_model="numpy")
def near(py, ylo, TP, P):
    """A cluster at her PY in [ylo, py] (a band: its range) is within the terrain's reach: its frame is the terrain
    instance's. TP: (has_floor, floor top, clear, has_ceiling, ceiling bottom, clear up)."""
    if TP[0] > 0 and (ylo - P[P_FOOT] - TP[1]) < TP[2]:
        return True
    return TP[3] > 0 and (TP[4] - (py + P[P_HEAD])) < TP[5]


@njit(cache=True, error_model="numpy")
def _ich(n, pb, qb, sb):
    h = np.uint64(n & 0x7FFFFFFFFFFFFFFF) * np.uint64(0x9E3779B97F4A7C15)
    h = (h ^ np.uint64(pb)) * np.uint64(1099511628211)
    h = (h ^ np.uint64(qb)) * np.uint64(1099511628211)
    h = h ^ np.uint64(sb)
    return np.int64(h & np.uint64(0x7FFFFFFFFFFFFFFF))


@njit(cache=True, error_model="numpy")
def _instance(n, py, P, NL, NCU, NID, NINT, NVY, EOFF, HT, CHT, CK, CH, CNT, ICK, ICT, key, ckey):
    """The floor instance of free node n at height py (her PY, absolute): cached by (n, the bits of py)."""
    pb = np.int64(np.array([py]).view(np.int64)[0])
    h = _ich(n, pb, 0, 0)
    m = ICT.shape[0] - 1
    slot = h & m
    while True:
        j = ICT[slot]
        if j < 0:
            break
        if ICK[j, 0] == n and ICK[j, 1] == pb and ICK[j, 3] == 0 and ICK[j, 4] == 0:
            return ICK[j, 2]
        slot = (slot + 1) & m
    L = NL[n].copy()
    for ln in range(2):
        L[ln, PY] += py
        L[ln, QY] += py
        L[ln, SY] += py
        L[ln, RY0] += py
    L[0, PY] = py
    L[1, PY] = py
    g = node_get(L, NCU[n].copy(), True, -1.0, P, NL, NCU, NID, NINT, NVY, EOFF, HT, CHT, CK, CH, CNT, key, ckey)
    if g < 0:
        return -1
    c = CNT[C_INST]
    if c >= ICK.shape[0] or 2 * (c + 1) > ICT.shape[0]:
        CNT[C_OVF] |= 16
        return -1
    ICK[c, 0] = n
    ICK[c, 1] = pb
    ICK[c, 2] = g
    ICK[c, 3] = 0
    ICK[c, 4] = 0
    ICT[slot] = c
    CNT[C_INST] = c + 1
    return g


@njit(cache=True, error_model="numpy")
def _ainst(n, alpha, py, qy, sy, P, NL, NCU, NID, NINT, NVY, EOFF, HT, CHT, CK, CH, CNT, ICK, ICT, key, ckey):
    """The phase instance of node n at her exact physics phase alpha and the cluster's own QY / SY (the drawn y reads
    them; py: her PY): cached by (n, the bits of alpha, QY, SY) in the floor instances' table (node id stored
    negative)."""
    ab = np.array([alpha, qy, sy])
    v = ab.view(np.int64)
    pb, qb, sb = v[0], v[1], v[2]
    nn = -(n + 1)
    h = _ich(nn, pb, qb, sb)
    m = ICT.shape[0] - 1
    slot = h & m
    while True:
        j = ICT[slot]
        if j < 0:
            break
        if ICK[j, 0] == nn and ICK[j, 1] == pb and ICK[j, 3] == qb and ICK[j, 4] == sb:
            return ICK[j, 2]
        slot = (slot + 1) & m
    L = NL[n].copy()
    off = 0.0 if NINT[n, I_ABS] == 1 else py
    for ln in range(2):
        L[ln, QY] = qy - off
        L[ln, SY] = sy - off
    g = node_get(L, NCU[n].copy(), NINT[n, I_ABS] == 1, alpha, P, NL, NCU, NID, NINT, NVY, EOFF, HT, CHT, CK, CH, CNT,
                 key, ckey)
    if g < 0:
        return -1
    c = CNT[C_INST]
    if c >= ICK.shape[0] or 2 * (c + 1) > ICT.shape[0]:
        CNT[C_OVF] |= 16
        return -1
    ICK[c, 0] = nn
    ICK[c, 1] = pb
    ICK[c, 2] = g
    ICK[c, 3] = qb
    ICK[c, 4] = sb
    ICT[slot] = c
    CNT[C_INST] = c + 1
    return g


@njit(cache=True, error_model="numpy")
def _merge(a, b, P, NL, NCU, NID, NINT, NVY, EOFF, HT, CHT, CK, CH, CNT, key, ckey):
    """Two nodes of one merge class at one height merged as the engine merges clusters: a's lanes (the first child)
    with the extreme lane velocities (lane 0 the lower vx / extra vx, lane 1 the higher)."""
    L = NL[a].copy()
    ch = False
    if NL[b, 0, VX] < L[0, VX] or NL[b, 1, VX] > L[1, VX] or NL[b, 1, XVX] > L[1, XVX] or NL[b, 0, XVX] < L[0, XVX]:
        ch = True
    if not ch:
        return a                                 # the same lane velocities: the engine keeps the first child's
    if NL[b, 0, VX] < L[0, VX]:
        L[0, VX] = NL[b, 0, VX]
    if NL[b, 1, VX] > L[1, VX]:
        L[1, VX] = NL[b, 1, VX]
    if NL[b, 1, XVX] > L[1, XVX]:
        L[1, XVX] = NL[b, 1, XVX]
    if NL[b, 0, XVX] < L[0, XVX]:
        L[0, XVX] = NL[b, 0, XVX]
    CNT[C_MERGE] += 1
    return node_get(L, NCU[a].copy(), NINT[a, I_ABS] == 1, NVY[a, V_ALF], P, NL, NCU, NID, NINT, NVY, EOFF, HT, CHT,
                    CK, CH, CNT, key, ckey)


@njit(cache=True, error_model="numpy")
def chain(n0, py0, qy0, sy0, ivs0, alpha0, T, boxes, box_off, maxev, TP, wall, wlo, whi, dflags, band_q, P, udt, TTf,
          TTg, opts, hh, NL, NCU, NID, NINT, NVY, EOFF, PFL, EI, EF, HT, CHT, CK, CH, CNT, ICK, ICT, cap_frame, cap_pc,
          cap_iv, cap_cl):
    """The table chain from one start (node n0 at her height py0 - her PY -, x intervals ivs0, her physics phase
    alpha0) over T frames: env_jit.forward's outputs (the same clusters and pieces) plus each cluster's node and
    events. boxes / box_off: the danger per frame (her centre's space), maxev the event limit (0: none), the floor
    (has_floor, its top) routes clusters whose box bottom is under clear over it through their floor instances; wall:
    clip the x intervals to [wlo, whi] after every step (the spec's use-time walls: not the engine's); dflags (T2): bit 0
    the air dash used at the start, bit 1 THE DASH MODE (the forward set with the air dash: each cluster carries its
    air-dash bit - unused: the no-dash lists + the bridge's entries; used: the full lists -, a key of the merge as in
    the engine), bit 2 a landing restores the dash (HERO2 H2_LAND_DASH; the no-dash lists' clusters drop the bit when
    the edge lands). band_q > 0: the flattened layer - clusters of one node whose
    heights lie within band_q merge into a band (y range [cl_ylo, cl_y]; an upper bound, never for witnesses). TP: the
    terrain's reach (near; has_floor = TP[0] > 0)."""
    has_floor = TP[0] > 0 or TP[3] > 0
    fl = 1 if has_floor else 0
    fdt = P[P_FDT]
    dt = f32(udt)
    cl_off = np.zeros(T + 2, dtype=np.int64)
    cl_y = np.empty(cap_cl)
    cl_ylo = np.empty(cap_cl)
    cl_vy = np.empty(cap_cl)
    cl_cond = np.empty(cap_cl, dtype=np.int64)
    cl_mode = np.empty(cap_cl, dtype=np.int64)
    cl_phase = np.empty(cap_cl, dtype=np.int64)
    cl_iv0 = np.empty(cap_cl, dtype=np.int64)
    cl_ivn = np.empty(cap_cl, dtype=np.int64)
    cl_node = np.empty(cap_cl, dtype=np.int64)
    cl_ev = np.empty(cap_cl)
    cl_ad = np.empty(cap_cl, dtype=np.int64)
    IV = np.empty((cap_iv, 2))
    pc_cl = np.empty(cap_pc, dtype=np.int64)
    pc_par = np.empty(cap_pc, dtype=np.int64)
    pc_cand = np.empty(cap_pc, dtype=np.int64)
    pc_lo = np.empty(cap_pc)
    pc_hi = np.empty(cap_pc)
    pc_dlo = np.empty(cap_pc)
    pc_dhi = np.empty(cap_pc)
    stats = np.zeros((T + 1, 8), dtype=np.int64)
    flags = np.zeros(5, dtype=np.int64)          # overflow: frame, pieces, intervals, clusters, library
    key = np.empty(NIDK)
    ckey = np.empty(NKEY)
    # frame 0
    cur_n = np.empty(cap_frame, dtype=np.int64)
    cur_y = np.empty(cap_frame)
    cur_yl = np.empty(cap_frame)
    cur_e = np.empty(cap_frame)
    cur_q = np.empty(cap_frame)
    cur_s = np.empty(cap_frame)
    nxt_q = np.empty(cap_frame)
    nxt_s = np.empty(cap_frame)
    nxt_n = np.empty(cap_frame, dtype=np.int64)
    nxt_y = np.empty(cap_frame)
    nxt_yl = np.empty(cap_frame)
    nxt_e = np.empty(cap_frame)
    cur_d = np.empty(cap_frame, dtype=np.int64)
    nxt_d = np.empty(cap_frame, dtype=np.int64)
    ad0 = dflags & 1
    dmode = (dflags & 2) != 0
    ldash = (dflags & 4) != 0
    cur_d[0] = ad0
    cur_n[0] = n0
    cur_y[0] = py0
    cur_yl[0] = py0
    cur_e[0] = 0.0
    cur_q[0] = qy0
    cur_s[0] = sy0
    ncl = 1
    niv = 0
    npc = 0
    for i in range(ivs0.shape[0]):
        IV[niv, 0] = ivs0[i, 0]
        IV[niv, 1] = ivs0[i, 1]
        niv += 1
    cl_y[0] = py0 + hh
    cl_ylo[0] = py0 + hh
    cl_vy[0] = NVY[n0, V_VY]
    cl_cond[0] = _cond(NINT[n0, I_COND], ej.COND_DASHED if ad0 else 0)
    cl_ad[0] = ad0
    cl_mode[0] = NINT[n0, I_MODE]
    cl_phase[0] = NINT[n0, I_PHASE]
    cl_iv0[0] = 0
    cl_ivn[0] = niv
    cl_node[0] = n0
    cl_ev[0] = 0.0
    cl_off[0] = 0
    cl_off[1] = 1
    stats[0, 0] = 1
    ntot = 1
    khs_c = np.empty(cap_frame, dtype=np.int64)
    khs_b = np.empty(cap_frame, dtype=np.int64)
    khs_q = np.empty(cap_frame, dtype=np.int64)
    khs_s = np.empty(cap_frame, dtype=np.int64)
    qsb = np.empty(2)
    ch_first = np.empty(cap_frame, dtype=np.int64)
    fp_cap = 8 * cap_frame
    fp_next = np.empty(fp_cap, dtype=np.int64)
    fp_ch = np.empty(fp_cap, dtype=np.int64)
    fp_par = np.empty(fp_cap, dtype=np.int64)
    fp_cand = np.empty(fp_cap, dtype=np.int64)
    fp_lo = np.empty(fp_cap)
    fp_hi = np.empty(fp_cap)
    fp_dlo = np.empty(fp_cap)
    fp_dhi = np.empty(fp_cap)
    olo = np.empty(64)
    ohi = np.empty(64)
    wlo_ = np.empty(64)
    whi_ = np.empty(64)
    klo = np.empty(64)
    khi = np.empty(64)
    sl = np.empty(256)
    sh_ = np.empty(256)
    HSZ = 1
    while HSZ < 4 * cap_frame:
        HSZ *= 2
    HMASK = HSZ - 1
    htab = np.full(HSZ, -1, dtype=np.int64)
    alpha = alpha0
    yb = np.empty(1)
    for t in range(1, T + 1):
        for i in range(HSZ):
            htab[i] = -1
        a_ = alpha + dt / fdt
        s = np.int64(math.floor(a_ + 1e-9))
        a_st = alpha
        alpha = min(max(a_ - s, 0.0), 1.0)
        if s > 1:
            flags[4] |= 32                       # (more than one physics step in a frame: not in the tables)
            s = 1
        nch = 0
        nfp = 0
        b0 = box_off[t]
        b1 = box_off[t + 1]
        base_g = cl_off[t - 1]
        for c in range(ncl):
            g = base_g + c
            n = cur_n[c]
            py = cur_y[c]
            src = n
            if NINT[n, I_ABS] == 0 and has_floor and near(py, cur_yl[c], TP, P):
                src = _instance(n, py, P, NL, NCU, NID, NINT, NVY, EOFF, HT, CHT, CK, CH, CNT, ICK, ICT, key, ckey)
                if src < 0:
                    flags[4] |= CNT[C_OVF]
                    return (cl_off, cl_y[:ntot], cl_ylo[:ntot], cl_vy[:ntot], cl_cond[:ntot], cl_mode[:ntot],
                            cl_phase[:ntot], cl_iv0[:ntot], cl_ivn[:ntot], IV[:niv], pc_cl[:npc], pc_par[:npc],
                            pc_cand[:npc], pc_lo[:npc], pc_hi[:npc], pc_dlo[:npc], pc_dhi[:npc], stats, flags,
                            cl_node[:ntot], cl_ev[:ntot], cl_ad[:ntot])
            # the edge list this cluster takes (T2): no air dash (T1: du 0); in the dash mode every candidate in the
            # engine's order (du 1 with the air dash unused: the no-dash children - T1's list - and the bridge's entries
            # among them; du 2 with it used)
            adc = cur_d[c]
            du = 0 if not dmode else (1 if adc == 0 else 2)
            bad = False
            if EOFF[src, s, 4 * du + 2 * fl, 0] < 0:
                bad = not expand(src, s, fl, du, P, udt, TTf, TTg, opts, hh, NL, NCU, NID, NINT, NVY, EOFF, PFL, EI, EF,
                                 HT, CHT, CK, CH, CNT)
            if not bad and (NINT[src, I_ADEP] & (1 << s)) != 0:
                src = _ainst(src, a_st, py, cur_q[c], cur_s[c], P, NL, NCU, NID, NINT, NVY, EOFF, HT, CHT, CK, CH,
                             CNT, ICK, ICT, key, ckey)
                bad = src < 0 or not expand(src, s, fl, du, P, udt, TTf, TTg, opts, hh, NL, NCU, NID, NINT, NVY, EOFF,
                                            PFL, EI, EF, HT, CHT, CK, CH, CNT)
            if bad:
                flags[4] |= CNT[C_OVF] | 64
                return (cl_off, cl_y[:ntot], cl_ylo[:ntot], cl_vy[:ntot], cl_cond[:ntot], cl_mode[:ntot],
                        cl_phase[:ntot], cl_iv0[:ntot], cl_ivn[:ntot], IV[:niv], pc_cl[:npc], pc_par[:npc],
                        pc_cand[:npc], pc_lo[:npc], pc_hi[:npc], pc_dlo[:npc], pc_dhi[:npc], stats, flags,
                        cl_node[:ntot], cl_ev[:ntot], cl_ad[:ntot])
            lim = 1 if (maxev > 0 and cur_e[c] >= maxev) else 0
            pg = NINT[src, I_GROUND]
            e0 = EOFF[src, s, 4 * du + 2 * fl + lim, 0]
            ne = EOFF[src, s, 4 * du + 2 * fl + lim, 1]
            stats[t, 5] += ne
            for e in range(e0, e0 + ne):
                if du == 0:
                    cad = adc
                    if ldash and adc == 1 and pg == 0 and NINT[EI[e, EI_CH], I_GROUND] == 1:
                        cad = 0                          # (a landing restores the dash: H2_LAND_DASH)
                else:
                    cad = EI[e, EI_AD]
                ch = EI[e, EI_CH]
                dlo = EF[e, EF_DLO] + EF[e, EF_SLO] * a_st
                dhi = EF[e, EF_DHI] + EF[e, EF_SHI] * a_st
                if EI[e, EI_YABS] == 1:
                    cy = EF[e, EF_DY]
                    cyl = EF[e, EF_DY]
                else:
                    cy = py + EF[e, EF_DY]
                    cyl = cur_yl[c] + EF[e, EF_DY]
                ev = cur_e[c] + (EF[e, EF_NEV] if lim == 0 else 0.0)
                qm = EF[e, EF_QM]
                if qm == 0.0:
                    cq = cur_q[c]
                elif qm == 1.0:
                    cq = py
                elif qm == 2.0:
                    cq = cy
                elif qm == 4.0:
                    cq = cur_q[c] + a_st * (cur_s[c] - cur_q[c])
                else:
                    cq = cy + EF[e, EF_QV]
                sm = EF[e, EF_SM]
                if sm == 0.0:
                    cs = cur_s[c]
                elif sm == 1.0:
                    cs = cy
                elif sm == 2.0:
                    cs = EF[e, EF_SV] if EI[e, EI_YABS] == 1 else py + EF[e, EF_SV]
                else:
                    cs = cy + EF[e, EF_SV]
                npcs = 0
                for q in range(cl_ivn[g]):
                    a = IV[cl_iv0[g] + q, 0] + dlo
                    b = IV[cl_iv0[g] + q, 1] + dhi
                    if wall:
                        a = max(a, wlo)
                        b = min(b, whi)
                        if a > b:
                            continue
                    if b0 < b1:
                        m = ej.cut_danger(a, b, cyl + hh, cy + hh, boxes, b0, b1, olo, ohi, wlo_, whi_)
                        for r in range(m):
                            if npcs < 64:
                                klo[npcs] = olo[r]
                                khi[npcs] = ohi[r]
                                npcs += 1
                    elif npcs < 64:
                        klo[npcs] = a
                        khi[npcs] = b
                        npcs += 1
                if npcs == 0:
                    stats[t, 2] += 1
                    continue
                # the merge class at the height (the engine's key; the band layer: the node within band_q, away from
                # the floor)
                use_band = band_q > 0.0 and not (has_floor and near(cy + 1.0, cyl - 1.0, TP, P))
                if use_band:
                    hb = np.int64(math.floor(cyl / band_q))
                    hc = 4 * ch + 2 * cad + 1
                    hq = np.int64(0)
                    hs = np.int64(0)
                else:
                    yb[0] = cy
                    hb = np.int64(yb.view(np.int64)[0])
                    qsb[0] = cq
                    qsb[1] = cs
                    vv = qsb.view(np.int64)
                    hq = vv[0]
                    hs = vv[1]
                    hc = 4 * NINT[ch, I_CLS if has_floor else I_CLSF] + 2 * cad
                h = _ich(hc, hb, hq, hs)
                idx = -1
                slot = h & HMASK
                while True:
                    j = htab[slot]
                    if j < 0:
                        break
                    if khs_c[j] == hc and khs_b[j] == hb and khs_q[j] == hq and khs_s[j] == hs:
                        if not use_band or (max(nxt_y[j], cy) - min(nxt_yl[j], cyl) <= band_q):
                            idx = j
                            break
                    slot = (slot + 1) & HMASK
                if idx < 0:
                    if nch >= cap_frame:
                        flags[0] = 1
                        continue
                    idx = nch
                    nch += 1
                    nxt_n[idx] = ch
                    nxt_y[idx] = cy
                    nxt_yl[idx] = cyl
                    nxt_e[idx] = ev
                    nxt_d[idx] = cad
                    nxt_q[idx] = cq
                    nxt_s[idx] = cs
                    khs_c[idx] = hc
                    khs_b[idx] = hb
                    khs_q[idx] = hq
                    khs_s[idx] = hs
                    htab[slot] = idx
                    ch_first[idx] = -1
                else:
                    stats[t, 4] += 1
                    if nxt_n[idx] != ch:
                        mg = _merge(nxt_n[idx], ch, P, NL, NCU, NID, NINT, NVY, EOFF, HT, CHT, CK, CH, CNT, key, ckey)
                        if mg < 0:
                            flags[4] |= CNT[C_OVF]
                            return (cl_off, cl_y[:ntot], cl_ylo[:ntot], cl_vy[:ntot], cl_cond[:ntot],
                                    cl_mode[:ntot], cl_phase[:ntot], cl_iv0[:ntot], cl_ivn[:ntot], IV[:niv],
                                    pc_cl[:npc], pc_par[:npc], pc_cand[:npc], pc_lo[:npc], pc_hi[:npc],
                                    pc_dlo[:npc], pc_dhi[:npc], stats, flags, cl_node[:ntot], cl_ev[:ntot], cl_ad[:ntot])
                        nxt_n[idx] = mg
                        stats[t, 3] += 1
                    if ev < nxt_e[idx]:
                        nxt_e[idx] = ev
                    if band_q > 0.0:
                        if cy > nxt_y[idx]:
                            nxt_y[idx] = cy
                        if cyl < nxt_yl[idx]:
                            nxt_yl[idx] = cyl
                for r in range(npcs):
                    if nfp >= fp_cap:
                        flags[1] = 1
                        break
                    fp_ch[nfp] = idx
                    fp_par[nfp] = g
                    fp_cand[nfp] = EI[e, EI_CAND]
                    fp_lo[nfp] = klo[r]
                    fp_hi[nfp] = khi[r]
                    fp_dlo[nfp] = dlo
                    fp_dhi[nfp] = dhi
                    fp_next[nfp] = ch_first[idx]
                    ch_first[idx] = nfp
                    nfp += 1
        gb = ntot
        if ntot + nch > cap_cl:
            flags[3] = 1
            nch = cap_cl - ntot
        for c in range(nch):
            gc = gb + c
            m = 0
            j = ch_first[c]
            while j >= 0 and m < 256:
                sl[m] = fp_lo[j]
                sh_[m] = fp_hi[j]
                m += 1
                j = fp_next[j]
            for i in range(1, m):
                a = sl[i]
                b = sh_[i]
                q = i - 1
                while q >= 0 and sl[q] > a:
                    sl[q + 1] = sl[q]
                    sh_[q + 1] = sh_[q]
                    q -= 1
                sl[q + 1] = a
                sh_[q + 1] = b
            cl_iv0[gc] = niv
            n0_ = niv
            for i in range(m):
                if niv > n0_ and sl[i] <= IV[niv - 1, 1] + 1e-9:
                    if sh_[i] > IV[niv - 1, 1]:
                        IV[niv - 1, 1] = sh_[i]
                else:
                    if niv >= cap_iv:
                        flags[2] = 1
                        break
                    IV[niv, 0] = sl[i]
                    IV[niv, 1] = sh_[i]
                    niv += 1
            cl_ivn[gc] = niv - n0_
            nd = nxt_n[c]
            cl_y[gc] = nxt_y[c] + hh
            cl_ylo[gc] = nxt_yl[c] + hh
            cl_vy[gc] = NVY[nd, V_VY]
            cl_cond[gc] = _cond(NINT[nd, I_COND], ej.COND_DASHED if nxt_d[c] else 0)
            cl_ad[gc] = nxt_d[c]
            cl_mode[gc] = NINT[nd, I_MODE]
            cl_phase[gc] = NINT[nd, I_PHASE]
            cl_node[gc] = nd
            cl_ev[gc] = nxt_e[c]
        for j in range(nfp):
            if fp_ch[j] >= nch:
                continue
            if npc >= cap_pc:
                flags[1] = 1
                break
            pc_cl[npc] = gb + fp_ch[j]
            pc_par[npc] = fp_par[j]
            pc_cand[npc] = fp_cand[j]
            pc_lo[npc] = fp_lo[j]
            pc_hi[npc] = fp_hi[j]
            pc_dlo[npc] = fp_dlo[j]
            pc_dhi[npc] = fp_dhi[j]
            npc += 1
        ntot += nch
        cl_off[t + 1] = ntot
        stats[t, 0] = nch
        stats[t, 1] = nfp
        # swap
        tn = cur_n
        cur_n = nxt_n
        nxt_n = tn
        ty = cur_y
        cur_y = nxt_y
        nxt_y = ty
        ty = cur_yl
        cur_yl = nxt_yl
        nxt_yl = ty
        ty = cur_e
        cur_e = nxt_e
        nxt_e = ty
        ty = cur_q
        cur_q = nxt_q
        nxt_q = ty
        ty = cur_s
        cur_s = nxt_s
        nxt_s = ty
        td = cur_d
        cur_d = nxt_d
        nxt_d = td
        ncl = nch
        if ncl == 0:
            for tt in range(t + 1, T + 1):
                cl_off[tt + 1] = ntot
            break
    return (cl_off, cl_y[:ntot], cl_ylo[:ntot], cl_vy[:ntot], cl_cond[:ntot], cl_mode[:ntot], cl_phase[:ntot],
            cl_iv0[:ntot], cl_ivn[:ntot], IV[:niv], pc_cl[:npc], pc_par[:npc], pc_cand[:npc], pc_lo[:npc],
            pc_hi[:npc], pc_dlo[:npc], pc_dhi[:npc], stats, flags, cl_node[:ntot], cl_ev[:ntot], cl_ad[:ntot])



# ---- routing, the reference member, path following ------------------------------------------------------------

@njit(cache=True, error_model="numpy")
def route(n, py, qy, sy, s, alpha, TP, P, udt, TTf, TTg, opts, hh, NL, NCU, NID, NINT, NVY, EOFF, PFL, EI, EF, HT, CHT,
          CK, CH, CNT, ICK, ICT):
    """route_du for the no-dash lists (T1)."""
    return route_du(n, py, qy, sy, s, alpha, 0, TP, P, udt, TTf, TTg, opts, hh, NL, NCU, NID, NINT, NVY, EOFF, PFL, EI,
                    EF, HT, CHT, CK, CH, CNT, ICK, ICT)


@njit(cache=True, error_model="numpy")
def route_du(n, py, qy, sy, s, alpha, du, TP, P, udt, TTf, TTg, opts, hh, NL, NCU, NID, NINT, NVY, EOFF, PFL, EI, EF,
             HT, CHT, CK, CH, CNT, ICK, ICT):
    """The node whose edges a cluster of node n at height py (her PY) uses in a frame of s steps starting at phase
    alpha (the chain's rule: a free node within clear of the floor -> its floor instance; a phase-dependent frame ->
    the phase instance), expanded. -1: a table is full."""
    key = np.empty(NIDK)
    ckey = np.empty(NKEY)
    fl = 1 if (TP[0] > 0 or TP[3] > 0) else 0
    src = n
    if NINT[n, I_ABS] == 0 and fl == 1 and near(py, py, TP, P):
        src = _instance(n, py, P, NL, NCU, NID, NINT, NVY, EOFF, HT, CHT, CK, CH, CNT, ICK, ICT, key, ckey)
        if src < 0:
            return -1
    if EOFF[src, s, 4 * du + 2 * fl, 0] < 0:
        if not expand(src, s, fl, du, P, udt, TTf, TTg, opts, hh, NL, NCU, NID, NINT, NVY, EOFF, PFL, EI, EF, HT, CHT,
                      CK, CH, CNT):
            return -1
    if (NINT[src, I_ADEP] & (1 << s)) != 0:
        src = _ainst(src, alpha, py, qy, sy, P, NL, NCU, NID, NINT, NVY, EOFF, HT, CHT, CK, CH, CNT, ICK, ICT, key,
                     ckey)
        if src < 0:
            return -1
        if not expand(src, s, fl, du, P, udt, TTf, TTg, opts, hh, NL, NCU, NID, NINT, NVY, EOFF, PFL, EI, EF, HT, CHT,
                      CK, CH, CNT):
            return -1
    return src


@njit(cache=True, error_model="numpy")
def member_frame(x, cu, m_raw, m_prev, strip, udt, P, TT):
    """One frame of env_jit.ref_rollout (kin_jit + the Clawline block + its residual drift; B_CLAW a Clawline press,
    bit 31 its P + 8 throw) for one concrete key mask, WITHOUT THE AIR DASH as the engine's OPT_NO_ADASH: the dash key
    is dropped whenever she is airborne after the frame's steps. Returns (strip, m_prev)."""
    m = m_raw
    no_j = (x[GROUND] > 0 and (x[MODE] == M_DASH or (x[MODE] == M_SPRINT and x[PHASE] == 2.0)) and
            (np.int64(P[km.P_H2]) & km.H2_SHUTTLE) == 0)
    no_a = x[MODE] == M_SPRINT and x[PHASE] >= 2.0
    for b in (B_JUMP, B_ATTACK):
        if (m & b) == 0:
            strip &= ~b
        elif (m_prev & b) == 0 and (no_j if b == B_JUMP else no_a):
            strip |= b
    m_prev = m
    m = m & ~strip
    fdt = P[P_FDT]
    dt, steps = ej.lane_timing(x, udt, P)
    if cu[C_CJ] >= 0:
        ctl = ej.claw_frame(x, cu, steps, P, TT)
        ej.tick_frozen(x, dt, udt)
        cu[C_CJ] += 1.0
        if ctl:
            rv = abs(x[VX])
            ej.claw_control(x)
            cu[C_CJ] = -1.0
            cu[ej.C_CLOCK] = ej.CLAW_NEXT_F
            cu[ej.C_RD] = cu[ej.C_CD]
            cu[ej.C_RV] = rv
            if x[GROUND] <= 0:
                m &= ~B_DASH
            update(x, m & ~ej.B_CLAW & ~(1 << 31), 0, dt, udt, P, TT)
    else:
        if cu[ej.C_CLOCK] > 0:
            cu[ej.C_CLOCK] -= 1.0
        for _ in range(steps):
            ej.fixed_step(x, P, TT)
            if cu[ej.C_RV] > 0:
                if x[GROUND] > 0 or x[MODE] != 0:
                    cu[ej.C_RV] = 0.0
                else:
                    mv = x[MOVE]
                    if mv == 0:
                        x[PX] += cu[ej.C_RV] * cu[ej.C_RD] * fdt
                        x[SX] = x[PX]
                    elif mv == -cu[ej.C_RD]:
                        cu[ej.C_RV] = 0.0
                    cu[ej.C_RV] *= ej.CLAW_END_DECAY
        if x[GROUND] <= 0:
            m &= ~B_DASH
        if (m & ej.B_CLAW) != 0 and ej.claw_allowed(x, cu, P):
            d = x[FACE]
            if (m & B_RIGHT) != 0 and (m & B_LEFT) == 0:
                d = 1.0
            elif (m & B_LEFT) != 0 and (m & B_RIGHT) == 0:
                d = -1.0
            x[FACE] = d
            ej.claw_enter(x, cu, d, 8.0 if (m & (1 << 31)) != 0 else 9.0, P)
            ej.tick_frozen(x, dt, udt)
            x[PREV] = np.float64(m & ~ej.B_CLAW & ~(1 << 31))
        else:
            update(x, m & ~ej.B_CLAW & ~(1 << 31), 0, dt, udt, P, TT)
    return strip, m_prev


@njit(cache=True, error_model="numpy")
def follow(S0, cu0, n0, masks, TP, tol, P, udt, TTf, TTg, opts, hh, NL, NCU, NID, NINT, NVY, EOFF, PFL, EI, EF, HT,
           CHT, CK, CH, CNT, ICK, ICT, out, xy):
    """CONTAINMENT by path following: each key sequence (masks [n, T]) is rolled from S0 by the reference member
    (member_frame) and followed through the graph from node n0: at every frame the children of the tracked lineages
    (node, height, x offset interval) whose height is the member's exactly and whose interval holds its x (+- tol)
    and whose mode / phase / ground / Clawline-block frame are the member's (an attack in normal control, which the
    engine does not offer, keeps the member in its lineage: the Wanderer's slash does not move her) are kept (at most
    LMAX). out [n, 3]: the first frame no lineage holds the member (-1: none, inside every frame), the most lineages
    tracked, the member's distance outside the nearest matching interval at that frame (-1: no child at its height
    and mode - a vertical escape); xy [n, T + 1, 2] the member's centre. Returns -1, or -2 when a library table
    filled up."""
    nr = masks.shape[0]
    T = masks.shape[1]
    fdt = P[P_FDT]
    dt = f32(udt)
    TT = TTg if (TP[0] > 0 or TP[3] > 0) else TTf
    fl = 1 if (TP[0] > 0 or TP[3] > 0) else 0
    LMAX = 512
    cq_ = np.empty(LMAX)
    cs_ = np.empty(LMAX)
    nq = np.empty(LMAX)
    ns = np.empty(LMAX)
    cn = np.empty(LMAX, dtype=np.int64)
    cy = np.empty(LMAX)
    clo = np.empty(LMAX)
    chi = np.empty(LMAX)
    nn_ = np.empty(LMAX, dtype=np.int64)
    ny = np.empty(LMAX)
    nlo = np.empty(LMAX)
    nhi = np.empty(LMAX)
    for r in range(nr):
        x = S0.copy()
        cu = cu0.copy()
        strip = 0
        m_prev = np.int64(x[PREV])
        nc = 1
        cn[0] = n0
        cy[0] = S0[PY]
        cq_[0] = S0[QY]
        cs_[0] = S0[SY]
        clo[0] = S0[PX]
        chi[0] = S0[PX]
        alpha = S0[ALPHA]
        out[r, 0] = -1
        out[r, 1] = 1
        out[r, 2] = 0.0
        xy[r, 0, 0] = x[PX]
        xy[r, 0, 1] = x[PY] + hh
        for t in range(1, T + 1):
            a_ = alpha + dt / fdt
            s = np.int64(math.floor(a_ + 1e-9))
            a_st = alpha
            alpha = min(max(a_ - s, 0.0), 1.0)
            strip, m_prev = member_frame(x, cu, masks[r, t - 1], m_prev, strip, udt, P, TT)
            mx = x[PX]
            my = x[PY]
            xy[r, t, 0] = mx
            xy[r, t, 1] = my + hh
            k = 0
            best = -1.0
            for j in range(nc):
                src = route(cn[j], cy[j], cq_[j], cs_[j], s, a_st, TP, P, udt, TTf, TTg, opts, hh, NL, NCU, NID, NINT,
                            NVY, EOFF, PFL, EI, EF, HT, CHT, CK, CH, CNT, ICK, ICT)
                if src < 0:
                    return -2
                e0 = EOFF[src, s, 2 * fl, 0]
                ne = EOFF[src, s, 2 * fl, 1]
                for e in range(e0, e0 + ne):
                    yy = EF[e, EF_DY] if EI[e, EI_YABS] == 1 else cy[j] + EF[e, EF_DY]
                    if yy != my:
                        continue
                    c2 = EI[e, EI_CH]
                    if (NINT[c2, I_MODE] != np.int64(x[MODE]) or NINT[c2, I_PHASE] != np.int64(x[PHASE]) or
                            NINT[c2, I_GROUND] != (1 if x[GROUND] > 0 else 0) or NCU[c2, C_CJ] != cu[C_CJ]):
                        continue
                    lo = clo[j] + EF[e, EF_DLO] + EF[e, EF_SLO] * a_st
                    hi = chi[j] + EF[e, EF_DHI] + EF[e, EF_SHI] * a_st
                    d = max(lo - mx, mx - hi, 0.0)
                    if best < 0.0 or d < best:
                        best = d
                    if d > tol:
                        continue
                    ch = EI[e, EI_CH]
                    dup = False
                    for q in range(k):
                        if nn_[q] == ch and ny[q] == yy and nlo[q] == lo and nhi[q] == hi:
                            dup = True
                            break
                    if dup or k >= LMAX:
                        continue
                    nn_[k] = ch
                    ny[k] = yy
                    nlo[k] = lo
                    nhi[k] = hi
                    qm = EF[e, EF_QM]
                    nq[k] = cq_[j] if qm == 0.0 else (cy[j] if qm == 1.0 else (yy if qm == 2.0 else (
                        cq_[j] + a_st * (cs_[j] - cq_[j]) if qm == 4.0 else yy + EF[e, EF_QV])))
                    sm = EF[e, EF_SM]
                    ns[k] = cs_[j] if sm == 0.0 else (yy if sm == 1.0 else (
                        (EF[e, EF_SV] if EI[e, EI_YABS] == 1 else cy[j] + EF[e, EF_SV]) if sm == 2.0 else yy + EF[e, EF_SV]))
                    k += 1
            if k == 0:
                out[r, 0] = t
                out[r, 2] = best
                for tt in range(t + 1, T + 1):
                    xy[r, tt, 0] = np.nan
                    xy[r, tt, 1] = np.nan
                break
            for q in range(k):
                cn[q] = nn_[q]
                cy[q] = ny[q]
                clo[q] = nlo[q]
                chi[q] = nhi[q]
                cq_[q] = nq[q]
                cs_[q] = ns[q]
            nc = k
            if k > out[r, 1]:
                out[r, 1] = k
    return -1

# ---- library bookkeeping ------------------------------------------------------------------------------------------

@njit(cache=True, error_model="numpy")
def _rehash(T, hashes, n):
    T[:] = -1
    m = T.shape[0] - 1
    for j in range(n):
        slot = hashes[j] & m
        while T[slot] >= 0:
            slot = (slot + 1) & m
        T[slot] = j


@njit(cache=True, error_model="numpy")
def _ic_hashes(ICK, n):
    out = np.empty(n, dtype=np.int64)
    for j in range(n):
        out[j] = _ich(ICK[j, 0], ICK[j, 1], ICK[j, 3], ICK[j, 4])
    return out


@njit(cache=True, error_model="numpy")
def _idents(NL, NCU, NINT, NVY, P, n, NID):
    for j in range(n):
        ident(NL[j], NCU[j], P, NINT[j, I_ABS] == 1, NVY[j, V_ALF], NID[j])


@njit(cache=True, error_model="numpy")
def _start_node(L, cu, absy, P, NL, NCU, NID, NINT, NVY, EOFF, HT, CHT, CK, CH, CNT):
    key = np.empty(NIDK)
    ckey = np.empty(NKEY)
    return node_get(L, cu, absy, -1.0, P, NL, NCU, NID, NINT, NVY, EOFF, HT, CHT, CK, CH, CNT, key, ckey)


K_TRANS, K_A1, K_A1OFF, K_A4, K_A2, K_A3, K_G, K_R, K_HANG = range(9)
KIND_NAMES = ("transient", "A1", "A1~", "A4", "A2", "A3", "G", "R", "hang")


def _pow2(n: int) -> int:
    p = 1
    while p < n:
        p *= 2
    return p


def _sha1(P: np.ndarray) -> str:
    import hashlib
    return hashlib.sha1(np.ascontiguousarray(P, dtype=np.float64).tobytes()).hexdigest()


class Lib:
    """The table library: the nodes (relative cluster states), their edges per step count, the merge classes, the
    floor instances; built from the canonical starts (close), grown on the fly by the chain (forward), saved as a
    knowledge file with its version and the hero model in the header."""

    _NODE_ARR = ("NL", "NCU", "NID", "NINT", "NVY", "EOFF", "PFL")

    def __init__(self, params: km.HeroParams | None = None, cap_nodes: int = 1 << 16, cap_edges: int = 1 << 19,
                 cap_cls: int = 1 << 15, cap_inst: int = 1 << 14, claw: bool = True, terrain: str = "floor"):
        from ssbot.map2 import envelope as env
        self.params = params or env.load_params()
        self.P = self.params.vector()
        self.udt = float(np.float32(self.params.frame_time))
        self.hh = 0.5 * (self.params.head - self.params.foot)
        self.TTf = km.Terrain2D.empty().packed()
        if terrain not in TERRAINS:
            raise ValueError(terrain)
        self.terrain = terrain
        self.claw = bool(claw)
        boxes = [(-1.0e4, FLOOR_TOP - 2.0, 1.0e4, FLOOR_TOP)]
        if terrain == "arena":
            boxes.append((-1.0e4, CEIL_BOT, 1.0e4, CEIL_BOT + 2.0))
        self.terr = km.Terrain2D.from_boxes(boxes)
        self.TTg = self.terr.packed()
        self.TP = np.array([1.0, FLOOR_TOP, CLEAR, 1.0 if terrain == "arena" else 0.0, CEIL_BOT, CLEAR_UP])
        self.TP_free = np.zeros(6)
        self.opts = (ej.OPT_CLAW | ej.OPT_TF8 if claw else 0) | ej.OPT_NO_ADASH
        self.eng = env.Engine(self.params)
        self.ldash = (int(self.P[km.P_H2]) & km.H2_LAND_DASH) != 0      # T2: a landing restores the air dash
        self.meta: dict = {}
        self.NL = np.zeros((cap_nodes, 2, K))
        self.NCU = np.zeros((cap_nodes, NC))
        self.NID = np.zeros((cap_nodes, NIDK))
        self.NINT = np.zeros((cap_nodes, NINTC), dtype=np.int64)
        self.NVY = np.zeros((cap_nodes, 2))
        self.EOFF = np.full((cap_nodes, 2, 4 * NDU, 2), -1, dtype=np.int64)
        self.PFL = np.zeros((cap_nodes, 2), dtype=np.int64)
        self.HT = np.full(_pow2(4 * cap_nodes), -1, dtype=np.int64)
        self.EI = np.zeros((cap_edges, NEI), dtype=np.int64)
        self.EF = np.zeros((cap_edges, NEF))
        self.CK = np.zeros((cap_cls, NKEY))
        self.CH = np.zeros(cap_cls, dtype=np.int64)
        self.CHT = np.full(_pow2(4 * cap_cls), -1, dtype=np.int64)
        self.ICK = np.zeros((cap_inst, 5), dtype=np.int64)
        self.ICT = np.full(_pow2(4 * cap_inst), -1, dtype=np.int64)
        self.CNT = np.zeros(NCNT, dtype=np.int64)

    # ---- capacity ----
    @property
    def n_nodes(self) -> int:
        return int(self.CNT[C_NODES])

    @property
    def n_edges(self) -> int:
        return int(self.CNT[C_EDGES])

    def _grow(self) -> None:
        ovf = int(self.CNT[C_OVF])
        if ovf & 8:
            raise RuntimeError("tables: the phase choice does not give the step count (ALPHA_S)")
        if ovf & 1:
            n = self.NL.shape[0] * 2
            for nm in self._NODE_ARR:
                a = getattr(self, nm)
                b = np.zeros((n,) + a.shape[1:], dtype=a.dtype)
                if nm == "EOFF":
                    b[:] = -1
                b[:a.shape[0]] = a
                setattr(self, nm, b)
            self.HT = np.full(_pow2(4 * n), -1, dtype=np.int64)
            _rehash(self.HT, self.NINT[:, I_HASH].copy(), self.n_nodes)
        if ovf & 2:
            self.EI = np.concatenate([self.EI, np.zeros_like(self.EI)])
            self.EF = np.concatenate([self.EF, np.zeros_like(self.EF)])
        if ovf & 4:
            n = self.CK.shape[0] * 2
            self.CK = np.concatenate([self.CK, np.zeros_like(self.CK)])
            self.CH = np.concatenate([self.CH, np.zeros_like(self.CH)])
            self.CHT = np.full(_pow2(4 * n), -1, dtype=np.int64)
            _rehash(self.CHT, self.CH, int(self.CNT[C_CLS]))
        if ovf & 16:
            n = self.ICK.shape[0] * 2
            self.ICK = np.concatenate([self.ICK, np.zeros_like(self.ICK)])
            self.ICT = np.full(_pow2(4 * n), -1, dtype=np.int64)
            _rehash(self.ICT, _ic_hashes(self.ICK, int(self.CNT[C_INST])), int(self.CNT[C_INST]))
        self.CNT[C_OVF] = 0

    def _lib(self):
        return (self.NL, self.NCU, self.NID, self.NINT, self.NVY, self.EOFF, self.PFL, self.EI, self.EF, self.HT,
                self.CHT, self.CK, self.CH, self.CNT)

    # ---- nodes ----
    def start_lanes(self, S: np.ndarray, x0: float | None = None, x1: float | None = None, cu=None,
                    floor: bool = False):
        """Her exact state -> (the engine's Start, the relative lanes, absy, the air dash used)."""
        st = self.eng.start_state(np.asarray(S, dtype=np.float64), x0, x1, cu)
        L = st.L.copy()
        dashed = bool(L[1, AIRDASHED] > 0)
        absy = bool(floor and L[1, GROUND] > 0)
        rel_x(L)
        if not absy:
            rel_y(L)
        return st, L, absy, dashed

    def node_of(self, L: np.ndarray, cu: np.ndarray, absy: bool) -> int:
        while True:
            n = _start_node(np.ascontiguousarray(L), np.asarray(cu, dtype=np.float64), absy, self.P, self.NL,
                            self.NCU, self.NID, self.NINT, self.NVY, self.EOFF, self.HT, self.CHT, self.CK, self.CH,
                            self.CNT)
            if n >= 0:
                return int(n)
            self._grow()

    def close(self, i0: int = 0, i1: int | None = None, log=None) -> int:
        """Expand every node from i0 (and every node found meanwhile) up to node i1: the closure."""
        i = i0
        lim = 1 << 62 if i1 is None else i1
        t0 = time.perf_counter()
        while True:
            i = int(closure(i, lim, self.P, self.udt, self.TTf, self.TTg, self.opts, self.hh, *self._lib()))
            if self.CNT[C_OVF]:
                self._grow()
                if log:
                    log(f"  grown: nodes {self.n_nodes} cap {self.NL.shape[0]}, edges {self.n_edges} cap "
                        f"{self.EI.shape[0]}, {time.perf_counter() - t0:.1f} s")
                continue
            if i >= self.n_nodes or i >= lim:
                return i

    # ---- the chain ----
    def forward(self, S: np.ndarray, T: int, danger=None, floor: bool = False, maxev: int = 0,
                x0: float | None = None, x1: float | None = None, cu=None, wall=None, band_q: float = 0.0,
                cap_frame: int = 20000, cap_pc: int = 4_000_000, cap_iv: int = 4_000_000, cap_cl: int = 2_000_000,
                dash: bool = False):
        """The chain from her exact state S over T frames (danger: None or T + 1 arrays of boxes [n, 4] in her
        centre's space; floor: the library's terrain (the Forum floor, and the ceiling for 'arena') - else free
        space; maxev: the event limit; wall: (x_lo, x_hi) of her centre or None;
        band_q > 0: the flattened layer's bands; dash (T2): the forward set WITH THE AIR DASH - the no-dash chain + the
        bridge's entries (the air dash pressed / held / queued, its own frames and every frame after it on the full
        lists), the engine's pass without OPT_NO_ADASH. Returns an envelope.Fwd (the engine's arrays: regions,
        contains, witness) with .node / .events / .ad (the air dash used) per cluster and .lib_stats."""
        from ssbot.map2 import envelope as env
        S = np.asarray(S, dtype=np.float64).reshape(-1)
        if S[TS] != 1.0 or S[WF_S] != 1.0:
            raise ValueError("tables.forward: a time scale / world freeze start (TS, WF_S != 1) is not in the tables")
        st, L, absy, dashed = self.start_lanes(S, x0, x1, cu, floor)
        n0 = self.node_of(L, st.cu, absy)
        if danger is None:
            boxes = np.zeros((0, 4))
            off = np.zeros(T + 2, dtype=np.int64)
        else:
            parts = [np.asarray(danger[t], dtype=np.float64).reshape(-1, 4) if t < len(danger) and danger[t] is not None
                     else np.zeros((0, 4)) for t in range(T + 1)]
            off = np.zeros(T + 2, dtype=np.int64)
            off[1:] = np.cumsum([len(p) for p in parts])
            boxes = np.concatenate(parts) if off[-1] else np.zeros((0, 4))
        wl, wh = (wall if wall is not None else (-1e9, 1e9))
        c0 = self.CNT.copy()
        while True:
            t0 = time.perf_counter()
            dfl = (1 if dashed else 0) | (2 if dash else 0) | (4 if self.ldash else 0)
            out = chain(n0, float(S[PY]), float(S[QY]), float(S[SY]), st.ivs, float(S[ALPHA]), T, boxes, off, maxev,
                        self.TP if floor else self.TP_free, wall is not None, float(wl), float(wh), dfl,
                        float(band_q), self.P, self.udt, self.TTf,
                        self.TTg, self.opts, self.hh, *self._lib(), self.ICK, self.ICT, cap_frame, cap_pc, cap_iv,
                        cap_cl)
            sec = time.perf_counter() - t0
            fl = out[18]
            if fl[4]:
                if fl[4] & 32:
                    raise RuntimeError("tables.forward: a frame with two physics steps")
                self._grow()
                continue
            if not fl[:4].any():
                break
            cap_frame *= 2 if fl[0] else 1
            cap_pc *= 2 if fl[1] else 1
            cap_iv *= 2 if fl[2] else 1
            cap_cl *= 2 if fl[3] else 1
        out = tuple(a.copy() for a in out)
        TT = self.TTg if floor else self.TTf
        fw = env.Fwd(self.eng, st, T, TT, *out[:17], np.zeros((0, NKEY)), out[17], out[18][:4], seconds=sec)
        fw.node = out[19]
        fw.events = out[20]
        fw.ad = out[21]
        fw.floor = bool(floor)
        d = self.CNT - c0
        fw.lib_stats = {"expanded": int(d[C_EXP]), "new_nodes": int(d[C_NODES]), "instances": int(d[C_INST]),
                        "merges": int(d[C_MERGE]), "avdep": int(d[C_AVDEP]), "dyupd": int(d[C_DYUPD])}
        return fw

    # ---- the spec's table view: steady states, the continue reference, the frame-0 actions ----
    def lattice(self, n: int = 60) -> np.ndarray:
        """The A1 lattice: her vy after k = 0, 1, ... physics steps of free fall from rest (kin_jit's arithmetic, bit
        for bit; the terminal clamp acts before the step's gravity, so the terminal vy is -max_fall - g fdt)."""
        P = self.P
        vy, out = 0.0, [0.0]
        for _ in range(n):
            if vy < -P[km.P_MAXFALL]:
                vy = -P[km.P_MAXFALL]
            vy = vy - P[km.P_G] * 1.0 * P[km.P_FDT]
            out.append(vy)
        return np.array(out)

    def kinds(self, lo: int = 0) -> np.ndarray:
        """Each node's kind (KIND_NAMES): the steady states the spec opens tables at - A1 (normal control in the air,
        every timer and lock spent, gravity 1, no hang to come, on the fall-from-rest lattice: A1_n), A1~ (the same off
        the lattice: an offset chain, e.g. the fall after the umbrella's Deflate continues the float's vy), A4 (the
        terminal fall), A2 (a bounce / jump rise), A3 (the umbrella's Float Idle), G (standing / walking), R (the
        ground sprint at its speed, past Sprint Grace), hang (the jump held through the apex: its own chain) - and
        transient (a timer / lock running: the attack, its cooldown, the umbrella's re-open lock, the Clawline block
        or lock or its residual drift, the air sprint's extra velocity, a queue, the downspike recovery, i-frames)."""
        n = self.n_nodes
        X = self.NL[lo:n, 1]
        X0 = self.NL[lo:n, 0]
        cu = self.NCU[lo:n]
        n = n - lo
        P = self.P
        mode, ph = X[:, MODE], X[:, PHASE]
        air = X[:, GROUND] <= 0
        normal = mode == km.M_NORMAL
        spent = ((X[:, ATTACKING] <= 0) & (X[:, km.ATK_CD] <= 0) & (X[:, INV_T] <= 0) & (X[:, XVX] == 0) &
                 (X0[:, XVX] == 0) & (cu[:, C_CJ] < 0) & (cu[:, ej.C_CLOCK] <= 0) & (cu[:, ej.C_RV] <= 0) &
                 (X[:, km.DS_REC] < 0) & (X[:, km.DASH_CD] <= 0) & (X[:, km.JBUF] <= 0) & (X[:, km.GL_CD] <= 0) &
                 (X[:, km.LEDGE] <= 0))
        k = np.zeros(n, dtype=np.int64)
        rise = normal & air & ((X[:, km.JUMPING] > 0) | (X[:, km.BOUNCE] >= 0))
        hang = normal & air & ~rise & ((X[:, km.GS] < 1.0) | (X[:, km.AIRHANG] <= 0))
        fall = normal & air & ~rise & ~hang & spent
        lat = np.isin(X[:, VY], self.lattice())
        term = X[:, VY] <= -P[km.P_MAXFALL]
        k[fall & lat & ~term] = K_A1
        k[fall & ~lat & ~term] = K_A1OFF
        k[fall & term] = K_A4
        k[rise & (cu[:, C_CJ] < 0) & (X[:, ATTACKING] <= 0) & (X[:, INV_T] <= 0)] = K_A2
        k[hang & spent] = K_HANG
        k[(mode == km.M_GLIDE) & (ph == 2.0) & (X[:, INV_T] <= 0) & (X[:, ATTACKING] <= 0)] = K_A3
        k[normal & ~air & spent] = K_G
        k[(mode == km.M_SPRINT) & (ph == 2.0) & ~air & (np.abs(X[:, VX]) == P[km.P_SPR_SPEED]) &
          (X[:, MODE_T] >= P[km.P_SPR_GRACE])] = K_R
        return k

    def label(self, nd: int) -> str:
        """A step's label (the spec): invincible (cannot be hit, cannot attack - positions kept), locked (can be hit,
        cannot attack), transitional (can be hit, can attack)."""
        if self.NL[nd, 1, INV_T] > 0:
            return "invincible"
        return "transitional" if (self.NINT[nd, I_COND] & ej.COND_ATK) else "locked"

    def edges(self, nd: int, py: float, s: int, alpha: float = 0.5, floor: bool = False, qy: float | None = None,
              sy: float | None = None, du: int = 0) -> range:
        """The node's edges for a frame of s steps (routed and expanded as the chain does; du: the dash status of the
        list, T2)."""
        qy = py if qy is None else qy
        sy = py if sy is None else sy
        while True:
            src = route_du(nd, py, qy, sy, s, alpha, du, self.TP if floor else self.TP_free, self.P, self.udt, self.TTf,
                           self.TTg, self.opts, self.hh, *self._lib(), self.ICK, self.ICT)
            if src >= 0:
                md = 4 * du + (2 if floor else 0)
                return range(int(self.EOFF[src, s, md, 0]), int(self.EOFF[src, s, md, 0] + self.EOFF[src, s, md, 1]))
            self._grow()

    def steps(self, alpha: float, T: int) -> list:
        """The physics steps of T frames from her phase alpha (the global clock: the same for every cluster)."""
        dt = float(np.float32(self.udt))
        fdt = float(self.P[km.P_FDT])
        out = []
        for _ in range(T):
            a = alpha + dt / fdt
            s = int(np.floor(a + 1e-9))
            out.append((s, alpha))
            alpha = min(max(a - s, 0.0), 1.0)
        return out

    def table(self, nd: int, alpha: float = 0.5, depth: int = 40, max_leaves: int = 2000, kinds=None) -> dict:
        """THE SPEC'S TABLE VIEW of node nd (a steady state) at phase alpha: the CONTINUE reference (the going-on edge:
        the next node one frame later, its x OFFSET INTERVAL [dlo, dhi] and dy) and its FRAME-0 ACTIONS (every other
        edge), each followed through the transient nodes it leads to (branching where they have choices) until a
        steady node or depth: per step the x offset interval relative to the origin, dy, the label and the press
        flags; at the end the REFERENCE (target node and kind, dt, dy, the x offset interval, the lanes' vx interval
        into a float)."""
        kd = self.kinds() if kinds is None else kinds
        sched = self.steps(alpha, depth + 1)
        rows = []
        s0, a0 = sched[0]
        es = list(self.edges(nd, 0.0, s0, a0))
        cont = None
        acts = []
        for e in es:
            ch = int(self.EI[e, EI_CH])
            dlo = float(self.EF[e, EF_DLO] + self.EF[e, EF_SLO] * a0)
            dhi = float(self.EF[e, EF_DHI] + self.EF[e, EF_SHI] * a0)
            dy = float(self.EF[e, EF_DY])
            if cont is None and self.EF[e, EF_NEV] == 0:
                cont = {"node": ch, "kind": KIND_NAMES[kd[ch]] if ch < len(kd) else "?", "dt": 1, "dy": dy,
                        "x_off": [dlo, dhi], "cand": int(self.EI[e, EI_CAND])}
                continue
            acts.append((int(self.EI[e, EI_CAND]), ch, dlo, dhi, dy))
        leaves = []
        trunc = 0
        per_act = max(1, max_leaves // max(1, len(acts)))
        for cand, ch, dlo, dhi, dy in acts:
            stack = [(ch, 1, dlo, dhi, dy, [(1, dlo, dhi, dy, self.label(ch))])]
            n0 = len(leaves)
            while stack:
                if len(leaves) - n0 >= per_act:
                    trunc += len(stack)              # (the rest of this action's tree not explored)
                    break
                c, t, lo, hi, yy, traj = stack.pop()
                kc = kd[c] if c < len(kd) else K_TRANS
                if kc != K_TRANS or t >= depth:
                    if len(leaves) - n0 < per_act:
                        leaves.append({"cand": cand, "steps": traj, "end": {
                            "node": c, "kind": KIND_NAMES[kc], "dt": t, "dy": yy, "x_off": [lo, hi],
                            "vx": [float(self.NL[c, 0, VX]), float(self.NL[c, 1, VX])],
                            "steady": kc != K_TRANS}})
                    else:
                        trunc += 1
                    continue
                s, a = sched[t]
                for e in self.edges(c, yy, s, a):
                    c2 = int(self.EI[e, EI_CH])
                    lo2 = lo + float(self.EF[e, EF_DLO] + self.EF[e, EF_SLO] * a)
                    hi2 = hi + float(self.EF[e, EF_DHI] + self.EF[e, EF_SHI] * a)
                    y2 = yy + float(self.EF[e, EF_DY])
                    stack.append((c2, t + 1, lo2, hi2, y2, traj + [(t + 1, lo2, hi2, y2, self.label(c2))]))
                    if c2 >= len(kd):
                        kd = np.concatenate([kd, self.kinds(len(kd))])
        return {"node": int(nd), "kind": KIND_NAMES[kd[nd]], "vy": float(self.NVY[nd, V_VY]), "alpha": alpha,
                "s0": s0, "continue": cont, "n_edges": len(es), "actions": leaves, "truncated": trunc}

    # ---- per-step press flags and the flattened layer ----
    def press_flags(self, fw, t: int) -> np.ndarray:
        """Per cluster of frame t of a chain: what a press in frame t + 1 meets (PF_* bits: the Clawline, an attack /
        a down slash that starts at once, an AIR DASH PRESS ALLOWED - airborne, normal control or the umbrella's
        cancel, no lock: whether the dash is still unused is the segment's -, airborne) for that frame's step count."""
        S = fw.start.L[1]
        s, a = self.steps(float(S[ALPHA]), t + 1)[t]
        g = np.arange(int(fw.cl_off[t]), int(fw.cl_off[t + 1]))
        TP = self.TP if getattr(fw, "floor", False) else self.TP_free
        res = np.zeros(len(g), dtype=np.int64)
        for i, gg in enumerate(g):
            py = float(fw.cl_y[gg] - self.hh)
            while True:                                 # routed as the chain: a floor / phase instance's own flags
                src = route(int(fw.node[gg]), py, py, py, s, a, TP, self.P, self.udt, self.TTf, self.TTg, self.opts,
                            self.hh, *self._lib(), self.ICK, self.ICT)
                if src >= 0:
                    break
                self._grow()
            res[i] = self.PFL[src, s]
        return res

    def flat(self, S: np.ndarray, T: int, maxev: int = 1, floor: bool = False, q: float = 0.05,
             conds=(0, ej.COND_DSLASH, ej.COND_CLAW)) -> dict:
        """THE FLATTENED LAYER of one start (no danger): per frame and end condition the union of the chain's
        clusters as rows of q (y bins relative to her centre, x relative to her x: env.raster's conservative rows) and
        the frame's bounding box. Exact for the pass's event family (maxev; 0 = every event, only for short T) up to
        the rows' q in y; an upper bound of the danger-cut chain (prune: a window outside it is out of reach; the
        chain's frames before the first danger touch are these)."""
        from ssbot.map2 import envelope as env
        fw = self.forward(S, T, floor=floor, maxev=maxev)
        xs, ys = float(S[PX]), float(S[PY] + self.hh)
        out = {c: [] for c in conds}
        box = np.full((T + 1, 4), np.nan)
        for t in range(T + 1):
            g, x0, x1, y0, y1 = fw.frame_rows(t)
            if len(g):
                box[t] = (x0.min() - xs, y0.min() - ys, x1.max() - xs, y1.max() - ys)
            cond = fw.cl_cond[g]
            for c in conds:
                sel = np.ones(len(g), bool) if not c else (cond & c) == c
                rows = np.stack([y0[sel], y1[sel], x0[sel], x1[sel]], axis=1)
                out[c].append(env.raster(rows, xs, ys, q))
        out["box"] = box
        out["clusters"] = [fw.count(t) for t in range(T + 1)]
        out["seconds"] = fw.seconds
        return out

    # ---- storage ----
    def save(self, path=None, extra: dict | None = None) -> Path:
        from ssbot.map2 import envelope as env
        path = Path(path or tables_path(self.claw, self.terrain))
        n, e, c, ni = self.n_nodes, self.n_edges, int(self.CNT[C_CLS]), int(self.CNT[C_INST])
        meta = {"version": VERSION, "kind": "map2 A1_n no-dash tables (stage T1)", "params": str(env.PARAMS_PATH),
                "hero2": int(self.P[km.P_H2]), "abilities": int(self.P[km.P_ABIL]), "opts": int(self.opts),
                "claw": self.claw, "terrain": self.terrain, "clear": CLEAR, "clear_up": CLEAR_UP,
                "floor_top": FLOOR_TOP, "ceil_bot": CEIL_BOT, "K": K, "NC": NC, "NKEY": NKEY, "NIDK": NIDK,
                "nodes": n, "edges": e, "classes": c, "instances": ni, "params_vector_sha1": _sha1(self.P)}
        meta.update(self.meta)
        if extra:
            meta.update(extra)
        np.savez_compressed(path, _meta=np.array(json.dumps(meta, default=str)), NL=self.NL[:n], NCU=self.NCU[:n],
                            NINT=self.NINT[:n], NVY=self.NVY[:n], EOFF=self.EOFF[:n], PFL=self.PFL[:n],
                            EI=self.EI[:e], EF=self.EF[:e], CK=self.CK[:c], CH=self.CH[:c], ICK=self.ICK[:ni],
                            CNT=self.CNT)
        return path

    @classmethod
    def load(cls, path=None, params: km.HeroParams | None = None) -> "Lib":
        path = Path(path or TABLES_PATH)
        z = np.load(path)
        meta = json.loads(str(z["_meta"]))
        n, e, c, ni = meta["nodes"], meta["edges"], meta["classes"], meta["instances"]
        lib = cls(params, cap_nodes=max(1 << 10, int(n * 1.25)), cap_edges=max(1 << 12, int(e * 1.25)),
                  cap_cls=max(1 << 10, int(c * 1.25)), cap_inst=max(1 << 10, int(ni * 1.25)),
                  claw=meta.get("claw", True), terrain=meta.get("terrain", "floor"))
        if meta.get("params_vector_sha1") != _sha1(lib.P) or meta.get("version") != VERSION:
            raise ValueError(f"tables {path}: built with another hero model or version (params / HERO2 bits)")
        for nm in ("NL", "NCU", "NINT", "NVY", "PFL"):
            getattr(lib, nm)[:n] = z[nm]
        eo = z["EOFF"]
        if eo.shape[2] == 2:                        # (a library from before the per-pass-kind lists: floor-strict)
            lib.EOFF[:n, :, 2:4] = eo
        else:
            lib.EOFF[:n, :, :eo.shape[2]] = eo      # (T1's: the no-dash lists only)
        ei = z["EI"]
        lib.EI[:e, :ei.shape[1]] = ei
        lib.EF[:e] = z["EF"]
        lib.CK[:c] = z["CK"]
        lib.CH[:c] = z["CH"]
        lib.ICK[:ni] = z["ICK"]
        lib.CNT[:] = z["CNT"]
        lib.CNT[C_OVF] = 0
        # (a library saved before the edge lists were committed together: an expansion whose event-limit list was
        # lost to a full table is expanded again)
        for f0 in range(0, 4 * NDU, 2):
            bad = (lib.EOFF[:n, :, f0, 0] >= 0) & (lib.EOFF[:n, :, f0 + 1, 0] < 0)
            v = lib.EOFF[:n, :, f0:f0 + 2]
            v[bad] = -1
            lib.EOFF[:n, :, f0:f0 + 2] = v
        _idents(lib.NL, lib.NCU, lib.NINT, lib.NVY, lib.P, n, lib.NID)
        _rehash(lib.HT, lib.NINT[:, I_HASH].copy(), n)
        _rehash(lib.CHT, lib.CH, c)
        _rehash(lib.ICT, _ic_hashes(lib.ICK, ni), ni)
        lib.meta = meta
        return lib
