"""The Clapper slam and a Wanderer down slash, from the real boxes (task 1v1 T1, the person's experiment method
2026-10-11, forum.md 46): the slam's boxes per frame from the antic entry (knowledge/.../pogo_clapper_slam.json, built
by ssbot.tools.pogo_theory template from 1,661 recorded slams), the hero's kinematics (ssbot.knowledge.kinematics),
the slash polygon and the contact rule (ssbot.combat.pogo_model) and the bounce (EV_POGO: the downspike i-frames,
cState.downspikeInvulnerabilitySteps 8 physics steps = pogo_invul 0.16 s against ENEMY damage, set by every hit
response, HeroDownAttack.OnHitResponded). No DamageHero cooldown: ContinueBounceTrigger's SetCooldown(0.5) skips a
DamageHero on a HealthManager's object, and the Clapper's body DamageHero is on its root (the hammer's Slam Collider
1 / 2 were never bounced on: they are passed through). A hit before the contact cancels the slash: no bounce.

The slam (all boxes deterministic per state and frame in the state; x in the Clapper's facing frame, the Clapper
faces the hero from the antic entry and never turns during the slam: 0 of 2,328 slams):
  Slam Antic 48-49 frames, the Clapper still; root box top 0.53 below its position (1.25 for the first 6 frames)
  Slam 0     4-5 frames, the lunge starts (vx 30 u/s: 0.6 u per 0.02 s physics step); the root box rises to +0.19
  Slam 1     3 frames, still lunging; root box low and long (front 3.23); Slam Collider 1: -1.91..6.24 x -3.19..3.13
  Slam 2     5-6 frames, stopped (lunge 3.0-4.2 u in all); Slam Collider 2: 0.67..7.75 x -4.99..2.64
  Slam Recover 15 frames, the root box only
A bounce is safe when the pogo i-frames cover every hammer and body frame the hero's box still touches.

    tl = SlamTimeline.load()                     # nominal timing; SlamTimeline.variants() for the timing spread
    th = SlamTheory(params, terrain)
    res = th.grid(tl, x0s, taus)                 # every jump path x jump frame x start x: the outcome at the press
"""
from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ssbot.combat.pogo_model import ACTIVE, slash_poly
from ssbot.ipc.framing import mask
from ssbot.knowledge import kinematics as kin

TEMPLATE = Path(__file__).resolve().parents[3] / "knowledge" / "1.0.30000" / "enemies" / "forum" / "pogo_clapper_slam.json"
M_L, M_R, M_D, M_J, M_A = mask("left"), mask("right"), mask("down"), mask("jump"), mask("attack")
BODY_COOLDOWN_F = 0           # no cooldown on a HealthManager's own DamageHero (HeroDownAttack.ContinueBounceTrigger)
HERO_STAND_DY = 1.553         # hero.pos above the floor when standing (Forum floor y 3.015, hero.pos y 4.568)
FLOOR_Y = 3.015
CX = 31.0                     # the Clapper's x in the theory (the Forum's middle: no wall within a lunge)
BIG = 1 << 30
# a hit the hero's box takes up to this many frames before the slash's contact does not land: the contact's i-frames
# win (the recorded slashes: probe FP 14 -> 7, the person's 3 -> 2, no new misses; HeroBox applies a buffered hit late)
PRE_PROTECT_F = 2


