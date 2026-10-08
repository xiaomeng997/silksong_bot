"""The Forum planner's terminal value (forum_planner_plan §4.1 / §4.2, round R5, the terminal-value half): what the
hero can still do after a candidate's horizon, from a coarse space-time field of every enemy's support. Scores only:
nothing here reaches a candidate's S, Hz or U (§4.4 items 2 and 5).

    fields = EnemyFields.build(mf_forecast, mf)          # once per tick (every owner; ~1 ms on wave 6, see forum.md)
    tv = TerminalValue(params)                           # the reachable templates, built once per process
    E, trapped, overlap, H = tv.rows(fields, end_xy, end_class, t_end_s)
    kv = fields.kill_value(hero_xy)                      # per enemy iid: the support only it covers near the hero

Field (EnemyFields): cells of GRID_DX x GRID_DY u over the arena (hero hurtbox centres: the support's templates hold the
hurtbox's dilation), time bins of FIELD_DT_S from FIELD_T0_S to the forecast's horizon. One bitmap per owner (an enemy
iid; a Tiny group row's cluster; a hazard; a wave's entries). A cell / bin is set when some placement's box may meet
a hurtbox centred anywhere in the cell at any time in the bin, so "field empty => every fine query in it empty"
(§4.4 item 5; tools/field_audit checks it on recordings):
  fine / window / bounding-box placements: the store's per-bin bounding boxes of the template's coarse base (a superset
    of the fine template) over every template bin an entry time of the placement gives inside the bin (the sparse
    tables' two lookups; time dilation by the bin and one template bin of slack each side);
  tubes and boxes (idle body, collider, hazard, death, arena): the box at both ends of the bin, grown by the growth at
    the bin's end (motion linear in time, growth monotone), dilated by the hero hurtbox;
  hazard paths: every centre a path may take in the bin (its slack copies and branches, 10 ms samples), grown by its
    radius / half extents, its tube growth, the contact skin and the hero hurtbox.
No rotation: every owner is rebuilt every tick (the plan's per-frame rotation was a cost measure; the box form costs
less than its one-enemy budget, forum.md §17), so the field is never stale.

Terminal terms of a row (TerminalValue.rows, at the nominal lane's last frame; the reachable templates R_t: hurtbox
centres the Forum kinematics reach REACH_S after a start of the row's end class, offline from a primitive library):
  E        sum_t w_t |R_t \\ U_t| / |R_t|, w_t = 1 / (1 + t) normalised (U: the union field at the end time + t);
  trapped  some t <= TRAP_S with R_t inside U_t (every way out closes);
  overlap  sum_t w_t |R_t and {C_t >= 2}| / |R_t| (C: how many owners cover the cell: the danger zones stack);
  H_exp    sum over t <= HEXP_S of w_t |R_t and F2_t| / |R_t| (F2: owners with a 2-mask attack or a multi-hit chain:
           the Q3 sources, §4.2 "h = 2 先回血、攒丝").
Kill value (fields.kill_value): per enemy, the share of the cells near the hero (NEAR_U box, every bin) only it covers
(the union shrinks by that when it dies: leave-one-out), divided by the nail hits it still needs (hp_est / one hit).
"""
import math
from dataclasses import dataclass

import numba
import numpy as np

from ssbot.core.forum import FLOOR_Y, WALL_L, WALL_R
from ssbot.knowledge import hitbox_tables as hb
from ssbot.knowledge import kinematics as kin

KIN_DIR = __import__("pathlib").Path(__file__).resolve().parents[3] / "knowledge" / "1.0.30000" / "kinematics"

GRID_X0, GRID_DX, GRID_NX = 14.0, 0.5, 70          # x 14.0 - 49.0
GRID_Y0, GRID_DY, GRID_NY = 3.5, 1.0, 15           # y 3.5 - 18.5 (a hurtbox centre on the floor: y 4.04)
FIELD_T0_S, FIELD_DT_S = 0.6, 0.1                  # bins [0.6, 0.7), ..., up to the forecast's horizon
REACH_S = (0.2, 0.5, 0.9, 1.4)                     # after the row's end (forum_planner_plan §4.2)
TRAP_S = 1.4
HEXP_S = 0.9                                       # the next ~1 s (design H §5.3)
NEAR_U = (8.0, 5.0)                                # kill value: cells within this of the hero (x, y)
PATH_DT_S = 0.01
TPL_SLACK = 1                                      # template bins of slack each side of a field bin
CLASSES = ("ground", "air_up", "air_mid", "air_down")
AIR_VY = 3.0                                       # |vy| above this: rising / falling
REACH_Q = (0.125, 0.25)                            # offsets quantised to this (x, y) before dedup (the file)
REACH_RUN_Q = (0.5, 1.0)                           # and to one cell at run time (the rows' cost: forum.md §17)
HERO_CY = FLOOR_Y + hb.HERO_HALF_U[1]              # a hurtbox centre standing on the floor
LIKELY_P = 0.5                                     # overlap: owners this likely in the cell
BODY_APPROACH_U_S = 1.5                            # body field: an enemy's zone grows this fast since its sighting
BODY_REACH_U = 1.5                                 # body field: from this far (a melee swing beyond the body)
CLEAR_U = 4.0                                      # body field: clearance beyond the reach saturates at this
VEL_CAP_S = 0.3                                    # body field: velocity dead reckoning for at most this long
REACH_FILE = "forum_reach.npz"                     # knowledge/<build>/kinematics: the reachable templates
LIKELY_V = int(round(LIKELY_P * 255))


