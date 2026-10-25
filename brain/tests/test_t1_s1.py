"""Map v2 t1 stage S1 (HANDOFF 'S1 (side / up slash)'): the Wanderer's side and up slashes as map2 strike primitives,
behind search.Cfg.prims 'side' / 'up' and LiveCfg.prims_su (default off; off: the search and the bot as before) - the
primitive against V1's recorded presses (the fixture: C:/ssbot/data/m2_play/map2/t1/v1/fixture_presses.pkl), the press
rules (press.su_start), the contact on the previous frame's shape (strike.su_boxes), her nail recoil in simulate, the
search's windows / realizer, the live plumbing (the realizer's press, the re-anchoring)."""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pytest

from ssbot.knowledge import kinematics as km
from ssbot.map2 import brnum
from ssbot.map2 import clapper as cm
from ssbot.map2 import live as lv
from ssbot.map2 import press
from ssbot.map2 import search as ms
from ssbot.map2 import strike as sk

R, L, J, A, D, U, DS = km.B_RIGHT, km.B_LEFT, km.B_JUMP, km.B_ATTACK, km.B_DOWN, km.B_UP, km.B_DASH
FIXTURE = Path(r"C:\ssbot\data\m2_play\map2\t1\v1\fixture_presses.pkl")
C = 33.0


@pytest.fixture(scope="module")
def W():
    return ms.World()


@pytest.fixture(autouse=True)
def _switches():
    lv.set_switches(lv.LiveCfg())
    yield
    lv.set_switches(lv.LiveCfg())


def _stand(W, x, face=1):
    return km.initial_state(W.params, x, sk.FLOOR + sk.FOOT, ground=True, facing=face)


def _box_rows(x0, x1, y0=sk.FLOOR, y1=sk.FLOOR + 3.9, n=40):
    return np.tile(np.array([x0, y0, x1, y1], float), (n, 1))


def test_the_primitive_reproduces_the_recorded_presses(W):
    """V1's fixture (landed side / up slashes with the direction key, misses): the kin start, its kind and facing,
    and the contact (frame, Clapper) or none - on the previous frame's shape at the position now, physics-step frames,
    both alternations."""
    if not FIXTURE.exists():
        pytest.skip("V1's fixture is not on this machine")
    fx = pickle.loads(FIXTURE.read_bytes())
    assert len(fx) >= 20
    for e in fx:
        st = press.trace_su(W, e["S0"], e["masks"])
        t2, kind, face = press.su_start(st, 1)
        assert kind == e["kind"], (e["ep"], e["P"])
        r = W.roll(e["S0"], e["masks"])
        cen = 0.5 * (r.box[0, :, :2] + r.box[0, :, 2:])
        best = None
        for iid, bx in e["boxes"].items():
            c = sk.su_contact(cen, face, t2, bx, kind, 0.0, alive=st[:, press.S_ATK] > 0, steps=st[:, press.S_STEPS])
            if c >= 0 and (best is None or c < best[0]):
                best = (c, int(iid))
        assert best == e["truth"], (e["ep"], e["P"], best, e["truth"])
        # the default slack (0.05 u) never turns a miss into a contact
        if e["truth"] is None:
            for iid, bx in e["boxes"].items():
                assert sk.su_contact(cen, face, t2, bx, kind, ms.SU_SHRINK[0], alive=st[:, press.S_ATK] > 0,
                                     steps=st[:, press.S_STEPS]) < 0


