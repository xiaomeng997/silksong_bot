"""Attack instances logged per Forum enemy type (M2 W8 data collection target: >= 200 of every attack of every type).

Counts the gauntlet AttemptRecords' state entries ("<type>/<fsm>/<state>", ssbot.train.gauntlet.GauntletTap) of the
attack-start states below, from the Hang_04_boss scene bundle FSMs (docs/facts/1.0.30000/forum.md §2: each attack's
first state; a "Parry ..." state is the counter of a parry stance). Also: episodes, waves reached, kills by source, and
an estimate of the hours to reach the target at the run's rate (wall time from the records).

    ..\\scripts\\uv.cmd run python -m ssbot.tools.forum_counts C:/ssbot/data/runs/m2/<run> [more runs ...]
"""
import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

ATTACKS: dict[str, tuple[str, ...]] = {
    "Song Heavy Sentry/Control": ("Slam Antic", "Jump Antic", "Spell Antic", "Cast Slam Antic", "Cast Jump Antic"),
    "Song Pilgrim 01/Attack": ("Slash Antic", "JumpSlash Antic", "Charge Antic", "HopSlash Antic", "Ambush Antic"),
    "Song Pilgrim 03/Attack": ("Slash Antic", "Whip Antic", "Jump Antic", "ComboSlash Antic1", "Slash Antic Jump"),
    "Pilgrim 03 Song/Control": ("Throw Antic", "Throw Antic Quick"),
    "Song Reed/Control": ("Stab Antic", "Throw Antic", "Parry Slash"),
    "Song Handmaiden/Control": ("Slash Antic", "Spin Antic", "Spear Cast Antic"),
    "Song Administrator/Control": ("Attack Antic", "Parry Stance Antic", "Parry Slash 1"),
    "Song Pilgrim Maestro/Control": ("Fire Antic", "Slash 1"),
}
TARGET = 200


def load(runs: list[Path]) -> list[dict]:
    rows = []
    for run in runs:
        for p in sorted(run.glob("attempts_i*.jsonl")):
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def counts(rows: list[dict]) -> Counter:
    c: Counter = Counter()
    for r in rows:
        c.update(r.get("attacks") or {})
    return c


def report(rows: list[dict]) -> dict:
    c = counts(rows)
    per: dict[str, int] = {}
    for tf, states in ATTACKS.items():
        for st in states:
            per[f"{tf}/{st}"] = c.get(f"{tf}/{st}", 0)
    waves = Counter((r.get("gauntlet") or {}).get("wave_reached") for r in rows)
    by_src: Counter = Counter()
    for r in rows:
        by_src.update(((r.get("gauntlet") or {}).get("kills") or {}).get("by_src") or {})
    ts = sorted(datetime.fromisoformat(r["t"]) for r in rows if r.get("t"))
    wall_h = sum((r.get("wall_s") or 0) for r in rows) / 3600.0
    span_h = (ts[-1] - ts[0]).total_seconds() / 3600.0 if len(ts) > 1 else None
    need = {k: v for k, v in per.items() if v < TARGET}
    eta = None
    if wall_h > 0 and need:
        # hours of episode wall time per instance until the slowest attack reaches the target, at the current rate
        worst = min((v / wall_h, k) for k, v in per.items())
        eta = {"slowest": worst[1], "per_hour": round(worst[0], 1),
               "hours_episode_time": round(TARGET / worst[0], 1) if worst[0] > 0 else None}
    return {"episodes": len(rows), "outcomes": dict(Counter(r["outcome"] for r in rows)),
            "wave_reached": dict(sorted(waves.items(), key=lambda kv: (kv[0] is None, kv[0]))),
            "kills_by_src": dict(by_src.most_common(12)), "episode_hours": round(wall_h, 2), "span_hours": span_h,
            "attacks": per, "below_target": len(need), "eta": eta,
            "other_states_top": [(k, v) for k, v in c.most_common(400) if k not in per][:40]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", type=Path, nargs="+")
    a = ap.parse_args(argv)
    print(json.dumps(report(load(a.runs)), indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
