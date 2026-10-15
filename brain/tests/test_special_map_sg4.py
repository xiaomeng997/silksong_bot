"""Task 1v1 SG4: the keyed map (special_map.KeyedMapBuilder), decide_keyed, the run-time store and map row
(special_map_rt), the planner helper's exits and readiness penalty (forum_map). A reduced map (T1's nine variants,
three holds, a narrower x range, phases 0 and 1) keeps the tests fast; forum.md 59."""
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from ssbot.combat import map_lookahead as ml
from ssbot.combat import pogo_slam as ps
from ssbot.combat import special_map as sm
from ssbot.combat import special_map_rt as rt
from ssbot.combat.hero_macros import ALPHAS, HeroMacros
from ssbot.combat.move_data import load_cl_slam
from ssbot.knowledge import kinematics as kin


@pytest.fixture(scope="module")
def setup(tmp_path_factory):
    from ssbot.train.forum_planner_policy import CREST_PARAMS
    params = kin.HeroParams.load(CREST_PARAMS["Wanderer"])
    terrain = kin.Terrain2D.from_boxes([(0.0, ps.FLOOR_Y - 5.0, 80.0, ps.FLOOR_Y)])
    hm = HeroMacros(params, terrain, x_world=40.0)
    base = sm.MapConfig(x_lo=-7.0, x_hi=9.0, holds=(4, 8, 16), variants="t1", tail=40)
    geo = sm.Geometry(load_cl_slam(), hm, base)
    pm_u = sm.MapBuilder(geo).build(0, keep_full=True)
    out = {"params": params, "terrain": terrain, "hm": hm, "geo": geo, "base": base, "unkeyed": pm_u}
    for mode in ("none", "hard", "hard_exp"):
        geo.cfg = replace(base, keyed=True, key_noise=mode)
        out[mode] = [sm.KeyedMapBuilder(geo).build(p, keep_full=True) for p in ((0, 1) if mode == "hard_exp" else (0,))]
    geo.cfg = replace(base, keyed=True, key_noise="hard_exp")
    scale = rt.level_scale(geo.cfg.wc)
    arrs = {}
    for pm in out["hard_exp"]:
        arrs.update(rt.phase_levels(pm, True, scale))
    path = tmp_path_factory.mktemp("sg4") / "levels.npz"
    rt.save_levels(path, geo, arrs, [0, 1], scale, {"ready_ref": 2.0})
    out["path"] = path
    out["scale"] = scale
    return out


def test_keyed_shapes_and_hard_is_stricter(setup):
    none, hard = setup["none"][0], setup["hard"][0]
    geo = setup["geo"]
    assert none.S.shape == (geo.K, 3, geo.NS, geo.NX) and none.SV.shape == (geo.K, geo.NS, geo.NX, 3)
    fn = np.isfinite(none.S.astype(np.float32))
    fh = np.isfinite(hard.S.astype(np.float32))
    # the late key change as a hard partner only removes choices: a node feasible with it is feasible without it
    assert not (fh & ~fn).any()
    assert (fn & ~fh).sum() > 0
    # the damage geometry is key independent: a damaged node is infeasible for every state key
    yb0 = int(geo.ybin(0.0))
    k = 58
    dmg = geo.D[k][yb0]
    assert not np.isfinite(none.S[k, :, 0, dmg].astype(np.float32)).any()


def test_keyed_strike_reads_the_held_key(setup):
    """A keyed strike value never exceeds the unkeyed one by more than the late-jump rule allows: the bounce is read
    with the key held at the contact (the unkeyed pass took the best key there)."""
    u = setup["unkeyed"].SV.astype(np.float32)
    k = setup["none"][0].SV.astype(np.float32)
    both = np.isfinite(u) & np.isfinite(k)
    assert both.sum() > 1000
    assert np.median(k[both] - u[both]) <= 1e-3


def test_level_store_roundtrip(setup, tmp_path, monkeypatch):
    for mmap in (False, True):
        monkeypatch.setattr(rt, "CACHE", tmp_path / "cache")
        srcs, ti, meta = rt.load_levels(setup["path"], mmap=mmap)
        assert meta["keyed"] and meta["phases"] == [0, 1]
        pm = setup["hard_exp"][0]
        src = srcs[0]
        rng = np.random.default_rng(3)
        flags = rt.press_flags(pm)
        for _ in range(400):
            k = int(rng.integers(0, ti.K))
            s = int(rng.integers(0, ti.NS))
            xi = int(rng.integers(0, ti.NX))
            c = int(rng.integers(-1, 2))
            x = ti.x_lo + xi * ti.step
            v = float(pm.S[k, c + 1, s, xi])
            got = src.S(k, s, x, c)
            if np.isfinite(v):
                assert abs(got - round(max(v, 0) / setup["scale"]) * setup["scale"]) < 1e-6
            else:
                assert got == -np.inf
            assert src.pbit(k, c, s, xi) == bool(flags[k, c + 1, s, xi])


