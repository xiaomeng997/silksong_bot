"""Key economy of planner runs against the person's own fight (M2 plan "key economy", 2026-10-03: "a good controller
presses as few keys as possible and changes its key plans as little as possible"; third after safety and time).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.key_economy RUN [RUN ...]                    # one group
    ../scripts/uv.cmd run python -m ssbot.tools.key_economy --arm off RUN RUN --arm on RUN RUN [--json out.json]
        [--human C:/ssbot/data/human/20260930_210337 --frames 64275 68397] [--no-human]

Per group (runs pooled), fights = attempts without HARNESS_FAIL, each from its wake to its end (AttemptRecord f_wake,
f_end):
- outcomes, CLEAR %, WOULD_DIE episodes, hits taken (mean, per episode), time to kill (CLEAR: p50, mean, sd);
- latched presses (rising edges of STATE act.mask, what the game applied) per second, per key and in total: from the
  key plan logs (keys_i<N>.jsonl, combat.keyplan) where the run has them, else from the recordings' act.mask;
- from the key plan logs only (runs from 2026-10-03 night on): decided presses (the planner's notes with the press in
  the fight; the supervisor's are counted apart), the share changed before the press was sent or cancelled (plan
  change rate, also per key), the decision lead (first decision to the press sent, frames; and to the latched press),
  the hold changes after a press, and the frame-level flips (changes, flip-flops: a change back at a frame that already
  changed, one-tick flip-flops) per second of the logged ticks.
The person's fight (raw human session, frames 64275-68397 = the Bell Beast fight from the wake to the kill, the same
window as opportunity_audit / pogo_repro): presses per second per key from STATE input.mask (the game's action layer:
what the person's keys did), counted the same way.
"""
import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np

from ssbot.combat.keyplan import final_press, match_actual, summarize

FPS = 60.0
HUMAN = Path(r"C:\ssbot\data\human\20260930_210337")
HUMAN_FRAMES = (64275, 68397)
LEAD_BINS = (2, 3, 6, 12, 24, 48, 10 ** 9)       # [2], [3, 5], [6, 11], [12, 23], [24, 47], [48, ...)
# menu actions: the game's action layer sets them from gameplay keys too (the person's fight: 11 "enter" with 11
# jumps, 1 "paneright"), so the comparison counts gameplay keys only; all keys are reported as well
MENU_KEYS = frozenset(("inventory", "map", "tools", "journal", "quests", "quickmap", "pause", "enter", "paneleft",
                       "paneright"))


def gameplay_total(c) -> int:
    return sum(v for k, v in c.items() if k not in MENU_KEYS)


def presses_from_masks(fs, masks, f0: int, f1: int) -> Counter:
    """Rising edges per key in [f0, f1] of a per-frame mask stream (the first frame's held keys are not presses)."""
    from ssbot.ipc.framing import BUTTONS
    out: Counter = Counter()
    last = None
    for f, m in zip(fs, masks):
        if f < f0 or f > f1:
            continue
        m = int(m or 0)
        if last is not None:
            x = m & ~last
            while x:
                b = (x & -x).bit_length() - 1
                x &= x - 1
                out[BUTTONS[b]] += 1
        last = m
    return out


def human(session: Path, f0: int, f1: int) -> dict:
    from ssbot.tools.raw_session import states
    fs, masks = [], []
    for s in states(session):
        f = s.get("f", -1)
        if f0 - 1 <= f <= f1:
            fs.append(f)
            masks.append((s.get("input") or {}).get("mask", 0))
        elif f > f1:
            break
    c = presses_from_masks(fs, masks, f0 - 1, f1)
    dur = (f1 - f0 + 1) / FPS
    return {"session": str(session), "frames": [f0, f1], "seconds": round(dur, 2), "presses": dict(c.most_common()),
            "total": sum(c.values()), "per_s": {k: round(v / dur, 3) for k, v in c.most_common()},
            "total_per_s": round(sum(c.values()) / dur, 3),
            "gameplay_per_s": round(gameplay_total(c) / dur, 3)}


