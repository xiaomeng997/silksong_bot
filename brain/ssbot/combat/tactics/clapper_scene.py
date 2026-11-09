"""Shared facts of one manual-B two-Clapper L2 call (Task 180): the scene every tactic reads.

The observed standing spans, the ground stance beside a body, the standing-gap test and the shared side / stomp
entry for a switch are computed here once per call and read by every tactic (clapper_tactics); none of them is a
tactic of its own. Geometry and preferences never certify an action: every key still goes through its action owner.
"""
import math
from dataclasses import dataclass, field

import numpy as np

from .forum_local import CLAPPER
from .modes import EntryAttack

JUMPS = {"CC_JUMP", "CC_JUMP_CAST"}
NEAR = {"Slam Antic", "Spell Antic"}
AIR = {"Jump", "Air"}
ANTIC = {"Jump Antic", "Cast Slam Antic", "Cast Slam Antic 2"}
SLAMMING = {"Slam Antic", "Slam 0", "Slam 1", "Slam 2"}
STACK_U = 4.5        # Task 182 seq 303: the two roots this close: their bodies (+-2.25 u about each root) touch: stacked, or passing through each other
NEARER_U = 1.0       # the other root this much nearer to her than the kept focus's (her centre to each root, u) is clearly nearer; within it the focus stays


@dataclass
class Scene:
    """One L2 call's facts. Observation fills `events` (each event tactic's live context, None when not active);
    a pick tick adds the candidate facts (`cands` .. `other`); the application adds the per-tick outputs."""
    tac: object
    ws: object
    fc: object
    prefs: object
    hx: float
    t: float
    subjects: list
    mem: dict
    geo: dict | None
    region: str | None
    keep: object = None                 # the kept focus (tac.goal's target) when it is still in play
    seen: dict = field(default_factory=dict)
    events: dict = field(default_factory=dict)
    cands: list | None = None           # the pick: tac.candidates, by iid, outer room, default and other one
    by_id: dict | None = None
    room: dict | None = None
    default: object = None
    other: object = None
    scene: str = "attack focus"         # the applied scene name (log and goal why)
    back_pose: dict | None = None       # the middle return's applied pose this tick (its winner only)
    table: object = None                # clapper_tactics.table(): the tactic set of this call
    plans: object = None                # SSBOT_FORUM_TWO_PLAN only: clapper_plans.PlanRunner

    def subject(self, iid):
        return next(s for s in self.subjects if s.iid == iid)

    @property
    def frame(self):
        return getattr(getattr(self.ws, "stamp", None), "frame", None)

    @property
    def grounded(self):
        return getattr(getattr(self.ws.hero, "contact", None), "v", None) == "GROUND"


def stacked_nearer(sc):
    """Task 182 seq 303 (the person: two Clappers stacked, passing through each other, the bot cannot tell which is nearer; the focus must follow):
    the other Clapper when the pair is stacked (roots within STACK_U), it is clearly nearer to her (by more than NEARER_U, so near-equal distances keep
    the focus and the entity order plays no part), it is not in a jump's flight (no target there), and the kept focus is not in its slam (the strike and
    the hammer stay with the owners already on them); else None."""
    keep = sc.keep
    if keep is None or len(sc.subjects) != 2:
        return None
    other = next(s for s in sc.subjects if s.iid != keep.iid)
    xk, xo = float(keep.pos[0]), float(other.pos[0])
    if abs(xk - xo) >= STACK_U or other.state in AIR or keep.state in SLAMMING:
        return None
    return other if abs(xk - sc.hx) - abs(xo - sc.hx) > NEARER_U else None


