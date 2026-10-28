"""Opt-in observation of the existing controller; never selects or sends keys.

The reader and control threads append bounded, in-memory records. JSON and disk I/O
belong to ``write`` after an episode. Missing evidence stays unknown. Raw STATEs
and their events remain the recorder's responsibility.
"""
from __future__ import annotations

import json
import copy
import threading
import time
from collections import OrderedDict
from pathlib import Path

SCHEMA = 1


class MeasurementError(RuntimeError):
    pass


def warm_query_kernels() -> dict:
    """Compile the real query signatures before measurement, without policy state.

    The old empty-forecast warmup never reaches these nonempty support paths.
    Signatures follow the contiguous arrays built by their production callers.
    """
    from numba import types
    from ssbot.combat import enemy_tables, fastquery, multi_forecast
    u1 = types.Array(types.uint8, 1, "C")
    i1, i2 = (types.Array(types.int64, dim, "C") for dim in (1, 2))
    f1, f2 = (types.Array(types.float64, dim, "C") for dim in (1, 2))
    b2 = types.Array(types.boolean, 2, "C")
    targets = [
        (enemy_tables._query_win_par, (u1, i2, i2, f2, f1, f2, f2, b2, types.int64, f2, f2)),
        (multi_forecast._bbox_boxes, (f1, f2, i2, i1, f1, f1, f1, f1, f1, f1, f1, i1, f1, types.float64)),
        (multi_forecast._box_hits, (f2, f2, f2, f2, f2, f2, b2, types.float64, types.float64)),
        (fastquery._query_par, (u1, i1, i2, f2, u1, f1, f2, f2, b2, types.int64, f2, f2)),
    ]
    result = {}
    for dispatcher, signature in targets:
        started = time.perf_counter_ns()
        dispatcher.compile(signature)
        result[dispatcher.py_func.__module__ + "." + dispatcher.py_func.__name__] = {
            "signature": str(signature), "warmup_ms": (time.perf_counter_ns() - started) / 1e6}
    return result


def escape_evidence(info: dict | None, final_idx: int | None) -> dict:
    """A zero failure count without an identified, checked final row is no pass."""
    esc = (info or {}).get("esc") or {}
    row = esc.get("row")
    checked = esc.get("checked", 0)
    failures = esc.get("fail")
    same = row is not None and row == final_idx and checked > 0
    status = "unchecked"
    if same and failures is not None:
        status = "pass" if failures == 0 else "fail"
    return {"status": status, "checked_row": row, "final_row": final_idx,
            **{k: esc.get(k) for k in ("checked", "fail", "threats", "cut", "forced", "why")},
            "scope": "planner_escape_check", "full_path_certified": False}


