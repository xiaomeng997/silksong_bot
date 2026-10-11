"""Why the 1v1 bot does not swing more (task 1v1, forum.md 44): an episode replayed open loop through the policy (as
forum_policy_replay: the recorded STATEs, the planner plans every tick, its keys are not applied), and per tick the
selection's inputs (ForumPlanner.last_sel): the most landed hits (sc["nh"]) of any allowed row and of the safe rows,
and of the rows with landed hits how many fail each test (S: the range / aim support, env: the envelope, hz: the
hazard rows, ok: not allowed) - per Clapper control state.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.forum_1v1_rows --run <run dir> --instance 0 --episode 0
        [--frames 2400] --out <json>
"""
import argparse
import json
import random
import time
import zlib
from collections import defaultdict
from pathlib import Path

import numpy as np

CLAPPER = "Song Heavy Sentry"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--episode", type=int, default=0)
    ap.add_argument("--frames", type=int, default=2400)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--ticks-out", type=Path, default=None)
    ap.add_argument("--det", action="store_true", help="infinite planner deadlines (decisions independent of speed)")
    a = ap.parse_args(argv)
    import dataclasses
    from ssbot.record.recorder import RecordingReader
    from ssbot.train.encounters import ENCOUNTERS
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy
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
    if a.det:
        pol.planner.fcfg.esc_deadline_ms = float("inf")
        pol.planner.fcfg.clash_deadline_ms = float("inf")
    step0 = pol.sc.step

    def step(*args, **kw):
        r = step0(*args, **kw)
        pol.sc.pq = None
        return r._replace(mask=None, outcome=None) if hasattr(r, "_replace") else \
            dataclasses.replace(r, mask=None, outcome=None)
    pol.sc.step = step
    agg = defaultdict(lambda: defaultdict(float))
    ticks = []
    t0 = time.perf_counter()
    n = 0
    for s in rd.states(row["f_wake"], row["f_end"]):
        if n >= a.frames:
            break
        n += 1
        pol.planner.last_sel = None
        dash0 = getattr(pol.planner.audit, "v2_dash_rows", 0)
        dashu0 = getattr(pol.planner.audit, "v2_dash_unsafe", 0)
        pol.act(s, None)
        ls = getattr(pol.planner, "last_sel", None)
        trk = None
        for tr in (getattr(pol.fc, "trackers", None) or {}).values():
            if not tr.dead and CLAPPER in str(getattr(getattr(tr, "table", None), "type_key", "")) + str(
                    getattr(getattr(getattr(tr, "table", None), "spec", None), "type_key", "")):
                trk = tr
                break
        st = getattr(trk, "state", None) if trk is not None else None
        hero = (s.get("hero") or {}).get("pos") or [0, 0]
        dx = abs(float(hero[0]) - float(trk.pos[0])) if trk is not None and getattr(trk, "pos", None) is not None \
            else None
        if ls is None:
            continue
        nh = np.asarray(ls["nh"], float)
        allowed = np.asarray(ls["allowed"], bool)
        safe = np.asarray(ls["safe"], bool)
        S = np.asarray(ls["S"], bool)
        hz = np.asarray(ls["hz"], bool)
        hit = allowed & (nh > 0)
        key = str(st)
        g = agg[key]
        g["ticks"] += 1
        g["any_hit_row"] += bool(hit.any())
        g["safe_hit_row"] += bool((hit & safe).any())
        g["chosen_nh"] += float(nh[ls["first"]])
        g["max_nh_all"] += float(nh[allowed].max()) if allowed.any() else 0.0
        g["max_nh_safe"] += float(nh[safe].max()) if safe.any() else 0.0
        if hit.any():
            g["hit_rows"] += int(hit.sum())
            g["hit_rows_S"] += int((hit & S).sum())
            g["hit_rows_hz"] += int((hit & hz).sum())
            g["hit_rows_notsafe_other"] += int((hit & ~safe & ~S & ~hz).sum())
        if dx is not None:
            g["dx_sum"] += dx
        if a.ticks_out is not None:
            ticks.append({"f": s["f"], "st": st, "dx": None if dx is None else round(dx, 2),
                          "nh_max": float(nh[allowed].max()) if allowed.any() else 0.0,
                          "nh_safe": float(nh[safe].max()) if safe.any() else 0.0, "nh_ch": float(nh[ls["first"]]),
                          "n_safe": int(safe.sum()), "hit_S": int((hit & S).sum()), "hit": int(hit.sum()),
                          # the margin-mode comparison (forum.md 46.1): the pick and digests of the safe test
                          "first": int(ls["first"]), "plan": getattr(pol.planner_last, "name", None),
                          "mask": int(getattr(pol.planner_last, "mask", 0)),
                          "safe_h": zlib.crc32(np.packbits(safe).tobytes()),
                          "S_h": zlib.crc32(np.packbits(S).tobytes()),
                          "dash": int(pol.planner.audit.v2_dash_rows - dash0),
                          "dash_unsafe": int(pol.planner.audit.v2_dash_unsafe - dashu0),
                          "pick_dash_only": int(ls["first"]) in set(int(x) for x in
                                                                    pol.planner.last_info.get("dash_only", ()))})
    out = {"run": str(a.run), "episode": a.episode, "ticks": n, "s": round(time.perf_counter() - t0, 1),
           "by_state": {k: {kk: (round(vv / v["ticks"], 3) if kk not in ("ticks",) else int(vv))
                            for kk, vv in v.items()} for k, v in sorted(agg.items(), key=lambda z: -z[1]["ticks"])}}
    a.out.write_text(json.dumps(out, indent=1), "utf-8")
    if a.ticks_out is not None:
        a.ticks_out.write_text("".join(json.dumps(t) + "\n" for t in ticks), "utf-8")
    print(json.dumps(out, indent=1)[:5000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
