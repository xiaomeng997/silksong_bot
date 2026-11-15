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
    # (seq 391: the research path calls admit too, with research=...; the strict admission is the call without it)
    monkeypatch.setattr(R, "admit", lambda *a, **k: (calls.append((a, k)) or (True, None, {"variants": 6, "branches": 48})))
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
    assert b["h1"] and b["h1_cause"] == "chain failure event" and b["entry"]
    assert [("research" in k) for _a, k in calls] == [False, True]       # the strict admission once, the research path once
    assert b["research"]["label"].startswith("would / candidate") and b["sent"] is False
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


# ------------------------------------------------- seq 391: the record-only research path (empirical height) and the C1 record

from ssbot.combat import rune_life as RL  # noqa: E402

PEND_OK = {"pending": (True, None)}


def evader(iid=9, x=31., t=0.1, vx=15., flip=False, bottom=3.015, vy=0.):
    """An Evade Scuttle Clapper (SetVelocityByScale 15 away from its facing: flipX False faces -x, so vx +15), its Idle-sized box."""
    face = 1 if flip else -1
    xa, xb = x + face * 2.252, x - face * 1.341
    lo, hi = min(xa, xb), max(xa, xb)
    return {"iid": iid, "type_key": "Song Heavy Sentry", "hp": 100, "pos": [x, 7.449], "vel": [vx, vy], "flipX": flip,
            "is_dead": False, "fsms": [{"name": "Control", "state": "Evade Scuttle", "t": t}],
            "colliders": [{"name": "Song Heavy Sentry Body", "enabled": True,
                           "verts_world": [lo, bottom, hi, bottom, hi, bottom + 3.901, lo, bottom + 3.901]}]}


def test_research_is_explicit_and_the_default_admission_keeps_its_strict_domain():
    e = evader()
    ok, why, _ = R.admit(scene(vy=0., y=12.1), 0., observed([e]), 1, Forecast(), np.zeros((0, 6)), enemies=[e])
    assert not ok and why == "body route unknown for 9 (Evade Scuttle)"            # the default call: unchanged
    ok, why, info = R.admit(scene(vy=0., y=12.1), 0., observed([e]), 1, Forecast(), np.zeros((0, 6)), enemies=[e], research=PEND_OK)
    assert ok, why
    assert info["supports"] == {"9": "empirical height"} and info["heights"]["9"]["valid_to"] >= R.E_IDX
    assert info["height_margin"] > 0 and info["pending_attack"] == "none observed" and info["branches"] == 48
    assert R.HEIGHT_REF == 7.90 and R.HEIGHT_MARGIN == 0.50 and R.HEIGHT_THRESHOLD == pytest.approx(8.40)


def test_the_empirical_height_rejects_a_flight_that_comes_down_to_it():
    e = evader()
    ok, why, info = R.admit(scene(vy=0., y=10.12), 0., observed([e]), 1, Forecast(), np.zeros((0, 6)), enemies=[e], research=PEND_OK)
    assert not ok and "empirical height" in why and info["height_margin"] <= 0, why


def test_the_height_domain_is_checked_item_by_item_on_this_state():
    v, info = R.height_support(evader())
    assert v == (20 - 6 - 1) + 29 and info["take_off_from"] == 43 and info["state"] == "Evade Scuttle"   # raw minima, k 6
    v, info = R.height_support(clapper(8, "Slam Recover", 2 / 60, 21.325, flip=True))
    assert v == (14 - 2 - 1) + 29 and info["wall_u"] == pytest.approx(7.315)
    idle = evader()
    idle["fsms"][0]["state"] = "Idle"
    bad = {"state Idle outside the height domain": idle,
           "clock 22 at or past the raw maximum 22 of Evade Scuttle": evader(t=22 / 60),
           "not standing (body bottom over the floor or a vertical speed)": evader(bottom=3.4),
           "Evade Scuttle not at 15 u/s away from its facing": evader(vx=-15.),
           "Slam Recover frame 0 within the clock tolerance (hammer tail)": clapper(8, "Slam Recover", 1 / 60, 21.325, flip=True)}
    for why, e in bad.items():
        assert R.height_support(e) == (None, why), why
    assert R.height_support(evader(vx=18.))[1] == "Evade Scuttle not at 15 u/s away from its facing"
    assert R.height_support(evader(vy=-1.))[1].startswith("not standing")
    assert R.height_support(evader(x=40.))[1].startswith("a wall")                          # it scuttles to x 49.5 by index 37
    assert R.height_support(clapper(8, "Slam Recover", 2 / 60, 19.5, flip=True))[1].startswith("a wall")
    routes, heights, why = R.research_supports([evader(t=12 / 60)])
    assert routes is None and why == "body route unknown for 9 and its empirical height holds only to index 36"


