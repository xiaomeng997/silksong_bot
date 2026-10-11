"""Attack-range estimate (ARE, Task "attack range", the person 2026-10-10; docs/plans/forum_planner_plan.md sec. 5):
where an enemy's attack can really deal damage, per family and time since its antic start, with NO margin. Margins
are a later, decision-time choice (from the estimation error or from the bot's attack goal), not part of this.
One enemy at a time; the first is the Choristor (Song Pilgrim 03).

Model, per family F, branch B and time bin b (game frames since the antic start: the first frame the tracker sees
the family's start state), built from R0 dev only (tools.attack_range_build build):
  shape[F, B][b]  the union, over the clean R0 dev instances (not hit, no nail clash), of every real damage collider
                  of the enemy at bin b (attack + Body Damager + the multi-hit Whip Hit exported with dealt 0, the
                  rule of tools.zone_overlay.hurts), RELATIVE to the enemy's own position at that frame, in the
                  facing frame of the antic start (u forward, v up); a CELL u raster, cropped per bin. An instance that
                  has ended (left the family's states) contributes its idle body at its end position.
  disp[F, B][b]   the enemy's displacement from the anchor at bin b (u, v): the median over the instances. CH_JUMP:
                  u = ratio[b] x L, the landing predicted from the hero's offset at the antic start (L = alpha du +
                  beta, clamped to +-L_MAX). After the last bin: the last value (the idle body stays there).
  walls           the enemy's x stays inside the recorded extremes (the arena walls stop the lunges).
  branches        CH_SLASH combo / single (decided at Combo?), CH_HOP back / forward / up (Hop Check), CH_WHIP multi /
                  plain: a branch is known once its first state is seen; before that the estimate is the union of the
                  branches' estimates (the classifier's decision points).
  idle            Battle Idle and every state outside the families: the exact current body (its Body Damager now)
                  moved by its velocity now x the look-ahead (k / 60 s of game time; IDLE_CARRY, the person
                  2026-10-10: the walks, flights and chases between attacks), kept inside the arena (carry_shift);
                  no growth, and no attack that has not started (group 2 is not part of this round). No margin:
                  a margin (e.g. 0.5 u) is a decision-time choice (tools.are_idlevel measures it per k).

Every type is a module under ssbot.combat.are_types (the registry; SPECS / CHORISTOR below come from it) declaring an
are_spec.EnemySpec; beyond the Choristor's parts a type can declare (Task "attack range: all types", stage A):
  decide          a family's aim decided inside it (Decision: its states and rule -> facing s and u extent L): the
                  template's bins from the decision are aligned to it (frames since the decision) and anchored at the
                  decision frame (u = ratio x L); before the decision the estimate stops at the bin before it (a pending
                  aim, group 2, is not drawn). The Clapper's jumps: decided at Jump Aim, L = 0.916 vx.
  hazards         objects the enemy spawns that outlive the family (HazardSpec: a row of circles or one circle at the
                  trigger state's entry, hurting in the measured window per ring): drawn on their rule path at the
                  game time asked, while idle too; a `pre` hazard is predicted from the family start with the trigger's
                  measured time window until the trigger is seen. The Clapper's rune bombs (Cast 2) and rune slam.

The estimate at (enemy, k) is shape[b + k] placed at the enemy's predicted position for bin b + k (anchor + disp,
mirrored by the facing, x clamped by the walls), plus its hazards at t + k. Hero-centre space (where the hero
TRANSFORM must not be): the raw
region dilated by the hero hurtbox (HeroBox 0.4554 x 2.2498 u at (0, -0.38) from the hero transform). Nothing else.

Rasters live on one world lattice: cell ix covers x in [ix CELL, (ix + 1) CELL), row 0 of a mask is its lowest row.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ssbot.combat.are_spec import PARKED, CustomView, Decision, EnemySpec, HazardSpec  # noqa: F401 (re-exported)

REPO = Path(__file__).resolve().parents[3]
FORUM = REPO / "knowledge" / "1.0.30000" / "enemies" / "forum"
FT = 1.0 / 60.0
CELL = 0.05
HERO_HALF = (0.2277, 1.1249)          # HeroBox 0.4554 x 2.2498 u (the hurtbox) ...
HERO_DY = -0.38                       # ... centred 0.38 u below the hero transform
MW_SRC_BIT = 8                        # ipc.ents SRC_BITS["multi_wounder"]




def hurts(dealt: int, eff: int, src: int) -> bool:
    """tools.zone_overlay.hurts on the exported fields: dealt > 0, or a multi-hit collider exported with dealt 0."""
    return dealt > 0 or (not dealt and eff != 0 and bool(int(src or 0) & MW_SRC_BIT))


# ------------------------------------------------------------------------------------------------ rasters

@dataclass
class Mask:
    """A world raster on the lattice: m [ny, nx] bool, m[0, 0] is cell (ix0, iy0) (row 0 = lowest y)."""
    m: np.ndarray
    ix0: int
    iy0: int

    def area(self, cell: float = CELL) -> float:
        return float(self.m.sum()) * cell * cell

    def bbox(self, cell: float = CELL):
        """(x0, y0, x1, y1) in world u of the set cells, or None."""
        rr, cc = np.nonzero(self.m)
        if not len(rr):
            return None
        return ((self.ix0 + cc.min()) * cell, (self.iy0 + rr.min()) * cell, (self.ix0 + cc.max() + 1) * cell,
                (self.iy0 + rr.max() + 1) * cell)


def empty_mask() -> Mask:
    return Mask(np.zeros((0, 0), bool), 0, 0)


def poly_mask(polys, cell: float = CELL, pad: int = 1) -> Mask:
    """The lattice cells whose centres lie inside any of the polygons (world u; cv2's fill, 1/16 cell precision:
    cells within half a cell of an edge are included, so a raster is at most one cell (0.05 u) larger per side; the
    estimate and the real colliders are rasterized the same way)."""
    import cv2
    polys = [np.asarray(p, np.float64).reshape(-1, 2) for p in polys if p is not None and len(p) >= 3]
    if not polys:
        return empty_mask()
    allp = np.vstack(polys)
    ix0 = int(math.floor(allp[:, 0].min() / cell)) - pad
    iy0 = int(math.floor(allp[:, 1].min() / cell)) - pad
    nx = int(math.floor(allp[:, 0].max() / cell)) + pad - ix0 + 1
    ny = int(math.floor(allp[:, 1].max() / cell)) + pad - iy0 + 1
    img = np.zeros((ny, nx), np.uint8)
    pts = [np.round(((p / cell) - (ix0 + 0.5, iy0 + 0.5)) * 16.0).astype(np.int32) for p in polys]
    cv2.fillPoly(img, pts, 1, lineType=cv2.LINE_8, shift=4)
    return Mask(img.astype(bool), ix0, iy0)


def union(masks) -> Mask:
    masks = [m for m in masks if m is not None and m.m.size and m.m.any()]
    if not masks:
        return empty_mask()
    if len(masks) == 1:
        return masks[0]
    ix0 = min(m.ix0 for m in masks)
    iy0 = min(m.iy0 for m in masks)
    ix1 = max(m.ix0 + m.m.shape[1] for m in masks)
    iy1 = max(m.iy0 + m.m.shape[0] for m in masks)
    out = np.zeros((iy1 - iy0, ix1 - ix0), bool)
    for m in masks:
        out[m.iy0 - iy0:m.iy0 - iy0 + m.m.shape[0], m.ix0 - ix0:m.ix0 - ix0 + m.m.shape[1]] |= m.m
    return Mask(out, ix0, iy0)


def same_mask(a: Mask, b: Mask) -> bool:
    """The same set cells (whatever the raster's padding)."""
    ra, rb = a.m.any(axis=1), b.m.any(axis=1)
    if not ra.any() or not rb.any():
        return not ra.any() and not rb.any()
    ca, cb = a.m.any(axis=0), b.m.any(axis=0)
    ya, yb, xa, xb = int(ra.argmax()), int(rb.argmax()), int(ca.argmax()), int(cb.argmax())
    ha, hb = len(ra) - int(ra[::-1].argmax()), len(rb) - int(rb[::-1].argmax())
    wa, wb = len(ca) - int(ca[::-1].argmax()), len(cb) - int(cb[::-1].argmax())
    if (a.iy0 + ya, a.ix0 + xa, ha - ya, wa - xa) != (b.iy0 + yb, b.ix0 + xb, hb - yb, wb - xb):
        return False
    return bool(np.array_equal(a.m[ya:ha, xa:wa], b.m[yb:hb, xb:wb]))


def on_canvas(m: Mask, ix0: int, iy0: int, shape) -> np.ndarray:
    """m on the canvas whose cell (0, 0) is (ix0, iy0) (cut where it leaves it)."""
    out = np.zeros(shape, bool)
    if not m.m.size:
        return out
    ny, nx = shape
    r0, c0 = m.iy0 - iy0, m.ix0 - ix0
    a0, b0 = max(r0, 0), max(c0, 0)
    a1, b1 = min(r0 + m.m.shape[0], ny), min(c0 + m.m.shape[1], nx)
    if a1 > a0 and b1 > b0:
        out[a0:a1, b0:b1] = m.m[a0 - r0:a1 - r0, b0 - c0:b1 - c0]
    return out


def hero_kernel(cell: float = CELL) -> tuple[np.ndarray, tuple[int, int]]:
    """(kernel, anchor) of cv2.dilate taking a raw damage raster (row 0 lowest) to hero-centre space: hero cell p is
    set when an occupied cell q (a CELL square) meets the hurtbox at p: |q_x - p_x| <= hx + c/2 and
    q_y - p_y in [HERO_DY - hy - c/2, HERO_DY + hy + c/2]."""
    hx, hy = HERO_HALF
    ni = int(math.floor((hx + cell / 2) / cell + 1e-9))
    lo = int(math.ceil((HERO_DY - hy - cell / 2) / cell - 1e-9))
    hi = int(math.floor((HERO_DY + hy + cell / 2) / cell + 1e-9))
    return np.ones((hi - lo + 1, 2 * ni + 1), np.uint8), (ni, -lo)


def hero_space(m: Mask, cell: float = CELL) -> Mask:
    """The hero-centre region of a raw damage raster (the only growth of the estimate)."""
    import cv2
    if not m.m.size or not m.m.any():
        return empty_mask()
    k, (ax, ay) = hero_kernel(cell)
    ph, pw = k.shape[0], k.shape[1]
    img = np.zeros((m.m.shape[0] + 2 * ph, m.m.shape[1] + 2 * pw), np.uint8)
    img[ph:ph + m.m.shape[0], pw:pw + m.m.shape[1]] = m.m
    d = cv2.dilate(img, k, anchor=(ax, ay), borderType=cv2.BORDER_CONSTANT, borderValue=0)
    return Mask(d.astype(bool), m.ix0 - pw, m.iy0 - ph)


def contours(m: Mask, cell: float = CELL) -> list[np.ndarray]:
    """Outer outlines of a mask as world polygons (cell corners)."""
    import cv2
    if not m.m.size or not m.m.any():
        return []
    img = np.zeros((m.m.shape[0] + 2, m.m.shape[1] + 2), np.uint8)
    img[1:-1, 1:-1] = m.m
    up = cv2.resize(img, (img.shape[1] * 2, img.shape[0] * 2), interpolation=cv2.INTER_NEAREST)
    cs, _ = cv2.findContours(up, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cs:
        p = c.reshape(-1, 2).astype(np.float64)
        # doubled raster: pixel edge 2i is the cell edge i; contour pixels lie inside, so push out half a pixel
        x = (m.ix0 - 1 + (p[:, 0] + 0.5) / 2.0) * cell
        y = (m.iy0 - 1 + (p[:, 1] + 0.5) / 2.0) * cell
        out.append(np.stack([x, y], axis=1))
    return out


# ------------------------------------------------------------------------------------------------ the table

@dataclass
class Template:
    """One family / branch: per bin the cropped shape raster (template lattice: cell iu covers u in
    [iu CELL, (iu + 1) CELL)), its crop origin and the median displacement; JUMP: the u ratio of the landing."""
    nb: int
    shape: list            # [nb] of np.ndarray [nv, nu] bool (row 0 = lowest v)
    origin: np.ndarray     # [nb, 2] int (iu0, iv0)
    disp: np.ndarray       # [nb, 2] float (u, v)
    ratio: np.ndarray | None = None   # [nb] (aim families; decided families: the bins from b_dec)
    n: int = 0
    b_dec: int | None = None          # decided families: the bin of the decision (bins from it are aligned to it:
    #                                   b_dec + frames since the decision; disp v and ratio from the decision frame)
    sst: list | None = None           # state-gated types: per bin {state: (shape, iu0, iv0)} (the union per state)
    order: dict | None = None         # ... and each state's rank in the family (its median first bin; "<end>" last)


@dataclass
class RangeTable:
    spec: EnemySpec
    templates: dict                 # (family, branch) -> Template
    meta: dict = field(default_factory=dict)
    cell: float = CELL

    @property
    def walls(self) -> tuple[float, float]:
        w = self.meta.get("walls") or (-1e9, 1e9)
        return float(w[0]), float(w[1])

    def facing(self, flip) -> int:
        """+1 / -1: the facing of an entity whose flipX is `flip` (measured from the attack colliders)."""
        f1 = int(self.meta.get("face_flip1", 1))
        return f1 if flip else -f1

    def branch_by_rule(self, fam: str, hero_du: float) -> str | None:
        """A pending branch already certain from the hero's offset at the antic start (meta branch_rule, the R0 dev
        extremes: CH_HOP goes forward only when the hero is farther than Hop Distance, so below the nearest forward
        hop it is back, beyond the farthest back hop it is forward); None: still open (the union)."""
        r = (self.meta.get("branch_rule") or {}).get(fam)
        if not r:
            return None
        if hero_du < r["lo"]:
            return r["below"]
        if hero_du > r["hi"]:
            return r["above"]
        return None

    def landing(self, hero_du: float) -> float:
        a, b = self.meta.get("jump_fit", (1.0, 0.0))
        lm = float(self.meta.get("jump_lmax", 15.0))
        return float(min(max(a * hero_du + b, -lm), lm))

    def place(self, fam: str, branch: str | None, b: int, anchor: tuple, s: int, hero_du: float = 0.0,
              now: tuple | None = None, b_now: int | None = None, dec: dict | None = None,
              st_now: str | None = None, vel: tuple | None = None, ctx: dict | None = None) -> Mask:
        """The raw estimate of bin b of an instance anchored at anchor = (x, y) with facing s: the union over the
        family's branches when branch is None. With now = the enemy's observed position at bin b_now, the position is
        re-anchored there: now + (the template's displacement at b - at b_now), so only the displacement still to
        come is predicted (what has happened is observed). dec: the instance's decision (Inst.dec) once seen; a
        decided family without it stops at the last bin before its decision (the pending aim is not drawn).
        st_now: the state it is in now (state-gated templates: re-anchored at the observed state too). ctx: what a
        type's own placement (EnemySpec.place_fn) reads (the game time, the hero now, the instance, the velocity)."""
        if self.spec.place_fn is not None and ctx is not None:
            m = self.spec.place_fn(self, fam, branch, b, anchor, s, hero_du, now, b_now, dec, st_now, ctx)
            if m is not None:
                return m
        brs = self.spec.branches.get(fam, ("main",))
        if branch is None:
            branch = self.branch_by_rule(fam, hero_du)
        if branch is not None and (fam, branch) in self.templates:
            brs = (branch,)
        return union([self._place1(self.templates[(fam, br)], b, anchor, s, hero_du, fam, now, b_now, dec, st_now,
                                   vel) for br in brs if (fam, br) in self.templates])

    def _shape(self, tp: Template, bb: int, k0: bool, st_now: str | None) -> tuple:
        """(shape, iu0, iv0) of bin bb: the union over the instances; state-gated (tp.sst): at k = 0 the union over
        the instances in the state it is in now (the nearest bin within 8 that has it), at k > 0 over the states at or
        after it (what it has left cannot come back); the whole union when that leaves nothing."""
        full = (tp.shape[bb], int(tp.origin[bb, 0]), int(tp.origin[bb, 1]))
        if tp.sst is None or st_now is None:
            return full

        def nearest():
            for d in range(9):
                for q in ((bb,) if d == 0 else (bb - d, bb + d)):
                    if 0 <= q < tp.nb and st_now in tp.sst[q]:
                        return tp.sst[q][st_now]
            return full
        if k0:
            return nearest()
        o = (tp.order or {}).get(st_now)
        if o is None:
            return full
        parts = [v for k, v in tp.sst[bb].items() if (tp.order or {}).get(k, 1 << 30) >= o]
        if not parts:                           # it is ahead of every R0 dev instance: its state's nearest shape
            return nearest()
        if len(parts) == 1:
            return parts[0]
        iu0 = min(p[1] for p in parts)
        iv0 = min(p[2] for p in parts)
        nu = max(p[1] + p[0].shape[1] for p in parts) - iu0
        nv = max(p[2] + p[0].shape[0] for p in parts) - iv0
        out = np.zeros((nv, nu), bool)
        for sh, u0, v0 in parts:
            out[v0 - iv0:v0 - iv0 + sh.shape[0], u0 - iu0:u0 - iu0 + sh.shape[1]] |= sh
        return out, iu0, iv0

    def position(self, tp: Template, b: int, anchor: tuple, s: int, hero_du: float, fam: str) -> tuple:
        bb = min(max(b, 0), tp.nb - 1)
        du, dv = float(tp.disp[bb, 0]), float(tp.disp[bb, 1])
        if tp.ratio is not None and fam in self.spec.aim:
            du = float(tp.ratio[bb]) * self.landing(hero_du)
        lo, hi = self.walls
        return min(max(anchor[0] + s * du, lo), hi), anchor[1] + dv

    def position_dec(self, tp: Template, ba: int, dec: dict) -> tuple:
        """The position at aligned bin ba (>= b_dec) of a decided move: the decision frame + (ratio x L, v)."""
        bb = min(max(ba, 0), tp.nb - 1)
        du = float(tp.ratio[bb]) * float(dec["L"]) if tp.ratio is not None else float(tp.disp[bb, 0])
        lo, hi = self.walls
        return min(max(dec["x"] + dec["s"] * du, lo), hi), dec["y"] + float(tp.disp[bb, 1])

    def _place1(self, tp: Template, b: int, anchor: tuple, s: int, hero_du: float, fam: str,
                now: tuple | None = None, b_now: int | None = None, dec: dict | None = None,
                st_now: str | None = None, vel: tuple | None = None) -> Mask:
        k0 = b_now is not None and b <= b_now
        if tp.b_dec is not None:
            if dec is None:                     # pending aim: nothing of the undecided move is drawn
                b = min(b, tp.b_dec - 1)
                if b_now is not None:
                    b_now = min(b_now, tp.b_dec - 1)
            elif b >= dec["b"]:
                return self._place_dec(tp, b, dec, now, b_now, st_now)
        bb = min(max(b, 0), tp.nb - 1)
        sh, iu0, iv0 = self._shape(tp, bb, k0, st_now)
        if sh is None or not sh.size:
            return empty_mask()
        px, py = self.position(tp, b, anchor, s, hero_du, fam)
        if now is not None and b_now is not None:
            qx, qy = self.position(tp, b_now, anchor, s, hero_du, fam)
            lo, hi = self.walls
            px, py = min(max(now[0] + px - qx, lo), hi), now[1] + py - qy
            if vel is not None and b > b_now and st_now in self.spec.coast:     # stage B: coasting on its velocity
                px, py = coast(now, vel, b - b_now, self.spec.coast[st_now])
                px = min(max(px, lo), hi)
        return place_shape(sh, iu0, iv0, px, py, s, self.cell)

    def _place_dec(self, tp: Template, b: int, dec: dict, now: tuple | None, b_now: int | None,
                   st_now: str | None = None) -> Mask:
        """Bin b (since the antic start) of a decided move: aligned bin b_dec + (b - the decision's bin), anchored at
        the decision frame in its facing, re-anchored at the observed position like the rest."""
        ba = tp.b_dec + b - int(dec["b"])
        bb = min(max(ba, 0), tp.nb - 1)
        sh, iu0, iv0 = self._shape(tp, bb, b_now is not None and b <= b_now, st_now)
        if sh is None or not sh.size:
            return empty_mask()
        px, py = self.position_dec(tp, ba, dec)
        if now is not None and b_now is not None:
            qx, qy = self.position_dec(tp, tp.b_dec + max(b_now - int(dec["b"]), 0), dec)
            lo, hi = self.walls
            px, py = min(max(now[0] + px - qx, lo), hi), now[1] + py - qy
        return place_shape(sh, iu0, iv0, px, py, int(dec["s"]), self.cell)

    # -------------------------------------------------------------------------------------------- hazards

    def hazard_params(self, hz: HazardSpec) -> dict:
        """The measured parameters of a hazard (meta["hazards"][name], from R0 dev) over the spec's defaults:
        win [[on, off] per ring] frames after the trigger, dx / dv the centre offsets, x_ok the x intervals where it
        ever stood, trig {family: [lo, hi]} its trigger's bins after the family start."""
        return (self.meta.get("hazards") or {}).get(hz.name) or {}

    def hazard_mask(self, hz: HazardSpec, t_lo: float, t_hi: float, x: float, y: float, s: int, t: float) -> Mask:
        """The raw region of one hazard spawned by a trigger at a game time in [t_lo, t_hi] (equal once seen) from
        (x, y) facing s, at game time t: the circles whose measured hurt window contains t (a pending trigger time
        widens the window by its spread)."""
        P = self.hazard_params(hz)
        win = P.get("win") or []
        if not win:
            return empty_mask()
        polys = []
        if hz.shape == "row":
            dx = float(P.get("dx", 0.0))
            cy = y + float(P.get("dv", hz.dv))
            for m in range(-hz.m_max, hz.m_max + 1):
                ring = abs(m)
                if ring >= len(win) or win[ring] is None:
                    continue
                on, off = win[ring]
                if not (t_lo + on * FT - 1e-6 <= t <= t_hi + off * FT + 1e-6):
                    continue
                cx = x + hz.spacing * m + dx
                if not _inside(cx, P.get("x_ok")):
                    continue
                polys.append(circle_poly(cx, cy, hz.radius))
        else:
            on, off = win[0]
            if t_lo + on * FT - 1e-6 <= t <= t_hi + off * FT + 1e-6:
                polys.append(circle_poly(x + s * float(P.get("du", hz.du)), y + float(P.get("dv", hz.dv)), hz.radius))
        return poly_mask(polys, self.cell)


def coast(now: tuple, vel: tuple, n: int, decay: float, step: float = 0.02) -> tuple:
    """Stage B: the position n game frames ahead of an enemy coasting from now at velocity vel whose velocity decays
    by `decay` per 50 Hz physics step (0: it holds): now + vel x step x sum(decay^i, i = 1..m), m = n x 50 / 60."""
    m = n * FT / step
    if decay <= 0.0:
        return float(now[0]), float(now[1])
    k = step * (decay * (1.0 - decay ** m) / (1.0 - decay) if decay < 1.0 else m)
    return float(now[0]) + float(vel[0]) * k, float(now[1]) + float(vel[1]) * k


# The person 2026-10-10: an idle / moving non-attack body (walk, flight, chase) at +k is the body now carried by its
# velocity now for k / 60 s of game time (True, the default), not the body now (False: the comparison variant).
# The velocity is the entity's exported velocity of the frame (its Rigidbody2D velocity as observed, no smoothing). On
# the R0 fresh / R2 / person idle rows (tools.are_idlevel, forum.md §38) a position difference over the last 3 frames
# is worse at every k, and a constant acceleration (the velocity change over 3 frames) covers a few points more at
# m 0 up to k 12 but leaves a longer tail from k 18 on: not adopted.
IDLE_CARRY = True


def carry_shift(polys, vel, tau: float) -> tuple:
    """(dx, dy): a body (world polygons) carried by vel = (vx, vy) for tau s of game time, stopped by the arena: its
    box does not cross the side walls (core.forum WALL_L / WALL_R), the floor (FLOOR_Y) or the dome's lower edge
    (dome_y at both box edges); a box already past a bound is not pushed back, only not moved further out."""
    from ssbot.core.forum import FLOOR_Y, WALL_L, WALL_R, dome_y
    if vel is None or tau <= 0.0 or not polys:
        return 0.0, 0.0
    vx, vy = float(vel[0] or 0.0), float(vel[1] or 0.0)
    if not (math.isfinite(vx) and math.isfinite(vy)):
        return 0.0, 0.0
    dx, dy = vx * tau, vy * tau
    a = np.vstack([np.asarray(p, np.float64).reshape(-1, 2) for p in polys])
    x0, y0 = a.min(axis=0)
    x1, y1 = a.max(axis=0)
    if dx < 0.0:
        dx = max(dx, min(0.0, WALL_L - x0))
    elif dx > 0.0:
        dx = min(dx, max(0.0, WALL_R - x1))
    if dy < 0.0:
        dy = max(dy, min(0.0, FLOOR_Y - y0))
    elif dy > 0.0:
        top = min(dome_y(x0 + dx), dome_y(x1 + dx))
        dy = min(dy, max(0.0, top - y1))
    return dx, dy


def carry_body(polys, vel, tau: float, cell: float = CELL, on: bool | None = None) -> Mask:
    """The raw mask of a body carried by its velocity for tau s (carry_shift); on False (default: IDLE_CARRY) the body
    where it is now."""
    on = IDLE_CARRY if on is None else on
    dx, dy = carry_shift(polys, vel, tau) if on else (0.0, 0.0)
    return poly_mask([np.asarray(p, np.float64).reshape(-1, 2) + (dx, dy) for p in polys], cell)


def _inside(x: float, intervals) -> bool:
    if not intervals:
        return True
    return any(lo <= x <= hi for lo, hi in intervals)


def circle_poly(cx: float, cy: float, r: float, n: int = 64) -> np.ndarray:
    """A circle collider as a polygon whose edges lie outside the circle by at most 0.1 % of r (n 64)."""
    a = (np.arange(n) + 0.5) * (2.0 * math.pi / n)
    rr = r / math.cos(math.pi / n)
    return np.stack([cx + rr * np.cos(a), cy + rr * np.sin(a)], axis=1)


def place_shape(sh: np.ndarray, iu0: int, iv0: int, px: float, py: float, s: int, cell: float = CELL) -> Mask:
    """A template-lattice raster (cell iu centre (iu + 0.5) c) at world (px, py), facing s, on the world lattice."""
    iy0 = iv0 + int(math.floor(py / cell + 0.5))
    if s >= 0:
        return Mask(sh, iu0 + int(math.floor(px / cell + 0.5)), iy0)
    iu1 = iu0 + sh.shape[1] - 1
    return Mask(sh[:, ::-1], int(math.floor(px / cell - 0.5)) - iu1, iy0)


def table_path(spec: EnemySpec | None = None, root: Path = FORUM) -> Path:
    return root / f"{(spec or CHORISTOR).table}.npz"


def save_table(t: RangeTable, path: Path) -> Path:
    arrs: dict = {}
    keys = []
    for (fam, br), tp in sorted(t.templates.items()):
        key = f"{fam}|{br}"
        keys.append({"key": key, "nb": tp.nb, "n": tp.n, "aim": tp.ratio is not None,
                     **({"b_dec": int(tp.b_dec)} if tp.b_dec is not None else {})})
        sizes = np.array([[s.shape[0], s.shape[1]] for s in tp.shape], np.int32)
        bits = np.concatenate([np.packbits(s.reshape(-1)) if s.size else np.zeros(0, np.uint8) for s in tp.shape])
        arrs[f"{key}/sizes"] = sizes
        arrs[f"{key}/bits"] = bits
        arrs[f"{key}/origin"] = tp.origin.astype(np.int32)
        arrs[f"{key}/disp"] = tp.disp.astype(np.float32)
        if tp.ratio is not None:
            arrs[f"{key}/ratio"] = tp.ratio.astype(np.float32)
        if tp.sst is not None:
            sts = sorted(tp.order or {}, key=lambda q: (tp.order[q], q))
            rows, bl = [], []
            for b, d in enumerate(tp.sst):
                for st, (sh, u0, v0) in sorted(d.items()):
                    rows.append((b, sts.index(st), sh.shape[0], sh.shape[1], u0, v0))
                    bl.append(np.packbits(sh.reshape(-1)) if sh.size else np.zeros(0, np.uint8))
            arrs[f"{key}/sst_rows"] = np.array(rows, np.int32).reshape(-1, 6)
            arrs[f"{key}/sst_bits"] = np.concatenate(bl) if bl else np.zeros(0, np.uint8)
            keys[-1]["states"] = sts
            keys[-1]["order"] = [int(tp.order[q]) for q in sts]
    meta = dict(t.meta, keys=keys, cell=t.cell, type_key=t.spec.type_key)
    arrs["meta"] = np.frombuffer(json.dumps(meta).encode("utf-8"), np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **arrs)
    return path


def load_table(path: Path | None = None, spec: EnemySpec | None = None) -> RangeTable:
    spec = spec or CHORISTOR
    path = Path(path) if path is not None else table_path(spec)
    z = np.load(path)
    meta = json.loads(bytes(z["meta"]).decode("utf-8"))
    spec = SPECS.get(meta.get("type_key"), spec)
    tps = {}
    for k in meta["keys"]:
        key = k["key"]
        sizes = z[f"{key}/sizes"]
        bits = z[f"{key}/bits"]
        shapes, o = [], 0
        for ny, nx in sizes:
            n = int(ny) * int(nx)
            nbytes = (n + 7) // 8
            shapes.append(np.unpackbits(bits[o:o + nbytes])[:n].reshape(int(ny), int(nx)).astype(bool))
            o += nbytes
        ratio = z[f"{key}/ratio"] if f"{key}/ratio" in z.files else None
        sst = order = None
        if f"{key}/sst_rows" in z.files:
            sts = k["states"]
            order = {st: int(o) for st, o in zip(sts, k["order"])}
            sst = [dict() for _ in range(int(k["nb"]))]
            bits, o = z[f"{key}/sst_bits"], 0
            for b, si, ny, nx, u0, v0 in z[f"{key}/sst_rows"]:
                n = int(ny) * int(nx)
                nbytes = (n + 7) // 8
                sh = np.unpackbits(bits[o:o + nbytes])[:n].reshape(int(ny), int(nx)).astype(bool)
                o += nbytes
                sst[int(b)][sts[int(si)]] = (sh, int(u0), int(v0))
        fam, br = key.split("|")
        tps[(fam, br)] = Template(nb=int(k["nb"]), shape=shapes, origin=z[f"{key}/origin"], disp=z[f"{key}/disp"],
                                  ratio=ratio, n=int(k.get("n", 0)), b_dec=k.get("b_dec"), sst=sst, order=order)
    return RangeTable(spec=spec, templates=tps, meta=meta, cell=float(meta.get("cell", CELL)))


# ------------------------------------------------------------------------------------------------ segmentation

@dataclass
class Inst:
    """One family instance of one enemy: anchored at the first frame the tracker saw its start state."""
    fam: str
    t0: float
    x0: float
    y0: float
    s: int
    hero_du: float
    branch: str | None = None
    branch_t: float | None = None
    states: list = field(default_factory=list)
    dec: dict | None = None    # the decision (EnemySpec.decide): t, b (its bin), x, y, s, L
    st_t0: float = 0.0         # the game time the current state was first seen (back-dated by its time in state)
    trig: dict = field(default_factory=dict)        # hazard name -> its trigger (t, x, y, s) in this instance
    extra: dict = field(default_factory=dict)       # the type's own record (EnemySpec.on_step), with game times


class Segmenter:
    """The family instances of one enemy from its per-frame state (the same rule offline and live): an instance
    starts when a start state is entered from outside the family, or when the family's primary antic is entered
    again; it ends at the first state outside the family's states (then the enemy is idle)."""

    def __init__(self, spec: EnemySpec):
        self.spec = spec
        self.cur: Inst | None = None
        self.prev: str | None = None
        self.spawned: list = []    # every hazard trigger of this enemy: (HazardSpec, t, x, y, s)
        self.prev_tin = 0.0

    def step(self, st: str | None, T: float, x: float, y: float, s: int, hero_x: float | None,
             tin: float = 0.0, vx: float | None = None, hero_y: float | None = None) -> Inst | None:
        """One frame: st and tin (its time in state) of the enemy's first FSM, game time T. A new instance is
        anchored here, its time origin back-dated by tin (the state's entry, also when first seen late). A decision
        state (EnemySpec.decide) fixes the instance's decision at its first frame; a hazard's trigger state entered
        in one of its families spawns it (back-dated by tin)."""
        sp = self.spec
        cur = self.cur
        if cur is not None:
            fs = sp.fam_states[cur.fam]
            restart = st == sp.primary.get(cur.fam) and self.prev != st
            if st not in fs or restart:
                bd = sp.branch_dur.get(cur.fam) if sp.branch_dur else None
                if bd is not None and cur.branch is None and self.prev == bd[0]:
                    cur.branch, cur.branch_t = bd[2], T      # its timed state was left within the frames: short
                self.cur = cur = None
        if cur is None and st in sp.start and self.prev != st:
            fam = sp.start[st]
            du = 0.0 if hero_x is None else (hero_x - x) * s
            self.cur = cur = Inst(fam=fam, t0=T - max(float(tin or 0.0), 0.0), x0=x, y0=y, s=s, hero_du=du)
        if cur is not None:
            if not cur.states or cur.states[-1] != st:
                cur.states.append(st)
                cur.st_t0 = T - max(float(tin or 0.0), 0.0)
            br = sp.branch.get(cur.fam, {}).get(st)
            if callable(br):        # a branch picked by a rule at that state's first frame (stage B: the Reed's
                br = None if cur.branch is not None else br(x=x, y=y, s=s, vx=vx, hero_x=hero_x, hero_y=hero_y,
                                                            s0=cur.s)
            if cur.branch is None and br is not None:
                cur.branch, cur.branch_t = br, T
            bd = sp.branch_dur.get(cur.fam) if sp.branch_dur else None
            if bd is not None and cur.branch is None:
                state, frames, short, long_ = bd
                again = self.prev == state and float(tin or 0.0) < self.prev_tin - 1e-6
                if st == state and (again or T - cur.st_t0 > frames * FT + 1e-6):
                    cur.branch, cur.branch_t = long_, T
                elif st != state and self.prev == state and state in cur.states:
                    cur.branch, cur.branch_t = short, T
            d = sp.decide.get(cur.fam) if sp.decide else None
            if d is not None and cur.dec is None and st in d.states:
                res = d.rule(x, y, vx, hero_x, hero_y)
                sd, L = res[0], res[1]
                sd = sd or s            # stage B: s 0 = the observed facing at the decision frame
                td = T - max(float(tin or 0.0), 0.0)
                cur.dec = {"t": td, "b": bin_of(td - cur.t0), "x": x, "y": y, "s": int(sd), "L": float(L)}
                if len(res) > 2 and res[2]:     # stage B: the rule's extras (the Reed's pin aim) kept in dec
                    cur.dec.update(res[2])
                if d.branch is not None and cur.branch is None:
                    br_d = d.branch(x, int(sd), float(L))
                    if br_d is not None:
                        cur.branch, cur.branch_t = br_d, td
            for hz in sp.hazards:
                if st == hz.state and self.prev != st and cur.fam in hz.fams and hz.name not in cur.trig:
                    tt = T - max(float(tin or 0.0), 0.0)
                    cur.trig[hz.name] = (tt, x, y, s)
                    self.spawned.append((hz, tt, x, y, s))
            if sp.on_step is not None:
                sp.on_step(cur, st, self.prev, T, x, y, s, hero_x, hero_y, tin, vx)
        self.prev = st
        self.prev_tin = float(tin or 0.0)
        return cur


def bin_of(t: float) -> int:
    return int(math.floor(t / FT + 0.5))


# ------------------------------------------------------------------------------------------------ live tracking

def _first_state(e: dict) -> tuple[str | None, float]:
    for f in e.get("fsms") or ():
        return f.get("state"), float(f.get("t") or 0.0)
    return None, 0.0


def _parked(e: dict, parked: tuple = PARKED) -> bool:
    """Not in play: hidden, dead, off-stage or in a parked state (the type's EnemySpec.parked: the Tiny's "Ready" is
    its formation flight, not a wait)."""
    if e.get("hidden") or e.get("is_dead"):
        return True
    p = e.get("pos") or (0.0, 0.0, 0.0)
    if len(p) > 2 and abs(float(p[2])) > 5.0:      # the waiting later-wave members sit at z -15
        return True
    st, _ = _first_state(e)
    return st is None or any(w in str(st) for w in parked)


def body_polys(e: dict, name) -> list[np.ndarray]:
    names = (name,) if isinstance(name, str) else tuple(name)
    out = []
    for c in e.get("cols") or e.get("colliders") or ():
        v = c.get("verts_world")
        if c.get("name") in names and c.get("enabled") and v and len(v) >= 6:
            out.append(np.asarray(v, np.float64).reshape(-1, 2))
    return out


@dataclass
class Estimate:
    iid: int
    k: int
    raw: Mask
    fam: str | None            # None: idle (the body now)
    branch: str | None
    b: int | None              # the bin of the frame shown (b + k is placed)
    pos: tuple
    haz: Mask | None = None    # the part of raw from the enemy's hazards (types with hazards)


class RangeTracker:
    """Feeds on game-frame STATEs (as tools.zone_overlay ZoneEngine.feed gets them) and gives the attack-range
    estimate of every tracked enemy at look-ahead k."""

    def __init__(self, tables: dict | None = None):
        if tables is None:
            tables = {}
            for tk, sp in SPECS.items():
                p = table_path(sp)
                if p.exists():
                    tables[tk] = load_table(p, sp)
        self.tables = tables
        self.reset()

    def reset(self) -> None:
        self.T = 0.0
        self.segs: dict = {}
        self.now: dict = {}         # iid -> (type key, entity dict, inst or None)
        self.hero: tuple | None = None
        self.objs: dict = {}        # stage B: owner iid -> its projectiles in flight now (type_extra)
        self.obj_owner: dict = {}   # projectile iid -> (owner iid: the nearest enemy of the owning type, first sight T)
        self.ents: tuple = ()       # the frame's entities (EnemySpec.custom: other entities, projectiles)
        self.mem: dict = {}         # type key -> the custom hook's memory across frames
        self.paths: dict = {}       # the last ladder's whole-path hooks: iid -> (sure, maybe) (RangeTracker.path)

    def feed(self, s: dict) -> None:
        dt = s.get("dt")
        self.T += FT if dt is None else float(dt)
        h = (s.get("hero") or {}).get("pos")
        self.hero = (float(h[0]), float(h[1])) if h else None
        self.ents = tuple(s.get("ents") or ())
        now = {}
        for e in self.ents:
            tk = e.get("type_key")
            tab = self.tables.get(tk)
            if tab is None or _parked(e, tab.spec.parked):
                continue
            iid = int(e.get("iid") or -1)
            st, tin = _first_state(e)
            p = e.get("pos") or (0.0, 0.0)
            sgn = tab.facing(e.get("flipX"))
            seg = self.segs.get(iid)
            if seg is None:
                seg = self.segs[iid] = Segmenter(tab.spec)
            vel = e.get("vel")
            inst = seg.step(st, self.T, float(p[0]), float(p[1]), sgn, None if self.hero is None else self.hero[0],
                            tin, vx=None if not vel else float(vel[0]),
                            hero_y=None if self.hero is None else self.hero[1])
            now[iid] = (tk, e, inst)
        self.now = now
        for iid in [i for i in self.segs if i not in now]:
            del self.segs[iid]
        self._feed_objs(s.get("ents") or ())

    def _feed_objs(self, ents) -> None:
        """Stage B: the projectiles in flight of the types whose module lists them (OBJ_TYPES) and draws them
        (extra): {x, y, vx, vy, t, t0 (first seen), cx, cy (its collider's centre)} of each one whose damage collider
        is on, given to its owner."""
        kinds = {}
        for tk, tab in self.tables.items():
            mod = type_module(tab.spec)
            for ot in getattr(mod, "OBJ_TYPES", ()) if mod is not None else ():
                kinds[ot] = tk
        self.objs = {}
        if not kinds:
            return
        seen = set()
        for e in ents:
            tk = kinds.get(e.get("type_key"))
            if tk is None:
                continue
            oid = int(e.get("iid") or -1)
            seen.add(oid)
            if not any(c.get("enabled") and c.get("damage") for c in e.get("cols") or e.get("colliders") or ()):
                continue
            p = e.get("pos") or (0.0, 0.0)
            v = e.get("vel") or (0.0, 0.0)
            own, t0 = self.obj_owner.get(oid, (None, self.T))
            if own is None or own not in self.now:
                cand = [(math.hypot(float(p[0]) - float((x[1].get("pos") or (0, 0))[0]),
                                    float(p[1]) - float((x[1].get("pos") or (0, 0))[1])), i)
                        for i, x in self.now.items() if x[0] == tk]
                if not cand:
                    continue
                own = min(cand)[1]
                self.obj_owner[oid] = (own, t0)
            o = {"x": float(p[0]), "y": float(p[1]), "vx": float(v[0]), "vy": float(v[1]), "t": self.T, "t0": t0}
            vs = [q for c in e.get("cols") or e.get("colliders") or () if c.get("enabled") and c.get("damage")
                  for q in [c.get("verts_world")] if q and len(q) >= 6]
            if vs:                          # its collider's centre (the pin's turns to its flight)
                a = np.asarray(vs[0], np.float64).reshape(-1, 2)
                o["cx"] = 0.5 * float(a[:, 0].min() + a[:, 0].max())
                o["cy"] = 0.5 * float(a[:, 1].min() + a[:, 1].max())
            self.objs.setdefault(own, []).append(o)
        for oid in [o for o in self.obj_owner if o not in seen]:
            del self.obj_owner[oid]

    def estimate(self, iid: int, k: int) -> Estimate | None:
        if iid not in self.now:
            return None
        tk, e, inst = self.now[iid]
        tab = self.tables[tk]
        p = e.get("pos") or (0.0, 0.0)
        if inst is None:                # idle: the body now carried by its velocity now (IDLE_CARRY)
            vel = e.get("vel")
            v2 = (float(vel[0]), float(vel[1])) if vel and len(vel) > 1 else None
            est = Estimate(iid, k, carry_body(body_polys(e, tab.spec.body), v2, k * FT, tab.cell), None, None, None,
                           (float(p[0]), float(p[1])))
        else:
            b = bin_of(self.T - inst.t0)
            now = (float(p[0]), float(p[1]))
            vel = e.get("vel")
            v2 = (float(vel[0]), float(vel[1])) if vel and len(vel) > 1 else None
            m = tab.place(inst.fam, inst.branch, b + k, (inst.x0, inst.y0), inst.s, inst.hero_du, now=now, b_now=b,
                          dec=inst.dec, st_now=inst.states[-1] if inst.states else None, vel=v2,
                          ctx={"T": self.T, "hero": self.hero, "inst": inst, "vel": v2,
                               "body": body_polys(e, tab.spec.body)})
            est = Estimate(iid, k, m, inst.fam, inst.branch, b, now)
        if tab.spec.hazards:
            seg = self.segs.get(iid)
            hm = hazards_at(tab, seg.spawned if seg else (), inst, self.T, (float(p[0]), float(p[1])),
                            self.T + k * FT)
            est.haz = hm
            est.raw = union([est.raw, hm])
        ex = type_extra(tab.spec)
        if ex is not None:
            xm = ex(tab, inst, self.T, (float(p[0]), float(p[1])), self.T + k * FT, self.objs.get(iid, ()))
            if xm.m.size and xm.m.any():
                est.haz = xm if est.haz is None else union([est.haz, xm])
                est.raw = union([est.raw, xm])
        if tab.spec.custom is not None:
            apply_custom(est, tab.spec.custom(self._view(iid, k)))
        return est

    def _view(self, iid: int, k: int) -> CustomView:
        """What a type's own hooks (EnemySpec.custom, the module's path) see of a tracked enemy at look-ahead k."""
        tk, e, inst = self.now[iid]
        tab = self.tables[tk]
        p = e.get("pos") or (0.0, 0.0)
        st, tin = _first_state(e)
        vel = e.get("vel") or (None, None)
        return CustomView(tab=tab, inst=inst, k=k, T=self.T, t=self.T + k * FT, x=float(p[0]), y=float(p[1]),
                          vx=None if vel[0] is None else float(vel[0]),
                          vy=None if len(vel) < 2 or vel[1] is None else float(vel[1]),
                          s=tab.facing(e.get("flipX")), st=st, tin=tin, hero=self.hero, iid=iid,
                          body=body_polys(e, tab.spec.body), ents=self.ents, mem=self.mem.setdefault(tk, {}))

    def path(self, iid: int) -> tuple | None:
        """A type's whole-path hook (its module's `path(view) -> (sure Mask, maybe Mask) | None`): the rest of a move
        whose path is known beyond the swept window, drawn with it (the Tiny's dive from the Maestro's antic entry, 0.7
        s before it starts: the person 2026-10-10); maybe = what the hero can still change. None: no such move."""
        tab = self.tables.get(self.now[iid][0]) if iid in self.now else None
        if tab is None:
            return None
        mod = type_module(tab.spec)
        fn = getattr(mod, "path", None) if mod is not None else None
        return None if fn is None else fn(self._view(iid, 0))

    def estimates(self, k: int) -> list[Estimate]:
        return [x for x in (self.estimate(i, k) for i in sorted(self.now)) if x is not None]

    def swept(self, iid: int, k: int, step: int = 1) -> Mask:
        """The union of the estimate over the look-aheads 0..k (every `step` frames, k itself always): the whole path
        a lunge or a dive takes within k frames, out and back (the overlay's swept outline, the person 2026-10-10);
        empty for an enemy not tracked."""
        if iid not in self.now:
            return empty_mask()
        js = sorted(set(range(0, max(int(k), 0) + 1, max(int(step), 1))) | {max(int(k), 0)})
        return union([e.raw for e in (self.estimate(iid, j) for j in js) if e is not None])

    def ladder(self, ks, sweep: int | None = None, step: int = 1) -> tuple[dict, dict]:
        """Every look-ahead of one frame in one pass (the overlay's all-k and swept modes, the person 2026-10-10):
        ({k: [Estimate] in iid order} for each k in ks, {iid: the swept Mask over 0..sweep} ({} without sweep)).
        Each (enemy, look-ahead) is estimated once: the ks inside 0..sweep come from the sweep's own estimates. With a
        sweep, self.paths gets the type path hooks' (sure, maybe) per enemy (RangeTracker.path)."""
        ks = [max(int(k), 0) for k in ks]
        js = set(ks)
        sw = None if sweep is None else max(int(sweep), 0)
        if sw is not None:
            js |= set(range(0, sw + 1, max(int(step), 1))) | {sw}
        out: dict = {k: [] for k in ks}
        swept: dict = {}
        self.paths = {}             # iid -> (sure, maybe) of the type path hooks (with a sweep; RangeTracker.path)
        for iid in sorted(self.now):
            parts = []
            for j in sorted(js):
                e = self.estimate(iid, j)
                if e is None:
                    continue
                if j in out:
                    out[j].append(e)
                if sw is not None and j <= sw:
                    parts.append(e.raw)
            if sw is not None:
                swept[iid] = union(parts)
                pa = self.path(iid)
                if pa is not None:
                    self.paths[iid] = pa
        return out, swept


def apply_custom(est: Estimate, out) -> Estimate:
    """An EnemySpec.custom result (replace, add) applied to an estimate: replace takes the place of its template part
    (its hazards stay), add is unioned in and counted with the hazards."""
    rep, add = out if out is not None else (None, None)
    if rep is not None:
        est.raw = union([rep, est.haz]) if est.haz is not None else rep
    if add is not None and add.m.size and add.m.any():
        est.haz = add if est.haz is None else union([est.haz, add])
        est.raw = union([est.raw, add])
    return est


def hazards_at(tab: RangeTable, spawned, inst: Inst | None, T: float, pos: tuple, t: float,
               only: str | None = None) -> Mask:
    """The raw region at game time t of an enemy's hazards (only: of that hazard): those spawned (seen triggers; the
    Segmenter's `spawned`) and, while the current instance is in a family whose trigger is still to come
    (HazardSpec.pre), the predicted ones from its measured trigger window (bins after the antic start) at the enemy's
    position now."""
    ms = [tab.hazard_mask(hz, tt, tt, x, y, s, t) for hz, tt, x, y, s in spawned
          if tt <= T + 1e-9 and (only is None or hz.name == only)]
    if inst is not None:
        for hz in tab.spec.hazards:
            if (only is not None and hz.name != only) or not hz.pre or inst.fam not in hz.fams or hz.name in inst.trig:
                continue
            w = (tab.hazard_params(hz).get("trig") or {}).get(inst.fam)
            if not w:
                continue
            t_lo, t_hi = inst.t0 + w[0] * FT, inst.t0 + w[1] * FT
            if T <= t_hi + FT:
                ms.append(tab.hazard_mask(hz, max(t_lo, T), max(t_hi, T), pos[0], pos[1], inst.s, t))
    return union(ms)


# ------------------------------------------------------------------------------------------------ stage B hooks

def type_module(spec: EnemySpec):
    """The are_types module of a spec (for its optional stage B functions), or None."""
    from ssbot.combat.are_types import module_of
    try:
        return module_of(spec.type_key)
    except KeyError:
        return None


def type_extra(spec: EnemySpec):
    """A type module's own drawn part (stage B), or None: extra(tab, inst, T, pos, t, objs) -> Mask, the raw region at
    game time t of what neither the templates nor a HazardSpec model (the Reed's pin: its decided line before the
    release, its real path in flight). inst: the instance as seen at T (or None: idle), pos: the enemy now, objs: its
    projectiles in flight now ([{x, y, vx, vy, t}], the module's OBJ_TYPES; the tracker gives each to the nearest
    enemy of the owning type at its first sight, the builder by the module's attach)."""
    mod = type_module(spec)
    return getattr(mod, "extra", None) if mod is not None else None


def _registry() -> dict:
    from ssbot.combat.are_types import specs
    return specs()


SPECS = _registry()
CHORISTOR = SPECS["Song Pilgrim 03"]
