"""The special-move table (task 1v1 T3, the person's design of 2026-10-11, forum.md 48): one-strike entries bound to an
enemy's move, discovered and certified OFFLINE, reached at run time by a handful of arrive-and-strike rows that join
the planner's normal candidates (SSBOT_FORUM_SPECIALS=1; the normal v2 checks cover the approach and the miss branch,
the planner's hit branch re-checks the hit with the live predictions).

An entry records one strike:
  type_key, move           the enemy type and its move (the time cells are frames from the move's antic entry)
  kind                     'down' (down slash) | 'up' | 'side'
  k0 .. k1                 the press frame range (frames from the antic entry, nominal timing)
  dx0 .. dx1, dy0 .. dy1   the hero's position (transform) relative to the enemy's position at the antic entry plus
                           its own displacement in the move (the lunge), x along the enemy's facing (mirrored)
  vy                       the hero's vertical-velocity class at the press: 0 rising (> 3 u/s), 1 apex, 2 falling
                           (< -3 u/s); -1: any
  key                      the horizontal key held from the press on, along the enemy's facing (+1: toward the
                           enemy's front, -1: toward its back, 0: none); the left and right strikes are separate entries
  jpost                    1: jump held again from the press + 3 for 16 frames (the bounce's extension)
  cert                     'both' (the bounce's branch and the miss branch are both safe: the locked-move rule) |
                           'bounce' (the strike lands and its bounce is safe, its miss branch is not: only pressed when
                           the bounce is robust)
  share                    the theory's robust share (the minimum over the timing variants of the paths through the
                           cell that succeed)
  live_n, live_ok          targeted live trials whose press fell in the entry (T1 batches 1-3) and their successes

The tables live next to the aim zones: knowledge/1.0.30000/enemies/forum/specials_<move key>.json (built by
ssbot.tools.specials_build).
"""
from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from ssbot.knowledge import kinematics as kin

SPECIALS_ON = os.environ.get("SSBOT_FORUM_SPECIALS", "0").strip() == "1"
# the arrive-and-strike rows per tick (SSBOT_FORUM_SPECIALS_ROWS) and per entry
MAX_ROWS = int(os.environ.get("SSBOT_FORUM_SPECIALS_ROWS", "8") or 8)
PER_ENTRY = 2
# 'both' only (default) or also 'bounce' entries (SSBOT_FORUM_SPECIALS_CERT=bounce)
CERT_OK = frozenset(("both", "bounce")) if os.environ.get("SSBOT_FORUM_SPECIALS_CERT", "both").strip() == "bounce" \
    else frozenset(("both",))
DIR = Path(__file__).resolve().parents[3] / "knowledge" / "1.0.30000" / "enemies" / "forum"
M_L, M_R, M_D, M_J, M_A = kin.B_LEFT, kin.B_RIGHT, kin.B_DOWN, kin.B_JUMP, kin.B_ATTACK
WINDOW_F, PER_WINDOW = 6, 3   # early_first (the special mode): rows per window of press frames
REACT_F = 2               # an entry whose press frame is fewer than this many frames ahead is not reached any more


@dataclass(frozen=True)
class Entry:
    id: str
    type_key: str
    move: str
    kind: str
    k0: int
    k1: int
    dx0: float
    dx1: float
    dy0: float
    dy1: float
    vy: int
    key: int
    jpost: int
    cert: str
    share: float
    live_n: int = 0
    live_ok: int = 0

    def has(self, k: int, dx: float, dy: float, vy: float | None = None) -> bool:
        if not (self.k0 <= k <= self.k1 and self.dx0 <= dx < self.dx1 and self.dy0 <= dy < self.dy1):
            return False
        return self.vy < 0 or vy is None or vy_class(vy) == self.vy


def vy_class(vy: float) -> int:
    return 0 if vy > 3 else (2 if vy < -3 else 1)


# the moves the table knows: type key -> {Control state: (move key, the state's first frame from the antic entry)}
def _slam_states() -> dict:
    from ssbot.combat.pogo_slam import SLAM_K0
    return {s: ("CL_SLAM", k0) for s, k0 in SLAM_K0.items()}


