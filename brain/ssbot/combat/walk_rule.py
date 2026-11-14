"""The other Clapper's Idle / Walk body on a whole route, by its walk rule (the person 2026-11-13, design doc
docs/plans/forum_clapper_committed_chain.md quote 130 and section 3.2; SSBOT_FORUM_TWO_WALK_RULE, default on).

A Clapper walks toward her only while she is farther than D_FWD (5.5 u, |dx| = her x - its root x: DistanceWalk's
reversal, map2.clapper WALK_DIST - WALK_RANGE); nearer, it only attacks, backs off or evades, and its moves are their
own forecast. So on one route of hers its root stays in an interval that starts at its root now and whose ends move
out by V_WALK (8 u/s) a frame: the end on her side only while some x of hers in the last LAG_F + 1 frames lies
farther than D_FWD - one step from that end, the end away from her always. Walls are ignored (they only stop it
earlier). Its body at a frame is its standing / walking body of either facing over that interval (TURN_U each side of
the root, the floor to BODY_TOP_U) grown by MARGIN_U; her HeroBox (swept from the previous frame) meeting it is a body
contact. The interval only grows, so the previous frame's body (whose colliders the damage reads) is inside it.

Sol seq 359 (Astra, #418 P2): a route that starts later than the forecast origin (a continuation after a bounce, a hook's
stop or control) walks the frames before it too. Her x there comes from the same candidate's earlier part when the
caller passes it (B2Geometry scan / preflight prelude=, scan_batch preludes=, or a path's walk_prelude); any frame of
hers that is not known (no prelude, a tracker history shorter than LAG_F + 1 frames) is unknown and lets the walker
close, so a later route alone is never checked against a smaller interval than the whole candidate.

Recordings (rx411 10 + new-50 50 bouts, 120 Clapper tracks, 3.78 M start / look-ahead pairs up to 60 frames while it
has no move; Opus walkcheck.py / walkexcess.py 11-13): the real root left this interval by more than 0.2 u toward her
in 439 pairs, by at most 0.35 u (inside MARGIN_U); away from her in 1,449 pairs (at most 0.61 u), never with her
within 4 u. The support's bound (the root carried at its velocity +- the "rule" margin) missed 7.1 %. LAG_F 2 left
toward-her misses up to 1.71 u; D_FWD 8.5 (no closing inside 8.5 u) missed 4.0 %.

knife_chain_geometry.B2Geometry uses it for the body contacts of every Clapper it covers (walker_x) on its whole-route
queries; the support's raster still covers that Clapper's cells (no "other" contact), its delayed hazards stay, a
Clapper in a move instance keeps its forecast and the route's target keeps its own treatment. The planner's rows and
every other reader of the support are unchanged.
"""
from __future__ import annotations

import math
import os

import numba
import numpy as np

ENABLED = os.environ.get("SSBOT_FORUM_TWO_WALK_RULE", "1").strip() == "1"
CLAPPER = "Song Heavy Sentry"
D_FWD = 5.5                 # u: map2.clapper WALK_DIST - WALK_RANGE (DistanceWalk turns back nearer than this)
V_WALK = 8.0                # u/s: map2.clapper WALK_SPEED
LAG_F = 10                  # frames: the walk reads her x up to this late (recordings above)
V_IDLE_MAX = 8.5            # u/s: a Clapper with no move faster than this (x or y) keeps its raster body
TURN_U = 2.3                # u: jump_behind CFG turn_u (its standing body of either facing reaches this far)
BODY_TOP_U = 3.92           # u: jump_behind BODY_TOP_U (the standing body's top above the floor)
MARGIN_U = 0.5              # u: forum_v2 FOCUS_M (the "rule" margin's k <= 12 value)
FLOOR_Y = 3.0               # core.forum FLOOR_Y
HB_HX, HB_HY, HB_DY = 0.2277, 1.1249, 0.133     # forum_v2 HeroBox half extents and centre - Bounds centre (y)
FT = 1.0 / 60.0             # attack_range FT
HIST_N = LAG_F + 1


def walker_x(trk, iid, target_iid) -> float | None:
    """The root x of a tracked Clapper the walk rule covers on a route at target_iid: not that target, no move
    instance, a finite position and velocity within V_IDLE_MAX; None otherwise (and with the switch off)."""
    if not ENABLED or iid is None:
        return None
    if target_iid is not None and int(iid) == int(target_iid):
        return None
    cur = (getattr(trk, "now", None) or {}).get(iid)
    if cur is None:
        return None
    tk, e, inst = cur
    if tk != CLAPPER or inst is not None or not isinstance(e, dict):
        return None
    p = e.get("pos")
    if not p:
        return None
    vel = e.get("vel") or (0.0, 0.0)
    try:
        x = float(p[0])
        vx = float(vel[0] or 0.0)
        vy = float(vel[1] or 0.0) if len(vel) > 1 else 0.0
    except (TypeError, ValueError, IndexError):
        return None
    if not (math.isfinite(x) and math.isfinite(vx) and math.isfinite(vy)):
        return None
    if abs(vx) > V_IDLE_MAX or abs(vy) > V_IDLE_MAX:
        return None
    return x


