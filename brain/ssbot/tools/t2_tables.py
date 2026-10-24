"""Map v2 stage T2: the air dash as the bridge (ssbot.map2.bridge, tables.Lib.forward(dash=True)) - exactness against
the M1 engine WITH the air dash (and with danger), the dash bundle, the backward sets and the strike windows, timings.
Offline; nothing in the bot imports it.

    python -m ssbot.tools.t2_tables exact OUT.json [--T 30] [--maxev 2] [--floor] [--danger] [--n 0] [--no-claw]
    python -m ssbot.tools.t2_tables bundle OUT.json [--no-claw]
    python -m ssbot.tools.t2_tables sits OUT.json [--n 0]       # M3's 236 situations: (b) the passes with the search's
    #                                                             danger, (c) the windows, the backward sets, timings

exact (a): per start (the 400 recorded M1 starts and the canonical ones) the engine's pass with the air dash
(Engine.forward, opts 0) against the chain with the bridge (Lib.forward(dash=True)): per frame the x interval sets per
(height, end-condition bits) - heights bit-equal, ends within t1_tables.TOL_X.
sits (b, c): per situation the search's root (its prediction) and its approach passes ((1, 60), (2, 30): the union of
the branches' damage with the margins + the walls, the arena) and an exit check per branch ((1, 40) from her state in
that branch's danger): engine vs tables; the windows (search.Searcher.windows' rows before its selection) of both
passes compared; every window's backward set over the tables' chain must hold her start; the windows only the bridge
reaches (not the no-dash chain) and the presses on their tubes.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from ssbot.knowledge import kinematics as km
from ssbot.map2 import bridge as br
from ssbot.map2 import env_jit as ej
from ssbot.map2 import envelope as env
from ssbot.map2 import tables as tb
from ssbot.tools import t1_tables as t1

DATA = Path("C:/ssbot/data/m2_play/map2/a1n/t2")


def _q(v, ps=(50, 90, 99, 100)):
    return t1._q(v, ps)


def _lib(args):
    if args.lib == "none":
        return tb.Lib(claw=not args.no_claw, terrain=args.terrain)
    return tb.Lib.load(args.lib or tb.tables_path(not args.no_claw, args.terrain))


# ---- (a) exactness with the air dash ----------------------------------------------------------------------------

def exact_cmd(args) -> int:
    t1.idle()
    lib = _lib(args)
    E = lib.eng
    S_all, lab = t1.load_starts(args.n)
    starts = [(S, lb, g) for (S, lb, g) in t1.canon_starts(lib.params)] if args.canon else []
    starts += [(S_all[i], lab[i], bool(S_all[i][km.GROUND] > 0)) for i in range(len(S_all))]
    terr = lib.terr if args.floor else None
    rng = np.random.default_rng(args.seed)
    per = []
    t0 = time.perf_counter()
    for i, (S, lb, gnd) in enumerate(starts):
        if gnd and not args.floor:
            continue
        if S[km.TS] != 1.0 or S[km.WF_S] != 1.0:
            continue
        if args.reload and len(per) and len(per) % args.reload == 0:
            lib = _lib(args)
        dz = None
        if args.danger:
            from ssbot.tools import m1_envelope as m1
            dz = m1.random_danger(rng, S, args.T, lib.hh)
        fe = E.forward(E.start_state(S), args.T, terrain=terr, opts=0, max_events=args.maxev, claw=lib.claw,
                       tf8=lib.claw, danger=dz)
        ft = lib.forward(S, args.T, floor=args.floor, maxev=args.maxev, danger=dz, dash=True)
        ft2 = lib.forward(S, args.T, floor=args.floor, maxev=args.maxev, danger=dz, dash=True)
        r = t1.compare(fe, ft, args.T)
        dashed = int(np.sum(ft.ad[int(ft.cl_off[args.T]):int(ft.cl_off[args.T + 1])] > 0))
        r.update({"i": i, "label": lb, "ground": gnd, "clusters_engine": fe.count(args.T),
                  "clusters_tables": ft.count(args.T), "clusters_dashed_T": dashed, "ms_engine": fe.seconds * 1e3,
                  "ms_tables_cold": ft.seconds * 1e3, "ms_tables": ft2.seconds * 1e3, "lazy": ft.lib_stats})
        per.append(r)
        if not r["ok"] or len(per) % 25 == 1:
            print(f"{i:3d} {lb:34s} ok {r['ok']} only e/t {r['only_engine']}/{r['only_tables']} len {r['len_diff']} "
                  f"dx {r['worst_dx']:.2e} first {r['first_bad']} clusters e/t {r['clusters_engine']}/"
                  f"{r['clusters_tables']} (dashed {dashed}) ms e {r['ms_engine']:.1f} t {r['ms_tables']:.1f} "
                  f"(cold {r['ms_tables_cold']:.1f}) nodes {lib.n_nodes}", flush=True)
    summ = {"T": args.T, "floor": args.floor, "maxev": args.maxev, "danger": args.danger, "claw": lib.claw,
            "terrain": lib.terrain, "starts": len(per), "exact": sum(r["ok"] for r in per),
            "dead_engine": int(sum(r["clusters_engine"] == 0 for r in per)),
            "worst_dx": max([r["worst_dx"] for r in per] or [0.0]),
            "ms_engine": _q([r["ms_engine"] for r in per]), "ms_tables": _q([r["ms_tables"] for r in per]),
            "ms_tables_cold": _q([r["ms_tables_cold"] for r in per]),
            "speedup_p50": round(float(np.median([r["ms_engine"] / max(r["ms_tables"], 1e-3) for r in per])), 2)
            if per else None,
            "clusters_engine": _q([r["clusters_engine"] for r in per]),
            "clusters_dashed_T": _q([r["clusters_dashed_T"] for r in per]),
            "wall_s": round(time.perf_counter() - t0, 1), "library_nodes_after": lib.n_nodes}
    print(json.dumps(summ), flush=True)
    Path(args.out).write_text(json.dumps({"summary": summ, "per": per}, default=float))
    return 0


# ---- the bundle -------------------------------------------------------------------------------------------------

def bundle_cmd(args) -> int:
    """The dash bundle of the canonical air starts (A1_n n = 0 .. 30, A2 / A3 / A4) per physics-phase class, in free
    space: entries, states, ends grouped by (end node, dt, dy); the ends relative to the press frame compared over
    A1_n (the spec: the same bundle from every A1_n)."""
    t1.idle()
    lib = _lib(args)
    rep = {"per": {}, "shared": {}}
    t0 = time.perf_counter()
    groups = {}
    for ac in range(6):
        for n in range(0, 31):
            S, _ = env.canonical(lib.params, "A1", n, ac, "", False)
            b = br.bundle(lib, S, T=args.T)
            rel = br.bundle_relative(b)
            # (the phase of the press frame: the step pattern - A1_n of one phase class reach other phases by n)
            pat = tuple(sv for sv, _ in lib.steps(float(S[km.ALPHA]), args.T + 1))
            groups.setdefault(pat, []).append((n, ac, rel))
            ends = b["ends"]
            dts = [k[1] for k in ends]
            rep["per"][f"A1@{n}/a{ac}"] = {"alpha": float(S[km.ALPHA]), "entries": len(b["press"]),
                                          "states": b["states"], "end_groups": len(ends),
                                          "end_nodes": len({k[0] for k in ends}), "dt": _q(dts, (0, 50, 100)),
                                          "intervals": int(sum(len(v) for v in ends.values())),
                                          "end_kinds": _kinds(lib, ends)}
    for al, lst in sorted(groups.items()):
        r0 = lst[0][2]
        shape0 = sorted((k[1], k[2], str(v)) for k, v in r0.items())
        same = sum(r == r0 for _, _, r in lst)
        same_shape = sum(sorted((k[1], k[2], str(v)) for k, v in r.items()) == shape0 for _, _, r in lst)
        rep["shared"]["".join(str(v) for v in al[:12])] = {"starts": [(n, ac) for n, ac, _ in lst], "identical": int(same),
                                        "same_dt_dy_x": int(same_shape), "of": len(lst)}
        print(f"steps {''.join(str(v) for v in al[:12])}: {len(lst)} A1_n, identical {same}, same (dt, dy, x) {same_shape} "
              f"{time.perf_counter() - t0:.1f} s", flush=True)
    for kind, ph, var in (("A2", 0, "claw"), ("A2", 10, "claw"), ("A3", 0, "N"), ("A3", 20, "L"), ("A4", 0, "")):
        S, _ = env.canonical(lib.params, kind, ph, 0, var, False)
        b = br.bundle(lib, S, T=args.T)
        rep["per"][f"{kind}{var}@{ph}/a0"] = {"entries": len(b["press"]), "states": b["states"],
                                              "end_groups": len(b["ends"]), "end_kinds": _kinds(lib, b["ends"])}
    rep["seconds"] = round(time.perf_counter() - t0, 1)
    rep["library_nodes"] = lib.n_nodes
    print(json.dumps({k: v for k, v in rep.items() if k != "per"}), flush=True)
    Path(args.out).write_text(json.dumps(rep, indent=1, default=float))
    return 0


def _kinds(lib, ends) -> dict:
    kd = lib.kinds()
    out = {}
    for (n, dt, dy) in ends:
        k = tb.KIND_NAMES[kd[n]] if n < len(kd) else "?"
        m = int(lib.NINT[n, tb.I_MODE])
        name = f"{k}/m{m}"
        out[name] = out.get(name, 0) + 1
    return out


# ---- (b, c) the situations ---------------------------------------------------------------------------------------

def win_rows(sr, node, fw) -> dict:
    """search.Searcher.windows' rows before its selection: {(kind, branch rank, iid, dc or d, t): [(cluster, lo, hi),
    ...]} - every row of the pass that meets a down slash window (the contact at press + dc on the robust body, her
    height at the contact in its band) or a hooked Clawline's ray (its height band, the side d)."""
    from ssbot.map2 import brnum, strike as sk
    cfg = sr.cfg
    out = {}
    brs = sorted(node.pred.branches, key=lambda b: -b.p)[:cfg.n_branch]
    R = sr._rows(fw)
    n = len(R["t"])
    if not n:
        return out
    for bi, b in enumerate(brs):
        for iid in brnum.iids(b):
            boxes = sk.robust_boxes(b, iid, node.pred.T)
            nb_ = len(boxes)
            if "dslash" in cfg.prims:
                done = np.zeros(n, bool)
                base = (R["t"] + node.k0 >= node.next_atk) & ((R["cond"] & ej.COND_DSLASH) != 0)
                for dc in (4, 3, 6):
                    c = node.k0 + R["t"] + 1 + dc
                    bx = boxes[np.minimum(c, nb_ - 1)]
                    ok = base & ~done & (c < nb_) & ~np.isnan(bx[:, 0])
                    if not ok.any():
                        continue
                    rx0, rx1 = bx[:, 0] - 1.742, bx[:, 2] + 1.742
                    ry0, ry1 = bx[:, 1] + 0.368 - sk.CTR_DY, bx[:, 3] + 2.676 - sk.CTR_DY
                    yc = R["y"] + R["vy"] * dc / 60.0 - 0.5 * 60.0 * (dc / 60.0) ** 2
                    sel = ok & (R["x1"] >= rx0 - 0.5) & (R["x0"] <= rx1 + 0.5) & (yc >= ry0) & (yc <= ry1)
                    done |= sel
                    for i in np.flatnonzero(sel):
                        a_, b_ = max(R["x0"][i], rx0[i] - 0.5), min(R["x1"][i], rx1[i] + 0.5)
                        out.setdefault(("dslash", bi, iid, dc, int(R["t"][i])), []).append((int(R["g"][i]), a_, b_))
            if "claw" in cfg.prims:
                hit = node.k0 + R["t"] + 1 + sk.HOOK_HIT_F
                bx = boxes[np.minimum(hit, nb_ - 1)]
                ok = ((R["cond"] & ej.COND_CLAW) != 0) & (hit < nb_) & ~np.isnan(bx[:, 0])
                if ok.any():
                    bbh = R["y"] - sk.HALF_H + 0.0774 * np.clip(R["vy"], -10.0, 5.0)
                    band = (bx[:, 1] < bbh + sk.RAY_BAND[1]) & (bx[:, 3] > bbh + sk.RAY_BAND[0])
                    for d in (1, -1):
                        rx0, rx1 = ((bx[:, 0] - sk.RAY_U - 1.5, bx[:, 2]) if d > 0 else
                                    (bx[:, 0], bx[:, 2] + sk.RAY_U + 1.5))
                        sel = ok & band & (R["x1"] >= rx0) & (R["x0"] <= rx1)
                        for i in np.flatnonzero(sel):
                            a_, b_ = max(R["x0"][i], rx0[i]), min(R["x1"][i], rx1[i])
                            out.setdefault(("claw", bi, iid, d, int(R["t"][i])), []).append((int(R["g"][i]), a_, b_))
    return out


