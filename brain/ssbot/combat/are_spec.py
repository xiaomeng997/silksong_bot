"""The per-type description of the attack-range estimate (ssbot.combat.attack_range): what a type module under
ssbot.combat.are_types declares. Kept free of imports of the estimate itself so a type module can be imported alone
(the registry imports every type module; attack_range imports the registry)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

PARKED = ("Ready", "Dormant", "Sleep", "Wait")


@dataclass(frozen=True)
class Decision:
    """An aim decided inside a family (a pending aim until then, group 2, NOT drawn): the first frame in one of
    `states` decides it. rule(x, y, vx, hero_x, hero_y) -> (s, L): the facing the move is measured in from there and
    the u extent of its displacement (the template's u displacement after the decision is ratio[b] x L, anchored at
    the decision frame's position, mirrored by s). Before the decision the estimate stops at the last bin before it."""
    states: frozenset
    rule: Callable
    branch: Callable | None = None     # (x, s, L) -> the family's branch, known from the decision on (or None)


@dataclass(frozen=True)
class HazardSpec:
    """A hazard the enemy owns (it outlives the family that spawned it): spawned at the entry of `state` while the
    owner is in one of `fams` (the trigger), drawn on its rule path at the measured times (the table's
    meta["hazards"][name], built from R0 dev: per ring the first / last frame it hurts after the trigger).
      shape "row":    circles at x_trig + spacing m (abs(m) <= m_max, only where the R0 dev bombs ever stood),
                      ring = abs(m);
      shape "circle": one circle at (x_trig + s du, y_trig + dv).
    Its real colliders are the AABBs of width box_w (+-0.03) of other entities (the pooled "damager" objects),
    attributed to the owner by the trigger rule (tools.attack_range_build.attach_hazards)."""
    name: str
    shape: str
    fams: frozenset
    state: str
    radius: float
    box_w: float
    spacing: float = 0.0
    m_max: int = 0
    du: float = 0.0
    dv: float = 0.0
    pre: bool = False          # predicted from the family's start, before its trigger is seen (trigger time window)
    on0: float | None = None   # the spawn rule's first hurting frame after the trigger: on0 + on_step x ring (the
    on_step: float = 0.0       # attribution takes the trigger that fits it within on_tol frames; None: the latest)
    on_tol: float = 3.0


@dataclass(frozen=True)
class EnemySpec:
    type_key: str
    short: str
    fam_states: dict           # family -> its states (antic start .. end of recovery)
    start: dict                # state -> family (entering it starts an instance)
    primary: dict              # family -> the antic state whose re-entry restarts the family
    branch: dict               # family -> {state: branch} (the first marker seen decides)
    branches: dict             # family -> the branch names (one name: no branch)
    aim: frozenset             # families whose u displacement scales with the hero's offset at the antic start
    body: str | tuple          # the body damager collider's name(s)
    table: str                 # the table's file stem under FORUM
    face_names: tuple = ()     # attack collider name prefixes whose side of the body gives the facing (build)
    decide: dict = field(default_factory=dict)      # family -> Decision
    branch_dur: dict = field(default_factory=dict)  # family -> (state, frames, short, long): a branch decided by how
    #                                                 long the state runs (long once it is entered again - its time
    #                                                 in state restarts - or runs over `frames` of game time since
    #                                                 first seen; short when it is left before); the union until then
    hazards: tuple = ()        # HazardSpec
    parked: tuple = PARKED     # state name parts of a member not in play
    left_out: tuple = ()       # (state, why): what this round does not draw (pending aims, counters)
    state_gate: bool = False   # templates keep each bin's shape per state: k = 0 draws the state it is in now, k > 0
    #                            the states at or after it (attack_range.RangeTable._shape); a state is kept at a bin
    #                            when at least 2 R0 dev instances were in it there (tools.attack_range_build)
    coast: dict = field(default_factory=dict)   # stage B: state -> its velocity decay per 50 Hz step (the FSM's
    #                                             DecelerateV2; 0: velocity set to 0, it holds): in it the position
    #                                             ahead is the observed velocity coasting (attack_range.coast), not the
    #                                             template's median displacement (the Reed's Parry Slash 0.95, Multihit 0)
    hit_started: frozenset = frozenset()   # stage B: families a hit starts (counters, HIT_COND: the Reed's Block, the
    #                                        Minister's Parry Block): the hit / clash that starts one does not count
    #                                        as interrupting it (tools.attack_range_build.segment); later ones do
    # stage B: the spec's branch values may be callables (x=, y=, s=, vx=, hero_x=, hero_y=) -> branch, picked at
    # that state's first frame (attack_range.Segmenter); a Decision rule may return (s, L, extras): s 0 = the
    # observed facing at the decision frame, extras are kept in the decision (Inst.dec)

    @property
    def body_names(self) -> tuple:
        return (self.body,) if isinstance(self.body, str) else tuple(self.body)
