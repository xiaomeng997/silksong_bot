"""L1 planner (DESIGN §3.5.4; M2 W4): every frame, roll every candidate out through the kinematics' timing lanes and
choose lexicographically: not Hz > not Hz_soft > not U > S = 0 > V > min P > max J; FORCED_RISK when no allowed
candidate has S = 0.

    planner = Planner(params, terrain)
    r = planner.tick(ws, start, hold, prefix, forecast, prefs, ctx)    # r.mask: the commanded mask for the next free
                                                                       # frame; r.S, r.forced_risk for the supervisor

Inputs. `start` is the hero's kinematic state at the WorldState's frame f (StateTracker in the glue: the planner never
reads oracle fields); `prefix` the commanded masks already sent for frames f+1 .. f+P (P = 1 with the harness's
2-frame lead; 1 + k on the simulated final path with k frames of observation delay), so the decision is for frame
f+P+1 and the rollout covers the prefix too (§3.5.4 `state_at(now + L)` on the executed command stream); `hold` the
oracle HoldFilter state at f (STATE act.hf, exact), which the compiled hold filter (combat.holdfilter) continues.

Per candidate (candidates.build: 25 first primitives x 18 continuations = 450, plus the previous plan carried on, plus
the Bind macro when the tactics want it, over a longer horizon):
  rollout   kinematics.rollout(variants="bounds"): the 9 timing lanes' per-frame hull (`bound`), the support form of
            the M2 kinematics acceptance; the nominal lane scores.
  S         a hull box of any frame 1..P+T overlaps a support tube (Forecast.occupied: point test of the box centre on
            templates dilated by the hero hurtbox + the forecaster's margin; a hull wider than that is tested at a grid
            of up to 2 x 2 points, wider still counts as contact). Frames invulnerable in every lane (flags_all
            F_INVULN: hit i-frames, the recoil) are skipped while every source in support is i-frame blocked (ENEMY:
            all of the Bell Beast's).
  Hz        safety_filter.hazard_flags on knockback.knockback_hull (computed only when hazards or soft gates exist).
  U         safety_filter.unpausable: a possible killing blow outside I3.
  V         at least 2 candidates with the same first primitive have S = 0 and no Hz (the committed part keeps two
            ways on); the carried plan counts its own S.
  P         only when no candidate has S = 0 (with S = 0, P is 0: the probability tubes lie inside the support):
            Forecast.prob over the nominal lane.
  J         playbook weights: predicted nail hits on the boss's nominal hurtbox (Hunter slash, up slash and down
            spike boxes from docs/facts/1.0.30000/crests.json P17, active 6 frames from the attack's start), Silkspear
            hits x 3, wasted attacks, jump presses, the end position's distance to the tactics' stance, its future
            support coverage (the tactics' risk map: the terminal value), facing the boss, ending on the floor, and
            a bonus for carrying on the previous plan (hysteresis).
Cost (13900K, 4 threads): see tests/test_planner.py and the stage-A numbers in the M2 report.
"""
import math
import time
from dataclasses import dataclass, field

import numba
import numpy as np

from ssbot.combat import candidates as cmod
from ssbot.combat.forecast import Forecast
from ssbot.combat.holdfilter import hold_filter_jit
from ssbot.combat.safety_filter import REASONS, FilterContext, hazard_flags, unpausable, veto
from ssbot.combat.tactics.modes import TacticPrefs
from ssbot.core.primitives import Prim
from ssbot.core.worldstate import WorldState
from ssbot.knowledge import kinematics as kin
from ssbot.knowledge.knockback import knockback_hull
from ssbot.knowledge.kinematics import (B_ATTACK, B_BIND, B_JUMP, B_LEFT, B_QUICKCAST, B_RIGHT, B_UP, F_ATTACKING,
                                        F_GROUND, F_INVULN, M_CAST, M_DS_ANTIC, M_DS_SPIKE, HeroParams, HoldState,
                                        Terrain2D)