def _attempts(run: Path) -> list[dict]:
    rows = []
    for p in sorted(run.glob("attempts_i*.jsonl")):
        for line in p.read_text("utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _key_records(run: Path) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for p in sorted(run.glob("keys_i*.jsonl")):
        inst = int(p.stem.split("_i")[1])
        recs = []
        for line in p.read_text("utf-8").splitlines():
            if line.strip():
                recs.append(json.loads(line))
        out[inst] = recs
    return out


def _record_for(recs: list[dict], a: dict) -> dict | None:
    lo, hi = a.get("f_reset") or a.get("f_wake"), a.get("f_end")
    if lo is None or hi is None:
        return None
    best = None
    for r in recs:
        if r.get("f0") is not None and lo - 5 <= r["f0"] <= hi:
            best = r
            break
    return best


def _latched_from_recording(a: dict) -> Counter | None:
    from ssbot.record.recorder import RecordingReader
    path = a.get("recording")
    if not path or not Path(path).exists():
        return None
    r = RecordingReader(path)
    fs, masks = [], []
    for s in r.states(a["f_wake"] - 1, a["f_end"], keys=("act",)):
        fs.append(s["f"])
        masks.append((s.get("act") or {}).get("mask", 0))
    return presses_from_masks(fs, masks, a["f_wake"] - 1, a["f_end"])


def _q(v, qs=(10, 25, 50, 75, 90)) -> dict:
    return {f"p{q}": round(float(np.percentile(v, q)), 2) for q in qs} | {"mean": round(float(np.mean(v)), 2),
                                                                       "n": len(v)} if len(v) else {"n": 0}


def group(runs: list[Path]) -> dict:
    rows, per_key_lat, ep_rate = [], Counter(), []
    secs = 0.0
    dec = ex = chg = canc = late = sup = hold = 0
    leads, leads_act, lag = [], [], []
    by_key: dict[str, Counter] = {}
    flips = np.zeros(3, np.int64)
    flip_s = 0.0
    sources = Counter()
    for run in runs:
        recs = _key_records(run)
        for a in _attempts(run):
            if a.get("outcome") == "HARNESS_FAIL" or a.get("f_wake") is None or a.get("f_end") is None:
                continue
            rows.append(a)
            fw, fe = a["f_wake"], a["f_end"]
            dur = (fe - fw + 1) / FPS
            rec = _record_for(recs.get(a.get("instance"), []), a)
            if rec is not None:
                c = Counter({k: sum(1 for p, _r in iv if fw <= p <= fe) for k, iv in rec["actual"].items()})
                c = +c
                sources["key_log"] += 1
            else:
                c = _latched_from_recording(a)
                if c is None:
                    sources["none"] += 1
                    continue
                sources["recording"] += 1
            per_key_lat.update(c)
            secs += dur
            ep_rate.append(sum(c.values()) / dur)
            if rec is None:
                continue
            sm = summarize(rec, fw, fe)
            dec += sm["decided"]
            ex += sm["executed"]
            chg += sm["changed_before_press"]
            canc += sm["cancelled"]
            late += sm["cancelled_late"]
            sup += sm["supervisor_notes"]
            hold += sm["hold_changed_after_press"]
            leads += sm["leads"]
            span = ((rec.get("f1") or 0) - (rec.get("f0") or 0) + 1) / FPS
            flips += np.array([sm["flip_changes"], sm["flipflops"], sm["flipflops_1tick"]])
            flip_s += max(span, 0.0)
            m = match_actual(rec)
            for i, (pa, _ra) in m.items():
                n = rec["notes"][i]
                if n[6] or not fw <= final_press(n) <= fe:
                    continue
                leads_act.append(pa - n[1])
                lag.append(pa - final_press(n))
            for n in rec["notes"]:
                if n[4] == "h" or n[6] or not fw <= final_press(n) <= fe:
                    continue
                k = by_key.setdefault(n[0], Counter())
                k["decided"] += 1
                k["changed_or_cancelled"] += (n[4] in ("c", "l")) or (n[4] == "x" and any(h[0] <= n[5] for h in n[7]))
    outc = Counter(a["outcome"] for a in rows)
    n = len(rows)
    ttk = [a["ingame_s"] for a in rows if a["outcome"] == "CLEAR" and a.get("ingame_s") is not None]
    hits = [a.get("hits") or 0 for a in rows]
    out = {"runs": [str(r) for r in runs], "episodes": n, "outcomes": dict(outc),
           "clear_pct": round(100.0 * outc.get("CLEAR", 0) / n, 1) if n else None,
           "would_die_episodes": sum(1 for a in rows if a.get("would_die")),
           "hits_total": sum(hits), "hits_mean": round(float(np.mean(hits)), 3) if hits else None,
           "hits_per_episode": dict(sorted(Counter(hits).items())),
           "time_to_kill_s": ({"p50": round(float(np.median(ttk)), 2), "mean": round(float(np.mean(ttk)), 2),
                               "sd": round(float(np.std(ttk, ddof=1)), 2) if len(ttk) > 1 else None, "n": len(ttk)}
                              if ttk else None),
           "press_source": dict(sources), "fight_s": round(secs, 1),
           "presses_per_s": {k: round(v / secs, 3) for k, v in per_key_lat.most_common()} if secs else {},
           "presses_per_s_total": round(sum(per_key_lat.values()) / secs, 3) if secs else None,
           "presses_per_s_gameplay": round(gameplay_total(per_key_lat) / secs, 3) if secs else None,
           "presses_per_s_episode": _q(ep_rate)}
    if dec:
        bins = np.histogram(leads, bins=LEAD_BINS)[0] if leads else []
        out["plan"] = {
            "decided": dec, "executed": ex, "changed_before_press": chg, "cancelled": canc, "cancelled_late": late,
            "supervisor_notes": sup, "hold_changed_after_press": hold,
            "plan_change_rate": round((chg + canc) / dec, 4),
            "plan_change_rate_by_key": {k: round(v["changed_or_cancelled"] / v["decided"], 4) for k, v in
                                        sorted(by_key.items(), key=lambda kv: -kv[1]["decided"])},
            "decided_by_key": {k: v["decided"] for k, v in sorted(by_key.items(), key=lambda kv: -kv[1]["decided"])},
            "lead_frames": _q(leads), "lead_frames_hist": {
                lab: int(c) for lab, c in zip(("2", "3-5", "6-11", "12-23", "24-47", ">=48"), bins)},
            "lead_to_latched_frames": _q(leads_act), "sent_to_latched_frames": dict(sorted(Counter(lag).items())),
            "flips_per_s": {"changes": round(flips[0] / flip_s, 3), "flipflops": round(flips[1] / flip_s, 3),
                            "flipflops_1tick": round(flips[2] / flip_s, 3)} if flip_s else None}
    return out


def compare(a: dict, b: dict) -> dict:
    """b against a: time to kill (Welch's t, 95 % interval of the difference of means), CLEAR and hits."""
    out = {}
    ta, tb = a.get("time_to_kill_s"), b.get("time_to_kill_s")
    if ta and tb and ta.get("sd") and tb.get("sd"):
        d = tb["mean"] - ta["mean"]
        se = math.sqrt(ta["sd"] ** 2 / ta["n"] + tb["sd"] ** 2 / tb["n"])
        out["time_to_kill_mean_diff_s"] = {"diff": round(d, 2), "ci95": [round(d - 1.96 * se, 2),
                                                                         round(d + 1.96 * se, 2)]}
    out["clear_pct_diff"] = None if a["clear_pct"] is None or b["clear_pct"] is None else \
        round(b["clear_pct"] - a["clear_pct"], 1)
    out["hits_mean_diff"] = None if a["hits_mean"] is None or b["hits_mean"] is None else \
        round(b["hits_mean"] - a["hits_mean"], 3)
    if a.get("presses_per_s_total") and b.get("presses_per_s_total"):
        out["presses_per_s_ratio"] = round(b["presses_per_s_total"] / a["presses_per_s_total"], 3)
    pa, pb = a.get("plan"), b.get("plan")
    if pa and pb:
        out["plan_change_rate_diff"] = round(pb["plan_change_rate"] - pa["plan_change_rate"], 4)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="*", type=Path)
    ap.add_argument("--arm", nargs="+", action="append", default=[], metavar=("NAME", "RUN"),
                    help="a named group of runs (repeat: the second and later are compared with the first)")
    ap.add_argument("--human", type=Path, default=HUMAN)
    ap.add_argument("--frames", type=int, nargs=2, default=HUMAN_FRAMES)
    ap.add_argument("--no-human", action="store_true")
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    arms = [(x[0], [Path(p) for p in x[1:]]) for x in a.arm]
    if a.runs:
        arms.insert(0, ("runs", a.runs))
    out: dict = {"arms": {name: group(runs) for name, runs in arms}}
    if len(arms) > 1:
        base = out["arms"][arms[0][0]]
        out["vs_" + arms[0][0]] = {name: compare(base, out["arms"][name]) for name, _ in arms[1:]}
    if not a.no_human and a.human.exists():
        out["human"] = human(a.human, *a.frames)
    print(json.dumps(out, indent=1))
    if a.json:
        a.json.write_text(json.dumps(out, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
