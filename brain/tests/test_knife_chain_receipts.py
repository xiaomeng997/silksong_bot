"""Shared Opt1 receipt stops at the real sender and worker bootstrap boundaries; fake IPC only."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from ssbot.combat import knife_chain_receipts as R
from ssbot.combat.knife_chain_b2 import NativeChainB2
from ssbot.combat.knife_chain_native import NativeChainAudit, NativeChainAuditError
from ssbot.ipc.framing import ACTION_EXCLUSIVE
from ssbot.train import episode
from ssbot.train import forum_planner_policy as PP
from ssbot.train.forum_planner_policy import ForumPlannerPolicy
from tests.test_knife_chain_native import PolicyStub, wire_link

STOP_TIMEOUT = "missing critical application receipt beyond four-frame upper bound"
STOP_DESYNC = "key application desync: desired differs from successful send"




def st(f, report=None):
    """STATE f; report = (target, applied, desired) of the action the oracle reports, else no action fields."""
    if report is None:
        return {"f": f, "act": {}}
    t, a, d = report
    return {"f": f, "act": {"target": t, "applied": a, "mask": d, "hf": {"desired": d, "latched": d}}}


def tick(audit, f, mask, report=None, flags=0):
    """One policy tick at the real boundaries: begin (observes STATE f) -> final -> before_send -> sent."""
    audit.begin(st(f, report))
    audit.final("plan", mask)
    audit.before_send(frame=f, target=f + 2, mask=mask, flags=flags, received_frame=f)
    return audit.sent()


def fresh():
    a = R.StrictReceiptAudit()
    a.reset(1, start_frame=None)
    return a


# ---- one criterion ----


def test_b2_inherits_the_single_copy_and_keeps_its_own_hooks():
    assert "_observe_application" not in NativeChainB2.__dict__
    assert NativeChainB2._observe_application is R.Opt1ReceiptMixin._observe_application
    for hook in ("_stop", "_receipt_note", "_note", "observe", "sent", "reset", "summary"):
        assert hook in NativeChainB2.__dict__, hook       # B2's own call / log semantics stay B2's
    assert NativeChainB2.__mro__[1] is R.Opt1ReceiptMixin


# ---- the user's Opt1 on the strict audit ----
def test_matching_report_late_by_two_is_fine():
    a = fresh()
    tick(a, 100, 1)                                   # target 102
    tick(a, 101, 1, report=(101, 101, 0))             # unrelated target: no receipt, ignored
    tick(a, 102, 1)                                   # no report yet
    tick(a, 103, 1)
    tick(a, 104, 1, report=(102, 104, 1))             # applied 2 frames late
    assert 102 not in a._pending and a._application[102]["kind"] == "direct"
    assert a._receipt_counts["lag"] == 1 and a.strict_stop is None


def test_later_matching_report_covers_skipped_same_key_and_key_change():
    a = fresh()
    tick(a, 99, 1)                                    # 101
    tick(a, 100, 1)                                   # 102 (same key as 103)
    tick(a, 101, 2, report=(101, 101, 1))             # 103 with key 2 (102 had key 1)
    tick(a, 102, 2)                                   # 104
    tick(a, 103, 2, report=(103, 103, 2))             # 102 never reported; 103's report covers it: key change
    assert a._application[102]["kind"] == "covered_changed_key"
    b = fresh()
    tick(b, 99, 1)
    tick(b, 100, 1)
    tick(b, 101, 1, report=(101, 101, 1))
    tick(b, 102, 1)
    tick(b, 103, 1, report=(103, 103, 1))
    assert b._application[102]["kind"] == "covered_same_key"
    assert a.strict_stop is None and b.strict_stop is None


def test_uncovered_target_passes_through_t_plus_4_and_stops_on_t_plus_5():
    a = fresh()
    tick(a, 100, 1)                                   # 102, never reported
    for f in range(101, 107):                         # through f = 106 = T+4: no stop
        a.begin(st(f))
    with pytest.raises(R.StrictReceiptStop, match="four-frame"):
        a.begin(st(107))                              # T+5
    assert a.strict_stop == STOP_TIMEOUT and a._receipt_counts["uncovered_timeout"] == 1
    assert [e["event"] for e in list(a.events)[-2:]] == ["strict_receipt", "strict_receipt_stop"]


def test_reported_desired_differing_from_the_send_stops():
    a = fresh()
    tick(a, 100, 1)
    a.begin(st(101))
    with pytest.raises(R.StrictReceiptStop, match="desync"):
        a.begin(st(102, (102, 102, 3)))
    assert a.strict_stop == STOP_DESYNC and a._receipt_counts["desired_mismatch"] == 1


def test_exclusive_keys_are_receipts_only_and_still_cover_earlier_targets():
    a = fresh()
    tick(a, 100, 4, flags=ACTION_EXCLUSIVE)            # pause key: receipt, not pending
    assert 102 in a._receipts and 102 not in a._pending
    for f in range(101, 112):
        a.begin(st(f))                                # never reported: no timeout stop
    assert a.strict_stop is None
    b = fresh()
    tick(b, 99, 1)                                    # 101
    tick(b, 100, 1)                                   # 102 (play key, pending)
    tick(b, 101, 4, report=(101, 101, 1), flags=ACTION_EXCLUSIVE)   # 103 pause key
    b.begin(st(102))
    b.begin(st(103, (103, 103, 4)))                   # the exclusive report covers 102
    assert b._application[102]["kind"] == "covered_changed_key" and not b._pending


def test_stop_is_an_episode_harness_failure_type():
    assert issubclass(R.StrictReceiptStop, NativeChainAuditError) and issubclass(R.StrictReceiptStop, RuntimeError)


def test_strict_events_use_their_own_prefix_and_summary_reports_scope():
    a = fresh()
    tick(a, 100, 1)
    tick(a, 101, 1)
    tick(a, 102, 1)
    tick(a, 103, 1)
    tick(a, 104, 1, report=(102, 104, 1))
    names = {e["event"] for e in a.events}
    assert "strict_application_late" in names and not any(n.startswith("b2_") for n in names)
    s = a.summary()
    assert s["mode"] == "strict_receipt_audit" and s["strict_receipts"] and s["strict_stop"] is None
    assert s["pending_application"] == [103, 104, 105, 106] and s["receipt_counts"] == {"lag": 1}


# ---- the real sender boundary ----
def test_real_episode_act_records_receipt_and_pending():
    a = fresh()
    a.reset(1, start_frame=99)
    link = wire_link(a)
    episode._act(link, 100, PolicyStub(a, wanted=3, flags=0), {"f": 100, "act": {}}, None)
    assert a._receipts == {102: 3} and a._pending == {102: 3} and len(link.packets) == 1
    episode._act(link, 101, PolicyStub(a, wanted=5, flags=ACTION_EXCLUSIVE), {"f": 101, "act": {}}, None)
    assert a._receipts == {102: 3, 103: 5} and a._pending == {102: 3}


def test_transport_failure_leaves_no_receipt():
    a = fresh()
    a.reset(1, start_frame=99)
    with pytest.raises(ConnectionError):
        episode._act(wire_link(a, fail=True), 100, PolicyStub(a), {"f": 100, "act": {}}, None)
    assert a._receipts == {} and a._pending == {}


# ---- factory and manifest ----
def policy_shell():
    pol = ForumPlannerPolicy.__new__(ForumPlannerPolicy)
    pol.episode, pol.planner = 2, SimpleNamespace()
    pol.link = SimpleNamespace(frame=90)
    return pol


def test_factory_constructs_strict_audit_only_without_native(monkeypatch):
    for k in ("SSBOT_FORUM_CHAIN_AUDIT", "SSBOT_FORUM_CHAIN_NATIVE", "SSBOT_FORUM_CHAIN_B2"):
        monkeypatch.delenv(k, raising=False)
    pol = policy_shell()
    monkeypatch.setattr(PP, "CHAIN_STRICT_RECEIPTS", False)
    pol._reset_chain_native()
    assert pol.chain_native is None
    monkeypatch.setattr(PP, "CHAIN_STRICT_RECEIPTS", True)
    pol._reset_chain_native()
    audit = pol.chain_native
    assert type(audit) is R.StrictReceiptAudit and pol.planner.chain_native is audit and audit.last_observed == 90
    pol.episode = 3
    pol._reset_chain_native()
    assert pol.chain_native is audit and audit.episode == 3 and audit._pending == {}
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_NATIVE", "1")
    with pytest.raises(ValueError, match="non-candidate"):
        pol._reset_chain_native()


def test_manifest_binds_the_switch_and_reports_the_strict_mode():
    from ssbot.train import forum_measure_manifest as M
    shell = SimpleNamespace(chain_native=fresh())
    out = M._execution_bindings(shell, None)
    assert out["SSBOT_FORUM_CHAIN_STRICT_RECEIPTS"] == {"policy.chain_native.strict_receipts": True}
    assert out["SSBOT_FORUM_CHAIN_AUDIT"]["policy.chain_native.audit_mode"]["mode"] == "strict_audit"
    plain = SimpleNamespace(chain_native=NativeChainAudit())
    out = M._execution_bindings(plain, None)
    assert out["SSBOT_FORUM_CHAIN_STRICT_RECEIPTS"] == {"policy.chain_native.strict_receipts": False}
    assert out["SSBOT_FORUM_CHAIN_AUDIT"]["policy.chain_native.audit_mode"] == {
        "mode": "audit_only", "audit_only_constructed": True, "audit_switch_used": True}
    root = Path(M.__file__).resolve().parents[1]
    man = M.configuration_manifest(root, None, environ={"SSBOT_FORUM_CHAIN_STRICT_RECEIPTS": "1"}, modules=sys.modules)
    entry = man["switches"]["SSBOT_FORUM_CHAIN_STRICT_RECEIPTS"]
    assert entry["resolution"] == "runtime_binding" and entry["role"] == "control"
    assert "SSBOT_FORUM_CHAIN_STRICT_RECEIPTS" not in man["unresolved"] + man["unknown_environment_switches"]


def strict_worker(tmp_path,monkeypatch,fault=None,stop=False):
    from tests.test_b2_worker_batch import Rig
    from ssbot.tools import combat_run as C
    from ssbot.train import episode as E
    rig=Rig(tmp_path,monkeypatch,fault=fault)
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_B2","0")
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_NATIVE","0")
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_STRICT_RECEIPTS","1")
    class Policy:
        def __init__(self):
            rig.events.append("strict_policy.new")
            self.episode=0;self.chain_native=fresh()
        def attach(self,link):self.link=link
        def warmup(self):rig.events.append("warmup");return 0.
        def flush_log(self):rig.events.append("policy.flush")
        def flush_keys(self):rig.events.append("keys.flush")
    monkeypatch.setattr(C,"make_policy",lambda *a,**k:Policy())
    def run(link,enc,tap,pol,cfg,rec):
        rig.attempts+=1;rig.events.append("episode");pol.episode+=1
        rec.outcome="CLEAR";rec.ingame_s=1.
        if stop:
            # Receipt semantics are tested above; here test its propagation to
            # the real worker row and break, independently of B2/budget files.
            try:pol.chain_native._stop(STOP_TIMEOUT,1001)
            except R.StrictReceiptStop as exc:rec.outcome="HARNESS_FAIL";rec.reason=str(exc)
    monkeypatch.setattr(E,"run_episode",run)
    def after(link,enc,instance,d):
        rig.events.append("after_episode")
        row=__import__('json').loads((tmp_path/"attempts_i0.jsonl").read_text().splitlines()[-1])
        assert "b2_reservation" not in row
        if stop:assert row["strict_receipt_stop"]==STOP_TIMEOUT
    monkeypatch.setattr(C,"after_episode",after)
    return rig


def test_strict_worker_reads_its_own_input_before_policy_or_ready(tmp_path,monkeypatch):
    import json
    rig=strict_worker(tmp_path,monkeypatch)
    assert rig.run(encounter="Forum_W_w13",episodes=1)==0
    assert rig.events.index("input.stats")<rig.events.index("strict_policy.new")<rig.events.index("ready")
    receipt=json.loads((tmp_path/"strict_input_path_i0.json").read_text())
    assert receipt["passed"] and receipt["peer"]==["127.0.0.1",47017]
    assert len(rig.links)==1 and all(p.closed for p in rig.links)
    assert not (tmp_path/"budget.json").exists() and not rig.receipts()
    assert all(p.closed for p in rig.links) and rig.events.count("ipc.close")==1


def test_strict_worker_bad_input_stops_before_policy_and_episode(tmp_path,monkeypatch):
    import json
    rig=strict_worker(tmp_path,monkeypatch,fault="input_pending")
    with pytest.raises(ValueError,match="input.stats"):rig.run(encounter="Forum_W_w13",episodes=1)
    assert rig.attempts==0 and "ready" not in rig.events and "strict_policy.new" not in rig.events
    assert json.loads((tmp_path/"strict_input_path_i0.json").read_text())["passed"] is False
    assert all(p.closed for p in rig.links) and rig.events.count("ipc.close")==1
    assert not rig.receipts()  # the durable worker resource receipt is B2-only


def test_strict_stop_records_failure_and_prevents_another_episode(tmp_path,monkeypatch):
    import json
    rig=strict_worker(tmp_path,monkeypatch,stop=True)
    assert rig.run(encounter="Forum_W_w13",episodes=3)==0
    rows=[json.loads(x) for x in (tmp_path/"attempts_i0.jsonl").read_text().splitlines()]
    assert len(rows)==rig.attempts==rig.events.count("ready")==1
    assert rows[0]["outcome"]=="HARNESS_FAIL" and rows[0]["strict_receipt_stop"]==STOP_TIMEOUT
    assert rig.events.index("after_episode")<rig.events.index("ipc.close")
    assert not (tmp_path/"budget.json").exists() and not rig.receipts()
    assert all(p.closed for p in rig.links) and rig.events.count("ipc.close")==1
