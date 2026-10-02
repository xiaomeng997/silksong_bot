"""Space-time hitbox templates (ssbot.knowledge.hitbox_tables): the raster is a superset of the polygon, accumulation,
npz round trip, query tolerance, conservative covers, dilation (a point test of the hurtbox centre on a dilated
template equals a box-overlap test), box distance, and the planner's batched numba query (parity with the NumPy
reference, 512 x 48 timing)."""
import math
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

from ssbot.knowledge import hitbox_tables as hb

C = hb.CELL_U
KNOWLEDGE_NPZ = Path(__file__).resolve().parents[2] / "knowledge" / "1.0.30000" / "enemies" / "BellBeast_hitboxes.npz"


def _box(x0, y0, x1, y1):
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], np.float64)


def _template(polys_by_t, frame="anchor", key="T/anchor"):
    acc = hb.TemplateAccumulator(key, frame)
    for i, (t, poly) in enumerate(polys_by_t):
        acc.add(t, poly, instance=i)
    return acc.finish()


def _cells(ix0, iy0, patch):
    ys, xs = np.nonzero(patch)
    return xs + ix0, ys + iy0


def _random_polygon(rng, n):
    """A simple (star-shaped) polygon with n vertices, slanted edges, a few u across, off-lattice."""
    c = rng.uniform(-3, 3, 2)
    ang = np.sort(rng.uniform(0, 2 * np.pi, n))
    rad = rng.uniform(0.02, 1.5, n)
    return np.column_stack([c[0] + rad * np.cos(ang), c[1] + rad * np.sin(ang)])


def _inside(poly, pts):
    cnt = poly.astype(np.float32).reshape(-1, 1, 2)
    return np.array([cv2.pointPolygonTest(cnt, (float(x), float(y)), False) >= 0 for x, y in pts])


def test_rasterize_is_a_superset_of_slanted_polygons():
    rng = np.random.default_rng(7)
    worst = 0.0
    for k in range(300):
        poly = _random_polygon(rng, int(rng.integers(3, 9)))
        ix0, iy0, patch = hb.rasterize(poly)
        marked = set(zip(*_cells(ix0, iy0, patch)))
        lo, hi = poly.min(axis=0), poly.max(axis=0)
        pts = rng.uniform(lo, hi, (400, 2))
        pts = np.vstack([pts[_inside(poly, pts)], poly,  # interior samples, the vertices, and points along edges
                         *(poly[i] + np.linspace(0, 1, 25)[:, None] * (np.roll(poly, -1, 0)[i] - poly[i])
                           for i in range(len(poly)))])
        cells = np.floor(pts / C).astype(int)
        missed = [tuple(c) for c in cells if tuple(c) not in marked]
        assert not missed, f"polygon {k}: {len(missed)} points in unmarked cells"
        xs, ys = _cells(ix0, iy0, patch)  # and the raster stays within about 2 cells of the bounding box
        worst = max(worst, lo[0] - xs.min() * C, (xs.max() + 1) * C - hi[0], lo[1] - ys.min() * C,
                    (ys.max() + 1) * C - hi[1])
    assert worst <= 2.1 * C  # 2 cells plus the fixed-point vertex rounding (0.1015 u measured)


def test_rasterize_box_covers_centres_and_stays_within_two_cells():
    x0, y0, x1, y1 = 1.0, 0.0, 2.0, 0.5
    ix0, iy0, patch = hb.rasterize(_box(x0, y0, x1, y1))
    xs, ys = _cells(ix0, iy0, patch)
    cx, cy = (xs + 0.5) * C, (ys + 0.5) * C
    assert cx.min() >= x0 - 2.01 * C and cx.max() <= x1 + 2.01 * C
    assert cy.min() >= y0 - 2.01 * C and cy.max() <= y1 + 2.01 * C
    covered = set(zip(xs.tolist(), ys.tolist()))
    for ix in range(int(x0 / C), int(x1 / C)):
        for iy in range(int(y0 / C), int(y1 / C)):
            assert (ix, iy) in covered


