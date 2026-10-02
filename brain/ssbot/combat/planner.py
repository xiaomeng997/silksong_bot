"""L1 planner (DESIGN §3.5.4; M2 W4): every frame, roll every candidate out through the kinematics' timing lanes and
choose lexicographically: not Hz > not Hz_soft > not U > S = 0 > keeps the committed jump hold > comfort > V > min P >
latest first contact > max J; FORCED_RISK when no allowed candidate has S = 0.
- FORCED_RISK ranks by the probability, then by the latest first contact: a plan certain to be hit was otherwise
  ranked by its score, and "wait, then go" re-chosen every frame never left (live run 20261002_041819).
- A pressed jump commits its hold schedule (§3.5.4): plans that release it early or cast rank below the ones that
  keep it while one of those is safe (live run 20261002_044711: a plan switch released a charge jump after 8 frames,
  a Silkspear cast then held the hero at the charge's height).
- Comfort is S again against templates grown by a further margin: among safe plans the ones with clearance win,
  whatever they score (live run 20261002_035118: a plan safe by millimetres in the air over a rolling attack bell lost
  all 26 safe continuations in one frame of drift, and the bell hit).
- Beyond the horizon: of the 2 best safe plans, the first whose end state keeps a safe way on over 0.8 s more (stay,
  run, jump) is chosen (Planner._tail_pick; a punish that ended under a bouncing drop bell, run 20261002_052118); a
  Silkspear still locking the hero at the horizon's end without such a way on gives way to the best safe plan that is
  free at its end (run 20261002_064001: 2 of 3 hits were a drop bell on a hero still casting).
- Hit effects: a slash that meets the boss's predicted hurtbox recoils the hero, an up-slash stops her rise, a down
  attack bounces her with its i-frames (Planner._hit_effects re-rolls those candidates with the event, twice, so a
  second slash is scored from where the first recoil left her); safe only if the miss branch is too. The long set carries
  jump-then-down-attack candidates for charges.
- Jump release: a pressed jump's hold is committed only release_latency (4) frames ahead; a later tick may move a
  release further out (DESIGN 3.5.4 refined: the height follows the boss's approach, e.g. a low hop for a pogo).
- Adaptive horizon (M2 plan): when the tactics ask for more than T frames (a committed charge), the dodge set
  candidates.build_long rolls out to the end of the attack, up to 2 s (live run 20261002_045049: with 0.8 s, jumps
  that cleared a charge's front half came down on its back half, 5 hits).

    planner = Planner(params, terrain)
    r = planner.tick(ws, start, hold, prefix, forecast, prefs, ctx)    # r.mask: the commanded mask for the next free
                                                                       # frame; r.S, r.forced_risk for the supervisor

Inputs. `start` is the hero's kinematic state at the WorldState's frame f (StateTracker in the glue: the planner never
reads oracle fields); `prefix` the commanded masks already sent for frames f+1 .. f+P (P = 1 with the harness's
2-frame lead; 1 + k on the simulated final path with k frames of observation delay), so the decision is for frame
f+P+1 and the rollout covers the prefix too (§3.5.4 `state_at(now + L)` on the executed command stream); `hold` the
oracle HoldFilter state at f (STATE act.hf, exact), which the compiled hold filter (combat.holdfilter) continues.

Per candidate (candidates.build: 21 first primitives x 17 continuations = 357, plus the previous plan carried on, plus
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
            hits x 3, wasted attacks, Silkspear casts that hit nothing (cast_waste: 4 of the Bind's 9 silk), jump
            presses, the end position's distance to the tactics' stance, its future
            support coverage (the tactics' risk map: the terminal value), facing the boss, ending on the floor, and
            a bonus for carrying on the previous plan (hysteresis).
Cost (13900K, 8 threads, ssbot.tools.planner_bench open loop over 5,951 ticks of live recording i2_002, 4 game
instances idling): planner p50 1.68 / p99 3.73 ms (rollout 0.90 / 1.99, support 0.42 / 1.71, hold filter + veto
0.18 / 0.55, scoring 0.06 / 0.31, probabilities and Bind 0.02 / 0.78), the whole tick with forecast and tactics p50
2.03 / p99 4.34 ms. The replayed hero is the data policy's, often in contact (FORCED_RISK, hit-stop); in the planner's
own fights the probabilities are rarely needed.
"""
import math
import time
from dataclasses import dataclass, field

import numba
import numpy as np

from ssbot.combat import candidates as cmod
from ssbot.combat import pogo_targets as pt
from ssbot.combat.forecast import body_shape, Forecast
from ssbot.combat.holdfilter import hold_filter_jit
from ssbot.combat.safety_filter import REASONS, FilterContext, hazard_flags, unpausable, veto
from ssbot.combat.tactics.modes import TacticPrefs
from ssbot.core.primitives import Prim
from ssbot.core.worldstate import WorldState
from ssbot.knowledge import kinematics as kin
from ssbot.knowledge.knockback import knockback_hull
from ssbot.knowledge.kinematics import (B_ATTACK, B_BIND, B_DOWN, B_JUMP, B_LEFT, B_QUICKCAST, B_RIGHT, B_UP,
                                        F_ATTACKING, F_GROUND, F_INVULN, M_CAST, M_DS_ANTIC, M_DS_SPIKE, M_NORMAL,
                                        HeroParams, HoldState, Terrain2D)

# Hunter attack boxes relative to the hurtbox centre in the facing frame (+x forward), crests.json P17 clash_tink
# polygons (captured facing left): side x [-0.12, 2.81] y [-0.62, 1.52]; up x [-1.23, 0.85] y [-0.04, 3.33];
# down spike x [-0.69, 1.41] y [-1.96, 0.32]. Silkspear: a forward band (scoring only).
SIDE = (-0.12, 2.81, -0.62, 1.52)
UP = (-1.23, 0.85, -0.04, 3.33)
DOWN = (-0.69, 1.41, -1.96, 0.32)
SPEAR = (0.3, 11.0, -0.8, 0.8)
# When each attack's box is really out, frames after the press reaches the game (the rollout's attack / cast start),
# measured as press -> hit event in live run 20261002_081716 (oracle, 52 episodes): Slash / AltSlash p5-p95 1-3 / 1-4
# frames (828 of 1037 side presses hit), UpSlash 2-7 (48 of 91), the Silkspear needle 18-19 (237 of 267 casts); the
# down spike while the kinematics are in M_DS_SPIKE (after its 0.1 s antic). Each is scored against the boss's
# hurtbox predicted for those frames (Forecast.boss_box along the family's mean path), not the press frame's: an
# earlier version scored the up-slash over frames 0-5 and the down spike from its antic on, and none of 112 down
# presses hit.
SPEAR_DELAY_F = 18             # Silkspear: the needle hits 18-19 frames after the cast starts
# [side, up, down spike (from, to; to 0: the spike frames only), Silkspear]; v1 = the first model, for the audit's
# before / after (PlannerConfig.attack_model): up 0-5, the down spike from its antic for 10 frames, the needle at 16
WINDOWS = {"v2": np.array([[0, 6], [2, 8], [0, 0], [17, 20]], np.int64),
           "v1": np.array([[0, 6], [0, 6], [0, 10], [16, 17]], np.int64)}
