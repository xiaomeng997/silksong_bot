"""Map v2 A1_n tables stage T4: the two verifiers' findings on T1 - T3, fixed (HANDOFF 'Task map2 - A1_n recursive
tables - stage T4'): the merge key with lane 0's extra air velocity, the dominance filter / merge with the horizontal
state (a forced dash's twins), no hidden jump press at a pass's start and the witness's written press, the up slash
at the ceiling, the free attack holding back a queued dash, the attack in the ground dash unmodelled, the search's
background passes stopped, the long pass's prediction, the library's fixed room, the flat layer's validity, the
table view's steady states, the witness's miss checked."""
from __future__ import annotations

import threading
import time

import numpy as np
import pytest

from ssbot.knowledge import kinematics as km
from ssbot.map2 import env_jit as ej
from ssbot.map2 import envelope as env
from ssbot.map2 import search as ms
from ssbot.map2 import strike as sk
from ssbot.map2 import tables as tb
from ssbot.tools import t1_tables as t1

B_J, B_A, B_D, B_L, B_R, B_UP = km.B_JUMP, km.B_ATTACK, km.B_DASH, km.B_LEFT, km.B_RIGHT, km.B_UP


@pytest.fixture(scope="module")
def W():
    w = ms.World()
    lib = tb.Lib(claw=False, terrain="arena")
    lib.mark()
    w.__dict__["_lib"] = lib
    return w


def _ground(W, x=30.0, alpha=0.5, facing=1):
    return km.initial_state(W.params, x, sk.FLOOR + sk.FOOT, ground=True, alpha=alpha, facing=facing)


def _roll(W, S, masks):
    return km.rollout(S, np.asarray(masks, np.int64)[None], W.params, W.terr)


def _contained(fw, cen, tol=1e-6):
    """The largest distance of a path's centres [T + 1, 2] from the pass's rows of their frame (0: inside)."""
    worst = 0.0
    for t in range(cen.shape[0]):
        g, x0, x1, y0, y1 = fw.frame_rows(t)
        x, y = cen[t]
        ok = (np.abs(y1 - y) <= tol) & (x0 - tol <= x) & (x <= x1 + tol)
        if ok.any():
            continue
        same = np.abs(y1 - y) <= tol
        d = float(np.min(np.maximum(x0[same] - x, x - x1[same]))) if same.any() else np.inf
        worst = max(worst, d)
    return worst


def _seq(spec, T):
    m = np.zeros(T, dtype=np.int64)
    cur, d = 0, dict(spec)
    for t in range(T):
        cur = d.get(t + 1, cur)
        m[t] = cur
    return m


# ---- the merge key: lane 0's extra air velocity (the verifiers' exactness finding 2 / 5) ------------------------

def test_key_holds_lane0_extra_velocity(W):
    """Two clusters equal but for lane 0's left extra air velocity (the sprint jump's cancel: 5 / s) and its decay
    have different keys (before T4 the key was lane 1's alone: they merged, the merged lane 0 kept the first child's
    decay); one lane's own vkey writes its own values in lane 0's slots."""
    P = W.E.P
    S = km.initial_state(W.params, 30.0, 8.0, ground=False, vy=-2.0, facing=-1)
    a, b = S.copy(), S.copy()
    a[km.XVX], a[km.XVXD] = -24.722, 5.0
    b[km.XVX], b[km.XVXD] = -31.289, 0.0
    cu = np.array([-1.0, 0, 0, 0, 0, 0, 0])
    ka, kb, k1 = np.empty(ej.NKEY), np.empty(ej.NKEY), np.empty(ej.NKEY)
    ej.vkey(S, cu, P, True, k1)                # lane 1 without an extra
    ka[:] = k1
    kb[:] = k1
    ej.key_l0(ka, a, P)
    ej.key_l0(kb, b, P)
    assert not ej.keq(ka, kb) and not ej.keq(ka, k1)
    assert ej.keq_lanes(ka, kb)                # (the vertical agrees: not a lane divergence)
    L = np.stack([a, S])
    L2 = np.stack([b, S])
    tb.rel_x(L), tb.rel_y(L), tb.rel_x(L2), tb.rel_y(L2)
    o1, o2 = np.empty(tb.NIDK), np.empty(tb.NIDK)
    tb.ident(L, cu, P, False, -1.0, o1)
    tb.ident(L2, cu, P, False, -1.0, o2)
    assert not ej.keq(o1, o2)                  # (the tables' node identity too)


