"""The middle-jump decision is about geometry and one observed move, not focus identity."""
import pytest

from ssbot.combat.tactics import gauntlet as G
from ssbot.core.worldstate import E
from tests.test_clapper_priority import manual, scene, step, change


def middle(xs=(22., 44.), hx=31., family=G.CC_JUMP):
    tac, ws, fc = scene(xs, hx)
    fc.horizon = 2.
    fc.known = True
    ws.hero.can = {"input": True, "dash": True, "harpoon": True}
    ws.hero.contact = E("GROUND")
    ws.res.silk = E(3)
    step(tac, ws, fc)
    change(fc, 7, family=family, state="Jump Antic" if family == G.CC_JUMP else "Cast Slam Antic", committed=True)
    ws.entities[0].phase = None  # Forum's OracleBackend() has no boss specs.
    ws.entities[0].fsm = [("Control", fc.subjects[0].state, .02)]
    return tac, ws, fc


def airborne(tac, ws, fc, land=25., face=1):
    change(fc, 7, state="Air")
    tac.jb_land[7] = (22., face, land, True)
    # A velocity-backed landing, with the current root still before it.
    ws.entities[0].vel = E(((land - 22.) / .916, 12.))
    ws.entities[0].fsm = [("Control", "Air", .02)]


def test_only_guide_when_arrival_and_future_middle_room_both_fit():
    tac, ws, fc = middle()
    out = step(tac, ws, fc)
    assert out.target == 7
    assert tac.last["clapper_middle"]["route"] == "guide"
    assert out.stance_x == pytest.approx(G.jump_behind.aim_spot(22., 1))
    # Same primary clock near its deadline: it must stop claiming it can guide.
    ws.entities[0].fsm = [("Control", "Jump Antic", .47)]
    out = step(tac, ws, fc)
    assert tac.last["clapper_middle"]["route"] == "hold"
    assert out.stance_x == pytest.approx(ws.hero.pos.v[0])


def test_cast_second_antic_does_not_restart_the_aim_clock():
    tac, ws, fc = middle(family=G.CC_JUMP_CAST)
    step(tac, ws, fc)
    origin = tac._clapper_priority["middle_jump"]["antic_at"]
    change(fc, 7, state="Cast Slam Antic 2")
    ws.entities[0].fsm = [("Control", "Cast Slam Antic 2", .01)]
    step(tac, ws, fc)
    assert tac._clapper_priority["middle_jump"]["antic_at"] == origin


def test_late_first_seen_secondary_antic_is_unknown_not_a_fresh_clock():
    tac, ws, fc = middle(family=G.CC_JUMP_CAST)
    change(fc, 7, state="Cast Slam Antic 2")
    ws.entities[0].fsm = [("Control", "Cast Slam Antic 2", .01)]
    step(tac, ws, fc)
    assert tac.last["clapper_middle"]["route"] == "hold"
    assert tac.last["clapper_middle"]["reason"] == "aim clock unknown"


@pytest.mark.parametrize("unready", ["input", "air", "dash"])
def test_guide_does_not_assume_a_dash_or_ground_input_is_available(unready):
    tac, ws, fc = middle()
    if unready == "air": ws.hero.contact = E("AIR")
    else: ws.hero.can[unready] = False
    step(tac, ws, fc)
    assert tac.last["clapper_middle"]["route"] == "hold"


@pytest.mark.parametrize("focus", [7, 8])
def test_locked_landing_with_room_selects_standing_monster_from_either_focus(focus):
    tac, ws, fc = middle()
    tac.goal.target = focus
    step(tac, ws, fc)
    airborne(tac, ws, fc)
    out = step(tac, ws, fc)
    assert out.target == 8
    assert tac.last["clapper_middle"]["route"] == "stand"
    assert 25.+G.JT["reach_j"] < out.stance_x < 43.
    assert out.entry_attack.kind == "side" and out.entry_attack.source == 7
    # Same jump cannot become a new rear-intercept after the target switch.
    for _ in range(tac.rules.period * 2):
        assert step(tac, ws, fc).target == 8
        assert not any(c["rule"] == "intercept" for c in tac.last["clapper_choices"])