@numba.njit(cache=True)
def _row_bins(rows, loff, nt, t0, e0, e1, cx, cy, hx, hy, mir, ta, tb, bin_s, slack):
    """[K, B] world boxes of bounding-box rows over field bins [ta[b], tb[b]]: the union of the template's per-bin
    boxes over every template bin an entry in [e0, e1] gives at some time in the bin (+-slack bins), mirrored (both
    when mir is 0), grown by the anchor box (hx, hy)."""
    K = loff.shape[0]
    B = ta.shape[0]
    jmax = loff.shape[1] - 1
    bx0 = np.zeros((K, B))
    by0 = np.zeros((K, B))
    bx1 = np.zeros((K, B))
    by1 = np.zeros((K, B))
    ok = np.zeros((K, B), np.bool_)
    for k in range(K):
        for t in range(B):
            b_lo = int(np.rint((ta[t] - e1[k] - t0[k]) / bin_s)) - slack
            b_hi = int(np.rint((tb[t] - e0[k] - t0[k]) / bin_s)) + slack
            if b_hi < 0 or b_lo >= nt[k]:
                continue
            if b_lo < 0:
                b_lo = 0
            if b_hi > nt[k] - 1:
                b_hi = nt[k] - 1
            x0, y0, x1, y1 = np.inf, np.inf, -np.inf, -np.inf
            b = b_lo
            while b <= b_hi:
                L = b_hi - b + 1
                j = 0
                while j < jmax and (1 << (j + 1)) <= L:
                    j += 1
                r = loff[k, j] + b
                x0 = min(x0, rows[r, 0])
                y0 = min(y0, rows[r, 1])
                x1 = max(x1, rows[r, 2])
                y1 = max(y1, rows[r, 3])
                if L <= (1 << (j + 1)):
                    r = loff[k, j] + b_hi - (1 << j) + 1
                    x0 = min(x0, rows[r, 0])
                    y0 = min(y0, rows[r, 1])
                    x1 = max(x1, rows[r, 2])
                    y1 = max(y1, rows[r, 3])
                    break
                b += 1 << j
            if x0 > x1:
                continue
            if mir[k] == 0:
                X0, X1 = min(x0, -x1), max(x1, -x0)
            elif mir[k] < 0:
                X0, X1 = -x1, -x0
            else:
                X0, X1 = x0, x1
            bx0[k, t] = cx[k] - hx[k] + X0
            bx1[k, t] = cx[k] + hx[k] + X1
            by0[k, t] = cy[k] - hy[k] + y0
            by1[k, t] = cy[k] + hy[k] + y1
            ok[k, t] = True
    return bx0, by0, bx1, by1, ok


@numba.njit(cache=True)
def _raster(bx0, by0, bx1, by1, ok, own, val, F, x0, dx, nx, y0, dy, ny):
    """F[owner, bin, iy, ix] = max(F, val[k]) where a box [K, B] meets the cell (closed: a box edge on a cell line
    sets both)."""
    K, B = bx0.shape
    for k in range(K):
        o = own[k]
        v = val[k]
        for t in range(B):
            if not ok[k, t]:
                continue
            fx0 = (bx0[k, t] - x0) / dx
            fx1 = (bx1[k, t] - x0) / dx
            fy0 = (by0[k, t] - y0) / dy
            fy1 = (by1[k, t] - y0) / dy
            if fx1 < 0.0 or fy1 < 0.0 or fx0 >= nx or fy0 >= ny:
                continue
            ix0 = max(int(math.floor(fx0)), 0)
            ix1 = min(int(math.floor(fx1)), nx - 1)
            iy0 = max(int(math.floor(fy0)), 0)
            iy1 = min(int(math.floor(fy1)), ny - 1)
            for iy in range(iy0, iy1 + 1):
                for ix in range(ix0, ix1 + 1):
                    if F[o, t, iy, ix] < v:
                        F[o, t, iy, ix] = v


