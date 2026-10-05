"""Thrown hazards of the Forum on deterministic paths (Forum plan R2, docs/plans/forum_planner_plan.md §4.2, §4.6
projectiles): where a hazard already in the air (or on the floor, waiting to burst) will be, from its observed
state and the arena's physics, instead of the union of every logged flight relative to where it armed (the self
templates of R0, margins up to 3 u).

    hz = HazardTracker(view)
    hz.update(ws)                              # every WorldState: the hazard entities, the physics clock
    paths = hz.paths(origin_t, horizon_s)      # [HazardPath]: circles / boxes on step-quantised paths
    cx, cy, on, grow = p.at(tk)                # [S, T] centres at the time-slack copies, collider on, tube growth

Models (measured on the R0 caches, ssbot.tools.projectile_audit; docs/facts/1.0.30000/forum.md §14):
  Throwing Bell (Choir Bellbearer; circle r 0.425, 1 mask): a Rigidbody2D at 50 Hz, g 60 (gravity scale 1), thrown at
      vy 20 with vx in [-15, 15]; semi-implicit Euler (vy -= g dt, then x += vx dt, y += vy dt). The floor (centre y
      3.428) stops it for one step (vy 0), then the FSM's Bounce sets vy 20 again (vx kept: the first bounce step rises
      BELL_BOUNCE_DY); at a later floor contact it breaks or bounces again (the path keeps bouncing: a superset). A side
      wall sends it back at BELL_WALL_VX. The dome (ssbot.core.forum.DOME) ends the determined path: from its contact
      on the bell is a tube grown by HAZARD_DV_U_S. A nail hit (FSM Nail Hit, collider off ~0.13 s: the Tink redirect)
      sets the speed to 30 u/s along the hit: from the next observation the path is determined again; the planner's
      own hit on a bell is redirect().
  Song Reed Pin Projectile (Reed's javelin; box about 2.0 x 0.1): straight on at 31 u/s from its first exported frame
      until its box meets a side wall or the floor (Stick: collider off).
  rune bomb small (Choir Clapper's Bomb Cast; circle r 2.166 at y 3.67, 1 mask): appears unarmed, arms BOMB_LEAD_S
      later, lit BOMB_LIT_S at most; a cast's row is the first bomb at x0 then pairs at x0 +- 4.2 k, a step every 9 or
      10 frames (the FSM's 0.15 s wait): once a row's first bomb is seen, every later pair is placed before it appears,
      timed from the row's latest step seen (a side the bomb pool could not serve comes later or never: tracked from
      its appearance on).
  rune slam (the Jump Cast's; circle r 7.187 at y 3.34, 2 masks): appears RUNE_LEAD_S before it arms, lit RUNE_LIT_S.
Positions are the step-quantised physics positions the export reports (a frame without a physics step repeats the last
one): the physics clock's phase is estimated from frames in which a moving hazard did not move (PhysClock), so the
predicted centre is the position after the last step before each query time (the centre error audit); the support
adds +-SLACK_STEPS steps of time slack and a contact skin.
"""
import math
from dataclasses import dataclass

import numpy as np

from ssbot.core.forum import ALIAS_TOL_U, DOME, FLOOR_Y, HAZARD_ALIASES, WALL_L, WALL_R, dome_y
from ssbot.core.worldstate import ORACLE, Entity, WorldState

