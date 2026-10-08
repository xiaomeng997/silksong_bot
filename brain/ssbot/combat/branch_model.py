"""Forum branch model (forum_planner_plan §5 R5, the behaviour-model half): the probability of each successor of an
enemy's decision state from what the FSM reads when it decides (scoring only: P / J and the O / BAIT values; the
support, which says what can happen, is not touched).

Three things the R0 behaviour tables (ssbot.knowledge.behaviour_tables, at runtime the walk's unconditional p_succ)
did not have:

1. The sensing time (the person 2026-10-04: "which moment's distance"). From the control FSMs (scene bundle, decoded
   in docs/facts/1.0.30000/forum.md §18): most decisions read the hero in the state they leave, either every frame
   (range checks: the exit frame is the frame the hero was in range) or once at entry with an instant exit; a few
   read it earlier: at the entry of a state left later (Choristor Hop Antic's Close Range, the Clawmaiden's silk test
   in Spin Antic, the Minister's Retreat? coin), or in an earlier state (the Reed's throw: Throw Antic Anim stores
   "aiming up", Throw Aim stores the angle 0.4 s before Throwing Up? reads it). SENSING lists them;
   ssbot.knowledge.forum_branch measured branch frame / sensing time / fixed leads on held-out fights.
2. Cooldowns and anti-repeat counters as history the view can see: SendRandomEventV4 (no more than eventMax of one
   event in a row, forced after missedMax misses), gate bools (Bellbearer Evade Cooldown: set by Evade, cleared only
   by Throw Antic; Reed's armed Evade Range and Just Did Defend; Clapper Evaded; Envoy Charge Range), counters (the
   Choristor's 1-3 hops, the Maestro's dead Tinies), timers (the Clawmaiden's suck timer). BranchMemory derives them
   from the Control transitions and the hits the tracker sees.
3. Branch-split history (the person 2026-10-04): the previous attack's last state (the defend that was hit and
   countered vs the one that ran out) and a recent hit, so the two branches can have different times to the next move.

Two tables per decision state (branch_model.json):

- "types" (the fire-frame model): P(successor | the decision fires now), fit on the frames the state was left. It
  answers "if it decides at this moment, which branch": the instant decisions (they fire on the frame they are
  entered) and a candidate path's what-if. Mid-state it is NOT a forecast: a range check that has not fired yet says
  little about the branch it will take later (held-out log loss several times the unconditional table's 0.2-0.5 s
  before the exit, forum.md §18.4).
- "ahead" (the forecast model): P(the successor this visit ends in | what the view sees now), fit on the frames an
  enemy spends in the state (every AHEAD_DT s of each visit, labelled with how the visit ended), so it is calibrated on
  the frames the planner queries. It marginalises over the hero's motion in the recorded fights (the data policies);
  a candidate-conditioned forecast would combine the fire-frame model with a time-to-fire model along the candidate's
  hero path (not built). BranchView.next_attack_probs (Subject.next_p) uses it.

    mem = BranchMemory("Song Reed")
    mem.enter("Alert", "Defend Start", T)       # every Control transition, in order
    mem.hit(T)                                  # the enemy took a hit (any source)
    model = BranchModel.load()                  # knowledge/1.0.30000/enemies/forum/branch_model.json
    p = model.predict("Song Reed", "Alert", mem, geo)   # {successor: p}; geo from geometry(...) at the sensing time

Everything here is view-legal (forum_planner_plan §4.6): states and their entry times (oracle FSM / vision phases),
hits seen, positions, the hero's own silk. Nothing reads FSM variables. The offline scan (ssbot.knowledge.forum_branch)
computes every covariate with the functions below (BranchMemory.features, geometry, clapper_context, TinyOwners) and
the segmentation the model stores, so the runtime sees the covariates the model was selected on
(ssbot.tools.forum_branch parity checks it on recordings).
"""
from __future__ import annotations

import json
import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

BRANCH_MODEL_PATH = Path(__file__).resolve().parents[3] / "knowledge" / "1.0.30000" / "enemies" / "forum" / \
    "branch_model.json"
PAD_U = 0.05                    # hero box padding against a trigger shape (reactive_moves §2: transform vs step)

# ---- trigger shapes (scene bundle AlertRange children, world size incl. the root scale; reactive_scripts ranges.json):
# ("box", cx, cy, hw, hh) / ("circ", cx, cy, r) relative to the enemy transform with cx for flipX False (the sprite
# faces -x); mirrored with flipX. A tuple of shapes is their union.
RANGES: dict[str, dict[str, tuple]] = {
    "Song Administrator": {"Attack Range": (("circ", 0.0, -1.0, 7.0),),
                           "Evade Range": (("circ", 0.0, -1.0, 4.955),)},
    "Song Heavy Sentry": {"Slam Range": (("box", 0.0, -0.543, 8.049, 3.913),)},
    "Song Handmaiden": {"Slash Range": (("box", -1.565, 0.395, 2.28, 2.204),),
                        "Suck Start Range": (("circ", 0.0, 0.0, 10.41),),
                        "Tele Escape Range": (("circ", 0.0, 0.0, 2.66),)},
    "Song Reed": {"Evade Range": (("box", 0.0, 0.043, 1.479, 5.202), ("box", 0.0, 2.570, 3.810, 2.674)),
                  "Defend Range": (("circ", 0.0, 0.0, 7.65),),
                  "Throw Range": (("box", 0.0, 0.0, 11.902, 7.559),),
                  "Stab Range": (("box", -0.129, -0.577, 6.362, 2.485),)},
    "Song Pilgrim 01": {"Attack Range": (("box", 0.0, 0.187, 4.5, 2.688),)},
    "Song Pilgrim 03": {"Close Range": (("box", -0.198, -0.27, 2.885, 1.906),),
                        "Attack Range": (("box", -0.034, 0.855, 12.703, 3.03),),
                        "Slash Range": (("box", 0.0, 0.855, 7.5, 3.03),),
                        "Jump Range": (("box", 8.36, 1.814, 3.325, 3.989),)},
    "Pilgrim 03 Song": {"Evade Range": (("box", 0.0, 0.0, 3.297, 6.659),),
                        "Throw Range": (("circ", 0.0, 0.0, 12.615),)},
    "Song Pilgrim Maestro": {"Attack Range": (("box", 0.0, -0.47, 13.5, 8.65),)},
}

