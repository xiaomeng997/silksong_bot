"""Offline checks of the M1 guards probe helpers (the probe itself needs the running game)."""
from pathlib import Path

import msgpack

from ssbot.ipc.framing import MsgType, encode
from ssbot.probes.m1_guards import Probe, Watch


class FakeLink:
    def __init__(self):
        self.fn = None

    def subscribe_raw(self, fn):
        self.fn = fn

    def feed(self, state: dict, seq: int = 1):
        self.fn(MsgType.STATE, encode(MsgType.STATE, seq, msgpack.packb(state)))


def state(frame, hp, dead=False, pdm=1, events=()):
    return {"f": frame, "guards": {"hp": hp, "dead": dead, "pdm": pdm},
            "ev": [{"k": k, "f": frame, "q": 0, "d": d} for k, d in events]}


def test_watch_collects_events_and_worst_state():
    link = FakeLink()
    w = Watch(link)
    mark = w.reset()
    link.feed(state(10, 2))
    link.feed(state(11, 1, events=[("catastrophe", {"cause": "damage", "blocked": True})]))
    link.feed(state(12, 1, events=[("would_die", {"cause": "death_catch"}), ("hero_dead", {})]))
    assert [e[1] for e in w.since(mark)] == ["catastrophe", "would_die", "hero_dead"]
    assert w.wait(mark, "catastrophe", 0.1, lambda d: d["cause"] == "damage")["blocked"] is True
    assert w.wait(mark, "catastrophe", 0.05, lambda d: d["cause"] == "quick") is None
    assert w.min_hp == 1 and not w.dead_seen and w.pdm_seen == {1}
    link.feed(state(13, 1, dead=True, pdm=2))
    assert w.dead_seen and w.pdm_seen == {1, 2}
    mark = w.reset()
    assert w.since(mark) == [] and w.min_hp is None and not w.dead_seen


def test_slot_files_matches_the_games_naming(tmp_path):
    for name in ("user2.dat", "user2.dat.bak1", "user2.dat.bak3", "user2_1.0.30000.dat", "user2.dat.del",
                 "user.dat", "user3.dat", "user2.dat.new", "shared.dat"):
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / "Restore_Points2").mkdir()
    (tmp_path / "Restore_Points2" / "restoreData1.dat").write_bytes(b"x")
    (tmp_path / "Restore_Points3").mkdir()
    (tmp_path / "Restore_Points3" / "restoreData1.dat").write_bytes(b"x")
    files = Probe.slot_files(tmp_path, 2)
    assert sorted(files) == sorted(["user2.dat", "user2.dat.bak1", "user2.dat.bak3", "user2_1.0.30000.dat", "user2.dat.del",
                                    "user2.dat.new", str(Path("Restore_Points2", "restoreData1.dat"))])
    assert set(Probe.slot_files(tmp_path, 0)) == {"user.dat"}