def test_su_start_rules(W):
    S = _stand(W, 30.0, face=-1)
    st = press.trace_su(W, S, np.array([A | R, R, 0, 0, 0, 0, 0, 0], np.int64))
    assert press.su_start(st, 1) == (1, "side", 1)                   # she turns to the direction key at the press
    st = press.trace_su(W, S, np.array([A | U | L, 0, 0, 0, 0, 0, 0, 0], np.int64))
    assert press.su_start(st, 1)[1:] == ("up", -1)
    # a press within the Wanderer's dash combo window after a ground dash: not credited
    st = press.trace_su(W, S, np.array([DS | R, DS | R] + [R] * 6 + [A | R] + [0] * 8, np.int64))
    t2, kd, _ = press.su_start(st, 9)
    assert kd in ("combo", "none")
    # out of the umbrella's antic / inflate: not credited
    S_air = km.initial_state(W.params, 30.0, sk.FLOOR + 6.0 + sk.FOOT, ground=False, vy=-2.0, facing=1)
    m = [J] * 3 + [J | A | R] + [J] * 8
    st = press.trace_su(W, S_air, np.array(m, np.int64))
    n_glide = 0
    for t in range(1, len(m) + 1):
        if st[t, press.S_MODE] == km.M_GLIDE and st[t, press.S_PH] <= 1 and press.su_started(st, t):
            assert press.su_start(st, t)[1] == "glide"
            n_glide += 1
    t2, kd, _ = press.su_start(st, 4)
    assert kd != "side" or not (st[t2, press.S_MODE] == km.M_GLIDE and st[t2, press.S_PH] <= 1)


def test_simulate_credits_a_side_slash_with_its_recoil_only_when_on(W):
    S = _stand(W, 30.0, face=1)
    masks = np.array([A | R, R, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], np.int64)
    bx = _box_rows(32.4, 36.0)
    plan = ms.Plan([ms.Seg(masks, [(0, 7)], None, "t")], "prim")
    off = ms.simulate(W, plan, lambda iid: bx, 1, S, sk.HOOK_VARIANTS[0])
    assert not off.contacts and any(m[0].startswith("dslash:side") for m in off.missed)
    on = ms.simulate(W, plan, lambda iid: bx, 1, S, sk.HOOK_VARIANTS[0], su_fn=lambda iid: bx)
    assert len(on.contacts) == 1 and on.contacts[0][1:] == (7, "side")
    c = on.contacts[0][0]
    assert on.hits[7][c] == ("side", sk.SU_DMG)
    ev = np.zeros(len(masks), np.int64)
    ev[c - 1] = km.EV_RECOIL_L
    ref = W.roll(S, masks, ev)
    assert np.allclose(on.pos, ref.pos[0][:len(on.pos)])
    assert on.pos[c + 4, 0] < off.pos[c + 4, 0] - 0.2                # the recoil away from it
    # out of reach: a miss, no recoil
    far = _box_rows(34.0, 37.0)
    m2 = ms.simulate(W, plan, lambda iid: far, 1, S, sk.HOOK_VARIANTS[0], su_fn=lambda iid: far)
    assert not m2.contacts and ("side", 1, 7) in m2.missed
    # the up slash: a box overhead, RecoilDown
    plan_u = ms.Plan([ms.Seg(np.array([A | U | R] + [0] * 11, np.int64), [(0, 7)], None, "t")], "prim")
    over = _box_rows(29.5, 31.0, sk.FLOOR + 3.0, sk.FLOOR + 6.0)
    up = ms.simulate(W, plan_u, lambda iid: over, 1, S, sk.HOOK_VARIANTS[0], su_fn=lambda iid: over)
    assert len(up.contacts) == 1 and up.contacts[0][2] == "up"