# ---- what each decision reads and when (Control FSM statics, forum.md §18.1). kind: "branch" = the state's checks
# run every frame or once with an instant exit, so the exit frame is the sensing frame; "entry" = read once when the
# state is entered, left later (a wait or an animation); "stored:<state>" = a value an earlier state stored.
SENSING: dict[str, dict[str, tuple[str, str]]] = {
    "Song Heavy Sentry": {
        "Idle": ("branch", "every frame: Slam Range & Will Evade (coin at entry) & Can Evade (>= 0.25 s) -> Evade "
                           "Scuttle; at entry: buddy |x| < 4 -> Avoid Type; TOOK DAMAGE -> Dmg Attack; 0.65 / 1.15 s "
                           "(no buddy / buddy) -> Walk"),
        "Walk": ("branch", "every frame: Attack Ready (>= 0.25 s) & Slam Range -> Close Range; WaitRandom 0.25-2 s -> "
                           "Far Range"),
        "Close Range": ("branch", "instant: buddy attacking -> Idle; clip Walk B -> Slam; V4 SLAM/CAST (Evaded); V4 "
                                  "SLAM/EVADE/CAST eventMax 1"),
        "Far Range": ("branch", "instant: buddy attacking -> Idle; V4 JUMP 0.5 / CAST 0.25 / JUMP CAST 0.25"),
        "After Scuttle": ("branch", "instant: Slam Range"),
        "Dmg Attack": ("branch", "instant: Slam Range"),
        "Escape Jump": ("branch", "instant: V4 JUMP SLAM / JUMP CAST, eventMax 1 missedMax 1 (alternates)"),
        "Avoid Type": ("branch", "instant: hero and buddy on the same side -> Evade Scuttle"),
        "Evade Scuttle": ("entry", "at entry: wall within 6 u behind -> Escape Jump; else 0.35 s -> After Scuttle"),
    },
    "Song Handmaiden": {
        "Fly": ("branch", "every frame: Slash Range -> Slash Antic; >= 0.5 s & Suck Start Range & suck timer out -> "
                          "Spin Antic; distance > 20 -> Tele Out Antic; WaitRandom 1-2 s -> Tele?"),
        "Spin Antic": ("entry", "at entry: hero silk < 3 & coin -> Fly To Slash; silk < 2 -> Fly; else animation -> "
                                "Spin 0"),
        "Tele?": ("branch", "instant: distance > 22 -> Tele Out Antic; V4 TELEPORT/FINISHED"),
        "Fly To Slash": ("branch", "every frame: Slash Range -> Slash Antic; 1.0 s -> Fly"),
        "Spin 0": ("entry", "the Silk Suck FSM: the hero's silk runs out (NO SILK) before a SUCK TICK"),
        "Spin 1": ("entry", "as Spin 0"),
        "Spin 2": ("entry", "as Spin 0"),
    },
    "Song Administrator": {
        "Chase": ("branch", "every frame: attack timer out & Attack Range -> Attack Choice; TOOK DAMAGE -> Range "
                            "Check"),
        "Attack Choice": ("branch", "instant: V4 CHARGE / PARRY 1:1, eventMax 2 missedMax 2 (no 3 in a row)"),
        "Evade?": ("branch", "instant: V4 FINISHED / none 1:1 (eventMax 2), then Evade Range -> Evade Antic"),
        "Retreat?": ("entry", "at entry: V4 FINISHED / none 1:1 (eventMax 2); else 0.5-1 s; TOOK DAMAGE -> Range "
                              "Check"),
        "Parry Stance": ("branch", "0.85 s or hero passed 1 u behind -> Parry Stance End; BLOCKED HIT -> Parry Block"),
        "Attack": ("branch", "its slash hooks the hero (MULTI HIT CONNECT) -> Multihit"),
        "Check Pos": ("branch", "instant: distance < 6 -> Shift"),
    },
    "Song Pilgrim Maestro": {
        "Attack Choice": ("branch", "instant: more than one dead Tiny -> Fire Antic; V4 FIRE 0.75 / DEFEND 0.25 "
                                    "(FIRE <= 3 in a row, DEFEND never twice)"),
        "Summon?": ("branch", "instant: dead Tinies 0 -> Attack Choice, 3 -> Call; 1-2: V4s (0.35 / ~0.77 summon)"),
        "Fly": ("branch", "instant: Forum battler -> Forum Fly (per instance)"),
        "Slash Recover": ("entry", "at entry: Forum battler -> Slash Recover F; else 0.25 s -> Fly"),
        "Check Pos": ("branch", "instant: distance < 8 -> Shift"),
    },
    "Song Reed": {
        "Alert": ("branch", "every frame: armed Evade Range -> Evade Antic; Will Defend (coin at entry) & Defend "
                            "Range & not Just Did Defend -> Defend Start; WaitRandom 1-1.75 s (0.75 s after a Move "
                            "Cancel) -> Choice; TOOK DAMAGE -> Stab Pos"),
        "Choice": ("branch", "instant: out of Throw Range -> Throw Range; V4 THROW 0.35 / STAB 0.65 (eventMax 2)"),
        "Evade End": ("branch", "instant: coin 0.5 -> Alert, else Throw Range -> Throw Antic Anim"),
        "Stab Pos": ("branch", "every frame: Stab Range -> Stab Antic; 1.5 s -> Move Cancel"),
        "Defend": ("branch", "1.0 s -> Defend End; BLOCKED HIT -> Block"),
        "Throw Lock": ("branch", "instant: its own facing"),
        "Throwing Up?": ("stored:Throw Aim", "the angle to the hero stored at Throw Aim entry (0.4 s before)"),
        "Lock R High": ("stored:Throw Aim", "the angle stored at Throw Aim entry"),
        "Throw Up": ("stored:Throw Antic Anim", "aiming up stored at Throw Antic Anim entry vs the Throw Aim angle"),
        "Throw Down": ("stored:Throw Antic Anim", "as Throw Up"),
        "Check Pos": ("branch", "instant: distance < 6 -> Shift"),
    },
    "Song Pilgrim 01": {
        "Walker": ("branch", "every frame: Attack Range -> Alert Followers; Alerted & Charge Range (active at scene "
                             "load, after a slash and once a Walker visit reaches 1.5 s; off at Charge Antic) -> "
                             "Charge Antic; TOOK DAMAGE -> Leader?"),
        "Combo?": ("branch", "instant: not facing the hero -> Attack End; V4 ATTACK / FINISHED (eventMax 2)"),
        "Charge": ("branch", "every frame: passed the hero 4 u / no floor / stopped -> Charge End; wall -> Wall Bonk; "
                             "PARRIED -> Deflect; TOOK DAMAGE -> Reset"),
    },
    "Song Pilgrim 03": {
        "Hop Antic": ("entry", "at entry: Close Range -> Attack Choice; else 0.2 s -> Hop Check"),
        "Hop Check": ("branch", "instant: |x distance| <= Hop Distance (U(6, 10), drawn at Move Start) -> Hop Back"),
        "Hop Land": ("branch", "instant: hops left (1-3 drawn at Move Start) or a wall ahead -> Attack Choice"),
        "Attack Choice": ("branch", "instant: out of Attack Range -> Battle Idle; Close Range -> Slash Check; V4 "
                                    "SLASH/JUMP/WHIP (eventMax 2, missedMax 3)"),
        "Combo?": ("branch", "instant: not facing the hero or no floor -> Slash Recover"),
        "Slash Check": ("branch", "instant: no floor -> Cancel To Hop Back; out of Slash Range -> BT?"),
        "Whip Check": ("branch", "instant: out of Whip Range -> Jump Check"),
        "Jump Check": ("branch", "instant: ceiling -> Attack Choice; out of Jump Range -> Whip Check"),
        "Unalert Tick?": ("branch", "instant: Unalert / ForceUnalert ranges"),
    },
    "Pilgrim 03 Song": {
        "In Range": ("branch", "every frame: out of Throw Range -> Out of Range; Evade Range & no wall behind & >= 0.5 "
                               "s & no Evade Cooldown -> Evade Antic; WaitRandom 0.8-1.5 s -> Throw Evade"),
        "Insta Throw?": ("branch", "instant: the evade test once, then V4 FINISHED 0.65 / ATTACK 0.35"),
        "Evade End": ("branch", "instant: out of Throw Range -> Out of Range; V4 ATTACK / FINISHED (eventMax 2)"),
        "Check Pos": ("branch", "instant: distance < 6 -> Shift"),
    },
}