TAIL_CHUNK = 2                # candidates per tail check batch
LOCK_EXTRA = 48               # frames a plan locked at the horizon's end is rolled on (a Silkspear locks ~73 frames)
LOCK_AFTER = 8                # ... and checked this many frames after the lock ends
COMFORT_FRAMES = 48           # the comfort check covers the whole horizon (24 frames: run 20261002_045049 hits)
NO_CONTROL_MODES = (kin.M_HURT_FREEZE, kin.M_HURT_RECOIL, kin.M_CAST, kin.M_BIND, kin.M_LOCKED)


@dataclass
class PlannerConfig:
    T: int = 48
    T_long: int = 120          # the adaptive horizon's cap (2 s, the forecast's horizon)
    T_bind: int = 100
    threads: int = 4
    variants: str = "bounds"
    max_points: int = 2        # grid points per axis for a hull wider than one point covers
    predict_log: bool = False  # record the chosen plan's attack predictions at each press (predict_audit; a lanes
    #                            rollout of the chosen plan: audit runs only, SSBOT_PREDICT_LOG=1)
    attack_model: str = "v2"
    release_latency: int = 4   # frames a planned jump release must lie ahead to be moved (the path latency, 2-4)
    pogo_k: int = 32           # fine-grid pogo candidates kept per tick (pruned by the boss's predicted path)
    pogo_lanes_k: int = 16     # pogo plans checked lane by lane per tick (the rest are rejected)   # "v1": the first attack windows and no slash recoil (the audit's before)
    tail_k: int = 2            # safe candidates checked for a way on beyond the horizon (0: off; one chunk)


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
    tail_ok: bool | None = None             # the chosen plan's end has a safe way on beyond the horizon (None: unchecked)
    attacks: list | None = None             # its attack predictions at a press (Planner._predict_attacks)
    best_up: tuple | None = None            # the best plan with an up-slash: (name, S, V, J, hits)
    attack: tuple | None = None             # its first attack scored as a hit: (kind, start frame, predicted boss box
    #                                         [x0, y0, x1, y1] at the active frame) for the whiff audit
    vetoes: dict = field(default_factory=dict)
    hits: float = 0.0


@numba.njit(cache=True)
def _hull_points(bound, hx, hy, mp):
    """Query points for hull boxes [N, T, 4]: X, Y [N + (mp*mp - 1) * R, T] (the first point of every frame, then
    one layer per extra grid point for the R rows that have a frame wider than a point covers; NaN where a frame needs
    fewer points), the row indices R and too_wide [N, T] (wider than mp points cover: counted as contact)."""
    N, T = bound.shape[0], bound.shape[1]
    gxs = np.ones((N, T), np.int64)
    gys = np.ones((N, T), np.int64)
    too_wide = np.zeros((N, T), np.bool_)
    wide_row = np.zeros(N, np.bool_)
    for n in range(N):
        for t in range(T):
            w = bound[n, t, 2] - bound[n, t, 0]
            h = bound[n, t, 3] - bound[n, t, 1]
            gx = int(np.ceil(w / (2 * hx) - 1e-9))
            gy = int(np.ceil(h / (2 * hy) - 1e-9))
            if gx > mp or gy > mp:
                too_wide[n, t] = True
            gx = min(max(gx, 1), mp)
            gy = min(max(gy, 1), mp)
            gxs[n, t] = gx
            gys[n, t] = gy
            if gx > 1 or gy > 1:
                wide_row[n] = True
    rows = np.flatnonzero(wide_row)
    R = rows.shape[0]
    L = mp * mp - 1
    X = np.full((N + L * R, T), np.nan)
    Y = np.full((N + L * R, T), np.nan)
    for n in range(N):
        for t in range(T):
            X[n, t] = bound[n, t, 0] + 0.5 * (bound[n, t, 2] - bound[n, t, 0]) / gxs[n, t]
            Y[n, t] = bound[n, t, 1] + 0.5 * (bound[n, t, 3] - bound[n, t, 1]) / gys[n, t]
    for r in range(R):
        n = rows[r]
        for t in range(T):
            gx, gy = gxs[n, t], gys[n, t]
            w = bound[n, t, 2] - bound[n, t, 0]
            h = bound[n, t, 3] - bound[n, t, 1]
            layer = 0
            for i in range(mp):
                for j in range(mp):
                    if i == 0 and j == 0:
                        continue
                    if i < gx and j < gy:
                        X[N + layer * R + r, t] = bound[n, t, 0] + (i + 0.5) * w / gx
                        Y[N + layer * R + r, t] = bound[n, t, 1] + (j + 0.5) * h / gy
                    layer += 1
    return X, Y, rows, too_wide