def test_plan_matches_the_sim(setup):
    from ssbot.tools.sg2_sim import Sim
    geo = setup["geo"]
    srcs, ti, meta = rt.load_levels(setup["path"], mmap=False)
    R = rt.MapRuntime(setup["params"], setup["terrain"], srcs=srcs, ti=ti, meta=meta, hm=setup["hm"])
    tl = geo.spec.timeline(K=geo.K + 20)
    for x0 in (3.0, 6.0):
        pl = R.plan(0, x0, {"kind": "ground", "k": 0}, 0, -100, [0], 70)
        sim = Sim(geo, setup["hard_exp"][0], np.random.default_rng(1), src=srcs[0])
        sim.late_p, sim.offset = 0.0, False
        e = sim.run(tl, "g", 0, x0, {"kind": "ground", "k": 0}, 0.02, 0)
        assert pl.presses and pl.presses == [p - 1 for p in e.presses][:len(pl.presses)]
        sx = np.array([t[1] for t in e.trace])[:len(pl.xs)]
        assert np.abs(sx - pl.xs[:len(sx)]).max() < 1e-4
        # the masks: world keys (face -1 mirrors them), the attack and down bits at the press
        pw = R.plan(0, x0, {"kind": "ground", "k": 0}, 0, -100, [0], 70, face=-1)
        assert pw.presses == pl.presses
        m1, m2 = pl.masks, pw.masks
        assert ((m1 & kin.B_RIGHT) != 0).sum() == ((m2 & kin.B_LEFT) != 0).sum()
        assert (m1[pl.presses[0]] & kin.B_ATTACK) and (m1[pl.presses[0]] & kin.B_DOWN)


def test_phases_of():
    for q in range(6):
        a = ALPHAS[q]
        for k in (0, 7, 40):
            assert rt.phases_of(a, a, k) == [(q + k) % 6]
    assert len(rt.phases_of(0.0, 0.99, 0)) == 6


def test_no_jump_fallback_and_keep_key(setup):
    srcs, ti, meta = rt.load_levels(setup["path"], mmap=False)
    src = srcs[0]

    class Dead:
        """Every value infeasible."""
        keyed, mode, pl, gamma = True, "hard_exp", src.pl, src.gamma

        def __init__(self):
            self.ti, self.st, self.p = src.ti, src.st, src.p

        def S(self, *a):
            return -np.inf

        def Smax(self, *a):
            return -np.inf

        def SV(self, *a):
            return -np.inf
    d = Dead()
    v, act, cands = ml.decide(d, 20, {"kind": "ground", "k": 20}, 3.0, 0, -100, 0.02)
    assert act == ("dir", 1)                         # retreat on the ground (away from its front)
    assert not any(c[1][0] == "jump" for c in cands)
    v, act, _ = ml.decide(d, 20, {"kind": "ground", "k": 20}, -3.0, 0, -100, 0.02)
    assert act == ("dir", -1)
    v, act, _ = ml.decide(d, 20, {"kind": "jump", "h": 8, "k": 15}, 3.0, -1, -100, 0.02, land=40)
    assert act == ("dir", -1)                        # in the air: keep the key
    # no jump without a reachable strike: every offered jump's value is above the clearance-only score
    for x in np.arange(-6.0, 8.0, 0.5):
        for k in (0, 20, 60, 80):
            _, _, cands = ml.decide(src, k, {"kind": "ground", "k": k}, float(x), 0, -100, 0.02)
            for v, a in cands:
                if a[0] == "jump":
                    assert v + 0.02 > ti.wc + 1e-3


def _mock(x_clapper: float, state: str, t: float, flip: bool = True, t0: float = 1.0):
    e = {"type_key": "Song Heavy Sentry", "pos": [x_clapper, ps.FLOOR_Y + 3.0], "flipX": flip,
         "fsms": [{"name": "Control", "state": state, "t": t}]}
    inst = SimpleNamespace(fam="CC_SLAM", t0=t0)
    trk = SimpleNamespace(now={7: ("Song Heavy Sentry", e, inst)})
    return SimpleNamespace(rs=SimpleNamespace(trk=trk, k_shift=0)), e