# ---- history the FSMs keep (state -> flag changes); BranchMemory applies them on entry
_GATES: dict[str, dict[str, dict[str, bool]]] = {
    # Bellbearer: Evade sets Evade Cooldown, only Throw Antic clears it (one evade per bell thrown)
    "Pilgrim 03 Song": {"Evade": {"evade_cd": True}, "Throw Antic": {"evade_cd": False}},
    # Reed: Evade Antic switches the Evade Range off, Defend Start / Stab Antic on; Defend Start sets Just Did Defend,
    # Stab Antic / Throw Antic clear it
    "Song Reed": {"Evade Antic": {"armed": False}, "Defend Start": {"armed": True, "jdd": True},
                  "Stab Antic": {"armed": True, "jdd": False}, "Throw Antic": {"jdd": False}},
    # Clapper: Evade Scuttle sets Evaded, any attack's antic clears it
    "Song Heavy Sentry": {"Evade Scuttle": {"evaded": True}, "Slam Antic": {"evaded": False},
                          "Jump Antic": {"evaded": False}, "Spell Antic": {"evaded": False},
                          "Cast Slam Antic": {"evaded": False}},
    # Envoy: the Charge Range object is active at scene load; Charge Antic switches it off, Slash Antic on, and
    # Walker's ActivateGameObjectDelay (1.5 s, resetOnExit 0) on once a Walker visit lasts 1.5 s (it stays on after
    # Walker is left; a shorter visit does not arm it: BranchMemory.enter). CHARGE also needs Alerted (set by Slash
    # Antic and Ambush Ready, never cleared).
    "Song Pilgrim 01": {"Charge Antic": {"charge_armed": False}, "Slash Antic": {"charge_armed": True, "alerted": True},
                        "Ambush Ready": {"alerted": True}},
}
_GATE_INIT = {"Pilgrim 03 Song": {"evade_cd": False}, "Song Reed": {"armed": True, "jdd": False},
              "Song Heavy Sentry": {"evaded": False}, "Song Pilgrim 01": {"charge_armed": True, "alerted": False}}
ENVOY_ARM_S = 1.5
TINY_DECISIONS = ("Ready", "Fire Ready", "Fire", "Brake", "Pull Up", "Return", "Defend Ready", "Defend Buzz", "Dead")
HIT_RECENT_S = (0.25, 1.0)      # "hit" bins: hit within 0.25 s / 1 s / earlier or never
SINCE_END_S = (0.25, 0.75, 1.5)
AGE_S = (0.1, 0.25, 0.5, 1.0, 1.5, 2.5)     # time in the state (0 for a state entered now)
LOCAL_KEEP = 6
STALE_S = 0.25                  # an enemy position older than this at the timing is "not seen"
ARENA_X3 = (25.67, 37.33)       # thirds of the Forum band x 14.01-48.99 (the R0 tables' hero_x / last_seen_x)


