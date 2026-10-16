"""Task 1v1 SG4 part 1b: rescore the slam map (the person, 2026-10-15: "raise the danger-distance score; once hit you
cannot strike anyway"; forum.md 59). No planner, no game.

Each variant is a MapConfig (special_map): (a) a larger clearance weight WC / cap C_CAP; (b) the keyed pass with the
expected value over the measured late-input distribution (on time 78.5 %, +1 frame 20 %, +2 1 %, +3 0.5 %; a late
branch through damage counts 0); (c) the keyed pass with the one-frame-late key change as a hard partner; and their
combinations. Every variant runs SG2's closed loop (sg2_sim: 155 starts x 24 timing variants per physics phase, seeds
57 + p, lambda 0.02, the measured lateness for keys, presses and jumps, off-lattice starts) with the same seeds;
damage episodes from feasible starts are replayed without noise; readiness vs outcome; T1's trials (sg2_check: the
press certified in every phase -> precision / recall).

    ../scripts/uv.cmd run python -m ssbot.tools.sg4_rescore run --variant base [--phases 0-5]
    ../scripts/uv.cmd run python -m ssbot.tools.sg4_rescore merge --variants base,a1,...
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

from ssbot.combat import map_lookahead as ml
from ssbot.combat import special_map as sm
from ssbot.tools.sg2_sim import MEASURED_EXTRA, Sim, sim_variants, starts
from ssbot.tools.sg3_sim import run_set, noise_free
from ssbot.tools.sg3b_sim import SUMS, counts, summary
from ssbot.tools.special_map_build import setup

OUT = Path(r"C:\ssbot\data\m2_map\sg4\rescore")
VARIANTS = {
    "base": {},                                                           # SG2: WC 0.3, cap 1 u, no key state
    "a_w1c1": {"wc": 1.0, "c_cap": 1.0},
    "a_w1c2": {"wc": 1.0, "c_cap": 2.0},
    "a_w3c2": {"wc": 3.0, "c_cap": 2.0},
    "k_none": {"keyed": True, "key_noise": "none"},                       # the held key at the contact only
    "b_exp": {"keyed": True, "key_noise": "exp"},
    "c_hard": {"keyed": True, "key_noise": "hard"},
    "bc_hexp": {"keyed": True, "key_noise": "hard_exp"},
    "ac_w1c2": {"keyed": True, "key_noise": "hard", "wc": 1.0, "c_cap": 2.0},
    "abc_w1c2": {"keyed": True, "key_noise": "hard_exp", "wc": 1.0, "c_cap": 2.0},
    "ac_w2c2": {"keyed": True, "key_noise": "hard", "wc": 2.0, "c_cap": 2.0},
    "abc_w2c2": {"keyed": True, "key_noise": "hard_exp", "wc": 2.0, "c_cap": 2.0},
    "ac_w1c3": {"keyed": True, "key_noise": "hard", "wc": 1.0, "c_cap": 3.0},
    # SG7 (forum.md 63): ac_w1c3 + the hammer's polygons + the HeroBox's head + stage-aligned rows; parts alone
    "sg7": {"keyed": True, "key_noise": "hard", "wc": 1.0, "c_cap": 3.0, "poly": True, "head_u": 0.2187,
            "stage": True},
    "sg7_poly": {"keyed": True, "key_noise": "hard", "wc": 1.0, "c_cap": 3.0, "poly": True, "head_u": 0.2187},
    "sg7_stage": {"keyed": True, "key_noise": "hard", "wc": 1.0, "c_cap": 3.0, "stage": True},
    # SG7 hard2: the key change's +1 and +2 late paths both feasible (the measured +2 lateness is 1 %)
    "sg7h2": {"keyed": True, "key_noise": "hard2", "wc": 1.0, "c_cap": 3.0, "poly": True, "head_u": 0.2187,
              "stage": True},
    "sg7h2_poly": {"keyed": True, "key_noise": "hard2", "wc": 1.0, "c_cap": 3.0, "poly": True, "head_u": 0.2187},
    # SG7 review (forum.md 63.5): sg7 + the hammer carried one frame into the next state (the physics order)
    "sg7r": {"keyed": True, "key_noise": "hard", "wc": 1.0, "c_cap": 3.0, "poly": True, "head_u": 0.2187,
             "stage": True, "carry": True},
}
HEAD_U = 0.2187                    # the HeroBox's top above the physics box's (HeroBox.cs): the truth's hero box


def config(name: str) -> sm.MapConfig:
    """A variant by name; SG7 wall buckets: <variant>_f<U> (a wall U u in front of the anchor) / _b<U> (behind)."""
    wf = wb = None
    base = name
    if "_f" in name and name.rsplit("_f", 1)[1].replace(".", "").isdigit():
        base, u = name.rsplit("_f", 1)
        wf = float(u)
    elif "_b" in name and name.rsplit("_b", 1)[1].replace(".", "").isdigit():
        base, u = name.rsplit("_b", 1)
        wb = -float(u)
    return replace(sm.MapConfig(), **VARIANTS[base], wall_front=wf, wall_back=wb)


def readiness_bins(eps: list, wc: float) -> dict:
    """Raw counts per readiness bin (the score at the start; relative to the clearance-only score WC)."""
    bins = {"infeasible": lambda r: np.isneginf(r), "le_wc": lambda r: np.isfinite(r) and r <= wc + 1e-3,
            "wc_to_wc+1": lambda r: wc + 1e-3 < r < wc + 1.0, "wc+1_to_wc+2": lambda r: wc + 1.0 <= r < wc + 2.0,
            "ge_wc+2": lambda r: r >= wc + 2.0}
    out = {}
    for nm, f in bins.items():
        es = [e for e in eps if f(e.readiness)]
        out[nm] = {"n": len(es), "reach": sum(1 for e in es if e.hits and e.damage_f < 0),
                   "damage": sum(1 for e in es if e.damage_f >= 0), "hits": sum(e.hits for e in es)}
    return out


def trial_verdicts(geo, pm, trials, tc) -> dict:
    """Per T1 trial: the press certified in this phase (sg2_check.TrialCheck.phase on this map)."""
    out = {}
    if pm.S is not None and pm.S.ndim == 4:            # keyed: the trial check reads the node values per key
        pm = replace(pm, S=pm.S.max(1))
    for i, t in enumerate(trials):
        r = tc.prep(i, t)
        if r is None:
            continue
        v = tc.phase(pm, r)
        if not v["ok"]:
            continue
        out[i] = {"cert": bool(np.isfinite(v["sv"]) and v["approach_safe"]), "success": bool(t["success"]),
                  "kp": r["kp"]}
    return out


def run(a) -> int:
    from ssbot.tools.sg2_check import TrialCheck, load_trials
    t0 = time.time()
    cfg = config(a.variant)
    geo = setup(cfg)
    ti = ml.TubeIndex.from_geometry(geo)
    b = sm.builder_for(geo)
    from ssbot.combat.move_data import load_cl_slam
    vs = sim_variants(geo, a.quick, load_cl_slam(poly=True) if a.truth == "poly" else
                      load_cl_slam(poly=True, carry=True) if a.truth == "polyc" else None)
    st = starts(a.quick)
    trials = load_trials()
    tc = TrialCheck(geo)
    lo, hi = (int(v) for v in a.phases.split("-"))
    res = {"variant": a.variant, "config": cfg.key(), "phases": {}, "lam": a.lam, "seed": a.seed, "truth": a.truth,
           "noise": {"late_p": 0.2, "late_extra": MEASURED_EXTRA}, "geometry_s": round(time.time() - t0, 1)}
    for p in range(lo, hi + 1):
        t1 = time.time()
        pm = b.build(p, keep_full=True)
        bs = time.time() - t1
        src = ml.KeyedDenseSource(pm, ti, cfg) if cfg.keyed else ml.DenseSource(pm, ti)
        sim = Sim(geo, pm, np.random.default_rng(a.seed + p), src=src)
        sim.late_extra = MEASURED_EXTRA
        if a.truth in ("poly", "polyc"):
            sim.true_poly, sim.head_u = True, HEAD_U
        lat = []
        orig = ml.decide

        def timed(*args, _o=orig, **kw):
            t2 = time.perf_counter()
            r = _o(*args, **kw)
            lat.append(time.perf_counter() - t2)
            return r
        import ssbot.tools.sg2_sim as s2
        s2.ml.decide = timed
        try:
            eps = run_set(sim, vs, st, a.lam, p)
        finally:
            s2.ml.decide = orig
        noise_free(sim, eps, vs, st, a.lam, p)
        rp = counts(eps)
        rp["build_s"] = round(bs, 1)
        if sim.n_src:
            rp["sources_per_decision"] = {"mean": round(float(np.mean(sim.n_src)), 3), "max": int(max(sim.n_src))}
        rp["sim_s"] = round(time.time() - t1 - bs, 1)
        lt = np.array(lat) * 1e6
        rp["decision_us"] = {"p50": round(float(np.median(lt)), 1), "p99": round(float(np.quantile(lt, 0.99)), 1)}
        rp["readiness"] = readiness_bins(eps, cfg.wc)
        rp["readiness_k0"] = readiness_bins([e for e in eps if e.start in ("ground", "antic_entry") and e.k0 == 0],
                                            cfg.wc)
        rp["by_start"] = {}
        for grp in ("ground", "antic_entry", "hop", "bounce"):
            es = [e for e in eps if e.start.startswith(grp)]
            rp["by_start"][grp] = counts(es)
        rp["trials"] = trial_verdicts(geo, pm, trials, tc)
        # SG7: every episode compactly (start, k0, x0, d0, variant, ev k, start feasible, damaged, hits) so maps can be
        # compared on the starts feasible in both
        rp["episodes"] = [[e.start, e.k0, e.x0, e.d0, e.variant, int(np.isfinite(e.readiness)), int(e.damage_f >= 0),
                           int(e.hits)] for e in eps]
        rp["damage_examples"] = [{"start": e.start, "k0": e.k0, "x0": e.x0, "variant": e.variant, "d0": e.d0,
                                  "damage_f": e.damage_f, "contacts": e.contacts, "presses": e.presses,
                                  "readiness": e.readiness, "noise_free": e.noise_free_damage}
                                 for e in eps if e.damage_f >= 0][:25]
        res["phases"][p] = rp
        print(json.dumps({"p": p, **summary(rp), "build_s": rp["build_s"], "sim_s": rp["sim_s"],
                          "us": rp["decision_us"]}, default=float), flush=True)
        del pm, sim, src, eps
    res["seconds"] = round(time.time() - t0, 1)
    a.out.mkdir(parents=True, exist_ok=True)
    sd = f"_s{a.seed}" if a.seed != 57 else ""
    tr = {"poly": "_tpoly", "polyc": "_tpolyc"}.get(a.truth, "")
    (a.out / f"rescore_{a.variant}{sd}{tr}_p{lo}-{hi}{'_quick' if a.quick else ''}.json").write_text(
        json.dumps(res, indent=1, default=float), "utf-8")
    return 0


def prf(rows: list) -> dict:
    pred = np.array([r["cert"] for r in rows])
    real = np.array([r["success"] for r in rows])
    tp, fp, fn = int((pred & real).sum()), int((pred & ~real).sum()), int((~pred & real).sum())
    return {"n": len(rows), "certified": int(pred.sum()), "tp": tp, "fp": fp,
            "precision": round(tp / max(tp + fp, 1), 3), "recall": round(tp / max(tp + fn, 1), 3)}


def merge(a) -> int:
    out = {}
    for v in a.variants.split(","):
        files = sorted(a.out.glob(f"rescore_{v}_p*.json"))
        files = [f for f in files if "_quick" not in f.name]
        if not files:
            continue
        phases = {}
        cfg = None
        for f in files:
            r = json.loads(f.read_text("utf-8"))
            phases.update(r["phases"])
            cfg = r["config"]
        c = dict.fromkeys(SUMS, 0)
        rb, rb0 = {}, {}
        bs = {}
        tr: dict = {}
        for rp in phases.values():
            for k in SUMS:
                c[k] += rp[k]
            for src_, dst in ((rp["readiness"], rb), (rp["readiness_k0"], rb0)):
                for nm, x in src_.items():
                    d = dst.setdefault(nm, dict.fromkeys(x, 0))
                    for kk, vv in x.items():
                        d[kk] += vv
            for grp, x in rp["by_start"].items():
                d = bs.setdefault(grp, dict.fromkeys(SUMS, 0))
                for kk in SUMS:
                    d[kk] += x[kk]
            for i, t in rp["trials"].items():
                e = tr.setdefault(i, {"cert": True, "success": t["success"], "kp": t["kp"], "n": 0})
                e["cert"] &= t["cert"]
                e["n"] += 1
        rows = [t for t in tr.values() if t["n"] == len(phases)]
        row = summary(c)
        row["phases"] = sorted(int(p) for p in phases)
        row["config"] = {k: cfg[k] for k in ("wc", "c_cap", "keyed", "key_noise")}
        row["readiness"] = {nm: {"n": x["n"], "strike_no_damage": round(x["reach"] / max(x["n"], 1), 3),
                                 "damage": round(x["damage"] / max(x["n"], 1), 4),
                                 "hits_per_slam": round(x["hits"] / max(x["n"], 1), 3)} for nm, x in rb.items()}
        row["readiness_k0"] = {nm: {"n": x["n"], "strike_no_damage": round(x["reach"] / max(x["n"], 1), 3),
                                    "damage": round(x["damage"] / max(x["n"], 1), 4),
                                    "hits_per_slam": round(x["hits"] / max(x["n"], 1), 3)} for nm, x in rb0.items()}
        row["by_start"] = {g: summary(x) for g, x in bs.items()}
        row["t1_trials"] = prf(rows)
        row["t1_trials_k42_47"] = prf([r for r in rows if 42 <= r["kp"] <= 47])
        row["build_s_per_phase"] = max(rp["build_s"] for rp in phases.values())
        row["decision_us_p50"] = round(float(np.median([rp["decision_us"]["p50"] for rp in phases.values()])), 1)
        row["decision_us_p99"] = max(rp["decision_us"]["p99"] for rp in phases.values())
        out[v] = row
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / f"merged_{a.name}.json").write_text(json.dumps(out, indent=1, default=float), "utf-8")
    for v, row in out.items():
        print(v, {k: row[k] for k in ("strike_no_damage_pct", "damage_eps", "feasible_starts_damaged",
                                      "noise_free_damage", "hits_per_slam", "two_hits_pct", "key_changes_per_slam",
                                      "misses")}, "T1", row["t1_trials"])
    return 0


def store(a) -> int:
    """The run-time file of a variant (special_map_rt: uint8 levels per phase, zlib): built phase by phase."""
    from ssbot.combat import special_map_rt as rt
    from ssbot.tools.special_map_build import git_head
    t0 = time.time()
    cfg = config(a.variant)
    geo = setup(cfg)
    b = sm.builder_for(geo)
    scale = rt.level_scale(cfg.wc)
    arrs, clip, mx = {}, 0, 0.0
    for p in range(6):
        pm = b.build(p, keep_full=True)
        for arr in (pm.S, pm.SV):
            f = np.asarray(arr, np.float32)
            fin = np.isfinite(f)
            mx = max(mx, float(f[fin].max()) if fin.any() else 0.0)
            clip += int((f[fin] > 250 * scale).sum())
        arrs.update(rt.phase_levels(pm, cfg.keyed, scale))
        del pm
        print("phase", p, round(time.time() - t0, 1), flush=True)
    path = rt.map_path(a.tag)
    extra = {"variant": a.variant, "source_commit": git_head(), "ready_ref": a.ready_ref, "max_score": mx,
             "clipped_cells": clip}
    if cfg.stage:
        extra["stage"] = geo.row_table()
    meta = rt.save_levels(path, geo, arrs, list(range(6)), scale, extra)
    print(json.dumps({"path": str(path), "bytes": path.stat().st_size, "scale": scale, "max": mx, "clipped": clip,
                      "seconds": round(time.time() - t0, 1)}))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s_ = sub.add_parser("store")
    s_.add_argument("--variant", required=True)
    s_.add_argument("--tag", default="sg4")
    s_.add_argument("--ready-ref", type=float, default=None)
    r = sub.add_parser("run")
    r.add_argument("--variant", required=True)
    r.add_argument("--truth", choices=("box", "poly", "polyc"), default="box",
                   help="poly (SG7): the closed loop's damage on the hammer's polygons and the HeroBox's head; polyc "
                        "(SG7 review): also the hammer carried one frame into the next state (the physics order)")
    r.add_argument("--phases", default="0-5")
    r.add_argument("--quick", action="store_true")
    r.add_argument("--lam", type=float, default=0.02)
    r.add_argument("--seed", type=int, default=57)
    r.add_argument("--out", type=Path, default=OUT)
    m = sub.add_parser("merge")
    m.add_argument("--variants", default=",".join(VARIANTS))
    m.add_argument("--name", default="all")
    m.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    return {"run": run, "merge": merge, "store": store}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
