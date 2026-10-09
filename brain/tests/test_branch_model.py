"""Forum branch model (R5 behaviour model): BranchMemory history and gates, the backoff tables, trigger geometry, the
Tiny orbit predictor, and the offline selection on synthetic decisions."""
import math
from pathlib import Path

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


def test_choristor_hops_and_recent_hits():
    m = _mem("Song Pilgrim 03")
    for frm, to, t in [("Alert Tick", "Move Start", 0.0), ("Move Start", "Hop Antic", 0.0),
                       ("Hop Antic", "Hop Check", 0.2), ("Hop Check", "Hop Back", 0.2),
                       ("Hop Back", "Ground Check", 0.3),
                       ("Ground Check", "Hop Land", 0.4)]:
        m.enter(frm, to, t)
    f = m.features("Hop Land", 0.4)
    assert f["hops"] == 1 and f["last_hop"] == "Hop Back" and f["hit"] == 2 and f["age"] == 0
    m.hit(0.5)
    assert m.features("Hop Land", 0.5)["hit"] == 0           # every hit seen up to now, this frame's included
    assert m.features("Hop Land", 0.6)["hit"] == 0
    assert m.features("Hop Land", 1.0)["hit"] == 1
    assert m.features("Hop Land", 1.0)["age"] == 3            # 0.6 s in Hop Land
    m.enter("Hop Land", "Hop Antic", 1.1)
    m.enter("Hop Antic", "Attack Choice", 1.1)
    m.enter("Attack Choice", "Battle Idle", 1.1)
    m.enter("Battle Idle", "Unalert Tick?", 1.4)
    m.enter("Unalert Tick?", "Alert Tick", 1.4)
    m.enter("Alert Tick", "Move Start", 1.4)
    assert m.features("Hop Land", 1.5)["hops"] == 0


def test_envoy_charge_range_gate_follows_the_fsm():
    """Charge Range is active at scene load, off at Charge Antic, on at Slash Antic, and on once a Walker visit lasts
    1.5 s (ActivateGameObjectDelay, resetOnExit 0: it stays on after Walker is left; a shorter visit does not arm
    it). CHARGE also needs Alerted (Slash Antic / Ambush Ready)."""
    m = _mem("Song Pilgrim 01")
    f = m.features("Walker", 0.0)
    assert f["charge_armed"] is True and f["alerted"] is False
    m.enter("Ambush 2", "Walker", 0.0)
    m.enter("Walker", "Charge Antic", 0.2)
    assert m.features("Walker", 0.3)["charge_armed"] is False and m.features("Walker", 0.3)["alerted"] is False
    m.enter("Charge Antic", "Charge", 0.5)
    m.enter("Charge", "Charge End", 1.0)
    m.enter("Charge End", "Attack Wait", 1.2)
    m.enter("Attack Wait", "Walker", 1.7)
    assert m.features("Walker", 2.0)["charge_armed"] is False          # 0.3 s into Walker
    assert m.features("Walker", 3.3)["charge_armed"] is True           # 1.6 s into Walker
    m.enter("Walker", "Alert Followers", 2.5)                          # left after 0.8 s: not armed
    m.enter("Alert Followers", "Hop Up?", 2.5)
    assert m.features("Walker", 2.6)["charge_armed"] is False
    m.enter("Hop Up?", "Slash Antic", 2.5)                             # a slash arms it and alerts
    f = m.features("Walker", 2.6)
    assert f["charge_armed"] is True and f["alerted"] is True
    m.enter("Slash Antic", "Charge Antic", 3.0)
    m.enter("Charge Antic", "Charge", 3.3)
    m.enter("Charge", "Charge End", 3.8)
    m.enter("Charge End", "Attack Wait", 4.0)
    m.enter("Attack Wait", "Walker", 4.5)
    m.enter("Walker", "Leader?", 6.1)                                  # 1.6 s in Walker: armed, and it stays
    assert m.features("Walker", 6.2)["charge_armed"] is True


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
    assert geometry("Song Reed", None, None, 0, 31.0, 10.0, None) == {"hero_x": 1}      # the hero alone


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


class _Tr:
    """The tracker fields BranchView reads."""

    def __init__(self, tk, iid, state, mem, pos=(30.0, 10.0), flip=0):
        self.tk, self.iid, self.state, self.mem, self.pos, self.flip = tk, iid, state, mem, pos, flip
        self.hidden, self.dead, self.in_play = False, False, True


class _WS:
    def __init__(self, hx, hy):
        from ssbot.core.worldstate import E, HeroState, Resources
        self.hero = HeroState(pos=E((hx, hy)), hurtbox=[(hx - 0.25, hy - 1.04), (hx + 0.25, hy + 1.04)])
        self.res = Resources(silk=E(5))


