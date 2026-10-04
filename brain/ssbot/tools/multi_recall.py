"""Held-out support recall of the run-time multi-enemy forecast (Forum plan R2 acceptance (b), docs/plans/
forum_planner_plan.md §4.4 item 1): every logged hero contact must lie inside the support that
ssbot.combat.multi_forecast.MultiForecast made L frames earlier from the WorldStates (OracleBackend on the recording;
--view ve: plus the ObservabilityFilter with the placeholder per-type phase table), with the tables of the other fold.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.multi_recall dev
        --extra C:/ssbot/data/m2_forum_r0/build_all/extra --fights C:/ssbot/data/m2_forum_r0/build_all/fights.json
        --dev-json C:/ssbot/data/m2_forum_r0/recall_dev3.json [--workers 4] [--json out.json]
    ../scripts/uv.cmd run python -m ssbot.tools.multi_recall fresh --extra .../build_all/extra
        --fresh C:/ssbot/data/m2_forum_r0/fresh --fresh C:/ssbot/data/m2_forum_r2/r1 [--view ve] [--json out.json]
    ../scripts/uv.cmd run python -m ssbot.tools.multi_recall bellbeast <recording> [--frames N]

R0's protocol (ssbot.tools.support_recall --encounter Forum; forum.md §12.2):
  dev    the 107 build fights: fold k's fights against the tables of fold 1 - k (EnemyTables.fold: that fold's support
         templates and walk), each half of fold k with the margins R0 calibrated on the other half's contacts and the
         tubes calibrated on fold 1 - k (recall_dev3.json margins_by_group / tube_by_fold: the same numbers).
  fresh  fights the build never saw (behaviour_build --contacts-only directories: R0's 35 fresh fights, the R1 runs
         without the w2 ghost episodes), against each fold's tables with the production margins and tubes
         (support_margins.json).
Contacts (behaviour_build's attribution, contacts.jsonl.gz): every "damage" frame and every frame of a damage_blocked
stretch; multi-hit follow-ups are not checked (the first contact of a chain stands for it). The pairing is the
planner's: the hero box of frame c at t_c or of c - 1 at t_c-1, the forecast made at c - L. A contact counts as
covered when the union of every enemy's and hazard's support covers it (what the planner and the supervisor read);
"own" restricts the support to the enemies of the contact's type and the hazards they throw (R0's per-subject check,
with its same-name / unnamed-source candidates: every enemy of the type). Counted apart: what covered it - the forecast
(placements, hazard paths, death tails), the idle body tube, the collider / hazard tubes (the reaction-lag safety net).

bellbeast: acceptance (a) - a Bell Beast Forecaster wrapped in MultiForecaster(boss=...) gives the same forecasts,
support sets and planner decisions as the Forecaster itself, frame by frame on a recording.
"""
import argparse
import gzip
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

LAGS = (2, 3, 4)


