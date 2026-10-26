"""Map v2 reflex stage 2: THE BATCHED GENERATOR of the one-Clapper window tables (HANDOFF 'Task reflex'). Offline code:
nothing in the bot imports it (tests/test_reflex.py checks it).

The exact generator (reflex.judge / judge_cl: the search's closed-loop evaluation judged strictly) costs 9 - 38 ms per
sample point and macro (a Clawline window 0.57 s with its continuation search); a table cell needs a macro that passes
at its sample points, and the macro grid has 9 - 2,400 members. Two tools make the tables affordable:

THE SCREEN (sound). A Clapper's COMMITTED move (COMMITTED: the slam from its antic to Slam Recover's end, the cast to
Cast 2's end, a jump's flight to its recovery, an evade, an antic up to Jump Aim) does not depend on her: its records,
timing views and damage shapes up to the first frame Kc where any branch leaves the move are the same in every
prediction - the judge's closed-loop one under the macro's own path and a REFERENCE prediction made once per Clapper
sample (state, frame, wall band edge, flight vx). Per lane (sample point x macro), rolled as kin_jit batches, the robust
down slash contact (strike.dslash_contact + the judge's robustness: no landing before it, the target shifted +-1 frame;
compiled here, robust_contacts) in every reference view and the window's target-state test (reflex._in_target): a lane
without both (its active frames + 1 within Kc) cannot pass the judge. A node (sample point) whose path cannot bring the
slash to the target at all (prune_nodes: the hull of her paths under every drift, the slash polygons' extent) is
dropped before its lanes are rolled.

TWO VERDICTS for the lanes the screen keeps:
  'exact'  reflex.judge / judge_cl_fast (judge_cl with the screen inside its continuation search: the same result) -
           the stage-1 generator, closed loop. Used for the ground windows and every Clawline window.
  'ref'    THE REFERENCE EVALUATION (refeval_ds): the judge's rule (lands, no collision to the macro's end, an exit:
           search.Evaluator.exit_ok) in every outcome of the REFERENCE prediction - the same as the judge while the
           macro and its exit horizon stay inside the committed move; after Kc the Clapper's next decision is drawn for
           her reference position, not the macro's path (no closed loop). ~5x cheaper; used for the down slash windows
           from the air / the float (millions of cells); its agreement with the judge is measured (reflex_build
           bitcheck) and the runtime re-checks every press from her exact state (reflex.Reflex.check).
A cell's ENTRY: the first macro (in the window's preference order: the earliest strike, the fewest frames, no drift
first) that passes at every sample point ('full'); else the one that passes at the most points if at least half
('partial', the runtime's check decides); else no window.

    from ssbot.map2 import reflex_gen as rg
    G = rg.Gen(W, ev)
    out = G.build_group(cells, o_template, mode="ref")      # {CellKey: Entry | None}; counters in G.stats / G.ms
"""
from __future__ import annotations

import math
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, replace

import numpy as np
from numba import njit

from ssbot.knowledge import kinematics as km
from ssbot.map2 import clapper as cm
from ssbot.map2 import reflex as rx
from ssbot.map2 import strike as sk

TAIL = 18                          # frames after a down slash press in a macro (Macro.tail)
MAX_TRY = 6                        # macros evaluated per cell (in order) before it settles
CTRL_W = 0                         # (off) a Clawline window: its down slash also landing with her control +-1 frame
# the moves that run without reading her from the anchor state on (their next decision reads her: Idle / Walk's
# choices, After Scuttle's pick, Jump Aim's target)
_SLAM = ("Slam Antic", "Slam 0", "Slam 1", "Slam Effects?", "Slam 2", "Slam Recover")
_CAST = ("Spell Antic", "Cast 1", "Cast 2")
_JCAST = ("Cast Slam Antic", "Cast Slam Antic 2", "Cast Jump")
_FLIGHT = ("Jump", "Air", "Slam 2", "Slam Recover")
COMMITTED = {"Slam Antic": _SLAM, "Spell Antic": _CAST, "Cast 1": _CAST, "Cast 2": _CAST, "Jump Antic": ("Jump Antic",),
             "Cast Slam Antic": _JCAST, "Cast Slam Antic 2": _JCAST, "Jump": _FLIGHT, "Air": _FLIGHT,
             "Evade Scuttle": ("Evade Scuttle",)}


# ---- the macro grids ------------------------------------------------------------------------------------------------

T_MAX = 50                         # the latest down slash press (frames from the decision)
HOPS_DS = tuple(range(1, 17))      # a hop's jump held 1 .. 16 frames (from the ground)
HOPS_CL = tuple(range(2, 9))       # the Clawline's hop from the ground: pressed in the air on the hop's frame h (the
#                                    bots' live ground Clawlines all had a hop of 2 - 4 frames; the strike module's
#                                    hook is calibrated on air presses: a press from the ground - its 7 / 8 frame antic -
#                                    is not in the grid)


def macro_grid(wt: rx.Window, cls: str, t_max: int = T_MAX) -> list:
    """Every macro of the family's grid for her class (the order is set per cell: Gen._order)."""
    out = []
    if wt.family == "cl":
        for h in (HOPS_CL if cls == "G" else (0,)):
            out.append(rx.Macro("cl", hop=h, tail=TAIL))
        return out
    if cls == "G":
        for h in HOPS_DS:
            for t in range(2, t_max + 1):
                for dd in (0, 1, -1):
                    out.append(rx.Macro("ds", hop=h, t=t, dd=dd, tail=TAIL))
    elif cls == "A":
        for t in range(1, t_max + 1):
            for dd in (0, 1, -1):
                out.append(rx.Macro("ds", t=t, dd=dd, tail=TAIL))
    else:
        for jh in (False, True):
            for t in range(1, t_max + 1):
                for dd in (0, 1, -1):
                    out.append(rx.Macro("ds", jh=jh, t=t, dd=dd, tail=TAIL))
    return out


# ---- the compiled robust contact (reflex._Robust over strike.dslash_contact) -------------------------------------------

