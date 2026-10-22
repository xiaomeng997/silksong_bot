"""Map v2 stage M1: the hero envelope (ssbot.map2.envelope / env_jit) against the hero model's rollouts."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest

from ssbot.knowledge import kinematics as km
from ssbot.map2 import envelope as env
from ssbot.map2 import env_jit as ej
from ssbot.tools import m1_envelope as me


@pytest.fixture(scope="module")
def eng():
    return env.Engine()


def _contained(fw, xy, T):
    fidx = me.frame_index(fw)
    bad = []
    for i in range(xy.shape[0]):
        for t in range(1, T + 1):
            if me.point_dist(fw, fidx, t, xy[i, t, 0], xy[i, t, 1]) > 0:
                bad.append((i, t))
                break
    return bad


def test_exact_pass_contains_random_rollouts(eng):
    """Every key sequence's centre lies in the exact (no event limit) envelope at every frame (free space, A1 and a
    rising start)."""
    rng = np.random.default_rng(3)
    T = 8
    for S in (km.initial_state(eng.params, 0.0, 20.0, ground=False),
              km.initial_state(eng.params, 0.0, 20.0, vy=9.0, ground=False)):
        st = eng.start_state(S)
        fw = eng.forward(st, T)
        assert fw.stats[:, 3].sum() == 0            # the lanes never diverge
        masks = me.random_masks(rng, 300, T, claw=True, start_prev=0)
        xy, _ = eng.rollouts(np.repeat(S[None], 300, 0), np.repeat(st.cu[None], 300, 0), masks)
        assert _contained(fw, xy, T) == []


def test_event_limited_pass_on_the_floor(eng):
    """The segment family (2 events) from standing on the floor holds the rollouts with at most 2 key changes."""
    rng = np.random.default_rng(5)
    T = 16
    terr = env.floor_terrain()
    S = km.initial_state(eng.params, 0.0, env.FLOOR_BB + eng.params.foot, ground=True)
    st = eng.start_state(S)
    fw = eng.forward(st, T, terrain=terr, max_events=2)
    masks = me.random_masks_ev(rng, 300, T, 2, claw=True)
    xy, _ = eng.rollouts(np.repeat(S[None], 300, 0), np.repeat(st.cu[None], 300, 0), masks, terrain=terr)
    assert _contained(fw, xy, T) == []
    # the event limit bounds the count: far below the unlimited pass
    full = eng.forward(st, 8, terrain=terr)
    lim = eng.forward(st, 8, terrain=terr, max_events=2)
    assert lim.count(8) < full.count(8)


def test_danger_cuts_rows_and_keeps_safe_rollouts(eng):
    rng = np.random.default_rng(9)
    T = 14
    S = km.initial_state(eng.params, 0.0, 20.0, ground=False)
    st = eng.start_state(S)
    dz = me.random_danger(rng, S, T, eng.hh, n_boxes=5)
    fw = eng.forward(st, T, danger=dz, max_events=2)
    for t in range(1, T + 1):
        g, x0, x1, y0, y1 = fw.frame_rows(t)
        for bx0, by0, bx1, by1 in dz[t]:
            assert not np.any((by0 <= y0) & (y0 <= by1) & (x0 < bx1 - 1e-9) & (x1 > bx0 + 1e-9))
    masks = me.random_masks_ev(rng, 300, T, 2, claw=True)
    xy, _ = eng.rollouts(np.repeat(S[None], 300, 0), np.repeat(st.cu[None], 300, 0), masks)
    fidx = me.frame_index(fw)
    for i in range(300):
        for t in range(1, T + 1):
            if me.in_danger(dz[t], xy[i, t, 0], xy[i, t, 1]):
                break
            assert me.point_dist(fw, fidx, t, xy[i, t, 0], xy[i, t, 1]) == 0.0


def test_witness_reaches_interval_ends(eng):
    rng = np.random.default_rng(11)
    S = km.initial_state(eng.params, 0.0, 20.0, ground=False)
    fw = eng.forward(eng.start_state(S), 20, max_events=2)
    misses = []
    for _ in range(12):
        t = int(rng.integers(8, 21))
        g = int(rng.integers(fw.cl_off[t], fw.cl_off[t + 1]))
        a, b = fw.intervals(g)[0]
        for x in (a, b):
            w = fw.witness(t, float(x), float(fw.cl_y[g]))
            assert w is not None
            assert abs(w["miss_y"]) < 1e-9
            misses.append(abs(w["miss_x"]))
    assert max(misses) <= 0.17


def test_raster_is_conservative():
    rows = np.array([[1.02, 1.02, -0.3, 0.7], [1.04, 1.13, 2.0, 2.5], [0.9, 0.9, 0.5, 1.5]])
    r = env.raster(rows, 0.0, 0.0)
    for y0, y1, x0, x1 in rows:
        for y in np.linspace(y0, y1, 5):
            j = np.floor(y / env.QROW)
            s = r[r[:, 0] == j]
            for x in np.linspace(x0, x1, 5):
                assert np.any((s[:, 1] <= x) & (x <= s[:, 2]))


def test_contours_cover_the_raster():
    rows = np.array([[0.0, 0.2, 0.0, 1.0], [0.2, 0.4, 0.5, 2.0], [1.0, 1.1, -3.0, -2.0]])
    r = env.raster(rows, 0.0, 0.0)
    polys = env.contours(r)
    assert len(polys) == 2

    def inside(p, x, y):
        n, c = len(p), False
        for i in range(n):
            (x1, y1), (x2, y2) = p[i], p[(i + 1) % n]
            if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                c = not c
        return c

    for b, a, c in r:
        y = (b + 0.5) * env.QROW
        for x in np.linspace(a + 1e-6, c - 1e-6, 4):
            assert any(inside(p, x, y) for p in polys)


def test_vkey_canonical(eng):
    S = km.initial_state(eng.params, 0.0, 20.0, ground=False)
    cu = np.array([-1.0, 0, 0, 0, 0, 0, 0])
    a, b = np.empty(ej.NKEY), np.empty(ej.NKEY)
    x = S.copy()
    x[km.JBUF] = -0.0067        # a spent buffer in normal control: not a key
    x[km.DASH_CD] = -0.003      # a finished cooldown: 0
    ej.vkey(S, cu, eng.P, False, a)
    ej.vkey(x, cu, eng.P, False, b)
    assert np.array_equal(a, b)
    x[km.VY] = -0.0
    ej.vkey(x, cu, eng.P, False, b)
    assert ej.khash(a) == ej.khash(b)


def test_no_live_module_imports_map2():
    """M1 is offline: the bot's code paths do not import ssbot.map2 (so the decisions stay bit-identical)."""
    root = Path(env.__file__).resolve().parents[1]
    pat = re.compile(r"^\s*(from|import)\s+ssbot\.map2|ssbot\.map2\s+import", re.M)
    offenders = []
    for p in root.rglob("*.py"):
        rel = p.relative_to(root).as_posix()
        if rel.startswith("map2/") or rel in ("tools/m1_envelope.py", "tools/m2_validate.py", "tools/zone_overlay.py",
                                               "tools/m3_search.py", "tools/m3_accept.py"):
            continue
        if pat.search(p.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(rel)
    assert offenders == []
