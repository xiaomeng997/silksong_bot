"""Map v2 stage T1: the A1_n no-dash table library (ssbot.map2.tables) - build, exactness, containment, tightness,
the build-time checks, timings. Offline; nothing in the bot imports it.

    python -m ssbot.tools.t1_tables build OUT.json [--depth 0] [--max-nodes 3000000]
    python -m ssbot.tools.t1_tables exact OUT.json [--T 24] [--floor] [--maxev 0] [--n 400]
    python -m ssbot.tools.t1_tables contain OUT.json [--T 120] [--rolls 300] [--floor]
    python -m ssbot.tools.t1_tables witness OUT.json [--T 120] [--targets 20]
    python -m ssbot.tools.t1_tables checks OUT.json
    python -m ssbot.tools.t1_tables flat OUT.json [--T 120] [--maxev 1]
    python -m ssbot.tools.t1_tables header OUT.json        # the tracked knowledge header of the generated files
    python -m ssbot.tools.t1_tables entry OUT.json [--floor]   # entry from any state: transitional starts

exact: per start (the canonical starts and the 400 recorded start states of M1, C:/ssbot/data/m2_play/map2/m1/
starts.npz) the engine's exact pass with the air dash off (env_jit.OPT_NO_ADASH; Engine.forward) against the table
chain (tables.Lib.forward): per frame the reachable x interval sets by (height, end-condition bits) must be equal -
the heights bit-equal, the interval ends within TOL_X. contain: random key sequences without the air dash rolled by
the reference model (kin_jit + the Clawline block) must stay inside the chain: each frame's state is followed through
the graph (its merge class at its exact height among the node's children, x inside the accumulated offset interval)
- any horizon, no event limit. witness: random paths through the graph (random edges, a random x in the end
interval) -> the keys from the path (its candidate codes) and the horizontal tracker -> re-simulated: the miss.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import sys
import time
from pathlib import Path

import numpy as np
from numba import njit

from ssbot.knowledge import kinematics as km
from ssbot.knowledge.kin_jit import f32, fixed_step, update
from ssbot.map2 import env_jit as ej
from ssbot.map2 import envelope as env
from ssbot.map2 import tables as tb

DATA = Path("C:/ssbot/data/m2_play/map2/a1n")
STARTS = Path("C:/ssbot/data/m2_play/map2/m1/starts.npz")
TOL_X = 1e-9


def idle() -> None:
    try:
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x40)
    except Exception:
        pass


def _q(v, ps=(50, 90, 99, 100)):
    v = np.asarray(v, dtype=float)
    return [round(float(np.percentile(v, p)), 6) for p in ps] if len(v) else None


def load_starts(n: int = 0):
    d = np.load(STARTS)
    S, lab = d["S"], d["labels"]
    S = np.pad(S, [(0, 0), (0, max(0, km.K - S.shape[1]))])
    if n:
        S, lab = S[:n], lab[:n]
    return S, [str(x) for x in lab]


CANON = [("A1", 0, ""), ("A1", 5, ""), ("A1", 12, ""), ("A2", 0, "claw"), ("A2", 0, "pogo"), ("A2", 10, "claw"),
         ("A3", 0, "L"), ("A3", 0, "N"), ("A3", 0, "R"), ("A3", 20, "N"), ("A4", 0, ""), ("G", 0, ""), ("G", 0, "L"),
         ("G", 0, "R")]


def canon_starts(params):
    """The canonical starts (envelope.canonical) at the six physics-phase classes: (S, label, ground)."""
    out = []
    for kind, ph, var in CANON:
        for ac in range(6):
            S, terr = env.canonical(params, kind, ph, ac, var, False)
            out.append((S, f"{kind}{var}@{ph}/a{ac}", kind == "G"))
    return out


# ---- build ------------------------------------------------------------------------------------------------------

def build_cmd(args) -> int:
    idle()
    t0 = time.perf_counter()
    lib = _new_lib(args)
    log = (lambda m: print(m, flush=True))
    roots = []
    for kind, ph, var in (("A1", 0, ""), ("A2", 0, "claw"), ("A2", 0, "pogo"), ("A3", 0, "L"), ("A3", 0, "N"),
                          ("A3", 0, "R"), ("A4", 0, ""), ("G", 0, ""), ("G", 0, "L"), ("G", 0, "R")):
        S, terr = env.canonical(lib.params, kind, ph, 0, var, False)
        st, L, absy, dashed = lib.start_lanes(S, floor=(kind == "G"))
        roots.append(lib.node_of(L, st.cu, absy))
    log(f"roots {roots}")
    # breadth-first by frame depth: level d = the nodes first found d frames from a root (the full closure does not
    # converge - forum.md / HANDOFF T1: the float's event histories give a new exact vertical state each - so the
    # library is this depth-limited core plus the nodes the search's own passes meet)
    a, b, depth = 0, lib.n_nodes, 0
    levels = []
    while a < b and (args.depth <= 0 or depth < args.depth) and lib.n_nodes < args.max_nodes:
        lib.close(a, b)
        levels.append((depth, b - a, lib.n_nodes, lib.n_edges, round(time.perf_counter() - t0, 1)))
        log(f"depth {depth:3d}: expanded {b - a:7d}  nodes {lib.n_nodes:8d}  edges {lib.n_edges:9d}  "
            f"{time.perf_counter() - t0:7.1f} s")
        a, b, depth = b, lib.n_nodes, depth + 1
    closed = a >= b
    t_free = time.perf_counter() - t0
    # the warm-up: the search's passes (the event limits it uses: <= 1 event 60 f, <= 2 events 30 f; and <= 3 events
    # 20 f, exact 16 f) from the canonical starts (x 6 phase classes) and from the even-numbered recorded starts
    # (the odd ones stay cold for the timing), over the floor and - for the air starts - in free space
    S_all, lab = load_starts()
    n_inst0 = int(lib.CNT[tb.C_INST])
    warm = [(S, gnd) for (S, lb, gnd) in canon_starts(lib.params)]
    warm += [(S_all[i], bool(S_all[i][km.GROUND] > 0)) for i in range(0, len(S_all), 2)
             if S_all[i][km.TS] == 1.0 and S_all[i][km.WF_S] == 1.0]
    PASSES = tuple(tuple(int(v) for v in x.split(":")) for x in args.passes.split(","))
    for j, (S, gnd) in enumerate(warm):
        for mev, T in PASSES:
            lib.forward(S, T, floor=True, maxev=mev)
            if not gnd:
                lib.forward(S, T, floor=False, maxev=mev)
        if j % 50 == 0:
            log(f"  warm {j}/{len(warm)}: nodes {lib.n_nodes} edges {lib.n_edges} instances "
                f"{int(lib.CNT[tb.C_INST])} {time.perf_counter() - t0:.1f} s")
    n_warm = lib.n_nodes
    t_all = time.perf_counter() - t0
    lib.meta.update({"built": time.strftime("%Y-%m-%d %H:%M:%S"), "build_s": round(t_all, 1),
                     "build_core_s": round(t_free, 1), "depth_limit": args.depth, "closed": bool(closed),
                     "levels": levels, "floor_instances": int(lib.CNT[tb.C_INST]) - n_inst0,
                     "warm_nodes": n_warm, "warm_passes": [list(p) for p in PASSES],
                     "warm_starts": "canonical x 6 phases + recorded starts 0, 2, 4, ..."})
    out_path = Path(args.lib) if args.lib else tb.tables_path(lib.claw, lib.terrain)
    t1 = time.perf_counter()
    lib.save(out_path)
    size = out_path.stat().st_size
    rep = {"nodes": lib.n_nodes, "edges": lib.n_edges, "classes": int(lib.CNT[tb.C_CLS]),
           "instances": int(lib.CNT[tb.C_INST]), "closed": bool(closed), "levels": levels,
           "build_s": round(t_all, 1), "free_closure_s": round(t_free, 1), "save_s": round(time.perf_counter() - t1, 1),
           "file": str(out_path), "file_MB": round(size / 1e6, 2), "avdep": int(lib.CNT[tb.C_AVDEP]),
           "dyupd": int(lib.CNT[tb.C_DYUPD]), "slope_edges": int(lib.CNT[tb.C_SLOPE]),
           "merges": int(lib.CNT[tb.C_MERGE])}
    t2 = time.perf_counter()
    tb.Lib.load(out_path)
    rep["load_s"] = round(time.perf_counter() - t2, 2)
    log(json.dumps(rep))
    Path(args.out).write_text(json.dumps(rep, indent=1))
    return 0


# ---- exactness --------------------------------------------------------------------------------------------------

def frame_sets(fw, t: int, by_cond: bool = True) -> dict:
    """{(height, cond): [[x0, x1], ...]} - the union of the frame's clusters per exact height (and end condition)."""
    g, x0, x1, y0, y1 = fw.frame_rows(t)
    if not len(g):
        return {}
    cond = fw.cl_cond[g] if by_cond else np.zeros(len(g), dtype=np.int64)
    order = np.lexsort((x0, cond, y1))
    out = {}
    for i in order:
        k = (float(y1[i]), int(cond[i]))
        m = out.get(k)
        if m is None:
            out[k] = [[float(x0[i]), float(x1[i])]]
        elif x0[i] <= m[-1][1] + 1e-9:
            if x1[i] > m[-1][1]:
                m[-1][1] = float(x1[i])
        else:
            m.append([float(x0[i]), float(x1[i])])
    return out


