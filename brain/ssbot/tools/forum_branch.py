"""Forum branch model (forum_planner_plan §5 R5, behaviour-model half): scan cached fights for decisions, study the
sensing timing and the history covariates on held-out fights, build knowledge/.../forum/branch_model.json, and check
that the runtime computes the covariates the model was selected on.

    cd brain   # below-normal priority, NUMBA_NUM_THREADS 4
    ..\\scripts\\uv.cmd run python -m ssbot.tools.forum_branch scan <cache dir> [<cache dir> ...] --out recs_dev.pkl
        [--ahead-out ahead_dev.pkl] [--extra-dir DIR] [--workers 3]
    ..\\scripts\\uv.cmd run python -m ssbot.tools.forum_branch study recs_dev.pkl --json study.json
    ..\\scripts\\uv.cmd run python -m ssbot.tools.forum_branch study ahead_dev.pkl --json study_ahead.json
    ..\\scripts\\uv.cmd run python -m ssbot.tools.forum_branch build recs_dev.pkl --study study.json
        [--ahead ahead_dev.pkl --ahead-study study_ahead.json] [--test recs_test.pkl --ahead-test ahead_test.pkl]
        --out <branch_model.json> [--report report.json]
    ..\\scripts\\uv.cmd run python -m ssbot.tools.forum_branch parity <cache.npz> [...] --model branch_model.json
        [--extra-dir DIR] [--frames N] [--json out.json]

scan: the fire-frame records (one per exit of a decision state) and, with --ahead-out, the forecast samples (every
forum_branch.AHEAD_DT s of each visit, labelled with how the visit ended) of every cached fight (forum_cache), with the
hero's silk from the recording (cached as <extra-dir>/<cache name>.hero.npz). Folds: the fights alternate by sorted id
(two folds). study: per decision, the CV log loss of the unconditional table (the runtime's p_succ for the fire-frame
records), the R0 tables' conditioner names refit on these rows ("r0_refit"), and the greedy selection per timing
(geometry only / geometry + history). build: the chosen tables fit on all scanned fights ("types": fire-frame,
"ahead": forecast); --test / --ahead-test evaluate them on other fights. The forecast report compares, on the test
fights' samples (the frames the planner queries): the per-visit unconditional table (today's p_succ), the fire-frame
model queried mid-state (what next_p was before the forecast tables), the forecast table; overall and on the samples
0.2-0.3 s and 0.5-0.6 s before the exit. parity: replays each cached fight's recording through the runtime
(OracleBackend -> MultiForecaster(branch=...)) and compares, on every frame an enemy is in a modelled decision state,
the covariates BranchView computes with the scan's (every-frame samples), and times next_attack_probs per frame.
"""
import argparse
import ctypes
import json
import math
import os
import pickle
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from ssbot.knowledge import forum_branch as fb
from ssbot.knowledge.forum_cache import load_cache

FORUM_DIR = Path(__file__).resolve().parents[3] / "knowledge" / "1.0.30000" / "enemies" / "forum"
R0_TABLES = {"Song Heavy Sentry": "ChoirClapper", "Song Handmaiden": "Clawmaiden", "Song Administrator": "Minister",
             "Song Pilgrim Maestro": "Maestro", "Song Automaton Tiny": "MaestroAutomaton", "Song Reed": "Reed",
             "Song Pilgrim 01": "Envoy", "Song Pilgrim 03": "Choristor", "Pilgrim 03 Song": "ChoirBellbearer"}
EXIT_BUCKETS = ((0.2, 0.3), (0.5, 0.6))
FIRE_TO_AHEAD = {"branch": "now", "entry": "entry", "stored": "stored"}


def _below_normal() -> None:
    if os.name == "nt":
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)


def _extra(path: Path, c: dict, extra_dir) -> dict | None:
    if extra_dir is None:
        return None
    xp = Path(extra_dir) / (Path(path).stem + ".hero.npz")
    if xp.exists():
        with np.load(xp) as z:
            return {k: z[k] for k in z.files}
    extra = fb.hero_extra(c["meta"])
    xp.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(xp, **extra)
    return extra


