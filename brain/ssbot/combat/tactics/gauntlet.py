"""The Forum's L2 target layer, v0 (forum_planner_plan §5 R6, the person's rules of 2026-10-04 / 05): a few rules above
LOCAL (combat.tactics.forum_local.ForumTactics) that say whom to go for and where to stand. Not the GoalArbiter of the
plan (§4.1) yet: no fields, no BAIT / SPLIT / POCKET goals, no terminal value.

    tac = GauntletTactics(ForumTactics(pb, rules, floor_y), L2Rules.from_dict(d["forum"]["l2"]))
    prefs = tac.decide(ws, mf_forecast, decision, h)     # every tick, before ForumPlanner.tick (same call as LOCAL)

Every tick LOCAL decides first (HEAL, LEAVE, EVADE, ENGAGE, HOLD); HEAL and LEAVE stand. Otherwise L2 picks a goal
every `period` ticks and on events (the goal's target gone or out of play, a PUNISH window over or its target into
another move: the goal ends; the target into another move: a pick that may keep it). The rule (below, first that
applies) and the target are held (round 2: the round-1 A/B changed goals 33 times a minute in wave 0, forum.md §21.5):
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
          the mean speed it closes on the hero at, R0 caches, forum.md §21). Clawmaiden first (only it while it is
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
  CC_JUMP / CC_JUMP_CAST  judged every tick from where the hero and it are now (live v3 / v4, forum.md 21.7.1):
          "landing" = its x + 0.92 clamp(hero x -/+ 5 on its side - its x, +-12) (jump_landing: the true landing from
          the take-off and the hero's x at its Jump Aim, here re-estimated from the current positions: a stance rule,
          not a landing forecast); behind_land_u behind it (the slam collider and the rune slam, 6.62 u in front of
          the landing with r 7.19, reach 0.58 u behind it) when the run gets there land_margin_s before the landing
          (jump_land_s / jump_cast_land_s after the commit, clapper_face.md §1.1 p50), does not cross its body on the
          ground and the wall leaves room behind, with up slashes scored up_hit_x; else back off in front of it:
          CC_JUMP past its landing slam (0.67-7.76 u in front: jump_out_u), CC_JUMP_CAST past the rune circle too (to
          13.8 u: cast_out_u), behind it when only there is room. Round 3 tried the true landing (the aim taken on
          the first tick past the antic: Jump Aim is instant, never a tick's state) with the way round fixed there,
          then with "behind only from its back side": live, the first ran under it on 8 / 8 w7 jumps (8 body hits),
          the second was cornered at the wall by the landing slam; this rule, re-judged with the drifting estimate,
          crossed under it 1 time in 25 jumps with 0 body hits (v4).
          After a CC_JUMP_CAST (it stands at its landing) its rune circle bursts about 0.75-0.87 s after the move ends
          (rune_hold_s 1 s): until then the stance stays behind the landing (the way round went under it; not through
          its body) or out past the circle, not at its face (round 3).
  Two Clappers never attack together (Buddy Is Attacking): while one is committed, the other one, if not and its
          spot is reached before that attack can end (Subject.t_free), is the RUSH / PUNISH pick between the two
          (priority x 2, a switch at once).
What a goal sets (scores only: the planner's S / Hz / U never see prefs, §4.4 item 2): mode (the goal's name), target,
stance_x, boss_x (face it), hit_w (the target x target_hit_w x priority, 0 while the Clapper controller steps away:
CC_RETREAT; the others as LOCAL, defensive stances still negative) and the weights' factors per goal (l2.weights). LOCAL's EVADE stands against KITE when it says the hero's spot
is covered within evade_s; PUNISH and RUSH replace it (the planner's support check is the safety).
Track A (the person's tactics of 2026-10-08, GauntletTactics.ta from SSBOT_FORUM_TA; forum.md §26; off by default):
  edge   RUSH stands edge_u from the target body's edge on the hero's side (the person waits at the edge of reach).
  guard  a Minister in Parry Stance / Parry Block and a Reed in Defend / Block get hit weights by slash kind
         (GoalPrefs.hit_kw: the Minister by its height band and grouped / alone; the Reed never) and, as the goal's
         target, the stance to wait at (_guard_rule).
  whip   a Choristor in its whip (CH_WHIP: the antic and Whip 1-6; it stands still): the stance leaves the whip's reach
         (whip_back_u behind, whip_front_u in front: the whip does reach behind, Whip Hit 5-6), picks whose spot lies in
         it go last, and a whip starting or ending re-picks.
Failure (§4.4 item 4): an exception or an injected failure (fail_p) returns LOCAL's prefs untouched, so with fail_p = 1
every decision is LOCAL's bit for bit (tests/test_forum_l2.py).
"""
import math
import os
import random
import time
from dataclasses import dataclass, field, replace

import numpy as np

from ssbot.combat import jump_behind, rune_bombs, slam_play, special_board, two_play
from ssbot.combat.tactics.forum_local import (CLAPPER, EVADE_HIT_X, EVADE_RISK_X, LEAVE, ForumTactics,
                                               clapper_facing)
from ssbot.combat.tactics.modes import EVADE, HEAL, GoalPrefs
from ssbot.core.forum import FLOOR_Y
from ssbot.core.worldstate import Ev

PUNISH, RUSH, KITE, LOCAL = "PUNISH", "RUSH", "KITE", "LOCAL"
CLAWMAIDEN = "Song Handmaiden"
MAESTRO = "Song Pilgrim Maestro"
MINISTER = "Song Administrator"
TINY = "Song Automaton Tiny"
CHORISTOR = "Song Pilgrim 03"
REED = "Song Reed"
CH_WHIP = "CH_WHIP"
MINISTER_GUARD = ("Parry Stance", "Parry Block")          # Forum.yaml forum.defensive
REED_GUARD = ("Defend", "Block")
CC_IDLE, CC_SLAM, CC_JUMP, CC_JUMP_CAST, CC_CAST = "CC_IDLE", "CC_SLAM", "CC_JUMP", "CC_JUMP_CAST", "CC_CAST"
# Jump Aim (and Cast Jump) are instant: one frame goes Jump Antic / Cast Slam Antic 2 -> (Cast Jump ->) Jump Aim ->
# Jump, so the tracker never ends a tick in them (forum.md 21.7.1)
CC_AIR_STATES = ("Jump", "Air")                           # its body off the ground (a jump's flight)
CC_RETREAT = ("slam: step out", "slam: out to the wall", "jump: back off", "rune: out",  # branches that step away
              "slam: outside")
# SSBOT_FORUM_JUMP_BEHIND: the branches whose target's hits do not count (GoalPrefs.no_hit)
JB_NO_HIT = ("jump: aim stance", "jump: under and behind (antic)", "jump: under and behind (flight)", "jump: back off",
             "rune: out")
