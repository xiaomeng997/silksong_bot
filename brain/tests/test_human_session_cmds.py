"""human_session's command file: a load runs only in gameplay, with save suppression first; the file is consumed."""
import ssbot.tools.human_session as hs


class _Link:
    def __init__(self, state):
        self.state = state
        self.calls = []

    def rpc(self, method, **kw):
        self.calls.append((method, kw))
        return {}


def _gameplay_state():
    # the fields ssbot.probes.common.in_gameplay reads
    return {"f": 100, "game": {"state": "PLAYING", "scene": "Hang_04", "menu": None, "hero_accepting_input": True,
                               "transitioning": False}, "hero": {"pos": [0, 0]}}


def test_load_in_gameplay_sets_save_suppression_then_loads(tmp_path, monkeypatch):
    monkeypatch.setattr(hs, "CMD_FILE", tmp_path / "cmd.txt")
    monkeypatch.setattr(hs, "in_gameplay", lambda s: True)
    hs.CMD_FILE.write_text("load fo_A\n", encoding="utf-8")
    link, log = _Link(_gameplay_state()), []
    hs.run_commands(link, log)
    assert [c[0] for c in link.calls] == ["guards.set", "savestate.load"]
    assert link.calls[0][1] == {"save_suppression": True}
    assert link.calls[1][1]["name"] == "fo_A"
    assert log[0]["result"] == "loaded" and log[0]["frame"] == 100
    assert not hs.CMD_FILE.exists()


def test_load_outside_gameplay_is_refused_and_unknown_commands_are_logged(tmp_path, monkeypatch):
    monkeypatch.setattr(hs, "CMD_FILE", tmp_path / "cmd.txt")
    monkeypatch.setattr(hs, "in_gameplay", lambda s: False)
    hs.CMD_FILE.write_text("load fo_A\nreset everything\n", encoding="utf-8")
    link, log = _Link({"f": 5}), []
    hs.run_commands(link, log)
    assert link.calls == []
    assert log[0]["result"].startswith("refused") and log[1]["result"] == "unknown command"
    assert not hs.CMD_FILE.exists()
