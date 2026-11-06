"""Task 179 #309 (Sol seq 229 item 5): the finite same-target bounce table (Tasks 143 / 145 / 148) on the minimal online
entry. Rows are the positive-slack witnesses; the state machine keeps the normal baseline until the first sighting,
verifies ONE row after the sighting tick's send and switches only while its first differing key can still be sent;
keys already sent never move; only a real next hit at the verified Update and physics step continues the row. The B2
adapter anchors only a real same-target hit + bounce (opt-in SSBOT_FORUM_CHAIN_BOUNCE_TABLE=1), keeps the existing
source responsibility, follows the first new slam instance, and verifies after the send. Verification is stubbed
here (the real-start verification is the replay positive); no hit receipt is ever made."""
from dataclasses import replace
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import knife_chain_bounce_table as BT
from ssbot.combat.knife_chain_commitment import MoveInstance
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.knowledge import kinematics as K

HIT, FC = 1000, 5000
REL = {i: 2 * (i - 1) - (i // 3) for i in range(1, 161)}          # a fixed physics pairing (state -> steps from the hit)


def start(i, rel0=None):
    return BT.Start(np.zeros(K.K), None, 0.01665, None, None, i, REL[i] if rel0 is None else rel0)


def fake_verify(ok=True, contacts=(14,), through=40):
    calls = []

    def verify(start, target, cmd, n_strikes, tls=None):
        calls.append((start.s, target.ua, list(cmd[:3]), n_strikes))
        return {"pass": ok, "why": None if ok else "variant 3: margins 1/2 unsafe None",
                "per_variant": [{"contacts_update": list(contacts), "through_update": through}],
                "rel_by_state": {i: v for i, v in REL.items() if i >= start.s}, "receipt": False}
    return verify, calls


def table_at_sighting(monkeypatch, ua=5, ok=True, contacts=(14,)):
    """Anchor, the baseline ticks, the sighting STATE and its send; returns (table, verify calls)."""
    verify, calls = fake_verify(ok, contacts)
    monkeypatch.setattr(BT, "verify", verify)
    t = BT.BounceTable()
    assert t.anchor(frame=HIT, fc=FC, iid=7, instance_t0=None, sent={HIT: 0, HIT + 1: 0})["decision"] == "anchored"
    for i in range(1, ua):
        f = HIT + i - 1
        d = t.on_state({"frame": f, "fc": FC + REL[i], "control": "Idle", "instance_t0": 3., "prev_seen": True,
                        "pose": {"x": 30., "y": 7.45, "face": -1}, "start": start(i)})
        assert d["decision"] == "keep_normal"
        t.record_sent(f + 2, t.key(f + 2))
    f = HIT + ua - 1
    d = t.on_state({"frame": f, "fc": FC + REL[ua], "control": "Slam Antic", "instance_t0": 4., "prev_seen": True,
                    "pose": {"x": 30., "y": 7.45, "face": -1}, "start": start(ua)})
    t.record_sent(f + 2, t.key(f + 2))
    return t, d, calls


def test_rows_are_the_positive_slack_witnesses_only():
    rows = BT.rows()
    assert sorted(rows) == [4, 5, 10, 11, 16, 17, 22, 35]
    normal = BT.normal_keys()
    for ua, r in rows.items():
        assert r.cut == ua + 1 and r.slack == r.first - 1 - ua > 0
        assert np.array_equal(r.masks[:r.cut], normal[:r.cut]) and r.masks[r.first] != normal[r.first]
    assert not {23, 28, 29, 34} & set(rows)                         # zero-slack-only first sightings are not rows


def test_baseline_sighting_verify_after_send_switch_and_the_verified_next_hit(monkeypatch):
    t, d, calls = table_at_sighting(monkeypatch)
    row = BT.rows()[5]
    assert d == {"decision": "verify_after_send", "row": row.H, "slack": 3} and not calls
    v = t.verify_now()                                               # after the sighting tick's send, once
    assert v["pass"] and len(calls) == 1 and calls[0][:2] == (5, 5) and t.chain.verify_ms is not None
    assert calls[0][2][0] == t.chain.sent[HIT + 5]                  # cmd[0] = the in-flight key actually sent
    assert t.verify_now() is None                                   # never twice
    d = t.on_state({"frame": HIT + 5, "fc": FC + REL[6], "control": "Slam Antic", "instance_t0": 4., "prev_seen": True,
                    "pose": {"x": 30., "y": 7.45, "face": -1}, "start": start(6)})
    assert d["decision"] == "switch" and d["first_difference_frame"] == HIT + row.first
    assert [t.key(HIT + j) for j in range(row.cut, 60)] == [int(m) for m in row.masks[row.cut:60]]
    assert t.verified_through() == 40
    d = t.on_state({"frame": HIT + 6, "fc": FC + REL[7], "control": "Slam Antic", "instance_t0": 4., "prev_seen": True,
                    "pose": {}, "start": None})
    assert d["decision"] == "keep_row"
    res = t.on_real_hit(frame=HIT + 13, fc=FC + REL[14], iid=7, marker=True)
    assert res["decision"] == "confirmed" and res["state"] == "done"


@pytest.mark.parametrize("case", ["late_hit", "off_physics", "other_target"])
def test_a_real_next_hit_off_the_verified_update_is_uncovered(monkeypatch, case):
    t, _, _ = table_at_sighting(monkeypatch)
    t.verify_now()
    t.on_state({"frame": HIT + 5, "fc": FC + REL[6], "control": "Slam Antic", "instance_t0": 4., "prev_seen": True,
                "pose": {}, "start": None})
    frame, fc, iid = HIT + 13, FC + REL[14], 7
    if case == "late_hit":
        frame += 1
    elif case == "off_physics":
        fc += 1
    else:
        iid = 8
    res = t.on_real_hit(frame=frame, fc=fc, iid=iid, marker=True)
    assert res["decision"] == ("ignored" if case == "other_target" else "uncovered")


def test_switched_row_without_its_verified_hit_or_with_a_new_pairing_is_uncovered(monkeypatch):
    t, _, _ = table_at_sighting(monkeypatch)
    t.verify_now()
    t.on_state({"frame": HIT + 5, "fc": FC + REL[6], "control": "Slam Antic", "instance_t0": 4., "prev_seen": True,
                "pose": {}, "start": None})
    d = t.on_state({"frame": HIT + 6, "fc": FC + REL[7] + 1, "control": "Slam 0", "instance_t0": 4.,
                    "prev_seen": True, "pose": {}, "start": None})
    assert d["decision"] == "uncovered" and "pairing" in d["why"]
    t, _, _ = table_at_sighting(monkeypatch)
    t.verify_now()
    for i in range(6, 17):
        d = t.on_state({"frame": HIT + i - 1, "fc": FC + REL[i], "control": "Slam 0", "instance_t0": 4.,
                        "prev_seen": True, "pose": {}, "start": None})
    assert d["decision"] == "uncovered" and "not observed" in d["why"]          # due 14: state 16 has no hit


@pytest.mark.parametrize("case", ["verify_failed", "not_verified", "deadline", "pairing"])
def test_the_switch_needs_a_passed_verification_its_deadline_and_the_pairing(monkeypatch, case):
    t, _, _ = table_at_sighting(monkeypatch, ok=case != "verify_failed")
    if case != "not_verified":
        t.verify_now()
    row = BT.rows()[5]
    f, i = HIT + 5, 6
    fc = FC + REL[6] + (1 if case == "pairing" else 0)
    if case == "deadline":                     # the first differing key (desired hit + first) is sent at hit + first - 2
        f = HIT + row.first - 1
        i = f - HIT + 1
        fc = FC + REL[i]
    d = t.on_state({"frame": f, "fc": fc, "control": "Slam Antic", "instance_t0": 4., "prev_seen": True, "pose": {},
                    "start": None})
    assert d["decision"] == "uncovered" and t.chain.state == "uncovered"
    assert t.key(HIT + row.first) == int(BT.normal_keys()[row.first])         # nothing switched


@pytest.mark.parametrize("case", ["zero_slack_ua", "already_in_antic", "no_actual_start", "key_after_cut_sent",
                                  "older_instance"])
def test_first_sightings_outside_the_rows_are_uncovered(monkeypatch, case):
    monkeypatch.setattr(BT, "verify", fake_verify()[0])
    t = BT.BounceTable()
    t.anchor(frame=HIT, fc=FC, iid=7, instance_t0=3., sent={HIT: 0, HIT + 1: 0})
    ua = 23 if case == "zero_slack_ua" else 5
    for f in range(HIT + 2, HIT + ua + 1):
        t.record_sent(f, int(t.normal[f - HIT]))
    if case == "key_after_cut_sent":
        t.record_sent(HIT + ua + 1, 0)
    st = {"frame": HIT + ua - 1, "fc": FC + REL[ua], "control": "Slam Antic",
          "instance_t0": 2. if case == "older_instance" else 4., "prev_seen": case != "already_in_antic",
          "pose": {"x": 30., "y": 7.45, "face": -1}, "start": None if case == "no_actual_start" else start(ua)}
    d = t.on_state(st)
    assert d["decision"] == "uncovered" and t.chain.row is None


def test_past_the_last_row_the_normal_knife_continues_and_a_late_antic_is_uncovered():
    t = BT.BounceTable()
    t.anchor(frame=HIT, fc=FC, iid=7, instance_t0=None, sent={})
    for i in range(1, 41):
        d = t.on_state({"frame": HIT + i - 1, "fc": FC + REL[i], "control": "Idle", "prev_seen": True})
        assert d["decision"] == "keep_normal"
    assert t.key(HIT + 33) == B["D"] | B["A"] and t.key(HIT + 36) == 0   # the normal knife: press at desired 33, no J
    d = t.on_state({"frame": HIT + 40, "fc": FC + REL[41], "control": "Slam Antic", "instance_t0": 4.,
                    "prev_seen": True, "pose": {"x": 30., "y": 7.45, "face": -1}, "start": start(41)})
    assert d["decision"] == "uncovered" and "no positive-slack row" in d["why"]


# ---- the B2 adapter ---------------------------------------------------------------------------------------------------

def scene(f=HIT, target_state="Idle", t=.2, hit=7):
    e = lambda i, st, x, tt: {"iid": i, "type_key": "Song Heavy Sentry", "hp": 100, "pos": [x, 7.45], "flipX": False,
                              "fsms": [{"name": "Control", "state": st, "t": tt}],
                              "colliders": [{"name": "Song Heavy Sentry", "enabled": True}]}
    return {"f": f, "fc": FC + f - HIT, "dt": 0.01665,
            "hero": {"health": 7, "pos": [30., 9.], "box": [29.75, 7.5, 30.25, 9.6], "cstate_int": [0, 8]},
            "ents": [e(7, target_state, 30.5, t), e(8, "Idle", 44., .5)],
            "ev": [{"k": "hit", "f": f, "d": {"ent": hit, "src": "DownSlashAlt"}}]}


def chain(monkeypatch, on=True):
    from ssbot.combat.knife_chain_air import load_runner
    from ssbot.combat.knife_chain_air_native import NativeManualAirChain
    monkeypatch.setenv(BT.ENV, "1" if on else "0")
    n = NativeManualAirChain(runner_factory=load_runner, probe_ref="bounce-table-309")
    n.reset(0, start_frame=HIT - 1)
    return n


def prefs(target=7, **kw):
    from ssbot.combat.tactics.modes import GoalPrefs
    return replace(GoalPrefs(mode="RUSH", stance_x=30., weights={}, target=target), **kw)


def anchored(monkeypatch):
    n = chain(monkeypatch)
    s = scene()
    BT.observe_frame(n, s)
    run = NS(iid=7, fa=946, ta=2., phase="after")
    assert n.observe_bounce_goal(s, prefs(), run)
    return n, s


def test_a_real_same_target_bounce_anchors_the_table_with_the_existing_source_responsibility(monkeypatch):
    n, s = anchored(monkeypatch)
    c = n._bounce.chain
    assert (c.iid, c.hit_frame, c.hit_fc, c.state) == (7, HIT, FC, "baseline")
    assert n.commitment["bounce_table"] and n.commitment["move"] == MoveInstance(7, 946, "CC_SLAM")
    assert n._transfer_goal is None and n.post_context is None
    assert n.goal_preferences(s, prefs(), handoff=True) is not None and not n._transfer_ready
    assert "air_bounce" in n.runner.chains


@pytest.mark.parametrize("case", ["flag_off", "other_target", "wall_pressure", "side_entry", "no_hit", "tail_pending",
                                  "moving", "casting"])
def test_outside_the_same_target_domain_the_existing_bounce_goal_stays(monkeypatch, case):
    from ssbot.combat.tactics.modes import EntryAttack
    n = chain(monkeypatch, on=case != "flag_off")
    s = scene(hit=8 if case == "other_target" else 7)
    if case == "other_target":
        s["ents"][1]["fsms"][0]["state"] = "Slam Recover"
    if case in ("tail_pending", "moving", "casting"):   # the bounced slam still swinging / evading / casting
        s["ents"][0]["fsms"][0]["state"] = {"tail_pending": "Slam 0", "moving": "Evade Scuttle", "casting": "Spell Antic"}[case]
    BT.observe_frame(n, s)
    kw = {"wall_pressure": NS(target=7)} if case == "wall_pressure" else {
        "entry_attack": EntryAttack(7, "side", 8, "CC_SLAM", 6., 0.)} if case == "side_entry" else {
        "no_hit": frozenset({7})} if case == "no_hit" else {}
    run = NS(iid=8 if case == "other_target" else 7, fa=946, ta=2., phase="after")
    n.observe_bounce_goal(s, prefs(**kw), run)
    assert n._bounce is None and n.commitment is None
    if case in ("flag_off", "other_target", "tail_pending", "moving", "casting"):
        assert n._transfer_goal is not None and n._transfer_goal.source_kind == "BOUNCE"


def test_responsibility_follows_the_first_new_antic_and_a_second_new_instance_recovers(monkeypatch):
    n, s = anchored(monkeypatch)
    n._clock = 20.
    s1 = scene(f=HIT + 4, target_state="Slam Antic", t=0.)
    BT.observe_identity(n, s1)
    assert n.commitment["move"] == MoveInstance(7, HIT + 4, "CC_SLAM") and n.commitment["sighted"]
    assert n.commitment["ta"] == 20. and n.commitment["responsibility_origin"] == HIT + 4
    n._clock = 20.02
    BT.observe_identity(n, scene(f=HIT + 5, target_state="Slam Antic", t=.02))     # the same instance: no change
    assert n._bounce is not None and n.commitment["move"].antic_frame == HIT + 4
    n._clock = 21.
    BT.observe_identity(n, scene(f=HIT + 66, target_state="Slam Antic", t=0.))     # a second new instance
    assert n._bounce is None and n.commitment is None
    assert n._failure_exposures[-1].move == MoveInstance(7, HIT + 4, "CC_SLAM")


def test_a_late_table_key_is_kept_only_when_it_equals_the_key_before_it(monkeypatch):
    n, _ = anchored(monkeypatch)
    n._bounce.chain.sent[HIT + 5] = B["D"]
    vetoed = []
    monkeypatch.setattr(n, "_abort_hook_dispatch", lambda sel, **kw: vetoed.append(kw) or 0)
    sel = NS(details={"bounce_table": True}, mask=B["D"])
    assert BT.before_send(n, sel, frame=HIT + 4, target=HIT + 6, mask=B["D"], flags=0, received_frame=HIT + 5) is None
    assert BT.before_send(n, sel, frame=HIT + 4, target=HIT + 6, mask=B["D"], flags=0, received_frame=HIT + 6) is None
    assert not vetoed
    assert BT.before_send(n, sel, frame=HIT + 4, target=HIT + 6, mask=B["D"] | B["A"], flags=0,
                          received_frame=HIT + 6) == 0
    assert vetoed and vetoed[0]["event"] == "bounce_table_send_veto"


def test_the_single_row_verification_runs_once_after_the_sighting_send(monkeypatch):
    n, _ = anchored(monkeypatch)
    verify, calls = fake_verify()
    monkeypatch.setattr(BT, "verify", verify)
    t = n._bounce
    for i in range(1, 5):
        t.on_state({"frame": HIT + i - 1, "fc": FC + REL[i], "control": "Idle", "prev_seen": True})
        t.record_sent(HIT + i + 1, t.key(HIT + i + 1))
    t.on_state({"frame": HIT + 4, "fc": FC + REL[5], "control": "Slam Antic", "instance_t0": 4., "prev_seen": True,
                "pose": {"x": 30., "y": 7.45, "face": -1}, "start": start(5)})
    sel = NS(details={"bounce_table": True})
    sent = NS(chain_outcome="sent", frame=HIT + 4, target_frame=HIT + 6, desired_mask=t.key(HIT + 6))
    BT.after_send(n, sel, sent)
    assert len(calls) == 1 and t.chain.verified["pass"] and t.chain.sent[HIT + 6] == sent.desired_mask
    BT.after_send(n, sel, NS(chain_outcome="sent", frame=HIT + 5, target_frame=HIT + 7, desired_mask=0))
    assert len(calls) == 1
    ev = [e for e in n.events if e["event"] == "bounce_table_verified"]
    assert len(ev) == 1 and ev[0]["ok"] and ev[0]["verify_ms"] is not None