def _helper(setup):
    from ssbot.combat import forum_map
    srcs, ti, meta = rt.load_levels(setup["path"], mmap=False)
    R = rt.MapRuntime(setup["params"], setup["terrain"], srcs=srcs, ti=ti, meta=meta, hm=setup["hm"])
    pl = SimpleNamespace(params=setup["params"], terrain=setup["terrain"])
    h = forum_map.MapHelper(pl)
    h._rt, h._loaded = R, True
    return h, R


def test_map_row_and_deviation_exit(setup, monkeypatch):
    from ssbot.combat import forum_map
    monkeypatch.setattr(forum_map, "FORUM_ARENA", (0.0, 80.0))
    h, R = _helper(setup)
    params = setup["params"]
    cx = 40.0
    f, e = _mock(cx, "Slam Antic", 0.1)
    start = kin.initial_state(params, cx + 4.0, setup["hm"].stand_py, facing=-1, ground=True, alpha=ALPHAS[0])
    hold = kin.HoldState.idle()
    row = h.row(f, start, hold, np.zeros(0, np.int64), 36, 0)
    assert row is not None and h.info["on"] and row.cmd.shape == (36,)
    assert abs(h.info["x"] - 4.0) < 0.2                      # flipX: it faces +x, the hero 4 u in front
    assert forum_map.BOARD[7]["on"]
    # the Clapper 0.5 u off its anchor + the displacement range (knockback): the map is left for this slam
    e["pos"][0] = cx + 0.6
    assert h.row(f, start, hold, np.zeros(0, np.int64), 36, 1) is None and h.info["why"] == "deviation"
    e["pos"][0] = cx
    assert h.row(f, start, hold, np.zeros(0, np.int64), 36, 2) is None and h.info["why"] == "deviation"
    # a new slam instance: a new anchor
    f2, e2 = _mock(cx, "Slam Antic", 0.1, t0=5.0)
    assert h.row(f2, start, hold, np.zeros(0, np.int64), 36, 3) is not None
    # near a wall: out
    monkeypatch.setattr(forum_map, "FORUM_ARENA", (cx - 20.0, cx + 10.0))
    f3, _ = _mock(cx, "Slam Antic", 0.1, t0=9.0)
    assert h.row(f3, start, hold, np.zeros(0, np.int64), 36, 4) is None and h.info["why"] == "wall"


def test_readiness_penalty(setup):
    h, R = _helper(setup)
    params = setup["params"]
    cx = 40.0
    f, _ = _mock(cx, "Walk", 0.3)
    start = kin.initial_state(params, cx + 4.0, setup["hm"].stand_py, facing=-1, ground=True, alpha=ALPHAS[0])
    T = 36
    xs = np.array([cx + 4.5, cx + 2.4, cx + 8.0, cx + 4.5])
    N = len(xs)
    box = np.zeros((N, T + 1, 4))
    y0 = setup["hm"].stand_y0
    for i, x in enumerate(xs):
        box[i, :, 0], box[i, :, 2] = x - 0.25, x + 0.25
        box[i, :, 1], box[i, :, 3] = y0, y0 + 1.3
    flags = np.full((N, T + 1), kin.F_GROUND, np.int64)
    mode = np.zeros((N, T + 1), np.int64)
    mode[3, -1] = kin.M_GLIDE                                # the umbrella at the end: readiness 0
    flags[3, -1] = 0
    r1 = SimpleNamespace(box=box, flags=flags, mode=mode)
    cmd = np.zeros((N, T), np.int64)
    pen, Rr = h.readiness(f, start, r1, cmd, 0, 0)
    ref = R.ready_ref
    assert Rr[0] > 1.0 and pen[0] == pytest.approx(rt.READY_W * max(0.0, ref - Rr[0]))
    assert np.isneginf(Rr[1]) and pen[1] == 100.0            # inside its body front: no safe continuation, last
    assert Rr[2] < Rr[0] and pen[2] > pen[0]                 # 8 u: readiness about 1.5, penalised
    assert Rr[3] == 0.0 and pen[3] == pytest.approx(rt.READY_W * ref)
    from ssbot.combat import forum_map
    assert 3.0 <= forum_map.BOARD[7]["ready_x"] - cx <= 6.0
    # not in a decision state (a cast) or out of its Slam Range: no penalty
    f2, _ = _mock(cx, "Cast 2", 0.3)
    assert h.readiness(f2, start, r1, cmd, 0, 1) is None
    far = kin.initial_state(params, cx + 12.0, setup["hm"].stand_py, facing=-1, ground=True)
    assert h.readiness(f, far, r1, cmd, 0, 2) is None