@njit(cache=True)
def _poly_box(px, py, x0, y0, x1, y1) -> bool:
    """clapper.poly_box_hit: the convex polygon (px, py) meets the box (the separating axis test)."""
    m = px.shape[0]
    pmin_x, pmax_x, pmin_y, pmax_y = px[0], px[0], py[0], py[0]
    for i in range(1, m):
        pmin_x = min(pmin_x, px[i])
        pmax_x = max(pmax_x, px[i])
        pmin_y = min(pmin_y, py[i])
        pmax_y = max(pmax_y, py[i])
    if pmax_x <= x0 or pmin_x >= x1 or pmax_y <= y0 or pmin_y >= y1:
        return False
    qx = (x0, x1, x1, x0)
    qy = (y0, y0, y1, y1)
    for i in range(m):
        j = (i + 1) % m
        nx = -(py[j] - py[i])
        ny = px[j] - px[i]
        amin, amax = 1e300, -1e300
        for q in range(m):
            v = px[q] * nx + py[q] * ny
            amin = min(amin, v)
            amax = max(amax, v)
        cmin, cmax = 1e300, -1e300
        for q in range(4):
            v = qx[q] * nx + qy[q] * ny
            cmin = min(cmin, v)
            cmax = max(cmax, v)
        if amax <= cmin or cmax <= amin:
            return False
    return True


@njit(cache=True)
def _orig_contact(pos, face, gnd, t, n_last, B, k_off, sh, g, DX, DY, AX, AY) -> int:
    """strike.dslash_contact on the boxes B (absolute frames; the lane's frame 0 is B's frame k_off) shifted sh frames
    (sh > 0: the target late), grown by g (< 0 shrinks: the screen's float-safe bounds)."""
    first0, first1 = -1, -1
    hi = min(t + 9, n_last)
    for c in range(t + 3, hi + 1):
        if gnd[c]:
            break
        k = c + k_off - sh
        if k < 0 or k >= B.shape[0] or c + k_off >= B.shape[0]:
            continue
        if np.isnan(B[k, 0]):
            continue
        f = 1.0 if face[c] >= 0 else -1.0
        if first0 < 0 and _poly_box(DX * f + pos[c, 0], DY + pos[c, 1], B[k, 0] - g, B[k, 1] - g, B[k, 2] + g,
                                    B[k, 3] + g):
            first0 = c
        if first1 < 0 and _poly_box(AX * f + pos[c, 0], AY + pos[c, 1], B[k, 0] - g, B[k, 1] - g, B[k, 2] + g,
                                    B[k, 3] + g):
            first1 = c
        if first0 >= 0 and first1 >= 0:
            return max(first0, first1)
    return -1


@njit(cache=True)
def robust_contacts(pos, face, gnd, t_arr, n_arr, k_off, Bs, g, land_bb, foot, floor, DX, DY, AX, AY):
    """[L, V] the judge's robust down slash contact frame per lane (lane frames; pos [L, T + 1, 2] her transform,
    face / gnd [L, T + 1], the press t, the lane's frames n, the lane's frame 0 at Bs' frame k_off[L]) in each view's
    boxes Bs [V, T, 4]: -1 none (reflex._Robust: the contact, no landing between the press and it, the target shifted
    one frame late and early still met)."""
    L = pos.shape[0]
    V = Bs.shape[0]
    out = np.full((L, V), -1, np.int64)
    for i in range(L):
        t = t_arr[i]
        nl = n_arr[i]
        ko = k_off[i]
        for v in range(V):
            B = Bs[v]
            c = _orig_contact(pos[i], face[i], gnd[i], t, nl, B, ko, 0, g, DX, DY, AX, AY)
            if c < 0:
                continue
            bad = False
            for k in range(t + 1, c + 1):
                if gnd[i, k] or pos[i, k, 1] - foot - floor <= land_bb:
                    bad = True
                    break
            if bad:
                continue
            if _orig_contact(pos[i], face[i], gnd[i], t, nl, B, ko, 1, g, DX, DY, AX, AY) < 0:
                continue
            if _orig_contact(pos[i], face[i], gnd[i], t, nl, B, ko, -1, g, DX, DY, AX, AY) < 0:
                continue
            out[i, v] = c
    return out


_DX, _DY = np.ascontiguousarray(sk.DOWN[:, 0]), np.ascontiguousarray(sk.DOWN[:, 1])
_AX, _AY = np.ascontiguousarray(sk.DOWN_ALT[:, 0]), np.ascontiguousarray(sk.DOWN_ALT[:, 1])


def contacts(pos, face, gnd, t_arr, n_arr, Bs, k_off=None, grow: float = 0.0) -> np.ndarray:
    L = len(t_arr)
    ko = np.zeros(L, np.int64) if k_off is None else np.ascontiguousarray(k_off, np.int64)
    return robust_contacts(np.ascontiguousarray(pos), np.ascontiguousarray(face, np.int64),
                           np.ascontiguousarray(gnd, np.bool_), np.ascontiguousarray(t_arr, np.int64),
                           np.ascontiguousarray(n_arr, np.int64), ko, np.ascontiguousarray(Bs, np.float64), float(grow),
                           rx.LAND_BB, sk.FOOT, sk.FLOOR, _DX, _DY, _AX, _AY)


SCREEN_EPS = 1e-6                  # u: the exact screen's boxes grown (a possible contact) / shrunk (a certain one)


# ---- the reference prediction of one Clapper sample ---------------------------------------------------------------------

