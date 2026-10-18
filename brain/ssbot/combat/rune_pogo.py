"""The big rune's pogo tier (task 1v1 SP11a, SSBOT_FORUM_TWO_RUNETIER, default off; the person's sequence, the lead's
NOTE 5 of 2026-10-17 - "big rune: no luring at all, just stay in the idle one's face and slash it", "as long as I am on
top of the second Clapper's head I am never hit by [the landing]", "only the circle needs the down-slash timing"; the
spec C:/ssbot/data/m2_play/bigrune/answer.txt sections 2-4 with the lure / Clawline parts replaced by NOTE 4 / 5).

F = the focus doing its escape jump CAST at its wall (Cast Slam Antic with its back <= 6.2 u, she within 8.3 u), B = the
other Clapper. Frames: A = F's Jump Aim (the first Jump / Air STATE; Cast Slam Antic 2 + 40, else the antic + 55), L =
F's landing (its Slam 2), u centre to centre (her box centre, its transform), sgn = the world direction from F to B.
F lands at L = x0 + 0.916 clamp(p - 5, +-12) (+ the wall rule; p = her x ahead of x0 at A - 1); its landing hammer
(Slam Collider 2: (0.67, 0.6) (2.4, 5.0) (4.07, 6.9) (6.09, 5.8) (7.76, 0.1) (7.17, -0.7) u along its facing / above
the floor, 30 recorded landings) is out L .. L + 12; its rune circle (r 7.19, centre 0.34 u above the floor, L + 6.48 /
6.75 u along its facing: a DOME 7.53 u high at its centre) is lit at L + 65 .. 72 (p95 first lit L + 77).

The facts behind the plan (SP11a, C:/ssbot/data/m2_play/sp11/s1):
  - the down-spike i-frames (cState.downspikeInvulnerabilitySteps 8 physics steps from a pogo contact, ~9.6 frames)
    block the rune slam (hazard_type ENEMY, no noBounceCooldown): 20261016_144051 i1 e0 f 3252230 - her box 1.2 - 2.2 u
    inside the lit circle for 6 frames with steps 5 .. 1, the hit on the first frame with steps 0 (iframe_probe);
  - a pogo on a Clapper's head (contact with her box bottom ~4.5 - 5.2 u above the floor) and the umbrella (the jump
    pressed in the air) ~10 frames later float her box bottom at 7.6 - 8.9 u for ~40 frames (recorded 3456616: >= 7.6
    from + 13 to + 54); the hero model reaches the same, 0.2 - 0.3 u high (float_check);
  - so above the dome's top (7.53 u) the circle cannot reach her anywhere, and above B's head (B >= L + 6.75 when she
    stood in B's face at A - 1) the landing hammer cannot.

The run (TwoPlay.esc mode "pogo"; L2 holds B):
  go     F's antic .. the jump: walk (a dash when far) to B's face (spot u from B's centre on F's side) and slash B when
         the side slash meets its body (slash=1: the person's "slash B continuously" through F's lock)
  far    at A: F's landing is known - her spot at B clear of the hammer and the circle (the spec's tier 1 / "no pogo"):
         the run ends, L2 keeps B (the default play)
  air    from the jump (pressed jump_lead frames before the predicted A) on: the altitude controller - every tick the
         hero model (the policy's start state and keys in flight: air_chain.ChainSim) rolls the plan "keep" (the
         umbrella held, a drift key toward the x it wants) and, when that meets a danger, the plans with ONE down slash
         onto B's head (the press timed so the slash meets B's body box, both slash shapes, before her box touches it),
         the bounce (EV_POGO) and the umbrella umb_f frames after the contact; a plan is safe when to the horizon her
         box meets neither B's body (outside the i-frames), nor F's landing hammer (its polygon around L, L - 3 .. L +
         13), nor the circle's dome (lit0 - 2 .. lit1 + 2) by dome_m; the latest safe press wins (the float lasts
         longest); none safe: the plan whose first danger comes latest. The drift target: above B's centre, behind B
         (its back side) while B slams.
  end    the circle seen lit then unlit, or L + end_f; F or B gone; she hurt (stats) -> the default play.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

import numpy as np

from ssbot.combat import cast_stab as _cs
from ssbot.combat import slam_play as _sp
from ssbot.combat.pogo_model import DOWN, DOWN_ALT
from ssbot.knowledge import kinematics as kin

CLAPPER = _sp.CLAPPER
M_L, M_R, M_D, M_J, M_A, M_DASH = _sp.M_L, _sp.M_R, _sp.M_D, _sp.M_J, _sp.M_A, _sp.M_DASH
SEND_AHEAD = _sp.SEND_AHEAD
WALK_U = _sp.WALK_U
WALL_L, WALL_R = _sp.WALL_L, _sp.WALL_R
FLOOR = 3.015
HALF_W = 0.25
RUNE_R = 7.187
RUNE_CY = 0.34                 # the dome's centre above the floor
# F's landing hammer (Slam Collider 2) along its facing from its centre / above the floor (convex)
SC2 = np.array([[0.67, 0.6], [2.4, 5.0], [4.07, 6.9], [6.09, 5.8], [7.76, 0.1], [7.17, -0.7]])
B_FREE = ("Idle", "Walk", "Slam Antic", "Spell Antic", "Cast 1", "Cast 2", "Slam Recover", "After Scuttle",
          "Dmg Attack", None)                       # B's body a pogo target (not lunging, jumping or sliding)
B_SLAM = ("Slam Antic", "Slam 0", "Slam 1", "Slam Effects?", "Slam 2")
B_BUSY_START = ("Jump Antic", "Cast Slam Antic", "Cast Slam Antic 2", "Jump Aim", "Cast Jump", "Jump", "Air",
                "Spell Antic", "Cast 1", "Cast 2", "Slam Antic", "Slam 0", "Slam 1", "Slam Effects?", "Slam 2",
                "Slam Recover")


@dataclass
class RtCfg:
    """SSBOT_FORUM_TWO_RUNETIER_SET="spot=3.0,umb_f=10": trial overrides."""
    spot: float = 3.0           # her centre from B's centre on F's side in the antic (B's front 2.25 + her 0.25 + 0.5)
    slash: int = 1              # 1: slash B through F's lock (the person); 0: no hit on B while F's flag is on
    dash_u: float = 4.5         # the walk to the spot dashes when farther than this
    jump_lead: int = 2          # the jump pressed this many frames before the predicted A (her x at A - 1 is the spot)
    a_csa2: int = 40            # A = Cast Slam Antic 2's first frame + this (39-40 in 1433 / 1533)
    a_antic: int = 55           # ... else the antic's first frame + this
    land_f: int = 53            # L = A + this (the flight p50 53-55)
    lit0: int = 64              # the circle lit from L + this (first lit 65 in 1,000 of ~1,400, 74-77 in ~140) ...
    lit1: int = 84              # ... to L + this (lit 7-8 frames; the late ones, first lit 74 - 77, end ~L + 84)
    umb_f: int = 10             # the umbrella (the jump pressed in the air) this many frames after a contact
    dome_m: float = 0.45        # her box bottom above the dome by this (the model floats 0.2 - 0.3 u high)
    hammer_m: float = 0.3       # her box off F's landing hammer polygon by this
    body_m: float = 0.1         # ... off B's body box
    horizon: int = 120          # the plans' rollout length (frames)
    end_f: int = 95             # the run ends L + this at the latest (or the circle's burst)
    min_db: float = 6.5         # B at least this far from F (its face spot off F's body)
    far_m: float = 0.5          # "far": her spot this clear of the hammer / the circle edge
    research: int = 1           # plan every this many frames in the air


def _cfg() -> RtCfg:
    c = RtCfg()
    for kv in os.environ.get("SSBOT_FORUM_TWO_RUNETIER_SET", "").replace(";", ",").split(","):
        if "=" not in kv:
            continue
        k, v = (x.strip() for x in kv.split("=", 1))
        if not hasattr(c, k):
            raise KeyError(f"SSBOT_FORUM_TWO_RUNETIER_SET: unknown key {k!r}")
        setattr(c, k, type(getattr(c, k))(float(v)))
    return c


def face_of(e: dict) -> int:
    return 1 if e.get("flipX") else -1


def body_box(e: dict) -> tuple[float, float, float, float]:
    """A Clapper's body AABB (x0, y0, x1, y1): its collider ("Song Heavy Sentry", "(2)" / "(3)" in wave 13), else
    the Idle box from its facing."""
    for col in e.get("colliders") or ():
        nm = str(col.get("name") or "")
        if (nm == CLAPPER or nm.startswith(CLAPPER + " (")) and col.get("enabled") and col.get("verts_world"):
            xs, ys = col["verts_world"][0::2], col["verts_world"][1::2]
            return float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))
    cx, cy, fc = float(e["pos"][0]), float(e["pos"][1]), face_of(e)
    a, b = cx + fc * _sp.BODY_FRONT, cx - fc * _sp.BODY_BACK
    return min(a, b), cy - 4.43, max(a, b), cy - 0.53


def landing(x0: float, hx: float, face: int) -> float:
    from ssbot.combat import jump_behind as _jb
    return float(_jb.landing(x0, hx, face))


def rune_centre(L: float, face: int) -> float:
    """The circle's centre x from F's landing x and its jump facing (6.48 u jumping left, 6.75 right)."""
    return L + face * (6.75 if face > 0 else 6.48)


def dome_top(dx: np.ndarray | float) -> np.ndarray | float:
    """The dome's height above the floor at |dx| from its centre (0 outside)."""
    d = np.abs(np.asarray(dx, float))
    return np.where(d < RUNE_R, RUNE_CY + np.sqrt(np.maximum(RUNE_R * RUNE_R - d * d, 0.0)), -1.0)


