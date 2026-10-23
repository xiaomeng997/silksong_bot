"""Map v2 stage M4b: the search's speed work - each faster path gives the same results as the code it replaces
(clapper_jit.predict = clapper.predict, the record arrays (brnum / Geo) = the tuple loops, the vectorized windows =
windows_ref, the trajectory memo = a fresh simulate, the exit probes agree with the pass), the tick checks, the
lazy second pass."""
from __future__ import annotations

import numpy as np
import pytest

from ssbot.knowledge import kinematics as km
from ssbot.map2 import brnum
from ssbot.map2 import clapper as cm
from ssbot.map2 import clapper_jit as cj
from ssbot.map2 import env_jit as ej
from ssbot.map2 import search as ms
from ssbot.map2 import strike as sk

C = 33.0


@pytest.fixture(scope="module")
def W():
    return ms.World()


def _obs(st, x, face=-1, j=2, iid=1, will_evade=None):
    return cm.Obs(iid, st, j / 60.0, x, cm.STAND_Y, 0.0, 0.0, face, 230, None, will_evade=will_evade, j=j)


def _ground(W, x, face=1):
    return km.initial_state(W.params, x, sk.FLOOR + sk.FOOT, ground=True, facing=face)


def _sits(W):
    """A few forced situations: an Idle Clapper near / far, a slam antic, a Walk with its far timer, two Clappers."""
    out = [ms.Situation(_ground(W, C - 5.0), [_obs("Idle", C, j=8)], {1: cm.Memory()}, name="idle5"),
           ms.Situation(_ground(W, C - 9.0), [_obs("Idle", C, j=8)], {1: cm.Memory()}, name="idle9"),
           ms.Situation(_ground(W, C - 7.0), [_obs("Slam Antic", C, j=3)], {1: cm.Memory()}, name="slam7"),
           ms.Situation(_ground(W, C - 12.0), [_obs("Walk", C, j=10)], {1: cm.Memory()}, name="walk12")]
    o1, o2 = _obs("Idle", 40.0, j=20, iid=1), _obs("Walk", 26.0, face=1, j=5, iid=2)
    out.append(ms.Situation(_ground(W, 33.0), [o1, o2], {1: cm.Memory(), 2: cm.Memory()}, name="two"))
    return out


def _same_pred(P, Q):
    assert len(P.branches) == len(Q.branches) and P.n_particles == Q.n_particles
    for a, b in zip(P.branches, Q.branches):
        assert a.p == b.p and a.choices == b.choices and a.reveal == b.reveal and a.n_merged == b.n_merged
        assert a.recs == b.recs and a.hazards == b.hazards


def _paths(W, sit, T):
    """Her do-nothing path, and the same with a down slash hit on Clapper 1 at frame 12 and a side hit at 30."""
    tr0 = ms.simulate(W, ms.Plan([ms.Seg(np.zeros(1, np.int64))]), lambda iid: None, 1, sit.S,
                      sk.HOOK_VARIANTS[0], sit.alpha_c)
    yield ms.hero_path(tr0, T, {})
    yield ms.hero_path(tr0, T, {1: {12: ("down", sk.DS_DMG), 30: ("side", 10)}})


def test_jit_predict_equals_python(W):
    for sit in _sits(W):
        for T in (60, 140):
            for path in _paths(W, sit, T):
                P = cm.predict(sit.obs, sit.mems, path, W.K, T=T, hazards=sit.hazards)
                Q = cj.predict(sit.obs, sit.mems, path, W.K, T=T, hazards=sit.hazards)
                _same_pred(P, Q)
                Pu = cm.predict(sit.obs, sit.mems, path, W.K, T=T, group=False)
                Qu = cj.predict(sit.obs, sit.mems, path, W.K, T=T, group=False)
                _same_pred(Pu, Qu)
    assert cj.STATS["jit"] > 0


def test_python_sum_is_neumaier():
    a = np.array([15 / 105.0] * 7)
    assert cj._pysum(a, 7) == sum(a.tolist())
    assert cj._pysum(a, 0) == 0.0


def _plain(b):
    return cm.Branch(b.p, b.choices, b.reveal, b.recs, b.hazards, b.K, b.T, b.n_merged)


def _ref(fn, *a):
    brnum.ON[0] = False
    try:
        return fn(*a)
    finally:
        brnum.ON[0] = True


