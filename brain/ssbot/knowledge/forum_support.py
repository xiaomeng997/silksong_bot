"""Held-out support recall of the Forum behaviour tables (M2 Forum round R0, docs/plans/forum_planner_plan.md §4.4 item
1: the certification before any Forum evaluation): every logged hero contact must lie inside the support forecast L
frames earlier for the enemy it came from, with the tables built from the other fold of fights only.

    tables = FoldTables(extra_dir, fold=0, margins=m)       # behaviour_build --extra output: fold-0 supports + walk
    rec = SubjectRecall(tables, lags=(2, 3, 4))
    rec.run(cache, contacts)                                 # forum_cache of a fold-1 fight, its contacts
    rec.stats, rec.misses

The forecast per enemy (subject) follows the planner's (ssbot.combat.forecast.Forecaster, oracle view) on the
gauntlet builder's segmentation (ssbot.knowledge.behaviour_tables.FightScanner: attack instances from the Control
FSM's transitions, the idle family between attacks, a kill ends the instance): the current state's per-state support
template at the instance's anchor (its transform at the instance's first exported frame, mirror by flipX), the
successors the training fold logged with entry intervals from its logged dwell range (one bin of slack on each side;
a current state already older than its longest logged dwell can end from the next frame on to the horizon; the walk
keeps one entry hull per state and instance, so zero-dwell decision loops end), the tail of an attack once it
can end (hazards outliving it), the tails of ended attacks for tail_max_s, and every armed hazard of a type the
enemy throws by its self template (relative to where and when it armed: a bouncing bell's path depends on where it
was thrown, which the thrower's per-state templates hold only as a union; the oracle sees the arming, vision the
projectile's first detection). Forum anchors vary (no Set L / Set R): an
instance that starts after the origin is anchored at the enemy's position moved along its exported velocity, one
anchor per frame of the horizon, both mirrors (the enemy may turn as it starts). The query is the planner's
SupportQuery over every type's per-state anchor templates dilated by the hero hurtbox half-extents plus the base
margin plus the family's margin; the pairing is the planner's (box of frame c at t_c or box of c - 1 at t_c-1, from
the origin c - L). Multi-hit follow-ups (the builder's `follow`) are left out: the first contact of a chain stands for
it (the supervisor counts the chain's measured damage).

This is an offline evaluator on the recordings' raw exports (ssbot.knowledge.forum_cache); the planner's run-time
multi-enemy forecast (MultiForecast, round R2) reads WorldState and must keep this recall.
"""
import gzip
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ssbot.knowledge import hitbox_tables as hb
from ssbot.knowledge.gauntlet_tables import FACES_LEFT, FORUM_SPECS, HAZARD_ALIASES

BIN = hb.BIN_S
FRAME_S = 1.0 / 60.0
TAIL = "_tail"
HAZARD_DV_U_S = 40.0         # a thrown hazard's velocity change bound per s for its tube (a bounce reverses ~34 u/s)
TUBE_MAX_AGE_S = 0.5         # the current-collider tube starts from a box seen at most this long ago
HAZARD_GONE_S = 0.5          # an armed hazard missing from the export this long has left (behaviour_tables
#                              ABSENT_CLOSE_F: 30 frames)
DWELL_SLACK_S = BIN          # logged dwell ranges are frame-quantised: one bin of slack on each side


def fight_of(row: dict) -> str:
    """The fight id of a contact row ("<run>/i<n>/ep<k>" of "<run>/i<n>/ep<k>/<type>#<iid>")."""
    return row["fight"].rsplit("/", 1)[0]


def margins_from_contacts(rows: list[dict], fold: int | None = None, q: float = 1.0, fights: set | None = None,
                          skip_families: set | frozenset = frozenset()) -> dict[tuple[str, str], float]:
    """Margins from held-out residuals (the q-quantile, 1.0 = max; a residual beyond the search radius counts as
    behaviour_tables.R_MARGIN_SEARCH_U). A contact's held-out residual is against the occupancy of the folds other
    than its own (two folds: the other one), so contacts of fold k calibrate margins for fold (1 - k)'s tables.
    fold / fights: only contacts of that fold / those fights (the calibration side; support_recall --encounter Forum
    certifies other fights of the same fold against the other fold's tables: tables, margins and the certified
    contacts come from three disjoint sets of fights). skip_families: families left without a margin (the idle
    families under the idle body tube):
      (type, family)  the enemy's own colliders: the per-state set ("state:<state>", the contact against the other
                      fold's per-state occupancy at its state and time)
      ("ent", hazard) a thrown hazard's contacts: its self template ("self:<hazard>", relative to where and when it
                      armed); the recall places it for every armed hazard (SubjectTracker.hazards), so a hazard
                      whose path the per-state templates cannot hold (a bell's bounces) does not widen the family"""
    from ssbot.knowledge.behaviour_tables import R_MARGIN_SEARCH_U
    per: dict[tuple, list] = defaultdict(list)
    for r in rows:
        if r.get("follow") or (fold is not None and r.get("fold") != fold) \
                or (fights is not None and fight_of(r) not in fights):
            continue
        ho = r.get("ho") or {}
        own = r.get("tk") == r.get("type")
        if own and r.get("family") in skip_families:
            continue
        if own:
            st = r.get("state")
            k = f"state:{st}"
            if r.get("family") is None or st is None or k not in ho:
                continue
            key = (r["type"], r["family"])
        else:
            k = f"self:{r.get('tk')}"
            if k not in ho:
                continue
            key = ("ent", r["tk"])
        v = ho[k]
        per[key].append(R_MARGIN_SEARCH_U if v is None else float(v))
    return {k: float(np.quantile(v, q)) if v else 0.0 for k, v in per.items()}


