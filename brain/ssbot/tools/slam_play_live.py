"""The Clapper's slams in live 1v1 runs, per arm (task 1v1 SP1, forum.md 65.4): did the playbook play it (its keys
in the STATE act.mask: the jump rising at antic +K_JUMP and the attack at +K_PRESS, either one frame late), landed,
bounce, damage in the slam (until the Slam Recover ends) and in the 60 frames after, the hero's distance at the antic
and at the Slam 0 entry (centre to centre, + = in front), and the policy's own playbook counters (attempts row
policy.slam_play).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.slam_play_live --manifest C:/ssbot/sandbox/1v1play_manifest.txt \
        [--manifest C:/ssbot/sandbox/1v1_manifest.txt --arms rn] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np

from ssbot.combat import slam_play as sp
from ssbot.probes.slam_play_probe import PlayProbe

AFTER_F = 60


def pct(v, qs=(10, 50, 90)):
    v = [x for x in v if x is not None]
    return [round(float(np.percentile(v, q)), 2) for q in qs] if v else None


def manifest(paths, arms) -> list[tuple[str, int, Path]]:
    out = []
    for p in paths:
        for line in Path(p).read_text("utf-8-sig").splitlines():
            parts = line.strip().split("\t")
            if len(parts) < 4 or (arms and parts[0] not in arms):
                continue
            out.append((parts[0], int(parts[2]), Path(parts[3].strip())))
    return out


def slams_of(states: list[dict], cfg: sp.PlayCfg) -> list[dict]:
    out = []
    prev_st = None
    for i, s in enumerate(states):
        e = sp.clapper(s)
        st = sp.control(e)[0]
        if st == "Slam Antic" and prev_st != "Slam Antic":
            face = 1 if e.get("flipX") else -1
            fa = s["f"]
            rows, end_n = [], None
            for s2 in states[i:]:
                rows.append(PlayProbe._row(s2, sp.clapper(s2), 0))
                if end_n is None and len(rows) > 5 and rows[-1]["st"] not in sp.SLAM_STATES:
                    end_n = len(rows)
                if (end_n is not None and len(rows) >= end_n + AFTER_F) or len(rows) > 400:
                    break
            run = NS(fa=fa, face=face, phase="", why="", k_start=None, x_start=None, k_jump=None, x_jump=None,
                     k_press=None)
            o = PlayProbe._outcome(run, rows)
            # the playbook's own keys: the jump rising at antic +15..40, then an attack rising with down by +60 (the
            # first rising attack after the antic can be the planner's slash)
            prev, jump, press = 0, None, None
            for r in rows:
                rise = r["act"] & ~prev
                prev = r["act"]
                k = r["f"] - fa
                if jump is None and rise & sp.M_J and 15 <= k <= 40:
                    jump = r["f"]
                elif jump is not None and press is None and rise & sp.M_A and r["act"] & sp.M_D and k <= 60:
                    press = r["f"]
            landed = kill = False
            if press is not None:
                win = [r for r in rows if press - 1 <= r["f"] <= press + 14]
                c0 = next((r["chp"] for r in win if r["chp"] is not None), None)
                landed = any(r["chp"] is not None and c0 is not None and r["chp"] < c0 for r in win)
                kill = c0 is not None and any(r["cx"] is None for r in win if r["f"] > press)
            x0 = (sp.hero_x(s) - float(e["pos"][0])) * face
            s0r = next((r for r in rows if r["st"] == "Slam 0"), None)
            played = (jump is not None and press is not None and jump - fa in (cfg.k_jump - 1, cfg.k_jump, cfg.k_jump + 1)
                      and press - fa in (cfg.k_press - 1, cfg.k_press, cfg.k_press + 1))
            o.pop("trace", None)
            o.update({"k_jump_real": None if jump is None else jump - fa, "k_press_real": None if press is None else
                      press - fa, "press_rel_s0": None if (press is None or o.get("s0") is None) else press - o["s0"],
                      "landed": landed or kill, "kill": kill})
            o["success"] = bool(o["landed"] and not o.get("hurt_slam"))
            out.append({"f": fa, "x_antic": round(x0, 2), "ground": sp.on_ground(s),
                        "x_s0": None if s0r is None or s0r["cx"] is None else round((s0r["x"] - s0r["cx"]) * face, 2),
                        "played": played} | o)
        prev_st = st
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", action="append", required=True)
    ap.add_argument("--arms", default="")
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    from ssbot.record.recorder import RecordingReader
    cfg = sp.PlayCfg()
    arms = set(filter(None, a.arms.split(",")))
    per = defaultdict(list)
    eps = defaultdict(list)
    for arm, inst, run in manifest(a.manifest, arms):
        for line in (run / f"attempts_i{inst}.jsonl").read_text("utf-8").splitlines():
            row = json.loads(line)
            if row.get("outcome") == "HARNESS_FAIL":
                continue
            states = list(RecordingReader(row["recording"]).states(row["f_wake"], row["f_end"]))
            S = slams_of(states, cfg)
            for x in S:
                x["ep"] = f"{run.name[:15]}_i{inst}_e{row['episode']}"
            per[arm] += S
            hp_drops, touches = [], 0
            fk = row.get("f_kill") or row["f_end"]
            for a_, b_ in zip(states, states[1:]):
                ha, hb = (a_.get("hero") or {}).get("health"), (b_.get("hero") or {}).get("health")
                if ha is not None and hb is not None and hb < ha:
                    hp_drops.append((b_["f"], ha - hb, b_["f"] <= fk))
            for i_, s_ in enumerate(states):
                for ev in s_.get("ev") or ():
                    if ev.get("k") == "damage" and not any(abs(f_ - s_["f"]) <= 3 for f_, _, _ in hp_drops):
                        touches += 1
            eps[arm].append({"ep": f"{run.name[:15]}_i{inst}_e{row['episode']}", "outcome": row.get("outcome"),
                             "hits": row.get("hits"), "ingame_s": row.get("ingame_s"), "kill_s": row.get("kill_s"),
                             "hp_hits_before_kill": sum(1 for _, _, b in hp_drops if b),
                             "hp_lost_before_kill": sum(d for _, d, b in hp_drops if b),
                             "hp_hits_tail": sum(1 for _, _, b in hp_drops if not b), "protected_touches": touches,
                             "slam_play": (row.get("policy") or {}).get("slam_play")})
    out = {}
    for arm, S in per.items():
        pl = [x for x in S if x["played"]]
        out[arm] = {
            "episodes": len(eps[arm]), "slams": len(S), "played": len(pl),
            "played_success": sum(x["success"] for x in pl), "played_landed": sum(x["landed"] for x in pl),
            "played_hurt_slam": sum(1 for x in pl if x["hurt_slam"]),
            "played_hurt_after": sum(1 for x in pl if x["hurt_after"]),
            "all_landed": sum(x["landed"] for x in S),
            "all_hurt_slam": sum(1 for x in S if x["hurt_slam"]),
            "hurt_slam_src": dict(Counter(h["src"][-20:] for x in S for h in x["hurt_slam"])),
            "x_antic": pct([x["x_antic"] for x in S]), "x_s0": pct([x["x_s0"] for x in S]),
            "fled_s0_gt9": sum(1 for x in S if x["x_s0"] is not None and abs(x["x_s0"]) > 9),
            "antic": dict(Counter(x.get("antic") for x in S)),
            "not_played_x_antic": pct([x["x_antic"] for x in S if not x["played"]]),
            "not_played_ground": sum(1 for x in S if not x["played"] and x["ground"]),
            "policy_counts": dict(sum((Counter(e["slam_play"] or {}) for e in eps[arm]), Counter())),
            "played_kill": sum(1 for x in pl if x.get("kill")),
            "kills": sum(1 for e in eps[arm] if e["kill_s"] is not None),
            "hp_hitless_kills": sum(1 for e in eps[arm] if e["kill_s"] is not None and e["hp_hits_before_kill"] == 0),
            "hp_hits_before_kill": sum(e["hp_hits_before_kill"] for e in eps[arm]),
            "protected_touches": sum(e["protected_touches"] for e in eps[arm]),
            "kill_s": pct([e["kill_s"] for e in eps[arm]]),
            "eps": eps[arm]}
        print(arm, json.dumps({k: v for k, v in out[arm].items() if k != "eps"}))
    if a.json:
        a.json.write_text(json.dumps({"arms": out, "slams": per}, indent=1, default=str), "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