def test_first_jump_without_locked_velocity_waits_instead_of_guessing_landing():
    tac, ws, fc = middle()
    step(tac, ws, fc)
    change(fc, 7, state="Jump")
    out = step(tac, ws, fc)
    assert tac.last["clapper_middle"]["route"] == "hold"
    assert tac.last["clapper_middle"]["reason"] == "locked landing unknown"
    # Task 179 (#296): a jumper in flight is never the hold target (live 786 2580..2606 drew her under its landing).
    assert out.target == 8


@pytest.mark.parametrize("what", ["clock", "body", "horizon", "occupied"])
def test_unknown_or_covered_future_room_never_authorizes_guidance(what):
    tac, ws, fc = middle()
    if what == "clock": ws.entities[0].fsm = None
    elif what == "body": ws.entities[1].dmg_boxes = []
    elif what == "horizon": fc.horizon = .05
    else: fc.default = 0.
    step(tac, ws, fc)
    info = tac.last.get("clapper_middle")
    assert info is None or info["route"] != "guide"


def test_middle_context_ends_at_new_move_not_target_switch():
    tac, ws, fc = middle()
    step(tac, ws, fc)
    token = tac._clapper_priority["middle_jump"]["move"]
    tac.goal.target = 8
    step(tac, ws, fc)
    assert tac._clapper_priority["middle_jump"]["move"] == token
    change(fc, 7, family=G.CC_IDLE, state="Idle", committed=False)
    step(tac, ws, fc)
    assert tac._clapper_priority["middle_jump"] is None


def test_both_jumping_or_hero_outside_does_not_start_middle_context():
    tac, ws, fc = middle()
    change(fc, 8, family=G.CC_JUMP, state="Jump Antic", committed=True)
    step(tac, ws, fc)
    assert tac._clapper_priority.get("middle_jump") is None
    tac, ws, fc = middle(hx=15.)
    step(tac, ws, fc)
    assert tac._clapper_priority.get("middle_jump") is None


@pytest.mark.parametrize("mirror", [False, True])
def test_closed_middle_compares_declared_destinations_and_requests_stomp_over_walker(mirror):
    xs, hx = ((41., 26.), 35.) if mirror else ((22., 37.), 28.)
    tac, ws, fc = middle(xs, hx, family=G.CC_JUMP_CAST)
    tac.pb.arena_x = (14.01, 48.99)
    step(tac, ws, fc)
    face, land = (-1, 38.) if mirror else (1, 25.)
    change(fc, 7, state="Air")
    tac.jb_land[7] = (xs[0], face, land, True)
    ws.entities[0].vel = E(((land-xs[0])/.916, 12.))
    out = step(tac, ws, fc)
    mid = tac.last["clapper_middle"]
    assert mid["route"] == "over" and out.target == 8
    assert out.entry_attack.kind == "stomp" and out.entry_attack.source == 7
    assert (out.stance_x-xs[1])*face > 1.
    assert not mid["path_checked"]
    assert all(e["certified"] is False for e in mid["endpoints"])
    assert "declared" in mid["reason"]  # a requested exit, not a predicted flight/hit


def test_under_wins_when_its_declared_wall_room_is_larger():
    tac, ws, fc = middle((22., 46.), 28., family=G.CC_JUMP_CAST)
    tac.pb.arena_x = (14.01, 48.99)
    step(tac, ws, fc)
    airborne(tac, ws, fc, land=33.)
    # The large-rune footprint closes the middle. A short walk under is
    # available, while the other declared destination is almost at the wall.
    out = step(tac, ws, fc)
    assert tac.last["clapper_middle"]["route"] == "under"
    assert out.target == 7 and out.entry_attack is None
    assert out.stance_x == pytest.approx(G.jump_behind.behind_spot(33., 1))


def test_wall_lower_bound_cannot_authorize_standing_or_guidance():
    tac, ws, fc = middle((16., 44.), 23.)
    tac.pb.arena_x = (14.01, 48.99)
    step(tac, ws, fc)
    assert tac.last["clapper_middle"]["route"] != "guide"
    change(fc, 7, state="Air")
    tac.jb_land[7] = (16., 1., 18., True)
    ws.entities[0].vel = E((2./.916, 12.))
    step(tac, ws, fc)
    info = tac.last["clapper_middle"]
    assert info["route"] not in {"stand", "guide", "under"} and "wall lower bound only" in info["landing_basis"]
    # Task 179 (#296, live 786 held 27 frames on this bound): the declared far side over the standing monster is
    # compared at once; the corner behind a bounded landing is never a destination.
    assert info["route"] == "over" and info["target"] == 8 and info["kind"] == "stomp"


