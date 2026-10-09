"""SSBOT_FORUM_RCLIP (task "support reach", forum.md §29.11): each enemy's own support clipped to its real reach
(ssbot.combat.reach_table, multi_forecast MultiForecast._clip_*). Synthetic Reed of tests/test_multi_forecast.py, a
synthetic reach table: off is bit-identical, on is a subset that keeps everything inside the reach box and nothing
outside it (fine, window and bounding-box placements, the idle tube), a hit-reaction forecast and the vision view
are not clipped, the table lookup falls back to the family and the type."""
import numpy as np

from ssbot.combat import multi_forecast as mfm
from ssbot.combat.multi_forecast import MultiForecaster
from ssbot.combat.reach_table import CLIP_BANDS, NT, ClipTable, ReachClip
from ssbot.core.worldstate import ORACLE, VISION_EQUIVALENT

from tests.test_multi_forecast import BIN, REED, _run, _script_stab, _tables

K = 40


def _box(u0, u1, v0, v1, n=500):
    """[NT + 1, 2, K + 1, 4] boxes and [NT + 1, 2, K + 1] rows: the same box in every time bin, part and k."""
    B = np.zeros((NT + 1, 2, K + 1, 4))
    B[...] = (u0, u1, v0, v1)
    return B, np.full((NT + 1, 2, K + 1), n, np.int64)


def _table(boxes: dict, fam_of: dict) -> ClipTable:
    return ClipTable({k: v[0] for k, v in boxes.items()}, {k: v[1] for k, v in boxes.items()}, fam_of, K)


def _clip(half, u1=1.5):
    """A reach table: in every state the Reed's colliders stay within 0.5 u behind and u1 forward of its
    transform, 1 u below and above; r 0."""
    st = {(REED, s): _box(-0.5, u1, -1.0, 1.0) for s in ("Alert", "Stab Pos", "Stab 1", "Stab Recover")}
    tab = _table(st, {(REED, "Alert"): "RE_IDLE", (REED, "Stab Pos"): "RE_STAB", (REED, "Stab 1"): "RE_STAB",
                      (REED, "Stab Recover"): "RE_STAB"})
    rc = ReachClip(tab, {(REED, "*", NT, p, b): 0.0 for p in (0, 1) for b in CLIP_BANDS}, half)
    rc.skip = frozenset()
    return rc


def _grid():
    xs = np.arange(14.0, 28.0, 0.25)
    ys = np.arange(3.0, 8.0, 0.25)
    X, Y = np.meshgrid(xs, ys)
    return X.reshape(-1), Y.reshape(-1)


def _occ(f, tk):
    X, Y = _grid()
    T = len(tk)
    return f.occupied(np.repeat(X[:, None], T, 1), np.repeat(Y[:, None], T, 1), tk), X, Y


def test_clip_off_is_identical_and_on_is_the_support_inside_the_reach(monkeypatch):
    tk = np.arange(0, 31) * BIN
    script = _script_stab()
    a = MultiForecaster(_tables(), ORACLE, waves=False)
    _run(a, script[:17])                       # f 16: Stab 1 entered at its anchor (20.3, 5), facing +x
    f0 = a.forecast(0.8)
    assert f0.clip == {}
    o0, X, Y = _occ(f0, tk)
    rc = _clip(a.half)
    monkeypatch.setattr(mfm, "reach_clip", lambda half: rc)
    b = MultiForecaster(_tables(), ORACLE, waves=False)
    b.reach = True
    _run(b, script[:17])
    f1 = b.forecast(0.8)
    assert set(f1.clip) == {7}
    o1, _, _ = _occ(f1, tk)
    assert not (o1 & ~o0).any()                # a subset
    tr = b.trackers[7]
    hx, hy = b.half
    inside = ((X >= tr.pos[0] - 0.5 - hx) & (X <= tr.pos[0] + 1.5 + hx) & (Y >= tr.pos[1] - 1.0 - hy)
              & (Y <= tr.pos[1] + 1.0 + hy))
    Xr, Yr = np.repeat(X[:, None], len(tk), 1), np.repeat(Y[:, None], len(tk), 1)
    tube = f1._box_occ(Xr, Yr, tk, kinds=("collider",))   # the reaction-lag collider tube is not clipped
    assert np.array_equal(o1 & ~tube, o0 & inside[:, None] & ~tube)   # the support inside the reach box
    assert (o0 & ~inside[:, None] & ~tube).any()          # the stab's blade (1 .. 3 u forward) was cut
    # the per-enemy query and the committed part are clipped the same way
    assert np.array_equal(f1.occupied_only(Xr, Yr, tk, {7}), o1)
    assert not (f1.committed().occupied(Xr, Yr, tk) & ~inside[:, None] & ~tube).any()