# ... and the branches whose target's hits count from the ground only (GoalPrefs.ground_hit; SP4's labels exist only
# with their switches: the flight with JB_PASS, the fall with JB_LAND, the cast antic with JB_CAST_ANTIC, the slam's
# recovery with SLAM_AFTER); JB_NOJUMP's ground-first branches (GoalPrefs.ground_first)
JB_GROUND_HIT = ("jump: under and behind (landed)", "rune: behind", "jump: under and behind (flight)",
                 "jump: under and behind (falling)", "jump: cast antic slash", "slam: after")
JB_GROUND_FIRST = ("jump: under and behind (landed)", "jump: under and behind (falling)", "rune: behind")
# SP4 (SLAM_PLAY_NODASH / _NOPOGO): the families in which the Clapper can start an attack any frame. The tracker's
# subject reads CC_IDLE for the whole Idle / Walk (EnemyTracker.enter: a decision state starts the idle family): SP3's
# ground_hit checked (None, CC_EVADE) only (SP4 t3: no ground_hit while it idled after a small rune cast; the pogo
# counted 2 landed hits)
SP4_IDLE_FAMS = (None, "CC_EVADE", CC_IDLE)
# SSBOT_FORUM_TWO_FOCUS (task 1v1 SP7, default off; forum.md 71): with two Clappers in play (and nobody else), L2's
# goal is RUSH on the focus (GauntletTactics._two_focus), never KITE (SP7's baseline: 8 of 8 w13 episodes QUIT at 1 HP,
# most hits under KITE(EVADE) with the hero in the air)
TWO_FOCUS = os.environ.get("SSBOT_FORUM_TWO_FOCUS", "0").strip() == "1"
TWO_HYST_U = 1.0            # a switch needs the other one this much more room to its outer wall (u)
TWO_CLOSE_U = 7.0           # ... and her within this of its centre in time (inside its Slam Range, 8.05 u)
TWO_RUN_U_S = 8.25          # ... at the run speed (u/s; the dash is ranked down near an idle Clapper, NODASH)
TWO_IDLE_S = 0.6            # ... before this long into its idle after an attack move (0.65 s without a buddy busy)
TWO_RUNE_S = 0.2            # no switch onto it until this past its rune hold (a jump cast's circle in front of it)
TWO_ATTACK_FAMS = (CC_SLAM, CC_CAST, CC_JUMP, CC_JUMP_CAST)
# SSBOT_FORUM_TWO_JUMPER (SP7, default off; with TWO_FOCUS): a Clapper in a jump move (or its rune circle still to burst)
# is the target meanwhile (GauntletTactics._two_focus)
TWO_JUMPER = os.environ.get("SSBOT_FORUM_TWO_JUMPER", "0").strip() == "1"
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
    up_hit_x: float = 1.5                                 # the Clapper in the air: its hit weight's extra factor
    face_u: float = 4.0                                   # the Clapper: face-hit distance (2.5-5.4 u, clapper_face §2)
    slam_out_u: float = 13.0
    slam_behind_u: float = 3.5
    behind_land_u: float = 2.5
    jump_land_s: float = 1.415                            # CC_JUMP: commit -> landing (clapper_face §1.1 p50)
    jump_cast_land_s: float = 1.85                        # CC_JUMP_CAST
    land_margin_s: float = 0.25                           # behind the landing this long before it lands
    jump_out_u: float = 8.5                               # CC_JUMP: in front of the landing past its slam (7.76 u)
    corner_room_u: float = 13.0                           # CC_JUMP: "under and behind" only with this much room to
    #                                                       the wall behind the hero there (1v1 live, forum.md 44: a
    #                                                       slam with < 8 u behind the hero hit 61 %; 0: off)
    cast_out_u: float = 14.5                              # CC_JUMP_CAST: past the rune circle (6.62 + 7.19 u)
    rune_hold_s: float = 1.0                              # CC_JUMP_CAST's rune circle: off this long after the move
    below: tuple = ("Pilgrim 03 Song", "Song Reed", "Song Administrator", MAESTRO)
    priority: dict = field(default_factory=dict)          # type_key -> factor (Clawmaiden first, Minister last)
    first: tuple = (CLAWMAIDEN,)                          # while one is in play, only these are picked
    last: tuple = (MINISTER,)                             # picked only when nobody else is in play
    pursuit_u_s: dict = field(default_factory=dict)       # type_key -> u/s
    weights: dict = field(default_factory=dict)           # goal -> {weight name: factor}
    fail_p: float = 0.0                                   # injected failures (§4.4 item 4)
    # track A (2026-10-08, the person's tactics; GauntletTactics.ta, SSBOT_FORUM_TA; forum.md §26)
    edge_u: float = 2.7                                   # "edge": RUSH stands this far from the target body's edge
    #                                                       (the Wanderer side slash reaches 3.12 u from the hero's
    #                                                       centre, less 0.4 u)
    whip_front_u: float = 9.3                             # "whip": the whip's reach in front of the Choristor's
    #                                                       transform (Whip Hit 1-4 to 8.75 u) + the hero's half-width
    #                                                       + 0.3 u
    whip_back_u: float = 5.3                              # ... behind it (Whip Hit 5-6 sweep over its head to 4.75 u
    #                                                       behind: the whip does reach behind)
    whip_prio_x: float = 0.2                              # a pick whose spot is in a whip's reach: its priority x this
    guard_low_y: float = 4.5                              # "guard": a Minister's stance whose transform is lower than
    #                                                       this above the floor reaches a standing hero (its stance
    #                                                       collider's bottom 2.14 u below it; the hero box 2.08 tall
    #                                                       + 0.3 u): low, no up slash
    guard_mid_y: float = 5.2                              # ... lower than this its counter (ParrySlash Hit 1-4, down to
    #                                                       2.8 u below it) reaches a standing hero: mid, one up slash
    #                                                       and the clash; higher: two up slashes
    guard_reach_y: float = 8.2                            # ... higher than this a small jump's up slash does not reach it

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
    # SSBOT_FORUM_L2_SET="face_u=3,slam_out_u=8": numeric rule fields for an A/B (the 1v1 runs, forum.md 44)
    import os
    for kv in os.environ.get("SSBOT_FORUM_L2_SET", "").replace(";", ",").split(","):
        if "=" in kv:
            k, v = (x.strip() for x in kv.split("=", 1))
            if not isinstance(getattr(r, k, None), (int, float)) or isinstance(getattr(r, k), bool):
                raise ValueError(f"SSBOT_FORUM_L2_SET: {k!r} is not a numeric L2Rules field")
            setattr(r, k, type(getattr(r, k))(float(v)))
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
        self.t_commit: dict[int, float] = {}              # Clapper iid -> game time its current jump was first seen
        self.jump_how: dict[int, str] = {}                # Clapper iid -> its jump's way round (the last tick's)
        self.jfam: dict[int, str] = {}                    # Clapper iid -> the jump family it is in
        self.rune: dict[int, tuple] = {}                  # Clapper iid -> (landing, facing, way round, until): a jump
                                                          # cast's rune circle still to burst
        self._t = 0.0                                     # the tick's game time
        self.stats = _new_stats()
        self.last: dict = {}
        self.ta: frozenset = frozenset()                  # track A's tokens (combat.forum_planner.TA_TOKENS): "whip",
        #                                                   "guard", "edge" are read here (the policy sets them)
        self._whips: frozenset = frozenset()              # iids of the Choristors whipping on the last tick
        self._strike: dict[int, tuple[float, float]] = {}  # Clapper iid -> (game time, x) of the last "slam: strike"
        self.jb_land: dict[int, tuple[float, float]] = {}  # SSBOT_FORUM_JUMP_BEHIND: Clapper iid -> (landing x, facing)
        #                                                    of its jump, from the first tick past the antic
        self._two_fam: dict[int, str | None] = {}         # SP7: Clapper iid -> its family on the last tick
        self._two_idle: dict[int, float] = {}             # SP7: Clapper iid -> game time it went idle after an attack
        self._sp9_fam: dict = {}                          # SP9a TWO_SPACE: Clapper iid -> its family on the last tick

    @property
    def xs(self):
        return self.local.xs

    def reset(self) -> None:
        """A new episode: no goal, no stored aims, the per-episode counters cleared."""
        self.goal, self.n, self.t_commit, self.jump_how = None, 0, {}, {}
        self.jfam, self.rune = {}, {}
        self._whips = frozenset()
        self._strike = {}
        self.jb_land = {}
        self._two_fam, self._two_idle = {}, {}
        self._sp9_fam = {}                                # SP9a TWO_SPACE: Clapper iid -> its family on the last tick
        self._n_clappers = 0                              # SP8b JB_CORNER: live Clappers in play this tick
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
        if fam != CC_SLAM:
            self._strike.pop(s.iid, None)
        mb = _map_board(s.iid)
        if fam == CC_SLAM and mb is not None and mb.get("x") is not None:
            # SSBOT_FORUM_SPECIAL_MAP (SG4): the map row's spot (its press or 10 frames ahead), else the map's best
            # ground spot near the hero; not slam_out_u (13 u: readiness 0.3, no strike)
            return self._clamp(float(mb["x"])), frozenset(), "slam: map " + ("row" if mb.get("on") else "ground")
        if fam == CC_SLAM:
            if special_board.L2_ON:
                # the person's general special rule (combat.special_mode): the planner found a strike on this slam
                # safe from every other enemy on its last tick: stand at its press point (a hit target, not a retreat)
                b = special_board.BOARD.get(s.iid)
                if b is not None and b.get("on") and b.get("x") is not None:
                    self._strike[s.iid] = (self._t, float(b["x"]))
                    return self._clamp(float(b["x"])), frozenset(), "slam: strike"
                held = self._strike.get(s.iid)
                if held is not None and 0.0 <= self._t - held[0] <= special_board.L2_HOLD_S:
                    # review 2026-10-12: the planner's safe strike flickers off for a tick or two while the slam goes on
                    # (open-loop replay: a median 4 on / off flips a slam, a third of the on runs 1-2 ticks long, the
                    # stance jumping 5 <-> 13 u): the last strike spot is kept L2_HOLD_S (a preference only: the
                    # normal rows keep the slam's danger)
                    return self._clamp(held[1]), frozenset(), "slam: strike (held)"
            if side != front:
                return self._clamp(x - front * r.slam_behind_u), frozenset(), "slam: stay behind"
            if slam_play.AFTER:
                # SSBOT_FORUM_SLAM_AFTER (task 1v1 SP4, the person: never run away from a slam): a slam the playbook
                # did not take, the hero in front: in Slam 2 (the lunge over; Slam Collider 2 reaches 7.76 u in front
                # of it at her height) just outside its reach, then in the recovery (the hammer off) back into slash
                # reach of its front edge (3.49 u to frame 67, then 2.25 u), ground hits counting
                if s.state == "Slam Recover":
                    return self._clamp(x + front * slam_play.AFTER_U), frozenset(), "slam: after"
                if s.state in ("Slam 2", "Slam Effects?"):
                    return self._clamp(x + front * slam_play.OUTSIDE_U), frozenset(), "slam: outside"
            if _sg8_on():
                # SSBOT_FORUM_SG8 (forum.md 64; the person: never run away from a slam): no map spot this tick (no
                # map for this slam, no finite ground value near): at its face, the hit weight kept (the planner's
                # checks keep the hammer's danger; slam_out_u's 13 u was 24 % of the live slam ticks)
                from ssbot.combat import forum_map
                return self._clamp(x + front * forum_map.FACE_U), frozenset(), "slam: face (no map)"
            out = x + front * r.slam_out_u
            if room(out):
                return out, frozenset(), "slam: step out"
            # behind it means through its body on the ground (round 2, live w13: 7 body hits that way): as far out
            # as the wall lets (the hammer reaches 12 u in front: the farther the likelier it misses)
            return self._clamp(out), frozenset(), "slam: out to the wall"
        if fam in (CC_JUMP, CC_JUMP_CAST) and jump_behind.ENABLED:
            return self._jump_behind(ws, s, x, hx, front, side, fam)
        if fam in (CC_JUMP, CC_JUMP_CAST):
            land = jump_landing(x, hx, front)              # from where both are now (module docstring)
            behind = land - front * r.behind_land_u
            out = land + front * (r.jump_out_u if fam == CC_JUMP else r.cast_out_u)
            t = self._t
            t_land = (r.jump_land_s if fam == CC_JUMP else r.jump_cast_land_s) - (t - self.t_commit.get(s.iid, t))
            t_run = r.start_s + abs(behind - hx) / r.run_u_s
            # the stance past its body while it is still on the ground: the run would go through it
            through = s.state not in CC_AIR_STATES and (behind - x) * (hx - x) < 0
            back = -front                                 # the hero ends past the landing on its back side
            wall_room = (behind - xa) if back < 0 else (xb - behind)
            # a jump cast's rune circle covers the landing's front (-0.7 to 13.8 u): behind it stays the way round
            cornered = r.corner_room_u > 0 and fam == CC_JUMP and wall_room < r.corner_room_u
            if room(behind) and t_run <= t_land - r.land_margin_s and not through and not cornered:
                how = "under and behind"
            elif room(out) or not room(behind):
                how = "back off"
            else:
                how = "under and behind (no room out)"
            self.jump_how[s.iid] = how                    # the last way round (a jump cast's rune circle after it)
            return self._clamp(behind if how.startswith("under") else out), frozenset(), f"jump: {how}"
        rp = self.rune.get(s.iid)
        if rp is not None and fam != CC_SLAM and self._t <= rp[3]:
            # a jump cast's rune circle (6.62 u in front of the landing, r 7.19: from 0.58 u behind it to 13.8 u in
            # front) bursts about 0.75-0.87 s after the move ends (its tail, ChoirClapper.json): the face (4 u in
            # front) is inside it. Stay behind the landing (where the way round went, not through its body) or out
            # past it (round 3: v4 w7 took 20 of its hits there, the controller back at the face)
            land, f0, how, _ = rp
            if jump_behind.ENABLED:
                # SSBOT_FORUM_JUMP_BEHIND (SP3): BACK_U behind the landing (behind_land_u 2.5 u is inside the reach of
                # its body turning at Idle: 2.25 u + the hero's half width), inside the walls by the module's pad; the
                # side by where the hero is from the landing (the circle), not from the Clapper now (trial 2: it backed
                # off past the landing's back spot and "behind" sent her back through the circle as it burst):
                # behind the landing -> stay behind; in front -> the nearer way out of the circle (its back edge 0.71
                # u behind the landing, its front 13.7 u in front), not past its body
                jb_spot = jump_behind.behind_spot(land, f0)
                out = self._clamp(land + f0 * r.cast_out_u)
                rel = (hx - land) * f0
                if jb_spot is not None and rel < -0.5:
                    return jb_spot, frozenset(), "rune: behind"
                if jb_spot is not None and abs(hx - jb_spot) < abs(hx - out) and not min(hx, jb_spot) < x < max(hx, jb_spot):
                    return jb_spot, frozenset(), "rune: behind"
                return out, frozenset(), "rune: out"
            behind = land - f0 * r.behind_land_u
            out = land + f0 * r.cast_out_u
            through = (behind - x) * (hx - x) < 0
            if room(behind) and not through and (how.startswith("under") or not room(out)):
                return behind, frozenset(), "rune: behind"
            return self._clamp(out), frozenset(), "rune: out"
        vocab = frozenset({GLIDE_SPIKE}) if fam == CC_CAST else frozenset()
        if fam != CC_CAST and _chase_on() and _chase_ok(mb, x, hx):
            # SSBOT_FORUM_CHASE (SG5): idle / walk, the evade (chase at once: it ends in its next move), the entry: a
            # slash stance in reach on the hero's side, the map's readiness argmax inside forum_map.CHASE_BAND (a slam
            # starting then leaves two strikes with full clearance), else CHASE_U. Review: only where the map handles
            # a slam it starts now (_chase_ok); elsewhere the branches below as in rnmap
            if mb is not None and mb.get("chase_x") is not None:
                return self._clamp(float(mb["chase_x"])), vocab, "chase: ready"
            return self._clamp(x + side * CHASE_U), vocab, "chase"
        if fam != CC_CAST and mb is not None and mb.get("ready_x") is not None:
            # SG4: before a slam can start, the readiness argmax 3-6 u in front (the map at k = 0)
            return self._clamp(float(mb["ready_x"])), vocab, "face: ready"
        if slam_play.STANCE_U > 0 and fam in (None, "CC_EVADE"):
            # SSBOT_FORUM_SLAM_PLAY_STANCE (task 1v1 SP1, rnplay6): while it idles / walks / backsteps, on the ground
            # this far in front (the person's band at the antic entry, 6.2 u; it picks the slam 74 % of the time at
            # 5.4-8 u): a slam it starts finds the playbook's start
            return self._clamp(x + side * slam_play.STANCE_U), vocab, "face: slam stance"
        if fam == CC_CAST and rune_bombs.FACE_U is not None:
            # SSBOT_FORUM_RUNE_FACE (task 1v1 G2, the why study's fix (6)): through the small runes on the ground
            # 3-4 u from it, where only ring 1 reaches (ring 0 ends 2.4 u out): one short hop clears it
            return self._clamp(x + side * rune_bombs.FACE_U), vocab, "rune: face"
        return self._clamp(x + side * r.face_u), vocab, "face"

    def _jump_behind(self, ws, s, x: float, hx: float, front: float, side: float, fam: str
                     ) -> tuple[float, frozenset, str]:
        """SSBOT_FORUM_JUMP_BEHIND (task 1v1 SP3, combat.jump_behind): the stance during a jump move. Antic: AIM_U in
        front (it jumps in place); past the antic: BACK_U behind the landing - stored on the first tick past the antic
        from its take-off x and its vx (the first Air frame's; before that the hero's x ~ hers at its Jump Aim), the
        wall rule, then never short of where it is now along the jump (a jump into the wall-top ledge is pushed out);
        on Slam 2 / Slam Recover behind its own x. No room behind (the landing < min_back_u + wall_pad_u from the wall
        behind it): the old back-off in front past its landing slam / rune circle."""
        r = self.rules
        jb = jump_behind
        st = s.state
        rec = self.jb_land.get(s.iid)
        if st in jb.ANTIC_STATES or (rec is None and st not in jb.AIR_STATES + jb.LANDED_STATES):
            self.jb_land.pop(s.iid, None)
            if (jb.CAST_ANTIC and fam == CC_JUMP_CAST and side == front and st in ("Cast Slam Antic", "Cast Slam Antic 2")
                    and self._t - self.t_commit.get(s.iid, self._t) < jb.CFG["cast_slash_s"]):
                # SSBOT_FORUM_JB_CAST_ANTIC (SP4, the person: "during the big rune's antic you can stand in front of it
                # and slash at least twice"): in slash reach in front, ground hits counting, then the aim stance
                self.jump_how[s.iid] = "under and behind"
                return self._clamp(x + front * jb.CFG["cast_u"]), frozenset(), "jump: cast antic slash"
            if side != front:
                # behind it already at the antic (it faces the hero at the antic start: she crossed during it)
                spot = jb.behind_spot(x, front)
                if spot is not None:
                    self.jump_how[s.iid] = "under and behind"
                    return spot, frozenset(), "jump: under and behind (antic)"
            self.jump_how[s.iid] = "under and behind"
            if jb.CORNER and getattr(self, "_n_clappers", 0) == 1 and jb.corner_room(x, front) < jb.CFG["push_from_u"]:
                # SSBOT_FORUM_JB_CORNER (SP8b): at a wall stay in reach through the antic (cast_stab slashes, then its
                # way under from the take-off) instead of backing off to aim_wall_u
                return self._clamp(x + front * jb.CFG["corner_aim_u"]), frozenset(), "jump: aim stance (corner)"
            return jb.aim_spot(x, front), frozenset(), "jump: aim stance"
        e = self._ent(ws, s.iid)
        vel = getattr(e, "vel", None) if e is not None else None
        vx = float(vel.v[0]) if (vel is not None and getattr(vel, "conf", 0) > 0) else None
        if rec is None:
            # (take-off x, facing, landing, from vx): the hero's x now stands for hers at its Jump Aim (1-2 frames ago)
            rec = (x, front, jb.landing(x, hx, front), False)
        x0, f0, land, by_v = rec
        if not by_v and st == "Air" and vx is not None and abs(vx) > 0.05:
            land, by_v = jb.landing_v(x0, vx, f0), True   # the decided vx (attack_range's jump_rule does the same)
        if st in jb.AIR_STATES and (x - x0) * f0 > 0.05 and (x - land) * f0 > 0:
            land = x                                      # pushed out past the estimate (the wall-top ledge): forward
            #                                               of its take-off and of the estimate
        self.jb_land[s.iid] = (x0, f0, land, by_v)
        phase = "flight"
        if jb.LAND_HIT and st == "Air" and vel is not None and getattr(vel, "conf", 0) > 0 and float(vel.v[1]) < 0:
            phase = "falling"                             # SSBOT_FORUM_JB_LAND (SP4): past its apex, hits count
        if st in jb.LANDED_STATES:
            land, phase = x, "landed"                     # it stands at its landing (a hit pushes it 0.24-1.44 u)
        spot = jb.behind_spot(land, f0)
        if jb.CFG["herd"] and jb.corner_room(x0, f0) >= jb.CFG["push_from_u"]:
            # SP8b trial only (SSBOT_FORUM_JUMP_BEHIND_SET=herd=1, the corner start state): away from a wall back off
            # instead of going behind - she stays on one side, its evades pin it at the wall behind it, and its jumps
            # there (an Escape Jump when an evade meets the wall) are the corner case
            spot = None
        if spot is None:
            out = land + f0 * (r.jump_out_u if fam == CC_JUMP else r.cast_out_u)
            self.jump_how[s.iid] = "back off"
            return self._clamp(out), frozenset(), "jump: back off"
        self.jump_how[s.iid] = "under and behind"
        return spot, frozenset(), f"jump: under and behind ({phase})"

    # ---- track A (2026-10-08, the person's tactics; forum.md §26) ----

    @staticmethod
    def _body(fc, s) -> tuple[float, float]:
        """(centre x, half-width) of an enemy's body (its tracker's export box; the transform and 0.8 u without)."""
        tr = (getattr(getattr(fc, "_fc", None), "trackers", None) or {}).get(s.iid)
        b = getattr(tr, "body", None)
        if b is not None and len(b) >= 4 and b[2] >= b[0]:
            return 0.5 * (float(b[0]) + float(b[2])), 0.5 * (float(b[2]) - float(b[0]))
        return float(s.pos[0]), 0.8

    def _edge_spot(self, fc, s, hx: float) -> float:
        """"edge" (forum.md 25.6: the person waits at the edge of reach; RUSH's stance was the target's x): the body's
        edge on the hero's side + edge_u (the other side when the wall leaves no room)."""
        r = self.rules
        cx, half = self._body(fc, s)
        side = 1.0 if hx >= cx else -1.0
        x0, x1 = self.pb.arena_x
        x = cx + side * (half + r.edge_u)
        if not (x0 + r.wall_room_u <= x <= x1 - r.wall_room_u):
            x = cx - side * (half + r.edge_u)
        return self._clamp(x)

    def _whip_zones(self, ws, fc) -> list[tuple[int, float, float, float, float]]:
        """"whip": (iid, lo, hi, x, facing) of every Choristor in its whip (CH_WHIP: the 0.82 s antic, Whip 1-6), the x
        span its whip reaches (whip_front_u in front, whip_back_u behind; it stands still while whipping)."""
        r = self.rules
        out = []
        for s in getattr(fc, "subjects", ()) or ():
            if not (s.alive and s.in_play and s.pos is not None and s.type_key == CHORISTOR and s.family == CH_WHIP):
                continue
            e = self._ent(ws, s.iid)
            fa = clapper_facing(e) if e is not None else None      # flipX: the Forum sprites face -x unflipped
            x = float(s.pos[0])
            face = float(fa) if fa is not None else (1.0 if float(ws.hero.pos.v[0]) >= x else -1.0)
            a, b = x - face * r.whip_back_u, x + face * r.whip_front_u
            out.append((s.iid, min(a, b), max(a, b), x, face))
        return out

    def _guard_rule(self, m, subs, w_pos: float, hx: float, fc) -> tuple[tuple | None, float | None, str]:
        """"guard" for one enemy (the person's Minister / Reed defence rules, forum_planner_plan sec. 5 notes of
        2026-10-08): ((side, up, wall, down) hit weights, the stance when it is the goal's target, label), or (None,
        None, "") when it is not guarding. Minister in Parry Stance / Parry Block (no turning, no damage in the stance,
        Parry Block 0.583 s is hittable, the counter is one forward lunge, ParrySlash Hit 1-4 its segments): by its
        height (guard_low_y / guard_mid_y / guard_reach_y) and whether another enemy is within iso_u (grouped: trigger
        it to split the group; alone: wait, or the down slash / harpoon trigger). Side / wall slashes never (its
        counter lunges level). Low: no up slash (its body reaches the hero), the down slash from above (grouped or
        alone); wait in reach (the edge spot). Mid: one up slash in the stance when grouped, the down slash, none in
        Parry Block (the swing is kept for the clash on the lunge); under it. High: up slashes when grouped and in
        Parry Block (its counter passes above); under it. Out of reach: wait. Reed in Defend / Block (Defend 1.0 s, Block 0.516 s, its counter aims at the hero's
        height): never trigger it from anywhere; wait in reach (the edge spot) for Defend to end, or clash its counter
        (the planner's clash branch)."""
        r = self.rules
        neg = self.local.rules.defensive_hit_w
        if m.type_key == MINISTER and m.state in MINISTER_GUARD:
            ey = float(m.pos[1]) - FLOOR_Y
            band = "low" if ey < r.guard_low_y else "mid" if ey < r.guard_mid_y else "high" \
                if ey <= r.guard_reach_y else "out"
            grouped = any(o.iid != m.iid and abs(float(o.pos[0]) - float(m.pos[0])) < r.iso_u for o in subs)
            block = m.state == "Parry Block"
            up = down = neg
            if band == "high" and (grouped or block):
                up = w_pos
            elif band == "mid":
                up = 0.0 if block else (w_pos if grouped else neg)
            if band in ("low", "mid") and not block:
                down = w_pos                  # from above (a full jump's down slash reaches 4.3 u): its lunge is level
            stance = self._edge_spot(fc, m, hx) if band == "low" else self._clamp(float(m.pos[0]))
            return (neg, up, neg, down), stance, f"guard {band} {'grouped' if grouped else 'alone'}"
        if m.type_key == REED and m.state in REED_GUARD:
            return (neg, neg, neg, neg), self._edge_spot(fc, m, hx), "guard reed: wait"
        return None, None, ""

    def _ta_rules(self, ws, fc, prefs: GoalPrefs, g: Goal, s, hx: float) -> tuple[GoalPrefs, list]:
        """Track A's L2 rules on the goal's prefs (scores only): edge, guard, whip (in this order; the whip's stance
        last: out of a whip's reach wins)."""
        r = self.rules
        ta = self.ta
        why = []
        stance = float(prefs.stance_x)
        hw = dict(prefs.hit_w)
        kw = dict(prefs.hit_kw)
        subs = [x for x in (getattr(fc, "subjects", ()) or ()) if x.alive and x.in_play and x.pos is not None]
        if "edge" in ta and g.name == RUSH and s is not None and s.pos is not None and s.type_key != CLAPPER:
            stance = self._edge_spot(fc, s, hx)
            why.append("edge")
        if "guard" in ta:
            for m in subs:
                tgt = s is not None and m.iid == s.iid
                w_pos = r.target_hit_w * r.priority.get(m.type_key, 1.0) if tgt else self.local.rules.other_hit_w
                w4, st, lab = self._guard_rule(m, subs, w_pos, hx, fc)
                if w4 is None:
                    continue
                kw[m.iid] = w4
                if tgt and g.name != KITE:
                    stance = st
                why.append(lab)
        if "whip" in ta and g.name != PUNISH:          # a PUNISH spot is clear of the support (the whip's included)
            x0, x1 = self.pb.arena_x
            for _, lo, hi, x, face in self._whip_zones(ws, fc):
                if lo <= stance <= hi:
                    outs = [v for v in (x - face * r.whip_back_u, x + face * r.whip_front_u)
                            if x0 + r.wall_room_u <= v <= x1 - r.wall_room_u]
                    if outs:
                        stance = min(outs, key=lambda v: abs(v - hx))
                        why.append("whip: out of its reach")
        if not why:
            return prefs, why
        return replace(prefs, stance_x=float(stance), hit_w=hw, hit_kw=kw), why

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
        if "whip" in self.ta and out:
            # a target whose spot is in a whipping Choristor's reach (that Choristor included) is picked last: the
            # person's "switch to a target out of the whip's reach" (it stands still while whipping)
            zones = self._whip_zones(ws, fc)
            for c in out:
                if any(lo <= c.spot <= hi for _, lo, hi, _, _ in zones):
                    c.prio *= r.whip_prio_x
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
        if TWO_FOCUS and len(cands) == 2 and all(c.s.type_key == CLAPPER for c in cands):
            return self._two_focus(ws, cands, t, old)
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

    # ---- SP7: two Clappers (SSBOT_FORUM_TWO_FOCUS) ----

    def _outer_room(self, c: Cand, o: Cand) -> float:
        """The room from a Clapper's centre to the wall on its side away from the other one (u): its evade backs off
        that way when the hero stands between them, and inside 6 u of that wall the evade becomes an escape jump."""
        x0, x1 = self.pb.arena_x
        return (c.x - x0) if c.x < o.x else (x1 - c.x)

    def _two_run_ok(self, f: Cand, o: Cand, t: float) -> tuple[bool, str]:
        """The person's second switch condition: the other one will not jump while she runs to it - it cannot start a
        move while the focus is committed (Buddy Is Attacking) and she gets within TWO_CLOSE_U of it before the focus's
        move can end, or it has just ended a move (TWO_IDLE_S into its idle family: the idle lasts 0.65-1.15 s before
        it decides, and within 8 u it decides a close move) and she gets there in time. Never into a jump move or onto
        a rune circle still to burst in front of it (the plan's 10-11 note: ~1.2 s after a jump cast's landing)."""
        if o.s.family in (CC_JUMP, CC_JUMP_CAST):
            return False, "other jumping"
        rp = self.rune.get(o.s.iid)
        if rp is not None and t <= rp[3] + TWO_RUNE_S:
            return False, "other's rune circle"
        need = max(0.0, o.d - TWO_CLOSE_U) / TWO_RUN_U_S
        if f.s.committed and need <= float(getattr(f.s, "t_free", 0.0) or 0.0):
            return True, "focus committed"
        t0 = self._two_idle.get(o.s.iid)
        if o.s.family in (None, CC_IDLE) and t0 is not None and (t - t0) + need <= TWO_IDLE_S:
            return True, "other just ended a move"
        return False, "other free"

    def _two_focus(self, ws, cands: list[Cand], t: float, old: Goal | None) -> Goal:
        """SSBOT_FORUM_TWO_FOCUS (task 1v1 SP7, the person's strategy of 2026-10-16): the goal is RUSH on the focus -
        the Clapper farther from the wall on its side away from the other one (then its face stance, 4 u on the hero's
        side, is between them; close, it decides close moves: slam / small runes / evade, not the jumps of 8 u and
        beyond); the focus switches to the other one only when it has more room (by TWO_HYST_U) AND it will not jump
        while she runs to it (_two_run_ok). Never KITE."""
        a, b = cands
        room = {a.s.iid: self._outer_room(a, b), b.s.iid: self._outer_room(b, a)}
        keep = next((c for c in cands if old is not None and c.s.iid == old.target), None)
        st = self.stats.setdefault("sp7", {})
        if two_play.SPACE:
            # SSBOT_FORUM_TWO_SPACE (SP9a S5, switch answer 2f / human_two R6): one of them in its Slam Antic with the
            # two < 16 u apart - its hammer covers the ground by the other one (HP lost 8 / 8 within 4 u of the other
            # one): the slammer is the target for this slam (strike it; the playbook takes it when it can start)
            sl = [c for c in cands if c.s.family == CC_SLAM and getattr(c.s, "state", None) == "Slam Antic"]
            if len(sl) == 1 and abs(a.x - b.x) < 16.0:
                c = sl[0]
                if keep is None or keep.s.iid != c.s.iid:
                    st["slammer"] = st.get("slammer", 0) + 1
                    self._sw_why = "two slammer" if keep is not None else self._sw_why
                st["picks"] = st.get("picks", 0) + 1
                return self._goal(ws, c, RUSH, t, 1.0, why=f"two: slammer; room {room[c.s.iid]:.1f}")
        if TWO_JUMPER:
            # SSBOT_FORUM_TWO_JUMPER (t1: an other one's jump cast landed 5.27 u in front of her, its rune circle over
            # the focus's front, the focus slammed: 8 of 41 slams not struck, 6 rune hits): a Clapper in a jump move or
            # with its rune circle still to burst is the goal's target (the 1v1's way round: under it and behind its
            # landing, the rune hold) - the plan's 10-11 note "go under it to its other side, it becomes the focus"
            jm = [c for c in cands if c.s.family in (CC_JUMP, CC_JUMP_CAST)
                  or (c.s.iid in self.rune and t <= self.rune[c.s.iid][3])]
            if jm:
                j = min(jm, key=lambda c: (c.s.family not in (CC_JUMP, CC_JUMP_CAST), c.d))
                if keep is None or j.s.iid != keep.s.iid:
                    st["jumper"] = st.get("jumper", 0) + 1
                    self._sw_why = "two jumper" if keep is not None else self._sw_why
                st["picks"] = st.get("picks", 0) + 1
                return self._goal(ws, j, RUSH, t, 1.0, why=f"two: jumper; room {room[j.s.iid]:.1f}")
        if keep is None:
            f = max(cands, key=lambda c: (room[c.s.iid], -c.d))
            why = "two: focus"
            self._sw_why = None if old is None else "ineligible"
        else:
            o = b if keep is a else a
            ok2, how = self._two_run_ok(keep, o, t)
            if room[o.s.iid] > room[keep.s.iid] + TWO_HYST_U and ok2:
                f, why = o, f"two: switch ({how})"
                self._sw_why = "two"
                st["switch"] = st.get("switch", 0) + 1
                st[f"switch_{how}"] = st.get(f"switch_{how}", 0) + 1
            else:
                f, why = keep, "two: keep" + ("" if room[o.s.iid] <= room[keep.s.iid] + TWO_HYST_U else f" ({how})")
        st["picks"] = st.get("picks", 0) + 1
        return self._goal(ws, f, RUSH, t, 1.0, why=f"{why}; room {room[f.s.iid]:.1f}")

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
        self._n_clappers = sum(1 for x in (getattr(fc, "subjects", ()) or ())
                               if x.type_key == CLAPPER and x.alive and x.in_play and x.pos is not None)
        for s in getattr(fc, "subjects", ()) or ():
            if s.type_key != CLAPPER or s.pos is None:
                continue
            if TWO_FOCUS:
                # SP7: when it went idle after an attack move (the switch rule's "it has just ended a move")
                if s.family in (None, CC_IDLE) and self._two_fam.get(s.iid) in TWO_ATTACK_FAMS:
                    self._two_idle[s.iid] = t
                elif s.family not in (None, CC_IDLE):
                    self._two_idle.pop(s.iid, None)
                self._two_fam[s.iid] = s.family
            if s.family not in (CC_JUMP, CC_JUMP_CAST):
                if self.jfam.pop(s.iid, None) == CC_JUMP_CAST:
                    # a jump cast just ended: it stands at its landing, and its rune circle bursts later in front
                    e = self._ent(ws, s.iid)
                    fa = clapper_facing(e) if e is not None else None
                    x = float(s.pos[0])
                    f0 = float(fa) if fa is not None else (1.0 if hx >= x else -1.0)
                    if jump_behind.ENABLED and s.iid in self.jb_land:
                        # SP3: the circle lies in front of the jump's facing; at Idle it turns to a hero behind it (the
                        # person's demo, the recordings' Idle body), so the jump's own facing
                        f0 = self.jb_land[s.iid][1]
                    self.rune[s.iid] = (x, f0, self.jump_how.get(s.iid) or "back off", t + r.rune_hold_s)
                elif s.iid in self.rune and t > self.rune[s.iid][3]:
                    del self.rune[s.iid]
                for m in (self.t_commit, self.jump_how):
                    m.pop(s.iid, None)
                if jump_behind.ENABLED:
                    self.jb_land.pop(s.iid, None)
                continue
            self.jfam[s.iid] = s.family
            self.rune.pop(s.iid, None)
            self.t_commit.setdefault(s.iid, t)
        self._count_hits(ws, t)
        self.n += 1
        status = self._status(fc, t)
        if two_play.SPACE and TWO_FOCUS and status == "ok" and self.goal is not None:
            # SP9a S5: the other one entering its slam is an event (the slammer rule picks at once)
            for x in getattr(fc, "subjects", ()) or ():
                if (x.type_key == CLAPPER and x.iid != self.goal.target and x.family == CC_SLAM
                        and self._sp9_fam.get(x.iid) != CC_SLAM):
                    status = "event"
        if two_play.SPACE:
            self._sp9_fam = {x.iid: x.family for x in (getattr(fc, "subjects", ()) or ()) if x.type_key == CLAPPER}
        if "whip" in self.ta:
            whips = frozenset(x.iid for x in (getattr(fc, "subjects", ()) or ())
                              if x.type_key == CHORISTOR and x.family == CH_WHIP and x.alive and x.in_play)
            if whips != self._whips and status == "ok":
                status = "event"                          # a whip started or ended: pick again (it may keep the goal)
            self._whips = whips
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
                if jump_behind.ENABLED and str(how).startswith(("jump:", "rune:")):
                    jbs = self.stats.setdefault("jb", {})       # SP3: the ticks per branch
                    jbs[how] = jbs.get(how, 0) + 1
            g.why = f"{g.why.split('; ')[0]}; {how}" if "; " in g.why else how     # the controller's branch now
            g.face_x = float(s.pos[0])
        wts = dict(prefs.weights)                         # LOCAL's (Q6's silk gathering in it), EVADE's factors undone
        if prefs.mode == EVADE:
            wts["hit"] /= EVADE_HIT_X
            wts["risk"] /= EVADE_RISK_X
        for k, v in (r.weights.get(g.name) or {}).items():
            wts[k] = wts.get(k, 0.0) * float(v)
        if str(how).startswith("chase"):
            # SSBOT_FORUM_CHASE (SG5): close the gap before its next move (the planner's safety keys stay above J)
            wts["stance"] = wts.get("stance", 0.0) * CHASE_STANCE_X
        hw = {k: (min(v, self.local.rules.other_hit_w) if v > 0 and k != g.target else v)
              for k, v in prefs.hit_w.items()}           # LOCAL's own target back to the others' weight
        if how in CC_RETREAT:
            # the Clapper controller steps away: no reward for chasing a hit on it meanwhile (round 2, v3 live: hits
            # by its slam / landing slam while stepping out or backing off, the hit weight pulling the other way)
            if hw.get(g.target, 0.0) > 0:
                hw[g.target] = 0.0
        elif g.target in hw and hw[g.target] > 0:
            w = r.target_hit_w * r.priority.get(getattr(s, "type_key", ""), 1.0)
            if s is not None and s.type_key == CLAPPER and str(how).startswith("jump: under"):
                w *= r.up_hit_x                           # up slashes on the way under it
            hw[g.target] = max(hw[g.target], w)
        out = replace(prefs, mode=g.name, goal=g.name, target=g.target, stance_x=float(g.stance_x),
                      boss_x=g.face_x, hit_w=hw, weights=wts, vocab=frozenset(prefs.vocab) | g.vocab)
        how_s = str(how)
        if jump_behind.ENABLED and how_s.startswith(JB_NO_HIT) and not (
                jump_behind.PASS_HIT and how_s == "jump: under and behind (flight)"):
            # SSBOT_FORUM_JUMP_BEHIND (SP3): no hit on it counts while it jumps (antic, flight) or while the stance
            # leaves its rune circle - the landed-hits rank sits above the stance (trial 2: rows slashing it in the air
            # kept the hero airborne in front of it: the umbrella, the landing slam, the rune circle)
            out = replace(out, no_hit=frozenset({g.target}))
        elif (jump_behind.ENABLED or (slam_play.AFTER and how_s == "slam: after")) and s is not None and (
                s.type_key == CLAPPER) and (
                s.family in (None, "CC_EVADE") or how_s.startswith(JB_GROUND_HIT)):
            # SSBOT_FORUM_JUMP_BEHIND (SP3 trial 3): near it after a jump the planner's pogo / jump slashes on the idle
            # Clapper sent it into its attack choice with the hero bouncing in the air (9 of 56 slams: no landing for
            # the playbook, 3 hammer hits): its hits count only from the ground (the person slashes it standing). SP4:
            # also in the flight (JB_PASS), its fall (JB_LAND), the jump cast's antic (JB_CAST_ANTIC) and after the
            # hammer (SLAM_AFTER)
            out = replace(out, ground_hit=frozenset({g.target}))
            if jump_behind.NO_JUMP and how_s.startswith(JB_GROUND_FIRST):
                # SSBOT_FORUM_JB_NOJUMP (SP4): behind it, rows without a jump key first among equal landed hits
                out = replace(out, ground_first=frozenset({g.target}))
        if (jump_behind.WALK and s is not None and s.type_key == CLAPPER and how_s == "jump: under and behind (flight)"
                and s.iid in self.jb_land):
            # SSBOT_FORUM_JB_WALK (SP6): a walk gets her past its back in time: no dash (she can slash on the way)
            x0, f0, land, _ = self.jb_land[s.iid]
            aim_f = 30.0 if s.family == CC_JUMP else 55.0
            since = (self._t - self.t_commit.get(s.iid, self._t)) * 60.0 - aim_f
            if (hx - land) * f0 > 0 and jump_behind.walk_fits(hx, land, int(f0), since):
                out = replace(out, no_dash=frozenset(out.no_dash) | frozenset({g.target}))
                self.stats["jb_walk"] = self.stats.get("jb_walk", 0) + 1
        if (jump_behind.CORNER and s is not None and s.type_key == CLAPPER
                and how_s == "jump: under and behind (flight)" and s.iid in self.jb_land
                and sum(1 for x in (getattr(fc, "subjects", ()) or ())
                        if x.type_key == CLAPPER and x.alive and x.in_play) == 1):
            # SSBOT_FORUM_JB_CORNER (SP8b): a jump taking off with its centre within push_from_u of the wall behind it
            # lands pushed out, near her: walk under it to the behind spot when the walk fits (dash rows after)
            x0, f0, land, _ = self.jb_land[s.iid]
            if jump_behind.corner_room(x0, f0) < jump_behind.CFG["push_from_u"]:
                aim_f = 30.0 if s.family == CC_JUMP else 55.0
                since = (self._t - self.t_commit.get(s.iid, self._t)) * 60.0 - aim_f
                if (hx - land) * f0 > 0 and jump_behind.walk_fits(hx, land, int(f0), since,
                                                                   jump_behind.CFG["corner_walk_end_f"]):
                    out = replace(out, no_dash=frozenset(out.no_dash) | frozenset({g.target}))
                    self.stats["jb_corner_walk"] = self.stats.get("jb_corner_walk", 0) + 1
        if (slam_play.ENABLED and slam_play.NODASH and s is not None and s.type_key == CLAPPER and s.pos is not None
                and s.family in SP4_IDLE_FAMS and abs(hx - float(s.pos[0])) <= slam_play.NODASH_U):
            # SSBOT_FORUM_SLAM_PLAY_NODASH (SP4): a slam can start any frame: no dash + run (no input) near it
            out = replace(out, no_dash=frozenset({g.target}))
        if (slam_play.ENABLED and slam_play.NOPOGO and s is not None and s.type_key == CLAPPER
                and s.family in SP4_IDLE_FAMS):
            # SSBOT_FORUM_SLAM_PLAY_NOPOGO (SP4): a hit starts its attack choice: not from the air, and (its idle family
            # CC_IDLE, which SP3's ground_hit missed) its hits count from the ground only
            out = replace(out, no_pogo=frozenset({g.target}),
                          ground_hit=frozenset(out.ground_hit) | frozenset({g.target}))
        if self.ta:
            out, ta_why = self._ta_rules(ws, fc, out, g, s, hx)
            if ta_why:
                self.last["ta"] = ta_why
                tw = self.stats.setdefault("ta", {})
                for k in ta_why:
                    k = k.split(":")[0]
                    tw[k] = tw.get(k, 0) + 1
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


