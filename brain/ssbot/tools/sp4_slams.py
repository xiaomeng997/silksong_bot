"""Every slam of live 1v1 runs, the declined ones in detail (task 1v1 SP4, forum.md 68): the playbook's keys or not
(slam_play_live.slams_of), and per slam the hero's x from the Clapper's CURRENT centre (+ = in front, the side it
faces; u, centre to centre) at the antic entry, at Slam 0, at the Slam 2 entry, the nearest in front during Slam 2
(Slam Collider 2 reaches 7.76 u in front of its centre at her height), at the Slam Recover entry; the hero's landed hits
from the Slam 2 entry to the slam's end + 30 frames (the after-the-hammer strike) and in the whole slam; HP lost in the
slam and the 60 frames after (source, state); the game stalls (STATE dt > 2.5 frames at time scale ~1) in the slam.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.sp4_slams --manifest C:/ssbot/sandbox/1v1sp4t1_manifest.txt \
        [--arms sp4aft,sp4] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from ssbot.combat import slam_play as sp
from ssbot.record.recorder import RecordingReader
from ssbot.tools.slam_play_live import manifest, pct

AFTER_HIT_F = 30
HP_AFTER_F = 60


def _x(s: dict, e: dict | None, face: int) -> float | None:
    if e is None or not (s.get("hero") or {}).get("box"):
        return None
    return round((sp.hero_x(s) - float(e["pos"][0])) * face, 3)


def slams(states: list[dict]) -> list[dict]:
    out = []
    i, n = 0, len(states)
    while i < n:
        s = states[i]
        e = sp.clapper(s)
        st = sp.control(e)[0]
        if st != "Slam Antic" or (i > 0 and sp.control(sp.clapper(states[i - 1]))[0] == "Slam Antic"):
            i += 1
            continue
        face = 1 if e.get("flipX") else -1
        hp0 = int((s.get("hero") or {}).get("health") or 0)
        row = {"f": s["f"], "x_antic": _x(s, e, face), "ground": sp.on_ground(s), "x_s0": None, "x_s2": None,
               "s2_min": None, "x_rec": None, "hits_slam": 0, "hits_after": 0, "hp": [], "stalls": [],
               "played": False, "end_f": None}
        prev_mask = 0
        jump = press = None
        end_j = None
        j = i
        while j < n:
            s2 = states[j]
            e2 = sp.clapper(s2)
            st2 = sp.control(e2)[0]
            act = int((s2.get("act") or {}).get("mask") or 0)
            rise = act & ~prev_mask
            prev_mask = act
            k = s2["f"] - s["f"]
            if jump is None and rise & sp.M_J and 15 <= k <= 40:
                jump = k
            if jump is not None and press is None and rise & sp.M_A and act & sp.M_D and k <= 60:
                press = k
            if st2 == "Slam 0" and row["x_s0"] is None:
                row["x_s0"] = _x(s2, e2, face)
            if st2 == "Slam 2":
                x2 = _x(s2, e2, face)
                if row["x_s2"] is None:
                    row["x_s2"] = x2
                if x2 is not None and x2 > 0:
                    row["s2_min"] = x2 if row["s2_min"] is None else min(row["s2_min"], x2)
            if st2 == "Slam Recover" and row["x_rec"] is None:
                row["x_rec"] = _x(s2, e2, face)
            dt, ts = float(s2.get("dt") or 0.0), float(s2.get("ts") or 0.0)
            if ts > 0.5 and dt > 2.5 / 60 * ts:
                row["stalls"].append([k, round(dt * 60 / ts, 1)])
            after_s2 = (row["x_s2"] is not None or st2 == "Slam Recover") and (end_j is None or j - end_j <= AFTER_HIT_F)
            for ev in s2.get("ev") or ():
                d = ev.get("d") or {}
                if ev.get("k") == "hit" and d.get("type_key") == sp.CLAPPER and (d.get("dealt") or 0) > 0:
                    if end_j is None:
                        row["hits_slam"] += 1
                    if after_s2:
                        row["hits_after"] += 1
                elif ev.get("k") == "hp" and (d.get("delta") or 0) < 0:
                    row["hp"].append({"k": k, "src": str(d.get("source"))[-28:], "st": st2,
                                      "x": _x(s2, e2, face), "after": end_j is not None})
            if end_j is None and k > 5 and st2 not in sp.SLAM_STATES:
                end_j = j
                row["end_f"] = s2["f"]
            if end_j is not None and j - end_j >= max(AFTER_HIT_F, HP_AFTER_F):
                break
            if e2 is None:
                break
            j += 1
        # hits after the slam's end: only the first AFTER_HIT_F frames count as the after-hammer strike
        row["played"] = press is not None
        row["k_jump"], row["k_press"] = jump, press
        row["hp0"] = hp0
        out.append(row)
        i = max(i + 1, (end_j or i + 1))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", action="append", required=True)
    ap.add_argument("--arms", default="")
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    arms = set(x for x in a.arms.split(",") if x)
    per = defaultdict(list)
    for arm, inst, run in manifest(a.manifest, arms):
        p = run / f"attempts_i{inst}.jsonl"
        if not p.exists():
            continue
        for line in p.read_text("utf-8").splitlines():
            if not line.strip():
                continue
            att = json.loads(line)
            S = list(RecordingReader(att["recording"]).states(att["f_wake"], att["f_end"]))
            for r in slams(S):
                r.update(arm=arm, run=run.name, inst=inst, ep=att["episode"])
                per[arm].append(r)
    summ = {}
    for arm, R in per.items():
        dec = [r for r in R if not r["played"]]
        ply = [r for r in R if r["played"]]
        c = Counter()
        for r in R:
            for h in r["hp"]:
                c[("after " if h["after"] else "") + h["src"]] += 1
        summ[arm] = {
            "slams": len(R), "played": len(ply), "declined": len(dec),
            "hits_slam_per_slam": round(sum(r["hits_slam"] for r in R) / max(1, len(R)), 3),
            "declined_hits_after_per_slam": round(sum(r["hits_after"] for r in dec) / max(1, len(dec)), 3),
            "declined_hits_slam_per_slam": round(sum(r["hits_slam"] for r in dec) / max(1, len(dec)), 3),
            "declined_x_s0": pct([r["x_s0"] for r in dec]), "declined_x_s2": pct([r["x_s2"] for r in dec]),
            "declined_s2_min_front": pct([r["s2_min"] for r in dec]), "declined_x_rec": pct([r["x_rec"] for r in dec]),
            "declined_fled_s0_gt9": sum(1 for r in dec if (r["x_s0"] or 0) > 9),
            "hp_hits_in_slam": sum(1 for r in R for h in r["hp"] if not h["after"]),
            "hp_hits_after_slam": sum(1 for r in R for h in r["hp"] if h["after"]),
            "hp_src": dict(c), "stalls": sum(len(r["stalls"]) for r in R),
            "declined_hp": [[r["run"][9:15], r["inst"], r["ep"], r["x_antic"], r["x_s0"], r["x_s2"], r["s2_min"],
                             r["hp"]] for r in dec if r["hp"]],
        }
        print(arm, json.dumps(summ[arm]))
    if a.json:
        a.json.write_text(json.dumps({"summary": summ, "slams": per}, indent=0), "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
