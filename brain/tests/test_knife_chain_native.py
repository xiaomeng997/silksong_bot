"""Real policy/sender boundary tests; no game, table generator or strict oracle."""
from collections import deque
from types import SimpleNamespace
import threading

import msgpack
import pytest

from ssbot.combat.knife_chain_admission import AdmissionDecision
from ssbot.combat.knife_chain_native import NativeChainAudit
from ssbot.ipc.framing import HEADER, MsgType
from ssbot.ipc.oracle_link import OracleLink
from ssbot.train import episode
from ssbot.train.forum_planner_policy import ForumPlannerPolicy


def state(f, *, target=-1, applied=-1, mask=0, desired=0):
    return {"f": f, "act": {"target": target, "applied": applied, "mask": mask,
                            "hf": {"desired": desired, "latched": mask}}}


def wire_link(audit=None, *, fail=False):
    # Exercise actual OracleLink.act -> _send -> framing.encode, without sockets.
    link = OracleLink.__new__(OracleLink)
    link._seq, link._state = 0, {"f": 100}
    link._send_lock = threading.Lock()
    link.measurement = None
    link.packets = []
    def sendall(packet):
        if audit is not None:
            payload = msgpack.unpackb(packet[HEADER.size:])
            assert audit.dispatch.sent_for(payload[0]) is None  # still an intention
        if fail:
            raise ConnectionError("injected transport failure")
        link.packets.append(packet)
    link.sock = SimpleNamespace(sendall=sendall)
    return link


class PolicyStub:
    _begin_chain_native = ForumPlannerPolicy._begin_chain_native
    _measure_choice = ForumPlannerPolicy._measure_choice

    def __init__(self, audit=None, *, owner="plan", wanted=3, flags=0, row=4, chain_row=False):
        self.chain_native, self.measurement = audit, None
        self.owner, self.wanted, self.action_flags = owner, wanted, flags
        self.row, self.chain_row = row, chain_row
        self._inbox = None
        self.sent = {}

    def act(self, s, tap):
        self._begin_chain_native(s)
        audit = self.chain_native
        if audit is not None:
            if self.chain_row:
                dec = AdmissionDecision("slam.air", "pass", s["f"], "fit:v1", ())
                offer = audit.dispatch.offer("slam.air", 3, table_ref="table:test", admission=dec)
                audit.register_row(4, offer)
            audit.planner_result(SimpleNamespace(idx=self.row, mask=3, name="native_row"))
        self.sent[s["f"] + 2] = self.wanted  # legacy intention is not a send receipt
        self._measure_choice(self.owner, self.wanted)
        return self.wanted


def unpack(packet):
    h = HEADER.unpack(packet[:HEADER.size])
    assert h[1] == MsgType.ACTION
    return msgpack.unpackb(packet[HEADER.size:])


@pytest.mark.parametrize("owner,mask,flags", [("plan", 3, 0), ("sup", 3, 1), ("slam", 7, 0),
                                             ("real_quit", 0, 1), ("no_world_state", 0, 0)])
def test_opt_in_audit_preserves_exact_action_bytes_and_final_owner(owner, mask, flags):
    plain_link, audit_link = wire_link(), wire_link()
    plain = PolicyStub(owner=owner, wanted=mask, flags=flags)
    audit = NativeChainAudit()
    pol = PolicyStub(audit, owner=owner, wanted=mask, flags=flags)
    for f in range(100, 116):
        plain_link._state = audit_link._state = {"f": f}
        episode._act(plain_link, f, plain, state(f), None)
        episode._act(audit_link, f, pol, state(f), None)
    assert plain_link.packets == audit_link.packets
    assert unpack(audit_link.packets[0]) == [102, mask, 0, 0] + ([flags] if flags else [])
    assert audit.dispatch.sent_for(102).owner == owner
    assert audit.counts["transport_sent"] == 16


@pytest.mark.parametrize("owner,mask,outcome", [("plan", 3, "sent"), ("sup", 3, "overridden"),
                                                ("slam", 3, "overridden"), ("plan", 2, "overridden")])
def test_native_row_choice_and_supervisor_are_separate_from_transport(owner, mask, outcome):
    audit = NativeChainAudit()
    pol = PolicyStub(audit, owner=owner, wanted=mask, chain_row=True)
    link = wire_link(audit)
    episode._act(link, 100, pol, state(100), None)
    sent = audit.dispatch.sent_for(102)
    assert sent.selection is not None and sent.chain_outcome == outcome
    assert sent.wire_mask is None
    assert audit.counts["chain_selected"] == 1
    assert audit.counts["transport_sent"] == 1
    assert pol.sent[102] == mask