@dataclass
class Ctx:
    """What the plans need from the STATE (world x / y)."""
    F0: int                       # the mask frame of cmds index 0 (f + 2)
    b_box: tuple                  # B's body box now (x0, y0, x1, y1)
    b_x: float
    b_ok: bool                    # B's body is a pogo target now
    tx: float                     # the drift target x
    face: int                     # her facing now (+1 right)
    L: float | None = None        # F's landing x (predicted / seen) and frame, its jump facing
    f_L: int | None = None
    fface: int = 1
    rc: float | None = None       # the circle's centre x (seen or predicted), its lit window (mask frames)
    lit: tuple | None = None
    a_frame: int | None = None    # F's Jump Aim frame (predicted) and whether it is seen
    a_seen: bool = False
    ground: bool = False
    atk_ready_f: int = 0          # the first mask frame the attack can be pressed
    gliding: bool = False         # the umbrella is open now
    j_held: bool = False          # the jump key is latched now
    f_box: tuple | None = None    # F's body box after its landing (its Slam 2 / Recover / Idle)
    b_hammer: tuple | None = None  # B's slam hammer: (mask frame from, to, x0, x1, top) while B slams
    f_fall: tuple | None = None   # F's flight: (its aim's mask frame, its landing's, x0, L, its facing) - the moving body


# F's body in the jump cast's flight (5 recorded flights, 53-55 frames): its box bottom above the floor every 6 frames
# from the aim (x linear from the take-off to the landing; the box 3.8 u high, 1.34 u behind / 2.25 u in front)
FLIGHT_Y0 = np.array([0.8, 4.1, 6.6, 8.2, 9.0, 8.9, 8.0, 6.3, 3.7, 0.3, 0.0])
# B's slam hammer (Slam Collider 1 front -1.91 .. +6.24 u, up to 7.57 u above the floor; the lunge 3 - 4 u forward
# from Slam 0) from its antic frame HAMMER_K to the end of Slam 2's landing collider (Slam Collider 2, <= 7.08 u)
HAMMER_K = (46, 72)
HAMMER_X = (-2.2, 6.24 + 4.3)
HAMMER_TOP = 7.57


@dataclass
class Plan:
    kind: str                     # keep / drop / up
    dirk: int = 0                 # the drift key (M_L / M_R / 0) ...
    d0: int = 0                   # ... held from this mask frame ...
    d1: int = 0                   # ... to this one (exclusive)
    jump: tuple | None = None     # up: the jump's press frame and hold (frames)
    press: int | None = None      # the down slash's press frame (mask frame)
    contact: int | None = None    # its predicted contact (mask frame)
    umb: int | None = None        # the umbrella's press frame (held to the horizon)
    hold_j: bool = False          # keep: the jump (umbrella) held from the first frame
    bad: int | None = None        # the first danger (mask frame), None = none to the horizon
    why: str = ""

    def row(self) -> list:
        return [self.kind, self.dirk, self.d0, self.d1, self.jump, self.press, self.contact, self.umb, self.bad,
                self.why]

    def key(self) -> tuple:
        return (self.kind, self.dirk, self.d0, self.d1, self.jump, self.press, self.umb, self.hold_j)


