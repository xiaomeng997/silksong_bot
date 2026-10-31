"""The air chain on alternating slams (task 1v1 SP10b R4, SSBOT_FORUM_TWO_AIRCHAIN, default off; the person,
2026-10-17: "in alternating slams try replacing the follow-up side slash with a down slash - likely it hits both; if
there is still time open the umbrella and take the next special straight from the air", and "before the second
hammer comes down the first Clapper is in its recovery and the second in its antic - both stand still, the air is
safe").

After the playbook's strike on Clapper A (combat.slam_play, the run's way out after the bounce), when the other
Clapper B is in Slam Antic, the script plans one airborne sequence with the hero model (the policy's start state and
keys in flight, ssbot.knowledge.kinematics rollouts):
  drift     a direction key toward B's strike point (STRIKE_U in front of B's centre) for D frames
  down      optional: a down slash on whatever body is below (A's, or B's antic body) in place of the pre-landing side
            slash - its bounce (the pogo: i-frames against enemies for 8 physics steps) keeps her up
  umbrella  optional: the jump pressed in the air (Drifter's Cloak: the float, vy -> -6 u/s) at frame u, held
  strike    down + attack at B's antic frame PRESS_K (the playbook's K_PRESS 47; 46 / 48 tried too): the down slash
            meets B's body in Slam 0 (the hammer itself is passed through; the bounce's i-frames cover it)
Accepted only when, in every timing variant of B's slam (antic 48 / 49 frames, Slam 0 4 / 5, the lunge's phase), the
strike's slash meets B's body in its active frames before she lands, the optional down slash meets a body, and her box
touches no hammer / body box (B's slam timeline, A's box from the STATE) outside the i-frames up to the contact +
SAFE_AFTER. The plan is chosen once (absolute frames), re-checked every tick from the new start state and searched
again when the check fails; none -> the playbook's way out as before (and TWO_HANDOFF / TWO_TIGHT when on). On the
strike press the run passes to B (slam_play: a run on B in its 'after' phase).

    sim = ChainSim(S0, prefix, hold, params, terrain, fo, f)     # built by the policy each tick (AIRCHAIN only)
    plan = search(sim, ctx)                                      # ctx: chain_ctx(...) from the STATE
    ok = check(sim, plan, ctx)
    m = mask_at(plan, F)                                         # the keys for mask frame F
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import numba
import numpy as np

from ssbot.combat.pogo_model import ACTIVE, DOWN, DOWN_ALT
from ssbot.knowledge import kinematics as kin

AIRCHAIN = os.environ.get("SSBOT_FORUM_TWO_AIRCHAIN", "0").strip() == "1"
M_L, M_R, M_D, M_J, M_A = kin.B_LEFT, kin.B_RIGHT, kin.B_DOWN, kin.B_JUMP, kin.B_ATTACK
STRIKE_U = 5.0                  # B's strike point in front of its centre (the playbook's STAND 4.6-5.6 u)
PRESS_K = (47, 46, 48)          # B's antic frames of the strike press (the playbook's K_PRESS first)
DRIFT_F = (0, 5, 10, 16, 24, 34)         # frames of the drift key toward the strike point
UMB_STEP = 4                    # umbrella press frames searched every UMB_STEP frames
UMB_MIN_CANCEL = 11             # the attack cancels the float from the umbrella press + 11 (recorded earliest)
DOWN_CAND = 2                   # down slash press frames kept per drift (the earliest that meet a body)
ATK_CD_F = 19                   # the Wanderer press-to-press minimum (frames)
SAFE_AFTER = 18                 # frames after the strike's contact her box is checked
PRE_PROTECT_F = 2               # a hit up to this many frames before a contact does not land (pogo_slam)
Y_BAND = (3.0, 6.3)             # her box bottom above the floor at the strike's press + 4: kept for the press pass
MAX_PRESS_C = 75                # the strike press at most this many frames ahead (else not searched yet)
MIN_PRESS_C = 6                 # ... at least this many
RESEARCH_F = 3                  # a failed search is tried again after this many frames
FLOOR_Y = 3.015
GROUND_EPS = 0.08               # her box bottom this close to the floor counts as landed
LATE_SLACK = 3                  # the strike's contact at most press + ACTIVE[1] - LATE_SLACK in the plan (a margin for
#                                 the model's error: FP2's lost plans had the contact at press + 8 / 9)
KEEP_F = 12                     # a plan failing its check is kept when no new plan exists and its strike is this close


@dataclass
class ChainSim:
    """The policy's hero model for one tick: rollouts of commanded masks from the mask frame f + 2 on (cmds index 0),
    after the masks in flight (prefix: frames fo + 1 .. f + 1), latched by the oracle's hold filter."""
    start: np.ndarray
    prefix: np.ndarray
    hold: object
    params: object
    terrain: object
    fo: int
    f: int

    @property
    def off(self) -> int:
        """The rollout index of cmds[:, 0] (rollout index 0 = frame fo)."""
        return len(self.prefix) + 1

    def roll(self, cmds: np.ndarray, ev: np.ndarray | None = None) -> kin.Rollout:
        cmds = np.asarray(cmds, np.int64)
        n, T = cmds.shape
        P = len(self.prefix)
        full = np.concatenate([np.broadcast_to(np.asarray(self.prefix, np.int64), (n, P)), cmds], axis=1)
        from ssbot.combat.holdfilter import hold_filter_jit
        lat, _ = hold_filter_jit(np.ascontiguousarray(full), self.hold)
        events = None
        if ev is not None:
            events = np.zeros((n, P + T), np.int64)
            events[:, P:] = ev
        return kin.rollout(self.start, lat, self.params, self.terrain, events=events)


