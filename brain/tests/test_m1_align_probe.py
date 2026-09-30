"""Offline checks of the M1 alignment probe's driving (the probe itself needs the running game)."""
from ssbot.ipc.framing import mask, names
from ssbot.probes.m1_align import Pattern, drive


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
