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
            fc_now = pol.forecasts[-1][1] if pol.forecasts else None
            snap = None
            if fc_now is not None:
                # the forecast's boss box and shape NOW: Forecast.boss_box reads the live tracker, so it must be
                # evaluated at the tick (evaluated after the replay it described the episode's last state)
                bb_all, ok_all = fc_now.boss_box(np.arange(0, 121) * pol.params.frame_time)
                snap = (bb_all, ok_all, *fc_now.body_polys())
            ticks[f] = (fo, res.name, res.path, res.alternatives, res.S, res.J, snap)
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
                b_now = next((e for e in s.get("ents") or () if e.get("type_key") == "Bone Beast"), None)
                rec["boss_state"] = ((b_now or {}).get("fsms") or [{}])[0].get("state")
                # the down attack's hit events carry src "DownSlash" (the attack object) in the event's data
                rec["hit"] = any(str((ev.get("d") or {}).get("src", "")).startswith("Down") for j in range(fa, fs + 14)
                                 for ev in (by_f.get(j) or {}).get("ev") or () if ev.get("k") == "hit")
                rec["hurt_after"] = next((j - fs for j in range(fa, fs + 40)
                                          for ev in (by_f.get(j) or {}).get("ev") or () if ev.get("k") == "damage"),
                                         None)
                bvx = float((b_now or {}).get("vel", [0.0, 0.0])[0])
                face = 1 if (s["hero"].get("facing") or 1) >= 0 else -1
                rec["approach"] = None
                if bv and abs(bvx) > 1.0:
                    bcx = 0.5 * (float(np.concatenate(bv)[:, 0].min()) + float(np.concatenate(bv)[:, 0].max()))
                    ahead = np.sign(bvx) * (0.5 * (hb[0] + hb[2]) - bcx) > 0
                    # the boss coming at the hero: head-on when she faces it, from behind when she faces away
                    rec["approach"] = ("head_on" if face != np.sign(bvx) else "behind") if ahead else "passed"
                if tick is not None:
                    fo, name, path, _alts, S_, J_, fcast = tick
                    rec["plan"] = name
                    k = fs - fo
                    if path is not None and 0 <= k < len(path):
                        rec["hero_box_planned"] = [round(float(v), 2) for v in path[k]]
                    if fcast is not None and 0 <= k < len(fcast[0]):
                        rec["boss_box_planned"] = [round(float(v), 2) for v in fcast[0][k]] if fcast[1][k] else None
                    # the spike's 6 frames, planned against recorded: hero centre height, boss top, the DOWN box's
                    # bottom above the boss top (planned / recorded), the boss's front edge along its motion
                    rows_ = []
                    pc, ac = [], []
                    for j in range(fs, fs + 6):
                        kk = j - fo
                        sj = by_f.get(j)
                        if sj is None or path is None or not 0 <= kk < len(path) or fcast is None                                 or kk >= len(fcast[0]):
                            continue
                        bvj = boss_box(sj)
                        bbj, okj = fcast[0][kk:kk + 1], fcast[1][kk:kk + 1]
                        if not bvj or not okj[0]:
                            continue
                        # contact of the DOWN box: planned hero vs predicted shape, recorded hero vs recorded shape
                        hp_ = path[kk]
                        cxp, cyp = 0.5 * (hp_[0] + hp_[2]), 0.5 * (hp_[1] + hp_[3])
                        g = pl.DOWN
                        x0p, x1p = (cxp + g[0], cxp + g[1]) if face > 0 else (cxp - g[1], cxp - g[0])
                        polys_p, starts_p = fcast[2], fcast[3]
                        if len(polys_p):
                            b0p = (polys_p[:, 0].min(), polys_p[:, 1].min())
                            pc.append(bool(pl._rect_meets_polys(x0p, cyp + g[2], x1p, cyp + g[3], polys_p, starts_p,
                                                                float(bbj[0, 0] - b0p[0]), float(bbj[0, 1] - b0p[1]))))
                        hbr = sj["hero"]["box"]
                        cxa, cya = 0.5 * (hbr[0] + hbr[2]), 0.5 * (hbr[1] + hbr[3])
                        x0a, x1a = (cxa + g[0], cxa + g[1]) if face > 0 else (cxa - g[1], cxa - g[0])
                        fa_ = np.concatenate(bvj)
                        sa_ = np.cumsum([0] + [len(q) for q in bvj]).astype(np.int64)
                        ac.append(bool(pl._rect_meets_polys(x0a, cya + g[2], x1a, cya + g[3], fa_, sa_, 0.0, 0.0)))
                        fl = np.concatenate(bvj)
                        top_a = float(fl[:, 1].max())
                        hbj = sj["hero"]["box"]
                        cy_a, cy_p = 0.5 * (hbj[1] + hbj[3]), 0.5 * float(path[kk][1] + path[kk][3])
                        cx_a, cx_p = 0.5 * (hbj[0] + hbj[2]), 0.5 * float(path[kk][0] + path[kk][2])
                        rows_.append([j - fs, round(cy_p - cy_a, 2), round(float(bbj[0, 3]) - top_a, 2),
                                      round(cy_p + pl.DOWN[2] - float(bbj[0, 3]), 2), round(cy_a + pl.DOWN[2] - top_a, 2),
                                      round(cx_p - cx_a, 2),
                                      round(float(bbj[0, 0] + bbj[0, 2]) * 0.5 - 0.5 * float(fl[:, 0].min()
                                                                                         + fl[:, 0].max()), 2)])
                    # [frame in spike, hero cy planned - recorded, boss top predicted - recorded, DOWN bottom above
                    #  the top planned, recorded, hero cx planned - recorded, boss cx predicted - recorded]
                    rec["spike_rows"] = rows_
                    rec["contact_planned"] = pc
                    rec["contact_recorded"] = ac
                spikes.append(rec)
            prev = an
    out = {"spikes": len(spikes), "geometric_hits": sum(1 for x in spikes if x.get("geometric_hit")),
           "with_plan": sum(1 for x in spikes if "plan" in x), "pogo_plans_dropped": len(dropped),
           "dropped_why": dict(why), "dropped_by": dict(Counter(d["by"].split("+")[0] for d in dropped).most_common(6)),
           "spike_plans": dict(Counter(str(x.get("plan", "")).split("+")[0] for x in spikes)),
           "spike_boss_dx": [round(abs(0.5 * (x["boss_box_planned"][0] + x["boss_box_planned"][2])
                                       - 0.5 * (x["hero_box_actual"][0] + x["hero_box_actual"][2])), 1)
                             for x in spikes if x.get("boss_box_planned")],
           "spike_cases": spikes, "dropped_cases": dropped[:6]}
    # per approach (head-on / from behind / passed) and outcome: medians over the spike's frames of the errors
    summ = {}
    for x in spikes:
        key = f"{x.get('approach')}/{'hit' if x.get('hit') else 'miss'}"
        e = summ.setdefault(key, {"n": 0, "hurt": 0, "rows": []})
        e["n"] += 1
        e["hurt"] += int(x.get("hurt_after") is not None)
        e["planned_contact"] = e.get("planned_contact", 0) + int(any(x.get("contact_planned") or ()))
        e["recorded_contact"] = e.get("recorded_contact", 0) + int(any(x.get("contact_recorded") or ()))
        e["rows"] += x.get("spike_rows") or []
    for key, e in summ.items():
        r = np.asarray(e.pop("rows"), float).reshape(-1, 7)
        if len(r):
            e.update({m: [round(float(np.percentile(r[:, c], p)), 2) for p in (10, 50, 90)]
                      for c, m in ((1, "hero_cy_err"), (2, "boss_top_err"), (3, "down_above_top_planned"),
                                   (4, "down_above_top_recorded"), (5, "hero_cx_err"), (6, "boss_cx_err"))})
    out["by_approach"] = summ
    print(json.dumps(out, indent=1, default=str))
    if a.json:
        a.json.write_text(json.dumps(out, indent=1, default=str), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
