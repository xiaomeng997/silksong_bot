"""Real episode-loop integration: observe every frame, preserve masks, stop at facts."""
from types import SimpleNamespace

import pytest

from ssbot.train import episode as ep
from ssbot.train.measurement import MeasurementTrace, validate_trace


class Tap:
    def __init__(self):
        self.reset()
    def reset(self):
        self.wake_frame = self.death_frame = None
        self.lethal = []
    def observe(self, state):
        if self.wake_frame is None and state["f"] >= 2:
            self.wake_frame = 2
    def lethal_frames(self):
        return []


class Link:
    def __init__(self, tap):
        self.frame = 0
        self.measurement = MeasurementTrace()
        self.measurement.start_episode(0)
        self.tap = tap
        self.acts, self.seq = [], 0
        self.state = {"f": 0, "game": {"scene": "Hang_04_boss", "paused": False}}
    def rpc(self, method, **kw):
        return {"seed": kw.get("seed")}
    def act(self, target, mask, hold_frames=0, flags=0):
        self.seq += 1
        self.acts.append((self.frame, target, mask, flags))
        self.measurement.sent(self.seq, [target, mask, hold_frames, 0, flags], self.measurement.clock())
    def wait_state(self, pred=None, newer_than=None, timeout_s=2):
        self.frame += 1
        f = self.frame
        entities = []
        if f >= 4:
            entities = [{"iid": iid, "type_key": "Song Heavy Sentry", "hp": 0 if f >= 6 else 230,
                         "is_dead": f >= 6, "hidden": False} for iid in (1, 2)]
        self.state = {"f": f, "dt": .25, "ents": entities, "ev": [],
                      "hero": {"health": 7, "health_blue": 0}, "act": {"mask": 7},
                      "game": {"scene": "Hang_04_boss", "paused": False},
                      "room": {"battles": [{"wave": 14 if f >= 10 else 13, "started": True}]}}
        self.measurement.received(f, f, self.measurement.clock())
        self.tap.observe(self.state)
        self.measurement.observe_state(self.state)
        return self.state


class Policy:
    def __init__(self, quit_at=None):
        self.planner = SimpleNamespace(measurement_enabled=False)
        self.episode_outcome = None
        self.quit_at = quit_at
        self.calls = []
    def reset(self, rng, enc):
        pass
    def act(self, state, tap):
        self.calls.append(state["f"])
        self.measurement_choice = {"owner": "plan"}
        if self.quit_at == state["f"]:
            self.episode_outcome = ep.QUIT
        return 7


@pytest.mark.parametrize("quit_at", [None, 5])
def test_episode_uses_raw_clock_and_keeps_quits_as_failures(monkeypatch, tmp_path, quit_at):
    monkeypatch.setattr(ep, "wait_settled", lambda link, *a, **kw: link.wait_state())
    monkeypatch.setattr(ep, "_summarise", lambda *a: None)
    tap, policy = Tap(), Policy(quit_at)
    link = Link(tap)
    def intro(ctx):
        while ctx.tap.wake_frame is None:
            ctx.link.wait_state()
    enc = SimpleNamespace(name="Forum_W_w13", scene="Hang_04_boss", savestate="test", timebox_s=120,
                          intro=intro, waves=(1,))
    rec = ep.AttemptRecord(unit=enc.name, stage="t", profile="t", build="t", code_rev=None,
                           config_fp="t", start_kind="t", mode="eval", seed=1)
    ep.run_episode(link, enc, tap, policy, ep.EpisodeConfig(mode="eval", seed=1, facing=None), rec)
    result = link.measurement.window.snapshot()
    assert result["complete"]
    if quit_at is None:
        assert rec.outcome == ep.CLEAR and rec.f_end == 10
        assert result["end_f"] == 6 and result["T"] == 1.25
        assert result["tail_end_reason"] == "next_wave"
        assert max(policy.calls) == 9
    else:
        assert rec.outcome == ep.QUIT and rec.f_end == 5
        assert result["end_reason"] == "episode_quit"
        assert result["T"] == 1.0
    assert all(mask == 7 for _, _, mask, _ in link.acts[:-1])
    assert link.acts[-1][2] == 0
    path = tmp_path / "episode.jsonl"
    link.measurement.write(path)
    assert validate_trace(path)["complete"]
