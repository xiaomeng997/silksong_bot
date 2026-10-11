"""The composite terrain-aware aim zones (tools.aim_zones; the person 2026-10-10: "draw them by the height of the ZONE
around the enemy, not by where I am now"): the hero-space rasters, the kernel (latency, walls), the height bands, the
reader (mirror, placement) and the overlay's aim layer (key 8)."""
from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np

from ssbot.tools import aim_zones as az
from ssbot.tools import zone_overlay as zo
from ssbot.tools.aim_ics import CLEAR, HB_HH, HB_HW, Library

CAM = {"V": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, -1, 0, -31.94, -9.6, -38.1, 1],
       "P": [2.6463542, 0, 0, 0, 0, 4.7046299, 0, 0, 0, 0, -1.4149377, -1, 0, 0, -24.1493798, 0],
       "rect": [0, 0, 1, 1], "screen": [1920, 1080]}


def test_height_bands():
    assert az.height_class(-0.3) is None
    assert az.height_class(0.0) == az.height_class(0.2) == "ground"
    assert az.height_class(0.25) == az.height_class(1.4) == "low"
    assert az.height_class(1.5) == az.height_class(9.0) == "high"
    assert set(az.CLASS_STATES["low"]) <= set(az.STATES) and set(az.CLASS_STATES["high"]) <= set(az.STATES)
    assert all(s.endswith("_nd") for c in ("low", "high") for s in az.CLASS_STATES[c])     # the air: no dash


def test_hero_shape_dilates_by_the_herobox_and_clearance():
    sh = np.ones((2, 2), bool)                        # u, v in [0, 0.1) x [0, 0.1)
    m, ix0, iy0 = az.hero_shape(sh, 0, 0)
    xs = (ix0 + np.nonzero(m.any(0))[0]) * az.D
    ys = (iy0 + np.nonzero(m.any(1))[0]) * az.D
    # every HeroBox centre whose box (+ CLEAR) touches the cell is forbidden, the lattice rounds outward only
    assert xs.min() <= -(HB_HW + CLEAR) + 1e-9 and xs.max() + az.D >= 0.1 + HB_HW + CLEAR - 1e-9
    assert ys.min() <= -(HB_HH + CLEAR) + 1e-9 and ys.max() + az.D >= 0.1 + HB_HH + CLEAR - 1e-9
    assert xs.max() + az.D <= 0.1 + HB_HW + CLEAR + 0.1 + 1e-9                  # at most one cell too wide
    assert az.hero_shape(np.zeros((3, 3), bool), 0, 0) is None


def _lib(paths) -> Library:
    q = np.ascontiguousarray(np.round(np.array(paths) / 0.03).astype(np.int16))
    n = len(q)
    div = np.zeros(n, np.int16)
    return Library(q, 0.03, div, np.array([True] * n), np.arange(n, dtype=np.int64))


def _frames(first: int = 5, last: int = 30) -> az.Frames:
    """A still box over x in [-1, 1], y in [-1, 1] (fan coordinates) that hurts from `first` to `last`."""
    J = last + 1
    m, ix0, iy0 = az.hero_shape(np.ones((40, 40), bool), -20, -20)
    fi = np.zeros((1, J, 5), np.int64)
    for j in range(first, J):
        fi[0, j] = (0, m.shape[0], m.shape[1], ix0, iy0)
    return az.Frames(m.ravel(), fi, np.zeros((1, J, 2)), np.array([J], np.int64), np.zeros(1, np.int64),
                     np.zeros((1, 6)), (-1e9, 1e9))


