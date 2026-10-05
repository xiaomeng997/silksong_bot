"""The Forum plan's §6.3 metrics over live full-gauntlet runs of ForumPlannerPolicy (forum_planner_plan R4, the A0
baseline).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.forum_a0_report C:/ssbot/data/runs/m2/<run> [<run> ...] [--out x.json]

Per run set: outcomes (CLEAR / QUIT by trigger / WOULD_DIE / STUCK / HARNESS_FAIL), waves reached, game time per wave
(room.battles' wave starts, the gauntlet record), hits per true wave and per source type, FORCED_RISK share per wave
(ticks and streaks per minute), unpredicted hits (outside the support: must be 0) with their sources, chain follow-ups,
the WaveTracker against room.battles, tick / plan times (per-episode p50 / p99, their medians and the max), late ticks,
modes, targets, Binds, Cogfly throws, the envelope audit (chosen S = 0 plans all enveloped), key presses."""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


def _q(v, p):
    return round(float(np.percentile(v, p)), 3) if v else None


def report(runs: list[Path]) -> dict:
    rows = []
    for d in runs:
        for p in sorted(d.glob("attempts_i*.jsonl")):
            rows += [json.loads(x) for x in p.read_text("utf-8").splitlines() if x.strip()]
    n = len(rows)
    out: dict = {"runs": [str(d) for d in runs], "episodes": n, "config_fp": dict(Counter(r.get("config_fp") for r in rows))}
    out["outcomes"] = dict(Counter(r["outcome"] for r in rows))
    quits = Counter()
    for r in rows:
        if r["outcome"] == "QUIT":
            reason = (r.get("reason") or "").split(": ", 1)[-1]
            quits[reason.split(":")[0].strip()[:24]] += 1
    out["quit_triggers"] = dict(quits)
    out["reasons"] = dict(Counter((r.get("reason") or "")[:90] for r in rows if r["outcome"] != "CLEAR").most_common(12))
    reached = Counter((r.get("gauntlet") or {}).get("wave_reached") for r in rows)
    out["wave_reached"] = {str(k): v for k, v in sorted(reached.items(), key=lambda kv: (kv[0] is None, kv[0] or 0))}
    # time per wave from the true wave starts
    wt = defaultdict(list)
    for r in rows:
        ws = (r.get("gauntlet") or {}).get("waves") or []
        end_f = r.get("f_kill") or r.get("f_end")
        for i, w in enumerate(ws):
            f1 = ws[i + 1]["f"] if i + 1 < len(ws) else (r.get("f_kill") if r.get("f_kill") else None)
            if f1 is not None:
                wt[w["wave"]].append((f1 - w["f"]) / 60.0)
        del end_f
    out["wave_time_s"] = {str(k): {"n": len(v), "p50": _q(v, 50), "max": round(max(v), 1)} for k, v in sorted(wt.items())}
    pol = [r.get("policy") or {} for r in rows]
    hits_w, hits_t, ticks_w, forced_w, streak_w = Counter(), Counter(), Counter(), Counter(), Counter()
    hits_wt = defaultdict(Counter)
    unpred, unknown, follow = [], [], 0
    for r, p in zip(rows, pol):
        for h in p.get("hit_log") or ():
            w = h.get("wave_t")
            hits_w[str(w)] += 1
            hits_t[str(h.get("src_type"))] += 1
            hits_wt[str(w)][str(h.get("src_type"))] += 1
        for w, c in (p.get("per_wave") or {}).items():
            ticks_w[w] += c.get("ticks", 0)
            forced_w[w] += c.get("forced", 0)
            streak_w[w] += c.get("streaks", 0)
        tag = f"{r.get('instance')}/{r.get('episode')}"
        unpred += [[tag, f, s] for f, s in (p.get("unpredicted_sources") or ())]
        unknown += [[tag, f] for f in p.get("unpredicted_unknown") or ()]
        follow += len(p.get("follow_ups") or ())
    out["hits"] = {"total": sum(len(p.get("hits_taken") or ()) for p in pol),
                   "hit_events": sum(hits_w.values()), "per_episode_mean": round(sum(r["hits"] for r in rows) / max(n, 1), 2),
                   "by_wave": dict(sorted(hits_w.items(), key=lambda kv: int(kv[0]) if kv[0] not in ("None",) else 99)),
                   "by_type": dict(hits_t.most_common()), "by_wave_type": {k: dict(v) for k, v in hits_wt.items()},
                   "hp_lost_mean": round(sum(r.get("hp_lost") or 0 for r in rows) / max(n, 1), 2),
                   "would_die_episodes": sum(1 for r in rows if r.get("would_die"))}
    out["forced_risk"] = {w: {"ticks": ticks_w[w], "forced": forced_w[w],
                              "share": round(forced_w[w] / ticks_w[w], 3) if ticks_w[w] else None,
                              "streaks_per_min": round(streak_w[w] / (ticks_w[w] / 3600.0), 2) if ticks_w[w] else None}
                          for w in sorted(ticks_w, key=int)}
    tt = sum(ticks_w.values())
    out["forced_risk_all"] = {"ticks": tt, "forced": sum(forced_w.values()),
                              "share": round(sum(forced_w.values()) / tt, 3) if tt else None}
    out["unpredicted"] = {"outside_support": len(unpred), "unknown": len(unknown), "list": unpred[:40],
                          "unknown_list": unknown[:40], "chain_follow_ups_judged_at_hook": follow,
                          "q4_by_instance": [p.get("q4_by_instance") for p in pol if p.get("q4_by_instance")]}
    wc = Counter()
    bad = []
    for r, p in zip(rows, pol):
        wc.update(p.get("wave_check") or {})
        bad += [[f"{r.get('instance')}/{r.get('episode')}", *b] for b in p.get("wave_bad") or ()]
    out["wave_tracker"] = {**dict(wc), "agree_share": round(wc["agree"] / wc["frames"], 5) if wc["frames"] else None,
                           "mismatch_runs": bad[:60]}
    for k in ("tick_ms_p50", "tick_ms_p99", "plan_ms_p50", "plan_ms_p99"):
        v = [p[k] for p in pol if p.get(k) is not None]
        out[k] = {"median": _q(v, 50), "max": round(max(v), 3) if v else None}
    out["late_ticks"] = {"total": sum(p.get("late_ticks") or 0 for p in pol), "ticks": sum(p.get("ticks") or 0 for p in pol)}
    out["late_states_mean"] = round(sum(r.get("late_states", 0) for r in rows) / max(n, 1), 1)
    modes, tg, aud = Counter(), Counter(), Counter()
    for p in pol:
        modes.update({k: v for k, v in (p.get("modes") or {}).items()})
        tg.update(p.get("targets") or {})
        aud.update(p.get("audit") or {})
    out["modes"] = dict(modes.most_common())
    out["targets"] = dict(tg.most_common())
    out["audit"] = dict(aud)
    out["binds"] = sum(p.get("binds") or 0 for p in pol)
    out["cogfly_throws"] = sum((p.get("cogfly") or {}).get("n", 0) for p in pol)
    out["kills_by_src"] = dict(sum((Counter(((r.get("gauntlet") or {}).get("kills") or {}).get("by_src") or {})
                                    for r in rows), Counter()).most_common(12))
    ing = [r["ingame_s"] for r in rows if r.get("ingame_s") is not None]
    out["ingame_s"] = {"p50": _q(ing, 50), "max": round(max(ing), 1) if ing else None}
    clear = [r.get("kill_s") for r in rows if r["outcome"] == "CLEAR" and r.get("kill_s") is not None]
    out["clear_time_s"] = {"n": len(clear), "p50": _q(clear, 50)}
    rq = [p["real_quit"] for p in pol if p.get("real_quit")]
    out["real_quits"] = {"armed": len(rq), "paused": sum(1 for q in rq if q.get("steps")),
                         "main_menu": sum(1 for q in rq if q.get("main_menu")),
                         "wrong_submits": sum(q.get("wrong_submits") or 0 for q in rq)}
    keys = [p.get("keys") or {} for p in pol]
    pps = [k.get("presses_per_s") for k in keys if k.get("presses_per_s") is not None]
    out["presses_per_s_median"] = _q(pps, 50)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", type=Path, nargs="+")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    out = report(a.runs)
    js = json.dumps(out, indent=1, default=str)
    if a.out:
        a.out.write_text(js, encoding="utf-8")
    print(js)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