def _wsig(fw, rows) -> list:
    """A window's rows as a comparable signature: per (height, cond) the united x intervals."""
    d = {}
    for g, a, b in rows:
        d.setdefault((float(fw.cl_y[g]), int(fw.cl_cond[g])), []).append((a, b))
    return sorted((k, br._union(v)) for k, v in d.items())


def _wsig_eq(A, B, tol=1e-9) -> bool:
    if len(A) != len(B):
        return False
    for (ka, va), (kb, vb) in zip(A, B):
        if ka != kb or len(va) != len(vb):
            return False
        for (a0, a1), (b0, b1) in zip(va, vb):
            if abs(a0 - b0) > tol or abs(a1 - b1) > tol:
                return False
    return True


def sits_cmd(args) -> int:
    t1.idle()
    from ssbot.map2 import search as ms
    from ssbot.tools import m4b_speed as m4b
    lib = _lib(args)
    E = lib.eng
    sits = m4b.load_sits()
    if args.n:
        sits = sits[:args.n]
    W = ms.World()
    cfg = ms.Cfg()
    if args.passes:
        cfg = cfg.replace(passes=tuple(tuple(int(v) for v in x.split(":")) for x in args.passes.split(",")))
    sr = ms.Searcher(W, cfg)
    if not np.array_equal(W.TT, lib.TTg):
        print("note: the search's terrain differs from the library's (the engine runs on the library's)", flush=True)
    per = []
    t0 = time.perf_counter()
    for si, sit in enumerate(sits):
        if args.reload and si and si % args.reload == 0:
            lib = _lib(args)
        try:
            node = sr.root(sit)
        except Exception as ex:                               # (a situation the search cannot root)
            per.append({"i": si, "error": repr(ex)})
            continue
        S = node.S
        if S[km.TS] != 1.0 or S[km.WF_S] != 1.0:
            per.append({"i": si, "skipped": "time scale"})
            continue
        rec = {"i": si, "name": getattr(sit, "name", ""), "passes": []}
        for ne, H in sr.cfg.passes:
            dz = ms._union_danger(node.pred, node.k0, H, sr.cfg.margins, None)
            fe = E.forward(E.start_state(S), H, danger=dz, terrain=lib.terr, max_events=ne, claw=False, opts=0)
            ft = lib.forward(S, H, danger=dz, floor=True, maxev=ne, dash=True)
            ft2 = lib.forward(S, H, danger=dz, floor=True, maxev=ne, dash=True)
            cmp = t1.compare(fe, ft, H)
            t_w = time.perf_counter()
            we = win_rows(sr, node, fe)
            ms_we = (time.perf_counter() - t_w) * 1e3
            wt = win_rows(sr, node, ft2)
            ws_ok = set(we) == set(wt) and all(_wsig_eq(_wsig(fe, we[k]), _wsig(ft2, wt[k])) for k in we)
            # the no-dash chain's windows (F alone) and the backward set of every window over the tables' chain
            fn = lib.forward(S, H, danger=dz, floor=True, maxev=ne, dash=False)
            wn = win_rows(sr, node, fn)
            t_b = time.perf_counter()
            nb_ok = 0
            bridge_only = 0
            press_t = []
            for k, rows in wt.items():
                g = np.array([r[0] for r in rows])
                bk = br.backward(ft2, g, np.array([r[1] for r in rows]), np.array([r[2] for r in rows]))
                nb_ok += int(bk.reached())
                if k not in wn:
                    bridge_only += 1
                    ps = br.bridge_presses(bk)
                    if ps:
                        press_t.append(min(p[0] for p in ps))
            ms_back = (time.perf_counter() - t_b) * 1e3 / max(1, len(wt))
            rec["passes"].append({
                "ne": ne, "H": H, "ok": cmp["ok"], "only_e": cmp["only_engine"], "only_t": cmp["only_tables"],
                "len": cmp["len_diff"], "dx": cmp["worst_dx"], "first_bad": cmp["first_bad"],
                "clusters_e": fe.count(H), "clusters_t": ft.count(H), "ms_e": fe.seconds * 1e3,
                "ms_t": ft2.seconds * 1e3, "ms_t_cold": ft.seconds * 1e3, "ms_nodash": fn.seconds * 1e3,
                "windows_e": len(we), "windows_t": len(wt), "windows_equal": bool(ws_ok), "windows_nodash": len(wn),
                "nodash_subset": bool(set(wn) <= set(wt)), "back_reached": nb_ok, "bridge_only": bridge_only,
                "bridge_press_t": press_t, "ms_windows": ms_we, "ms_back_per_window": ms_back})
        # the exit check per branch from her state (the search's: <= 1 event, 40 frames, the branch's danger)
        ex = []
        for b in ([] if args.no_exits else node.pred.branches):
            dz, _, _ = ms._packed_danger(b, node.k0, sr.cfg.exit_h, -1, sr.cfg.margins)
            fe = E.forward(E.start_state(S), sr.cfg.exit_h, danger=dz, terrain=lib.terr,
                           max_events=sr.cfg.exit_events, claw=False, opts=0)
            ft = lib.forward(S, sr.cfg.exit_h, danger=dz, floor=True, maxev=sr.cfg.exit_events, dash=True)
            ft2 = lib.forward(S, sr.cfg.exit_h, danger=dz, floor=True, maxev=sr.cfg.exit_events, dash=True)
            c = t1.compare(fe, ft, sr.cfg.exit_h)
            ex.append({"ok": c["ok"], "alive_e": fe.count(sr.cfg.exit_h), "alive_t": ft.count(sr.cfg.exit_h),
                       "ms_e": fe.seconds * 1e3, "ms_t": ft2.seconds * 1e3})
        rec["exits"] = ex
        per.append(rec)
        ok = all(p["ok"] and p["windows_equal"] for p in rec["passes"]) and all(e["ok"] for e in ex)
        if not ok or si % 20 == 0:
            p0, p1 = rec["passes"][0], rec["passes"][-1]
            print(f"{si:3d} ok {ok} pass1 {p0['ok']} w {p0['windows_e']}/{p0['windows_t']} eq {p0['windows_equal']} "
                  f"bridge {p0['bridge_only']} ms {p0['ms_e']:.1f}/{p0['ms_t']:.1f} | pass2 {p1['ok']} w "
                  f"{p1['windows_e']}/{p1['windows_t']} eq {p1['windows_equal']} bridge {p1['bridge_only']} ms "
                  f"{p1['ms_e']:.1f}/{p1['ms_t']:.1f} | exits {sum(e['ok'] for e in ex)}/{len(ex)} nodes {lib.n_nodes} "
                  f"{time.perf_counter() - t0:.0f} s", flush=True)
    good = [p for p in per if "passes" in p]
    summ = {"situations": len(sits), "run": len(good), "errors": len(per) - len(good)}
    for pi, (ne, H) in enumerate(sr.cfg.passes):
        ps = [p["passes"][pi] for p in good]
        summ[f"pass_{ne}_{H}"] = {
            "exact": sum(p["ok"] for p in ps), "windows_equal": sum(p["windows_equal"] for p in ps),
            "windows_found_e": sum(p["windows_e"] for p in ps), "windows_found_t": sum(p["windows_t"] for p in ps),
            "back_reached": sum(p["back_reached"] for p in ps), "bridge_only": sum(p["bridge_only"] for p in ps),
            "nodash_subset": sum(p["nodash_subset"] for p in ps), "worst_dx": max([p["dx"] for p in ps] or [0]),
            "ms_engine": _q([p["ms_e"] for p in ps]), "ms_tables": _q([p["ms_t"] for p in ps]),
            "ms_tables_cold": _q([p["ms_t_cold"] for p in ps]), "ms_nodash": _q([p["ms_nodash"] for p in ps]),
            "ms_back_per_window": _q([p["ms_back_per_window"] for p in ps]),
            "speedup_p50": round(float(np.median([p["ms_e"] / max(p["ms_t"], 1e-3) for p in ps])), 2) if ps else None,
            "bridge_press_t": _q([t for p in ps for t in p["bridge_press_t"]])}
    exs = [e for p in good for e in p["exits"]]
    summ["exits"] = {"n": len(exs), "exact": sum(e["ok"] for e in exs), "ms_engine": _q([e["ms_e"] for e in exs]),
                     "ms_tables": _q([e["ms_t"] for e in exs]),
                     "verdict_equal": sum((e["alive_e"] > 0) == (e["alive_t"] > 0) for e in exs)}
    summ["wall_s"] = round(time.perf_counter() - t0, 1)
    summ["library_nodes_after"] = lib.n_nodes
    print(json.dumps(summ), flush=True)
    Path(args.out).write_text(json.dumps({"summary": summ, "per": per}, default=float))
    return 0


