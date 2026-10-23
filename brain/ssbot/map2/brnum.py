"""Map v2 stage M4b: the predicted branches' records as ARRAYS and the search's hot paths on them (offline / planning
code; nothing in the live bot imports ssbot.map2).

clapper_jit.predict gives each branch its records as arrays (JBranch._arr: per Clapper [n, 9] rows k, a, b, state id,
j, x, y, face, ham); a branch with tuple records (clapper.predict, an older pickle) is converted once. The functions
here compute what search.py / strike.py computed by looping over the tuples - the same values:
  views(br)              search.timing_views: the early / late timing views and their reveal frame
  robust_rows(...)       strike.robust_boxes' rows (the box per record and its frame range)
  state_at(br, iid, k)   strike.state_at: the first record of frame k
  move_spans(br)         search.move_spans: per Clapper the moves started and their first frame
  next_move(br, iid, k)  search.terminal's next move start (frame, facing)
  emit(...)              search.branch_frames' first-occurrence rule: the (frame, record) pairs that draw shapes
  first_hit(...)         her hurtbox against the per-frame body boxes and the walls: the first frame hit
tests/test_m4b_speed.py checks each against the tuple version.
"""
from __future__ import annotations

import math

import numpy as np
from numba import njit, objmode, types
from numba.typed import Dict

from ssbot.map2 import clapper as cm
from ssbot.map2 import clapper_jit as cj

ON = [True]                     # the array paths on (False: the tuple loops, for the identity checks)
MOVE_STARTS = {"Slam Antic": "slam", "Spell Antic": "cast", "Jump Antic": "jump", "Cast Slam Antic": "jcast",
               "Evade Scuttle": "evade"}            # = search.MOVE_STARTS
MV_NAMES = list(dict.fromkeys(MOVE_STARTS.values()))
_KEY7 = types.UniTuple(types.int64, 7)


class Flags:
    """Per state table: what the numeric paths need about each state id."""

    def __init__(self, tb: cj.Tables, K: cm.Know):
        names = tb.names
        self.names = names
        self.nobody = np.array([nm in cm.NO_BODY for nm in names], np.bool_)          # rec_shapes: none
        self.nobox = np.array([nm in cm.NO_BODY or nm in cm.DEAD for nm in names], np.bool_)  # _rec_box: none
        self.ms = np.array([MV_NAMES.index(MOVE_STARTS[nm]) if nm in MOVE_STARTS else -1 for nm in names], np.int64)
        self.mo = np.array([MV_NAMES.index(cm.MOVE_OF[nm]) if cm.MOVE_OF.get(nm) in MV_NAMES else -1
                            for nm in names], np.int64)
        self.mvof = [cm.MOVE_OF.get(nm, "idle") for nm in names]
        JM = tb.BOX.shape[1]
        self.BSPAN = np.zeros((len(names), JM + 2, 4))
        for i, nm in enumerate(names):
            for j in range(JM + 2):
                self.BSPAN[i, j] = K.box_span(nm, j)


_FLAGS: dict = {}


def flags(tb: cj.Tables, K: cm.Know) -> Flags:
    f = _FLAGS.get(id(tb))
    if f is None:
        f = Flags(tb, K)
        f._tb = tb
        _FLAGS[id(tb)] = f
    return f


def barr(br) -> tuple:
    """(records {iid: [n, 9] float64}, Tables) of a branch."""
    a = getattr(br, "_arr", None)
    if a is not None:
        return a, br._tb
    c = br.__dict__.get("_arr_t")
    if c is None:
        base = set(cj.static_names(br.K))
        sts = {r[3] for rr in br.recs.values() for r in rr}
        tb = cj.tables(br.K, tuple(sorted(s for s in sts if s is not None and s not in base)))
        arr = {iid: np.array([(r[0], r[1], r[2], -1 if r[3] is None else tb.sid[r[3]], r[4], r[5], r[6], r[7], r[8])
                              for r in rr], np.float64).reshape(-1, 9) for iid, rr in br.recs.items()}
        c = (arr, tb)
        br.__dict__["_arr_t"] = c
    return c


def iids(br) -> list:
    a = getattr(br, "_arr", None)
    return list(a.keys()) if a is not None else list(br.recs.keys())


# ---- timing views ----------------------------------------------------------------------------------------------------

def _last_map(a: np.ndarray, T: int) -> np.ndarray:
    """Per frame 0 .. T the state of the LAST record drawn at that (shifted) frame (-2: none)."""
    out = np.full(T + 1, -2, np.int64)
    if not len(a):
        return out
    ks = a[:, 0].astype(np.int64)
    st = a[:, 3].astype(np.int64)
    rk, rs = ks[::-1], st[::-1]
    u, first = np.unique(rk, return_index=True)              # first in reversed = last in order
    ok = (u >= 0) & (u <= T)
    out[u[ok]] = rs[first[ok]]
    return out


