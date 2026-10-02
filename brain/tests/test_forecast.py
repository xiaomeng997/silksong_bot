"""Threat forecast (ssbot.combat.forecast, M2 W3): the boss model, the walk over the Control graph, both views, the
contacts of the fixture windows inside the support forecast 3 frames earlier, and the drop-bell / tail rules."""
import math

import numpy as np
import pytest

from ssbot.backends.observability import ObservabilityFilter
from ssbot.backends.oracle_backend import OracleBackend
from ssbot.combat.boss_model import Anchor, BossModel
from ssbot.combat.forecast import BIN, Ctx, Forecaster, Root, load_planner_templates
from ssbot.core.bosses import BELL_BEAST
from ssbot.core.worldstate import ORACLE, VISION_EQUIVALENT
from tests import worldstate_fixture as fx

LAG = 3


@pytest.fixture(scope="module")
def model() -> BossModel:
    return BossModel.load()


@pytest.fixture(scope="module")
def templates(model):
    return load_planner_templates(model, 0.0)


def test_boss_model_facts(model):
    assert model.anchor("BB_CHARGE", "Set L") == Anchor(75.03, 5.49, 1)
    assert model.anchor("BB_CHARGE", "Set R") == Anchor(95.72, 5.49, -1)
    assert model.anchor("BB_CHARGE", "-") == Anchor(95.72, 5.49, -1)          # the first attack: from the right
    assert model.anchor("BB_LEAP", "Set L").y == 0.99
    assert model.anchor("BB_BURST", None) is None                              # x anywhere in 81.2-91.2
    assert model.families["BB_BURST"].box_offset[True] == (-0.539, -2.68)
    assert model.anchor("BB_RAGE", None) == Anchor(86.21, 5.49, 1)
    lo, hi = model.states["Submerged"].dwell
    assert 1.0 <= lo <= hi <= 1.02
    assert {s for s, _ in model.states["Bell Burst?"].succ} == {"Burst Pos", "Choose Dir"}
    assert model.families["BB_LEAP"].p2_only["Dig In"] == frozenset({"BoneBeast DropBell M2"})


def _fc(model, templates, view, roots=None):
    fc = Forecaster(model, view, templates=templates)
    if roots is not None:
        fc.tracker.roots = lambda origin: (roots, True)
    return fc


def test_walk_places_the_charge_and_its_successors(model, templates):
    an = model.anchor("BB_CHARGE", "Set L")
    fc = _fc(model, templates, ORACLE, [Root("Charge Antic", -0.3, -0.3, Ctx("BB_CHARGE", "Set L", an, "P1", False),
                                             current=True)])
    f = fc.forecast(1.5, 0.0)
    keys = {p.key for p in f.placements}
    assert "support/BB_CHARGE/Charge Antic/anchor" in keys and "support/BB_CHARGE/Charge/anchor" in keys
    assert all(p.anchor == (75.03, 5.49) for p in f.placements if p.key.endswith("/anchor"))
    ch = [p for p in f.placements if p.key == "support/BB_CHARGE/Charge/anchor"]
    # Charge enters after the rest of the antic (0.5833-0.6001 s logged, 0.3 s spent): one placement per 1/60 s bin
    assert len(ch) == 2 and min(-p.t_ref for p in ch) == pytest.approx(0.2833, abs=1e-3)
    # a normal end places no body tail (the charge's tail holds only bodies of killed instances)
    assert not any("_tail" in p.key for p in f.placements)
    tk = np.arange(0, 91) * BIN
    ground = f.occupied(np.full((1, 91), an.x + 10.0), np.full((1, 91), 3.0544), tk)[0]
    air = f.occupied(np.full((1, 91), an.x + 10.0), np.full((1, 91), 9.0), tk)[0]
    assert ground[30:60].any() and not ground[:15].any() and not air.any()   # the charge sweeps the floor only