# ---- the window shapes (the lead's note windows) ---------------------------------------------------------------

def _abs_lane(lib, fw, g: int, ln: int, alpha: float) -> np.ndarray:
    """Cluster g's lane ln as an absolute kin state (x 0, her height, the frame's phase, its air dash)."""
    nd = int(fw.node[g])
    x = lib.NL[nd, ln].copy()
    if lib.NINT[nd, tb.I_ABS] == 0:
        py = float(fw.cl_y[g] - lib.hh)
        for f in (km.PY, km.QY, km.SY, km.RY0):
            x[f] += py
    x[km.AIRDASHED] = float(fw.ad[g])
    x[km.ALPHA] = alpha
    return x


def _bang_masks() -> np.ndarray:
    """Key sequences for the judge check: a down slash press, then hold a / release / hold b with two switch frames
    (L / none / R each) - every x reachable at two frames of the swing."""
    out = []
    keys = (km.B_LEFT, 0, km.B_RIGHT)
    for a in keys:
        for m in keys:
            for b in keys:
                for j1 in range(1, 10):
                    for j2 in range(j1, 10):
                        r = np.array([a] * j1 + [m] * (j2 - j1) + [b] * (10 - j2), np.int64)
                        r[0] |= km.B_ATTACK | km.B_DOWN
                        out.append(r)
    return np.unique(np.array(out), axis=0)