class Ref:
    """One Clapper sample (its Obs at frame 0, the target): the reference prediction's outcomes (its branches x timing
    views, search.timing_views), per view the target's robust boxes (strike.robust_boxes), the window's target-state
    mask (reflex._in_target), the big rune's end (search.rune_end), and Kc - the last frame up to which every view's
    target is still in its committed move (the screen's horizon). alpha (stage 4): the physics phase of the sample
    points the prediction serves (their ALPHA: the cells' corners are at 0) - its Clappers' steps anchored as the
    judge's (reflex.clapper_steps), so the screen stays sound for the judge."""

    def __init__(self, W, o, wt: rx.Window, T: int = 160, alpha: float = 0.0):
        from ssbot.map2 import clapper_jit as cj
        from ssbot.map2 import search as ms
        self.o, self.wt, self.T, self.alpha = o, wt, T, float(alpha)
        S_a = km.initial_state(W.params, 0.0, sk.FLOOR + sk.FOOT, ground=True)
        S_a[km.ALPHA] = self.alpha
        path = cm.HeroPath.constant(o.x + 9.0 * o.face, sk.FLOOR + sk.FOOT, T=T, steps=rx.clapper_steps(W, S_a, T))
        self.P = cj.predict([o], {o.iid: cm.Memory()}, path, W.K, T=T)
        self.views = [v for b in self.P.branches for v in ms.timing_views(b)]
        self.p = np.array([b0.p / len(ms.timing_views(b0)) for b0 in self.P.branches for _ in ms.timing_views(b0)])
        comm = COMMITTED.get(o.st, (o.st,))
        V = len(self.views)
        self.B = np.full((V, T + 1, 4), np.nan)
        self.tgt = np.zeros((V, T + 12), bool)
        self.rune_end = []
        kc = T
        for vi, v in enumerate(self.views):
            b = sk.robust_boxes(v, o.iid, T)
            self.B[vi, :len(b)] = b[:T + 1]
            for k in range(1, T + 1):
                self.tgt[vi, k] = rx._in_target(v, o.iid, k, wt.target)
            for k in range(0, T + 1):
                st = rx._state_near(v, o.iid, k)
                if st is None or st[0] not in comm:
                    kc = min(kc, k - 1)
                    break
            self.rune_end.append(ms.rune_end(v))
        self.Kc = kc
        # the window's frames per view (prune_nodes, the macro grid's last press): the first run of target-state
        # frames (the anchored move's; the prediction's later moves are not this window)
        self.win_k = []
        for vi in range(V):
            ks = np.flatnonzero(self.tgt[vi, :T + 1])
            if len(ks):
                br_ = np.flatnonzero(np.diff(ks) > 1)
                ks = ks[:br_[0] + 1] if len(br_) else ks
            self.win_k.append(ks)


# ---- the node prune and the screen ----------------------------------------------------------------------------------

SLASH_X = float(max(np.abs(sk.DOWN[:, 0]).max(), np.abs(sk.DOWN_ALT[:, 0]).max()))
SLASH_Y = (float(min(sk.DOWN[:, 1].min(), sk.DOWN_ALT[:, 1].min())), float(max(sk.DOWN[:, 1].max(), sk.DOWN_ALT[:, 1].max())))
PRUNE_PAD = 0.75                   # u: the bound's slack (the paths between the drift extremes, the render's lag)


def _bound_masks(cls: str, n: int) -> list:
    """The key sequences whose paths bound every macro's path before its contact (the drift extremes; from the float:
    the umbrella kept / closed; from the ground: the shortest and the longest hop)."""
    out = []
    for d in (0, km.B_LEFT, km.B_RIGHT):
        if cls == "F":
            out.append(np.full(n, km.B_JUMP | d, np.int64))
            out.append(np.full(n, d, np.int64))
        elif cls == "G":
            for h in (HOPS_DS[0], HOPS_DS[-1]):
                m = np.full(n, d, np.int64)
                m[:h] |= km.B_JUMP
                out.append(m)
        else:
            out.append(np.full(n, d, np.int64))
    return out


def prune_nodes(W, ref: Ref, nodes: list, cls: str, t_max: int) -> np.ndarray:
    """[N] bool: the node can bring the down slash onto the target in every view (a necessary condition, PRUNE_PAD of
    slack): the hull of her paths under the bounding key sequences, grown by the slash polygons' extent, meets the
    target's box at a frame of its window (t + 3 .. t + 9 of some press t <= t_max) in every view."""
    if not nodes:
        return np.zeros(0, bool)
    n = t_max + 10
    ms_ = _bound_masks(cls, n)
    S0 = np.stack([np.asarray(S, float) for S in nodes], axis=1)
    N = len(nodes)
    xs = np.empty((len(ms_), N, n + 1))
    ys = np.empty((len(ms_), N, n + 1))
    for q, m in enumerate(ms_):
        r = km.rollout(S0, np.repeat(m[None], N, axis=0), W.params, W.terr)
        xs[q], ys[q] = r.pos[:, :, 0], r.pos[:, :, 1]
    x0, x1 = xs.min(0) - SLASH_X - PRUNE_PAD, xs.max(0) + SLASH_X + PRUNE_PAD
    y0, y1 = ys.min(0) + SLASH_Y[0] - PRUNE_PAD, ys.max(0) + SLASH_Y[1] + PRUNE_PAD
    ok = np.ones(N, bool)
    for vi in range(len(ref.views)):
        ks = ref.win_k[vi]
        ks = ks[(ks >= 4) & (ks <= n)]
        if not len(ks):
            return np.zeros(N, bool)
        B = ref.B[vi, ks]                                   # [nk, 4]
        hit = ((x0[:, ks] < B[None, :, 2]) & (x1[:, ks] > B[None, :, 0]) &
               (y0[:, ks] < B[None, :, 3]) & (y1[:, ks] > B[None, :, 1])).any(axis=1)
        ok &= hit
    return ok


@dataclass
class Lanes:
    """The screen's result per node and macro: ok (not pruned), c [N, M, V] the contact frame per reference view (-1:
    none / not computed), why (0 kept, 1 no contact, 2 not the target state, 3 a collision, 4 kept: its window reaches
    past Kc, 5 the node pruned, 6 no slash starts at the press - stage 4)."""
    ok: np.ndarray
    c: np.ndarray
    why: np.ndarray


def _render_lanes(macros: list, d_arr: np.ndarray) -> tuple:
    """masks [N * M, n_max] for nodes with target sides d_arr [N] and the macros (node-major), t / n per lane."""
    N, M = len(d_arr), len(macros)
    raws = {}
    for d in (1, -1):
        if (d_arr == d).any():
            raws[d] = [rx.render(m, d) for m in macros]
    n_max = max(len(r.pre) for rr in raws.values() for r in rr)
    masks = np.zeros((N * M, n_max), np.int64)
    t_arr = np.zeros(N * M, np.int64)
    n_arr = np.zeros(N * M, np.int64)
    for i in range(N):
        rr = raws[int(d_arr[i])]
        for q, r in enumerate(rr):
            L = i * M + q
            masks[L, :len(r.pre)] = r.pre
            t_arr[L] = r.ds[0] if r.ds else 0
            n_arr[L] = len(r.pre)
    return masks, t_arr, n_arr