def test_su_boxes_take_the_previous_frames_shape(W):
    """strike.su_boxes: each frame's box in the shape of the frame before at the position now - the array path and
    the tuple path agree, and at a state change the box is the old state's."""
    from ssbot.map2 import clapper_jit as cj
    o = cm.Obs(1, "Idle", 14 / 60.0, C, cm.STAND_Y, 0.0, 0.0, -1, 230, None, j=14, will_evade=True)
    hp = cm.HeroPath.constant(C - 5.0, sk.FLOOR + sk.FOOT, T=90)
    P = cj.predict([o], {1: cm.Memory()}, hp, W.K, T=90)
    b = P.branches[0]
    sb = sk.su_boxes(b, 1, 90)
    rb = sk.robust_boxes(b, 1, 90)
    arr, tb = brnum.barr(b)
    rows = arr[1]
    names = tb.names
    ks = rows[:, 0].astype(int)
    for i in range(1, len(rows)):
        if rows[i, 1] != 0 or rows[i, 2] != 0 or rows[i - 1, 0] != rows[i, 0] - 1:
            continue
        st0, j0 = names[int(rows[i - 1, 3])], int(rows[i - 1, 4])
        if st0 in cm.NO_BODY or names[int(rows[i, 3])] in cm.NO_BODY:
            continue
        bx = W.K.box(st0, j0)
        x, y, f = rows[i, 5], rows[i, 6], rows[i, 7]
        xa, xb = x + f * bx[0], x + f * bx[1]
        k = ks[i]
        if np.isnan(sb[k, 0]):
            continue
        assert np.allclose(sb[k], (min(xa, xb), y + bx[2], max(xa, xb), y + bx[3])), (k, st0, j0)
    assert np.isfinite(rb[:, 0]).sum() > 10
    brnum.ON[0] = False
    try:
        b2 = cj.predict([o], {1: cm.Memory()}, hp, W.K, T=90).branches[0]
        b2.__dict__.pop("_su", None)
        sb2 = sk.su_boxes(b2, 1, 90)
    finally:
        brnum.ON[0] = True
    assert np.allclose(np.nan_to_num(sb, nan=-1.0), np.nan_to_num(sb2, nan=-1.0))


def test_the_search_plans_a_side_slash_only_when_on(W):
    from ssbot.tools import m3_accept as ma
    sit = ma._sit(ma._her(W, C - 4.5, face=1), [ma._obs("Spell Antic", C, face=-1, j=4)], "cast g dx4.5", [])
    S0 = ms.Searcher(W, ms.Cfg(cap_s=0.4))
    S0.vclock = 0.004
    r0 = S0.decide(sit)
    assert not any(k.startswith("win_side") or k.startswith("win_up") for k in S0.stats)
    assert not any(kd in sk.SU_KINDS for o in r0.ev.outcomes for (_, _, kd) in o.tr.contacts)
    S1 = ms.Searcher(W, ms.Cfg(cap_s=0.4, prims=("dslash", "claw", "side", "up")))
    S1.vclock = 0.004
    r1 = S1.decide(sit)
    assert S1.stats.get("win_side_d1", 0) > 0
    assert r1.ev is not None and r1.ev.safe
    kinds = {kd for o in r1.ev.outcomes for (_, _, kd) in o.tr.contacts}
    assert "side" in kinds
    seg = r1.plan.segs[0]
    for (i, iid) in seg.dsl:
        m = int(seg.masks[i])
        if not (m & D):
            assert m & A and m & R                                # the press toward the Clapper (on her right)


def test_live_accepts_a_planned_side_press_only_when_on():
    lat = np.array([0, R, A | R, A | R, R, 0, 0], np.int64)
    assert lv._press_at(lat, 2, R) == -1
    assert lv._press_at(lat, 2, R, su=True) == 2
    hr = lv.HoldRealizer(0, lv.hold_tuple(km.HoldState.idle(1)), su=True)
    seg = ms.Seg(np.array([R, R, A | R, R, R, 0, 0, 0, 0, 0], np.int64), [(2, 7)], None, "t")
    out = hr(ms.Plan([seg], "prim"))
    assert out.segs[0].dsl and hr.n_dropped == 0
    hr0 = lv.HoldRealizer(0, lv.hold_tuple(km.HoldState.idle(1)))
    out0 = hr0(ms.Plan([seg], "prim"))
    assert not out0.segs[0].dsl and hr0.n_dropped == 1


def test_switches_off_identical_defaults():
    assert ms.Cfg().prims == ("dslash", "claw")
    assert lv.LiveCfg().prims_su is False
    assert "prims" not in lv.search_kw(lv.LiveCfg())
    assert lv.search_kw(lv.LiveCfg(prims_su=True))["prims"] == ("dslash", "claw", "side", "up")
    assert lv.search_kw(lv.LiveCfg(prims_su=True, su_kinds="side"))["prims"] == ("dslash", "claw", "side")
    lv.set_switches(lv.LiveCfg())
    assert lv.SU[0] is False