def read_contacts(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


@dataclass(slots=True)
class Walk:
    dwell: dict[str, tuple[float, float]]
    succ: dict[str, tuple[str, ...]]


class FoldTables:
    """One fold's support templates of every Forum type (behaviour_build --extra: <enemy>_support_fold<k>.npz) dilated
    for the planner's point query, and that fold's walk (dwell ranges, successors). margins: (type, family) ->
    extra dilation (u); base: added for every key (the planner's margin)."""

    def __init__(self, extra: Path, fold: int, margins: dict[tuple[str, str], float] | None = None,
                 base: float = 0.0, specs=FORUM_SPECS, family_wide: bool = False):
        self.extra, self.fold, self.specs = Path(extra), fold, specs
        self.family_wide = family_wide       # also the family templates (t from the attack start): a structural union
        self.margins = dict(margins or {})
        build = json.loads((self.extra / "build.json").read_text("utf-8"))
        self.walk: dict[str, Walk] = {}
        for tk, w in build["walk"].items():
            d = w["dwell"].get(str(fold), {})
            s = w["succ"].get(str(fold), {})
            self.walk[tk] = Walk({k: (float(v[0]), float(v[1])) for k, v in d.items()},
                                 {k: tuple(v) for k, v in s.items()})
        self.fam_type = {fam: tk for tk, sp in specs.items()
                         for fam in list(sp.attack_starts.values()) + [sp.idle_family]}
        tpls: dict[str, hb.SpaceTimeTemplate] = {}
        self.area: dict[str, tuple[float, float]] = {}      # family -> (mean area per bin without, with its margin)
        for tk, sp in specs.items():
            npz = self.extra / f"{sp.enemy}_support_fold{fold}.npz"
            if not npz.exists():
                continue
            raw, _ = hb.load_templates(npz, prefix=hb.SUPPORT)
            for k, t in raw.items():
                parts = k.split("/")
                if len(parts) not in (3, 4):
                    continue
                if len(parts) == 3 and not (parts[2] == "anchor" and self.family_wide):
                    continue
                if len(parts) == 4 and parts[3] == "world_all" and parts[1].endswith("_ENTRY"):
                    # an entry comes from the wave's fixed spawn point: its world-frame union per state
                    m = base + self.margins.get((tk, parts[1]), 0.0)
                    tpls[k] = t.dilated(rx=hb.HERO_HALF_U[0] + m, ry=hb.HERO_HALF_U[1] + m, key=k)
                    continue
                if len(parts) == 3 and parts[2] == "anchor" and self.family_wide:    # t from the attack start
                    m = base + self.margins.get((tk, parts[1]), 0.0)
                    tpls[k] = t.dilated(rx=hb.HERO_HALF_U[0] + m, ry=hb.HERO_HALF_U[1] + m, key=k)
                    continue
                if parts[1] == "ent" and parts[3] == "self":       # a hazard's self template
                    m = base + self.margins.get(("ent", parts[2]), 0.0)
                elif parts[3] == "anchor":
                    m = base + self.margins.get((tk, parts[1]), 0.0)
                else:
                    continue
                tpls[k] = t.dilated(rx=hb.HERO_HALF_U[0] + m, ry=hb.HERO_HALF_U[1] + m, key=k)
        self.templates = tpls
        self.meta = {k: (t.t0, t.t1) for k, t in tpls.items()}
        self.query = hb.SupportQuery(tpls, hero_half=hb.HERO_HALF_U) if tpls else None

    def key(self, fam: str, state: str) -> str | None:
        k = f"{hb.SUPPORT}{fam}/{state}/anchor"
        return k if k in self.meta else None

    def world_key(self, fam: str, state: str) -> str | None:
        k = f"{hb.SUPPORT}{fam}/{state}/world_all"
        return k if k in self.meta else None

    def family_key(self, fam: str) -> str | None:
        k = f"{hb.SUPPORT}{fam}/anchor"
        return k if k in self.meta else None

    def self_key(self, hazard: str) -> str | None:
        k = f"{hb.SUPPORT}ent/{hazard}/self"
        return k if k in self.meta else None


@dataclass(slots=True)
class Inst:
    family: str
    start: str
    t_start: float
    anchor: tuple | None = None
    mirror: int = 1
    iid: int = 0
    tk: str = ""
    f_start: int = -1
    t_end: float | None = None
    f_end: int | None = None
    end: str | None = None              # "rest" | "chain" | "death" (SubjectTracker log only)
    states: list = field(default_factory=list)   # [(state, T)] entries (SubjectTracker log only)


@dataclass(slots=True)
class Subject:
    iid: int
    tk: str
    state: str | None = None
    t_entry: float | None = None
    cur: Inst | None = None
    dead: bool = False
    ends: list = field(default_factory=list)       # (family, anchor, mirror, t_end) of ended attacks
    pos: tuple = (math.nan, math.nan)
    vel: tuple = (0.0, 0.0)
    flip: int = 0
    hidden: bool = False
    seen_T: float = -math.inf
    name: str | None = None                        # its GameObject name (the Control events' obj)
    box: tuple | None = None                       # its enabled damage colliders' box on the last frame exported
    seen_f: int | None = None                      # the last frame it was seen (not hidden) and its box then
    seen_box: tuple | None = None


class SubjectTracker:
    """Per enemy entity of a fight: Control state and entry, the attack instance with its anchor, ended attacks
    (the gauntlet builder's segmentation, FightScanner._control)."""

    def __init__(self, specs=FORUM_SPECS, tail_keep_s: float | None = None, log: list | None = None):
        self.specs = specs
        self.subjects: dict[int, Subject] = {}
        self.tail_keep_s = tail_keep_s
        self.log = log            # every instance started, in order (ended ones with t_end / f_end / end)
        self.f = -1               # the frame being fed (log only)
        self.hazards: dict[int, list] = {}   # thrown hazard iid -> [type, armed, arm time, arm position, last seen]
        self.T = 0.0              # game time of the frame being fed

    def subject(self, iid: int, tk: str) -> Subject:
        s = self.subjects.get(iid)
        if s is None:
            s = self.subjects[iid] = Subject(iid, tk)
        return s

    def _end(self, s: Subject, T: float, why: str = "rest") -> None:
        c = s.cur
        if c is not None:
            c.t_end, c.f_end, c.end = T, self.f, why
        if c is not None and c.anchor is not None:
            keep = self.tail_keep_s if self.tail_keep_s is not None else self.specs[s.tk].tail_max_s + 1.0
            s.ends = [e for e in s.ends if T - e[3] <= keep] + [(c.family, c.anchor, c.mirror, T)]
        s.cur = None

    def _start(self, s: Subject, fam: str, to: str, T: float) -> None:
        s.cur = Inst(fam, to, T, iid=s.iid, tk=s.tk, f_start=self.f)
        if self.log is not None:
            self.log.append(s.cur)
        if not s.hidden and not math.isnan(s.pos[0]) and s.seen_T == T:
            s.cur.anchor, s.cur.mirror = s.pos, FACES_LEFT[s.flip]

    def transition(self, iid: int, tk: str, to: str, T: float, name: str | None = None) -> None:
        sp = self.specs[tk]
        s = self.subject(iid, tk)
        if name:
            s.name = name
        s.state, s.t_entry = to, T
        cur, idle = s.cur, sp.idle_family
        if to in sp.death_states:
            if cur is not None:
                self._end(s, T, "death")
            s.dead = True
        elif to in sp.attack_starts and cur is not None and cur.family == sp.attack_starts[to] and to != cur.start:
            pass
        elif to in sp.attack_starts:
            if cur is not None:
                self._end(s, T, "chain")
            s.dead = False
            self._start(s, sp.attack_starts[to], to, T)
        elif to in sp.decision_states:
            if cur is not None and cur.family != idle:
                self._end(s, T)
            if idle is not None and not s.dead and s.cur is None:
                self._start(s, idle, to, T)
        if self.log is not None and s.cur is not None:
            s.cur.states.append((to, T))

    def hazard(self, iid: int, tk: str, T: float, x: float, y: float, armed: bool, box=None,
               vel=(0.0, 0.0)) -> None:
        """A thrown hazard's frame: an arming (armed now, not on its last frame) records where and when (its self
        template's origin, the gauntlet builder's EntitySeg.arm_T / arm_pos)."""
        h = self.hazards.get(iid)
        if h is None:
            h = self.hazards[iid] = [tk, False, T, (float(x), float(y)), T, (float(x), float(y)), None, (0.0, 0.0)]
        if armed and (not h[1] or T - h[4] > 2.5 * FRAME_S):    # (re-)armed, or back in the export (pooled)
            h[0], h[2], h[3] = tk, T, (float(x), float(y))
        if tk is not None:
            h[0] = tk
        h[1], h[4], h[5] = armed, T, (float(x), float(y))
        if box is not None and not math.isnan(float(box[0])):    # its damage box relative to it (kept while off)
            h[6] = (float(box[0]) - x, float(box[1]) - y, float(box[2]) - x, float(box[3]) - y)
        h[7] = (float(vel[0]), float(vel[1]))

    def kill(self, iid: int, T: float) -> None:
        s = self.subjects.get(iid)
        if s is not None:
            if s.cur is not None:
                self._end(s, T, "death")
            s.dead = True

    def entity(self, iid: int, tk: str, T: float, x: float, y: float, vx: float, vy: float, flip: int,
               hidden: bool, state: str | None = None, tin: float | None = None, box=None) -> None:
        s = self.subject(iid, tk)
        s.hidden = hidden
        s.box = None if box is None or math.isnan(float(box[0])) else tuple(float(v) for v in box)
        if not hidden:
            s.pos, s.vel, s.flip, s.seen_T = (float(x), float(y)), (float(vx), float(vy)), int(flip), T
            s.seen_f, s.seen_box = self.f, s.box
            if s.cur is not None and s.cur.anchor is None:
                s.cur.anchor, s.cur.mirror = s.pos, FACES_LEFT[s.flip]
        if s.state is None and state is not None:      # seen before any Control event: its exported state
            s.state, s.t_entry = state, T - (tin or 0.0)


class SubjectRecall:
    """Run the trackers over a fight's cache and test the contacts (see the module docstring)."""

    def __init__(self, tables: FoldTables, lags=(2, 3, 4), tube_speed: dict[str, float] | None = None,
                 tube_skin: float = 0.1, idle_growth: dict[str, list[float]] | None = None):
        self.t = tables
        self.lags = tuple(lags)
        self.tube = tube_speed is not None
        self.tube_speed = dict(tube_speed or {})
        self.body_rel: dict[str, tuple] = {}     # type -> body collider hull relative to its position (body_hulls)
        self.tube_skin = tube_skin
        # the idle body tube (idle_tube_growth): an enemy in its idle family is forecast by its body as last seen,
        # moved along its exported velocity and grown by g[frames since the sighting], instead of the idle family's
        # per-state templates (anchored at the idle start they cover most of the arena: an idle Minister chases)
        self.idle_growth = dict(idle_growth) if idle_growth is not None else None
        self.stats: dict = defaultdict(Counter)
        self.misses: list[dict] = []
        self.placements = Counter()
        self._raw_src: dict = {}

    # ---- the walk ----

    def _place(self, out: list, key: str | None, e_lo: float, e_hi: float, anchors, H: float) -> None:
        if key is None:
            return
        t0, t1 = self.t.meta[key]
        # entries on the 1/60 s grid from e_lo (and e_hi itself), only those whose active span meets [-BIN, H + BIN]
        lo, hi = max(e_lo, -BIN - t1), min(e_hi, H + BIN - t0)
        if hi < lo - 1e-9:
            return
        i0 = max(0, int(math.ceil((lo - e_lo) / BIN - 1e-6)))
        i1 = int(math.floor((hi - e_lo) / BIN + 1e-6))
        es = [e_lo + i * BIN for i in range(i0, i1 + 1)]
        if e_hi <= hi + 1e-9 and (not es or es[-1] < e_hi - 1e-3):
            es.append(e_hi)
        for e in es:
            on, off = e + t0, e + t1
            if off < -BIN or on > H + BIN:
                continue
            for ax, ay, m in anchors:
                out.append((key, -e, (ax, ay), m))

    def _place_world(self, out: list, key: str | None, e_lo: float, e_hi: float, H: float) -> None:
        """A world-frame template (no anchor): the same entries as _place."""
        if key is None:
            return
        tmp: list = []
        self._place(tmp, key, e_lo, e_hi, [(0.0, 0.0, 1)], H)
        out += [(k, t, None, 1) for k, t, _, _ in tmp]

    def placements_of(self, s: Subject, T_o: float, H: float, anchor_step: int = 1,
                      hazards: list | None = None) -> list[tuple]:
        """SupportQuery placements (key, t_ref, anchor, mirror) of one subject at origin T_o (no duplicates).
        anchor_step: frames between the anchors of instances that start after the origin (1 = every frame: the
        recall; a coarser step for long horizons is an approximation for statistics, not a support). hazards:
        (type, arm time, arm position) of the armed hazards to place by their self templates."""
        sp = self.t.specs[s.tk]
        w = self.t.walk.get(s.tk)
        out: list = []
        for fam, anc, mir, t_end in s.ends:
            e = t_end - T_o
            self._place(out, self.t.key(fam, TAIL), e, e, [(anc[0], anc[1], mir)], H)
        for htk, arm_T, pos in hazards or ():
            if arm_T is None:       # not armed: it may arm from the next frame on, where it is now
                self._place(out, self.t.self_key(htk), BIN, H, [(pos[0], pos[1], 1)], H)
            else:
                e = arm_T - T_o
                self._place(out, self.t.self_key(htk), e, e, [(pos[0], pos[1], 1)], H)
        if w is not None and s.state is not None and s.t_entry is not None:
            k_max = int(math.ceil(H / FRAME_S))
            x, y = s.pos
            if math.isnan(x):
                new: tuple = ()
            else:
                vx, vy = s.vel
                ks = sorted(set(range(0, k_max + 1, max(1, anchor_step))) | {k_max})
                pts = {(round(x + vx * k * FRAME_S, 4), round(y + vy * k * FRAME_S, 4)) for k in ks}
                new = tuple((px, py, m) for px, py in sorted(pts) for m in (-1, 1))
            cur = s.cur
            ctx = skip = None
            if cur is not None:
                anc = ((cur.anchor[0], cur.anchor[1], cur.mirror),) if cur.anchor is not None else new
                ctx = (cur.family, cur.start, anc)
                if self.idle_tube_ok(s, T_o):
                    skip = ctx               # the current idle instance: its body tube (in_idle_tube) instead
                elif self.t.family_wide:     # the union over every state at the time since the attack start
                    e = cur.t_start - T_o
                    self._place(out, self.t.family_key(cur.family), e, e, list(anc), H)
            e0 = s.t_entry - T_o
            self._walk(sp, w, s.state, e0, ctx, new, s.dead, H, out, skip)
        return list(dict.fromkeys(out))

    def idle_tube_ok(self, s: Subject, T_o: float) -> bool:
        """Whether the idle body tube stands for the subject's current idle instance at origin T_o (calibrated for
        its type, seen at most TUBE_MAX_AGE_S before)."""
        return self.idle_growth is not None and s.cur is not None and not s.dead and s.tk in self.idle_growth \
            and s.cur.family == self.t.specs[s.tk].idle_family and s.seen_f is not None \
            and T_o - s.seen_T <= TUBE_MAX_AGE_S

    def in_idle_tube(self, s: Subject, pts: list[tuple], T_o: float) -> bool:
        """The idle body tube: the subject's damage box as last seen (no damage collider then: its type's body hull at
        its position), moved along its exported velocity for the game time since, grown by the type's calibrated
        g[tube_bin(game time since the sighting)] (beyond the calibration: not covered) plus the hero half-extents."""
        g = self.idle_growth.get(s.tk) if self.idle_growth is not None else None
        if g is None or s.seen_f is None:
            return False
        b = s.seen_box
        if b is None:
            rel = self.body_rel.get(s.tk)
            if rel is None or math.isnan(s.pos[0]):
                return False
            b = (s.pos[0] + rel[0], s.pos[1] + rel[1], s.pos[0] + rel[2], s.pos[1] + rel[3])
        age = T_o - s.seen_T
        vx, vy = s.vel
        hx, hy = hb.HERO_HALF_U[0] + 1e-3, hb.HERO_HALF_U[1] + 1e-3
        for x, y, tau, *_ in pts:
            dt = age + tau
            n = int(tube_bin(dt))
            if n >= len(g):
                continue
            gx = g[n]
            if b[0] + vx * dt - hx - gx <= x <= b[2] + vx * dt + hx + gx and \
                    b[1] + vy * dt - hy - gx <= y <= b[3] + vy * dt + hy + gx:
                return True
        return False

    def _walk(self, sp, w: Walk, state: str, e0: float, ctx, new, dead: bool, H: float, out: list,
              skip=None) -> None:
        """The support walk as a worklist over (state, instance context, dead): each node keeps the hull of its
        entry intervals (a superset of every path's: conservative), entries past the horizon are dropped, so the
        decision chains' zero-dwell loops end. skip: an instance context whose nodes are walked but not placed (the
        current idle instance under the idle body tube)."""
        idle = sp.idle_family
        cap = H + BIN
        nodes: dict[tuple, list] = {}
        todo: list[tuple] = []

        def push(st, lo, hi, c, d, current=False):
            if lo > cap:
                return
            hi = min(hi, cap)
            if not current:          # a state not entered yet enters from the next frame on (the hull stays bounded)
                lo, hi = max(lo, BIN), max(hi, BIN)
            k = (st, c, d, current)
            iv = nodes.get(k)
            if iv is None:
                nodes[k] = [lo, hi]
            elif lo < iv[0] - 1e-9 or hi > iv[1] + 1e-9:
                iv[0], iv[1] = min(iv[0], lo), max(iv[1], hi)
            else:
                return
            todo.append(k)

        push(state, e0, e0, ctx, dead, True)
        steps = 0
        while todo:
            k = todo.pop()
            st, c, d, current = k
            lo, hi = nodes[k]
            steps += 1
            if steps > 20000:
                self.placements["walks cut at 20000 steps"] += 1
                break
            fam = c[0] if c else None
            dw = w.dwell.get(st)
            if dw is None:
                continue
            # the training fold's dwell range, one bin of frame-time slack on each side; a current state already
            # older than its longest logged dwell (a held-out instance) can end at any time from the next frame on
            x_lo, x_hi = lo + dw[0] - DWELL_SLACK_S, hi + dw[1] + DWELL_SLACK_S
            if current:
                x_lo = max(x_lo, BIN)
                x_hi = cap if x_hi < BIN else x_hi
            if x_lo > cap:
                continue
            for nxt in w.succ.get(st, ()):
                if nxt in sp.death_states:
                    continue
                c2, d2 = c, d
                if nxt in sp.attack_starts:
                    nf = sp.attack_starts[nxt]
                    if not (c is not None and c[0] == nf and nxt != c[1]):
                        if fam is not None and fam != idle:
                            push(TAIL, x_lo, x_hi, c, d)
                        c2, d2 = (nf, nxt, new), False
                elif nxt in sp.decision_states:
                    if fam is not None and fam != idle:
                        push(TAIL, x_lo, x_hi, c, d)
                        c2 = (idle, nxt, new) if idle and not d else None
                    elif fam is None and idle and not d:
                        c2 = (idle, nxt, new)
                push(nxt, x_lo, x_hi, c2, d2)
        for (st, c, d, current), (lo, hi) in nodes.items():
            if c is None or (skip is not None and c is skip):
                continue
            self._place(out, self.t.key(c[0], st), lo, hi, c[2], H)
            if c[0].endswith("_ENTRY"):
                self._place_world(out, self.t.world_key(c[0], st), lo, hi, H)

    def in_tube(self, s: Subject, pts: list[tuple[float, float, float]], T_o: float) -> bool:
        """The enemy's damage colliders as last exported (its box on the last frame it was seen, at most
        TUBE_MAX_AGE_S before the origin) moved at most its type's top speed (tube_speed: measured on the training
        fold) since then: the current-collider tube, tried after every forecast failed. Outside every attack instance
        no behaviour template applies (a dying body - the export drops an enemy on its kill frame while its body still
        hurts for some frames, forum_products death_tails - a waiting body, a parked summon); in an attack it catches
        the enemy's own body beyond its family's margin. Only for the recall's lags; counted apart."""
        age = T_o - s.seen_T
        if age > TUBE_MAX_AGE_S:
            return False
        b = s.box
        if b is None:       # no damage collider exported (an entering leap): the type's body hull at its position
            rel = self.body_rel.get(s.tk)
            if rel is None or math.isnan(s.pos[0]):
                return False
            b = (s.pos[0] + rel[0], s.pos[1] + rel[1], s.pos[0] + rel[2], s.pos[1] + rel[3])
        v = self.tube_speed.get(s.tk, 0.0)
        hx, hy = hb.HERO_HALF_U[0] + self.tube_skin, hb.HERO_HALF_U[1] + self.tube_skin
        for x, y, tau, *_ in pts:
            g = v * (age + tau)
            if b[0] - hx - g <= x <= b[2] + hx + g and b[1] - hy - g <= y <= b[3] + hy + g:
                return True
        return False

    def in_hazard_tube(self, tr: SubjectTracker, sp, pts: list[tuple[float, float, float]], T_o: float) -> bool:
        """A thrown hazard's damage box (its last enabled one, relative to it, at its last exported position: a
        nail hit turns its collider off for a few frames) moved along its exported velocity, grown by
        HAZARD_DV_U_S x the elapsed time (a bounce or a nail hit turns it; Throwing Bell speeds stay <= 34 u/s): for
        the recall's lags only (the run-time model is its path, round R2)."""
        hx, hy = hb.HERO_HALF_U[0] + self.tube_skin, hb.HERO_HALF_U[1] + self.tube_skin
        for h in tr.hazards.values():
            if h[6] is None or T_o - h[4] > HAZARD_GONE_S or not any(n.startswith(sp.projectiles)
                                                                      for n in _names(h[0])):
                continue
            rel, (vx, vy), (px, py) = h[6], h[7], h[5]
            b = (px + rel[0], py + rel[1], px + rel[2], py + rel[3])
            for x, y, tau, *_ in pts:
                t = tau + (T_o - h[4])
                g = HAZARD_DV_U_S * t
                if b[0] + vx * t - hx - g <= x <= b[2] + vx * t + hx + g and \
                        b[1] + vy * t - hy - g <= y <= b[3] + vy * t + hy + g:
                    return True
        return False

    def covered(self, placements: list, pts: list[tuple[float, float, float]]) -> bool:
        q = self.t.query
        if q is None or not placements:
            return False
        q.clear()
        for key, t_ref, anchor, mirror in placements:
            q.place(key, t_ref, anchor, mirror)
        for x, y, tau, *_ in pts:
            if q.query(np.array([[x]]), np.array([[y]]), np.array([tau]))[0, 0]:
                return True
        return False

    # ---- one fight ----

    def run(self, cache: dict, contacts: list[dict], label: str = "") -> None:
        specs = self.t.specs
        f_arr, T_arr = cache["f"], cache["T"]
        fi_of = {int(f): i for i, f in enumerate(f_arr)}
        need: dict[int, list] = defaultdict(list)            # origin frame -> [(contact, lag)]
        for c in contacts:
            if c.get("follow"):
                self.stats[("follow-up (not checked)", 0)]["n"] += 1
                continue
            for L in self.lags:
                need[int(c["f"]) - L].append((c, L))
        self._raw_src = raw_sources(cache)
        tr = SubjectTracker(specs)
        H = (max(self.lags) + 1) * FRAME_S + 1e-6
        for i, f, T in replay(cache, tr, specs):
            for c, L in need.get(f, ()):
                self._check(c, L, tr, T, fi_of, T_arr, H, label)

    def _check(self, c: dict, L: int, tr: SubjectTracker, T_o: float, fi_of: dict, T_arr, H: float,
               label: str) -> None:
        key = (c["type"], L)
        st = self.stats[key]
        st["n"] += 1
        if c.get("family") is None:
            st["outside_attacks"] += 1
        iid = int(c["fight"].rsplit("#", 1)[1])
        s = tr.subjects.get(iid)
        cf = int(c["f"])
        pts = []
        for fr, box in zip((cf - 1, cf), c["boxes"][-2:] if len(c["boxes"]) >= 2 else [None] + c["boxes"]):
            if box is None or fr not in fi_of:
                continue
            pts.append((0.5 * (box[0] + box[2]), 0.5 * (box[1] + box[3]), float(T_arr[fi_of[fr]]) - T_o, fr))
        how = None
        if s is not None and pts:
            # the gauntlet builder attributes a contact by the GameObject name (a waiting wave-12 "Song Reed" and the
            # wave-0 one share it): every subject of that name is a candidate, the attributed one first (a subject
            # seen only in its waiting state never had a Control event to name it: every one of its type); a source
            # that names no enemy at all ("Colliders/Collider Fly": the builder took one of the Ministers exporting
            # that collider, not always the one touching) makes every subject of the type a candidate
            raw = self._raw_src.get(cf, ())      # the event's own source (the row's src carries the builder's pick)
            unnamed = c.get("tk") == c.get("type") and bool(raw) and not any(names_enemy(x, s.tk) for x in raw)
            names = [s] + [o for o in tr.subjects.values() if o is not s and o.tk == s.tk
                           and (unnamed or s.name is None or o.name is None or o.name == s.name)]
            other = "unnamed-source candidate" if unnamed else "namesake"
            for k, o in enumerate(names):
                pl = self.placements_of(o, T_o, H, hazards=thrown(tr, self.t.specs[o.tk]))
                self.placements["placements"] += len(pl)
                self.placements["forecasts"] += 1
                if self.covered(pl, pts):
                    how = "forecast" if k == 0 else f"{other} forecast"
                    break
                if self.idle_tube_ok(o, T_o):
                    self.placements["idle body tubes"] += 1
                    if self.in_idle_tube(o, pts, T_o):
                        how = "idle body tube" if k == 0 else f"{other} idle body tube"
                        break
            if how is None and self.tube:
                for k, o in enumerate(names):
                    if self.in_tube(o, pts, T_o):
                        how = ("current-collider tube" if k == 0 else f"{other} tube") + \
                            (" (outside attacks)" if o.cur is None else " (in an attack)")
                        break
            if how is None and self.tube and self.t.specs[s.tk].projectiles and \
                    self.in_hazard_tube(tr, self.t.specs[s.tk], pts, T_o):
                how = "hazard tube"
        if how is not None:
            st["covered"] += 1
            if how == "idle body tube":       # part of the forecast (the idle family's model), counted apart
                st["forecast: idle body tube"] += 1
            elif how != "forecast":
                st[f"covered by {how}"] += 1
            return
        self.misses.append({"fight": c["fight"], "f": cf, "lag": L, "type": c["type"], "family": c.get("family"),
                            "state": c.get("state"), "ts": c.get("ts"), "src": c.get("src"), "kind": c.get("kind"),
                            "subject_state": None if s is None else s.state,
                            "subject_family": None if s is None or s.cur is None else s.cur.family,
                            "ho": c.get("ho"), "label": label})


def top_speeds(caches, specs=FORUM_SPECS, jump_u: float = 1.2, min_dt: float = 0.012,
               q: float = 0.9999) -> dict[str, float]:
    """Per enemy type the q-quantile speed (u per game s) of its transform between consecutive exported frames over
    the given fight caches: frames with a game step shorter than min_dt (hit-stop, the end-of-battle slow motion: a
    small step over a real-time move reads as hundreds of u/s) and moves longer than jump_u in one frame (teleports,
    pooled respawns) are left out. 2026-10-04, 9 fights: p99.99 31-56 u/s per type, the maxima 43-66 u/s
    (Clapper jump launch, Minister charge). The current-collider tube's growth rate."""
    vals: dict[str, list] = defaultdict(list)
    for c in caches:
        types = c["types"]
        order = np.lexsort((c["e_fi"], c["e_iid"]))
        iid, fi = c["e_iid"][order], c["e_fi"][order]
        x, y, tk = c["e_x"][order].astype(np.float64), c["e_y"][order].astype(np.float64), c["e_tk"][order]
        same = (iid[1:] == iid[:-1]) & (fi[1:] == fi[:-1] + 1)
        dt = np.diff(c["T"])[fi[:-1].clip(0, len(c["T"]) - 2)]
        d = np.hypot(np.diff(x), np.diff(y))
        ok = same & (dt >= min_dt) & (d <= jump_u)
        for k in np.unique(tk[:-1][ok]):
            t = types[int(k)]
            if t in specs:
                m = ok & (tk[:-1] == k)
                vals[t].append(d[m] / dt[m])
    return {t: float(np.quantile(np.concatenate(v), q)) for t, v in vals.items()}


IDLE_TUBE_N = 40             # time bins (1/60 s) from an idle body's last sighting the idle body tube is calibrated
#                              for (the recall's lags plus TUBE_MAX_AGE_S)


def idle_rows(cache: dict, specs=FORUM_SPECS) -> np.ndarray:
    """Per entity row of the cache: the start frame of the subject's current idle-family instance at that frame
    (SubjectTracker on the replay: the gauntlet builder's segmentation), -1 outside idle (an attack, waiting, dead)."""
    out = np.full(len(cache["e_fi"]), -1, np.int64)
    tr = SubjectTracker(specs)
    starts = np.searchsorted(cache["e_fi"], np.arange(len(cache["f"]) + 1))
    types = cache["types"]
    for i, f, T in replay(cache, tr, specs):
        for r in range(starts[i], starts[i + 1]):
            tk = types[int(cache["e_tk"][r])]
            if tk not in specs:
                continue
            s = tr.subjects.get(int(cache["e_iid"][r]))
            if s is not None and s.cur is not None and s.cur.family == specs[tk].idle_family and not s.dead:
                out[r] = s.cur.f_start
    return out


def idle_tube_samples(cache: dict, hulls: dict[str, tuple], specs=FORUM_SPECS, n_max: int = IDLE_TUBE_N) \
        -> dict[str, np.ndarray]:
    """Dead-reckoning residuals of idle bodies: per type a dict time bin -> values (tube_bin of the game time between
    the two frames) of how far the enemy's damage box n = 1..n_max frames later lies outside its box at frame i moved
    along its exported velocity at i for the game time between them (the larger of the four edge excesses, 0
    inside), over every pair of exported, visible frames of one idle-family instance (no damage collider at i: the
    type's body hull at its position; none at i + n: no sample, it cannot hurt); bins past n_max are dropped. The idle
    body tube's growth (IdleTubeCalibration)."""
    iid, fi = cache["e_iid"], cache["e_fi"].astype(np.int64)
    inst = idle_rows(cache, specs)
    vis = cache["e_hidden"] == 0
    ok = (inst >= 0) & vis
    rows = np.flatnonzero(ok)
    if not len(rows):
        return {}
    types = cache["types"]
    tk_r = cache["e_tk"][rows]
    box = cache["e_box"][rows].astype(np.float64)
    x, y = cache["e_x"][rows].astype(np.float64), cache["e_y"][rows].astype(np.float64)
    nan = np.isnan(box[:, 0])
    for k in np.unique(tk_r[nan]):           # no damage collider at i: the body hull at its position
        h = hulls.get(types[int(k)])
        m = nan & (tk_r == k)
        if h is None:
            continue
        box[m] = np.stack([x[m] + h[0], y[m] + h[1], x[m] + h[2], y[m] + h[3]], axis=1)
    vx, vy = cache["e_vx"][rows].astype(np.float64), cache["e_vy"][rows].astype(np.float64)
    T = cache["T"]
    fi_r, inst_r = fi[rows], inst[rows]
    ebox = cache["e_box"][rows]
    has_j = ~np.isnan(ebox[:, 0])
    # pair rows of the same subject and idle instance n frames apart
    _, rank = np.unique(iid[rows], return_inverse=True)
    key = rank.astype(np.int64) * (int(fi.max()) + n_max + 2) + fi_r
    order = np.argsort(key, kind="stable")
    ks = key[order]
    out: dict[str, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    for n in range(1, n_max + 1):
        pos = np.searchsorted(ks, key + n)
        hit = pos < len(ks)
        pos = np.where(hit, pos, 0)
        j = order[pos]
        hit &= (ks[pos] == key + n) & (inst_r[j] == inst_r) & has_j[j] & ~np.isnan(box[:, 0])
        if not hit.any():
            continue
        a = np.flatnonzero(hit)
        b = j[a]
        dt = T[fi_r[b]] - T[fi_r[a]]
        sx, sy = vx[a] * dt, vy[a] * dt
        bj = ebox[b].astype(np.float64)
        e = np.maximum.reduce([box[a, 0] + sx - bj[:, 0], bj[:, 2] - (box[a, 2] + sx),
                               box[a, 1] + sy - bj[:, 1], bj[:, 3] - (box[a, 3] + sy), np.zeros(len(a))])
        kb = tube_bin(dt)                    # by game time, not frames: a hitch spans 0.5 s in 4 frames
        for k in np.unique(tk_r[a]):
            m = tk_r[a] == k
            for t_bin in np.unique(kb[m]):
                if t_bin <= n_max:
                    out[types[int(k)]][int(t_bin)].append(e[m & (kb == t_bin)])
    return {tk: {n: np.concatenate(v) for n, v in d.items()} for tk, d in out.items()}


def tube_bin(dt):
    """The idle body tube's time bin of a game-time span (s): bins of one frame (BIN), rounded up with a 5 % tolerance
    for frame-time jitter; the calibration and the query use the same."""
    return np.maximum(0, np.ceil(np.asarray(dt, np.float64) / BIN - 0.05)).astype(np.int64)


class IdleTubeCalibration:
    """The idle body tube's growth from training fights, streamed (idle_tube_samples per cache; per type and n the
    exact maximum and a HIST_U histogram for the quantiles):

        cal = IdleTubeCalibration(hulls)
        for cache in training_caches: cal.add(cache)
        g = cal.growth(q=1.0)          # type -> [g_0, ..., g_n_max] per tube_bin of game time, non-decreasing"""

    HIST_U = 0.01
    HIST_N = 2000

    def __init__(self, hulls: dict[str, tuple], specs=FORUM_SPECS, n_max: int = IDLE_TUBE_N):
        self.hulls, self.specs, self.n_max = hulls, specs, n_max
        self.max: dict[str, np.ndarray] = {}
        self.hist: dict[str, np.ndarray] = {}
        self.fights = 0

    def add(self, cache: dict) -> None:
        self.fights += 1
        for tk, d in idle_tube_samples(cache, self.hulls, self.specs, self.n_max).items():
            if tk not in self.max:
                self.max[tk] = np.zeros(self.n_max + 1)
                self.hist[tk] = np.zeros((self.n_max + 1, self.HIST_N + 1), np.int64)
            for n, v in d.items():
                self.max[tk][n] = max(self.max[tk][n], float(v.max()))
                self.hist[tk][n] += np.bincount(np.minimum((v / self.HIST_U).astype(np.int64), self.HIST_N),
                                                minlength=self.HIST_N + 1)

    def growth(self, q: float = 1.0) -> dict[str, list[float]]:
        """q = 1.0: the maximum; else the upper edge of the histogram bin holding the q-quantile (capped by the
        maximum)."""
        out = {}
        for tk, mx in self.max.items():
            g = [0.0]
            for n in range(0, self.n_max + 1):
                h = self.hist[tk][n]
                if q >= 1.0 or not h.sum():
                    v = float(mx[n])
                else:
                    k = int(np.searchsorted(np.cumsum(h), q * h.sum()))
                    v = min(float(mx[n]), (k + 1) * self.HIST_U)
                g.append(max(g[-1], v))
            out[tk] = [math.ceil(x * 1e4) / 1e4 for x in g[1:]]  # rounded up: never below the calibration
        return out

    def samples(self) -> dict[str, list[int]]:
        return {tk: [int(x) for x in h.sum(axis=1)] for tk, h in self.hist.items()}


def raw_sources(cache: dict) -> dict[int, list[str]]:
    """Contact frame -> the sources the oracle's events name (a "damage" event on its frame, a "damage_blocked"
    stretch on each of its frames), as reported (the contact rows' src carries the gauntlet builder's pick)."""
    out: dict[int, list[str]] = defaultdict(list)
    for f, k, d in cache["events"]:
        if k == "damage":
            out[int(f)].append(str(d.get("source")))
        elif k == "damage_blocked" and isinstance(d.get("first_f"), int) and isinstance(d.get("last_f"), int):
            for g in range(d["first_f"], d["last_f"] + 1):
                out[g].append(str(d.get("source")))
    return out


def names_enemy(src, tk: str) -> bool:
    """Whether a contact's source path names an enemy of type tk by its GameObject ("Song Administrator (1)/Colliders/
    Collider Fly", "Wave 12/Song Reed"), not only a collider child ("Colliders/Collider Fly")."""
    from ssbot.train.gauntlet import type_key
    return any(type_key(p.replace("(Clone)", "").strip()) == tk for p in str(src or "").split("/") if p)


def _names(tk: str) -> tuple[str, ...]:
    """The hazard types an exported name may be (a shared name whose radius is not known yet: each alias)."""
    return tuple(n for _, n in HAZARD_ALIASES[tk]) if tk in HAZARD_ALIASES else (tk,)


def body_hulls(caches, specs=FORUM_SPECS) -> dict[str, tuple]:
    """Per enemy type the hull of its body colliders (forum_products.body_collider: the root collider, the
    Choristor's Body Damager, the Minister's "Collider ..." boxes) relative to its transform, over the given caches."""
    from ssbot.knowledge.forum_products import body_collider
    out: dict[str, list] = {}
    for c in caches:
        names, types = c["names"], c["types"]
        ei = c["c_ei"]
        for j in range(len(ei)):
            r = int(ei[j])
            tk = types[int(c["e_tk"][r])]
            if tk not in specs:
                continue
            n = int(c["c_name"][j])
            if not body_collider(tk, names[n] if n >= 0 else None):
                continue
            b = c["c_box"][j]
            x, y = float(c["e_x"][r]), float(c["e_y"][r])
            rel = (float(b[0]) - x, float(b[1]) - y, float(b[2]) - x, float(b[3]) - y)
            h = out.get(tk)
            out[tk] = list(rel) if h is None else [min(h[0], rel[0]), min(h[1], rel[1]), max(h[2], rel[2]),
                                                   max(h[3], rel[3])]
    return {k: tuple(v) for k, v in out.items()}


def thrown(tr: SubjectTracker, sp) -> list[tuple]:
    """(type, arm time or None, position) of the hazards of the types this enemy type throws that are in the export:
    armed ones from where and when they armed; the others (a rune waiting to burst, a bell between a nail hit and its
    collider coming back) may arm within the horizon where they are now (arm time None)."""
    if not sp.projectiles:
        return []
    out = []
    for h in tr.hazards.values():
        if tr.T - h[4] > HAZARD_GONE_S:
            continue
        for n in _names(h[0]):
            if not n.startswith(sp.projectiles):
                continue
            if h[1] and n == h[0]:
                out.append((n, h[2], h[3]))
            elif tr.T - h[4] <= 2.5 * FRAME_S:
                out.append((n, None, h[5]))
    return out


def replay(cache: dict, tr: SubjectTracker, specs=FORUM_SPECS):
    """Feed a fight's cache to the tracker frame by frame (the Control events and kills first, then the entities, as
    the gauntlet builder does); yields (frame index, frame, game time) after each frame."""
    types, states = cache["types"], cache["states"]
    f_arr, T_arr = cache["f"], cache["T"]
    evs: dict[int, list] = defaultdict(list)
    for f, k, d in cache["events"]:
        if k in ("fsm", "hit"):
            evs[int(f)].append((k, d))
    starts = np.searchsorted(cache["e_fi"], np.arange(len(f_arr) + 1))
    tk_ok = np.array([t in specs for t in types], bool)
    prefixes = tuple(p for sp in specs.values() for p in sp.projectiles)
    haz_ok = np.array([t not in specs and (t in HAZARD_ALIASES or t.startswith(prefixes)) for t in types], bool)         if prefixes else np.zeros(len(types), bool)
    rest = frozenset(st for sp in specs.values() if sp.projectiles for st in sp.rest_states)
    alias: dict[int, str] = {}
    for i, f in enumerate(f_arr):
        f = int(f)
        T = float(T_arr[i])
        tr.f, tr.T = f, T
        for k, d in evs.get(f, ()):
            if k == "fsm":
                tk = _type_of(d.get("obj"), specs)
                if tk is not None and d.get("fsm") == specs[tk].control_fsm and isinstance(d.get("to"), str)                         and isinstance(d.get("ent"), int):
                    tr.transition(int(d["ent"]), tk, d["to"], T, d.get("obj"))
            elif k == "hit" and d.get("dead") and isinstance(d.get("ent"), int) and d.get("ent") in tr.subjects:
                tr.kill(int(d["ent"]), T)
        for r in range(starts[i], starts[i + 1]):
            tki = int(cache["e_tk"][r])
            if haz_ok[tki]:
                iid = int(cache["e_iid"][r])
                box = cache["e_box"][r]
                st = int(cache["e_st"][r])
                armed = not math.isnan(float(box[0])) or (st >= 0 and states[st] not in rest)
                tk = types[tki]
                if tk in HAZARD_ALIASES:      # a shared name: the circle's radius from the box width (None: unknown)
                    if not math.isnan(float(box[0])):
                        w = 0.5 * float(box[2] - box[0])
                        alias[iid] = min(HAZARD_ALIASES[tk], key=lambda a: abs(a[0] - w))[1]
                    tk = alias.get(iid, tk)
                tr.hazard(iid, tk, T, cache["e_x"][r], cache["e_y"][r], armed, box,
                          (cache["e_vx"][r], cache["e_vy"][r]))
                continue
            if not tk_ok[tki]:
                continue
            st = int(cache["e_st"][r])
            tr.entity(int(cache["e_iid"][r]), types[tki], T, cache["e_x"][r], cache["e_y"][r], cache["e_vx"][r],
                      cache["e_vy"][r], int(cache["e_flip"][r]), bool(cache["e_hidden"][r]),
                      states[st] if st >= 0 else None, float(cache["e_tin"][r]), cache["e_box"][r])
        yield i, f, T


def _type_of(obj, specs) -> str | None:
    from ssbot.train.gauntlet import type_key
    tk = type_key(obj) if isinstance(obj, str) else None
    return tk if tk in specs else None
