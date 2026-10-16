"""Task 1v1 SG8 (forum.md 64): the fixes from the first live runs. The airborne locate (the live jump collapse at
i0e2 f19893), the builder's jump starts only with a reachable strike (the dead ends the online rule met), the stay rule
and the jumps with every first key (Python reference = compiled kernels), the lunge re-anchored after a shortfall."""
import numpy as np
import pytest

from ssbot.combat import forum_map
from ssbot.combat import map_lookahead as ml
from ssbot.combat import pogo_slam as ps
from ssbot.combat import special_map as sm
from ssbot.combat import special_map_rt as rt
from ssbot.combat.hero_macros import HeroMacros
from ssbot.combat.move_data import load_cl_slam
from ssbot.knowledge import kinematics as kin

BASE = dict(x_lo=-7.0, x_hi=12.0, holds=(1, 4, 8, 12, 16), tail=30, keyed=True, key_noise="hard", wc=1.0, c_cap=3.0,
            variants="observed", poly=True, head_u=0.2187, stage=True, carry=True)


@pytest.fixture(scope="module")
def kinf():
    from ssbot.train.forum_planner_policy import CREST_PARAMS
    params = kin.HeroParams.load(CREST_PARAMS["Wanderer"])
    terrain = kin.Terrain2D.from_boxes([(0.0, ps.FLOOR_Y - 5.0, 80.0, ps.FLOOR_Y)])
    return params, terrain, HeroMacros(params, terrain, x_world=40.0)


def _helper():
    h = forum_map.MapHelper.__new__(forum_map.MapHelper)
    h._arc = None
    h.locate_stats = {"plan": 0, "mem": 0, "facts": 0, "open": 0, "min": 0, "fallback": 0}
    return h


def test_airborne_locate_keeps_the_maps_own_jump(kinf):
    """i0e2 f19893 (live, sg7r): the map's own jump (hold 12 from k 32 at x 5.65, value 2.3) located one frame later as
    the minimum over every hold matching the heights (holds 1-5: -inf) -> "no feasible continuation", the planner went
    FORCED. SG8: the plan's own state is among the matching slices: it is the state (finite)."""
    path = rt.map_path("sg7r")
    if not path.exists():
        pytest.skip("no sg7r map")
    params, terrain, _ = kinf
    r = rt.MapRuntime(params, terrain, path)
    r.observe({}, 32, 0, k_frac=32.0)
    plan = r.plan(32, 5.65, {"kind": "ground", "k": 32}, 0, -100, [0], 84)
    assert plan.first is not None and plan.first[0] == "jump"
    h = float(plan.first[1])
    s1 = plan.states[1]
    k, x, c = int(s1[0]), float(s1[1]), int(s1[6])
    assert k == 33 and s1[2] == "jump" and float(s1[4]) == h
    ys = [float(plan.ys[0]), 0.0]
    sl = r.locate(k, ys, 0)
    assert len(sl) > 3                                       # every hold matches one frame after the start
    old = min(r.S_obs(0, k, s, x, c) for s in sl)
    hp = _helper()
    S = np.zeros(kin.K)
    S[kin.JHELD] = 1.0
    ev, how = hp._locate_sg8(r, {"plan": plan}, k, x, c, [0], ys, S, np.zeros(2, np.int64))
    assert how == "plan" and ev["kind"] == "jump" and float(ev["h"]) == h and int(ev["k"]) == 32
    v = r.S_obs(0, k, r.ti.slice_of(ev, k - ev["k"]), x, c)
    assert np.isfinite(v) and v >= old
    # without the plan (a jump the planner started): the key held -> the open holds are the bot's own choice: the best
    ev2, how2 = hp._locate_sg8(r, {}, k, x, c, [0], ys, S, np.zeros(2, np.int64))
    assert how2 == "open" and np.isfinite(r.S_obs(0, k, r.ti.slice_of(ev2, k - ev2["k"]), x, c))
    # the row survives: a fresh plan from the located state has a finite value
    p2 = r.plan(k, x, ev, c, -100, [0], 60)
    assert np.isfinite(p2.value)


@pytest.fixture(scope="module")
def small(kinf):
    """A reduced stage map with the carry, phase 0, with and without jump_strike."""
    params, terrain, hm = kinf
    out = {}
    for js in (False, True):
        cfg = sm.MapConfig(**BASE, jump_strike=js)
        geo = sm.Geometry(load_cl_slam(poly=True, carry=True), hm, cfg)
        out[js] = (geo, sm.StageKeyedMapBuilder(geo).build(0, keep_full=True))
    return out


def _dead_ends(geo, pm) -> tuple[int, int]:
    ti = ml.TubeIndex.from_geometry(geo)
    src = ml.KeyedDenseSource(pm, ti, geo.cfg)
    fin = dead = 0
    for r_ in range(geo.NR):
        k = int(geo.row_k[r_])
        if k >= geo.K - 6:
            continue
        srcs = [src.with_rows(rm) for rm in np.unique(geo.RM[geo.RV[r_]], axis=0)]
        for c in (-1, 0, 1):
            for xi in range(0, geo.NX, 2):
                x = geo.xs[xi]
                if not np.isfinite(min(s_.S(k, 0, x, c) for s_ in srcs)):
                    continue
                fin += 1
                v, _, _ = rt.decide_multi(srcs, k, {"kind": "ground", "k": k}, x, c, -100, 0.02, None)
                dead += int(not np.isfinite(v))
    return fin, dead


