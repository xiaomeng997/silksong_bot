"""Task 179 #316 (Sol seq 239 a): SSBOT_FORUM_TWO_RETURN_AIR, a default-off local candidate. L2's air-pose middle return
after an observed near move that has ENDED is a ReturnRequest; the native B2 owner runs it with its existing SWITCH
approach / down-slash execution as a ReturnGoal. The ended source is attribution and the one-return key only: no phase or
instance gate, no rewritten cast_fa or clock, no exemption; the request exists only on the ticks L2 makes it and a
pending goal is withdrawn when it is gone."""
import os
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import forum_v2 as v2
from ssbot.combat import knife_chain_transfer as T
from ssbot.combat.knife_chain_air import load_runner
from ssbot.combat.knife_chain_air_native import NativeManualAirChain
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.combat.tactics import gauntlet as G
from ssbot.combat.tactics.modes import GoalPrefs, ReturnRequest
from tests.test_clapper_priority import change, manual, scene, step   # noqa: F401  (autouse manual-B fixture)
from tests.test_middle_return313 import hero_at, move


def _step(tac, ws, fc):
    ws.stamp.frame += 1
    return step(tac, ws, fc)


def _near_cast(tac, ws, fc):
    for st in ("Spell Antic", "Cast 2"):
        change(fc, 7, family=G.CC_CAST, state=st, committed=True)
        _step(tac, ws, fc)
    change(fc, 7, family=G.CC_IDLE, state="Idle", committed=False)
    return _step(tac, ws, fc)


def test_l2_makes_the_request_only_on_its_winning_air_ticks(monkeypatch):
    monkeypatch.setattr(v2, "RETURN_AIR", True)
    tac, ws, fc = scene(xs=(20., 23.), hx=15.)             # bodies 19..21 and 22..24: no standing gap
    ws.stamp.frame = 1000
    _step(tac, ws, fc)                                      # 1001
    out = _near_cast(tac, ws, fc)                           # the cast seen 1002 .. 1003, ended at 1004
    assert tac.last["clapper_scene"] == "middle return air" and out.target == 8
    req = out.return_request
    assert req == ReturnRequest(8, 7, G.CC_CAST, 1002, 1004, 1004)
    assert tac.last["clapper_back"]["return_request"] == vars(req)
    assert _step(tac, ws, fc).return_request == req         # the same request (its issue frame kept)
    move(ws, fc, 8, 28.)                                    # the gap opens: the ground pose, no air request
    out = _step(tac, ws, fc)
    assert tac.last["clapper_scene"] == "middle return ground" and out.return_request is None
    move(ws, fc, 8, 23.)                                    # closed again: the same request, the same window
    assert _step(tac, ws, fc).return_request == req
    change(fc, 8, state="After Scuttle")                    # outside Idle / Walk: none
    assert _step(tac, ws, fc).return_request is None
    change(fc, 8, state="Idle")
    hero_at(ws, 21.5)                                       # and while the return is over (landed): none
    change(fc, 7, family=G.CC_SLAM, state="Slam Antic", committed=True)   # a new attack suspends the return
    out = _step(tac, ws, fc)
    assert tac.last["clapper_back"] is None and out.return_request is None


def test_l2_makes_no_request_with_the_switch_off():
    tac, ws, fc = scene(xs=(20., 23.), hx=15.)
    ws.stamp.frame = 1000
    _step(tac, ws, fc)
    out = _near_cast(tac, ws, fc)
    assert tac.last["clapper_scene"] == "middle return air" and out.return_request is None
    assert "start_f" not in (tac._clapper_priority or {}).get("back", {})      # nothing recorded off


def _state(f=1010, source_state="Idle", target_state="Idle"):
    e = lambda i, st, x: {"iid": i, "type_key": "Song Heavy Sentry", "hp": 100, "pos": [x, 7.45],  # noqa: E731
                          "fsms": [{"name": "Control", "state": st, "t": 0.}]}
    return {"f": f, "hero": {"health": 7, "pos": [20., 10.], "box": [19.75, 8.5, 20.25, 10.6]},
            "ents": [e(7, source_state, 22.), e(8, target_state, 25.)]}


