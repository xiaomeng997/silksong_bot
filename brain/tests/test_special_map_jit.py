"""Task 1v1 SG6 (forum.md 62): the compiled map work (special_map_jit) equals the Python reference exactly: the
one-step decision (value and action) on random states of every physics phase (one or two phases), every tube layer
(ground, the jump holds, the bounce heights) and every state key; the map row (MapRuntime.plan: masks, path, actions,
values, states, presses, contacts, the final state; extend); the readiness of many end states (the minimum over the
phases, np.unique's first-occurrence rows); the batched lookups (the L2 strip, the off-board spot, the swing lock)
through MapHelper; the four key-noise modes on the reduced test map (RAM and mmap); the kernels compiled once at the
warm-up (no new specialisation on a real call); the switch."""
from dataclasses import replace

import numpy as np
import pytest

from ssbot.combat import map_lookahead as ml
from ssbot.combat import special_map as sm
from ssbot.combat import special_map_jit as smj
from ssbot.combat import special_map_rt as rt
from ssbot.combat.hero_macros import ALPHAS
from ssbot.knowledge import kinematics as kin
from tests.test_special_map_sg4 import _helper, _mock, setup  # noqa: F401 (the module fixture)


def _same_plan(a, b) -> bool:
    return (np.array_equal(a.masks, b.masks) and np.array_equal(a.xs, b.xs) and np.array_equal(a.ys, b.ys)
            and a.presses == b.presses and a.contacts == b.contacts and a.acts == b.acts and a.k0 == b.k0
            and (a.value == b.value or (np.isnan(a.value) and np.isnan(b.value))) and a.first == b.first
            and a.states == b.states and a.final == b.final and a.phases == b.phases
            and np.array_equal(np.array(a.values, float), np.array(b.values, float), equal_nan=True))


def _rand_state(R, rng, k_hi=None):
    ti = R.ti
    p = int(rng.integers(6)) if len(R.srcs) == 6 else int(rng.choice(sorted(R.srcs)))
    ps_ = sorted(R.srcs)
    phases = [p]
    if len(ps_) > 1 and rng.random() < 0.4:
        phases.append(int(rng.choice([q for q in ps_ if q != p])))
    k = int(rng.integers(0, (k_hi or ti.K - 6)))
    x = float(rng.uniform(ti.x_lo - 0.5, ti.x_lo + ti.step * ti.NX + 0.5)) if rng.random() < 0.1 else \
        float(rng.uniform(-6.0, 9.0))
    c = int(rng.integers(-1, 2))
    ev = {"kind": "ground", "k": k}
    if rng.random() < 0.6:
        for _ in range(20):
            s = int(rng.integers(1, ti.NS))
            if ti.valid(p, k, s):
                ev = R.ev_of_slice(s, k, p)
                break
    lp = int(rng.choice([-100, k - 1, k - 5, k - 17, k - 18, k - 19]))
    return phases, k, x, c, ev, lp


def _states(R, rng, n):
    """n random states, then the states along the map rows from some of them (the frames before presses, jumps and
    bounces)."""
    out = []
    for i in range(n):
        st = _rand_state(R, rng)
        out.append(st)
        if i % 10 == 0:
            phases, k, x, c, ev, lp = st
            R.use_jit = False
            pl = R.plan(k, x, ev, c, lp, phases, 60)
            R.use_jit = True
            for (k_, x_, kind, ek, h, yc, c_, lp_, sl) in pl.states:
                if sl:
                    continue
                e = {"kind": kind, "k": ek}
                if kind == "jump":
                    e.update(h=h, q0=(phases[0] - ek) % 6)
                elif kind == "bounce":
                    e.update(yc=yc, q0=(phases[0] - ek) % 6)
                out.append((phases, k_, x_, c_, e, lp_))
    return out


def _decide_cmp(R, rng, n):
    lam = rt.LAMBDA
    n_jump = n_press = n_air = 0
    for phases, k, x, c, ev, lp in _states(R, rng, n):
        land = R.land_of(ev) if ev["kind"] != "ground" else None
        v, a, _ = rt.decide_multi([R.srcs[p] for p in phases], k, ev, x, c, lp, lam, land)
        vj, aj = R.decide_jit(phases, k, ev, x, c, lp, lam, land)
        assert (vj == v) or (np.isnan(v) and np.isnan(vj)), (phases, k, ev, x, c, lp, v, vj)
        assert aj == a, (phases, k, ev, x, c, lp, a, aj)
        n_jump += a[0] == "jump"
        n_press += a[0] == "press"
        n_air += ev["kind"] != "ground"
    return n_jump, n_press, n_air


