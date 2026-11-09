"""Every big rune circle's own life, and the one check every key owner shares (Task 182 seq 310).

The Clapper's jump cast leaves a pooled "damager" object: an octagon, apothem RUNE_R, on the floor. Measured on the 50 bouts of
bf221a09 (opus/review182/s310/UPSTREAM310.json, 100 lit stays, game-clock frames): it lights 65.0-65.5 game frames after it first
appears (the real-frame spread 64-78 is hit-stop freeze) and is lit 5.5-7.0 game frames, ending before the first-seen time + OFF_F; the
object then stays unlit in the entity list for about 100-130 frames before the pool takes it back (a new circle reuses the iid after
at least 11 frames out of the list, 49 reuses, none in place without leaving).

RuneCircles keeps one record per generation (one stay of one object): first seen, lit, spent. A STATE without entities says nothing
about them (ents is empty only before the first enemy and after the last); an iid absent from the list for fewer than ABSENT_F frames
is the same object (no data is no burst); present again after that, moved more than MOVED_U, or lit again after its burst: a new
generation with its own clock. One burst never ends another circle; nothing here matches by position alone; a spent one stays spent
for the rest of its stay; a new owner move or the owner's death changes nothing. Every script reads the same records (the policy feeds
one instance once per tick); the small runes' per-bomb forecast (rune_bombs.RuneBombs) stays where it is, its own rows.

rows() gives the circles as rows in rune_bombs.frames' layout (owner, x, y, r, on_k, off_k; frames from the tick's STATE frame, game
clock). exit_veto() is the last check on a final key: after this tick's key, can she still get clear of every lit-or-to-come rune? A key
that takes that away from her while she has it now is refused (the planner's own row goes out instead). It reads the tick's hero model
(the real in-flight prefix, the hold filter, dash cooldown, locks), a handful of rows, and nothing else.
"""
from __future__ import annotations

import math

import numpy as np

from ssbot.knowledge import kinematics as K

RUNE_R = 7.187               # the circle's apothem (an octagon: |dx|, |dy| <= r, |dx| + |dy| <= r sqrt 2)
ON_F = 65.0                  # game frames from its first appearance to its first lit frame (65.0-65.5 measured)
OFF_F = 74.0                 # ... to the end of its lit frames (the attack_range table's own window, real last lit <= 73.5)
PENDING_F = 77               # the frames after its appearance an unlit, unburst circle still counts as to come (OFF_F + 3)
ABSENT_F = 6                 # frames out of the entity list before its iid counts as gone (real reuses: >= 11)
MOVED_U = 0.5                # u: a circle object this far from where it was has been placed anew

FLOOR_BOX, HERO_HW, HERO_H = 3.015, 0.25, 2.079      # her standing box bottom, half width, height
HORIZON = 130                # frames of the tick's look at the runes (the small-rune forecast's own cut)
# the gate's margins: frames before a rune's earliest lit frame that "after this key she can still get clear" must hold. Now she
# only has to have ANY clean way out (none: nothing to protect, the owner goes on as before)
MARGIN_BIG, MARGIN_BOMB = 6, 2
HOP_F = 16                   # a held jump's frames among the escape rows
RUN_V, DASH_V, MAX_V = 8.25, 28.0, 30.0   # u/s: her run, her dash, nothing of hers is faster without the hook
NEAR_F, NEAR_U = 12, 0.3     # a rune farther than speed x NEAR_F / 60 + NEAR_U from her box is out of this key's reach (no hero model rolled)
CLAW_BIT = 1 << 4            # (the wire mask's Clawline key)


class Circle:
    __slots__ = ("iid", "lo", "hi", "cx", "cy", "first_f", "t0", "t_on", "last_f", "gone_f", "lit", "burst")

    def __init__(self, iid, lo: float, hi: float, cy: float, f: int, t: float):
        self.iid, self.lo, self.hi, self.cx, self.cy = iid, lo, hi, 0.5 * (lo + hi), cy
        self.first_f, self.t0 = f, t
        self.t_on: float | None = None       # game clock of the first lit frame seen
        self.last_f, self.lit, self.burst = f, False, False
        self.gone_f: int | None = None       # the first frame with entities that did not list it (None: listed on the last one)


