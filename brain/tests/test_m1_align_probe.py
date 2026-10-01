"""Offline checks of the M1 alignment probe: its driving, and that the frame marker goes on for the gate run (the
vision mask's marker, read in the capture path) and off again at the end, also after an error (the probe itself needs
the running game)."""
import sys
from pathlib import Path

import pytest

from ssbot.ipc.framing import mask, names
from ssbot.ipc.oracle_link import OracleError
from ssbot.probes import m1_align
from ssbot.probes.m1_align import Pattern, drive
from ssbot.vision import mask as vmask


def test_pattern_changes_speed_and_stays_near_the_start():
    p = Pattern(seed=1, span=6.0)
    x, v = 100.0, 0.0
    held = []
    for _ in range(3600):
        m = p.next(x)
        held.append(m)
        v = 8.25 / 60 * ((m & mask("right")) > 0) - 8.25 / 60 * ((m & mask("left")) > 0)
        x += v
        assert abs(x - 100.0) < 6.0 + 1.0  # steered back once past the span
    moves = [(bool(m & mask("right")), bool(m & mask("left"))) for m in held]
    changes = sum(a != b for a, b in zip(moves, moves[1:]))
    assert changes > 60                       # ~1 speed change per 40 frames: plenty of decisive windows
    assert not any(r and lf for r, lf in moves)  # never both directions at once
    assert any(m & mask("jump") for m in held) and any(m & mask("dash") for m in held)
    assert Pattern(seed=1).next(0.0) == Pattern(seed=1).next(0.0)  # reproducible


class FakeLink:
    def __init__(self, states):
        self.states = list(states)
        self.acts = []

    def wait_state(self, pred=None, timeout_s=10.0, newer_than=None):
        return self.states.pop(0)

    def act(self, target, buttons, hold_frames=0, ack_seq=0):
        self.acts.append((target, buttons, hold_frames))


def st(f, scene="Bonetown", gs=4, x=10.0):
    return {"f": f, "game": {"gs": gs, "scene": scene}, "hero": {"pos": [x, 5.0, 0.0]}}


def test_drive_sends_continuous_control_every_frame_and_stops_on_a_scene_change():
    link = FakeLink([st(100), st(101), st(102), st(103, scene="Bonetown_02"), st(104)])
    why = drive(link, 60.0, Pattern(seed=2), progress=lambda s: None)
    assert why == "scene changed to Bonetown_02"
    assert [a[0] for a in link.acts] == [103, 104] and all(a[2] == 0 for a in link.acts)
    assert all(set(names(a[1])) <= {"left", "right", "jump", "dash"} for a in link.acts)
    link = FakeLink([st(100), st(101), st(102, gs=5)])
    assert drive(link, 60.0, Pattern(seed=2), progress=lambda s: None) == "left PLAYING (gs 5)"


# ---- the frame marker: on for the gate run, off at the end, also after an error ------------------------------------

class GateLink:
    """OracleLink for main(): Hornet standing in Bonetown, 1280x720; frame.marker optionally refused."""

    def __init__(self, refuse: bool = False):
        self.hello = {"plugin": "0.1.0", "game": "1.0.30000", "instance": "0", "qpc_freq": 10_000_000,
                      "rpcs": ["ping", "input.release", "frame.marker"]}
        self.refuse = refuse
        self.marker = False
        self.calls = []
        self.closed = False

    def wait_state(self, pred=lambda s: True, timeout_s=10.0, newer_than=None):
        mk = {"drawn": True, "cell": 3, "rect": [float(v) for v in vmask.marker_rect(1280, 720)]}
        s = {"f": 100, "game": {"gs": 4, "scene": "Bonetown"}, "pause": {"bench": False},
             "hero": {"pos": [10.0, 5.0, 0.0], "hero_accepting_input": True}, "cam": {"screen": [1280.0, 720.0]},
             "mk": mk if self.marker else None}
        if not pred(s):
            raise TimeoutError("condition not met")
        return s

    def rpc(self, name, timeout_s=10.0, **args):
        self.calls.append((name, args))
        if name == "frame.marker":
            if args["on"] and self.refuse:
                raise OracleError("probe tools are disabled in profile SHADOW")
            self.marker = args["on"]
        return {"on": self.marker}

    def close(self):
        self.closed = True


class FakeRecorder:
    def __init__(self, link, out_dir, **kw):
        self.path = Path(out_dir)
        self.states, self.dropped, self.closed = 0, {"state": 0}, False

    def start(self):
        return self

    def close(self):
        self.closed = True
        return {"drops": {}, "error": None}


class BrokenVideo:
    made = []

    def __init__(self, *a, **kw):
        BrokenVideo.made.append(kw)

    def start(self):
        raise RuntimeError("capture start: window gone")


def _gate(monkeypatch, tmp_path, link):
    monkeypatch.setattr(m1_align, "OracleLink", lambda instance: link)
    monkeypatch.setattr(m1_align, "instance_window", lambda instance: 0x1234)
    monkeypatch.setattr(m1_align, "Recorder", FakeRecorder)
    monkeypatch.setattr(m1_align, "VideoRecorder", BrokenVideo)
    monkeypatch.setattr(m1_align.time, "sleep", lambda s: None)
    monkeypatch.setattr(sys, "argv", ["m1_align", "--out", str(tmp_path), "--no-load"])


def test_marker_goes_off_after_an_error(monkeypatch, tmp_path):
    link = GateLink()
    _gate(monkeypatch, tmp_path, link)
    with pytest.raises(RuntimeError, match="window gone"):
        m1_align.main()
    names = [(n, a.get("on")) for n, a in link.calls]
    assert names == [("frame.marker", True), ("input.release", None), ("frame.marker", False)]
    assert link.calls[0][1] == {"on": True, "corner": "tr"}        # the oracle's default cell: the mask's
    assert BrokenVideo.made[-1]["marker"] is True                    # read in the capture path, masked
    assert callable(BrokenVideo.made[-1]["states"])                  # and guarded against STATE mk
    assert link.closed and not link.marker


def test_refused_marker_fails_the_gate(monkeypatch, tmp_path, capsys):
    link = GateLink(refuse=True)
    _gate(monkeypatch, tmp_path, link)
    assert m1_align.main() == 1
    assert "frame marker not on" in capsys.readouterr().out
    assert [(n, a["on"]) for n, a in link.calls] == [("frame.marker", True), ("frame.marker", False)] and link.closed