class Planner:
    def __init__(self, params: HeroParams, terrain: Terrain2D, cfg: PlannerConfig | None = None):
        self.params = params
        self.terrain = terrain
        self.cfg = cfg or PlannerConfig()
        self.cands = cmod.build(self.cfg.T)
        self.cands_nc = cmod.no_control(self.cands)
        self.cands_long = cmod.build_long(self.cfg.T_long)
        self._grid = None
        self._has_up = ((self.cands.cmd & B_UP) != 0).any(axis=1) & ((self.cands.cmd & B_ATTACK) != 0).any(axis=1)
        self.tails = cmod.tails(self.cfg.T)
        self.bind = cmod.bind_macro(self.cfg.T_bind)
        self.reset()

    def reset(self) -> None:
        self.prev_cmd: np.ndarray | None = None
        self.prev_name = ""
        self.ticks = 0
        self._audit = (np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros((0, 4)))
        self.last_pogo = 0            # candidates with a predicted bounce in the last tick
        self.last_recoil = 0          # ... with a predicted nail recoil
        self.last_bell_pogo = 0       # ... bouncing off a registry target (a bell)
        self._pogo_ok = np.zeros(0, bool)
        self.pogo_log = {"generated": 0, "lane_miss": 0, "accepted": 0}   # last tick's pogo plans: every lane
        #                                                                     connects or rejected (S)
        self.jump_until = -1          # tick until which the pressed jump's hold schedule is committed
        self.macro_until = -1         # tick until which a started macro (pogo chain) is kept (MACRO_MARGIN)
        self.prev_tail_ok = False

    # ---- S -----------------------------------------------------------------------------------------------------------

    def _contacts(self, f: Forecast, bound: np.ndarray, tk: np.ndarray, skip: np.ndarray, comfort: bool = False
                  ) -> np.ndarray:
        """[N, T1] contact of the lanes' hull with the support. A hull a point covers (the templates are dilated by
        the hurtbox plus the margin) is tested at its centre; a wider one at a grid of 2 points along each wide axis
        (sub-boxes the dilation covers), wider still counts as contact. One query: the first point of every frame,
        plus extra layers for the rows with a wide frame (NaN where a frame needs fewer points: skipped)."""
        hx, hy = f.fc.half
        X, Y, rows, too_wide = _hull_points(np.ascontiguousarray(bound), hx, hy, self.cfg.max_points)
        hit = f.occupied(X, Y, tk, comfort)
        N = bound.shape[0]
        occ = hit[:N].copy()
        if len(rows):
            occ[rows] |= hit[N:].reshape(-1, len(rows), hit.shape[1]).any(axis=0)
        occ |= too_wide
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
        T_req = int(min(max(prefs.horizon_frames, 0), cfg.T_long))
        if T_req > cfg.T:
            cs = cmod.truncate(self.cands_long, T_req)          # adaptive horizon: through a committed long attack
            cs = self._pogo_pick(cs, f, start, T_req)
        else:
            cs = self.cands_nc if mode0 in NO_CONTROL_MODES else self.cands
        N0, T = len(cs.cmd), cs.T
        rows = [cs.cmd]
        cont = self.prev_cmd is not None
        if cont:
            rows.append(cmod.continue_plan(self.prev_cmd, 1, T)[None])
        cmd = np.concatenate(rows)
        rem0 = self.jump_until - self.ticks
        if rem0 > 0:
            # a slash keeps the committed jump held (an up-slash into a leaping boss above the hero): without it every
            # attack released the jump and ranked below the plans that keep it (the person saw side slashes under a
            # leap; live run 20261002_064001: in Leap Out 56 fresh side slashes hit 6 times, 52 up-slashes 37 times)
            att = np.array([n.startswith("ATTACK") for n in cs.first_names])[cs.first]
            if att.any():
                cmd = cmd.copy()
                cmd[:N0][att, :min(rem0, T)] |= B_JUMP
        N = len(cmd)
        full = np.empty((N, P + T), np.int64)
        full[:, :P] = prefix
        full[:, P:] = cmd
        ok, why = veto(cs, ctx)
        if cont:
            ok = np.append(ok, bool(ctx.allowed_mask.all()) or self._prev_allowed(ctx))
            why = np.append(why, 0 if ok[-1] else 1)
        latched, hold_end = hold_filter_jit(full, hold)
        t1 = time.perf_counter()
        roll = kin.rollout(start, latched, params, self.terrain, variants=cfg.variants, threads=cfg.threads)
        t2 = time.perf_counter()
        T1 = P + T + 1
        tk = np.arange(T1, dtype=np.float64) * params.frame_time
        enemy_only = not any(fm.hazard for fm in f.fc.model.families.values())
        skip = ((roll.flags_all & F_INVULN) != 0) if enemy_only else np.zeros((N, T1), bool)
        occ = self._contacts(f, roll.bound, tk, skip)
        S = occ.any(axis=1)
        roll_j = self._hit_effects(f, start, latched, roll, tk, S, enemy_only)
        self._lock_check(f, roll, hold_end, S, P + T, enemy_only)
        t_hit = np.where(S, occ.argmax(axis=1), T1)        # first contact frame (FORCED_RISK: later is better)
        S2 = S.copy()
        if f.fc.query_c is not None:
            rows = np.flatnonzero(ok & ~S)
            tc = min(T1, COMFORT_FRAMES + P + 1)      # clearance matters for the drift of the next frames
            if len(rows):
                S2[rows] = self._contacts(f, roll.bound[rows, :tc], tk[:tc], skip[rows, :tc], comfort=True
                                          ).any(axis=1)
        t3 = time.perf_counter()
        hz = np.zeros(N, bool)
        hz_soft = np.zeros(N, bool)
        if ctx.hazards or ctx.soft:
            hull, kfl = knockback_hull(roll.box, params, self.terrain, threads=cfg.threads)
            hz, hz_soft = hazard_flags(hull, kfl, ctx)
        J, hits, may_kill = self._score(ws, roll_j, latched, start, f, prefs, P, tk)
        if cont:
            J[-1] += prefs.weights.get("cont", 0.0)
        U = unpausable(may_kill, ctx) if ctx.hp else np.zeros(N, bool)
        t4 = time.perf_counter()
        # a jump's hold is committed when it is pressed (DESIGN §3.5.4): a plan that releases it early, or casts
        # (a cast stops the rise), ranks below every plan that keeps it, unless none of those is safe (ABORT)
        rem = self.jump_until - self.ticks
        keep = np.ones(N, bool)
        if rem > 0:
            # the committed hold binds only the next release_latency frames (and the hold filter's minimum press,
            # which the rollout applies): a later release can move while it is still that far ahead, so the jump's
            # height follows the boss's approach (a refinement of DESIGN 3.5.4; the executed stream still equals
            # the rolled-out one, the frames already sent are the prefix)
            w = cmd[:, :min(rem, T, cfg.release_latency)]
            keep = ((w & B_JUMP) != 0).all(axis=1) & ((w & B_QUICKCAST) == 0).all(axis=1)
        safe = ok & ~S & ~hz
        self.last_safe, self.last_cs = safe, cs      # audits (which candidates were safe this tick)
        first = np.append(cs.first, -1) if cont else cs.first
        V = np.zeros(N, bool)
        counts = np.bincount(first[:N0][safe[:N0]], minlength=len(cs.first_names))
        V[:N0] = counts[first[:N0]] >= 2
        if cont:
            V[-1] = safe[-1]
        # an accepted pogo (every lane bounces, the bounce branch safe) passes the boss's body by design: the comfort
        # margin would always rank it below plans keeping clearance, and as the only candidate of its first piece it
        # never had V; its bounce is its way on (gate chunk 20261002_123347, 2 episodes replayed: accepted pogos in
        # 107 of 936 charge ticks, chosen in none)
        pz = self._pogo_ok[:N] if len(self._pogo_ok) >= N else np.zeros(N, bool)
        S2 = np.where(pz, False, S2)
        V = V | (pz & safe)
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
            # a started macro (a pogo chain: hop, down press, bounce, second press) is kept while it stays safe,
            # unless another plan beats it by MACRO_MARGIN: re-planned every tick, 2,433 chosen pogo plans of live
            # run 20261002_105845 were all replaced before their down press and none was sent
            mkeep = np.ones(N, bool)
            if cont and self.macro_until > self.ticks:
                mkeep = J >= J[N - 1] + MACRO_MARGIN
                mkeep[N - 1] = True
            order = np.lexsort((-J, -t_hit, Pc, ~V, S2, ~mkeep, ~keep, S, U, hz_soft, hz))
            order = order[ok[order]]
            i = int(order[0])
            tail_ok = None
            carried = cont and i == N - 1 and self.prev_tail_ok
            if not forced and T <= cfg.T and cfg.tail_k > 0 and not carried:
                ranked = order[safe[order]]
                i, tail_ok = self._tail_pick(f, roll, hold_end, ranked, P + T, i)
                if tail_ok is False and roll.mode[i, -1] == M_CAST:
                    # a Silkspear locks the hero ~73 frames, past the horizon: with no way on after it, take the
                    # best safe plan that is free at its end instead (run 20261002_064001: 2 of 3 hits were a drop
                    # bell coming down on a hero still in the cast after Leap Land)
                    free = ranked[roll.mode[ranked, -1] != M_CAST]
                    if len(free):
                        j, ok_j = self._tail_pick(f, roll, hold_end, free[:1], P + T, int(free[0]))
                        i, tail_ok = (j, ok_j) if ok_j else (int(free[0]), False)
            elif carried:
                tail_ok = True                     # the plan kept from last tick passed its check then
            self.prev_tail_ok = bool(tail_ok)
            sel_cmd = cmd[i]
            name = "CONTINUE" if cont and i == N - 1 else cs.name(i)
            res = PlanResult(int(sel_cmd[0]), i, name, int(S[i]), forced, float(Pc[i]), float(J[i]), bool(V[i]),
                             bool(hz[i]), bool(U[i]), N, int(ok.sum()), int(safe.sum()), sel_cmd,
                             roll.box[i].copy(), roll.bound[i].copy(), hits=float(hits[i]))
            res.tail_ok = tail_ok
            # the best plan with an up-slash in it, beside the chosen one (why an up-slash loses, when it does)
            up_rows = np.flatnonzero(self._has_up[:N0]) if len(self._has_up) >= N0 and cs is self.cands else []
            if len(up_rows):
                bu = int(up_rows[np.lexsort((-J[up_rows], S[up_rows]))[0]])
                res.best_up = (cs.name(bu), int(S[bu]), bool(V[bu]), round(float(J[bu]), 2), float(hits[bu]))
            fh, fk, bb = self._audit
            if fh[i] >= 0 and len(bb):
                jj = min(int(fh[i]) + {1: 3, 2: 5, 3: 8, 4: 18}[int(fk[i])], len(bb) - 1)
                res.attack = (int(fk[i]), int(fh[i]), [round(float(v), 2) for v in bb[jj]])
            if cfg.predict_log and (sel_cmd[0] & (B_ATTACK | B_QUICKCAST)) and not (prefix[-1:] & (B_ATTACK |
                                                                                             B_QUICKCAST)).any():
                res.attacks = self._predict_attacks(f, start, latched[i], i, tk, P)
            for j in order[1:6]:
                nm = "CONTINUE" if cont and j == N - 1 else cs.name(int(j))
                res.alternatives.append((nm, int(S[j]), round(float(Pc[j]), 3), round(float(J[j]), 2)))
        else:
            sel_cmd = np.zeros(T, np.int64)
            res = PlanResult(0, -1, "NONE", 1, True, n=N)
        res.vetoes = {REASONS[k]: int(v) for k, v in zip(*np.unique(why, return_counts=True)) if k}
        if len(sel_cmd) and sel_cmd[0] & B_JUMP:
            if self.jump_until <= self.ticks:                        # a new press: commit its hold
                held = sel_cmd & B_JUMP
                self.jump_until = self.ticks + (int(np.argmin(held != 0)) if (held == 0).any() else len(held))
        else:
            self.jump_until = -1                                      # released (or aborted): nothing committed
        if _is_macro(res.name):
            # committed until the chain's last planned press has gone out and the bounce had time (+12 frames)
            last = np.flatnonzero((sel_cmd & B_DOWN) != 0)
            self.macro_until = self.ticks + (int(last[-1]) + 12 if len(last) else 0)
        elif res.name != "CONTINUE":
            self.macro_until = -1
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

    # ---- the pogo ---------------------------------------------------------------------------------------------------

    def _hit_effects(self, f: Forecast, start, latched: np.ndarray, roll, tk: np.ndarray, S: np.ndarray,
                     enemy_only: bool):
        """What a hit does to the hero, in the rollout: a side slash that meets the boss's predicted hurtbox in its
        active frames recoils her away (EV_RECOIL_L/R: 3.75 u/s for 9 steps), an up-slash stops her rise
        (EV_RECOIL_DOWN), a down spike bounces her (EV_POGO, with its i-frames against enemies). The rollout does not
        know the boss, so candidates with a predicted hit are rolled out again with the event from that frame, twice
        (a second hit from where the first one left her: in the burst punish the first slash's recoil made the second
        whiff). Safety needs both branches (DESIGN 3.5.6: an attack may miss or come late): S is updated in place.
        Returns the rollout to score J on (the hit branch where one is predicted)."""
        self.last_pogo = 0
        self.last_recoil = 0
        self.last_bell_pogo = 0
        self._fx_ev = None
        self.pogo_log = {"generated": 0, "lane_miss": 0, "accepted": 0, "bell": 0}
        self._pogo_ok = np.zeros(len(latched), bool)
        modes = roll.mode
        if not (((roll.flags & F_ATTACKING) != 0).any() or (modes == M_DS_SPIKE).any()):
            return roll
        tgts = self._targets(f, tk)
        if not tgts:
            return roll
        face0 = 1 if start.reshape(kin.K, -1)[kin.FACE, 0] >= 0 else -1
        win = WINDOWS[self.cfg.attack_model]
        N, T = latched.shape
        ev = np.zeros((N, T), np.int64)
        cur = _View(roll.box, roll.flags, roll.mode, roll.bound, roll.flags_all)
        after = np.full(N, -1, np.int64)
        rows_all = np.zeros(N, bool)
        pogo_tgt = np.full(N, -1, np.int64)      # the target of a row's first predicted bounce (0: the boss)
        for _ in range(2):
            hit_f = np.full(N, -1, np.int64)
            kind = np.zeros(N, np.int64)
            tsel = np.full(N, -1, np.int64)
            cb, cf, cm = (np.ascontiguousarray(cur.box), np.ascontiguousarray(cur.flags),
                          np.ascontiguousarray(cur.mode))
            for ti, g in enumerate(tgts):
                hf = np.full(N, -1, np.int64)
                kd = np.zeros(N, np.int64)
                _first_hits(cb, cf, cm, np.ascontiguousarray(latched), face0, g.box, g.ok, g.polys, g.starts, g.base,
                            after, hf, kd, win)
                if not g.recoil:
                    hf[kd != 3] = -1
                better = (hf >= 0) & ((hit_f < 0) | (hf < hit_f))
                hit_f[better], kind[better], tsel[better] = hf[better], kd[better], ti
            if self.cfg.attack_model == "v1":
                hit_f[kind != 3] = -1      # the first model predicted the pogo only
            rows = np.flatnonzero(hit_f >= 0)
            if not len(rows):
                break
            j = np.minimum(hit_f[rows], T - 1)
            k = kind[rows]
            bits = np.where(k == 3, kin.EV_POGO, np.where(k == 2, kin.EV_RECOIL_DOWN,
                                                          np.where(k == 1, kin.EV_RECOIL_L, kin.EV_RECOIL_R)))
            ev[rows, j] |= bits
            pr = rows[(k == 3) & (pogo_tgt[rows] < 0)]
            pogo_tgt[pr] = tsel[pr]
            self.last_pogo += int((k == 3).sum())
            self.last_bell_pogo += int(((k == 3) & (tsel[rows] > 0)).sum())
            self.last_recoil += int((k <= 1).sum())
            after[rows] = hit_f[rows]
            rows_all[rows] = True
            sub = np.flatnonzero(rows_all)
            rh = kin.rollout(start, latched[sub], self.params, self.terrain, events=ev[sub],
                             variants=self.cfg.variants, threads=self.cfg.threads)
            box, flags, mode = cur.box.copy(), cur.flags.copy(), cur.mode.copy()
            bound, fall = cur.bound.copy(), cur.flags_all.copy()
            box[sub], flags[sub], mode[sub], bound[sub], fall[sub] = rh.box, rh.flags, rh.mode, rh.bound, rh.flags_all
            cur = _View(box, flags, mode, bound, fall)
        self._fx_ev = ev
        sub = np.flatnonzero(rows_all)
        s_hit = np.zeros(N, bool)
        if len(sub):
            skip = ((cur.flags_all[sub] & F_INVULN) != 0) if enemy_only else np.zeros(cur.flags_all[sub].shape, bool)
            s_hit[sub] = self._contacts(f, cur.bound[sub], tk, skip).any(axis=1)
            S[sub] |= s_hit[sub]
        # a pogo plan stands only if the down spike connects in every timing lane (DESIGN 3.5.6: a miss lands the hero
        # on the boss, or on the bell): its lanes rolled out with the bounce, a lane whose first spike meets no hurtbox
        # (for a bell: its certain circle on its predicted path) rejects it (S)
        pg_all = np.flatnonzero(rows_all & ((ev & kin.EV_POGO) != 0).any(axis=1))
        self.pogo_log = {"generated": int(len(pg_all)), "lane_miss": 0, "accepted": 0, "bell": 0}
        # the lanes only for those the bounce branch leaves safe (the rest are rejected anyway), at most pogo_lanes_k
        # of them (the earliest bounces): the per-lane check costs about 0.1 ms a candidate
        pg = pg_all[~s_hit[pg_all]]
        if len(pg) > self.cfg.pogo_lanes_k:
            # the carried plan (the last row: CONTINUE of a started chain) is always checked, never dropped by the cap
            first_bounce = np.argmax((ev[pg] & kin.EV_POGO) != 0, axis=1) - (pg == N - 1) * 10 ** 6
            order = np.argsort(first_bounce, kind="stable")
            S[pg[order[self.cfg.pogo_lanes_k:]]] = True
            pg = pg[order[:self.cfg.pogo_lanes_k]]
        if len(pg):
            rl = kin.rollout(start, latched[pg], self.params, self.terrain, events=ev[pg], variants=self.cfg.variants,
                             lanes=True)
            conn = np.zeros(len(pg), np.bool_)
            for ti in np.unique(pogo_tgt[pg]):
                g = tgts[max(int(ti), 0)]
                idx = np.flatnonzero(pogo_tgt[pg] == ti)
                cn = np.zeros(len(idx), np.bool_)
                _lanes_connect(np.ascontiguousarray(rl.var_box[idx]), np.ascontiguousarray(rl.var_flags[idx]),
                               np.ascontiguousarray(rl.var_mode[idx]), np.ascontiguousarray(latched[pg[idx]]), face0,
                               g.cbox, g.cok, g.cpolys, g.cstarts, g.cbase, win, cn)
                conn[idx] = cn
            for n, c in enumerate(pg):
                ok_all = bool(conn[n])
                if not ok_all:
                    S[c] = True
                    self.pogo_log["lane_miss"] += 1
                else:
                    S[c] = s_hit[c]           # every lane bounces: the miss branch does not happen in the model
                    self.pogo_log["accepted"] += int(not S[c])
                    if not S[c]:
                        self._pogo_ok[c] = True
                        self.pogo_log["bell"] += int(pogo_tgt[c] > 0)
        return cur

    def _targets(self, f: Forecast, tk: np.ndarray) -> list["_Target"]:
        """What an attack can hit in the rollout: the boss's predicted hurtbox (target 0, when drawn), then the
        registry targets on their predicted paths (pogo_targets: bells). Each with its certain form for the pogo gate
        (the boss's: the same; a target's: its circle minus CERT_MARGIN_U, CERT_MAX_S ahead)."""
        out = []
        boss, okb = f.boss_box(tk)
        polys, starts = f.body_polys()
        b0 = _box_of(polys) if len(polys) else boss[0]
        base = np.array([b0[0], b0[1]])
        bt = _Target(np.ascontiguousarray(boss, np.float64), np.ascontiguousarray(okb),
                     np.ascontiguousarray(polys, np.float64), np.ascontiguousarray(starts, np.int64), base)
        out.append(bt)
        paths = f.target_paths(tk) if hasattr(f, "target_paths") else []
        for pth in paths:
            P0, S0, B0 = pt.octagon(pth.r)
            m = pt.CERT_MARGIN_U
            P1, S1, B1 = pt.octagon(pth.r - m)
            cbox = np.ascontiguousarray(pth.box + np.array([m, m, -m, -m]))
            spec = f.fc.targets.spec_of(pth.type_key) if hasattr(f.fc, "targets") else None
            out.append(_Target(np.ascontiguousarray(pth.box), np.ascontiguousarray(pth.ok), P0, S0, B0, cbox,
                               np.ascontiguousarray(pth.cert), P1, S1, B1, spec.recoil if spec else True,
                               pth.type_key))
        if not okb.any() and len(out) == 1:
            return []
        return out

    def warm_kernels(self) -> None:
        """Compile the hit-effect and prediction kernels and the lanes rollout before a fight: they run only when the
        boss is drawn and an attack is planned, and a first call mid-fight compiles past the oracle's 250 ms
        brain-lost watchdog (run 20261002_091133: 2 episodes paused unasked 6 s in)."""
        T1 = 49
        box = np.zeros((1, T1, 4))
        box[..., 2:] = 1.0
        fl = np.zeros((1, T1), np.int32)
        md = np.zeros((1, T1), np.int32)
        lat = np.zeros((1, T1 - 1), np.int64)
        boss = np.zeros((T1, 4))
        okb = np.ones(T1, np.bool_)
        polys = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]])
        starts = np.array([0, 3], np.int64)
        win = WINDOWS[self.cfg.attack_model]
        _first_hits(box, fl, md, lat, 1, boss, okb, polys, starts, np.zeros(2), np.full(1, -1, np.int64),
                    np.full(1, -1, np.int64), np.zeros(1, np.int64), win)
        _attacks_of(box[0], fl[0], md[0], lat[0], 1, boss, okb, polys, starts, np.zeros(2), win)
        start = kin.initial_state(self.params, 85.0, 2.015 + self.params.foot)
        kin.rollout(start, lat, self.params, self.terrain, events=np.zeros((1, T1 - 1), np.int64),
                    variants=self.cfg.variants, lanes=True)

    def _pogo_pick(self, cs, f: Forecast, start, T: int):
        """The fine pogo grid pruned by the boss's predicted path: the pogo_k grid rows whose spike frame finds the
        boss's predicted hurtbox nearest the hero in x (within 3 u), added to the tick's candidates."""
        if self.cfg.pogo_k <= 0:
            return cs
        if self._grid is None or self._grid[0].shape[1] < T:
            self._grid = cmod.pogo_grid(max(T, self.cfg.T_long))
        g_cmd, g_ts, g_names = self._grid
        tk = np.arange(T + 1, dtype=np.float64) * self.params.frame_time
        boss, okb = f.boss_box(tk)
        if not okb.any():
            return cs
        hx = float(np.asarray(start).reshape(kin.K, -1)[kin.PX, 0])
        ts = np.minimum(g_ts, T)
        cx = 0.5 * (boss[ts, 0] + boss[ts, 2])
        d = np.where(okb[ts], np.abs(cx - hx), np.inf)
        rows = np.flatnonzero(d < 3.0)
        if not len(rows):
            return cs
        rows = rows[np.argsort(d[rows], kind="stable")[:self.cfg.pogo_k]]
        return cmod.with_extra(cs, g_cmd[rows, :T], [g_names[r] for r in rows])

    # ---- prediction record (the attack-outcome audit) ---------------------------------------------------------------

    def _predict_attacks(self, f: Forecast, start, lat: np.ndarray, i: int, tk: np.ndarray, P: int) -> list:
        """Every attack of the chosen plan as [kind, start frame (from the forecast origin), predicted hit,
        p (share of the timing lanes that hit), hit frame (or the window's middle), predicted boss boxes there and
        0.25 / 0.5 s later, effect],
        on a lanes rollout of that one plan with its predicted hit events (ssbot.tools.predict_audit matches them to
        the recording). Kinds 1 side, 2 up, 3 down spike, 4 Silkspear; effects recoil / recoil_down / pogo / none."""
        boss, okb = f.boss_box(tk)
        polys, starts = f.body_polys()
        b0 = _box_of(polys) if len(polys) else (boss[0] if len(boss) else np.zeros(4))
        ev = self._fx_ev[i:i + 1] if self._fx_ev is not None and i < len(self._fx_ev) else None
        r = kin.rollout(start, lat[None], self.params, self.terrain, events=ev, variants=self.cfg.variants,
                        lanes=True)
        face0 = 1 if start.reshape(kin.K, -1)[kin.FACE, 0] >= 0 else -1
        V = r.var_box.shape[1]
        out = {}
        for v in range(V):
            lst = _attacks_of(np.ascontiguousarray(r.var_box[0, v]), np.ascontiguousarray(r.var_flags[0, v]),
                              np.ascontiguousarray(r.var_mode[0, v]), np.ascontiguousarray(lat), face0,
                              np.ascontiguousarray(boss, np.float64), np.ascontiguousarray(okb),
                              np.ascontiguousarray(polys, np.float64), np.ascontiguousarray(starts, np.int64),
                              np.array([b0[0], b0[1]]), WINDOWS[self.cfg.attack_model])
            for kind, k, j in lst:
                e = out.setdefault((int(kind), int(k)), [0, -1, 0])
                e[2] += 1
                if j >= 0:
                    e[0] += 1
                    if v == 0:
                        e[1] = int(j)
        rec = []
        for (kind, k), (nh, j0, n) in sorted(out.items(), key=lambda kv: kv[0][1]):
            jj = j0 if j0 >= 0 else min(k + {1: 3, 2: 5, 3: 8, 4: 18}[kind], len(boss) - 1)
            eff = ("recoil" if kind == 1 else "recoil_down" if kind == 2 else "pogo" if kind == 3 else "none") \
                if j0 >= 0 else "none"
            bxs = []
            for d in (0, 15, 30):          # the predicted boss box at the active frame, +0.25 s and +0.5 s
                q = min(jj + d, len(boss) - 1)
                bxs.append([round(float(x), 2) for x in boss[q]] if okb[q] and jj + d < len(boss) else None)
            rec.append([kind, k, j0 >= 0, round(nh / V, 2), jj, bxs, eff])
        return rec

    # ---- beyond the horizon ----------------------------------------------------------------------------------------

    def _lock_check(self, f: Forecast, roll, hold_end: HoldState, S: np.ndarray, T0: int, enemy_only: bool) -> None:
        """A plan still locked at the horizon's end (a Silkspear: M_CAST, about 73 frames, the hero hanging in the air)
        is safe only if the lock's remaining frames are: rolled on with no input for LOCK_EXTRA frames (gate run
        20261002_125420 i2 ep 8: air casts were S = 0 over the 48 frames ahead, a drop bell bounced into the hero 4
        frames after the lock ended, 60 frames after the press; replayed, all 42 cast candidates were safe 2 ticks
        before the press). S is updated in place."""
        rows = np.flatnonzero((roll.mode[:, -1] == M_CAST) & ~S)
        if not len(rows):
            return
        start = roll.final[:, rows]
        hs = HoldState(*(np.asarray(a)[rows] for a in (hold_end.latched, hold_end.desired, hold_end.pending,
                                                        hold_end.age)))
        latched, _ = hold_filter_jit(np.zeros((len(rows), LOCK_EXTRA), np.int64), hs)
        tr = kin.rollout(start, latched, self.params, self.terrain, variants=self.cfg.variants,
                         threads=self.cfg.threads)
        tk = (T0 + np.arange(LOCK_EXTRA + 1, dtype=np.float64)) * self.params.frame_time
        skip = ((tr.flags_all & F_INVULN) != 0) if enemy_only else np.zeros(tr.flags_all.shape, bool)
        # only the frames still in the lock and the few after it (the way on is the tail check's job)
        free = tr.mode != M_CAST
        free_at = np.where(free.any(axis=1), np.argmax(free, axis=1), LOCK_EXTRA + 1)
        upto = np.minimum(free_at + LOCK_AFTER, LOCK_EXTRA + 1)
        occ = self._contacts(f, tr.bound, tk, skip)
        occ &= np.arange(LOCK_EXTRA + 1)[None, :] < upto[:, None]
        S[rows] |= occ.any(axis=1)
        self.last_lock = (int(len(rows)), int(occ.any(axis=1).sum()))

    def _tail_pick(self, f: Forecast, roll, hold_end: HoldState, ranked: np.ndarray, T0: int, default: int
                   ) -> tuple[int, bool | None]:
        """V beyond the horizon: of the best tail_k safe candidates (in the lexicographic order), the first whose end
        state still has a safe way on over a further T frames (stay, run either way, a full jump in place or either
        way), so that a plan does not end where the next threat leaves no escape (live run 20261002_052118: a punish
        ended under a drop bell that bounced 1.2-2.8 s after arming, beyond the 0.8 s horizon). None of them: the
        default choice, flagged (tail_ok False)."""
        K = int(min(self.cfg.tail_k, len(ranked)))
        if K == 0:
            return default, None
        tails = self.tails
        nt = len(tails)
        tk = (T0 + np.arange(tails.shape[1] + 1, dtype=np.float64)) * self.params.frame_time
        for c0 in range(0, K, TAIL_CHUNK):          # the best first: usually the first chunk settles it
            rows = ranked[c0:min(K, c0 + TAIL_CHUNK)]
            k = len(rows)
            start = np.repeat(roll.final[:, rows], nt, axis=1)
            hs = HoldState(*(np.repeat(np.asarray(a)[rows], nt, axis=0)
                             for a in (hold_end.latched, hold_end.desired, hold_end.pending, hold_end.age)))
            latched, _ = hold_filter_jit(np.tile(tails, (k, 1)), hs)
            tr = kin.rollout(start, latched, self.params, self.terrain, variants=self.cfg.variants,
                             threads=self.cfg.threads)
            occ = self._contacts(f, tr.bound, tk, np.zeros((k * nt, tails.shape[1] + 1), bool))
            ok = (~occ.any(axis=1)).reshape(k, nt).any(axis=1)
            if ok.any():
                return int(rows[int(np.argmax(ok))]), True
        return default, False

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
        polys, starts = f.body_polys()
        base = np.array([boss[0, 0], boss[0, 1]]) if len(boss) else np.zeros(2)
        if len(polys):
            # boss_box moves the box along the mean path; the polygons move with it (offset from frame 0)
            b0 = _box_of(polys)
            base = np.array([b0[0], b0[1]])
        wv = np.array([w.get("hit", 10.0), w.get("waste", 0.6), w.get("jump", 0.15), w.get("stance", 0.6),
                       w.get("risk", 3.0), w.get("face", 0.3), w.get("ground", 0.2), w.get("cast_waste", 2.0)])
        boss_x = prefs.boss_x if prefs.boss_x is not None else np.nan
        max_hits = float(prefs.max_hits) if prefs.max_hits is not None else np.inf
        rx = prefs.risk_x if len(prefs.risk_x) else np.zeros(1)
        rv = prefs.risk if len(prefs.risk) else np.zeros(1)
        J = np.zeros(N)
        hits = np.zeros(N)
        near = np.zeros(N, np.bool_)
        first_hit = np.full(N, -1, np.int64)       # frame of the first attack scored as a hit (audit), its kind
        first_kind = np.zeros(N, np.int64)         # 1 side, 2 up, 3 down spike, 4 Silkspear
        _score_kernel(np.ascontiguousarray(roll.box), np.ascontiguousarray(roll.flags),
                      np.ascontiguousarray(roll.mode), np.ascontiguousarray(latched), face0,
                      np.ascontiguousarray(boss, np.float64), np.ascontiguousarray(okb), wv, float(prefs.stance_x),
                      np.ascontiguousarray(rx, np.float64), np.ascontiguousarray(rv, np.float64), boss_x, max_hits,
                      np.ascontiguousarray(polys, np.float64), np.ascontiguousarray(starts, np.int64),
                      np.ascontiguousarray(base, np.float64), J, hits, near, first_hit, first_kind,
                      WINDOWS[self.cfg.attack_model])
        self._audit = (first_hit, first_kind, boss)
        boss_hp = f.fc.tracker.ctx.hp
        may_kill = near if (boss_hp is not None and boss_hp <= SPEAR_DAMAGE) else np.zeros(N, bool)
        return J, hits, may_kill