def _swing_paths(lib, fw, gs, k0_alpha: float):
    """Per cluster g of the tables' chain (frame t): her transform height, the run's reach and the ground flag over a
    down slash pressed in frame t + 1 (index 0 = the cluster's frame), rolled by the reference model from the node's
    representative at her height and the frame's phase: (ty [n, 11], L, R, ground)."""
    from ssbot.map2 import wshape  # noqa: F401
    n = len(gs)
    S0 = np.zeros((3 * n, km.K))
    cu0 = np.zeros((3 * n, ej.NC))
    masks = np.zeros((3 * n, 10), np.int64)
    AD = km.B_ATTACK | km.B_DOWN
    for i, g in enumerate(gs):
        t = int(np.searchsorted(fw.cl_off, g, side="right") - 1)
        nd = int(fw.node[g])
        al = lib.steps(k0_alpha, t + 1)[t][1] if t > 0 else k0_alpha
        for j, h in enumerate((0, km.B_LEFT, km.B_RIGHT)):
            x = _abs_lane(lib, fw, g, 0 if j == 1 else 1, al)       # (the left reach from the left lane: its MOVE
            S0[3 * i + j] = x                                       # acts in the press frame's steps)
            cu0[3 * i + j] = lib.NCU[nd]
            masks[3 * i + j, 0] = AD | h
            masks[3 * i + j, 1:] = h
    xy, md = ej.ref_many(S0, cu0, masks, lib.udt, lib.P, lib.TTg)
    ty = xy[0::3, :, 1] - lib.hh
    L = xy[1::3, :, 0] - xy[1::3, :1, 0]
    R = xy[2::3, :, 0] - xy[2::3, :1, 0]
    ground = xy[0::3, :, 1] <= tb.FLOOR_TOP + lib.params.foot + lib.hh + 1e-6
    return ty, L, R, ground


