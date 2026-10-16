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
    current key is (within 0.01) the node's best continuation (the press flag) or (SG3b) at least the best
    continuation without it given the key already read (committed), and the cooldown (19 frames from the last
    press) has run out; equal values go to the current key (lambda), then to the key whose value is the earlier
    strike (SG3b tie rule);
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
TIE_EPS = 0.0                     # > 0: equal values in the air -> the key whose value is the earlier strike (SG3b
                                  # tried 1e-9; see forum.md 58)
PRESS_COMMITTED = True            # SG3b: also slash when the strike beats every continuation with the committed key


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
    as infeasible here, as in the dense pass). Values are the lower band edges: band x step (SG3's fixed steps) or,
    for an equal-area file (SG3b, meta.banding), the band's lower edge from the file's edges (per frame or per
    layer; band 0: 0.0)."""
    kind = "contour"

    def __init__(self, cs: sc.ContourSet, ti: TubeIndex, p: int):
        self.p, self.ti, self.cs = p, ti, cs
        self.step = cs.step
        self.st = steps(p, ti.K)
        self.L = cs.layers
        self.nq = 0
        bd = cs.meta.get("banding", {"mode": "step"})
        self.mode = bd.get("mode", "step")
        self.scope = bd.get("scope")
        self._fv, self._lv = None, None
        if self.mode == "equal_area":                 # SG3b: a band stands for its lower edge
            if self.scope == "frame":
                self._fv = sc.edge_values(cs.arrays[f"edges_{p}"])                        # [K, n]
            else:
                E = sc.edge_values(cs.arrays["edges"])                                    # [layer, n]
                self._lv = {nm: E[i] for i, nm in enumerate(cs.meta["names"])}

    def value(self, name: str, k: int, b: int) -> float:
        """The score a band stands for (its lower edge); -inf for -1."""
        if b < 0:
            return -np.inf
        if self._fv is not None:
            return float(self._fv[k, b])
        if self._lv is not None:
            return float(self._lv[name][b])
        return b * self.step

    def _band(self, name: str, k: int, x: float, s: int) -> int:
        lay = self.L.get(name)
        if lay is None or not self.ti.valid(self.p, k, s):        # filled rows (no state there) are not the layer
            return -1
        self.nq += 1
        return lay.query(k, self.ti.xi(x))

    def S(self, k, s, x):
        if s < 0:
            return -np.inf
        nm = f"S/{s}"
        return self.value(nm, k, self._band(nm, k, x, s))

    def SV(self, k, s, x, d):
        if s < 0:
            return -np.inf
        nm = f"SV{d + 1}/{s}"
        return self.value(nm, k, self._band(nm, k, x, s))

    def press(self, k, s, x, d):
        return s >= 0 and self._band(f"P{d + 1}/{s}", k, x, s) >= 0


class KeyedDenseSource:
    """SG4: a keyed map's per-frame values of one phase (special_map.KeyedMapBuilder with keep_full): S [K, 3, NS, NX]
    (the state's key c: the key already read, moving the body in the next frame), SV [K, NS, NX, 3] (the slash pressed
    next frame with the key d held = the state's key). noise: the map's key_noise and p_late (decide_keyed weighs the
    late branches the same way)."""
    kind = "keyed_dense"
    keyed = True

    def __init__(self, pm, ti: TubeIndex, cfg, rm: np.ndarray | None = None):
        self.p, self.ti = pm.p, ti
        self.st = steps(pm.p, ti.K)
        self._S, self._SV = pm.S, pm.SV
        self.mode = cfg.key_noise
        pl = np.asarray(cfg.p_late, float)
        self.pl = pl / pl.sum()
        self.gamma = float(cfg.gamma)
        self.nq = 0
        # SG7 stage maps: frame k -> the row of the arrays (one variant's path; -1 = none); plain maps: the frame
        self.rm = np.arange(ti.K + 16) if rm is None else np.asarray(rm, np.int64)

    def with_rows(self, rm: np.ndarray) -> "KeyedDenseSource":
        import copy
        o = copy.copy(self)
        o.rm = np.asarray(rm, np.int64)
        return o

    def _xi(self, k, s, x):
        if s < 0 or not 0 <= k < self.ti.K or self.rm[k] < 0:
            return -1
        xi = self.ti.xi(x)
        return xi if 0 <= xi < self.ti.NX else -1

    def S(self, k: int, s: int, x: float, c: int = 0) -> float:
        xi = self._xi(k, s, x)
        self.nq += 1
        return -np.inf if xi < 0 else float(self._S[self.rm[k], c + 1, s, xi])

    def Smax(self, k: int, s: int, x: float) -> float:
        xi = self._xi(k, s, x)
        self.nq += 1
        return -np.inf if xi < 0 else float(self._S[self.rm[k], :, s, xi].max())

    def SV(self, k: int, s: int, x: float, d: int) -> float:
        xi = self._xi(k, s, x)
        self.nq += 1
        return -np.inf if xi < 0 else float(self._SV[self.rm[k], s, xi, d + 1])


def keyed_q(src, k: int, s1: int, x1: float, c: int, d: int, nexts) -> float:
    """The value of reading key d in frame k + 1 from a state whose key c moves the body in frame k + 1 (the hero at
    x1 after that move, in slice s1 at k + 1): on time the state (k + 1, s1, x1, d); late by m frames c moves the body
    m more frames (the intermediate nodes must be feasible) and the state is (k + 1 + m, s_m, x_m, d). nexts(m) -> the
    slice at k + 1 + m. The map's key_noise weighs the branches (exp: a branch through damage counts 0; hard: the +1
    branch must be feasible, the worse of both)."""
    v1 = src.S(k + 1, s1, x1, d)
    if d == c or src.mode == "none" or not np.isfinite(v1):
        return v1
    br = []
    ok = src.Smax(k + 1, s1, x1) > -np.inf
    x, s = x1, s1
    g = src.gamma
    for m in (1, 2, 3):
        if not ok:
            br.append(-np.inf)
            continue
        x = x + c * src.ti.step * src.st[k + 1 + m]
        s = nexts(m)
        v = src.S(k + 1 + m, s, x, d) if s >= 0 else -np.inf
        br.append(g ** m * v if np.isfinite(v) else -np.inf)
        if m < 3:
            ok = s >= 0 and src.Smax(k + 1 + m, s, x) > -np.inf
    pl = src.pl
    if src.mode == "hard":
        return min(v1, br[0])
    if src.mode == "hard2":                         # SG7: the +1 and +2 late branches both feasible
        return min(v1, br[0], br[1])
    z = [b if np.isfinite(b) else 0.0 for b in br]
    if src.mode == "exp":
        return pl[0] * v1 + pl[1] * z[0] + pl[2] * z[1] + pl[3] * z[2]
    if not np.isfinite(br[0]):                      # hard_exp
        return -np.inf
    return pl[0] * v1 + pl[1] * br[0] + pl[2] * z[1] + pl[3] * z[2]


def decide_keyed(src, k: int, ev: dict, x: float, dir_cur: int, last_press: int, lam: float, land: int | None = None):
    """decide() on a keyed map (SG4): the state's key is dir_cur. In the air: the slash now when the map's node takes
    the strike with the held key (SV at least the node's value) and the cooldown is over; else the key d for frame
    k + 1 by keyed_q - lambda per change. On the ground: the key d, or a ground jump with hold h now (the start slice's
    value with the late-jump rule, only above the clearance-only score WC: a reachable strike) with its first-move key.
    Nothing feasible: retreat on the ground (away from the enemy), keep the key in the air."""
    ti, st = src.ti, src.st
    c = dir_cur
    j = k - ev["k"]
    x1 = x + c * ti.step * st[k + 1]
    cands = []

    def nexts_of(ev_, j_):
        def f(m):
            if ev_["kind"] == "ground":
                return 0
            jj = j_ + 1 + m
            return ti.slice_of(ev_, jj) if (land is None or jj < land) else 0
        return f

    if ev["kind"] == "ground":
        for d in (-1, 0, 1):
            v = keyed_q(src, k, 0, x1, c, d, nexts_of(ev, j))
            cands.append((v - lam * (d != c), ("dir", d)))
        # the jump starts: the start slice's value at k (with the late jump) bounds the candidate, so the holds are
        # tried best first and a hold that cannot beat the best candidate so far is skipped (exact up to ties)
        v0s = [(src.S(k, ti.s0_of[h], x, c), i, h) for i, h in enumerate(ti.jump_h)]
        top = max(v for v, _ in cands)
        jc = []
        for v0, i, h in sorted(v0s, key=lambda t: (-t[0], t[1])):
            if not v0 > ti.wc + 1e-3 or v0 - lam <= top:
                continue
            s0 = ti.s0_of[h]
            best, bd = -np.inf, c
            for d in (-1, 0, 1):
                v = keyed_q(src, k, s0 + 1, x1, c, d, lambda m, s0=s0: s0 + 1 + m) - lam * (d != c)
                if v > best:
                    best, bd = v, d
            cv = min(v0, best + lam * (bd != c)) - lam
            jc.append((i, (cv, ("jump", h, bd))))
            top = max(top, cv)
        cands.extend(c_ for _, c_ in sorted(jc, key=lambda t: t[0]))
    else:
        s_now = ti.slice_of(ev, j)
        if k + 1 - last_press >= PRESS_COOL and s_now >= 0:
            sv = src.SV(k, s_now, x, c)
            if np.isfinite(sv) and sv >= src.S(k, s_now, x, c) - 1e-3:
                cands.append((np.inf, ("press", c)))
        if not cands:
            s1 = ti.slice_of(ev, j + 1) if (land is None or j + 1 < land) else 0
            nf = nexts_of(ev, j)
            for d in (-1, 0, 1):
                v = keyed_q(src, k, s1, x1, c, d, nf)
                cands.append((v - lam * (d != c), ("dir", d)))
    v, act = max(cands, key=lambda cd: cd[0])
    if not np.isfinite(v) and v < 0:
        act = ("dir", 1 if x >= 0 else -1) if ev["kind"] == "ground" else ("dir", c)
    return v, act, cands


def decide(src, k: int, ev: dict, x: float, dir_cur: int, last_press: int, lam: float, land: int | None = None):
    """The lookahead at the end of frame k (inputs for frame k + 1). ev: the hero's vertical event {"kind": ground |
    jump | bounce, "k": its start frame, "h": jump hold, "yc": bounce contact height}; land: the event's landing index
    (frames from its start; from the hero model, needed in the air). Returns (value, action, candidates); action =
    ("dir", d) | ("jump", h, d) | ("press", d). A keyed source (SG4) goes to decide_keyed."""
    if getattr(src, "keyed", False):
        return decide_keyed(src, k, ev, x, dir_cur, last_press, lam, land)
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
        best_dir = -np.inf
        for d in (-1, 0, 1):
            x2 = x1 + d * ti.step * st[k + 2]
            s2 = ti.slice_of(ev, j + 2) if j + 2 < land else 0
            v = src.S(k + 2, s2, x2)
            tie = 0.0
            if s1 >= 0 and k + 2 - last_press >= PRESS_COOL:
                sv = src.SV(k + 1, s1, x1, d)
                if np.isfinite(sv) and sv >= v:
                    v, tie = sv, TIE_EPS           # TIE_EPS > 0: a tie goes to the key whose value is the earlier strike
            best_dir = max(best_dir, v)
            cands.append((v - lam * (d != dir_cur) + tie, ("dir", d)))
        if k + 1 - last_press >= PRESS_COOL and s_now >= 0:
            # the key read now (dir_cur) is committed: the slash now is right when it is the best continuation with
            # that key (the press flag compares it with S, the best over every key, which may need another key)
            # (strictly better than waiting: on a tie wait, the strike may come one frame later; an early strike's
            # value assumes a free key at its contact, which the held key may not have)
            sv_now = src.SV(k, s_now, x, dir_cur) if PRESS_COMMITTED else -np.inf
            if src.press(k, s_now, x, dir_cur) or (np.isfinite(sv_now) and sv_now > best_dir):
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
