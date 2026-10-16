"""Why the planner picks a row at given frames (task 1v1 SP4, forum.md 68): an episode replayed open loop through the
policy (the recorded STATEs, the planner plans every tick with infinite deadlines, its keys are not applied - as
tools.forum_1v1_rows), and at the asked frames the chosen row, the L2 branch, and the best rows of each kind (ground
rows: no jump / dash key in the row's first 12 frames; jump rows; attack rows) with their selection keys (hz, hz_soft,
S, U, keep, safe, landed hits nh, J) and the escape check's result. The arm's switches come from the environment (set
them as the arm line does).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.sp4_why --run <run dir> --instance 0 --episode 0 \
        --frames 1958630:1958640,1960000:1960005 [--out why.json]
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import random
from pathlib import Path

import numpy as np

from ssbot.knowledge import kinematics as kin

CLAPPER = "Song Heavy Sentry"


def _row_kind(cmd_row: np.ndarray, n: int = 12) -> str:
    c = np.asarray(cmd_row[:n], np.int64)
    if (c & kin.B_JUMP).any():
        return "jump"
    if (c & kin.B_DASH).any():
        return "dash"
    return "ground"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--episode", type=int, default=0)
    ap.add_argument("--frames", required=True, help="f0:f1[,f0:f1...] (STATE frames, inclusive)")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    from ssbot.record.recorder import RecordingReader
    from ssbot.train.encounters import ENCOUNTERS
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy
    wins = [tuple(int(v) for v in w.split(":")) for w in a.frames.split(",")]
    rows = [json.loads(x) for x in (a.run / f"attempts_i{a.instance}.jsonl").read_text("utf-8").splitlines() if x]
    row = next(r for r in rows if r.get("episode") == a.episode)
    pol = ForumPlannerPolicy(threads=4, crest="Wanderer", clash="main")
    pol.warmup()
    rd = RecordingReader(row["recording"])
    for _, m in rd.terrain():
        if (m.get("scene_raw") or m.get("scene")) in ("Hang_04", "Hang_04_boss"):
            pol.terrain_msg = m
    pol.reset(random.Random(0), ENCOUNTERS[row["unit"]])
    pol.planner.fcfg.deadline_ms = float("inf")
    pol.planner.fcfg.esc_deadline_ms = float("inf")
    pol.planner.fcfg.clash_deadline_ms = float("inf")
    pol.planner.debug = True
    step0 = pol.sc.step

    def step(*args, **kw):
        r = step0(*args, **kw)
        pol.sc.pq = None
        return r._replace(mask=None, outcome=None) if hasattr(r, "_replace") else \
            dataclasses.replace(r, mask=None, outcome=None)
    pol.sc.step = step
    f_end = max(w[1] for w in wins)
    out = []
    for s in rd.states(row["f_wake"], min(row["f_end"], f_end + 1)):
        f = int(s["f"])
        pol.planner.last_sel = None
        pol.act(s, None)
        if not any(w0 <= f <= w1 for w0, w1 in wins):
            continue
        ls = pol.planner.last_sel
        li = pol.planner.last_info or {}
        dbg = li.get("dbg") or {}
        names = dbg.get("names") or []
        e = next((e for e in s.get("ents") or () if e.get("type_key") == CLAPPER and e.get("pos")), None)
        st = None
        for m in (e or {}).get("fsms") or ():
            if m.get("name") == "Control":
                st = m.get("state")
        h = s.get("hero") or {}
        b = h.get("box")
        hx = 0.5 * (b[0] + b[2]) if b else h["pos"][0]
        face = 1 if (e or {}).get("flipX") else -1
        rec = {"f": f, "st": st, "x": None if e is None else round((hx - float(e["pos"][0])) * face, 2),
               "hero_clip": str((h.get("anim") or {}).get("clip")), "plan": getattr(pol.planner_last, "name", None),
               "goal_why": pol.tac.last.get("goal_why"), "esc": {k: v for k, v in (li.get("esc") or {}).items()
                                                                   if k in ("fail", "checked", "why", "unsafe")}}
        if ls is not None:
            nh = np.asarray(ls["nh"], float)
            J = np.asarray(ls["J"], float)
            safe = np.asarray(ls["safe"], bool)
            keys = {k: np.asarray(ls[k]) for k in ("hz", "hz_soft", "S", "U", "keep", "allowed")}
            cmd = np.asarray(ls["cmd"])
            i = int(ls.get("chosen", ls["first"]))
            kinds = [_row_kind(cmd[j]) for j in range(len(cmd))]

            def desc(j):
                return {"i": j, "name": names[j] if j < len(names) else None, "kind": kinds[j],
                        "nh": round(float(nh[j]), 2), "J": round(float(J[j]), 2), "safe": bool(safe[j]),
                        **{k: bool(v[j]) for k, v in keys.items()}}
            rec["chosen"] = desc(i)
            rec["first"] = desc(int(ls["first"]))
            for kind in ("ground", "jump", "dash"):
                idx = [j for j in range(len(cmd)) if kinds[j] == kind and keys["allowed"][j]]
                if not idx:
                    continue
                best = max(idx, key=lambda j: (bool(safe[j]), float(nh[j]), float(J[j])))
                rec[f"best_{kind}"] = desc(best)
                rec[f"n_{kind}"] = {"allowed": len(idx), "safe": int(sum(bool(safe[j]) for j in idx)),
                                    "hz": int(sum(bool(keys['hz'][j]) for j in idx)),
                                    "S": int(sum(bool(keys['S'][j]) for j in idx)),
                                    "U": int(sum(bool(keys['U'][j]) for j in idx)),
                                    "nh>0": int(sum(float(nh[j]) > 0 for j in idx)),
                                    "safe&nh>0": int(sum(bool(safe[j]) and float(nh[j]) > 0 for j in idx))}
        out.append(rec)
        print(json.dumps(rec), flush=True)
    if a.out is not None:
        a.out.write_text("".join(json.dumps(r) + "\n" for r in out), "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