def plan_cmds(p: Plan, F0: int, T: int) -> np.ndarray:
    """The plan's masks for mask frames F0 .. F0 + T - 1."""
    out = np.zeros(T, np.int64)
    if p.dirk:
        a, b = max(p.d0 - F0, 0), max(min(p.d1 - F0, T), 0)
        if b > a:
            out[a:b] |= p.dirk
    if p.hold_j:
        stop = (p.press - F0) if p.press is not None else T
        out[:max(min(stop, T), 0)] |= M_J
    if p.jump is not None:
        j0, H = p.jump
        a = max(j0 - F0, 0)
        out[a:max(min(j0 + H - F0, T), 0)] |= M_J
    if p.press is not None:
        c = p.press - F0
        if 0 <= c - 1 < T:
            out[c - 1] |= M_D
        if 0 <= c < T:
            out[c] = (out[c] & ~M_J) | M_D | M_A
        out[max(c + 1, 0):max(min(c + 5, T), 0)] |= M_D
        out[max(c, 0):max(min(c + 5, T), 0)] &= ~M_J
    if p.umb is not None:
        a = max(p.umb - F0, 0)
        out[a:T] |= M_J
    return out


def mask_at(p: Plan, F: int) -> int:
    """The plan's keys for mask frame F."""
    return int(plan_cmds(p, F, 1)[0])


# ---- geometry on rollouts (vectorized; air_chain's SAT kernel) ----

def _poly_hits(px: np.ndarray, py: np.ndarray, hx: np.ndarray, hy: np.ndarray, rect: np.ndarray) -> np.ndarray:
    from ssbot.combat.air_chain import _sat
    out = np.zeros(hx.shape[0], bool)
    _sat(np.ascontiguousarray(px, float), np.ascontiguousarray(py, float), np.ascontiguousarray(hx, float),
         np.ascontiguousarray(hy, float), np.ascontiguousarray(rect, float), out)
    return out


def slash_hits(ro: kin.Rollout, faces: np.ndarray, box: tuple, i0: int) -> np.ndarray:
    """[N, T1] the down slash (BOTH shapes: the alternation unknown) placed at her transform on frame i would meet the
    box (frames before i0 False)."""
    N, T1 = ro.flags.shape
    pos = ro.pos
    hx, hy = pos[..., 0].ravel(), pos[..., 1].ravel()
    rect = np.broadcast_to(np.asarray(box, float), (hx.shape[0], 4))
    fr = np.repeat(np.asarray(faces), T1)
    hit = np.ones(hx.shape[0], bool)
    for poly in (DOWN, DOWN_ALT):
        h = np.zeros(hx.shape[0], bool)
        for face in (1, -1):
            sel = fr == face
            if sel.any():
                h[sel] = _poly_hits(poly[:, 0] * face, poly[:, 1], hx[sel], hy[sel], rect[sel])
        hit &= h
    hit = hit.reshape(N, T1)
    hit[:, :i0] = False
    return hit


def box_hits(ro: kin.Rollout, box: tuple, pad: float = 0.0) -> np.ndarray:
    """[N, T1] her box meets the AABB (grown by pad)."""
    b = ro.box
    x0, y0, x1, y1 = box
    return (b[..., 0] < x1 + pad) & (b[..., 2] > x0 - pad) & (b[..., 1] < y1 + pad) & (b[..., 3] > y0 - pad)


def hammer_hits(ro: kin.Rollout, L: float, face: int, pad: float) -> np.ndarray:
    """[N, T1] her box meets F's landing hammer polygon at L (grown by pad: her box grown instead)."""
    N, T1 = ro.flags.shape
    px = L + face * SC2[:, 0]
    py = FLOOR + SC2[:, 1]
    b = ro.box.reshape(-1, 4).copy()
    b[:, 0] -= pad
    b[:, 1] -= pad
    b[:, 2] += pad
    b[:, 3] += pad
    z = np.zeros(b.shape[0])
    return _poly_hits(px, py, z, z, b).reshape(N, T1)


def dome_hits(ro: kin.Rollout, rc: float, m: float) -> np.ndarray:
    """[N, T1] her box bottom below the dome (+ m) at her box's x nearest the centre."""
    b = ro.box
    dx = np.maximum(np.maximum(b[..., 0] - rc, rc - b[..., 2]), 0.0)
    top = dome_top(dx)
    return (top > 0) & (b[..., 1] - FLOOR < top + m)