STEP_S = 0.02
FRAME_S = 1.0 / 60.0
BELL = "Throwing Bell"
PIN = "Song Reed Pin Projectile"
BOMB = "rune bomb small"
RUNE = "rune slam"
BELL_R = 0.425
BELL_G = 60.0
BELL_FLOOR_Y = 3.428                         # the centre at rest on the floor (905 of 911 floor contacts)
BELL_BOUNCE_VY = 20.0                        # the FSM's Bounce (and the throw) velocity
BELL_BOUNCE_DY = 0.1                         # the first step after a floor contact rises 0.1 u (Box2D contact)
BELL_WALL_VX = 10.0                          # a side wall sends it back at 10 u/s
BELL_NAIL_SPEED = 30.0                       # a nail hit's speed (94 of 94: 30.000)
BELL_NAIL_OFF_S = 0.15                       # Nail Hit lasts 9 frames, collider off
BELL_STATES_ON = frozenset(("Air", "Bounce"))
PIN_STATES_ON = frozenset(("Fly",))
BOMB_R, RUNE_R = 2.166, 7.187
BOMB_LEAD_S = (0.335, 0.360)                 # appearance -> armed (game time)
BOMB_LIT_S = 18 * FRAME_S                    # armed 5-17 frames
BOMB_Y = 3.67
BOMB_DX = 4.2
BOMB_STEP_F = (9, 10)                        # a row's steps: the FSM's 0.15 s wait, 9 or 10 frames apart at 60 fps
BOMB_PAIRS = 9
BOMB_ROW_GAP_S = 0.3                         # a bomb more than this after the row's last one starts a new row
RUNE_LEAD_S = (1.06, 1.11)
RUNE_LIT_S = 20 * FRAME_S
RUNE_Y = 3.34
HAZARD_DV_U_S = 40.0                         # an undetermined hazard's tube growth (u/s): a bounce reverses ~34 u/s
DOME_NEAR_U = 1.1                            # a bell this close under the dome line may touch it (forum.md 8.1 vs Box2D:
#                                              703 logged air contacts away from the walls, gap p99 0.83, max 1.01 u)
SLACK_STEPS = 1                              # +- physics steps of time slack in the support
SKIN_U = 0.1                                 # contact skin (Box2D contact offset)
GONE_S = 0.5                                 # a hazard missing from the export this long has left