@dataclass
class SlamTimeline:
    """Per frame k from the antic entry (k = 0: the first frame the Control state reads Slam Antic): the state, the
    root box and the hammer boxes in the Clapper's frame (x along its facing, relative to its position at the antic
    entry; y relative to that position) and the lunge displacement."""
    state: list
    root: np.ndarray          # [K, 4] x0, x1, y0, y1
    hammer: np.ndarray        # [K, 4] (nan: none)
    disp: np.ndarray          # [K]
    pos_y: float              # the Clapper's position above the floor
    name: str = "nominal"

    @classmethod
    def load(cls, antic: int = 49, s0: int = 5, s1: int = 3, s2: int = 6, rec: int = 15, phase: float = 0.5,
             K: int = 160, path: Path = TEMPLATE) -> "SlamTimeline":
        t = json.loads(Path(path).read_text("utf-8"))
        ham = {k.split("|")[0]: v for k, v in t["hammer"].items()}
        seq = [("Slam Antic", antic), ("Slam 0", s0), ("Slam 1", s1), ("Slam 2", s2), ("Slam Recover", rec)]
        state, root, hm = [], [], []
        for s, n in seq:
            boxes = t["root"][s]
            for j in range(n):
                state.append(s)
                root.append(boxes[min(j, len(boxes) - 1)])
                hm.append(ham.get(s, [np.nan] * 4))
        while len(state) < K:                 # after the slam: the last recover box (Idle), no hammer
            state.append("after")
            root.append(root[-1])
            hm.append([np.nan] * 4)
        # the lunge: vx set on the Slam 0 entry frame (Update, after that frame's physics); every 0.02 s physics step
        # in the frames after it moves 0.6 u until the Slam 2 entry frame's Update (its own steps still move)
        k0 = antic
        k2 = antic + s0 + s1
        ft = 1 / 60
        dt = float(t.get("physics_dt", 0.02))
        step = float(t.get("lunge_vx", 30.0)) * dt
        disp = np.zeros(K)
        for k in range(k0 + 1, K):
            kk = min(k, k2)
            n = np.floor((kk - k0) * ft / dt - phase + 1e-9) + 1 if kk > k0 else 0
            disp[k] = step * max(n, 0)
        return cls(state[:K], np.asarray(root[:K], float), np.asarray(hm[:K], float), disp, float(t["pos_above_floor"]),
                   f"a{antic}s{s0}p{phase}")

    @classmethod
    def variants(cls, **kw) -> list["SlamTimeline"]:
        """The timing spread seen in the slams: antic 48 / 49 frames, Slam 0 4 / 5, the lunge's physics phase."""
        return [cls.load(antic=a, s0=s, phase=p, **kw) for a, s, p in itertools.product((48, 49), (4, 5), (0.2, 0.8))]

    def world(self, k: np.ndarray, which: str = "root") -> np.ndarray:
        """[.., 4] boxes at frames k (clipped to the timeline) with the lunge applied."""
        kk = np.clip(k, 0, len(self.state) - 1)
        b = (self.root if which == "root" else self.hammer)[kk].copy()
        b[..., 0] += self.disp[kk]
        b[..., 1] += self.disp[kk]
        return b


def clip_band(poly: np.ndarray, y0: float, y1: float) -> tuple[float, float] | None:
    """The x range of a convex polygon clipped to y0 <= y <= y1 (None: empty)."""
    pts = [tuple(p) for p in poly]
    for lim, keep_ge in ((y0, True), (y1, False)):
        out = []
        n = len(pts)
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            ina = a[1] >= lim if keep_ge else a[1] <= lim
            inb = b[1] >= lim if keep_ge else b[1] <= lim
            if ina:
                out.append(a)
            if ina != inb:
                t = (lim - a[1]) / (b[1] - a[1])
                out.append((a[0] + t * (b[0] - a[0]), lim))
        pts = out
        if not pts:
            return None
    xs = [p[0] for p in pts]
    return min(xs), max(xs)


@dataclass
class Path_:
    """One jump path in the canonical frame (the hero starts at x 0 on the floor, 'toward' = -x)."""
    h: int                    # jump held frames
    a: int                    # frames from the jump's first frame to the press frame
    pre: int                  # horizontal before the press: +1 toward, 0 none, -1 away
    post: int                 # horizontal from the press on
    jpost: int                # jump held again from the press + 3 for 16 frames (the bounce's extension)
    masks: np.ndarray
    facing: int               # the hero's facing at the press (canonical frame: toward = -1)


