"""Task 1v1 SG2: the backward score map (ssbot.combat.special_map), its closed-loop policy (ssbot.tools.sg2_sim) and
the overlay layer (zone_overlay.special_map_now / draw_smap). A reduced map (T1's nine variants, three holds, a
narrower x range, one phase) keeps the tests fast; the full build is ssbot.tools.special_map_build (forum.md 56)."""
import numpy as np
import pytest

from ssbot.combat import pogo_slam as ps
from ssbot.combat import special_map as sm
from ssbot.combat.hero_macros import HeroMacros
from ssbot.combat.move_data import load_cl_slam
from ssbot.knowledge import kinematics as kin


@pytest.fixture(scope="module")
def built():
    from ssbot.train.forum_planner_policy import CREST_PARAMS
    params = kin.HeroParams.load(CREST_PARAMS["Wanderer"])
    terrain = kin.Terrain2D.from_boxes([(0.0, ps.FLOOR_Y - 5.0, 80.0, ps.FLOOR_Y)])
    hm = HeroMacros(params, terrain, x_world=40.0)
    cfg = sm.MapConfig(x_lo=-7.0, x_hi=9.0, holds=(4, 8, 16), variants="t1", tail=40)
    geo = sm.Geometry(load_cl_slam(), hm, cfg)
    pm = sm.MapBuilder(geo).build(0, keep_full=True)
    return geo, pm


def test_geometry(built):
    geo, _ = built
    yb0 = int(geo.ybin(0.0))
    assert geo.D[30][yb0, geo.x_index(0.0)]                     # standing inside the Clapper's body
    assert not geo.D[30][yb0, geo.x_index(-6.0)]                # far behind it
    assert geo.CL[30][yb0, geo.x_index(-6.0)] > 0.5
    # the hammer (Slam Collider 2) reaches ~12 u in front at k 57; at k 30 the front at 5 u is clear
    assert geo.D[58][yb0, geo.x_index(8.0)] and not geo.D[30][yb0, geo.x_index(5.0)]
    # a variant's own damage set never exceeds the union
    for k in (30, 50, 55, 60):
        for ds in geo.DS[k]:
            assert not (ds & ~geo.D[k]).any()


def test_contact_masks(built):
    geo, _ = built
    # a slash whose rendered pos is 1.5 u above the root box top (antic: 3.90 u above the floor) touches it near x 0
    r = int(geo.rbin(3.90 + 1.5))
    b = geo.VB[0, 30]
    assert geo.CB[30][b, r, geo.x_index(0.0)]
    assert not geo.CB[30][b, r, geo.x_index(5.0)]
    assert not (geo.CBM[30] & ~geo.CB[30]).any()                 # the held-key mask is a subset


def test_map_regions(built):
    geo, pm = built
    g = pm.ground
    assert np.isneginf(g[10, geo.x_index(0.0)])                  # inside the body: infeasible
    assert 0.0 <= g[10, geo.x_index(-6.5)] <= geo.cfg.wc + 1e-6 or g[10, geo.x_index(-6.5)] > 1.0
    assert g[10, geo.x_index(4.0)] > 1.0                         # in front at 4 u early in the antic: a strike reachable
    st = pm.strike
    assert (st[10:40] > 0).any()                                 # strikes during the antic
    assert not (st[50:56] > 0).any()                             # none while the hammer comes down
    # the person's late-antic window (press 42-47, 2.5-5 u in front) holds strike cells
    xs = geo.xs
    sel = (xs >= 2.5) & (xs <= 5.0)
    assert (st[42:48][:, sel] > 0).sum() >= 10


def test_strike_values_need_a_press_late_too(built):
    geo, pm = built
    # every stored strike value at (k, s, x, d) has a partner at k + 1 (the press one frame late) that is a strike too
    k, s, xi, d = np.nonzero(np.isfinite(pm.SV[:, :, :, :].astype(np.float32)))
    assert len(k) > 100
    i = np.random.default_rng(1).choice(len(k), size=50, replace=False)
    for a in i:
        assert np.isfinite(float(pm.S[k[a], s[a], xi[a]]))       # a strike node is a feasible node


def test_quantize_and_store(built, tmp_path):
    geo, pm = built
    a = np.array([-np.inf, np.nan, 0.0, 1.234, 9.0])
    b = sm.dequantize(sm.quantize(a))
    assert np.isneginf(b[0]) and np.isnan(b[1]) and b[2] == 0.0 and abs(b[3] - 1.24) < 1e-6 and b[4] == 5.0
    path = tmp_path / "special_map_test.npz"
    sm.save_map(path, geo, [pm], {"source_commit": "test"})
    m = sm.SpecialMap.load(path=path)
    assert m.K == geo.K and m.NX == geo.NX and m.holds == [4, 8, 16]
    assert np.isneginf(m.ground(10, 0.0, q=0))
    assert m.readiness(4.0) > 1.0
    ch = m.ground_choice(30, 4.0)
    assert ch["best"] in ch["options"] and np.isfinite(ch["value"])
    assert m.layer("apex", 30).shape == (len(geo.tubes) - 1, geo.NX)


def test_closed_loop_no_damage_without_noise(built):
    from ssbot.tools.sg2_sim import Sim
    geo, pm = built
    sim = Sim(geo, pm, np.random.default_rng(3))
    sim.late_p, sim.offset = 0.0, False
    hits = 0
    for tl in geo.variants[:5]:
        assert len(tl.state) >= geo.K + 3
        for x0 in (-4.0, 4.0, 5.0):
            e = sim.run(tl, "ground", 0, x0, {"kind": "ground", "k": 0}, 0.02, 0)
            assert np.isfinite(e.readiness)
            assert e.damage_f < 0, (v.name, x0, e.damage_f, e.contacts)
            hits += e.hits
    assert hits >= 10


def test_overlay_layer(built, tmp_path):
    import types
    from ssbot.tools import zone_overlay as zo
    geo, pm = built
    path = tmp_path / "special_map_test.npz"
    sm.save_map(path, geo, [pm], {"source_commit": "test"})
    eng = types.SimpleNamespace(_smap=sm.SpecialMap.load(path=path))
    tl = ps.SlamTimeline.load()
    h = {"pos": [31.0 + 4.0, ps.FLOOR_Y + ps.HERO_STAND_DY], "box": [34.75, ps.FLOOR_Y, 35.25, ps.FLOOR_Y + 2.08]}
    sp = zo.special_map_now(eng, tl, 30, 31.0, 1, h)
    assert sp is not None and sp["hero"]["ground"] and abs(sp["hero"]["xm"] - 4.0) < 0.01
    assert sp["choice"]["best"] in sp["choice"]["options"]
    img = np.zeros((540, 960, 4), np.uint8)
    Hw = np.array([[30.0, 0.0, -400.0], [0.0, -30.0, 600.0], [0.0, 0.0, 1.0]])
    zo.draw_smap(img, sp, Hw, 540)
    assert img.any()
