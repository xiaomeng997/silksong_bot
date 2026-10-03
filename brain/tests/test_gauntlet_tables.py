"""Multi-enemy behaviour tables (ssbot.knowledge.gauntlet_tables) on synthetic STATEs: one stream per enemy entity,
two enemies of one type told apart by their GameObject names, a hazard owned by the enemy whose attack spawned it
(also when it arms after the attack ended), a source naming only a collider child, a blocked stretch attributed frame
by frame, the idle family between attacks, a kill as the death, and the radius aliases of the shared "damager"."""
from pathlib import Path

from ssbot.knowledge.behaviour_tables import BehaviourSpec, Fight
from ssbot.knowledge.gauntlet_tables import FORUM_SPECS, GauntletBuilder, hazard_type

SPEC = BehaviourSpec(
    enemy="Foe", scene="Test", boss_type="Foe", control_fsm="Control", hp=10, dormant=("Init",), death_states=(),
    attack_starts={"Antic": "F_HIT"}, decision_states=("Idle",), dir_states={}, directed=("F_HIT", "F_IDLE"),
    phase_marks={}, phases={"P1": "all"}, initial_phase="P1", world_fixed=(), flip_mirror=(-1, 1),
    idle_family="F_IDLE", death_on_kill=True, projectiles=("Ball",), spawns=(("Ball", ("F_HIT",)),),
    spawn_window_s=2.0)
DMG = {"dealt": 1, "eff": 1, "hazard_type": 1, "flags": 0, "parry": 4, "parryable": False, "can_cause_damage": True}


def _box(name, x, y, w=1.0, h=1.0, enabled=True):
    return {"kind": "box", "name": name, "enabled": enabled, "layer": 11, "damage": dict(DMG),
            "verts_world": [x - w / 2, y - h / 2, x + w / 2, y - h / 2, x + w / 2, y + h / 2, x - w / 2, y + h / 2]}


def _foe(iid, name, x, state, child=None):
    cols = [_box(name, x, 5.0)]
    if child:
        cols.append(_box(child, x + 1.0, 5.0))
    return {"iid": iid, "type_key": "Foe", "src": 3, "pos": [x, 5.0, 0.0], "hp": 10, "is_dead": False,
            "flipX": False, "hidden": False, "fsms": [{"name": "Control", "state": state}], "colliders": cols}


def _ball(x, armed=True):
    c = _box("Ball(Clone)", x, 4.0, 0.5, 0.5, enabled=armed)
    return {"iid": 99, "type_key": "Ball", "src": 34, "pos": [x, 4.0, 0.0], "flipX": False, "hidden": False,
            "fsms": [{"name": "Control", "state": "Fly" if armed else "Init"}], "colliders": [c]}


def _fsm(ent, obj, frm, to):
    return {"k": "fsm", "d": {"iid": ent, "ent": ent, "obj": obj, "fsm": "Control", "from": frm, "to": to,
                              "t_in_prev": None, "rt_in_prev": None}}


def _states():
    st = {1: "Init", 2: "Init"}
    out = []
    for f in range(1, 121):
        ev = []
        if f == 2:
            ev += [_fsm(1, "Foe", "Init", "Idle"), _fsm(2, "Foe (1)", "Init", "Idle")]
            st = {1: "Idle", 2: "Idle"}
        if f == 10:
            ev.append(_fsm(2, "Foe (1)", "Idle", "Antic"))
            st[2] = "Antic"
        if f == 20:
            ev.append(_fsm(2, "Foe (1)", "Antic", "Idle"))
            st[2] = "Idle"
        hero_x = 20.0 if f < 60 else 10.0
        ents = [_foe(1, "Foe", 10.0, st[1], child="Hand"), _foe(2, "Foe (1)", 20.0, st[2])]
        if 30 <= f <= 70:      # spawned by Foe (1)'s attack, arms 10 frames after it ended
            ents.append(_ball(21.0 + 0.1 * (f - 30)))
        if f == 40:
            ev.append({"k": "damage", "d": {"source": "Wave 1/Foe (1)", "amount": 1}})
        if f == 45:
            ev.append({"k": "damage", "d": {"source": "Ball(Clone)", "amount": 1}})
        if f == 64:   # a stretch of three blocked frames on Foe's child collider, reported when it ends
            ev.append({"k": "damage_blocked", "d": {"source": "Colliders/Hand", "first_f": 62, "last_f": 64}})
        if f == 90:
            ev.append({"k": "hit", "d": {"ent": 1, "type_key": "Foe", "dead": True, "hp_after": 0, "dmg": 10}})
        out.append({"f": f, "dt": 1 / 60, "hero": {"pos": [hero_x, 5.0], "box": [hero_x - 0.25, 4.0,
                                                                                  hero_x + 0.25, 6.0]},
                    "ents": ents, "ev": ev})
    return out


def test_one_stream_per_enemy_and_attribution():
    g = GauntletBuilder({"Foe": SPEC})
    info = g.scan(Fight("states", Path("."), 1, 120, "synthetic"), _states())
    assert info["subjects"] == {"Foe": 2}
    b = g.builders["Foe"]
    by_fight = {}
    for i in b.instances:
        by_fight.setdefault(i.fight.split("#")[-1], []).append((i.family, i.end))
    # Foe (1): idle, its attack, idle again; Foe: idle until the kill
    assert by_fight["2"] == [("F_IDLE", "chain"), ("F_HIT", "rest"), ("F_IDLE", "fight_end")]
    assert by_fight["1"] == [("F_IDLE", "death")]
    contacts = {(c.f, c.fight.split("#")[-1]): c for c in b.contacts}
    assert contacts[(40, "2")].inst.family == "F_IDLE"
    ball = contacts[(45, "2")]   # the ball armed after Foe (1)'s attack ended: it belongs to that attack
    assert ball.tk == "Ball" and ball.inst.family == "F_HIT"
    for ff in (62, 63, 64):      # only Foe exports a collider named "Hand"
        c = contacts[(ff, "1")]
        assert c.kind == "blocked" and c.exported and c.src == "Foe/Colliders/Hand"
    assert len(b.contacts) == 5


def test_damager_radius_aliases_and_forum_specs():
    circle = {"type_key": "damager", "colliders": [{"kind": "circle", "r": 2.1662, "verts_world": [0, 0]}]}
    assert hazard_type(circle) == "rune bomb small"
    circle["colliders"][0]["r"] = 7.19
    assert hazard_type(circle) == "rune slam"
    circle["colliders"][0]["r"] = 1.0
    assert hazard_type(circle) == "damager"
    assert set(FORUM_SPECS) == {"Song Heavy Sentry", "Song Handmaiden", "Song Administrator", "Song Pilgrim Maestro",
                                "Song Automaton Tiny", "Song Reed", "Song Pilgrim 01", "Song Pilgrim 03",
                                "Pilgrim 03 Song"}
    for s in FORUM_SPECS.values():   # no state is both an attack start and a decision state
        assert not set(s.attack_starts) & set(s.decision_states), s.enemy
        assert not set(s.attack_starts) & set(s.dormant), s.enemy
