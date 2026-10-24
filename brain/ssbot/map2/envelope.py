"""Map v2 L2: Hornet's reach envelope (docs/plans/forum_map_v2.md section 1 L2 with the person's refinements of
2026-10-20 / 21; stage M1). Offline / planning code only: nothing in the live bot imports it.

    from ssbot.map2 import envelope as env
    E = env.Engine()                                   # Wanderer, the Forum kit, the M0 (HERO2) calibration
    st = E.start_state(S)                              # her exact kin_jit state (estimate_state) -> one start cluster
    fw = E.forward(st, T=60, danger=boxes)             # the cluster forward pass (danger: per-frame boxes)
    fw.region(30)                                      # where she can be at frame 30: (y, x0, x1) rows
    w = fw.witness(30, x, y)                           # concrete keys to (x, y) at frame 30, re-simulated

THE CLUSTER (the person, 2026-10-21): one vertical trajectory (its exact kin_jit vertical state: the curve, its phase,
its origin height, the flags: air dash used, the umbrella / dash / attack locks, the Clawline lock) with the reachable
x as an interval set per frame. See ssbot.map2.env_jit for the pass. No snapping: two clusters merge only when their
vertical keys are bit-equal (the same vertical history up to the order of events), so the pass from one exact start is
exact; the x sets are exact for the instant run and the committed blocks and an over-approximation inside the
umbrella's inertia (the extremes are exact, interior points after a cut keep the extreme velocities).

THE RECURSIVE ELEMENT (the one-step transition table): kin_jit's frame (steps + Update) applied to a cluster under
each vertical choice of the frame; R(s, t) is the union of the clusters' x sets at frame t of the pass started at s
(the dynamic programme over t: every child is computed from its parent at t - 1 only; children equal in the vertical
key merge). The precomputed tables (build_tables) store that union per canonical start and frame as rows (y bins of
0.05 u: the exact heights inside each bin, the union x range) - the contour vertices of the region - and per end
condition (strike windows, the steady states).

Positions are her box centre (u, world units; x the collider centre, y its middle: box bottom + 1.0395).
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numba
import numpy as np

from ssbot.knowledge import kinematics as km
from ssbot.map2 import env_jit as ej

PARAMS_PATH = km.REPO / "knowledge" / "1.0.30000" / "kinematics" / "hero_wanderer_forum.json"
FLOOR_BB = 3.015           # the Forum floor (her box bottom standing)
WIDE_BEAM = 128            # T4: the witness's second beam (a target the first beam misses by > 0.01 u: the float's
#                            interior points)
COND = {"atk": ej.COND_ATK, "dslash": ej.COND_DSLASH, "claw": ej.COND_CLAW, "ground": ej.COND_GROUND,
        "run": ej.COND_RUN, "float": ej.COND_FLOAT, "air": ej.COND_AIR, "clawblk": ej.COND_CLAWBLK,
        "dashed": ej.COND_DASHED}


def load_params(hero2: bool = True) -> km.HeroParams:
    p = km.HeroParams.load(PARAMS_PATH)
    return km.hero2(p, on=True) if hero2 else p


def floor_terrain(bb: float = FLOOR_BB) -> km.Terrain2D:
    """A flat floor (the Forum's) without walls: the online pass's terrain (walls are not modelled yet)."""
    return km.Terrain2D.from_boxes([(-1.0e4, bb - 2.0, 1.0e4, bb)])


@dataclass
class Start:
    """One start cluster: lanes [2, K] (lane 0 the left extreme, lane 1 the right), the custom fields, x intervals."""
    L: np.ndarray
    cu: np.ndarray
    ivs: np.ndarray
    label: str = ""


@dataclass
class Fwd:
    """The forward pass's result (env_jit.forward's arrays) with the queries."""
    eng: "Engine"
    start: Start
    T: int
    terrain: object
    cl_off: np.ndarray
    cl_y: np.ndarray           # the cluster's height (a band: its top)
    cl_ylo: np.ndarray         # its bottom (= cl_y for an exact cluster)
    cl_vy: np.ndarray
    cl_cond: np.ndarray
    cl_mode: np.ndarray
    cl_phase: np.ndarray
    cl_iv0: np.ndarray
    cl_ivn: np.ndarray
    IV: np.ndarray
    pc_cl: np.ndarray
    pc_par: np.ndarray
    pc_cand: np.ndarray
    pc_lo: np.ndarray
    pc_hi: np.ndarray
    pc_dlo: np.ndarray
    pc_dhi: np.ndarray
    cl_key: np.ndarray
    stats: np.ndarray
    flags: np.ndarray
    seconds: float = 0.0
    _pc_by_cl: object = field(default=None, repr=False)

    # ---- per frame ----
    def frame(self, t: int) -> range:
        return range(int(self.cl_off[t]), int(self.cl_off[t + 1]))

    def count(self, t: int) -> int:
        return int(self.cl_off[t + 1] - self.cl_off[t])

    def intervals(self, g: int) -> np.ndarray:
        return self.IV[self.cl_iv0[g]:self.cl_iv0[g] + self.cl_ivn[g]]

    def region(self, t: int, cond: int = 0) -> np.ndarray:
        """[n, 4] rows (y0, y1, x0, x1): every cluster's intervals at frame t over its height range (y0 = y1 for an
        exact cluster), with all bits of `cond` set if given."""
        rows = []
        for g in self.frame(t):
            if cond and (int(self.cl_cond[g]) & cond) != cond:
                continue
            for a, b in self.intervals(g):
                rows.append((self.cl_ylo[g], self.cl_y[g], a, b))
        return np.array(rows).reshape(-1, 4)

    def contains(self, t: int, x: float, y: float, tol_x: float = 1e-6, tol_y: float = 1e-6) -> bool:
        g0, g1 = int(self.cl_off[t]), int(self.cl_off[t + 1])
        ok = np.flatnonzero((self.cl_ylo[g0:g1] - tol_y <= y) & (y <= self.cl_y[g0:g1] + tol_y))
        for i in ok:
            iv = self.intervals(g0 + int(i))
            if np.any((iv[:, 0] - tol_x <= x) & (x <= iv[:, 1] + tol_x)):
                return True
        return False

    def frame_rows(self, t: int):
        """Frame t's intervals as arrays: cluster index, x0, x1, y0, y1."""
        g0, g1 = int(self.cl_off[t]), int(self.cl_off[t + 1])
        n = self.cl_ivn[g0:g1]
        g = np.repeat(np.arange(g0, g1), n)
        i0 = self.cl_iv0[g0] if g1 > g0 else 0
        iv = self.IV[i0:i0 + int(n.sum())]
        return g, iv[:, 0], iv[:, 1], self.cl_ylo[g], self.cl_y[g]

    def nearest(self, t: int, x: float, y: float) -> tuple[float, int]:
        """The smallest distance from (x, y) to the frame's rows and that cluster (the escape size of a point)."""
        g, x0, x1, y0, y1 = self.frame_rows(t)
        if not len(g):
            return np.inf, -1
        dx = np.maximum(np.maximum(x0 - x, x - x1), 0.0)
        dy = np.maximum(np.maximum(y0 - y, y - y1), 0.0)
        dd = np.hypot(dx, dy)
        k = int(np.argmin(dd))
        return float(dd[k]), int(g[k])

    def exact_until(self) -> int:
        """The last frame whose clusters are all exact (before the far layer's bands)."""
        on = np.flatnonzero(self.stats[:, 6] > 0)
        return int(on[0]) - 1 if len(on) else self.T

    # ---- the witness ----
    def _pieces(self):
        if self._pc_by_cl is None:
            order = np.argsort(self.pc_cl, kind="stable")
            starts = np.searchsorted(self.pc_cl[order], np.arange(len(self.cl_y) + 1))
            self._pc_by_cl = (order, starts)
        return self._pc_by_cl

    def chain(self, g: int, x: float, tol: float = 1e-6) -> tuple[list, list, list] | None:
        """Backtrack from cluster g (at its frame) and x in it: per frame back to the start, the cluster, its
        candidate code (the vertical choice of that frame) and an x on the path. Returns (clusters, cands, xs) in
        time order (cands[0] unused), or None if x is not in g."""
        order, starts = self._pieces()
        t = int(np.searchsorted(self.cl_off, g, side="right") - 1)
        cls, cands, xs, ds = [g], [], [x], []
        while t > 0:
            ps = order[starts[g]:starts[g + 1]]
            if not len(ps):
                return None
            lo, hi = self.pc_lo[ps], self.pc_hi[ps]
            inside = np.flatnonzero((lo - tol <= x) & (x <= hi + tol))
            if not len(inside):
                # nearest piece (a float rounding of the union)
                d = np.maximum(lo - x, x - hi)
                k = int(np.argmin(d))
                if d[k] > 1e-3:
                    return None
            else:
                k = int(inside[0])
            p = ps[k]
            par = int(self.pc_par[p])
            dlo, dhi = self.pc_dlo[p], self.pc_dhi[p]
            # x at t - 1: in [x - dhi, x - dlo] and in the parent's intervals; prefer the no-key displacement
            a, b = x - dhi, x - dlo
            want = x - 0.5 * (dlo + dhi)
            best, bx = np.inf, None
            for ia, ib in self.intervals(par):
                lo2, hi2 = max(a, ia), min(b, ib)
                if lo2 > hi2 + 1e-9:
                    continue
                c = min(max(want, lo2), hi2)
                if abs(c - want) < best:
                    best, bx = abs(c - want), c
            if bx is None:
                # tolerance: the closest point of the parent's intervals
                iv = self.intervals(par)
                cand_x = np.clip(want, iv[:, 0], iv[:, 1])
                bx = float(cand_x[np.argmin(np.abs(cand_x - want))])
            cands.append(int(self.pc_cand[p]))
            ds.append((float(dlo), float(dhi)))
            g, x, t = par, bx, t - 1
            cls.append(g)
            xs.append(x)
        cls.reverse(), cands.reverse(), xs.reverse(), ds.reverse()
        self._last_ds = ds
        return cls, [0] + cands, xs

    def witness(self, t: int, x: float, y: float | None = None, cond: int = 0, tol_y: float = 1e-6,
                look: int = 3, beam: int = 24) -> dict | None:
        """Concrete keys that bring her to x (at height y, or any height when None; with the end condition bits
        `cond`) at frame t: the cluster chain backtracked to the start (the vertical choices per frame and the
        tube of x from which the target stays reachable), then the horizontal keys by a beam search in that tube
        (beam > 0; else the greedy tracker with `look` frames), re-simulated with the reference model (kin_jit + the
        Clawline). Returns masks, the planned x path, the re-simulated centres and the miss at t; None when no
        cluster holds the point."""
        best = None
        for g in self.frame(t):
            if y is not None and abs(self.cl_y[g] - y) > tol_y:
                continue
            if cond and (int(self.cl_cond[g]) & cond) != cond:
                continue
            iv = self.intervals(g)
            dx = float(np.min(np.maximum(np.maximum(iv[:, 0] - x, x - iv[:, 1]), 0.0)))
            if best is None or dx < best[0]:
                best = (dx, g)
        if best is None or best[0] > 1e-6:
            return None
        g = best[1]
        ch = self.chain(g, x)
        if ch is None:
            return None
        cls, cands, xs = ch
        vm = np.array(cands[1:], dtype=np.int64)
        xp = np.array(xs, dtype=np.float64)
        # the tube: per frame the x from which the target is reachable along this vertical history (the chain's
        # lane displacements summed to the end: exact for the instant run, wider inside the umbrella's inertia)
        d = np.array(self._last_ds).reshape(-1, 2)
        clo = np.concatenate([np.cumsum(d[::-1, 0])[::-1], [0.0]])
        chi = np.concatenate([np.cumsum(d[::-1, 1])[::-1], [0.0]])
        tlo, thi = x - chi, x - clo
        masks = np.zeros(t, dtype=np.int64)
        oxy = np.zeros((t + 1, 2))
        S0 = self.start.L[1].copy()
        dx0 = xp[0] - S0[km.PX]
        S0[km.PX] += dx0
        S0[km.QX] += dx0
        S0[km.SX] += dx0
        ej.track(S0, self.start.cu.copy(), vm, tlo, thi, self.eng.udt, self.eng.P, self.terrain, look, masks, oxy)
        if beam > 0 and abs(oxy[t, 0] - x) > 1e-3:
            m2 = np.zeros(t, dtype=np.int64)
            o2 = np.zeros((t + 1, 2))
            ej.track_beam(S0, self.start.cu.copy(), vm, tlo, thi, self.eng.udt, self.eng.P, self.terrain, beam, m2,
                          o2)
            if abs(o2[t, 0] - x) < abs(oxy[t, 0] - x):
                masks, oxy = m2, o2
            # T4 (the verifiers' finding: interior points of the float's clusters missed by 0.1 - 0.65 u that a dense
            # left / none / right search reaches): a wider beam once the first one misses
            if beam < WIDE_BEAM and abs(oxy[t, 0] - x) > 0.01:
                m3 = np.zeros(t, dtype=np.int64)
                o3 = np.zeros((t + 1, 2))
                ej.track_beam(S0, self.start.cu.copy(), vm, tlo, thi, self.eng.udt, self.eng.P, self.terrain,
                              WIDE_BEAM, m3, o3)
                if abs(o3[t, 0] - x) < abs(oxy[t, 0] - x):
                    masks, oxy = m3, o3
        # T4: a CB_JH frame (jump held without a press) is reached in the game by a jump pressed where it is inert -
        # in an attack's recovery: the trackers hold it by setting her previous keys, the keys they return press it
        # there (the umbrella opens) - the press written in (an attack 1 - 7 frames before, the jump pressed in its
        # recovery and held), each kept only when the keys reproduce the tracked path
        jh = np.flatnonzero((vm & ej.CB_JH) != 0)
        hidden = []
        if len(jh):
            masks, hidden = self._hidden_press(S0, masks, oxy, jh)
        # the keys rolled as they are (the reference model, no hidden state): the true miss
        xy = self._roll(S0, masks)
        dev = float(np.max(np.abs(xy - oxy))) if len(xy) else 0.0
        return {"cluster": g, "masks": masks, "vmask": vm, "xpath": xp, "xy": xy,
                "miss_x": float(xy[t, 0] - x), "miss_y": float(xy[t, 1] - self.cl_y[g]),
                "y": float(self.cl_y[g]), "clusters": cls, "path_dev": dev, "hidden": hidden}

    def _roll(self, S0: np.ndarray, masks: np.ndarray) -> np.ndarray:
        """Her centres along masks from S0 (the reference model: kin_jit + the Clawline, no hidden state)."""
        n = len(masks)
        xy = np.zeros((n + 1, 2))
        md = np.zeros(n + 1, dtype=np.int64)
        ej.ref_rollout(S0.copy(), self.start.cu.copy(), np.asarray(masks, np.int64), self.eng.udt, self.eng.P,
                       self.terrain, xy, md)
        return xy

    def _hidden_press(self, S0: np.ndarray, masks: np.ndarray, oxy: np.ndarray, jh: np.ndarray):
        """T4: the keys for the chain's CB_JH frames (jump held without a press at index i): an attack at i - k - 1
        and the jump pressed at i - k (inert in the attack's recovery: the umbrella cannot open) held through i, k
        = 0 .. 6 (a dash pressed with it held needs the attack's recovery over by i: k >= 5); a variant is kept when
        the keys rolled as they are reproduce the tracked path (every frame within 1e-6 u). Returns (masks,
        [(index, k) or (index, None) when none fits])."""
        m = np.asarray(masks, np.int64).copy()
        done = []
        jl = [int(v) for v in jh]
        for q, i in enumerate(jl):
            # (checked up to the next CB_JH frame - its press not written yet - or the end: the dash pressed with it
            # shows in the steps after its frame)
            end = jl[q + 1] if q + 1 < len(jl) else len(m)
            ok = None
            for k in range(0, 7):
                f1, f0 = i - k, i - k - 1
                if f0 < 0:
                    break
                mm = m.copy()
                if (int(mm[f0]) & (km.B_JUMP | km.B_ATTACK)) != 0:
                    continue                       # (a frame that already presses: not this variant)
                mm[f0] |= km.B_ATTACK
                mm[f1:i + 1] |= km.B_JUMP
                xy = self._roll(S0, mm[:end])
                if np.max(np.abs(xy - oxy[:end + 1])) <= 1e-6:
                    ok = k
                    m = mm
                    break
            done.append((i, ok))
        return m, done


