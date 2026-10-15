"""The one-step lookahead on a special map (task 1v1 SG3; the person's online rule S8, spec_notes_zh parts 82 / 85 / 94;
forum.md 57). Pure and planner-independent: (hero state, move frame, enemy pose) -> the input for the next frame and
its score. It reads a ValueSource: SG2's dense pass (DenseSource), the same values cut to score bands (BandedSource,
the reference of the contours) or the contour store (ContourSource, ssbot.combat.score_contours).

The rule (identical to SG2's closed-loop policy, ssbot.tools.sg2_sim): step the hero model by one frame for each input
possible now (left / none / right, a ground jump with hold h, the down slash), read the next node's score, subtract
lambda per key change, take the best:
  * on the ground: per key d the ground value two frames ahead (the key read now moves the body in the frame after
    next; the current key moves it next frame), or a jump pressed next frame if its value exceeds the clearance-only
    score WC (a reachable strike: never jump without one); a jump now with hold h: the best key for its first move,
    bounded by the jump start's own score (which holds the late-jump robustness);
  * in the air: per key d the event's value two frames ahead, or the strike pressed from the next node with that key
    held (input latency: the key read now is the key the strike holds); the slash now when the strike with the
    current key is (within 0.01) the node's best continuation (the press flag) and the cooldown (19 frames from the
    last press) has run out;
  * nothing feasible: retreat on the ground (away from the enemy), keep the key in the air.
Map coordinates: x = hero box centre minus the enemy's position at the antic entry (k = 0), along the enemy's facing
(u, centre to centre); d = +1 moves toward the enemy's front. The map is per physics phase p: frame k has a 50 Hz step
iff (k - p) % 6 != 0 (frame 0 counts none).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ssbot.combat import score_contours as sc

PRESS_COOL = 19                   # frames from one press to the next (hero_macros.COOLDOWN_F)
PRESS_EPS = 1e-2                  # the strike is the node's best continuation within this


def steps(p: int, K: int) -> np.ndarray:
    k = np.arange(K + 16)
    s = ((k - p) % 6 != 0).astype(np.int64)
    s[0] = 0
    return s


@dataclass
class TubeIndex:
    """The map's macro states: per tube (ground, jump hold h, bounce contact-height bin) its first slice and length,
    the landing index per start cycle; the lattice."""
    kinds: list
    params: list
    s0: list
    n: list
    L: list
    cb_w: float
    ncb: int
    x_lo: float
    step: float
    NX: int
    K: int
    wc: float
    NS: int = 0
    jump_h: list = field(default_factory=list)
    s0_of: dict = field(default_factory=dict)
    bounce_t: list = field(default_factory=list)

    def __post_init__(self):
        self.NS = int(sum(self.n))
        self.jump_h = [p for kd, p in zip(self.kinds, self.params) if kd == "jump"]
        self.s0_of = {p: s for kd, p, s in zip(self.kinds, self.params, self.s0) if kd == "jump"}
        self._jt = {p: i for i, (kd, p) in enumerate(zip(self.kinds, self.params)) if kd == "jump"}
        self.bounce_t = [i for i, kd in enumerate(self.kinds) if kd == "bounce"]
        self.ST = np.concatenate([np.full(n, i) for i, n in enumerate(self.n)]).astype(np.int64)    # slice -> tube
        self.SJ = np.concatenate([np.arange(n) for n in self.n]).astype(np.int64)                   # slice -> j
        self.LA = np.array(self.L, np.int64)                                                         # [tube, q]

    def valid_rows(self, p: int, s: int) -> np.ndarray:
        """[K] frames k at which slice s is a state (the event started at k - j with start cycle q = (p - k + j) % 6
        has not landed: j < L[tube, q]); the ground slice always."""
        k = np.arange(self.K)
        j = self.SJ[s]
        if self.kinds[self.ST[s]] == "ground":
            return np.ones(self.K, bool)
        return j < self.LA[self.ST[s], (p - k + j) % 6]

    def valid(self, p: int, k: int, s: int) -> bool:
        if s <= 0:
            return s == 0
        j = int(self.SJ[s])
        return j < self.LA[self.ST[s], (p - k + j) % 6]

    @classmethod
    def from_geometry(cls, geo) -> "TubeIndex":
        t = geo.tubes
        return cls([x.kind for x in t], [float(x.param) for x in t], [int(x.s0) for x in t], [int(x.n) for x in t],
                   [x.L.astype(int).tolist() for x in t], float(geo.cfg.cb_w), int(geo.ncb), float(geo.cfg.x_lo),
                   float(geo.step), int(geo.NX), int(geo.K), float(geo.cfg.wc))

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in ("kinds", "params", "s0", "n", "L", "cb_w", "ncb", "x_lo", "step", "NX",
                                              "K", "wc")}

    @classmethod
    def from_dict(cls, d: dict) -> "TubeIndex":
        return cls(**d)

    def slice_of(self, ev: dict, j: int) -> int:
        if ev["kind"] == "ground":
            return 0
        if ev["kind"] == "jump":
            ti = self._jt[float(ev["h"])]
        else:
            cb = int(np.clip(np.floor(ev["yc"] / self.cb_w), 0, self.ncb - 1))
            ti = self.bounce_t[cb]
        return self.s0[ti] + j if j < self.n[ti] else -1

    def xi(self, x: float) -> int:
        return int(np.rint((x - self.x_lo) / self.step))


class DenseSource:
    """SG2's per-frame values of one phase (PhaseMap with keep_full): S [K, NS, NX], SV [K, NS, NX, 3]."""
    kind = "dense"

    def __init__(self, pm, ti: TubeIndex):
        self.p, self.ti = pm.p, ti
        self.st = steps(pm.p, ti.K)
        self._S, self._SV = pm.S, pm.SV

    def _ok(self, k, s, x):
        if s < 0 or not 0 <= k < self.ti.K:
            return -1
        xi = self.ti.xi(x)
        return xi if 0 <= xi < self.ti.NX else -1

    def S(self, k: int, s: int, x: float) -> float:
        xi = self._ok(k, s, x)
        return -np.inf if xi < 0 else float(self._S[k, s, xi])

    def SV(self, k: int, s: int, x: float, d: int) -> float:
        xi = self._ok(k, s, x)
        return -np.inf if xi < 0 else float(self._SV[k, s, xi, d + 1])

    def press(self, k: int, s: int, x: float, d: int) -> bool:
        sv = DenseSource.SV(self, k, s, x, d)
        return bool(np.isfinite(sv) and sv >= DenseSource.S(self, k, s, x) - PRESS_EPS)


