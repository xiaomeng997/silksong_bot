"""The Choir Clapper's small runes (CC_CAST: Spell Antic -> Cast 1 -> Cast 2, a row of bombs falling in rings), task 1v1
G2 (forum.md sec. 50; the 2026-10-12 "why" study's fixes (5)-(9), docs/plans/forum_planner_plan.md).

Switches. Unset, every one follows SSBOT_FORUM_V2 (the person, 2026-10-15: the arm rn is the default): with v2 on,
NOPRE / BOMB / HOP / NOGLIDE are on and FACE is 3 u; without v2 all are off. Set to 0 (FACE=0: no cast stance), the
planner is 7f8bb7a's bit for bit (the arm fcs0 does that):
  SSBOT_FORUM_RUNE_NOPRE=1   no bomb forecast before Cast 2 is seen (attack_range.hazards_at drops the pending
                             CC_CAST instance's bombs). A Cast 2 entry seen without its CC_CAST instance (the Spell
                             Antic missed) still spawns the row (Segmenter.step). The cast is never cancelled by a hit
                             (forum.md 33.2) and the bombs are not drawn before Cast 2, so a cast cut short before it
                             leaves nothing behind; the jump cast (CC_JUMP_CAST) has no small bombs (its rune slam is
                             untouched).
  SSBOT_FORUM_RUNE_BOMB=1    the bombs in the planner's safety check from this per-bomb forecast (RuneBombs): every
                             bomb its own lit window, checked on every planner frame (not the SAMPLE_KS union), with
                             the margin SSBOT_FORUM_RUNE_BOMB_M (u, default 0.15) instead of the focus margin; the
                             table's ring windows of the spawned row leave the estimate (the pending row before
                             Cast 2 stays unless NOPRE).
  SSBOT_FORUM_RUNE_FACE=<u>  the L2 stance during CC_CAST: on the ground <u> from the Clapper, centre to centre (3 /
                             3.5: the live face_u A/B, 2026-10-12; 0: face_u as before G2).
  SSBOT_FORUM_RUNE_HOP=1     the person's rows: continuous slashes on the ground with one short hop timed from this
                             forecast so the hero is above the bomb that covers her when it lights; no second jump
                             press in the air (that opens the umbrella).
  SSBOT_FORUM_NOGLIDE=1      of the safe rows with the same landed hits, one without a glide (umbrella) first.

The row (forum.md 33.3; calibrated on the fcs replays' recordings, C:/ssbot/data/m2_special/g2/calib.txt, game time in
frames of 1/60 s): ring 0 appears at the Cast 2 entry (x of the Clapper then, y - 3.8), ring r's pair (x0 +- 4.2 r)
one step (9-10 frames) after ring r - 1; a bomb lights 20-21 frames after it appears and stays lit 5-7 frames. The
bomb pool sometimes serves one side of a pair late (or never): such a side is predicted only once it is seen. Once a
bomb is seen its own appearance times it; a ring not seen yet is timed from the latest ring seen. A ring that does not
appear in its window ends the row.
"""
from __future__ import annotations

import math
import os

import numpy as np

FT = 1.0 / 60.0
NAME = "rune bomb small"
CLAPPER = "Song Heavy Sentry"


RN_FACE_U = 3.0                   # the default cast stance under v2 (arm rn; the person chose it over 3.5 on 2026-10-15)


def switches(env=None) -> dict:
    """The switches from the environment. Unset, they follow SSBOT_FORUM_V2: on with v2 (the arm rn's values), off
    without it; "0" turns a flag off and SSBOT_FORUM_RUNE_FACE=0 drops the cast stance (face_u as before G2)."""
    env = os.environ if env is None else env
    v2 = env.get("SSBOT_FORUM_V2", "0").strip() == "1"

    def flag(name: str) -> bool:
        v = env.get(name, "").strip()
        return v2 if not v else v == "1"

    def num(name: str, default: float | None) -> float | None:
        v = env.get(name, "").strip()
        return default if not v else float(v)

    face = num("SSBOT_FORUM_RUNE_FACE", RN_FACE_U if v2 else None)
    return {"NOPRE": flag("SSBOT_FORUM_RUNE_NOPRE"), "BOMB": flag("SSBOT_FORUM_RUNE_BOMB"),
            "BOMB_M": num("SSBOT_FORUM_RUNE_BOMB_M", 0.15), "FACE_U": face if face else None,
            "HOP": flag("SSBOT_FORUM_RUNE_HOP"), "NOGLIDE": flag("SSBOT_FORUM_NOGLIDE")}