def _run(fr, lib, cells, hxhi=1e9, lat=0, jmax=40):
    import ssbot.tools.aim_zones as m
    sc = SimpleNamespace(fr=fr, var=np.array([[0.0, 1.0]]), nchunk=2, mv=SimpleNamespace(j_max=jmax))
    cells = np.asarray(cells, np.float64)
    cf = np.zeros((len(cells), az.C_NF))
    cf[:, az.C_EXLO], cf[:, az.C_EXHI], cf[:, az.C_EYMIN] = -1e9, 1e9, -1e9
    cf[:, az.C_HXLO], cf[:, az.C_HXHI], cf[:, az.C_HYHI] = -1e9, hxhi, 1e9
    ci = np.zeros((len(cells), 2), np.int64)
    ci[:, 1] = 1
    return m.Scanner.run(sc, lib, az.lib_ext(lib), cells, cf, ci, lat)


def test_kernel_escapes_inescapable_and_walls():
    T = 40
    still = np.zeros((T, 2))
    run = np.stack([0.3 * np.arange(1, T + 1), np.zeros(T)], 1)              # 0.3 u per frame toward +x
    lib = _lib([still, run])
    fr = _frames(first=8)
    out = _run(fr, lib, [[0.0, 0.0], [-0.9, 0.0], [5.0, 0.0]])
    # the centre runs out (2.25 u half a frame before frame 8 > 1 + 0.33 + a lattice cell), -0.9 does not (1.35 u),
    # 5 u is never touched (stands still)
    assert out[0] == 1 and out[1] == -1 and out[2] >= 0
    # a wall 0.5 u to the right: running is pruned, so the centre is inescapable too
    out = _run(fr, lib, [[0.0, 0.0], [5.0, 0.0]], hxhi=0.5)
    assert out[0] == -1
    # a box already there at the decision: nothing escapes
    assert _run(_frames(first=0), lib, [[0.0, 0.0]])[0] == -1


def test_kernel_sweeps_the_hero_within_a_frame():
    """A hero that jumps across a thin wall of damage inside one frame is hit (the swept test)."""
    T = 10
    jump = np.zeros((T, 2))
    jump[2:, 0] = 3.0                                 # 3 u in one frame: across the box
    lib = _lib([jump])
    J = 11
    m, ix0, iy0 = az.hero_shape(np.ones((40, 2), bool), 20, -20)              # x in [1.0, 1.1)
    fi = np.zeros((1, J, 5), np.int64)
    fi[0, :] = (0, m.shape[0], m.shape[1], ix0, iy0)
    fr = az.Frames(m.ravel(), fi, np.zeros((1, J, 2)), np.array([J], np.int64), np.zeros(1, np.int64),
                   np.zeros((1, 6)), (-1e9, 1e9))
    assert _run(fr, lib, [[-1.0, 0.0]], jmax=10)[0] == -1


def _write_table(path, gx, gy, zone_cells, nyb=1):
    keys = [az.bin_name(b) for b in az.x_bin_keys()]
    parts, offs = [], [0]
    for lat in az.LATS:
        for yi in range(nyb):
            for bn in keys:
                c = np.array(zone_cells.get((lat, bn), []), np.int32).reshape(-1, 2)
                parts.append(c)
                offs.append(offs[-1] + len(c))
    meta = {"move": {"name": "RE_STAB"}, "y_bins": [7.0] * nyb, "x_bins": keys, "lats": list(az.LATS)}
    np.savez_compressed(path, meta=np.array(json.dumps(meta)), grid_x=gx, grid_y=gy,
                        cells=np.concatenate(parts), offs=np.array(offs, np.int64))


