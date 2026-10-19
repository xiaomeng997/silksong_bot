"""SP-AIR1: SSBOT_FORUM_AIRSHOW (combat.air_show) - the air show's controller: off by default, the Clapper's boxes by
time, the up plan from the ground, the drop / keep plans in the air, the floor as a danger, the step's ownership."""
from __future__ import annotations

import numpy as np
import pytest

from ssbot.combat import air_show as asw
from ssbot.combat import rune_pogo as rp
from ssbot.combat.air_chain import ChainSim
from ssbot.knowledge import kinematics as kin
from ssbot.knowledge.kinematics import HoldState, Terrain2D

FLOOR = asw.FLOOR


@pytest.fixture(scope="module")
def world():
    p = kin.HeroParams.load(kin.REPO / "knowledge" / "1.0.30000" / "kinematics" / "hero_wanderer_forum.json")
    terr = Terrain2D.from_boxes([(-200.0, FLOOR - 10.0, 260.0, FLOOR), (0.0, 0.0, asw.WALL_L, 40.0),
                                 (asw.WALL_R, 0.0, 70.0, 40.0)])
    return p, terr


def clapper(x=30.0, st="Idle", t=0.1, face=1, vx=0.0, hp=200):
    return {"iid": 7, "type_key": "Song Heavy Sentry", "pos": [x, FLOOR + asw.POS_Y], "vel": [vx, 0.0],
            "flipX": face > 0, "hp": hp, "is_dead": False, "colliders": [],
            "fsms": [{"name": "Control", "state": st, "t": t}]}


def sim_at(world, hx, y, vy=0.0, ground=False, face=-1):
    p, terr = world
    S = kin.initial_state(p, hx, y, vy=vy, facing=face, ground=ground)
    return ChainSim(S, np.zeros(2, np.int64), HoldState.idle(1), p, terr, 1000, 1002)


def planner(world, e, st, hx, y, vy=0.0, ground=False, t=0.1, face=-1):
    sim = sim_at(world, hx, y, vy, ground, face)
    cfg = asw.AsCfg()
    ctx = rp.Ctx(F0=1004, b_box=rp.body_box(e), b_x=float(e["pos"][0]), b_ok=True, tx=float(e["pos"][0]), face=face,
                 ground=ground, atk_ready_f=1004)
    tl = asw.its_timeline(e, st, t, sim.f - sim.fo, sim.off + cfg.horizon, cfg, hx)
    return asw.ShowPlanner(sim, ctx, cfg, tl), tl


def test_default_off():
    assert asw.AIRSHOW is False                        # the suite runs without SSBOT_FORUM_AIRSHOW
    c = asw.cfg_from_env()
    assert c.after_c == 46 and c.floor_c == 30 and c.horizon == 96


def test_slam_timeline_has_the_hammer_and_the_lunge():
    e = clapper(30.0, "Slam Antic", 0.0, face=1)
    tl = asw.its_timeline(e, "Slam Antic", 0.0, 0, 100, asw.AsCfg(), 34.0)
    assert tl.kind == "slam" and tl.k0 == 0 and len(tl.ham) == 4
    fr = sorted({i for i, _x, _y in tl.ham[0]})
    assert fr[0] == 54 and fr[-1] in (63, 64)              # Slam 1 from k 54, Slam 2 (+ its carried frame)
    # Slam Collider 1 at k 54: -1.91 .. 6.24 u along its facing from its lunging centre, up to 7.56 u above the floor
    i, px, py = next(h for h in tl.ham[0] if h[0] == 54)
    assert px.max() - px.min() == pytest.approx(8.146, abs=0.01) and px.min() > 30.0
    assert py.max() - FLOOR == pytest.approx(7.56, abs=0.05)
    # the lunge moves its body forward (+x) 3 - 4.3 u by Slam 2
    assert tl.body[0, 70, 0] - tl.body[0, 10, 0] > 2.9


def test_cast_body_top_by_frame():
    e = clapper(30.0, "Spell Antic", 0.0)
    tl = asw.its_timeline(e, "Spell Antic", 0.0, 0, 100, asw.AsCfg(), 34.0)
    tops = tl.tgt[:, 3] - FLOOR
    assert tops[0] == pytest.approx(3.19) and tops[5] == pytest.approx(4.36) and tops[20] == pytest.approx(4.78)


