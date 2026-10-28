"""Measurement observes actual IPC and fails closed on lost or inconsistent evidence."""
import json
import threading
from types import SimpleNamespace

import msgpack
import pytest

from ssbot.ipc.framing import HEADER, MsgType, encode
from ssbot.ipc.oracle_link import OracleLink
from ssbot.train.measurement import MeasurementError, MeasurementTrace, escape_evidence, validate_trace


class Clock:
    def __init__(self):
        self.n = 0

    def __call__(self):
        self.n += 100
        return self.n


class Socket:
    def __init__(self, incoming=b"", fail=False):
        self.incoming = incoming
        self.sent = []
        self.fail = fail

    def recv(self, count):
        chunk, self.incoming = self.incoming[:count], self.incoming[count:]
        return chunk

    def sendall(self, data):
        if self.fail:
            raise ConnectionError("test send failure")
        self.sent.append(data)


def link(trace=None, socket=None):
    obj = OracleLink.__new__(OracleLink)
    obj.sock = socket or Socket()
    obj.measurement = trace
    obj._send_lock = threading.Lock()
    obj._seq = 0
    return obj


def trace():
    obj = MeasurementTrace(clock_ns=Clock())
    obj.start_episode(3)
    return obj


def tick(obj, f=10, owner="plan", mask=7, flags=1):
    obj.received(f, f, obj.clock())
    obj.begin_tick({"f": f, "dt": 0., "act": {"mask": 2}})
    obj.begin_decision()
    obj.decision({"owner": owner}, returned_mask=mask, flags=flags)


def test_trace_on_and_off_send_identical_wire_bytes_including_flags_and_sequence():
    observed = trace()
    a, b = link(), link(observed)
    tick(observed)
    for obj in (a, b):
        obj.act(12, 7, hold_frames=0, ack_seq=9, flags=1)
        obj._send(MsgType.RPC_REQ, msgpack.packb({"id": 1, "name": "ping"}))
        obj.act(13, 7, hold_frames=2)
    observed.end_tick()
    assert a.sock.sent == b.sock.sent
    actions = [r for r in observed.records() if r["kind"] == "action"]
    assert [r["action_seq"] for r in actions] == [1, 3]
    assert actions[0]["owner"] == "plan" and actions[0]["flags"] == 1
    assert actions[0]["policy_mask_matches_wire"] is True
    assert actions[1]["hold_frames"] == 2


def test_read_loop_preserves_state_and_raw_frame_and_captures_real_header_sequence():
    observed = trace()
    state = {"f": 55, "dt": 0.0, "act": {"mask": 8}, "ev": []}
    wire = encode(MsgType.STATE, 0x12345678, msgpack.packb(state))
    obj = link(observed, Socket(wire))
    raw, decoded = [], []
    obj._raw_subscribers = [lambda kind, data: raw.append((kind, data))]
    obj._state_subscribers = [decoded.append]
    obj._state_cv = threading.Condition()
    obj._rpc, obj.closed = {}, False
    obj._read_loop()
    assert decoded == [state] and obj._state == state
    assert raw == [(MsgType.STATE, wire)]
    assert observed.records()[0]["state_seq"] == 0x12345678
    assert "recv_ns" not in decoded[0]


def test_failed_send_is_not_reported_as_an_action():
    observed = trace()
    tick(observed)
    with pytest.raises(ConnectionError):
        link(observed, Socket(fail=True)).act(12, 7)
    observed.end_tick(error="ConnectionError")
    assert not any(r["kind"] == "action" for r in observed.records())
    assert observed.records()[-1]["error"] == "ConnectionError"


def test_no_action_turns_and_unreceived_states_are_retained_without_fabricated_times():
    observed = trace()
    observed.begin_tick({"f": 10, "dt": 0.0})
    observed.end_tick()
    observed.begin_tick({"f": 13, "dt": 0.005})
    observed.end_tick()
    a, b = observed.records()
    assert a["actions"] == b["actions"] == 0
    assert a["recv_ns"] is None and a["decision_end_ns"] is None
    assert a["dt"] == 0.0 and b["processed_frame_gap"] == 3


@pytest.mark.parametrize("info,idx,status", [
    ({}, 2, "unchecked"),
    ({"esc": {"fail": 0}}, 2, "unchecked"),
    ({"esc": {"row": 2, "checked": 0, "fail": 0}}, 2, "unchecked"),
    ({"esc": {"row": 1, "checked": 3, "fail": 0}}, 2, "unchecked"),
    ({"esc": {"row": 2, "checked": 3, "fail": 0}}, 2, "pass"),
    ({"esc": {"row": 2, "checked": 3, "fail": 1}}, 2, "fail"),
])
def test_escape_requires_evidence_for_the_final_row(info, idx, status):
    assert escape_evidence(info, idx)["status"] == status