class Engine:
    """The envelope engine for one hero kit (default: Wanderer with the Forum loadout, the M0 / HERO2 model)."""

    def __init__(self, params: km.HeroParams | None = None, claw: bool = True, tf8: bool = True):
        self.params = params or load_params()
        self.P = self.params.vector()
        self.udt = float(np.float32(self.params.frame_time))
        self.claw = claw
        self.tf8 = tf8
        self.hh = 0.5 * (self.params.head - self.params.foot)
        self.empty_tt = km.Terrain2D.empty().packed()

    # ---- starts ----
    def start_state(self, S: np.ndarray, x0: float | None = None, x1: float | None = None, cu=None,
                    label: str = "") -> Start:
        """A start cluster from one exact kin_jit state (estimate_state / initial_state): both lanes = S, the x
        interval [x0, x1] (default her x)."""
        S = np.asarray(S, dtype=np.float64).reshape(-1)
        L = np.stack([S.copy(), S.copy()])
        x = S[km.PX]
        a = x if x0 is None else x0
        b = x if x1 is None else x1
        for ln, v in ((0, a), (1, b)):     # shifted as a whole: the previous step's / drawn x keep their offsets
            dx = v - x                      # (a ground sprint's start translates from the drawn position)
            L[ln, km.PX] += dx
            L[ln, km.QX] += dx
            L[ln, km.SX] += dx
        cu = np.array([-1.0, 0, 0, 0, 0, 0, 0]) if cu is None else np.asarray(cu, dtype=np.float64)
        return Start(L, cu, np.array([[a, b]]), label)

    # ---- the pass ----
    def forward(self, st: Start, T: int, danger=None, terrain=None, claw: bool | None = None,
                tf8: bool | None = None, opts: int = 0, max_events: int = 0, band_t: int = -1, band_n: int = 0,
                qy: float = 0.25, qv: float = 1.2, cap_frame: int = 20000, cap_pc: int = 4_000_000,
                cap_iv: int = 4_000_000, cap_cl: int = 2_000_000, keep_keys: bool = False, par: int = 0,
                stop: np.ndarray | None = None) -> Fwd | None:
        """The cluster forward pass over T frames. danger: None, or a list of T + 1 arrays [n, 4] of boxes (x0, y0,
        x1, y1) in her centre's space (already grown by her hurtbox), per frame; terrain: None (free space: the
        tables' infinite height) or a Terrain2D / packed array. The far layer (bands, an over-approximation): from
        frame band_t (>= 0), or from the first frame with more than band_n clusters (> 0); bins qy (u) / qv (u/s).
        Exact (the default) otherwise. stop (T4): an int64 [1] another thread may set non-zero - the pass is then
        abandoned at its next frame and None returned."""
        if danger is None:
            boxes = np.zeros((0, 4))
            off = np.zeros(T + 2, dtype=np.int64)
        else:
            parts = [np.asarray(danger[t], dtype=np.float64).reshape(-1, 4) if t < len(danger) and danger[t] is not None
                     else np.zeros((0, 4)) for t in range(T + 1)]
            off = np.zeros(T + 2, dtype=np.int64)
            off[1:] = np.cumsum([len(p) for p in parts])
            boxes = np.concatenate(parts) if off[-1] else np.zeros((0, 4))
        if terrain is None:
            TT = self.empty_tt
        elif isinstance(terrain, np.ndarray):
            TT = terrain
        else:
            TT = terrain.packed()
        claw = self.claw if claw is None else claw
        tf8 = self.tf8 if tf8 is None else tf8
        stp = np.zeros(1, dtype=np.int64) if stop is None else stop
        while True:
            t0 = time.perf_counter()
            o = opts | (ej.OPT_CLAW if claw else 0) | (ej.OPT_TF8 if (claw and tf8) else 0) | (min(max_events, 15) << 8)
            if par > 1 and band_t < 0 and band_n <= 0:
                # M4b: each frame's per-parent work on par threads, merged in the parents' order (the same result)
                out = ej.forward_par(st.L, st.cu, st.ivs, T, self.udt, self.P, TT, boxes, off, o, cap_frame, cap_pc,
                                     cap_iv, cap_cl, keep_keys, max(par, numba.config.NUMBA_NUM_THREADS), 256, stp)
            else:
                out = ej.forward(st.L, st.cu, st.ivs, T, self.udt, self.P, TT, boxes, off, o, cap_frame, cap_pc,
                                 cap_iv, cap_cl, keep_keys, band_t, band_n, qy, qv, stp)
            sec = time.perf_counter() - t0
            if stp[0] != 0:
                return None
            fl = out[-1]
            if not fl.any():
                break
            cap_frame *= 2 if fl[0] else 1
            cap_pc *= 2 if fl[1] else 1
            cap_iv *= 2 if fl[2] else 1
            cap_cl *= 2 if fl[3] else 1
        # (M4b: the outputs are slices of the pass's preallocated buffers - cap_cl / cap_pc / cap_iv rows, ~0.4 GB -
        # copied, so a kept pass holds only its rows: the search keeps tens of passes and grew to 8 - 48 GB)
        out = tuple(a.copy() for a in out)
        return Fwd(self, st, T, TT, *out, seconds=sec)

    # ---- the reference rollouts ----
    def rollouts(self, S0s: np.ndarray, cu0s: np.ndarray, masks: np.ndarray, terrain=None):
        """[n, T + 1, 2] centres and [n, T + 1] modes of n key sequences (B_CLAW = env_jit.B_CLAW for the Clawline)
        from n states (kin_jit + the Clawline block + the residual drift)."""
        TT = self.empty_tt if terrain is None else (terrain if isinstance(terrain, np.ndarray) else terrain.packed())
        return ej.ref_many(np.ascontiguousarray(S0s), np.ascontiguousarray(cu0s),
                           np.ascontiguousarray(masks, dtype=np.int64), self.udt, self.P, TT)


