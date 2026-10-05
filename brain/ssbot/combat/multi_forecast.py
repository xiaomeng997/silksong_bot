"""Threat forecast of a multi-enemy arena (Forum plan R2, docs/plans/forum_planner_plan.md §4.1 / §4.3): every enemy's
support and probability over the next H seconds in one object with the single-boss Forecast's interface, so the
planner does not need to know how many enemies there are.

    mf = MultiForecaster(EnemyTables.production(), view=ORACLE)   # or MultiForecaster(boss=Forecaster(...))
    mf.reset(); mf.warm(); mf.notify_wake(t_battle)
    mf.update(ws)                                    # every WorldState, in order
    f = mf.forecast(horizon_s=0.8)                   # origin ws.stamp.t_game_s
    f.occupied(x, y, tk)                             # [N, T] bool, every enemy and hazard at once
    f.occupied_without(x, y, tk, iid)                # without one enemy (a kill's effect) or hazard
    f.prob(x, y, tk)                                 # 1 - prod(1 - p_i), scoring only
    f.support_set(ws)                                # one event per instance; multi-hit chains hits > 1
    f.targets(tk), f.t_min(x, y), f.committed(), f.known, f.subjects

Support per enemy (EnemyTracker: Control state, the attack instance and its anchor), the structure the R0 held-out
certification ran on (ssbot.knowledge.forum_support.SubjectRecall; forum.md §12.2), at run time:
  - the walk: from the current state over the logged successors and dwell ranges (one bin of slack each side), a hull
    of entry times per (state, instance context, dead) node, so loops end; a current state older than its longest
    logged dwell can end at any time from the next frame. Memoised per (type, state, instance context, dead,
    overdue): re-walked only when the state changes (the walk cache), times relative to the state's entry (or to the
    origin when overdue); a state not entered yet enters from the next frame on (applied at placement time: the
    unclipped walk's later nodes are a superset of the clipped one's). Structurally absent states
    (ssbot.core.forum.STRUCTURALLY_ABSENT) are not in the tables' walk.
  - the current attack's states at its anchor: fine templates, one per entry bin, while the entry is known to
    FINE_MAX_BINS bins; else one window placement (the coarse base's time pyramid answers every entry in the interval
    at once: EnemyTables.TemplateStore); its family template from the attack start (the family-wide union, coarse);
    its tail once it can end; the tails of ended attacks;
  - instances that may start later (attacks, idle instances): the family walk template of their start (every state
    the instance can reach and its tail, each time-dilated over its entry interval since the start) as a bounding
    box per time bin, grown by the anchor box (the enemy's transform dead-reckoned to the possible start times, grown
    by the type's idle growth since the sighting), both mirrors, per start-time piece; entry families also in their
    world frame;
  - an enemy in its idle family: the idle body tube (its damage box as last seen, moved along its velocity, grown by
    the idle growth) instead of the idle instance's templates;
  - for the first frames only (COLLIDER_TUBE_S, the reaction lag the certification needed them for): the
    current-collider tube (its box grown at the type's top speed) and the hazard tube;
  - a killed enemy's last damage box for DEATH_TAIL_S (forum_products death_tails: contacts on the kill frame only);
    a pooled enemy (the Maestro's Tinies) is walked on after its death while a Maestro is in play (a summon brings it
    back), the others are not; an enemy in a waiting state only while it may enter soon (its wave queued, a Maestro in
    play for a parked Tiny), a wave member not before its wave's earliest activation;
  - thrown hazards: on deterministic paths (ssbot.combat.projectiles: bells incl. the nail redirect, javelins, bomb
    rows, rune slams), the others by their self template from where they armed (the Clawmaiden's spear and blast;
    every hazard in the vision view too, where the paths come from tracked velocities);
  - entries: the next wave's members not in the export yet (WaveTracker's activation window: the static wave table,
    the kills and sightings, never room.battles) by their entry family's world-frame template.
Tiny group placement: with >= TINY_GROUP Tinies, the instances they may start are placed once per cluster (the Tinies
in one TINY_CLUSTER_U grid cell) starting the same family (one anchor box covering the members) instead of once per
Tiny; a group row stands for every Tiny of its cluster (occupied_without keeps it while one of them is in,
occupied_only / t_min(subject) include it for each of them, support_set counts an event for each of them).

The single-boss path is untouched: MultiForecaster(boss=fc) wraps a Forecaster (without resetting it) and its forecast
is a proxy of the boss's Forecast: every query delegated, every other attribute read and written on the boss Forecast
(bit-identical: tests/test_multi_forecast.py and tools/multi_recall bellbeast, incl. the live policy's
bell_hit_monitor.zone).

Not in the multi path yet (R3): comfort templates (occupied(..., comfort=True) answers with the plain support and
counts the request in MultiForecaster.comfort_requests).
"""
import copy
import json
import math
from collections import defaultdict
from dataclasses import dataclass

import numba
import numpy as np

from ssbot.combat.enemy_tables import BIN, EMPTY, FORUM_DIR, JMAX, TAIL, EnemyTables, PlaceBatch, TypeTable, \
    WinBatch
from ssbot.combat.enemy_tracker import TAIL_KEEP_S, EnemyTracker, body_offsets
from ssbot.combat.fastquery import circle_hits
from ssbot.combat.forecast import active_within, entry_grid, exit_interval
from ssbot.combat.projectiles import BELL, HAZARD_DV_U_S, RUNE, SKIN_U, HazardPath, HazardTracker, hazard_type
from ssbot.combat.wave_tracker import WaveTracker
from ssbot.core.forum import FORUM_TYPES, FORUM_WAVES, HAZARD_ALIASES, HAZARD_OWNER, WAVE_TYPES, _type_key
from ssbot.core.worldstate import ORACLE, Ev, WorldState
from ssbot.knowledge import hitbox_tables as hb
from ssbot.safety.hits_to_death import SupportEvent, SupportSet

MIN_HORIZON_S = 0.8
SUP_HORIZON_S = 0.8
DWELL_SLACK_S = BIN               # logged dwell ranges are frame-quantised
WALK_CAP_S = 6.0                  # memoised walks reach this far past the state's entry
WALK_MAX_STEPS = 20000
FINE_MAX_BINS = 3                 # a node whose entry spans more bins is one window placement
TUBE_MAX_AGE_S = 0.5              # the idle body tube starts from a box seen at most this long ago
COLLIDER_TUBE_S = 5 * BIN         # the current-collider and hazard tubes cover only the reaction lag
DEATH_TAIL_S = 3 * BIN            # a killed enemy's last box hurts on its kill frame (forum_products death_tails)
HAZARD_GONE_S = 0.5
COARSE_MAX_U = 24.0               # an anchor box wider than this places an arena-wide box instead
ARENA_BOX = (0.0, -5.0, 64.0, 40.0)
TINY = "Song Automaton Tiny"
MAESTRO = "Song Pilgrim Maestro"
TINY_GROUP = 3                    # Tinies at least this many: group placement
TINY_CLUSTER_U = 4.0              # Tinies in one cell of this grid share one placement set
ENTRY_LAG_S = 1.0                 # a wave's activation -> its member's entry family start (upper bound)
ENTRY_OWNER = -(1 << 50)          # placement owner of wave w's entries: ENTRY_OWNER - w
PIECES_S = ((0.4, 6 * BIN), (1.0, 12 * BIN), (math.inf, 24 * BIN))   # start-time piece length by distance


def _piece_len(t: float) -> float:
    for lim, w in PIECES_S:
        if t < lim:
            return w
    return PIECES_S[-1][1]


@dataclass(slots=True)
class WalkNode:
    state: str
    family: str | None
    start: str | None
    kind: str | None              # "cur" (the current instance) | "new" (one starting later) | None
    dead: bool
    lo: float                     # entry interval relative to the walk's reference time
    hi: float
    p: float                      # max-product path probability (scoring only)
    current: bool = False         # the walk's root: the current state at its entry


def walk(tt: TypeTable, state: str, ctx: tuple | None, dead: bool, overdue: bool, cap: float = WALK_CAP_S,
         instance_only: bool = False) -> list[WalkNode]:
    """The support walk (ssbot.knowledge.forum_support.SubjectRecall._walk) from `state` entered at 0 (overdue: the
    state can end at any time from the next frame: entries relative to the origin). ctx: (family, start state) of the
    current instance. Hull of entry times per (state, family, start, kind, dead) node. instance_only: the states of
    the root's instance and its tail only (a family walk template)."""
    sp = tt.spec
    idle = sp.idle_family
    nodes: dict[tuple, list] = {}
    todo: list[tuple] = []

    def push(st, lo, hi, c, d, p, current=False):
        if lo > cap:
            return
        hi = min(hi, cap)
        k = (st, c, d, current)
        iv = nodes.get(k)
        if iv is None:
            nodes[k] = [lo, hi, p, 0]
        elif lo < iv[0] - 1e-9 or hi > iv[1] + 1e-9:
            iv[3] += 1
            if iv[3] >= 2:
                # widening: an interval that keeps growing (a loop pushing the latest entry later, branches found
                # in turn pulling the earliest one earlier) takes its bounds at once: a superset, and walks end fast
                if hi > iv[1] + 1e-9:
                    hi = cap
                if lo < iv[0] - 1e-9:
                    lo = min(lo, 0.0) if not current else lo
            iv[0], iv[1], iv[2] = min(iv[0], lo), max(iv[1], hi), max(iv[2], p)
        else:
            iv[2] = max(iv[2], p)     # a likelier path alone does not re-walk (scoring only)
            return
        todo.append(k)

    c0 = (ctx[0], ctx[1], "cur") if ctx is not None else None
    push(state, 0.0, 0.0, c0, dead, 1.0, True)
    steps = 0
    while todo and steps < WALK_MAX_STEPS:
        k = todo.pop()
        st, c, d, current = k
        lo, hi, p, _ = nodes[k]
        steps += 1
        fam = c[0] if c else None
        dw = tt.dwell.get(st)
        if dw is None:
            continue
        # relative to the state's entry: the next-frame clip of the current state is applied at placement time
        x_lo, x_hi = exit_interval(lo, hi, dw, False, DWELL_SLACK_S)
        if current and overdue:
            x_lo, x_hi = BIN, cap
        if x_lo > cap:
            continue
        ps = tt.p_succ.get(st, {})
        for nxt in tt.succ.get(st, ()):
            pn = p * ps.get(nxt, 0.0)
            c2, d2 = c, d
            if nxt in tt.attack_starts:
                nf = tt.attack_starts[nxt]
                if not (c is not None and c[0] == nf and nxt != c[1]):
                    if fam is not None and fam != idle:
                        push(TAIL, x_lo, x_hi, c, d, pn)
                    c2, d2 = (nf, nxt, "new"), False
            elif nxt in tt.decision_states:
                if fam is not None and fam != idle:
                    push(TAIL, x_lo, x_hi, c, d, pn)
                    c2 = (idle, nxt, "new") if idle and not d else None
                elif fam is None and idle and not d:
                    c2 = (idle, nxt, "new")
            if instance_only and c2 != c:
                continue
            push(nxt, x_lo, x_hi, c2, d2, pn)
    out = []
    for (st, c, d, current), (lo, hi, p, _) in nodes.items():
        if c is None:
            continue
        out.append(WalkNode(st, c[0], c[1], c[2], d, lo, hi, p, current))
    return out