def _scan_one(args) -> tuple[str, list, list, str | None]:
    path, extra_dir, ahead_dt = args
    _below_normal()
    try:
        c = load_cache(Path(path))
        recs, samples = fb.scan_fight(c, _extra(Path(path), c, extra_dir), ahead_dt)
        return c["meta"]["id"], recs, samples, None
    except Exception as e:  # noqa: BLE001 - one bad fight must not stop the scan
        return str(path), [], [], f"{type(e).__name__}: {e}"


def _paths(dirs) -> list[Path]:
    return sorted(p for d in dirs for p in Path(d).glob("*.npz") if not p.name.endswith(".hero.npz"))


def cmd_scan(a) -> int:
    paths = _paths(a.caches)
    if a.max_fights:
        paths = paths[:a.max_fights]
    t0 = time.perf_counter()
    recs, samples, errors = [], [], []
    ahead_dt = fb.AHEAD_DT if a.ahead_out else None
    jobs = [(str(p), str(a.extra_dir) if a.extra_dir else None, ahead_dt) for p in paths]
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for i, (fid, rr, ss, err) in enumerate(ex.map(_scan_one, jobs, chunksize=1)):
            if err:
                errors.append((fid, err))
            recs += rr
            samples += ss
            print(f"[{i + 1}/{len(jobs)}] {fid}: {len(rr)} decisions, {len(ss)} samples"
                  f"{' ERROR ' + err if err else ''}", flush=True)
    fights = sorted({r.fight for r in recs})
    fold = {f: i % 2 for i, f in enumerate(fights)}
    meta = {"fold": fold, "caches": [str(d) for d in a.caches], "errors": errors}
    with open(a.out, "wb") as fh:
        pickle.dump({"records": recs, "kind": "fire", **meta}, fh)
    if a.ahead_out:
        with open(a.ahead_out, "wb") as fh:
            pickle.dump({"records": samples, "kind": "ahead", "ahead_dt": ahead_dt,
                         "ahead_dt_tiny": fb.AHEAD_DT_TINY, **meta}, fh)
    print(f"{len(recs)} decisions, {len(samples)} forecast samples from {len(fights)} fights in "
          f"{time.perf_counter() - t0:.0f} s; {len(errors)} errors")
    return 0


def _load(path: Path) -> tuple[list, dict, str]:
    with open(path, "rb") as fh:
        d = pickle.load(fh)
    return d["records"], d["fold"], d.get("kind", "fire")


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
    recs, fold, kind = _load(a.records)
    out = {}
    t0 = time.perf_counter()
    for (tk, st), rr in sorted(_groups(recs).items()):
        outs = {r.outcome for r in rr}
        if len(outs) < 2 or len(rr) < a.min_n:
            continue
        dd = fb.decision_data(rr, fold)
        res = fb.study_decision(dd, _r0_conditioners(tk, st) if kind == "fire" else None)
        out.setdefault(tk, {})[st] = res
        ch = res["chosen"]
        print(f"{tk:22} {st:22} n={res['n']:7} uncond {res['uncond']['logloss']:.4f} "
              f"r0_refit {res.get('r0_refit', {}).get('logloss', float('nan')):.4f} -> {ch['logloss']:.4f} "
              f"[{ch['timing']}] {ch['covariates']}  ({time.perf_counter() - t0:.0f} s)", flush=True)
    Path(a.json).write_text(json.dumps({"records": str(a.records), "kind": kind, "select_gain": fb.SELECT_GAIN,
                                        "max_covariates": fb.MAX_COVARIATES, "types": out}, indent=1), "utf-8")
    return 0


def _ll_summary(P: np.ndarray, y: np.ndarray, ll: np.ndarray, mask: np.ndarray | None = None) -> dict:
    if mask is not None:
        P, y, ll = P[mask], y[mask], ll[mask]
    if not len(y):
        return {"n": 0}
    return {"n": int(len(y)), "logloss": round(float(ll.mean()), 5), "sum": float(ll.sum()),
            **fb.calibration(P, y)}


