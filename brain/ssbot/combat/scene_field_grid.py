"""Continuous soft scene values on coarse event-time grids.

One instance is one focus/capability/conditional-world layer. Builders supply
absolute game-time knots and static spatial region ids; queries never simulate
motion, choose keys, or certify path safety. No runtime owner imports this yet.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Hashable

import numpy as np


def _axis(values):
    a = np.array(values, dtype=float, copy=True)
    if a.ndim != 1 or not len(a) or not np.isfinite(a).all():
        raise ValueError('axes must be nonempty finite vectors')
    if np.any(np.diff(a) <= 0):
        raise ValueError('axes must increase strictly')
    a.setflags(write=False)
    return a


def _bracket(axis, q):
    if len(axis) == 1:
        z = np.zeros(len(q), dtype=np.intp)
        return z, z, np.zeros(len(q))
    lo = np.clip(np.searchsorted(axis, q, side='right') - 1, 0, len(axis) - 2)
    hi = lo + 1
    w = np.clip((q - axis[lo]) / (axis[hi] - axis[lo]), 0., 1.)
    return lo, hi, w


@dataclass(frozen=True, eq=False)
class SceneFieldGrid:
    times: np.ndarray
    xs: np.ndarray
    ys: np.ndarray
    values: np.ndarray
    known: np.ndarray
    regions: np.ndarray

    def __post_init__(self):
        for name in ('times', 'xs', 'ys'):
            object.__setattr__(self, name, _axis(getattr(self, name)))
        shape = (len(self.times), len(self.ys), len(self.xs))
        values = np.array(self.values, dtype=float, copy=True)
        known = np.array(self.known, dtype=bool, copy=True)
        regions = np.array(self.regions, copy=True)
        if values.shape != shape or known.shape != shape:
            raise ValueError('values/known must have shape [time, y, x]')
        if regions.shape != shape[1:] or regions.dtype.kind not in 'iu':
            raise ValueError('regions must be integer [y, x], positive inside a region')
        if not np.isfinite(values[known]).all():
            raise ValueError('known values must be finite')
        for name, a in [('values', values), ('known', known), ('regions', regions)]:
            a.setflags(write=False)
            object.__setattr__(self, name, a)

    def query(self, points):
        """Batch [x,y,absolute_game_time] -> (soft_values, known).

        Unknown values are NaN, distinct from a neutral score; the caller owns
        its unknown policy. Only positive-weight corners are needed, so an
        exact knot can be known even when the adjacent interval is uncovered.
        """
        p = np.asarray(points, dtype=float)
        if p.ndim != 2 or p.shape[1] != 3:
            raise ValueError('points must have shape [N,3]')
        n = len(p)
        valid = np.isfinite(p).all(axis=1)
        q = np.where(np.isfinite(p), p, 0.)
        bounds = [(self.xs, 0), (self.ys, 1), (self.times, 2)]
        for axis, col in bounds:
            valid &= (q[:, col] >= axis[0]) & (q[:, col] <= axis[-1])
        ix = _bracket(self.xs, q[:, 0])
        iy = _bracket(self.ys, q[:, 1])
        it = _bracket(self.times, q[:, 2])
        total = np.zeros(n)
        region = np.zeros(n, dtype=self.regions.dtype)
        for bt in (0, 1):
            for by in (0, 1):
                for bx in (0, 1):
                    w = (it[2] if bt else 1-it[2]) * (iy[2] if by else 1-iy[2]) * (ix[2] if bx else 1-ix[2])
                    used = w > 0
                    t, y, x = it[bt], iy[by], ix[bx]
                    r = self.regions[y, x]
                    valid &= ~used | (self.known[t, y, x] & (r > 0) & ((region == 0) | (region == r)))
                    region = np.where(used & (region == 0), r, region)
                    v = np.where(used & self.known[t, y, x], self.values[t, y, x], 0.)
                    total += w * v
        total[~valid] = np.nan
        return total, valid


class SceneFieldCache:
    """Low-frequency builds; queries retain the original absolute time knots.

    key includes scene/move/aim-lock and layer identity supplied by the adapter.
    refresh_s is caller configuration, not a fixed prediction horizon. An event
    key change or clock reset rebuilds immediately; routine ticks reuse the grid.
    """
    def __init__(self, refresh_s: float):
        if not np.isfinite(refresh_s) or refresh_s <= 0:
            raise ValueError('refresh_s must be finite and positive')
        self.refresh_s = float(refresh_s)
        self.clear()

    def clear(self):
        self._key = None
        self._at = None
        self._field = None

    def get(self, key: Hashable, now_s: float, build: Callable[[], SceneFieldGrid]):
        hash(key)
        now_s = float(now_s)
        if not np.isfinite(now_s):
            raise ValueError('game time must be finite')
        expired = self._field is None or self._key != key
        if self._at is not None:
            expired |= now_s < self._at or now_s >= self._at + self.refresh_s
            expired |= now_s > self._field.times[-1]
        if expired:
            field = build()
            if not isinstance(field, SceneFieldGrid):
                raise TypeError('builder must return a SceneFieldGrid')
            if not field.times[0] <= now_s <= field.times[-1]:
                raise ValueError('new field must cover the current game time')
            self._field, self._key, self._at = field, key, now_s
        return self._field
