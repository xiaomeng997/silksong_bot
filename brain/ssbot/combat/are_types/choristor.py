"""Choristor (Song Pilgrim 03): the first attack-range type (approved by the person 2026-10-10, 'very accurate').
Families from the v2 classification (docs/plans/forum_zones_v2.md sec. 1); CH_JUMP lands at 1.04 x the hero's
offset at the antic start (the table's jump_fit); CH_HOP's direction is certain outside the R0 dev overlap
(branch_rule).
"""
from ssbot.combat.are_spec import EnemySpec

SPEC = EnemySpec(
    type_key="Song Pilgrim 03", short="Choristor",
    fam_states={
        "CH_SLASH": frozenset({"Slash Antic", "Slash Antic Jump", "Slash 1", "Slash 2", "Slash End", "Combo?",
                               "ComboSlash Antic1", "ComboSlash Antic2", "ComboSlash 1", "ComboSlash 2", "ComboSlash 3",
                               "Slash Recover"}),
        "CH_WHIP": frozenset({"Whip Antic", "Whip 1", "Whip 2", "Whip 3", "Whip 4", "Whip 5", "Whip 6", "Whip End",
                              "Multiwhip"}),
        "CH_JUMP": frozenset({"Jump Antic", "Wait for Ground", "Jump Launch", "Jump Rise", "Jump Spin", "Spin Slash",
                              "Spin Slash End", "Quick Land"}),
        "CH_HOP": frozenset({"Hop Antic", "Hop Back", "Hop Forward", "Hop Up", "Ground Check", "Hop Land",
                             "Cancel To Hop Back", "Hop Check"}),
        "CH_ENTRY": frozenset({"Battle Wake", "Enter Antic 2", "Enter Leap 2", "Enter Fall", "Enter Land",
                               "Enter Idle", "Enter Antic", "Enter Leap"}),
    },
    start={"Slash Antic": "CH_SLASH", "Whip Antic": "CH_WHIP", "Jump Antic": "CH_JUMP", "Hop Antic": "CH_HOP",
           "Cancel To Hop Back": "CH_HOP", "Battle Wake": "CH_ENTRY", "Enter Antic 2": "CH_ENTRY",
           "Enter Leap 2": "CH_ENTRY"},
    primary={"CH_SLASH": "Slash Antic", "CH_WHIP": "Whip Antic", "CH_JUMP": "Jump Antic", "CH_HOP": "Hop Antic",
             "CH_ENTRY": "Battle Wake"},
    branch={"CH_SLASH": {"ComboSlash Antic1": "combo", "ComboSlash Antic2": "combo", "ComboSlash 1": "combo",
                         "ComboSlash 2": "combo", "ComboSlash 3": "combo", "Slash Recover": "single"},
            "CH_HOP": {"Hop Back": "back", "Cancel To Hop Back": "back", "Hop Forward": "forward", "Hop Up": "up"},
            # Multiwhip follows Whip k only when the whip caught the hero; a whip that runs to Whip 6 is plain
            "CH_WHIP": {"Multiwhip": "multi", "Whip 6": "plain", "Whip End": "plain"}},
    branches={"CH_SLASH": ("single", "combo"), "CH_HOP": ("back", "forward", "up"), "CH_WHIP": ("plain", "multi"),
              "CH_JUMP": ("main",), "CH_ENTRY": ("main",)},
    aim=frozenset({"CH_JUMP"}),
    body="Body Damager",
    table="attack_range_choristor",
    face_names=("Slash Hit", "Whip Hit 2"),
)

# the person's own frames (tools.attack_range_png)
SESSIONS = ("20261009_085824", "20261009_161454")
CASES = (("20261009_085824", 5690, "whip antic, frame 5690 (the person)"),
         ("20261009_161454", 2916, "Battle Idle, frame 2916 (the person)"))
