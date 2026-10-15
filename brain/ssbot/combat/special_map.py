"""The backward score map of one (enemy, move) for the down slash (task 1v1 SG2; the person's space-time map design
2026-10-12..14, C:/ssbot/data/m2_map/spec_notes_zh.txt parts 89-96; forum.md 56). It replaces the slam-only special
tables (specials v1 / v2) for new code; the planner does not read it yet.

Inputs: the move data (ssbot.combat.move_data: per-frame damage and target boxes, every timing variant) and the hero
event macros' vertical profiles (ssbot.combat.hero_macros: ground jumps per hold h, the down-slash bounce, per cycle
position q of the 50 Hz physics steps among the 60 fps frames).

Nodes (what the map stores): the ground layer (k, x) and one apex layer per apex class (k, x): a ground jump with hold
h, or a bounce whose contact height lies in a 0.2 u bin. k = frame from the move's antic entry (the hero state at the
end of frame k), x = the hero's box centre along the enemy's facing relative to its position at k = 0 (u, centre to
centre; on a lattice of one run step 0.165 u). Scores >= 0 are feasible nodes; -inf (stored as the level INF) means no
safe continuation exists; NaN (level NONE) means no node of that class at that frame.

Why the computation runs per frame. Normal movement has no horizontal inertia, so between two nodes the hero's
horizontal input is free in every frame (the effective key d in {-1, 0, +1}, one run step in each frame that has a
physics step) while the vertical follows the event's profile. The builder therefore runs the backward pass over
absolute frames k (descending) through every state of every macro (tube = event class x frame index j since the
event), so the best horizontal schedule and the press frame inside each rise and fall are found exactly (S2, S3);
only the ground and apex states are stored. The step pattern is the game's global 50 Hz clock: a map is built per
physics phase p (the hero's cycle position at k = 0; frame k has a step iff (k - p) % 6 != 0), so the run steps, the
jump and bounce profiles are exact on the lattice (SG1: box error 0 per q); the map without the phase is the minimum
over p.

Rules (S3-S5):
  * damage: every hurt box of every timing variant (union; the robust share is 1.0, see below), the hero box dilated
    by MX in x (half a lattice cell: the hero is not on the lattice; plus one run step: a key change one frame late)
    and MY in y (the bounce's contact-height bin, the off-lattice alpha). A node touching it is infeasible.
  * the down slash: pressed in frame k + 1 from an airborne node at k; the slash polygon (both alternations, both
    facings: the facing and the alternation are not state) at the rendered pos must meet the target box (root) in
    every timing variant on one frame of k + 4 .. k + 10 (ACTIVE), with the target shrunk by RENDER_U and the half
    cell; c_max = the first frame all contact; the contact may be one frame later (SG1). The hero follows the event's
    profile with a fixed key until the contact; damage is checked up to c_max - 2 (PRE_PROTECT_F: a hit 1-2 frames
    before the contact does not land). A slash on an enemy in a move is a certain hit (the person, 2026-10-11): only
    the bounce branch is certified. The bounce: i-frames contact + 0 .. + 8 (no damage test), then the bounce tube of
    the contact height's bin; its value is the minimum over every possible contact frame [c_min, c_max + 1].
  * a press one frame late (20 % of live presses): a strike counts only if the press one frame later (the key held
    one more frame) is a strike too; its value is the minimum of both.
  * cooldown: a second press in a bounce only from 16 frames after the contact (COOLDOWN_F 19 from the press, the
    contact 3..9 frames after the press; derived from the event time, no extra dimension).
  * the contact must happen inside the move (k_contact <= the earliest variant's last frame).
Scores (S6): a strike = gamma^c (1 + depth) + the bounce continuation's value (follow-ups: a second strike adds its
own discounted score); depth = min(distance to the region boundary along x / 0.5 u, the number of the next three
press frames that still strike / 3) (time late-only). A path node = gamma x the best successor; clearance = the
minimum distance from the dilated hero box to damage along the chosen path (capped at C_CAP); the stored score is
R + WC x min(C, C_CAP) / C_CAP. Operation costs are not stored (lambda per key change at search time).

Robust share 1.0 over the "observed" variants (antic 47/48/49 x Slam 0 4/5 x Slam 2 5/6 x Recover 14/15/16 x lunge
phase 0.2/0.8): a failure costs a hit, and the hero cannot tell the variants apart before Slam 0 starts; a share
< 1 would need a per-variant pass (72x). Walls: open floor (the Clapper away from the walls); see forum.md 56.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from ssbot.combat import move_data as md
from ssbot.combat.hero_macros import COOLDOWN_F, IFRAMES, HeroMacros
from ssbot.combat.pogo_model import ACTIVE, slash_poly
from ssbot.combat.pogo_slam import PRE_PROTECT_F, clip_band
from ssbot.knowledge import kinematics as kin

MAP_DIR = md.FORUM
NEG = -np.inf
LEVEL_SCALE = 0.02            # stored level = round(score / LEVEL_SCALE), 0..250
INF_LEVEL, NONE_LEVEL = 255, 254


@dataclass
class MapConfig:
    x_lo: float = -12.0           # map x range (u, hero centre to enemy anchor along its facing)
    x_hi: float = 16.0
    gamma: float = 0.99           # per frame
    wc: float = 0.3               # clearance weight
    c_cap: float = 1.0            # clearance cap (u)
    mx: float = 0.0825 + 0.165    # damage dilation in x: half a lattice cell + one run step (a key one frame late)
    my: float = 0.12              # damage dilation in y: the contact-height bin half width + off-lattice alpha
    sx: float = 0.0825 + 0.02     # target shrink in x: half a cell + RENDER_U x
    sx_move: float = 0.165        # extra target shrink when the key is held (the render lag of the last step)
    sy: float = 0.16              # rendered-y tolerance of the contact (bin half width + RENDER_U y)
    holds: tuple = (1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 19, 20, 22, 25)   # T1's holds included
    cb_w: float = 0.2             # contact-height bin (box bottom above the floor at the contact)
    cb_max: float = 6.0
    yb: float = 0.05              # y bin of the damage / contact lookups
    tail: int = 60                # frames after the latest variant's end (the body only)
    variants: str = "observed"
    cool_j: int = COOLDOWN_F - ACTIVE[0]   # bounce index from which a new press is allowed (press = node + 1 >= 16)
    depth_x_u: float = 0.5
    depth_t: int = 3
    late_press: bool = True       # a strike must also work pressed one frame late (20 % of live presses)
    late_jump: bool = True        # a ground jump start must also work pressed one frame late
    wall_front: float | None = None   # hero x limit in front (u from the anchor), None: open floor
    wall_back: float | None = None
    # SG4 (KeyedMapBuilder): the key already read is part of the state (it moves the body in the next frame), so a
    # key change can be late. key_noise: "none" (no late keys; only the held key at a strike's contact), "exp" (the
    # expected value over the measured late-input distribution p_late (on time, +1, +2, +3 frames); a late branch that
    # meets damage counts 0: a hit means no strike), "hard" (a key change also needs its one-frame-late path feasible:
    # the late press / late jump rule), "hard_exp" (hard for +1, the +2 / +3 branches in expectation)
    keyed: bool = False
    key_noise: str = "none"
    p_late: tuple = (0.785, 0.20, 0.01, 0.005)

    def key(self) -> dict:
        d = asdict(self)
        d["holds"] = list(self.holds)
        d["p_late"] = list(self.p_late)
        return d


@dataclass
class Tube:
    """One event class: per start cycle q0 the vertical profile (box bottom above the floor y, rendered pos y,
    airborne flag, i-frame flag) per index j since the event, the landing index L (the first grounded index after
    leaving: the slice j is valid for j < L) and the apex index."""
    kind: str                     # ground | jump | bounce
    param: float                  # hold h | contact-height bin centre
    y: np.ndarray                 # [6, J]
    yr: np.ndarray                # [6, J]
    air: np.ndarray               # [6, J] bool
    inv: np.ndarray               # [6, J] bool
    L: np.ndarray                 # [6]
    apex: np.ndarray              # [6]
    s0: int = 0                   # first slice index
    n: int = 0                    # slices (max L)


class Geometry:
    """The move's damage / target geometry on the lattice (all variants), shared by the phases."""

    def __init__(self, spec: md.MoveSpec, hm: HeroMacros, cfg: MapConfig):
        t0 = time.time()
        self.spec, self.hm, self.cfg = spec, hm, cfg
        self.variants = spec.variants(cfg.variants)
        if cfg.wall_front is not None:
            # a wall in front stops the lunge: the body's front edge (the antic root box's, 2.04 u) stays behind it
            front0 = max(float(np.nanmax(v.boxes["root"][0, 1])) for v in self.variants)
            for v in self.variants:
                v.disp = np.minimum(v.disp, max(cfg.wall_front - front0, 0.0))
        self.end_min = min(v.end_k for v in self.variants)
        self.end_max = max(v.end_k for v in self.variants)
        self.K = self.end_max + 1 + cfg.tail
        self.step = hm.step_u
        self.NX = int(np.floor((cfg.x_hi - cfg.x_lo) / self.step + 1e-9)) + 1
        self.xs = cfg.x_lo + self.step * np.arange(self.NX)
        self.hw, self.H = hm.hw, hm.H
        self.floor = hm.stand_y0
        self.y_lo = -0.2
        self.NYB = int(np.ceil((12.0 - self.y_lo) / cfg.yb))
        self.NYR = int(np.ceil((14.0 - self.y_lo) / cfg.yb))
        self.ncb = int(round(cfg.cb_max / cfg.cb_w))
        self._boxes()
        self._danger()
        self._contact()
        self._tubes()
        self.seconds = time.time() - t0

    # ---- boxes per frame (union over the variants), y above the floor ----
    def _boxes(self):
        pa = self.spec.pos_above_floor
        self.dmg, self.tgt = [], []
        for k in range(self.K):
            ds, ts = set(), set()
            for v in self.variants:
                for b in v.damage(k):
                    ds.add(tuple(np.round([b[0], b[1], b[2] + pa, b[3] + pa], 4)))
                for b in v.targets(k):
                    ts.add(tuple(np.round([b[0], b[1], b[2] + pa, b[3] + pa], 4)))
            self.dmg.append(np.array(sorted(ds), float).reshape(-1, 4))
            self.tgt.append(np.array(sorted(ts), float).reshape(-1, 4))

    def ybin(self, y) -> np.ndarray:
        return np.clip(np.floor((np.asarray(y) - self.y_lo) / self.cfg.yb).astype(np.int64), 0, self.NYB - 1)

    def rbin(self, y) -> np.ndarray:
        return np.clip(np.floor((np.asarray(y) - self.y_lo) / self.cfg.yb).astype(np.int64), 0, self.NYR - 1)

    def _danger(self):
        """D[k, yb, x]: the dilated hero box with its bottom in bin yb at lattice x meets a damage box of frame k in
        some variant; CL[k, yb, x]: the gap between that box and the nearest damage box (u, capped)."""
        c = self.cfg
        K, NYB, NX = self.K, self.NYB, self.NX
        self.D = np.zeros((K, NYB, NX), bool)
        self.CL = np.full((K, NYB, NX), np.float32(c.c_cap), np.float32)
        lo = self.y_lo + c.yb * np.arange(NYB)
        hy0, hy1 = lo - c.my, lo + c.yb + self.H + c.my
        hx0, hx1 = self.xs - self.hw - c.mx, self.xs + self.hw + c.mx
        wl, wr = c.wall_back, c.wall_front
        for k in range(K):
            B = self.dmg[k]
            if not len(B):
                continue
            yov = (B[None, :, 2] < hy1[:, None]) & (B[None, :, 3] > hy0[:, None])          # [NYB, n]
            xin = (hx1[None, :] > B[:, None, 0]) & (hx0[None, :] < B[:, None, 1])           # [n, NX]
            self.D[k] = (yov[:, :, None] & xin[None]).any(1)
            gx = np.maximum(0.0, np.maximum(B[:, None, 0] - hx1[None, :], hx0[None, :] - B[:, None, 1]))   # [n, NX]
            gy = np.maximum(0.0, np.maximum(B[None, :, 2] - hy1[:, None], hy0[:, None] - B[None, :, 3]))   # [NYB, n]
            dist = np.sqrt(gx[None] ** 2 + gy[:, :, None] ** 2).min(1)
            self.CL[k] = np.minimum(dist, c.c_cap)
        # per variant: its own damage set per frame (VD[v, k] -> DS[k][id]): the pre-contact test of a strike is per
        # variant (an early-lunging variant's body is no danger once that variant's own contact protects the hero)
        pa = self.spec.pos_above_floor
        self.VD = np.zeros((len(self.variants), K + 16), np.int64)
        self.DS = []
        for k in range(K):
            B = self.dmg[k]
            sets: dict = {}
            for vi, v in enumerate(self.variants):
                idx = []
                for b in v.damage(k):
                    key = np.round([b[0], b[1], b[2] + pa, b[3] + pa], 4)
                    idx.append(int(np.flatnonzero((np.abs(B - key) < 1e-6).all(1))[0]))
                self.VD[vi, k] = sets.setdefault(tuple(sorted(idx)), len(sets))
            ds = np.zeros((max(len(sets), 1), NYB, NX), bool)
            if len(B):
                yov = (B[None, :, 2] < hy1[:, None]) & (B[None, :, 3] > hy0[:, None])
                xin = (hx1[None, :] > B[:, None, 0]) & (hx0[None, :] < B[:, None, 1])
                for key, sid in sets.items():
                    if key:
                        ds[sid] = (yov[:, list(key), None] & xin[None, list(key)]).any(1)
            self.DS.append(ds)
        self.VD[:, K:] = self.VD[:, K - 1:K]
        if wl is not None or wr is not None:          # the wall buckets: the hero cannot stand past a wall
            out = np.zeros(NX, bool)
            if wr is not None:
                out |= self.xs + self.hw > wr
            if wl is not None:
                out |= self.xs - self.hw < wl
            self.D[:, :, out] = True
            for ds in self.DS:
                ds[:, :, out] = True

    def _contact(self):
        """Per frame k and per distinct target box b of that frame (tgt[k][b]; VB[v, k] = variant v's box index):
        CB[k][b, r, x] (robust: both alternations, both facings, the rendered y anywhere in bin r +- sy, the target
        shrunk by sx) and CBM (the extra shrink of a held key) for a slash whose rendered pos y (above the floor) lies
        in bin r; CY[k, r, x]: some variant / polygon at the bin centre (the earliest possible contact). Each variant
        has its own first contact frame; the builder takes c_min / c_max over them (a strike needs all to touch)."""
        c = self.cfg
        K, NYR, NX = self.K, self.NYR, self.NX
        polys = [slash_poly(f, a) for f in (1, -1) for a in (False, True)]
        cache: dict = {}

        def iv(pi, y0, y1, yr):
            key = (pi, round(y0 - yr, 4), round(y1 - yr, 4))
            if key not in cache:
                cache[key] = clip_band(polys[pi], y0 - yr, y1 - yr)
            return cache[key]

        pa = self.spec.pos_above_floor
        self.VB = np.zeros((len(self.variants), K + 16), np.int64)
        for vi, v in enumerate(self.variants):
            for k in range(K):
                t = v.targets(k)
                if len(t):
                    key = tuple(np.round([t[0][0], t[0][1], t[0][2] + pa, t[0][3] + pa], 4))
                    self.VB[vi, k] = int(np.flatnonzero((np.abs(self.tgt[k] - np.array(key)) < 1e-6).all(1))[0])
            self.VB[vi, K:] = self.VB[vi, K - 1]
        self.CB, self.CBM = [], []
        self.CY = np.zeros((K, NYR, NX), bool)
        rlo = self.y_lo + c.yb * np.arange(NYR)
        for k in range(K):
            T = self.tgt[k]
            cb = np.zeros((max(len(T), 1), NYR, NX), bool)
            cbm = np.zeros_like(cb)
            for r in range(NYR):
                yc = rlo[r] + 0.5 * c.yb
                if not len(T) or yc - 3.0 > T[:, 3].max() or yc + 1.0 < T[:, 2].min():
                    continue
                lo_y, hi_y = np.inf, -np.inf
                for b, t in enumerate(T):
                    lo_a, hi_a, ok_all = -np.inf, np.inf, True
                    for pi in range(4):
                        for yy in (rlo[r] - c.sy, rlo[r] + c.yb + c.sy):
                            q = iv(pi, t[2], t[3], yy)
                            if q is None:
                                ok_all = False
                                break
                            lo_a, hi_a = max(lo_a, t[0] - q[1]), min(hi_a, t[1] - q[0])
                        q = iv(pi, t[2], t[3], yc)
                        if q is not None:
                            lo_y, hi_y = min(lo_y, t[0] - q[1]), max(hi_y, t[1] - q[0])
                    if ok_all and hi_a - lo_a > 2 * c.sx:
                        cb[b, r] = (self.xs > lo_a + c.sx) & (self.xs < hi_a - c.sx)
                        cbm[b, r] = (self.xs > lo_a + c.sx + c.sx_move) & (self.xs < hi_a - c.sx - c.sx_move)
                if hi_y > lo_y:
                    self.CY[k, r] = (self.xs > lo_y) & (self.xs < hi_y)
            self.CB.append(cb)
            self.CBM.append(cbm)

    # ---- the event tubes ----
    def _tubes(self):
        hm, c = self.hm, self.cfg
        tubes = []
        g = np.zeros((6, 1))
        tubes.append(Tube("ground", 0.0, g.copy(), g + hm.jumps[(1, 0)].py[0], np.zeros((6, 1), bool),
                          np.zeros((6, 1), bool), np.full(6, 1 << 20), np.zeros(6, np.int64)))
        for h in c.holds:
            ps = [hm.jumps[(h, q)] for q in range(6)]
            L = np.array([p.land for p in ps])
            if (L <= 0).any():
                raise ValueError(f"hold {h}: no landing inside the jump table")
            J = int(L.max())
            y = np.stack([p.y[:J] for p in ps])
            yr = y + np.stack([p.py[:J] for p in ps])
            air = np.stack([(p.flags[:J] & kin.F_GROUND) == 0 for p in ps])
            tubes.append(Tube("jump", h, y, yr, air, np.zeros_like(air), L, np.array([p.apex for p in ps])))
        i0, i1 = IFRAMES
        for cb in range(self.ncb):
            yc = (cb + 0.5) * c.cb_w
            ys, Ls = [], []
            for qc in range(6):
                b = hm.bounces[qc]
                yy = yc + b.y
                below = np.flatnonzero(yy[b.apex:] <= 0.0)
                Ls.append(b.apex + int(below[0]))
                ys.append(yy)
            L = np.array(Ls)
            J = int(L.max())
            y = np.stack([v[:J] for v in ys])
            yr = y + np.stack([hm.bounces[qc].py[:J] for qc in range(6)])
            air = np.ones((6, J), bool)
            inv = np.zeros((6, J), bool)
            inv[:, i0:i1 + 1] = True
            tubes.append(Tube("bounce", round(yc, 3), y, yr, air, inv, L,
                              np.array([hm.bounces[qc].apex for qc in range(6)])))
        s = 0
        for t in tubes:
            t.s0, t.n = s, (1 if t.kind == "ground" else t.y.shape[1])
            s += t.n
        self.tubes = tubes
        self.NS = s
        self.JM = max(t.n for t in tubes) + 16
        # padded per-tube profile tables [n_tubes, 6, JM]
        nt = len(tubes)
        self.TY = np.full((nt, 6, self.JM), 50.0)
        self.TYR = np.full((nt, 6, self.JM), 50.0)
        self.TAIR = np.zeros((nt, 6, self.JM), bool)
        self.TINV = np.zeros((nt, 6, self.JM), bool)
        self.TL = np.zeros((nt, 6), np.int64)
        self.TAPEX = np.zeros((nt, 6), np.int64)
        for i, t in enumerate(tubes):
            n = t.y.shape[1]
            self.TY[i, :, :n], self.TYR[i, :, :n] = t.y, t.yr
            self.TAIR[i, :, :n], self.TINV[i, :, :n] = t.air, t.inv
            self.TL[i], self.TAPEX[i] = t.L, t.apex
        self.TYB = self.ybin(self.TY)
        self.TRB = self.rbin(self.TYR)
        self.ST = np.concatenate([np.full(t.n, i) for i, t in enumerate(tubes)]).astype(np.int64)   # slice -> tube
        self.SJ = np.concatenate([np.arange(t.n) for t in tubes]).astype(np.int64)                   # slice -> j
        self.SN = np.array([t.n for t in tubes])[self.ST]                                            # tube length
        self.kind = np.array([t.kind for t in tubes])
        self.bounce0 = np.array([t.s0 for t in tubes if t.kind == "bounce"], np.int64)               # bin -> slice
        self.can_kind = np.isin(self.kind[self.ST], ("jump", "bounce"))
        self.cool = np.where(self.kind[self.ST] == "bounce", c.cool_j, 0)

    def steps(self, p: int) -> np.ndarray:
        """[K + 16] 1 if frame k has a physics step for phase p (frame 0: none counted)."""
        k = np.arange(self.K + 16)
        s = ((k - p) % 6 != 0).astype(np.int64)
        s[0] = 0
        return s

    def x_index(self, x) -> np.ndarray:
        return np.rint((np.asarray(x) - self.cfg.x_lo) / self.step).astype(np.int64)

    def classes(self) -> list[dict]:
        return [{"i": i, "kind": t.kind, "param": t.param, "apex": t.apex.tolist(), "L": t.L.tolist(),
                 "apex_y": [round(float(t.y[q, t.apex[q]]), 3) for q in range(6)] if t.kind != "ground" else [0.0] * 6}
                for i, t in enumerate(self.tubes)]