class SlamTheory:
    T_AFTER = 75              # frames checked after the press

    def __init__(self, params: kin.HeroParams, terrain: kin.Terrain2D | None = None, alt: bool = False,
                 ev_off: int = 0):
        self.params = params
        self.terrain = terrain
        self.alt = alt
        self.ev_off = ev_off

    def paths(self, hs=(1, 3, 5, 7, 9, 11, 13, 16, 20), as_=range(3, 41), pres=(1, 0, -1), posts=(1, 0, -1),
              jposts=(0, 1)) -> list[Path_]:
        out = []
        for h, a, pre, post, jp in itertools.product(hs, as_, pres, posts, jposts):
            T = a + 1 + self.T_AFTER
            m = np.zeros(T, np.int64)
            m[:h] |= M_J
            hm = {1: M_L, -1: M_R, 0: 0}
            m[:a] |= hm[pre]
            m[a:] |= hm[post]
            m[max(a - 3, 0):a + 3] |= M_D
            m[a] |= M_A
            if jp:
                m[a + 3:a + 19] |= M_J
            face = -1 if (post == 1 or (post == 0 and pre >= 0)) else 1
            if post == 0 and pre == -1:
                face = 1
            out.append(Path_(h, a, pre, post, jp, m, face))
        return out

    def _roll(self, masks: np.ndarray, events: np.ndarray | None = None) -> kin.Rollout:
        x = CX + 5.0
        S = kin.initial_state(self.params, x, FLOOR_Y + HERO_STAND_DY, facing=-1, ground=True)
        return kin.rollout(S, masks, self.params, self.terrain, events=events)

    def grid(self, tl: SlamTimeline, x0s: np.ndarray, taus: np.ndarray, paths: list[Path_] | None = None,
             acc=None) -> "GridAcc":
        """Every path x jump frame tau (the jump's first frame, from the antic entry) x start x0 (the hero's x at the
        jump relative to the Clapper's antic-entry position, in its facing frame; x0 >= 0 in front: 'toward' = -x,
        x0 < 0 behind: the path mirrored). Accumulates the outcome by the state at the press."""
        paths = self.paths() if paths is None else paths
        acc = acc or GridAcc()
        cy = tl.pos_y + FLOOR_Y                 # the Clapper's position y
        x0s = np.asarray(x0s, float)
        taus = np.asarray(taus, int)
        miss = self.miss_rollouts(paths)             # one batch: the miss branch of every path
        for side in (1, -1):
            xs = x0s[x0s >= 0] if side == 1 else x0s[x0s < 0]
            if not len(xs):
                continue
            for i, p in enumerate(paths):
                o = self.cells(tl, p, miss, i, side, xs, taus, cy)
                acc.add(p, side, o["kp"], o["dxp"], o["dyp"], o["vyp"], o["contact"], o["hit_bad"], o["miss_bad"],
                        o["valid"])
        return acc

    def miss_rollouts(self, paths: list[Path_]) -> kin.Rollout:
        T = max(len(p.masks) for p in paths)
        M = np.zeros((len(paths), T), np.int64)
        for i, p in enumerate(paths):
            M[i, :len(p.masks)] = p.masks
            M[i, len(p.masks):] = p.masks[-1] & ~(M_A | M_J)
        S = kin.initial_state(self.params, CX + 5.0, FLOOR_Y + HERO_STAND_DY, facing=-1, ground=True)
        return kin.rollout(S, M, self.params, self.terrain, threads=4)

    def cells(self, tl, p: Path_, miss: kin.Rollout, i: int, side: int, xs, taus, cy) -> dict:
        """side +1: the hero in front (canonical, toward = -x); -1: behind (mirrored: toward = +x)."""
        pj = p.a + 1                                   # rollout index of the press frame
        fl = miss.flags[i]
        pos = miss.pos[i] - np.array([CX + 5.0, 0.0])  # relative to the jump start
        box = miss.box[i] - np.array([CX + 5.0, 0.0, CX + 5.0, 0.0])
        if side == -1:
            pos = pos * np.array([-1.0, 1.0])
            box = np.stack([-box[:, 2], box[:, 1], -box[:, 0], box[:, 3]], axis=1)
        face = p.facing * side
        swung = bool(((fl[pj:pj + 2] & kin.F_ATTACKING) != 0).any()) and not bool(fl[pj - 1] & kin.F_GROUND)
        g = np.flatnonzero((fl[pj:] & kin.F_GROUND) != 0)
        last = pj + int(g[0]) - 1 if len(g) else len(fl) - 1
        land = pj + int(g[0]) if len(g) else len(fl) - 1
        n_t, n_x = len(taus), len(xs)
        X = xs[None, :]
        k_of = lambda j: taus[:, None] + (j - 1)        # noqa: E731  the slam frame of rollout index j
        contact = np.full((n_t, n_x), -1, np.int64)
        if swung:
            sp = slash_poly(face, self.alt)
            for j in range(pj + ACTIVE[0], min(pj + ACTIVE[1], last) + 1):
                k = np.clip(k_of(j), 0, len(tl.state) - 1)[:, 0]
                rb = tl.world(k)                         # [n_t, 4]
                # the slash polygon clipped to each frame's root y band (few distinct bands)
                lo = np.full(n_t, np.inf)
                hi = np.full(n_t, -np.inf)
                for band in {(b[2], b[3]) for b in map(tuple, rb)}:
                    r = clip_band(sp + pos[j], cy + band[0], cy + band[1])
                    if r is None:
                        continue
                    sel = (rb[:, 2] == band[0]) & (rb[:, 3] == band[1])
                    lo[sel] = rb[sel, 0] - r[1]
                    hi[sel] = rb[sel, 1] - r[0]
                hit = (X > lo[:, None]) & (X < hi[:, None]) & (contact < 0) & (k_of(j) >= 0)
                contact[hit] = j
        # the press state relative to the Clapper's position at the press
        kp = np.clip(taus + p.a, 0, len(tl.state) - 1)
        dxp = X + pos[pj, 0] - tl.disp[kp][:, None]
        dyp = pos[pj, 1] - cy
        vyp = float(miss.vel[i, pj, 1])
        valid = (taus + p.a >= 0)[:, None] & np.ones((1, n_x), bool) & swung
        # the miss branch: the hammer and the body, no i-frames, from the press to the landing
        miss_first = self._damage(tl, box, fl, pj, land, taus, X, cy, None)
        miss_bad = miss_first < BIG
        # a hit before the contact (and its PRE_PROTECT_F frames) cancels the slash
        contact[(contact >= 0) & (miss_first < contact - PRE_PROTECT_F)] = -1
        hit_bad = np.zeros((n_t, n_x), bool)
        for jc in np.unique(contact[contact >= 0]):
            ev = np.zeros((1, len(p.masks)), np.int64)
            ev[0, min(max(jc - 1 + self.ev_off, 0), len(p.masks) - 1)] = kin.EV_POGO
            hr = self._roll(p.masks, ev)
            hb = hr.box[0] - np.array([CX + 5.0, 0.0, CX + 5.0, 0.0])
            if side == -1:
                hb = np.stack([-hb[:, 2], hb[:, 1], -hb[:, 0], hb[:, 3]], axis=1)
            hfl = hr.flags[0]
            gg = np.flatnonzero((hfl[jc + 1:] & kin.F_GROUND) != 0)
            hland = jc + 1 + int(gg[0]) if len(gg) else len(hfl) - 1
            bad = self._damage(tl, hb, hfl, pj, hland, taus, X, cy, jc) < BIG
            sel = contact == jc
            hit_bad[sel] = bad[sel]
        return {"kp": taus + p.a, "dxp": dxp, "dyp": dyp, "vyp": vyp, "contact": contact, "hit_bad": hit_bad,
                "miss_bad": miss_bad, "valid": valid, "contact_k": np.where(contact >= 0, taus[:, None] + contact - 1, -1)}

    def _damage(self, tl, box, fl, j0, j1, taus, X, cy, contact_j) -> np.ndarray:
        """[n_t, n_x]: the first frame j0..j1 on which the hero's box (relative x, absolute y) meets the hammer or the
        body while not invulnerable (BIG: none); with contact_j the body is off from the contact for BODY_COOLDOWN_F
        frames."""
        n_t = len(taus)
        first = np.full((n_t, X.shape[1]), BIG, np.int64)
        for j in range(j0, min(j1, len(fl) - 1) + 1):
            if fl[j] & kin.F_INVULN:
                continue
            if contact_j is not None and contact_j - PRE_PROTECT_F <= j < contact_j:
                continue
            k = taus + (j - 1)
            ok = k >= 0
            kc = np.clip(k, 0, len(tl.state) - 1)
            hx0, hy0, hx1, hy1 = box[j]
            for which in ("hammer", "root"):
                if which == "root" and contact_j is not None and 0 <= j - contact_j < BODY_COOLDOWN_F:
                    continue
                b = tl.world(kc, which)
                yov = (b[:, 2] + cy < hy1) & (b[:, 3] + cy > hy0) & ok & np.isfinite(b[:, 0])
                if not yov.any():
                    continue
                lo = b[:, 0] - hx1
                hi = b[:, 1] - hx0
                m = yov[:, None] & (X > lo[:, None]) & (X < hi[:, None]) & (first == BIG)
                first[m] = j
        return first


