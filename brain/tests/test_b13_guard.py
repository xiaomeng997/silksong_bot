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