def compare(fe, ft, T: int) -> dict:
    """The engine's pass fe against the chain ft: per frame the keys (height, cond) only one side has, the interval
    lists of different length, the largest interval-end difference."""
    only_e = only_t = nlen = 0
    worst = 0.0
    first_bad = None
    for t in range(T + 1):
        a, b = frame_sets(fe, t), frame_sets(ft, t)
        ka, kb = set(a), set(b)
        oe, ot = len(ka - kb), len(kb - ka)
        only_e += oe
        only_t += ot
        bad = oe + ot
        for k in ka & kb:
            A, B = a[k], b[k]
            if len(A) != len(B):
                nlen += 1
                bad += 1
                continue
            for (a0, a1), (b0, b1) in zip(A, B):
                d = max(abs(a0 - b0), abs(a1 - b1))
                if d > worst:
                    worst = d
                if d > TOL_X:
                    bad += 1
        if bad and first_bad is None:
            first_bad = t
    return {"only_engine": only_e, "only_tables": only_t, "len_diff": nlen, "worst_dx": worst, "first_bad": first_bad,
            "ok": only_e == 0 and only_t == 0 and nlen == 0 and worst <= TOL_X}


def exact_cmd(args) -> int:
    idle()
    lib = _new_lib(args) if args.lib == "none" else tb.Lib.load(args.lib or tb.tables_path(not args.no_claw,
                                                                                        args.terrain))
    E = lib.eng
    S_all, lab = load_starts(args.n)
    starts = [(S, lb, g) for (S, lb, g) in canon_starts(lib.params)] if args.canon else []
    starts += [(S_all[i], lab[i], bool(S_all[i][km.GROUND] > 0)) for i in range(len(S_all))]
    terr = lib.terr if args.floor else None
    opts = ej.OPT_NO_ADASH
    # warm both
    E.forward(E.start_state(starts[0][0]), 2, terrain=terr, opts=opts, claw=lib.claw, tf8=lib.claw)
    lib.forward(starts[0][0], 2, floor=args.floor)
    per = []
    rng = np.random.default_rng(args.seed)
    t0 = time.perf_counter()
    for i, (S, lb, gnd) in enumerate(starts):
        if gnd and not args.floor:
            continue
        if S[km.TS] != 1.0 or S[km.WF_S] != 1.0:
            per.append({"i": i, "label": lb, "skipped": "time scale"})
            continue
        T = args.T
        if args.reload and len(per) and len(per) % args.reload == 0 and args.lib != "none":
            lib = tb.Lib.load(args.lib or tb.tables_path(not args.no_claw, args.terrain))    # bound the lazy growth
        dz = None
        if args.danger:
            from ssbot.tools import m1_envelope as m1
            dz = m1.random_danger(rng, S, T, lib.hh)
        fe = E.forward(E.start_state(S), T, terrain=terr, opts=opts, max_events=args.maxev, claw=lib.claw,
                       tf8=lib.claw, danger=dz)
        ft = lib.forward(S, T, floor=args.floor, maxev=args.maxev, danger=dz)
        ft2 = lib.forward(S, T, floor=args.floor, maxev=args.maxev, danger=dz)  # warm (the lazily expanded nodes kept)
        r = compare(fe, ft, T)
        r.update({"i": i, "label": lb, "ground": gnd, "clusters_engine": fe.count(T), "clusters_tables": ft.count(T),
                  "total_engine": int(fe.cl_off[-1]), "ms_engine": fe.seconds * 1e3, "ms_tables_cold": ft.seconds * 1e3,
                  "ms_tables": ft2.seconds * 1e3, "lazy": ft.lib_stats})
        per.append(r)
        if not r["ok"] or i % 20 == 0:
            print(f"{i:3d} {lb:34s} ok {r['ok']} only e/t {r['only_engine']}/{r['only_tables']} len {r['len_diff']} "
                  f"dx {r['worst_dx']:.2e} clusters e/t {r['clusters_engine']}/{r['clusters_tables']} ms e "
                  f"{r['ms_engine']:.1f} t {r['ms_tables']:.1f} (cold {r['ms_tables_cold']:.1f}) lazy "
                  f"{ft.lib_stats['expanded']}", flush=True)
    ok = [r for r in per if "ok" in r]
    summ = {"T": args.T, "floor": args.floor, "maxev": args.maxev, "danger": args.danger, "claw": lib.claw,
            "terrain": lib.terrain, "starts": len(ok), "dead_engine": int(sum(r["clusters_engine"] == 0 for r in ok)),
            "skipped": len(per) - len(ok), "exact": sum(r["ok"] for r in ok),
            "worst_dx": max([r["worst_dx"] for r in ok] or [0.0]),
            "ms_engine": _q([r["ms_engine"] for r in ok]), "ms_tables": _q([r["ms_tables"] for r in ok]),
            "ms_tables_cold": _q([r["ms_tables_cold"] for r in ok]),
            "speedup_p50": round(float(np.median([r["ms_engine"] / max(r["ms_tables"], 1e-3) for r in ok])), 2)
            if ok else None,
            "clusters_engine": _q([r["clusters_engine"] for r in ok]),
            "clusters_tables": _q([r["clusters_tables"] for r in ok]),
            "lazy_expanded": _q([r["lazy"]["expanded"] for r in ok]),
            "wall_s": round(time.perf_counter() - t0, 1), "library_nodes_after": lib.n_nodes}
    print(json.dumps(summ), flush=True)
    Path(args.out).write_text(json.dumps({"summary": summ, "per": per}, default=float))
    return 0


