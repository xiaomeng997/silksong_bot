"""The Forum's L2 target layer, v0 (forum_planner_plan §5 R6, the person's rules of 2026-10-04 / 05): a few rules above
LOCAL (combat.tactics.forum_local.ForumTactics) that say whom to go for and where to stand. Not the GoalArbiter of the
plan (§4.1) yet: no fields, no BAIT / SPLIT / POCKET goals, no terminal value.

    tac = GauntletTactics(ForumTactics(pb, rules, floor_y), L2Rules.from_dict(d["forum"]["l2"]))
    prefs = tac.decide(ws, mf_forecast, decision, h)     # every tick, before ForumPlanner.tick (same call as LOCAL)

Every tick LOCAL decides first (HEAL, LEAVE, EVADE, ENGAGE, HOLD); HEAL and LEAVE stand. Otherwise L2 picks a goal
every `period` ticks and on events (the goal's target gone or out of play, a PUNISH window over or its target into
another move: the goal ends; the target into another move: a pick that may keep it). The rule (below, first that
applies) and the target are held (round 2: the round-1 A/B changed goals 33 times a minute in wave 0, forum.md §17.5):
  - a rule change waits until the kept rule has run `goal_dwell_s` (KITE <-> RUSH at the 8 u edge), except into
    PUNISH (an opening); a kept PUNISH runs to its window's end unless another one scores `switch_x` times more;
  - under the rule the kept target stays while it is eligible (RUSH: isolated, for the kept one down to iso_u -
    iso_hyst_u; KITE: any), unless another one scores `switch_x` times more and the kept one has been the target
    `dwell_s`, or it is the idle Clapper's turn (Buddy Is Attacking); a kept RUSH target that lost its isolation is
    kited with (KITE on it) until dwell_s, then RUSH moves to an isolated one; a `first` type entering switches at
    once. stats: tgt_switches by kind (gone / ineligible / better / turn / punish).
Goals:
  PUNISH  an enemy whose engagement spot stays out of every support (all enemies, hazards, entries: MultiForecast
          .occupied, one batched query for all spots) from the hero's arrival through the swing: window (the first
          cover at or after t_run; a cover before the arrival does not count) >= t_run + swing_s + margin_s, t_run =
          start_s + |dx| / run_u_s (dash + sprint, ~17.5 u/s, the person). Picked by slack (window -
          what it needs) x type priority. This is the far-target rule of the plan's R6 row: a near idle enemy (its next
          attack can start any time: a short window) against a far one in a long recovery (a long window) -> the far
          one when the window covers the run, the near one when it does not.
  RUSH    an isolated enemy (no other enemy in play within iso_u): go and hit it. When every enemy is isolated
          ("spread"), the fastest pursuer first: the least ETA = max(0, d - reach) / its pursuit speed (pursuit_u_s:
          the mean speed it closes on the hero at, R0 caches, forum.md §17). Clawmaiden first (only it while it is
          in play), Minister last (only when nobody else is).
  KITE    nobody isolated: stand kite_u from the fastest pursuer on its side away from the others (it comes first and
          alone); with Tinies in play, under the nearest Maestro instead (the Tinies' charge is safer there: below.json
          7.1 % vs 34 / 58 %).
Engagement spots by type: under the flyers (Bellbearer, Reed, Minister, Maestro: x = theirs, the person's "under it is
safer"; the Minister's dash slash carries it two bodies on, so from below you end up behind it), reach_u on the hero's
side for the rest, and the Choir Clapper by its own controller (cannot be clashed; forum.md §10, clapper_face.md):
  idle / walk / cast / evade  face it at face_u (its front is where the hero is: FaceObject at every attack start);
          CC_CAST (about 1.25 s standing, only the ground runes hurt: jump when the near rune lights) also opens the
          GLIDE_SPIKE hook (vocab; R7's Sawtooth Circlet glide spike is not in the planner yet: nothing reads it).
  CC_SLAM the one move that needs a step back: out to slam_out_u in front (12.5 u: 2.3 %, 13 u: 0) or, with the hero
          already behind it, slam_behind_u behind (3 u: 0.2 %); with no room out, as far out as the wall lets (not
          behind: that is through its body on the ground); the down slash on its head (15 / 22 in the person's
          practice: the down-slash hit's 0.16 s i-frames + the bounce) is the planner's to pick from its own rows.
  CC_JUMP / CC_JUMP_CAST  landing = take-off + 0.92 clamp(aim - take-off, +-12), aim = hero x at Jump Aim -/+ 5 on
          its side. The aim (the hero's x then, the take-off x from its antic, its facing) is taken on the first tick
          past the antic (Jump Aim is instant: never a tick's state); before it the landing follows the hero. Behind
          the landing (behind_land_u: the slam collider and the rune slam, 6.62 u in front of it with r 7.19, reach
          0.58 u behind it) only following it from its back side (the hero not in front of it: it jumps the way it
          faces) with room there, never under it; else back off in front of the landing: CC_JUMP past its landing slam (0.67-7.76 u in front:
          jump_out_u), CC_JUMP_CAST past the rune circle too (to 13.8 u: cast_out_u), as far as the wall lets.
          Judged every tick. (Rounds 1-3: running under it to get behind it took its body: v2 6 crossings / 14 body
          hits on w7, the round-3 way round fixed at the aim 8 / 8 crossings / 8 body hits; v3 / v4, whose judgement
          followed the hero, 0-1 crossings / 0 body hits; forum.md 17.7.1.)
          After a CC_JUMP_CAST its rune circle bursts about 0.75-0.87 s after the move ends (rune_hold_s 1 s): until
          then the stance stays behind the landing (the hero on its back side; not through its body) or out past
          the circle, not at its face (round 3).
  Two Clappers never attack together (Buddy Is Attacking): while one is committed, the other one, if not and its
          spot is reached before that attack can end (Subject.t_free), is the RUSH / PUNISH pick between the two
          (priority x 2, a switch at once).
What a goal sets (scores only: the planner's S / Hz / U never see prefs, §4.4 item 2): mode (the goal's name), target,
stance_x, boss_x (face it), hit_w (the target x target_hit_w x priority, 0 while the Clapper controller steps away:
CC_RETREAT; the others as LOCAL, defensive stances still negative) and the weights' factors per goal (l2.weights). LOCAL's EVADE stands against KITE when it says the hero's spot
is covered within evade_s; PUNISH and RUSH replace it (the planner's support check is the safety).
Failure (§4.4 item 4): an exception or an injected failure (fail_p) returns LOCAL's prefs untouched, so with fail_p = 1
every decision is LOCAL's bit for bit (tests/test_forum_l2.py).
"""
import math
import random
import time
from dataclasses import dataclass, field, replace

