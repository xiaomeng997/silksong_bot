"""Route bosses (Task route bosses): FightTap on bosses without a death state in Control (Lace 1: the kill is the hit
event), the exact boss match (Trobbio's bombs run their own "Control"), the tap following a rotated encounter, and the
encounters / behaviour specs agreeing with each other."""
from ssbot.knowledge.behaviour_tables import SPECS
from ssbot.train.encounters import (BELL_BEAST, ENCOUNTERS, GRAND_MOTHER_SILK, LACE_1, ROUTE_BOSSES, TROBBIO,
                                    WIDOW)
from ssbot.train.episode import FightTap


class _Link:
    def __init__(self):
        self.subs = []

    def subscribe_state(self, fn) -> None:
        self.subs.append(fn)

    def feed(self, f: int, *evs: tuple[str, dict]) -> None:
        s = {"f": f, "ev": [{"k": k, "d": d} for k, d in evs]}
        for fn in self.subs:
            fn(s)


def _fsm(obj: str, frm, to: str) -> tuple[str, dict]:
    return "fsm", {"obj": obj, "fsm": "Control", "from": frm, "to": to}


def test_lace_kill_is_the_boss_hit_event_with_dead():
    link = _Link()
    tap = FightTap(link, LACE_1)
    link.feed(10, _fsm("Lace Boss1", "Dormant", "Refight"))
    assert tap.wake_frame == 10
    link.feed(20, ("hit", {"type_key": "Lace Boss1", "hp_before": 30, "hp_after": 25, "dead": False}))
    link.feed(30, ("hit", {"type_key": "Song Reed", "hp_before": 5, "hp_after": 0, "dead": True}))
    assert tap.death_frame is None
    link.feed(40, ("hit", {"type_key": "Lace Boss1", "hp_before": 5, "hp_after": -1, "dead": True}))
    link.feed(50, ("hit", {"type_key": "Lace Boss1", "hp_before": -1, "hp_after": -6, "dead": True}))
    assert tap.death_frame == 40


def test_lace_kill_after_the_lava_took_her_hp_below_zero():
    # LAVA DAMAGE subtracts HP in the FSM (no hit event); the next hit kills with hp_before already <= 0
    link = _Link()
    tap = FightTap(link, LACE_1)
    link.feed(10, _fsm("Lace Boss1", "Dormant", "Refight"))
    link.feed(20, ("hit", {"type_key": "Lace Boss1", "hp_before": 15, "hp_after": 10, "dead": False}))
    link.feed(30, _fsm("Lace Boss1", None, "Lava Damage"))
    assert tap.death_frame is None
    link.feed(40, ("hit", {"type_key": "Lace Boss1", "hp_before": -30, "hp_after": -35, "dead": True}))
    link.feed(41, ("hit", {"type_key": "Lace Boss1", "hp_before": -35, "hp_after": -40, "dead": True}))
    assert tap.death_frame == 40


def test_hit_event_does_not_kill_a_boss_with_death_states():
    link = _Link()
    tap = FightTap(link, BELL_BEAST)
    link.feed(5, ("hit", {"type_key": "Bone Beast", "hp_before": 5, "hp_after": 0, "dead": True}))
    assert tap.death_frame is None


def test_spawned_hazards_with_the_boss_prefix_are_not_the_boss():
    link = _Link()
    tap = FightTap(link, TROBBIO)
    link.feed(1, _fsm("Trobbio", "Wait Refight", "Start Pause"))
    link.feed(2, _fsm("Trobbio Bomb(Clone)", "Init", "Fling"))
    assert tap.control == "Start Pause"
    assert [t for _, _, t in tap.control_log] == ["Start Pause"]


def test_reset_follows_the_episode_encounter():
    link = _Link()
    tap = FightTap(link, LACE_1)
    tap.reset(TROBBIO)
    link.feed(1, _fsm("Trobbio", "Wait Refight", "Start Pause"))
    link.feed(2, _fsm("Trobbio", "Death Air", "Death Hit"))
    assert (tap.wake_frame, tap.death_frame) == (1, 2)