def test_reader_bins_mirror_and_placement(tmp_path):
    gx = np.round(np.arange(10) * 0.1 + 0.05, 3)
    gy = np.round(np.arange(10) * 0.1 - 0.95, 3)
    nx = len(gx)
    # open floor: ground cell (row 2, col 3); the wall bin x 16.5 toward the left wall: + a low-air cell
    zc = {(2, az.bin_name(b)): [[2 * nx + 3, 1]] for b in az.x_bin_keys()}
    zc[(2, "x16.5L")] = [[2 * nx + 3, 1], [5 * nx + 4, 2]]
    p = tmp_path / "aim_zones_RE_STAB.npz"
    _write_table(p, gx, gy, zc)
    r = az.AimZones(p)
    z = r.zone(None, 7.0, 1, lat=2)
    assert z[2, 3] == 1 and (z != 0).sum() == 1
    assert (r.zone(None, 7.0, 1, lat=0) != 0).sum() == 0
    assert r.zone(16.6, 7.0, -1, lat=2)[5, 4] == 2 and r.zone(16.6, 7.0, 1, lat=2)[5, 4] == 0
    assert r.area(16.6, 7.0, -1)["low"] == 0.01
    # placement: the ground cell's centre is (0.35, -0.75) from the enemy, mirrored by the side
    assert r.inescapable((30.0 + 0.35, 7.0 - 0.75), (30.0, 7.0), 1) == 1
    assert r.inescapable((30.0 - 0.35, 7.0 - 0.75), (30.0, 7.0), -1) == 1
    assert r.inescapable((30.0 - 0.35, 7.0 - 0.75), (30.0, 7.0), 1) == 0
    polys = r.world_polys(30.0, 7.0, -1)
    q = polys["ground"][0]
    # (the attack-range outlines run a quarter cell inside the cell edges)
    assert np.allclose([q[:, 0].min(), q[:, 0].max()], [30.0 - 0.4, 30.0 - 0.3], atol=0.026)
    assert np.allclose([q[:, 1].min(), q[:, 1].max()], [7.0 - 0.8, 7.0 - 0.7], atol=0.026)


def test_pending_moves():
    assert az.pending_move("Song Reed", "Stab Antic") == "RE_STAB"
    assert az.pending_move("Song Automaton Tiny", "Fire Ready") == "AT_DIVE"
    assert az.pending_move("Song Pilgrim Maestro", "Fire Antic") == "MA_SLASH"
    assert az.pending_move("Song Heavy Sentry", "Jump Antic") == "CC_JUMP"
    assert az.pending_move("Song Heavy Sentry", "Cast Slam Antic 2") == "CC_JUMP_CAST"
    assert az.pending_move("Song Reed", "Stab 1") is None


def test_overlay_aim_layer_draws_and_labels():
    g = zo.Grid()
    size = (1920, 1080)
    Hw, _ = zo.homography(g, CAM, size)
    sq = np.array([[20.0, 4.0], [21.0, 4.0], [21.0, 5.0], [20.0, 5.0]])
    fr = {"ks": (0,), "support": {}, "cols": [], "hero": None, "cam": CAM, "range": {0: []},
          "aim": [(1, "Reed 1", (40, 200, 40), {"ground": [sq]}, "aim RE_STAB lat2: G 1.0 u2", (20.5, 7.0)),
                  (2, "Tiny 1", (200, 40, 40), {}, "aim AT_DIVE lat2: zone 0", (30.0, 12.0))]}
    x, y = (int(round(v)) for v in zo._to_px(Hw, np.array([[20.5, 4.5]]))[0])
    on = zo.render(fr, g, size, zo.View(mode="range", aim=True))
    off = zo.render(fr, g, size, zo.View(mode="range", aim=False))
    assert on[y, x, 3] > 0 and off[y, x, 3] == 0
    lines = [t for t, _ in zo.legend_lines(fr, zo.View(mode="range", aim=True), "cfg")]
    assert any("AIM ZONES" in t for t in lines) and any("zone 0" in t for t in lines)
    assert not any("AIM ZONES" in t for t, _ in zo.legend_lines(fr, zo.View(mode="range"), "cfg"))
    v = zo.View(mode="range+red", aim=True)
    assert v.range_aim() and not zo.View(mode="yellow+red", aim=True).range_aim()


def test_live_command_toggles_aim():
    ov = SimpleNamespace(view=zo.View(mode="range"), dirty=False)
    zo.LiveOverlay._apply(ov, "aim on")
    assert ov.view.aim
    zo.LiveOverlay._apply(ov, "aim")
    assert not ov.view.aim