# Hunter attack boxes relative to the hurtbox centre in the facing frame (+x forward), crests.json P17 clash_tink
# polygons (captured facing left): side x [-0.12, 2.81] y [-0.62, 1.52]; up x [-1.23, 0.85] y [-0.04, 3.33];
# down spike x [-0.69, 1.41] y [-1.96, 0.32]. Silkspear: a forward band (scoring only).
SIDE = (-0.12, 2.81, -0.62, 1.52)
UP = (-1.23, 0.85, -0.04, 3.33)
DOWN = (-0.69, 1.41, -1.96, 0.32)
SPEAR = (0.3, 11.0, -0.8, 0.8)
SPEAR_DELAY_F = 16             # Silkspear antic 0.26 s before the needle flies
ACTIVE_F = 6                   # frames an attack box counts from its start (scoring)
NO_CONTROL_MODES = (kin.M_HURT_FREEZE, kin.M_HURT_RECOIL, kin.M_CAST, kin.M_BIND, kin.M_LOCKED)


@dataclass
class PlannerConfig:
    T: int = 48
    T_bind: int = 100
    threads: int = 4
    variants: str = "bounds"
    max_points: int = 2        # grid points per axis for a hull wider than one point covers


@dataclass
class PlanResult:
    mask: int
    idx: int
    name: str
    S: int
    forced_risk: bool
    P: float = 0.0
    J: float = 0.0
    V: bool = True
    Hz: bool = False
    U: bool = False
    n: int = 0
    n_allowed: int = 0
    n_safe: int = 0
    cmd: np.ndarray = field(default_factory=lambda: np.zeros(0, np.int64))
    path: np.ndarray | None = None            # chosen candidate's nominal box per frame [T1, 4]
    hull: np.ndarray | None = None
    t_ms: dict = field(default_factory=dict)
    alternatives: list = field(default_factory=list)
    vetoes: dict = field(default_factory=dict)
    hits: float = 0.0


