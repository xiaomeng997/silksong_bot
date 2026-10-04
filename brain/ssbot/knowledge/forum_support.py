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
successors the training fold logged with entry intervals from its logged dwell range, the tail of an attack once it
can end (hazards outliving it), the tails of ended attacks for tail_max_s. Forum anchors vary (no Set L / Set R): an
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
from ssbot.knowledge.gauntlet_tables import FACES_LEFT, FORUM_SPECS

BIN = hb.BIN_S
FRAME_S = 1.0 / 60.0
TAIL = "_tail"
MAX_DEPTH = 12


def margins_from_contacts(rows: list[dict], fold: int | None = None, q: float = 1.0) -> dict[tuple[str, str], float]:
    """Per (type, family) margin from the held-out residuals of the per-state sets ("state:<state>": the contact
    against the other fold's per-state occupancy): the q-quantile (1.0 = max). fold: only contacts of that fold
    (the calibration side; the certified side is the other). A residual beyond the search radius counts as
    behaviour_tables.R_MARGIN_SEARCH_U."""
    from ssbot.knowledge.behaviour_tables import R_MARGIN_SEARCH_U
    per: dict[tuple, list] = defaultdict(list)
    for r in rows:
        if r.get("follow") or r.get("family") is None or (fold is not None and r.get("fold") != fold):
            continue
        st = r.get("state")
        if st is None:
            continue
        ho = r.get("ho") or {}
        k = f"state:{st}"
        if k not in ho:
            continue
        v = ho[k]
        per[(r["type"], r["family"])].append(R_MARGIN_SEARCH_U if v is None else float(v))
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
                if len(parts) != 4 or parts[3] != "anchor" or parts[2].startswith("ent"):
                    continue
                m = base + self.margins.get((tk, parts[1]), 0.0)
                tpls[k] = t.dilated(rx=hb.HERO_HALF_U[0] + m, ry=hb.HERO_HALF_U[1] + m, key=k)
        self.templates = tpls
        self.meta = {k: (t.t0, t.t1) for k, t in tpls.items()}
        self.query = hb.SupportQuery(tpls, hero_half=hb.HERO_HALF_U) if tpls else None

    def key(self, fam: str, state: str) -> str | None:
        k = f"{hb.SUPPORT}{fam}/{state}/anchor"
        return k if k in self.meta else None


@dataclass(slots=True)
class Inst:
    family: str
    start: str
    t_start: float
    anchor: tuple | None = None
    mirror: int = 1


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


class SubjectTracker:
    """Per enemy entity of a fight: Control state and entry, the attack instance with its anchor, ended attacks
    (the gauntlet builder's segmentation, FightScanner._control)."""

    def __init__(self, specs=FORUM_SPECS, tail_keep_s: float | None = None):
        self.specs = specs
        self.subjects: dict[int, Subject] = {}
        self.tail_keep_s = tail_keep_s

    def subject(self, iid: int, tk: str) -> Subject:
        s = self.subjects.get(iid)
        if s is None:
            s = self.subjects[iid] = Subject(iid, tk)
        return s

    def _end(self, s: Subject, T: float) -> None:
        c = s.cur
        if c is not None and c.anchor is not None:
            keep = self.tail_keep_s if self.tail_keep_s is not None else self.specs[s.tk].tail_max_s + 1.0
            s.ends = [e for e in s.ends if T - e[3] <= keep] + [(c.family, c.anchor, c.mirror, T)]
        s.cur = None

    def _start(self, s: Subject, fam: str, to: str, T: float) -> None:
        s.cur = Inst(fam, to, T)
        if not s.hidden and not math.isnan(s.pos[0]) and s.seen_T == T:
            s.cur.anchor, s.cur.mirror = s.pos, FACES_LEFT[s.flip]

    def transition(self, iid: int, tk: str, to: str, T: float) -> None:
        sp = self.specs[tk]
        s = self.subject(iid, tk)
        s.state, s.t_entry = to, T
        cur, idle = s.cur, sp.idle_family
        if to in sp.death_states:
            if cur is not None:
                self._end(s, T)
            s.dead = True
        elif to in sp.attack_starts and cur is not None and cur.family == sp.attack_starts[to] and to != cur.start:
            pass
        elif to in sp.attack_starts:
            if cur is not None:
                self._end(s, T)
            s.dead = False
            self._start(s, sp.attack_starts[to], to, T)
        elif to in sp.decision_states:
            if cur is not None and cur.family != idle:
                self._end(s, T)
            if idle is not None and not s.dead and s.cur is None:
                self._start(s, idle, to, T)

    def kill(self, iid: int, T: float) -> None:
        s = self.subjects.get(iid)
        if s is not None:
            if s.cur is not None:
                self._end(s, T)
            s.dead = True

    def entity(self, iid: int, tk: str, T: float, x: float, y: float, vx: float, vy: float, flip: int,
               hidden: bool, state: str | None = None, tin: float | None = None) -> None:
        s = self.subject(iid, tk)
        s.hidden = hidden
        if not hidden:
            s.pos, s.vel, s.flip, s.seen_T = (float(x), float(y)), (float(vx), float(vy)), int(flip), T
            if s.cur is not None and s.cur.anchor is None:
                s.cur.anchor, s.cur.mirror = s.pos, FACES_LEFT[s.flip]
        if s.state is None and state is not None:      # seen before any Control event: its exported state
            s.state, s.t_entry = state, T - (tin or 0.0)