class Planner:
    """One tick's plans over the hero model (air_chain.ChainSim: start state at frame fo, the keys in flight)."""

    def __init__(self, sim, ctx: Ctx, cfg: RtCfg):
        self.sim, self.c, self.cfg = sim, ctx, cfg
        self.off = sim.off                      # rollout index of mask frame F0
        self.T = cfg.horizon
        self.last_ro = None

    def _i(self, F: int) -> int:
        return self.off + (F - self.c.F0)

    def _F(self, i: int) -> int:
        return self.c.F0 + (i - self.off)

    def _faces(self, plans: list[Plan]) -> np.ndarray:
        return np.array([((1 if p.dirk == M_R else -1) if (p.dirk and p.press is not None and p.d0 < p.press)
                          else self.c.face) for p in plans])

    def _roll(self, plans: list[Plan], ev: np.ndarray | None = None) -> kin.Rollout:
        cm = np.stack([plan_cmds(p, self.c.F0, self.T) for p in plans])
        return self.sim.roll(cm, ev)

    def danger(self, ro: kin.Rollout, contacts: np.ndarray) -> np.ndarray:
        """[N] the first danger's rollout index (after off), -1 none; contacts [N] the bounce's index or -1."""
        c, cfg = self.c, self.cfg
        N, T1 = ro.flags.shape
        idx = np.arange(T1)[None, :]
        inv = (ro.flags & kin.F_INVULN) != 0
        pre = (contacts[:, None] >= 0) & (idx >= contacts[:, None] - 2) & (idx < contacts[:, None])
        bad = np.zeros((N, T1), bool)
        if c.b_box is not None:
            bad |= box_hits(ro, c.b_box, cfg.body_m) & ~inv & ~pre
        if c.f_box is not None:
            bad |= box_hits(ro, c.f_box, cfg.body_m) & ~inv
        if c.L is not None and c.f_L is not None:
            lo, hi = self._i(c.f_L - 3), self._i(c.f_L + 13)
            if hi > self.off:
                w = (idx >= lo) & (idx <= hi)
                bad |= hammer_hits(ro, c.L, c.fface, cfg.hammer_m) & w
        if c.rc is not None and c.lit is not None:
            lo, hi = self._i(c.lit[0] - 2), self._i(c.lit[1] + 2)
            if hi > self.off:
                w = (idx >= lo) & (idx <= hi)
                bad |= dome_hits(ro, c.rc, cfg.dome_m) & w & ~inv
        if c.f_fall is not None:
            fa, fl, x0, L, fc = c.f_fall
            span = max(fl - fa, 1)
            for j in range(max(self.off + 1, self._i(fa)), min(self._i(fl + 2), T1)):
                k = self._F(j) - fa
                fr = min(max(k / span, 0.0), 1.0)
                xc = x0 + (L - x0) * fr
                y0 = float(np.interp(k * 54.0 / span, np.arange(0, 66, 6), FLIGHT_Y0))
                xa, xb = xc - fc * (1.34 + 0.3), xc + fc * (2.25 + 0.3)
                box = (min(xa, xb), FLOOR + y0 - 0.3, max(xa, xb), FLOOR + y0 + 3.8 + 0.3)
                bad[:, j] |= box_hits(ro, box, 0.0)[:, j]
        if c.b_hammer is not None:
            f0, f1, x0, x1, top = c.b_hammer
            lo, hi = self._i(f0), self._i(f1)
            if hi > self.off:
                w = (idx >= lo) & (idx <= hi)
                bad |= box_hits(ro, (x0, FLOOR - 1.0, x1, FLOOR + top), cfg.hammer_m) & w & ~inv
        bad[:, :self.off + 1] = False
        return np.where(bad.any(axis=1), np.argmax(bad, axis=1), -1)

    def _contact(self, ro: kin.Rollout, plans: list[Plan]) -> np.ndarray:
        """[N] the down slash's contact index on B's box: the first frame in press + 3 .. press + 9 where both shapes
        meet it, airborne, not landed since the press, the attack swung; -1 none."""
        N, T1 = ro.flags.shape
        out = np.full(N, -1)
        if self.c.b_box is None or not self.c.b_ok:
            return out
        faces = self._faces(plans)
        hit = slash_hits(ro, faces, self.c.b_box, self.off)
        gnd = (ro.flags & kin.F_GROUND) != 0
        for n, p in enumerate(plans):
            if p.press is None:
                continue
            pi = self._i(p.press)
            if pi + 3 >= T1:
                continue
            sw = (ro.flags[n, min(pi, T1 - 1)] | ro.flags[n, min(pi + 1, T1 - 1)]) & kin.F_ATTACKING
            if not sw or gnd[n, max(pi - 1, 0)]:
                continue
            for j in range(pi + 3, min(pi + 10, T1)):
                if gnd[n, pi:j + 1].any():
                    break
                if hit[n, j]:
                    out[n] = j
                    break
        return out

    def evaluate(self, plans: list[Plan]) -> list[Plan]:
        """Fill contact / bad for each plan (a press plan needs its contact on B, else bad = the press frame)."""
        if not plans:
            return plans
        ro0 = self._roll(plans)
        js = self._contact(ro0, plans)
        ev = np.zeros((len(plans), self.T), np.int64)
        for n, p in enumerate(plans):
            if p.press is not None and js[n] >= 0:
                p.contact = self._F(int(js[n]))
                k = int(js[n]) - self.off
                if 0 <= k < self.T:
                    ev[n, k] |= kin.EV_POGO
                if p.umb is None:
                    p.umb = p.contact + self.cfg.umb_f
        ro = self._roll(plans, ev)
        cont = np.array([self._i(p.contact) if p.contact is not None else -1 for p in plans])
        bad = self.danger(ro, cont)
        for n, p in enumerate(plans):
            if p.press is not None and p.contact is None:
                p.bad, p.why = p.press, p.why + " no contact"
            else:
                p.bad = None if bad[n] < 0 else self._F(int(bad[n]))
        self.last_ro = ro
        return plans

    def _dk(self, x0: float) -> int:
        tx = self.c.tx
        return 0 if abs(tx - x0) <= 0.35 else (M_R if tx > x0 else M_L)

    def _keeps(self, x0: float, umb_t: int | None) -> list[Plan]:
        """Keep plans: the umbrella held (open now) or pressed at F0 + u (released before: an edge), a drift key
        (toward the target x first, the other way too)."""
        F0, c = self.c.F0, self.c
        dk = self._dk(x0)
        ok = M_L if dk == M_R else M_R
        drifts = [(0, 0)] + ([(dk, d) for d in (6, 14, 30)] if dk else []) + [(ok, d) for d in (10, 30)]
        out = []
        for k, d in drifts:
            if c.gliding:
                out.append(Plan("keep", k, F0, F0 + d, hold_j=True, why="keep"))
            else:
                u0 = 2 if c.j_held else 0          # a held jump key is released 2 frames first (an edge)
                us = sorted({max(umb_t - F0, u0) if umb_t is not None else u0, u0, u0 + 3, u0 + 7, u0 + 12})
                for u in us:
                    out.append(Plan("keep", k, F0, F0 + d, umb=F0 + u, why=f"keep u{u}"))
        return out

    @staticmethod
    def _again(prev: Plan | None, kinds: tuple) -> Plan | None:
        """The previous tick's plan (same absolute frames) to evaluate again: kept while it stays safe (no receding
        presses)."""
        if prev is None or prev.kind not in kinds:
            return None
        return Plan(prev.kind, prev.dirk, prev.d0, prev.d1, prev.jump, prev.press, None,
                    prev.umb if prev.press is None else None, prev.hold_j, why=prev.why)

    def best_air(self, x0: float, umb_t: int | None = None, prev: Plan | None = None) -> Plan:
        """In the air: keep (the umbrella) or one down slash onto B; the previous plan while it stays safe, else a safe
        keep (no drift or toward the target; the umbrella press nearest umb_t, the shortest drift), else the latest
        safe press, else a safe keep drifting away, else the plan whose first danger comes latest."""
        F0, c = self.c.F0, self.c
        again = self._again(prev, ("keep", "drop"))
        if again is not None and (again.press is None or again.press >= max(F0, c.atk_ready_f)) and (
                again.umb is None or again.umb >= F0 or c.gliding):
            if again.umb is not None and again.umb < F0:
                again.umb, again.hold_j = None, True
            self.evaluate([again])
            if again.bad is None:
                return again
        plans = self._keeps(x0, umb_t)
        if c.b_ok:
            dk = 0 if abs(c.b_x - x0) <= 0.35 else (M_R if c.b_x > x0 else M_L)
            p0 = max(F0, c.atk_ready_f)
            for P in range(p0, F0 + 60, 3):
                for k, d in ((0, 0), (dk, 8), (dk, 20)):
                    if d and not k:
                        continue
                    plans.append(Plan("drop", k, F0, min(F0 + d, P + 6), press=P, hold_j=c.gliding, why="drop"))
        plans = self.evaluate(plans)
        safe = [p for p in plans if p.bad is None]
        dk = self._dk(x0)
        # 1) keep, no drift or toward the target x; 2) a down slash onto B (the latest press); 3) keep drifting away
        keep = [p for p in safe if p.kind == "keep" and p.dirk in (0, dk)]
        if keep:
            tgt = umb_t if umb_t is not None else F0
            return min(keep, key=lambda p: (abs((p.umb or F0) - tgt), p.d1 - p.d0))
        drop = [p for p in safe if p.kind == "drop"]
        if drop:
            return max(drop, key=lambda p: (p.press, -(p.d1 - p.d0)))
        if safe:
            tgt = umb_t if umb_t is not None else F0
            return min(safe, key=lambda p: (abs((p.umb or F0) - tgt), p.d1 - p.d0))
        return max(plans, key=lambda p: (p.bad if p.bad is not None else 1 << 30, p.kind == "keep", p.press or 0))

    def best_flee(self, x0: float) -> Plan:
        """On the ground without a safe contact plan: walk either way (or stand), optionally jump and open the
        umbrella; the plan whose first danger comes latest."""
        F0 = self.c.F0
        plans = [Plan("flee", 0, F0, F0, why="stand")]
        for k in (M_L, M_R):
            for d in (10, 25, 60):
                plans.append(Plan("flee", k, F0, F0 + d, why="walk"))
                plans.append(Plan("flee", k, F0, F0 + d, jump=(F0, 12), umb=F0 + 22, why="hop"))
        plans = self.evaluate(plans)
        return max(plans, key=lambda p: (p.bad if p.bad is not None else 1 << 30, p.jump is None,
                                         -(p.d1 - p.d0)))

    def best_up(self, x0: float, a_frame: int, prev: Plan | None = None) -> Plan | None:
        """On the ground: the jump (pressed from a_frame - jump_lead; no drift before a_frame + 1: her x at A - 1 is
        the spot), the drift toward B, one down slash onto its head; the previous plan while it stays safe, else the
        earliest safe contact, else the plan whose first danger comes latest."""
        F0, c, cfg = self.c.F0, self.c, self.cfg
        if not c.b_ok:
            return None
        again = self._again(prev, ("up",))
        if again is not None and again.jump[0] >= F0 and again.press >= c.atk_ready_f:
            self.evaluate([again])
            if again.bad is None:
                return again
        dk = M_R if c.b_x > x0 else M_L
        j_lo = max(F0, a_frame - cfg.jump_lead)
        d0 = max(a_frame + 1, F0)
        plans = []
        # after F's aim (her x no longer matters to it) a walk toward B may come first: the jump w frames later
        walks = (0, 2) if d0 > F0 else (0, 2, 8, 16)
        for w in walks:
            j0 = j_lo + w
            for H in (16, 22, 30):
                for d in (0, 6, 10, 14, 18, 24, 30):
                    if w > 2 and d < w:
                        continue
                    plans.append(Plan("up", dk if d else 0, d0, d0 + d, jump=(j0, H), why="up"))
        ro = self._roll(plans)
        faces = np.array([((1 if p.dirk == M_R else -1) if p.dirk else c.face) for p in plans])
        # a pogo from above: the slash meets B's box with her box bottom at or above its top - 0.3, falling
        hit = slash_hits(ro, faces, c.b_box, self.off) & (ro.box[..., 1] >= c.b_box[3] - 0.3) & (ro.vel[..., 1] < 0)
        out = []
        for n, p in enumerate(plans):
            ks = np.flatnonzero(hit[n])
            if not len(ks):
                continue
            k = int(ks[0])
            for a in (5, 4, 6, 3):
                P = self._F(k) - a
                if P <= p.jump[0] + 2 or P < c.atk_ready_f:
                    continue
                out.append(Plan("up", p.dirk, p.d0, min(p.d1, P + 6), jump=(p.jump[0], min(p.jump[1], P - p.jump[0])),
                                press=P, why="up"))
                break
        if not out:
            return None
        out = self.evaluate(out)
        safe = [p for p in out if p.bad is None]
        if safe:
            return min(safe, key=lambda p: (p.contact, p.d1 - p.d0))
        return max(out, key=lambda p: (p.bad, -(p.contact or 0)))


