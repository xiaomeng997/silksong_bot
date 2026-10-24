"""Map v2 stage T1: the A1_n no-dash tables (ssbot.map2.tables) against the M1 engine with the air dash off."""
from __future__ import annotations

import numpy as np
import pytest

from ssbot.knowledge import kinematics as km
from ssbot.map2 import envelope as env
from ssbot.map2 import env_jit as ej
from ssbot.map2 import tables as tb
from ssbot.tools import m1_envelope as m1
from ssbot.tools import t1_tables as t1


@pytest.fixture(scope="module")
def lib():
    return tb.Lib()


@pytest.fixture(scope="module")
def lib_s():
    return tb.Lib(claw=False, terrain="arena")


def test_chain_equals_engine_free_space(lib):
    """A1 at rest, free space, every event (no limit): the same heights (bit for bit) and x sets per frame and end
    condition as the engine's exact pass with OPT_NO_ADASH."""
    S, _ = env.canonical(lib.params, "A1", 0, 3, "", False)
    T = 16
    fe = lib.eng.forward(lib.eng.start_state(S), T, opts=ej.OPT_NO_ADASH)
    ft = lib.forward(S, T)
    r = t1.compare(fe, ft, T)
    assert r["ok"], r


def test_chain_equals_engine_floor_float(lib):
    """The umbrella's float over the floor (its instances near the floor), every event, 14 frames."""
    S, _ = env.canonical(lib.params, "A3", 4, 1, "R", False)
    S = S.copy()
    S[km.PY] = tb.FLOOR_TOP + lib.params.foot + 2.2      # 2.2 u over the floor: the floor instances come in
    S[km.QY] = S[km.SY] = S[km.PY]
    T = 14
    fe = lib.eng.forward(lib.eng.start_state(S), T, terrain=lib.terr, opts=ej.OPT_NO_ADASH)
    ft = lib.forward(S, T, floor=True)
    r = t1.compare(fe, ft, T)
    assert r["ok"], r


def test_chain_equals_engine_ground_event_limit_danger(lib_s):
    """The search's configuration (no Clawline, the floor and the ceiling), standing on the floor, <= 2 events, 30
    frames, random moving danger boxes: the same clusters (the engine's merges, events kept per cluster)."""
    S, _ = env.canonical(lib_s.params, "G", 0, 2, "", False)
    rng = np.random.default_rng(3)
    for k in range(3):
        dz = m1.random_danger(rng, S, 30, lib_s.hh)
        fe = lib_s.eng.forward(lib_s.eng.start_state(S), 30, terrain=lib_s.terr, opts=ej.OPT_NO_ADASH,
                               max_events=2, claw=False, tf8=False, danger=dz)
        ft = lib_s.forward(S, 30, floor=True, maxev=2, danger=dz)
        r = t1.compare(fe, ft, 30)
        assert r["ok"], (k, r)


def test_save_load_roundtrip(tmp_path):
    """A small library (two levels from A1 at rest) saved and loaded: the same nodes, the same chain."""
    lib = tb.Lib(cap_nodes=1 << 10, cap_edges=1 << 12)
    S, _ = env.canonical(lib.params, "A1", 0, 0, "", False)
    st, L, absy, dashed = lib.start_lanes(S)
    lib.node_of(L, st.cu, absy)
    lib.close(0, 1)
    p = lib.save(tmp_path / "t.npz")
    lib2 = tb.Lib.load(p)
    assert lib2.n_nodes == lib.n_nodes and lib2.n_edges == lib.n_edges
    a = lib.forward(S, 10)
    b = lib2.forward(S, 10)
    assert t1.compare(a, b, 10)["ok"]


def test_follow_contains_random_keys(lib):
    """Random key sequences without the air dash (presses / holds of every key, Clawline taps), 90 frames, followed
    through the graph: every frame inside a lineage."""
    S, _ = env.canonical(lib.params, "A2", 0, 0, "claw", False)
    rng = np.random.default_rng(5)
    T = 90
    masks = m1.random_masks(rng, 40, T, claw=True)
    st, L, absy, dashed = lib.start_lanes(S)
    n0 = lib.node_of(L, st.cu, absy)
    out = np.zeros((40, 3))
    xy = np.zeros((40, T + 1, 2))
    while tb.follow(st.L[1].copy(), st.cu.copy(), n0, masks, lib.TP_free, 1e-6, *t1._lib_args(lib), out, xy) == -2:
        lib._grow()
    assert np.all(out[:, 0] < 0), out[out[:, 0] >= 0]


def test_a1_recursion(lib):
    """A1_n: the going-on edge of a physics step leads one lattice step on, widened by one run step each side; a frame
    without a step keeps the node."""
    S, _ = env.canonical(lib.params, "A1", 0, 0, "", False)
    st, L, absy, dashed = lib.start_lanes(S)
    n = lib.node_of(L, st.cu, absy)
    # the canonical start's own lanes (no key yet) -> A1_0 with the lanes' keys after one frame without a step
    n = int(lib.EI[[e for e in lib.edges(n, 0.0, 0) if lib.EF[e, tb.EF_NEV] == 0][0], tb.EI_CH])
    run = lib.P[km.P_RUN] * lib.P[km.P_FDT]
    lat = lib.lattice()
    for k in range(5):
        e1 = [e for e in lib.edges(n, 0.0, 1) if lib.EF[e, tb.EF_NEV] == 0][0]
        e0 = [e for e in lib.edges(n, 0.0, 0) if lib.EF[e, tb.EF_NEV] == 0][0]
        assert lib.EI[e0, tb.EI_CH] == n and lib.EF[e0, tb.EF_DLO] == 0.0 and lib.EF[e0, tb.EF_DHI] == 0.0
        c = int(lib.EI[e1, tb.EI_CH])
        assert lib.NVY[c, tb.V_VY] == lat[k + 1]
        if k > 0:
            assert abs(lib.EF[e1, tb.EF_DLO] + run) < 1e-12 and abs(lib.EF[e1, tb.EF_DHI] - run) < 1e-12
        n = c
