"""Offline Forum data products of round R0 (docs/plans/forum_planner_plan.md §5 R0 and the person's answers of
2026-10-03 evening, docs/plans/M2.md "Forum 打法问答"), from the per-fight caches (ssbot.knowledge.forum_cache):

    acc = Products()
    for cache in caches:
        acc.add(FightView(cache))
    out = acc.result()           # JSON-able; ssbot.tools.forum_products writes knowledge/.../forum/<product>.json

Every product is an accumulator with add(view) and result(); FightView segments the enemies' attack instances the way
the gauntlet builder does (forum_support.SubjectTracker on the Control FSM events) and indexes each entity's rows.

  chains         multi-hit chains per damage source: hits and damage of the whole chain (the first "damage" event,
                 the hornet_multi_wounder follow-ups ("special_damage" from the Multihit FSM) and LethalBlock-blocked
                 hits ("catastrophe", data mode keeps the hero at 1 mask) on distinct frames within MW_CHAIN_F)
  death_tails    after a kill: how long the enemy still exports an enabled damage collider, hero contacts then
  kill_freeze    the freeze events a kill starts (type, the FreezeMoment parameters, the real-time length)
  strikes        per attack family: time from the commit (the attack-start state) to its first enabled attack collider
                 (not the body: STRIKE_BODY) or owned hazard, the hero's distance then, and its reach (the attack
                 colliders' extent in the facing frame); per type the fastest family ("idle to the fastest strike")
  punish         per committed attack: startup (commit to the first attack collider), active span, recovery (last
                 attack collider off to the attack's end), the share of instances where a full hero attack
                 (HERO_ATTACK_S) fits in the startup or the recovery, and the body contact during the attack
  quiet          inter-wave quiet stretches: no armed enemy (out of its waiting states) and no enabled hazard; their
                 length against the Bind's need (BIND_NEED_S)
  garmond        Garmond's target choice: at each of his attack starts the enemy he then hits first, against the
                 nearest enemy to him, the one with the most HP, the nearest to the hero (allies export)
  stances        defensive stances (Minister parry, Reed defend, Maestro / Tiny defend): hits taken in the stance, the
                 counter's states, delay, length, reach and parry bits (clash bit 1: clashable)
  below          flying enemies: share of their attack instances whose own colliders touch a hero standing on the floor
                 directly below the commit point, against one standing diagonally (BELOW_DX)
  clawmaiden     the Clawmaiden's distance to the hero while it flies between attacks, against a dash stab's reach
  bells          Throwing Bell: parry bits, nail hits (Tink states), pogo off a bell (hero bounce after a down slash)
  boundaries     per attack family the hero distance when it was chosen, its trigger boundary (max) and how many
                 decisions were sampled within BOUNDARY_U of it (chosen / not chosen)
"""
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from ssbot.knowledge.forum_support import SubjectTracker, replay
from ssbot.knowledge.gauntlet_tables import FORUM_SPECS, HAZARD_ALIASES
from ssbot.train.gauntlet import type_key as go_type

REPO = Path(__file__).resolve().parents[3]
MW_CHAIN_F = 90                 # a multi-hit's follow-ups land within this many frames of the hit before
# the multi-hit attacks (hornet_multi_wounder): their follow-up hits come as "damage" events of the same attack, the
# collider's trailing number stripped (Choristor Whip Hit 1-6, Reed ParrySlash Hit, Minister Slash Collider)
MULTI_HIT = frozenset(("Whip Hit", "ParrySlash Hit", "Slash Collider"))
TAIL_LOOK_S = 6.0
BIND_NEED_S = 1.37 + 0.15       # DESIGN §3.5.6: T_bind + delta_b (no Injector Band)
BELOW_DX = (0.0, 3.0, 6.0)      # hero x offsets from the commit point tested by "below"
FLOOR_Y = (3.015, 5.094)        # the hero's physics box standing on the Forum floor (STATE hero.box)
HERO_HALF_W = 0.25
BOUNDARY_U = 1.0
GARMOND = "Garmond Fighter"
GARMOND_SRCS = ("WildSlash Enemy Damager", "Stomp Damager", "Stomp Splash Damager", "Charge Damager")
GARMOND_ATTACKS = ("Wildslash", "Charge", "Stomp", "Jump", "Hop", "Chase Target")
STANCE_FAMILIES = {"MI_PARRY": "Song Administrator", "RE_DEFEND": "Song Reed", "MA_DEFEND": "Song Pilgrim Maestro",
                   "AT_DEFEND": "Song Automaton Tiny"}
FLIERS = ("Song Handmaiden", "Song Administrator", "Song Pilgrim Maestro", "Song Automaton Tiny", "Song Reed",
          "Pilgrim 03 Song")
BELL = "Throwing Bell"


def reaper_timing() -> dict:
    """The Reaper crest's attack timing and the dash stab (knowledge/1.0.30000/attacks/reaper.json, kinematics)."""
    d = json.loads((REPO / "knowledge" / "1.0.30000" / "attacks" / "reaper.json").read_text("utf-8"))
    k = json.loads((REPO / "knowledge" / "1.0.30000" / "kinematics" / "hero_reaper_forum.json").read_text("utf-8"))
    cfg = d["config"]
    side = max(p[0] for poly in d["shapes"]["normal"]["polys"] for p in poly)
    stab = max(p[0] for poly in d["shapes"]["dash_stab"]["polys"] for p in poly)

    def find(o, key):
        if isinstance(o, dict):
            if key in o:
                return o[key]
            for v in o.values():
                r = find(v, key)
                if r is not None:
                    return r
        return None
    dash = float(find(k, "dash_speed") or 28.0) * float(find(k, "dash_time") or 0.1)
    return {"attack_s": float(cfg["duration"]), "cooldown_s": float(cfg["cooldown"]),
            "recovery_s": float(cfg["recovery"]), "side_reach_u": round(side, 3), "dash_stab_reach_u": round(stab, 3),
            "dash_u": round(dash, 3), "dash_stab_total_u": round(dash + stab, 3)}


