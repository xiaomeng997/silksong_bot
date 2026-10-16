"""Task 1v1 SG7 (forum.md 63): the hammer's polygons, the stage-aligned rows, the row-mapped sources and kernels, the
observation and the wall buckets. A reduced map (three holds, a narrower x range, a short tail) keeps the tests fast."""
from dataclasses import replace

import numpy as np
import pytest

from ssbot.combat import map_lookahead as ml
from ssbot.combat import pogo_slam as ps
from ssbot.combat import special_map as sm
from ssbot.combat import special_map_rt as rt
from ssbot.combat.hero_macros import HeroMacros
from ssbot.combat.move_data import HAMMER_POLY, load_cl_slam
from ssbot.knowledge import kinematics as kin

BASE = dict(x_lo=-7.0, x_hi=9.0, holds=(4, 8, 16), tail=30, keyed=True, key_noise="hard", wc=1.0, c_cap=3.0)


@pytest.fixture(scope="module")
def hm():
    from ssbot.train.forum_planner_policy import CREST_PARAMS
    params = kin.HeroParams.load(CREST_PARAMS["Wanderer"])
    terrain = kin.Terrain2D.from_boxes([(0.0, ps.FLOOR_Y - 5.0, 80.0, ps.FLOOR_Y)])
    return params, terrain, HeroMacros(params, terrain, x_world=40.0)


@pytest.fixture(scope="module")
def stage_map(hm, tmp_path_factory):
    """The stage map on the observed variants (poly + head), phases 0 and 1, stored and loaded."""
    params, terrain, h = hm
    cfg = sm.MapConfig(**BASE, variants="observed", poly=True, head_u=0.2187, stage=True)
    geo = sm.Geometry(load_cl_slam(poly=True), h, cfg)
    pms = [sm.StageKeyedMapBuilder(geo).build(p, keep_full=True) for p in (0, 1)]
    scale = rt.level_scale(cfg.wc)
    arrs = {}
    for pm in pms:
        arrs.update(rt.phase_levels(pm, True, scale))
    path = tmp_path_factory.mktemp("sg7") / "levels.npz"
    rt.save_levels(path, geo, arrs, [0, 1], scale, {"ready_ref": 3.0, "stage": geo.row_table()})
    return {"geo": geo, "pms": pms, "path": path, "params": params, "terrain": terrain, "hm": h}


def test_hammer_polygons_are_the_template_boxes():
    spec = load_cl_slam(poly=True)
    for t in spec.tracks:
        if t.name in HAMMER_POLY:
            pg = np.asarray(t.poly)
            b = next(iter(t.by_state.values()))[0]
            assert np.allclose([pg[:, 0].min(), pg[:, 0].max(), pg[:, 1].min(), pg[:, 1].max()], b, atol=0.01)
    tl = spec.timeline()
    k = tl.entry["Slam 2"] + 1
    shapes = tl.damage_shapes(k)
    assert any(pg is not None for _, pg in shapes)
    # the polygon moves with the lunge as its box does
    for b, pg in shapes:
        if pg is not None:
            assert abs(pg[:, 0].min() - b[0]) < 0.01 and abs(pg[:, 0].max() - b[1]) < 0.01


def test_polygon_damage_is_inside_the_box_damage(hm):
    _, _, h = hm
    g_box = sm.Geometry(load_cl_slam(), h, sm.MapConfig(**BASE, variants="t1"))
    g_pol = sm.Geometry(load_cl_slam(poly=True), h, sm.MapConfig(**BASE, variants="t1", poly=True))
    g_hd = sm.Geometry(load_cl_slam(poly=True), h, sm.MapConfig(**BASE, variants="t1", poly=True, head_u=0.2187))
    assert not (g_pol.D & ~g_box.D).any() and (g_box.D & ~g_pol.D).sum() > 1000
    assert not (g_pol.D & ~g_hd.D).any()            # the head only adds damage cells
    # the polygon clearance never exceeds the true gap: one Slam 2 frame against shapely, sampled
    import shapely
    k = 60
    b = [i for i, pp in enumerate(g_pol.dmgp[k]) if pp is not None]
    assert b
    q, dx = g_pol.dmgp[k][b[0]]
    poly = shapely.Polygon(g_pol.pbase[q] + [dx, 0.0])
    c = g_pol.cfg
    rng = np.random.default_rng(1)
    for _ in range(200):
        yb = int(rng.integers(0, g_pol.NYB))
        xi = int(rng.integers(0, g_pol.NX))
        lo = g_pol.y_lo + c.yb * yb
        x = g_pol.xs[xi]
        r = shapely.box(x - g_pol.hw - c.mx, lo - c.my, x + g_pol.hw + c.mx, lo + c.yb + g_pol.H + c.my)
        d = poly.distance(r)
        assert g_pol.CL[k, yb, xi] <= min(d, c.c_cap) + 1e-5


def test_stage_builder_equals_keyed_with_one_variant(hm):
    _, _, h = hm
    cfg = sm.MapConfig(**BASE, variants="nominal")
    g0 = sm.Geometry(load_cl_slam(), h, cfg)
    g1 = sm.Geometry(load_cl_slam(), h, replace(cfg, stage=True))
    assert g1.NR == g1.K and (g1.RM[0, :g1.K] == np.arange(g1.K)).all()
    a = sm.KeyedMapBuilder(g0).build(2, keep_full=True)
    b = sm.StageKeyedMapBuilder(g1).build(2, keep_full=True)
    for nm in ("S", "SV", "ground", "jstart", "strike"):
        x, y = getattr(a, nm).astype(np.float32), getattr(b, nm).astype(np.float32)
        assert np.array_equal(np.nan_to_num(x, nan=-7), np.nan_to_num(y, nan=-7)), nm


