"""Offline checks of the "ents" / "fsm" readers against hand-built STATE fragments (msgpack round-trip)."""
import msgpack

from ssbot.ipc import ents


def _entity(**over) -> dict:
    e = {
        "iid": -1234, "type_key": "Bone Hunter", "category": "enemy", "src": 1 | 2, "layer": 11,
        "pos": [10.0, 5.0, 0.0], "vel": [1.5, 0.0], "gravity_scale": 1.0, "hp": 30, "is_dead": False, "inv": False,
        "fsms": [{"name": "Control", "state": "Idle", "t": 0.25}],
        "anim": {"clip": "Idle", "frame": 2, "n": 6}, "flipX": True, "render_aabb": [9.0, 4.0, 11.0, 6.5],
        "colliders": [
            {"kind": "box", "verts_world": [9.5, 4.0, 10.5, 4.0, 10.5, 6.0, 9.5, 6.0], "enabled": True, "layer": 11,
             "damage": {"dealt": 1, "eff": 1, "hazard_type": 1, "flags": 0, "parry": 4, "parryable": True,
                        "can_cause_damage": True}},
            {"kind": "circle", "verts_world": [0.0] * 16, "enabled": False, "layer": 13, "r": 3.0, "damage": None},
        ],
    }
    e.update(over)
    return e


def _roundtrip(obj):
    return msgpack.unpackb(msgpack.packb(obj, use_single_float=True), raw=False, strict_map_key=False)


def test_valid_entity_survives_msgpack():
    e = _roundtrip(_entity())
    assert ents.validate_entity(e) == []
    assert ents.collider_points(e["colliders"][0]) == [(9.5, 4.0), (10.5, 4.0), (10.5, 6.0), (9.5, 6.0)]
    assert ents.is_threat(e["colliders"][0])
    assert not ents.is_threat(e["colliders"][1])
    assert ents.bits(e["src"], ents.SRC_BITS) == ["health_manager", "damage_hero"]
    assert "Bone Hunter [enemy; health_manager+damage_hero]" in ents.describe(e)


def test_validation_catches_schema_drift():
    bad = _entity(category="monster", pos=[1.0, 2.0])
    del bad["inv"]
    bad["colliders"][0]["verts_world"] = [1.0, 2.0, 3.0]
    bad["colliders"][1].pop("r")
    bad["anim"] = {"clip": "Idle", "frame": 6, "n": 6}
    errs = ents.validate_entity(bad)
    joined = "\n".join(errs)
    for needle in ("missing keys ['inv']", "bad category", "pos not", "collider 0: verts_world",
                   "collider 1: circle needs", "anim frame 6"):
        assert needle in joined, (needle, errs)


def test_hazard_without_hp_is_valid():
    e = _entity(category="hazard", src=2 | 32, hp=None, is_dead=None, inv=None, vel=None, gravity_scale=None,
                anim=None, render_aabb=None, fsms=[])
    assert ents.validate_entity(e) == []
    e["is_dead"] = False
    assert "hp and is_dead disagree on presence" in ents.validate_entity(e)


def test_fsm_events_and_counts():
    state = _roundtrip({
        "f": 100,
        "ev": [
            {"k": "fsm", "f": 99, "q": 1, "d": {"iid": 5, "ent": 5, "obj": "Bone Hunter (2)", "fsm": "Control",
                                                  "from": "Idle", "to": "Attack", "t_in_prev": 1.25}},
            {"k": "damage", "f": 99, "q": 2, "d": {"x": 1}},
            {"k": "fsm", "f": 100, "q": 3, "d": {"iid": 6, "ent": 5, "obj": "Hitbox", "fsm": "FSM",
                                                   "from": None, "to": "Start", "t_in_prev": None}},
        ],
        "ents": [_entity(), _entity(iid=7, category="hazard", hp=None, is_dead=None)],
    })
    evs = ents.fsm_events(state)
    assert [e["to"] for e in evs] == ["Attack", "Start"]
    assert evs[0]["f"] == 99 and set(evs[0]) - {"f"} == ents.FSM_EVENT_KEYS
    assert evs[1]["from"] is None
    assert ents.count_categories(state["ents"]) == {"enemy": 1, "hazard": 1}


def test_hazard_names():
    assert ents.hazard_name(2) == "SPIKES"
    assert ents.hazard_name(10) == "STEAM"
    assert ents.hazard_name(-1) == "?-1"
