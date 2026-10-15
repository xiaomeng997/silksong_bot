"""Task 1v1 SG3: the one-step lookahead (ssbot.combat.map_lookahead) on SG2's dense values, the banded values and the
contour store; SG2's sim calls it (ssbot.tools.sg2_sim). A reduced map (as in test_special_map) keeps it fast; the
contour layers are built on demand from the dense pass (forum.md 57)."""
import numpy as np
import pytest

from ssbot.combat import map_lookahead as ml
from ssbot.combat import pogo_slam as ps
from ssbot.combat import score_contours as sc
from ssbot.combat import special_map as sm
from ssbot.combat.hero_macros import HeroMacros
from ssbot.combat.move_data import load_cl_slam
from ssbot.knowledge import kinematics as kin

STEP = 0.05


@pytest.fixture(scope="module")
def built():
    from ssbot.train.forum_planner_policy import CREST_PARAMS
    params = kin.HeroParams.load(CREST_PARAMS["Wanderer"])
    terrain = kin.Terrain2D.from_boxes([(0.0, ps.FLOOR_Y - 5.0, 80.0, ps.FLOOR_Y)])
    hm = HeroMacros(params, terrain, x_world=40.0)
    cfg = sm.MapConfig(x_lo=-7.0, x_hi=9.0, holds=(4, 8, 16), variants="t1", tail=40)
    geo = sm.Geometry(load_cl_slam(), hm, cfg)
    pm = sm.MapBuilder(geo).build(0, keep_full=True)
    return geo, pm, ml.TubeIndex.from_geometry(geo)


class LazyLayers(dict):
    """The tube layers of a ContourSource, contoured on first use from the dense pass (as score_contours_build)."""

    def __init__(self, pm, ti, tol):
        super().__init__()
        self.pm, self.ti, self.tol = pm, ti, tol

    def get(self, name, default=None):
        if name not in self:
            kind, s = name.split("/")
            s = int(s)
            S = self.pm.S[:, s, :].astype(np.float32)
            vr = self.ti.valid_rows(self.pm.p, s)
            if kind == "S":
                B = sc.to_bands(S, STEP)
            else:
                sv = self.pm.SV[:, s, :, int(kind[-1])].astype(np.float32)
                B = (sc.to_bands(sv, STEP) if kind.startswith("SV") else
                     np.where(np.isfinite(sv) & (sv >= S - ml.PRESS_EPS), 0, -1).astype(np.int16))
            B = sc.fill_rows(B, vr)
            self[name] = sc.ContourLayer.from_bands(B, STEP, tol=0 if kind.startswith("P") else self.tol) \
                if B.max() >= 0 else None
        return dict.get(self, name, default)


def contour_source(pm, ti, tol):
    cs = sc.ContourSet(ti.K, ti.NX, STEP)
    src = ml.ContourSource(cs, ti, pm.p)
    src.L = LazyLayers(pm, ti, tol)
    return src


def test_tube_index(built):
    geo, pm, ti = built
    assert ti.NS == geo.NS and ti.jump_h == [4.0, 8.0, 16.0]
    d = ml.TubeIndex.from_dict(ti.to_dict())
    assert d.s0 == ti.s0 and d.slice_of({"kind": "bounce", "yc": 4.3}, 5) == ti.slice_of({"kind": "bounce", "yc": 4.3}, 5)
    # valid rows: exactly where the dense pass has states (an invalid slice row is -inf in S everywhere)
    for s in (ti.s0_of[16.0] + 30, ti.s0[ti.bounce_t[20]] + 40):
        vr = ti.valid_rows(pm.p, s)
        assert np.isneginf(pm.S[~vr, s, :].astype(np.float32)).all()
        assert all(ti.valid(pm.p, k, s) == vr[k] for k in range(ti.K))


def test_sources_agree_on_the_lattice(built):
    geo, pm, ti = built
    dsrc, bsrc = ml.DenseSource(pm, ti), ml.BandedSource(pm, ti, STEP)
    csrc = contour_source(pm, ti, tol=0)
    rng = np.random.default_rng(3)
    for _ in range(400):
        k = int(rng.integers(0, ti.K))
        s = int(rng.choice([0, ti.s0_of[4.0] + int(rng.integers(0, 20)), ti.s0[ti.bounce_t[21]] + int(rng.integers(0, 40))]))
        x = float(rng.uniform(-7.0, 9.0))
        v = dsrc.S(k, s, x)
        assert bsrc.S(k, s, x) == ml.band_value(v, STEP)
        assert csrc.S(k, s, x) == bsrc.S(k, s, x)                 # tol 0: exact bands
        for d in (-1, 0, 1):
            assert csrc.press(k, s, x, d) == dsrc.press(k, s, x, d)
            assert csrc.SV(k, s, x, d) == bsrc.SV(k, s, x, d)


def test_sim_decisions(built):
    """SG2's sim with the dense source and two shadows: the tol-0 contours decide exactly as the banded values; the
    +-1 contours differ only on options whose values are within three bands (a contour value lies within -2..+1
    bands of the true value: the floor to the band edge plus the +-1 band of the simplification)."""
    from ssbot.tools.sg2_sim import Sim
    geo, pm, ti = built
    sim = Sim(geo, pm, np.random.default_rng(5))
    sim.src = ml.BandedSource(pm, ti, STEP)
    sim.shadows = [{"name": nm, "src": contour_source(pm, ti, tol), "n": 0, "diff": 0, "gaps": [], "ex": [],
                    "max_ex": 5} for nm, tol in (("c0", 0), ("c1", 1))]
    tl = geo.variants[0]
    for x0 in (-3.0, 3.0, 4.5):
        sim.run(tl, "ground", 30, x0, {"kind": "ground", "k": 30}, 0.02)
    sim.run(tl, "bounce", 0, 0.0, {"kind": "bounce", "yc": 4.6, "k": -6, "q0": (0 + 6) % 6}, 0.02)
    c0, c1 = sim.shadows
    assert c0["n"] > 100 and c0["diff"] == 0
    for kind, gap in c1["gaps"]:                                   # a jump may cross the never-jump threshold
        assert kind in ("value", "not_offered_here", "not_offered_there")
        assert gap is None or gap < 3 * STEP + 1e-6