SPEAR_DAMAGE = 15.0


def _box_of(polys: np.ndarray) -> tuple[float, float, float, float]:
    return float(polys[:, 0].min()), float(polys[:, 1].min()), float(polys[:, 0].max()), float(polys[:, 1].max())


@numba.njit(cache=True)
def _seg_hits_rect(x0, y0, x1, y1, rx0, ry0, rx1, ry1):
    # Liang-Barsky: does the segment (x0, y0)-(x1, y1) meet the rectangle?
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for pp, qq in ((-dx, x0 - rx0), (dx, rx1 - x0), (-dy, y0 - ry0), (dy, ry1 - y0)):
        if pp == 0.0:
            if qq < 0.0:
                return False
        else:
            r = qq / pp
            if pp < 0.0:
                if r > t1:
                    return False
                if r > t0:
                    t0 = r
            else:
                if r < t0:
                    return False
                if r < t1:
                    t1 = r
    return True


@numba.njit(cache=True)
def _rect_meets_polys(rx0, ry0, rx1, ry1, polys, starts, dx, dy):
    """The rectangle meets one of the polygons (moved by dx, dy): an edge crosses it or it lies inside one."""
    for p in range(len(starts) - 1):
        a, b = starts[p], starts[p + 1]
        inside = False
        cx, cy = 0.5 * (rx0 + rx1), 0.5 * (ry0 + ry1)
        j = b - 1
        for i in range(a, b):
            xi, yi = polys[i, 0] + dx, polys[i, 1] + dy
            xj, yj = polys[j, 0] + dx, polys[j, 1] + dy
            if _seg_hits_rect(xj, yj, xi, yi, rx0, ry0, rx1, ry1):
                return True
            if (yi > cy) != (yj > cy) and cx < (xj - xi) * (cy - yi) / (yj - yi) + xi:
                inside = not inside
            j = i
        if inside:
            return True
    return False