import numpy as np

from ssbot.combat.tactics.forum_local import (CLAPPER, EVADE_HIT_X, EVADE_RISK_X, LEAVE, ForumTactics,
                                               clapper_facing)
from ssbot.combat.tactics.modes import EVADE, HEAL, GoalPrefs
from ssbot.core.worldstate import Ev

PUNISH, RUSH, KITE, LOCAL = "PUNISH", "RUSH", "KITE", "LOCAL"
CLAWMAIDEN = "Song Handmaiden"
MAESTRO = "Song Pilgrim Maestro"
MINISTER = "Song Administrator"
TINY = "Song Automaton Tiny"
CC_IDLE, CC_SLAM, CC_JUMP, CC_JUMP_CAST, CC_CAST = "CC_IDLE", "CC_SLAM", "CC_JUMP", "CC_JUMP_CAST", "CC_CAST"
# a jump's states before its Jump Aim (the antic: standing). Jump Aim (and Cast Jump) are instant: one frame goes
# Jump Antic / Cast Slam Antic 2 -> (Cast Jump ->) Jump Aim -> Jump, so the tracker never ends a frame in Jump Aim and
# the first tick past the antic (Jump, 1 frame, then Air) is where the aim is taken (round 3: keyed on Jump Aim as a
# tick state the aim was never stored live, forum.md 17.7)
CC_PRE_AIM_STATES = ("Jump Antic", "Cast Slam Antic", "Cast Slam Antic 2", "Cast Jump")
CC_RETREAT = ("slam: step out", "slam: out to the wall", "jump: back off", "rune: out")  # branches that step away
GLIDE_SPIKE = "GLIDE_SPIKE"
NAIL_SRC = ("Slash", "UpSlash", "DownSlash New", "AltSlash", "WallSlash", "DashSlash")


def jump_landing(x0: float, aim_x: float, front: float) -> float:
    """A Choir Clapper's jump landing x (forum.md §10.1, clapper_face.md §2.1: Jump Aim targets the hero's x 5 u on its
    own side, the jump's vx = clamp(target - x, +-12), the landing fitted as take-off + 0.92 x that, residual p50 0)."""
    return x0 + 0.92 * max(-12.0, min(12.0, aim_x - front * 5.0 - x0))