def test_decide_world_and_readiness(built):
    geo, pm, ti = built
    src = ml.DenseSource(pm, ti)
    # a Clapper facing left (-1) at world x 50: a hero at world 46 stands 4 u in front of it (map x +4)
    hero = ml.HeroState(x=46.0, key=0)
    en = ml.EnemyPose(x0=50.0, facing=-1, k=20)
    r = ml.decide_world(src, hero, en)
    v, act, _ = ml.decide(src, 20, {"kind": "ground", "k": 20}, 4.0, 0, -100, 0.02)
    assert r["value"] == pytest.approx(v)
    exp = (act[0], act[1], -act[2]) if act[0] == "jump" else (act[0], -act[1])
    assert r["action"] == exp
    assert ml.readiness(src, 4.0) == src.S(0, 0, 4.0)
    assert np.isneginf(ml.readiness(src, 0.0))                     # inside the body
    # no feasible option: retreat away from the enemy on the ground
    v, act, _ = ml.decide(src, 60, {"kind": "ground", "k": 60}, 0.0, 0, -100, 0.02)
    if not np.isfinite(v):
        assert act == ("dir", 1)


def ea_source(pm, ti, n, scope):
    """An equal-area contour source (SG3b) on the reduced map, every layer contoured exactly (tol 0)."""
    S = pm.S.astype(np.float32)
    VR = np.stack([ti.valid_rows(pm.p, s) for s in range(ti.NS)], 1)
    meta = {"banding": {"mode": "equal_area", "bands": n, "scope": scope}}
    cs = sc.ContourSet(ti.K, ti.NX, 0.0, meta)
    if scope == "frame":
        E = sc.pad_edges([sc.equal_area_edges(S[k][VR[k]], n) for k in range(ti.K)], n - 1)
        cs.arrays[f"edges_{pm.p}"] = E

        def edges_of(nm):
            return E
    else:
        led = {}

        def edges_of(nm):
            if nm not in led:
                kind, s = nm.split("/")
                s = int(s)
                a = S[:, s, :] if kind == "S" else pm.SV[:, s, :, int(kind[2:])].astype(np.float32)
                led[nm] = sc.equal_area_edges(a[VR[:, s]], n)
            return led[nm]
        names = [f"{k}/{s}" for s in range(ti.NS) for k in ("S", "SV0", "SV1", "SV2")]
        cs.meta["names"] = names
        cs.arrays["edges"] = sc.pad_edges([edges_of(nm) for nm in names], n - 1)

    class EALayers(dict):
        def get(self, name, default=None):
            if name not in self:
                kind, s = name.split("/")
                s = int(s)
                Ss = pm.S[:, s, :].astype(np.float32)
                if kind == "S":
                    B = sc.bands_from_edges(Ss, edges_of(name))
                else:
                    sv = pm.SV[:, s, :, int(kind[-1])].astype(np.float32)
                    B = (sc.bands_from_edges(sv, edges_of(name)) if kind.startswith("SV") else
                         np.where(np.isfinite(sv) & (sv >= Ss - ml.PRESS_EPS), 0, -1).astype(np.int16))
                B = sc.fill_rows(B, VR[:, s])
                self[name] = sc.ContourLayer.from_bands(B, 0.0, tol=0) if B.max() >= 0 else None
            return dict.get(self, name, default)
    src = ml.ContourSource(cs, ti, pm.p)
    src.L = EALayers()
    return src, edges_of


@pytest.mark.parametrize("scope", ["frame", "layer"])
def test_equal_area_source_exact(built, scope):
    """SG3b: on every sampled lattice state the equal-area contour value is the lower edge of the dense value's band
    (feasibility exact), the press flags are exact, and a jump decided on it has a reachable strike on the dense map."""
    geo, pm, ti = built
    dsrc = ml.DenseSource(pm, ti)
    src, edges_of = ea_source(pm, ti, 4, scope)
    rng = np.random.default_rng(4)
    for _ in range(300):
        k = int(rng.integers(0, ti.K))
        s = int(rng.choice([0, ti.s0_of[8.0] + int(rng.integers(0, 20)), ti.s0[ti.bounce_t[21]] + int(rng.integers(0, 40))]))
        x = ti.x_lo + ti.step * int(rng.integers(0, ti.NX))
        v = dsrc.S(k, s, x) if ti.valid(pm.p, k, s) else -np.inf
        e = edges_of(f"S/{s}")
        e = e[k] if e.ndim == 2 else e
        want = -np.inf if not np.isfinite(v) else float(sc.edge_values(e)[np.searchsorted(e, v, side="right")])
        assert src.S(k, s, x) == want
        for d in (-1, 0, 1):
            assert src.press(k, s, x, d) == (dsrc.press(k, s, x, d) and ti.valid(pm.p, k, s))
    for x0 in (-3.0, 3.0, 4.5):
        for k0 in (0, 20):
            v, act, _ = ml.decide(src, k0, {"kind": "ground", "k": k0}, x0, 0, -100, 0.02)
            if act[0] == "jump":
                assert v > ti.wc and dsrc.S(k0, ti.s0_of[act[1]], x0) > ti.wc
