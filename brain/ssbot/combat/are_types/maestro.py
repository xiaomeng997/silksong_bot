"""Maestro (Song Pilgrim Maestro): attack-range type (Task "attack range: all types", stage B). Families and rules
from the v2 classification (docs/plans/forum_zones_v2.md sec. 1.3, C:/ssbot/data/m2_forum_v2/workflow_result.json),
first-FSM states as the tracker sees them:

  MA_SLASH   Fire Antic (0.68-0.73 s; recoil 15 u/s back, exactly 2.37 u; sends FIRE to one ready Tiny) > Slash 1 >
             Slash 2 > Slash End > Slash Recover F / Slash Recover. The SIDE is decided at the Slash 1 entry, the first
             damage frame: the hero's side then (7922 / 7922; at the Fire Antic entry only 95.4 %). Until then it is a
             pending aim (group 2): only the antic body (with its recoil) is drawn; from Slash 1 the decided slash
             (Slash Hit 1 3.18 x 2.38, Slash Hit 2 3.53 x 2.45), anchored at the Slash 1 frame in the decided side.
  MA_DEFEND  Defend Start > Defending > Defend End: the body (Defending tracks the hero to 4 u at <= 5 u/s); the
             Tinies' orbit is the Tiny type's (are_types/tiny.py)
  MA_SUMMON  Call > Summon > Summon Recover: the body (no attack collider); spawns Tinies
  MA_ENTRY   Fly In: the body descending 10 u
  idle       Forum Fly / Fly / Chase (and the 0 s Summon? / Attack Choice): the exact body now

The body damagers are "Song Pilgrim Maestro" and "Song Pilgrim Maestro (1)" (1.76 x 1.95). A hit on it starts Summon?
(an attack decision, no counter collider): nothing hit-conditioned to draw. "Fly In Ready" (a later wave's member
waiting) is parked by the default PARKED.
"""
from ssbot.combat.are_spec import Decision, EnemySpec


def side_rule(x: float, y: float, vx, hero_x, hero_y) -> tuple[int, float]:
    """The slash's side at the Slash 1 entry: the hero's side then (L unused: the displacement is the template's)."""
    return (1 if (hero_x is None or hero_x >= x) else -1), 1.0


SLASH_DECISION = Decision(states=frozenset({"Slash 1"}), rule=side_rule, scale=False)

# Defending keeps 4 u from the hero (DistanceFlyHorizontal, <= 5 u/s): toward or away from the hero by where it is, so
# the template's median path misses it (R0 fresh k 12 coverage 79 %, the miss behind p95 1.95 u); its velocity now
# carries it (the custom hook below).
TRACKING = frozenset({"Defend Start", "Defending", "Defend End"})


def _body(view) -> list:
    """Its body colliders now (CustomView.body: the tracker / the builder fill it)."""
    return list(view.body or [])


def custom(view):
    """(the body now carried by its velocity, None) in MA_DEFEND; else (None, None)."""
    if view.st not in TRACKING:
        return None, None
    from ssbot.combat.attack_range import carry_body
    body = _body(view)
    if not body:
        return None, None
    tau = max(view.t - view.T, 0.0)
    # kept inside the arena like the idle bodies (attack_range.carry_body; always carried: MA_DEFEND's own rule)
    return carry_body(body, (view.vx or 0.0, view.vy or 0.0), tau, view.tab.cell, on=True), None

SPEC = EnemySpec(
    type_key="Song Pilgrim Maestro", short="Maestro",
    fam_states={
        "MA_SLASH": frozenset({"Fire Antic", "Slash 1", "Slash 2", "Slash End", "Slash Recover", "Slash Recover F"}),
        "MA_DEFEND": frozenset({"Defend Start", "Defending", "Defend End"}),
        "MA_SUMMON": frozenset({"Call", "Summon", "Summon Recover"}),
        "MA_ENTRY": frozenset({"Fly In"}),
    },
    start={"Fire Antic": "MA_SLASH", "Defend Start": "MA_DEFEND", "Call": "MA_SUMMON", "Fly In": "MA_ENTRY"},
    primary={"MA_SLASH": "Fire Antic", "MA_DEFEND": "Defend Start", "MA_SUMMON": "Call", "MA_ENTRY": "Fly In"},
    branch={},
    branches={"MA_SLASH": ("main",), "MA_DEFEND": ("main",), "MA_SUMMON": ("main",), "MA_ENTRY": ("main",)},
    aim=frozenset(),
    body=("Song Pilgrim Maestro", "Song Pilgrim Maestro (1)", "Song Pilgrim Maestro (2)"),
    table="attack_range_maestro",
    face_names=("Slash Hit",),
    decide={"MA_SLASH": SLASH_DECISION},
    state_gate=True,
    custom=custom,
    left_out=(
        ("Fire Antic", "MA_SLASH's side is pending until the Slash 1 entry (its first damage frame, 0.68-0.73 s): "
         "only the antic body and its 2.37 u recoil are drawn, the slash from Slash 1 on"),
        ("Forum Fly / Fly / Chase / Summon? / Attack Choice", "the next attack is picked at 0 s (group 2)"),
    ),
)

SESSIONS = ("20261005_160435", "20261008_231544", "20261009_085824", "20261009_161454")
CASES = ()
