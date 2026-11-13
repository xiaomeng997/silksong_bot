"""Task 182 B13 (docs/plans/forum_clapper_committed_chain.md 2.3 / 5.1 / 6.1; the person 11-12 "先做committed chain吧"): the
rune_transfer Run's own still target body under the conditional rule. The air link's body guard (knife_chain_transfer.b13_guard)
reads the Run's own keys ahead to her landing on the real hero model; when they would put her into that body first it picks the
Run's own follow-up: a blade-first down slash (Idle's Will Evade taken as not evading, the small rune's opening pending or not), else
steering off within B13_LEAD_F, else the latest meeting (forced); farther away with no strike it waits. Rows of a still target are
turned down when her box meets its body before contact-2. Off (SSBOT_FORUM_CHAIN_B13=0): the old rows and no guard."""
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import knife_chain_transfer as T
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.knowledge import kinematics as K
from tests.test_shared_strike_approach import flight

TX = 36.5   # the Idle target's root: body box 34.25 .. 37.84, top 6.92 (fit_pose t 20/60)


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(T, "B13", True)


def _propose(x, y, vx, vy, *, evidence=True, atk_cd=None, idle_ev=None, **kw):
    r, s, sim = flight(x=x, y=y, vx=vx, vy=vy, target_x=TX)
    if not evidence:
        r.run.v["idle_in_range"] = None          # no in-range record of Will Evade shown False: the old witness ends at Can Evade
    if atk_cd is not None:
        sim.start[K.ATK_CD] = atk_cd             # no down slash can be pressed now
    if idle_ev is not None:
        kw["idle_evidence"] = {8: idle_ev}
    made = T.propose(r, s, (s["f"] - 1000) / 60., sim, 8, False, np.zeros((0, 6)), set(), **kw)
    assert made is not None and made[0] is not None
    return made, r, s, sim


def test_b13_follows_v2_unless_set():
    # SSBOT_FORUM_CHAIN_B13 unset follows SSBOT_FORUM_V2 (on in production, off in a plain test run); =0 / =1 decide
    assert T.B13 == T._env_on("SSBOT_FORUM_CHAIN_B13", T._ENV_V2)


def test_danger_is_a_still_targets_body_per_frame_and_none_otherwise(monkeypatch):
    _, _, s, _ = _propose(35.5, 10.12, 0., -.6)
    e = s["ents"][1]
    box = np.asarray(T.body_box(e), float)
    d = T.b13_danger(e, 6)
    assert d.shape == (6, 4) and np.allclose(d, box)                            # Idle: its one pose at every index
    # a timed still state: the union of its poses per index (its hull witness), index 0 with the observed box, the last held
    e["fsms"][0]["state"] = "Spell Antic"
    grow = np.array([[box[0], box[1], box[2], box[3] - .5], [box[0], box[1], box[2], box[3] + .5],
                     [box[0] - .2, box[1], box[2], box[3] + 1.]] + [[np.nan] * 4] * 2)
    seen = []
    monkeypatch.setattr(T, "contact_body_witness", lambda en, n, **kw: seen.append(kw) or grow)
    d = T.b13_danger(e, 6)
    assert seen and seen[0].get("hull") is True
    assert np.allclose(d[0], box) and np.allclose(d[1], grow[1]) and np.allclose(d[2], grow[2]) and np.allclose(d[5], grow[2])
    for state in ("Walk", "Evade Scuttle", "Slam Antic", "Slam 2", "Jump"):
        e["fsms"][0]["state"] = state
        assert T.b13_danger(e) is None


def test_hull_witness_is_the_union_of_the_same_poses():
    from tests.test_knife_chain_transfer import fit_pose
    _, _, s, _ = _propose(35.5, 10.12, 0., -.6)
    e = fit_pose(s["ents"][1], state="Spell Antic", t=.05)
    core = T.contact_body_witness(e, 20)
    hull = T.contact_body_witness(e, 20, hull=True)
    ok = np.isfinite(core).all(axis=1)
    assert ok.any() and np.isfinite(hull[ok]).all()
    assert (hull[ok, :2] <= core[ok, :2] + 1e-9).all() and (hull[ok, 2:] >= core[ok, 2:] - 1e-9).all()


def test_first_meet_reads_a_per_frame_body():
    boxes = np.array([[2., 0., 3., 1.], [2., 0., 3., 1.], [2., 0., 3., 1.], [2., 0., 3., 1.]])
    grows = np.array([[0., 0., 1., 1.], [0., 0., 1.5, 1.], [0., 0., 2.2, 1.]])        # the body reaches her at index 2, held after
    assert T.b13_first_meet(boxes, grows, 1, 4) == 2
    assert T.b13_first_meet(boxes, grows[:1], 1, 4) is None


def test_off_falling_onto_an_idle_without_its_evade_record_keeps_coasting(monkeypatch):
    monkeypatch.setattr(T, "B13", False)
    (draft, _, _, mask), _, _, _ = _propose(35.5, 10.12, 0., -.6, evidence=False)
    assert draft.run.link == "air" and mask == B["R"] and "b13" not in draft.run.v


