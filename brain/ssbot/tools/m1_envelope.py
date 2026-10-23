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


def random_danger(rng, S: np.ndarray, T: int, hh: float, n_boxes: int = 4) -> list:
    """Per frame boxes (her centre's space) around her start: n_boxes rectangles 0.5 .. 3 u wide, 0.5 .. 4 u high,
    centres within 6 u in x and -4 .. +3 u in y, each drifting at up to 6 u/s, live from frame 3 on."""
    x0, y0 = float(S[km.PX]), float(S[km.PY] + hh)
    out = [np.zeros((0, 4)) for _ in range(T + 1)]
    for _ in range(n_boxes):
        cx, cy = x0 + rng.uniform(-6, 6), y0 + rng.uniform(-4, 3)
        w, h = rng.uniform(0.5, 3.0), rng.uniform(0.5, 4.0)
        vx, vy = rng.uniform(-6, 6) / 60, rng.uniform(-3, 3) / 60
        for t in range(3, T + 1):
            bx, by = cx + vx * t, cy + vy * t
            out[t] = np.vstack([out[t], [[bx - w / 2, by - h / 2, bx + w / 2, by + h / 2]]])
    return out


def in_danger(boxes: np.ndarray, x: float, y: float) -> bool:
    return bool(len(boxes) and np.any((boxes[:, 0] <= x) & (x <= boxes[:, 2]) & (boxes[:, 1] <= y) & (y <= boxes[:, 3])))


