"""Task 179 #305 (live 179-L2 w13_walk179L2_20261106T000950Z_1263e9e3, runtime 1263e9e3): an air transfer toward a
target standing in Slam Antic is timed by the target's earliest lunge.

Live: after the real 2761 bounce off 335476 the new target 335470 had been in Slam Antic since 2747. The air Run coasted
R for 32 ticks (its once-per-Run probe only asked whether the coast EVER gets above the body, which it did at the
antic's end) with current-step checks only, and handed back at 2793, two frames before the lunge; Slam 1 hit at 2801.
On the exact tick inputs one air dash at the next free frame reaches a press_now_row contact (all slash polygons) at
2771-2777, before the lunge. The fix: the coast-or-dash choice needs the coast to reach a contact before the earliest
lunge, and a Run whose approach rows cannot reach one any more hands back at once (table air link guard).
"""
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import knife_chain_transfer as T
from ssbot.combat.knife_chain_air import load_runner
from ssbot.combat.knife_chain_commitment import MoveInstance
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from tests.test_knife_chain_transfer import fit_pose

WHY = "attacking target: no down slash on its standing antic before the earliest lunge"
# live 179-L2 tick 2761: planner_input hero_state (K rows) and STATE act.hf.age (decisions_i0.chain.jsonl / raw STATE)
S2761 = [24.261946, 8.613712, 24.261946, 9.057712, 24.261946, 8.613712, 0.0, -10.0, 0.732491, 1.0, 1.0, 0.0, 0.0,
         5.366649, 322.0, 1.0, 8.0, -20.0, -1.0, -1.0, 1.0, 0.0, 0.0, 0.150001, 0.0, 0.0, 0.0, 0.016679, 0.0, -0.0, 7.5,
         0.0, 0.0, 0.0, 8.0, 0.0, 0.0, 0.0, 0.0, 1.0, -1.0, 0.732491, 0.732491, 0.0, -1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0,
         0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -1.0, 0.0, 25.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, -1.0, 0.0, 0.0, 0.0, 0.0,
         0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.133349, 0.0, 0.0, 0.0, 0.0, 0.0, 8.0]
AGE2761 = [122, 6] + [255] * 17 + [4, 140, 138]


def scene(target_state="Slam Antic", target_t=14 / 60, hero=None, airdashed=0.0):
    """The live 2761 shape: hero just bounced off the caster (iid 7) at x 23.79; the target (iid 8) faces her from
    x 30.51 in its antic. The hero is the EXACT live 2761 tick input (planner_input S0, in-flight prefix 0, STATE act
    hold filter) unless hero=(x, y, vx, vy) places a synthetic one; production-shaped bodies (fit_pose), HERO2."""
    from pathlib import Path
    from ssbot.knowledge import kinematics as K
    from ssbot.combat.air_chain import ChainSim
    root = Path(__file__).resolve().parents[2]
    params = K.hero2(K.HeroParams.load(root / "knowledge/1.0.30000/kinematics/hero_wanderer_forum.json"))
    hx, hy, vx, vy = (S2761[0], S2761[1], 0.0, 0.0) if hero is None else hero
    key = B["R"]
    s = {"f": 2761, "hero": {"pos": [hx, hy], "box": [hx - .25, hy - 1.04, hx + .25, hy + 1.04], "vel": [vx, vy],
                             "health": 7, "hero_accepting_input": True, "tm": {"dash_cd": -.02}},
         "act": {"hf": {"latched": 0, "desired": 0, "pending": [0] * 22, "age": AGE2761}}, "ents": []}
    for iid, x, st, t, flip in [(7, 23.79, "Idle", 0., True), (8, 30.51, target_state, target_t, False)]:
        s["ents"].append({"iid": iid, "type_key": "Song Heavy Sentry", "hp": 160, "pos": [x, 7.45], "vel": [0., 0.],
                          "flipX": flip, "fsms": [{"name": "Control", "state": st, "t": t}],
                          "colliders": [{"name": "Song Heavy Sentry", "enabled": True, "verts_world": [0.] * 8}]})
        fit_pose(s["ents"][-1])
    S = (np.asarray(S2761, float) if hero is None else
         K.initial_state(params, hx, hy, vx=vx, vy=vy, ground=False, facing=1)).reshape(K.K, 1).copy()
    S[K.AIRDASHED, 0] = airdashed
    terrain = K.Terrain2D.from_boxes([(-100., -10., 100., 3.015)])
    sim = ChainSim(S, np.array([0 if hero is None else key], np.int64), K.HoldState.from_act(s["act"]), params,
                   terrain, 2761, 2761)
    goal = T.TransferGoal(8, 7, 2761, 2.767, "BOUNCE", MoveInstance(7, 2598, "CC_SLAM"))
    return s, sim, goal


def propose(s, sim, goal):
    return T.propose(load_runner(), s, 2.767, sim, 8, False, None, set(), goal)


def test_coast_too_late_for_the_antic_spends_the_one_air_dash():
    s, sim, goal = scene()
    assert T.antic_strike_out_of_time(sim, s["ents"][1], 0, B["R"], False)        # coast and release: no contact
    assert not T.antic_strike_out_of_time(sim, s["ents"][1], 0, B["R"], True)     # the dash still reaches one
    draft, plan, path, mask = propose(s, sim, goal)
    assert mask & B["DASH"] and mask & B["R"] and draft.run.link == "air"
    assert draft.run.v["approach_recipe"] == "air_dash"


def test_no_contact_left_before_the_lunge_hands_back_at_once():
    s, sim, goal = scene(airdashed=1.0)            # the air dash is spent: only the coast rows remain
    made = propose(s, sim, goal)
    assert made[0] is None and made[1].ended_reason == WHY


def test_a_target_outside_its_antic_keeps_the_old_coast_probe(monkeypatch):
    s, sim, goal = scene(target_state="Cast 2", target_t=.2)
    assert not T.antic_strike_out_of_time(sim, s["ents"][1], 0, B["R"], False)
    real, calls = T.antic_strike_out_of_time, []
    monkeypatch.setattr(T, "antic_strike_out_of_time", lambda *a: calls.append(a[4]) or real(*a))
    draft, plan, path, mask = propose(s, sim, goal)
    # the table guard asked (dash still free) and did not abort; the recipe never took the antic branch (dash_free
    # False): the old once-per-Run coast probe made the coast-or-dash choice, as before #305
    assert calls == [True] and draft.run.link == "air"


def test_a_near_entry_with_antic_time_left_neither_dashes_nor_aborts():
    s, sim, goal = scene(target_t=0., hero=(28.2, 10.0, 0.0, 0.0))
    assert not T.antic_strike_out_of_time(sim, s["ents"][1], 0, B["R"], False)
    made = propose(s, sim, goal)
    assert made[0] is not None and not made[3] & B["DASH"]


@pytest.mark.parametrize("field", ["pos", "fsms", "colliders"])
def test_unknown_target_inputs_keep_the_approach(field):
    s, sim, goal = scene(airdashed=1.0)
    e = dict(s["ents"][1]); e[field] = None
    assert T.antic_strike_out_of_time(sim, e, 0, B["R"], False) is False


@pytest.mark.parametrize("state", ["Slam 0", "Slam 1"])
def test_a_lunging_target_has_no_standing_antic_left(state):
    s, sim, goal = scene(target_state=state, target_t=0.)
    assert T.antic_strike_out_of_time(sim, s["ents"][1], 0, B["R"], True)
    made = propose(s, sim, goal)
    assert made[0] is None and made[1].ended_reason == WHY
