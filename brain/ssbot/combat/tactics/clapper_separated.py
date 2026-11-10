"""Task 182 seq 312 (the person 11-09 / 11-10; plan: main docs/plans/forum_clapper_l2_tactics.md "seq312", design:
opus/review182/q_cross/DESIGN_SEPARATED.md): the facts the L2 units of this package read, once per call.

  separated  the far one of the two (F) begins a move with the near one (N) between her and it (both on one side of her), or a live
             big rune circle lies across her way to it. Bodies: the current observed spans (clapper_scene.geometry); circles: the
             shared ledger (rune_life, seq 310), she not inside one.
  slam       F's slam: the range edge on her side (its antic-entry root, its facing toward her, the measured furthest hammer front),
             the place outside it for each of the plan's branches 1.1 / 1.2.1 / 1.2.2 / 1.2.3, and 1.2.2's way into the middle once
             both hammer stages are over.
  small rune the casts and their bombs by the shared per-bomb forecast (rune_bombs, the tracker's own), the down-slash target in the
             order both > F > N, and the two tiers of its end (2.3).
  stacked    #379: the seam double's intent condition (both near body edges within one blade's width at their tops, the tops level);
             without it the ground stance in front of the near one on her side.

Every value here is an intent for the L2 units (clapper_tactics). It certifies nothing: every key, crossing, landing and hit still goes
through the existing action owners and their checks (the planner's rows score each predicted contact on each body with the model).
SSBOT_FORUM_SEP312=0 turns the package's L2 units off (offline comparisons only)."""
from __future__ import annotations

import math
import os

import numpy as np

ENABLED = os.environ.get("SSBOT_FORUM_SEP312", "1").strip() != "0"
# Offline A/B only: the package acts from this frame on (before it every change here is inert, so a replay keeps the recording's keys up
# to the model start both trees share); unset or 0: always
FROM_F = int(os.environ.get("SSBOT_FORUM_SEP312_FROM", "0").strip() or 0)
NOW_F = None             # the frame of the current L2 call (clapper_priority.decide sets it before any unit reads it)


def active(frame=None) -> bool:
    """The package acts now: ENABLED, and past FROM_F (the given frame, else the current L2 call's)."""
    if not ENABLED:
        return False
    f = NOW_F if frame is None else frame
    return FROM_F <= 0 or f is None or f >= FROM_F

CC_SLAM, CC_CAST = "CC_SLAM", "CC_CAST"
JUMPS = frozenset({"CC_JUMP", "CC_JUMP_CAST"})
ATTACKS = frozenset({CC_SLAM, CC_CAST}) | JUMPS
SLAMMING = frozenset({"Slam Antic", "Slam 0", "Slam 1", "Slam 2"})
CASTING = frozenset({"Spell Antic", "Cast 1", "Cast 2"})
JUMP_ANTIC = frozenset({"Jump Antic", "Cast Slam Antic", "Cast Slam Antic 2"})

# ---- the slam (plan 1.x; design 3.2) ----
SLAM_EDGE_U = 12.76      # her centre this far from F's antic-entry root, toward her, is outside the range: the furthest hammer front of the
#                          342 recorded slams (12.255 u, bout 13 49804; a sample maximum, not a physical bound) + her half width 0.25 +
#                          the existing pad 0.25 (the model's own bound, HAMMER_POLY's second front 7.75 + the furthest lunge 4.56, is 12.31)
SLAM_FIRST_F = 50        # Slam Antic entry -> its first hammer frame: the earliest of the 342 (p50 53, at most 77)
ESCAPE_LEAD_F = 2        # the way out reaches the outside this many frames before that
OUT_U = .25              # a stance just outside an edge
ROOM_U = .25             # 1.2.1: the spare centre room inside N, outside the range
POGO_IN_U = .3           # 1.2.2: her centre at least this far over N's body from its outer edge
REACH_U = 3.02           # the side slash from her centre to a body edge (knife_chain_transfer.FALL_SLASH_X)
POST_S = 1.2             # an after-step (1.2.2's way into the middle, 2.3's one strike): given up this long after it began