def _judge_check(lib, ft, g, t, k0n, boxes, shp, raw, ivs, alpha0, BM, chk, chk_n) -> None:
    """THE BISECTION CHECK against the strike judge (strike.dslash_contact on simulated paths): points just inside the
    shape's interval ends and its middle must be hit by some key sequence (BM, both facings' lanes), points just
    outside the ends (inside the cluster) by none."""
    from ssbot.map2 import strike as sk
    chk_n[0] += 1
    al = lib.steps(alpha0, t + 1)[t][1] if t > 0 else alpha0
    pts = []
    for u, v in br._union(shp):
        pts += [(u + 0.01, 1), (0.5 * (u + v), 1), (v - 0.01, 1)]
    for u, v in br._union(raw):
        pts += [(u - 0.02, 0), (v + 0.02, 0)]
    for xq, inside in pts:
        if inside and not any(a <= xq <= b for a, b in shp):
            continue
        if not inside and (any(a <= xq <= b for a, b in raw) or not any(a <= xq <= b for a, b in ivs)):
            continue
        hit = False
        for ln in (0, 1):
            x = _abs_lane(lib, ft, g, ln, al)
            x[km.PX] += xq
            x[km.QX] += xq
            x[km.SX] += xq
            n = len(BM)
            xy, md = ej.ref_many(np.repeat(x[None], n, 0), np.repeat(lib.NCU[int(ft.node[g])][None], n, 0), BM,
                                 lib.udt, lib.P, lib.TTg)
            face = 1 if ln == 1 else -1
            for r in range(n):
                pos = np.stack([xy[r, :, 0], xy[r, :, 1] - lib.hh], axis=1)
                gr = xy[r, :, 1] <= tb.FLOOR_TOP + lib.params.foot + lib.hh + 1e-6
                if sk.dslash_contact(pos, np.full(len(pos), face), gr, 1, boxes[k0n + t:k0n + t + len(pos)]) >= 0:
                    hit = True
                    break
            if hit:
                break
        if inside and not hit and BM.shape[0] < 20000:
            # every key sequence of the swing (3^9 after the press, both lanes): a miss of the bang-bang family only
            import itertools
            ex = np.array([[km.B_ATTACK | km.B_DOWN | a] + list(r) for a in (km.B_LEFT, 0, km.B_RIGHT)
                           for r in itertools.product((km.B_LEFT, 0, km.B_RIGHT), repeat=9)], np.int64)
            for ln in (0, 1):
                x = _abs_lane(lib, ft, g, ln, al)
                x[km.PX] += xq
                x[km.QX] += xq
                x[km.SX] += xq
                xy, md = ej.ref_many(np.repeat(x[None], len(ex), 0), np.repeat(lib.NCU[int(ft.node[g])][None],
                                     len(ex), 0), ex, lib.udt, lib.P, lib.TTg)
                face = 1 if ln == 1 else -1
                for r in range(len(ex)):
                    pos = np.stack([xy[r, :, 0], xy[r, :, 1] - lib.hh], axis=1)
                    gr = xy[r, :, 1] <= tb.FLOOR_TOP + lib.params.foot + lib.hh + 1e-6
                    if sk.dslash_contact(pos, np.full(len(pos), face), gr, 1, boxes[k0n + t:k0n + t + len(pos)]) >= 0:
                        hit = True
                        break
                if hit:
                    break
            chk["exhaustive_tried"] = chk.get("exhaustive_tried", 0) + 1
            chk["exhaustive_hit"] = chk.get("exhaustive_hit", 0) + int(hit)
            if not hit and len(chk.setdefault("miss_examples", [])) < 5:
                chk["miss_examples"].append({"g": g, "t": t, "x": xq, "shape": [list(v) for v in br._union(shp)]})
        key = "inside" if inside else "outside"
        chk[key] += 1
        chk[key + "_hit"] += int(hit)