def test_sprint_jump_left_cancel_contained(W):
    """A ground dash left, the sprint jump with right held against its 18 u/s, the key let go: the extra velocity
    left (5 / s) on lane 0 only - every release frame x {none, left, right} after it inside the engine's and the
    tables' <= 1 event pass (the verifiers' case escaped 0.03 - 0.24 u)."""
    S0 = _ground(W, 34.0, 0.4, facing=-1)
    S = _roll(W, S0, [B_D | B_L, B_D | B_L]).final[:, 0].copy()
    T = 60
    fe = W.envelope(S, T, None, 1)
    ft = W.envelope(S, T, None, 1, tables=True)
    worst_e = worst_t = 0.0
    seen_extra = False
    for rel in range(11, 50, 3):
        for after in (0, B_L, B_R):
            m = _seq([(1, B_D | B_R), (10, B_J | B_D | B_R), (rel, B_J | B_D | after)], T)
            r = _roll(W, S, m)
            seen_extra |= bool(np.any(r.final[km.XVX] < -W.E.P[km.P_RUN]))
            worst_e = max(worst_e, _contained(fe, r.centre[0]))
            worst_t = max(worst_t, _contained(ft, r.centre[0]))
    assert worst_e == 0.0 and worst_t == 0.0


# ---- the dominance filter and the merge: the horizontal state (finding 3) -----------------------------------

def test_hcover_and_merge_h():
    """A forced-left child and its forced-right twin (equal vertical keys): neither covers the other's x set, so the
    dominance filter keeps both; merged, the lanes take the extreme velocity / held direction / facing."""
    a = np.zeros((2, km.K))
    b = np.zeros((2, km.K))
    a[:, km.MOVE], a[:, km.FACE], a[:, km.VX] = -1.0, -1.0, -8.25
    b[:, km.MOVE], b[:, km.FACE], b[:, km.VX] = 1.0, 1.0, 8.25
    assert not ej.hcover(a, b) and not ej.hcover(b, a)
    c = a.copy()
    assert ej.hcover(a, c)                     # (an identical child: dropped as before)
    ej.merge_h(c, b)
    assert (c[0, km.MOVE], c[1, km.MOVE], c[0, km.FACE], c[1, km.FACE]) == (-1.0, 1.0, -1.0, 1.0)
    assert (c[0, km.VX], c[1, km.VX]) == (-8.25, 8.25)


def test_forced_direction_in_the_key(W):
    """The held direction is a key slot when both lanes hold the same one (a dash forced left vs its right twin: two
    clusters for that frame, not one hull claiming the 0.33 u between them); the free keys (lane 0 left, lane 1 right)
    give 0."""
    P = W.E.P
    S = km.initial_state(W.params, 30.0, 8.0, ground=False, vy=-2.0, facing=1)
    cu = np.array([-1.0, 0, 0, 0, 0, 0, 0])
    keys = {}
    for name, (m0, m1) in {"left": (-1.0, -1.0), "right": (1.0, 1.0), "free": (-1.0, 1.0)}.items():
        a, b = S.copy(), S.copy()
        a[km.MOVE], b[km.MOVE] = m0, m1
        k = np.empty(ej.NKEY)
        ej.vkey(b, cu, P, True, k)
        ej.key_l0(k, a, P)
        keys[name] = k
    assert keys["left"][ej.K_MOVEF] == -1.0 and keys["right"][ej.K_MOVEF] == 1.0 and keys["free"][ej.K_MOVEF] == 0.0
    assert not ej.keq(keys["left"], keys["right"])