def circle_objects(s: dict) -> list[tuple[float, float, float, object, bool]]:
    """The rune circles of a STATE: (x lo, x hi, centre y, iid, lit now): the damager objects with a collider of the circle's size."""
    out = []
    for o in s.get("ents") or ():
        if o.get("type_key") != "damager" or not o.get("pos"):
            continue
        for col in o.get("colliders") or ():
            vs = col.get("verts_world") or ()
            xs = vs[0::2]
            if xs and abs((max(xs) - min(xs)) - 2 * RUNE_R) <= 0.6:
                ys = vs[1::2]
                cy = 0.5 * (max(ys) + min(ys)) if ys else float(o["pos"][1])
                out.append((float(min(xs)), float(max(xs)), float(cy), o.get("iid"), bool(col.get("enabled"))))
                break
    return out


class RuneCircles:
    """The live big rune circles, one record per generation (module docstring). update() once per tick (idempotent on one frame)."""

    def __init__(self):
        self.recs: dict = {}                 # iid -> Circle (the current generation of that object)
        self.f: int | None = None
        self.t = 0.0                         # game clock of the frame last seen

    def reset(self) -> None:
        self.recs, self.f, self.t = {}, None, 0.0

    def update(self, f: int, s: dict, t_game: float | None = None) -> None:
        """Frame f's STATE; t_game: its game clock (the policy's Stamp; no clock: frames at 60 Hz). A frame is read once."""
        f = int(f)
        if f == self.f:
            return
        t = float(t_game) if t_game is not None else float(s.get("_t")) if s.get("_t") is not None else f / 60.0
        self.f, self.t = f, t
        if not s.get("ents"):
            return                           # (a STATE without entities says nothing about the objects)
        here = {o[3]: o for o in circle_objects(s)}
        for iid, c in list(self.recs.items()):
            if iid not in here:
                c.gone_f = f if c.gone_f is None else c.gone_f
                if f - c.gone_f >= ABSENT_F:
                    del self.recs[iid]       # gone: its next appearance is a new circle
        for iid, (lo, hi, cy, _, lit) in here.items():
            cx = 0.5 * (lo + hi)
            c = self.recs.get(iid)
            if c is None or abs(c.cx - cx) > MOVED_U or (c.burst and lit) or (c.gone_f is not None and f - c.gone_f >= ABSENT_F):
                c = self.recs[iid] = Circle(iid, lo, hi, cy, f, t)
            c.last_f, c.lit, c.gone_f = f, lit, None
            if lit:
                if c.t_on is None:
                    c.t_on = t
            elif c.t_on is not None:
                c.burst = True

    @staticmethod
    def _live(c: Circle, t: float) -> bool:
        """Lit now, or unlit, not burst, and inside its schedule."""
        if c.lit:
            return True
        return not c.burst and (t - c.t0) * 60.0 < PENDING_F

    def live(self, t: float | None = None) -> list[Circle]:
        t = self.t if t is None else float(t)
        return [c for c in self.recs.values() if self._live(c, t)]

    def spans(self) -> list[tuple[float, float]]:
        """The x spans of the circles lit now or still to come (the scripts' view)."""
        return [(c.lo, c.hi) for c in self.live()]

    def rows(self, t: float | None = None) -> np.ndarray:
        """[n, 6] (owner iid, x, y, r, on_k, off_k): the live circles, lit frames from this STATE's frame (0 = now; inclusive, rounded
        outward), rune_bombs.frames' layout; an overdue one (past ON_F, not lit yet) stays a window from now to its OFF_F."""
        t = self.t if t is None else float(t)
        out = []
        for c in self.recs.values():
            if not self._live(c, t):
                continue
            if c.lit:
                on, off = 0.0, max(0.0, ((c.t_on if c.t_on is not None else t) + 7.0 / 60.0 - t) * 60.0)
            else:
                on = max(0.0, (c.t0 + ON_F / 60.0 - t) * 60.0)
                off = (c.t0 + OFF_F / 60.0 - t) * 60.0
                if off < 0.0:
                    off = 0.0
            out.append((float(c.iid if isinstance(c.iid, (int, float)) else -1), c.cx, c.cy, RUNE_R, math.floor(on + 1e-6), math.ceil(off - 1e-6)))
        return np.asarray(out, np.float64).reshape(-1, 6) if out else np.zeros((0, 6))


# ---- hazards against a hero path (box rows) ----

def _over_big(x0, y0, x1, y1, cx, cy, r, m=0.0):
    """Boxes (arrays) that meet the octagon (cx, cy, apothem r + m)."""
    dx = np.maximum(np.maximum(x0 - cx, cx - x1), 0.0)
    dy = np.maximum(np.maximum(y0 - cy, cy - y1), 0.0)
    a = r + m
    return (dx <= a) & (dy <= a) & (dx + dy <= a * math.sqrt(2.0))


