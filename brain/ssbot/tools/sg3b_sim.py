"""Task 1v1 SG3b: SG3's closed loop on the equal-area contour files (forum.md 58). No planner, no game.

Per physics phase, SG2's starts x timing variants (the same seeds, execution noise and lambda as SG3,
ssbot.tools.sg3_sim):
  dense      SG2's policy on the dense values; every equal-area variant shadows it (decides on every visited state;
             a differing decision is classified by its cost on the dense values);
  <variant>  the same policy on that variant's tube contour file (special_map_CL_SLAM_tubes_p<p>_<variant>.npz,
             score_contours_build tubes --bands/--scope/--tol), e.g. ea4f = 4 bands, frame scope, inner rings exact.
Damage episodes from feasible starts are replayed without execution noise. Per variant the decision latency (one
lookahead), the file size, the load / prepare time and the query arrays' bytes are recorded. Raw counts are stored per
phase, so the per-phase files merge exactly (merge).

    ../scripts/uv.cmd run python -m ssbot.tools.sg3b_sim run --phases 0-1 --variants ea3l,ea4l,ea5l,ea3f,ea4f,ea5f
    ../scripts/uv.cmd run python -m ssbot.tools.sg3b_sim merge sim_*_p0-1.json sim_*_p2-3.json ... --name all
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from ssbot.combat import map_lookahead as ml
from ssbot.combat import score_contours as sc
from ssbot.combat import special_map as sm
from ssbot.tools.sg2_sim import Sim, sim_variants, starts
from ssbot.tools.sg3_sim import TimedSource, gap_table, noise_free, run_set
from ssbot.tools.special_map_build import setup

OUT = Path(r"C:\ssbot\data\m2_map\sg3b")
SUMS = ("n", "reach", "damage_eps", "hits", "key_changes", "presses", "misses", "two_hits", "fs_n", "fs_of",
        "fs_noise_free")


def counts(eps: list) -> dict:
    """Raw sums of a run (merge by adding)."""
    c = dict.fromkeys(SUMS, 0)
    for e in eps:
        c["n"] += 1
        c["reach"] += int(e.hits > 0 and e.damage_f < 0)
        c["damage_eps"] += int(e.damage_f >= 0)
        c["hits"] += e.hits
        c["two_hits"] += int(e.hits >= 2 and e.damage_f < 0)
        c["key_changes"] += e.key_changes
        c["presses"] += len(e.presses)
        c["misses"] += e.misses
        fs = bool(np.isfinite(e.readiness))
        c["fs_of"] += int(fs)
        c["fs_n"] += int(fs and e.damage_f >= 0)
        c["fs_noise_free"] += int(e.noise_free_damage is not None and e.noise_free_damage >= 0)
    return c


def summary(c: dict) -> dict:
    n = max(c["n"], 1)
    return {"n": c["n"], "strike_no_damage_pct": round(100 * c["reach"] / n, 2), "damage_eps": c["damage_eps"],
            "feasible_starts_damaged": f'{c["fs_n"]} / {c["fs_of"]}',
            "feasible_damaged_pct": round(100 * c["fs_n"] / max(c["fs_of"], 1), 3),
            "noise_free_damage": c["fs_noise_free"], "hits_per_slam": round(c["hits"] / n, 3),
            "two_hits_pct": round(100 * c["two_hits"] / n, 2), "key_changes_per_slam": round(c["key_changes"] / n, 2),
            "presses_per_slam": round(c["presses"] / n, 3), "misses": c["misses"]}


def ram_bytes(cs: sc.ContourSet) -> int:
    """The query arrays of every layer after prepare(): ring points, offsets, bboxes, level offsets, levels, parents."""
    tot = 0
    for lay in cs.layers.values():
        pts, rso, rbb, lvl_off = lay._flat()
        tot += pts.nbytes + rso.nbytes + rbb.nbytes + lvl_off.nbytes + lay.level.nbytes + lay.parent.nbytes
    return tot


def run(a) -> int:
    t0 = time.time()
    geo = setup()
    ti = ml.TubeIndex.from_geometry(geo)
    b = sm.MapBuilder(geo)
    vs = sim_variants(geo, a.quick)
    st = starts(a.quick)
    lo, hi = (int(v) for v in a.phases.split("-"))
    names = [v for v in a.variants.split(",") if v]
    res = {"phases": {}, "lam": a.lam, "seed": a.seed, "variants": names, "quick": a.quick}
    for p in range(lo, hi + 1):
        pm = b.build(p, keep_full=True)
        rp = {"files": {}}
        srcs = {}
        for v in names:
            path = sm.MAP_DIR / f"special_map_CL_SLAM_tubes_p{p}_{v}.npz"
            t1 = time.time()
            cs = sc.ContourSet.load(path)
            t2 = time.time()
            prep = cs.prepare()
            rp["files"][v] = {"bytes": path.stat().st_size, "load_s": round(t2 - t1, 2), "prepare_s": round(prep, 2),
                              "ram_mb": round(ram_bytes(cs) / 1e6, 1), "layers": len(cs.layers),
                              "banding": {k: cs.meta.get("banding", {"mode": "step", "step": cs.step}).get(k) for k in ("mode", "bands", "scope", "tol", "step")}}
            srcs[v] = ml.ContourSource(cs, ti, p)
        dsrc = ml.DenseSource(pm, ti)
        sim = Sim(geo, pm, np.random.default_rng(a.seed + p), src=dsrc)
        sim.shadows = [{"name": v, "src": s_, "n": 0, "diff": 0, "gaps": [], "ex": [], "max_ex": 10}
                       for v, s_ in srcs.items()]
        eps = run_set(sim, vs, st, a.lam, p)
        noise_free(sim, eps, vs, st, a.lam, p)
        rp["dense"] = counts(eps)
        rp["agreement"] = {sh["name"]: {"decisions": sh["n"], "differ": sh["diff"],
                                        "gaps": gap_table(sh["gaps"], 0.0, a.lam), "examples": sh["ex"]}
                           for sh in sim.shadows}
        for v, s_ in srcs.items():
            tsrc = TimedSource(s_)
            sim = Sim(geo, pm, np.random.default_rng(a.seed + p), src=tsrc)
            lat, nq = [], []
            orig = ml.decide

            def timed(src, *args, _o=orig, **kw):
                q0 = tsrc.nq
                t1 = time.perf_counter()
                r = _o(src, *args, **kw)
                lat.append(time.perf_counter() - t1)
                nq.append(tsrc.nq - q0)
                return r
            import ssbot.tools.sg2_sim as s2
            s2.ml.decide = timed
            try:
                e2 = run_set(sim, vs, st, a.lam, p)
            finally:
                s2.ml.decide = orig
            noise_free(sim, e2, vs, st, a.lam, p)
            lt = np.array(lat) * 1e6
            rp[v] = counts(e2)
            rp[v]["decision_us"] = {"p50": round(float(np.median(lt)), 1), "p99": round(float(np.quantile(lt, 0.99)), 1),
                                    "queries_p50": float(np.median(nq)), "queries_max": int(np.max(nq)),
                                    "decisions": len(lt)}
        res["phases"][p] = rp
        print(json.dumps({"p": p, "dense": summary(rp["dense"]),
                          **{v: dict(summary(rp[v]), same=round(1 - rp["agreement"][v]["differ"] /
                                                                 max(rp["agreement"][v]["decisions"], 1), 4),
                                     us=rp[v]["decision_us"]["p50"]) for v in names}}, default=float), flush=True)
        del pm, sim, srcs
    res["seconds"] = round(time.time() - t0, 1)
    a.out.mkdir(parents=True, exist_ok=True)
    nm = f"sim_{a.tag or '_'.join(names)}_p{lo}-{hi}{'_quick' if a.quick else ''}.json"
    (a.out / nm).write_text(json.dumps(res, indent=1, default=float), "utf-8")
    return 0


def merge(a) -> int:
    """Pool the per-phase raw counts of several run files into one table per source."""
    phases, names = {}, None
    for f in a.files:
        r = json.loads(Path(f).read_text("utf-8"))
        names = names or r["variants"]
        phases.update(r["phases"])
    out = {"phases": sorted(int(p) for p in phases), "sources": {}}
    for src in ["dense"] + names:
        c = dict.fromkeys(SUMS, 0)
        for rp in phases.values():
            for k in SUMS:
                c[k] += rp[src][k]
        row = summary(c)
        if src != "dense":
            dec = sum(rp["agreement"][src]["decisions"] for rp in phases.values())
            dif = sum(rp["agreement"][src]["differ"] for rp in phases.values())
            row["identical_decisions_pct"] = round(100 * (1 - dif / max(dec, 1)), 2)
            kinds = {}
            for rp in phases.values():
                for k, v in rp["agreement"][src]["gaps"].get("kinds", {}).items():
                    kinds[k] = kinds.get(k, 0) + v
            row["differ_kinds"] = kinds
            row["value_gap_max"] = max(rp["agreement"][src]["gaps"].get("value_gap", {}).get("max", 0)
                                       for rp in phases.values())
            row["decision_us_p50"] = round(float(np.median([rp[src]["decision_us"]["p50"] for rp in phases.values()])), 1)
            row["decision_us_p99"] = round(float(max(rp[src]["decision_us"]["p99"] for rp in phases.values())), 1)
            fl = [rp["files"][src] for rp in phases.values()]
            row["file_mb_per_phase"] = [round(min(x["bytes"] for x in fl) / 1e6, 2), round(max(x["bytes"] for x in fl) / 1e6, 2)]
            row["ram_mb_per_phase_max"] = max(x["ram_mb"] for x in fl)
            row["load_s_max"] = max(x["load_s"] + x["prepare_s"] for x in fl)
        out["sources"][src] = row
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / f"sim_merged_{a.name}.json").write_text(json.dumps(out, indent=1, default=float), "utf-8")
    print(json.dumps(out, indent=1, default=float))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--phases", default="0-5")
    r.add_argument("--variants", default="ea3l,ea4l,ea5l,ea3f,ea4f,ea5f")
    r.add_argument("--quick", action="store_true")
    r.add_argument("--lam", type=float, default=0.02)
    r.add_argument("--seed", type=int, default=57)
    r.add_argument("--tag", default="")
    r.add_argument("--out", type=Path, default=OUT)
    m = sub.add_parser("merge")
    m.add_argument("files", nargs="+")
    m.add_argument("--name", default="all")
    m.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    return run(a) if a.cmd == "run" else merge(a)


if __name__ == "__main__":
    raise SystemExit(main())