_SW = switches()
NOPRE = _SW["NOPRE"]
BOMB = _SW["BOMB"]
BOMB_M = _SW["BOMB_M"]
FACE_U = _SW["FACE_U"]
HOP = _SW["HOP"]
NOGLIDE = _SW["NOGLIDE"]
FORECAST = BOMB or HOP            # the tracker keeps a RuneBombs

R = 2.166                         # the bomb's circle collider
DX = 4.2                          # ring spacing
M_MAX = 9
DV = -3.8                         # centre y - the Clapper's y at Cast 2
# timing in frames of game time (C:/ssbot/data/m2_special/g2/calib.txt)
A0_F = (0.0, 1.0)                 # Cast 2 entry -> ring 0 appears
STEP_F = (9.0, 10.5)              # ring r - 1 -> ring r appears
LEAD_F = (19.5, 21.5)             # appears -> lights
DUR_F = 7.0                       # lit frames at most (5-7)
PAIR_F = 2.0                      # the other side of a ring seen: appears within this, else late (pool): not predicted
LATE_F = 3.0                      # a ring not seen this long after its window: the row has ended
TOL_X = 0.35                      # a bomb's x off its ring's x
HORIZON_S = 3.0                   # a row is dropped this long after its Cast 2


class _Bomb:
    __slots__ = ("x", "y", "a", "on", "last_lit", "last", "ended")

    def __init__(self, x: float, y: float, a: float):
        self.x, self.y, self.a = x, y, a
        self.on: float | None = None
        self.last_lit: float | None = None
        self.last = a                 # last seen
        self.ended = False


class _Row:
    def __init__(self, owner: int, t0: float, x0: float, y0: float, x_ok=None, synthetic: bool = False):
        self.owner, self.t0, self.x0, self.y0 = owner, t0, x0, y0
        self.x_ok = x_ok
        self.synthetic = synthetic
        self.seen: dict = {}          # m -> _Bomb
        self.ring_a: dict = {}        # ring -> its first appearance (game time)
        self.end_ring: int | None = None
        self.x0_seen = False


def bomb_ents(ents) -> list[tuple[int, float, float, bool]]:
    """The small-rune bombs of a frame's entities: (iid, centre x, centre y, lit). A bomb is exported from its
    appearance (its collider off until it lights); its type is the shared "damager" (or the alias) with a circle of
    radius R."""
    out = []
    for e in ents or ():
        tk = str(e.get("type_key"))
        if tk != NAME and "damager" not in tk and "damager" not in str(e.get("name")):
            continue
        for c in e.get("colliders") or e.get("cols") or ():
            v = c.get("verts_world") or ()
            if len(v) < 6:
                continue
            r = c.get("r")
            a = np.asarray(v, np.float64).reshape(-1, 2)
            if r is None:
                r = 0.5 * float(a[:, 0].max() - a[:, 0].min())
            if abs(float(r) - R) > 0.15:
                continue
            ctr = a.mean(axis=0)
            d = c.get("damage")
            lit = bool(c.get("enabled") and d and d.get("eff") != 0)
            out.append((int(e.get("iid") or 0), float(ctr[0]), float(ctr[1]), lit))
            break
    return out


def _inside(x: float, x_ok) -> bool:
    if not x_ok:
        return True
    return any(a - 1e-6 <= x <= b + 1e-6 for a, b in x_ok)