def test_declared_far_side_is_kept_through_ticks_without_input_until_the_walker_changes():
    tac, ws, fc = middle((16., 44.), 23.)
    tac.pb.arena_x = (14.01, 48.99)
    step(tac, ws, fc)
    change(fc, 7, state="Air")
    tac.jb_land[7] = (16., 1., 18., True)
    ws.entities[0].vel = E((2./.916, 12.))
    step(tac, ws, fc)
    assert tac.last["clapper_middle"]["route"] == "over"
    # live 786 2607..2616: inside a dash and its landing lag she takes no input; the same jump's declaration stays
    ws.hero.can["input"] = False
    for _ in range(tac.rules.period):
        step(tac, ws, fc)
    info = tac.last["clapper_middle"]
    assert info["route"] == "over" and info["target"] == 8
    assert info["endpoints"][0]["basis"].endswith("kept from this jump's declaration")
    change(fc, 8, family=G.CC_SLAM, state="Slam Antic", committed=True)  # the walker begins its own move
    step(tac, ws, fc)
    assert (tac.last.get("clapper_middle") or {}).get("route") != "over"


def test_a_new_close_attack_can_still_outscore_this_jump_scene():
    tac, ws, fc = middle((22., 34.), 31.)
    step(tac, ws, fc)
    change(fc, 8, family=G.CC_SLAM, state="Slam Antic", committed=True)
    out = step(tac, ws, fc)
    assert out.target == 8 and tac.last["clapper_winner"]["rule"] == "near"


def test_declared_far_side_survives_source_landing_for_the_bounded_handoff():
    tac, ws, fc = middle((22., 37.), 28., family=G.CC_JUMP_CAST)
    tac.pb.arena_x = (14.01, 48.99)
    step(tac, ws, fc)
    airborne(tac, ws, fc)
    first = step(tac, ws, fc)
    assert first.target == 8 and tac.last["clapper_middle"]["route"] == "over"
    stance = first.stance_x
    change(fc, 7, family=G.CC_IDLE, state="Idle", committed=False)
    out = step(tac, ws, fc)
    assert out.target == 8 and out.stance_x == stance
    assert out.entry_attack.source_family == G.CC_JUMP_CAST
    assert tac._clapper_priority["middle_jump"]["finishing"]
    ws.stamp.t_game_s += 2.1
    step(tac, ws, fc)
    assert tac._clapper_priority["middle_jump"] is None


def test_default_oracle_backend_control_clock_reaches_real_l2_without_phase():
    from ssbot.backends.oracle_backend import OracleBackend
    from tests import worldstate_fixture as fx
    tac, ws, fc = middle()
    raw = fx.window(0)[0]  # Portable STATE envelope; the two-Clapper scene is synthetic.
    raw["ents"] = [{"iid": 7, "type_key": G.CLAPPER, "name": G.CLAPPER, "category": "enemy",
                    "pos": [22., 5.], "vel": [0., 0.], "flipX": True, "hp": 50,
                    "fsms": [{"name": "Control", "state": "Jump Antic", "t": .02}],
                    "colliders": [{"name": G.CLAPPER, "enabled": True, "layer": 11,
                                   "verts_world": [21., 3., 23., 3., 23., 7., 21., 7.],
                                   "damage": {"can_cause_damage": True, "eff": 2, "hazard_type": 1, "flags": 0}}]}]
    produced = OracleBackend().feed(raw)
    ent = next(e for e in produced.entities if e.id == 7)
    assert ent.phase is None
    assert ent.fsm == [("Control", "Jump Antic", .02)]
    ws.entities[0] = ent
    out = step(tac, ws, fc)
    assert out.target == 7 and tac.last["clapper_middle"]["route"] == "guide"


@pytest.mark.parametrize("clock", [None, [], [("Control", "Air", .02)],
    [("Control", "Jump Antic", float("nan"))], [("Control", "Jump Antic", -.1)],
    [("Control", "Jump Antic", .01), ("Control", "Jump Antic", .02)]])
def test_missing_invalid_or_ambiguous_control_clock_is_unknown(clock):
    tac, ws, fc = middle()
    ws.entities[0].fsm = clock
    step(tac, ws, fc)
    assert tac.last["clapper_middle"]["reason"] == "aim clock unknown"