# ---- the big rune (are_types.clapper "rune slam"; rune_life) ----
RUNE_HALF_U = 7.187      # the octagon's apothem: its x half span

# ---- the small rune (rune_bombs) and its end (plan 2.x; design 3.3) ----
BOMB_NEAR_U = 1.0        # a bomb's circle this near the span of her and both bodies keeps the small rune on
STRIKE_DY = 1.49         # 2.2's strike (Sol REVIEW383 X14): her Bounds centre over the struck top at a down slash's contact (box bottom
#                          0.5 u over it: rune_bombs' HeroBox, HB_HY 1.1249 and HB_DY 0.133)
STRIKE_F = 8             # ... the frames of the strike window read from the frame she can be there (the press and the blade's frames)
TIER_U = 2.5             # 2.3: the two near body edges at most this far apart (the standing gap's own value): the seam strike; past it the fall slash
FALL_U = 1.0             # 2.3: her box this far from the chosen body's edge, inside the gap, as she falls

# ---- the stacked pair (#379; design 3.6) ----
DOUBLE_GAP_U = 2.8       # the seam double's intent: the two near body edges at most this far apart. The down slash's every modelled variant
#                          (DownSlash / DownSlashAlt, both facings: forum_planner._down_variants) covers her centre +- 1.48 u, 2.96 u, so a gap
#                          she could stand in (2.5 u) can still be met on both sides (the person: the blade is wider than she is); 0.08 u spare
#                          each side for her place. Overlapping bodies always. No gap condition at all (Sol seq 320).
DOUBLE_TOP_U = .5        # ... and their tops within this (the higher top bounces the blade first)


def _span(geo, iid):
    a, b = geo["bodies"][iid]
    return float(a), float(b)


def pair_outside(geo):
    """(near, far) by the roots' order when she stands outside both bodies on one side (clapper_scene's region left / right), else None."""
    if geo is None or geo.get("region") not in ("left", "right"):
        return None
    low, high = geo["low"], geo["high"]
    return (low, high) if geo["region"] == "left" else (high, low)


def live_circles(tac, t):
    """The big rune circles lit now or still to come, as x spans, from the shared ledger (rune_life, the policy's one instance); [] without it."""
    rl = getattr(tac, "rune_life", None)
    if rl is None:
        return []
    return [(float(c.lo), float(c.hi)) for c in rl.live(t)]


def circles_across(tac, t, hx, x_to):
    """The live circles lying across her way from hx to x_to (she not inside one): [(lo, hi)]."""
    lo, hi = min(hx, x_to), max(hx, x_to)
    return [sp for sp in live_circles(tac, t) if not sp[0] <= hx <= sp[1] and sp[0] < hi and sp[1] > lo]


def place_clear(sc, x) -> bool:
    """Sol #382 R1: her centre at x is outside every live big rune circle (grown by her half widths and the pad) and no live circle lies
    across her way there from where she stands (the shared ledger, as circles_across reads it)."""
    from .gauntlet import JT
    geo = sc.geo
    for lo, hi in live_circles(sc.tac, sc.t):
        if lo - geo["right"] - JT["pad"] < x < hi + geo["left"] + JT["pad"]:
            return False
    return not circles_across(sc.tac, sc.t, sc.hx, x)


def behind(hx, near, far) -> bool:
    """The near one's root lies strictly between her centre and the far one's root (both on one side of her; over the near one's outer half
    she is still in front of it)."""
    xn, xf = float(near.pos[0]), float(far.pos[0])
    return (xn - hx) * (xf - xn) > 0


def separated(sc, families):
    """The far one's move (its family in families) with the near one between her and it (by the roots' order: the person's "both on her
    side"), or a live big rune across her way to it: dict(far, near, kind body / rune / both, circles, toward +1 / -1 from her to it), or
    None. With both in such a move the farther one goes first."""
    geo, hx = sc.geo, sc.hx
    if geo is None or len(sc.subjects) != 2:
        return None
    for s in sorted(sc.subjects, key=lambda v: -abs(float(v.pos[0]) - hx)):
        if s.family not in families:
            continue
        other = next(v for v in sc.subjects if v.iid != s.iid)
        a, b = _span(geo, s.iid)
        toward = 1 if float(s.pos[0]) > hx else -1
        near_edge = a if toward > 0 else b
        body = behind(hx, other, s)
        circles = circles_across(sc.tac, sc.t, hx, near_edge)
        if body or circles:
            return dict(far=s, near=other, kind="both" if body and circles else "body" if body else "rune", circles=circles,
                        toward=toward)
    return None


