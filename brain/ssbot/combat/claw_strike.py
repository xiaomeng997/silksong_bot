"""SP13: SSBOT_FORUM_CLAWSTRIKE - the Clawline approach to the slam strike (task 1v1 SP13, default off; the person,
2026-10-18 ~07:50, watching runs: "several slams at the range limit - no time to run over, jump and down-slash, and no
way to dodge outward either; the small hop + Clawline + down slash skill is badly needed").

S = the Clapper in Slam Antic (it does not move in its antic but for a hit's 0.48 u knock-back, its timing is fixed:
Slam 0 at antic frame 48 / 49; it does not react to the hook - only Idle does). When the playbook (combat.slam_play)
cannot start its ground strike on S in time (no time to walk, too far, in the air with no landing in time, the jump band
missed) the run plays, from the antic's first STATE frames:
  hop    on the ground: the jump held `hop` frames (none when she is already in the air)
  press  the turn key toward S on the frame before, then the Clawline (key S, the ACTION bit 4) with the key toward S for
         two frames at the mask frame P (antic frame k_P), her box bottom in S's body band at the ray check (<= RAY_BB)
  lock   no key until control returns (accepting input, no Harpoon clip)
  strike the air chain's strike (combat.air_chain's plans: a drift key, the down slash on S's Slam 0 body at antic frame
         44-50; the playbook's press part and way out after it)
The Clawline's live timeline (108 SP10c / SP12b runs, `m2_play/sp13/claw_cal.py`; frames from the press's mask frame
P): Harpoon Antic P + 2 .. + 10 (she drifts ~1.25 u toward, her box bottom y_P - 0.26 + 0.079 vy_P, sd 0.10), the
needle's hit P + 10 / 11 (frozen to the dash), the dash from P + 19 .. 22 (p50 21; 70 u/s: 1.4 u per physics step), the
catch (the stop) after 3-7 frames of dash, control 5 / 6 frames after the catch (P + 26 .. 34, p50 32) with vy -10 for
one frame and then the pogo's bounce (vy 17.4: kinematics EV_POGO reproduces it frame by frame) - **but no i-frames
(tm.ds 0, inv 0) and the attack cooled down for 0.15 s more (27 / 27 runs)**: the strike's down slash can be pressed
from control + 9 at the earliest. With Slam 0 at 48 / 49 and the strike pressed by Slam 0 + 1 (the playbook's 52: 0 / 12
safe), control must come by antic frame ~40: the Clawline by antic frame ~8-12 (the person's 15-20 assumed control 25-30
frames after the press and no cooldown). Against a still body the stop leaves her box ~2 u short of its front (Clapper
p50 2.26, answer.txt; the hooked body's contact is off to 0.2 s after control).

The plan (each tick until the press; the strike again from control on): candidates (hop, P) rolled with the hero model
(the policy's ChainSim), the Clawline phase from the live timeline in GAP x CTRL variants (the stop gap 1.7 / 2.5 u,
control at the catch + 5 / 6 with the dash from + 20 / 21), then from control the air chain's strike plans evaluated in
B's two slam timelines (antic 48 / 49): a contact on S's Slam 0 body in the slash's active frames before she lands and
her box clear of S's hammer / body outside the strike's i-frames to the contact + 18. A (hop, P) passes when every
variant has a passing strike plan; the earliest such P is played.

    cs = ClawStrike()                                  # module constants; SSBOT_FORUM_CLAWSTRIKE_SET overrides
    plan = cs.plan(sim, ctx)                           # ctx: CsCtx from the STATE (slam_play builds it)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import numpy as np

from ssbot.combat import air_chain as _ac
from ssbot.knowledge import kinematics as kin


def _on(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip() == "1"


# SP13 A/B (cc69bf0, w13, 64 episodes per arm, the same seeds 9900000.. / 9910000..; rnjb vs cs13f = trigger force):
# HP-hitless clears 10 -> 14 / 64 (+0.063, 90 % -0.047 .. +0.172), landed / s 1.331 -> 1.358 (-0.031 .. +0.086), HP-loss
# hits / min 3.422 -> 3.423 (-0.76 .. +0.76), both killed 46 -> 44 (-11 .. +6); the person's rule (the best on hitless
# clears, not worse on the others): CLAWSTRIKE follows SSBOT_FORUM_V2 when unset (on with v2, trigger force), =0 off
# (arm rnsp13_0 = the SP12b default)
CLAWSTRIKE = _on("SSBOT_FORUM_CLAWSTRIKE", "1" if _on("SSBOT_FORUM_V2") else "0")
# SSBOT_FORUM_AIRSTRIKE (SP13a, default off): the air approach to the same strike when she is in the air at S's antic
# and the playbook's landing comes too late (or no Clawline plan exists): combat.air_chain's search with S as its B (a
# drift toward S's strike point, an optional down slash on a body below - S's antic body or the other one's -, the
# umbrella, the strike at S's antic frame 46-48), re-checked every tick, kept near the strike (slam_play)
AIRSTRIKE = _on("SSBOT_FORUM_AIRSTRIKE")
M_L, M_R, M_D, M_J, M_A = kin.B_LEFT, kin.B_RIGHT, kin.B_DOWN, kin.B_JUMP, kin.B_ATTACK
M_CLAW = 1 << 4                 # the clawline button (ssbot.ipc.framing.BUTTONS order; key S)
FLOOR = 3.015                   # the Forum floor (box bottom standing)
POS_DY = 1.553                  # hero.pos above her box bottom
HALF_W = 0.23                   # her box half width
# the live timeline (frames from the press's mask frame P; claw_cal.py over 106 runs)
ANTIC_DX = 1.25                 # u toward in Harpoon Antic (p50 1.18, p90 1.32)
DY0, DYV = -0.261, 0.0788       # her box bottom at the throw: y_P + DY0 + DYV * vy_P (resid sd 0.10)
DASH_U = 1.4 * 50.0 / 60.0      # u per 60 Hz frame (70 u/s, 0.02 s physics steps)
VY_RANGE = (-6.0, 9.0)          # her vy at the press inside the live runs' range (the fit above)
DASH_MAX_U = 7.0                # the dash runs 0.1 s at most
ATK_CD_S = 0.15                 # the attack cooldown at control (s)
# SSBOT_FORUM_HERO2 (map v2 stage M0, default off; forum.md 91): the hold height from the Harpoon Antic's own rules
# (ClampVelocity2D y -10 .. 5, then DecelerateXY 0.875 per step, gravity off, to the throw 9 frames after the press):
# her box bottom at the throw = bb + H2_HOLD_K * clamp(vy, -10, 5) with bb / vy her free-flight state at the press's
# latched frame (the model's rollout at P); live m0_probe 123 airborne presses vy -19.6 .. +17.4: exact to 0.000 u
# (p10 / p90) with the 7 / 8 physics steps known, K 0.0744 / 0.0804 without (DY0 / DYV above were fitted on the state
# two frames before the latch: the SP13 runs' P was the decision frame)
HERO2 = kin.hero2_on()
H2_HOLD_K = 0.0774
H2_HOLD_SPREAD = 0.0030         # +- per u/s of the clamped vy (7 vs 8 physics steps in the antic)


def hold_bb(bb: float, vy: float) -> float:
    """Her box bottom (above the floor) held through the Clawline from her state at the press."""
    if HERO2:
        return bb + H2_HOLD_K * min(max(vy, -10.0), 5.0)
    return bb + DY0 + DYV * vy


def vy_ok(vy: float) -> bool:
    """Her vy at the press inside the hold model's range (HERO2: any; the clamp holds over the measured -19.6 .. 17.4)."""
    if HERO2:
        return -30.0 <= vy <= 25.0
    return VY_RANGE[0] <= vy <= VY_RANGE[1]
