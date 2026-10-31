"""Opt-in deferral on the wait tick before the first J: the wait step never claims a J; a missed first J slot is
still the ground veto; skipped re-plans owe one later full C5 (ran is not passed) before CLAW; the HoldFilter and
target checks; the new-owner check's blind spot (diagnosis, never a pass)."""
from types import SimpleNamespace as NS
import numpy as np
import pytest
from ssbot.combat import knife_chain_hook_fast as fast
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.combat.knife_chain_commitment import MoveInstance
from ssbot.combat.knife_chain_nominal import logical_copy
from ssbot.knowledge import kinematics as km
from tests.test_b2_deferred_dispatch_guard import actual, deferred, stage, state_names, MOVE, ORIGIN
from tests.test_b2_fast_hook import eligible
from dataclasses import replace


def fast_on():
    n = deferred()
    n.profile = replace(n.profile, fast_hook=True)
    n._fast_j_mode = True
    return n


def mark(n, tick):
    n._b2_selected.details["fast_j"] = {"tick": tick, "key": [ORIGIN + 4, 3, ORIGIN + 7, B["R"]]}


def wait_skip(n):
    stage(n, ORIGIN + 1, B["R"], target=ORIGIN + 1, desired=B["R"])
    mark(n, "wait")
    assert n.before_send(frame=ORIGIN + 1, target=ORIGIN + 3, mask=B["R"], flags=0, received_frame=ORIGIN + 1) is None
    assert n.sent().desired_mask == B["R"]
    return n


def two_skips():
    n = wait_skip(fast_on())
    stage(n, ORIGIN + 2, B["J"])
    mark(n, "J")
    assert n.before_send(frame=ORIGIN + 2, target=ORIGIN + 4, mask=B["J"], flags=0, received_frame=ORIGIN + 2) is None
    n.sent()
    return n


def claw_after_takeoff(n):
    n.begin(actual(ORIGIN + 3, target=ORIGIN + 2, desired=B["R"]))
    stage(n, ORIGIN + 4, B["J"], target=ORIGIN + 4, desired=B["J"])
    assert n.before_send(frame=ORIGIN + 4, target=ORIGIN + 6, mask=B["J"], flags=0, received_frame=ORIGIN + 4) is None
    n.sent()
    stage(n, ORIGIN + 5, B["R"] | B["CLAW"], ground=False, clip="Airborne", vy=18.6, target=ORIGIN + 4, desired=B["J"])
    assert n._jump_start.seen_frame == ORIGIN + 5
    return n.before_send(frame=ORIGIN + 5, target=ORIGIN + 7, mask=B["R"] | B["CLAW"], flags=0, received_frame=ORIGIN + 5)


def test_wait_fast_step_records_a_skip_but_never_a_jump_send():
    n = wait_skip(fast_on())
    assert n._fast_j_sent == {"move": MOVE, "frame": ORIGIN + 1, "target": None, "deferred": None, "skips": ["wait"]}
    assert n._jump_start.sent_targets == set() and n._jump_start.seen_frame is None
    note = next(e for e in n.events if e["event"] == "b2_fast_j_sent")
    assert note["tick"] == "wait" and note["j_sent"] is False


def test_missed_first_J_slot_after_a_fast_wait_is_still_the_ground_veto():
    n = wait_skip(fast_on())
    stage(n, ORIGIN + 3, B["J"])          # no tick processed ORIGIN+2: the first J slot ORIGIN+4 was missed
    assert n.before_send(frame=ORIGIN + 3, target=ORIGIN + 5, mask=B["J"], flags=0, received_frame=ORIGIN + 3) == 0
    assert n.commitment is None and MOVE in n._failed_hook_moves and n._fast_j_sent is None
    reason = next(v["reason"] for v in n.events if v["event"] == "b2_jump_send_veto")
    assert "first" in reason and "skipped" in reason


def test_two_skips_then_CLAW_without_a_later_full_C5_is_an_explicit_recovery():
    n = two_skips()
    assert n._fast_j_sent["skips"] == ["wait", "J"] and n._fast_j_sent["target"] == ORIGIN + 4
    assert claw_after_takeoff(n) == 0
    assert n.commitment is None and n._fast_j_sent is None and n.counts["b2_fast_j_claw_veto"] == 1


@pytest.mark.parametrize("calls,outcome", [
    ([{"p_only": ORIGIN + 7, "ok": True}], "p_only_pass"),
    ([{"p_only": ORIGIN + 7, "ok": False}, {"p_only": None, "ok": True}], "replan"),
    ([{"p_only": ORIGIN + 7, "ok": False}, {"p_only": None, "ok": False}], "lost_plan_kept"),
])
def test_a_later_full_C5_that_ran_releases_the_CLAW_and_ran_is_not_passed(calls, outcome):
    n = two_skips()
    n._last_c5_calls = calls
    n._fast_j_record_deferred(ORIGIN + 2, MOVE)       # same frame as the last skip: does not pay it back
    assert n._fast_j_sent["deferred"] is None
    n._fast_j_record_deferred(ORIGIN + 3, MOVE)
    assert n._fast_j_sent["deferred"] == {"frame": ORIGIN + 3, "outcome": outcome}
    row = next(e for e in n.events if e["event"] == "b2_fast_j_deferred_check")
    assert row["verdict"] == "ran"
    assert claw_after_takeoff(n) is None
    assert n.counts["b2_fast_j_claw_veto"] == 0


def test_a_full_first_J_tick_after_a_fast_wait_pays_back_the_wait_skip():
    n = wait_skip(fast_on())
    n._last_c5_calls = [{"p_only": ORIGIN + 7, "ok": True}]
    n._fast_j_record_deferred(ORIGIN + 2, MOVE)       # the J tick took the full path and ran rule 0
    assert n._fast_j_sent["deferred"] == {"frame": ORIGIN + 2, "outcome": "p_only_pass"}


