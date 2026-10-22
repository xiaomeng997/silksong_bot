"""Map v2 L1: the Choir Clapper model (docs/plans/forum_map_v2.md section 1 L1 and 1b; stage M2; forum.md section 93).
Offline / planning code only: nothing in the live bot imports it (tests/test_map2_clapper.py checks it).

    from ssbot.map2 import clapper as cm
    K = cm.Know.load()                                  # knowledge/1.0.30000/enemies/forum/clapper_m2.json (fit)
    obs = [cm.Obs.from_entity(e) for e in clappers]     # its STATE entities (Control state, time in state, ...)
    mem = {o.iid: cm.Memory() for o in obs}             # per Clapper: its V4 counters / flags (Memory.observe)
    hero = cm.HeroPath.constant(x, y, T=120)            # her planned path (transform, physics box, hits per frame)
    P = cm.predict(obs, mem, hero, K, T=120)
    for b in P.branches:  b.p, b.choices, b.reveal, b.shapes(k)   # per frame k: damage / body / pogo shapes

THE MODEL. One Clapper is a small deterministic machine (the decompiled Control FSM, C:/ssbot/sandbox/reactive_scripts/
out/Song_Heavy_Sentry.txt) stepped frame by frame in game frames (1/60 s of game time; a hit-stop freeze is not a
frame), driven by her planned path (closed loop) and by the random choices the FSM makes, which are the BRANCHES:
  Idle      entry: Will Evade = RandomBool (a branch: revealed when the evade starts, or when she is in Slam Range at
            Can Evade and none starts); the buddy within 4 u (|dx|) -> Avoid Type (her and the buddy on the same side
            -> Evade Scuttle, else Walk); a hit on it (TOOK DAMAGE) -> Dmg Attack in the hit frame; Idle Time 0.65 s
            (no buddy) / 1.15 s (a buddy) -> Walk; Will Evade, in Slam Range and Can Evade (0.25 s) -> Evade
            Scuttle; FaceObjectV2 every frame.
  Walk      DistanceWalk 8 u/s keeping 7 +- 1.5 u from her (back while nearer, forward while farther); Attack Ready
            (0.25 s) and in Slam Range -> Close Range; WaitRandom 0.25 - 2 s (a branch, in 15-frame bins) -> Far
            Range; FaceObjectV2.
  Close     the buddy attacking -> Idle (CANCEL); the clip Walk B -> SLAM; Evaded -> V4 SLAM / CAST (0.5 each,
            eventMax 1, missedMax 2); else V4 SLAM / EVADE / CAST (1/3 each, eventMax 1, missedMax 3).
  Far       the buddy attacking -> Idle; V4 JUMP 0.5 / CAST 0.25 / JUMP CAST 0.25 (eventMax 2 / 1 / 1, missedMax
            1 / 2 / 2).
  Dmg Attack / After Scuttle: in Slam Range -> Close, else Far (instant).
  Evade     entry: a wall within 6 u behind (its facing before the turn) -> Escape Jump (V4 JUMP SLAM / JUMP CAST 1:1,
            eventMax 1, missedMax 1: strict alternation); else FaceObjectV2, 15 u/s backward for 0.35 s -> After
            Scuttle.
  moves     every start state faces her (FaceObjectV2, turns >= 0.5 s apart); Slam Antic 0.8 s -> Slam 0 (30 u/s
            forward) -> Slam 1 (30 u/s, Slam Collider 1) -> Slam 2 (stop, Slam Collider 2) -> Slam Recover -> Idle;
            Spell Antic -> Cast 1 -> Cast 2 (the bomb row) -> Idle; Jump Antic -> Jump Aim (target = her x - 5 x its
            facing, Jump X = clamp(target - x, +-12)) -> Jump (vx = Jump X, vy 38) -> Air (gravity 84 u/s^2; the roof
            near the walls: the body slides along it - the WALL PUSH) -> the landing: Slam 2 (Slam Collider 2) -> Slam
            Recover -> Idle; Cast Slam Antic 0.25 s -> Cast Slam Antic 2 -> the same jump and the big rune at the
            landing; a side slash pushes it 0.48 u (Recoil).
  Is Attacking (the buddy lock): from Slam / Spell / Jump / Cast Slam Antic to Slam 2 / Cast 2.
The state durations, the body box per state frame, the bomb rows and the rune timing are the fit's (Know: measured
distributions). TIMING VARIANTS: a branch is simulated at the nominal durations and each record carries the offset
range [a, b] of the real timing (a state lasting d_lo .. d_hi frames widens the range of everything after it; a
decision that waits for her - she enters Slam Range, her hit - narrows it again); a record's shapes are drawn at every
frame k + a .. k + b, so a branch's per-frame shapes are the union over its timing variants (damage never missed for
a timing inside the measured spread).

SHAPES (per frame, world coordinates, u): kinds DAMAGE (touching it hurts her), BODY (a slash that meets it lands),
POGO (a down slash that meets it bounces), TINK (bounces the nail; the Clapper has none: every collider is parry 4).
The root box is DAMAGE | BODY | POGO; Slam Collider 1 / 2 (polygons, move_data.HAMMER_POLY) DAMAGE only (a slash
passes through); the bombs and the big rune (circles) DAMAGE only, while lit.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
KNOW_PATH = REPO / "knowledge" / "1.0.30000" / "enemies" / "forum" / "clapper_m2.json"

DAMAGE, BODY, POGO, TINK = 1, 2, 4, 8
KIND_NAMES = {DAMAGE: "damage", BODY: "body", POGO: "pogo", TINK: "tink"}

DT = 0.02                      # the physics step
WALL_L, WALL_R = 14.01, 48.99  # the arena's wall faces (Battle Gate / Wall Collider)
FLOOR = 3.015                  # the floor's top
STAND_Y = 7.449                # its transform y standing (the root box bottom -4.434)
SLAM_RANGE = (8.046, -4.454, 3.369)   # the trigger: +-x half width, y0 / y1 relative to its transform
BUDDY_NEAR = 4.0               # Idle's Close To Buddy (|dx|)
ESCAPE_RAY = 6.0               # Evade Scuttle's ray behind (from its Centre) to a wall -> Escape Jump
TURN_PAUSE = 30                # FaceObjectV2 pauseBetweenTurns 0.5 s (frames; Idle / Walk's every-frame turns)
WALK_SPEED = 8.0
WALK_DIST, WALK_RANGE = 7.0, 1.5
EVADE_SPEED = 15.0
LUNGE = 30.0
JUMP_VY = 38.0
GRAV_STEP = 1.68               # gravity scale 1.4: 84 u/s^2, per 0.02 s step
JUMP_CLAMP = 12.0
TARGET_U = 5.0                 # Jump Aim's target: her x - 5 x its facing
RECOIL_V, RECOIL_N = 3.0, 8    # a side slash's push (Recoil: 3 u/s for 0.15 s; measured 0.42 / 0.48)
NAIL_DMG = 10                  # a nail hit's damage on its hp (Wanderer: 10; the oracle's 'dealt' 9)
BOMB_DX = 4.2
BOMB_DY = -3.8                 # a bomb's centre below its transform at Cast 2
HURTBOX = (0.2277, 1.1249, -0.3799)   # HeroBoxNormal half extents and its centre below her transform
EV_K = (15, 16, 17)            # Idle's Can Evade (0.25 s): the evade frame lo / nominal / hi (fit: 210 / 1200 / 1552)
CLOSE_K = (16, 16, 17)         # Walk's Attack Ready (0.25 s): the Close Range frame (fit: 702 / 1218)
IDLE_K = {True: (68, 70, 70), False: (39, 40, 40)}   # Idle Time with / without a buddy (fit: 79 / 925 / 2277)
WALK_FAR_MIN, WALK_FAR_MAX = 15, 120          # Walk's WaitRandom 0.25 - 2 s
NO_FAR = 10 ** 6
RANGE_LAG = 2                  # her Slam Range entry -> the FSM's decision: 0 (most) .. 2 frames later (fit)
RANGE_SKIN = 0.02              # the trigger reports her box this close to Slam Range already (the contact offset;
#                                decisions seen with a recorded gap of 0.004 / 0.006 u)

# Slam Collider 1 / 2 in its frame (x along the facing, y relative to its transform; move_data.HAMMER_POLY)
HAMMER = {
    "Slam Collider 1": np.array(((-1.91, 2.854), (1.739, 3.129), (4.067, 2.645), (6.089, 1.524), (6.236, 0.505),
                                 (5.297, 0.014), (1.966, -3.185))),
    "Slam Collider 2": np.array(((2.399, 0.754), (4.067, 2.645), (6.089, 1.523), (7.755, -4.194), (7.166, -4.987),
                                 (0.674, -3.62))),
}
# the roof near the walls (the active terrain "Roof Collider_Basic (2)" left / "(1)" right): the ceiling over x
ROOF_L = ((13.93, 14.19), (15.44, 14.99), (16.74, 16.14), (17.58, 16.24), (19.68, 17.32), (20.38, 17.75),
          (21.53, 17.87), (22.46, 19.0), (23.89, 20.36), (25.82, 21.77))
ROOF_R = ((40.6, 17.85), (42.42, 17.1), (43.41, 16.95), (44.31, 16.51), (46.43, 15.86), (46.91, 15.05),
          (49.67, 14.28))

ATTACK_SET = ("Slam Antic", "Spell Antic", "Jump Antic", "Cast Slam Antic")
ATTACK_CLR = ("Slam 2", "Cast 2")
ATTACKING = ("Slam Antic", "Slam 0", "Slam 1", "Slam Effects?", "Spell Antic", "Cast 1", "Jump Antic", "Jump Aim",
             "Jump", "Air", "Charged?", "Cast Slam Antic", "Cast Slam Antic 2", "Cast Jump")
INTRO = ("Init", "Rest", "Drop Antic", "Notify", "Drop In", "Enter Land", "Roar", "Roar End", "Z Set")
INSTANT = ("Close Range", "Far Range", "Dmg Attack", "After Scuttle", "Avoid Type", "Escape Jump", "Jump Aim",
           "Cast Jump", "Charged?", "Slam Effects?", "Z Set", "Notify", "Init", "Rest")
NO_BODY = ("Init", "Rest", "Drop Antic", "Notify", "Start Battle?", "Start Battle 2")
DEAD = ("Start Battle?", "Start Battle 2")
NEXT = {"Slam Antic": "Slam 0", "Slam 0": "Slam 1", "Slam 1": "Slam Effects?", "Slam 2": "Slam Recover",
        "Slam Recover": "Idle", "Spell Antic": "Cast 1", "Cast 1": "Cast 2", "Cast 2": "Idle",
        "Jump Antic": "Jump Aim", "Cast Slam Antic": "Cast Slam Antic 2", "Cast Slam Antic 2": "Cast Jump",
        "Evade Scuttle": "After Scuttle", "Drop Antic": "Drop In", "Enter Land": "Roar", "Roar": "Roar End",
        "Roar End": "Idle", "Z Set": "Idle"}
MOVE_OF = {"Slam Antic": "slam", "Slam 0": "slam", "Slam 1": "slam", "Slam 2": "slam", "Slam Recover": "slam",
           "Spell Antic": "cast", "Cast 1": "cast", "Cast 2": "cast", "Jump Antic": "jump", "Jump": "jump",
           "Air": "jump", "Cast Slam Antic": "jcast", "Cast Slam Antic 2": "jcast", "Evade Scuttle": "evade",
           "Idle": "idle", "Walk": "walk", "Drop In": "intro", "Enter Land": "intro", "Roar": "intro",
           "Roar End": "intro", "Drop Antic": "intro"}
CHOICE_KINDS = ("will_evade", "walk_far", "close", "close_ev", "far", "escape", "hit_idle")
MOVE_KINDS = ("close", "close_ev", "far", "escape")


# ---- the knowledge (the fit's tables) ----

class Know:
    """The fit's tables (ssbot.tools.m2_clapper fit): state durations (game frames), the body box runs per state,
    the bombs / rune timing."""

    def __init__(self, d: dict):
        self.d = d
        self.dur = {st: {int(k): int(v) for k, v in c.items()} for st, c in d["durations"].items()}
        self.body = {}
        for st, b in d["body"].items():
            runs = b["runs"]
            J = runs[-1][0] + 1
            tab = np.zeros((max(J, 1), 4))
            for i, r in enumerate(runs):
                j1 = runs[i + 1][0] if i + 1 < len(runs) else J
                tab[r[0]:j1] = r[1:5]
            self.body[st] = (tab, np.asarray(runs[-1][1:5], float))
        self._span = {}
        self._dur = {}

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Know":
        return cls(json.loads(Path(path or KNOW_PATH).read_text("utf-8")))

    def box(self, st: str, j: int) -> np.ndarray:
        """Its root box (x0, x1 along its facing, y0, y1) relative to its transform in state st, frame j."""
        t = self.body.get(st) or self.body["Idle"]
        tab, last = t
        return tab[j] if 0 <= j < len(tab) else last

    def box_span(self, st: str, j: int, w: int = 1) -> np.ndarray:
        """The union of box(st, j - w .. j + w) (an animation's change point falls a frame earlier or later)."""
        key = (st, j, w)
        r = self._span.get(key)
        if r is None:
            bs = np.array([self.box(st, max(jj, 0)) for jj in range(j - w, j + w + 1)])
            r = np.array([bs[:, 0].min(), bs[:, 1].max(), bs[:, 2].min(), bs[:, 3].max()])
            self._span[key] = r
        return r

    def durations(self, st: str, gt: int = -1, min_share: float = 0.005) -> tuple[int, int, int] | None:
        """(lo, nominal, hi) frames the state lasts, given it lasted more than gt frames already (the counts with
        share >= min_share; nominal = the median); None for a state without a duration table."""
        key = (st, gt)
        if key in self._dur:
            return self._dur[key]
        c = self.dur.get(st)
        r = None
        if c:
            tot = sum(c.values())
            mode = max(c, key=lambda k: c[k])
            # a pass-through (0 frames: the evade's escape at its entry) and the cut-short glitches are not timings
            floor = 0.6 * mode if mode >= 5 else 0
            ks = sorted(k for k, v in c.items() if v >= min_share * tot and k > gt and k >= floor)
            if not ks:
                ks = [gt + 1]
                r = (gt + 1, gt + 1, gt + 1)
            else:
                w = np.array([c[k] for k in ks], float)
                cum = np.cumsum(w) / w.sum()
                r = (ks[0], ks[int(np.searchsorted(cum, 0.5))], ks[-1])
        self._dur[key] = r
        return r

    def margin(self, mv: str, k: int) -> float:
        """The measured error as a margin (u) for a shape of move mv predicted k frames ahead: the smallest growth
        that covered >= 99 % of the actual damage area in the fit set's validation (by look-ahead; past the table's
        last k its last value; a 99 % not reached takes the grid's cap)."""
        mt = self.d.get("margins") or {}
        tab = mt.get("by_move", {}).get(mv)
        if not tab:
            return float(mt.get("default", 0.0))
        for kk, m in tab:
            if k <= kk:
                return float(m)
        return float(tab[-1][1])

    def p_ended(self, st: str, j: int, dur: tuple) -> float:
        """The share of the state's timing variants (its durations in dur's range) already over at frame j."""
        c = self.dur.get(st) or {}
        ks = [k for k in c if dur[0] <= k <= dur[2]]
        tot = sum(c[k] for k in ks)
        if not tot:
            return 0.5
        return float(min(max(sum(c[k] for k in ks if k <= j) / tot, 0.0), 1.0))

    def rune(self) -> tuple[float, float, float, float]:
        """(centre y, r, first lit frame lo, last lit frame hi) after the landing."""
        r = self.d["rune"]
        return float(r["cy"][2]), float(r["r"][2]), float(r["lit0"][0]), float(r["lit1"][4])

    def bomb_rings(self) -> list[tuple[int, float, float]]:
        """[(ring m, first lit frame lo, last lit frame hi)] after the Cast 2 entry (rings 0 .. 5 come on time,
        +-1; the pool's late rings 6 .. 9 anywhere in their observed window)."""
        B = self.d["bombs"]
        lead, lit = B["lead"], B["lit"]
        out = []
        for m in range(10):
            a = B["appear"].get(str(m))
            if a is None:
                continue
            if m <= 5:
                t0, t1 = a[2] - 1.0, a[2] + 1.0
            else:
                t0, t1 = a[2] - 3.0, max(a[4], a[2] + 3.0)
            out.append((m, t0 + lead[1], t1 + lead[3] + lit[3] - 1.0))
        return out


# ---- shapes ----

class Shape:
    """One collider-like shape at one frame: kinds (DAMAGE | BODY | POGO | TINK bits), its owner iid, a name, the
    move it belongs to (mv: the margin table's key), and the geometry: a box (x0, y0, x1, y1), a polygon ([m, 2],
    convex) or a circle (cx, cy, r)."""
    __slots__ = ("kinds", "iid", "name", "box", "poly", "circle", "mv")

    def __init__(self, kinds: int, iid: int, name: str, box=None, poly=None, circle=None, mv: str = ""):
        self.kinds, self.iid, self.name = kinds, iid, name
        self.box, self.poly, self.circle = box, poly, circle
        self.mv = mv

    def grown(self, m: float) -> "Shape":
        """The shape grown by m (u) on every side, conservatively (a polygon: its Minkowski sum with the square of
        half side m)."""
        if m <= 0:
            return self
        if self.box is not None:
            x0, y0, x1, y1 = self.box
            return Shape(self.kinds, self.iid, self.name, box=(x0 - m, y0 - m, x1 + m, y1 + m), mv=self.mv)
        if self.circle is not None:
            cx, cy, r = self.circle
            return Shape(self.kinds, self.iid, self.name, circle=(cx, cy, r + m), mv=self.mv)
        pts = np.concatenate([self.poly + (dx, dy) for dx in (-m, m) for dy in (-m, m)])
        return Shape(self.kinds, self.iid, self.name, poly=convex_hull(pts), mv=self.mv)

    def bbox(self) -> tuple:
        if self.box is not None:
            return self.box
        if self.poly is not None:
            return (float(self.poly[:, 0].min()), float(self.poly[:, 1].min()), float(self.poly[:, 0].max()),
                    float(self.poly[:, 1].max()))
        cx, cy, r = self.circle
        return (cx - r, cy - r, cx + r, cy + r)

    def polygon(self, n_circle: int = 32) -> np.ndarray:
        """[m, 2] vertices (a circle: the circumscribed n-gon, conservative)."""
        if self.poly is not None:
            return self.poly
        if self.box is not None:
            x0, y0, x1, y1 = self.box
            return np.array(((x0, y0), (x1, y0), (x1, y1), (x0, y1)), float)
        cx, cy, r = self.circle
        R = r / math.cos(math.pi / n_circle)
        a = np.linspace(0.0, 2.0 * math.pi, n_circle, endpoint=False) + math.pi / n_circle
        return np.stack([cx + R * np.cos(a), cy + R * np.sin(a)], axis=1)

    def hits_box(self, b, m: float = 0.0) -> bool:
        """Does it (grown by m on every side) meet the axis-aligned box b = (x0, y0, x1, y1)?"""
        x0, y0, x1, y1 = b[0] - m, b[1] - m, b[2] + m, b[3] + m
        if self.box is not None:
            a = self.box
            return a[0] < x1 and a[2] > x0 and a[1] < y1 and a[3] > y0
        if self.circle is not None:
            cx, cy, r = self.circle
            dx = max(b[0] - cx, 0.0, cx - b[2])
            dy = max(b[1] - cy, 0.0, cy - b[3])
            return dx * dx + dy * dy < (r + m) * (r + m)
        return poly_box_hit(self.poly, (x0, y0, x1, y1))

    def __repr__(self) -> str:
        k = "|".join(v for b, v in KIND_NAMES.items() if self.kinds & b)
        g = self.box if self.box is not None else ("circle", self.circle) if self.circle is not None else "poly"
        return f"Shape({self.name} {k} {g})"


def convex_hull(pts: np.ndarray) -> np.ndarray:
    """The convex hull ([m, 2], counter-clockwise) of points (the monotone chain)."""
    P = sorted(set(map(tuple, np.round(np.asarray(pts, float), 9))))
    if len(P) <= 2:
        return np.asarray(P, float)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for q in P:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], q) <= 0:
            lo.pop()
        lo.append(q)
    for q in reversed(P):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], q) <= 0:
            hi.pop()
        hi.append(q)
    return np.asarray(lo[:-1] + hi[:-1], float)


