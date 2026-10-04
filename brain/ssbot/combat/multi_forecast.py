"""Threat forecast of a multi-enemy arena (Forum plan R2, docs/plans/forum_planner_plan.md §4.1 / §4.3): every enemy's
support and probability over the next H seconds in one object with the single-boss Forecast's interface, so the
planner does not need to know how many enemies there are.

    mf = MultiForecaster(EnemyTables.production(), view=ORACLE)   # or MultiForecaster(boss=Forecaster(...))
    mf.reset(); mf.notify_wake(t_battle)
    mf.update(ws)                                    # every WorldState, in order
    f = mf.forecast(horizon_s=0.8)                   # origin ws.stamp.t_game_s
    f.occupied(x, y, tk)                             # [N, T] bool, every enemy and hazard at once
    f.occupied_without(x, y, tk, iid)                # without one enemy (a kill's effect) or hazard
    f.prob(x, y, tk)                                 # 1 - prod(1 - p_i), scoring only
    f.support_set(ws)                                # one event per instance; multi-hit chains hits > 1
    f.targets(tk), f.t_min(x, y), f.committed(), f.known

Support per enemy (EnemyTracker: Control state, the attack instance and its anchor), the structure the R0 held-out
certification ran on (ssbot.knowledge.forum_support.SubjectRecall; forum.md §12.2), at run time:
  - the walk: from the current state over the logged successors and dwell ranges (one bin of slack each side), a hull
    of entry times per (state, instance context, dead) node, so loops end; a current state older than its longest
    logged dwell can end at any time from the next frame. Memoised per (type, state, instance context, overdue):
    re-walked only when the state changes (the walk cache), times relative to the state's entry (or to the origin
    when overdue). Structurally absent states (ssbot.core.forum.STRUCTURALLY_ABSENT) are not in the tables' walk.
  - the current attack's states at its anchor (fine templates per entry bin while the entry is known to a few bins,
    else coarse ones whose time dilation spans the interval: EnemyTables), its family template from the attack start
    (the family-wide union), its tail once it can end, the tails of ended attacks;
  - attacks (and idle instances) that may start within the horizon: the per-state templates at an anchor box (the
    enemy's transform dead-reckoned to the possible start times, grown by the type's idle growth since the
    sighting) and both mirrors, as coarse templates dilated by the box; entry families also in their world frame;
  - an enemy in its idle family: the idle body tube (its damage box as last seen, moved along its velocity, grown by
    the idle growth) instead of the idle instance's templates;
  - for the first few frames only (COLLIDER_TUBE_S, the reaction lag the certification needed them for): the
    current-collider tube (its box grown at the type's top speed) and the hazard tube;
  - a killed enemy's last damage box for DEATH_TAIL_S (forum_products death_tails: contacts on the kill frame only);
    a pooled enemy (the Maestro's Tinies) is walked on after its death (it comes back), the others are not;
  - thrown hazards: on deterministic paths (ssbot.combat.projectiles: bells incl. the nail redirect, javelins, bomb
    rows, rune slams), the others by their self template from where they armed (the Clawmaiden's spear and blast;
    every hazard in the vision view, where the paths come from tracked velocities);
  - entries: the next wave's members not in the export yet (WaveTracker's activation window; static wave table plus
    the kills and sightings, never room.battles) by their entry family's world-frame template.
Tiny group placement: with >= TINY_GROUP Tinies, the attacks they may start are placed once per cluster of nearby
Tinies in the same state (one anchor box covering the members) instead of once per Tiny.

The single-boss path is untouched: MultiForecaster(boss=fc) wraps a Forecaster and its forecast delegates every query
to the boss's Forecast (bit-identical: tests/test_multi_forecast.py and tools/multi_recall --bellbeast).
"""
import math
from collections import defaultdict
from dataclasses import dataclass, field

import numba
import numpy as np

from ssbot.combat.enemy_tables import BIN, COARSE_U, TAIL, EnemyTables, PlaceBatch, TypeTable, shifted_union
from ssbot.combat.enemy_tracker import TAIL_KEEP_S, EnemyTracker, body_offsets
from ssbot.combat.fastquery import circle_hits
from ssbot.combat.forecast import active_within, entry_grid, exit_interval
from ssbot.combat.projectiles import (BELL, BOMB, HAZARD_DV_U_S, PIN, RUNE, SKIN_U, HazardPath, HazardTracker,
                                      hazard_type)
from ssbot.combat.wave_tracker import WaveTracker
from ssbot.core.forum import FORUM_TYPES, FORUM_WAVES, HAZARD_ALIASES, HAZARD_OWNER, _type_key
from ssbot.core.worldstate import ORACLE, Ev, WorldState
from ssbot.knowledge import hitbox_tables as hb
from ssbot.safety.hits_to_death import SupportEvent, SupportSet

MIN_HORIZON_S = 0.8
SUP_HORIZON_S = 0.8
DWELL_SLACK_S = BIN               # logged dwell ranges are frame-quantised
WALK_CAP_S = 6.0                  # memoised walks reach this far past the state's entry
WALK_MAX_STEPS = 20000
FINE_MAX_BINS = 3                 # a node whose entry spans more bins goes coarse
TUBE_MAX_AGE_S = 0.5              # the idle body tube starts from a box seen at most this long ago
COLLIDER_TUBE_S = 5 * BIN         # the current-collider and hazard tubes cover only the reaction lag
DEATH_TAIL_S = 3 * BIN            # a killed enemy's last box hurts on its kill frame (forum_products death_tails)
HAZARD_GONE_S = 0.5
COARSE_MAX_U = 24.0               # an anchor box wider than this places an arena-wide box instead
BOXIFY_U = 1.0                    # ... wider than this: the template's per-bin bounding box grown by the anchor box
ARENA_BOX = (0.0, -5.0, 64.0, 40.0)
TINY = "Song Automaton Tiny"
TINY_GROUP = 3                    # Tinies at least this many: group placement
TINY_CLUSTER_U = 4.0              # Tinies whose anchors lie this close share one placement set
ENTRY_LAG_S = 1.0                 # a wave's activation -> its member's entry family start (upper bound)
ENTRY_OWNER = -(1 << 50)          # placement owner of wave w's entries: ENTRY_OWNER - w
LADDER = (0, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96)    # coarse dilation steps (cells of COARSE_U)
KT_NEAR, KT_MID, KT_FAR = 3, 6, 12                            # time dilation (bins) of coarse pieces by distance


