"""Task 178 live 786766c3: an episode that raises keeps what it collected, marked aborted, and its original error.

The live worker died on a ValueError in policy.act (2625): attempts_i0.jsonl stayed empty and no measurement trace,
manifest or decision rows were written, although the records up to the error existed in memory.
"""
import json
from types import SimpleNamespace
from collections import deque
import pytest
from ssbot.train.measurement import MeasurementTrace, validate_trace
from tests.test_b2_worker_batch import Rig


def test_episode_exception_writes_an_aborted_attempt_and_keeps_the_original_error(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch, fault="episode")
    with pytest.raises(RuntimeError, match="episode failed"):
        rig.run(episodes=1)
    (line,) = (tmp_path / "attempts_i0.jsonl").read_text().splitlines()
    d = json.loads(line)
    assert d["complete"] is False and (d["aborted"]["type"], d["aborted"]["message"]) == ("RuntimeError", "episode failed")
    # the fake set CLEAR before raising: kept beside, never reported as the outcome
    assert (d["outcome"], d["reason"], d["outcome_before_abort"]) == ("HARNESS_FAIL", "RuntimeError: episode failed", "CLEAR")
    assert d["abort_persisted"] == {"decision_ring": "not_supported"} and "secondary_errors" not in d
    assert d["b2_reservation"]["seed"] == d["seed"]
    receipt = rig.receipts()[0]
    assert "episode failed" in receipt["primary_error"] and receipt["secondary_errors"] == []
    assert rig.links[0].closed and rig.events.count("recorder.close") == 1


def test_a_failing_persistence_step_is_secondary_and_never_replaces_the_error(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch, fault="episode")
    from ssbot.tools import combat_run as C
    real = C.make_policy

    def policy(*a, **k):
        p = real(*a, **k)
        p.log_abort_ring = lambda: (_ for _ in ()).throw(OSError("decision log disk full"))
        return p

    monkeypatch.setattr(C, "make_policy", policy)
    with pytest.raises(RuntimeError, match="episode failed"):
        rig.run(episodes=1)
    d = json.loads((tmp_path / "attempts_i0.jsonl").read_text().splitlines()[0])
    problem = {"origin": "abort_persist.decision_ring", "reason": "OSError: decision log disk full"}
    assert d["abort_persisted"]["decision_ring"] == {"failed": "OSError: decision log disk full"}
    assert d["secondary_errors"] == [problem]
    receipt = rig.receipts()[0]
    assert "episode failed" in receipt["primary_error"] and problem in receipt["secondary_errors"]


def test_aborted_trace_keeps_its_records_and_never_validates_complete(tmp_path):
    m = MeasurementTrace()
    m.start_episode(0)
    m.received(2625, 1, 10)
    m.begin_tick({"f": 2625, "act": {}})
    m.end_tick(error="ValueError")
    summary = m.write(tmp_path / "t.jsonl", aborted="ValueError: failure exposure requires a supported observed move family")
    assert summary["complete"] is False and summary["records"] == 2 and summary["aborted"].startswith("ValueError")
    rows = [json.loads(x) for x in (tmp_path / "t.jsonl").read_text().splitlines()]
    assert rows[-1]["complete"] is False and rows[2]["error"] == "ValueError"
    check = validate_trace(tmp_path / "t.jsonl")
    assert check["complete"] is False and any(p.startswith("episode aborted: ValueError") for p in check["problems"])
    assert "incomplete buffer" not in check["problems"]


def test_decision_ring_goes_to_the_log_once_like_an_event(tmp_path):
    from ssbot.train.planner_policy import PlannerPolicy
    p = object.__new__(PlannerPolicy)
    p.log_path = tmp_path / "decisions_i0.jsonl"; p._log_buf = []; p.ring = deque([{"f": 2623}, {"f": 2624}], maxlen=90)
    assert p.log_abort_ring() == 2 and not p.ring
    assert [json.loads(x)["f"] for x in p.log_path.read_text().splitlines()] == [2623, 2624]
    assert p.log_abort_ring() == 0 and len(p.log_path.read_text().splitlines()) == 2
    q = object.__new__(PlannerPolicy)
    q.log_path = None; q._log_buf = []; q.ring = deque([{"f": 1}], maxlen=90)
    assert q.log_abort_ring() == 0
