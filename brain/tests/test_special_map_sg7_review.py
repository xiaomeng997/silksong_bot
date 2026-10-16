"""SG7 review (forum.md 63.5): the hammer carried one frame into the next state (the physics order), no stage rows
off the 60 Hz grid, the wall buckets' margin."""
from __future__ import annotations

import types

import numpy as np
from shapely import Polygon, box as sbox

from ssbot.combat import move_data as md
from ssbot.combat import special_map_rt as rt

MX, MY, HEAD = 0.0825 + 0.165, 0.12, 0.745 - 0.5262      # the map's dilation and the HeroBox's head (MapConfig)


def _world(name: str, pos, face: int) -> Polygon:
    v = np.asarray(md.HAMMER_POLY[name], float)
    return Polygon(np.c_[pos[0] + face * v[:, 0], pos[1] + v[:, 1]])


def test_recorded_hit_needs_the_carried_frame():
    """The specials probe (2026-10-11, live/specials_i1_s32 frame 2401446): an hp loss to Slam Collider 1 logged on
    the first Slam 2 frame. The hero stood on the floor (physics box y 3.01-5.09; x 35.46-35.96 on the last Slam 1
    frame, 35.29-35.79 on the Slam 2 frame); the Clapper faced her (+x) and lunged 31.79 -> 32.39 in that frame's
    physics step, Collider 1 still enabled. Each Slam 1 frame's polygon misses the map's dilated hero box of that
    frame; on the Slam 2 frame's positions (the carry) it meets it. Its bounding box (the SG4 rule) met it already."""
    def hero(x0, x1):
        return sbox(x0 - MX, 3.01 - MY, x1 + MX, 5.09 + HEAD + MY)
    last_s1 = _world("Slam Collider 1", (31.79, 7.4433), 1)
    s2_entry = _world("Slam Collider 1", (32.39, 7.4478), 1)
    assert not last_s1.intersects(hero(35.46, 35.96)) and last_s1.distance(hero(35.46, 35.96)) > 0.1
    assert s2_entry.intersects(hero(35.29, 35.79))
    assert sbox(*last_s1.bounds).intersects(hero(35.46, 35.96))


def test_carry_adds_the_next_state_first_frame_only():
    old = md.load_cl_slam(poly=True)
    new = md.load_cl_slam(poly=True, carry=True)
    v0 = old.variants("observed")[5]
    v1 = new.timeline(v0.frames, v0.phase, K=v0.K)
    e2, e3 = int(v0.entry["Slam 2"]), int(v0.entry["Slam Recover"])
    for k in range(v0.K):                              # every other frame unchanged
        if k in (e2, e3):
            continue
        a, b = v0.damage_shapes(k), v1.damage_shapes(k)
        assert len(a) == len(b)
        for (ba, pa), (bb, pb) in zip(a, b):
            assert np.allclose(ba, bb)
    # Slam 2's first frame: Collider 1 at that frame's lunge position (the last step is in it)
    b2 = [s for s in v1.damage_shapes(e2) if s[1] is not None]
    assert len(b2) == 2
    x0s = sorted(float(np.min(pg[:, 0])) for _, pg in b2)
    c1 = np.asarray(md.HAMMER_POLY["Slam Collider 1"], float)
    assert np.isclose(x0s[0], c1[:, 0].min() + v1.disp[e2])
    assert v1.disp[e2] > v1.disp[e2 - 1]               # the lunge's last step lands on the Slam 2 entry frame
    # Slam Recover's first frame: Collider 2 once more, then off
    assert len([s for s in v1.damage_shapes(e3) if s[1] is not None]) == 1
    assert len([s for s in v1.damage_shapes(e3 + 1) if s[1] is not None]) == 0
    assert len([s for s in v0.damage_shapes(e3) if s[1] is not None]) == 0


def _stub():
    spec = md.load_cl_slam(poly=True)
    V = spec.variants("observed")
    return types.SimpleNamespace(stage=True, vtl=[spec.timeline(v.frames, v.phase, K=160) for v in V],
                                 RMv=np.arange(len(V))[:, None].repeat(4, 1), spec=spec, tl=spec.timeline(K=160))


def test_observe_off_the_60hz_grid_is_every_variant():
    """A 120 fps / x0.5 slam: entries on half frames (the person's demo: Slam 0 at 48.5, Slam 1 at 53.0, Slam 2 at
    54.5); the template's whole-frame stage lengths do not hold there (Slam 1 1.5-2.5 frames), so no stage rows."""
    s = _stub()
    n = len(s.vtl)
    ok = rt.MapRuntime.observe(s, {"Slam 0": 48.497}, 52, 0, k_frac=52.0)
    assert len(ok) == n and s.rows is None
    ok = rt.MapRuntime.observe(s, {"Slam 0": 48.0}, 52, 0, k_frac=52.5)
    assert len(ok) == n and s.rows is None
    # on the grid (the 60 fps runs: within 0.06 of a whole frame): the exact rule, as before
    ok = rt.MapRuntime.observe(s, {"Slam 0": 48.95}, 52, 0, k_frac=51.95)
    assert 0 < len(ok) < n and all(int(s.vtl[i].entry["Slam 0"]) == 49 for i in ok)
    assert s.rows is not None
    assert ok == rt.MapRuntime.observe(s, {"Slam 0": 49}, 52, 0)
    assert rt.off_grid(48.5) and rt.off_grid(52.25) and not rt.off_grid(48.95) and not rt.off_grid(53.06)


def test_wall_bucket_keeps_a_margin_from_the_real_wall():
    B = rt.MapRuntime.wall_bucket
    arena = (14.01, 48.99)
    assert rt.WALL_MARGIN_U >= 0.1 + 0.165              # the wall-touch ray + one late run step
    assert B(48.99 - 8.5, 1, arena) == "_f7.25"          # a bucket's wall on the real wall: the next bucket in
    assert B(48.99 - 8.5 - rt.WALL_MARGIN_U, 1, arena) == "_f8.5"
    assert B(48.99 - 6.6, 1, arena) is None              # 6.6 - 0.35 < 6.5
    assert B(14.01 + 4.0, 1, arena) == "_b2.5"
    assert B(14.01 + 2.7, 1, arena) is None
    assert B(48.99 - 14.0, 1, arena) == ""               # the open floor: unchanged (out of the hammer's reach)
    for x0 in np.arange(20.0, 43.0, 0.05):               # never a bucket wall within the margin of the real one
        for face in (1, -1):
            b = B(float(x0), face, arena)
            if b:
                u = float(b[2:])
                real = (arena[1] - x0 if face > 0 else x0 - arena[0]) if b[1] == "f" else \
                       (x0 - arena[0] if face > 0 else arena[1] - x0)
                assert real - u >= rt.WALL_MARGIN_U - 1e-9