def test_queued_dash_twins_contained(W):
    """Airborne just over the floor with the air dash used and the dash held and queued: the landing restores the
    dash, a jump press with the dash and right held - the queued dash fires later in the air (the jump's dash
    cooldown first); every frame's x inside the <= 1 event pass, both ways."""
    worst = 0.0
    for d in (B_R, B_L):
        S = km.initial_state(W.params, 30.0, sk.FLOOR + sk.FOOT + 0.6, ground=False, vy=-3.0, facing=1)
        S[km.AIRDASHED] = 1.0
        S[km.PREV] = float(B_D)
        S[km.DQ] = 0.0
        T = 20
        fe = W.envelope(S, T, None, 1)
        ft = W.envelope(S, T, None, 1, tables=True)
        for jf in range(3, 10):
            m = _seq([(1, B_D | d), (jf, B_J | B_D | d)], T)
            r = _roll(W, S, m)
            worst = max(worst, _contained(fe, r.centre[0]), _contained(ft, r.centre[0]))
    assert worst == 0.0


# ---- the hidden jump press (finding 4) ------------------------------------------------------------------------

def test_no_hidden_press_at_the_start(W):
    """A jump held without a press (CB_JH) needs an earlier frame for its press: never a pass's first frame (the
    engine and the tables alike)."""
    for S in (km.initial_state(W.params, 30.0, 8.0, ground=False, vy=v, facing=1) for v in (-3.0, 2.0, 9.0)):
        for tables in (False, True):
            fw = W.envelope(S, 4, None, 1, tables=tables)
            p1 = fw.pc_cl < fw.cl_off[2]
            assert not np.any((fw.pc_cand[p1] & ej.CB_JH) != 0)


def test_dash_with_jump_really_held_contained(W):
    """A start holding jump (no hang left: holding it alone does nothing) - the dash pressed with it held from frame 1
    on, and the umbrella's dash cancel with jump held whose queued dash fires next: inside the engine's and the
    tables' passes, the executable family too (the jump is held for real - no hidden press, no attack)."""
    worst = 0.0
    S = km.initial_state(W.params, 30.0, 9.0, ground=False, vy=-2.0, facing=1)
    S[km.PREV] = float(B_J)
    T = 16
    for ex in (False, True):
        fe = W.envelope(S, T, None, 1, exec_only=ex)
        ft = W.envelope(S, T, None, 1, tables=True, exec_only=ex)
        for f in range(1, 6):
            for d in (B_L, B_R):
                m = _seq([(1, B_J), (f, B_J | B_D | d)], T)
                r = _roll(W, S, m)
                worst = max(worst, _contained(fe, r.centre[0]), _contained(ft, r.centre[0]))
    assert worst == 0.0