class Planner:
    def __init__(self, params: HeroParams, terrain: Terrain2D, cfg: PlannerConfig | None = None):
        self.params = params
        self.terrain = terrain
        self.cfg = cfg or PlannerConfig()
        self.cands = cmod.build(self.cfg.T)
        self.cands_nc = cmod.no_control(self.cands)
        self.bind = cmod.bind_macro(self.cfg.T_bind)
        self.reset()

    def reset(self) -> None:
        self.prev_cmd: np.ndarray | None = None
        self.prev_name = ""
        self.ticks = 0

    # ---- S -----------------------------------------------------------------------------------------------------------

    def _contacts(self, f: Forecast, bound: np.ndarray, tk: np.ndarray, skip: np.ndarray) -> np.ndarray:
        """[N, T1] contact of the lanes' hull with the support, hull wider than a point covers: grid points."""
        hx, hy = f.fc.half
        x0, y0, x1, y1 = bound[..., 0], bound[..., 1], bound[..., 2], bound[..., 3]
        cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
        occ = f.occupied(cx, cy, tk)
        w, h = x1 - x0, y1 - y0
        nx = np.ceil(w / (2 * hx) - 1e-9).astype(np.int64)
        ny = np.ceil(h / (2 * hy) - 1e-9).astype(np.int64)
        wide = ((nx > 1) | (ny > 1)) & ~skip
        if wide.any():
            mp = self.cfg.max_points
            occ |= wide & ((nx > mp) | (ny > mp))
            rows = np.flatnonzero(wide.any(axis=1))
            px, py = [], []
            for i in range(mp):
                for j in range(mp):
                    fx = np.where(nx[rows] > 1, x0[rows] + (i + 0.5) * w[rows] / mp, cx[rows])
                    fy = np.where(ny[rows] > 1, y0[rows] + (j + 0.5) * h[rows] / mp, cy[rows])
                    px.append(fx)
                    py.append(fy)
            sub = f.occupied(np.concatenate(px), np.concatenate(py), tk).reshape(mp * mp, len(rows), -1).any(axis=0)
            occ[rows] |= sub & wide[rows]
        occ &= ~skip
        occ[:, 0] = False
        return occ

    # ---- the tick ------------------------------------------------------------------------------------------------

    def tick(self, ws: WorldState, start: np.ndarray, hold: HoldState, prefix: np.ndarray, f: Forecast,
             prefs: TacticPrefs, ctx: FilterContext) -> PlanResult:
        t0 = time.perf_counter()
        cfg, params = self.cfg, self.params
        prefix = np.asarray(prefix, np.int64).reshape(-1)
        P = len(prefix)
        mode0 = int(np.asarray(start).reshape(kin.K, -1)[kin.MODE, 0])
        cs = self.cands_nc if mode0 in NO_CONTROL_MODES else self.cands
        N0, T = len(cs.cmd), cfg.T
        rows = [cs.cmd]
        cont = self.prev_cmd is not None
        if cont:
            rows.append(cmod.continue_plan(self.prev_cmd, 1, T)[None])
        cmd = np.concatenate(rows)
        N = len(cmd)
        full = np.empty((N, P + T), np.int64)
        full[:, :P] = prefix
        full[:, P:] = cmd
        ok, why = veto(cs, ctx)
        if cont:
            ok = np.append(ok, bool(ctx.allowed_mask.all()) or self._prev_allowed(ctx))
            why = np.append(why, 0 if ok[-1] else 1)
        latched, _ = hold_filter_jit(full, hold)
        t1 = time.perf_counter()
        roll = kin.rollout(start, latched, params, self.terrain, variants=cfg.variants, threads=cfg.threads)
        t2 = time.perf_counter()
        T1 = P + T + 1
        tk = np.arange(T1, dtype=np.float64) * params.frame_time
        enemy_only = not any(fm.hazard for fm in f.fc.model.families.values())
        skip = ((roll.flags_all & F_INVULN) != 0) if enemy_only else np.zeros((N, T1), bool)
        occ = self._contacts(f, roll.bound, tk, skip)
        S = occ.any(axis=1)
        t3 = time.perf_counter()
        hz = np.zeros(N, bool)
        hz_soft = np.zeros(N, bool)
        if ctx.hazards or ctx.soft:
            hull, kfl = knockback_hull(roll.box, params, self.terrain, threads=cfg.threads)
            hz, hz_soft = hazard_flags(hull, kfl, ctx)
        J, hits, may_kill = self._score(ws, roll, latched, start, f, prefs, P, tk)
        if cont:
            J[-1] += prefs.weights.get("cont", 0.0)
        U = unpausable(may_kill, ctx) if ctx.hp else np.zeros(N, bool)
        t4 = time.perf_counter()
        safe = ok & ~S & ~hz
        first = np.append(cs.first, -1) if cont else cs.first
        V = np.zeros(N, bool)
        counts = np.bincount(first[:N0][safe[:N0]], minlength=len(cs.first_names))
        V[:N0] = counts[first[:N0]] >= 2
        if cont:
            V[-1] = safe[-1]
        bind_res = None
        if prefs.want_bind and ctx.want_bind:
            bind_res = self._bind(ws, start, hold, prefix, f, ctx)
        forced = not safe.any() and not (bind_res is not None and bind_res[0])
        Pc = np.zeros(N)
        if forced and ok.any():
            cand = np.flatnonzero(ok)
            b = roll.box[cand]
            Pc[cand] = f.prob(0.5 * (b[..., 0] + b[..., 2]), 0.5 * (b[..., 1] + b[..., 3]), tk)
        t5 = time.perf_counter()
        if bind_res is not None and bind_res[0]:
            idx, name = -2, "BIND"
            sel_cmd = self.bind.cmd[0]
            res = PlanResult(int(sel_cmd[0]), idx, name, 0, False, 0.0, 1e3, True, n=N + 1,
                             n_allowed=int(ok.sum()) + 1, n_safe=int(safe.sum()) + 1, cmd=sel_cmd, path=bind_res[1])
        elif ok.any():
            order = np.lexsort((-J, Pc, ~V, S, U, hz_soft, hz))
            order = order[ok[order]]
            i = int(order[0])
            sel_cmd = cmd[i]
            name = "CONTINUE" if cont and i == N - 1 else cs.name(i)
            res = PlanResult(int(sel_cmd[0]), i, name, int(S[i]), forced, float(Pc[i]), float(J[i]), bool(V[i]),
                             bool(hz[i]), bool(U[i]), N, int(ok.sum()), int(safe.sum()), sel_cmd,
                             roll.box[i].copy(), roll.bound[i].copy(), hits=float(hits[i]))
            for j in order[1:6]:
                nm = "CONTINUE" if cont and j == N - 1 else cs.name(int(j))
                res.alternatives.append((nm, int(S[j]), round(float(Pc[j]), 3), round(float(J[j]), 2)))
        else:
            sel_cmd = np.zeros(T, np.int64)
            res = PlanResult(0, -1, "NONE", 1, True, n=N)
        res.vetoes = {REASONS[k]: int(v) for k, v in zip(*np.unique(why, return_counts=True)) if k}
        self.prev_cmd = sel_cmd
        self.prev_name = res.name
        self.ticks += 1
        t6 = time.perf_counter()
        res.t_ms = {"filter": (t1 - t0) * 1e3, "rollout": (t2 - t1) * 1e3, "support": (t3 - t2) * 1e3,
                    "score": (t4 - t3) * 1e3, "prob_bind": (t5 - t4) * 1e3, "select": (t6 - t5) * 1e3,
                    "total": (t6 - t0) * 1e3}
        return res

    def _prev_allowed(self, ctx: FilterContext) -> bool:
        """The carried plan uses only keys the allowlist still permits (evasive keys always are)."""
        m = int(np.bitwise_or.reduce(self.prev_cmd)) if self.prev_cmd is not None and len(self.prev_cmd) else 0
        need = []
        if m & B_ATTACK:
            need.append(Prim.ATTACK_SIDE)
        if m & B_QUICKCAST:
            need.append(Prim.SILKSKILL)
        if m & B_BIND:
            need.append(Prim.BIND)
        return all(ctx.allowed_mask[int(p)] for p in need)

    # ---- the Bind macro ------------------------------------------------------------------------------------------

    def _bind(self, ws: WorldState, start, hold, prefix, f: Forecast, ctx: FilterContext
              ) -> tuple[bool, np.ndarray]:
        P = len(prefix)
        T = self.cfg.T_bind
        full = np.empty((1, P + T), np.int64)
        full[0, :P] = prefix
        full[0, P:] = self.bind.cmd[0]
        latched, _ = hold_filter_jit(full, hold)
        roll = kin.rollout(start, latched, self.params, self.terrain, variants=self.cfg.variants, threads=1)
        tk = np.arange(P + T + 1, dtype=np.float64) * self.params.frame_time
        skip = np.zeros((1, P + T + 1), bool)
        occ = self._contacts(f, roll.bound, tk, skip)
        hz = False
        if ctx.hazards or ctx.soft:
            hull, kfl = knockback_hull(roll.box, self.params, self.terrain)
            a, b = hazard_flags(hull, kfl, ctx)
            hz = bool(a[0] or b[0])
        return (not occ.any()) and not hz, roll.box[0].copy()

    # ---- J ---------------------------------------------------------------------------------------------------------

    def _score(self, ws: WorldState, roll, latched: np.ndarray, start: np.ndarray, f: Forecast, prefs: TacticPrefs,
               P: int, tk: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        w = prefs.weights
        N, T1 = roll.flags.shape
        face0 = 1 if start.reshape(kin.K, -1)[kin.FACE, 0] >= 0 else -1
        boss, okb = f.boss_box(tk)
        wv = np.array([w.get("hit", 10.0), w.get("waste", 0.6), w.get("jump", 0.15), w.get("stance", 0.6),
                       w.get("risk", 3.0), w.get("face", 0.3), w.get("ground", 0.2)])
        boss_x = prefs.boss_x if prefs.boss_x is not None else np.nan
        max_hits = float(prefs.max_hits) if prefs.max_hits is not None else np.inf
        rx = prefs.risk_x if len(prefs.risk_x) else np.zeros(1)
        rv = prefs.risk if len(prefs.risk) else np.zeros(1)
        J = np.zeros(N)
        hits = np.zeros(N)
        near = np.zeros(N, np.bool_)
        _score_kernel(np.ascontiguousarray(roll.box), np.ascontiguousarray(roll.flags),
                      np.ascontiguousarray(roll.mode), np.ascontiguousarray(latched), face0,
                      np.ascontiguousarray(boss, np.float64), np.ascontiguousarray(okb), wv, float(prefs.stance_x),
                      np.ascontiguousarray(rx, np.float64), np.ascontiguousarray(rv, np.float64), boss_x, max_hits,
                      J, hits, near)
        boss_hp = f.fc.tracker.ctx.hp
        may_kill = near if (boss_hp is not None and boss_hp <= SPEAR_DAMAGE) else np.zeros(N, bool)
        return J, hits, may_kill


SPEAR_DAMAGE = 15.0


@numba.njit(cache=True, inline="always")
def _ov(cx, cy, face, fx0, fx1, y0, y1, b0, b1, b2, b3):
    if face > 0:
        ax0, ax1 = cx + fx0, cx + fx1
    else:
        ax0, ax1 = cx - fx1, cx - fx0
    return ax0 < b2 and ax1 > b0 and cy + y0 < b3 and cy + y1 > b1


@numba.njit(cache=True, parallel=True)
def _score_kernel(box, flags, mode, latched, face0, boss, okb, wv, stance_x, rx, rv, boss_x, max_hits, J, hits, near):
    """J per candidate (the module docstring's terms) on the nominal lane; hits: predicted boss hits (Silkspear x 3);
    near: an attack starts with the boss within 1 u of its box (a possible killing blow, U)."""
    N, T1 = flags.shape
    any_boss = False
    for k in range(T1):
        if okb[k]:
            any_boss = True
    for c in numba.prange(N):
        face = face0
        fc = np.empty(T1, np.int64)
        cxs = np.empty(T1)
        cys = np.empty(T1)
        for k in range(T1):
            if k > 0:
                m = latched[c, k - 1]
                if m & B_LEFT:
                    face = -1
                elif m & B_RIGHT:
                    face = 1
            fc[k] = face
            cxs[k] = 0.5 * (box[c, k, 0] + box[c, k, 2])
            cys[k] = 0.5 * (box[c, k, 1] + box[c, k, 3])
        h = 0.0
        presses = 0
        jumps = 0
        nr = False
        for k in range(T1):
            if k > 0:
                jl = (latched[c, k - 1] & B_JUMP) != 0
                jp = k > 1 and (latched[c, k - 2] & B_JUMP) != 0
                if jl and not jp:
                    jumps += 1
            if k == 0:
                continue
            att = (flags[c, k] & F_ATTACKING) != 0 and (flags[c, k - 1] & F_ATTACKING) == 0
            dsk = (mode[c, k] == M_DS_ANTIC or mode[c, k] == M_DS_SPIKE) and not (
                mode[c, k - 1] == M_DS_ANTIC or mode[c, k - 1] == M_DS_SPIKE)
            cst = mode[c, k] == M_CAST and mode[c, k - 1] != M_CAST
            if not (att or dsk or cst):
                continue
            presses += 1
            if not any_boss:
                continue
            up = (latched[c, k - 1] & B_UP) != 0
            got = False
            if att:
                for j in range(k, min(T1, k + ACTIVE_F)):
                    if not okb[j]:
                        continue
                    bx = boss[j]
                    if up:
                        if _ov(cxs[j], cys[j], fc[j], UP[0], UP[1], UP[2], UP[3], bx[0], bx[1], bx[2], bx[3]):
                            got = True
                    elif _ov(cxs[j], cys[j], fc[j], SIDE[0], SIDE[1], SIDE[2], SIDE[3], bx[0], bx[1], bx[2], bx[3]):
                        got = True
                    if _ov(cxs[j], cys[j], fc[j], SIDE[0] - 1.0, SIDE[1] + 1.0, SIDE[2] - 1.0, SIDE[3] + 1.0, bx[0],
                           bx[1], bx[2], bx[3]):
                        nr = True
                if got:
                    h += 1.0
            elif dsk:
                for j in range(k, min(T1, k + 10)):
                    if okb[j] and _ov(cxs[j], cys[j], fc[j], DOWN[0], DOWN[1], DOWN[2], DOWN[3], boss[j, 0],
                                      boss[j, 1], boss[j, 2], boss[j, 3]):
                        got = True
                        nr = True
                if got:
                    h += 1.0
            else:
                j = k + SPEAR_DELAY_F
                if j < T1 and okb[j] and _ov(cxs[j], cys[j], fc[j], SPEAR[0], SPEAR[1], SPEAR[2], SPEAR[3],
                                             boss[j, 0], boss[j, 1], boss[j, 2], boss[j, 3]):
                    h += 3.0
                    nr = True
        h = min(h, max_hits)
        waste = max(presses - h, 0.0)
        x_end = cxs[T1 - 1]
        r = np.interp(x_end, rx, rv)
        v = wv[0] * h - wv[1] * waste - wv[2] * jumps - wv[3] * abs(x_end - stance_x) - wv[4] * r
        if boss_x == boss_x:
            want = 1 if boss_x > x_end else -1
            if fc[T1 - 1] == want:
                v += wv[5]
        if flags[c, T1 - 1] & F_GROUND:
            v += wv[6]
        J[c] = v
        hits[c] = h
        near[c] = nr