def cmd_build(a) -> int:
    _below_normal()
    recs, fold, _ = _load(a.records)
    study = json.loads(Path(a.study).read_text("utf-8"))["types"]
    test_groups = {}
    if a.test:
        trecs, _, _ = _load(a.test)
        test_groups = _groups(trecs)
        del trecs
    fire_groups = _groups(recs)
    del recs
    model, report, fire_dd = {}, {}, {}
    for (tk, st), rr in sorted(fire_groups.items()):
        res = study.get(tk, {}).get(st)
        if res is None:
            continue
        dd = fire_dd[(tk, st)] = fb.decision_data(rr, fold)
        ch = res["chosen"]
        model.setdefault(tk, {})[st] = fb.fit_tables(dd, ch["timing"], ch["covariates"])
        model[tk][st]["cv_logloss"] = ch["logloss"]
        tr = test_groups.get((tk, st))
        if tr:
            td = fb.decision_data(tr, {}, timings=tuple(dict.fromkeys((ch["timing"], "branch"))))
            r0 = res.get("r0_refit", {}).get("conditioners") or []
            r0_names = []
            for n in r0:
                k = fb.R0_ALIASES.get(n, n)
                if k in dd.hist and k in td.hist:
                    r0_names.append(f"h:{k}")
                elif k in dd.geo.get("branch", {}) and k in td.geo.get("branch", {}):
                    r0_names.append(f"g:{k}")
            row = {"chosen": fb.holdout_eval(dd, td, ch["timing"], ch["covariates"]),
                   "uncond": fb.holdout_eval(dd, td, "branch", []),
                   "r0_refit": fb.holdout_eval(dd, td, "branch", r0_names) if r0_names else None}
            report.setdefault(tk, {})[st] = row
            print(f"{tk:22} {st:22} test n={row['chosen']['n']:6} uncond {row['uncond']['logloss']:.4f} "
                  f"r0_refit {row['r0_refit']['logloss'] if row['r0_refit'] else float('nan'):.4f} -> "
                  f"{row['chosen']['logloss']:.4f}", flush=True)
    del test_groups
    ahead_model, ahead_report = {}, {}
    if a.ahead:
        ahead_model, ahead_report = _build_ahead(a, study, fire_dd)
    meta = {"schema": 2, "built_from": str(a.records), "study": str(a.study), "ahead_from": str(a.ahead),
            "ahead_study": str(a.ahead_study), "ahead_dt": fb.AHEAD_DT, "ahead_dt_tiny": fb.AHEAD_DT_TINY,
            "fights": len({r.fight for rr in fire_groups.values() for r in rr}),
            "decisions": sum(len(rr) for rr in fire_groups.values()),
            "note": "ssbot.tools.forum_branch build; scoring only (P / J, O / BAIT), never the support; types: "
                    "P(successor | the decision fires now); ahead: P(the successor the visit ends in | now)"}
    Path(a.out).write_text(json.dumps({**meta, "types": model, "ahead": ahead_model}, separators=(",", ":")),
                           "utf-8")
    if a.report:
        Path(a.report).write_text(json.dumps({"test": str(a.test), "ahead_test": str(a.ahead_test), "types": report,
                                              "ahead": ahead_report}, indent=1), "utf-8")
    return 0