@numba.njit(cache=True, parallel=True)
def _terminal_rows(ex, ey, ecls, jb, wt, trap_m, hexp_m, offs, n_off, Cl, Vf, Lk, P2, x0, dx, nx, y0, dy, ny,
                   xmin, xmax, ymin, E, trapped, overlap, hexp):
    """Per row: E / trapped / overlap / H_exp (module docstring) from the end centre (ex, ey) and class, the reachable
    offsets offs [class, m, k, 2] (n_off [class, m]) in field bins jb[m] (-1: past the field), weights wt[m]."""
    N = ex.shape[0]
    M = jb.shape[0]
    for c in numba.prange(N):
        seen = np.zeros(ny * nx, np.int32)
        cl = ecls[c]
        e = 0.0
        ov = 0.0
        he = 0.0
        wsum = 0.0
        hsum = 0.0
        tr = False
        for m in range(M):
            j = jb[m]
            if j < 0:
                continue
            n_r = 0
            n_open = 0
            free = 0.0
            n_ov = 0
            two = 0.0
            stamp = m + 1
            for k in range(n_off[cl, m]):
                px = ex[c] + offs[cl, m, k, 0]
                py = ey[c] + offs[cl, m, k, 1]
                if px < xmin:
                    px = xmin
                if px > xmax:
                    px = xmax
                if py < ymin:
                    py = ymin
                ix = int(math.floor((px - x0) / dx))
                iy = int(math.floor((py - y0) / dy))
                if ix < 0 or iy < 0 or ix >= nx or iy >= ny:
                    continue
                q = iy * nx + ix
                if seen[q] == stamp:
                    continue
                seen[q] = stamp
                n_r += 1
                if Cl[j, iy, ix] == 0:
                    n_open += 1
                free += Vf[j, iy, ix]
                if Lk[j, iy, ix] >= 2:
                    n_ov += 1
                two += P2[j, iy, ix]
            if n_r == 0:
                continue
            e += wt[m] * free / n_r
            ov += wt[m] * n_ov / n_r
            wsum += wt[m]
            if hexp_m[m]:
                he += wt[m] * two / n_r
                hsum += wt[m]
            if trap_m[m] and n_open == 0:
                tr = True
        E[c] = e / wsum if wsum > 0 else 1.0
        overlap[c] = ov / wsum if wsum > 0 else 0.0
        hexp[c] = he / hsum if hsum > 0 else 0.0
        trapped[c] = tr