def shapes_cmd(args) -> int:
    """The down slash windows as SHAPES (ssbot.map2.wshape: the exact press region per press frame x her state)
    against the search's window predicate (search.Searcher.windows' box test with the extrapolated height) on M3's
    situations: per (branch, Clapper, cluster at frame t) found by the predicate / by the shape / by both, and the
    shape's x length inside the cluster."""
    t1.idle()
    from ssbot.map2 import search as ms, wshape as wsh, brnum, strike as sk
    from ssbot.tools import m4b_speed as m4b
    lib = _lib(args)
    sits = m4b.load_sits()
    if args.n:
        sits = sits[:args.n]
    W = ms.World()
    sr = ms.Searcher(W, ms.Cfg())
    tot = {"pred": 0, "shape": 0, "both": 0, "pred_only": 0, "shape_only": 0}
    lens = []
    per = []
    BM = _bang_masks()
    chk = {"inside": 0, "inside_hit": 0, "outside": 0, "outside_hit": 0}
    chk_n = [0]
    t0 = time.perf_counter()
    for si, sit in enumerate(sits):
        try:
            node = sr.root(sit)
        except Exception:
            continue
        S = node.S
        ne, H = sr.cfg.passes[0]
        dz = ms._union_danger(node.pred, node.k0, H, sr.cfg.margins, None)
        ft = lib.forward(S, H, danger=dz, floor=True, maxev=ne, dash=True)
        rows = win_rows(sr, node, ft)
        pred = {}
        for k, rr in rows.items():
            if k[0] != "dslash":
                continue
            for g, a, b in rr:
                pred.setdefault((k[1], k[2], int(np.searchsorted(ft.cl_off, g, side="right") - 1), g), []).append((a, b))
        R_ = sr._rows(ft)
        cand = np.flatnonzero(((R_["cond"] & ej.COND_DSLASH) != 0) & (R_["t"] + node.k0 >= node.next_atk))
        gs = np.unique(R_["g"][cand])
        if not len(gs):
            continue
        ty, L, R, ground = _swing_paths(lib, ft, gs, float(S[km.ALPHA]))
        gi = {int(g): i for i, g in enumerate(gs)}
        brs = sorted(node.pred.branches, key=lambda b: -b.p)[:sr.cfg.n_branch]
        rec = dict.fromkeys(tot, 0)
        for bi, b in enumerate(brs):
            for iid in brnum.iids(b):
                boxes = sk.robust_boxes(b, iid, node.pred.T)
                for g in gs:
                    i = gi[int(g)]
                    t = int(np.searchsorted(ft.cl_off, g, side="right") - 1)
                    k0 = node.k0 + t
                    ivs = ft.intervals(int(g))
                    shp = []
                    raw = []
                    for face in (-1, 1):
                        # the press frame's own step: the facing F of the swing is a member that stepped toward F
                        # or stood (a turn happens in that step, before the press) - its first step is F's or none
                        Lf, Rf = L[i].copy(), R[i].copy()
                        if face > 0:
                            Lf[1:] -= L[i][1]
                        else:
                            Rf[1:] -= R[i][1]
                        for lo, hi in wsh.ds_press_set(boxes, k0, ty[i], Lf, Rf, ground[i], face):
                            raw.append((lo, hi))
                            for a, c in ivs:
                                u, v = max(lo, a), min(hi, c)
                                if u <= v:
                                    shp.append((u, v))
                    pk = (bi, iid, t, int(g))
                    p = pk in pred
                    rec["pred"] += p
                    rec["shape"] += bool(shp)
                    rec["both"] += p and bool(shp)
                    rec["pred_only"] += p and not shp
                    rec["shape_only"] += bool(shp) and not p
                    if shp:
                        lens.append(sum(v - u for u, v in br._union(shp)))
                    if args.check and chk_n[0] < args.check and (shp or p):
                        _judge_check(lib, ft, int(g), t, node.k0, boxes, shp, raw, ivs, float(S[km.ALPHA]), BM, chk,
                                     chk_n)
        for k in tot:
            tot[k] += rec[k]
        per.append({"i": si, **rec})
        if si % 20 == 0:
            print(f"{si:3d} {rec} total {tot} {time.perf_counter() - t0:.0f} s", flush=True)
    summ = {"situations": len(per), **tot, "shape_x_len": _q(lens), "judge_check": chk,
            "wall_s": round(time.perf_counter() - t0, 1)}
    print(json.dumps(summ), flush=True)
    Path(args.out).write_text(json.dumps({"summary": summ, "per": per}, default=float))
    return 0


