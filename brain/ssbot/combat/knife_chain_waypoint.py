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
    by_f: int               # the frame she should be there by (kind press: the frame the press still counts until; no arrival is owed)
    kind: str               # guide / under / retreat / press
    source: int             # the Clapper whose jump this is about
    plan: tuple             # (instance, generation, phase): which running phase asks; another one hands the Run back
    tol: float = TOL_U
    over: tuple | None = None   # (x0, y0, x1, y1) a body between her and the place she must pass above
    family: str | None = None   # the jump's family: who answers for a failure of this Run
    over_iid: int | None = None   # kind "vault" (Task 182 seq 312 #385): the Clapper whose body `over` is (her fall slash's target)
    land: tuple | None = None     # kind "vault": (lo, hi) the band her centre lands in past the body (else within tol of x)


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
    last = k0 + a_dash
    row, k = _released(m, dash, k0, max(k_dash + 1, last - 14), last, goal, d, tol)
    return row, k, "dash"


def _released(m, dash, k0, first, last, goal, d, tol):
    """The dash row released at the first key index of first..last whose rest stop (REST_F frames on, within the row) reaches the
    goal, and her arrival key index: route()'s dash release, what a plan counts on. The Run's own release on the route it checks is
    next_mask's "arrived" by its own glide (_handback, route_keys; Sol seq 273)."""
    i0 = m.off + k0
    rows = np.tile(dash, (last - first + 1, 1))
    for i, r in enumerate(range(first, last + 1)):
        rows[i, r:] = 0
    xs = m.xs(rows)[:, i0:]
    for i, r in enumerate(range(first, last + 1)):
        stop = min(xs.shape[1] - 1, r - k0 + REST_F)
        if (xs[i, stop] - goal) * d >= -tol:
            a = _arrival(xs[i], goal, d, tol)
            return rows[i].copy(), k0 + (a if a is not None else stop)
    return rows[-1].copy(), last


def _arrived_at(m, row, lo, hi, goal, tol):
    """next_mask's "arrived" on the Run's later ticks (Sol seq 273): the first key index j in lo..hi at which, with row's keys before
    j sent and none from j, she is there (x at j) or her rest stop (REST_F frames of no keys from j) reaches the goal, as next_mask
    reads it on its tick f + j. Rolled REST_F frames past hi, never cut at the row's own length. None: none in lo..hi."""
    lo, hi = max(int(lo), 1), int(hi)
    if hi < lo:
        return None
    js = range(lo, hi + 1)
    rows = np.zeros((hi - lo + 1, hi + REST_F), np.int64)
    w = min(row.shape[0], hi + REST_F)
    rows[:, :w] = row[:w]
    for i, j in enumerate(js):
        rows[i, j:] = 0
    xs = m.xs(rows)
    for i, j in enumerate(js):
        x0 = float(xs[i, m.off + j])
        d = 1 if goal > x0 else -1
        if abs(goal - x0) <= tol or (float(xs[i, m.off + j + REST_F - 1]) - goal) * d >= -tol:
            return int(j)
    return None


def _handback(m, row, hi, goal, tol, span=4):
    """The tick the Run hands back on (_arrived_at over 1..hi), searched down from hi in windows of span, doubled each step down:
    her keys go toward the goal, so once her rest stop reaches it, it does on every later tick; the window whose first index has
    not arrived holds the first tick that has. None: not even at hi."""
    found, top, span = None, int(hi), int(span)
    while top >= 1:
        a = max(1, top - span + 1)
        j = _arrived_at(m, row, a, top, goal, tol)
        if j is None:
            return found
        if j > a or a == 1:
            return j
        found, top, span = j, a - 1, span * 2
    return found