HERO = reaper_timing()
HERO_ATTACK_S = HERO["attack_s"]


def body_collider(tk: str, name: str | None) -> bool:
    """The enemy's body (contact damage while it moves): its root collider (the GameObject's own name), the
    Choristor's Body Damager, the Minister's "Colliders/Collider ..." boxes."""
    if not name:
        return True
    n = name.replace("(Clone)", "").strip()
    return go_type(n) == tk or n == "Body Damager" or n.startswith("Collider ")


def _q(v, qs=(0.0, 0.05, 0.5, 0.95, 1.0), nd: int = 3) -> dict:
    if not len(v):
        return {"n": 0}
    a = np.asarray(v, np.float64)
    return {"n": int(a.size), **{f"p{int(q * 100)}" if q not in (0.0, 1.0) else ("min" if q == 0.0 else "max"):
                                 round(float(np.quantile(a, q)), nd) for q in qs}}


def source_type(src: str) -> tuple[str | None, str]:
    """(enemy type, collider name) of a damage event's source path."""
    parts = [p for p in str(src).split("/") if p]
    leaf = parts[-1].replace("(Clone)", "").strip() if parts else ""
    for p in reversed(parts):
        t = go_type(p)
        if t in FORUM_SPECS:
            return t, leaf
    for p in parts:
        base = p.replace("(Clone)", "").strip()
        for tk, sp in FORUM_SPECS.items():
            if any(base.startswith(x) for x in sp.projectiles):
                return tk, base if leaf in ("damager", "") else leaf
    if parts and parts[0] == "Colliders":
        return "Song Administrator", leaf
    alias = {n: r for r, n in HAZARD_ALIASES.get("damager", ())}
    for p in parts:
        base = p.replace("(Clone)", "").strip()
        if base in alias:
            for tk, sp in FORUM_SPECS.items():
                if any(base.startswith(x) for x in sp.projectiles):
                    return tk, base
    return None, leaf


class FightView:
    """A cache with per-entity rows and the enemies' attack instances."""

    def __init__(self, cache: dict, specs=FORUM_SPECS):
        self.c = c = cache
        self.specs = specs
        self.f = c["f"]
        self.T = c["T"]
        self.fi_of = {int(f): i for i, f in enumerate(self.f)}
        self.types, self.states, self.names = c["types"], c["states"], c["names"]
        self.starts = np.searchsorted(c["e_fi"], np.arange(len(self.f) + 1))
        order = np.argsort(c["e_iid"], kind="stable")
        iids, first = np.unique(c["e_iid"][order], return_index=True)
        bounds = list(first) + [len(order)]
        self.rows = {int(i): order[bounds[k]:bounds[k + 1]] for k, i in enumerate(iids)}
        self.tk_of = {int(c["e_iid"][r[0]]): self.types[int(c["e_tk"][r[0]])] for r in self.rows.values()}
        cs = np.argsort(c["c_ei"], kind="stable")
        eis, cf = np.unique(c["c_ei"][cs], return_index=True)
        cb = list(cf) + [len(cs)]
        self.cols = {int(e): cs[cb[k]:cb[k + 1]] for k, e in enumerate(eis)}
        self.events = c["events"]
        self.instances = []
        tr = SubjectTracker(specs, log=self.instances)
        for _ in replay(c, tr, specs):
            pass
        self.tracker = tr
        self.hazards = self._own_hazards()

    def _own_hazards(self) -> dict[int, list]:
        """id(instance) -> [(frame index, name, box, parry)] of the hazards it threw (Throwing Bell, Reed's pin, the
        Clawmaiden's spear and blast, the Clapper's bombs and rune): each armed stretch of a hazard entity goes to the
        instance of a spawning type in a family that spawns it (or ended one within spawn_window_s), else any of that
        type in an attack, nearest first (the gauntlet builder's rule, GauntletBuilder._pick_owner, simplified)."""
        c = self.c
        out: dict[int, list] = defaultdict(list)
        by_type: dict[str, list] = defaultdict(list)
        for inst in self.instances:
            by_type[inst.tk].append(inst)
        owners = {}
        for tk, sp in self.specs.items():
            for p in sp.projectiles:
                owners.setdefault(p, []).append(tk)
        for iid, rs in self.rows.items():
            name = self.tk_of.get(iid)
            if name in self.specs:
                continue
            aliases = HAZARD_ALIASES.get(name or "")
            if not aliases and not any(name and name.startswith(p) for p in owners):
                continue
            armed = ~np.isnan(c["e_box"][rs, 0])
            prev_fi, owner = -10, None
            for r, a in zip(rs, armed):
                fi = int(c["e_fi"][r])
                if not a:
                    prev_fi = -10
                    continue
                if fi - prev_fi > 2:          # a new armed stretch
                    nm = name
                    if aliases:               # a shared name ("damager"): the circle's radius from its box width
                        w = 0.5 * float(c["e_box"][r, 2] - c["e_box"][r, 0])
                        nm = min(aliases, key=lambda a_: abs(a_[0] - w))[1]
                    ots = [t for p, ts in owners.items() if nm.startswith(p) for t in ts]
                    owner = self._pick(fi, nm, ots, float(c["e_x"][r]), float(c["e_y"][r])) if ots else None
                prev_fi = fi
                if owner is not None:
                    for nm, box, par, _ in self.colliders(int(r)):
                        out[id(owner)].append((fi, nm or name, box, par))
        return out

    def _pick(self, fi: int, name: str, types: list[str], hx: float, hy: float):
        f = int(self.f[fi])
        T = float(self.T[fi])
        best = None
        for tk in types:
            sp = self.specs[tk]
            fams = next((fs for p, fs in sp.spawns if name.startswith(p)), ())
            for inst in self.instances:
                if inst.tk != tk or inst.f_start > f:
                    continue
                live = inst.f_end is None or inst.f_end >= f
                late = not live and inst.family in fams and inst.t_end is not None and T - inst.t_end <=                     sp.spawn_window_s
                if not (live or late):
                    continue
                r = self.row_at(inst.iid, fi)
                d = math.inf if r is None else math.hypot(float(self.c["e_x"][r]) - hx, float(self.c["e_y"][r]) - hy)
                key = (inst.family not in fams, inst.family == sp.idle_family, not live, d, -inst.f_start)
                if best is None or key < best[0]:
                    best = (key, inst)
        return None if best is None else best[1]

    def row_at(self, iid: int, fi: int) -> int | None:
        rs = self.rows.get(iid)
        if rs is None:
            return None
        k = int(np.searchsorted(self.c["e_fi"][rs], fi))
        return int(rs[k]) if k < len(rs) and int(self.c["e_fi"][rs[k]]) == fi else None

    def rows_between(self, iid: int, fi0: int, fi1: int) -> np.ndarray:
        rs = self.rows.get(iid)
        if rs is None:
            return np.zeros(0, np.int64)
        e = self.c["e_fi"][rs]
        return rs[np.searchsorted(e, fi0):np.searchsorted(e, fi1, side="right")]

    def colliders(self, r: int) -> list[tuple[str, tuple, int, int]]:
        """(name, box, parry, dealt) of entity row r's enabled damage colliders."""
        c = self.c
        out = []
        for j in self.cols.get(r, ()):
            n = int(c["c_name"][j])
            out.append((self.names[n] if n >= 0 else None, tuple(float(v) for v in c["c_box"][j]),
                        int(c["c_parry"][j]), int(c["c_dealt"][j])))
        return out

    def alive_enemies(self, fi: int) -> list[int]:
        """Rows of frame fi: enemies of the specs out of their waiting states, not hidden."""
        c = self.c
        out = []
        for r in range(self.starts[fi], self.starts[fi + 1]):
            tk = self.types[int(c["e_tk"][r])]
            sp = self.specs.get(tk)
            if sp is None or c["e_hidden"][r]:
                continue
            st = int(c["e_st"][r])
            s = self.states[st] if st >= 0 else None
            if s is None or s in sp.dormant or s in sp.rest_states and s != "Idle" or c["e_hp"][r] <= 0:
                continue
            out.append(r)
        return out