def _shift(a: np.ndarray, n: int, fill) -> np.ndarray:
    """out[..., x] = a[..., x + n] (fill outside)."""
    if n == 0:
        return a
    out = np.empty_like(a)
    if n > 0:
        out[..., :-n] = a[..., n:]
        out[..., -n:] = fill
    else:
        out[..., -n:] = a[..., :n]
        out[..., :-n] = fill
    return out


@dataclass
class PhaseMap:
    """One phase's backward pass. S [K, NS, NX] float16: the score of every macro state (slice) at every frame;
    SV [K, NS, NX, 3] float16 (keep_full): the robust strike value for a press in frame k + 1 with the key d - 1 held
    (-inf: none); the ground / apex layers; the strike projection by press frame."""
    p: int
    S: np.ndarray | None
    SV: np.ndarray | None
    ground: np.ndarray            # [K, NX] float32
    apex: np.ndarray              # [n_tubes, K, NX] float32 (NaN: no apex state of that class at k)
    strike: np.ndarray            # [K + 1, NX] max robust strike score (1 + depth) by press frame and node x
    strike_y: np.ndarray          # [K + 1, NX] the node's box bottom (above the floor) of that best strike
    strike_kind: np.ndarray       # [K + 1, NX] 1 jump, 2 bounce
    jstart: np.ndarray | None = None   # [n_holds, K, NX] the score of starting a ground jump with hold h at (k, x)
    stats: dict = field(default_factory=dict)


