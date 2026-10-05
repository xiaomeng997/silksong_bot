"""Static facts of the High Halls Forum gauntlet (Hang_04 / Hang_04_boss) for the run-time modules (DESIGN §8.2: the
final-run packages may not import the behaviour builder or the oracle-side encounter code, so the few facts the
multi-enemy forecast needs are kept here; tests/test_multi_forecast.py holds them to ssbot.knowledge.gauntlet_tables
.FORUM_SPECS and ssbot.train.encounters.FORUM_WAVES). Sources: docs/facts/1.0.30000/forum.md §2 (waves, spawn
points), §8 (arena), §9 (types), §13.2 (the moves the Control FSMs can never reach).

    FORUM_TYPES["Song Heavy Sentry"].idle_family     # "CC_IDLE"
    FORUM_WAVES[6].members                           # (("Song Pilgrim Maestro", 20.51, 10.87), ...)
    HAZARD_OWNER["Throwing Bell"]                    # "Pilgrim 03 Song"
"""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ForumType:
    type_key: str                                   # the oracle's EntityRegistry.TypeKey ("Song Heavy Sentry")
    enemy: str                                      # the behaviour table's file stem ("ChoirClapper")
    name: str                                       # the game's journal name (forum.md §9.1)
    control_fsm: str
    hp: float
    prefix: str                                     # family prefix ("CC": CC_IDLE, CC_ENTRY)
    death_states: tuple[str, ...] = ()
    waiting: tuple[str, ...] = ()                   # Control states before the enemy takes part (BehaviourSpec.dormant)
    spawns: tuple[tuple[str, tuple[str, ...]], ...] = ()   # hazard type -> the families that throw it
    hazard_rest: tuple[str, ...] = ("Init", "Dormant")     # hazard FSM states that cannot hurt (BehaviourSpec.rest)
    pooled: bool = False                            # killed instances come back under the same iid (the Tinies)

    @property
    def idle_family(self) -> str:
        return f"{self.prefix}_IDLE"

    @property
    def entry_family(self) -> str:
        return f"{self.prefix}_ENTRY"

    @property
    def hazards(self) -> tuple[str, ...]:
        return tuple(h for h, _ in self.spawns)


FORUM_TYPES: dict[str, ForumType] = {t.type_key: t for t in (
    ForumType("Song Heavy Sentry", "ChoirClapper", "Choir Clapper", "Control", 230, "CC",
              waiting=("Init", "Rest", "On-plane Rest", "Start Idle", "Start Battle?", "Start Battle 2"),
              spawns=(("rune bomb small", ("CC_CAST",)), ("rune slam", ("CC_JUMP_CAST",))),
              hazard_rest=("Init", "Dormant", "Idle")),
    ForumType("Song Handmaiden", "Clawmaiden", "Clawmaiden", "Control", 48, "CM",
              death_states=("Zero HP", "Die", "Burn Death", "Sim Death"),
              waiting=("Init", "Pause", "Respawner?", "Rest", "Silk?", "Silkless", "Set FG", "Set BG", "Off Plane",
                       "Battle Ready", "Burned?", "Wake Away Pause", "Away"),
              spawns=(("Spear", ("CM_SPIN",)), ("handmaiden_spear_silk_explosion", ("CM_SPIN",))),
              hazard_rest=("Init", "Dormant", "Idle", "Deactivate")),
    ForumType("Song Administrator", "Minister", "Minister", "Control", 60, "MI",
              waiting=("Init", "Fly In Ready", "Rest Ground", "Rest Wall")),
    ForumType("Song Pilgrim Maestro", "Maestro", "Maestro", "Control", 65, "MA", death_states=("Death",),
              waiting=("Init", "Pause", "Fly In Pause", "Fly In Ready", "Start Idle", "Corpse Spawn", "Init Old")),
    ForumType("Song Automaton Tiny", "MaestroAutomaton", "Song Automaton Tiny", "Control", 28, "AT",
              death_states=("Death Fx",), waiting=("Dead", "Pause", "Die", "Set Pos", "Left"), pooled=True),
    ForumType("Song Reed", "Reed", "Reed", "Control", 55, "RE", death_states=("Death",),
              waiting=("Init", "Custom Target?", "Target Hero", "Custom Target", "Fly In Ready", "Sleep", "Off Plane?",
                       "FG", "BG", "Start Patrol", "Start Praying", "Preacher Pray", "Merchant Start",
                       "Fly In Instant"),
              spawns=(("Song Reed Pin Projectile", ("RE_THROW",)),),
              hazard_rest=("Init", "Dormant", "Stick", "Deactivate", "Recycle")),
    ForumType("Song Pilgrim 01", "Envoy", "Envoy", "Attack", 38, "EN", death_states=("Zero HP",),
              waiting=("Init", "Ambush Ready", "Sleep", "Off Plane?", "FG", "BG", "Custom Target?", "Target Hero",
                       "Custom Target", "Start Praying", "Create Noise")),
    ForumType("Song Pilgrim 03", "Choristor", "Choristor", "Attack", 55, "CH",
              waiting=("Init", "Wait", "Start Praying", "Preacher Pray", "Sleep", "Off Plane?", "FG", "BG",
                       "Custom Target?", "Target Hero", "Custom Target", "Pray Voice?", "FG Jump", "Set Battler")),
    ForumType("Pilgrim 03 Song", "ChoirBellbearer", "Choir Bellbearer", "Control", 35, "CB",
              waiting=("Init", "Fly In Ready", "Sleep", "Off Plane?", "FG", "BG", "Preacher Pray",
                       "Start Patrol Voice", "Fly In Instant"),
              spawns=(("Throwing Bell", ("CB_THROW",)),),
              hazard_rest=("Init", "Dormant", "Deactivate", "Recycle", "Break")),
)}