# ---- canonical start states (the tables' keys) -------------------------------------------------------------------
# Phases are counted in frames from the canonical event; the physics phase (alpha, the 50 Hz steps' position in the
# 60 fps frames) is the table's phase class: alpha_c = c / 6 (c = 0 .. 5).
AIR_Y = 20.0


def _roll_final(params, S0, masks, events=None, terrain=None) -> np.ndarray:
    masks = np.asarray(masks, dtype=np.int64)[None]
    ev = None if events is None else np.asarray(events, dtype=np.int64)[None]
    r = km.rollout(S0, masks, params, terrain, events=ev)
    return r.final[:, 0].copy()


def canonical(params: km.HeroParams, kind: str, phase: int = 0, alpha_c: int = 0, var: str = "",
              dashed: bool = False) -> tuple[np.ndarray, km.Terrain2D | None]:
    """A canonical start's kin_jit state (x 0) and its terrain (None: free space, the floor for the ground):
    A1 at rest (vy 0, no keys) + `phase` frames of free fall; A2 the bounce `phase` frames after the contact (var
    'claw': the default bounce, 4.09 u, as the hooked Clawline's control; 'pogo': a down slash pressed 3 frames
    before the contact, restarted at its Bounce event, 3.74 u; the air dash restored); A3 the umbrella's Float Idle
    `phase` frames after its start with the key var 'L' / 'N' / 'R' held from the open (the vx class); A4 the
    terminal fall (A1 + 40 frames); G walk standing on the floor; G run the ground sprint at its steady 17.5 u/s
    (var 'L' / 'R'). dashed: the air dash used."""
    a = alpha_c / 6.0
    if kind in ("A1", "A4"):
        S = km.initial_state(params, 0.0, AIR_Y, ground=False, alpha=a)
        n = phase if kind == "A1" else 40
        if n:
            S = _roll_final(params, S, np.zeros(n))
        terr = None
    elif kind == "A2":
        S = km.initial_state(params, 0.0, AIR_Y, ground=False, alpha=a)
        if var == "pogo":
            m = np.zeros(3 + phase, dtype=np.int64)
            m[0] = km.B_ATTACK | km.B_DOWN
            ev = np.zeros(3 + phase, dtype=np.int64)
            ev[2] = km.EV_POGO
        else:
            m = np.zeros(1 + phase, dtype=np.int64)
            ev = np.zeros(1 + phase, dtype=np.int64)
            ev[0] = km.EV_POGO
        S = _roll_final(params, S, m, ev)
        S[km.AIRDASHED] = 0.0          # the pogo restores the air dash (M0: 28 / 28)
        S[km.INV_T] = 0.0              # its i-frames (against enemies) do not move her
        terr = None
    elif kind == "A3":
        S0 = km.initial_state(params, 0.0, AIR_Y, ground=False, alpha=a)
        h = {"L": km.B_LEFT, "R": km.B_RIGHT}.get(var, 0)
        # the open: jump pressed, held (with the key) until Float Idle, then `phase` frames more
        m = []
        for _ in range(60):
            m.append(km.B_JUMP | h)
            x = _roll_final(params, S0, m)
            if x[km.MODE] == km.M_GLIDE and x[km.PHASE] == 2.0:
                break
        m += [km.B_JUMP | h] * phase
        S = _roll_final(params, S0, m)
        terr = None
    elif kind == "G":
        terr = floor_terrain()
        S = km.initial_state(params, 0.0, FLOOR_BB + params.foot, ground=True, alpha=a)
        if var in ("L", "R"):
            h = km.B_LEFT if var == "L" else km.B_RIGHT
            S = _roll_final(params, S, [km.B_DASH | h] * 30, terrain=terr)
    else:
        raise ValueError(kind)
    if dashed and kind != "G":
        S[km.AIRDASHED] = 1.0
    return S, terr


