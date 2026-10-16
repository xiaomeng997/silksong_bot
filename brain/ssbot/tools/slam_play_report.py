"""Tables of the slam playbook's fixed-point live trials (task 1v1 SP1, ssbot.probes.slam_play_probe; forum.md 65).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.slam_play_report C:/ssbot/data/m2_play/live/.../play_trials.jsonl ...
        [--json out.json]

Per distance class (the hero's x at the antic sighting, rounded to the class): trials that saw a slam, the playbook
started / pressed, landed (the Clapper lost HP), bounce, success (landed and no damage until the Slam Recover ends),
damage in the slam by source (hammer = Slam Collider 1 / 2, body = the Clapper), misses, the real press frame relative
to the antic entry and to Slam 0, the antic length, x at the jump / press (u in front, centre to centre), the reasons
it did not start or aborted, damage after the slam (to the trial's end).
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


def pct(v, qs=(10, 50, 90)):
    v = [x for x in v if x is not None]
    return [round(float(np.percentile(v, q)), 2) for q in qs] if v else None


def src_kind(src: str) -> str:
    if "Collider" in src:
        return "hammer"
    if "Heavy Sentry" in src:
        return "body"
    return "other"


def load(paths) -> list[dict]:
    out = []
    for p in paths:
        for line in Path(p).read_text("utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                r["_file"] = str(p)
                out.append(r)
    return out


def mixed(r: dict) -> bool:
    """A trace whose playbook run is a second slam inside the trial's settle (probe before 2026-10-16 05:15): its
    stages and keys mix two slams."""
    a = r.get("antic")
    kp = r.get("k_press_real")
    return (a is not None and not 40 <= a <= 60) or (kp is not None and kp < 0)


def summarize(rows: list[dict]) -> dict:
    by = defaultdict(list)
    for r in rows:
        if "skip" in r or "error" in r or r.get("seen") is None or mixed(r):
            continue
        by[r["d"]].append(r)
    out = {}
    for d in sorted(by) + ["all"]:
        R = [r for k in by for r in by[k]] if d == "all" else by[d]
        st = [r for r in R if (r.get("play") or {}).get("k_start") is not None]
        pr = [r for r in R if r.get("k_press_real") is not None]
        hurt = Counter(src_kind(h["src"]) for r in R for h in r.get("hurt_slam") or ())
        hurt_after = Counter(src_kind(h["src"]) for r in R for h in r.get("hurt_after") or ())
        why = Counter((r.get("play") or {}).get("why") or (r.get("play") or {}).get("phase") for r in R
                      if (r.get("play") or {}).get("k_start") is None or (r.get("play") or {}).get("phase") == "abort")
        out[str(d)] = {
            "n": len(R), "x_seen": pct([r["seen"]["x"] for r in R]), "started": len(st), "pressed": len(pr),
            "landed": sum(r.get("landed", False) for r in R), "bounce": sum(r.get("bounce", False) for r in R),
            "success": sum(r.get("success", False) for r in R),
            "success_of_started": f"{sum(r.get('success', False) for r in st)}/{len(st)}",
            "hurt_slam_trials": sum(1 for r in R if r.get("hurt_slam")), "hurt_slam_src": dict(hurt),
            "miss": sum(1 for r in pr if not r.get("landed")),
            "k_press": pct([r.get("k_press_real") for r in pr]), "press_rel_s0": pct([r.get("press_rel_s0") for r in pr]),
            "press_rel_s0_hist": dict(Counter(r.get("press_rel_s0") for r in pr)),
            "contact_rel_s0": pct([r.get("contact_rel_s0") for r in pr]),
            "k_jump": pct([r.get("k_jump_real") for r in st]), "antic": dict(Counter(r.get("antic") for r in R)),
            "x_jump": pct([r.get("x_jump") for r in st]), "x_press": pct([r.get("x_press") for r in pr]),
            "y_press": pct([r.get("y_press") for r in pr]),
            "not_started_or_abort": dict(why), "hurt_after_src": dict(hurt_after),
            "gaps": sum(r.get("gaps", 0) for r in R)}
    return out


def fails(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        if "skip" in r or "error" in r or r.get("seen") is None or mixed(r):
            continue
        p = r.get("play") or {}
        if p.get("k_start") is not None and not r.get("success"):
            out.append({"n": r["n"], "file": Path(r["_file"]).parent.name, "d": r["d"], "x_seen": r["seen"]["x"],
                        "phase": p.get("phase"), "why": p.get("why"), "antic": r.get("antic"),
                        "k_jump": r.get("k_jump_real"), "k_press": r.get("k_press_real"),
                        "press_rel_s0": r.get("press_rel_s0"), "x_jump": r.get("x_jump"), "x_press": r.get("x_press"),
                        "landed": r.get("landed"), "bounce": r.get("bounce"),
                        "hurt": [(h["rel_s0"], h["st"], h["src"]) for h in r.get("hurt_slam") or ()]})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    rows = load(a.files)
    s = summarize(rows)
    f = fails(rows)
    skips = Counter(r.get("skip") or ("error" if "error" in r else "mixed" if mixed(r) else "ok") for r in rows)
    for d, v in s.items():
        print(d, json.dumps(v))
    print("skips", dict(skips))
    for x in f:
        print("FAIL", json.dumps(x))
    if a.json:
        a.json.write_text(json.dumps({"classes": s, "fails": f, "skips": dict(skips), "files": a.files}, indent=1),
                          "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