def poly_box_hit(p: np.ndarray, b) -> bool:
    """A convex polygon p ([m, 2]) meets the box b (x0, y0, x1, y1) (the separating axis test)."""
    x0, y0, x1, y1 = b
    if p[:, 0].max() <= x0 or p[:, 0].min() >= x1 or p[:, 1].max() <= y0 or p[:, 1].min() >= y1:
        return False
    q = np.array(((x0, y0), (x1, y0), (x1, y1), (x0, y1)), float)
    m = len(p)
    for i in range(m):
        e = p[(i + 1) % m] - p[i]
        n = np.array((-e[1], e[0]))
        a, c = p @ n, q @ n
        if a.max() <= c.min() or c.max() <= a.min():
            return False
    return True


def hurtbox(x: float, y: float) -> tuple:
    """Her HeroBox (normal) from her transform (x, y): (x0, y0, x1, y1)."""
    hw, hh, dy = HURTBOX
    return (x - hw, y + dy - hh, x + hw, y + dy + hh)


# ---- the observed state and her path ----

@dataclass
class Obs:
    """One Clapper as the STATE shows it now, plus what its history tells (the caller's tracker): will_evade (Idle:
    False once she was in Slam Range at Can Evade without an evade), turn_age (frames since its facing last
    changed), charged (a jump cast: Cast Slam Antic seen before this jump)."""
    iid: int
    st: str | None
    t: float                      # seconds in the state
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    face: int = -1                # +1 right
    hp: int = 230
    clip: str | None = None
    will_evade: bool | None = None
    turn_age: int = 10 ** 6
    charged: bool = False
    j: int | None = None          # frames in the state (game frames; else from t)
    prev: str | None = None       # the persistent state before this one (Slam 2 after Slam 1: Slam Collider 1's carry)
    cast2: tuple | None = None    # (k <= 0 of its last Cast 2 entry, its x, y then): the bomb row still to light
    idle_buddy: bool | None = None  # Idle: was the buddy alive at its entry (Idle Time is read there; None: now)
    rune: tuple | None = None     # (k <= 0 of its last charged landing, its x, its facing then): the rune to light

    @classmethod
    def from_entity(cls, e: dict, **kw) -> "Obs":
        st, t = None, 0.0
        for m in e.get("fsms") or ():
            if m.get("name") == "Control":
                st, t = m.get("state"), float(m.get("t") or 0.0)
        v = e.get("vel") or [0.0, 0.0]
        return cls(int(e["iid"]), st, t, float(e["pos"][0]), float(e["pos"][1]), float(v[0]), float(v[1]),
                   1 if e.get("flipX") else -1, int(e.get("hp") or 0), (e.get("anim") or {}).get("clip"), **kw)


