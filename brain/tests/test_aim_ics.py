"""Aimed-attack inescapable zones (ssbot.tools.aim_ics): state keys, the Reed's fan and spawn rule, the pin-escape
kernel on hand-made paths, the reader's lookup and mirroring, and the stored table's coverage."""
import json

import numpy as np
import pytest

from ssbot.tools import aim_ics as ai


def test_state_keys():
    assert ai.hero_state_key(0.0, 0.0, True, True) == "ground"
    assert ai.hero_state_key(0.0, 0.0, True, False) == "ground_nd"
    assert ai.hero_state_key(0.0, 0.0, True, False, dashing=-1) == "dash_toward"
    assert ai.hero_state_key(0.0, 0.0, True, True, wall_behind=0.5) == "ground_w0.3"
    assert ai.hero_state_key(0.8, -2.0, False, False) == "air_h1.0_rest_nd"
    assert ai.hero_state_key(0.2, 9.0, False, True) == "air_h0.25_rise_d"
    assert ai.hero_state_key(6.0, -12.0, False, True) == "air_h5.0_fall_d"
    assert ai.hero_state_key(2.0, 0.0, False, True, wall_behind=2.0) == "air_h2.5_rest_d_w1.5"
    assert ai.hero_state_key(3.0, -1.0, False, False, wall=True) == "air_h2.5_rest_nd_w0.3"
    for k in (ai.hero_state_key(h, vy, g, d, 0, w) for h in (0, 0.3, 1, 2, 4, 7) for vy in (-9, 0, 9)
              for g in (False,) for d in (True, False) for w in (None, 0.2, 2.0, 9.0)):
        assert k in ai.STATES


def test_fan_clamp_and_spawn():
    att = ai.FAMILIES["measured"]
    cells = np.array([[6.0, -0.38], [0.5, -8.0], [3.0, 1.0], [2.0, 9.0]])
    ux, uy, px, py, rel, ss = ai.pin_variants(att, cells, np.full(4, -20.0), np.full(4, 1e6))
    j = att.aim_err_deg.index(0.0) * len(att.release_frames) * len(att.drift)     # aim error 0, first release, no drift
    el = np.degrees(np.arctan2(uy[:, j], ux[:, j]))
    assert el[0] == pytest.approx(0.0, abs=1e-6)                 # straight at the hero transform
    assert el[1] == pytest.approx(-70.0)                         # below the fan: the lower edge
    assert el[3] == pytest.approx(45.0)                          # above the fan: the upper edge
    assert (px[0, j], py[0, j]) == pytest.approx((1.53, -0.54))  # thrown low
    assert 10.0 <= el[2] <= 45.0 and (px[2, j], py[2, j]) == pytest.approx((1.11, 0.48))   # thrown from Throw Point U
    assert set(rel[0]) == {24, 25}
    assert (ux[:, j] > 0).all()                                  # always toward the hero's side


def test_pin_floor_stop():
    att = ai.FAMILIES["measured"]
    cells = np.array([[1.0, -6.0]])                              # steep down throw: sticks into the floor
    ux, uy, px, py, rel, ss = ai.pin_variants(att, cells, np.array([-3.0]), np.array([1e6]))
    tip_y = py[0] + uy[0] * (ss[0] + att.half_len - att.back)
    assert np.allclose(tip_y, -3.0)


def test_kernel_still_vs_escape():
    p = ai.hero_params(False)
    att = ai.FAMILIES["measured"]
    still = np.zeros((42, 2))
    assert not ai.path_escapes(still, (6.0, -0.38), "air_h2.5_rest_d", att, p)     # in the line: hit
    up = np.zeros((42, 2))
    up[:, 1] = np.minimum(np.arange(1, 43) * 0.3, 3.0)                              # 3 u up by frame 10
    assert ai.path_escapes(up, (6.0, -0.38), "air_h2.5_rest_d", att, p)
    late = np.zeros((42, 2))
    late[36:, 1] = 3.0                                                              # leaves after the pin passed
    assert not ai.path_escapes(late, (6.0, -0.38), "air_h2.5_rest_d", att, p)
    assert ai.path_escapes(still, (2.0, 9.0), "air_h5.0_rest_d", att, p)           # far above the fan: line misses


def test_reader_lookup_and_mirror(tmp_path):
    z = np.zeros((len(ai.GRID_Y), len(ai.GRID_X)), np.int8)
    iy, ix = np.searchsorted(ai.GRID_Y, -2.0), np.searchsorted(ai.GRID_X, 3.0)
    z[iy, ix] = 1
    meta = {"type": "Reed"}
    f = tmp_path / "aim_ics_Reed.npz"
    np.savez_compressed(f, meta=np.array(json.dumps(meta)), grid_x=ai.GRID_X, grid_y=ai.GRID_Y,
                        **{"z|measured|ground|0": z})
    t = ai.AimICS(f)
    gx, gy = float(ai.GRID_X[ix]), float(ai.GRID_Y[iy])
    assert t.inescapable("measured", "ground", 0, (10.0 + gx, 5.0 + gy), (10.0, 5.0))
    assert t.inescapable("measured", "ground", 0, (10.0 - gx, 5.0 + gy), (10.0, 5.0))   # the other fan: mirrored
    assert not t.inescapable("measured", "ground", 0, (10.0 + gx + 0.5, 5.0 + gy), (10.0, 5.0))
    assert not t.inescapable("measured", "ground", 0, (40.0, 5.0), (10.0, 5.0))          # off the grid
    assert t.area("measured", "ground", 0) == pytest.approx(0.01)
    assert ai.zone("Reed", "measured", "ground", 0, path=f)[iy, ix] == 1


@pytest.mark.skipif(not ai.DEFAULT_NPZ.exists(), reason="aim_ics_Reed.npz not built")
def test_stored_table_covers_states():
    t = ai.AimICS()
    keys = set(t.keys())
    for fam in ai.FAMILIES:
        for st in ai.STATES:
            for lat in ai.LATENCIES:
                assert (fam, st, str(lat)) in keys
    z = t.zone("measured", "ground", 0)
    assert z.shape == (len(ai.GRID_Y), len(ai.GRID_X))
    assert set(np.unique(z)) <= {-1, 0, 1}