def _late_at(m, key, by_k, goal, tol, d, near=8, probes=8):
    """next_mask's "late" on the later ticks of a Run whose new dash its lock refuses every time (Sol seq 276): that dash was asked for
    at once (its cooldown spent, none held), so on each later tick j it is asked for from j again, after the direction key sent
    before it; her run alone is late from the start (the same keys on). The first j >= 1 whose dash from j no longer arrives by
    by_k (late at by_k + 1 whatever she does), each check one row of by_k + 2 keys (d: her direction to the goal). A later dash
    arrives later except within a frame or so of the deadline (the frame phase; a dash pressed on some frames does not start), so:
    a search for that boundary with `probes` ticks checked in one batch each round, then the near ticks below it not yet checked in
    one batch, further down while the earliest late found is the batch's first."""
    hi = max(int(by_k) + 1, 1)
    known = {hi: True}

    def lates(js):
        todo = [j for j in js if j not in known]
        if todo:
            rows = np.full((len(todo), hi + 1), key, np.int64)
            for i, j in enumerate(todo):
                rows[i, j:] |= K.B_DASH
            xs = m.xs(rows)
            for i, j in enumerate(todo):
                a = _arrival(xs[i, m.off:], goal, d, tol)
                known[j] = a is None or a > by_k
        return [known[j] for j in js]

    lo, top = 1, hi                             # late at top
    while lo < top:
        js = sorted({int(round(v)) for v in np.linspace(lo, top - 1, min(int(probes), top - lo))})
        res = lates(js)
        i = next((n for n, late in enumerate(res) if late), None)
        if i is None:
            lo = js[-1] + 1
        else:
            top = js[i]
            lo = js[i - 1] + 1 if i > 0 else lo
            if i == 0 and js[0] == lo:
                break
    j = top
    while j > 1:
        js = list(range(max(1, j - int(near)), j))
        first = next((jj for jj, late in zip(js, lates(js)) if late), None)
        if first is None:
            break
        j = first
        if first > js[0]:
            break
    return int(j)


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
        if goal.kind != "press":
            return None, "late"
        # Task 182 seq 311: a press owes no arrival, only as far toward the first one as she gets by its aim: the dash when it takes her farther by then
        i = m.off + max(by_k, 0)
        if k_dash == 0 and (float(m.xs(row)[0][i]) - float(m.xs(run)[0][i])) * d > 0:
            return key | K.B_DASH, "dash"
        return key, "go"
    return (key | K.B_DASH, "dash") if k_dash == 0 else (key, "go")


# ---- Task 182 seq 312 #385 (Sol REVIEW384 1-2; the person's 1.2.2: over N into the middle once both hammer stages of F's slam are over) ----
# kind "vault": a bounded way over one body to one place from her actual model state, on the ground or in the air. No route above a body
# exists from the floor without a jump: a full jump keeps her box over an Idle top for 28 frames, 3.8 u of run, short of its 4.5 u span and her
# own width; its free air dash near the apex keeps her over it for 4.9 - 6.2 u (design probe s312/jump385.py). So: one jump (J held a few fixed
# lengths, on the ground only), the key toward the place from the first frame, the free air dash at a few fixed frames, then the key released
# on a grid once she is past the body. Chosen once on an event and then followed as an absolute row (the caller scans it).
VAULT_JH = (16, 20, 30)           # J held this many key indices from the first free mask frame (30: the full jump; 12 never cleared a top)
VAULT_KEY = (0, 6, 10, 14)        # ... the key toward the place from this key index (next to the body she rises first; in the air: 0)
VAULT_DASH = (None, 0, 4, 14, 18, 22)   # the free air dash's first key index (two frames of DASH), None: no dash
VAULT_DASH_GROUND = (None, 14, 18, 22)  # ... from the floor: only once the jump has lifted her (an earlier one is a floor dash into the body)
VAULT_REL_STEP = 2                # the release grid of the side key past the body (key indices)
VAULT_REL_N = 12                  # ... at most this many releases tried per kept recipe
VAULT_PAD = .25                   # her box kept this far off the body's sides on the way over (out of her invulnerability)
VAULT_PAD_TOP = .1                # ... and this far over its top (BODY_TOP is the recorded collider's top; at .25 no floor start 1-2 u
#                                   from an Idle body cleared it: the full jump's box crosses the near edge 0.16 u over the top, s312/vault385pad.py)
VAULT_H = 64                      # key indices rolled (a full jump lands within 55, a late dash within 49 from the floor)
VAULT_ALTS = 5                    # the next-best rows returned with the best (one per landing place, by the same order): the caller scans them
#                                   in that order when a better one's whole route is blocked (C14 sy14_122: the nearest landing met the slammer's
#                                   move forecast)


def _air_index(flags, off):
    """(takeoff, landing) rollout indices: the first airborne index from off on and the first ground index after it, or None each."""
    g = (np.asarray(flags) & K.F_GROUND) != 0
    idx = np.arange(len(g))
    air = np.flatnonzero(~g & (idx >= off))
    if not len(air):
        return None, None
    land = np.flatnonzero(g & (idx > air[0]))
    return int(air[0]), (int(land[0]) if len(land) else None)


