"""Map v2 L3: the SEARCH (docs/plans/forum_map_v2.md section 1 L3, 1b and section 0; stage M3). Offline / planning
code only: nothing in the live bot imports it (tests/test_map2_search.py checks it).

    from ssbot.map2 import search as ms
    W = ms.World()                                          # the hero model (HERO2), the M1 engine, the Clapper model
    sit = ms.Situation(S, obs, mems)                        # her exact kin state, the Clappers (Obs / Memory)
    res = ms.Searcher(W, ms.Cfg()).decide(sit, prev=None)   # -> Result: the plan, its evaluation, the log row
    res.plan, res.ev.value, res.ev.p_safe, res.log

THE LOOP (one decision; re-planned every tick, receding horizon):
 1. ROOT: predict() the Clappers under her do-nothing path (M2) -> outcome branches (p, choices, reveal frames).
 2. EXPAND a node (her state at a frame, the plan so far, the prediction after its hits): the M1 envelope pass from
    her exact state (event-limited segment families, cfg.passes) with the union of the branches' damage (margins on)
    and the arena's walls cut out; the WINDOWS bound to the enemy (strike.py: per branch, Clapper and frame the press
    region of each primitive - the down slash on its robust body, the hooked Clawline at its body) intersected with
    the pass's clusters (their end-condition bits: can down slash / can Clawline) -> candidate press points; the
    witness (M1: the cluster chain + the horizontal tracker) turns each into concrete keys + the press. Plus the
    safe-endpoint candidates (the pass's surviving clusters at its horizon, spread in x) and, with a library, the
    combo macros instantiated on their parameter grids (combos.py). Each node's children continue from the strike's
    next state (the pogo bounce, the Clawline's control) with the re-predicted Clappers - depth cfg.depth, beam
    cfg.beam.
 3. EVALUATE a plan (concrete keys) - the 'exact computation': simulate it with the hero model (kin_jit HERO2) and
    the strike module in CLOSED LOOP with the Clappers: predict under the plan's path; per branch find its contacts /
    hooks (robust targets); every new hit re-predicts (the hit changes an Idle Clapper's future) and the branches
    consistent with the history before the hit carry on. Per OUTCOME (branch x Clawline variant):
    - COMMIT / REVEAL / REACTIVE STEERING: her hurtbox against the branch's damage shapes (margins; not in the pogo
      i-frames) frame by frame; a collision before reveal + cfg.lag (the frame she can tell this branch apart and
      react; a Clawline block delays it to control) makes the plan unsafe; a collision after it is allowed only if
      a safe continuation exists from the plan's state at that frame (she steers away; the hits after it do not
      count);
    - the COARSE EXIT CHECK: from the plan's end (or the deviation) an envelope pass in that branch's danger for
      cfg.exit_h frames (cfg.exit_events events) must keep a cluster alive (an exit exists);
    - the VALUE: hits (cfg.w_hit) + the TERMINAL value at the end (room to the walls, the facing-to-the-wall rule:
      her side of a Clapper that will start its next move facing her, the distance to the nearest body: a strike
      window next).
    The plan's value = the expected value over the outcomes; safe = every outcome safe (hitless first).
 4. HYSTERESIS / TIME CAP: the previous plan (shifted by the elapsed frames) is re-evaluated first; a new plan
    replaces it only when better by cfg.w_switch; the search stops at cfg.cap_s and returns the best so far, or the
    committed plan if its check still passes, else none (the caller's fallback: the current planner).
 5. LOG: every chosen plan as a row in the combo library's step format (plan_steps): per segment its anchor (the
    decision frame or a Clawline's control), the key changes and the strike events, the hits, the outcomes.

SPEED (stage M4b; HANDOFF 'Task map2 - stage M4' / 'M4b'). Exact paths - the same decisions, checked on all 236
acceptance situations with a virtual clock (Searcher.vclock): predict() compiled (clapper_jit, Cfg.jit_predict), the
branches' records as arrays (clapper_jit.JBranch, brnum, Geo, first_collision), the windows vectorized, a trajectory
memo (Evaluator.sim), exit probes and an exit memo (Cfg.exit_probe), the envelope pass threaded (Cfg.fwd_threads).
The ANYTIME order (behaviour, default off; Cfg.live() turns it on): the 2-event pass after the first pass's first
candidates or on a background thread (Cfg.pass2_after / pass2_bg), the noop's evaluation reused and its exits deferred
(Cfg.reuse_root / defer_noop), a split search over processes (Searcher.part). The per-frame check of a committed plan
on the bot's thread is TickCheck; tick_check is the full check from a new observation.

Frames: game frames from the decision (0 = now); a plan's masks apply to frames 1 .. n (kin_jit's latched masks).
Positions: her transform (kin pos) for the Clapper model and the slash polygons, her box centre for the envelope;
u world units, centre to centre.
"""
from __future__ import annotations

import math
import os
import time
import zlib
from dataclasses import dataclass, field

import numpy as np

from ssbot.knowledge import hero2
from ssbot.knowledge import kinematics as km
from ssbot.map2 import brnum
from ssbot.map2 import clapper as cm
from ssbot.map2 import clapper_jit as cj
from ssbot.map2 import env_jit as ej
from ssbot.map2 import envelope as env
from ssbot.map2 import strike as sk

WALL_L, WALL_R = cm.WALL_L, cm.WALL_R
CEIL = 15.15                       # the Forum's ceiling step (box bottom of the ceiling, the middle; the roof is lower
#                                    within ~6 u of the walls: not modelled here)
HB = cm.HURTBOX                    # (0.2277, 1.1249, -0.3799)
HB_OFF = HB[2] + sk.CTR_DY         # her hurtbox centre relative to her box centre (+0.1336)
M_DS = km.B_ATTACK | km.B_DOWN
DIRS = km.B_LEFT | km.B_RIGHT


def arena_terrain() -> km.Terrain2D:
    """The Forum floor and the flat ceiling (walls: cut as danger, the envelope has no walls)."""
    return km.Terrain2D.from_boxes([(-1.0e4, sk.FLOOR - 2.0, 1.0e4, sk.FLOOR), (-1.0e4, CEIL, 1.0e4, CEIL + 2.0)])


WALL_BOXES = np.array([(-1.0e4, -1.0e4, WALL_L + sk.HALF_W, 1.0e4), (WALL_R - sk.HALF_W, -1.0e4, 1.0e4, 1.0e4)])


# ---- configuration --------------------------------------------------------------------------------------------------

@dataclass
class Cfg:
    passes: tuple = ((1, 60), (2, 30))     # the approach passes: (event limit, frames)
    exit_h: int = 40                       # the coarse exit check's frames
    exit_h_max: int = 180                  # ... stretched to a big rune's last lit frame (a jump cast's burst lights
    #                                        ~65 - 72 f after its landing: the spec's 3 s while a jump cast is on)
    exit_events: int = 1
    exit_probe: bool = True                # M4b: concrete probe exits before the pass (the same verdict, faster)
    jit_predict: bool = True               # M4b: the compiled predict (clapper_jit: the same branches, faster)
    t_pred: int = 72                       # the prediction horizon at least (frames; else the plan + 72)
    depth: int = 3                         # strike segments chained
    beam: int = 4                          # nodes kept per depth
    n_win: int = 7                         # window candidates per (primitive, Clapper, branch)
    n_safe: int = 5                        # safe-endpoint candidates per node
    n_refine: int = 4                      # down slash windows refined (+-1-2 f, +-0.4 u) per node
    n_branch: int = 3                      # branches whose windows are queried per node
    lag: int = 2                           # her reaction lag after a reveal (STATE 1-2 f late, keys 2 f ahead: 1b.3)
    margins: bool = True
    margin_scale: float = 1.0              # the measured margins x this (1: as measured; the sensitivity runs only)
    prims: tuple = ("dslash", "claw")
    cap_s: float = 8.0                     # the time cap of one decision
    depth_frac: tuple = (0.45, 0.8)        # the cumulative share of the cap that depth 1, 2, ... may use (the last: all)
    w_hit: float = 1.0
    w_face: float = 0.5                    # the facing-to-the-wall value (P3)
    w_wall: float = 0.08                   # per u of wall room under 3 u
    w_dist: float = 0.01                   # per u of distance to the nearest body beyond 6 u
    w_switch: float = 0.05                 # hysteresis: a new plan must beat the kept one by this
    w_time: float = 0.002                  # per frame to the plan's end (hits per second: sooner is better)
    face_wall_u: float = 12.0              # the facing rule acts within this of a wall (the person, 10-19)
    library: tuple = ()                    # combo macros (combos.Combo) - empty: primitives + the strike module only
    # CONTINGENT PLANS (the reaction to a hook is seen at the needle's hit, P + 8 / 9, long before control, P + 23 ..
    # 34: she re-plans at control per reaction - slam -> the first window, evade -> a second Clawline, jump -> the
    # ride, the person 10-22): a hooked Clawline whose hit splits the Clappers' future into reactions gets one child
    # node per reaction (its own danger, its own continuation), recombined into one plan with a continuation per
    # reaction (Seg.out_alt)
    split: bool = True
    split_min_p: float = 0.04              # reactions below this probability are not expanded (they keep the exit)
    split_max: int = 4                     # reactions expanded per split
    combine_top: int = 6                   # continuations per reaction whose exits are checked when recombining
    combine_splits: int = 4                # top-level splits recombined (the best by the open value; nested first)
    # M4b ANYTIME ORDER: > 0 - a node's later passes (the 2-event pass: 35 - 370 ms on the w7 recordings) are run only
    # after this many of the first pass's candidates were evaluated (or its queue ran out); their candidates then join
    # the M3 round robin for the rest of the node's queue. 0: every pass up front (M3).
    pass2_after: int = 0
    hard_cap: bool = False                 # M4b: the contingent plans' and the deferred noop's exit checks stop at
    #                                        the time (M3 ran them all: a two-Clapper decision with a 2 s cap took up to
    #                                        59 s); the outcomes left count as unchecked
    defer_noop: bool = False               # M4b: the noop (the fallback plan) gets its exit checks at the end, not
    #                                        before the first candidate (5 - 90 ms on the w7 recordings)
    reuse_root: bool = False               # M4b: the noop plan is the root's evaluation with its exits run (one
    #                                        prediction less; the same plan and value - M3 evaluated it twice)
    fwd_threads: int = 0                   # M4b: the approach passes' per-parent work on this many threads (> 1;
    #                                        env_jit.forward_par: the same pass)
    pass2_bg: bool = False                 # M4b: with pass2_after, the later passes run on a background thread from
    #                                        the node's start and join when done (the order then depends on time)
    safe_ts: tuple = ()                    # M4b: safe endpoints also at these frames of the first pass (before its
    #                                        end's; a short plan is ready sooner and keeps its exits more often)

    def replace(self, **kw) -> "Cfg":
        d = dict(self.__dict__)
        d.update(kw)
        return Cfg(**d)

    @classmethod
    def live(cls, **kw) -> "Cfg":
        """M4b's configuration for the live worker (HANDOFF 'Task map2 - stage M4' / 'M4b'): the anytime order (the
        2-event pass on the background thread, joined when done or after the first pass's queue), the passes on 2
        threads, the noop's evaluation reused and its exits deferred, a 1 s cap; with two worker processes per game
        instance each searcher takes a part (Searcher.part = (0, 2) / (1, 2)) and the better result wins."""
        d = dict(cap_s=1.0, pass2_after=6, pass2_bg=True, fwd_threads=2, reuse_root=True, defer_noop=True, hard_cap=True)
        d.update(kw)
        return cls(**d)


# ---- the world ----------------------------------------------------------------------------------------------------

class _Params(km.HeroParams):
    """HeroParams with its parameter vector computed once (kinematics.rollout asks for it on every call)."""

    def vector(self) -> np.ndarray:
        v = self.__dict__.get("_vec")
        if v is None:
            v = km.HeroParams.vector(self)
            self.__dict__["_vec"] = v
        return v


def _cached_params(p: km.HeroParams) -> km.HeroParams:
    import dataclasses
    return _Params(**{f.name: getattr(p, f.name) for f in dataclasses.fields(p)})


class World:
    """The fixed parts: the hero model (Wanderer, the Forum kit, HERO2), the M1 engine, the Clapper knowledge, the
    arena's terrain."""

    def __init__(self, K: cm.Know | None = None):
        self.params = _cached_params(env.load_params(hero2=True))
        self.E = env.Engine(self.params, claw=False)
        self.K = K or cm.Know.load()
        self.terr = arena_terrain()
        self.TT = self.terr.packed()

    def roll(self, S0: np.ndarray, masks: np.ndarray, events: np.ndarray | None = None) -> km.Rollout:
        m = np.asarray(masks, np.int64)
        if not len(m):
            m = np.zeros(1, np.int64)
        ev = None if events is None else np.asarray(events, np.int64)[None]
        return km.rollout(S0, m[None], self.params, self.terr, events=ev)


@dataclass
class Situation:
    """One decision: her exact kin state now, the Clappers as observed (Obs, Memory), the hazards of dead ones."""
    S: np.ndarray
    obs: list
    mems: dict
    hazards: list = field(default_factory=list)
    name: str = ""
    meta: dict = field(default_factory=dict)

    @property
    def alpha_c(self) -> int:
        return int(round(float(self.S[km.ALPHA]) * 6.0)) % 6


# ---- plans --------------------------------------------------------------------------------------------------------

@dataclass
class Seg:
    """One segment of a plan: masks for its frames (index 0 = the segment's first frame), down slash presses (frame
    index into masks, the target iid) and an optional hooked Clawline at its end (pressed on its last frame toward d at
    iid). The first segment starts at the decision; a segment after a Clawline starts at that hook's control (the
    strike module's branch point: its frame differs per outcome), any other after its predecessor's end."""
    masks: np.ndarray
    dsl: list = field(default_factory=list)       # [(i, iid)]: masks[i] has down + attack
    claw: tuple | None = None                     # (d, iid)
    tag: str = ""
    var_alt: dict | None = None                   # after a Clawline: the segment re-planned at control per hook
    #                                               variant (control is a branch point: she sees it and re-plans)
    out_alt: dict | None = None                   # after a Clawline: {reaction key: [Seg, ...]} the rest of the plan
    #                                               (this segment and the later ones) per reaction to the hook seen
    #                                               by control (reaction_key); a key not listed plays this one

    def copy(self) -> "Seg":
        return Seg(self.masks.copy(), list(self.dsl), self.claw, self.tag,
                   None if self.var_alt is None else {k: v.copy() for k, v in self.var_alt.items()},
                   None if self.out_alt is None else {k: [s.copy() for s in v] for k, v in self.out_alt.items()})


@dataclass
class Plan:
    segs: list
    origin: str = "prim"                          # "prim" / "safe" / "noop" / a combo's name
    note: str = ""

    def copy(self) -> "Plan":
        return Plan([s.copy() for s in self.segs], self.origin, self.note)

    def n_frames(self) -> int:
        return int(sum(len(s.masks) for s in self.segs))

    def shifted(self, n: int) -> "Plan | None":
        """The plan n frames later (the frames already played dropped from its first segment; None once its first
        segment - up to a Clawline press - is played: from there the plan is re-made at control)."""
        if not self.segs or n >= len(self.segs[0].masks):
            return None
        s0 = self.segs[0]
        seg = Seg(s0.masks[n:].copy(), [(i - n, iid) for (i, iid) in s0.dsl if i - n >= 0], s0.claw, s0.tag,
                  s0.var_alt, s0.out_alt)
        return Plan([seg] + [x.copy() for x in self.segs[1:]], self.origin, self.note)

    def key(self) -> tuple:
        out = []
        for s in self.segs:
            k = (tuple(int(v) for v in s.masks), tuple(s.dsl), s.claw)
            if s.out_alt:
                k += (tuple(sorted((tuple(sorted(rk)), Plan(v).key()) for rk, v in s.out_alt.items())),)
            out.append(k)
        return tuple(out)


# ---- the reaction to a hook (contingent plans) ----------------------------------------------------------------------

REACT_LO, REACT_HI = 7, 23        # the reaction's choices are made from the needle's hit (P + 8 / 9; the frame before
#                                   allowed) and seen by the earliest control (P + 23, strike.claw_hook's clamp)


def reaction_key(br, P: int, lag: int = 2) -> frozenset:
    """The Clappers' choices of the branch that she has SEEN by the earliest control of a Clawline pressed at P: made
    in P + 7 .. P + 23 - lag and revealed by then - (iid, outcome) pairs (e.g. {(1, 'SLAM')}); empty: no reaction
    (the hook's hit changed nothing yet, or what changed is not visible by control)."""
    hi = P + REACT_HI - lag
    out = []
    for iid, chs in br.choices.items():
        for c in chs:
            if P + REACT_LO <= c[2] <= hi and c[3] is not None and c[3] <= hi:
                out.append((int(iid), str(c[1])))
    return frozenset(out)


def rk_label(rk: frozenset) -> str:
    return ",".join(f"{iid % 1000}:{o}" for (iid, o) in sorted(rk)) or "none"


@dataclass
class Traj:
    """A plan simulated in one outcome: per frame (0 .. n) her transform, box, grounded, facing, mode, i-frames,
    Clawline block; the hits on the Clappers, the contacts, the hooks; the segment roll records (state_at)."""
    pos: np.ndarray
    box: np.ndarray
    ground: np.ndarray
    face: np.ndarray
    mode: np.ndarray
    ifr: np.ndarray
    blk: np.ndarray
    hits: dict
    contacts: list                 # [(frame, iid, kind)]
    hooks: list                    # [Hook]
    rolls: list                    # [(k0, S0, masks, events)] kin pieces (state_at)
    end: int
    seg_start: list                # the absolute start frame of each segment
    missed: list = field(default_factory=list)   # strikes that found no target: [(kind, frame, iid)]
    variant: str = ""
    claws: list = field(default_factory=list)    # every Clawline press: (P, iid, d, hooked, hit, ctrl)
    alts: list = field(default_factory=list)     # the reaction continuations played: (segment index, P, key)


