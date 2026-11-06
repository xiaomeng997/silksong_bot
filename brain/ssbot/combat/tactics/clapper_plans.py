"""The two-Clapper jump plans (Task 182; default off, SSBOT_FORUM_TWO_PLAN=1): snapshot, generator, foreground adapter.

generate() is pure: a Request (the bodies, the move's clock, the hero's hand-back prediction and her committed keys) goes
in, a complete immutable l2_plan.Plan comes out. It runs in the resident worker (l2_plan_worker) and reads nothing of
the policy. It never reads her current ground flag or can.input: what she can do follows from the model roll of her
committed keys (Hand) and of simple key rows from there; the action owners keep every real key check.

Two parent scenes, each with its own options (design: docs/plans/forum_clapper_l2_tactics.md):
  middle   she is clearly between the two bodies, exactly one in a jump's antic / flight: stay (the nearest sufficient
           guide point, or none needed, then back to slash the walker on the observed take-off), under, over; the
           normal choice is made in the aim and the fallback for a walker that closes the gap is prepared with it.
  cluster  she is outside both bodies, exactly one in a jump's antic: lure (back off to a sufficient interval, return under
           on the observed take-off) and attack (slash the reachable one, retreat past the coverage, come back once the
           hazards are over), chosen by the public selector.

PlanRunner is the foreground: non-blocking result read and checks, the executor's events and stance references, and the
event-driven requests (no period: first antic, a support range left, a new move, no plan left while time remains).
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import os
import time

import numpy as np

from ssbot.combat import jump_behind as JB
from .l2_plan import BLOCKED, DONE, INVALID, Candidate, Phase, Plan, PlanExecutor, Range

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

LOCK_S = {"CC_JUMP": .48, "CC_JUMP_CAST": .88}   # the antic's start -> the earliest aim lock
GAIN = .916                 # the flight: x_land - x = 0.916 vx (are_types.clapper.JUMP_GAIN)
FLIGHT_S = GAIN
DESCENT_S = 50 / 60.        # take-off -> its body's bottom comes down to a standing head (jump_behind walk_end_f)
SWEEP_S = 5 / 60.           # ... and from there to the landing: the slanted descent behind the landing is vx x this
BODY_BACK_U = 1.34          # its back edge behind its centre in the air (recordings: root + 1.34 facing left)
RESERVE_S = .10             # the guide's arrival before the earliest lock (the design's reserve)
GUIDE_START_X = 1.5         # the stance is given this many travel times before the lock reserve: the ordinary rows go to a
#                             stance by a row's end, not at once (replay k_stay); the latest departure itself is unchanged
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
LAND_SUPPORT_U = 3.0        # an observed landing this far from every landing the plan was made for is outside its support
RUN_ROW_U = 36 * JB.CFG["walk_v"]   # the planner's rows (36 frames) reach a stance this near at a run: no dash is chosen for it
UNDER_ROW_U = 7.0           # the under route is the ordinary rows' (no B2 owner, the jumper is its target). Replays with the
#                             route forced at the take-off: 6.9 u under a flat jump arrived; 7.75 / 8.9 / 9.9 / 11.6 u under it and
#                             9.2 u under an in-place cast did not: she hovers at the hammer's edge or inside it. Past this it
#                             is not offered (the usual aim leaves about 8.5-9.3 u: over, or an explicit block; TO_SOL #325).
RUNE_ON_S, RUNE_OVER_S = 65 / 60., (65 + 17) / 60.    # the landing -> the big rune hurts (are_types: on0, its long window)
HIT_TAIL_S = 1.0            # a plan's validity past the last hazard, for its return phases


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


def hand_back(m: Roller, t: float, fallback_x: float) -> Hand:
    """The first frame her committed keys and locked motion leave to new keys (no key after the ones in flight)."""
    kin = m.kin
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
    the faster of a run and a held dash (cooldown, air and turn are the model's). run_only: a guide, whose latest departure
    must hold even when the ordinary rows do not choose a dash. (row, arrival command index), or (row, None) when neither
    arrives inside the row."""
    L, R, D = _keys()
    x = m.xs(row[None])[0]
    i0 = m.off + k0
    if i0 >= x.shape[0]:
        return row, None
    if abs(goal - x[i0]) <= tol:
        return row, k0
    d = 1 if goal > x[i0] else -1
    key = R if d > 0 else L
    run, dash = row.copy(), row.copy()
    run[k0:], dash[k0:] = key, key | D
    X = m.xs(np.stack([run, dash]))[:, i0:]
    reached = (X - goal) * d >= -tol
    arrivals = [int(np.argmax(h)) if h.any() else None for h in reached]
    if run_only or abs(goal - x[i0]) <= RUN_ROW_U:
        arrivals[1] = None
    best = None
    for i, a in enumerate(arrivals):
        if a is not None and (best is None or a < arrivals[best]):
            best = i
    if best is None:
        return row, None
    out = (run if best == 0 else dash).copy()
    k = k0 + arrivals[best]
    out[k:] = 0
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

    def start_x(self, aim_x):
        """Where she is at the take-off when the aim stage takes her toward aim_x: there if her model path arrives in
        time (the attack keeps her there: no sprint overshoot counted), else where that path has come to."""
        if aim_x is None:
            return self.q.hand.x
        row, k = go(self.m, np.zeros(ROLL_T, np.int64), self.k_hand, aim_x)
        if k is not None and k <= self.k_take:
            return aim_x
        x = self.m.xs(row[None])[0]
        return float(x[min(len(x) - 1, self.m.off + self.k_take)])

    def leg(self, aim_x, goal):
        """The route after the observed take-off, from rest where she stands then (a dash ready: a guide's cooldown is
        the stay route's own continuous roll). (Roller, row, arrival index, seconds from the take-off) or None."""
        from ssbot.core.forum import FLOOR_Y
        q, m = self.q, self.m
        start = self.start_x(aim_x)
        r = Roller(m.kin.initial_state(m.params, start, FLOOR_Y + m.params.foot), np.zeros(1, np.int64), m.kin.HoldState.idle(1),
                   m.params, m.terrain)
        row, k = go(r, np.zeros(ROLL_T, np.int64), 0, goal)
        if k is None:
            return None
        # she may be locked past the take-off: the route starts at her hand-back
        late = max(0., q.hand.t - self.t_to) if q.hand.known else 0.
        return r, row, k, (r.off + k) * r.dt + late

    def route(self, aim_x, goal, depart_k=None):
        """Her model path: to aim_x from her hand-back (or depart_k), then to goal from the take-off. (row, k_aim, k_goal)."""
        row = np.zeros(ROLL_T, np.int64)
        k_aim = None
        if aim_x is not None:
            row, k_aim = go(self.m, row, self.k_hand if depart_k is None else depart_k, aim_x)
        k0 = max(self.k_take, k_aim if k_aim is not None else self.k_take)
        if k_aim is None or k_aim > self.k_take:
            k0 = self.k_take
            row[k0:] = 0
        k0 = max(k0, self.k_hand)
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

    if W.family in ATTACK_FAMS:
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
        row, k_arr = go(m, np.zeros(ROLL_T, np.int64), c.k_hand, guide, run_only=True)
        if k_arr is None:
            return no("guide not reached in the model")
        travel = (k_arr - c.k_hand) * m.dt
        depart = c.lock - RESERVE_S - travel
        if depart < q.hand.t - 1e-9:
            det.update(guide=guide, travel_s=travel, latest_depart=depart)
            return no("guide arrives after the aim reserve")
        # the same route from the latest departure itself (from rest, her cooldown over)
        k_dep = c.k_of(depart)
        row, k_arr = go(m, np.zeros(ROLL_T, np.int64), k_dep, guide, run_only=True)
        if k_arr is None:
            return no("guide not reached in the model")
        late = c.t_of(k_arr) - (c.lock - RESERVE_S)
        if late > 0:
            depart -= late
            if depart < q.hand.t - 1e-9:
                return no("guide arrives after the aim reserve")
        arrive = c.lock - RESERVE_S
        det.update(travel_s=travel, guide_u=abs(q.hand.x - guide))
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
    x = m.xs(row[None])[0]
    i_land = min(len(x) - 1, int(round((c.land_t - q.t) / m.dt)))
    if (x[i_land] - (land + f * (q.reach_j + c.half_j))) * f < 0:
        return no("still under the landing hammer on the way back")
    if c.cast:
        i_rune = min(len(x) - 1, int(round((c.land_t + RUNE_ON_S - q.t) / m.dt)))
        if (x[i_rune] - (land + f * (c.reach + c.half_j))) * f < 0:
            return no("still inside the big rune on the way back")
    start = None if depart is None else depart - (GUIDE_START_X - 1.) * det["travel_s"]
    return Candidate("stay", True, None, "aim_wait" if guide is not None else "aim_attack", 1.,
                     tuple(det.items())), dict(aim_x=aim_x, guide=guide, depart=depart, start=start)