@dataclass
class Ctx:
    """What the plan needs from the STATE (world x, y; B's slam frame at rollout index 0)."""
    b_iid: object
    b_x: float                  # B's centre now (it does not move in its antic)
    b_y: float                  # B's position y
    b_face: int                 # +1: facing right
    kb0: int                    # B's antic frame at rollout index 0 (STATE frame fo)
    a_box: tuple | None         # A's body AABB (x0, y0, x1, y1) now, or None
    hero_x: float
    face: int                   # her facing now (+1 right)
    floor_y: float = FLOOR_Y
    tls: list = field(default_factory=list)   # B's slam timelines (pogo_slam.SlamTimeline variants)


@dataclass
class Plan:
    f0: int                     # the mask frame of cmds index 0 when planned
    dirk: int                   # the drift key (M_L / M_R / 0)
    d_end: int                  # drift until this frame (exclusive)
    f_down: int | None          # the optional first down slash's press frame
    f_umb: int | None           # the umbrella's jump press frame (held to the strike press)
    f_press: int                # the strike press frame
    k_press: int                # B's antic frame of the press
    b_iid: object
    c_down: int | None = None   # predicted contact frames (mask frames)
    c_strike: int | None = None
    pressed_down: int | None = None    # the frames actually sent
    pressed: int | None = None
    inv_until: int | None = None       # mask frame: her box is not checked up to here (a down slash's pogo i-frames,
    #                                    which the tracked start state does not carry: the STATE does not show them)
    n_ok: int = 0               # timing variants that pass

    def row(self) -> list:
        return [self.f0, self.dirk, self.d_end, self.f_down, self.f_umb, self.f_press, self.k_press, self.c_down,
                self.c_strike, self.pressed_down, self.pressed]


_TLS: list = []


def timelines() -> list:
    """B's slam timing variants (the extremes of pogo_slam.SlamTimeline.variants: antic 48 / s0 4 / phase 0.2 and
    antic 49 / s0 5 / phase 0.8)."""
    if not _TLS:
        from ssbot.combat.pogo_slam import SlamTimeline
        _TLS.extend([SlamTimeline.load(antic=48, s0=4, phase=0.2), SlamTimeline.load(antic=49, s0=5, phase=0.8)])
    return _TLS


