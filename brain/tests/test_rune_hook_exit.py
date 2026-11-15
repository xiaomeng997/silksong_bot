"""SSBOT_FORUM_RUNE_HOOK_EXIT (Task 182 seq 387 / 388): the empty-hook exit's branch admission and its record-only wiring.

Synthetic geometry here proves MODULE behaviour only (a branch the admission must see, a hazard only a derived branch or only the
physical lane meets), never a live trigger."""
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
from tests.test_knife_chain_transfer import fit_pose


class Forecast:
    """A stand-in for the planner's forecast: only its damage support occ(cx, cy, tk) -> bool [N, T] is read by the admission."""

    def __init__(self, occ=None):
        self.occ = occ

    def targets(self, tk):          # never read for a body route (seq 388 P2-B)
        raise AssertionError("the admission must not read the forecast's constant-velocity targets")

    def occupied(self, x, y, tk):
        x = np.asarray(x, float)
        return np.zeros(x.shape, bool) if self.occ is None else self.occ(x, np.asarray(y, float), np.asarray(tk, float))


def clapper(iid, state, t, x, flip=False, vel=(0., 0.)):
    """A production-shaped Clapper in its fitted pose (tests.test_knife_chain_transfer.fit_pose)."""
    e = {"iid": iid, "type_key": "Song Heavy Sentry", "hp": 100, "pos": [x, 7.45], "vel": list(vel), "flipX": flip, "is_dead": False,
         "fsms": [{"name": "Control", "state": state, "t": t}],
         "colliders": [{"name": "Song Heavy Sentry Body", "enabled": True, "verts_world": []}]}
    return fit_pose(e)


def observed(enemies):
    from ssbot.combat.knife_chain_air import body_box
    return [(int(e["iid"]), tuple(float(v) for v in body_box(e))) for e in enemies]


def _lanes(sim, d=1):
    """{(throw, late, catch, control, lane): pivots [E + 1, 2] from f} for every variant and branch of this scene."""
    out = {}
    for throw in (9, 8):
        for late in (0, 1, 2):
            made = N.compile_empty(sim, 0., [], d, throw_frames=throw, activation_delay=late)
            P = made.activation_frame - sim.fo
            lp, lr = made.path.states[[K.PX, K.PY], :P + 1].T, made.path.pos[:P + 1]
            for cs, rr, phys, rend in R.branch_paths(made, sim, d, throw):
                out[(throw, late, cs, rr, "physical")] = np.vstack((lp, phys[1:]))
                out[(throw, late, cs, rr, "rendered")] = np.vstack((lr, rend[1:]))
    return out


def _cx(sim, piv):
    b = N._boxes(piv, sim.params.vector())
    return 0.5 * (b[:, 0] + b[:, 2])


@pytest.mark.parametrize("throw", [9, 8])
@pytest.mark.parametrize("vy", [0., -15., 8.])
def test_the_measured_branch_is_hero2_claw_unhooked_exactly(throw, vy):
    from ssbot.map2.strike import steps_of
    sh = throw - H2.CLAW_THROW_F
    for phase in range(6):
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
    cs, rr, phys, rend = next(b for b in br if b[0] == 0 and b[1] == 32)
    np.testing.assert_allclose(phys[:33], made.path.states[[K.PX, K.PY], P:P + 33].T, atol=1e-12)
    np.testing.assert_allclose(rend[1:33], made.path.pos[P + 1:P + 33], atol=1e-12)


def test_a_clean_flight_admits_every_variant_and_branch_module_positive_only():
    ok, why, info = R.admit(scene(vy=0.), 0., [], 1, Forecast(), np.zeros((0, 6)))
    assert ok and why is None and info == {"variants": 6, "branches": 48}


def test_a_hazard_only_an_early_restore_branch_reaches_rejects():
    sim = scene(vy=0.)
    lanes = _lanes(sim)
    reach = max(_cx(sim, v)[-1] for (t, l, cs, rr, ln), v in lanes.items() if cs == 0 and rr == 32 + (t - 9))
    assert any(_cx(sim, v)[-1] > reach + 0.05 for v in lanes.values())
    occ = lambda cx, cy, tk: cx > reach + 0.05
    ok, why, _ = R.admit(scene(vy=0.), 0., [], 1, Forecast(occ=occ), np.zeros((0, 6)))
    m = re.match(r"throw (\d) late (\d) catch ([+-]\d) control P\+(\d+) (physical|rendered): forecast damage", why or "")
    assert not ok and m is not None, why
    assert int(m[3]) == 0 and int(m[4]) != 32 + (int(m[1]) - 9)     # a restore phase, not the measured branch


