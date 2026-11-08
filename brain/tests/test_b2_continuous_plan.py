"""Task 182 seq 288: one worker through an explicit bounded plan of bouts (combat_run --continuous-plan): the plan's strict
count, order, arm and seeds in the persisted ledger; a clear or a completed real Q1 exit lets the next bout start; any other end
stops with a failing exit, the row written and the worker's cleanup done; without a plan the first-smoke limits stand. Fake
IPC / Recorder, real persisted budget, no game (the rig of test_b2_worker_batch)."""
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from ssbot.combat import knife_chain_budget as B
from ssbot.combat.knife_chain_budget import (LearningBudget, LearningStop, continuous_plan, continuous_stop_reason,
                                             execution_conditions, preflight_options)
from ssbot.tools import combat_run as C
from tests.test_b2_worker_batch import Rig, env, options


def write_plan(path, n=6, **over):
    plan = dict(schema=1, kind=B.CONTINUOUS_PLAN_KIND, batch="test-batch", arm="B", attempts=n, seeds=[1000 + 7 * i for i in range(n)],
                authorization="the person's words", source="unit test")
    plan.update(over)
    path.write_text(json.dumps(plan), encoding="utf-8")
    return plan


def planned(tmp_path, monkeypatch, n=6, **over):
    env(monkeypatch, tmp_path)
    p = tmp_path / "plan.json"
    plan = write_plan(p, n, **over)
    return p, plan, options(tmp_path, episodes=n, continuous_plan=str(p))


Q1_ROW = dict(outcome="QUIT", reason="QUIT: Q1: remaining HP 2 <= 2; after a hit: pause in the post-hit window", min_hp=2,
              policy=dict(remaining_hp_quit=2, real_quit=dict(armed=True, main_menu=True, outcome="QUIT", steps=[[.1, "done", ""]])))


# ---- no plan: nothing changes

def test_without_a_plan_the_first_smoke_limits_stand(tmp_path, monkeypatch):
    env(monkeypatch, tmp_path)
    with pytest.raises(LearningStop, match="1..4"):
        preflight_options(options(tmp_path, episodes=5))
    preflight_options(options(tmp_path, episodes=4))
    assert continuous_plan(options(tmp_path)) is None
    c = execution_conditions(options(tmp_path))
    assert c["smoke_limit"] == {"total": 8, "per_arm": 4} and "continuous" not in c


def test_without_a_plan_the_ledger_limits_stand(tmp_path):
    b = LearningBudget(tmp_path / "b.json", batch="b", revision="r", worker="i0")
    b.bind_execution({"profile": "no plan"})
    for i in range(4):
        b.begin_attempt(episode=i, arm="B", seed=i)
    with pytest.raises(LearningStop, match="upper limit"):
        b.begin_attempt(episode=4, arm="B", seed=4)


# ---- the plan file

@pytest.mark.parametrize("over", [dict(schema=2), dict(kind="other"), dict(batch="another"), dict(arm="A"), dict(arm="C"),
                                  dict(attempts=5), dict(attempts=5, seeds=[1, 2, 3, 4, 5, 5]),
                                  dict(attempts=B.CONTINUOUS_MAX_ATTEMPTS + 1, seeds=list(range(B.CONTINUOUS_MAX_ATTEMPTS + 1))),
                                  dict(seeds=[1, 1, 2, 3, 4, 5]),
                                  dict(seeds=[1, 2, 3, 4, 5, "6"]), dict(seeds=[1, 2, 3, 4, 5, -6]), dict(seeds=[1, 2, 3, 4, 5, 6.0]),
                                  dict(seeds=[1, 2, 3, 4, 5, True]), dict(attempts=True, seeds=[1]), dict(authorization=""),
                                  dict(authorization="  "), dict(authorization=None)],
                         ids=["schema", "kind", "batch", "arm", "arm_unknown", "count", "count_with_a_repeat", "over_cap", "duplicate", "str_seed", "negative", "float",
                              "bool", "bool_count", "no_auth", "blank_auth", "null_auth"])
def test_a_bad_plan_is_refused(tmp_path, monkeypatch, over):
    p, plan, a = planned(tmp_path, monkeypatch, **over)
    with pytest.raises(LearningStop, match="continuous plan invalid"):
        continuous_plan(a)
    with pytest.raises(LearningStop, match="continuous plan invalid"):
        preflight_options(a)