def mask_at(p: Plan, F: int, first_press: bool = True) -> int:
    """The keys of plan p for mask frame F (the presses on the first tick at or after their frame)."""
    m = p.dirk if F < p.d_end else 0
    if p.f_down is not None and p.pressed_down is None and F >= p.f_down - 1:
        m |= M_D
        if F >= p.f_down:
            m |= M_A
    elif p.f_down is not None and p.pressed_down is not None and F <= p.pressed_down + 4:
        m |= M_D
    if p.f_umb is not None and F >= p.f_umb and (p.pressed is None and F < p.f_press):
        m |= M_J
    if p.pressed is None and F >= p.f_press - 1:
        m |= M_D
        if F >= p.f_press:
            m = (m & ~M_J) | M_A
    elif p.pressed is not None and F <= p.pressed + 2:
        m |= M_D
    return m


def plan_cmds(p: Plan, F0: int, T: int) -> np.ndarray:
    """The plan's masks for frames F0 .. F0 + T - 1 with every press on its planned frame (mask_at frame by frame on
    a tick every frame; tests/test_sp10b.py checks the two agree)."""
    out = np.zeros(T, np.int64)
    d = p.d_end - F0
    if p.dirk and d > 0:
        out[:min(d, T)] |= p.dirk
    if p.f_down is not None:
        if p.pressed_down is None:
            c = max(p.f_down - F0, 0)
            if c - 1 >= 0 and p.f_down - 1 >= F0:
                out[c - 1] |= M_D
            if c < T:
                out[c] |= M_D | M_A
            out[c + 1:c + 5] |= M_D
        else:
            out[:max(p.pressed_down + 5 - F0, 0)] |= M_D
    if p.pressed is None:
        cp = max(p.f_press - F0, 0)
        if p.f_umb is not None:
            out[max(p.f_umb - F0, 0):cp] |= M_J
        if cp - 1 >= 0 and p.f_press - 1 >= F0:
            out[cp - 1] |= M_D
        if cp < T:
            out[cp] = (out[cp] & ~M_J) | M_D | M_A
        out[cp + 1:cp + 3] |= M_D
    else:
        out[:max(p.pressed + 3 - F0, 0)] |= M_D
    return out


def _plan_cmds_loop(p: Plan, F0: int, T: int) -> np.ndarray:
    """plan_cmds by mask_at frame by frame (the reference for the test)."""
    out = np.zeros(T, np.int64)
    q = Plan(**{k: getattr(p, k) for k in p.__dataclass_fields__})
    for i in range(T):
        F = F0 + i
        m = mask_at(q, F)
        if q.f_down is not None and q.pressed_down is None and m & M_A:
            q.pressed_down = F
        elif q.pressed is None and F >= q.f_press and m & M_A:
            q.pressed = F
        out[i] = m
    return out


# ---- geometry (vectorized) ----