def _ev(n: int) -> np.ndarray:
    return np.zeros(n, np.int64)


def _rows_sig(bx, lo: int, hi: int):
    """What a strike reads of a box array: its length, the rows lo .. hi - 1 and its last row (None: no array)."""
    if bx is None:
        return None
    return (len(bx), bx[lo:hi].tobytes(), bx[-1].tobytes() if len(bx) else b"")


def simulate(W: World, plan: Plan, boxes_fn, face0: int, S0: np.ndarray, variant: sk.HookVariant,
             alpha_c: int = 0, extra: int = 0, br=None, lag: int = 2, rec: list | None = None) -> Traj:
    """The plan from S0 in one outcome: boxes_fn(iid) -> the robust body boxes per frame of that branch. Each down
    slash press finds its contact (both alternations, robust box) and the bounce (EV_POGO); a Clawline hooks its
    target (strike.claw_hook) or, when the ray misses, is played unhooked (hero2.claw_unhooked) - a miss. extra:
    frames of no keys appended after the last segment. br: the outcome's branch - after a Clawline the rest of the
    plan follows the continuation of the reaction she has seen by control (Seg.out_alt, reaction_key).
    rec: a list that receives every input read from the branch (M4b's trajectory memo, Evaluator.sim): ("rows", iid,
    lo, hi, rows) the box rows lo .. hi - 1 a strike looked at (with the array's length and its last row), ("rk", P,
    key) a reaction key - the trajectory is a function of the plan, the start and these reads only."""
    P_, B_, G_, F_, M_, I_, C_ = [], [], [], [], [], [], []
    hits: dict = {}
    contacts, hooks, rolls, starts, missed, claws, alts = [], [], [], [], [], [], []
    S = S0.copy()
    k0 = 0
    face = face0
    pre_ev = 0                       # an event for the segment's first frame (the Clawline's forced bounce)
    first = True
    segs = list(plan.segs)
    played = []
    last_P = None
    si = -1
    while si + 1 < len(segs):
        si += 1
        seg = segs[si]
        if si > 0 and segs[si - 1].claw is not None:
            if seg.out_alt and br is not None and last_P is not None:
                rk = reaction_key(br, last_P, lag)
                if rec is not None:
                    rec.append(("rk", last_P, rk))
                alt = seg.out_alt.get(rk)
                if alt is not None:
                    segs = segs[:si] + list(alt)
                    alts.append((si, last_P, rk))
                    if si >= len(segs):
                        break
                    seg = segs[si]
            if seg.var_alt and variant.name in seg.var_alt:
                seg = seg.var_alt[variant.name]
        starts.append(k0)
        played.append(seg)
        masks = np.asarray(seg.masks, np.int64)
        if si == len(segs) - 1 and extra and seg.claw is None:
            masks = np.concatenate([masks, np.zeros(extra, np.int64)])
        n = len(masks)
        ev = _ev(max(n, 1))
        if pre_ev:
            ev[0] = pre_ev
        # the down slashes: contacts in order, each re-rolled with its bounce
        r = W.roll(S, masks if n else np.zeros(1, np.int64), ev)
        fac = sk.facing_track(face, masks if n else np.zeros(1, np.int64))
        for (i, iid) in sorted(seg.dsl):
            t = i + 1                                     # the press frame (rollout index)
            bx = boxes_fn(iid)
            if rec is not None:
                lo_, hi_ = k0 + t + sk.DS_ACTIVE[0], k0 + min(t + sk.DS_ACTIVE[1], n) + 1
                rec.append(("rows", iid, lo_, hi_, _rows_sig(bx, lo_, hi_)))
            rel = bx[k0:] if bx is not None else np.full((1, 4), np.nan)
            gnd = (r.flags[0] & km.F_GROUND) != 0
            c = sk.dslash_contact(r.pos[0], fac, gnd, t, rel)
            if c < 0:
                missed.append(("dslash", k0 + t, iid))
                continue
            ev[c - 1] |= km.EV_POGO                       # the events' index 0 = rollout index 1
            r = W.roll(S, masks if n else np.zeros(1, np.int64), ev)
            hits.setdefault(iid, {})[k0 + c] = ("down", sk.DS_DMG)
            contacts.append((k0 + c, iid, "down"))
        rolls.append((k0, S.copy(), masks.copy(), ev.copy()))
        nn = n if n else 0
        sl = slice(0 if first else 1, nn + 1)
        P_.append(r.pos[0, sl]), B_.append(r.box[0, sl]), G_.append(((r.flags[0] & km.F_GROUND) != 0)[sl])
        F_.append(fac[sl]), M_.append(r.mode[0, sl])
        ifr = np.zeros(nn + 1, bool)
        for (kc, iid_, kind) in contacts:
            if kind == "down" and k0 <= kc <= k0 + nn:
                ifr[kc - k0 + sk.DS_IFR[0]:kc - k0 + sk.DS_IFR[1] + 1] = True
        I_.append(ifr[sl]), C_.append(np.zeros(nn + 1, bool)[sl])
        first = False
        S = r.final[:, 0].copy()
        face = int(fac[-1])
        k0 += nn
        pre_ev = 0
        if seg.claw is not None:
            d, iid = seg.claw
            bx = boxes_fn(iid)
            if rec is not None:
                lo_, hi_ = k0 + sk.HOOK_HIT_F, k0 + 62
                rec.append(("rows", iid, lo_, hi_, _rows_sig(bx, lo_, hi_)))
            bxa = bx if bx is not None else np.full((k0 + 60, 4), np.nan)
            if len(bxa) < k0 + 60:
                bxa = np.concatenate([bxa, np.full((k0 + 60 - len(bxa), 4), np.nan)])
            hk = sk.claw_hook(S, k0, d, iid, bxa, variant, alpha_c)
            last_P = k0
            if hk.ok:
                hooks.append(hk)
                hits.setdefault(iid, {})[hk.hit] = ("claw", sk.CLAW_DMG)
                contacts.append((hk.hit, iid, "claw"))
                pos = hk.pos
                ctrl = hk.ctrl
                claws.append((k0, iid, d, True, hk.hit, ctrl))
            else:
                missed.append(("claw", k0, iid))
                # the unhooked Clawline (M0's track), control at P + 32 as an A1 start
                fs = [sk.steps_of(k0 + j, alpha_c) for j in range(1, 40)]
                tr = hero2.claw_unhooked(
                    float(S[km.PX]), float(S[km.PY]) - sk.FOOT, float(S[km.VX]), float(S[km.VY]), d, fs)
                pos = np.stack([tr.x, tr.bb + sk.FOOT], axis=1)
                ctrl = k0 + tr.ctrl
                hk = sk.Hook(k0, d, iid, "unhooked", pos, -1, ctrl, float(tr.x[-1]), float(tr.bb[-1]) + sk.FOOT,
                             False, "ray")
                claws.append((k0, iid, d, False, -1, ctrl))
            m = len(pos) - 1
            P_.append(pos[1:])
            bb = pos[1:, 1] - sk.FOOT
            B_.append(np.stack([pos[1:, 0] - sk.HALF_W, bb, pos[1:, 0] + sk.HALF_W, bb + 2 * sk.HALF_H], axis=1))
            G_.append(np.zeros(m, bool)), F_.append(np.full(m, d)), M_.append(np.full(m, km.M_NORMAL))
            I_.append(np.zeros(m, bool)), C_.append(np.ones(m, bool))
            S = sk.control_state(W.params, hk, float(S[km.ALPHA]), airdashed=float(S[km.AIRDASHED]))
            if hk.ok:
                pre_ev = km.EV_POGO
            face = d
            k0 = ctrl
    if pre_ev:                       # a plan ending at a Clawline's control: its forced bounce's first frame
        r = W.roll(S, np.zeros(1, np.int64), np.array([pre_ev]))
        rolls.append((k0, S.copy(), np.zeros(1, np.int64), np.array([pre_ev])))
        P_.append(r.pos[0, 1:]), B_.append(r.box[0, 1:]), G_.append(((r.flags[0] & km.F_GROUND) != 0)[1:])
        F_.append(np.full(1, face)), M_.append(r.mode[0, 1:]), I_.append(np.zeros(1, bool)), C_.append(np.zeros(1, bool))
        k0 += 1
    pos = np.concatenate(P_)
    tr = Traj(pos, np.concatenate(B_), np.concatenate(G_), np.concatenate(F_), np.concatenate(M_),
              np.concatenate(I_), np.concatenate(C_), hits, contacts, hooks, rolls, k0, starts, missed, variant.name,
              claws, alts)
    tr.segs = played                 # the segments played (the reaction's continuation and the hook variant's in place)
    return tr


def state_at(W: World, tr: Traj, k: int) -> tuple[np.ndarray, np.ndarray] | None:
    """Her kin state (and the envelope's custom fields) at frame k of the trajectory; None inside a Clawline block."""
    if k <= tr.end and tr.blk[min(k, len(tr.blk) - 1)] and k != tr.end:
        return None
    best = None
    for (k0, S0, masks, ev) in tr.rolls:
        if k0 <= k <= k0 + max(len(masks), 0):
            best = (k0, S0, masks, ev)
    if best is None:
        return None
    k0, S0, masks, ev = best
    n = k - k0
    if n == 0:
        S = S0.copy()
    else:
        S = W.roll(S0, masks[:n], ev[:n]).final[:, 0].copy()
    return S, np.array([-1.0, 0, 0, 0, 0, 0, 0])


# ---- the closed-loop evaluation -----------------------------------------------------------------------------------

@dataclass
class Outcome:
    p: float
    branch: object
    tr: Traj
    safe: bool
    why: str
    k_col: int | None
    dev: int | None
    hits: int
    value: float
    term: float
    exit_n: int
    value_open: float = -1.0       # the value if the exit checks had passed (a parent that needs its child's strike to
    #                                be safe - CLAWSTRIKE's Clawline before the down slash - is still expanded)


@dataclass
class Eval:
    plan: Plan
    outcomes: list
    value: float
    p_safe: float
    safe: bool
    hits: float
    ms: float
    n_pred: int
    n_exit: int
    pred: object = None            # the prediction of the most probable outcome group (children continue in it)
    nominal: Outcome | None = None
    value_open: float = -1.0
    open_ok: bool = False          # no collision before the end / a deviation in any outcome (only exits missing)
    finished: bool = True          # the exit checks done (evaluate(exits=False) leaves them to finish())

    def short(self) -> str:
        return (f"{self.plan.origin} v={self.value:.2f} hits={self.hits:.2f} p_safe={self.p_safe:.2f} "
                f"out={len(self.outcomes)} {self.ms:.0f}ms")


def _open(o) -> bool:
    """No collision before the outcome's end / deviation (its exit check may have failed or not run: a parent whose
    child's strike makes it safe is still expanded)."""
    return o.safe or o.why.startswith("exit") or o.why == "unchecked"


def hero_path(tr: Traj, T: int, hits: dict) -> cm.HeroPath:
    n = len(tr.pos)
    idx = np.minimum(np.arange(T + 1), n - 1)
    return cm.HeroPath(tr.pos[idx, 0].copy(), tr.pos[idx, 1].copy(), tr.box[idx].copy(),
                       {iid: dict(h) for iid, h in hits.items()})


def _choice_set(br, before: int) -> frozenset:
    out = []
    for iid, chs in br.choices.items():
        for c in chs:
            if c[2] < before:
                out.append((iid, c[0], str(c[1])))
    return frozenset(out)


def _reveal(br, after: int = 0) -> int | None:
    rv = [c[3] for chs in br.choices.values() for c in chs if c[3] is not None and c[2] >= after]
    return min(rv) if rv else None


INMOVE_PATH = cm.REPO / "knowledge" / "1.0.30000" / "enemies" / "forum" / "clapper_m3_margins.json"
_INMOVE: dict | None = None
MOVE_STARTS = {"Slam Antic": "slam", "Spell Antic": "cast", "Jump Antic": "jump", "Cast Slam Antic": "jcast",
               "Evade Scuttle": "evade"}


def inmove_table() -> dict:
    """The in-move margins (stage M3, ssbot.tools.m3_search margins on the fit set; knowledge clapper_m3_margins.json):
    {"by_move": {move: [(k, m)]}, "by_state": {move: {state: [(k, m)]}}} for a shape of a move already under way, k
    frames after its start was seen."""
    global _INMOVE
    if _INMOVE is None:
        try:
            import json
            _INMOVE = json.loads(INMOVE_PATH.read_text("utf-8"))
        except OSError:
            _INMOVE = {}
    return _INMOVE


def _tab(tab, k: int, default: float) -> float:
    if not tab:
        return default
    for kk, m in tab:
        if k <= kk:
            return float(m)
    return float(tab[-1][1])


def move_spans(br) -> dict:
    """iid -> [(move, the earliest frame its start state is drawn at)] in the branch."""
    c = getattr(br, "_spans", None)
    if c is not None:
        return c
    if brnum.ON[0]:
        out = brnum.move_spans(br)                       # M4b: the same from the record arrays
        br._spans = out
        return out
    out = {}
    for iid, rr in br.recs.items():
        starts = {}
        for r in rr:
            st = r[3]
            if st in MOVE_STARTS and r[4] <= 1:
                starts.setdefault(MOVE_STARTS[st], []).append(r[0] + r[1])
            elif r[0] == 0 and cm.MOVE_OF.get(st) in MOVE_STARTS.values():
                starts.setdefault(cm.MOVE_OF[st], []).append(0)       # under way at the decision: seen now
        out[iid] = [(m_, min(ks)) for m_, ks in starts.items()]
    br._spans = out
    return out


def margin_of(br, s, st, k: int, K) -> float:
    """The margin (u) of a damage shape (in state st) at frame k: the in-move table of its own state from the start
    of its move when that move is under way at k (its start is seen then and she re-plans: 1b.2 'per move and frame
    offset'), else M2's look-ahead table (Know.margin)."""
    mvn = s.mv
    T = inmove_table()
    tab = (T.get("by_state", {}).get(mvn) or {}).get(st) if st is not None else None
    tab = tab or T.get("by_move", {}).get(mvn)
    if tab:
        for (m_, r0) in move_spans(br).get(s.iid, ()):
            if m_ == mvn and r0 <= k:
                return _tab(tab, k - max(r0, 0), K.margin(mvn, k))
    return K.margin(mvn, k)


def rune_end(br) -> int | None:
    """The last lit frame of the branch's big runes (None: none)."""
    v = [h[1][5] for h in br.hazards if h[1][0] == "rune"]
    return max(v) if v else None


def branch_frames(br) -> list:
    """Per frame 0 .. T the branch's shapes with the state of the record that drew them: [(Shape, state)] (as
    clapper.build_frames, the hazards with state None). Beyond T, up to the last hazard's lit end (a big rune lit
    after the prediction's horizon, its landing inside it): the hazards and the frame T's other shapes held (the
    caster stands through its burst)."""
    c = getattr(br, "_sframes", None)
    if c is not None:
        return c
    T = br.T
    T_h = max([T] + [int(h[1][5]) for h in br.hazards])
    frames = [[] for _ in range(T_h + 1)]
    seen = [set() for _ in range(T_h + 1)]
    for iid, rr in br.recs.items():
        for r in rr:
            k, a, b = r[0], r[1], r[2]
            lo, hi = max(k + a, 0), min(k + b, T)
            if lo > hi:
                continue
            key = (iid, r[3], r[4], round(r[5], 2), round(r[6], 2), r[7], r[8])
            sh = None
            for kk in range(lo, hi + 1):
                if key in seen[kk]:
                    continue
                if sh is None:
                    sh = [(x, r[3]) for x in cm.rec_shapes(r, iid, br.K)]
                seen[kk].add(key)
                frames[kk].extend(sh)
    for kk in range(T + 1, T_h + 1):
        frames[kk] = list(frames[T])
    for iid, hz in br.hazards:
        kind, x, y, rad, t0, t1 = hz
        s = cm.Shape(cm.DAMAGE, iid, kind, circle=(x, y, rad), mv=kind)
        key = (iid, kind, round(x, 2), round(y, 2))
        for kk in range(max(t0, 0), min(t1, T_h) + 1):
            if key not in seen[kk]:
                seen[kk].add(key)
                frames[kk].append((s, None))
    br._sframes = frames
    return frames


_GROWN: dict = {}
MARGIN_SCALE = [1.0]               # set by the Searcher from Cfg.margin_scale (the branch caches are per Searcher run)


def grow_shape(x, m: float):
    """Shape.grown with the polygon's Minkowski hull cached by its shape relative to its first vertex (the hammer
    polygons are a few templates translated)."""
    if m <= 0:
        return x
    if x.poly is None:
        return x.grown(m)
    p0 = x.poly[0]
    rel = x.poly - p0
    key = (tuple(np.round(rel, 4).ravel()), m)
    g = _GROWN.get(key)
    if g is None:
        g = x.grown(m).poly - p0
        if len(_GROWN) < 20000:
            _GROWN[key] = g
    return cm.Shape(x.kinds, x.iid, x.name, poly=g + p0, mv=x.mv)


def bdamage(br, k: int, margins: bool, skip: tuple = ()) -> list:
    """The branch's damage shapes at frame k grown by their margins (margin_of), cached on the branch. skip: the
    Clappers whose BODY does not hurt then (a hooked Clawline's window, strike.hook_body_off; M4a)."""
    c = getattr(br, "_dmg", None)
    if c is None:
        c = {}
        br._dmg = c
    key = (k, margins, skip)
    v = c.get(key)
    if v is None:
        fr = branch_frames(br)
        v = [(x, st) for (x, st) in (fr[k] if 0 <= k < len(fr) else []) if x.kinds & cm.DAMAGE
             and not (skip and x.iid in skip and x.name == "body")]
        if margins:
            v = [grow_shape(x, MARGIN_SCALE[0] * margin_of(br, x, st, k, br.K)) for (x, st) in v]
        else:
            v = [x for (x, st) in v]
        c[key] = v
    return v