@dataclass
class HeroPath:
    """Her planned path, per frame k = 0 .. T (k = 0 is now): her transform (x, y), her physics box (x0, y0, x1, y1:
    the Slam Range test), the frames her attacks land on each Clapper ({iid: {k: "side" / "down"}}), the physics
    steps per frame (0 / 1 / 2; the Clapper moves only on frames with a step; default 5 of 6 frames)."""
    x: np.ndarray
    y: np.ndarray
    box: np.ndarray
    hits: dict = field(default_factory=dict)
    steps: np.ndarray | None = None

    @property
    def T(self) -> int:
        return len(self.x) - 1

    def at(self, k: int) -> int:
        return min(max(k, 0), len(self.x) - 1)

    def step(self, k: int) -> int:
        if self.steps is None:
            return 0 if k % 6 == 5 else 1
        return int(self.steps[min(max(k, 0), len(self.steps) - 1)])

    @classmethod
    def constant(cls, x: float, y: float, box=None, T: int = 120, hits=None, steps=None) -> "HeroPath":
        if box is None:
            box = (x - 0.25, y - 1.5527, x + 0.25, y - 1.5527 + 2.0789)
        return cls(np.full(T + 1, float(x)), np.full(T + 1, float(y)), np.tile(np.asarray(box, float), (T + 1, 1)),
                   hits or {}, None if steps is None else np.asarray(steps))


# ---- the V4 random choice (SendRandomEventV4) and the memory ----

class V4:
    """One SendRandomEventV4 action instance: per event its run count (in a row) and its missed count. The choice:
    an event missed >= missedMax times is forced (the last such in the list); else a weighted draw over the events
    whose run count is below eventMax (the action's re-draw loop)."""
    __slots__ = ("events", "w", "emax", "mmax", "run", "miss")

    def __init__(self, events, weights, emax, mmax):
        self.events = tuple(events)
        self.w = tuple(float(x) for x in weights)
        self.emax, self.mmax = tuple(emax), tuple(mmax)
        self.run = [0] * len(self.events)
        self.miss = [0] * len(self.events)

    def copy(self) -> "V4":
        c = V4.__new__(V4)
        c.events, c.w, c.emax, c.mmax = self.events, self.w, self.emax, self.mmax
        c.run, c.miss = list(self.run), list(self.miss)
        return c

    def dist(self) -> list[tuple[float, str]]:
        n = len(self.events)
        forced = [i for i in range(n) if self.miss[i] >= self.mmax[i]]
        if forced:
            return [(1.0, self.events[forced[-1]])]
        ok = [i for i in range(n) if self.run[i] < self.emax[i]]
        if not ok:
            return [(1.0, self.events[0])]
        s = sum(self.w[i] for i in ok)
        return [(self.w[i] / s, self.events[i]) for i in ok]

    def take(self, ev: str) -> None:
        i = self.events.index(ev)
        r = self.run[i] + 1
        self.run = [0] * len(self.events)
        self.run[i] = r
        self.miss = [m + 1 for m in self.miss]
        self.miss[i] = 0


def _v4s() -> dict:
    return {"close": V4(("SLAM", "EVADE", "CAST"), (0.5, 0.5, 0.5), (1, 1, 1), (3, 3, 3)),
            "close_ev": V4(("SLAM", "CAST"), (0.5, 0.5), (1, 1), (2, 2)),
            "far": V4(("JUMP", "CAST", "JUMP CAST"), (0.5, 0.25, 0.25), (2, 1, 1), (1, 2, 2)),
            "escape": V4(("JUMP", "JUMP CAST"), (1.0, 1.0), (1, 1), (1, 1))}


EV_STATE = {"SLAM": "Slam Antic", "EVADE": "Evade Scuttle", "CAST": "Spell Antic", "JUMP": "Jump Antic",
            "JUMP CAST": "Cast Slam Antic"}