def test_rasterize_thin_segment_and_point():
    ix0, iy0, patch = hb.rasterize(np.array([[0.0, 0.0], [1.0, 0.0]]))
    assert patch.sum() >= 3 * 20  # 1 u of a horizontal edge collider, grown by one cell
    ix0, iy0, patch = hb.rasterize(np.array([[0.52, 0.27]]))
    xs, ys = _cells(ix0, iy0, patch)
    assert (10, 5) in set(zip(xs.tolist(), ys.tolist())) and patch.sum() == 9
    assert hb.rasterize(np.zeros((0, 2))) is None
    assert hb.rasterize(np.array([[np.nan, 1.0]])) is None


def test_anchor_frame_round_trip_and_mirror():
    p = np.array([[80.0, 4.0], [70.5, -1.0]])
    for m in (1, -1):
        q = hb.to_anchor(p, (75.0, 5.0), m)
        assert np.allclose(hb.from_anchor(q, (75.0, 5.0), m), p)
    assert np.allclose(hb.to_anchor(p, (75.0, 5.0), -1)[:, 0], [-5.0, 4.5])
    assert hb.box_to_anchor((76.0, 1.0, 77.0, 3.0), (75.0, 5.0), -1) == (-2.0, -4.0, -1.0, -2.0)


def test_accumulator_template_queries_and_npz_round_trip(tmp_path):
    # a 2 x 1 u box moving +0.2 u per bin over 10 bins
    tpl = _template([(k * hb.BIN_S, _box(0.2 * k - 1, -0.5, 0.2 * k + 1, 0.5)) for k in range(10)])
    assert tpl.nt == 10 and tpl.n_instances == 10
    assert np.allclose(tpl.active(), (0.0, 9 * hb.BIN_S))
    t = np.arange(10) * hb.BIN_S
    assert tpl.contains(t, 0.2 * np.arange(10), 0.0).all()
    assert not tpl.contains(t, 0.2 * np.arange(10) + 1.7, 0.0, tol_bins=1).any()
    assert not tpl.contains(t, 0.2 * np.arange(10), 0.8).any()
    assert not tpl.contains(5.0, 0.0, 0.0)  # outside the stored bins
    assert tpl.box_hit(0.0, 0.0, (0.5, -0.1, 0.7, 0.1))
    assert not tpl.box_hit(0.0, 0.0, (1.5, -0.1, 1.7, 0.1))  # bins 0 and 1 reach x 1.3 at most
    assert tpl.box_hit(0.0, 9 * hb.BIN_S, (2.5, -0.1, 2.6, 0.1))
    x0, y0, x1, y1 = tpl.extent()
    assert abs(x0 + 1.0) <= 2.01 * C and abs(x1 - 2.8) <= 2.01 * C and abs(y0 + 0.5) <= 2.01 * C
    assert abs(y1 - 0.5) <= 2.01 * C
    sup = tpl.dilated(r_disk=0.1, t_bins=1, key="support/T/anchor")
    path = hb.save_templates(tmp_path / "t.npz", {tpl.key: tpl, sup.key: sup},
                             {"T/boss_path": np.arange(6.0).reshape(3, 2)})
    tpls, extra = hb.load_templates(path)
    back = tpls[tpl.key]
    assert back.frame == "anchor" and back.n_instances == 10 and (back.bits == tpl.bits).all()
    assert (back.ix0, back.iy0, back.nx, back.ny, back.t_pad) == (tpl.ix0, tpl.iy0, tpl.nx, tpl.ny, 0)
    sb = tpls["support/T/anchor"]
    assert sb.t_pad == 1 and sb.pad_x == pytest.approx(0.1) and sb.t0 == pytest.approx(-hb.BIN_S)
    assert np.array_equal(extra["T/boss_path"], np.arange(6.0).reshape(3, 2))
    assert set(hb.load_templates(path, prefix=hb.SUPPORT)[0]) == {"support/T/anchor"}
    old = hb.SpaceTimeTemplate.from_arrays("old", tpl.bits, tpl.meta()[:10])  # files written before t_pad / pad_*
    assert old.t_pad == 0 and old.pad_x == 0.0


