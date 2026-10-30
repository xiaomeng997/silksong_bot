"""Clapper (Song Heavy Sentry): attack-range type (Task "attack range: all types", the person 2026-10-10: "its danger
zone was far too big"). Families and rules from the v2 classification (docs/plans/forum_zones_v2.md sec. 1.8,
C:/ssbot/data/m2_forum_v2/workflow_result.json) and the first-FSM states the tracker sees:

  CC_SLAM       Slam Antic (0.8 s, turns to the hero) > Slam 0 > Slam 1 > Slam 2 > Slam Recover: 30 u/s lunge 2.1-4.8 u
  CC_EVADE      Evade Scuttle: 15 u/s backward for 0.35 s, body only; single, or double (entered again at once: 0.7 s)
  CC_CAST       Spell Antic > Cast 1 > Cast 2: no collider of its own; Cast 2 spawns the rune bombs (hazard below)
  CC_JUMP       Jump Antic > (Jump Aim) Jump > Air > Slam 2 > Slam Recover: the landing is decided at Jump Aim
                (0.48-0.52 s; the tracker sees Jump, 1 frame, then Air): x_land = x + 0.916 vx,
                vx = clamp(hero x - 5 s - x, +-12) facing the hero; vy 38; a landing predicted beyond x 19.5 / 45.5
                runs into the wall and lands early and short (the "wall" branch, known at the decision)
  CC_JUMP_CAST  Cast Slam Antic > Cast Slam Antic 2 > Jump > Air > Slam 2 > Slam Recover: the same jump (decided at
                0.88-0.93 s), then the rune slam (hazard below)
  CC_ENTRY      Drop In > Enter Land > Roar > Roar End: the body
  idle          Idle / Walk and the 0 s decision states: the exact body now (three box colliders)

Hazards (pooled "damager" objects; the damage events name them "rune bomb small(Clone)/damager", "rune slam ..."):
  rune bomb small  Cast 2 entry: circles r 2.166 at x_c + 4.2 m (abs(m) <= 9, where bombs ever stood: the walls and
                   the pool cut the row), floor + 0.65; ring abs(m) appears 10 abs(m) frames after Cast 2 and hurts
                   21 frames later for 5-17 frames (the table's measured window per ring); predicted from the Spell
                   Antic start with the Cast 2 time window before Cast 2 is seen
  rune slam        Slam 2 entry of a CC_JUMP_CAST (the landing): one octagon, apothem 7.187, 6.48 u left / 6.75 u right in front of the landing
                   at floor + 0.33, hurts 65 frames after the landing for p50 8 frames
"""
import math

from ssbot.combat import jump_behind as _jb
from ssbot.combat.are_spec import Decision, EnemySpec, HazardSpec

JUMP_GAIN = 0.916          # x_land - x = 0.916 vx (the flight's horizontal time)
JUMP_SHORT = 5.0           # the target stops 5 u short of the hero
JUMP_VX_MAX = 12.0
FLIGHT = frozenset({"Jump Aim", "Jump", "Air", "Charged?", "Slam Effects?", "Slam 2", "Slam Recover"})


def jump_rule(x: float, y: float, vx, hero_x, hero_y) -> tuple[int, float]:
    """(s, L) at the decision (Jump Aim; the tracker sees Jump / Air): s = facing the hero, L = the landing's u
    offset in that frame from the observed vx, or from the hero's x when vx is not known."""
    s = 1 if (hero_x is None or hero_x >= x) else -1
    if vx is not None and math.isfinite(vx) and abs(vx) > 1e-3:
        L = JUMP_GAIN * float(vx) * s
    else:
        du = 0.0 if hero_x is None else (hero_x - x) * s
        L = JUMP_GAIN * min(max(du - JUMP_SHORT, -JUMP_VX_MAX), JUMP_VX_MAX)
    if _jb.WALL_PUSH:
        # SSBOT_FORUM_JB_WALL (task 1v1 SP4): a take-off with its back within 4 u of a wall lands >= 4.4 u from it
        # (SP3: 334 jumps, 3.47 u once, p5 4.58): the arc meets the wall-top ledge and is pushed out
        L = _jb.push_l(x, s, L)
    return s, L


