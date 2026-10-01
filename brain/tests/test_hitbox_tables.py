"""Space-time hitbox templates (ssbot.knowledge.hitbox_tables): rasterisation bounds, accumulation, npz round trip,
point / box queries (NumPy fallback against the numba loop kernel run as plain Python), conservative covers."""
import cv2
import numpy as np

from ssbot.knowledge import hitbox_tables as hb

C = hb.CELL_U


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


def test_rasterize_box_covers_centres_and_stays_within_one_cell():
    x0, y0, x1, y1 = 1.0, 0.0, 2.0, 0.5
    ix0, iy0, patch = hb.rasterize(_box(x0, y0, x1, y1))
    xs, ys = _cells(ix0, iy0, patch)
    cx, cy = (xs + 0.5) * C, (ys + 0.5) * C
    # within one cell of the box
    assert cx.min() >= x0 - 1.01 * C and cx.max() <= x1 + 1.01 * C
    assert cy.min() >= y0 - 1.01 * C and cy.max() <= y1 + 1.01 * C
    # every cell whose centre is inside is covered
    covered = set(zip(xs.tolist(), ys.tolist()))
    for ix in range(int(x0 / C), int(x1 / C)):
        for iy in range(int(y0 / C), int(y1 / C)):
            assert (ix, iy) in covered


def test_rasterize_thin_segment_and_point():
    ix0, iy0, patch = hb.rasterize(np.array([[0.0, 0.0], [1.0, 0.0]]))
    assert patch.sum() >= 19  # 1 u of a horizontal edge collider = 20 cells
    ix0, iy0, patch = hb.rasterize(np.array([[0.52, 0.27]]))
    xs, ys = _cells(ix0, iy0, patch)
    assert list(zip(xs, ys)) == [(10, 5)]
    assert hb.rasterize(np.zeros((0, 2))) is None
    assert hb.rasterize(np.array([[np.nan, 1.0]])) is None


def test_anchor_frame_round_trip_and_mirror():
    p = np.array([[80.0, 4.0], [70.5, -1.0]])
    for m in (1, -1):
        q = hb.to_anchor(p, (75.0, 5.0), m)
        assert np.allclose(hb.from_anchor(q, (75.0, 5.0), m), p)
    assert np.allclose(hb.to_anchor(p, (75.0, 5.0), -1)[:, 0], [-5.0, 4.5])


def test_accumulator_template_queries_and_npz_round_trip(tmp_path):
    # a 2 x 1 u box moving +0.2 u per bin over 10 bins
    tpl = _template([(k * hb.BIN_S, _box(0.2 * k - 1, -0.5, 0.2 * k + 1, 0.5)) for k in range(10)])
    assert tpl.nt == 10 and tpl.n_instances == 10
    assert np.allclose(tpl.active(), (0.0, 9 * hb.BIN_S))
    t = np.arange(10) * hb.BIN_S
    assert tpl.contains(t, 0.2 * np.arange(10), 0.0).all()
    assert not tpl.contains(t, 0.2 * np.arange(10) + 1.5, 0.0, tol_bins=1).any()
    assert not tpl.contains(t, 0.2 * np.arange(10), 0.8).any()
    assert not tpl.contains(5.0, 0.0, 0.0)  # outside the stored bins
    assert tpl.box_hit(0.0, 0.0, (0.5, -0.1, 0.7, 0.1), tol_bins=0)
    assert not tpl.box_hit(0.0, 0.0, (1.2, -0.1, 1.4, 0.1), tol_bins=0)
    assert tpl.box_hit(0.0, 9 * hb.BIN_S, (2.5, -0.1, 2.6, 0.1))
    x0, y0, x1, y1 = tpl.extent()
    assert abs(x0 + 1.0) <= 1.01 * C and abs(x1 - 2.8) <= 1.01 * C and abs(y0 + 0.5) <= 1.01 * C
    path = hb.save_templates(tmp_path / "t.npz", {tpl.key: tpl}, {"T/boss_path": np.arange(6.0).reshape(3, 2)})
    tpls, extra = hb.load_templates(path)
    back = tpls[tpl.key]
    assert back.frame == "anchor" and back.n_instances == 10 and (back.bits == tpl.bits).all()
    assert (back.ix0, back.iy0, back.nx, back.ny) == (tpl.ix0, tpl.iy0, tpl.nx, tpl.ny)
    assert np.array_equal(extra["T/boss_path"], np.arange(6.0).reshape(3, 2))


def test_numpy_query_matches_loop_kernel():
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
        b = hb._contains_loop(tpl.bits, tpl.nx, ib, iy, ix, tol, np.zeros(n, bool))
        assert np.array_equal(a, b)
    assert a.any() and not a.all()


def test_union_of_templates_and_occupancy_window():
    a = _template([(0.0, _box(0, 0, 1, 1))], key="A/anchor")
    b = _template([(0.5, _box(2, 0, 3, 1))], key="B/anchor")
    u = hb.union([a, b], "U/anchor")
    assert u.contains([0.0, 0.5], [0.5, 2.5], [0.5, 0.5], tol_bins=0).all()
    assert not u.contains(0.0, 2.5, 0.5, tol_bins=0)
    occ = u.occupancy(0.4, 0.6, tol_bins=0)
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
