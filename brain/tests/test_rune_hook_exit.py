"""SSBOT_FORUM_RUNE_HOOK_EXIT (Task 182 seq 387): the empty-hook exit's branch admission and its record-only wiring.

Synthetic geometry here proves MODULE behaviour only (a branch the admission must see, a hazard only a derived branch meets),
never a live trigger."""
import importlib
import re
from collections import deque
from types import SimpleNamespace

import numpy as np
import pytest

from ssbot.combat import knife_chain_empty_needle as N
from ssbot.combat import rune_hook_exit as R
from ssbot.knowledge import kinematics as K, hero2 as H2
from tests.test_empty_needle import scene


class Forecast:
    """A stand-in for the planner's forecast: static bodies [(iid, box)], a damage support occ(cx, cy, tk) -> bool [N, T]."""

    def __init__(self, bodies=(), occ=None, drop=()):
        self.bodies, self.occ, self.drop = list(bodies), occ, set(drop)

    def targets(self, tk):
        return [SimpleNamespace(iid=i, type_key="Clapper", box=np.repeat(np.array([b], float), len(tk), axis=0),
                                ok=np.ones(len(tk), bool), hazard=False, blocked=False) for i, b in self.bodies if i not in self.drop]

    def occupied(self, x, y, tk):
        x = np.asarray(x, float)
        return np.zeros(x.shape, bool) if self.occ is None else self.occ(x, np.asarray(y, float), np.asarray(tk, float))


def _centres(full):
    return 0.5 * (full[:, 0] + full[:, 2]), 0.5 * (full[:, 1] + full[:, 3])


def _all_branches(sim, d=1):
    """{(throw, late, catch, control): full boxes from f} for every variant of this scene."""
    p = sim.params.vector()
    out = {}
    for throw in (9, 8):
        for late in (0, 1, 2):
            made = N.compile_empty(sim, 0., [], d, throw_frames=throw, activation_delay=late)
            P = made.activation_frame - sim.fo
            for cs, rr, phys, rend in R.branch_paths(made, sim, d, throw):
                out[(throw, late, cs, rr)] = np.vstack((made.path.box[:P + 1], N._boxes(rend[1:], p)))
    return out


@pytest.mark.parametrize("throw", [9, 8])
@pytest.mark.parametrize("vy", [0., -15., 8.])
def test_the_measured_branch_is_hero2_claw_unhooked_exactly(throw, vy):
    sh = throw - H2.CLAW_THROW_F
    for phase in range(6):
        from ssbot.map2.strike import steps_of
        fs = [steps_of(j, phase) for j in range(1, 40)]
        a = H2.claw_unhooked(27., 8.5, 3., vy, 1, fs, throw)
        b = R._track(27., 8.5, 3., vy, 1, fs, throw, 0, H2.CLAW_CTRL_F + sh)
        for k in ("x", "bb", "vx", "vy"):
            np.testing.assert_array_equal(getattr(a, k), getattr(b, k))
        assert a.ctrl == b.ctrl


def test_every_variant_has_both_catch_hypotheses_crossed_with_every_restore_phase():
    sim = scene(vy=0.)
    made = N.compile_empty(sim, 0., [], 1)
    br = R.branch_paths(made, sim, 1, 9)
    assert sorted((cs, rr) for cs, rr, _, _ in br) == sorted((cs, r) for cs in (0, -1) for r in (30, 31, 32, 33))
    P = made.activation_frame - sim.fo
    for cs, rr, phys, rend in br:
        assert len(phys) == len(rend) == R.E_IDX - P + 1
    # the measured branch up to its control is the module's own flight
    cs, rr, phys, rend = next(b for b in br if b[0] == 0 and b[1] == 32)
    np.testing.assert_allclose(phys[:33], made.path.states[[K.PX, K.PY], P:P + 33].T, atol=1e-12)
    np.testing.assert_allclose(rend[1:33], made.path.pos[P + 1:P + 33], atol=1e-12)


def test_a_clean_flight_admits_every_variant_and_branch_module_positive_only():
    ok, why, info = R.admit(scene(vy=0.), 0., [], 1, Forecast(), np.zeros((0, 6)))
    assert ok and why is None and info == {"variants": 6, "branches": 48}