class GridAcc:
    """Counts by the press state: slam frame of the press (0..KP), dx (0.25 u bins, -6..10), dy (0.25 u, -4..6), vy
    class (rising > 3, apex, falling < -3 u/s), the side (front / behind at the jump), post horizontal (toward /
    none / away) and the jump held after the press; the outcomes: n, bounce, bounce + hit branch safe, miss branch
    safe, bounce + both safe; and the contact's slam frame sums for the mean."""
    KP, DX0, DX1, DY0, DY1, B = 100, -6.0, 10.0, -4.0, 6.0, 0.25

    def __init__(self):
        self.nx = int(round((self.DX1 - self.DX0) / self.B))
        self.ny = int(round((self.DY1 - self.DY0) / self.B))
        self.shape = (self.KP, self.nx, self.ny, 3, 2, 3, 2)
        self.c = np.zeros((5,) + self.shape, np.int32)

    def add(self, p: Path_, side, kp, dxp, dyp, vyp, contact, hit_bad, miss_bad, valid):
        kpb = np.broadcast_to(kp[:, None], dxp.shape)
        xi = np.floor((dxp - self.DX0) / self.B).astype(int)
        yi = int(np.floor((dyp - self.DY0) / self.B))
        ok = valid & (kpb >= 0) & (kpb < self.KP) & (xi >= 0) & (xi < self.nx) & (0 <= yi < self.ny)
        if not ok.any():
            return
        vc = 0 if vyp > 3 else (2 if vyp < -3 else 1)
        si = 0 if side == 1 else 1
        pi = {1: 0, 0: 1, -1: 2}[p.post]
        idx = (kpb[ok], xi[ok], yi, vc, si, pi, p.jpost)
        b = contact[ok] >= 0
        hs = b & ~hit_bad[ok]
        ms = ~miss_bad[ok]
        for c, v in enumerate((np.ones_like(b), b, hs, ms, hs & ms)):
            np.add.at(self.c[c], idx, v.astype(np.int32))

    def save(self, path: Path, meta: dict):
        np.savez_compressed(path, c=self.c, meta=json.dumps(meta | {"shape": self.shape, "KP": self.KP, "DX0": self.DX0,
                                                                     "DY0": self.DY0, "B": self.B}))