def decisions_of(tk: str) -> tuple[str, ...]:
    """The decision states whose exits the model covers (the SENSING table; the Tiny's, which the Maestro drives)."""
    if tk == "Song Automaton Tiny":
        return TINY_DECISIONS
    return tuple(SENSING.get(tk, {}))


def _bin(v: float, edges: tuple[float, ...]) -> int:
    for i, e in enumerate(edges):
        if v < e:
            return i
    return len(edges)


@dataclass(slots=True)
class BranchMemory:
    """One enemy's history as the view sees it: Control state entries (with the state each was left from) and the
    hits it took. Families from the type's attack-start table (ssbot.knowledge.gauntlet_tables.FORUM_SPECS)."""
    tk: str
    attack_starts: dict = field(default_factory=dict)
    decision_states: frozenset = frozenset()          # the segmentation's (entering one ends an attack)
    choice_states: frozenset = frozenset()            # states whose outcomes are kept as anti-repeat history
    state: str | None = None
    t_entry: float | None = None
    prev_state: str | None = None
    fam: str | None = None                 # the attack family running (None: between attacks)
    fam_last: str | None = None            # the last attack family
    fam_end_state: str | None = None       # the last state of that attack (its branch: Parry Stance End / Slash End)
    t_fam_end: float | None = None
    run: int = 0                           # attacks in a row of fam_last
    since: dict = field(default_factory=dict)        # family -> attacks since (0: the last one)
    local: dict = field(default_factory=lambda: defaultdict(lambda: deque(maxlen=LOCAL_KEEP)))
    gates: dict = field(default_factory=dict)
    t_hit: float = -math.inf
    entries: dict = field(default_factory=dict)      # state -> last entry time
    seq: int = 0                                     # entries so far (BranchView snapshots the new ones)
    # Choristor: hops in the current move (Move Start resets), the last hop's direction and |x distance|
    hops: int = 0
    last_hop: str | None = None
    # Clawmaiden: time spent in Fly since the suck timer was last set, and by which state
    suck_age: float = 0.0
    suck_set: str | None = None
    # Envoy: Walker entry (the Charge Range comes on 1.5 s in)
    t_walker: float | None = None
    # Bellbearer: how long its last In Range lasted (Can Evade carries over to Insta Throw?)
    inrange_dur: float = 0.0

    def __post_init__(self) -> None:
        self.gates = dict(_GATE_INIT.get(self.tk, {}))

    def enter(self, frm: str | None, to: str, T: float) -> None:
        """A Control transition frm -> to at game time T (frm None: first seen)."""
        if frm is not None and self.state is not None and frm != self.state:
            frm = self.state                         # a missed event: the state we last knew left
        if frm is None:
            frm = self.state
        if frm is not None and (frm in self.decision_states or frm in self.choice_states):
            self.local[frm].append(to)
        if frm == "Fly" and self.tk == "Song Handmaiden" and self.t_entry is not None:
            self.suck_age += max(0.0, T - self.t_entry)
        if frm == "In Range" and self.t_entry is not None:
            self.inrange_dur = T - self.t_entry
        fam = self.attack_starts.get(to)
        if fam is not None and fam != self.fam:
            if self.fam is not None:
                self._end_attack(frm, T)
            self.fam = fam
            for k in list(self.since):
                self.since[k] += 1
            self.since[fam] = 0
            self.run = self.run + 1 if fam == self.fam_last else 1
            self.fam_last = fam
        elif to in self.decision_states and self.fam is not None:
            self._end_attack(frm, T)
        if frm == "Walker" and self.tk == "Song Pilgrim 01" and self.t_walker is not None and \
                T - self.t_walker >= ENVOY_ARM_S:
            self.gates["charge_armed"] = True        # the delayed activation fired during this visit and stays
        for k, v in _GATES.get(self.tk, {}).get(to, {}).items():
            self.gates[k] = v
        if self.tk == "Song Pilgrim 03":
            if to == "Move Start":
                self.hops, self.last_hop = 0, None
            elif to in ("Hop Back", "Hop Forward"):
                self.last_hop = to
            elif to == "Hop Land":
                self.hops += 1
        elif self.tk == "Song Handmaiden" and to in ("Startle", "Spear Fire Recover"):
            self.suck_age, self.suck_set = 0.0, to
        elif self.tk == "Song Pilgrim 01" and to == "Walker":
            self.t_walker = T
        self.prev_state, self.state, self.t_entry = frm, to, T
        self.entries[to] = T
        self.seq += 1

    def _end_attack(self, frm: str | None, T: float) -> None:
        self.fam_end_state, self.t_fam_end, self.fam = frm, T, None

    def hit(self, T: float) -> None:
        self.t_hit = max(self.t_hit, T)

    def features(self, state: str, T: float, context: dict | None = None) -> dict:
        """History covariates for a decision of `state` at game time T (the state being the current one, or about
        to be: the walk's next decision). context: cross-enemy facts the caller knows (Clapper buddy, Maestro dead
        Tinies). The hit covariate counts every hit seen up to T, a hit on this frame included: a TOOK DAMAGE exit
        follows its recorded hit by 12-18 frames when it follows one at all (forum.md §18.2), so a recent hit is past
        information the view has, not the exit's same-frame cause."""
        loc = self.local.get(state) or ()
        run = 0
        for o in reversed(loc):
            if o != loc[-1]:
                break
            run += 1
        cur = self.state == state
        f = {"prev": self.fam_last or "none",
             "prev_end": f"{self.fam_last}:{self.fam_end_state}" if self.fam_last else "none",
             "since_end": "none" if self.t_fam_end is None else _bin(T - self.t_fam_end, SINCE_END_S),
             "run": min(self.run, 3) if self.fam_last else "none",
             "last_choice": loc[-1] if loc else "none",
             "choice_run": min(run, 3) if loc else "none",
             "prev2_choice": "|".join(list(loc)[-2:]) if len(loc) >= 2 else ("|".join(loc) or "none"),
             "hit": _bin(T - self.t_hit, HIT_RECENT_S),
             "from": self.prev_state if cur else self.state,
             "age": _bin(T - self.t_entry, AGE_S) if cur and self.t_entry is not None else 0}
        # the R0 tables' anti-repeat counters: attacks since each family (V4 eventMax), choices since each outcome
        # of this state (V4 missedMax)
        for fam in set(self.attack_starts.values()):
            k = self.since.get(fam)
            f[f"since_{fam}"] = "none" if k is None else min(k, 4)
        for i, o in enumerate(reversed(loc)):
            f.setdefault(f"miss_{o}", min(i, 4))
        for k, v in self.gates.items():
            f[k] = v
        if self.tk == "Song Pilgrim 03":
            f["hops"] = self.hops
            f["last_hop"] = self.last_hop or "none"
        elif self.tk == "Song Handmaiden":
            age = self.suck_age + (T - self.t_entry if self.state == "Fly" and self.t_entry is not None else 0.0)
            f["suck_age"] = _bin(age, (1.0, 1.5, 2.0, 3.0))
            f["suck_set"] = self.suck_set or "none"
        elif self.tk == "Song Pilgrim 01":
            on = self.gates.get("charge_armed", False) or (
                self.state == "Walker" and self.t_walker is not None and T - self.t_walker >= ENVOY_ARM_S)
            f["charge_armed"] = on
        elif self.tk == "Pilgrim 03 Song":
            f["can_evade"] = self.inrange_dur >= 0.5
        for k, v in (context or {}).items():
            f[k] = v
        return f


