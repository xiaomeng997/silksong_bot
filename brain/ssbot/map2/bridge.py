"""Map v2 stage T2: THE AIR DASH AS THE BRIDGE between the no-dash tables (docs/plans/forum_map_v2.md, 'THE A1_n
RECURSIVE TABLES': 'ONE SHARED DASH BUNDLE', 'THE AIR DASH IS NOT IN THE TABLES', 'MEET IN THE MIDDLE, THE DASH
BUNDLE AS THE BRIDGE', 'FLATTENED AND CHAINED, BOTH'; HANDOFF 'Task map2 - A1_n recursive tables - stage T2').
Offline / planning code: nothing in the live bot imports it.

    from ssbot.map2 import tables as tb, bridge as br
    lib = tb.Lib.load(tb.tables_path(False, "arena"))
    fw = lib.forward(S, T=60, danger=boxes, floor=True, maxev=1, dash=True)   # forward + the bridge (the engine's
    #                                                                           pass with the air dash, exactly)
    b = br.bundle(lib, S)                    # the dash bundle of her state: tubes, ends grouped by (end, dt, dy)
    bk = br.backward(fw, goal)               # the backward set of a goal region over the chain's pieces

THE PIECES (tables.py T2): every node's edges per dash status - du 0 the no-dash lists (T1: the air dash unused, every
candidate OPT_NO_ADASH keeps), du 1 every candidate with the air dash unused (the BRIDGE'S ENTRIES marked: a dash
pressed / held / queued in the air), du 2 every candidate with the air dash used (the dash's own frames - its hold,
its attack / jump / Clawline cancels, the re-press -, the umbrella's dash press that only closes it, a queued dash).
A cluster carries its air-dash bit (a key of the merge, as the engine's vkey holds AIRDASHED); a landing restores it
(HERO2 H2_LAND_DASH, BackOnGround), so a segment between refills has one bridge.

THE BUNDLE: the dash family pressed from one state - the entries of the press frame and the full lists while she is
in the dash (M_DASH / the air sprint, airborne) - is the same for every A1_n up to its first physics step (the dash
zeroes vy every step; bundle_family / tools.t2_tables bundle measure it): its paths' tubes (x offset interval and dy
per frame), displacements (dt, dy, [lo, hi]) and end states (the no-dash node the post-dash chain continues from;
the attack cancel with its extra velocity, the jump cancel into the umbrella, the regain of the sprint's end) grouped
by (end node, dt, dy). In the library the bundle is the dash family's nodes and edges (memoised once per node and
step count: per physics phase by the step pattern), so the forward set with the dash (Lib.forward(dash=True)) is
the no-dash chain + the bundle entered at every frame where a dash press is allowed + the post-dash chain - the
engine's pass, cluster for cluster.

BACKWARD (meet in the middle): a goal region (per frame and cluster the x intervals of a strike window's press region
or a safe endpoint) is pulled back over the chain's pieces - x at the parent reaches the child's x' iff x' - x is in
the piece's lane displacement [dlo, dhi] (the instant run; a translation in the committed blocks; the float's lanes
as the forward) and the cuts (danger, walls) are the pieces' own: per cluster the x set from which the goal is still
reachable (the tube forward x backward). The bridge's presses on the tube are the pieces whose candidate presses the
air dash in the air (bridge_presses).
EXACT ONLY WITHOUT INERTIA (T4, the verifiers' finding): the rule 'x reaches x' iff x' - x is in [dlo, dhi]' holds for
the instant run (every member at x has the same choices) and the committed blocks (translations); inside the float's
inertia the piece's displacement depends on the member's vx, which the cluster does not hold per x - there the
backward set is an UPPER BOUND (A3 'N', the goal the middle of the cluster at frame 24: the tube spans the whole
cluster at frame 12, its end members miss the goal by 1.66 u). Back.exact says which; a use that needs the exact set
(an escape funnel's 'inside') must confirm an inexact one forward (a witness rolled through the danger).
"""
from __future__ import annotations

import numpy as np
from numba import njit

from ssbot.knowledge import kinematics as km
from ssbot.map2 import env_jit as ej
from ssbot.map2 import tables as tb

DASH_MODES = (km.M_DASH, km.M_SPRINT)


# ---- backward over a chain's pieces -----------------------------------------------------------------------------