# ---- products ---------------------------------------------------------------------------------------------------

class Chains:
    def __init__(self):
        self.rows: dict[tuple, list] = defaultdict(list)     # (type, collider) -> [(hits, damage, frames)]

    def add(self, v: FightView) -> None:
        cur = None
        blocked = {int(f) for f, k, d in v.events if k == "catastrophe" and d.get("blocked")}

        def close():
            if cur is not None:
                hits = len(cur["frames"])
                self.rows[(cur["type"], cur["src"])].append((hits, sum(cur["frames"].values()),
                                                              max(cur["frames"]) - min(cur["frames"]), cur["mw"],
                                                              cur["first_blocked"]))
        for f, k, d in sorted(v.events, key=lambda e: e[0]):
            if k == "damage":
                tk, leaf = source_type(d.get("source"))
                if tk is not None and go_type(leaf) == tk:
                    leaf = "body"
                who = str(d.get("source")).rsplit("/", 1)[0]
                base = re.sub(r"\s*\d+$", "", leaf)
                if cur is not None and base in MULTI_HIT and cur["base"] == base and cur["who"] == who \
                        and f - cur["last"] <= MW_CHAIN_F:
                    cur["frames"][int(f)] = max(cur["frames"].get(int(f), 0), int(d.get("amount") or 1))
                    cur["last"], cur["mw"] = int(f), True
                    continue
                close()
                # LethalBlock (data mode) blocks a hit at 1 mask: a multi-hit whose first hit is blocked never chains
                cur = {"type": tk or "?", "src": base if base in MULTI_HIT else leaf, "base": base, "who": who,
                       "frames": {int(f): int(d.get("amount") or 1)}, "last": int(f), "mw": False,
                       "first_blocked": any(int(f) + g in blocked for g in (-1, 0, 1))}
            elif k == "special_damage" and "Multihit" in str(d.get("fsm")) and cur is not None \
                    and f - cur["last"] <= MW_CHAIN_F:
                cur["frames"][int(f)] = max(cur["frames"].get(int(f), 0), int(d.get("amount") or 1))
                cur["last"], cur["mw"] = int(f), True
            elif k == "catastrophe" and d.get("blocked") and cur is not None and f - cur["last"] <= MW_CHAIN_F \
                    and not any(abs(int(f) - g) <= 1 for g in cur["frames"]):
                cur["frames"][int(f)] = int(d.get("amount") or d.get("dmg") or 1)
                cur["last"] = int(f)
        close()

    def result(self) -> dict:
        out = {}
        for (tk, src), rows in sorted(self.rows.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])):
            a = np.array([x[:3] for x in rows], np.float64)
            out[f"{tk}/{src}"] = {
                "n": len(rows), "first_hit_blocked": sum(1 for x in rows if x[4]),
                "multi_hit_chains": sum(1 for x in rows if x[3] or x[0] > 1), "hits_max": int(a[:, 0].max()),
                "damage_max": int(a[:, 1].max()), "hits": dict(Counter(int(x) for x in a[:, 0])),
                "damage": dict(Counter(int(x) for x in a[:, 1])), "span_frames_max": int(a[:, 2].max())}
        return {"note": "a chain: a source's damage event, then within " f"{MW_CHAIN_F}" " frames of the last hit the same "
                        "attack's further damage events, the Multihit follow-ups (special_damage) and the hits "
                        "LethalBlock blocked (catastrophe: data mode keeps the hero at 1 mask; the hit happened, its "
                        "damage is counted). A chain whose first hit was blocked tends not to continue (first_hit_"
                        "blocked), so the maxima are lower bounds of what an unblocked chain deals", "by_source": out}


