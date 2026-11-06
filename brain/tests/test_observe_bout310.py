"""Task 179 #310 (the person, Sol seq 230): the ONE watched observation bout.

Opt-in SSBOT_FORUM_OBSERVE_BOUT=1. Ordinary / chain HP losses never stop it; a guard-vetoed lethal hit is recorded and
play goes on (episode loop, measurement window, B2 ledger, policy learning check); an unblocked lethal hit or a dead
hero still stops; one bout, no HP quit, 45 s game time. Without the switch every path is unchanged."""
from types import SimpleNamespace as NS

import pytest

from ssbot.combat.knife_chain_budget import (LearningBudget, LearningStop, OBSERVE_POLICY, execution_conditions,
                                             preflight_options)
from ssbot.train import observe_bout
from ssbot.train.episode import _stopping_lethal
from ssbot.train.forum_measure_window import CLAPPER, MeasurementWindow


def state(f, dt=.1, ev=(), hp=7):
    return {"f": f, "dt": dt, "ev": list(ev), "hero": {"health": hp, "health_blue": 0},
            "ents": [{"iid": i, "type_key": CLAPPER, "hp": 230, "is_dead": False, "hidden": False} for i in (1, 2)],
            "room": {"battles": [{"started": True, "wave": 13}]}}


def event(f, kind, **data):
    return {"f": f, "q": f * 100, "k": kind, "d": data}


def window(observe, game_limit=120.):
    return MeasurementWindow(NS(wake_frame=10), wave=13, expected_targets=2, game_limit=game_limit,
                             observe_lethal=observe)


def test_the_switch_is_explicit(monkeypatch):
    monkeypatch.delenv(observe_bout.ENV, raising=False)
    assert not observe_bout.enabled()
    monkeypatch.setenv(observe_bout.ENV, "1")
    assert observe_bout.enabled() and observe_bout.label()["hp_stop"] is None
    monkeypatch.setenv(observe_bout.ENV, "yes")
    with pytest.raises(ValueError):
        observe_bout.enabled()


@pytest.mark.parametrize("observe", [False, True])
def test_the_window_records_a_vetoed_lethal_and_goes_on_only_when_observing(observe):
    w = window(observe)
    for f in range(10, 16):
        w.observe(state(f, ev=[event(f, "would_die", blocked=True, cause="death_catch")] if f == 12 else []),
                  f * 100_000_000)
    r = w.snapshot()
    if observe:
        assert r["end_f"] is None and r["lethal_vetoes"] == [12] and r["observe_lethal"]
    else:
        assert (r["end_f"], r["end_reason"]) == (12, "lethal") and "lethal_vetoes" not in r


@pytest.mark.parametrize("kind,data", [("would_die", {"blocked": False}), ("catastrophe", {}), ("hero_dead", {})])
def test_the_observed_window_still_ends_on_an_unblocked_lethal_or_a_death(kind, data):
    w = window(True)
    for f in range(10, 14):
        w.observe(state(f, ev=[event(f, kind, **data)] if f == 12 else []), f * 100_000_000)
    r = w.snapshot()
    assert (r["end_f"], r["end_reason"]) == (12, "lethal") and r["lethal_vetoes"] == []


def test_the_observed_window_ends_at_the_45s_game_limit():
    w = window(True, game_limit=observe_bout.GAME_LIMIT_S)
    for f in range(10, 10 + 95):
        w.observe(state(f, dt=.5, ev=[event(f, "catastrophe", blocked=True)] if f == 20 else []), f * 10_000_000)
    r = w.snapshot()
    assert r["end_reason"] == "game_timeout" and r["T"] == pytest.approx(45.) and r["lethal_vetoes"] == [20]


@pytest.mark.parametrize("observe", [False, True])
@pytest.mark.parametrize("blocked", [False, True])
@pytest.mark.parametrize("mode", ["eval", "data"])
def test_the_episode_ends_on_a_lethal_hit_only_as_the_mode_says(monkeypatch, observe, blocked, mode):
    monkeypatch.setenv(observe_bout.ENV, "1" if observe else "0")
    tap = NS(lethal=[(100, "would_die", {"blocked": blocked})])
    assert _stopping_lethal(tap, NS(mode=mode)) is (mode == "eval" and (not observe or not blocked))
    assert _stopping_lethal(NS(lethal=[]), NS(mode=mode)) is False