class RuneBombs:
    """The per-bomb forecast (module docstring). feed() every game frame; predict() the bombs still to hurt."""

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.rows: list[_Row] = []
        self.keys: set = set()
        self.by_iid: dict = {}        # bomb entity iid -> (_Row or None, m, _Bomb)
        self.T = 0.0
        self.n_synth = 0

    def add_trigger(self, owner: int, t0: float, x: float, y: float, x_ok=None) -> None:
        """A Cast 2 entry (the Segmenter's spawn: game time back-dated to the entry, the Clapper's x / y then)."""
        key = (int(owner), round(float(t0), 4))
        if key in self.keys:
            return
        self.keys.add(key)
        self.rows.append(_Row(int(owner), float(t0), float(x), float(y) + DV, x_ok))

    def _match(self, x: float, T: float) -> tuple[_Row | None, int]:
        best, bm, bt = None, 0, None
        for r in self.rows:
            m = int(round((x - r.x0) / DX))
            if abs(m) > M_MAX or abs(x - r.x0 - DX * m) > TOL_X:
                continue
            dt = T - r.t0
            if dt < -2 * FT or dt > (A0_F[1] + abs(m) * STEP_F[1] + 90.0) * FT:      # (+ the pool's delays)
                continue
            b = r.seen.get(m)
            if b is not None and not (b.ended and b.on is None and T - b.last > 3 * FT):
                if b.ended and b.on is None:      # lost for a frame or two before lighting: the same bomb
                    return r, m
                continue
            if best is None or r.t0 > bt:
                best, bm, bt = r, m, r.t0
        return best, bm

    def feed(self, T: float, ents, owners=None) -> None:
        """One game frame at game time T: the bombs in ents. owners: [(iid, x)] of the tracked Clappers (a bomb row
        with no Cast 2 seen goes to the nearest)."""
        self.feed_bombs(T, bomb_ents(ents), owners)

    def feed_bombs(self, T: float, bombs, owners=None) -> None:
        """feed() on the frame's bombs already parsed (bomb_ents)."""
        self.T = T
        cur = {}
        for iid, x, y, lit in bombs:
            cur[iid] = (x, y, lit)
            rec = self.by_iid.get(iid)
            if rec is not None and abs(rec[2].x - x) > 0.3:
                rec = None                       # a pooled object placed anew
            if rec is None:
                row, m = self._match(x, T)
                if row is None:                  # no Cast 2 seen for it: a row of its own, this bomb its ring 0
                    own = -1
                    if owners:
                        own = min(owners, key=lambda o: abs(o[1] - x))[0]
                    row = _Row(int(own), T - A0_F[0] * FT, x, y, None, synthetic=True)
                    self.rows.append(row)
                    self.n_synth += 1
                    m = 0
                b = row.seen.get(m)
                if b is not None and b.ended and b.on is None and T - b.last <= 3 * FT:
                    b.ended = False
                else:
                    b = _Bomb(x, y, T)
                    row.seen[m] = b
                ring = abs(m)
                if ring not in row.ring_a:
                    row.ring_a[ring] = T
                if row.end_ring is not None and ring >= row.end_ring:
                    row.end_ring = None              # the row goes on (a late ring): timed from this one
                if m == 0 and not row.x0_seen:
                    row.x0, row.y0, row.x0_seen = x, y, True
                elif not row.x0_seen:
                    row.y0 = y
                rec = (row, m, b)
                self.by_iid[iid] = rec
            b = rec[2]
            b.last = T
            if lit:
                if b.on is None:
                    b.on = T
                b.last_lit = T
                b.ended = False                     # lit again (a frozen frame's export): it still hurts
            elif b.on is not None:
                b.ended = True
        for iid in [i for i in self.by_iid if i not in cur]:
            self.by_iid.pop(iid)[2].ended = True     # gone: it cannot hurt (back within 3 frames unlit: the same)
        self.rows = [r for r in self.rows if T - r.t0 <= HORIZON_S]

    def _sched(self, r: _Row, ring: int) -> tuple[float, float]:
        """Ring's appearance window from the ring before it (its first appearance), else from the Cast 2 entry."""
        if ring > 0 and ring - 1 in r.ring_a:
            a = r.ring_a[ring - 1]
            return a + STEP_F[0] * FT, a + STEP_F[1] * FT
        return r.t0 + (A0_F[0] + ring * STEP_F[0]) * FT, r.t0 + (A0_F[1] + ring * STEP_F[1]) * FT

    def predict(self, T: float | None = None) -> np.ndarray:
        """The bombs that can still hurt: [n, 6] (owner, x, y, r, on, off), game times (on / off inclusive, half a
        frame of slack on each side for the frame clock)."""
        T = self.T if T is None else T
        out = []
        dur = (DUR_F - 1.0) * FT
        for r in self.rows:
            # the latest ring seen (its first appearance) times the rings after it
            k_ref = max(r.ring_a) if r.ring_a else None
            for m in range(-M_MAX, M_MAX + 1):
                ring = abs(m)
                x = r.x0 + DX * m
                b = r.seen.get(m)
                if b is not None:
                    if b.ended:
                        continue
                    if b.on is not None:
                        on = b.on
                        off = max(b.on + dur, (b.last_lit or b.on) + FT)
                    else:
                        lo, hi = b.a + LEAD_F[0] * FT, b.a + LEAD_F[1] * FT
                        s_lo, s_hi = self._sched(r, ring)
                        if b.a > s_hi + FT:            # seen late: its appearance missed, or the pool's late side
                            lo = min(lo, s_lo + LEAD_F[0] * FT)
                        if hi < T:
                            # appeared, not lit past its lead (the pool's late side: 23-61 frames): it can light on
                            # any frame now, a rolling window of a lead and a lit time
                            lo, hi = min(lo, T + FT), T + LEAD_F[1] * FT
                        on, off = lo, hi + dur
                    out.append((r.owner, b.x, b.y, R, on - 0.5 * FT, off + 0.5 * FT))
                    continue
                if r.end_ring is not None and ring >= r.end_ring:
                    continue
                if not _inside(x, r.x_ok) or r.synthetic:     # a row with no Cast 2 seen: its seen bombs only
                    continue
                if k_ref is not None and ring <= k_ref:
                    sib = r.seen.get(-m)
                    if m == 0 or sib is None or T > sib.a + PAIR_F * FT:
                        continue                     # late (pool) or never: predicted once seen
                    a_lo, a_hi = max(sib.a, T + 0.5 * FT), sib.a + PAIR_F * FT
                else:
                    if k_ref is None:
                        n, a0, a1 = ring, r.t0 + A0_F[0] * FT, r.t0 + A0_F[1] * FT
                    else:
                        n, a0 = ring - k_ref, r.ring_a[k_ref]
                        a1 = a0
                    a_lo, a_hi = a0 + n * STEP_F[0] * FT, a1 + n * STEP_F[1] * FT
                    if a_hi + LATE_F * FT < T:
                        r.end_ring = ring if r.end_ring is None else min(r.end_ring, ring)
                        continue
                    a_lo = max(a_lo, T + 0.5 * FT)
                    a_hi = max(a_hi, a_lo)
                out.append((r.owner, x, r.y0, R, a_lo + (LEAD_F[0] - 0.5) * FT, a_hi + (LEAD_F[1] + 0.5) * FT + dur))
        if not out:
            return np.zeros((0, 6))
        a = np.asarray(out, np.float64)
        return a[a[:, 5] >= T - 1e-9]