@njit(cache=True, error_model="numpy")
def _backward(ncl, cl_iv0, cl_ivn, IV, order, pstart, pc_par, pc_lo, pc_hi, pc_dlo, pc_dhi, goal_cl, goal_lo, goal_hi,
              cap, eps):
    """Per cluster the x intervals from which a goal row is reached (clusters in decreasing index: a child's index is
    larger than its parents'). Returns (b_iv0, b_ivn, BIV, overflow)."""
    head = np.full(ncl, -1, dtype=np.int64)
    alo = np.empty(cap)
    ahi = np.empty(cap)
    anx = np.empty(cap, dtype=np.int64)
    na = 0
    for i in range(goal_cl.shape[0]):
        c = goal_cl[i]
        for q in range(cl_ivn[c]):
            u = IV[cl_iv0[c] + q, 0]
            v = IV[cl_iv0[c] + q, 1]
            s = max(u, goal_lo[i])
            e = min(v, goal_hi[i])
            if s <= e + eps:
                if na >= cap:
                    return np.zeros(1, np.int64), np.zeros(1, np.int64), np.zeros((0, 2)), True
                alo[na] = s
                ahi[na] = max(s, e)
                anx[na] = head[c]
                head[c] = na
                na += 1
    b_iv0 = np.zeros(ncl, dtype=np.int64)
    b_ivn = np.zeros(ncl, dtype=np.int64)
    BIV = np.empty((cap, 2))
    nb = 0
    tl = np.empty(4096)
    th = np.empty(4096)
    for c in range(ncl - 1, -1, -1):
        m = 0
        j = head[c]
        while j >= 0 and m < 4096:
            tl[m] = alo[j]
            th[m] = ahi[j]
            m += 1
            j = anx[j]
        if m == 0:
            continue
        for i in range(1, m):
            a = tl[i]
            b = th[i]
            q = i - 1
            while q >= 0 and tl[q] > a:
                tl[q + 1] = tl[q]
                th[q + 1] = th[q]
                q -= 1
            tl[q + 1] = a
            th[q + 1] = b
        k0 = nb
        for i in range(m):
            if nb > k0 and tl[i] <= BIV[nb - 1, 1] + eps:
                if th[i] > BIV[nb - 1, 1]:
                    BIV[nb - 1, 1] = th[i]
            else:
                if nb >= cap:
                    return b_iv0, b_ivn, BIV[:nb], True
                BIV[nb, 0] = tl[i]
                BIV[nb, 1] = th[i]
                nb += 1
        b_iv0[c] = k0
        b_ivn[c] = nb - k0
        for qq in range(pstart[c], pstart[c + 1]):
            p = order[qq]
            par = pc_par[p]
            if par < 0:
                continue
            for r in range(k0, nb):
                lo = max(BIV[r, 0], pc_lo[p])
                hi = min(BIV[r, 1], pc_hi[p])
                if lo > hi + eps:
                    continue
                x0 = lo - pc_dhi[p]
                x1 = hi - pc_dlo[p]
                for q in range(cl_ivn[par]):
                    u = IV[cl_iv0[par] + q, 0]
                    v = IV[cl_iv0[par] + q, 1]
                    s = max(x0, u)
                    e = min(x1, v)
                    if s <= e + eps:
                        if na >= cap:
                            return b_iv0, b_ivn, BIV[:nb], True
                        alo[na] = s
                        ahi[na] = max(s, e)
                        anx[na] = head[par]
                        head[par] = na
                        na += 1
    return b_iv0, b_ivn, BIV[:nb], False


class Back:
    """The backward set of a goal over a forward pass (envelope.Fwd from the engine or the tables): per cluster the x
    intervals from which the goal is reached."""

    def __init__(self, fw, b_iv0, b_ivn, BIV):
        self.fw = fw
        self.b_iv0, self.b_ivn, self.BIV = b_iv0, b_ivn, BIV
        # T4: exact when no cluster on the tube is in the float's inertia (the umbrella: M_GLIDE) - else an upper
        # bound (module docstring)
        on = np.flatnonzero(b_ivn > 0)
        self.exact = not bool(np.any(fw.cl_mode[on] == km.M_GLIDE)) if len(on) else True

    def intervals(self, g: int) -> np.ndarray:
        return self.BIV[self.b_iv0[g]:self.b_iv0[g] + self.b_ivn[g]]

    def reached(self, eps: float = 1e-9) -> bool:
        """Whether her start (cluster 0, its x intervals) reaches the goal."""
        return self.b_ivn[0] > 0

    def tube(self, t: int) -> list:
        """Frame t's clusters on the tube: [(cluster, intervals)]."""
        return [(g, self.intervals(g)) for g in self.fw.frame(t) if self.b_ivn[g] > 0]