def test_on_falling_onto_an_idle_without_its_evade_record_strikes_blade_first(on):
    (draft, _, _, mask), _, _, _ = _propose(35.5, 10.12, 0., -.6, evidence=False)
    rec = draft.run.v["b13"]
    assert draft.run.link == "strike" and mask & B["D"] and rec["kind"] == "strike"
    assert rec["contact_F"] < rec["meet_F"] - 2                # the blade lands before her box could meet the body
    assert draft.run.v["row"]["contact_frame"] == rec["contact_F"] and draft.run.v.get("b13_steer") is None


def test_on_a_still_target_row_is_turned_down_when_her_box_meets_its_body_before_contact_minus_2(on):
    (_, _, _, _), r, s, sim = _propose(35.5, 10.12, 0., -.6)
    body = T.contact_body_witness(s["ents"][1], len(sim.prefix) + 12, idle_no_evade=True)
    row = T.press_now_row(sim, body, 1002, 0, B["R"])
    assert row is not None
    hb = s["hero"]["box"]
    below = np.array([hb[0], hb[1] - .3, hb[2], hb[1] - .001])               # just under her feet: entered on her first steps down
    assert T.press_now_row(sim, body, 1002, 0, B["R"], danger=below) is None
    assert T.press_now_row(sim, body, 1002, 0, B["R"], danger=np.array(hb, float)) == row   # already inside: no entry, no veto
    far = np.array([60., 3., 61., 7.])
    assert T.press_now_row(sim, body, 1002, 0, B["R"], danger=far) == row


def test_first_meet_counts_an_entry_from_outside_only():
    body = np.array([0., 0., 1., 1.])
    boxes = np.array([[2., 0., 3., 1.], [1.5, 0., 2.5, 1.], [.5, 0., 1.5, 1.], [.2, 0., 1.2, 1.]])
    assert T.b13_first_meet(boxes, body, 1, 4) == 2
    inside = np.array([[.5, 0., 1.5, 1.], [.6, 0., 1.6, 1.], [1.2, 0., 2.2, 1.], [.9, 0., 1.9, 1.]])
    assert T.b13_first_meet(inside, body, 1, 4) == 3                           # left at 2, entered again at 3
    assert T.b13_first_meet(inside, body, 1, 3) is None


def test_on_already_inside_the_body_and_in_a_real_bounce_the_guard_reads_nothing(on):
    # she stands inside the body box now (the pogo protection after a real bounce, or a hit taken): no new meeting, no record
    (draft, _, _, _), _, _, _ = _propose(36.0, 7.2, 0., -10.2, atk_cd=1.)
    assert "b13" not in draft.run.v
    r, s, sim = flight(x=36.0, y=9.0, vx=0., vy=-10., target_x=TX)
    sim.start[K.ATK_CD] = 1.
    s["hero"]["anim"] = {"clip": "DownSpikeBounce 2"}
    made = T.propose(r, s, (s["f"] - 1000) / 60., sim, 8, False, np.zeros((0, 6)), set())
    assert "b13" not in made[0].run.v                                         # the B1 scene of the forced test, in a bounce clip


def test_on_a_hit_idle_is_never_struck_by_the_guard(on):
    (draft, _, _, _), _, _, _ = _propose(35.5, 10.12, 0., -.6, evidence=False, idle_ev={"entry": 980, "buddy": None, "hit": 995})
    assert draft.run.link == "air" and draft.run.v["b13"]["kind"] == "wait"


def test_on_no_strike_waits_while_the_meeting_is_far(on):
    (draft, _, _, mask), _, _, _ = _propose(35.5, 10.12, 0., -.6, evidence=False, no_strike=True)
    rec = draft.run.v["b13"]
    assert draft.run.link == "air" and mask == B["R"] and rec["kind"] == "wait" and rec["lead"] > T.B13_LEAD_F


def test_on_no_strike_row_near_the_edge_steers_off_and_keeps_the_steer(on):
    (draft, _, _, mask), r, s, sim = _propose(33.6, 8.6, 0., -6., atk_cd=1.)
    rec = draft.run.v["b13"]
    assert draft.run.link == "air" and rec["kind"] == "steer" and rec["lead"] <= T.B13_LEAD_F
    assert rec["steer"] == 0 and not mask & (B["L"] | B["R"]) and draft.run.v["b13_steer"] == 0
    # the next tick keeps the steer (its roll clear): no new decision, still no side key and no dash
    r.run = draft.run
    again = T.propose(r, s, (s["f"] - 1000) / 60., sim, 8, False, np.zeros((0, 6)), set())
    assert again[0].run.link == "air" and not again[3] & (B["L"] | B["R"] | B["DASH"])
    assert again[0].run.v["b13"] is rec or again[0].run.v["b13"] == rec


