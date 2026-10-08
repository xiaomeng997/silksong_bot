"""Forum branch model (R5 behaviour model): BranchMemory history and gates, the backoff tables, trigger geometry, the
Tiny orbit predictor, and the offline selection on synthetic decisions."""
import math

import numpy as np
import pytest

from ssbot.combat.branch_model import (SENSING, BranchMemory, BranchModel, DecisionModel, geometry, in_range)
from ssbot.combat.tiny_orbit import TinyOrbit, static_radius
from ssbot.knowledge import forum_branch as fb
from ssbot.knowledge.gauntlet_tables import FORUM_SPECS

SPECS = {s.boss_type: s for s in FORUM_SPECS.values()}


def _mem(tk: str) -> BranchMemory:
    return fb.memory_for(tk)


def test_bellbearer_evade_cooldown_only_cleared_by_throw_antic():
    m = _mem("Pilgrim 03 Song")
    assert m.features("In Range", 0.0)["evade_cd"] is False
    for frm, to, t in [("Startle", "In Range", 0.0), ("In Range", "Evade Antic", 0.6), ("Evade Antic", "Evade", 0.7),
                       ("Evade", "Evade End", 1.0), ("Evade End", "Out of Range", 1.1),
                       ("Out of Range", "Insta Throw?", 1.5), ("Insta Throw?", "In Range", 1.5)]:
        m.enter(frm, to, t)
    f = m.features("In Range", 2.0)
    assert f["evade_cd"] is True and f["prev"] == "CB_EVADE"
    m.enter("In Range", "Throw Evade", 2.2)
    m.enter("Throw Evade", "Roof Avoid", 2.3)
    assert m.features("In Range", 2.4)["evade_cd"] is True        # throwing has not reached Throw Antic yet
    m.enter("Roof Avoid", "Throw Antic", 2.4)
    assert m.features("In Range", 2.5)["evade_cd"] is False


def test_reed_armed_and_just_did_defend():
    m = _mem("Song Reed")
    f = m.features("Alert", 0.0)
    assert f["armed"] is True and f["jdd"] is False
    m.enter("Activate", "Alert", 0.0)
    m.enter("Alert", "Evade Antic", 0.5)
    assert m.features("Alert", 0.6)["armed"] is False
    m.enter("Evade Antic", "Evade", 0.6)
    m.enter("Evade", "Evade End", 0.9)
    m.enter("Evade End", "Alert", 0.9)
    m.enter("Alert", "Defend Start", 1.0)
    f = m.features("Alert", 1.1)
    assert f["armed"] is True and f["jdd"] is True
    m.enter("Defend Start", "Defend", 1.1)
    m.enter("Defend", "Defend End", 2.1)
    m.enter("Defend End", "Alert", 2.3)
    f = m.features("Alert", 2.4)
    assert f["jdd"] is True and f["prev_end"] == "RE_DEFEND:Defend End" and f["from"] == "Defend End"
    m.enter("Alert", "Choice", 3.5)
    m.enter("Choice", "Throw Range", 3.5)
    m.enter("Throw Range", "Throw Recoil", 3.9)
    m.enter("Throw Recoil", "Throw Antic Anim", 4.0)
    m.enter("Throw Antic Anim", "Throw Antic", 4.2)
    assert m.features("Alert", 4.3)["jdd"] is False
    # the choices of this decision state are its anti-repeat history
    assert m.features("Alert", 4.3)["last_choice"] == "Choice"
    assert m.features("Alert", 4.3)["prev2_choice"] == "Defend Start|Choice"


def test_choristor_hops_and_hit_same_frame_excluded():
    m = _mem("Song Pilgrim 03")
    for frm, to, t in [("Alert Tick", "Move Start", 0.0), ("Move Start", "Hop Antic", 0.0),
                       ("Hop Antic", "Hop Check", 0.2), ("Hop Check", "Hop Back", 0.2), ("Hop Back", "Ground Check", 0.3),
                       ("Ground Check", "Hop Land", 0.4)]:
        m.enter(frm, to, t)
    f = m.features("Hop Land", 0.4)
    assert f["hops"] == 1 and f["last_hop"] == "Hop Back"
    m.hit(0.5)
    assert m.features("Hop Land", 0.5)["hit"] == 2           # the hit on the decision's own frame is not history
    assert m.features("Hop Land", 0.6)["hit"] == 0
    m.hit(1.0)
    assert m.features("Hop Land", 1.0)["hit"] == 1           # the hit 0.5 s before still counts
    m.enter("Hop Land", "Hop Antic", 1.1)
    m.enter("Hop Antic", "Attack Choice", 1.1)
    m.enter("Attack Choice", "Battle Idle", 1.1)
    m.enter("Battle Idle", "Unalert Tick?", 1.4)
    m.enter("Unalert Tick?", "Alert Tick", 1.4)
    m.enter("Alert Tick", "Move Start", 1.4)
    assert m.features("Hop Land", 1.5)["hops"] == 0


def test_clawmaiden_suck_age_accumulates_in_fly_only():
    m = _mem("Song Handmaiden")
    m.enter("Startle", "Start", 0.0)
    m.enter("Start", "Set Distance", 0.1)
    m.enter("Set Distance", "Fly", 0.1)
    assert m.features("Fly", 0.9)["suck_age"] == 0            # 0.8 s in Fly
    m.enter("Fly", "Slash Antic", 1.1)                        # 1.0 s in Fly
    m.enter("Slash Antic", "Slash 1", 1.6)
    m.enter("Slash 1", "Fly", 2.5)
    assert m.features("Fly", 2.5)["suck_age"] == 1            # 1.0 s
    assert m.features("Fly", 3.6)["suck_age"] == 3            # 2.1 s