class MapBuilder:
    def __init__(self, geo: Geometry):
        self.g = geo

    def build(self, p: int, keep_full: bool = False) -> PhaseMap:
        g, c = self.g, self.g.cfg
        t0 = time.time()
        K, NS, NX = g.K, g.NS, g.NX
        st = g.steps(p)
        ncum = np.cumsum(st)                                   # steps in frames 1..k
        gam = np.float32(c.gamma)
        R, C = {}, {}                                          # ring: frame -> [NS, NX]
        OK0, B0 = {}, {}                                       # ring: frame -> [3, NS, NX] raw strike ok / bounce value
        S = np.empty((K, NS, NX), np.float16) if keep_full else None
        SV = np.full((K, NS, NX, 3), -np.inf, np.float16) if keep_full else None
        ground = np.full((K, NX), -np.inf, np.float32)
        apex = np.full((len(g.tubes), K, NX), np.nan, np.float32)
        strike = np.zeros((K + 1, NX), np.float32)
        strike_y = np.full((K + 1, NX), np.nan, np.float32)
        strike_kind = np.zeros((K + 1, NX), np.int8)
        sidx = np.arange(NS)
        j0 = np.array([t.s0 for t in g.tubes if t.kind == "jump"])
        jstart = np.full((len(j0), K, NX), -np.inf, np.float32)
        n_strike_cells = 0
        # why a press with a contact in every variant is not a strike, by press frame and node x (diagnostics)
        why = {w: np.zeros((K + 1, NX), np.int32) for w in ("contact", "air_or_end", "pre_damage", "bounce", "late")}
        for k in range(K - 1, -1, -1):
            q = (p - k + g.SJ) % 6                              # each slice's start cycle (the event at k - j)
            T, J = g.ST, g.SJ
            Lq = g.TL[T, q]
            valid = J < Lq
            yb = g.TYB[T, q, J]
            inv = g.TINV[T, q, J]
            Dn = g.D[k][yb] & ~inv[:, None]
            CLn = np.where(inv[:, None], np.float32(c.c_cap), g.CL[k][yb])
            # ---- continuation: the next state of the same macro (or the ground after the landing)
            if k == K - 1:
                bR = np.zeros((NS, NX), np.float32)
                bC = CLn.astype(np.float32)
            else:
                nxt = np.where(g.kind[T] == "ground", 0, np.where(J + 1 < Lq, sidx + 1, 0))
                Rn, Cn = R[k + 1][nxt], C[k + 1][nxt]
                bR = np.full((NS, NX), -np.inf, np.float32)
                bC = np.zeros((NS, NX), np.float32)
                bS = np.full((NS, NX), -np.inf, np.float32)
                for d in (-1, 0, 1):
                    n = d * int(st[k + 1])
                    rr = gam * _shift(Rn, n, -np.inf)
                    cc = np.minimum(CLn, _shift(Cn, n, 0.0))
                    sc = rr + c.wc * np.minimum(cc, c.c_cap) / c.c_cap
                    better = sc > bS
                    bS = np.where(better, sc, bS)
                    bR = np.where(better, rr, bR)
                    bC = np.where(better, cc, bC)
            # ---- the strike: a down slash pressed in frame k + 1
            ok_now = np.zeros((3, NS, NX), bool)
            b_now = np.full((3, NS, NX), -np.inf, np.float32)
            sv_best = np.full((NS, NX), -np.inf, np.float32)
            sv_C = np.zeros((NS, NX), np.float32)
            can = valid & g.can_kind[T] & g.TAIR[T, q, J] & (J >= g.cool) & (k + 4 + 1 <= g.end_min)
            ss = np.flatnonzero(can)
            if len(ss) and k + 11 < K:
                Ts, Js, qs = T[ss], J[ss], q[ss]
                Ls = Lq[ss]
                rel = {}
                for i in range(1, 12):
                    idx = Js + i
                    rel[i] = (idx < Ls, g.TYB[Ts, qs, idx], g.TRB[Ts, qs, idx], g.TY[Ts, qs, idx])
                nrel = {i: int(ncum[k + i] - ncum[k]) for i in range(1, 12)}
                ia = list(range(ACTIVE[0] + 1, ACTIVE[1] + 2))
                # the variant classes: one target box and one damage set sequence over the frames k + 1 .. k + 10
                classes = np.unique(np.concatenate([g.VB[:, k + 1:k + 11], g.VD[:, k + 1:k + 11]], axis=1), axis=0)
                for di, d in enumerate((-1, 0, 1)):
                    CBx = g.CBM if d else g.CB
                    cmin = np.full((len(ss), NX), -1, np.int64)
                    for i in ia:
                        air_i, _, rb_i, _ = rel[i]
                        if k + i > g.end_min:
                            break
                        y = _shift(g.CY[k + i][rb_i], d * nrel[i], False) & air_i[:, None]
                        cmin = np.where((cmin < 0) & y, i, cmin)
                    # per variant class: its first robust contact, and its own damage before that contact (frames
                    # 1 .. c - PRE_PROTECT_F: a contact one frame late still protects from c - 1 on); a strike needs
                    # every class to touch with no damage before
                    cmax = np.full((len(ss), NX), -1, np.int64)
                    every = np.ones((len(ss), NX), bool)
                    nocon = np.zeros((len(ss), NX), bool)
                    predmg = np.zeros((len(ss), NX), bool)
                    for cls in classes:
                        sb, sd = cls[:10], cls[10:]
                        cc_ = np.full((len(ss), NX), -1, np.int64)
                        for i in ia:
                            if k + i > g.end_min:
                                break
                            air_i, _, rb_i, _ = rel[i]
                            a = _shift(CBx[k + i][sb[i - 1], rb_i], d * nrel[i], False) & air_i[:, None]
                            cc_ = np.where((cc_ < 0) & a, i, cc_)
                        con = cc_ >= 0
                        bad = np.zeros_like(con)
                        for i in range(1, ACTIVE[1]):
                            sel = con & (i <= cc_ - PRE_PROTECT_F)
                            if not sel.any():
                                break
                            _, yb_i, _, _ = rel[i]
                            bad |= sel & _shift(g.DS[k + i][sd[i - 1]][yb_i], d * nrel[i], True)
                        nocon |= ~con
                        predmg |= con & bad
                        every &= con & ~bad
                        cmax = np.maximum(cmax, cc_)
                    why["contact"][k + 1] += (~nocon).sum(0).astype(np.int32)
                    why["pre_damage"][k + 1] += (~nocon & predmg).sum(0).astype(np.int32)
                    cmax = np.where(every, cmax, -1)
                    ok = cmax >= 0
                    ok_c = ok.copy()
                    if not ok.any():
                        continue
                    cmin = np.where(cmin < 0, cmax, np.minimum(cmin, cmax))
                    # airborne one frame after c_max too (a contact one frame late), inside the move
                    air_next = np.stack([rel[i][0] for i in range(1, 12)])          # [11, n]
                    cm1 = np.clip(cmax + 1, 1, 11)
                    ok &= np.take_along_axis(air_next.T, cm1 - 1, axis=1) & (k + cmax + 1 <= g.end_min)
                    why["air_or_end"][k + 1] += (ok_c & ~ok).sum(0).astype(np.int32)
                    ok_c = ok.copy()
                    # the bounce: the minimum over the contact frames c_min .. c_max + 1
                    Bm = np.full((len(ss), NX), np.inf, np.float32)
                    Cm = np.full((len(ss), NX), np.inf, np.float32)
                    for cc in range(ACTIVE[0] + 1, ACTIVE[1] + 3):
                        sel = ok & (cc >= cmin) & (cc <= cmax + 1)
                        if not sel.any():
                            continue
                        _, _, _, ycon = rel[cc]
                        cb = np.floor(ycon / c.cb_w).astype(np.int64)
                        has = (cb >= 0) & (cb < g.ncb)
                        sb = g.bounce0[np.clip(cb, 0, g.ncb - 1)]
                        Rb = _shift(R[k + cc][sb], d * nrel[cc], -np.inf)
                        Cb = _shift(C[k + cc][sb], d * nrel[cc], 0.0)
                        Rb = np.where(has[:, None], Rb, -np.inf)
                        Bm = np.where(sel, np.minimum(Bm, Rb), Bm)
                        Cm = np.where(sel, np.minimum(Cm, Cb), Cm)
                    ok &= np.isfinite(Bm)
                    why["bounce"][k + 1] += (ok_c & ~ok).sum(0).astype(np.int32)
                    disc = gam ** np.maximum(cmax, 0).astype(np.float32)
                    ok_now[di, ss] = ok
                    b_now[di, ss] = np.where(ok, disc * Bm, -np.inf)
                    # robust late press: the same key one frame more, pressed in frame k + 2
                    n1 = d * int(st[k + 1])
                    part = np.where(Js + 1 < g.SN[ss], ss + 1, ss)
                    okL = ok & (Js + 1 < g.SN[ss])[:, None]
                    late_ok = _shift(OK0[k + 1][di][part], n1, False) if (k + 1) in OK0 else np.zeros_like(ok)
                    late_b = _shift(B0[k + 1][di][part], n1, -np.inf) if (k + 1) in B0 else np.full_like(Bm, -np.inf)
                    if c.late_press:
                        why["late"][k + 1] += (okL & ~late_ok).sum(0).astype(np.int32)
                        okL &= late_ok
                    else:
                        okL, late_b = ok.copy(), np.full_like(Bm, np.inf)
                    if not okL.any():
                        continue
                    BL = np.minimum(np.where(ok, disc * Bm, -np.inf), late_b)
                    # depth: late-only time margin (the next three presses) and the x margin on the row
                    cnt = np.zeros_like(BL)
                    run = np.ones_like(okL)
                    for m in range(1, c.depth_t + 1):
                        km = k + m
                        pm = np.where(Js + m < g.SN[ss], ss + m, ss)
                        if km in OK0:
                            nm = d * int(ncum[km] - ncum[k])
                            run = run & _shift(OK0[km][di][pm], nm, False) & (Js + m < g.SN[ss])[:, None]
                        else:
                            run = np.zeros_like(run)
                        cnt += run
                    dt = cnt / c.depth_t
                    marg = np.full(BL.shape, np.inf, np.float32)
                    nmax = int(np.ceil(c.depth_x_u / g.step)) + 1
                    for m in range(nmax, 0, -1):
                        fail = ~_shift(okL, m, False) | ~_shift(okL, -m, False)
                        marg = np.where(fail, (m - 0.5) * g.step, marg)
                    dx = np.minimum(marg / c.depth_x_u, 1.0)
                    depth = np.minimum(dx, dt)
                    sv = np.where(okL, disc * (1.0 + depth) + BL, -np.inf).astype(np.float32)
                    cs = np.minimum(CLn[ss], np.where(np.isfinite(Cm), Cm, 0.0))
                    sc = sv + c.wc * np.minimum(cs, c.c_cap) / c.c_cap
                    cur = sv_best[ss] + c.wc * np.minimum(sv_C[ss], c.c_cap) / c.c_cap
                    better = sc > cur
                    sv_best[ss] = np.where(better, sv, sv_best[ss])
                    sv_C[ss] = np.where(better, cs, sv_C[ss])
                    if SV is not None:
                        SV[k, ss, :, di] = sc.astype(np.float16)
                    # the strike projection (press frame k + 1)
                    sco = np.where(okL & ~Dn[ss], 1.0 + depth, 0.0)
                    if sco.any():
                        n_strike_cells += int((sco > 0).sum())
                        best_row = sco.max(0)
                        arg = sco.argmax(0)
                        upd = best_row > strike[k + 1]
                        strike[k + 1] = np.where(upd, best_row, strike[k + 1])
                        strike_y[k + 1] = np.where(upd, g.TY[Ts[arg], qs[arg], Js[arg]], strike_y[k + 1])
                        kk = np.where(g.kind[Ts[arg]] == "bounce", 2, 1).astype(np.int8)
                        strike_kind[k + 1] = np.where(upd, kk, strike_kind[k + 1])
            # ---- the node: the best of continuing and striking; damage and invalid states are infeasible
            sc_c = bR + c.wc * np.minimum(bC, c.c_cap) / c.c_cap
            sc_s = sv_best + c.wc * np.minimum(sv_C, c.c_cap) / c.c_cap
            use_s = sc_s > sc_c
            Rk = np.where(use_s, sv_best, bR)
            Ck = np.where(use_s, sv_C, bC)
            bad = Dn | ~valid[:, None]
            if SV is not None:
                SV[k][bad] = -np.inf                            # no strike from an infeasible node
            Rk = np.where(bad, -np.inf, Rk).astype(np.float32)
            Ck = np.where(bad, 0.0, Ck).astype(np.float32)
            # the ground node: also every jump start (the slice (h, 0) is the same standing state)
            if c.late_jump and k + 1 < K:
                # a jump pressed one frame late: the hero stands (any key) one more frame and starts the same jump at
                # k + 1; the start counts with the worse of both (the raw starts of k + 1 are kept in JR / JC)
                Rl = np.full_like(Rk[j0], np.inf)
                Cl = np.full_like(Ck[j0], np.inf)
                for d in (-1, 0, 1):
                    n = d * int(st[k + 1])
                    Rl = np.minimum(Rl, _shift(JR, n, -np.inf))
                    Cl = np.minimum(Cl, _shift(JC, n, 0.0))
                JR, JC = Rk[j0].copy(), Ck[j0].copy()
                Rk[j0] = np.minimum(Rk[j0], gam * Rl)
                Ck[j0] = np.minimum(Ck[j0], Cl)
            else:
                JR, JC = Rk[j0].copy(), Ck[j0].copy()
            scj = Rk[j0] + c.wc * np.minimum(Ck[j0], c.c_cap) / c.c_cap
            jstart[:, k] = scj
            sc0 = Rk[0] + c.wc * np.minimum(Ck[0], c.c_cap) / c.c_cap
            bj = scj.argmax(0)
            jb = scj.max(0) > sc0
            Rk[0] = np.where(jb, Rk[j0][bj, np.arange(NX)], Rk[0])
            Ck[0] = np.where(jb, Ck[j0][bj, np.arange(NX)], Ck[0])
            R[k], C[k] = Rk, Ck
            OK0[k], B0[k] = ok_now, b_now
            for old in [kk for kk in R if kk > k + 12]:
                del R[old], C[old]
            for old in [kk for kk in OK0 if kk > k + 4]:
                del OK0[old], B0[old]
            Sk = Rk + c.wc * np.minimum(Ck, c.c_cap) / c.c_cap
            if S is not None:
                S[k] = Sk.astype(np.float16)
            ground[k] = Sk[0]
            # the apex layers: the slices at their class's apex index at this frame
            at_apex = valid & (J == g.TAPEX[T, q]) & (g.kind[T] != "ground")
            for s in np.flatnonzero(at_apex):
                ti = T[s]
                apex[ti, k] = np.fmax(apex[ti, k], Sk[s])
        stats = {"p": p, "seconds": round(time.time() - t0, 1), "strike_cells": n_strike_cells, "why": why}
        return PhaseMap(p, S, SV, ground, apex, strike, strike_y, strike_kind, jstart, stats)


