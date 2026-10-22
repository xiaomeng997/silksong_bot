"""Map v2 stage M3: the search (ssbot.map2.search), the strike module, the combo library, the recognizers."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest

from ssbot.knowledge import kinematics as km
from ssbot.map2 import clapper as cm
from ssbot.map2 import combos as cb
from ssbot.map2 import recognize as rz
from ssbot.map2 import search as ms
from ssbot.map2 import strike as sk

C = 33.0


@pytest.fixture(scope="module")
def W():
    return ms.World()


def _obs(st, x, face=-1, j=2, iid=1):
    return cm.Obs(iid, st, j / 60.0, x, cm.STAND_Y, 0.0, 0.0, face, 230, None, will_evade=None, j=j)


def _ground(W, x, face=1):
    return km.initial_state(W.params, x, sk.FLOOR + sk.FOOT, ground=True, facing=face)


def test_dslash_contact_both_alternations():
    pos = np.array([[30.0, 9.0]] * 12)
    face = np.ones(12, dtype=np.int64)
    ground = np.zeros(12, bool)
    boxes = np.full((12, 4), np.nan)
    boxes[:, :] = (29.5, 5.0, 30.5, 7.0)             # top 2.0 below her transform: both polygons reach it
    assert sk.dslash_contact(pos, face, ground, 1, boxes) == 4      # press 1 -> the first active frame 1 + 3
    boxes[:, :] = (29.5, 5.0, 30.5, 6.0)             # top 3.0 below: out of reach
    assert sk.dslash_contact(pos, face, ground, 1, boxes) == -1
    ground[5:] = True                                # landing ends the swing
    boxes[:, :] = (29.5, 5.0, 30.5, 7.0)
    boxes[:5] = np.nan
    assert sk.dslash_contact(pos, face, ground, 1, boxes) == -1


def test_claw_hook_timeline(W):
    S = km.initial_state(W.params, 25.0, sk.FLOOR + 1.0 + sk.FOOT, ground=False, facing=1)
    boxes = np.tile(np.array([31.13, 3.0, 34.35, 6.9]), (80, 1))     # an Idle body 6 u ahead
    for var in sk.HOOK_VARIANTS:
        hk = sk.claw_hook(S, 10, 1, 1, boxes, var)
        assert hk.ok and hk.hit == 10 + sk.HOOK_HIT_F
        assert 10 + 23 <= hk.ctrl <= 10 + 34
        # the stop: her box front `gap` short of the body front
        assert abs((boxes[0, 0] - var.gap) - (hk.x_stop + sk.HALF_W)) < 1e-6
    far = np.tile(np.array([45.0, 3.0, 48.0, 6.9]), (80, 1))
    assert not sk.claw_hook(S, 10, 1, 1, far, sk.HOOK_VARIANTS[0]).ok          # beyond the ray: unhooked
    high = np.tile(np.array([31.13, 9.0, 34.35, 12.0]), (80, 1))
    assert not sk.claw_hook(S, 10, 1, 1, high, sk.HOOK_VARIANTS[0]).ok         # out of the height band


def test_robust_boxes_intersect_the_timing_variants():
    K = cm.Know.load()
    rec = [(5, 0, 2, "Idle", 3, 30.0, cm.STAND_Y, 1, 0), (6, -1, 0, "Idle", 4, 30.5, cm.STAND_Y, 1, 0)]
    br = cm.Branch(1.0, {}, None, {1: rec}, [], K, 10)
    b = sk.robust_boxes(br, 1)
    assert np.isnan(b[4, 0]) and not np.isnan(b[5, 0])
    one = sk._rec_box(rec[0], K)
    two = sk._rec_box(rec[1], K)
    assert b[5, 0] == pytest.approx(max(one[0], two[0])) and b[5, 2] == pytest.approx(min(one[2], two[2]))
    assert b[7, 0] == pytest.approx(one[0])


def test_simulate_and_state_at(W):
    S0 = _ground(W, 25.0)
    masks = np.array([km.B_JUMP] * 10 + [km.B_RIGHT] * 10, np.int64)
    plan = ms.Plan([ms.Seg(masks)])
    tr = ms.simulate(W, plan, lambda iid: None, 1, S0, sk.HOOK_VARIANTS[0])
    assert tr.end == 20 and len(tr.pos) == 21
    r = W.roll(S0, masks)
    assert np.allclose(tr.pos, r.pos[0])
    S12, cu = ms.state_at(W, tr, 12)
    assert np.allclose(S12[km.PX], r.pos[0, 12, 0]) or abs(S12[km.PX] - r.phys[0, 12, 0]) < 1e-9


def test_inmove_margin_by_state():
    K = cm.Know.load()
    tab = ms.inmove_table()
    assert "by_state" in tab and "Slam 0" in tab["by_state"]["slam"]
    rec = [(0, 0, 0, "Slam Antic", 10, C, cm.STAND_Y, -1, 0), (40, 0, 0, "Slam 0", 1, C, cm.STAND_Y, -1, 0)]
    br = cm.Branch(1.0, {}, None, {1: rec}, [], K, 60)
    s = cm.Shape(cm.DAMAGE, 1, "body", box=(30, 3, 34, 7), mv="slam")
    m = ms.margin_of(br, s, "Slam 0", 40, K)
    assert m == ms._tab(tab["by_state"]["slam"]["Slam 0"], 40, -1)
    assert m < K.margin("slam", 40)                 # the in-move table, not M2's look-ahead one


def test_search_finds_the_clawline_on_an_idle_clapper(W):
    """P1 (forced setup): an Idle Clapper 7 u in front, her on the ground - the search (primitives only) finds a
    safe plan whose strike is a hooked Clawline on it."""
    sit = ms.Situation(_ground(W, C - 7.0), [_obs("Idle", C, face=-1, j=8)], {1: cm.Memory()})
    res = ms.Searcher(W, ms.Cfg(depth=1, cap_s=60)).decide(sit)
    assert res.ev is not None and res.ev.safe and res.ev.hits >= 0.99
    labels = rz.classify(res.ev, sit)
    assert any(lb.startswith("P1") for lb in labels)
    row = ms.plan_log(res.ev)
    assert any(st.get("do") == "claw" for st in row["steps"])
    assert row["p_safe"] == 1.0 and row["outcomes"]


def test_search_down_slashes_a_clapper_under_her(W):
    """P5 (forced setup): an Idle Clapper under her falling path - a down slash on it instead of landing on it."""
    S = km.initial_state(W.params, C + 0.3, cm.FLOOR + 5.5 + sk.FOOT, ground=False, vy=-3.0, facing=1)
    sit = ms.Situation(S, [_obs("Idle", C, face=-1, j=6)], {1: cm.Memory()})
    res = ms.Searcher(W, ms.Cfg(depth=1, cap_s=60, prims=("dslash",))).decide(sit)
    assert res.ev is not None and res.ev.safe
    assert any(kd == "down" and iid == 1 for (_, iid, kd) in res.ev.nominal.tr.contacts)
    # the direct down slash on it (P5) is found among the tried plans (the chosen one may reach it through the float)
    assert any("P5" in rz.classify(e, sit) for e in res.tried if e.safe)


def test_combo_library(W):
    lib = cb.load_library()
    names = {c.name for c in lib}
    assert {"CLAWSTRIKE", "SLAMSTRIKE", "JUMPTRAP", "LOWHOP"} <= names
    for c in lib:
        d = c.d
        assert d["status"] in ("candidate", "verified", "promoted", "demoted")
        assert d["steps"] and d["anchor"] and d["impl"] in cb.IMPLS
    sit = ms.Situation(_ground(W, C - 7.0), [_obs("Slam Antic", C, face=-1, j=2)], {1: cm.Memory()})
    cs = next(c for c in lib if c.name == "CLAWSTRIKE")
    plans = cs.instantiate(W, sit)
    assert plans and all(p.segs[-1].claw is not None and p.origin == "CLAWSTRIKE" for p in plans)


def test_m3_tools_only_import_map2():
    """M3 is offline: no bot module imports ssbot.map2 (the decisions stay bit-identical); only map2 itself and the
    offline tools do."""
    root = Path(ms.__file__).resolve().parents[1]
    pat = re.compile(r"^\s*(from|import)\s+ssbot\.map2|ssbot\.map2\s+import", re.M)
    allowed = {"tools/m1_envelope.py", "tools/m2_validate.py", "tools/zone_overlay.py", "tools/m3_search.py",
               "tools/m3_accept.py"}
    offenders = []
    for p in root.rglob("*.py"):
        rel = p.relative_to(root).as_posix()
        if rel.startswith("map2/") or rel in allowed:
            continue
        if pat.search(p.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(rel)
    assert offenders == []


def test_hysteresis_keeps_a_valid_plan(W):
    """The previous plan, shifted by the frames played, is re-evaluated first and kept unless a new one beats it by
    w_switch (the G-line flicker of 10-12 / 13)."""
    sit = ms.Situation(_ground(W, C - 7.0), [_obs("Idle", C, face=-1, j=8)], {1: cm.Memory()})
    S = ms.Searcher(W, ms.Cfg(depth=1, cap_s=60))
    r0 = S.decide(sit)
    assert r0.ev is not None and r0.ev.safe
    n = 1
    prev = r0.plan.shifted(n)
    assert prev is not None and len(prev.segs[0].masks) == len(r0.plan.segs[0].masks) - n
    sit1 = ms.advance(W, sit, r0.ev, n)
    S2 = ms.Searcher(W, ms.Cfg(depth=1, cap_s=60, w_switch=10.0))   # a huge switch penalty: the kept plan stays
    r1 = S2.decide(sit1, prev=prev)
    assert r1.kept and r1.ev.safe