def shapes_hit(shapes, hb) -> bool:
    for s in shapes:
        x0, y0, x1, y1 = s.bbox()
        if x0 >= hb[2] or x1 <= hb[0] or y0 >= hb[3] or y1 <= hb[1]:
            continue
        if s.hits_box(hb):
            return True
    return False


PROBE_EPS = 1e-4                   # the exit probes' boxes grown by this (closed): a probe this near a box is not trusted
PROBE_VERIFY = [os.environ.get("SSBOT_M4B_PROBE_VERIFY", "") == "1"]   # also run the pass after a probe and count
PROBE_STATS = {"checked": 0, "violations": 0}                         # a probe exit the pass did not keep


def _probe_masks(S: np.ndarray, H: int) -> np.ndarray:
    """The exit probes (within one event): her held jump / dash kept (going on is free), with no direction, left,
    right; when jump is not held, a jump pressed and held (one event) with no direction, left, right; when dash is not
    held, a dash pressed and held to the left / right."""
    base = int(S[km.PREV]) & (km.B_JUMP | km.B_DASH)
    ms_ = [base, base | km.B_LEFT, base | km.B_RIGHT]
    if not base & km.B_JUMP:
        j = base | km.B_JUMP
        ms_ += [j, j | km.B_LEFT, j | km.B_RIGHT]
    if not base & km.B_DASH:
        d = base | km.B_DASH                          # a dash pressed and held, left / right (one event)
        ms_ += [d | km.B_LEFT, d | km.B_RIGHT]
    return np.repeat(np.array(ms_, np.int64)[:, None], H, axis=1)


SLAB = 0.25                        # the slab height a polygon / circle is cut into for the envelope's danger boxes


_SLABS: dict = {}


def poly_slabs(poly: np.ndarray, hw: float, hh: float, off: float, dy: float = SLAB) -> list:
    """A convex polygon grown by her hurtbox (the Minkowski sum with [-hw, hw] x [-hh, hh], shifted to her box
    centre by -off) as horizontal slabs of height dy: per slab the x range of the grown polygon within it (exact per
    slab's y range, conservative) - instead of one bounding box (a hammer's box reaches 10 u up). Cached by the
    polygon's shape relative to its first vertex (the hammers / circles are a few templates translated)."""
    p0 = poly[0]
    key = (tuple(np.round(poly - p0, 4).ravel()), hw, hh, off, dy)
    rel = _SLABS.get(key)
    if rel is None:
        rel = _poly_slabs(poly - p0, hw, hh, off, dy)
        if len(_SLABS) < 50000:
            _SLABS[key] = rel
    return [(a + p0[0], b + p0[1], c + p0[0], d + p0[1]) for (a, b, c, d) in rel]


def _poly_slabs(poly: np.ndarray, hw: float, hh: float, off: float, dy: float = SLAB) -> list:
    P = cm.convex_hull(np.concatenate([poly + (sx, sy) for sx in (-hw, hw) for sy in (-hh - off, hh - off)]))
    y_lo, y_hi = float(P[:, 1].min()), float(P[:, 1].max())
    n = max(1, int(np.ceil((y_hi - y_lo) / dy)))
    out = []
    m = len(P)
    for i in range(n):
        a, b = y_lo + i * dy, min(y_lo + (i + 1) * dy, y_hi)
        xs = [px for (px, py) in P if a <= py <= b]
        for j in range(m):
            (x0, y0), (x1, y1) = P[j], P[(j + 1) % m]
            if y0 == y1:
                continue
            for yc in (a, b):
                if min(y0, y1) <= yc <= max(y0, y1):
                    xs.append(x0 + (x1 - x0) * (yc - y0) / (y1 - y0))
        if xs:
            out.append((min(xs), a, max(xs), b))
    return out


def branch_danger(br, k: int, margins: bool, skip: tuple = ()) -> np.ndarray:
    """[n, 4] her box-centre configuration-space boxes of the branch's damage at frame k (a box grown by her
    hurtbox; a polygon / circle as slabs), cached on the branch. skip: as bdamage. (M4b: from the branch's Geo - the
    same boxes, the body boxes first.)"""
    c = getattr(br, "_dz", None)
    if c is None:
        c = {}
        br._dz = c
    key = (k, margins, skip)
    v = c.get(key)
    if v is not None:
        return v
    hw, hh = HB[0], HB[1]
    if brnum.ON[0]:
        g = geo(br, margins)
        if 0 <= k < len(g.off) - 1:
            a, b = int(g.off[k]), int(g.off[k + 1])
            B = g.BX[a:b]
            if skip:
                B = B[~np.isin(g.IIDB[a:b], skip)]
            parts = [np.stack([B[:, 0] - hw, B[:, 1] - hh - HB_OFF, B[:, 2] + hw, B[:, 3] + hh - HB_OFF], axis=1)]
            out = []
            for s in g.rare_grown(br, k, margins):
                if s.box is not None:
                    x0, y0, x1, y1 = s.box
                    out.append((x0 - hw, y0 - hh - HB_OFF, x1 + hw, y1 + hh - HB_OFF))
                else:
                    out += poly_slabs(s.polygon(16), hw, hh, HB_OFF)
            for c_ in range(int(g.coff[k]), int(g.coff[k + 1])):          # the hazards' circles (grown)
                cx, cy, r = g.CO[c_]
                out += poly_slabs(cm.Shape(cm.DAMAGE, 0, "", circle=(float(cx), float(cy), float(r))).polygon(16),
                                  hw, hh, HB_OFF)
            if out:
                parts.append(np.asarray(out, float).reshape(-1, 4))
            v = np.concatenate(parts) if len(parts) > 1 else parts[0]
        else:
            v = np.zeros((0, 4))
        c[key] = v
        return v
    out = []
    for s in bdamage(br, k, margins, skip):
        if s.box is not None:
            x0, y0, x1, y1 = s.box
            out.append((x0 - hw, y0 - hh - HB_OFF, x1 + hw, y1 + hh - HB_OFF))
        else:
            out += poly_slabs(s.polygon(16), hw, hh, HB_OFF)
    v = np.asarray(out, float).reshape(-1, 4)
    c[key] = v
    return v


# ---- M4b: a branch's damage per frame as arrays (Geo) ---------------------------------------------------------------

_TABV: dict = {}


def _tab_vec(tab, ks: np.ndarray) -> np.ndarray:
    """_tab / Know.margin's lookup for an array of k: the first row whose kk >= k (the table's last past its end)."""
    v = _TABV.get(id(tab))
    if v is None or v[0] is not tab:
        v = (tab, np.array([float(t[0]) for t in tab]), np.array([float(t[1]) for t in tab]))
        _TABV[id(tab)] = v
    _, kk, mm = v
    i = np.searchsorted(kk, ks, side="left")
    return mm[np.minimum(i, len(mm) - 1)]


def _kmargin_vec(K, mv: str, ks: np.ndarray) -> np.ndarray:
    """Know.margin(mv, k) for an array of k."""
    mt = K.d.get("margins") or {}
    tab = mt.get("by_move", {}).get(mv)
    if not tab:
        return np.full(len(ks), float(mt.get("default", 0.0)))
    return _tab_vec(tab, ks)


def _margins_vec(br, iid: int, st, ks: np.ndarray) -> np.ndarray:
    """margin_of for the body shapes of one Clapper in one state at the frames ks."""
    mvn = cm.MOVE_OF.get(st, "idle")
    T_ = inmove_table()
    tab = (T_.get("by_state", {}).get(mvn) or {}).get(st) if st is not None else None
    tab = tab or T_.get("by_move", {}).get(mvn)
    base = _kmargin_vec(br.K, mvn, ks)
    if tab:
        for (m_, r0) in move_spans(br).get(iid, ()):
            if m_ == mvn:
                use = r0 <= ks
                if use.any():
                    base = base.copy()
                    base[use] = _tab_vec(tab, ks[use] - max(r0, 0))
                break
    return base


class Geo:
    """One branch's damage per frame (branch_frames + bdamage as arrays): the body boxes of frame k are rows
    off[k] .. off[k + 1] - 1 of BX (grown by their margins x MARGIN_SCALE; IIDB their Clapper); the rare shapes (the
    hammers, the bombs, the big rune) as Shape objects per frame (rare), grown on use as bdamage grows them."""
    __slots__ = ("off", "BX", "IIDB", "coff", "CO", "rare", "rare_k", "_grown")

    def rare_grown(self, br, k: int, margins: bool) -> list:
        g = self._grown.get(k)
        if g is None:
            v = self.rare.get(k, ())
            if margins:
                g = [grow_shape(x, MARGIN_SCALE[0] * margin_of(br, x, st, k, br.K)) for (x, st) in v]
            else:
                g = [x for (x, st) in v]
            self._grown[k] = g
        return g


_MTABS: dict = {}


def _margin_tabs(tb, K) -> dict:
    """The margin tables as flat arrays for brnum.geo_boxes (per state table): each state's move (MOVE_OF, else
    idle), its in-move table (by state, else by move; -1: none), Know.margin's table per move (-1: the default)."""
    c = _MTABS.get(id(tb))
    if c is not None and c["tb"] is tb:
        return c
    mt = K.d.get("margins") or {}
    T_ = inmove_table()
    mvs = sorted(set(cm.MOVE_OF.values()) | {"idle"} | set(mt.get("by_move", {})) | set(T_.get("by_move", {})))
    mvi = {m: i for i, m in enumerate(mvs)}
    tabs, ids = [], {}

    def tid(t):
        if not t:
            return -1
        if id(t) not in ids:
            ids[id(t)] = len(tabs)
            tabs.append(t)
        return ids[id(t)]
    MVOF = np.array([mvi[cm.MOVE_OF.get(nm, "idle")] for nm in tb.names], np.int64)
    TABST = np.array([tid((T_.get("by_state", {}).get(cm.MOVE_OF.get(nm, "idle")) or {}).get(nm) or
                          T_.get("by_move", {}).get(cm.MOVE_OF.get(nm, "idle"))) for nm in tb.names], np.int64)
    BASE = np.array([tid(mt.get("by_move", {}).get(m)) for m in mvs], np.int64)
    TK = np.array([float(r[0]) for t in tabs for r in t] + [0.0])
    TM = np.array([float(r[1]) for t in tabs for r in t] + [0.0])
    TOFF = np.zeros(len(tabs) + 1, np.int64)
    TOFF[1:] = np.cumsum([len(t) for t in tabs])
    c = {"tb": tb, "mv": mvs, "mvi": mvi, "MVOF": MVOF, "TABST": TABST, "BASE": BASE, "TK": TK, "TM": TM,
         "TOFF": TOFF, "default": float(mt.get("default", 0.0))}
    _MTABS[id(tb)] = c
    return c


def geo(br, margins: bool) -> Geo:
    """The branch's Geo (cached per margins and MARGIN_SCALE): branch_frames' rule (brnum.emit: a record drawn at
    k + a .. k + b unless an earlier record with the same rounded key drew that frame; frames past T hold frame T's;
    the hazards' circles while lit) and bdamage's margins (margin_of, vectorized per Clapper and state)."""
    c = br.__dict__.get("_geo")
    if c is None:
        c = {}
        br.__dict__["_geo"] = c
    key = (margins, MARGIN_SCALE[0])
    g = c.get(key)
    if g is not None:
        return g
    arr, tb = brnum.barr(br)
    F = brnum.flags(tb, br.K)
    T = br.T
    T_h = max([T] + [int(h[1][5]) for h in br.hazards])
    il = list(arr.keys())
    A = np.ascontiguousarray(np.concatenate([arr[i] for i in il])) if il else np.zeros((0, 9))
    IIDc = np.concatenate([np.full(len(arr[i]), i, np.int64) for i in il]) if il else np.zeros(0, np.int64)
    IQ = np.concatenate([np.full(len(arr[i]), q, np.int64) for q, i in enumerate(il)]) if il else IIDc
    MT = _margin_tabs(tb, br.K)
    R0 = np.full((max(len(il), 1), len(MT["mv"])), np.nan)
    if margins:
        sp_ = move_spans(br)
        for q, i in enumerate(il):
            for (m_, r0) in sp_.get(i, ()):
                R0[q, MT["mvi"][m_]] = r0
    off, BX, IIDB, EK, EI, body = brnum.geo_boxes(
        A, IIDc, IQ, T, T_h, F.nobody, F.BSPAN, tb.BOXL, MT["MVOF"], MT["TABST"], R0, MT["BASE"], MT["default"],
        MT["TK"], MT["TM"], MT["TOFF"], float(MARGIN_SCALE[0]), bool(margins))
    rare: dict = {}
    hm = np.flatnonzero(body & (A[EI, 8] != 0)) if len(EI) else np.zeros(0, np.int64)
    for q in hm:
        kk, i = int(EK[q]), int(EI[q])
        r = A[i]
        iid = int(IIDc[i])
        tup = cj._rec_tuple(r, tb.names)
        for s in cm.rec_shapes(tup, iid, br.K)[1:]:
            rare.setdefault(kk, []).append((s, tup[3]))
    rare_k = np.array(sorted(rare), np.int64)        # the frames with hammers (checked in Python)
    # the hazards' circles while lit (branch_frames' rule: a hazard key drawn once per frame, the first in order)
    CO = np.zeros((0, 3))
    coff = np.zeros(T_h + 2, np.int64)
    hz = br.hazards
    if hz:
        keys: dict = {}
        kid, lo_, n_, hv, kinds = [], [], [], [], []
        for iid, h in hz:
            kind, hx, hy, rad, t0, t1 = h
            kid.append(keys.setdefault((iid, kind, round(hx, 2), round(hy, 2)), len(keys)))
            lo, hi = max(t0, 0), min(t1, T_h)
            lo_.append(lo)
            n_.append(max(hi - lo + 1, 0))
            hv.append((hx, hy, rad))
            kinds.append(kind)
        n_ = np.array(n_, np.int64)
        if n_.sum():
            hidx = np.repeat(np.arange(len(hz)), n_)
            kk = np.repeat(np.array(lo_, np.int64), n_) + (np.arange(int(n_.sum())) - np.repeat(np.cumsum(n_) - n_, n_))
            code = np.array(kid, np.int64)[hidx] * (T_h + 1) + kk
            _, first = np.unique(code, return_index=True)
            sel = np.sort(first)
            hidx, kk = hidx[sel], kk[sel]
            o = np.argsort(kk, kind="stable")
            hidx, kk = hidx[o], kk[o]
            HV = np.array(hv, float)
            CO = HV[hidx].copy()
            if margins:
                ka = np.array(kinds)
                for kind in sorted(set(kinds)):
                    q = ka[hidx] == kind
                    m = MARGIN_SCALE[0] * _kmargin_vec(br.K, kind, kk[q].astype(float))
                    CO[q, 2] = np.where(m > 0, CO[q, 2] + m, CO[q, 2])
            coff[1:] = np.cumsum(np.bincount(kk, minlength=T_h + 1)[:T_h + 1])
    g = Geo()
    g.off, g.BX, g.IIDB = off, np.ascontiguousarray(BX), np.ascontiguousarray(IIDB)
    g.coff, g.CO = coff, CO
    g.rare, g.rare_k = rare, rare_k
    g._grown = {}
    c[key] = g
    return g


_HW, _HH, _HDY = cm.HURTBOX


def first_collision(br, tr: "Traj", k0: int, k1: int, margins: bool) -> int | None:
    """The first frame k0 .. k1 (her i-frames skipped) where her hurtbox leaves the walls or meets the branch's damage
    (the hooked Clapper's body skipped in its window: hook_body_off) - the loops of _outcome / quick / tick_check with
    bdamage + shapes_hit, on the Geo's arrays (brnum.first_hit) and the rare shapes."""
    if k1 < k0:
        return None
    g = geo(br, margins)
    hk = [(h.iid, h.P + sk.HOOK_BODY_OFF[0], h.ctrl + sk.HOOK_BODY_OFF[1]) for h in tr.hooks if h.ok]
    if hk:
        hki = np.array([h[0] for h in hk], np.int64)
        hlo = np.array([h[1] for h in hk], np.int64)
        hhi = np.array([h[2] for h in hk], np.int64)
    else:
        hki = hlo = hhi = _EMPTY_I
    pos = tr.pos
    kb, _ = brnum.first_hit(np.ascontiguousarray(pos[:, 0]), np.ascontiguousarray(pos[:, 1]), tr.ifr, k0, k1, g.off,
                            g.BX, g.IIDB, hki, hlo, hhi, _HW, _HH, _HDY, WALL_L, WALL_R, g.coff, g.CO)
    top = kb - 1 if kb >= 0 else k1
    if len(g.rare_k):
        for k in g.rare_k[(g.rare_k >= k0) & (g.rare_k <= top)]:
            k = int(k)
            if tr.ifr[k]:
                continue
            if shapes_hit(g.rare_grown(br, k, margins), cm.hurtbox(*pos[k])):
                return k
    return kb if kb >= 0 else None


_EMPTY_I = np.zeros(0, np.int64)


