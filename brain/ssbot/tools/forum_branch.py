"""Forum branch model (forum_planner_plan §5 R5, behaviour-model half): scan cached fights for decisions, study the
sensing timing and the history covariates on held-out fights, build knowledge/.../forum/branch_model.json.

    cd brain   # below-normal priority, NUMBA_NUM_THREADS <= 4
    ..\\scripts\\uv.cmd run python -m ssbot.tools.forum_branch scan <cache dir> [<cache dir> ...] --out recs_dev.pkl
        [--extra-dir DIR] [--workers 3]
    ..\\scripts\\uv.cmd run python -m ssbot.tools.forum_branch study recs_dev.pkl --json study.json
    ..\\scripts\\uv.cmd run python -m ssbot.tools.forum_branch build recs_dev.pkl --study study.json
        [--test recs_test.pkl] --out <branch_model.json> [--report report.json]

scan: one DecisionRecord per exit of a decision state (ssbot.knowledge.forum_branch.decisions_of) in every cached
fight (forum_cache), with the hero's silk from the recording (cached as <extra-dir>/<cache name>.hero.npz). Folds:
the fights alternate by sorted id (two folds). study: per decision, the CV log loss of the unconditional table (the
runtime's p_succ), the R0 tables' conditioners, and the greedy selection per timing (geometry only / geometry +
history). build: the chosen model per decision fit on all scanned fights; --test evaluates it, the unconditional and
the R0 conditioners on other fights (fit on the scanned ones).
"""
import argparse
import ctypes
import json
import os
import pickle
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from ssbot.knowledge import forum_branch as fb
from ssbot.knowledge.forum_cache import load_cache

FORUM_DIR = Path(__file__).resolve().parents[3] / "knowledge" / "1.0.30000" / "enemies" / "forum"
R0_TABLES = {"Song Heavy Sentry": "ChoirClapper", "Song Handmaiden": "Clawmaiden", "Song Administrator": "Minister",
             "Song Pilgrim Maestro": "Maestro", "Song Automaton Tiny": "MaestroAutomaton", "Song Reed": "Reed",
             "Song Pilgrim 01": "Envoy", "Song Pilgrim 03": "Choristor", "Pilgrim 03 Song": "ChoirBellbearer"}


def _below_normal() -> None:
    if os.name == "nt":
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)


def _scan_one(args) -> tuple[str, list, str | None]:
    path, extra_dir = args
    _below_normal()
    try:
        c = load_cache(Path(path))
        extra = None
        if extra_dir is not None:
            xp = Path(extra_dir) / (Path(path).stem + ".hero.npz")
            if xp.exists():
                with np.load(xp) as z:
                    extra = {k: z[k] for k in z.files}
            else:
                extra = fb.hero_extra(c["meta"])
                xp.parent.mkdir(parents=True, exist_ok=True)
                np.savez_compressed(xp, **extra)
        return c["meta"]["id"], fb.scan_fight(c, extra), None
    except Exception as e:  # noqa: BLE001 - one bad fight must not stop the scan
        return str(path), [], f"{type(e).__name__}: {e}"


def cmd_scan(a) -> int:
    paths = sorted(p for d in a.caches for p in Path(d).glob("*.npz") if not p.name.endswith(".hero.npz"))
    if a.max_fights:
        paths = paths[:a.max_fights]
    t0 = time.perf_counter()
    recs, errors = [], []
    jobs = [(str(p), str(a.extra_dir) if a.extra_dir else None) for p in paths]
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for i, (fid, rr, err) in enumerate(ex.map(_scan_one, jobs, chunksize=1)):
            if err:
                errors.append((fid, err))
            recs += rr
            print(f"[{i + 1}/{len(jobs)}] {fid}: {len(rr)} decisions{' ERROR ' + err if err else ''}", flush=True)
    fights = sorted({r.fight for r in recs})
    fold = {f: i % 2 for i, f in enumerate(fights)}
    with open(a.out, "wb") as fh:
        pickle.dump({"records": recs, "fold": fold, "caches": [str(d) for d in a.caches], "errors": errors}, fh)
    print(f"{len(recs)} decisions from {len(fights)} fights in {time.perf_counter() - t0:.0f} s; {len(errors)} errors")
    return 0


def _load(path: Path) -> tuple[list, dict]:
    with open(path, "rb") as fh:
        d = pickle.load(fh)
    return d["records"], d["fold"]