def _starts_for(args, lib, with_canon: bool = True):
    S_all, lab = load_starts(args.n)
    out = [(S, lb, g) for (S, lb, g) in canon_starts(lib.params)] if (with_canon and args.canon) else []
    out += [(S_all[i], lab[i], bool(S_all[i][km.GROUND] > 0)) for i in range(len(S_all))]
    return [(S, lb, g) for (S, lb, g) in out if S[km.TS] == 1.0 and S[km.WF_S] == 1.0 and (args.floor or not g)]


def _new_lib(args):
    return tb.Lib(claw=not args.no_claw, terrain=args.terrain)


def _lib_args(lib):
    return (lib.P, lib.udt, lib.TTf, lib.TTg, lib.opts, lib.hh, *lib._lib(), lib.ICK, lib.ICT)


# ---- containment ------------------------------------------------------------------------------------------------

def contain_cmd(args) -> int:
    """Random key sequences without the air dash (m1_envelope.random_masks: left / none / right, jump presses and
    holds, dash presses and holds - dropped in the air -, attack taps, Clawline taps) rolled by the reference member
    and followed through the graph (tables.follow): every frame's centre must be in a lineage of the chain."""
    idle()
    from ssbot.tools import m1_envelope as m1
    lib = _new_lib(args) if args.lib == "none" else tb.Lib.load(args.lib or tb.tables_path(not args.no_claw,
                                                                                        args.terrain))
    rng = np.random.default_rng(args.seed)
    starts = _starts_for(args, lib)
    per, esc = [], []
    t0 = time.perf_counter()
    for i, (S, lb, gnd) in enumerate(starts):
        if args.reload and i and i % args.reload == 0 and args.lib != "none":
            lib = tb.Lib.load(args.lib or tb.tables_path(not args.no_claw, args.terrain))
        masks = m1.random_masks(rng, args.rolls, args.T, claw=lib.claw, start_prev=int(S[km.PREV]))
        st, L, absy, dashed = lib.start_lanes(S, floor=args.floor)
        out = np.zeros((args.rolls, 3))
        xy = np.zeros((args.rolls, args.T + 1, 2))
        while True:
            n0 = lib.node_of(L, st.cu, absy)
            t1 = time.perf_counter()
            r = tb.follow(st.L[1].copy(), st.cu.copy(), n0, masks, lib.TP if args.floor else lib.TP_free, 1e-6,
                          *_lib_args(lib), out, xy)
            if r == -2:
                lib._grow()
                continue
            break
        sec = time.perf_counter() - t1
        ne = int(np.sum(out[:, 0] >= 0))
        for k in np.flatnonzero(out[:, 0] >= 0)[:5]:
            t = int(out[k, 0])
            esc.append({"start": i, "label": lb, "roll": int(k), "t": t, "dist": float(out[k, 2]),
                        "masks": masks[k, :t].tolist(), "xy": xy[k, t].tolist()})
        per.append({"i": i, "label": lb, "escapes": ne, "lineages_max": int(out[:, 1].max()), "s": sec})
        if ne or i % 25 == 0:
            print(f"{i:3d} {lb:34s} escapes {ne:3d} lineages max {int(out[:, 1].max()):3d} {sec * 1e3:8.1f} ms "
                  f"nodes {lib.n_nodes}", flush=True)
    summ = {"T": args.T, "floor": args.floor, "starts": len(per), "rollouts": len(per) * args.rolls,
            "escapes": sum(p["escapes"] for p in per), "escape_dist": _q([e["dist"] for e in esc]),
            "lineages_max": _q([p["lineages_max"] for p in per]), "ms_per_start": _q([p["s"] * 1e3 for p in per]),
            "wall_s": round(time.perf_counter() - t0, 1), "library_nodes_after": lib.n_nodes}
    print(json.dumps(summ), flush=True)
    Path(args.out).write_text(json.dumps({"summary": summ, "per": per, "escapes": esc}, default=float))
    return 0


# ---- tightness: random paths through the graph and their keys ---------------------------------------------------

def walk(lib, S, T: int, rng, floor: bool, p_go: float = 0.85):
    """A random path of T frames through the graph from her state: per frame the going-on edge (the first one that
    spends no event) with probability p_go, else a random edge. Returns (the candidate codes, the per-frame lane
    displacements, the end interval [lo, hi], her end PY) or None (a table filled up: retry)."""
    st, L, absy, dashed = lib.start_lanes(S, floor=floor)
    n = lib.node_of(L, st.cu, absy)
    py, alpha = float(S[km.PY]), float(S[km.ALPHA])
    qy, sy = float(S[km.QY]), float(S[km.SY])
    lo = hi = float(S[km.PX])
    dt = float(np.float32(lib.udt))
    fdt = float(lib.P[km.P_FDT])
    vm, ds = [], []
    for t in range(1, T + 1):
        a_ = alpha + dt / fdt
        s = int(np.floor(a_ + 1e-9))
        a_st = alpha
        alpha = min(max(a_ - s, 0.0), 1.0)
        src = tb.route(n, py, qy, sy, s, a_st, lib.TP if floor else lib.TP_free, *_lib_args(lib))
        if src < 0:
            lib._grow()
            return None
        md = 2 if floor else 0
        e0, ne = int(lib.EOFF[src, s, md, 0]), int(lib.EOFF[src, s, md, 1])
        if ne == 0:
            return "dead"
        es = np.arange(e0, e0 + ne)
        go = es[lib.EF[es, tb.EF_NEV] == 0]
        e = int(go[0]) if (len(go) and rng.random() < p_go) else int(rng.choice(es))
        dl = lib.EF[e, tb.EF_DLO] + lib.EF[e, tb.EF_SLO] * a_st
        dh = lib.EF[e, tb.EF_DHI] + lib.EF[e, tb.EF_SHI] * a_st
        lo += dl
        hi += dh
        yabs = lib.EI[e, tb.EI_YABS] == 1
        py2 = float(lib.EF[e, tb.EF_DY]) if yabs else py + float(lib.EF[e, tb.EF_DY])
        qm, sm = lib.EF[e, tb.EF_QM], lib.EF[e, tb.EF_SM]
        q2 = qy if qm == 0 else (py if qm == 1 else (py2 if qm == 2 else (qy + a_st * (sy - qy) if qm == 4
                                                                         else py2 + lib.EF[e, tb.EF_QV])))
        s2 = sy if sm == 0 else (py2 if sm == 1 else ((lib.EF[e, tb.EF_SV] if yabs else py + lib.EF[e, tb.EF_SV])
                                                      if sm == 2 else py2 + lib.EF[e, tb.EF_SV]))
        py, qy, sy = py2, float(q2), float(s2)
        n = int(lib.EI[e, tb.EI_CH])
        vm.append(int(lib.EI[e, tb.EI_CAND]))
        ds.append((dl, dh))
    return np.array(vm, dtype=np.int64), np.array(ds), lo, hi, py, st