def test_unknown_anchor_uses_world_all_and_the_decision_chain_branches(model, templates):
    fc = _fc(model, templates, VISION_EQUIVALENT, [Root("Submerged", -0.5, -0.5, Ctx(phase="P1", raged=False,
                                                                                       hp=150.0))])
    f = fc.forecast(2.5, 0.0)
    fams = {p.key.split("/")[1] for p in f.placements}
    assert {"BB_CHARGE", "BB_LEAP", "BB_BURST"} <= fams
    assert any(p.key.endswith("world_all") for p in f.placements if "BB_BURST" in p.key)
    anchors = {p.anchor for p in f.placements if p.key.startswith("support/BB_CHARGE") and p.anchor}
    assert anchors == {(75.03, 5.49), (95.72, 5.49)}                        # both directions
    p = f.prob(np.array([[85.4] * 10]), np.array([[3.05] * 10]), np.arange(10) * BIN + 1.6)
    assert 0.0 <= p[0] <= 1.0


@pytest.mark.parametrize("view", [ORACLE, VISION_EQUIVALENT])
@pytest.mark.parametrize("win", [0, 1])
def test_fixture_contacts_are_inside_the_support_forecast_earlier(model, templates, view, win):
    """Hits taken in the fixture windows (a charge after the wake; a drop bell of the rage pattern): the hero box of
    the hit frame or the one before lies inside the forecast made LAG frames earlier."""
    states = fx.window(win)
    backend = OracleBackend(bosses=[BELL_BEAST])
    filt = ObservabilityFilter(bosses=[BELL_BEAST]) if view == VISION_EQUIVALENT else None
    fc = Forecaster(model, view, templates=templates)
    forecasts, boxes, ts, hits = {}, {}, {}, []
    for s in states:
        ws = backend.feed(s)
        if filt is not None:
            ws = filt.apply(ws)
        if s["f"] == 56532 and view == VISION_EQUIVALENT:
            fc.notify_wake(ws.stamp.t_game_s)
        fc.update(ws)
        forecasts[s["f"]] = fc.forecast(1.0)
        boxes[s["f"]] = (s.get("hero") or {}).get("box")
        ts[s["f"]] = ws.stamp.t_game_s
        if any(e.get("k") == "damage" for e in s.get("ev") or ()):
            hits.append(s["f"])
    if win == 1 and view == VISION_EQUIVALENT:
        pytest.skip("the window starts inside the rage: the vision view never saw the boss before it")
    assert hits
    for c in hits:
        f = forecasts[c - LAG]
        ok = False
        for fr in (c, c - 1):
            b = boxes[fr]
            x, y = 0.5 * (b[0] + b[2]), 0.5 * (b[1] + b[3])
            ok |= bool(f.occupied(np.array([[x]]), np.array([[y]]), np.array([ts[fr] - ts[c - LAG]]))[0, 0])
        assert ok, (view, c)
        assert f.known


def test_drop_bell_unions_count_only_after_the_arming_lead(model, templates):
    fc = _fc(model, templates, ORACLE, [Root("Ptn L", -1.0, -1.0, Ctx("BB_RAGE", None, model.anchor("BB_RAGE", None),
                                                                      "P1", True), current=True)])
    assert 1.15 < fc.bell_lead < 1.25
    f = fc.forecast(2.0, 0.0)
    ptn = [p for p in f.placements if "Ptn L" in p.key]
    assert ptn and all(p.t_from == pytest.approx(fc.bell_lead) for p in ptn)
    # nothing armed: the floor is free for the bell lead, whatever the union says
    tk = np.arange(0, 120) * BIN
    xs = np.arange(70.0, 101.0, 1.0)
    occ = f.occupied(np.repeat(xs[:, None], len(tk), 1), np.full((len(xs), len(tk)), 3.0544), tk)
    assert not occ[:, tk < fc.bell_lead - BIN].any() and occ[:, tk > fc.bell_lead + BIN].any()
    # an armed bell's self template is placed at its arming position and time
    fc.tracker.bells = {7: ("BoneBeast DropBell M", -1.0, (85.2, 13.74))}
    f = fc.forecast(2.0, 0.0)
    own = [p for p in f.placements if p.key == "support/ent/BoneBeast DropBell M/self"]
    assert len(own) == 1 and own[0].anchor == (85.2, 13.74) and own[0].t_ref == pytest.approx(1.0)
    # with an armed bell whose arming was not seen the unions count from the start again
    fc.tracker.bells_unknown = True
    f = fc.forecast(2.0, 0.0)
    assert all(math.isinf(p.t_from) for p in f.placements if "Ptn L" in p.key)