# ---- geometry at the sensing time

DX_BINS = (1.5, 3.0, 4.5, 6.0, 8.0, 10.0, 13.0)
DY_BINS = (-4.0, -1.5, 1.5, 4.0)
SILK_BINS = (1, 2, 3, 9)


def _shape_hit(shape: tuple, ex: float, ey: float, mirror: int, hb: tuple) -> bool:
    x0, y0, x1, y1 = hb[0] - PAD_U, hb[1] - PAD_U, hb[2] + PAD_U, hb[3] + PAD_U
    if shape[0] == "box":
        _, cx, cy, hw, hh = shape
        cx, cy = ex + mirror * cx, ey + cy
        return x0 <= cx + hw and x1 >= cx - hw and y0 <= cy + hh and y1 >= cy - hh
    _, cx, cy, r = shape
    cx, cy = ex + mirror * cx, ey + cy
    nx, ny = min(max(cx, x0), x1), min(max(cy, y0), y1)
    return (nx - cx) ** 2 + (ny - cy) ** 2 <= r * r


def in_range(tk: str, name: str, ex: float, ey: float, flip: int, hero_box: tuple) -> bool | None:
    """Whether the hero's physics box (padded) meets one of the type's trigger shapes (None: shape unknown). flip:
    the enemy's flipX (0: faces -x, the shapes' frame)."""
    shapes = RANGES.get(tk, {}).get(name)
    if shapes is None:
        return None
    m = 1 if not flip else -1
    return any(_shape_hit(s, ex, ey, m, hero_box) for s in shapes)


def geometry(tk: str, ex: float | None, ey: float | None, flip: int, hx: float | None, hy: float | None,
             hero_box: tuple | None, silk: int | None = None) -> dict:
    """Geometric covariates of a decision at one moment: |dx| / dy bins, side, distance bin, the type's trigger
    ranges (in_<name>), the hero's silk bin, the R0 tables' dist_visible / last_seen_x / hero_x. (ex, ey): the enemy
    transform; (hx, hy): the hero transform (STATE hero.pos, WorldState hero.pos_transform); hero_box: the hero's
    physics box. Missing inputs give None values (not available)."""
    out: dict = {}
    if ex is not None and hx is not None and not (math.isnan(ex) or math.isnan(hx)):
        dx, dy = hx - ex, hy - ey
        out["dx"] = _bin(abs(dx), DX_BINS)
        out["dy"] = _bin(dy, DY_BINS)
        out["side"] = "R" if dx >= 0 else "L"
        out["front"] = "front" if (dx < 0) == (not flip) else "back"
        out["dist"] = _bin(math.hypot(dx, dy), DX_BINS)
        # the R0 tables' geometry (behaviour_tables._covariates): |dx| in 3 / 6 / 10 u bins, the enemy's third
        out["dist_visible"] = _bin(abs(dx), (3.0, 6.0, 10.0))
        out["last_seen_x"] = _bin(ex, ARENA_X3)
        if hero_box is not None and not any(math.isnan(v) for v in hero_box):
            for name in RANGES.get(tk, {}):
                out[f"in_{name}"] = in_range(tk, name, ex, ey, flip, hero_box)
    if hx is not None and not math.isnan(hx):
        out["hero_x"] = _bin(hx, ARENA_X3)
    if silk is not None:
        out["silk"] = _bin(silk, SILK_BINS)
    return out


# ---- the model

ALPHA_BACKOFF = 4.0


@dataclass(slots=True)
class DecisionModel:
    """One decision state's table: outcomes, the covariates in selection order, counts per covariate prefix
    (backoff: P(y | c1..ck) = (n(y, c1..ck) + a P(y | c1..ck-1)) / (n(c1..ck) + a))."""
    outcomes: list[str]
    covariates: list[str]
    timing: str
    counts: list[dict]            # counts[k]: key "v1|..|vk" -> [n per outcome] (k = 0: the "" key)
    alpha: float = ALPHA_BACKOFF

    def predict(self, feats: dict) -> dict[str, float]:
        K = len(self.outcomes)
        c0 = self.counts[0].get("", [0] * K)
        n0 = sum(c0)
        p = [(c + 0.5) / (n0 + 0.5 * K) for c in c0]
        key = []
        for k, name in enumerate(self.covariates, start=1):
            v = feats.get(name)
            if v is None:
                break
            key.append(_key(v))
            c = self.counts[k].get("|".join(key))
            if c is None:
                break
            n = sum(c)
            p = [(c[i] + self.alpha * p[i]) / (n + self.alpha) for i in range(K)]
        return dict(zip(self.outcomes, p))


