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
  U         safety_filter.unpausable: a possible killing blow (safety_filter.kill_frames: every damaging press at its
            attack's bound, combat.hero_damage) outside I3 and not certified safe through the kill kind's slow motion
            (safety_filter.kill_certified); vetoed (R_KILL) when the candidate's own presses may kill, ranked when only
            a blow already sent may (in flight: the certified plans first); the chosen plan's kill goes out as
            PlanResult.kill (KillPlan), which the policy keeps through the slow motion by game time.
  idle      PlanResult.idle_clear: frames after the decision frame the no-input candidate stays out of the support
            (the pause machine's keys replace the plan's while a pause is on its way; supervisor QS's safe frame).
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
from ssbot.combat.safety_filter import (R_KILL, REASONS, FilterContext, hazard_flags, i3_kill_allowed, kill_certified,
                                        kill_frames, kill_window_frames, released_rise, unpausable, veto)
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
# The down spike's damage collider itself (Attacks/Default/DownSlash, damager 0, crests.json P17, same frame as DOWN):
# a diagonal sliver from the hero's back-top to a forward-low tip. DOWN, the clash polygon's bounding box, covers 0.5-1 u
# behind and below it where nothing hits: live check 20261002_152649 (tools/attack_shape_audit), spikes whose DOWN met
# the boss's collider without a hit came within 0.39-0.49 u of it with this polygon (head-on dives over the boss's
# back: the planner pressed too high and the spike ended before the real shape reached the boss).
DOWN_POLY = np.array([[-0.58, 0.32], [-0.671, -0.467], [0.544, -1.536], [1.599, -2.195], [1.155, -1.069],
                      [0.479, 0.21]])
DOWN_BOX = (float(DOWN_POLY[:, 0].min()), float(DOWN_POLY[:, 0].max()), float(DOWN_POLY[:, 1].min()),
            float(DOWN_POLY[:, 1].max()))
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
LOCK_MODES = np.array([kin.M_CAST, kin.M_BIND, kin.M_LOCKED])   # committed locks a plan chooses
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
    kill: "KillPlan | None" = None          # the chosen plan may land a killing blow (its own or one in flight)
    path_hit: np.ndarray | None = None      # the chosen candidate's box per frame where its predicted hits land
    path_kill: tuple | None = None          # ... where its killing hit lands, earliest / latest (Planner._kill_branches)
    idle_clear: int | None = None           # frames after the decision frame the no-input path stays out of the
    #                                         support (the pause machine's keys; supervisor QS), None: no such candidate


@dataclass(frozen=True)
class KillPlan:
    """The chosen plan's killing blow: own (its presses, else one already sent), certified safe through the slow motion
    (safety_filter.kill_certified), i3 (entered uncertified under I3), the rollout frames [k_lo, k_hi] the blow can
    land in (frame k applies latched[:, k - 1]; P prefix frames) and the window frames the plan stays S = 0 after k_hi.
    The policy keeps a certified plan through the slow motion by game time (train.planner_policy)."""
    own: bool
    certified: bool
    i3: bool
    k_lo: int
    k_hi: int
    window: int
    P: int


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
        self.last_kill = (0, 0, 0, 0)   # this tick's plans that may kill, of them certified, vetoed (R_KILL), and
        #                                 the plans with a blow in flight only (ranked by U, not vetoed)
        self.last_pogo = 0            # candidates with a predicted bounce in the last tick
        self.last_recoil = 0          # ... with a predicted nail recoil
        self.last_bell_pogo = 0       # ... bouncing off a registry target (a bell)
        self._pogo_ok = np.zeros(0, bool)
        self._redirect: dict[int, tuple] = {}
        self.pogo_log = {"generated": 0, "lane_miss": 0, "accepted": 0}   # last tick's pogo plans: every lane
        #                                                                     connects or rejected (S)
        self.jump_until = -1          # tick until which the pressed jump's hold schedule is committed
        self.macro_until = -1         # tick until which a started macro (pogo chain) is kept (MACRO_MARGIN)
        self.prev_tail_ok = False

    # ---- S -----------------------------------------------------------------------------------------------------------

    def _contacts(self, f: Forecast, bound: np.ndarray, tk: np.ndarray, skip: np.ndarray, comfort: bool = False,
                  exclude: str | None = None, redirect: tuple | None = None) -> np.ndarray | None:
        """[N, T1] contact of the lanes' hull with the support. A hull a point covers (the templates are dilated by
        the hurtbox plus the margin) is tested at its centre; a wider one at a grid of 2 points along each wide axis
        (sub-boxes the dilation covers), wider still counts as contact. One query: the first point of every frame,
        plus extra layers for the rows with a wide frame (NaN where a frame needs fewer points: skipped)."""
        hx, hy = f.fc.half
        X, Y, rows, too_wide = _hull_points(np.ascontiguousarray(bound), hx, hy, self.cfg.max_points)
        if redirect is not None:
            hit = f.occupied_redirect(X, Y, tk, *redirect, comfort=comfort)
            if hit is None:
                return None
        else:
            hit = f.occupied(X, Y, tk, comfort) if exclude is None else f.occupied_without(X, Y, tk, exclude)
        N = bound.shape[0]
        occ = hit[:N].copy()
        if len(rows):
            occ[rows] |= hit[N:].reshape(-1, len(rows), hit.shape[1]).any(axis=0)
        occ |= too_wide
        occ &= ~skip
        occ[:, 0] = False
        return occ

    def _contacts_redirect(self, f: Forecast, bound: np.ndarray, tk: np.ndarray, skip: np.ndarray, params: list,
                           comfort: bool = False) -> tuple[np.ndarray, np.ndarray]:
        """_contacts for rows that each knock a drop bell aside, params[i] = (bell type key, hit time, direction):
        the support without that bell (one query per bell for all its rows) plus its one redirected path (one per
        distinct hit). Returns contact [n, T1] and applicable [n] (False: the bell is not on an exact path; those rows
        keep their both-sides contact). One call per row cost 0.6 ms (occupied_redirect: 11,771 calls in an
        8,000-tick bench of live run 20261002_162847, tick p99 33 ms with up to ~30 such rows a tick)."""
        hx, hy = f.fc.half
        X, Y, rows, too_wide = _hull_points(np.ascontiguousarray(bound), hx, hy, self.cfg.max_points)
        n = bound.shape[0]
        R = len(rows)
        L = (X.shape[0] - n) // R if R else 0
        own = np.concatenate([np.arange(n), np.tile(rows, L)]) if R else np.arange(n)
        hit = np.zeros(X.shape, bool)
        appl = np.ones(n, bool)
        keys = [p[0] for p in params]
        for name in set(keys):
            mine = np.array([k == name for k in keys])
            pts = np.flatnonzero(mine[own])
            hit[pts] = f.occupied_without(X[pts], Y[pts], tk, name, comfort)
            for th, d in {(p[1], p[2]) for p in params if p[0] == name}:
                rsel = np.array([p[0] == name and p[1] == th and p[2] == d for p in params])
                p2 = np.flatnonzero(rsel[own])
                o = f.redirect_occ(X[p2], Y[p2], tk, name, th, d, comfort)
                if o is None:
                    appl[rsel] = False
                else:
                    hit[p2] |= o
        occ = hit[:n].copy()
        if R:
            occ[rows] |= hit[n:].reshape(-1, R, hit.shape[1]).any(axis=0)
        occ |= too_wide
        occ &= ~skip
        occ[:, 0] = False
        return occ, appl

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
        th0 = time.perf_counter()
        roll_j = self._hit_effects(f, start, latched, roll, tk, S, enemy_only)
        self._ambiguous_bells(f, latched, roll_j, start, tk, S)
        self._no_cast_out_of_spike(latched, roll, roll_j, S)
        th1 = time.perf_counter()
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
        J, hits, _near = self._score(ws, roll_j, latched, start, f, prefs, P, tk)
        if cont:
            J[-1] += prefs.weights.get("cont", 0.0)
        tr0 = time.perf_counter()
        if self._redirect:
            self._redirect_value(f, roll_j, tk, J, S, S2, ctx, prefs, enemy_only, min(T1, COMFORT_FRAMES + P + 1))
        tr1 = time.perf_counter()
        # the killing blow (safety_filter U / KILL): every press may land at its attack's bound, and a plan whose own
        # presses may kill passes only under I3 (GREEN, full HP, h >= 3) or certified safe through the slow motion (a
        # hard veto); a blow already sent (the prefix, a running attack) is not the candidate's doing: U ranks those
        # candidates, the certified ones first, so the plan kept through the slow motion is a certified one
        may_kill, _k_lo, k_hi, in_flight = kill_frames(latched, roll.flags, roll.mode, P, ctx)
        cert = kill_certified(S, k_hi, T1, ctx, params.frame_time, k_lo=_k_lo, vel_y=roll.vel[:, :, 1],
                              latched=latched)
        if cert.any() and roll_j is not roll and getattr(roll_j, "vel", None) is not None:
            # the hit branch too (a killing down spike's bounce, a slash's recoil): no released rise in either
            cert &= kill_certified(S, k_hi, T1, ctx, params.frame_time, k_lo=_k_lo, vel_y=roll_j.vel[:, :, 1],
                                   latched=latched)
        kill_paths = {}
        self.last_kill_branches = (0, 0)    # plans whose killing hit's branches were rolled out, of them still certified
        if cert.any():
            cert = self._kill_branches(f, start, latched, roll, cert, _k_lo, k_hi, ctx, J, tk, enemy_only, kill_paths)
        U = unpausable(may_kill | in_flight, ctx, cert)
        veto_k = U & may_kill
        if veto_k.any():
            why[ok & veto_k] = R_KILL
            ok = ok & ~veto_k
        self.last_kill = (int(may_kill.sum()), int((may_kill & cert).sum()), int(veto_k.sum()), int(in_flight.sum()))
        # the no-input path (the pause machine's keys while a pause is on its way): first contact after the prefix
        zero = ~cmd.any(axis=1)
        idle_clear = int(min(t_hit[zero].min(), T1) - P) if zero.any() else None
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
            if roll_j is not roll:
                res.path_hit = roll_j.box[i].copy()      # the branch where the predicted hits land
            if i in kill_paths:
                res.path_kill = kill_paths[i]            # the killing hit's own branches (earliest, latest)
            if may_kill[i] or in_flight[i]:
                res.kill = KillPlan(own=bool(may_kill[i]), certified=bool(cert[i]), i3=i3_kill_allowed(ctx),
                                    k_lo=int(_k_lo[i]), k_hi=int(k_hi[i]),
                                    window=kill_window_frames(params.frame_time, ctx.kill_window_s), P=P)
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
        res.idle_clear = idle_clear
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
                    "total": (t6 - t0) * 1e3, "hit_fx": (th1 - th0) * 1e3, "redirect": (tr1 - tr0) * 1e3}
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

    def _kill_branches(self, f: Forecast, start, latched: np.ndarray, roll, cert: np.ndarray, k_lo: np.ndarray,
                       k_hi: np.ndarray, ctx: FilterContext, J: np.ndarray, tk: np.ndarray, enemy_only: bool,
                       paths: dict) -> np.ndarray:
        """The killing hit's own effect on the hero, for the plans the filter would certify: whatever the boss model
        predicts, a kill means the killing press landed, and a landed hit moves the hero (a side slash recoils her
        away from where she faces, 3.75 u/s for 9 physics steps, overriding her keys; an up-slash stops her rise; a
        down spike bounces her). _hit_effects rolls that out only where the predicted hurtbox meets the attack; the
        rest kept the no-hit path, which the hero did not follow (live 20261004_042718 i0 ep 0: certified, the
        killing slash's recoil carried her 1.9 u from the plan through the slow motion). Here every such plan is
        rolled out twice more, with the killing attack's effect on its earliest and on its latest hit frame
        (kill_hit_events), and stays certified only if both branches are out of the support (S, the plan's own
        rollout frames) with no released rise. At most KILL_BRANCH_K plans (the best by J, the carried plan first)
        are checked; the others lose the certificate (unknown is never safe). paths[i]: the branches' boxes."""
        rows = np.flatnonzero(cert)
        N, T = latched.shape
        if len(rows) > KILL_BRANCH_K:
            pri = J[rows] + np.where(rows == N - 1, 1e9, 0.0)
            keep = rows[np.argsort(-pri, kind="stable")[:KILL_BRANCH_K]]
            cert = cert.copy()
            cert[np.setdiff1d(rows, keep)] = False
            rows = np.sort(keep)
        face0 = 1 if start.reshape(kin.K, -1)[kin.FACE, 0] >= 0 else -1
        ev = np.zeros((2, len(rows), T), np.int64)
        kill_hit_events(np.ascontiguousarray(latched[rows]), np.ascontiguousarray(roll.flags[rows]),
                        np.ascontiguousarray(roll.mode[rows]), face0, np.asarray(k_lo, np.int64)[rows],
                        WINDOWS[self.cfg.attack_model], ev)
        ok = np.ones(len(rows), bool)
        W = kill_window_frames(self.params.frame_time, ctx.kill_window_s)
        boxes = []
        for b in range(2):
            moved = ev[b].any(axis=1)
            if not moved.any():
                boxes.append(None)
                continue
            sub = np.flatnonzero(moved)
            rl = kin.rollout(start, latched[rows[sub]], self.params, self.terrain, events=ev[b][sub],
                             variants=self.cfg.variants, threads=self.cfg.threads)
            skip = ((rl.flags_all & F_INVULN) != 0) if enemy_only else np.zeros(rl.flags_all.shape, bool)
            occ = self._contacts(f, rl.bound, tk, skip)
            bad = occ.any(axis=1)
            bad |= released_rise(rl.vel[:, :, 1], latched[rows[sub]], np.asarray(k_lo, np.int64)[rows[sub]],
                                 np.asarray(k_hi, np.int64)[rows[sub]] + W)
            ok[sub] &= ~bad
            bx = np.full((len(rows),) + rl.box.shape[1:], np.nan)
            bx[sub] = rl.box
            boxes.append(bx)
        out = cert.copy()
        out[rows] &= ok
        for n_, c in enumerate(rows):
            paths[int(c)] = tuple(None if bx is None or np.isnan(bx[n_]).all() else bx[n_].copy() for bx in boxes)
        self.last_kill_branches = (int(len(rows)), int(ok.sum()))
        return out

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
        self.last_redirect = 0
        self.redirect_rows: list[int] = []        # rows whose side slash knocks a drop bell aside (audits, J)
        self._redirect: dict[int, tuple] = {}     # ... their (bell type key, hit time, direction)
        self.side_bell_rows = 0                   # rows whose first side slash meets a bell at all
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
        cur = _View(roll.box, roll.flags, roll.mode, roll.bound, roll.flags_all, roll.vel)
        after = np.full(N, -1, np.int64)
        rows_all = np.zeros(N, bool)
        pogo_tgt = np.full(N, -1, np.int64)      # the target of a row's first predicted bounce (0: the boss)
        side_tgt = np.full(N, -1, np.int64)      # ... of its first side slash hit, its frame and direction
        side_f = np.full(N, -1, np.int64)
        side_d = np.zeros(N, np.int64)
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
                if g.pogo_ok is not None:
                    # a pogo where it does not count (a rising drop bell, VE): no hit, the miss branch stands
                    hf[(kd == 3) & (hf >= 0) & ~g.pogo_ok[np.clip(hf, 0, len(g.pogo_ok) - 1)]] = -1
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
            sr = rows[(k <= 1) & (side_tgt[rows] < 0)]
            side_tgt[sr], side_f[sr], side_d[sr] = tsel[sr], hit_f[sr], np.where(kind[sr] == 1, 1, -1)
            self.last_pogo += int((k == 3).sum())
            self.last_bell_pogo += int(((k == 3) & (tsel[rows] > 0)).sum())
            self.last_recoil += int((k <= 1).sum())
            after[rows] = hit_f[rows]
            rows_all[rows] = True
            sub = np.flatnonzero(rows_all)
            rh = kin.rollout(start, latched[sub], self.params, self.terrain, events=ev[sub],
                             variants=self.cfg.variants, threads=self.cfg.threads)
            box, flags, mode = cur.box.copy(), cur.flags.copy(), cur.mode.copy()
            bound, fall, vel = cur.bound.copy(), cur.flags_all.copy(), cur.vel.copy()
            box[sub], flags[sub], mode[sub], bound[sub], fall[sub] = rh.box, rh.flags, rh.mode, rh.bound, rh.flags_all
            vel[sub] = rh.vel
            cur = _View(box, flags, mode, bound, fall, vel)
        self._fx_ev = ev
        self.side_bell_rows = int((side_tgt > 0).sum())
        sub = np.flatnonzero(rows_all)
        s_hit = np.zeros(N, bool)
        if len(sub):
            skip = ((cur.flags_all[sub] & F_INVULN) != 0) if enemy_only else np.zeros(cur.flags_all[sub].shape, bool)
            occ = self._contacts(f, cur.bound[sub], tk, skip)
            # a down attack that met a bell disarms it for damage_cooldown_s (HeroDownAttack.ContinueBounceTrigger ->
            # DamageHero.SetCooldown(0.5); side and up tinks do not): from the bounce frame on, that bell's own
            # placements do not count for that long
            for ti in np.unique(pogo_tgt[sub]):
                g = tgts[int(ti)] if ti > 0 else None
                if g is None or g.cooldown_s <= 0:
                    continue
                r = np.flatnonzero(pogo_tgt[sub] == ti)
                occ_x = self._contacts(f, cur.bound[sub[r]], tk, skip[r], exclude=g.name)
                b0 = np.argmax((ev[sub[r]] & kin.EV_POGO) != 0, axis=1)
                # (named cool, not win: win is the attack windows the pogo lane gate below reads; reusing the name
                # handed _lanes_connect this bool mask as its windows after a bell pogo, out-of-bounds reads in a
                # compiled kernel; found by a cold-cache replay: _lanes_connect compiled for win bool[:, :])
                cool = ((np.arange(tk.shape[0])[None, :] >= b0[:, None]) &
                        (tk[None, :] <= tk[b0][:, None] + g.cooldown_s))
                occ[r] = np.where(cool, occ_x, occ[r])
            # a side slash on a drop bell knocks it away from the hitter (TINK): its support is its one redirected
            # path instead of both bounce sides (Forecast.occupied_redirect); the slash's own safety as usual
            self.last_redirect = 0
            self.redirect_rows = []
            red = [n_ for n_ in np.flatnonzero(side_tgt[sub] > 0) if tgts[int(side_tgt[sub[n_]])].redirect]
            if len(red) > REDIRECT_K:
                # the earliest hits first (the rest keep both bounce sides: their S is the conservative one)
                red = sorted(red, key=lambda n_: int(side_f[sub[n_]]))[:REDIRECT_K]
            if red:
                red = np.asarray(red, np.int64)
                cs_ = sub[red]
                prm = [(tgts[int(side_tgt[c])].name, float(tk[min(side_f[c], len(tk) - 1)]), int(side_d[c]))
                       for c in cs_]
                o, appl = self._contacts_redirect(f, cur.bound[cs_], tk, skip[red], prm)
                for i_, (n_, c) in enumerate(zip(red, cs_)):
                    if appl[i_]:
                        occ[n_] = o[i_]
                        self.last_redirect += 1
                        self.redirect_rows.append(int(c))
                        self._redirect[int(c)] = prm[i_]
            s_hit[sub] = occ.any(axis=1)
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
                buckets = getattr(g, "buckets", None)
                if buckets is None:
                    _lanes_connect(np.ascontiguousarray(rl.var_box[idx]), np.ascontiguousarray(rl.var_flags[idx]),
                                   np.ascontiguousarray(rl.var_mode[idx]), np.ascontiguousarray(latched[pg[idx]]),
                                   face0, g.cbox, g.cok, g.cpolys, g.cstarts, g.cbase, win, cn)
                else:
                    # the certain form of the bucket that covers the row's bounce (+ BUCKET_SLACK frames for the
                    # lanes' spread); rows bouncing beyond the last bucket, or with no form at all, are rejected
                    kb0 = np.argmax((ev[pg[idx]] & kin.EV_POGO) != 0, axis=1) + BUCKET_SLACK
                    done = np.zeros(len(idx), bool)
                    for kb, cbox, cok, cp, cst, cbs in buckets:
                        sel = np.flatnonzero(~done & (kb0 <= kb))
                        if not len(sel):
                            continue
                        done[sel] = True
                        cs_ = np.zeros(len(sel), np.bool_)
                        _lanes_connect(np.ascontiguousarray(rl.var_box[idx[sel]]),
                                       np.ascontiguousarray(rl.var_flags[idx[sel]]),
                                       np.ascontiguousarray(rl.var_mode[idx[sel]]),
                                       np.ascontiguousarray(latched[pg[idx[sel]]]), face0, cbox, cok, cp, cst, cbs,
                                       win, cs_)
                        cn[sel] = cs_
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

    def _ambiguous_bells(self, f: Forecast, latched: np.ndarray, roll, start, tk: np.ndarray, S: np.ndarray) -> None:
        """VE: a drop bell whose track has tinked branches open (bell_track: the hero attacked it and the detections
        do not tell yet) is no hit target, so what a new attack would do to it is not modelled: a plan whose attack
        (slash, up-slash or down spike, in its windows) meets the bell on any of its branches is not safe (S)."""
        amb = f.ambiguous_paths(tk) if hasattr(f, "ambiguous_paths") else []
        self.last_ambiguous = 0
        if not amb:
            return
        flags = roll.flags
        if not (((flags & F_ATTACKING) != 0).any() or (roll.mode == M_DS_SPIKE).any()):
            return
        face0 = 1 if start.reshape(kin.K, -1)[kin.FACE, 0] >= 0 else -1
        win = WINDOWS[self.cfg.attack_model]
        N = len(latched)
        cb, cf, cm = (np.ascontiguousarray(roll.box), np.ascontiguousarray(flags), np.ascontiguousarray(roll.mode))
        lat = np.ascontiguousarray(latched)
        for _name, paths in amb:
            for box, ok in paths:
                r = 0.5 * float(box[0, 2] - box[0, 0])
                P0, S0, B0 = pt.octagon(r)
                hf = np.full(N, -1, np.int64)
                kd = np.zeros(N, np.int64)
                _first_hits(cb, cf, cm, lat, face0, box, ok, P0, S0, B0, np.full(N, -1, np.int64), hf, kd, win)
                hit = hf >= 0
                self.last_ambiguous += int(hit.sum())
                S |= hit

    def _no_cast_out_of_spike(self, latched: np.ndarray, roll, roll_j, S: np.ndarray) -> None:
        """A Silkspear pressed during a down spike (its antic or the spike) or within CAST_AFTER_POGO frames of a
        predicted pogo is not modelled against the game: there the queued cast starts at the hit and cancels the bounce,
        and the hero hangs in the cast's antic at the boss's height (live run 20261002_162847: all 17 hits in Charge End
        came 5-10 frames after a pogo hit, the hero in NeedleThrow AnticA over the boss; quickcast pressed 2 frames
        before the hit, the bounce never came). Such plans count as unsafe (S)."""
        qc = (latched & B_QUICKCAST) != 0
        if not qc.any():
            return
        ds = (roll.mode[:, :-1] == M_DS_ANTIC) | (roll.mode[:, :-1] == M_DS_SPIKE)
        if roll_j is not roll:
            ds |= (roll_j.mode[:, :-1] == M_DS_ANTIC) | (roll_j.mode[:, :-1] == M_DS_SPIKE)
        bad = (qc & ds).any(axis=1)
        ev = self._fx_ev
        if ev is not None and ev.shape == latched.shape:
            pg = (ev & kin.EV_POGO) != 0
            if pg.any():
                near = np.zeros_like(pg)
                for k in range(-2, CAST_AFTER_POGO + 1):
                    if k >= 0:
                        near[:, k:] |= pg[:, :pg.shape[1] - k]
                    else:
                        near[:, :k] |= pg[:, -k:]
                bad |= (qc & near).any(axis=1)
        S |= bad
        self.last_cast_vetoed = int(bad.sum())

    def _redirect_value(self, f: Forecast, roll_j, tk: np.ndarray, J: np.ndarray, S: np.ndarray, S2: np.ndarray,
                        ctx: FilterContext, prefs: TacticPrefs, enemy_only: bool, tc: int) -> None:
        """What knocking a falling drop bell aside is worth (the person, 2026-10-02: hitting a bell shrinks the danger
        zone; the bot only ever dodged them). For each safe redirect candidate:
        - comfort is checked against the bell's one redirected path, not both bounce sides (against both, every
          redirect lost the comfort rank to plans that keep clearance from the side the bell no longer takes);
        - J gains bell_free (playbook weight, default 8; doubled outside GREEN: at h <= 2 freeing room matters more)
          times the share of probe points near the hero (her x -4.5 .. +4.5 u every 1.5 u and the stance, at her
          height and 3 u above, every 3 frames from the hit to the horizon's end) that the both-sides support
          covers and the redirected one does not.
        FORCED_RISK turned into a safe plan needs no bonus: S = 0 ranks first. J and S2 are updated in place."""
        w = prefs.weights.get("bell_free", 8.0) * (1.0 if ctx.tier == "GREEN" else 2.0)
        cache: dict = {}
        safe_rows = [c for c in self._redirect if c < len(S) and not S[c]]
        if safe_rows:
            cs_ = np.asarray(safe_rows, np.int64)
            sk = (((roll_j.flags_all[cs_, :tc] & F_INVULN) != 0) if enemy_only else np.zeros((len(cs_), tc), bool))
            o, appl = self._contacts_redirect(f, roll_j.bound[cs_, :tc], tk[:tc], sk,
                                              [self._redirect[c] for c in safe_rows], comfort=True)
            S2[cs_[appl]] = o[appl].any(axis=1)
        if not safe_rows:
            return
        # the probe grid is the same for every row (frame 0 is the start state): the rest of the support and the
        # bell's both-sides occupancy once per bell, its redirected path once per hit
        b0 = roll_j.box[safe_rows[0], 0]
        cx, cy = 0.5 * (b0[0] + b0[2]), 0.5 * (b0[1] + b0[3])
        xs = np.concatenate([cx + np.arange(-4.5, 4.6, 1.5), [prefs.stance_x]])
        tq = tk[::3]
        X = np.repeat(np.concatenate([xs, xs])[:, None], len(tq), axis=1)
        Y = np.repeat(np.concatenate([np.full(len(xs), cy), np.full(len(xs), cy + 3.0)])[:, None], len(tq), axis=1)
        per_bell: dict = {}
        for c in safe_rows:
            name, t_hit, d = self._redirect[c]
            key = (name, int(round(t_hit * 60)), d)
            if key not in cache:
                if name not in per_bell:
                    rest = f.occupied_without(X, Y, tq, name)
                    per_bell[name] = f._det_occ(X, Y, tq, only=name) & ~rest
                one = f.redirect_occ(X, Y, tq, name, t_hit, d)
                after = tq >= t_hit
                cache[key] = 0.0 if one is None or not after.any() else                     float((per_bell[name] & ~one)[:, after].mean())
            J[c] += w * cache[key]

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
        # vision view: the pogo gate checks the boss eroded by the measured box residuals, per horizon bucket
        bt.buckets = f.certain_boss(bt.box, bt.ok, bt.polys, bt.starts, tk) if hasattr(f, "certain_boss") else None
        out.append(bt)
        paths = f.target_paths(tk) if hasattr(f, "target_paths") else []
        for pth in paths:
            P0, S0, B0 = pt.octagon(pth.r)
            m = getattr(pth, "cert_margin", pt.CERT_MARGIN_U)
            P1, S1, B1 = pt.octagon(pth.r - m)
            cbox = np.ascontiguousarray(pth.box + np.array([m, m, -m, -m]))
            spec = f.fc.targets.spec_of(pth.type_key) if hasattr(f.fc, "targets") else None
            t_ = _Target(np.ascontiguousarray(pth.box), np.ascontiguousarray(pth.ok), P0, S0, B0, cbox,
                         np.ascontiguousarray(pth.cert), P1, S1, B1, spec.recoil if spec else True,
                         pth.type_key, spec.cooldown_s if spec else 0.0,
                         bool(spec and "side" in spec.redirect and getattr(pth, "redirect", True)))
            po = getattr(pth, "pogo_ok", None)
            t_.pogo_ok = None if po is None else np.asarray(po, bool)
            out.append(t_)
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
        rl = kin.rollout(start, lat, self.params, self.terrain, events=np.zeros((1, T1 - 1), np.int64),
                         variants=self.cfg.variants, lanes=True)
        # the killing hit's branch events (Planner._kill_branches), with the rollout's own dtypes
        kill_hit_events(np.ascontiguousarray(lat), np.ascontiguousarray(rl.flags), np.ascontiguousarray(rl.mode), 1,
                        np.ones(1, np.int64), win, np.zeros((2, 1, T1 - 1), np.int64))
        # the pogo lane gate and the hit kernels with a bell's octagon too: a fresh checkout has no numba cache, and
        # these compiled mid-fight past the watchdog (live run 20261002_162847 from a new worktree: 2-3 episodes per
        # worker "paused unasked", in the first charge and in a burst)
        from ssbot.combat.fastquery import circle_hits      # drop bells on exact paths (forecast._det_occ)
        z = np.zeros((1, 2))
        circle_hits(z, z, z, z, np.ones((1, 2), np.bool_), 0.5, 1.0, 1.0)
        P0, S0, B0 = pt.octagon(1.274)
        for pp, ss, bb in ((polys, starts, np.zeros(2)), (P0, S0, B0)):
            pp, ss, bb = (np.ascontiguousarray(pp, np.float64), np.ascontiguousarray(ss, np.int64),
                          np.ascontiguousarray(bb, np.float64))
            cn = np.zeros(1, np.bool_)
            _lanes_connect(np.ascontiguousarray(rl.var_box), np.ascontiguousarray(rl.var_flags),
                           np.ascontiguousarray(rl.var_mode), np.ascontiguousarray(lat), 1, boss, okb, pp, ss, bb,
                           win, cn)
            _first_hits(box, fl, md, lat, 1, boss, okb, pp, ss, bb, np.full(1, -1, np.int64),
                        np.full(1, -1, np.int64), np.zeros(1, np.int64), win)

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
        """A committed lock (LOCK_MODES: a Silkspear cast, about 73 frames with the hero hanging in the air; the Bind;
        other locks) must be safe until it ends + LOCK_AFTER frames, from every tick that can choose it: a plan whose
        lock reaches past the horizon's end - LOCK_AFTER is rolled on with no input (LOCK_EXTRA frames) and checked
        that far (gate run 20261002_125420 i2 ep 8: air casts were S = 0 over the 48 frames ahead, a drop bell bounced
        into the hero 4 frames after the lock ended, 60 frames after the press; replayed, all 42 cast candidates were
        safe at the press tick, and 21 two ticks earlier, whose modelled lock ended inside the horizon). Getting away
        after the lock is the tail check's. S is updated in place."""
        mode = roll.mode
        T1 = mode.shape[1]
        lockm = np.isin(mode, LOCK_MODES)
        anyl = lockm.any(axis=1)
        last = np.where(anyl, T1 - 1 - np.argmax(lockm[:, ::-1], axis=1), -1)
        rows = np.flatnonzero(anyl & (last >= T1 - 1 - LOCK_AFTER) & ~S)
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
        free = ~np.isin(tr.mode, LOCK_MODES)
        free_at = np.where(free.any(axis=1), np.argmax(free, axis=1), LOCK_EXTRA + 1)
        still = lockm[rows, -1]
        upto = np.where(still, free_at + LOCK_AFTER, last[rows] + LOCK_AFTER - (T1 - 1) + 1)
        upto = np.minimum(upto, LOCK_EXTRA + 1)
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
            for j, c in enumerate(rows):
                # a plan that knocked a drop bell aside goes on against its one redirected path
                rd = self._redirect.get(int(c))
                if rd is not None:
                    o = self._contacts(f, tr.bound[j * nt:(j + 1) * nt], tk,
                                       np.zeros((nt, tails.shape[1] + 1), bool), redirect=rd)
                    if o is not None:
                        occ[j * nt:(j + 1) * nt] = o
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
        # near: an attack starts with the boss within 1 u of its box (audits only). The killing-blow rule no longer
        # reads it: it counted SPEAR_DAMAGE = 15 for every attack (a nail hit is 5 with the Hunter crest) and missed
        # up-slashes above the side box; safety_filter.kill_frames bounds every press instead (2026-10-04)
        return J, hits, near


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
def _cross(ax, ay, bx, by, cx, cy):
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


@numba.njit(cache=True)
def _segs_meet(ax, ay, bx, by, cx, cy, dx, dy):
    """Segments AB and CD meet (touching counts)."""
    d1 = _cross(cx, cy, dx, dy, ax, ay)
    d2 = _cross(cx, cy, dx, dy, bx, by)
    d3 = _cross(ax, ay, bx, by, cx, cy)
    d4 = _cross(ax, ay, bx, by, dx, dy)
    if d1 * d2 > 0.0 or d3 * d4 > 0.0:
        return False
    if d1 == 0.0 and d2 == 0.0:              # collinear: their extents must overlap
        return (min(ax, bx) <= max(cx, dx) and min(cx, dx) <= max(ax, bx) and min(ay, by) <= max(cy, dy)
                and min(cy, dy) <= max(ay, by))
    return True


@numba.njit(cache=True)
def _inside(px, py, q, a, b, dx, dy):
    """Point inside polygon q[a:b] moved by (dx, dy) (ray casting)."""
    inside = False
    j = b - 1
    for i in range(a, b):
        xi, yi = q[i, 0] + dx, q[i, 1] + dy
        xj, yj = q[j, 0] + dx, q[j, 1] + dy
        if (yi > py) != (yj > py) and px < (xj - xi) * (py - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


@numba.njit(cache=True)
def _poly_meets_polys(P, polys, starts, dx, dy):
    """Polygon P [m, 2] meets one of the polygons (moved by dx, dy): an edge pair crosses or one lies inside."""
    m = P.shape[0]
    for p in range(len(starts) - 1):
        a, b = starts[p], starts[p + 1]
        for i in range(m):
            i2 = (i + 1) % m
            j = b - 1
            for k in range(a, b):
                if _segs_meet(P[i, 0], P[i, 1], P[i2, 0], P[i2, 1], polys[j, 0] + dx, polys[j, 1] + dy,
                              polys[k, 0] + dx, polys[k, 1] + dy):
                    return True
                j = k
        if _inside(P[0, 0], P[0, 1], polys, a, b, dx, dy):
            return True
        if _inside(polys[a, 0] + dx, polys[a, 1] + dy, P, 0, m, 0.0, 0.0):
            return True
    return False


@numba.njit(cache=True)
def _ov_down(cx, cy, face, b0, b1, b2, b3, polys, starts, dx, dy):
    """The down spike's damage polygon (DOWN_POLY, mirrored with the facing) at the hurtbox centre meets the target:
    its bounding box against the target's box first, then the polygons (a target without polygons: the box)."""
    if face > 0:
        ax0, ax1 = cx + DOWN_BOX[0], cx + DOWN_BOX[1]
    else:
        ax0, ax1 = cx - DOWN_BOX[1], cx - DOWN_BOX[0]
    if not (ax0 < b2 and ax1 > b0 and cy + DOWN_BOX[2] < b3 and cy + DOWN_BOX[3] > b1):
        return False
    if len(starts) < 2:
        return True
    P = np.empty((DOWN_POLY.shape[0], 2))
    for i in range(DOWN_POLY.shape[0]):
        P[i, 0] = cx + face * DOWN_POLY[i, 0]
        P[i, 1] = cy + DOWN_POLY[i, 1]
    return _poly_meets_polys(P, polys, starts, dx, dy)


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
            if kind == 3:
                got = _ov_down(cx, cy, fc[j], bx[0], bx[1], bx[2], bx[3], polys, starts, bx[0] - base[0],
                               bx[1] - base[1])
            else:
                got = _ov(cx, cy, fc[j], g[0], g[1], g[2], g[3], bx[0], bx[1], bx[2], bx[3], polys, starts,
                          bx[0] - base[0], bx[1] - base[1])
            if got:
                hit = j
                break
        out.append((kind, k, hit))
    return out


MACRO_MARGIN = 5.0             # J (half a hit) another plan needs over a started macro to replace it
CAST_AFTER_POGO = 12           # frames after a predicted pogo in which a Silkspear press counts as unsafe
REDIRECT_K = 12                # side-slash-on-a-drop-bell rows scored on the redirected path per tick (earliest hits)
BUCKET_SLACK = 3               # vision view's pogo gate: frames added to a row's nominal bounce to pick its margin


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
                 recoil: bool = True, name: str = "boss", cooldown_s: float = 0.0, redirect: bool = False):
        self.box, self.ok, self.polys, self.starts, self.base = box, ok, polys, starts, base
        self.cbox = box if cbox is None else cbox
        self.cok = ok if cok is None else cok
        self.cpolys = polys if cpolys is None else cpolys
        self.cstarts = starts if cstarts is None else cstarts
        self.cbase = base if cbase is None else cbase
        self.recoil, self.name, self.cooldown_s, self.redirect = recoil, name, cooldown_s, redirect
        self.pogo_ok: np.ndarray | None = None    # [T] where a down spike's hit counts (None: wherever ok)


class _View:
    """The parts of a Rollout the scoring reads, for a rollout patched with hit branches."""

    def __init__(self, box, flags, mode, bound, flags_all, vel=None):
        self.box, self.flags, self.mode, self.bound, self.flags_all = box, flags, mode, bound, flags_all
        self.vel = vel          # [N, T1, 2] nominal lane (the killing blow's released-rise check reads both branches)


@numba.njit(cache=True)
def kill_hit_events(latched, flags, mode, face0, k_lo, win, ev):
    """ev[0 / 1, c, :]: the killing attack's hit effect on its earliest / latest hit frame (Planner._kill_branches):
    the attack whose onset is the first at or after k_lo - 1 (an attack already out at the start: frame 1), side
    slash EV_RECOIL_L facing right / EV_RECOIL_R facing left on onset + win[0] .. + win[0, 1] - 1, up-slash
    EV_RECOIL_DOWN on onset + win[1], down spike EV_POGO on its first and last spike frame; a cast (the Silkspear)
    moves nothing. The facing follows the keys as in _first_hits. Frame k's event goes in column k - 1."""
    n, T = latched.shape
    T1 = mode.shape[1]
    for c in range(n):
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
        k0 = max(1, k_lo[c] - 1)
        on, kind = -1, -1
        if k_lo[c] <= 1 and ((flags[c, 0] & F_ATTACKING) != 0 or mode[c, 0] == M_DS_SPIKE or mode[c, 0] == M_DS_ANTIC):
            on = 0
            kind = 2 if mode[c, 0] == M_DS_SPIKE or mode[c, 0] == M_DS_ANTIC else 0
        else:
            for k in range(k0, T1):
                if mode[c, k] == M_CAST and mode[c, k - 1] != M_CAST:
                    break                                    # a cast: no movement effect
                if (flags[c, k] & F_ATTACKING) != 0 and (flags[c, k - 1] & F_ATTACKING) == 0:
                    on = k
                    kind = 1 if (latched[c, k - 1] & B_UP) != 0 else 0
                    break
                if mode[c, k] == M_DS_SPIKE and mode[c, k - 1] != M_DS_SPIKE:
                    on = k
                    kind = 2
                    break
        if on < 0:
            continue
        if kind == 2:
            k1 = on
            while k1 + 1 < T1 and mode[c, k1 + 1] == M_DS_SPIKE:
                k1 += 1
            lo, hi, bit = max(on, 1), max(k1, 1), EV_POGO_
        elif kind == 1:
            lo, hi, bit = on + win[1, 0], on + win[1, 1] - 1, EV_RECOIL_DOWN_
        else:
            lo, hi = on + win[0, 0], on + win[0, 1] - 1
            bit = EV_RECOIL_L_ if fc[min(max(on, 0), T1 - 1)] > 0 else EV_RECOIL_R_
        lo, hi = max(lo, 1), max(hi, max(lo, 1))
        if lo <= T:
            ev[0, c, lo - 1] |= bit
        if hi <= T:
            ev[1, c, hi - 1] |= bit


EV_POGO_, EV_RECOIL_DOWN_, EV_RECOIL_L_, EV_RECOIL_R_ = (int(kin.EV_POGO), int(kin.EV_RECOIL_DOWN),
                                                         int(kin.EV_RECOIL_L), int(kin.EV_RECOIL_R))
KILL_BRANCH_K = 12            # plans whose killing hit's branches are rolled out (Planner._kill_branches)


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
                if _ov_down(cx, cy, fc[k], bx[0], bx[1], bx[2], bx[3], polys, starts, bx[0] - base[0],
                            bx[1] - base[1]):
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
                    if (win[2, 1] != 0 or mode[c, j] == M_DS_SPIKE) and okb[j] and _ov_down(
                            cxs[j], cys[j], fc[j], boss[j, 0], boss[j, 1], boss[j, 2], boss[j, 3], polys, starts,
                            boss[j, 0] - base[0], boss[j, 1] - base[1]):
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
