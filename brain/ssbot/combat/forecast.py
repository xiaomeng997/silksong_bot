"""Threat forecast (M2 W3; DESIGN §3.5.3 support vs probability, §3.5.4 `tubes = forecast(s, H)`, §3.9.2 the
vision-equivalent view): from the WorldState and the boss's knowledge files, where the boss's attacks can be over the
next H seconds.

    fc = Forecaster(BossModel.load("BellBeast"), view=ORACLE)       # or VISION_EQUIVALENT; margin for the hurtbox
    fc.reset(); fc.notify_wake(t_game)                              # every episode; the fight start (bot-observable)
    fc.update(ws)                                                   # every WorldState, in order
    f = fc.forecast(horizon_s=0.8)                                  # origin: ws.stamp.t_game_s
    hit = f.occupied(x, y, tk)                                      # [N, T] bool: hero collider centres at tk s
    p = f.prob(x, y, tk)                                            # [N] probability of contact (scoring only)
    f.support_set(...)                                              # SupportSet for the supervisor (hits_to_death)

Two outputs (§3.5.3). Support, conservative: the union over every branch the behaviour table has ever logged
(support_transitions), every logged dwell (min..max) and every logged instance's colliders, so it must cover every
logged contact; it decides S(c). Probability, for scoring only: each branch weighted by the table's smoothed
transition probabilities (Bell Burst? by fight phase, Rage? by the HP rule), P(c) = sum over leaves of p * contact.

How. The space-time templates of ssbot.knowledge.hitbox_tables are per Control state ("support/<family>/<state>/
<frame>", t from the state's entry; "_tail" from the attack's end, for what outlives it: the attack bells, DropBell
M2), already dilated by the validated contact residual and +-1 bin of export lag; SupportQuery dilates them by the
hero hurtbox plus a margin, so a point test of the hurtbox centre is an overlap test. The forecaster walks the Control
graph from the current state: each state's entry is an interval (the logged dwell min / max of the states before it
accumulate), and the state's template is placed once per 1/60 s bin of that interval (each placement keeps its own
+-1 bin for the export lag). Branches (burst / charge / leap, left / right, rage) are all placed; the walk stops past
the horizon. An attack's anchor is used when it is known (Set L / Set R fixed at x 75.03 / 95.72, the rage at 86.21;
a burst's from the boss's hidden x underground, which is its anchor: live runs 2026-10-02, 81 of 81 bursts and 336 of
336 charges / leaps exactly; in the vision view from its first drawn frame), else the world_all template of the state
(every logged anchor). The horizon is the caller's: at least 0.8 s (the policy asks 2 s: the Bind macro, the tactics'
risk map and the planner's adaptive horizon through a charge).
Tails: an attack that ends into the decision chain leaves the boss underground, so only what outlives it is placed
from its end (attack bells, DropBell M2 in P2); the tail templates also hold the body of instances killed mid-attack,
placed only after a death. A tracker that starts mid-attack (the start state missed) roots the walk in every family
with that state. Drop bells (oracle view): they hang in the export all fight and arm (FSM out of Dormant) at least
1.2 s before they can hurt, so an armed bell gets its own self template at its arming position and time, and the
drop-bell unions of the rage pattern and of P2 (Ptn L / R, Rage End, the M2 world templates) count only from that lead
on (Placement.t_from); a bell seen armed without its arming makes them count from the start again.

Measured (stage A, ssbot.tools.support_recall, 2026-10-02): a held-out behaviour build without live recordings i2_002 /
i3_002 and the trial run (C:/ssbot/data/m2_heldout/tables), contacts of those fights (every "damage" frame and every
frame of a "damage_blocked" stretch) inside the support forecast L frames earlier, box of frame c or c - 1 (the
planner's pairing), margin 0: 35 live fights 23,896 / 23,896 and 2 trial fights 1,795 / 1,795 for L = 2, 3 and 4, in
both views.

Views. ORACLE: the Control FSM state and time in state (Entity.phase, and the FSM_TRANSITION events, which also arrive
while the boss is not exported: before its first emergence). VISION_EQUIVALENT: the observable phase
(ssbot.core.bosses.BELL_BEAST_PHASES) with the time since it changed, the boss's position and facing while drawn, and
memory: "recover" is the end of a charge or of a leap (the phase before it says which), "hidden" after "recover" is
Submerged, after "burst" Burst Recovery (the bells still rolling), after "roar_end" Rage Submerge, and before the first
emergence the wake chain (Submerged Init 2.0 s, then a charge from the right: the first attack of every logged fight).
An observable phase's entry is known to +-1 frame (a transition frame can show the next clip early), a hidden boss's
position is unknown (both charge / leap anchors, the burst's world_all), a burst's anchor comes from the box centre
(fixed offset +-0.539, -2.68 by flipX, on its first drawn frame only: the box follows the sprite frames after it), a
charge's or leap's from its facing.
A boss lost over the image edge (a ghost: no phase) coasts: the last known state stays the root, and its successors
come in as their entry intervals pass.

Time. Templates count game time (1/60 s bins; game time stands still in hit-stop and pauses); offsets are game seconds
from the WorldState's frame (stamp.t_game_s). The planner's rollout frame k is at tk = k * frame_time.
"""
import functools
import json
import math
from pathlib import Path
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace

import numpy as np

from ssbot.combat.boss_model import TAIL, Anchor, BossModel
from ssbot.combat.fastquery import query_par
from ssbot.combat.pogo_targets import TargetTracker, simulate
from ssbot.core.worldstate import ORACLE, VISION_EQUIVALENT, Entity, Ev, WorldState
from ssbot.knowledge import hitbox_tables as hb
from ssbot.safety.hits_to_death import SupportEvent, SupportSet

BIN = hb.BIN_S
MIN_HORIZON_S = 0.8
SUP_HORIZON_S = 0.8          # what the supervisor's support covers (hits_to_death's worst event "now")
VE_ENTRY_SLACK = 1           # bins of slack on an observable phase's entry (a transition frame shows a clip early)
MAX_NODES = 400
HIDDEN, UNKNOWN = "hidden", "unknown"
DROP_BELL = "BoneBeast DropBell"
# the exact path's time slack: a hit lands in the physics step after the recorded position (fixture hit 62131: the bell
# 0.11 u short of the hurtbox in the hit frame's STATE), and hit-stop frames still step (game time vs steps, 0.37 u)
DET_SLACK_S = (-0.04, -0.02, 0.0, 0.02, 0.04)
DET_STATES = frozenset({"Drop", "Air", "Bounce Up", "Bounce Air", "Submerge", "Tink Right", "Tink R Min", "Tink Left",
                        "Tink L Min", "Tink D", "Tink Right 2", "Tink R Min 2", "Tink Left 2", "Tink L Min 2", "Tink D 2"})   # world-fixed hazards with self templates (entities.<tk>.self_template)
REST_STATES = ("Init", "Dormant")
BELL_TTL_S = 8.0                   # a disarmed bell (left the export, back to Dormant) is forgotten after this

# observable phase -> the Control state its first frame is (the root of the forecast walk)
PHASE_ROOT = {"emerge": "Charge Emerge", "charge_antic": "Charge Antic", "charge": "Charge", "leap": "Leap Out",
              "burst": "Burst Out", "roar": "Rage Burst", "roar_end": "Roar End", "burst_tell": "Burst Antic",
              "dust_low": "Emerge Antic C", "dust_tall": "Emerge Antic L", "dust_burst": "Burst Antic"}