def band_value(v: float, step: float) -> float:
    """The lower edge of v's score band (sc.to_bands); -inf stays."""
    if not np.isfinite(v):
        return -np.inf
    return float(np.floor(max(v, 0.0) / step + 1e-9)) * step


class BandedSource(DenseSource):
    """The dense values cut to the contour bands (lower band edge), exact on the lattice: what the contours store
    before the simplification's +-1 band. The press flag stays exact (it is a binary layer)."""
    kind = "banded"

    def __init__(self, pm, ti: TubeIndex, step: float):
        super().__init__(pm, ti)
        self.step = step

    def S(self, k, s, x):
        return band_value(super().S(k, s, x), self.step)

    def SV(self, k, s, x, d):
        return band_value(super().SV(k, s, x, d), self.step)


class ContourSource:
    """One phase's tube layers from the contour store (score_contours_build: layers S/<s>, SV<d+1>/<s>, P<d+1>/<s>;
    a missing layer is all infeasible; the rows at which a slice is no state were filled before contouring and read
    as infeasible here, as in the dense pass). Values are the lower band edges."""
    kind = "contour"

    def __init__(self, cs: sc.ContourSet, ti: TubeIndex, p: int):
        self.p, self.ti, self.cs = p, ti, cs
        self.step = cs.step
        self.st = steps(p, ti.K)
        self.L = cs.layers
        self.nq = 0

    def _band(self, name: str, k: int, x: float, s: int) -> int:
        lay = self.L.get(name)
        if lay is None or not self.ti.valid(self.p, k, s):        # filled rows (no state there) are not the layer
            return -1
        self.nq += 1
        return lay.query(k, self.ti.xi(x))

    def S(self, k, s, x):
        if s < 0:
            return -np.inf
        b = self._band(f"S/{s}", k, x, s)
        return -np.inf if b < 0 else b * self.step

    def SV(self, k, s, x, d):
        if s < 0:
            return -np.inf
        b = self._band(f"SV{d + 1}/{s}", k, x, s)
        return -np.inf if b < 0 else b * self.step

    def press(self, k, s, x, d):
        return s >= 0 and self._band(f"P{d + 1}/{s}", k, x, s) >= 0