@numba.njit(cache=True, inline="always")
def _ov(cx, cy, face, fx0, fx1, y0, y1, b0, b1, b2, b3, polys, starts, dx, dy):
    if face > 0:
        ax0, ax1 = cx + fx0, cx + fx1
    else:
        ax0, ax1 = cx - fx1, cx - fx0
    if not (ax0 < b2 and ax1 > b0 and cy + y0 < b3 and cy + y1 > b1):
        return False
    if len(starts) < 2:
        return True
    return _rect_meets_polys(ax0, cy + y0, ax1, cy + y1, polys, starts, dx, dy)


@numba.njit(cache=True)
def _attacks_of(box, flags, mode, lat, face0, boss, okb, polys, starts, base, win):
    """One lane's attacks: (kind, start frame, hit frame or -1), windows and boxes as in _score_kernel."""
    T1 = mode.shape[0]
    out = []
    face = face0
    fc = np.empty(T1, np.int64)
    fc[0] = face
    for k in range(1, T1):
        m = lat[k - 1]
        d = 1 if m & B_RIGHT else (-1 if m & B_LEFT else 0)
        if d != 0:
            starts_cast = mode[k] == M_CAST and mode[k - 1] != M_CAST
            free = mode[k - 1] == M_NORMAL and (flags[k - 1] & F_ATTACKING) == 0
            if starts_cast or free:
                face = d
        fc[k] = face
    for k in range(1, T1):
        att = (flags[k] & F_ATTACKING) != 0 and (flags[k - 1] & F_ATTACKING) == 0
        dsk = mode[k] == M_DS_SPIKE and mode[k - 1] != M_DS_SPIKE
        cst = mode[k] == M_CAST and mode[k - 1] != M_CAST
        if not (att or dsk or cst):
            continue
        hit = -1
        if att:
            up = (lat[k - 1] & B_UP) != 0
            kind = 2 if up else 1
            w0, w1 = (win[1, 0], win[1, 1]) if up else (win[0, 0], win[0, 1])
            g = UP if up else SIDE
        elif dsk:
            kind, w0, w1, g = 3, 0, (8 if win[2, 1] == 0 else win[2, 1]), DOWN
        else:
            kind, w0, w1, g = 4, win[3, 0], win[3, 1], SPEAR
        for j in range(k + w0, min(T1, k + w1)):
            if kind == 3 and win[2, 1] == 0 and mode[j] != M_DS_SPIKE:
                continue
            if not okb[j]:
                continue
            cx = 0.5 * (box[j, 0] + box[j, 2])
            cy = 0.5 * (box[j, 1] + box[j, 3])
            bx = boss[j]
            if _ov(cx, cy, fc[j], g[0], g[1], g[2], g[3], bx[0], bx[1], bx[2], bx[3], polys, starts, bx[0] - base[0],
                   bx[1] - base[1]):
                hit = j
                break
        out.append((kind, k, hit))
    return out


