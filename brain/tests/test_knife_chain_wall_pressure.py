"""Finite wall-pressure motion witnesses use real terrain and the actual prefix."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat.air_chain import ChainSim
from ssbot.combat.knife_chain_commitment import MoveInstance
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.combat.knife_chain_wall_pressure import propose
from ssbot.combat.tactics.modes import WallPressure
from ssbot.knowledge import kinematics as K


@pytest.fixture(scope="module")
def params():
    return K.hero2(K.HeroParams.load(Path(__file__).resolve().parents[2] /
                   "knowledge/1.0.30000/kinematics/hero_wanderer_forum.json"))


def scene(params, *, wall=52., hx=51., hy=8., vx=0., vy=-2., mirror=False, ground=False, prefix=0):
    body = [46.6, 3., 49.9, 6.9]
    side = 1
    if mirror:
        hx, wall, vx = 60. - hx, 60. - wall, -vx
        body = [60. - body[2], body[1], 60. - body[0], body[3]]
        side = -1
    boxes = [(-20., -10., 80., 3.015),
             (wall, -10., wall + 1., 25.) if side > 0 else (wall - 1., -10., wall, 25.)]
    terrain = K.Terrain2D.from_boxes(boxes)
    S = K.initial_state(params, hx, hy, vx=vx, vy=vy, ground=ground).reshape(K.K)
    S[K.PREV] = prefix
    state = {"f": 1000, "hero": {"health": 7, "pos": [hx, hy], "vel": [vx, vy],
             "hero_accepting_input": True, "anim": {"clip": "Airborne"}},
             "act": {"hf": {"latched": prefix, "desired": prefix,
                             "pending": [0] * 22, "age": [100] * 22}},
             "ents": [{"iid": 8, "hp": 100, "pos": [(body[0] + body[2]) / 2, 7.45],
                       "colliders": [{"name": "Song Heavy Sentry", "enabled": True,
                         "verts_world": [body[0], body[1], body[2], body[1],
                                         body[2], body[3], body[0], body[3]]}]}]}
    sim = ChainSim(S, np.array([prefix], np.int64), K.HoldState.from_act(state["act"]),
                   params, terrain, 1000, 1000)
    plan = NS(iid=8, move=MoveInstance(8, 994, "CC_SLAM"), origin=1000,
              entry_k=6, press_k=None, contact_frame=None)
    # This L2 projection is deliberately false: the helper must use terrain.
    intent = WallPressure(8, "side", side, (-999., 999.))
    return sim, state, intent, plan


@pytest.mark.parametrize("mirror", [False, True])
def test_real_wall_gap_lands_and_stops_without_a_new_jump_or_cling(params, mirror):
    sim, state, intent, plan = scene(params, mirror=mirror)
    out = propose(sim, state, .1, intent, plan)
    assert out is not None and out.kind == "side"
    expected = (50.65, 51.735) if not mirror else (8.265, 9.35)
    assert out.floor_span == pytest.approx(expected)
    assert out.landing_frame > state["f"] and out.contact_frame is None
    assert not np.any(out.commands & (B["J"] | B["DASH"] | B["A"] | B["CLAW"]))
    assert out.path.states[K.GROUND, -1] > 0
    assert out.floor_span[0] <= out.path.pos[-1, 0] <= out.floor_span[1]
    assert not np.any(out.path.states[[K.CLING, K.WSIDE, K.WTOUCH]])
    assert out.mask_at(out.F0) == out.commands[0]
    assert out.mask_at(out.F0 - 1) is None and out.mask_at(out.path.through + 1) is None


def test_side_witness_covers_landing_rather_than_only_two_frames(params):
    sim, state, intent, plan = scene(params, hy=12., vy=0.)
    out = propose(sim, state, .1, intent, plan)
    assert out is not None and out.kind == "side" and len(out.commands) > 10
    assert out.path.through >= out.landing_frame + 2
    assert out.path.assumptions["all_owner_safety"] == "caller"


def test_unrelated_high_floor_does_not_replace_the_gap_floor(params):
    sim, state, intent, plan = scene(params)
    # A higher platform elsewhere must not select stomp for this supported gap.
    sim.terrain.hseg = np.r_[sim.terrain.hseg, [[3.01, 100., 110.]]]
    out = propose(sim, state, .1, intent, plan)
    assert out is not None and out.kind == "side"
    assert out.floor_span == pytest.approx((50.65, 51.735))


@pytest.mark.parametrize("mirror", [False, True])
def test_tight_observed_gap_uses_one_conditional_air_downslash(params, mirror):
    sim, state, intent, plan = scene(params, wall=50.3, hx=49., hy=10., vy=0., mirror=mirror)
    out = propose(sim, state, .1, intent, plan)
    assert out is not None and out.kind == "stomp"
    assert out.floor_span is None and out.landing_frame is None
    assert out.press_frame < out.contact_frame == out.path.through
    assert out.path.contact_frame == out.contact_frame
    assert np.any(out.commands & B["A"])
    assert not np.any(out.commands & (B["J"] | B["DASH"] | B["CLAW"]))
    assert not np.any(out.path.flags & K.F_INVULN)
    assert out.path.assumptions["future_pogo_injected"] is False
    assert out.path.assumptions["conditional_contact"] is True
    assert out.path.states[K.GROUND, -1] == 0


@pytest.mark.parametrize("bad", ["floor", "wall", "nan_wall", "slopes", "body", "bad_body", "hf"])
def test_unknown_geometry_or_input_never_becomes_a_stomp_fallback(params, bad):
    sim, state, intent, plan = scene(params, wall=50.3, hx=49., hy=10., vy=0.)
    if bad == "floor": sim.terrain = K.Terrain2D.empty()
    elif bad == "wall": sim.terrain.vseg = np.empty((0, 3))
    elif bad == "nan_wall": sim.terrain.vseg[0, 0] = float("nan")
    elif bad == "slopes": sim.terrain.slopes = np.array([[49.9, float("nan"), 50.1, 4.]])
    elif bad == "body": state["ents"][0]["colliders"] = []
    elif bad == "bad_body": state["ents"][0]["colliders"][0]["verts_world"] = [1., 2., 3.]
    else: state["act"]["hf"].pop("age")
    assert propose(sim, state, .1, intent, plan) is None


@pytest.mark.parametrize("wall_state", [K.CLING, K.WSIDE, K.WTOUCH])
def test_existing_wall_contact_is_not_a_pressure_entry(params, wall_state):
    sim, state, intent, plan = scene(params)
    sim.start[wall_state] = 1
    assert propose(sim, state, .1, intent, plan) is None


def test_row_and_actual_prefix_hold_state_are_separate(params):
    sim, state, intent, plan = scene(params, prefix=B["R"])
    original_state = deepcopy(state)
    before = (sim.start.copy(), sim.prefix.copy(), sim.hold.latched.copy(), sim.hold.pending.copy())
    out = propose(sim, state, .1, intent, plan)
    assert out is not None and out.path.commands[0] == B["R"]
    assert np.array_equal(out.commands, out.path.commands[1:])
    assert state == original_state
    for a, b in zip(before, (sim.start, sim.prefix, sim.hold.latched, sim.hold.pending)):
        assert np.array_equal(a, b)


def test_known_gap_with_no_finite_landing_does_not_claim_side(params):
    sim, state, intent, plan = scene(params, hy=30., vy=15.)
    assert propose(sim, state, .1, intent, plan, max_frames=16) is None


def test_grounded_tight_gap_cannot_fabricate_an_airborne_stomp(params):
    sim, state, intent, plan = scene(params, wall=50.3, hx=49.,
                                     hy=3.015 + params.skin + params.foot, vy=0., ground=True)
    assert propose(sim, state, .1, intent, plan) is None


def test_fragments_without_full_hero_width_are_not_ground_standing_space(params):
    sim, state, intent, plan = scene(params, hx=49., hy=10., vy=0.)
    sim.terrain.hseg = np.array([[3.015, 49.9, 50.1], [3.015, 51.9, 52.]])
    out = propose(sim, state, .1, intent, plan)
    assert out is None or out.kind == "stomp"


def test_unaccepted_model_attack_is_not_a_conditional_contact(params):
    sim, state, intent, plan = scene(params, wall=50.3, hx=49., hy=10., vy=0.)
    sim.start[K.ATK_CD] = 2.
    assert propose(sim, state, .1, intent, plan) is None


@pytest.mark.parametrize("mirror", [False, True])
def test_caller_can_decline_landing_then_try_rear_knife_without_erasing_known_space(params, mirror):
    sim, state, intent, plan = scene(params, hx=49., hy=10., vy=0., mirror=mirror)
    landing = propose(sim, state, .1, intent, plan)
    rear = propose(sim, state, .1, intent, plan, allow_landing=False)
    assert landing is not None and landing.kind == "side"
    assert rear is not None and rear.kind == "stomp"
    assert rear.floor_span == pytest.approx(landing.floor_span)
    assert rear.path.assumptions["observed_floor_span"] == pytest.approx(landing.floor_span)
    assert rear.contact_frame == rear.path.through and rear.landing_frame is None


def test_remote_slope_does_not_hide_a_supported_wall_gap(params):
    sim, state, intent, plan = scene(params)
    sim.terrain.slopes = np.array([[0., 8., 1., 9.]])
    out = propose(sim, state, .1, intent, plan)
    assert out is not None and out.kind == "side"


def test_next_stroke_waits_for_old_attack_and_cooldown_then_requires_a_new_onset(params):
    sim, state, intent, plan = scene(params, wall=50.3, hx=49., hy=10., vy=0.)
    sim.start[K.ATTACKING] = 1.
    sim.start[K.ATK_T] = .1
    sim.start[K.ATK_CD] = .15
    sim.start[K.ATK_PDIR] = 2.
    out = propose(sim, state, .1, intent, plan)
    assert out is not None and out.kind == "stomp"
    assert out.press_frame > state["f"] + 2
    j = out.press_frame - state["f"]
    assert out.path.states[K.ATTACKING, j - 1] <= 0
    assert out.contact_frame > out.press_frame


@pytest.mark.parametrize("mirror", [False, True])
def test_real2915_narrow_gap_geometry_can_land_from_a_controlled_post_h1_air_state(params, mirror, monkeypatch):
    # Body/wall/floor are the recorded2915 geometry. The airborne hero is an
    # explicit controlled geometry/motion witness, not a later recording STATE
    # or a claim about the other enemy/H1 hazard in the original fight.
    sim, state, intent, plan = scene(params, wall=48.99223709106445, hx=48.1,
                                     hy=9., vy=-2., mirror=mirror)
    body = [44.37588882446289, 3.0149991512298584, 47.76182556152344, 6.1946868896484375]
    if mirror:
        body = [60. - body[2], body[1], 60. - body[0], body[3]]
    state["ents"][0]["colliders"][0]["verts_world"] = [body[0], body[1], body[2], body[1],
                                                            body[2], body[3], body[0], body[3]]
    state["ents"][0]["pos"][0] = (body[0] + body[2]) / 2
    # The actual floor is3.0, not the earlier synthetic fixture's3.015.
    wall = 60. - 48.99223709106445 if mirror else 48.99223709106445
    wall_box = (wall - 1., -10., wall, 25.) if mirror else (wall, -10., wall + 1., 25.)
    sim.terrain = K.Terrain2D.from_boxes([(-20., -10., 80., 3.), wall_box])
    calls = []
    original_roll = sim.roll
    def bounded_batch(rows, *args, **kwargs):
        calls.append(np.asarray(rows).shape)
        return original_roll(rows, *args, **kwargs)
    monkeypatch.setattr(sim, "roll", bounded_batch)
    out = propose(sim, state, .1, intent, plan)
    assert out is not None and out.kind == "side"
    expected = (48.51182556152344, 48.72723709106445)
    if mirror: expected = (60. - expected[1], 60. - expected[0])
    assert out.floor_span == pytest.approx(expected)
    assert out.path.states[K.GROUND, -1] > 0
    assert expected[0] <= out.path.states[K.PX, -1] <= expected[1]
    assert not np.any(out.path.states[[K.CLING, K.WSIDE, K.WTOUCH]])
    assert len(calls) == 1 and 1 <= calls[0][0] <= 3
