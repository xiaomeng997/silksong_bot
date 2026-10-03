"""Coverage map / safe pockets (ssbot.tools.coverage_map): rasterized threat unions and hurtbox clearances on
synthetic STATEs, the wall-cling candidates of a box room, and the HeroBox placement."""
import numpy as np
import pytest

from ssbot.knowledge.kinematics import Terrain2D
from ssbot.tools import coverage_map as cmap


def _state(x0, y0, x1, y1, state="Attack", tk="Clapper"):
    v = [x0, y0, x1, y0, x1, y1, x0, y1]
    dmg = {"dealt": 2, "eff": 2, "hazard_type": 1, "flags": 0, "parry": 0, "parryable": False,
           "can_cause_damage": True}
    return {"f": 1, "ents": [{"type_key": tk, "fsms": [{"name": "Control", "state": state, "t": 0, "rt": 0}],
                              "colliders": [{"kind": "poly", "verts_world": v, "enabled": True, "layer": 11,
                                             "damage": dmg},
                                            {"kind": "poly", "verts_world": [p + 50 for p in v], "enabled": False,
                                             "layer": 11, "damage": dmg}]}]}


def test_union_and_clearance():
    cm = cmap.CoverageMap(0.0, 0.0, 20.0, 10.0, 0.05)
    cm.add_state(_state(5.0, 1.0, 6.0, 3.0))
    cm.add_state(_state(6.0, 1.0, 7.0, 3.0))                  # same attack: one union 5..7
    cm.add_state(_state(12.0, 1.0, 13.0, 2.0, state="Slam"))
    cm.finish()
    assert set(cm.groups) == {("Clapper", "Attack"), ("Clapper", "Slam")}
    g = cm.groups[("Clapper", "Attack")]
    assert g.frames == 2 and g.colliders == 2                 # the disabled collider is not a threat
    assert abs(g.grid.sum() * 0.05 ** 2 - 4.0) < 0.15
    c = cm.clearance((8.0, 1.0, 9.0, 3.0))                    # 1 u right of the Attack union, 3 u left of Slam
    assert abs(c[("Clapper", "Attack")] - 1.0) < 0.06
    assert abs(c[("Clapper", "Slam")] - 3.0) < 0.06
    assert cm.clearance((6.5, 2.0, 7.5, 4.0))[("Clapper", "Attack")] < 0     # overlapping
    ex = cm.extent(0.0)
    assert ex[0] == pytest.approx(5.0, abs=0.06) and ex[2] == pytest.approx(13.0, abs=0.06)


def test_hurtbox_mirrors_with_facing():
    # HeroBoxWallSlide: 0.876 x 1.28, offset 0.21 along local +x (the hero's left-facing forward)
    left = cmap.hurtbox(10.0, 5.0, -1, "wall")
    right = cmap.hurtbox(10.0, 5.0, 1, "wall")
    assert left[0] > 9.7 and left[2] > 10.6                  # facing left (wall on the left): box shifted right
    assert right[2] < 10.3 and right[0] < 9.4
    assert np.isclose(left[3] - left[1], 1.280464)


def test_wall_cling_candidates_in_a_box_room():
    # floor y 0 from x 0 to 20; a tall wall solid x -5..0 up to y 15
    terr = Terrain2D.from_boxes([(-5.0, -5.0, 20.0, 0.0), (-5.0, 0.0, 0.0, 15.0)])
    pts = cmap.candidate_points(terr, -1.0, 19.0, -1.0, 20.0, step=0.25)
    walls = [q for q in pts if q["kind"] == "wall"]
    assert walls and all(q["face"] == -1 and abs(q["pos"][0] - 0.265) < 1e-6 for q in walls)
    top = max(q["pos"][1] for q in walls)
    assert 14.0 < top <= 15.0 + 0.52                          # the highest cling has the box centre at the top
    stands = [q for q in pts if q["kind"] == "stand"]
    floor = [q for q in stands if q["pos"][1] < 5]
    assert floor and all(abs(q["pos"][1] - (0.015 + 1.5527)) < 1e-6 for q in floor)
    assert all(abs(q["pos"][1] - (15.015 + 1.5527)) < 1e-6 for q in stands if q["pos"][1] >= 5)   # on the wall top
