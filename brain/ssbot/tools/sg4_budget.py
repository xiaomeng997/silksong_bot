"""Task 1v1 SG4 part 1: the hit budget of the Clapper 1v1 per Clapper state family (forum.md 59). Offline, from the
2026-10-12 live runs of the arm rn (C:/ssbot/data/m2_live_g, 16 episodes).

Per episode the fight runs from the wave's activation (the attempt row's f_wake) to the kill (f_kill); the entry
(Drop / Roar) counts as "other". Per frame: the Clapper's family (its Control state; an attack family starts at its antic state
(gauntlet_tables FORUM_SPECS attack_starts) and lasts until the next decision state; decision states = idle / walk),
the hero's distance (box centre to the Clapper's centre, horizontal, u), airborne (cstate onGround false), the
landed hits (the hero's own `hit` events with damage, forum_remaining_hits rule) by attack (down slash / slash).

The rough ceiling per family: a slash press every 19 frames (the Wanderer's shortest press interval) during the frames
in which a standing hero at STANCE_U from the Clapper's centre (front or behind; the landed ground slashes' p50)
touches no recorded damage collider of any entity in that frame and the next 12
(a 0.2 s reaction): 60 / 19 x the safe share. "as played": the same press rate over the frames the hero actually was
within REACH_U of the centre on the ground or in the air.

    ../scripts/uv.cmd run python -m ssbot.tools.sg4_budget [--out C:/ssbot/data/m2_map/sg4]
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

RUNS = Path("C:/ssbot/data/runs/m2")
LIVE = Path("C:/ssbot/data/m2_live_g/col/eps")
OUT = Path(r"C:\ssbot\data\m2_map\sg4")
CLAPPER = "Song Heavy Sentry"
PRESS_F = 19                  # the Wanderer's shortest slash press interval (frames)
STANCE_U = 4.5                # a slash stance (centre to centre): the p50 of the landed ground slashes (4.6 u)
REACH_U = 5.4                 # in slash reach (centre to centre, horizontal): the farthest landed ground slash
LOOK_F = 12                   # the safe stance must stay clear this many frames ahead (0.2 s)
FAMILIES = ("idle_walk", "evade", "cast", "slam", "jump_slam", "jump_cast", "other")
FAM_OF = {"CC_SLAM": "slam", "CC_JUMP": "jump_slam", "CC_CAST": "cast", "CC_JUMP_CAST": "jump_cast",
          "CC_EVADE": "evade", "CC_ENTRY": "other"}


def episodes(arm: str) -> list[dict]:
    out = []
    for p in sorted(LIVE.glob(f"g_{arm}_*.json")):
        d = json.loads(p.read_text("utf-8"))["episode"]
        out.append(d)
    return out


def attempt_row(run: str, inst: int, ep: int) -> dict:
    p = RUNS / run / f"attempts_i{inst}.jsonl"
    for x in p.read_text("utf-8").splitlines():
        if x.strip():
            r = json.loads(x)
            if int(r.get("episode", -1)) == ep:
                return r
    return {}


def analyse(e: dict) -> dict:
    from ssbot.knowledge.gauntlet_tables import FORUM_SPECS
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.forum_demo import HERO_ATTACKS
    from ssbot.tools.forum_remaining_hits import compact_frames, fsm_timeline
    spec = FORUM_SPECS[CLAPPER]
    row = attempt_row(e["run"], int(e["inst"]), int(e["ep"]))
    rd = RecordingReader(row["recording"])
    f0, f1 = int(row["f_wake"]), int(row["f_kill"] or row["f_end"])
    fr = compact_frames(rd.states(f0, f1), fsm_timeline(rd, f0, f1))
    fam, cur = [], "other"
    started = False
    rows = []
    for x in fr:
        cl = next((t for t in x["ents"] if t[1] == CLAPPER and t[10]), None)
        st = cl[6] if cl else None
        if st in spec.attack_starts:
            cur = FAM_OF.get(spec.attack_starts[st], "other")
        elif st in spec.decision_states:
            cur = "evade" if st == "After Scuttle" and cur == "evade" else "idle_walk"
            started = True
        elif st in spec.dormant or st is None:
            cur = cur if started else "other"
        if not started and st not in spec.decision_states:
            f_cur = "other"
        else:
            f_cur = cur
        b = x["box"]
        hx = 0.5 * (b[0] + b[2]) if b else np.nan
        dist = abs(hx - cl[2]) if (cl and b) else np.nan
        air = not x["fl"].get("onGround", True) if x["fl"] else False
        landed, kinds = 0, []
        for k, d in x["ev"]:
            if k == "hit" and d.get("src") in HERO_ATTACKS:
                dealt = d.get("dealt", d.get("amount"))
                if dealt is None or float(dealt) > 0:
                    landed += 1
                    kinds.append("down" if "Down" in str(d.get("src")) else "slash")
        dmg = [bb for t in x["ents"] for (_, bb) in t[8]]
        rows.append({"f": x["f"], "fam": f_cur, "st": st, "dist": dist, "air": air, "landed": landed, "kinds": kinds,
                     "cx": cl[2] if cl else np.nan, "box": b, "dmg": dmg})
    # the safe stance per frame: a ground hero box at +-3 u touches no damage box now and in the next LOOK_F frames
    hb = [r["box"] for r in rows if r["box"] and not r["air"]]
    hw = float(np.median([b[2] - b[0] for b in hb])) if hb else 0.46
    hh = float(np.median([b[3] - b[1] for b in hb])) if hb else 1.3
    yb = float(np.median([b[1] for b in hb])) if hb else 0.0
    n = len(rows)
    safe_side = np.zeros((n, 2), bool)
    for i, r in enumerate(rows):
        if not np.isfinite(r["cx"]):
            continue
        for si, sgn in enumerate((-1, 1)):
            x0 = r["cx"] + sgn * STANCE_U - 0.5 * hw
            x1 = x0 + hw
            ok = True
            for j in range(i, min(n, i + LOOK_F + 1)):
                for bb in rows[j]["dmg"]:
                    if bb[0] < x1 and bb[2] > x0 and bb[1] < yb + hh and bb[3] > yb:
                        ok = False
                        break
                if not ok:
                    break
            safe_side[i, si] = ok
    for i, r in enumerate(rows):
        r["safe"] = bool(safe_side[i].any())
        del r["box"], r["dmg"]
    # slams: the number of slam antic entries
    n_slam = sum(1 for a, b in zip(rows[:-1], rows[1:]) if b["st"] == "Slam Antic" and a["st"] != "Slam Antic")
    return {"run": e["run"], "ep": int(e["ep"]), "inst": int(e["inst"]), "f0": f0, "f_kill": row.get("f_kill"),
            "kill_s": row.get("kill_s"), "ingame_s": row.get("ingame_s"), "hits_taken": row.get("hits"),
            "rows": rows, "slams": n_slam}


def table(eps: list[dict]) -> dict:
    agg = defaultdict(lambda: defaultdict(float))
    tot_f, tot_l = 0, 0
    for e in eps:
        for r in e["rows"]:
            a = agg[r["fam"]]
            a["frames"] += 1
            a["landed"] += r["landed"]
            a["down"] += sum(1 for k in r["kinds"] if k == "down")
            a["air"] += r["air"]
            a["safe"] += r["safe"]
            if np.isfinite(r["dist"]):
                a["dist_n"] += 1
                a["dist_sum"] += r["dist"]
                a["reach"] += r["dist"] <= REACH_U
                a.setdefault("dists", [])
            tot_f += 1
            tot_l += r["landed"]
    dists = defaultdict(list)
    hit_d = defaultdict(list)
    for e in eps:
        for r in e["rows"]:
            if np.isfinite(r["dist"]):
                dists[r["fam"]].append(r["dist"])
            if r["landed"] and np.isfinite(r["dist"]):
                hit_d["down" if "down" in r["kinds"] else ("slash_air" if r["air"] else "slash_ground")].append(r["dist"])
    out = {"fight_s": round(tot_f / 60, 1), "landed": tot_l, "hits_per_s": round(tot_l / (tot_f / 60), 3), "fam": {},
           "landed_dist_p10_50_90_max": {k: [round(float(np.quantile(v, q)), 2) for q in (0.1, 0.5, 0.9, 1.0)] + [len(v)]
                                         for k, v in hit_d.items()}}
    for fm in FAMILIES:
        a = agg.get(fm)
        if not a or not a["frames"]:
            continue
        s = a["frames"] / 60
        d = np.array(dists[fm]) if dists[fm] else np.array([np.nan])
        out["fam"][fm] = {
            "time_s": round(s, 1), "time_share": round(a["frames"] / tot_f, 3),
            "dist_p10_50_90": [round(float(np.nanquantile(d, q)), 2) for q in (0.1, 0.5, 0.9)],
            "air_share": round(a["air"] / a["frames"], 3),
            "landed": int(a["landed"]), "landed_down": int(a["down"]), "hits_per_s": round(a["landed"] / s, 3),
            "landed_share": round(a["landed"] / max(tot_l, 1), 3),
            "in_reach_share": round(a["reach"] / a["frames"], 3),
            "safe_stance_share": round(a["safe"] / a["frames"], 3),
            "ceiling_hits_per_s_safe": round(60 / PRESS_F * a["safe"] / a["frames"], 2),
            "ceiling_hits_per_s_as_played": round(60 / PRESS_F * a["reach"] / a["frames"], 2),
            "ceiling_hits_safe": round(a["safe"] / PRESS_F, 1)}
    return out


def scenarios(res: dict, n_slam: int) -> dict:
    """Overall hits / s = sum over the families of time share x rate, at today's time shares (the Clapper's choices
    depend on the hero's distance, so the shares would move; rough). The slam map's closed loop gives 1.13 (SG3b dense)
    to 2 (a hop / bounce start) strikes per slam; a slam lasts the family's time / slams."""
    fam = res["fam"]
    sh = {k: v["time_share"] for k, v in fam.items()}
    rate = {k: v["hits_per_s"] for k, v in fam.items()}
    slam_s = fam["slam"]["time_s"] / max(n_slam, 1)

    def tot(r):
        return round(sum(sh[k] * r[k] for k in sh), 3)
    out = {"today": tot(rate), "slam_s_per_slam": round(slam_s, 2)}
    for nm, per in (("slam_map_1.13", 1.13), ("slam_map_2.0", 2.0)):
        r = dict(rate, slam=per / slam_s)
        out[nm] = {"slam_rate": round(per / slam_s, 3), "total": tot(r)}
        need = 1.5 - (tot(r) - sh["idle_walk"] * r["idle_walk"])
        out[nm]["idle_walk_rate_needed_for_1.5"] = round(need / sh["idle_walk"], 2)
        r2 = {k: max(rate[k], 0.7 * fam[k]["ceiling_hits_per_s_safe"]) for k in rate}
        r2["slam"] = per / slam_s
        out[nm]["others_at_70pct_safe_ceiling"] = tot(r2)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="rn")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    eps = [analyse(e) for e in episodes(a.arm)]
    res = table(eps)
    n_slam = sum(e["slams"] for e in eps)
    res["episodes"] = len(eps)
    res["slams"] = n_slam
    res["slams_per_min"] = round(n_slam / (res["fight_s"] / 60), 2)
    sl = res["fam"].get("slam", {})
    res["slam_hits_per_slam"] = round(sl.get("landed", 0) / max(n_slam, 1), 3)
    res["per_episode"] = [{"run": e["run"], "ep": e["ep"], "kill_s": e["kill_s"], "hits_taken": e["hits_taken"],
                           "slams": e["slams"],
                           "fight_s": round(len(e["rows"]) / 60, 1),
                           "landed": sum(r["landed"] for r in e["rows"])} for e in eps]
    res["scenarios"] = scenarios(res, n_slam)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "budget.json").write_text(json.dumps(res, indent=1, default=float), "utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "per_episode"}, indent=1, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