MACRO_MARGIN = 5.0             # J (half a hit) another plan needs over a started macro to replace it


def _is_macro(name: str) -> bool:
    return "_hop" in name or "_ds" in name or name.startswith("POGO+")


@numba.njit(cache=True, parallel=True)
def _lanes_connect(var_box, var_flags, var_mode, lat, face0, boss, okb, polys, starts, base, win, out):
    """Per candidate: the first down spike meets the boss's predicted hurtbox in every timing lane (the pogo gate),
    compiled: the Python loop over candidates and lanes cost about 0.1 ms a candidate."""
    n, V = var_box.shape[0], var_box.shape[1]
    for c in numba.prange(n):
        ok = True
        for v in range(V):
            lst = _attacks_of(var_box[c, v], var_flags[c, v], var_mode[c, v], lat[c], face0, boss, okb, polys,
                              starts, base, win)
            got = False
            seen = False
            for kd, _k, j in lst:
                if kd == 3:
                    seen = True
                    got = j >= 0
                    break
            if not (seen and got):
                ok = False
                break
        out[c] = ok


class _Target:
    """Something an attack can hit in the rollout, in the kernels' form: per-frame box [T, 4] and ok [T], the shape's
    polygons around base (moved by box - base); c*: the certain form the pogo gate uses."""

    def __init__(self, box, ok, polys, starts, base, cbox=None, cok=None, cpolys=None, cstarts=None, cbase=None,
                 recoil: bool = True, name: str = "boss"):
        self.box, self.ok, self.polys, self.starts, self.base = box, ok, polys, starts, base
        self.cbox = box if cbox is None else cbox
        self.cok = ok if cok is None else cok
        self.cpolys = polys if cpolys is None else cpolys
        self.cstarts = starts if cstarts is None else cstarts
        self.cbase = base if cbase is None else cbase
        self.recoil, self.name = recoil, name