MOVES = {"Song Heavy Sentry": _slam_states}


def move_frame(type_key: str, state: str | None, t_in: float) -> tuple[str, int] | None:
    """(move key, frame from the move's antic entry) of an enemy of `type_key` in Control state `state` for t_in s."""
    f = MOVES.get(type_key)
    if f is None or state is None:
        return None
    m = f().get(state)
    if m is None:
        return None
    return m[0], m[1] + int(round(float(t_in) * 60))


class SpecialTable:
    def __init__(self, entries: list[Entry], meta: dict | None = None):
        self.entries = entries
        self.meta = meta or {}
        self.by_move: dict[str, list[Entry]] = {}
        for e in entries:
            self.by_move.setdefault(e.move, []).append(e)
        self._lut: dict = {}

    def lut(self, move: str, certs=CERT_OK, rank_cert: bool = True) -> "Lut | None":
        """The dense lookup of `move`'s entries (cached per cert set). rank_cert False (the special mode: a down slash
        on an enemy in a move is a certain hit, so 'bounce' is as good as 'both'): rows ranked by share only."""
        key = (move, tuple(sorted(certs))) if rank_cert else (move, tuple(sorted(certs)), "share")
        if key not in self._lut:
            es = [e for e in self.by_move.get(move, ()) if e.cert in certs]
            self._lut[key] = Lut(es, rank_cert) if es else None
        return self._lut[key]

    @classmethod
    def load(cls, moves=("CL_SLAM",), d: Path = DIR) -> "SpecialTable":
        out, meta = [], {}
        for m in moves:
            p = Path(d) / f"specials_{m}.json"
            if not p.exists():
                continue
            j = json.loads(p.read_text("utf-8"))
            meta[m] = j.get("meta", {})
            out += [Entry(**e) for e in j["entries"]]
        return cls(out, meta)

    def save(self, move: str, d: Path = DIR, meta: dict | None = None) -> Path:
        p = Path(d) / f"specials_{move}.json"
        ents = [asdict(e) for e in self.by_move.get(move, [])]
        nl = chr(10)
        body = ("," + nl).join(json.dumps(e, separators=(",", ":")) for e in ents)
        head = json.dumps(meta or self.meta.get(move, {}))
        p.write_text('{"meta": ' + head + ',' + nl + '"entries": [' + nl + body + nl + ']}' + nl, "utf-8")
        return p

    def applicable(self, move: str, k_now: int, horizon: int, certs=CERT_OK) -> list[Entry]:
        """The entries of `move` whose press range is still ahead (k_now + REACT_F .. k_now + horizon)."""
        lo, hi = k_now + REACT_F, k_now + horizon
        return [e for e in self.by_move.get(move, ()) if e.cert in certs and e.k1 >= lo and e.k0 <= hi]


class Lut:
    """Entries on their (aligned) cells as a dense array [k, x bin, y bin, vy class, key + 1] -> entry index (-1: none;
    when several keys share a cell, a row may land in any of them: the best one by cert then share is taken)."""

    def __init__(self, entries: list[Entry], rank_cert: bool = True):
        self.entries = entries
        e0 = entries[0]
        self.bx, self.by = e0.dx1 - e0.dx0, e0.dy1 - e0.dy0
        self.x0 = min(e.dx0 for e in entries)
        self.y0 = min(e.dy0 for e in entries)
        self.K = max(e.k1 for e in entries) + 1
        nx = int(round((max(e.dx1 for e in entries) - self.x0) / self.bx))
        ny = int(round((max(e.dy1 for e in entries) - self.y0) / self.by))
        self.idx = np.full((self.K, nx, ny, 3, 3), -1, np.int32)
        self.rank = np.array([((2 if e.cert == "both" else 1) * 10 if rank_cert else 10) + e.share for e in entries])
        self.k_has = np.zeros(self.K, bool)          # the move frames with an entry (long rows)
        for e in entries:
            self.k_has[e.k0:e.k1 + 1] = True
        for i, e in enumerate(entries):
            xi = int(round((e.dx0 - self.x0) / self.bx))
            yi = int(round((e.dy0 - self.y0) / self.by))
            vs = range(3) if e.vy < 0 else (e.vy,)
            for v in vs:
                self.idx[e.k0:e.k1 + 1, xi, yi, v, e.key + 1] = i

    def find(self, k: np.ndarray, dx: np.ndarray, dy: np.ndarray, vyc: np.ndarray) -> np.ndarray:
        """[n] the best entry index for each press (k, dx, dy, vy class), -1: none."""
        xi = np.floor((dx - self.x0) / self.bx).astype(np.int64)
        yi = np.floor((dy - self.y0) / self.by).astype(np.int64)
        ok = (k >= 0) & (k < self.K) & (xi >= 0) & (xi < self.idx.shape[1]) & (yi >= 0) & (yi < self.idx.shape[2])
        out = np.full(len(k), -1, np.int64)
        if not ok.any():
            return out
        c = self.idx[k[ok], xi[ok], yi[ok], vyc[ok]]                      # [m, 3] over the keys
        r = np.where(c >= 0, self.rank[np.maximum(c, 0)], -1.0)
        b = r.argmax(axis=1)
        out[ok] = np.where(r.max(axis=1) >= 0, c[np.arange(len(c)), b], -1)
        return out


