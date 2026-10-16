"""The person's key timeline per Clapper slam (task 1v1 SP1 step 1, forum.md 65.1) from the demo's compact frames
(C:/ssbot/data/m2_map/human_1015/fights.pkl, made by that folder's extract.py from 20261015_193525 / 194816; read
only). The demo ran at 0.5x: the frames here are game frames (game time x 60) from the antic entry (k = 0 at the start of
the step whose transition entered Slam Antic), so half frames occur.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.sp1_human_keys [--pkl ...] [--out C:/ssbot/data/m2_play/human_keys.json]

Per slam: the stage entries, the hero's x at the antic entry (centre to centre, + = in front: the side the Clapper
faces), on the ground or not, the direction key per frame (toward / away / none relative to the Clapper's current
side), the jump press / release, the down press, the attack press (down / side / up) with x then, the contact (a hit
on the Clapper by a DownSlash), the damage taken, the dash and jump presses after the down press, the landing side.
Prints the summary over the down strikes that landed.
"""
from __future__ import annotations

import argparse
import json
import math
import pickle
from collections import Counter
from pathlib import Path

import numpy as np

B_JUMP, B_ATK, B_DASH = 1, 2, 4
B_UP, B_DOWN, B_L, B_R = 1 << 18, 1 << 19, 1 << 20, 1 << 21
STAGES = ("Slam Antic", "Slam 0", "Slam 1", "Slam Effects?", "Slam 2", "Slam Recover")


def pct(v, qs=(10, 50, 90)):
    v = [x for x in v if x is not None]
    return [round(float(np.percentile(v, q)), 2) for q in qs] if v else None


def slams(D: list) -> list[dict]:
    out = []
    for d in D:
        R, fg = d["rows"], d["fight"]
        trans = [(i, e[1], e[2]) for i, r in enumerate(R) for e in r["ev"] if e[0] == "fsm"]
        for j, (ie, _, to) in enumerate(trans):
            if to != "Slam Antic" or R[ie]["cl"] is None:
                continue
            Te = R[ie]["T"] - R[ie]["dt"]
            stages, nxt = [("Slam Antic", ie)], None
            for (i2, _, t2) in trans[j + 1:]:
                if t2 in STAGES:
                    stages.append((t2, i2))
                else:
                    nxt = (t2, i2)
                    break
            ent = {a: round((R[i]["T"] - R[i]["dt"] - Te) * 60, 1) for a, i in stages}
            end_i = nxt[1] if nxt else min(len(R) - 1, ie + 400)
            cl0 = R[ie]["cl"]
            face = 1 if cl0["flip"] else -1
            cx0 = cl0["pos"][0]

            def k_of(i):
                return (R[i]["T"] - Te) * 60

            lo = ie
            while lo > 0 and k_of(lo) > -20:
                lo -= 1
            rows = []
            for i in range(lo, min(len(R), end_i + 160)):
                r = R[i]
                c = r["cl"]
                cx = c["pos"][0] if c else cx0
                side = 1 if (r["pos"][0] - cx) * face >= 0 else -1
                w = (1 if r["mask"] & B_R else 0) - (1 if r["mask"] & B_L else 0)
                rows.append({"k": k_of(i), "m": r["mask"], "dir": w * face * side, "g": r["ground"],
                             "x": (r["pos"][0] - cx0) * face, "xc": (r["pos"][0] - cx) * face, "ev": r["ev"]})
            evs = []
            prev = R[lo - 1]["mask"] if lo > 0 else 0
            for rr in rows:
                m = rr["m"]
                rise, fall = m & ~prev, prev & ~m
                prev = m
                k = round(rr["k"], 2)
                if rise & B_JUMP:
                    evs.append(["jump_on", k, rr["g"]])
                if fall & B_JUMP:
                    evs.append(["jump_off", k])
                if rise & B_ATK:
                    evs.append(["atk", k, "down" if m & B_DOWN else ("up" if m & B_UP else "side"), rr["g"],
                                round(rr["xc"], 3)])
                if rise & B_DASH:
                    evs.append(["dash", k])
                if rise & B_DOWN:
                    evs.append(["down_on", k])
                for e in rr["ev"]:
                    if e[0] == "hit" and e[2] == "Song Heavy Sentry":
                        evs.append(["hit", k, str(e[3])])
                    if e[0] == "hp":
                        evs.append(["hp", k, e[1], str(e[2])[-28:]])
            dirs = {}
            for rr in rows:
                dirs.setdefault(math.floor(rr["k"]), Counter())[rr["dir"]] += 1
            seg = []
            for kb in sorted(dirs):
                c = dirs[kb]
                dv = max(c, key=c.get)
                if seg and seg[-1][2] == dv and seg[-1][1] == kb - 1:
                    seg[-1][1] = kb
                else:
                    seg.append([kb, kb, dv])
            atk = next((e for e in evs if e[0] == "atk" and e[2] == "down" and 30 < e[1] < 60), None)
            hit = next((e for e in evs if atk and e[0] == "hit" and "Down" in e[2] and e[1] > atk[1]), None)
            land = next((rr for rr in rows if hit and rr["k"] > hit[1] + 3 and rr["g"]), None)
            out.append({"fight": f"{fg['name']}a{fg['attempt']}", "face": face, "stages": ent,
                        "end": nxt[0] if nxt else None, "x0": round((R[ie]["pos"][0] - cx0) * face, 2),
                        "g0": bool(R[ie]["ground"]), "dir_segments": seg, "events": evs,
                        "land": None if land is None else {"k": round(land["k"], 1), "xc": round(land["xc"], 2)}})
    return out