def pending_rows(clappers, cast2_k: tuple = (47.5, 51.0), cast1_k: tuple = (5.0, 7.5), skip=()) -> np.ndarray:
    """(SP13b, SSBOT_FORUM_TWO_BOMBS2) the rows still to come: every Clapper in Spell Antic / Cast 1 (no Cast 2 yet:
    the tracker's forecast starts at Cast 2 under NOPRE) as frames() rows from now (owner, x, y, r, on_k, off_k): its
    Cast 2 entry cast2_k frames after the antic entry (Cast 1: cast1_k after its entry), ring r's pair at x +- 4.2 r,
    the windows of predict() over the entry's spread. clappers: [(iid, x, y, Control state, state time s)]."""
    rows = []
    for iid, x, y, st, tin in clappers:
        if iid in skip or st not in ("Spell Antic", "Cast 1"):
            continue
        kk = cast2_k if st == "Spell Antic" else cast1_k
        lo, hi = max(kk[0] - tin * 60.0, 0.0), max(kk[1] - tin * 60.0, 0.0)
        rb = RuneBombs()
        rb.add_trigger(iid, lo * FT, x, y)
        rb.add_trigger(iid, hi * FT, x, y)
        p = rb.predict(0.0)
        if len(p):
            rows.append(frames(p, 0.0))
    if not rows:
        return np.zeros((0, 6))
    return np.concatenate(rows)


