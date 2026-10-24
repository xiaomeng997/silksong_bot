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


def test_follow_contains_shuttle_cancel(lib_s):
    """T1b: a ground dash held into the sprint, the sprint (shuttlecock) jump, an attack cancelling it in the air ->
    the extra air velocity of 18 u/s with ShuttleCockCancel's decay (5 / s): a member without a key outruns the run
    lane for several frames and the lane on its side must carry it (env_jit.xvx_extra with the lane's own decay; the
    first version used the attack cancel's for every extra: escapes of 0.03 - 0.3 u)."""
    S, _ = env.canonical(lib_s.params, "G", 0, 1, "", False)
    T = 50
    rows = []
    for a in (12, 14, 16):
        for c in (a + 9, a + 11, a + 13):
            for key in (0, km.B_RIGHT):
                m = [km.B_DASH | km.B_RIGHT] * a + [km.B_DASH | km.B_RIGHT | km.B_JUMP] * (c - a) + [key] * (T - c)
                m[c] |= km.B_ATTACK
                rows.append(m)
    masks = np.array(rows, np.int64)
    st, L, absy, dashed = lib_s.start_lanes(S, floor=True)
    n0 = lib_s.node_of(L, st.cu, absy)
    out = np.zeros((len(masks), 3))
    xy = np.zeros((len(masks), T + 1, 2))
    while tb.follow(st.L[1].copy(), st.cu.copy(), n0, masks, lib_s.TP, 1e-6, *t1._lib_args(lib_s), out, xy) == -2:
        lib_s._grow()
    assert np.all(out[:, 0] < 0), out[out[:, 0] >= 0]
    # the no-key members do pass the key-held ones (the extension matters)
    assert max(float(np.max(xy[2 * j, :, 0] - xy[2 * j + 1, :, 0])) for j in range(len(masks) // 2)) > 0.3


def test_follow_contains_claw_in_sprint_jump(lib):
    """T1b: the Clawline pressed in a sprint jump relinquishes control - ShuttleCockCancel leaves the extra air
    velocity, which decays through the block and moves a member without a key after control together with the
    HarpoonDashEnd residual drift (env_jit.lane_drift: the lanes bound their sum)."""
    S, _ = env.canonical(lib.params, "G", 0, 1, "", False)
    T = 80
    rows = []
    for a in (12, 15):
        for c in (a + 9, a + 12):
            for after in (0, km.B_RIGHT, km.B_LEFT):
                m = [km.B_DASH | km.B_RIGHT] * a + [km.B_DASH | km.B_RIGHT | km.B_JUMP] * (c - a) + [after] * (T - c)
                m[c] |= ej.B_CLAW
                rows.append(m)
    masks = np.array(rows, np.int64)
    st, L, absy, dashed = lib.start_lanes(S, floor=True)
    n0 = lib.node_of(L, st.cu, absy)
    out = np.zeros((len(masks), 3))
    xy = np.zeros((len(masks), T + 1, 2))
    while tb.follow(st.L[1].copy(), st.cu.copy(), n0, masks, lib.TP, 1e-6, *t1._lib_args(lib), out, xy) == -2:
        lib._grow()
    assert np.all(out[:, 0] < 0), out[out[:, 0] >= 0]
    # the press did cancel the sprint jump: after the block a member without a key does not keep 18 u/s
    x = st.L[1].copy()
    cu = st.cu.copy()
    strip, mp = 0, int(x[km.PREV])
    for t in range(12 + 9 + 1):                       # (rows[0]: a = 12, the press at frame index c = 21)
        strip, mp = tb.member_frame(x, cu, masks[0, t], mp, strip, lib.udt, lib.P, lib.TTg)
    assert x[km.SHUT] == 0.0 and x[km.XVX] == 18.0 and cu[ej.C_CJ] >= 0


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


def test_tables_growing_keep_both_edge_lists():
    """A library grown from tiny tables (every expansion may meet a full table): the event-limited chain still equals
    the engine (both edge lists of a node are committed together)."""
    lib = tb.Lib(cap_nodes=1 << 8, cap_edges=1 << 8, cap_cls=1 << 8, cap_inst=1 << 8, claw=False, terrain="arena")
    for kind, ph, var in (("A3", 6, "L"), ("G", 0, "")):
        S, _ = env.canonical(lib.params, kind, ph, 1, var, False)
        fe = lib.eng.forward(lib.eng.start_state(S), 40, terrain=lib.terr, opts=ej.OPT_NO_ADASH, max_events=1,
                             claw=False, tf8=False)
        ft = lib.forward(S, 40, floor=True, maxev=1)
        r = t1.compare(fe, ft, 40)
        assert r["ok"], (kind, r)