def test_record_arrays_equal_the_tuple_loops(W):
    n = 0
    for sit in _sits(W):
        for path in _paths(W, sit, 150):
            P = cj.predict(sit.obs, sit.mems, path, W.K, T=150, hazards=sit.hazards)
            for b in P.branches:
                q = _plain(b)
                va, vr = ms.timing_views(b), _ref(ms.timing_views, q)
                assert len(va) == len(vr)
                for x, y in zip(va, vr):
                    assert x.recs == y.recs and getattr(x, "t_reveal", None) == getattr(y, "t_reveal", None)
                    assert x.p == y.p and getattr(x, "tview", "") == getattr(y, "tview", "")
                    xq = y if y is not q else _plain(y)
                    for iid in brnum.iids(x):
                        assert np.array_equal(sk.robust_boxes(x, iid, x.T), _ref(sk.robust_boxes, xq, iid, xq.T),
                                              equal_nan=True)
                        for k in range(0, x.T + 1, 7):
                            assert sk.state_at(x, iid, k) == _ref(sk.state_at, xq, iid, k)
                    assert ms.move_spans(x) == _ref(ms.move_spans, xq)
                    for k in range(0, x.T + 1, 5):
                        for mg in (True, False):
                            d1 = ms.branch_danger(x, k, mg)
                            d2 = _ref(ms.branch_danger, xq, k, mg)
                            assert d1.shape == d2.shape
                            if len(d1):
                                assert np.array_equal(d1[np.lexsort(d1.T[::-1])], d2[np.lexsort(d2.T[::-1])])
                    n += 1
    assert n > 10


def test_first_collision_equals_the_loop(W):
    rng = np.random.default_rng(3)
    for sit in _sits(W):
        P = cj.predict(sit.obs, sit.mems, next(iter(_paths(W, sit, 120))), W.K, T=120)
        for b in P.branches:
            for x in ms.timing_views(b):
                xq = _plain(x)
                for _ in range(6):
                    n = 100
                    xs = np.cumsum(rng.normal(0, 0.3, n + 1)) + rng.uniform(16, 47)
                    ys = np.full(n + 1, sk.FLOOR + sk.FOOT) + np.abs(np.cumsum(rng.normal(0, 0.2, n + 1)))
                    tr = ms.Traj(np.stack([xs, ys], 1), np.zeros((n + 1, 4)), np.zeros(n + 1, bool),
                                 np.ones(n + 1, np.int64), np.zeros(n + 1, np.int64), rng.random(n + 1) < 0.1,
                                 np.zeros(n + 1, bool), {}, [], [], [], n, [0])
                    got = ms.first_collision(x, tr, 1, n, True)
                    want = None
                    brnum.ON[0] = False
                    try:
                        for k in range(1, n + 1):
                            if tr.ifr[k]:
                                continue
                            hb = cm.hurtbox(*tr.pos[k])
                            if hb[0] < ms.WALL_L or hb[2] > ms.WALL_R or \
                                    ms.shapes_hit(ms.bdamage(xq, k, True), hb):
                                want = k
                                break
                    finally:
                        brnum.ON[0] = True
                    assert got == want


def test_windows_vectorized_equal_the_loops(W):
    for sit in _sits(W):
        S = ms.Searcher(W, ms.Cfg())
        rt = S.root(sit)
        for fw in S.passes(rt):
            assert S.windows(rt, fw) == S.windows_ref(rt, fw)


def test_trajectory_memo_equals_fresh(W):
    sit = _sits(W)[0]
    S = ms.Searcher(W, ms.Cfg())
    rt = S.root(sit)
    fw = S.passes(rt)[0]
    n = 0
    for c in S.windows(rt, fw)[:8]:
        seg = S.realize(rt, fw, c)
        if seg is None:
            continue
        plan = ms.Plan([seg])
        for b0 in rt.pred.branches:
            for b in ms.timing_views(b0):
                a = S.ev.sim(sit, plan, sk.HOOK_VARIANTS[0], 1, b, rt.pred.T, 2)
                f = ms.simulate(W, plan, lambda iid, b=b: sk.robust_boxes(b, iid, rt.pred.T), 1, sit.S,
                                sk.HOOK_VARIANTS[0], sit.alpha_c, br=b, lag=2)
                assert np.array_equal(a.pos, f.pos) and a.contacts == f.contacts and a.end == f.end
                n += 1
    assert n > 0 and S.ev.n_sim_hit > 0