class KeyedMapBuilder(MapBuilder):
    """SG4: the backward pass with the key already read as part of the state (forum.md 59).

    R[k][c] is the value at the end of frame k with the key c (-1 / 0 / +1 along the enemy's facing) already read: it
    moves the body in frame k + 1. The choice at a node is the key d read in frame k + 1 (moving the body in frame
    k + 2), the slash (pressed in frame k + 1 with c held through it) or a ground jump. A key change (d != c) can land
    late (cfg.p_late: on time, +1, +2, +3 frames): late by m frames, c moves the body m more frames and the state is
    (k + 1 + m, d) (the intermediate nodes must be feasible). cfg.key_noise:
      none      on time only (the late key is ignored; the strike's contact value still uses the held key);
      exp       the expected value over the late distribution; a late branch through damage counts 0;
      hard      the +1 branch must be feasible too and the change counts with the worse of both (as the late press);
      hard_exp  hard for +1, the +2 / +3 branches in expectation.
    The clearance follows the same branches (expected, or the minimum for hard). A strike's bounce value is read with
    the held key at the contact (the SG3b map gap: the key held through the slash is still committed there). The late
    jump: the hero stands one frame more with c and starts the same jump.
    PhaseMap fields (keep_full): S [K, 3, NS, NX], SV [K, NS, NX, 3] (the strike with the key d held = the state's
    key), ground [K, 3, NX], apex [n_tubes, K, 3, NX], jstart [n_holds, K, 3, NX]."""

    def build(self, p: int, keep_full: bool = False) -> PhaseMap:
        g, c = self.g, self.g.cfg
        t0 = time.time()
        K, NS, NX = g.K, g.NS, g.NX
        st = g.steps(p)
        ncum = np.cumsum(st)
        gam = np.float32(c.gamma)
        wc, cap = np.float32(c.wc), np.float32(c.c_cap)
        pl = np.asarray(c.p_late, np.float32)
        pl = pl / pl.sum()
        mode = c.key_noise
        R, C, F, NXT, CLR = {}, {}, {}, {}, {}
        OK0, B0 = {}, {}
        S = np.empty((K, 3, NS, NX), np.float16) if keep_full else None
        SV = np.full((K, NS, NX, 3), -np.inf, np.float16) if keep_full else None
        ground = np.full((K, 3, NX), -np.inf, np.float32)
        apex = np.full((len(g.tubes), K, 3, NX), np.nan, np.float32)
        strike = np.zeros((K + 1, NX), np.float32)
        strike_y = np.full((K + 1, NX), np.nan, np.float32)
        strike_kind = np.zeros((K + 1, NX), np.int8)
        sidx = np.arange(NS)
        j0 = np.array([t.s0 for t in g.tubes if t.kind == "jump"])
        jstart = np.full((len(j0), K, 3, NX), -np.inf, np.float32)
        n_strike_cells = 0
        why = {w: np.zeros((K + 1, NX), np.int32) for w in ("contact", "air_or_end", "pre_damage", "bounce", "late")}
        JR = JC = None

        def score(r, cc):
            return r + wc * np.minimum(cc, cap) / cap

        for k in range(K - 1, -1, -1):
            q = (p - k + g.SJ) % 6
            T, J = g.ST, g.SJ
            Lq = g.TL[T, q]
            valid = J < Lq
            yb = g.TYB[T, q, J]
            inv = g.TINV[T, q, J]
            Dn = g.D[k][yb] & ~inv[:, None]
            CLn = np.where(inv[:, None], cap, g.CL[k][yb]).astype(np.float32)
            nxt = np.where(g.kind[T] == "ground", 0, np.where(J + 1 < Lq, sidx + 1, 0))
            NXT[k], CLR[k] = nxt, CLn
            # ---- continuation per state key c: the body moves by c in frame k + 1, then the chosen key d
            bR = np.full((3, NS, NX), -np.inf, np.float32)
            bC = np.zeros((3, NS, NX), np.float32)
            if k == K - 1:
                bR[:] = 0.0
                bC[:] = CLn
            else:
                s1 = nxt
                s2 = NXT[k + 1][s1] if (k + 1) in NXT else None
                s3 = NXT[k + 2][s2] if (s2 is not None and (k + 2) in NXT) else None
                s4 = NXT[k + 3][s3] if (s3 is not None and (k + 3) in NXT) else None
                for ci, cv in enumerate((-1, 0, 1)):
                    n1 = cv * int(st[k + 1])
                    bS = np.full((NS, NX), -np.inf, np.float32)
                    # the late branches' intermediate path: c keeps moving the body m more frames
                    late = []
                    if mode != "none":
                        ok_path = _shift(F[k + 1][s1], n1, False)
                        cl_path = _shift(CLR[k + 1][s1], n1, 0.0)
                        nm = n1
                        for m, (sm_, kk) in enumerate(((s2, k + 2), (s3, k + 3), (s4, k + 4)), start=1):
                            if sm_ is None or kk not in R:
                                late.append(None)
                                continue
                            nm = nm + cv * int(st[kk])
                            late.append((sm_, kk, nm, ok_path.copy(), cl_path.copy()))
                            if kk in F and m < 3:
                                ok_path &= _shift(F[kk][sm_], nm, False)
                                cl_path = np.minimum(cl_path, _shift(CLR[kk][sm_], nm, 0.0))
                    for di, dv in enumerate((-1, 0, 1)):
                        V1 = _shift(R[k + 1][di][s1], n1, -np.inf)
                        C1 = _shift(C[k + 1][di][s1], n1, 0.0)
                        if di == ci or mode == "none":
                            rr, cc = gam * V1, np.minimum(CLn, C1)
                        else:
                            br, bc = [], []
                            for m, lb in enumerate(late, start=1):
                                if lb is None:
                                    br.append(np.full((NS, NX), -np.inf, np.float32))
                                    bc.append(np.zeros((NS, NX), np.float32))
                                    continue
                                sm_, kk, nm, okp, clp = lb
                                v = gam ** m * np.where(okp, _shift(R[kk][di][sm_], nm, -np.inf), -np.inf)
                                cv_ = np.where(okp, np.minimum(clp, _shift(C[kk][di][sm_], nm, 0.0)), 0.0)
                                br.append(v.astype(np.float32))
                                bc.append(cv_.astype(np.float32))
                            if mode == "hard":
                                rr = gam * np.minimum(V1, br[0])
                                cc = np.minimum(CLn, np.minimum(C1, bc[0]))
                            else:
                                def z(v):
                                    return np.where(np.isfinite(v), v, 0.0)
                                if mode == "exp":
                                    fin = np.isfinite(V1)
                                    rexp = pl[0] * V1 + pl[1] * z(br[0]) + pl[2] * z(br[1]) + pl[3] * z(br[2])
                                    cexp = pl[0] * C1 + pl[1] * z(bc[0]) + pl[2] * z(bc[1]) + pl[3] * z(bc[2])
                                else:                        # hard_exp: the +1 branch must be feasible
                                    fin = np.isfinite(V1) & np.isfinite(br[0])
                                    rexp = pl[0] * V1 + pl[1] * br[0] + pl[2] * z(br[1]) + pl[3] * z(br[2])
                                    cexp = pl[0] * C1 + pl[1] * bc[0] + pl[2] * z(bc[1]) + pl[3] * z(bc[2])
                                rr = np.where(fin, gam * rexp, -np.inf)
                                cc = np.minimum(CLn, np.where(fin, cexp, 0.0))
                        sc = score(rr, cc)
                        better = sc > bS
                        bS = np.where(better, sc, bS)
                        bR[ci] = np.where(better, rr, bR[ci])
                        bC[ci] = np.where(better, cc, bC[ci])
            # ---- the strike pressed in frame k + 1 with the key d held (d = the state key)
            ok_now = np.zeros((3, NS, NX), bool)
            b_now = np.full((3, NS, NX), -np.inf, np.float32)
            svb = np.full((3, NS, NX), -np.inf, np.float32)
            svC = np.zeros((3, NS, NX), np.float32)
            can = valid & g.can_kind[T] & g.TAIR[T, q, J] & (J >= g.cool) & (k + 4 + 1 <= g.end_min)
            ss = np.flatnonzero(can)
            if len(ss) and k + 11 < K:
                Ts, Js, qs = T[ss], J[ss], q[ss]
                Ls = Lq[ss]
                rel = {}
                for i in range(1, 12):
                    idx = Js + i
                    rel[i] = (idx < Ls, g.TYB[Ts, qs, idx], g.TRB[Ts, qs, idx], g.TY[Ts, qs, idx])
                nrel = {i: int(ncum[k + i] - ncum[k]) for i in range(1, 12)}
                ia = list(range(ACTIVE[0] + 1, ACTIVE[1] + 2))
                classes = np.unique(np.concatenate([g.VB[:, k + 1:k + 11], g.VD[:, k + 1:k + 11]], axis=1), axis=0)
                for di, d in enumerate((-1, 0, 1)):
                    CBx = g.CBM if d else g.CB
                    cmin = np.full((len(ss), NX), -1, np.int64)
                    for i in ia:
                        air_i, _, rb_i, _ = rel[i]
                        if k + i > g.end_min:
                            break
                        y = _shift(g.CY[k + i][rb_i], d * nrel[i], False) & air_i[:, None]
                        cmin = np.where((cmin < 0) & y, i, cmin)
                    cmax = np.full((len(ss), NX), -1, np.int64)
                    every = np.ones((len(ss), NX), bool)
                    nocon = np.zeros((len(ss), NX), bool)
                    predmg = np.zeros((len(ss), NX), bool)
                    for cls in classes:
                        sb, sd = cls[:10], cls[10:]
                        cc_ = np.full((len(ss), NX), -1, np.int64)
                        for i in ia:
                            if k + i > g.end_min:
                                break
                            air_i, _, rb_i, _ = rel[i]
                            a = _shift(CBx[k + i][sb[i - 1], rb_i], d * nrel[i], False) & air_i[:, None]
                            cc_ = np.where((cc_ < 0) & a, i, cc_)
                        con = cc_ >= 0
                        bad = np.zeros_like(con)
                        for i in range(1, ACTIVE[1]):
                            sel = con & (i <= cc_ - PRE_PROTECT_F)
                            if not sel.any():
                                break
                            _, yb_i, _, _ = rel[i]
                            bad |= sel & _shift(g.DS[k + i][sd[i - 1]][yb_i], d * nrel[i], True)
                        nocon |= ~con
                        predmg |= con & bad
                        every &= con & ~bad
                        cmax = np.maximum(cmax, cc_)
                    why["contact"][k + 1] += (~nocon).sum(0).astype(np.int32)
                    why["pre_damage"][k + 1] += (~nocon & predmg).sum(0).astype(np.int32)
                    cmax = np.where(every, cmax, -1)
                    ok = cmax >= 0
                    ok_c = ok.copy()
                    if not ok.any():
                        continue
                    cmin = np.where(cmin < 0, cmax, np.minimum(cmin, cmax))
                    air_next = np.stack([rel[i][0] for i in range(1, 12)])
                    cm1 = np.clip(cmax + 1, 1, 11)
                    ok &= np.take_along_axis(air_next.T, cm1 - 1, axis=1) & (k + cmax + 1 <= g.end_min)
                    why["air_or_end"][k + 1] += (ok_c & ~ok).sum(0).astype(np.int32)
                    ok_c = ok.copy()
                    # the bounce with the key d still held at the contact (the state key of the contact frame)
                    Bm = np.full((len(ss), NX), np.inf, np.float32)
                    Cm = np.full((len(ss), NX), np.inf, np.float32)
                    for cc in range(ACTIVE[0] + 1, ACTIVE[1] + 3):
                        sel = ok & (cc >= cmin) & (cc <= cmax + 1)
                        if not sel.any():
                            continue
                        _, _, _, ycon = rel[cc]
                        cb = np.floor(ycon / c.cb_w).astype(np.int64)
                        has = (cb >= 0) & (cb < g.ncb)
                        sb = g.bounce0[np.clip(cb, 0, g.ncb - 1)]
                        Rb = _shift(R[k + cc][di][sb], d * nrel[cc], -np.inf)
                        Cb = _shift(C[k + cc][di][sb], d * nrel[cc], 0.0)
                        Rb = np.where(has[:, None], Rb, -np.inf)
                        Bm = np.where(sel, np.minimum(Bm, Rb), Bm)
                        Cm = np.where(sel, np.minimum(Cm, Cb), Cm)
                    ok &= np.isfinite(Bm)
                    why["bounce"][k + 1] += (ok_c & ~ok).sum(0).astype(np.int32)
                    disc = gam ** np.maximum(cmax, 0).astype(np.float32)
                    ok_now[di, ss] = ok
                    b_now[di, ss] = np.where(ok, disc * Bm, -np.inf)
                    n1 = d * int(st[k + 1])
                    part = np.where(Js + 1 < g.SN[ss], ss + 1, ss)
                    okL = ok & (Js + 1 < g.SN[ss])[:, None]
                    late_ok = _shift(OK0[k + 1][di][part], n1, False) if (k + 1) in OK0 else np.zeros_like(ok)
                    late_b = _shift(B0[k + 1][di][part], n1, -np.inf) if (k + 1) in B0 else np.full_like(Bm, -np.inf)
                    if c.late_press:
                        why["late"][k + 1] += (okL & ~late_ok).sum(0).astype(np.int32)
                        okL &= late_ok
                    else:
                        okL, late_b = ok.copy(), np.full_like(Bm, np.inf)
                    if not okL.any():
                        continue
                    BL = np.minimum(np.where(ok, disc * Bm, -np.inf), late_b)
                    cnt = np.zeros_like(BL)
                    run = np.ones_like(okL)
                    for m in range(1, c.depth_t + 1):
                        km = k + m
                        pm_ = np.where(Js + m < g.SN[ss], ss + m, ss)
                        if km in OK0:
                            nm = d * int(ncum[km] - ncum[k])
                            run = run & _shift(OK0[km][di][pm_], nm, False) & (Js + m < g.SN[ss])[:, None]
                        else:
                            run = np.zeros_like(run)
                        cnt += run
                    dt = cnt / c.depth_t
                    marg = np.full(BL.shape, np.inf, np.float32)
                    nmax = int(np.ceil(c.depth_x_u / g.step)) + 1
                    for m in range(nmax, 0, -1):
                        fail = ~_shift(okL, m, False) | ~_shift(okL, -m, False)
                        marg = np.where(fail, (m - 0.5) * g.step, marg)
                    dx = np.minimum(marg / c.depth_x_u, 1.0)
                    depth = np.minimum(dx, dt)
                    sv = np.where(okL, disc * (1.0 + depth) + BL, -np.inf).astype(np.float32)
                    cs = np.minimum(CLn[ss], np.where(np.isfinite(Cm), Cm, 0.0))
                    svb[di, ss] = sv
                    svC[di, ss] = cs
                    if SV is not None:
                        SV[k, ss, :, di] = score(sv, cs).astype(np.float16)
                    sco = np.where(okL & ~Dn[ss], 1.0 + depth, 0.0)
                    if sco.any():
                        n_strike_cells += int((sco > 0).sum())
                        best_row = sco.max(0)
                        arg = sco.argmax(0)
                        upd = best_row > strike[k + 1]
                        strike[k + 1] = np.where(upd, best_row, strike[k + 1])
                        strike_y[k + 1] = np.where(upd, g.TY[Ts[arg], qs[arg], Js[arg]], strike_y[k + 1])
                        kk = np.where(g.kind[Ts[arg]] == "bounce", 2, 1).astype(np.int8)
                        strike_kind[k + 1] = np.where(upd, kk, strike_kind[k + 1])
            # ---- the node per state key: continuing or the slash with that key; damage / invalid infeasible
            use_s = score(svb, svC) > score(bR, bC)
            Rk = np.where(use_s, svb, bR)
            Ck = np.where(use_s, svC, bC)
            bad = (Dn | ~valid[:, None])[None]
            if SV is not None:
                SV[k][np.broadcast_to(bad[0][:, :, None], SV[k].shape)] = -np.inf
            Rk = np.where(bad, -np.inf, Rk).astype(np.float32)
            Ck = np.where(bad, 0.0, Ck).astype(np.float32)
            # the jump starts (slice (h, 0) = standing); the late jump: one more standing frame with the same key
            if c.late_jump and k + 1 < K and JR is not None:
                Rl = np.stack([_shift(JR[ci], cv * int(st[k + 1]), -np.inf) for ci, cv in enumerate((-1, 0, 1))])
                Cl = np.stack([_shift(JC[ci], cv * int(st[k + 1]), 0.0) for ci, cv in enumerate((-1, 0, 1))])
                JR, JC = Rk[:, j0].copy(), Ck[:, j0].copy()
                Rk[:, j0] = np.minimum(Rk[:, j0], gam * Rl)
                Ck[:, j0] = np.minimum(Ck[:, j0], Cl)
            else:
                JR, JC = Rk[:, j0].copy(), Ck[:, j0].copy()
            scj = score(Rk[:, j0], Ck[:, j0])                    # [3, n_holds, NX]
            jstart[:, k] = scj.transpose(1, 0, 2)
            sc0 = score(Rk[:, 0], Ck[:, 0])
            bj = scj.argmax(1)                                    # [3, NX]
            jb = scj.max(1) > sc0
            ar = np.arange(NX)
            for ci in range(3):
                Rk[ci, 0] = np.where(jb[ci], Rk[ci, j0][bj[ci], ar], Rk[ci, 0])
                Ck[ci, 0] = np.where(jb[ci], Ck[ci, j0][bj[ci], ar], Ck[ci, 0])
            R[k], C[k] = Rk, Ck
            F[k] = np.isfinite(Rk).any(0)
            OK0[k], B0[k] = ok_now, b_now
            for old in [kk for kk in R if kk > k + 12]:
                del R[old], C[old]
            for old in [kk for kk in F if kk > k + 6]:
                del F[old], NXT[old], CLR[old]
            for old in [kk for kk in OK0 if kk > k + 4]:
                del OK0[old], B0[old]
            Sk = score(Rk, Ck)
            if S is not None:
                S[k] = Sk.astype(np.float16)
            ground[k] = Sk[:, 0]
            at_apex = valid & (J == g.TAPEX[T, q]) & (g.kind[T] != "ground")
            for s in np.flatnonzero(at_apex):
                ti = T[s]
                apex[ti, k] = np.fmax(apex[ti, k], Sk[:, s])
        stats = {"p": p, "seconds": round(time.time() - t0, 1), "strike_cells": n_strike_cells, "why": why,
                 "keyed": True, "key_noise": mode}
        return PhaseMap(p, S, SV, ground, apex, strike, strike_y, strike_kind, jstart, stats)