def _under(c: _Middle, aim_x, name="under"):
    """Behind the predicted landing where the descending body does not come: its slanted sweep counted, not the end point."""
    q, f, m = c.q, c.f, c.m
    J = q.jumper
    land = q.land if not c.aim else _land(J.x, aim_x, f)
    vx = abs(q.land_vx) if (not c.aim and q.land_vx is not None) else abs(_vx_of(J.x, aim_x if aim_x is not None else q.hand.x, f))
    det = dict(landing=land, aim_x=aim_x, vx=vx)

    def no(reason):
        return Candidate(name, False, reason, None, 1., tuple(det.items()))

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
    if abs(spot - c.start_x(aim_x)) > UNDER_ROW_U:
        return no("the way under is longer than one planner row")
    leg = c.leg(aim_x, spot)
    if leg is None:
        return no("the way under not reached in the model")
    by = c.t_to + DESCENT_S
    det.update(arrive_t=c.t_to + leg[3], by_t=by, route_s=leg[3])
    if c.t_to + leg[3] > by - .05:
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

    if W.state not in STANDING:
        return no("walker not in a standing state")
    if room < .5:
        return no("no far-side room")
    leg = c.leg(aim_x, c.w_x)
    if leg is None:
        return no("the walker's head not reached in the model")
    det.update(arrive_t=c.t_to + leg[3], by_t=c.land_t, route_s=leg[3])
    if c.t_to + leg[3] > c.land_t - .05 and land is not None:
        # late at its head is fine only when the way there is already past the landing hammer's reach then
        r, row, _, _ = leg
        x = r.xs(row[None])[0]
        i = min(len(x) - 1, int(round(FLIGHT_S / r.dt)))
        if (x[i] - (land + f * (q.reach_j + c.half_j))) * f < 0:
            return no("still under the landing hammer on the way to its head")
    follow = "back"
    if c.cast and land is not None:
        # out only when the far stance is past the rune's whole coverage; otherwise over the head until it has burst
        follow = "out" if (far - (land + f * (c.reach + c.half_j + q.pad))) * f >= 0 else "stay"
    det.update(follow=follow)
    return Candidate(name, True, None, "aim_attack" if c.aim else "over_head", 1., tuple(det.items()))


