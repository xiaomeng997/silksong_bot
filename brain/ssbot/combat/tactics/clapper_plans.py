"""The two-Clapper jump plans (Task 182; default off, SSBOT_FORUM_TWO_PLAN=1): snapshot, generator, foreground adapter.

generate() is pure: a Request (the bodies, the move's clock, the hero's hand-back prediction and her committed keys) goes
in, a complete immutable l2_plan.Plan comes out. It runs in the resident worker (l2_plan_worker) and reads nothing of
the policy. It never reads her current ground flag or can.input: what she can do follows from the model roll of her
committed keys (Hand) and of simple key rows from there; the action owners keep every real key check.

Her hand-back is the model's AND her key owner's: the keys a B2 or script owner has committed are part of the roll; an owner whose
release cannot be told makes the hand-back unknown, never a free hero (Sol seq 255 A). Every route rolls on from the state she is
predicted to leave from, with its speed, air and resources. A guide, the way under and the retreat are driven by the action layer's
bounded approach (knife_chain_waypoint), which sends what these rolls count on.

Two parent scenes, each with its own options (design: docs/plans/forum_clapper_l2_tactics.md):
  middle   she is clearly between the two bodies, exactly one in a jump's antic / flight: stay (the nearest sufficient
           guide point, or none needed, then back to slash the walker on the observed take-off), under, over; the
           normal choice is made in the aim and the fallback for a walker that closes the gap is prepared with it.
  cluster  she is outside both bodies with no standing gap between them, exactly one in a jump's antic: lure (back off to a sufficient interval, return under
           on the observed take-off) and attack (slash the reachable one, retreat past the coverage, come back once the
           hazards are over), chosen by the public selector.

PlanRunner is the foreground: non-blocking result read and checks, the executor's events and stance references, and the
event-driven requests (no period: first antic, a support range left, a new move, no plan left while time remains).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
import os
import time

import numpy as np

from ssbot.combat import jump_behind as JB, knife_chain_waypoint as WP
from .l2_plan import BLOCKED, DONE, HANDBACK, INVALID, Candidate, Phase, Plan, PlanExecutor, Range

ENABLED = os.environ.get("SSBOT_FORUM_TWO_PLAN", "0").strip() == "1"
# Offline determinism only: the plan appears this many ticks after its request, in this process (replays, tests).
INLINE = os.environ.get("SSBOT_FORUM_TWO_PLAN_INLINE", "").strip()

JUMPS = {"CC_JUMP", "CC_JUMP_CAST"}
AIR = {"Jump", "Air"}
ANTIC = {"Jump Antic", "Cast Slam Antic", "Cast Slam Antic 2"}
NEAR = {"Slam Antic", "Spell Antic"}
PRIMARY = {"CC_JUMP": "Jump Antic", "CC_JUMP_CAST": "Cast Slam Antic"}
ATTACK_FAMS = {"CC_SLAM", "CC_CAST", "CC_JUMP", "CC_JUMP_CAST"}
# The walker states the over route's stomp is declared for (clapper_middle's existing list)
STANDING = {"Idle", "Walk", "Spell Antic", "Cast 1", "Cast 2", "Slam Recover"}
# Its ordinary reaction to being hit (knife_chain_air_v01 rune_transfer target_states; the hit frame itself, T 3147 / 3339: Idle)
REACTION = {"Dmg Attack", "Close Range", "Evade Scuttle"}
EVADE = "Evade Scuttle"
FOLLOW_UP = ("stay", "over")   # Task 182 seq 311 (the person 11-09): after the press only these two: back in the middle, or over the second one
PRESS_OVER = "the press is over"     # why a press's follow-up is requested
PRESS_WAIT_S = .6            # the take-off -> the follow-up in force at the latest: the rest of a walker's slide, then a result; past it the generic rules go on (its flight is 0.916 s)

LOCK_S = {"CC_JUMP": .48, "CC_JUMP_CAST": .88}   # the antic's start -> the earliest aim lock
GAIN = .916                 # the flight: x_land - x = 0.916 vx (are_types.clapper.JUMP_GAIN)
FLIGHT_S = GAIN
DESCENT_S = 50 / 60.        # take-off -> its body's bottom comes down to a standing head (jump_behind walk_end_f)
CROSS_S = .75               # a real bounce at its near edge -> the far stance above its body, at a run (exp_cross: 40-45 frames)
SWEEP_S = 5 / 60.           # ... and from there to the landing: the slanted descent behind the landing is vx x this
BODY_BACK_U = 1.34          # its back edge behind its centre in the air (recordings: root + 1.34 facing left)
RESERVE_S = .10             # the guide's arrival before the earliest lock (the design's reserve)
GUIDE_MARGIN_U = .25        # the guide point inside the sufficient interval's end
ARRIVE_U = .35              # at a stance (no ground claim)
WALK_LOOK_S = .25           # a walker's closing counted past the observation (a bounded allowance, no displacement bound)
SOFT_WALKER_U = 1.0         # a walker inside this of the plan's prediction for it asks for no update
HARD_WALKER_U = 8.0         # ... an aim-stage plan this far off its prediction no longer holds
SOFT_HAND_U = 1.5           # a hand-back x inside this of the plan's asks for no update
REQUEST_STEP_U = .5         # an update asked again only after this much more change
PEND_MAX_S = .25            # the scene is held for a result this long; after that the generic rules go on
ROLL_T = 200                # model frames of a route roll
HAND_T = 90                 # model frames scanned for her hand-back
ROUTE_TOL_U = .2
MAX_START_MOVES = 6         # as l2_plan.MAX_MOVES
LAND_SUPPORT_U = 3.0        # an observed landing this far from every landing the plan was made for is outside its support
RUN_ROW_U = 36 * JB.CFG["walk_v"]   # the planner's rows (36 frames) reach a stance this near at a run: no dash is chosen for it
BODY_TOP = 6.92             # a standing Clapper's body top (recordings: its collider's top; the x span is observed)
BODY_HALF = 2.25            # ... and its reach from the root in either pose (Idle / Walk bodies, recordings)
RUNE_ON_S, RUNE_OVER_S = 65 / 60., (65 + 17) / 60.    # the landing -> the big rune hurts (are_types: on0, its long window)
HIT_TAIL_S = 1.0            # a plan's validity past the last hazard, for its return phases
# The jumper attacks again while its rune is still due: these phases keep her off it and go on (the new threat takes its turn by the
# public priorities); a way back to the middle not yet made is handed on, never counted as done.
RUNE_WAITS = frozenset({"over_head", "over_wait", "over_stay", "over_out", "return", "attack_retreat"})
RETURN_OWED = frozenset({"over_head", "over_wait", "over_stay", "over_out", "over_back"})


def _rune_reach() -> float:
    from ssbot.combat.are_types.clapper import SPEC
    h = next(h for h in SPEC.hazards if h.name == "rune slam")
    return float(max(h.du_by_face)) + float(h.box_w) / 2.


RUNE_REACH_U = _rune_reach()  # 6.75 + 7.187 = 13.937: the wider side of both facings


@dataclass(frozen=True)
class Body:
    iid: int
    x: float
    vx: float
    a: float                  # the observed standing body's horizontal span
    b: float
    state: str | None
    family: str | None


@dataclass(frozen=True)
class Hand:
    """Her predicted legal hand-back: the first model frame after her committed keys and locked motion that takes input."""
    t: float
    x: float
    vx: float
    index: int                # the rollout index of that frame
    known: bool


@dataclass(frozen=True)
class HeroInput:
    """What the policy gives L2 for this tick (the same objects the planner gets, before the planner runs)."""
    S0: object
    prefix: object
    hold: object
    params: object
    terrain: object
    commit: tuple | None = None   # (owner, release known, keys past the in-flight prefix): already in prefix when known
    bounce: int | None = None     # the Clapper of this frame's real strike bounce (hit and pogo evidence), or None
    t0_ns: int | None = None      # when the policy took this STATE (the latency's origin)


@dataclass(frozen=True)
class Request:
    scene: str
    stage: str                # aim / flight
    instance: tuple
    generation: int
    t: float
    jumper: Body
    other: Body
    side: int                 # cluster: the outward direction (+1 right of them)
    antic_at: float | None
    air_at: float | None
    land: float | None        # flight: the observed landing estimate
    land_vx: float | None
    face: int | None          # flight: the observed facing of the jump
    hand: Hand
    left: float
    right: float
    xa: float
    xb: float
    gap_u: float
    pad: float
    face_u: float
    reach_j: float
    S0: object
    prefix: object
    hold: object
    routes: tuple | None = None   # Task 182 seq 311: the only candidates this request may choose (a press's follow-up); None: all of the scene's
    other_antic_at: float | None = None   # ... the other one's own aim clock (its antic's start) when it is aiming a jump of its own at such a follow-up


class Roller:
    """Model rolls of command rows from the mask frame f + 2 on, after her keys in flight (air_chain.ChainSim.roll)."""

    def __init__(self, S0, prefix, hold, params, terrain):
        from ssbot.knowledge import kinematics as kin
        from ssbot.combat.holdfilter import hold_filter_jit
        self.kin, self._hf = kin, hold_filter_jit
        self.start = np.asarray(S0, np.float64).reshape(-1)
        self.prefix = np.asarray(prefix, np.int64).reshape(-1)
        self.hold, self.params, self.terrain = hold, params, terrain
        self.dt = float(params.frame_time)
        self.off = len(self.prefix) + 1

    def rollout(self, rows):
        rows = np.asarray(rows, np.int64)
        n, _ = rows.shape
        full = np.concatenate([np.broadcast_to(self.prefix, (n, len(self.prefix))), rows], axis=1)
        lat, _ = self._hf(np.ascontiguousarray(full), self.hold)
        return self.kin.rollout(self.start, lat, self.params, self.terrain)

    def xs(self, rows):
        return self.rollout(rows).centre[:, :, 0]


def _keys():
    from ssbot.combat.knife_chain_format import MASK_NAMES as B
    return B["L"], B["R"], B["DASH"]


def hand_back(m: Roller, t: float, fallback_x: float, owner_known: bool = True) -> Hand:
    """The first frame her committed keys and locked motion leave to new keys (no key after the committed ones). An owner whose
    release cannot be told: unknown, not a free hero."""
    kin = m.kin
    if not owner_known:
        return Hand(math.inf, float(fallback_x), 0., m.off, False)
    r = m.rollout(np.zeros((1, HAND_T), np.int64))
    mode, flags = r.mode[0], r.flags[0]
    locked = np.isin(mode, (kin.M_DASH, *kin.RELINQUISHED, *kin.NO_INPUT)) | ((flags & (kin.F_RELINQ | kin.F_NO_INPUT)) != 0)
    j = None
    if int(mode[m.off]) == kin.M_SPRINT:
        # a ground sprint is steerable now (knife_chain_air_native._dash_lock_scan: phase 2 on the ground)
        n = m.rollout(np.zeros((1, 1), np.int64)).final
        k_mode = n[kin.MODE].reshape(-1)[0]
        if int(k_mode) == kin.M_SPRINT and int(n[kin.PHASE].reshape(-1)[0]) == 2 and n[kin.GROUND].reshape(-1)[0] > 0:
            j = m.off
    if j is None:
        free = np.flatnonzero(~locked[m.off:])
        if not len(free):
            return Hand(math.inf, float(fallback_x), 0., m.off, False)
        j = m.off + int(free[0])
    return Hand(t + j * m.dt, float(r.centre[0, j, 0]), float(r.vel[0, j, 0]), int(j), True)


def go(m: Roller, row, k0: int, goal: float, tol: float = ROUTE_TOL_U, run_only: bool = False):
    """Extend a key row toward goal from command index k0, as the planner goes to a stance: a run inside one row's run, else
    the faster of a run and a dash (cooldown, air and turn are the model's). run_only: the run alone. (row, arrival command
    index), or (row, None) when neither arrives inside the row."""
    x = m.xs(row[None])[0]
    i0 = m.off + k0
    if i0 >= x.shape[0]:
        return row, None
    if abs(goal - x[i0]) <= tol:
        return row, k0
    if run_only or abs(goal - x[i0]) <= RUN_ROW_U:
        d = 1 if goal > x[i0] else -1
        run = row.copy()
        run[k0:] = WP._key(d)
        a = WP._arrival(m.xs(run[None])[0][i0:], goal, d, tol)
        if a is None:
            return row, None
        run[k0 + a:] = 0
        return run, k0 + a
    out, k, _ = WP.route(m, row, k0, goal, tol=tol)
    return out, k


def stand_x(land, f, reach, w_a, w_b, w_x, left, right, pad, gap_u, face_u, shift=0.):
    """A hero-centre x beyond the jump's forward coverage and short of the walker's body (shift: the walker's closing, in
    world x), or None (clapper_middle._standing's interval, its reach given)."""
    end = land + f * reach
    a, b = w_a + shift, w_b + shift
    if f > 0:
        raw = a - end - 2 * pad
        lo, hi = end + pad + left, a - pad - right
    else:
        raw = end - b - 2 * pad
        lo, hi = b + pad + left, end - pad - right
    if raw < max(gap_u, left + right) or lo > hi:
        return None
    return min(hi, max(lo, w_x + shift - f * face_u))


def _hmax(j, limit, f, xa, xb):
    """The aim-time hero x at or short of which the landing stays at or short of limit (f coordinates: larger is nearer
    the walker). None: no aim does; math.inf * f: every aim does (the 12 u/s saturation)."""
    wall_min = JB.wall_rule(j, j - f * 99., f)          # the landing never comes closer to the wall behind it than this
    if (limit - wall_min) * f < 0:
        return None
    if (limit - (j + f * GAIN * 12.)) * f >= 0:
        return math.inf * f
    v = (limit - j) * f / GAIN
    if v < -12.:
        return None
    return j + f * (5. + v)


def _land(j, h, f):
    return JB.landing(j, h, f)


def _vx_of(j, h, f):
    return max(-12., min(12., h - 5. * f - j))


class _Middle:
    """The numbers every option of one middle request shares."""

    def __init__(self, q: Request, m: Roller):
        self.q, self.m = q, m
        J, W = q.jumper, q.other
        self.f = f = 1 if W.x > J.x else -1
        self.cast = J.family == "CC_JUMP_CAST"
        self.reach = RUNE_REACH_U if self.cast else q.reach_j
        self.aim = q.stage == "aim"
        self.lock = q.antic_at + LOCK_S[J.family] if (self.aim and q.antic_at is not None) else None
        self.t_to = (self.lock if self.lock is not None else q.t + .1) if self.aim else (q.air_at if q.air_at is not None else q.t)
        self.land_t = self.t_to + FLIGHT_S
        self.hazard_end = self.land_t + (RUNE_OVER_S if self.cast else 5 / 60.)
        closing = W.vx if (W.state == "Walk" and W.vx * f < 0) else 0.
        self.closing = closing
        self.shift = closing * max(0., self.t_to - q.t)
        self.w_x = W.x + self.shift
        self.w_in = (W.a if f > 0 else W.b) + self.shift
        self.half_w = q.right if f > 0 else q.left       # her half width on the walker's side
        self.half_j = q.left if f > 0 else q.right       # ... on the jumper's side
        self.need = self.reach + 2 * q.pad + max(q.gap_u, q.left + q.right)
        self.limit = self.w_in - f * self.need
        self.h_lo = (J.b if f > 0 else J.a) + f * (self.half_j + q.pad)
        self.w_front = self.w_in - f * (self.half_w + q.pad)
        self.front = min(self.w_front * f, (self.w_x - f * q.face_u) * f) * f
        self.k_hand = max(0, q.hand.index - m.off)
        self.k_take = max(0, int(math.ceil((self.t_to - q.t) / m.dt)) - m.off)
        self.hmax = _hmax(J.x, self.limit, f, q.xa, q.xb) if self.aim else None

    def t_of(self, k):
        return self.q.t + (self.m.off + k) * self.m.dt

    def k_of(self, t):
        return max(0, int(math.ceil((t - self.q.t) / self.m.dt)) - self.m.off)

    def keys_to_take(self, aim_x):
        """Her keys through the aim stage: toward aim_x from her hand-back as the rows go, none past the take-off."""
        row = np.zeros(ROLL_T, np.int64)
        if aim_x is not None:
            row, _ = go(self.m, row, self.k_hand, aim_x)
            row = row.copy()
            row[self.k_take:] = 0
        return row

    def start_x(self, aim_x):
        """Where her model path has come to at the take-off."""
        if aim_x is None:
            return self.q.hand.x
        x = self.m.xs(self.keys_to_take(aim_x)[None])[0]
        return float(x[min(len(x) - 1, self.m.off + self.k_take)])

    def leg(self, aim_x, goal, by_t=None):
        """The route after the observed take-off, rolled on from the state she is predicted to leave from (speed, air, cooldown,
        her hand-back if she is locked past the take-off). by_t: the bounded approach's own choice for that deadline; None:
        the rows' way. (row, arrival key index, seconds from the take-off) or None."""
        row = self.keys_to_take(aim_x)
        k0 = max(self.k_take, self.k_hand)
        if by_t is not None:
            out, k, _ = WP.route(self.m, row, k0, goal, by_k=self.k_of(by_t))
        else:
            out, k = go(self.m, row, k0, goal)
        if k is None:
            return None
        return out, k, self.t_of(k) - self.t_to

    def route(self, aim_x, goal, depart_k=None):
        """Her model path: to the guide from depart_k by the bounded approach, or nothing, then to goal from the take-off.
        (row, k_aim, k_goal)."""
        row = np.zeros(ROLL_T, np.int64)
        k_aim = None
        if aim_x is not None:
            row, k_aim, _ = WP.route(self.m, row, self.k_hand if depart_k is None else depart_k, aim_x,
                                     by_k=None if self.lock is None else self.k_of(self.lock - RESERVE_S))
        if k_aim is None or k_aim > self.k_take:
            row = row.copy()
            row[self.k_take:] = 0
        k0 = max(self.k_take, k_aim if k_aim is not None else self.k_take, self.k_hand)
        if goal is None:
            return row, k_aim, None
        row, k_goal = go(self.m, row, k0, goal)
        return row, k_aim, k_goal


def _stay(c: _Middle):
    """(Candidate, facts). Aim: the nearest sufficient point from her predicted hand-back, or none needed (an absolute
    latest departure, attacks legal before it). Take-off: back to slash the walker."""
    q, f, m = c.q, c.f, c.m
    J, W = q.jumper, q.other
    det = dict(limit=c.limit, reach=c.reach, closing=c.closing, walker_x=c.w_x, hand_x=q.hand.x, hand_t=q.hand.t)

    def no(reason):
        return Candidate("stay", False, reason, None, 1., tuple(det.items())), None

    if W.family in ATTACK_FAMS and not _second_aiming(q):
        return no("walker in an attack move")
    if not q.hand.known:
        return no("hand-back unknown")
    if (J.x - q.xa if f > 0 else q.xb - J.x) < JB.CFG["push_from_u"]:
        # A wall push lands it at least that far out: a lower bound, no middle stance is claimed beyond it (live 786).
        return no("wall landing is only a bound")
    if not c.aim:
        land = q.land
        if land is None:
            return no("landing unknown")
        stand = stand_x(land, f, c.reach, W.a, W.b, W.x, q.left, q.right, q.pad, q.gap_u, q.face_u,
                        c.closing * WALK_LOOK_S)
        if stand is None:
            return no("middle ground footprint closed")
        det.update(landing=land, end_x=stand)
        if q.routes is not None:
            # seq 311: after a press she stands deep in this landing's coverage: the way out is counted, as for the aim's choice
            row, _, k_goal = c.route(None, stand)
            if k_goal is None:
                return no("the return to the walker not reached in the model")
            det.update(return_s=c.t_of(k_goal) - c.t_to)
            why = _way_back_late(c, row, land)
            if why is None and _second_aiming(q):
                why = _second_way_out(c, stand, land, c.t_of(k_goal), det)
            if why is not None:
                return no(why)
        return Candidate("stay", True, None, "return", 1., tuple(det.items())), dict(aim_x=None, guide=None, depart=None)
    if c.hmax is None:
        return no("no aim leaves the walker's side open (wall rule / walker too near)")
    cap = c.hmax - f * GUIDE_MARGIN_U if math.isfinite(c.hmax) else math.inf * f
    if (cap - c.h_lo) * f < 0:
        return no("sufficient point inside the jumper's front")
    det.update(hmax=c.hmax if math.isfinite(c.hmax) else None, h_lo=c.h_lo)
    if q.hand.x * f <= cap * f:
        # the current stance already suffices: no guide. In the aim she keeps to the sufficient side of it.
        aim_x = min(c.front * f, cap * f) * f
        guide, depart, arrive = None, None, None
    else:
        guide, aim_x = cap, cap
        if c.lock is None:
            return no("aim clock unknown: no guide deadline")
        arrive = c.lock - RESERVE_S
        depart, travel, how = _latest_departure(m, c.k_hand, q.hand.t, guide, arrive, c.k_of)
        if depart is None:
            det.update(guide=guide, travel_s=travel)
            return no("guide not reached in the model" if travel is None else "guide arrives after the aim reserve")
        det.update(travel_s=travel, guide_u=abs(q.hand.x - guide), guide_how=how)
    land = _land(J.x, aim_x, f)
    stand = stand_x(land, f, c.reach, W.a, W.b, W.x, q.left, q.right, q.pad, q.gap_u, q.face_u, c.shift)
    det.update(aim_x=aim_x, guide=guide, depart_t=depart, arrive_t=arrive, landing=land, end_x=stand)
    if stand is None:
        return no("middle ground footprint closed at the predicted landing")
    # The way back is modeled too (a dash's cooldown after the guide, the turn), not assumed free.
    row, k_aim, k_goal = c.route(aim_x if guide is not None else None, stand, None if depart is None else c.k_of(depart))
    if k_goal is None:
        return no("the return to the walker not reached in the model")
    det.update(return_s=c.t_of(k_goal) - c.t_to)
    why = _way_back_late(c, row, land)
    if why is not None:
        return no(why)
    return Candidate("stay", True, None, "aim_wait" if guide is not None else "aim_attack", 1.,
                     tuple(det.items())), dict(aim_x=aim_x, guide=guide, depart=depart, arrive=arrive)


def _second_aiming(q: Request) -> bool:
    """A press's follow-up with the second one already aiming a jump of its own (still on the ground)."""
    return q.routes is not None and q.other.family in JUMPS and q.other.state in ANTIC


def _second_way_out(c: _Middle, stand: float, land1: float, at_stand_t: float, det: dict) -> str | None:
    """The middle with the second one aiming its own jump (seq 311, Sol's review of #374): its own clock and its own landing, never a waiting walker. Where she stands when its aim
    locks decides where it lands, so the stance counts only if a way out of what that landing covers is still open afterwards, at a run: toward the first one's side (past all its
    coverage; the first one's rune, while it is still to burst there, is crossed only after that) or behind its landing before its body comes down. None: there is one; else why not."""
    q, f = c.q, c.f
    W = q.other
    if q.other_antic_at is None:
        return "the second one's aim clock is unknown"
    fw, v = -f, JB.CFG["walk_v"] * 60.
    half = max(q.left, q.right)
    lock2 = q.other_antic_at + LOCK_S[W.family]
    land2 = lock2 + FLIGHT_S
    cast2 = W.family == "CC_JUMP_CAST"
    bite2 = land2 + RUNE_ON_S if cast2 else land2      # when what it covers bites
    reach2 = RUNE_REACH_U if cast2 else q.reach_j
    land_second = _land(W.x, stand, fw)
    depart = max(at_stand_t, lock2)                    # she holds the stance until its aim has read her: leaving earlier moves its landing with her
    det.update(second_lock_t=lock2, second_land_t=land2, second_bite_t=bite2, second_landing=land_second)
    x_out = land_second + fw * (reach2 + half + q.pad)
    x_ham = land_second + fw * (q.reach_j + half + q.pad)
    t_out = depart + abs(x_out - stand) / v
    # that place may lie inside the first one's coverage: closed only if the second one bites while the first one's rune is lit there
    first_rune_there = c.cast and (x_out - (land1 + f * c.reach)) * f < 0 and c.land_t + RUNE_ON_S - .05 <= bite2 <= c.land_t + RUNE_OVER_S
    side_open = (q.xa <= x_out <= q.xb and t_out <= bite2 - .05 and depart + abs(x_ham - stand) / v <= land2 - .05 and not first_rune_there)
    vx2 = abs(_vx_of(W.x, stand, fw))
    need = max(JB.CFG["min_back_u"], BODY_BACK_U + vx2 * SWEEP_S + c.half_w + q.pad)
    spot = land_second - fw * max(JB.CFG["back_u"], need)
    spot = min(max(spot, q.xa + JB.CFG["wall_pad_u"]), q.xb - JB.CFG["wall_pad_u"])
    behind_open = abs(land_second - spot) >= need and depart + abs(spot - stand) / v <= lock2 + DESCENT_S - .05
    det.update(second_out_x=x_out, second_out_t=t_out, second_behind_x=spot, second_ways=("side" if side_open else "") + ("/behind" if behind_open else ""))
    return None if side_open or behind_open else "the second one's own jump leaves no way out of the middle in time"


def _way_back_late(c: _Middle, row, land) -> str | None:
    """What of this landing's coverage still lies over her on the way back along row: its hammer when it comes down, its rune when it lights; None: nothing."""
    q, f, m = c.q, c.f, c.m
    x = m.xs(row[None])[0]
    i_land = min(len(x) - 1, int(round((c.land_t - q.t) / m.dt)))
    if (x[i_land] - (land + f * (q.reach_j + c.half_j))) * f < 0:
        return "still under the landing hammer on the way back"
    if c.cast:
        i_rune = min(len(x) - 1, int(round((c.land_t + RUNE_ON_S - q.t) / m.dt)))
        if (x[i_rune] - (land + f * (c.reach + c.half_j))) * f < 0:
            return "still inside the big rune on the way back"
    return None


def _latest_departure(m, k_hand, hand_t, goal, arrive_t, k_of):
    """When she must leave for goal to be there by arrive_t, by the bounded approach: the run when it still can, else the dash,
    from the state she is in then. (latest departure or None, travel seconds or None, how)."""
    zero = np.zeros(ROLL_T, np.int64)
    best = None
    for run_only in (True, False):
        if run_only:
            _, k = go(m, zero, k_hand, goal, run_only=True)
            how = "run"
        else:
            _, k, how = WP.route(m, zero, k_hand, goal)
        if k is None:
            continue
        travel = (k - k_hand) * m.dt
        depart = arrive_t - travel
        best = (depart, travel, how) if best is None else best
        if depart >= hand_t - 1e-9:
            # the same way from that departure itself: her cooldown is over by then, the turn is the model's
            _, k2, how2 = WP.route(m, zero, k_of(depart), goal, by_k=k_of(arrive_t))
            if k2 is None:
                continue
            late = (k2 - k_of(arrive_t)) * m.dt
            if late > 0:
                depart -= late
            if depart >= hand_t - 1e-9:
                return depart, travel, how2
    return (None, None if best is None else best[1], None)


def _under(c: _Middle, aim_x, name="under"):
    """Behind the predicted landing where the descending body does not come: its slanted sweep counted, not the end point."""
    q, f, m = c.q, c.f, c.m
    J = q.jumper
    land = q.land if not c.aim else _land(J.x, aim_x, f)
    vx = abs(q.land_vx) if (not c.aim and q.land_vx is not None) else abs(_vx_of(J.x, aim_x if aim_x is not None else q.hand.x, f))
    det = dict(landing=land, aim_x=aim_x, vx=vx)

    def no(reason):
        return Candidate(name, False, reason, None, 1., tuple(det.items()))

    if not q.hand.known:
        return no("hand-back unknown")
    if land is None:
        return no("landing unknown")
    back = J.x - q.xa if f > 0 else q.xb - J.x
    if back < JB.CFG["push_from_u"]:
        return no("wall landing is only a bound")
    need = max(JB.CFG["min_back_u"], BODY_BACK_U + vx * SWEEP_S + c.half_w + q.pad)
    spot = land - f * max(JB.CFG["back_u"], need)
    spot = min(max(spot, q.xa + JB.CFG["wall_pad_u"]), q.xb - JB.CFG["wall_pad_u"])
    if (land - spot) * f < need:
        return no("no room behind the landing past its descent")
    room = spot - q.xa if f > 0 else q.xb - spot
    det.update(end_x=spot, wall_room=room, need_back=need)
    by = c.t_to + DESCENT_S
    leg = c.leg(aim_x, spot, by_t=by - .05)
    if leg is None:
        return no("the way under not reached in the model")
    det.update(arrive_t=c.t_to + leg[2], by_t=by, route_s=leg[2])
    if c.t_to + leg[2] > by - .05:
        return no("arrives after its body comes down")
    return Candidate(name, True, None, "aim_attack" if c.aim else "under", 1., tuple(det.items()))


def _far_x(q: Request, c: _Middle):
    W, f = q.other, c.f
    return (W.b + max(1.2, q.left) if f > 0 else W.a - max(1.2, q.right)) + c.shift


def _over(c: _Middle, aim_x, name="over"):
    """To the walker's head. Normal jump: back to the middle once the hammer's reach has passed; jump cast: over its
    head longer or out past it, written here from the geometry (the rune's full coverage)."""
    q, f, m = c.q, c.f, c.m
    W, J = q.other, q.jumper
    land = q.land if not c.aim else _land(J.x, aim_x, f)
    far = _far_x(q, c)
    room = q.xb - far if f > 0 else far - q.xa
    det = dict(landing=land, aim_x=aim_x, far_x=far, wall_room=room, end_x=c.w_x)

    def no(reason):
        return Candidate(name, False, reason, None, 1., tuple(det.items()))

    if not q.hand.known:
        return no("hand-back unknown")
    if W.state not in STANDING:
        return no("the second one is aiming its own jump: no strike is supported on it" if _second_aiming(q) else "walker not in a standing state")
    if room < .5:
        return no("no far-side room")
    leg = c.leg(aim_x, c.w_x)
    if leg is None:
        return no("the walker's head not reached in the model")
    det.update(arrive_t=c.t_to + leg[2], by_t=c.land_t, route_s=leg[2])
    if c.t_to + leg[2] > c.land_t - .05 and land is not None:
        # late at its head is fine only when the way there is already past the landing hammer's reach then
        x = m.xs(leg[0][None])[0]
        i = min(len(x) - 1, int(round((c.land_t - q.t) / m.dt)))
        if (x[i] - (land + f * (q.reach_j + c.half_j))) * f < 0:
            return no("still under the landing hammer on the way to its head")
    why = _vault_start(c, aim_x)
    if why is not None:
        return no(why)
    follow = "back"
    if land is not None:
        # Where she waits must be out of the landing hammer: the walker's head when that is past its reach, else the far side (replay
        # m_over: the walker beside the landing, its head inside the hammer's polygon). A jump cast: out only when the far stance is past
        # the rune's whole coverage, otherwise over the head until it has burst.
        # Out is a real passage above its body from the strike's bounce: there must be time for it before the hazard.
        hammer = land + f * (q.reach_j + c.half_j)
        head_clear, far_clear = (c.w_x - hammer) * f >= 0, (far - hammer) * f >= 0
        crossed = c.t_to + leg[2] + CROSS_S
        if c.cast and (far - (land + f * (c.reach + c.half_j + q.pad))) * f >= 0 and crossed <= c.land_t + RUNE_ON_S - .05:
            follow = "out"
        elif head_clear:
            follow = "stay" if c.cast else "back"
        elif far_clear and not c.cast and crossed <= c.land_t - .05:
            follow = "out"
        else:
            return no("its head and far side are under the landing's coverage")
    det.update(follow=follow)
    return Candidate(name, True, None, "aim_attack" if c.aim else "over_head", 1., tuple(det.items()))


def _vault_start(c: _Middle, aim_x) -> str | None:
    """From the predicted start on the ground, inside the near vault's range: a row that reaches the walker's body without her box
    meeting it first (the same clean_near_row the action layer takes at its entry). Off the ground or outside that range the
    action layer's other entries apply; this asks nothing of them."""
    from ssbot.combat.air_chain import ChainSim
    from ssbot.combat.knife_chain_vault_entry import clean_near_row
    from ssbot.core.forum import FLOOR_Y
    q, m, f = c.q, c.m, c.f
    row = c.keys_to_take(aim_x)
    n = max(1, c.k_take)
    final = m.rollout(row[:n][None]).final
    S = np.asarray(final[:, 0], np.float64)
    kin = m.kin
    if S[kin.GROUND] <= 0 or int(S[kin.MODE]) != kin.M_NORMAL:
        return None
    W = q.other
    a, b = W.a + c.shift, W.b + c.shift
    x = float(S[kin.PX])
    gap = a - (x + q.right) if f > 0 else (x - q.left) - b
    if not .5 <= gap <= 3.5:
        return None
    S = S.copy()
    S[kin.JHELD] = 0.
    sim = ChainSim(S, np.zeros(1, np.int64), kin.HoldState.idle(1), m.params, m.terrain, 0, 0)
    row_, _ = clean_near_row(sim, (a, FLOOR_Y, b, BODY_TOP), f, walker_v=c.closing)
    return None if row_ is not None else "no clean vault row from the predicted start"


def _middle_phases(c: _Middle, stay: Candidate, stay_facts, follow: str, selected: str | None = None) -> tuple:
    q, f = c.q, c.f
    J, W = q.jumper.iid, q.other.iid
    take = (("takeoff_return", "return"), ("takeoff_under", "under"), ("takeoff_over", "over_head"),
            ("takeoff_blocked", BLOCKED), ("other_move", INVALID))
    # a new generation of a running aim stage keeps its place in time: the departure is the plan's, read from the plan
    phases = []
    aim_x = (stay_facts or {}).get("aim_x")
    front_ok = aim_x is None or (stay_facts or {}).get("guide") is not None or abs(aim_x - c.front) < 1e-9
    # Task 182 seq 311 (the person 11-09, the design's "原选翻过走路怪时"): only a jump cast's aim whose plan chose over. The walker's evade ends the attack on it: she stops
    # following it and goes straight at the first one, with no comparison first; what comes after is chosen from the real take-off (press_next), over being only the entry.
    pressing = c.cast and c.aim and selected == "over"
    phases.append(Phase("aim_attack", target=W, attack="side", no_hit=(J,),
                        stance=("front", W) if front_ok else ("x", aim_x), on=(("walker_evade", "aim_press"),) + take if pressing else take))
    if pressing:
        phases.append(Phase("aim_press", target=J, stance=("press",), ground=True, suppress_hits=True, go="press", replaceable=False, no_chase=True,
                            on=(("pressed", "press_next"),)))
        # The first one is off the ground: the follow-up is asked from the real take-off (one request, no search here), once the walker stands. Both follow-ups
        # lie toward the walker, so she already goes there while waiting; no hit is asked of anyone.
        phases.append(Phase("press_next", target=W, stance=("front", W), ground=True, suppress_hits=True, replaceable=False, adopts_next=True, no_chase=True,
                            on=(("next_late", BLOCKED),)))
    if stay_facts is not None and stay_facts.get("guide") is not None:
        H = stay_facts["guide"]
        fall = (("gap_closed", "aim_attack"), ("too_late", "aim_attack"))
        phases.append(Phase("aim_wait", target=W, stance=("x", q.hand.x), no_hit=(J,), on=take + fall,
                            at=(stay_facts["depart"] - c.m.off * c.m.dt, "aim_guide")))
        phases.append(Phase("aim_guide", target=J, stance=("x", H), suppress_hits=True, go="guide",
                            on=take + fall + (("arrived", "aim_hold"),)))
        phases.append(Phase("aim_hold", target=J, stance=("x", H), on=take + (("gap_closed", "aim_attack"),)))
    # Past the take-off: no replacement boundary inside a route; a new move of the walker ends the routes that need it.
    # stance_lost: the landing as tracked since has taken the place this stage stands on; it is not kept as safe (a flight plan may follow).
    phases.append(Phase("return", target=W, attack="side", stance=("stand",), no_hit=(J,), replaceable=False,
                        on=(("other_off", DONE),) * _second_aiming(q) + (("other_move", INVALID), ("move_over", DONE), ("stance_lost", BLOCKED))))
    phases.append(Phase("under", target=J, stance=("behind",), ground=True, replaceable=False, go="under",
                        on=(("move_over", DONE), ("stance_lost", BLOCKED))))
    after = {"back": "over_wait", "stay": "over_stay", "out": "over_out"}[follow]
    phases.append(Phase("over_head", target=W, attack="stomp", stance=("head", W), no_hit=(J,), replaceable=False,
                        on=(("other_gone", INVALID), ("bounced", after), ("hazard_over", "over_back"), ("stance_lost", BLOCKED))))
    # After the first real bounce: over its head or out past it, no second strike is asked of the action owners (B2's Idle
    # witness is revoked by that hit: its next Run would descend onto the body, #316 / #317); float there, no hit on either.
    phases.append(Phase("over_wait", target=W, stance=("head", W), no_hit=(J, W), replaceable=False,
                        on=(("other_gone", INVALID), ("hazard_over", "over_back"), ("stance_lost", BLOCKED))))
    # Task 182 seq 280 (the person: "give the ordinary planner the slow-shift preference"): over its head, the ordinary rows' own
    # down slash on it still counts (down_ok), checked like any row on both branches, re-judged on each real bounce; no strike
    # is asked of the action owners
    phases.append(Phase("over_stay", target=W, stance=("head", W), no_hit=(J, W), replaceable=False, down_ok=True,
                        on=(("other_gone", INVALID), ("hazard_over", "over_back"), ("stance_lost", BLOCKED))))
    phases.append(Phase("over_out", target=W, stance=("far", W), no_hit=(J, W), replaceable=False, go="out",
                        on=(("other_gone", INVALID), ("hazard_over", "over_back"), ("stance_lost", BLOCKED))))
    # Back to the middle from the air. Landed in the gap: done. Landed elsewhere the rows cannot cross its body (replay m_close stood
    # still there): not a success: the plan hands the return it did not finish to the public middle return.
    phases.append(Phase("over_back", target=W, stance=("middle", W), no_hit=(J,), replaceable=False,
                        on=(("other_gone", INVALID), ("landed_gap", DONE), ("landed_away", HANDBACK))))
    return tuple(phases)


def _only_routes(q: Request, cand: Candidate) -> Candidate:
    """A request that names its routes (a press's follow-up): any other candidate is closed, with the reason."""
    if q.routes is None or cand.name in q.routes:
        return cand
    return Candidate(cand.name, False, "not a follow-up of the press", None, 1., cand.detail)


def _middle_plan(q: Request, m: Roller) -> Plan:
    c = _Middle(q, m)
    f = c.f
    if q.stage == "flight" and ((q.face in (-1, 1) and q.face != f) or (q.land is not None and (q.other.x - q.land) * f <= 0)):
        # A jump away from the walker, or one landing past it: none of this scene's three routes is about it.
        return Plan("middle", q.instance, q.generation, q.t, None, c.hazard_end + HIT_TAIL_S, status="none",
                    reason="the jump does not land toward the walker", detail=(("family", q.jumper.family), ("other", q.other.iid)))
    stay, facts = _stay(c)
    # Each option as it would be chosen: under / over attack the walker in the aim, so their landing follows from there.
    attack_x = c.front if c.aim else None
    under, over = _only_routes(q, _under(c, attack_x)), _only_routes(q, _over(c, attack_x))
    prepared = []
    if stay.feasible:
        # Stay chosen: the walker can still close the gap, so the fallback is prepared from where stay's aim leaves her.
        from_x = facts["aim_x"] if facts["aim_x"] is not None else attack_x
        fb_under, fb_over = _only_routes(q, _under(c, from_x, "under")), _only_routes(q, _over(c, from_x, "over"))
        cands = (stay, fb_under, fb_over)
        selected = "stay"
        prepared = [x.name for x in (fb_under, fb_over) if x.feasible]
    else:
        cands = (stay, under, over)
        ok = [x for x in (under, over) if x.feasible]
        selected = max(ok, key=lambda x: x.get("wall_room", -math.inf)).name if ok else None
        prepared = [x.name for x in ok]
    follow = next((x.get("follow") for x in cands if x.name == "over" and x.feasible), None) or "back"
    made = dict(f=f, reach=c.reach, family=q.jumper.family, jumper=q.jumper.iid, other=q.other.iid, other_family=q.other.family, follow=follow,
                prepared=tuple(prepared), lock_t=c.lock, take_t=c.t_to, land_t=c.land_t, w_in=(q.other.a if f > 0 else q.other.b),
                arrive_dir=-f, arrive_t=None if facts is None else facts.get("arrive"),
                need=c.need, h_lo=c.h_lo, h_cap_margin=GUIDE_MARGIN_U, stage=q.stage, walker_x0=q.other.x, walker_v=c.closing,
                landings=tuple(x.get("landing") for x in (stay, under, over) if x.get("landing") is not None),
                latest_depart=None if facts is None else facts.get("depart"), followup=q.routes is not None)
    until = c.hazard_end + HIT_TAIL_S
    soft = [Range("walker_err", -SOFT_WALKER_U, SOFT_WALKER_U)]
    if facts is not None and facts.get("guide") is not None:
        soft.append(Range("hand_x", q.hand.x - SOFT_HAND_U, q.hand.x + SOFT_HAND_U))
        soft.append(Range("hand_t", -math.inf, facts["depart"]))
    base = dict(scene="middle", instance=q.instance, generation=q.generation, made_t=q.t, aim_deadline=c.lock, valid_until=until,
                candidates=cands, detail=tuple(made.items()),
                support=(Range("walker_err", -HARD_WALKER_U, HARD_WALKER_U),), soft=tuple(soft))
    if selected is None:
        return Plan(status="none", reason="; ".join(f"{x.name}: {x.reason}" for x in cands), **base)
    return Plan(phases=_middle_phases(c, stay, facts, follow, selected), selected=selected, **base)


def _cluster_plan(q: Request, m: Roller) -> Plan:
    """Lure first when its whole space holds; attack otherwise; neither is an explicit no plan. The public selector picks."""
    J, G = q.jumper, q.other
    out = q.side
    cast = J.family == "CC_JUMP_CAST"
    reach = RUNE_REACH_U if cast else q.reach_j
    half_out = q.right if out > 0 else q.left
    half_in = q.left if out > 0 else q.right
    lock = q.antic_at + LOCK_S[J.family] if q.antic_at is not None else None
    t_to = lock if lock is not None else q.t + .1
    land_t = t_to + FLIGHT_S
    k_hand = max(0, q.hand.index - m.off)
    k_take = max(0, int(math.ceil((t_to - q.t) / m.dt)) - m.off)
    t_of = lambda k: q.t + (m.off + k) * m.dt
    k_of = lambda t: max(0, int(math.ceil((t - q.t) / m.dt)) - m.off)
    wall = q.xb - JB.CFG["wall_pad_u"] if out > 0 else q.xa + JB.CFG["wall_pad_u"]
    closing = G.vx if (G.state == "Walk" and G.vx * out > 0) else 0.
    shift = closing * (max(0., t_to - q.t) + WALK_LOOK_S)

    def lure():
        det = dict(out=out, closing=closing, walker_shift=shift, hand_x=q.hand.x, hand_t=q.hand.t)

        def no(reason):
            return Candidate("lure", False, reason, None, 1., tuple(det.items())), None

        if not q.hand.known:
            return no("hand-back unknown")
        if lock is None:
            return no("aim clock unknown")
        S = G.x + shift + out * q.face_u
        S = min(S * out, (wall * out)) * out
        need = max(JB.CFG["min_back_u"], BODY_BACK_U + 12. * SWEEP_S + half_in + q.pad)
        v = ((S + out * need) - J.x) * out / GAIN
        det.update(return_x=S, need_back=need, v_need=v)
        if v > 12.:
            return no("the jump cannot land that far out")
        v = max(v, -12.)
        h_need = J.x + out * (5. + v) + out * GUIDE_MARGIN_U
        if (h_need - wall) * out > 0:
            return no("no space behind her for the landing it needs")
        land_need = _land(J.x, h_need, out)
        if (land_need - (S + out * need)) * out < 0:
            return no("the wall rule keeps the landing short of the room it needs")
        widths = abs(h_need - q.hand.x) / max(.1, abs(G.b - G.a))
        guide = None if q.hand.x * out >= h_need * out else h_need
        aim_x = q.hand.x if guide is None else guide
        det.update(h_need=h_need, guide=guide, aim_x=aim_x, widths_observed=widths, wall_x=wall)
        depart = None
        arrive = lock - RESERVE_S
        if guide is not None:
            depart, travel, how = _latest_departure(m, k_hand, q.hand.t, guide, arrive, k_of)
            if depart is None:
                det.update(travel_s=travel)
                return no("guide not reached in the model" if travel is None else "guide arrives after the aim reserve")
            det.update(depart_t=depart, travel_s=travel, guide_how=how)
        # the way back from the guide, against its descent (a dash's cooldown and the turn are the model's)
        row = np.zeros(ROLL_T, np.int64)
        k_aim = k_take
        if guide is not None:
            row, k_aim, _ = WP.route(m, row, k_of(depart), guide, by_k=k_of(arrive))
            if k_aim is None:
                return no("guide not reached in the model")
        row, k_back = go(m, row, max(k_take, k_aim), S)
        if k_back is None:
            return no("the way back not reached in the model")
        by = t_to + DESCENT_S
        det.update(return_arrive_t=t_of(k_back), by_t=by, end_x=S, route_s=t_of(k_back) - t_to)
        if t_of(k_back) > by - .05:
            return no("the way back arrives after its body comes down")
        return Candidate("lure", True, None, "lure_wait" if guide is not None else "lure_hold", 1., tuple(det.items())), \
            dict(guide=guide, depart=depart, need=need, aim_x=aim_x, arrive=arrive)

    def attack():
        det = dict(out=out, hand_x=q.hand.x)

        def no(reason):
            return Candidate("attack", False, reason, None, 1., tuple(det.items())), None

        if not q.hand.known:
            return no("hand-back unknown")
        near = min((J, G), key=lambda b: min(abs(q.hand.x - b.a), abs(q.hand.x - b.b)))
        stance = near.x + out * q.face_u
        land = _land(J.x, stance, out)
        X = land + out * (reach + half_in + q.pad)
        det.update(reachable=near.iid, aim_x=stance, landing=land, retreat_x=X, reach=reach, wall_x=wall)
        if (X - wall) * out > 0:
            return no("no room to retreat past the coverage")
        # rolled on from the state she is predicted to leave from (speed, air, cooldown; a late hand-back starts it later)
        row0, _ = go(m, np.zeros(ROLL_T, np.int64), k_hand, stance)
        row0 = row0.copy()
        row0[k_take:] = 0
        by = land_t + (RUNE_ON_S if cast else 0.)
        row, k_x, _ = WP.route(m, row0, max(k_take, k_hand), X, by_k=k_of(by - .05))
        if k_x is None:
            return no("the retreat not reached in the model")
        leg_s = t_of(k_x) - t_to
        det.update(arrive_t=t_to + leg_s, by_t=by, end_x=X, route_s=leg_s)
        if t_to + leg_s > by - .05:
            return no("the retreat arrives after the hazard")
        hammer_x = land + out * (q.reach_j + half_in)
        x = m.xs(row[None])[0]
        i_land = min(len(x) - 1, int(round((land_t - q.t) / m.dt)))
        if (x[i_land] - hammer_x) * out < 0:
            return no("still under the landing hammer on the retreat")
        return Candidate("attack", True, None, "attack_aim", 1., tuple(det.items())), dict(target=near.iid)

    cand_l, f_l = lure()
    cand_a, f_a = attack()
    hazard_end = land_t + (RUNE_OVER_S if cast else 5 / 60.)
    made = dict(out=out, f=out, reach=reach, family=J.family, jumper=J.iid, other=G.iid, other_family=G.family, lock_t=lock, take_t=t_to,
                land_t=land_t, stage=q.stage, need_back=(f_l or {}).get("need"), half_in=half_in, pad=q.pad, wall_x=wall,
                walker_x0=G.x, walker_v=closing, latest_depart=(f_l or {}).get("depart"), reach_j=q.reach_j,
                arrive_dir=out, arrive_t=(f_l or {}).get("arrive"))
    soft = [Range("walker_err", -SOFT_WALKER_U, SOFT_WALKER_U)]
    if f_l is not None and f_l.get("guide") is not None:
        soft.append(Range("hand_x", q.hand.x - SOFT_HAND_U, q.hand.x + SOFT_HAND_U))
        soft.append(Range("hand_t", -math.inf, f_l["depart"]))
    base = dict(scene="cluster", instance=q.instance, generation=q.generation, made_t=q.t, aim_deadline=lock,
                valid_until=hazard_end + HIT_TAIL_S, candidates=(cand_l, cand_a), detail=tuple(made.items()),
                support=(Range("walker_err", -HARD_WALKER_U, HARD_WALKER_U),), soft=tuple(soft))
    if not cand_l.feasible and not cand_a.feasible:
        return Plan(status="none", reason=f"lure: {cand_l.reason}; attack: {cand_a.reason}", **base)
    jid, gid = J.iid, G.iid
    other_move = ("other_move", INVALID)
    phases = [
        # lure: attacks stay legal until its departure; the return is the observed take-off's, never the landing's
        Phase("lure_hold", target=gid, stance=("x", (f_l or {}).get("aim_x", q.hand.x)), no_hit=(jid,),
              on=(("takeoff_return", "lure_return"), ("takeoff_retreat", "attack_retreat"), ("takeoff_blocked", BLOCKED),
                  other_move)),
        # The way back is the existing side approach (B2 owns its keys and scans; it may pass under a source in the air). Past
        # the landing the jumper is the focus until it is down: as a non-focus its rule margin keeps her off the very place
        # the return is for (the standing gap behind its landing; #314 G1, replay c_lure: pushed back into the hammer).
        Phase("lure_return", target=gid, attack="side", stance=("front", gid), no_hit=(jid,), replaceable=False,
              on=(("past_landing", "lure_behind"), other_move, ("in_reach", DONE),)),
        Phase("lure_behind", target=jid, stance=("behind",), ground=True, replaceable=False,
              on=(("hazard_over", "lure_slash"), ("stance_lost", BLOCKED))),
        Phase("lure_slash", target=gid, attack="side", stance=("front", gid), no_hit=(jid,), replaceable=False,
              on=(other_move, ("in_reach", DONE),)),
        Phase("attack_aim", target=(f_a or {}).get("target", gid), attack="side", stance=("front", (f_a or {}).get("target", gid)),
              no_hit=(() if (f_a or {}).get("target", gid) == jid else (jid,)),
              on=(("takeoff_retreat", "attack_retreat"), ("takeoff_blocked", BLOCKED), other_move)),
        # Coming back: the body standing nearer to her then, by the observed landing (written here, read when the hazard ends).
        Phase("attack_retreat", target=jid, stance=("retreat",), suppress_hits=True, ground=True, replaceable=False, go="retreat",
              on=(("back_jumper", "attack_back_jumper"), ("back_other", "attack_back_other"), ("stance_lost", BLOCKED))),
        Phase("attack_back_jumper", target=jid, attack="side", stance=("front", jid), replaceable=False, on=(("in_reach", DONE),)),
        Phase("attack_back_other", target=gid, attack="side", stance=("front", gid), no_hit=(jid,), replaceable=False,
              on=(other_move, ("in_reach", DONE),)),
    ]
    if f_l is not None and f_l.get("guide") is not None:
        take = (("takeoff_return", "lure_return"), ("takeoff_retreat", "attack_retreat"), ("takeoff_blocked", BLOCKED), other_move)
        phases.append(Phase("lure_wait", target=gid, stance=("x", q.hand.x), no_hit=(jid,), on=take + (("too_late", "lure_late"),),
                            at=(f_l["depart"] - m.off * m.dt, "lure_go")))
        phases.append(Phase("lure_go", target=jid, stance=("x", f_l["guide"]), suppress_hits=True, go="guide",
                            on=take + (("arrived", "lure_hold"), ("too_late", "lure_late"))))
        # too late for the guide: lure is not forced, and attack was prepared with it when feasible
        phases.append(Phase("lure_late", target=(f_a or {}).get("target", gid), attack="side",
                            stance=("front", (f_a or {}).get("target", gid)), no_hit=(jid,), on=take))
    return Plan(phases=tuple(phases), selected=None, **base)


def generate(q: Request, params, terrain) -> Plan:
    """The whole plan of one snapshot. Pure: no policy, no clock, no execution state."""
    m = Roller(q.S0, q.prefix, q.hold, params, terrain)
    if q.scene == "middle":
        return _middle_plan(q, m)
    if q.scene == "cluster":
        return _cluster_plan(q, m)
    raise ValueError("unknown plan scene " + repr(q.scene))


def warm(params) -> None:
    """The generator's numba paths (startup only)."""
    from ssbot.knowledge import kinematics as kin
    S = np.asarray(kin.initial_state(params, 30., 3.01 + params.foot), np.float64)
    hold = kin.HoldState.idle(1)
    terrain = kin.Terrain2D(np.array([[3.01, 0., 80.]]), np.zeros((0, 3)), np.zeros((0, 4)))
    r = Roller(S, np.zeros(1, np.int64), hold, params, terrain)
    hand = hand_back(r, 0., 30.)
    WP.route(r, np.zeros(ROLL_T, np.int64), 0, 40.)
    J = Body(1, 24., 0., 22., 26., "Jump Antic", "CC_JUMP")
    W = Body(2, 40., 0., 38., 42., "Idle", None)
    q = Request("middle", "aim", (1, 0.), 1, 0., J, W, 0, 0., None, None, None, None, hand, .25, .25, 14.01, 48.99, 2., .25, 4., 7.76,
                S, np.zeros(1, np.int64), hold)
    generate(q, params, terrain)
    q = Request("cluster", "aim", (1, 0.), 2, 0., Body(1, 36., 0., 34., 38., "Jump Antic", "CC_JUMP"), W, -1, 0., None, None, None,
                None, hand, .25, .25, 14.01, 48.99, 2., .25, 4., 7.76, S, np.zeros(1, np.int64), hold)
    generate(q, params, terrain)


def standing_gap(geo):
    from .clapper_scene import standing_gap as shared
    return shared(geo)


def region_at(geo, x: float) -> str | None:
    """clapper_scene.geometry's region for an x other than her current one (her predicted hand-back)."""
    if geo is None:
        return None
    low, high = geo["low"], geo["high"]
    (a1, b1), (a2, b2) = geo["bodies"][low.iid], geo["bodies"][high.iid]
    left, right = geo["left"], geo["right"]
    lo, hi = b1 + left, a2 - right
    return ("left" if x + right <= a1 else "right" if x - left >= b2 else "middle" if lo <= x <= hi else
            "tight" if lo > hi and low.pos[0] <= x <= high.pos[0] else "over")


def parent_scene(subjects, geo, x: float):
    """(scene, jumper, other, side) of the planned jump scenes, or None. Exactly one in a jump. Middle: between the bodies by
    their spans (bracketing roots is not enough; stacked bodies are not middle); no ground or input term. Cluster: outside
    both, with no standing gap between them (the design's bodies together: two apart with her beyond one are not one), antic
    only, the other one neither in a near antic nor in the air."""
    if geo is None or len(subjects) != 2:
        return None
    jumping = [s for s in subjects if s.family in JUMPS]
    if len(jumping) != 1:
        return None
    s = jumping[0]
    o = next(v for v in subjects if v.iid != s.iid)
    region = region_at(geo, x)
    if region == "middle" and s.state in ANTIC | AIR:
        return "middle", s, o, 0
    if region in ("left", "right") and s.state in ANTIC and o.state not in NEAR | AIR and standing_gap(geo) is False:
        return "cluster", s, o, -1 if region == "left" else 1
    return None


class PlanRunner:
    """The foreground side of the plans for one GauntletTactics: the executor, the channel and the per-tick adapter."""

    def __init__(self, tac):
        self.tac = tac
        self.exec = PlanExecutor()
        self.channel = None
        self.reset()

    def reset(self) -> None:
        self.exec.reset()
        if self.channel is not None:
            self.channel.check_health()    # the reset boundary: a dead worker is loud here, never inside a tick
            self.channel.invalidate()
        self.moves: dict = {}
        self.generation = 0
        self.last_request = None           # dict: key, why and the values at the latest request
        self.waiting = None                # (scene, first request t) of a result not yet seen
        self.sent: dict = {}               # sequence -> dict(ns, f, t, why)
        self.seen_sequence = 0
        self.changed = False
        self.notes: list = []
        self.hand: Hand | None = None
        self.hand_free_index = 0
        self.last_stance: dict = {}
        self.no_plan: dict = {}            # scene -> the reason of the latest explicit no plan
        self.latency: list = []            # adopted: (observed -> validated ms, observed -> adopted ms, observed -> published ms, build ms, ticks)
        self.pending_wait: list = []       # pending -> adopted at the legal boundary: ms
        self.pending_info = None           # the result waiting for a legal boundary: its observation and validation
        self.counts = Counter()            # results by outcome: the denominators of the latency
        self.requests = self.adopted = 0
        self.tick_n = 0
        self.tick_ns = None
        self.worker_failed = None
        self.roller = None
        self.commit = None
        self._model_set = (None, None)
        self._routes: dict = {}            # this tick's take-off conditions, per plan generation and selection
        self._takeoff_noted: set = set()   # plan generations whose take-off was recorded
        self._go_done: set = set()         # (generation, phase): its bounded approach has arrived
        self._stage_key = None             # (generation, phase) stage_frame last saw, and the frame it was first read
        self._stage_f = None
        self.pressed = None                # Task 182 seq 311: the jump instance she pressed (its later requests choose only the follow-ups)
        self.press_asked = None            # ... the plan generation whose follow-up has been asked for

    # ---- the channel ----

    def _channel(self, inp):
        ch = self.channel
        if ch is None and INLINE and inp is not None:
            from .l2_plan_worker import InlineChannel
            ch = self.channel = InlineChannel(inp.params, int(INLINE))
        if ch is None and self.worker_failed is None:
            self.worker_failed = "no plan channel (the policy's startup did not make one)"
        if (ch is not None and inp is not None and inp.terrain is not None
                and (inp.params is not self._model_set[0] or inp.terrain is not self._model_set[1])):
            self._model_set = (inp.params, inp.terrain)
            ch.set_model(inp.params, inp.terrain)      # no terrain yet: no model and no request, never an empty terrain
        return ch

    def close(self) -> None:
        """Cleanup: the owned worker exits; its exit stays in stats()."""
        if self.channel is not None:
            self.channel.close()

    # ---- per-move facts ----

    def _track(self, sc) -> None:
        tac, t = sc.tac, sc.t
        for s in sc.subjects:
            m = self.moves.get(s.iid)
            if s.family in JUMPS:
                inst = (s.iid, tac.t_commit.get(s.iid))
                if m is None or m["instance"] != inst:
                    m = self.moves[s.iid] = dict(instance=inst, family=s.family, antic_at=None, air_at=None, land_seen=None,
                                                 x0=None, face=None, land=None, vx=None, by_v=False, ended=None)
                ent = tac._ent(sc.ws, s.iid)
                controls = [row for row in getattr(ent, "fsm", None) or ()
                            if isinstance(row, (tuple, list)) and len(row) == 3 and row[0] == "Control"]
                state, elapsed = (controls[0][1], controls[0][2]) if len(controls) == 1 else (None, None)
                if (m["antic_at"] is None and s.state == PRIMARY[s.family] and state == s.state
                        and type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0):
                    m["antic_at"] = t - elapsed     # the observed primary clock (first reading), never the second cast timer
                if s.state in AIR:
                    from .forum_local import clapper_facing
                    if m["air_at"] is None:
                        m["air_at"] = t
                        m["x0"] = float(s.pos[0])
                        m["face"] = clapper_facing(ent) if ent is not None else None
                        m["land"] = JB.landing(m["x0"], sc.hx, m["face"]) if m["face"] in (-1, 1) else None
                    vel = getattr(ent, "vel", None)
                    if (not m["by_v"] and vel is not None and getattr(vel, "conf", 0) > 0 and abs(float(vel.v[0])) > .05
                            and m["face"] in (-1, 1)):
                        m["vx"] = float(vel.v[0])
                        m["land"] = JB.landing_v(m["x0"], m["vx"], m["face"])
                        m["by_v"] = True
                    x = float(s.pos[0])
                    if (m["face"] in (-1, 1) and m["land"] is not None and (x - m["x0"]) * m["face"] > .05
                            and (x - m["land"]) * m["face"] > 0):
                        m["land"] = x                # pushed out past the estimate (the wall-top ledge)
                elif s.state in JB.LANDED_STATES:
                    if m["land_seen"] is None:
                        m["land_seen"] = t
                    m["land"] = float(s.pos[0])
            elif m is not None and m["ended"] is None:
                m["ended"] = t
                if m["land_seen"] is None:
                    m["land_seen"] = t

    def _instance_of(self, sc, iid):
        s = next((v for v in sc.subjects if v.iid == iid), None)
        if s is None:
            return None
        if s.family in JUMPS:
            return (iid, sc.tac.t_commit.get(iid))
        m = self.moves.get(iid)
        return None if m is None else m["instance"]

    def _vx(self, sc, s) -> float:
        vel = getattr(sc.tac._ent(sc.ws, s.iid), "vel", None)
        return float(vel.v[0]) if vel is not None and getattr(vel, "conf", 0) > 0 else 0.

    # ---- the tick ----

    def tick(self, sc):
        tac, t = sc.tac, sc.t
        ex = self.exec
        ex.notes, ex.changed = [], False
        self.notes = []
        self.tick_n += 1
        self.tick_ns = time.perf_counter_ns()
        self._routes = {}
        self._track(sc)
        inp = getattr(tac, "plan_input", None)
        ch = self._channel(inp)
        if ch is not None:
            ch.tick()
            failure = getattr(ch, "failure", None)
            if failure is not None and self.worker_failed is None:
                self.worker_failed = str(failure).strip().splitlines()[-1][:200]
                self.notes.append(dict(what="worker failed", reason=self.worker_failed))
        jumping = any(s.family in JUMPS for s in sc.subjects)
        self.hand = self.roller = None
        self.commit = None if inp is None else inp.commit
        if (jumping or ex.plan is not None or ex.pending is not None) and inp is not None and inp.terrain is not None:
            roller = Roller(inp.S0, inp.prefix, inp.hold, inp.params, inp.terrain)
            self.hand = hand_back(roller, t, sc.hx, inp.commit is None or inp.commit[1])
            self.roller = roller
            self.hand_free_index = roller.off
        self._take_result(sc)
        self._step(sc)
        self._request(sc)
        self.changed = ex.changed
        self.notes = self.notes + ex.notes

    def _step(self, sc) -> None:
        ex = self.exec
        plan = ex.plan
        if plan is not None and plan.get("other") is not None and all(v.iid != plan.get("other") for v in sc.subjects):
            ex.end("invalid", "the plan's other body is gone", sc.t)   # (a phase may target it: no output names a body that left)
        plan = ex.plan
        if plan is not None and plan.scene in ("middle", "cluster"):
            s = next((v for v in sc.subjects if v.iid == plan.instance[0]), None)
            if s is not None and s.family in ATTACK_FAMS and s.family not in JUMPS:
                self._jumper_moved(sc, plan, s)
        before, name = ex.plan, ex.name
        ex.step(sc.t, lambda ph: self._events(sc, ph), lambda pl: self._values(sc, pl),
                lambda pl: self._instance_of(sc, pl.instance[0]))
        self._after_step(sc, before, name)

    def _jumper_moved(self, sc, plan, s) -> None:
        """Its jump is over and it attacks again. The new threat takes its turn by the public priorities; that finishes only what is
        finished. Its rune still due: the stages that keep her off it go on at their own score (the rule comparison above them decides
        each tick); any other stage stops as an interruption, the rune staying in the public rules. A way back to the middle not
        made: the public middle return keeps it (its own conditions decide when). Only with neither is the plan complete."""
        ex = self.exec
        m = self.moves.get(plan.instance[0]) or {}
        rune_due = plan.get("family") == "CC_JUMP_CAST" and not self._hazard_over(sc, plan, s, m)
        if rune_due and ex.name in RUNE_WAITS:
            return
        why = "the jumper began a new move"
        if ex.name in RETURN_OWED:
            ex.end("handed_back", why, sc.t)
            self._keep_return(sc, plan)
        elif rune_due:
            ex.end("interrupted", why + " with its rune still due", sc.t)
        else:
            ex.end("complete", why, sc.t)

    def _after_step(self, sc, before, name=None) -> None:
        ex = self.exec
        if ex.name == "aim_press" and self.pressed != ex.plan.instance:
            self.pressed = ex.plan.instance
            self.notes.append(dict(what="press", f=sc.frame, hx=sc.hx, jumper=ex.plan.instance[0], walker=ex.plan.get("other")))
        if ex.name == "press_next" and not ex.handled(ex.plan.instance, "departed"):
            ex.record(ex.plan.instance, "departed", sc.t)      # the jump she left: not to be intercepted back, as the aim's take-off routes record it
        info = self.pending_info
        if info is not None and ex.pending is None:
            self.pending_info = None
            now = time.perf_counter_ns()
            if ex.plan is not None and ex.plan.generation == info["generation"]:
                self.counts["pending_adopted"] += 1
                self.adopted += 1
                self.pending_wait.append((now - info["ready_ns"]) / 1e6)
                self.latency.append((info["ready_ms"], (now - info["observed_ns"]) / 1e6, info["published_ms"], info["build_ms"], info["ticks"]))
                self.notes.append(dict(what="pending adopted", generation=info["generation"], pending_wait_ms=round(self.pending_wait[-1], 3),
                                       event_to_adopted_ms=round((now - info["observed_ns"]) / 1e6, 3)))
            else:
                self.counts["pending_dropped"] += 1
        if before is not None and ex.plan is None and (ex.status == "handed_back" or (ex.status == "expired" and name in RETURN_OWED)):
            self._keep_return(sc, before)

    def _keep_return(self, sc, plan) -> None:
        """The plan could not finish her way back to the middle: the public middle return keeps that goal, as it does after a near
        attack (its own conditions still decide when it is offered)."""
        m = self.moves.get(plan.instance[0]) or {}
        s = next((v for v in sc.subjects if v.iid == plan.instance[0]), None)
        start = m.get("antic_at")
        if start is None:
            start = plan.made_t                   # first seen in its flight: no antic clock
        due = dict(family=plan.get("family"), start_t=start, near=True, iid=plan.instance[0], end_t=sc.t, end_hx=sc.hx,
                   end_state=None if s is None else s.state, offered=False)
        if type(sc.frame) is int:
            due.update(start_f=sc.frame - int(round((sc.t - start) * 60.)), end_f=sc.frame)
        sc.mem["back"] = due
        self.notes.append(dict(what="return kept", family=due["family"], reason=self.exec.reason))

    def commit_choice(self, sc, branch: str) -> None:
        """The public selector's winner starts now and takes this tick's observed events at once: an observed take-off is not seen
        a tick late because the choice came on its tick."""
        ex = self.exec
        if ex.selected == branch:
            return
        n0 = len(ex.notes)
        if ex.select(branch, sc.t):
            self._step(sc)
            self.changed = ex.changed
        self.notes = self.notes + ex.notes[n0:]

    def start_phase(self, sc, branch: str):
        """The phase a candidate of the running plan stands in on this tick if the public selector chooses it: its first phase past
        the times and events already observed. No side effect. (phase, None), or (None, why) when it ends right there."""
        plan = self.exec.plan
        name = plan.candidate(branch).start
        for _ in range(MAX_START_MOVES):
            ph = plan.phase(name)
            if ph is None:
                return None, "no phase " + str(name)
            if ph.at is not None and sc.t >= ph.at[0]:
                nxt = ph.at[1]
            else:
                true = set(self._events(sc, ph, selected=branch, dry=True))
                nxt = next((to for ev, to in ph.on if ev in true), None)
            if nxt is None:
                return ph, None
            if nxt not in {p.name for p in plan.phases}:
                return None, "it ends at this tick: " + str(nxt)
            name = nxt
        return plan.phase(name), None

    def _values(self, sc, plan=None) -> dict:
        known = self.hand is not None and self.hand.known
        locked = known and (self.hand.index > self.hand_free_index or bool(self.commit and self.commit[1] and self.commit[2]))
        out = {"hand_x": self.hand.x if known else None,
               # a free hero's hand-back only follows the clock: it asks for nothing; a locked or owned one's can pass a departure
               "hand_t": self.hand.t if locked else None}
        if plan is not None:
            out.update(self._walker_err(sc, plan))
        return out

    @staticmethod
    def _walker_err(sc, plan) -> dict:
        """The walker against the plan's own prediction for it: a walk it already counted is no change."""
        if plan.get("other") is None or plan.get("walker_x0") is None:
            return {}
        o = next((v for v in sc.subjects if v.iid == plan.get("other")), None)
        return {"walker_err": None if o is None else
                float(o.pos[0]) - (plan.get("walker_x0") + plan.get("walker_v") * max(0., sc.t - plan.made_t))}

    def _take_result(self, sc) -> None:
        ch = self.channel
        pub = None if ch is None else ch.latest()
        if pub is None or pub.sequence <= self.seen_sequence:
            return
        self.seen_sequence = pub.sequence
        plan = pub.field
        info = self.sent.get(pub.sequence)
        merged = [seq for seq in self.sent if seq < pub.sequence]
        self.counts["merged"] += len(merged)
        for seq in [q for q in self.sent if q <= pub.sequence]:
            del self.sent[seq]
        state, why = self.exec.offer(plan, sc.t, self._instance_of(sc, plan.instance[0]), self._values(sc, plan))
        if state == "none" and self.exec.name == "press_next" and info is not None and info["why"] == PRESS_OVER:
            self.exec.end("blocked", "the press's follow-up: " + str(plan.reason), sc.t)
        if self.waiting is not None and (info is None or not self.sent):
            self.waiting = None
        now_ns = time.perf_counter_ns()
        self.counts["results"] += 1
        self.counts[state] += 1
        if state == "rejected":
            self.counts["rejected: " + str(why).split(":")[0]] += 1
        rec = dict(what="result", state=state, reason=why, scene=plan.scene, generation=plan.generation, status=plan.status,
                   sequence=pub.sequence, build_ms=round(float(pub.build_ms), 3), selected=plan.selected,
                   candidates=[dict(name=c.name, feasible=c.feasible, reason=c.reason, start=c.start,
                                    **{k: _num(v) for k, v in c.detail}) for c in plan.candidates],
                   plan=dict(made_t=plan.made_t, aim_deadline=plan.aim_deadline, valid_until=plan.valid_until,
                             **{k: _num(v) for k, v in plan.detail}))
        if info is not None:
            # From the STATE's arrival in the policy (before the hand-back roll and the snapshot), not from the channel's request.
            observed = info["observed_ns"]
            ready_ms = (now_ns - observed) / 1e6
            published_ms = (pub.origin - observed) / 1e6
            ticks = self.tick_n - info["tick"]
            rec.update(event=info["why"], observed_f=info["f"], observed_t=info["t"], event_to_validated_ms=round(ready_ms, 3),
                       event_to_published_ms=round(published_ms, 3), request_to_published_ms=round((pub.origin - info["ns"]) / 1e6, 3),
                       ticks=ticks, before_lock=None if plan.aim_deadline is None else sc.t < plan.aim_deadline)
            if state == "adopted":
                self.adopted += 1
                rec["event_to_adopted_ms"] = round(ready_ms, 3)
                self.latency.append((ready_ms, ready_ms, published_ms, float(pub.build_ms), ticks))
            elif state == "pending":
                self.pending_info = dict(generation=plan.generation, observed_ns=observed, ready_ns=now_ns, ready_ms=ready_ms,
                                         published_ms=published_ms, build_ms=float(pub.build_ms), ticks=ticks)
        self.notes.append(rec)
        if plan.status != "ok":
            self.no_plan[plan.scene] = plan.reason

    # ---- events: observations -> the names the current phase waits for ----

    def _events(self, sc, phase, selected=None, dry=False) -> list:
        ex = self.exec
        plan = ex.plan
        names = {ev for ev, _ in phase.on}
        out: list = []
        s = next((v for v in sc.subjects if v.iid == plan.instance[0]), None)
        m = self.moves.get(plan.instance[0]) or {}
        if s is None:
            return out
        o = next((v for v in sc.subjects if v.iid == plan.get("other")), None)
        past = m.get("air_at") is not None or s.family not in JUMPS
        if past and any(n.startswith("takeoff_") for n in names):
            route, why = self._route(sc, plan, s, o, m, selected if dry else ex.selected)
            if not dry:
                self._note_takeoff(sc, plan, o, m, route, why)
            out.append("takeoff_" + route)
        if "walker_evade" in names and self._walker_evades(sc, plan, s, o, m):
            out.append("walker_evade")
        if "pressed" in names and past:
            out.append("pressed")
        if "next_late" in names and sc.t - ex.since > PRESS_WAIT_S:
            out.append("next_late")
        if "other_off" in names and o is not None and o.state in AIR:
            out.append("other_off")                # the second one is off the ground: its jump takes its turn by the public priorities
        if "other_move" in names and _new_hostile(o, plan.get("other_family")):
            out.append("other_move")
        if "other_gone" in names and _other_gone(o):
            out.append("other_gone")
        if "gap_closed" in names and o is not None and self._gap_closed(sc, plan, s, o):
            out.append("gap_closed")
        if "too_late" in names and self._too_late(sc, plan, phase):
            out.append("too_late")
        if "arrived" in names and phase.stance and phase.stance[0] == "x" and (
                sc.hx - phase.stance[1]) * plan.get("arrive_dir") >= -ARRIVE_U:
            out.append("arrived")                  # at it or past it: a sprint's skid stops beyond its place
        if "bounced" in names and o is not None and self._bounced(sc, o):
            out.append("bounced")
        if "back_jumper" in names and self._hazard_over(sc, plan, s, m):
            nearer = m.get("land") is not None and o is not None and (m["land"] - float(o.pos[0])) * plan.get("out") > 0
            out.append("back_jumper" if nearer else "back_other")
        if names & {"hazard_over", "move_over"}:
            over = self._hazard_over(sc, plan, s, m)
            if "hazard_over" in names and over:
                out.append("hazard_over")
            if "move_over" in names and over and s.family not in JUMPS:
                out.append("move_over")
        if "in_reach" in names:
            target = next((v for v in sc.subjects if v.iid == phase.target), None)
            if target is not None and self._in_reach(sc, target):
                out.append("in_reach")
        if "past_landing" in names and m.get("land") is not None and (
                sc.hx - m["land"]) * plan.get("out") <= -(plan.get("need_back") or JB.CFG["min_back_u"]) + ARRIVE_U:
            out.append("past_landing")
        if "stance_lost" in names and self._stance_lost(sc, plan, phase, o, m):
            out.append("stance_lost")
            if not dry:
                self.notes.append(dict(what="stance lost", phase=phase.name, landing=m.get("land"), hx=sc.hx,
                                       walker_x=None if o is None else float(o.pos[0]),
                                       body=None if (o is None or sc.geo is None) else list(sc.geo["bodies"].get(o.iid, ()))))
        if names & {"landed_gap", "landed_away"} and sc.grounded:
            # completion facts only, no admission: in the gap the return is done; elsewhere it is not
            out.append("landed_gap" if sc.region == "middle" else "landed_away")
        if "response_over" in names and s.family not in JUMPS and not (
                s.iid in sc.tac.rune and sc.t <= sc.tac.rune[s.iid][3]):
            out.append("response_over")
        return out

    def _second_aiming_scene(self, sc, plan, x):
        """The press's follow-up with the second one already aiming a jump of its own, where the generic scene sees two jumps and gives up: the first one off the ground, the second still on it,
        she between them. (Two in the air are nobody's follow-up.)"""
        if sc.geo is None or len(sc.subjects) != 2:
            return None
        s = next((v for v in sc.subjects if v.iid == plan.instance[0]), None)
        o = next((v for v in sc.subjects if v.iid != plan.instance[0]), None)
        if s is None or o is None or s.family not in JUMPS or s.state not in AIR or o.family not in JUMPS or o.state not in ANTIC:
            return None
        return ("middle", s, o, 0) if "middle" in (region_at(sc.geo, x), region_at(sc.geo, sc.hx)) else None

    def _walker_evades(self, sc, plan, s, o, m) -> bool:
        """The press's entry: the walker has gone into its evade while she is still between the two and the first one is still aiming, not locked and not off the ground."""
        x = self.hand.x if (self.hand is not None and self.hand.known) else sc.hx
        return (o is not None and o.state == EVADE and s.state in ANTIC and m.get("air_at") is None and plan.aim_deadline is not None
                and sc.t < plan.aim_deadline and region_at(sc.geo, x) == "middle")

    def _gap_closed(self, sc, plan, s, o) -> bool:
        """No aim point is left at all for the stay route with the walker where it is now."""
        geo = sc.geo
        if geo is None:
            return False
        f = plan.get("f")
        a, b = geo["bodies"][o.iid]
        limit = (a if f > 0 else b) - f * plan.get("need")
        hmax = _hmax(float(s.pos[0]), limit, f, geo["xa"], geo["xb"])
        if hmax is None:
            return True
        return math.isfinite(hmax) and (hmax - f * plan.get("h_cap_margin") - plan.get("h_lo")) * f < 0

    def _too_late(self, sc, plan, phase) -> bool:
        if phase.at is not None:
            # her lock ends past the written latest departure
            latest = plan.get("latest_depart")
            return latest is not None and self.hand is not None and self.hand.known and self.hand.t > latest + 1e-6
        lock = plan.get("lock_t")
        if lock is None or not phase.stance or phase.stance[0] != "x":
            return False
        x = phase.stance[1]
        return (sc.hx - x) * plan.get("arrive_dir") < -ARRIVE_U and not self._arrives(sc, x, lock)

    def _arrives(self, sc, x: float, by_t: float) -> bool:
        """From her actual state and hand-back, by the bounded approach's own choice: at x by by_t in the model."""
        m, hand = self.roller, self.hand
        if m is None or hand is None or not hand.known:
            return False
        k0 = max(0, hand.index - m.off)
        k_by = int(math.floor((by_t - sc.t) / m.dt)) - m.off
        if k_by < 0:
            return False
        row = np.zeros(min(ROLL_T, max(k_by + 12, k0 + 4)), np.int64)
        # her committed motion may carry her there by itself (a dash already sent)
        d = 1 if x > sc.hx else -1
        crossing = WP._arrival(m.xs(row[None])[0][m.off:], float(x), d, ROUTE_TOL_U)
        if crossing is not None and crossing <= k_by:
            return True
        if k_by < k0:
            return False
        _, k, _ = WP.route(m, row, k0, float(x), by_k=k_by, release=False)
        return k is not None and k <= k_by

    def _clear_by(self, sc, x: float, direction: int, by_t: float) -> bool:
        """She is on the far side of x along direction by by_t: already, or by the bounded approach."""
        return (sc.hx - x) * direction >= 0 or self._arrives(sc, x, by_t)

    def _bounced(self, sc, o) -> bool:
        """This frame's real strike bounce on this body (a hit and the pogo evidence, the action layer's facts); a hit alone is none."""
        inp = getattr(sc.tac, "plan_input", None)
        return inp is not None and inp.bounce == o.iid

    def stage_frame(self, sc) -> int | None:
        """The frame the running stage began (Sol seq 272 B): this read's frame when its (generation, phase) is new to it. The stage's
        unit reads it each tick it applies the stage, from the tick it enters it (a later first read only makes it later)."""
        ex = self.exec
        key = (None if ex.plan is None else ex.plan.generation, ex.name)
        if key != self._stage_key:
            self._stage_key, self._stage_f = key, sc.frame if type(sc.frame) is int else None
        return self._stage_f

    def _hazard_over(self, sc, plan, s, m) -> bool:
        seen = m.get("land_seen")
        if seen is None:
            return False
        if plan.get("family") == "CC_JUMP_CAST":
            return sc.t >= seen + RUNE_OVER_S
        return s.family not in JUMPS or s.state == "Slam Recover"

    def _in_reach(self, sc, target) -> bool:
        if sc.geo is None:
            return False
        a, b = sc.geo["bodies"][target.iid]
        gap = max(a - sc.hx, sc.hx - b, 0.)
        return gap <= sc.tac.rules.edge_u

    # ---- the observed take-off: a few written conditions, no route search ----

    def _route(self, sc, plan, s, o, m, selected):
        """The written take-off conditions (no route search), once per tick per plan and selection; no side effect."""
        key = (plan.generation, selected)
        if key not in self._routes:
            self._routes[key] = (self._resolve_middle(sc, plan, s, o, m) if plan.scene == "middle"
                                 else self._resolve_cluster(sc, plan, s, o, m, selected))
        return self._routes[key]

    def _note_takeoff(self, sc, plan, o, m, route, why) -> None:
        if plan.generation in self._takeoff_noted:
            return
        self._takeoff_noted.add(plan.generation)
        self.notes.append(dict(what="takeoff", route=route, reason=why, landing=m.get("land"), by_v=m.get("by_v"), hx=sc.hx,
                               walker_x=None if o is None else float(o.pos[0]), f=sc.frame, selected=self.exec.selected))
        if route in ("return", "over"):
            self.exec.record(plan.instance, "departed", sc.t)   # the jump she left: not to be intercepted back

    def _stand_now(self, sc, plan, o, m, gap=None) -> float | None:
        """gap: the room asked between the body and the coverage (None: the plan's own margin, for choosing the route; a running stage asks
        only for a place she fits)."""
        geo = sc.geo
        land = m.get("land")
        if geo is None or land is None or o is None or o.iid not in geo["bodies"]:
            return None
        from .gauntlet import JT
        a, b = geo["bodies"][o.iid]
        vx = self._vx(sc, o)
        f = plan.get("f")
        shift = vx * WALK_LOOK_S if (o.state == "Walk" and vx * f < 0) else 0.
        return stand_x(land, f, plan.get("reach"), a, b, float(o.pos[0]), geo["left"], geo["right"], JT["pad"], JT["gap_u"] if gap is None else gap,
                       sc.tac.rules.face_u, shift)

    def _spot_now(self, sc, plan, m) -> float | None:
        land = m.get("land")
        if land is None or sc.geo is None:
            return None
        f = plan.get("f")
        half = sc.geo["right"] if f > 0 else sc.geo["left"]
        from .gauntlet import JT
        vx = abs(m.get("vx") or 0.)
        need = max(JB.CFG["min_back_u"], BODY_BACK_U + vx * SWEEP_S + half + JT["pad"])
        spot = land - f * max(JB.CFG["back_u"], need)
        spot = min(max(spot, sc.geo["xa"] + JB.CFG["wall_pad_u"]), sc.geo["xb"] - JB.CFG["wall_pad_u"])
        return spot if (land - spot) * f >= need else None

    def _far_now(self, sc, plan, o) -> float | None:
        if sc.geo is None or o is None:
            return None
        f = plan.get("f")
        a, b = sc.geo["bodies"][o.iid]
        return b + max(1.2, sc.geo["left"]) if f > 0 else a - max(1.2, sc.geo["right"])

    def _out_x(self, sc, plan, o, land) -> float | None:
        """The way out's stance at this landing (the tracked one, not the aim's): past its body and past all this landing covers (a jump
        cast: its whole rune; a plain jump: the hammer), inside the wall. None: no such place: no way out here."""
        far = self._far_now(sc, plan, o)
        if far is None or land is None:
            return None
        from .gauntlet import JT
        f = plan.get("f")
        half_j = sc.geo["left"] if f > 0 else sc.geo["right"]
        cast = plan.get("family") == "CC_JUMP_CAST"
        edge = land + f * (plan.get("reach") + half_j + (JT["pad"] if cast else 0.))
        x = max(far * f, edge * f) * f
        wall = sc.geo["xb"] if f > 0 else sc.geo["xa"]       # (the arena's limits for her centre)
        return x if (wall - x) * f >= 0 else None

    def _wait_holds(self, sc, plan, o, land) -> bool:
        """Where the over route waits (its written follow) is out of what this landing covers."""
        if plan.get("follow") == "out":
            return self._out_x(sc, plan, o, land) is not None
        from .gauntlet import JT
        f = plan.get("f")
        half_j = sc.geo["left"] if f > 0 else sc.geo["right"]
        return (float(o.pos[0]) - (land + f * (JT["reach_j"] + half_j))) * f >= 0

    def _stance_lost(self, sc, plan, phase, o, m) -> bool:
        """The landing as tracked now leaves no safe place for this running stage's stance (the place chosen earlier stays no safer)."""
        kind = (phase.stance or (None,))[0]
        land = m.get("land")
        if land is None or sc.geo is None:
            return False
        if kind == "stand":
            return o is not None and self._stand_now(sc, plan, o, m, gap=0.) is None
        if kind == "behind":
            return self._spot_now(sc, plan, m) is None
        if kind in ("head", "far"):
            # (its ordinary reaction to the hit moves its body for a moment; the place is judged once it stands again)
            return o is not None and o.state not in REACTION and not self._wait_holds(sc, plan, o, land)
        if kind == "retreat":
            out = plan.get("out")
            return (land + out * (plan.get("reach") + plan.get("half_in") + plan.get("pad")) - plan.get("wall_x")) * out > 0
        return False

    def _resolve_middle(self, sc, plan, s, o, m):
        tac, t, f = sc.tac, sc.t, plan.get("f")
        if m.get("face") in (-1, 1) and m["face"] != f:
            return "blocked", "the jump's facing differs from the plan's"
        if m.get("land") is None:
            return "blocked", "landing unknown at the take-off"
        planned = plan.get("landings") or ()
        if planned and min(abs(m["land"] - v) for v in planned) > LAND_SUPPORT_U:
            return "blocked", "the observed landing is outside the plan's support"
        if self.hand is None or not self.hand.known:
            return "blocked", "her hand-back is unknown at the take-off"
        from .gauntlet import JT
        land = m["land"]
        take_t = t if m.get("air_at") is None else m["air_at"]
        land_t = take_t + FLIGHT_S
        back = (m["x0"] - sc.geo["xa"] if f > 0 else sc.geo["xb"] - m["x0"]) if (sc.geo is not None and m.get("x0") is not None) else math.inf
        wall_bound = back < JB.CFG["push_from_u"]
        stand = None if wall_bound else self._stand_now(sc, plan, o, m)
        why = "wall landing is only a bound" if wall_bound else "middle ground footprint closed"
        half_j = (sc.geo["left"] if f > 0 else sc.geo["right"]) if sc.geo is not None else 0.
        if stand is not None:
            # The written geometry (the jump's whole forward reach, the walker's body and its closing), the walker's own state
            # and her way out of the coverage from her actual state. The forecast's union is not asked here: its coarse placements
            # cover every stance near an idle Clapper (replay m_guide: by both Clappers from 0.19 s, committed part too), which
            # made this route unreachable. Each row toward it still goes through the planner's support.
            due = o is not None and o.iid in tac.rune and t <= tac.rune[o.iid][3] and (
                (stand - tac.rune[o.iid][0]) * tac.rune[o.iid][1] > 0)
            if o is not None and o.family in ATTACK_FAMS:
                why = "the walker is in an attack move"
            elif due:
                why = "the walker's rune circle is due over the stance"
            elif not self._clear_by(sc, land + f * (JT["reach_j"] + half_j), f, land_t - .05):
                why = "she does not clear the landing hammer in time"
            elif plan.get("family") == "CC_JUMP_CAST" and not self._clear_by(sc, land + f * (plan.get("reach") + half_j), f, land_t + RUNE_ON_S):
                why = "she does not clear the rune's coverage in time"
            else:
                self.last_stance["stand"] = stand
                return "return", "the middle still has room"
        # the walker closed it (or it never had it): the prepared routes, the endpoint farther from the wall
        options = []
        prepared = plan.get("prepared") or ()
        if "under" in prepared:
            spot = self._spot_now(sc, plan, m)
            if spot is not None and self._arrives(sc, spot, take_t + DESCENT_S - .05):
                options.append(("under", (spot - sc.geo["xa"]) if f > 0 else (sc.geo["xb"] - spot)))
        if "over" in prepared and o is not None and o.state in STANDING:
            # where this plan waits (written), at the observed landing and the observed body: out of all it covers, or the route is not there
            out = plan.get("follow") == "out"
            end = self._out_x(sc, plan, o, land) if out else self._far_now(sc, plan, o)
            room = None if end is None else (sc.geo["xb"] - end if f > 0 else end - sc.geo["xa"])
            past = (sc.hx - (land + f * plan.get("reach"))) * f >= 0
            by = land_t - .05
            if out:                                # (the passage above its body before the hazard, as the plan counted it)
                by = min(by, land_t + (RUNE_ON_S if plan.get("family") == "CC_JUMP_CAST" else 0.) - .05 - CROSS_S)
            if room is not None and room >= .5 and self._wait_holds(sc, plan, o, land) and (past or self._arrives(sc, float(o.pos[0]), by)):
                options.append(("over", room))
        if not options:
            return "blocked", why + "; no prepared route supported"
        best = max(options, key=lambda v: v[1])
        return best[0], why + "; endpoint room " + ", ".join(f"{a} {b:.2f}" for a, b in options)

    def _resolve_cluster(self, sc, plan, s, o, m, selected):
        t, out = sc.t, plan.get("out")
        if m.get("face") in (-1, 1) and m["face"] != out:
            return "blocked", "the jump's facing differs from the plan's"
        land = m.get("land")
        if land is None or sc.geo is None or o is None:
            return "blocked", "landing or bodies unknown at the take-off"
        if self.hand is None or not self.hand.known:
            return "blocked", "her hand-back is unknown at the take-off"
        take_t = t if m.get("air_at") is None else m["air_at"]
        land_t = take_t + FLIGHT_S
        if selected == "lure":
            S = float(o.pos[0]) + out * sc.tac.rules.face_u
            need = plan.get("need_back")
            if need is not None and (land - S) * out >= need - .25 and self._arrives(sc, S, take_t + DESCENT_S - .05):
                return "return", "the way back holds"
        # The retreat is the prepared fallback only while it really holds: the plan found it feasible, it fits inside the wall and
        # she gets out of the coverage in time from where she actually is. A written phase is no route (Root: 23.26 u in 0.916 s).
        attack = plan.candidate("attack")
        if attack is None or not attack.feasible:
            return "blocked", "no prepared retreat: " + str(None if attack is None else attack.reason)
        X = land + out * (plan.get("reach") + plan.get("half_in") + plan.get("pad"))
        if (X - plan.get("wall_x")) * out > 0:
            return "blocked", "no room to retreat past the coverage"
        cast = plan.get("family") == "CC_JUMP_CAST"
        if not self._clear_by(sc, X, out, land_t + (RUNE_ON_S if cast else 0.) - .05):
            return "blocked", "the retreat does not arrive before the hazard"
        if not self._clear_by(sc, land + out * (plan.get("reach_j") + plan.get("half_in")), out, land_t - .05):
            return "blocked", "she does not clear the landing hammer in time"
        return "retreat", "retreat past the coverage"

    # ---- requests: events only ----

    def _request(self, sc) -> None:
        tac, t = sc.tac, sc.t
        ex = self.exec
        inp = getattr(tac, "plan_input", None)
        if self.channel is None or inp is None or inp.terrain is None or self.worker_failed is not None:
            return                                # (no terrain yet: refused, never an implicit empty one)
        x = self.hand.x if (self.hand is not None and self.hand.known) else sc.hx
        scene = parent_scene(sc.subjects, sc.geo, x)
        plan = ex.plan
        if ex.name == "aim_press":
            return                                # the press decides nothing: no new plan until the first one is off the ground
        if ex.name == "press_next":
            scene = scene or parent_scene(sc.subjects, sc.geo, sc.hx)    # (a key in flight may carry the predicted hand-back past a body's edge for a moment: she herself is still between them)
            if sc.geo is None:
                return                            # (no body geometry on this tick says nothing about the scene: the wait goes on, bounded by next_late)
            scene = scene or self._second_aiming_scene(sc, plan, x)
            if scene is None or scene[0] != plan.scene or scene[1].iid != plan.instance[0]:
                ex.end("blocked", "no scene left for the press's follow-up", t)
            elif self.press_asked != plan.generation and scene[2].state != EVADE:     # (an evading body is no place to choose from: asked once it stands)
                self.press_asked = plan.generation
                name, s, o, side = scene
                self._send(sc, name, s, o, side, plan.instance, PRESS_OVER, x, float(o.pos[0]), (name, plan.instance))
            return
        if plan is not None and plan.scene in ("middle", "cluster") and ex.phase is not None and ex.phase.replaceable:
            # the layout of the running aim-stage plan is gone: invalid at once, without waiting for anything
            reg = region_at(sc.geo, x)
            if (plan.scene == "middle" and reg in ("left", "right")) or (plan.scene == "cluster" and reg == "middle"):
                ex.end("invalid", "left the parent scene", t)
                plan = None
        if scene is None:
            if self.waiting is not None and t - self.waiting[1] > PEND_MAX_S:
                self.waiting = None
            return
        name, s, o, side = scene
        inst = (s.iid, tac.t_commit.get(s.iid))
        key = (name, inst)
        if ex.plan is None and ex.status == "complete" and ex.last_plan is not None and ex.last_plan.instance == inst:
            return                                # this jump's plan has run to its end: the ordinary rules from here
        if plan is None and ex.handled(inst, "bounced"):
            return                                # the over route's strike is done: no new route (and second strike) for this jump
        why = None
        last = self.last_request
        running = plan is not None and plan.instance == inst and plan.scene == name
        m = self.moves.get(s.iid) or {}
        land_t = (m.get("air_at") + FLIGHT_S) if m.get("air_at") is not None else None
        o_x = float(o.pos[0])
        if land_t is not None and t >= land_t:
            return
        if last is None or last["key"] != key:
            why = "first antic" if s.state in ANTIC else "first seen in flight"
        elif o.family != last["other_family"] and (o.family in ATTACK_FAMS or last["other_family"] in ATTACK_FAMS):
            why = "the other one's new move"       # (its ordinary reaction to a hit is no new move)
        elif (o.state == "Walk") != last["walking"] and not (plan is not None and running and ex.phase is not None
                                                             and not ex.phase.replaceable):
            why = "the walker started walking" if o.state == "Walk" else "the walker stopped walking"
        elif running and plan.aim_deadline is not None and t >= plan.aim_deadline:
            return                                # past the lock a running plan is executed, not regenerated
        elif running:
            if ex.phase is not None and not ex.phase.replaceable:
                return
            vals = self._values(sc, plan)
            if ex.phase is None or ex.phase.at is None:
                vals.pop("hand_x", None)           # past its departure she moves by the plan; no update for that
                vals.pop("hand_t", None)
            out = next((r.name for r in plan.soft if vals.get(r.name) is not None and not r.holds(vals[r.name])), None)
            if out is None:
                return
            moved = (abs(o_x - last["walker_x"]) >= REQUEST_STEP_U if out == "walker_err" else
                     abs(vals["hand_x"] - last["hand_x"]) >= REQUEST_STEP_U if out == "hand_x" else
                     abs(vals["hand_t"] - last["hand_t"]) >= .05)
            if not moved:
                return
            why = "support left: " + out
        else:
            # no running plan of this scene (pending, invalid or blocked): only a real change asks again
            if not last["hand_known"] and self.hand is not None and self.hand.known:
                why = "her hand-back is known now"
            elif abs(o_x - last["walker_x"]) >= SOFT_WALKER_U or abs(x - last["hand_x"]) >= SOFT_HAND_U:
                why = "no plan, the scene changed"
            elif s.state in AIR and last["stage"] == "aim" and not self.waiting:
                why = "no plan at the take-off"
            else:
                return
        self._send(sc, name, s, o, side, inst, why, x, o_x, key)

    def _send(self, sc, name, s, o, side, inst, why, x, o_x, key) -> None:
        tac, t, geo = sc.tac, sc.t, sc.geo
        from .gauntlet import JT
        inp = tac.plan_input
        m = self.moves.get(s.iid) or {}
        hand = self.hand if self.hand is not None else Hand(math.inf, sc.hx, 0., 0, False)
        self.generation += 1
        stage = "flight" if s.state in AIR else "aim"
        hold = inp.hold
        S0, prefix = np.array(inp.S0, np.float64), np.array(inp.prefix, np.int64)
        S0.setflags(write=False)
        prefix.setflags(write=False)
        J = Body(s.iid, float(s.pos[0]), self._vx(sc, s), *geo["bodies"][s.iid], s.state, s.family)
        W = Body(o.iid, float(o.pos[0]), self._vx(sc, o), *geo["bodies"][o.iid], o.state, o.family)
        q = Request(name, stage, inst, self.generation, t, J, W, side, m.get("antic_at"), m.get("air_at"), m.get("land"), m.get("vx"),
                    m.get("face"), hand, geo["left"], geo["right"], geo["xa"], geo["xb"], JT["gap_u"], JT["pad"], tac.rules.face_u,
                    JT["reach_j"], S0, prefix, _copy_hold(hold), FOLLOW_UP if inst == self.pressed else None,
                    (self.moves.get(o.iid) or {}).get("antic_at") if o.family in JUMPS else None)
        seq = self.channel.request(key, q)
        now = time.perf_counter_ns()
        self.sent[seq] = dict(ns=now, observed_ns=inp.t0_ns if inp.t0_ns is not None else (self.tick_ns or now), f=sc.frame, t=t, why=why,
                              tick=self.tick_n)
        self.requests += 1
        if self.waiting is None or self.waiting[0] != name:
            self.waiting = (name, t)
        self.last_request = dict(key=key, walker_x=o_x, hand_x=x, hand_t=hand.t if hand.known else t, other_family=o.family, stage=stage,
                                 walking=o.state == "Walk", hand_known=hand.known)
        self.notes.append(dict(what="request", scene=name, stage=stage, generation=self.generation, sequence=seq, why=why, f=sc.frame,
                               t=t, hand_x=x, hand_t=None if not hand.known else hand.t, walker_x=o_x, jumper_x=J.x))

    # ---- what the tactic units read ----

    def waypoint(self, sc, ph):
        """The running phase's bounded approach for the action layer: where and by which frame; None: this phase has none."""
        ex = self.exec
        plan = ex.plan
        if ph is None or ph.go is None or plan is None or type(sc.frame) is not int:
            return None
        x = self.stance(sc, ph)
        key = (plan.generation, ph.name)
        if key in self._go_done:
            return None                           # once there the ordinary rows hold the place
        if x is not None and abs(sc.hx - x) <= ARRIVE_U:
            self._go_done.add(key)
            return None
        m = self.moves.get(plan.instance[0]) or {}
        air = m.get("air_at")
        if ph.go == "guide":
            by = plan.get("arrive_t")
        elif ph.go == "press":
            by = plan.get("lock_t")
        elif air is None:
            by = None
        elif ph.go == "under":
            by = air + DESCENT_S - .05
        else:
            by = air + FLIGHT_S + (RUNE_ON_S if plan.get("family") == "CC_JUMP_CAST" else 0.) - .05
        if x is None or by is None or sc.t > by:
            return None
        over = None
        if ph.go == "out":
            span = (sc.geo or {}).get("bodies", {}).get(ph.target)
            root = next((s.pos[0] for s in sc.subjects if s.iid == ph.target), None)
            if span is None or root is None:
                return None
            # its body in either pose (an Idle one turns to a hero at its back), the span the action layer's support holds it to
            over = (min(float(span[0]), float(root) - BODY_HALF), 0., max(float(span[1]), float(root) + BODY_HALF), BODY_TOP)
        return WP.WaypointGoal(float(x), sc.frame + int(math.ceil((by - sc.t) * 60.)), ph.go, plan.instance[0],
                               (plan.instance, plan.generation, ph.name), over=over, family=plan.get("family"))

    def respond(self, sc, target) -> None:
        """A generic immediate response (no worker, no scene): one phase bound to this jump's instance."""
        inst = self._instance_of(sc, target.iid)
        self.generation += 1
        phase = Phase("hold", target=target.iid, on=(("response_over", DONE),))
        plan = Plan("intercept", inst, self.generation, sc.t, None, sc.t + 30., phases=(phase,),
                    candidates=(Candidate("hold", True, None, "hold"),), selected="hold",
                    detail=(("family", target.family),))
        self.exec.offer(plan, sc.t, inst, {})

    def departed(self, sc):
        """The jump she has left in this call's event history (its instance), or None."""
        for s in sc.subjects:
            if s.family in JUMPS:
                inst = (s.iid, sc.tac.t_commit.get(s.iid))
                if self.exec.handled(inst, "departed"):
                    return inst
        return None

    def context(self, scene: str, t: float):
        ex = self.exec
        if ex.plan is not None and ex.plan.scene == scene:
            return dict(generation=ex.plan.generation, phase=ex.name, selected=ex.selected)
        if self.waiting is not None and self.waiting[0] == scene and t - self.waiting[1] <= PEND_MAX_S:
            return dict(pending=True)
        return None

    def why_not(self, scene: str) -> str:
        ex = self.exec
        if self.worker_failed is not None:
            return "plan worker failed: " + self.worker_failed
        if self.waiting is not None and self.waiting[0] == scene:
            return "plan pending"
        if ex.status in ("blocked", "invalid", "expired") and ex.last_plan is not None and ex.last_plan.scene == scene:
            return f"plan {ex.status}: {ex.reason}"
        return f"no {scene} jump"

    def blocked_for(self, s) -> bool:
        """This jumper's move has no running plan (blocked, invalid, or no plan at all)."""
        ex = self.exec
        return ex.plan is None and s.family in JUMPS

    def entry(self, sc, target, previous):
        from .modes import EntryAttack
        ex = self.exec
        ph = ex.phase
        if ph is None or ph.attack is None or ex.plan is None:
            return None
        src = next((v for v in sc.subjects if v.iid == ex.plan.instance[0]), None)
        if src is None or src.iid == target.iid:
            return None
        if previous is not None and (previous.target, previous.source, previous.kind) == (target.iid, src.iid, ph.attack):
            return previous
        return EntryAttack(target.iid, ph.attack, src.iid, ex.plan.get("family"), abs(float(src.pos[0]) - sc.hx), sc.t)

    def stance(self, sc, ph) -> float | None:
        """The current stage's stance reference, resolved now (a walker moves, a landing estimate sharpens)."""
        ref, plan = ph.stance, self.exec.plan
        if ref is None or plan is None:
            return None
        kind = ref[0]
        m = self.moves.get(plan.instance[0]) or {}
        o = next((v for v in sc.subjects if v.iid == plan.get("other")), None)
        out = None
        if kind == "x":
            out = float(ref[1])
        elif kind == "front":
            from .clapper_scene import ground_stance
            target = next((v for v in sc.subjects if v.iid == ref[1]), None)
            if target is not None:
                out = ground_stance(sc.tac, target, sc.hx, sc.geo)
                if out is None:
                    out = sc.tac._clamp(float(target.pos[0]) + (-1 if sc.hx < float(target.pos[0]) else 1) * sc.tac.rules.face_u)
        elif kind == "press":
            # the first one's standable front side: where she would stand facing it (the same stance as any front one), never past it
            from .clapper_scene import ground_stance
            target = next((v for v in sc.subjects if v.iid == plan.instance[0]), None)
            if target is not None:
                out = ground_stance(sc.tac, target, sc.hx, sc.geo)
                if out is not None and (out - sc.hx) * (float(target.pos[0]) - sc.hx) < 0:
                    out = sc.hx                   # nearer to it than that already: she holds, a press never backs off
        elif kind == "stand":
            out = self._stand_now(sc, plan, o, m, gap=0.)
        elif kind == "behind":
            out = self._spot_now(sc, plan, m)
        elif kind == "head":
            target = next((v for v in sc.subjects if v.iid == ref[1]), None)
            out = None if target is None else float(target.pos[0])
        elif kind == "far":
            land = m.get("land")
            out = self._far_now(sc, plan, o) if land is None else self._out_x(sc, plan, o, land)
        elif kind == "middle":
            from .clapper_tactics import return_pose
            target = next((v for v in sc.subjects if v.iid == ref[1]), None)
            if target is not None and sc.geo is not None:
                out = return_pose(sc.tac, target, sc.geo, sc.hx)["stance"]
        elif kind == "retreat":
            land = m.get("land")
            if land is not None:
                out = land + plan.get("out") * (plan.get("reach") + plan.get("half_in") + plan.get("pad"))
                out = min(out * plan.get("out"), plan.get("wall_x") * plan.get("out")) * plan.get("out")
        if out is None:
            out = self.last_stance.get(kind)       # the last known answer of this reference, never a new route
        else:
            self.last_stance[kind] = out
        return out

    def log_row(self, sc):
        ex = self.exec
        ph = ex.phase
        row = dict(status=ex.status, reason=ex.reason, phase=ex.name, selected=ex.selected,
                   scene=None if ex.plan is None else ex.plan.scene, generation=None if ex.plan is None else ex.plan.generation,
                   hand=None if self.hand is None else dict(t=_num(self.hand.t), x=self.hand.x, vx=self.hand.vx, known=self.hand.known),
                   requests=self.requests, adopted=self.adopted, stance=None if ph is None else self.last_stance.get(ph.stance[0]) if ph.stance else None,
                   channel=None if self.channel is None else self.channel.mode, worker_failed=self.worker_failed,
                   commit=None if self.commit is None else [self.commit[0], self.commit[1], len(self.commit[2])])
        if self.notes:
            row["notes"] = list(self.notes)
        return row

    def stats(self) -> dict:
        lat = self.latency
        q = (lambda i, p: round(float(np.percentile([v[i] for v in lat], p)), 3) if lat else None)
        wait = self.pending_wait
        return dict(requests=self.requests, adopted=self.adopted, counts=dict(self.counts),
                    event_to_validated_ms=dict(p50=q(0, 50), p99=q(0, 99), max=q(0, 100)),
                    event_to_adopted_ms=dict(p50=q(1, 50), p99=q(1, 99), max=q(1, 100)),
                    event_to_published_ms_p50=q(2, 50), build_ms_p50=q(3, 50),
                    pending_wait_ms=dict(n=len(wait), p50=round(float(np.percentile(wait, 50)), 3) if wait else None,
                                         max=round(float(max(wait)), 3) if wait else None),
                    channel=None if self.channel is None else self.channel.status())


def _new_hostile(o, family_at_plan) -> bool:
    """The other one is gone or began a new attack move (its ordinary reaction to a hit is neither)."""
    return o is None or (o.family != family_at_plan and o.family in ATTACK_FAMS)


def _other_gone(o) -> bool:
    """No longer a body she can stand on the head of: dead or absent, or in a new dangerous move. Its ordinary reaction to the hit
    she just landed is not that: the same hit is the over route's bounce."""
    return o is None or o.state not in STANDING | REACTION


def _num(v):
    """A JSON-safe value for the logs."""
    if isinstance(v, (float, np.floating)):
        return None if not math.isfinite(v) else round(float(v), 4)
    if isinstance(v, (tuple, list)):
        return [_num(x) for x in v]
    return v


def _copy_hold(hold):
    from ssbot.knowledge.kinematics import HoldState
    return HoldState(np.array(hold.latched), np.array(hold.desired), np.array(hold.pending), np.array(hold.age))