@dataclass
class EnemyFields:
    """The tick's field (module docstring): F [owners, bins, NY, NX] uint8, each owner's largest path probability
    covering the cell in the bin (x 255; tubes, boxes and paths 255; 0: no support), the owners' keys (enemy iid,
    ("g", cluster), hazard iid, entry owner), Uc the committed union (MultiForecast.committed(): the current attacks,
    tails, death boxes, hazard paths), and derived from F: U the union (binary), Pu = 1 - prod(1 - p_i), Lk how many
    owners are likely there (p_i >= LIKELY_P), P2 the largest p_i of the 2-mask / multi-hit owners; ta the bins'
    start times (s from the origin), the build time and the live enemies' (hp_est, hp_sd)."""
    F: np.ndarray
    keys: list
    Uc: np.ndarray
    U: np.ndarray
    Pu: np.ndarray
    Lk: np.ndarray
    P2: np.ndarray
    ta: np.ndarray
    ms: float = 0.0
    hp: dict | None = None
    Cl: np.ndarray | None = None       # closed cells (the terminal terms' "trapped"): Uc, or the body zones' union
    Vf: np.ndarray | None = None       # free value in [0, 1]: (1 - Uc)(1 - Pu), or the body field's clearance

    def __post_init__(self):
        if self.Cl is None:
            self.Cl = self.Uc
        if self.Vf is None:
            self.Vf = ((1 - self.Uc.astype(np.float32)) * (1.0 - self.Pu)).astype(np.float32)

    @property
    def nbins(self) -> int:
        return len(self.ta)

    def bin_of(self, t: float) -> int:
        """The field bin holding origin time t (-1 before the first, clipped to the last: the forecast's horizon)."""
        if t < FIELD_T0_S - 1e-9 or not len(self.ta):
            return -1
        return min(int((t - FIELD_T0_S) / FIELD_DT_S + 1e-9), len(self.ta) - 1)

    def owner_field(self, key) -> np.ndarray | None:
        try:
            return self.F[self.keys.index(key)]
        except ValueError:
            return None

    def kill_value(self, hx: float, hy: float, hit_dmg: float, iids=None) -> dict:
        """iid -> leave-one-out drop of the union probability near the hero (mean over the NEAR_U box and every bin
        of Pu - Pu without it) / the nail hits it still needs (ceil(hp_est / hit_dmg), at least 1); iids: only these."""
        if not len(self.keys) or not self.hp or not self.nbins:
            return {}
        ix0 = max(int(math.floor((hx - NEAR_U[0] - GRID_X0) / GRID_DX)), 0)
        ix1 = min(int(math.floor((hx + NEAR_U[0] - GRID_X0) / GRID_DX)), GRID_NX - 1)
        iy0 = max(int(math.floor((hy - NEAR_U[1] - GRID_Y0) / GRID_DY)), 0)
        iy1 = min(int(math.floor((hy + NEAR_U[1] - GRID_Y0) / GRID_DY)), GRID_NY - 1)
        if ix1 < ix0 or iy1 < iy0:
            return {}
        q = 1.0 - self.F[:, :, iy0:iy1 + 1, ix0:ix1 + 1].astype(np.float32) / 255.0      # [owners, ...]
        pu = 1.0 - np.prod(q, axis=0)
        out = {}
        for i, k in enumerate(self.keys):
            if k not in self.hp or (iids is not None and k not in iids):
                continue
            others = np.prod(np.delete(q, i, axis=0), axis=0) if len(self.keys) > 1 else np.ones_like(pu)
            drop = float((pu - (1.0 - others)).mean())
            hp_est, _ = self.hp[k]
            need = max(1.0, math.ceil(max(hp_est, 0.0) / max(hit_dmg, 1e-6)))
            out[k] = max(drop, 0.0) / need
        return out

    @classmethod
    def build(cls, f, two_mask=None) -> "EnemyFields":
        """The field of a MultiForecast f (its placements, boxes and hazard paths), bins from FIELD_T0_S to
        f.horizon. two_mask(owner key) -> bool: the owner has a 2-mask attack or a multi-hit chain."""
        import time
        t0 = time.perf_counter()
        fc = f._fc
        store = fc.tables.store
        nb = max(int(math.floor((float(f.horizon) - FIELD_T0_S) / FIELD_DT_S + 1e-9)), 0)
        ta = FIELD_T0_S + FIELD_DT_S * np.arange(nb)
        tb = ta + FIELD_DT_S
        keys: list = []
        kidx: dict = {}

        def key_of(k):
            i = kidx.get(k)
            if i is None:
                i = kidx[k] = len(keys)
                keys.append(k)
            return i
        parts = []                    # (bx0, by0, bx1, by1, ok, own, val, committed) per placement kind
        if nb:
            parts += _placement_parts(f, store, ta, tb, key_of)
            parts += _box_parts(f, ta, tb, key_of)
            parts += _path_parts(f, ta, tb, key_of)
        n_own = max(len(keys), 1)
        shp = (nb, GRID_NY, GRID_NX)
        F = np.zeros((n_own,) + shp, np.uint8)
        Uc = np.zeros((1,) + shp, np.uint8)
        g = (GRID_X0, GRID_DX, GRID_NX, GRID_Y0, GRID_DY, GRID_NY)
        for bx0, by0, bx1, by1, ok, own, val, com in parts:
            if not len(own):
                continue
            _raster(bx0, by0, bx1, by1, ok, own, val, F, *g)
            if com.any():
                c = np.ascontiguousarray
                _raster(c(bx0[com]), c(by0[com]), c(bx1[com]), c(by1[com]), c(ok[com]),
                        np.zeros(int(com.sum()), np.int64), np.full(int(com.sum()), 255, np.uint8), Uc, *g)
        F = F[:len(keys)]
        if len(keys):
            U = (F.max(axis=0) > 0).astype(np.uint8)
            Pu = (1.0 - np.prod(1.0 - F.astype(np.float32) / 255.0, axis=0)).astype(np.float32)
            Lk = (F >= LIKELY_V).sum(axis=0, dtype=np.uint8)
        else:
            U, Pu, Lk = np.zeros(shp, np.uint8), np.zeros(shp, np.float32), np.zeros(shp, np.uint8)
        two = np.array([bool(two_mask(k)) if two_mask is not None else False for k in keys], bool)
        P2 = (F[two].max(axis=0).astype(np.float32) / 255.0) if two.any() else np.zeros(shp, np.float32)
        hp = {tr.iid: (float(tr.hp_est), float(tr.hp_sd)) for tr in fc.trackers.values()
              if tr.in_play and not tr.dead and tr.iid in kidx}
        return cls(F, keys, Uc[0], U, Pu, Lk, P2, ta, (time.perf_counter() - t0) * 1e3, hp)

    @classmethod
    def from_bodies(cls, f, two_mask=None) -> "EnemyFields":
        """The body field (module docstring, "Body field"): per live enemy in play, its body box as last seen,
        dead-reckoned along its velocity for at most VEL_CAP_S (at the bin's middle), dilated by the hero hurtbox;
        its zone F (closed) = the cells within BODY_REACH_U + BODY_APPROACH_U_S x t of it; the clearance Vf =
        clip((distance to the nearest body - BODY_REACH_U) / CLEAR_U, 0, 1); bins from FIELD_T0_S to f.horizon."""
        import time
        t0 = time.perf_counter()
        fc = f._fc
        nb = max(int(math.floor((float(f.horizon) - FIELD_T0_S) / FIELD_DT_S + 1e-9)), 0)
        ta = FIELD_T0_S + FIELD_DT_S * np.arange(nb)
        tm = ta + 0.5 * FIELD_DT_S
        hx, hy = fc.half
        trs = [tr for tr in fc.trackers.values()
               if tr.in_play and not tr.dead and not tr.hidden and tr.body is not None]
        K = len(trs)
        shp = (nb, GRID_NY, GRID_NX)
        cx = GRID_X0 + (np.arange(GRID_NX) + 0.5) * GRID_DX
        cy = GRID_Y0 + (np.arange(GRID_NY) + 0.5) * GRID_DY
        dmin = np.full(shp, np.inf, np.float32)
        F = np.zeros((K,) + shp, np.uint8)
        if K and nb:
            b = np.array([tr.body for tr in trs], np.float64)                       # [K, 4]
            v = np.array([tr.vel for tr in trs], np.float64)[:, :2]
            ts = np.array([tr.seen_T - f.origin_t for tr in trs], np.float64)      # sighting, s from the origin
            sh = np.minimum(np.clip(tm[None, :] - ts[:, None], 0.0, None), VEL_CAP_S)   # [K, B]
            x0 = (b[:, None, 0] + v[:, None, 0] * sh - hx)[:, :, None, None]
            x1 = (b[:, None, 2] + v[:, None, 0] * sh + hx)[:, :, None, None]
            y0 = (b[:, None, 1] + v[:, None, 1] * sh - hy)[:, :, None, None]
            y1 = (b[:, None, 3] + v[:, None, 1] * sh + hy)[:, :, None, None]
            ddx = np.maximum(np.maximum(x0 - cx[None, None, None, :], cx[None, None, None, :] - x1), 0.0)
            ddy = np.maximum(np.maximum(y0 - cy[None, None, :, None], cy[None, None, :, None] - y1), 0.0)
            d = np.hypot(ddx, ddy).astype(np.float32)                              # [K, B, NY, NX]
            r = (BODY_REACH_U + BODY_APPROACH_U_S * np.clip(tm[None, :] - ts[:, None], 0.0, None))
            F = (d <= r[:, :, None, None]).astype(np.uint8)
            dmin = d.min(axis=0)
        keys = [tr.iid for tr in trs]
        if K:
            U = F.max(axis=0)
            Lk = F.sum(axis=0, dtype=np.uint8)
        else:
            U, Lk = np.zeros(shp, np.uint8), np.zeros(shp, np.uint8)
        two = np.array([bool(two_mask(k)) if two_mask is not None else False for k in keys], bool)
        P2 = F[two].max(axis=0).astype(np.float32) if two.any() else np.zeros(shp, np.float32)
        Vf = np.clip((dmin - BODY_REACH_U) / CLEAR_U, 0.0, 1.0).astype(np.float32)
        hp = {tr.iid: (float(tr.hp_est), float(tr.hp_sd)) for tr in trs}
        return cls(F, keys, U, U, np.zeros(shp, np.float32), Lk, P2, ta, (time.perf_counter() - t0) * 1e3, hp,
                   Cl=U, Vf=Vf)