def _middle_phases(c: _Middle, stay: Candidate, stay_facts, follow: str) -> tuple:
    q, f = c.q, c.f
    J, W = q.jumper.iid, q.other.iid
    take = (("takeoff_return", "return"), ("takeoff_under", "under"), ("takeoff_over", "over_head"),
            ("takeoff_blocked", BLOCKED), ("other_move", INVALID))
    phases = []
    aim_x = (stay_facts or {}).get("aim_x")
    front_ok = aim_x is None or (stay_facts or {}).get("guide") is not None or abs(aim_x - c.front) < 1e-9
    phases.append(Phase("aim_attack", target=W, attack="side", no_hit=(J,),
                        stance=("front", W) if front_ok else ("x", aim_x), on=take))
    if stay_facts is not None and stay_facts.get("guide") is not None:
        H = stay_facts["guide"]
        fall = (("gap_closed", "aim_attack"), ("too_late", "aim_attack"))
        phases.append(Phase("aim_wait", target=W, stance=("x", q.hand.x), no_hit=(J,), on=take + fall,
                            at=(stay_facts["start"] - c.m.off * c.m.dt, "aim_guide")))
        phases.append(Phase("aim_guide", target=J, stance=("x", H), suppress_hits=True, on=take + fall + (("arrived", "aim_hold"),)))
        phases.append(Phase("aim_hold", target=J, stance=("x", H), on=take + (("gap_closed", "aim_attack"),)))
    # Past the take-off: no replacement boundary inside a route; a new move of the walker ends the routes that need it.
    phases.append(Phase("return", target=W, attack="side", stance=("stand",), no_hit=(J,), replaceable=False,
                        on=(("other_move", INVALID), ("move_over", DONE))))
    phases.append(Phase("under", target=J, stance=("behind",), ground=True, replaceable=False, on=(("move_over", DONE),)))
    after = {"back": "over_wait", "stay": "over_stay", "out": "over_out"}[follow]
    phases.append(Phase("over_head", target=W, attack="stomp", stance=("head", W), no_hit=(J,), replaceable=False,
                        on=(("other_gone", INVALID), ("bounced", after), ("hazard_over", "over_back"))))
    # After the first real bounce: over its head or out past it, no second strike is asked of the action owners (B2's Idle
    # witness is revoked by that hit: its next Run would descend onto the body, #316 / #317); float there, no hit on either.
    phases.append(Phase("over_wait", target=W, stance=("head", W), no_hit=(J, W), replaceable=False,
                        on=(("other_gone", INVALID), ("hazard_over", "over_back"))))
    phases.append(Phase("over_stay", target=W, stance=("head", W), no_hit=(J, W), replaceable=False,
                        on=(("other_gone", INVALID), ("hazard_over", "over_back"))))
    phases.append(Phase("over_out", target=W, stance=("far", W), no_hit=(J, W), replaceable=False,
                        on=(("other_gone", INVALID), ("hazard_over", "over_back"))))
    # Back to the middle from the air. Landed anywhere, the plan is over: on the walker's far side the rows cannot cross its body
    # (replay m_close stood still there for the rest of the hazard's tail); the ordinary rules go on from where she is.
    phases.append(Phase("over_back", target=W, stance=("middle", W), no_hit=(J,), replaceable=False,
                        on=(("landed", DONE),)))
    return tuple(phases)


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
    under, over = _under(c, attack_x), _over(c, attack_x)
    prepared = []
    if stay.feasible:
        # Stay chosen: the walker can still close the gap, so the fallback is prepared from where stay's aim leaves her.
        from_x = facts["aim_x"] if facts["aim_x"] is not None else attack_x
        fb_under, fb_over = _under(c, from_x, "under"), _over(c, from_x, "over")
        cands = (stay, fb_under, fb_over)
        selected = "stay"
        prepared = [x.name for x in (fb_under, fb_over) if x.feasible]
    else:
        cands = (stay, under, over)
        ok = [x for x in (under, over) if x.feasible]
        selected = max(ok, key=lambda x: x.get("wall_room", -math.inf)).name if ok else None
        prepared = [x.name for x in ok]
    follow = next((x.get("follow") for x in cands if x.name == "over" and x.feasible), None) or "back"
    made = dict(f=f, reach=c.reach, family=q.jumper.family, jumper=q.jumper.iid, other=q.other.iid, other_family=q.other.family,
                prepared=tuple(prepared), lock_t=c.lock, take_t=c.t_to, land_t=c.land_t, w_in=(q.other.a if f > 0 else q.other.b),
                need=c.need, h_lo=c.h_lo, h_cap_margin=GUIDE_MARGIN_U, stage=q.stage, walker_x0=q.other.x, walker_v=c.closing,
                landings=tuple(x.get("landing") for x in (stay, under, over) if x.get("landing") is not None),
                speed=max(_avg_speed(x) for x in cands), guide_speed=_guide_speed(stay, q.hand.x),
                latest_depart=None if facts is None else facts.get("depart"))
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
    return Plan(phases=_middle_phases(c, stay, facts, follow), selected=selected, **base)


