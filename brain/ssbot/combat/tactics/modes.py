"""Tactic modes for one boss fight (DESIGN §3.5.1 L2, §3.5.5, §3.5.6 Bind commit test, §3.7.3 tier restrictions).

    tac = Tactics(load_playbook("BellBeast"))
    prefs = tac.decide(ws, forecast, decision, h)       # every tick, before the planner

Modes:
  HEAL    Q1a (DESIGN §3.7.4, the person's rule of 2026-10-03: h >= 2 below max HP, heal first; the supervisor's
          Restrictions.heal_first): silk >= 9, the supervisor allows BIND and the §3.5.6 commit test passes at the
          hero's position (T_min >= 1.37 + 0.15 s from the forecast's support, HP <= max - 3 or h <= 2, no
          PAUSE_PENDING): the planner gets the Bind macro (its own rollout checks the support and the knockback
          envelope's hazards). Never at h <= 1 (Q1 quits in the post-hit window instead).
  HEAL_SPOT Q1a when the commit test fails only on the place: the nearest verified safe spot of the playbook
          (bind.safe_spots, Playbook.SafeSpot.usable, and the forecast agreeing it is out of reach for a Bind) is the
          stance; the planner walks there under its support check and HEAL takes over once the test passes there.
          No spot (Bell Beast has none: playbook) -> the other modes, i.e. fight on under the supervisor's triggers.
  ENGAGE  the boss is drawn in a punish window of the playbook: the stance is just outside its body on the hero's side,
          where the support's future coverage is lowest, and hits score fully.
  PREPARE the boss is committed to an attack whose punish window is ahead (a leap in its antic or flight, a burst
          underground at a known x): the stance is the playbook's spot in the attack's anchor frame (14 u in front of
          a charge, 12 u along a leap, 10 u beside a burst on the hero's side), pulled to low future coverage.
  EVADE   the support reaches the hero's spot within the evade horizon (0.6 s): the nearest floor spot the support
          leaves free over that horizon, weighed with its later coverage, never within 5 u of a wall unless all else
          is covered (a corner the bell rolls into is no refuge), hits score little.
  HOLD    anything else (the boss underground, the next attack unknown): the playbook's hidden stance, moved by the
          future coverage at 0.15 risk units per u. Underground (the boss not drawn) only the committed part of the
          forecast counts (Forecast.committed: the current attack, tails, armed bells), at 0.5 per u, and it alone
          can call EVADE: the next attack's union covers the whole floor there.
The risk map is the support's coverage of floor positions over the playbook's risk horizon (0.4-2.0 s), earlier times
weighted more; it is the planner's terminal value too (where the horizon ends matters beyond the horizon: a leap's
landing zone is in support from 1.4 s on). YELLOW restricts punishes to one hit (supervisor Restrictions).
"""
import math
from dataclasses import dataclass, field

import numpy as np

from ssbot.combat.forecast import BIN, HIDDEN, Forecast
from ssbot.combat.tactics.playbook import Playbook
from ssbot.core.primitives import Prim
from ssbot.core.worldstate import ORACLE, WorldState
from ssbot.safety.supervisor import BIND_SILK, DELTA_B_S, T_BIND_S, SupervisorDecision, bind_allowed

ENGAGE, EVADE, HEAL, HOLD, PREPARE = "ENGAGE", "EVADE", "HEAL", "HOLD", "PREPARE"
HEAL_SPOT = "HEAL_SPOT"
GRID_U = 0.5
EVADE_S = 0.6
HOLD_PULL = 0.15               # risk units per u away from the playbook's stance (HOLD)
HOLD_PULL_VE = 0.5             # the same underground in the vision view, against the committed threats only
PREP_PULL = 0.12               # risk units per u away from a prepare stance (PREPARE)
WALL_ROOM = 5.0                # prepare stances keep this far from the arena's ends
WALL_PEN = 1.0                 # an evade stance closer to an end than WALL_ROOM costs this (risk units)


@dataclass
class TacticPrefs:
    mode: str
    stance_x: float
    weights: dict[str, float]
    max_hits: int | None = None
    want_bind: bool = False
    bind_why: str = ""
    risk_x: np.ndarray = field(default_factory=lambda: np.zeros(0))
    risk: np.ndarray = field(default_factory=lambda: np.zeros(0))
    boss_x: float | None = None
    t_min: float = math.inf
    horizon_frames: int = 0          # > the planner's T: roll out this long (a committed long attack)

    def risk_at(self, x: np.ndarray) -> np.ndarray:
        if not len(self.risk_x):
            return np.zeros_like(np.asarray(x, np.float64))
        return np.interp(x, self.risk_x, self.risk)