def read_contacts(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def fight_of(row: dict) -> str:
    return row["fight"].rsplit("/", 1)[0]


def placeholder_specs():
    """BossSpecs of the Forum types with the placeholder observable-phase table: every Control state its own phase
    (until M3 measures per-type phase tables), so the vision view's tracker sees the states with the filter's timing."""
    from ssbot.combat.enemy_tables import FORUM_DIR
    from ssbot.core.bosses import BossSpec
    from ssbot.core.forum import FORUM_TYPES
    out = []
    for tk, sp in FORUM_TYPES.items():
        d = json.loads((FORUM_DIR / f"{sp.enemy}.json").read_text("utf-8"))
        states = set(d["dwell_s"]) | set(d["support_transitions"]) | set(sp.waiting) | set(sp.death_states)
        out.append(BossSpec(tk, sp.control_fsm, sp.death_states, float(sp.hp), {s: s for s in states}))
    return out


def wave_of(fight_id: str) -> int:
    """A wave-start run's first wave (Forum_A_w<i>_...), else 0."""
    run = fight_id.split("/")[0]
    for part in run.split("_"):
        if part.startswith("w") and part[1:].isdigit():
            return int(part[1:])
    return 0


def run_fight(job: dict) -> dict:
    """One fight's contacts against one MultiForecaster configuration (a worker process; tables cached per config)."""
    from ssbot.backends.oracle_backend import OracleBackend
    from ssbot.combat.multi_forecast import MultiForecaster
    from ssbot.core.worldstate import ORACLE, VISION_EQUIVALENT
    from ssbot.record.recorder import RecordingReader
    tables = _tables(job["config"])
    view = job.get("view", "oracle")
    mf = MultiForecaster(tables, ORACLE if view == "oracle" else VISION_EQUIVALENT)
    bosses = placeholder_specs() if view != "oracle" else []
    backend = OracleBackend(bosses=bosses)
    filt = None
    if view != "oracle":
        from ssbot.backends.observability import ObservabilityFilter
        filt = ObservabilityFilter(bosses=bosses)
        filt.reset(0)
    contacts = job["contacts"]
    need: dict[int, list] = defaultdict(list)
    stats: dict = defaultdict(Counter)
    for c in contacts:
        if c.get("follow"):
            stats[(c["type"], 0)]["follow-up (not checked)"] += 1
            continue
        for L in LAGS:
            need[int(c["f"]) - L].append((c, L))
    f0, f1 = job["f0"], job["f1"]
    r = RecordingReader(job["path"])
    t_of: dict[int, float] = {}
    misses = []
    n_fc = 0
    t_fc = 0.0
    wave = wave_of(job["id"])
    for s in r.states(f0 - 300, f1 + 2):
        f = s["f"]
        ws = backend.feed(s)
        if filt is not None:
            ws = filt.apply(ws)
        if f == f0:
            mf.notify_wake(ws.stamp.t_game_s, wave)
        mf.update(ws)
        t_of[f] = ws.stamp.t_game_s
        todo = need.get(f)
        if not todo:
            continue
        a = time.perf_counter()
        fc = mf.forecast(job.get("horizon", 0.1), clamp=False)
        t_fc += time.perf_counter() - a
        n_fc += 1
        T_o = ws.stamp.t_game_s
        for c, L in todo:
            _check(c, L, fc, mf, T_o, t_of, stats, misses, job["label"])
    return {"id": job["id"], "stats": {f"{k[0]}|{k[1]}": dict(v) for k, v in stats.items()}, "misses": misses,
            "forecasts": n_fc, "forecast_ms": round(1e3 * t_fc / max(1, n_fc), 3)}


def _check(c: dict, L: int, fc, mf, T_o: float, t_of: dict, stats: dict, misses: list, label: str) -> None:
    """The contact against the forecast at its origin (frames c - 1 and c; their times are known by then: the
    recording is read past c before the check runs, see below)."""
    key = (c["type"], L)
    st = stats[key]
    st["n"] += 1
    if c.get("family") is None:
        st["outside_attacks"] += 1
    c.setdefault("_pending", []).append((L, fc, T_o, key, label))


def _resolve(c: dict, t_of: dict, mf_types: dict, stats: dict, misses: list) -> None:
    pass


def main_fresh_dev(a, mode: str) -> int:
    from ssbot.combat.enemy_tables import parse_margins
    rows_by_fight: dict = {}
    jobs = []
    if mode == "dev":
        dev = json.loads(a.dev_json.read_text("utf-8"))
        build = json.loads((a.extra / "build.json").read_text("utf-8"))
        folds = {f["id"]: f["fold"] for f in build["fights"]}
        fl = {f["id"]: f for f in json.loads(a.fights.read_text("utf-8"))["fights"]}
        rows = read_contacts(a.extra / "contacts.jsonl.gz")
        for r in rows:
            rows_by_fight.setdefault(fight_of(r), []).append(r)
        for k in (0, 1):
            ids_all = [fid for fid, fd in folds.items() if fd == k]
            half = {fid: i % 2 for i, fid in enumerate(ids_all)}
            tube = dev["tube_by_fold"][str(k)]
            for h in (0, 1):
                name = f"fold{k}/half{h}"
                margins = dev["margins_by_group"][name]
                cfg = {"kind": "fold", "extra": str(a.extra), "fold": 1 - k, "margins": margins,
                       "tubes": {"idle_growth": tube["idle_growth"], "tube_speed": tube["tube_speed"],
                                 "body_hull": tube["body_hull"]}, "name": name}
                for fid in ids_all:
                    if half[fid] != h or fid not in fl:
                        continue
                    jobs.append(_job(fid, fl[fid], rows_by_fight.get(fid, []), cfg, name, a))
    else:
        md = json.loads(a.margins.read_text("utf-8"))
        prod = md["production_tubes"]
        for fdir in a.fresh:
            fl = json.loads((fdir / "fights.json").read_text("utf-8"))["fights"]
            rows = read_contacts(fdir / "contacts.jsonl.gz")
            byf: dict = defaultdict(list)
            for r in rows:
                byf[fight_of(r)].append(r)
            for j in a.tables:
                cfg = {"kind": "fold", "extra": str(a.extra), "fold": j, "margins": md["by_family"],
                       "tubes": {k: prod[k] for k in ("idle_growth", "tube_speed", "body_hull")},
                       "name": f"{fdir.name}/tables{j}"}
                for f in fl:
                    jobs.append(_job(f["id"], f, byf.get(f["id"], []), cfg, cfg["name"], a))
    if a.max_fights:
        keep = []
        per: Counter = Counter()
        for j in jobs:
            if per[j["label"]] < a.max_fights:
                keep.append(j)
                per[j["label"]] += 1
        jobs = keep
    return run_jobs(a, jobs, mode)


def _job(fid: str, f: dict, contacts: list, cfg: dict, label: str, a) -> dict:
    return {"id": fid, "path": f["path"], "f0": int(f["f0"]), "f1": int(f["f1"]), "contacts": contacts,
            "config": cfg, "label": label, "view": a.view, "horizon": a.horizon}


_TABLES: dict = {}


def _tables(cfg: dict):
    from ssbot.combat.enemy_tables import EnemyTables, Tubes, parse_margins
    key = json.dumps({k: cfg[k] for k in ("kind", "extra", "fold")}, sort_keys=True) + json.dumps(
        cfg["margins"], sort_keys=True)
    t = _TABLES.get(key)
    if t is None:
        _TABLES.clear()
        t = _TABLES[key] = EnemyTables.fold(Path(cfg["extra"]), int(cfg["fold"]), parse_margins(cfg["margins"]),
                                            Tubes.from_doc(cfg["tubes"]))
    return t


def run_jobs(a, jobs: list, mode: str) -> int:
    t0 = time.perf_counter()
    stats: dict = defaultdict(Counter)
    misses: list = []
    by_label: dict = defaultdict(lambda: defaultdict(Counter))
    fc_ms = []
    jobs.sort(key=lambda j: (j["label"], j["id"]))
    done = 0
    if a.workers > 1:
        ex = ProcessPoolExecutor(max_workers=a.workers, initializer=_init_worker)
        it = ex.map(run_fight_safe, jobs, chunksize=1)
    else:
        it = map(run_fight_safe, jobs)
    for j, res in zip(jobs, it):
        done += 1
        if "error" in res:
            print(f"[{done}/{len(jobs)}] {j['label']} {j['id']}: ERROR {res['error']}", flush=True)
            stats[("ERROR", 0)]["fights"] += 1
            continue
        for k, v in res["stats"].items():
            tk, L = k.split("|")
            stats[(tk, int(L))].update(v)
            by_label[j["label"]][(tk, int(L))].update(v)
        misses += res["misses"]
        fc_ms.append(res["forecast_ms"])
        n = sum(v["n"] for (tk, L), v in stats.items() if L)
        cov = sum(v["covered"] for (tk, L), v in stats.items() if L)
        print(f"[{done}/{len(jobs)}] {j['label']} {j['id']} covered {cov}/{n} misses {len(misses)} "
              f"({res['forecast_ms']} ms/forecast, {time.perf_counter() - t0:.0f} s)", flush=True)
    out = {"mode": mode, "view": a.view, "lags": list(LAGS), "fights": done, "horizon_s": a.horizon,
           "summary": summarise(stats), "by_group": {k: summarise(v)["recall"] for k, v in by_label.items()},
           "misses": misses[:500], "n_misses": len(misses),
           "miss_by": dict(Counter(f"{m['type']}/{m['family']}/{m['state']}/L{m['lag']}" for m in misses)
                           .most_common(60)),
           "forecast_ms_mean_per_fight": round(float(np.mean(fc_ms)), 3) if fc_ms else None,
           "elapsed_s": round(time.perf_counter() - t0, 1)}
    from ssbot.record.recorder import find_repo_root, git_info
    out["code"] = git_info(find_repo_root())
    print(json.dumps({k: out[k] for k in ("summary", "n_misses", "miss_by")}, indent=1))
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(out, indent=1), "utf-8")
    return 0