def decide(src, k: int, ev: dict, x: float, dir_cur: int, last_press: int, lam: float, land: int | None = None):
    """The lookahead at the end of frame k (inputs for frame k + 1). ev: the hero's vertical event {"kind": ground |
    jump | bounce, "k": its start frame, "h": jump hold, "yc": bounce contact height}; land: the event's landing index
    (frames from its start; from the hero model, needed in the air). Returns (value, action, candidates); action =
    ("dir", d) | ("jump", h, d) | ("press", d)."""
    ti, st = src.ti, src.st
    j = k - ev["k"]
    s_now = ti.slice_of(ev, j) if ev["kind"] != "ground" else 0
    x1 = x + dir_cur * ti.step * st[k + 1]
    cands = []
    if ev["kind"] == "ground":
        for d in (-1, 0, 1):
            x2 = x1 + d * ti.step * st[k + 2]
            v = src.S(k + 2, 0, x2)
            # a jump pressed next frame (node k + 1) makes its first move with the key read now
            for h in ti.jump_h:
                s0 = ti.s0_of[h]
                vj = min(src.S(k + 2, s0 + 1, x2), src.S(k + 1, s0, x1))
                if vj > ti.wc + 1e-3:
                    v = max(v, vj)
            cands.append((v - lam * (d != dir_cur), ("dir", d)))
        for h in ti.jump_h:
            s0 = ti.s0_of[h]
            best, bd = -np.inf, dir_cur
            for d in (-1, 0, 1):
                x2 = x1 + d * ti.step * st[k + 2]
                v = src.S(k + 2, s0 + 2, x2) - lam * (d != dir_cur)
                if v > best:
                    best, bd = v, d
            best = min(best, src.S(k, s0, x))        # the start's own score: the same jump one frame later too
            if best > ti.wc + 1e-3:                  # a reachable strike: never jump without one
                cands.append((best - lam, ("jump", h, bd)))
    else:
        s1 = ti.slice_of(ev, j + 1) if j + 1 < land else -1
        for d in (-1, 0, 1):
            x2 = x1 + d * ti.step * st[k + 2]
            s2 = ti.slice_of(ev, j + 2) if j + 2 < land else 0
            v = src.S(k + 2, s2, x2)
            if s1 >= 0 and k + 2 - last_press >= PRESS_COOL:
                v = max(v, src.SV(k + 1, s1, x1, d))
            cands.append((v - lam * (d != dir_cur), ("dir", d)))
        if k + 1 - last_press >= PRESS_COOL and s_now >= 0 and src.press(k, s_now, x, dir_cur):
            cands.append((np.inf, ("press", dir_cur)))
    v, act = max(cands, key=lambda c: c[0])
    if not np.isfinite(v) and v < 0:                 # nothing feasible: retreat on the ground, keep the key in the air
        act = ("dir", 1 if x >= 0 else -1) if ev["kind"] == "ground" else ("dir", dir_cur)
    return v, act, cands


# ---- the world-frame interface (what the Forum planner would call) ----
@dataclass
class HeroState:
    x: float                       # hero box centre x (world u)
    key: int = 0                   # the direction key read this frame (world: -1 left, +1 right)
    kind: str = "ground"           # ground | jump | bounce (the vertical event the hero is in)
    j: int = 0                     # frames since that event started
    h: float = 0.0                 # jump: the jump key hold (frames)
    yc: float = 0.0                # bounce: the hero box bottom above the floor at the contact (u)
    land: int | None = None        # the event's landing index (frames from its start; hero model)
    last_press_k: int = -100       # move frame of the last slash press


@dataclass
class EnemyPose:
    x0: float                      # the enemy's centre x at the antic entry (k = 0) (world u)
    facing: int                    # +1 / -1
    k: int                         # frames since the antic entry (the move clock)


def to_map_x(hero_x: float, enemy: EnemyPose) -> float:
    return (hero_x - enemy.x0) * enemy.facing


def decide_world(src, hero: HeroState, enemy: EnemyPose, lam: float = 0.02) -> dict:
    """decide() in world coordinates: the returned keys are world keys (-1 left, +1 right)."""
    f = 1 if enemy.facing >= 0 else -1
    ev = {"kind": hero.kind, "k": enemy.k - hero.j, "h": hero.h, "yc": hero.yc}
    v, act, cands = decide(src, enemy.k, ev, to_map_x(hero.x, enemy), hero.key * f, hero.last_press_k, lam, hero.land)

    def w(a):
        return (a[0], a[1], a[2] * f) if a[0] == "jump" else (a[0], a[1] * f)
    return {"action": w(act), "value": float(v), "options": [(float(c[0]), w(c[1])) for c in cands]}


def readiness(src, x: float, ev: dict | None = None) -> float:
    """The map's score at the antic entry (k = 0) for a hero at map x: the ground layer, or the airborne event's
    slice (ev with its start frame <= 0). -inf: no safe continuation; <= WC: no reachable strike."""
    if ev is None or ev["kind"] == "ground":
        return src.S(0, 0, x)
    return src.S(0, src.ti.slice_of(ev, -ev["k"]), x)


def load_contour_source(path: Path, p: int) -> ContourSource:
    cs = sc.ContourSet.load(path)
    return ContourSource(cs, TubeIndex.from_dict(cs.meta["tubes"]), p)


__all__ = ["TubeIndex", "DenseSource", "BandedSource", "ContourSource", "decide", "decide_world", "HeroState",
           "EnemyPose", "readiness", "steps", "band_value", "load_contour_source", "to_map_x", "PRESS_COOL"]
