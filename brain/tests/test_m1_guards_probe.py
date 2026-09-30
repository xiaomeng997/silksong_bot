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


def state(frame, hp, dead=False, pdm=1, events=(), gs=4):
    return {"f": frame, "guards": {"hp": hp, "dead": dead, "pdm": pdm},
            "game": {"gs": gs} if gs is not None else None,
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


def test_watch_requires_playing_throughout():
    link = FakeLink()
    w = Watch(link)
    w.reset()
    link.feed(state(20, 1))
    link.feed(state(21, 1))
    assert w.stayed_playing()
    link.feed(state(22, 1, gs=6))  # EXITING_LEVEL: a death respawn or PermaDeath load
    assert not w.stayed_playing()
    w.reset()
    link.feed(state(23, 1, gs=None))  # no GameManager (Save & Quit)
    assert not w.stayed_playing()
    w.reset()
    assert w.stayed_playing()


def test_death_evidence_spans_the_whole_run():
    link = FakeLink()
    w = Watch(link)
    start = w.reset()
    link.feed(state(30, 1, events=[("would_die", {"cause": "death_catch", "blocked": True}),
                                   ("catastrophe", {"cause": "quick", "blocked": True})]))
    assert w.death_evidence(1, start) == []  # blocked events are the guard working
    link.feed(state(31, 1, dead=True))
    w.reset()  # a later case starts: the per-case fields clear, the run-wide evidence stays
    assert not w.dead_seen and w.death_evidence(1, start) == ["hero dead (cState.dead) in some STATE"]


def test_death_evidence_sees_unblocked_would_die_and_mode_change():
    link = FakeLink()
    w = Watch(link)
    start = w.reset()
    link.feed(state(40, 1, events=[("would_die", {"cause": "damage", "blocked": False})]))
    link.feed(state(41, 0, pdm=2, events=[("permadeath_dead", {"hp": 0})]))
    why = w.death_evidence(1, start)
    assert any("unblocked would_die" in x for x in why)
    assert any("permadeathMode 1 -> [2]" in x for x in why)
    assert any(x.startswith("permadeath_dead") for x in why)
    assert w.death_evidence(1, len(w.events)) == ["permadeathMode 1 -> [2]"]  # only the run-wide mode set remains


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