# ---- run time: a press now during a slam (the overlay's eye check; the special-move table's check) ----
SLAM_K0 = {"Slam Antic": 0, "Slam 0": 49, "Slam 1": 54, "Slam 2": 57, "Slam Recover": 63}
REGION = TEMPLATE.with_name("pogo_clapper_slam_region.npz")


def slam_frame(state: str | None, t_in: float) -> int | None:
    """The slam frame (from the antic entry, nominal timing) of a Clapper in Control state `state` for t_in s."""
    if state not in SLAM_K0:
        return None
    return SLAM_K0[state] + int(round(float(t_in) * 60))


def predict_press(params: kin.HeroParams, terrain, tl: SlamTimeline, k_now: int, cx_now: float, cy: float,
                  face: int, start: np.ndarray, masks: np.ndarray, facing: int, alt: bool = False) -> dict:
    """A down slash pressed on rollout index 1 (masks[0] holds down + attack) by a hero in model state `start`,
    against a Clapper at slam frame k_now (rollout index j <-> slam frame k_now + j), now at x cx_now (its position
    y cy) facing `face`: the miss branch, the contact on the predicted path (pogo_model's rule against the root box of
    each future frame), the bounce branch, and each branch's first hit (hammer or body, outside the i-frames and the
    PRE_PROTECT_F frames before the contact); world coordinates."""
    from ssbot.combat.pogo_model import ACTIVE, meets
    T = len(masks)
    x_anchor = cx_now - face * tl.disp[min(max(k_now, 0), len(tl.disp) - 1)]

    def wbox(k, which):
        b = tl.world(np.array([k]), which)[0]
        if not np.isfinite(b[0]):
            return None
        x0, x1 = sorted((x_anchor + face * b[0], x_anchor + face * b[1]))
        return np.array([x0, x1, cy + b[2], cy + b[3]])

    miss = kin.rollout(start, np.asarray(masks, np.int64)[None], params, terrain)
    fl = miss.flags[0]
    swung = bool(((fl[1:3] & kin.F_ATTACKING) != 0).any()) and not bool(fl[0] & kin.F_GROUND)
    g = np.flatnonzero((fl[1:] & kin.F_GROUND) != 0)
    last = int(g[0]) if len(g) else T
    sp = slash_poly(facing, alt)
    cj = -1
    if swung:
        for j in range(1 + ACTIVE[0], min(1 + ACTIVE[1], last) + 1):
            b = wbox(k_now + j - 1, "root")
            if b is not None and meets(sp + miss.pos[0, j], np.array([[b[0], b[2]], [b[1], b[2]], [b[1], b[3]], [b[0], b[3]]])):
                cj = j
                break

    def first_hit(ro, contact_j):
        f_ = ro.flags[0]
        for j in range(1, T + 1):
            if f_[j] & kin.F_INVULN:
                continue
            if contact_j is not None and contact_j - PRE_PROTECT_F <= j < contact_j:
                continue
            hx0, hy0, hx1, hy1 = ro.box[0, j]
            for which in ("hammer", "root"):
                b = wbox(k_now + j - 1, which)
                if b is not None and b[0] < hx1 and b[1] > hx0 and b[2] < hy1 and b[3] > hy0:
                    return j, which
        return -1, None

    mj, msrc = first_hit(miss, None)
    if cj >= 0 and 0 <= mj < cj - PRE_PROTECT_F:
        cj = -1
    out = {"miss": miss.pos[0].copy(), "miss_hit_j": mj, "miss_hit": msrc, "j": cj, "hit": None, "hit_hit_j": -1,
           "hit_hit": None, "inv": None, "kind": "hurtbox" if cj >= 0 else None}
    if cj >= 0:
        ev = np.zeros((1, T), np.int64)
        ev[0, cj - 1] = kin.EV_POGO
        hr = kin.rollout(start, np.asarray(masks, np.int64)[None], params, terrain, events=ev)
        out["hit"] = hr.pos[0].copy()
        out["inv"] = (hr.flags[0] & kin.F_INVULN) != 0
        out["hit_hit_j"], out["hit_hit"] = first_hit(hr, cj)
        out["slash"] = sp + miss.pos[0, cj]
    return out