def _val(prob) -> np.ndarray:
    """Path probabilities as field values: p x 255, at least 1 (a placement always marks its support)."""
    return np.clip(np.rint(np.asarray(prob, np.float64) * 255.0), 1, 255).astype(np.uint8)


def _tid_info(store, tids: np.ndarray) -> tuple:
    """Per template id (cached on the store): bounding-box table level offsets, bins, t0, static, anchor frame."""
    cache = store.__dict__.setdefault("_tv_info", {})
    uniq, inv = np.unique(tids, return_inverse=True)
    rows = []
    for t in uniq.tolist():
        r = cache.get(t)
        if r is None:
            offs, nt, t0 = store.bbox_table(t)
            tpl = store.template(t) if (t >= 0 or t in store._pooled) else None
            r = cache[t] = (np.asarray(offs, np.int64), int(nt), float(t0), bool(tpl is not None and tpl.static),
                            bool(tpl is not None and tpl.frame == "anchor"))
        rows.append(r)
    loff = np.stack([r[0] for r in rows])[inv]
    nt = np.array([r[1] for r in rows], np.int64)[inv]
    t0 = np.array([r[2] for r in rows], np.float64)[inv]
    static = np.array([r[3] for r in rows], bool)[inv]
    anch = np.array([r[4] for r in rows], bool)[inv]
    return np.ascontiguousarray(loff), nt, t0, static, anch


