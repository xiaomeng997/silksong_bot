"""The air show (task 1v1 SP-AIR1, SSBOT_FORUM_AIRSHOW, default off; the person, 2026-10-18 18:25 / 2026-10-19 11:00:
"one Clapper killed with no HP lost and without landing"): ONE Clapper (Forum_W_w7); from her first take-off (before her
first hit, so every hit is airborne) to the Clapper's death no grounded frame (cState.onGround), no wall cling, no HP
lost. A SHOW arm, not a default: with the switch off nothing here runs (the policy builds no AirShow).

The controller owns the keys from the start of the fight to the kill (the supervisor's keys still win):
  ground   no attack on the ground. Every tick the "up" plans (walk w frames toward the Clapper, the jump held H, the
           drift key toward it, the down slash timed onto its body from above) are rolled with the policy's hero model
           (air_chain.ChainSim); the earliest safe contact is taken (the take-off). None safe: walk to the stance
           (stance_u in front of it) or away from a slam's reach.
  air      every tick (unless a sent down slash is still due: the plan is then kept to its contact + 2) the plans
           "drop" (one down slash pressed at P with a drift key toward / away from the target for d frames) and
           "keep" (no press: the umbrella pressed at u and held, a drift key) are rolled and judged against the
           Clapper's boxes BY TIME (its_timeline: the slam template's root / hammer boxes per frame with the lunge,
           four timing variants; the cast's body top by frame; the evade's slide; the jump moves' flight / landing
           hammer / rune dome from rune_pogo), the small-rune bombs (rune_bombs' forecast), the floor (a grounded
           frame or her box bottom within floor_eps of the floor) and the walls, outside the i-frames (EV_POGO's
           down-spike i-frames ~9 frames) up to the contact + after_c (the floor up to the contact + floor_c). The
           safe drop with the earliest contact wins (the most hits), else the safe keep (no umbrella first, then the
           latest umbrella), else the plan whose first danger comes latest.
A landing (the chain broken) starts the ground phase again (the episode no longer counts as a show success; the
stats keep every chain and what broke it).

    a = AirShow()                                  # per episode: a.reset()
    m = a.step(f, s, ground, accepting, sim, bombs)    # the mask for frame f + 2, or None (the default play)
"""
from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass, field

import numpy as np

from ssbot.combat import rune_pogo as _rp
from ssbot.combat import slam_play as _sp
from ssbot.combat.pogo_model import DOWN, DOWN_ALT
from ssbot.knowledge import kinematics as kin


