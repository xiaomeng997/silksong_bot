"""The Forum's LOCAL multi-enemy tactics (forum_planner_plan §5 R4, the A0 baseline that R5 / R6 must beat).

    tac = ForumTactics(*load_forum_playbook())
    prefs = tac.decide(ws, mf_forecast, decision, h)      # every tick, before ForumPlanner.tick

Modes (first that applies; rules, not learning; scores only: no field here reaches a candidate's S / Hz / U,
forum_planner_plan §4.4 item 2):
  HEAL    Q1a (DESIGN §3.7.4): h >= 2 below max HP with the Bind's silk and the §3.5.6 commit test passing at the
          hero's position (the support's t_min there >= T_bind + delta_b): the planner gets the Bind macro. No safe
          spot in the Forum (the pocket is not a heal point until the wall Bind is verified: playbook). Q6: with
          h >= 2 below max HP and silk < 9 the nail hit weight is raised (gather silk; the supervisor has the silk
          skills off below full HP). Q1 is the supervisor's (quit in the post-hit window).
  LEAVE   the finale's pocket rule (2) (forum.md §10.4): the hero is in the left-wall pocket and a Choir Clapper
          facing left stands at transform x <= 18 (its jump from there grazes or enters the pocket): leave it.
  EVADE   the support reaches the hero's spot within evade_s: the nearest floor spot the support leaves free over
          that horizon, weighed with its later coverage and the walls; hits score little.
  ENGAGE  enemies in play: the target is the nearest by distance / type priority (Clawmaiden first; a Bellbearer or a
          Maestro farther than far_u last); the stance just outside its body on the hero's side, pulled to low
          coverage; hit weights per enemy iid: the target more, a Minister / Reed in its defensive stance negative
          (no melee into the counter: forum.md §12.3 stances).
  HOLD    nobody in play (between waves): the hero's x, moved by the coverage (the next wave's entries are in the
          support, so its spawn points are avoided by the risk map).
Pocket rule (1): before the pocket, no Clapper with its body's left edge at x <= 14.6: while one is there, stances
under the pocket (x < pocket_x) cost extra. A0 has no climb macro (R7), so the rules only shape stances.
"""
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml

from ssbot.combat.tactics.modes import ENGAGE, EVADE, HEAL, HOLD, GoalPrefs
from ssbot.combat.tactics.playbook import PLAYBOOKS, Playbook
from ssbot.core.primitives import Prim
from ssbot.safety.supervisor import BIND_SILK, bind_allowed

LEAVE = "LEAVE"
GRID_U = 0.5
WALL_ROOM = 3.0
WALL_PEN = 1.0
HOLD_PULL = 0.15
CLAPPER = "Song Heavy Sentry"


@dataclass
class ForumRules:
    priority: dict = field(default_factory=dict)          # type_key -> weight (distance / weight picks the target)
    first: tuple = ()                                      # types targeted before any other while one is in play
    distant_last: tuple = ()                               # type_keys whose weight drops beyond far_u
    far_u: float = 8.0
    far_w: float = 0.4
    defensive: dict = field(default_factory=dict)         # type_key -> Control states of its defensive stance
    defensive_hit_w: float = -1.0
    target_hit_w: float = 1.5
    other_hit_w: float = 1.0
    engage_reach_u: float = 1.8
    evade_s: float = 0.6
    pocket_box: tuple = (14.04, 14.92, 12.53, 13.97)       # HeroBoxWallSlide at the top of the left-wall cling
    pocket_x: float = 16.0                                 # stances left of this are "under the pocket"
    veto_enter_left_edge: float = 14.6                     # rule (1)
    veto_in_x: float = 18.0                                # rule (2)
    clapper_body_l: tuple = (2.25, 1.34)                   # body left extent from the transform: facing left / right
    cogfly: dict = field(default_factory=dict)             # wave index -> throws; min_clear_s, gap_s

    @classmethod
    def from_dict(cls, d: dict) -> "ForumRules":
        p = d.get("pocket") or {}
        dl = d.get("distant_last") or {}
        cg = d.get("cogfly") or {}
        return cls(priority={str(k): float(v) for k, v in (d.get("priority") or {}).items()},
                   first=tuple(d.get("first") or ()),
                   distant_last=tuple(dl.get("types") or ()), far_u=float(dl.get("far_u", 8.0)),
                   far_w=float(dl.get("weight", 0.4)),
                   defensive={str(k): tuple(v) for k, v in (d.get("defensive") or {}).items()},
                   defensive_hit_w=float(d.get("defensive_hit_w", -1.0)),
                   target_hit_w=float(d.get("target_hit_w", 1.5)), other_hit_w=float(d.get("other_hit_w", 1.0)),
                   engage_reach_u=float(d.get("engage_reach_u", 1.8)), evade_s=float(d.get("evade_s", 0.6)),
                   pocket_box=tuple(p.get("box", (14.04, 14.92, 12.53, 13.97))),
                   pocket_x=float(p.get("stance_x", 16.0)),
                   veto_enter_left_edge=float(p.get("veto_enter_left_edge", 14.6)),
                   veto_in_x=float(p.get("veto_in_x", 18.0)),
                   cogfly={"uses": {int(k): int(v) for k, v in (cg.get("uses") or {}).items()},
                           "min_clear_s": float(cg.get("min_clear_s", 1.0)), "gap_s": float(cg.get("gap_s", 3.0)),
                           "enabled": bool(cg.get("enabled", True))})