# ---- the slam ----

def slam_record(sc, mem, s):
    """F's slam instance: its antic-entry clock, frame, root and facing (toward her then), kept in mem until the family ends. The clock is
    the FSM's own (the Control row's elapsed time in the state, as clapper_plans._track reads a jump's); first seen past the antic: the
    record starts there and says so."""
    recs = mem.setdefault("sep_slam", {})
    rec = recs.get(s.iid)
    if s.family != CC_SLAM:
        recs.pop(s.iid, None)
        return None
    if rec is not None:
        if s.state == "Slam Recover" and rec.get("recover_f") is None:
            rec["recover_f"] = sc.frame
        return rec
    from .forum_local import clapper_facing
    ent = sc.tac._ent(sc.ws, s.iid)
    elapsed = None
    for row in getattr(ent, "fsm", None) or ():
        if isinstance(row, (tuple, list)) and len(row) == 3 and row[0] == "Control" and row[1] == s.state:
            elapsed = row[2]
    if s.state != "Slam Antic" or type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
        elapsed, seen = None, "first seen past its antic entry"
    else:
        seen = "antic"
    face = clapper_facing(ent) if ent is not None else None
    if face not in (-1, 1):
        face = 1 if sc.hx > float(s.pos[0]) else -1
    f0 = None if (elapsed is None or type(sc.frame) is not int) else sc.frame - int(round(float(elapsed) * 60.))
    rec = recs[s.iid] = dict(t0=sc.t - (elapsed or 0.), f0=f0, x0=float(s.pos[0]), face=int(face), seen=seen, recover_f=None,
                             branch=None, pogo=False)
    return rec


def hammer_over(sc, s, rec) -> bool:
    """Both hammer stages of this slam are over: its Slam Recover seen at least one frame ago (a hit in frame g reads the colliders at the end
    of g - 1), or the family has ended."""
    if s.family != CC_SLAM:
        return True
    rf = rec.get("recover_f")
    return rf is not None and type(sc.frame) is int and sc.frame >= rf + 1


def slam_place(sc, sep, rec):
    """Where she stands for F's slam (plan 1.1 / 1.2.1-1.2.3), from its range edge on her side. dict(branch, stance, target, style, no_hit,
    edge, inside, escape_x) or None: no place outside the range on her side inside the walls (the existing rules keep it: design 3.2, the
    8 wall cases)."""
    geo, hx = sc.geo, sc.hx
    face = rec["face"]                                  # the hammer comes toward her: +1 she is to its right
    edge = rec["x0"] + face * SLAM_EDGE_U
    half_in = geo["left"] if face > 0 else geo["right"]     # her half width toward F
    pad = .25
    wall = geo["xb"] if face > 0 else geo["xa"]
    out_x = edge + face * OUT_U
    if (wall - face * (half_in + pad) - out_x) * face < 0:
        return None
    far, near = sep["far"], sep["near"]
    inside = (hx - edge) * face < 0
    res = dict(edge=edge, inside=inside, escape_x=out_x, face=face)
    if sep["kind"] == "rune":
        # 1.1: at the outer one of the circle's edge and the range edge, whatever she reaches she slashes
        stance = out_x
        for lo, hi in sep["circles"]:
            x = (hi + half_in + pad) if face > 0 else (lo - half_in - pad)
            stance = max(stance * face, x * face) * face
        res.update(branch="1.1", stance=stance, target=near, style=None, no_hit=frozenset({far.iid}), escape_x=stance)
        return res
    na, nb = _span(geo, near.iid)
    n_in, n_out = (na, nb) if face > 0 else (nb, na)     # N's edge toward F, toward her
    x_in = n_in - face * (half_in + pad)
    if (x_in - edge) * face >= ROOM_U:
        # 1.2.1: room past N toward F, outside the range: over it, its inner side slashed (the crossing is the owners')
        style = None if (hx - n_in) * face < 0 else "stomp"
        res.update(branch="1.2.1", stance=x_in, target=near, style=style, no_hit=frozenset({far.iid}))
        return res
    if (out_x - n_in) * face > 0 and (n_out - out_x) * face >= POGO_IN_U:
        # 1.2.2: N's body reaches out past the range edge: down slashes on it from just outside
        res.update(branch="1.2.2", stance=out_x, target=near, style="stomp", no_hit=frozenset({far.iid}))
        return res
    # 1.2.3: outside the range; N only while it is within the side slash's reach of the stance
    reach = (out_x - n_out) * face <= REACH_U
    res.update(branch="1.2.3", stance=out_x, target=near, style=None,
               no_hit=frozenset({far.iid}) if reach else frozenset({far.iid, near.iid}))
    return res