def check_start(E: env.Engine, S: np.ndarray, T: int, n_roll: int, rng, terrain=None, band_n: int = 0,
                band_t: int = -1, claw: bool = True, cover_frames=(5, 10, 15, 20, 30, 40), opts: int = 0,
                danger: bool = False) -> dict:
    st = E.start_state(S)
    dz = random_danger(rng, S, T, E.hh) if danger else None
    fw = E.forward(st, T, terrain=terrain, band_n=band_n, band_t=band_t, claw=claw, tf8=claw, opts=opts, danger=dz)
    max_ev = (opts >> 8) & 15
    if max_ev:
        masks = random_masks_ev(rng, n_roll, T, max_ev, claw=claw, start_prev=int(S[km.PREV]))
    else:
        masks = random_masks(rng, n_roll, T, claw=claw, start_prev=int(S[km.PREV]))
    xy, md = E.rollouts(np.repeat(S[None], n_roll, axis=0), np.repeat(st.cu[None], n_roll, axis=0), masks,
                        terrain=terrain)
    fidx = frame_index(fw)
    esc = []
    hit = 0
    for i in range(n_roll):
        for t in range(1, T + 1):
            if dz is not None and in_danger(dz[t], xy[i, t, 0], xy[i, t, 1]):
                hit += 1
                break                   # touched the danger: the later frames are not hers to keep
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
    # the cut envelope must hold no point inside a box (a sample of the rows at the frames' heights)
    leak = 0
    if dz is not None:
        for t in range(1, T + 1):
            g, x0, x1, y0, y1 = fw.frame_rows(t)
            for bx0, by0, bx1, by1 in dz[t]:
                # a row strictly overlapping a box at a height inside it (exact clusters: y0 = y1)
                leak += int(np.sum((y0 == y1) & (by0 <= y0) & (y0 <= by1) & (x0 < bx1 - 1e-9) & (x1 > bx0 + 1e-9)))
    return {"escapes": esc, "n_esc": len(esc), "danger_hit": hit, "danger_leak": leak,
            "dead": int(fw.stats[:, 2].sum()), "counts": [fw.count(t) for t in range(T + 1)],
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


def build_tables_cmd(args) -> int:
    """tables OUT.npz: the canonical starts' tables (env.table_keys) per phase class, args.T frames, the event limit
    args.max_ev (0: none - only for short T), written with save_tables; prints per table the counts and time."""
    E = env.Engine()
    alphas = [int(a) for a in args.alphas.split(",")]
    keys = env.table_keys(full=args.full)
    tabs, stat = {}, {}
    t0 = time.perf_counter()
    for ac in alphas:
        for k in keys:
            S, terr = env.canonical(E.params, k[0], k[1], ac, k[2], k[3])
            tb = env.build_table(E, S, terr, args.T, band_n=0, max_events=args.max_ev)
            name = env.key_name(k, ac)
            tabs[name] = tb
            verts = [env.contour_vertices(tb["all"][t]) for t in range(0, args.T + 1, 5)]
            stat[name] = {"ms": round(tb["_seconds"] * 1e3, 1), "clusters_T": tb["_counts"][-1],
                          "rows_T": len(tb["all"][-1]), "vertices": verts}
            print(f"{name:22s} {tb['_seconds'] * 1e3:8.1f} ms clusters T {tb['_counts'][-1]:6d} rows T "
                  f"{len(tb['all'][-1]):5d} contour vertices / 5 f {verts}", flush=True)
    meta = {"T": args.T, "max_ev": args.max_ev, "alphas": alphas, "q": env.QROW, "keys": list(tabs),
            "params": str(env.PARAMS_PATH), "hero2": True, "built_s": round(time.perf_counter() - t0, 1)}
    env.save_tables(args.a, tabs, meta)
    Path(args.b[0]).write_text(json.dumps({"meta": meta, "stat": stat}))
    print("tables", len(tabs), "in %.1f s" % (time.perf_counter() - t0), "file %.1f MB" % (Path(args.a).stat().st_size / 1e6))
    return 0


def tabcheck_cmd(args) -> int:
    """tabcheck TABLES.npz OUT.json: the stored tables against fresh exact passes from their canonical starts:
    every exact cluster point (sampled) must be inside the table (the raster is conservative); the raster's extra
    area (cells of the table not touched by a cluster point) is the looseness of the 0.05 u rows."""
    E = env.Engine()
    tb = env.Tables(args.a)
    rng = np.random.default_rng(args.seed)
    miss = tot = 0
    for name in tb.meta["keys"]:
        kind_var, rest = name.split("@")
        ph = int(rest.split("/")[0].rstrip("d"))
        dashed = rest.split("/")[0].endswith("d")
        ac = int(rest.split("/a")[1])
        kind, var = kind_var[:2], kind_var[2:]
        if kind[0] == "G":
            kind, var = "G", kind_var[1:]
        S, terr = env.canonical(E.params, kind, ph, ac, var, dashed)
        fw = E.forward(E.start_state(S), tb.meta["T"], terrain=terr, max_events=tb.meta["max_ev"])
        xs, ys = float(S[km.PX]), float(S[km.PY] + E.hh)
        for t in rng.choice(np.arange(1, tb.meta["T"] + 1), size=5, replace=False):
            g, x0, x1, y0, y1 = fw.frame_rows(int(t))
            for k in rng.choice(len(g), size=min(40, len(g)), replace=False):
                x = float(rng.uniform(x0[k], x1[k]))
                tot += 1
                if not tb.contains(name, "all", int(t), x - xs, float(y0[k]) - ys):
                    miss += 1
    out = {"points": tot, "outside_table": miss}
    print(json.dumps(out))
    Path(args.b[0]).write_text(json.dumps(out))
    return 0


def timing_cmd(args) -> int:
    """timing STARTS.npz OUT.json: the forward pass's time and cluster count per (event limit, horizon) over the
    start states (the Forum floor), single thread, the pass only."""
    d = np.load(args.a)
    S = d["S"][args.start:args.start + (args.n or len(d["S"]))]
    S = np.pad(S, [(0, 0), (0, max(0, km.K - S.shape[1]))])     # states saved before M4a's rows (K 81 -> 83)
    E = env.Engine()
    terr = env.floor_terrain()
    E.forward(E.start_state(S[0]), 2, terrain=terr)
    out = {}
    for mev, T in ((1, 30), (1, 60), (2, 10), (2, 20), (2, 30), (3, 20), (0, 6), (0, 8), (0, 10), (0, 12)):
        secs, cnt, tot = [], [], []
        for s in S:
            fw = E.forward(E.start_state(s), T, terrain=terr, max_events=mev)
            secs.append(fw.seconds)
            cnt.append(fw.count(T))
            tot.append(int(fw.cl_off[-1]))
        key = f"ev{mev or 'all'} T{T}"
        out[key] = {"ms_p50_p90_p99_max": [round(v * 1e3, 1) for v in _q(secs)], "clusters_T": _q(cnt),
                    "clusters_total": _q(tot)}
        print(key, json.dumps(out[key]), flush=True)
    Path(args.b[0]).write_text(json.dumps(out))
    return 0


def _q(v, ps=(50, 90, 99, 100)):
    v = np.asarray(v, dtype=float)
    return [round(float(np.percentile(v, p)), 4) for p in ps] if len(v) else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["starts", "check", "witness", "tables", "tabcheck", "timing"])
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
    ap.add_argument("--danger", action="store_true", help="random moving boxes cut the envelope; a rollout ends at its first touch")
    ap.add_argument("--start", type=int, default=0, help="first start index")
    ap.add_argument("--full", action="store_true", help="tables: every canonical phase (else every 5th)")
    ap.add_argument("--alphas", default="0", help="tables: the phase classes, e.g. 0,1,2,3,4,5")
    args = ap.parse_args(argv)
    if args.cmd == "starts":
        d = sample_starts(args.b)
        np.savez_compressed(args.a, **d)
        print(len(d["S"]), "start states")
        return 0
    if args.cmd == "tables":
        return build_tables_cmd(args)
    if args.cmd == "tabcheck":
        return tabcheck_cmd(args)
    if args.cmd == "timing":
        return timing_cmd(args)
    d = np.load(args.a)
    S, lab = d["S"], d["labels"]
    S = np.pad(S, [(0, 0), (0, max(0, km.K - S.shape[1]))])     # states saved before M4a's rows (K 81 -> 83)
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
                            claw=claw, opts=args.opts, danger=args.danger)
            r["label"] = str(lab[i])
            out["per"].append(r)
            print(f"{i:3d} {lab[i]:34s} esc {r['n_esc']:3d} clusters T {r['counts'][-1]:6d} max "
                  f"{max(r['counts']):6d} {r['seconds'] * 1e3:8.1f} ms exact<= {r['exact_until']}", flush=True)
        n_esc = sum(r["n_esc"] for r in out["per"])
        out["danger"] = {"hit": sum(r["danger_hit"] for r in out["per"]), "leak": sum(r["danger_leak"] for r in out["per"]),
                         "dead": sum(r["dead"] for r in out["per"])}
        secs = [r["seconds"] for r in out["per"]]
        out["summary"] = {"starts": len(S), "rollouts": len(S) * args.rolls, "escapes": n_esc,
                          "escape_dist": _q([e["dist"] for r in out["per"] for e in r["escapes"]]),
                          "seconds_p50_p90_p99_max": _q(secs),
                          "clusters_at_T": _q([r["counts"][-1] for r in out["per"]]),
                          "clusters_max": _q([max(r["counts"]) for r in out["per"]])}
        out["summary"]["danger"] = out["danger"]
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