def builder_for(geo: Geometry) -> MapBuilder:
    return KeyedMapBuilder(geo) if geo.cfg.keyed else MapBuilder(geo)


# ---- the stored map (knowledge/1.0.30000/enemies/forum/special_map_<move>.npz) ----
def quantize(a: np.ndarray) -> np.ndarray:
    out = np.full(a.shape, NONE_LEVEL, np.uint8)
    fin = np.isfinite(a)
    out[fin] = np.clip(np.rint(np.maximum(a[fin], 0.0) / LEVEL_SCALE), 0, 250).astype(np.uint8)
    out[np.isneginf(a)] = INF_LEVEL
    return out


def dequantize(q: np.ndarray) -> np.ndarray:
    out = q.astype(np.float32) * LEVEL_SCALE
    out[q == INF_LEVEL] = -np.inf
    out[q == NONE_LEVEL] = np.nan
    return out


class SpecialMap:
    """The stored map: per physics phase p the ground layer [K, NX] and the apex layers [n_classes, K, NX] (levels,
    see quantize), the strike projection, meta. Lookups snap x to the lattice; q None = the minimum over phases."""

    def __init__(self, path: Path):
        z = np.load(path, allow_pickle=False)
        self.meta = json.loads(str(z["meta"]))
        self.ground_q = z["ground"]
        self.apex_q = z["apex"]
        self.strike = z["strike"].astype(np.float32) * LEVEL_SCALE
        self.x_lo, self.step = self.meta["x_lo"], self.meta["step"]
        self.K = self.ground_q.shape[1]
        self.NX = self.ground_q.shape[2]
        self.classes = self.meta["classes"]
        self._ground = dequantize(self.ground_q)
        self._apex = None
        self.jump_start = dequantize(z["jump_start"]) if "jump_start" in z.files else None
        sy = z["strike_y"].astype(np.float32) * 0.05 if "strike_y" in z.files else None
        self.strike_y = None if sy is None else np.where(z["strike_y"] == 255, np.nan, sy)
        self.holds = self.meta.get("jump_holds", [])
        self.xs = self.x_lo + self.step * np.arange(self.NX)

    @classmethod
    def load(cls, move: str = "CL_SLAM", path: Path | None = None) -> "SpecialMap":
        return cls(path or MAP_DIR / f"special_map_{move}.npz")

    @property
    def apex(self) -> np.ndarray:
        if self._apex is None:
            self._apex = dequantize(self.apex_q)
        return self._apex

    def xi(self, x) -> np.ndarray:
        return np.clip(np.rint((np.asarray(x) - self.x_lo) / self.step).astype(np.int64), 0, self.NX - 1)

    def ground(self, k: int, x, q: int | None = None):
        if not 0 <= k < self.K:
            return np.nan
        g = self._ground[:, k, self.xi(x)]
        return g.min(0) if q is None else g[q]

    def layer(self, which: str, k: int, q: int | None = None) -> np.ndarray:
        """[NX] (ground) or [n_classes, NX] (apex / jump_start) scores at frame k; q None = the minimum over the
        phases (a missing node in one phase is skipped)."""
        a = {"ground": self._ground, "apex": self.apex, "jump_start": self.jump_start}[which]
        if not 0 <= k < self.K:
            return np.full(a.shape[2:] if which == "ground" else (a.shape[1],) + a.shape[3:], np.nan)
        v = a[:, k] if which == "ground" else a[:, :, k]
        if q is not None:
            return v[q]
        return np.where(np.isnan(v).all(0), np.nan, np.nanmin(np.where(np.isnan(v), np.inf, v), axis=0))

    def ground_choice(self, k: int, x: float, key: int = 0, lam: float = 0.02, q: int | None = None) -> dict:
        """The one-step lookahead from a ground node (S8): stand / left / right (the ground layer two frames ahead,
        the key now moving in the frame after next) or a ground jump with hold h pressed next frame (its start
        score); lambda per key change. Never jump without a reachable strike (start score <= WC)."""
        opts = {}
        for nm, d in (("left", -1), ("stand", 0), ("right", 1)):
            g = self.layer("ground", k + 2, q)
            xi = int(self.xi(x + (key + d) * self.step))
            opts[nm] = float(g[xi]) - lam * (d != key)
        if self.jump_start is not None:
            js = self.layer("jump_start", k, q)          # the jump key pressed next frame: the node is now
            xi = int(self.xi(x))
            for i, h in enumerate(self.holds):
                v = float(js[i, xi])
                if v > self.meta["config"]["wc"] + 1e-3:
                    opts[f"jump h{h:g}"] = v - lam
        best = max(opts, key=lambda n: opts[n] if np.isfinite(opts[n]) else -1e9)
        return {"best": best, "value": opts[best], "options": opts}

    def readiness(self, x, q: int | None = None):
        """The ground layer at the antic entry (k = 0): the score a standing hero at x starts the move with."""
        return self.ground(0, x, q)