GOOD_OK = 4                     # plan(): a (hop, P) with this many passing strike plans in its worst variant is taken
BUDGET_S = 0.020                # plan(): stop searching after this long once one passes
HARD_S = 0.030                  # ... and after this long in any case
DS_REC0 = 0.1                   # HeroController.DownspikeBounce(harpoonRecoil): FinishDownspike(standardRecovery=False)
#                                 starts the down slash's recovery timer at 0.1 s (to Config.DownspikeRecoveryTime);
#                                 CanDownAttack is false while downSpikeBouncing (DOWNSPIKE_REBOUND_STEPS) or recovering
# the Slam Antic body (pogo_clapper_slam.json root box from antic frame 6: -1.341 .. 1.873 along its facing; top 0.532
# below its position, i.e. 3.90 u above the floor)
BODY_FRONT = 1.873
BODY_BACK = 1.341
BODY_TOP = 3.90


@dataclass
class CsCfg:
    gaps: tuple = (1.7, 2.5)        # the stop: her box front edge this far short of the body front (u)
    ctrl: tuple = (25, 27)          # control = the dash's start + catch-to-control (20 / 21 + 5 / 6) + the dash frames
    ray_bb: float = 3.3             # her box bottom at the press at most (the ray band: bb + 0.5 .. + 1.98 meets the body)
    ray_lo: float = 0.6             # ... and at least (in the air, above the floor's hover)
    reach: float = 10.2             # her box centre to the body front at the press at most (the ray's 10.5 u)
    k_last: int = 14                # the latest antic frame of the press considered
    hops: tuple = (3, 4, 5, 6)      # the hop's jump-held frames (on the ground; the offline study: 3-5 pass, 8+ none)
    press_k: tuple = (44, 51)       # the strike press's antic frames (inclusive)
    cd_f: int = 10                  # the strike press at control + this at the earliest (0.15 s + 1)
    drifts: tuple = (0, 3, 6, 10)   # the drift key's frames after control (toward / away)
    pre_press: tuple = (45, 50)     # plan(): the strike grid of the Clawline's feasibility check (a coarser one: the
    pre_drifts: tuple = (0, 4)      # full grid is searched again from control on)
    room: int = 0                   # 1: only when she cannot leave the hammer's reach (12.5 u) behind her
    other_free: int = 1             # the other Clapper Idle / Walk at the start (else no Clawline: she is locked ~30 f)
    trigger: str = "force"          # "force" (the default since the SP13 A/B): every slam from force_min_u it can plan;
    #                                 "reach": only the playbook's reach / time declines (hardly fires with two Clappers:
    #                                 those slams start with her high in the air)
    force_min_u: float = 5.6        # "force": her centre this far from its centre at least

    @classmethod
    def from_env(cls) -> "CsCfg":
        c = cls()
        for kv in os.environ.get("SSBOT_FORUM_CLAWSTRIKE_SET", "").replace(";", ",").split(","):
            if "=" not in kv:
                continue
            k, v = (x.strip() for x in kv.split("=", 1))
            if not hasattr(c, k):
                raise KeyError(f"SSBOT_FORUM_CLAWSTRIKE_SET: unknown key {k!r}")
            cur = getattr(c, k)
            if isinstance(cur, tuple):
                setattr(c, k, tuple(type(cur[0])(float(x)) for x in v.split(":")))
            elif isinstance(cur, str):
                setattr(c, k, v)
            else:
                setattr(c, k, type(cur)(float(v)))
        return c