STATE_EV = {v: k for k, v in EV_STATE.items()}


class Memory:
    """What the FSM remembers between moves (all of it follows from the observed Control transitions since the
    fight's start, fed in order to observe()): the four V4 instances' counters, Evaded, Charged Slam."""

    def __init__(self):
        self.v4 = _v4s()
        self.evaded = False
        self.charged = False

    def copy(self) -> "Memory":
        m = Memory.__new__(Memory)
        m.v4 = {k: v.copy() for k, v in self.v4.items()}
        m.evaded, m.charged = self.evaded, self.charged
        return m

    def source(self, frm: str | None, to: str | None, clip_before: str | None = None) -> str | None:
        """The V4 instance that made the choice frm -> to (None: no V4 ran)."""
        if frm == "Close Range" and to in STATE_EV:
            if clip_before == "Walk B" and to == "Slam Antic":
                return None                                  # the Walk B shortcut
            return "close_ev" if self.evaded else "close"
        if frm == "Far Range" and to in STATE_EV:
            return "far"
        if frm == "Escape Jump" and to in STATE_EV:
            return "escape"
        return None

    def observe(self, frm: str | None, to: str | None, clip_before: str | None = None) -> str | None:
        """Feed one Control transition. Returns the V4 instance that made the choice (None: not a V4 choice)."""
        src = self.source(frm, to, clip_before)
        if src is not None:
            ev = STATE_EV[to]
            if ev in self.v4[src].events:
                self.v4[src].take(ev)
        if to == "Evade Scuttle":
            self.evaded = True
        elif to in ATTACK_SET:
            self.evaded = False
        if to == "Cast Slam Antic":
            self.charged = True
        elif to == "Jump Antic":
            self.charged = False
        elif to == "Charged?":
            pass
        elif frm == "Charged?":
            self.charged = False
        return src


# ---- the roof near the walls (the wall push of a jump) ----

def roof_y(px: float) -> float:
    """The ceiling's y over x near the walls (inf in the middle)."""
    for pts in (ROOF_L, ROOF_R):
        if pts[0][0] <= px <= pts[-1][0]:
            for (xa, ya), (xb, yb) in zip(pts[:-1], pts[1:]):
                if xa <= px <= xb:
                    return ya + (yb - ya) * (px - xa) / max(xb - xa, 1e-9)
    if px < ROOF_L[0][0]:
        return ROOF_L[0][1]
    if px > ROOF_R[-1][0]:
        return ROOF_R[-1][1]
    return 1e9


def roof_normal(px: float) -> tuple[float, float]:
    """The ceiling's unit normal at x pointing down into the arena."""
    e = 0.05
    s = (roof_y(px + e) - roof_y(px - e)) / (2 * e)
    n = math.hypot(s, 1.0)
    return s / n, -1.0 / n


# ---- the thrown hazards (world-fixed once spawned) ----

def rune_hazards(K: Know, k: int, x: float, face: int, a: int = 0, b: int = 0) -> list:
    """The big rune of a charged landing at frame k (x, its facing then): one circle, its centre 6.75 / 6.48 u ahead
    (the spawn point's pivot), lit from the landing + 65 (fit p1 64.9) to + 72, the timing range [a, b] added."""
    cy, r, l0, l1 = K.rune()
    dx = 6.75 if face > 0 else 6.48
    return [("rune", x + face * dx, cy, r, k + a + int(math.floor(l0)), k + b + int(math.ceil(l1)))]


def bomb_hazards(K: Know, k: int, x0: float, y: float, a: int = 0, b: int = 0) -> list:
    """The small-rune row of a Cast 2 entry at frame k from its x0 / y then: ring m at x0 +- 4.2 m (only the ones
    that reach the arena), each lit in its window (rings 0 .. 5 on time, the pool's late rings 6 .. 9 anywhere in their
    observed window)."""
    out = []
    y0 = y + BOMB_DY
    for m, t0, t1 in K.bomb_rings():
        for sx in ((0,) if m == 0 else (-1, 1)):
            x = x0 + sx * BOMB_DX * m
            if x < WALL_L - 2.2 or x > WALL_R + 2.2:
                continue
            out.append(("bomb", x, y0, 2.166, k + a + int(math.floor(t0)), k + b + int(math.ceil(t1))))
    return out


# ---- one Clapper's machine ----

class NeedChoice(Exception):
    """A random choice the branch has not fixed yet: options [(probability, outcome)]."""

    def __init__(self, key, options):
        super().__init__(key)
        self.key, self.options = key, options


