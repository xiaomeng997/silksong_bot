"""Task 182 seq 308: the Forum decision log stays in memory through a fight and reaches its file at the fight's boundaries: same
rows, same order, same bytes; a failed write neither loses nor repeats a line; the held text is bounded."""
import json
from collections import deque
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from ssbot.tools import combat_run as C
from ssbot.train import planner_policy as PP
from ssbot.train.forum_planner_policy import ForumPlannerPolicy
from ssbot.train.planner_policy import PlannerPolicy


class Old(PlannerPolicy):
    """The file path as it was before seq 308."""

    def flush_log(self):
        if self._log_buf and self.log_path is not None:
            with self.log_path.open("a", encoding="utf-8") as fh:
                for x in self._log_buf:
                    fh.write(json.dumps(x) + "\n")
        self._log_buf.clear()


def bare(cls, path):
    p = object.__new__(cls)
    p.log_path = path
    p._log_buf = []
    p.ring = deque(maxlen=PP.LOG_BEFORE)
    p.log_after = 0
    p.sc = NS(pq=NS(pressing=False))
    return p


def row(f, **kw):
    return {"ep": 0, "f": f, "hero": [1.5, 2.25], "plan": "é-free ascii", "alts": [["x", 1]], "nan": float("nan"), **kw}


SCRIPT = [(f, f in (120, 124, 300, 301, 500)) for f in range(700)]


def play(p, script=SCRIPT):
    for f, event in script:
        p._emit(row(f), event)


def frames(path):
    return [json.loads(x)["f"] for x in path.read_text(encoding="utf-8").splitlines()]


def forum(tmp_path, name="decisions.jsonl"):
    return bare(ForumPlannerPolicy, tmp_path / name)


