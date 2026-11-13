"""Task 182, Sol seq354 (#407, #409): the manual-air B2 worker's runtime package.

GC: automatic gen2 out of fights, one unfreeze / collect / freeze before every bout, receipts. The thresholds are checked in a child
process on the real collector (this test process's GC is never changed); the worker loop on the B2 rig.
Safe stop: a stopped B2 bout's game is released and frozen first (episode.b2_safe_stop), before the ledger, the trace, the row and
the cleanup; a failed freeze is a secondary error and the cleanup goes on. The RPCs here are fakes: component evidence only, no game.
"""
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from ssbot.combat import runtime_gc as R
from ssbot.combat.knife_chain_budget import LearningBudget, LearningStop
from ssbot.tools import combat_run as C
from ssbot.train import episode as E
from tests.test_b2_worker_batch import Rig, env, options, quit_rig
from tests.test_b2_worker_audit_priority import REASON

BRAIN = Path(__file__).resolve().parents[1]


# ---- the GC policy

def test_prepare_in_a_child_moves_gen2_out_of_fights_and_every_thread_reads_the_same_thresholds():
    code = r'''
import gc, json, threading
from ssbot.combat import runtime_gc as R
before = list(gc.get_threshold())
prep = R.prepare()
seen = []
reader = threading.Thread(target=lambda: seen.append(list(gc.get_threshold())), name="OracleLink.read")
reader.start(); reader.join()
bouts = [R.bout(episode=0), R.bout(episode=1)]
print(json.dumps({"before": before, "prep": prep, "reader": seen[0], "main": list(gc.get_threshold()), "bouts": bouts,
                  "enabled": gc.isenabled()}))
'''
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = str(BRAIN)
    out = subprocess.run([sys.executable, "-c", code], cwd=BRAIN, env=env, capture_output=True, text=True, timeout=120,
                         stdin=subprocess.DEVNULL)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout.strip().splitlines()[-1])
    want = got["before"][:2] + [R.GEN2_THRESHOLD]
    assert got["prep"]["threshold_before"] == got["before"] and got["prep"]["threshold"] == want
    assert got["reader"] == want and got["main"] == want and got["enabled"] is True
    assert got["prep"]["frozen"] > 0 and got["prep"]["policy"] == "manual_air_precombat_collect_and_freeze"
    for k, b in enumerate(got["bouts"]):
        assert b["episode"] == k and b["threshold"] == want and b["frozen"] > 0 and b["gen_counts"][2] == 0
        assert b["policy"] == "manual_air_bout_unfreeze_collect_freeze"
        assert {"before", "collected", "frozen", "gc_enabled", "ms", "rss_before", "rss_after"} <= set(b)


def test_a_bout_unfreezes_collects_then_freezes(monkeypatch):
    import gc
    calls = []
    monkeypatch.setattr(gc, "unfreeze", lambda: calls.append("unfreeze"))
    monkeypatch.setattr(gc, "collect", lambda: calls.append("collect") or 7)
    monkeypatch.setattr(gc, "freeze", lambda: calls.append("freeze"))
    got = R.bout(episode=3)
    assert calls == ["unfreeze", "collect", "freeze"] and got["collected"] == 7 and got["episode"] == 3


# ---- the worker loop: one collection before each bout

