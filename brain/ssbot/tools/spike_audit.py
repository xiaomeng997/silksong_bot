"""Down-spike execution audit: every down spike the bot executed in a recorded run, against the plan that pressed it
(the planner replayed open loop on the recording, which reproduces the live decisions with the same code), and every
accepted pogo chain that never reached its press, with what replaced it.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.spike_audit C:/ssbot/data/runs/m2/<run> [--instance 0] [--episodes 6]

Per executed spike (hero clip DownSpike after DownSpike Antic): the press frame (down + attack edge of the latched
mask), the antic and spike frames, the plan's predicted hero box and boss box at the spike's first frame against the
recorded ones, whether the recorded DOWN box met the boss's recorded colliders in the spike frames (a geometric hit),
and the jump hold that was latched before it. Per chosen pogo plan that did not reach its press: the tick it was
replaced, by what, and the carried plan's S / J beside the replacement's (from the planner's alternatives).
"""
import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

import numpy as np


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path)
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--episodes", type=int, default=6)
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    from ssbot.combat import planner as pl
    from ssbot.ipc.framing import BIT
    from ssbot.knowledge.kinematics import Terrain2D
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.postmortem import episode_rows, find_recording
    from ssbot.train.encounters import BELL_BEAST
    from ssbot.train.planner_policy import PlannerPolicy
    D, A, J = (1 << BIT[k] for k in ("down", "attack", "jump"))
    rows = episode_rows(a.run, a.instance)
    pol = PlannerPolicy(view="oracle", threads=4)
    spikes, dropped = [], []
    why = Counter()

    def anim(s):
        return str(((s.get("hero") or {}).get("anim") or [""])[0] if isinstance((s.get("hero") or {}).get("anim"),
                                                                                (list, tuple))
                   else (s.get("hero") or {}).get("anim"))

    def boss_box(s):
        b = next((e for e in s.get("ents") or () if e.get("type_key") == "Bone Beast"), None)
        vs = [np.asarray(c["verts_world"], float).reshape(-1, 2) for c in (b or {}).get("colliders") or ()
              if c.get("enabled")]
        return vs

    for row in rows[:a.episodes]:
        if not row.get("recording") or row.get("outcome") == "HARNESS_FAIL":
            continue
        r = RecordingReader(find_recording(a.run, row))
        for _, m in r.terrain():
            if m.get("scene_raw") == BELL_BEAST.scene:
                pol.terrain = Terrain2D.from_message(m, pol.params.scene(BELL_BEAST.scene))

        class Tap:
            wake_frame = row.get("f_wake")
        pol.reset(random.Random(row["seed"]), BELL_BEAST)
        states = list(r.states(row["f_end"] - row["acts"], row["f_end"]))
        by_f = {s["f"]: s for s in states}
        ticks = {}
        pend = None                                      # (tick f, press frame, name)
        for s in states:
            pol.act(s, Tap)
            res = pol.planner_last
            if res is None:
                continue
            f = s["f"]
            fo = pol.forecasts[-1][0] if pol.forecasts else f
            ticks[f] = (fo, res.name, res.path, res.alternatives, res.S, res.J, pol.forecasts[-1][1] if pol.forecasts
                        else None)
            if pend is not None and f + 2 >= pend[1]:
                why["chains reached their press"] += 1
                pend = None                              # reached the press
            if pend is not None and res.name != "CONTINUE":
                cont = next((x for x in res.alternatives if x[0] == "CONTINUE"), None)
                dropped.append({"f": pend[0], "press": pend[1], "plan": pend[2], "replaced_at": f, "by": res.name,
                                "by_S": res.S, "by_J": round(res.J, 2), "carried": cont})
                why["carried unsafe (S)" if cont and cont[1] else ("carried not in top 6" if cont is None else
                                                                   "outscored by >= margin")] += 1
                pend = None
            pgl = pol.planner.pogo_log
            st_now = pol.fc.tracker.state
            if st_now in ("Charge Emerge", "Charge Antic", "Charge"):
                why["charge ticks"] += 1
                why["charge ticks with pogo candidates"] += int(pgl.get("generated", 0) > 0)
                why["charge ticks with an accepted pogo"] += int(pgl.get("accepted", 0) > 0)
                why["charge ticks on the long set"] += int(res.n < 300)
            if pl._is_macro(res.name):
                why["macro plan ticks"] += 1
            if pl._is_macro(res.name) and pend is None:
                why["macro chains started"] += 1
                cmd = res.cmd if res.cmd is not None else np.zeros(0)
                dn = np.flatnonzero((cmd & D) != 0) if len(cmd) else []
                if len(dn):
                    pend = (f, f + 2 + int(dn[0]), res.name)
        # executed spikes
        prev = ""
        for i, s in enumerate(states):
            an = anim(s)
            if "DownSpike" in an and "Antic" not in an and "Antic" in prev and "DownSpike" in prev:
                fs = s["f"]
                fa = next((states[j]["f"] for j in range(i - 1, max(0, i - 20), -1) if "Antic" not in anim(states[j])
                           and "DownSpike" not in anim(states[j])), fs - 6) + 1
                press = next((states[j]["f"] for j in range(i - 1, max(0, i - 30), -1)
                              if ((states[j].get("act") or {}).get("mask", 0) & (D | A)) == (D | A)
                              and not ((states[j - 1].get("act") or {}).get("mask", 0) & A)), None)
                hold = sum(1 for j in range(max(0, i - 40), i) if (states[j].get("act") or {}).get("mask", 0) & J)
                tick = None if press is None else ticks.get(press - 2)
                rec = {"spike_f": fs, "antic_f": fa, "press_f": press, "jump_frames_held_before": hold}
                hb = s["hero"]["box"]
                bv = boss_box(s)
                if bv:
                    flat = np.concatenate(bv)
                    st = np.cumsum([0] + [len(q) for q in bv]).astype(np.int64)
                    face = 1 if (s["hero"].get("facing") or 1) >= 0 else -1
                    geo = False
                    for k in range(0, 8):
                        sk = by_f.get(fs + k)
                        if sk is None:
                            continue
                        b2 = boss_box(sk)
                        if not b2:
                            continue
                        h2 = sk["hero"]["box"]
                        cx, cy = 0.5 * (h2[0] + h2[2]), 0.5 * (h2[1] + h2[3])
                        g = pl.DOWN
                        x0, x1 = (cx + g[0], cx + g[1]) if face > 0 else (cx - g[1], cx - g[0])
                        f2 = np.concatenate(b2)
                        s2 = np.cumsum([0] + [len(q) for q in b2]).astype(np.int64)
                        geo |= bool(pl._rect_meets_polys(x0, cy + g[2], x1, cy + g[3], f2, s2, 0.0, 0.0))
                    rec["geometric_hit"] = geo
                    rec["boss_box_actual"] = [round(float(flat[:, 0].min()), 2), round(float(flat[:, 1].min()), 2),
                                              round(float(flat[:, 0].max()), 2), round(float(flat[:, 1].max()), 2)]
                rec["hero_box_actual"] = [round(v, 2) for v in hb[:4]]
                if tick is not None:
                    fo, name, path, _alts, S_, J_, fcast = tick
                    rec["plan"] = name
                    k = fs - fo
                    if path is not None and 0 <= k < len(path):
                        rec["hero_box_planned"] = [round(float(v), 2) for v in path[k]]
                    if fcast is not None:
                        bb, okb = fcast.boss_box(np.array([k * pol.params.frame_time]))
                        rec["boss_box_planned"] = [round(float(v), 2) for v in bb[0]] if okb[0] else None
                spikes.append(rec)
            prev = an
    out = {"spikes": len(spikes), "geometric_hits": sum(1 for x in spikes if x.get("geometric_hit")),
           "with_plan": sum(1 for x in spikes if "plan" in x), "pogo_plans_dropped": len(dropped),
           "dropped_why": dict(why), "dropped_by": dict(Counter(d["by"].split("+")[0] for d in dropped).most_common(6)),
           "spike_plans": dict(Counter(str(x.get("plan", "")).split("+")[0] for x in spikes)),
           "spike_boss_dx": [round(abs(0.5 * (x["boss_box_planned"][0] + x["boss_box_planned"][2])
                                       - 0.5 * (x["hero_box_actual"][0] + x["hero_box_actual"][2])), 1)
                             for x in spikes if x.get("boss_box_planned")],
           "spike_cases": spikes[:4], "dropped_cases": dropped[:6]}
    print(json.dumps(out, indent=1, default=str))
    if a.json:
        a.json.write_text(json.dumps(out, indent=1, default=str), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