def _ladder(cells: float) -> int:
    for k in LADDER:
        if k >= cells - 1e-9:
            return k
    return LADDER[-1]


def _kt_for(t: float) -> int:
    return KT_NEAR if t < 0.4 else KT_MID if t < 1.0 else KT_FAR


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
            nodes[k] = [lo, hi, p]
        elif lo < iv[0] - 1e-9 or hi > iv[1] + 1e-9 or p > iv[2] + 1e-9:
            iv[0], iv[1], iv[2] = min(iv[0], lo), max(iv[1], hi), max(iv[2], p)
        else:
            return
        todo.append(k)

    c0 = (ctx[0], ctx[1], "cur") if ctx is not None else None
    push(state, 0.0, 0.0, c0, dead, 1.0, True)
    steps = 0
    while todo and steps < WALK_MAX_STEPS:
        k = todo.pop()
        st, c, d, current = k
        lo, hi, p = nodes[k]
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
    for (st, c, d, current), (lo, hi, p) in nodes.items():
        if c is None:
            continue
        out.append(WalkNode(st, c[0], c[1], c[2], d, lo, hi, p, current))
    return out


class _WalkCache:
    def __init__(self):
        self.d: dict = {}
        self.hits = 0
        self.misses = 0

    def get(self, tt: TypeTable, state: str, ctx, dead: bool, overdue: bool) -> list[WalkNode]:
        k = (tt.tk, state, ctx, dead, overdue)
        r = self.d.get(k)
        if r is None:
            self.misses += 1
            r = self.d[k] = walk(tt, state, ctx, dead, overdue)
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
    t_strike: float               # earliest time its support reaches anywhere (s from the origin)


@dataclass(slots=True)
class Target:
    """A hittable body (an enemy's hurtbox moved along its velocity) or a hazard (a bell) over the query times."""
    iid: int
    type_key: str
    box: np.ndarray               # [T, 4]
    ok: np.ndarray                # [T]
    hazard: bool = False


class _Shim:
    """The bits of the single-boss Forecaster the planner reads off f.fc (half, model.families' hazard flags, the
    comfort query, the registry's spec_of)."""

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
        self._fwalk_none: set = set()
        self.offsets = {}
        if tables is not None and view != ORACLE:
            import json
            from ssbot.combat.enemy_tables import FORUM_DIR
            for tk, spec in FORUM_TYPES.items():
                p = FORUM_DIR / f"{spec.enemy}.json"
                if p.exists():
                    self.offsets[tk] = body_offsets(json.loads(p.read_text("utf-8")))
        self.reset()

    def reset(self) -> None:
        if self.boss is not None:
            self.boss.reset()
        self.trackers: dict[int, EnemyTracker] = {}
        self.hazards = HazardTracker(self.view)
        self.waves = WaveTracker()
        self.self_haz: dict[int, list] = {}    # hazard iid -> [type, armed, arm_T, arm_pos, last_T, pos, rel_box, vel]
        self.t = 0.0
        self._ws: WorldState | None = None
        self.t_wake: float | None = None

    def notify_wake(self, t_game: float, wave: int = 0) -> None:
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

    def family_walk_id(self, tt: TypeTable, fam: str, start: str, frame: str = "anchor") -> int | None:
        """The family walk template of an instance of (fam, start): the union over the walk inside the instance
        (instance_only: every state it reaches and its tail, each per-state template time-dilated over its entry
        interval since the start, on the coarse grid). Built once (a coarse-only base of the store)."""
        key = f"fwalk/{tt.tk}/{fam}/{start}/{frame}"
        store = self.tables.store
        i = store.coarse_keys.get(key)
        if i is not None or key in self._fwalk_none:
            return i
        parts = []
        for nd in walk(tt, start, (fam, start), False, False, instance_only=True):
            tid = self.tables.key_id(fam, TAIL if nd.state == TAIL else nd.state, frame)
            if tid is None:
                continue
            base = store.base(tid)
            k = int(math.ceil((nd.hi - nd.lo) / (2 * BIN) - 1e-9))
            parts.append((base.dilated(t_bins=k) if k > 0 else base, 0.5 * (nd.lo + nd.hi)))
        u = shifted_union(parts, key)
        if u is None:
            self._fwalk_none.add(key)
            return None
        return store.add_coarse_base(key, u)

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

    # ---- the forecast ----

    def forecast(self, horizon_s: float = MIN_HORIZON_S, origin_t: float | None = None,
                 clamp: bool = True) -> "MultiForecast":
        """clamp False: exactly horizon_s (the recall's few frames), else at least MIN_HORIZON_S."""
        H = max(MIN_HORIZON_S, horizon_s) if clamp else horizon_s
        if self.boss is not None:
            return MultiForecast(self, self.boss.t if origin_t is None else origin_t, H,
                                 boss=self.boss.forecast(horizon_s, origin_t))
        origin = self.t if origin_t is None else origin_t
        self.tables.store.trim()
        b = _Builder(self, origin, H)
        for tr in self.trackers.values():
            b.subject(tr)
        b.groups()
        b.hazards()
        if self.use_waves:
            b.entries()
        return b.finish()