@dataclass
class GoalPrefs(TacticPrefs):
    """The Forum's L2 goal for the fast layer (forum_planner_plan §4.3; GauntletTactics is R6): the goal's name, the
    enemy it is about, a 2D stance region, a hit weight per enemy iid (combat.forum_planner scores every target's hits
    with it; 1 when absent), extra macros and the goal's lifetime. The Bell Beast reads only TacticPrefs' fields. Scores
    only: no field here changes a candidate's S, Hz or U (§4.4 item 2, tests/test_forum_planner.py)."""
    goal: str = "LOCAL"
    target: int | None = None
    region: tuple | None = None          # (x0, x1, y0, y1, contact)
    hit_w: dict = field(default_factory=dict)
    vocab: frozenset = frozenset()
    ttl_s: float = 0.6


class Tactics:
    def __init__(self, pb: Playbook):
        self.pb = pb
        self.hidden_x = pb.hidden_x         # HOLD's stance (PlannerPolicy: pb.hidden_x_vision without a burst cue)
        x0, x1 = pb.arena_x
        self.xs = np.arange(x0, x1 + 1e-9, GRID_U)

    def risk_map(self, f: Forecast, horizon: tuple[float, float] | None = None) -> np.ndarray:
        """[len(xs)]: weighted share of the risk horizon's time bins in which a hurtbox standing on the floor at x is
        in support (weight 1 / (1 + t))."""
        t0, t1 = horizon or self.pb.risk_horizon_s
        tk = np.arange(int(t0 / BIN), int(t1 / BIN) + 1, 2) * BIN
        n = len(self.xs)
        occ = f.occupied(np.repeat(self.xs[:, None], len(tk), 1), np.full((n, len(tk)), self.pb.hero_y), tk)
        w = 1.0 / (1.0 + tk)
        return (occ * w).sum(axis=1) / w.sum()

    def safe_spot(self, f: Forecast, x: float):
        """The nearest usable safe spot of the playbook (Playbook.SafeSpot.usable) where the forecast agrees with the
        coverage map: no support tube reaches a hurtbox standing there within T_bind + delta_b (§3.5.6), else None.
        A spot the forecast covers is not taken on the map's word (the map is a union over recorded fights)."""
        need = T_BIND_S + DELTA_B_S
        for sp in sorted((s for s in self.pb.safe_spots if s.usable), key=lambda s: abs(s.x - x)):
            if f.t_min(sp.x, sp.y, t_max=2.0) >= need:
                return sp
        return None

    def long_horizon(self, f: Forecast, state: str | None) -> int:
        """Frames to roll out through the committed long attack this state is part of (playbook long_horizon: until
        the last listed state ends, at its longest logged dwell, plus extra_s), 0 when none."""
        lh = self.pb.long_horizon
        if not lh or state not in lh["states"] or f.fc.tracker.t_entry is None:
            return 0
        m = f.fc.model
        st = lh["map"].get(state, state)
        t = f.fc.tracker.t_entry - f.origin_t
        for _ in range(8):
            info = m.states.get(st)
            if info is None:
                return 0
            t += info.dwell[1]
            if st == lh["until"] or not info.succ:
                break
            st = max(info.succ, key=lambda x: x[1])[0]
        return int(math.ceil((t + lh["extra_s"]) / BIN)) if t > 0 else 0

    def decide(self, ws: WorldState, f: Forecast, d: SupervisorDecision | None, h: int | None) -> TacticPrefs:
        pb = self.pb
        wts = dict(pb.weights)
        hero = ws.hero.pos.v
        hp, max_hp, silk = ws.res.hp.v, ws.res.hp_max.v, ws.res.silk.v
        risk = self.risk_map(f)
        prefs = TacticPrefs(HOLD, self.hidden_x, wts, risk_x=self.xs, risk=risk)
        if d is not None and d.restrictions.max_punish_hits is not None:
            prefs.max_hits = d.restrictions.max_punish_hits
        box, ok = f.boss_box(np.zeros(1))
        drawn = bool(ok[0])
        if drawn:
            prefs.boss_x = 0.5 * (box[0, 0] + box[0, 2])
        # HEAL (Q1a, DESIGN §3.7.4, the person's rule of 2026-10-03): with h >= 2 below max HP, heal first: the Bind
        # commit test at the hero's position (the Bind roots her there), else a verified safe spot, else fight on.
        # Never at h <= 1: that is Q1's quit in the post-hit window (a model error there is death), and an unknown h
        # (no hero read) is no reason to Bind. h is this tick's (PlannerPolicy: SupervisedControl.h_now), and heal
        # first is Q1a's rule on it (the decision's own flag is a tick old). The playbook's hp_missing_min still gates
        # a Bind without the supervisor (d None: tests, tools)
        bind_ok = d is None or d.allows(Prim.BIND)
        heal_first = d is not None and h is not None and h >= 2 and hp is not None and max_hp is not None \
            and hp < max_hp
        if heal_first and silk is not None and silk < BIND_SILK:
            # gathering silk for the heal (DESIGN §3.7.4 Q6, the person's rule of 2026-10-03: at h 2 fight on with
            # nail hits until the Bind's silk is there): nail hits count more (playbook bind.gather_hit_x; silk skills
            # are already off below full HP, supervisor.silk_spend_allowed)
            wts["hit"] *= pb.bind_gather_hit_x
        if (hp is not None and max_hp and silk is not None and silk >= BIND_SILK and hp < max_hp and bind_ok
                and h is not None and h >= 2 and (heal_first or hp <= max_hp - pb.bind_hp_missing_min)):
            pending = bool(d is not None and d.pause_pending)
            prefs.t_min = f.t_min(hero[0], hero[1], t_max=2.0)
            v = bind_allowed(int(silk), int(hp), int(max_hp), int(h), prefs.t_min, pause_pending=pending)
            prefs.bind_why = v.reason
            if v.ok:
                prefs.mode, prefs.want_bind = HEAL, True
                prefs.stance_x = hero[0]
                return prefs
            spot = self.safe_spot(f, hero[0]) if heal_first and \
                bind_allowed(int(silk), int(hp), int(max_hp), int(h), math.inf, pause_pending=pending).ok else None
            if spot is not None:
                # everything but the place passes: walk to the spot (each step under the planner's support check) and
                # Bind there once the commit test passes at the hero's position
                prefs.mode, prefs.stance_x = HEAL_SPOT, spot.x
                prefs.bind_why = f"{v.reason}; to safe spot {spot.name}"
                wts["hit"] *= 0.3
                return prefs
        state = f.fc.tracker.state
        prefs.horizon_frames = self.long_horizon(f, state)
        punish = state in pb.punish_states or state in pb.punish_phases
        if drawn and punish:
            b0, b1 = box[0, 0], box[0, 2]
            side = -1.0 if hero[0] < 0.5 * (b0 + b1) else 1.0
            x_eng = b0 - pb.engage_reach_u if side < 0 else b1 + pb.engage_reach_u
            cost = risk + 0.3 * np.abs(self.xs - x_eng) / max(1.0, pb.engage_reach_u)
            prefs.mode, prefs.stance_x = ENGAGE, float(self.xs[int(np.argmin(cost))])
            return prefs
        prep = pb.prepare.get(state) if state else None
        anchor = f.fc.tracker.ctx.anchor if f.fc.view == ORACLE else f.fc.tracker.last_anchor
        if prep is not None and anchor is not None:
            # stand where the coming punish window starts (the leap's landing side, beside the burst), in the
            # attack's anchor frame; the support check keeps the hero out of the attack on the way
            xp, side = prep
            m = anchor.mirror if side == "attack" else (1.0 if hero[0] >= anchor.x else -1.0)
            x0, x1 = pb.arena_x
            # never into a corner: an attack bell rolls on into the wall and back (run 20261002_050217, i3 ep1:
            # 10 u beside a burst at x 82.8 was 3 u from the left gate, and the bell trapped the hero there)
            x_prep = min(max(anchor.x + m * xp, x0 + WALL_ROOM), x1 - WALL_ROOM)
            cost = risk + PREP_PULL * np.abs(self.xs - x_prep)
            prefs.mode, prefs.stance_x = PREPARE, float(self.xs[int(np.argmin(cost))])
            return prefs
        pull = HOLD_PULL
        underground = state == HIDDEN if f.fc.view != ORACLE else (state is not None and not f.fc.model.drawn(state))
        if underground:
            # underground the next attack's union covers the whole floor, so evading it or weighing it only moves the
            # hero about; what matters is to be where every branch is reactable when the boss comes up
            # (ssbot.tools.reactability), away from what is already decided (a burst's rolling bells). Vision view,
            # run 20261002_061942: 3 of the first 4 hits were a leap from the near anchor while the hero, evading the
            # union, was still on its way back from a corner after a burst; oracle view, run 20261002_062923 i3 ep2:
            # evading in Submerged kept the hero at x 72, and the leap from the left anchor caught her.
            f = f.committed()
            risk = prefs.risk = self.risk_map(f)
            pull = HOLD_PULL_VE
        soon = f.t_min(hero[0], pb.hero_y, t_max=EVADE_S)
        if soon < EVADE_S:
            # imminent: the nearest floor spot the support leaves free over the evade horizon
            near = self.risk_map(f, (0.0, EVADE_S))
            prefs.mode = EVADE
            # not into a corner: a rolling attack bell runs on into the wall and comes back, so the way out is over
            # it (stage B run 20261002_052118: 5 of 7 hits were such bells, 4 of them within 5 u of a wall; tell
            # experiment 20261002_062635 i2 ep0 the same)
            x0, x1 = pb.arena_x
            wall = ((self.xs < x0 + WALL_ROOM) | (self.xs > x1 - WALL_ROOM)) * WALL_PEN
            prefs.stance_x = float(self.xs[int(np.argmin(near + 0.5 * risk + 0.1 * np.abs(self.xs - hero[0])
                                                         + wall))])
            wts["hit"] *= 0.3
            wts["risk"] *= 2.0
            return prefs
        # the next attack unknown: the playbook's stance, moved only as far as the future coverage is worth (a corner
        # chosen for a slightly lower coverage was where a leap then emerged: run 20261002_042404, i1 ep0)
        cost = risk + pull * np.abs(self.xs - self.hidden_x)
        prefs.stance_x = float(self.xs[int(np.argmin(cost))])
        return prefs
