"""One enemy instance of a multi-enemy arena as the view can know it (Forum plan R2, docs/plans/forum_planner_plan.md
§4.3 / §4.6; the single-boss ssbot.combat.forecast.BossTracker is left as it is).

    tr = EnemyTracker(tables.types["Song Reed"], view=ORACLE, iid=-6912)
    e = tr.update(ws)                 # every WorldState, in order: its events, then its entity
    tr.state, tr.t_entry, tr.cur      # Control state (view-dependent), entry, the attack instance with its anchor
    roots, known = tr.roots(t)        # the shape of BossTracker.roots: where the forecast walk starts
    tr.hp_est, tr.hp_sd               # from the hits the view saw (never ents.hp)

Segmentation (the gauntlet builder's, ssbot.knowledge.forum_support.SubjectTracker, which the R0 certification ran
on): entering an attack-start state starts an instance of its family (a second start state of the same family inside
it does not); a decision state ends an attack instance and starts the idle family's; a death state or a killing hit
ends the instance and the enemy. An instance's anchor is the enemy's transform at its first exported frame of the
instance (mirror from flipX: these sprites face -x, FACES_LEFT), which is the tables' anchor frame. Ended attacks are
kept for their tails (tail_max_s + 1 s).

Views (§4.6, the tracker branches by view; MultiForecast above it does not):
  ORACLE              the Control FSM's transitions (FSM_TRANSITION) and its state / time in state on the entity
                      (Entity.fsm), the transform (Entity.pos_transform), the exported velocity.
  VISION_EQUIVALENT   the observable phase and its time (Entity.phase from ObservabilityFilter's per-type phase table:
                      until M3 measures one per type, the placeholder table maps every Control state to itself),
                      the body position (Entity.pos: main collider or sprite centre) less the type's body offset
                      (the tables' anchor.body_offset box_centre, mirrored with the sprite) with its spread as anchor
                      uncertainty, the tracked velocity.
HP in both views from the hits the view saw (HIT_DEALT: the oracle's amount when it reports one, else the price of
the attack that dealt it, FORUM_HIT_DAMAGE), never from the exported HP.
"""
import math
from dataclasses import dataclass, field

from ssbot.combat.boss_model import Anchor
from ssbot.combat.forecast import Ctx, Root
from ssbot.core.worldstate import ORACLE, Entity, Ev, WorldState

FACES_LEFT = (-1, 1)              # flipX False faces -x: mirror -1 (ssbot.knowledge.gauntlet_tables.FACES_LEFT)
TAIL_KEEP_S = 7.0                 # tail_max_s (6 s) + 1 s
# Damage per hit by the attacking object (HitDealt.src, else .attack) in the Forum loadout (fo_A: Reaper, needle 1;
# forum.md §9.2: Hornet's nail 9, Silk Spear 27, Garmond 5, Cogfly 3-4, a redirected bell 9); the vision view's HP
# counts these (the oracle view takes HitDealt.amount when it has one)
FORUM_HIT_DAMAGE = {"Slash": 9.0, "UpSlash": 9.0, "DownSlash New": 9.0, "AltSlash": 9.0, "WallSlash": 9.0,
                    "DashSlash": 9.0, "Needle Damage": 27.0, "WildSlash Enemy Damager": 5.0, "Stomp Damager": 5.0,
                    "Stomp Splash Damager": 5.0, "Charge Damager": 5.0, "Damager": 4.0, "Enemy Damager": 9.0,
                    "Nail": 9.0, "Heavy": 27.0, "Generic": 5.0}
HIT_DAMAGE_DEFAULT = 9.0
HIT_SIGMA = 1.0                   # per counted hit (u of HP); an unpriced hit adds its whole damage


@dataclass(slots=True)
class Instance:
    family: str
    start: str
    t_start: float
    anchor: tuple[float, float] | None = None
    mirror: int = 1
    sd: float = 0.0                # VE: the anchor's uncertainty half-extent (u); 0 in the oracle view
    t_end: float | None = None