def _over_bomb(x0, y0, x1, y1, cx, cy, r, m=0.0):
    """Boxes (arrays) that meet the circle (cx, cy, r + m)."""
    qx = np.clip(cx, x0, x1)
    qy = np.clip(cy, y0, y1)
    return (qx - cx) ** 2 + (qy - cy) ** 2 < (r + m) ** 2


def _box_hits(box: np.ndarray, rows: np.ndarray, i0: int, big_f: int = 0, bomb_f: int = 0) -> np.ndarray:
    """[N, T1] her box (ro.box [N, T1, 4]) meets a lit rune of rows; rollout index = i0 + k; big_f / bomb_f: frames earlier than a row's on_k
    that count too (the gate's margins)."""
    N, T1 = box.shape[:2]
    out = np.zeros((N, T1), bool)
    for _o, cx, cy, r, on, off in rows:
        big = r > 5.0
        lo = max(int(i0 + on) - (big_f if big else bomb_f), int(i0))
        hi = min(int(i0 + off), T1 - 1)
        if hi < lo:
            continue
        x0, y0, x1, y1 = box[:, lo:hi + 1, 0], box[:, lo:hi + 1, 1], box[:, lo:hi + 1, 2], box[:, lo:hi + 1, 3]
        out[:, lo:hi + 1] |= _over_big(x0, y0, x1, y1, cx, cy, r) if big else _over_bomb(x0, y0, x1, y1, cx, cy, r)
    return out


def path_exposed(x: np.ndarray, bottom: np.ndarray, rows: np.ndarray) -> str | None:
    """Her box centred at x, bottom `bottom` above the floor (one row: frames 0.. from this STATE's frame) against the runes: "circle" / "bomb"
    for the first rune that is lit over her on its own frames, else None. No hero model: a plan's own path (the slam's walk and strike)."""
    if rows is None or not len(rows):
        return None
    x = np.asarray(x, np.float64)
    bottom = np.asarray(bottom, np.float64)
    n = x.shape[0]
    for _o, cx, cy, r, on, off in rows:
        lo, hi = max(int(on), 0), min(int(off), n - 1)
        if hi < lo:
            continue
        x0, x1 = x[lo:hi + 1] - HERO_HW, x[lo:hi + 1] + HERO_HW
        y0 = FLOOR_BOX + bottom[lo:hi + 1]
        y1 = y0 + HERO_H
        if r > 5.0:
            if _over_big(x0, y0, x1, y1, cx, cy, r).any():
                return "circle"
        elif _over_bomb(x0, y0, x1, y1, cx, cy, r).any():
            return "bomb"
    return None


# ---- the last check on a final key ----

ESCAPES = tuple((np.int64(k), h) for k, h in (
    (K.B_LEFT, 0), (K.B_RIGHT, 0), (K.B_LEFT | K.B_DASH, 0), (K.B_RIGHT | K.B_DASH, 0), (0, 0),
    (K.B_JUMP, HOP_F), (K.B_JUMP | K.B_LEFT, HOP_F), (K.B_JUMP | K.B_RIGHT, HOP_F)))


def _escape_row(esc, n: int) -> np.ndarray:
    key, hold = esc
    row = np.full(n, key, np.int64)
    if hold:
        row[hold:] = key & ~K.B_JUMP
    return row


def _safe(ro, rows, i0, big_f, bomb_f) -> np.ndarray:
    """[N] the rollout rows that stay clear of every rune (rollout index i0 + k; big_f / bomb_f frames of margin before a rune's on_k)."""
    hit = _box_hits(ro.box, rows, i0, big_f, bomb_f) & ~((ro.flags & K.F_INVULN) != 0)
    return ~hit[:, i0:].any(axis=1)


def _held_bits(hold) -> int:
    """What the hold filter still holds, wants or has queued (one lane) as a key mask: a key the prefix and this tick's key do not show can still land."""
    if hold is None:
        return 0
    on = hold.latched[0] | hold.desired[0] | (hold.pending[0] > 0)
    return int((on.astype(np.int64) << np.arange(on.size, dtype=np.int64)).sum())


