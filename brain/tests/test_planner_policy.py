"""PlannerPolicy glue (ssbot.train.planner_policy, M2 W3 + W4 integration), open loop on the fixture STATEs of the
trial run's wake and first charge (tests/worldstate_fixture.py window 0): every STATE gets a mask, the forecast is
certified from the wake on, the supervisor runs, the hit taken at 56777 is a predicted one, and the stage-C path
(DegradedOracleBackend) runs with its delay."""
import random

import pytest

from ssbot.knowledge.kinematics import Terrain2D
from ssbot.train.encounters import BELL_BEAST
from ssbot.train.planner_policy import PlannerPolicy
from tests import worldstate_fixture as fx

ARENA = [(60.0, 0.0, 110.0, 2.0), (67.2, 0.0, 69.2, 14.0), (102.0, 0.0, 104.0, 14.0)]


class Tap:
    wake_frame = 56532


@pytest.mark.parametrize("view", ["oracle", "degraded"])
def test_policy_runs_open_loop(view):
    pol = PlannerPolicy(view=view, threads=4)
    pol.terrain = Terrain2D.from_boxes(ARENA)
    pol.reset(random.Random(1), BELL_BEAST)
    masks = []
    for s in fx.window(0):
        if s["f"] < 56540:
            continue
        masks.append(pol.act(s, Tap))
    assert len(masks) > 300 and all(isinstance(m, int) and m >= 0 for m in masks)
    st = pol.stats()
    assert st["tick_ms_p50"] is not None and st["view"] == view
    assert 56777 in st["hits_taken"] or view != "oracle"
    assert not st["unpredicted"]
    assert pol.fc.tracker.t_wake is not None
    if view == "degraded":
        assert 2 <= st["k"] <= 4
