"""Warm the actual optional reader cache, never a tracker or its zones."""
from functools import lru_cache
from types import SimpleNamespace

from ssbot.combat import forum_v2
from ssbot.tools import aim_zones


def test_warmup_uses_the_same_reader_cache_as_pending_checks(monkeypatch):
    loads = []
    marker = object()

    @lru_cache(maxsize=1)
    def readers():
        loads.append(1)
        return {"example": marker}

    monkeypatch.setattr(aim_zones, "readers", readers)
    tracker = SimpleNamespace(now={})
    forum_v2.warm_aim_tables()
    assert forum_v2.pending_aims(tracker) == []
    assert forum_v2.pending_aims(tracker) == []
    assert loads == [1]
    assert readers()["example"] is marker
    assert tracker.now == {}


def test_failed_optional_load_is_still_retried_by_the_live_path(monkeypatch):
    calls = []

    @lru_cache(maxsize=1)
    def readers():
        calls.append(1)
        if len(calls) == 1:
            raise OSError("optional table temporarily unreadable")
        return {}

    monkeypatch.setattr(aim_zones, "readers", readers)
    forum_v2.warm_aim_tables()
    assert forum_v2.pending_aims(SimpleNamespace(now={})) == []
    assert calls == [1, 1]