def frames(bombs: np.ndarray, T: float) -> np.ndarray:
    """predict()'s windows as look-ahead frames from T: [n, 6] (owner, x, y, r, on_k, off_k), on_k / off_k integer
    frames (a frame k is game time T + k FT; inclusive, rounded outward)."""
    if not len(bombs):
        return np.zeros((0, 6))
    b = bombs.copy()
    b[:, 4] = np.floor((bombs[:, 4] - T) / FT + 1e-6)
    b[:, 5] = np.ceil((bombs[:, 5] - T) / FT - 1e-6)
    return b


# HeroBox in the planner's Bounds-centre space (forum_v2: HB_HX, HB_HY, HB_DY)
HB_HX, HB_HY, HB_DY = 0.2277, 1.1249, 0.133


def occupied(bk: np.ndarray, x, y, k, m: float, owners=None) -> np.ndarray:
    """Planner points (Bounds centres x, y at look-ahead frames k, broadcastable) whose HeroBox grown by m meets a
    lit bomb of bk (frames()); owners: only the bombs of these iids (None: all)."""
    x = np.asarray(x, np.float64)
    y = np.asarray(y, np.float64)
    k = np.asarray(k)
    shp = np.broadcast_shapes(x.shape, y.shape, k.shape)
    out = np.zeros(shp, bool)
    if not len(bk):
        return out
    reach = R + HB_HX + m
    with np.errstate(invalid="ignore"):
        xs = x[np.isfinite(x)]
        if not xs.size:
            return out
        x_lo, x_hi = float(xs.min()), float(xs.max())
        cols = k.ndim == 1 and len(shp) >= 1 and shp[-1] == k.shape[0]    # k along the last axis: per column
        X = np.broadcast_to(x, shp)
        Y = np.broadcast_to(y, shp)
        for o, bx, by, r, on, off in bk:
            if owners is not None and int(o) not in owners:
                continue
            if bx + reach < x_lo or bx - reach > x_hi:
                continue
            w = (k >= on) & (k <= off)
            if not np.any(w):
                continue
            if cols:
                c = np.flatnonzero(w)
                dx = np.maximum(np.abs(X[..., c] - bx) - HB_HX - m, 0.0)
                dy = np.maximum(np.abs(Y[..., c] + HB_DY - by) - HB_HY - m, 0.0)
                out[..., c] |= dx * dx + dy * dy < r * r
            else:
                dx = np.maximum(np.abs(x - bx) - HB_HX - m, 0.0)
                dy = np.maximum(np.abs(y + HB_DY - by) - HB_HY - m, 0.0)
                out |= w & (dx * dx + dy * dy < r * r)
    return out


def hop_target(bk: np.ndarray, hx: float, k_min: int = 0) -> tuple[int, int] | None:
    """The first bomb window (on_k, off_k) from look-ahead k_min on whose circle covers a hero standing at hx (Bounds
    centre x; the HeroBox half width and 0.3 u in), or None."""
    if not len(bk):
        return None
    near = np.abs(bk[:, 1] - hx) < bk[:, 3] + HB_HX + 0.3
    ok = near & (bk[:, 5] >= k_min)
    if not ok.any():
        return None
    i = np.flatnonzero(ok)[np.argmin(bk[ok, 4])]
    return int(bk[i, 4]), int(bk[i, 5])


__all__ = ["NOPRE", "BOMB", "BOMB_M", "FACE_U", "HOP", "NOGLIDE", "FORECAST", "RuneBombs", "bomb_ents", "frames",
           "occupied", "hop_target", "NAME"]
