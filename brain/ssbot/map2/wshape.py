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


# ---- T4: the shapes from a tables' pass (the search's windows; tools.t2_tables' shapes) ---------------------------

def abs_lane(lib, fw, g: int, ln: int, alpha: float) -> np.ndarray:
    """Cluster g's lane ln of a tables' pass (fw.node) as an absolute kin state (x 0, her height, the frame's phase,
    its air dash)."""
    from ssbot.knowledge import kinematics as km
    from ssbot.map2 import tables as tb
    nd = int(fw.node[g])
    x = lib.NL[nd, ln].copy()
    if lib.NINT[nd, tb.I_ABS] == 0:
        py = float(fw.cl_y[g] - lib.hh)
        for f in (km.PY, km.QY, km.SY, km.RY0):
            x[f] += py
    x[km.AIRDASHED] = float(fw.ad[g])
    x[km.ALPHA] = alpha
    return x


def swing_paths(lib, fw, gs, k0_alpha: float):
    """Per cluster g of a tables' pass (frame t): her transform height, the run's reach and the ground flag over a
    down slash pressed in frame t + 1 (index 0 = the cluster's frame), rolled by the reference model from the node's
    representative at her height and the frame's phase: (ty [n, 11], L, R, ground)."""
    from ssbot.knowledge import kinematics as km
    from ssbot.map2 import env_jit as ej
    from ssbot.map2 import tables as tb
    n = len(gs)
    S0 = np.zeros((3 * n, km.K))
    cu0 = np.zeros((3 * n, ej.NC))
    masks = np.zeros((3 * n, 10), np.int64)
    AD = km.B_ATTACK | km.B_DOWN
    for i, g in enumerate(gs):
        t = int(np.searchsorted(fw.cl_off, g, side="right") - 1)
        nd = int(fw.node[g])
        al = lib.steps(k0_alpha, t + 1)[t][1] if t > 0 else k0_alpha
        for j, h in enumerate((0, km.B_LEFT, km.B_RIGHT)):
            x = abs_lane(lib, fw, g, 0 if j == 1 else 1, al)       # (the left reach from the left lane: its MOVE
            S0[3 * i + j] = x                                       # acts in the press frame's steps)
            cu0[3 * i + j] = lib.NCU[nd]
            masks[3 * i + j, 0] = AD | h
            masks[3 * i + j, 1:] = h
    xy, md = ej.ref_many(S0, cu0, masks, lib.udt, lib.P, lib.TTg)
    ty = xy[0::3, :, 1] - lib.hh
    L = xy[1::3, :, 0] - xy[1::3, :1, 0]
    R = xy[2::3, :, 0] - xy[2::3, :1, 0]
    ground = xy[0::3, :, 1] <= tb.FLOOR_TOP + lib.params.foot + lib.hh + 1e-6
    return ty, L, R, ground


def cluster_windows(boxes: np.ndarray, k0: int, ivs: np.ndarray, ty, L, R, ground) -> list:
    """THE PRESS REGION of one cluster (its frame k0, its x intervals ivs) - both facings, inside the cluster:
    [(lo, hi)] (the facing F of the swing is a member that stepped toward F in the press frame's step or stood)."""
    shp = []
    for face in (-1, 1):
        Lf, Rf = L.copy(), R.copy()
        if face > 0:
            Lf[1:] -= L[1]
        else:
            Rf[1:] -= R[1]
        for lo, hi in ds_press_set(boxes, k0, ty, Lf, Rf, ground, face):
            for a, c in ivs:
                u, v = max(lo, a), min(hi, c)
                if u <= v:
                    shp.append((u, v))
    return shp