@dataclass
class RtRun:
    iid: object                    # F
    other: object                  # B
    f_a: int                       # the STATE frame that first showed F's Cast Slam Antic
    k_a: int                       # its antic frame then
    x0: float
    face: int                      # F's facing (+1 right): sgn toward the open side (B's)
    back0: float
    rel0: float                    # her x in front of F
    db0: float                     # B ahead of x0 along F's facing
    b_st0: str | None
    hp0: int = 0
    tier: str = "pogo"             # pogo / far
    phase: str = "go"              # go / air / done
    far_checked: bool = False      # the "far" test made at F's aim
    f_csa2: int | None = None
    f_aim: int | None = None       # F's Jump Aim (the first Jump / Air STATE frame, its state time back)
    a_pred: int | None = None
    aim_hx: float | None = None
    p_aim: float | None = None     # her x ahead of x0 at the aim, and B's
    db_aim: float | None = None
    L_pred: float | None = None
    f_land: int | None = None      # F's landing (Slam 2's first frame)
    x_land: float | None = None
    rune: dict = field(default_factory=dict)   # {"first", "lit", "unlit", "cx"} (frames - f_land)
    presses: list = field(default_factory=list)   # (frame - f_a, kind) of the side slash presses on B
    jump_f: int | None = None      # the jump's press (mask frame - f_a)
    contacts: list = field(default_factory=list)  # (frame - f_a, her box bottom, B's state) of the bounces seen
    umbs: list = field(default_factory=list)      # umbrella presses (mask frame - f_a)
    drops: list = field(default_factory=list)     # down-slash presses (mask frame - f_a, plan contact - f_a)
    plans: list = field(default_factory=list)     # (f - f_a, plan row) when the plan's kind / press changed
    hits_b: list = field(default_factory=list)
    hp: list = field(default_factory=list)        # frames (- f_a) of HP losses while the run lasts
    hp_src: list = field(default_factory=list)
    min_h_lit: float | None = None  # her box bottom's lowest above the floor while the circle was lit
    b_moves: list = field(default_factory=list)   # B's move starts in the run (state, frame - f_a)
    ms: list = field(default_factory=list)
    ms_plan: list = field(default_factory=list)   # the plans' compute time (ms)
    f_end: int | None = None
    end: str = ""