class _Builder:
    """One forecast's placements, tubes and hazard shapes."""

    def __init__(self, fc: MultiForecaster, origin: float, H: float):
        self.fc = fc
        self.tables = fc.tables
        self.store = fc.tables.store
        self.origin = origin
        self.H = H
        self.rows: list[tuple] = []          # (tid, t_ref, ax, ay, mirror)
        self.meta: list[tuple] = []          # (subject iid, family, committed, p, t_on, t_off)
        self.boxes: list[tuple] = []         # (owner, kind, x0, y0, x1, y1, vx, vy, grow_type, t_from, t_to, t0)
        self.paths: list[HazardPath] = []
        self.subjects: list[Subject] = []
        self.known = fc.tables.certified
        self.n_place_fine = 0
        self.n_place_coarse = 0
        self.tiny_new: list[tuple] = []      # deferred "new" nodes of Tinies (group placement)
        self.unknown: list[int] = []
        self.meta_group: dict = {}           # group owner -> the other Tinies its placements stand for
        self.bbx: list[tuple] = []           # bounding-box placements (BB_FIELDS)

    # ---- placements ----

    def _fine(self, tid, e_lo: float, e_hi: float, anchor, mirror: int, owner: int, fam, committed: bool, p: float):
        if tid < 0:                               # kept only coarse
            ax, ay = anchor if anchor is not None else (0.0, 0.0)
            self._coarse(tid, e_lo, e_hi, ax, ay, 0.0, 0.0, (mirror,), owner, fam, committed, p,
                         world=anchor is None)
            return
        t0, t1 = self.store.tpls[tid].t0, self.store.tpls[tid].t1
        es = [e for e in entry_grid(e_lo, e_hi) if active_within(e + t0, e + t1, self.H)]
        ax, ay = (anchor if anchor is not None else (math.nan, math.nan))
        for e in es:
            self.rows.append((tid, -e, ax, ay, mirror))
            self.meta.append((owner, fam, committed, p, e + t0, e + t1))
        self.n_place_fine += len(es)

    def _coarse(self, tid, e_lo: float, e_hi: float, cx: float, cy: float, hx: float, hy: float, mirrors,
                owner: int, fam, committed: bool, p: float, world: bool = False):
        """Entries over [e_lo, e_hi] at anchors in the box (cx +- hx, cy +- hy): coarse pieces of 2 kt + 1 bins."""
        tpl = self.tables.template(tid)
        t0, t1 = tpl.t0, tpl.t1
        lo, hi = max(e_lo, -BIN - t1), min(e_hi, self.H + BIN - t0)
        if hi < lo - 1e-9:
            return
        if max(hx, hy) > COARSE_MAX_U:
            self.boxes.append((owner, "arena", *ARENA_BOX, 0.0, 0.0, None, lo + t0 - BIN, hi + t1 + BIN, 0.0))
            return
        if not world and max(hx, hy) > BOXIFY_U:
            # an anchor this uncertain: the template's bounding box per time bin, grown by the anchor box (a superset
            # of the dilated template, without building one per box size)
            self.store.bbox_table(tid)
            self.bbx.append((owner, fam, committed, p, tid, lo, hi, cx, cy, hx, hy, 0 if len(mirrors) > 1 else
                             int(mirrors[0]), lo + t0 - BIN, hi + t1 + BIN))
            return
        kx = _ladder(hx / COARSE_U)
        ky = _ladder(hy / COARSE_U)
        e = lo
        while e <= hi + 1e-9:
            kt = _kt_for(max(e, 0.0))
            span = (2 * kt) * BIN
            mid = min(e + kt * BIN, max(hi - kt * BIN, e))
            cid = self.store.coarse_id(tid, kx, ky, kt)
            for m in mirrors:
                self.rows.append((cid, -mid, math.nan if world else cx, math.nan if world else cy, m))
                self.meta.append((owner, fam, committed, p, mid - kt * BIN + t0, mid + kt * BIN + t1))
                self.n_place_coarse += 1
            e += span + BIN
        return

    # ---- one enemy ----

    def _walk_waiting(self, tr: EnemyTracker) -> bool:
        """An enemy in a waiting state is walked (its entry may start) only when it may enter soon: a pooled Tiny
        while a Maestro is in play (a summon), a wave member when its wave is queued or no wave is known yet."""
        fc = self.fc
        if tr.table.spec.pooled:
            return any(t.tk == "Song Pilgrim Maestro" and t.in_play and not t.dead for t in fc.trackers.values())
        if not fc.use_waves or fc.t_wake is None:
            return True
        nw = fc.waves.next_window()
        if nw is None:
            return False
        return tr.tk in FORUM_WAVES[nw[0]].types and nw[1] - self.origin <= self.H + ENTRY_LAG_S

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
        if tr.dead and not sp.pooled:
            self.subjects.append(self._subject_row(tr, False))
            return
        if tr.state is None or tr.t_entry is None:
            if tr.seen_T > -math.inf and not tr.hidden:
                self.unknown.append(tr.iid)
            self.subjects.append(self._subject_row(tr, False))
            return
        if not tr.in_play and not self._walk_waiting(tr):
            self.subjects.append(self._subject_row(tr, False))
            return
        if tr.state not in tt.dwell and tr.in_play:
            self.unknown.append(tr.iid)
        age = T - tr.t_entry
        dw = tt.dwell.get(tr.state)
        overdue = dw is not None and age > dw[1] + DWELL_SLACK_S
        ctx = (cur.family, cur.start) if cur is not None else None
        nodes = self.fc.walks.get(tt, tr.state, ctx, tr.dead, overdue)
        ref = T if overdue else tr.t_entry
        idle_tube = (cur is not None and cur.family == sp.idle_family and not tr.dead and tr.pos is not None
                     and T - tr.seen_T <= TUBE_MAX_AGE_S and tt.tk in tubes.growth)
        anc = None
        if cur is not None and cur.anchor is not None:
            anc = (cur.anchor, cur.mirror, cur.sd)
        committed_now = cur is not None and cur.family != sp.idle_family
        # the current attack's family template from its start (the family-wide union)
        if committed_now and anc is not None:
            fid = tables.key_id(cur.family, None, "anchor")
            if fid is not None:
                self._place_anchor(fid, cur.t_start - T, cur.t_start - T, anc, tr.iid, cur.family, True, 1.0)
        for nd in nodes:
            if nd.current:
                lo = hi = tr.t_entry - T          # the current state: its entry
            else:
                # a state not entered yet enters from the next frame on (SubjectRecall._walk's push); the memoised
                # walk is relative to the entry, unclipped: its later nodes are a superset of the clipped walk's
                lo, hi = ref + nd.lo - T, ref + nd.hi - T
                lo, hi = max(lo, BIN), max(hi, BIN)
            if lo > H + BIN:
                continue
            fam = nd.family
            if nd.kind == "cur":
                if idle_tube and fam == sp.idle_family:
                    continue                      # the current idle instance: its body tube
                if anc is None:
                    continue                      # placed below from the instance's start
                key_state = TAIL if nd.state == TAIL else nd.state
                tid = tables.key_id(fam, key_state, "anchor")
                if tid is not None:
                    self._place_anchor(tid, lo, hi, anc, tr.iid, fam, fam != sp.idle_family, nd.p)
                if fam == sp.entry_family:
                    wid = tables.key_id(fam, key_state, "world_all")
                    if wid is not None:
                        self._coarse(wid, lo, hi, 0.0, 0.0, 0.0, 0.0, (1,), tr.iid, fam, True, nd.p, world=True)
                continue
            if nd.state != nd.start:
                continue                          # inside a later instance: its family walk template
            if sp.pooled and self.fc.tiny_group:
                self.tiny_new.append((tr, fam, nd.start, lo, hi, nd.p))
            else:
                self._place_family(tr, fam, nd.start, lo, hi, nd.p)
        if cur is not None and anc is None and not (idle_tube and cur.family == sp.idle_family):
            # the current instance's anchor is not known (not exported at its start): from its start, anchored
            # where it is now
            self._place_family(tr, cur.family, cur.start, cur.t_start - T, cur.t_start - T, 1.0, committed_now)
        if idle_tube:
            self._idle_tube(tr)
        if self.fc.collider_tube and T - tr.seen_T <= TUBE_MAX_AGE_S:
            b = tr.seen_box
            if b is None and tr.pos is not None and tt.tk in tubes.hull:
                h = tubes.hull[tt.tk]
                b = (tr.pos[0] + h[0], tr.pos[1] + h[1], tr.pos[0] + h[2], tr.pos[1] + h[3])
            if b is not None:
                self.boxes.append((tr.iid, "collider", *b, 0.0, 0.0, ("speed", tubes.speed.get(tt.tk, 60.0)),
                                   -BIN, COLLIDER_TUBE_S, tr.seen_T - T))
        self.subjects.append(self._subject_row(tr, True))

    def _subject_row(self, tr: EnemyTracker, alive: bool) -> Subject:
        c = tr.cur
        committed = c is not None and c.family != tr.table.spec.idle_family
        return Subject(tr.iid, tr.tk, alive and not tr.dead, tr.in_play, committed, None if c is None else c.family,
                       tr.state, tr.hp_est, tr.hp_sd, tr.pos, 0.0, math.inf)

    def _tails(self, tr: EnemyTracker) -> None:
        T = self.origin
        for inst in tr.ends:
            if inst.t_end is None or T - inst.t_end > TAIL_KEEP_S or inst.anchor is None:
                continue
            tid = self.tables.key_id(inst.family, TAIL, "anchor")
            if tid is not None:
                e = inst.t_end - T
                self._place_anchor(tid, e, e, (inst.anchor, inst.mirror, inst.sd), tr.iid, inst.family, True, 1.0)

    def _place_anchor(self, tid, lo, hi, anc, owner, fam, committed, p):
        (ax, ay), m, sd = anc
        if tid >= 0 and sd <= 1e-9 and hi - lo <= FINE_MAX_BINS * BIN + 1e-9:
            self._fine(tid, lo, hi, (ax, ay), m, owner, fam, committed, p)
        else:
            self._coarse(tid, lo, hi, ax, ay, sd, sd, (m,), owner, fam, committed, p)

    def _start_box(self, tr: EnemyTracker, s_lo: float, s_hi: float):
        """Where an instance starting within [s_lo, s_hi] (s from the origin) is anchored: the transform dead-reckoned
        to those times, grown by the type's idle growth since the sighting (and the view's anchor spread):
        (cx, cy, hx, hy), or None without a position."""
        if tr.pos is None:
            return None
        s_lo, s_hi = max(0.0, s_lo), max(0.0, s_hi)
        vx, vy = tr.vel
        age = self.origin - tr.seen_T
        x0, x1 = tr.pos[0] + vx * s_lo, tr.pos[0] + vx * s_hi
        y0, y1 = tr.pos[1] + vy * s_lo, tr.pos[1] + vy * s_hi
        g = float(self.tables.tubes.g(tr.tk, age + s_hi)) + tr.pos_sd
        return 0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * abs(x1 - x0) + g, 0.5 * abs(y1 - y0) + g

    def _pieces(self, lo: float, hi: float):
        """Start-time pieces of [lo, hi] (s from the origin): 2 kt + 1 bins each, kt by distance."""
        e = max(lo, -BIN) if hi >= -BIN else lo
        while e <= hi + 1e-9:
            kt = _kt_for(max(e, 0.0))
            e1 = min(hi, e + 2 * kt * BIN)
            yield e, e1
            e = e1 + BIN

    def _place_family(self, tr: EnemyTracker, fam: str, start: str, lo: float, hi: float, p: float,
                      committed: bool = False, box=None, owner: int | None = None):
        """An instance of (fam, start) starting within [lo, hi]: its family walk template (every state the walk
        reaches from the start and its tail, entry intervals from the logged dwells: one coarse template) at the
        anchor box of each start piece, both mirrors; an entry family also in its world frame."""
        fid = self.fc.family_walk_id(tr.table, fam, start, "anchor")
        wid = self.fc.family_walk_id(tr.table, fam, start, "world_all") if fam == tr.table.spec.entry_family \
            else None
        owner = tr.iid if owner is None else owner
        for e, e1 in self._pieces(lo, hi):
            if fid is not None:
                b = self._start_box(tr, e, e1) if box is None else box(e, e1)
                if b is None:
                    break
                self._coarse(fid, e, e1, b[0], b[1], b[2], b[3], (-1, 1), owner, fam, committed, p)
            if wid is not None:
                self._coarse(wid, e, e1, 0.0, 0.0, 0.0, 0.0, (1,), owner, fam, committed, p, world=True)

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
        """Tiny group placement: with >= tiny_group Tinies, the instances they may start are placed once per cluster
        of Tinies (within TINY_CLUSTER_U) starting the same family from the same state in the same window: one anchor
        box covering the members' boxes."""
        items = self.tiny_new
        self.tiny_new = []
        if not items:
            return
        if len({it[0].iid for it in items}) < self.fc.tiny_group:
            for tr, fam, start, lo, hi, p in items:
                self._place_family(tr, fam, start, lo, hi, p)
            return
        by: dict[tuple, list] = defaultdict(list)
        for it in items:
            tr, fam, start, lo, hi, p = it
            by[(fam, start, round(lo / (6 * BIN)), round(hi / (6 * BIN)))].append(it)
        for (fam, start, _, _), lst in by.items():
            lst = [it for it in lst if it[0].pos is not None]
            lst.sort(key=lambda it: it[0].pos[0])
            clusters: list[list] = []
            for it in lst:
                last = clusters[-1][-1][0] if clusters else None
                if last is not None and abs(it[0].pos[0] - last.pos[0]) <= TINY_CLUSTER_U \
                        and abs(it[0].pos[1] - last.pos[1]) <= TINY_CLUSTER_U:
                    clusters[-1].append(it)
                else:
                    clusters.append([it])
            for cl in clusters:
                if len(cl) == 1:
                    tr, fam_, start_, lo, hi, p = cl[0]
                    self._place_family(tr, fam_, start_, lo, hi, p)
                    continue
                lo = min(it[3] for it in cl)
                hi = max(it[4] for it in cl)
                members = [it[0] for it in cl]

                def box(e, e1, members=members):
                    bs = [self._start_box(m, e, e1) for m in members]
                    bs = [b for b in bs if b is not None]
                    if not bs:
                        return None
                    x0 = min(b[0] - b[2] for b in bs)
                    x1 = max(b[0] + b[2] for b in bs)
                    y0 = min(b[1] - b[3] for b in bs)
                    y1 = max(b[1] + b[3] for b in bs)
                    return 0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * (x1 - x0), 0.5 * (y1 - y0)
                owner = members[0].iid
                self._place_family(members[0], fam, start, lo, hi, max(it[5] for it in cl), box=box, owner=owner)
                self.meta_group.setdefault(owner, set()).update(m.iid for m in members[1:])

    # ---- hazards ----

    def hazards(self) -> None:
        fc = self.fc
        T = self.origin
        det = set()
        if fc.view == ORACLE and fc.self_templates != "all":
            for p in fc.hazards.paths(T, self.H):
                self.paths.append(p)
                if not p.predicted:
                    det.add(p.iid)
        elif fc.self_templates != "all":
            for p in fc.hazards.paths(T, self.H):
                self.paths.append(p)
        for iid, h in fc.self_haz.items():
            tk, armed, arm_T, arm_pos, last_T, pos, rel, vel = h
            if T - last_T > HAZARD_GONE_S:
                continue
            owner = HAZARD_OWNER.get(tk)
            use_self = fc.self_templates in ("all",) or iid not in det or fc.view != ORACLE
            if fc.self_templates == "none" and iid in det:
                use_self = False
            if use_self:
                sid = self.tables.self_id(tk)
                if sid is not None:
                    if armed and arm_T is not None:
                        e = arm_T - T
                        self._fine(sid, e, e, arm_pos, 1, iid, f"ent/{tk}", True, 1.0)
                    elif T - last_T <= 2.5 * BIN:
                        self._coarse(sid, BIN, self.H, pos[0], pos[1], 0.0, 0.0, (1,), iid, f"ent/{tk}", True,
                                     1.0)
            if fc.collider_tube and rel is not None and T - last_T <= HAZARD_GONE_S:
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
        for tk in set(FORUM_WAVES[w].types):
            if tk in present and FORUM_WAVES[w].active_from_load:
                continue                       # in the export already, walked from its waiting state
            tt = self.tables.types.get(tk)
            if tt is None:
                continue
            wid = self.tables.key_id(tt.spec.entry_family, None, "world_all")
            if wid is not None:
                self._coarse(wid, lo, hi + ENTRY_LAG_S, 0.0, 0.0, 0.0, 0.0, (1,), ENTRY_OWNER - w,
                             tt.spec.entry_family, False, 1.0, world=True)

    def finish(self) -> "MultiForecast":
        out = MultiForecast(self.fc, self.origin, self.H)
        out.P = PlaceBatch.from_rows(self.rows)
        m = self.meta
        out.p_owner = np.array([x[0] for x in m], np.int64)
        out.p_family = [x[1] for x in m]
        out.p_committed = np.array([x[2] for x in m], bool)
        out.p_prob = np.array([x[3] for x in m], np.float64)
        out.p_on = np.array([x[4] for x in m], np.float64)
        out.p_off = np.array([x[5] for x in m], np.float64)
        out.bb = _bb_arrays(self.bbx, self.store)
        out.boxes = self.boxes
        out.paths = self.paths
        out.subjects = self.subjects
        out.known = bool(self.known and not self.unknown)
        out.unknown = self.unknown
        out.n_fine, out.n_coarse, out.n_bbox = self.n_place_fine, self.n_place_coarse, len(self.bbx)
        out.groups = self.meta_group
        out.gen = self.store.gen
        return out


