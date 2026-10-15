"""Task 1v1 SG3: SG2's closed-loop simulation driven by the contour store (ssbot.combat.map_lookahead on
ssbot.combat.score_contours; forum.md 57). No planner, no game.

Per physics phase, the same starts x timing variants as SG2's sim (ssbot.tools.sg2_sim) three times with the same
execution-noise seed:
  dense    SG2's policy on the dense values (shadows: the banded and the contour source decide on every visited
           state; each differing decision is classified by what it costs on the dense values);
  banded   the same policy on the dense values cut to the contour bands (exact on the lattice);
  contour  the same policy on the contour store (bands, +-1 band after the simplification).
Damage episodes from feasible starts are replayed without execution noise (map / policy limit vs noise). The decision
latency of the contour source (one lookahead = all successor queries of one decision) is timed.

    ../scripts/uv.cmd run python -m ssbot.tools.sg3_sim [--phases 0-5] [--quick] [--suffix _s0.1] [--tag T]
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
from ssbot.tools.sg2_sim import Sim, readiness_table, sim_variants, starts, summarize
from ssbot.tools.special_map_build import setup

OUT = Path(r"C:\ssbot\data\m2_map\sg3")


class TimedSource:
    """Wraps a source: counts queries per decision and times decide() via the sim's calls."""

    def __init__(self, src):
        self.src = src
        self.p, self.ti, self.st = src.p, src.ti, src.st
        self.nq = 0

    def S(self, *a):
        self.nq += 1
        return self.src.S(*a)

    def SV(self, *a):
        self.nq += 1
        return self.src.SV(*a)

    def press(self, *a):
        self.nq += 1
        return self.src.press(*a)


def run_set(sim: Sim, vs, st, lam: float, p: int) -> list:
    eps = []
    for tl in vs:
        for (nm, k0, x0, ev0, d0) in st:
            ev = dict(ev0)
            if ev["kind"] != "ground":
                ev["q0"] = (p - ev["k"]) % 6
            eps.append(sim.run(tl, nm, k0, x0, ev, lam, d0))
    return eps


def noise_free(sim: Sim, eps: list, vs, st, lam: float, p: int) -> int:
    """Damage episodes from feasible starts replayed without execution noise: how many still take damage."""
    late, off = sim.late_p, sim.offset
    sim.late_p, sim.offset = 0.0, False
    still = 0
    for e in [e for e in eps if e.damage_f >= 0 and np.isfinite(e.readiness)]:
        tl = next(v for v in vs if v.name == e.variant)
        s0 = next(s_ for s_ in st if s_[0] == e.start and s_[1] == e.k0 and s_[2] == e.x0 and s_[4] == e.d0)
        ev = dict(s0[3])
        if ev["kind"] != "ground":
            ev["q0"] = (p - ev["k"]) % 6
        e2 = sim.run(tl, e.start, e.k0, e.x0, ev, lam, e.d0)
        e.noise_free_damage = e2.damage_f
        still += e2.damage_f >= 0
    sim.late_p, sim.offset = late, off
    return still