def test_route_specs_match_their_encounters():
    for enc in ROUTE_BOSSES:
        spec = SPECS[enc.name]
        assert ENCOUNTERS[enc.name] is enc and ENCOUNTERS[f"{enc.name}_low"].start_boss_hp is not None
        assert (spec.boss_type, spec.scene, spec.dormant, spec.death_states) == \
            (enc.boss_type, enc.scene, enc.dormant, enc.death_states)
        assert enc.name in spec.units and f"{enc.name}_low" in spec.units
        assert not set(spec.attack_starts) & set(spec.decision_states)
        assert not set(spec.attack_starts) & set(spec.dormant)
        assert spec.death_on_kill == enc.death_on_kill and spec.phase_fsm == enc.phase_fsm


def test_gms_wakes_in_attack_control_and_dies_in_phase_control():
    link = _Link()
    tap = FightTap(link, GRAND_MOTHER_SILK)
    link.feed(1, ("fsm", {"obj": "Silk Boss", "fsm": "Control", "from": "Dormant", "to": "Ready"}))
    assert tap.wake_frame is None
    link.feed(2, ("fsm", {"obj": "Silk Boss", "fsm": "Attack Control", "from": "Dormant", "to": "Init Pause"}))
    assert (tap.wake_frame, tap.control) == (2, "Init Pause")
    # the phase changes are no kill (HP Check -> Set P2 adds HP); Phase Control's Death Hit is
    link.feed(3, ("fsm", {"obj": "Silk Boss", "fsm": "Phase Control", "from": "HP Check 1", "to": "Set P2"}))
    link.feed(4, ("hit", {"type_key": "Silk Boss", "hp_before": 3, "hp_after": -2, "dead": True}))
    assert tap.death_frame is None
    link.feed(5, ("fsm", {"obj": "Silk Boss", "fsm": "Phase Control", "from": "HP Check 6", "to": "Death Hit"}))
    assert tap.death_frame == 5 and tap.control == "Init Pause"


def test_widow_fake_death_is_not_the_kill():
    link = _Link()
    tap = FightTap(link, WIDOW)
    link.feed(1, _fsm("Spinner Boss", "Dormant", "Set Intro Pos"))
    link.feed(2, _fsm("Spinner Boss", "Idle", "Death Stagger F"))
    assert (tap.wake_frame, tap.death_frame) == (1, None)
    link.feed(3, _fsm("Spinner Boss", "Rage Idle", "Death Stagger"))
    assert tap.death_frame == 3


def test_taunt_starts_widow_and_gms():
    for enc in (WIDOW, GRAND_MOTHER_SILK):
        assert enc.intro.__qualname__.startswith("taunt_intro")
    assert SPECS["GMS"].phase_fsm == "Phase Control" and SPECS["Widow"].phase_fsm == ""


def test_gms_dash_slash_hits_are_the_boss():
    # "DashSlash Effect/SlashHit 1-5" hits do not pass through "Silk Boss" in their source path, but their polys are
    # the boss's colliders: they belong to the boss (its current attack, GM_DASH), not outside every attack
    from ssbot.knowledge.behaviour_tables import BehaviourBuilder, FightScanner
    spec = SPECS["GMS"]
    sc = FightScanner(spec, "t", BehaviourBuilder(spec))
    assert sc._source_tk("DashSlash Effect/SlashHit 5") == spec.boss_type
    assert sc._source_tk("DashSlash End Effect/SlashHit 1") == spec.boss_type
    assert sc._source_tk("Sprites/Sprite type 2") is None
    assert FightScanner(SPECS["Widow"], "t", BehaviourBuilder(SPECS["Widow"]))._source_tk("DashSlash Effect/x") is None
