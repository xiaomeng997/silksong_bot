"""Task 1v1 SG3: score contours (ssbot.combat.score_contours) - property tests on synthetic band layers with peaks,
holes, cliffs and rows with no node: every lattice point equals the bands (feasibility exact; inner bands exact with
tol 0, within +-1 with tol 1), rings closed and oriented, the tree kept by the simplification, siblings disjoint, no
vertex on a lattice point, the encoding round trip and the contourc layout (forum.md 57)."""
import numpy as np
import pytest

from ssbot.combat import score_contours as sc


def field(seed: int, nk: int = 60, nx: int = 70) -> np.ndarray:
    rng = np.random.default_rng(seed)
    k, x = np.mgrid[0:nk, 0:nx].astype(float)
    s = np.zeros((nk, nx))
    for _ in range(5):
        ck, cx, w, h = rng.uniform(0, nk), rng.uniform(0, nx), rng.uniform(3, 12), rng.uniform(0.5, 3.0)
        s += h * np.exp(-((k - ck) ** 2 + (x - cx) ** 2) / (2 * w * w))
    s += 0.02 * (nk - k)                                         # a ramp along k (the discount)
    s[(k - nk / 2) ** 2 / 40 + (x - nx / 3) ** 2 / 15 < 1] = -np.inf   # a hole (danger)
    s[:, :3] = -np.inf                                           # a wall
    s[rng.random((nk, nx)) < 0.01] = -np.inf                     # isolated infeasible points
    s[10:12, 40:50] = 4.0                                        # a cliff next to danger
    s[12, 40:50] = -np.inf
    return s


@pytest.mark.parametrize("seed", [0, 1, 2])
@pytest.mark.parametrize("tol", [0, 1])
def test_lattice_equality_and_structure(seed, tol):
    step = 0.1
    B = sc.to_bands(field(seed), step)
    for simplify in (False, True):
        L = sc.ContourLayer.from_bands(B, step, simplify=simplify, tol=tol)
        D = L.dense()
        assert ((D >= 0) == (B >= 0)).all()                      # feasibility exact
        diff = D.astype(int) - B
        assert np.abs(diff).max() <= (tol if simplify else 0)
        if simplify:
            assert L.stats["points"] < L.stats["points_raw"]
            assert L.stats["tree_kept"]
        assert L.stats["orientation_flips"] == 0
        # point queries (compiled and numpy) agree with the raster
        rng = np.random.default_rng(seed)
        for k, x in zip(rng.integers(0, B.shape[0], 150), rng.integers(0, B.shape[1], 150)):
            assert L.query(int(k), int(x)) == L.band(int(k), int(x)) == D[k, x]
        assert L.query(-1, 0) == -1 and L.query(0, B.shape[1]) == -1
        # rings: closed polygons of >= 3 points, no vertex on a lattice point
        for r in L.rings:
            assert len(r) >= 3
            assert not ((r[:, 0] % sc.COORD == 0) & (r[:, 1] % sc.COORD == 0)).any()
        # orientation: roots are outer rings (CCW, > 0); a ring and its same-level parent have opposite signs
        a = L.areas2()
        for i, p in enumerate(L.parent):
            if p < 0:
                assert a[i] > 0
            elif L.level[p] == L.level[i]:
                assert np.sign(a[p]) != np.sign(a[i])
            elif L.level[p] < L.level[i]:
                assert a[p] > 0 and a[i] > 0                     # a higher level's outer ring inside an outer ring
            else:
                assert a[p] < 0 and a[i] < 0                     # a deeper pit's hole inside a higher level's hole
            # the parent contains every vertex of the child (no crossing)
            if p >= 0:
                assert (sc.winding(L.rings[p], L.rings[i][:, 0], L.rings[i][:, 1]) != 0).all()
        # siblings disjoint: no sibling contains another's vertex
        for p in np.unique(L.parent):
            sib = np.flatnonzero(L.parent == p)
            for i in sib:
                for j in sib:
                    if i != j:
                        assert (sc.winding(L.rings[i], L.rings[j][:, 0], L.rings[j][:, 1]) == 0).all()