def views(br, branch_cls) -> list:
    """search.timing_views on the arrays: two views (every record drawn at k + a / k + b, a = b = 0), each
    branch_cls (JBranch) with t_reveal = the first frame 1 .. T where the views' states differ (the last record of
    the frame); [br] when no record spreads."""
    arr, tb = barr(br)
    if not any(bool(np.any(a[:, 1] != a[:, 2])) for a in arr.values()):
        return None
    views_ = []
    maps = []
    for mode in (1, 2):
        arr2 = {}
        for iid, a in arr.items():
            b = a.copy()
            b[:, 0] = a[:, 0] + a[:, mode]
            b[:, 1] = 0.0
            b[:, 2] = 0.0
            arr2[iid] = b
        v = branch_cls(br.p * 0.5, br.choices, br.reveal, None, br.hazards, br.K, br.T, br.n_merged)
        v._arr, v._tb, v._names = arr2, tb, tb.names
        v.tview = "early" if mode == 1 else "late"
        views_.append(v)
        maps.append({iid: _last_map(b, br.T) for iid, b in arr2.items()})
    tr_ = None
    for iid in arr:
        d = np.flatnonzero(maps[0][iid][1:] != maps[1][iid][1:])
        if len(d):
            k = int(d[0]) + 1
            tr_ = k if tr_ is None else min(tr_, k)
    for v in views_:
        v.t_reveal = tr_
    return views_


# ---- robust boxes, state lookups -------------------------------------------------------------------------------------

def robust_rows(br, iid: int, T: int) -> np.ndarray:
    """strike.robust_boxes' rows: per record with k + a .. k + b inside 0 .. T: (k_lo, k_hi, its box on that frame:
    K.box(state, j) mirrored by its facing; NO_BODY / DEAD: (inf, inf, -inf, -inf))."""
    arr, tb = barr(br)
    a = arr.get(iid)
    if a is None or not len(a):
        return np.zeros((0, 6))
    F = flags(tb, br.K)
    k_lo = np.maximum(a[:, 0] + a[:, 1], 0.0)
    k_hi = np.minimum(a[:, 0] + a[:, 2], float(T))
    ok = k_lo <= k_hi
    a = a[ok]
    k_lo, k_hi = k_lo[ok], k_hi[ok]
    st = a[:, 3].astype(np.int64)
    j = a[:, 4].astype(np.int64)
    sts = np.maximum(st, 0)
    inr = (j >= 0) & (j < tb.BOXN[sts])
    bx = np.where(inr[:, None], tb.BOX[sts, np.clip(j, 0, tb.BOX.shape[1] - 1)], tb.BOXL[sts])
    x, y, face = a[:, 5], a[:, 6], a[:, 7]
    xa = x + face * bx[:, 0]
    xb = x + face * bx[:, 1]
    rows = np.stack([k_lo, k_hi, np.minimum(xa, xb), y + bx[:, 2], np.maximum(xa, xb), y + bx[:, 3]], axis=1)
    nb = (st < 0) | F.nobox[sts]
    rows[nb, 2:] = (np.inf, np.inf, -np.inf, -np.inf)
    return rows


def _first_rows(br, iid: int) -> dict:
    c = br.__dict__.get("_firstrow")
    if c is None:
        c = {}
        br.__dict__["_firstrow"] = c
    m = c.get(iid)
    if m is None:
        arr, _ = barr(br)
        a = arr.get(iid)
        if a is None or not len(a):
            m = {}
        else:
            u, idx = np.unique(a[:, 0].astype(np.int64), return_index=True)
            m = dict(zip(u.tolist(), idx.tolist()))
        c[iid] = m
    return m


def state_at(br, iid: int, k: int) -> tuple | None:
    """strike.state_at: (state, j, x, y, face) of the first record of frame k (None: none)."""
    i = _first_rows(br, iid).get(int(k))
    if i is None:
        return None
    arr, tb = barr(br)
    r = arr[iid][i]
    st = int(r[3])
    return (tb.names[st] if st >= 0 else None, int(r[4]), float(r[5]), float(r[6]), int(r[7]))


def move_spans(br) -> dict:
    """search.move_spans: iid -> [(move, the earliest frame its start state is drawn at)] in the order the moves
    first appear."""
    arr, tb = barr(br)
    F = flags(tb, br.K)
    out = {}
    for iid, a in arr.items():
        if not len(a):
            out[iid] = []
            continue
        st = np.maximum(a[:, 3].astype(np.int64), 0)
        valid = a[:, 3] >= 0
        ms = np.where(valid, F.ms[st], -1)
        mo = np.where(valid, F.mo[st], -1)
        c1 = (ms >= 0) & (a[:, 4] <= 1)
        c2 = ~c1 & (a[:, 0] == 0) & (mo >= 0)
        mv = np.where(c1, ms, np.where(c2, mo, -1))
        val = np.where(c1, a[:, 0] + a[:, 1], 0.0)
        sel = np.flatnonzero(mv >= 0)
        res = []
        if len(sel):
            mvs, vals = mv[sel], val[sel]
            u, first = np.unique(mvs, return_index=True)
            for q in np.argsort(first, kind="stable"):
                m_ = int(u[q])
                res.append((MV_NAMES[m_], int(vals[mvs == m_].min())))
        out[iid] = res
    return out