def test_on_nothing_clear_low_over_the_body_is_forced_to_the_latest_meeting(on):
    (draft, _, _, _), _, _, _ = _propose(36.0, 9.0, 0., -10.2, atk_cd=1.)
    rec = draft.run.v["b13"]
    assert draft.run.link == "air" and rec["kind"] == "forced" and rec["lead"] <= T.B13_LEAD_F
    assert len(rec["meets_F"]) == 3 and rec["meet_F"] == max(rec["meets_F"]) or rec["steer"] != rec["planned"]


def test_on_far_with_no_strike_row_waits_with_the_runs_own_keys(on):
    (draft, _, _, mask), _, _, _ = _propose(33.0, 11.5, 0., 5., atk_cd=1.)
    rec = draft.run.v["b13"]
    assert rec["kind"] == "wait" and rec["lead"] > T.B13_LEAD_F and mask == B["R"] and draft.run.v.get("b13_steer") is None


def test_on_clear_keys_leave_no_record(on):
    (draft, _, _, mask), _, _, _ = _propose(30.0, 10.12, 0., -.6, atk_cd=1.)   # far left of the body, the jump hold none: lands short
    assert draft.run.link == "air" and mask & B["R"] and "b13" not in draft.run.v


def test_air_keys_honour_the_steer_without_a_dash(on):
    from ssbot.combat.knife_chain_eval import X
    r, s, sim = flight(x=27., y=10.12, vx=0., vy=10.2, target_x=TX)
    x = X(r, r.run, NS(sim=sim, ground=False, k=2, hero=s["hero"], e=s["ents"][1]))
    r.run.v.update(jump_until=6, b13_steer=B["L"])
    assert T.air_approach_keys(x) == B["L"] | B["J"]
    r.run.v["b13_steer"] = 0
    assert T.air_approach_keys(x) == B["J"]


def test_the_opening_pending_caster_is_struck_when_she_would_land_on_it(monkeypatch, on):
    # p12 ep9 37701-37719 (the live case): over the casting caster, its hook not pressable ("no body on the hook ray": the opening
    # stays pending, so the Run's rows are none), coming down on its body: the guard's strike on the caster's head
    from tests.test_seq387 import _caster_run, _opening_scene
    row = {"F0": 1002, "masks": [B["D"] | B["A"]] * 12, "press_F": 1003, "contact_frame": 1008, "support": "still"}
    monkeypatch.setattr(T, "contact_body_witness", lambda *a, **k: np.array([21.2, 3.01, 24.8, 6.92]))
    monkeypatch.setattr(T, "press_now_row", lambda *a, **k: dict(row))
    monkeypatch.setattr(T, "face_hook_check_any", lambda *a, **k: (False, "no body on the hook ray", {}))
    s, sim = _opening_scene(23., 31., hx=24.0, y=10.0, vy=-.6)
    first = T.propose(_caster_run(), s, 1000 / 60., sim, 7, False, np.zeros((0, 6)), set(), hook_open=True)
    v = first[0].run.v
    assert T.opening_pending(v) and first[0].run.link == "strike" and v["b13"]["kind"] == "strike" and v["b13"]["opening"]
    monkeypatch.setattr(T, "B13", False)                                      # the old Run: no row while the opening is pending
    old = T.propose(_caster_run(), s, 1000 / 60., sim, 7, False, np.zeros((0, 6)), set(), hook_open=True)
    assert old[0].run.link == "air" and "b13" not in old[0].run.v


def test_the_native_adapter_notes_each_decision_once_and_offers_carry_it(monkeypatch, on):
    from tests.test_dash_lock179 import FC, chain, geometry
    r, s, sim = flight(x=33.6, y=8.6, vx=0., vy=-6., target_x=TX)
    sim.start[K.ATK_CD] = 1.
    n = chain(monkeypatch, r)
    geometry(monkeypatch)
    offer = n._transfer_offer(s, 0., sim, FC, NS(target=8), False)
    notes = [e for e in n.events if e["event"] == "transfer_b13_guard"]
    assert offer is not None and len(notes) == 1 and notes[0]["kind"] == "steer" and notes[0]["steer"] == 0
    assert offer.details["b13"] == "steer" and offer.details["b13_steer"] == 0 and not offer.mask & (B["L"] | B["R"])
    n._transfer_offer(s, 0., sim, FC, NS(target=8), False)        # the same decision again: not noted twice
    assert len([e for e in n.events if e["event"] == "transfer_b13_guard"]) == 1