def _facing(face0: np.ndarray, masks: np.ndarray) -> np.ndarray:
    """strike.facing_track per lane: [L, T + 1]."""
    L, T = masks.shape
    out = np.empty((L, T + 1), np.int64)
    cur = np.where(face0 >= 0, 1, -1).astype(np.int64)
    out[:, 0] = cur
    for i in range(T):
        m = masks[:, i]
        r = (m & km.B_RIGHT) != 0
        l_ = (m & km.B_LEFT) != 0
        cur = np.where(r & ~l_, 1, np.where(l_ & ~r, -1, cur))
        out[:, i + 1] = cur
    return out


def screen_ds(W, ref: Ref, nodes: list, macros: list, alive: np.ndarray | None = None, chunk: int = 8000,
              exact: bool = False, collide: bool | None = None) -> Lanes:
    """The screen (module docstring) of the down slash macros from the nodes (her kin states at frame 0). exact: sound
    for the judge (the contact on boxes grown by SCREEN_EPS; a certain contact - the same frame on boxes shrunk by it -
    in every view also gets the collision test: its bounce rolled, search.first_collision up to Kc); else consistent
    with the reference evaluation (the contact as it computes it)."""
    from ssbot.map2 import search as ms
    collide = exact if collide is None else collide
    N, M, V = len(nodes), len(macros), len(ref.views)
    ok = np.zeros((N, M), bool)
    cc = np.full((N, M, V), -1, np.int64)
    why = np.full((N, M), 5, np.int8)
    idx = np.flatnonzero(alive) if alive is not None else np.arange(N)
    if not len(idx) or not M:
        return Lanes(ok, cc, why)
    S0 = np.stack([np.asarray(nodes[i], float) for i in idx], axis=1)
    d_arr = np.array([1 if ref.o.x >= float(nodes[i][km.PX]) else -1 for i in idx], np.int64)
    masks, t_arr, n_arr = _render_lanes(macros, d_arr)
    face0 = np.array([int(nodes[i][km.FACE]) if nodes[i][km.FACE] != 0 else 1 for i in idx], np.int64)
    NL = len(idx) * M
    Kc = ref.Kc
    for a in range(0, NL, chunk):
        b = min(a + chunk, NL)
        ni = np.arange(a, b) // M
        r = km.rollout(S0[:, ni], masks[a:b], W.params, W.terr)
        gnd = (r.flags & km.F_GROUND) != 0
        face = _facing(face0[ni], masks[a:b])
        if exact:
            c = contacts(r.pos, face, gnd, t_arr[a:b], n_arr[a:b], ref.B, grow=SCREEN_EPS)
            cs = contacts(r.pos, face, gnd, t_arr[a:b], n_arr[a:b], ref.B, grow=-SCREEN_EPS)
        else:
            c = cs = contacts(r.pos, face, gnd, t_arr[a:b], n_arr[a:b], ref.B)
        node = idx[ni]
        q = np.arange(a, b) % M
        t = t_arr[a:b]
        beyond = t + 10 > Kc
        has = (c >= 0).all(axis=1)
        tg = np.ones(b - a, bool)
        for v in range(V):
            cv = np.where(c[:, v] >= 0, c[:, v], 0)
            tg &= ref.tgt[v, cv]
        certain = (c == cs).all(axis=1)
        if exact:
            tg |= ~certain                                 # (an uncertain contact frame: its target state not tested)
        # (stage 4) the kin's slash must START on the press frame (the float's release + attack on frame 1: the Deflate
        # eats the attack - no slash; reflex.swings): a lane without it cannot pass the judge, beyond Kc too
        li = np.arange(b - a)
        att = (r.flags & km.F_ATTACKING) != 0
        tt = np.clip(t, 1, att.shape[1] - 1)
        swing = att[li, tt] & ~att[li, tt - 1] & (t >= 1)
        keep = swing & (beyond | (has & tg))
        wy = np.where(~swing, 6, np.where(beyond, 4, np.where(~has, 1, np.where(~tg, 2, 0)))).astype(np.int8)
        if collide:
            # the collision test of the certain lanes up to Kc (their bounce rolled per view's contact frame)
            sel = np.flatnonzero(keep & ~beyond & certain)
            if len(sel):
                pairs = [(int(li), v) for li in sel for v in range(V)]
                nmax = int(n_arr[a:b][sel].max())
                M2 = np.zeros((len(pairs), nmax), np.int64)
                E2 = np.zeros((len(pairs), nmax), np.int64)
                for pi, (li, v) in enumerate(pairs):
                    nl = int(n_arr[a + li])
                    M2[pi, :nl] = masks[a + li, :nl]
                    E2[pi, int(c[li, v]) - 1] |= km.EV_POGO
                lanes_n = np.array([ni[li] for (li, v) in pairs], np.int64)
                rb = km.rollout(S0[:, lanes_n], M2, W.params, W.terr, events=E2)
                bad = set()
                for pi, (li, v) in enumerate(pairs):
                    if li in bad:
                        continue
                    nl = int(n_arr[a + li])
                    tr = _LightTr(rb.pos[pi], int(c[li, v]), nl)
                    if ms.first_collision(ref.views[v], tr, 1, min(nl, Kc), True) is not None:
                        bad.add(li)
                for li in bad:
                    keep[li] = False
                    wy[li] = 3
        ok[node, q] = keep
        cc[node, q] = c
        why[node, q] = wy
    return Lanes(ok, cc, why)


# ---- the reference evaluation (ds) ------------------------------------------------------------------------------------

class _LightTr:
    """What search.first_collision reads of a trajectory: her transform per frame, her i-frames, no hooks."""
    __slots__ = ("pos", "ifr", "hooks")

    def __init__(self, pos, c: int, n: int):
        self.pos = np.ascontiguousarray(pos[:n + 1])
        ifr = np.zeros(n + 1, bool)
        if c >= 0:
            ifr[c + sk.DS_IFR[0]:c + sk.DS_IFR[1] + 1] = True
        self.ifr = ifr
        self.hooks = []