def table_keys(full: bool = False) -> list[tuple]:
    """The canonical starts of the stored tables: (kind, phase, var, dashed). full: every phase (A1 0 .. 30, A2 0 ..
    22, A3 0 .. 58 x 3); else a representative subset (every 5th / 10th phase)."""
    st = 1 if full else 5
    keys = []
    for d in (False, True):
        keys += [("A1", k, "", d) for k in range(0, 31, st)]
        if not d:
            keys += [("A2", k, v, d) for v in ("claw", "pogo") for k in range(0, 23, st)]
        keys += [("A3", k, v, d) for v in ("L", "N", "R") for k in range(0, 60, st * 2)]
        keys += [("A4", 0, "", d)]
    keys += [("G", 0, "", False), ("G", 0, "L", False), ("G", 0, "R", False)]
    return keys


def key_name(k: tuple, alpha_c: int = 0) -> str:
    kind, ph, var, d = k
    return f"{kind}{var}@{ph}{'d' if d else ''}/a{alpha_c}"


# ---- the stored tables: per start, frame and end condition the union region as rows of 0.05 u ---------------------
TABLE_CONDS = {"all": 0, "atk": ej.COND_ATK, "dslash": ej.COND_DSLASH, "claw": ej.COND_CLAW,
               "ground": ej.COND_GROUND, "float": ej.COND_FLOAT}