class DeathTails:
    """The export drops a killed enemy on its kill frame (it leaves the HealthManager list), but its body and colliders
    can still hurt: per kill the hero contacts ("damage", each frame of "damage_blocked") whose source names the
    killed enemy's GameObject, up to TAIL_LOOK_S after the kill."""

    def __init__(self):
        self.kills: Counter = Counter()
        self.delays: dict[str, list] = defaultdict(list)       # type -> delay of the last post-kill contact (s)
        self.frames: dict[str, list] = defaultdict(list)
        self.n: Counter = Counter()

    def add(self, v: FightView) -> None:
        names = {}
        for f, k, d in v.events:
            if k == "fsm" and isinstance(d.get("ent"), int) and isinstance(d.get("obj"), str):
                names.setdefault(int(d["ent"]), d["obj"])
        contacts = []
        for f, k, d in v.events:
            if k == "damage":
                contacts.append((int(f), str(d.get("source"))))
            elif k == "damage_blocked" and isinstance(d.get("first_f"), int) and isinstance(d.get("last_f"), int):
                contacts += [(g, str(d.get("source"))) for g in range(d["first_f"], d["last_f"] + 1)]
        contacts.sort()
        cf = np.array([c[0] for c in contacts], np.int64)
        for f, k, d in v.events:
            if k != "hit" or not d.get("dead") or not isinstance(d.get("ent"), int):
                continue
            tk, name = d.get("type_key"), names.get(int(d["ent"]))
            if tk not in v.specs or not name or int(f) not in v.fi_of:
                continue
            self.kills[tk] += 1
            T0 = float(v.T[v.fi_of[int(f)]])
            last = None
            for j in range(int(np.searchsorted(cf, int(f))), len(contacts)):
                g, src = contacts[j]
                if g not in v.fi_of or float(v.T[v.fi_of[g]]) - T0 > TAIL_LOOK_S:
                    break
                if name in src.split("/"):
                    last = g
                    self.n[tk] += 1
            if last is not None:
                self.delays[tk].append(float(v.T[v.fi_of[last]]) - T0)
                self.frames[tk].append(last - int(f))

    def result(self) -> dict:
        return {"note": "contacts naming the killed enemy after its kill frame (the export no longer has it)",
                "by_type": {tk: {"kills": n, "kills_with_contacts_after": len(self.delays[tk]),
                                 "contact_frames_after": self.n[tk], "last_contact_s": _q(self.delays[tk]),
                                 "last_contact_frames": _q(self.frames[tk], nd=0)}
                            for tk, n in sorted(self.kills.items())}}


class KillFreeze:
    def __init__(self):
        self.rows: dict[str, Counter] = defaultdict(Counter)
        self.real: dict[str, list] = defaultdict(list)
        self.none: Counter = Counter()

    def add(self, v: FightView) -> None:
        starts = defaultdict(list)
        ends = {}
        for f, k, d in v.events:
            if k == "freeze":
                if d.get("phase") == "start":
                    starts[int(f)].append(d)
                elif d.get("phase") in ("end", "stop", "done") and d.get("id") is not None:
                    ends[d["id"]] = int(f)
        for f, k, d in v.events:
            if k != "hit" or not d.get("dead"):
                continue
            tk = d.get("type_key") or "?"
            fz = [x for g in (int(f), int(f) + 1) for x in starts.get(g, ())]
            if not fz:
                self.none[tk] += 1
                continue
            for x in fz:
                key = f"{x.get('type')} down {x.get('down')} wait {round(float(x.get('wait') or 0), 3)} up " \
                      f"{x.get('up')} speed {x.get('speed')}"
                self.rows[tk][key] += 1
                if x.get("id") in ends:
                    i0, i1 = v.fi_of.get(int(f)), v.fi_of.get(ends[x["id"]])
                    if i0 is not None and i1 is not None:
                        self.real[f"{tk}|{x.get('type')}"].append(ends[x["id"]] - int(f))

    def result(self) -> dict:
        return {"by_type": {tk: dict(c.most_common()) for tk, c in sorted(self.rows.items())},
                "kills_without_freeze": dict(self.none),
                "frames_to_end": {k: _q(v, nd=1) for k, v in sorted(self.real.items())}}


