"""The person's GENERAL SPECIAL RULE (2026-10-12; task 1v1 G1, forum.md 49) behind SSBOT_FORUM_SPECIAL_MODE=1 (default
off: every planner decision as before).

The rule: at the antic of a move M that has entries in the special-move table (combat.specials; CL_SLAM so far), look
the table up; if a strike point is reachable and safe from the OTHER enemies, ignore M's own danger and plan the path
to the strike point. Concretely (ForumPlanner.tick under v2):

  a. enemy E is in special mode for M while its arrive-and-strike rows exist (specials.strike_rows with the mode's
     certs: both + bounce, the person's rule "a down slash on an enemy in a move is a certain hit"). Those rows only
     ("special rows") are judged against the special support: every other enemy as built (moves, bodies, hazards,
     margins), E's hazards, and E's BODY in M (the move's measured root boxes, the frames k - 1 .. k + 1, with E's
     support margin), not M's attack-range estimate; the pending-aim check skips E's aims. Every other row keeps the
     full checks.
  b. the down slash is a certain hit: a special row's lane is the BOUNCE lane from its press on (EV_POGO on the slash's
     contact with the move's root box, as the T1 theory), in stage 1 and in the envelope; the hit branch is not run
     for it (the bounce against M is certified offline by the entry). The certified window is the press .. the
     landing after the bounce (SlamTheory: press .. landing, at most T_AFTER frames); if M still has active boxes
     after it, the full support (M's estimate) is read from the window's end on.
  c. the approach before the press is checked against E's body and the other enemies only; T1's real-box approach
     check (the hammer and the root box, no margin) is counted for the chosen special rows as a diagnostic only.
  d. long rows: a press past the planner's horizon (strike_rows long_hi): the row is the template's first T masks;
     the rest (the approach, the press, the bounce's first LONG_POST frames) is rolled out here and checked against
     the special support (the tail check). Every special row's tail check doubles as its escape: clear -> the row
     has an escape; else the v2 escape check from its end state (the bounce state) against the FULL escape support
     (review 2026-10-12: an escape command leaves the certified bounce, so M's danger applies to it).
  e. the planner posts its decision on BOARD (iid -> tick, on, x); the L2 Clapper controller
     (tactics.gauntlet._clapper_spot) reads it: on -> the stance is the strike point (hit weight > 0), else today's
     step-out.
  f. special rows are filtered on the keys they use (MOVE, JUMP, ATTACK_DOWN), not on the whole allowlist.
  g. no safe special row -> nothing changes (the normal rows keep M's danger).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import numpy as np

from ssbot.knowledge import kinematics as kin

SPECIAL_MODE = os.environ.get("SSBOT_FORUM_SPECIAL_MODE", "0").strip() == "1"
MODE_CERTS = frozenset(("both", "bounce"))
LONG = SPECIAL_MODE and os.environ.get("SSBOT_FORUM_SPECIAL_LONG", "1").strip() != "0"
# the real-box approach check (T1: the hammer and the root box, no margin, from the jump to the press) as a FILTER of
# the special rows (default on, the person 2026-10-12 after G1's replay: the approach also checks M's active real
# boxes - without it 475 of 712 chosen ticks waited inside the falling hammer; SSBOT_FORUM_SPECIAL_APPR=0 is the
# literal rule, E's body and the others only; the audit counts the chosen rows failing it either way)
APPR = SPECIAL_MODE and os.environ.get("SSBOT_FORUM_SPECIAL_APPR", "1").strip() != "0"
_BM = os.environ.get("SSBOT_FORUM_SPECIAL_BODY_M", "").strip()
BODY_M: float | None = float(_BM) if _BM else None      # None: E's support margin (RangeSupport.m_of)
CERT_AFTER = 75           # SlamTheory.T_AFTER: the certified window ends at the landing, at most this many frames on
LONG_PRESS_MAX = 60       # long rows: presses up to this many masks ahead (1 s)
MAX_ROWS = int(os.environ.get("SSBOT_FORUM_SPECIAL_ROWS", "12") or 12)    # special rows per tick (earliest press first)
# SSBOT_FORUM_SPECIAL_FAST=1 (task 1v1 G3 item 3, the mode's cost): per tick only the templates that can start now (jump
# now, or none: the current state) are rolled out; the whole set (jumps later, the long rows) every FULL_EVERY ticks and
# on the move's first tick, and its BOARD decision (the L2 strike spot) is kept for the ticks between
FAST = SPECIAL_MODE and os.environ.get("SSBOT_FORUM_SPECIAL_FAST", "0").strip() == "1"
FULL_EVERY = int(os.environ.get("SSBOT_FORUM_SPECIAL_FULL_EVERY", "6") or 6)
# SSBOT_FORUM_SPECIAL_HOLD=1 (G3 item 4): the special rows keep holding a committed jump (Planner.jump_until) over its
# remaining frames, as the set's attack rows do; without it every special row ranks behind the rows that keep the hold
# (the selection's `keep` key) until the hold ends (G1's replay, slam 20261012_054126 i0 ep1 f 124204-124213)
HOLD = SPECIAL_MODE and os.environ.get("SSBOT_FORUM_SPECIAL_HOLD", "0").strip() == "1"
# task 1v1 G4 (the person's decisions of 2026-10-12; every one default off, each its own switch):
# SSBOT_FORUM_SPECIAL_KEEP=1 (4b, "keep once chosen"): a chosen special row (or a G3 down-slash row) is kept while it
# is still on its template (the special CONTINUE still certified with a contact; the "DS cont" row's contact holds)
# and passes every check: no other row replaces it, and its template search is skipped on those ticks
KEEP = os.environ.get("SSBOT_FORUM_SPECIAL_KEEP", "0").strip() == "1"
# SSBOT_FORUM_SPECIAL_TABLE=v2 (G4 item 3): the merged table (specials_CL_SLAM_v2.json: the slack cores, late-only time
# slack, +-0.5 u) instead of today's cells
TABLE = os.environ.get("SSBOT_FORUM_SPECIAL_TABLE", "").strip()
# SSBOT_FORUM_HITS_FIRST=1 (4c, "most hits first, stop early"): the strike options (special rows, the down-slash family)
# are enveloped first, by their hit count; once one passes every check, the rows with fewer hits are not evaluated
HITS_FIRST = os.environ.get("SSBOT_FORUM_HITS_FIRST", "0").strip() == "1"
# SSBOT_FORUM_MOVE_HITS=1 (5b): the scorer's target body of an enemy in a tracked move follows the move template's
# displacement (the hits, the ranking, the family's prefilter) instead of moving on at its present velocity
MOVE_HITS = os.environ.get("SSBOT_FORUM_MOVE_HITS", "0").strip() == "1"
from ssbot.combat.special_board import BOARD, L2_ON  # noqa: E402,F401  (the L2 controller's board)

_TL: dict = {}


# the tracker's family of each table move (attack_range's Segmenter instance): the jump (CC_JUMP) and the jump cast
# (CC_JUMP_CAST) land through the slam's own Control states "Slam 2" / "Slam Recover" (are_types.clapper FLIGHT), which
# specials.enemy_move reads as CL_SLAM frames 57+ (review 2026-10-12)
MOVE_FAMS = {"CL_SLAM": frozenset({"CC_SLAM"})}


def in_family(move: str, inst) -> bool:
    """E's tracked instance is the table move's own family (no instance: the antic was not seen, the move is not known
    for sure: False)."""
    fams = MOVE_FAMS.get(move)
    return fams is not None and inst is not None and getattr(inst, "fam", None) in fams


def timeline(move: str):
    """The move's per-frame boxes (root = the body, hammer = the attack) and lunge, in the enemy's facing frame
    relative to its position at the antic entry (CL_SLAM: pogo_slam.SlamTimeline); None: unknown move."""
    if move not in _TL:
        tl = None
        if move == "CL_SLAM":
            from ssbot.combat.pogo_slam import SlamTimeline
            tl = SlamTimeline.load()
        _TL[move] = tl
    return _TL[move]


def world_boxes(tl, ks: np.ndarray, xa: float, cy: float, face: int, which: str = "root") -> np.ndarray:
    """[n, 4] world boxes (x0, y0, x1, y1) at move frames ks (NaN rows: none)."""
    b = tl.world(np.asarray(ks, np.int64), which)
    xs = np.stack([xa + face * b[:, 0], xa + face * b[:, 1]], axis=1)
    return np.stack([xs.min(axis=1), cy + b[:, 2], xs.max(axis=1), cy + b[:, 3]], axis=1)


def active_last(tl) -> int:
    """The last move frame with an active attack box (the hammer); -1: none."""
    ok = np.flatnonzero(np.isfinite(tl.hammer[:, 0]))
    return int(ok[-1]) if len(ok) else -1


def row_keys_allowed(cmd: np.ndarray, allowed_mask: np.ndarray) -> np.ndarray:
    """(f) [n] every primitive a special row uses is allowed: MOVE (a horizontal key), JUMP, ATTACK_DOWN."""
    from ssbot.core.primitives import Prim
    m = np.bitwise_or.reduce(np.asarray(cmd, np.int64), axis=1) if len(cmd) else np.zeros(0, np.int64)
    ok = np.ones(len(m), bool)
    am = np.asarray(allowed_mask, bool)
    for bits, p in ((kin.B_LEFT | kin.B_RIGHT, Prim.MOVE), (kin.B_JUMP, Prim.JUMP),
                    (kin.B_ATTACK, Prim.ATTACK_DOWN), (kin.B_DOWN, Prim.ATTACK_DOWN)):
        ok &= ~(((m & bits) != 0) & ~am[int(p)])
    ok &= (m & ~(kin.B_LEFT | kin.B_RIGHT | kin.B_JUMP | kin.B_ATTACK | kin.B_DOWN)) == 0
    return ok


def facing_at(start: np.ndarray, masks: np.ndarray, j: int) -> int:
    """The hero's facing on mask index j: the last horizontal key at or before it, else the start state's."""
    m = np.asarray(masks[:j + 1], np.int64)
    h = np.flatnonzero((m & (kin.B_LEFT | kin.B_RIGHT)) != 0)
    if len(h):
        return 1 if int(m[h[-1]]) & kin.B_RIGHT else -1
    f0 = float(np.asarray(start).reshape(kin.K, -1)[kin.FACE, 0])
    return 1 if f0 >= 0 else -1


def contact_index(tl, pos: np.ndarray, flags: np.ndarray, pj: int, k0: int, xa: float, cy: float, face: int,
                  hero_face: int) -> int:
    """The rollout index of the down slash's first contact with the move's root box (T1's rule: frames pj + ACTIVE,
    before a landing; the slash polygon of either alternation), -1: none. pos / flags: one lane [T1]; pj: the press
    frame's rollout index; move frame of rollout index i: k0 + i."""
    from ssbot.combat.pogo_model import ACTIVE, meets
    L = len(flags)
    if pj >= L or pj < 1:
        return -1
    if not bool(((flags[pj:min(pj + 2, L)] & kin.F_ATTACKING) != 0).any()) or bool(flags[pj - 1] & kin.F_GROUND):
        return -1
    sp = _slash(hero_face)
    js = np.arange(pj + ACTIVE[0], min(pj + ACTIVE[1], L - 1) + 1)
    if not len(js):
        return -1
    bs = world_boxes(tl, k0 + js, xa, cy, face)
    for j, b in zip(js, bs):
        if flags[j] & kin.F_GROUND:
            break
        if not np.isfinite(b[0]):
            continue
        # the slash's bounding box first (cheap), then the polygons
        q = sp + pos[j]
        if q[:, 0].max() <= b[0] or q[:, 0].min() >= b[2] or q[:, 1].max() <= b[1] or q[:, 1].min() >= b[3]:
            continue
        rect = np.array([[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]])
        if meets(q, rect):
            return int(j)
    return -1


