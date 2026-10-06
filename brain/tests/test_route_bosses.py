"""Route bosses (Task route bosses): FightTap on bosses without a death state in Control (Lace 1: the kill is the hit
event), the exact boss match (Trobbio's bombs run their own "Control"), the tap following a rotated encounter, and the
encounters / behaviour specs agreeing with each other."""
from ssbot.knowledge.behaviour_tables import SPECS
from ssbot.train.encounters import BELL_BEAST, ENCOUNTERS, LACE_1, ROUTE_BOSSES, TROBBIO
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
        assert spec.death_on_kill == enc.death_on_kill