# thrown hazard type -> the enemy type that throws it
HAZARD_OWNER: dict[str, str] = {h: t.type_key for t in FORUM_TYPES.values() for h in t.hazards}
# hazards exported under one shared GameObject name ("damager"), told apart by their circle radius (forum.md §9.2)
HAZARD_ALIASES: dict[str, tuple[tuple[float, str], ...]] = {
    "damager": ((2.166, "rune bomb small"), (7.187, "rune slam"), (3.553, "handmaiden_spear_silk_explosion")),
}
ALIAS_TOL_U = 0.05

# Moves the Control FSMs can never reach (forum.md §13.2, R1: PlayMaker's SendEvent FINISHED fires before the action
# that would branch, or the branch's action is disabled in the scene bundle; checked on 2,407 Envoy "Hop Up?", 910
# Bellbearer "Rethrow?" and 794 Maestro "Attack Choice" exits): never walked, never placed. The Forum Envoy's entry is
# its ambush (default clip "Ambush"); the Wake states belong to the sleeping variant.
STRUCTURALLY_ABSENT: dict[str, frozenset[str]] = {
    "Song Pilgrim 01": frozenset(("HopSlash Antic", "Wake Pause", "Wake", "Black Thread Wake")),
    "Pilgrim 03 Song": frozenset(("Throw Antic Quick",)),
    "Song Pilgrim Maestro": frozenset(("Point Start",)),
}
ABSENT_FAMILIES: dict[str, frozenset[str]] = {
    "Song Pilgrim 01": frozenset(("EN_HOPSLASH", "EN_ENTRY")),
    "Song Pilgrim Maestro": frozenset(("MA_POINT",)),
}


@dataclass(frozen=True, slots=True)
class ForumWave:
    index: int
    name: str
    start_delay_s: float
    remaining_to_end: int
    members: tuple[tuple[str, float, float], ...]     # (GameObject name, spawn x, spawn y)
    active_from_load: bool = False                    # its enemies are in the scene before the battle (FSM waits)

    @property
    def types(self) -> tuple[str, ...]:
        return tuple(_type_key(n) for n, _, _ in self.members)


def _type_key(name: str) -> str:
    """EntityRegistry.TypeKey: the name without trailing " (n)" / "(Clone)" (ssbot.train.gauntlet.type_key)."""
    s = name
    while True:
        s = s.rstrip(" ")
        if s.endswith("(Clone)"):
            s = s[:-7]
            continue
        if s.endswith(")"):
            i = s.rfind("(")
            if 0 <= i < len(s) - 2 and s[i + 1:-1].isdigit():
                s = s[:i]
                continue
        return s or name