@dataclass
class RV:
    """A reference verdict (the judge's fields that the table keeps)."""
    window: bool
    why: str
    k_strike: tuple
    end: tuple


_CU0 = np.array([-1.0, 0, 0, 0, 0, 0, 0])


def _exit(W, ev, S: np.ndarray, k0: int, br, ifr_until: int, H: int, full: bool) -> bool:
    """search.Evaluator.exit_ok's verdict (full) or its probes only (full False: a probe that touches no danger is
    an exit; none -> no exit, without the envelope pass that may still find one - conservative, 2.3 ms saved per
    failed probe set)."""
    from ssbot.map2 import env_jit as ej
    from ssbot.map2 import search as ms
    if full:
        return ev.exit_ok(S, None, k0, br, ifr_until, H) > 0
    dz, boxes, off = ms._packed_danger(br, k0, H, ifr_until, True)
    S = np.asarray(S, np.float64)
    return ej.probe_exit(S, _CU0, ms._probe_masks(S, H), W.E.udt, W.E.P, W.TT, boxes, off, ms.PROBE_EPS) >= 0


def refeval_ds(W, ev, ref: Ref, S: np.ndarray, macro: rx.Macro, cs: np.ndarray, full_exit: bool = False) -> RV:
    """The judge's rule in every outcome of the reference prediction (module docstring): cs [V] the screen's contact
    per view (lane frames; -1 none)."""
    from ssbot.map2 import search as ms
    o = ref.o
    d = 1 if o.x >= float(S[km.PX]) else -1
    raw = rx.render(macro, d)
    masks = raw.pre
    n = len(masks)
    ks = []
    rolled = {}
    order = np.argsort(-ref.p, kind="stable")
    for vi in order:
        c = int(cs[vi])
        v = ref.views[vi]
        if c < 0:
            return RV(False, "miss", (), ())
        if not ref.tgt[vi, c]:
            return RV(False, "tgt", (), ())
        r = rolled.get(c)
        if r is None:
            evs = np.zeros(n, np.int64)
            evs[c - 1] |= km.EV_POGO
            r = W.roll(S, masks, evs)
            rolled[c] = r
        tr = _LightTr(r.pos[0], c, n)
        kcol = ms.first_collision(v, tr, 1, n, True)
        if kcol is not None:
            return RV(False, f"hit@{kcol}", (), ())
        H = ev.cfg.exit_h
        re_ = ref.rune_end[vi]
        if re_ is not None and re_ > n + H:
            H = min(re_ - n + 2, ev.cfg.exit_h_max)
        Se = r.final[:, 0]
        if not _exit(W, ev, Se, n, v, c + sk.DS_IFR[1], H, full_exit):
            return RV(False, f"exit@{n}", (), ())
        ks.append(c)
    r = rolled[int(cs[order[0]])]
    Se = r.final[:, 0]
    end = (round((float(Se[km.PX]) - o.x) * o.face, 3), round(float(Se[km.PY]) - sk.FOOT - sk.FLOOR, 3),
           round(float(Se[km.VX]) * o.face, 2), round(float(Se[km.VY]), 2))
    return RV(True, "", (min(ks), max(ks)), end)


# ---- judge_cl with the screen inside (the exact Clawline window, faster) ----------------------------------------------

def judge_cl_fast(W, ev, S: np.ndarray, obs: list, iid: int, wt: rx.Window, macro: rx.Macro, ref: Ref | None = None,
                  mems: dict | None = None, hazards: list | None = None, robust: bool = True, dds: tuple = (0, 1, -1),
                  stats: Counter | None = None, ctrl_w: int = 0) -> rx.Verdict:
    """reflex.judge_cl with the same search order; a continuation (variant, dd, k) is judged only when the screen
    finds its robust down slash contact on the target in the window's target states in every reference view (its
    active frames + 1 and the hook within Kc; ref: the target's reference prediction) - the others cannot pass the
    judge, so the verdict and the continuation found are judge_cl's."""
    if ref is not None and abs(float(S[km.ALPHA]) - ref.alpha) > 1e-9:
        ref = None                                          # (the screen's prediction is anchored at another phase)
    if ref is None or wt.strike == "claw" or wt.family != "cl" or             int(next(o for o in obs if o.iid == iid).hp) <= rx.LOW_HP_CL:
        return rx.judge_cl(W, ev, S, obs, iid, wt, macro, mems, hazards, robust, dds)
    from ssbot.map2 import clapper_jit as cj
    from ssbot.map2 import search as ms
    t0 = time.perf_counter()
    tgt = next(o for o in obs if o.iid == iid)
    hx = float(S[km.PX])
    d = 1 if tgt.x >= hx else -1
    base = rx.render(replace(macro, k=None, cont=()), d)
    pre = base.pre
    sit = ms.Situation(np.asarray(S, float), list(obs), mems if mems is not None else {o.iid: cm.Memory() for o in obs},
                       list(hazards or ()))
    variants = rx.judge_variants(tgt, robust)
    with rx._Robust(robust, variants=variants):
        T = len(pre) + 80
        P0 = cj.predict(sit.obs, sit.mems, cm.HeroPath.constant(hx, float(S[km.PY]), T=T,
                                                              steps=rx.clapper_steps(W, S, T)), W.K, T=T,
                        hazards=sit.hazards)
        br = max(P0.branches, key=lambda b: b.p)
        ctrls = rx._hook_ctrls(W, sit.S, base, iid, br, sit.alpha_c)
    kt = [k for k in range(len(pre) + 1, T) if (lambda st: st is not None and rx.in_states(st[0], int(st[1]), wt.target))(
        rx._state_near(br, iid, k))]
    # the screen's data: her state at the press and each variant's hook in each reference view
    n = len(pre)
    Sp = W.roll(sit.S, pre).final[:, 0]
    V = len(ref.views)
    found, last = {}, {}
    raw_pre = macro.raw[0] if macro.raw is not None else None
    claw_d = int(macro.raw[1]) if macro.raw is not None and macro.raw[1] else d
    for v in variants:
        c = ctrls.get(v.name, -1)
        if c < 0 or not kt:
            continue
        lo, hi = max(c + 9, kt[0] - 9), min(kt[-1] - 3, c + 40)
        allowed = _cl_screen(W, ref, sit.S, raw_pre if raw_pre is not None else pre, Sp, n, claw_d, iid, v,
                             sit.alpha_c, float(Sp[km.AIRDASHED]), c, lo, hi, dds, ctrl_w)
        for dd in dds:
            for k in range(lo, hi + 1):
                if allowed is not None and (k, dd) not in allowed:
                    if stats is not None:
                        stats["cl_skipped"] += 1
                    continue
                m = (rx.Macro("cl", raw=(raw_pre if raw_pre is not None else pre, claw_d, np.zeros(1, np.int64), []),
                              cont=((v.name, k, dd),), tail=macro.tail))
                vd = rx.judge(W, ev, S, obs, iid, wt, m, mems, hazards, robust=robust, variants=(v,))
                if stats is not None:
                    stats["cl_judged"] += 1
                last[v.name] = vd
                if vd.window:
                    found[v.name] = (k, dd, vd)
                    break
            if v.name in found:
                break
    ok = len(found) == len(variants)
    vs = [found[v.name][2] if v.name in found else last.get(v.name) for v in variants]
    vs = [x for x in vs if x is not None]
    why = "" if ok else next((f"{v.name}:" + (last[v.name].why if v.name in last else "no ctrl / target")
                              for v in variants if v.name not in found), "")
    ks = [k for x in vs for k in x.k_strike]
    return rx.Verdict(ok, sum(x.lands for x in vs), sum(x.safe for x in vs), sum(x.exit for x in vs),
                      sum(x.n for x in vs), why, (min(ks), max(ks)) if ks else (), max((x.k_end for x in vs), default=0),
                      vs[0].end if vs else (), (time.perf_counter() - t0) * 1e3, [],
                      {v.name: (found[v.name][2].by_var if v.name in found else {}) for v in variants},
                      tuple((v.name, found[v.name][0], found[v.name][1]) for v in variants if v.name in found))