def test_a_hazard_only_the_early_catch_branch_meets_rejects():
    sim = scene(vy=0.)
    lanes = _lanes(sim)
    measured = np.stack([_cx(sim, v) for (t, l, cs, rr, ln), v in lanes.items() if cs == 0])
    thr = measured.min(axis=0) - 0.05           # behind every measured-Catch branch of every variant, lane and restore phase
    assert any((_cx(sim, v)[28:] < thr[28:]).any() for (t, l, cs, rr, ln), v in lanes.items() if cs == -1)

    def occ(cx, cy, tk):
        out = np.zeros(cx.shape, bool)
        out[..., 28:] = cx[..., 28:] < thr[28:]
        return out
    ok, why, _ = R.admit(scene(vy=0.), 0., [], 1, Forecast(occ=occ), np.zeros((0, 6)))
    assert not ok and "catch -1" in why and "forecast damage" in why, why


def test_terrain_only_a_derived_branch_reaches_rejects_although_every_nominal_flight_is_clear():
    sim = scene(vy=0.)
    lanes = _lanes(sim)
    p = sim.params.vector()
    nominal = [N._boxes(v, p) for (t, l, cs, rr, ln), v in lanes.items() if cs == 0 and rr == 32 + (t - 9)]
    regions = np.vstack([N._sweeps(b) for b in nominal])
    pt = None
    for (t, l, cs, rr, ln), v in sorted(lanes.items()):
        if (cs, rr) == (0, 32 + (t - 9)):
            continue
        for b in N._boxes(v, p)[::-1]:
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


def test_a_body_route_only_the_physical_ram_box_meets_rejects(monkeypatch):
    # seq 388 P2-A: the physical pivot leads the rendered one inside a frame (alpha), so its ram box reaches further ahead
    sim = scene(vy=0.)
    made = N.compile_empty(sim, 0., [], 1)
    P = made.activation_frame - sim.fo
    lp, lr = made.path.states[[K.PX, K.PY], :P + 1].T, made.path.pos[:P + 1]
    cs, rr, phys, rend = R.branch_paths(made, sim, 1, 9)[0]                 # the first branch the admission checks
    p = sim.params.vector()
    rp = R.lane_regions(np.vstack((lp, phys[1:])), p, 1, P, 9, cs)
    rd = R.lane_regions(np.vstack((lr, rend[1:])), p, 1, P, 9, cs)
    gap = np.where(rp[5], rp[4][:, 2] - rd[4][:, 2], -1.)
    k = int(np.argmax(gap))
    assert gap[k] > 0.2, "the physical ram front should lead the rendered one by part of a dash step"
    x0, x1 = rd[4][k, 2] + 0.05, rp[4][k, 2] - 0.05
    y0, y1 = rp[4][k, 1] + 0.1, rp[4][k, 3] - 0.1
    route = np.tile([200., 3.015, 202., 7.], (R.E_IDX + 1, 1))
    route[k + 1] = [x0, y0, x1, y1]                                          # ram row k is frame k + 1
    monkeypatch.setattr(R, "body_routes", lambda enemies, E=R.E_IDX: ({77: route}, None))
    ok, why, _ = R.admit(scene(vy=0.), 0., [], 1, Forecast(), np.zeros((0, 6)))
    assert not ok and why.startswith(f"throw 9 late 0 catch {cs:+d} control P+{rr}: physical ram box meets body route 77"), why


def test_a_moving_clapper_has_no_body_route_and_rejects_whatever_its_velocity_box_says():
    # seq 388 P2-B: an evade moves its root - no fitted support; the forecast's constant-velocity box is never asked
    mover = {"iid": 9, "type_key": "Song Heavy Sentry", "hp": 100, "pos": [45., 7.45], "vel": [18., 0.], "flipX": True,
             "is_dead": False, "fsms": [{"name": "Control", "state": "Evade Scuttle", "t": 0.1}],
             "colliders": [{"name": "Song Heavy Sentry Body", "enabled": True,
                            "verts_world": [43.7, 3.015, 47.3, 3.015, 47.3, 6.9, 43.7, 6.9]}]}
    ok, why, _ = R.admit(scene(vy=0.), 0., observed([mover]), 1, Forecast(), np.zeros((0, 6)), enemies=[mover])
    assert not ok and why == "body route unknown for 9 (Evade Scuttle)"