def _attack_cols(v: FightView, inst, fi0: int, fi1: int, hazards: bool = True) -> list[tuple[int, str, tuple, int]]:
    """(frame index, name, box, parry) of the instance's own attack colliders (not the body) in [fi0, fi1], and of
    the hazards it threw (FightView.hazards), in frame order."""
    out = []
    for r in v.rows_between(inst.iid, fi0, fi1):
        for name, box, par, _ in v.colliders(int(r)):
            if not body_collider(inst.tk, name):
                out.append((int(v.c["e_fi"][r]), name, box, par))
    if hazards:
        out += [x for x in v.hazards.get(id(inst), ()) if fi0 <= x[0] <= fi1]
        out.sort(key=lambda x: x[0])
    return out


def _facing_box(box: tuple, ax: float, ay: float, mirror: int) -> tuple:
    x0, x1 = mirror * (box[0] - ax), mirror * (box[2] - ax)
    return (min(x0, x1), box[1] - ay, max(x0, x1), box[3] - ay)


class Strikes:
    """Strike timing, reach and punish windows of every attack instance (strikes + punish products)."""

    def __init__(self):
        self.ttd: dict[str, list] = defaultdict(list)
        self.dist: dict[str, list] = defaultdict(list)
        self.reach: dict[str, list] = defaultdict(list)
        self.win: dict[str, list] = defaultdict(list)   # (startup, active, recovery, dur, body contact frames)
        self.none: Counter = Counter()

    def add(self, v: FightView) -> None:
        c = v.c
        for inst in v.instances:
            sp = v.specs[inst.tk]
            if inst.family == sp.idle_family or inst.family.endswith("_ENTRY") or inst.t_end is None \
                    or inst.anchor is None:
                continue
            fi0, fi1 = v.fi_of.get(inst.f_start), v.fi_of.get(inst.f_end)
            if fi0 is None or fi1 is None:
                continue
            own = _attack_cols(v, inst, fi0, fi1, hazards=False)
            # its hazards may arm after it ended (a Clawmaiden's spear, the Clapper's rune): up to spawn_window_s
            fi2 = int(np.searchsorted(v.T, float(v.T[fi1]) + sp.spawn_window_s))
            haz = [x for x in v.hazards.get(id(inst), ()) if fi0 <= x[0] <= fi2]
            cols = sorted(own + haz, key=lambda x: x[0])
            key = f"{inst.tk}/{inst.family}"
            hx, hy = float(c["hx"][fi0]), float(c["hy"][fi0])
            self.dist[key].append((abs(hx - inst.anchor[0]), hy - inst.anchor[1]))
            dur = inst.t_end - inst.t_start
            if not cols:
                self.none[key] += 1
                self.win[key].append((None, None, None, dur))
                continue
            t_on = [float(v.T[fi]) - inst.t_start for fi, *_ in cols]
            self.ttd[key].append(min(t_on))
            for fi, name, box, par in own:      # the reach of its own colliders (hazards fly on)
                self.reach[key].append(_facing_box(box, inst.anchor[0], inst.anchor[1], inst.mirror))
            if own:
                t_own = [float(v.T[fi]) - inst.t_start for fi, *_ in own]
                start, last = min(t_own), max(t_own)
                self.win[key].append((start, last - start, max(0.0, dur - last), dur))
            else:
                self.win[key].append((None, None, None, dur))

    def result(self) -> dict:
        strikes, punish = {}, {}
        fastest: dict[str, tuple] = {}
        for key in sorted(set(self.ttd) | set(self.none)):
            tk = key.split("/")[0]
            d = np.array(self.dist.get(key) or [(math.nan, math.nan)])
            rb = np.array(self.reach.get(key) or [(math.nan,) * 4])
            ttd = self.ttd.get(key, [])
            strikes[key] = {
                "instances_with_attack_colliders": len(ttd), "instances_without": self.none.get(key, 0),
                "commit_to_first_attack_collider_s": _q(ttd),
                "hero_dx_at_commit_u": _q(d[:, 0]), "hero_dy_at_commit_u": _q(d[:, 1]),
                "reach_facing_frame_u": {"x_min": round(float(np.nanmin(rb[:, 0])), 2),
                                         "x_max": round(float(np.nanmax(rb[:, 2])), 2),
                                         "y_min": round(float(np.nanmin(rb[:, 1])), 2),
                                         "y_max": round(float(np.nanmax(rb[:, 3])), 2),
                                         "x_max_p99": round(float(np.nanquantile(rb[:, 2], 0.99)), 2)}}
            if ttd and (tk not in fastest or min(ttd) < fastest[tk][1]):
                fastest[tk] = (key.split("/")[1], round(min(ttd), 3))
            w = [x for x in self.win.get(key, []) if x[0] is not None]
            if w:
                a = np.array(w, np.float64)
                punish[key] = {"n": len(w), "startup_s": _q(a[:, 0]), "active_s": _q(a[:, 1]),
                               "recovery_s": _q(a[:, 2]), "duration_s": _q(a[:, 3]),
                               "share_attack_fits_startup": round(float((a[:, 0] >= HERO_ATTACK_S).mean()), 3),
                               "share_attack_fits_recovery": round(float((a[:, 2] >= HERO_ATTACK_S).mean()), 3)}
        return {"hero": HERO, "strikes": strikes, "fastest_by_type": {k: {"family": f, "min_s": t}
                                                                      for k, (f, t) in sorted(fastest.items())},
                "punish": punish}