def hero_history(trk) -> np.ndarray:
    """Her x over the HIST_N frames up to the tracker's now, oldest first (RangeTracker.hero_hist; none: her x now).
    Frames the tracker has not seen are nan, unknown (Sol seq 359: a missing x is never filled from a known one; the
    walk rule reads an unknown x as one that lets the walker close). Nothing known: empty."""
    h = getattr(trk, "hero_hist", None)
    vals = [float(v) for v in list(h)[-HIST_N:]] if h else []
    if not vals:
        hero = getattr(trk, "hero", None)
        if not hero:
            return np.zeros(0)
        vals = [float(hero[0])]
    return np.array([np.nan] * (HIST_N - len(vals)) + vals, np.float64)


def prelude_xs(spec):
    """(first frame, her x per frame from it) of a prelude spec: (first_frame, xs), or a path-like (its pos x, else its
    box centres, from its own origin): the part of the same candidate before a route that starts later (Sol seq 359)."""
    if isinstance(spec, tuple) and len(spec) == 2 and not hasattr(spec, "box"):
        return int(spec[0]), np.asarray(spec[1], np.float64).ravel()
    pos = getattr(spec, "pos", None)
    if pos is not None:
        pa = np.asarray(pos, np.float64)
        if pa.ndim == 2 and pa.shape[0] > 0:
            return int(spec.origin), pa[:, 0].copy()
    b = np.asarray(spec.box, np.float64)
    return int(spec.origin), 0.5 * (b[:, 0] + b[:, 2])


def gap_xs(now: int, offset: int, spec) -> list | None:
    """Her x at frames now + 1 .. now + offset - 1 (between the forecast origin and a route starting offset frames later)
    from a prelude spec (prelude_xs; or a list of specs: alternatives): one array per alternative, nan where the spec
    does not cover a frame. None when the route has no such frames or nothing is known (the whole gap unknown)."""
    if offset <= 1 or spec is None:
        return None
    specs = spec if isinstance(spec, list) else [spec]
    frames = now + 1 + np.arange(offset - 1)
    out = []
    for s in specs:
        first, xs = prelude_xs(s)
        a = np.full(offset - 1, np.nan)
        k = frames - first
        ok = (k >= 0) & (k < len(xs))
        a[ok] = xs[k[ok]]
        out.append(a)
    return out or None


@numba.njit(cache=True)
def _hits(x0, hist, has_hist, hx, cx, cy, n, off, pre, lag, d_fwd, step, reach, hb_x, hb_lo, hb_hi, y_lo, y_hi):
    """hx [P, W]: her x per route frame (the walk's reference); cx, cy [P, W]: her Bounds centre per route frame; n [P]:
    the frames each route checks (<= W); off [P]: its first frame - now; hist [lag + 1]: her x at frames now - lag ..
    now (has_hist False: none known); pre [P, >= max(off) - 1]: her x at frames now + 1 .. now + off - 1, before the
    route's first frame (the same candidate's earlier part). A nan x is unknown (Sol seq 359: a missing x is never filled
    from the route's own points): a step whose window holds one moves both ends out, as if she were far. Returns hits
    [P, W] and the root interval lo, hi [P, W] (nan past a route's frames)."""
    P, W = hx.shape
    hits = np.zeros((P, W), np.bool_)
    LO = np.full((P, W), np.nan)
    HI = np.full((P, W), np.nan)
    omax = 0
    for p in range(P):
        if off[p] > omax:
            omax = off[p]
    seq = np.empty(lag + 1 + omax + W)      # seq[c]: her x at frame now + c - lag
    for p in range(P):
        m = n[p]
        o = off[p]
        if m <= 0:
            continue
        for c in range(lag + 1):
            seq[c] = hist[c] if has_hist else np.nan
        for i in range(1, o + m):
            j = i - o
            seq[lag + i] = pre[p, i - 1] if j < 0 else hx[p, j]
        lo = x0
        hi = x0
        for i in range(o + m):
            if i > 0:
                # the step from frame now + i - 1 to now + i reads her x at frames now + i - 1 - lag .. now + i - 1
                unknown = False
                wmax = -np.inf
                wmin = np.inf
                for c in range(i - 1, i + lag):
                    v = seq[c]
                    if v != v:
                        unknown = True
                    else:
                        if v > wmax:
                            wmax = v
                        if v < wmin:
                            wmin = v
                if unknown or not (wmin > hi and wmax <= hi + d_fwd - step):
                    hi = hi + step
                if unknown or not (wmax < lo and wmin >= lo - d_fwd + step):
                    lo = lo - step
            j = i - o
            if j < 0:
                continue
            LO[p, j] = lo
            HI[p, j] = hi
            xa = cx[p, j]
            ya = cy[p, j]
            xb = cx[p, j - 1] if j > 0 else xa
            yb = cy[p, j - 1] if j > 0 else ya
            if (min(xa, xb) - hb_x <= hi + reach and max(xa, xb) + hb_x >= lo - reach
                    and min(ya, yb) + hb_lo <= y_hi and max(ya, yb) + hb_hi >= y_lo):
                hits[p, j] = True
    return hits, LO, HI