QROW = 0.05


def raster(rows: np.ndarray, x0: float = 0.0, y0: float = 0.0, q: float = QROW) -> np.ndarray:
    """Rows (y0, y1, x0, x1) relative to (x0, y0) -> the conservative raster: [n, 3] (bin, xa, xb), per y bin of
    q (bin j covers [j q, (j + 1) q)) the union of the x intervals of every row touching it, sorted."""
    if not len(rows):
        return np.zeros((0, 3))
    ya = np.floor((rows[:, 0] - y0) / q).astype(np.int64)
    yb = np.floor((rows[:, 1] - y0) / q).astype(np.int64)
    n = yb - ya + 1
    b = np.repeat(ya, n) + (np.arange(int(n.sum())) - np.repeat(np.cumsum(n) - n, n))
    xa = np.repeat(rows[:, 2] - x0, n)
    xb = np.repeat(rows[:, 3] - x0, n)
    return ej.union_rows(b, xa, xb)


def contour_vertices(r: np.ndarray) -> int:
    """The vertex count of the raster's outline (a rectilinear polygon set: two corners per interval end that moves
    between consecutive bins, plus the caps) - the size of the contour storage."""
    if not len(r):
        return 0
    v = 0
    prev = None
    for bj in np.unique(r[:, 0]):
        cur = r[r[:, 0] == bj][:, 1:]
        if prev is None or len(prev) != len(cur):
            v += 2 * len(cur) + (2 * len(prev) if prev is not None else 0)
        else:
            v += 2 * int(np.sum(np.abs(prev[:, 0] - cur[:, 0]) > 1e-9))
            v += 2 * int(np.sum(np.abs(prev[:, 1] - cur[:, 1]) > 1e-9))
        prev = cur
    return v + 2 * len(prev)


