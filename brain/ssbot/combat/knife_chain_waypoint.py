"""The bounded floor approach of the jump plans (Task 182; SSBOT_FORUM_TWO_PLAN only, Sol seq 255 F1).

Ordinary planner rows arrive by a row's end and stop at a hazard's edge, so a plan's "she is there by then" needs its own key
owner: one Run to one x by one frame, under the B2 transaction (a new dash through the motion it locks, each step through every
owner's support, her real prefix, HoldFilter and input). It decides nothing: L2's running phase names the place and the deadline,
withdrawing it hands the Run back at once, the keys already sent staying the next owner's prefix. No jump, no attack, no search.

route() is what a plan counts on, next_mask() what the Run sends: the same choice from the same model. The run when it arrives
by the deadline, else the dash at the first frame it can start (an edge: a key held through a cooldown never starts one), held into
the sprint, released where she stops at the place. Held dash keys are not re-decided: releasing them ends the sprint.

A place past a body (kind "out", the over route's far side after a real bounce): no key that takes her box into that body once her
modelled invulnerability is over (the action layer's own rule; of 51 real DownSlash hits the only one whose box met the struck body later
than that, at hit + 9, lost health: SCANAFTER182). Rows stop at a body, so this Run takes her over it: the run that passes above it from
the bounce, else the dash, else she waits while the bounce lifts her, off its x span while under its top.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from ssbot.knowledge import kinematics as K

PROGRAM = "waypoint"
FAMILY = "WAYPOINT"         # the Run's own move label; its failure responsibility is the jump it is about (knife_chain_air_native)
TOL_U = .2
REST_F = 46                 # frames rolled past a release to see where she stops
MAX_F = 150                 # a route longer than this is not one of these
EDGE_TRY = tuple(range(0, 40, 3))    # the key indices tried for a dash edge when her keys before it hold a dash of their own


@dataclass(frozen=True)
class WaypointGoal:
    x: float
    by_f: int               # the frame she should be there by
    kind: str               # guide / under / retreat
    source: int             # the Clapper whose jump this is about
    plan: tuple             # (instance, generation, phase): which running phase asks; another one hands the Run back
    tol: float = TOL_U
    over: tuple | None = None   # (x0, y0, x1, y1) a body between her and the place she must pass above
    family: str | None = None   # the jump's family: who answers for a failure of this Run


def _key(direction: int) -> int:
    return K.B_RIGHT if direction > 0 else K.B_LEFT


def _arrival(xs, goal, direction, tol):
    reached = (xs - goal) * direction >= -tol
    return int(np.argmax(reached)) if reached.any() else None


def dash_ready_k(start, off, dt, k0=0) -> int:
    """The first key index at or after k0 whose edge can start a dash, from her cooldown. A dash in the row before k0 is the
    caller's to try (dash_edge)."""
    cd = float(np.asarray(start, float).reshape(-1)[K.DASH_CD])
    return max(int(k0), int(math.ceil(max(0., cd) / dt)) - int(off) + 1)


def dash_edge(m, row, k0, key) -> int | None:
    """The first key index at or after k0 where the edge really starts a dash in the model, with her keys before it."""
    if not np.any(row[:k0] & K.B_DASH):
        k = dash_ready_k(m.start, m.off, m.dt, k0=k0)
        return k if k < row.shape[0] else None
    tries = [k0 + d for d in EDGE_TRY if k0 + d + 3 < row.shape[0]]
    if not tries:
        return None
    rows = np.tile(row, (len(tries), 1))
    for i, k in enumerate(tries):
        rows[i, k0:k] = key
        rows[i, k:] = key | K.B_DASH
    modes = m.rollout(rows).mode
    for i, k in enumerate(tries):
        j = m.off + k
        if np.any(modes[i, j:j + 4] == K.M_DASH):
            return k
    return None