def test_the_guard_reads_the_keys_the_adapter_really_sends_after_its_side_hold_back(monkeypatch, on):
    # test_seq387's g387_X14 scene (a casting body she would fly into, top 9.5): the native adapter's transfer_side_held_back takes the
    # side key out (14 frames of it meet the body); the guard reads those keys (b13_held_back), finds the release clear and records
    # nothing (c86 ep1 7075-7082: the guard read the held side key and struck 18 frames before a real hit at 7097)
    from tests.test_dash_lock179 import FC, chain, geometry
    r, s, sim = flight(x=27., y=8.4, vy=6., target_x=29.6)
    n = chain(monkeypatch, r); geometry(monkeypatch)
    e = next(x for x in s["ents"] if x["iid"] == 8)
    x0 = float(e["pos"][0])
    e["fsms"] = [{"name": "Control", "state": "Cast 1", "t": .2}]
    e["colliders"] = [{"name": "Song Heavy Sentry", "enabled": True,
                       "verts_world": [x0 - 1.8, 3.015, x0 + 1.8, 3.015, x0 + 1.8, 9.5, x0 - 1.8, 9.5]}]
    offer = n._transfer_offer(s, 0., sim, FC, NS(target=8), False)
    held = [ev for ev in n.events if ev["event"] == "transfer_side_held_back"]
    assert offer is not None and held and not offer.mask & B["R"]
    assert not [ev for ev in n.events if ev["event"] in ("transfer_b13_guard", "b2_recovery")]
    from ssbot.combat.knife_chain_eval import X
    x = X(r, r.run, NS(sim=sim, f=1000, k=2, e=e, hero=s["hero"], ground=False))
    assert T.b13_held_back(x, e, sim, B["R"], 0)                             # the guard's own read of the same rule


def test_the_guards_own_strike_waits_while_the_entry_is_farther_than_strike_f(monkeypatch, on):
    # the entry 15 frames off (B13_STRIKE_F 14): the Run's own rows still have time; a row the relaxed rules would give is not taken
    row = {"F0": 1002, "masks": [B["D"] | B["A"]] * 12, "press_F": 1003, "contact_frame": 1010, "support": "still"}
    real = T.press_now_row
    # a row only from the relaxed witness (Will Evade taken as not evading); the Run's own witness has none here (no evade record)
    monkeypatch.setattr(T, "press_now_row", lambda sim, body, *a, **k: dict(row) if np.isfinite(np.asarray(body, float)).all(axis=-1).any()
                        else real(sim, body, *a, **k))
    (draft, _, _, _), _, _, _ = _propose(34.6, 10.0, 0., 10., evidence=False)
    rec = draft.run.v["b13"]
    assert rec["lead"] == 15 and rec["kind"] == "wait" and draft.run.link == "air"
    monkeypatch.setattr(T, "B13_STRIKE_F", 15)
    (draft, _, _, _), _, _, _ = _propose(34.6, 10.0, 0., 10., evidence=False)
    assert draft.run.link == "strike" and draft.run.v["b13"]["kind"] == "strike"


def test_bounce_hold_is_the_air_stop_and_the_frozen_minus_ten_reading_in_any_clip():
    hold = lambda clip, vx, vy: T.b13_bounce_hold({"anim": {"clip": clip}, "vel": [vx, vy]})
    assert hold("DownSpikeBounce 1", 0., 0.) and hold("Airborne", 0., 0.)      # c86 ep13 41452 hit-stop; ep40 121806 takeoff frame
    assert hold("DownSpikeBounce 2", 8.25, -10.) and hold("Recoil Twirl", 0., -10.)   # ep13 41455-41456, ep33 101136
    assert not hold("DownSpikeBounce 1", 8.25, 17.4)                           # the hold's 17.4 is her real rise (ep13 41453)
    assert not hold("Shuttlecock", -18., 17.4) and not hold("Airborne", -8.25, 17.4)  # a held jump rises at 17.4 (ep14, ep40)
    assert not hold("DownSpikeBounce 1", 0., -13.2) and not hold("Airborne", 8.25, -10.2) and not T.b13_bounce_hold(None)


def test_on_a_downspikebounce_clip_with_a_real_vy_is_read(on):
    r, s, sim = flight(x=36.0, y=9.0, vx=0., vy=-10.4, target_x=TX)
    sim.start[K.ATK_CD] = 1.
    s["hero"]["anim"] = {"clip": "DownSpikeBounce 1"}
    made = T.propose(r, s, (s["f"] - 1000) / 60., sim, 8, False, np.zeros((0, 6)), set())
    assert made[0].run.v["b13"]["kind"] == "forced"


# ---- Sol REVIEW399 (0e3d6593): the steer's lifecycle and the route keys ----