def summarise(stats: dict) -> dict:
    tot: dict = {}
    by: dict = {}
    for (tk, L), v in sorted(stats.items()):
        if not L:
            continue
        t = tot.setdefault(f"L{L}", Counter())
        t.update({k: v[k] for k in v})
        by[f"{tk}/L{L}"] = {"n": v["n"], "covered": v["covered"], "own": v["own"],
                            "recall": round(v["covered"] / v["n"], 6) if v["n"] else None,
                            "own_recall": round(v["own"] / v["n"], 6) if v["n"] else None,
                            **{k: v[k] for k in sorted(v) if k.startswith(("by ", "outside"))}}
    rec = {L: {"n": v["n"], "covered": v["covered"], "recall": round(v["covered"] / v["n"], 6) if v["n"] else None,
               "own": v["own"], "own_recall": round(v["own"] / v["n"], 6) if v["n"] else None,
               **{k: v[k] for k in sorted(v) if k.startswith("by ")}} for L, v in tot.items()}
    return {"recall": rec, "by_type": by}


def _init_worker() -> None:
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass


def run_fight_safe(job: dict) -> dict:
    try:
        return run_fight2(job)
    except Exception as e:           # a fight that fails is reported, the run goes on
        import traceback
        return {"error": f"{type(e).__name__}: {e} {traceback.format_exc()[-800:]}"}