def route_hits(x0: float, history: np.ndarray, paths, spans, width: int, box=None, preludes=None):
    """Body contacts of a walker with root x0 now on each route: hits [len(paths), width] (column k = the route's
    frame k, False past its span) and the root interval lo, hi [len(paths), width]. spans[i] = (offset, length): the
    route's first frame minus the forecast origin (>= 0) and its last checked frame index; history: hero_history();
    box: the routes' boxes stacked [len(paths), >= width, 4] when the caller has them (B2Geometry.scan_batch).
    Her x for the walk is the route's pos where it has one, else its box centre; her HeroBox comes from its box.
    preludes[i] (Sol seq 359): her x at frames now + 1 .. now + offset - 1, before route i (gap_xs: a list of arrays,
    alternatives, nan where unknown; None: all unknown). A route with alternatives is checked once per alternative:
    its contacts are their union, its interval the hull of theirs."""
    P = len(paths)
    W = int(width)
    alts = [None if preludes is None or preludes[g] is None else list(preludes[g]) for g in range(P)]
    if any(a is not None and len(a) > 1 for a in alts):
        src = np.array([g for g in range(P) for _ in (alts[g] or [None])], np.int64)
        rows = [a for g in range(P) for a in (alts[g] or [None])]
        h, lo, hi = route_hits(x0, history, [paths[g] for g in src], [spans[g] for g in src], W,
                               box=None if box is None else np.asarray(box)[src], preludes=[None if a is None else [a] for a in rows])
        hits = np.zeros((P, W), np.bool_)
        LO = np.full((P, W), np.nan)
        HI = np.full((P, W), np.nan)
        for q, g in enumerate(src):
            hits[g] |= h[q]
            LO[g] = np.fmin(LO[g], lo[q])
            HI[g] = np.fmax(HI[g], hi[q])
        return hits, LO, HI
    n = np.zeros(P, np.int64)
    off = np.zeros(P, np.int64)
    if box is not None:
        b = np.asarray(box, np.float64)[:, :W]
        cx = np.ascontiguousarray(0.5 * (b[..., 0] + b[..., 2]))
        cy = np.ascontiguousarray(0.5 * (b[..., 1] + b[..., 3]))
    else:
        cx = np.zeros((P, W))
        cy = np.zeros((P, W))
    hx = cx.copy()
    for g, (path, (o, length)) in enumerate(zip(paths, spans)):
        L = min(int(length) + 1, W, len(path.box))
        if L <= 0:
            continue
        if box is None:
            b = np.asarray(path.box, np.float64)[:L]
            cx[g, :L] = 0.5 * (b[:, 0] + b[:, 2])
            cy[g, :L] = 0.5 * (b[:, 1] + b[:, 3])
            hx[g, :L] = cx[g, :L]
        pos = getattr(path, "pos", None)
        if pos is not None:
            pa = np.asarray(pos)
            if pa.ndim == 2 and pa.shape[0] >= L:
                hx[g, :L] = pa[:L, 0]
        n[g] = L
        off[g] = int(o)
    hist = np.asarray(history, np.float64)
    has_hist = hist.size == HIST_N
    if not has_hist:
        hist = np.zeros(HIST_N)
    pre = np.full((P, max(int(off.max(initial=0)) - 1, 1)), np.nan)
    for g in range(P):
        a = alts[g]
        if a and off[g] > 1:
            v = np.asarray(a[0], np.float64).ravel()[:off[g] - 1]
            pre[g, :len(v)] = v
    return _hits(float(x0), hist, has_hist, hx, cx, cy, n, off, pre, LAG_F, D_FWD, V_WALK * FT, TURN_U + MARGIN_U,
                 HB_HX, HB_DY - HB_HY, HB_DY + HB_HY, FLOOR_Y - MARGIN_U, FLOOR_Y + BODY_TOP_U + MARGIN_U)


def warm() -> dict:
    """Load (or compile) the kernel before the fight (ForumPlannerPolicy.warmup's B2 part): one route alone and two
    with a box array, as B2Geometry calls it. {"enabled", "ms"}; with the switch off nothing runs."""
    import time
    from types import SimpleNamespace as NS
    t0 = time.perf_counter()
    if ENABLED:
        xs = np.linspace(30.0, 27.0, 13)
        box = np.stack([xs - 0.25, np.full(13, 3.0), xs + 0.25, np.full(13, 5.1)], 1)
        p = NS(box=box, pos=np.stack([xs, np.full(13, 4.6)], 1))
        route_hits(24.5, np.full(HIST_N, 30.0), [p], [(0, 12)], 13)
        route_hits(24.5, np.zeros(0), [p, p], [(0, 12), (1, 11)], 13, box=np.stack([box, box]))
    return {"enabled": bool(ENABLED), "ms": round((time.perf_counter() - t0) * 1e3, 3)}


__all__ = ["ENABLED", "CLAPPER", "D_FWD", "V_WALK", "LAG_F", "V_IDLE_MAX", "TURN_U", "BODY_TOP_U", "MARGIN_U",
           "walker_x", "hero_history", "prelude_xs", "gap_xs", "route_hits", "warm"]