def test_unselected_row_does_not_advance_chain_ownership():
    audit = NativeChainAudit()
    pol = PolicyStub(audit, chain_row=True, row=9)
    episode._act(wire_link(audit), 100, pol, state(100), None)
    assert audit.counts["row_registered"] == 1
    assert audit.dispatch.selection is None
    assert audit.dispatch.sent_for(102).chain_outcome == "unselected"


def test_transport_failure_leaves_no_receipt_despite_policy_intention():
    audit = NativeChainAudit()
    pol = PolicyStub(audit, chain_row=True)
    link = wire_link(audit, fail=True)
    with pytest.raises(ConnectionError, match="injected"):
        episode._act(link, 100, pol, state(100), None)
    assert pol.sent[102] == 3
    assert audit.dispatch.sent_for(102) is None
    assert audit.counts["transport_sent"] == 0
    assert audit.counts["transport_failed"] == 1


def test_hold_filter_changes_under_one_applied_target_are_not_conflicting_receipts():
    audit = NativeChainAudit()
    episode._act(wire_link(audit), 100, PolicyStub(audit), state(100), None)
    audit.observe(state(102, target=102, applied=102, mask=2, desired=3))
    audit.observe(state(103, target=102, applied=102, mask=3, desired=3))
    samples = [x for x in audit.events if x["event"] == "application_sample"]
    assert [x["latched_mask"] for x in samples] == [2, 3]
    assert all(x["desired_agrees"] for x in samples)
    assert audit.counts["application_first_seen"] == 1
    assert audit.dispatch.sent_for(102).wire_mask is None
    assert audit.summary()["wire_prediction"] == "unchecked"


def test_late_action_sample_is_not_presented_as_exact_application_latch():
    audit = NativeChainAudit()
    episode._act(wire_link(audit), 100, PolicyStub(audit), state(100), None)
    audit.observe(state(106, target=102, applied=104, mask=3, desired=3))
    first = next(x for x in audit.events if x["event"] == "application_first_seen")
    assert first["applied"] == 104 and first["frame"] == 106
    assert first["exact_application_frame"] is False
    assert audit.counts["state_gap"] == 1


def test_inbox_catchup_excludes_future_and_previous_episode_frames():
    audit = NativeChainAudit()
    audit.reset(2, start_frame=98)
    audit.begin(state(102), history=[state(90), state(99), state(100), state(101), state(103)])
    assert [x["frame"] for x in audit.events if x["event"] == "state_sample"] == [99, 100, 101, 102]
    assert audit.last_observed == 102
    audit.reset(3)  # no trusted fence: only the first current STATE is imported
    audit.begin(state(4), history=[state(1), state(2), state(5)])
    assert [x["frame"] for x in audit.events if x["event"] == "state_sample"] == [4]


@pytest.mark.parametrize("fresh,mask", [(False, 3), (True, 7)])
def test_reused_or_mismatched_planner_result_does_not_select_registered_offer(fresh, mask):
    audit = NativeChainAudit()
    audit.begin(state(100))
    dec = AdmissionDecision("slam.air", "pass", 100, "fit:v1", ())
    offer = audit.dispatch.offer("slam.air", 3, table_ref="t", admission=dec)
    audit.register_row(4, offer)
    audit.planner_result(SimpleNamespace(idx=4, mask=mask, name="row"), fresh=fresh)
    assert audit.dispatch.selection is None
    assert audit.counts["row_identity_reject"] == 1


def test_real_policy_missing_world_path_reaches_real_sender_without_measurement():
    pol = ForumPlannerPolicy.__new__(ForumPlannerPolicy)
    pol.chain_native, pol.measurement = NativeChainAudit(), None
    pol._inbox, pol.real_quit = None, False
    pol._catch_up = lambda *args: None
    pol.keylog = SimpleNamespace(observe=lambda *a: None, tick=lambda *a: None)
    pol.backend = SimpleNamespace(feed=lambda *a: None)
    pol.raw, pol.sent = {}, {}
    link = wire_link(pol.chain_native)
    episode._act(link, 100, pol, state(100), None)
    assert unpack(link.packets[0]) == [102, 0, 0, 0]
    assert pol.chain_native.dispatch.sent_for(102).owner == "no_world_state"