def test_jump_strike_removes_the_dead_ends(small, monkeypatch):
    """A finite ground cell must give the online rule a finite decision: without jump_strike some cells were finite
    only through an escape jump the rule never takes (sg7r's noise-free damage); with it (and ALLD for the jumps'
    first key under several sources) none is left."""
    monkeypatch.setattr(ml, "ALLD", True)
    f0, d0 = _dead_ends(*small[False])
    f1, d1 = _dead_ends(*small[True])
    assert f0 > 1000 and f1 > 1000
    assert d1 == 0 and d0 >= d1


def test_stay_and_alld_python_equals_jit(kinf, small, tmp_path, monkeypatch):
    """The stay rule and the jumps with every first key: the compiled plan equals the Python reference."""
    params, terrain, hm = kinf
    geo, pm = small[True]
    scale = rt.level_scale(geo.cfg.wc)
    path = tmp_path / "lv.npz"
    rt.save_levels(path, geo, rt.phase_levels(pm, True, scale), [0], scale, {"ready_ref": 3.0,
                                                                              "stage": geo.row_table()})
    D = np.stack([np.pad(v.disp, (0, max(0, geo.K + 40 - len(v.disp))), mode="edge")[:geo.K + 40]
                  for v in geo.variants])
    monkeypatch.setattr(ml, "STAY", {"caps": None, "c_need": 1.0, "mu": 0.2, "dsp": 0.5 * (D.min(0) + D.max(0)),
                                     "fb": (4.5, 7.0), "bb": (3.0, 5.0)})
    monkeypatch.setattr(ml, "ALLD", True)
    r = rt.MapRuntime(params, terrain, path, hm=hm)
    assert abs(ml.STAY["caps"] - 1.0 / 3.0) < 1e-9
    assert r.jit_tables() is not None
    rng = np.random.default_rng(8)
    n_stay = 0
    for _ in range(120):
        k = int(rng.integers(0, 60))
        x = float(rng.uniform(-5.0, 11.0))
        c = int(rng.integers(-1, 2))
        r.observe({}, k, 0, k_frac=float(k)) if k < 47 else r.observe(None)
        a = r.plan(k, x, {"kind": "ground", "k": k}, c, -100, [0], 40, face_hero=1, face=1)
        b = r.plan_py(k, x, {"kind": "ground", "k": k}, c, -100, [0], 40, face_hero=1, face=1)
        assert a.acts == b.acts and np.array_equal(a.masks, b.masks)
        assert np.allclose(np.nan_to_num(np.asarray(a.values, float), nan=9e9, neginf=-9e9),
                           np.nan_to_num(np.asarray(b.values, float), nan=9e9, neginf=-9e9))
        n_stay += int(any(np.isfinite(v) and 0 <= v < 1.0 / 3.0 + 1e-9 for v in a.values if not np.isnan(v)))
    assert n_stay > 0


def test_stay_value_rule():
    st = np.ones(80, np.int64)
    stay = {"caps": 1.0 / 3.0, "mu": 0.2, "dsp": np.zeros(80), "fb": (4.5, 7.0), "bb": (3.0, 5.0)}
    # no strike: capped, then the face distance after the move; a strike value as it is; lambda's order kept
    assert ml.stay_value(0.9, ("dir", 1), 10.0, 1, 5, st, 0.165, 1.0, stay, 0.02) == pytest.approx(
        1.0 / 3.0 - 0.2 * (10.0 + 2 * 0.165 - 7.0))
    assert ml.stay_value(2.5, ("dir", 1), 10.0, 1, 5, st, 0.165, 1.0, stay, 0.02) == 2.5
    v_keep = ml.stay_value(0.9, ("dir", 0), 5.5, 0, 5, st, 0.165, 1.0, stay, 0.0)
    v_chg = ml.stay_value(0.9 - 0.02, ("dir", 1), 5.5, 0, 5, st, 0.165, 1.0, stay, 0.02)
    assert v_keep > v_chg                                    # in the band: no key change for nothing
    assert ml.face_dist(-4.0, 3, stay) == 0.0 and ml.face_dist(-1.0, 3, stay) == pytest.approx(2.0)


def test_lunge_short_reanchors_after_the_lunge(kinf, monkeypatch):
    """A lunge shorter than every variant: during Slam 0 / 1 no row (not sticky); in Slam 2 the anchor moves so the
    Clapper sits on the consistent variants' smallest displacement (no deviation left), the row resumes."""
    path = rt.map_path("sg7r")
    if not path.exists():
        pytest.skip("no sg7r map")
    params, terrain, _ = kinf
    r = rt.MapRuntime(params, terrain, path)
    monkeypatch.setattr(forum_map, "SG8", True)
    x0, face = 30.0, 1
    k = 58
    seen = {"Slam 0": 48.0, "Slam 1": 52.0, "Slam 2": 55.0}
    ok_v = r.observe(seen, k, 0, k_frac=float(k))
    cx = x0 + 2.4                                           # a 2.4 u lunge (live 18015 / 18811)
    assert r.deviation(k, cx, x0, face) > rt.DEV_TOL_U
    dmin = min(float(r.vtl[v].disp[k]) for v in ok_v)
    x0n = cx - face * dmin
    assert r.deviation(k, cx, x0n, face) <= rt.DEV_TOL_U + 1e-9