class _WalkCache:
    """Memoised walks, split for the placements: the current instance's nodes and the roots of later instances."""

    def __init__(self):
        self.d: dict = {}
        self.hits = 0
        self.misses = 0

    def get(self, tt: TypeTable, state: str, ctx, dead: bool, overdue: bool) -> tuple[list, list]:
        k = (tt.tk, state, ctx, dead, overdue)
        r = self.d.get(k)
        if r is None:
            self.misses += 1
            nodes = walk(tt, state, ctx, dead, overdue)
            r = self.d[k] = ([n for n in nodes if n.kind == "cur"],
                             [n for n in nodes if n.kind == "new" and n.state == n.start])
        else:
            self.hits += 1
        return r


@dataclass(slots=True)
class Subject:
    """What a forecast says about one enemy (MultiForecast.subjects)."""
    iid: int
    type_key: str
    alive: bool
    in_play: bool
    committed: bool               # in an attack (not idle, not waiting)
    family: str | None
    state: str | None
    hp_est: float
    hp_sd: float
    pos: tuple | None
    t_free: float                 # earliest time its current attack can end (s from the origin; 0 when idle)
    t_strike: float               # earliest time it may start a new attack (s from the origin; inf: none in H)


@dataclass(slots=True)
class Target:
    """A hittable body (an enemy's hurtbox moved along its velocity) or a hazard (a bell) over the query times."""
    iid: int
    type_key: str
    box: np.ndarray               # [T, 4]
    ok: np.ndarray                # [T]
    hazard: bool = False


class _Shim:
    """The bits of the single-boss Forecaster the planner reads off f.fc (the families' hazard flags: Forum damage
    is all ENEMY, i-frames block it; no comfort query; no registry targets)."""

    class _Fam:
        hazard = False

    class _Model:
        def __init__(self):
            self.families = {"forum": _Shim._Fam()}
            self.decision_states = ()

    class _Targets:
        @staticmethod
        def spec_of(_type_key):
            return None


class MultiForecaster:
    """Every enemy's tracker, the hazards, the wave tracker and the tables (see the module docstring); or, with
    boss=Forecaster, the single-boss forecaster wrapped (bit-identical)."""

    def __init__(self, tables: EnemyTables | None = None, view: str = ORACLE, boss=None, margin: float = 0.0,
                 waves: bool = True, collider_tube: bool = True, self_templates: str = "auto",
                 tiny_group: int = TINY_GROUP):
        self.tables = tables
        self.view = view
        self.boss = boss
        self.margin = margin
        self.half = (hb.HERO_HALF_U[0] + margin, hb.HERO_HALF_U[1] + margin) if boss is None else boss.half
        self.use_waves = waves
        self.collider_tube = collider_tube
        # "auto": deterministic paths for the modelled hazards in the oracle view, self templates for the rest and
        # for every hazard in the vision view; "all": self templates for every hazard too; "none": paths only
        self.self_templates = self_templates
        self.tiny_group = tiny_group
        self.model = _Shim._Model()
        self.query_c = None
        self.targets = _Shim._Targets()
        self.walks = _WalkCache()
        self._fwalk: dict = {}
        self.offsets = {}
        if tables is not None and view != ORACLE:
            for tk, spec in FORUM_TYPES.items():
                p = FORUM_DIR / f"{spec.enemy}.json"
                if p.exists():
                    self.offsets[tk] = body_offsets(json.loads(p.read_text("utf-8")))
        self._reset_multi()                   # a wrapped boss keeps its state (wrapping mid-fight changes nothing)

    def reset(self) -> None:
        if self.boss is not None:
            self.boss.reset()
        self._reset_multi()

    def _reset_multi(self) -> None:
        self.trackers: dict[int, EnemyTracker] = {}
        self.hazards = HazardTracker(self.view)
        self.waves = WaveTracker()
        self.self_haz: dict[int, list] = {}    # hazard iid -> [type, armed, arm_T, arm_pos, last_T, pos, rel_box, vel]
        self.t = getattr(self.boss, "t", 0.0) if self.boss is not None else 0.0
        self.comfort_requests = 0             # comfort queries answered by the plain support (no comfort templates)
        self._ws: WorldState | None = None
        self.t_wake: float | None = None

    def notify_wake(self, t_game: float, wave: int = 0) -> None:
        """The battle started (the gates close: the bot walked into Start Range; a wave-start savestate's battle at
        its wave)."""
        if self.boss is not None:
            self.boss.notify_wake(t_game)
            return
        if self.t_wake is None:
            self.t_wake = t_game
            if self.use_waves:
                self.waves.start(t_game, wave)

    # ---- per frame ----

    def update(self, ws: WorldState) -> None:
        if self.boss is not None:
            self.boss.update(ws)
            self.t = self.boss.t
            self._ws = ws
            return
        T = ws.stamp.t_game_s
        self.t = T
        self._ws = ws
        tabs = self.tables.types
        evs: dict[int, list] = defaultdict(list)
        for ev in ws.events:
            d = ev.data
            if ev.kind == Ev.FSM_TRANSITION and d is not None and d.enemy_id is not None:
                evs[d.enemy_id].append(ev)
                tk = d.type_key if d.type_key in tabs else _type_key(d.type_key or "")
                if d.enemy_id not in self.trackers and tk in tabs and self.view == ORACLE \
                        and d.fsm == tabs[tk].spec.control_fsm:
                    self._new(d.enemy_id, tk)
            elif ev.kind in (Ev.HIT_DEALT, Ev.ENEMY_KILLED) and d is not None:
                evs[d.target_id].append(ev)
        ents = {}
        for e in ws.entities:
            tk = e.type_key.v
            if tk in tabs:
                ents[e.id] = e
                if e.id not in self.trackers:
                    self._new(e.id, tk)
        for iid, tr in self.trackers.items():
            was_dead = tr.dead
            tr.observe(T, evs.get(iid, ()), ents.get(iid))
            if was_dead and not tr.dead and tr.table.spec.pooled:
                tr.revive()
        self.hazards.update(ws)
        self._self_hazards(ws, T)
        if self.use_waves:
            if self.t_wake is None and any(tr.in_play for tr in self.trackers.values()):
                self.notify_wake(T)
            self.waves.update(ws)

    def _new(self, iid: int, tk: str) -> None:
        self.trackers[iid] = EnemyTracker(self.tables.types[tk], self.view, iid, self.offsets.get(tk))

    def _self_hazards(self, ws: WorldState, T: float) -> None:
        """Thrown hazards placed by their self templates (forum_support.SubjectTracker.hazard): armed when a damage
        box is on (or its state is not a rest state), its arming time and position kept."""
        for e in ws.entities:
            tk = e.type_key.v
            if tk not in HAZARD_OWNER and tk not in HAZARD_ALIASES or e.hidden:
                continue
            if tk in HAZARD_ALIASES:
                tk = self.hazards.alias.get(e.id) or hazard_type(e)
            owner = HAZARD_OWNER.get(tk)
            if owner is None:
                continue
            rest = FORUM_TYPES[owner].hazard_rest
            st = e.fsm[0][1] if e.fsm else None
            boxes = [b for b in e.dmg_boxes if b.active and b.poly]
            armed = bool(boxes) or (st is not None and st not in rest)
            p = e.pos_transform if (self.view == ORACLE and e.pos_transform is not None) else e.pos.v
            pos = (float(p[0]), float(p[1]))
            h = self.self_haz.get(e.id)
            if h is None:
                h = self.self_haz[e.id] = [tk, False, T, pos, T, pos, None, (0.0, 0.0)]
            if armed and (not h[1] or T - h[4] > 2.5 * BIN):
                h[0], h[2], h[3] = tk, T, pos
            h[1], h[4], h[5] = armed, T, pos
            if boxes:
                xs = [q[0] for b in boxes for q in b.poly]
                ys = [q[1] for b in boxes for q in b.poly]
                h[6] = (min(xs) - pos[0], min(ys) - pos[1], max(xs) - pos[0], max(ys) - pos[1])
            h[7] = (float(e.vel.v[0]), float(e.vel.v[1])) if e.vel.conf > 0 else (0.0, 0.0)
        for iid in [i for i, h in self.self_haz.items() if T - h[4] > HAZARD_GONE_S]:
            del self.self_haz[iid]

    # ---- family walk templates ----

    def family_walk_id(self, tt: TypeTable, fam: str, start: str, frame: str = "anchor") -> int | None:
        """A bbox-only id: per time bin since the instance's start, the bounding box of every state the instance
        can reach from `start` and its tail (walk instance_only), each per-state template's box table time-dilated
        over its entry interval (sparse-table window unions). Built once."""
        key = (tt.tk, fam, start, frame)
        if key in self._fwalk:
            return self._fwalk[key]
        store = self.tables.store
        skey = f"fwalk/{tt.tk}/{fam}/{start}/{frame}"
        i = store.coarse_keys.get(skey)
        if i is not None and i in store._bb:          # built by an earlier forecaster on these tables
            self._fwalk[key] = i
            return i
        parts = []
        for nd in walk(tt, start, (fam, start), False, False, instance_only=True):
            tid = self.tables.key_id(fam, TAIL if nd.state == TAIL else nd.state, frame)
            if tid is None:
                continue
            offs, nt, t0 = store.bbox_table(tid)
            parts.append((offs, nt, t0, nd.lo, nd.hi))
        if not parts:
            self._fwalk[key] = None
            return None
        rows = store.bb_rows()
        u0 = min(int(round((t0 + lo) / BIN)) for _, _, t0, lo, _ in parts)
        u1 = max(int(round((t0 + hi) / BIN)) + nt for _, nt, t0, _, hi in parts)
        acc = np.tile(np.array(EMPTY), (u1 - u0 + 1, 1))
        tau = (np.arange(u1 - u0 + 1) + u0) * BIN
        for offs, nt, t0, lo, hi in parts:
            b = _window_union(rows, offs, nt, np.rint((tau - hi - t0) / BIN).astype(np.int64),
                              np.rint((tau - lo - t0) / BIN).astype(np.int64))
            acc[:, 0] = np.minimum(acc[:, 0], b[:, 0])
            acc[:, 1] = np.minimum(acc[:, 1], b[:, 1])
            acc[:, 2] = np.maximum(acc[:, 2], b[:, 2])
            acc[:, 3] = np.maximum(acc[:, 3], b[:, 3])
        i = store.add_coarse_base(f"fwalk/{tt.tk}/{fam}/{start}/{frame}", None)
        store.add_bbox(i, acc, u0 * BIN)
        self._fwalk[key] = i
        return i

    def warm(self) -> int:
        """Build before the fight what the forecasts would build lazily: every logged instance start's family walk
        boxes, the coarse time pyramids and box tables of the per-state templates. Returns how many."""
        store = self.tables.store
        n = 0
        for tt in self.tables.types.values():
            starts = {(f.name, s) for f in tt.families.values() for s in f.starts}
            starts |= {(tt.spec.idle_family, s) for s in tt.decision_states}
            for fam, s in sorted(starts):
                for frame in ("anchor",) + (("world_all",) if fam == tt.spec.entry_family else ()):
                    n += self.family_walk_id(tt, fam, s, frame) is not None
        for tid in list(range(store.n_fine)) + list(store._pooled):
            store.pyramid(tid)
            store.bbox_table(tid)
            n += 1
        # the walks from every state with the instance contexts it can be in
        for tt in self.tables.types.values():
            idle = tt.spec.idle_family
            for st in tt.dwell:
                ctxs = {None}
                for f in tt.families.values():
                    if st in f.states:
                        ctxs |= {(f.name, s) for s in f.starts}
                if st in tt.decision_states:
                    ctxs.add((idle, st))
                for ctx in ctxs:
                    for overdue in (False, True):
                        for dead in ((False, True) if tt.spec.pooled else (False,)):
                            self.walks.get(tt, st, ctx, dead, overdue)
                            n += 1
        return n

    # ---- the forecast ----

    def forecast(self, horizon_s: float = MIN_HORIZON_S, origin_t: float | None = None,
                 clamp: bool = True) -> "MultiForecast":
        """clamp False: exactly horizon_s (the recall's few frames), else at least MIN_HORIZON_S."""
        H = max(MIN_HORIZON_S, horizon_s) if clamp else horizon_s
        if self.boss is not None:
            return MultiForecast(self, self.boss.t if origin_t is None else origin_t, H,
                                 boss=self.boss.forecast(horizon_s, origin_t))
        origin = self.t if origin_t is None else origin_t
        b = _Builder(self, origin, H)
        for tr in self.trackers.values():
            b.subject(tr)
        b.groups()
        b.hazards()
        if self.use_waves:
            b.entries()
        return b.finish()

    def forecast_if_killed(self, iids, horizon_s: float = MIN_HORIZON_S, origin_t: float | None = None,
                           clamp: bool = True) -> "MultiForecast":
        """The forecast as if the enemies iids died now (a kill's value; forum_planner_plan §4.4 item 6, the
        consistency audit): each one's tracker ends its instance and dies at the origin (its death tail), the wave
        tracker counts the kills (a wave's last member queues the next wave). The real state is left as it was."""
        if self.boss is not None:
            raise NotImplementedError("the single-boss path has its own kill handling")
        T = self.t if origin_t is None else origin_t
        keep_tr, keep_waves = self.trackers, self.waves
        try:
            self.trackers = dict(keep_tr)
            self.waves = copy.deepcopy(keep_waves)
            for i in iids:
                tr = keep_tr.get(i)
                if tr is None or tr.dead:
                    continue
                t2 = copy.copy(tr)
                t2.cur = copy.copy(tr.cur)
                t2.ends = list(tr.ends)
                t2.kill(T)
                self.trackers[i] = t2
                if self.use_waves and tr.tk in WAVE_TYPES:
                    self.waves._kill(T)
            return self.forecast(horizon_s, origin_t, clamp)
        finally:
            self.trackers, self.waves = keep_tr, keep_waves


    def reaction_state(self, iid: int) -> str | None:
        """The Control state enemy iid goes to when the hero's nail hits it now (hero_caused.json "TOOK DAMAGE" exits
        of its current state: a Clapper's Idle -> Dmg Attack, a Minister's Chase -> Range Check, ...), None: no such
        exit (the hit does not change its FSM; static FSM structure, legal in both views)."""
        tr = self.trackers.get(iid)
        if tr is None or tr.dead or tr.state is None:
            return None
        return hit_reactions().get(tr.tk, {}).get(tr.state)

    def forecast_reaction(self, iid: int, to_state: str, t_react: float, horizon_s: float = MIN_HORIZON_S,
                          origin_t: float | None = None) -> "MultiForecast | None":
        """Only enemy iid's support as if it entered to_state at game time t_react (a hit's reaction, forum_planner_plan
        R3: the planner's hit branch checks against the forecast and this), from origin_t over horizon_s. The real
        state is left as it was."""
        if self.boss is not None:
            raise NotImplementedError("the single-boss path has no hit reactions")
        tr = self.trackers.get(iid)
        if tr is None or tr.dead:
            return None
        t2 = copy.copy(tr)
        t2.cur = copy.copy(tr.cur)
        t2.ends = list(tr.ends)
        t2.enter(to_state, t_react)
        b = _Builder(self, self.t if origin_t is None else origin_t, horizon_s)
        b.subject(t2)
        b.groups()
        return b.finish()


