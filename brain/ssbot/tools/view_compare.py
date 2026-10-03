"""Oracle view against the vision-equivalent view on the same recorded fights (M2 task V, DESIGN §3.9.2): where does
the simulated final path lose what the oracle view has, tick by tick?

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.view_compare C:/ssbot/data/runs/m2/<run> [--instance 0]
        [--episodes 0,1] [--views oracle,degraded_dust] [--threads 4] [--jsonl out.jsonl] [--json summary.json]

How: each episode's recording drives one PlannerPolicy per view, open loop, through the same STATEs. The prefix of
every tick (the masks already sent for the frames between the WorldState and the decision) is the recorded one (STATE
act.hf.desired), so every view plans from the hero's real motion, not from its own counterfactual decisions; the
supervisor runs but its pauses are dropped (a view that would have quit keeps planning). Per tick and view: the
tracker's state, the plan, S, FORCED_RISK, the number of safe candidates, the pogo plans (generated, rejected by the
lane gate, accepted) and whether the chosen plan is an accepted pogo; per tick the Control state from the recording
(the truth both views are scored against). The summary groups ticks by the recorded Control state (and whether a drop
bell is falling) and puts the views side by side.
"""
import argparse
import dataclasses
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np


def _control_state(s: dict) -> str | None:
    b = next((e for e in s.get("ents") or () if e.get("type_key") == "Bone Beast"), None)
    if not b or not b.get("fsms"):
        return None
    return b["fsms"][0].get("state")


def _bells_falling(s: dict) -> int:
    n = 0
    for e in s.get("ents") or ():
        if str(e.get("type_key", "")).startswith("BoneBeast DropBell") and e.get("fsms"):
            if e["fsms"][0].get("state") not in ("Dormant", "Init", "Antic", "Position"):
                n += 1
    return n


def _neutralize(pol) -> None:
    """Supervisor pauses dropped: the decision is kept (tier, allowlist) without pause_pending."""
    from ssbot.train.supervision import Supervised
    sc = pol.sc
    orig = sc.step

    def step(s, **kw):
        r = orig(s, **kw)
        sc.pq = None
        d = r.decision
        if dataclasses.is_dataclass(d):
            d = dataclasses.replace(d, pause_pending=False, stop_input=False, quit_requested=False)
        return Supervised(None, d, None, r.alerts)
    sc.step = step


def replay_episode(run: Path, row: dict, views: list[str], pols: dict, out_rows: list) -> None:
    from ssbot.knowledge.kinematics import Terrain2D
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.postmortem import find_recording
    from ssbot.train.encounters import BELL_BEAST
    r = RecordingReader(find_recording(run, row))
    terrain = None
    for _, m in r.terrain():
        if m.get("scene_raw") == BELL_BEAST.scene:
            terrain = m

    class Tap:
        wake_frame = row.get("f_wake")
    for v in views:
        pol = pols[v]
        if terrain is not None:
            pol.terrain = Terrain2D.from_message(terrain, pol.params.scene(BELL_BEAST.scene))
        pol.reset(random.Random(row["seed"]), BELL_BEAST)
        _neutralize(pol)
    start = row["f_end"] - row["acts"]
    states = list(r.states(start, row["f_end"]))
    desired = {}
    for s in states:
        hf = (s.get("act") or {}).get("hf") or {}
        desired[s["f"]] = int(hf.get("desired", (s.get("act") or {}).get("mask") or 0))
    for s in states:
        f = s["f"]
        rec = {"ep": row.get("episode"), "f": f, "cs": _control_state(s), "bells": _bells_falling(s),
               "hero": [round(float(x), 2) for x in ((s.get("hero") or {}).get("pos") or (0, 0))[:2]]}
        for v in views:
            pol = pols[v]
            for g in range(f - 12, f + 2):
                if g in desired:
                    pol.sent[g] = desired[g]
            pol.planner_last = None
            pol.act(s, Tap)
            res = pol.planner_last
            if res is None:                   # no planner tick (the delay line filling)
                rec[v] = None
                continue
            pl = pol.planner
            pz = pl._pogo_ok if pl is not None else np.zeros(0, bool)
            chosen_pogo = bool(0 <= res.idx < len(pz) and pz[res.idx])
            rec[v] = {"st": pol.fc.tracker.state, "plan": res.name, "S": int(res.S), "forced": bool(res.forced_risk),
                      "safe": int(res.n_safe), "pogo": dict(pl.pogo_log) if pl is not None else {},
                      "cpogo": chosen_pogo, "fo": pol.forecasts[-1][0] if pol.forecasts else None}
        out_rows.append(rec)


def summarize(rows: list[dict], views: list[str]) -> dict:
    agg: dict = defaultdict(lambda: {v: [0, 0, 0, 0, 0, 0, 0] for v in views})
    for r in rows:
        key = f"{r['cs']}{'+bell' if r['bells'] else ''}"
        for v in views:
            x = r.get(v)
            if not x:
                continue
            a = agg[key][v]
            a[0] += 1
            a[1] += x["forced"]
            a[2] += x["pogo"].get("generated", 0)
            a[3] += x["pogo"].get("lane_miss", 0)
            a[4] += x["pogo"].get("accepted", 0)
            a[5] += x["cpogo"]
            a[6] += x["safe"]
    out = {}
    for key, d in sorted(agg.items(), key=lambda kv: -max(a[0] for a in kv[1].values())):
        out[key] = {v: {"ticks": a[0], "forced_pct": round(100 * a[1] / max(1, a[0]), 1),
                        "gen": round(a[2] / max(1, a[0]), 2), "lane_miss": round(a[3] / max(1, a[0]), 2),
                        "acc": round(a[4] / max(1, a[0]), 2), "chosen_pogo": a[5],
                        "safe": round(a[6] / max(1, a[0]), 1)} for v, a in d.items()}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path)
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--episodes", default="0")
    ap.add_argument("--views", default="oracle,degraded_dust")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--jsonl", type=Path, default=None)
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    from ssbot.tools.postmortem import episode_rows
    from ssbot.train.planner_policy import PlannerPolicy
    views = a.views.split(",")
    rows = episode_rows(a.run, a.instance)
    pols = {v: PlannerPolicy(view=v, threads=a.threads) for v in views}
    out_rows: list[dict] = []
    eps = [int(x) for x in a.episodes.split(",")] if a.episodes != "all" else list(range(len(rows)))
    for ep in eps:
        row = rows[ep]
        if row.get("outcome") == "HARNESS_FAIL" or not row.get("recording"):
            continue
        row = dict(row, episode=ep)
        replay_episode(a.run, row, views, pols, out_rows)
        print(f"ep {ep}: {len(out_rows)} ticks", flush=True)
    if a.jsonl:
        with a.jsonl.open("w", encoding="utf-8") as fh:
            for r in out_rows:
                fh.write(json.dumps(r) + "\n")
    summ = summarize(out_rows, views)
    for key, d in summ.items():
        print(f"{key:22s} " + "  ".join(f"{v[:6]}: n {x['ticks']:5d} fr {x['forced_pct']:5.1f} gen {x['gen']:6.2f} "
                                         f"miss {x['lane_miss']:5.2f} acc {x['acc']:5.2f} cp {x['chosen_pogo']:4d} "
                                         f"safe {x['safe']:6.1f}" for v, x in d.items()))
    if a.json:
        a.json.write_text(json.dumps(summ, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