def test_witness_writes_the_hidden_press(W):
    """Every witness's keys, rolled as they are (no hidden previous key), follow its cluster's heights: a CB_JH frame
    gets its press written (an attack before, the jump pressed in its recovery) or the witness reports the miss."""
    S = km.initial_state(W.params, 30.0, 9.0, ground=False, vy=8.0, facing=1)
    fw = W.envelope(S, 24, None, 1)
    checked = jh = 0
    for t in (12, 18, 24):
        g, x0, x1, y0, y1 = fw.frame_rows(t)
        for i in range(0, len(g), max(1, len(g) // 12)):
            x = 0.5 * (x0[i] + x1[i])
            w = fw.witness(t, float(x), float(y1[i]))
            if w is None:
                continue
            checked += 1
            jh += int(np.any((w["vmask"] & ej.CB_JH) != 0))
            r = ej.ref_rollout(S.copy(), np.array([-1.0, 0, 0, 0, 0, 0, 0]), w["masks"], W.E.udt, W.E.P, W.TT,
                               np.zeros((t + 1, 2)), np.zeros(t + 1, np.int64))
            assert abs(w["miss_y"]) < 1e-6 or any(k is None for (_, k) in w["hidden"])
    assert checked > 10


# ---- the up slash at the ceiling (finding 6) ------------------------------------------------------------------

def test_up_slash_at_the_ceiling_contained(W):
    """A Clawline bounce under the arena's ceiling: an up slash pressed while rising meets the ceiling (RecoilDown:
    the rise stops) - inside the engine's and the tables' <= 1 event pass (before T4 no cluster at those heights)."""
    S, _ = env.canonical(W.params, "A2", 0, 0, "claw", False)
    dy = 10.0 - S[km.PY]
    for r_ in (km.PY, km.QY, km.SY, km.RY0):
        S[r_] += dy
    T = 30
    fe = W.envelope(S, T, None, 1)
    ft = W.envelope(S, T, None, 1, tables=True)
    thunked = 0
    for k in (2, 4, 6, 8):
        m = np.zeros(T, dtype=np.int64)
        m[k] |= B_A | B_UP
        r = _roll(W, S, m)
        thunked += int(r.final[km.ATK_KIND, 0] < 0)
        assert _contained(fe, r.centre[0]) == 0.0
        assert _contained(ft, r.centre[0]) == 0.0
    assert thunked >= 2


# ---- the ground dash's attack: unmodelled (finding 7) -------------------------------------------------------

def test_ground_dash_attack_is_unmodelled(W):
    """An attack pressed in the ground dash (the Wanderer's dash attack at its end into the sprint): the reference
    rollout drops it like one in the ground sprint, and the press rule flags it."""
    from ssbot.map2 import press
    S = _ground(W, 30.0, 0.5)
    m = np.array([B_D | B_R, B_D | B_R, B_D | B_R | B_A, B_D | B_R, B_D | B_R, B_D | B_R], np.int64)
    xy = np.zeros((7, 2))
    md = np.zeros(7, np.int64)
    ej.ref_rollout(S.copy(), np.array([-1.0, 0, 0, 0, 0, 0, 0]), m, W.E.udt, W.E.P, W.TT, xy, md)
    m2 = m.copy()
    m2[2] &= ~B_A
    xy2 = np.zeros((7, 2))
    ej.ref_rollout(S.copy(), np.array([-1.0, 0, 0, 0, 0, 0, 0]), m2, W.E.udt, W.E.P, W.TT, xy2, md)
    assert np.array_equal(xy, xy2)
    kt = press.trace(W, S, m)
    assert press.unmodelled(kt, m) == [3]


# ---- the search: the background passes, the long pass, the library's room (search findings 1, 2, 7) --------

def test_stop_abandons_a_pass(W):
    """A pass with its stop flag set from another thread returns None (the engine and the tables)."""
    S = km.initial_state(W.params, 30.0, 8.0, ground=False, vy=2.0, facing=1)
    for tables in (False, True):
        stop = np.ones(1, dtype=np.int64)
        assert W.envelope(S, 40, None, 2, tables=tables, stop=stop) is None
        stop[0] = 0
        assert W.envelope(S, 10, None, 1, tables=tables, stop=stop) is not None


def test_searcher_stops_its_background_passes(W):
    """Searcher._stop_bg: a background pass not joined is cancelled / abandoned and the library's lock is free."""
    lib = W.table_lib()
    cfg = ms.Cfg(tables=True, passes=((1, 20), (3, 60)))
    s = ms.Searcher(W, cfg)
    S = km.initial_state(W.params, 30.0, 8.0, ground=False, vy=2.0, facing=1)

    class _Pred:
        branches = []
        T = 200
    node = ms.Node(ms.Plan([], "prim"), 0, S, _Pred(), None, 0, 0)
    futs = s.passes(node, (1,), bg=True)
    time.sleep(0.05)
    assert s._stop_bg() >= 0
    for f in futs:
        try:
            assert f.result(timeout=60) is None or f.done()
        except Exception:                      # (cancelled before it started)
            pass
    assert lib.lock.acquire(timeout=5)
    lib.lock.release()


def test_long_pass_prediction_horizon():
    """The longest approach pass sets the predictions' horizon (the long pass saw no danger past ~75 f)."""
    assert ms.Cfg().h_pass == 60
    assert ms.Cfg(passes=((1, 60), (2, 30), (1, 120, 60))).h_pass == 120


def test_fixed_library_never_reallocates(W):
    """A fixed library (the search's) raises TablesFull instead of doubling its arrays; World.envelope then takes
    the engine's pass."""
    lib = tb.Lib(claw=False, terrain="arena", cap_nodes=64, cap_edges=256, cap_cls=64, cap_inst=64)
    lib.fixed = True
    S = km.initial_state(W.params, 30.0, 8.0, ground=False, vy=2.0, facing=1)
    with pytest.raises(tb.TablesFull):
        lib.forward(S, 30, None, floor=True, maxev=2, dash=True)
    w2 = ms.World()
    w2.__dict__["_lib"] = lib
    fw = w2.envelope(S, 30, None, 2, tables=True)
    assert fw is not None and not hasattr(fw, "lib_stats")
    assert lib.room == 64


# ---- the flat layer's validity, the table view (findings 10, 12) ---------------------------------------------

def test_flat_contains_tolerance_and_patterns(tmp_path):
    """Tables.contains takes a height on a bin boundary within its tolerance; steps_pattern is the chain's own; a
    start at another physics phase of the class is refused (valid_until -1)."""
    import json
    E = env.Engine(env.load_params(True), claw=False)
    P = E.P
    dt, fdt = float(np.float32(E.udt)), float(P[km.P_FDT])
    a = env.steps_pattern(0.0, 12, dt, fdt)
    b = env.steps_pattern(0.12, 12, dt, fdt)
    assert len(a) == 12 and a != b            # (alpha = c / 6 is a step-pattern boundary: dt / fdt < 5 / 6)
    arrs = {"_meta": np.array(json.dumps({"T": 1, "q": 0.05, "alpha": {"k": 0.0}, "free": {"k": True}, "dt": dt,
                                          "fdt": fdt})),
            "k|all|off": np.array([0, 1, 2]), "k|all|bin": np.array([0, -1], np.int32),
            "k|all|x": np.array([[-0.1, 0.1], [-0.2, 0.2]], np.float32)}
    p = tmp_path / "flat.npz"
    np.savez(p, **arrs)
    tab = env.Tables(p)
    assert tab.contains("k", "all", 1, 0.0, -1.8e-15)
    S = km.initial_state(env.load_params(True), 30.0, 20.0, ground=False)
    S[km.ALPHA] = 0.12
    assert tab.valid_until("k", S, P) == (-1 if env.steps_pattern(0.12, 1, dt, fdt) != a[:1] else 1)


def test_kinds_need_the_keys_up(W):
    """A node in the plain fall with jump held is not A1 / A1~ (a jump press there would be a hold: no umbrella)."""
    lib = tb.Lib(claw=False, terrain="arena")
    S = km.initial_state(W.params, 30.0, 8.0, ground=False, vy=0.0, facing=1)
    for held in (0, B_J):
        S2 = S.copy()
        S2[km.PREV] = float(held)
        st, L, absy, dashed = lib.start_lanes(S2)
        lib.node_of(L, st.cu, absy)
    k = lib.kinds()
    assert k[0] in (tb.K_A1, tb.K_A1OFF) and k[1] not in (tb.K_A1, tb.K_A1OFF)


# ---- the witness's miss in the search (finding 8) ------------------------------------------------------------

def test_realize_rejects_a_missing_witness(W):
    s = ms.Searcher(W, ms.Cfg())
    assert s._witness_ok({"miss_x": 0.05, "miss_y": 0.0})
    assert not s._witness_ok({"miss_x": 0.2, "miss_y": 0.0})
    assert not s._witness_ok({"miss_x": 0.0, "miss_y": 0.3})
