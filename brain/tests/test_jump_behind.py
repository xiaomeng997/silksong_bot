"""SSBOT_FORUM_JUMP_BEHIND (task 1v1 SP3, combat.jump_behind): the L2 stance during the Clapper's jumps (antic: in front
so it jumps in place; past the antic: behind the landing), the rune hold on the jump's own facing, the wall rule, the
corner ranking skipping a jumping Clapper, the planner estimate's turned body from the landing on, and the slam
playbook's nearer stand point at a wall; off, nothing changes."""
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import jump_behind as jb
from ssbot.combat import slam_play as sp
from tests.test_forum_l2 import CC, WinFc, clapper, l2, subj, world

JMP = dict(y=7.45, family="CC_JUMP", committed=True)
CAST = dict(y=7.45, family="CC_JUMP_CAST", committed=True)


@pytest.fixture
def jb_on(monkeypatch):
    monkeypatch.setattr(jb, "ENABLED", True)
    return jb


def test_landing_formula_and_wall_rule():
    # hero 9 u in front (facing left): target = hero + 5, vx = -4 -> 3.66 u toward her
    assert jb.landing(35.0, 26.0, -1.0) == pytest.approx(35.0 - 0.916 * 4.0)
    # hero within 5 u: it jumps back, but never closer than wall_back_u to the wall behind it
    assert jb.landing(19.5, 21.5, 1.0) == pytest.approx(jb.WALL_L + jb.CFG["wall_back_u"])
    assert jb.landing(43.5, 41.5, -1.0) == pytest.approx(jb.WALL_R - jb.CFG["wall_back_u"])
    # taken off with its back near the wall: pushed out at least wall_push_u
    assert jb.landing(16.0, 18.0, 1.0) == pytest.approx(jb.WALL_L + jb.CFG["wall_push_u"])
    assert jb.landing_v(30.0, -5.0, -1.0) == pytest.approx(30.0 - 4.58)
    # behind: back_u behind the landing; against the wall: up to the pad, None below min_back_u
    assert jb.behind_spot(30.0, -1.0) == pytest.approx(33.5)
    assert jb.behind_spot(jb.WALL_L + 4.0, 1.0) == pytest.approx(jb.WALL_L + 0.5)
    assert jb.behind_spot(jb.WALL_L + 3.4, 1.0) is None
    assert jb.aim_spot(30.0, -1.0) == pytest.approx(24.5)


def test_switch_off_keeps_the_old_rule():
    assert not jb.ENABLED                                # the default
    t = l2()
    t.decide(world(26.0, t=10.0, ents=[clapper(9, 35.0, False)]),
             WinFc([subj(9, CC, 35.0, state="Jump Antic", **JMP)]), None, 3)
    assert t.last["goal_why"].endswith("jump: under and behind")   # the v4 rule, unchanged
    assert "jb" not in t.stats and not t.jb_land


def test_antic_flight_landed(jb_on):
    t = l2()
    # antic: 5.5 u in front of it (facing left: x - 5.5), the hit weight on
    p = t.decide(world(26.0, t=10.0, ents=[clapper(9, 35.0, False)]),
                 WinFc([subj(9, CC, 35.0, state="Jump Antic", **JMP)]), None, 3)
    assert t.last["goal_why"].endswith("jump: aim stance") and p.stance_x == pytest.approx(29.5)
    assert p.hit_w[9] > 0
    # first tick past the antic, the hero 5.2 u in front: landing from her x, behind it 3.5 u
    p = t.decide(world(29.8, t=10.5, ents=[clapper(9, 35.0, False)]),
                 WinFc([subj(9, CC, 35.0, y=8.2, state="Jump", family="CC_JUMP", committed=True)]), None, 3)
    land = jb.landing(35.0, 29.8, -1.0)
    assert t.last["goal_why"] == "jump: under and behind (flight)" if "; " not in t.last["goal_why"] else True
    assert p.stance_x == pytest.approx(land + 3.5) and p.hit_w[9] > 0
    # later in the flight the hero moved: the stored landing stays
    p = t.decide(world(33.0, t=10.9, ents=[clapper(9, 35.0, False)]),
                 WinFc([subj(9, CC, 35.0, y=14.0, state="Air", family="CC_JUMP", committed=True)]), None, 3)
    assert p.stance_x == pytest.approx(land + 3.5)
    # landed: behind its own x
    p = t.decide(world(38.0, t=11.4, ents=[clapper(9, 34.6, False)]),
                 WinFc([subj(9, CC, 34.6, state="Slam 2", **JMP)]), None, 3)
    assert t.last["goal_why"].endswith("(landed)") and p.stance_x == pytest.approx(38.1)
    assert t.stats["jb"]["jump: aim stance"] == 1


def test_landing_from_the_air_vx(jb_on):
    t = l2()
    t.decide(world(20.0, t=10.0, ents=[clapper(9, 35.0, False)]),
             WinFc([subj(9, CC, 35.0, state="Jump Antic", **JMP)]), None, 3)
    e = clapper(9, 35.0, False)
    from ssbot.core.worldstate import E
    e.vel = E((-9.0, 30.0))
    p = t.decide(world(21.0, t=10.6, ents=[e]),
                 WinFc([subj(9, CC, 35.0, y=10.0, state="Air", family="CC_JUMP", committed=True)]), None, 3)
    assert p.stance_x == pytest.approx(35.0 - 0.916 * 9.0 + 3.5)