@dataclass
class CsCtx:
    """S (the slammer) and her from the STATE: world x / y, facings, S's antic frame at the sim's rollout index 0."""
    s_iid: object
    s_x: float
    s_y: float
    s_face: int
    kb0: int                        # S's antic frame at rollout index 0 (STATE frame sim.fo)
    hero_x: float
    face: int
    other_box: tuple | None = None  # the other Clapper's body AABB (safety) or None
    tls: list = field(default_factory=list)


@dataclass
class CsPlan:
    f0: int                         # the mask frame of the plan's cmds index 0
    hop: int                        # jump frames from f0 (0: none)
    f_press: int                    # the Clawline's mask frame
    k_press: int                    # S's antic frame of it
    n_ok: int = 0                   # passing strike plans over every variant
    var_ok: list = field(default_factory=list)   # per variant: passing strike plans
    bb_press: float | None = None   # her box bottom at the press (model)
    ctrl_k: tuple = ()              # S's antic frames of control in the variants
    strike: list = field(default_factory=list)   # a sample strike plan per variant (air_chain.Plan.row())

    def row(self) -> list:
        return [self.f0, self.hop, self.f_press, self.k_press, self.n_ok, self.var_ok,
                None if self.bb_press is None else round(self.bb_press, 2), list(self.ctrl_k)]