PHASE_FAMILY = {"emerge": "BB_CHARGE", "charge_antic": "BB_CHARGE", "charge": "BB_CHARGE", "leap": "BB_LEAP",
                "burst": "BB_BURST", "roar": "BB_RAGE", "roar_end": "BB_RAGE", "burst_tell": "BB_BURST",
                "dust_low": "BB_CHARGE", "dust_tall": "BB_LEAP", "dust_burst": "BB_BURST"}
# Underground cues (ObservabilityFilter tells; hypotheses until M3 measures tell_lead_vision in shadow mode). The
# entity's x is the hidden transform's: the burst anchor (oracle view: 81 of 81 bursts) or the emergence anchor.
# Screenshots C:/ssbot/sandbox/m2_tells (ssbot.probes.m2_tells): nothing at +0.1 s, dust where it will come up from
# +0.3 s after Emerge Antic C / L and Burst Antic; low for a charge, a tall column with debris for a leap, told apart
# for certain at +0.6 s. "dust": at an anchor, charge or leap not yet told; "dust_low" / "dust_tall": a charge / a
# leap; "dust_burst": inside the burst range (bursts erupt at x 81.2-91.2, charges and leaps at the anchors 75.03 /
# 95.72). The antic began TELL_DELAY before the cue, give or take TELL_SLACK_S (when vision would first see it).
# "burst_tell": the burst position from the antic's first frame, the first experiment (run 20261002_061942).
TELL_PHASES = frozenset(("burst_tell", "dust", "dust_low", "dust_tall", "dust_burst"))
EMERGE_TELLS = frozenset(("dust", "dust_low", "dust_tall"))
TELL_DELAY = {"burst_tell": 0.0, "dust": 0.3, "dust_low": 0.6, "dust_tall": 0.6, "dust_burst": 0.3, "bell_dust": 0.3}
TELL_SLACK_S = {"burst_tell": BIN, "dust": 0.1, "dust_low": 0.1, "dust_tall": 0.1, "dust_burst": 0.1,
                "bell_dust": 0.1}
# A drop bell's cue: a narrow dust column from the ceiling at its x, from +0.3 s after it arms (Antic; none at +0.1 s;
# it falls about 1.25 s after arming), screenshots C:/ssbot/sandbox/m2_tells DropBell_*. The vision view places its
# self template from the cue (arming TELL_DELAY earlier, +-TELL_SLACK_S) like the oracle view does from the FSM.
DUST_ROOTS = (("BB_CHARGE", "Emerge Antic C"), ("BB_LEAP", "Emerge Antic L"))
RECOVER_ROOT = {"BB_CHARGE": "Charge End", "BB_LEAP": "Leap Land"}
# the state a hidden phase starts in, by the last drawn family (None: before the first emergence)
HIDE_ROOT = {"BB_CHARGE": "Submerged", "BB_LEAP": "Submerged", "BB_BURST": "Burst Recovery", "BB_RAGE": "Rage Submerge"}


@dataclass(slots=True)
class Ctx:
    """What the walk knows about the attack it is in and the fight."""
    family: str | None = None
    direction: str | None = None       # "Set L" | "Set R" | "-" (first attack) | None
    anchor: Anchor | None = None
    phase: str | None = None           # "P1" | "P2" | None (unknown)
    raged: bool | None = None
    hp: float | None = None


@dataclass(slots=True)
class Node:
    id: int
    state: str
    e_lo: float                        # entry interval, game s from the origin
    e_hi: float
    family: str | None
    p: float                           # probability of the path to here
    parent: int
    anchor: Anchor | None = None


@dataclass(slots=True)
class Placement:
    key: str
    t_ref: float                       # template time at the origin
    anchor: tuple[float, float] | None
    mirror: int
    node: int
    t_on: float                        # active interval relative to the origin
    t_off: float
    sources: frozenset[str]
    t_from: float = -math.inf          # ignored for query times before this (drop-bell unions, see Forecaster)


@dataclass(slots=True)
class Root:
    state: str
    e_lo: float
    e_hi: float
    ctx: Ctx
    p: float = 1.0
    current: bool = False              # the state is known to be the current one (its exit is after the origin)