def vault_row(sim, goal: WaypointGoal, f: int):
    """kind "vault": over goal.over to goal.x by goal.by_f from her actual model state (the in-flight prefix and hold included). The finite
    rows above in two batched rolls: the recipes with the key held throughout, then for each recipe that clears the body the side key released
    on a grid past it. A row counts when her box never meets the body grown by VAULT_PAD (sides) / VAULT_PAD_TOP (top) out of her
    invulnerability, she is past its far edge
    before she lands, and she lands with her centre inside goal.land (else within goal.tol of goal.x) by the frame. The one landing nearest
    goal.x (then no dash before a dash, then the shorter hold, then the earlier landing): dict(masks: from key index 0 through the landing,
    land_k: the landing's key index, land_box, takeoff_k, recipe, alts: up to VAULT_ALTS next rows in that order, one per landing place),
    or None (no row; past the body already)."""
    m = SimRoller(sim)
    body = goal.over
    if body is None:
        return None
    zero = m.rollout(np.zeros((1, 2), np.int64))
    x0 = float(zero.centre[0, m.off, 0])
    d = 1 if goal.x > x0 else -1
    key = _key(d)
    far = float(body[2] if d > 0 else body[0])
    grown = (float(body[0]) - VAULT_PAD, float(body[1]), float(body[2]) + VAULT_PAD, float(body[3]) + VAULT_PAD_TOP)
    b0 = zero.box[0, m.off]
    if (float(b0[0]) >= grown[2]) if d > 0 else (float(b0[2]) <= grown[0]):
        return None                     # past the body already: no vault (the caller's place is no vault any more)
    ground = bool(int(zero.flags[0, m.off]) & K.F_GROUND)
    held_j = bool(int(np.asarray(sim.prefix).reshape(-1)[-1]) & K.B_JUMP)
    jh = VAULT_JH if ground or held_j else (0,)
    keys = VAULT_KEY if ground else (0,)
    k_dash = dash_ready_k(m.start, m.off, m.dt)
    air_free = float(m.start[K.AIRDASHED]) <= 0
    dashes = [dk for dk in (VAULT_DASH_GROUND if ground else VAULT_DASH) if dk is None or (dk >= k_dash and air_free)]
    by_k = int(goal.by_f) - (int(f) + 2)
    recipes = [(h, s, dk) for h in jh for s in keys for dk in dashes if dk is None or dk >= s]
    rows = np.zeros((len(recipes), VAULT_H), np.int64)
    for i, (h, s, dk) in enumerate(recipes):
        rows[i, :h] |= K.B_JUMP
        rows[i, s:] |= key
        if dk is not None:
            rows[i, dk:dk + 2] |= K.B_DASH
    lo, hi = (goal.land if goal.land is not None else (float(goal.x) - goal.tol, float(goal.x) + goal.tol))

    def judge(ro, i):
        box, fl = ro.box[i], np.asarray(ro.flags[i])
        t, j = _air_index(fl, m.off)
        if j is None or (t is None and not ground):
            return None
        way = box[m.off + 1:j + 1]
        inv = (fl[m.off + 1:j + 1] & K.F_INVULN) != 0
        hit = ((way[:, 0] <= grown[2]) & (way[:, 2] >= grown[0]) & (way[:, 1] <= grown[3]) & (way[:, 3] >= grown[1])) & ~inv
        if np.any(hit):
            return None
        past = way[:, 0] >= grown[2] if d > 0 else way[:, 2] <= grown[0]
        if not np.any(past):
            return None
        return t, j, int(np.argmax(past)) + m.off + 1

    ro = m.rollout(rows)
    kept = [(i, r) for i in range(len(recipes)) for r in (judge(ro, i),) if r is not None]
    if not kept:
        return None
    rel_rows, meta = [], []
    for i, (t, j, p) in kept:
        k_p = p - m.off
        for r in list(range(k_p, j - m.off, VAULT_REL_STEP))[:VAULT_REL_N] + [None]:
            row = rows[i].copy()
            if r is not None:
                row[r:] &= ~np.int64(K.B_LEFT | K.B_RIGHT)
            rel_rows.append(row)
            meta.append((i, r))
    ro2 = m.rollout(np.stack(rel_rows))
    found = []
    for n, (i, r) in enumerate(meta):
        res = judge(ro2, n)
        if res is None:
            continue
        t, j, p = res
        lb = ro2.box[n, j]
        cx = .5 * (float(lb[0]) + float(lb[2]))
        if not lo <= cx <= hi or j - m.off > max(by_k, 0) + 2:
            continue
        h, s, dk = recipes[i]
        found.append(((abs(cx - float(goal.x)), dk is not None, h, j), n, i, r, t, j, lb))
    if not found:
        return None
    found.sort(key=lambda c: c[0])
    out, seen = [], set()
    for _, n, i, r, t, j, lb in found:
        land = round(.5 * (float(lb[0]) + float(lb[2])), 1)
        if land in seen:
            continue                     # (one row per landing place: the alternatives differ where she comes down)
        seen.add(land)
        h, s, dk = recipes[i]
        out.append(dict(masks=[int(v) for v in rel_rows[n][:j - m.off + 1]], land_k=int(j - m.off),
                        takeoff_k=None if t is None else int(t - m.off), land_box=[float(v) for v in lb],
                        recipe=dict(jump=int(h), key=int(s), dash=dk, release=r), far_edge=far,
                        box=np.asarray(ro2.box[n, :j + 1], float).copy(), flags=np.asarray(ro2.flags[n, :j + 1]).copy()))
        if len(out) >= VAULT_ALTS + 1:
            break
    best = out[0]
    best["alts"] = out[1:]
    return best