def middle_room(geo, near, far, face):
    """The gap between N's inner edge and F's near edge is standable (clapper_scene.standing_gap's test on these two): (lo, hi) of her
    centre in it, or None."""
    from .gauntlet import JT
    na, nb = _span(geo, near.iid)
    fa, fb = _span(geo, far.iid)
    if face > 0:
        lo_edge, hi_edge = fb, na          # F left of N
    else:
        lo_edge, hi_edge = nb, fa
    if hi_edge - lo_edge - 2 * JT["pad"] < max(JT["gap_u"], geo["left"] + geo["right"]):
        return None
    return lo_edge + JT["pad"] + geo["left"], hi_edge - JT["pad"] - geo["right"]


def fall_x(geo, body_iid, toward_gap, lo, hi):
    """Her centre FALL_U (box to box) from that body's edge, inside the gap [lo, hi]."""
    a, b = _span(geo, body_iid)
    x = (b + FALL_U + geo["left"]) if toward_gap > 0 else (a - FALL_U - geo["right"])
    return min(max(x, lo), hi)


# ---- the small rune ----

def bombs_now(tac):
    """The small runes' per-bomb forecast of this tick (rune_bombs.frames from the tracker the policy feeds: owner, x, y, r, on_k, off_k),
    or None without one."""
    trk = getattr(tac, "v2trk", None)
    rb = getattr(trk, "rune", None)
    if rb is None:
        return None
    from ssbot.combat import rune_bombs
    return rune_bombs.frames(rb.predict(trk.T), trk.T)


def rune_on(sc, bombs):
    """The small rune is on: a Clapper in its cast, or a bomb not yet over whose circle meets the span of her and both bodies (the shared
    per-bomb forecast). (on, casters: the iids casting or owning such a bomb)."""
    casters = {s.iid for s in sc.subjects if s.family == CC_CAST and s.state in CASTING}
    on = bool(casters)
    if bombs is not None and len(bombs) and sc.geo is not None:
        spans = [_span(sc.geo, s.iid) for s in sc.subjects]
        lo = min([sc.hx] + [a for a, _ in spans]) - BOMB_NEAR_U
        hi = max([sc.hx] + [b for _, b in spans]) + BOMB_NEAR_U
        b = np.asarray(bombs, float)
        live = (b[:, 5] >= 0) & (b[:, 1] + b[:, 3] >= lo) & (b[:, 1] - b[:, 3] <= hi)
        if live.any():
            on = True
            casters |= {int(v) for v in b[live, 0] if v >= 0}
    return on, casters