class Sim:
    """One Clapper's machine (module docstring) in game frames. step(k) moves it from frame k - 1 to k under her path
    and the buddy's state; a random choice not fixed in self.choices raises NeedChoice (the caller forks the branch
    and steps again from a copy taken before the step)."""
    __slots__ = ("K", "iid", "st", "j", "x", "y", "vx", "vy", "face", "hp", "clip", "mem", "buddy", "buddy_x",
                 "a", "b", "dur", "entry_k", "ea", "eb", "rs", "choices", "log", "n_ch", "attacking", "will_evade",
                 "walk_far", "walk_dir", "jump_x", "landed", "dead", "last_turn", "hazards", "k", "ev_revealed",
                 "prev_st", "recoil", "rec_dir", "idle_bud", "inr_prev")

    def __init__(self, o: Obs, mem: Memory, K: Know, buddy: bool):
        self.K = K
        self.iid = o.iid
        self.st = o.st or "Idle"
        self.j = int(o.j) if o.j is not None else int(round(o.t * 60.0))
        self.x, self.y, self.vx, self.vy = o.x, o.y, o.vx, o.vy
        self.face = o.face
        self.hp = o.hp
        self.clip = o.clip
        self.mem = mem.copy()
        self.buddy = buddy
        self.buddy_x = None
        self.a, self.b = 0, 0
        self.entry_k, self.ea, self.eb = -self.j, 0, 0
        self.rs = None                       # the first frame of her current run inside Slam Range
        self.inr_prev = False                # her box was inside Slam Range on the previous frame
        self.choices = {}
        self.log = []                         # [kind, outcome, k decided, reveal lo, reveal hi]
        self.n_ch = 0
        self.attacking = self.st in ATTACKING
        self.will_evade = o.will_evade if self.st == "Idle" else None
        self.walk_far = None
        self.walk_dir = 1 if o.clip == "Walk F" else -1 if o.clip == "Walk B" else 0
        self.jump_x = o.vx
        self.landed = False
        self.dead = self.hp <= 0 or self.st in DEAD
        self.last_turn = -int(o.turn_age)
        self.hazards = []
        self.k = 0
        self.ev_revealed = self.will_evade is not None
        if self.st == "Idle" and self.will_evade is not None:
            self.log.append(["will_evade", self.will_evade, 0, 0, 0])
        self.prev_st = o.prev
        self.recoil, self.rec_dir = 0, 0
        self.idle_bud = buddy if o.idle_buddy is None else bool(o.idle_buddy)
        self.dur = self._dur(self.st, gt=self.j)
        if o.cast2 is not None:
            k0, x0, y0 = o.cast2
            self._bombs(int(k0), x0, y0)
        if o.rune is not None:
            k0, x0, f0 = o.rune
            self._rune(int(k0), x0, f0)
        if self.st in ("Cast Slam Antic", "Cast Slam Antic 2", "Cast Jump"):
            self.mem.charged = True
        elif o.charged:
            self.mem.charged = True

    def clone(self) -> "Sim":
        s = Sim.__new__(Sim)
        for k in Sim.__slots__:
            setattr(s, k, getattr(self, k))
        s.mem = self.mem.copy()
        s.choices = dict(self.choices)
        s.log = [list(x) for x in self.log]
        s.hazards = list(self.hazards)
        return s

    # -- helpers --
    def _dur(self, st: str, gt: int = -1):
        if st in ("Idle", "Walk", "Air", "Jump", "Drop In") or st in DEAD:
            return None
        return self.K.durations(st, gt=gt)

    def _choose(self, kind: str, options):
        key = (kind, self.n_ch)
        self.n_ch += 1
        if key in self.choices:
            return self.choices[key]
        if len(options) == 1:
            return options[0][1]
        raise NeedChoice(key, options)

    def _decided(self, kind: str, outcome, k: int, rlo: int | None = None, rhi: int | None = None) -> None:
        self.log.append([kind, outcome, k, k + self.a if rlo is None else rlo, k + self.b if rhi is None else rhi])

    def in_range(self, hero: HeroPath, k: int) -> bool:
        hx, ry0, ry1 = SLAM_RANGE
        hx += RANGE_SKIN
        b = hero.box[hero.at(k)]
        return b[0] < self.x + hx and b[2] > self.x - hx and b[1] < self.y + ry1 + RANGE_SKIN and             b[3] > self.y + ry0 - RANGE_SKIN

    def _face(self, hero: HeroPath, k: int, pause: bool = True) -> None:
        """FaceObjectV2 toward her transform. pause: the 0.5 s between turns (Idle / Walk's every-frame instance);
        a move's start state turns at once (its own instance: 13 / 13 starts that needed a turn turned, 5 of them
        < 0.5 s after the last one)."""
        hx = float(hero.x[hero.at(k)])
        want = 1 if hx > self.x else -1 if hx < self.x else self.face
        if want != self.face and (not pause or k - self.last_turn >= TURN_PAUSE):
            self.face = want
            self.last_turn = k

    def _clamp_x(self, st: str | None = None) -> None:
        bx = self.K.box(st or self.st, self.j)
        a, b = self.x + self.face * bx[0], self.x + self.face * bx[1]
        lo, hi = min(a, b), max(a, b)
        if lo < WALL_L:
            self.x += WALL_L - lo
        elif hi > WALL_R:
            self.x -= hi - WALL_R

    def _grounded_y(self, steps: int) -> None:
        """Grounded: the transform sits so that the root box bottom rests on the floor (a shorter box falls under
        gravity, a taller one is pushed up at once)."""
        yg = FLOOR - float(self.K.box(self.st, self.j)[2])
        if self.y < yg - 1e-6:
            self.y, self.vy = yg, 0.0
        elif self.y > yg + 1e-6:
            for _ in range(steps):
                self.vy -= GRAV_STEP
                self.y = max(self.y + self.vy * DT, yg)
            if self.y <= yg + 1e-6:
                self.y, self.vy = yg, 0.0
        else:
            self.vy = 0.0

    def _timer_offsets(self, k: int, lo: int, nom: int, hi: int, her_rs: int | None) -> None:
        """A decision at frame k (nominal) that fires on the state's timer (lo / nom / hi frames after its entry)
        once she is in range (from her_rs; None: no range condition): the offset range of what follows."""
        e_lo, e_hi = self.entry_k + self.ea + lo, self.entry_k + self.eb + hi
        if her_rs is not None:
            # her box enters Slam Range: the trigger reports it in a physics step, the FSM reads it 0 .. 2 frames on
            e_lo, e_hi = max(e_lo, her_rs), max(e_hi, her_rs + RANGE_LAG)
        self.a, self.b = min(e_lo - k, 0), max(e_hi - k, 0)

    def _close_eta(self, hero: HeroPath, k: int) -> int:
        """The walk frame of her first Slam Range entry at walk frame >= Attack Ready (its x held), else 121."""
        hx, ry0, ry1 = SLAM_RANGE
        hx += RANGE_SKIN
        for kk in range(k, k + WALK_FAR_MAX - self.j + 2):
            jj = self.j + (kk - k)
            if jj < CLOSE_K[1]:
                continue
            b = hero.box[hero.at(kk)]
            if b[0] < self.x + hx and b[2] > self.x - hx and b[1] < self.y + ry1 and b[3] > self.y + ry0:
                return jj
        return WALK_FAR_MAX + 1

    # -- the state machine --
    def _enter(self, st: str, hero: HeroPath, k: int, buddy_att: bool) -> None:
        """Enter st at frame k (its OnEnter actions), following the instant states."""
        prev = self.st
        self.prev_st = self.st
        for _ in range(16):
            self.st, self.j = st, 0
            if st in ATTACK_SET:
                self.attacking = True
                self.mem.evaded = False
            if st in ATTACK_CLR:
                self.attacking = False
            if st == "Idle":
                self.vx = 0.0
                self.will_evade = None
                self.ev_revealed = False
                self.idle_bud = self.buddy_x is not None          # Idle Time: the buddy at the entry
                self._face(hero, k)
                if self.buddy_x is not None and abs(self.buddy_x - self.x) < BUDDY_NEAR:
                    hr = float(hero.x[hero.at(k)]) > self.x
                    br = self.buddy_x > self.x
                    st = "Evade Scuttle" if hr == br else "Walk"
                    self._decided("avoid", st, k)
                    prev = "Avoid Type"
                    continue
            elif st == "Walk":
                self.walk_far = None
                # DistanceWalk at its entry: back while she is nearer than 7 u (|dx|), forward otherwise
                hx = float(hero.x[hero.at(k)])
                self.walk_dir = -1 if abs(hx - self.x) < WALK_DIST else 1
                self.vx = WALK_SPEED * self.walk_dir * (1 if hx > self.x else -1)
                self.clip = "Walk F" if self.walk_dir > 0 else "Walk B"
            elif st == "Close Range":
                if buddy_att:
                    self._decided("cancel", "Idle", k)
                    st, prev = "Idle", "Close Range"
                    continue
                if self.clip == "Walk B" and prev == "Walk":
                    self._decided("walkb", "SLAM", k)
                    st, prev = "Slam Antic", "Close Range"
                    continue
                src = "close_ev" if self.mem.evaded else "close"
                ev = self._choose(src, self.mem.v4[src].dist())
                self.mem.v4[src].take(ev)
                self._decided(src, ev, k)
                st, prev = EV_STATE[ev], "Close Range"
                continue
            elif st == "Far Range":
                if buddy_att:
                    self._decided("cancel", "Idle", k)
                    st, prev = "Idle", "Far Range"
                    continue
                ev = self._choose("far", self.mem.v4["far"].dist())
                self.mem.v4["far"].take(ev)
                self._decided("far", ev, k)
                st, prev = EV_STATE[ev], "Far Range"
                continue
            elif st == "Dmg Attack":
                # the trigger reports her leaving one frame late (fit: 91 Close Range decisions with her box out
                # of Slam Range since the frame before, none with Far)
                st, prev = ("Close Range" if self.in_range(hero, k) or self.inr_prev else "Far Range"), st
                continue
            elif st == "After Scuttle":
                st, prev = ("Close Range" if self.in_range(hero, k) else "Far Range"), st
                continue
            elif st == "Evade Scuttle":
                self.mem.evaded = True
                back = (self.x - WALL_L) if self.face > 0 else (WALL_R - self.x)
                if back < ESCAPE_RAY:
                    ev = self._choose("escape", self.mem.v4["escape"].dist())
                    self.mem.v4["escape"].take(ev)
                    self._decided("escape", ev, k)
                    st, prev = EV_STATE[ev], "Escape Jump"
                    continue
                self._face(hero, k, pause=False)
                self.vx = -EVADE_SPEED * self.face
            elif st in ATTACK_SET:
                self._face(hero, k, pause=False)
                self.vx = 0.0
                if st == "Cast Slam Antic":
                    self.mem.charged = True
                elif st == "Jump Antic":
                    self.mem.charged = False
            elif st in ("Slam 0", "Slam 1"):
                self.vx = LUNGE * self.face
            elif st == "Cast Jump":
                self._face(hero, k, pause=False)
                st, prev = "Jump Aim", st
                continue
            elif st == "Jump Aim":
                self._face(hero, k, pause=False)
                tgt = float(hero.x[hero.at(k)]) - TARGET_U * self.face
                self.jump_x = float(np.clip(tgt - self.x, -JUMP_CLAMP, JUMP_CLAMP))
                st, prev = "Jump", st
                continue
            elif st == "Jump":
                self.vx, self.vy = self.jump_x, JUMP_VY
            elif st == "Charged?":
                if self.mem.charged:
                    self.mem.charged = False
                    self._rune(k)
                st, prev = "Slam Effects?", st
                continue
            elif st == "Slam Effects?":
                st, prev = "Slam 2", st
                continue
            elif st == "Slam 2":
                self.vx = 0.0
            elif st == "Cast 2":
                self._bombs(k)
            elif st in DEAD:
                self.dead = True
            break
        self.entry_k, self.ea, self.eb = k, self.a, self.b
        self.dur = self._dur(self.st)

    def _rune(self, k: int, x: float | None = None, face: int | None = None) -> None:
        """The big rune of a charged landing at frame k."""
        self.hazards.extend(rune_hazards(self.K, k, self.x if x is None else x, self.face if face is None else face,
                                         self.a, self.b))

    def _bombs(self, k: int, x: float | None = None, y: float | None = None) -> None:
        """The small-rune row of a Cast 2 entry at frame k (from its x / y then)."""
        self.hazards.extend(bomb_hazards(self.K, k, self.x if x is None else x, self.y if y is None else y,
                                         self.a, self.b))

    def step(self, k: int, hero: HeroPath, buddy_att: bool, buddy_x: float | None) -> None:
        """Frame k: the physics steps (its motion), then the FSM's update (the state's exit, the instant chain)."""
        self.k = k
        self.buddy_x = buddy_x
        if self.dead:
            return
        steps = hero.step(k)
        st = self.st
        # ---- physics ----
        if st in ("Jump", "Air"):
            bx = self.K.box("Air", 0)
            for _ in range(steps):
                self.vy -= GRAV_STEP
                nx, ny = self.x + self.vx * DT, self.y + self.vy * DT
                lo = nx + min(self.face * bx[0], self.face * bx[1])
                hi = nx + max(self.face * bx[0], self.face * bx[1])
                cx = lo if nx < 0.5 * (WALL_L + WALL_R) else hi
                ry = roof_y(cx)
                if ny + bx[3] > ry and self.vy > 0:
                    n0, n1 = roof_normal(cx)
                    vn = self.vx * n0 + self.vy * n1
                    if vn < 0:
                        self.vx, self.vy = self.vx - vn * n0, self.vy - vn * n1
                    ny = ry - bx[3]
                self.x, self.y = nx, ny
                self._clamp_x("Air")
                if self.y + bx[2] <= FLOOR and self.vy < 0:
                    self.y = FLOOR - bx[2]
                    self.landed = True
                    break
        elif st == "Drop In":
            for _ in range(steps):
                self.y = max(self.y - 48.0 * DT, STAND_Y)
        else:
            if self.vx and steps:
                self.x += self.vx * DT * steps
                self._clamp_x()
            if st not in INTRO:
                self._grounded_y(steps)
        if self.recoil > 0 and steps:
            # Recoil (0.15 s from the hit): 0.06 u per physics step away from her on top of its own motion, in the
            # air too (the flight's velocity unchanged; fit: +0.06 per step over the flight's, 0.42 - 0.48 in all)
            n = min(steps, self.recoil)
            self.recoil -= n
            self.x += self.rec_dir * RECOIL_V * DT * n
            self._clamp_x("Air" if st in ("Jump", "Air") else None)
        # her run inside Slam Range (her physics box against its trigger after this frame's motion)
        self.inr_prev = self.rs is not None
        if self.in_range(hero, k):
            if self.rs is None:
                self.rs = k
        else:
            self.rs = None
        # ---- the update ----
        self.j += 1
        hit = hero.hits.get(self.iid, {}).get(k)
        if hit is not None:
            kind, dmg = (hit, NAIL_DMG) if isinstance(hit, str) else (hit[0], hit[1])
            if kind == "side":
                self.recoil, self.rec_dir = RECOIL_N, (1 if self.x > float(hero.x[hero.at(k)]) else -1)
            self.hp -= int(dmg)
            if self.hp <= 0:
                self.dead = True
                self.st, self.j = "Start Battle?", 0
                self.attacking = False
                return
        if hit is not None and st == "Idle":
            self.a, self.b = 0, 0
            self._enter("Dmg Attack", hero, k, buddy_att)
            return
        if hit is not None and NEXT.get(st) == "Idle" and self.dur is not None and self.j + self.a >= self.dur[0]:
            # the state may have ended already (its early timing variants are in Idle): Idle's TOOK DAMAGE or not
            p_idle = self.K.p_ended(st, self.j + self.a, self.dur)
            if self._choose("hit_idle", ((p_idle, True), (1.0 - p_idle, False))):
                self.log.append(["hit_idle", True, k, k, k])
                self.a, self.b = 0, 0
                self._enter("Idle", hero, k, buddy_att)
                self._enter("Dmg Attack", hero, k, buddy_att)
                return
        if st == "Idle":
            self._face(hero, k)
            lo, nom, hi = IDLE_K[self.idle_bud]
            if self.j >= nom:
                self._timer_offsets(k, lo, nom, hi, None)
                self._enter("Walk", hero, k, buddy_att)
                return
            if self.j >= EV_K[1] and self.rs is not None and not self.ev_revealed:
                # Will Evade shows now (the FSM draws it at the entry, nothing before this frame depends on it)
                self.ev_revealed = True
                if self.will_evade is None:
                    self.will_evade = self._choose("will_evade", ((0.5, True), (0.5, False)))
                if self.will_evade:
                    self._timer_offsets(k, EV_K[0], EV_K[1], EV_K[2], self.rs)
                    self.log.append(["will_evade", True, k, k + self.a, k + self.b])
                    self._enter("Evade Scuttle", hero, k, buddy_att)
                    return
                self.log.append(["will_evade", False, k, k, k])
            return
        if st == "Walk":
            self._face(hero, k)
            hx = float(hero.x[hero.at(k)])
            d = abs(hx - self.x)                     # DistanceWalk: |dx|, hysteresis 5.5 .. 8.5 (fit: 7,289 / 37)
            if d < WALK_DIST - WALK_RANGE:
                self.walk_dir = -1
            elif d > WALK_DIST + WALK_RANGE:
                self.walk_dir = 1
            elif self.walk_dir == 0:
                self.walk_dir = 1 if d > WALK_DIST else -1
            toward = 1 if hx > self.x else -1
            self.vx = WALK_SPEED * self.walk_dir * toward
            self.clip = "Walk F" if self.walk_dir > 0 else "Walk B"
            if self.j >= CLOSE_K[1] and self.rs is not None:
                self._timer_offsets(k, CLOSE_K[0], CLOSE_K[1], CLOSE_K[2], self.rs)
                self._enter("Close Range", hero, k, buddy_att)
                return
            if self.walk_far is not None and self.walk_far >= NO_FAR and self.j > self.walk_far - NO_FAR + 8:
                self.walk_far = None                 # the Close it waited for did not come: draw again
            if self.walk_far is None and self.j >= WALK_FAR_MIN - 1:
                # the far timer can fire from here: draw its bin only up to her expected Close (later: no Far)
                jc = self._close_eta(hero, k)
                opts = walk_bins(self.j, jc)
                v = self._choose("walk_far", opts)
                self.walk_far = v if v is not None else NO_FAR + jc
                self.log.append(["walk_far", v, k, None, None])
            if self.walk_far is not None and self.walk_far < NO_FAR and self.j >= self.walk_far:
                w = 8
                self._timer_offsets(k, self.walk_far - w, self.walk_far, self.walk_far + w, None)
                self._enter("Far Range", hero, k, buddy_att)
            return
        if st == "Air":
            if self.landed:
                self.landed = False
                self._enter("Charged?", hero, k, buddy_att)
            return
        if st == "Jump":
            self.st, self.j = "Air", 0
            return
        if st == "Drop In":
            if self.y <= STAND_Y + 1e-6:
                self._enter("Enter Land", hero, k, buddy_att)
            return
        if self.dur is not None and self.j >= self.dur[1]:
            lo, nom, hi = self.dur
            self.a += lo - nom
            self.b += hi - nom
            nxt = NEXT.get(st)
            if nxt is not None:
                self._enter(nxt, hero, k, buddy_att)

    def may_choose(self, k: int, hero: HeroPath) -> bool:
        """Can step(k) need a random choice (the caller then keeps a copy to step again)? Idle / Walk, a hit this
        frame, or a timed state whose nominal end comes now (its exit's instant chain may hold a choice)."""
        if self.dead:
            return False
        if self.st in ("Idle", "Walk") or hero.hits.get(self.iid, {}).get(k) is not None:
            return True
        return self.dur is not None and self.j + 1 >= self.dur[1]

    def rec(self) -> tuple:
        """The record of this frame: (k, a, b, state, j, x, y, face, hammer)."""
        ham = 0
        if self.st == "Slam 1":
            ham = 1
        elif self.st == "Slam 2":
            ham = 2 | (1 if self.j == 0 and self.prev_st == "Slam 1" else 0)
        elif self.st == "Slam Recover" and self.j == 0:
            ham = 2
        return (self.k, self.a, self.b, self.st, self.j, self.x, self.y, self.face, ham)