def test_tails_of_a_burst_and_of_a_killed_attack(model, templates):
    an = Anchor(86.0, 5.49, 1)
    fc = _fc(model, templates, ORACLE, [])
    fc.tracker.ends = [("BB_BURST", an, -0.5, -0.5, "P1", False)]
    keys = {p.key for p in fc.forecast(1.0, 0.0).placements}
    assert keys == {"support/BB_BURST/_tail/anchor"}                       # bells; DropBell M2 is P2 only
    fc.tracker.ends = [("BB_CHARGE", Anchor(75.03, 5.49, 1), 0.0, 0.0, "P1", False)]
    assert not fc.forecast(1.0, 0.0).placements                              # underground after a normal end
    fc.tracker.ends = [("BB_CHARGE", Anchor(75.03, 5.49, 1), 0.0, 0.0, "P1", True)]
    assert {p.key for p in fc.forecast(1.0, 0.0).placements} == {"support/BB_CHARGE/_tail/anchor"}


def test_support_set_names_instances(model, templates):
    an = model.anchor("BB_CHARGE", "Set R")
    fc = _fc(model, templates, ORACLE, [Root("Charge", -0.1, -0.1, Ctx("BB_CHARGE", "Set R", an, "P1", False),
                                             current=True)])
    fc.tracker.iid = 42
    sup = fc.forecast(1.0, 0.0).support_set()
    assert sup.known and [(e.source, e.instance, e.damage) for e in sup.events] == [("Bone Beast", 42, 2)]
    fc.tracker.roots = lambda origin: ([], False)
    sup = fc.forecast(1.0, 0.0).support_set()
    assert not sup.known and not sup.certified_empty


def test_ve_burst_anchor_lasts_the_burst_and_a_tell_sets_it_underground(model, templates):
    """Vision-equivalent tracker: the burst anchor comes from the first drawn frame (box offset) and stays for the
    whole burst (an earlier version lost it from the second frame on); a hypothetical tell phase (ObservabilityFilter
    tells) sets it from the hidden transform x before the eruption, and the walk starts in Burst Antic there."""
    from ssbot.core.worldstate import E, Entity, Kind, PhasePost, WorldState
    off = model.families["BB_BURST"].box_offset.get(False, (0.0, 0.0))[0]

    def frame(t, phase, x, tau, hidden=False, conf=1.0):
        ws = WorldState()
        ws.stamp.t_game_s = t
        ws.entities = [Entity(id=7, kind=Kind.BOSS, type_key=E("Bone Beast"), pos=E((x, 3.0), conf=conf),
                              phase=PhasePost(topk=[(phase, 1.0)], t_in_phase=tau), hidden=hidden,
                              visible_frac=0.0 if hidden else 1.0)]
        return ws

    for told in (False, True):
        fc = _fc(model, templates, VISION_EQUIVALENT)
        trk = fc.tracker
        trk.seen = True
        fc.update(frame(10.0, "hidden", 0.0, 0.0, hidden=True, conf=0.0))
        assert trk.last_anchor is None or trk.last_family != "BB_BURST"
        t = 11.0
        if told:
            fc.update(frame(t, "burst_tell", 88.0, 0.0, hidden=True))
            assert trk.state == "burst_tell" and trk.last_anchor.x == 88.0
            roots, ok = trk.roots(t)
            assert ok and roots[0].state == "Burst Antic" and roots[0].ctx.anchor.x == 88.0
            assert {p.anchor for p in fc.forecast(2.0).placements if p.anchor is not None} == {(88.0, 5.49)}
            t += 1.2
        for k in range(3):
            fc.update(frame(t + k * BIN, "burst", 88.0 + off + 0.4 * k, k * BIN))
            assert trk.state == "burst" and trk.last_anchor is not None and trk.last_anchor.x == pytest.approx(88.0)
        fc.update(frame(t + 0.95, "hidden", 0.0, 0.0, hidden=True, conf=0.0))
        roots, _ = trk.roots(t + 0.95)
        assert roots[0].state == "Burst Recovery" and roots[0].ctx.anchor.x == pytest.approx(88.0)