@dataclass
class L2Rules:
    enabled: bool = True
    period: int = 6                                       # ticks between picks (10 Hz)
    switch_x: float = 1.5                                 # another target must score this many times the kept one's
    dwell_s: float = 4.0                                  # a kept target is held this long before another one
    goal_dwell_s: float = 1.0                             # the same target under another rule after this long
    iso_u: float = 8.0                                    # isolated: no other enemy in play within this (|dx|, u)
    iso_hyst_u: float = 2.0                               # the kept target stays isolated down to iso_u - this
    rule_hyst_u: float = 0.0                              # from KITE, RUSH needs one isolated by iso_u + this
    run_u_s: float = 17.5                                 # dash + sprint (the person)
    start_s: float = 0.05
    swing_s: float = 0.25                                 # press -> the Reaper side slash's active end (0.208 s)
    margin_s: float = 0.10
    window_max_s: float = 2.0
    reach_u: float = 1.8                                  # engagement spot from the transform (LOCAL's)
    kite_u: float = 8.0
    wall_room_u: float = 2.5
    target_hit_w: float = 3.0
    face_u: float = 4.0                                   # the Clapper: face-hit distance (2.5-5.4 u, clapper_face §2)
    slam_out_u: float = 13.0
    slam_behind_u: float = 3.5
    behind_land_u: float = 2.5
    jump_out_u: float = 8.5                               # CC_JUMP: in front of the landing past its slam (7.76 u)
    cast_out_u: float = 14.5                              # CC_JUMP_CAST: past the rune circle (6.62 + 7.19 u)
    rune_hold_s: float = 1.0                              # CC_JUMP_CAST's rune circle: off this long after the move
    below: tuple = ("Pilgrim 03 Song", "Song Reed", "Song Administrator", MAESTRO)
    priority: dict = field(default_factory=dict)          # type_key -> factor (Clawmaiden first, Minister last)
    first: tuple = (CLAWMAIDEN,)                          # while one is in play, only these are picked
    last: tuple = (MINISTER,)                             # picked only when nobody else is in play
    pursuit_u_s: dict = field(default_factory=dict)       # type_key -> u/s
    weights: dict = field(default_factory=dict)           # goal -> {weight name: factor}
    fail_p: float = 0.0                                   # injected failures (§4.4 item 4)

    @classmethod
    def from_dict(cls, d: dict | None) -> "L2Rules":
        d = dict(d or {})
        out = cls()
        for k, v in d.items():
            if not hasattr(out, k):
                raise KeyError(f"forum.l2: unknown key {k!r}")
            cur = getattr(out, k)
            if isinstance(cur, dict):
                v = {str(a): (dict(b) if isinstance(b, dict) else float(b)) for a, b in (v or {}).items()}
            elif isinstance(cur, tuple):
                v = tuple(v or ())
            elif isinstance(cur, bool):
                v = bool(v)
            elif isinstance(cur, int):
                v = int(v)
            else:
                v = float(v)
            setattr(out, k, v)
        return out


def load_l2_rules(path=None, env: str | None = None) -> L2Rules:
    """The playbook's forum.l2 section (Forum.yaml), then the run's SSBOT_FORUM_L2 switch (combat_run records it in
    config.json and each row): "0" / "off" -> disabled (the A0 LOCAL tactics), "fail:<p>" -> injected failures."""
    from pathlib import Path

    import yaml

    from ssbot.combat.tactics.playbook import PLAYBOOKS
    p = Path(path) if path else PLAYBOOKS / "Forum.yaml"
    d = yaml.safe_load(p.read_text("utf-8"))
    r = L2Rules.from_dict((d.get("forum") or {}).get("l2") or {"enabled": False})
    sw = (env or "").strip().lower()
    if sw in ("0", "off", "false"):
        r.enabled = False
    elif sw.startswith("fail:"):
        r.fail_p = float(sw[5:])
    elif sw not in ("", "1", "on", "true"):
        raise ValueError(f"SSBOT_FORUM_L2={env!r}: 0 / off, 1 / on or fail:<p>")
    return r


@dataclass
class Cand:
    s: object                                             # the Subject
    x: float
    y: float
    d: float                                              # |dx| to the hero
    spot: float                                           # engagement spot x
    t_run: float
    window: float = math.inf
    iso: bool = False
    sep: float = math.inf                                 # |dx| to the nearest other enemy in play
    eta: float = math.inf
    prio: float = 1.0
    cov0: bool = False                                    # the spot covered now (the arbitration log)


@dataclass
class Goal:
    name: str
    target: int | None
    stance_x: float
    t_pick: float
    score: float = 0.0
    family: str | None = None
    t_end: float = math.inf                               # PUNISH: the window's end (game time)
    vocab: frozenset = frozenset()
    face_x: float | None = None
    why: str = ""
    landed: bool = False                                  # PUNISH: a nail hit on the target inside the window
    t_goal: float = 0.0                                   # since when this rule on this target (t_pick: this target)