def build_region(npz_paths: list[Path], out: Path = REGION) -> dict:
    """The success region table from GridAcc grids of several timing variants: per (press frame, dx, dy, vy class)
    the share of the theory's paths through that cell whose down slash bounces with both branches safe ('success',
    the locked-move rule), that bounces with the bounce branch safe ('hit': the strike works, its miss branch may not
    be safe) and that bounces ('bounce'), each for the best held direction / jump after the press, the minimum over
    the variants (robust)."""
    best_s, best_b, best_h, meta = None, None, None, None
    for p in npz_paths:
        z = np.load(p, allow_pickle=False)
        c = z["c"].astype(np.float64)                 # [5, KP, nx, ny, vc, side, post, jpost]
        meta = json.loads(str(z["meta"]))
        n = c[0].sum(axis=4)                          # over the side
        succ = np.where(n > 0, c[4].sum(axis=4) / np.maximum(n, 1), 0.0)
        bounce = np.where(n > 0, c[1].sum(axis=4) / np.maximum(n, 1), 0.0)
        hit = np.where(n > 0, c[2].sum(axis=4) / np.maximum(n, 1), 0.0)
        s_ = succ.max(axis=(4, 5))                    # the best post / jpost
        b_ = bounce.max(axis=(4, 5))
        h_ = hit.max(axis=(4, 5))
        best_s = s_ if best_s is None else np.minimum(best_s, s_)
        best_b = b_ if best_b is None else np.minimum(best_b, b_)
        best_h = h_ if best_h is None else np.minimum(best_h, h_)
    np.savez_compressed(out, success=np.round(best_s * 100).astype(np.uint8), bounce=np.round(best_b * 100).astype(np.uint8),
                        hit=np.round(best_h * 100).astype(np.uint8),
                        meta=json.dumps({k: meta[k] for k in ("KP", "DX0", "DY0", "B")} | {"variants": len(npz_paths)}))
    return {"cells_success_50": int((best_s >= 0.5).sum()), "cells_hit_50": int((best_h >= 0.5).sum()),
            "cells_bounce_50": int((best_b >= 0.5).sum())}