def _steer_then_land(release):
    """Sol's b13_review_probe sequence: the guard steers at 1000 (release: 33.6 / 8.6, the release clear; countersteer: 34.15 / 9.2,
    only the countersteer clear), the same outside-air-entry Run lands at 1012 and jumps again (R + J), airborne again at 1016."""
    import copy
    from ssbot.combat.air_chain import ChainSim
    x, y, vy = (33.6, 8.6, -6.) if release else (34.15, 9.2, -4.)
    r, s, sim = flight(x=x, y=y, vx=0., vy=vy, target_x=TX)
    sim.start[K.ATK_CD] = 1.
    made = T.propose(r, s, 0., sim, 8, False, np.zeros((0, 6)), set())
    s2 = copy.deepcopy(s); s2["f"] = 1012
    s2["hero"].update(pos=[32.5, 4.568], box=[32.25, 3.015, 32.75, 5.1], vel=[0., 0.])
    s2["act"]["hf"].update(latched=0, desired=0)
    S = K.initial_state(sim.params, 32.5, 4.568, vx=0., ground=True); S[K.ATK_CD] = .8
    sim2 = ChainSim(S, np.array([0], np.int64), K.HoldState.from_act(s2["act"]), sim.params, sim.terrain, 1012, 1012)
    land = T.propose(made[0], s2, 12 / 60., sim2, 8, True, np.zeros((0, 6)), set())
    s3 = copy.deepcopy(s2); s3["f"] = 1016
    s3["hero"].update(pos=[32.8, 5.2], box=[32.55, 3.647, 33.05, 5.732], vel=[8.25, 17.4])
    s3["act"]["hf"].update(latched=B["R"] | B["J"], desired=B["R"] | B["J"])
    S3 = K.initial_state(sim.params, 32.8, 5.2, vx=8.25, vy=17.4, ground=False); S3[K.ATK_CD] = .7; S3[K.JHELD] = 1.
    S3[K.PREV] = B["R"] | B["J"]; S3[K.JUMPING] = 1.; S3[K.JSTEPS] = 2.
    sim3 = ChainSim(S3, np.array([B["R"] | B["J"]], np.int64), K.HoldState.from_act(s3["act"]), sim.params, sim.terrain, 1016, 1016)
    again = T.propose(land[0], s3, 16 / 60., sim3, 8, False, np.zeros((0, 6)), set())
    return made, land, again


@pytest.mark.parametrize("release", [True, False])
def test_a_steer_ends_with_its_flight_and_a_new_jump_never_takes_it_back(on, release):
    made, land, again = _steer_then_land(release)
    steer = 0 if release else B["L"]
    assert made[0].run.link == "air" and made[0].run.v["b13_steer"] == steer and made[0].run.v["b13"]["kind"] == "steer"
    assert land[0].run.link == "jump" and "b13_steer" not in land[0].run.v            # landed, jumping again: that flight is over
    assert land[3] == B["R"] | B["J"]
    # airborne again: the guard reads the new flight afresh (its own decision of 1016), never the stale steer of 1000 (Sol: L + J)
    rec = again[0].run.v.get("b13")
    assert again[0].run.link == "air" and (rec is None or rec["f"] == 1016) and not again[3] & B["L"]


def test_a_follow_up_route_does_not_inherit_a_steer(on):
    r, s, sim = flight(x=33.6, y=8.6, vx=0., vy=-6., target_x=TX)
    sim.start[K.ATK_CD] = 1.
    made = T.propose(r, s, 0., sim, 8, False, np.zeros((0, 6)), set())
    assert made[0].run.v["b13_steer"] == 0
    follow = {"kind": "left_landing", "F0": 1002, "masks": [B["L"]] * 20}
    fd = T.follow_draft(r, made, s, 0., sim, "land", follow)
    assert fd is not None and fd[0].run.link == "land" and "b13_steer" not in fd[0].run.v


@pytest.mark.parametrize("release", [True, False])
def test_the_route_reads_the_keys_the_air_link_really_sends(on, release):
    # Sol REVIEW399 2: _route_keys on the guard's own draft matches the air link's keys tick by tick (release 0, countersteer L)
    from ssbot.combat.knife_chain_air_native import NativeManualAirChain
    from ssbot.combat.knife_chain_eval import X
    x, y, vy = (33.6, 8.6, -6.) if release else (34.15, 9.2, -4.)
    r, s, sim = flight(x=x, y=y, vx=0., vy=vy, target_x=TX)
    sim.start[K.ATK_CD] = 1.
    d, plan, path, mask = T.propose(r, s, 0., sim, 8, False, np.zeros((0, 6)), set())
    from dataclasses import replace
    plan = replace(plan, jump_until=plan.entry_k + 6); d.run.v["jump_until"] = plan.jump_until   # a jump hold left: J in the first keys
    n = NativeManualAirChain.__new__(NativeManualAirChain)
    route = n._route_keys(plan, d, int(mask), "air", 1000)
    actual = [int(mask)] + [T.air_approach_keys(X(d, d.run, NS(k=plan.entry_k + 2 + i))) for i in range(1, 7)]
    assert d.run.v["b13_steer"] == (0 if release else B["L"]) and plan.side == B["R"]
    assert [int(v) & ~B["DASH"] for v in route[:7]] == [v & ~B["DASH"] for v in actual]
    monkeypatch_off = T.B13
    try:
        T.B13 = False
        old = n._route_keys(plan, d, int(mask), "air", 1000)
    finally:
        T.B13 = monkeypatch_off
    assert all(int(v) & (B["L"] | B["R"]) == B["R"] for v in old[1:7])             # B13 off: the plan's side, as before


def test_a_hook_ends_the_flight_of_a_steer(on):
    # Sol REVIEW399 1, the action boundary: the small rune opening's hook fires (claw link) on a Run that still holds a steer; the hook
    # is a motion of its own, so the steer goes (its release later re-enters the air link without it)
    from tests.test_seq387 import _caster_run, _opening_scene
    s, sim = _opening_scene(17., 20.5)
    r = _caster_run(b13_steer=B["R"])
    made = T.propose(r, s, 1000 / 60., sim, 7, False, np.zeros((0, 6)), set(), hook_open=True)
    assert made[0].run.link == "claw" and "b13_steer" not in made[0].run.v