class Quiet:
    def __init__(self):
        self.gaps: list[dict] = []

    def add(self, v: FightView) -> None:
        c = v.c
        busy = np.zeros(len(v.f), bool)
        for i in range(len(v.f)):
            for r in range(v.starts[i], v.starts[i + 1]):
                tk = v.types[int(c["e_tk"][r])]
                if tk in v.specs:
                    if r in v.alive_enemies_cache(i):
                        busy[i] = True
                        break
                elif not math.isnan(float(c["e_box"][r, 0])):
                    busy[i] = True
                    break
        kills = sorted(int(f) for f, k, d in v.events if k == "hit" and d.get("dead")
                       and d.get("type_key") in v.specs and d.get("type_key") != "Song Automaton Tiny")
        i = 0
        n = len(busy)
        k_idx = 0
        while i < n:
            if busy[i]:
                i += 1
                continue
            j = i
            while j < n and not busy[j]:
                j += 1
            if 0 < i and j < n:
                dur = float(v.T[j] - v.T[i])
                f_i = int(v.f[i])
                while k_idx < len(kills) and kills[k_idx] <= f_i:
                    k_idx += 1
                nxt = sorted({v.types[int(c["e_tk"][r])] for r in range(v.starts[j], v.starts[j + 1])
                              if v.types[int(c["e_tk"][r])] in v.specs and r in v.alive_enemies_cache(j)})
                if dur >= 0.25:
                    self.gaps.append({"fight": v.c["meta"].get("id"), "f": f_i, "dur_s": round(dur, 3),
                                      "kills_before": k_idx, "next": nxt})
            i = j

    def result(self) -> dict:
        by_next: dict[str, list] = defaultdict(list)
        for g in self.gaps:
            by_next["+".join(g["next"]) or "-"].append(g["dur_s"])
        d = [g["dur_s"] for g in self.gaps]
        return {"bind_need_s": BIND_NEED_S, "gaps": len(d), "dur_s": _q(d),
                "share_bind_fits": round(float(np.mean(np.array(d) >= BIND_NEED_S)), 3) if d else None,
                "by_next_enemies": {k: {**_q(v), "share_bind_fits": round(float(np.mean(np.array(v) >= BIND_NEED_S)),
                                                                            3)}
                                    for k, v in sorted(by_next.items(), key=lambda kv: -len(kv[1]))}}


class Garmond:
    def __init__(self):
        self.n = Counter()
        self.fights_with_allies = 0

    def add(self, v: FightView) -> None:
        c = v.c
        gi = [k for k, n in enumerate(v.names) if n == GARMOND]
        if not len(c["a_fi"]) or not gi:
            return
        self.fights_with_allies += 1
        sel = np.flatnonzero(c["a_name"] == gi[0])
        hits = sorted((int(f), int(d["ent"])) for f, k, d in v.events if k == "hit" and isinstance(d.get("ent"), int)
                      and str(d.get("src")) in GARMOND_SRCS)
        hf = np.array([h[0] for h in hits], np.int64)
        prev = None
        for j in sel:
            st = int(c["a_st"][j])
            s = v.states[st] if st >= 0 else None
            if s == prev:
                continue
            prev = s
            if s not in GARMOND_ATTACKS:
                continue
            fi = int(c["a_fi"][j])
            f0 = int(v.f[fi])
            k = int(np.searchsorted(hf, f0))
            if k >= len(hits) or hits[k][0] - f0 > 180:
                self.n["attack starts without a hit within 3 s"] += 1
                continue
            target = hits[k][1]
            gx, gy = float(c["a_x"][j]), float(c["a_y"][j])
            cands = []
            for r in v.alive_enemies_cache(fi):
                iid = int(c["e_iid"][r])
                cands.append((iid, math.hypot(float(c["e_x"][r]) - gx, float(c["e_y"][r]) - gy),
                              float(c["e_hp"][r]) if not math.isnan(float(c["e_hp"][r])) else -1.0,
                              abs(float(c["e_x"][r]) - float(c["hx"][fi]))))
            if not any(x[0] == target for x in cands):
                self.n["target not among the enemies in play"] += 1
                continue
            self.n["decisions"] += 1
            self.n["candidates>1"] += len(cands) > 1
            if len(cands) > 1:
                self.n["nearest_to_garmond"] += min(cands, key=lambda x: x[1])[0] == target
                self.n["most_hp"] += max(cands, key=lambda x: x[2])[0] == target
                self.n["nearest_to_hero"] += min(cands, key=lambda x: x[3])[0] == target
                self.n["state:" + s] += 1

    def result(self) -> dict:
        n = self.n
        m = n.get("candidates>1", 0)
        return {"fights_with_allies_export": self.fights_with_allies, "counts": dict(n),
                "share_with_choice": {k: round(n[k] / m, 3) for k in ("nearest_to_garmond", "most_hp",
                                                                       "nearest_to_hero") if m}}