def test_pushed_out_past_the_estimate(jb_on):
    # taken off 4.6 u from the left wall, the hero 2 u in front: it jumps back, the estimate is the wall rule's 3.0 u (no
    # room behind: back off); pushed out forward of its take-off (5.2 u), behind it again
    t = l2()
    x0 = jb.WALL_L + 4.6
    t.decide(world(x0 + 2.0, t=10.0, ents=[clapper(9, x0, True)]),
             WinFc([subj(9, CC, x0, state="Jump Antic", **JMP)]), None, 3)
    t.decide(world(x0 + 2.0, t=10.5, ents=[clapper(9, x0, True)]),
             WinFc([subj(9, CC, x0, y=8.0, state="Jump", family="CC_JUMP", committed=True)]), None, 3)
    assert t.last["goal_why"].endswith("jump: back off")
    p = t.decide(world(x0 + 2.0, t=10.8, ents=[clapper(9, jb.WALL_L + 4.4, True)]),
                 WinFc([subj(9, CC, jb.WALL_L + 4.4, y=12.0, state="Air", family="CC_JUMP", committed=True)]), None, 3)
    assert t.last["goal_why"].endswith("jump: back off")          # moving back: not past its take-off
    p = t.decide(world(x0 + 2.0, t=11.0, ents=[clapper(9, jb.WALL_L + 5.2, True)]),
                 WinFc([subj(9, CC, jb.WALL_L + 5.2, y=12.0, state="Air", family="CC_JUMP", committed=True)]), None, 3)
    assert "under and behind" in t.last["goal_why"] and p.stance_x == pytest.approx(jb.WALL_L + 5.2 - 3.5)


def test_rune_hold_uses_the_jumps_facing(jb_on):
    # a jump cast landed at 30 facing left; at Idle it turned to the hero behind it (flip True = facing right): the
    # circle still lies left of the landing, so the stance stays right of it (behind the jump), 3.5 u
    t = l2()
    t.decide(world(24.0, t=10.0, ents=[clapper(9, 30.0, False)]),
             WinFc([subj(9, CC, 30.0, state="Cast Slam Antic", **CAST)]), None, 3)
    t.decide(world(24.5, t=10.9, ents=[clapper(9, 30.0, False)]),
             WinFc([subj(9, CC, 30.0, y=9.0, state="Air", family="CC_JUMP_CAST", committed=True)]), None, 3)
    t.decide(world(33.5, t=11.8, ents=[clapper(9, 30.0, False)]),
             WinFc([subj(9, CC, 30.0, state="Slam Recover", **CAST)]), None, 3)
    p = t.decide(world(33.5, t=12.2, ents=[clapper(9, 30.0, True)]), WinFc([subj(9, CC, 30.0, y=7.45)]), None, 3)
    assert t.rune[9][1] == -1.0
    assert t.last["goal_why"].endswith("rune: behind") and p.stance_x == pytest.approx(33.5)


def test_corner_zones_skip_a_jumping_clapper(monkeypatch):
    from ssbot.combat import forum_v2
    tr = NS(dead=False, pos=(20.0, 7.45), table=NS(type_key=CC), cur=NS(family="CC_JUMP"))
    fc = NS(trackers={9: tr})
    assert forum_v2.corner_zones(fc)                      # off: the corner counts
    monkeypatch.setattr(jb, "ENABLED", True)
    assert forum_v2.corner_zones(fc) == []
    tr.cur = None                                         # idle: the corner again
    assert forum_v2.corner_zones(fc)


def test_turn_mask_covers_both_sides():
    from ssbot.combat import attack_range as ar
    m = ar._jb_turn_mask(30.0)
    x0, y0, x1, y1 = m.bbox()
    assert x0 == pytest.approx(30.0 - 2.3, abs=0.11) and x1 == pytest.approx(30.0 + 2.3, abs=0.11)
    assert y0 == pytest.approx(3.0, abs=0.11) and y1 == pytest.approx(3.0 + jb.BODY_TOP_U, abs=0.11)


def _slam_state(f, cx, flip, hx, st="Slam Antic", tin=0.0):
    return {"f": f, "ents": [{"type_key": sp.CLAPPER, "iid": 9, "hp": 100, "pos": [cx, 7.45], "flipX": flip,
                              "fsms": [{"name": "Control", "state": st, "t": tin}]}],
            "hero": {"box": [hx - 0.25, 3.01, hx + 0.25, 5.09], "vel": [0.0, 0.0], "health": 7}}