class SubjectRecall:
    """Run the trackers over a fight's cache and test the contacts (see the module docstring)."""

    def __init__(self, tables: FoldTables, lags=(2, 3, 4)):
        self.t = tables
        self.lags = tuple(lags)
        self.stats: dict = defaultdict(Counter)
        self.misses: list[dict] = []
        self.placements = Counter()

    # ---- the walk ----

    def _place(self, out: list, key: str | None, e_lo: float, e_hi: float, anchors, H: float) -> None:
        if key is None:
            return
        t0, t1 = self.t.meta[key]
        n = int(math.floor((e_hi - e_lo) / BIN + 1e-6)) + 1
        es = [e_lo + i * BIN for i in range(n)]
        if es[-1] < e_hi - 1e-3:
            es.append(e_hi)
        for e in es:
            on, off = e + t0, e + t1
            if off < -BIN or on > H + BIN:
                continue
            for ax, ay, m in anchors:
                out.append((key, -e, (ax, ay), m))

    def placements_of(self, s: Subject, T_o: float, H: float) -> list[tuple]:
        """SupportQuery placements (key, t_ref, anchor, mirror) of one subject at origin T_o."""
        sp = self.t.specs[s.tk]
        w = self.t.walk.get(s.tk)
        out: list = []
        for fam, anc, mir, t_end in s.ends:
            e = t_end - T_o
            self._place(out, self.t.key(fam, TAIL), e, e, [(anc[0], anc[1], mir)], H)
        if w is None or s.state is None or s.t_entry is None:
            return out
        k_max = int(math.ceil(H / FRAME_S))
        x, y = s.pos
        if math.isnan(x):
            new = []
        else:
            vx, vy = s.vel
            pts = {(round(x + vx * k * FRAME_S, 4), round(y + vy * k * FRAME_S, 4)) for k in range(k_max + 1)}
            new = [(px, py, m) for px, py in sorted(pts) for m in (-1, 1)]
        cur = s.cur
        ctx = None
        if cur is not None:
            anc = [(cur.anchor[0], cur.anchor[1], cur.mirror)] if cur.anchor is not None else new
            ctx = (cur.family, cur.start, anc)
        e0 = s.t_entry - T_o
        self._walk(sp, w, s.state, e0, e0, ctx, new, s.dead, True, 0, H, out)
        return out

    def _walk(self, sp, w: Walk, state: str, e_lo: float, e_hi: float, ctx, new, dead: bool, current: bool,
              depth: int, H: float, out: list) -> None:
        if e_lo > H:
            return
        if depth > MAX_DEPTH:
            self.placements["truncated walks"] += 1
            return
        fam = ctx[0] if ctx else None
        if fam is not None:
            self._place(out, self.t.key(fam, state), e_lo, e_hi, ctx[2], H)
        dw = w.dwell.get(state)
        if dw is None:
            return
        x_lo, x_hi = e_lo + dw[0], e_hi + dw[1]
        if current:
            x_lo, x_hi = max(x_lo, BIN), max(x_hi, BIN)
        if x_lo > H:
            return
        idle = sp.idle_family
        for nxt in w.succ.get(state, ()):
            if nxt in sp.death_states:
                continue
            c2, d2 = ctx, dead
            if nxt in sp.attack_starts:
                nf = sp.attack_starts[nxt]
                if not (ctx is not None and ctx[0] == nf and nxt != ctx[1]):
                    if fam is not None and fam != idle:
                        self._place(out, self.t.key(fam, TAIL), x_lo, x_hi, ctx[2], H)
                    c2, d2 = (nf, nxt, new), False
            elif nxt in sp.decision_states:
                if fam is not None and fam != idle:
                    self._place(out, self.t.key(fam, TAIL), x_lo, x_hi, ctx[2], H)
                    c2 = (idle, nxt, new) if idle and not dead else None
                elif fam is None and idle and not dead:
                    c2 = (idle, nxt, new)
            self._walk(sp, w, nxt, x_lo, x_hi, c2, new, d2, False, depth + 1, H, out)

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
        types, states = cache["types"], cache["states"]
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
        evs: dict[int, list] = defaultdict(list)
        for f, k, d in cache["events"]:
            if k in ("fsm", "hit"):
                evs[int(f)].append((k, d))
        tr = SubjectTracker(specs)
        e_fi = cache["e_fi"]
        starts = np.searchsorted(e_fi, np.arange(len(f_arr) + 1))
        tk_ok = np.array([t in specs for t in types], bool)
        H = (max(self.lags) + 1) * FRAME_S + 1e-6
        for i, f in enumerate(f_arr):
            f = int(f)
            T = float(T_arr[i])
            for k, d in evs.get(f, ()):
                if k == "fsm":
                    tk = _type_of(d.get("obj"), specs)
                    if tk is not None and d.get("fsm") == specs[tk].control_fsm and isinstance(d.get("to"), str) \
                            and isinstance(d.get("ent"), int):
                        tr.transition(int(d["ent"]), tk, d["to"], T)
                elif k == "hit" and d.get("dead") and isinstance(d.get("ent"), int) and d.get("ent") in tr.subjects:
                    tr.kill(int(d["ent"]), T)
            for r in range(starts[i], starts[i + 1]):
                tki = int(cache["e_tk"][r])
                if not tk_ok[tki]:
                    continue
                st = int(cache["e_st"][r])
                tr.entity(int(cache["e_iid"][r]), types[tki], T, cache["e_x"][r], cache["e_y"][r], cache["e_vx"][r],
                          cache["e_vy"][r], int(cache["e_flip"][r]), bool(cache["e_hidden"][r]),
                          states[st] if st >= 0 else None, float(cache["e_tin"][r]))
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
        ok = False
        if s is not None and pts:
            pl = self.placements_of(s, T_o, H)
            self.placements["placements"] += len(pl)
            self.placements["forecasts"] += 1
            ok = self.covered(pl, pts)
        if ok:
            st["covered"] += 1
            return
        self.misses.append({"fight": c["fight"], "f": cf, "lag": L, "type": c["type"], "family": c.get("family"),
                            "state": c.get("state"), "ts": c.get("ts"), "src": c.get("src"), "kind": c.get("kind"),
                            "subject_state": None if s is None else s.state,
                            "subject_family": None if s is None or s.cur is None else s.cur.family,
                            "ho": c.get("ho"), "label": label})


def _type_of(obj, specs) -> str | None:
    from ssbot.train.gauntlet import type_key
    tk = type_key(obj) if isinstance(obj, str) else None
    return tk if tk in specs else None