def geometry(tac, ws, subjects):
    """Observed horizontal standing spans only; unknown boxes stay unknown."""
    try:
        hx = float(ws.hero.pos.v[0])
        if not .8 <= ws.hero.pos.conf <= 1.: return None
        hurt = np.asarray(ws.hero.hurtbox, float)
        if hurt.ndim != 2 or hurt.shape[0] < 3 or hurt.shape[1] != 2 or not np.isfinite(hurt).all(): return None
        left, right = hx - hurt[:, 0].min(), hurt[:, 0].max() - hx
        xa, xb = map(float, tac.pb.arena_x)
        if min(left, right) <= 0 or not np.isfinite([hx, xa, xb]).all() or not xa <= hx <= xb: return None
        bodies = {}
        for s in subjects:
            boxes = [b for b in getattr(tac._ent(ws, s.iid), "dmg_boxes", ()) or ()
                     if b.active is True and isinstance(b.name, str) and b.name.startswith(CLAPPER)]
            if len(boxes) != 1: return None
            p = np.asarray(boxes[0].poly, float)
            if p.ndim != 2 or p.shape[0] < 3 or p.shape[1] != 2 or not np.isfinite(p).all(): return None
            a, b = float(p[:, 0].min()), float(p[:, 0].max())
            if a >= b: return None
            bodies[s.iid] = (a, b)
        low, high = sorted(subjects, key=lambda s: float(s.pos[0]))
        lo, hi = bodies[low.iid][1] + left, bodies[high.iid][0] - right
        region = ("left" if hx + right <= bodies[low.iid][0] else
                  "right" if hx - left >= bodies[high.iid][1] else
                  "middle" if lo <= hx <= hi else
                  "tight" if lo > hi and low.pos[0] <= hx <= high.pos[0] else "over")
        return dict(bodies=bodies, left=float(left), right=float(right), xa=xa, xb=xb,
                    low=low, high=high, lo=float(lo), hi=float(hi), region=region)
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None


def standing_gap(geo):
    """Whether the bodies' gap holds the existing middle standing footprint (JT gap_u plus a pad each side, as
    clapper_middle._standing); None when the bodies are unknown."""
    if geo is None:
        return None
    from .gauntlet import JT
    (_, b1), (a2, _) = geo["bodies"][geo["low"].iid], geo["bodies"][geo["high"].iid]
    return a2 - b1 - 2 * JT["pad"] >= max(JT["gap_u"], geo["left"] + geo["right"])


def ground_stance(tac, target, hx, geo):
    if geo is None: return None
    a, b = geo["bodies"][target.iid]
    other = geo["high"] if target.iid == geo["low"].iid else geo["low"]
    c, d = geo["bodies"][other.iid]
    if hx < target.pos[0]:
        lo = max(geo["xa"], d if c < a else geo["xa"]) + geo["left"]
        hi = a - geo["right"]
    else:
        lo = b + geo["left"]
        hi = min(geo["xb"], c if d > b else geo["xb"]) - geo["right"]
    return (min(hi, max(lo, target.pos[0] + (-1 if hx < target.pos[0] else 1) * tac.rules.face_u))
            if lo < hi else None)


def entry(tac, ws, fc, source, target, t, geo):
    """The shared entry for a switch: ground room plus the existing forecast window chooses side versus stomp."""
    if source is None or source.iid == target.iid or source.family not in JUMPS | {"CC_CAST", "CC_SLAM"}:
        return None, None
    hx = float(ws.hero.pos.v[0]); stance = ground_stance(tac, target, hx, geo)
    if stance is not None:
        arrival = tac.rules.start_s + abs(stance - hx) / tac.rules.run_u_s
        end = arrival + tac.rules.swing_s + tac.rules.margin_s
        if end > tac.rules.window_max_s:
            stance = None
        else:
            times = np.linspace(arrival, end, max(2, int(math.ceil((end - arrival) * 30)) + 1))
            X = np.full((1, len(times)), stance)
            occ = np.asarray(fc.occupied(X, np.full_like(X, tac.floor_y), times))
            if occ.shape != X.shape or occ.dtype.kind != "b" or occ.any(): stance = None
    kind = "stomp" if stance is None else "side"
    return EntryAttack(target.iid, kind, source.iid, source.family,
                       abs(float(source.pos[0]) - hx), t), stance