def route(m, row, k0, goal, by_k=None, tol=TOL_U, release=True):
    """From key index k0, after the keys in row: to goal along the model. (row, arrival key index or None, how). The run when it
    arrives by by_k, else the dash released where she stops at the goal; by_k None: the fastest. release False: arrival only."""
    x = m.xs(row[None])[0]
    i0 = m.off + k0
    if i0 >= x.shape[0]:
        return row, None, "none"
    if abs(goal - x[i0]) <= tol:
        return row, k0, "there"
    d = 1 if goal > x[i0] else -1
    key = _key(d)
    run = row.copy()
    run[k0:] = key
    a_run = _arrival(m.xs(run[None])[0][i0:], goal, d, tol)
    if a_run is not None and by_k is not None and k0 + a_run <= by_k:
        run[k0 + a_run:] = 0
        return run, k0 + a_run, "run"
    k_dash = dash_edge(m, row, k0, key)
    if k_dash is None:
        if a_run is None:
            return row, None, "none"
        run[k0 + a_run:] = 0
        return run, k0 + a_run, "run"
    dash = row.copy()
    dash[k0:k_dash] = key
    dash[k_dash:] = key | K.B_DASH
    a_dash = _arrival(m.xs(dash[None])[0][i0:], goal, d, tol)
    if a_dash is None or (a_run is not None and a_run <= a_dash):
        if a_run is None:
            return row, None, "none"
        run[k0 + a_run:] = 0
        return run, k0 + a_run, "run"
    if not release:
        return dash, k0 + a_dash, "dash"
    # released where she stops at the goal
    last = k0 + a_dash
    first = max(k_dash + 1, last - 14)
    rows = np.tile(dash, (last - first + 1, 1))
    for i, r in enumerate(range(first, last + 1)):
        rows[i, r:] = 0
    xs = m.xs(rows)[:, i0:]
    for i, r in enumerate(range(first, last + 1)):
        stop = min(xs.shape[1] - 1, r - k0 + REST_F)
        if (xs[i, stop] - goal) * d >= -tol:
            a = _arrival(xs[i], goal, d, tol)
            return rows[i].copy(), k0 + (a if a is not None else stop), "dash"
    return rows[-1].copy(), last, "dash"


class SimRoller:
    """route()'s model on the B2 tick's ChainSim."""

    def __init__(self, sim):
        self.sim, self.off, self.dt = sim, sim.off, float(sim.params.frame_time)
        self.start = np.asarray(sim.start, float).reshape(-1)

    def rollout(self, rows):
        return self.sim.roll(np.asarray(rows, np.int64))

    def xs(self, rows):
        return self.rollout(rows).centre[:, :, 0]


def _meets(m, rows, body) -> bool:
    """Her box meets the body, out of her invulnerability, on a step this tick's keys can still change (key index 0 acts from m.off on)."""
    r = m.rollout(rows)
    b, fl = r.box[0, m.off + 1:], np.asarray(r.flags[0, m.off + 1:])
    hit = (b[:, 0] <= body[2]) & (b[:, 2] >= body[0]) & (b[:, 1] <= body[3]) & (b[:, 3] >= body[1])
    return bool(np.any(hit & ((fl & K.F_INVULN) == 0)))


def next_mask(sim, goal: WaypointGoal, f: int):
    """This tick's keys for a WaypointGoal from the actual model state. (mask, what): what "go" / "dash": keys to send, "wait": a body
    to pass above and the bounce still lifting her (keys off its x span, or none), "arrived": she is there or stops there with no more
    keys, "late": it cannot arrive by its frame from here."""
    m = SimRoller(sim)
    by_k = int(goal.by_f) - (int(f) + 2)
    rest = m.xs(np.zeros((1, REST_F), np.int64))[0]
    x0, stop = float(rest[m.off]), float(rest[-1])
    d = 1 if goal.x > x0 else -1
    if abs(goal.x - x0) <= goal.tol or (stop - goal.x) * d >= -goal.tol:
        return 0, "arrived"
    key = _key(d)
    held = bool(int(np.asarray(sim.prefix).reshape(-1)[-1]) & K.B_DASH)
    if held and np.any(np.isin(m.rollout(np.full((1, 4), key | K.B_DASH, np.int64)).mode[0], (K.M_DASH, K.M_SPRINT))):
        return key | K.B_DASH, "dash"       # in flight or running: releasing it ends the sprint: held until she stops at the place
    T = int(min(MAX_F, max(8, by_k + 8)))
    body = goal.over
    if body is not None and (x0 - (body[2] if d > 0 else body[0])) * d >= 0:
        body = None                         # past its far edge
    run = np.full((1, T), key, np.int64)
    a_run = _arrival(m.xs(run)[0][m.off:], goal.x, d, goal.tol)
    if a_run is not None and a_run <= by_k and (body is None or not _meets(m, run, body)):
        return key, "go"
    k_dash = 0 if not held else 1           # an edge needs the key released first
    k_dash = max(k_dash, dash_ready_k(m.start, m.off, m.dt))
    row = np.full((1, T), key, np.int64)
    row[0, k_dash:] |= K.B_DASH
    a_dash = _arrival(m.xs(row)[0][m.off:], goal.x, d, goal.tol)
    if body is not None:
        if a_dash is not None and a_dash <= by_k and k_dash == 0 and not _meets(m, row, body):
            return key | K.B_DASH, "dash"
        still = np.zeros((1, REST_F), np.int64)
        if by_k <= 0 or not np.any(m.rollout(still).box[0, m.off + 1:, 1] >= body[3]):
            return None, "late"
        return (_key(-d) if _meets(m, still, body) else 0), "wait"
    if a_dash is None or a_dash > by_k:
        return None, "late"
    return (key | K.B_DASH, "dash") if k_dash == 0 else (key, "go")
