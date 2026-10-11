"""Idle velocity compensation of the attack-range estimate (the person 2026-10-10; combat.attack_range carry_shift /
carry_body / IDLE_CARRY) and its measure (tools.are_idlevel.measure): offline, synthetic data."""
import numpy as np
import pytest

from ssbot.combat import attack_range as ar
from ssbot.core.forum import FLOOR_Y, WALL_L, WALL_R, dome_y
from ssbot.tools.are_idlevel import MS, measure

C = ar.CELL


def box(x0, y0, x1, y1):
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], float)


def test_carry_shift_is_velocity_times_time():
    dx, dy = ar.carry_shift([box(29.5, 7.0, 30.5, 9.0)], (6.0, -3.0), 0.2)
    assert dx == pytest.approx(1.2) and dy == pytest.approx(-0.6)
    assert ar.carry_shift([box(29.5, 7.0, 30.5, 9.0)], (6.0, -3.0), 1 / 60) == pytest.approx((0.1, -0.05))
    assert ar.carry_shift([box(29.5, 7.0, 30.5, 9.0)], None, 0.5) == (0.0, 0.0)
    assert ar.carry_shift([box(29.5, 7.0, 30.5, 9.0)], (float("nan"), 0.0), 0.5) == (0.0, 0.0)


def test_carry_shift_stops_at_the_floor_walls_and_dome():
    b = box(30.0, FLOOR_Y + 0.2, 31.0, FLOOR_Y + 2.2)
    assert ar.carry_shift([b], (0.0, -10.0), 0.5)[1] == pytest.approx(-0.2)          # the floor
    b = box(WALL_R - 1.5, 4.0, WALL_R - 0.5, 6.0)
    assert ar.carry_shift([b], (10.0, 0.0), 0.5)[0] == pytest.approx(0.5)             # the right wall
    b = box(WALL_L + 0.3, 4.0, WALL_L + 1.3, 6.0)
    assert ar.carry_shift([b], (-10.0, 0.0), 0.5)[0] == pytest.approx(-0.3)           # the left wall
    top = min(dome_y(31.0), dome_y(32.0))
    b = box(31.0, top - 2.3, 32.0, top - 0.3)
    assert ar.carry_shift([b], (0.0, 10.0), 0.5)[1] == pytest.approx(0.3, abs=1e-6)   # the dome
    # a body already past a bound (a Clapper falling in from above the dome) is not pushed back
    b = box(21.0, 22.0, 22.0, 24.0)
    assert ar.carry_shift([b], (0.0, 5.0), 0.5)[1] == 0.0
    assert ar.carry_shift([b], (0.0, -5.0), 0.5)[1] == pytest.approx(-2.5)


def _ent(st, x=20.0, vel=None):
    e = {"type_key": "Song Pilgrim 03", "iid": 7, "pos": [x, 4.87, 0.0], "flipX": True,
         "fsms": [{"name": "Attack", "state": st, "t": 0.0}],
         "cols": [{"name": "Body Damager", "enabled": True,
                   "verts_world": [x - 0.44, 4.0, x + 0.44, 4.0, x + 0.44, 6.15, x - 0.44, 6.15]}]}
    if vel is not None:
        e["vel"] = list(vel)
    return e


def _table():
    meta = {"face_flip1": 1, "walls": [14.0, 49.0]}
    return ar.RangeTable(spec=ar.CHORISTOR, templates={}, meta=meta)


def test_tracker_idle_body_is_carried_by_its_velocity():
    trk = ar.RangeTracker(tables={"Song Pilgrim 03": _table()})
    trk.feed({"dt": ar.FT, "hero": {"pos": [25.0, 4.5]}, "ents": [_ent("Battle Idle", vel=(3.0, 0.0))]})
    x0, _, x1, _ = trk.estimate(7, 0).raw.bbox()
    assert 0.5 * (x0 + x1) == pytest.approx(20.0, abs=2 * C)                       # k 0: the body now
    x0, _, x1, _ = trk.estimate(7, 30).raw.bbox()
    assert 0.5 * (x0 + x1) == pytest.approx(21.5, abs=2 * C)                       # k 30: + 3 u/s x 0.5 s
    assert trk.estimate(7, 30).raw.area() == pytest.approx(trk.estimate(7, 0).raw.area(), rel=0.05)
    ar.IDLE_CARRY = False
    try:
        x0, _, x1, _ = trk.estimate(7, 30).raw.bbox()
        assert 0.5 * (x0 + x1) == pytest.approx(20.0, abs=2 * C)                   # the switch: the body now
    finally:
        ar.IDLE_CARRY = True
    trk.feed({"dt": ar.FT, "hero": {"pos": [25.0, 4.5]}, "ents": [_ent("Battle Idle")]})   # no velocity exported
    x0, _, x1, _ = trk.estimate(7, 30).raw.bbox()
    assert 0.5 * (x0 + x1) == pytest.approx(20.0, abs=2 * C)


def test_measure_margins_and_sides():
    R = ar.poly_mask([box(20.0, 4.0, 21.0, 6.0)])
    aR, cov, area, side, big = measure(R, R, +1)
    assert cov[0] == aR and big == 0.0 and not side.any()
    E = ar.poly_mask([box(19.5, 4.0, 20.5, 6.0)])                    # 0.5 u behind the real body
    aR, cov, area, side, big = measure(E, R, +1)
    assert big == pytest.approx(0.5, abs=1.5 * C)
    assert side[0] == pytest.approx(0.5, abs=1.5 * C) and side[1] == 0.0          # missed in front
    i = MS.index(0.5)
    assert cov[i] == aR and cov[i - 1] < aR                          # m 0.5 covers it, 0.25 does not
    assert list(area) == sorted(area) and area[0] == pytest.approx(aR, rel=0.02)
    aR, cov, area, side, big = measure(E, R, -1)                     # facing -x: the same cells are behind
    assert side[1] > 0.0 and side[0] == 0.0