def _new_stats() -> dict:
    return {"picks": 0, "switches": 0, "changes": 0, "tgt_switches": 0, "fails": 0, "errors": 0, "ms": [], "goals": {},
            "goal_hits": {}, "punish_goals": 0, "punish_landed": 0, "switch_kinds": {}, "rule_changes": {}}


class GauntletTactics:
    def __init__(self, local: ForumTactics, rules: L2Rules, seed: int = 0):
        self.local, self.rules = local, rules
        self.pb = local.pb
        self.floor_y = local.floor_y
        self.rng = random.Random(seed)
        self.goal: Goal | None = None
        self._sw_why: str | None = None                   # why _pick moved off the kept target (stats switch_kinds)
        self.n = 0
        self.aim: dict[int, tuple] = {}                   # Clapper iid -> (hero x, take-off x, facing) at its aim
        self.antic: dict[int, float] = {}                 # Clapper iid -> its x in its jump's antic (the take-off)
        self.jump_how: dict[int, str] = {}                # Clapper iid -> its jump's way round (the last tick's)
        self.jfam: dict[int, str] = {}                    # Clapper iid -> the jump family it is in
        self.rune: dict[int, tuple] = {}                  # Clapper iid -> (landing, facing, way round, until): a jump
                                                          # cast's rune circle still to burst
        self._t = 0.0                                     # the tick's game time
        self.stats = _new_stats()
        self.last: dict = {}

    @property
    def xs(self):
        return self.local.xs

    def reset(self) -> None:
        """A new episode: no goal, no stored aims, the per-episode counters cleared."""
        self.goal, self.n, self.aim, self.antic, self.jump_how = None, 0, {}, {}, {}
        self.jfam, self.rune = {}, {}
        self.stats = _new_stats()

    # ---- geometry ----

    def _clamp(self, x: float) -> float:
        x0, x1 = self.pb.arena_x
        r = self.rules.wall_room_u
        return min(max(x, x0 + r), x1 - r)

    def _ent(self, ws, iid):
        for e in getattr(ws, "entities", ()) or ():
            if getattr(e, "id", None) == iid:
                return e
        return None

    def _clapper_spot(self, ws, s, hx: float) -> tuple[float, frozenset, str]:
        """The Clapper controller (module docstring): (stance x, vocab, why)."""
        r = self.rules
        x = float(s.pos[0])
        side = 1.0 if hx >= x else -1.0                   # where the hero is from it
        e = self._ent(ws, s.iid)
        fa = clapper_facing(e) if e is not None else None
        front = float(fa) if fa is not None else side      # it faces the hero at every attack start
        fam = s.family
        xa, xb = self.pb.arena_x
        room = (lambda v: xa + r.wall_room_u <= v <= xb - r.wall_room_u)
        if fam == CC_SLAM:
            if side != front:
                return self._clamp(x - front * r.slam_behind_u), frozenset(), "slam: stay behind"
            out = x + front * r.slam_out_u
            if room(out):
                return out, frozenset(), "slam: step out"
            # behind it means through its body on the ground (round 2, live w13: 7 body hits that way): as far out
            # as the wall lets (the hammer reaches 12 u in front: the farther the likelier it misses)
            return self._clamp(out), frozenset(), "slam: out to the wall"
        if fam in (CC_JUMP, CC_JUMP_CAST):
            # before its Jump Aim it will aim at where the hero is then (from where it stands); after, the stored aim
            aim_x, x0, front = self.aim.get(s.iid, (hx, x, front))
            land = jump_landing(x0, aim_x, front)
            behind = land - front * r.behind_land_u
            out = land + front * (r.jump_out_u if fam == CC_JUMP else r.cast_out_u)
            # never under it (round 3, live: with the way round fixed at the aim the hero ran under it on 8 / 8 w7
            # jumps and took its body 8 times; v2 6 crossings / 14 body hits, v3 / v4 0-1 crossings / 0 body hits):
            # behind the landing only following it from its back side (it jumps the way it faces), else back off in
            # front of the landing, away from where it comes down
            how = "behind" if room(behind) and (hx - x) * front <= 0 else "back off"
            self.jump_how[s.iid] = how                    # the last way round (a jump cast's rune circle after it)
            return self._clamp(behind if how == "behind" else out), frozenset(), f"jump: {how}"
        rp = self.rune.get(s.iid)
        if rp is not None and fam != CC_SLAM and self._t <= rp[3]:
            # a jump cast's rune circle (6.62 u in front of the landing, r 7.19: from 0.58 u behind it to 13.8 u in
            # front) bursts about 0.75-0.87 s after the move ends (its tail, ChoirClapper.json): the face (4 u in
            # front) is inside it. Stay behind the landing (where the way round went, not through its body) or out
            # past it (round 3: v4 w7 took 20 of its hits there, the controller back at the face)
            land, f0, how, _ = rp
            behind = land - f0 * r.behind_land_u
            out = land + f0 * r.cast_out_u
            through = (behind - x) * (hx - x) < 0
            if room(behind) and not through and (how == "behind" or not room(out)):
                return behind, frozenset(), "rune: behind"
            return self._clamp(out), frozenset(), "rune: out"
        vocab = frozenset({GLIDE_SPIKE}) if fam == CC_CAST else frozenset()
        return self._clamp(x + side * r.face_u), vocab, "face"

    def _spot(self, ws, s, hx: float) -> tuple[float, frozenset, str]:
        r = self.rules
        x = float(s.pos[0])
        if s.type_key == CLAPPER:
            return self._clapper_spot(ws, s, hx)
        if s.type_key in r.below:
            return self._clamp(x), frozenset(), "below"
        return self._clamp(x - r.reach_u if hx < x else x + r.reach_u), frozenset(), "reach"

    # ---- the pick ----

    def candidates(self, ws, fc, hx: float, kept: int | None = None) -> list[Cand]:
        """Every enemy in play with its spot, run time, window, isolation (`kept`: the kept target's iid, isolated down
        to iso_u - iso_hyst_u), ETA and priority."""
        r = self.rules
        live = [s for s in (getattr(fc, "subjects", ()) or ()) if s.alive and s.in_play and s.pos is not None]
        out = []
        for s in live:
            x, y = float(s.pos[0]), float(s.pos[1])
            spot, _, _ = self._spot(ws, s, hx)
            c = Cand(s, x, y, abs(x - hx), spot, r.start_s + abs(spot - hx) / r.run_u_s)
            others = [abs(float(o.pos[0]) - x) for o in live if o.iid != s.iid]
            c.sep = min(others) if others else math.inf
            c.iso = c.sep >= r.iso_u - (r.iso_hyst_u if s.iid == kept else 0.0)
            v = r.pursuit_u_s.get(s.type_key, 5.0)
            c.eta = max(0.0, c.d - r.reach_u) / max(v, 0.1)
            c.prio = r.priority.get(s.type_key, 1.0)
            out.append(c)
        if out:
            tk = np.arange(0, int(round(r.window_max_s * 30)) + 1) / 30.0
            X = np.repeat(np.array([[c.spot] for c in out]), len(tk), 1)
            occ = np.asarray(fc.occupied(X, np.full(X.shape, self.floor_y), tk))
            for c, row in zip(out, occ):
                # the window counts from the hero's arrival: the spot covered before it (the enemy's body there now,
                # an attack ending) does not matter, the first cover at or after t_run ends it. Clear to the query's
                # end: open (inf) when the run and the swing fit in it, else unknown past it (the window = its end,
                # too short: before round 2 a far spot, t_run + swing > window_max_s, was never checked -> inf)
                i = np.flatnonzero(row & (tk >= c.t_run - 1e-9))
                fits = c.t_run + r.swing_s + r.margin_s <= tk[-1]
                c.window = float(tk[i[0]]) if len(i) else (math.inf if fits else float(tk[-1]))
                c.cov0 = bool(row[0])
        return out

    def _choose(self, elig: list[Cand], val, old: Goal | None, t: float, turn: set) -> Cand:
        """The target under a rule: the best by `val` (bigger is better), but the kept target while eligible unless
        the best scores switch_x times more after dwell_s, or it is the idle Clapper's turn (module docstring)."""
        r = self.rules
        best = max(elig, key=val)
        kept = next((c for c in elig if old is not None and c.s.iid == old.target), None)
        self._sw_why = "ineligible" if kept is None else None
        if kept is None or best is kept:
            return best
        if best.s.iid in turn and kept.s.iid not in turn:
            self._sw_why = "turn"
            return best
        if val(best) >= r.switch_x * val(kept) and t - old.t_pick >= r.dwell_s:
            self._sw_why = "better"
            return best
        return kept

    def _pick(self, ws, fc, hx: float, t: float, old: Goal | None = None) -> Goal | None:
        """The goal (module docstring); `old`: the kept goal (its target alive and in play), None when it ended."""
        r = self.rules
        cands = self.candidates(ws, fc, hx, old.target if old is not None else None)
        self._sw_why = None
        # the arbitration log (decision records "l2_cands"): iid, type, window, what it needs, isolated, ETA, priority
        self.last["l2_cands"] = [[c.s.iid, c.s.type_key, round(min(c.window, 9.0), 3),
                                  round(c.t_run + r.swing_s + r.margin_s, 3), c.iso, round(c.eta, 2), c.prio, c.cov0]
                                 for c in cands]
        if not cands:
            return None
        claps = [c for c in cands if c.s.type_key == CLAPPER]
        turn = set()
        if len(claps) >= 2 and any(c.s.committed for c in claps):
            # Buddy Is Attacking: the idle one cannot start an attack while the other one is in its; its turn only
            # when its spot is reached before that attack can end (round 2: live w13 switched 15 / min on turns)
            busy = {c.s.iid for c in claps if c.s.committed}
            t_free = max(float(getattr(c.s, "t_free", 0.0) or 0.0) for c in claps if c.s.iid in busy)
            for c in claps:
                if c.s.iid not in busy and c.t_run <= t_free:
                    c.prio *= 2.0
                    turn.add(c.s.iid)
        firsts = [c for c in cands if c.s.type_key in r.first]
        pool = firsts or [c for c in cands if c.s.type_key not in r.last] or cands
        need = lambda c: c.t_run + r.swing_s + r.margin_s
        slack = lambda c: (min(c.window, r.window_max_s) - need(c) + 0.05) * c.prio
        go = [c for c in pool if c.window >= need(c)]
        if old is not None and old.name == PUNISH:
            # a kept opening runs to its window's end (t_end) unless another one is clearly better
            better = [c for c in go if c.s.iid != old.target and slack(c) >= r.switch_x * old.score]
            if not better:
                return old
            go = better
            self._sw_why = "punish"
        iso = [c for c in pool if c.iso]
        if old is not None and old.name == KITE:
            # the rule's own hysteresis (round 3: RUSH <-> KITE at the 8 u edge was most of the goal changes): from
            # KITE, RUSH only on one isolated by iso_u + rule_hyst_u
            iso = [c for c in iso if c.sep >= r.iso_u + r.rule_hyst_u]
        rule = PUNISH if go else RUSH if iso else KITE
        kept = next((c for c in pool if old is not None and c.s.iid == old.target), None)
        if rule == RUSH and kept is not None and old.name == RUSH and not kept.iso and t - old.t_pick < r.dwell_s:
            rule = KITE                                   # the rushed target lost its isolation: kite with it first
        held = old is not None and rule != old.name and rule != PUNISH and t - old.t_goal < r.goal_dwell_s
        if held:
            rule = old.name                               # the kept rule runs goal_dwell_s first
        if rule == PUNISH:
            c = self._choose(go, slack, old, t, turn)
            if old is not None and c.s.iid != old.target:
                self._sw_why = "punish"
            return self._goal(ws, c, PUNISH, t, slack(c), t_end=t + c.window,
                              why=f"window {c.window:.2f} >= {need(c):.2f}")
        elig = iso + ([kept] if held and kept is not None and not kept.iso else [])
        if rule == RUSH and elig:
            spread = len(iso) == len(pool) and len(pool) > 1
            val = (lambda c: 1.0 / (0.2 + c.eta / c.prio)) if spread else (lambda c: c.prio / (c.d + 1.0))
            c = self._choose(elig, val, old, t, turn)
            return self._goal(ws, c, RUSH, t, val(c), why="spread: fastest pursuer" if spread else "isolated")
        val = lambda c: 1.0 / (0.2 + c.eta / c.prio)
        c = self._choose(pool, val, old, t, turn)
        g = self._kite(cands, c, hx, t)
        g.score = val(c)
        return g

    def _kite_spot(self, subjects, target, hx: float) -> tuple[float, str]:
        """KITE's stance (module docstring) from the enemies in play now: kite_u from the target on its side away from
        the others, or under the nearest Maestro while Tinies are in play."""
        r = self.rules
        x0, x1 = self.pb.arena_x
        cx = float(target.pos[0])
        live = [s for s in subjects if s.alive and s.in_play and s.pos is not None]
        maestros = [m for m in live if m.type_key == MAESTRO]
        if maestros and any(m.type_key == TINY for m in live):
            m = min(maestros, key=lambda m: abs(float(m.pos[0]) - hx))
            return self._clamp(float(m.pos[0])), "under the Maestro"
        others = [float(o.pos[0]) for o in live if o.iid != target.iid]
        g = float(np.mean(others)) if others else hx
        d = 1.0 if cx >= g else -1.0
        x = cx + d * r.kite_u
        if not (x0 + r.wall_room_u <= x <= x1 - r.wall_room_u):
            x = cx + (1.0 if hx >= cx else -1.0) * r.kite_u
        return self._clamp(x), "kite: fastest first"

    def _kite(self, cands: list[Cand], c: Cand, hx: float, t: float) -> Goal:
        x, why = self._kite_spot([o.s for o in cands], c.s, hx)
        return Goal(KITE, c.s.iid, x, t, 1.0 / (0.2 + c.eta), c.s.family, face_x=c.x, why=why, t_goal=t)

    def _goal(self, ws, c: Cand, name: str, t: float, score: float, t_end: float = math.inf, why: str = "") -> Goal:
        spot, vocab, how = self._spot(ws, c.s, float(ws.hero.pos.v[0]))
        return Goal(name, c.s.iid, spot, t, score, c.s.family, t_end, vocab, c.x, f"{why}; {how}", t_goal=t)

    def _status(self, fc, t: float) -> str:
        """The kept goal: "gone" (none, its target dead / out of play, a PUNISH window over or its target into another
        move: the goal ends), "event" (its target into another move: pick now, the goal may stay), else "ok"."""
        g = self.goal
        if g is None or g.target is None:
            return "gone"
        s = next((s for s in (getattr(fc, "subjects", ()) or ()) if s.iid == g.target), None)
        if s is None or not s.alive or not s.in_play or s.pos is None or t > g.t_end:
            return "gone"
        if s.family != g.family:
            return "gone" if g.name == PUNISH else "event"
        return "ok"

    # ---- decide ----

    def decide(self, ws, fc, d, h) -> GoalPrefs:
        prefs = self.local.decide(ws, fc, d, h)
        self.last = dict(self.local.last)
        self.last["goal"] = LOCAL
        r = self.rules
        if not r.enabled or prefs.mode in (HEAL, LEAVE):
            return prefs
        if r.fail_p > 0.0 and self.rng.random() < r.fail_p:
            self.stats["fails"] += 1
            return prefs
        t0 = time.perf_counter()
        try:
            out = self._decide(ws, fc, prefs)
        except Exception as ex:                           # noqa: BLE001  (L2 fails -> LOCAL, §4.4 item 4)
            self.stats["errors"] += 1
            self.last["l2_error"] = repr(ex)[:200]
            self.goal = None
            return prefs
        self.stats["ms"].append((time.perf_counter() - t0) * 1e3)
        return out

    def _decide(self, ws, fc, prefs: GoalPrefs) -> GoalPrefs:
        r = self.rules
        hx = float(ws.hero.pos.v[0])
        t = float(ws.stamp.t_game_s) if getattr(ws, "stamp", None) is not None else 0.0
        self._t = t
        for s in getattr(fc, "subjects", ()) or ():
            if s.type_key != CLAPPER or s.pos is None:
                continue
            if s.family not in (CC_JUMP, CC_JUMP_CAST):
                if self.jfam.pop(s.iid, None) == CC_JUMP_CAST and s.iid in self.aim:
                    # a jump cast just ended: its rune circle bursts later, around its landing
                    aim_x, x0, f0 = self.aim[s.iid]
                    self.rune[s.iid] = (jump_landing(x0, aim_x, f0), f0, self.jump_how.get(s.iid) or "back off",
                                        t + r.rune_hold_s)
                elif s.iid in self.rune and t > self.rune[s.iid][3]:
                    del self.rune[s.iid]
                for m in (self.jump_how, self.aim, self.antic):
                    m.pop(s.iid, None)
                continue
            self.jfam[s.iid] = s.family
            self.rune.pop(s.iid, None)
            if s.iid in self.aim:
                continue
            x = float(s.pos[0])
            e = self._ent(ws, s.iid)
            fa = clapper_facing(e) if e is not None else None
            front = float(fa) if fa is not None else (1.0 if hx >= x else -1.0)
            if s.state in CC_PRE_AIM_STATES:
                self.antic[s.iid] = x                     # standing: the take-off x
            else:
                # past its (instant) Jump Aim: aimed at the hero's x of that frame from where it stood in the antic,
                # facing as Jump Aim turned it (FaceObject; it does not turn in the air)
                self.aim[s.iid] = (hx, self.antic.get(s.iid, x), front)
        self._count_hits(ws, t)
        self.n += 1
        status = self._status(fc, t)
        if status != "ok" or self.n % r.period == 0:
            prev = self.goal
            old = prev if status != "gone" else None
            new = self._pick(ws, fc, hx, t, old)
            self.stats["picks"] += 1
            if new is not None:
                if old is not None and new.target == old.target:
                    new.t_pick, new.landed = old.t_pick, old.landed       # still that target
                    if new.name == old.name:
                        new.t_goal = old.t_goal                         # still that rule
                new.family = next(s.family for s in fc.subjects if s.iid == new.target)   # an event is handled
                if prev is None or new.target != prev.target or new.name != prev.name:
                    self.stats["changes"] += 1
                    if prev is not None and new.target == prev.target:
                        rc = self.stats["rule_changes"]           # the same target under another rule
                        k = f"{prev.name}>{new.name}"
                        rc[k] = rc.get(k, 0) + 1
                    if prev is not None and new.target != prev.target:
                        self.stats["tgt_switches"] += 1
                        self.stats["switches"] += int(old is not None)  # a kept target given up (not one gone)
                        kind = (self._sw_why or "?") if old is not None else "gone"
                        sk = self.stats["switch_kinds"]
                        sk[kind] = sk.get(kind, 0) + 1
                    if new.name == PUNISH:
                        self.stats["punish_goals"] += 1
            self.goal = new
        g = self.goal
        if g is None:
            return prefs
        if g.name == KITE and prefs.mode == EVADE:
            self.last["goal"] = f"{KITE}(EVADE)"
            self.stats["goals"][self.last["goal"]] = self.stats["goals"].get(self.last["goal"], 0) + 1
            return prefs
        # a kept goal's stance follows its target (the spot moves with it; KITE's with the others too)
        s = next((s for s in fc.subjects if s.iid == g.target), None)
        how = None
        if s is not None and s.pos is not None:
            if g.name == KITE:
                g.stance_x, how = self._kite_spot(fc.subjects, s, hx)
            else:
                g.stance_x, g.vocab, how = self._spot(ws, s, hx)
            g.why = f"{g.why.split('; ')[0]}; {how}" if "; " in g.why else how     # the controller's branch now
            g.face_x = float(s.pos[0])
        wts = dict(prefs.weights)                         # LOCAL's (Q6's silk gathering in it), EVADE's factors undone
        if prefs.mode == EVADE:
            wts["hit"] /= EVADE_HIT_X
            wts["risk"] /= EVADE_RISK_X
        for k, v in (r.weights.get(g.name) or {}).items():
            wts[k] = wts.get(k, 0.0) * float(v)
        hw = {k: (min(v, self.local.rules.other_hit_w) if v > 0 and k != g.target else v)
              for k, v in prefs.hit_w.items()}           # LOCAL's own target back to the others' weight
        if how in CC_RETREAT:
            # the Clapper controller steps away: no reward for chasing a hit on it meanwhile (round 2, v3 live: hits
            # by its slam / landing slam while stepping out or backing off, the hit weight pulling the other way)
            if hw.get(g.target, 0.0) > 0:
                hw[g.target] = 0.0
        elif g.target in hw and hw[g.target] > 0:
            hw[g.target] = max(hw[g.target], r.target_hit_w * r.priority.get(getattr(s, "type_key", ""), 1.0))
        out = replace(prefs, mode=g.name, goal=g.name, target=g.target, stance_x=float(g.stance_x),
                      boss_x=g.face_x, hit_w=hw, weights=wts, vocab=frozenset(prefs.vocab) | g.vocab)
        self.stats["goals"][g.name] = self.stats["goals"].get(g.name, 0) + 1
        self.last.update(goal=g.name, goal_why=g.why, target_type=getattr(s, "type_key", None),
                         goal_t_end=None if math.isinf(g.t_end) else round(g.t_end, 3))
        return out

    def _count_hits(self, ws, t: float) -> None:
        """Hornet's nail hits on the current goal's target (the view's HIT_DEALT events): per goal, and for PUNISH
        whether one landed inside the window it was picked for (stats punish_landed / punish_goals)."""
        g = self.goal
        if g is None:
            return
        for ev in getattr(ws, "events", ()) or ():
            if ev.kind != Ev.HIT_DEALT or ev.data.target_id != g.target:
                continue
            if ev.data.attack != "Nail" and str(ev.data.src or "") not in NAIL_SRC:
                continue
            gh = self.stats["goal_hits"]
            gh[g.name] = gh.get(g.name, 0) + 1
            if g.name == PUNISH and t <= g.t_end and not g.landed:
                g.landed = True
                self.stats["punish_landed"] += 1

    def stats_dict(self) -> dict:
        ms = self.stats["ms"]
        q = (lambda p: round(float(np.percentile(ms, p)), 3) if ms else None)
        return {k: (dict(v) if isinstance(v, dict) else v) for k, v in self.stats.items() if k != "ms"} | \
            {"ms_p50": q(50), "ms_p99": q(99), "ms_n": len(ms)}