def witness_cmd(args) -> int:
    idle()
    lib = _new_lib(args) if args.lib == "none" else tb.Lib.load(args.lib or tb.tables_path(not args.no_claw,
                                                                                        args.terrain))
    rng = np.random.default_rng(args.seed)
    starts = _starts_for(args, lib)
    TT = lib.TTg if args.floor else lib.TTf
    res = []
    t0 = time.perf_counter()
    for i, (S, lb, gnd) in enumerate(starts):
        if args.reload and i and i % args.reload == 0 and args.lib != "none":
            lib = tb.Lib.load(args.lib or tb.tables_path(not args.no_claw, args.terrain))
        for _ in range(args.targets):
            w = None
            while w is None:
                w = walk(lib, S, args.T, rng, args.floor)
            if isinstance(w, str):
                res.append({"start": i, "ok": False, "why": w})
                continue
            vm, ds, lo, hi, py, st = w
            kind = int(rng.integers(3))
            x = lo if kind == 0 else (hi if kind == 1 else float(rng.uniform(lo, hi)))
            clo = np.concatenate([np.cumsum(ds[::-1, 0])[::-1], [0.0]])
            chi = np.concatenate([np.cumsum(ds[::-1, 1])[::-1], [0.0]])
            tlo, thi = x - chi, x - clo
            S0 = st.L[1].copy()
            masks = np.zeros(args.T, dtype=np.int64)
            oxy = np.zeros((args.T + 1, 2))
            t1 = time.perf_counter()
            ej.track(S0, st.cu.copy(), vm, tlo, thi, lib.udt, lib.P, TT, 3, masks, oxy)
            if abs(oxy[args.T, 0] - x) > 1e-3:
                m2 = np.zeros(args.T, dtype=np.int64)
                o2 = np.zeros((args.T + 1, 2))
                ej.track_beam(S0, st.cu.copy(), vm, tlo, thi, lib.udt, lib.P, TT, 24, m2, o2)
                if abs(o2[args.T, 0] - x) < abs(oxy[args.T, 0] - x):
                    masks, oxy = m2, o2
            sec = time.perf_counter() - t1
            res.append({"start": i, "label": lb, "ok": True, "kind": ["lo", "hi", "in"][kind],
                        "miss_x": float(oxy[args.T, 0] - x), "miss_y": float(oxy[args.T, 1] - (py + lib.hh)),
                        "events": int(np.sum((vm & (ej.CB_CLAW | ej.CB_A | ej.CB_J)) != 0)),
                        "claw": bool(np.any((vm & ej.CB_CLAW) != 0)), "width": hi - lo, "s": sec})
        if i % 25 == 0:
            ok = [r for r in res if r.get("ok")]
            print(f"{i:3d} {lb:34s} targets {len(res)} within 0.1 {sum(abs(r['miss_x']) <= 0.1 for r in ok)} "
                  f"miss_y max {max([abs(r['miss_y']) for r in ok] or [0]):.2e}", flush=True)
    ok = [r for r in res if r.get("ok")]
    summ = {"T": args.T, "floor": args.floor, "targets": len(res), "found": len(ok),
            "miss_x": _q([abs(r["miss_x"]) for r in ok]), "miss_y": _q([abs(r["miss_y"]) for r in ok]),
            "within_0.1": int(sum(abs(r["miss_x"]) <= 0.1 and abs(r["miss_y"]) <= 1e-9 for r in ok)),
            "by_kind": {k: _q([abs(r["miss_x"]) for r in ok if r["kind"] == k]) for k in ("lo", "hi", "in")},
            "with_claw": _q([abs(r["miss_x"]) for r in ok if r["claw"]]),
            "events": _q([r["events"] for r in ok]), "ms": _q([r["s"] * 1e3 for r in ok]),
            "wall_s": round(time.perf_counter() - t0, 1)}
    print(json.dumps(summ), flush=True)
    Path(args.out).write_text(json.dumps({"summary": summ, "per": res}, default=float))
    return 0


# ---- the settle-at-build-time checks ------------------------------------------------------------------------------

@njit(cache=True, error_model="numpy")
def _float_x(vx0, keys, P, out):
    """The umbrella float's horizontal for one key sequence per row (keys [n, k]: -1 left, 0 none, +1 right, one per
    physics step) from vx0: x after each step (UmbrellaMotionX.DoAccelerate, kin_jit.umbrella_x, Float Idle's
    accel / decel / vmax)."""
    from_ = 0
    n, k = keys.shape
    fdt = P[km.P_FDT]
    for i in range(n):
        v = vx0
        x = 0.0
        for j in range(k):
            m = keys[i, j]
            if m > 0:
                if v < P[km.P_GL_VMAX]:
                    v += P[km.P_GL_ACC]
            elif m < 0:
                if v > -P[km.P_GL_VMAX]:
                    v -= P[km.P_GL_ACC]
            elif v > 0.0:
                v -= P[km.P_GL_DEC]
                if v < 0.0:
                    v = 0.0
            elif v < 0.0:
                v += P[km.P_GL_DEC]
                if v > 0.0:
                    v = 0.0
            v = min(max(v, -P[km.P_GL_VMAX]), P[km.P_GL_VMAX])
            x += v * fdt
            out[i, j] = x
    return from_