def route_keys(sim, goal: WaypointGoal, f: int, mask: int, dash_refused: bool = False):
    """The keys this Run counts on from this tick (Task 182, Sol seq 271 / 272 / 273 / 276), for a check of its whole route: the
    keys it sends itself, from the key it actually sends now (the one its gates passed) up to the tick it hands back, next_mask's
    "arrived" by its own glide (_handback: REST_F frames of no keys past that tick, never cut at the row's length) or its "late".
    The keys in flight at the hand-back are among them; the next owner's first key is the next one, and her glide after it is no
    part of this Run:
      - a dash it starts or holds (DASH in mask): held, as next_mask holds it (releasing it would end the sprint);
      - a dash refused this tick (dash_refused, mask the key it sends instead): the run of that key, the keys it sends while the
        lock keeps refusing every later new dash too, up to next_mask's "late" there (_late_at) or its "arrived", whichever comes
        first; the refused dash is no part of the route (a later tick whose dash passes its lock is checked on that tick's own);
      - otherwise route() on from the next key (a run, or the dash at its cooldown edge, then held as next_mask holds it).
    MAX_F at most. None: from the key sent the model gives no route (a dash or route() with no arrival): nothing to check. A place
    past a body (goal.over) is not one of these: route() has no passage above it. The check made of it only ever hands back; a
    route with no contact is no certificate."""
    m = SimRoller(sim)
    by_k = int(goal.by_f) - (int(f) + 2)
    T = int(min(MAX_F, max(8, by_k + 8)))
    mask = int(mask)
    x0 = float(m.xs(np.zeros((1, 1), np.int64))[0][m.off])
    d = 1 if goal.x > x0 else -1
    until = np.full(max(1, min(MAX_F, by_k + 1)), mask, np.int64)   # (kind press: the keys it counts on when it does not arrive: this key up to its frame)
    if dash_refused and not mask & K.B_DASH:
        if goal.kind == "press":
            return until
        row = np.full(T, mask, np.int64)
        late = _late_at(m, mask, by_k, float(goal.x), goal.tol, d)
        r = _handback(m, row, late, float(goal.x), goal.tol)
        return np.asarray(row[:late if r is None else r], np.int64)
    if mask & K.B_DASH:
        row = np.full(T, mask, np.int64)
    else:
        row = np.zeros(T, np.int64)
        row[0] = mask
        row, k, how = route(m, row, 1, float(goal.x), by_k=by_k, tol=goal.tol)
        if k is None:
            return until if goal.kind == "press" else None
        if how == "dash":
            kd = int(np.argmax((row & K.B_DASH) != 0))
            row = row.copy()
            row[kd:] = row[kd]                  # held from its edge, as next_mask holds it (route()'s own release is a plan's)
    a = _arrival(m.xs(row[None])[0][m.off:], goal.x, d, goal.tol)
    if a is None:
        return until if goal.kind == "press" else None
    r = _handback(m, row, max(int(a), 1), float(goal.x), goal.tol)
    r = max(int(a), 1) if r is None else r
    return np.asarray(row[:r], np.int64)