def contours(r: np.ndarray, q: float = QROW) -> list[np.ndarray]:
    """The raster rows (bin, xa, xb) as outline polygons (vertices counter-clockwise, collinear points dropped): one per
    run of consecutive bins whose intervals overlap; a bin holding several intervals of one run contributes its hull
    (conservative). The contour-vertex form of a table region (for display and polygon tests)."""
    if not len(r):
        return []
    bins = np.unique(r[:, 0]).astype(np.int64)
    rows = {int(b): r[r[:, 0] == b][:, 1:] for b in bins}
    # runs: overlapping intervals of consecutive bins
    comp, polys = {}, []
    runs = []
    for b in bins:
        for k, (a, c) in enumerate(rows[int(b)]):
            joined = None
            for ri, run in enumerate(runs):
                lb, (la, lc) = run[-1][0], run[-1][1]
                if lb == b - 1 and a <= lc + 1e-9 and c >= la - 1e-9:
                    if joined is None:
                        run.append((int(b), (a, c)))
                        joined = ri
            if joined is None:
                runs.append([(int(b), (a, c))])
    for run in runs:
        hull = {}
        for b, (a, c) in run:
            lo, hi = hull.get(b, (a, c))
            hull[b] = (min(lo, a), max(hi, c))
        bs = sorted(hull)
        right = []
        for b in bs:
            right += [(hull[b][1], b * q), (hull[b][1], (b + 1) * q)]
        left = []
        for b in reversed(bs):
            left += [(hull[b][0], (b + 1) * q), (hull[b][0], b * q)]
        pts = np.array(right + left)
        keep = [i for i in range(len(pts))
                if not (np.allclose(pts[i - 1], pts[i]) or
                        abs((pts[i][0] - pts[i - 1][0]) * (pts[(i + 1) % len(pts)][1] - pts[i - 1][1]) -
                            (pts[i][1] - pts[i - 1][1]) * (pts[(i + 1) % len(pts)][0] - pts[i - 1][0])) < 1e-12)]
        polys.append(pts[keep])
    return polys