def _key(v) -> str:
    if isinstance(v, bool):
        return "1" if v else "0"
    return str(v)


def _tables(rows: dict) -> dict[str, DecisionModel]:
    return {st: DecisionModel(r["outcomes"], r["covariates"], r.get("timing", "branch"), r["counts"],
                              float(r.get("alpha", ALPHA_BACKOFF))) for st, r in rows.items()}


class BranchModel:
    """Per type and decision state: the fire-frame DecisionModel ("types": P(successor | it fires now)) and the
    forecast one ("ahead": P(the successor this visit ends in | now)), and the segmentation the history was kept with
    ("segmentation"); branch_model.json, ssbot.tools.forum_branch build. Timings: "branch" / "now" (the query frame), "entry" (the state's entry), "stored" (the entry of the state
    SENSING "stored:<state>" names), "lead<s>" (s before now)."""

    def __init__(self, d: dict):
        self.meta = {k: v for k, v in d.items() if k not in ("types", "ahead", "segmentation")}
        self.types = {tk: _tables(rows) for tk, rows in (d.get("types") or {}).items()}
        self.ahead = {tk: _tables(rows) for tk, rows in (d.get("ahead") or {}).items()}
        # type -> {"attack_starts": {state: family}, "decision_states": [...]}: the scan's segmentation
        self.segmentation: dict = d.get("segmentation") or {}

    @classmethod
    def load(cls, path: Path | None = None) -> "BranchModel":
        return cls(json.loads(Path(path or BRANCH_MODEL_PATH).read_text("utf-8")))

    def get(self, tk: str, state: str, ahead: bool = False) -> DecisionModel | None:
        return (self.ahead if ahead else self.types).get(tk, {}).get(state)

    def has(self, tk: str, state: str, ahead: bool = False) -> bool:
        return self.get(tk, state, ahead) is not None

    def timing(self, tk: str, state: str, ahead: bool = False) -> str:
        m = self.get(tk, state, ahead)
        return "branch" if m is None else m.timing

    def predict(self, tk: str, state: str, mem: BranchMemory | None, geo: dict | None, T: float = 0.0,
                context: dict | None = None, ahead: bool = False) -> dict[str, float] | None:
        m = self.get(tk, state, ahead)
        if m is None:
            return None
        feats = dict(geo or {})
        if mem is not None:
            feats.update(mem.features(state, T, context))
        return m.predict(feats)


def memory_for_table(tt, model: BranchModel | None = None) -> BranchMemory:
    """A BranchMemory for a combat.enemy_tables.TypeTable's enemy type with the segmentation the model was fit with
    (BranchModel.segmentation: the scan's gauntlet_tables.FORUM_SPECS, stored in branch_model.json; the walk's
    TypeTable lacks a few families, the Maestro's MA_POINT and the Envoy's EN_HOPSLASH / EN_ENTRY), else the table's,
    and the type's choice states."""
    tk = tt.spec.type_key
    seg = (model.segmentation if model is not None else {}).get(tk)
    if seg is None:
        return BranchMemory(tk, dict(tt.attack_starts), frozenset(tt.decision_states), frozenset(decisions_of(tk)))
    return BranchMemory(tk, dict(seg["attack_starts"]), frozenset(seg["decision_states"]), frozenset(decisions_of(tk)))


CLAPPER = "Song Heavy Sentry"
MAESTRO = "Song Pilgrim Maestro"
TINY = "Song Automaton Tiny"
CLAPPER_ATTACKS = ("CC_SLAM", "CC_JUMP", "CC_CAST", "CC_JUMP_CAST")
TINY_DEAD = ("Death Fx", "Dead", "Die")
TINY_OWNER_U = 8.0
KEEP_S = 1.0
MAX_CHAIN = 4


def in_play(tk: str, state: str | None) -> bool:
    """A Control state that takes part in the fight (ssbot.core.forum.ForumType.waiting: not yet)."""
    from ssbot.core.forum import FORUM_TYPES
    ft = FORUM_TYPES.get(tk)
    return state is not None and (ft is None or state not in ft.waiting)


def clapper_context(me: tuple | None, buddies: list) -> dict:
    """The Clapper's cross-enemy facts (its Control: Close Range / Far Range go back to Idle while the buddy attacks;
    Idle's Avoid Type when the buddy stands within 4 u). me: its (x, y, flip) seen within STALE_S or None; buddies:
    [(BranchMemory, (x, y, flip))] of the other Clappers in play (in_play) seen within STALE_S."""
    return {"buddy": bool(buddies),
            "buddy_attacking": any(m.fam in CLAPPER_ATTACKS for m, _ in buddies),
            "buddy_close": bool(me is not None and any(abs(r[0] - me[0]) < 4.0 for _, r in buddies))}


class TinyOwners:
    """Which Maestro each Tiny belongs to, assigned online: on every frame a Tiny is seen in Ready, the nearest
    Maestro seen within STALE_S, if closer than TINY_OWNER_U (the Tinies' Idle Pos is (+-3, 2.5) / (0, 4.5) from their
    own Maestro); the last assignment holds. The Maestro's dead_tinies context counts its Tinies in TINY_DEAD."""

    def __init__(self):
        self.owner: dict[int, int] = {}

    def update(self, tinies: list, maes: list) -> None:
        """tinies: [(iid, (x, y))] seen this frame in Ready; maes: [(iid, (x, y))] seen within STALE_S."""
        if not maes:
            return
        for j, (x, y) in tinies:
            d, m = min((math.hypot(mx - x, my - y), mi) for mi, (mx, my) in maes)
            if d < TINY_OWNER_U:
                self.owner[j] = m

    def dead(self, maestro: int, state_of) -> int:
        return sum(1 for j, o in self.owner.items() if o == maestro and state_of(j) in TINY_DEAD)