def test_decision_model_backoff():
    dm = DecisionModel(["A", "B"], ["x", "y"], "branch",
                       [{"": [50, 50]}, {"0": [40, 0], "1": [10, 50]}, {"0|a": [5, 0]}])
    p = dm.predict({"x": 0, "y": "a"})
    assert math.isclose(sum(p.values()), 1.0)
    assert p["A"] > 0.95
    q = dm.predict({"x": 1})                                   # y unknown: stops at x
    assert math.isclose(q["A"], (10 + 4 * 50.5 / 101) / 64)
    r = dm.predict({"x": 7})                                   # unseen level: the marginal
    assert math.isclose(r["A"], 0.5)
    bm = BranchModel({"types": {"Song Reed": {"Alert": {"outcomes": ["A", "B"], "covariates": [], "timing": "entry",
                                                         "counts": [{"": [1, 3]}]}}}})
    assert bm.has("Song Reed", "Alert") and bm.timing("Song Reed", "Alert") == "entry"
    assert bm.predict("Song Reed", "Choice", None, None) is None
    assert math.isclose(bm.predict("Song Reed", "Alert", None, None)["B"], 3.5 / 5.0)


def test_trigger_shapes_mirror_with_flip():
    hb = lambda x, y: (x - 0.25, y - 1.04, x + 0.25, y + 1.04)  # noqa: E731
    # Clawmaiden Slash Range: box centred 1.565 u in front (flipX False faces -x)
    assert in_range("Song Handmaiden", "Slash Range", 20.0, 10.0, 0, hb(17.0, 10.0))
    assert not in_range("Song Handmaiden", "Slash Range", 20.0, 10.0, 0, hb(23.5, 10.0))
    assert in_range("Song Handmaiden", "Slash Range", 20.0, 10.0, 1, hb(23.0, 10.0))
    # Minister Evade Range: circle r 4.955 one unit below the transform
    assert in_range("Song Administrator", "Evade Range", 30.0, 10.0, 0, hb(30.0, 5.0))
    assert not in_range("Song Administrator", "Evade Range", 30.0, 10.0, 0, hb(30.0, 15.2))
    assert in_range("Song Reed", "Nope", 0, 0, 0, hb(0, 0)) is None
    g = geometry("Song Reed", 30.0, 10.0, 0, 31.0, 10.0, hb(31.0, 10.0), silk=5)
    assert g["in_Evade Range"] and g["side"] == "R" and g["front"] == "back" and g["silk"] == 3
    assert geometry("Song Reed", None, None, 0, 31.0, 10.0, None) == {}


def test_sensing_table_names_real_states():
    for tk, rows in SENSING.items():
        sp = SPECS[tk]
        for st, (kind, note) in rows.items():
            assert kind in ("branch", "entry") or kind.startswith("stored:"), (tk, st)
            assert note


def test_tiny_orbit_rotates_by_facing_and_clamps():
    orb = TinyOrbit({0: -200.0, 1: 200.0}, [[0.0, 1.0], [1.0, 5.0], [2.0, 5.0]],
                    bounds=(14.0, 49.0, 4.0, 30.0))
    p0 = orb.predict((35.0, 9.78), (30.0, 10.0), (0.0, 0.0), 1.2, [0.1], flip=0)[0]
    p1 = orb.predict((35.0, 9.78), (30.0, 10.0), (0.0, 0.0), 1.2, [0.1], flip=1)[0]
    assert p0[1] < 9.78 < p1[1]                                   # clockwise vs counter-clockwise
    assert math.isclose(math.hypot(p0[0] - 30.0, p0[1] - 9.78), 5.0, abs_tol=1e-6)
    low = orb.predict((30.0, 5.0), (30.0, 6.0), (0.0, 0.0), 1.5, [0.2], flip=0)[0]
    assert low[1] >= 4.0
    assert math.isclose(static_radius(0.0), 1.0) and math.isclose(static_radius(1.0), 5.0)


def test_greedy_finds_the_informative_covariate():
    rng = np.random.default_rng(3)
    n = 4000
    x = rng.integers(0, 2, n)
    z = rng.integers(0, 3, n)                                     # noise
    y = np.where(rng.random(n) < np.where(x == 1, 0.9, 0.1), 1, 0)
    fold = np.arange(n) % 2
    sel, ll, trace = fb.greedy(y, 2, fold, {"g:x": x.astype(np.int64), "h:z": z.astype(np.int64)})
    assert sel == ["g:x"]
    assert ll < 0.4 < trace[0][1]
    ll_u, P = fb.cv_logloss(y, 2, fold, [])
    cal = fb.calibration(P, y)
    assert cal["ece"] < 0.05 and math.isclose(ll_u, trace[0][1], abs_tol=1e-4)


@pytest.mark.parametrize("tk", sorted(SENSING))
def test_decisions_are_decision_or_attack_states(tk):
    sp = SPECS[tk]
    known = set(sp.decision_states) | set(sp.attack_starts)
    for st in fb.decisions_of(tk):
        assert st, tk
    assert known