class RunePogo:
    """The run's controller (TwoPlay owns one per episode)."""

    def __init__(self):
        self.cfg = _cfg()
        self.run: RtRun | None = None
        self.done: list[RtRun] = []
        self.plan: Plan | None = None
        self._prev_steps = 0
        self._prev_b = None
        self._press_f: int | None = None      # the go phase's side slash press (mask frame)
        self._drop_f: int | None = None       # the air phase's down slash press (mask frame)
        self._bounce_f: int | None = None     # the last bounce seen (STATE frame)
        self._b_slam_f0: int | None = None    # B's Slam Antic entry (STATE frame) while it slams
        self._umb_f: int | None = None        # the last umbrella press sent (mask frame)
        self._next_plan = 0

    # ---- bookkeeping (every tick, TwoPlay._esc_observe) ----

    def start(self, f: int, s: dict, F: dict, B: dict, hx: float, hp: int, tin: float) -> RtRun:
        face = face_of(F)
        x0 = float(F["pos"][0])
        r = RtRun(iid=F.get("iid"), other=B.get("iid"), f_a=f, k_a=int(round(tin * 60.0)), x0=round(x0, 3),
                  face=face, back0=round((x0 - WALL_L) if face > 0 else (WALL_R - x0), 2),
                  rel0=round((hx - x0) * face, 2), db0=round((float(B["pos"][0]) - x0) * face, 2),
                  b_st0=_sp.control(B)[0], hp0=hp)
        r.a_pred = f - r.k_a + self.cfg.a_antic
        self.run = r
        self.plan = None
        self._press_f = self._drop_f = self._bounce_f = self._b_slam_f0 = self._umb_f = None
        self._next_plan = 0
        self._prev_b = _sp.control(B)[0]
        return r

    def update(self, f: int, s: dict, hx: float | None, hp: int) -> None:
        r = self.run
        if r is None:
            return
        c = self.cfg
        cs = _sp.clappers(s)
        F = next((e for e in cs if e.get("iid") == r.iid), None)
        B = next((e for e in cs if e.get("iid") == r.other), None)
        h = s.get("hero") or {}
        if hp < r.hp0:
            r.hp.append(f - r.f_a)
            for ev in s.get("ev") or ():
                d = ev.get("d") or {}
                if ev.get("k") == "hp" and (d.get("delta") or 0) < 0:
                    r.hp_src.append(str(d.get("source") or "")[-40:])
        r.hp0 = hp
        for ev in s.get("ev") or ():
            d = ev.get("d") or {}
            if (ev.get("k") == "hit" and d.get("type_key") == CLAPPER and (d.get("ent") or d.get("iid")) == r.other
                    and (d.get("dealt") is None or float(d.get("dealt")) > 0)):
                r.hits_b.append(f - r.f_a)
        if B is not None:
            bst, btin = _sp.control(B)
            if bst != self._prev_b and bst in ("Slam Antic", "Spell Antic", "Jump Antic", "Cast Slam Antic",
                                               "Evade Scuttle"):
                r.b_moves.append((bst, f - r.f_a))
            if bst == "Slam Antic" and self._prev_b != "Slam Antic":
                self._b_slam_f0 = f - int(round(btin * 60.0))
            elif bst not in B_SLAM:
                self._b_slam_f0 = None
            self._prev_b = bst
        # a bounce: the down-spike steps jump up (cstate_int[1])
        ci = h.get("cstate_int") or [0, 0]
        steps = int(ci[1]) if len(ci) > 1 and ci[1] is not None else 0
        if steps > self._prev_steps and steps >= 7:
            hb = (float(h["box"][1]) - FLOOR) if h.get("box") else None
            r.contacts.append((f - r.f_a, None if hb is None else round(hb, 2),
                               None if B is None else _sp.control(B)[0]))
            self.plan = None                  # the bounce: plan again (the umbrella next)
            self._drop_f = None
            self._bounce_f = f
        self._prev_steps = steps
        if F is None:
            self.close(f, "F dead")
            return
        st, tin = _sp.control(F)
        k_st = int(round(tin * 60.0))
        if st == "Cast Slam Antic 2" and r.f_csa2 is None:
            r.f_csa2 = f - k_st
            r.a_pred = r.f_csa2 + c.a_csa2
        if r.f_aim is None and st in ("Jump Aim", "Cast Jump", "Jump", "Air"):
            r.f_aim = f - k_st if st in ("Jump Aim", "Jump") else f - 1
            if hx is not None:
                r.aim_hx = round(hx, 3)
                r.p_aim = round((hx - r.x0) * r.face, 2)
                r.L_pred = round(landing(r.x0, hx, r.face), 3)
                if B is not None:
                    r.db_aim = round((float(B["pos"][0]) - r.x0) * r.face, 2)
        if r.f_aim is not None and r.f_land is None and st not in ("Jump Aim", "Cast Jump", "Jump", "Air"):
            r.f_land = f - k_st if st == "Slam 2" else f
            r.x_land = float(F["pos"][0])
        if r.f_land is not None:
            for lo, hi, iid, lit in _cs.rune_spans(s):
                cx = 0.5 * (lo + hi)
                if abs(cx - rune_centre(r.x_land, r.face)) > 3.0:
                    continue
                rr = r.rune
                rr.setdefault("first", f - r.f_land)
                rr["cx"] = round(cx, 3)
                if lit:
                    rr.setdefault("lit", f - r.f_land)
                    if h.get("box"):
                        hb = float(h["box"][1]) - FLOOR
                        r.min_h_lit = round(hb if r.min_h_lit is None else min(r.min_h_lit, hb), 2)
                elif "lit" in rr:
                    rr.setdefault("unlit", f - r.f_land)
        if B is None:
            self.close(f, "B dead")
            return
        if r.phase == "done":
            return
        if "unlit" in r.rune or (r.f_land is not None and f - r.f_land > c.end_f):
            self.close(f, "burst" if "unlit" in r.rune else "end")

    def close(self, f: int, why: str) -> None:
        r = self.run
        if r is not None:
            r.f_end, r.end = f - r.f_a, why
            r.phase = "done"
            self.done.append(r)
        self.run = None
        self.plan = None

    def critical(self) -> bool:
        return self.run is not None and self.run.phase in ("go", "air")

    # ---- the keys (TwoPlay.step) ----

    def step(self, f: int, s: dict, ground: bool, accepting: bool, sim) -> int | None:
        r = self.run
        if r is None or r.phase == "done":
            return None
        cs = _sp.clappers(s)
        F = next((e for e in cs if e.get("iid") == r.iid), None)
        B = next((e for e in cs if e.get("iid") == r.other), None)
        if F is None or B is None:
            return None
        h = s.get("hero") or {}
        if not accepting:
            return 0
        Fm = f + SEND_AHEAD
        a_frame = r.f_aim if r.f_aim is not None else r.a_pred
        if r.f_aim is not None and not r.far_checked:
            r.far_checked = True
            if self._far(r, B):
                r.tier = "far"
                self.close(f, "far")
                return None
        if r.phase == "go":
            if ground and Fm < a_frame - self.cfg.jump_lead:
                return self._go(f, s, F, B)
            r.phase = "air"
        m = self._air(f, s, F, B, ground, sim, a_frame)
        r.ms.append((Fm - r.f_a, m))
        return m

    def _far(self, r: RtRun, B: dict) -> bool:
        """At F's aim: B's face spot clear of F's landing hammer and its circle (the spec's tier 1 / "no pogo")."""
        if r.L_pred is None:
            return False
        c = self.cfg
        bx = float(B["pos"][0])
        spot = bx - r.face * c.spot
        u = (spot - r.L_pred) * r.face                 # her spot ahead of the landing
        rc = (rune_centre(r.L_pred, r.face) - r.L_pred) * r.face
        return u - HALF_W >= max(7.76, rc + RUNE_R) + c.far_m

    def _go(self, f: int, s: dict, F: dict, B: dict) -> int:
        """B's face: the walk / dash to the spot, the side slash on B when it meets its body (slash=1)."""
        r, c = self.run, self.cfg
        h = s.get("hero") or {}
        vx = float((h.get("vel") or [0.0, 0.0])[0])
        hx = _sp.hero_x(s)
        hxw = hx + vx * SEND_AHEAD / 60.0
        bx = float(B["pos"][0])
        spot = bx - r.face * c.spot
        look = 1 if bx > hxw else -1
        toward = M_R if look > 0 else M_L
        if self._press_f is not None and f + SEND_AHEAD - self._press_f == 1:
            return M_A | toward                          # the press's second frame
        bb = body_box(B)
        lo, hi = (hxw + _sp.SLASH_X[0], hxw + _sp.SLASH_X[1]) if look > 0 else (hxw - _sp.SLASH_X[1],
                                                                                 hxw - _sp.SLASH_X[0])
        meets = lo < bb[2] - 0.1 and hi > bb[0] + 0.1
        if c.slash and meets and _atk_ready(s):
            fc = h.get("facing")
            if fc is None or float(fc) * look <= 0:
                return toward
            self._press_f = f + SEND_AHEAD
            r.presses.append((f - r.f_a, "slash"))
            return M_A | toward
        d = spot - hxw
        if abs(d) <= 0.3:
            return 0
        k = M_R if d > 0 else M_L
        clip = str((h.get("anim") or {}).get("clip") or "")
        if abs(d) > c.dash_u and _sp.on_ground(s) and not any(x in clip for x in ("Dash", "Sprint", "Skid")) and \
                ((h.get("can") or {}).get("dash", True)):
            return k | M_DASH
        return k

    def _ctx(self, f: int, s: dict, F: dict, B: dict, ground: bool, a_frame: int) -> Ctx:
        r, c = self.run, self.cfg
        h = s.get("hero") or {}
        bst = _sp.control(B)[0]
        bx = float(B["pos"][0])
        bb = body_box(B)
        # the drift target: above B; behind it (its back) while it slams
        tx = bx
        if bst in B_SLAM:
            tx = bx - face_of(B) * 3.0
        tx = min(max(tx, WALL_L + 0.6), WALL_R - 0.6)
        fc = h.get("facing")
        L = r.x_land if r.x_land is not None else r.L_pred
        if L is None:
            hx = _sp.hero_x(s)
            L = landing(r.x0, hx, r.face)
        f_L = r.f_land if r.f_land is not None else (a_frame + c.land_f)
        rc = r.rune.get("cx") or rune_centre(L, r.face)
        lit0 = f_L + c.lit0
        lit1 = f_L + c.lit1
        if "lit" in r.rune:
            lit0 = min(lit0, r.f_land + r.rune["lit"])
            lit1 = max(r.f_land + r.rune["lit"] + 9, f + SEND_AHEAD)
        tm = h.get("tm") or {}
        cd = tm.get("atk_cd")
        rdy = f + SEND_AHEAD + (0 if cd is None else max(0, int(math.ceil(float(cd) * 60.0 - (SEND_AHEAD - 1)))))
        clip = str((h.get("anim") or {}).get("clip") or "")
        j_held = bool(int((s.get("act") or {}).get("mask") or 0) & M_J)
        # the umbrella open, or pressed by the run in the last 10 frames with the key still held (the STATE shows the
        # Umbrella clips 1 - 3 frames later): keep holding the key (a release would end the float)
        gliding = (clip.startswith("Umbrella") and "Deflate" not in clip) or (
            self._umb_f is not None and 0 <= f + SEND_AHEAD - self._umb_f <= 10 and not ground)
        fst = _sp.control(F)[0]
        f_box = None if fst in ("Cast Slam Antic", "Cast Slam Antic 2", "Jump Aim", "Cast Jump", "Jump", "Air")             else body_box(F)
        f_fall = None
        if r.x_land is None and fst in ("Cast Slam Antic", "Cast Slam Antic 2", "Jump Aim", "Cast Jump", "Jump", "Air"):
            f_fall = (a_frame, f_L, r.x0, L, r.face)
        b_ham = None
        if self._b_slam_f0 is not None:
            fb = face_of(B)
            xa, xb = bx + fb * HAMMER_X[0], bx + fb * HAMMER_X[1]
            b_ham = (self._b_slam_f0 + HAMMER_K[0], self._b_slam_f0 + HAMMER_K[1], min(xa, xb), max(xa, xb),
                     HAMMER_TOP)
        return Ctx(F0=f + SEND_AHEAD, b_box=bb, b_x=bx, b_ok=bst in B_FREE, tx=tx,
                   face=1 if fc is None or float(fc) >= 0 else -1, L=L, f_L=f_L, fface=r.face, rc=rc,
                   lit=(lit0, lit1), a_frame=a_frame, a_seen=r.f_aim is not None, ground=ground, atk_ready_f=rdy,
                   gliding=gliding, j_held=j_held, f_box=f_box, b_hammer=b_ham, f_fall=f_fall)

    def _air(self, f: int, s: dict, F: dict, B: dict, ground: bool, sim, a_frame: int) -> int:
        r, c = self.run, self.cfg
        Fm = f + SEND_AHEAD
        p = self.plan
        if sim is None:
            return mask_at(p, Fm) if p is not None else 0
        ctx = self._ctx(f, s, F, B, ground, a_frame)
        committed = self.committed(p, Fm)
        if not committed and (p is None or Fm >= self._next_plan):
            import time
            t0 = time.perf_counter()
            pl = Planner(sim, ctx, c)
            hx = _sp.hero_x(s)
            if ground:
                q = pl.best_up(hx, a_frame, prev=p)
                if q is None or q.bad is not None:
                    fl = pl.best_flee(hx)
                    if q is None or (fl.bad is None or (q.bad is not None and fl.bad > q.bad)):
                        q = fl
            else:
                umb_t = None
                if self._bounce_f is not None and f - self._bounce_f < 30:
                    umb_t = self._bounce_f + c.umb_f
                q = pl.best_air(hx, umb_t, prev=p)
            r.ms_plan.append(round(1e3 * (time.perf_counter() - t0), 1))
            if p is None or q.key() != p.key():
                r.plans.append((f - r.f_a, q.row()))
            self.plan = p = q
            self._next_plan = Fm + c.research
            self._drop_f = None
        m = mask_at(p, Fm)
        if p.press is not None and Fm == p.press:
            self._drop_f = Fm
            r.drops.append((Fm - r.f_a, None if p.contact is None else p.contact - r.f_a, p.kind))
        if p.jump is not None and Fm == p.jump[0]:
            r.jump_f = Fm - r.f_a
        if p.umb is not None and Fm == p.umb:
            r.umbs.append(Fm - r.f_a)
            self._umb_f = Fm
        return m

    def committed(self, p: Plan | None, Fm: int) -> bool:
        """A plan under way is kept (no new plan): a jump pressed, to its down slash + 12 (the bounce resets the plan);
        a down slash sent, to + 12 (a miss); a hop (flee) to its umbrella."""
        if p is None:
            return False
        if self._drop_f is not None and Fm <= self._drop_f + 12:
            return True
        if p.jump is not None and p.jump[0] < Fm:
            end = (p.press + 12) if p.press is not None else (p.umb if p.umb is not None else p.jump[0] + p.jump[1])
            return Fm <= end
        return False

    def stats(self) -> list:
        runs = self.done + ([self.run] if self.run is not None else [])
        out = []
        for r in runs:
            d = {k: getattr(r, k) for k in ("f_a", "k_a", "x0", "face", "back0", "rel0", "db0", "b_st0", "tier",
                                            "f_csa2", "f_aim", "a_pred", "aim_hx", "p_aim", "db_aim", "L_pred",
                                            "f_land", "x_land", "rune", "presses", "jump_f", "contacts", "umbs",
                                            "drops", "hits_b", "hp", "hp_src", "min_h_lit", "b_moves", "f_end",
                                            "end")}
            for k in ("f_csa2", "f_aim", "a_pred", "f_land"):
                if d[k] is not None:
                    d[k] = d[k] - r.f_a
            d["plans"] = r.plans[-60:]
            d["ms_plan"] = [round(float(np.percentile(r.ms_plan, q)), 1) for q in (50, 99)] if r.ms_plan else None
            d["keys"] = r.ms[-200:]
            out.append(d)
        return out