class MeasurementTrace:
    def __init__(self, *, max_records: int = 100_000, receive_history: int = 4096,
                 clock_ns=None, detail: bool = True):
        if max_records < 1 or receive_history < 1:
            raise ValueError("measurement buffer limits must be positive")
        self.max_records = max_records
        self.receive_history = receive_history
        self.clock = clock_ns or time.perf_counter_ns
        self.detail = detail
        self._lock = threading.Lock()
        self._received = OrderedDict()
        self._contexts: dict[int, dict] = {}
        self._rows: list[dict] = []
        self._overflow = 0
        self._last_frame = None
        self.episode = None
        self.window = None

    def start_episode(self, episode: int) -> None:
        with self._lock:
            if self._contexts:
                raise MeasurementError("cannot reset measurement during a tick")
            if self._rows:
                raise MeasurementError("previous measurement records have not been written")
            self.episode = episode
            self._overflow = 0
            self._last_frame = None
            self.window = None

    def observe_state(self, state: dict) -> None:
        window = self.window
        if window is not None:
            with self._lock:
                received = self._received.get(state["f"])
            window.observe(state, received[1] if received else None)

    def _append_locked(self, row: dict) -> None:
        if len(self._rows) < self.max_records:
            self._rows.append(row)
        else:
            self._overflow += 1

    def received(self, frame: int, sequence: int, received_ns: int) -> None:
        with self._lock:
            self._received[frame] = (sequence, received_ns)
            self._received.move_to_end(frame)
            while len(self._received) > self.receive_history:
                self._received.popitem(last=False)
            if self.episode is not None and self.detail:
                self._append_locked({"kind": "receive", "ep": self.episode, "f": frame,
                                     "state_seq": sequence, "recv_ns": received_ns})

    def begin_tick(self, state: dict) -> None:
        started = self.clock()
        tid = threading.get_ident()
        frame = state["f"]
        with self._lock:
            if tid in self._contexts:
                raise MeasurementError("nested measurement tick")
            received = self._received.get(frame)
            ctx = {"kind": "tick", "ep": self.episode, "f": frame,
                   "state_seq": received[0] if received else None,
                   "recv_ns": received[1] if received else None,
                   "tick_start_ns": started, "dt": state.get("dt"),
                   "processed_frame_gap": None if self._last_frame is None else frame - self._last_frame,
                   "latched_mask": (state.get("act") or {}).get("mask"),
                   "hold_filter": copy.deepcopy((state.get("act") or {}).get("hf")) if self.detail else None,
                   "decision_start_ns": None, "decision_end_ns": None,
                   "owner": None, "actions": 0}
            self._last_frame = frame
            self._contexts[tid] = ctx

    def begin_decision(self) -> None:
        with self._lock:
            ctx = self._contexts.get(threading.get_ident())
            if ctx is not None:
                ctx["decision_start_ns"] = self.clock()

    def decision(self, choice: dict | None, *, returned_mask: int, flags: int,
                 fallback_owner: str | None = None) -> None:
        ended = self.clock()
        with self._lock:
            ctx = self._contexts.get(threading.get_ident())
            if ctx is None:
                return
            ctx.update(choice or {})
            ctx.update(decision_end_ns=ended, returned_mask=int(returned_mask), flags=int(flags))
            if ctx.get("owner") is None:
                ctx["owner"] = fallback_owner

    def sent(self, sequence: int, body, sent_ns: int) -> None:
        """Called only after sendall succeeded, with its sequence still under the send lock."""
        target, mask, hold, ack = body[:4]
        flags = body[4] if len(body) > 4 else 0
        with self._lock:
            if self.episode is None:
                return
            ctx = self._contexts.get(threading.get_ident())
            if not self.detail:
                if ctx is not None:
                    ctx["actions"] += 1
                    ctx["send_done_ns"] = sent_ns
                return
            row = {"kind": "action", "ep": self.episode, "action_seq": sequence,
                   "target_frame": target, "mask": mask, "hold_frames": hold,
                   "ack_seq": ack, "flags": flags, "send_done_ns": sent_ns,
                   "f": ctx["f"] if ctx else None,
                   "owner": ctx.get("owner") if ctx else "harness",
                   "tick_start_ns": ctx["tick_start_ns"] if ctx else None}
            latest = next(reversed(self._received), None)
            row["latest_received_frame_at_send"] = latest
            row["target_already_observed"] = latest >= target if latest is not None else None
            if ctx is not None:
                if ctx.get("decision_start_ns") is None:
                    row["owner"] = ctx["owner"] = "harness"
                ctx["actions"] += 1
                ctx["send_done_ns"] = sent_ns
                row["policy_mask_matches_wire"] = (ctx["returned_mask"] == mask
                                                    if "returned_mask" in ctx else None)
                row["policy_flags_match_wire"] = ctx["flags"] == flags if "flags" in ctx else None
            self._append_locked(row)

    def end_tick(self, *, error: str | None = None) -> None:
        with self._lock:
            ctx = self._contexts.pop(threading.get_ident(), None)
            if ctx is None:
                raise MeasurementError("measurement tick was not started")
            ctx["error"] = error
            self._append_locked(ctx)
            # Includes record construction, lock acquisition and insertion in the buffer.
            ctx["tick_end_ns"] = self.clock()
            ctx["total_tick_ms"] = (ctx["tick_end_ns"] - ctx["tick_start_ns"]) / 1e6

    def check(self) -> None:
        with self._lock:
            if self._overflow:
                raise MeasurementError(f"measurement buffer overflow: {self._overflow} records lost")

    def records(self) -> list[dict]:
        with self._lock:
            if self._contexts:
                raise MeasurementError("cannot snapshot measurement during a tick")
            return [dict(row) for row in self._rows]

    def write(self, path: Path) -> dict:
        """Only between episodes. Failed/truncated writes retain the buffer and raise."""
        with self._lock:
            if self._contexts:
                raise MeasurementError("cannot write measurement during a tick")
            rows, overflow, episode = self._rows, self._overflow, self.episode
            self._rows = []
            self.episode = None
        summary = {"kind": "footer", "schema": SCHEMA, "ep": episode, "detail": self.detail,
                   "records": len(rows), "overflow": overflow, "complete": overflow == 0}
        started = self.clock()
        try:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8", newline="\n") as out:
                out.write(json.dumps({"kind": "header", "schema": SCHEMA, "ep": episode,
                                      "max_records": self.max_records, "detail": self.detail}) + "\n")
                for row in rows:
                    out.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
                out.write(json.dumps(summary) + "\n")
                out.flush()
        except (OSError, TypeError, ValueError):
            with self._lock:
                self._rows = rows + self._rows
                self.episode = episode
            raise
        return {**summary, "write_ms": (self.clock() - started) / 1e6, "path": str(path)}


