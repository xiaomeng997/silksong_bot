"""The Forum plan's §6.3 metrics over live full-gauntlet runs of ForumPlannerPolicy (forum_planner_plan R4, the A0
baseline).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.forum_a0_report C:/ssbot/data/runs/m2/<run> [<run> ...] [--out x.json]

Per run set: outcomes (CLEAR / QUIT by trigger / WOULD_DIE / STUCK / HARNESS_FAIL), waves reached, game time per wave
(room.battles' wave starts, the gauntlet record), hits per true wave and per source type, FORCED_RISK share per wave
(ticks and streaks per minute), unpredicted hits (outside the support: must be 0) with their sources, chain follow-ups,
the WaveTracker against room.battles, tick / plan times (per-episode p50 / p99, their medians and the max), late ticks,
modes, targets, Binds, Cogfly throws, the envelope audit (chosen S = 0 plans all enveloped), key presses.

Hits are counted per damage event (the episode's "hits"); the Multihit ticks of a multi-hit chain (special_damage,
TakeQuickDamage, no source of their own) are HIT_TAKEN too but counted apart ("mh_ticks"). A hit's type is its
HIT_TAKEN source type, else the one its caller path names (a projectile: the type that throws it, ForumType.spawns).
Records from before the R4 fixer round have no hit kind / path in hit_log: they are read from the episode's recording
(events.jsonl, the damage / special_damage events of the hit's frame)."""
import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from ssbot.core.forum import FORUM_TYPES

_SPAWNS = {hz: tk for tk, t in FORUM_TYPES.items() for hz, _ in t.spawns}


def _q(v, p):
    return round(float(np.percentile(v, p)), 3) if v else None


def type_of(path: str | None, src_type: str | None = None) -> str | None:
    """The Forum type key a hit came from: its HIT_TAKEN source type (a hazard's: its thrower), else the type (or the
    thrower of the hazard) a part of its caller path names ("Song Reed Pin Projectile(Clone)" -> "Song Reed",
    "Wave 9/Song Reed (3)" -> "Song Reed", "rune bomb small(Clone)/damager" -> "Song Heavy Sentry"); None: no part
    names one."""
    if src_type in FORUM_TYPES:
        return src_type
    if src_type in _SPAWNS:
        return _SPAWNS[src_type]
    for part in reversed(str(path or "").split("/")):
        q = re.sub(r"\s*\(\d+\)$", "", part.replace("(Clone)", "").strip())
        if q in FORUM_TYPES:
            return q
        if q in _SPAWNS:
            return _SPAWNS[q]
        for tk in sorted(FORUM_TYPES, key=len, reverse=True):
            if q.startswith(tk):
                return tk
    return None


def _rec_hits(row: dict) -> dict[int, list[tuple[str, str | None]]]:
    """frame -> [(kind, path)] of the recording's damage ("damage", source) and special_damage ("tick", fsm) events."""
    out: dict[int, list] = defaultdict(list)
    rec = row.get("recording")
    p = Path(rec) / "events.jsonl" if rec else None
    if p is None or not p.exists():
        return out
    for line in p.read_text("utf-8").splitlines():
        if 'damage"' not in line:
            continue
        e = json.loads(line)
        k, d = e.get("kind"), e.get("data") or {}
        if k == "damage":
            out[int(e["frame"])].append(("damage", d.get("source")))
        elif k == "special_damage":
            out[int(e["frame"])].append(("tick", d.get("fsm") or d.get("method")))
    return out


def hit_kinds(row: dict, hit_log: list[dict]) -> list[tuple[str, str | None]]:
    """(kind, caller path) per hit_log entry: the entry's own (R4 fixer round on), else from the recording (the
    frame's damage / special_damage events in order; an entry with a source is a damage event's)."""
    if all("kind" in h for h in hit_log):
        return [(h["kind"], h.get("path")) for h in hit_log]
    rec = _rec_hits(row)
    out = []
    used: Counter = Counter()
    for h in hit_log:
        f = int(h["f"])
        evs = next((rec[g] for g in (f, f - 1, f + 1) if rec.get(g)), [])
        if h.get("src_id") is not None or h.get("src_type"):
            evs = [e for e in evs if e[0] == "damage"] or evs
        i = used[f]
        used[f] += 1
        out.append(evs[min(i, len(evs) - 1)] if evs else ("damage", None))
    return out


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
    mh_w, mh_judged = Counter(), Counter()
    hits_wt = defaultdict(Counter)
    unpred, unknown, follow = [], [], 0
    for r, p in zip(rows, pol):
        hl = p.get("hit_log") or []
        for h, (kind, path) in zip(hl, hit_kinds(r, hl)):
            w = h.get("wave_t")
            if kind == "tick":
                mh_w[str(w)] += 1
                continue
            tk = type_of(path, h.get("src_type"))
            tk = FORUM_TYPES[tk].name if tk in FORUM_TYPES else "unresolved"
            hits_w[str(w)] += 1
            hits_t[tk] += 1
            hits_wt[str(w)][tk] += 1
        mh_judged.update(x[1] for x in p.get("mh_ticks") or ())
        for w, c in (p.get("per_wave") or {}).items():
            ticks_w[w] += c.get("ticks", 0)
            forced_w[w] += c.get("forced", 0)
            streak_w[w] += c.get("streaks", 0)
        tag = f"{r.get('instance')}/{r.get('episode')}"
        unpred += [[tag, f, s] for f, s in (p.get("unpredicted_sources") or ())]
        unknown += [[tag, f] for f in p.get("unpredicted_unknown") or ()]
        follow += len(p.get("follow_ups") or ())
    wkey = (lambda kv: int(kv[0]) if kv[0] not in ("None",) else 99)
    out["hits"] = {"damage_events": sum(len(p.get("hits_taken") or ()) for p in pol),
                   "hits_taken": sum(hits_w.values()), "mh_ticks": sum(mh_w.values()),
                   "per_episode_mean": round(sum(r["hits"] for r in rows) / max(n, 1), 2),
                   "by_wave": dict(sorted(hits_w.items(), key=wkey)),
                   "mh_ticks_by_wave": dict(sorted(mh_w.items(), key=wkey)),
                   "mh_ticks_judged": dict(mh_judged),
                   "by_type": dict(hits_t.most_common()), "by_wave_type": {k: dict(v) for k, v in hits_wt.items()},
                   "hp_lost_mean": round(sum(r.get("hp_lost") or 0 for r in rows) / max(n, 1), 2),
                   "would_die_episodes": sum(1 for r in rows if r.get("would_die"))}
    shares = [forced_w[w] / ticks_w[w] for w in ticks_w if ticks_w[w]]
    out["forced_risk_range"] = [round(min(shares), 3), round(max(shares), 3)] if shares else None
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