def test_reactive_branches_follow_the_gates_and_the_revealed_coin():
    from ssbot.combat.branch_model import BranchView
    bv = BranchView(BranchModel({"types": {}}))
    reed = fb.memory_for("Song Reed")
    reed.enter("Activate", "Alert", 0.0)
    tr = _Tr("Song Reed", 1, "Alert", reed)
    bv.observe(0.0, _WS(45.0, 10.0), {1: tr})
    got = {rx.successor: p for rx, p in bv.reactive(tr, 0.0)}
    assert got == {"Evade Antic": 0.95, "Defend Start": 0.45}
    path = [(0.05 * k, (40.0 - 0.5 * k - 0.25, 8.96, 40.0 - 0.5 * k + 0.25, 11.04)) for k in range(20)]
    ep = {s: (round(t, 2), p) for s, t, p in bv.entry_prob(tr, 0.0, path)}
    assert ep["Defend Start"][0] < ep["Evade Antic"][0]          # the 7.65 u circle before the narrow evade boxes
    reed.enter("Alert", "Evade Antic", 1.0)
    reed.enter("Evade Antic", "Evade", 1.1)
    reed.enter("Evade", "Evade End", 1.4)
    reed.enter("Evade End", "Alert", 1.4)
    tr.state = "Alert"
    assert {rx.successor for rx, _ in bv.reactive(tr, 1.5)} == {"Defend Start"}      # the evade is spent
    bell = fb.memory_for("Pilgrim 03 Song")
    bell.enter("Startle", "In Range", 0.0)
    trb = _Tr("Pilgrim 03 Song", 2, "In Range", bell)
    assert [rx.successor for rx, _ in bv.reactive(trb, 0.6)] == ["Evade Antic"]
    bell.gates["evade_cd"] = True
    assert bv.reactive(trb, 0.6) == []
    # Clapper: the hero stood in Slam Range for frames after the 0.25 s gate and it did not evade: tails, p 0
    clap = fb.memory_for("Song Heavy Sentry")
    clap.enter("Slam Recover", "Idle", 0.0)
    trc = _Tr("Song Heavy Sentry", 3, "Idle", clap)
    bv2 = BranchView(BranchModel({"types": {}}))
    for k in range(20):
        bv2.observe(0.05 * k, _WS(32.0, 9.0), {3: trc})
    assert [p for _, p in bv2.reactive(trc, 0.2)] == [0.49]
    assert [p for _, p in bv2.reactive(trc, 0.95)] == [0.0]


def test_multi_forecaster_branch_view_is_scoring_only():
    """The branch model hangs on the trackers (BranchMemory) and fills Subject.next_p; the placements, the occupancy,
    the probability map and the support set are the same with and without it."""
    from ssbot.combat.multi_forecast import MultiForecaster
    from ssbot.core.worldstate import ORACLE
    from tests import test_multi_forecast as tm
    model = BranchModel({"types": {"Song Reed": {"Alert": {
        "outcomes": ["Defend Start", "Stab Pos"], "covariates": ["prev"], "timing": "branch",
        "counts": [{"": [10, 30]}, {"none": [1, 9]}]}}}})
    plain = MultiForecaster(tm._tables(), ORACLE, waves=False)
    withb = MultiForecaster(tm._tables(), ORACLE, waves=False, branch=model)
    script = tm._script_stab()
    tk = np.arange(0, 31) * tm.BIN
    xs, ys = np.full((3, 31), 22.0), np.full((3, 31), 5.0)
    xs[1] += 3.0
    xs[2] -= 4.0
    for f, t, ents, evs in script[:20]:
        plain.update(tm._ws(f, t, ents, evs))
        withb.update(tm._ws(f, t, ents, evs))
        a, b = plain.forecast(0.8), withb.forecast(0.8)
        assert np.array_equal(a.occupied(xs, ys, tk), b.occupied(xs, ys, tk))
        assert np.array_equal(a.prob(xs, ys, tk), b.prob(xs, ys, tk))
        assert [(e.instance, e.hits, e.damage) for e in a.support_set().events] == \
            [(e.instance, e.hits, e.damage) for e in b.support_set().events]
        sa = {s.iid: s.next_p for s in a.subjects}
        sb = {s.iid: s.next_p for s in b.subjects}
        assert all(v is None for v in sa.values())
        if f < 10:
            assert sb[7] == pytest.approx({"RE_DEFEND": (1 + 4 * 10.5 / 41) / 14,
                                           "RE_STAB": (9 + 4 * 30.5 / 41) / 14})
        else:
            assert sb[7] is None                      # in an attack: no decision to predict
    tr = withb.trackers[7]
    assert tr.mem is not None and tr.mem.fam == "RE_STAB" and plain.trackers[7].mem is None
    assert withb.branch_probs(7, "Alert") is not None and plain.branch_probs(7) is None


PARITY_CACHE = Path("C:/ssbot/data/m2_forum_r0/cache/20261002_223640_Forum_A_data__i2__ep0.npz")
HITBOXES = Path(__file__).resolve().parents[2] / "knowledge" / "1.0.30000" / "enemies" / "forum" / \
    "Reed_hitboxes.npz"


@pytest.mark.skipif(not (PARITY_CACHE.exists() and HITBOXES.exists()),
                    reason="R0 Forum cache / recording or the generated forum hitbox tables not on this machine")
def test_runtime_covariates_equal_the_scans_on_a_recording(tmp_path):
    """Train / serve parity: the recording replayed through OracleBackend -> MultiForecaster(branch=...) gives, on
    every frame an enemy is in a modelled decision state, the covariates the offline scan gives that frame (geometry
    at now / entry / stored, history, gates, context)."""
    from ssbot.tools.forum_branch import _parity_one
    model = Path(__file__).resolve().parents[2] / "knowledge" / "1.0.30000" / "enemies" / "forum" / \
        "branch_model.json"
    r = _parity_one((str(PARITY_CACHE), str(model), str(tmp_path), 6000))     # the hero's silk read into tmp_path
    assert r["stats"].get("compared", 0) > 3000
    assert r["differences"] == {} and set(r["stats"]) == {"compared"}