def test_slam_play_near_wall_stand(monkeypatch):
    # the hero between it and the right wall: the stand point 4.6 u in front is past the wall's 0.5 u -> off: no start
    cx = sp.WALL_R - 4.6                                  # facing right (flip True), 4.1 u of room to the wall's pad
    play = sp.SlamPlay(sp.PlayCfg())
    assert play.step(1000, _slam_state(1000, cx, True, cx + 3.5), True, True, None) is None
    assert play.run.why == "wall"
    monkeypatch.setattr(jb, "ENABLED", True)
    play = sp.SlamPlay(sp.PlayCfg())
    m = play.step(1000, _slam_state(1000, cx, True, cx + 3.5), True, True, None)
    assert play.run.phase == "walk" and play.run.stand == (sp.NEAR_STAND_U, pytest.approx(4.1))
    assert play.run.band == (sp.NEAR_BAND_LO, 6.2)
    assert m in (0, sp.M_R)                               # 3.5 u -> toward 3.7..4.1 (right) or already close
    # too little room even for the near stand: no start
    play = sp.SlamPlay(sp.PlayCfg())
    cx2 = sp.WALL_R - 4.0
    assert play.step(1000, _slam_state(1000, cx2, True, cx2 + 3.0), True, True, None) is None
    assert play.run.why == "wall"


def test_dash_focus_free_in_the_flight(monkeypatch):
    from ssbot.combat import forum_v2
    inst = NS(fam="CC_JUMP", states=["Jump Antic", "Jump", "Air"])
    rs = NS(dash_focus=9, trk=NS(now={9: (CC, {"pos": (30.0, 12.0)}, inst)}))
    assert not forum_v2.jb_dash_free(rs)                  # off
    monkeypatch.setattr(jb, "ENABLED", True)
    assert forum_v2.jb_dash_free(rs)
    inst.states = ["Jump Antic"]                          # the antic: the aim is not decided yet
    assert not forum_v2.jb_dash_free(rs)
    inst.states, inst.fam = ["Slam Antic"], "CC_SLAM"
    assert not forum_v2.jb_dash_free(rs)


def test_wall_push_rule():
    # its back at the left wall at take-off (centre 1.35 u out), the hero 4.6 u in front: the formula lands it 1.3 u out
    # (it jumps back); the data: >= 3.83 u but once (3.47) - the stored landing is 4.4 u out, behind it fits (3.9 u)
    x0 = jb.WALL_L + 1.35
    assert jb.landing(x0, x0 + 4.6, 1.0) == pytest.approx(jb.WALL_L + 4.4)
    assert jb.behind_spot(jb.landing(x0, x0 + 4.6, 1.0), 1.0) == pytest.approx(jb.WALL_L + 0.9)
    # taking off 5 u out and jumping back: only the 3.0 u floor (no room behind)
    x1 = jb.WALL_L + 5.0
    assert jb.landing(x1, x1 + 2.0, 1.0) == pytest.approx(jb.WALL_L + 3.0)
    assert jb.behind_spot(jb.landing(x1, x1 + 2.0, 1.0), 1.0) is None
    # the right wall, facing left
    assert jb.landing_v(jb.WALL_R - 2.0, 1.0, -1.0) == pytest.approx(jb.WALL_R - 4.4)


def test_no_hit_while_it_jumps(jb_on):
    t = l2()
    p = t.decide(world(26.0, t=10.0, ents=[clapper(9, 35.0, False)]),
                 WinFc([subj(9, CC, 35.0, state="Jump Antic", **JMP)]), None, 3)
    assert p.no_hit == frozenset({9})                     # antic
    p = t.decide(world(29.8, t=10.5, ents=[clapper(9, 35.0, False)]),
                 WinFc([subj(9, CC, 35.0, y=8.2, state="Air", family="CC_JUMP", committed=True)]), None, 3)
    assert p.no_hit == frozenset({9})                     # flight
    p = t.decide(world(38.0, t=11.4, ents=[clapper(9, 34.6, False)]),
                 WinFc([subj(9, CC, 34.6, state="Slam 2", **JMP)]), None, 3)
    assert p.no_hit == frozenset() and p.hit_w[9] > 0     # landed: slash its back


def test_rune_hold_exit_by_the_landing(jb_on):
    # landed at 30 facing left (the circle 23.5 +- 7.19 to its left); the hero in front of the landing at 26 and the
    # Clapper backed off past the landing's back spot (to 35): the nearer way out is behind the landing, not past it
    t = l2()
    t.rune[9] = (30.0, -1.0, "under and behind", 99.0)
    p = t.decide(world(29.0, t=12.0, ents=[clapper(9, 35.5, False)]), WinFc([subj(9, CC, 35.5, y=7.45)]), None, 3)
    assert t.last["goal_why"].endswith("rune: behind") and p.stance_x == pytest.approx(33.5)
    # far in front (20): the front way out (30 - 14.5 = 15.5) is nearer
    p = t.decide(world(20.0, t=12.1, ents=[clapper(9, 35.5, False)]), WinFc([subj(9, CC, 35.5, y=7.45)]), None, 3)
    assert t.last["goal_why"].endswith("rune: out") and p.no_hit == frozenset({9})
    # the Clapper standing at the landing between her and the back spot: out
    p = t.decide(world(29.0, t=12.2, ents=[clapper(9, 30.0, False)]), WinFc([subj(9, CC, 30.0, y=7.45)]), None, 3)
    assert t.last["goal_why"].endswith("rune: out")