def strike_covered(sc, s, x, bombs) -> bool:
    """Sol REVIEW383 (X14, #384): 2.2's down slash on s from x is covered by the small rune's bombs: her box at the contact height over s's
    current top (STRIKE_DY), on a frame of its strike window (from the frame she can be there, by the shared entry's start and run constants
    from where she is, through STRIKE_F frames on), meets a lit bomb of the shared per-bomb forecast (rune_bombs.occupied). True: that target
    is not one she can strike now; False: every frame free, or nothing is known (no bombs, no top). (A bomb is lit about 6 frames and one
    place sees one ring: a whole-window reading would never hold.)"""
    if bombs is None or not len(bombs) or sc.geo is None:
        return False
    top = (sc.geo.get("tops") or {}).get(s.iid)
    if top is None:
        return False
    from ssbot.combat import rune_bombs as RB
    r = sc.tac.rules
    k0 = int(math.ceil((float(r.start_s) + abs(float(x) - sc.hx) / float(r.run_u_s)) * 60.))
    k1 = k0 + STRIKE_F
    b, x, y = np.asarray(bombs, float), float(x), float(top) + STRIKE_DY
    # (cost: occupied walks its rows one by one, ~8 us each) only a row lit inside the window whose circle meets her box at this one place
    # covers a frame of it: occupied's own contact rule at m = 0, one vectorised pass decides a free window; a covered one is confirmed by
    # occupied itself on the first such row (the same answer as occupied over every row)
    dx = np.maximum(np.abs(x - b[:, 1]) - RB.HB_HX, 0.)
    dy = np.maximum(np.abs(y + RB.HB_DY - b[:, 2]) - RB.HB_HY, 0.)
    near = b[(dx * dx + dy * dy < b[:, 3] * b[:, 3]) & (b[:, 4] <= k1) & (b[:, 5] >= k0)]
    if not len(near):
        return False
    ks = np.arange(k0, k1 + 1)
    return bool(np.any(RB.occupied(near[:1], np.full(len(ks), x), np.full(len(ks), y), ks, 0.)))


def blocked_iids(sc) -> frozenset:
    """GoalPrefs.blocked: the Clappers she cannot go straight at now (reachable's test on each)."""
    if sc.geo is None or len(sc.subjects) != 2:
        return frozenset()
    a, b = sc.subjects
    return frozenset(s.iid for s, o in ((a, b), (b, a)) if not reachable(sc, s, o))


def reachable(sc, target, other):
    """By the roots' order and the live circles only: the other one does not stand between her and this one, and no big rune lies across
    the way to it."""
    a, b = _span(sc.geo, target.iid)
    edge = a if float(target.pos[0]) > sc.hx else b
    return not behind(sc.hx, other, target) and not circles_across(sc.tac, sc.t, sc.hx, edge)


def double_intent(geo):
    """#379 / 2.2's seam double: the two near body edges at most DOUBLE_GAP_U apart (overlapping always) with their tops within
    DOUBLE_TOP_U. Geometry only: the planner's rows score the actual predicted contact on each body (this never certifies a double hit).
    (ok, seam x)."""
    low, high = geo["low"], geo["high"]
    (a1, b1), (a2, b2) = _span(geo, low.iid), _span(geo, high.iid)
    gap = a2 - b1
    seam = .5 * (b1 + a2) if gap >= 0 else .5 * (max(a1, a2) + min(b1, b2))
    tops = geo.get("tops") or {}
    ta, tb = tops.get(low.iid), tops.get(high.iid)
    level = ta is not None and tb is not None and abs(ta - tb) <= DOUBLE_TOP_U
    return bool(gap <= DOUBLE_GAP_U and level), float(seam)


def gap_of(geo):
    low, high = geo["low"], geo["high"]
    return _span(geo, high.iid)[0] - _span(geo, low.iid)[1]


def wall_room(geo, s):
    """The distance from this Clapper's root to its nearest wall."""
    x = float(s.pos[0])
    return min(x - geo["xa"], geo["xb"] - x)


def outer_ground(tac, geo, hx):
    """#379's ground stance in front of the near one on her side: the pair's member on her side of their seam, and the existing ground
    stance (clapper_scene.ground_stance) on its outer side. (near subject, stance x)."""
    from .clapper_scene import ground_stance
    low, high = geo["low"], geo["high"]
    seam = .5 * (_span(geo, low.iid)[1] + _span(geo, high.iid)[0])
    near, side = (low, -1) if hx <= seam else (high, 1)
    a, b = _span(geo, near.iid)
    x = ground_stance(tac, near, a - 1. if side < 0 else b + 1., geo)
    return near, (x if x is not None else tac._clamp(float(near.pos[0]) + side * tac.rules.face_u))