_HIT_REACTIONS: dict | None = None


def hit_reactions() -> dict:
    """{type key: {state: the state a nail hit sends it to}} from hero_caused.json (TOOK DAMAGE exits)."""
    global _HIT_REACTIONS
    if _HIT_REACTIONS is None:
        out: dict = {}
        p = FORUM_DIR / "hero_caused.json"
        if p.exists():
            for tk, d in json.loads(p.read_text("utf-8")).get("types", {}).items():
                sp = FORUM_TYPES.get(tk)
                if sp is None or d.get("fsm", sp.control_fsm) != sp.control_fsm:
                    continue                   # the tracker follows another FSM's states
                ex = {s: e["TOOK DAMAGE"] for s, e in (d.get("exits") or {}).items() if "TOOK DAMAGE" in e}
                if ex:
                    out[tk] = ex
        _HIT_REACTIONS = out
    return _HIT_REACTIONS


def _window_union(rows: np.ndarray, offs: np.ndarray, nt: int, b_lo: np.ndarray, b_hi: np.ndarray) -> np.ndarray:
    """Union of a box sparse table's bins [b_lo, b_hi] (vectorised over rows; empty where the window misses)."""
    out = np.tile(np.array(EMPTY), (len(b_lo), 1))
    lo = np.clip(b_lo, 0, nt - 1)
    hi = np.clip(b_hi, 0, nt - 1)
    ok = (b_hi >= 0) & (b_lo < nt) & (hi >= lo)
    cur = lo.copy()
    jm = len(offs) - 1
    while True:
        rem = ok & (cur <= hi)
        if not rem.any():
            break
        L = hi - cur + 1
        j = np.minimum(np.floor(np.log2(np.maximum(L, 1))).astype(np.int64), jm)
        r1 = rows[offs[j] + cur]
        r2 = rows[offs[j] + np.maximum(hi - (1 << j) + 1, cur)]
        for a, r in ((r1, rem), (r2, rem & (L <= (1 << (j + 1))))):
            out[r, 0] = np.minimum(out[r, 0], a[r, 0])
            out[r, 1] = np.minimum(out[r, 1], a[r, 1])
            out[r, 2] = np.maximum(out[r, 2], a[r, 2])
            out[r, 3] = np.maximum(out[r, 3], a[r, 3])
        done = L <= (1 << (j + 1))
        cur = np.where(done, hi + 1, cur + (1 << j))
    return out