class BranchView:
    """The branch model at runtime (MultiForecaster(branch=...)): each EnemyTracker carries a BranchMemory (fed by its
    Control entries and hits); this keeps the hero's recent box, transform and silk, the enemies' recent positions
    (the frames they were seen) and a snapshot of both at each state entry, so a decision's geometry is taken at the
    model's timing exactly as the offline scan takes it (now / branch: this frame; entry: the state's entry; stored:
    the stored state's entry; lead<s>: s before now)."""

    def __init__(self, model: BranchModel, keep_s: float = KEEP_S):
        self.model = model
        self.keep_s = keep_s
        self.hero: deque = deque()                          # (T, box, x, y, silk)
        self.enemy: dict[int, deque] = defaultdict(deque)   # iid -> (T, x, y, flip), frames it was seen
        self.snap: dict[int, dict] = defaultdict(dict)      # iid -> state -> (entry T, hero row, enemy row)
        self._seq: dict[int, int] = {}
        self.owners = TinyOwners()
        self.t = -math.inf

    def observe(self, T: float, ws, trackers: dict) -> None:
        self.t = T
        h = ws.hero
        if h.hurtbox:
            xs = [p[0] for p in h.hurtbox]
            ys = [p[1] for p in h.hurtbox]
            box = (min(xs), min(ys), max(xs), max(ys))
        else:
            box = None
        pt = h.pos_transform if h.pos_transform is not None else h.pos.v     # the transform, as STATE hero.pos
        silk = ws.res.silk.v if ws.res.silk.conf > 0 else None
        self.hero.append((T, box, float(pt[0]), float(pt[1]), silk))
        while self.hero and T - self.hero[0][0] > self.keep_s:
            self.hero.popleft()
        for iid, tr in trackers.items():
            q = self.enemy[iid]
            if tr.pos is not None and not tr.hidden and getattr(tr, "seen_T", T) == T and (not q or q[-1][0] < T):
                q.append((T, tr.pos[0], tr.pos[1], tr.flip))
            while q and T - q[0][0] > self.keep_s:
                q.popleft()
        for iid, tr in trackers.items():
            m = tr.mem
            if m is None or m.seq == self._seq.get(iid, 0):
                continue
            self._seq[iid] = m.seq
            snaps = self.snap[iid]
            for st, te in m.entries.items():
                old = snaps.get(st)
                if old is None or old[0] != te:
                    snaps[st] = (te,) + self._rows(iid, te)
        tinies, maes = [], []
        for iid, tr in trackers.items():
            if tr.tk == TINY and tr.state == "Ready":
                q = self.enemy.get(iid)
                if q and q[-1][0] == T:
                    tinies.append((iid, (q[-1][1], q[-1][2])))
            elif tr.tk == MAESTRO:
                e = self._enemy_at(iid, T)
                if e is not None:
                    maes.append((iid, (e[1], e[2])))
        self.owners.update(tinies, maes)

    def _hero_at(self, t: float):
        for row in reversed(self.hero):
            if row[0] <= t + 1e-9:
                return row
        return None

    def _enemy_at(self, iid: int, t_frame: float):
        """The enemy's last row seen at or before the frame at t_frame, None if older than STALE_S."""
        for row in reversed(self.enemy.get(iid) or ()):
            if row[0] <= t_frame + 1e-9:
                return row if t_frame - row[0] <= STALE_S + 1e-9 else None
        return None

    def _rows(self, iid: int, t: float) -> tuple:
        h = self._hero_at(t)
        return h, self._enemy_at(iid, t if h is None else h[0])

    def _rows_for(self, tr, state: str, T: float, timing: str) -> tuple:
        mem = tr.mem
        if timing == "entry" and mem is not None and mem.state == state:
            s = self.snap.get(tr.iid, {}).get(state)
            return (None, None) if s is None else s[1:]
        if timing == "stored":
            kind = SENSING.get(tr.tk, {}).get(state, ("branch", ""))[0]
            src = kind.split(":", 1)[1] if kind.startswith("stored:") else None
            s = self.snap.get(tr.iid, {}).get(src) if src is not None else None
            return (None, None) if s is None else s[1:]
        if timing.startswith("lead"):
            return self._rows(tr.iid, T - float(timing[4:]))
        return self._rows(tr.iid, T)

    def geo_at(self, tr, state: str, T: float, timing: str) -> dict:
        h, e = self._rows_for(tr, state, T, timing)
        if h is None:
            return {}
        _, box, hx, hy, silk = h
        if e is None:
            return geometry(tr.tk, None, None, 0, hx, hy, box, silk)
        return geometry(tr.tk, e[1], e[2], e[3], hx, hy, box, silk)

    def context(self, tr, trackers: dict, T: float) -> dict:
        if tr.tk == CLAPPER:
            me = self._enemy_at(tr.iid, T)
            buddies = []
            for b in trackers.values():
                if b.tk != tr.tk or b.iid == tr.iid or b.mem is None or not in_play(b.tk, b.mem.state):
                    continue
                r = self._enemy_at(b.iid, T)
                if r is not None:
                    buddies.append((b.mem, r[1:]))
            return clapper_context(None if me is None else me[1:], buddies)
        if tr.tk == MAESTRO:
            return {"dead_tinies": self.owners.dead(
                tr.iid, lambda j: trackers[j].mem.state if j in trackers and trackers[j].mem is not None else None)}
        return {}

    def features(self, tr, state: str, T: float, trackers: dict, ahead: bool = False,
                 ctx: dict | None = None) -> dict | None:
        """The covariates the model's table for tr's decision `state` reads at T (geometry at its timing + history);
        None when the model has no table for it."""
        m = self.model.get(tr.tk, state, ahead)
        if m is None or tr.mem is None:
            return None
        f = self.geo_at(tr, state, T, m.timing)
        f.update(tr.mem.features(state, T, self.context(tr, trackers, T) if ctx is None else ctx))
        return f

    def branch_probs(self, tr, T: float, trackers: dict, state: str | None = None,
                     ahead: bool = False) -> dict[str, float] | None:
        """{successor: p} of tr's decision `state` (default: its current state). ahead False: the fire-frame model,
        P(successor | it decides at T); ahead True: the forecast, P(the successor this visit ends in | the view at T)
        (falls back to the fire-frame table when the state has no forecast table: the instant decisions, which
        decide on the frame they are entered)."""
        st = state or tr.state
        if st is None or tr.mem is None:
            return None
        use = ahead and self.model.has(tr.tk, st, True)
        f = self.features(tr, st, T, trackers, use)
        return None if f is None else self.model.get(tr.tk, st, use).predict(f)

    def next_attack_probs(self, tr, T: float, trackers: dict) -> dict[str, float] | None:
        """{family or "wait:<state>": p}: the next attack family when tr's current decision resolves (the forecast
        table of its state, then the decisions it leads to, each as entered now with today's geometry and history:
        their forecast tables, the fire-frame ones for the instant decisions); "wait:<state>" for paths that first
        reach a state the model does not cover. None: tr is not in a modelled decision state."""
        p0 = self.branch_probs(tr, T, trackers, ahead=True)
        if p0 is None:
            return None
        starts = tr.table.attack_starts
        out: dict[str, float] = defaultdict(float)
        frontier = list(p0.items())
        for _ in range(MAX_CHAIN):
            nxt = []
            for st, p in frontier:
                if p < 1e-4:
                    continue
                if st in starts:
                    out[starts[st]] += p
                    continue
                q = self.branch_probs(tr, T, trackers, st, ahead=True) if st != tr.state else None
                if q is None:
                    out[f"wait:{st}"] += p
                    continue
                nxt += [(s2, p * p2) for s2, p2 in q.items()]
            frontier = nxt
            if not frontier:
                break
        for st, p in frontier:
            out[f"wait:{st}"] += p
        return dict(out)

    # ---- body-entry reactive branches (forum_reactive_moves.md; scoring only)

    def _coin_tails(self, tr, rx: Reactive, T: float) -> bool:
        """The hidden coin of this visit came up tails: the hero's box was in the trigger with the gates open for two
        frames or more and the enemy is still in the source state (a heads goes on the first such frame)."""
        mem = tr.mem
        if not rx.coin or mem is None or mem.t_entry is None:
            return False
        q = self.enemy.get(tr.iid)
        if not q:
            return False
        e = q[-1]
        n = 0
        for t, box, _, _, _ in self.hero:
            if t < mem.t_entry + rx.min_age_s or t > T or box is None:
                continue
            if in_range(tr.tk, rx.range_name, e[1], e[2], e[3], box):
                n += 1
                if n >= 2:
                    return True
        return False

    def reactive(self, tr, T: float) -> list[tuple[Reactive, float]]:
        """The body-entry branches open for tr now: (the trigger, the chance the hero's body entering it now starts the
        dodge / defence). Gates from its BranchMemory; a coin already shown tails in this visit gives 0."""
        out = []
        mem = tr.mem
        if mem is None or tr.state is None:
            return out
        for rx in REACTIVE.get((tr.tk, tr.state), ()):
            if not all(bool(mem.gates.get(k, False)) == v for k, v in rx.gates):
                continue
            p = 0.0 if self._coin_tails(tr, rx, T) else rx.p_enter
            out.append((rx, p))
        return out

    def entry_prob(self, tr, T: float, path) -> list[tuple[str, float, float]]:
        """For a candidate's hero boxes path [(t, box)] (game time, ascending): per open trigger of tr, (the successor,
        the first time the box enters the trigger at or after its gate age, the chance it starts then). The enemy is
        held where it was last seen (the source states hover or stand: forum_reactive_moves §1.2)."""
        q = self.enemy.get(tr.iid)
        if not q or tr.mem is None or tr.mem.t_entry is None:
            return []
        e = q[-1]
        out = []
        for rx, p in self.reactive(tr, T):
            t_gate = tr.mem.t_entry + rx.min_age_s
            for t, box in path:
                if t >= t_gate and in_range(tr.tk, rx.range_name, e[1], e[2], e[3], box):
                    out.append((rx.successor, t, p))
                    break
        return out