def front_x(ctx: CsCtx) -> float:
    """S's body front edge (world x) in its antic."""
    return ctx.s_x + ctx.s_face * BODY_FRONT


def claw_phase(x_p: float, bb_p: float, vy_p: float, toward: int, fx: float, gap: float, ctrl: int
               ) -> tuple[float, float, int] | None:
    """The live timeline from the press state (her box centre x, box bottom above the floor, vy): (her stop x, box
    bottom held to control, control's frame after P), None when the dash cannot reach the stop (> DASH_MAX_U)."""
    x_t = x_p + toward * ANTIC_DX
    bb = max(hold_bb(bb_p, vy_p), 0.25)
    x_s = fx - toward * (gap + HALF_W)
    dist = (x_s - x_t) * toward
    if dist > DASH_MAX_U:
        return None
    n = 0 if dist <= 0 else int(np.ceil(dist / DASH_U))
    if dist <= 0:
        x_s = x_t
    return x_s, bb, ctrl + n


class ClawStrike:
    def __init__(self, cfg: CsCfg | None = None, params=None, terrain=None):
        self.cfg = cfg or CsCfg.from_env()
        self.params, self.terrain = params, terrain
        self._exact_cs_step_cache = None  # explicit private B2 actual-step scope only

    # ---- the strike after control ----

    def _ctrl_sim(self, sim: _ac.ChainSim, x_s: float, bb: float, face: int, f_ctrl: int) -> _ac.ChainSim:
        """The hero model from control (STATE frame f_ctrl): the catch's state one frame before, the pogo's bounce on
        the control frame without its i-frames (the Clawline's bounce has none), the attack cooling down."""
        S = kin.initial_state(sim.params, x_s, FLOOR + bb + POS_DY, vy=0.0, facing=face, ground=False)
        S[kin.ATK_CD] = ATK_CD_S + 1.0 / 60.0
        ev = np.zeros((1, 1), np.int64)
        ev[0, 0] = kin.EV_POGO
        ro = kin.rollout(S, np.zeros((1, 1), np.int64), sim.params, sim.terrain, events=ev)
        S1 = np.array(ro.final[:, 0], float)
        S1[kin.INV_T] = 0.0
        # FinishDownspike(standardRecovery=False): the recovery timer starts at 0.1 s (a down slash's at 0)
        S1[kin.DS_REC] = DS_REC0 + 1.0 / 60.0
        return _ac.ChainSim(S1, np.zeros(0, np.int64), kin.HoldState.idle(1), sim.params, sim.terrain, f_ctrl,
                            f_ctrl - 1)

    def strike_plans(self, csim: _ac.ChainSim, ctx: CsCtx, a_entry: int, toward: int, coarse: bool = False) -> list:
        """The strike plans from control (a_entry: S's antic entry as a STATE frame)."""
        c = self.cfg
        F0 = csim.f + 2
        out = []
        pk, drifts = (c.pre_press, c.pre_drifts) if coarse else (c.press_k, c.drifts)
        lo = max(F0 + c.cd_f - 1, a_entry + pk[0])
        for fp in range(lo, a_entry + pk[1] + 1):
            for d in drifts:
                for dk in ((0,) if d == 0 else (toward, -toward)):
                    m = 0 if dk == 0 else (M_R if dk > 0 else M_L)
                    out.append(_ac.Plan(F0, m, F0 + d, None, None, fp, fp - a_entry, ctx.s_iid))
        return out

    def eval_strike(self, csim: _ac.ChainSim, ctx: CsCtx, a_entry: int, toward: int, coarse: bool = False) -> list:
        """The strike plans from control that pass in both slam timelines (air_chain.evaluate: S as B, the other one's
        body as A's box)."""
        cache = self._exact_cs_step_cache
        key = None
        if cache is not None:
            from .knife_chain_cs_cache import MISSING
            key = cache.key(self, csim, ctx, a_entry, toward, coarse)
            if key is not None:
                cached = cache.lookup(key)
                if cached is not MISSING:
                    return cached
        plans = self.strike_plans(csim, ctx, a_entry, toward, coarse)
        if not plans:
            if key is not None:cache.put(key, [])
            return []
        ac_ctx = _ac.Ctx(b_iid=ctx.s_iid, b_x=ctx.s_x, b_y=ctx.s_y, b_face=ctx.s_face, kb0=csim.fo - a_entry,
                         a_box=ctx.other_box, hero_x=float(csim.start[kin.PX]), face=toward, tls=ctx.tls)
        result = _ac.evaluate(csim, ac_ctx, plans, csim.f + 2)
        if key is not None:cache.put(key, result)
        return result

    # ---- the plan before the press ----

    def plan(self, sim: _ac.ChainSim, ctx: CsCtx, ground: bool, accepting: bool, hop_until: int | None = None,
             p_only: int | None = None, p_min: int | None = None, first_feasible: bool = False) -> CsPlan | None:
        """The (hop, P) whose every Clawline variant has a strike plan (the most passing plans in the worst variant,
        then the earliest P; the search stops at GOOD_OK or BUDGET_S); None: none.
        hop_until: a hop under way - the jump held to this mask frame (exclusive), no new hop; p_only: this press only.
        p_min is an optional absolute mask-frame floor, applied before every
        feasibility test. None preserves the legacy h2 search domain.
        first_feasible changes candidate preference only; no variant/contact/
        safety test is skipped. False keeps h2's GOOD_OK quality search."""
        import time
        if type(first_feasible) is not bool:raise ValueError("invalid first-feasible search preference")
        if p_min is not None and (type(p_min) is not int or p_min < 0):
            raise ValueError("invalid absolute first-Clawline floor")
        t0 = time.perf_counter()
        c = self.cfg
        F0 = sim.f + 2
        a_entry = sim.fo - ctx.kb0                          # S's antic entry (STATE frame)
        toward = 1 if ctx.s_x > ctx.hero_x else -1
        fx = front_x(ctx)
        new_hop = ground and accepting and hop_until is None
        hops = c.hops if new_hop else (0,)
        p_hi = a_entry + c.k_last
        rows = []
        for h in hops:
            lo = F0 + (2 if h else 1)
            if p_min is not None:lo = max(lo, p_min)
            for P in ((p_only,) if p_only is not None else range(lo, p_hi + 1)):
                if lo <= P <= p_hi:
                    rows.append((h, P))
        if not rows:
            return None
        T = max(P for _, P in rows) - F0 + 2
        cm = np.zeros((len(rows), T), np.int64)
        tk = M_R if toward > 0 else M_L
        for n, (h, P) in enumerate(rows):
            if h:
                cm[n, :h] |= M_J
            elif hop_until is not None and hop_until > F0:
                cm[n, :min(hop_until - F0, T)] |= M_J
            if P - 1 - F0 >= 0:
                cm[n, P - 1 - F0] |= tk
        ro = sim.roll(cm)
        off = sim.off
        cand = []
        for n, (h, P) in enumerate(rows):
            i = off + (P - F0)
            if i >= ro.box.shape[1]:
                continue
            # in the air from the frame after the first key to the press (a hop that lands again is no hop)
            if ((ro.flags[n, off + 1:i + 1] & kin.F_GROUND) != 0).any():
                continue
            bb = float(ro.box[n, i, 1]) - FLOOR
            vy = float(ro.vel[n, i, 1])
            xp = 0.5 * float(ro.box[n, i, 0] + ro.box[n, i, 2])
            if not c.ray_lo <= hold_bb(bb, vy) <= c.ray_bb:
                continue
            if not vy_ok(vy):
                # the hold height's fit (DY0, DYV) covers vy -5.4 .. +8.7 at the press; fp4 (162ca26): two presses in a
                # hop's fast rise held her 2.1-2.6 u up at control - no strike plan, the other one's hammer
                continue
            if (fx - xp) * toward - HALF_W > c.reach or (fx - xp) * toward < 0.5:
                continue
            cand.append((h, P, bb, vy, xp))
        best = None
        cand.sort(key=lambda r_: (r_[0], r_[1]))           # the smallest hop and the earliest press first
        for h, P, bb, vy, xp in cand:
            el = time.perf_counter() - t0
            if (el > BUDGET_S and best is not None) or el > HARD_S:
                break
            var_ok, ctrl_k, sample = [], [], []
            for gap in c.gaps:
                for cc in c.ctrl:
                    ph = claw_phase(xp, bb, vy, toward, fx, gap, cc)
                    ok = []
                    if ph is not None:
                        x_s, bbh, fc = ph
                        f_ctrl = P + fc
                        ctrl_k.append(f_ctrl - a_entry)
                        ok = self.eval_strike(self._ctrl_sim(sim, x_s, bbh, toward, f_ctrl), ctx, a_entry, toward,
                                              coarse=True)
                    var_ok.append(len(ok))
                    sample.append(ok[0].row() if ok else None)
                    if not ok:
                        break
                if var_ok[-1] == 0:
                    break
            if len(var_ok) < len(c.gaps) * len(c.ctrl) or min(var_ok) == 0:
                continue
            p = CsPlan(F0, h, P, P - a_entry, sum(var_ok), var_ok, bb, tuple(ctrl_k), sample)
            # Every gap/control variant has a real passing strike witness. B2
            # may stop at this first feasible candidate rather than spend the
            # remaining clock budget optimizing the number of future choices.
            if first_feasible:return p
            if best is None or (-min(p.var_ok), p.f_press) < (-min(best.var_ok), best.f_press):
                best = p
            if min(best.var_ok) >= GOOD_OK:
                break
        return best


