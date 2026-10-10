"""SSBOT_FORUM_BODYCLIP (task precision push S4 (b)): the idle body tube is also cut by the body's own reach table
(reach_table BODY_FILE) where the reach clip is; off it is not. The synthetic Reed of tests/test_multi_forecast.py idling
in Alert, a wide synthetic reach table and a narrow body table."""
import numpy as np

from ssbot.combat import multi_forecast as mfm
from ssbot.combat import reach_table
from ssbot.combat.multi_forecast import MultiForecaster
from ssbot.combat.reach_table import CLIP_BANDS, NT, ReachClip
from ssbot.core.worldstate import ORACLE

from tests.test_multi_forecast import BIN, REED, _run, _script_stab, _tables
from tests.test_reach_clip import _box, _grid, _table


def _rc(half, u0, u1, v0, v1):
    st = {(REED, s): _box(u0, u1, v0, v1) for s in ("Alert", "Stab Pos", "Stab 1", "Stab Recover")}
    tab = _table(st, {(REED, "Alert"): "RE_IDLE", (REED, "Stab Pos"): "RE_STAB", (REED, "Stab 1"): "RE_STAB",
                      (REED, "Stab Recover"): "RE_STAB"})
    rc = ReachClip(tab, {(REED, "*", NT, p, b): 0.0 for p in (0, 1) for b in CLIP_BANDS}, half)
    rc.skip = frozenset()
    return rc


def _idle(monkeypatch, on: bool):
    monkeypatch.setattr(reach_table, "R_FLOOR", 0.0)
    half = MultiForecaster(_tables(), ORACLE, waves=False).half
    wide, narrow = _rc(half, -20.0, 20.0, -20.0, 20.0), _rc(half, -0.6, 0.6, -1.2, 1.2)
    monkeypatch.setattr(mfm, "reach_clip", lambda h: wide)
    monkeypatch.setattr(mfm, "body_clip", lambda h: narrow)
    b = MultiForecaster(_tables(), ORACLE, waves=False)
    b.reach = True
    b.bodyclip = on
    _run(b, _script_stab()[:6])                # f 5: idle in Alert at (20, 5)
    f = b.forecast(0.8)
    tk = np.arange(0, 31) * BIN
    X, Y = _grid()
    T = len(tk)
    Xr, Yr = np.repeat(X[:, None], T, 1), np.repeat(Y[:, None], T, 1)
    return f, f._box_occ(Xr, Yr, tk, kinds=("idle",)), X, Y, b


def test_bodyclip_cuts_the_idle_tube_to_the_body_reach(monkeypatch):
    f0, off, X, Y, _ = _idle(monkeypatch, False)
    assert f0.body_clip == {}
    f1, on, _, _, b = _idle(monkeypatch, True)
    assert set(f1.body_clip) == {7}
    assert off.any() and not (on & ~off).any()            # a subset
    tr = b.trackers[7]
    hx, hy = b.half
    inside = ((X >= tr.pos[0] - 0.6 - hx - 1e-9) & (X <= tr.pos[0] + 0.6 + hx + 1e-9)
              & (Y >= tr.pos[1] - 1.2 - hy - 1e-9) & (Y <= tr.pos[1] + 1.2 + hy + 1e-9))
    assert np.array_equal(on, off & inside[:, None])
    assert (off & ~inside[:, None]).any()                  # the tube grew past the body's reach
    assert f1.committed().body_clip.keys() == f1.body_clip.keys()
