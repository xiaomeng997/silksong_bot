"""tools.forum_ics: the person's two thought experiments (forum.md §26) on synthetic templates: an instant AoE over
the whole screen makes every start inescapable; the same AoE after a long wind-up leaves only the body."""
import numpy as np
import pytest

from ssbot.knowledge import hitbox_tables as hb
from ssbot.tools import forum_ics as F

K = 200


@pytest.fixture(scope="module")
def lib():
    p = F.hero_params()
    d, names, ok = F.library(p, "free", K, F.LAT_F)
    return d, ok


def _template(t_on: float, t_off: float, body_until: float, half: float = 12.0) -> hb.SpaceTimeTemplate:
    """Anchor-frame template on a 0.05 u grid: a box of +-half u (x) x [-3, 9] u (y) occupied from t_on to t_off,
    and a 1 x 2 u body at the anchor until body_until (s)."""
    cell = hb.CELL_U
    nx, ny = int(2 * half / cell), int(12.0 / cell)
    ix0, iy0 = -nx // 2, int(-3.0 / cell)
    nt = int(round(max(t_off, body_until) * 60)) + 3
    planes = np.zeros((nt, ny, nx), bool)
    xs = (np.arange(nx) + ix0 + 0.5) * cell
    ys = (np.arange(ny) + iy0 + 0.5) * cell
    body = (np.abs(xs)[None, :] <= 0.5) & (ys[:, None] >= -1.0) & (ys[:, None] <= 1.0)
    for b in range(nt):
        t = -1.0 / 60.0 + b / 60.0
        if t_on <= t <= t_off:
            planes[b] = True
        if t <= body_until:
            planes[b] |= body
    bits = np.packbits(planes, axis=2)
    return hb.SpaceTimeTemplate(key="test", frame="anchor", ix0=ix0, iy0=iy0, nx=nx, ny=ny, t0=-1.0 / 60.0,
                                bits=bits, t_pad=1)


def test_instant_aoe_everything_inescapable(lib):
    d, ok = lib
    t = _template(0.0, 0.3, 0.3)
    xs = np.arange(-10.0, 10.01, 1.0)
    z, _ = F.zone_ub(t, xs, np.zeros(len(xs)), d, ok)
    assert z.all()


def test_long_windup_leaves_the_body(lib):
    d, ok = lib
    t = _template(2.5, 2.7, 2.7)             # the AoE (+-12 u) after 2.5 s: the hero runs 20 u in it
    xs = np.arange(-10.0, 10.01, 0.5)
    z, _ = F.zone_ub(t, xs, np.zeros(len(xs)), d, ok)
    assert z[np.abs(xs) < 0.25].all()        # standing in the body
    assert not z[np.abs(xs) >= 1.0].any()    # anywhere else: run out before the AoE


def test_lower_bound_inside_upper(lib):
    t = _template(0.6, 0.8, 0.8, half=6.0)
    zl, (gx0, gy0) = F.zone_lb(t, F.hero_params(), 0.0, F.LAT_F)
    d, ok = lib
    # every floor start the erosion calls inescapable, the library cannot escape either
    yy, xx = np.nonzero(zl)
    floor = np.abs((yy + gy0 + 0.5) * t.cell) < t.cell
    xs = (xx[floor] + gx0 + 0.5) * t.cell
    if len(xs):
        z, _ = F.zone_ub(t, xs, np.zeros(len(xs)), d, ok)
        assert z.all()


def test_aimed_strike_far_is_escapable(lib):
    d, ok = lib
    xs = np.array([6.0, 10.0])
    z = F.pin_zone(xs, np.zeros(len(xs)), d[:, :K], ok)
    assert not z.any()