class _Builder:
    """One forecast's placements (fine, window, bounding box), tubes and hazard shapes."""

    def __init__(self, fc: MultiForecaster, origin: float, H: float):
        self.fc = fc
        self.tables = fc.tables
        self.store = fc.tables.store
        self.origin = origin
        self.H = H
        self.fine: list[tuple] = []          # (tid, t_ref, ax, ay, mirror)
        self.fine_m: list[tuple] = []        # (owner, family, committed, p, t_on, t_off)
        self.win: list[tuple] = []           # (tid, e0, e1, ax, ay, mirror)
        self.win_m: list[tuple] = []
        self.bb_chunks: list[tuple] = []     # bounding-box rows, in chunks of arrays (_bbox_rows)
        self.root_buf: list[tuple] = []      # later instances' roots: (tracker, fid, lo, hi, p, family), flushed
        #                                      together (groups())
        self.fam_code: dict = {}             # family name -> its code in the chunks
        # the start-time grid of later instances' pieces (s from the origin; finer near it: PIECES_S)
        ed, e = [-BIN], 0.0
        while e < H + BIN:
            e += _piece_len(e)
            ed.append(e)
        self.edges = np.array(ed)
        self.boxes: list[tuple] = []         # (owner, kind, x0, y0, x1, y1, vx, vy, grow, t_from, t_to, t_seen)
        self.paths: list[HazardPath] = []
        self.subjects: list[Subject] = []
        self.known = fc.tables.certified
        self.unknown: list[int] = []
        self.meta_group: dict = {}           # group owner -> the other Tinies its placements stand for
        self.clusters: list = []             # Tiny cluster index -> its Tinies (the group rows' gcl)
        self.arena: dict = {}                # owner -> [t_from, t_to] of its arena-wide box
        self._maestro: bool | None = None    # a Maestro in play (lazily)

    # ---- placements ----

    def _fine(self, tid, e_lo: float, e_hi: float, anchor, mirror: int, owner: int, fam, committed: bool, p: float):
        """Fine placements, one per entry bin (the template's own +-1 bin covers between them)."""
        if tid < 0:                               # kept only coarse
            self._window(tid, e_lo, e_hi, anchor, mirror, owner, fam, committed, p)
            return
        tpl = self.store.tpls[tid]
        t0, t1 = tpl.t0, tpl.t1
        ax, ay = (anchor if anchor is not None else (math.nan, math.nan))
        for e in entry_grid(e_lo, e_hi):
            if active_within(e + t0, e + t1, self.H):
                self.fine.append((tid, -e, ax, ay, mirror))
                self.fine_m.append((owner, fam, committed, p, e + t0, e + t1))

    def _window(self, tid, e_lo: float, e_hi: float, anchor, mirror: int, owner: int, fam, committed: bool,
                p: float):
        """One window placement: every entry in [e_lo, e_hi] at once (the coarse base's time pyramid)."""
        t0, t1 = self.store.span(tid)
        lo, hi = max(e_lo, -BIN - t1), min(e_hi, self.H + BIN - t0)
        if hi < lo - 1e-9:
            return
        ax, ay = (anchor if anchor is not None else (math.nan, math.nan))
        self.win.append((tid, lo, hi, ax, ay, mirror))
        self.win_m.append((owner, fam, committed, p, lo + t0, hi + t1))

    def _bbox(self, tid, e_lo: float, e_hi: float, cx: float, cy: float, hx: float, hy: float, mir: int,
              owner: int, fam, committed: bool, p: float):
        """Entries in [e_lo, e_hi] at anchors in the box (cx +- hx, cy +- hy): the template's per-bin bounding box
        over the window, grown by the anchor box; mir 0: both mirrors."""
        self._bbox_rows(tid, np.array([e_lo]), np.array([e_hi]), np.array([[cx, cy, hx, hy]]), mir, owner, fam,
                        committed, p)

    def _bbox_rows(self, tid, e0: np.ndarray, e1: np.ndarray, boxes: np.ndarray, mir: int, owner: int, fam,
                   committed: bool, p: float):
        """_bbox for n entry windows at once (boxes [n, 4]: cx, cy, hx, hy); an anchor box wider than COARSE_MAX_U
        places an arena-wide box instead."""
        t0, t1 = self.store.span(tid)
        lo = np.maximum(e0, -BIN - t1)
        hi = np.minimum(e1, self.H + BIN - t0)
        ok = hi >= lo - 1e-9
        if not ok.any():
            return
        big = ok & (np.maximum(boxes[:, 2], boxes[:, 3]) > COARSE_MAX_U)
        for i in np.flatnonzero(big):
            self._arena(owner, lo[i] + t0 - BIN, hi[i] + t1 + BIN)
        sel = ok & ~big
        n = int(sel.sum())
        if not n:
            return
        self.store.bbox_table(tid)
        code = self.fam_code.setdefault(fam, len(self.fam_code))
        self.bb_chunks.append((np.full(n, owner, np.int64), np.full(n, code, np.int64), np.full(n, committed),
                               np.full(n, p), np.full(n, tid, np.int64), lo[sel], hi[sel], boxes[sel],
                               np.full(n, mir, np.int64), lo[sel] + t0 - BIN, hi[sel] + t1 + BIN,
                               np.full(n, -1, np.int64)))

    def _arena(self, owner: int, t_from: float, t_to: float) -> None:
        """An arena-wide box of owner over [t_from, t_to]: one per owner, over the hull of its windows (a superset;
        the query loops over the box rows)."""
        a = self.arena.get(owner)
        if a is None:
            self.arena[owner] = [float(t_from), float(t_to)]
        else:
            a[0], a[1] = min(a[0], float(t_from)), max(a[1], float(t_to))

    def _place_anchor(self, tid, lo, hi, anc, owner, fam, committed, p):
        (ax, ay), m, sd = anc
        if sd > 1e-9:                             # an anchor known to a box (the vision view's offset spread)
            self._bbox(tid, lo, hi, ax, ay, sd, sd, m, owner, fam, committed, p)
        elif tid >= 0 and hi - lo <= FINE_MAX_BINS * BIN + 1e-9:
            self._fine(tid, lo, hi, (ax, ay), m, owner, fam, committed, p)
        else:
            self._window(tid, lo, hi, (ax, ay), m, owner, fam, committed, p)

    # ---- one enemy ----

    def _walk_waiting(self, tr: EnemyTracker) -> bool:
        """An enemy in a waiting state is walked (its entry may start) only when it may enter soon: a pooled Tiny
        while a Maestro is in play (a summon), a wave member when its wave is queued or no wave is known yet."""
        fc = self.fc
        if tr.table.spec.pooled:
            return self._maestro_in_play()
        if not fc.use_waves or fc.t_wake is None:
            return True
        nw = fc.waves.next_window()
        if nw is None:
            return False
        return tr.tk in FORUM_WAVES[nw[0]].types and nw[1] - self.origin <= self.H + ENTRY_LAG_S

    def _maestro_in_play(self) -> bool:
        if self._maestro is None:
            self._maestro = any(t.tk == MAESTRO and t.in_play and not t.dead for t in self.fc.trackers.values())
        return self._maestro

    def _wave_wake(self, tr: EnemyTracker) -> float | None:
        """The earliest game time a waiting wave member can leave its waiting state: its queued wave's earliest
        activation (WaveTracker); None when that does not bound it (in play, pooled, no wave known)."""
        fc = self.fc
        if tr.in_play or tr.table.spec.pooled or not fc.use_waves or fc.t_wake is None:
            return None
        nw = fc.waves.next_window()
        if nw is None or tr.tk not in FORUM_WAVES[nw[0]].types or not math.isfinite(nw[1]):
            return None
        return nw[1]

    def subject(self, tr: EnemyTracker) -> None:
        tt = tr.table
        sp = tt.spec
        T = self.origin
        H = self.H
        tables = self.tables
        tubes = tables.tubes
        cur = tr.cur
        if tr.dead and tr.t_dead is not None and tr.death_box is not None and T - tr.t_dead <= DEATH_TAIL_S:
            self.boxes.append((tr.iid, "death", *tr.death_box, 0.0, 0.0, None, -BIN, tr.t_dead + DEATH_TAIL_S - T,
                               0.0))
        self._tails(tr)
        # a killed Tiny comes back only through a Maestro's summon: walked on after its death only while one is in play
        if tr.dead and (not sp.pooled or not self._maestro_in_play()) or tr.state is None or tr.t_entry is None:
            if not tr.dead and tr.state is None and tr.seen_T > -math.inf and not tr.hidden:
                self.unknown.append(tr.iid)
            self.subjects.append(self._subject_row(tr, False, math.inf))
            return
        if not tr.in_play and not self._walk_waiting(tr):
            self.subjects.append(self._subject_row(tr, False, math.inf))
            return
        if tr.state not in tt.dwell and tr.in_play:
            self.unknown.append(tr.iid)
        age = T - tr.t_entry
        dw = tt.dwell.get(tr.state)
        # overdue: past its longest logged dwell; or so old that the memoised walk from its entry (cut at WALK_CAP_S)
        # would not reach the horizon's end (Minister Chase up to 5.9 s, a Tiny dead 10.6 s): walked from the origin,
        # the state ending at any time from the next frame (a superset of its dwell window)
        overdue = dw is not None and (age > dw[1] + DWELL_SLACK_S or age + H + BIN > WALK_CAP_S)
        wake = self._wave_wake(tr)
        if wake is not None:
            overdue = True
        ctx = (cur.family, cur.start) if cur is not None else None
        cur_nodes, roots = self.fc.walks.get(tt, tr.state, ctx, tr.dead, overdue)
        ref = T if overdue else tr.t_entry
        if wake is not None:
            # a waiting wave member leaves its waiting state once BattleScene activates its wave, not before
            ref = max(T, wake - BIN)
        idle_tube = (cur is not None and cur.family == sp.idle_family and not tr.dead and tr.pos is not None
                     and T - tr.seen_T <= TUBE_MAX_AGE_S and tt.tk in tubes.growth)
        anc = (cur.anchor, cur.mirror, cur.sd) if cur is not None and cur.anchor is not None else None
        committed_now = cur is not None and cur.family != sp.idle_family
        if committed_now and anc is not None:
            # the current attack's family template from its start (the family-wide union)
            fid = tables.key_id(cur.family, None, "anchor")
            if fid is not None:
                self._place_anchor(fid, cur.t_start - T, cur.t_start - T, anc, tr.iid, cur.family, True, 1.0)
        if anc is not None and not (idle_tube and cur.family == sp.idle_family):
            for nd in cur_nodes:
                if nd.current:
                    lo = hi = tr.t_entry - T          # the current state: its entry
                else:
                    lo, hi = max(ref + nd.lo - T, BIN), max(ref + nd.hi - T, BIN)
                if lo > H + BIN:
                    continue
                key_state = TAIL if nd.state == TAIL else nd.state
                tid = tables.key_id(nd.family, key_state, "anchor")
                if tid is not None:
                    self._place_anchor(tid, lo, hi, anc, tr.iid, nd.family, nd.family != sp.idle_family, nd.p)
                if nd.family == sp.entry_family:
                    wid = tables.key_id(nd.family, key_state, "world_all")
                    if wid is not None:
                        self._window(wid, lo, hi, None, 1, tr.iid, nd.family, True, nd.p)
        if committed_now and cur.re_anchor is not None:
            # re-anchored (forum.md 15.1): an attack that moved since its start (the anchor frame's templates hold the
            # logged travel only) is also the family walk of an instance starting at the start state it entered,
            # anchored where the enemy was then (13.13: the Clawmaiden's lunge after a 3.3 u flight)
            rid = self.fc.family_walk_id(tt, cur.family, cur.re_state, "anchor")
            if rid is not None:
                (rx, ry), rsd = cur.re_anchor, cur.re_sd
                self._bbox(rid, cur.re_t - T, cur.re_t - T, rx, ry, rsd, rsd, cur.re_mirror, tr.iid, cur.family,
                           True, 1.0)
        if cur is not None and anc is None and not (idle_tube and cur.family == sp.idle_family):
            # the current instance's anchor is not known (not exported at its start): its family walk from the
            # start, anchored where the enemy is now
            self._place_family(tr, cur.family, cur.start, cur.t_start - T, cur.t_start - T, 1.0, committed_now)
        t_strike = math.inf
        for nd in roots:
            lo, hi = max(ref + nd.lo - T, BIN), max(ref + nd.hi - T, BIN)
            if lo > H + BIN:
                continue
            if nd.family != sp.idle_family:
                t_strike = min(t_strike, lo)
            fid = self.fc.family_walk_id(tt, nd.family, nd.start, "anchor")
            if fid is not None:
                self.root_buf.append((tr, fid, lo, min(hi, H + BIN), nd.p, nd.family))
            if nd.family == sp.entry_family:
                wid = self.fc.family_walk_id(tt, nd.family, nd.start, "world_all")
                if wid is not None:
                    self._bbox(wid, lo, hi, 0.0, 0.0, 0.0, 0.0, 1, tr.iid, nd.family, False, nd.p)
        if idle_tube:
            self._idle_tube(tr)
        # (a waiting wave member's collider cannot move before its wave is activated)
        if self.fc.collider_tube and T - tr.seen_T <= TUBE_MAX_AGE_S and (wake is None or wake - T <= COLLIDER_TUBE_S):
            b = tr.seen_box
            if b is None and tr.pos is not None and tt.tk in tubes.hull:
                h = tubes.hull[tt.tk]
                b = (tr.pos[0] + h[0], tr.pos[1] + h[1], tr.pos[0] + h[2], tr.pos[1] + h[3])
            if b is not None:
                self.boxes.append((tr.iid, "collider", *b, 0.0, 0.0, ("speed", tubes.speed.get(tt.tk, 60.0)),
                                   -BIN, COLLIDER_TUBE_S, tr.seen_T - T))
        self.subjects.append(self._subject_row(tr, True, t_strike))

    def _subject_row(self, tr: EnemyTracker, alive: bool, t_strike: float) -> Subject:
        c = tr.cur
        committed = c is not None and c.family != tr.table.spec.idle_family
        return Subject(tr.iid, tr.tk, alive and not tr.dead, tr.in_play, committed, None if c is None else c.family,
                       tr.state, tr.hp_est, tr.hp_sd, tr.pos, 0.0, t_strike)

    def _tails(self, tr: EnemyTracker) -> None:
        T = self.origin
        for inst in tr.ends:
            if inst.t_end is None or T - inst.t_end > TAIL_KEEP_S or inst.anchor is None:
                continue
            tid = self.tables.key_id(inst.family, TAIL, "anchor")
            if tid is not None:
                e = inst.t_end - T
                self._place_anchor(tid, e, e, (inst.anchor, inst.mirror, inst.sd), tr.iid, inst.family, True, 1.0)

    def _start_boxes(self, tr: EnemyTracker, s_lo: np.ndarray, s_hi: np.ndarray) -> np.ndarray | None:
        """Where instances starting within [s_lo, s_hi] (s from the origin, arrays) are anchored: the transform
        dead-reckoned to those times, grown by the type's idle growth since the sighting (and the view's anchor
        spread): [n, 4] (cx, cy, hx, hy), or None without a position."""
        if tr.pos is None:
            return None
        s_lo, s_hi = np.maximum(s_lo, 0.0), np.maximum(s_hi, 0.0)
        vx, vy = tr.vel
        g = self.tables.tubes.g(tr.tk, (self.origin - tr.seen_T) + s_hi) + tr.pos_sd
        mid = 0.5 * (s_lo + s_hi)
        half = 0.5 * (s_hi - s_lo)
        return np.stack([tr.pos[0] + vx * mid, tr.pos[1] + vy * mid, abs(vx) * half + g, abs(vy) * half + g], axis=1)

    def _pieces(self, lo: float, hi: float) -> tuple[np.ndarray, np.ndarray]:
        """[lo, hi] (s from the origin, within the horizon) cut at the forecast's start-time grid (PIECES_S: finer
        near the origin): the pieces' (e0, e1)."""
        hi = min(hi, self.H + BIN)
        if hi < lo - 1e-9:
            return np.zeros(0), np.zeros(0)
        ed = self.edges
        k0 = max(0, int(np.searchsorted(ed, lo, "right")) - 1)
        k1 = int(np.searchsorted(ed, hi, "left"))
        a = np.maximum(ed[k0:k1], lo)
        b = np.minimum(ed[k0 + 1:k1 + 1], hi)
        if not len(a):
            return np.array([lo]), np.array([hi])
        return a, b

    def _place_family(self, tr: EnemyTracker, fam: str, start: str, lo: float, hi: float, p: float,
                      committed: bool = False, boxes_of=None, owner: int | None = None):
        """An instance of (fam, start) starting within [lo, hi]: its family walk boxes at the anchor box of each
        start piece, both mirrors; an entry family also in its world frame."""
        fid = self.fc.family_walk_id(tr.table, fam, start, "anchor")
        wid = self.fc.family_walk_id(tr.table, fam, start, "world_all") if fam == tr.table.spec.entry_family \
            else None
        owner = tr.iid if owner is None else owner
        e0s, e1s = self._pieces(lo, hi)
        if not len(e0s):
            return
        if fid is not None:
            bs = self._start_boxes(tr, e0s, e1s) if boxes_of is None else boxes_of(e0s, e1s)
            if bs is not None:
                self._bbox_rows(fid, e0s, e1s, bs, 0, owner, fam, committed, p)
        if wid is not None:
            self._bbox(wid, float(e0s[0]), float(e1s[-1]), 0.0, 0.0, 0.0, 0.0, 1, owner, fam, committed, p)

    def _idle_tube(self, tr: EnemyTracker) -> None:
        tubes = self.tables.tubes
        b = tr.seen_box
        if b is None:
            h = tubes.hull.get(tr.tk)
            if h is None or tr.pos is None:
                return
            b = (tr.pos[0] + h[0], tr.pos[1] + h[1], tr.pos[0] + h[2], tr.pos[1] + h[3])
        self.boxes.append((tr.iid, "idle", *b, tr.vel[0], tr.vel[1], ("idle", tr.tk), -BIN, self.H + BIN,
                           tr.seen_T - self.origin))

    def groups(self) -> None:
        """Place every buffered later-instance root at once (vectorised): each root's start window cut at the
        start-time grid, each piece's anchor box from its enemy's dead-reckoned transform and idle growth; Tiny
        group placement: with >= tiny_group Tinies, the Tinies in one cell of a TINY_CLUSTER_U grid form a cluster
        whose roots of one family walk share a row per grid piece (the union of their windows and anchor boxes)."""
        buf = self.root_buf
        self.root_buf = []
        if not buf:
            return
        R = len(buf)
        num = np.array([(b[1], b[2], b[3], b[4]) for b in buf], np.float64)
        fid = num[:, 0].astype(np.int64)
        lo, hi, p = num[:, 1], num[:, 2], num[:, 3]
        trs = [b[0] for b in buf]
        by_iid = {t.iid: t for t in trs}
        tlist = list(by_iid.values())
        pos_of = {iid: i for i, iid in enumerate(by_iid)}
        sidx = np.array([pos_of[t.iid] for t in trs], np.int64)
        ok_pos = np.array([t.pos is not None for t in tlist])
        tv = np.array([(t.pos[0], t.pos[1], t.vel[0], t.vel[1], self.origin - t.seen_T, t.pos_sd)
                       if t.pos is not None else (0.0, 0.0, t.vel[0], t.vel[1], self.origin - t.seen_T, t.pos_sd)
                       for t in tlist], np.float64)
        px, py, vx, vy, age, sd = tv.T
        keep = ok_pos[sidx] & (hi >= lo - 1e-9)
        if not keep.any():
            return
        # pieces on the grid
        E = self.edges
        k0 = np.maximum(np.searchsorted(E, lo, "right") - 1, 0)
        k1 = np.maximum(np.searchsorted(E, hi, "left"), k0 + 1)
        cnt = np.where(keep, k1 - k0, 0)
        ri = np.repeat(np.arange(R), cnt)
        if not len(ri):
            return
        off = np.arange(len(ri)) - np.repeat(np.cumsum(cnt) - cnt, cnt)
        k = np.minimum(k0[ri] + off, len(E) - 2)
        e0 = np.maximum(E[k], lo[ri])
        e1 = np.minimum(E[k + 1], hi[ri])
        good = e1 >= e0 - 1e-9
        ri, k, e0, e1 = ri[good], k[good], e0[good], e1[good]
        s = sidx[ri]
        s_lo, s_hi = np.maximum(e0, 0.0), np.maximum(e1, 0.0)
        g = np.empty(len(ri))
        tub = self.tables.tubes
        tks = [t.tk for t in tlist]
        if len(set(tks)) == 1:
            g[:] = tub.g(tks[0], age[s] + s_hi)
        else:
            tcode = {tk: i for i, tk in enumerate(dict.fromkeys(tks))}
            tc = np.array([tcode[tk] for tk in tks], np.int64)[s]
            for tk, c_ in tcode.items():             # one growth lookup per type
                m = tc == c_
                g[m] = tub.g(tk, age[s[m]] + s_hi[m])
        g += sd[s]
        mid, half = 0.5 * (s_lo + s_hi), 0.5 * (s_hi - s_lo)
        x0 = px[s] + vx[s] * mid - np.abs(vx[s]) * half - g
        x1 = px[s] + vx[s] * mid + np.abs(vx[s]) * half + g
        y0 = py[s] + vy[s] * mid - np.abs(vy[s]) * half - g
        y1 = py[s] + vy[s] * mid + np.abs(vy[s]) * half + g
        owner = np.array([t.iid for t in tlist], np.int64)[s]
        fam_c = np.array([self.fam_code.setdefault(b[5], len(self.fam_code)) for b in buf], np.int64)[ri]
        # Tiny clusters
        tiny = np.array([t.table.spec.pooled for t in tlist])
        if self.fc.tiny_group and int(tiny.sum()) >= self.fc.tiny_group:
            # clusters are the cells of a fixed TINY_CLUSTER_U grid: a cluster never spans more than a cell, and a
            # Tiny gone (killed) never joins two others into one (forum_planner_plan §4.4 item 6)
            ti = np.flatnonzero(tiny)
            cell = (np.floor(px[ti] / TINY_CLUSTER_U).astype(np.int64) + 1024) * 4096 \
                + np.floor(py[ti] / TINY_CLUSTER_U).astype(np.int64) + 1024
            cl = np.full(len(tlist), -1, np.int64)
            cl[ti] = np.unique(cell, return_inverse=True)[1].ravel()
            grp = tiny[s] & (cl[s] >= 0)
            if grp.any():
                gi = np.flatnonzero(grp)
                # one group per (cluster, family walk, grid piece): a 1-d key (np.unique over rows is slow)
                fu, fi = np.unique(fid[ri[gi]], return_inverse=True)
                nk = len(E)
                key = (cl[s[gi]] * len(fu) + fi.ravel()) * nk + k[gi]
                ukey1, inv = np.unique(key, return_inverse=True)
                inv = inv.ravel()
                ukey = np.stack([ukey1 // (len(fu) * nk), fu[(ukey1 // nk) % len(fu)]], axis=1)
                n = len(ukey)
                G = {"e0": np.full(n, np.inf), "e1": np.full(n, -np.inf), "x0": np.full(n, np.inf),
                     "x1": np.full(n, -np.inf), "y0": np.full(n, np.inf), "y1": np.full(n, -np.inf),
                     "p": np.zeros(n)}
                np.minimum.at(G["e0"], inv, e0[gi])
                np.maximum.at(G["e1"], inv, e1[gi])
                np.minimum.at(G["x0"], inv, x0[gi])
                np.maximum.at(G["x1"], inv, x1[gi])
                np.minimum.at(G["y0"], inv, y0[gi])
                np.maximum.at(G["y1"], inv, y1[gi])
                np.maximum.at(G["p"], inv, p[ri[gi]])
                first = np.zeros(n, np.int64)
                first[inv[::-1]] = gi[::-1]                    # a representative row per group (its owner)
                g_owner = owner[first]
                # the Tinies a group row stands for: its cluster's (occupied_without / occupied_only keep a group row
                # while one of them is in, support_set counts it for each of them)
                cl_members: dict = defaultdict(set)
                for t_i in ti:
                    cl_members[int(cl[t_i])].add(tlist[t_i].iid)
                self.clusters = [frozenset(cl_members[c_]) for c_ in range(int(cl.max()) + 1)]
                for o, c_ in {(int(a), int(b)) for a, b in zip(g_owner, ukey[:, 0])}:
                    m = cl_members[c_] - {o}
                    if m:
                        self.meta_group.setdefault(o, set()).update(m)
                rest = ~grp
                self._emit_bbox(np.concatenate([fid[ri[rest]], ukey[:, 1]]),
                                np.concatenate([e0[rest], G["e0"]]), np.concatenate([e1[rest], G["e1"]]),
                                np.concatenate([x0[rest], G["x0"]]), np.concatenate([y0[rest], G["y0"]]),
                                np.concatenate([x1[rest], G["x1"]]), np.concatenate([y1[rest], G["y1"]]),
                                np.concatenate([owner[rest], g_owner]), np.concatenate([fam_c[rest], fam_c[first]]),
                                np.concatenate([p[ri[rest]], G["p"]]),
                                np.concatenate([np.full(int(rest.sum()), -1, np.int64), ukey[:, 0]]))
                return
        self._emit_bbox(fid[ri], e0, e1, x0, y0, x1, y1, owner, fam_c, p[ri])

    def _emit_bbox(self, tid, e0, e1, x0, y0, x1, y1, owner, fam_c, p, gcl=None) -> None:
        """Bounding-box rows of later instances (both mirrors, not committed): anchor boxes from their edges; an
        anchor box wider than COARSE_MAX_U is an arena-wide box. gcl: a Tiny group row's cluster (-1: one enemy's)."""
        if gcl is None:
            gcl = np.full(len(tid), -1, np.int64)
        cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
        hx, hy = 0.5 * (x1 - x0), 0.5 * (y1 - y0)
        ut, inv = np.unique(tid, return_inverse=True)
        spans = np.array([self.store.span(int(t)) for t in ut])
        t0, t1 = spans[inv, 0], spans[inv, 1]
        lo = np.maximum(e0, -BIN - t1)
        hi = np.minimum(e1, self.H + BIN - t0)
        ok = hi >= lo - 1e-9
        big = ok & (np.maximum(hx, hy) > COARSE_MAX_U)
        if big.any():
            # one arena box per owner over its rows' hull (a dead Tiny walked for a summon: ~160 rows a tick in wave
            # 6); the boxes are filtered by owner: a group row's once per Tiny of its cluster
            a0, a1 = lo + t0 - BIN, hi + t1 + BIN
            for grp_rows in (False, True):
                m = big & ((gcl >= 0) == grp_rows)
                if not m.any():
                    continue
                u, inv = np.unique(gcl[m] if grp_rows else owner[m], return_inverse=True)
                inv = inv.ravel()
                mn, mx = np.full(len(u), np.inf), np.full(len(u), -np.inf)
                np.minimum.at(mn, inv, a0[m])
                np.maximum.at(mx, inv, a1[m])
                for j, key in enumerate(u.tolist()):
                    for o in (self.clusters[key] if grp_rows else (key,)):
                        self._arena(int(o), mn[j], mx[j])
        sel = ok & ~big
        n = int(sel.sum())
        if not n:
            return
        for t in ut:
            self.store.bbox_table(int(t))
        self.bb_chunks.append((owner[sel], fam_c[sel], np.zeros(n, bool), p[sel], tid[sel], lo[sel], hi[sel],
                               np.stack([cx[sel], cy[sel], hx[sel], hy[sel]], axis=1), np.zeros(n, np.int64),
                               lo[sel] + t0[sel] - BIN, hi[sel] + t1[sel] + BIN, gcl[sel]))

    # ---- hazards ----

    def hazards(self) -> None:
        fc = self.fc
        T = self.origin
        det = set()
        if fc.self_templates != "all":
            for p in fc.hazards.paths(T, self.H):
                self.paths.append(p)
                if not p.predicted and fc.view == ORACLE:
                    det.add(p.iid)
        for iid, h in fc.self_haz.items():
            tk, armed, arm_T, arm_pos, last_T, pos, rel, vel = h
            if T - last_T > HAZARD_GONE_S:
                continue
            use_self = iid not in det and fc.self_templates != "none"
            if use_self:
                sid = self.tables.self_id(tk)
                if sid is not None:
                    if armed and arm_T is not None:
                        e = arm_T - T
                        self._fine(sid, e, e, arm_pos, 1, iid, f"ent/{tk}", True, 1.0)
                    elif T - last_T <= 2.5 * BIN:      # may arm from the next frame on, where it is now
                        self._window(sid, BIN, self.H, pos, 1, iid, f"ent/{tk}", True, 1.0)
            if fc.collider_tube and rel is not None:
                b = (pos[0] + rel[0], pos[1] + rel[1], pos[0] + rel[2], pos[1] + rel[3])
                self.boxes.append((iid, "hazard", *b, vel[0], vel[1], ("speed", HAZARD_DV_U_S), -BIN,
                                   COLLIDER_TUBE_S, last_T - T))

    # ---- entries of the next wave ----

    def entries(self) -> None:
        nw = self.fc.waves.next_window()
        if nw is None:
            return
        w, a_lo, a_hi = nw
        lo, hi = a_lo - self.origin, (a_hi if math.isfinite(a_hi) else self.origin + self.H) - self.origin
        if lo > self.H + BIN:
            return
        present = {tr.tk for tr in self.fc.trackers.values() if not tr.dead}
        for tk in sorted(set(FORUM_WAVES[w].types)):
            if tk in present and FORUM_WAVES[w].active_from_load:
                continue                       # in the export already, walked from its waiting state
            tt = self.tables.types.get(tk)
            if tt is None:
                continue
            wid = self.tables.key_id(tt.spec.entry_family, None, "world_all")
            if wid is not None:
                self._window(wid, lo, hi + ENTRY_LAG_S, None, 1, ENTRY_OWNER - w, tt.spec.entry_family, False, 1.0)

    def finish(self) -> "MultiForecast":
        for o, (a, b) in self.arena.items():
            self.boxes.append((o, "arena", *ARENA_BOX, 0.0, 0.0, None, a, b, 0.0))
        out = MultiForecast(self.fc, self.origin, self.H)
        out.P = PlaceBatch.from_rows(self.fine)
        out.pm = _meta_arrays(self.fine_m)
        out.W = WinBatch.from_rows(self.win)
        out.wm = _meta_arrays(self.win_m)
        out.bb = _bb_arrays(self.bb_chunks, self.store, self.fam_code)
        out.boxes = self.boxes
        out.paths = self.paths
        out.subjects = self.subjects
        out.known = bool(self.known and not self.unknown)
        out.unknown = self.unknown
        out.groups = self.meta_group
        out.clusters = self.clusters
        return out


def _meta_arrays(m: list[tuple]) -> dict:
    return {"owner": np.array([x[0] for x in m], np.int64), "family": [x[1] for x in m],
            "committed": np.array([x[2] for x in m], bool), "prob": np.array([x[3] for x in m], np.float64),
            "on": np.array([x[4] for x in m], np.float64), "off": np.array([x[5] for x in m], np.float64)}


def _bb_arrays(chunks: list, store, fam_code: dict | None = None) -> dict:
    """The bounding-box placements as arrays: owner, family (one name per row), committed, prob, tid, e0, e1, cx,
    cy, hx, hy, mir, on, off, gcl (a Tiny group row's cluster, else -1), and their sparse tables' level offsets, bins
    and t0."""
    if not chunks:
        z = np.zeros(0)
        zi = np.zeros(0, np.int64)
        return {"owner": zi, "family": [], "committed": np.zeros(0, bool), "prob": z, "tid": zi, "e0": z, "e1": z,
                "cx": z, "cy": z, "hx": z, "hy": z, "mir": zi, "on": z, "off": z, "gcl": zi,
                "loff": np.zeros((0, JMAX + 1), np.int64), "nt": zi, "t0": z}
    cat = [np.concatenate([c[i] for c in chunks]) for i in range(len(chunks[0]))]
    names = np.empty(max(len(fam_code or {}), 1), object)          # family code -> name
    for k, v in (fam_code or {}).items():
        names[v] = k
    tid = cat[4]
    uniq, inv = np.unique(tid, return_inverse=True)
    tabs = [store.bbox_table(int(t)) for t in uniq]
    loff = np.stack([t[0] for t in tabs])[inv]
    nt = np.array([t[1] for t in tabs], np.int64)[inv]
    t0 = np.array([t[2] for t in tabs], np.float64)[inv]
    box = cat[7]
    return {"owner": cat[0], "family": names[cat[1]], "committed": cat[2], "prob": cat[3],
            "tid": tid, "e0": cat[5], "e1": cat[6], "cx": box[:, 0].copy(), "cy": box[:, 1].copy(),
            "hx": box[:, 2].copy(), "hy": box[:, 3].copy(), "mir": cat[8], "on": cat[9], "off": cat[10],
            "gcl": cat[11], "loff": np.ascontiguousarray(loff), "nt": nt, "t0": t0}


@numba.njit(cache=True)
def _bbox_boxes(tk, rows, loff, nt, t0, e0, e1, cx, cy, hx, hy, mir, bin_s):
    """World boxes [K, T] of bounding-box placements: the union of the template's per-bin boxes over the template
    times an entry in [e0, e1] gives at tk (the sparse table's two lookups; mirrored: both mirrors when mir is 0),
    grown by the anchor box."""
    K = loff.shape[0]
    T = tk.shape[0]
    jmax = loff.shape[1] - 1
    bx0 = np.zeros((K, T))
    by0 = np.zeros((K, T))
    bx1 = np.zeros((K, T))
    by1 = np.zeros((K, T))
    ok = np.zeros((K, T), np.bool_)
    for k in range(K):
        for t in range(T):
            b_lo = int(np.rint((tk[t] - e1[k] - t0[k]) / bin_s))
            b_hi = int(np.rint((tk[t] - e0[k] - t0[k]) / bin_s))
            if b_hi < 0 or b_lo >= nt[k]:
                continue
            if b_lo < 0:
                b_lo = 0
            if b_hi > nt[k] - 1:
                b_hi = nt[k] - 1
            x0, y0, x1, y1 = np.inf, np.inf, -np.inf, -np.inf
            b = b_lo
            while b <= b_hi:
                L = b_hi - b + 1
                j = 0
                while j < jmax and (1 << (j + 1)) <= L:
                    j += 1
                r = loff[k, j] + b
                x0 = min(x0, rows[r, 0])
                y0 = min(y0, rows[r, 1])
                x1 = max(x1, rows[r, 2])
                y1 = max(y1, rows[r, 3])
                if L <= (1 << (j + 1)):
                    r = loff[k, j] + b_hi - (1 << j) + 1
                    x0 = min(x0, rows[r, 0])
                    y0 = min(y0, rows[r, 1])
                    x1 = max(x1, rows[r, 2])
                    y1 = max(y1, rows[r, 3])
                    break
                b += 1 << j
            if x0 > x1:
                continue
            if mir[k] == 0:
                X0, X1 = min(x0, -x1), max(x1, -x0)
            elif mir[k] < 0:
                X0, X1 = -x1, -x0
            else:
                X0, X1 = x0, x1
            bx0[k, t] = cx[k] - hx[k] + X0
            bx1[k, t] = cx[k] + hx[k] + X1
            by0[k, t] = cy[k] - hy[k] + y0
            by1[k, t] = cy[k] + hy[k] + y1
            ok[k, t] = True
    return bx0, by0, bx1, by1, ok


@numba.njit(cache=True, parallel=True)
def _box_hits(x, y, bx0, by0, bx1, by1, ok, hx, hy):
    """[N, T]: the box of half-extents (hx, hy) centred at (x, y) [N, T] meets one of K boxes [K, T] where ok."""
    N, T = x.shape
    K = bx0.shape[0]
    out = np.zeros((N, T), np.bool_)
    for n in numba.prange(N):
        for t in range(T):
            px, py = x[n, t], y[n, t]
            if px != px:
                continue
            for k in range(K):
                if ok[k, t] and px >= bx0[k, t] - hx and px <= bx1[k, t] + hx and py >= by0[k, t] - hy \
                        and py <= by1[k, t] + hy:
                    out[n, t] = True
                    break
    return out


def _mask(meta: dict, ids=None, names=None, only=None, committed_only: bool = False,
          clusters: list | None = None) -> np.ndarray:
    """Which placements remain: not owned by ids, not of a family / hazard named in names (a suffix match), owned
    by one of only, committed. A Tiny group row (meta gcl >= 0) stands for every Tiny of its cluster: it stays while
    one of them is not in ids, and it is one of only's when one of them is."""
    owner = meta["owner"]
    m = np.ones(len(owner), bool)
    gcl = meta.get("gcl")
    grp = gcl is not None and clusters and len(gcl) and bool((gcl >= 0).any())
    gi = np.maximum(gcl, 0) if grp else None
    if ids:
        out = np.isin(owner, np.fromiter(ids, np.int64))
        if grp:
            gone = np.array([c <= ids for c in clusters], bool)
            out = np.where(gcl >= 0, gone[gi], out)
        m &= ~out
    if names:
        m &= ~np.array([any(str(f).endswith(n) for n in names) for f in meta["family"]], bool)
    if only is not None:
        inc = np.isin(owner, np.fromiter(only, np.int64)) if only else np.zeros(len(owner), bool)
        if grp:
            hit = np.array([bool(c & only) for c in clusters], bool)
            inc = np.where(gcl >= 0, hit[gi], inc)
        m &= inc
    if committed_only:
        m &= meta["committed"]
    return m


class MultiForecast:
    """One tick's forecast (see the module docstring). With a wrapped boss it is a proxy of the boss Forecast: every
    read this class does not answer itself goes to the boss (its origin, horizon, placements, det, caches, _occ, ...),
    every write goes to the boss (bell_hit_monitor.zone swaps f.det and resets the path caches), so a consumer of a
    single-boss Forecast sees the same object behaviour."""

    def __init__(self, fc: MultiForecaster, origin_t: float, horizon: float, boss=None):
        object.__setattr__(self, "_fc", fc)
        object.__setattr__(self, "_cache", {})
        if boss is not None:
            object.__setattr__(self, "boss_fc", boss)
            return
        self.boss_fc = None
        self.origin_t = origin_t
        self.horizon = horizon
        self.P = PlaceBatch.from_rows([])
        self.pm = _meta_arrays([])
        self.W = WinBatch.from_rows([])
        self.wm = _meta_arrays([])
        self.bb = _bb_arrays([], None)
        self.boxes: list = []
        self.paths: list[HazardPath] = []
        self.subjects: list[Subject] = []
        self.known = False
        self.unknown: list = []
        self.groups: dict = {}               # Tiny group owner -> the other Tinies of its cluster
        self.clusters: list = []             # Tiny cluster index (bb["gcl"]) -> the Tinies its group rows stand for

    def __getattr__(self, name):
        # the wrapped boss forecast answers everything this class does not define (boss_box, body_polys, det, ...)
        b = self.__dict__.get("boss_fc")
        if b is not None:
            return getattr(b, name)
        raise AttributeError(name)

    def __setattr__(self, name, value):
        b = self.__dict__.get("boss_fc")
        if b is not None:
            setattr(b, name, value)
        else:
            object.__setattr__(self, name, value)

    @property
    def fc(self):
        return self.boss_fc.fc if self.boss_fc is not None else self._fc

    @property
    def n_fine(self) -> int:
        return len(self.P)

    @property
    def n_window(self) -> int:
        return len(self.W)

    @property
    def n_bbox(self) -> int:
        return len(self.bb["owner"])

    @property
    def placements(self):
        if self.boss_fc is not None:
            return self.boss_fc.placements
        return range(self.n_fine + self.n_window + self.n_bbox)

    @property
    def roots(self):
        if self.boss_fc is not None:
            return self.boss_fc.roots
        out = []
        for tr in self._fc.trackers.values():
            r, _ = tr.roots(self.origin_t)
            out += r
        return out

    @property
    def nodes(self):
        return self.boss_fc.nodes if self.boss_fc is not None else []

    # ---- component queries ----

    @staticmethod
    def _active(meta: dict, tk: np.ndarray, sel) -> np.ndarray:
        act = (meta["off"] >= tk.min() - BIN) & (meta["on"] <= tk.max() + BIN)
        return act if sel is None else act & sel

    def _fine_occ(self, x, y, tk, sel=None) -> np.ndarray:
        out = np.zeros(np.shape(x), bool)
        if not len(self.P):
            return out
        act = self._active(self.pm, tk, sel)
        if not act.any():
            return out
        P = self.P if act.all() else self.P.take(np.flatnonzero(act))
        return self._fc.tables.store.query(P, x, y, tk, out)

    def _win_occ(self, x, y, tk, sel=None) -> np.ndarray:
        out = np.zeros(np.shape(x), bool)
        if not len(self.W):
            return out
        act = self._active(self.wm, tk, sel)
        if not act.any():
            return out
        W = self.W if act.all() else self.W.take(np.flatnonzero(act))
        return self._fc.tables.store.query_win(W, x, y, tk, out)

    def _bbox_occ(self, x, y, tk, sel=None) -> np.ndarray:
        x = np.asarray(x, np.float64)
        shp = x.shape
        bb = self.bb
        if not len(bb["owner"]):
            return np.zeros(shp, bool)
        idx = np.flatnonzero(self._active(bb, tk, sel))
        if not len(idx):
            return np.zeros(shp, bool)
        rows = self._fc.tables.store.bb_rows()
        g = lambda k: np.ascontiguousarray(bb[k][idx])  # noqa: E731
        bx = _bbox_boxes(np.ascontiguousarray(tk, np.float64), rows, g("loff"), g("nt"), g("t0"), g("e0"), g("e1"),
                         g("cx"), g("cy"), g("hx"), g("hy"), g("mir"), BIN)
        T = shp[-1]
        x2 = np.ascontiguousarray(x.reshape(-1, T))
        y2 = np.ascontiguousarray(np.asarray(y, np.float64).reshape(-1, T))
        # the templates already hold the hero hurtbox's dilation: a point test of the centre
        return _box_hits(x2, y2, *bx, 0.0, 0.0).reshape(shp)

    def _box_arrays(self, tk: np.ndarray, kinds=None, exclude=None, only=None):
        key = (len(tk), float(tk[0]) if len(tk) else 0.0, float(tk[-1]) if len(tk) else 0.0, kinds,
               None if not exclude else frozenset(exclude), None if only is None else frozenset(only))
        if key in self._cache:
            return self._cache[key]
        tubes = self._fc.tables.tubes
        rows = []
        for (owner, kind, x0, y0, x1, y1, vx, vy, grow, t_from, t_to, t_seen) in self.boxes:
            if kinds is not None and kind not in kinds:
                continue
            if exclude and owner in exclude or only is not None and owner not in only:
                continue
            dt = tk - t_seen
            if grow is None:
                g = np.zeros(len(tk))
            elif grow[0] == "idle":
                g = tubes.g(grow[1], dt)
            else:
                g = grow[1] * np.maximum(dt, 0.0)
            ok = (tk >= t_from - 1e-9) & (tk <= t_to + 1e-9)
            if kind == "idle":
                ok &= dt >= 0
            rows.append((x0 + vx * dt - g, y0 + vy * dt - g, x1 + vx * dt + g, y1 + vy * dt + g, ok))
        r = None if not rows else tuple(
            np.ascontiguousarray(np.stack([q[i] for q in rows]), np.float64 if i < 4 else np.bool_) for i in range(5))
        if len(self._cache) > 64:
            self._cache.clear()
        self._cache[key] = r
        return r

    def _box_occ(self, x, y, tk, kinds=None, exclude=None, only=None) -> np.ndarray:
        x = np.asarray(x, np.float64)
        shp = x.shape
        arr = self._box_arrays(tk, kinds, exclude, only)
        if arr is None:
            return np.zeros(shp, bool)
        hx, hy = self._fc.half
        T = shp[-1]
        x2 = np.ascontiguousarray(x.reshape(-1, T))
        y2 = np.ascontiguousarray(np.asarray(y, np.float64).reshape(-1, T))
        return _box_hits(x2, y2, *arr, float(hx), float(hy)).reshape(shp)

    def _path_occ(self, x, y, tk, exclude=None, only=None, types=None) -> np.ndarray:
        x = np.asarray(x, np.float64)
        y = np.asarray(y, np.float64)
        shp = x.shape
        out = np.zeros(shp, bool)
        if not self.paths:
            return out
        T = shp[-1]
        hx, hy = self._fc.half
        x2 = np.ascontiguousarray(x.reshape(-1, T))
        y2 = np.ascontiguousarray(y.reshape(-1, T))
        flat = out.reshape(-1, T)
        circles: dict = defaultdict(list)
        c = np.ascontiguousarray
        for p in self.paths:
            if exclude and p.iid in exclude or only is not None and p.iid not in only:
                continue
            if types is not None and p.type_key not in types:
                continue
            cx, cy, on, grow = p.at(tk)
            if p.kind == "circle" and not grow.any():
                circles[p.r + SKIN_U].append((cx, cy, on))
                continue
            rx, ry = (p.r, p.r) if p.kind == "circle" else (p.hx, p.hy)
            flat |= _box_hits(x2, y2, c(cx - rx - grow), c(cy - ry - grow), c(cx + rx + grow), c(cy + ry + grow),
                              c(on), float(hx + SKIN_U), float(hy + SKIN_U))
        for rr, lst in circles.items():
            flat |= circle_hits(x2, y2, c(np.concatenate([a[0] for a in lst])),
                                c(np.concatenate([a[1] for a in lst])), c(np.concatenate([a[2] for a in lst])),
                                float(hx), float(hy), float(rr))
        return out

    def _union_occ(self, x, y, tk, ids=None, names=None, only=None, committed_only: bool = False,
             parts: bool = False):
        x = np.asarray(x, np.float64)
        y = np.asarray(y, np.float64)
        tk = np.asarray(tk, np.float64)
        filt = bool(ids or names or only is not None or committed_only)
        kw = dict(ids=ids, names=names, only=only, committed_only=committed_only)
        f = self._fine_occ(x, y, tk, _mask(self.pm, **kw) if filt and len(self.P) else None)
        f |= self._win_occ(x, y, tk, _mask(self.wm, **kw) if filt and len(self.W) else None)
        f |= self._bbox_occ(x, y, tk, _mask(self.bb, clusters=self.clusters, **kw) if filt and self.n_bbox else None)
        types = ({p.type_key for p in self.paths} - set(names)) if names else None
        f |= self._path_occ(x, y, tk, exclude=ids, only=only, types=types)
        f |= self._box_occ(x, y, tk, kinds=("death", "arena"), exclude=ids, only=only)
        if committed_only:
            return f
        tubes = {k: self._box_occ(x, y, tk, kinds=(k,), exclude=ids, only=only) for k in ("idle", "collider",
                                                                                           "hazard")}
        if parts:
            return {"forecast": f, "idle body tube": tubes["idle"], "collider tube": tubes["collider"],
                    "hazard tube": tubes["hazard"]}
        return f | tubes["idle"] | tubes["collider"] | tubes["hazard"]

    # ---- the interface ----

    def occupied(self, x, y, tk, comfort: bool = False) -> np.ndarray:
        """[N, T] bool: the hero hurtbox (grown by the margin) centred at (x, y) at tk s from the origin meets some
        support: every enemy's placements and tubes, every hazard."""
        if self.boss_fc is not None:
            return self.boss_fc.occupied(x, y, tk, comfort)
        if comfort:
            # no comfort templates in the multi path yet (R3): the plain support answers, the request is counted
            self._fc.comfort_requests += 1
        return self._union_occ(x, y, tk)

    def occupied_parts(self, x, y, tk) -> dict[str, np.ndarray]:
        """occupied() split by what covers (the recall's accounting): "forecast" (placements, hazard paths, death
        tails, the arena-wide boxes), "idle body tube", "collider tube", "hazard tube"."""
        return self._union_occ(x, y, tk, parts=True)

    def occupied_without(self, x, y, tk, exclude, comfort: bool = False) -> np.ndarray:
        """occupied() without the support of `exclude`: an enemy iid (a kill: its tails, tubes and the instances it
        may start; its thrown hazards stay; a Tiny group row stays while another Tiny of its cluster is in), a hazard
        iid, a set of them, or a hazard type / family name."""
        if self.boss_fc is not None:
            return self.boss_fc.occupied_without(x, y, tk, exclude, comfort)
        if comfort:
            self._fc.comfort_requests += 1
        ex = set(exclude) if isinstance(exclude, (set, frozenset, list, tuple)) else {exclude}
        ids = {int(e) for e in ex if isinstance(e, (int, np.integer))}
        names = {e for e in ex if isinstance(e, str)}
        return self._union_occ(x, y, tk, ids=ids, names=names)

    def occupied_only(self, x, y, tk, iids) -> np.ndarray:
        """occupied() restricted to these enemies' and hazards' support (the recall's per-type check)."""
        return self._union_occ(x, y, tk, only={int(i) for i in iids})

    def occupied_redirect(self, x, y, tk, type_key, t_hit, d, comfort=False):
        if self.boss_fc is not None:
            return self.boss_fc.occupied_redirect(x, y, tk, type_key, t_hit, d, comfort)
        return None

    def redirect_occ(self, x, y, tk, type_key, t_hit, d, comfort=False):
        if self.boss_fc is not None:
            return self.boss_fc.redirect_occ(x, y, tk, type_key, t_hit, d, comfort)
        return None

    def bell_redirected(self, x, y, tk, iid: int, t_hit: float, d: int) -> np.ndarray | None:
        """occupied() with the bell iid knocked by the hero's hit at t_hit (d: +1 right, -1 left, 0 down, 2 up) onto
        its redirect path (projectiles.HazardTracker.redirect); None when it is not a bell on a path."""
        p = self._fc.hazards.redirect(iid, t_hit, d, self.origin_t, self.horizon)
        if p is None:
            return None
        out = self.occupied_without(x, y, tk, iid)
        keep = self.paths
        self.paths = [p]
        try:
            out |= self._path_occ(x, y, np.asarray(tk, np.float64))
        finally:
            self.paths = keep
        return out

    def prob(self, x, y, tk) -> np.ndarray:
        """[N]: 1 - prod_i (1 - p_i), p_i the largest path probability of enemy i's placements the point meets
        (committed attacks, tails, hazards and tubes 1); scoring only."""
        if self.boss_fc is not None:
            return self.boss_fc.prob(x, y, tk)
        x = np.asarray(x, np.float64)
        y = np.asarray(y, np.float64)
        tk = np.asarray(tk, np.float64)
        N = x.shape[0]
        q = np.ones(N)
        owners = set(self.pm["owner"].tolist()) | set(self.wm["owner"].tolist()) | set(self.bb["owner"].tolist())
        owners |= {b[0] for b in self.boxes} | {p.iid for p in self.paths}
        for o in owners:
            pi = np.zeros(N)
            for meta, occ in ((self.pm, self._fine_occ), (self.wm, self._win_occ), (self.bb, self._bbox_occ)):
                sel = meta["owner"] == o
                for pv in np.unique(meta["prob"][sel]):
                    hit = occ(x, y, tk, sel & (meta["prob"] == pv)).any(axis=1)
                    pi = np.maximum(pi, np.where(hit, min(1.0, float(pv)), 0.0))
            hit = (self._box_occ(x, y, tk, only={o}) | self._path_occ(x, y, tk, only={o})).any(axis=1)
            pi = np.maximum(pi, hit.astype(float))
            q *= 1.0 - pi
        return 1.0 - q

    def t_min(self, x: float, y: float, t_max: float = 3.0, subject: int | None = None) -> float:
        """Earliest game time (s from the origin) at which some support reaches a hurtbox standing at (x, y) (one
        enemy's: subject); inf when none does within t_max."""
        if self.boss_fc is not None:
            return self.boss_fc.t_min(x, y, t_max)
        tk = np.arange(0, int(t_max / BIN) + 1) * BIN
        X, Y = np.full((1, len(tk)), x), np.full((1, len(tk)), y)
        hit = (self.occupied(X, Y, tk) if subject is None else self.occupied_only(X, Y, tk, {subject}))[0]
        i = np.flatnonzero(hit)
        return float(tk[i[0]]) if len(i) else math.inf

    def committed(self) -> "MultiForecast":
        """What is already decided: the current attacks, tails, death tails and hazards (no instance that may start
        later, no tubes)."""
        if self.boss_fc is not None:
            return MultiForecast(self._fc, self.origin_t, self.horizon, boss=self.boss_fc.committed())
        out = MultiForecast(self._fc, self.origin_t, self.horizon)

        def keep(meta, rows):
            s = np.flatnonzero(meta["committed"])
            return rows.take(s), {k: ([v[i] for i in s] if isinstance(v, list) else v[s]) for k, v in meta.items()}
        out.P, out.pm = keep(self.pm, self.P)
        out.W, out.wm = keep(self.wm, self.W)
        s = np.flatnonzero(self.bb["committed"])
        out.bb = {k: ([v[i] for i in s] if isinstance(v, list) else v[s]) for k, v in self.bb.items()}
        out.boxes = [b for b in self.boxes if b[1] == "death"]
        out.paths = self.paths
        out.subjects = self.subjects
        out.known = self.known
        out.groups, out.clusters = self.groups, self.clusters
        return out

    def support_set(self, ws: WorldState | None = None, t1: float = SUP_HORIZON_S) -> SupportSet:
        """The supervisor's support: one event per enemy instance with support within t1 (its largest family damage;
        a family with a multi-hit collider: the chain's measured hits and damage, chains.json), one per hazard;
        known when the tables are certified and every enemy in play has a tracked state."""
        if self.boss_fc is not None:
            return self.boss_fc.support_set(ws, t1)
        tables = self._fc.tables
        by_owner: dict = defaultdict(set)
        for meta in (self.pm, self.wm, self.bb):
            act = (meta["off"] >= 0.0) & (meta["on"] <= t1)
            gcl = meta.get("gcl")
            for i in np.flatnonzero(act):
                if gcl is not None and gcl[i] >= 0:          # a Tiny group row: an event for each of its Tinies
                    for o in self.clusters[int(gcl[i])]:
                        by_owner[o].add(meta["family"][i])
                else:
                    by_owner[int(meta["owner"][i])].add(meta["family"][i])
        for b in self.boxes:
            if b[9] <= t1 and b[10] >= 0.0:
                by_owner[b[0]].add(None)
        events = []
        trackers = self._fc.trackers
        for owner, fams in by_owner.items():
            tr = trackers.get(owner)
            if tr is None:
                if ENTRY_OWNER - len(FORUM_WAVES) < owner <= ENTRY_OWNER:          # a wave entry
                    events.append(SupportEvent(f"wave {ENTRY_OWNER - owner} entry", 2, instance=None))
                elif owner in self._fc.self_haz:
                    tk = self._fc.self_haz[owner][0]
                    events.append(SupportEvent(tk, _hazard_damage(tk), instance=owner))
                continue
            tt = tables.types[tr.tk]
            dmg, hits = 1, 1
            for f in fams:
                if f is None:
                    dmg = max(dmg, max((fm.damage for fm in tt.families.values()), default=1))
                    continue
                if str(f).startswith("ent/"):
                    dmg = max(dmg, _hazard_damage(str(f)[4:]))
                    continue
                fm = tt.families.get(f)
                if fm is not None:
                    dmg = max(dmg, fm.damage)
                h, d = _chain(tables.chains, tr.tk, f)
                if h > 1:
                    hits, dmg = max(hits, h), max(dmg, d)
            events.append(SupportEvent(tr.tk, dmg, hits=hits, instance=owner))
        for p in self.paths:
            if p.static:
                if p.t_hi < 0 or p.t_lo > t1:
                    continue
            else:
                _, _, on, _ = p.at(np.arange(0.0, t1 + 1e-9, BIN), slack=False)
                if not on.any() and p.tube_from is None:
                    continue
            events.append(SupportEvent(p.type_key, p.damage, instance=p.iid))
        known = bool(self.known)
        return SupportSet(tuple(events), known, certified_empty=known and not events)

    def targets(self, tk) -> list[Target]:
        """Each live enemy in play: its body box (the export's colliders when last seen) moved along its velocity;
        each bell on a path: its circle's box (a redirect target)."""
        tk = np.asarray(tk, np.float64)
        out = []
        for tr in self._fc.trackers.values():
            if tr.dead or not tr.in_play or tr.body is None or tr.hidden:
                continue
            dt = tk - (tr.seen_T - self.origin_t)
            b = np.array(tr.body)
            box = np.stack([b[0] + tr.vel[0] * dt, b[1] + tr.vel[1] * dt, b[2] + tr.vel[0] * dt,
                            b[3] + tr.vel[1] * dt], axis=1)
            out.append(Target(tr.iid, tr.tk, box, np.ones(len(tk), bool)))
        for p in self.paths:
            if p.type_key != BELL:
                continue
            cx, cy, on, _ = p.at(tk, slack=False)
            out.append(Target(p.iid, p.type_key, np.stack([cx[0] - p.r, cy[0] - p.r, cx[0] + p.r, cy[0] + p.r], 1),
                              on[0], hazard=True))
        return out

    # ---- the single-boss planner's view of a gauntlet (today's planner; Forum planner changes are R3) ----

    def _nearest(self):
        ws = self._fc._ws
        hx, hy = (ws.hero.pos.v if ws is not None else (0.0, 0.0))
        best, bd = None, math.inf
        for tr in self._fc.trackers.values():
            if tr.dead or not tr.in_play or tr.body is None or tr.hidden:
                continue
            d = math.hypot(0.5 * (tr.body[0] + tr.body[2]) - hx, 0.5 * (tr.body[1] + tr.body[3]) - hy)
            if d < bd:
                best, bd = tr, d
        return best

    def boss_box(self, tk):
        if self.boss_fc is not None:
            return self.boss_fc.boss_box(tk)
        tk = np.asarray(tk, np.float64)
        tr = self._nearest()
        if tr is None:
            return np.zeros((len(tk), 4)), np.zeros(len(tk), bool)
        dt = tk - (tr.seen_T - self.origin_t)
        b = np.array(tr.body)
        box = np.stack([b[0] + tr.vel[0] * dt, b[1] + tr.vel[1] * dt, b[2] + tr.vel[0] * dt, b[3] + tr.vel[1] * dt],
                       axis=1)
        return box, np.ones(len(tk), bool)

    def body_polys(self):
        if self.boss_fc is not None:
            return self.boss_fc.body_polys()
        tr = self._nearest()
        if tr is None:
            return np.zeros((0, 2)), np.zeros(1, np.int64)
        x0, y0, x1, y1 = tr.body
        return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], np.float64), np.array([0, 4], np.int64)

    def certain_boss(self, *args, **kw):
        return self.boss_fc.certain_boss(*args, **kw) if self.boss_fc is not None else None

    def target_paths(self, tk):
        return self.boss_fc.target_paths(tk) if self.boss_fc is not None else []

    def ambiguous_paths(self, tk):
        return self.boss_fc.ambiguous_paths(tk) if self.boss_fc is not None else []

    @property
    def det(self):
        return self.boss_fc.det if self.boss_fc is not None else []

    def _det_occ(self, x, y, tk, *a, **kw):
        if self.boss_fc is not None:
            return self.boss_fc._det_occ(x, y, tk, *a, **kw)
        return np.zeros(np.shape(x), bool)