@numba.njit(cache=True)
def _sat(px, py, hx, hy, rect, out):
    """out[m] |= the convex polygon (px, py) at (hx[m], hy[m]) overlaps the AABB rect[m] (x0, y0, x1, y1; nan: none);
    separating axes x, y and the polygon's edge normals (touching does not count)."""
    V = px.shape[0]
    for m in range(hx.shape[0]):
        x0, y0, x1, y1 = rect[m, 0], rect[m, 1], rect[m, 2], rect[m, 3]
        if not (x0 == x0) or out[m]:
            continue
        ok = True
        lo = 1e18
        hi = -1e18
        for v in range(V):
            a = px[v] + hx[m]
            lo = min(lo, a)
            hi = max(hi, a)
        if hi <= x0 + 1e-9 or x1 <= lo + 1e-9:
            continue
        lo = 1e18
        hi = -1e18
        for v in range(V):
            a = py[v] + hy[m]
            lo = min(lo, a)
            hi = max(hi, a)
        if hi <= y0 + 1e-9 or y1 <= lo + 1e-9:
            continue
        for i in range(V):
            j = (i + 1) % V
            ax = -(py[j] - py[i])
            ay = px[j] - px[i]
            plo = 1e18
            phi = -1e18
            for v in range(V):
                a = (px[v] + hx[m]) * ax + (py[v] + hy[m]) * ay
                plo = min(plo, a)
                phi = max(phi, a)
            c0 = x0 * ax + y0 * ay
            c1 = x1 * ax + y0 * ay
            c2 = x1 * ax + y1 * ay
            c3 = x0 * ax + y1 * ay
            clo = min(min(c0, c1), min(c2, c3))
            chi = max(max(c0, c1), max(c2, c3))
            if phi <= clo + 1e-9 or chi <= plo + 1e-9:
                ok = False
                break
        if ok:
            out[m] = True


def _b_boxes(ctx: Ctx, tl, idx: np.ndarray, which: str) -> np.ndarray:
    """B's world boxes [len(idx), 4] (x0, y0, x1, y1) at rollout indices idx (the box of slam frame kb0 + i - 1:
    pogo_slam.predict_press's one-frame lag), nan where none."""
    k = ctx.kb0 + np.asarray(idx) - 1
    kk = np.clip(k, 0, len(tl.disp) - 1)
    k_now = int(np.clip(ctx.kb0, 0, len(tl.disp) - 1))
    x_anchor = ctx.b_x - ctx.b_face * tl.disp[k_now]
    b = tl.world(kk, which)                                 # x0, x1, y0, y1 in its frame (lunge applied)
    xa = x_anchor + ctx.b_face * b[..., 0]
    xb = x_anchor + ctx.b_face * b[..., 1]
    return np.stack([np.minimum(xa, xb), ctx.b_y + b[..., 2], np.maximum(xa, xb), ctx.b_y + b[..., 3]], axis=-1)