def _placement_parts(f, store, ta, tb, key_of) -> list:
    """Fine, window and bounding-box placements as bounding-box rows over the field bins."""
    out = []
    info = [(P, meta, fine, _tid_info(store, np.asarray(P.tid, np.int64)) if len(P) else None)
            for P, meta, fine in ((f.P, f.pm, True), (f.W, f.wm, False))]
    rows = store.bb_rows()                    # after _tid_info: a table built lazily there is in it
    for P, meta, fine, inf in info:
        if inf is None:
            continue
        loff, nt, t0, static, anch = inf
        anchored = anch & ~np.isnan(P.ax)
        if fine:
            e0 = np.where(static, -1e9, -P.t_ref)
            e1 = np.where(static, 1e9, -P.t_ref)
        else:
            e0, e1 = P.e0, P.e1
        own = np.array([key_of(int(o)) for o in meta["owner"]], np.int64)
        c = np.ascontiguousarray
        bx = _row_bins(rows, loff, nt, t0, c(e0, np.float64), c(e1, np.float64),
                       c(np.where(anchored, P.ax, 0.0)), c(np.where(anchored, P.ay, 0.0)), np.zeros(len(P)),
                       np.zeros(len(P)), c(np.where(anchored, P.mirror, 1), np.int64), ta, tb, hb.BIN_S, TPL_SLACK)
        out.append((*bx, own, _val(meta["prob"]), np.asarray(meta["committed"], bool)))
    bb = f.bb
    if len(bb["owner"]):
        gcl = bb.get("gcl")
        own = np.array([key_of(("g", int(gcl[i])) if gcl is not None and gcl[i] >= 0 else int(bb["owner"][i]))
                        for i in range(len(bb["owner"]))], np.int64)
        c = np.ascontiguousarray
        bx = _row_bins(rows, c(bb["loff"]), c(bb["nt"]), c(bb["t0"]), c(bb["e0"]), c(bb["e1"]), c(bb["cx"]),
                       c(bb["cy"]), c(bb["hx"]), c(bb["hy"]), c(bb["mir"]), ta, tb, hb.BIN_S, TPL_SLACK)
        out.append((*bx, own, _val(bb["prob"]), np.asarray(bb["committed"], bool)))
    return out


def _box_parts(f, ta, tb, key_of) -> list:
    """The tubes and boxes (MultiForecast.boxes) over the field bins, dilated by the hero hurtbox."""
    if not f.boxes:
        return []
    tubes = f._fc.tables.tubes
    hx, hy = f._fc.half
    K, B = len(f.boxes), len(ta)
    bx0, by0, bx1, by1 = (np.zeros((K, B)) for _ in range(4))
    ok = np.zeros((K, B), bool)
    own = np.zeros(K, np.int64)
    com = np.zeros(K, bool)
    for k, (owner, kind, x0, y0, x1, y1, vx, vy, grow, t_from, t_to, t_seen) in enumerate(f.boxes):
        own[k] = key_of(int(owner))
        lo = np.maximum(ta, t_from)
        if kind == "idle":
            lo = np.maximum(lo, t_seen)
        hi = np.minimum(tb, t_to)
        act = hi >= lo - 1e-9
        da, db = lo - t_seen, hi - t_seen
        if grow is None:
            g = np.zeros(B)
        elif grow[0] == "idle":
            g = tubes.g(grow[1], np.maximum(db, 0.0))
        else:
            g = grow[1] * np.maximum(db, 0.0)
        bx0[k] = np.minimum(x0 + vx * da, x0 + vx * db) - g - hx
        bx1[k] = np.maximum(x1 + vx * da, x1 + vx * db) + g + hx
        by0[k] = np.minimum(y0 + vy * da, y0 + vy * db) - g - hy
        by1[k] = np.maximum(y1 + vy * da, y1 + vy * db) + g + hy
        ok[k] = act
        com[k] = kind == "death"                # MultiForecast.committed() keeps the death boxes only
    return [(bx0, by0, bx1, by1, ok, own, np.full(K, 255, np.uint8), com)]