class _View:
    """The parts of a Rollout the scoring reads, for a rollout patched with hit branches."""

    def __init__(self, box, flags, mode, bound, flags_all):
        self.box, self.flags, self.mode, self.bound, self.flags_all = box, flags, mode, bound, flags_all


@numba.njit(cache=True, parallel=True)
def _first_hits(box, flags, mode, latched, face0, boss, okb, polys, starts, base, after, hit_f, kind, win):
    """Per candidate, the first frame after `after` at which an attack's active box meets the boss's predicted
    hurtbox (windows as in _score_kernel), and its kind: 0 side slash facing left, 1 facing right, 2 up-slash,
    3 down spike; -1 none. Silkspear hits move nothing."""
    N, T1 = mode.shape
    for c in numba.prange(N):
        face = face0
        fc = np.empty(T1, np.int64)
        fc[0] = face
        for k in range(1, T1):
            m = latched[c, k - 1]
            d = 1 if m & B_RIGHT else (-1 if m & B_LEFT else 0)
            if d != 0:
                starts_cast = mode[c, k] == M_CAST and mode[c, k - 1] != M_CAST
                free = mode[c, k - 1] == M_NORMAL and (flags[c, k - 1] & F_ATTACKING) == 0
                if starts_cast or free:
                    face = d
            fc[k] = face
        done = False
        for k in range(1, T1):
            if done:
                break
            att = (flags[c, k] & F_ATTACKING) != 0 and (flags[c, k - 1] & F_ATTACKING) == 0
            dsk = mode[c, k] == M_DS_SPIKE
            if not (att or dsk):
                continue
            if att:
                up = (latched[c, k - 1] & B_UP) != 0
                w0, w1 = (win[1, 0], win[1, 1]) if up else (win[0, 0], win[0, 1])
                for j in range(k + w0, min(T1, k + w1)):
                    if j <= after[c] or not okb[j]:
                        continue
                    cx = 0.5 * (box[c, j, 0] + box[c, j, 2])
                    cy = 0.5 * (box[c, j, 1] + box[c, j, 3])
                    bx = boss[j]
                    if up:
                        ok = _ov(cx, cy, fc[j], UP[0], UP[1], UP[2], UP[3], bx[0], bx[1], bx[2], bx[3], polys, starts,
                                 bx[0] - base[0], bx[1] - base[1])
                    else:
                        ok = _ov(cx, cy, fc[j], SIDE[0], SIDE[1], SIDE[2], SIDE[3], bx[0], bx[1], bx[2], bx[3], polys,
                                 starts, bx[0] - base[0], bx[1] - base[1])
                    if ok:
                        hit_f[c] = j
                        kind[c] = 2 if up else (1 if fc[j] > 0 else 0)
                        done = True
                        break
            elif k > after[c] and okb[k]:
                cx = 0.5 * (box[c, k, 0] + box[c, k, 2])
                cy = 0.5 * (box[c, k, 1] + box[c, k, 3])
                bx = boss[k]
                if _ov(cx, cy, fc[k], DOWN[0], DOWN[1], DOWN[2], DOWN[3], bx[0], bx[1], bx[2], bx[3], polys, starts,
                       bx[0] - base[0], bx[1] - base[1]):
                    hit_f[c] = k
                    kind[c] = 3
                    done = True