def _build_ahead(a, fire_study: dict, fire_dd: dict) -> tuple[dict, dict]:
    srecs, sfold, _ = _load(a.ahead)
    study = json.loads(Path(a.ahead_study).read_text("utf-8"))["types"]
    groups = _groups(srecs)
    del srecs
    test_groups = {}
    if a.ahead_test:
        trecs, _, _ = _load(a.ahead_test)
        test_groups = _groups(trecs)
        del trecs
    model, report = {}, {}
    tot: dict = defaultdict(lambda: defaultdict(float))
    for (tk, st), rr in sorted(groups.items()):
        res = study.get(tk, {}).get(st)
        if res is None:
            continue
        dd = fb.decision_data(rr, sfold)
        ch = res["chosen"]
        model.setdefault(tk, {})[st] = fb.fit_tables(dd, ch["timing"], ch["covariates"])
        model[tk][st]["cv_logloss"] = ch["logloss"]
        tr = test_groups.get((tk, st))
        if not tr:
            continue
        td = fb.decision_data(tr, {})
        arms = {"ahead": fb.holdout_ll(dd, td, ch["timing"], ch["covariates"]),
                "uncond_sample": fb.holdout_ll(dd, td, "now", [])}
        fdd = fire_dd.get((tk, st))
        fch = (fire_study.get(tk, {}).get(st) or {}).get("chosen")
        if fdd is not None:
            arms["uncond_visit"] = fb.holdout_ll(fdd, td, "branch", [], "now")
            if fch is not None and fch["timing"] in FIRE_TO_AHEAD:
                arms["fire_mid"] = fb.holdout_ll(fdd, td, fch["timing"], fch["covariates"],
                                                 FIRE_TO_AHEAD[fch["timing"]])
        row = {"covariates": ch["covariates"], "timing": ch["timing"], "cv_logloss": ch["logloss"]}
        masks = {"all": None, **{f"exit_{lo}_{hi}": (td.to_exit >= lo - 1e-9) & (td.to_exit < hi - 1e-9)
                                 for lo, hi in EXIT_BUCKETS}}
        for mk, mask in masks.items():
            row[mk] = {arm: _ll_summary(*v, mask) for arm, v in arms.items()}
            if "fire_mid" in arms:
                # the decisions the fire-frame model can be queried for mid-state: all four arms on the same rows
                for arm, s in row[mk].items():
                    if s.get("n"):
                        tot[f"{mk}|common"][f"{arm}_sum"] += s["sum"]
                        tot[f"{mk}|common"][f"{arm}_n"] += s["n"]
            for arm in ("ahead", "uncond_sample", "uncond_visit"):
                s = row[mk].get(arm) or {}
                if s.get("n"):
                    tot[f"{mk}|all"][f"{arm}_sum"] += s["sum"]
                    tot[f"{mk}|all"][f"{arm}_n"] += s["n"]
        report.setdefault(tk, {})[st] = row
        al = row["all"]
        print(f"AHEAD {tk:22} {st:20} test n={al['ahead']['n']:7} uncond_visit "
              f"{al.get('uncond_visit', {}).get('logloss', float('nan')):.4f} fire_mid "
              f"{al.get('fire_mid', {}).get('logloss', float('nan')):.4f} -> {al['ahead']['logloss']:.4f} "
              f"[{ch['timing']}] {ch['covariates']}", flush=True)
    summary = {}
    for k, v in tot.items():
        summary[k] = {arm[:-4]: {"n": int(v[arm[:-4] + "_n"]), "logloss": round(v[arm] / v[arm[:-4] + "_n"], 5)}
                      for arm in v if arm.endswith("_sum") and v[arm[:-4] + "_n"]}
        print("AHEAD TOTAL", k, json.dumps(summary[k]), flush=True)
    report["_summary"] = summary
    return model, report


# ---- parity: the runtime's covariates vs the scan's ---------------------------------------------------------------

def _parity_one(args) -> dict:
    try:
        return _parity(*args)
    except Exception as e:  # noqa: BLE001 - one bad fight must not stop the check
        return {"id": str(args[0]), "error": f"{type(e).__name__}: {e}", "frames": 0, "stats": {},
                "differences": {}, "cost_ms": {}}