def _path_parts(f, ta, tb, key_of) -> list:
    """The hazard paths over the field bins: the hull of every centre (slack copies, branches) sampled each
    PATH_DT_S in the bin +- one sample, grown by the path's extents, tube growth, skin and the hero hurtbox."""
    if not f.paths:
        return []
    from ssbot.combat.projectiles import SKIN_U
    hx, hy = f._fc.half
    B = len(ta)
    ts = np.arange(ta[0] - PATH_DT_S, tb[-1] + 2 * PATH_DT_S, PATH_DT_S)
    jb = np.floor((ts - FIELD_T0_S) / FIELD_DT_S + 1e-9).astype(np.int64)
    K = len(f.paths)
    bx0, by0 = np.full((K, B), np.inf), np.full((K, B), np.inf)
    bx1, by1 = np.full((K, B), -np.inf), np.full((K, B), -np.inf)
    own = np.zeros(K, np.int64)
    # a sample counts for every bin whose window +- one sample holds it (its own and at most one neighbour)
    sets = []
    for d in (-1, 0, 1):
        j = jb + d
        jc = np.clip(j, 0, B - 1)
        v = (j >= 0) & (j < B) & (ts >= ta[jc] - PATH_DT_S - 1e-9) & (ts <= tb[jc] + PATH_DT_S + 1e-9)
        sets.append((jc, v))
    for k, p in enumerate(f.paths):
        own[k] = key_of(int(p.iid))
        cx, cy, on, grow = p.at(ts)
        rx, ry = (p.r, p.r) if p.kind == "circle" else (p.hx, p.hy)
        ex = rx + grow + hx + SKIN_U
        ey = ry + grow + hy + SKIN_U
        for b in range(on.shape[0]):
            for jc, v in sets:
                sel = on[b] & v
                if not sel.any():
                    continue
                js = jc[sel]
                np.minimum.at(bx0[k], js, (cx[b] - ex[b])[sel])
                np.minimum.at(by0[k], js, (cy[b] - ey[b])[sel])
                np.maximum.at(bx1[k], js, (cx[b] + ex[b])[sel])
                np.maximum.at(by1[k], js, (cy[b] + ey[b])[sel])
    ok = (bx0 <= bx1) & (by0 <= by1)
    return [(bx0, by0, bx1, by1, ok, own, np.full(K, 255, np.uint8), np.ones(K, bool))]


# ---- the reachable templates ----

_REACH: dict = {}


def reach_templates(params: kin.HeroParams) -> tuple[np.ndarray, np.ndarray]:
    """offs [len(CLASSES), len(REACH_S), K, 2] hurtbox-centre offsets the kinematics reach REACH_S (+- half a field
    bin) after a start of each end class, n [len(CLASSES), len(REACH_S)] (quantised to REACH_Q, deduplicated). From a
    primitive library (run either way or stand, turning once at 0.5 s; no / short / mid / full jumps at once or at
    0.33 s; a dash at once or at 0.42 s) on a wide floor (walls far: the arena's are applied at run time by
    clamping). Built once per parameter set (~0.3 s)."""
    key = (params.frame_time, params.run_speed, params.jump_speed, params.gravity, getattr(params, "weighted", False))
    r = _REACH.get(key)
    if r is not None:
        return r
    path = KIN_DIR / REACH_FILE
    if path.exists() and not getattr(params, "weighted", False):
        z = np.load(path)
        if tuple(np.round(z["key"], 6)) == tuple(np.round(np.array(key[:4], np.float64), 6)) \
                and tuple(z["reach_s"]) == REACH_S:
            r = _REACH[key] = _coarse(z["offs"], z["n"])
            return r
    r = _REACH[key] = _coarse(*_build_reach(params))
    return r


def _coarse(offs: np.ndarray, n: np.ndarray, q=REACH_RUN_Q) -> tuple[np.ndarray, np.ndarray]:
    """The offsets re-quantised to q and deduplicated (a cell's worth of offsets marks one cell at most twice)."""
    per = {}
    for ci in range(offs.shape[0]):
        for mi in range(offs.shape[1]):
            d = offs[ci, mi, :n[ci, mi]]
            per[ci, mi] = np.unique(np.round(d / np.array(q)), axis=0) * np.array(q)
    kmax = max(1, max(len(v) for v in per.values()))
    out = np.zeros((offs.shape[0], offs.shape[1], kmax, 2))
    nn = np.zeros(n.shape, np.int64)
    for (ci, mi), v in per.items():
        out[ci, mi, :len(v)] = v
        nn[ci, mi] = len(v)
    return out, nn