@dataclass(slots=True)
class HazardPath:
    """One hazard over the horizon. Moving: xs[0], ys[0] the observed position (until the first step, at path time
    t_first from the origin), xs[1 + k] after step k (at t_first + k STEP_S); on[i] its collider there; past the
    last step it is gone (or, from tube_from on, a tube from the last determined centre grown by HAZARD_DV_U_S: a dome
    contact). A bell's xs, ys, on are [B, n]: branch 0 the modelled flight, the others its side bounces after floor
    bounces (bell_branches). Static (one position): active over [t_lo, t_hi] (path times)."""
    type_key: str
    iid: int
    kind: str                       # "circle" | "box"
    r: float
    hx: float
    hy: float
    t_first: float
    xs: np.ndarray
    ys: np.ndarray
    on: np.ndarray
    damage: int = 1
    tube_from: float | None = None
    t_lo: float = -math.inf
    t_hi: float = math.inf
    slack: int = SLACK_STEPS
    predicted: bool = False         # not in the export yet (a later bomb of a row)

    @property
    def static(self) -> bool:
        return self.xs.shape[-1] == 1

    def at(self, tk, slack: bool = True) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Centres [B S, T] at tk (game s from the origin) for each branch (B: 1 but for a bell's side bounces;
        branch-major, the modelled flight first) and time-slack copy (S = 2 slack + 1; 1 without slack), collider on
        [B S, T], tube growth [B S, T]."""
        tk = np.asarray(tk, np.float64)
        offs = np.arange(-self.slack, self.slack + 1) * STEP_S if (slack and self.slack) else np.zeros(1)
        t = tk[None, :] + offs[:, None]
        if self.static:
            on = (t >= self.t_lo) & (t <= self.t_hi) & bool(np.ravel(self.on)[0])
            return np.full(t.shape, float(np.ravel(self.xs)[0])), np.full(t.shape, float(np.ravel(self.ys)[0])), on, \
                np.zeros(t.shape)
        xs, ys, on_b = (np.atleast_2d(self.xs), np.atleast_2d(self.ys), np.atleast_2d(self.on))
        B, n = xs.shape
        i = np.floor((t - self.t_first) / STEP_S + 1e-9).astype(np.int64) + 1
        ic = np.clip(i, 0, n - 1)
        S, T = t.shape
        cx, cy = xs[:, ic].reshape(B * S, T), ys[:, ic].reshape(B * S, T)
        on = (on_b[:, ic] & (i < n)[None]).reshape(B * S, T)
        grow = np.zeros((B * S, T))
        if self.tube_from is not None:
            past = np.tile(t >= self.tube_from, (B, 1))
            grow = np.where(past, HAZARD_DV_U_S * np.maximum(np.tile(t, (B, 1)) - self.tube_from, 0.0), 0.0)
            on = on | past
        return cx, cy, on, grow


class PhysClock:
    """The 50 Hz physics clock's phase in game time: step times are offset + k STEP_S. A frame (game time T_prev ->
    T, 0 < T - T_prev < STEP_S) in which a moving body did not move had no step in (T_prev, T]; one in which it moved
    had one. The feasible offsets mod STEP_S are kept on a 0.1 ms grid; mid() is their circular mean (None before a
    frame without a step narrowed them)."""

    N = 200

    def __init__(self) -> None:
        self.grid = (np.arange(self.N) + 0.5) * (STEP_S / self.N)
        self.ok = np.ones(self.N, bool)
        self.narrowed = False

    def observe(self, t_prev: float, t: float, moved: bool) -> None:
        if not t > t_prev + 1e-9 or t - t_prev >= STEP_S:
            return
        a, b = t_prev % STEP_S, t % STEP_S
        inside = ((self.grid > a) & (self.grid <= b)) if a < b else ((self.grid > a) | (self.grid <= b))
        new = self.ok & (inside if moved else ~inside)
        if new.any():
            self.ok = new
            self.narrowed = self.narrowed or not moved
        else:                       # inconsistent (a hitch, a time-scale change): start over from this frame
            self.ok = inside if moved else ~inside
            self.narrowed = not moved

    def mid(self) -> float | None:
        if not self.narrowed or not self.ok.any():
            return None
        ang = self.grid[self.ok] * (2 * math.pi / STEP_S)
        m = math.atan2(np.sin(ang).mean(), np.cos(ang).mean()) % (2 * math.pi)
        return m / (2 * math.pi) * STEP_S

    def next_step(self, t: float) -> float:
        """The first step time after t (without an estimate: half a step after t)."""
        o = self.mid()
        if o is None:
            return t + 0.5 * STEP_S
        return o + (math.floor((t - o) / STEP_S + 1e-9) + 1) * STEP_S


@dataclass(slots=True)
class _Haz:
    iid: int
    tk: str
    last_T: float
    pos: tuple[float, float]
    vel: tuple[float, float]
    state: str | None
    state_T: float
    on: bool
    appear_T: float
    rel_box: tuple | None = None    # its damage box relative to it (the last one seen)
    arm_T: float | None = None


def hazard_type(e: Entity) -> str:
    """The entity's type, or its alias by circle radius ("damager": bomb, rune, spear blast)."""
    tk = e.type_key.v
    alias = HAZARD_ALIASES.get(tk)
    if alias:
        b = next((b for b in e.dmg_boxes if b.poly), None)
        if b is not None:
            xs = [p[0] for p in b.poly]
            r = 0.5 * (max(xs) - min(xs))
            for r0, name in alias:
                if abs(r - r0) <= max(ALIAS_TOL_U, 0.05 * r0):
                    return name
    return tk


def _box(e: Entity) -> tuple | None:
    xs, ys = [], []
    for b in e.dmg_boxes:
        if b.active and b.poly:
            xs += [p[0] for p in b.poly]
            ys += [p[1] for p in b.poly]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