class Forecast:
    """One tick's tubes. Placements are SupportQuery placements of planner templates; nodes the walk's tree."""

    def __init__(self, fc: "Forecaster", origin_t: float, horizon: float, nodes: list[Node],
                 placements: list[Placement], known: bool, roots: list[Root], boss: Entity | None):
        self.fc = fc
        self.origin_t = origin_t
        self.horizon = horizon
        self.nodes = nodes
        self.placements = placements
        self.known = known
        self.roots = roots
        self.boss = boss
        self.det: list = []           # drop bells on exact paths (Forecaster._det_bell)
        kids = {}
        for n in nodes:
            kids.setdefault(n.parent, []).append(n.id)
        self.leaves = [n.id for n in nodes if n.id not in kids]

    # ---- queries ------------------------------------------------------------------------------------------------

    def _query(self, placements: Iterable[Placement], comfort: bool = False) -> hb.SupportQuery:
        q = self.fc.query_c if comfort and self.fc.query_c is not None else self.fc.query
        q.clear()
        for p in placements:
            q.place(p.key, p.t_ref, p.anchor, p.mirror)
        return q

    def _occ(self, placements: list[Placement], x, y, tk: np.ndarray, comfort: bool = False) -> np.ndarray:
        x = np.asarray(x, np.float64)
        y = np.asarray(y, np.float64)
        out = np.zeros(x.shape, bool)
        cuts = sorted({p.t_from for p in placements if tk[0] < p.t_from <= tk[-1]})
        edges = [-math.inf] + cuts + [math.inf]
        for a, b in zip(edges, edges[1:]):
            sel = np.flatnonzero((tk >= a) & (tk < b))
            if not len(sel):
                continue
            t_lo, t_hi = tk[sel[0]], tk[sel[-1]]
            act = [p for p in placements if p.t_from <= t_lo and p.t_off >= t_lo - BIN and p.t_on <= t_hi + BIN]
            if not act:
                continue
            q = self._query(act, comfort)
            xs, ys, ts = x[:, sel], y[:, sel], tk[sel]
            out[:, sel] = query_par(q, xs, ys, ts)
        return out

    def occupied(self, x, y, tk, comfort: bool = False) -> np.ndarray:
        """[N, T] bool: the hurtbox (grown by the forecaster's margin) centred at (x, y) [N, T] at tk [T] game s from
        the origin overlaps some support tube. comfort: against the templates grown by the comfort margin too (the
        planner's preference for clearance; Forecaster(comfort=...))."""
        tk = np.asarray(tk, np.float64)
        out = self._occ(self.placements, x, y, tk, comfort)
        if self.det:
            out |= self._det_occ(np.asarray(x, np.float64), np.asarray(y, np.float64), tk, comfort)
        return out

    def _det_occ(self, x, y, tk: np.ndarray, comfort: bool = False, exclude: str | None = None) -> np.ndarray:
        """Contact with the drop bells on exact paths (Forecaster._det_bell): the hurtbox grown like the templates'
        dilation (comfort: and the comfort margin) meets the bell's circle on either bounce branch."""
        out = np.zeros(np.shape(x), bool)
        hx, hy = self.fc.half
        if comfort and self.fc.comfort is not None:
            hx, hy = hx + self.fc.comfort[0], hy + self.fc.comfort[1]
        for sp, bx, by, vx, vy, nb, rest, tk_ in self.det:
            if exclude is not None and tk_.endswith(exclude):
                continue
            sides = (1, -1) if nb < len(sp.bounces) and sp.bounces[nb].get("vx") == "random" else (0,)
            for sd in sides:
                for dt in DET_SLACK_S:
                    t = np.maximum(tk + dt, 0.0)
                    if rest is not None:
                        cx, cy = np.full(len(tk), bx), np.full(len(tk), by)
                        ok = t <= rest
                    else:
                        cx, cy, ok = simulate(sp, bx, by, vx, vy, nb, None, t, side=sd)
                    dx = np.maximum(np.abs(x - cx) - hx, 0.0)
                    dy = np.maximum(np.abs(y - cy) - hy, 0.0)
                    out |= ((dx * dx + dy * dy) <= sp.r * sp.r) & ok
        return out

    def occupied_without(self, x, y, tk, exclude: str) -> np.ndarray:
        """occupied() without the placements whose only source is the entity type `exclude` (a bell disarmed by a
        down attack: its DamageHero cooldown; a placement shared with other sources still counts)."""
        pl = [p for p in self.placements if not (p.sources and all(src.endswith(exclude) for src in p.sources))]
        tk = np.asarray(tk, np.float64)
        out = self._occ(pl, x, y, tk)
        if self.det:
            out |= self._det_occ(np.asarray(x, np.float64), np.asarray(y, np.float64), tk, exclude=exclude)
        return out

    def node_hits(self, x, y, tk) -> np.ndarray:
        """[nodes, N] bool: contact with each node's own placements."""
        x = np.asarray(x, np.float64)
        tk = np.asarray(tk, np.float64)
        out = np.zeros((len(self.nodes), x.shape[0]), bool)
        by_node: dict[int, list[Placement]] = {}
        for p in self.placements:
            by_node.setdefault(p.node, []).append(p)
        for nid, ps in by_node.items():
            out[nid] = self._occ(ps, x, y, tk).any(axis=1)
        return out

    def prob(self, x, y, tk) -> np.ndarray:
        """[N]: sum over the walk's leaves of p(leaf) * (contact with a placement on its path); scoring only."""
        x = np.asarray(x, np.float64)
        nh = self.node_hits(x, y, tk)
        p = np.zeros(x.shape[0])
        parent = {n.id: n.parent for n in self.nodes}
        for leaf in self.leaves:
            hit = np.zeros(x.shape[0], bool)
            nid = leaf
            while nid >= 0:
                hit |= nh[nid]
                nid = parent[nid]
            p += self.nodes[leaf].p * hit
        return np.minimum(p, 1.0)

    def t_min(self, x: float, y: float, t_max: float = 3.0) -> float:
        """Earliest game time (s from the origin) at which a support tube reaches a hurtbox standing at (x, y);
        inf when none does within t_max (the Bind commit test's T_min, §3.5.6)."""
        tk = np.arange(0, int(t_max / BIN) + 1) * BIN
        hit = self.occupied(np.full((1, len(tk)), x), np.full((1, len(tk)), y), tk)[0]
        i = np.flatnonzero(hit)
        return float(tk[i[0]]) if len(i) else math.inf

    def committed(self) -> "Forecast":
        """The same forecast restricted to what is already decided: the current attack up to the next decision
        state, its tail, ended attacks' tails and armed bells (scoring and tactics only; the support is all of it).
        In the vision view underground, the next attack's union covers the whole floor; this part does not."""
        dec = set(self.fc.model.decision_states)
        pre: dict[int, bool] = {}
        for n in self.nodes:                    # the walk appends a parent before its children
            pre[n.id] = (n.parent < 0 or pre.get(n.parent, False)) and n.state not in dec
        kept = [p for p in self.placements if pre.get(p.node, False)]
        return Forecast(self.fc, self.origin_t, self.horizon, self.nodes, kept, self.known, self.roots, self.boss)

    def active_sources(self, t0: float = 0.0, t1: float = SUP_HORIZON_S) -> frozenset[str]:
        out: set[str] = set()
        for p in self.placements:
            if p.t_off >= t0 and max(p.t_on, p.t_from) <= t1:
                out |= p.sources
        return frozenset(out)

    def support_set(self, ws: WorldState | None = None, t1: float = SUP_HORIZON_S) -> SupportSet:
        """The supervisor's support (hits_to_death events): one event per threat instance in support within t1, the
        boss's iid for the boss, a visible entity's iid for a bell, else its type key; plus every visible entity with
        an active damage box the walk does not explain. Certified (known) only when the tracker is."""
        m = self.fc.model
        dmg = max(f.damage for f in m.families.values())
        hazard = any(f.hazard for f in m.families.values())
        by_type: dict[str, int] = {}
        if ws is not None:
            for e in ws.entities:
                by_type.setdefault(e.type_key.v, e.id)
        srcs = self.active_sources(0.0, t1)
        events = []
        for s in sorted(srcs):
            iid = self.fc.tracker.iid if s == m.boss_type else by_type.get(s)
            events.append(SupportEvent(s, dmg, hazard=hazard, instance=iid))
        if ws is not None:
            for e in ws.entities:
                if e.type_key.v in srcs or e.id == self.fc.tracker.iid:
                    continue
                if any(b.active for b in e.dmg_boxes):
                    events.append(SupportEvent(e.type_key.v or "entity", dmg, instance=e.id))
        return SupportSet(tuple(events), self.known, certified_empty=self.known and not events)

    # ---- J helpers ----------------------------------------------------------------------------------------------

    def _hurt_box(self) -> tuple[float, float, float, float] | None:
        """The boss's hittable box now: its enabled colliders (oracle view), or in the vision view the hurtbox table's
        median box for the observable phase and its time (ssbot.tools.hurtbox_table) at the observed position, the
        sprite's render box only where the table has nothing."""
        b = self.boss
        if b is None:
            return None
        tab = self.fc.hurtbox
        st = self.fc.tracker.state
        if self.fc.view != ORACLE and tab and st in tab and self.fc.tracker.t_entry is not None:
            bins = tab[st]
            k = str(min(int(max(0.0, self.origin_t - self.fc.tracker.t_entry) / 0.1), max(int(x) for x in bins)))
            m = (bins.get(k) or bins[min(bins, key=lambda x: abs(int(x) - int(k)))])["median"]
            x0, y0, x1, y1 = m
            if b.flip_x:
                x0, x1 = -x1, -x0
            px, py = b.pos.v
            return px + x0, py + y0, px + x1, py + y1
        return _body_box(b)

    def _table_entry(self) -> dict | None:
        tab, st = self.fc.hurtbox, self.fc.tracker.state
        if self.fc.view == ORACLE or not tab or st not in tab or self.fc.tracker.t_entry is None:
            return None
        bins = tab[st]
        k = str(min(int(max(0.0, self.origin_t - self.fc.tracker.t_entry) / 0.1), max(int(x) for x in bins)))
        return bins.get(k) or bins[min(bins, key=lambda x: abs(int(x) - int(k)))]

    def body_polys(self) -> tuple[np.ndarray, np.ndarray]:
        """body_shape of the boss, or in the vision view the hurtbox table's polygon (else its box) for the phase
        at the observed position, mirrored with the sprite (scoring)."""
        ent = self._table_entry()
        if ent is not None and ent.get("poly") and self.boss is not None:
            q = np.asarray(ent["poly"], np.float64)
            if self.boss.flip_x:
                q = q * (-1.0, 1.0)
            q = q + self.boss.pos.v
            return q, np.array([0, len(q)], np.int64)
        if self.fc.view != ORACLE and self.fc.hurtbox:
            bb = self._hurt_box()
            if bb is not None:
                x0, y0, x1, y1 = bb
                return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], np.float64), np.array([0, 4], np.int64)
        return body_shape(self.boss)

    def target_paths(self, tk: np.ndarray) -> list:
        """Registry targets (pogo_targets: bells) on their predicted paths, tk seconds from the observation."""
        ws = self.fc._ws
        return self.fc.targets.paths(ws, tk) if ws is not None else []

    def boss_box(self, tk: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Nominal boss hurtbox [T, 4] (x0, y0, x1, y1) and hittable [T] along the most likely path (scoring only):
        the current body box moved along the family's logged mean path, hittable while the boss stays drawn."""
        tk = np.asarray(tk, np.float64)
        box = np.zeros((len(tk), 4))
        ok = np.zeros(len(tk), bool)
        tr = self.fc.tracker
        b = self.boss
        if b is None or b.hidden or b.visible_frac <= 0.0 and self.fc.view != ORACLE:
            return box, ok
        bb = self._hurt_box()
        if bb is None:
            return box, ok
        box[:] = bb
        t_left = tr.drawn_left(self.origin_t)
        ok[:] = tk <= t_left
        if tr.state in self.fc.no_hurtbox:
            # no hurtbox while the boss stays in this state (its longest logged dwell), not over the whole horizon: the
            # charge that follows the antic is hittable, and a pogo planned in the antic must see it (spike_audit on
            # gate chunk 20261002_123347: no pogo plan was ever offered in Charge Emerge / Charge Antic)
            st = PHASE_ROOT.get(tr.state, tr.state)
            info = self.fc.model.states.get(st)
            if info is None or tr.t_entry is None:
                ok[:] = False
            else:
                ok[tk < tr.t_entry + info.dwell[1] - self.origin_t] = False
        # the vision view's tracker keeps the attack in last_family / last_anchor (ctx is the oracle's): without them
        # the box stood still while the boss moved (stage C run 20261002_093052, predict_audit: boss centre 7.3 u off
        # at +0.5 s for side slashes, 9.4 u at a down spike's active frame)
        fam = tr.ctx.family if self.fc.view == ORACLE else tr.last_family
        anchor = tr.ctx.anchor if self.fc.view == ORACLE else (tr.fit_anchor or tr.last_anchor)
        f = self.fc.model.families.get(fam) if fam else None
        if f is not None and f.path is not None and tr.t_start is not None and anchor is not None:
            t_att = self.origin_t - tr.t_start
            path = f.path
            xs = np.interp(t_att + tk, path[:, 0], path[:, 6])
            ys = np.interp(t_att + tk, path[:, 0], path[:, 7])
            x0 = np.interp(t_att, path[:, 0], path[:, 6])
            y0 = np.interp(t_att, path[:, 0], path[:, 7])
            m = anchor.mirror
            box[:, [0, 2]] += (m * (xs - x0))[:, None]
            box[:, [1, 3]] += (ys - y0)[:, None]
        return box, ok


def body_shape(e: Entity | None) -> tuple[np.ndarray, np.ndarray]:
    """The boss's enabled collider polygons as flat vertices [V, 2] and starts [P + 1] (scoring: nail hits land on
    them). During an attack the root box is disabled and the attack polygon takes the hits (live run 20261002_064001:
    Leap Out / Descending have only LeapCollider enabled, a 9-vertex shape whose box is 11.7 x 3.8 u, the root box
    2.2 x 1.8 u disabled; Charge only PolyCollider); its bounding box credited side, up and down slashes alike, while
    side slashes in Leap Out hit 6 times of 56. Vision view: the render box as a rectangle."""
    polys = [np.asarray(p, np.float64).reshape(-1, 2) for p in (e.body_polys if e is not None else ()) if len(p) >= 3]
    if not polys:
        return np.zeros((0, 2)), np.zeros(1, np.int64)
    starts = np.zeros(len(polys) + 1, np.int64)
    starts[1:] = np.cumsum([len(q) for q in polys])
    return np.concatenate(polys), starts


def _body_box(e: Entity) -> tuple[float, float, float, float] | None:
    if e.body_polys:
        p = np.concatenate([np.asarray(q, np.float64).reshape(-1, 2) for q in e.body_polys])
        return float(p[:, 0].min()), float(p[:, 1].min()), float(p[:, 0].max()), float(p[:, 1].max())
    if e.render_box is not None:
        return e.render_box
    return None


class BossTracker:
    """The boss's state as the view can know it. ORACLE: Control state, entry time, attack start, direction, anchor
    (transform at the first drawn frame of the attack, or the fixed one). VISION_EQUIVALENT: observable phase and its
    entry, memory of the last drawn family / anchor, hide time, burst anchor from the box centre."""

    def __init__(self, model: BossModel, view: str):
        self.model = model
        self.view = view
        self.reset()

    def reset(self) -> None:
        self.state: str | None = None          # ORACLE: Control state; VE: observable phase
        self.t_entry: float | None = None      # game time the state / phase began
        self.t_start: float | None = None      # game time the current attack began (ORACLE; VE estimate)
        self.ctx = Ctx(phase=self.model.initial_phase, raged=False)
        self.iid: int | None = None
        self.seen = False                      # the boss was drawn at least once
        self.t_wake: float | None = None
        self.dead = False
        self.last_family: str | None = None    # VE: family of the last drawn phase
        self.last_anchor: Anchor | None = None
        self.t_hide: float | None = None
        self.tell_dir: str | None = None       # VE: the anchor side of the last emergence dust
        self.fit = getattr(self, "fit", None)  # VE: AttackFit for committed attacks (kept across resets)
        if self.fit is not None:
            self.fit.reset()
        self.fit_ok = False
        self.fit_anchor: Anchor | None = None
        self.fit_anomalies = 0
        self._t_start0: float | None = None
        self.coasting = False                  # VE: no phase this frame (a ghost)
        self._anchor_sum: list[float] = []
        self.t = 0.0
        self.hidden_x: dict[str, float] = {}   # ORACLE: the hidden boss's x per state of this attack (anchor check)
        self.ends: list[tuple] = []   # last attacks' ends: (family, anchor, t_end lo, t_end hi, phase, by a death):
        #                               their tails (bells; the body too when the boss died mid-attack) outlive them
        self._drawn_anchor: tuple | None = None
        self.n_attacks = 0
        self.bells: dict[int, tuple[str, float, tuple[float, float]]] = {}   # ORACLE: armed drop bells: (type,
        #                                                                    arm time, arm position)
        self.bells_unknown = False             # an armed drop bell whose arming was not seen
        self._cued: set[int] = set()           # VE: drop bells with their cue in the last frame
        self.anchor_log: list[tuple[str, float, float]] = []   # ORACLE: (family, hidden x, drawn transform x)

    # ---- ORACLE -------------------------------------------------------------------------------------------------

    def _enter(self, state: str, t: float) -> None:
        m = self.model
        prev = self.state
        self.state, self.t_entry = state, t
        if state in m.death_states:
            if self.ctx.family is not None and not self.dead:     # the bells of a killed attack roll on: its tail
                self._ended(self.ctx.family, self.ctx.anchor, t, t, death=True)
            self.dead = True
            return
        if state == "Submerged Init":
            self.ctx.direction = "-"
            self.t_wake = self.t_wake if self.t_wake is not None else t
        if state in m.dir_states:
            self.ctx.direction = state
        if state in m.attack_starts:
            fam = m.attack_starts[state]
            if self.ctx.direction is None and self.n_attacks == 0 and self.t_wake is not None:
                self.ctx.direction = "-"          # the first attack after the wake (its Set state came before us)
            self.ctx.family = fam
            self.ctx.anchor = m.anchor(fam, self.ctx.direction)
            self.t_start = t
            self.hidden_x = {}
            self.n_attacks += 1
        elif state in m.decision_states and prev is not None and prev not in m.decision_states:
            if self.ctx.family is not None:
                self._ended(self.ctx.family, self.ctx.anchor, t, t)
            self.ctx.family, self.ctx.anchor, self.t_start = None, None, None
            if state == "Submerged":
                self.ctx.direction = None
        if state == "Rage Pos":
            self.ctx.raged = True
        if state in m.phase_marks:
            self.ctx.phase = m.phase_marks[state]

    def _ended(self, family: str, anchor: Anchor | None, t_lo: float, t_hi: float, death: bool = False) -> None:
        self.ends = (self.ends + [(family, anchor, t_lo, t_hi, self.ctx.phase, death)])[-2:]

    def update(self, ws: WorldState) -> Entity | None:
        m = self.model
        t = ws.stamp.t_game_s
        self.t = t
        boss = next((e for e in ws.entities if e.type_key.v == m.boss_type), None)
        if boss is not None:
            self.iid = boss.id
            if boss.hp_est is not None:
                self.ctx.hp = boss.hp_est.v
        for ev in ws.events:
            if (ev.kind == Ev.ENEMY_KILLED and ev.data is not None and ev.data.type_key == m.boss_type
                    and not self.dead):
                if self.view == ORACLE and self.ctx.family is not None:
                    self._ended(self.ctx.family, self.ctx.anchor, ev.t_game_s, ev.t_game_s, death=True)
                elif self.view != ORACLE and self.state not in (None, HIDDEN) and self.last_family is not None:
                    self._ended(self.last_family, self.last_anchor, ev.t_game_s - BIN, ev.t_game_s + BIN,
                                death=True)
                self.dead = True
        if self.view == ORACLE:
            self._update_oracle(ws, boss, t)
        else:
            self._update_ve(ws, boss, t)
        return boss

    def _update_oracle(self, ws: WorldState, boss: Entity | None, t: float) -> None:
        m = self.model
        for ev in ws.events:
            d = ev.data
            if ev.kind == Ev.FSM_TRANSITION and d is not None and d.fsm == m.control_fsm and d.to_state \
                    and str(d.type_key or "").startswith(m.boss_type):
                if d.from_state in ("Dormant", "Init") and self.t_wake is None:
                    self.t_wake = ev.t_game_s
                self._enter(d.to_state, ev.t_game_s)
        self._bells(ws, t)
        if boss is None:
            return
        if boss.phase is not None and boss.phase.top:
            st, tau = boss.phase.top, boss.phase.t_in_phase
            if st != self.state:
                self._enter(st, t - tau)
            else:
                self.t_entry = t - tau
        if boss.hidden:
            fam = self.ctx.family
            if fam is not None:
                self.hidden_x[self.state or ""] = boss.pos.v[0]
                f = m.families[fam]
                # the burst's x is set underground at Burst Pos and the boss erupts there: the hidden x is the
                # anchor (live runs 2026-10-02: 81 of 81 bursts exactly, and 336 of 336 charges / leaps at their
                # fixed anchors), known 1.2 s before the eruption
                if self.ctx.anchor is None and not f.directed and f.anchor_y is not None and self.state != f.start:
                    self.ctx.anchor = Anchor(float(boss.pos.v[0]), f.anchor_y, f.mirror)
            return
        self.seen = True
        fam = self.ctx.family
        # A variable anchor (the burst) is the transform at the attack's first drawn frame (behaviour_tables' anchor
        # definition; the burst's transform does not move while drawn). Fixed anchors stay: a tracker that starts in
        # the middle of a charge would otherwise anchor on a moving transform.
        if fam is not None and boss.pos_transform is not None and self._drawn_anchor != (fam, self.t_start):
            self._drawn_anchor = (fam, self.t_start)
            ax, ay = boss.pos_transform
            hx = next(iter(self.hidden_x.values()), math.nan)
            self.anchor_log.append((fam, hx, float(ax)))
            f = m.families[fam]
            if f.directed and self.ctx.anchor is None:
                # direction missed (the tracker started after the Set state): the facing tells it (Set L flipX
                # False, Set R True in every logged instance)
                self.ctx.anchor = m.anchor(fam, "Set R" if boss.flip_x else "Set L")
            elif m.anchor(fam, self.ctx.direction) is None and not f.directed:
                self.ctx.anchor = Anchor(float(ax), float(ay), f.mirror)

    def _bells(self, ws: WorldState, t: float) -> None:
        """ORACLE: drop bells hang in the export all fight (FSM Dormant) and arm (leave Dormant: Antic, the shake)
        about 1.2 s before they can hurt (self templates start 1.217 s after arming). Arm time and position (the
        transform: they hang still while shaking) make their self template placeable."""
        seen = set()
        unknown = False
        for e in ws.entities:
            tk = e.type_key.v
            if not tk.startswith(DROP_BELL) or not e.fsm:
                continue
            st, tau = e.fsm[0][1], e.fsm[0][2]
            if st in REST_STATES:
                self.bells.pop(e.id, None)     # disarmed: the same bell object re-arms for a later drop
                continue
            seen.add(e.id)
            if e.id not in self.bells:
                if st == "Antic" and e.pos_transform is not None:
                    self.bells[e.id] = (tk, t - tau, (float(e.pos_transform[0]), float(e.pos_transform[1])))
                else:
                    unknown = True
        for iid in [i for i in self.bells if i not in seen]:
            if t - self.bells[iid][1] > BELL_TTL_S:
                del self.bells[iid]
        self.bells_unknown = unknown

    # ---- VISION_EQUIVALENT ----------------------------------------------------------------------------------------

    def _bells_ve(self, ws: WorldState, t: float) -> None:
        """VE with the bell cue (ObservabilityFilter tells, phase "bell_dust"): arming time from the cue."""
        cued = set()
        for e in ws.entities:
            if not e.type_key.v.startswith(DROP_BELL) or e.phase is None or e.phase.top != "bell_dust":
                continue
            cued.add(e.id)
            if e.id not in self._cued:             # a new cue: this bell (re-)armed
                t_arm = t - e.phase.t_in_phase - TELL_DELAY["bell_dust"]
                self.bells[e.id] = (e.type_key.v, t_arm, (float(e.pos.v[0]), float(e.pos.v[1])))
        self._cued = cued
        for iid in [i for i in self.bells if i not in cued]:
            if t - self.bells[iid][1] > BELL_TTL_S:
                del self.bells[iid]

    def _update_ve(self, ws: WorldState, boss: Entity | None, t: float) -> None:
        m = self.model
        self._bells_ve(ws, t)
        self.coasting = boss is None or boss.phase is None or boss.phase.top == UNKNOWN
        if boss is None or boss.phase is None:
            return
        ph, tau = boss.phase.top, boss.phase.t_in_phase
        if ph == UNKNOWN:
            return
        if ph != self.state:
            prev = self.state
            self.state, self.t_entry = ph, t - tau
            if ph == HIDDEN:
                self.t_hide = t - tau
                if prev == "roar":
                    self.last_family = "BB_RAGE"
                if prev == "recover" and self.last_family in RECOVER_ROOT:
                    self._ended(self.last_family, self.last_anchor, self.t_hide - VE_ENTRY_SLACK * BIN,
                                self.t_hide + VE_ENTRY_SLACK * BIN)
            else:
                fam = PHASE_FAMILY.get(ph)
                if ph == "recover":
                    fam = self.last_family if self.last_family in RECOVER_ROOT else None
                if fam is not None and fam != self.last_family or ph in ("emerge", "leap", "burst", "roar",
                                                                         *TELL_PHASES) \
                        and prev in (HIDDEN, None, "recover", "roar_end"):
                    self._anchor_sum = []
                    self.last_anchor = None
                    self.t_start = None
                    self._t_start0, self.fit_ok, self.fit_anchor = None, False, None
                self.last_family = fam if fam is not None else (None if ph == "dust" else self.last_family)
                if ph == "roar":
                    self.ctx.raged = True
                if ph == "roar_end":
                    self.ctx.phase = "P2"      # the drop-bell pattern follows; P2 from its end
        if ph == HIDDEN:
            return
        self.seen = True
        if ph in EMERGE_TELLS and boss.pos.conf > 0:
            xl, xr = m.anchor("BB_CHARGE", "Set L").x, m.anchor("BB_CHARGE", "Set R").x
            self.tell_dir = "Set L" if boss.pos.v[0] < 0.5 * (xl + xr) else "Set R"
            if ph == "dust":
                self.last_anchor = m.anchor("BB_CHARGE", self.tell_dir)     # charge and leap share the anchors
                return
        fam = self.last_family
        if fam is None:
            return
        f = m.families[fam]
        root = PHASE_ROOT.get(ph)
        if self.t_start is None and root in f.entry:
            # the attack began this long before the phase's first state (the family's logged entry offsets): the
            # boss box then moves along the family's mean path for scoring (Forecast.boss_box)
            self.t_start = t - tau - TELL_DELAY.get(ph, 0.0) - f.entry[root][0]
            self._t_start0 = self.t_start
        if fam == "BB_BURST":
            # set once per burst and kept to its end (an earlier version fell through to the family's named anchor,
            # which a burst has none of, from the second drawn frame on: the whole burst range for the rest of the
            # burst, FORCED_RISK in every stage C burst, run 20261002_060151)
            if boss.pos.conf > 0 and not self._anchor_sum:
                if ph in TELL_PHASES:
                    self._anchor_sum.append(boss.pos.v[0])
                else:
                    # the box follows the sprite frame (live i2_002 f605393-605452: box centre x 89.93 -> 91.57 while
                    # the transform stays at 90.47), so only the first drawn frame has the behaviour table's offset
                    self._anchor_sum.append(boss.pos.v[0] - f.box_offset.get(bool(boss.flip_x), (0.0, 0.0))[0])
                y = f.anchor_y if f.anchor_y is not None else boss.pos.v[1] + 2.68
                self.last_anchor = Anchor(float(self._anchor_sum[0]), y, 1)
        elif f.directed:
            told = ph in TELL_PHASES and self.tell_dir is not None
            base = m.anchor(fam, self.tell_dir if told else ("Set R" if boss.flip_x else "Set L"))
            self.last_anchor = base
            if self.fit is not None and ph not in TELL_PHASES and boss.pos.conf > 0 and self.t_start is not None:
                # multi-frame fusion (combat.attack_fit): the committed attack's template fitted to every frame seen
                # since it came up; a rejected fit keeps the phase-level estimate (broad support) and flags it
                self.fit.start(fam, base, self._t_start0 if self._t_start0 is not None else self.t_start)
                self.fit.observe(t, float(boss.pos.v[0]), float(boss.pos.v[1]))
                r = self.fit.result()
                self.fit_ok = bool(r is not None and r.ok)
                if r is not None and not r.ok:
                    self.fit_anomalies += 1
                if self.fit_ok:
                    # scoring only (Forecast.boss_box): moving the support's anchor by the fit lost 3.3 % of the
                    # held-out contacts (support_recall ve / ve_dust 23,117 of 23,896, emerge / charge body)
                    self.t_start = r.t_start
                    self.fit_anchor = Anchor(base.x + r.dx, base.y, base.mirror)
        else:
            self.last_anchor = m.anchor(fam, None)

    # ---- roots ----------------------------------------------------------------------------------------------------

    def roots(self, origin_t: float) -> tuple[list[Root], bool]:
        """Where the walk starts: [(state, entry interval relative to the origin, context, p)] and whether the view
        certifies it (False: nothing known about the boss)."""
        if self.dead:
            return [], True
        if self.view == ORACLE:
            return self._roots_oracle(origin_t)
        return self._roots_ve(origin_t)

    def _wake_root(self, origin_t: float) -> list[Root]:
        if self.t_wake is None:
            return []
        e = self.t_wake - origin_t
        # the wake comes from the episode's frame count (+-2 bins: game time and frames part in a hit-stop)
        return [Root("Submerged Init", e - 2 * BIN, e + 2 * BIN,
                     Ctx(direction="-", phase="P1", raged=False, hp=self.ctx.hp))]

    def _roots_oracle(self, origin_t: float) -> tuple[list[Root], bool]:
        if self.state is None or self.t_entry is None:
            r = self._wake_root(origin_t)
            return r, bool(r)
        e = self.t_entry - origin_t
        ctx = replace(self.ctx)
        fams = [f.name for f in self.model.families.values() if self.state in f.states]
        if ctx.family is None and fams:
            # the attack's start was missed (the tracker began mid-attack): every family with this state, its fixed
            # anchor when it has one, else world_all
            return [Root(self.state, e, e, replace(ctx, family=fam, anchor=self.model.anchor(fam, ctx.direction)),
                         1.0 / len(fams), current=True) for fam in fams], True
        return [Root(self.state, e, e, ctx, current=True)], True

    def _roots_ve(self, origin_t: float) -> tuple[list[Root], bool]:
        m = self.model
        base = Ctx(phase=self.ctx.phase, raged=self.ctx.raged, hp=self.ctx.hp)
        if self.state is None or self.t_entry is None:
            r = self._wake_root(origin_t)
            return r, bool(r)
        e = self.t_entry - origin_t
        lo, hi = e - VE_ENTRY_SLACK * BIN, e + VE_ENTRY_SLACK * BIN
        if self.state == HIDDEN:
            if not self.seen:
                r = self._wake_root(origin_t)
                return r, bool(r)
            fam = self.last_family
            states = [HIDE_ROOT[fam]] if fam in HIDE_ROOT else sorted(set(HIDE_ROOT.values()))
            out = []
            for st in states:
                ctx = replace(base)
                if st != "Submerged":
                    ctx.family = "BB_BURST" if st == "Burst Recovery" else "BB_RAGE"
                    ctx.anchor = self.last_anchor if self.last_family == ctx.family else m.anchor(ctx.family, None)
                out.append(Root(st, lo, hi, ctx, 1.0 / len(states)))
            return out, True
        fam = self.last_family
        if self.state == "recover":
            fams = [fam] if fam in RECOVER_ROOT else list(RECOVER_ROOT)
            out = []
            for f in fams:
                ctx = replace(base, family=f, anchor=self.last_anchor if f == fam else None)
                out.append(Root(RECOVER_ROOT[f], lo, hi, ctx, 1.0 / len(fams)))
            return out, True
        direction = None
        if self.state in TELL_PHASES:
            d, sl = TELL_DELAY[self.state], TELL_SLACK_S[self.state]
            lo, hi = e - d - sl, e - d + sl
            if self.state in EMERGE_TELLS:
                direction = self.tell_dir
            if self.state == "dust":
                return [Root(st, lo, hi, replace(base, family=f, direction=direction, anchor=m.anchor(f, direction)),
                             1.0 / len(DUST_ROOTS)) for f, st in DUST_ROOTS], True
        st = PHASE_ROOT.get(self.state)
        if st is None:
            return [], False
        fam_r = PHASE_FAMILY[self.state]
        ctx = replace(base, family=fam_r, anchor=self.last_anchor, direction=direction)
        return [Root(st, lo, hi, ctx)], True

    def drawn_left(self, origin_t: float) -> float:
        """Game s the boss stays drawn from the origin along the shortest logged dwells (scoring only)."""
        m = self.model
        if self.state is None or self.t_entry is None:
            return 0.0
        st = self.state if self.view == ORACLE else (
            RECOVER_ROOT.get(self.last_family or "", "Charge End") if self.state == "recover"
            else PHASE_ROOT.get(self.state))
        if st is None or not m.drawn(st):
            return 0.0
        t = self.t_entry - origin_t
        for _ in range(12):
            info = m.states.get(st)
            if info is None or not m.drawn(st):
                break
            t += info.dwell[0]
            if not info.succ:
                break
            st = max(info.succ, key=lambda x: x[1])[0]
        return max(0.0, t)


class Forecaster:
    """Tracker + walk + one SupportQuery over the planner templates (packed once; about 2 s and 0.2-0.3 GB for the
    Bell Beast per-state templates)."""

    def __init__(self, model: BossModel, view: str = ORACLE, margin: float | tuple[float, float] = 0.0,
                 templates: dict[str, hb.SpaceTimeTemplate] | None = None, npz: str | None = None,
                 comfort: float | tuple[float, float] | None = None,
                 comfort_templates: dict[str, hb.SpaceTimeTemplate] | None = None):
        if view not in (ORACLE, VISION_EQUIVALENT):
            raise ValueError(view)
        self.model = model
        self.view = view
        self.margin = margin_xy(margin)
        if templates is None:
            templates = load_planner_templates(model, self.margin, npz)
        self.templates = templates
        self.meta = {k: (t.t0, t.t1) for k, t in templates.items()}
        # half-extents of the box a point test covers (the templates' dilation)
        self.half = (hb.HERO_HALF_U[0] + self.margin[0], hb.HERO_HALF_U[1] + self.margin[1])
        # earliest damage after a drop bell arms (its self template's first occupied bin, padding included)
        leads = [t.active()[0] for k, t in templates.items() if k.startswith(f"{hb.SUPPORT}ent/{DROP_BELL}")
                 and t.active() is not None]
        self.bell_lead = (min(leads) - BIN) if leads else -math.inf
        self.query = hb.SupportQuery(templates, hero_half=hb.HERO_HALF_U)
        # comfort: the same templates grown by an extra margin, a preference above the score (clearance against the
        # one-frame drift of a plan that is safe by millimetres)
        self.comfort = None if comfort is None else margin_xy(comfort)
        self.query_c = None
        if self.comfort is not None:
            if comfort_templates is None:
                mx, my = self.margin
                comfort_templates = load_planner_templates(model, (mx + self.comfort[0], my + self.comfort[1]), npz)
            self.query_c = hb.SupportQuery(comfort_templates, hero_half=hb.HERO_HALF_U)
        self.tracker = BossTracker(model, view)
        # registry hit targets (bells): their predicted paths for the planner's hit effects (pogo off a bell)
        self.targets = TargetTracker()
        self._ws: WorldState | None = None
        self.boss: Entity | None = None
        self.no_hurtbox: frozenset[str] = frozenset()     # states / phases with the body box disabled (playbook)
        self.bell_tells = False        # VE: the drop bells' cue is in the view (ObservabilityFilter tells)
        self.hurtbox: dict | None = None   # VE: the boss's hittable box per phase (load_hurtbox; scoring only)
        self.t = 0.0

    def reset(self) -> None:
        self.tracker.reset()
        self.targets.reset()
        self._ws = None
        self.boss = None

    def notify_wake(self, t_game: float) -> None:
        """The fight started at this game time (the bot walked into the trigger; vision sees the arena gates close)."""
        if self.tracker.t_wake is None:
            self.tracker.t_wake = t_game

    def update(self, ws: WorldState) -> None:
        self.t = ws.stamp.t_game_s
        self.boss = self.tracker.update(ws)
        self.targets.update(ws, self.t)
        self._ws = ws

    # ---- the walk -----------------------------------------------------------------------------------------------

    def forecast(self, horizon_s: float = MIN_HORIZON_S, origin_t: float | None = None) -> Forecast:
        H = max(MIN_HORIZON_S, horizon_s)
        origin = self.t if origin_t is None else origin_t
        roots, known = self.tracker.roots(origin)
        nodes: list[Node] = []
        placements: list[Placement] = []
        for r in roots:
            self._walk(r.state, r.e_lo, r.e_hi, replace(r.ctx), r.p, -1, H, nodes, placements, r.current, 0)
        tr = self.tracker
        det: list = []
        if tr.bells:
            nid = len(nodes)
            nodes.append(Node(nid, "bells", 0.0, 0.0, None, 1.0, -1, None))
            # oracle: the arming frame; vision: from the cue, +-its slack in 1/60 s steps
            k = 0 if self.view == ORACLE else int(round(TELL_SLACK_S["bell_dust"] / BIN))
            for iid, (tk, t_arm, pos) in tr.bells.items():
                key = f"{hb.SUPPORT}ent/{tk}/self"
                if key not in self.meta:
                    continue
                if self._det_bell(iid, det):
                    continue                  # falling or bounced: its exact path (two branches) replaces the template
                t0, t1 = self.meta[key]
                for j in range(-k, k + 1):
                    e = t_arm + j * BIN - origin
                    if e + t1 < -BIN or e + t0 > H + BIN:
                        continue
                    placements.append(Placement(key, -e, pos, 1, nid, e + t0, e + t1, frozenset({tk})))
        for fam, anchor, lo, hi, phase, death in self.tracker.ends:
            nid = len(nodes)
            nodes.append(Node(nid, TAIL, lo - origin, hi - origin, fam, 1.0, -1, anchor))
            self._place(fam, TAIL, lo - origin, hi - origin, Ctx(family=fam, anchor=anchor, phase=phase), nid, H,
                        placements, death_tail=death)
        if not roots and self.tracker.dead:
            known = True
        out = Forecast(self, origin, H, nodes, placements, known, roots, self.boss)
        out.det = det
        return out

    def _det_bell(self, iid: int, det: list) -> bool:
        """ORACLE: an armed drop bell already falling (Drop, Air) or bounced (Bounce Air, Submerge) has an exact path
        (pogo_targets.simulate, centre error 0.000 u over 0.8 s in game time on 2 recordings): it is support as two
        branches, one per bounce side (p 0.5 each; the bounce speed is fixed, 4 u/s), or one once it bounced, instead
        of the logged union of its self template."""
        if self.view != ORACLE or self._ws is None:
            return False
        e = next((x for x in self._ws.entities if x.id == iid), None)
        if e is None or not e.fsm or e.vel.conf <= 0:
            return False
        sp = self.targets.spec_of(e.type_key.v)
        st = e.fsm[0][1]
        if sp is None or st not in DET_STATES:
            return False
        rest = None
        if st == "Submerge":
            rest = max(0.0, 0.75 - e.fsm[0][2])
        det.append((sp, float(e.pos.v[0]), float(e.pos.v[1]), float(e.vel.v[0]), float(e.vel.v[1]),
                    int(sp.next_bounce.get(st, len(sp.bounces))), rest, e.type_key.v))
        return True

    def _place(self, fam: str, state: str, e_lo: float, e_hi: float, ctx: Ctx, node: int, H: float,
               out: list[Placement], death_tail: bool = False) -> None:
        m = self.model
        f = m.families[fam]
        ws = f.world_sources.get(state, frozenset())
        p2 = ctx.phase == "P1" and ws and ws <= f.p2_only.get(state, frozenset())
        if ctx.anchor is not None:
            frames = ["anchor"]
            if not p2:
                frames.append("world")
        else:
            frames = ["world_all"]
        if state == TAIL and not death_tail:
            # An attack that ended into the decision chain left the boss underground: its tail is what outlives it
            # (attack bells, drop bells). The tail templates also hold the body of instances killed mid-attack
            # (support/BB_CHARGE/_tail: 66 instances, no tail source logged), which only a death end places.
            anchored = f.sources.get(TAIL, frozenset()) - ws - {m.boss_type}
            world = ws if not p2 else frozenset()
            if ctx.anchor is not None:
                frames = (["anchor"] if anchored else []) + (["world"] if world else [])
            else:
                frames = ["world_all"] if (anchored or world) else []
        srcs = f.sources.get(state, frozenset())
        if ctx.phase == "P1":
            srcs = srcs - f.p2_only.get(state, frozenset())
        n = int(math.floor((e_hi - e_lo) / BIN + 1e-6)) + 1
        es = [e_lo + i * BIN for i in range(n)]
        if es[-1] < e_hi - 1e-3:            # a 1 ms remainder rounds to the same 1/60 s bin
            es.append(e_hi)
        for fr in frames:
            key = m.key(fam, state, fr)
            if key is None:
                continue
            t0, t1 = self.meta[key]
            anchor = (ctx.anchor.x, ctx.anchor.y) if fr == "anchor" else None
            mirror = ctx.anchor.mirror if fr == "anchor" else 1
            # a union of drop-bell falls: in the oracle view every armed bell has its own self template, and a bell
            # not armed yet cannot hurt sooner than its arming lead, so the union only counts from then on
            allsrc = f.sources.get(state, frozenset())
            fsrc = ws if fr == "world" else (allsrc - ws if fr == "anchor" else allsrc)
            t_from = -math.inf
            if fsrc and all(x.startswith(DROP_BELL) for x in fsrc) and not self.tracker.bells_unknown:
                if self.view == ORACLE:
                    t_from = self.bell_lead
                elif self.bell_tells:      # a bell whose cue is not out yet armed less than the cue's delay ago
                    t_from = self.bell_lead - TELL_DELAY["bell_dust"] - TELL_SLACK_S["bell_dust"]
            for e in es:
                on, off = e + t0, e + t1
                if off < -BIN or on > H + BIN:
                    continue
                if t_from > H + BIN:
                    continue
                out.append(Placement(key, -e, anchor, mirror, node, on, off, srcs, t_from))

    def _walk(self, state: str, e_lo: float, e_hi: float, ctx: Ctx, p: float, parent: int, H: float,
              nodes: list[Node], out: list[Placement], current: bool, depth: int) -> None:
        m = self.model
        if e_lo > H or len(nodes) >= MAX_NODES or depth > 40:
            return
        info = m.states.get(state)
        if info is None:
            return
        if state in m.attack_starts:
            fam = m.attack_starts[state]
            if ctx.family != fam:
                ctx.family = fam
                ctx.anchor = m.anchor(fam, ctx.direction)
        if state in m.dir_states:
            ctx.direction = state
        if state == "Rage Pos":
            ctx.raged = True
        if state in m.phase_marks:
            ctx.phase = m.phase_marks[state]
        nid = len(nodes)
        nodes.append(Node(nid, state, e_lo, e_hi, ctx.family, p, parent, ctx.anchor))
        fam = ctx.family
        if fam is not None and state in m.families[fam].states:
            self._place(fam, state, e_lo, e_hi, ctx, nid, H, out)
        x_lo, x_hi = e_lo + info.dwell[0], e_hi + info.dwell[1]
        if current:
            x_lo, x_hi = max(x_lo, BIN), max(x_hi, BIN)
        for nxt, pn in self._successors(state, ctx):
            c2 = replace(ctx)
            if fam is not None and state in m.families[fam].states and nxt in m.decision_states:
                self._place(fam, TAIL, x_lo, x_hi, ctx, nid, H, out)
                c2.family, c2.anchor, c2.direction = None, None, None
            if nxt in m.attack_starts and c2.family is not None and c2.family != m.attack_starts[nxt]:
                c2.family, c2.anchor = None, None
            dirs = None
            if nxt in m.attack_starts and c2.direction is None:
                fam2 = m.attack_starts[nxt]
                dirs = m.directions(fam2) or None
            if dirs:
                for dname in dirs:
                    c3 = replace(c2, direction=dname)
                    self._walk(nxt, x_lo, x_hi, c3, p * pn / len(dirs), nid, H, nodes, out, False, depth + 1)
            else:
                self._walk(nxt, x_lo, x_hi, c2, p * pn, nid, H, nodes, out, False, depth + 1)

    def _successors(self, state: str, ctx: Ctx) -> list[tuple[str, float]]:
        """Support successors with the scoring probability; structural rules: Rage Pos only before the rage
        (P1, not raged), with p 1 at hp <= the logged rage HP else 0; Bell Burst? by phase."""
        m = self.model
        succ = list(m.states[state].succ)
        if state == "Rage?":
            rage_possible = ctx.phase != "P2" and not ctx.raged
            p_rage = 0.0
            if rage_possible and ctx.phase == "P1" and ctx.hp is not None and m.rage_hp is not None:
                p_rage = 1.0 if ctx.hp <= m.rage_hp else 0.0
            elif rage_possible:
                p_rage = 0.03
            out = []
            for s, _ in succ:
                if s == "Rage Pos":
                    if rage_possible:
                        out.append((s, p_rage))
                else:
                    out.append((s, 1.0 - p_rage))
            return out
        if state == "Bell Burst?" and ctx.phase in m.p_burst:
            pb = m.p_burst[ctx.phase]
            return [(s, pb if s == "Burst Pos" else 1.0 - pb) for s, _ in succ]
        return succ


def load_hurtbox(path: str | Path | None = None) -> dict:
    """The hurtbox-per-phase table (ssbot.tools.hurtbox_table): {phase: {time bin: {median, p10, p90, n}}}."""
    p = Path(path) if path else Path(__file__).resolve().parents[3] / "knowledge" / "1.0.30000" / "enemies" / \
        "BellBeast_hurtbox.json"
    return json.loads(p.read_text("utf-8"))["phases"] if p.exists() else {}


def margin_xy(margin: float | tuple[float, float]) -> tuple[float, float]:
    return (float(margin), float(margin)) if isinstance(margin, (int, float)) else (float(margin[0]), float(margin[1]))


def load_planner_templates(model: BossModel, margin: float | tuple[float, float] = 0.0, npz: str | None = None
                           ) -> dict[str, hb.SpaceTimeTemplate]:
    """Cached per (enemy, margin, file): the dilation takes 1-2 s and the result is read-only."""
    return _load_planner_templates(model.enemy, margin_xy(margin), None if npz is None else str(npz))


@functools.lru_cache(maxsize=8)
def _load_planner_templates(enemy: str, margin: tuple[float, float], npz: str | None
                            ) -> dict[str, hb.SpaceTimeTemplate]:
    """The per-state and tail support templates of the model's families, dilated for a point query of the hurtbox
    centre: hero half-extents plus margin (x, y). Family-wide templates (t from the attack start) are not needed by
    the walk."""
    from ssbot.combat.boss_model import KNOWLEDGE
    mx, my = margin
    path = npz or (KNOWLEDGE / "enemies" / f"{enemy}_hitboxes.npz")
    tpls, _ = hb.load_templates(path, prefix=hb.SUPPORT)
    out = {}
    for k, t in tpls.items():
        if k.count("/") != 3 or k.split("/")[2].startswith("ent"):
            continue
        if t.t_pad < 1:
            raise ValueError(f"{k}: not a support template (no +-1 bin of export lag baked in)")
        out[k] = t.dilated(rx=hb.HERO_HALF_U[0] + mx, ry=hb.HERO_HALF_U[1] + my, key=k)
    return out


def offsets(T: int, frame_time: float) -> np.ndarray:
    """tk for rollout frames 0..T (frame k at k * frame_time game seconds from the origin)."""
    return np.arange(T + 1, dtype=np.float64) * frame_time


__all__: Sequence[str] = ("Forecaster", "Forecast", "BossTracker", "load_planner_templates", "offsets")