@dataclass(slots=True)
class EnemyTracker:
    table: object                  # combat.enemy_tables.TypeTable
    view: str
    iid: int
    offsets: dict | None = None    # VE: {flipX: (dx, dy, spread)} body offset of the type (transform -> Entity.pos)
    state: str | None = None
    t_entry: float | None = None
    cur: Instance | None = None
    ends: list = field(default_factory=list)       # ended instances with an anchor (their tails)
    dead: bool = False
    t_dead: float | None = None
    death_box: tuple | None = None
    pos: tuple[float, float] | None = None         # the transform (oracle) or its estimate (VE)
    pos_sd: float = 0.0
    vel: tuple[float, float] = (0.0, 0.0)
    flip: int = 0
    hidden: bool = True
    seen_T: float = -math.inf
    seen_box: tuple | None = None                  # its active damage boxes' bounding box when last seen
    box: tuple | None = None                       # ... this frame (None: none active or not exported)
    body: tuple | None = None                      # its body polygons' bounding box when last seen (hit targets)
    hp_est: float = 0.0
    hp_sd: float = 0.0
    hits: int = 0
    t: float = 0.0
    in_play: bool = False                          # its Control state is not a waiting one
    _var: float = 0.0

    def __post_init__(self) -> None:
        self.hp_est = float(self.table.spec.hp)

    @property
    def tk(self) -> str:
        return self.table.spec.type_key

    # ---- the walk's segmentation ----

    def _end(self, T: float) -> None:
        c = self.cur
        if c is not None:
            c.t_end = T
            if c.anchor is not None:
                self.ends = [e for e in self.ends if T - e.t_end <= TAIL_KEEP_S] + [c]
        self.cur = None

    def _start(self, fam: str, state: str, T: float) -> None:
        self.cur = Instance(fam, state, T)
        if not self.hidden and self.pos is not None and self.seen_T == T:
            self.cur.anchor, self.cur.mirror, self.cur.sd = self.pos, FACES_LEFT[self.flip], self.pos_sd

    def enter(self, to: str, T: float) -> None:
        """A Control state entry at game time T (SubjectTracker.transition)."""
        tb = self.table
        sp = tb.spec
        self.state, self.t_entry = to, T
        self.in_play = to not in sp.waiting
        cur, idle = self.cur, sp.idle_family
        if to in sp.death_states:
            if cur is not None:
                self._end(T)
            self._die(T)
        elif to in tb.attack_starts and cur is not None and cur.family == tb.attack_starts[to] and to != cur.start:
            pass
        elif to in tb.attack_starts:
            if cur is not None:
                self._end(T)
            self.dead = False
            self._start(tb.attack_starts[to], to, T)
        elif to in tb.decision_states:
            if cur is not None and cur.family != idle:
                self._end(T)
            if not self.dead and self.cur is None:
                self._start(idle, to, T)

    def _die(self, T: float) -> None:
        if not self.dead:
            self.t_dead = T
            self.death_box = self.box if self.box is not None else self.seen_box
        self.dead = True

    def kill(self, T: float) -> None:
        if self.cur is not None:
            self._end(T)
        self._die(T)

    # ---- per frame ----

    def update(self, ws: WorldState) -> Entity | None:
        e = next((x for x in ws.entities if x.id == self.iid), None)
        self.observe(ws.stamp.t_game_s, [ev for ev in ws.events if _about(ev, self.iid)], e)
        return e

    def observe(self, T: float, events, e: Entity | None) -> None:
        """This frame's events about the enemy (in order), then its entity (None: not exported / not seen)."""
        self.t = T
        tb = self.table
        for ev in events:
            d = ev.data
            if ev.kind == Ev.FSM_TRANSITION:
                if self.view == ORACLE and d.fsm == tb.spec.control_fsm and d.to_state:
                    self.enter(d.to_state, T)
            elif ev.kind == Ev.HIT_DEALT:
                self._hit(d)
                if d.killing:
                    self.kill(T)
            elif ev.kind == Ev.ENEMY_KILLED:
                self.kill(T)
        if e is None:
            self.box = None
            return
        if self.view != ORACLE:
            ph = e.phase.top if e.phase is not None else None
            if ph is not None and ph != self.state and ph not in ("unknown", "hidden"):
                self.enter(ph, T - float(e.phase.t_in_phase))
        elif self.state is None and e.fsm:
            ctl = next((f for f in e.fsm if f[0] == tb.spec.control_fsm), None)
            if ctl is not None and ctl[1]:       # first seen before any Control event: its exported state
                self.enter(ctl[1], T - float(ctl[2] or 0.0))
        self.hidden = bool(e.hidden) or (self.view != ORACLE and e.pos.conf <= 0.0)
        self.box = _box_of(e)
        if self.hidden:
            return
        self.flip = 1 if e.flip_x else 0
        if self.view == ORACLE:
            p = e.pos_transform if e.pos_transform is not None else e.pos.v
            self.pos, self.pos_sd = (float(p[0]), float(p[1])), 0.0
        else:
            dx, dy, spread = (self.offsets or {}).get(bool(e.flip_x), (0.0, 0.0, 0.0))
            m = FACES_LEFT[self.flip]
            self.pos = (float(e.pos.v[0]) - m * dx, float(e.pos.v[1]) - dy)
            self.pos_sd = spread + (0.0 if math.isinf(e.pos.sigma) else 3.0 * float(e.pos.sigma))
        v = e.vel.v if e.vel.conf > 0 else (0.0, 0.0)
        self.vel = (0.0 if math.isnan(v[0]) else float(v[0]), 0.0 if math.isnan(v[1]) else float(v[1]))
        self.seen_T = T
        self.seen_box = self.box
        if e.body_polys:
            xs = [p[0] for q in e.body_polys for p in q]
            ys = [p[1] for q in e.body_polys for p in q]
            self.body = (min(xs), min(ys), max(xs), max(ys))
        if self.cur is not None and self.cur.anchor is None:
            self.cur.anchor, self.cur.mirror, self.cur.sd = self.pos, FACES_LEFT[self.flip], self.pos_sd

    def _hit(self, d) -> None:
        """HP from the hits seen: the oracle's amount (an O field: None in the vision view), else the price of the
        attacking object; a hit nobody priced adds its whole default damage to the spread."""
        self.hits += 1
        if self.view == ORACLE and d.amount is not None:
            dmg, var = float(d.amount), 0.0
        else:
            key = next((k for k in (d.src, d.attack) if k is not None and k in FORUM_HIT_DAMAGE), None)
            dmg = FORUM_HIT_DAMAGE[key] if key is not None else HIT_DAMAGE_DEFAULT
            var = HIT_SIGMA ** 2 if key is not None else HIT_DAMAGE_DEFAULT ** 2
        self._var += var
        self.hp_est = max(0.0, self.hp_est - dmg)
        self.hp_sd = math.sqrt(self._var)

    def revive(self) -> None:
        """A pooled enemy (the Maestro's Tinies) summoned again under its iid: full HP again."""
        self.hp_est, self.hp_sd, self._var, self.hits = float(self.table.spec.hp), 0.0, 0.0, 0
        self.dead, self.t_dead, self.death_box = False, None, None

    # ---- the walk's roots ----

    def roots(self, origin_t: float) -> tuple[list[Root], bool]:
        """[Root(current state, its entry relative to the origin, Ctx(family, anchor), current=True)] and whether the
        view knows the state (False: never seen in a state)."""
        if self.state is None or self.t_entry is None:
            return [], False
        e = self.t_entry - origin_t
        c = self.cur
        anc = None if c is None or c.anchor is None else Anchor(c.anchor[0], c.anchor[1], c.mirror)
        return [Root(self.state, e, e, Ctx(family=None if c is None else c.family, anchor=anc), current=True)], True