def contacts(tl, pos: np.ndarray, flags: np.ndarray, pj: np.ndarray, k0: int, xa: float, cy: float, face: int,
             hero_face: np.ndarray) -> np.ndarray:
    """contact_index for n lanes at once ([n] rollout index of the first contact, -1: none; pj 0: no press): the
    slash's bounding box against the root boxes on all frames in one pass, the polygons only where those meet."""
    from ssbot.combat.pogo_model import ACTIVE, meets
    n, L = flags.shape
    out = np.full(n, -1, np.int64)
    pj = np.asarray(pj, np.int64)
    ok = (pj >= 1) & (pj < L)
    if not ok.any():
        return out
    q = np.flatnonzero(ok)
    pq = pj[q]
    at = (flags[q, pq] & kin.F_ATTACKING) != 0
    at |= (flags[q, np.minimum(pq + 1, L - 1)] & kin.F_ATTACKING) != 0
    ok_q = at & ((flags[q, pq - 1] & kin.F_GROUND) == 0)
    q, pq = q[ok_q], pq[ok_q]
    if not len(q):
        return out
    js = pq[:, None] + np.arange(ACTIVE[0], ACTIVE[1] + 1)[None, :]                 # [m, A]
    valid = js <= L - 1
    jc = np.minimum(js, L - 1)
    gnd = (flags[q[:, None], jc] & kin.F_GROUND) != 0
    valid &= np.cumsum(gnd, axis=1) == 0                                            # before a landing
    bx = world_boxes(tl, (k0 + jc).reshape(-1), xa, cy, face).reshape(len(q), -1, 4)
    hf = np.asarray(hero_face, np.int64)[q]
    lo = np.zeros((len(q), 2))
    hi = np.zeros((len(q), 2))
    for f_ in (1, -1):
        sp = _slash(f_)
        m_ = hf == f_
        lo[m_] = sp.min(axis=0)
        hi[m_] = sp.max(axis=0)
    p_ = pos[q[:, None], jc]                                                        # [m, A, 2]
    with np.errstate(invalid="ignore"):
        cand = valid & np.isfinite(bx[..., 0]) & (p_[..., 0] + hi[:, None, 0] > bx[..., 0]) \
            & (p_[..., 0] + lo[:, None, 0] < bx[..., 2]) & (p_[..., 1] + hi[:, None, 1] > bx[..., 1]) \
            & (p_[..., 1] + lo[:, None, 1] < bx[..., 3])
    for r in np.flatnonzero(cand.any(axis=1)):
        sp = _slash(int(hf[r]))
        for a in np.flatnonzero(cand[r]):
            b = bx[r, a]
            rect = np.array([[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]])
            if meets(sp + p_[r, a], rect):
                out[q[r]] = int(js[r, a])
                break
    return out