def test_a_caster_rising_into_the_ray_band_rejects_although_its_observed_box_is_clear():
    # seq 388 P2-B with the fitted data: Spell Antic's top rises 3.18 -> 4.76 over the floor within ten frames
    caster = clapper(8, "Spell Antic", 0., 33.)
    bodies = observed([caster])
    bottom = 6.8                                             # she sinks about 0.4 u to control: still above the observed top
    assert bodies[0][1][3] < bottom - 0.2 and bodies[0][1][3] + 1.5 > bottom + 0.5
    sim = scene(vy=0., y=bottom + 1.553)
    for throw in (9, 8):
        for late in (0, 1, 2):
            N.compile_empty(scene(vy=0., y=bottom + 1.553), 0., bodies, 1, throw_frames=throw, activation_delay=late)  # static: clear
    ok, why, _ = R.admit(sim, 0., bodies, 1, Forecast(), np.zeros((0, 6)), enemies=[caster])
    assert not ok and "ray meets body route 8" in why, why


def test_an_observed_body_without_its_entity_opposite_key_and_no_sideways_exit_reject():
    ok, why, _ = R.admit(scene(vy=0.), 0., [(8, (60., 3.015, 63., 6.9))], 1, Forecast(), np.zeros((0, 6)))
    assert not ok and why == "an observed body has no entity for its route"
    s2 = scene(vy=0.)
    s2.prefix[0] = K.B_LEFT
    ok, why, _ = R.admit(s2, 0., [], 1, Forecast(), np.zeros((0, 6)))
    assert not ok and why == "opposite side key in flight"
    x0 = float(s2.start[K.PX])
    rows = np.array([[-1., x0 + 11., 3.342, 7.187, 60., 70.]])
    ok, why, _ = R.admit(scene(vy=0.), 0., [], 1, Forecast(), rows)
    assert not ok and "not sideways out" in why


def _stub_policy(sim, rows, events=()):
    return SimpleNamespace(params=sim.params, terrain=sim.terrain, _rune_rows=lambda: rows,
                           chain_native=SimpleNamespace(events=deque(events, maxlen=50)))


def _state(sim, f, states):
    """A STATE at frame f: the hero of the scene, a Clapper per {iid: Control state}."""
    x, y = float(sim.start[K.PX]), float(sim.start[K.PY])
    ents = [{"iid": i, "type_key": "Song Heavy Sentry", "hp": 100, "pos": [60. + 5 * n, 4.5],
             "fsms": [{"name": "Control", "state": st, "t": 0.1}], "colliders": []} for n, (i, st) in enumerate(states.items())]
    return {"f": f, "hero": {"box": [x - .25, y - 1.553, x + .25, y + .532], "can": {"harpoon": True}, "silk": 3,
                             "hero_accepting_input": True, "facing": 1}, "ents": ents}


WS = SimpleNamespace(hero=SimpleNamespace(contact=SimpleNamespace(v="AIR")), stamp=SimpleNamespace(t_game_s=1.0))


def _tick(rec, pol, sim, f, states, own, name, target, forced=False):
    return rec.record(pol, _state(sim, f, states), f, f, WS, sim.start, sim.prefix, sim.hold,
                      SimpleNamespace(name=name, forced_risk=forced), Forecast(), SimpleNamespace(target=target), own)


@pytest.fixture
def recorder_env(monkeypatch):
    calls = []
    monkeypatch.setattr(R, "admit", lambda *a, **k: (calls.append(a) or (True, None, {"variants": 6, "branches": 48})))
    sim = scene(vy=0.)
    rows = np.array([[-1., float(sim.start[K.PX]), 3.342, 7.187, 40., 50.]])   # she is inside a not-lit big circle
    return sim, _stub_policy(sim, rows), calls