# --- package 1 and 2 after B13 (design 7.1, the person 11-13 "你决定顺序"; SSBOT_FORUM_CHAIN_B13B) ---------------------------------

@pytest.fixture
def onb(monkeypatch):
    monkeypatch.setattr(T, "B13", True)
    monkeypatch.setattr(T, "B13B", True)


def test_b13b_follows_v2_unless_set():
    assert T.B13B == T._env_on("SSBOT_FORUM_CHAIN_B13B", T._ENV_V2)


def test_first_meet_reads_the_protection_when_given():
    boxes = np.array([[0., 0., 1., 1.], [1.5, 0., 2.5, 1.], [1.6, 0., 2.6, 1.], [1.7, 0., 2.7, 1.], [1.8, 0., 2.8, 1.]])
    body = np.array([2., 0., 4., 1.])
    assert T.b13_first_meet(boxes, body, 1, 5) == 1                                              # an unprotected entry
    assert T.b13_first_meet(boxes, body, 1, 5, prot=[False] * 5) == 1
    assert T.b13_first_meet(boxes, body, 1, 5, prot=[True, True, True, False, False]) == 3      # entered protected: its end
    assert T.b13_first_meet(boxes[1:], body, 1, 4) is None                                       # inside from now on: no entry
    assert T.b13_first_meet(boxes[1:], body, 1, 4, prot=[True, True, True, False]) == 3         # inside at the protection's end
    assert T.b13_first_meet(boxes[1:], body, 1, 4, prot=[True] * 4) is None


def test_flight_and_side_meet():
    G = K.F_GROUND
    assert T.b13b_flight([G, G, G, 0, 0, G, G], 1) == (3, 5)
    assert T.b13b_flight([G, G, G, G], 1) == (None, 4)
    assert T.b13b_flight([G, 0, 0, 0], 1) == (1, 4)
    body = np.array([2., 3., 4., 7.])
    side = np.array([[0., 3., .5, 5.], [1., 3., 1.5, 5.], [1.8, 3.2, 2.3, 5.2]])                  # centre y 4.2 < top 7
    top = np.array([[2.5, 9., 3., 11.], [2.5, 8., 3., 10.], [2.5, 6.8, 3., 8.8]])                 # centre 7.8 > top: from above
    assert T.b13b_side_meet(side, body, 1, 3) == 2
    assert T.b13b_side_meet(top, body, 1, 3) is None


class _Roll:
    """A stub ChainSim: roll returns designed boxes / flags per row (index 0 = frame fo)."""
    def __init__(self, boxes, flags):
        self.boxes, self.flags = np.asarray(boxes, float), np.asarray(flags, np.int64)
        self.prefix = np.array([0], np.int64); self.fo = 1000; self.f = 1000
        self.start = np.zeros(K.K)

    @property
    def off(self):
        return len(self.prefix) + 1

    def roll(self, rows):
        n = len(rows)
        return NS(box=self.boxes[:n], flags=self.flags[:n])


def _sprint_case(monkeypatch, *, plan_takeoff, plan_meet, rel_meets, rel_takeoff=5, n=T.B13_ROLL_F + 2):
    """Three rows: she runs right on the ground into a body at x 10 (top 7) from x 0; a row's takeoff index and entry index."""
    G = K.F_GROUND
    body = np.array([10., 3., 12., 7.])
    boxes = np.zeros((3, n, 4)); flags = np.zeros((3, n), np.int64)
    for i, (t, m) in enumerate([(plan_takeoff, plan_meet)] + [(rel_takeoff, r) for r in rel_meets]):
        for j in range(n):
            x = (10.1 - (m - j) * .3) if m is not None and j >= m else (9. - (m - j) * .3 if m is not None else 0.)
            if m is None:x = min(9., .2 * j)
            boxes[i, j] = [x - .25, 3.1, x + .25, 5.1]
            flags[i, j] = G if (t is None or j < t) else 0
    monkeypatch.setattr(T, "b13_danger", lambda e, frames=None: np.tile(body, (frames or T.B13_ROLL_F, 1)))
    monkeypatch.setattr(T, "render", lambda runner, p, k, length, link="walk": np.full(length, B["R"] | B["J"] | B["DASH"], np.int64))
    monkeypatch.setattr(T, "control", lambda e: ("Spell Antic", .1))
    plan = T.TransferPlan(8, 7, 990, 1000, 0., B["R"], 10, 2, 20, True, 1000, 0)
    return T.b13b_sprint_jump(None, plan, _Roll(boxes, flags), {}, 0, "dash")