def _native():
    n = NativeManualAirChain(runner_factory=load_runner, probe_ref="return-air")
    n.reset(0, start_frame=999)
    return n


REQ = ReturnRequest(8, 7, "CC_CAST", 900, 960, 1000)


def test_b2_binds_the_request_as_a_switch_execution_goal_and_withdraws_it_when_gone(monkeypatch):
    monkeypatch.setattr(v2, "RETURN_AIR", True)
    n = _native()
    s = _state()
    prefs = GoalPrefs(mode="RUSH", stance_x=24., weights={}, target=8, return_request=REQ)
    out = n.goal_preferences(s, prefs, handoff=True)
    g = n._transfer_goal
    assert isinstance(g, T.ReturnGoal) and g.source_kind == "SWITCH"
    assert (g.target, g.caster, g.cast_fa, g.return_f, g.window_from) == (8, 7, 900, 1000, 1000)
    assert g.source_move == T.MoveInstance(7, 900, "CC_CAST") and g.responsibility == g.source_move
    assert n._transfer_ready and n.runner.run is None and n.commitment is None and out.target == 8
    assert n.goal_preferences(s, prefs, handoff=True) is not None and n._transfer_goal == g      # kept, not rebound
    n.goal_preferences(s, replace(prefs, return_request=None), handoff=True)                     # the request gone
    assert n._transfer_goal is None
    n.goal_preferences(s, replace(prefs, return_request=replace(REQ, target=7), target=7), handoff=True)
    assert n._transfer_goal is None or n._transfer_goal.target == 7
    n._transfer_goal = None
    n._transfer_finished.add((7, 900))                       # one return per source instance
    n.goal_preferences(s, prefs, handoff=True)
    assert n._transfer_goal is None


def test_b2_binds_nothing_with_the_switch_off_or_for_another_target(monkeypatch):
    n = _native()
    s = _state()
    prefs = GoalPrefs(mode="RUSH", stance_x=24., weights={}, target=8, return_request=REQ)
    n.goal_preferences(s, prefs, handoff=True)
    assert n._transfer_goal is None                          # off
    monkeypatch.setattr(v2, "RETURN_AIR", True)
    n.goal_preferences(s, replace(prefs, target=7), handoff=True)
    assert n._transfer_goal is None                          # the request is for 8, the current target 7


def test_the_admission_window_counts_from_the_request_never_a_rewritten_cast_frame():
    cfg = load_runner().chains["rune_transfer"].cfg
    s = _state(f=1100)
    goal = T.ReturnGoal(8, 7, 900, None, "SWITCH", T.MoveInstance(7, 900, "CC_CAST"), 1000)
    assert T.observe_goal(s, goal, cfg, set()) == goal       # 200 frames after the source began, 100 after the request
    plain = T.TransferGoal(8, 7, 900, None, "SWITCH", T.MoveInstance(7, 900, "CC_CAST"))
    assert T.observe_goal(s, plain, cfg, set()) is None      # an ordinary goal: its own cast_fa window, unchanged
    s["f"] = 1000 + cfg["max_frames"] + 1
    assert T.observe_goal(s, goal, cfg, set()) is None       # finite: past the request's window


def test_the_source_must_have_ended_its_move():
    n = _native()
    goal = T.ReturnGoal(8, 7, 900, None, "SWITCH", T.MoveInstance(7, 900, "CC_CAST"), 1000)
    assert n._return_source_ended(_state(), goal)
    assert not n._return_source_ended(_state(source_state="Cast 2"), goal)
    unknown = replace(goal, source_move=T.MoveInstance(7, 900, "CC_EVADE"))
    assert not n._return_source_ended(_state(), unknown)
    gone = deepcopy(_state())
    gone["ents"] = gone["ents"][1:]
    assert not n._return_source_ended(gone, goal)