def walk_bins(j0: int, j_close: int = 10 ** 6, width: int = 15) -> list:
    """Walk's WaitRandom 0.25 - 2 s (frames 15 .. 120, uniform) given j0 frames walked: bins of `width` frames up to
    her expected Close at walk frame j_close, each (its probability, its middle frame), and (the rest, None): the
    timer would fire after the Close."""
    lo, hi = max(WALK_FAR_MIN, j0 + 1), WALK_FAR_MAX
    if lo >= hi:
        return [(1.0, lo)]
    top = min(hi, j_close)
    out = []
    a = lo
    while a < top:
        b = min(a + width, top)
        out.append(((b - a) / (hi - lo), int((a + b) // 2)))
        a = b
    rest = 1.0 - sum(p for p, _ in out)
    if rest > 1e-9:
        out.append((rest, None))
    return out


# ---- predict ----

@dataclass
class Branch:
    """One outcome branch: its probability, the choices that make it (per Clapper iid: [kind, outcome, frame decided,
    reveal lo, reveal hi]), its reveal frame (the earliest frame at which one of its choices shows; None: no choice)
    and the records per Clapper; shapes(k) gives the frame's shapes (the union over its timing variants)."""
    p: float
    choices: dict
    reveal: int | None
    recs: dict
    hazards: list
    K: Know = None
    T: int = 120
    n_merged: int = 1
    _frames: list | None = None
    logs: dict | None = None

    def shapes(self, k: int) -> list[Shape]:
        if self._frames is None:
            self._frames = build_frames(self.recs, self.hazards, self.K, self.T)
        return self._frames[k] if 0 <= k < len(self._frames) else []

    def damage(self, k: int, margins: bool = False) -> list[Shape]:
        """The frame's damage shapes; margins: each grown by its move's measured error at this look-ahead
        (Know.margin)."""
        out = [s for s in self.shapes(k) if s.kinds & DAMAGE]
        if margins:
            out = [s.grown(self.K.margin(s.mv, k)) for s in out]
        return out

    def targets(self, k: int, kind: int = BODY) -> list[Shape]:
        return [s for s in self.shapes(k) if s.kinds & kind]

    def label(self) -> str:
        out = []
        for iid, ch in self.choices.items():
            out.append(f"{iid % 1000}:" + ",".join(f"{c[0]}={c[1]}" for c in ch))
        return " ".join(out) or "-"


@dataclass
class Prediction:
    branches: list
    T: int
    n_particles: int
    ms: float

    def damage(self, k: int, margins: bool = False) -> list[Shape]:
        """The union over every branch of the frame's damage shapes (the conservative danger; margins: grown by
        the measured errors)."""
        out = []
        for b in self.branches:
            out += b.damage(k, margins)
        return out

    def danger_boxes(self, k: int, hero_ref: str = "box", margins: bool = True) -> np.ndarray:
        """[n, 4] boxes (x0, y0, x1, y1) of her reference point's configuration space at frame k (every branch):
        each damage shape's bounding box grown by her hurtbox, for her physics box centre (M1's danger input,
        hero_ref "box") or her transform ("transform"). Conservative (a polygon / circle by its bounding box)."""
        hw, hh, dy = HURTBOX
        off = dy + 0.5135 if hero_ref == "box" else dy      # her box centre = transform - 0.5135
        out = []
        for s in self.damage(k, margins):
            x0, y0, x1, y1 = s.bbox()
            out.append((x0 - hw, y0 - hh - off, x1 + hw, y1 + hh - off))
        return np.asarray(out, float).reshape(-1, 4)


def rec_shapes(r: tuple, iid: int, K: Know) -> list[Shape]:
    k, a, b, st, j, x, y, face, ham = r
    if st in NO_BODY or st is None:
        return []
    bx = K.box_span(st, j)
    xa, xb = x + face * bx[0], x + face * bx[1]
    mv = MOVE_OF.get(st, "idle")
    out = [Shape(DAMAGE | BODY | POGO, iid, "body", box=(min(xa, xb), y + bx[2], max(xa, xb), y + bx[3]), mv=mv)]
    if ham & 1:
        p = HAMMER["Slam Collider 1"]
        out.append(Shape(DAMAGE, iid, "Slam Collider 1", poly=np.stack([x + face * p[:, 0], y + p[:, 1]], axis=1),
                         mv=mv))
    if ham & 2:
        p = HAMMER["Slam Collider 2"]
        out.append(Shape(DAMAGE, iid, "Slam Collider 2", poly=np.stack([x + face * p[:, 0], y + p[:, 1]], axis=1),
                         mv=mv))
    return out


def build_frames(recs: dict, hazards: list, K: Know, T: int) -> list[list[Shape]]:
    """Per frame 0 .. T the shapes of the records (each drawn at k + a .. k + b) and of the timed hazards."""
    frames = [[] for _ in range(T + 1)]
    seen = [set() for _ in range(T + 1)]
    for iid, rr in recs.items():
        for r in rr:
            k, a, b = r[0], r[1], r[2]
            lo, hi = max(k + a, 0), min(k + b, T)
            if lo > hi:
                continue
            key = (iid, r[3], r[4], round(r[5], 2), round(r[6], 2), r[7], r[8])
            sh = None
            for kk in range(lo, hi + 1):
                if key in seen[kk]:
                    continue
                if sh is None:
                    sh = rec_shapes(r, iid, K)
                seen[kk].add(key)
                frames[kk].extend(sh)
    for iid, hz in hazards:
        kind, x, y, rad, t0, t1 = hz
        s = Shape(DAMAGE, iid, kind, circle=(x, y, rad), mv=kind)
        key = (iid, kind, round(x, 2), round(y, 2))
        for kk in range(max(t0, 0), min(t1, T) + 1):
            if key not in seen[kk]:
                seen[kk].add(key)
                frames[kk].append(s)
    return frames


def predict(obs: list[Obs], mems: dict, hero: HeroPath, K: Know, T: int = 120, max_choices: int = 2,
            max_particles: int = 2000, group: bool = True, hazards: list | None = None) -> Prediction:
    """The branches of the Clappers' futures (jointly: the buddy lock couples them) over frames 0 .. T under her
    path (module docstring). Output branches are keyed by each Clapper's first max_choices move choices (V4) and its
    Will Evade draws; the deeper choices and Walk's timing bins are still simulated exactly and go into the union of
    their group (n_merged)."""
    t0 = time.perf_counter()
    extra = list(hazards or ())         # (iid, hazard) of a Clapper not in obs (killed after its cast): still to light
    alive = [o for o in obs if o.hp > 0 and o.st not in DEAD]
    buddy = len(alive) > 1
    sims0 = [Sim(o, mems.get(o.iid) or Memory(), K, buddy) for o in alive]
    for s in sims0:
        s.buddy_x = None
    parts = [(1.0, sims0, [[s.rec()] for s in sims0])]
    n_max = 1
    for k in range(1, T + 1):
        new = []
        for p, sims, recs in parts:
            stack = [(p, list(sims), recs, 0)]
            while stack:
                pp, ss, rr, i = stack.pop()
                if i >= len(ss):
                    new.append((pp, ss, rr))
                    continue
                s = ss[i]
                o = ss[1 - i] if len(ss) == 2 else None
                b_att = bool(o.attacking) if o is not None and not o.dead else False
                b_x = o.x if o is not None and not o.dead else None
                snap = s.clone() if s.may_choose(k, hero) else None
                try:
                    s.step(k, hero, b_att, b_x)
                    rr[i].append(s.rec())
                    stack.append((pp, ss, rr, i + 1))
                except NeedChoice as nc:
                    if snap is None:
                        raise RuntimeError(f"a choice {nc.key} where may_choose said none ({s.st})") from nc
                    for q, outc in nc.options:
                        if q <= 0:
                            continue
                        s2 = snap.clone()
                        s2.choices[nc.key] = outc
                        ss2 = [x.clone() for x in ss]       # every Clapper of the branch is its own from here
                        ss2[i] = s2
                        rr2 = [list(x) for x in rr]
                        stack.append((pp * q, ss2, rr2, i))
        parts = new
        n_max = max(n_max, len(parts))
        if len(parts) > max_particles:
            parts.sort(key=lambda t: -t[0])
            parts = parts[:max_particles]
    if not group:
        out = []
        for p, sims, recs in sorted(parts, key=lambda t: -t[0]):
            chs = {s.iid: [c for c in s.log if c[0] in CHOICE_KINDS] for s in sims}
            rv = [c[3] for ch in chs.values() for c in ch if c[3] is not None]
            b = Branch(p, chs, min(rv) if rv else None, {s.iid: rr for s, rr in zip(sims, recs)},
                       [(s.iid, h) for s in sims for h in s.hazards] + extra, K, T, 1)
            b.logs = {s.iid: s.log for s in sims}
            out.append(b)
        return Prediction(out, T, n_max, (time.perf_counter() - t0) * 1000.0)
    groups: dict = {}
    for p, sims, recs in parts:
        key, chs = [], {}
        for s in sims:
            moves = [c for c in s.log if c[0] in MOVE_KINDS][:max_choices]
            evs = [c for c in s.log if c[0] == "will_evade" and c[3] is not None and
                   (not moves or c[2] <= moves[-1][2])]
            key.append((s.iid, tuple((c[0], c[1]) for c in moves), tuple(c[1] for c in evs)))
            chs[s.iid] = sorted(moves + evs, key=lambda c: c[2])
        key = tuple(key)
        g = groups.get(key)
        if g is None:
            rv = [c[3] for ch in chs.values() for c in ch if c[3] is not None]
            groups[key] = g = {"p": 0.0, "recs": {s.iid: [] for s in sims}, "haz": [], "choices": chs,
                               "reveal": min(rv) if rv else None, "n": 0}
        g["p"] += p
        g["n"] += 1
        if g["n"] == 1:
            g["haz"].extend(extra)
        for s, rr in zip(sims, recs):
            g["recs"][s.iid].append(rr)
            g["haz"].extend((s.iid, h) for h in s.hazards)
    branches = []
    for key, g in sorted(groups.items(), key=lambda kv: -kv[1]["p"]):
        recs = {}
        for iid, lists in g["recs"].items():
            if len(lists) == 1:
                recs[iid] = lists[0]
                continue
            seen, out = set(), []
            for rr in lists:
                for r in rr:
                    kk = (r[0], r[1], r[2], r[3], r[4], round(r[5], 3), round(r[6], 3), r[7], r[8])
                    if kk not in seen:
                        seen.add(kk)
                        out.append(r)
            recs[iid] = out
        hz = list({(h[0],) + tuple(round(v, 3) if isinstance(v, float) else v for v in h[1]): h
                   for h in g["haz"]}.values())
        branches.append(Branch(g["p"], g["choices"], g["reveal"], recs, hz, K, T, g["n"]))
    return Prediction(branches, T, n_max, (time.perf_counter() - t0) * 1000.0)


# ---- a move's timeline in its own frame ----

MOVE_START = {"slam": "Slam Antic", "cast": "Spell Antic", "jump": "Jump Antic", "jcast": "Cast Slam Antic",
              "evade": "Evade Scuttle"}


def move_timeline(K: Know, move: str, T: int = 200, jump_dx: float = 0.0) -> list[list[Shape]]:
    """The move's shapes per frame 0 .. T from its first state, in its own frame: x along its facing relative to its
    transform at frame 0 (the anchor), y relative to the anchor's y; the nominal timing (the measured median
    durations; the union over the timing variants is what predict() draws). move: slam / cast / jump / jcast / evade;
    jump_dx: a jump's Jump X (its landing moves 0.916 x jump_dx). After the move it stands in Idle (no new choice)."""
    x0 = 0.5 * (WALL_L + WALL_R)
    face = 1
    hx = x0 + face * (TARGET_U + jump_dx) if move in ("jump", "jcast") else x0 + 30.0
    o = Obs(1, MOVE_START[move], 0.0, x0, STAND_Y, 0.0, 0.0, face, 10 ** 6, None, will_evade=False, j=0)
    mem = Memory()
    if move == "jcast":
        mem.charged = True
    sim = Sim(o, mem, K, buddy=False)
    if move == "evade":
        sim.vx = -EVADE_SPEED * face
    hero = HeroPath.constant(hx, 30.0, T=T)          # far above: out of Slam Range, the aim from her x
    out = [[]]
    rec = [sim.rec()]
    for k in range(1, T + 1):
        try:
            sim.step(k, hero, False, None)
        except NeedChoice:                                # its next move: the timeline ends with this one
            break
        if sim.st in ("Walk", "Close Range", "Far Range"):
            sim.st, sim.j = "Idle", sim.j
        rec.append(sim.rec())
    frames = build_frames({1: [(r[0], 0, 0) + tuple(r[3:]) for r in rec]},
                          [(1, h) for h in sim.hazards], K, T)
    for fr in frames:
        rel = []
        for s_ in fr:
            if s_.box is not None:
                a, b = sorted(((s_.box[0] - x0) * face, (s_.box[2] - x0) * face))
                rel.append(Shape(s_.kinds, 1, s_.name, box=(a, s_.box[1] - STAND_Y, b, s_.box[3] - STAND_Y), mv=s_.mv))
            elif s_.poly is not None:
                rel.append(Shape(s_.kinds, 1, s_.name, poly=np.stack([(s_.poly[:, 0] - x0) * face,
                                                                      s_.poly[:, 1] - STAND_Y], axis=1), mv=s_.mv))
            else:
                cx, cy, r = s_.circle
                rel.append(Shape(s_.kinds, 1, s_.name, circle=((cx - x0) * face, cy - STAND_Y, r), mv=s_.mv))
        out.append(rel)
    return out[1:]


# ---- the online tracker (what the history tells, for Obs) ----

CLAPPER = "Song Heavy Sentry"


class Tracker:
    """Online: feed every game frame's STATE (the oracle's dict: the Clappers' entities - Control state and time,
    position, velocity, flipX, hp, clip - and the frame's events - the Control transitions with their instant states);
    obs() then gives each living Clapper's Obs with what its history tells (Will Evade shown false, the turn's age,
    the bomb row / big rune still to light, Idle Time's buddy, the previous state) and mems its Memory (the V4
    counters replayed from the fight's start). The same rules as the validation's (ssbot.tools.m2_validate Episode)."""

    def __init__(self):
        self.k = 0
        self.cl: dict = {}
        self.hero_box = None

    def _t(self, iid: int) -> dict:
        t = self.cl.get(iid)
        if t is None:
            t = self.cl[iid] = {"mem": Memory(), "st": None, "ent": 0, "prev": None, "face": None, "face_k": None,
                                "cast2": None, "rune": None, "idle_no_ev": False, "idle_bud": None, "clip": None,
                                "x": None, "y": None, "e": None}
        return t

    def feed(self, s: dict, k: int | None = None) -> None:
        self.k = self.k + 1 if k is None else int(k)
        k = self.k
        h = s.get("hero") or {}
        if h.get("box"):
            self.hero_box = tuple(float(v) for v in h["box"][:4])
        ents = {int(e["iid"]): e for e in s.get("ents") or () if e.get("type_key") == CLAPPER and e.get("pos")}
        for ev in s.get("ev") or ():
            d = ev.get("d") or {}
            if ev.get("k") != "fsm" or d.get("fsm") != "Control" or not str(d.get("obj") or "").startswith(CLAPPER):
                continue
            iid = int(d.get("iid") or d.get("ent") or 0)
            t = self._t(iid)
            frm, to = d.get("from"), d.get("to")
            charged = t["mem"].charged
            t["mem"].observe(frm, to, t["clip"])
            e = ents.get(iid)
            x = float(e["pos"][0]) if e else t["x"]
            y = float(e["pos"][1]) if e else t["y"]
            face = (1 if e.get("flipX") else -1) if e else t["face"]
            if to == "Cast 2" and x is not None:
                t["cast2"] = (k, x, y)
            if to == "Charged?" and charged and x is not None:
                t["rune"] = (k, x, face)
            if to not in INSTANT and to is not None:
                if t["st"] is not None and t["st"] != to:
                    t["prev"] = t["st"]
                t["st"], t["ent"] = to, k
                if to == "Idle":
                    t["idle_no_ev"] = False
                    t["idle_bud"] = any(o != iid and not ((oe.get("hp") or 0) <= 0 or oe.get("is_dead"))
                                        for o, oe in ents.items())
        for iid, e in ents.items():
            t = self._t(iid)
            st, tin = None, 0.0
            for m in e.get("fsms") or ():
                if m.get("name") == "Control":
                    st, tin = m.get("state"), float(m.get("t") or 0.0)
            if st is not None and st != t["st"]:            # a transition the events did not show
                if t["st"] is not None:
                    t["prev"] = t["st"]
                t["st"], t["ent"] = st, k - int(round(tin * 60.0))
            face = 1 if e.get("flipX") else -1
            if t["face"] != face:
                t["face"], t["face_k"] = face, (k if t["face"] is not None else None)
            t["clip"] = (e.get("anim") or {}).get("clip")
            t["x"], t["y"] = float(e["pos"][0]), float(e["pos"][1])
            t["e"] = e
            if st == "Idle" and k - t["ent"] >= EV_K[2] and self.hero_box is not None and not t["idle_no_ev"]:
                hx, ry0, ry1 = SLAM_RANGE
                b, m_ = self.hero_box, RANGE_SKIN
                if b[0] < t["x"] + hx + m_ and b[2] > t["x"] - hx - m_ and b[1] < t["y"] + ry1 + m_ and                         b[3] > t["y"] + ry0 - m_:
                    t["idle_no_ev"] = True
        for iid in list(self.cl):
            if iid not in ents:
                self.cl[iid]["e"] = None

    def obs(self) -> list[Obs]:
        out = []
        for iid, t in self.cl.items():
            e = t["e"]
            if e is None or (e.get("hp") or 0) <= 0 or e.get("is_dead") or t["st"] in DEAD or t["st"] is None:
                continue
            k = self.k
            o = Obs.from_entity(e)
            o.j = k - t["ent"]
            o.turn_age = (k - t["face_k"]) if t["face_k"] is not None else 10 ** 6
            o.charged = bool(t["mem"].charged)
            o.prev = t["prev"]
            if o.st == "Idle" and t["idle_no_ev"]:
                o.will_evade = False
            if o.st == "Idle":
                o.idle_buddy = t["idle_bud"]
            if t["cast2"] is not None and k - t["cast2"][0] <= 150:
                c = t["cast2"]
                o.cast2 = (c[0] - k, c[1], c[2])
            if t["rune"] is not None and k - t["rune"][0] <= 100:
                r = t["rune"]
                o.rune = (r[0] - k, r[1], r[2])
            out.append(o)
        return out

    def mems(self) -> dict:
        return {iid: t["mem"].copy() for iid, t in self.cl.items()}

    def hazards(self, K: Know) -> list:
        """(iid, hazard) of the bomb rows / big runes still to light of the Clappers obs() leaves out (dead)."""
        live = {o.iid for o in self.obs()}
        out = []
        for iid, t in self.cl.items():
            if iid in live:
                continue
            if t["cast2"] is not None and self.k - t["cast2"][0] <= 150:
                c = t["cast2"]
                out += [(iid, h) for h in bomb_hazards(K, c[0] - self.k, c[1], c[2])]
            if t["rune"] is not None and self.k - t["rune"][0] <= 100:
                r = t["rune"]
                out += [(iid, h) for h in rune_hazards(K, r[0] - self.k, r[1], r[2])]
        return out


__all__ = ["Know", "Shape", "Obs", "HeroPath", "Memory", "V4", "Sim", "Branch", "Prediction", "predict",
           "DAMAGE", "BODY", "POGO", "TINK", "HAMMER", "SLAM_RANGE", "hurtbox", "poly_box_hit", "walk_bins",
           "roof_y", "Tracker", "move_timeline", "MOVE_OF", "rune_hazards", "bomb_hazards"]