BB_FIELDS = ("owner", "family", "committed", "prob", "tid", "e0", "e1", "cx", "cy", "hx", "hy", "mir", "on", "off")


def _bb_arrays(rows: list, store) -> dict:
    """The bounding-box placements as arrays (BB_FIELDS) plus their rows in the store's bbox table."""
    out = {}
    if not rows:
        out = {k: np.zeros(0, np.int64 if k in ("owner", "tid", "mir") else bool if k == "committed"
                           else np.float64) for k in BB_FIELDS if k != "family"}
        out["family"] = []
        out["off_row"] = np.zeros(0, np.int64)
        out["nt"] = np.zeros(0, np.int64)
        out["t0"] = np.zeros(0)
        return out
    for i, k in enumerate(BB_FIELDS):
        col = [r[i] for r in rows]
        if k == "family":
            out[k] = col
        elif k in ("owner", "tid", "mir"):
            out[k] = np.array(col, np.int64)
        elif k == "committed":
            out[k] = np.array(col, bool)
        else:
            out[k] = np.array(col, np.float64)
    tabs = [store.bbox_table(int(t)) for t in out["tid"]]
    out["off_row"] = np.array([t[0] for t in tabs], np.int64)
    out["nt"] = np.array([t[1] for t in tabs], np.int64)
    out["t0"] = np.array([t[2] for t in tabs], np.float64)
    return out