@dataclass(frozen=True, slots=True)
class Reactive:
    """A body-entry branch (forum_reactive_moves.md §1.2 / §2.2, R0 per-visit rates): in source state, the hero's
    physics box entering range_name with the gates open (BranchMemory.gates name -> required value) and the state at
    least min_age_s old starts successor with chance p_enter (coin: a hidden 50 % coin drawn at the state's entry)."""
    range_name: str
    successor: str
    p_enter: float
    min_age_s: float
    coin: bool
    gates: tuple = ()


REACTIVE: dict[tuple[str, str], tuple[Reactive, ...]] = {
    # Bellbearer: Evade Range & no wall behind & Can Evade (0.5 s into In Range) & no Evade Cooldown: 0.97 per visit
    ("Pilgrim 03 Song", "In Range"): (Reactive("Evade Range", "Evade Antic", 0.97, 0.5, False,
                                               (("evade_cd", False),)),),
    # Clapper: Slam Range & Will Evade (coin at Idle entry) & Can Evade (0.25 s): 0.49
    ("Song Heavy Sentry", "Idle"): (Reactive("Slam Range", "Evade Scuttle", 0.49, 0.25, True),),
    # Reed: armed Evade Range (one shot: off at Evade Antic, on at Defend Start / Stab Antic): 0.95 entering during
    # Alert (0.8 when already inside as Alert begins); Defend Range & Will Defend (coin) & not Just Did Defend: 0.45
    # (EVADE is tested first in the same frame)
    ("Song Reed", "Alert"): (Reactive("Evade Range", "Evade Antic", 0.95, 0.0, False, (("armed", True),)),
                             Reactive("Defend Range", "Defend Start", 0.45, 0.0, True, (("jdd", False),))),
}