class _TrCl:
    """search.first_collision's view of a Clawline macro's trajectory: her transform per absolute frame, her i-frames,
    the hook (its body-harmless window)."""
    __slots__ = ("pos", "ifr", "hooks")

    def __init__(self, pos, ifr, hooks):
        self.pos, self.ifr, self.hooks = pos, ifr, hooks


def _cl_screen(W, ref: Ref, S0: np.ndarray, pre: np.ndarray, Sp: np.ndarray, n: int, d: int, iid: int, var,
               alpha_c: int, airdashed: float, c_plan: int, lo: int, hi: int, dds: tuple, ctrl_w: int = 0):
    """The (k, dd) continuations of one hook variant that may pass: per reference view the hook (strike.claw_hook on
    that view's robust boxes; its control must be the planned one, c_plan, else the judge cuts the continuation) and
    no collision on the way to control (the hooked body harmless from P + 17), then the continuation rolled from
    control (its forced bounce) with the down slash at k: the robust contact in the window's target states and no
    collision after it, in every view, up to Kc. None: the screen does not apply (the contact window past Kc)."""
    from ssbot.map2 import search as ms
    if c_plan + 1 > ref.Kc or hi + 10 > ref.Kc:
        return None
    Kc = ref.Kc
    pre_pos = W.roll(S0, pre).pos[0]
    hooks, Ss = [], []
    for vi in range(len(ref.views)):
        bx = ref.B[vi]
        if len(bx) < n + 62:
            bx = np.concatenate([bx, np.full((n + 62 - len(bx), 4), np.nan)])
        h = sk.claw_hook(Sp, n, d, iid, bx, var, alpha_c)
        if not h.ok or h.ctrl != c_plan:
            return set()
        pos = np.concatenate([pre_pos, h.pos[1:]])
        if ms.first_collision(ref.views[vi], _TrCl(pos, np.zeros(len(pos), bool), [h]), 1, min(c_plan, Kc),
                              True) is not None:
            return set()
        hooks.append((h, pos))
        Ss.append(sk.control_state(W.params, h, float(Sp[km.ALPHA]), airdashed=airdashed))
    lanes = [(k, dd) for dd in dds for k in range(lo, hi + 1)]
    if not lanes:
        return set()
    L = len(lanes)
    mlen = max(k + 1 + TAIL - c_plan for (k, dd) in lanes)
    masks = np.zeros((L, mlen), np.int64)
    t_arr = np.zeros(L, np.int64)
    n_arr = np.zeros(L, np.int64)
    for i, (k, dd) in enumerate(lanes):
        post = rx._cl_post(n, k, d * dd, TAIL)
        m = post[c_plan - n:] if c_plan - n < len(post) else np.zeros(1, np.int64)
        masks[i, :len(m)] = m
        t_arr[i] = k - c_plan
        n_arr[i] = len(m)
    face = _facing(np.full(L, d, np.int64), masks)
    ok = np.ones(L, bool)
    cs = np.full((L, len(Ss)), -1, np.int64)
    for vi, Sc in enumerate(Ss):
        evs = np.zeros((L, mlen), np.int64)
        evs[:, 0] = km.EV_POGO
        r = km.rollout(Sc, masks, W.params, W.terr, events=evs)
        gnd = (r.flags & km.F_GROUND) != 0
        c = contacts(r.pos, face, gnd, t_arr, n_arr, ref.B[vi:vi + 1], np.full(L, c_plan, np.int64))[:, 0]
        cs[:, vi] = c
        ok &= np.array([ci >= 0 and ref.tgt[vi, c_plan + ci] for ci in c])
    # ROBUST TO THE CONTROL FRAME (ctrl_w): the down slash stays at its absolute frame k (the runtime's Press), so
    # it must also land when her control comes ctrl_w frames earlier / later (the dash's stop a physics step off:
    # the replay found the late variant's control a frame off inside cells whose corners agreed) - the
    # continuation from control (its bounce) shifted, the target's boxes as they are
    for dc in [x for w_ in range(1, ctrl_w + 1) for x in (-w_, w_)]:
        c2 = c_plan + dc
        if c2 < n + 1:
            continue
        sel = np.flatnonzero(ok)
        if not len(sel):
            break
        m2 = np.zeros((len(sel), mlen + ctrl_w), np.int64)
        t2 = np.zeros(len(sel), np.int64)
        n2 = np.zeros(len(sel), np.int64)
        for q, i in enumerate(sel):
            k, dd = lanes[i]
            post = rx._cl_post(n, k, d * dd, TAIL)
            m = post[c2 - n:] if c2 - n < len(post) else np.zeros(1, np.int64)
            m2[q, :len(m)] = m
            t2[q] = k - c2
            n2[q] = len(m)
        f2 = _facing(np.full(len(sel), d, np.int64), m2)
        for vi, Sc in enumerate(Ss):
            evs = np.zeros(m2.shape, np.int64)
            evs[:, 0] = km.EV_POGO
            r = km.rollout(Sc, m2, W.params, W.terr, events=evs)
            gnd = (r.flags & km.F_GROUND) != 0
            c = contacts(r.pos, f2, gnd, t2, n2, ref.B[vi:vi + 1], np.full(len(sel), c2, np.int64))[:, 0]
            for q, i in enumerate(sel):
                if c[q] < 0 or not ref.tgt[vi, c2 + c[q]]:
                    ok[i] = False
    # the continuation's collisions (its bounce rolled) up to Kc, view by view
    for i in np.flatnonzero(ok):
        nl = int(n_arr[i])
        for vi, Sc in enumerate(Ss):
            c = int(cs[i, vi])
            evs = np.zeros(nl, np.int64)
            evs[0] |= km.EV_POGO
            evs[c - 1] |= km.EV_POGO
            r = W.roll(Sc, masks[i, :nl], evs)
            h, hpos = hooks[vi]
            pos = np.concatenate([hpos, r.pos[0, 1:nl + 1]])
            ifr = np.zeros(len(pos), bool)
            ifr[c_plan + c + sk.DS_IFR[0]:c_plan + c + sk.DS_IFR[1] + 1] = True
            if ms.first_collision(ref.views[vi], _TrCl(pos, ifr, [h]), c_plan + 1, min(len(pos) - 1, Kc),
                                  True) is not None:
                ok[i] = False
                break
    return {lanes[i] for i in np.flatnonzero(ok)}