def test_sprint_jump_kinds(monkeypatch):
    assert _sprint_case(monkeypatch, plan_takeoff=6, plan_meet=None, rel_meets=(None, None))["kind"] == "clear"
    # entering 8 frames after its takeoff: the air guard's (B13B_GUARD_F 6)
    assert _sprint_case(monkeypatch, plan_takeoff=6, plan_meet=14, rel_meets=(None, None))["kind"] == "guard"
    # within 6 of the takeoff, or on the ground (never off it): the dash let go when a release row takes off clear
    # the approved row is the first clear one (Sol REVIEW402): row 1 keeps the plan's side key, row 2 lets it go too
    rec = _sprint_case(monkeypatch, plan_takeoff=6, plan_meet=11, rel_meets=(15, None))
    assert rec["kind"] == "release" and rec["row"] == 2 and rec["side"] == 0
    rec = _sprint_case(monkeypatch, plan_takeoff=None, plan_meet=9, rel_meets=(None, 12))
    assert rec["kind"] == "release" and rec["row"] == 1 and rec["side"] == B["R"]
    rec = _sprint_case(monkeypatch, plan_takeoff=None, plan_meet=9, rel_meets=(None, None))
    assert rec["kind"] == "release" and rec["row"] == 1 and rec["side"] == B["R"]
    rec = _sprint_case(monkeypatch, plan_takeoff=None, plan_meet=9, rel_meets=(9, 10))
    assert rec["kind"] == "forced" and rec["meet_F"] == 1009 and rec["release_meets_F"] == [1009, 1010]
    # a release row that never leaves the ground is no way (the jump link would end in its own failed jump)
    assert _sprint_case(monkeypatch, plan_takeoff=6, plan_meet=11, rel_meets=(None, None), rel_takeoff=None)["kind"] == "forced"


@pytest.mark.parametrize("kind,row,dash,side", [("release", 1, False, True), ("release", 2, False, False), ("guard", None, True, True),
                                               ("forced", None, True, True), ("clear", None, True, True)])
def test_propose_sends_the_approved_row_only_on_release(onb, monkeypatch, kind, row, dash, side):
    from tests.test_knife_chain_transfer import transfer_at_gap
    seen = []
    rec = {"kind": kind, "f": 1000, **({"row": row, "side": B["R"] if row == 1 else 0} if row else {})}
    monkeypatch.setattr(T, "b13b_sprint_jump", lambda *a: seen.append(a) or rec)
    r, s, sim = transfer_at_gap(2., K.M_SPRINT)
    made = T.propose(r, s, 0., sim, 8, True, np.zeros((0, 6)), set())
    assert made is not None and made[0] is not None and seen
    draft, p, _, mask = made
    assert p.sprint_jump is dash and bool(mask & B["DASH"]) is dash and mask & B["J"]
    assert bool(mask & B["R"]) is side and p.side == (B["R"] if side else 0)
    assert draft.run.v["b13b"]["kind"] == kind
    assert draft.run.v["b13b_side"] == (rec["side"] if kind == "release" else None)


def test_propose_checks_no_sprint_jump_when_off(monkeypatch):
    from tests.test_knife_chain_transfer import transfer_at_gap
    monkeypatch.setattr(T, "B13", True); monkeypatch.setattr(T, "B13B", False)
    monkeypatch.setattr(T, "b13b_sprint_jump", lambda *a: pytest.fail("checked while off"))
    r, s, sim = transfer_at_gap(2., K.M_SPRINT)
    made = T.propose(r, s, 0., sim, 8, True, np.zeros((0, 6)), set())
    assert made[1].sprint_jump and made[3] & B["DASH"] and made[0].run.v["b13b"] is None


def _inside(monkeypatch, on_b, steps=8.):
    monkeypatch.setattr(T, "B13", True); monkeypatch.setattr(T, "B13B", on_b)
    r, s, sim = flight(x=34.55, y=7., vx=0., vy=-.6, target_x=TX)    # her box 34.30-34.80 x 5.45-7.53 in the body 34.25-37.84 (top 6.92)
    sim.start[K.POGO_OBS] = steps                                      # a real bounce protection: steps left
    sim.start[K.ATK_CD] = 1.                                           # no down slash now (the Run's own strike row would come first)
    return T.propose(r, s, (s["f"] - 1000) / 60., sim, 8, False, np.zeros((0, 6)), set())


@pytest.mark.parametrize("steps", [8., 12.])   # its end 8 / 10 frames past the mask frame: inside steers at once, past B13_LEAD_F too
def test_inside_the_body_at_the_protections_end_steers_out(monkeypatch, steps):
    draft, _, _, mask = _inside(monkeypatch, True, steps)
    rec = draft.run.v["b13"]
    assert rec["kind"] == "steer" and rec["inside"] and rec["steer"] == B["L"]
    assert mask & B["L"] and not mask & B["R"] and draft.run.v["b13_steer"] == B["L"]


def test_inside_the_body_is_no_meeting_without_b13b(monkeypatch):
    draft, _, _, mask = _inside(monkeypatch, False)
    assert "b13" not in draft.run.v or draft.run.v["b13"] is None or draft.run.v["b13"].get("kind") != "steer"