@numba.njit(cache=True)
def _bbox_boxes(tk, rows, off, nt, t0, e0, e1, cx, cy, hx, hy, mir, bin_s):
    """World boxes [K, T] of bounding-box placements: the union of the template's per-bin boxes over the template
    times an entry in [e0, e1] gives at tk (mirrored: both mirrors when mir is 0), grown by the anchor box."""
    K = off.shape[0]
    T = tk.shape[0]
    bx0 = np.zeros((K, T))
    by0 = np.zeros((K, T))
    bx1 = np.zeros((K, T))
    by1 = np.zeros((K, T))
    ok = np.zeros((K, T), np.bool_)
    for k in range(K):
        for t in range(T):
            b0 = int(np.rint((tk[t] - e1[k] - t0[k]) / bin_s))
            b1 = int(np.rint((tk[t] - e0[k] - t0[k]) / bin_s))
            if b1 < 0 or b0 >= nt[k]:
                continue
            if b0 < 0:
                b0 = 0
            if b1 > nt[k] - 1:
                b1 = nt[k] - 1
            x0, y0, x1, y1 = np.inf, np.inf, -np.inf, -np.inf
            for b in range(b0, b1 + 1):
                r = off[k] + b
                if rows[r, 0] != rows[r, 0]:
                    continue
                x0 = min(x0, rows[r, 0])
                y0 = min(y0, rows[r, 1])
                x1 = max(x1, rows[r, 2])
                y1 = max(y1, rows[r, 3])
            if x0 == np.inf:
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