def test_queries_enforce_the_export_lag_tolerance():
    tpl = _template([(0.0, _box(0, 0, 1, 1))])
    for call in (lambda: tpl.contains(0.0, 0.5, 0.5, tol_bins=0), lambda: tpl.box_hit(0, 0, (0, 0, 1, 1), 0),
                 lambda: tpl.occupancy(0.0, 0.1, tol_bins=0), lambda: tpl.box_distance(0.0, (0, 0, 1, 1), 0)):
        with pytest.raises(ValueError):
            call()
    sup = tpl.dilated(t_bins=1)  # the +-1 bin baked in: tol 0 is allowed and equals tol 1 on the raw template
    t = np.array([-hb.BIN_S, 0.0, hb.BIN_S, 2 * hb.BIN_S])
    assert np.array_equal(sup.contains(t, 0.5, 0.5, tol_bins=0), tpl.contains(t, 0.5, 0.5, tol_bins=1))


def test_numba_query_matches_numpy_reference():
    rng = np.random.default_rng(3)
    polys = []
    for _ in range(12):
        xs, ys = np.sort(rng.uniform(-3, 3, 2)), np.sort(rng.uniform(-2, 2, 2))
        polys.append((rng.uniform(0, 0.3), _box(xs[0], ys[0], xs[1], ys[1])))
    tpl = _template(polys)
    n = 4000
    ib = rng.integers(-3, tpl.nt + 3, n)
    ix = rng.integers(-5, tpl.nx + 5, n)
    iy = rng.integers(-5, tpl.ny + 5, n)
    for tol in (0, 1, 2):
        a = hb._contains_np(tpl.bits, tpl.nx, ib, iy, ix, tol, np.zeros(n, bool))
        b = hb._contains(tpl.bits, tpl.nx, ib, iy, ix, tol, np.zeros(n, bool))
        c = hb._contains_loop(tpl.bits, tpl.nx, ib, iy, ix, tol, np.zeros(n, bool))
        assert np.array_equal(a, b) and np.array_equal(a, c)
    assert a.any() and not a.all()


def test_union_of_templates_and_occupancy_window():
    a = _template([(0.0, _box(0, 0, 1, 1))], key="A/anchor")
    b = _template([(0.5, _box(2, 0, 3, 1))], key="B/anchor")
    u = hb.union([a, b], "U/anchor")
    assert u.contains([0.0, 0.5], [0.5, 2.5], [0.5, 0.5]).all()
    assert not u.contains(0.0, 2.5, 0.5)
    occ = u.occupancy(0.4, 0.6)
    assert occ.any() and occ.sum() < u.reach().sum()


def test_mask_boxes_is_an_exact_cover():
    rng = np.random.default_rng(1)
    mask = cv2.dilate((rng.random((40, 60)) > 0.93).astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    boxes = hb.mask_boxes(mask)
    rebuilt = np.zeros_like(mask, dtype=np.int32)
    for x0, y0, x1, y1 in boxes:
        rebuilt[y0:y1, x0:x1] += 1
    assert np.array_equal(rebuilt > 0, mask) and rebuilt.max() == 1


def test_mask_polygons_are_conservative():
    rng = np.random.default_rng(2)
    for _ in range(5):
        mask = cv2.dilate((rng.random((30, 30)) > 0.96).astype(np.uint8), np.ones((2, 2), np.uint8)).astype(bool)
        polys = [p.astype(np.float32).reshape(-1, 1, 2) for p in hb.mask_polygons(mask)]
        for iy, ix in zip(*np.nonzero(mask)):
            for cx, cy in ((ix, iy), (ix + 1, iy), (ix, iy + 1), (ix + 1, iy + 1)):  # cell corners
                assert any(cv2.pointPolygonTest(p, (float(cx), float(cy)), False) >= 0 for p in polys)


def test_template_boxes_and_polygons_cover_reach():
    tpl = _template([(0.0, _box(0, 0, 1, 1)), (0.1, np.array([[3.0, 0.0], [4.0, 0.0], [3.5, 1.5]]))])
    boxes = tpl.boxes()
    area = float(((boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])).sum())
    assert abs(area - tpl.reach().sum() * C * C) < 1e-9
    polys = tpl.polygons()
    assert len(polys) == 2
    for p in polys:
        assert p.min(axis=0)[1] < 0.0  # the conservative outline lies outside the occupied cells