# a predicted landing beyond these x (u) runs into a wall: R0 dev, 41 of the 42 jumps that landed 2-13 frames early
# (and short) had it, against 29 of the 1,186 others; the "wall" branch is built from those 70, "open" from the rest
WALL_ZONE = (19.5, 45.5)


def jump_branch(x: float, s: int, L: float) -> str:
    xl = x + s * L
    return "wall" if (xl < WALL_ZONE[0] or xl > WALL_ZONE[1]) else "open"


JUMP_DECISION = Decision(states=frozenset({"Jump", "Air"}), rule=jump_rule, branch=jump_branch)

SPEC = EnemySpec(
    type_key="Song Heavy Sentry", short="Clapper",
    fam_states={
        "CC_SLAM": frozenset({"Slam Antic", "Slam 0", "Slam 1", "Slam Effects?", "Slam 2", "Slam Recover"}),
        "CC_EVADE": frozenset({"Evade Scuttle"}),
        "CC_CAST": frozenset({"Spell Antic", "Cast 1", "Cast 2"}),
        "CC_JUMP": frozenset({"Jump Antic"}) | FLIGHT,
        "CC_JUMP_CAST": frozenset({"Cast Slam Antic", "Cast Slam Antic 2", "Cast Jump"}) | FLIGHT,
        "CC_ENTRY": frozenset({"Drop Antic", "Drop In", "Enter Land", "Roar", "Roar End"}),
    },
    start={"Slam Antic": "CC_SLAM", "Evade Scuttle": "CC_EVADE", "Spell Antic": "CC_CAST", "Jump Antic": "CC_JUMP",
           "Cast Slam Antic": "CC_JUMP_CAST", "Drop Antic": "CC_ENTRY", "Drop In": "CC_ENTRY"},
    primary={"CC_SLAM": "Slam Antic", "CC_EVADE": "Evade Scuttle", "CC_CAST": "Spell Antic", "CC_JUMP": "Jump Antic",
             "CC_JUMP_CAST": "Cast Slam Antic", "CC_ENTRY": "Drop In"},
    branch={},
    branches={"CC_SLAM": ("main",), "CC_EVADE": ("single", "double"), "CC_CAST": ("main",),
              "CC_JUMP": ("open", "wall"), "CC_JUMP_CAST": ("open", "wall"), "CC_ENTRY": ("main",)},
    # Evade Scuttle runs 21-22 frames (5.1 u); in 7 % of R0 dev it is entered again at once (a second evade, 40-44
    # frames, 10.8 u): known when its time in state restarts (or it runs over 26 frames), single when it is left
    branch_dur={"CC_EVADE": ("Evade Scuttle", 26, "single", "double")},
    # each bin's shape is kept per state: the rare early landings' slam collider is not drawn while it is in the air
    state_gate=True,
    aim=frozenset(),
    body=("Song Heavy Sentry", "Song Heavy Sentry (2)", "Song Heavy Sentry (3)"),
    table="attack_range_clapper",
    face_names=("Slam Collider",),
    decide={"CC_JUMP": JUMP_DECISION, "CC_JUMP_CAST": JUMP_DECISION},
    hazards=(
        HazardSpec(name="rune bomb small", shape="row", fams=frozenset({"CC_CAST"}), state="Cast 2", radius=2.166,
                   box_w=4.332, spacing=4.2, m_max=9, dv=-3.8, pre=True, on0=21.0, on_step=10.0),
        HazardSpec(name="rune slam", shape="octagon", fams=frozenset({"CC_JUMP_CAST"}), state="Slam 2", radius=7.187,
                   box_w=14.374, du=6.48, dv=-3.27, on0=65.0, du_by_face=(6.48, 6.75)),
    ),
    left_out=(
        ("Jump Antic", "CC_JUMP's landing is a pending aim until Jump Aim (0.48-0.52 s): only the antic body is drawn"),
        ("Cast Slam Antic / Cast Slam Antic 2", "CC_JUMP_CAST's landing is pending until Jump Aim (0.88-0.93 s)"),
        ("Idle / Walk / Close Range / Far Range / Dmg Attack", "the next attack is picked at 0 s (group 2); a hit in "
         "Idle only shortens the wait (no counter collider)"),
    ),
)

SESSIONS = ("20261005_160435", "20261008_231544", "20261009_085824", "20261009_161454")
CASES = ()