def validate_trace(path: Path) -> dict:
    """Structural and linkage checks, independent of the code that emits rows."""
    problems = []
    try:
        raw = Path(path).read_text("utf-8")
        if not raw.endswith("\n"):
            problems.append("unterminated file")
        rows = [json.loads(line) for line in raw.splitlines()]
    except (OSError, ValueError) as exc:
        return {"complete": False, "problems": [f"unreadable trace: {exc}"]}
    if (len(rows) < 2 or not isinstance(rows[0], dict) or not isinstance(rows[-1], dict)
            or rows[0].get("kind") != "header" or rows[-1].get("kind") != "footer"):
        return {"complete": False, "problems": ["missing header/footer"]}
    header, footer = rows[0], rows[-1]
    if header.get("schema") != SCHEMA or footer.get("schema") != SCHEMA:
        problems.append("unsupported schema")
    if footer.get("records") != len(rows) - 2:
        problems.append("record count mismatch")
    if not footer.get("complete") or footer.get("overflow") != 0:
        problems.append("incomplete buffer")
    ticks, actions, receive_keys = {}, [], set()
    for row in rows[1:-1]:
        if not isinstance(row, dict) or row.get("ep") != header.get("ep"):
            problems.append("invalid row/episode")
            continue
        kind = row.get("kind")
        if kind == "tick":
            key = (row.get("f"), row.get("tick_start_ns"))
            if key in ticks:
                problems.append("duplicate tick")
            ticks[key] = row
            names = ("recv_ns", "tick_start_ns", "decision_start_ns", "decision_end_ns",
                     "send_done_ns", "tick_end_ns")
            times = [row[n] for n in names if row.get(n) is not None]
            if any(not isinstance(t, int) for t in times) or times != sorted(times):
                problems.append("invalid/nonmonotonic timestamps")
            start, end = row.get("tick_start_ns"), row.get("tick_end_ns")
            if not isinstance(start, int) or not isinstance(end, int):
                problems.append("missing tick endpoints")
            elif row.get("total_tick_ms") != (end - start) / 1e6:
                problems.append("tick duration mismatch")
            if row.get("error"):
                problems.append("tick exception")
        elif kind == "action":
            actions.append(row)
        elif kind == "receive":
            key = (row.get("state_seq"), row.get("f"))
            if key in receive_keys:
                problems.append("duplicate STATE")
            receive_keys.add(key)
        else:
            problems.append("unexpected record kind")
    sequences, action_counts = set(), {}
    for row in actions:
        seq = row.get("action_seq")
        if not isinstance(seq, int) or seq in sequences:
            problems.append("invalid/duplicate ACTION sequence")
        sequences.add(seq)
        if row.get("policy_mask_matches_wire") is False or row.get("policy_flags_match_wire") is False:
            problems.append("policy/ACTION mismatch")
        if row.get("tick_start_ns") is not None:
            key = (row.get("f"), row["tick_start_ns"])
            action_counts[key] = action_counts.get(key, 0) + 1
            if key not in ticks:
                problems.append("ACTION without tick")
            elif row.get("owner") != ticks[key].get("owner"):
                problems.append("ACTION/tick owner mismatch")
    receive_by_key = {(row.get("state_seq"), row.get("f")): row.get("recv_ns")
                      for row in rows[1:-1] if isinstance(row, dict) and row.get("kind") == "receive"}
    for key, row in ticks.items():
        if header.get("detail", True) and row.get("actions") != action_counts.get(key, 0):
            problems.append("tick ACTION count mismatch")
        if header.get("detail", True):
            receive_key = (row.get("state_seq"), row.get("f"))
            if (receive_key not in receive_by_key or row.get("recv_ns") is None
                    or receive_by_key[receive_key] != row["recv_ns"]):
                problems.append("tick/receive mismatch")
    covered = sum(row.get("owner") is not None for row in actions)
    coverage = covered / len(actions) if actions else None
    if coverage is not None and coverage < .999:
        problems.append("owner coverage below 99.9%")
    return {"complete": not problems, "problems": sorted(set(problems)), "detail": header.get("detail", True),
            "ticks": len(ticks), "actions": len(actions), "receives": len(receive_keys),
            "owner_coverage": coverage}