# Battle Scene.waves of Hang_04_boss (scene bundle; forum.md §2): startDelay, remainingEnemyToEnd, members with their
# spawn points (the GameObjects' initial positions); waves 1, 6 and 12 have activateEnemiesOnStart 0
FORUM_WAVES: tuple[ForumWave, ...] = (
    ForumWave(0, "Wave 1", 0.0, 0, (("Song Reed", 30.73, 12.53), ("Song Pilgrim 01", 44.92, 5.13),
                                     ("Song Pilgrim 03", 19.41, 4.53))),
    ForumWave(1, "Wave 2 - Call Ally", 1.0, 0, (("Song Pilgrim 03 (2)", 22.75, 4.53),
                                                 ("Song Pilgrim 03 (3)", 39.97, 4.53)), active_from_load=True),
    ForumWave(2, "Wave 3", 1.0, 2, (("Pilgrim 03 Song", 39.25, 10.96), ("Song Reed (1)", 21.37, 10.53))),
    ForumWave(3, "Wave 4", 0.5, 0, (("Song Handmaiden", 1.67, 46.23),)),
    ForumWave(4, "Wave 5 - Song Admins", 1.0, 1, (("Song Administrator", 40.68, 11.34),
                                                   ("Song Administrator (1)", 20.6, 11.34))),
    ForumWave(5, "Wave 6", 0.0, 0, (("Song Handmaiden", 1.67, 46.23),)),
    ForumWave(6, "Wave 7 - Maestro x 2", 1.0, 0, (("Song Pilgrim Maestro", 20.51, 10.87),
                                                   ("Song Pilgrim Maestro (1)", 42.51, 10.87)), active_from_load=True),
    ForumWave(7, "Wave 8 - Heavy Sentry", 1.5, 0, (("Song Heavy Sentry", 31.03, 25.73),)),
    ForumWave(8, "Wave 9", 3.0, 0, (("Song Reed (2)", 40.34, 11.16), ("Song Reed (3)", 21.44, 11.16),
                                     ("Pilgrim 03 Song", 31.05, 10.96))),
    ForumWave(9, "Wave 10", 1.0, 2, (("Song Pilgrim 03 (2)", 30.85, 4.95), ("Pilgrim 03 Song", 21.34, 10.96),
                                      ("Pilgrim 03 Song (1)", 39.25, 10.96))),
    ForumWave(10, "Wave 11", 0.5, 0, (("Song Handmaiden", 1.67, 46.23),)),
    ForumWave(11, "Wave 12", 1.0, 0, (("Pilgrim 03 Song (1)", 31.35, 12.43), ("Song Administrator", 40.68, 11.34),
                                       ("Song Administrator (1)", 20.6, 11.34))),
    ForumWave(12, "Wave 13 - Maestro", 2.0, 0, (("Song Pilgrim Maestro", 24.42, 10.87), ("Song Reed", 39.64, 10.9)),
              active_from_load=True),
    ForumWave(13, "Wave 14 - Finale", 2.0, 0, (("Song Heavy Sentry (2)", 21.03, 23.73),
                                                ("Song Heavy Sentry (3)", 42.03, 23.73))),
)
BATTLE_START_PAUSE_S = 0.75      # BattleScene.battleStartPause: StartBattle -> StartWave(0)
WAVE_CHECK_S = 1.0               # StartWave: DoCheckEnemies 1 s after a wave's activation
WAVE_TYPES = frozenset(t for w in FORUM_WAVES for t in w.types)

# arena (forum.md §8.1): the gates' inner faces, the floor
WALL_L, WALL_R, FLOOR_Y = 14.01, 48.99, 3.0
# the dome's lower edge (Roof Collider_Basic (2) / (1), world points left to right): bells and pins meet it
DOME = ((10.72, 14.41), (13.93, 14.19), (15.44, 14.99), (16.74, 16.14), (17.58, 16.24), (19.68, 17.32),
        (20.38, 17.75), (21.53, 17.87), (22.46, 19.00), (23.89, 20.36), (25.82, 21.77), (27.87, 22.66),
        (29.52, 23.02), (31.19, 23.15), (31.89, 23.31), (33.53, 22.95), (36.41, 21.81), (38.73, 20.23),
        (39.96, 18.69), (40.60, 17.85), (42.42, 17.10), (43.41, 16.95), (44.31, 16.51), (46.43, 15.86),
        (46.91, 15.05), (49.67, 14.28))


def dome_y(x: float) -> float:
    """The dome's lower edge height at x (piecewise linear; the end heights outside it)."""
    pts = DOME
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0) if x1 > x0 else max(y0, y1)
    return pts[-1][1]