def save_map(path: Path, geo: Geometry, maps: list[PhaseMap], meta: dict) -> dict:
    ground = np.stack([m.ground for m in maps])
    apex = np.stack([m.apex[1:] for m in maps])            # the ground tube has no apex
    strike = np.stack([m.strike for m in maps]).max(0)
    m = {"x_lo": geo.cfg.x_lo, "step": geo.step, "NX": geo.NX, "K": geo.K, "end_min": geo.end_min,
         "end_max": geo.end_max, "level_scale": LEVEL_SCALE, "inf_level": INF_LEVEL, "none_level": NONE_LEVEL,
         "classes": geo.classes()[1:], "config": geo.cfg.key(), "floor_y": geo.floor,
         "n_variants": len(geo.variants)} | meta
    path.parent.mkdir(parents=True, exist_ok=True)
    jstart = np.stack([m.jstart for m in maps])
    sy = np.stack([np.where(m.strike > 0, m.strike_y, np.nan) for m in maps])
    strike_y = np.where(np.isnan(sy).all(0), np.nan, np.nanmax(np.where(np.isnan(sy), -np.inf, sy), axis=0))
    m["jump_holds"] = [t.param for t in geo.tubes if t.kind == "jump"]
    np.savez_compressed(path, ground=quantize(ground), apex=quantize(apex), jump_start=quantize(jstart),
                        strike=np.clip(np.rint(strike / LEVEL_SCALE), 0, 250).astype(np.uint8),
                        strike_y=np.where(np.isfinite(strike_y), np.clip(np.rint(strike_y / 0.05), 0, 250), 255
                                          ).astype(np.uint8), meta=json.dumps(m))
    return m


__all__ = ["MapConfig", "Geometry", "MapBuilder", "PhaseMap", "SpecialMap", "save_map", "quantize", "dequantize",
           "LEVEL_SCALE", "INF_LEVEL", "NONE_LEVEL", "MAP_DIR"]
