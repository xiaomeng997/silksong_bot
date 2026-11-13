"""Task 182 (the person 11-13 "那就先修出圈吧"; Sol analysis/w13_50_b13b404_20261113/video_0250/REVIEW.md): the final L2 stance out of
the live big rune circles (clapper_priority.rune_exit_x / _apply). b13b404 ep2 12316-12361: the base spot's exit 39.66 was overwritten by
the cluster plan's attack_aim 29.0 and attack_retreat 33.8, inside the circle 24.73..39.10; 2 HP at its lighting."""
from types import SimpleNamespace as NS

import pytest

from ssbot.combat.tactics import clapper_plans as CP, clapper_priority as P
from tests.test_clapper_priority import change, manual, scene, step   # noqa: F401  (autouse manual-B fixture)

PAD, HALF = .25, .25
WALLS = (0., 60.)


@pytest.fixture(autouse=True)
def plans_on(monkeypatch):
    monkeypatch.setattr(CP, "ENABLED", True)        # the plan table (production: SSBOT_FORUM_TWO_PLAN=1)


def ex(x, hx, circles, bodies=(), roots=(), walls=WALLS):
    return P.rune_exit_x(x, hx, list(circles), list(bodies), list(roots), walls, HALF, HALF, PAD)


def inside(x, lo, hi):
    return lo - HALF - PAD < x < hi + HALF + PAD


# ---- the pure exit ----

def test_a_stance_outside_every_circle_stays_and_records_nothing():
    assert ex(20., 33., [(25., 35.)]) == (20., None)
    assert ex(35.5, 33., [(25., 35.)]) == (35.5, None)          # her box and the pad just clear of the edge
    assert ex(24.5, 33., [(25., 35.)]) == (24.5, None)
    assert ex(30., 33., []) == (30., None)


def test_the_2_50_layout_leaves_by_the_right_edge_not_over_the_near_body():
    # b13b404 ep2: circle 24.7253..39.0989, the near one's root 25.0 (its body over the circle's left edge), she at ~33.9
    x, rec = ex(29.0026, 33.9, [(24.7253, 39.0989)], bodies=[(22.75, 27.25)], roots=[25.0026, 52.])
    assert x == pytest.approx(39.0989 + HALF + PAD) and rec["exit"] == pytest.approx(39.5989)
    left, right = rec["ends"]
    assert left["x"] == pytest.approx(22.75 - HALF - PAD) and left["crosses"] and not right["crosses"]
    assert rec["x0"] == pytest.approx(29.0026) and rec["circles"] == [(24.7253, 39.0989)]
    x2, _ = ex(33.8328, 33.9, [(24.7253, 39.0989)], bodies=[(22.75, 27.25)], roots=[25.0026, 52.])
    assert x2 == pytest.approx(39.5989)                          # the attack_retreat stance of 12337 the same


def test_the_nearer_end_wins_when_no_root_lies_on_either_way():
    x, rec = ex(15., 12., [(10., 30.)])
    assert x == pytest.approx(9.5) and [d["x"] for d in rec["ends"]] == [pytest.approx(9.5), pytest.approx(30.5)]
    assert ex(25., 28., [(10., 30.)])[0] == pytest.approx(30.5)


def test_a_root_on_the_nearer_way_takes_the_clear_far_end():
    x, rec = ex(15., 12., [(10., 30.)], bodies=[(10.5, 11.5)], roots=[11.])
    assert x == pytest.approx(30.5) and rec["ends"][0]["crosses"] and not rec["ends"][1]["crosses"]


def test_both_ways_past_a_root_take_the_nearer_end():
    x, rec = ex(20., 20., [(10., 30.)], roots=[12., 28.])
    assert all(d["crosses"] for d in rec["ends"]) and x == pytest.approx(9.5)


def test_overlapping_circles_and_a_touching_body_merge_into_one_span():
    x, rec = ex(15., 15., [(10., 20.), (19., 30.)])
    assert rec["span"] == (pytest.approx(9.5), pytest.approx(30.5)) and x == pytest.approx(9.5)
    assert len(rec["circles"]) == 1                                 # the circle(s) her stance is in
    # a body whose grown span meets the grown circle: the exit past the body
    x, rec = ex(19., 19., [(10., 20.)], bodies=[(20.6, 22.6)])
    assert rec["span"][1] == pytest.approx(22.6 + HALF + PAD) and x == pytest.approx(23.1)
    # a body clear of it (its grown span starts past the circle's): the circle's own edge
    x, rec = ex(19., 19., [(10., 20.)], bodies=[(21.5, 23.5)])
    assert rec["span"][1] == pytest.approx(20.5) and x == pytest.approx(20.5)


def test_an_end_past_a_wall_is_no_candidate_and_no_end_keeps_the_stance():
    x, rec = ex(4., 3., [(-1., 8.)])
    assert not rec["ends"][0]["inside"] and x == pytest.approx(8.5)
    x, rec = ex(5., 5., [(-1., 11.)], walls=(0., 10.))
    assert x == 5. and rec["exit"] is None and not any(d["inside"] for d in rec["ends"])