def test_the_observation_ledger_has_no_hp_quit_and_keeps_every_fatal(tmp_path):
    b = LearningBudget(tmp_path / "b.json", batch="obs", revision="r", worker="i0", policy=OBSERVE_POLICY)
    b.bind_execution({"real_quit": 1.})
    b.begin_attempt(episode=0, arm="B", seed=1)
    for f in (10, 20, 30, 40):
        b.observe(episode=0, frame=f, arm="B", hp_loss=2, chain_related=True)
    assert b.state["stop"] is None and b.remaining_hp_quit is None and b.state["b_fight_hp"] == 8
    with pytest.raises(LearningStop, match="death"):
        b.observe(episode=0, frame=50, arm="B", fatal="death")


def test_the_observation_preflight_binds_one_bout_and_no_hp_quit(tmp_path, monkeypatch):
    from tests.test_b2_worker_batch import options, env
    env(monkeypatch, tmp_path)
    monkeypatch.setenv(observe_bout.ENV, "1")
    a = options(tmp_path, real_quit=1.)
    a.episodes = 1
    preflight_options(a)
    assert execution_conditions(a)["learning_policy"]["policy"] == OBSERVE_POLICY
    a.episodes = 2
    with pytest.raises(LearningStop, match="exactly one bout"):
        preflight_options(a)
    a.episodes = 1
    monkeypatch.setenv("SSBOT_FORUM_REMAINING_HP_QUIT", "6")
    with pytest.raises(LearningStop, match="HP quit"):
        preflight_options(a)


def b2(monkeypatch, tmp_path, observe):
    from ssbot.combat.knife_chain_air import load_runner
    from ssbot.combat.knife_chain_air_native import NativeManualAirChain
    from ssbot.combat.knife_chain_budget import LOW_HP_POLICY
    from tests.test_knife_chain_air import raw
    budget = LearningBudget(tmp_path / "b.json", batch="obs", revision="r", worker="i0",
                            policy=OBSERVE_POLICY if observe else LOW_HP_POLICY)
    budget.bind_execution({"real_quit": 1.})
    n = NativeManualAirChain(runner_factory=load_runner, probe_ref="observe310", budget=budget)
    n.reset(0, start_frame=999)
    s = raw(1000)
    s["game"] = {"scene": "Hang_04"}
    n.observe_learning(s)
    return n, raw


@pytest.mark.parametrize("observe", [False, True])
def test_b2_counts_a_vetoed_zero_hp_state_as_fatal_only_without_the_observation(monkeypatch, tmp_path, observe):
    n, raw = b2(monkeypatch, tmp_path, observe)
    s = raw(1001)
    s["game"] = {"scene": "Hang_04"}
    s["hero"]["health"] = 0
    s["ev"] = [event(1001, "would_die", blocked=True, cause="death_catch")]
    if observe:
        n.observe_learning(s)
        assert any(e["event"] == "b2_observe_lethal_veto" for e in n.events) and n.learning_stop is None
    else:
        with pytest.raises(LearningStop, match="death"):
            n.observe_learning(s)


@pytest.mark.parametrize("case", ["no_veto", "unblocked", "dead_flag"])
def test_b2_still_stops_an_observed_death(monkeypatch, tmp_path, case):
    n, raw = b2(monkeypatch, tmp_path, True)
    s = raw(1001)
    s["game"] = {"scene": "Hang_04"}
    s["hero"]["health"] = 0 if case != "dead_flag" else 3
    s["ev"] = [] if case == "no_veto" else [event(1001, "would_die", blocked=False)] if case == "unblocked" else []
    if case == "dead_flag":            # a dead hero stops even beside a vetoed event
        from ssbot.combat.knife_chain_nominal import state_names
        i = state_names().index("dead")
        bits = list(s["hero"]["cstate"])
        bits[i // 64] = int(bits[i // 64]) | (1 << (i % 64))
        s["hero"]["cstate"] = bits
        s["ev"] = [event(1001, "would_die", blocked=True)]
    with pytest.raises(LearningStop, match="death"):
        n.observe_learning(s)


@pytest.mark.parametrize("observe", [False, True])
@pytest.mark.parametrize("blocked", [False, True])
def test_the_policy_learning_check_stops_only_on_an_unblocked_lethal_when_observing(monkeypatch, observe, blocked):
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy
    monkeypatch.setenv(observe_bout.ENV, "1" if observe else "0")
    stops = []
    audit = NS(b2=True, exit_transition=False, _episode_start=None, observe_learning=lambda *a, **k: None,
               _stop=lambda why, f: stops.append(why))
    p = ForumPlannerPolicy.__new__(ForumPlannerPolicy)
    p.chain_native, p._inbox = audit, None
    p.learning_check({"f": 1001}, NS(death_frame=None, lethal=[(1001, "would_die", {"blocked": blocked})]))
    assert bool(stops) is (not observe or not blocked)