def test_clip_skips_reactions_the_vision_view_and_falls_back(monkeypatch):
    rc = _clip((0.25, 1.04))
    monkeypatch.setattr(mfm, "reach_clip", lambda half: rc)
    script = _script_stab()
    b = MultiForecaster(_tables(), ORACLE, waves=False)
    b.reach = True
    _run(b, script[:12])                       # in Stab Pos
    assert b.forecast(0.8).clip
    r = b.forecast_reaction(7, "Alert", b.t + 0.05)
    assert r is not None and r.clip == {}
    v = MultiForecaster(_tables(), VISION_EQUIVALENT, waves=False)
    v.reach = True
    assert v.forecast(0.8).clip == {}
    # a time bin without its own rows takes the state's (every bin), a state without rows its family's, then the type's
    b1 = _box(-0.5, 9.0, -1, 1)
    b1[0][7] = (-0.5, 4.0, -1, 1)                         # time bin 7 alone: 4 u
    b1[1][2] = 10                                         # time bin 2: too few rows
    tab = _table({(REED, "Stab 1"): b1, (REED, "Alert"): _box(-0.5, 1.0, -1, 1, n=10)},
                 {(REED, "Stab 1"): "RE_STAB", (REED, "Stab Pos"): "RE_STAB", (REED, "Alert"): "RE_IDLE"})
    assert tab.boxes(REED, "Stab 1", 7, 0)[5, 1] == 4.0
    assert tab.boxes(REED, "Stab 1", 2, 0)[5, 1] == 9.0
    assert tab.boxes(REED, "Stab Pos", 0, 0)[5, 1] == 9.0         # the family's
    assert tab.boxes(REED, "Alert", 0, 1)[5, 1] == 9.0            # 10 rows < CLIP_MIN_ROWS: the type's
    # the world box: mirrored by the facing, shifted by the sighting's age, past the table no clip
    w = ReachClip(tab, {}, (0.25, 1.0))
    w.skip = frozenset()
    a = w.world(REED, "Stab 1", 0.05, 0, (10.0, 5.0), -1, 2)
    assert np.allclose(a[0], (10.0 - 9.0 - 0.25, 5.0 - 2.0, 10.0 + 0.5 + 0.25, 5.0 + 2.0))
    assert np.allclose(w.world(REED, "Stab 1", 0.35, 0, (10.0, 5.0), 1, 0)[5], (9.25, 3.0, 14.25, 7.0))
    assert np.isinf(a[-1]).all() and np.isinf(a[-2]).all() and np.isfinite(a[-3]).all()


def test_tracker_remembers_the_last_hit():
    from ssbot.combat.enemy_tracker import EnemyTracker
    from tests.test_multi_forecast import _tables as tabs
    b = MultiForecaster(tabs(), ORACLE, waves=False)
    _run(b, _script_stab()[:22])                  # hit at f 20
    assert abs(b.trackers[7].t_hit - 20 * BIN) < 1e-9
    assert EnemyTracker.__dataclass_fields__["t_hit"].default == -np.inf