class Region:
    """The success region table at run time: cells (dx along the Clapper's facing from its position, dy from its
    position) where a press at slam frame k with the hero's vy class succeeds."""

    def __init__(self, path: Path = REGION):
        z = np.load(path, allow_pickle=False)
        self.success = z["success"]
        self.bounce = z["bounce"]
        self.hit = z["hit"]
        m = json.loads(str(z["meta"]))
        self.DX0, self.DY0, self.B, self.KP = m["DX0"], m["DY0"], m["B"], m["KP"]

    def cells(self, k: int, vy: float, thr: int = 50, which: str = "success") -> list[tuple[float, float, int]]:
        if not (0 <= k < self.KP):
            return []
        vc = 0 if vy > 3 else (2 if vy < -3 else 1)
        a = {"success": self.success, "hit": self.hit, "bounce": self.bounce}[which][k, :, :, vc]
        xi, yi = np.nonzero(a >= thr)
        return [(self.DX0 + x * self.B, self.DY0 + y * self.B, int(a[x, y])) for x, y in zip(xi, yi)]


__all__ = ["SlamTimeline", "SlamTheory", "GridAcc", "clip_band", "TEMPLATE", "BODY_COOLDOWN_F", "HERO_STAND_DY",
           "FLOOR_Y", "CX", "PRE_PROTECT_F", "SLAM_K0", "slam_frame", "predict_press", "build_region", "Region",
           "REGION"]