def test_pending_attacks_and_missing_evidence_reject_the_research_path():
    sim = scene(vy=0.)
    names = K.cstate_names()

    def bits(*ns):
        v = [0, 0]
        for n in ns:
            i = names.index(n)
            v[i >> 6] |= 1 << (i & 63)
        return v
    clean = {"cstate": bits("facingRight", "falling")}               # the b35 F104247 bits
    raws = {g: {"f": g, "ev": []} for g in range(90, 101)}
    assert R.pending_attack(sim, clean, raws, 100, {9}) == (True, None)
    assert R.pending_attack(sim, {"cstate": bits("falling", "attacking")}, raws, 100, {9})[1] == "her attack under way (attacking)"
    assert R.pending_attack(sim, {}, raws, 100, {9})[1] == "her cstate unknown"
    s2 = scene(vy=0.)
    s2.prefix[0] = K.B_ATTACK
    assert R.pending_attack(s2, clean, raws, 100, {9})[1] == "an attack key in flight"
    s3 = scene(vy=0.)
    s3.start[K.AQ] = 0.
    assert R.pending_attack(s3, clean, raws, 100, {9})[1] == "the model start has an attack queued"
    s4 = scene(vy=0.)
    s4.hold.latched[0, K.B_ATTACK.bit_length() - 1] = True
    assert R.pending_attack(s4, clean, raws, 100, {9})[1] == "an attack key in the hold filter"
    gap = dict(raws)
    del gap[95]
    assert "frame 95 not seen" in R.pending_attack(sim, clean, gap, 100, {9})[1]
    hit = {**raws, 97: {"f": 97, "ev": [{"k": "hit", "f": 97, "d": {"ent": 9, "attack": "Nail"}}]}}
    assert R.pending_attack(sim, clean, hit, 100, {9})[1].startswith("a hit on 9 at 97")
    other = {**raws, 97: {"f": 97, "ev": [{"k": "hit", "f": 97, "d": {"ent": 77}}]}}
    assert R.pending_attack(sim, clean, other, 100, {9}) == (True, None)     # a hit on a body not observed here
    frz = {**raws, 99: {"f": 99, "ev": [{"k": "freeze", "f": 99, "d": {}}]}}
    assert R.pending_attack(sim, clean, frz, 100, {9})[1] == "a freeze at 99"
    old = {**raws, 89: {"f": 89, "ev": [{"k": "hit", "f": 89, "d": {"ent": 9}}]}}
    assert R.pending_attack(sim, clean, old, 100, {9}) == (True, None)       # older than RECENT_F frames
    e = evader()
    ok, why, _ = R.admit(scene(vy=0., y=12.1), 0., observed([e]), 1, Forecast(), np.zeros((0, 6)), enemies=[e],
                         research={"pending": (False, "an attack key in flight")})
    assert not ok and why == "pending attack / effect: an attack key in flight"


R_IID, R_TGT, R_SRC = -2258876, 3877540, 3877546


def _cl(iid, x, state="Idle", dead=False):
    return {"iid": iid, "type_key": "Song Heavy Sentry", "hp": 0 if dead else 100, "pos": [x, 7.449], "is_dead": dead,
            "fsms": [{"name": "Control", "state": state, "t": 0.1}], "colliders": []}


