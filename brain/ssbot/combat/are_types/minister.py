"""Minister (Song Administrator): attack-range type (Task "attack range: all types", stage B). Families from the v2
classification (docs/plans/forum_zones_v2.md sec. 1.2, C:/ssbot/data/m2_forum_v2/workflow_result.json) and the
Control FSM decode (C:/ssbot/sandbox/reactive_scripts/out/Song_Administrator.txt):

  MI_CHARGE   Attack Antic (0.48-0.52 s; FaceObjectV2, then GetAngleToTarget2D to the hero + (0, 1.5) clamped to
              +-45 deg on the facing side; a -14 u/s recoil along it, decel 0.925; collider Collider AttackAntic) >
              Attack (33 u/s along the aim, the Slash Collider, multi-hit, exported with dealt 0) > Multihit (it caught
              the hero: stops 0.4 s) or Attack End. The aim is decided at the antic START, so the branch is the aim
              bin (15 deg) from its first frame: one template per bin, in its facing
  MI_COUNTER  Parry Block (a blocked hit in the parry stance: HIT_COND; faces the hero at its entry, 20 u/s back and
              -4 down, then rising) > Parry Slash 1-4 (one lunge, -45 u/s forward and -20 down, in four segments,
              ParrySlash Hit 1-4) > Parry Slash End: drawn from the Parry Block entry in its facing
  MI_EVADE    Evade Antic > Evade (25 u/s away + 5 up, 0.4 s): the body; the direction is fixed at the Evade entry:
              branch "same" / "turned" against the antic start's facing (the union during the antic)
  MI_ENTRY    Fly In: the body falling in
  idle        Chase, Retreat?, Parry Stance Antic / Parry Stance / Parry Stance End (the stance: no attack without a
              blocked hit), the 0 s choice states: the exact body now (every enabled body collider: the main one and
              the per-state Collider Fly / Evade / ParryStance / ParryAntic / AttackAntic)

The caches keep AABBs: the attack rotates the whole Minister to its aim, so its rotated colliders (the body, the
Slash Collider) are their AABBs on both sides of the error (estimate and truth) - larger than the real polygons.
"""
import math

import numpy as np

from ssbot.combat.are_spec import EnemySpec

AIM_OFFSET_Y = 1.5
AIM_CLAMP = 45.0
AIM_EDGES = (-37.5, -22.5, -7.5, 7.5, 22.5, 37.5)
AIM_NAMES = ("a-45", "a-30", "a-15", "a0", "a+15", "a+30", "a+45")


def aim_of(x: float, y: float, s: int, hero_x: float, hero_y: float) -> float:
    """The charge's aim at the Attack Antic entry: the angle (deg, facing frame: + = up) to the hero + (0, 1.5),
    clamped to +-45 (a hero behind clamps to the nearer edge)."""
    a = math.degrees(math.atan2(float(hero_y) + AIM_OFFSET_Y - y, (float(hero_x) - x) * s))
    return min(max(a, -AIM_CLAMP), AIM_CLAMP)


# u: 59 of the 1,798 R0 dev evades turned, all with the hero within 2.09 u in front at the antic start (beyond it
# the direction is certain from the start; the CH_HOP branch rule's idea)
TURN_DU_MAX = 2.09


def evade_start(x=0.0, s=1, hero_x=None, **_):
    """At the antic start: "same" when the hero is too far in front to cross before the Evade entry, else pending."""
    if hero_x is None:
        return None
    return "same" if (float(hero_x) - x) * s > TURN_DU_MAX else None


def evade_branch(s=1, s0=1, **_):
    """The evade's direction at the Evade entry (away from the hero): "same" as the antic start's facing or "turned"."""
    return "same" if s == s0 else "turned"


def charge_branch(x=0.0, y=0.0, s=1, vx=None, hero_x=None, hero_y=None, **_):
    """The aim bin at the Attack Antic's first frame."""
    if hero_x is None or hero_y is None:
        return None
    return AIM_NAMES[int(np.searchsorted(AIM_EDGES, aim_of(x, y, s, hero_x, hero_y), side="right"))]


SPEC = EnemySpec(
    type_key="Song Administrator", short="Minister",
    fam_states={
        "MI_CHARGE": frozenset({"Attack Antic", "Attack", "Multihit", "Attack End"}),
        "MI_COUNTER": frozenset({"Parry Block", "Parry Slash 1", "Parry Slash 2", "Parry Slash 3", "Parry Slash 4",
                                 "Parry Slash End"}),
        "MI_EVADE": frozenset({"Evade Antic", "Evade"}),
        "MI_ENTRY": frozenset({"Fly In"}),
    },
    start={"Attack Antic": "MI_CHARGE", "Parry Block": "MI_COUNTER", "Evade Antic": "MI_EVADE",
           "Evade": "MI_EVADE", "Fly In": "MI_ENTRY"},
    primary={"MI_CHARGE": "Attack Antic", "MI_COUNTER": "Parry Block", "MI_EVADE": "Evade Antic",
             "MI_ENTRY": "Fly In"},
    branch={"MI_CHARGE": {"Attack Antic": charge_branch},
            "MI_EVADE": {"Evade Antic": evade_start, "Evade": evade_branch}},
    branches={"MI_CHARGE": AIM_NAMES, "MI_COUNTER": ("main",), "MI_EVADE": ("same", "turned"),
              "MI_ENTRY": ("main",)},
    hit_started=frozenset({"MI_COUNTER"}),
    state_gate=True,
    aim=frozenset(),
    body=("Song Administrator", "Song Administrator (1)", "Song Administrator (2)", "Collider Fly",
          "Collider Evade", "Collider ParryStance", "Collider ParryAntic", "Collider AttackAntic"),
    table="attack_range_minister",
    # the facing of flipX from the Slash Collider (in front at every aim; the ParrySlash Hits vote the wrong way:
    # flipX 1 faces the hero at +x in 2625 / 2625 R0 dev Attack Antic entries)
    face_names=("Slash Collider",),
    left_out=(
        ("Chase / Retreat? / Parry Stance", "the next attack is picked later (group 2); the parry stance has no "
         "attack without a blocked hit: its counter is drawn only from the Parry Block entry"),
    ),
)

SESSIONS = ("20261004_002749", "20261005_160435", "20261008_231544", "20261009_085824", "20261009_161454")
CASES = ()