def backward(fw, goal_cl, goal_lo, goal_hi, eps: float = 1e-9) -> Back:
    """THE BACKWARD SET of a goal region (rows: cluster, x interval) over fw's pieces (see the module docstring:
    exact without the float's inertia on the tube, an upper bound with it - Back.exact)."""
    ncl = int(fw.cl_off[-1])
    ix = getattr(fw, "_back_ix", None)
    if ix is None:                                   # (the pieces by child, once per pass)
        order = np.argsort(fw.pc_cl, kind="stable").astype(np.int64)
        ix = (order, np.searchsorted(fw.pc_cl[order], np.arange(ncl + 1)).astype(np.int64))
        fw._back_ix = ix
    order, pstart = ix
    cap = max(1 << 14, 4 * len(fw.pc_cl) + 4 * len(goal_cl))
    while True:
        r = _backward(ncl, fw.cl_iv0, fw.cl_ivn, fw.IV, order, pstart, fw.pc_par, fw.pc_lo, fw.pc_hi,
                      fw.pc_dlo, fw.pc_dhi, np.asarray(goal_cl, np.int64), np.asarray(goal_lo, np.float64),
                      np.asarray(goal_hi, np.float64), cap, eps)
        if not r[3]:
            return Back(fw, r[0], r[1], r[2])
        cap *= 4


def bridge_presses(bk: Back, lib=None) -> list:
    """The air-dash presses on a backward tube: the pieces into a cluster on the tube whose candidate presses / holds
    the dash in the air and whose parent did not have the air dash used (fw.ad, the tables' chain) - [(frame of the
    press, parent cluster, the parent's x on the tube)]."""
    fw = bk.fw
    ad = getattr(fw, "ad", None)
    out = []
    for p in np.flatnonzero((fw.pc_cand & ej.CB_D) != 0):
        c, par = int(fw.pc_cl[p]), int(fw.pc_par[p])
        if bk.b_ivn[c] == 0 or bk.b_ivn[par] == 0:
            continue
        if ad is not None and (ad[par] != 0 or ad[c] == 0):
            continue
        if ad is None and (int(fw.cl_cond[par]) & ej.COND_DASHED or not int(fw.cl_cond[c]) & ej.COND_DASHED):
            continue
        t = int(np.searchsorted(fw.cl_off, c, side="right") - 1)
        out.append((t, par, bk.intervals(par).tolist()))
    return out


# ---- the flattened union: exact until the danger first touches it ---------------------------------------------

def touch_frame(fw, danger) -> int:
    """The first frame whose clusters (a pass without danger: the flattened union of her state) meet a danger box
    (the cut's own test: the box's y range holds the cluster's height, the x ranges overlap); -1: none. Before it the
    danger-cut pass is this pass, frame for frame (it cuts nothing)."""
    for t in range(fw.T + 1):
        if t >= len(danger) or danger[t] is None or not len(danger[t]):
            continue
        g, x0, x1, y0, y1 = fw.frame_rows(t)
        if not len(g):
            continue
        b = np.asarray(danger[t], np.float64).reshape(-1, 4)
        yin = (b[None, :, 1] <= y0[:, None]) & (y1[:, None] <= b[None, :, 3])
        xin = ~((b[None, :, 2] < x0[:, None]) | (b[None, :, 0] > x1[:, None]))
        if np.any(yin & xin):
            return t
    return -1


# ---- the dash bundle --------------------------------------------------------------------------------------------

def _in_dash(lib, n: int) -> bool:
    """In the dash's own frames: M_DASH / the air sprint, airborne, not in a Clawline block (a Clawline pressed out of
    the sprint ends the bundle: its block is the Clawline's transient, an end state)."""
    return (int(lib.NINT[n, tb.I_MODE]) in DASH_MODES and lib.NINT[n, tb.I_GROUND] == 0 and
            lib.NCU[n, ej.C_CJ] < 0)


def _qs(lib, e, py, qy, sy, py2, a_st):
    qm, sm = lib.EF[e, tb.EF_QM], lib.EF[e, tb.EF_SM]
    yabs = lib.EI[e, tb.EI_YABS] == 1
    q2 = qy if qm == 0 else (py if qm == 1 else (py2 if qm == 2 else (qy + a_st * (sy - qy) if qm == 4
                                                                     else py2 + lib.EF[e, tb.EF_QV])))
    s2 = sy if sm == 0 else (py2 if sm == 1 else ((lib.EF[e, tb.EF_SV] if yabs else py + lib.EF[e, tb.EF_SV])
                                                  if sm == 2 else py2 + lib.EF[e, tb.EF_SV]))
    return float(q2), float(s2)