@dataclass
class StrikeRows:
    cmd: np.ndarray           # [n, T] commanded masks
    entry: list               # [n] the entry each row strikes
    j_press: np.ndarray       # [n] the press's mask index
    tried: int                # templates rolled out
    full: list | None = None  # long rows (strike_rows long_hi): [n] the whole template past T (None: a row within T)


def _templates(T: int, js: list[int], toward: int, step: int = 3, holds=(3, 8, 14, 20), hdelays=(0, 8)
               ) -> tuple[np.ndarray, np.ndarray]:
    """Approach templates of length T for each press mask index j in js: the jump starting at mask s (0 .. j - 2, every
    `step`; or no jump), held h frames, the horizontal key before the press -1 / 0 / +1 (world: +1 right) from the
    jump + hdelay (straight up first: over a body), down from j - 3, the attack on j. Returns (masks [n, T], j [n])."""
    rows, jj = [], []
    hk = {1: M_R, -1: M_L, 0: 0}
    for j in js:
        starts = [None] + list(range(0, max(j - 1, 1), step))
        for s in starts:
            for h in (holds if s is not None else (0,)):
                for pre in (1, 0, -1):
                    for d in (hdelays if (s is not None and pre != 0) else (0,)):
                        if s is not None and s + d >= j:
                            continue
                        m = np.zeros(T, np.int64)
                        if s is not None:
                            m[s:s + h] |= M_J
                        m[(0 if d == 0 else s + d):j] |= hk[pre]
                        m[max(j - 3, 0):j + 1] |= M_D
                        m[j] |= M_A
                        rows.append(m)
                        jj.append(j)
    return (np.asarray(rows, np.int64).reshape(-1, T), np.asarray(jj, np.int64))


# long rows (SSBOT_FORUM_SPECIAL_MODE, task 1v1 G1 (d)): a press past the planner's horizon, the jump within LONG_SPAN
# frames before it (held LONG_HOLDS), the frames before the jump standing or running; the row's masks past the press
# run on for LONG_POST frames (the bounce's first part: the planner re-plans it within its horizon later)
LONG_SPAN = 30
LONG_HOLDS = (8, 14, 20)
LONG_POST = 24


