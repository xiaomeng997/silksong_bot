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
HAZARD_GONE_S = 0.5          # an armed hazard missing from the export this long has left (behaviour_tables
#                              ABSENT_CLOSE_F: 30 frames)
DWELL_SLACK_S = BIN          # logged dwell ranges are frame-quantised: one bin of slack on each side


def margins_from_contacts(rows: list[dict], fold: int | None = None, q: float = 1.0) -> dict[tuple[str, str], float]:
    """Margins from held-out residuals (the q-quantile, 1.0 = max; a residual beyond the search radius counts as
    behaviour_tables.R_MARGIN_SEARCH_U); fold: only contacts of that fold (the calibration side; the certified side is
    the other):
      (type, family)  the enemy's own colliders: the per-state set ("state:<state>", the contact against the other
                      fold's per-state occupancy at its state and time)
      ("ent", hazard) a thrown hazard's contacts: its self template ("self:<hazard>", relative to where and when it
                      armed); the recall places it for every armed hazard (SubjectTracker.hazards), so a hazard
                      whose path the per-state templates cannot hold (a bell's bounces) does not widen the family"""
    from ssbot.knowledge.behaviour_tables import R_MARGIN_SEARCH_U
    per: dict[tuple, list] = defaultdict(list)
    for r in rows:
        if r.get("follow") or (fold is not None and r.get("fold") != fold):
            continue
        ho = r.get("ho") or {}
        own = r.get("tk") == r.get("type")
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
                 base: float = 0.0, specs=FORUM_SPECS):
        self.extra, self.fold, self.specs = Path(extra), fold, specs
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
                if len(parts) != 4:
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
    box: tuple | None = None                       # its enabled damage colliders' box on the last frame seen


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

    def hazard(self, iid: int, tk: str, T: float, x: float, y: float, armed: bool) -> None:
        """A thrown hazard's frame: an arming (armed now, not on its last frame) records where and when (its self
        template's origin, the gauntlet builder's EntitySeg.arm_T / arm_pos)."""
        h = self.hazards.get(iid)
        if h is None:
            h = self.hazards[iid] = [tk, False, T, (float(x), float(y)), T]
        if armed and (not h[1] or T - h[4] > 2.5 * FRAME_S):    # (re-)armed, or back in the export (pooled)
            h[0], h[2], h[3] = tk, T, (float(x), float(y))
        h[1], h[4] = armed, T

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
            if s.cur is not None and s.cur.anchor is None:
                s.cur.anchor, s.cur.mirror = s.pos, FACES_LEFT[s.flip]
        if s.state is None and state is not None:      # seen before any Control event: its exported state
            s.state, s.t_entry = state, T - (tin or 0.0)