def _groups(recs: list) -> dict[tuple[str, str], list]:
    g = defaultdict(list)
    for r in recs:
        g[(r.tk, r.state)].append(r)
    return g


def _r0_conditioners(tk: str, state: str) -> list[str] | None:
    name = R0_TABLES.get(tk)
    if name is None:
        return None
    p = FORUM_DIR / f"{name}.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text("utf-8"))
    row = (d.get("decisions") or {}).get(state)
    return None if row is None else list(row.get("conditioners") or [])


def cmd_study(a) -> int:
    _below_normal()
    recs, fold = _load(a.records)
    out = {}
    t0 = time.perf_counter()
    for (tk, st), rr in sorted(_groups(recs).items()):
        outs = {r.outcome for r in rr}
        if len(outs) < 2 or len(rr) < a.min_n:
            continue
        dd = fb.decision_data(rr, fold)
        res = fb.study_decision(dd, _r0_conditioners(tk, st))
        out.setdefault(tk, {})[st] = res
        ch = res["chosen"]
        print(f"{tk:22} {st:22} n={res['n']:6} uncond {res['uncond']['logloss']:.4f} "
              f"r0 {res.get('r0', {}).get('logloss', float('nan')):.4f} -> {ch['logloss']:.4f} "
              f"[{ch['timing']}] {ch['covariates']}  ({time.perf_counter() - t0:.0f} s)", flush=True)
    Path(a.json).write_text(json.dumps({"records": str(a.records), "select_gain": fb.SELECT_GAIN,
                                        "max_covariates": fb.MAX_COVARIATES, "types": out}, indent=1), "utf-8")
    return 0


def cmd_build(a) -> int:
    _below_normal()
    recs, fold = _load(a.records)
    study = json.loads(Path(a.study).read_text("utf-8"))["types"]
    test_groups = {}
    if a.test:
        trecs, _ = _load(a.test)
        test_groups = _groups(trecs)
    model, report = {}, {}
    for (tk, st), rr in sorted(_groups(recs).items()):
        res = study.get(tk, {}).get(st)
        if res is None:
            continue
        dd = fb.decision_data(rr, fold)
        ch = res["chosen"]
        model.setdefault(tk, {})[st] = fb.fit_tables(dd, ch["timing"], ch["covariates"])
        model[tk][st]["cv_logloss"] = ch["logloss"]
        tr = test_groups.get((tk, st))
        if tr:
            td = fb.decision_data(tr, {}, timings=(ch["timing"], "branch"))
            r0 = res.get("r0", {}).get("conditioners") or []
            r0_names = [f"h:{n}" for n in r0 if n in dd.hist and n in td.hist]
            row = {"chosen": fb.holdout_eval(dd, td, ch["timing"], ch["covariates"]),
                   "uncond": fb.holdout_eval(dd, td, "branch", []),
                   "r0": fb.holdout_eval(dd, td, "branch", r0_names) if r0_names else None}
            report.setdefault(tk, {})[st] = row
            print(f"{tk:22} {st:22} test n={row['chosen']['n']:6} uncond {row['uncond']['logloss']:.4f} "
                  f"r0 {row['r0']['logloss'] if row['r0'] else float('nan'):.4f} -> {row['chosen']['logloss']:.4f}",
                  flush=True)
    meta = {"schema": 1, "built_from": str(a.records), "study": str(a.study),
            "fights": len({r.fight for r in recs}), "decisions": len(recs),
            "note": "ssbot.tools.forum_branch build; scoring only (P / J, O / BAIT), never the support"}
    Path(a.out).write_text(json.dumps({**meta, "types": model}, separators=(",", ":")), "utf-8")
    if a.report:
        Path(a.report).write_text(json.dumps({"test": str(a.test), "types": report}, indent=1), "utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("caches", nargs="+", type=Path)
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--extra-dir", type=Path, default=None)
    s.add_argument("--workers", type=int, default=3)
    s.add_argument("--max-fights", type=int, default=0)
    s = sub.add_parser("study")
    s.add_argument("records", type=Path)
    s.add_argument("--json", type=Path, required=True)
    s.add_argument("--min-n", type=int, default=60)
    s = sub.add_parser("build")
    s.add_argument("records", type=Path)
    s.add_argument("--study", type=Path, required=True)
    s.add_argument("--test", type=Path, default=None)
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--report", type=Path, default=None)
    a = ap.parse_args(argv)
    return {"scan": cmd_scan, "study": cmd_study, "build": cmd_build}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
