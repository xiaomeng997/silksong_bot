"""Map v2 stage T2: the air dash as the bridge (tables.Lib.forward(dash=True), ssbot.map2.bridge) against the M1
engine with the air dash; the landing's refill (HERO2 H2_LAND_DASH); the two engine keys T2 fixed; the backward sets;
the shared dash bundle."""
from __future__ import annotations

import numpy as np
import pytest

from ssbot.knowledge import kinematics as km
from ssbot.map2 import bridge as br
from ssbot.map2 import env_jit as ej
from ssbot.map2 import envelope as env
from ssbot.map2 import tables as tb
from ssbot.tools import m1_envelope as m1
from ssbot.tools import t1_tables as t1


@pytest.fixture(scope="module")
def lib_s():
    return tb.Lib(claw=False, terrain="arena")


@pytest.fixture(scope="module")
def lib():
    return tb.Lib()


def _ground(lib, x=30.0, alpha=0.5):
    return km.initial_state(lib.params, x, tb.FLOOR_TOP + lib.params.foot, ground=True, alpha=alpha)


def test_dash_chain_equals_engine_free(lib):
    """A1 at rest in free space, every event, 12 frames: the chain with the bridge = the engine's exact pass WITH the
    air dash (the dash family's 10^4 - 10^5 clusters)."""
    S, _ = env.canonical(lib.params, "A1", 0, 2, "", False)
    T = 12
    fe = lib.eng.forward(lib.eng.start_state(S), T, opts=0)
    ft = lib.forward(S, T, dash=True)
    r = t1.compare(fe, ft, T)
    assert r["ok"], r
    assert np.any(ft.ad[int(ft.cl_off[T]):int(ft.cl_off[T + 1])] > 0)


@pytest.mark.parametrize("mev,T", [(1, 40), (2, 24)])
def test_dash_chain_equals_engine_ground_danger(lib_s, mev, T):
    """From the ground (jump, air dash, landing, the refill) with the search's library and random danger."""
    rng = np.random.default_rng(3)
    for x in (22.0, 35.0):
        S = _ground(lib_s, x)
        dz = m1.random_danger(rng, S, T, lib_s.hh)
        fe = lib_s.eng.forward(lib_s.eng.start_state(S), T, terrain=lib_s.terr, opts=0, max_events=mev, claw=False,
                               tf8=False, danger=dz)
        ft = lib_s.forward(S, T, floor=True, maxev=mev, danger=dz, dash=True)
        r = t1.compare(fe, ft, T)
        assert r["ok"], r


def test_landing_restores_the_air_dash():
    """HERO2 H2_LAND_DASH: an air dash, a landing, a jump - the second air dash dashes (BackOnGround's airDashed =
    false); without the bit it does not."""
    base = km.HeroParams.load(env.PARAMS_PATH)
    on = km.hero2(base, on=True)
    off = km.HeroParams.from_json(dict(on.to_json(), hero2=int(on.hero2) & ~km.H2_LAND_DASH))
    terr = km.Terrain2D.from_boxes([(-1.0e4, 1.0, 1.0e4, tb.FLOOR_TOP)])
    J, D, R = km.B_JUMP, km.B_DASH, km.B_RIGHT
    m = [0] * 5 + [J] * 6 + [0] * 3 + [D | R] + [R] * 40 + [0] * 10 + [J] * 6 + [0] * 3 + [D | R]
    masks = np.array(m, dtype=np.int64)[None]
    res = {}
    for name, prm in (("on", on), ("off", off)):
        S = km.initial_state(prm, 20.0, tb.FLOOR_TOP + prm.foot, ground=True, alpha=0.5)
        x = km.rollout(S, masks, prm, terr).final[:, 0]
        res[name] = (int(x[km.MODE]), float(x[km.AIRDASHED]))
    assert res["on"][0] == km.M_DASH and res["on"][1] == 1.0
    assert res["off"][0] != km.M_DASH


def test_vkey_keeps_the_sprint_loop_timer_under_the_attack_gate(lib):
    """The air sprint's loop (phase 1) keeps its timer in the key while the Attack Cancel's gate still reads it."""
    P = lib.P
    x = km.initial_state(lib.params, 0.0, 20.0, ground=False)
    x[km.MODE] = km.M_SPRINT
    x[km.PHASE] = 1.0
    cu = np.array([-1.0, 0, 0, 0, 0, 0, 0])
    k1, k2 = np.empty(ej.NKEY), np.empty(ej.NKEY)
    x[km.MODE_T] = 0.02
    ej.vkey(x, cu, P, False, k1)
    x[km.MODE_T] = 0.05
    ej.vkey(x, cu, P, False, k2)
    assert not ej.keq(k1, k2)
    x[km.MODE_T] = 0.3
    ej.vkey(x, cu, P, False, k1)
    x[km.MODE_T] = 0.5
    ej.vkey(x, cu, P, False, k2)
    assert ej.keq(k1, k2)