def test_up_plan_from_the_ground_hits_its_head(world):
    e = clapper(30.0, "Idle", 0.1, face=1)
    pl, _ = planner(world, e, "Idle", 35.5, 4.568, ground=True)
    ups = pl.evaluate(pl.ups(35.5, 30.0, 0))
    safe = [p for p in ups if p.bad is None and p.contact is not None]
    assert safe, "no safe up plan 5.5 u from an Idle Clapper"
    q = min(safe, key=lambda p: (p.contact, p.jump[0]))
    assert q.jump[0] - 1004 <= 10 and q.contact - 1004 < 60


def test_air_drop_on_its_head_and_the_floor_is_a_danger(world):
    e = clapper(30.0, "Idle", 0.1, face=1)
    # her box bottom ~5.2 u above the floor, falling, right above it: a drop with a contact is picked
    pl, _ = planner(world, e, "Idle", 30.3, FLOOR + 5.2 + 1.553, vy=-2.0)
    plans = pl.evaluate(pl.drops(30.3, 30.0) + pl.keeps(30.3, 30.0))
    q = asw.pick(plans)
    assert q is not None and q.kind == "drop" and q.contact is not None and q.bad is None
    # far from it (nothing to pogo) every plan lands: no safe plan (the floor)
    pl2, _ = planner(world, clapper(16.0, "Idle", 0.1), "Idle", 40.0, FLOOR + 3.0 + 1.553, vy=-2.0)
    plans2 = pl2.evaluate(pl2.keeps(40.0, 16.0))
    assert all(p.bad is not None for p in plans2)


def test_step_owns_the_keys_and_yields_with_two(world):
    a = asw.AirShow()
    s = {"f": 1000, "hero": {"box": [35.25, FLOOR, 35.75, FLOOR + 2.08], "pos": [35.5, 4.568], "vel": [0, 0],
                             "health": 7, "facing": -1, "tm": {}, "anim": {"clip": "Idle"}, "cstate": [0, 0]},
         "ents": [clapper(30.0, "Idle", 0.1)], "act": {"mask": 0}}
    sim = sim_at(world, 35.5, 4.568, ground=True)
    m = a.step(1000, s, True, True, sim)
    assert isinstance(m, int)
    s2 = dict(s, ents=[clapper(30.0), dict(clapper(20.0), iid=8)])
    assert a.step(1001, s2, True, True, sim) is None
    st = a.stats()
    assert st["success"] is False and st["n_chains"] == 0 and "chains" in st


def test_jump_flight_is_a_danger(world):
    # its jump in place under her: the rising flight body (FLIGHT_Y0, grown 0.8 / 0.5 u) makes staying over it bad
    e = clapper(30.0, "Air", 0.05, face=1)
    pl, _ = planner(world, e, "Air", 30.5, FLOOR + 5.0 + 1.553, vy=0.0)
    pl.c.f_fall = (1004, 1004 + 53, 30.0, 30.0, 1)          # (the default margins 0.3 u)
    pl.c.L, pl.c.f_L, pl.c.fface = 30.0, 1004 + 53, 1
    plans = pl.evaluate(pl.keeps(30.5, 33.0))
    stay = [p for p in plans if p.dirk == 0]
    assert stay and all(p.bad is not None for p in stay)


def test_face_wall_keeps_her_on_its_wall_side(world, monkeypatch):
    # NOTE 3: near the left wall (4 u) a contact on an Idle Clapper only with her centre >= 0.4 u left of its centre
    monkeypatch.setenv("SSBOT_FORUM_AIRSHOW_SET", "face=wall")
    a = asw.AirShow()
    assert a.cfg.face == "wall" and a._face_side(clapper(18.0)) == -1 and a._face_side(clapper(31.0)) == 0
    e = clapper(18.0, "Idle", 0.1, face=1)
    pl, _ = planner(world, e, "Idle", 18.6, FLOOR + 5.2 + 1.553, vy=-2.0)
    free = [p for p in pl.evaluate(pl.drops(18.6, 18.0)) if p.contact is not None]
    pl2, _ = planner(world, e, "Idle", 18.6, FLOOR + 5.2 + 1.553, vy=-2.0)
    pl2.ac = a.cfg
    pl2.face_side = -1
    bb = rp.body_box(e)
    pl2.face_off = 18.0 - 0.5 * (bb[0] + bb[2])
    side = [p for p in pl2.evaluate(pl2.drops(18.6, 17.0)) if p.contact is not None]
    assert len(free) > len(side)
    for p in side:
        i = pl2._i(p.contact)
        n = [q.key() for q in pl2.last_sub].index(p.key())
        assert float(pl2.last_ro.centre[n, i, 0]) - 18.0 <= -0.4 + 1e-6