class HazardTracker:
    """The hazards of TYPES in the export (oracle view: FSM state, transform, exported velocity; vision view: the
    detection's position and tracked velocity, no FSM state) and the physics clock."""

    TYPES = frozenset((BELL, PIN, BOMB, RUNE))

    def __init__(self, view: str = ORACLE):
        self.view = view
        self.reset()

    def reset(self) -> None:
        self.clock = PhysClock()
        self.h: dict[int, _Haz] = {}
        self.alias: dict[int, str] = {}
        self.rows: list[dict] = []      # bomb rows: {x0, t0, last_T, seen: {(k, side)}, k_last, T_k, id}
        self._row_id = 0
        self.t = 0.0
        self.t_prev: float | None = None

    def kind_of(self, e: Entity) -> str:
        tk = e.type_key.v
        if tk in HAZARD_ALIASES:
            a = self.alias.get(e.id)
            if a is None or a == tk:
                a = self.alias[e.id] = hazard_type(e)
            return a
        return tk

    def update(self, ws: WorldState) -> None:
        T = ws.stamp.t_game_s
        moved_any, still_any = False, False
        for e in ws.entities:
            tk = self.kind_of(e)
            if tk not in self.TYPES or e.hidden:
                continue
            st = e.fsm[0][1] if e.fsm else None
            box = _box(e)
            p = e.pos_transform if (self.view == ORACLE and e.pos_transform is not None) else e.pos.v
            pos = (float(p[0]), float(p[1]))
            vel = (float(e.vel.v[0]), float(e.vel.v[1])) if e.vel.conf > 0 else (0.0, 0.0)
            h = self.h.get(e.id)
            if h is None or T - h.last_T > GONE_S:
                h = self.h[e.id] = _Haz(e.id, tk, T, pos, vel, st, T, box is not None, T)
                if tk == BOMB:
                    self._bomb_row(pos[0], T)
            else:
                if tk in (BELL, PIN) and abs(vel[0]) + abs(vel[1]) > 1.0 and h.last_T == self.t_prev:
                    mv = abs(pos[0] - h.pos[0]) + abs(pos[1] - h.pos[1]) > 1e-4
                    moved_any |= mv
                    still_any |= not mv
                if st != h.state:
                    h.state, h.state_T = st, T
                h.pos, h.vel, h.last_T, h.tk, h.on = pos, vel, T, tk, box is not None
            if box is not None:
                h.rel_box = (box[0] - pos[0], box[1] - pos[1], box[2] - pos[0], box[3] - pos[1])
                if h.arm_T is None:
                    h.arm_T = T
        if self.t_prev is not None and (moved_any or still_any):
            self.clock.observe(self.t_prev, T, not still_any)
        for iid in [i for i, h in self.h.items() if T - h.last_T > GONE_S]:
            del self.h[iid]
            self.alias.pop(iid, None)
        life = BOMB_STEP_F[1] * FRAME_S * (BOMB_PAIRS + 1) + BOMB_LEAD_S[1] + BOMB_LIT_S
        self.rows = [r for r in self.rows if T - r["t0"] < life]
        self.t_prev, self.t = T, T

    def _bomb_row(self, x: float, T: float) -> None:
        """A new bomb: bomb k of a row (x0 +- 4.2 k, the row's last bomb within BOMB_ROW_GAP_S), else a new row."""
        for r in self.rows:
            if T - r["last_T"] <= BOMB_ROW_GAP_S:
                k = round(abs(x - r["x0"]) / BOMB_DX)
                if abs(abs(x - r["x0"]) - k * BOMB_DX) < 0.3:
                    r["last_T"] = T
                    r["seen"].add((k, int(np.sign(x - r["x0"]))))
                    if k > r["k_last"]:
                        r["k_last"], r["T_k"] = k, T
                    return
        self._row_id += 1
        self.rows.append({"x0": x, "t0": T, "last_T": T, "seen": {(0, 0)}, "k_last": 0, "T_k": T,
                          "id": self._row_id})

    # ---- paths ----

    def paths(self, origin: float, horizon: float) -> list[HazardPath]:
        out = []
        n = int(math.ceil((horizon + 3 * STEP_S) / STEP_S)) + 1
        for h in self.h.values():
            if h.last_T < origin - 3 * STEP_S:
                continue
            p = None
            if h.tk == BELL:
                p = self._bell(h, origin, n)
            elif h.tk == PIN:
                p = self._pin(h, origin, n)
            elif h.tk == BOMB:
                p = self._static(h, origin, BOMB_LEAD_S, BOMB_LIT_S, BOMB_R, BOMB_Y, 1)
            elif h.tk == RUNE:
                p = self._static(h, origin, RUNE_LEAD_S, RUNE_LIT_S, RUNE_R, RUNE_Y, 2)
            if p is not None:
                out.append(p)
        out += self._row_bombs(origin)
        return out

    def _bell(self, h: _Haz, origin: float, n: int, redirect: tuple | None = None) -> HazardPath | None:
        if h.state is not None and h.state not in BELL_STATES_ON and h.state != "Nail Hit":
            return None          # broken or put away (oracle view)
        t0 = self.clock.next_step(origin) - origin
        floor = h.vel[1] == 0.0 and abs(h.pos[1] - BELL_FLOOR_Y) < 0.01
        wall = (1 if abs(h.pos[0] - (WALL_L + BELL_R)) < 0.01 else -1 if abs(h.pos[0] - (WALL_R - BELL_R)) < 0.01
                else 0) if h.vel[0] == 0.0 else 0
        nail = max(0.0, BELL_NAIL_OFF_S - (origin - h.state_T) - t0) if h.state == "Nail Hit" else 0.0
        # just off the floor (the floor bounce's step seen): its side bounce may still come on the next step
        bounced = h.vel[1] > 0.0 and h.pos[1] <= BELL_FLOOR_Y + BELL_BOUNCE_DY + 0.01 and not floor
        xs, ys, on, tube = bell_branches(h.pos[0], h.pos[1], h.vel[0], h.vel[1], n, floor_contact=floor,
                                         wall_contact=wall, nail_left=nail, redirect=redirect, just_bounced=bounced)
        if redirect is None and h.pos[1] + BELL_R >= dome_y(h.pos[0]) - DOME_NEAR_U:
            tube = 1             # touching the dome now: the FSM's Bounce is still to set its velocity
        on[:, 0] = (h.on or h.state is None) and h.state != "Nail Hit"
        return HazardPath(h.tk, h.iid, "circle", BELL_R, 0.0, 0.0, t0, xs, ys, on, 1,
                          tube_from=None if tube is None else t0 + (tube - 1) * STEP_S)

    def _pin(self, h: _Haz, origin: float, n: int) -> HazardPath | None:
        if h.state is not None and h.state not in PIN_STATES_ON or h.rel_box is None:
            return None
        t0 = self.clock.next_step(origin) - origin
        xs, ys, on = pin_steps(h.pos[0], h.pos[1], h.vel[0], h.vel[1], n, h.rel_box)
        on[0] = h.on or h.state is None
        rb = h.rel_box
        return HazardPath(h.tk, h.iid, "box", 0.0, 0.5 * (rb[2] - rb[0]), 0.5 * (rb[3] - rb[1]), t0,
                          xs + 0.5 * (rb[0] + rb[2]), ys + 0.5 * (rb[1] + rb[3]), on, 1)

    def _static(self, h: _Haz, origin: float, lead: tuple, lit: float, r: float, y: float,
                dmg: int) -> HazardPath | None:
        if h.arm_T is not None:
            lo, hi = h.arm_T - origin - STEP_S, h.arm_T - origin + lit
        else:
            lo, hi = h.appear_T + lead[0] - origin - STEP_S, h.appear_T + lead[1] + lit - origin
        if hi < -STEP_S:
            return None
        return HazardPath(h.tk, h.iid, "circle", r, 0.0, 0.0, 0.0, np.array([h.pos[0]]), np.array([y]),
                          np.ones(1, bool), dmg, t_lo=lo, t_hi=hi, slack=0)

    def _row_bombs(self, origin: float) -> list[HazardPath]:
        """The later bombs of every row whose first bomb was seen: pair k (past the latest step seen, k_last at T_k) at
        x0 +- 4.2 k appearing (k - k_last) steps of 9 to 10 frames after T_k."""
        out = []
        for r in self.rows:
            for k in range(r["k_last"] + 1, BOMB_PAIRS + 1):
                n = k - r["k_last"]
                a_lo = r["T_k"] + n * BOMB_STEP_F[0] * FRAME_S
                a_hi = r["T_k"] + n * BOMB_STEP_F[1] * FRAME_S
                for s in (-1, 1):
                    if (k, s) in r["seen"]:
                        continue
                    lo = a_lo + BOMB_LEAD_S[0] - 2 * STEP_S - origin
                    hi = a_hi + BOMB_LEAD_S[1] + BOMB_LIT_S + 2 * STEP_S - origin
                    x = r["x0"] + s * k * BOMB_DX
                    if hi < 0 or x < WALL_L - BOMB_R - 1.0 or x > WALL_R + BOMB_R + 1.0:
                        continue
                    out.append(HazardPath(BOMB, -(1 << 40) - r["id"] * 64 - k * 2 - (s > 0), "circle", BOMB_R, 0.0,
                                          0.0, 0.0,
                                          np.array([x]), np.array([BOMB_Y]), np.ones(1, bool), 1, t_lo=lo, t_hi=hi,
                                          slack=0, predicted=True))
        return out

    def redirect(self, iid: int, t_hit: float, d: int, origin: float, horizon: float) -> HazardPath | None:
        """A bell hit at t_hit (s from the origin) by the hero's attack moving d (+1 right, -1 left, 0 down, 2 up):
        30 u/s that way, collider off through the redirect, then free flight (the planner's hit effect)."""
        h = self.h.get(iid)
        if h is None or h.tk != BELL:
            return None
        n = int(math.ceil((horizon + 3 * STEP_S) / STEP_S)) + 1
        t0 = self.clock.next_step(origin) - origin
        k_hit = 1 + max(0, int(math.ceil((t_hit - t0) / STEP_S - 1e-9)))
        return self._bell(h, origin, n, redirect=(k_hit, d))