def build_table(eng: "Engine", S: np.ndarray, terr, T: int, band_n: int = 0, max_events: int = 0) -> dict:
    """One table: the forward pass from S over T frames (the event limit max_events: the segment family; the far
    layer's bands from band_n clusters), per frame and end condition the raster relative to her start position (x,
    centre y). Returns {cond: [T + 1 arrays (bin, xa, xb)]}, with the counts and the time."""
    st = eng.start_state(S)
    fw = eng.forward(st, T, terrain=terr, band_n=band_n, max_events=max_events)
    xs, ys = float(S[km.PX]), float(S[km.PY] + eng.hh)
    out = {c: [] for c in TABLE_CONDS}
    for t in range(T + 1):
        g, x0, x1, y0, y1 = fw.frame_rows(t)
        cond = fw.cl_cond[g]
        for c, bits in TABLE_CONDS.items():
            sel = np.ones(len(g), bool) if not bits else (cond & bits) == bits
            rows = np.stack([y0[sel], y1[sel], x0[sel], x1[sel]], axis=1)
            out[c].append(raster(rows, xs, ys))
    out["_counts"] = [fw.count(t) for t in range(T + 1)]
    out["_seconds"] = fw.seconds
    out["_exact_until"] = fw.exact_until()
    return out


def save_tables(path, tables: dict, meta: dict) -> None:
    """tables {key name: build_table output} -> one npz: per key / cond the rows of all frames concatenated (bin as
    int32, xa / xb as float32 rounded outward) with frame offsets."""
    import json
    arrs = {"_meta": np.array(json.dumps(meta, default=str))}
    for k, tb in tables.items():
        for c in TABLE_CONDS:
            fr = tb[c]
            off = np.zeros(len(fr) + 1, dtype=np.int64)
            off[1:] = np.cumsum([len(r) for r in fr])
            cat = np.concatenate([r for r in fr if len(r)] or [np.zeros((0, 3))])
            arrs[f"{k}|{c}|off"] = off
            arrs[f"{k}|{c}|bin"] = cat[:, 0].astype(np.int32)
            x = np.empty((len(cat), 2), dtype=np.float32)
            x[:, 0] = np.nextafter(cat[:, 1].astype(np.float32), np.float32(-np.inf))
            x[:, 1] = np.nextafter(cat[:, 2].astype(np.float32), np.float32(np.inf))
            arrs[f"{k}|{c}|x"] = x
        arrs[f"{k}|counts"] = np.asarray(tb["_counts"], dtype=np.int64)
    np.savez_compressed(path, **arrs)