# ---- the generator ------------------------------------------------------------------------------------------------

def _order(macros: list, cn: np.ndarray, cand: np.ndarray) -> list:
    """The window's preference among the candidate macros: the earliest strike (the latest contact over the nodes and
    views), the fewest frames, no drift first, the float kept last."""
    c = list(cand)
    c.sort(key=lambda q: (int(cn[q]) if cn[q] >= 0 else 10 ** 4, macros[q].t + macros[q].hop, abs(macros[q].dd),
                          int(macros[q].jh), macros[q].dd))
    return c


class Gen:
    """The batched generator (module docstring): build_group over the cells of one (window type, Clapper state, frame,
    wall band, flight vx / charge, her class)."""

    def __init__(self, W, ev=None, max_try: int = MAX_TRY, t_max: int = T_MAX, full_exit: bool = False,
                 collide: bool = False, ctrl_w: int = CTRL_W):
        self.W = W
        self.ctrl_w = ctrl_w                               # a Clawline window's continuation robust to +-ctrl_w control
        self.cl_partial = False                            # Clawline windows: full cells only (the runtime's rule)
        self.collide = collide                             # the screen's collision test (exact mode: always)
        self.ev = ev or rx.judge_evaluator(W)
        self.full_exit = full_exit                         # 'ref': the exit's envelope pass after failed probes
        self.max_try = max_try
        self.t_max = t_max
        self.stats = Counter()
        self.ms = Counter()

    def _tm(self, k: str, t0: float) -> None:
        self.ms[k] += (time.perf_counter() - t0) * 1e3

    def build_group(self, cells: list, o_template, mode: str = "ref") -> dict:
        """{CellKey: (Entry, n_pass, n_nodes) | None} for cells sharing (wt, st, j, band, cvx, chg, cls). mode 'exact'
        (reflex.judge / judge_cl_fast) or 'ref' (refeval_ds; a Clawline window is always exact)."""
        if not cells:
            return {}
        k0 = cells[0]
        wt = rx.WINDOWS[k0.wt]
        o_t = replace(o_template, j=k0.j, t=k0.j / 60.0)
        t0 = time.perf_counter()
        node_ix: dict = {}
        nodes_by_o: dict = defaultdict(list)
        o_by: dict = {}
        cell_nodes: dict = {}
        for key in cells:
            ids = []
            for (S, obs) in rx.cell_samples(self.W, key, o_t, eps=0.0):
                o = obs[0]
                ok_ = (round(o.x, 6), round(o.vx, 6), bool(o.charged), round(float(S[km.ALPHA]), 9))
                #     (stage 4: the float's corners are at several physics phases - one reference prediction per phase)
                o_by.setdefault(ok_, o)
                nk = (ok_, np.asarray(S, float).tobytes())
                if nk not in node_ix:
                    node_ix[nk] = (ok_, len(nodes_by_o[ok_]))
                    nodes_by_o[ok_].append(S)
                ids.append(node_ix[nk])
            cell_nodes[key] = ids
        self._tm("samples", t0)
        refs, lanes = {}, {}
        t_hi = 0
        for ok_ in nodes_by_o:
            t0 = time.perf_counter()
            refs[ok_] = Ref(self.W, o_by[ok_], wt, alpha=ok_[3])
            self._tm("ref", t0)
            for wk in refs[ok_].win_k:
                if len(wk):
                    t_hi = max(t_hi, int(wk.max()) - 3)     # a press later than this cannot contact in the window
        t_hi = min(t_hi, self.t_max)
        macros = macro_grid(wt, k0.cls, t_hi) if wt.family == "ds" else macro_grid(wt, k0.cls)
        self.stats["macros"] += len(macros)
        if not macros:
            self.stats["cells"] += len(cell_nodes)
            self.stats["cells_screened_out"] += len(cell_nodes)
            return {key: None for key in cell_nodes}
        for ok_, nodes in nodes_by_o.items():
            self.stats["nodes"] += len(nodes)
            if wt.family == "ds":
                t0 = time.perf_counter()
                alive = prune_nodes(self.W, refs[ok_], nodes, k0.cls, t_hi) if k0.cls != "G" else None
                self._tm("prune", t0)
                if alive is not None:
                    self.stats["nodes_pruned"] += int((~alive).sum())
                t0 = time.perf_counter()
                lanes[ok_] = screen_ds(self.W, refs[ok_], nodes, macros, alive, exact=(mode == "exact"),
                                       collide=(mode == "exact") or self.collide)
                self._tm("screen", t0)
                self.stats["lanes"] += int(len(nodes) if alive is None else alive.sum()) * len(macros)
        cache: dict = {}
        out = {}
        # a Clawline window's PARTIAL cell is not kept (the runtime takes only full Clawline cells: Reflex.cl_partial)
        partial_ok = wt.family != "cl" or self.cl_partial
        for key, ids in cell_nodes.items():
            self.stats["cells"] += 1
            if wt.family == "ds":
                alive_m = np.ones(len(macros), bool)
                cn = np.full(len(macros), -1, np.int64)
                nviable = np.zeros(len(macros), np.int64)
                for (ok_, ni) in ids:
                    ln = lanes[ok_]
                    nviable += ln.ok[ni]
                    cn = np.maximum(cn, ln.c[ni].max(axis=1))
                full_c = np.flatnonzero(nviable == len(ids))
                part_c = np.flatnonzero((nviable < len(ids)) & (nviable * 2 >= len(ids)))
                cand = _order(macros, cn, full_c) + _order(macros, cn, part_c)
            else:
                cand = list(range(len(macros)))
            if not cand:
                self.stats["cells_screened_out"] += 1
                out[key] = None
                continue
            best = None                                    # (n_pass, -rank, q, verdicts)
            for rank, q in enumerate(cand[:self.max_try]):
                m = macros[q]
                vs = []
                fails = 0
                for (ok_, ni) in ids:
                    ck = (ok_, ni, q)
                    v = cache.get(ck)
                    if v is None:
                        v = self._verdict(mode, wt, refs[ok_], o_by[ok_], nodes_by_o[ok_][ni], m,
                                          lanes[ok_].c[ni, q] if wt.family == "ds" else None,
                                          lanes[ok_].ok[ni, q] if wt.family == "ds" else True)
                        cache[ck] = v
                    vs.append(v)
                    fails += not v.window
                    if fails * 2 > len(ids) or (best is not None and len(ids) - fails < best[0]) or                             (fails and not partial_ok):
                        break                              # cannot be a window nor beat the best so far
                n_pass = sum(1 for v in vs if v.window)
                cand_ent = (n_pass, -rank, q, vs)
                if best is None or cand_ent[:2] > best[:2]:
                    best = cand_ent
                if n_pass == len(ids):
                    break
            if best is None or best[0] * 2 < len(ids) or best[0] == 0 or (best[0] < len(ids) and not partial_ok):
                self.stats["cells_no"] += 1
                out[key] = None
                continue
            n_pass, _, q, vs = best
            m = macros[q]
            if wt.family == "cl":
                ok_ids = [ids[i] for i, v in enumerate(vs) if v.window]
                m, vs2 = self._cl_unify(wt, m, [v for v in vs if v.window], ok_ids, refs, o_by, nodes_by_o)
                if m is None:
                    self.stats["cells_cl_mixed"] += 1
                    out[key] = None
                    continue
                vs = vs2
            ks = [k for v in vs if v.window for k in v.k_strike]
            end = next((v.end for v in vs if v.window), ())
            out[key] = (rx.Entry(m, (min(ks), max(ks)) if ks else (), end), n_pass, len(ids))
            self.stats["cells_full" if n_pass == len(ids) else "cells_partial"] += 1
        return out

    def _cl_unify(self, wt, m, vs: list, ids: list, refs, o_by, nodes_by_o):
        """One continuation per hook variant for the whole cell: judge_cl finds the earliest per sample point; when the
        points differ, each point's continuation is judged (exactly: reflex.judge with it fixed) at the others - the
        first that passes at every passing point is the cell's. (macro | None, verdicts)."""
        conts = []
        for v in vs:
            if v.cont not in conts:
                conts.append(v.cont)
        if len(conts) == 1:
            return replace(m, cont=conts[0]), vs
        conts.sort(key=lambda c: tuple(-k for (_, k, _) in c))          # the latest presses first: the widest margin
        for cont in conts:
            mm = replace(m, cont=cont)
            out = []
            for (ok_, ni) in ids:
                o = o_by[ok_]
                v = rx.judge(self.W, self.ev, nodes_by_o[ok_][ni], [o], o.iid, wt, mm)
                self.stats["judged_unify"] += 1
                if not v.window:
                    out = None
                    break
                out.append(v)
            if out:
                return mm, out
        return None, vs

    def _verdict(self, mode: str, wt, ref: Ref, o, S, m, cs, screened_ok: bool):
        t0 = time.perf_counter()
        if wt.family == "ds" and not screened_ok:
            v = RV(False, "screen", (), ())
        elif wt.family == "cl":
            v = judge_cl_fast(self.W, self.ev, S, [o], o.iid, wt, m, ref, stats=self.stats, ctrl_w=self.ctrl_w)
            self.stats["judged_cl"] += 1
        elif mode == "exact":
            v = rx.judge(self.W, self.ev, S, [o], o.iid, wt, m)
            self.stats["judged"] += 1
        else:
            if (cs < 0).any():
                v = RV(False, "beyond", (), ())               # (a lane kept past Kc: the reference has no contact)
            else:
                v = refeval_ds(self.W, self.ev, ref, S, m, cs, self.full_exit)
            self.stats["refevals"] += 1
        self._tm("verdict", t0)
        return v


def _cl_macro(m: rx.Macro, vs: list):
    """A Clawline window's entry: the press part and one continuation per hook variant - the same at every passing
    sample point (else None: the points want different continuations)."""
    conts = {v.cont for v in vs}
    if len(conts) != 1:
        return None
    return replace(m, cont=vs[0].cont)


__all__ = ["Gen", "Ref", "screen_ds", "prune_nodes", "refeval_ds", "judge_cl_fast", "robust_contacts", "contacts",
           "macro_grid", "COMMITTED", "MAX_TRY", "RV"]