def timing_views(br) -> list:
    """The branch's TIMING VARIANTS as separate outcomes: every record drawn at its earliest (k + a) / latest (k + b)
    offset - two exact timelines instead of their union (M2 draws the union). Each view carries t_reveal, the first
    frame where the two timelines' states differ: she sees which one it is then (a state's entry) and re-plans - the
    reveal rule for timings (SP13 checked both slam timelines, antic 48 / 49). One view (the branch) when no record
    spreads. Cached on the branch."""
    c = getattr(br, "_views", None)
    if c is not None:
        return c
    if brnum.ON[0]:
        vs = brnum.views(br, cj.JBranch)                 # M4b: the same views from the record arrays
        if vs is None:
            br.t_reveal = None
            br.tview = ""
            br._views = [br]
        else:
            br._views = vs
        return br._views
    spread = any(r[1] != r[2] for rr in br.recs.values() for r in rr)
    if not spread:
        br.t_reveal = None
        br.tview = ""
        br._views = [br]
        return br._views
    views = []
    states = []
    for mode in (1, 2):
        recs = {}
        st_at = {}
        for iid, rr in br.recs.items():
            out = []
            for r in rr:
                off = r[mode]
                out.append((r[0] + off, 0, 0) + tuple(r[3:]))
                st_at[(iid, r[0] + off)] = r[3]
            recs[iid] = out
        v = cm.Branch(br.p * 0.5, br.choices, br.reveal, recs, br.hazards, br.K, br.T, br.n_merged)
        v.tview = "early" if mode == 1 else "late"
        v._base = br                                   # M4c: the branch it was drawn from (its records' spreads)
        views.append(v)
        states.append(st_at)
    tr_ = None
    for k in range(1, br.T + 1):
        for iid in br.recs:
            if states[0].get((iid, k)) != states[1].get((iid, k)):
                tr_ = k
                break
        if tr_ is not None:
            break
    for v in views:
        v.t_reveal = tr_
    br._views = views
    return views


_PK_NONE: dict = {}


def _packed_danger(br, k0: int, H: int, ifr_until: int, margins: bool) -> tuple:
    """The exit check's danger: per frame k0 .. k0 + H the branch's boxes (none up to ifr_until: the pogo's
    i-frames) and the walls - the list, and packed (boxes, frame offsets) - cached on the branch (M4b: every outcome
    of a view that ends at the same frame shares it)."""
    c = br.__dict__.setdefault("_pk", {}) if br is not None else _PK_NONE
    key = (k0, H, ifr_until, margins)
    v = c.get(key)
    if v is None:
        dz = []
        for t in range(H + 1):
            k = k0 + t
            b = branch_danger(br, k, margins) if (br is not None and k > ifr_until) else np.zeros((0, 4))
            dz.append(np.concatenate([b, WALL_BOXES]))
        off = np.zeros(H + 2, np.int64)
        off[1:] = np.cumsum([len(d) for d in dz])
        v = (dz, np.concatenate(dz), off)
        if br is not None or len(c) < 4096:
            c[key] = v
    return v


class Evaluator:
    def __init__(self, W: World, cfg: Cfg):
        self.W, self.cfg = W, cfg
        self.n_pred = 0
        self.n_exit = 0
        self.ms_pred = 0.0
        self.ms_exit = 0.0
        self.units = 0                 # work units (closed-loop evaluations + exit checks): the virtual clock's ticks
        self._simm: dict = {}          # the trajectory memo (sim)
        self.n_sim = 0
        self.n_sim_hit = 0
        self.n_probe = 0               # exit checks settled by a probe (exit_ok)
        self._exm_none: dict = {}      # exit_ok's memo without a branch

    def reset(self) -> None:
        """Drop the per-decision memos (a new situation)."""
        self._simm = {}

    def sim(self, sit: Situation, plan: Plan, var: sk.HookVariant, face0: int, b=None, T: int | None = None,
            lag: int = 2) -> Traj:
        """simulate() of the plan from the situation's state in one outcome (b: its branch, T: its prediction's
        horizon; None: no Clapper - the do-nothing path's trajectory), MEMOIZED EXACTLY (M4b): a trajectory is a
        function of the plan, the start and the branch inputs it read (simulate's rec: the box rows its strikes
        looked at, the reaction keys); a branch whose reads are equal gets the same trajectory. A plan without a
        strike reads nothing: one trajectory for every outcome."""
        self.n_sim += 1
        key = (id(plan), var.name, lag, face0, id(sit.S), sit.alpha_c, b is None)
        ent = self._simm.get(key)
        if ent is None:
            ent = self._simm[key] = (plan, sit.S, [])
        for reads, tr in ent[2]:
            if b is None or self._reads_ok(reads, b, T, lag):
                self.n_sim_hit += 1
                return tr
        if b is None:
            tr = simulate(self.W, plan, lambda iid: None, face0, sit.S, var, sit.alpha_c)
            ent[2].append(((), tr))
            return tr
        rec: list = []
        tr = simulate(self.W, plan, lambda iid: sk.robust_boxes(b, iid, T), face0, sit.S, var, sit.alpha_c, br=b,
                      lag=lag, rec=rec)
        ent[2].append((tuple(rec), tr))
        if len(ent[2]) > 24:
            ent[2].pop(0)
        return tr

    @staticmethod
    def _reads_ok(reads: tuple, b, T, lag: int) -> bool:
        for r in reads:
            if r[0] == "rows":
                if _rows_sig(sk.robust_boxes(b, r[1], T), r[2], r[3]) != r[4]:
                    return False
            elif reaction_key(b, r[1], lag) != r[2]:
                return False
        return True

    def _predict_fn(self):
        """clapper.predict, or its compiled port (Cfg.jit_predict; the same Prediction: clapper_jit)."""
        return cj.predict if self.cfg.jit_predict else cm.predict

    def predict(self, sit: Situation, path: cm.HeroPath, T: int):
        t0 = time.perf_counter()
        P = self._predict_fn()(sit.obs, sit.mems, path, self.W.K, T=T, hazards=sit.hazards)
        self.n_pred += 1
        self.ms_pred += (time.perf_counter() - t0) * 1e3
        return P

    def tick_check(self, sit: Situation, plan: Plan) -> tuple:
        """THE FULL CHECK of a committed plan from a new observation (M4b): the closed-loop evaluation without its
        exit checks - the prediction over the evaluation's horizon, re-predicted at the plan's own hits that change a
        Clapper (a hook's reaction: the contingent plan's continuation), every timing view and hook variant - and the
        commit rule (a collision before the branch's reveal + lag, a Clawline block moving it to control) -> (ok, the
        first failing frame or None, ms). M3's version (tick_check_m3) predicted with none of her hits over the plan's
        length only: the hooked Clapper never reacted (its Idle future instead) and the timing groups were not the
        evaluation's, so plans the evaluation called safe failed it (M3 open item 8: 4 of v4's chosen plans - the far
        hooks' contingent plans 8 / 14, the locked hook 185; and situation 97, an unsafe fallback). The per-frame
        check on the bot's thread is TickCheck (the committed evaluation's outcomes against the observations)."""
        t0 = time.perf_counter()
        e = self.evaluate(sit, plan, exits=False)
        bad = None
        for o in e.outcomes:
            if o.why.startswith("hit@"):
                k = int(o.why[4:])
                bad = k if bad is None else min(bad, k)
        return bad is None, bad, (time.perf_counter() - t0) * 1e3

    def tick_check_m3(self, sit: Situation, plan: Plan) -> tuple:
        """M3's PER-TICK CHECK of a committed plan (what runs every frame between the background searches): one
        prediction under the plan's path, the plan simulated in every branch (both timing views, the first hook
        variant, its reaction's continuation) and her hurtbox checked against the branch's damage (margins) up to
        the branch's reveal + lag (the committed part; after it she re-plans) - (ok, the first failing frame or None,
        ms). No re-prediction at the plan's own hits and no exit check (those are the background search's)."""
        t0 = time.perf_counter()
        W, cfg = self.W, self.cfg
        face0 = int(sit.S[km.FACE]) if sit.S[km.FACE] != 0 else 1
        tr0 = self.sim(sit, plan, sk.HOOK_VARIANTS[0], face0)
        T = tr0.end + 2
        P = self._predict_fn()(sit.obs, sit.mems, hero_path(tr0, T, {}), W.K, T=T, hazards=sit.hazards)
        bad = None
        for b0 in P.branches:
            for b in timing_views(b0):
                tr = self.sim(sit, plan, sk.HOOK_VARIANTS[0], face0, b, P.T, cfg.lag)
                rv = _reveal(b, 1)
                tv = getattr(b, "t_reveal", None)
                rv = tv if rv is None else (rv if tv is None else min(rv, tv))
                kmax = min(tr.end, P.T, (rv + cfg.lag) if rv is not None else tr.end)
                if brnum.ON[0]:
                    k = first_collision(b, tr, 1, kmax, cfg.margins)
                    if k is not None:
                        bad = k if bad is None else min(bad, k)
                    continue
                for k in range(1, kmax + 1):
                    if tr.ifr[k]:
                        continue
                    hb = cm.hurtbox(*tr.pos[k])
                    if hb[0] < WALL_L or hb[2] > WALL_R or \
                            shapes_hit(bdamage(b, k, cfg.margins, sk.hook_body_off(tr.hooks, k)), hb):
                        bad = k if bad is None else min(bad, k)
                        break
        return bad is None, bad, (time.perf_counter() - t0) * 1e3

    def quick(self, sit: Situation, plan: Plan, pred, k_from: int, n_branch: int = 3) -> str:
        """A cheap pre-screen before the closed-loop evaluation: the plan simulated in the given prediction's most
        probable branches (both timing views, the first hook variant; no re-prediction) - '' when it lands a strike
        after frame k_from with no collision before its end in all of them, else the reason."""
        cfg = self.cfg
        face0 = int(sit.S[km.FACE]) if sit.S[km.FACE] != 0 else 1
        brs = sorted(pred.branches, key=lambda b: -b.p)[:n_branch]
        for b0 in brs:
            for b in timing_views(b0):
                tr = self.sim(sit, plan, sk.HOOK_VARIANTS[0], face0, b, pred.T, cfg.lag)
                if not any(kc > k_from for (kc, _, _) in tr.contacts):
                    return "miss"
                kmax = min(tr.end, pred.T)
                if brnum.ON[0]:
                    ks_ = [first_collision(b, tr, k_from + 1, kmax, cfg.margins)]
                    ks_ = [k for k in ks_ if k is not None]
                else:
                    ks_ = []
                    for k in range(k_from + 1, kmax + 1):
                        if tr.ifr[k]:
                            continue
                        hb = cm.hurtbox(*tr.pos[k])
                        if hb[0] < WALL_L or hb[2] > WALL_R or \
                                shapes_hit(bdamage(b, k, cfg.margins, sk.hook_body_off(tr.hooks, k)), hb):
                            ks_.append(k)
                            break
                for k in ks_:
                    rv = _reveal(b, 1)
                    tv = getattr(b, "t_reveal", None)
                    rv = tv if rv is None else (rv if tv is None else min(rv, tv))
                    if rv is None or k < rv + cfg.lag:
                        return f"hit@{k}"
        return ""

    def _hit_matters(self, sit: Situation, b, fixed: dict, pre: list, k: int, iid: int, h) -> bool:
        st = sk.state_at(b, iid, k - 1)
        if st is None:
            return True
        s_, j = st[0], st[1]
        if s_ in ("Idle", "Walk"):
            return True
        nxt = cm.NEXT.get(s_)
        if nxt == "Idle":
            d = b.K.durations(s_)
            if d is None or j >= d[0] - 2:
                return True
        hp = next((o.hp for o in sit.obs if o.iid == iid), 10 ** 6)
        dmg = sum(v[1] for (ii, kk), v in fixed.items() if ii == iid) +             sum(hh[1] for (kk, ii, hh) in pre if ii == iid) + h[1]
        return hp - dmg <= 0

    def exit_ok(self, S: np.ndarray, cu: np.ndarray, k0: int, br, ifr_until: int = -1, H: int | None = None) -> int:
        """The coarse exit check: an envelope pass from S at frame k0 in the branch's danger (+ the walls) for
        H (cfg.exit_h) frames; returns the clusters alive at the end (0: no exit)."""
        H = self.cfg.exit_h if H is None else H
        self.n_exit += 1
        # M4b: the same check (her state, the branch, the frames) answered once - e.g. both hook variants of a plan
        # without a hook, or two timing views' outcomes ending in the same state on the same danger
        memo = br.__dict__.setdefault("_exm", {}) if br is not None else self._exm_none
        mkey = (np.asarray(S, np.float64).tobytes(), None if cu is None else np.asarray(cu, np.float64).tobytes(),
                k0, H, ifr_until, self.cfg.margins)
        v = memo.get(mkey)
        if v is None:
            v = self._exit_compute(S, cu, k0, br, ifr_until, H)
            if br is not None or len(memo) < 4096:
                memo[mkey] = v
        return v

    def _exit_compute(self, S: np.ndarray, cu, k0: int, br, ifr_until: int, H: int) -> int:
        dz, boxes, off = _packed_danger(br, k0, H, ifr_until, self.cfg.margins)
        t0 = time.perf_counter()
        if self.cfg.exit_probe:
            # M4b: a few concrete key sequences first - one that touches no danger box is an exit (the pass, which
            # contains it, would keep a cluster: the same verdict for a fraction of the cost)
            cu_ = np.array([-1.0, 0, 0, 0, 0, 0, 0]) if cu is None else np.asarray(cu, np.float64)
            i = ej.probe_exit(np.asarray(S, np.float64), cu_, _probe_masks(S, H), self.W.E.udt, self.W.E.P,
                              self.W.TT, boxes, off, PROBE_EPS)
            if i >= 0:
                self.n_probe += 1
                if not PROBE_VERIFY[0]:
                    self.ms_exit += (time.perf_counter() - t0) * 1e3
                    return 1
                st = self.W.E.start_state(S, cu=cu)
                fw = self.W.E.forward(st, H, danger=dz, terrain=self.W.TT, max_events=self.cfg.exit_events,
                                      claw=False)
                PROBE_STATS["checked"] += 1
                if fw.count(H) <= 0:
                    PROBE_STATS["violations"] += 1
                self.ms_exit += (time.perf_counter() - t0) * 1e3
                return fw.count(H)
        st = self.W.E.start_state(S, cu=cu)
        fw = self.W.E.forward(st, H, danger=dz, terrain=self.W.TT, max_events=self.cfg.exit_events, claw=False)
        self.ms_exit += (time.perf_counter() - t0) * 1e3
        return fw.count(H)

    def _tag_ok(self, b, tag: tuple, fixed: dict) -> bool:
        """The branch belongs to the reactions of tag (checked for a split only once its hook's hit is in the
        group's hits: before it the branches carry no reaction)."""
        for (_, Ps, rk) in tag:
            if any(v[0] == "claw" and Ps < kk <= Ps + 12 for (ii, kk), v in fixed.items()):
                if reaction_key(b, Ps, self.cfg.lag) != rk:
                    return False
        return True

    def evaluate(self, sit: Situation, plan: Plan, exits: bool = True, tag: tuple = (), start=None,
                 until=None) -> Eval | None:
        """The closed-loop evaluation (module docstring, step 3). tag / start: a CONDITIONAL evaluation inside the
        reactions of tag (a contingent plan's continuation searched per reaction): the cascade starts from the node's
        group (start = its hits, the choice sets before its last hit, a branch of it for her path) and keeps only the
        branches of those reactions - its value is the plan's given those reactions, not the plan's (only _combine's
        joined plan is evaluated whole). until (M4b's hard cap): checked before each re-prediction of the cascade -
        true: the evaluation is abandoned and None returned (a joined two-Clapper plan's cascade ran 200 predictions,
        40 s past a 2 s cap)."""
        t0 = time.perf_counter()
        self.units += 1
        W, cfg = self.W, self.cfg
        n0p, n0e = self.n_pred, self.n_exit
        face0 = int(sit.S[km.FACE]) if sit.S[km.FACE] != 0 else 1
        T = cfg.t_pred
        variants = sk.HOOK_VARIANTS if any(s.claw is not None for s in plan.segs) else sk.HOOK_VARIANTS[:1]
        if start is None:
            tr0 = self.sim(sit, plan, variants[0], face0)
            T = max(T, tr0.end + max(cfg.exit_h, cfg.t_pred) + 2)
            P0 = self.predict(sit, hero_path(tr0, T, {}), T)
            groups = [(P0, 1.0, None, {}, -1)]
        else:
            fixed0, cons0, lh0, rb = start
            tr0 = self.sim(sit, plan, variants[0], face0, rb, rb.T, cfg.lag)
            T = max(T, tr0.end + max(cfg.exit_h, cfg.t_pred) + 2)
            hits0: dict = {}
            for (ii, kk), v in fixed0.items():
                hits0.setdefault(ii, {})[kk] = v
            P0 = self.predict(sit, hero_path(tr0, T, hits0), T)
            groups = [(P0, 1.0, cons0, dict(fixed0), lh0)]
        results = []
        best_group = (0.0, P0)
        has_alt = any(sg.out_alt for sg in plan.segs)
        for _level in range(5):
            new_groups = []
            work = [g + (None, has_alt) for g in groups]
            while work:
                (P, w, cons, fixed, last_hit, kf, redo_ok) = work.pop(0)
                brs = [b for b in P.branches if cons is None or _choice_set(b, last_hit) in cons]
                if tag:
                    brs = [b for b in brs if self._tag_ok(b, tag, fixed)]
                    if not brs:
                        continue
                if kf is not None:
                    brs = [b for b in brs if all(reaction_key(b, Ps, cfg.lag) == rk for (Ps, rk) in kf)]
                    if not brs:
                        continue
                if not brs:
                    brs = list(P.branches)
                ptot = sum(b.p for b in brs) or 1.0
                buckets: dict = {}
                redo: dict = {}
                p_akey = getattr(P, "_akey", None)
                for b0 in brs:
                    vws = timing_views(b0)
                    for b, var in [(b_, v_) for b_ in vws for v_ in variants]:
                        tr = self.sim(sit, plan, var, face0, b, P.T, cfg.lag)
                        wb = w * b0.p / ptot / len(variants) / len(vws)
                        akey = tuple(rk for (_, _, rk) in tr.alts)
                        if redo_ok and p_akey is not None and akey != p_akey:
                            # a contingent plan: this reaction plays another continuation than the path the group
                            # was predicted with - its future re-predicted under its own path (below)
                            redo.setdefault(akey, []).append((wb, tr))
                            continue
                        new = sorted((k, iid, h) for iid, hh in tr.hits.items() for k, h in hh.items()
                                     if (iid, k) not in fixed)
                        # only a hit that can change the Clapper's future re-predicts: one on an Idle Clapper (or
                        # in a state's last frames before Idle: M2's hit_idle), or a killing one; the others are
                        # carried in the hits (hp) of the next re-prediction
                        mat, pre = None, []
                        for (k, iid, h) in new:
                            if self._hit_matters(sit, b, fixed, pre, k, iid, h):
                                mat = (k, iid, h)
                                break
                            pre.append((k, iid, h))
                        if mat is None:
                            results.append((wb, b, tr, P, cons, last_hit, fixed))
                        else:
                            k, iid, h = mat
                            # (her path after the hit differs with the continuation played: its own re-prediction)
                            buckets.setdefault((k, iid, h[0], akey), []).append((wb, b, tr, tuple(pre)))
                for akey, lst in redo.items():
                    if until is not None and until():
                        return None
                    trr = lst[0][1]
                    hits: dict = {}
                    for (ii, kk), v in fixed.items():
                        hits.setdefault(ii, {})[kk] = v
                    T2 = max(P.T, trr.end + max(cfg.exit_h, cfg.t_pred) + 2)
                    P3 = self.predict(sit, hero_path(trr, T2, hits), T2)
                    P3._akey = akey
                    kf3 = [(Ps, rk) for (_, Ps, rk) in trr.alts]
                    work.append((P3, sum(x[0] for x in lst), cons, fixed, last_hit, kf3, False))
                for (k, iid, kind, ak), lst in buckets.items():
                    if until is not None and until():
                        return None
                    fx = dict(fixed)
                    for (kk, ii, hh) in lst[0][3]:
                        fx[(ii, kk)] = hh
                    fx[(iid, k)] = (kind, sk.DS_DMG if kind == "down" else sk.CLAW_DMG)
                    lst = [x[:3] for x in lst]
                    hits = {}
                    for (ii, kk), v in fx.items():
                        hits.setdefault(ii, {})[kk] = v
                    trr = lst[0][2]
                    T2 = max(T, trr.end + max(cfg.exit_h, cfg.t_pred) + 2)
                    P2 = self.predict(sit, hero_path(trr, T2, hits), T2)
                    P2._akey = ak
                    wsum = sum(x[0] for x in lst)
                    cons2 = {_choice_set(b, k) for (_, b, _) in lst}
                    new_groups.append((P2, wsum, cons2, fx, k))
                    if wsum > best_group[0]:
                        best_group = (wsum, P2)
            groups = new_groups
            if not groups:
                break
        for (P, w, cons, fixed, last_hit) in groups:     # a cascade cut by the level cap: as plain outcomes
            for b0 in P.branches:
                if (cons is None or _choice_set(b0, last_hit) in cons) and (not tag or self._tag_ok(b0, tag, fixed)):
                    vws = timing_views(b0)
                    for b in vws:
                        tr = self.sim(sit, plan, variants[0], face0, b, P.T, cfg.lag)
                        results.append((w * b0.p / len(vws), b, tr, P, cons, last_hit, fixed))
        outs = []
        ptot = sum(x[0] for x in results) or 1.0
        for (wb, b, tr, P_, cons_, lh_, fx_) in results:
            o = self._outcome(sit, wb / ptot, b, tr, exits)
            # the outcome's group: its prediction after the hits, the choice sets before its last hit, its hits
            o.P, o.cons, o.last_hit, o.fixed = P_, cons_, lh_, fx_
            outs.append(o)
        value = sum(o.p * o.value for o in outs)
        p_safe = sum(o.p for o in outs if o.safe)
        hits = sum(o.p * o.hits for o in outs)
        nominal = max(outs, key=lambda o: o.p) if outs else None
        pend = any(getattr(o, "pending", False) for o in outs)
        ev = Eval(plan, outs, value, p_safe, all(o.safe for o in outs) and not pend, hits,
                  (time.perf_counter() - t0) * 1e3, self.n_pred - n0p, self.n_exit - n0e, best_group[1], nominal,
                  sum(o.p * o.value_open for o in outs), all(o.safe or o.why.startswith("exit") for o in outs),
                  not pend)
        ev.tag, ev.start = tag, start
        return ev

    def _outcome(self, sit: Situation, p: float, br, tr: Traj, exits: bool) -> Outcome:
        cfg = self.cfg
        k_col = None
        if brnum.ON[0]:
            k_col = first_collision(br, tr, 1, tr.end, cfg.margins)
        else:
            for k in range(1, tr.end + 1):
                if tr.ifr[k]:
                    continue
                x, y = tr.pos[k]
                hb = cm.hurtbox(x, y)
                if hb[0] < WALL_L or hb[2] > WALL_R:
                    k_col = k
                    break
                if shapes_hit(bdamage(br, k, cfg.margins, sk.hook_body_off(tr.hooks, k)), hb):
                    k_col = k
                    break
        rv = _reveal(br, 1)
        tv = getattr(br, "t_reveal", None)
        if tv is not None and tv >= 1:
            rv = tv if rv is None else min(rv, tv)
        dev = None
        if rv is not None:
            dev = rv + cfg.lag
            while dev < tr.end and tr.blk[dev]:
                dev += 1
        safe, why, exit_n, k_end = True, "", -1, tr.end
        ifr_until = max([kc + sk.DS_IFR[1] for (kc, _, kind) in tr.contacts if kind == "down"], default=-1)
        if k_col is not None:
            if dev is None or k_col < dev:
                safe, why = False, f"hit@{k_col}"
            else:
                k_end = dev
        hits = sum(1 for (kc, iid, kind) in tr.contacts if kc <= k_end)
        term = self.terminal(sit, br, tr, k_end) - cfg.w_time * k_end
        vo = cfg.w_hit * hits + term if safe else -1.0
        o = Outcome(p, br, tr, safe, why or ("dev" if k_end != tr.end else ""), k_col, dev if k_end != tr.end
                    else None, hits, vo if safe else -1.0, term, exit_n, vo)
        o.k_end, o.ifr_until, o.pending = k_end, ifr_until, safe
        if safe and exits:
            self._exit(o)
        return o

    def _exit(self, o: Outcome) -> None:
        """The coarse exit check of one outcome (from its end or its deviation frame)."""
        self.units += 1
        o.pending = False
        st = state_at(self.W, o.tr, o.k_end)
        if st is None:
            o.safe, o.why, o.value = False, "exit:block", -1.0
            return
        H = self.cfg.exit_h
        re_ = rune_end(o.branch)
        if re_ is not None and re_ > o.k_end + H:
            H = min(re_ - o.k_end + 2, self.cfg.exit_h_max)        # through a big rune's burst
        o.exit_n = self.exit_ok(st[0], st[1], o.k_end, o.branch, o.ifr_until, H)
        if o.exit_n <= 0:
            o.safe, o.why, o.value = False, f"exit@{o.k_end}", -1.0

    def finish(self, ev: Eval, stop: bool = True, until=None) -> Eval:
        """Run the pending exit checks (most probable outcome first; stop at the first failure unless stop is False)
        and settle the plan's safety and value. until: a callable - true once the time is up (M4b's hard cap: the
        outcomes not checked by then count as unchecked, unsafe)."""
        t0 = time.perf_counter()
        for o in sorted(ev.outcomes, key=lambda o: -o.p):
            if getattr(o, "pending", False):
                if until is not None and until():
                    break
                self._exit(o)
                if not o.safe and stop:
                    break
        for o in ev.outcomes:
            if getattr(o, "pending", False):
                o.safe, o.why, o.value = False, "unchecked", -1.0
        ev.value = sum(o.p * o.value for o in ev.outcomes)
        ev.p_safe = sum(o.p for o in ev.outcomes if o.safe)
        ev.safe = all(o.safe for o in ev.outcomes)
        ev.ms += (time.perf_counter() - t0) * 1e3
        ev.finished = True
        return ev

    def terminal(self, sit: Situation, br, tr: Traj, k: int) -> float:
        """The terminal value at frame k (1b.6): wall room; the FACING-TO-THE-WALL rule (P3, the person 10-19): for a
        Clapper within face_wall_u of its nearer wall, +w_face when its next move (the first one starting after the
        decision, up to k + 40, in this branch) faces that wall (its evades then go to the middle, no escape jumps),
        -w_face when it faces the middle; no new move by then: half of it by her side at k (Idle / Walk turn to her);
        the distance to the nearest body beyond 6 u (a strike window next)."""
        cfg = self.cfg
        x, y = tr.pos[min(k, len(tr.pos) - 1)]
        v = -cfg.w_wall * max(0.0, 3.0 - min(x - WALL_L, WALL_R - x))
        dmin = np.inf
        for iid in sorted({o.iid for o in sit.obs}):
            st = sk.state_at(br, iid, min(k, br.T))
            if st is None or st[0] in cm.DEAD or st[0] is None:
                continue
            s_, j, cx, cy, face = st
            dmin = min(dmin, abs(cx - x))
            o0 = next((o for o in sit.obs if o.iid == iid), None)
            x0 = o0.x if o0 is not None else cx
            wall = WALL_L if x0 - WALL_L < WALL_R - x0 else WALL_R
            if abs(x0 - wall) > cfg.face_wall_u:
                continue
            to_wall = 1 if wall > x0 else -1
            nxt = None
            if brnum.ON[0]:
                nxt = brnum.next_move(br, iid, k + 40)        # M4b: the same from the record arrays
            else:
                for r in br.recs.get(iid, ()):
                    if 1 <= r[0] <= k + 40 and r[3] in MOVE_STARTS and r[4] <= 1:
                        if nxt is None or r[0] < nxt[0]:
                            nxt = (r[0], r[7])
            if nxt is not None:
                v += cfg.w_face * (1.0 if nxt[1] == to_wall else -1.0)
            elif s_ in ("Idle", "Walk"):
                side = 1 if x > cx else -1
                v += 0.5 * cfg.w_face * (1.0 if side == to_wall else -1.0)
        if np.isfinite(dmin):
            v -= cfg.w_dist * max(0.0, dmin - 6.0)
        return v