def press_certified(lut, disp: np.ndarray, pos: np.ndarray, vel: np.ndarray, flags: np.ndarray, pj: np.ndarray,
                    masks: np.ndarray, k0: int, xa: float, cy: float, face: int) -> np.ndarray:
    """[n] the row's press state ON THE PLANNER'S OWN LANE lies in a certified entry of the table (review 2026-10-12):
    airborne on the frame before the press, the press frame's move frame k0 + pj, dx along E's facing from E's lunged
    x, dy, the vy class, and the row's own key after the press (masks[q, pj]: the mask on the press frame's rollout
    index, prefix included) all inside one entry. specials.strike_rows finds the entries on a rollout of the raw
    masks; the planner's lane is hold-filtered (a key held now delays a press), and a CONTINUE of a chosen special row
    is not looked up again at all, so a row whose press left its cell would otherwise drop M's danger uncertified.
    pos / vel / flags: [n, L] lanes (pos, vel [n, L, 2]); pj: the press frame's rollout index (0: none)."""
    n = len(pj)
    out = np.zeros(n, bool)
    if lut is None or not n:
        return out
    L = flags.shape[1]
    for q in range(n):
        p = int(pj[q])
        if p < 1 or p >= L or (int(flags[q, p - 1]) & kin.F_GROUND):
            continue
        kp = int(k0) + p
        if kp < 0 or kp >= lut.K:
            continue
        ex = xa + face * float(disp[min(max(kp, 0), len(disp) - 1)])
        dx = (float(pos[q, p, 0]) - ex) * face
        dy = float(pos[q, p, 1]) - cy
        vy = float(vel[q, p, 1])
        vyc = 0 if vy > 3 else (2 if vy < -3 else 1)
        xi = int(np.floor((dx - lut.x0) / lut.bx))
        yi = int(np.floor((dy - lut.y0) / lut.by))
        if not (0 <= xi < lut.idx.shape[1] and 0 <= yi < lut.idx.shape[2]):
            continue
        h = int(masks[q, p]) & (kin.B_LEFT | kin.B_RIGHT) if p < masks.shape[1] else 0
        s = 1 if h == kin.B_RIGHT else (-1 if h == kin.B_LEFT else 0)
        out[q] = lut.idx[kp, xi, yi, vyc, s * face + 1] >= 0
    return out