def test_actual_policy_reset_helper_is_opt_in_and_clears_both_receivers(monkeypatch):
    pol = ForumPlannerPolicy.__new__(ForumPlannerPolicy)
    pol.episode, pol.planner = 2, SimpleNamespace()
    pol.link = SimpleNamespace(frame=90)
    monkeypatch.delenv("SSBOT_FORUM_CHAIN_AUDIT", raising=False)
    pol._reset_chain_native()
    assert pol.chain_native is None and pol.planner.chain_native is None
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_AUDIT", "1")
    pol._reset_chain_native()
    audit = pol.chain_native
    assert pol.planner.chain_native is audit
    assert audit.episode == 2 and audit.last_observed == 90
    episode._act(wire_link(audit), 100, PolicyStub(audit), state(100), None)
    pol.episode, pol.link.frame = 3, 200
    pol._reset_chain_native()
    assert audit.dispatch.sent_for(102) is None and audit.counts == {}
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_AUDIT", "0")
    pol._reset_chain_native()
    assert pol.chain_native is None and pol.planner.chain_native is None


def test_observation_missing_or_inconsistent_fields_stays_unknown():
    audit = NativeChainAudit()
    episode._act(wire_link(audit), 100, PolicyStub(audit), state(100), None)
    audit.observe({"f": 101})
    audit.observe(state(102, target=102, applied=105, mask=3))
    assert audit.counts["action_unknown"] >= 2
    assert audit.counts["application_first_seen"] == 0


def test_trace_eviction_is_explicit_and_summary_is_not_a_full_log():
    audit = NativeChainAudit(trace_limit=2)
    audit.begin(state(1))
    audit.final("plan", 0)
    summary = audit.summary()
    assert len(summary["trace"]) == 2 and summary["trace_evicted"] > 0
    assert summary["buffer_complete"] is False
    assert summary["candidate_generation"] is False


@pytest.mark.parametrize("measurement", [None, SimpleNamespace(detail=False)])
def test_final_owner_capture_does_not_require_measurement_detail(measurement):
    pol = PolicyStub(NativeChainAudit())
    pol.measurement = measurement
    pol._begin_chain_native(state(100))
    pol._measure_choice("sup", 7)
    assert pol.chain_native.counts["policy_final"] == 1
    assert pol.chain_native.summary()["send_scope"] == "episode._act_only"


def test_disabled_factory_never_imports_chain_runtime(monkeypatch):
    import builtins
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.endswith("knife_chain_native"):
            raise AssertionError("default-off factory imported new runtime")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    monkeypatch.delenv("SSBOT_FORUM_CHAIN_AUDIT", raising=False)
    pol = ForumPlannerPolicy.__new__(ForumPlannerPolicy)
    pol.episode, pol.planner = 0, None
    pol._reset_chain_native()
    assert pol.chain_native is None



def test_native_prefix_snapshot_distinguishes_missing_send_and_unknown_wire():
    audit = NativeChainAudit()
    episode._act(wire_link(audit), 99, PolicyStub(audit, wanted=1), state(99), None)
    audit.begin(state(100))
    hold = SimpleNamespace(latched=[0], desired=[0], pending=[0], age=[2])
    audit.planner_input(origin=99, prefix=[0, 1], hold=hold, hero_state=[1.0, 2.0])
    ctx = audit.summary()["last_planner_context"]
    assert ctx["prefix"] == [{"target": 100, "planner_desired": 0, "transport_desired": None, "wire": None},
                              {"target": 101, "planner_desired": 1, "transport_desired": 1, "wire": None}]
    hold.desired[0] = 7
    ctx["hold"]["desired"][0] = 8
    assert audit.planner_context["hold"]["desired"] == [0]


def test_native_prefix_frame_mismatch_is_detected_before_planning():
    audit = NativeChainAudit()
    audit.begin(state(100))
    with pytest.raises(RuntimeError, match="prefix"):
        audit.planner_input(origin=98, prefix=[0], hold=None, hero_state=None)



def test_native_integrity_error_is_an_episode_harness_failure_type():
    audit = NativeChainAudit()
    audit.begin(state(100))
    with pytest.raises(RuntimeError, match="decision frame"):
        audit.before_send(frame=99, target=101, mask=0, flags=0, received_frame=100)
    assert audit.dispatch.sent_for(101) is None


def test_unfitted_selected_row_needs_a_named_probe_before_any_send():
    audit = NativeChainAudit()
    audit.begin(state(100))
    dec = AdmissionDecision("slam.air", "unchecked", 100, None, ())
    offer = audit.dispatch.offer("slam.air", 3, table_ref="table:test", admission=dec)
    audit.register_row(4, offer)
    with pytest.raises(RuntimeError, match="probe"):
        audit.planner_result(SimpleNamespace(idx=4, mask=3, name="row"))
    assert audit.dispatch.selection is None and audit.counts["row_contract_error"] == 1