def _plan_cmp(R, rng, n, L=60):
    T = R.jit_tables()
    n_cont = n_press = 0
    for i in range(n):
        phases, k, x, c, ev, lp = _rand_state(R, rng)
        fh, fc = int(rng.choice([-1, 1])), int(rng.choice([-1, 1]))
        slash = None
        if ev["kind"] != "ground" and rng.random() < 0.3:
            slash = {"P": int(k - rng.integers(0, 8)), "face": fh}
        a = R.plan_py(k, x, ev, c, lp, phases, L, face_hero=fh, face=fc, slash=slash)
        b = R.plan_jit(T, k, x, ev, c, lp, phases, L, face_hero=fh, face=fc, slash=slash)
        assert b is not None and _same_plan(a, b), (phases, k, x, c, ev, lp, fh, fc, slash)
        n_cont += len(a.contacts)
        n_press += len(a.presses)
        if len(a.states) > 6 and i % 3 == 0:
            j = int(rng.integers(1, len(a.states)))
            e1 = R.extend(a, j, L, face=fc)
            R.use_jit = False
            e0 = R.extend(a, j, L, face=fc)
            R.use_jit = True
            assert _same_plan(e0, e1), (phases, k, x, c, ev, lp, fh, fc, slash, j)
    return n_cont, n_press


@pytest.fixture(scope="module")
def real():
    if not rt.map_path().exists():
        pytest.skip("the SG4 level map is not on this machine")
    from ssbot.combat import pogo_slam as ps
    from ssbot.train.forum_planner_policy import CREST_PARAMS
    params = kin.HeroParams.load(CREST_PARAMS["Wanderer"])
    terrain = kin.Terrain2D.from_boxes([(0.0, ps.FLOOR_Y - 5.0, 80.0, ps.FLOOR_Y)])
    R = rt.MapRuntime(params, terrain)
    R.use_jit = True
    assert R.jit_tables() is not None
    return R


def test_decisions_equal_on_the_real_map(real):
    """Random states over all six phases (one or two at once), every tube, every key: value and action identical."""
    nj, npr, na = _decide_cmp(real, np.random.default_rng(6), 4000)
    assert nj > 20 and npr > 20 and na > 1500           # jumps, presses and airborne states were exercised


def test_plans_equal_on_the_real_map(real):
    """The map row (and extend) from random states: every MapPlan field identical."""
    nc, npr = _plan_cmp(real, np.random.default_rng(7), 300)
    assert nc > 10 and npr > 50


def test_readiness_and_lookups_equal_on_the_real_map(real):
    R = real
    rng = np.random.default_rng(8)
    for _ in range(40):
        p_end = sorted(set(int(q) for q in rng.choice(6, size=int(rng.integers(1, 4)))))
        N = int(rng.integers(1, 120))
        xm = rng.uniform(-13.0, 17.0, N)
        kd = rng.integers(-1, 2, N)
        gnd = rng.random(N) < 0.5
        s, y0, y1 = R._k0_slices(p_end[0])
        pick = rng.integers(0, len(s), N)
        yb = np.where(rng.random(N) < 0.7, y0[pick] + rng.normal(0, 0.03, N), rng.uniform(0, 4, N))
        yp = np.where(rng.random(N) < 0.7, y1[pick] + rng.normal(0, 0.03, N), rng.uniform(0, 4, N))
        dup = rng.random(N) < 0.3                            # rows with an earlier row's key (np.unique's dedupe)
        for i in np.flatnonzero(dup):
            j = int(rng.integers(0, i + 1))
            xm[i] = xm[j] + rng.uniform(-0.05, 0.05)
            kd[i], gnd[i] = kd[j], gnd[j]
            yb[i], yp[i] = yb[j] + rng.uniform(-0.004, 0.004), yp[j]
        R.use_jit = False
        a = R.readiness_min(p_end, xm, kd, gnd, yb, yp)
        R.use_jit = True
        b = R.readiness_min(p_end, xm, kd, gnd, yb, yp)
        assert np.array_equal(a, b), p_end
        ks = rng.integers(-2, R.ti.K + 2, N)
        ss = rng.integers(-1, R.ti.NS, N)
        cs = rng.integers(-1, 2, N)
        R.use_jit = False
        a = R.S_min(p_end, ks, ss, xm, cs)
        R.use_jit = True
        assert np.array_equal(a, R.S_min(p_end, ks, ss, xm, cs))