def run_fight2(job: dict) -> dict:
    """run_fight with the checks done once both contact frames have been read (the planner's pairing needs t_c)."""
    from ssbot.backends.oracle_backend import OracleBackend
    from ssbot.combat.multi_forecast import MultiForecaster
    from ssbot.core.forum import FORUM_TYPES, HAZARD_OWNER
    from ssbot.core.worldstate import ORACLE, VISION_EQUIVALENT
    from ssbot.record.recorder import RecordingReader
    tables = _tables(job["config"])
    view = job.get("view", "oracle")
    mf = MultiForecaster(tables, ORACLE if view == "oracle" else VISION_EQUIVALENT)
    bosses = placeholder_specs() if view != "oracle" else []
    backend = OracleBackend(bosses=bosses)
    filt = None
    if view != "oracle":
        from ssbot.backends.observability import ObservabilityFilter
        filt = ObservabilityFilter(bosses=bosses)
        filt.reset(0)
    stats: dict = defaultdict(Counter)
    origins: dict[int, list] = defaultdict(list)
    checks: dict[int, list] = defaultdict(list)       # frame c -> [(contact, L)] checked once c is read
    for c in job["contacts"]:
        if c.get("follow"):
            stats[(c["type"], 0)]["follow-up (not checked)"] += 1
            continue
        for L in LAGS:
            origins[int(c["f"]) - L].append((c, L))
    f0, f1 = job["f0"], job["f1"]
    r = RecordingReader(job["path"])
    t_of: dict[int, float] = {}
    misses = []
    held: dict = {}                                   # (origin frame) -> (forecast, T_o, iids by type)
    n_fc, t_fc = 0, 0.0
    wave = wave_of(job["id"])
    last_f = None
    for s in r.states(f0 - 300, f1 + 2):
        f = s["f"]
        ws = backend.feed(s)
        if filt is not None:
            ws = filt.apply(ws)
        if last_f is not None and last_f < f0 <= f:
            mf.notify_wake(ws.stamp.t_game_s, wave)
        last_f = f
        mf.update(ws)
        t_of[f] = ws.stamp.t_game_s
        if f in origins:
            a = time.perf_counter()
            fc = mf.forecast(job.get("horizon", 0.1), clamp=False)
            t_fc += time.perf_counter() - a
            n_fc += 1
            by_type: dict = defaultdict(set)
            for tr in mf.trackers.values():
                by_type[tr.tk].add(tr.iid)
            for p in fc.paths:
                o = HAZARD_OWNER.get(p.type_key)
                if o is not None:
                    by_type[o].add(p.iid)
            for iid, h in mf.self_haz.items():
                o = HAZARD_OWNER.get(h[0])
                if o is not None:
                    by_type[o].add(iid)
            for owner, others in fc.groups.items():
                for o2 in others:
                    for tk_, ids in by_type.items():
                        if o2 in ids:
                            ids.add(owner)
            held[f] = (fc, ws.stamp.t_game_s, by_type)
            for c, L in origins[f]:
                checks[int(c["f"])].append((c, L, f))
        for c, L, o in checks.pop(f, ()):
            fc, T_o, by_type = held[o]
            _check2(c, L, fc, T_o, t_of, by_type, stats, misses, job["label"], s)
        for o in [o for o in held if o < f - 8]:
            del held[o]
    for cf, lst in checks.items():           # contact frames past the recording's end
        for c, L, o in lst:
            stats[(c["type"], L)]["n"] += 1
            stats[(c["type"], L)]["no frame"] += 1
    return {"id": job["id"], "stats": {f"{k[0]}|{k[1]}": dict(v) for k, v in stats.items()}, "misses": misses,
            "forecasts": n_fc, "forecast_ms": round(1e3 * t_fc / max(1, n_fc), 3)}