def _hazard_damage(tk: str) -> int:
    return 2 if tk in (RUNE, "Spear", "handmaiden_spear_silk_explosion") else 1


def _chain(chains: dict, tk: str, family: str) -> tuple[int, int]:
    """(hits, masks) of the longest measured multi-hit chain of a family's colliders (chains.json by_source
    "<type>/<collider>"): the Minister's Slash Collider (MI_CHARGE) and ParrySlash Hit (MI_PARRY), the Choristor's
    Whip Hit (CH_WHIP), the Reed's ParrySlash Hit (RE_DEFEND)."""
    cols = MULTI_HIT.get((tk, family), ())
    h, d = 1, 1
    for c in cols:
        hh, dd = chains.get(f"{tk}/{c}", (1, 1))
        h, d = max(h, hh), max(d, dd)
    return h, d


# families whose colliders chain (forum.md §9.2 / §12.3: the hornet_multi_wounder colliders)
MULTI_HIT = {("Song Administrator", "MI_CHARGE"): ("Slash Collider",),
             ("Song Administrator", "MI_PARRY"): ("ParrySlash Hit",),
             ("Song Pilgrim 03", "CH_WHIP"): tuple(f"Whip Hit {i}" for i in range(1, 7)) + ("Whip Hit",),
             ("Song Reed", "RE_DEFEND"): ("ParrySlash Hit",)}
