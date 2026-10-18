"""TWO_PUSHMID's cast route (task 1v1 SP13b, SSBOT_FORUM_TWO_PMCAST, default off; the person, 2026-10-18: "stand on the
ground, slash twice, and when the small runes are about to come out flip over" - in F's close cast antic slash it twice
on the ground, then just before its runes pogo over its head to its wall side, in the air while ring 1 is lit, land
after it, then herd it toward the middle; the plan notes of 2026-10-17: "when the far one is out of reach, jump between
the focus and its wall and push it toward the middle").

F = the caster (the focus, nearer its wall than the other one B), wdir = the world direction from F's centre to its
wall (her landing side), u centre to centre (her box centre, its transform). F's cast (rune_lowhop's facts): Spell Antic
43-44 frames, Cast 1 6, Cast 2 at antic frame 48-50 (C); its body top 3.19 u above the floor (Spell Antic 0-3), 4.36
(4-7), 4.78 (8 on, Cast 1, Cast 2 0-13), 3.19 (Cast 2 14 on), front 1.84-2.06 / back 1.34 u; the bombs ring r at x0 +-
4.2 r (r 2.166, top 2.83 u above the floor), ring 0 lit ~C + 20, ring 1 (1.78 - 6.62 u to each side) ~C + 30, ring 2
(5.98 - 10.82) ~C + 40, lit 5.5 - 7 frames. So on F's wall side from C + 38 on the floor 2.2 - 5.7 u from x0 is clear
until the cast's end; above F's head (her box bottom over 4.78 u) no bomb reaches her.

The over plan (each tick in the stance from antic frame k_plan0 on, every `every` ticks; the policy's hero model,
air_chain.ChainSim, rolled through rune_pogo's Planner): the jump pressed w frames from now held H, a drift key toward
F's wall side from the jump + dd for D frames, the down slash pressed so it meets F's body box (the tall box to Cast 2 +
13, the low one after) from above while she falls (both slash shapes), its bounce (EV_POGO, the down-spike i-frames),
optionally the umbrella u frames after the contact (it holds the height; it never lifts). Safe: to the horizon her box
meets neither F's body (outside the i-frames and the 2 frames before the contact) nor B's nor a lit bomb of any row
(rune_bombs' forecast and the rows still to come, grown by bomb_m; outside the i-frames), and she lands on F's wall
side land_lo .. land_hi from x0 (F's x at Cast 2). Of the safe plans the latest jump (the most ground slashes first),
then no umbrella, then the landing nearest the middle of the band. Committed from the jump press: the plan (absolute
frames) is checked again every tick; failing, the air variants (rune_pogo's best_air toward the landing band) or, none
safe, the run hands back.

    pl = OverPlanner(sim, ctx, cfg)              # ctx: rune_pogo.Ctx (b_box = F's tall box, f_box = B's box)
    p = pl.best_over(...)                        # or None
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np

from ssbot.combat import rune_pogo as _rp
from ssbot.knowledge import kinematics as kin


def _on(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip() == "1"


PMCAST = _on("SSBOT_FORUM_TWO_PMCAST")
M_L, M_R, M_D, M_J, M_A = _rp.M_L, _rp.M_R, _rp.M_D, _rp.M_J, _rp.M_A
FLOOR = _rp.FLOOR
TALL_TOP, LOW_TOP = 4.78, 3.19         # F's body top above the floor: Spell Antic 8 on / Cast 1 / Cast 2 0-13; Cast 2 14 on
NO_UMB = 1 << 40                        # a plan's umbrella press beyond any horizon (none); (fp1: 10 ** 6 was below
#                                         the live frame numbers ~8.9e6: every plan held the jump key to its landing)
IDLE_HALF = 2.25                        # F's Idle body front (it may turn to face her once its cast is over)
IDLE_TOP = 3.92


@dataclass
class PcCfg:
    """SSBOT_FORUM_TWO_PMCAST_SET="trig=force,ret=2": trial overrides."""
    trig: str = "nat"          # nat: TWO_PUSHMID's gates (F nearer its wall than B, B idle / walking and out of the lock-
    #                            bounded run's reach); force: every close cast of F with room behind it (the fixed point)
    ret: int = 1               # the herd's return rule: 1 after one F move, 2 once the lock-bounded run to B passes
    room_c: float = 4.3        # F's centre to the wall behind it (away from her) at the antic >= this (land_lo + the wall pad + 0.3)
    d_max: float = 7.5         # she within this of F's centre at the antic (in front of it)
    land_lo: float = 3.5       # her landing behind x0 (fp1: F turns to face her in its Idle - its front 2.25 + her
    #                            half width 0.25 + 1.0: fp2 - her ground slashes push F 0.48 u toward her landing side and
    #                            the real drift after the bounce fell 0.5 - 0.8 u short of the model's) ...
    land_hi: float = 5.6       # ... to this (ring 2's inner edge 5.98 - her half width - 0.15)
    wall_pad: float = 0.5      # and this clear of the wall
    k_plan0: int = 12          # over plans from this antic frame on ...
    k_last: int = 62           # ... the jump pressed by this antic frame at the latest (else the low hop)
    tgt_c: int = 8             # the contact's target: Cast 2 + this (fp1: contacts near Cast 2 + 14, where its body
    #                            top drops 4.78 -> 3.19 u, missed; the i-frames ~9 frames, ring 0 lights ~C + 20)
    idle_k: int = 22           # F's body may turn toward her from Cast 2 + this (its Idle: the box both ways)
    guard_u: float = 0.7       # after the bounce: falling within this of F's body box (x) -> the key away from it
    every: int = 3             # ... every this many ticks (the plan kept and checked between)
    horizon: int = 110
    body_m: float = 0.1
    bomb_m: float = 0.15
    contact_in: float = 0.3
    after_contact: int = 95
    umb_after: tuple = (8, 14)  # umbrella variants: pressed this many frames after the contact


def cfg_from_env() -> PcCfg:
    c = PcCfg()
    for kv in os.environ.get("SSBOT_FORUM_TWO_PMCAST_SET", "").replace(";", ",").split(","):
        if "=" not in kv:
            continue
        k, v = (x.strip() for x in kv.split("=", 1))
        if not hasattr(c, k):
            raise KeyError(f"SSBOT_FORUM_TWO_PMCAST_SET: unknown key {k!r}")
        cur = getattr(c, k)
        setattr(c, k, v if isinstance(cur, str) else type(cur)(float(v)))
    return c


def rt_cfg(c: PcCfg) -> _rp.RtCfg:
    return _rp.RtCfg(horizon=c.horizon, body_m=c.body_m, contact_in=c.contact_in, after_contact=c.after_contact,
                     umb_f=NO_UMB, bomb_m=c.bomb_m)


class OverPlanner(_rp.Planner):
    """rune_pogo's Planner with F as the pogo target (ctx.b_box: its tall box) whose body top drops at the mask frame
    low_F (Cast 2 + 14: the contact box then is the low one) and the over plans' landing band."""

    def __init__(self, sim, ctx: _rp.Ctx, cfg: PcCfg, low_F: int, x0: float, wdir: int,
                 walls: tuple = (_rp.WALL_L, _rp.WALL_R), idle_F: int | None = None):
        super().__init__(sim, ctx, rt_cfg(cfg))
        self.pc = cfg
        self.low_F, self.x0, self.wdir, self.walls = low_F, x0, wdir, walls
        self.idle_F = (low_F - 14 + cfg.idle_k) if idle_F is None else idle_F

    def _boxes(self) -> tuple:
        x0, y0, x1, _y1 = self._b_contact_box()
        return (x0, y0, x1, FLOOR + TALL_TOP), (x0, y0, x1, FLOOR + LOW_TOP)

    def _hit(self, ro: kin.Rollout, faces: np.ndarray) -> np.ndarray:
        """The slash meets F's box on this frame and the next (fp1: one-frame contacts missed live): the tall box to
        low_F - 3, the low one from there (the drop's frame is not known to the frame)."""
        tall, low = self._boxes()
        T1 = ro.flags.shape[1]
        h_t = _rp.slash_hits(ro, faces, tall, self.off)
        h_l = _rp.slash_hits(ro, faces, low, self.off)
        il = self._i(self.low_F) - 3
        idx = np.arange(T1)[None, :]
        h = np.where(idx < il, h_t, h_l)
        h2 = np.zeros_like(h)
        h2[:, :-1] = h[:, :-1] & h[:, 1:]
        return h2

    def danger(self, ro: kin.Rollout, contacts: np.ndarray) -> np.ndarray:
        """rune_pogo's dangers but F's body by time: the tall box to low_F, the low one (top 3.19 u) to idle_F, then
        its Idle body both ways from x0 (fp1: it turns to face her) - outside the i-frames and the 2 frames before the
        contact."""
        b_box = self.c.b_box
        self.c.b_box = None
        try:
            bad_i = super().danger(ro, contacts)
        finally:
            self.c.b_box = b_box
        N, T1 = ro.flags.shape
        idx = np.arange(T1)[None, :]
        inv = (ro.flags & kin.F_INVULN) != 0
        pre = (contacts[:, None] >= 0) & (idx >= contacts[:, None] - 2) & (idx < contacts[:, None])
        x0b, _y0, x1b, _y1 = b_box
        il, ii = self._i(self.low_F), self._i(self.idle_F)
        m = self.pc.body_m
        hit = np.zeros((N, T1), bool)
        for lo, hi, box in ((0, il, (x0b, FLOOR - 1.0, x1b, FLOOR + TALL_TOP)),
                            (il, ii, (x0b - 0.2, FLOOR - 1.0, x1b + 0.2, FLOOR + LOW_TOP)),
                            (ii, T1, (self.x0 - IDLE_HALF, FLOOR - 1.0, self.x0 + IDLE_HALF, FLOOR + IDLE_TOP))):
            lo, hi = max(lo, self.off + 1), min(hi, T1)
            if hi > lo:
                h = _rp.box_hits(ro, box, m)
                hit[:, lo:hi] |= h[:, lo:hi]
        hit &= ~inv & ~pre
        first = np.where(hit.any(axis=1), np.argmax(hit, axis=1), -1)
        out = bad_i.copy()
        for n in range(N):
            if first[n] >= 0 and (out[n] < 0 or first[n] < out[n]):
                out[n] = first[n]
        return out

    def _contact(self, ro: kin.Rollout, plans: list) -> np.ndarray:
        N, T1 = ro.flags.shape
        out = np.full(N, -1)
        hit = self._hit(ro, self._faces(plans))
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

    def landing(self, n: int, from_i: int) -> tuple[int | None, float | None]:
        """Plan n's first ground frame (rollout index) from from_i on and her x there (last_ro)."""
        ro = self.last_ro
        gnd = (ro.flags[n] & kin.F_GROUND) != 0
        ks = np.flatnonzero(gnd[from_i:])
        if not len(ks):
            return None, None
        i = from_i + int(ks[0])
        return i, float(ro.centre[n, i, 0])

    def band_ok(self, x: float | None) -> bool:
        if x is None:
            return False
        u = (x - self.x0) * self.wdir
        return (self.pc.land_lo <= u <= self.pc.land_hi
                and self.walls[0] + self.pc.wall_pad <= x <= self.walls[1] - self.pc.wall_pad)

    def check(self, plans: list) -> list:
        """Evaluate and keep the plans that are safe and land in the band after their contact."""
        self.evaluate(plans)
        out = []
        for n, p in enumerate(plans):
            if p.bad is not None or p.contact is None:
                continue
            i, x = self.landing(n, self._i(p.contact) + 1)
            if i is None or not self.band_ok(x):
                continue
            p.why = f"{p.why} land {self._F(i)} x {x:.2f}"
            out.append((p, self._F(i), x))
        return out

    def best_over(self, target_F: int | None = None, ws: tuple = (0, 3, 7, 12), holds: tuple = (18, 26),
                  dds: tuple = (6, 10, 14, 18), es: tuple = (0, 12, 30)) -> _rp.Plan | None:
        """From the ground: the safe over plans (module docstring); the contact nearest target_F (the person: just
        before the runes - ring 0 lights ~C + 20), then the latest jump, no umbrella, the band's middle."""
        c, F0 = self.c, self.c.F0
        dk = M_R if self.wdir > 0 else M_L
        j_lo = F0 + (2 if c.j_held else 0)
        base = []
        for w in ws:
            for H in holds:
                for dd in dds:
                    j0 = j_lo + w
                    base.append(_rp.Plan("over", dk, j0 + dd, j0 + dd + 60, jump=(j0, H),
                                         why=f"over w{w} H{H} dd{dd}"))
        ro = self._roll(base)
        faces = np.full(len(base), 1 if self.wdir > 0 else -1)
        tall, _low = self._boxes()
        top = np.where(np.arange(ro.flags.shape[1])[None, :] < self._i(self.low_F), tall[3], FLOOR + LOW_TOP)
        hit = self._hit(ro, faces) & (ro.box[..., 1] >= top - 0.3) & (ro.vel[..., 1] < 0)
        cands = []
        for n, p in enumerate(base):
            ks = np.flatnonzero(hit[n])
            if not len(ks):
                continue
            k = int(ks[0])
            for a in (5, 4, 6, 3):
                P = self._F(k) - a
                if P <= p.jump[0] + 2 or P < c.atk_ready_f:
                    continue
                for e in es:
                    # the drift past the contact: e frames after the press + 6 (no key after it: she falls straight)
                    cands.append(_rp.Plan("over", p.dirk, p.d0, P + 6 + e, jump=(p.jump[0], min(p.jump[1],
                                          P - p.jump[0])), press=P, umb=NO_UMB, why=p.why + f" a{a} e{e}"))
                break
        if not cands:
            return None
        ok = self.check(cands)
        # none safe: the umbrella variants of the plans with a contact (it holds the height over ring 1)
        umbs = []
        for p in cands:
            if ok or p.contact is None:
                continue
            for u in self.pc.umb_after:
                umbs.append(_rp.Plan("over", p.dirk, p.d0, p.d1, jump=p.jump, press=p.press, umb=p.contact + u,
                                     why=p.why.split(" land")[0] + f" u{u}"))
        if umbs:
            ok += self.check(umbs)
        if not ok:
            return None
        mid = 0.5 * (self.pc.land_lo + self.pc.land_hi)
        best = max(ok, key=lambda t: (-abs(t[0].contact - target_F) if target_F is not None else 0, t[0].jump[0],
                                      t[0].umb == NO_UMB, -abs((t[2] - self.x0) * self.wdir - mid)))
        return best[0]

    def again(self, p: _rp.Plan) -> bool:
        """The committed plan (absolute frames) is still safe and lands in the band."""
        q = _rp.Plan(p.kind, p.dirk, p.d0, p.d1, p.jump, p.press, None, p.umb, p.hold_j, why=p.why)
        ok = self.check([q])
        if ok:
            p.contact = q.contact
            return True
        return False