@pytest.fixture(scope="module")
def modes(setup, tmp_path_factory):  # noqa: F811
    """The reduced map's keyed variants as level files: none / hard (phase 0), hard_exp (0, 1), exp (0, 1)."""
    geo, base = setup["geo"], setup["base"]
    out = {}
    old = geo.cfg
    try:
        geo.cfg = replace(base, keyed=True, key_noise="exp")
        exp = [sm.KeyedMapBuilder(geo).build(p, keep_full=True) for p in (0, 1)]
        for mode, pms in (("none", setup["none"]), ("hard", setup["hard"]), ("hard_exp", setup["hard_exp"]),
                          ("exp", exp)):
            geo.cfg = replace(base, keyed=True, key_noise=mode)
            scale = rt.level_scale(geo.cfg.wc)
            arrs = {}
            for pm in pms:
                arrs.update(rt.phase_levels(pm, True, scale))
            path = tmp_path_factory.mktemp("sg6") / f"levels_{mode}.npz"
            rt.save_levels(path, geo, arrs, [pm.p for pm in pms], scale, {"ready_ref": 2.0})
            out[mode] = path
    finally:
        geo.cfg = old
    return out


@pytest.mark.parametrize("mode", ["none", "exp", "hard", "hard_exp"])
def test_key_noise_modes_equal(setup, modes, mode, monkeypatch, tmp_path):  # noqa: F811
    """Every key-noise mode (the branch weights of the late key change), RAM and mmap loads."""
    monkeypatch.setattr(rt, "CACHE", tmp_path)
    for mmap in (False, True):
        srcs, ti, meta = rt.load_levels(modes[mode], mmap=mmap)
        R = rt.MapRuntime(setup["params"], setup["terrain"], srcs=srcs, ti=ti, meta=meta, hm=setup["hm"])
        R.use_jit = True
        assert R.jit_tables() is not None and srcs[0].mode == mode
        rng = np.random.default_rng(11 + mmap)
        _decide_cmp(R, rng, 600)
        _plan_cmp(R, rng, 40)