def _check2(c: dict, L: int, fc, T_o: float, t_of: dict, by_type: dict, stats: dict, misses: list, label: str,
            s: dict) -> None:
    key = (c["type"], L)
    st = stats[key]
    st["n"] += 1
    if c.get("family") is None:
        st["outside_attacks"] += 1
    cf = int(c["f"])
    boxes = c.get("boxes") or []
    pairs = list(zip((cf - 1, cf), boxes[-2:] if len(boxes) >= 2 else [None] + boxes))
    xs, ys, ts = [], [], []
    for fr, box in pairs:
        if box is None or fr not in t_of:
            continue
        xs.append(0.5 * (box[0] + box[2]))
        ys.append(0.5 * (box[1] + box[3]))
        ts.append(t_of[fr] - T_o)
    if not xs:
        st["no box"] += 1
        misses.append({"fight": c["fight"], "f": cf, "lag": L, "type": c["type"], "family": c.get("family"),
                       "state": c.get("state"), "why": "no box", "label": label})
        return
    order = np.argsort(ts)
    X = np.array([[xs[i] for i in order]])
    Y = np.array([[ys[i] for i in order]])
    tk = np.array([ts[i] for i in order])
    parts = fc.occupied_parts(X, Y, tk)
    hit = {k: bool(v.any()) for k, v in parts.items()}
    ok = any(hit.values())
    if ok:
        st["covered"] += 1
        how = "forecast" if hit["forecast"] else next(k for k in ("idle body tube", "collider tube", "hazard tube")
                                                       if hit[k])
        st[f"by {how}"] += 1
        own = fc.occupied_only(X, Y, tk, by_type.get(c["type"], set())).any()
        st["own"] += int(bool(own))
        return
    tr_states = {}
    misses.append({"fight": c["fight"], "f": cf, "lag": L, "type": c["type"], "family": c.get("family"),
                   "state": c.get("state"), "src": c.get("src"), "kind": c.get("kind"), "tk": c.get("tk"),
                   "hero": [round(v, 3) for v in (xs[-1], ys[-1])], "label": label,
                   "subjects": [(sb.iid, sb.state, sb.family, None if sb.pos is None else
                                 [round(sb.pos[0], 2), round(sb.pos[1], 2)]) for sb in fc.subjects
                                if sb.type_key == c["type"]][:6]})