def test_off_by_default_and_the_switch_resolves_to_the_module_constant_in_the_measurement_manifest():
    from ssbot.train.forum_measure_manifest import configuration_manifest
    if "SSBOT_FORUM_TWO_RETURN_AIR" not in os.environ:
        assert v2.RETURN_AIR is False
    root = Path(v2.__file__).resolve().parents[1]
    m = configuration_manifest(root, None, modules={"ssbot.combat.forum_v2": v2},
                               environ={"SSBOT_FORUM_TWO_RETURN_AIR": "0"})
    s = m["switches"]["SSBOT_FORUM_TWO_RETURN_AIR"]
    assert s["resolution"] == "runtime_binding"
    assert s["effective"] == {"ssbot.combat.forum_v2.RETURN_AIR": v2.RETURN_AIR}


def _events(n, name):
    return [e for e in n.events if e["event"] == name]


def test_b2_binds_no_request_past_its_finite_window(monkeypatch):
    monkeypatch.setattr(v2, "RETURN_AIR", True)
    n = _native()
    cfg = n.runner.chains[T.PROGRAM].cfg
    prefs = GoalPrefs(mode="RUSH", stance_x=24., weights={}, target=8, return_request=REQ)
    n.goal_preferences(_state(f=REQ.made_f + cfg["max_frames"] + 1), prefs, handoff=True)
    assert n._transfer_goal is None and not _events(n, "return_request_bound")


def _running(n, link, req=REQ):
    from ssbot.combat.knife_chain_eval import Run
    p = T.TransferPlan(req.target, req.source, req.source_start_f, 1000, 0., B["R"], 10000, 0, 0, False, 1000, 0)
    n._transfer_goal = T.ReturnGoal(req.target, req.source, req.source_start_f, None, "SWITCH",
                                    T.MoveInstance(req.source, req.source_start_f, req.source_family), req.made_f)
    n.runner.run = Run(T.PROGRAM, link, p.variables())


@pytest.mark.parametrize("link", ["walk", "dash", "jump", "air"])
def test_a_sent_return_approach_is_handed_back_once_l2_no_longer_makes_the_request(monkeypatch, link):
    monkeypatch.setattr(v2, "RETURN_AIR", True)
    n = _native()
    _running(n, link)
    prefs = GoalPrefs(mode="RUSH", stance_x=24., weights={}, target=8)            # the gap opened: no air request
    assert n._transfer_offer(_state(), 1., None, None, prefs, False) is None
    assert n.runner.run is None and n._transfer_goal is None
    (ev,) = _events(n, "return_request_released")
    assert ev["link"] == link and ev["target"] == 8 and ev["request"] is None


@pytest.mark.parametrize("link,req", [("air", REQ), ("strike", None)])
def test_a_held_request_or_a_chosen_strike_row_keeps_its_owner(monkeypatch, link, req):
    monkeypatch.setattr(v2, "RETURN_AIR", True)
    n = _native()
    _running(n, link)
    monkeypatch.setattr(n, "queued_prefix", lambda f, s: (None, None))      # stop right after the release decision
    prefs = GoalPrefs(mode="RUSH", stance_x=24., weights={}, target=8, return_request=req)
    n._transfer_offer(_state(), 1., NS(prefix=np.array([0])), None, prefs, False)
    assert not _events(n, "return_request_released")