class SubjectRecall:
    """Run the trackers over a fight's cache and test the contacts (see the module docstring)."""

    def __init__(self, tables: FoldTables, lags=(2, 3, 4), tube_speed: dict[str, float] | None = None,
                 tube_skin: float = 0.1):
        self.t = tables
        self.lags = tuple(lags)
        self.tube = tube_speed is not None
        self.tube_speed = dict(tube_speed or {})
        self.tube_skin = tube_skin
        self.stats: dict = defaultdict(Counter)
        self.misses: list[dict] = []
        self.placements = Counter()

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
            ctx = None
            if cur is not None:
                anc = ((cur.anchor[0], cur.anchor[1], cur.mirror),) if cur.anchor is not None else new
                ctx = (cur.family, cur.start, anc)
            e0 = s.t_entry - T_o
            self._walk(sp, w, s.state, e0, ctx, new, s.dead, H, out)
        return list(dict.fromkeys(out))

    def _walk(self, sp, w: Walk, state: str, e0: float, ctx, new, dead: bool, H: float, out: list) -> None:
        """The support walk as a worklist over (state, instance context, dead): each node keeps the hull of its
        entry intervals (a superset of every path's: conservative), entries past the horizon are dropped, so the
        decision chains' zero-dwell loops end."""
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
            if c is None:
                continue
            if st == TAIL:
                self._place(out, self.t.key(c[0], TAIL), lo, hi, c[2], H)
            else:
                self._place(out, self.t.key(c[0], st), lo, hi, c[2], H)
    def in_tube(self, s: Subject, pts: list[tuple[float, float, float]]) -> bool:
        """The enemy's damage colliders enabled now (its box on the origin frame) moved at most its type's top speed
        (tube_speed: measured on the training fold) by the query time: the current-collider tube. Only for the
        recall's lags (a few frames): dying and waiting bodies, a parked summon, a body thrown back by a clash."""
        if s.box is None:
            return False
        v = self.tube_speed.get(s.tk, 0.0)
        hx, hy = hb.HERO_HALF_U[0] + self.tube_skin, hb.HERO_HALF_U[1] + self.tube_skin
        b = s.box
        return any(b[0] - hx - v * tau <= x <= b[2] + hx + v * tau and b[1] - hy - v * tau <= y <= b[3] + hy + v * tau
                   for x, y, tau in pts)

    def covered(self, placements: list, pts: list[tuple[float, float, float]]) -> bool:
        q = self.t.query
        if q is None or not placements:
            return False
        q.clear()
        for key, t_ref, anchor, mirror in placements:
            q.place(key, t_ref, anchor, mirror)
        for x, y, tau in pts:
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
            pts.append((0.5 * (box[0] + box[2]), 0.5 * (box[1] + box[3]), float(T_arr[fi_of[fr]]) - T_o))
        how = None
        if s is not None and pts:
            # the gauntlet builder attributes a contact by the GameObject name (a waiting wave-12 "Song Reed" and the
            # wave-0 one share it): every subject of that name is a candidate, the attributed one first
            names = [s] + [o for o in tr.subjects.values() if o is not s and o.tk == s.tk and s.name
                           and o.name == s.name]
            for k, o in enumerate(names):
                pl = self.placements_of(o, T_o, H, hazards=thrown(tr, self.t.specs[o.tk]))
                self.placements["placements"] += len(pl)
                self.placements["forecasts"] += 1
                if self.covered(pl, pts):
                    how = "forecast" if k == 0 else "namesake forecast"
                    break
                if self.tube and self.in_tube(o, pts):
                    how = "current-collider tube" if k == 0 else "namesake tube"
                    break
        if how is not None:
            st["covered"] += 1
            if how != "forecast":
                st[f"covered by {how}"] += 1
            return
        self.misses.append({"fight": c["fight"], "f": cf, "lag": L, "type": c["type"], "family": c.get("family"),
                            "state": c.get("state"), "ts": c.get("ts"), "src": c.get("src"), "kind": c.get("kind"),
                            "subject_state": None if s is None else s.state,
                            "subject_family": None if s is None or s.cur is None else s.cur.family,
                            "ho": c.get("ho"), "label": label})


def top_speeds(caches, specs=FORUM_SPECS, jump_u: float = 2.0) -> dict[str, float]:
    """Per enemy type the largest speed (u per game s) of its transform between consecutive exported frames over the
    given fight caches (moves longer than jump_u in one frame are teleports or respawns and are left out): the
    current-collider tube's growth rate."""
    out: dict[str, float] = {}
    for c in caches:
        types = c["types"]
        order = np.lexsort((c["e_fi"], c["e_iid"]))
        iid, fi = c["e_iid"][order], c["e_fi"][order]
        x, y, tk = c["e_x"][order].astype(np.float64), c["e_y"][order].astype(np.float64), c["e_tk"][order]
        same = (iid[1:] == iid[:-1]) & (fi[1:] == fi[:-1] + 1)
        dt = np.diff(c["T"])[fi[:-1].clip(0, len(c["T"]) - 2)]
        d = np.hypot(np.diff(x), np.diff(y))
        ok = same & (dt > 1e-4) & (d <= jump_u)
        sp = np.zeros_like(d)
        sp[ok] = d[ok] / dt[ok]
        for k in np.unique(tk[:-1][ok]):
            t = types[int(k)]
            if t in specs:
                out[t] = max(out.get(t, 0.0), float(sp[ok & (tk[:-1] == k)].max()))
    return out


def thrown(tr: SubjectTracker, sp) -> list[tuple]:
    """(type, arm time, arm position) of the armed hazards of the types this enemy type throws."""
    if not sp.projectiles:
        return []
    return [(h[0], h[2], h[3]) for h in tr.hazards.values()
            if h[1] and tr.T - h[4] <= HAZARD_GONE_S and h[0].startswith(sp.projectiles)]


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
                if tk in HAZARD_ALIASES:      # a shared name: the circle's radius from the box width
                    if not math.isnan(float(box[0])):
                        w = 0.5 * float(box[2] - box[0])
                        alias[iid] = min(HAZARD_ALIASES[tk], key=lambda a: abs(a[0] - w))[1]
                    tk = alias.get(iid)
                if tk is not None:
                    tr.hazard(iid, tk, T, cache["e_x"][r], cache["e_y"][r], armed)
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