def main_bellbeast(a) -> int:
    """(a): Forecaster vs MultiForecaster(boss=Forecaster) on a recording: placements, occupancy on a candidate grid,
    probabilities, support sets and planner decisions frame by frame."""
    import numba

    from ssbot.backends.oracle_backend import OracleBackend
    from ssbot.combat.boss_model import BossModel
    from ssbot.combat.forecast import Forecaster
    from ssbot.combat.multi_forecast import MultiForecaster
    from ssbot.combat.planner import Planner, PlannerConfig
    from ssbot.combat.safety_filter import FilterContext
    from ssbot.combat.tactics import Tactics, load_playbook
    from ssbot.core.bosses import BELL_BEAST
    from ssbot.core.worldstate import ORACLE
    from ssbot.knowledge.kinematics import HeroParams, HoldState, StateTracker, Terrain2D
    from ssbot.record.recorder import RecordingReader
    numba.set_num_threads(a.threads)
    r = RecordingReader(a.recording)
    params = HeroParams.load()
    terrain = None
    for _, m in r.terrain():
        if m.get("scene_raw") == "Bone_05" or m.get("scene") == "Bone_05":
            terrain = Terrain2D.from_message(m, params.scene("Bone_05"))
    terrain = terrain or Terrain2D.empty()
    model = BossModel.load()
    pb = load_playbook()

    def make_fc():
        fc = Forecaster(model, ORACLE, margin=(0.15, 0.25), comfort=(0.25, 0.25))
        fc.no_hurtbox, fc.shape_from = pb.no_hurtbox, pb.shape_from
        return fc
    fa = make_fc()
    mb = MultiForecaster(boss=make_fc())
    tac_a, tac_b = Tactics(pb), Tactics(pb)
    pl_a = Planner(params, terrain, PlannerConfig(threads=a.threads))
    pl_b = Planner(params, terrain, PlannerConfig(threads=a.threads))
    ba, bb = OracleBackend(bosses=[BELL_BEAST]), OracleBackend(bosses=[BELL_BEAST])
    trk = StateTracker(params, terrain)
    f0 = a.start if a.start is not None else r.index("state")[0].get("f0", 0)
    rng = np.random.default_rng(0)
    diff: Counter = Counter()
    n = 0
    prev = None
    for s in r.states(f0, f0 + a.frames + 1):
        if prev is None:
            prev = s
            continue
        wa, wb = ba.feed(prev), bb.feed(prev)
        trk.push(prev)
        if wa.game.scene.v != "Bone_05" or not prev.get("hero"):
            prev = s
            continue
        fa.update(wa)
        mb.update(wb)
        A = fa.forecast(2.0)
        B = mb.forecast(2.0)
        n += 1
        pa = [(p.key, p.t_ref, p.anchor, p.mirror, p.t_on, p.t_off, p.t_from) for p in A.placements]
        pbb = [(p.key, p.t_ref, p.anchor, p.mirror, p.t_on, p.t_off, p.t_from) for p in B.placements]
        diff["placements"] += pa != pbb
        hx, hy = wa.hero.pos.v
        X = hx + rng.uniform(-8, 8, (64, 25))
        Y = hy + rng.uniform(-3, 6, (64, 25))
        tk = np.arange(25) / 60.0
        diff["occupied"] += not np.array_equal(A.occupied(X, Y, tk), B.occupied(X, Y, tk))
        diff["prob"] += not np.array_equal(A.prob(X, Y, tk), B.prob(X, Y, tk))
        diff["support_set"] += A.support_set(wa) != B.support_set(wb)
        diff["committed"] += not np.array_equal(A.committed().occupied(X, Y, tk), B.committed().occupied(X, Y, tk))
        pa_ = tac_a.decide(wa, A, None, 3)
        pb_ = tac_b.decide(wb, B, None, 3)
        diff["tactics"] += repr(pa_) != repr(pb_)
        ctx_a = FilterContext.from_world(wa, None, 3, want_bind=pa_.want_bind)
        ctx_b = FilterContext.from_world(wb, None, 3, want_bind=pb_.want_bind)
        hold = HoldState.from_act(prev.get("act"))
        prefix = np.array([int((s.get("act") or {}).get("mask") or 0)])
        st = trk.state()
        ra = pl_a.tick(wa, st, hold, prefix, A, pa_, ctx_a)
        rb = pl_b.tick(wb, st, hold, prefix, B, pb_, ctx_b)
        same = (ra.name, ra.idx, ra.S, ra.forced_risk, tuple(np.asarray(ra.cmd).tolist())) == \
            (rb.name, rb.idx, rb.S, rb.forced_risk, tuple(np.asarray(rb.cmd).tolist()))
        diff["planner decision"] += not same
        prev = s
    out = {"recording": str(a.recording), "frames": n, "differences": {k: diff[k] for k in (
        "placements", "occupied", "prob", "support_set", "committed", "tactics", "planner decision")}}
    print(json.dumps(out, indent=1))
    if a.json:
        a.json.write_text(json.dumps(out, indent=1), "utf-8")
    return 0 if not any(diff.values()) else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=("dev", "fresh", "bellbeast"))
    ap.add_argument("recording", type=Path, nargs="?")
    ap.add_argument("--extra", type=Path, default=Path("C:/ssbot/data/m2_forum_r0/build_all/extra"))
    ap.add_argument("--fights", type=Path, default=Path("C:/ssbot/data/m2_forum_r0/build_all/fights.json"))
    ap.add_argument("--dev-json", type=Path, default=Path("C:/ssbot/data/m2_forum_r0/recall_dev3.json"))
    ap.add_argument("--fresh", type=Path, action="append", default=[])
    ap.add_argument("--tables", type=int, nargs="+", default=[0, 1], help="fresh: the folds' tables to test against")
    ap.add_argument("--margins", type=Path, default=None, help="fresh: support_margins.json (production)")
    ap.add_argument("--view", default="oracle", choices=("oracle", "ve"))
    ap.add_argument("--horizon", type=float, default=0.1)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--max-fights", type=int, default=0, help="per group")
    ap.add_argument("--frames", type=int, default=4000)
    ap.add_argument("--start", type=int, default=None)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    if a.mode == "bellbeast":
        if a.recording is None:
            ap.error("bellbeast needs a recording")
        return main_bellbeast(a)
    if a.margins is None:
        from ssbot.combat.enemy_tables import FORUM_DIR
        a.margins = FORUM_DIR / "support_margins.json"
    return main_fresh_dev(a, a.mode)


if __name__ == "__main__":
    sys.exit(main())