def _guide_speed(cand: Candidate, hand_x: float) -> float:
    """The guide route's own average speed in the model (u/s): the foreground's arrival check while it runs."""
    s, guide = cand.get("travel_s"), cand.get("guide")
    return max(8.25, abs(guide - hand_x) / s) if (s and guide is not None and abs(guide - hand_x) > 0) else 8.25


def _avg_speed(cand: Candidate) -> float:
    """The route's average speed in the model (u/s), for the foreground's few takeoff checks; 8.25 u/s when unknown."""
    s, end, aim = cand.get("route_s"), cand.get("end_x"), cand.get("aim_x")
    if s and s > 0 and end is not None and aim is not None and abs(end - aim) > 1.:
        return max(8.25, abs(end - aim) / s)
    return 8.25


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
        if guide is not None:
            row, k_arr = go(m, np.zeros(ROLL_T, np.int64), k_hand, guide, run_only=True)
            if k_arr is None:
                return no("guide not reached in the model")
            travel = (k_arr - k_hand) * m.dt
            depart = lock - RESERVE_S - travel
            if depart < q.hand.t - 1e-9:
                det.update(travel_s=travel, latest_depart=depart)
                return no("guide arrives after the aim reserve")
            det.update(depart_t=depart, travel_s=travel)
        # the way back from the guide, against its descent (a dash's cooldown and the turn are the model's)
        row = np.zeros(ROLL_T, np.int64)
        k_aim = k_take
        if guide is not None:
            row, k_aim = go(m, row, k_of(depart), guide, run_only=True)
            if k_aim is None:
                return no("guide not reached in the model")
        row, k_back = go(m, row, max(k_take, k_aim), S)
        if k_back is None:
            return no("the way back not reached in the model")
        by = t_to + DESCENT_S
        det.update(return_arrive_t=t_of(k_back), by_t=by, end_x=S, route_s=t_of(k_back) - t_to)
        if t_of(k_back) > by - .05:
            return no("the way back arrives after its body comes down")
        start = None if depart is None else depart - (GUIDE_START_X - 1.) * det["travel_s"]
        return Candidate("lure", True, None, "lure_wait" if guide is not None else "lure_hold", 1., tuple(det.items())), \
            dict(guide=guide, depart=depart, need=need, aim_x=aim_x, start=start)

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
        from ssbot.core.forum import FLOOR_Y
        row0, k_aim = go(m, np.zeros(ROLL_T, np.int64), k_hand, stance)
        start = stance if (k_aim is not None and k_aim <= k_take) else float(m.xs(row0[None])[0][min(ROLL_T, m.off + k_take)])
        r = Roller(m.kin.initial_state(m.params, start, FLOOR_Y + m.params.foot), np.zeros(1, np.int64), m.kin.HoldState.idle(1),
                   m.params, m.terrain)
        row, k_x = go(r, np.zeros(ROLL_T, np.int64), 0, X)
        if k_x is None:
            return no("the retreat not reached in the model")
        by = land_t + (RUNE_ON_S if cast else 0.)
        late = max(0., q.hand.t - t_to)
        leg_s = (r.off + k_x) * r.dt + late
        det.update(arrive_t=t_to + leg_s, by_t=by, end_x=X, route_s=leg_s)
        if t_to + leg_s > by - .05:
            return no("the retreat arrives after the hazard")
        hammer_x = land + out * (q.reach_j + half_in)
        x = r.xs(row[None])[0]
        i_land = min(len(x) - 1, int(round(FLIGHT_S / r.dt)))
        if (x[i_land] - hammer_x) * out < 0:
            return no("still under the landing hammer on the retreat")
        return Candidate("attack", True, None, "attack_aim", 1., tuple(det.items())), dict(target=near.iid)

    cand_l, f_l = lure()
    cand_a, f_a = attack()
    hazard_end = land_t + (RUNE_OVER_S if cast else 5 / 60.)
    made = dict(out=out, f=out, reach=reach, family=J.family, jumper=J.iid, other=G.iid, other_family=G.family, lock_t=lock, take_t=t_to,
                land_t=land_t, stage=q.stage, need_back=(f_l or {}).get("need"), half_in=half_in, pad=q.pad, wall_x=wall,
                walker_x0=G.x, walker_v=closing, speed=max(_avg_speed(cand_l), _avg_speed(cand_a)),
                guide_speed=_guide_speed(cand_l, q.hand.x), latest_depart=(f_l or {}).get("depart"))
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
              on=(("hazard_over", "lure_slash"),)),
        Phase("lure_slash", target=gid, attack="side", stance=("front", gid), no_hit=(jid,), replaceable=False,
              on=(("in_reach", DONE),)),
        Phase("attack_aim", target=(f_a or {}).get("target", gid), attack="side", stance=("front", (f_a or {}).get("target", gid)),
              no_hit=(() if (f_a or {}).get("target", gid) == jid else (jid,)),
              on=(("takeoff_retreat", "attack_retreat"), ("takeoff_blocked", BLOCKED), other_move)),
        # Coming back: the body standing nearer to her then, by the observed landing (written here, read when the hazard ends).
        Phase("attack_retreat", target=jid, stance=("retreat",), suppress_hits=True, ground=True, replaceable=False,
              on=(("back_jumper", "attack_back_jumper"), ("back_other", "attack_back_other"))),
        Phase("attack_back_jumper", target=jid, attack="side", stance=("front", jid), replaceable=False, on=(("in_reach", DONE),)),
        Phase("attack_back_other", target=gid, attack="side", stance=("front", gid), no_hit=(jid,), replaceable=False,
              on=(("in_reach", DONE),)),
    ]
    if f_l is not None and f_l.get("guide") is not None:
        take = (("takeoff_return", "lure_return"), ("takeoff_retreat", "attack_retreat"), ("takeoff_blocked", BLOCKED), other_move)
        phases.append(Phase("lure_wait", target=gid, stance=("x", q.hand.x), no_hit=(jid,), on=take + (("too_late", "lure_late"),),
                            at=(f_l["start"] - m.off * m.dt, "lure_go")))
        phases.append(Phase("lure_go", target=jid, stance=("x", f_l["guide"]), suppress_hits=True,
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
    hand = hand_back(Roller(S, np.zeros(1, np.int64), hold, params, terrain), 0., 30.)
    J = Body(1, 24., 0., 22., 26., "Jump Antic", "CC_JUMP")
    W = Body(2, 40., 0., 38., 42., "Idle", None)
    q = Request("middle", "aim", (1, 0.), 1, 0., J, W, 0, 0., None, None, None, None, hand, .25, .25, 14.01, 48.99, 2., .25, 4., 7.76,
                S, np.zeros(1, np.int64), hold)
    generate(q, params, terrain)
    q = Request("cluster", "aim", (1, 0.), 2, 0., Body(1, 36., 0., 34., 38., "Jump Antic", "CC_JUMP"), W, -1, 0., None, None, None,
                None, hand, .25, .25, 14.01, 48.99, 2., .25, 4., 7.76, S, np.zeros(1, np.int64), hold)
    generate(q, params, terrain)


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
    both, antic only, the other one neither in a near antic nor in the air."""
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
    if region in ("left", "right") and s.state in ANTIC and o.state not in NEAR | AIR:
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
        self.send_s = 0.
        self.last_stance: dict = {}
        self.no_plan: dict = {}            # scene -> the reason of the latest explicit no plan
        self.latency: list = []            # (event -> adoptable ms, event -> publication ms, build ms, ticks)
        self.requests = self.adopted = 0
        self.tick_n = 0
        self.worker_failed = None
        self._model_set = (None, None)

    # ---- the channel ----

    def _channel(self, inp):
        ch = self.channel
        if ch is None and INLINE and inp is not None:
            from .l2_plan_worker import InlineChannel
            ch = self.channel = InlineChannel(inp.params, int(INLINE))
        if ch is None and self.worker_failed is None:
            self.worker_failed = "no plan channel (the policy's startup did not make one)"
        if ch is not None and inp is not None and (inp.params is not self._model_set[0] or inp.terrain is not self._model_set[1]):
            self._model_set = (inp.params, inp.terrain)
            ch.set_model(inp.params, inp.terrain)
        return ch

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
        self.hand = None
        if (jumping or ex.plan is not None) and inp is not None:
            roller = Roller(inp.S0, inp.prefix, inp.hold, inp.params, inp.terrain)
            self.hand = hand_back(roller, t, sc.hx)
            self.hand_free_index = roller.off
            self.send_s = roller.off * roller.dt
        self._take_result(sc)
        plan = ex.plan
        inst = None if plan is None else self._instance_of(sc, plan.instance[0])
        ex.step(t, lambda ph: self._events(sc, ph), self._values(sc), inst)
        self._resolved = None
        self._request(sc)
        self.changed = ex.changed
        self.notes = self.notes + ex.notes

    def _values(self, sc) -> dict:
        plan = self.exec.plan or self.exec.pending
        known = self.hand is not None and self.hand.known
        out = {"hand_x": self.hand.x if known else None,
               # a free hero's hand-back only follows the clock: it asks for nothing; a locked one's can pass a departure
               "hand_t": self.hand.t if (known and self.hand.index > self.hand_free_index) else None}
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
        for seq in [s for s in self.sent if s <= pub.sequence]:
            del self.sent[seq]
        values = dict(self._values(sc))
        values.update(self._walker_err(sc, plan))
        state, why = self.exec.offer(plan, sc.t, self._instance_of(sc, plan.instance[0]), values)
        if self.waiting is not None and (info is None or not self.sent):
            self.waiting = None
        now_ns = time.perf_counter_ns()
        rec = dict(what="result", state=state, reason=why, scene=plan.scene, generation=plan.generation, status=plan.status,
                   sequence=pub.sequence, build_ms=round(float(pub.build_ms), 3), selected=plan.selected,
                   candidates=[dict(name=c.name, feasible=c.feasible, reason=c.reason, start=c.start,
                                    **{k: _num(v) for k, v in c.detail}) for c in plan.candidates],
                   plan=dict(made_t=plan.made_t, aim_deadline=plan.aim_deadline, valid_until=plan.valid_until,
                             **{k: _num(v) for k, v in plan.detail}))
        if info is not None:
            rec.update(event=info["why"], observed_f=info["f"], observed_t=info["t"], event_to_adoptable_ms=round((now_ns - info["ns"]) / 1e6, 3),
                       event_to_published_ms=round((pub.origin - info["ns"]) / 1e6, 3), ticks=self.tick_n - info["tick"],
                       before_lock=None if plan.aim_deadline is None else sc.t < plan.aim_deadline)
            if state == "adopted":
                self.adopted += 1
                self.latency.append((rec["event_to_adoptable_ms"], rec["event_to_published_ms"], rec["build_ms"], rec["ticks"]))
        self.notes.append(rec)
        if plan.status != "ok":
            self.no_plan[plan.scene] = plan.reason

    # ---- events: observations -> the names the current phase waits for ----

    def _events(self, sc, phase) -> list:
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
            out.append("takeoff_" + self._resolve(sc, plan, s, o, m))
        if "other_move" in names and (o is None or o.family != plan.get("other_family")):
            out.append("other_move")
        if "other_gone" in names and (o is None or o.state not in STANDING):
            out.append("other_gone")
        if "gap_closed" in names and o is not None and self._gap_closed(sc, plan, s, o):
            out.append("gap_closed")
        if "too_late" in names and self._too_late(sc, plan, phase):
            out.append("too_late")
        if "arrived" in names and phase.stance and phase.stance[0] == "x" and abs(sc.hx - phase.stance[1]) <= ARRIVE_U:
            out.append("arrived")
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
        if "landed" in names and sc.grounded:
            out.append("landed")                   # a completion confirmation only, no admission
        if "response_over" in names and s.family not in JUMPS and not (
                s.iid in sc.tac.rune and sc.t <= sc.tac.rune[s.iid][3]):
            out.append("response_over")
        return out

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
        lock = plan.get("lock_t")
        if phase.at is not None:
            # her lock ends past the written latest departure
            latest = plan.get("latest_depart")
            return latest is not None and self.hand is not None and self.hand.known and self.hand.t > latest + 1e-6
        if lock is None or not phase.stance or phase.stance[0] != "x":
            return False
        start = max(sc.t, self.hand.t) if (self.hand is not None and self.hand.known) else sc.t
        return start + max(0., abs(sc.hx - phase.stance[1]) - ARRIVE_U) / max(1., plan.get("guide_speed")) > lock

    def _bounced(self, sc, o) -> bool:
        from ssbot.core.worldstate import Ev
        for ev in getattr(sc.ws, "events", ()) or ():
            if ev.kind == Ev.HIT_DEALT and ev.data.target_id == o.iid and "DownSlash" in str(ev.data.src or ""):
                return True
        return False

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

    def _resolve(self, sc, plan, s, o, m) -> str:
        if getattr(self, "_resolved", None) is not None:
            return self._resolved
        route, why = (self._resolve_middle if plan.scene == "middle" else self._resolve_cluster)(sc, plan, s, o, m)
        self._resolved = route
        rec = dict(what="takeoff", route=route, reason=why, landing=m.get("land"), by_v=m.get("by_v"), hx=sc.hx,
                   walker_x=None if o is None else float(o.pos[0]), f=sc.frame, selected=self.exec.selected)
        self.notes.append(rec)
        if route in ("return", "over"):
            self.exec.record(plan.instance, "departed", sc.t)   # the jump she left: not to be intercepted back
        return route

    def _stand_now(self, sc, plan, o, m) -> float | None:
        geo = sc.geo
        land = m.get("land")
        if geo is None or land is None or o is None or o.iid not in geo["bodies"]:
            return None
        from .gauntlet import JT
        a, b = geo["bodies"][o.iid]
        vx = self._vx(sc, o)
        f = plan.get("f")
        shift = vx * WALK_LOOK_S if (o.state == "Walk" and vx * f < 0) else 0.
        return stand_x(land, f, plan.get("reach"), a, b, float(o.pos[0]), geo["left"], geo["right"], JT["pad"], JT["gap_u"],
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

    def _resolve_middle(self, sc, plan, s, o, m):
        tac, t, f = sc.tac, sc.t, plan.get("f")
        if m.get("face") in (-1, 1) and m["face"] != f:
            return "blocked", "the jump's facing differs from the plan's"
        if m.get("land") is None:
            return "blocked", "landing unknown at the take-off"
        planned = plan.get("landings") or ()
        if planned and min(abs(m["land"] - v) for v in planned) > LAND_SUPPORT_U:
            return "blocked", "the observed landing is outside the plan's support"
        back = (m["x0"] - sc.geo["xa"] if f > 0 else sc.geo["xb"] - m["x0"]) if (sc.geo is not None and m.get("x0") is not None) else math.inf
        wall_bound = back < JB.CFG["push_from_u"]
        stand = None if wall_bound else self._stand_now(sc, plan, o, m)
        why = "wall landing is only a bound" if wall_bound else "middle ground footprint closed"
        if stand is not None:
            # The written geometry (the jump's whole forward reach, the walker's body and its closing) and the walker's own
            # state. The forecast's union is not asked here: its coarse placements cover every stance near an idle Clapper
            # (replay m_guide: by both Clappers from 0.19 s, committed part too), which made this route unreachable. Each
            # row toward it still goes through the planner's support.
            due = o is not None and o.iid in tac.rune and t <= tac.rune[o.iid][3] and (
                (stand - tac.rune[o.iid][0]) * tac.rune[o.iid][1] > 0)
            if o is not None and o.family in ATTACK_FAMS:
                why = "the walker is in an attack move"
            elif due:
                why = "the walker's rune circle is due over the stance"
            else:
                self.last_stance["stand"] = stand
                return "return", "the middle still has room"
        # the walker closed it (or it never had it): the prepared routes, the endpoint farther from the wall
        take_t = m.get("air_at", t)
        speed = max(1., plan.get("speed"))
        options = []
        prepared = plan.get("prepared") or ()
        if "under" in prepared:
            spot = self._spot_now(sc, plan, m)
            if (spot is not None and abs(spot - sc.hx) <= UNDER_ROW_U
                    and t + abs(spot - sc.hx) / speed <= take_t + DESCENT_S - .05):
                options.append(("under", (spot - sc.geo["xa"]) if f > 0 else (sc.geo["xb"] - spot)))
        if "over" in prepared and o is not None and o.state in STANDING:
            far = self._far_now(sc, plan, o)
            room = None if far is None else (sc.geo["xb"] - far if f > 0 else far - sc.geo["xa"])
            in_time = t + abs(float(o.pos[0]) - sc.hx) / speed <= take_t + FLIGHT_S - .05
            past_hammer = (sc.hx - (m["land"] + f * plan.get("reach"))) * f >= 0
            if room is not None and room >= .5 and (in_time or past_hammer):
                options.append(("over", room))
        if not options:
            return "blocked", why + "; no prepared route supported"
        best = max(options, key=lambda v: v[1])
        return best[0], why + "; endpoint room " + ", ".join(f"{a} {b:.2f}" for a, b in options)

    def _resolve_cluster(self, sc, plan, s, o, m):
        t, out = sc.t, plan.get("out")
        if m.get("face") in (-1, 1) and m["face"] != out:
            return "blocked", "the jump's facing differs from the plan's"
        land = m.get("land")
        if land is None or sc.geo is None or o is None:
            return "blocked", "landing or bodies unknown at the take-off"
        take_t = m.get("air_at", t)
        speed = max(1., plan.get("speed"))
        if self.exec.selected == "lure":
            S = float(o.pos[0]) + out * sc.tac.rules.face_u
            need = plan.get("need_back")
            if need is not None and (land - S) * out >= need - .25 and t + abs(S - sc.hx) / speed <= take_t + DESCENT_S - .05:
                return "return", "the way back holds"
        X = land + out * (plan.get("reach") + plan.get("half_in") + plan.get("pad"))
        if (X - plan.get("wall_x")) * out > 0:
            return "blocked", "no room to retreat past the coverage"
        return "retreat", "retreat past the coverage"

    # ---- requests: events only ----

    def _request(self, sc) -> None:
        tac, t = sc.tac, sc.t
        ex = self.exec
        if self.channel is None or getattr(tac, "plan_input", None) is None or self.worker_failed is not None:
            return
        x = self.hand.x if (self.hand is not None and self.hand.known) else sc.hx
        scene = parent_scene(sc.subjects, sc.geo, x)
        plan = ex.plan
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
        elif o.family != last["other_family"]:
            why = "the other one's new move"
        elif (o.state == "Walk") != last["walking"] and not (plan is not None and running and ex.phase is not None
                                                             and not ex.phase.replaceable):
            why = "the walker started walking" if o.state == "Walk" else "the walker stopped walking"
        elif running and plan.aim_deadline is not None and t >= plan.aim_deadline:
            return                                # past the lock a running plan is executed, not regenerated
        elif running:
            if ex.phase is not None and not ex.phase.replaceable:
                return
            vals = self._values(sc)
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
            if abs(o_x - last["walker_x"]) >= SOFT_WALKER_U or abs(x - last["hand_x"]) >= SOFT_HAND_U:
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
                    JT["reach_j"], S0, prefix, _copy_hold(hold))
        seq = self.channel.request(key, q)
        self.sent[seq] = dict(ns=time.perf_counter_ns(), f=sc.frame, t=t, why=why, tick=self.tick_n)
        self.requests += 1
        if self.waiting is None or self.waiting[0] != name:
            self.waiting = (name, t)
        self.last_request = dict(key=key, walker_x=o_x, hand_x=x, hand_t=hand.t if hand.known else t, other_family=o.family, stage=stage,
                                 walking=o.state == "Walk")
        self.notes.append(dict(what="request", scene=name, stage=stage, generation=self.generation, sequence=seq, why=why, f=sc.frame,
                               t=t, hand_x=x, hand_t=None if not hand.known else hand.t, walker_x=o_x, jumper_x=J.x))

    # ---- what the tactic units read ----

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
        elif kind == "stand":
            out = self._stand_now(sc, plan, o, m)
        elif kind == "behind":
            out = self._spot_now(sc, plan, m)
        elif kind == "head":
            target = next((v for v in sc.subjects if v.iid == ref[1]), None)
            out = None if target is None else float(target.pos[0])
        elif kind == "far":
            out = self._far_now(sc, plan, o)
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
                   channel=None if self.channel is None else self.channel.mode, worker_failed=self.worker_failed)
        if self.notes:
            row["notes"] = list(self.notes)
        return row

    def stats(self) -> dict:
        lat = self.latency
        q = (lambda i, p: round(float(np.percentile([v[i] for v in lat], p)), 3) if lat else None)
        return dict(requests=self.requests, adopted=self.adopted, event_to_adoptable_ms_p50=q(0, 50), event_to_adoptable_ms_p99=q(0, 99),
                    event_to_published_ms_p50=q(1, 50), build_ms_p50=q(2, 50), channel=None if self.channel is None else self.channel.status())


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