def checks_cmd(args) -> int:
    """The spec's 'Points to settle' measured on the library and the hero model (forum_map_v2.md, THE A1_n RECURSIVE
    TABLES): the steady-state rule, the jump-held offsets, the physics phase, the float's monotonicity incl. a
    reversal (the Umbrella Turn) and its gaps, the entry-vx bit-equality; the A1_n recursion itself."""
    idle()
    lib = tb.Lib.load(args.lib or tb.tables_path(not args.no_claw, args.terrain))
    P = lib.P
    rep = {}
    kd = lib.kinds()
    rep["kinds"] = {tb.KIND_NAMES[k]: int(np.sum(kd == k)) for k in range(len(tb.KIND_NAMES))}
    rep["nodes"], rep["edges"] = lib.n_nodes, lib.n_edges
    # (1) the A1_n recursion: A1_0 -> continue -> A1_1 ... (s = 1), A1_n -> itself (s = 0), the x offset interval
    S, terr = env.canonical(lib.params, "A1", 0, 0, "", False)
    st, L, absy, dashed = lib.start_lanes(S)
    n = lib.node_of(L, st.cu, absy)
    lat = lib.lattice()
    chain = []
    for step in range(40):
        row = {"n": step, "node": n, "kind": tb.KIND_NAMES[kd[n]] if n < len(kd) else "?",
               "vy": float(lib.NVY[n, tb.V_VY])}
        for s in (0, 1):
            es = list(lib.edges(n, 0.0, s))
            go = [e for e in es if lib.EF[e, tb.EF_NEV] == 0]
            e = go[0]
            row[f"s{s}"] = {"child": int(lib.EI[e, tb.EI_CH]), "x_off": [float(lib.EF[e, tb.EF_DLO]),
                                                                        float(lib.EF[e, tb.EF_DHI])],
                            "dy": float(lib.EF[e, tb.EF_DY]), "actions": len(es) - 1,
                            "action_cands": sorted({int(lib.EI[x, tb.EI_CAND]) for x in es if x != e})}
        chain.append(row)
        nxt = row["s1"]["child"]
        if nxt == n:
            break
        n = nxt
    kd = lib.kinds()
    for r in chain:
        r["kind"] = tb.KIND_NAMES[kd[r["node"]]]
    rep["a1_chain"] = chain
    rep["a1_lattice_vy"] = lat[:30].tolist()
    rep["run_step"] = float(P[km.P_RUN] * P[km.P_FDT])
    # (2) the steady-state rule: what each kind waits out
    rep["steady_rule"] = ("A1 / A1~ / A4: normal control in the air with the attack and its cooldown, i-frames, the "
                          "air sprint's extra velocity, the Clawline block / lock (control + 13) / residual drift, the "
                          "downspike recovery, the dash cooldown, the jump buffer, the umbrella's re-open lock (0.1 s) "
                          "and the ledge buffer spent, gravity 1, no hang to come (else 'hang'); A1 on the lattice, A1~ "
                          "off it; A3 Float Idle; A2 a rise (jump / bounce); G standing / walking; R the ground sprint "
                          "at 17.5 u/s past Sprint Grace; the air dash used is NOT a key (a segment property)")
    # (3) the jump-held offsets: the hang chains and the vy offsets they leave
    X = lib.NL[:lib.n_nodes, 1]
    hang = kd == tb.K_HANG
    off = kd == tb.K_A1OFF
    rep["hang_nodes"] = int(hang.sum())
    rep["offset_chain_nodes"] = int(off.sum())
    rep["offset_distinct_vy"] = int(len(np.unique(X[off, km.VY])))
    rep["lattice_distinct_vy_in_lib"] = int(len(np.unique(X[kd == tb.K_A1, km.VY])))
    # (4) the physics phase
    dt = float(np.float32(lib.udt))
    fdt = float(P[km.P_FDT])
    rep["phase"] = {"dt_over_fdt": dt / fdt, "minus_5_6": dt / fdt - 5.0 / 6.0,
                    "frames_drift_1e-6": 1e-6 / (dt / fdt - 5.0 / 6.0),
                    "phase_dependent_nodes": int(np.sum(lib.NINT[:lib.n_nodes, tb.I_ADEP] != 0)),
                    "slope_edges": int(lib.CNT[tb.C_SLOPE]),
                    "pattern_from_0": [s for s, a in lib.steps(0.0, 12)],
                    "pattern_from_0.5": [s for s, a in lib.steps(0.5, 12)]}
    # (5) the float's monotonicity (incl. a full reversal) and the lanes as the extremes; (6) the gaps
    rng = np.random.default_rng(args.seed)
    nseq, k = 20000, 40
    keys = rng.integers(-1, 2, size=(nseq, k)).astype(np.int64)
    # reversals: hold one way then the other (the Umbrella Turn)
    keys[:2000, :20] = 1
    keys[:2000, 20:] = -1
    keys[2000:4000, :20] = -1
    keys[2000:4000, 20:] = 1
    viol = 0
    lane_viol = 0
    vmax = float(P[km.P_GL_VMAX])
    grid = np.linspace(-vmax, vmax, 35)
    prev = None
    left = np.full((1, k), -1, dtype=np.int64)
    right = np.full((1, k), 1, dtype=np.int64)
    for v0 in grid:
        out = np.zeros((nseq, k))
        _float_x(float(v0), keys, P, out)
        lo = np.zeros((1, k))
        hi = np.zeros((1, k))
        _float_x(float(v0), left, P, lo)
        _float_x(float(v0), right, P, hi)
        lane_viol += int(np.sum((out < lo - 1e-12) | (out > hi + 1e-12)))
        if prev is not None:
            viol += int(np.sum(out < prev - 1e-12))
        prev = out
    rep["float_monotone"] = {"vx_grid": len(grid), "sequences": nseq, "steps": k, "reversals": 4000,
                             "violations_vx_order": viol, "members_outside_lanes": lane_viol}
    gaps = {}
    for v0 in (0.0, vmax):
        for kk in (4, 6, 8, 10):
            seqs = np.array(np.meshgrid(*[[-1, 0, 1]] * kk, indexing="ij")).reshape(kk, -1).T.astype(np.int64)
            out = np.zeros((len(seqs), kk))
            _float_x(float(v0), np.ascontiguousarray(seqs), P, out)
            xs = np.unique(out[:, -1])
            gaps[f"vx{v0:g}_k{kk}"] = {"points": int(len(xs)), "span": float(xs[-1] - xs[0]),
                                       "max_gap": float(np.max(np.diff(xs))) if len(xs) > 1 else 0.0}
    rep["float_gaps"] = gaps
    rep["run_gap"] = float(P[km.P_RUN] * P[km.P_FDT])
    # (7) the entry vx at Float Idle: every key pattern of the Inflate (3^m), the antic's keys sampled
    S0, _ = env.canonical(lib.params, "A1", 0, 0, "", False)
    ms = [km.B_JUMP]
    for _ in range(40):
        x = env._roll_final(lib.params, S0, ms)
        if x[km.MODE] == km.M_GLIDE and x[km.PHASE] == 2.0:
            break
        ms.append(km.B_JUMP)
    nfl = len(ms)                      # frames from the open to Float Idle
    xa = [env._roll_final(lib.params, S0, ms[:j]) for j in range(1, nfl + 1)]
    n_antic = sum(1 for x in xa if x[km.MODE] == km.M_GLIDE and x[km.PHASE] == 0.0)
    m_infl = nfl - n_antic
    dirs = np.array([0, km.B_LEFT, km.B_RIGHT])
    m_enum = min(m_infl, 11)
    combos = np.array(np.meshgrid(*[[0, 1, 2]] * m_enum, indexing="ij")).reshape(m_enum, -1).T
    masks = np.zeros((len(combos), nfl), dtype=np.int64)
    masks[:, :] = km.B_JUMP
    masks[:, nfl - m_enum:] |= dirs[combos]
    xy, md = lib.eng.rollouts(np.repeat(S0[None], len(masks), axis=0),
                              np.repeat(np.array([[-1.0, 0, 0, 0, 0, 0, 0]]), len(masks), axis=0), masks)
    # the vx at the end: re-roll the finals (rollouts give positions only)
    vxs = []
    for i in range(0, len(masks), max(1, len(masks) // 4000)):
        vxs.append((int(combos[i, -1]), env._roll_final(lib.params, S0, masks[i])[km.VX]))
    vxs = np.array(vxs)
    by_last = {["none", "left", "right"][c]: int(len(np.unique(vxs[vxs[:, 0] == c, 1]))) for c in range(3)}
    # the antic's keys: patterns differing only there
    am = np.zeros((300, nfl), dtype=np.int64) + km.B_JUMP
    am[:, :n_antic] |= dirs[rng.integers(0, 3, size=(300, n_antic))]
    av = np.array([env._roll_final(lib.params, S0, am[i])[km.VX] for i in range(300)])
    lanes = [env._roll_final(lib.params, S0, [km.B_JUMP | d] * nfl)[km.VX] for d in (km.B_LEFT, km.B_RIGHT)]
    rep["entry_vx"] = {"frames_open_to_float_idle": nfl, "antic_frames": n_antic, "inflate_frames": m_infl,
                       "enumerated_inflate_frames": m_enum, "patterns": int(len(masks)),
                       "distinct_vx_sampled_by_last_key": by_last,
                       "distinct_vx_over_antic_keys": int(len(np.unique(av))),
                       "lanes_vx": [float(v) for v in lanes]}
    # (8) the spec's table view of some steady starts: the continue reference, the frame-0 actions to their steady ends
    views = {}
    kd = lib.kinds()
    for kind, ph, var in (("A1", 0, ""), ("A1", 10, ""), ("A4", 0, ""), ("A2", 0, "claw"), ("A3", 0, "N"),
                          ("A3", 30, "L")):
        S, terr = env.canonical(lib.params, kind, ph, 0, var, False)
        st, L, absy, dashed = lib.start_lanes(S)
        n = lib.node_of(L, st.cu, absy)
        # the canonical start's own lanes (no key yet): one frame without a step gives the lanes' steady node
        n = int(lib.EI[[e for e in lib.edges(n, 0.0, 0) if lib.EF[e, tb.EF_NEV] == 0][0], tb.EI_CH])
        kd = lib.kinds() if n >= len(kd) else kd
        tv = lib.table(n, alpha=0.5, depth=args.view_depth, max_leaves=20000, kinds=kd)
        ends = {}
        for a in tv["actions"]:
            ends[a["end"]["kind"]] = ends.get(a["end"]["kind"], 0) + 1
        views[f"{kind}{var}@{ph}"] = {
            "node": tv["node"], "kind": tv["kind"], "vy": tv["vy"], "edges": tv["n_edges"], "continue": tv["continue"],
            "action_leaves": len(tv["actions"]), "truncated": tv["truncated"], "ends_by_kind": ends,
            "dt_to_steady": _q([a["end"]["dt"] for a in tv["actions"] if a["end"]["steady"]]),
            "example": tv["actions"][0] if tv["actions"] else None}
    rep["table_views"] = views
    print(json.dumps(rep, default=float)[:4000], flush=True)
    Path(args.out).write_text(json.dumps(rep, indent=1, default=float))
    return 0


# ---- the flattened layer ----------------------------------------------------------------------------------------

FLAT_KEYS = ([("A1", k, "") for k in range(0, 31)] + [("A4", 0, ""), ("A2", 0, "claw"), ("A2", 0, "pogo")] +
             [("A3", k, v) for v in ("L", "N", "R") for k in (0, 10, 20, 30, 40, 50)] +
             [("G", 0, ""), ("G", 0, "L"), ("G", 0, "R")])


def flat_cmd(args) -> int:
    """The flattened tables of the canonical steady starts (FLAT_KEYS x the 6 physics-phase classes; the air ones in
    free space, the ground ones on the floor): per frame and end condition the union rows (q 0.05 u) of the chain's
    <= args.maxev-event family over args.T frames, saved as a knowledge npz (env.save_tables' layout); checks: the
    file's rows hold the chain's exact points (sampled), the danger-cut chain equals them before the first touch,
    the lookup time."""
    idle()
    from ssbot.tools import m1_envelope as m1
    lib = tb.Lib.load(args.lib or tb.tables_path(not args.no_claw, args.terrain))
    T, mev = args.T, args.maxev
    tabs, stat = {}, {}
    t0 = time.perf_counter()
    for kind, ph, var in FLAT_KEYS:
        for ac in range(6):
            S, terr = env.canonical(lib.params, kind, ph, ac, var, False)
            fl = lib.flat(S, T, maxev=mev, floor=(kind == "G"))
            name = f"{kind}{var}@{ph}/a{ac}"
            tabs[name] = {"all": fl[0], "dslash": fl[ej.COND_DSLASH], "claw": fl[ej.COND_CLAW],
                          "_counts": fl["clusters"]}
            stat[name] = {"ms": round(fl["seconds"] * 1e3, 2), "rows_T": len(fl[0][-1]),
                          "box_T": fl["box"][-1].tolist()}
    build_s = time.perf_counter() - t0
    out_path = Path(args.lib_out) if args.lib_out else tb.tables_path(lib.claw, lib.terrain).with_name(
        f"a1n_flat_v{tb.VERSION}_ev{mev}_t{T}.npz")
    arrs = {"_meta": np.array(json.dumps({"version": tb.VERSION, "T": T, "maxev": mev, "q": env.QROW,
                                          "keys": list(tabs), "claw": lib.claw, "terrain": lib.terrain,
                                          "hero2": int(lib.P[km.P_H2]), "params_vector_sha1": tb._sha1(lib.P),
                                          "built_s": round(build_s, 1)}))}
    for k, tbl in tabs.items():
        for c in ("all", "dslash", "claw"):
            fr = tbl[c]
            off = np.zeros(len(fr) + 1, dtype=np.int64)
            off[1:] = np.cumsum([len(r) for r in fr])
            cat = np.concatenate([r for r in fr if len(r)] or [np.zeros((0, 3))])
            arrs[f"{k}|{c}|off"] = off
            arrs[f"{k}|{c}|bin"] = cat[:, 0].astype(np.int32)
            x = np.empty((len(cat), 2), dtype=np.float32)
            x[:, 0] = np.nextafter(cat[:, 1].astype(np.float32), np.float32(-np.inf))
            x[:, 1] = np.nextafter(cat[:, 2].astype(np.float32), np.float32(np.inf))
            arrs[f"{k}|{c}|x"] = x
        arrs[f"{k}|counts"] = np.asarray(tbl["_counts"], dtype=np.int64)
    np.savez_compressed(out_path, **arrs)
    size = out_path.stat().st_size
    # checks
    ft = env.Tables(out_path)
    rng = np.random.default_rng(args.seed)
    miss = tot = 0
    first_ok = first_n = 0
    for name in rng.choice(list(tabs), size=min(40, len(tabs)), replace=False):
        kind_var, rest = name.split("@")
        ph = int(rest.split("/")[0])
        ac = int(rest.split("/a")[1])
        kind = "G" if kind_var.startswith("G") else kind_var[:2]
        var = kind_var[1:] if kind == "G" else kind_var[2:]
        S, terr = env.canonical(lib.params, kind, ph, ac, var, False)
        fw = lib.forward(S, T, floor=(kind == "G"), maxev=mev)
        xs, ys = float(S[km.PX]), float(S[km.PY] + lib.hh)
        for t in rng.choice(np.arange(1, T + 1), size=8, replace=False):
            g, x0, x1, y0, y1 = fw.frame_rows(int(t))
            for k in rng.choice(len(g), size=min(30, len(g)), replace=False):
                x = float(rng.uniform(x0[k], x1[k]))
                tot += 1
                if not ft.contains(name, "all", int(t), x - xs, float(y0[k]) - ys):
                    miss += 1
        # the danger-cut chain before its first touch: the flattened rows
        dz = m1.random_danger(rng, S, T, lib.hh)
        fd = lib.forward(S, T, floor=(kind == "G"), maxev=mev, danger=dz)
        touch = next((t for t in range(T + 1) if fd.stats[t, 2] > 0 or fd.count(t) != fw.count(t)), T + 1)
        for t in range(1, min(touch, T + 1)):
            first_n += 1
            a = env.raster(np.column_stack([fd.frame_rows(t)[3], fd.frame_rows(t)[4], fd.frame_rows(t)[1],
                                            fd.frame_rows(t)[2]]), xs, ys)
            first_ok += int(np.array_equal(np.asarray(a, np.float64), np.asarray(tabs[name]["all"][t], np.float64)))
    # lookup time
    names = list(tabs)
    q = [(names[int(rng.integers(len(names)))], int(rng.integers(1, T + 1)), float(rng.uniform(-6, 6)),
          float(rng.uniform(-4, 4))) for _ in range(2000)]
    t1_ = time.perf_counter()
    for nm, t, dx, dy in q:
        ft.contains(nm, "all", t, dx, dy)
    look_us = (time.perf_counter() - t1_) / len(q) * 1e6
    rep = {"T": T, "maxev": mev, "tables": len(tabs), "file": str(out_path), "file_MB": round(size / 1e6, 2),
           "build_s": round(build_s, 1), "ms_per_table": _q([v["ms"] for v in stat.values()]),
           "rows_T": _q([v["rows_T"] for v in stat.values()]), "points": tot, "outside": miss,
           "frames_before_first_touch": first_n, "equal_there": first_ok, "lookup_us": round(look_us, 2)}
    print(json.dumps(rep), flush=True)
    Path(args.out).write_text(json.dumps({"summary": rep, "stat": stat}, default=float))
    return 0


# ---- entry from any state: transitional starts -------------------------------------------------------------------

ENTRY_KINDS = ("dslash", "claw", "pogo", "umbrella", "deflate", "gdash", "skid", "hang", "cancel", "sjump",
               "scancel")


def transitional_starts(lib, S_all, lab, rng, n_per: int = 40):
    """Exact states in the middle of an action (the lead's note 'ENTRY FROM ANY STATE', spec on main): from recorded
    starts (and canonical ones), the action pressed at frame 0 and the state k frames into it, rolled by the
    reference model (env_jit.ref_rollout: kin_jit + the Clawline block; km.rollout for the pogo event): mid down
    slash, mid Clawline (its block: cu), a pogo bounce's lock, the umbrella's antic / inflate, the Deflate, a ground
    dash / sprint, the sprint's skid, the hang (jump held through the apex), the float's attack cancel, the sprint
    (shuttlecock) jump's antic / rise and its attack cancel (T1b). Returns [(S, cu, label)]."""
    P, udt = lib.P, lib.udt
    air = [i for i in range(len(S_all)) if S_all[i][km.GROUND] <= 0 and S_all[i][km.MODE] == km.M_NORMAL
           and S_all[i][km.TS] == 1.0]
    gnd = [i for i in range(len(S_all)) if S_all[i][km.GROUND] > 0 and S_all[i][km.MODE] == km.M_NORMAL
           and S_all[i][km.TS] == 1.0]
    flt = [i for i in range(len(S_all)) if S_all[i][km.MODE] == km.M_GLIDE and S_all[i][km.PHASE] == 2.0
           and S_all[i][km.TS] == 1.0]
    cu0 = np.array([-1.0, 0, 0, 0, 0, 0, 0])
    out = []

    def roll(S, masks, TT=None):
        masks = np.asarray(masks, dtype=np.int64)
        xy = np.zeros((len(masks) + 1, 2))
        md = np.zeros(len(masks) + 1, dtype=np.int64)
        x, cu = ej.ref_rollout(np.asarray(S, np.float64).copy(), cu0.copy(), masks, udt, P,
                               lib.TTf if TT is None else TT, xy, md)
        return x, cu

    for kind in ENTRY_KINDS:
        src = {"gdash": gnd, "skid": gnd, "sjump": gnd, "scancel": gnd, "deflate": flt, "cancel": flt}.get(kind, air)
        if not src:
            continue
        for i in rng.choice(src, size=min(n_per, len(src)), replace=False):
            S0 = S_all[i]
            d = int(rng.choice([km.B_LEFT, km.B_RIGHT]))
            TT = lib.TTg if kind in ("gdash", "skid", "sjump", "scancel") else None
            if kind == "dslash":
                k = int(rng.choice([1, 2, 4, 6, 9, 12]))
                ms = [km.B_ATTACK | km.B_DOWN] + [0] * (k - 1)
            elif kind == "claw":
                k = int(rng.choice([1, 3, 8, 12, 18, 22, 26, 30]))
                ms = [ej.B_CLAW | d] + [d] * (k - 1)
            elif kind == "umbrella":
                k = int(rng.choice([1, 3, 5, 8, 12, 16]))
                ms = [km.B_JUMP | d] * k
            elif kind == "deflate":
                k = int(rng.choice([1, 2, 4, 6, 8]))
                ms = [int(S0[km.PREV]) & ~km.B_JUMP] * k
            elif kind == "gdash":
                k = int(rng.choice([1, 3, 5, 7, 10, 16]))
                ms = [km.B_DASH | d] * k
            elif kind == "sjump":                         # (T1b: mid sprint jump - its antic / the 18 u/s rise)
                k = int(rng.choice([1, 3, 5, 7, 9, 12, 16]))
                ms = [km.B_DASH | d] * 12 + [km.B_DASH | d | km.B_JUMP] * k
            elif kind == "scancel":                       # (T1b: the sprint jump cancelled by an attack: the extra
                k = int(rng.choice([8, 10, 12]))          # air velocity, ShuttleCockCancel's decay)
                ms = ([km.B_DASH | d] * 12 + [km.B_DASH | d | km.B_JUMP] * k + [km.B_ATTACK] +
                      [0] * int(rng.choice([1, 2, 4, 6])))
            elif kind == "skid":
                k = int(rng.choice([1, 3, 6, 9]))
                ms = [km.B_DASH | d] * 24 + [0] * k
            elif kind == "hang":
                k = int(rng.choice([2, 5, 8, 12]))
                ms = [km.B_JUMP] * k                       # (from normal air: the umbrella opens unless the hang)
            elif kind == "cancel":
                k = int(rng.choice([1, 3, 6, 10]))
                ms = [km.B_JUMP | km.B_ATTACK] + [km.B_JUMP] * (k - 1)
            else:  # pogo
                k = int(rng.choice([1, 2, 4, 7, 10, 14]))
                masks = np.zeros(k, dtype=np.int64)
                ev = np.zeros(k, dtype=np.int64)
                ev[0] = km.EV_POGO
                x = env._roll_final(lib.params, S0, masks, ev)
                out.append((x, cu0.copy(), f"{kind}+{k}/{lab[i]}"))
                continue
            x, cu = roll(S0, ms, TT)
            out.append((x, cu, f"{kind}+{k}/{lab[i]}"))
    return out


def entry_cmd(args) -> int:
    """ENTRY FROM ANY STATE (the lead's note, the spec on main): the chain from transitional exact states - the rest
    of the transient rolled online with the exact model (the engine's frame, every remaining choice: the nodes not
    in the library are expanded on the fly) until the branches reach the library's nodes - against the engine."""
    idle()
    lib = _new_lib(args) if args.lib == "none" else tb.Lib.load(args.lib or tb.tables_path(not args.no_claw,
                                                                                        args.terrain))
    E = lib.eng
    rng = np.random.default_rng(args.seed)
    S_all, lab = load_starts()
    starts = transitional_starts(lib, S_all, lab, rng, n_per=args.n or 40)
    terr = lib.terr if args.floor else None
    opts = ej.OPT_NO_ADASH
    per = []
    t0 = time.perf_counter()
    kd = lib.kinds()
    for j, (S, cu, lb) in enumerate(starts):
        if not args.floor and S[km.GROUND] > 0:
            continue
        for mev, T in ((0, args.T), (1, 60), (2, 30)):
            fe = E.forward(E.start_state(S, cu=cu), T, terrain=terr, opts=opts, max_events=mev, claw=lib.claw,
                           tf8=lib.claw)
            ft = lib.forward(S, T, floor=args.floor, maxev=mev, cu=cu)
            ft2 = lib.forward(S, T, floor=args.floor, maxev=mev, cu=cu)
            r = compare(fe, ft, T)
            # the transient: frames until every cluster sits on a node the library had before this start
            n_lib = len(kd)
            tr = next((t for t in range(T + 1) if np.all(ft.node[int(ft.cl_off[t]):int(ft.cl_off[t + 1])] < n_lib)),
                      None)
            r.update({"label": lb, "kind": lb.split("+")[0], "mev": mev, "T": T, "mode": int(S[km.MODE]),
                      "phase": int(S[km.PHASE]), "in_block": bool(cu[ej.C_CJ] >= 0),
                      "ms_engine": fe.seconds * 1e3, "ms_tables": ft2.seconds * 1e3,
                      "ms_tables_cold": ft.seconds * 1e3, "transient_frames": tr, "lazy": ft.lib_stats})
            per.append(r)
            if not r["ok"]:
                print(f"{j:3d} {lb:44s} mev {mev} T {T} ok {r['ok']} {r}", flush=True)
        if args.reload and j and j % args.reload == 0 and args.lib != "none":
            lib = tb.Lib.load(args.lib or tb.tables_path(not args.no_claw, args.terrain))
            kd = lib.kinds()
        if j % 25 == 0:
            print(f"{j:3d}/{len(starts)} {lb:44s} ok so far {sum(p['ok'] for p in per)}/{len(per)}", flush=True)
    by = {}
    for p in per:
        b = by.setdefault(f"{p['kind']} ev{p['mev']}", {"n": 0, "exact": 0, "ms_e": [], "ms_t": [], "tr": []})
        b["n"] += 1
        b["exact"] += int(p["ok"])
        b["ms_e"].append(p["ms_engine"])
        b["ms_t"].append(p["ms_tables"])
        if p["transient_frames"] is not None:
            b["tr"].append(p["transient_frames"])
    summ = {"floor": args.floor, "claw": lib.claw, "terrain": lib.terrain, "starts": len(starts), "passes": len(per),
            "exact": sum(p["ok"] for p in per), "worst_dx": max([p["worst_dx"] for p in per] or [0.0]),
            "by_kind": {k: {"n": v["n"], "exact": v["exact"], "ms_engine_p50": _q(v["ms_e"], (50,)),
                            "ms_tables_p50": _q(v["ms_t"], (50,)), "transient_frames": _q(v["tr"], (50, 90, 100))}
                        for k, v in sorted(by.items())},
            "wall_s": round(time.perf_counter() - t0, 1)}
    print(json.dumps(summ), flush=True)
    Path(args.out).write_text(json.dumps({"summary": summ, "per": per}, default=float))
    return 0


def header_cmd(args) -> int:
    """The tracked knowledge header (knowledge/1.0.30000/kinematics/a1n_tables_v1.json) of the generated, untracked
    library files: their version, hero model, configuration, counts, sizes and sha1 - and how to rebuild them."""
    import hashlib
    kdir = tb.TABLES_PATH.parent
    files = {}
    for p in sorted(kdir.glob(f"a1n_*_v{tb.VERSION}*.npz")):
        z = np.load(p)
        meta = json.loads(str(z["_meta"]))
        h = hashlib.sha1(p.read_bytes()).hexdigest()
        keep = {k: meta.get(k) for k in ("version", "kind", "claw", "terrain", "hero2", "abilities", "opts", "clear",
                                         "clear_up", "floor_top", "ceil_bot", "nodes", "edges", "classes",
                                         "instances", "params", "params_vector_sha1", "built", "build_s",
                                         "depth_limit", "warm_passes", "warm_starts", "T", "maxev", "q")
                if k in meta}
        keep.update({"bytes": p.stat().st_size, "sha1": h})
        files[p.name] = keep
    out = {"version": tb.VERSION, "what": "map2 stage T1: the A1_n no-dash table library (ssbot.map2.tables) - the "
                                          "M1 engine's per-cluster frame memoised on relative cluster states "
                                          "(nodes), with their edges per physics-step count; the flattened rows of "
                                          "the canonical steady starts",
           "rebuild": ["python -m ssbot.tools.t1_tables build OUT.json --depth 6",
                       "python -m ssbot.tools.t1_tables build OUT.json --depth 6 --no-claw --terrain arena",
                       "python -m ssbot.tools.t1_tables flat OUT.json --T 120 --maxev 1"],
           "hero_model": "kinematics/hero_wanderer_forum.json + SSBOT_FORUM_HERO2 (kinematics.HERO2_OVERRIDES, every "
                         "H2 bit of the build: the 'hero2' field); a library refuses to load under another hero model "
                         "(params_vector_sha1)",
           "files": files}
    path = tb.TABLES_PATH.with_suffix(".json")
    path.write_text(json.dumps(out, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
    print(path, json.dumps({k: (v["bytes"], v.get("nodes")) for k, v in files.items()}))
    Path(args.out).write_text(json.dumps(out, indent=1, default=str))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["build", "exact", "contain", "witness", "checks", "flat", "header", "entry"])
    ap.add_argument("out")
    ap.add_argument("--lib", default="", help="the library file (default: the knowledge file)")
    ap.add_argument("--T", type=int, default=24)
    ap.add_argument("--n", type=int, default=0)
    ap.add_argument("--floor", action="store_true")
    ap.add_argument("--canon", action="store_true", help="also the canonical starts (x 6 phase classes)")
    ap.add_argument("--maxev", type=int, default=0)
    ap.add_argument("--cap-cl", type=int, default=400_000)
    ap.add_argument("--depth", type=int, default=0)
    ap.add_argument("--max-nodes", type=int, default=3_000_000)
    ap.add_argument("--rolls", type=int, default=300)
    ap.add_argument("--targets", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--no-claw", action="store_true", help="the library without the Clawline (the search's passes)")
    ap.add_argument("--terrain", default="floor", choices=list(tb.TERRAINS))
    ap.add_argument("--passes", default="1:60,2:30", help="build: the warm-up passes (events:frames, ...)")
    ap.add_argument("--lib-out", default="", help="flat: the output file")
    ap.add_argument("--view-depth", type=int, default=30, help="checks: the table view's depth (frames)")
    ap.add_argument("--reload", type=int, default=0, help="reload the library every n starts (bounds the lazy growth)")
    ap.add_argument("--danger", action="store_true", help="exact: m1's random moving danger boxes cut both passes")
    args = ap.parse_args(argv)
    return {"build": build_cmd, "exact": exact_cmd, "contain": contain_cmd, "witness": witness_cmd,
            "checks": checks_cmd, "flat": flat_cmd, "header": header_cmd, "entry": entry_cmd}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