def bell_branches(x: float, y: float, vx: float, vy: float, n: int, floor_contact: bool = False,
                  wall_contact: int = 0, nail_left: float = 0.0, redirect: tuple[int, int] | None = None,
                  just_bounced: bool = False):
    """The bell's flight (bell_steps) and its side-bounce branches: xs, ys, on [B, n] (branch 0 the modelled flight),
    the earliest undetermined index over the branches (None: none).
    A floor bounce is followed by a side bounce on the next step in 384 of the 8,813 logged floor bounces of the R0
    caches (forum.md §14; 60 of them away from the side walls; 378 of all to +10 u/s): vx becomes +-10 u/s,
    the bell shifted BELL_BOUNCE_DY that way, vy kept (Box2D's ghost contact at a floor seam, a resting bell). Each
    floor bounce of the modelled flight (just_bounced: the one seen just before the origin) gets both directions as
    branches from its next step (one level: a branch's own later floor bounces do not branch again)."""
    floors: list[int] = []
    xs, ys, on, tube = bell_steps(x, y, vx, vy, n, floor_contact, wall_contact, nail_left, redirect, floors=floors)
    if just_bounced:
        floors.insert(0, 0)
    X, Y, O, tubes = [xs], [ys], [on], [tube]
    for k in floors:
        if k + 1 >= n:
            continue
        for side in (1, -1):
            a, b, c, t = bell_steps(x, y, vx, vy, n, floor_contact, wall_contact, nail_left, redirect,
                                    side_at=(k + 1, side))
            X.append(a)
            Y.append(b)
            O.append(c)
            tubes.append(t)
    tube = min((t for t in tubes if t is not None), default=None)
    return np.stack(X), np.stack(Y), np.stack(O), tube


