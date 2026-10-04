"""Replay of STUCK episodes under this code's killing-blow rule (task "STUCK at 15 HP", 2026-10-04; DESIGN §3.7.3
YELLOW, §3.7.4 Q6 as revised 2026-10-03): for every Bell Beast eval episode that ended STUCK (the 240 s time box), the
recording drives a fresh PlannerPolicy of this code open loop over the stuck stretch, and per tick it records what
the old rule and this one decide.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.stuck_replay C:/ssbot/data/runs/m2/<run> [<run> ...] [--json out.json]
        [--seconds 60]

  live   from the recording: the hero hits dealt (src, dmg, crit), the hit that left h = 2, the boss HP and the silk
         from then to the end; from the decision log the ticks after the boss reached its final HP (tier, h, n_ok)
  old    the rule before: the supervision glue's one "hero hit", max(5, the largest "hit" this attempt) (a Silkspear's
         15 once one landed), against the boss HP: at or below it YELLOW removed every damaging primitive
  new    this code, replayed from WARM_F frames before the h = 2 hit to `seconds` after the boss reached its final HP
         (or the episode's end): per tick the supervisor's kill_prims / kill_rule / stall, the allowlist's attacks,
         the planner's kill counts (plans that may kill, certified, vetoed R_KILL) and whether the chosen plan presses
         an attack in its first 3 frames or scores a hit (PlanResult.attack). The recording does not follow the new
         choices (the live hero did not attack), so "attacks" counts decisions, not outcomes.
"""
import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

from ssbot.tools.postmortem import find_recording

WARM_F = 60
MAX_HP = 5


def stuck_rows(runs: list[Path]):
    from ssbot.tools.combat_run import load_attempts
    for run in runs:
        for row in load_attempts(run):
            if row.get("outcome") == "STUCK" and row.get("recording"):
                yield run, row


def live_facts(run: Path, row: dict) -> dict:
    """Hits dealt, the h = 2 hit, the boss's final HP and when it got there, from the recording's events."""
    rec = find_recording(run, row)
    f0, f1 = row["f_end"] - row["acts"] - (row.get("late_states") or 0), row["f_end"]
    hits, dmg_taken = [], []
    for line in (rec / "events.jsonl").open(encoding="utf-8"):
        e = json.loads(line)
        fr = e.get("frame") or 0
        if not f0 <= fr <= f1:
            continue
        d = e.get("data") or {}
        if e.get("kind") == "hit":
            hits.append({"f": fr, "src": d.get("src"), "attack": d.get("attack"), "dmg": d.get("dmg"),
                         "crit": d.get("crit"), "hp_after": d.get("hp_after")})
        elif e.get("kind") == "damage":
            dmg_taken.append({"f": fr, "source": d.get("source"), "amount": d.get("amount"),
                              "h_after": (d.get("h") or 0) - (d.get("amount") or 0)})
    low = [x for x in dmg_taken if x["h_after"] <= MAX_HP - 2]
    last = hits[-1] if hits else None
    old_hit, old = 5, []
    for x in hits:                    # the old glue's one number, and when it first exceeded the nail's 5
        if isinstance(x["dmg"], (int, float)) and x["dmg"] > old_hit:
            old_hit = int(x["dmg"])
            old.append((x["f"], old_hit, x["src"]))
    return {"rec": rec, "hits": hits, "damage": dmg_taken, "low_hit_f": low[0]["f"] if low else None,
            "boss_final": None if last is None else last["hp_after"], "final_f": None if last is None else last["f"],
            "old_hero_hit": old_hit, "old_raised": old,
            "srcs": dict(Counter(f"{x['src']}:{x['dmg']}" for x in hits)), "crits": sum(bool(x["crit"]) for x in hits)}