def test_net_area_and_levels():
    B = sc.to_bands(field(3), 0.1)
    L = sc.ContourLayer.from_bands(B, 0.1, simplify=False)
    na = L.net_area()
    # the net area of a level's region (holes subtracted) tracks the number of lattice points with band >= m
    for m in (0, 5, 10):
        n = int((B >= m).sum())
        assert abs(na[m] - n) <= 0.5 * n + 30
    # higher levels have smaller regions
    lv = sorted(na)
    assert all(na[lv[i]] >= na[lv[i + 1]] - 1e-6 for i in range(len(lv) - 1))


def test_encoding_round_trip_and_contourc(tmp_path):
    B1 = sc.to_bands(field(4), 0.05)
    B2 = (field(5) > 1.0).astype(int) - 1                          # a binary layer
    L1 = sc.ContourLayer.from_bands(B1, 0.05, tol=1)
    L2 = sc.ContourLayer.from_bands(B2.astype(np.int16), 0.05, tol=0)
    cs = sc.ContourSet(*B1.shape, 0.05, {"what": "test"})
    cs.add("a", L1)
    cs.add("b/c", L2)
    cs.save(tmp_path / "c.npz")
    cs2 = sc.ContourSet.load(tmp_path / "c.npz")
    for nm, L in (("a", L1), ("b/c", L2)):
        R = cs2.layers[nm]
        assert len(R.rings) == len(L.rings)
        assert all((r1 == r2).all() for r1, r2 in zip(L.rings, R.rings))
        assert (R.parent == L.parent).all() and (R.level == L.level).all()
        assert (R.dense() == L.dense()).all()
    assert (cs2.layers["b/c"].dense() == B2).all()
    C = L1.contourc()
    assert C.shape[0] == 2 and C.shape[1] == len(L1.rings) + sum(len(r) for r in L1.rings)
    col, lv = 0, []
    while col < C.shape[1]:
        lv.append(C[0, col])
        col += 1 + C[1, col]
    assert col == C.shape[1] and lv == sorted(lv)                  # header columns, sorted by level


def test_fill_rows_and_errors():
    a = np.arange(12).reshape(4, 3)
    f = sc.fill_rows(a, np.array([False, True, False, True]))
    assert (f[0] == a[1]).all() and (f[2] == a[1]).all() and (f[3] == a[3]).all()
    B = np.full((5, 5), -1, np.int16)
    B[2, 2] = 150                                                  # a jump of 151 bands on one edge
    with pytest.raises(ValueError):
        sc.ContourLayer.from_bands(B, 0.01)
    E = sc.ContourLayer.from_bands(np.full((4, 4), -1, np.int16), 0.1)
    assert E.top == -1 and not E.rings and E.query(1, 1) == -1


# ---- SG3b: equal-area bands (forum.md 58) ----
def _brute_sse(v, n):
    """The least sum of squared band areas over every partition of the distinct values into n contiguous bands."""
    import itertools
    uv, cnt = np.unique(v, return_counts=True)
    cm = np.concatenate([[0], np.cumsum(cnt)])
    best = np.inf
    for cuts in itertools.combinations(range(1, len(uv)), min(n, len(uv)) - 1):
        pos = [0, *cm[list(cuts)], cm[-1]]
        best = min(best, float(sum((b - a) ** 2 for a, b in zip(pos[:-1], pos[1:]))))
    return best