def test_committed_keeps_the_current_attack_and_tails_only(model, templates):
    """Forecast.committed (tactics underground in the vision view): the next attack's branches are dropped, an ended
    burst's bells and the current attack up to its next decision are kept."""
    fc = _fc(model, templates, ORACLE, [Root("Submerged", -0.2, -0.2, Ctx(phase="P1", raged=True, hp=100.0))])
    fc.tracker.ends = [("BB_BURST", Anchor(86.0, 5.49, 1), -0.5, -0.5, "P1", False)]
    f = fc.forecast(3.0, 0.0)
    keys = {p.key.split("/")[1] for p in f.placements}
    assert {"BB_CHARGE", "BB_LEAP", "BB_BURST"} <= keys
    assert {p.key for p in f.committed().placements} == {"support/BB_BURST/_tail/anchor"}
    an = model.anchor("BB_CHARGE", "Set L")
    fc = _fc(model, templates, ORACLE, [Root("Charge", -0.1, -0.1, Ctx("BB_CHARGE", "Set L", an, "P1", False),
                                             current=True)])
    f = fc.forecast(5.0, 0.0)                    # long enough for the next attack (Dig In, Submerged 1 s, antic 1 s)
    kept = f.committed().placements
    assert kept and {p.key.split("/")[1] for p in kept} == {"BB_CHARGE"} and len(kept) < len(f.placements)


def test_ve_dust_cues_start_the_walk_in_the_antic(model, templates):
    """Dust cues (ObservabilityFilter tells, PlannerPolicy DUST_TELL): dust at an anchor roots both a charge and a
    leap from that side, entered TELL_DELAY earlier; low / tall dust one of them; dust in the burst range a burst at
    its x."""
    from ssbot.combat.forecast import TELL_DELAY, TELL_SLACK_S
    from ssbot.core.worldstate import E, Entity, Kind, PhasePost, WorldState

    def frame(t, phase, x, tau):
        ws = WorldState()
        ws.stamp.t_game_s = t
        ws.entities = [Entity(id=7, kind=Kind.BOSS, type_key=E("Bone Beast"), pos=E((x, 3.0), conf=1.0),
                              phase=PhasePost(topk=[(phase, 1.0)], t_in_phase=tau), hidden=True, visible_frac=0.0)]
        return ws

    fc = _fc(model, templates, VISION_EQUIVALENT)
    trk = fc.tracker
    trk.seen = True
    fc.update(frame(10.0, "hidden", 0.0, 0.0))
    fc.update(frame(11.3, "dust", 95.72, 0.0))
    roots, ok = trk.roots(11.3)
    assert ok and {(r.state, r.ctx.family, r.ctx.direction) for r in roots} == {
        ("Emerge Antic C", "BB_CHARGE", "Set R"), ("Emerge Antic L", "BB_LEAP", "Set R")}
    for r in roots:
        assert r.ctx.anchor.x == pytest.approx(95.72) and r.p == 0.5
        assert r.e_lo == pytest.approx(-0.3 - 0.1) and r.e_hi == pytest.approx(-0.3 + 0.1)
    fc.update(frame(11.6, "dust_tall", 95.72, 0.0))
    roots, _ = trk.roots(11.6)
    assert [(r.state, r.ctx.family, r.ctx.direction, r.ctx.anchor.x) for r in roots] == [
        ("Emerge Antic L", "BB_LEAP", "Set R", pytest.approx(95.72))]
    assert roots[0].e_lo == pytest.approx(-TELL_DELAY["dust_tall"] - TELL_SLACK_S["dust_tall"])
    fc = _fc(model, templates, VISION_EQUIVALENT)
    fc.tracker.seen = True
    fc.update(frame(20.0, "hidden", 0.0, 0.0))
    fc.update(frame(21.3, "dust_burst", 84.2, 0.0))
    roots, _ = fc.tracker.roots(21.3)
    assert [(r.state, r.ctx.family, r.ctx.anchor.x) for r in roots] == [("Burst Antic", "BB_BURST", 84.2)]
    assert {p.anchor for p in fc.forecast(2.0).placements if p.anchor is not None} == {(84.2, 5.49)}