# ---- candidate generation -------------------------------------------------------------------------------------------

@dataclass
class Node:
    plan: Plan                     # the plan so far (its last segment ends at this node's frame)
    k0: int                        # the node's frame (absolute)
    S: np.ndarray                  # her state there (the nominal outcome)
    pred: object                   # the prediction the node's children see (after the plan's hits)
    ev: Eval | None = None
    depth: int = 0
    next_atk: int = 0              # the earliest frame of the next swing (the slash cadence)
    var_states: dict | None = None  # after a Clawline: {hook variant: (frame, state)} in the nominal branch
    nom_var: str = ""
    tag: tuple = ()                 # the contingency path: ((split plan key, P, reaction key), ...) of the reactions
    #                                 this node lives in (its pred holds only their branches)
    claw_ctrl: int | None = None    # after a Clawline: its control frame (the next Clawline's lock, control + 13)
    hook_iid: int | None = None     # after a HOOKED Clawline: its target, whose body does not hurt to control + 12
    start: tuple | None = None      # inside a reaction (tag): where its children's conditional evaluation starts
    #                                 (the group's hits, choice sets before the last hit, last hit, a branch)


def _union_danger(pred, k0: int, H: int, margins: bool, body_off: tuple | None = None) -> list:
    """Per frame k0 .. k0 + H the union of the branches' danger and the walls; body_off (iid, k_last): that Clapper's
    body left out through frame k_last (a hooked Clawline's window, strike.HOOK_BODY_OFF; M4a)."""
    out = []
    for t in range(H + 1):
        skip = (body_off[0],) if (body_off is not None and k0 + t <= body_off[1]) else ()
        parts = [branch_danger(b, k0 + t, margins, skip) for b in pred.branches]
        parts.append(WALL_BOXES)
        out.append(np.concatenate(parts))
    return out


def _alive(pred) -> list:
    iids = set()
    for b in pred.branches:
        iids |= set(brnum.iids(b))
    return sorted(iids)


_BG: list = []


def _bg_pool():
    """The search's background thread (the 2-event pass while the first pass's candidates are evaluated)."""
    if not _BG:
        from concurrent.futures import ThreadPoolExecutor
        _BG.append(ThreadPoolExecutor(max_workers=1, thread_name_prefix="map2-pass"))
    return _BG[0]