def load_forum_playbook(path: Path | str | None = None) -> tuple[Playbook, ForumRules]:
    p = Path(path) if path else PLAYBOOKS / "Forum.yaml"
    d = yaml.safe_load(p.read_text("utf-8"))
    return Playbook.from_dict(d), ForumRules.from_dict(d.get("forum") or {})


def _ent_x(e) -> float | None:
    pt = getattr(e, "pos_transform", None)
    if pt is not None:
        return float(pt[0])
    pos = getattr(e, "pos", None)
    v = getattr(pos, "v", None)
    return None if v is None or getattr(pos, "conf", 1.0) <= 0 else float(v[0])


def _facing(e) -> int | None:
    fa = getattr(e, "facing", None)
    if fa is None or getattr(fa, "conf", 1.0) <= 0 or getattr(fa, "v", None) is None:
        return None
    return 1 if fa.v > 0 else -1


class ForumTactics:
    def __init__(self, pb: Playbook, rules: ForumRules, floor_y: float):
        self.pb, self.rules, self.floor_y = pb, rules, floor_y
        x0, x1 = pb.arena_x
        self.xs = np.arange(x0, x1 + 1e-9, GRID_U)
        self.last: dict = {}

    def risk_map(self, fc, horizon: tuple[float, float] | None = None) -> np.ndarray:
        t0, t1 = horizon or self.pb.risk_horizon_s
        tk = np.arange(int(round(t0 * 30)), int(round(t1 * 30)) + 1) / 30.0
        n = len(self.xs)
        occ = fc.occupied(np.repeat(self.xs[:, None], len(tk), 1), np.full((n, len(tk)), self.floor_y), tk)
        w = 1.0 / (1.0 + tk)
        return (np.asarray(occ) * w).sum(axis=1) / w.sum()

    def clappers(self, ws) -> list[tuple[float, int | None]]:
        """(transform x, facing) of every Choir Clapper in the view."""
        out = []
        for e in getattr(ws, "entities", ()) or ():
            tk = getattr(getattr(e, "type_key", None), "v", None)
            if tk == CLAPPER and not getattr(e, "hidden", False):
                x = _ent_x(e)
                if x is not None:
                    out.append((x, _facing(e)))
        return out

    def in_pocket(self, hx: float, hy: float) -> bool:
        x0, x1, y0, _ = self.rules.pocket_box
        return hx <= x1 + 0.3 and hy >= y0 + 0.3

    def pocket_vetoes(self, ws) -> tuple[bool, bool]:
        """(rule 1: a Clapper's body left edge at or left of veto_enter_left_edge, rule 2: a Clapper facing left (or
        facing unknown) at transform x <= veto_in_x). forum.md §10.4."""
        r = self.rules
        enter = inside = False
        for x, fa in self.clappers(ws):
            left = x - (r.clapper_body_l[0] if fa is None or fa < 0 else r.clapper_body_l[1])
            enter |= left <= r.veto_enter_left_edge
            inside |= (fa is None or fa < 0) and x <= r.veto_in_x
        return enter, inside

    def target(self, subjects, hx: float, hy: float):
        """The nearest enemy in play by distance / type weight (None: nobody in play)."""
        r = self.rules
        best, best_k = None, math.inf
        live = [s for s in subjects if s.alive and s.in_play and s.pos is not None]
        if any(s.type_key in r.first for s in live):
            live = [s for s in live if s.type_key in r.first]
        for s in live:
            d = math.hypot(s.pos[0] - hx, s.pos[1] - hy)
            w = r.priority.get(s.type_key, 1.0)
            if s.type_key in r.distant_last and d > r.far_u:
                w = min(w, r.far_w)
            k = d / max(w, 1e-3)
            if k < best_k:
                best, best_k = s, k
        return best

    def hit_weights(self, subjects, target) -> dict:
        r = self.rules
        out = {}
        for s in subjects:
            if not s.alive:
                continue
            if s.state is not None and s.state in r.defensive.get(s.type_key, ()):
                out[s.iid] = r.defensive_hit_w
            elif target is not None and s.iid == target.iid:
                out[s.iid] = r.target_hit_w * max(1.0, r.priority.get(s.type_key, 1.0))
            else:
                out[s.iid] = r.other_hit_w
        return out

    def decide(self, ws, fc, d, h: int | None) -> GoalPrefs:
        pb, r = self.pb, self.rules
        wts = dict(pb.weights)
        hx, hy = float(ws.hero.pos.v[0]), float(ws.hero.pos.v[1])
        hp, max_hp, silk = ws.res.hp.v, ws.res.hp_max.v, ws.res.silk.v
        risk = self.risk_map(fc)
        subjects = list(getattr(fc, "subjects", ()) or ())
        tgt = self.target(subjects, hx, hy)
        prefs = GoalPrefs(HOLD, hx, wts, risk_x=self.xs, risk=risk, goal="LOCAL",
                          target=None if tgt is None else tgt.iid, hit_w=self.hit_weights(subjects, tgt))
        if tgt is not None:
            prefs.boss_x = float(tgt.pos[0])
        if d is not None and d.restrictions.max_punish_hits is not None:
            prefs.max_hits = d.restrictions.max_punish_hits
        enter_veto, in_veto = self.pocket_vetoes(ws)
        self.last = {"target_type": None if tgt is None else tgt.type_key, "pocket_veto": [enter_veto, in_veto]}
        x0, x1 = pb.arena_x
        wall = ((self.xs < x0 + WALL_ROOM) | (self.xs > x1 - WALL_ROOM)) * WALL_PEN
        if enter_veto:
            wall = wall + (self.xs < r.pocket_x) * 2.0 * WALL_PEN
        # HEAL (Q1a) and Q6's silk gathering: the same rule as the Bell Beast's Tactics (DESIGN §3.7.4)
        bind_ok = d is None or d.allows(Prim.BIND)
        heal_first = d is not None and h is not None and h >= 2 and hp is not None and max_hp is not None \
            and hp < max_hp
        if heal_first and silk is not None and silk < BIND_SILK:
            wts["hit"] *= pb.bind_gather_hit_x
        if (hp is not None and max_hp and silk is not None and silk >= BIND_SILK and hp < max_hp and bind_ok
                and h is not None and h >= 2 and (heal_first or hp <= max_hp - pb.bind_hp_missing_min)):
            pending = bool(d is not None and d.pause_pending)
            prefs.t_min = fc.t_min(hx, hy, t_max=2.0)
            v = bind_allowed(int(silk), int(hp), int(max_hp), int(h), prefs.t_min, pause_pending=pending)
            prefs.bind_why = v.reason
            if v.ok:
                prefs.mode, prefs.want_bind, prefs.stance_x = HEAL, True, hx
                return prefs
        if in_veto and self.in_pocket(hx, hy):
            prefs.mode = LEAVE
            prefs.stance_x = float(self.xs[int(np.argmin(risk + wall + 0.05 * np.abs(self.xs - 24.0)))])
            wts["hit"] *= 0.3
            return prefs
        soon = fc.t_min(hx, self.floor_y if hy < self.floor_y + 1.0 else hy, t_max=r.evade_s)
        if soon < r.evade_s:
            near = self.risk_map(fc, (0.0, r.evade_s))
            prefs.mode = EVADE
            prefs.stance_x = float(self.xs[int(np.argmin(near + 0.5 * risk + 0.1 * np.abs(self.xs - hx) + wall))])
            wts["hit"] *= 0.3
            wts["risk"] *= 2.0
            return prefs
        if tgt is not None:
            tx = float(tgt.pos[0])
            x_eng = tx - r.engage_reach_u if hx < tx else tx + r.engage_reach_u
            cost = risk + wall + 0.3 * np.abs(self.xs - x_eng) / max(1.0, r.engage_reach_u)
            prefs.mode, prefs.stance_x = ENGAGE, float(self.xs[int(np.argmin(cost))])
            return prefs
        cost = risk + wall + HOLD_PULL * np.abs(self.xs - hx)
        prefs.stance_x = float(self.xs[int(np.argmin(cost))])
        return prefs