def _admission(hx, hy, vx, vy, other_x, target_x, prefix=0, target_t=.2, held=0, dash_lock=()):
    """_return_admission on a model pose: hy is the live hero y (box from hy - 1.04; the model's PY is 0.514 higher);
    both Clappers production-shaped (fit_pose: the fitted Idle pose at its clock, on the floor, facing her). dash_lock:
    the contacts the B2 geometry scan reports on a dash's locked motion (a stand-in for the tick's all-owner scan)."""
    from ssbot.combat.air_chain import ChainSim
    from ssbot.knowledge import kinematics as K
    from tests.test_knife_chain_transfer import fit_pose
    root = Path(__file__).resolve().parents[2]
    params = K.hero2(K.HeroParams.load(root / "knowledge/1.0.30000/kinematics/hero_wanderer_forum.json"))
    terrain = K.Terrain2D.from_boxes([(-100., -10., 100., 3.015)])
    ent = lambda i, x, t: fit_pose({"iid": i, "type_key": "Song Heavy Sentry", "hp": 100, "pos": [x, 7.45],  # noqa: E731
                                    "vel": [0., 0.], "flipX": x < hx,
                                    "fsms": [{"name": "Control", "state": "Idle", "t": t}],
                                    "colliders": [{"name": "Song Heavy Sentry", "enabled": True, "verts_world": []}]})
    s = {"f": 1000, "hero": {"pos": [hx, hy], "health": 7, "hero_accepting_input": True},
         "ents": [ent(7, other_x, .2), ent(8, target_x, target_t)],
         "act": {"hf": {"latched": held, "desired": held, "pending": [0] * 22, "age": [100] * 22}}}
    S = K.initial_state(params, hx, hy + .514, vx=vx, vy=vy, facing=1, ground=False)
    sim = ChainSim(S, np.array([prefix], np.int64), K.HoldState.from_act(s["act"]), params, terrain, 1000, 1000)
    side = B["R"] if target_x > hx else B["L"]
    plan = T.TransferPlan(8, 7, 900, 1000, 0., side, 2, 0, 0, False, 1000, 0)        # a fresh air start
    geo = NS(scan=lambda path: NS(complete=True, contacts=tuple(dash_lock)))
    return _native()._return_admission(s, sim, plan, 1., geo)


def test_a_fresh_return_start_waits_while_the_straight_approach_would_cross_the_other_body():
    # A2 2770: outside the pair, just above the bodies' tops, falling: even its air dash ends short of / into the body
    assert "other body" in _admission(15.76, 8.04, 9.9, -28.8, 19.56, 25.1)
    # the same pose with the planner's DASH+L in flight (sent 2769): never past it either
    assert "other body" in _admission(15.76, 8.04, 9.9, -28.8, 19.56, 25.1, prefix=B["DASH"] | B["L"])
    # A3 2798: high over the body's span, J released: the recipe's air dash carries her past it, over a fresh Idle
    assert _admission(19.62, 13.40, 0., -5., 20.47, 26.2) is None
    # lower over it (9.5): its air dash still passes; with a fresh jump press in flight the dash waits for it and
    # the modelled dash never starts after it (unknown, never a pass): that start waits
    assert _admission(19.62, 9.5, 0., -5., 20.47, 26.2) is None
    assert "locked motion" in _admission(19.62, 9.5, 0., -5., 20.47, 26.2, prefix=B["J"] | B["L"])
    assert "other body" in _admission(19.62, 8.5, 0., -5., 20.47, 26.2)
    # nothing between her and the target: no crossing to check
    assert _admission(23.0, 10.5, 0., -5., 19.56, 26.2) is None
    # A3 2790: the approach needs its air dash, and the tick's all-owner scan of the dash's locked motion refuses it
    assert "locked motion" in _admission(19.62, 13.40, 0., -5., 20.47, 26.2, dash_lock=("contact",))


def test_a_fresh_return_start_waits_when_no_strike_witness_can_hold_over_the_target():
    # A2 2798-2823: 470 held in Idle long past its modelled exits (Idle Time, k 39): no press-now row can exist there,
    # the Run would only descend onto her
    assert "strike witness" in _admission(19.62, 13.40, 0., -5., 20.47, 26.2, target_t=1.4)
    assert "strike witness" in _admission(23.0, 10.5, 0., -5., 19.56, 26.2, target_t=1.4)
    # never above the target within the probe (ground level, far): waits too
    assert "above the target" in _admission(23.0, 4.3, 0., 0., 19.56, 40.0)