def approach_codes(tl, k0: int, xa: float, cy: float, face: int, pj: np.ndarray, box: np.ndarray,
                   flags: np.ndarray) -> np.ndarray:
    """real_approach_fail for n lanes at once (box [n, L, 4], flags [n, L], pj [n]): [n] 0 clear, 2 the attack box,
    1 the root box only."""
    n, L = flags.shape
    pj = np.asarray(pj, np.int64)
    J = int(min(max(int(pj.max()) if n else 0, 1), L))
    js = np.arange(1, J)
    out = np.zeros(n, np.int64)
    if not len(js):
        return out
    live = ((flags[:, js] & kin.F_INVULN) == 0) & (js[None, :] < pj[:, None])
    hb = box[:, js]
    for code, which in ((1, "root"), (2, "hammer")):
        b = world_boxes(tl, k0 + js, xa, cy, face, which)[None]                    # [1, J-1, 4]
        with np.errstate(invalid="ignore"):
            hit = np.isfinite(b[..., 0]) & (b[..., 0] < hb[..., 2]) & (b[..., 2] > hb[..., 0]) \
                & (b[..., 1] < hb[..., 3]) & (b[..., 3] > hb[..., 1]) & live
        out = np.where(hit.any(axis=1), code, out)
    return out


_SLASH: dict = {}