def test_helper_paths_equal(setup, monkeypatch):  # noqa: F811
    """MapHelper.readiness (rnmap and the chase: the swing lock, the L2 strip / chase band) and off_board: the same
    penalty, readiness and BOARD with the compiled lookups."""
    from types import SimpleNamespace
    from ssbot.combat import forum_map
    h, R = _helper(setup)
    params = setup["params"]
    cx = 40.0
    y0 = setup["hm"].stand_y0
    rng = np.random.default_rng(12)
    monkeypatch.setattr(forum_map, "FORUM_ARENA", (0.0, 80.0))
    for chase in (False, True):
        monkeypatch.setattr(forum_map, "CHASE", chase)
        for trial in range(12):
            f, _ = _mock(cx, "Walk", 0.3)
            start = kin.initial_state(params, cx + float(rng.uniform(2, 7)), setup["hm"].stand_py, facing=-1,
                                      ground=True, alpha=ALPHAS[int(rng.integers(6))])
            T = 36
            N = 50
            xs = cx + rng.uniform(-8, 8, N)
            box = np.zeros((N, T + 1, 4))
            for i, x in enumerate(xs):
                box[i, :, 0], box[i, :, 2] = x - 0.25, x + 0.25
                yy = 0.0 if i % 3 else float(rng.uniform(0.2, 3.0))
                box[i, :, 1], box[i, :, 3] = y0 + yy, y0 + yy + 1.3
            flags = np.full((N, T + 1), kin.F_GROUND, np.int64)
            flags[::3] = 0
            flags[1::4, -int(rng.integers(1, 15)):] |= kin.F_ATTACKING       # rows ending in a ground swing
            mode = np.zeros((N, T + 1), np.int64)
            r1 = SimpleNamespace(box=box, flags=flags, mode=mode)
            cmd = rng.choice([0, kin.B_LEFT, kin.B_RIGHT], size=(N, T)).astype(np.int64)
            rows = np.flatnonzero(rng.random(N) < 0.8)
            res = []
            for jit in (False, True):
                R.use_jit = jit
                forum_map.BOARD.clear()
                o = h.readiness(f, start, r1, cmd, 0, trial, rows=rows)
                res.append((o, dict(forum_map.BOARD)))
            (a, ba), (b, bb) = res
            assert (a is None) == (b is None)
            if a is not None:
                assert np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1], equal_nan=True)
                assert ba == bb
    # off_board: the map's best ground spot near the hero (all phases)
    for trial in range(10):
        hx = cx + float(rng.uniform(-6, 9))
        start = kin.initial_state(params, hx, setup["hm"].stand_py, facing=-1, ground=True)
        out = []
        for jit in (False, True):
            R.use_jit = jit
            forum_map.BOARD.clear()
            h.info = {"on": False, "k": int(rng.integers(0, 60)) if jit is False else out[0][1], "iid": 7,
                      "x0": cx, "face": 1, "why": "mode 3"}
            h.off_board(None, start, trial)
            out.append((dict(forum_map.BOARD), h.info["k"]))
        assert out[0][0] == out[1][0]
    R.use_jit = rt.JIT


def test_compiled_once_at_the_warm_up(real, setup, tmp_path, monkeypatch):  # noqa: F811
    """warm() compiles every kernel with the run-time types (read-only levels): a real call (mmap or RAM tables)
    adds no specialisation, so neither the first arena tick nor the first slam tick compiles."""
    smj.warm()
    n0 = {nm: len(getattr(smj, nm).signatures) for nm in ("plan_k", "decide_k", "ready_k", "smin_k")}
    real.plan(10, 4.0, {"kind": "ground", "k": 10}, 0, -100, [2, 3], 60)
    real.readiness_min([0, 5], np.array([4.0, 5.0]), np.array([0, 1]), np.array([True, False]),
                       np.array([0.0, 1.0]), np.array([0.0, 0.8]))
    real.S_min([1], 0, 0, np.array([4.0]), 0)
    real.decide_jit([4], 10, {"kind": "ground", "k": 10}, 3.0, 1, -100, 0.02, None)
    srcs, ti, meta = rt.load_levels(setup["path"], mmap=False)                       # writable arrays
    R2 = rt.MapRuntime(setup["params"], setup["terrain"], srcs=srcs, ti=ti, meta=meta, hm=setup["hm"])
    R2.use_jit = True
    R2.plan(0, 4.0, {"kind": "ground", "k": 0}, 0, -100, [0, 1], 60)
    assert {nm: len(getattr(smj, nm).signatures) for nm in n0} == n0


def test_switch(setup, monkeypatch):  # noqa: F811
    """SSBOT_FORUM_SPECIAL_MAP_JIT=0: the Python reference (plan dispatches to plan_py)."""
    srcs, ti, meta = rt.load_levels(setup["path"], mmap=False)
    monkeypatch.setattr(rt, "JIT", False)
    R = rt.MapRuntime(setup["params"], setup["terrain"], srcs=srcs, ti=ti, meta=meta, hm=setup["hm"])
    assert not R.use_jit and R._jt is None
    called = []
    monkeypatch.setattr(rt.MapRuntime, "plan_jit", lambda *a, **k: called.append(1))
    p = R.plan(0, 4.0, {"kind": "ground", "k": 0}, 0, -100, [0], 60)
    assert not called and p.presses
    monkeypatch.setattr(rt, "JIT", True)
    R2 = rt.MapRuntime(setup["params"], setup["terrain"], srcs=srcs, ti=ti, meta=meta, hm=setup["hm"])
    assert R2.use_jit and R2.jit_tables() is not None
    assert ml.PRESS_COOL == smj.PRESS_COOL and sm.NONE_LEVEL == smj.NONE_LEVEL