def test_only_this_moves_wait_skip_may_precede_a_fast_first_J():
    n, fc = eligible("J")
    n._fast_j_sent = {"move": MOVE, "frame": ORIGIN + 1, "target": None, "deferred": None, "skips": ["wait"]}
    assert fast.admit(n, fc)["tick"] == "J"
    for other in ({"move": MOVE, "frame": ORIGIN + 1, "target": ORIGIN + 4, "deferred": None, "skips": ["J"]},
                  {"move": MoveInstance(99, ORIGIN, "CC_SLAM"), "frame": ORIGIN + 1, "target": None, "deferred": None, "skips": ["wait"]}):
        n, fc = eligible("J")
        n._fast_j_sent = other
        assert fast.admit(n, fc) is None and n.counts["b2_fast_j_fallback"] == 1


@pytest.mark.parametrize("kind", ["wait", "J"])
@pytest.mark.parametrize("which", ["pending", "desired_hold", "age_class", "hf_incomplete", "no_hold_start",
                                   "target_moved", "target_turned", "antic_clock", "target_state", "wait_key"])
def test_hold_and_target_mismatch_returns_full_path(kind, which):
    n, fc = eligible(kind)
    sim = n._context[1]
    e = n._actual_state["ents"][0]
    if which == "pending":
        sim.hold.pending[0, 0] = 1                     # a queued J edge the commitment never commanded
    elif which == "desired_hold":
        sim.hold.desired[0, 0] = True
    elif which == "age_class":
        sim.hold.age[0, 20] = 1                        # R latched one frame only
    elif which == "hf_incomplete":
        del n._actual_state["act"]["hf"]["age"]
    elif which == "no_hold_start":
        n._fast_j_commit["hold_start"] = None
    elif which == "target_moved":
        e["pos"] = [30.2, 7.449]
    elif which == "target_turned":
        e["flipX"] = False
    elif which == "antic_clock":
        e["fsms"][0]["t"] += 1 / 60
    elif which == "target_state":
        e["fsms"][0]["state"] = "Slam"
    elif which == "wait_key":
        if kind == "J":
            pytest.skip("wait-key rule is the wait tick's")
        n._fast_j_commit["path"].commands[2] |= B["L"]
    assert fast.admit(n, fc) is None
    assert n.counts["b2_fast_j_fallback"] == 1


def test_hold_ages_compare_by_the_two_frame_class_only():
    a = km.HoldState.from_hf({"latched": B["R"], "desired": B["R"], "pending": [0] * 22, "age": [255] * 22})
    b = a.copy()
    b.age[0, 20] = 3
    assert fast.hold_equivalent(a, b)
    b.age[0, 20] = 1
    assert not fast.hold_equivalent(a, b)


L = 1 << 20
AGE_2758 = [40, 20, 7, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 174, 18, 173]
AGE_2760 = [42, 22, 9, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 176, 20, 175]


def test_recorded_15e26dc3_hold_equals_the_commitment_hold_pushed_two_frames():
    # act.hf of STATE 2758 (commitment) and 2760 (first-J tick); the commanded prefix is the held L twice.
    from ssbot.combat.holdfilter import hold_filter_jit
    c = km.HoldState.from_hf({"latched": L, "desired": L, "pending": [0] * 22, "age": AGE_2758})
    _, pred = hold_filter_jit(np.array([[L, L]], np.int64), c, parallel=False)
    assert fast.hold_equivalent(pred, km.HoldState.from_hf({"latched": L, "desired": L, "pending": [0] * 22, "age": AGE_2760}))


def test_new_owner_check_cannot_see_a_same_owner_hazard_diagnosis():
    """Counterexample diagnosis, never a pass: a new hazard part of an EXISTING owner keeps the owner set."""
    def forecast(raw):
        return NS(rs=NS(trk=NS(now={7: (30., 7.449, object())}, orphan_hazards={}), haz_raw={}, raw=raw, layers={},
                        bombs=None))
    before = fast.owners(forecast({}))
    after = fast.owners(forecast({"hammer": [(7, "new same-owner hazard part")]}))
    assert before == after == frozenset({7}) and after <= before


@pytest.mark.parametrize("kind",["wait","J"])
@pytest.mark.parametrize("which",["pending_short","age_short","age_bool","pending_negative","mask_bool","missing_flip","target_nan","target_clock_missing","target_malformed_fsm","commit_hold_unknown"])
def test_malformed_export_or_unknown_seed_cannot_enable_fast_step(kind,which):
    n,fc=eligible(kind);hf=n._actual_state['act']['hf'];e=n._actual_state['ents'][0]
    if which=='pending_short':hf['pending']=[]
    elif which=='age_short':hf['age']=[255]
    elif which=='age_bool':hf['age'][0]=True
    elif which=='pending_negative':hf['pending'][0]=-1
    elif which=='mask_bool':hf['latched']=False
    elif which=='missing_flip':del e['flipX']
    elif which=='target_nan':e['pos'][0]=float('nan')
    elif which=='target_clock_missing':del e['fsms'][0]['t']
    elif which=='target_malformed_fsm':e['fsms']=[None]
    else:n._fast_j_commit['hold_known']=False
    assert fast.admit(n,fc) is None and n.counts['b2_fast_j_fallback']==1


def test_actual_exported_hold_cannot_be_replaced_by_a_matching_model_default():
    n,fc=eligible('J')
    n._actual_state['act']['hf']['pending'][0]=1
    assert fast.admit(n,fc) is None
    assert next(e for e in n.events if e['event']=='b2_fast_j_fallback')['reason']=='current model hold differs from actual act.hf'