def test_a_missing_or_unreadable_plan_is_refused(tmp_path, monkeypatch):
    env(monkeypatch, tmp_path)
    with pytest.raises(LearningStop, match="continuous plan invalid"):
        continuous_plan(options(tmp_path, continuous_plan=str(tmp_path / "none.json")))
    (tmp_path / "bad.json").write_text("{", encoding="utf-8")
    with pytest.raises(LearningStop, match="continuous plan invalid"):
        continuous_plan(options(tmp_path, continuous_plan=str(tmp_path / "bad.json")))


def test_a_plan_is_not_taken_together_with_a_crossover_schedule(tmp_path, monkeypatch):
    p, plan, a = planned(tmp_path, monkeypatch)
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_SCHEDULE", str(tmp_path / "schedule.json"))
    with pytest.raises(LearningStop, match="crossover"):
        continuous_plan(a)


def test_the_episodes_must_be_exactly_the_plans(tmp_path, monkeypatch):
    p, plan, a = planned(tmp_path, monkeypatch, n=6)
    preflight_options(a)
    for wrong in (5, 7, 1):
        a2 = options(tmp_path, episodes=wrong, continuous_plan=str(p))
        with pytest.raises(LearningStop, match="must equal"):
            preflight_options(a2)


def test_a_plan_runs_on_one_instance(tmp_path, monkeypatch):
    p, plan, a = planned(tmp_path, monkeypatch, n=6)
    preflight_options(options(tmp_path, episodes=6, continuous_plan=str(p), instances="0"))
    with pytest.raises(LearningStop, match="invalid instances"):
        preflight_options(options(tmp_path, episodes=6, continuous_plan=str(p), instances="0,1"))


def test_a_plan_needs_the_b2_ledger(tmp_path, monkeypatch):
    p, plan, a = planned(tmp_path, monkeypatch)
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_B2", "0")
    with pytest.raises(LearningStop, match="B2 ledger only"):
        preflight_options(a)


def test_a_plan_of_many_bouts_passes_the_preflight(tmp_path, monkeypatch):
    p, plan, a = planned(tmp_path, monkeypatch, n=49)
    preflight_options(a)
    c = execution_conditions(a)
    assert c["smoke_limit"] == {"continuous_attempts": 49} and c["continuous"]["plan"]["seeds"] == plan["seeds"]
    assert len(c["continuous"]["sha256"]) == 64


# ---- the ledger

def ledger(tmp_path, monkeypatch, n=49, **over):
    p, plan, a = planned(tmp_path, monkeypatch, n, **over)
    b = LearningBudget(tmp_path / "budget.json", batch="test-batch", revision="r", worker="w")
    b.bind_execution(execution_conditions(a))
    return b, plan


def test_the_ledger_reserves_the_plan_past_the_smoke_limits_and_no_further(tmp_path, monkeypatch):
    b, plan = ledger(tmp_path, monkeypatch, n=49)
    for i, s in enumerate(plan["seeds"]):
        b.begin_attempt(episode=i, arm="B", seed=s)
    assert len(b.state["attempts"]) == 49 and [a["seed"] for a in b.state["attempts"]] == plan["seeds"]
    with pytest.raises(LearningStop, match="plan complete"):
        b.begin_attempt(episode=49, arm="B", seed=1)
    assert b.state["stop"]["mode"] == "batch_end" and len(b.state["attempts"]) == 49


@pytest.mark.parametrize("attempt", [dict(episode=0, arm="B", seed=999), dict(episode=1, arm="B", seed=1000), dict(episode=0, arm="A", seed=1000)],
                         ids=["seed", "order", "arm"])
def test_an_attempt_off_the_plan_is_refused(tmp_path, monkeypatch, attempt):
    b, plan = ledger(tmp_path, monkeypatch, n=6)
    before = b.path.read_bytes()
    with pytest.raises(LearningStop, match="frozen continuous plan"):
        b.begin_attempt(**attempt)
    assert b.path.read_bytes() == before and b.state["attempts"] == []


def test_the_second_seed_must_be_the_plans_second(tmp_path, monkeypatch):
    b, plan = ledger(tmp_path, monkeypatch, n=6)
    b.begin_attempt(episode=0, arm="B", seed=plan["seeds"][0])
    with pytest.raises(LearningStop, match="frozen continuous plan"):
        b.begin_attempt(episode=1, arm="B", seed=plan["seeds"][2])


def test_a_changed_plan_is_another_batch(tmp_path, monkeypatch):
    b, plan = ledger(tmp_path, monkeypatch, n=6)
    p = tmp_path / "plan.json"
    write_plan(p, 6, seeds=list(reversed(plan["seeds"])))
    with pytest.raises(LearningStop, match="NEW batch"):
        b.bind_execution(execution_conditions(options(tmp_path, episodes=6, continuous_plan=str(p))))