def test_a_hazard_only_an_early_restore_branch_reaches_rejects():
    sim = scene(vy=0.)
    br = _all_branches(sim)
    measured = [v for (t, l, cs, rr), v in br.items() if cs == 0 and rr == 32 + (t - 9)]
    reach = max(_centres(b)[0][-1] for b in measured)
    occ = lambda cx, cy, tk: cx > reach + 0.05
    assert any(_centres(v)[0][-1] > reach + 0.05 for v in br.values())
    ok, why, _ = R.admit(scene(vy=0.), 0., [], 1, Forecast(occ=occ), np.zeros((0, 6)))
    m = re.match(r"throw (\d) late (\d) catch ([+-]\d) control P\+(\d+): forecast damage", why or "")
    assert not ok and m is not None, why
    assert int(m[3]) == 0 and int(m[4]) != 32 + (int(m[1]) - 9)     # a restore phase, not the measured branch


def test_a_hazard_only_the_early_catch_branch_meets_rejects():
    sim = scene(vy=0.)
    br = _all_branches(sim)
    measured = np.stack([_centres(v)[0] for (t, l, cs, rr), v in br.items() if cs == 0])
    thr = measured.min(axis=0) - 0.05           # behind every measured-Catch branch of every variant and restore phase
    assert any((_centres(v)[0][28:] < thr[28:]).any() for (t, l, cs, rr), v in br.items() if cs == -1), \
        "the early Catch should trail every measured-Catch branch late in the flight"

    def occ(cx, cy, tk):
        out = np.zeros(cx.shape, bool)
        out[..., 28:] = cx[..., 28:] < thr[28:]
        return out
    ok, why, _ = R.admit(scene(vy=0.), 0., [], 1, Forecast(occ=occ), np.zeros((0, 6)))
    assert not ok and "catch -1" in why and "forecast damage" in why, why


def test_terrain_only_a_derived_branch_reaches_rejects_although_every_nominal_flight_is_clear():
    sim = scene(vy=0.)
    br = _all_branches(sim)
    p = sim.params.vector()
    nominal = [v for (t, l, cs, rr), v in br.items() if cs == 0 and rr == 32 + (t - 9)]
    regions = np.vstack([np.column_stack((np.minimum(b[:-1, :2], b[1:, :2]), np.maximum(b[:-1, 2:], b[1:, 2:]))) for b in nominal])
    pt = None
    for (t, l, cs, rr), v in sorted(br.items()):
        if (cs, rr) == (0, 32 + (t - 9)):
            continue
        for b in v[::-1]:
            x, y = b[2] - 0.03, b[1] + 0.05
            inside = ((regions[:, 0] - .1 <= x) & (x <= regions[:, 2] + .1) & (regions[:, 1] - .1 <= y) & (y <= regions[:, 3] + .1)).any()
            if not inside and x > b[0]:
                pt = (x, y)
                break
        if pt:
            break
    assert pt is not None, "no point that only a derived branch reaches"
    def terr(s):
        t_ = K.Terrain2D.from_boxes([(-100., -10., 100., 3.015)])
        t_.slopes = np.array([[pt[0] - .01, pt[1] - .01, pt[0] + .01, pt[1] + .01]])
        s.terrain = t_
        return s
    for throw in (9, 8):
        for late in (0, 1, 2):
            N.compile_empty(terr(scene(vy=0.)), 0., [], 1, throw_frames=throw, activation_delay=late)   # every nominal flight clear
    ok, why, _ = R.admit(terr(scene(vy=0.)), 0., [], 1, Forecast(), np.zeros((0, 6)))
    assert not ok and ("sloped terrain in reach" in why or "ray meets terrain" in why)


def test_missing_forecast_body_opposite_key_and_a_late_inside_circle_reject():
    sim = scene(vy=0.)
    ok, why, _ = R.admit(sim, 0., [(8, (60., 3.015, 63., 6.9))], 1, Forecast(bodies=[(8, (60., 3.015, 63., 6.9))], drop={8}),
                         np.zeros((0, 6)))
    assert not ok and "does not cover observed body 8" in why
    s2 = scene(vy=0.)
    s2.prefix[0] = K.B_LEFT
    ok, why, _ = R.admit(s2, 0., [], 1, Forecast(), np.zeros((0, 6)))
    assert not ok and why == "opposite side key in flight"
    x0 = float(s2.start[K.PX])
    # a big circle whose octagon still holds her at control (centre well ahead of where the hook stops)
    rows = np.array([[-1., x0 + 11., 3.342, 7.187, 60., 70.]])
    ok, why, _ = R.admit(scene(vy=0.), 0., [], 1, Forecast(), rows)
    assert not ok and "not sideways out" in why


def _stub_policy(sim, rows, events=()):
    return SimpleNamespace(params=sim.params, terrain=sim.terrain, _rune_rows=lambda: rows,
                           chain_native=SimpleNamespace(events=deque(events, maxlen=50)))


