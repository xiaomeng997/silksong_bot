"""Map v2 stage T2: THE STRIKE WINDOWS AS SHAPES (docs/plans/forum_map_v2.md, 'THE STRIKE WINDOWS ARE SHAPES, NOT GRID
CELLS'; the lead's note NOTE_FROM_LEAD_windows: the goal regions of the backward tables). Offline / planning code.

A down slash window, per (the body's robust box per frame - a Clapper move's frames as the prediction gives them -,
the press frame) x her exact state at the press (her vertical trajectory after it: the table and its phase; the
facing she has - the polygons are mirrored by it): THE PRESS REGION, an x interval set of her transform at the press
from which the swing meets the body with both alternations (strike.dslash_contact's judge: each alternation's first
contact in press + 3 .. + 9, before she lands), her keys free in the swing (the instant run: the lanes' reach). The
boundaries are exact: for a convex polygon and a box, the x set of a hit at one height is the box widened by the
polygon's x extent inside the box's slab (an interval; strike / clapper.poly_box_hit's open overlap - the ends
themselves are misses), checked against the judge by bisection (tests); the contact frames chain by interval
arithmetic (alternation 1 at c1, alternation 2 at c2 >= c1 reachable from it in the run). Walls clip at use time.
"""
from __future__ import annotations

import numpy as np

from ssbot.map2 import strike as sk


def slab_extent(poly: np.ndarray, y0: float, y1: float):
    """The x extent of the convex polygon poly ([m, 2]) inside the slab y0 <= y <= y1, or None (no overlap)."""
    xs = []
    m = len(poly)
    for i in range(m):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % m]
        if y0 <= ay <= y1:
            xs.append(ax)
        for yc in (y0, y1):
            if (ay - yc) * (by - yc) < 0.0:
                xs.append(ax + (yc - ay) * (bx - ax) / (by - ay))
    if not xs:
        return None
    return min(xs), max(xs)


def hit_interval(poly: np.ndarray, box, ty: float):
    """Her transform x at height ty for which poly (relative to her transform) meets box (x0, y0, x1, y1): (lo, hi)
    open, or None."""
    if box is None or np.isnan(box[0]):
        return None
    e = slab_extent(poly, box[1] - ty, box[3] - ty)
    if e is None or not (box[1] - ty < poly[:, 1].max() and box[3] - ty > poly[:, 1].min()):
        return None
    lo, hi = box[0] - e[1], box[2] - e[0]
    return (lo, hi) if lo < hi else None


def ds_press_set(boxes: np.ndarray, k0: int, ty: np.ndarray, L: np.ndarray, R: np.ndarray, ground: np.ndarray,
                 face: int) -> list:
    """THE DOWN SLASH PRESS REGION: index 0 = the press frame's start (her transform x there is the unknown), index
    1 = the press frame; ty[c] her transform height at index c (her vertical after the press: the swing does not
    move her), L[c] / R[c] the run's reach from index 0 (all left / all right, the swing's own lock included),
    ground[c] she stands (the swing ends); boxes[k0 + c] the robust body box at index c (absolute frames). Returns the
    x intervals (closed hull of the open sets) at index 0 from which both alternations meet the box at frames in
    press + 3 .. press + 9 with her facing face."""
    pa, pb = sk.slash_polys(face)
    act = []
    for c in range(1 + sk.DS_ACTIVE[0], min(1 + sk.DS_ACTIVE[1], len(ty) - 1) + 1):
        if ground[c]:
            break
        k = k0 + c
        box = boxes[k] if 0 <= k < len(boxes) else None
        act.append((c, hit_interval(pa, box, ty[c]), hit_interval(pb, box, ty[c])))
    out = []
    for c1, a1, b1 in act:
        for c2, a2, b2 in act:
            if c2 < c1:
                continue
            for i1, i2 in ((a1, b2), (b1, a2)):
                if i1 is None or i2 is None:
                    continue
                if c1 == c2:
                    lo, hi = max(i1[0], i2[0]), min(i1[1], i2[1])
                else:
                    dl, dr = L[c2] - L[c1], R[c2] - R[c1]
                    lo, hi = max(i1[0], i2[0] - dr), min(i1[1], i2[1] - dl)
                if lo < hi:
                    out.append([lo - R[c1], hi - L[c1]])
    out.sort()
    res = []
    for lo, hi in out:
        if res and lo <= res[-1][1]:
            res[-1][1] = max(res[-1][1], hi)
        else:
            res.append([lo, hi])
    return res


def ds_judge(boxes, k0, x0, ty, xs_path, ground, face) -> bool:
    """The strike module's judge on one concrete path (her transform x per index): both alternations meet."""
    pos = np.stack([xs_path, ty], axis=1)
    return sk.dslash_contact(pos, np.full(len(ty), face), ground, 1, boxes[k0:k0 + len(ty)] if k0 >= 0 else boxes) >= 0