def _on(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip() == "1"


AIRSHOW = _on("SSBOT_FORUM_AIRSHOW")
M_L, M_R, M_D, M_J, M_A, M_DASH = _sp.M_L, _sp.M_R, _sp.M_D, _sp.M_J, _sp.M_A, _sp.M_DASH
SEND_AHEAD = _sp.SEND_AHEAD
FLOOR = _rp.FLOOR                       # 3.015: the Forum floor's world y
WALL_L, WALL_R = _sp.WALL_L, _sp.WALL_R
POS_Y = 4.434                           # the Clapper's position above the floor (standing)
SLAM_K0 = {"Slam Antic": 0, "Slam 0": 49, "Slam 1": 54, "Slam 2": 57, "Slam Recover": 63}
SLAM_ST = tuple(SLAM_K0)
CAST_ST = ("Spell Antic", "Cast 1", "Cast 2")
JUMP_PRE = ("Jump Antic", "Cast Slam Antic", "Cast Slam Antic 2")
JUMP_AIR = ("Jump Aim", "Cast Jump", "Jump", "Air", "Charged?", "Slam")
EVADE_F = 21                            # Evade Scuttle 0.35 s at 15 u/s straight back
INTRO = (None, "Init", "Rest", "Drop Antic", "Notify", "Drop In", "Enter Land", "Roar")   # no take-off in these
JUMP_AIM_K = {"Jump Antic": 30, "Cast Slam Antic": 55, "Cast Slam Antic 2": 40}   # the aim's frame in the state
# the cast's body top above the floor (push_cast / rune_lowhop facts): Spell Antic 0-3 3.19, 4-7 4.36, 8 on 4.78,
# Cast 1 4.78, Cast 2 0-13 4.78, 14 on 3.19; the Idle body 3.92
CAST_ANTIC_F = 44
CAST1_F = 6
IDLE_TOP = 3.92


@dataclass
class AsCfg:
    """SSBOT_FORUM_AIRSHOW_SET="after_c=50,floor_c=30": trial overrides."""
    horizon: int = 96           # the plans' rollout length (frames from the mask frame f + 2)
    after_c: int = 46           # a drop plan is judged to its contact + this (the bounce's apex ~20, back at the head ~40)
    floor_c: int = 30           # ... the floor / the walls to its contact + this (the next plan takes it from there)
    floor_eps: float = 0.08     # her box bottom this close to the floor counts as landed (air_chain GROUND_EPS)
    wall_m: float = 0.12        # her box this close to a wall counts as a wall touch (the cling)
    body_m: float = 0.12        # her box off the Clapper's body by this
    ham_m: float = 0.15         # ... off its hammer polygons
    bomb_m: float = 0.15
    contact_in: float = 0.3     # the slash meets its body box this far inside its x edges
    pre_f: int = 1              # its body this many frames before a contact does not count (air_chain PRE_PROTECT_F 2)
    strike_k: tuple = (45, 52)  # a contact in these slam antic frames (the Slam 0 rise) ranks after the other safe drops
    dash_a: tuple = (0, 3)      # air dash plans: the dash pressed F0 + a (2 frames), the press from its end + dash_gap
    dash_gap: int = 16
    two_f: int = 1              # 1: the contact needs the slash on the box two frames running (push_cast fp1)
    p_max: int = 44             # presses searched to F0 + this
    p_step: int = 1             # ... every this many frames (3x past p_fine)
    p_fine: int = 12
    stance_u: float = 5.6       # the ground stance in front of it (outside the walk's 7 +- 1.5: it comes to her)
    away_u: float = 9.0         # a slam in its antic with no safe up plan: walk to this from its centre
    lead_f: int = 16            # the drift target: its body this many frames ahead
    slam_back_u: float = 0.6    # ... in its slam antic: this far behind its antic centre
    side_u: float = 0.6         # the drift target this far toward the nearer wall from its centre (it evades away
    #                             from her: from its wall side it backs into the middle)
    research: int = 1           # plan every this many ticks
    commit_f: int = 12          # a sent press is kept to its contact + 2 or press + this
    jump_commit: int = 4        # an up plan's jump is kept this many frames from its press
    v_slam: int = 4             # slam timing variants judged (antic 48 / 49 x Slam 0 4 / 5)
    max_ms: float = 40.0        # (stats only) a plan slower than this is counted
    walk_w: tuple = (0, 3, 6, 10)
    hold_h: tuple = (8, 12, 16, 22, 30)
    drift_d: tuple = (0, 6, 10, 14, 20, 28)
    air_drift: tuple = ((0, 0), (1, 5), (1, 10), (1, 18), (1, 30), (-1, 8), (-1, 18))
    umb_u: tuple = (0, 4, 8, 14, 22)


def cfg_from_env() -> AsCfg:
    c = AsCfg()
    for kv in os.environ.get("SSBOT_FORUM_AIRSHOW_SET", "").replace(";", ",").split(","):
        if "=" not in kv:
            continue
        k, v = (x.strip() for x in kv.split("=", 1))
        if not hasattr(c, k):
            raise KeyError(f"SSBOT_FORUM_AIRSHOW_SET: unknown key {k!r}")
        cur = getattr(c, k)
        if isinstance(cur, tuple):
            raise KeyError(f"SSBOT_FORUM_AIRSHOW_SET: {k!r} is a tuple")
        setattr(c, k, type(cur)(float(v)))
    return c


# ---- the Clapper's boxes by time ----

def _slam_tls(n: int):
    from ssbot.combat.pogo_slam import SlamTimeline
    vs = [SlamTimeline.load(antic=a, s0=s, phase=0.5) for a, s in ((49, 5), (48, 5), (49, 4), (48, 4))]
    return vs[:max(1, n)]


_TLS: list = []
HAMMER = None


def _hammer_polys():
    global HAMMER
    if HAMMER is None:
        from ssbot.combat.move_data import HAMMER_POLY
        HAMMER = {k: np.asarray(v, float) for k, v in HAMMER_POLY.items()}
    return HAMMER


@dataclass
class Tl:
    """The Clapper over the rollout (index i = STATE frame fo + i): tgt [T1, 4] the pogo target box (x0, y0, x1, y1;
    nan none), body [V, T1, 4] its body boxes, ham [V] lists of (i, px, py) hammer polygons in world coordinates."""
    tgt: np.ndarray
    body: np.ndarray
    ham: list
    kind: str
    k0: int | None = None


def its_timeline(e: dict, st: str | None, t_in: float, base_i: int, T1: int, cfg: AsCfg, hero_x: float) -> Tl:
    """The Clapper e's boxes per rollout index (base_i = the index of the STATE frame e was read in)."""
    nanb = np.full(4, np.nan)
    cx, cy = float(e["pos"][0]), float(e["pos"][1])
    fc = _rp.face_of(e)
    bb = _rp.body_box(e)
    idx = np.arange(T1)
    if st in SLAM_ST:
        if not _TLS:
            _TLS.extend(_slam_tls(4))
        tls = _TLS[:max(1, cfg.v_slam)]
        k_now = SLAM_K0[st] + int(round(float(t_in) * 60))
        V = len(tls)
        body = np.full((V, T1, 4), np.nan)
        ham = []
        hp = _hammer_polys()
        tgt = np.full((T1, 4), np.nan)
        for v, tl in enumerate(tls):
            kk = np.clip(k_now + (idx - base_i), 0, len(tl.state) - 1)
            # its position at the antic entry: now minus the lunge so far (in this variant)
            x0 = cx - fc * tl.disp[min(max(k_now, 0), len(tl.state) - 1)]
            r = tl.root[kk]                       # x0, x1, y0, y1 in its frame
            d = tl.disp[kk]
            xa, xb = x0 + fc * (r[:, 0] + d), x0 + fc * (r[:, 1] + d)
            bx = np.stack([np.minimum(xa, xb), cy + r[:, 2], np.maximum(xa, xb), cy + r[:, 3]], axis=1)
            body[v] = bx
            if v == 0:
                tgt = bx.copy()
            hl = []
            for i in range(T1):
                stt = tl.state[kk[i]]
                k = int(kk[i])
                nm = None
                if stt == "Slam 1" or (stt == "Slam 2" and k > 0 and tl.state[k - 1] == "Slam 1"):
                    nm = "Slam Collider 1"
                if stt == "Slam 2" or (stt == "Slam Recover" and k > 0 and tl.state[k - 1] == "Slam 2"):
                    nm2 = "Slam Collider 2"
                    hl.append((i, x0 + fc * (d[i] + hp[nm2][:, 0]), cy + hp[nm2][:, 1]))
                if nm is not None:
                    hl.append((i, x0 + fc * (d[i] + hp[nm][:, 0]), cy + hp[nm][:, 1]))
            ham.append(hl)
        return Tl(tgt, body, ham, "slam", k_now)
    if st in CAST_ST:
        k_now = int(round(float(t_in) * 60)) + (0 if st == "Spell Antic" else CAST_ANTIC_F if st == "Cast 1"
                                                 else CAST_ANTIC_F + CAST1_F)
        kk = k_now + (idx - base_i)
        c2 = kk - (CAST_ANTIC_F + CAST1_F)
        top = np.where(kk < 4, 3.19, np.where(kk < 8, 4.36, np.where(c2 < 14, 4.78, np.where(c2 < 40, 3.19,
                                                                                                IDLE_TOP))))
        bx = np.stack([np.full(T1, bb[0]), np.full(T1, FLOOR), np.full(T1, bb[2]), FLOOR + top], axis=1)
        return Tl(bx.copy(), bx[None], [[]], "cast", k_now)
    if st == "Evade Scuttle":
        k_now = int(round(float(t_in) * 60))
        vx = float((e.get("vel") or [0.0, 0.0])[0]) / 60.0
        n = np.clip(idx - base_i, 0, max(EVADE_F - k_now, 0))
        sh = vx * n
        bx = np.stack([bb[0] + sh, np.full(T1, bb[1]), bb[2] + sh, np.full(T1, bb[3])], axis=1)
        return Tl(bx.copy(), bx[None], [[]], "evade", k_now)
    if st in JUMP_PRE or st in JUMP_AIR:
        # the jump moves: its body on the ground to the aim (a target to the aim - 2), the flight / the landing from
        # rune_pogo's Ctx (AirShow._ctx); no target in the flight
        bx = np.tile(np.asarray(bb, float), (T1, 1))
        k_now = int(round(float(t_in) * 60))
        if st in JUMP_AIR:
            bx[:] = nanb
            tg = bx.copy()
        else:
            aim = JUMP_AIM_K.get(st, 30) - k_now
            bx[base_i + max(aim, 0):] = nanb
            tg = bx.copy()
            tg[base_i + max(aim - 2, 0):] = nanb
        return Tl(tg, bx[None], [[]], "jump", k_now)
    # Idle / Walk / After Scuttle / the rest: its box now, a walk extrapolated 30 frames
    vx = float((e.get("vel") or [0.0, 0.0])[0]) / 60.0 if st == "Walk" else 0.0
    sh = vx * np.clip(idx - base_i, 0, 30)
    bx = np.stack([bb[0] + sh, np.full(T1, bb[1]), bb[2] + sh, np.full(T1, bb[3])], axis=1)
    return Tl(bx.copy(), bx[None], [[]], "idle")


def slash_hits_t(ro: kin.Rollout, faces: np.ndarray, boxes: np.ndarray, i0: int) -> np.ndarray:
    """[N, T1] the down slash (both shapes) at her transform on frame i meets boxes[i] (nan: none)."""
    N, T1 = ro.flags.shape
    hx, hy = ro.pos[..., 0].ravel(), ro.pos[..., 1].ravel()
    rect = np.tile(np.asarray(boxes, float), (N, 1))
    fr = np.repeat(np.asarray(faces), T1)
    hit = np.ones(hx.shape[0], bool)
    for poly in (DOWN, DOWN_ALT):
        h = np.zeros(hx.shape[0], bool)
        for face in (1, -1):
            sel = fr == face
            if sel.any():
                h[sel] = _rp._poly_hits(poly[:, 0] * face, poly[:, 1], hx[sel], hy[sel], rect[sel])
        hit &= h
    hit = hit.reshape(N, T1)
    hit[:, :i0] = False
    return hit


def box_hits_t(ro: kin.Rollout, boxes: np.ndarray, pad: float) -> np.ndarray:
    """[N, T1] her box meets boxes[i] (grown by pad; nan: none)."""
    b = ro.box
    x0, y0, x1, y1 = (boxes[:, j][None, :] for j in range(4))
    with np.errstate(invalid="ignore"):
        return (b[..., 0] < x1 + pad) & (b[..., 2] > x0 - pad) & (b[..., 1] < y1 + pad) & (b[..., 3] > y0 - pad)


class ShowPlanner(_rp.Planner):
    """rune_pogo's Planner with the Clapper's boxes by time (its_timeline), the floor and the walls."""

    def __init__(self, sim, ctx: _rp.Ctx, cfg: AsCfg, tl: Tl):
        rc = _rp.RtCfg(horizon=cfg.horizon, body_m=cfg.body_m, contact_in=cfg.contact_in, after_contact=cfg.after_c,
                       umb_f=1 << 40, bomb_m=cfg.bomb_m)
        super().__init__(sim, ctx, rc)
        self.ac, self.tl = cfg, tl
        tg = tl.tgt.copy()
        w = tg[:, 2] - tg[:, 0]
        d = np.where(w > 2.0 * cfg.contact_in + 0.4, cfg.contact_in, 0.0)
        tg[:, 0] += d
        tg[:, 2] -= d
        self.tgt = tg

    def _fit(self, a: np.ndarray, T1: int) -> np.ndarray:
        if a.shape[-2] >= T1:
            return a[..., :T1, :]
        pad = np.repeat(a[..., -1:, :], T1 - a.shape[-2], axis=-2)
        return np.concatenate([a, pad], axis=-2)

    def _contact(self, ro: kin.Rollout, plans: list) -> np.ndarray:
        N, T1 = ro.flags.shape
        out = np.full(N, -1)
        tg = self._fit(self.tgt, T1)
        if not np.isfinite(tg[:, 0]).any():
            return out
        hit = slash_hits_t(ro, self._faces(plans), tg, self.off)
        if self.ac.two_f:
            h2 = np.zeros_like(hit)
            h2[:, :-1] = hit[:, :-1] & hit[:, 1:]
            hit = h2
        gnd = ((ro.flags & kin.F_GROUND) != 0) | (ro.box[..., 1] <= FLOOR + self.ac.floor_eps)
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

    def danger(self, ro: kin.Rollout, contacts: np.ndarray) -> np.ndarray:
        c, ac = self.c, self.ac
        b_box = c.b_box
        c.b_box = None                      # the parent: bombs, the jump moves' flight / landing / dome
        try:
            bad_p = super().danger(ro, contacts)
        finally:
            c.b_box = b_box
        N, T1 = ro.flags.shape
        idx = np.arange(T1)[None, :]
        inv = (ro.flags & kin.F_INVULN) != 0
        pre = (contacts[:, None] >= 0) & (idx >= contacts[:, None] - ac.pre_f) & (idx < contacts[:, None])
        bad = np.zeros((N, T1), bool)
        body = self._fit(self.tl.body, T1)
        for v in range(body.shape[0]):
            bad |= box_hits_t(ro, body[v], ac.body_m)
        b = ro.box
        for hl in self.tl.ham:
            for i, px, py in hl:
                if i <= self.off or i >= T1:
                    continue
                r = b[:, i].copy()
                r[:, 0] -= ac.ham_m
                r[:, 1] -= ac.ham_m
                r[:, 2] += ac.ham_m
                r[:, 3] += ac.ham_m
                z = np.zeros(N)
                bad[:, i] |= _rp._poly_hits(px, py, z, z, r)
        bad &= ~inv & ~pre
        # the floor and the walls (no i-frames for those): to the contact + floor_c (a drop) / the horizon (no contact)
        gnd = ((ro.flags & kin.F_GROUND) != 0) | (b[..., 1] <= FLOOR + ac.floor_eps)
        wall = (b[..., 0] <= WALL_L + ac.wall_m) | (b[..., 2] >= WALL_R - ac.wall_m)
        lim = np.where(contacts >= 0, contacts + ac.floor_c, T1)[:, None]
        ff = getattr(self, "_floor_from", None)
        f0 = (np.asarray(ff)[:, None] if ff is not None and len(ff) == N else self.off + 1)
        bad |= (gnd | wall) & (idx <= lim) & (idx >= f0)
        bad[:, :self.off + 1] = False
        first = np.where(bad.any(axis=1), np.argmax(bad, axis=1), -1)
        out = bad_p.copy()
        for n in range(N):
            if first[n] >= 0 and (out[n] < 0 or first[n] < out[n]):
                out[n] = first[n]
        return out

    def evaluate(self, plans: list) -> list:
        """The parent's evaluate with the floor checked from each plan's lift-off (an up plan: its jump + 3)."""
        if not plans:
            return plans
        ff = [self._i(p.jump[0]) + 3 if (p.jump is not None and self.c.ground) else self.off + 1 for p in plans]
        ro0 = self._roll(plans)
        js = self._contact(ro0, plans)
        # a press without a contact is bad at its press (no second rollout); the rest rolled again with the bounce
        keep = []
        for n, p in enumerate(plans):
            p.contact = None
            if p.press is not None and js[n] < 0:
                p.bad, p.why = p.press, p.why + " no contact"
                continue
            if p.press is not None:
                p.contact = self._F(int(js[n]))
            keep.append(n)
        if not keep:
            self.last_ro = ro0
            return plans
        sub = [plans[n] for n in keep]
        ev = np.zeros((len(sub), self.T), np.int64)
        for m, p in enumerate(sub):
            if p.contact is not None:
                k = self._i(p.contact) - self.off
                if 0 <= k < self.T:
                    ev[m, k] |= kin.EV_POGO
        ro = self._roll(sub, ev)
        self._floor_from = [ff[n] for n in keep]
        cont = np.array([self._i(p.contact) if p.contact is not None else -1 for p in sub])
        bad = self.danger(ro, cont)
        for m, p in enumerate(sub):
            b = None if bad[m] < 0 else self._F(int(bad[m]))
            if b is not None and p.contact is not None and b > p.contact + self.ac.after_c:
                b = None
            p.bad = b
        self.last_ro = ro
        self.last_sub = sub
        return plans

    def first_ground(self, n: int) -> int | None:
        ro = self.last_ro
        if ro is None:
            return None
        g = ((ro.flags[n] & kin.F_GROUND) != 0) | (ro.box[n, :, 1] <= FLOOR + self.ac.floor_eps)
        g[:self.off + 1] = False
        k = np.flatnonzero(g)
        return None if not len(k) else self._F(int(k[0]))

    # ---- the plans ----

    def ups(self, x0: float, tx: float, walk_key: int) -> list:
        """On the ground: walk w frames toward tx, jump held H, drift toward tx d frames from the jump, the down slash
        timed onto the target from above (the first frame its slash meets the box falling, minus 3 .. 6)."""
        F0, c, ac = self.c.F0, self.c, self.ac
        dk = M_R if tx > x0 else M_L
        j_lo = F0 + (2 if c.j_held else 0)
        plans = []
        for w in ac.walk_w:
            j0 = j_lo + w
            for H in ac.hold_h:
                for d in ac.drift_d:
                    p = _rp.Plan("up", dk if (d or w) else 0, F0, j0 + d, jump=(j0, H), why=f"up w{w}")
                    plans.append(p)
        ro = self._roll(plans)
        faces = np.array([((1 if p.dirk == M_R else -1) if p.dirk else c.face) for p in plans])
        T1 = ro.flags.shape[1]
        tg = self._fit(self.tgt, T1)
        hit = slash_hits_t(ro, faces, tg, self.off) & (ro.vel[..., 1] < 0)
        with np.errstate(invalid="ignore"):
            hit &= ro.box[..., 1] >= tg[None, :, 3] - 0.3
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
                out.append(_rp.Plan("up", p.dirk, p.d0, max(p.d1, P + 2), jump=(p.jump[0], min(p.jump[1], P - p.jump[0])),
                                    press=P, why=p.why))
                break
        return out

    def drops(self, x0: float, tx: float) -> list:
        F0, c, ac = self.c.F0, self.c, self.ac
        dk = 0 if abs(tx - x0) <= 0.2 else (M_R if tx > x0 else M_L)
        ok = M_L if dk == M_R else M_R
        p0 = max(F0, c.atk_ready_f)
        out = []
        P = p0
        holds = (True, False) if (c.rising and not c.gliding) else (c.gliding,)
        while P <= F0 + ac.p_max:
            for sgn, d in ac.air_drift:
                k = 0 if sgn == 0 else (dk if sgn > 0 else (ok if dk else 0))
                if d and not k:
                    continue
                for hj in holds:
                    out.append(_rp.Plan("drop", k, F0, F0 + d, press=P, hold_j=hj, why="drop" + ("h" if hj else "")))
            P += ac.p_step if P - p0 < ac.p_fine else 3 * ac.p_step
        if getattr(c, "dash_ok", False) and dk:
            for a in ac.dash_a:
                for P in range(max(p0, F0 + a + ac.dash_gap), F0 + ac.p_max + 1, 2):
                    for d in (a + 4, a + 14, a + 30):
                        out.append(_rp.Plan("drop", dk, F0, F0 + d, press=P, dash=(F0 + a, 2), why=f"dash{a}"))
        return out

    def keeps(self, x0: float, tx: float) -> list:
        F0, c, ac = self.c.F0, self.c, self.ac
        dk = 0 if abs(tx - x0) <= 0.2 else (M_R if tx > x0 else M_L)
        ok = M_L if dk == M_R else M_R
        drifts = [(0, 0)] + ([(dk, d) for d in (6, 14, 30)] if dk else []) + [(ok, d) for d in (8, 20)]
        out = []
        for k, d in drifts:
            if c.gliding:
                out.append(_rp.Plan("keep", k, F0, F0 + d, hold_j=True, why="glide"))
                continue
            if c.rising:
                out.append(_rp.Plan("keep", k, F0, F0 + d, hold_j=True, why="rise"))
            out.append(_rp.Plan("keep", k, F0, F0 + d, why="fall"))
            u0 = 2 if c.j_held else 0
            for u in ac.umb_u:
                out.append(_rp.Plan("keep", k, F0, F0 + d, umb=F0 + u0 + u, why=f"umb{u0 + u}"))
        return out


def pick(plans: list, prefer: str = "drop", strike: tuple | None = None) -> _rp.Plan | None:
    """The safe drop with the earliest contact (then the shortest drift), else the safe keep (a fall first, then the
    latest umbrella, the shortest drift), else the plan whose first danger comes latest."""
    if not plans:
        return None
    safe = [p for p in plans if p.bad is None]
    dr = [p for p in safe if p.press is not None and p.contact is not None]
    if dr:
        def risky(p):
            return strike is not None and strike[0] <= p.contact <= strike[1]
        return min(dr, key=lambda p: (risky(p), p.dash is not None, p.contact, p.d1 - p.d0, p.press))
    kp = [p for p in safe if p.press is None]
    if kp:
        return min(kp, key=lambda p: (p.umb is not None, -(p.umb or 0), p.d1 - p.d0))
    return max(plans, key=lambda p: (p.bad if p.bad is not None else 1 << 30, p.contact is not None,
                                     -(p.d1 - p.d0)))


_WBITS: list = []


def _wall(h: dict) -> bool:
    """cState wallClinging / wallSliding (the facts' cstate schema)."""
    if not _WBITS:
        nm = kin.cstate_names()
        _WBITS.extend(nm.index(x) for x in ("wallClinging", "wallSliding"))
    cs = h.get("cstate")
    return bool(cs) and any((int(cs[i >> 6]) >> (i & 63)) & 1 for i in _WBITS)


@dataclass
class Chain:
    """One take-off to its landing (or the kill)."""
    f_take: int
    f_end: int | None = None
    end: str = ""
    hits: list = field(default_factory=list)       # (f, its state, her box bottom, kind)
    hp: list = field(default_factory=list)         # (f, amount, its state)
    ground_f: int = 0
    wall_f: int = 0
    br: dict | None = None                          # what broke it: frame, its state / k, the plan, her y


class AirShow:
    def __init__(self, cfg: AsCfg | None = None):
        self.cfg = cfg or cfg_from_env()
        self.reset()

    def reset(self) -> None:
        self.plan = None
        self.phase = "ground"
        self.chains: list[Chain] = []
        self.chain: Chain | None = None
        self._drop_f = None
        self._umb_f = None
        self._next = 0
        self._hp = None
        self._chp = None
        self._iid = None
        self.f_first_take = None
        self.f_first_hit = None
        self.ground_after = 0
        self.wall_after = 0
        self.hp_after = 0
        self.air_frames = 0
        self.hits_pre = 0                   # Clapper HP drops before the first take-off (should stay 0)
        self.kill_f = None
        self.ms: list = []
        self.n_plans = 0
        self.plans_log: list = []
        self.kinds = {}
        self.ent: dict = {}                 # state -> its first frame (the current move's states)
        self._st_last = None
        self.jump: dict = {}
        self.done = False
        self.why_none = {}
        self._pend = None

    # ---- bookkeeping ----

    def _observe(self, f: int, s: dict, ground: bool, e: dict | None) -> None:
        h = s.get("hero") or {}
        hp = h.get("health")
        st = _sp.control(e)[0] if e is not None else None
        if e is not None:
            self._iid = e.get("iid")
            if st != self._st_last:
                if st in ("Jump Antic", "Cast Slam Antic"):
                    self.jump = {"f_antic": f, "x0": float(e["pos"][0]), "face": _rp.face_of(e), "kind": st}
                if st == "Cast Slam Antic 2" and self.jump:
                    self.jump["f_csa2"] = f
                if st in ("Jump Aim", "Cast Jump", "Jump", "Air") and self.jump and "f_aim" not in self.jump:
                    self.jump["f_aim"] = f
                    self.jump["hx_aim"] = _sp.hero_x(s)
                if st in ("Slam 2",) and self.jump.get("f_aim") is not None and "f_land" not in self.jump:
                    self.jump["f_land"] = f
                    self.jump["x_land"] = float(e["pos"][0])
                if st in ("Idle", "Walk", "Evade Scuttle", "Spell Antic", "Slam Antic") and self.jump.get("f_land"):
                    if f - self.jump["f_land"] > 120:
                        self.jump = {}
                self._st_last = st
        chp = (e or {}).get("hp")
        if self._chp is not None and chp is not None and chp < self._chp:
            yb = float((h.get("box") or [0, FLOOR, 0, FLOOR])[1]) - FLOOR
            if self.f_first_take is None:
                self.hits_pre += 1
            else:
                if self.f_first_hit is None:
                    self.f_first_hit = f
                if self.chain is not None:
                    self.chain.hits.append((f, st, round(yb, 2), "air" if not ground else "ground"))
        if e is None and self._chp is not None and self.kill_f is None:
            self.kill_f = f
        self._chp = chp if e is not None else self._chp
        if self._hp is not None and hp is not None and hp < self._hp:
            if self.f_first_take is not None:
                self.hp_after += self._hp - hp
            if self.chain is not None:
                self.chain.hp.append((f, self._hp - hp, st))
                if self.chain.br is None:
                    self.chain.br = self._brk(f, s, e, "hp")
        self._hp = hp

    def _brk(self, f: int, s: dict, e: dict | None, why: str) -> dict:
        st, t = _sp.control(e) if e is not None else (None, 0.0)
        h = s.get("hero") or {}
        p = self.plan
        return {"f": f, "why": why, "st": st, "k": int(round(t * 60)), "yb": round(float((h.get("box") or [0, FLOOR])[1])
                                                                               - FLOOR, 2),
                "dx": None if e is None else round(_sp.hero_x(s) - float(e["pos"][0]), 2),
                "plan": None if p is None else [p.kind, p.why, p.press, p.contact, p.bad, p.umb],
                "phase": self.phase}

    # ---- the step ----

    def step(self, f: int, s: dict, ground: bool, accepting: bool, sim, bombs=None, plan: bool = True) -> int | None:
        """The mask for frame f + 2 (None: not the show's - two Clappers / none). plan=False: no new plan this tick
        (the policy alternates this planner with its own: the tick's cost), the current plan's keys."""
        cl = _sp.clappers(s)
        e = cl[0] if len(cl) == 1 else None
        if len(cl) > 1:
            self.why_none["two"] = self.why_none.get("two", 0) + 1
            return None
        if bombs is not None:
            self._bombs = bombs
        h = s.get("hero") or {}
        wall = _wall(h)
        ground = bool(ground)
        self._observe(f, s, ground, e)
        if self._pend is not None and not ground:
            # the take-off: the first airborne STATE after the up plan's jump press
            self._lift(f)
        if self.f_first_take is not None and e is not None:
            self.air_frames += int(not ground)
            self.ground_after += int(ground)
            self.wall_after += int(wall)
        if e is None:
            if self.chain is not None and self.chain.f_end is None:
                self.chain.f_end, self.chain.end = f, "kill" if self.kill_f is not None else "gone"
            if self.kill_f is not None:
                self.done = True               # the kill (before its spawn: not yet)
            return None
        Fm = f + SEND_AHEAD
        c = self.chain
        if c is not None and c.f_end is None and (ground or wall):
            c.ground_f += int(ground)
            c.wall_f += int(wall)
            c.f_end, c.end = f, "land" if ground else "wall"
            if c.br is None:
                c.br = self._brk(f, s, e, c.end)
        if ground and self.phase == "air" and self._pend is None:
            self.phase = "ground"
            self.plan = None
            self._drop_f = None
        if self._pend is not None and Fm > self._pend + 6 and ground:
            self._pend = None                 # the jump never left the ground
            self.phase = "ground"
        if ground and not accepting:
            self.why_none["input"] = self.why_none.get("input", 0) + 1
            return 0
        if sim is None:
            return self._mask_plan(Fm)
        st, t_in = _sp.control(e)
        if self._committed(Fm):
            return self._mask_plan(Fm)
        if self.plan is not None and (Fm < self._next or not plan):
            return self._mask_plan(Fm)
        t0 = time.perf_counter()
        ctx = self._ctx(f, s, e, ground, st)
        T1 = sim.off + self.cfg.horizon
        hx = _sp.hero_x(s)
        tl = its_timeline(e, st, t_in, sim.f - sim.fo, T1, self.cfg, hx)
        pl = ShowPlanner(sim, ctx, self.cfg, tl)
        tx = self._tx(e, st, tl, sim.f - sim.fo)
        if ground and self._pend is None and st in INTRO:
            q = self._ground_move(Fm, hx, e, st)          # the intro (its Roar locks her): no take-off yet
        elif ground and self._pend is None:
            ups = pl.evaluate(pl.ups(hx, tx, 0))
            safe = [p for p in ups if p.bad is None and p.contact is not None]
            q = min(safe, key=lambda p: (p.contact, p.jump[0], p.d1 - p.d0)) if safe else None
            if q is None:
                q = self._ground_move(Fm, hx, e, st)
        else:
            plans = pl.drops(hx, tx) + pl.keeps(hx, tx)
            prev = self._again(self.plan, Fm, ctx)
            if prev is not None:
                plans.insert(0, prev)
            plans = pl.evaluate(plans)
            sk = None
            if tl.kind == "slam" and tl.k0 is not None:
                sk = (f + self.cfg.strike_k[0] - tl.k0, f + self.cfg.strike_k[1] - tl.k0)
            q = pick(plans, strike=sk)
        self.ms.append((time.perf_counter() - t0) * 1e3)
        self.n_plans += 1
        if q is not None:
            key = q.key()
            if self.plan is None or key != self.plan.key():
                if len(self.plans_log) < 400:
                    self.plans_log.append((f, self.phase, st, round(hx, 2), q.row()))
            self.kinds[q.kind] = self.kinds.get(q.kind, 0) + 1
        self.plan = q
        self._next = Fm + self.cfg.research
        return self._mask_plan(Fm)

    def _again(self, p, Fm: int, ctx) -> _rp.Plan | None:
        if p is None or p.kind == "walk":
            return None
        if p.press is not None and p.press < max(Fm, ctx.atk_ready_f):
            return None
        if p.jump is not None and p.jump[0] < Fm and p.kind == "up":
            # the jump is under way: the same keys from now on (an air plan)
            q = _rp.Plan("drop" if p.press is not None else "keep", p.dirk, p.d0, p.d1, None, p.press, None,
                         None, ctx.gliding, why=p.why + " cont")
            if p.jump[0] + p.jump[1] > Fm:
                q.jump = (Fm, p.jump[0] + p.jump[1] - Fm)
            return q
        q = _rp.Plan(p.kind, p.dirk, p.d0, p.d1, p.jump, p.press, None, p.umb if p.press is None else None,
                     p.hold_j, why=p.why)
        if q.umb is not None and q.umb < Fm:
            q.umb, q.hold_j = None, True
        return q

    def _committed(self, Fm: int) -> bool:
        p = self.plan
        if p is None:
            return False
        if self._drop_f is not None:
            end = (p.contact + 2) if p.contact is not None else self._drop_f + self.cfg.commit_f
            if Fm <= min(end, self._drop_f + self.cfg.commit_f):
                return True
            self._drop_f = None
        if p.kind == "up" and p.jump is not None and p.jump[0] < Fm <= p.jump[0] + self.cfg.jump_commit:
            return True                       # the jump pressed: its keys to lift-off (the STATE shows it ~2 frames on)
        return False

    def _mask_plan(self, Fm: int) -> int:
        p = self.plan
        if p is None:
            return 0
        if p.kind == "up" and p.jump is not None and Fm == p.jump[0]:
            self._take(Fm)
        if p.kind == "walk":
            return int(p.dirk) if p.d0 <= Fm < p.d1 else 0
        m = _rp.mask_at(p, Fm)
        if p.press is not None and p.press <= Fm <= p.press + 1 and (m & M_A) and self._drop_f is None:
            self._drop_f = Fm
        if p.umb is not None and Fm == p.umb:
            self._umb_f = Fm
        return m

    def _take(self, Fm: int) -> None:
        """The up plan's jump press sent (the take-off is the first airborne STATE after it: _lift)."""
        if self._pend is None:
            self._pend = Fm
        self.phase = "air"

    def _lift(self, f: int) -> None:
        self._pend = None
        if self.f_first_take is None:
            self.f_first_take = f
        self.chain = Chain(f)
        self.chains.append(self.chain)

    def _tx(self, e: dict, st: str | None, tl: Tl | None = None, base_i: int = 0) -> float:
        """The drift target: its body's centre lead_f frames ahead (the evade's slide, a walk, the lunge), side_u
        toward its nearer wall."""
        cx = float(e["pos"][0])
        fc = _rp.face_of(e)
        if tl is not None and tl.kind == "slam" and tl.k0 is not None:
            # the slam: over its back half before the hammer (the lunge carries Slam Collider 1's back edge forward
            # past its antic centre), behind its lunging centre in Slam 1 / 2, over it in the recover
            k = tl.k0
            if not _TLS:
                _TLS.extend(_slam_tls(4))
            x0 = cx - fc * _TLS[0].disp[min(max(k, 0), len(_TLS[0].disp) - 1)]
            if k < 54:
                tx = x0 - fc * self.cfg.slam_back_u
            elif k < 63:
                tx = cx - fc * 1.0
            else:
                tx = cx
            return min(max(tx, WALL_L + 0.8), WALL_R - 0.8)
        if tl is not None:
            i = min(base_i + self.cfg.lead_f, tl.tgt.shape[0] - 1)
            b = tl.body[0, i]
            if np.isfinite(b[0]):
                cx = 0.5 * float(b[0] + b[2])
        side = -1.0 if (cx - WALL_L) < (WALL_R - cx) else 1.0
        tx = cx + side * self.cfg.side_u
        return min(max(tx, WALL_L + 0.8), WALL_R - 0.8)

    def _ground_move(self, Fm: int, hx: float, e: dict, st: str | None) -> _rp.Plan:
        cx = float(e["pos"][0])
        fc = _rp.face_of(e)
        sgn = 1.0 if hx >= cx else -1.0
        want = self.cfg.away_u if st in SLAM_ST else self.cfg.stance_u
        spot = cx + sgn * want
        spot = min(max(spot, WALL_L + 0.8), WALL_R - 0.8)
        k = 0 if abs(spot - hx) < 0.3 else (M_R if spot > hx else M_L)
        return _rp.Plan("walk", k, Fm, Fm + 1, why=f"walk {st} {round(spot - hx, 2)} fc{fc}")

    def _ctx(self, f: int, s: dict, e: dict, ground: bool, st: str | None) -> _rp.Ctx:
        h = s.get("hero") or {}
        tm = h.get("tm") or {}
        cd = tm.get("atk_cd")
        rdy = f + SEND_AHEAD + (0 if cd is None else max(0, int(math.ceil(float(cd) * 60.0 - (SEND_AHEAD - 1)))))
        clip = str((h.get("anim") or {}).get("clip") or "")
        j_held = bool(int((s.get("act") or {}).get("mask") or 0) & M_J)
        gliding = (clip.startswith("Umbrella") and "Deflate" not in clip) or (
            self._umb_f is not None and 0 <= f + SEND_AHEAD - self._umb_f <= 10 and not ground)
        fc = h.get("facing")
        bx = float(e["pos"][0])
        vy = float((h.get("vel") or [0.0, 0.0])[1])
        rising = (not ground) and j_held and vy > 0.5 and not gliding and not clip.startswith("DownSpike")
        ctx = _rp.Ctx(F0=f + SEND_AHEAD, b_box=_rp.body_box(e), b_x=bx, b_ok=True, tx=bx,
                      face=1 if fc is None or float(fc) >= 0 else -1, ground=ground, atk_ready_f=rdy,
                      gliding=gliding, j_held=j_held, bomb_m=self.cfg.bomb_m, rising=rising)
        ctx.dash_ok = (not ground) and bool((h.get("can") or {}).get("dash")) and not clip.startswith("Dash")
        if self._bombs is not None and len(self._bombs):
            ctx.bombs = np.asarray(self._bombs, float)
        j = self.jump
        if j and st in JUMP_PRE + JUMP_AIR + ("Slam 2", "Slam Recover"):
            rc = _rp.RtCfg()
            face = j["face"]
            if "f_aim" in j:
                a_frame = j["f_aim"] + SEND_AHEAD
                L = _rp.landing(j["x0"], j["hx_aim"], face)
            else:
                a_frame = (j["f_csa2"] + rc.a_csa2) if "f_csa2" in j else (
                    j["f_antic"] + (rc.a_antic if j["kind"] == "Cast Slam Antic" else 30))
                a_frame += SEND_AHEAD
                L = _rp.landing(j["x0"], _sp.hero_x(s), face)
                ctx.jx0 = j["x0"]
            if "x_land" in j:
                L = j["x_land"]
            f_L = (j["f_land"] + SEND_AHEAD) if "f_land" in j else a_frame + rc.land_f
            ctx.L, ctx.f_L, ctx.fface, ctx.a_frame, ctx.a_seen = L, f_L, face, a_frame, "f_aim" in j
            if "f_land" not in j:
                ctx.f_fall = (a_frame, f_L, j["x0"], L, face)
            if j["kind"] == "Cast Slam Antic":
                ctx.rc = _rp.rune_centre(L, face)
                ctx.lit = (f_L + rc.lit0, f_L + rc.lit1)
        return ctx

    _bombs = None

    def set_bombs(self, bombs) -> None:
        self._bombs = bombs

    def critical(self) -> bool:
        return not self.done

    def stats(self) -> dict:
        ch = [dict(f_take=c.f_take, f_end=c.f_end, end=c.end, n_hits=len(c.hits), hits=c.hits[:60], hp=c.hp,
                   ground_f=c.ground_f, wall_f=c.wall_f, br=c.br) for c in self.chains]
        kinds = {}
        for c in self.chains:
            for _f, st, _y, k in c.hits:
                kk = "slam" if st in SLAM_ST else "cast" if st in CAST_ST else "evade" if st in (
                    "Evade Scuttle", "After Scuttle") else "jump" if st in JUMP_PRE + JUMP_AIR else "idle"
                kinds[kk] = kinds.get(kk, 0) + 1
        ok = (self.f_first_take is not None and self.kill_f is not None and self.ground_after == 0
              and self.wall_after == 0 and self.hp_after == 0 and self.hits_pre == 0 and len(self.chains) == 1)
        return {"f_first_take": self.f_first_take, "f_first_hit": self.f_first_hit, "kill_f": self.kill_f,
                "ground_after": self.ground_after, "wall_after": self.wall_after, "hp_after": self.hp_after,
                "air_frames": self.air_frames, "hits_pre": self.hits_pre, "n_chains": len(self.chains),
                "success": bool(ok), "hits_by_kind": kinds, "chains": ch,
                "ms": [round(float(np.percentile(self.ms, q)), 1) for q in (50, 90, 99)] if self.ms else None,
                "n_plans": self.n_plans, "kinds": self.kinds, "why_none": self.why_none,
                "plans": self.plans_log[-300:]}


def warm(params) -> float:
    """Compile the planner's numba paths before the fight: an up plan on the ground and an air plan."""
    from ssbot.combat.air_chain import ChainSim
    from ssbot.knowledge.kinematics import HoldState, Terrain2D
    t0 = time.perf_counter()
    terr = Terrain2D.from_boxes([(-200.0, FLOOR - 10.0, 260.0, FLOOR), (0.0, 0.0, WALL_L, 40.0),
                                 (WALL_R, 0.0, 70.0, 40.0)])
    cfg = AsCfg()
    bx = 30.0
    e = {"pos": [bx, FLOOR + POS_Y], "flipX": True, "vel": [0.0, 0.0], "colliders": []}
    for ground, vy, y, hx in ((True, 0.0, 4.568, 36.0), (False, -2.0, 9.5, 30.5)):
        S = kin.initial_state(params, hx, y, vy=vy, facing=-1, ground=ground)
        sim = ChainSim(S, np.zeros(2, np.int64), HoldState.idle(1), params, terr, 1000, 1002)
        ctx = _rp.Ctx(F0=1004, b_box=_rp.body_box(e), b_x=bx, b_ok=True, tx=bx, face=-1, ground=ground, atk_ready_f=1004)
        for st in ("Idle", "Slam Antic"):
            tl = its_timeline(e, st, 0.1, 2, sim.off + cfg.horizon, cfg, hx)
            pl = ShowPlanner(sim, ctx, cfg, tl)
            if ground:
                pl.evaluate(pl.ups(hx, bx, 0))
            else:
                pick(pl.evaluate(pl.drops(hx, bx) + pl.keeps(hx, bx)))
    return time.perf_counter() - t0


__all__ = ["AIRSHOW", "AsCfg", "AirShow", "ShowPlanner", "its_timeline", "pick", "warm"]