def test_vkey_keeps_the_queues_while_a_dash_can_start(lib):
    """Normal control in the air with the air dash unused: the jump queue is a key (a dash carries it into the
    sprint); with the dash used it is not."""
    P = lib.P
    x = km.initial_state(lib.params, 0.0, 20.0, ground=False)
    cu = np.array([-1.0, 0, 0, 0, 0, 0, 0])
    k1, k2 = np.empty(ej.NKEY), np.empty(ej.NKEY)
    x[km.JBUF] = 0.05
    ej.vkey(x, cu, P, False, k1)
    x[km.JBUF] = 0.0
    ej.vkey(x, cu, P, False, k2)
    assert not ej.keq(k1, k2)
    x[km.AIRDASHED] = 1.0
    x[km.JBUF] = 0.05
    ej.vkey(x, cu, P, False, k1)
    x[km.JBUF] = 0.0
    ej.vkey(x, cu, P, False, k2)
    assert ej.keq(k1, k2)


def test_backward_holds_the_start_and_a_witness(lib_s):
    """A goal at the pass's end (one cluster's interval end): its backward set holds her start, and the frame-0 .. T
    tube holds the witness path's positions."""
    S = _ground(lib_s, 30.0)
    T = 30
    ft = lib_s.forward(S, T, floor=True, maxev=2, dash=True)
    gs = list(ft.frame(T))
    g = max(gs, key=lambda q: ft.cl_y[q])
    a, b = ft.intervals(g)[-1]
    bk = br.backward(ft, [g], [b], [b])
    assert bk.reached()
    w = ft.witness(T, float(b), float(ft.cl_y[g]))
    assert w is not None
    for t, gg in enumerate(w["clusters"]):
        iv = bk.intervals(gg)
        assert len(iv) and np.any((iv[:, 0] - 1e-6 <= w["xpath"][t]) & (w["xpath"][t] <= iv[:, 1] + 1e-6)), t
    # a goal out of reach: nothing
    bk2 = br.backward(ft, [g], [b + 50.0], [b + 60.0])
    assert not bk2.reached()


def test_bundle_shared_by_a1_n(lib_s):
    """The dash bundle of A1_n (the same physics-step pattern): the same ends (dt, dy, x offsets) whatever n (the
    dash zeroes vy every step)."""
    rels = []
    for n in (6, 12, 24):
        S, _ = env.canonical(lib_s.params, "A1", n, 0, "", False)
        b = br.bundle(lib_s, S)
        assert b["press"] and b["ends"]
        rels.append(sorted((k[1], k[2], str(v)) for k, v in br.bundle_relative(b).items()))
    assert rels[0] == rels[1] == rels[2]


def test_window_shape_hit_interval_matches_the_judge():
    """wshape.hit_interval (the polygon's extent in the box's slab) = the x set where clapper.poly_box_hit meets the
    box (bisection of the judge at random boxes / heights, both alternations and facings)."""
    from ssbot.map2 import clapper as cm, strike as sk, wshape as wsh
    rng = np.random.default_rng(5)
    for _ in range(300):
        x0, y0 = rng.uniform(-3, 3), rng.uniform(-4, 1)
        box = (x0, y0, x0 + rng.uniform(0.2, 3), y0 + rng.uniform(0.2, 3))
        for face in (-1, 1):
            for poly in sk.slash_polys(face):
                iv = wsh.hit_interval(poly, box, 0.0)
                xs = np.linspace(-8, 8, 801)
                hit = np.array([cm.poly_box_hit(poly + (x, 0.0), box) for x in xs])
                if iv is None:
                    assert not hit.any()
                    continue
                inside = (xs > iv[0] + 1e-9) & (xs < iv[1] - 1e-9)
                assert np.array_equal(hit[inside], np.ones(inside.sum(), bool))
                outside = (xs < iv[0] - 1e-9) | (xs > iv[1] + 1e-9)
                assert not hit[outside].any()


@pytest.mark.parametrize("dash", [False, True])
def test_dash_used_start_equals_engine(lib_s, dash):
    """A start with the air dash used (the T1 chain's lists with it used - du 3 -, the merge classes with it used:
    the engine's key drops the queues then): exact without and with the bridge (a landing restores the dash)."""
    for kind, ph, var in (("A1", 4, ""), ("A3", 3, "N")):
        S, _ = env.canonical(lib_s.params, kind, ph, 1, var, True)
        S = S.copy()
        dy = tb.FLOOR_TOP + lib_s.params.foot + 3.0 - S[km.PY]
        for f in (km.PY, km.QY, km.SY):
            S[f] += dy
        S[km.JBUF] = 0.05
        fe = lib_s.eng.forward(lib_s.eng.start_state(S), 30, terrain=lib_s.terr, max_events=2, claw=False, tf8=False,
                               opts=0 if dash else ej.OPT_NO_ADASH)
        ft = lib_s.forward(S, 30, floor=True, maxev=2, dash=dash)
        r = t1.compare(fe, ft, 30)
        assert r["ok"], (kind, r)


def test_vkey_keeps_a_stale_jump_queue_while_jump_can_be_held_again(lib):
    """Normal control in the air, jump up: a queued jump within its window is a key over the terrain (the candidate
    CB_JH holds jump again without a press and the queue fires on landing)."""
    P = lib.P
    x = km.initial_state(lib.params, 0.0, 5.0, ground=False)
    cu = np.array([-1.0, 0, 0, 0, 0, 0, 0])
    k1, k2 = np.empty(ej.NKEY), np.empty(ej.NKEY)
    x[km.PREV] = 0.0
    x[km.JQ] = 1.0
    ej.vkey(x, cu, P, True, k1)
    x[km.JQ] = -1.0
    ej.vkey(x, cu, P, True, k2)
    assert not ej.keq(k1, k2)