def _atk_ready(s: dict) -> bool:
    h = s.get("hero") or {}
    tm = h.get("tm") or {}
    cd = tm.get("atk_cd")
    clip = str((h.get("anim") or {}).get("clip") or "")
    if any(x in clip for x in ("Dash", "Sprint", "Skid")):
        return False
    return cd is None or float(cd) * 60.0 - (SEND_AHEAD - 1) <= 0.05


def warm(params) -> float:
    """Compile / load the planner's numba paths before the fight (a synthetic escape cast: her in B's face, F's aim in
    2 frames; then in the air after a bounce). Returns the seconds spent."""
    import time
    from ssbot.combat.air_chain import ChainSim
    from ssbot.knowledge.kinematics import HoldState, Terrain2D
    t0 = time.perf_counter()
    terr = Terrain2D.from_boxes([(-200.0, FLOOR - 10.0, 260.0, FLOOR), (0.0, 0.0, WALL_L, 40.0),
                                 (WALL_R, 0.0, 70.0, 40.0)])
    cfg = RtCfg()
    x0, face, bx = 15.5, 1, 30.0
    hx = bx - 3.0
    L = landing(x0, hx, face)
    bbox = (bx - 2.25, 3.02, bx + 1.34, 6.92)
    for ground, vy, y in ((True, 0.0, 4.568), (False, 12.0, 9.5)):
        S = kin.initial_state(params, hx, y, vy=vy, facing=1, ground=ground)
        sim = ChainSim(S, np.zeros(2, np.int64), HoldState.idle(1), params, terr, 1000, 1001)
        F0 = 1003
        ctx = Ctx(F0=F0, b_box=bbox, b_x=bx, b_ok=True, tx=bx, face=1, L=L, f_L=F0 + 55, fface=face,
                  rc=rune_centre(L, face), lit=(F0 + 55 + cfg.lit0, F0 + 55 + cfg.lit1), a_frame=F0 + 2,
                  ground=ground, atk_ready_f=F0, f_fall=(F0 + 2, F0 + 55, x0, L, face),
                  b_hammer=(F0 + 60, F0 + 80, bx - 2.2, bx + 10.5, HAMMER_TOP))
        pl = Planner(sim, ctx, cfg)
        if ground:
            pl.best_up(hx, F0 + 2)
            pl.best_flee(hx)
        else:
            pl.best_air(hx, F0 + 8)
    return time.perf_counter() - t0


__all__ = ["RtCfg", "RtRun", "RunePogo", "Planner", "Plan", "Ctx", "plan_cmds", "mask_at", "dome_top", "body_box",
           "rune_centre", "SC2"]