def test_stage_rows(stage_map):
    g = stage_map["geo"]
    assert (g.RM[:, 0] == 0).all() and g.rows[0] == (0, ("A",))
    # before the earliest antic end every variant shares one row per frame
    a_min = min(v.frames["Slam Antic"] for v in g.variants)
    assert all(len(g.rows_at[k]) == 1 for k in range(a_min))
    # a row's consistent variants agree on the info; the reachable rows are the variants' own next rows
    for r in range(g.NR):
        k, inf = g.rows[r]
        assert all(sm.Geometry.info_of(g.variants[v], k) == inf for v in g.RV[r])
        for m in (1, 2):
            if k + m < g.K:
                assert set(g.REACH[r][m]) == set(int(x) for x in g.RM[g.RV[r], k + m])
    # after the Slam 0 entry the damage is only the consistent variants': no Slam 1 hammer in a Slam 0 row two frames
    # after an entry at 47 (the union over the variants had it from frame 51 on)
    r47 = g.rows.index((49, ("S0", 47)))
    assert not (g.DR[r47] & ~g.D[49]).any() and g.DR[r47].sum() < g.D[49].sum()


def test_stage_map_value_never_below_the_union_map(stage_map, hm):
    """Knowing the stage entries can only help: on the antic rows every node feasible on the union map (same geometry,
    frame clock) is feasible on the stage map."""
    g = stage_map["geo"]
    _, _, h = hm
    gu = sm.Geometry(load_cl_slam(poly=True), h, replace(g.cfg, stage=False))
    pu = sm.KeyedMapBuilder(gu).build(0, keep_full=True)
    ps_ = stage_map["pms"][0]
    for k in (20, 40, 46):
        r = g.rows_at[k][0]
        a = ps_.S[r].astype(np.float32)
        b = pu.S[k].astype(np.float32)
        fin = np.isfinite(b)
        assert (np.isfinite(a) | ~fin).all()            # feasible on the union map -> feasible on the stage map
        # the score (strike value + WC x clearance of the chosen path) need not dominate: the branch minimum is taken
        # per component (value, clearance) of differently chosen paths; 99.4 % of the cells do here
        assert (a[fin] >= b[fin] - 0.03).mean() > 0.99


def test_store_sources_and_kernels(stage_map, tmp_path, monkeypatch):
    from ssbot.combat import special_map_jit as smj
    monkeypatch.setattr(rt, "CACHE", tmp_path / "cache")
    srcs, ti, meta = rt.load_levels(stage_map["path"], mmap=True)
    assert meta["stage"]["RM"][0][0] == 0
    run = rt.MapRuntime(stage_map["params"], stage_map["terrain"], srcs=srcs, ti=ti, meta=meta, hm=stage_map["hm"])
    g = stage_map["geo"]
    pm = stage_map["pms"][0]
    # a source on a variant's row map reads the builder's rows
    vi = 5
    src = srcs[0].with_rows(g.RM[vi])
    rng = np.random.default_rng(2)
    flags = rt.press_flags(pm)
    for _ in range(300):
        k = int(rng.integers(0, ti.K - 1))
        s = int(rng.integers(0, g.NS))
        xi = int(rng.integers(0, g.NX))
        x = g.xs[xi]
        r = int(g.RM[vi, k])
        c = int(rng.integers(-1, 2))
        v = src.S(k, s, x, c)
        lv = rt.to_levels(pm.S[r, c + 1, s, xi:xi + 1].astype(np.float32), meta["scale"])[0]
        assert (v == -np.inf and lv >= rt.NONE_LEVEL) or abs(v - lv * meta["scale"]) < 1e-9
        assert src.pbit(r, c, s, xi) == bool(flags[r, c + 1, s, xi])
    # the observation: Slam 0 seen at 47 -> only the variants whose antic was 47 frames
    ok = run.observe({"Slam 0": 47}, 49)
    assert ok and all(run.vtl[i].entry["Slam 0"] == 47 for i in ok)
    assert run.rows and all(int(rm[49]) == g.rows.index((49, ("S0", 47))) for rm in run.rows)
    # still in the antic at 47: the antic lasts 48 or 49 frames
    ok = run.observe({}, 47)
    assert ok and all(run.vtl[i].frames["Slam Antic"] in (48, 49) for i in ok)
    # the compiled decision equals the Python reference on the observation's sources
    run.use_jit = True
    ev = {"kind": "ground", "k": 40}
    for k, x, c in ((40, 4.0, 0), (45, 5.0, -1), (47, 3.5, 1)):
        ev = {"kind": "ground", "k": k}
        run.observe({}, k)
        vj, aj = run.decide_jit([0, 1], k, ev, x, c, -100, 0.02, None)
        vp, ap, _ = rt.decide_multi(run._srcs([0, 1]), k, ev, x, c, -100, 0.02, None)
        assert aj == ap and (vj == vp or abs(vj - vp) < 1e-9)
    run.observe(None)
    assert smj.warm() >= 0.0


def test_wall_buckets():
    B = rt.MapRuntime.wall_bucket
    arena = (14.01, 48.99)
    assert B(31.0, 1, arena) == ""                    # 18 u in front, 17 behind: open floor
    assert B(48.99 - 13.0, 1, arena) == "_f12"        # 13 u in front -> the 12 u bucket (the hero limited more)
    assert B(48.99 - 7.0, 1, arena) == "_f6.5"
    assert B(48.99 - 6.0, 1, arena) is None           # nearer than every bucket: the wall exit
    assert B(14.01 + 5.0, 1, arena) == "_b4"          # 5 u behind (front 30 u)
    assert B(14.01 + 1.0, 1, arena) is None
    assert B(14.01 + 7.0, -1, arena) == "_f6.5"       # facing left: the left wall in front
