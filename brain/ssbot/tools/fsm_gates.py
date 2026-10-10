"""FSM history gates (task precision push S3, fix_spec F5: SSBOT_FORUM_GATES). Mined from the forum_extract caches:
for every Forum type and attack family F, every pair of consecutive starts of F by one enemy (no death between), the
Control states entered strictly between the two starts. A state entered between EVERY pair (n pairs >= --min-pairs) is
a lift state of F: once F starts, no other instance of F starts before it is entered (the Bellbearer: Evade Cooldown
set by Evade, cleared by Throw Antic, fix_spec F5: 0 of 4,497). Only lift states that are attack starts of another
family are kept (a cooldown cleared by another attack; the idle decision states and F's own states lift too early to
matter, and an own state is entered by the current instance anyway). The time-out is twice the longest recorded gap
from F's start to the lift state's entry.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.fsm_gates mine C:/ssbot/data/m2_forum_r0/cache --out <fsm_gates.json>
    ../scripts/uv.cmd run python -m ssbot.tools.fsm_gates check <fsm_gates.json> C:/ssbot/data/m2_forum_r0/cache_fresh
                                                     # held out: violations (a second start before the lift) per gate
"""
import argparse
import glob
import gzip
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

from ssbot.combat.enemy_tables import FORUM_DIR
from ssbot.core.forum import FORUM_TYPES


def type_specs() -> dict:
    """{type key: (control fsm, {start state: family}, idle family, entry family, death states)}."""
    out = {}
    for tk, sp in FORUM_TYPES.items():
        p = FORUM_DIR / f"{sp.enemy}.json"
        if not p.exists():
            continue
        d = json.loads(p.read_text("utf-8"))
        out[tk] = (sp.control_fsm, dict(d["spec"]["attack_starts"]), sp.idle_family, sp.entry_family,
                   set(sp.death_states))
    return out


def sequences(path: str, specs: dict):
    """(type key, [(game time, state)]) per enemy of one cached fight, its Control transitions in order."""
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        d = json.load(fh)
    z = np.load(path.replace(".json.gz", ".npz"))
    f, T = z["f"], z["T"]
    seq = defaultdict(list)
    tk_of = {}
    for fr, kind, ev in d["events"]:
        if kind != "fsm":
            continue
        tk = ev.get("obj")
        sp = specs.get(tk)
        if sp is None or ev.get("fsm") != sp[0]:
            continue
        i = min(int(np.searchsorted(f, fr)), len(f) - 1)
        seq[ev["iid"]].append((float(T[i]), ev["to"]))
        tk_of[ev["iid"]] = tk
    for iid, s in seq.items():
        yield tk_of[iid], s


def pairs(tk: str, s: list, specs: dict):
    """(family, gap list) per consecutive start pair of one enemy: (t start, t next start, [(t, state) between])."""
    _fsm, starts, idle, entry, deaths = specs[tk]
    last: dict = {}                     # family -> (its latest start time, the transitions since)
    for t, st in s:
        if st in deaths:
            last = {}
            continue
        for fam, (t0, between) in last.items():
            between.append((t, st))
        fam = starts.get(st)
        if fam is None or fam in (idle, entry):
            continue
        if fam in last:
            t0, between = last[fam]
            yield fam, (t0, t, between[:-1])
        last[fam] = (t, [])


def mine(dirs: list, min_pairs: int) -> dict:
    specs = type_specs()
    inter: dict = {}
    n: dict = defaultdict(int)
    gaps: dict = defaultdict(lambda: defaultdict(float))
    for dr in dirs:
        for fn in sorted(glob.glob(str(Path(dr) / "*.json.gz"))):
            for tk, s in sequences(fn, specs):
                for fam, (t0, t1, between) in pairs(tk, s, specs):
                    k = (tk, fam)
                    first = {}
                    for t, st in between:
                        first.setdefault(st, t)
                    inter[k] = set(first) if k not in inter else inter[k] & set(first)
                    n[k] += 1
                    for st, t in first.items():
                        gaps[k][st] = max(gaps[k][st], t - t0)
    gates = []
    for (tk, fam), cand in sorted(inter.items()):
        starts = specs[tk][1]
        lifts = sorted(st for st in cand if st in starts and starts[st] != fam)
        if n[(tk, fam)] < min_pairs or not lifts:
            continue
        for lift in lifts:
            gates.append({"type": tk, "family": fam, "lift": lift, "pairs": n[(tk, fam)],
                          "longest_gap_s": round(gaps[(tk, fam)][lift], 4),
                          "timeout_s": round(2.0 * gaps[(tk, fam)][lift], 4)})
    return {"product": "fsm_gates", "sources": [str(d) for d in dirs], "min_pairs": min_pairs, "gates": gates,
            "pairs": {f"{tk}/{fam}": c for (tk, fam), c in sorted(n.items())}}


def check(gates_path: str, dirs: list) -> dict:
    specs = type_specs()
    gates = json.loads(Path(gates_path).read_text("utf-8"))["gates"]
    by = defaultdict(list)
    for g in gates:
        by[(g["type"], g["family"])].append(g)
    res = {f"{g['type']}/{g['family']}/{g['lift']}": {"pairs": 0, "violations": 0, "over_timeout": 0,
                                                       "examples": []} for g in gates}
    for dr in dirs:
        for fn in sorted(glob.glob(str(Path(dr) / "*.json.gz"))):
            for tk, s in sequences(fn, specs):
                for fam, (t0, t1, between) in pairs(tk, s, specs):
                    for g in by.get((tk, fam), ()):
                        r = res[f"{tk}/{fam}/{g['lift']}"]
                        r["pairs"] += 1
                        tl = next((t for t, st in between if st == g["lift"]), None)
                        if tl is None:
                            r["violations"] += 1
                            if len(r["examples"]) < 5:
                                r["examples"].append([Path(fn).name, round(t0, 3), round(t1, 3)])
                        elif tl - t0 > g["timeout_s"]:
                            r["over_timeout"] += 1
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("mine")
    a.add_argument("dirs", nargs="+")
    a.add_argument("--out", required=True)
    a.add_argument("--min-pairs", type=int, default=200)
    b = sub.add_parser("check")
    b.add_argument("gates")
    b.add_argument("dirs", nargs="+")
    b.add_argument("--json")
    args = ap.parse_args()
    if args.cmd == "mine":
        out = mine(args.dirs, args.min_pairs)
        Path(args.out).write_text(json.dumps(out, indent=1), "utf-8")
        for g in out["gates"]:
            print(g)
    else:
        res = check(args.gates, args.dirs)
        print(json.dumps(res, indent=1))
        if args.json:
            Path(args.json).write_text(json.dumps(res, indent=1), "utf-8")


if __name__ == "__main__":
    main()