def _about(ev, iid: int) -> bool:
    d = ev.data
    if ev.kind == Ev.FSM_TRANSITION:
        return d is not None and d.enemy_id == iid
    if ev.kind in (Ev.HIT_DEALT, Ev.ENEMY_KILLED):
        return d is not None and d.target_id == iid
    return False


def _box_of(e: Entity) -> tuple | None:
    """Bounding box of the entity's active damage boxes (None: none)."""
    xs, ys = [], []
    for b in e.dmg_boxes:
        if b.active and b.poly:
            xs += [p[0] for p in b.poly]
            ys += [p[1] for p in b.poly]
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def body_offsets(d: dict) -> dict[bool, tuple[float, float, float]]:
    """{flipX: (dx, dy, spread)}: Entity.pos - transform of a type (mirror-relative dx: pos x = transform x + mirror
    dx), the middle of every family's logged box_centre support (behaviour JSON anchor.body_offset.by_dir_flip), and
    the half-extent of their union as the anchor's uncertainty (vision view)."""
    acc: dict[bool, list] = {}
    for a in d.get("attacks", {}).values():
        bo = (a.get("anchor") or {}).get("body_offset") or {}
        for k, v in (bo.get("by_dir_flip") or {}).items():
            bc = v.get("box_centre")
            if not bc:
                continue
            s = bc["support"]
            f = k.endswith("True")
            r = acc.setdefault(f, [math.inf, -math.inf, math.inf, -math.inf])
            r[0], r[1] = min(r[0], s["dx"][0]), max(r[1], s["dx"][1])
            r[2], r[3] = min(r[2], s["dy"][0]), max(r[3], s["dy"][1])
    out = {}
    for f, (x0, x1, y0, y1) in acc.items():
        out[f] = (0.5 * (x0 + x1), 0.5 * (y0 + y1), max(0.5 * (x1 - x0), 0.5 * (y1 - y0)))
    return out