class Stances:
    def __init__(self):
        self.rows: dict[str, list] = defaultdict(list)
        self.seqs: dict[str, Counter] = defaultdict(Counter)

    def add(self, v: FightView) -> None:
        hits = defaultdict(list)
        for f, k, d in v.events:
            if k == "hit" and isinstance(d.get("ent"), int):
                hits[int(d["ent"])].append((int(f), d))
        for inst in v.instances:
            if inst.family not in STANCE_FAMILIES or inst.t_end is None or inst.anchor is None:
                continue
            seq = tuple(s for s, _ in inst.states)
            self.seqs[inst.family][" > ".join(seq[:8])] += 1
            hs = [h for h in hits.get(inst.iid, ()) if inst.f_start <= h[0] <= (inst.f_end or 0)]
            fi0, fi1 = v.fi_of.get(inst.f_start), v.fi_of.get(inst.f_end)
            if fi0 is None or fi1 is None:
                continue
            cols = _attack_cols(v, inst, fi0, fi1)
            row = {"hit": bool(hs), "dur": inst.t_end - inst.t_start, "states": seq}
            if hs and cols:
                fh = v.fi_of.get(hs[0][0])
                after = [x for x in cols if fh is not None and x[0] >= fh]
                if after:
                    row["delay_s"] = float(v.T[after[0][0]] - v.T[fh])
                    row["active_s"] = float(v.T[after[-1][0]] - v.T[after[0][0]])
                    row["names"] = sorted({x[1] for x in after})
                    row["parry"] = sorted({x[3] for x in after})
                    row["reach"] = [_facing_box(x[2], inst.anchor[0], inst.anchor[1], inst.mirror) for x in after]
                    row["dealt_on_hit"] = int(hs[0][1].get("dealt") or 0)
            elif cols:
                row["unhit_attack_cols"] = sorted({x[1] for x in cols})
            self.rows[inst.family].append(row)

    def result(self) -> dict:
        out = {}
        for fam, rows in sorted(self.rows.items()):
            hit = [r for r in rows if r["hit"]]
            ctr = [r for r in hit if "delay_s" in r]
            reach = np.array([b for r in ctr for b in r["reach"]] or [(math.nan,) * 4])
            out[fam] = {"type": STANCE_FAMILIES[fam], "instances": len(rows), "hit_in_stance": len(hit),
                        "counter_after_hit": len(ctr),
                        "unhit_with_attack_colliders": sum(1 for r in rows if not r["hit"] and r.get("unhit_attack_cols")),
                        "counter_delay_s": _q([r["delay_s"] for r in ctr]),
                        "counter_active_s": _q([r["active_s"] for r in ctr]),
                        "counter_colliders": dict(Counter(n for r in ctr for n in r["names"])),
                        "counter_parry_bits": dict(Counter(str(p) for r in ctr for p in r["parry"])),
                        "clashable_share": round(float(np.mean([any(p & 1 for p in r["parry"]) for r in ctr])), 3)
                        if ctr else None,
                        "hero_damage_dealt_on_the_stance_hit": _q([r.get("dealt_on_hit", 0) for r in ctr]),
                        "counter_reach_facing_u": {"x_min": round(float(np.nanmin(reach[:, 0])), 2),
                                                   "x_max": round(float(np.nanmax(reach[:, 2])), 2),
                                                   "y_min": round(float(np.nanmin(reach[:, 1])), 2),
                                                   "y_max": round(float(np.nanmax(reach[:, 3])), 2)},
                        "state_sequences": dict(self.seqs[fam].most_common(8))}
        return out


class Below:
    def __init__(self):
        self.n: dict[str, Counter] = defaultdict(Counter)

    def add(self, v: FightView) -> None:
        for inst in v.instances:
            if inst.tk not in FLIERS or inst.t_end is None or inst.anchor is None:
                continue
            sp = v.specs[inst.tk]
            if inst.family == sp.idle_family or inst.family.endswith("_ENTRY"):
                continue
            fi0, fi1 = v.fi_of.get(inst.f_start), v.fi_of.get(inst.f_end)
            if fi0 is None or fi1 is None:
                continue
            ax, ay = inst.anchor
            if ay < FLOOR_Y[1] + 1.0:       # on the ground: not above a hero
                continue
            key = f"{inst.tk}/{inst.family}"
            self.n[key]["instances"] += 1
            own = [b for r in v.rows_between(inst.iid, fi0, fi1) for _, b, _, _ in v.colliders(int(r))]
            fi2 = int(np.searchsorted(v.T, float(v.T[fi1]) + sp.spawn_window_s))
            thrown = [x[2] for x in v.hazards.get(id(inst), ()) if fi0 <= x[0] <= fi2]
            for label, boxes in (("own", own), ("with thrown hazards", own + thrown)):
                for dx in BELOW_DX:
                    for side in ((1,) if dx == 0 else (-1, 1)):
                        x = ax + side * dx * inst.mirror
                        hb = (x - HERO_HALF_W, FLOOR_Y[0], x + HERO_HALF_W, FLOOR_Y[1])
                        if any(b[0] <= hb[2] and hb[0] <= b[2] and b[1] <= hb[3] and hb[1] <= b[3] for b in boxes):
                            self.n[key][f"{label}: dx {'+' if side > 0 else '-'}{dx:g}"] += 1

    def result(self) -> dict:
        out = {}
        for key, c in sorted(self.n.items()):
            n = c["instances"]
            out[key] = {"instances": n, **{k: round(c[k] / n, 3) for k in sorted(c) if k != "instances"}}
        return {"note": "share of attack instances committed in the air whose own colliders (body included), and with "
                        "the hazards they threw (up to spawn_window_s after the attack), touch a hero box on the floor "
                        "at the commit point's x + dx (+: the side the enemy faces)", "by_family": out}


class Clawmaiden:
    TK = "Song Handmaiden"

    def __init__(self):
        self.dx, self.dy, self.speed = [], [], []

    def add(self, v: FightView) -> None:
        c = v.c
        for inst in v.instances:
            if inst.tk != self.TK or inst.family != v.specs[self.TK].idle_family or inst.t_end is None:
                continue
            for r in v.rows_between(inst.iid, v.fi_of.get(inst.f_start, 0), v.fi_of.get(inst.f_end, 0))[::3]:
                fi = int(c["e_fi"][r])
                self.dx.append(abs(float(c["hx"][fi]) - float(c["e_x"][r])))
                self.dy.append(float(c["e_y"][r]) - float(c["hy"][fi]))
                self.speed.append(abs(float(c["e_vx"][r])))

    def result(self) -> dict:
        dx = np.array(self.dx)
        reach = HERO["dash_stab_total_u"]
        return {"idle_frames_sampled": len(dx), "hero_dx_u": _q(dx), "dy_above_hero_u": _q(self.dy),
                "speed_x_u_s": _q(self.speed), "dash_stab_total_u": reach, "walk_side_reach_u": HERO["side_reach_u"],
                "share_within_dash_stab": round(float((dx <= reach).mean()), 3) if len(dx) else None,
                "share_within_side_slash": round(float((dx <= HERO["side_reach_u"]).mean()), 3) if len(dx) else None}