def _probe_scene(gap, mode):
    """Sol REVIEW402's production-shaped fixture (analysis/b13b_402_20261113/b13b_review_probe.py): the ground sprint / dash scene
    with the hero2 model, its previous keys in flight, the move held, the sprint 0.1 s old and an Idle target."""
    from tests.test_knife_chain_transfer import transfer_at_gap, fit_pose
    r, s, sim = transfer_at_gap(gap, mode)
    sim.params = K.hero2(sim.params, on=True)
    sim.start[K.PREV] = int(sim.prefix[0])
    sim.start[K.MOVE] = 1.
    if mode == K.M_SPRINT:
        sim.start[K.MODE_T] = .1
    fit_pose(s["ents"][1], state="Idle", t=.05)
    return r, s, sim


def test_row2_only_sends_the_jump_alone_and_holds_it(onb):
    # REVIEW402's counterexample, no stubs: the sprint jump would enter on the ground (1003, takeoff 1009); the dash let go with the side
    # key held takes off at 1002 and enters at 1003; with the side key let go too it takes off at 1002 clear. Its keys are J alone.
    r, s, sim = _probe_scene(3., K.M_SPRINT)
    draft, p, path, mask = T.propose(r, s, 0., sim, 8, True, np.zeros((0, 6)), set())
    rec = draft.run.v["b13b"]
    assert rec["kind"] == "release" and rec["row"] == 2 and rec["release_meets_F"] == [1003, None]
    assert mask == B["J"] and p.side == 0 and not p.sprint_jump and draft.run.v["b13b_side"] == 0
    keys = T.render(r, p, 0, T.B13_ROLL_F, "dash")
    assert not np.any(keys & (B["L"] | B["R"] | B["DASH"]))                  # the rendered row is the approved row 2
    ro = sim.roll(np.asarray([keys], np.int64))
    danger = T.b13_danger(s["ents"][1], len(sim.prefix) + 1 + T.B13_ROLL_F)
    t, land = T.b13b_flight(ro.flags[0], sim.off)
    assert t is not None and T.b13b_side_meet(ro.box[0], danger, 1, land + 1) is None


def test_row2_side_holds_in_the_air_and_ends_with_the_flight(monkeypatch):
    monkeypatch.setattr(T, "B13", True)
    monkeypatch.setattr(T, "B13B", True)
    r, s, sim = flight(x=30., y=8., vx=0., vy=5., target_x=TX)                # an air link Run of side R, a later tick of the flight
    r.run.v["b13b_side"] = 0
    draft, p, _, mask = T.propose(r, s, (s["f"] - 1000) / 60., sim, 8, False, np.zeros((0, 6)), set())
    assert p.side == 0 and not mask & (B["L"] | B["R"]) and draft.run.v["b13b_side"] == 0
    monkeypatch.setattr(T, "B13B", False)                                      # off: the parent's side, no hold kept
    r, s, sim = flight(x=30., y=8., vx=0., vy=5., target_x=TX)
    r.run.v["b13b_side"] = 0
    draft, p, _, mask = T.propose(r, s, (s["f"] - 1000) / 60., sim, 8, False, np.zeros((0, 6)), set())
    assert p.side == B["R"] and mask & B["R"] and draft.run.v["b13b_side"] is None


def test_row1_clear_keeps_the_side_key(onb, monkeypatch):
    # a release whose row 1 is clear keeps the plan's side key (the dash alone let go); the real model gives no such row in this
    # fixture, so the record is given over the counterexample's scene
    r, s, sim = _probe_scene(3., K.M_SPRINT)
    real = T.b13b_sprint_jump
    monkeypatch.setattr(T, "b13b_sprint_jump", lambda *a: {**real(*a), "row": 1, "side": B["R"]})
    draft, p, _, mask = T.propose(r, s, 0., sim, 8, True, np.zeros((0, 6)), set())
    assert mask == B["R"] | B["J"] and p.side == B["R"] and not p.sprint_jump and draft.run.v["b13b_side"] == B["R"]


def test_inside_at_reads_the_frame_before_the_meeting():
    body = np.array([2., 0., 4., 1.])
    # a protected touch she left before an unprotected entry from outside: no inside meeting (REVIEW402's doubt)
    boxes = np.array([[0., 0., 1., 1.], [1.5, 0., 2.5, 1.], [1.6, 0., 2.6, 1.], [.5, 0., 1.5, 1.], [.8, 0., 1.8, 1.], [1.8, 0., 2.8, 1.]])
    prot = [True, True, True, False, False, False]
    i = T.b13_first_meet(boxes, body, 1, 6, prot=prot)
    assert i == 5 and not T.b13_inside_at(boxes, body, i)
    assert T.b13_first_meet(boxes, body, 1, 6) == 1                         # the old whole-roll comparison called it inside
    # in the body when the protection ends: inside
    boxes = np.array([[2.5, 0., 3., 1.]] * 5)
    i = T.b13_first_meet(boxes, body, 1, 5, prot=[True, True, True, False, False])
    assert i == 3 and T.b13_inside_at(boxes, body, i)
