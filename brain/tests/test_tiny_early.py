"""The Tiny's dive drawn from the Maestro's antic (the person 2026-10-10: "the path should be known half a second
earlier"): the chain simulator (tiny.simulate), the early estimate in Fire Ready, the whole-path hook
(RangeTracker.path / ladder's paths) and the overlay's dive outlines. Offline, synthetic data."""
import numpy as np
import pytest

from ssbot.combat import attack_range as ar
from ssbot.combat.are_types import tiny as ti

C = ar.CELL
TINY = "Song Automaton Tiny"
MAE = "Song Pilgrim Maestro"


def _tiny(st, x, y, vx=0.0, vy=0.0, iid=9, tin=0.0):
    return {"type_key": TINY, "iid": iid, "pos": [x, y, 0.0], "vel": [vx, vy], "flipX": False,
            "fsms": [{"name": "Control", "state": st, "t": tin}],
            "cols": [{"name": "Song Automaton Tiny(Clone)", "enabled": True,
                      "verts_world": [x - 0.5, y - 0.54, x + 0.5, y - 0.54, x + 0.5, y + 0.54, x - 0.5, y + 0.54]}]}


def _mae(x, y, st="Fire Antic", iid=2, vx=0.0):
    return {"type_key": MAE, "iid": iid, "pos": [x, y, 0.0], "vel": [vx, 0.0], "flipX": False,
            "fsms": [{"name": "Control", "state": st, "t": 0.0}], "cols": []}


def _tracker():
    spec = ar.SPECS[TINY]
    body = np.ones((int(1.08 / C), int(1.0 / C)), bool)
    tp = ar.Template(nb=60, shape=[body] * 60, origin=np.tile(np.array([[-10, -11]], np.int32), (60, 1)),
                     disp=np.zeros((60, 2)), n=1)
    tab = ar.RangeTable(spec=spec, templates={("AT_FIRE_READY", "main"): tp, ("AT_DIVE", "main"): tp},
                        meta={"face_flip1": 1})
    return ar.RangeTracker(tables={TINY: tab})


def test_dive_falls_to_the_floor_slides_past_the_hero_then_pulls_up():
    rows = ti.simulate("fire", 40.0, 14.0, -24.0, -39.0 * ti.FIRE_DY, 0.0, (42.0, 11.0, 0.0, 0.0), 1, 25.0, side=-1)
    phases = [r[3] for r in rows]
    assert phases.index("brake") < phases.index("pull") < phases.index("ret")
    b = rows[phases.index("brake")]
    assert b[2] <= ti.BRAKE_Y and b[2] > ti.BRAKE_Y - 1.0          # the 2 u ray meets the floor
    p = rows[phases.index("pull")]
    assert p[1] == pytest.approx(25.0 - ti.PASS_U, abs=0.5)         # 5 u past the hero (Is Active by then)
    # nothing beyond the arena walls
    assert all(ti.X_WALLS[0] <= r[1] <= ti.X_WALLS[1] for r in rows)


def test_dive_into_a_wall_bonks_back():
    rows = ti.simulate("fire", 18.0, 8.0, -24.0, -10.0, 0.0, (30.0, 11.0, 0.0, 0.0), 1, 5.0, side=-1)
    phases = [r[3] for r in rows]
    assert "bonk" in phases
    i = phases.index("bonk")
    assert rows[i][1] == pytest.approx(ti.X_WALLS[0], abs=0.6) and rows[i + 5][1] > rows[i][1]   # back off the wall


def test_fire_ready_flies_to_the_slash_point_behind_the_maestro():
    # the hero left of the Maestro (sm -1): the Slash Point is 1.87 u right of it and 1.88 u above
    rows = ti.simulate("ready", 41.87, 12.88, 0.3, 0.0, 0.0, (40.0, 11.0, 0.0, 0.0), -1, 20.0, t_fire=0.7)
    k = next(i for i, r in enumerate(rows) if r[3] != "ready")
    assert rows[k][0] == pytest.approx(0.7, abs=ti.FIXED_DT)
    assert rows[k][1] == pytest.approx(40.0 + 1.87, abs=0.1) and rows[k][2] == pytest.approx(11.0 + 1.88, abs=0.1)
    assert rows[k + 3][1] < rows[k][1]                               # then dives toward the hero (left)