def flat_cmd(args) -> int:
    """FLATTENED AND CHAINED, BOTH, on M3's situations: per situation her pass WITHOUT danger (the flattened union of
    her state, with the dash) for the exit check's horizon, its first touch of each branch's danger (bridge.touch_frame)
    - the danger-cut chain equals it frame for frame before the touch (checked), and an exit check whose danger never
    touches it is answered by it (alive at the horizon) - against the per-branch chains: the verdicts and the times."""
    t1.idle()
    from ssbot.map2 import search as ms
    from ssbot.tools import m4b_speed as m4b
    lib = _lib(args)
    sits = m4b.load_sits()
    if args.n:
        sits = sits[:args.n]
    W = ms.World()
    sr = ms.Searcher(W, ms.Cfg())
    H, ne = sr.cfg.exit_h, sr.cfg.exit_events
    res = {"exits": 0, "untouched": 0, "verdict_equal": 0, "prefix_equal": 0, "prefix_frames": 0, "touch": [],
           "ms_flat": [], "ms_touch": [], "ms_chain": []}
    t0 = time.perf_counter()
    for si, sit in enumerate(sits):
        try:
            node = sr.root(sit)
        except Exception:
            continue
        S = node.S
        # (the walls clip - the spec's use-time rule; the search cuts them as danger boxes: the same sets)
        wall = (float(ms.WALL_BOXES[0, 2]), float(ms.WALL_BOXES[1, 0]))
        lib.forward(S, H, floor=True, maxev=ne, dash=True, wall=wall)
        f0 = lib.forward(S, H, floor=True, maxev=ne, dash=True, wall=wall)
        res["ms_flat"].append(f0.seconds * 1e3)
        for b in node.pred.branches:
            dz, _, _ = ms._packed_danger(b, node.k0, H, -1, sr.cfg.margins)
            dzb = [ms.branch_danger(b, node.k0 + t, sr.cfg.margins) for t in range(H + 1)]
            t_ = time.perf_counter()
            tf = br.touch_frame(f0, dzb)
            res["ms_touch"].append((time.perf_counter() - t_) * 1e3)
            fd = lib.forward(S, H, danger=dz, floor=True, maxev=ne, dash=True)
            res["ms_chain"].append(fd.seconds * 1e3)
            res["exits"] += 1
            res["touch"].append(tf)
            upto = H if tf < 0 else tf - 1
            ok = all(t1.frame_sets(f0, t) == t1.frame_sets(fd, t) for t in range(upto + 1))
            res["prefix_equal"] += int(ok)
            res["prefix_frames"] += upto + 1
            if tf < 0:
                res["untouched"] += 1
                res["verdict_equal"] += int((f0.count(H) > 0) == (fd.count(H) > 0))
        if si % 40 == 0:
            print(f"{si:3d} exits {res['exits']} untouched {res['untouched']} prefix_equal {res['prefix_equal']} "
                  f"{time.perf_counter() - t0:.0f} s", flush=True)
    summ = {"situations": len(sits), "exits": res["exits"], "untouched_by_danger": res["untouched"],
            "untouched_verdict_equal": res["verdict_equal"], "prefix_equal": res["prefix_equal"],
            "touch_frame": _q([t for t in res["touch"] if t >= 0], (0, 10, 50, 90, 100)),
            "ms_flat_per_state": _q(res["ms_flat"]), "ms_touch_per_branch": _q(res["ms_touch"]),
            "ms_chain_per_branch": _q(res["ms_chain"]), "wall_s": round(time.perf_counter() - t0, 1)}
    print(json.dumps(summ), flush=True)
    Path(args.out).write_text(json.dumps(summ, default=float))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["exact", "bundle", "sits", "shapes", "flat"])
    ap.add_argument("out")
    ap.add_argument("--lib", default="")
    ap.add_argument("--T", type=int, default=30)
    ap.add_argument("--n", type=int, default=0)
    ap.add_argument("--floor", action="store_true")
    ap.add_argument("--canon", action="store_true")
    ap.add_argument("--maxev", type=int, default=2)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--no-claw", action="store_true")
    ap.add_argument("--terrain", default="floor", choices=list(tb.TERRAINS))
    ap.add_argument("--reload", type=int, default=0)
    ap.add_argument("--danger", action="store_true")
    ap.add_argument("--passes", default="", help="sits: the passes (events:frames, ...; default the search's)")
    ap.add_argument("--no-exits", action="store_true")
    ap.add_argument("--check", type=int, default=0, help="shapes: the judge check on this many (cluster, window)s")
    args = ap.parse_args(argv)
    return {"exact": exact_cmd, "bundle": bundle_cmd, "sits": sits_cmd, "shapes": shapes_cmd, "flat": flat_cmd}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