@numba.njit(cache=True, parallel=True)
def _score_kernel(box, flags, mode, latched, face0, boss, okb, wv, stance_x, rx, rv, boss_x, max_hits, polys, starts,
                  base, J, hits, near, first_hit, first_kind, win):
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
                # the kinematics' facing rule: a direction key turns the hero only in normal movement outside an
                # attack, or as a cast starts (the throw goes the held way); a cast, an attack, a dive and the hurt
                # modes keep it (an earlier version turned with every key, so a cast away from the boss followed by a
                # run towards it scored the spear's three hits: run 20261002_064001, 123 casts away, none hit)
                m = latched[c, k - 1]
                d = 1 if m & B_RIGHT else (-1 if m & B_LEFT else 0)
                if d != 0:
                    starts_cast = mode[c, k] == M_CAST and mode[c, k - 1] != M_CAST
                    free = mode[c, k - 1] == M_NORMAL and (flags[c, k - 1] & F_ATTACKING) == 0
                    if starts_cast or free:
                        face = d
            fc[k] = face
            cxs[k] = 0.5 * (box[c, k, 0] + box[c, k, 2])
            cys[k] = 0.5 * (box[c, k, 1] + box[c, k, 3])
        h = 0.0
        presses = 0
        jumps = 0
        dry_casts = 0
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
                w0, w1 = (win[1, 0], win[1, 1]) if up else (win[0, 0], win[0, 1])
                for j in range(k + w0, min(T1, k + w1)):
                    if not okb[j]:
                        continue
                    bx = boss[j]
                    ddx, ddy = bx[0] - base[0], bx[1] - base[1]
                    if up:
                        if _ov(cxs[j], cys[j], fc[j], UP[0], UP[1], UP[2], UP[3], bx[0], bx[1], bx[2], bx[3], polys,
                               starts, ddx, ddy):
                            got = True
                    elif _ov(cxs[j], cys[j], fc[j], SIDE[0], SIDE[1], SIDE[2], SIDE[3], bx[0], bx[1], bx[2], bx[3],
                             polys, starts, ddx, ddy):
                        got = True
                    if _ov(cxs[j], cys[j], fc[j], SIDE[0] - 1.0, SIDE[1] + 1.0, SIDE[2] - 1.0, SIDE[3] + 1.0, bx[0],
                           bx[1], bx[2], bx[3], polys, starts, ddx, ddy):
                        nr = True
                if got:
                    h += 1.0
                    if first_hit[c] < 0:
                        first_hit[c], first_kind[c] = k, 2 if up else 1
            elif dsk:
                for j in range(k, min(T1, k + (16 if win[2, 1] == 0 else win[2, 1]))):
                    if (win[2, 1] != 0 or mode[c, j] == M_DS_SPIKE) and okb[j] and _ov(cxs[j], cys[j], fc[j], DOWN[0], DOWN[1], DOWN[2], DOWN[3], boss[j, 0],
                                      boss[j, 1], boss[j, 2], boss[j, 3], polys, starts, boss[j, 0] - base[0],
                                      boss[j, 1] - base[1]):
                        got = True
                        nr = True
                if got:
                    h += 1.0
                    if first_hit[c] < 0:
                        first_hit[c], first_kind[c] = k, 3
            else:
                for j in range(k + win[3, 0], min(T1, k + win[3, 1])):
                    if okb[j] and _ov(cxs[j], cys[j], fc[j], SPEAR[0], SPEAR[1], SPEAR[2], SPEAR[3], boss[j, 0],
                                      boss[j, 1], boss[j, 2], boss[j, 3], polys, starts, boss[j, 0] - base[0],
                                      boss[j, 1] - base[1]):
                        got = True
                        break
                if got:
                    h += 3.0
                    nr = True
                    if first_hit[c] < 0:
                        first_hit[c], first_kind[c] = k, 4
                else:
                    dry_casts += 1
        h = min(h, max_hits)
        waste = max(presses - h, 0.0)
        x_end = cxs[T1 - 1]
        r = np.interp(x_end, rx, rv)
        # distance to the stance over the whole horizon, not only at its end: "wait, then run there" re-planned every
        # frame never gets there (live run 20261002_032738: the hero stood 4 u short of every Leap Land punish)
        d_mean = 0.0
        for k in range(T1):
            d_mean += abs(cxs[k] - stance_x)
        d_mean /= T1
        v = (wv[0] * h - wv[1] * waste - wv[2] * jumps - wv[3] * (0.5 * abs(x_end - stance_x) + 0.5 * d_mean)
             - wv[4] * r - wv[7] * dry_casts)
        if boss_x == boss_x:
            want = 1 if boss_x > x_end else -1
            if fc[T1 - 1] == want:
                v += wv[5]
        if flags[c, T1 - 1] & F_GROUND:
            v += wv[6]
        J[c] = v
        hits[c] = h
        near[c] = nr
