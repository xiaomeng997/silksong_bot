"""Aimed-attack inescapable zones (ssbot.tools.aim_ics): state keys (locked, walls kept), bin neighbours, the Reed's
and the spear's fan / spawn rules, the physics-clock kernel on hand-made paths (clearance, homing), the reader's
lookup, mirroring and locked states, and the stored tables' coverage."""
import json

import numpy as np
import pytest

from ssbot.tools import aim_ics as ai

REED = ai.FAMILIES_BY_TYPE["Reed"]["measured"]
SPEAR = ai.FAMILIES_BY_TYPE["Clawmaiden"]["measured"]


def test_state_keys():
    assert ai.hero_state_key(0.0, 0.0, True, True) == "ground"
    assert ai.hero_state_key(0.0, 0.0, True, False) == "ground_nd"
    assert ai.hero_state_key(0.0, 0.0, True, False, dashing=-1) == "dash_toward"
    assert ai.hero_state_key(0.0, 0.0, True, True, wall_behind=0.5) == "ground_w0.3"
    assert ai.hero_state_key(0.0, 0.0, True, False, wall_behind=2.0) == "ground_nd_w0.3"     # the wall is kept
    assert ai.hero_state_key(0.8, -2.0, False, False) == "air_h1.0_rest_nd"
    assert ai.hero_state_key(0.2, 9.0, False, True) == "air_h0.25_rise_d"
    assert ai.hero_state_key(6.0, -12.0, False, True, wall_behind=0.2) == "air_h5.0_fall_d_w0.3"
    assert ai.hero_state_key(2.0, 0.0, False, True, wall_behind=2.0) == "air_h2.5_rest_d_w1.5"
    assert ai.hero_state_key(0.2, 9.0, False, True, wall_behind=2.0) == "air_h0.25_rise_d_w0.3"
    for sp in ("bind", "recoil", "hurt", "umbrella", "pogo", "airdash", "wallcling"):
        assert ai.hero_state_key(1.0, 0.0, False, True, special=sp) == ai.LOCKED
    for k in (ai.hero_state_key(h, vy, g, d, 0, w) for h in (0, 0.3, 1, 2, 4, 7) for vy in (-9, 0, 9)
              for g in (True, False) for d in (True, False) for w in (None, 0.2, 2.0, 9.0)):
        assert k in ai.STATES


def test_neighbours():
    nb = ai.neighbours("air_h1.0_rest_nd")
    assert {"air_h0.25_rest_nd", "air_h2.5_rest_nd", "air_h1.0_rise_nd", "air_h1.0_fall_nd"} <= set(nb)
    assert all(k.endswith("_nd") for k in nb) and len(nb) == 9
    assert all(k.endswith("_w0.3") for k in ai.neighbours("air_h5.0_fall_d_w0.3"))
    assert ai.neighbours("ground") == ["ground"]


def test_reed_fan_and_spawn():
    cells = np.array([[6.0, -0.38], [0.5, -8.0], [3.0, 1.0], [2.0, 9.0]])
    vf, vi = ai.variants(REED, cells, np.full(4, -20.0), np.full(4, 1e6))
    j = REED.aim_err_deg.index(0.0) * len(REED.release_frames) * len(REED.drift)    # aim error 0, no drift
    el = np.degrees(np.arctan2(vf[:, j, 1], vf[:, j, 0]))
    assert el[0] == pytest.approx(0.0, abs=1e-6)
    assert el[1] == pytest.approx(-70.0) and el[3] == pytest.approx(45.0)
    assert tuple(vf[0, j, 2:4]) == pytest.approx((1.53, -0.54))
    assert 10.0 <= el[2] <= 45.0 and tuple(vf[2, j, 2:4]) == pytest.approx((1.11, 0.48))
    assert set(vi[0, :, 0]) == {24, 25}


def test_spear_fan():
    cells = np.array([[8.0, -0.63], [1.0, -9.0], [-3.0, 2.0], [-3.0, -6.0]])
    vf, vi = ai.variants(SPEAR, cells, np.full(4, -20.0), np.full(4, 1e6))
    j = SPEAR.aim_err_deg.index(0.0) * len(SPEAR.release_frames) * len(SPEAR.antic_modes)
    el = np.degrees(np.arctan2(vf[:, j, 1], vf[:, j, 0]))
    assert el[0] == pytest.approx(0.0, abs=1e-6)                 # at the hero transform + 0.25
    assert el[1] == pytest.approx(-45.0)
    assert el[2] == pytest.approx(45.0) and el[3] == pytest.approx(-45.0)   # behind: the nearer edge
    assert (vf[:, :, 2:4] == 0).all() and set(vi[0, :, 2]) == set(SPEAR.antic_modes)


