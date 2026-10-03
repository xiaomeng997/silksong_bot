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
    assert 4.0 - 1e-9 <= g.grid.sum() * 0.05 ** 2 < 4.0 + 0.25   # conservative: outline cells on top
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


def _ent(colliders, iid=1, tk="Clapper", state="Attack", hidden=False):
    dmg = {"dealt": 2, "eff": 2, "hazard_type": 1, "flags": 0, "parry": 0, "parryable": False,
           "can_cause_damage": True}
    return {"iid": iid, "type_key": tk, "hidden": hidden, "fsms": [{"name": "Control", "state": state}],
            "colliders": [dict(c, enabled=True, layer=11, damage=dmg) for c in colliders]}


def _clear(cm, box):
    cm.finish()
    return cm.clearance(box)[("Clapper", "Attack")]


@pytest.mark.parametrize("x0", [0.0, 0.013, 0.031])
def test_thin_and_edge_colliders_are_never_reported_clear(x0):
    # a 3 x 0.02 u damage sliver, an EdgeCollider2D segment and a 2-point collider through a HeroBox-sized box
    box = (1.0 + x0, 0.9, 1.4554 + x0, 3.1498)
    for col in ({"kind": "poly", "verts_world": [0.0, 2.0, 3.0, 2.0, 3.0, 2.02, 0.0, 2.02]},
                {"kind": "edge", "verts_world": [0.0, 2.003, 3.0, 2.011]},
                {"kind": "box", "verts_world": [0.0, 1.5, 3.0, 1.5]}):
        cm = cmap.CoverageMap(-1.0, -1.0, 5.0, 5.0, 0.05)
        cm.add_state({"f": 1, "ents": [_ent([col])]})
        assert _clear(cm, box) < 0, col


def test_polygon_edge_between_cell_centres_overlaps():
    # the polygon ends at x 2.024, inside the cell 2.00 - 2.05 but short of its centre: a box from x 2.0 overlaps it
    cm = cmap.CoverageMap(0.0, 0.0, 5.0, 5.0, 0.05)
    cm.add_state({"f": 1, "ents": [_ent([{"kind": "poly", "verts_world": [0.5, 1.0, 2.024, 1.0, 2.024, 2.0,
                                                                            0.5, 2.0]}])]})
    assert _clear(cm, (2.0, 1.2, 2.5, 1.8)) < 0
    assert 0.4 <= _clear(cm, (2.5, 1.2, 3.0, 1.8)) <= 0.476 + 1e-9    # never more than the true gap


def test_moving_collider_marks_its_sweep():
    # a 0.5 u box moving 1.2 u right per frame: the 0.7 u between two logged outlines was passed through
    cm = cmap.CoverageMap(0.0, 0.0, 10.0, 5.0, 0.05)
    for f, x in ((1, 1.0), (2, 2.2)):
        v = [x, 1.0, x + 0.5, 1.0, x + 0.5, 1.5, x, 1.5]
        cm.add_state({"f": f, "ents": [_ent([{"kind": "box", "verts_world": v}])]})
    assert cm.swept == 1
    assert _clear(cm, (1.7, 1.1, 1.9, 1.4)) < 0
    # a gap in the frames (or a jump past SWEEP_MAX) is no sweep
    cm = cmap.CoverageMap(0.0, 0.0, 10.0, 5.0, 0.05)
    for f, x in ((1, 1.0), (3, 2.2)):
        v = [x, 1.0, x + 0.5, 1.0, x + 0.5, 1.5, x, 1.5]
        cm.add_state({"f": f, "ents": [_ent([{"kind": "box", "verts_world": v}])]})
    assert cm.swept == 0 and _clear(cm, (1.7, 1.1, 1.9, 1.4)) > 0


def test_circle_octagon_and_hidden_entities():
    # the oracle exports a circle as its circumscribed octagon; the old code took the first vertex as the centre
    r, cx, cy = 1.0, 3.0, 2.0
    ang = np.deg2rad(22.5 + 45 * np.arange(8))
    v = np.stack([cx + r / np.cos(np.pi / 8) * np.cos(ang), cy + r / np.cos(np.pi / 8) * np.sin(ang)], 1)
    cm = cmap.CoverageMap(0.0, 0.0, 6.0, 5.0, 0.05)
    cm.add_state({"f": 1, "ents": [_ent([{"kind": "circle", "verts_world": v.ravel().tolist(), "r": r}],
                                        hidden=True)]})
    assert _clear(cm, (cx - 0.1, cy - 0.1, cx + 0.1, cy + 0.1)) < 0     # the centre is covered (hidden counts)
    assert 0.0 <= _clear(cm, (cx + 1.0 + 0.3, cy - 0.1, cx + 1.6, cy + 0.1)) <= 0.3