class Bells:
    def __init__(self):
        self.parry = Counter()
        self.tinks = Counter()
        self.pogo = Counter()
        self.speed: list = []

    def add(self, v: FightView) -> None:
        c = v.c
        bi = [k for k, t in enumerate(v.types) if t == BELL]
        if not bi:
            return
        sel = np.flatnonzero(c["e_tk"] == bi[0])
        for r in sel[::5]:
            for _, _, par, _ in v.colliders(int(r)):
                self.parry[str(par)] += 1
        prev: dict[int, str] = {}
        for r in sel:
            iid = int(c["e_iid"][r])
            st = int(c["e_st"][r])
            s = v.states[st] if st >= 0 else ""
            if s != prev.get(iid) and ("Tink" in s or s == "Nail Hit"):
                self.tinks[s] += 1
                fi = int(c["e_fi"][r])
                by = float(c["e_y"][r])
                hb = c["hbox"][fi]
                where = "hero above" if float(hb[1]) >= by - 0.2 else ("hero below" if float(hb[3]) <= by else
                                                                            "hero level")
                self.pogo[f"nail hits, {where}"] += 1
                vy0 = float(c["hvy"][max(0, fi - 3)])
                vy = c["hvy"][fi:fi + 10]
                if where == "hero above" and vy0 < 0.0:
                    self.pogo["nail hits from above while falling (down attacks)"] += 1
                    if len(vy) and float(np.nanmax(vy)) > 5.0:
                        self.pogo["... hero bounced (vy > 5 u/s within 10 frames)"] += 1
                # knocked away: the bell's speed right after the hit
                rs = v.rows.get(iid)
                k = int(np.searchsorted(c["e_fi"][rs], fi + 3))
                if k < len(rs):
                    rr = rs[k]
                    self.speed.append(math.hypot(float(c["e_vx"][rr]), float(c["e_vy"][rr])))
            prev[iid] = s

    def result(self) -> dict:
        return {"collider_parry_bits_frames": dict(self.parry), "tink_states": dict(self.tinks.most_common()),
                "pogo": dict(self.pogo), "speed_after_nail_hit_u_s": _q(self.speed)}


class Boundaries:
    def __init__(self):
        self.chosen: dict[str, list] = defaultdict(list)
        self.decisions: dict[str, list] = defaultdict(list)    # type -> [(dx, chosen family or None)]

    def add(self, v: FightView) -> None:
        c = v.c
        for f, k, d in v.events:
            if k != "fsm" or not isinstance(d.get("ent"), int):
                continue
            tk = go_type(d.get("obj")) if isinstance(d.get("obj"), str) else None
            sp = v.specs.get(tk)
            if sp is None or d.get("fsm") != sp.control_fsm or d.get("from") not in sp.decision_states:
                continue
            fi = v.fi_of.get(int(f))
            r = v.row_at(int(d["ent"]), fi) if fi is not None else None
            if r is None:
                continue
            dx = abs(float(c["hx"][fi]) - float(c["e_x"][r]))
            fam = sp.attack_starts.get(d.get("to"))
            self.decisions[tk].append((dx, fam))
            if fam is not None:
                self.chosen[f"{tk}/{fam}"].append(dx)

    def result(self) -> dict:
        out = {}
        for key, v in sorted(self.chosen.items()):
            tk, fam = key.split("/")
            b = float(np.max(v))
            near = [(dx, f) for dx, f in self.decisions[tk] if abs(dx - b) <= BOUNDARY_U]
            out[key] = {"chosen": len(v), "hero_dx_u": _q(v), "boundary_u": round(b, 2),
                        "p99_u": round(float(np.quantile(v, 0.99)), 2),
                        "decisions_within_1u_of_boundary": len(near),
                        "of_them_chosen": sum(1 for _, f in near if f == fam),
                        "beyond_boundary_within_1u": sum(1 for dx, f in near if dx > b)}
        return out


PRODUCTS = {"chains": Chains, "death_tails": DeathTails, "kill_freeze": KillFreeze, "strikes": Strikes,
            "quiet": Quiet, "garmond": Garmond, "stances": Stances, "below": Below, "clawmaiden": Clawmaiden,
            "bells": Bells, "boundaries": Boundaries}


def _alive_cache(self: FightView, fi: int) -> set:
    cache = self.__dict__.setdefault("_alive", {})
    s = cache.get(fi)
    if s is None:
        s = cache[fi] = set(self.alive_enemies(fi))
    return s


FightView.alive_enemies_cache = _alive_cache


class Products:
    def __init__(self, names=None):
        self.p = {k: cls() for k, cls in PRODUCTS.items() if names is None or k in names}
        self.fights = []

    def add(self, v: FightView) -> None:
        self.fights.append(v.c["meta"].get("id"))
        for p in self.p.values():
            p.add(v)
            v.__dict__.pop("_alive", None) if isinstance(p, Quiet) else None

    def result(self) -> dict:
        return {k: p.result() for k, p in self.p.items()}
