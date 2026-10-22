"""Map v2 stage M1: the validation of the hero envelope (ssbot.map2.envelope) against the hero model's rollouts.

    python -m ssbot.tools.m1_envelope starts OUT.npz REC [REC ...]      # recorded start states (the M0 recordings)
    python -m ssbot.tools.m1_envelope check STARTS.npz OUT.json [--T 20] [--band-n 0] [--rolls 1000] [--floor]
    python -m ssbot.tools.m1_envelope witness STARTS.npz OUT.json [--T 20] [--targets 40]

check: per start state the cluster forward pass and n random key sequences rolled by the reference model (kin_jit +
the Clawline block + its residual drift): every rollout's centre must lie inside the envelope at every frame (an
escape is a bug: its distance is reported); the coverage of the envelope by the rollouts (cells of 0.05 u hit by a
rollout / cells of the envelope) and the extents; the cluster counts and the time per pass. witness: random points
of the exact envelope (inside and at the interval ends) -> the keys from the cluster chain and the tracker ->
re-simulated: the miss at the target frame.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from ssbot.knowledge import kinematics as km
from ssbot.map2 import envelope as env
from ssbot.map2 import env_jit as ej

CELL = 0.05


# ---- recorded start states --------------------------------------------------------------------------------------

def sample_starts(recs, n_per_trial: int = 3, seed: int = 0, max_n: int = 400) -> dict:
    """Model states (estimate_state, HERO2 params) at random frames of the M0 trials (hero only: no Clapper in the
    probes' hero-model experiments), before any Clawline press of the trial (the model has no Clawline)."""
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools import m0_calib as mc
    params = env.load_params()
    rng = np.random.default_rng(seed)
    S_all, lab = [], []
    for rec in recs:
        rec = Path(rec)
        rr = RecordingReader(rec)
        trials = [json.loads(l) for l in (rec / "m0_trials.jsonl").read_text(encoding="utf-8").splitlines()
                  if l.strip()]
        for t in trials:
            res = t.get("res") or {}
            f0, f1 = res.get("f0"), res.get("f1")
            if f0 is None or f1 is None or f1 - f0 < 5:
                continue
            try:
                states = list(rr.states(f0 - 40, f1 + 1, keys=mc.KIN_KEYS))
                tr = km.Trace.from_states(states, params, mask_source="act")
            except Exception:
                continue
            fr = np.asarray(tr.f)
            masks = np.asarray(tr.mask)
            claw = np.flatnonzero((masks & mc.M_CLAW) != 0)
            lo = int(np.searchsorted(fr, f0 - 10))
            hi = int(claw[0]) - 1 if len(claw) else len(fr) - 1
            if hi - lo < 2:
                continue
            idx = rng.choice(np.arange(lo, hi), size=min(n_per_trial, hi - lo), replace=False)
            S = km.estimate_state(tr, idx, params)
            for j, i in enumerate(idx):
                s = S[:, j]
                if s[km.MODE] not in (km.M_NORMAL, km.M_GLIDE, km.M_DASH, km.M_SPRINT, km.M_HARD_LAND):
                    continue
                S_all.append(s)
                lab.append(f"{t['exp']}/{res.get('v') or t.get('v')}/f{int(fr[i])}/m{int(s[km.MODE])}"
                           f"/g{int(s[km.GROUND])}")
    S_all = np.array(S_all)
    if len(S_all) > max_n:
        keep = np.sort(rng.choice(len(S_all), size=max_n, replace=False))
        S_all = S_all[keep]
        lab = [lab[i] for i in keep]
    return {"S": S_all, "labels": np.array(lab)}


# ---- random key sequences ---------------------------------------------------------------------------------------

def random_masks(rng, n: int, T: int, claw: bool = True, start_prev: int = 0) -> np.ndarray:
    """Key sequences with held keys of random lengths: left / none / right switches, the jump toggled (presses and
    holds), dash presses and holds, attack taps (also with down / up), Clawline taps (ej.B_CLAW, P + 8 variant 1 in
    6), a mix of busy and calm policies."""
    out = np.zeros((n, T), dtype=np.int64)
    for i in range(n):
        busy = rng.random()
        p_h = 0.05 + 0.25 * busy
        p_j = 0.03 + 0.2 * busy
        p_d = 0.01 + 0.08 * busy
        p_a = 0.02 + 0.1 * busy
        p_c = (0.005 + 0.04 * busy) if claw else 0.0
        h = int(rng.choice([0, km.B_LEFT, km.B_RIGHT]))
        j = start_prev & km.B_JUMP
        dsh = start_prev & km.B_DASH
        for t in range(T):
            if rng.random() < p_h:
                h = int(rng.choice([0, km.B_LEFT, km.B_RIGHT]))
            if rng.random() < p_j:
                j ^= km.B_JUMP
            if dsh:
                if rng.random() < 0.25:
                    dsh = 0
            elif rng.random() < p_d:
                dsh = km.B_DASH
            m = h | j | dsh
            if rng.random() < p_a:
                m |= km.B_ATTACK | int(rng.choice([0, 0, km.B_DOWN, km.B_UP]))
            if rng.random() < p_c:
                m |= ej.B_CLAW | ((1 << 31) if rng.random() < 1 / 6 else 0)
            out[i, t] = m
    return out


def random_masks_ev(rng, n: int, T: int, max_ev: int, claw: bool = True, start_prev: int = 0) -> np.ndarray:
    """Key sequences with at most max_ev changes of the jump / dash keys or taps (attack, Clawline) - each is at
    most one of the engine's events (a choice other than going on) - and free left / right switches."""
    out = np.zeros((n, T), dtype=np.int64)
    for i in range(n):
        k = int(rng.integers(0, max_ev + 1))
        when = set(rng.choice(T, size=min(k, T), replace=False).tolist())
        h = int(rng.choice([0, km.B_LEFT, km.B_RIGHT]))
        j = start_prev & km.B_JUMP
        dsh = start_prev & km.B_DASH
        for t in range(T):
            if rng.random() < 0.2:
                h = int(rng.choice([0, km.B_LEFT, km.B_RIGHT]))
            tap = 0
            if t in when:
                kinds = ["j", "d", "a"] + (["c"] if claw else [])
                kd = kinds[int(rng.integers(len(kinds)))]
                if kd == "j":
                    j ^= km.B_JUMP
                elif kd == "d":
                    dsh ^= km.B_DASH
                    if dsh:
                        h = int(rng.choice([km.B_LEFT, km.B_RIGHT]))
                elif kd == "a":
                    tap = km.B_ATTACK
                else:
                    tap = ej.B_CLAW
            out[i, t] = h | j | dsh | tap
    return out


# ---- containment -------------------------------------------------------------------------------------------------

def frame_index(fw: env.Fwd):
    """Per frame the clusters sorted by their bottom and the largest band height (for the point lookups)."""
    idx = []
    for t in range(fw.T + 1):
        g0, g1 = int(fw.cl_off[t]), int(fw.cl_off[t + 1])
        o = np.argsort(fw.cl_ylo[g0:g1], kind="stable") + g0
        span = float(np.max(fw.cl_y[g0:g1] - fw.cl_ylo[g0:g1])) if g1 > g0 else 0.0
        idx.append((o, fw.cl_ylo[o], span))
    return idx


def point_dist(fw: env.Fwd, fidx, t: int, x: float, y: float, tol: float = 1e-6) -> float:
    o, ylo, span = fidx[t]
    a = int(np.searchsorted(ylo, y - span - tol))
    b = int(np.searchsorted(ylo, y + tol, side="right"))
    for g in o[a:b]:
        if fw.cl_y[g] + tol < y:
            continue
        iv = fw.intervals(int(g))
        if np.any((iv[:, 0] - tol <= x) & (x <= iv[:, 1] + tol)):
            return 0.0
    return fw.nearest(t, x, y)[0]


def raster_cells(rows: np.ndarray, cell: float = CELL) -> set:
    """Cells (i, j) of side `cell` touched by rows (y0, y1, x0, x1)."""
    cells = set()
    for y0, y1, x0, x1 in rows:
        for jy in range(int(np.floor(y0 / cell)), int(np.floor(y1 / cell)) + 1):
            for ix in range(int(np.floor(x0 / cell)), int(np.floor(x1 / cell)) + 1):
                cells.add((ix, jy))
    return cells


def check_start(E: env.Engine, S: np.ndarray, T: int, n_roll: int, rng, terrain=None, band_n: int = 0,
                band_t: int = -1, claw: bool = True, cover_frames=(5, 10, 15, 20, 30, 40), opts: int = 0) -> dict:
    st = E.start_state(S)
    fw = E.forward(st, T, terrain=terrain, band_n=band_n, band_t=band_t, claw=claw, tf8=claw, opts=opts)
    max_ev = (opts >> 8) & 15
    if max_ev:
        masks = random_masks_ev(rng, n_roll, T, max_ev, claw=claw, start_prev=int(S[km.PREV]))
    else:
        masks = random_masks(rng, n_roll, T, claw=claw, start_prev=int(S[km.PREV]))
    xy, md = E.rollouts(np.repeat(S[None], n_roll, axis=0), np.repeat(st.cu[None], n_roll, axis=0), masks,
                        terrain=terrain)
    fidx = frame_index(fw)
    esc = []
    for i in range(n_roll):
        for t in range(1, T + 1):
            d = point_dist(fw, fidx, t, xy[i, t, 0], xy[i, t, 1])
            if d > 0:
                esc.append({"roll": i, "t": t, "dist": d, "xy": xy[i, t].tolist(),
                            "modes": md[i, :t + 1].tolist(), "masks": masks[i, :t].tolist()})
                break
    cover = {}
    for t in cover_frames:
        if t > T:
            continue
        rows = fw.region(t)
        if len(rows) > 20000:
            rows = rows[np.random.default_rng(0).choice(len(rows), 20000, replace=False)]
        ce = raster_cells(rows)
        cr = {(int(np.floor(x / CELL)), int(np.floor(y / CELL))) for x, y in xy[:, t]}
        cover[t] = {"env_cells": len(ce), "roll_cells": len(cr), "roll_in_env": len(cr & ce),
                    "env_x": [float(rows[:, 2].min()), float(rows[:, 3].max())] if len(rows) else None,
                    "env_y": [float(rows[:, 0].min()), float(rows[:, 1].max())] if len(rows) else None,
                    "roll_x": [float(xy[:, t, 0].min()), float(xy[:, t, 0].max())],
                    "roll_y": [float(xy[:, t, 1].min()), float(xy[:, t, 1].max())]}
    return {"escapes": esc, "n_esc": len(esc), "counts": [fw.count(t) for t in range(T + 1)],
            "seconds": fw.seconds, "exact_until": fw.exact_until(), "diverged": int(fw.stats[:, 3].sum()),
            "splits": int(fw.stats[:, 7].sum()), "cover": cover}


# ---- witness ------------------------------------------------------------------------------------------------------

def witness_start(E: env.Engine, S: np.ndarray, T: int, n_targets: int, rng, terrain=None, claw: bool = True,
                  look: int = 3, opts: int = 0) -> list:
    st = E.start_state(S)
    fw = E.forward(st, T, terrain=terrain, claw=claw, tf8=claw, opts=opts)
    out = []
    for _ in range(n_targets):
        t = int(rng.integers(max(1, T // 3), T + 1))
        g0, g1 = int(fw.cl_off[t]), int(fw.cl_off[t + 1])
        if g1 <= g0:
            continue
        g = int(rng.integers(g0, g1))
        iv = fw.intervals(g)
        a, b = iv[int(rng.integers(len(iv)))]
        kind = int(rng.integers(3))
        x = a if kind == 0 else (b if kind == 1 else float(rng.uniform(a, b)))
        t0 = time.perf_counter()
        w = fw.witness(t, x, float(fw.cl_y[g]), look=look)
        sec = time.perf_counter() - t0
        if w is None:
            out.append({"t": t, "g": g, "x": x, "kind": kind, "ok": False})
            continue
        out.append({"t": t, "g": g, "x": x, "kind": ["lo", "hi", "in"][kind], "ok": True, "miss_x": w["miss_x"],
                    "miss_y": w["miss_y"], "mode": int(fw.cl_mode[g]), "seconds": sec,
                    "claw": bool(np.any((w["vmask"] & ej.CB_CLAW) != 0)),
                    "jh": bool(np.any((w["vmask"] & ej.CB_JH) != 0)),
                    "events": int(np.sum((w["vmask"] & (ej.CB_D | ej.CB_CLAW | ej.CB_A)) != 0))})
    return out


def _q(v, ps=(50, 90, 99, 100)):
    v = np.asarray(v, dtype=float)
    return [round(float(np.percentile(v, p)), 4) for p in ps] if len(v) else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["starts", "check", "witness"])
    ap.add_argument("a")
    ap.add_argument("b", nargs="*")
    ap.add_argument("--T", type=int, default=20)
    ap.add_argument("--band-n", type=int, default=0)
    ap.add_argument("--band-t", type=int, default=-1)
    ap.add_argument("--rolls", type=int, default=1000)
    ap.add_argument("--targets", type=int, default=30)
    ap.add_argument("--n", type=int, default=0, help="first n start states only")
    ap.add_argument("--floor", action="store_true", help="the Forum floor (no walls) instead of free space")
    ap.add_argument("--no-claw", action="store_true")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--look", type=int, default=3)
    ap.add_argument("--opts", type=int, default=0, help="env_jit OPT_* bits (64: attacks in normal control)")
    ap.add_argument("--max-ev", type=int, default=0, help="the event limit (the rollouts then change keys <= it)")
    ap.add_argument("--start", type=int, default=0, help="first start index")
    args = ap.parse_args(argv)
    if args.cmd == "starts":
        d = sample_starts(args.b)
        np.savez_compressed(args.a, **d)
        print(len(d["S"]), "start states")
        return 0
    d = np.load(args.a)
    S, lab = d["S"], d["labels"]
    if args.n or args.start:
        S, lab = S[args.start:args.start + (args.n or len(S))], lab[args.start:args.start + (args.n or len(S))]
    E = env.Engine()
    terr = env.floor_terrain() if args.floor else None
    args.opts |= min(args.max_ev, 15) << 8
    rng = np.random.default_rng(args.seed)
    claw = not args.no_claw
    out = {"T": args.T, "band_n": args.band_n, "band_t": args.band_t, "floor": args.floor, "claw": claw, "per": []}
    # warm the compiled code
    E.forward(E.start_state(S[0]), 2, terrain=terr)
    if args.cmd == "check":
        for i, s in enumerate(S):
            r = check_start(E, s, args.T, args.rolls, rng, terrain=terr, band_n=args.band_n, band_t=args.band_t,
                            claw=claw, opts=args.opts)
            r["label"] = str(lab[i])
            out["per"].append(r)
            print(f"{i:3d} {lab[i]:34s} esc {r['n_esc']:3d} clusters T {r['counts'][-1]:6d} max "
                  f"{max(r['counts']):6d} {r['seconds'] * 1e3:8.1f} ms exact<= {r['exact_until']}", flush=True)
        n_esc = sum(r["n_esc"] for r in out["per"])
        secs = [r["seconds"] for r in out["per"]]
        out["summary"] = {"starts": len(S), "rollouts": len(S) * args.rolls, "escapes": n_esc,
                          "escape_dist": _q([e["dist"] for r in out["per"] for e in r["escapes"]]),
                          "seconds_p50_p90_p99_max": _q(secs),
                          "clusters_at_T": _q([r["counts"][-1] for r in out["per"]]),
                          "clusters_max": _q([max(r["counts"]) for r in out["per"]])}
        print(json.dumps(out["summary"]))
    else:
        allw = []
        for i, s in enumerate(S):
            w = witness_start(E, s, args.T, args.targets, rng, terrain=terr, claw=claw, look=args.look,
                              opts=args.opts)
            for o in w:
                o["start"] = i
            allw += w
            ok = [o for o in w if o["ok"]]
            print(f"{i:3d} {lab[i]:34s} targets {len(w)} found {len(ok)} miss_x p50/p90/max "
                  f"{_q([abs(o['miss_x']) for o in ok], (50, 90, 100))} miss_y max "
                  f"{_q([abs(o['miss_y']) for o in ok], (100,))}", flush=True)
        ok = [o for o in allw if o["ok"]]
        out["per"] = allw
        out["summary"] = {"targets": len(allw), "found": len(ok),
                          "miss_x": _q([abs(o["miss_x"]) for o in ok]),
                          "miss_y": _q([abs(o["miss_y"]) for o in ok]),
                          "within_0.1": int(sum(abs(o["miss_x"]) <= 0.1 and abs(o["miss_y"]) <= 0.1 for o in ok)),
                          "within_0.0825": int(sum(abs(o["miss_x"]) <= 0.0825 + 1e-6 and abs(o["miss_y"]) <= 1e-6
                                                   for o in ok)),
                          "by_kind": {k: _q([abs(o["miss_x"]) for o in ok if o["kind"] == k]) for k in ("lo", "hi", "in")},
                          "seconds": _q([o["seconds"] for o in ok])}
        print(json.dumps(out["summary"]))
    Path(args.b[0]).write_text(json.dumps(out, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