# ---- through the real L2 entry ----

def _rune(tac, lo, hi):
    tac.rune_life = NS(live=lambda t: [NS(lo=lo, hi=hi)])


def _cluster_case(monkeypatch, on):
    monkeypatch.setattr(P, "RUNE_EXIT_FINAL", on)
    tac, ws, fc = scene(xs=(25.0026, 50.), hx=33.9)
    ws.stamp.frame = 12316
    step(tac, ws, fc)
    _rune(tac, 24.7253, 39.0989)
    ws.stamp.frame += 1
    return tac, step(tac, ws, fc)


def test_a_stance_inside_a_live_circle_leaves_it_whatever_set_it(monkeypatch):
    tac, out = _cluster_case(monkeypatch, False)
    before = out.stance_x
    assert inside(before, 24.7253, 39.0989), before                   # the stance this layout gets without the rule
    assert "clapper_rune_exit" not in tac.last
    tac, out = _cluster_case(monkeypatch, True)
    rec = tac.last["clapper_rune_exit"]["stance"]
    assert rec["x0"] == pytest.approx(before, abs=1e-3) and out.stance_x == pytest.approx(rec["exit"])
    assert not inside(out.stance_x, 24.7253, 39.0989) and tac.goal.stance_x == pytest.approx(out.stance_x)
    assert out.stance_x == pytest.approx(39.5989)                     # the right edge: the left one is past the near body
    assert "rune exit" in tac.last["goal_why"]


def test_the_winners_stage_stance_inside_a_circle_she_stands_in_leaves_it(monkeypatch):
    # the separated slam (tests/test_separated312's first layout): its place comes from the winner's own stage (Applied.stance); a circle
    # she stands in is no circle across her way, so the place is the body branch's, inside it
    from tests.test_separated312 import slam, start
    from ssbot.combat.tactics import clapper_separated as SEP
    stances = {}
    for on in (False, True):
        monkeypatch.setattr(P, "RUNE_EXIT_FINAL", on)
        tac, ws, fc = start((20., 30.), 40.)
        _rune(tac, 30., 45.)
        out = slam(tac, ws, fc)
        assert tac.last["clapper_winner"]["rule"] == "sep_slam" and out.target == 8
        stances[on] = (out.stance_x, tac.last.get("clapper_rune_exit"))
    assert stances[False][0] == pytest.approx(20. + SEP.SLAM_EDGE_U + SEP.OUT_U) and stances[False][1] is None
    x, rec = stances[True]
    assert rec["stance"]["x0"] == pytest.approx(stances[False][0])
    assert x == pytest.approx(45.5)          # the merged span 28.5 (8's body grown) .. 45.5: the left end is past 8's root


def test_no_live_circle_leaves_the_stance_and_the_log_as_before(monkeypatch):
    for on in (False, True):
        monkeypatch.setattr(P, "RUNE_EXIT_FINAL", on)
        tac, ws, fc = scene(xs=(25.0026, 50.), hx=33.9)
        ws.stamp.frame = 12316
        step(tac, ws, fc)
        _rune(tac, 2., 6.)                                            # a circle far from every stance here
        ws.stamp.frame += 1
        out = step(tac, ws, fc)
        assert "clapper_rune_exit" not in tac.last and "rune exit" not in tac.last["goal_why"]
        if on:
            assert out.stance_x == pytest.approx(ref)
        else:
            ref = out.stance_x


def test_the_withdrawn_stance_leaves_the_circle_too(monkeypatch):
    # test_l2_plan182's over_head stage: its stance on the walker's head, L2's own stance in its withdraw
    from tests.test_l2_plan182 import antic, go_, planned, take_off
    tac, ws, fc = planned(monkeypatch, xs=(19., 31.5), hx=27.)
    ws.stamp.frame = 500

    def tick():
        ws.stamp.frame += 1
        return go_(tac, ws, fc)
    tick()
    antic(tac, ws, fc)
    tick(); tick()
    r = tac.plan_runner
    land = r.exec.plan.get("landings")[0]
    change(fc, 8, pos=(30., fc.subjects[1].pos[1]))
    ws.entities[1].dmg_boxes[0].poly = [(29., 3.), (31., 3.), (31., 7.), (29., 7.)]
    take_off(tac, ws, fc, vx=(land - 19.) / CP.GAIN)
    out = tick()
    assert r.exec.name == "over_head" and out.withdraw is not None
    wx, sx = out.withdraw.stance_x, out.stance_x
    lo, hi = wx - .5, wx + .5                                         # a narrow circle on L2's own stance only
    assert not inside(sx, lo, hi), (wx, sx)
    _rune(tac, lo, hi)
    out = tick()
    assert r.exec.name == "over_head" and out.withdraw is not None
    rec = tac.last["clapper_rune_exit"]
    assert rec["stance"] is None and rec["withdraw"]["exit"] is not None
    assert out.withdraw.stance_x == pytest.approx(rec["withdraw"]["exit"]) and not inside(out.withdraw.stance_x, lo, hi)
    assert out.stance_x == pytest.approx(sx)                          # the stage's own stance is outside: kept