def plan_mask(p: CsPlan, F: int, toward: int) -> int:
    """The keys of the plan for mask frame F up to the press's second frame (the lock after it: no key)."""
    m = 0
    if p.hop and p.f0 <= F < p.f0 + p.hop:
        m |= M_J
    tk = M_R if toward > 0 else M_L
    if F == p.f_press - 1:
        m |= tk
    if p.f_press <= F < p.f_press + 2:
        m = (m & ~M_J) | M_CLAW | tk
    return m


def warm(params) -> float:
    """Compile the numba paths (a synthetic slam: her 8 u in front on the ground at antic frame 3)."""
    import time
    t0 = time.perf_counter()
    terr = kin.Terrain2D.from_boxes([(-200.0, FLOOR - 10.0, 260.0, FLOOR), (0.0, 0.0, 14.01, 40.0),
                                     (48.99, 0.0, 70.0, 40.0)])
    S = kin.initial_state(params, 23.0, FLOOR + POS_DY, facing=1, ground=True)
    sim = _ac.ChainSim(S, np.zeros(1, np.int64), kin.HoldState.idle(1), params, terr, 1000, 1000)
    ctx = CsCtx(s_iid=8, s_x=31.0, s_y=FLOOR + 4.434, s_face=-1, kb0=3, hero_x=23.0, face=1, tls=_ac.timelines())
    ClawStrike(CsCfg(), params, terr).plan(sim, ctx, True, True)
    return time.perf_counter() - t0


__all__ = ["CLAWSTRIKE", "CsCfg", "CsCtx", "CsPlan", "ClawStrike", "claw_phase", "plan_mask", "warm", "M_CLAW"]