CHASE_U = 4.0               # SSBOT_FORUM_CHASE: the chase stance without the map's readiness (centre to centre, u)
CHASE_STANCE_X = 2.0        # ... and its stance weight's factor


def _chase_on() -> bool:
    """SSBOT_FORUM_CHASE=1 with SSBOT_FORUM_SPECIAL_MAP=1 (task 1v1 SG5)."""
    return (os.environ.get("SSBOT_FORUM_SPECIAL_MAP", "0").strip() == "1"
            and os.environ.get("SSBOT_FORUM_CHASE", "0").strip() == "1")


def _chase_ok(mb, x: float, hx: float) -> bool:
    """SSBOT_FORUM_CHASE review: the chase stance only where the slam map handles a slam this Clapper starts now: the
    planner's gate on its last tick (BOARD "chase_x": yes, "chase_off": no), else (no readiness that tick: far, the
    entry, no safe row) the map loaded (forum_map.MAP_READY) and no wall exit for it facing the hero (chase_wall)."""
    if mb is not None:
        if mb.get("chase_x") is not None:
            return True
        if mb.get("chase_off"):
            return False
    from ssbot.combat import forum_map
    return bool(forum_map.MAP_READY.get("ok")) and not forum_map.chase_wall(x, hx)


def _sg8_on() -> bool:
    """SSBOT_FORUM_SG8=1 with SSBOT_FORUM_SPECIAL_MAP=1 (task 1v1 SG8)."""
    return (os.environ.get("SSBOT_FORUM_SPECIAL_MAP", "0").strip() == "1"
            and os.environ.get("SSBOT_FORUM_SG8", "0").strip() == "1")


def _map_board(iid):
    """SSBOT_FORUM_SPECIAL_MAP (SG4): the planner's map decision for this Clapper this tick (combat.forum_map.BOARD),
    None without the switch."""
    if os.environ.get("SSBOT_FORUM_SPECIAL_MAP", "0").strip() != "1":
        return None
    from ssbot.combat import forum_map
    return forum_map.BOARD.get(iid)