def strikes(S: list[dict]) -> list[dict]:
    """One row per slam with a down press in the late antic / Slam 0 (k 30-60)."""
    out = []
    for s in S:
        ev = s["events"]
        s0 = s["stages"].get("Slam 0")
        a = next((e for e in ev if e[0] == "atk" and e[2] == "down" and 30 < e[1] < 60), None)
        if a is None:
            continue
        jon = [e for e in ev if e[0] == "jump_on" and 15 < e[1] < a[1]]
        jk = jon[-1][1] if jon else None
        joff = next((e for e in ev if e[0] == "jump_off" and jk is not None and e[1] > jk), None)
        dn = [e for e in ev if e[0] == "down_on" and 25 < e[1] <= a[1] + 0.01]
        hit = next((e for e in ev if e[0] == "hit" and "Down" in e[2] and e[1] > a[1]), None)

        def dirs(k0, k1):
            c = {-1: 0, 0: 0, 1: 0}
            for x0, x1, d in s["dir_segments"]:
                lo, hi = max(x0, k0), min(x1, k1)
                if hi >= lo:
                    c[d] += hi - lo + 1
            return c
        pre = dirs(0, int(jk) - 1) if jk is not None else None
        air = dirs(int(jk), int(a[1])) if jk is not None else None
        out.append({"fight": s["fight"], "x0": s["x0"], "g0": s["g0"], "antic": s0, "jump_k": jk,
                    "hold": None if joff is None else round(joff[1] - jk, 1), "down_k": dn[-1][1] if dn else None,
                    "press_k": a[1], "press_s0": None if s0 is None else round(a[1] - s0, 1), "x_press": a[4],
                    "contact_s0": None if (hit is None or s0 is None) else round(hit[1] - s0, 1),
                    "landed": hit is not None,
                    "hp": [(e[1], e[3]) for e in ev if e[0] == "hp" and a[1] - 5 < e[1] < a[1] + 60],
                    "jump_after_press": sum(1 for e in ev if e[0] == "jump_on" and a[1] < e[1] < a[1] + 50),
                    "dash_after": next((e[1] for e in ev if e[0] == "dash" and a[1] < e[1] < a[1] + 50), None),
                    "toward_pre": None if pre is None else pre[-1], "away_pre": None if pre is None else pre[1],
                    "toward_air": None if air is None else air[-1], "away_air": None if air is None else air[1],
                    "land_xc": None if s["land"] is None else s["land"]["xc"]})
    return out


def summary(T: list[dict]) -> dict:
    ok = [t for t in T if t["landed"]]
    fails = [t for t in T if not t["landed"]]
    xs = np.array([t["x0"] for t in ok if t["jump_k"] is not None])
    jk = np.array([t["jump_k"] for t in ok if t["jump_k"] is not None])
    return {"strikes": len(T), "landed": len(ok), "x0": pct([t["x0"] for t in ok]),
            "jump_k": pct([t["jump_k"] for t in ok]), "hold": pct([t["hold"] for t in ok]),
            "down_lead": pct([t["press_k"] - t["down_k"] for t in ok if t["down_k"] is not None]),
            "press_k": pct([t["press_k"] for t in ok]), "press_s0": pct([t["press_s0"] for t in ok]),
            "x_press": pct([t["x_press"] for t in ok]), "contact_s0": pct([t["contact_s0"] for t in ok]),
            "jump_to_press": pct([t["press_k"] - t["jump_k"] for t in ok if t["jump_k"] is not None]),
            "toward_pre": pct([t["toward_pre"] for t in ok]), "away_pre": pct([t["away_pre"] for t in ok]),
            "toward_air": pct([t["toward_air"] for t in ok]), "away_air": pct([t["away_air"] for t in ok]),
            "jump_after_press": sum(t["jump_after_press"] for t in T),
            "dash_after": [sum(1 for t in ok if t["dash_after"] is not None), pct([t["dash_after"] for t in ok])],
            "land_behind": sum(1 for t in ok if t["land_xc"] is not None and t["land_xc"] < 0),
            "land_front": sum(1 for t in ok if t["land_xc"] is not None and t["land_xc"] > 0),
            "corr_jump_k_x0": None if len(xs) < 3 else round(float(np.corrcoef(xs, jk)[0, 1]), 2),
            "fails": [{k: t[k] for k in ("fight", "x0", "press_k", "press_s0", "x_press", "hp")} for t in fails]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pkl", type=Path, default=Path("C:/ssbot/data/m2_map/human_1015/fights.pkl"))
    ap.add_argument("--out", type=Path, default=Path("C:/ssbot/data/m2_play/human_keys.json"))
    a = ap.parse_args(argv)
    with open(a.pkl, "rb") as fh:
        D = pickle.load(fh)
    S = slams(D)
    T = strikes(S)
    sm = summary(T)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps({"slams": S, "strikes": T, "summary": sm}, indent=0, default=str), "utf-8")
    print(len(S), "slams;", json.dumps(sm, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