def no_files(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("no decision-log file I/O in the fight")
    monkeypatch.setattr(Path, "open", boom)
    import builtins
    monkeypatch.setattr(builtins, "open", boom)


# ---- the fight

def test_the_fight_writes_no_file(tmp_path, monkeypatch):
    p = forum(tmp_path)
    no_files(monkeypatch)
    play(p)
    monkeypatch.undo()
    assert not p.log_path.exists() and p._log_held and p._log_buf == []
    assert p._log_held_bytes == sum(len(x) for x in p._log_held)
    assert all(isinstance(x, bytes) for x in p._log_held)


def test_the_file_after_the_bout_is_byte_for_byte_the_old_one(tmp_path):
    old = bare(Old, tmp_path / "old.jsonl")
    new = forum(tmp_path, "new.jsonl")
    play(old)
    play(new)
    assert not new.log_path.exists()
    new.flush_log()
    assert new.log_path.read_bytes() == old.log_path.read_bytes() and new.log_path.read_bytes()
    assert new._log_held_bytes == 0 and not new._log_held


def test_the_ring_before_and_after_an_event_is_unchanged(tmp_path):
    p = forum(tmp_path)
    for f in range(200):
        p._emit(row(f), f == 150)
    p.flush_log()
    assert frames(p.log_path) == list(range(61, 151)) + list(range(151, 161))


def test_every_tick_when_log_all(tmp_path, monkeypatch):
    monkeypatch.setattr(PP, "LOG_ALL", True)
    p = forum(tmp_path)
    no_files(monkeypatch)
    for f in range(40):
        p._emit(row(f), False)
    monkeypatch.undo()
    p.flush_log()
    assert frames(p.log_path) == list(range(40))


def test_while_the_pause_loop_presses_the_rows_stay_rows(tmp_path):
    p = forum(tmp_path)
    p.sc.pq.pressing = True
    p._emit(row(1), True)
    assert p._log_buf and not p._log_held
    p.sc.pq.pressing = False
    p._emit(row(2), True)
    assert not p._log_buf and len(p._log_held) == 1
    p.flush_log()
    assert frames(p.log_path) == [1, 2]


def test_the_pause_loops_rows_are_not_lost_when_the_fight_ends_in_it(tmp_path):
    p = forum(tmp_path)
    p._emit(row(1), True)
    p.sc.pq.pressing = True
    p._emit(row(2), True)
    p.flush_log()
    assert frames(p.log_path) == [1, 2] and not p._log_buf


def test_a_policy_without_a_log_holds_nothing(tmp_path):
    p = bare(ForumPlannerPolicy, None)
    p._emit(row(1), True)
    p.flush_log()
    assert not p._log_held and p._log_buf == []


def test_other_policies_still_write_through(tmp_path):
    p = bare(PlannerPolicy, tmp_path / "base.jsonl")
    p._emit(row(1), True)
    assert frames(p.log_path) == [1] and not p._log_held


# ---- the bound

def test_past_the_bound_the_tick_writes_and_nothing_is_dropped(tmp_path, monkeypatch):
    monkeypatch.setattr(PP, "LOG_HELD_MAX", 400)
    p = forum(tmp_path)
    for f in range(20):
        p._emit(row(f), True)
        assert p._log_held_bytes <= 400
    assert p.log_path.exists()
    p.flush_log()
    assert frames(p.log_path) == list(range(20))


def test_under_the_bound_the_tick_does_not_write(tmp_path, monkeypatch):
    monkeypatch.setattr(PP, "LOG_HELD_MAX", 1 << 30)
    p = forum(tmp_path)
    for f in range(20):
        p._emit(row(f), True)
    assert not p.log_path.exists()


# ---- the write

def test_a_failed_open_keeps_everything_for_the_next_call(tmp_path, monkeypatch):
    p = forum(tmp_path)
    play(p)
    held = list(p._log_held)

    def boom(*a, **k):
        raise OSError(28, "no space")
    monkeypatch.setattr(Path, "open", boom)
    with pytest.raises(OSError):
        p.flush_log()
    monkeypatch.undo()
    assert list(p._log_held) == held
    p.flush_log()
    old = bare(Old, tmp_path / "old.jsonl")
    play(old)
    assert p.log_path.read_bytes() == old.log_path.read_bytes()


class Sink:
    """A raw file whose write() takes a part of the data, or fails once at a chosen call."""

    def __init__(self, take=None, fail_at=None):
        self.data, self.take, self.fail_at, self.calls = bytearray(), take, fail_at, 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def write(self, b):
        self.calls += 1
        if self.fail_at == self.calls:
            self.fail_at = None
            raise OSError(5, "write failed")
        n = len(b) if self.take is None else min(self.take, len(b))
        self.data += b[:n]
        return n


def expected(tmp_path):
    old = bare(Old, tmp_path / "ref.jsonl")
    play(old)
    return old.log_path.read_bytes()


def test_a_short_write_goes_on_from_where_it_stopped(tmp_path, monkeypatch):
    p = forum(tmp_path)
    play(p)
    sink = Sink(take=37)
    monkeypatch.setattr(Path, "open", lambda *a, **k: sink)
    p.flush_log()
    monkeypatch.undo()
    assert bytes(sink.data) == expected(tmp_path) and p._log_held_bytes == 0 and not p._log_held


def test_a_write_error_midway_neither_loses_nor_repeats_a_line(tmp_path, monkeypatch):
    want = expected(tmp_path)
    p = forum(tmp_path)
    play(p)
    sink = Sink(fail_at=3)
    monkeypatch.setattr(Path, "open", lambda *a, **k: sink)
    with pytest.raises(OSError):
        p.flush_log()
    assert 0 < len(sink.data) < len(want) and p._log_held
    p.flush_log()
    monkeypatch.undo()
    assert bytes(sink.data) == want and p._log_held_bytes == 0


def test_a_row_that_cannot_be_written_stays_and_raises(tmp_path):
    p = forum(tmp_path)
    p._emit(row(1), True)
    with pytest.raises(TypeError):
        p._emit(row(2, bad={1, 2}), True)
    assert len(p._log_buf) == 1 and len(p._log_held) == 1


def test_flushing_twice_writes_once(tmp_path):
    p = forum(tmp_path)
    play(p)
    p.flush_log()
    before = p.log_path.read_bytes()
    p.flush_log()
    assert p.log_path.read_bytes() == before


# ---- the fight's boundaries

def test_an_aborted_episode_writes_what_was_held_then_the_ring(tmp_path):
    p = forum(tmp_path)
    for f in range(200):
        p._emit(row(f), f == 150)
    n = p.log_abort_ring()
    assert n == 39 and not p.ring                                     # 161 .. 199
    assert frames(p.log_path) == list(range(61, 200))


def test_the_bout_end_reset_and_worker_close_all_write():
    assert "flush_log" in ForumPlannerPolicy.stats.__code__.co_names
    assert "flush_log" in ForumPlannerPolicy.reset.__code__.co_names
    assert "flush_log" in C._close_worker.__code__.co_consts


def test_no_thread_is_involved(tmp_path, monkeypatch):
    import threading
    def boom(*a, **k):
        raise AssertionError("no thread")
    monkeypatch.setattr(threading.Thread, "start", boom)
    p = forum(tmp_path)
    play(p)
    p.flush_log()
    assert p.log_path.exists()


def test_the_forum_policy_holds_and_the_base_does_not():
    assert ForumPlannerPolicy.LOG_AT_BOUT_END is True and PlannerPolicy.LOG_AT_BOUT_END is False