def steps_pattern(alpha: float, T: int, dt: float, fdt: float) -> list:
    """The physics steps of each of T frames from phase alpha (the tables' chain's own arithmetic)."""
    a, out = float(alpha), []
    for _ in range(T):
        a_ = a + dt / fdt
        s = math.floor(a_ + 1e-9)
        a = min(max(a_ - s, 0.0), 1.0)
        out.append(s)
    return out


class Tables:
    """The stored tables: lookup by (key name, cond, frame) -> (bin, xa, xb) rows relative to her start (translate
    to her position); the backward (meet in the middle) region is the point reflection."""

    def __init__(self, path):
        import json
        self.z = np.load(path)
        self.meta = json.loads(str(self.z["_meta"]))
        self.q = float(self.meta.get("q", QROW))

    def rows(self, key: str, cond: str, t: int) -> np.ndarray:
        off = self.z[f"{key}|{cond}|off"]
        a, b = int(off[t]), int(off[t + 1])
        return np.column_stack([self.z[f"{key}|{cond}|bin"][a:b], self.z[f"{key}|{cond}|x"][a:b]])

    def contains(self, key: str, cond: str, t: int, dx: float, dy: float, tol: float = 1e-9) -> bool:
        """Whether the offset (dx, dy) from the start (centre to centre) is in the table's region at frame t (T4:
        within tol - a height on a bin boundary, dy = -1.8e-15 for 0, fell into the bin below)."""
        r = self.rows(key, cond, t)
        b0, b1 = np.floor((dy - tol) / self.q), np.floor((dy + tol) / self.q)
        s = r[(r[:, 0] >= b0) & (r[:, 0] <= b1)]
        return bool(np.any((s[:, 1] - tol <= dx) & (dx <= s[:, 2] + tol)))

    def valid_until(self, key: str, S: np.ndarray, P: np.ndarray, floor_top: float | None = None,
                    ceil_bot: float | None = None, clear: float = 2.5, clear_up: float = 1.0) -> int:
        """T4 (the verifiers' finding: the flattened layer is no upper bound for the states it is keyed by): the last
        frame up to which table `key` bounds her reach from her state S - -1 when S's physics phase gives another
        step pattern over the table's frames than the build's (each phase class was built at its exact alpha c / 6:
        a start a fraction of a step later in the class has other heights), and an air table (built in free space)
        only before its rows come within `clear` of the floor (her box bottom: a landing, the umbrella's ground ray)
        or `clear_up` of the ceiling. The flat layer is not used by the search."""
        meta = self.meta
        a0 = meta.get("alpha", {}).get(key)
        T = int(meta.get("T", 0))
        if a0 is None or "dt" not in meta:
            return -1                                      # (a file from before T4: no phase recorded)
        dt, fdt = float(meta["dt"]), float(meta["fdt"])
        if steps_pattern(float(S[km.ALPHA]), T, dt, fdt) != steps_pattern(float(a0), T, dt, fdt):
            return -1
        if not meta.get("free", {}).get(key, False) or (floor_top is None and ceil_bot is None):
            return T
        cy = float(S[km.PY]) + 0.5 * (P[km.P_HEAD] - P[km.P_FOOT])
        hh = 0.5 * (P[km.P_HEAD] + P[km.P_FOOT])          # her box's half height (centre to bottom / top)
        for t in range(T + 1):
            r = self.rows(key, "all", t)
            if not len(r):
                continue
            ylo = cy + float(r[:, 0].min()) * self.q - hh
            yhi = cy + (float(r[:, 0].max()) + 1.0) * self.q + hh
            if (floor_top is not None and ylo - floor_top < clear) or (ceil_bot is not None and ceil_bot - yhi < clear_up):
                return t - 1
        return T

    def backward(self, key: str, cond: str, t: int) -> np.ndarray:
        """Meet in the middle: the offsets (start - goal) from which the end condition `cond` is reachable at frame
        t from state `key`: the point reflection of the forward region, rows (y0, y1, x0, x1)."""
        r = self.rows(key, cond, t)
        return np.column_stack([-(r[:, 0] + 1) * self.q, -r[:, 0] * self.q, -r[:, 2], -r[:, 1]])

    def meet(self, key: str, cond: str, t: int, start_xy, goal_xy) -> bool:
        """Is the goal (with the end condition) reachable at frame t from a start in state `key` at start_xy? The
        same as goal - start in the forward region (start in the goal's backward region)."""
        return self.contains(key, cond, t, goal_xy[0] - start_xy[0], goal_xy[1] - start_xy[1])
