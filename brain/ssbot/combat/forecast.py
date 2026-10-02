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
+-1 bin for the export lag). Branches (burst / charge / leap, left / right, rage) are all placed; the walk stops past the
horizon. An attack's anchor is used when it is known (Set L / Set R fixed at x 75.03 / 95.72, the rage at 86.21, a
burst once seen), else the world_all template of the state (every logged anchor). The horizon is adaptive: at least
0.8 s, and as long as the planner's longest candidate (a Bind needs 1.37 s + 0.15 s).

Views. ORACLE: the Control FSM state and time in state (Entity.phase, and the FSM_TRANSITION events, which also arrive
while the boss is not exported: before its first emergence). VISION_EQUIVALENT: the observable phase
(ssbot.core.bosses.BELL_BEAST_PHASES) with the time since it changed, the boss's position and facing while drawn, and
memory: "recover" is the end of a charge or of a leap (the phase before it says which), "hidden" after "recover" is
Submerged, after "burst" Burst Recovery (the bells still rolling), after "roar_end" Rage Submerge, and before the first
emergence the wake chain (Submerged Init 2.0 s, then a charge from the right: the first attack of every logged fight).
An observable phase's entry is known to +-1 frame (a transition frame can show the next clip early), a hidden boss's
position is unknown (both charge / leap anchors, the burst's world_all), a burst's anchor comes from the box centre
(fixed offset +-0.539, -2.68 by flipX; averaged over the frames seen), a charge's or leap's from its facing.
A boss lost over the image edge (a ghost: no phase) coasts: the last known state stays the root, and its successors
come in as their entry intervals pass.

Time. Templates count game time (1/60 s bins; game time stands still in hit-stop and pauses); offsets are game seconds
from the WorldState's frame (stamp.t_game_s). The planner's rollout frame k is at tk = k * frame_time.
"""
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace

import numpy as np

from ssbot.combat.boss_model import TAIL, Anchor, BossModel
from ssbot.core.worldstate import ORACLE, VISION_EQUIVALENT, Entity, Ev, WorldState
from ssbot.knowledge import hitbox_tables as hb
from ssbot.safety.hits_to_death import SupportEvent, SupportSet

BIN = hb.BIN_S
MIN_HORIZON_S = 0.8
SUP_HORIZON_S = 0.8          # what the supervisor's support covers (hits_to_death's worst event "now")
VE_ENTRY_SLACK = 1           # bins of slack on an observable phase's entry (a transition frame shows a clip early)
MAX_NODES = 400
HIDDEN, UNKNOWN = "hidden", "unknown"

# observable phase -> the Control state its first frame is (the root of the forecast walk)
PHASE_ROOT = {"emerge": "Charge Emerge", "charge_antic": "Charge Antic", "charge": "Charge", "leap": "Leap Out",
              "burst": "Burst Out", "roar": "Rage Burst", "roar_end": "Roar End"}
PHASE_FAMILY = {"emerge": "BB_CHARGE", "charge_antic": "BB_CHARGE", "charge": "BB_CHARGE", "leap": "BB_LEAP",
                "burst": "BB_BURST", "roar": "BB_RAGE", "roar_end": "BB_RAGE"}
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
        kids = {}
        for n in nodes:
            kids.setdefault(n.parent, []).append(n.id)
        self.leaves = [n.id for n in nodes if n.id not in kids]

    # ---- queries ------------------------------------------------------------------------------------------------

    def _query(self, placements: Iterable[Placement]) -> hb.SupportQuery:
        q = self.fc.query
        q.clear()
        for p in placements:
            q.place(p.key, p.t_ref, p.anchor, p.mirror)
        return q

    def occupied(self, x, y, tk) -> np.ndarray:
        """[N, T] bool: the hurtbox (grown by the forecaster's margin) centred at (x, y) [N, T] at tk [T] game s from
        the origin overlaps some support tube."""
        tk = np.asarray(tk, np.float64)
        active = [p for p in self.placements if p.t_off >= tk.min() - BIN and p.t_on <= tk.max() + BIN]
        return self._query(active).query(x, y, tk)

    def node_hits(self, x, y, tk) -> np.ndarray:
        """[nodes, N] bool: contact with each node's own placements."""
        x = np.asarray(x, np.float64)
        out = np.zeros((len(self.nodes), x.shape[0]), bool)
        by_node: dict[int, list[Placement]] = {}
        for p in self.placements:
            by_node.setdefault(p.node, []).append(p)
        for nid, ps in by_node.items():
            out[nid] = self._query(ps).query(x, y, tk).any(axis=1)
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

    def active_sources(self, t0: float = 0.0, t1: float = SUP_HORIZON_S) -> frozenset[str]:
        out: set[str] = set()
        for p in self.placements:
            if p.t_off >= t0 and p.t_on <= t1:
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
        bb = _body_box(b)
        if bb is None:
            return box, ok
        box[:] = bb
        t_left = tr.drawn_left(self.origin_t)
        ok[:] = tk <= t_left
        fam = tr.ctx.family
        f = self.fc.model.families.get(fam) if fam else None
        if f is not None and f.path is not None and tr.t_start is not None and tr.ctx.anchor is not None:
            t_att = self.origin_t - tr.t_start
            path = f.path
            xs = np.interp(t_att + tk, path[:, 0], path[:, 6])
            ys = np.interp(t_att + tk, path[:, 0], path[:, 7])
            x0 = np.interp(t_att, path[:, 0], path[:, 6])
            y0 = np.interp(t_att, path[:, 0], path[:, 7])
            m = tr.ctx.anchor.mirror
            box[:, [0, 2]] += (m * (xs - x0))[:, None]
            box[:, [1, 3]] += (ys - y0)[:, None]
        return box, ok


def _body_box(e: Entity) -> tuple[float, float, float, float] | None:
    if e.body_polys:
        p = np.asarray(e.body_polys[0], np.float64)
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
        self.coasting = False                  # VE: no phase this frame (a ghost)
        self._anchor_sum: list[float] = []
        self.t = 0.0
        self.hidden_x: dict[str, float] = {}   # ORACLE: the hidden boss's x per state of this attack (anchor check)
        self.ends: list[tuple[str, Anchor | None, float, float, str | None]] = []   # last attacks' ends: (family,
        #                                         anchor, t_end lo, t_end hi, phase): their tails (bells) outlive them
        self._drawn_anchor: tuple | None = None
        self.anchor_log: list[tuple[str, float, float]] = []   # ORACLE: (family, hidden x, drawn transform x)

    # ---- ORACLE -------------------------------------------------------------------------------------------------

    def _enter(self, state: str, t: float) -> None:
        m = self.model
        prev = self.state
        self.state, self.t_entry = state, t
        if state in m.death_states:
            self.dead = True
            return
        if state == "Submerged Init":
            self.ctx.direction = "-"
            self.t_wake = self.t_wake if self.t_wake is not None else t
        if state in m.dir_states:
            self.ctx.direction = state
        if state in m.attack_starts:
            fam = m.attack_starts[state]
            self.ctx.family = fam
            self.ctx.anchor = m.anchor(fam, self.ctx.direction)
            self.t_start = t
            self.hidden_x = {}
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

    def _ended(self, family: str, anchor: Anchor | None, t_lo: float, t_hi: float) -> None:
        self.ends = (self.ends + [(family, anchor, t_lo, t_hi, self.ctx.phase)])[-2:]

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
            if ev.kind == Ev.ENEMY_KILLED and ev.data is not None and ev.data.type_key == m.boss_type:
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
        if boss is None:
            return
        if boss.phase is not None and boss.phase.top:
            st, tau = boss.phase.top, boss.phase.t_in_phase
            if st != self.state:
                self._enter(st, t - tau)
            else:
                self.t_entry = t - tau
        if boss.hidden:
            if self.ctx.family is not None:
                self.hidden_x[self.state or ""] = boss.pos.v[0]
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
            if m.anchor(fam, self.ctx.direction) is None:
                f = m.families[fam]
                mirror = f.mirror if not f.directed else (-1 if boss.flip_x else 1)
                self.ctx.anchor = Anchor(float(ax), float(ay), mirror)

    # ---- VISION_EQUIVALENT ----------------------------------------------------------------------------------------

    def _update_ve(self, ws: WorldState, boss: Entity | None, t: float) -> None:
        m = self.model
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
                if fam is not None and fam != self.last_family or ph in ("emerge", "leap", "burst", "roar") \
                        and prev in (HIDDEN, None, "recover", "roar_end"):
                    self._anchor_sum = []
                    self.last_anchor = None
                    self.t_start = None
                self.last_family = fam if fam is not None else self.last_family
                if ph == "roar":
                    self.ctx.raged = True
                if ph == "roar_end":
                    self.ctx.phase = "P2"      # the drop-bell pattern follows; P2 from its end
        if ph == HIDDEN:
            return
        self.seen = True
        fam = self.last_family
        if fam is None:
            return
        f = m.families[fam]
        if fam == "BB_BURST" and boss.pos.conf > 0 and not self._anchor_sum:
            # the box follows the sprite frame (live i2_002 f605393-605452: box centre x 89.93 -> 91.57 while the
            # transform stays at 90.47), so only the first drawn frame has the fixed offset of the behaviour table
            dx = f.box_offset.get(bool(boss.flip_x), (0.0, 0.0))[0]
            self._anchor_sum.append(boss.pos.v[0] - dx)
            ax = float(self._anchor_sum[0])
            self.last_anchor = Anchor(ax, f.anchor_y if f.anchor_y is not None else boss.pos.v[1] + 2.68, 1)
        elif f.directed:
            self.last_anchor = m.anchor(fam, "Set R" if boss.flip_x else "Set L")
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
        return [Root("Submerged Init", e - BIN, e + BIN, Ctx(direction="-", phase="P1", raged=False, hp=self.ctx.hp))]

    def _roots_oracle(self, origin_t: float) -> tuple[list[Root], bool]:
        if self.state is None or self.t_entry is None:
            r = self._wake_root(origin_t)
            return r, bool(r)
        e = self.t_entry - origin_t
        ctx = replace(self.ctx)
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
        st = PHASE_ROOT.get(self.state)
        if st is None:
            return [], False
        ctx = replace(base, family=PHASE_FAMILY[self.state], anchor=self.last_anchor)
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

    def __init__(self, model: BossModel, view: str = ORACLE, margin: float = 0.0,
                 templates: dict[str, hb.SpaceTimeTemplate] | None = None, npz: str | None = None):
        if view not in (ORACLE, VISION_EQUIVALENT):
            raise ValueError(view)
        self.model = model
        self.view = view
        self.margin = margin
        if templates is None:
            templates = load_planner_templates(model, margin, npz)
        self.templates = templates
        self.meta = {k: (t.t0, t.t1) for k, t in templates.items()}
        self.query = hb.SupportQuery(templates, hero_half=(hb.HERO_HALF_U[0] + margin, hb.HERO_HALF_U[1] + margin)) \
            if margin > 0 else hb.SupportQuery(templates)
        self.tracker = BossTracker(model, view)
        self.boss: Entity | None = None
        self.t = 0.0

    def reset(self) -> None:
        self.tracker.reset()
        self.boss = None

    def notify_wake(self, t_game: float) -> None:
        """The fight started at this game time (the bot walked into the trigger; vision sees the arena gates close)."""
        if self.tracker.t_wake is None:
            self.tracker.t_wake = t_game

    def update(self, ws: WorldState) -> None:
        self.t = ws.stamp.t_game_s
        self.boss = self.tracker.update(ws)

    # ---- the walk -----------------------------------------------------------------------------------------------

    def forecast(self, horizon_s: float = MIN_HORIZON_S, origin_t: float | None = None) -> Forecast:
        H = max(MIN_HORIZON_S, horizon_s)
        origin = self.t if origin_t is None else origin_t
        roots, known = self.tracker.roots(origin)
        nodes: list[Node] = []
        placements: list[Placement] = []
        for r in roots:
            self._walk(r.state, r.e_lo, r.e_hi, replace(r.ctx), r.p, -1, H, nodes, placements, r.current, 0)
        for fam, anchor, lo, hi, phase in self.tracker.ends:
            nid = len(nodes)
            nodes.append(Node(nid, TAIL, lo - origin, hi - origin, fam, 1.0, -1, anchor))
            self._place(fam, TAIL, lo - origin, hi - origin, Ctx(family=fam, anchor=anchor, phase=phase), nid, H,
                        placements)
        if not roots and self.tracker.dead:
            known = True
        return Forecast(self, origin, H, nodes, placements, known, roots, self.boss)

    def _place(self, fam: str, state: str, e_lo: float, e_hi: float, ctx: Ctx, node: int, H: float,
               out: list[Placement]) -> None:
        m = self.model
        f = m.families[fam]
        if ctx.anchor is not None:
            frames = ["anchor"]
            ws = f.world_sources.get(state, frozenset())
            if not (ctx.phase == "P1" and ws and ws <= f.p2_only.get(state, frozenset())):
                frames.append("world")
        else:
            frames = ["world_all"]
        srcs = f.sources.get(state, frozenset())
        if ctx.phase == "P1":
            srcs = srcs - f.p2_only.get(state, frozenset())
        n = int(math.floor((e_hi - e_lo) / BIN + 1e-6)) + 1
        es = [e_lo + i * BIN for i in range(n)]
        if es[-1] < e_hi - 1e-9:
            es.append(e_hi)
        for fr in frames:
            key = m.key(fam, state, fr)
            if key is None:
                continue
            t0, t1 = self.meta[key]
            anchor = (ctx.anchor.x, ctx.anchor.y) if fr == "anchor" else None
            mirror = ctx.anchor.mirror if fr == "anchor" else 1
            for e in es:
                on, off = e + t0, e + t1
                if off < -BIN or on > H + BIN:
                    continue
                out.append(Placement(key, -e, anchor, mirror, node, on, off, srcs))

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


def load_planner_templates(model: BossModel, margin: float = 0.0, npz: str | None = None
                           ) -> dict[str, hb.SpaceTimeTemplate]:
    """The per-state and tail support templates of the model's families, dilated for a point query of the hurtbox
    centre (hero half-extents + margin). Family-wide templates (t from the attack start) are not needed by the walk."""
    from ssbot.combat.boss_model import KNOWLEDGE
    path = npz or (KNOWLEDGE / "enemies" / f"{model.enemy}_hitboxes.npz")
    tpls, _ = hb.load_templates(path, prefix=hb.SUPPORT)
    keep = {k: t for k, t in tpls.items() if k.count("/") == 3 and not k.split("/")[2].startswith("ent")}
    return hb.planner_templates(keep, margin=margin)


def offsets(T: int, frame_time: float) -> np.ndarray:
    """tk for rollout frames 0..T (frame k at k * frame_time game seconds from the origin)."""
    return np.arange(T + 1, dtype=np.float64) * frame_time


__all__: Sequence[str] = ("Forecaster", "Forecast", "BossTracker", "load_planner_templates", "offsets")