def _overlaps(tpl, b, box):
    """Brute force: any occupied cell of bin b intersecting the closed box."""
    iy, ix = np.nonzero(tpl.plane(b))
    x0 = (ix + tpl.ix0) * tpl.cell
    y0 = (iy + tpl.iy0) * tpl.cell
    return bool(((x0 < box[2]) & (x0 + tpl.cell > box[0]) & (y0 < box[3]) & (y0 + tpl.cell > box[1])).any())


def test_dilated_point_test_is_a_conservative_box_overlap_test():
    rng = np.random.default_rng(11)
    tpl = _template([(k * hb.BIN_S, _random_polygon(rng, 6)) for k in range(4)])
    hx, hy = hb.HERO_HALF_U
    dil = tpl.dilated(rx=hx, ry=hy, t_bins=1)
    lo = np.array(tpl.bounds[:2]) - 2.0
    hi = np.array(tpl.bounds[2:]) + 2.0
    n_true = 0
    for _ in range(3000):
        b = int(rng.integers(-1, tpl.nt + 1))
        cx, cy = rng.uniform(lo, hi)
        box = (cx - hx, cy - hy, cx + hx, cy + hy)
        truth = any(_overlaps(tpl, bb, box) for bb in (b - 1, b, b + 1))
        got = bool(dil.contains(b * hb.BIN_S, cx, cy, tol_bins=0))
        assert got or not truth, f"missed overlap at {(cx, cy)}, bin {b}"
        n_true += truth
        if got and not truth:  # false positives only when the box comes within one cell of the occupancy
            grown = (box[0] - C, box[1] - C, box[2] + C, box[3] + C)
            assert any(_overlaps(tpl, bb, grown) for bb in (b - 1, b, b + 1))
    assert n_true > 200


def test_disk_kernel_and_box_distance():
    rng = np.random.default_rng(5)
    for r in (0.03, 0.1, 0.27):
        k = hb.disk_kernel(r)
        h = k.shape[0] // 2
        for _ in range(500):  # any point within r of cell (0, 0) lies in a kernel cell
            a, d = rng.uniform(0, 2 * np.pi), rng.uniform(0, r)
            px, py = rng.uniform(0, C), rng.uniform(0, C)
            jx, jy = int(math.floor((px + d * math.cos(a)) / C)), int(math.floor((py + d * math.sin(a)) / C))
            assert k[jy + h, jx + h]
    tpl = _template([(0.0, _box(0, 0, 1, 1))])
    assert tpl.box_distance(0.0, (0.5, 0.5, 2, 2)) == 0.0
    d = tpl.box_distance(0.0, (1.5, 0.2, 2.0, 0.4))
    assert 0.5 - 2 * C - 1e-9 <= d <= 0.5  # the raster extends up to 2 cells past the box
    assert tpl.box_distance(0.0, (5, 5, 6, 6), r_max=1.0) == math.inf
    sup = tpl.dilated(r_disk=d, t_bins=1)
    assert sup.box_hit(0.0, 0.0, (1.5, 0.2, 2.0, 0.4), tol_bins=0)  # dilating by the residual covers the contact