def test_no_retry_of_a_bout(tmp_path, monkeypatch):
    b, plan = ledger(tmp_path, monkeypatch, n=6)
    b.begin_attempt(episode=0, arm="B", seed=plan["seeds"][0])
    with pytest.raises(LearningStop, match="already reserved"):
        b.begin_attempt(episode=0, arm="B", seed=plan["seeds"][0])


# ---- which ends let the next bout start

def test_a_clear_and_a_completed_real_q1_go_on():
    assert continuous_stop_reason(dict(outcome="CLEAR", reason=None)) is None
    assert continuous_stop_reason(Q1_ROW) is None


def _q1(**policy_over):
    pol = {**Q1_ROW["policy"], **policy_over}
    return {**Q1_ROW, "policy": pol}


@pytest.mark.parametrize("row", [dict(outcome="WOULD_DIE", reason="lethal hit"), dict(outcome="STUCK", reason="timebox"),
                                 dict(outcome="HARNESS_FAIL", reason="left the scene"), dict(outcome=None, reason=None),
                                 {**Q1_ROW, "reason": "QUIT: Q2: I2 broken"}, {**Q1_ROW, "min_hp": 3}, {**Q1_ROW, "min_hp": None},
                                 _q1(real_quit=dict(armed=True, main_menu=False, outcome="QUIT")),
                                 _q1(real_quit=dict(armed=False, main_menu=True, outcome="QUIT")),
                                 _q1(real_quit=dict(armed=True, main_menu=True, outcome=None)), _q1(real_quit=None),
                                 _q1(remaining_hp_quit=None), _q1(remaining_hp_quit=0)],
                         ids=["death", "stuck", "harness", "none", "other_q", "hp_above_floor", "hp_unknown", "no_main_menu", "not_armed", "quit_unfinished",
                              "no_real_quit", "no_floor", "zero_floor"])
def test_any_other_end_stops_the_plan(row):
    assert continuous_stop_reason(row)


# ---- the worker

def scripted(rig, monkeypatch, script):
    """The rig with the episode scripted: script[i] sets the record of bout i (CLEAR when it runs out)."""
    import ssbot.train.episode as episode

    def run_episode(link, enc, tap, pol, cfg, rec):
        i = rig.attempts
        rig.attempts += 1
        rig.events.append("episode")
        pol.episode += 1
        assert len(pol.chain_native.budget.state["attempts"]) == rig.attempts
        rig.seeds.append(cfg.seed if hasattr(cfg, "seed") else None)
        rec.outcome = "CLEAR"
        rec.ingame_s = 1.
        if i < len(script):
            script[i](link, pol, rec)

    rig.seeds = []
    monkeypatch.setattr(episode, "run_episode", run_episode)


def q1(link, pol, rec):
    rec.outcome, rec.reason, rec.min_hp, rec.policy = Q1_ROW["outcome"], Q1_ROW["reason"], Q1_ROW["min_hp"], Q1_ROW["policy"]


def outcome(name, reason="x"):
    def set_(link, pol, rec):
        rec.outcome, rec.reason = name, reason

    return set_


def rows(tmp_path):
    return [json.loads(l) for l in (tmp_path / "attempts_i0.jsonl").read_text(encoding="utf-8").splitlines()]


def plan_rig(tmp_path, monkeypatch, script=(), n=6):
    rig = Rig(tmp_path, monkeypatch)
    plan = write_plan(tmp_path / "plan.json", n)
    scripted(rig, monkeypatch, list(script))
    return rig, plan, dict(episodes=n, continuous_plan=str(tmp_path / "plan.json"))


def test_the_worker_plays_the_plans_seeds_in_order_past_the_smoke_limit(tmp_path, monkeypatch):
    rig, plan, kw = plan_rig(tmp_path, monkeypatch)
    assert rig.run(**kw) == 0
    assert rig.attempts == 6 and [r["seed"] for r in rows(tmp_path)] == plan["seeds"]
    assert [a["seed"] for a in rig.budget.state["attempts"]] == plan["seeds"]
    assert rig.receipts()[0]["complete"] and rig.links[0].closed