class C1Env:
    """The Recorder over a stub policy with a REAL rune ledger (rune_life.RuneCircles) and a chain event deque, admit stubbed."""

    def __init__(self, monkeypatch):
        self.calls = []
        monkeypatch.setattr(R, "admit", lambda *a, **k: (self.calls.append("research" in k)
                                                         or (True, None, {"variants": 6, "branches": 48})))
        self.sim = scene(vy=0.)
        self.ledger = RL.RuneCircles()
        self.pol = SimpleNamespace(params=self.sim.params, terrain=self.sim.terrain, _rune_rows=lambda: self.ledger.rows(),
                                   chain_native=SimpleNamespace(events=deque(maxlen=200), episode=0), rune_life=self.ledger, raw={})
        self.rec = R.Recorder()

    def tick(self, f, own="plan", name="MOVE(R)+runR8_stop", ground=False, outside=False, clappers=None, circles=((28.07, False),),
             room="Hang_04", events=(), target=8):
        x, y = float(self.sim.start[K.PX]), float(self.sim.start[K.PY])
        hb = [x - .25, 10.6, x + .25, 12.7] if outside else [x - .25, y - 1.553, x + .25, y + .532]
        ents = list(clappers if clappers is not None else [_cl(R_TGT, 33.), _cl(R_SRC, 21.3)])
        for n, (cx, lit) in enumerate(circles):
            r = RL.RUNE_R
            ents.append({"iid": R_IID - n, "type_key": "damager", "pos": [cx, 3.34],
                         "colliders": [{"enabled": lit,
                                        "verts_world": [cx - r, 3.34 - r, cx + r, 3.34 - r, cx + r, 3.34 + r, cx - r, 3.34 + r]}]})
        s = {"f": f, "room": room, "ev": [], "ents": ents,
             "hero": {"box": hb, "can": {"harpoon": True}, "silk": 3, "hero_accepting_input": True, "facing": 1, "cstate": [1025, 0]}}
        self.pol.raw[f] = s
        self.ledger.update(f, s, f / 60.)
        for e in events:
            self.pol.chain_native.events.append({"episode": 0, **e})
        ws = SimpleNamespace(hero=SimpleNamespace(contact=SimpleNamespace(v="GROUND" if ground else "AIR")),
                             stamp=SimpleNamespace(t_game_s=f / 60.))
        return self.rec.record(self.pol, s, f, f, ws, self.sim.start, self.sim.prefix, self.sim.hold,
                               SimpleNamespace(name=name, forced_risk=False), Forecast(), SimpleNamespace(target=target), own)

    def failure(self, exposure=True, run_move=True, run_target=R_TGT, circles=((28.07, False),)):
        """Ticks 100 (the chain's Run owns the keys) and 101 (its failure hand-back, outside the circle), as bout 35's 104240-104241."""
        ev = [{"event": "b2_selected", "frame": 100, "move": {"target_iid": run_target, "antic_frame": 84, "family": "RUNE_TRANSFER"}}]
        self.tick(100, name="CHAIN B2 active rune_transfer.air", events=ev if run_move else (), circles=circles)
        ev = [{"event": "transfer_no_witness_handback", "frame": 101, "target": R_TGT, "reason": "no fitted still pose in Evade Scuttle",
               "owner": "B2 recovery hands back; failure responsibility kept"},
              {"event": "b2_recovery", "frame": 101, "reason": "transfer air run over its target with no strike witness"}]
        if exposure:
            ev.append({"event": "b2_failure_exposure", "frame": 101,
                       "exposure": {"move": {"target_iid": R_SRC, "antic_frame": 43, "family": "CC_JUMP_CAST"}, "origin": 84,
                                    "failed_frame": 101, "minimum_through": 131, "end_status": "unknown"}})
        ev.append({"event": "chain_interrupted", "frame": 101, "link": "rune_transfer.air", "reason": "no strike witness"})
        return self.tick(101, events=ev, outside=True, circles=circles)


