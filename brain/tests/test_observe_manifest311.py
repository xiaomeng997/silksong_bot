"""Task 179 #311b (Sol seq 232): the observation bout's configuration receipt from the REAL constructed policy.

A fresh interpreter (as a worker starts) with the bout's switches - OBSERVE_BOUT, REMAINING_HP_QUIT 0, FACE_HOOK 0,
BOUNCE_TABLE 0, manual-air B2 on arm B - builds ForumPlannerPolicy, prepares the B2 batch (execution bound), reserves
the attempt, resets the w13 episode, snapshots the v2 lazy config and writes the measurement manifest. Both new
switches resolve to the constructed objects (the supervisor config's record-only triggers, the ledger policy, the
bounce mode and the runner's chain set); the switch off resolves too and changes the control fingerprint. No game."""
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

BRAIN = Path(__file__).resolve().parents[1]
CHILD = textwrap.dedent("""
    import json, os, random, sys
    from pathlib import Path
    from types import SimpleNamespace as NS
    sys.dont_write_bytecode = True
    from ssbot.combat.knife_chain_budget import attempt_labels
    from ssbot.knowledge.kinematics import Terrain2D
    from ssbot.train import forum_planner_policy as PP
    from ssbot.train.encounters import ENCOUNTERS
    from ssbot.train.forum_measure_manifest import configuration_manifest, runtime_manifest
    from ssbot.train.measurement import MeasurementTrace, prepare_lazy_configuration
    out = Path(sys.argv[1])
    p = PP.ForumPlannerPolicy(crest="Wanderer", clash="main")
    p.log_path = out / "decisions.jsonl"
    p.terrain = Terrain2D.empty()
    options = NS(instance=0, run_dir=str(out), encounter="Forum_W_w13", mode="eval", policy="planner", view="oracle",
                 episodes=1, hours=0., rotate=1, seed=10, same_seeds=True, time_scale=1., no_record=False, threads=1,
                 real_quit=1., inject_hits=0., start_silk=None, start_hp=None, silk_reserve=False, forum_clash="main",
                 key_cost=None, timebox=0., measure=True)
    budget = p.prepare_learning_batch(options)
    budget.begin_attempt(episode=0, arm="B", seed=10, policy_episode=p.episode + 1, **attempt_labels(0))
    p.measurement = MeasurementTrace(protocol_version=2)
    prepare_lazy_configuration(p, p.measurement)
    p.reset(random.Random(10), ENCOUNTERS["Forum_W_w13"])
    m = configuration_manifest(Path(PP.__file__).resolve().parents[1], p,
                               runtime_context={"worker": {"requested_environment": {}, "boost_result": "none",
                                                           "runtime_before": runtime_manifest()}, "attempt": None})
    keys = ("SSBOT_FORUM_OBSERVE_BOUT", "SSBOT_FORUM_CHAIN_BOUNCE_TABLE", "SSBOT_FORUM_CHAIN_FACE_HOOK",
            "SSBOT_FORUM_REMAINING_HP_QUIT")
    print(json.dumps({"complete": m["configuration_complete"], "unresolved": m["unresolved"],
                      "unknown": m["unknown_environment_switches"], "behavior": m["behavior_sha256"],
                      "episode": [p.episode, p.chain_native.episode], "attempts": budget.state["attempts"],
                      "switches": {k: {f: m["switches"][k].get(f) for f in ("resolution", "effective", "role")}
                                   for k in keys}}))
""")


def run(tmp_path, observe):
    env = {k: v for k, v in os.environ.items() if not k.startswith("SSBOT_")}
    env.update(SSBOT_FORUM_HERO2="1", SSBOT_FORUM_V2="1", SSBOT_FORUM_CHAIN_NATIVE="1", SSBOT_FORUM_CHAIN_B2="1",
               SSBOT_FORUM_CHAIN_AIR_MANUAL="1", SSBOT_FORUM_CHAIN_ARM="B", SSBOT_FORUM_CHAIN_VAULT="1",
               SSBOT_FORUM_CHAIN_FACE_HOOK="0", SSBOT_FORUM_CHAIN_BOUNCE_TABLE="0",
               SSBOT_FORUM_OBSERVE_BOUT="1" if observe else "0", SSBOT_FORUM_REMAINING_HP_QUIT="0",
               SSBOT_FORUM_CHAIN_BATCH=f"manifest311-{int(observe)}", SSBOT_FORUM_CHAIN_PROBE=f"manifest311-{int(observe)}",
               SSBOT_FORUM_CHAIN_BUDGET=str(tmp_path / "budget.json"), PYTHONDONTWRITEBYTECODE="1",
               PYTHONIOENCODING="utf-8", PYTHONPATH=str(BRAIN))
    done = subprocess.run([sys.executable, "-c", CHILD, str(tmp_path)], env=env, cwd=str(BRAIN), capture_output=True,
                          text=True, timeout=600, stdin=subprocess.DEVNULL)
    assert done.returncode == 0, done.stderr[-3000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def both(tmp_path_factory):
    return {obs: run(tmp_path_factory.mktemp(f"obs{obs}"), obs) for obs in (True, False)}


@pytest.mark.parametrize("observe", [True, False])
def test_the_real_policy_manifest_is_complete_for_the_bout_and_with_the_switch_off(both, observe):
    m = both[observe]
    assert m["complete"] and m["unresolved"] == [] and m["unknown"] == []
    assert m["episode"][0] == m["episode"][1] == m["attempts"][0]["policy_episode"]
    s = m["switches"]
    assert s["SSBOT_FORUM_OBSERVE_BOUT"]["resolution"] == "runtime_binding"
    assert s["SSBOT_FORUM_OBSERVE_BOUT"]["effective"] == {
        "policy.sc.cfg.observe_only": ["Q1", "Q3", "Q4", "Q6"] if observe else [],
        "policy.chain_native.budget.policy": "observe-one-bout-v1" if observe else "episode-remaining-2hp-v1"}
    assert s["SSBOT_FORUM_CHAIN_BOUNCE_TABLE"]["role"] == "control"
    assert s["SSBOT_FORUM_CHAIN_BOUNCE_TABLE"]["effective"] == {
        "policy.chain_native._bounce_mode": False, "policy.chain_native.runner.air_bounce_loaded": False}
    assert s["SSBOT_FORUM_CHAIN_FACE_HOOK"]["effective"] == {"policy.chain_native._face_hook_mode": False}
    assert s["SSBOT_FORUM_REMAINING_HP_QUIT"]["effective"] == {"ssbot.train.forum_planner_policy.REMAINING_HP_QUIT": 0}


def test_the_observation_switch_is_part_of_the_control_fingerprint(both):
    assert both[True]["behavior"] != both[False]["behavior"]