def gap_table(gaps: list, step: float, lam: float) -> dict:
    out = {"n": len(gaps)}
    kinds = {}
    for kd, g in gaps:
        kinds[kd] = kinds.get(kd, 0) + 1
    out["kinds"] = kinds
    g = np.array([g for kd, g in gaps if kd == "value" and g is not None], float)
    if len(g):
        out["value_gap"] = {"max": round(float(g.max()), 4), "p50": round(float(np.median(g)), 4),
                            "le_step": round(float((g <= step + 1e-6).mean()), 4),
                            "le_2step_plus_lam": round(float((g <= 2 * step + lam + 1e-6).mean()), 4)}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phases", default="0-5")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--lam", type=float, default=0.02)
    ap.add_argument("--seed", type=int, default=57)
    ap.add_argument("--suffix", default="", help="the tube contour files' suffix (score_contours_build --suffix)")
    ap.add_argument("--tag", default="")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    t0 = time.time()
    geo = setup()
    ti = ml.TubeIndex.from_geometry(geo)
    b = sm.MapBuilder(geo)
    vs = sim_variants(geo, a.quick)
    st = starts(a.quick)
    lo, hi = (int(v) for v in a.phases.split("-"))
    res = {"phases": {}, "lam": a.lam, "suffix": a.suffix, "quick": a.quick}
    allr = {"dense": [], "banded": [], "contour": []}
    for p in range(lo, hi + 1):
        pm = b.build(p, keep_full=True)
        cs = sc.ContourSet.load(sm.MAP_DIR / f"special_map_CL_SLAM_tubes_p{p}{a.suffix}.npz")
        step = cs.step
        prep_s = cs.prepare()                               # the query arrays of every layer (load time, not tick time)
        dsrc = ml.DenseSource(pm, ti)
        bsrc = ml.BandedSource(pm, ti, step)
        csrc = ml.ContourSource(cs, ti, p)
        rp = {"step": step, "prepare_s": round(prep_s, 1), "layers": len(cs.layers)}
        # dense with shadows
        sim = Sim(geo, pm, np.random.default_rng(a.seed + p), src=dsrc)
        sim.shadows = [{"name": nm, "src": s_, "n": 0, "diff": 0, "gaps": [], "ex": [], "max_ex": 25}
                       for nm, s_ in (("banded", bsrc), ("contour", csrc))]
        eps = run_set(sim, vs, st, a.lam, p)
        rp["dense"] = {"summary": summarize(eps)["all"], "noise_free_still_damage": noise_free(sim, eps, vs, st, a.lam, p)}
        rp["agreement"] = {sh["name"]: {"decisions": sh["n"], "differ": sh["diff"],
                                        "share_same": round(1 - sh["diff"] / max(sh["n"], 1), 5),
                                        "gaps": gap_table(sh["gaps"], step, a.lam), "examples": sh["ex"]}
                           for sh in sim.shadows}
        allr["dense"] += eps
        # banded and contour closed loops
        for nm, s_ in (("banded", bsrc), ("contour", csrc)):
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
            rp[nm] = {"summary": summarize(e2)["all"], "noise_free_still_damage": noise_free(sim, e2, vs, st, a.lam, p)}
            if nm == "contour":
                lt = np.array(lat) * 1e6
                rp[nm]["decision_us"] = {"p50": round(float(np.median(lt)), 1), "p99": round(float(np.quantile(lt, 0.99)), 1),
                                         "queries_p50": float(np.median(nq)), "queries_max": int(np.max(nq)),
                                         "decisions": len(lt)}
            allr[nm] += e2
        res["phases"][p] = rp
        print(json.dumps({"p": p, "agreement": {k: {kk: v[kk] for kk in ("share_same", "gaps")}
                                                for k, v in rp["agreement"].items()},
                          **{k: rp[k]["summary"] for k in ("dense", "banded", "contour")},
                          "decision_us": rp["contour"].get("decision_us")}, default=float), flush=True)
        del pm, sim, cs
    res["all"] = {k: summarize(v)["all"] for k, v in allr.items() if v}
    res["readiness_k0"] = {k: readiness_table([e for e in v if e.start in ("ground", "antic_entry") and e.k0 == 0])
                           for k, v in allr.items() if v}
    res["feasible_start_damage"] = {k: {"n": sum(1 for e in v if e.damage_f >= 0 and np.isfinite(e.readiness)),
                                        "of": sum(1 for e in v if np.isfinite(e.readiness)),
                                        "noise_free_still": sum(1 for e in v if e.noise_free_damage is not None
                                                                and e.noise_free_damage >= 0)}
                                    for k, v in allr.items() if v}
    res["seconds"] = round(time.time() - t0, 1)
    a.out.mkdir(parents=True, exist_ok=True)
    nm = f"sim{a.suffix}{'_' + a.tag if a.tag else ''}_p{lo}-{hi}{'_quick' if a.quick else ''}.json"
    (a.out / nm).write_text(json.dumps(res, indent=1, default=float), "utf-8")
    print(json.dumps({k: res[k] for k in ("all", "feasible_start_damage", "seconds")}, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
