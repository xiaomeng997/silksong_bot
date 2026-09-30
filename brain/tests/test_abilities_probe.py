"""Offline checks of the ability probe's safety net (the probe itself needs the running game): save suppression goes
back off only once the grant is verifiably undone, whatever interrupts the probe between the grant and the undo."""
import sys

import pytest

from ssbot.ipc.oracle_link import OracleError
from ssbot.probes import abilities as P

NAMES = ["facingRight", "onGround"]
SLOT = {"index": 0, "type": "Skill", "binding": "Neutral", "locked": False, "tool": None}
BEFORE = {"flags": {"hasDash": False}, "crest": "Hunter", "slots": [SLOT],
          "bindings": {"neutral": None, "up": None, "down": None}, "config": {}, "silk": 0, "silk_max": 9,
          "silk_skill_cost": 4, "tools": [{"name": "Rosary Magnet"}],
          "skills": [{"tool": "Silk Spear", "unlocked": False}], "sets": {"movement": False, "combat": False, "all": False}}
GRANTED = {**BEFORE, "flags": {"hasDash": True}, "slots": [{**SLOT, "tool": "Silk Spear"}],
           "bindings": {"neutral": "Silk Spear", "up": None, "down": None},
           "skills": [{"tool": "Silk Spear", "unlocked": True}],
           "sets": {"movement": True, "combat": True, "all": True}}


class FakeOracle:
    """Just enough of an instance for the probe up to its first exercise, which never finds Hornet on the ground
    (TimeoutError), or a savestate.load that fails."""

    def __init__(self, load_fails: bool = False):
        self.hello = {"rpcs": ["abilities.grant", "abilities.list", "schema.cstate", "guards.set", "savestate.save"]}
        self.pd = BEFORE  # what PlayerData holds now
        self.saved: dict[str, dict] = {}
        self.suppression = False
        self.suppression_log: list[bool] = []
        self.load_fails = load_fails
        self.frame = 10
        self.state = {"f": 10, "game": {"gs": 4, "paused": False}, "pause": {"bench": False},
                      "hero": {"hero_accepting_input": True, "cstate": [0], "can": {}, "tools": []}}  # airborne
        self.closed = False

    def wait_state(self, pred=lambda s: True, timeout_s=10.0, newer_than=None):
        if pred(self.state):
            return self.state
        raise TimeoutError("fake: condition not met")

    def rpc(self, name, /, timeout_s=10.0, **args):
        if name == "schema.cstate":
            return {"bools": NAMES}
        if name == "abilities.list":
            return self.pd
        if name == "savestate.save":
            self.saved[args["state"]] = self.pd
            return {}
        if name == "savestate.load":
            if self.load_fails:
                raise TimeoutError("fake: load timed out")
            self.pd = self.saved[args["state"]]
            return {}
        if name == "guards.get":
            return {"save_suppression": self.suppression}
        if name == "guards.set":
            self.suppression = args["save_suppression"]
            self.suppression_log.append(self.suppression)
            return {"save_suppression": self.suppression}
        if name == "abilities.grant":
            if "No Such Tool" in (args.get("tools") or ()):
                raise OracleError("unknown tool 'No Such Tool'")
            changed = [] if self.pd is GRANTED else ["hasDash (Swift Step)"]
            self.pd = GRANTED
            return {**GRANTED, "changed": changed, "unplaced": [], "requested": ["Silk Spear"],
                    "bindings_cached": GRANTED["bindings"]}
        if name == "input.release":
            return {}
        raise AssertionError(f"unexpected rpc {name}")

    def close(self):
        self.closed = True


def run_probe(monkeypatch, fake, *argv):
    monkeypatch.setattr(P, "OracleLink", lambda instance: fake)
    monkeypatch.setattr(P, "failures", [])
    monkeypatch.setattr(sys, "argv", ["abilities", *argv])
    with pytest.raises(TimeoutError):
        P.main()
    assert fake.closed


def test_interrupted_probe_undoes_the_grant_before_suppression_goes_off(monkeypatch, capsys):
    fake = FakeOracle()
    run_probe(monkeypatch, fake, "--set", "combat")
    assert fake.pd is BEFORE and fake.suppression_log == [True, False]
    assert "PASS grant undone" in capsys.readouterr().out


def test_suppression_stays_on_when_the_undo_fails(monkeypatch, capsys):
    fake = FakeOracle(load_fails=True)
    run_probe(monkeypatch, fake, "--set", "combat")
    assert fake.pd is GRANTED and fake.suppression_log == [True] and fake.suppression is True
    out = capsys.readouterr().out
    assert "undo failed" in out and "save suppression is left ON" in out


def test_keep_leaves_the_grant_and_suppression(monkeypatch, capsys):
    fake = FakeOracle()
    run_probe(monkeypatch, fake, "--set", "combat", "--keep")
    assert fake.pd is GRANTED and fake.suppression_log == [True]
    assert "--keep: save suppression stays on" in capsys.readouterr().out