def _feed_antic(trk, hero_x, frames):
    for i in range(frames):
        trk.feed({"dt": ar.FT, "hero": {"pos": [hero_x, 4.6]},
                  "ents": [_mae(40.0, 11.0), _tiny("Fire Ready", 41.87, 12.88, tin=(i + 1) * ar.FT)]})


def test_early_estimate_puts_the_body_on_the_dive_before_it_starts():
    trk = _tracker()
    _feed_antic(trk, 20.0, 12)                                       # 0.2 s into the antic
    e0 = trk.estimate(9, 0)
    x0, y0, x1, y1 = e0.raw.bbox()
    assert 0.5 * (x0 + x1) == pytest.approx(41.87, abs=0.1)          # k 0: the body now
    e = trk.estimate(9, 36)                                          # 0.6 s ahead: the dive has started
    x0, y0, x1, y1 = e.raw.bbox()
    assert 0.5 * (y0 + y1) < 12.0 and 0.5 * (x0 + x1) < 41.5         # down and toward the hero (left)
    assert x1 - x0 < 1.6                                             # one side only (the hero 22 u away)


def test_ladder_gives_the_whole_dive_and_the_other_side_only_when_the_hero_can_cross():
    trk = _tracker()
    _feed_antic(trk, 20.0, 6)
    _, swept = trk.ladder((0, 36), sweep=36)
    sure, maybe = trk.paths[9]
    x0, y0, x1, y1 = sure.bbox()
    assert y0 < ti.BRAKE_Y and x0 < 20.0                            # down to the floor, slides past the hero
    assert x1 < 43.5                                                 # nothing on the far side
    assert not maybe.m.any() or maybe.bbox()[2] < 43.5               # maybe: only a longer slide, same side
    # the hero right under the FIRE point: both sides
    trk = _tracker()
    _feed_antic(trk, 41.8, 6)
    trk.ladder((0, 36), sweep=36)
    sure, maybe = trk.paths[9]
    assert maybe.m.any()
    x0, _, x1, _ = ar.union([sure, maybe]).bbox()
    assert x0 < 38.0 and x1 > 45.0
    # in the dive: the rest of it (to the floor, past the hero); back in Ready: no path
    trk.feed({"dt": ar.FT, "hero": {"pos": [20.0, 4.6]}, "ents": [_mae(40.0, 11.0, "Slash 1"),
                                                                  _tiny("Fire", 41.0, 12.0, -24.0, -36.0)]})
    trk.ladder((0, 36), sweep=36)
    sure, _ = trk.paths[9]
    assert sure.bbox()[1] < ti.BRAKE_Y and sure.bbox()[0] < 20.0
    trk.feed({"dt": ar.FT, "hero": {"pos": [20.0, 4.6]}, "ents": [_mae(40.0, 11.0, "Forum Fly"),
                                                                  _tiny("Ready", 41.0, 12.0)]})
    trk.ladder((0, 36), sweep=36)
    assert 9 not in trk.paths


def test_overlay_range_layer_lists_the_dive_outlines():
    from ssbot.tools import zone_overlay as zo
    trk = _tracker()
    _feed_antic(trk, 20.0, 6)
    eng = zo.ZoneEngine.__new__(zo.ZoneEngine)
    eng.rng = trk
    eng.names = {9: "Tiny_1"}
    eng.name = lambda iid: "Tiny_1"
    eng.color = lambda iid: (0, 200, 0)
    res = eng.range_layer((0, 36), sweep=36, hero=False)
    labs = [r[4] for r in res["range_swept"]]
    assert "path 0-36" in labs and "dive" in labs