def bell_steps(x: float, y: float, vx: float, vy: float, n: int, floor_contact: bool = False,
               wall_contact: int = 0, nail_left: float = 0.0, redirect: tuple[int, int] | None = None,
               floors: list | None = None, side_at: tuple[int, int] | None = None):
    """xs, ys [n]: index 0 the observed position, index i >= 1 after step i - 1; collider on; the index from which the
    path is not determined (a dome contact; None: determined throughout). floors: the indices of its floor-bounce
    steps are appended; side_at (i, side): a side bounce at step i (vx 10 u/s that side, x moved BELL_BOUNCE_DY, y and
    vy kept: bell_branches).
    The Control FSM answers a contact with Bounce on the step after it: off the floor vy 20 (vx kept), off a side
    wall (or the dome's slope) vx 10 away from it (vy kept), the bell moved BELL_BOUNCE_DY off the surface; Box2D
    stops the contact's normal velocity on the contact step. In Nail Hit (nail_left game s left: the Tink redirect,
    collider off) a contact waits: the bell slides along the floor (vy 0) or down the wall (vx 0) until Nail Hit ends,
    then bounces (R0 caches: 230325 i2 ep0 f7633-7642, 231917 i2 ep0 f35321-35330)."""
    xs, ys, on = np.empty(n), np.empty(n), np.ones(n, bool)
    xs[0], ys[0] = x, y
    on[0] = nail_left <= 0.0
    cf, cw = floor_contact, wall_contact
    tube = None
    nail = nail_left
    for i in range(1, n):
        if redirect is not None and i == redirect[0]:
            d = redirect[1]
            vx, vy = ((BELL_NAIL_SPEED * d, 0.0) if d in (-1, 1)
                      else (0.0, BELL_NAIL_SPEED if d == 2 else -BELL_NAIL_SPEED))
            nail, cf, cw = BELL_NAIL_OFF_S, False, 0
        if tube is not None:
            xs[i], ys[i] = xs[i - 1], ys[i - 1]
            continue
        in_nail = nail > 1e-9
        nail -= STEP_S
        if side_at is not None and i == side_at[0]:
            vx = BELL_WALL_VX * side_at[1]
            x += BELL_BOUNCE_DY * side_at[1]
            cw = 0
        elif not in_nail and cf:
            vy = BELL_BOUNCE_VY - BELL_G * STEP_S
            x += vx * STEP_S
            y = BELL_FLOOR_Y + BELL_BOUNCE_DY
            cf = False           # a corner (floor and wall at once): the wall's Bounce follows on the next step
            if floors is not None:
                floors.append(i)
        elif not in_nail and cw:
            vx = BELL_WALL_VX * cw
            vy -= BELL_G * STEP_S
            x += BELL_BOUNCE_DY * cw
            y += vy * STEP_S
            cw = 0
        else:
            vy -= BELL_G * STEP_S
            x += vx * STEP_S
            y += vy * STEP_S
        if y <= BELL_FLOOR_Y and vy < 0:
            y, vy, cf = BELL_FLOOR_Y, 0.0, True
        if x <= WALL_L + BELL_R and vx < 0:
            x, vx, cw = WALL_L + BELL_R, 0.0, 1
        elif x >= WALL_R - BELL_R and vx > 0:
            x, vx, cw = WALL_R - BELL_R, 0.0, -1
        if y + BELL_R >= dome_y(x) - DOME_NEAR_U:
            tube = i
        xs[i], ys[i] = x, y
        on[i] = not (nail > 1e-9)
    return xs, ys, on, tube


def pin_steps(x: float, y: float, vx: float, vy: float, n: int, rel_box: tuple):
    """A javelin's transform: index 0 observed, i >= 1 after step i - 1, straight on until its box meets a side wall
    or the floor (Stick: collider off from the step after)."""
    k = np.arange(n)
    xs = x + vx * STEP_S * k
    ys = y + vy * STEP_S * k
    on = np.ones(n, bool)
    hit = (xs + rel_box[0] <= WALL_L) | (xs + rel_box[2] >= WALL_R) | (ys + rel_box[1] <= FLOOR_Y)
    hit[0] = False
    if hit.any():
        i = int(np.argmax(hit))
        on[i + 1:] = False
        xs[i + 1:], ys[i + 1:] = xs[i], ys[i]
    return xs, ys, on


__all__ = ("HazardTracker", "HazardPath", "PhysClock", "bell_branches", "bell_steps", "pin_steps", "DOME", "STEP_S")