def _planner_set():
    rng = np.random.default_rng(9)
    tpls = {}
    for j, frame in enumerate(("anchor", "world", "anchor", "world")):
        tpl = _template([(k * hb.BIN_S, _random_polygon(rng, 7) * 2) for k in range(0, 60, 3)], frame=frame,
                        key=f"F{j}/{frame}")
        tpls[f"support/F{j}/{frame}"] = tpl.dilated(r_disk=0.1, t_bins=1, key=f"support/F{j}/{frame}")
    return hb.planner_templates(tpls)


def test_support_query_matches_reference_and_meets_the_budget():
    plan = _planner_set()
    q = hb.SupportQuery(plan)
    place = [("support/F0/anchor", 0.2, (1.0, 0.5), -1), ("support/F1/world", 0.0, None, 1),
             ("support/F2/anchor", 0.35, (-0.5, 0.0), 1), ("support/F3/world", 0.1, None, 1)]
    for key, t_ref, anchor, mirror in place:
        q.place(key, t_ref, anchor, mirror)
    rng = np.random.default_rng(1)
    n, t_steps = 512, 48
    x = rng.uniform(-8, 8, (n, t_steps))
    y = rng.uniform(-6, 6, (n, t_steps))
    tk = np.arange(t_steps) * hb.BIN_S
    got = q.query(x, y, tk)
    ref = hb._query_ref([plan[k] for k, *_ in place], [(i, t, a, m) for i, (_, t, a, m) in enumerate(place)], tk, x, y)
    assert np.array_equal(got, ref) and got.any() and not got.all()
    times = []
    for _ in range(300):
        t0 = time.perf_counter()
        q.query(x, y, tk)
        times.append(time.perf_counter() - t0)
    p99 = float(np.quantile(times, 0.99))
    print(f"SupportQuery 512 x 48, 4 placements: p50 {np.median(times) * 1e3:.3f} ms, p99 {p99 * 1e3:.3f} ms")
    assert p99 < 3e-3  # DESIGN §3.5.4 budget for the whole tick; the query is a small part of it
    with pytest.raises(ValueError):
        hb.SupportQuery({"raw": _template([(0.0, _box(0, 0, 1, 1))])})
    with pytest.raises(ValueError, match="hurtbox"):  # support without the hurtbox dilation: a centre-only test
        hb.SupportQuery({"support/x": _template([(0.0, _box(0, 0, 1, 1))]).dilated(r_disk=0.1, t_bins=1)})
    with pytest.raises(ValueError):
        q.place("support/F1/world", 0.0, anchor=(0.0, 0.0))


def test_static_template_holds_at_every_time(tmp_path):
    """An ambient hazard's template is static: one time-invariant bin, kept through dilation, union, the npz round
    trip and the planner query, at any template time."""
    acc = hb.TemplateAccumulator("S/world", "world", static=True)
    acc.add(5.0, _box(0, 0, 1, 1))
    acc.add(-3.0, _box(2, 0, 3, 1))
    t = acc.finish()
    assert t.static and t.nt == 1 and t.active() == (-math.inf, math.inf)
    assert t.contains([-100.0, 0.0, 1e4], 0.5, 0.5).all() and t.contains(7.0, 2.5, 0.5)
    sup = t.dilated(r_disk=0.1, t_bins=1, key="support/S/world")
    assert sup.static and sup.nt == 1 and sup.t_pad == 1
    path = hb.save_templates(tmp_path / "s.npz", {"support/S/world": sup})
    back = hb.load_templates(path)[0]["support/S/world"]
    assert back.static and np.array_equal(back.bits, sup.bits)
    u = hb.union([t, t], "U/world")
    assert u.static and u.nt == 1
    plan = hb.planner_templates({"support/S/world": back})
    q = hb.SupportQuery(plan)
    q.place("support/S/world", 1e3)
    x = np.array([[0.5] * 4, [5.0] * 4])
    y = np.array([[1.9] * 4, [0.5] * 4])   # the hurtbox (1.04 u half-height) reaches the box from 1.9 u
    tk = np.array([-1.0, 0.0, 0.5, 30.0])
    got = q.query(x, y, tk)
    assert got[0].all() and not got[1].any()
    assert np.array_equal(got, hb._query_ref([plan["support/S/world"]], [(0, 1e3, None, 1)], tk, x, y))


