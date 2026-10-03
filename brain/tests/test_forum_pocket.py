"""ssbot.tools.forum_pocket: exact-enough distance from a collider (box, polygon, the oracle's 8-point circle) to the
pocket box."""
import math

from ssbot.tools.forum_pocket import POCKET, collider_box_distance


def _circle(cx, cy, r):
    v = []
    for k in range(8):
        a = k * math.pi / 4
        v += [cx + r * math.cos(a), cy + r * math.sin(a)]
    return {"kind": "circle", "r": r, "verts_world": v}


def test_distances():
    box = (0.0, 0.0, 1.0, 1.0)
    sq = {"kind": "box", "verts_world": [2.0, 0.0, 3.0, 0.0, 3.0, 1.0, 2.0, 1.0]}
    assert abs(collider_box_distance(sq, box) - 1.0) < 1e-6
    wrap = {"kind": "poly", "verts_world": [-1.0, -1.0, 2.0, -1.0, 2.0, 2.0, -1.0, 2.0]}
    assert collider_box_distance(wrap, box) == 0.0          # the polygon wraps the box
    diag = {"kind": "poly", "verts_world": [2.0, 2.0, 3.0, 2.0, 3.0, 3.0]}
    assert abs(collider_box_distance(diag, box) - math.sqrt(2.0)) < 1e-3
    # the Jump Cast rune: r 7.19 centred at (14.38, 3.34) under the pocket: its top is 10.53, 2.0 below the pocket
    assert abs(collider_box_distance(_circle(14.38, 3.34, 7.187), POCKET) - (POCKET[1] - 3.34 - 7.187)) < 1e-6