def test_pin_kernel_paths():
    p = ai.hero_params(False)
    cell = (6.0, -0.38)
    still = np.zeros((120, 2))
    assert not ai.path_escapes(still, cell, -20.0, 1e6, REED, p)
    up = np.zeros((120, 2))
    up[:, 1] = np.minimum(np.arange(1, 121) * 0.3, 3.0)
    assert ai.path_escapes(up, cell, -20.0, 1e6, REED, p)
    late = np.zeros((120, 2))
    late[36:, 1] = 3.0
    assert not ai.path_escapes(late, cell, -20.0, 1e6, REED, p)
    # clearance: the horizontal pin's top (spawn y -0.54, +0.06 drift, +-0.5 deg, half thickness 0.049) is at about
    # -0.39 under the hero; a box bottom 0.05 u above it is not an escape (CLEAR 0.1 u), 0.2 u above is
    gap = np.zeros((120, 2))
    gap[:, 1] = 1.0739 + 0.04 + 0.05
    assert not ai.path_escapes(gap, cell, -20.0, 1e6, REED, p)
    gap[:, 1] = 1.0739 + 0.04 + 0.2
    assert ai.path_escapes(gap, cell, -20.0, 1e6, REED, p)


def test_spear_kernel_paths():
    p = ai.hero_params(False)
    still = np.zeros((120, 2))
    run = np.zeros((120, 2))
    run[:, 0] = np.arange(1, 121) * 8.25 / 60
    cell = (8.0, -6.0)
    floor = cell[1] - ai.HB_STAND
    assert not ai.path_escapes(still, cell, floor, 1e6, SPEAR, p)     # the explosion at her feet
    assert ai.path_escapes(run, cell, floor, 1e6, SPEAR, p)           # 1.2 s of running clears the blast
    stop = run.copy()
    stop[30:, 0] = stop[29, 0]                                        # 2 u only: inside the blast
    assert not ai.path_escapes(stop, cell, floor, 1e6, SPEAR, p)


def _table(tmp_path, gx, gy, z, name="Reed"):
    f = tmp_path / f"aim_ics_{name}.npz"
    np.savez_compressed(f, meta=np.array(json.dumps({"type": name})), grid_x=gx, grid_y=gy,
                        **{"z|measured|ground|0": z})
    return f


def test_reader_lookup_mirror_locked(tmp_path):
    z = np.zeros((len(ai.GRID_Y), len(ai.GRID_X)), np.int8)
    iy, ix = np.searchsorted(ai.GRID_Y, -2.0), np.searchsorted(ai.GRID_X, 3.0)
    z[iy, ix] = 1
    z[0, :] = -1
    f = _table(tmp_path, ai.GRID_X, ai.GRID_Y, z)
    t = ai.AimICS(f)
    gx, gy = float(ai.GRID_X[ix]), float(ai.GRID_Y[iy])
    assert t.inescapable("measured", "ground", 0, (10.0 + gx, 5.0 + gy), (10.0, 5.0))
    assert t.inescapable("measured", "ground", 0, (10.0 - gx, 5.0 + gy), (10.0, 5.0))          # mirrored fan
    assert not t.inescapable("measured", "ground", 0, (10.0 - gx, 5.0 + gy), (10.0, 5.0), side=1)  # behind
    assert not t.inescapable("measured", "ground", 0, (10.0 + gx + 0.5, 5.0 + gy), (10.0, 5.0))
    assert not t.inescapable("measured", "ground", 0, (40.0, 5.0), (10.0, 5.0))
    assert t.area("measured", "ground", 0) == pytest.approx(0.01)
    assert ai.zone("Reed", "measured", "ground", 0, path=f)[iy, ix] == 1
    zl = t.zone("measured", ai.LOCKED, 2)                                                      # locked: all
    assert (zl[1:] == 1).all() and (zl[0] == -1).all()
    assert t.inescapable("measured", ai.LOCKED, 0, (10.0 + 5.0, 5.0 - 3.0), (10.0, 5.0))


@pytest.mark.parametrize("type_name", ["Reed", "Clawmaiden"])
def test_stored_tables_cover_states(type_name):
    f = ai.FORUM / f"aim_ics_{type_name}.npz"
    if not f.exists():
        pytest.skip(f"{f.name} not built")
    t = ai.AimICS(f)
    keys = set(t.keys())
    for st in ai.STATES:
        for lat in ai.LATENCIES:
            assert ("measured", st, str(lat)) in keys
    gx, gy = ai.grid(type_name)
    z = t.zone("measured", "ground", 0)
    assert z.shape == (len(gy), len(gx)) and set(np.unique(z)) <= {-1, 0, 1}