def test_c1_record_binds_the_real_failure_identity_and_lives_outside_the_circle(monkeypatch):
    env = C1Env(monkeypatch)
    a = env.failure()
    assert a["h1"] and a["c1"]["status"] == "live" and not a["c1_entry"] and not a["gate"]["inside_not_lit"]
    idn = a["c1"]["record"]
    assert idn["failure"]["frame"] == 101 and idn["failure"]["target"] == R_TGT and idn["failure"]["episode"] == 0   # not the focus 8
    assert idn["run_move"] == {"target_iid": R_TGT, "antic_frame": 84, "family": "RUNE_TRANSFER", "frame": 100}
    assert idn["source_move"] == {"target_iid": R_SRC, "antic_frame": 43, "family": "CC_JUMP_CAST"} and idn["minimum_through"] == 131
    assert idn["circle"]["iid"] == R_IID and idn["circle"]["first_f"] == 100
    env.calls.clear()
    b = env.tick(102)                                                      # back inside the circle: the C1 entry (no N1 / H1 / H2)
    assert b["c1"]["status"] == "live" and b["c1_entry"] and not b["entry"] and b["admission"] is None
    assert env.calls == [True] and b["research"]["label"].startswith("would / candidate") and b["sent"] is False
    c = env.tick(103, clappers=[_cl(R_TGT, 33.), _cl(R_SRC, 21.3, dead=True)])
    assert c["c1"]["status"] == "live"                                     # the circle's source owner dying does not clear it


@pytest.mark.parametrize("kw,why", [
    ({"exposure": False}, "no same-frame failure exposure with its source move"),
    ({"run_move": False}, "the Run's own move not observed on the chain's last ticks"),
    ({"run_target": 999}, "the failure target is not the Run move's target"),
    ({"circles": ((28.07, False), (40.0, False))}, "big circle association not unique"),
    ({"circles": ()}, "no big circle alive at the failure")])
def test_c1_without_its_identity_or_a_unique_circle_is_unknown(monkeypatch, kw, why):
    env = C1Env(monkeypatch)
    a = env.failure(**kw)
    assert a["h1"] and a["c1"] == {"status": "unknown", "reason": why, "record": None}
    assert env.tick(102)["c1"]["status"] == "none"


@pytest.mark.parametrize("tick,why", [
    ({"ground": True}, "landing (the air phase ended)"),
    ({"name": "CHAIN B2 active rune_transfer.air"}, "a chain link is the final key owner again"),
    ({"own": "chain"}, "a chain link is the final key owner again"),
    ({"own": "sup"}, "a supervisor or script owner (sup)"),
    ({"own": "slam"}, "a supervisor or script owner (slam)"),
    ({"clappers": [_cl(R_TGT, 33., dead=True), _cl(R_SRC, 21.3)]}, "the failure target dead"),
    ({"circles": ((28.07, True),)}, "the bound circle lit"),
    ({"circles": ()}, "the bound circle not listed"),
    ({"circles": ((30.0, False),)}, "the bound circle's object re-created (a new generation)"),
    ({"room": "Hang_05"}, "scene changed")])
def test_c1_record_clears(monkeypatch, tick, why):
    env = C1Env(monkeypatch)
    assert env.failure()["c1"]["status"] == "live"
    assert env.tick(102)["c1"]["status"] == "live"
    c = env.tick(103, **tick)
    assert c["c1"]["status"] == "cleared" and c["c1"]["reason"] == why and c["c1"]["record"]["failure"]["frame"] == 101
    assert not c["c1_entry"]
    d = env.tick(104)                                                      # a cleared record never comes back (a chain that
    assert d["c1"]["status"] != "live" and d["c1"]["record"] is None      # held the keys hands back again: H1, unknown cause)


def test_c1_record_clears_on_an_unseen_target_and_on_a_record_gap(monkeypatch):
    env = C1Env(monkeypatch)
    env.failure()
    for f in (102, 103, 104):
        assert env.tick(f, clappers=[_cl(R_SRC, 21.3)])["c1"]["status"] == "live"       # unseen 1 .. 3 frames: still live
    assert env.tick(105, clappers=[_cl(R_SRC, 21.3)])["c1"]["reason"] == "the failure target unseen over MAX_GAP frames"
    env2 = C1Env(monkeypatch)
    env2.failure()
    assert env2.tick(106)["c1"]["reason"] == "a record gap over MAX_GAP frames"