def _build_reach(params: kin.HeroParams) -> tuple[np.ndarray, np.ndarray]:
    ft = params.frame_time
    nf = int(round((max(REACH_S) + FIELD_DT_S) / ft)) + 1
    terrain = kin.Terrain2D.from_boxes([(-200.0, FLOOR_Y - 10.0, 260.0, FLOOR_Y)])
    seqs = []
    half = int(round(0.5 / ft))
    for d1 in (-1, 0, 1):
        for d2 in (-1, 0, 1):
            for jump in ((0, 0), (0, 6), (0, 14), (0, 40), (20, 30)):
                for dash in (-1, 0, 25):
                    m = np.zeros(nf, np.int64)
                    m[:half] |= kin.B_LEFT if d1 < 0 else (kin.B_RIGHT if d1 > 0 else 0)
                    m[half:] |= kin.B_LEFT if d2 < 0 else (kin.B_RIGHT if d2 > 0 else 0)
                    if jump[1]:
                        m[jump[0]:jump[0] + jump[1]] |= kin.B_JUMP
                    if dash >= 0:
                        m[dash:dash + 4] |= kin.B_DASH
                    seqs.append(m)
    masks = np.stack(seqs)
    y_floor = FLOOR_Y + params.foot
    starts = {"ground": dict(ground=True, vy=0.0, y=y_floor), "air_up": dict(ground=False, vy=12.0, y=y_floor + 3.0),
              "air_mid": dict(ground=False, vy=0.0, y=y_floor + 5.0),
              "air_down": dict(ground=False, vy=-12.0, y=y_floor + 5.0)}
    per: dict = {}
    kmax = 1
    for ci, cl in enumerate(CLASSES):
        st = starts[cl]
        S = kin.initial_state(params, 30.0, st["y"], vy=st["vy"], ground=st["ground"])
        ro = kin.rollout(S, masks, params, terrain)
        c = 0.5 * (ro.box[..., :2] + ro.box[..., 2:])            # [N, T+1, 2]
        c0 = c[0, 0]
        for mi, t in enumerate(REACH_S):
            k0 = max(int(math.floor((t - 0.5 * FIELD_DT_S) / ft)), 0)
            k1 = min(int(math.ceil((t + 0.5 * FIELD_DT_S) / ft)), c.shape[1] - 1)
            d = (c[:, k0:k1 + 1] - c0).reshape(-1, 2)
            q = np.unique(np.round(d / np.array(REACH_Q)), axis=0) * np.array(REACH_Q)
            per[ci, mi] = q
            kmax = max(kmax, len(q))
    offs = np.zeros((len(CLASSES), len(REACH_S), kmax, 2))
    n = np.zeros((len(CLASSES), len(REACH_S)), np.int64)
    for (ci, mi), q in per.items():
        offs[ci, mi, :len(q)] = q
        n[ci, mi] = len(q)
    return offs, n


def write_reach(params: kin.HeroParams, path=None) -> "Path":
    """Build the reachable templates and write them (tools: python -m ssbot.combat.terminal)."""
    _REACH.clear()
    p = path or KIN_DIR / REACH_FILE
    old = p.with_suffix(".tmp.npz")
    offs, n = _build_reach(params)
    key = np.array([params.frame_time, params.run_speed, params.jump_speed, params.gravity], np.float64)
    np.savez_compressed(old, offs=offs, n=n, key=key, reach_s=np.array(REACH_S))
    old.replace(p)
    return p


def end_class(flags_end: np.ndarray, vy_end: np.ndarray) -> np.ndarray:
    """CLASSES index of each row's last nominal frame."""
    g = (flags_end & kin.F_GROUND) != 0
    return np.where(g, 0, np.where(vy_end > AIR_VY, 1, np.where(vy_end < -AIR_VY, 3, 2))).astype(np.int64)


class TerminalValue:
    def __init__(self, params: kin.HeroParams):
        self.offs, self.n = reach_templates(params)

    def rows(self, fields: EnemyFields, ex: np.ndarray, ey: np.ndarray, ecls: np.ndarray, t_end: float
             ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """(E, trapped, overlap, H_exp) [N] for rows ending at hurtbox centres (ex, ey) of class ecls at origin time
        t_end (module docstring). Without a field (no bins): E 1, trapped False, overlap 0, H 0."""
        N = len(ex)
        E, ov, he = np.ones(N), np.zeros(N), np.zeros(N)
        tr = np.zeros(N, np.bool_)
        if fields is None or fields.nbins == 0 or N == 0:
            return E, tr, ov, he
        jb = np.array([fields.bin_of(t_end + t) for t in REACH_S], np.int64)
        # a reach time past the field (the forecast's horizon) is dropped, except that the last one keeps the last
        # bin when the end itself is inside the field (a T = 48 row: 0.8 + 1.4 s > 2 s)
        for m, t in enumerate(REACH_S):
            if t_end + t > fields.ta[-1] + FIELD_DT_S + 1e-9 and m != len(REACH_S) - 1:
                jb[m] = -1
        wt = np.array([1.0 / (1.0 + t) for t in REACH_S])
        trap_m = np.array([t <= TRAP_S + 1e-9 for t in REACH_S])
        hexp_m = np.array([t <= HEXP_S + 1e-9 for t in REACH_S])
        _terminal_rows(np.ascontiguousarray(ex, np.float64), np.ascontiguousarray(ey, np.float64),
                       np.ascontiguousarray(ecls, np.int64), jb, wt, trap_m, hexp_m, self.offs, self.n,
                       fields.Cl, fields.Vf, fields.Lk, fields.P2, GRID_X0, GRID_DX, GRID_NX, GRID_Y0, GRID_DY, GRID_NY,
                       WALL_L + hb.HERO_HALF_U[0], WALL_R - hb.HERO_HALF_U[0], HERO_CY, E, tr, ov, he)
        return E, tr, ov, he


if __name__ == "__main__":
    import sys
    pp = sys.argv[1] if len(sys.argv) > 1 else str(KIN_DIR / "hero_reaper_forum.json")
    print(write_reach(kin.HeroParams.load(pp)))