def test_a_real_chain_hand_back_keeps_the_failure_events_identity_never_the_focus(recorder_env):
    sim, pol, calls = recorder_env
    rec = R.Recorder()
    a = _tick(rec, pol, sim, 100, {8: "Idle"}, "chain", "CHAIN B2 active rune_transfer.air", 8)
    assert not a["h1"] and a["first_reject"] == "plan" and not calls
    pol.chain_native.events.append({"event": "transfer_no_witness_handback", "episode": 34, "frame": 101, "target": 3877540,
                                    "reason": "no fitted still pose in Evade Scuttle", "owner": "B2 recovery hands back"})
    b = _tick(rec, pol, sim, 101, {8: "Idle"}, "plan", "MOVE(R)+runR8_stop", 8)
    assert b["h1"] and b["h1_cause"] == "chain failure event" and b["entry"] and len(calls) == 1
    ev = b["h1_events"][0]
    assert ev["event"] == "transfer_no_witness_handback" and ev["target"] == 3877540 and ev["episode"] == 34 and ev["frame"] == 101
    assert b["h1_failure_targets"] == [3877540]            # the event's own target, not the focus 8


def test_a_supervisor_over_a_chain_row_is_no_chain_hold_and_no_hand_back(recorder_env):
    sim, pol, calls = recorder_env
    rec = R.Recorder()
    _tick(rec, pol, sim, 100, {8: "Idle"}, "sup", "CHAIN B2 active rune_transfer.air", 8)
    b = _tick(rec, pol, sim, 101, {8: "Idle"}, "plan", "MOVE(R)+runR8_stop", 8)
    assert not b["h1"] and b["h1_cause"] is None and not b["entry"] and not calls
    # the planner sending a chain row as its own pick does hold the keys (its mask is that row's)
    rec2 = R.Recorder()
    _tick(rec2, pol, sim, 200, {8: "Idle"}, "plan", "CHAIN B2 active rune_transfer.air", 8)
    c = _tick(rec2, pol, sim, 201, {8: "Idle"}, "plan", "WAIT", 8)
    assert c["h1"] and c["h1_cause"] == "unknown" and c["h1_events"] == [] and c["h1_failure_targets"] == []


def test_evade_edges_need_a_known_previous_state_of_the_same_iid(recorder_env):
    sim, pol, calls = recorder_env
    rec = R.Recorder()
    a = _tick(rec, pol, sim, 100, {8: "Evade Scuttle", 9: "Idle"}, "plan", "MOVE", 8)
    assert not a["h2"] and a["h2_status"] == "unknown: no previous state"           # first sight of an evading target
    b = _tick(rec, pol, sim, 101, {8: "Evade Scuttle", 9: "Evade Scuttle"}, "plan", "MOVE", 9)
    assert b["h2"] and b["h2_state"] == ["Idle", "Evade Scuttle"]   # 9 was tracked Idle on the last tick: a real transition
    c = _tick(rec, pol, sim, 102, {8: "Evade Scuttle", 9: "Evade Scuttle"}, "plan", "MOVE", 8)
    assert not c["h2"] and c["h2_status"] == "no change"   # a focus switch to an evading target is no transition
    d = _tick(rec, pol, sim, 103, {8: "Idle", 9: "Evade Scuttle"}, "plan", "MOVE", 8)
    e = _tick(rec, pol, sim, 104, {8: "Evade Scuttle", 9: "Evade Scuttle"}, "plan", "MOVE", 8)
    assert not d["h2"] and e["h2"] and e["h2_state"] == ["Idle", "Evade Scuttle"] and e["entry"]
    f_ = _tick(rec, pol, sim, 110, {8: "Idle"}, "plan", "MOVE", 8)
    g = _tick(rec, pol, sim, 120, {8: "Evade Scuttle"}, "plan", "MOVE", 8)
    assert not g["h2"] and g["h2_status"] == "unknown: no previous state"           # a gap: the change may lie in it


def test_mode_one_is_refused_and_zero_is_off(monkeypatch):
    monkeypatch.setenv("SSBOT_FORUM_RUNE_HOOK_EXIT", "1")
    with pytest.raises(ValueError, match="not implemented"):
        importlib.reload(R)
    monkeypatch.setenv("SSBOT_FORUM_RUNE_HOOK_EXIT", "2")
    assert importlib.reload(R).RECORD
    monkeypatch.setenv("SSBOT_FORUM_RUNE_HOOK_EXIT", "0")
    assert not importlib.reload(R).RECORD