def _templates_long(js: list[int], step: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """Templates for presses past the horizon (each of length max(js) + 2): the jump starts at s in j - LONG_SPAN ..
    j - 6 (every `step`), held LONG_HOLDS, the horizontal key -1 / 0 / +1 from frame 0 (run, then jump) or from the
    jump + 8 (stand, jump straight up first); down from j - 3, the attack on j."""
    TL = max(js) + 2
    rows, jj = [], []
    hk = {1: M_R, -1: M_L, 0: 0}
    for j in js:
        for s in range(max(j - LONG_SPAN, 0), j - 5, step):
            for h in LONG_HOLDS:
                for pre in (1, 0, -1):
                    for d in ((0, 8) if pre != 0 else (0,)):
                        if s + d >= j:
                            continue
                        m = np.zeros(TL, np.int64)
                        m[s:s + h] |= M_J
                        m[(0 if d == 0 else s + d):j] |= hk[pre]
                        m[max(j - 3, 0):j + 1] |= M_D
                        m[j] |= M_A
                        rows.append(m)
                        jj.append(j)
    return (np.asarray(rows, np.int64).reshape(-1, TL), np.asarray(jj, np.int64))


_TCACHE: dict = {}


def _cached(key, make):
    """The special mode's template cache (the templates depend on the press indices only)."""
    v = _TCACHE.get(key)
    if v is None:
        if len(_TCACHE) > 96:
            _TCACHE.clear()
        v = _TCACHE[key] = make()
    return v


def strike_rows(params, terrain, start: np.ndarray, lut: "Lut | None", k_now: int, x_anchor: float, cy: float,
                face: int, disp: np.ndarray, T: int, max_rows: int = MAX_ROWS, per_entry: int = PER_ENTRY,
                horizon: int | None = None, js_step: int = 3, threads: int = 1, prefix: np.ndarray | None = None,
                long_hi: int | None = None, early_first: bool = False) -> StrikeRows:
    """The arrive-and-strike rows for a move's entries: approach templates (a press on every js_step-th frame from
    k_now + REACT_F within the horizon) rolled out from `start` (the hero's model state now, at the move's frame
    k_now), kept where the hero's position on the press frame (rollout index j + 1 = move frame k_now + j + 1) lies in
    an entry's cell and vy class; the entry's key (and jpost) from the press on. The best rows by cert, share and
    distance to the cell's centre, at most per_entry per entry. Enemy x on move frame k: x_anchor + face * disp[k] (the
    lunge); its y: cy. prefix: the masks already in flight (the rows start after them; rollout index P + j + 1).
    long_hi (the special mode, None: off): presses on mask indices up to long_hi past the horizon too (_templates_long,
    only on move frames with entries); such a row's cmd is its first T masks, its whole template (the press + LONG_POST
    frames) in .full. early_first (the special mode): the earliest press first, then share and distance, at most
    PER_WINDOW rows a WINDOW_F-frame window of press frames (the rows spread over the strikes still to come)."""
    T = int(T)
    P = 0 if prefix is None else len(prefix)
    hz = min(T - 2, horizon or T - 2)
    empty = StrikeRows(np.zeros((0, T), np.int64), [], np.zeros(0, np.int64), 0)
    if lut is None:
        return empty
    js = [j for j in range(max(REACT_F - 1 - P, 0), hz + 1, js_step) if k_now + P + j + 1 < lut.K]
    jl = [] if long_hi is None else [j for j in range(hz + 1, int(long_hi) + 1, js_step)
                                     if k_now + P + j + 1 < lut.K and lut.k_has[k_now + P + j + 1]]
    if not js and not jl:
        return empty
    def press_states(M_, J_):
        """The templates' press-frame position, vy and airborne flag (one rollout)."""
        Mf = np.concatenate([np.broadcast_to(np.asarray(prefix, np.int64), (len(M_), P)), M_], axis=1) if P else M_
        ro = kin.rollout(start, Mf, params, terrain, threads=threads)
        a_ = np.arange(len(M_))
        return ro.pos[a_, P + J_ + 1], ro.vel[a_, P + J_ + 1, 1], (ro.flags[a_, P + J_] & kin.F_GROUND) == 0

    if long_hi is None:
        M, J = _templates(T, js, face)
        pos, vy, air = press_states(M, J)
    else:
        # the special mode: the templates within the horizon first; the long ones only when those give fewer than
        # max_rows rows (the rows go to the earliest presses: a long row ranks after every row within the horizon)
        M, J = _cached(("s", T, tuple(js)), lambda: _templates(T, js, face)) if js else             (np.zeros((0, T), np.int64), np.zeros(0, np.int64))
        pos, vy, air = press_states(M, J) if len(M) else (np.zeros((0, 2)), np.zeros(0), np.zeros(0, bool))
        if jl:
            kp_ = k_now + P + J + 1
            dx_ = (pos[:, 0] - (x_anchor + face * disp[np.clip(kp_, 0, len(disp) - 1)])) * face
            vyc_ = np.where(vy > 3, 0, np.where(vy < -3, 2, 1))
            ei_ = np.where(air, lut.find(kp_, dx_, pos[:, 1] - cy, vyc_), -1) if len(M) else np.zeros(0, np.int64)
            got = int(np.minimum(np.bincount(ei_[ei_ >= 0], minlength=1), per_entry).sum()) if (ei_ >= 0).any() else 0
            if got < max_rows:
                ML, JL = _cached(("l", tuple(jl), js_step), lambda: _templates_long(jl, js_step))
                pl_, vl_, al_ = press_states(ML, JL)
                TL = ML.shape[1]
                M = np.concatenate([np.pad(M, ((0, 0), (0, max(TL - M.shape[1], 0)))), ML])
                J = np.concatenate([J, JL])
                pos, vy, air = np.concatenate([pos, pl_]), np.concatenate([vy, vl_]), np.concatenate([air, al_])
    n = len(M)
    kp = k_now + P + J + 1
    ex = x_anchor + face * disp[np.clip(kp, 0, len(disp) - 1)]
    dx = (pos[:, 0] - ex) * face
    dy = pos[:, 1] - cy
    vyc = np.where(vy > 3, 0, np.where(vy < -3, 2, 1))
    ei = np.where(air, lut.find(kp, dx, dy, vyc), -1)
    cand = np.flatnonzero(ei >= 0)
    if not len(cand):
        return StrikeRows(np.zeros((0, T), np.int64), [], np.zeros(0, np.int64), n)
    es = lut.entries
    cxm = np.array([0.5 * (es[i].dx0 + es[i].dx1) for i in ei[cand]])
    cym = np.array([0.5 * (es[i].dy0 + es[i].dy1) for i in ei[cand]])
    d = (dx[cand] - cxm) ** 2 + (dy[cand] - cym) ** 2
    order = np.lexsort((d, -lut.rank[ei[cand]], kp[cand])) if early_first else np.lexsort((d, -lut.rank[ei[cand]]))
    hk = {1: M_R, -1: M_L, 0: 0}
    out, ents, jp, used, full = [], [], [], Counter(), []
    for o in order:
        i = int(cand[o])
        e = es[int(ei[i])]
        if used[e.id] >= per_entry:
            continue
        if early_first:
            # spread over the press windows: at most PER_WINDOW rows a WINDOW_F-frame window of press frames
            wk = ("w", int(kp[i]) // WINDOW_F)
            if used[wk] >= PER_WINDOW:
                continue
            used[wk] += 1
        used[e.id] += 1
        j = int(J[i])
        L = T if j <= T - 2 else j + 1 + LONG_POST
        m = np.zeros(L, np.int64)
        m[:min(L, M.shape[1])] = M[i][:L]
        m[j + 1:] &= ~(M_L | M_R)
        m[j + 1:] |= hk[int(e.key * face)]
        m[j + 1:min(j + 4, L)] |= M_D
        if e.jpost:
            m[j + 3:min(j + 19, L)] |= M_J
        out.append(m[:T])
        full.append(m if L > T else None)
        ents.append(e)
        jp.append(j)
        if len(out) >= max_rows:
            break
    return StrikeRows(np.asarray(out, np.int64).reshape(-1, T), ents, np.asarray(jp, np.int64), n,
                      full if long_hi is not None else None)


def enemy_move(ent: dict) -> tuple[str, int] | None:
    """(move key, frame) of an observed enemy dict (type_key, fsms [{name: Control, state, t}])."""
    st, tin = None, 0.0
    for m in ent.get("fsms") or ():
        if m.get("name") == "Control":
            st, tin = m.get("state"), float(m.get("t") or 0.0)
    return move_frame(ent.get("type_key") or "", st, tin)


__all__ = ["SPECIALS_ON", "MAX_ROWS", "CERT_OK", "Entry", "SpecialTable", "StrikeRows", "Lut", "strike_rows", "move_frame",
           "enemy_move", "vy_class", "MOVES", "DIR"]