def test_a_q1_bout_is_recorded_and_the_plan_goes_on(tmp_path, monkeypatch):
    rig, plan, kw = plan_rig(tmp_path, monkeypatch, [lambda *a: None, q1])
    assert rig.run(**kw) == 0
    r = rows(tmp_path)
    assert rig.attempts == 6 and r[1]["outcome"] == "QUIT" and r[1]["min_hp"] == 2 and r[1]["policy"]["real_quit"]["main_menu"] is True
    assert not (tmp_path / "budget.json.halt").exists()


def test_the_game_stays_up_between_bouts_and_recovers_after_each(tmp_path, monkeypatch):
    rig, plan, kw = plan_rig(tmp_path, monkeypatch, [q1])
    rig.run(**kw)
    # one worker: one link, one warm-up, one batch preparation; after_episode between the bouts, not after the last one
    assert len(rig.links) == 1 and rig.events.count("warmup") == 1 and rig.events.count("batch.prepare") == 1
    assert rig.events.count("after_episode") == 5


def test_the_last_bout_goes_straight_to_the_cleanup(tmp_path, monkeypatch, capsys):
    rig, plan, kw = plan_rig(tmp_path, monkeypatch, [lambda *a: None] * 5 + [q1])
    assert rig.run(**kw) == 0
    assert "the plan's last bout ended" in capsys.readouterr().out
    assert rig.events.count("after_episode") == 5 and rig.attempts == 6
    assert rig.events[-1] == "ipc.close" or "ipc.close" in rig.events


@pytest.mark.parametrize("bad,match", [(outcome("WOULD_DIE", "lethal hit"), "WOULD_DIE"), (outcome("STUCK", "timebox"), "STUCK"),
                                       (outcome("HARNESS_FAIL", "left the scene"), "harness"),
                                       (lambda l, p, r: (q1(l, p, r), setattr(r, "reason", "QUIT: Q2: I2 broken")), "not a completed"),
                                       (lambda l, p, r: (q1(l, p, r), setattr(r, "min_hp", 5)), "not a completed"),
                                       (lambda l, p, r: (q1(l, p, r), setattr(r, "policy", {"remaining_hp_quit": 2,
                                        "real_quit": {"armed": True, "main_menu": False, "outcome": "QUIT"}})), "not a completed")],
                         ids=["death", "stuck", "harness", "other_quit", "q1_above_floor", "quit_not_on_the_menu"])
def test_any_other_end_stops_the_worker_with_a_failing_exit(tmp_path, monkeypatch, bad, match):
    rig, plan, kw = plan_rig(tmp_path, monkeypatch, [lambda *a: None, bad])
    with pytest.raises(LearningStop, match=match):
        rig.run(**kw)
    assert rig.attempts == 2 and len(rows(tmp_path)) == 2 and rows(tmp_path)[1]["seed"] == plan["seeds"][1]
    assert rig.events.count("after_episode") == 1                            # none after the bout that stopped it
    assert rig.events.count("ready") == 2 and (tmp_path / "budget.json.halt").exists()
    receipt = rig.receipts()[0]
    assert receipt["complete"] and receipt["resources"]["ipc"] == "pass" and receipt["primary_error"]
    assert rig.links[0].closed


def test_a_chain_stop_ends_the_plan(tmp_path, monkeypatch):
    def stop(link, pol, rec):
        pol.chain_native.learning_stop = "input receipt mismatch"

    rig, plan, kw = plan_rig(tmp_path, monkeypatch, [stop])
    with pytest.raises(LearningStop, match="input receipt mismatch"):
        rig.run(**kw)
    assert rig.attempts == 1 and rows(tmp_path)[0]["b2_learning_stop"] == "input receipt mismatch"
    assert (tmp_path / "budget.json.halt").exists() and rig.links[0].closed


def test_a_scene_field_failure_ends_the_plan(tmp_path, monkeypatch):
    def stop(link, pol, rec):
        pol._scene_field_event_reader = NS(async_builder=NS(failure="field worker died"), close=lambda: None)

    rig, plan, kw = plan_rig(tmp_path, monkeypatch, [stop])
    with pytest.raises(LearningStop, match="scene field stopped: field worker died"):
        rig.run(**kw)
    assert rig.attempts == 1 and rows(tmp_path)[0]["scene_field_stop"] == "field worker died"


def test_a_closed_link_ends_the_plan(tmp_path, monkeypatch):
    def closed(link, pol, rec):
        link.closed = True

    rig, plan, kw = plan_rig(tmp_path, monkeypatch, [closed])
    with pytest.raises(LearningStop, match="game link closed"):
        rig.run(**kw)
    assert rig.attempts == 1 and (tmp_path / "budget.json.halt").exists()