def _slash(face: int) -> np.ndarray:
    """The down slash's polygon of either alternation (pogo_model.slash_poly(face, None)), cached."""
    if face not in _SLASH:
        from ssbot.combat.pogo_model import slash_poly
        _SLASH[face] = slash_poly(face, None)
    return _SLASH[face]


def body_extra(rs, iid: int, tl, k_trk: int, xa: float, cy: float, face: int, type_key: str) -> list:
    """E's body in M as raw parts [(si, coarse, ix0, iy0, m, esc_m)]: at each sample the move's root boxes of the
    frames k - 1 .. k + 1 (the lunge in), E's support margin (BODY_M when set)."""
    from ssbot.combat import forum_v2
    from ssbot.combat.attack_range import CELL, poly_mask
    out = []
    for si, k in enumerate(rs.samples):
        kk = k_trk + k
        bx = world_boxes(tl, np.array([kk - 1, kk, kk + 1]), xa, cy, face)
        polys = [np.array([[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]]) for b in bx if np.isfinite(b[0])]
        if not polys:
            continue
        mk = poly_mask(polys, CELL)
        c, ix0, iy0 = forum_v2.coarse(mk, CELL, rs.cv.cell)
        m = BODY_M if BODY_M is not None else rs.m_of(iid, type_key, k)
        esc = k + rs.k_shift >= forum_v2.ESC_FROM_K
        out.append((si, c, ix0, iy0, m, m if esc else None))
    return out


_BODY: dict = {}


def body_stacks(rs, iid: int, tl, k_trk: int, xa: float, cy: float, face: int, type_key: str
                ) -> tuple[np.ndarray, np.ndarray]:
    """E's body in M as (stack, escape stack) on the support's samples: body_extra's parts dilated, each (move frame,
    anchor, margin) once (cached: the anchor holds still through a move, the samples come back tick after tick)."""
    from ssbot.combat import forum_v2
    from ssbot.combat.attack_range import CELL, poly_mask
    st = np.zeros(rs.stack.shape, bool)
    es = np.zeros(rs.stack.shape, bool)
    for si, k in enumerate(rs.samples):
        kk = int(k_trk + k)
        m = BODY_M if BODY_M is not None else rs.m_of(iid, type_key, k)
        xq, yq = round(float(xa) / 0.05) * 0.05, round(float(cy) / 0.05) * 0.05      # the raster's own lattice
        key = (id(tl), kk, round(xq, 3), round(yq, 3), int(face), round(float(m), 4))
        d = _BODY.get(key)
        if d is None:
            bx = world_boxes(tl, np.array([kk - 1, kk, kk + 1]), xq, yq, face)
            polys = [np.array([[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]]) for b in bx
                     if np.isfinite(b[0])]
            d = None
            if polys:
                c, ix0, iy0 = forum_v2.coarse(poly_mask(polys, CELL), CELL, rs.cv.cell)
                d = forum_v2.dilate_group([(c, ix0, iy0)], m, rs.cv.cell)
            if len(_BODY) > 8192:
                _BODY.clear()
            _BODY[key] = d
        if d is None or not d[0].size:
            continue
        rs.cv.paste(st[si], *d)
        if k + rs.k_shift >= forum_v2.ESC_FROM_K:
            rs.cv.paste(es[si], *d)
    if rs.stack_esc is None:
        es = st.copy()
    return st, es