def next_move(br, iid: int, k_max: int):
    """search.terminal's next move: the first record (in order) with the smallest frame 1 .. k_max of a move's
    start state at j <= 1: (frame, its facing), else None."""
    arr, tb = barr(br)
    a = arr.get(iid)
    if a is None or not len(a):
        return None
    F = flags(tb, br.K)
    st = np.maximum(a[:, 3].astype(np.int64), 0)
    m = (a[:, 0] >= 1) & (a[:, 0] <= k_max) & (a[:, 3] >= 0) & (F.ms[st] >= 0) & (a[:, 4] <= 1)
    idx = np.flatnonzero(m)
    if not len(idx):
        return None
    ks = a[idx, 0]
    i = idx[int(np.argmin(ks))]                                   # argmin: the first of the smallest
    return (int(a[i, 0]), int(a[i, 7]))


# ---- the frames' shapes (search.branch_frames' rule) ------------------------------------------------------------------

@njit(cache=True)
def _rnd(v, scale):
    """Python's round(v, digits) as an integer key (scale = 10 ** digits): the double product, and a value at a half
    (within 1e-6) settled by Python's round."""
    p = v * scale
    f = math.floor(p)
    if abs((p - f) - 0.5) < 1e-6:
        with objmode(q="int64"):
            q = _py_round_key(v, scale)
        return q
    return np.int64(np.round(p))


def _py_round_key(v: float, scale: float) -> int:
    d = int(round(math.log10(scale)))
    return int(round(round(v, d) * scale))


@njit(cache=True)
def emit(A, IIDc, T):
    """branch_frames' first-occurrence rule: the records A [n, 9] (all Clappers, in the branch's order; IIDc their
    iid) drawn at k + a .. k + b inside 0 .. T; a (frame, key) already drawn by an earlier record (key: iid, state, j,
    round(x, 2), round(y, 2), face, ham) is not drawn again. Returns the (frame, record index) pairs in order."""
    n = A.shape[0]
    d = Dict.empty(key_type=_KEY7, value_type=types.int64)
    claimed = np.zeros((max(n, 1), T + 1), np.bool_)
    EK = np.empty(max(16, 4 * n), np.int64)
    EI = np.empty(max(16, 4 * n), np.int64)
    m = 0
    for i in range(n):
        lo = max(np.int64(A[i, 0] + A[i, 1]), 0)
        hi = min(np.int64(A[i, 0] + A[i, 2]), T)
        if lo > hi:
            continue
        key = (np.int64(IIDc[i]), np.int64(A[i, 3]), np.int64(A[i, 4]), _rnd(A[i, 5], 100.0), _rnd(A[i, 6], 100.0),
               np.int64(A[i, 7]), np.int64(A[i, 8]))
        if key in d:
            q = d[key]
        else:
            q = len(d)
            d[key] = q
        for kk in range(lo, hi + 1):
            if claimed[q, kk]:
                continue
            claimed[q, kk] = True
            if m >= EK.shape[0]:
                EK2 = np.empty(2 * EK.shape[0], np.int64)
                EI2 = np.empty(2 * EK.shape[0], np.int64)
                EK2[:m] = EK[:m]
                EI2[:m] = EI[:m]
                EK, EI = EK2, EI2
            EK[m] = kk
            EI[m] = i
            m += 1
    return EK[:m], EI[:m]


@njit(cache=True)
def first_hit(px, py, ifr, k0, k1, off, BX, IIDB, hk_iid, hk_lo, hk_hi, hw, hh, dy, wl, wr):
    """The first frame k0 .. k1 (not in her i-frames) where her hurtbox (transform px, py; HeroBox hw, hh, its centre
    dy below) leaves the walls (1) or meets a body box of the frame (2: BX rows off[k] .. off[k + 1] - 1, open
    overlap; a box of a hooked Clapper inside its window hk_lo .. hk_hi skipped): (k, 1 / 2), or (-1, 0)."""
    nf = off.shape[0] - 1
    for k in range(k0, k1 + 1):
        if ifr[k]:
            continue
        x = px[k]
        y = py[k]
        h0 = x - hw
        h1 = y + dy - hh
        h2 = x + hw
        h3 = y + dy + hh
        if h0 < wl or h2 > wr:
            return k, 1
        if k < 0 or k >= nf:
            continue
        for b in range(off[k], off[k + 1]):
            sk_ = False
            for q in range(hk_iid.shape[0]):
                if IIDB[b] == hk_iid[q] and hk_lo[q] <= k <= hk_hi[q]:
                    sk_ = True
                    break
            if sk_:
                continue
            if BX[b, 0] < h2 and BX[b, 2] > h0 and BX[b, 1] < h3 and BX[b, 3] > h1:
                return k, 2
    return -1, 0


__all__ = ["barr", "iids", "views", "robust_rows", "state_at", "move_spans", "next_move", "emit", "first_hit",
           "flags", "MOVE_STARTS"]