def _parity(path: str, model_path: str, extra_dir: str | None, max_frames: int) -> dict:
    _below_normal()
    from ssbot.backends.oracle_backend import OracleBackend
    from ssbot.combat.branch_model import BranchModel
    from ssbot.combat.enemy_tables import EnemyTables
    from ssbot.combat.multi_forecast import MultiForecaster
    from ssbot.core.worldstate import ORACLE
    from ssbot.record.recorder import RecordingReader
    c = load_cache(Path(path))
    meta = c["meta"]
    f0, f1 = int(meta["f0"]), int(meta["f1"])
    if max_frames:
        f1 = min(f1, f0 + max_frames)
    _, samples = fb.scan_fight(c, _extra(Path(path), c, extra_dir), 0.0, every_frame=True)
    off = {}
    for r in samples:
        off[(int(c["f"][r.fi]), r.iid)] = r
    model = BranchModel.load(Path(model_path))
    mf = MultiForecaster(EnemyTables.production(), ORACLE, waves=False, branch=model)
    bv = mf.bv
    backend = OracleBackend()
    stats: Counter = Counter()
    bad: Counter = Counter()
    examples: dict = {}
    cost = []
    T0 = None
    for s in RecordingReader(meta["path"]).states(f0, f1):
        f = s["f"]
        ws = backend.feed(s)
        mf.update(ws)
        T = ws.stamp.t_game_s
        if T0 is None:
            T0 = T
        a0 = time.perf_counter()
        for tr in mf.trackers.values():
            if tr.mem is not None and not tr.dead:
                bv.next_attack_probs(tr, T, mf.trackers)
        cost.append(time.perf_counter() - a0)
        for iid, tr in mf.trackers.items():
            m = tr.mem
            if m is None or m.state is None or m.state not in m.choice_states or (tr.tk, m.state) in fb.AHEAD_SKIP:
                continue
            r = off.get((f, iid))
            if r is None:
                stats["runtime only"] += 1
                bad[f"runtime only|{tr.tk}|{m.state}"] += 1
                continue
            if r.state != m.state or abs(r.t_in - (T - m.t_entry)) > 1e-4:
                stats["state / entry differ"] += 1
                bad[f"state / entry differ|{tr.tk}|{r.state}|{m.state}"] += 1
                continue
            stats["compared"] += 1
            got = dict(m.features(m.state, T, bv.context(tr, mf.trackers, T)))
            want = dict(r.hist)
            for tm in fb.AHEAD_TIMINGS:
                g = bv.geo_at(tr, m.state, T, tm)
                w = fb.geo_features(tr.tk, r.geo, tm, fb.AHEAD_TIMINGS)
                got.update({f"{tm}:{k}": v for k, v in g.items()})
                want.update({f"{tm}:{k}": v for k, v in w.items()})
            diff = [k for k in set(got) | set(want) if got.get(k) != want.get(k)]
            if diff:
                stats["rows with a difference"] += 1
            for k in diff:
                key = f"{tr.tk}|{k.split('_')[0] if k.startswith(('since_', 'miss_')) else k}"
                bad[key] += 1
                examples.setdefault(key, {"f": f, "iid": iid, "state": m.state, "runtime": repr(got.get(k)),
                                          "scan": repr(want.get(k))})
    ms = np.array(cost) * 1e3
    return {"id": meta["id"], "frames": len(cost), "stats": dict(stats), "differences": dict(bad),
            "examples": examples, "scan_samples": len(samples),
            "cost_ms": {"p50": round(float(np.percentile(ms, 50)), 3), "p99": round(float(np.percentile(ms, 99)), 3),
                        "max": round(float(ms.max()), 3)} if len(ms) else {}}


def cmd_parity(a) -> int:
    paths = [p for x in a.caches for p in (_paths([x]) if Path(x).is_dir() else [Path(x)])]
    jobs = [(str(p), str(a.model), str(a.extra_dir) if a.extra_dir else None, a.frames) for p in paths]
    res = []
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for r in ex.map(_parity_one, jobs, chunksize=1):
            res.append(r)
            print(json.dumps({k: r[k] for k in ("id", "frames", "stats", "differences", "cost_ms", "error") if k in r}),
                  flush=True)
    tot, diff = Counter(), Counter()
    for r in res:
        tot.update(r["stats"])
        diff.update(r["differences"])
    print("TOTAL", json.dumps(dict(tot)), json.dumps(dict(diff.most_common(40))))
    if a.json:
        Path(a.json).write_text(json.dumps({"fights": res, "total": dict(tot), "differences": dict(diff)},
                                           indent=1), "utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("caches", nargs="+", type=Path)
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--ahead-out", type=Path, default=None)
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
    s.add_argument("--ahead", type=Path, default=None)
    s.add_argument("--ahead-study", type=Path, default=None)
    s.add_argument("--ahead-test", type=Path, default=None)
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--report", type=Path, default=None)
    s = sub.add_parser("parity")
    s.add_argument("caches", nargs="+", type=Path)
    s.add_argument("--model", type=Path, default=FORUM_DIR / "branch_model.json")
    s.add_argument("--extra-dir", type=Path, default=None)
    s.add_argument("--frames", type=int, default=0)
    s.add_argument("--workers", type=int, default=3)
    s.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    return {"scan": cmd_scan, "study": cmd_study, "build": cmd_build, "parity": cmd_parity}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