@pytest.mark.parametrize("n", [3, 4, 5])
def test_equal_area_edges(n):
    rng = np.random.default_rng(n)
    # no ties: the plain quantiles, every band within 1 / (64 n) of the total (the cut grid)
    v = rng.random(20000)
    e = sc.equal_area_edges(v, n)
    sh = sc.band_shares(sc.bands_from_edges(v[None], e), n)
    assert len(e) == n - 1 and np.abs(sh - 1 / n).max() <= 1 / (64 * n) + 1e-9
    # an atom (the clearance-only plateau): one band of its own, never split
    w = np.concatenate([rng.random(1000) * 0.3, np.full(7900, 0.3), 0.5 + rng.random(1100)])
    B = sc.bands_from_edges(w[None], sc.equal_area_edges(w, n))[0]
    assert ((B == B[1000]) == (w == 0.3)).all()
    # ties: the most equal partition (least sum of squared areas), checked by brute force; a value never split
    for seed in range(5):
        r = np.random.default_rng(100 + seed)
        t = r.choice(np.round(r.random(9), 2), size=300, p=r.dirichlet(np.ones(9)))
        e = sc.equal_area_edges(t, n)
        Bt = sc.bands_from_edges(t[None], e)[0]
        for u in np.unique(t):
            assert len(np.unique(Bt[t == u])) == 1
        c = np.bincount(Bt, minlength=n).astype(float)
        assert float((c ** 2).sum()) == pytest.approx(_brute_sse(t, n))
    # fewer distinct values than bands: fewer edges; one value: none
    assert len(sc.equal_area_edges(np.array([1.0, 1.0, 2.0]), n)) == 1
    assert len(sc.equal_area_edges(np.full(10, 0.3), n)) == 0
    assert len(sc.equal_area_edges(np.array([np.nan, -np.inf]), n)) == 0


def test_bands_from_edges_per_frame():
    s = field(6)
    E = sc.pad_edges([sc.equal_area_edges(row, 4) for row in s], 3)
    B = sc.bands_from_edges(s, E)
    for k in range(s.shape[0]):
        e = E[k][np.isfinite(E[k])]
        assert (B[k] == sc.bands_from_edges(s[k][None], e)[0]).all()
    assert ((B >= 0) == np.isfinite(s)).all()
    V = sc.edge_values(E)
    assert V.shape == (s.shape[0], 4) and (V[:, 0] == 0).all()


@pytest.mark.parametrize("scope", ["layer", "frame"])
@pytest.mark.parametrize("n", [3, 5])
def test_equal_area_layers_exact_after_encoding(tmp_path, scope, n):
    """The feasibility ring exact on every lattice point after simplification and after the integer encoding (file
    round trip); inner rings exact with tol 0 and within +-1 with tol 1; nesting, orientation, tree."""
    cs = sc.ContourSet(60, 70, 0.0, {"banding": {"mode": "equal_area", "bands": n, "scope": scope}})
    want = {}
    for seed in (0, 1, 2):
        s = field(seed)
        if scope == "layer":
            E = sc.equal_area_edges(s, n)
        else:
            E = sc.pad_edges([sc.equal_area_edges(row, n) for row in s], n - 1)
        B = sc.bands_from_edges(s, E)
        for tol in (0, 1):
            L = sc.ContourLayer.from_bands(B, 0.0, tol=tol)
            assert L.stats["tree_kept"] and L.stats["orientation_flips"] == 0
            a = L.areas2()
            for i, p in enumerate(L.parent):
                if p < 0:
                    assert a[i] > 0                                   # roots are outer rings
                else:
                    assert (sc.winding(L.rings[p], L.rings[i][:, 0], L.rings[i][:, 1]) != 0).all()
                    if L.level[p] == L.level[i]:
                        assert np.sign(a[p]) != np.sign(a[i])
            for p in np.unique(L.parent):                            # siblings disjoint
                sib = np.flatnonzero(L.parent == p)
                for i in sib:
                    for j in sib:
                        if i != j:
                            assert (sc.winding(L.rings[i], L.rings[j][:, 0], L.rings[j][:, 1]) == 0).all()
            cs.add(f"{seed}/{tol}", L)
            want[f"{seed}/{tol}"] = (B, tol)
    cs.arrays["edges"] = np.arange(6, dtype=np.float32).reshape(2, 3)
    cs.save(tmp_path / "ea.npz")
    cs2 = sc.ContourSet.load(tmp_path / "ea.npz")
    assert cs2.meta["banding"]["scope"] == scope and (cs2.arrays["edges"] == cs.arrays["edges"]).all()
    for nm, (B, tol) in want.items():
        D = cs2.layers[nm].dense()
        assert ((D >= 0) == (B >= 0)).all()                       # feasibility exact on every lattice point
        assert np.abs(D.astype(int) - B).max() <= tol