def _timed(q, x, y, tk, n=200) -> tuple[float, float]:
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        q.query(x, y, tk)
        times.append(time.perf_counter() - t0)
    return float(np.median(times)), float(np.quantile(times, 0.99))


def test_support_query_budget_on_the_committed_bell_beast_templates():
    """The planner's tick on the committed Bell Beast support (family templates + hero hurtbox): 512 x 48 hero
    collider centres against 16 placements (all four families' world-frame support, each started 0.9-1.95 s ago, so
    the queried times fall in their active windows), checked against the NumPy reference and timed in two regimes:
    candidates mostly flagged (floor to mid-air, ~90 %) and mostly clear (one placement whose bins all hold geometry
    and candidates inside its grid that it does not flag: every candidate pays the full test, the planner's regime
    when it searches for safe moves)."""
    sup, _ = hb.load_templates(KNOWLEDGE_NPZ, prefix=hb.SUPPORT)
    plan = hb.planner_templates({k: v for k, v in sup.items() if k.count("/") == 2})
    q = hb.SupportQuery(plan)
    keys = [f"support/{f}/world_all" for f in ("BB_CHARGE", "BB_LEAP", "BB_BURST", "BB_RAGE")]
    place = [(keys[j % 4], 0.9 + 0.35 * (j // 4)) for j in range(16)]
    for key, t_ref in place:
        q.place(key, t_ref)
    rng = np.random.default_rng(0)
    x, y = rng.uniform(70, 100, (512, 48)), rng.uniform(0, 10, (512, 48))  # the arena, floor to mid-air
    tk = np.arange(48) / 60.0
    got = q.query(x, y, tk)
    assert 0.5 < got.mean() < 1.0
    ref = hb._query_ref([plan[k] for k, _ in place], [(i, t, None, 1) for i, (_, t) in enumerate(place)], tk,
                        x[:64], y[:64])
    assert np.array_equal(got[:64], ref)
    p50, p99 = _timed(q, x, y, tk)
    print(f"Bell Beast support, 512 x 48 x 16 placements, {got.mean():.0%} flagged: p50 {p50 * 1e3:.3f} ms, "
          f"p99 {p99 * 1e3:.3f} ms")
    assert p99 < 3e-3
    # mostly clear: candidates inside the Rage world_all grid (bells and boss), at heights it does not reach then
    rage = plan["support/BB_RAGE/world_all"]
    x0, y0, x1, y1 = rage.bounds
    q.clear()
    q.place("support/BB_RAGE/world_all", 3.0)
    xs, ys = rng.uniform(x0, x1, (512, 48)), rng.uniform(y0, y1, (512, 48))
    clear = ~q.query(xs, ys, tk)
    xs, ys = np.where(clear, xs, x0 + 0.01), np.where(clear, ys, y0 + 0.01)   # flagged ones moved to an empty corner
    one = q.query(xs, ys, tk).mean()
    q.clear()
    for j in range(16):
        q.place("support/BB_RAGE/world_all", 3.0 + 0.01 * j)
    hit = q.query(xs, ys, tk).mean()
    p50, p99 = _timed(q, xs, ys, tk)
    print(f"Bell Beast Rage support, 512 x 48 x 16 placements, {hit:.0%} flagged: p50 {p50 * 1e3:.3f} ms, "
          f"p99 {p99 * 1e3:.3f} ms ({p50 / 16 * 1e3:.3f} ms per placement)")
    assert one < 0.05 and hit < 0.3
    assert p99 < 3e-3
