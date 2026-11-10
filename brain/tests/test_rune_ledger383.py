"""Task 182 seq 312 #383: L2 reads the same big rune ledger every key owner reads. The REAL constructed policy, reset for a w13
episode in a fresh interpreter (the switches of the production arm): tac.rune_life is the episode's RuneCircles, the instance the
policy updates every tick and the scripts read (before #383 reset() wired L2 to the instance it then replaced: L2 saw no circle)."""
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

BRAIN = Path(__file__).resolve().parents[1]
CHILD = textwrap.dedent("""
    import json, random, sys
    from pathlib import Path
    from types import SimpleNamespace as NS
    sys.dont_write_bytecode = True
    from ssbot.combat.knife_chain_budget import attempt_labels
    from ssbot.combat.tactics.gauntlet import GauntletTactics
    from ssbot.knowledge.kinematics import Terrain2D
    from ssbot.train import forum_planner_policy as PP
    from ssbot.train.encounters import ENCOUNTERS
    out = Path(sys.argv[1])
    p = PP.ForumPlannerPolicy(crest="Wanderer", clash="main")
    p.log_path = out / "decisions.jsonl"
    p.terrain = Terrain2D.empty()
    options = NS(instance=0, run_dir=str(out), encounter="Forum_W_w13", mode="eval", policy="planner", view="oracle",
                 episodes=2, hours=0., rotate=1, seed=10, same_seeds=True, time_scale=1., no_record=False, threads=1,
                 real_quit=1., inject_hits=0., start_silk=None, start_hp=None, silk_reserve=False, forum_clash="main",
                 key_cost=None, timebox=0., measure=False)
    budget = p.prepare_learning_batch(options)
    rows = []
    for ep in range(2):
        budget.begin_attempt(episode=ep, arm="B", seed=10 + ep, policy_episode=p.episode + 1, **attempt_labels(ep))
        p.reset(random.Random(10 + ep), ENCOUNTERS["Forum_W_w13"])
        g = isinstance(p.tac, GauntletTactics)
        rows.append(dict(gauntlet=g, same=(p.tac.rune_life is p.rune_life) if g else None,
                         scripts=[sc._life is p.rune_life for sc in (p.slam_play, p.cast_stab, p.evade_chase, p.rune_lowhop, p.two)
                                  if sc is not None and hasattr(sc, "_life")]))
        budget.finish_attempt(outcome="test") if hasattr(budget, "finish_attempt") else None
    print(json.dumps(rows))
""")


def test_l2_reads_the_episodes_rune_ledger(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("SSBOT_")}
    env.update(SSBOT_FORUM_HERO2="1", SSBOT_FORUM_V2="1", SSBOT_FORUM_CHAIN_NATIVE="1", SSBOT_FORUM_CHAIN_B2="1",
               SSBOT_FORUM_CHAIN_AIR_MANUAL="1", SSBOT_FORUM_CHAIN_ARM="B", SSBOT_FORUM_CHAIN_VAULT="1", SSBOT_FORUM_TWO_PLAN="1",
               SSBOT_FORUM_TWO_PLAN_INLINE="1", SSBOT_FORUM_REMAINING_HP_QUIT="0", SSBOT_FORUM_CHAIN_BATCH="ledger383",
               SSBOT_FORUM_CHAIN_PROBE="ledger383", SSBOT_FORUM_CHAIN_BUDGET=str(tmp_path / "budget.json"),
               PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8", PYTHONPATH=str(BRAIN))
    done = subprocess.run([sys.executable, "-c", CHILD, str(tmp_path)], env=env, cwd=str(BRAIN), capture_output=True, text=True,
                          timeout=600, stdin=subprocess.DEVNULL)
    assert done.returncode == 0, done.stderr[-3000:]
    rows = json.loads(done.stdout.strip().splitlines()[-1])
    assert all(r["gauntlet"] for r in rows)
    assert all(r["same"] is True for r in rows), rows
    assert all(all(r["scripts"]) and r["scripts"] for r in rows), rows