def _mask(owner: np.ndarray, family: list, committed: np.ndarray, ids=None, names=None, only=None,
          committed_only: bool = False) -> np.ndarray:
    """Which placements remain: not owned by ids, not of a family / hazard named in names (a suffix match), owned
    by one of only, committed."""
    m = np.ones(len(owner), bool)
    if ids:
        m &= ~np.isin(owner, np.fromiter(ids, np.int64))
    if names:
        m &= ~np.array([any(str(f).endswith(n) for n in names) for f in family], bool)
    if only is not None:
        m &= np.isin(owner, np.fromiter(only, np.int64)) if only else np.zeros(len(owner), bool)
    if committed_only:
        m &= committed
    return m


class MultiForecast:
    """One tick's forecast (see the module docstring). With a wrapped boss: every query is the boss Forecast's."""

    def __init__(self, fc: MultiForecaster, origin_t: float, horizon: float, boss=None):
        self._fc = fc
        self.origin_t = origin_t
        self.horizon = horizon
        self.boss_fc = boss
        self.P = None
        self.bb: dict = {}
        self.boxes: list = []
        self.paths: list[HazardPath] = []
        self.subjects: list[Subject] = []
        self.known = False if boss is None else boss.known
        self.unknown: list = []
        self.n_fine = self.n_coarse = self.n_bbox = 0
        self.groups: dict = {}
        self.gen = None
        self._cache: dict = {}

    def __getattr__(self, name):
        # the wrapped boss forecast answers everything this class does not define (boss_box, body_polys, det, ...)
        b = self.__dict__.get("boss_fc")
        if b is not None:
            return getattr(b, name)
        raise AttributeError(name)

    @property
    def fc(self):
        return self.boss_fc.fc if self.boss_fc is not None else self._fc

    @property
    def placements(self):
        if self.boss_fc is not None:
            return self.boss_fc.placements
        return range((len(self.P) if self.P is not None else 0) + self.n_bbox)

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

    def _place_occ(self, x, y, tk, sel: np.ndarray | None = None) -> np.ndarray:
        x = np.asarray(x, np.float64)
        out = np.zeros(x.shape, bool)
        if self.P is None or not len(self.P):
            return out
        on, off = self.p_on, self.p_off
        act = (off >= tk.min() - BIN) & (on <= tk.max() + BIN)
        if sel is not None:
            act &= sel
        if not act.any():
            return out
        P = self.P if act.all() else self.P.take(np.flatnonzero(act))
        return self._fc.tables.store.query(P, x, np.asarray(y, np.float64), tk, out, gen=self.gen)

    def _bbox_occ(self, x, y, tk, sel: np.ndarray | None = None) -> np.ndarray:
        x = np.asarray(x, np.float64)
        shp = x.shape
        bb = self.bb
        if not bb or not len(bb["owner"]):
            return np.zeros(shp, bool)
        act = (bb["off"] >= tk.min() - BIN) & (bb["on"] <= tk.max() + BIN)
        if sel is not None:
            act &= sel
        idx = np.flatnonzero(act)
        if not len(idx):
            return np.zeros(shp, bool)
        rows = self._fc.tables.store.bb_rows()
        g = lambda k: np.ascontiguousarray(bb[k][idx])  # noqa: E731
        bx = _bbox_boxes(np.ascontiguousarray(tk, np.float64), rows, g("off_row"), g("nt"), g("t0"), g("e0"),
                         g("e1"), g("cx"), g("cy"), g("hx"), g("hy"), g("mir"), BIN)
        T = shp[-1]
        x2 = np.ascontiguousarray(x.reshape(-1, T))
        y2 = np.ascontiguousarray(np.asarray(y, np.float64).reshape(-1, T))
        # the templates already hold the hero hurtbox's dilation: a point test of the centre
        return _box_hits(x2, y2, *bx, 0.0, 0.0).reshape(shp)

    def _bb_mask(self, **kw) -> np.ndarray | None:
        if not self.bb or not len(self.bb["owner"]):
            return None
        return _mask(self.bb["owner"], self.bb["family"], self.bb["committed"], **kw)

    def _p_mask(self, **kw) -> np.ndarray | None:
        if self.P is None or not len(self.P):
            return None
        return _mask(self.p_owner, self.p_family, self.p_committed, **kw)

    def _box_arrays(self, tk: np.ndarray, kinds=None, exclude=None, only=None):
        key = (len(tk), float(tk[0]) if len(tk) else 0.0, float(tk[-1]) if len(tk) else 0.0, kinds,
               None if exclude is None else frozenset(exclude), None if only is None else frozenset(only))
        if key in self._cache:
            return self._cache[key]
        r = self._box_arrays_(tk, kinds, exclude, only)
        if len(self._cache) > 64:
            self._cache.clear()
        self._cache[key] = r
        return r

    def _box_arrays_(self, tk: np.ndarray, kinds=None, exclude=None, only=None):
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
        if not rows:
            return None
        return tuple(np.ascontiguousarray(np.stack([r[i] for r in rows]), np.float64 if i < 4 else np.bool_)
                     for i in range(5))

    def _box_occ(self, x, y, tk, kinds=None, exclude=None, only=None) -> np.ndarray:
        x = np.asarray(x, np.float64)
        shp = x.shape
        T = shp[-1]
        arr = self._box_arrays(tk, kinds, exclude, only)
        if arr is None:
            return np.zeros(shp, bool)
        hx, hy = self._fc.half
        x2 = np.ascontiguousarray(x.reshape(-1, T))
        y2 = np.ascontiguousarray(np.asarray(y, np.float64).reshape(-1, T))
        return _box_hits(x2, y2, *arr, float(hx), float(hy)).reshape(shp)

    def _path_occ(self, x, y, tk, exclude=None, only=None, types=None) -> np.ndarray:
        x = np.asarray(x, np.float64)
        y = np.asarray(y, np.float64)
        shp = x.shape
        T = shp[-1]
        out = np.zeros(shp, bool)
        if not self.paths:
            return out
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

    def _occ(self, x, y, tk, ids=None, names=None, only=None, committed_only: bool = False,
             kinds=None) -> np.ndarray:
        tk = np.asarray(tk, np.float64)
        kw = dict(ids=ids, names=names, only=only, committed_only=committed_only)
        sel = self._p_mask(**kw) if (ids or names or only is not None or committed_only) else None
        out = self._place_occ(x, y, tk, sel)
        bsel = self._bb_mask(**kw) if (ids or names or only is not None or committed_only) else None
        out |= self._bbox_occ(x, y, tk, bsel)
        if committed_only:
            kinds = ("death",)
        out |= self._box_occ(x, y, tk, kinds=kinds, exclude=ids, only=only)
        types = None
        if names:
            types = {p.type_key for p in self.paths} - set(names)
        out |= self._path_occ(x, y, tk, exclude=ids, only=only, types=types)
        return out

    # ---- the interface ----

    def occupied(self, x, y, tk, comfort: bool = False) -> np.ndarray:
        """[N, T] bool: the hero hurtbox (grown by the margin) centred at (x, y) at tk s from the origin meets some
        support: every enemy's placements and tubes, every hazard."""
        if self.boss_fc is not None:
            return self.boss_fc.occupied(x, y, tk, comfort)
        return self._occ(x, y, tk)

    def occupied_parts(self, x, y, tk) -> dict[str, np.ndarray]:
        """occupied() split by what covers (the recall's accounting): "forecast" (placements, hazard paths, death
        tails, the arena-wide boxes), "idle body tube", "collider tube", "hazard tube"."""
        tk = np.asarray(tk, np.float64)
        f = self._place_occ(x, y, tk) | self._bbox_occ(x, y, tk) | self._path_occ(x, y, tk) | \
            self._box_occ(x, y, tk, kinds=("death", "arena"))
        return {"forecast": f, "idle body tube": self._box_occ(x, y, tk, kinds=("idle",)),
                "collider tube": self._box_occ(x, y, tk, kinds=("collider",)),
                "hazard tube": self._box_occ(x, y, tk, kinds=("hazard",))}

    def occupied_without(self, x, y, tk, exclude, comfort: bool = False) -> np.ndarray:
        """occupied() without the support of `exclude`: an enemy iid (a kill: its tails, tubes and the attacks it may
        start; its thrown hazards stay), a hazard iid, a set of them, or a hazard type / family name."""
        if self.boss_fc is not None:
            return self.boss_fc.occupied_without(x, y, tk, exclude, comfort)
        ex = set(exclude) if isinstance(exclude, (set, frozenset, list, tuple)) else {exclude}
        ids = {int(e) for e in ex if isinstance(e, (int, np.integer))}
        names = {e for e in ex if isinstance(e, str)}
        return self._occ(x, y, tk, ids=ids, names=names)

    def occupied_only(self, x, y, tk, iids) -> np.ndarray:
        """occupied() restricted to these enemies' and hazards' support (the recall's per-type check)."""
        return self._occ(x, y, tk, only={int(i) for i in iids})

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
        owners = set(self.p_owner.tolist()) if self.P is not None else set()
        if self.bb:
            owners |= set(self.bb["owner"].tolist())
        owners |= {b[0] for b in self.boxes} | {p.iid for p in self.paths}
        for o in owners:
            pi = np.zeros(N)
            for arr_owner, arr_p, occ in ((self.p_owner if self.P is not None else np.zeros(0, np.int64),
                                           self.p_prob if self.P is not None else np.zeros(0), self._place_occ),
                                          (self.bb.get("owner", np.zeros(0, np.int64)),
                                           self.bb.get("prob", np.zeros(0)), self._bbox_occ)):
                sel = arr_owner == o
                for pv in np.unique(arr_p[sel]):
                    hit = occ(x, y, tk, sel & (arr_p == pv)).any(axis=1)
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
        """What is already decided: the current attacks, tails, death tails and hazards (no attack or idle instance
        that may start later, no tubes)."""
        if self.boss_fc is not None:
            return MultiForecast(self._fc, self.origin_t, self.horizon, boss=self.boss_fc.committed())
        out = MultiForecast(self._fc, self.origin_t, self.horizon)
        sel = np.flatnonzero(self.p_committed) if self.P is not None else np.zeros(0, np.int64)
        out.P = self.P.take(sel) if self.P is not None else None
        if self.P is not None:
            out.p_owner, out.p_committed = self.p_owner[sel], self.p_committed[sel]
            out.p_family = [self.p_family[i] for i in sel]
            out.p_prob, out.p_on, out.p_off = self.p_prob[sel], self.p_on[sel], self.p_off[sel]
        if self.bb and len(self.bb["owner"]):
            s2 = np.flatnonzero(self.bb["committed"])
            out.bb = {k: ([v[i] for i in s2] if isinstance(v, list) else v[s2]) for k, v in self.bb.items()}
        out.boxes = [b for b in self.boxes if b[1] == "death"]
        out.paths = self.paths
        out.subjects = self.subjects
        out.known = self.known
        out.gen = self.gen
        return out

    def support_set(self, ws: WorldState | None = None, t1: float = SUP_HORIZON_S) -> SupportSet:
        """The supervisor's support: one event per enemy instance with support within t1 (its largest family damage;
        a family with a multi-hit collider: hits 2 and the chain's measured damage, chains.json), one per hazard;
        known when the tables are certified and every enemy in play has a tracked state."""
        if self.boss_fc is not None:
            return self.boss_fc.support_set(ws, t1)
        tables = self._fc.tables
        events = []
        by_owner: dict = defaultdict(set)
        if self.P is not None and len(self.P):
            act = (self.p_off >= 0.0) & (self.p_on <= t1)
            for i in np.flatnonzero(act):
                by_owner[int(self.p_owner[i])].add(self.p_family[i])
        if self.bb and len(self.bb["owner"]):
            act = (self.bb["off"] >= 0.0) & (self.bb["on"] <= t1)
            for i in np.flatnonzero(act):
                by_owner[int(self.bb["owner"][i])].add(self.bb["family"][i])
        for b in self.boxes:
            if b[9] <= t1 and b[10] >= 0.0:
                by_owner[b[0]].add(None)
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
            _, _, on, _ = p.at(np.array([0.0, min(t1, self.horizon)]), slack=False)
            if p.static and (p.t_hi < 0 or p.t_lo > t1):
                continue
            if not p.static and not on.any() and p.tube_from is None:
                continue
            events.append(SupportEvent(p.type_key, p.damage, instance=p.iid))
        known = bool(self.known)
        return SupportSet(tuple(events), known, certified_empty=known and not events)

    def targets(self, tk) -> list[Target]:
        """Each live enemy in play: its body box (the export's colliders when last seen) moved along its velocity
        (hittable while it stays seen); each bell on a path: its circle's box (a redirect target)."""
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


# families whose colliders chain (forum.md §9.2 / §12.3: hornet_multi_wounder colliders)
MULTI_HIT = {("Song Administrator", "MI_CHARGE"): ("Slash Collider",),
             ("Song Administrator", "MI_PARRY"): ("ParrySlash Hit",),
             ("Song Pilgrim 03", "CH_WHIP"): tuple(f"Whip Hit {i}" for i in range(1, 7)) + ("Whip Hit",),
             ("Song Reed", "RE_DEFEND"): ("ParrySlash Hit",)}