class Searcher:
    def __init__(self, W: World | None = None, cfg: Cfg | None = None):
        self.W = W or World()
        self.cfg = cfg or Cfg()
        self.ev = Evaluator(self.W, self.cfg)
        MARGIN_SCALE[0] = float(self.cfg.margin_scale)
        self.stats: dict = {}
        self.splits: dict = {}
        self.debug = False
        self.trace: list = []
        # the clock of the time cap: None = wall time; a float = a VIRTUAL clock, seconds per work unit (Evaluator.units:
        # one closed-loop evaluation or exit check) - deterministic runs (the identity checks of the speed work)
        self.vclock: float | None = None
        # the ANYTIME trace of the last decide(): (clock s, wall ms, value, safe, origin, plan frames) each time the
        # best plan changed (the noop included)
        self.anytime: list = []
        # M4b: one part of a split search (i, n) - this searcher takes the root's candidates whose key hashes to i
        # (the safe endpoints and the library: part 0) and the whole subtree below them; None: all of it
        self.part: tuple | None = None
        # M4c: a callable plan -> plan applied to every plan the search builds (_merge) before it is evaluated (the
        # live worker's: its masks as the oracle's hold filter latches them, ssbot.map2.live.HoldRealizer); None: none
        self.realizer = None
        # M4d2: a callable (eval, kept eval | None) called with each new safe best that is not the kept plan nor the
        # noop (the live worker sends it at once: anytime); None: none (the search itself is unchanged by it)
        self.on_best = None

    def _mine(self, c) -> bool:
        if self.part is None:
            return True
        i, n = self.part
        if c[0] == "safe":
            return i == 0
        key = (c[0], int(c[1]), -1 if c[5] is None else int(c[5]), int(round(float(c[3]) * 4)), int(c[6]))
        return zlib.crc32(repr(key).encode()) % n == i

    def _now(self) -> float:
        return time.perf_counter() if self.vclock is None else self.ev.units * self.vclock

    # ---- the pass and the windows ----
    def passes(self, node: Node, which=None, bg: bool = False) -> list:
        """The approach passes from the node (cfg.passes; which: only these indices). bg: started on the background
        thread (the pass runs without the GIL: M4b's cfg.pass2_bg) - a list of futures."""
        out = []
        cu = None
        if node.claw_ctrl is not None:
            # the next Clawline from control + 13 (M0: hooked 0 / 18 before + 12, 1 / 2 at + 12, 9 / 9 at + 13)
            cu = np.array([-1.0, 0, 0, max(0.0, float(ej.CLAW_NEXT_F - (node.k0 - node.claw_ctrl))), 0, 0, 0])
        bo = None
        if node.claw_ctrl is not None and node.hook_iid is not None:
            bo = (node.hook_iid, node.claw_ctrl + sk.HOOK_BODY_OFF[1])
        for pi, (ne, H) in enumerate(self.cfg.passes):
            if which is not None and pi not in which:
                continue
            dz = _union_danger(node.pred, node.k0, H, self.cfg.margins, bo)
            st = self.W.E.start_state(node.S, cu=cu)
            if bg:
                out.append(_bg_pool().submit(self.W.E.forward, st, H, danger=dz, terrain=self.W.TT, max_events=ne,
                                             claw=False, par=self.cfg.fwd_threads))
                continue
            fw = self.W.E.forward(st, H, danger=dz, terrain=self.W.TT, max_events=ne, claw=False,
                                  par=self.cfg.fwd_threads)
            out.append(fw)
        return out

    @staticmethod
    def _rows(fw) -> dict:
        """Every frame's rows of the pass at once: frame, cluster, x interval, height, vy, end-condition bits."""
        R = getattr(fw, "_rows_all", None)
        if R is not None:
            return R
        ts, gs_, x0s, x1s, ys = [], [], [], [], []
        for tp in range(1, fw.T + 1):
            g, x0, x1, y0, y1 = fw.frame_rows(tp)
            if len(g):
                ts.append(np.full(len(g), tp)), gs_.append(g), x0s.append(x0), x1s.append(x1), ys.append(y1)
        if ts:
            R = {"t": np.concatenate(ts), "g": np.concatenate(gs_), "x0": np.concatenate(x0s),
                 "x1": np.concatenate(x1s), "y": np.concatenate(ys)}
            R["vy"] = fw.cl_vy[R["g"]]
            R["cond"] = fw.cl_cond[R["g"]]
        else:
            R = {"t": np.zeros(0, np.int64)}
        fw._rows_all = R
        return R

    def windows(self, node: Node, fw) -> list:
        """Candidate presses: (kind, t_rel, cluster, x, y, iid, d, c_abs) from the windows bound to the enemy - the
        same list as windows_ref (M3's loops), computed with array operations (M4b; tests/test_m4b_speed.py)."""
        cfg = self.cfg
        cands = []
        brs = sorted(node.pred.branches, key=lambda b: -b.p)[:cfg.n_branch]
        R = self._rows(fw)
        n = len(R["t"])
        for b in brs:
            for iid in brnum.iids(b):
                boxes = sk.robust_boxes(b, iid, node.pred.T)
                nb_ = len(boxes)
                found = {"dslash": [], "claw": []}
                if "dslash" in cfg.prims and n:
                    done = np.zeros(n, bool)
                    base = (R["t"] + node.k0 >= node.next_atk) & ((R["cond"] & ej.COND_DSLASH) != 0)
                    for dc in (4, 3, 6):                  # the contact at press + dc (the press in tp + 1)
                        c = node.k0 + R["t"] + 1 + dc
                        cc = np.minimum(c, nb_ - 1)
                        bx = boxes[cc]
                        ok = base & ~done & (c < nb_) & ~np.isnan(bx[:, 0])
                        if not ok.any():
                            continue
                        rx0, rx1 = bx[:, 0] - 1.742, bx[:, 2] + 1.742
                        ry0, ry1 = bx[:, 1] + 0.368 - sk.CTR_DY, bx[:, 3] + 2.676 - sk.CTR_DY
                        yc = R["y"] + R["vy"] * dc / 60.0 - 0.5 * 60.0 * (dc / 60.0) ** 2
                        sel = ok & (R["x1"] >= rx0 - 0.5) & (R["x0"] <= rx1 + 0.5) & (yc >= ry0) & (yc <= ry1)
                        done |= sel
                        I = np.flatnonzero(sel)
                        if not len(I):
                            continue
                        a_ = np.maximum(R["x0"][I], rx0[I] - 0.5)
                        bb_ = np.minimum(R["x1"][I], rx1[I] + 0.5)
                        cx = 0.5 * (bx[I, 0] + bx[I, 2])
                        mid = 0.5 * (a_ + bb_)
                        X = np.empty((len(I), 3))
                        V = np.zeros((len(I), 3), bool)
                        X[:, 0], V[:, 0] = mid, True
                        # the middle of the overlap and, when wide, both sides of its centre (the contact's side
                        # steers its next move's facing: P3)
                        for col, sd in ((1, -0.9), (2, 0.9)):
                            xv = np.minimum(np.maximum(cx + sd, a_ + 0.1), bb_ - 0.1)
                            X[:, col] = xv
                            V[:, col] = (bb_ - a_ > 0.2) & ((xv - cx) * sd > 0.3) & (np.abs(xv - mid) > 0.3)
                        m = V.ravel()
                        k_ = np.repeat(I, 3)[m]
                        xm = X.ravel()[m]
                        found["dslash"].append((R["t"][k_], R["g"][k_], xm, R["y"][k_], np.full(len(k_), dc),
                                                np.abs(xm - np.repeat(cx, 3)[m])))
                if "claw" in cfg.prims and n:
                    hit = node.k0 + R["t"] + 1 + sk.HOOK_HIT_F
                    hh = np.minimum(hit, nb_ - 1)
                    bx = boxes[hh]
                    ok = ((R["cond"] & ej.COND_CLAW) != 0) & (hit < nb_) & ~np.isnan(bx[:, 0])
                    if ok.any():
                        bbh = R["y"] - sk.HALF_H + 0.0774 * np.clip(R["vy"], -10.0, 5.0)
                        band = (bx[:, 1] < bbh + sk.RAY_BAND[1]) & (bx[:, 3] > bbh + sk.RAY_BAND[0])
                        for d in (1, -1):
                            if d > 0:
                                rx0, rx1 = bx[:, 0] - sk.RAY_U - 1.5, bx[:, 2]
                            else:
                                rx0, rx1 = bx[:, 0], bx[:, 2] + sk.RAY_U + 1.5
                            sel = ok & band & (R["x1"] >= rx0) & (R["x0"] <= rx1)
                            I = np.flatnonzero(sel)
                            if not len(I):
                                continue
                            a_ = np.maximum(R["x0"][I], rx0[I])
                            bb_ = np.minimum(R["x1"][I], rx1[I])
                            near = bx[I, 0] if d > 0 else bx[I, 2]
                            # the point nearest the body (the shortest pull) but not inside it
                            xm = (bb_ - 0.3) if d > 0 else (a_ + 0.3)
                            xm = np.minimum(np.maximum(xm, a_), bb_)
                            keep = (near - xm) * d >= 0.3
                            I, xm, near = I[keep], xm[keep], near[keep]
                            found["claw"].append((R["t"][I], R["g"][I], xm, R["y"][I], np.full(len(I), d),
                                                  np.abs(near - xm)))
                for kind, parts in found.items():
                    if not parts:
                        continue
                    T_ = np.concatenate([q[0] for q in parts])
                    if not len(T_):
                        continue
                    G_ = np.concatenate([q[1] for q in parts])
                    X_ = np.concatenate([q[2] for q in parts])
                    Y_ = np.concatenate([q[3] for q in parts])
                    E_ = np.concatenate([q[4] for q in parts])
                    D_ = np.concatenate([q[5] for q in parts])
                    # spread over the whole horizon: per 6-frame bin the best rows (dslash: up to 3 x points of the
                    # earliest frame in the bin; claw: the nearest), bins taken evenly up to n_win rows
                    o = np.lexsort((D_, T_))                       # stable: ties keep the order found
                    T_, G_, X_, Y_, E_, D_ = T_[o], G_[o], X_[o], Y_[o], E_[o], D_[o]

                    def row(i):
                        return (int(T_[i]), int(G_[i]), float(X_[i]), float(Y_[i]), int(E_[i]), float(D_[i]))
                    keys, starts = np.unique(T_ // 6, return_index=True)
                    ends = np.append(starts[1:], len(T_))
                    pos = list(range(len(keys)))
                    nb = max(1, cfg.n_win)
                    if len(pos) > nb:
                        pos = [pos[int(round(i))] for i in np.linspace(0, len(pos) - 1, nb)]
                    for pi in pos:
                        s0, s1 = int(starts[pi]), int(ends[pi])
                        nf = s0 + int(np.searchsorted(T_[s0:s1], T_[s0], side="right"))
                        sel_rows = [row(s0)]
                        if kind == "claw":
                            # the hold height matters (the bounce from control): the lowest, the highest and the
                            # middle press heights of the bin
                            yr = [round(float(v), 2) for v in Y_[s0:s1]]
                            ys = sorted(set(yr))
                            for yv in (ys[-1], ys[len(ys) // 2]):
                                r2 = row(s0 + yr.index(yv))
                                if r2 not in sel_rows:
                                    sel_rows.append(r2)
                        elif nf - s0 > 1:
                            sel_rows += [row(i) for i in range(s0 + 1, min(nf, s0 + 3))]   # the sides of its centre
                        for r in sel_rows:
                            cands.append((kind, r[0], r[1], r[2], r[3], iid, r[4], b))
        # dedupe
        seen, out = set(), []
        for c in cands:
            key = (c[0], c[1], round(c[3] * 2) / 2, c[5], c[6])
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
        return out

    def windows_ref(self, node: Node, fw) -> list:
        """M3's windows (the loops; the reference of the M4b version's test)."""
        cfg = self.cfg
        cands = []
        brs = sorted(node.pred.branches, key=lambda b: -b.p)[:cfg.n_branch]
        H = fw.T
        # every frame's rows at once: frame, cluster, x interval, height, vy, end-condition bits
        ts, gs_, x0s, x1s, ys = [], [], [], [], []
        for tp in range(1, H + 1):
            g, x0, x1, y0, y1 = fw.frame_rows(tp)
            if len(g):
                ts.append(np.full(len(g), tp)), gs_.append(g), x0s.append(x0), x1s.append(x1), ys.append(y1)
        if ts:
            R = {"t": np.concatenate(ts), "g": np.concatenate(gs_), "x0": np.concatenate(x0s),
                 "x1": np.concatenate(x1s), "y": np.concatenate(ys)}
            R["vy"] = fw.cl_vy[R["g"]]
            R["cond"] = fw.cl_cond[R["g"]]
        else:
            R = {"t": np.zeros(0, np.int64)}
        for b in brs:
            for iid in b.recs:
                boxes = sk.robust_boxes(b, iid, node.pred.T)
                found = {"dslash": [], "claw": []}
                nb_ = len(boxes)
                if "dslash" in cfg.prims and len(R["t"]):
                    done = np.zeros(len(R["t"]), bool)
                    base = (R["t"] + node.k0 >= node.next_atk) & ((R["cond"] & ej.COND_DSLASH) != 0)
                    for dc in (4, 3, 6):                  # the contact at press + dc (the press in tp + 1)
                        c = node.k0 + R["t"] + 1 + dc
                        cc = np.minimum(c, nb_ - 1)
                        bx = boxes[cc]
                        ok = base & ~done & (c < nb_) & ~np.isnan(bx[:, 0])
                        if not ok.any():
                            continue
                        rx0, rx1 = bx[:, 0] - 1.742, bx[:, 2] + 1.742
                        ry0, ry1 = bx[:, 1] + 0.368 - sk.CTR_DY, bx[:, 3] + 2.676 - sk.CTR_DY
                        yc = R["y"] + R["vy"] * dc / 60.0 - 0.5 * 60.0 * (dc / 60.0) ** 2
                        sel = ok & (R["x1"] >= rx0 - 0.5) & (R["x0"] <= rx1 + 0.5) & (yc >= ry0) & (yc <= ry1)
                        done |= sel
                        for i in np.flatnonzero(sel):
                            a_, bb_ = max(R["x0"][i], rx0[i] - 0.5), min(R["x1"][i], rx1[i] + 0.5)
                            cx = 0.5 * (bx[i, 0] + bx[i, 2])
                            # the middle of the overlap and, when wide, both sides of its centre (the contact's side
                            # steers its next move's facing: P3)
                            xs_ = [0.5 * (a_ + bb_)]
                            for sd in (-0.9, 0.9):           # each side of its centre (the contact's side: P3)
                                xv = min(max(cx + sd, a_ + 0.1), bb_ - 0.1)
                                if bb_ - a_ > 0.2 and (xv - cx) * sd > 0.3 and abs(xv - xs_[0]) > 0.3:
                                    xs_.append(xv)
                            for xm in xs_:
                                found["dslash"].append((int(R["t"][i]), int(R["g"][i]), float(xm), float(R["y"][i]),
                                                        dc, abs(xm - cx)))
                if "claw" in cfg.prims and len(R["t"]):
                    hit = node.k0 + R["t"] + 1 + sk.HOOK_HIT_F
                    hh = np.minimum(hit, nb_ - 1)
                    bx = boxes[hh]
                    ok = ((R["cond"] & ej.COND_CLAW) != 0) & (hit < nb_) & ~np.isnan(bx[:, 0])
                    if ok.any():
                        bbh = R["y"] - sk.HALF_H + 0.0774 * np.clip(R["vy"], -10.0, 5.0)
                        band = (bx[:, 1] < bbh + sk.RAY_BAND[1]) & (bx[:, 3] > bbh + sk.RAY_BAND[0])
                        for d in (1, -1):
                            if d > 0:
                                rx0, rx1 = bx[:, 0] - sk.RAY_U - 1.5, bx[:, 2]
                            else:
                                rx0, rx1 = bx[:, 0], bx[:, 2] + sk.RAY_U + 1.5
                            sel = ok & band & (R["x1"] >= rx0) & (R["x0"] <= rx1)
                            for i in np.flatnonzero(sel):
                                a_, bb_ = max(R["x0"][i], rx0[i]), min(R["x1"][i], rx1[i])
                                near = bx[i, 0] if d > 0 else bx[i, 2]
                                # the point nearest the body (the shortest pull) but not inside it
                                xm = (bb_ - 0.3) if d > 0 else (a_ + 0.3)
                                xm = min(max(xm, a_), bb_)
                                if (near - xm) * d < 0.3:
                                    continue
                                found["claw"].append((int(R["t"][i]), int(R["g"][i]), float(xm), float(R["y"][i]), d,
                                                      abs(near - xm)))
                for kind, lst in found.items():
                    if not lst:
                        continue
                    # spread over the whole horizon: per 6-frame bin the best rows (dslash: up to 3 x points of the
                    # earliest frame in the bin; claw: the nearest), bins taken evenly up to n_win rows
                    bins: dict = {}
                    for r in sorted(lst, key=lambda r: (r[0], r[5])):
                        bins.setdefault(r[0] // 6, []).append(r)
                    keys = sorted(bins)
                    per = 2 if kind == "dslash" else 1
                    nb = max(1, cfg.n_win)
                    if len(keys) > nb:
                        keys = [keys[int(round(i))] for i in np.linspace(0, len(keys) - 1, nb)]
                    for n_, kb in enumerate(keys):
                        rows = bins[kb]
                        t0_ = rows[0][0]
                        first = [r for r in rows if r[0] == t0_]
                        sel = first[:1]
                        if kind == "claw":
                            # the hold height matters (the bounce from control): the lowest, the highest and the
                            # middle press heights of the bin
                            ys = sorted({round(r[3], 2) for r in rows})
                            for yv in (ys[-1], ys[len(ys) // 2]):
                                r2 = min((r for r in rows if round(r[3], 2) == yv), key=lambda r: (r[0], r[5]))
                                if r2 not in sel:
                                    sel.append(r2)
                        elif per > 1 and len(first) > 1:
                            sel += first[1:3]                                # the sides of its centre
                        for r in sel:
                            cands.append((kind, r[0], r[1], r[2], r[3], iid, r[4], b))
        # dedupe
        seen, out = set(), []
        for c in cands:
            key = (c[0], c[1], round(c[3] * 2) / 2, c[5], c[6])
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
        return out

    def realize(self, node: Node, fw, cand) -> Seg | None:
        """The witness keys to the window's press point at frame tp (the cluster's state after frame tp: its end-
        condition bits say what a press in frame tp + 1 does), then the press in frame tp + 1."""
        kind, tp, g, x, y, iid, extra, br = cand[:8]
        w = fw.witness(tp, x, y, tol_y=1e-6)
        if w is None:
            return None
        masks = np.asarray(w["masks"], np.int64).copy()
        last = int(masks[-1]) if len(masks) else 0
        if kind == "dslash":
            dc = extra
            press = (last & DIRS) | M_DS
            tail = np.zeros(sk.DS_ACTIVE[1], np.int64)
            # the direction of the approach kept to the expected contact, then no key (the swing's window)
            tail[:max(dc - 1, 0)] = last & DIRS
            masks = np.concatenate([masks, [press], tail])
            return Seg(masks, [(tp, iid)], None, f"ds@{iid}")
        d = extra
        masks = np.concatenate([masks, [km.B_RIGHT if d > 0 else km.B_LEFT]])
        return Seg(masks, [], (d, iid), f"claw@{iid}")

    def _variants(self, fw, node: Node, c) -> list:
        """The refinement of a down slash window: the press 1 - 2 frames earlier / later at the same x, and the same
        frame 0.4 u to either side (a cluster of the frame with the end condition, the height nearest the original);
        marked with a 9th field so they are not refined again."""
        kind, tp, g, x, y, iid, dc, br = c
        out = []
        for (dt, dx) in ((-1, 0.0), (1, 0.0), (-2, 0.0), (2, 0.0), (0, -0.4), (0, 0.4)):
            t2 = tp + dt
            if t2 < 1 or t2 > fw.T:
                continue
            gg, x0, x1, y0, y1 = fw.frame_rows(t2)
            if not len(gg):
                continue
            x2 = x + dx
            ok = ((fw.cl_cond[gg] & ej.COND_DSLASH) != 0) & (x0 <= x2) & (x2 <= x1)
            if not ok.any():
                continue
            i = np.flatnonzero(ok)[np.argmin(np.abs(y1[ok] - y))]
            out.append((kind, t2, int(gg[i]), float(x2), float(y1[i]), iid, dc, br, "ref"))
        return out

    def safe_cands(self, node: Node, fw, T: int | None = None) -> list:
        """The safe endpoints: clusters alive at the pass's end (or frame T), spread in x (ground first, then the
        air)."""
        T = fw.T if T is None else min(int(T), fw.T)
        g, x0, x1, y0, y1 = fw.frame_rows(T)
        if not len(g):
            return []
        xs = np.concatenate([x0, x1, 0.5 * (x0 + x1)])
        gs = np.concatenate([g, g, g])
        ys = np.concatenate([y1, y1, y1])
        order = np.argsort(xs)
        n = self.cfg.n_safe
        idx = np.unique(np.linspace(0, len(order) - 1, n).astype(int))
        out = []
        for i in idx:
            j = order[i]
            out.append(("safe", T, int(gs[j]), float(xs[j]), float(ys[j]), None, 0, None))
        return out

    def realize_safe(self, fw, cand) -> Seg | None:
        _, tp, g, x, y, *_ = cand
        w = fw.witness(tp, x, y, tol_y=1e-6)
        if w is None:
            return None
        return Seg(np.asarray(w["masks"], np.int64).copy(), [], None, "safe")

    # ---- the decision ----
    def root(self, sit: Situation, prefix: Seg | None = None) -> Node:
        """The root node: her state now, the prediction under her do-nothing path. prefix (M4c, the live worker): the
        keys already on their way to the game and the bridge she is expected to play while the search runs (latched
        masks, down slash presses with their targets, no Clawline) - every plan then starts with them: the root is
        the node after the prefix (its nominal outcome's state and prediction, as a node after a strike is), the noop
        is the prefix and one frame of no key. None: as before (M3 / M4b)."""
        if prefix is None:
            noop = Plan([Seg(np.zeros(1, np.int64))], "noop")
            ev = self.ev.evaluate(sit, noop, exits=False)
            nd = Node(Plan([], "prim"), 0, sit.S.copy(), ev.pred, None, 0, 0)
            nd.noop_ev = ev
            return nd
        if prefix.claw is not None:
            raise ValueError("a root prefix cannot end in a Clawline")
        n = len(prefix.masks)
        pre = np.asarray(prefix.masks, np.int64)
        noop = Plan([Seg(np.concatenate([pre, np.zeros(1, np.int64)]), list(prefix.dsl), None, "pre")], "noop")
        ev = self.ev.evaluate(sit, noop, exits=False)
        rep = ev.nominal
        st = state_at(self.W, rep.tr, n) if rep is not None else None
        S = st[0] if st is not None else self.W.roll(sit.S, pre).final[:, 0].copy()
        pred = ev.pred
        nx = 0
        if rep is not None and rep.tr.contacts:
            pred = self._node_pred(rep, ()) or ev.pred
            nx = max([kc for (kc, _, kd) in rep.tr.contacts if kd == "down"], default=-99) + sk.SLASH_NEXT_F - 3
        nd = Node(Plan([Seg(pre.copy(), list(prefix.dsl), None, "pre")], "prim"), n, S, pred, None, 0, max(nx, 0))
        nd.noop_ev = ev
        return nd

    def _after_claw(self, seg: Seg) -> Seg:
        # after a Clawline: the segment is anchored at its control; its first frame is the forced bounce's (EV_POGO,
        # no key): the node's state was taken after it
        return Seg(np.concatenate([np.zeros(1, np.int64), seg.masks]), [(i + 1, iid) for (i, iid) in seg.dsl],
                   seg.claw, seg.tag)

    def _alt_segs(self, node: Node, cand, var: str, n: int = 3) -> list:
        """The same strike re-planned from another hook variant's control: the windows of the same primitive on the
        same Clapper nearest in time to the nominal one (up to n, realized)."""
        k0, S = node.var_states[var]
        cache = node.__dict__.setdefault("_alt_cache", {})
        if var not in cache:                     # the variant's passes and windows once per node
            nv = Node(node.plan, k0, S, node.pred, node.ev, node.depth, node.next_atk, tag=node.tag,
                      claw_ctrl=None if node.claw_ctrl is None else k0 - 1, start=node.start,
                      hook_iid=node.hook_iid)
            cache[var] = (nv, [(fw, c) for fw in self.passes(nv) for c in self.windows(nv, fw)])
        nv, allw = cache[var]
        kind, tp, _, x, _, iid, extra, _ = cand[:8]
        want = node.k0 + tp
        found = []
        for fw, c in allw:
            if c[0] != kind or c[5] != iid:
                continue
            found.append((abs(k0 + c[1] - want) + (0 if c[6] == extra else 0.5) + 0.1 * abs(c[3] - x), fw, c))
        out = []
        for _, fw, c in sorted(found, key=lambda t: t[0])[:n]:
            sg = self.realize(nv, fw, c)
            if sg is not None:
                out.append(self._after_claw(sg))
        return out

    def _merge(self, node: Node, seg: Seg, origin: str) -> Plan:
        plan = Plan([s.copy() for s in node.plan.segs] + [seg], origin)
        if node.plan.segs and node.plan.segs[-1].claw is None:
            # merge into the previous segment (no branch point between them)
            prev = plan.segs[-2]
            off = len(prev.masks)
            prev.masks = np.concatenate([prev.masks, seg.masks])
            prev.dsl = prev.dsl + [(i + off, iid) for (i, iid) in seg.dsl]
            prev.claw = seg.claw
            prev.tag = (prev.tag + "+" + seg.tag).strip("+")
            plan.segs.pop()
        # M4c: the live worker's realizer (the keys as the oracle's hold filter will latch them); None: as before
        return plan if self.realizer is None else self.realizer(plan)

    def child(self, sit: Situation, node: Node, seg: Seg, origin: str, cand=None) -> tuple[Plan, Eval]:
        if node.plan.segs and node.plan.segs[-1].claw is not None:
            seg = self._after_claw(seg)
            if node.var_states and cand is not None and cand[0] != "safe" and                     not self.ev.quick(sit, self._merge(node, seg, origin), node.pred, node.k0):
                # control is a branch point: per other hook variant the strike re-planned there; the alternative
                # that keeps the plan open (no collision) best is taken (only when the nominal one screens well)
                best = None
                for v in node.var_states:
                    if v == node.nom_var:
                        continue
                    for a in self._alt_segs(node, cand, v):
                        sg = seg.copy()
                        sg.var_alt = dict(seg.var_alt or {})
                        sg.var_alt[v] = a
                        plan = self._merge(node, sg, origin)
                        ev = self._eval_screened(sit, node, plan, cand)
                        if best is None or (ev.open_ok, ev.value_open) > (best[1].open_ok, best[1].value_open):
                            best = (plan, ev)
                        if ev.open_ok:
                            break
                if best is not None:
                    return best
        plan = self._merge(node, seg, origin)
        ev = self._eval_screened(sit, node, plan, cand)
        return plan, ev

    def _eval_screened(self, sit: Situation, node: Node, plan: Plan, cand) -> Eval:
        """The closed-loop evaluation of a strike candidate after the cheap pre-screen (quick) passed; a failed screen
        gives an unsafe, finished Eval without outcomes."""
        if cand is not None and cand[0] != "safe":
            why = self.ev.quick(sit, plan, node.pred, node.k0)
            self.stats["screen_" + (why.split("@")[0] or "pass")] = self.stats.get(
                "screen_" + (why.split("@")[0] or "pass"), 0) + 1
            if why:
                return Eval(plan, [], -1.0, 0.0, False, 0.0, 0.0, 0, 0, None, None, -1.0, False, True)
        e = self.ev.evaluate(sit, plan, exits=False, tag=node.tag, start=node.start,
                             until=getattr(self, "_until", None))
        if e is None:                         # (the hard cap: cut at the time - unsafe, finished, no outcomes)
            self.stats["cut"] = self.stats.get("cut", 0) + 1
            return Eval(plan, [], -1.0, 0.0, False, 0.0, 0.0, 0, 0, None, None, -1.0, False, True)
        return e

    # ---- nodes (after a landed strike) and the contingent splits ----
    def _in_tag(self, o: Outcome, tag: tuple) -> bool:
        return all(reaction_key(o.branch, P, self.cfg.lag) == rk for (_, P, rk) in tag)

    def _node_pred(self, o: Outcome, tag: tuple):
        """The prediction a node continues in: the outcome's group prediction (after the plan's hits), its branches
        consistent with the history before the last hit and with the node's reactions (tag)."""
        P = getattr(o, "P", None)
        if P is None:
            return None
        cons, lh = getattr(o, "cons", None), getattr(o, "last_hit", -1)
        brs = [b for b in P.branches if (cons is None or _choice_set(b, lh) in cons) and
               all(reaction_key(b, Pk, self.cfg.lag) == rk for (_, Pk, rk) in tag)]
        if not brs:
            return None
        return cm.Prediction(brs, P.T, P.n_particles, 0.0)

    def _one_node(self, plan: Plan, outs: list, depth: int, tag: tuple) -> Node | None:
        rep = max(outs, key=lambda o: o.p)
        tr = rep.tr
        if not tr.contacts:
            return None
        st = state_at(self.W, tr, tr.end)
        if st is None:
            return None
        pred = self._node_pred(rep, tag)
        if pred is None:
            return None
        nx_atk = max([kc for (kc, _, kd) in tr.contacts if kd == "down"], default=-99) + sk.SLASH_NEXT_F - 3
        nd = Node(plan, tr.end, st[0], pred, None, depth, nx_atk, tag=tag)
        if tag:
            nd.start = (dict(getattr(rep, "fixed", {}) or {}), getattr(rep, "cons", None),
                        getattr(rep, "last_hit", -1), rep.branch)
        ptot = sum(o.p for o in outs) or 1.0
        nd.v = sum(o.p * o.value_open for o in outs) / ptot
        nd.rep = rep
        nd.rk = None
        if plan.segs[-1].claw is not None:
            vs = {}
            for o in outs:
                if o.branch is rep.branch and o.tr.variant not in vs:
                    so = state_at(self.W, o.tr, o.tr.end)
                    if so is not None:
                        vs[o.tr.variant] = (o.tr.end, so[0])
            nd.var_states, nd.nom_var = vs, tr.variant
            if tr.claws:
                nd.claw_ctrl = int(tr.claws[-1][5])
                nd.hook_iid = int(tr.claws[-1][1]) if tr.claws[-1][3] else None
        return nd

    def _mk_nodes(self, plan: Plan, e: Eval, depth: int, tag: tuple = ()) -> list:
        """The nodes after a plan whose strike landed (no collision before its end) in the outcomes of the node's own
        reactions (tag): her state at the plan's end there; after a Clawline the hook variants' control states (each
        re-planned). A hooked Clawline whose hit splits the Clappers' future into reactions she sees by control gives
        ONE NODE PER REACTION (cfg.split): its own prediction (only that reaction's branches: its own danger), its
        own continuation - recombined later (_combine)."""
        if e.nominal is None or not e.outcomes:
            return []
        outs = [o for o in e.outcomes if self._in_tag(o, tag)]
        if not outs or not all(_open(o) for o in outs):
            return []
        nd = self._one_node(plan, outs, depth, tag)
        if nd is None:
            return []
        rep = nd.rep
        if not (self.cfg.split and plan.segs[-1].claw is not None and rep.tr.claws and rep.tr.claws[-1][3]):
            return [nd]
        P_last = int(rep.tr.claws[-1][0])
        groups: dict = {}
        for o in outs:
            groups.setdefault(reaction_key(o.branch, P_last, self.cfg.lag), []).append(o)
        if len(groups) < 2:
            return [nd]
        ptot = sum(o.p for o in outs) or 1.0
        pkey = plan.key()
        rks = sorted(groups, key=lambda rk: -sum(o.p for o in groups[rk]))
        rks = [rk for rk in rks if sum(o.p for o in groups[rk]) >= self.cfg.split_min_p * ptot][:self.cfg.split_max]
        nodes = []
        for rk in rks:
            n2 = self._one_node(plan, groups[rk], depth, tag + ((pkey, P_last, rk),))
            if n2 is not None:
                n2.rk = rk
                nodes.append(n2)
        if not nodes:
            return [nd]
        self.splits.setdefault(pkey, {"plan": plan, "ev": e, "P": P_last, "tag": tag, "depth": depth,
                                      "start": getattr(e, "start", None),
                                      "rks": [n.rk for n in nodes],
                                      "p": {rk: sum(o.p for o in groups[rk]) / ptot for rk in groups}})
        self.stats["splits"] = self.stats.get("splits", 0) + 1
        return nodes

    def _gval(self, e: Eval, tag: tuple, finish: bool) -> tuple | None:
        """(safe, value, p) of the plan's outcomes in the reactions of tag (finish: their exit checks run)."""
        outs = [o for o in e.outcomes if self._in_tag(o, tag)]
        if not outs:
            return None
        if finish:
            for o in sorted(outs, key=lambda o: -o.p):
                if getattr(o, "pending", False):
                    self.ev._exit(o)
                    if not o.safe:
                        break
            for o in outs:
                if getattr(o, "pending", False):
                    o.safe, o.why, o.value = False, "unchecked", -1.0
        p = sum(o.p for o in outs) or 1e-12
        if not finish:
            return (all(_open(o) for o in outs), sum(o.p * o.value_open for o in outs) / p, p)
        return (all(o.safe for o in outs), sum(o.p * o.value for o in outs) / p, p)

    def _combine(self, sit: Situation, tried: list, t_end: float) -> list:
        """The CONTINGENT PLANS: per split (a hooked Clawline whose reactions were expanded separately; the deepest
        first, so a nested split's combination competes in its parent's), per reaction the best continuation found
        under it (safe in that reaction's outcomes with its exits checked, best first by the open value, up to
        cfg.combine_top checked; none: the plan ends at control with its exit there), joined into one plan - the
        most probable reaction's continuation as the default, the others in Seg.out_alt - and evaluated in the
        closed loop like any plan (a reaction whose continuation fails there falls back to its next one, twice)."""
        made = []
        lag = self.cfg.lag
        idx: dict = {}                        # tag prefix -> the conditional evaluations under it

        def index(e):
            tg = getattr(e, "tag", ())
            for i in range(len(tg)):
                idx.setdefault(tg[:i + 1], []).append(e)
        for e in tried:
            if e.outcomes:
                index(e)
        # the splits with a continuation searched under some reaction, the deepest first, then by the open value
        order = [kv for kv in self.splits.items()
                 if any(kv[1]["tag"] + ((kv[0], kv[1]["P"], rk),) in idx for rk in kv[1]["rks"])]
        order.sort(key=lambda kv: (-len(kv[1]["tag"]), -kv[1]["ev"].value_open))
        n_top = 0
        for pkey, sp in order:
            if not sp["tag"]:
                n_top += 1
                if n_top > self.cfg.combine_splits:
                    break
            if self._now() > t_end:
                break
            base, ptag, P = sp["plan"], sp["tag"], sp["P"]
            nb = len(base.segs)
            options = {}
            for rk in sp["rks"]:
                pre = ptag + ((pkey, P, rk),)
                cands = [e for e in idx.get(pre, ()) if len(e.plan.segs) > nb]
                scored = []
                for e in cands:
                    g = self._gval(e, pre, finish=False)
                    if g is not None and g[0]:
                        scored.append((g[1], e))
                ok = []
                for _, e in sorted(scored, key=lambda t: -t[0])[:self.cfg.combine_top]:
                    if self._now() > t_end:
                        break
                    g = self._gval(e, pre, finish=True)
                    if g is not None and g[0]:
                        ok.append((g[1], e))
                        if len(ok) >= 3:
                            break
                if ok:
                    options[rk] = [[s_.copy() for s_ in e.plan.segs[nb:]] for _, e in sorted(ok, key=lambda t: -t[0])]
            if not options:
                continue
            p_of = sp["p"]
            pick = {rk: 0 for rk in options}
            for _try in range(3):
                conts = {rk: options[rk][i] for rk, i in pick.items() if i < len(options[rk])}
                if not conts:
                    break
                dflt = max(conts, key=lambda rk: p_of.get(rk, 0.0))
                first = conts[dflt][0].copy()
                alt = {rk: [x.copy() for x in v] for rk, v in conts.items() if rk != dflt}
                # the reactions without a continuation of their own: the plan ends at control there (its exit)
                for rk in p_of:
                    if rk not in conts:
                        alt[rk] = [Seg(np.zeros(1, np.int64))]
                first.out_alt = alt or None
                plan = Plan([x.copy() for x in base.segs] + [first] + [x.copy() for x in conts[dflt][1:]],
                            base.origin, "contingent")
                e = self.ev.evaluate(sit, plan, exits=False, tag=ptag, start=sp.get("start") if ptag else None,
                                     until=(lambda: self._now() > t_end) if self.cfg.hard_cap else None)
                if e is None:
                    return made                      # (the hard cap: the joined plan's cascade cut at the time)
                e.tag = ptag
                if e.open_ok:
                    self.ev.finish(e, stop=False, until=(lambda: self._now() > t_end) if self.cfg.hard_cap else None)
                e.contingent = {rk_label(rk): len(v) for rk, v in conts.items()}
                made.append(e)
                if e.outcomes:
                    index(e)
                self.stats["combined"] = self.stats.get("combined", 0) + 1
                if e.safe or self._now() > t_end:
                    break
                # the reactions that failed in the joined plan: their next continuation (or none)
                bad = {reaction_key(o.branch, P, lag) for o in e.outcomes if not o.safe}
                bad &= set(conts)
                if not bad:
                    break
                for rk in bad:
                    pick[rk] += 1
        return made

    def decide(self, sit: Situation, prev: Plan | None = None, cap_s: float | None = None,
               prefix: Seg | None = None) -> "Result":
        """One decision (module docstring). prefix (M4c): the keys every plan starts with (root())."""
        t0 = time.perf_counter()
        cap = self.cfg.cap_s if cap_s is None else cap_s
        cfg = self.cfg
        self.ev.n_pred = self.ev.n_exit = 0
        self.ev.ms_pred = self.ev.ms_exit = 0.0
        self.ev.units = 0
        self.ev.reset()
        self.ev.n_sim = self.ev.n_sim_hit = self.ev.n_probe = 0
        now = self._now
        t0c = now()
        self.stats = {}
        # (M4b's hard cap: a candidate's evaluation in progress at the cap is abandoned between its re-predictions)
        self._until = (lambda: now() - t0c > cap) if cfg.hard_cap else None
        self.splits = {}
        self.anytime = []
        self.marks = []                # (wall ms, what): the decision's phases and candidates (the speed work)
        last_noted = [None]

        def mark(what):
            self.marks.append((round((time.perf_counter() - t0) * 1e3, 2), what))

        def note(e):
            if e is not None and e is not last_noted[0]:
                last_noted[0] = e
                self.anytime.append((now() - t0c, (time.perf_counter() - t0) * 1e3, float(e.value), bool(e.safe),
                                     e.plan.origin, e.plan.n_frames()))
                # M4d2 (the live worker; None: nothing): each new best that is safe, finished and not the kept plan
                # nor the noop goes to the caller at once (anytime: the first safe plan sent, the better ones after)
                cb = self.on_best
                if cb is not None and e.safe and e.finished and e is not kept and e.plan.origin != "noop" and \
                        not getattr(e, "tag", ()):
                    cb(e, kept)
        tried = []
        kept = None
        if prev is not None and prev.segs:
            e = self.ev.evaluate(sit, prev)
            if e.safe:
                kept = e
                tried.append(e)
                note(kept)
        rt = self.root(sit) if prefix is None else self.root(sit, prefix)
        mark("root")
        beam = [rt]
        best = kept
        if cfg.defer_noop:
            noop = rt.noop_ev                                  # M4b: its exits run at the end (the fallback only)
        elif cfg.reuse_root:
            noop = self.ev.finish(rt.noop_ev, stop=False)      # M4b: the root's noop evaluation, its exits run
        else:
            noop = self.ev.evaluate(sit, Plan([Seg(np.zeros(1, np.int64))], "noop") if prefix is None else
                                    rt.noop_ev.plan.copy())
        tried.append(noop)
        mark("noop")

        def consider(e):
            # the exit checks only for a plan that could become the best (a conditional evaluation inside a
            # reaction never does: its exits are checked when the contingent plan is joined)
            if getattr(e, "tag", ()):
                return e
            if not e.finished and e.open_ok and (best is None or not best.safe or e.value_open > best.value + 1e-9):
                # (M4b's hard cap: a two-Clapper plan's exit checks - hundreds of outcomes - stop at the time; the
                # plan then counts as unchecked)
                self.ev.finish(e, until=(lambda: now() - t0c > cap) if cfg.hard_cap else None)
            return e
        if not cfg.defer_noop and (best is None or (noop.safe and not best.safe)):
            best = noop
        if best is not None:
            note(best)
        timed_out = False
        n_cand = 0

        def better(a, b):
            if b is None:
                return True
            if a.safe != b.safe:
                return a.safe
            if not a.safe:
                return a.p_safe > b.p_safe
            return a.value > b.value

        # the library's macros (anchored on the observed state)
        lib_nodes = []
        for combo in (cfg.library if self.part is None or self.part[0] == 0 else ()):
            for plan in combo.instantiate(self.W, sit, rt.pred):
                if now() - t0c > cap:
                    timed_out = True
                    break
                e = consider(self.ev.evaluate(sit, plan, exits=False))
                e.tag = ()
                n_cand += 1
                tried.append(e)
                if e.finished and better(e, best):
                    best = e
                    note(best)
                lib_nodes += self._mk_nodes(plan, e, 1)  # a macro that landed a strike: the search goes on after it
        for depth in range(1, cfg.depth + 1):
            nxt = list(lib_nodes) if depth == 1 else []
            # ANYTIME: each depth gets its share of the cap (cfg.depth_frac, cumulative) and each node of the beam an
            # equal part of what is left of it, so a slow depth (two Clappers) still leaves time for the next one
            frac = cfg.depth_frac[min(depth, len(cfg.depth_frac)) - 1] if depth < cfg.depth else 1.0
            depth_end = t0c + cap * frac
            for ni, node in enumerate(beam):
                if now() - t0c > cap:
                    timed_out = True
                    break
                node_end = now() + max(0.0, depth_end - now()) / (len(beam) - ni)
                lazy = cfg.pass2_after > 0 and len(cfg.passes) > 1
                fws = self.passes(node, (0,) if lazy else None)
                mark(f"passes d{depth}")
                # (M4b: the later passes started now on the background thread, joined when done)
                futs = self.passes(node, tuple(range(1, len(cfg.passes))), bg=True) if (lazy and cfg.pass2_bg) \
                    else None

                def node_cands(fws_):
                    cs = []
                    for fw in fws_:
                        ws = fw.__dict__.get("_win")
                        if ws is None:
                            ws = self.windows(node, fw)
                            fw.__dict__["_win"] = ws
                            for c in ws:
                                self.stats[f"win_{c[0]}_d{depth}"] = self.stats.get(f"win_{c[0]}_d{depth}", 0) + 1
                        cs += [(fw, c) for c in ws]
                    # round robin over (primitive, Clapper): a time slice spent on one of them alone finds nothing else
                    groups: dict = {}
                    for fc in cs:
                        groups.setdefault((fc[1][0], fc[1][5]), []).append(fc)
                    return [g[i] for i in range(max((len(g) for g in groups.values()), default=0))
                            for g in groups.values() if i < len(g)]
                cands = node_cands(fws)
                mark(f"windows d{depth} {len(cands)}")
                if depth == 1:
                    for fw in fws[:1]:
                        early = [(fw, c) for t_ in cfg.safe_ts for c in self.safe_cands(node, fw, t_)]
                        cands = early + [(fw, c) for c in self.safe_cands(node, fw)] + cands
                refine = []
                queue = list(cands) if depth > 1 else [x for x in cands if self._mine(x[1])]
                qi = 0
                n_main = len(queue)                       # the queue's candidates before the refinements
                n_ev_node = 0
                while qi < len(queue) or lazy:
                    if lazy and ((futs is None and n_ev_node >= cfg.pass2_after) or qi >= n_main or
                                 (futs is not None and all(f.done() for f in futs))):
                        # the later passes: all passes' candidates in the M3 round robin, those not taken yet
                        lazy = False
                        if now() - t0c > cap:
                            timed_out = True
                            break
                        if now() > node_end:
                            self.stats[f"sliced_d{depth}"] = self.stats.get(f"sliced_d{depth}", 0) + 1
                            break
                        fws = fws + ([f.result() for f in futs] if futs is not None else
                                     self.passes(node, tuple(range(1, len(cfg.passes)))))
                        futs = None
                        mark(f"passes2 d{depth}")
                        done_ = {id(x[1]) for x in queue[:qi]}
                        rest = [x for x in queue[qi:n_main] if x[1][0] == "safe"]      # safe endpoints not taken
                        rest += [x for x in node_cands(fws) if id(x[1]) not in done_ and (depth > 1 or self._mine(x[1]))]
                        queue = queue[:qi] + rest + queue[n_main:]
                        n_main = qi + len(rest)
                        mark(f"windows2 d{depth} {len(rest)}")
                        continue
                    if qi >= len(queue):
                        break
                    fw, c = queue[qi]
                    qi += 1
                    n_ev_node += 1
                    if now() - t0c > cap:
                        timed_out = True
                        break
                    if now() > node_end:
                        self.stats[f"sliced_d{depth}"] = self.stats.get(f"sliced_d{depth}", 0) + 1
                        break
                    seg = self.realize(node, fw, c) if c[0] != "safe" else self.realize_safe(fw, c)
                    if seg is None:
                        continue
                    plan, e = self.child(sit, node, seg, "prim" if c[0] != "safe" else "safe", c)
                    e.tag = node.tag
                    e = consider(e)
                    n_cand += 1
                    tried.append(e)
                    mark((depth, c[0], bool(e.safe), bool(e.open_ok), len(e.outcomes)))
                    if self.debug:
                        nm = e.nominal
                        self.trace.append((depth, c[0], node.k0 + c[1], round(c[3], 2), round(c[4], 2), c[5], c[6],
                                           e.safe, round(e.hits, 2), round(e.value, 2),
                                           None if nm is None else (nm.why, nm.tr.contacts, nm.tr.missed), e))
                    if e.finished and not e.tag and better(e, best):
                        best = e
                        note(best)
                    # the +-1-2 f / +-0.4 u refinement near a tight window (the spec's coarse grid then refinement): a
                    # down slash whose plan failed by a collision just before its contact or missed its target
                    if c[0] == "dslash" and len(c) == 8 and not e.open_ok and len(refine) < cfg.n_refine:
                        ct = node.k0 + c[1] + 1 + c[6]
                        tight = any(o.why.startswith("hit@") and ct - 6 <= int(o.why[4:]) <= ct + 3
                                    for o in e.outcomes) or (e.nominal is not None and e.nominal.tr.missed)
                        if tight:
                            refine.append(c)
                            for c2 in self._variants(fw, node, c):
                                queue.append((fw, c2))
                    # a child node continues after a landed strike (in the nominal outcome)
                    if c[0] != "safe":
                        nxt += self._mk_nodes(plan, e, depth, node.tag)
            if not nxt or timed_out:
                break
            # the beam: the best by the open value (in the node's own reactions), diverse in the strikes (kind,
            # target, 4-frame time bucket) and the height at the node (a Clawline's hold sets the bounce); a split's
            # reaction nodes come in together (up to cfg.beam parents, each with all its reactions)
            nxt.sort(key=lambda n: -n.v)
            beam, parents, seen_k = [], set(), set()
            for n_ in nxt:
                pk = (tuple((kc // 4, iid, kd) for (kc, iid, kd) in n_.rep.tr.contacts),
                      round(float(n_.S[km.PY]) * 2.0), n_.tag[:-1] if n_.rk is not None else n_.tag)
                if pk not in parents:
                    if len(parents) >= cfg.beam:
                        continue
                    parents.add(pk)
                key = (pk, n_.rk)
                if key in seen_k:
                    continue
                seen_k.add(key)
                beam.append(n_)
        # the contingent plans (one continuation per reaction to a hook), within a quarter of the cap more
        if self.splits:
            t_end = max(now(), t0c + cap) + 0.25 * cap
            for e in self._combine(sit, tried, t_end):
                tried.append(e)
                n_cand += 1
                if e.finished and not e.tag and better(e, best):
                    best = e
                    note(best)
        if cfg.defer_noop:
            # (the noop's value is at most its open value: a safe plan already worth as much needs no noop exits)
            if not noop.finished and not (best is not None and best.safe and best.value >= noop.value_open):
                self.ev.finish(noop, stop=False,
                               until=(lambda: now() - t0c > 1.5 * cap) if cfg.hard_cap else None)
            if noop.finished and (best is None or better(noop, best)):
                best = noop
                note(best)
        chosen = best
        if kept is not None and best is not None and best is not kept and best.safe and \
                best.value < kept.value + cfg.w_switch:
            chosen = kept                                            # hysteresis
            note(kept)
        ms = (time.perf_counter() - t0) * 1e3
        self.stats.update(n_sim=self.ev.n_sim, n_sim_hit=self.ev.n_sim_hit, n_probe=self.ev.n_probe)
        res = Result(chosen, tried, ms, timed_out, n_cand, self.ev.n_pred, self.ev.n_exit, self.ev.ms_pred,
                     self.ev.ms_exit, kept is not None and chosen is kept)
        return res


class TickCheck:
    """THE PER-FRAME CHECK of a committed plan on the bot's thread (M4b): the commit-time evaluation is kept - per
    outcome (a branch's timing view x hook variant, judged safe there) its Clappers' records per frame, her planned
    positions and the frame its committed part ends (the reveal + lag, a Clawline block moving it to control; else
    the plan's end) - and each frame's observation is matched against it: ok while some outcome is consistent with
    what she sees (every Clapper's state, its frame in the state within +- tol_j, its x within tol_x, its facing; her
    position within tol_hero) with frames of its committed part left. It neither predicts nor simulates (the commit
    already checked every outcome); an observation outside every outcome (an unpredicted move or timing, her keys
    missed, a model error) fails it - the bot then falls back while the background search re-plans (tick_check is
    the full check from a new observation). It holds arrays and dicts only: the worker process that searched pickles
    it to the bot's thread (a few hundred kB)."""

    def __init__(self, ev: Eval, tol_j: int = 1, tol_x: float = 0.35, tol_hero: float = 0.2):
        self.tol_j, self.tol_x, self.tol_hero = tol_j, tol_x, tol_hero
        self.out = []
        sid_of: dict = {}
        for o in ev.outcomes:
            if not o.safe:
                continue
            kc = int(getattr(o, "k_end", o.tr.end))
            arr, tb = brnum.barr(o.branch)
            recs = {}
            for iid, a in arr.items():
                a = a[(a[:, 0] >= 0) & (a[:, 0] <= kc)]
                a = a[np.argsort(a[:, 0], kind="stable")]
                recs[iid] = (a[:, 0].astype(np.int64), a[:, 3].astype(np.int64), a[:, 4], a[:, 5], a[:, 7])
            self.out.append((float(o.p), kc, np.asarray(o.tr.pos[:kc + 1]).copy(), recs,
                             sid_of.setdefault(id(tb), dict(tb.sid))))

    def check(self, n: int, her_xy, obs: list) -> tuple:
        """(ok, frames of the committed part left in the consistent outcomes (the most), consistent outcomes' p) at
        frame n after the commit: her transform (x, y), the Clappers as observed (Obs: st, j, x, face)."""
        left, pc = -1, 0.0
        hx, hy = float(her_xy[0]), float(her_xy[1])
        for (p, kc, pos, recs, sids) in self.out:
            if n > kc:
                continue
            if abs(pos[n, 0] - hx) > self.tol_hero or abs(pos[n, 1] - hy) > self.tol_hero:
                continue
            ok = True
            for o in obs:
                r = recs.get(o.iid)
                if r is None:
                    continue                             # a Clapper the outcome does not hold (dead): no constraint
                ks, st, j, x, f = r
                a, b = np.searchsorted(ks, n), np.searchsorted(ks, n, side="right")
                sid = sids.get(o.st, -9)
                oj = o.j if o.j is not None else int(round(o.t * 60.0))
                if not np.any((st[a:b] == sid) & (np.abs(j[a:b] - oj) <= self.tol_j) &
                              (np.abs(x[a:b] - o.x) <= self.tol_x) & (f[a:b] == o.face)):
                    ok = False
                    break
            if ok:
                left = max(left, kc - n)
                pc += p
        return left >= 0, left, pc


def observe_branch(sit: Situation, br, n: int) -> list:
    """The Clappers' observations at frame n of a branch (each one's record of frame n as an Obs) - what TickCheck
    is fed along an outcome offline."""
    out = []
    for ob in sit.obs:
        r = sk.state_at(br, ob.iid, n)
        if r is None:
            continue
        s_, j, x, y, face = r
        out.append(cm.Obs(ob.iid, s_, j / 60.0, x, y, 0.0, 0.0, face, ob.hp, ob.clip, None, 10 ** 6, ob.charged, j))
    return out


def advance(W: World, sit: Situation, ev: Eval, n: int) -> Situation:
    """The situation n frames later along the plan's nominal outcome (her kin state there; each Clapper's state,
    frame in it, position and facing from that branch's records; Memory and hazards kept) - for the hysteresis /
    flicker checks offline."""
    o = ev.nominal
    st = state_at(W, o.tr, n)
    S = st[0] if st is not None else sit.S.copy()
    obs = []
    for ob in sit.obs:
        r = sk.state_at(o.branch, ob.iid, n)
        if r is None:
            continue
        s_, j, x, y, face = r
        if s_ in cm.DEAD or s_ is None:
            continue
        nb = cm.Obs(ob.iid, s_, j / 60.0, x, y, 0.0, 0.0, face, ob.hp, ob.clip, ob.will_evade, 10 ** 6, ob.charged, j,
                    prev=ob.prev, cast2=ob.cast2, rune=ob.rune, idle_buddy=ob.idle_buddy)
        obs.append(nb)
    return Situation(S, obs, {k: v.copy() for k, v in sit.mems.items()}, list(sit.hazards), sit.name + f"+{n}",
                     dict(sit.meta))


@dataclass
class Result:
    ev: Eval | None
    tried: list
    ms: float
    timed_out: bool
    n_cand: int
    n_pred: int
    n_exit: int
    ms_pred: float
    ms_exit: float
    kept: bool = False

    @property
    def plan(self) -> Plan | None:
        return None if self.ev is None else self.ev.plan

    def log(self, t0: int = 0) -> dict:
        return plan_log(self.ev, t0) if self.ev is not None else {"t": t0, "plan": None}


# ---- the log format (the combo library's step format) -----------------------------------------------------------

KEY_NAMES = ((km.B_LEFT, "L"), (km.B_RIGHT, "R"), (km.B_UP, "U"), (km.B_DOWN, "D"), (km.B_JUMP, "J"),
             (km.B_ATTACK, "A"), (km.B_DASH, "S"))


def key_str(m: int) -> str:
    return "".join(n for b, n in KEY_NAMES if int(m) & b) or "-"


def plan_steps(plan: Plan) -> list:
    """The plan as steps: per segment its anchor ('start' or 'ctrl<i>': the i-th Clawline's control), and per key
    change {"f": the frame in the segment (1 = its first), "keys": ...}, the strikes {"f", "do": "dslash" / "claw",
    "iid", "dir"}."""
    out = []
    for si, s in enumerate(plan.segs):
        anchor = "start" if si == 0 else f"ctrl{si - 1}"
        prev = None
        for i, m in enumerate(s.masks):
            ks = key_str(m)
            if ks != prev:
                out.append({"seg": si, "anchor": anchor, "f": i + 1, "keys": ks})
                prev = ks
        for (i, iid) in s.dsl:
            out.append({"seg": si, "anchor": anchor, "f": i + 1, "do": "dslash", "iid": int(iid)})
        if s.claw is not None:
            out.append({"seg": si, "anchor": anchor, "f": len(s.masks), "do": "claw", "dir": int(s.claw[0]),
                        "iid": int(s.claw[1])})
        if s.out_alt:
            # a contingent plan: the rest of the plan per reaction seen by control (its own steps, anchored there)
            out.append({"seg": si, "anchor": anchor, "f": 0, "alt": {rk_label(rk): plan_steps(Plan(v))
                                                                    for rk, v in s.out_alt.items()}})
    return sorted(out, key=lambda r: (r["seg"], r["f"], "do" in r))


def plan_log(ev: Eval, t0: int = 0) -> dict:
    """One executed plan's log row: the steps, the expected value / hits / safety, the outcomes (p, branch label,
    hits, safe, why) - the decisions' record for combo mining."""
    outs = []
    for o in sorted(ev.outcomes, key=lambda o: -o.p)[:8]:
        outs.append({"p": round(o.p, 3), "branch": o.branch.label() if o.branch is not None else "-",
                     "var": o.tr.variant, "hits": o.hits, "safe": o.safe, "why": o.why,
                     "alt": [rk_label(rk) for (_, _, rk) in o.tr.alts],
                     "contacts": [(int(k), int(i), kd) for (k, i, kd) in o.tr.contacts]})
    return {"t": int(t0), "origin": ev.plan.origin, "note": ev.plan.note, "value": round(ev.value, 3),
            "hits": round(ev.hits, 3),
            "p_safe": round(ev.p_safe, 3), "steps": plan_steps(ev.plan), "outcomes": outs}


__all__ = ["World", "Situation", "Cfg", "Seg", "Plan", "Traj", "simulate", "state_at", "Evaluator", "Eval",
           "Outcome", "Searcher", "Result", "plan_steps", "plan_log", "arena_terrain", "branch_danger", "key_str"]
