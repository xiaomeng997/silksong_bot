"""Whiff audit of planner runs: every attack and Silkspear press the bot made, whether a hit followed in its active
window, and where the planner predicted the boss's hurtbox at that frame against where it was.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.whiff_audit C:/ssbot/data/runs/m2/<run> [--list 40] [--json out.json]

Needs SSBOT_LOG_ALL=1 decision logs (every tick) with the planner's "attack" record (PlanResult.attack: the chosen
plan's first attack scored as a hit: kind, start frame from the forecast origin, the predicted boss box at its
active frame). A press is the decision whose sent mask (applied at f + 2) newly holds attack or quickcast; the scored
attack belongs to it when its start frame is that press's frame. Its active frame is fo + start + the kind's offset
(side 3, up 5, down spike 8, Silkspear 18 frames: planner.WINDOWS["v2"]); the actual boss box is the
bounding box of the boss's enabled colliders in the recorded STATE of that frame. A hit is a "hit" event on the boss
with the kind's source (Slash / AltSlash, UpSlash, DownSpike*, Needle Damage) within 2 frames after the window.
Presses the planner did not score as hits (no attack record, or one for a later press) are counted apart.
"""
import argparse
import bisect
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

KINDS = {1: "side", 2: "up", 3: "down", 4: "spear"}
OFFSET = {1: 3, 2: 5, 3: 8, 4: 18}
WINDOW = {1: (0, 6), 2: (2, 8), 3: (4, 16), 4: (17, 20)}
SRC = {1: ("Slash", "AltSlash"), 2: ("UpSlash",), 3: ("DownSpike", "DownSlash", "Down"), 4: ("Needle Damage",)}


def _src_ok(kind: int, src: str | None) -> bool:
    return src is not None and any(src.startswith(x) for x in SRC[kind])


def audit(run: Path) -> dict:
    from ssbot.ipc.framing import BIT
    from ssbot.record.recorder import RecordingReader
    A, Q, U, D = (1 << BIT[k] for k in ("attack", "quickcast", "up", "down"))
    rows = []
    for dp in sorted(run.glob("decisions_i*.jsonl")):
        inst = dp.stem.split("_i")[1]
        prev = 0
        presses = []
        for line in dp.open():
            d = json.loads(line)
            m = d.get("mask") or 0
            new = m & ~prev
            prev = m
            if not new & (A | Q):
                continue
            kind = 4 if new & Q else (2 if m & U else (3 if m & D else 1))
            att = d.get("attack")
            scored = bool(att and att[1] <= (d["f"] - d.get("fo", d["f"])) + 2 and att[0] == kind)
            pred = att[2] if scored else None
            fo = d.get("fo", d["f"])
            presses.append({"inst": inst, "ep": d["ep"], "f_press": d["f"] + 2, "kind": kind, "scored": scored,
                            "f_active": (fo + att[1] + OFFSET[kind]) if scored else d["f"] + 2 + OFFSET[kind],
                            "pred": pred, "state": d.get("boss_state")})
        hits = defaultdict(list)
        need = {p["f_active"] for p in presses}
        boss_at: dict[int, list[float]] = {}
        for rec in sorted(run.glob(f"rec/*/*/i{inst}_*")):
            ev_p = rec / "events.jsonl"
            if ev_p.exists():
                for line in ev_p.open():
                    if '"hit"' not in line:
                        continue
                    e = json.loads(line)
                    dd = e.get("data") or {}
                    if e.get("kind") == "hit" and dd.get("type_key") == "Bone Beast":
                        hits["all"].append((e["frame"], dd.get("src")))
            if need:
                r = RecordingReader(rec)
                lo, hi = min(need), max(need)
                for s in r.states(lo, hi + 1):
                    if s["f"] not in need:
                        continue
                    b = next((e for e in s.get("ents") or () if e.get("type_key") == "Bone Beast"), None)
                    if b is None:
                        continue
                    vs = [np.asarray(c["verts_world"], float).reshape(-1, 2) for c in b.get("colliders") or ()
                          if c.get("enabled")]
                    if vs:
                        v = np.concatenate(vs)
                        boss_at[s["f"]] = [float(v[:, 0].min()), float(v[:, 1].min()), float(v[:, 0].max()),
                                           float(v[:, 1].max())]
        hf = sorted(hits["all"])
        frames = [h[0] for h in hf]
        for p in presses:
            w0, w1 = WINDOW[p["kind"]]
            i0 = bisect.bisect_left(frames, p["f_press"] + w0)
            i1 = bisect.bisect_right(frames, p["f_press"] + w1 + 2)
            p["hit"] = any(_src_ok(p["kind"], hf[i][1]) for i in range(i0, i1))
            p["actual"] = boss_at.get(p["f_active"])
            if p["pred"] is not None and p["actual"] is not None:
                pc = (0.5 * (p["pred"][0] + p["pred"][2]), 0.5 * (p["pred"][1] + p["pred"][3]))
                ac = (0.5 * (p["actual"][0] + p["actual"][2]), 0.5 * (p["actual"][1] + p["actual"][3]))
                p["delta"] = [round(ac[0] - pc[0], 2), round(ac[1] - pc[1], 2)]
            rows.append(p)
    by = defaultdict(Counter)
    dx = defaultdict(list)
    for p in rows:
        k = KINDS[p["kind"]]
        by[k]["presses"] += 1
        by[k]["hit"] += p["hit"]
        by[k]["scored"] += p["scored"]
        by[k]["scored_hit"] += p["scored"] and p["hit"]
        if p.get("delta") is not None:
            dx[(k, p["hit"])].append(abs(p["delta"][0]))
    summary = {k: dict(v, hit_rate=round(v["hit"] / v["presses"], 3) if v["presses"] else None,
                       scored_hit_rate=round(v["scored_hit"] / v["scored"], 3) if v["scored"] else None)
               for k, v in by.items()}
    for (k, h), v in dx.items():
        summary[k][f"mean_abs_dx_{'hit' if h else 'whiff'}"] = round(float(np.mean(v)), 2)
    return {"summary": summary, "whiffs": [p for p in rows if p["scored"] and not p["hit"]]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+", type=Path)
    ap.add_argument("--list", type=int, default=20, help="whiffs to print")
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    out = {}
    for run in a.runs:
        res = audit(run)
        out[run.name] = res
        print(run.name)
        print(json.dumps(res["summary"], indent=1))
        for p in res["whiffs"][:a.list]:
            print(f"  whiff {KINDS[p['kind']]:5s} i{p['inst']} ep{p['ep']} f{p['f_press']} {p['state']} pred "
                  f"{p['pred']} actual {p['actual']} delta {p.get('delta')}")
    if a.json:
        a.json.write_text(json.dumps(out, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