@dataclass
class SpecialCtx:
    """One tick's special mode (ForumPlanner.tick)."""
    iid: int
    move: str
    k0: int                    # E's move frame at the planner's rollout index 0
    xa: float                  # E's x at the antic entry (the lunge's anchor)
    cy: float
    face: int
    tl: object
    st_o: np.ndarray           # the special support: every other enemy and E's hazards (special_stacks)
    es_o: np.ndarray           #   ... the escape check's
    st_b: np.ndarray           # E's body in M (body_extra)
    es_b: np.ndarray           #   ... the escape check's
    rows: np.ndarray           # the planner rows (indices) judged in special mode
    contact: np.ndarray        # [n] the bounce event's rollout index (-1: none found: the row keeps the full checks)
    cert_end: np.ndarray       # [n] rollout index the certified window ends on
    full_from: np.ndarray      # [n] rollout index from which the full support is read (M active after the window)
    ev: np.ndarray             # [n, P + T] events of the planner lanes
    tail_ok: np.ndarray        # [n] the template's continuation past the row's end is clear (its escape)
    pj: np.ndarray             # [n] the press frame's rollout index
    is_long: np.ndarray        # [n]
    ms: float = 0.0
    info: dict = field(default_factory=dict)

    def index(self) -> dict:
        return {int(r): q for q, r in enumerate(self.rows)}


def pre_protect(ctx: SpecialCtx, q: np.ndarray, fi: np.ndarray) -> np.ndarray:
    """[len(q), L] frames fi [L] in a row's PRE_PROTECT_F frames before its contact (T1, pogo_slam: a hit the hero's
    box takes there does not land, the contact's i-frames win; the certified bounce's rule, for E's body only)."""
    from ssbot.combat.pogo_slam import PRE_PROTECT_F
    c = ctx.contact[q][:, None]
    return (fi[None, :] >= c - PRE_PROTECT_F) & (fi[None, :] < c)


def occ_special(ctx: SpecialCtx, rs, q: np.ndarray, x: np.ndarray, y: np.ndarray, tq: np.ndarray, esc: bool = False
                ) -> np.ndarray:
    """[len(q), L] the special support at points x, y [len(q), L] (planner frames tq [L] s): the others (and E's
    hazards) | E's body outside the pre-protect frames; frames at or past a row's full_from read the full support
    instead (M's estimate back after the certified window)."""
    from ssbot.combat.attack_range import FT
    fi = np.rint(np.asarray(tq, np.float64) / FT).astype(np.int64)
    o = rs.occ_stack_b(ctx.es_o if esc else ctx.st_o, x, y, tq)       # (+ the per-bomb small runes, G2)
    o |= rs._occ_stack(ctx.es_b if esc else ctx.st_b, x, y, tq) & ~pre_protect(ctx, q, fi)
    ff = ctx.full_from[q]
    late = fi[None, :] >= ff[:, None]
    if late.any():
        of = rs.occupied_esc(x, y, tq) if esc else rs.occupied(x, y, tq)
        o = np.where(late, of, o)
    return o


def real_approach_fail(tl, k0: int, xa: float, cy: float, face: int, pj: int, box: np.ndarray, flags: np.ndarray
                       ) -> int:
    """(c) T1's real-box approach check: the hero's box [L, 4] meets the move's attack (hammer) or root box (no
    margin, i-frames skipped) on a frame 1 .. press - 1 (rollout index pj: the press frame; move frame k0 + index).
    0: clear, 2: the attack box, 1: the root box only."""
    js = np.arange(1, min(int(pj), box.shape[0]))
    if not len(js):
        return 0
    live = (flags[js] & kin.F_INVULN) == 0
    hb = box[js]
    for code, which in ((2, "hammer"), (1, "root")):
        b = world_boxes(tl, k0 + js, xa, cy, face, which)
        with np.errstate(invalid="ignore"):
            hit = np.isfinite(b[:, 0]) & (b[:, 0] < hb[:, 2]) & (b[:, 2] > hb[:, 0]) & (b[:, 1] < hb[:, 3])                 & (b[:, 3] > hb[:, 1]) & live
        if hit.any():
            return code
    return 0


__all__ = ["in_family", "MOVE_FAMS", "press_certified", "approach_codes", "contacts", "body_stacks", "SPECIAL_MODE", "MODE_CERTS", "LONG", "L2_ON", "APPR", "BODY_M", "BOARD", "pre_protect", "SpecialCtx", "timeline", "world_boxes",
           "active_last", "row_keys_allowed", "facing_at", "contact_index", "body_extra", "occ_special",
           "real_approach_fail"]
