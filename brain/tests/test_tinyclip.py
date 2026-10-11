"""SSBOT_FORUM_TINYCLIP (task precision push S4 (c)): a Tiny group row (bb gcl >= 0, it stands for every Tiny of its
cluster) is clipped by the union of its members' reach clips; a cluster with a member without a clip stays
unclipped; off, group rows are never clipped (as before). The synthetic Reed of tests/test_reach_clip.py; its bounding
box rows are turned into one cluster's group rows by hand."""
import numpy as np

from ssbot.combat import multi_forecast as mfm
from ssbot.combat import reach_table
from ssbot.combat.multi_forecast import CLUSTER0, NOCLIP, MultiForecaster
from ssbot.core.worldstate import ORACLE

from tests.test_multi_forecast import BIN, _run, _script_stab, _tables
from tests.test_reach_clip import _clip, _grid


def _forecast(monkeypatch):
    monkeypatch.setattr(reach_table, "R_FLOOR", 0.0)
    rc = _clip(MultiForecaster(_tables(), ORACLE, waves=False).half)
    monkeypatch.setattr(mfm, "reach_clip", lambda half: rc)
    b = MultiForecaster(_tables(), ORACLE, waves=False)
    b.reach = True
    _run(b, _script_stab()[:17])
    f = b.forecast(0.8)
    assert set(f.clip) == {7} and len(f.bb["owner"])
    return f


def _bb(f, tk, clip=None, gcl=None, clusters=None, on=False):
    """The bounding-box occupancy of f on the test grid with its clip / gcl / clusters / switch replaced."""
    f.__dict__.pop("_crow", None)
    if clip is not None:
        f.clip = clip
    n = len(f.bb["owner"])
    f.bb["gcl"] = np.full(n, -1 if gcl is None else gcl, np.int64)
    f.clusters = clusters or []
    f.tinyclip = on
    X, Y = _grid()
    T = len(tk)
    return f._bbox_occ(np.repeat(X[:, None], T, 1), np.repeat(Y[:, None], T, 1), tk)


def test_group_rows_are_clipped_by_the_union_of_their_members(monkeypatch):
    f = _forecast(monkeypatch)
    tk = np.arange(0, 31) * BIN
    c7 = f.clip[7].copy()
    c8 = c7.copy()
    c8[:, [0, 2]] += 3.0                              # a second Tiny 3 u further along x
    full = _bb(f, tk, clip={})                        # nothing clipped
    a = _bb(f, tk, clip={7: c7})                      # the rows clipped by member 7's reach
    b = _bb(f, tk, clip={7: c8})                      # ... by member 8's
    assert (full & ~a).any() and (full & ~b).any() and (b & ~a).any()
    # off: a group row is never clipped
    off = _bb(f, tk, clip={7: c7, 8: c8}, gcl=0, clusters=[frozenset({7, 8})])
    assert np.array_equal(off, full)
    on = _bb(f, tk, clip={7: c7, 8: c8}, gcl=0, clusters=[frozenset({7, 8})], on=True)
    assert np.array_equal(on, a | b)
    assert (f._clip_rows("bb") == CLUSTER0).all()
    assert f._clip_members(CLUSTER0) == (7, 8) and f._clip_members(-7) == (-7,)


def test_a_member_without_a_clip_leaves_its_cluster_unclipped(monkeypatch):
    f = _forecast(monkeypatch)
    tk = np.arange(0, 31) * BIN
    c7 = f.clip[7].copy()
    full = _bb(f, tk, clip={})
    on = _bb(f, tk, clip={7: c7}, gcl=0, clusters=[frozenset({7, 9})], on=True)
    assert np.array_equal(on, full)
    assert (f._clip_rows("bb") == NOCLIP).all()


def test_clip_xy_keeps_points_inside_any_member(monkeypatch):
    f = _forecast(monkeypatch)
    tk = np.arange(0, 3) * BIN
    c7 = np.tile([[10.0, 0.0, 11.0, 1.0]], (len(f.clip[7]), 1))
    f.clip = {7: c7, 8: c7 + [5.0, 0.0, 5.0, 0.0]}
    f.clusters = [frozenset({7, 8})]
    x = np.repeat(np.array([10.5, 15.5, 13.0])[:, None], len(tk), 1)
    y = np.full_like(x, 0.5)
    xx, yy = f._clip_xy(x, y, tk, CLUSTER0)
    assert np.isfinite(xx[0]).all() and np.isfinite(xx[1]).all() and np.isnan(xx[2]).all()