def test_a_failed_recovery_ends_the_plan(tmp_path, monkeypatch):
    rig, plan, kw = plan_rig(tmp_path, monkeypatch, [q1])

    def after_episode(link, enc, instance, d):
        rig.events.append("after_episode")
        raise TimeoutError("load_slot: no gameplay")

    monkeypatch.setattr(C, "after_episode", after_episode)
    with pytest.raises(TimeoutError, match="load_slot"):
        rig.run(**kw)
    assert rig.attempts == 1 and len(rows(tmp_path)) == 1 and (tmp_path / "budget.json.halt").exists()
    assert rig.receipts()[0]["complete"] and rig.links[0].closed


def test_an_exception_in_a_bout_ends_the_plan(tmp_path, monkeypatch):
    def boom(link, pol, rec):
        raise RuntimeError("episode failed")

    rig, plan, kw = plan_rig(tmp_path, monkeypatch, [boom])
    with pytest.raises(RuntimeError, match="episode failed"):
        rig.run(**kw)
    assert rig.attempts == 1 and (tmp_path / "budget.json.halt").exists() and rig.links[0].closed


def test_stop_between_bouts_ends_the_plan_and_cleans_up(tmp_path, monkeypatch):
    rig, plan, kw = plan_rig(tmp_path, monkeypatch)
    n = [0]

    def stop_after_two(run_dir):
        n[0] += 1
        return n[0] > 2

    monkeypatch.setattr(C, "stop_requested", stop_after_two)
    assert rig.run(**kw) == 0
    assert rig.attempts == 2 and len(rows(tmp_path)) == 2 and rig.links[0].closed and rig.receipts()[0]["complete"]


def test_a_halted_ledger_stops_before_the_next_bout(tmp_path, monkeypatch):
    def halt(link, pol, rec):
        (tmp_path / "budget.json.halt").write_text("{}", encoding="utf-8")

    rig, plan, kw = plan_rig(tmp_path, monkeypatch, [halt])
    with pytest.raises(LearningStop):
        rig.run(**kw)
    assert rig.attempts == 1 and rig.links[0].closed


def test_a_finished_plan_cannot_be_run_again_on_its_ledger(tmp_path, monkeypatch):
    rig, plan, kw = plan_rig(tmp_path, monkeypatch, n=2)
    assert rig.run(**kw) == 0
    second = tmp_path / "second"
    second.mkdir()
    with pytest.raises(LearningStop, match="plan complete"):
        rig.run(run_dir=str(second), **kw)                                   # another worker, the same ledger: no bout replayed
    assert rig.attempts == 2


def test_the_seed_options_are_unused_with_a_plan(tmp_path, monkeypatch):
    rig, plan, kw = plan_rig(tmp_path, monkeypatch, n=2)
    assert rig.run(seed=777777, same_seeds=False, **kw) == 0
    assert [r["seed"] for r in rows(tmp_path)] == plan["seeds"]


# ---- the command line

def test_the_worker_command_takes_the_plan(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(C, "worker", lambda a: seen.update(plan=a.continuous_plan, episodes=a.episodes) or 0)
    assert C.main(["_worker", "--instance", "0", "--run-dir", str(tmp_path), "--episodes", "49", "--continuous-plan", "plan.json"]) == 0
    assert seen == {"plan": "plan.json", "episodes": 49}


def test_without_the_option_there_is_no_plan(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(C, "worker", lambda a: seen.update(plan=a.continuous_plan) or 0)
    C.main(["_worker", "--instance", "0", "--run-dir", str(tmp_path)])
    assert seen == {"plan": None}


def test_the_parent_forwards_the_plan_to_its_worker(tmp_path, monkeypatch):
    p, plan, a = planned(tmp_path, monkeypatch, n=6)
    calls = []

    class Proc:
        pid = 1

        def wait(self):
            return 0

    def popen(cmd, **k):
        calls.append(cmd)
        return Proc()

    monkeypatch.setattr(C.subprocess, "Popen", popen)
    monkeypatch.setattr(C, "new_run_dir", lambda *x, **k: tmp_path)
    monkeypatch.setattr(C, "summary", lambda *x, **k: {})
    assert C.run(options(tmp_path, episodes=6, continuous_plan=str(p), instances="0", tag="", start_hp=None)) == 0
    assert len(calls) == 1 and calls[0][calls[0].index("--continuous-plan") + 1] == str(p)
    assert calls[0][calls[0].index("--episodes") + 1] == "6"
