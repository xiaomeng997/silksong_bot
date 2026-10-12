"""The Clapper slam theory (ssbot.combat.pogo_slam): the timeline from the measured template, the band clip, a press
over the Clapper's head in the late antic, the grid's bookkeeping."""
import numpy as np
import pytest

from ssbot.combat import pogo_slam as ps
from ssbot.combat.pogo_model import slash_poly
from ssbot.knowledge import kinematics as kin

pytestmark = pytest.mark.skipif(not ps.TEMPLATE.exists(), reason="no slam template")


def _kin():
    """The Wanderer's parameters and a flat Forum-like floor (top at FLOOR_Y, walls far away)."""
    from ssbot.train.forum_planner_policy import CREST_PARAMS
    params = kin.HeroParams.load(CREST_PARAMS["Wanderer"])
    return params, kin.Terrain2D.from_boxes([(0.0, ps.FLOOR_Y - 5.0, 80.0, ps.FLOOR_Y)])


def test_timeline_states_and_lunge():
    tl = ps.SlamTimeline.load(antic=49, s0=5, phase=0.5)
    assert tl.state[0] == "Slam Antic" and tl.state[48] == "Slam Antic" and tl.state[49] == "Slam 0"
    assert tl.state[54] == "Slam 1" and tl.state[57] == "Slam 2" and tl.state[63] == "Slam Recover"
    assert tl.disp[49] == 0.0                                  # the lunge's velocity is set on the Slam 0 entry
    assert tl.disp[-1] in (pytest.approx(3.6), pytest.approx(4.2))   # 6 or 7 physics steps of 0.6 u
    assert np.isnan(tl.hammer[50, 0]) and np.isfinite(tl.hammer[54, 0]) and np.isfinite(tl.hammer[57, 0])
    assert len(ps.SlamTimeline.variants()) == 8


def test_clip_band():
    sq = np.array([[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0]])
    assert ps.clip_band(sq, 0.5, 1.0) == (0.0, 2.0)
    tri = np.array([[0.0, 0.0], [2.0, 0.0], [1.0, 2.0]])
    lo, hi = ps.clip_band(tri, 1.0, 3.0)
    assert lo == pytest.approx(0.5) and hi == pytest.approx(1.5)
    assert ps.clip_band(tri, 2.5, 3.0) is None


def test_press_over_the_head_in_the_late_antic_bounces():
    params, terrain = _kin()
    tl = ps.SlamTimeline.load()
    cy = ps.FLOOR_Y + tl.pos_y
    # the hero 1.3 u above the Clapper's position (her box clear of its body), 0.5 u in front, falling slowly
    start = kin.initial_state(params, ps.CX + 0.5, cy + 1.3, vy=-1.0, facing=-1, ground=False)
    masks = np.zeros(40, np.int64)
    masks[0] = ps.M_D | ps.M_A
    masks[1:3] = ps.M_D
    pr = ps.predict_press(params, terrain, tl, 30, ps.CX, cy, 1, start, masks, -1)
    assert pr["j"] >= 0 and pr["hit"] is not None
    assert pr["inv"][pr["j"]]                                  # the bounce's i-frames start on the contact


def test_grid_counts():
    params, terrain = _kin()
    th = ps.SlamTheory(params, terrain)
    tl = ps.SlamTimeline.load()
    paths = th.paths(hs=(13,), as_=(14,), pres=(1,), posts=(1,), jposts=(0,))
    acc = th.grid(tl, np.round(np.arange(2.0, 6.0, 0.5), 2), np.arange(20, 40), paths)
    c = acc.c
    assert c[0].sum() > 0
    assert (c[1] <= c[0]).all() and (c[2] <= c[1]).all() and (c[4] <= c[2]).all() and (c[4] <= c[3]).all()
    assert slash_poly(1).shape == (7, 2)