def _aabb_hit(hb: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    ok = np.isfinite(boxes).all(axis=-1)
    with np.errstate(invalid="ignore"):
        return ok & (boxes[..., 0] < hb[..., 2]) & (boxes[..., 2] > hb[..., 0]) & (boxes[..., 1] < hb[..., 3]) & (
            boxes[..., 3] > hb[..., 1])


def _contacts(ro: kin.Rollout, press_i: np.ndarray, faces: np.ndarray, ctx: Ctx, tl, targets: str) -> np.ndarray:
    """[N] the first rollout index where the slash pressed at rollout index press_i[n] meets a target (both slash
    shapes), -1 none: the swing airborne (F_ATTACKING on the press frame or the next, not grounded the frame before),
    not from the first grounded frame after the press. targets: 'b' (B's root box), 'ab' (A's box or B's)."""
    fl = ro.flags
    N, T1 = fl.shape
    rows = np.arange(N)
    pi = np.asarray(press_i, np.int64)

    def c(a):
        return np.clip(a, 0, T1 - 1)
    swung = ((fl[rows, c(pi)] | fl[rows, c(pi + 1)]) & kin.F_ATTACKING) != 0
    ok = (pi + 1 < T1) & swung & ((fl[rows, c(pi - 1)] & kin.F_GROUND) == 0)
    J = np.arange(ACTIVE[0], ACTIVE[1] + 1)
    idx = pi[:, None] + J[None, :]                            # [N, 7]
    idc = c(idx)
    gnd = np.cumsum((fl & kin.F_GROUND) != 0, axis=1)         # grounded frames up to each index
    landed = gnd[rows[:, None], idc] - gnd[rows, c(pi - 1)][:, None] > 0
    valid = ok[:, None] & (idx < T1) & ~landed
    pos = ro.pos[rows[:, None], idc]                          # [N, 7, 2]
    rb = _b_boxes(ctx, tl, idc.ravel(), "root")
    hx, hy = pos[..., 0].ravel(), pos[..., 1].ravel()
    hit = np.ones(hx.shape[0], bool)
    fr = np.repeat(np.asarray(faces), len(J))
    ab = None if (targets != "ab" or ctx.a_box is None) else np.ascontiguousarray(
        np.broadcast_to(np.asarray(ctx.a_box, float), (hx.shape[0], 4)))
    for poly in (DOWN, DOWN_ALT):                             # both shapes (the alternation unknown)
        h = np.zeros(hx.shape[0], bool)
        for face in (1, -1):
            sel = fr == face
            if not sel.any():
                continue
            px = np.ascontiguousarray(poly[:, 0] * face)
            py = np.ascontiguousarray(poly[:, 1])
            hs = np.zeros(int(sel.sum()), bool)
            hxs, hys = np.ascontiguousarray(hx[sel]), np.ascontiguousarray(hy[sel])
            _sat(px, py, hxs, hys, np.ascontiguousarray(rb[sel]), hs)
            if ab is not None:
                _sat(px, py, hxs, hys, np.ascontiguousarray(ab[sel]), hs)
            h[sel] = hs
        hit &= h
    hit = hit.reshape(idx.shape) & valid
    return np.where(hit.any(axis=1), idx[rows, np.argmax(hit, axis=1)], -1)


def _first_unsafe(ro: kin.Rollout, ctx: Ctx, tl, contacts: np.ndarray, i_end: np.ndarray,
                  i_from: np.ndarray | None = None) -> np.ndarray:
    """[N] the first rollout index in 1 .. i_end[n] where her box meets B's hammer / body or A's box outside the
    i-frames (F_INVULN) and the PRE_PROTECT_F frames before a contact (contacts [N, C], -1 none); -1 none."""
    N, T1 = ro.flags.shape
    idx = np.arange(T1)
    hb = ro.box                                                 # [N, T1, 4]
    bad = _aabb_hit(hb, _b_boxes(ctx, tl, idx, "hammer")[None]) | _aabb_hit(hb, _b_boxes(ctx, tl, idx, "root")[None])
    if ctx.a_box is not None:
        bad |= _aabb_hit(hb, np.asarray(ctx.a_box, float)[None, None])
    bad &= (ro.flags & kin.F_INVULN) == 0
    bad[:, 0] = False
    if i_from is not None:
        bad &= idx[None, :] >= np.asarray(i_from)[:, None]
    bad &= idx[None, :] <= np.asarray(i_end)[:, None]
    for col in range(contacts.shape[1]):
        cc = contacts[:, col][:, None]
        bad &= ~((cc >= 0) & (idx[None, :] >= cc - PRE_PROTECT_F) & (idx[None, :] < cc))
    return np.where(bad.any(axis=1), np.argmax(bad, axis=1), -1)


# ---- the search ----

def _plans(sim: ChainSim, ctx: Ctx, F0: int, press_k: tuple = PRESS_K) -> list[Plan]:
    """The candidate grid at mask frame F0 (cmds index 0)."""
    kb_mask = ctx.kb0 + (F0 - sim.fo)                       # B's antic frame at F0
    tx = ctx.b_x + ctx.b_face * STRIKE_U
    dirk = M_R if tx > ctx.hero_x else M_L
    out = []
    for kp in press_k:
        c_p = kp - kb_mask
        if not MIN_PRESS_C <= c_p <= MAX_PRESS_C:
            continue
        for D in DRIFT_F:
            if D > c_p:
                continue
            ups = [None] + list(range(0, max(c_p - UMB_MIN_CANCEL + 1, 0), UMB_STEP))
            for u in ups:
                out.append(Plan(F0, dirk if D else 0, F0 + D, None, None if u is None else F0 + u, F0 + c_p, kp,
                                ctx.b_iid))
    return out


def _down_candidates(sim: ChainSim, ctx: Ctx, F0: int, tl) -> dict:
    """Per drift D: the earliest DOWN_CAND frames (cmds index) where a down slash meets a body (A's or B's), from the
    drift-only rollouts (no umbrella, no strike); the press at least ATK_CD_F before the strike at K_PRESS 47."""
    kb_mask = ctx.kb0 + (F0 - sim.fo)
    last = 47 - kb_mask - ATK_CD_F
    if last < 0:
        return {}
    tx = ctx.b_x + ctx.b_face * STRIKE_U
    dirk = M_R if tx > ctx.hero_x else M_L
    rows = [(D, c) for D in DRIFT_F for c in range(0, last + 1)]
    T = last + ACTIVE[1] + 3
    cm = np.zeros((len(rows), T), np.int64)
    for n, (D, c) in enumerate(rows):
        cm[n, :min(D, T)] = dirk if D else 0
        if c > 0:
            cm[n, c - 1] |= M_D
        cm[n, c] |= M_D | M_A
        cm[n, c + 1:c + 5] |= M_D
    ro = sim.roll(cm)
    faces = np.array([((1 if dirk == M_R else -1) if D else ctx.face) for D, _ in rows])
    js = _contacts(ro, np.array([sim.off + c for _, c in rows]), faces, ctx, tl, "ab")
    out: dict = {}
    for n, (D, c) in enumerate(rows):
        if js[n] >= 0 and len(out.get(D, ())) < DOWN_CAND:
            out.setdefault(D, []).append(c)
    return out


def _face(p: Plan, ctx: Ctx) -> int:
    """Her facing at the plan's presses: the drift key's once it was held, else hers now."""
    return (1 if p.dirk == M_R else -1) if p.dirk and p.d_end > p.f0 else ctx.face


_CHAIN_ROLL_AUTHORITY=ChainSim.roll
_KIN_ROLLOUT_AUTHORITY=kin.rollout
_CONTACTS_AUTHORITY=_contacts
_UNSAFE_AUTHORITY=_first_unsafe


def _single_pass2_origin(sim):
    # Filtering command lanes must never change which start/hold lane they
    # receive. The B2 control model is explicitly one broadcast origin.
    try:
        if type(sim.start) is not np.ndarray or sim.start.shape not in ((kin.K,),(kin.K,1)):return False
        if sim.start.dtype.kind not in "fiu" or type(sim.prefix) is not np.ndarray or sim.prefix.ndim!=1:return False
        if type(sim.hold) is not kin.HoldState or type(sim.params) is not kin.HeroParams or type(sim.terrain) is not kin.Terrain2D:return False
        return all(type(a) is np.ndarray and a.ndim==2 and a.shape[0]==1
                   for a in (sim.hold.latched,sim.hold.desired,sim.hold.pending,sim.hold.age))
    except (TypeError,AttributeError):return False


def _pass2_rows(ro,sel):
    # Even a complete row set is copied: a later timeline cannot mutate the
    # stored physics through an all-row alias if native checks evolve.
    return kin.Rollout(ro.phys[sel],ro.pos[sel],ro.vel[sel],ro.mode[sel],ro.flags[sel],ro.final[:,sel],ro.box[sel])


def evaluate(sim: ChainSim, ctx: Ctx, plans: list[Plan], F0: int, *, reuse_no_event: bool = False) -> list[Plan]:
    """The plans that pass in every timeline of ctx.tls (contact on B, the optional down slash's contact, safety)."""
    if not plans:
        return []
    off = sim.off
    T = max(p.f_press - F0 for p in plans) + ACTIVE[1] + SAFE_AFTER + 2
    cm = np.stack([plan_cmds(p, F0, T) for p in plans])
    good = np.ones(len(plans), bool)
    c_down = np.full(len(plans), -1)
    c_strike = np.full(len(plans), -1)
    faces = np.array([_face(p, ctx) for p in plans])
    has_d = np.array([p.f_down is not None and p.pressed_down is None for p in plans])
    p_down = np.array([off + ((p.f_down if p.f_down is not None else F0) - F0) for p in plans])
    p_strike = np.array([off + (p.f_press - F0) for p in plans])
    ro0 = sim.roll(cm[has_d]) if has_d.any() else None     # pass 1 (no events): the same in every timeline
    # Only the explicitly opted-in native, lane-independent no-event pass may
    # be reused. Every timeline still gets its own contact and hit/safety pass.
    reuse=(reuse_no_event is True and not has_d.any() and type(sim) is ChainSim and _single_pass2_origin(sim) and
           getattr(sim.roll,"__func__",None) is _CHAIN_ROLL_AUTHORITY and kin.rollout is _KIN_ROLLOUT_AUTHORITY and
           _contacts is _CONTACTS_AUTHORITY and _first_unsafe is _UNSAFE_AUTHORITY)
    pass2=None
    for tl in ctx.tls:
        ev = np.zeros_like(cm)
        if ro0 is not None:
            d_i = np.flatnonzero(has_d)
            j = _contacts(ro0, p_down[d_i], faces[d_i], ctx, tl, "ab")
            good[d_i[j < off]] = False
            hit = d_i[j >= off]
            c_down[hit] = j[j >= off]
            ev[hit, c_down[hit] - off] |= kin.EV_POGO           # the bounce on the contact frame (pogo_model EV_OFF 0)
        # pass 2: the strike's contact on B (with the down slash's bounce)
        sel = np.flatnonzero(good)
        if not len(sel):
            return []
        ro = _pass2_rows(pass2,sel) if pass2 is not None else sim.roll(cm[sel],ev[sel])
        if reuse and pass2 is None and len(sel)==len(plans) and type(ro) is kin.Rollout and not ro.variants and all(
                getattr(ro,k) is None for k in ("var_box","var_mode","var_flags","bound","flags_all","flags_any")):
            pass2=ro
        j = _contacts(ro, p_strike[sel], faces[sel], ctx, tl, "b")
        good[sel[j < off]] = False
        hit = sel[j >= off]
        c_strike[hit] = j[j >= off]
        late = c_strike[sel] > p_strike[sel] + ACTIVE[1] - LATE_SLACK
        good[sel[(j >= off) & late]] = False
        ev[hit, c_strike[hit] - off] |= kin.EV_POGO
        sel = np.flatnonzero(good)
        if not len(sel):
            return []
        # pass 3: safety with both bounces; no landing before the strike's contact
        ro = sim.roll(cm[sel], ev[sel])
        # grounded: the flag, or her box bottom at the floor (FP2, 3eb3914: a plan whose umbrella press came 1 frame
        # above the floor became a buffered ground jump - the model never set the flag on the landing frame - and
        # the run closed on the landing)
        gnd = ((ro.flags & kin.F_GROUND) != 0) | (ro.box[..., 1] <= FLOOR_Y + GROUND_EPS)
        ii = np.arange(ro.flags.shape[1])[None, :]
        landed = (gnd & (ii >= off) & (ii <= c_strike[sel][:, None])).any(axis=1)
        i_from = np.array([0 if plans[i].inv_until is None else off + plans[i].inv_until - F0 + 1 for i in sel])
        bad = _first_unsafe(ro, ctx, tl, np.stack([c_down[sel], c_strike[sel]], axis=1), c_strike[sel] + SAFE_AFTER,
                            i_from)
        good[sel[landed | (bad >= 0)]] = False
    out = []
    for i in np.flatnonzero(good):
        p = plans[i]
        p.c_down = None if c_down[i] < 0 else F0 + int(c_down[i]) - off
        p.c_strike = F0 + int(c_strike[i]) - off
        out.append(p)
    return out


_EVALUATE_AUTHORITY=evaluate


def search(sim: ChainSim, ctx: Ctx) -> Plan | None:
    """The chain for this tick (mask frame F0 = f + 2), or None: plans with a down slash first (more hits), then the
    strike at K_PRESS 47 before 46 / 48, the shortest drift, no umbrella before an umbrella, the latest umbrella."""
    F0 = sim.f + 2
    downs = None
    ok: list = []
    for press_k in (PRESS_K[:1], PRESS_K[1:]):               # K_PRESS 47 first; 46 / 48 only when it has none
        base = _plans(sim, ctx, F0, press_k)
        if not base:
            continue
        if downs is None:
            downs = _down_candidates(sim, ctx, F0, ctx.tls[0])
        plans = list(base)
        for p in base:
            D = p.d_end - F0
            for c in downs.get(D, ()):
                if F0 + c + ATK_CD_F <= p.f_press and (p.f_umb is None or p.f_umb > F0 + c + 4):
                    plans.append(Plan(p.f0, p.dirk, p.d_end, F0 + c, p.f_umb, p.f_press, p.k_press, p.b_iid))
        ok = evaluate(sim, ctx, plans, F0)
        if ok:
            break
    if not ok:
        return None
    pref = {k: i for i, k in enumerate(PRESS_K)}
    ok.sort(key=lambda p: (p.f_down is None, pref[p.k_press], p.c_strike - p.f_press, p.d_end - F0,
                           p.f_umb is not None, -(p.f_umb or 0)))
    best = ok[0]
    best.n_ok = len(ok)
    return best


def check(sim: ChainSim, ctx: Ctx, p: Plan) -> bool:
    """The committed plan from this tick's start state still passes (every timeline)."""
    F0 = sim.f + 2
    q = Plan(**{k: getattr(p, k) for k in p.__dataclass_fields__})
    q.f0 = F0
    if q.pressed_down is not None and q.inv_until is None:
        # sent: its bounce (if it landed) is in the start state, its i-frames are not (contact <= press + 9, then
        # 8 physics steps ~ 10 frames)
        q.inv_until = q.pressed_down + ACTIVE[1] + 10
    return bool(evaluate(sim, ctx, [q], F0))


__all__ = ["AIRCHAIN", "ChainSim", "Ctx", "Plan", "timelines", "mask_at", "plan_cmds", "search", "check", "evaluate"]


def warm(params) -> float:
    """Compile / load every numba path of the chain before the fight (a synthetic double slam: her falling 2.4 u in
    front of A's Idle body, B 9.4 u away in Slam Antic): search (both press passes) and check. The first chain of a
    worker process otherwise paid the compile inside a tick (fixed-point FP2, 3eb3914: one 758 ms tick, the brain-lost
    watchdog paused the game: HARNESS_FAIL). Returns the seconds spent."""
    import time
    from ssbot.knowledge.kinematics import HoldState, Terrain2D
    t0 = time.perf_counter()
    terr = Terrain2D.from_boxes([(-200.0, FLOOR_Y - 10.0, 260.0, FLOOR_Y), (0.0, 0.0, 14.01, 40.0),
                                 (48.99, 0.0, 70.0, 40.0)])
    for kb, prefix in ((5, np.zeros(1, np.int64)), (30, np.zeros(2, np.int64))):
        S = kin.initial_state(params, 37.0, 4.568 + 4.8, vy=-19.0, facing=1, ground=False)
        sim = ChainSim(S, prefix, HoldState.idle(1), params, terr, 1000, 1000 + len(prefix) - 1)
        ctx = Ctx(b_iid=8, b_x=44.0, b_y=7.449, b_face=-1, kb0=kb, a_box=(33.26, 3.02, 36.85, 6.92), hero_x=37.0,
                  face=1, tls=timelines())
        p = search(sim, ctx)
        if p is not None:
            check(sim, ctx, p)
        evaluate(sim, ctx, [Plan(sim.f + 2, M_R, sim.f + 6, None, sim.f + 4, sim.f + 30, 47, 8)], sim.f + 2)
    return time.perf_counter() - t0