def bundle(lib, S: np.ndarray, floor: bool = False, T: int = 40, cu=None) -> dict:
    """THE DASH BUNDLE of her state S (the air dash unused, airborne): the bridge's entries in frame 1 (the press, its
    direction, the jump held with it) and the dash family's frames on the full lists with the air dash used, until
    each branch leaves the dash (out of M_DASH / the air sprint, or on the ground). Branches with equal (node, height,
    QY / SY) merge per frame as in the chain (the union of their x offsets). Returns:
      tube: per frame k >= 1 the rows (node, dy, lo, hi, label) - x offsets relative to her x, dy to her height;
      ends: {(end node, dt, dy): [[lo, hi], ...]} - the displacements per end state (dt frames from the press frame's
            start; the end's frame is the first out of the dash);
      press: the press frame's children (node, dy, lo, hi) - the bundle relative to them is A1_n-independent;
      paths: the number of distinct (frame, node, height) states, entries the press children."""
    st, L, absy, dashed = lib.start_lanes(np.asarray(S, np.float64), floor=floor, cu=cu)
    n0 = lib.node_of(L, st.cu, absy)
    py0, qy0, sy0 = float(S[km.PY]), float(S[km.QY]), float(S[km.SY])
    sched = lib.steps(float(S[km.ALPHA]), T + 1)
    front = {}
    press = []
    s, a = sched[0]
    for e in lib.edges(n0, py0, s, a, floor, qy0, sy0, du=1):
        if lib.EI[e, tb.EI_ENT] == 0:
            continue
        ch = int(lib.EI[e, tb.EI_CH])
        dlo = float(lib.EF[e, tb.EF_DLO] + lib.EF[e, tb.EF_SLO] * a)
        dhi = float(lib.EF[e, tb.EF_DHI] + lib.EF[e, tb.EF_SHI] * a)
        py2 = float(lib.EF[e, tb.EF_DY]) if lib.EI[e, tb.EI_YABS] == 1 else py0 + float(lib.EF[e, tb.EF_DY])
        q2, s2 = _qs(lib, e, py0, qy0, sy0, py2, a)
        press.append((ch, py2 - py0, dlo, dhi, int(lib.EI[e, tb.EI_CAND])))
        front.setdefault((ch, py2, q2, s2), []).append((dlo, dhi))
    tube, ends, nstates = [], {}, 0
    for k in range(1, T + 1):
        rows = []
        nxt = {}
        for (n, py, qy, sy), ivs in front.items():
            nstates += 1
            ivs = _union(ivs)
            for lo, hi in ivs:
                rows.append((n, py - py0, lo, hi, lib.label(n)))
            if not _in_dash(lib, n):
                key = (n, k, round(py - py0, 12))
                ends.setdefault(key, []).extend(ivs)
                continue
            if k == T:
                continue
            s, a = sched[k]
            for e in lib.edges(n, py, s, a, floor, qy, sy, du=2):
                ch = int(lib.EI[e, tb.EI_CH])
                dlo = float(lib.EF[e, tb.EF_DLO] + lib.EF[e, tb.EF_SLO] * a)
                dhi = float(lib.EF[e, tb.EF_DHI] + lib.EF[e, tb.EF_SHI] * a)
                py2 = float(lib.EF[e, tb.EF_DY]) if lib.EI[e, tb.EI_YABS] == 1 else py + float(lib.EF[e, tb.EF_DY])
                q2, s2 = _qs(lib, e, py, qy, sy, py2, a)
                lst = nxt.setdefault((ch, py2, q2, s2), [])
                for lo, hi in ivs:
                    lst.append((lo + dlo, hi + dhi))
        tube.append(rows)
        front = nxt
        if not front:
            break
    ends = {k: _union(v) for k, v in ends.items()}
    return {"tube": tube, "ends": ends, "press": press, "states": nstates, "node0": n0}


def _union(ivs) -> list:
    ivs = sorted(ivs)
    out = []
    for lo, hi in ivs:
        if out and lo <= out[-1][1] + 1e-9:
            out[-1][1] = max(out[-1][1], hi)
        else:
            out.append([lo, hi])
    return out


def bundle_relative(b: dict, nd: int = 9) -> dict:
    """The bundle's ends relative to the press frame (its own fall taken out: the press children's dy; x is relative
    to her x already): {(end node, dt, dy rel): x offset intervals}, rounded to nd decimals - what every A1_n shares
    if the dash zeroes vy (tools.t2_tables bundle)."""
    dy1 = b["press"][0][1] if b["press"] else 0.0
    return {(n, dt, round(dy - dy1, nd)): [[round(lo, nd), round(hi, nd)] for lo, hi in ivs]
            for (n, dt, dy), ivs in b["ends"].items()}