def live_log(run: Path, row: dict, f_from: int) -> dict:
    """The live decision log's ticks from f_from: tiers, h, silk, and the planner's allowed counts."""
    p = run / f"decisions_i{row['instance']}.jsonl"
    rows = []
    if p.is_file():
        key = f'"ep": {row["episode"]},'
        for line in p.open(encoding="utf-8"):
            if key in line[:24]:
                r = json.loads(line)
                if r.get("ep") == row["episode"] and r["f"] >= f_from:
                    rows.append(r)
    return {"ticks": len(rows), "tiers": dict(Counter(r.get("tier") for r in rows)),
            "h": dict(Counter(r.get("h") for r in rows)), "silk": dict(Counter(r.get("silk") for r in rows)),
            "n_ok_by_mode": {m: sorted({r.get("n_ok") for r in rows if r.get("mode") == m})
                             for m in sorted({r.get("mode") for r in rows})},
            "attacks_scored": sum(1 for r in rows if r.get("attack")),
            "plans_with_attack": sum(1 for r in rows if "atk" in (r.get("plan") or "").lower()
                                     or "ATTACK" in (r.get("plan") or ""))}


def replay(run: Path, row: dict, facts: dict, pol, seconds: float) -> dict:
    from ssbot.core.primitives import ATTACKS, Prim
    from ssbot.knowledge.kinematics import B_ATTACK, Terrain2D
    from ssbot.record.recorder import RecordingReader
    from ssbot.train.encounters import BELL_BEAST
    r = RecordingReader(facts["rec"])
    for _, m in r.terrain():
        if m.get("scene_raw") == BELL_BEAST.scene:
            pol.terrain = Terrain2D.from_message(m, pol.params.scene(BELL_BEAST.scene))
    start = row["f_end"] - row["acts"] - (row.get("late_states") or 0)
    fh = facts["low_hit_f"] or start
    ff = facts["final_f"] or fh
    end = min(row["f_end"], ff + int(seconds * 60))

    class Tap:
        wake_frame = row.get("f_wake")
    pol.reset(random.Random(row["seed"]), BELL_BEAST)
    states = r.states(start, end + 1)
    ticks = []
    prev = None
    for s in states:
        nxt_mask = None
        if prev is not None:
            f_prev = prev["f"]
            if s["f"] == f_prev + 1 and (s.get("act") or {}).get("mask") is not None:
                nxt_mask = int(s["act"]["mask"])
            if nxt_mask is not None:
                pol.sent[f_prev + 1] = nxt_mask
            _step(pol, prev, Tap, fh, ff, ticks, B_ATTACK, ATTACKS, Prim)
        prev = s
    if prev is not None:
        _step(pol, prev, Tap, fh, ff, ticks, B_ATTACK, ATTACKS, Prim)
    after = [t for t in ticks if t["after_final"]]
    first_atk = next((t["f"] - ff for t in after if t["presses"]), None)
    first_hit = next((t["f"] - ff for t in after if t["scores_hit"]), None)
    return {"from_f": fh - WARM_F, "to_f": end, "ticks": len(ticks), "after_final_ticks": len(after),
            "tiers": dict(Counter(t["tier"] for t in after)), "h": dict(Counter(t["h"] for t in after)),
            "attacks_allowed": sum(t["atk_allowed"] for t in after),
            "nail_in_kill_prims": sum(t["nail_kills"] for t in after),
            "plans_may_kill": sum(t["kill"][0] > 0 for t in after),
            "r_kill_vetoes": sum(t["kill"][2] for t in after),
            "chosen_presses_attack": sum(t["presses"] for t in after),
            "kill_certified_ticks": sum(t["kill"][1] > 0 for t in after),
            "in_flight_ticks": sum(len(t["kill"]) > 3 and t["kill"][3] > 0 for t in after),
            "chosen_certified_kill": sum(t["chosen_cert"] for t in after),
            "idle_clear_p50": (sorted(t["idle_clear"] for t in after if t["idle_clear"] is not None) or [None])[
                len([t for t in after if t["idle_clear"] is not None]) // 2],
            "chosen_scores_hit": sum(t["scores_hit"] for t in after),
            "first_attack_after_final_f": first_atk, "first_scored_hit_after_final_f": first_hit,
            "pending": next(({"f": t["f"] - ff, "triggers": t["triggers"]} for t in ticks if t["pending"]), None),
            "max_stall_s": max((t["stall"] for t in ticks), default=0.0)}


def _step(pol, s, tap, fh, ff, ticks, B_ATTACK, ATTACKS, Prim):
    from ssbot.tools.lowhp_replay import _perceive
    f = s["f"]
    if f < fh - WARM_F:
        _perceive(pol, s, tap)
        return
    pol.act(s, tap)
    if f < fh or pol.planner_last is None or pol.decision is None:
        return
    d, res = pol.decision, pol.planner_last
    ticks.append({"f": f, "after_final": f > ff, "tier": d.tier, "h": d.h,
                  "atk_allowed": d.allows(Prim.ATTACK_SIDE), "nail_kills": bool(d.kill_prims & ATTACKS),
                  "kill": list(pol.planner.last_kill), "presses": bool((res.cmd[:3] & B_ATTACK).any()),
                  "scores_hit": res.attack is not None, "pending": d.pause_pending, "triggers": list(d.triggers),
                  "stall": round(d.stall_s, 2), "idle_clear": res.idle_clear,
                  "chosen_cert": bool(res.kill is not None and res.kill.certified and not res.kill.i3)})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", type=Path, nargs="+")
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--kill-hp", type=float, default=None,
                    help="counterfactual: every enemy's HP read as this (e.g. 5: the last nail hit), so the replay "
                         "shows how often a killing blow is certified on the recorded states")
    a = ap.parse_args(argv)
    if a.kill_hp is not None:
        import ssbot.combat.safety_filter as sf
        import ssbot.train.supervision as sup
        sf.kill_hp_world = lambda ws, z=sf.VISION_HP_Z: a.kill_hp
        sup.kill_hp_world = sf.kill_hp_world
        sup.threat_min_hp = lambda s: a.kill_hp
    from ssbot.train.planner_policy import PlannerPolicy
    pols: dict[str, PlannerPolicy] = {}
    items = []
    for run, row in stuck_rows(a.runs):
        view = (row.get("policy") or {}).get("view", "oracle")
        if view not in pols:
            pols[view] = PlannerPolicy(view=view, threads=a.threads)
        facts = live_facts(run, row)
        lg = live_log(run, row, (facts["final_f"] or 0) + 1)
        rp = replay(run, row, facts, pols[view], a.seconds)
        x = {"run": run.name, "instance": row.get("instance"), "episode": row.get("episode"), "seed": row.get("seed"),
             "code": row.get("code_rev"), "view": view,
             "live": {k: v for k, v in facts.items() if k not in ("rec", "hits", "damage")} | {"log": lg},
             "replay": rp}
        items.append(x)
        print(json.dumps({"run": x["run"][:15], "i": x["instance"], "ep": x["episode"],
                          "boss_final": facts["boss_final"], "old_hero_hit": facts["old_hero_hit"],
                          "crits": facts["crits"], "live_tiers": lg["tiers"], "live_silk": lg["silk"],
                          "live_attacks_scored": lg["attacks_scored"]}
                         | {k: rp[k] for k in ("after_final_ticks", "attacks_allowed", "nail_in_kill_prims",
                                               "chosen_presses_attack", "chosen_scores_hit",
                                               "first_attack_after_final_f", "first_scored_hit_after_final_f",
                                               "r_kill_vetoes", "kill_certified_ticks", "pending", "max_stall_s")},
                         default=str), flush=True)
    summ = {"episodes": len(items),
            "boss_final": dict(Counter(x["live"]["boss_final"] for x in items)),
            "old_hero_hit": dict(Counter(x["live"]["old_hero_hit"] for x in items)),
            "crits": sum(x["live"]["crits"] for x in items),
            "new_attacks_after_final": sum(x["replay"]["chosen_presses_attack"] > 0 for x in items),
            "new_scored_hits_after_final": sum(x["replay"]["chosen_scores_hit"] > 0 for x in items),
            "new_pending": sum(x["replay"]["pending"] is not None for x in items)}
    print(json.dumps(summ, indent=1))
    if a.json:
        a.json.write_text(json.dumps({"summary": summ, "items": items}, indent=1, default=str), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