def manual_air_rig(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    made = C.make_policy

    def make(*a, **k):
        p = made(*a, **k)
        prep = p.prepare_learning_batch

        def with_manual_air(args):
            b = prep(args)
            p.chain_native.manual_air = True
            return b
        p.prepare_learning_batch = with_manual_air
        return p
    monkeypatch.setattr(C, "make_policy", make)
    import ssbot.combat.knife_chain_air as air
    monkeypatch.setattr(air, "prepare_runtime_gc", lambda: rig.events.append("gc.prepare") or
                        {"policy": "manual_air_precombat_collect_and_freeze", "threshold": [700, 10, R.GEN2_THRESHOLD]})
    monkeypatch.setattr(R, "bout", lambda episode=None: rig.events.append(f"gc.bout {episode}") or
                        {"policy": "manual_air_bout_unfreeze_collect_freeze", "episode": episode})
    return rig


def rows(tmp_path):
    return [json.loads(line) for line in (tmp_path / "attempts_i0.jsonl").read_text(encoding="utf-8").splitlines()]


def test_two_bouts_each_start_on_their_own_collection_after_the_one_precombat_prepare(tmp_path, monkeypatch):
    rig = manual_air_rig(tmp_path, monkeypatch)
    assert rig.run(episodes=2) == 0
    gc_and_bouts = [e for e in rig.events if e.startswith("gc.") or e == "episode"]
    assert gc_and_bouts == ["gc.prepare", "gc.bout 0", "episode", "gc.bout 1", "episode"]
    assert [r["b2_context"]["gc_bout"]["episode"] for r in rows(tmp_path)] == [0, 1]
    assert json.loads((tmp_path / "b2_gc_ready_i0.json").read_text())["threshold"] == [700, 10, R.GEN2_THRESHOLD]
    assert "time.scale 0.0001" not in rig.events            # a normal bout is never frozen


def test_without_manual_air_nothing_collects_between_bouts(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    monkeypatch.setattr(R, "bout", lambda episode=None: pytest.fail("bout GC outside a manual-air B2 worker"))
    assert rig.run(episodes=2) == 0
    assert all("gc_bout" not in r["b2_context"] for r in rows(tmp_path))


# ---- the safe stop: run_episode's own paths

class FakeLink:
    def __init__(self, calls, scale_reply=lambda s: {"time_scale": s}):
        self.calls, self.closed, self.frame, self.state, self.measurement = calls, False, 5000, {}, None
        self.scale_reply = scale_reply

    def rpc(self, method, **kw):
        self.calls.append(("rpc", method, kw.get("scale")))
        return self.scale_reply(kw.get("scale")) if method == "time.scale" else {}

    def act(self, *a, **k):
        self.calls.append(("act",))


def record(b2=True):
    return E.AttemptRecord(unit="Forum_W_w13", stage="TRAIN", profile="TRAIN", build="test", code_rev="test", config_fp="test",
                           start_kind="savestate", mode="eval", seed=1, f_reset=4000, b2_context={} if b2 else None)


def episode_with(monkeypatch, calls, exc):
    def run(*a):
        raise exc
    monkeypatch.setattr(E, "_run", run)
    monkeypatch.setattr(E, "_summarise", lambda *a: None)
    return SimpleNamespace(stats=lambda: calls.append(("stats",)) or {})


def test_a_learning_stop_inside_run_episode_is_frozen_before_the_release_summaries_and_log_flushes(monkeypatch):
    calls = []
    policy = episode_with(monkeypatch, calls, LearningStop("missing critical application receipt beyond four-frame upper bound"))
    rec = record()
    E.run_episode(FakeLink(calls), None, None, policy, None, rec)
    assert calls[:2] == [("rpc", "input.release", None), ("rpc", "time.scale", E.SAFE_STOP_SCALE)]
    assert calls[2:] == [("act",), ("rpc", "input.release", None), ("stats",)]     # the finally as before, after it
    stop = rec.b2_context["safe_stop"]
    assert rec.outcome == E.HARNESS_FAIL and rec.reason.startswith("LearningStop: missing critical application receipt")
    assert stop["frozen"] is True and stop["where"] == "episode_exception" and stop["frame"] == 5000
    assert stop["time_scale"] == {"requested": E.SAFE_STOP_SCALE, "read_back": E.SAFE_STOP_SCALE}


def test_any_other_exception_of_a_b2_bout_is_frozen_then_propagates(monkeypatch):
    calls = []
    policy = episode_with(monkeypatch, calls, ValueError("policy.act broke"))
    rec = record()
    with pytest.raises(ValueError, match="policy.act broke"):
        E.run_episode(FakeLink(calls), None, None, policy, None, rec)
    assert calls[1] == ("rpc", "time.scale", E.SAFE_STOP_SCALE) and calls.index(("stats",)) > 1
    assert rec.b2_context["safe_stop"]["where"] == "episode_exception_raised"


def test_a_bout_outside_b2_is_never_frozen(monkeypatch):
    calls = []
    policy = episode_with(monkeypatch, calls, LearningStop("x"))
    rec = record(b2=False)
    E.run_episode(FakeLink(calls), None, None, policy, None, rec)
    assert ("rpc", "time.scale", E.SAFE_STOP_SCALE) not in calls and rec.outcome == E.HARNESS_FAIL


@pytest.mark.parametrize("reply,why", [(lambda s: {"time_scale": 1.0}, "read back 1.0"), (lambda s: None, "no reply"),
                                       ("raise", "timeout")])
def test_a_failed_freeze_is_recorded_and_never_changes_the_outcome(monkeypatch, reply, why):
    calls = []
    policy = episode_with(monkeypatch, calls, LearningStop("x"))
    rec = record()
    link = FakeLink(calls)
    if reply == "raise":
        def broken(method, **kw):
            calls.append(("rpc", method, kw.get("scale")))
            if method == "time.scale":
                raise TimeoutError("time.scale")
            return {}
        link.rpc = broken
    else:
        link.scale_reply = reply
    E.run_episode(link, None, None, policy, None, rec)
    assert rec.b2_context["safe_stop"]["frozen"] is False, why
    assert rec.outcome == E.HARNESS_FAIL and rec.reason == "LearningStop: x" and ("stats",) in calls


# ---- the safe stop: the worker

def returned_stop(rig, monkeypatch, *, raise_after=False):
    """run_episode returns the way the real one does after a LearningStop: HARNESS_FAIL with the chain's stop set."""
    original = E.run_episode

    def wrapped(link, enc, tap, pol, cfg, rec):
        original(link, enc, tap, pol, cfg, rec)
        pol.chain_native.learning_stop = REASON
        rec.outcome, rec.reason = E.HARNESS_FAIL, "LearningStop: " + REASON
    monkeypatch.setattr(E, "run_episode", wrapped)
    finish = LearningBudget.finish_bout

    def finish_bout(self, **kw):
        rig.events.append("ledger.finish_bout")
        return finish(self, **kw)
    monkeypatch.setattr(LearningBudget, "finish_bout", finish_bout)


def test_a_returned_stop_is_frozen_once_before_the_ledger_and_the_row(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    returned_stop(rig, monkeypatch)
    assert rig.run(episodes=2) == 0
    ev = rig.events
    assert ev.count("time.scale 0.0001") == 1 and ev.count("episode") == 1
    assert ev.index("episode") < ev.index("input.release") < ev.index("time.scale 0.0001") < ev.index("ledger.finish_bout")
    row = rows(tmp_path)[0]
    assert row["b2_safe_stop"]["frozen"] is True and row["b2_safe_stop"]["where"] == "episode_return"
    assert row["b2_learning_stop"] == REASON and "secondary_errors" not in row
    cleanup = rig.receipts()[0]
    assert cleanup["primary_error"] == "LearningStop: " + REASON and cleanup["resources"]["time_scale"] == "kept_frozen"
    assert len(list(tmp_path.glob("b2_safe_stop_i0_*.json"))) == 1 and rig.links[0].closed


@pytest.mark.parametrize("fault", ["raise", "unfrozen"])
def test_a_failed_freeze_keeps_the_primary_and_the_cleanup(tmp_path, monkeypatch, fault):
    rig = Rig(tmp_path, monkeypatch)
    rig.freeze_fault = fault
    returned_stop(rig, monkeypatch)
    assert rig.run(episodes=2) == 0
    row = rows(tmp_path)[0]
    assert row["b2_safe_stop"]["frozen"] is False and row["b2_learning_stop"] == REASON
    assert [e["origin"] for e in row["secondary_errors"]] == ["safe_stop"]
    cleanup = rig.receipts()[0]
    assert cleanup["primary_error"] == "LearningStop: " + REASON and cleanup["primary_error_origin"] == "chain.learning_stop"
    assert any(e["origin"] == "safe_stop" for e in cleanup["secondary_errors"])
    assert cleanup["resources"]["time_scale"] == "not_required" and cleanup["resources"]["ipc"] == "pass"
    assert "after_episode" in rig.events             # an unverified freeze keeps the old way back


def test_a_frozen_stop_skips_the_way_back_that_would_resume_the_fight(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    returned_stop(rig, monkeypatch)
    assert rig.run(episodes=2) == 0
    assert "after_episode" not in rig.events and rig.events.count("time.scale 0.0001") == 1


def test_an_episode_exception_is_frozen_before_the_aborted_bout_is_persisted(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch, fault="episode")
    persist = C._persist_aborted_episode
    monkeypatch.setattr(C, "_persist_aborted_episode", lambda *a, **k: rig.events.append("persist") or persist(*a, **k))
    with pytest.raises(RuntimeError, match="episode failed"):
        rig.run(episodes=2)
    ev = rig.events
    assert ev.index("episode") < ev.index("time.scale 0.0001") < ev.index("persist") and ev.count("time.scale 0.0001") == 1
    assert rig.receipts()[0]["primary_error"] == "RuntimeError: episode failed"
    assert rig.receipts()[0]["resources"]["time_scale"] == "kept_frozen"


def test_normal_bouts_and_a_real_q1_exit_are_never_frozen(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    assert rig.run(episodes=2) == 0 and "time.scale 0.0001" not in rig.events
    q = quit_rig(tmp_path / "q1", monkeypatch)
    (tmp_path / "q1").mkdir(exist_ok=True)
    assert q.run(episodes=2) == 0 and "time.scale 0.0001" not in q.events
    assert not list((tmp_path / "q1").glob("b2_safe_stop_i0_*.json"))


def test_a_continuous_plan_stop_is_frozen_before_the_worker_raises(tmp_path, monkeypatch):
    from tests.test_b2_continuous_plan import outcome, plan_rig
    rig, plan, kw = plan_rig(tmp_path, monkeypatch, [outcome("STUCK", "timebox")])
    with pytest.raises(LearningStop, match="continuous plan"):
        rig.run(**kw)
    assert rig.events.count("time.scale 0.0001") == 1 and rig.events.count("episode") == 1
    assert json.loads(next(tmp_path.glob("b2_safe_stop_i0_*.json")).read_text())["where"] == "continuous_plan_stop"


def test_the_cleanup_never_sets_a_frozen_game_back_to_1x(tmp_path, monkeypatch):
    env(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(C, "set_time_scale", lambda *a, **k: calls.append(a))
    link = SimpleNamespace(closed=False, close=lambda: None)
    a = options(tmp_path, time_scale=2.0)
    frozen = C._close_worker(a, link=link, recorder=None, out=None, diagnostics=None, policy=None, stage="episodes",
                             primary_error="LearningStop: x", frozen=True)
    assert frozen["resources"]["time_scale"] == "kept_frozen" and calls == []
    C._close_worker(a, link=link, recorder=None, out=None, diagnostics=None, policy=None, stage="episodes",
                    primary_error="LearningStop: x")
    assert len(calls) == 1 and calls[0][1] == 1.