def warm(params) -> float:
    """Compile / load the over planner's paths (a synthetic close cast: her 4 u in front of F, 20 frames into its
    antic)."""
    import time
    from ssbot.combat.air_chain import ChainSim
    from ssbot.knowledge.kinematics import HoldState, Terrain2D
    t0 = time.perf_counter()
    terr = Terrain2D.from_boxes([(-200.0, FLOOR - 10.0, 260.0, FLOOR), (0.0, 0.0, _rp.WALL_L, 40.0),
                                 (_rp.WALL_R, 0.0, 70.0, 40.0)])
    fx, hx = 20.0, 24.0
    S = kin.initial_state(params, hx, 4.568, facing=-1, ground=True)
    sim = ChainSim(S, np.zeros(2, np.int64), HoldState.idle(1), params, terr, 1000, 1001)
    F0 = 1003
    bb = (fx - 2.06, FLOOR, fx + 1.34, FLOOR + TALL_TOP)
    bk = np.array([[1, fx + 4.2, FLOOR + 0.64, 2.166, 50, 58], [1, fx - 4.2, FLOOR + 0.64, 2.166, 50, 58]], float)
    ctx = _rp.Ctx(F0=F0, b_box=bb, b_x=fx, b_ok=True, tx=fx - 4.0, face=-1, ground=True, atk_ready_f=F0, bombs=bk)
    pl = OverPlanner(sim, ctx, PcCfg(), F0 + 45, fx, -1)
    pl.best_over(ws=(0, 8), holds=(26,), dds=(12,), es=(0, 16))
    return time.perf_counter() - t0