def test_exit_probe_agrees_with_the_pass(W):
    rng = np.random.default_rng(5)
    ev = ms.Evaluator(W, ms.Cfg())
    n_probe = 0
    for _ in range(60):
        S = _ground(W, rng.uniform(20, 42))
        if rng.random() < 0.5:
            S = km.initial_state(W.params, rng.uniform(20, 42), sk.FLOOR + rng.uniform(1, 5) + sk.FOOT, ground=False,
                                 vy=rng.uniform(-8, 8), facing=1)
        H = 40
        dz = []
        for t in range(H + 1):
            bx = []
            for _q in range(rng.integers(0, 4)):
                x0, y0 = rng.uniform(15, 47), rng.uniform(2, 12)
                bx.append((x0, y0, x0 + rng.uniform(0.5, 4), y0 + rng.uniform(0.5, 4)))
            dz.append(np.concatenate([np.asarray(bx, float).reshape(-1, 4), ms.WALL_BOXES]))
        off = np.zeros(H + 2, np.int64)
        off[1:] = np.cumsum([len(d) for d in dz])
        i = ej.probe_exit(S, np.array([-1.0, 0, 0, 0, 0, 0, 0]), ms._probe_masks(S, H), W.E.udt, W.E.P, W.TT,
                          np.concatenate(dz), off, ms.PROBE_EPS)
        fw = W.E.forward(W.E.start_state(S), H, danger=dz, terrain=W.TT, max_events=1, claw=False)
        if i >= 0:
            n_probe += 1
            assert fw.count(H) > 0
    assert n_probe > 10
    assert ev.cfg.exit_probe


def test_tick_check_and_the_per_frame_check(W):
    sit = ms.Situation(_ground(W, C - 9.0), [_obs("Idle", C, j=8)], {1: cm.Memory()}, name="far hook")
    S = ms.Searcher(W, ms.Cfg(cap_s=3.0, depth=2, pass2_after=6))
    S.vclock = 0.01
    r = S.decide(sit)
    assert r.ev is not None and r.ev.safe
    ok, bad, _ = S.ev.tick_check(sit, r.plan)
    assert ok, bad                                   # the full check agrees with the evaluation
    tc = ms.TickCheck(r.ev)
    nom = r.ev.nominal
    for n in range(0, min(nom.k_end, 30)):
        okn, left, _ = tc.check(n, nom.tr.pos[n], ms.observe_branch(sit, nom.branch, n))
        assert okn and left >= 0
    obs = ms.observe_branch(sit, nom.branch, 5)
    for o in obs:
        o.x += 1.0                                   # the Clapper 1 u away from every outcome: not consistent
    assert not tc.check(5, nom.tr.pos[5], obs)[0]


def test_lazy_second_pass_decides(W):
    sit = _sits(W)[2]
    for after in (0, 4):
        S = ms.Searcher(W, ms.Cfg(cap_s=2.0, depth=2, pass2_after=after))
        S.vclock = 0.01
        r = S.decide(sit)
        assert r.ev is not None and r.n_cand > 5
        assert any(str(m[1]).startswith("passes2") for m in S.marks) == (after > 0)


def test_parallel_pass_equals_the_pass(W):
    """env_jit.forward_par (each frame's per-parent work on threads, the merge in the parents' order, the clusters
    finalized in parallel) gives forward's arrays bit for bit."""
    names = ["cl_off", "cl_y", "cl_ylo", "cl_vy", "cl_cond", "cl_mode", "cl_phase", "cl_iv0", "cl_ivn", "IV", "pc_cl",
             "pc_par", "pc_cand", "pc_lo", "pc_hi", "pc_dlo", "pc_dhi", "stats", "flags"]
    for sit in _sits(W):
        S = ms.Searcher(W, ms.Cfg())
        rt = S.root(sit)
        for (ne, H) in S.cfg.passes:
            dz = ms._union_danger(rt.pred, 0, H, True, None)
            st = W.E.start_state(rt.S)
            a = W.E.forward(st, H, danger=dz, terrain=W.TT, max_events=ne, claw=False)
            b = W.E.forward(st, H, danger=dz, terrain=W.TT, max_events=ne, claw=False, par=4)
            for nm in names:
                assert np.array_equal(getattr(a, nm), getattr(b, nm)), nm


def test_background_pass_and_threads_decide(W):
    sit = _sits(W)[1]
    S = ms.Searcher(W, ms.Cfg(cap_s=1.0, depth=2, pass2_after=6, pass2_bg=True, fwd_threads=4, reuse_root=True))
    r = S.decide(sit)
    assert r.ev is not None and r.ev.safe and any(str(m[1]).startswith("passes2") for m in S.marks)