def exit_veto(sim, mask: int, rows: np.ndarray, m_big: int = MARGIN_BIG, m_bomb: int = MARGIN_BOMB, strike_exempt: bool = False) -> tuple[bool, dict | None]:
    """(veto, info). rows: rune rows (rows() / rune_bombs.frames, frames from this STATE's frame). True: the key `mask` (for frame f + 2) leaves her no way clear of the
    lit-or-to-come runes on the escape rows of the next tick on, with the margin, while she has one now. No way now either: False (nothing the key takes away).
    Stages, cheapest first: her distance alone (no hero model): out of reach of every rune with this key, the keys in flight and what the hold filter still holds; two rows
    (this key, then run left / right); only when both fail, the full rows. info None: nothing was rolled. Rollout index = i0 + k (ChainSim: index off = frame f + 2). strike_exempt (the owners that check their own
    strikes along the whole path: the slam script, the chain): a down slash press or a Clawline key is not looked at (the rows have no contact, bounce or hook). A side slash
    is an ordinary key, for every owner."""
    rows = np.asarray(rows, np.float64).reshape(-1, 6)
    rows = rows[rows[:, 5] >= 0.0] if len(rows) else rows
    mask = int(mask)
    strike = bool(mask & CLAW_BIT) or bool(mask & K.B_ATTACK and mask & K.B_DOWN)
    if not len(rows) or (strike_exempt and strike):
        return False, None                   # (the owner's own whole-path checks cover the strike)
    state = np.asarray(sim.start, np.float64).reshape(-1)
    x, vx = float(state[K.PX]), float(state[K.VX])
    prefix = np.asarray(sim.prefix, np.int64).reshape(-1)
    inflight = int(np.bitwise_or.reduce(prefix)) if prefix.size else 0
    keys = mask | inflight | _held_bits(sim.hold)
    speed = max(abs(vx), DASH_V if keys & K.B_DASH else RUN_V if keys & (K.B_LEFT | K.B_RIGHT) else 0.0)
    gap = np.abs(x - rows[:, 1]) - rows[:, 3] - HERO_HW
    if (gap > speed * (NEAR_F + prefix.size - 1) / 60.0 + NEAR_U).all():
        return False, None                   # she is too far from every rune for this key to matter
    rows = rows[gap <= (np.maximum(rows[:, 5], 0.0) + 4.0) * MAX_V / 60.0]     # (the ones she can reach at all before they end)
    if not len(rows):
        return False, None
    i0 = sim.off - 2
    T = max(int(min(np.ceil(rows[:, 5].max()) + 2, HORIZON)), 4)
    info = {"after": True, "now": True, "n_big": int((rows[:, 3] > 5.0).sum()), "n_bomb": int((rows[:, 3] <= 5.0).sum()), "first_on": float(rows[:, 4].min()), "rolls": 2}
    rs = np.zeros((2, T), np.int64)
    rs[:, 0] = mask
    rs[0, 1:] = K.B_LEFT
    rs[1, 1:] = K.B_RIGHT
    if _safe(sim.roll(rs), rows, i0, m_big, m_bomb).any():
        return False, info
    n = len(ESCAPES)
    rs = np.zeros((2 * n + 1, T), np.int64)
    for i, e in enumerate(ESCAPES):
        rs[i, 0] = mask                      # this tick's key, then the way out from the next tick on
        rs[i, 1:] = _escape_row(e, T - 1)
        rs[n + 1 + i] = _escape_row(e, T)    # the way out this tick (the same rows from now)
    rs[n] = mask                             # or simply holding this key
    ro = sim.roll(rs)
    info["rolls"] = 2 * n + 3
    keep = np.arange(n + 1)
    inv = (ro.flags & K.F_INVULN) != 0
    after = _box_hits(ro.box[keep], rows, i0, m_big, m_bomb) & ~inv[keep]
    now = _box_hits(ro.box[n + 1:], rows, i0) & ~inv[n + 1:]
    safe_after = bool((~after[:, i0:].any(axis=1)).any())
    safe_now = bool((~now[:, i0:].any(axis=1)).any())
    holding = _box_hits(ro.box[n:n + 1], rows, i0) & ~inv[n:n + 1]
    keeps_going = not holding[:, i0:].any()     # holding this key is itself a way out (the key away from the rune)
    info["after"], info["now"], info["hold"] = safe_after, safe_now, keeps_going
    return (not safe_after) and safe_now and not keeps_going, info


__all__ = ["RUNE_R", "ON_F", "OFF_F", "PENDING_F", "ABSENT_F", "MOVED_U", "Circle", "RuneCircles", "circle_objects", "path_exposed", "exit_veto"]