def test_overflow_is_explicit_and_prevents_a_complete_footer(tmp_path):
    observed = MeasurementTrace(max_records=1, clock_ns=Clock())
    observed.start_episode(0)
    observed.received(1, 1, observed.clock())
    observed.received(2, 2, observed.clock())
    with pytest.raises(MeasurementError, match="overflow"):
        observed.check()
    path = tmp_path / "overflow.jsonl"
    result = observed.write(path)
    assert result["overflow"] == 1 and not result["complete"]
    assert not validate_trace(path)["complete"]


def test_write_validate_and_tampered_missing_duplicate_and_truncated_records(tmp_path):
    observed = trace()
    tick(observed)
    link(observed).act(12, 7, flags=1)
    observed.end_tick()
    path = tmp_path / "ok.jsonl"
    observed.write(path)
    assert validate_trace(path)["complete"]
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    for name, changed in (
        ("missing", rows[:2] + rows[3:]),
        ("duplicate", rows[:2] + [rows[2]] + rows[2:]),
        ("mismatch", [{**r, "policy_mask_matches_wire": False} if r["kind"] == "action" else r for r in rows]),
        ("truncated", rows[:-1]),
    ):
        bad = tmp_path / f"{name}.jsonl"
        bad.write_text("".join(json.dumps(row) + "\n" for row in changed))
        assert not validate_trace(bad)["complete"], name


def test_failed_write_preserves_buffer_and_does_not_overwrite_existing_file(tmp_path):
    observed = trace()
    observed.received(10, 1, observed.clock())
    path = tmp_path / "exists.jsonl"
    path.write_text("keep me")
    before = observed.records()
    with pytest.raises(FileExistsError):
        observed.write(path)
    assert observed.records() == before and path.read_text() == "keep me"


def test_script_override_does_not_inherit_the_planner_rows_escape_certificate():
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy
    obj = ForumPlannerPolicy.__new__(ForumPlannerPolicy)
    obj.measurement = trace()
    res = SimpleNamespace(idx=2, name="ROW", mask=7, t_ms={"total": 1.0})
    obj.planner = SimpleNamespace(measurement_result=res,
                                  last_info={"esc": {"row": 2, "checked": 1, "fail": 0}})
    obj._measure_choice("slam", 7, res)
    assert obj.measurement_choice["planner_escape"]["status"] == "pass"
    assert obj.measurement_choice["final_key_escape"] == "unchecked"
    obj.planner.measurement_result = None
    obj._measure_choice("plan", 7, res)
    assert obj.measurement_choice["planner_escape"]["status"] == "unchecked"


def test_timing_control_preserves_wire_and_declares_that_it_has_no_action_detail(tmp_path):
    obj = MeasurementTrace(detail=False, clock_ns=Clock())
    obj.start_episode(3)
    tick(obj)
    measured, plain = link(obj), link()
    measured.act(12, 7, flags=1)
    plain.act(12, 7, flags=1)
    obj.end_tick()
    assert measured.sock.sent == plain.sock.sent
    assert [r["kind"] for r in obj.records()] == ["tick"]
    path = tmp_path / "timing.jsonl"
    obj.write(path)
    checked = validate_trace(path)
    assert checked["complete"] and not checked["detail"]
    assert checked["owner_coverage"] is None


@pytest.mark.parametrize("args", [["--no-record"], ["--time-scale", "2"], ["--inject-hits", ".1"]])
def test_measurement_cli_rejects_incompatible_collection_before_launch(args):
    from ssbot.tools.combat_run import main
    with pytest.raises(SystemExit) as exc:
        main(["run", "--measure", "--threads", "4", "--mode", "eval", "--policy", "planner", *args])
    assert exc.value.code == 2


def test_valid_timing_calibration_arguments_reach_dispatch_without_starting_a_game(monkeypatch):
    from ssbot.tools import combat_run
    monkeypatch.setattr(combat_run, "run", lambda a: 17 if a.measure_timing_only and a.encounter == "Forum_W_w13" else 0)
    assert combat_run.main(["run", "--measure", "--measure-timing-only", "--threads", "4", "--mode", "eval",
                            "--policy", "planner", "--encounter", "Forum_W_w13"]) == 17