def _state(sim, target_state, f):
    x, y = float(sim.start[K.PX]), float(sim.start[K.PY])
    clap = {"iid": 8, "type_key": "Heavy Sentry", "hp": 100, "pos": [60., 4.5],
            "fsms": [{"name": "Control", "state": target_state, "t": 0.1}], "colliders": []}
    return {"f": f, "hero": {"box": [x - .25, y - 1.553, x + .25, y + .532], "can": {"harpoon": True}, "silk": 3,
                             "hero_accepting_input": True, "facing": 1}, "ents": [clap]}


def test_the_record_edges_causes_and_entry_never_touch_the_tick(monkeypatch):
    from ssbot.combat import slam_play
    monkeypatch.setattr(slam_play, "CLAPPER", "Heavy Sentry")
    calls = []
    monkeypatch.setattr(R, "admit", lambda *a, **k: (calls.append(a) or (True, None, {"variants": 6, "branches": 48})))
    sim = scene(vy=0.)
    x0 = float(sim.start[K.PX])
    rows = np.array([[-1., x0, 3.342, 7.187, 40., 50.]])
    ws = SimpleNamespace(hero=SimpleNamespace(contact=SimpleNamespace(v="AIR")), stamp=SimpleNamespace(t_game_s=1.0))
    prefs = SimpleNamespace(target=8)
    rec = R.Recorder()
    pol = _stub_policy(sim, rows)
    a = rec.record(pol, _state(sim, "Idle", 100), 100, 100, ws, sim.start, sim.prefix, sim.hold,
                   SimpleNamespace(name="CHAIN B2 active rune_transfer.air", forced_risk=False), Forecast(), prefs, "chain")
    assert not a["h1"] and not a["entry"] and a["first_reject"] == "plan" and a["admission"] is None and not calls
    pol.chain_native.events.append({"event": "chain_interrupted", "frame": 101, "reason": "no fitted still pose in Evade Scuttle"})
    b = rec.record(pol, _state(sim, "Evade Scuttle", 101), 101, 101, ws, sim.start, sim.prefix, sim.hold,
                   SimpleNamespace(name="MOVE(R)+runR8_stop", forced_risk=False), Forecast(), prefs, "plan")
    assert b["h1"] and b["h1_cause"] == "chain failure event" and b["h1_events"][0][0] == "chain_interrupted"
    assert b["h2"] and b["h2_state"] == ["Idle", "Evade Scuttle"] and b["gate"]["inside_not_lit"] and b["entry"]
    assert b["admission"]["ok"] and b["intersection"] and b["first_reject"] is None and len(calls) == 1
    c = rec.record(pol, _state(sim, "Evade Scuttle", 102), 102, 102, ws, sim.start, sim.prefix, sim.hold,
                   SimpleNamespace(name="MOVE(R)+runR8_stop", forced_risk=False), Forecast(), prefs, "plan")
    assert not c["h1"] and not c["h2"] and not c["n1"] and not c["entry"] and c["first_reject"].startswith("no candidate edge")
    d = rec.record(pol, _state(sim, "Evade Scuttle", 103), 103, 103, ws, sim.start, sim.prefix, sim.hold,
                   SimpleNamespace(name="MOVE(R)+runR8_stop", forced_risk=True), Forecast(), prefs, "plan")
    assert d["n1"] and d["entry"] and len(calls) == 2
    # a hand-back with no failure event of the chain is recorded as unknown, never as a failed plan
    rec2 = R.Recorder()
    rec2.record(pol, _state(sim, "Idle", 200), 200, 200, ws, sim.start, sim.prefix, sim.hold,
                SimpleNamespace(name="CHAIN B2 active x", forced_risk=False), Forecast(), prefs, "chain")
    e = rec2.record(pol, _state(sim, "Idle", 201), 201, 201, ws, sim.start, sim.prefix, sim.hold,
                    SimpleNamespace(name="WAIT", forced_risk=False), Forecast(), prefs, "plan")
    assert e["h1"] and e["h1_cause"] == "unknown" and e["h1_events"] == []


def test_mode_one_is_refused_and_zero_is_off(monkeypatch):
    monkeypatch.setenv("SSBOT_FORUM_RUNE_HOOK_EXIT", "1")
    with pytest.raises(ValueError, match="not implemented"):
        importlib.reload(R)
    monkeypatch.setenv("SSBOT_FORUM_RUNE_HOOK_EXIT", "2")
    assert importlib.reload(R).RECORD
    monkeypatch.setenv("SSBOT_FORUM_RUNE_HOOK_EXIT", "0")
    assert not importlib.reload(R).RECORD
