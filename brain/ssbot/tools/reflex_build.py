"""Map v2 reflex stage 2: THE ONE-CLAPPER WINDOW TABLES BUILT, the replay check (HANDOFF 'Task reflex'; ssbot.map2.reflex,
ssbot.map2.reflex_gen). Offline only: the bot does not import this or ssbot.map2.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.reflex_build frames [--sets fit,old,rx,held] [--jobs 8]
        # every game frame of the recorded traces: her kin state (the estimator, causal) and every Clapper as the
        # recording shows it -> per window type the table cells she visited (frames_<set>.pkl), the flight templates
        # (a jumping Clapper's y / vy per frame of its flight), the frames a cell could not be keyed (her class)
    ../scripts/uv.cmd run python -m ssbot.tools.reflex_build domain [--build-sets fit,old,rx]
        # the build domain: per window type the visited cells and their neighbours (domain.pkl)
    ../scripts/uv.cmd run python -m ssbot.tools.reflex_build build [--jobs 8] [--types ...]
        # the batched generator over the domain (reflex_gen) -> knowledge clapper_windows_v1.npz
    ../scripts/uv.cmd run python -m ssbot.tools.reflex_build bitcheck [--n 40]
        # the batched generator against the brute-force judge (every macro of the grid, every sample point) on
        # random cells: the same verdict and the same macro
    ../scripts/uv.cmd run python -m ssbot.tools.reflex_build replay [--sets held] [--jobs 8]
        # Reflex.check over the recorded episodes frame by frame as the bot saw them -> replay_*.pkl
    ../scripts/uv.cmd run python -m ssbot.tools.reflex_build report    # -> stage2.txt numbers

Frames: game frames (a hit-stop freeze is not a frame; M2's Episode); her state is the estimator's at the last
recorded STATE frame of each game frame (what the bot's tick sees).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from ssbot.map2 import clapper as cm

OUT = Path(r"C:\ssbot\data\m2_play\reflex")
S2 = OUT / "s2"
M2CACHE = Path(r"C:\ssbot\data\m2_play\map2\m2\cache")
SETS = ("fit", "old", "rx", "held")


def _set_dir(s: str) -> Path:
    return (OUT / "cache" / s) if s == "rx" else (M2CACHE / s)


def etiquette() -> int:
    from ssbot.tools import reflex_val as rv
    return rv.etiquette()


def stop_requested() -> bool:
    return (OUT / "STOP").exists()


# ---- one trace frame by frame ------------------------------------------------------------------------------------------

class TraceFrames:
    """A cached trace (M2's extract_episode) in game frames with her kin state at every one (the estimator over the
    recording's STATE stream, causal: the bot's information) and the Clappers as cm.Obs (the light fields: state, its
    frame, x / y, velocity, facing, hp, charge; the full Obs - memory, seeds - via obs_full)."""

    def __init__(self, path: str):
        from ssbot.knowledge import kinematics as km
        from ssbot.record.recorder import RecordingReader
        from ssbot.tools import m2_validate as mv
        from ssbot.tools import reflex_val as rv
        with open(path, "rb") as fh:
            tr = pickle.load(fh)
        self.tr = tr
        self.meta = tr["meta"]
        self.rec = rv._recording(tr["meta"])
        if self.rec is None or not Path(self.rec).exists():
            raise FileNotFoundError(f"no recording for {self.meta['id']}")
        self.E = E = mv.Episode(tr)
        F = tr["F"]
        rr = RecordingReader(self.rec)
        params = rv._params()
        states = [s for s in rr.states(int(F[0]) - 120, int(F[-1]), keys=rv.KIN_KEYS)]
        fidx = {int(s["f"]): i for i, s in enumerate(states)}
        trk = km.Trace.from_states(states, params, mask_source="act")
        rows = np.array([fidx.get(int(F[E.g2i[g]]), -1) for g in range(E.n_g)], np.int64)
        ok = rows >= 0
        self.S = np.full((km.K, E.n_g), np.nan)
        if ok.any():
            self.S[:, ok] = km.estimate_state(trk, rows[ok], params, terrain=rv._terrain(rr, self.rec, params))
        self.ok = ok
        self.f = np.array([int(F[E.g2i[g]]) for g in range(E.n_g)], np.int64)
        self.act = np.array([int((states[r].get("act") or {}).get("mask") or 0) if r >= 0 else 0 for r in rows],
                            np.int64)
        self.hf = [((states[r].get("act") or {}).get("hf") if r >= 0 else None) for r in rows]   # the hold filter
        # (stage 4) her animation clip and input acceptance (M4's Clawline block / control: _busy_claw, the S1 feed)
        self.clip = [str((((states[r].get("hero") or {}).get("anim") or {}).get("clip")) or "") if r >= 0 else ""
                     for r in rows]
        self.acc = np.array([bool((states[r].get("hero") or {}).get("hero_accepting_input", True)) if r >= 0 else True
                             for r in rows], bool)
        self._ent = {}
        self._charged = {}
        for iid in E.iids:
            ent = np.full(E.n_g, -1, np.int64)
            chg = np.zeros(E.n_g, bool)
            L = E.trans[iid]
            n = 0
            cur_ent, cur_st, charged = None, None, False
            for g in range(E.n_g):
                while n < len(L) and L[n][0] <= g:
                    gg, a, b, f = L[n]
                    if b not in cm.INSTANT:
                        cur_ent, cur_st = gg, b
                    if b in ("Cast Slam Antic", "Cast Slam Antic 2"):
                        charged = True
                    elif b == "Jump Antic":
                        charged = False
                    n += 1
                ent[g] = cur_ent if cur_ent is not None else -1
                chg[g] = charged
            self._ent[iid] = ent
            self._charged[iid] = chg

    def obs_light(self, iid, g: int) -> cm.Obs | None:
        E = self.E
        c = E.cl[iid]
        i = E.g2i[g]
        st = c["st"][i]
        if st is None or c["hp"][i] <= 0 or c["dead"][i] or st in cm.DEAD or st in cm.INTRO:
            return None
        e = self._ent[iid][g]
        j = (g - e) if (e >= 0 and st == E.st(iid, e)) else int(round(float(c["t"][i]) * 60))
        return cm.Obs(iid, st, float(c["t"][i]), float(c["pos"][i, 0]), float(c["pos"][i, 1]), float(c["vel"][i, 0]),
                      float(c["vel"][i, 1]), int(c["face"][i]), int(c["hp"][i]), c["clip"][i],
                      charged=bool(self._charged[iid][g]), j=int(j))


# ---- frames: the visited cells -------------------------------------------------------------------------------------------

def _frames_job(path: str) -> dict:
    from ssbot.knowledge import kinematics as km
    from ssbot.map2 import reflex as rx
    out = {"path": path, "cells": defaultdict(Counter), "na": Counter(), "anchor": Counter(), "tmpl": defaultdict(list),
           "n_g": 0, "err": None, "unit": None, "arm": None, "id": None}
    try:
        T = TraceFrames(path)
    except Exception as ex:
        import traceback
        out["err"] = traceback.format_exc()[-600:]
        return out
    E = T.E
    out.update(n_g=int(E.n_g), unit=T.tr.get("unit") or T.meta.get("unit"), arm=T.meta.get("arm"), id=T.meta["id"],
               manifest=T.meta.get("manifest"))
    for g in range(1, E.n_g):
        if not T.ok[g]:
            continue
        S = T.S[:, g]
        hc = None
        for iid in E.iids:
            o = T.obs_light(iid, g)
            if o is None:
                continue
            if o.st in rx.JUMPING and o.j is not None and o.j <= 90:
                out["tmpl"][(o.st, int(o.j))].append((o.y, o.vy, o.vx * o.face))
            wts = rx.windows_for(o.st, int(o.j))
            if not wts:
                continue
            if hc is None:
                hc = rx.her_class(S)
            for wt in wts:
                out["anchor"][wt.name] += 1
                if hc is None:
                    out["na"][(wt.name, "mode:" + km.MODE_NAMES[int(S[km.MODE])])] += 1
                    continue
                if hc[0] not in wt.classes:
                    out["na"][(wt.name, "cls:" + hc[0])] += 1
                    continue
                key = rx.cell_of(S, o, wt)
                out["cells"][wt.name][rx.pack_key(key)] += 1
    out["cells"] = {k: dict(v) for k, v in out["cells"].items()}
    out["tmpl"] = dict(out["tmpl"])
    return out


def cmd_frames(a) -> int:
    cap = etiquette()
    S2.mkdir(parents=True, exist_ok=True)
    from multiprocessing import Pool
    for s in a.sets.split(","):
        paths = [str(p) for p in sorted(_set_dir(s).glob("*.pkl"))]
        if a.limit:
            paths = paths[:a.limit]
        t0 = time.time()
        res = []
        with Pool(min(a.jobs, cap), initializer=etiquette, maxtasksperchild=20) as pool:
            for k, r in enumerate(pool.imap_unordered(_frames_job, paths)):
                res.append(r)
                if r["err"]:
                    print("error", r["path"], r["err"][-300:], flush=True)
                if k % 100 == 0:
                    print(f"{s} {k + 1}/{len(paths)} {time.time() - t0:.0f}s", flush=True)
                if stop_requested():
                    print("STOP: frames cut", flush=True)
                    break
        with open(S2 / f"frames_{s}.pkl", "wb") as fh:
            pickle.dump(res, fh, protocol=pickle.HIGHEST_PROTOCOL)
        cells = Counter()
        for r in res:
            for wt, d in (r["cells"] or {}).items():
                cells[wt] += len(d)
        print(f"{s}: {len(res)} traces {sum(r['n_g'] for r in res)} game frames in {time.time() - t0:.0f}s; "
              f"(trace-level) cells {dict(cells)}", flush=True)
        if stop_requested():
            return 0
    return 0


# ---- the build domain and the templates --------------------------------------------------------------------------------

def target_top(K, st: str, j: int) -> float:
    """The body's top above the floor (a standing Clapper in state st at frame j: the fit's box)."""
    b = K.box(st, j)
    return float(cm.STAND_Y + b[3] - cm.FLOOR)


def template_obs(st: str, j: int, flight: dict | None = None) -> cm.Obs:
    """The table's Clapper sample in state st at frame j (facing +1, relocated per cell): hp 230, a fresh memory, its
    velocity of that state (an evade backward 15 u/s; a flight's y / vy from the recordings' median per frame - its vx
    is the key's), a jump cast charged."""
    from ssbot.map2 import reflex as rx
    vx, vy, y = 0.0, 0.0, cm.STAND_Y
    if st == "Evade Scuttle":
        vx = -cm.EVADE_SPEED
    if st in rx.JUMPING and flight:
        y, vy = flight.get((st, int(j)), (cm.STAND_Y, 0.0))
    return cm.Obs(1, st, j / 60.0, 0.0, float(y), float(vx), float(vy), 1, 230, None, will_evade=None,
                  turn_age=10 ** 6, charged=st in ("Cast Slam Antic", "Cast Slam Antic 2"), j=int(j))


HOLD_BINS = (-1, 18)               # a Clawline window from the air: her hold height bins (BB_Q) -0.5 .. 9 u
VY_BINS = (-13, 8)                 # a down slash window from the air: vy bins (VY_Q) -31.2 .. 21.6 u/s


def dense_groups(wt_name: str, cls: str, K) -> list:
    """[(group key, [CellKey])] of the dense domain of one window type and her class: every anchor frame x wall band x
    dx bin over DX_RANGE x (A) the hold bins x vy classes (a Clawline window) / the box bottom within -2 .. +6 u of
    the target's top x the vy bins (a down slash window). The flight anchors (Jump / Air: their vx / charge keys) are
    not enumerated densely."""
    from ssbot.map2 import reflex as rx
    wt = rx.WINDOWS[wt_name]
    out = []
    lo_dx, hi_dx = rx.DX_RANGE[wt_name]
    for (st, j0, j1) in wt.anchor:
        if st in rx.JUMPING:
            continue
        for j in range(j0, j1 + 1):
            for band in range(len(rx.WALL_BANDS) - 1):
                cells = []
                if cls == "G":
                    for dxq in range(int(math.floor(lo_dx / rx.DX_Q)), int(math.ceil(hi_dx / rx.DX_Q))):
                        cells.append(rx.CellKey(wt_name, st, j, band, dxq, "G"))
                elif cls == "A" and wt.family == "cl":
                    # the hold heights a hook can reach: the ray meets the body (hold <= its top - 0.5 u) and, on a
                    # static target, the judge's domain (her box bottom >= 2.5 u below its top: HOOK_HOLD_MAX) -
                    # 0.5 u of slack for the press frame's own motion
                    top = target_top(K, st, j)
                    static = st not in rx.MOVING and wt.strike == "down"     # (the judge's domain rule: a continuation)
                    h_max = top + (rx.HOOK_HOLD_MAX if static else -0.5) + 0.5
                    b_hi = min(HOLD_BINS[1], int(math.floor(h_max / rx.BB_Q)) + 1)
                    for dxq in range(int(math.floor(lo_dx / rx.DXA_Q)), int(math.ceil(hi_dx / rx.DXA_Q))):
                        for bbq in range(HOLD_BINS[0], b_hi):
                            for sub in range(len(rx.CL_VY_SAMPLE)):
                                cells.append(rx.CellKey(wt_name, st, j, band, dxq, "A", bbq, sub, adash=1))
                elif cls == "A":
                    top = target_top(K, st, j)
                    b0 = int(math.floor((top - 2.0) / rx.BB_Q))
                    b1 = int(math.ceil((top + 6.0) / rx.BB_Q))
                    for dxq in range(int(math.floor(lo_dx / rx.DXA_Q)), int(math.ceil(hi_dx / rx.DXA_Q))):
                        for bbq in range(max(b0, 0), b1):
                            for sub in range(VY_BINS[0], VY_BINS[1] + 1):
                                cells.append(rx.CellKey(wt_name, st, j, band, dxq, "A", bbq, sub, adash=1))
                if cells:
                    out.append(((wt_name, cls, st, j, band), cells))
    return out


FRAMES_RES = {"dx": 0.25, "bb": 0.25, "vy": 1.2, "fph": 4}     # the resolution frames_*.pkl were keyed at (stage 1's)


def visited_groups(wt_name: str, cls: str, nbr: int = 1, sets: tuple = SETS, unpack=None) -> list:
    """[(group key, [CellKey])] of the VISITED domain: the cells her recorded states fell in (frames_*.pkl, re-binned to
    the table's resolution) and their neighbours (+-nbr bins in dx and each continuous key of her class) - for the
    classes / anchors whose dense domain is out of reach (the umbrella's float, the flights). unpack: the frames' key
    decoder (default reflex.unpack_key)."""
    from ssbot.map2 import reflex as rx
    unpack = unpack or rx.unpack_key
    wt = rx.WINDOWS[wt_name]
    q = rx.dx_q(cls)
    keys = set()
    for s in sets:
        p = S2 / f"frames_{s}.pkl"
        if not p.exists():
            continue
        with open(p, "rb") as fh:
            for r in pickle.load(fh):
                for pk in (r.get("cells") or {}).get(wt_name, {}):
                    k = unpack(int(pk))
                    if k.cls != cls:
                        continue
                    dxq = int(math.floor((k.dxq + 0.5) * FRAMES_RES["dx"] / q))
                    if cls == "G":
                        keys.add((k.st, k.j, k.band, dxq, 0, 0, 0, 0, k.cvx, k.chg))
                        continue
                    bbq = int(math.floor((k.bbq + 0.5) * FRAMES_RES["bb"] / rx.BB_Q))
                    if cls == "A" and wt.family == "cl":
                        sub = k.sub
                    elif cls == "A":
                        sub = int(math.floor((k.sub + 0.5) * FRAMES_RES["vy"] / rx.VY_Q))
                    else:
                        sub = int((k.sub * FRAMES_RES["fph"] + 1) // rx.FPH_Q)
                    keys.add((k.st, k.j, k.band, dxq, bbq, sub, k.vxc, k.adash, k.cvx, k.chg))
    cells = set()
    rng = range(-nbr, nbr + 1)
    for (st, j, band, dxq, bbq, sub, vxc, ad, cvx, chg) in keys:
        for a in rng:
            if cls == "G":
                cells.add((st, j, band, dxq + a, 0, 0, 0, 0, cvx, chg))
                continue
            for b in rng:
                for c in (rng if not (cls == "A" and wt.family == "cl") else (0,)):
                    s2 = sub + c
                    if cls == "A" and wt.family == "cl" and not 0 <= s2 < len(rx.CL_VY_SAMPLE):
                        continue
                    if cls == "F" and s2 < 0:
                        continue
                    cells.add((st, j, band, dxq + a, bbq + b, s2, vxc, 1, cvx, chg))
    groups = defaultdict(list)
    for (st, j, band, dxq, bbq, sub, vxc, ad, cvx, chg) in cells:
        if bbq < -2:
            continue
        groups[(wt_name, cls, st, j, band, cvx, chg)].append(
            rx.CellKey(wt_name, st, j, band, dxq, cls, bbq, sub, vxc, ad, cvx, chg))
    return sorted(groups.items())


# ---- build ---------------------------------------------------------------------------------------------------------------

_G = {}
MODES = {"ds": "ref", "cl": "exact"}


def _paused() -> bool:
    return (Path(r"C:\ssbot\sandbox") / "DEMO_SOON.paused").exists()


def _build_init():
    etiquette()
    from ssbot.map2 import reflex as rx, reflex_gen as rg, search as ms
    W = ms.World()
    _G["W"] = W
    _G["gen"] = rg.Gen(W, rx.judge_evaluator(W))


def _build_job(args) -> dict:
    gkey, cells, mode, flight = args[:4]
    try:
        import psutil
        p = psutil.Process()
        p.cpu_affinity(list(range(16, 32)) if _paused() else list(range(psutil.cpu_count())))
    except Exception:
        pass
    from ssbot.map2 import reflex as rx
    G = _G["gen"]
    if len(args) > 4 and args[4]:
        G.max_try = int(args[4])
    G.cl_partial = bool(args[5]) if len(args) > 5 else False   # (stage 4) a Clawline window's partial cells kept
    s0, m0 = Counter(G.stats), Counter(G.ms)
    t0 = time.time()
    try:
        tmpl = template_obs(gkey[2], gkey[3], flight)
        out = G.build_group(cells, tmpl, mode=mode)
        err = None
    except Exception:
        import traceback
        out, err = {}, traceback.format_exc()[-1500:]
    res = {}
    for k, v in out.items():
        if v is None:
            continue
        e, n_pass, n_nodes = v
        res[rx.pack_key(k)] = rx.Table._encode(rx.Entry(e.macro, e.k_strike, e.end, (n_pass, n_nodes)))
    st = Counter(G.stats)
    st.subtract(s0)
    ms_ = Counter(G.ms)
    ms_.subtract(m0)
    return {"gkey": gkey, "n": len(cells), "res": res, "stats": dict(st), "ms": dict(ms_), "s": time.time() - t0,
            "err": err}


def _flight_templates() -> dict:
    """(state, frame) -> (y, vy): the recordings' median of a jumping Clapper (frames_*.pkl)."""
    acc = defaultdict(list)
    for s in SETS:
        p = S2 / f"frames_{s}.pkl"
        if not p.exists():
            continue
        with open(p, "rb") as fh:
            for r in pickle.load(fh):
                for k, v in (r.get("tmpl") or {}).items():
                    acc[k] += v
    return {k: (float(np.median([a[0] for a in v])), float(np.median([a[1] for a in v]))) for k, v in acc.items()
            if len(v) >= 3}


def read_build(path: Path) -> list:
    out = []
    if path.exists():
        with open(path, "rb") as fh:
            while True:
                try:
                    out.append(pickle.load(fh))
                except EOFError:
                    break
    return out


def cmd_build(a) -> int:
    cap0 = etiquette()
    from ssbot.map2 import reflex as rx
    K = cm.Know.load()
    out_dir = S2 / (a.out_dir or "build")
    out_dir.mkdir(parents=True, exist_ok=True)
    flight = _flight_templates() if a.flight else {}
    jobs = []
    for spec in a.types.split(","):
        wt_name, cls = spec.split(":")
        fam = rx.WINDOWS[wt_name].family
        mode = a.mode or ("exact" if cls == "G" else MODES[fam])
        path = out_dir / (f"{wt_name}_{cls}.pkl" if a.domain == "dense" else f"{wt_name}_{cls}_visited.pkl")
        done = {tuple(r["gkey"]) for r in read_build(path) if not r.get("err")}
        groups = dense_groups(wt_name, cls, K) if a.domain == "dense" else visited_groups(wt_name, cls, a.nbr)
        if a.j:
            jlo, jhi = (int(x) for x in a.j.split("-"))
            groups = [g for g in groups if jlo <= g[0][3] <= jhi]
        todo = [(g, c, mode, flight, a.max_try, a.cl_partial) for (g, c) in groups if tuple(g) not in done]
        print(f"{wt_name}:{cls} mode {mode}: {len(groups)} groups, {sum(len(c) for _, c in groups)} cells; "
              f"done {len(done)}, to do {len(todo)}", flush=True)
        jobs += [(path, j) for j in todo]
    if a.order == "interleave":
        jobs.sort(key=lambda pj: (pj[1][0][3], pj[1][0][4]))
    from multiprocessing import Pool
    t0 = time.time()
    n_done = 0
    tot = Counter()
    with Pool(a.jobs, initializer=_build_init, maxtasksperchild=a.maxtasks) as pool:
        pending = []
        it = iter(jobs)
        exhausted = False
        while True:
            cap = 2 if _paused() else min(a.jobs, cap0)
            while not exhausted and len(pending) < cap and not stop_requested():
                try:
                    path, job = next(it)
                except StopIteration:
                    exhausted = True
                    break
                pending.append((path, pool.apply_async(_build_job, (job,))))
            if not pending:
                break
            still = []
            for path, ar in pending:
                if ar.ready():
                    r = ar.get()
                    with open(path, "ab") as fh:
                        pickle.dump(r, fh, protocol=pickle.HIGHEST_PROTOCOL)
                    n_done += 1
                    tot.update({k: v for k, v in r["stats"].items() if isinstance(v, (int, float))})
                    if r["err"]:
                        print("error", r["gkey"], r["err"][-600:], flush=True)
                    if n_done % a.every == 0 or n_done == len(jobs):
                        el = time.time() - t0
                        print(f"{n_done}/{len(jobs)} {el:.0f}s ({el / n_done:.1f} s/job) last {r['gkey']} "
                              f"{r['s']:.1f}s windows {len(r['res'])}/{r['n']} | full {tot['cells_full']} "
                              f"partial {tot['cells_partial']} cells {tot['cells']}", flush=True)
                else:
                    still.append((path, ar))
            pending = still
            if stop_requested() and not pending:
                print("STOP: the build cut (the groups done are saved)", flush=True)
                break
            time.sleep(0.2)
    print(f"build done: {n_done} jobs in {time.time() - t0:.0f}s; {dict(tot)}", flush=True)
    return 0


# ---- pack: the knowledge file ------------------------------------------------------------------------------------------

def _iter_build(path: Path):
    """The build file's group results one by one (a type's file can hold millions of rows)."""
    with open(path, "rb") as fh:
        while True:
            try:
                yield pickle.load(fh)
            except EOFError:
                return


def cmd_pack(a) -> int:
    """Every built group -> the table file (reflex.Table's npz) with the build's meta (rows packed per group into
    arrays: millions of cells)."""
    import subprocess
    from ssbot.map2 import reflex as rx
    K_, M_, C_, S_, E_, F_ = [], [], [], [], [], []
    meta_types = {}
    for path in sorted((S2 / "build").glob("*.pkl")):
        st = Counter()
        n_cells = n_groups = n_err = 0
        s_cpu = 0.0
        for r in _iter_build(path):
            if r.get("err"):
                n_err += 1
                continue
            n_groups += 1
            n_cells += r["n"]
            s_cpu += r["s"]
            st.update({k: v for k, v in r["stats"].items() if isinstance(v, (int, float))})
            if not r["res"]:
                continue
            pks = np.fromiter((int(k) for k in r["res"]), np.int64, len(r["res"]))
            enc = list(r["res"].values())
            K_.append(pks)
            M_.append(np.array([e[0] for e in enc], np.int16).reshape(-1, 8))
            C_.append(np.array([e[1] for e in enc], np.int16).reshape(-1, 4, 3))
            S_.append(np.array([e[2] for e in enc], np.int16).reshape(-1, 2))
            E_.append(np.array([e[3] for e in enc], np.float16).reshape(-1, 4))
            F_.append(np.array([e[4] for e in enc], np.int16).reshape(-1, 2))
        meta_types[path.stem] = {"groups": n_groups, "errors": n_err, "cells": n_cells,
                                 "full": st["cells_full"], "partial": st["cells_partial"], "cpu_s": round(s_cpu),
                                 "nodes": st["nodes"], "lanes": st["lanes"], "refevals": st["refevals"],
                                 "judged": st["judged"] + st["judged_cl"] + st["judged_unify"] + st["cl_judged"]}
    keys = np.concatenate(K_) if K_ else np.zeros(0, np.int64)
    order = np.argsort(keys, kind="stable")
    n = len(keys)
    rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    meta = {"version": rx.VERSION, "built": time.strftime("%Y-%m-%d %H:%M"), "code_rev": rev,
            "resolution": {"dx_ground": rx.DX_Q, "dx_air": rx.DXA_Q, "bb": rx.BB_Q, "vy": rx.VY_Q,
                           "float_frames": rx.FPH_Q, "cl_vy_edges": list(rx.CL_VY_EDGES), "bands": list(rx.WALL_BANDS),
                           "cvx": rx.CVX_Q},
            "modes": {"G": "exact", "cl": "exact", "ds_air": "ref (probe exits)"}, "types": meta_types,
            "templates": "hp 230, a fresh Memory, one Clapper (no buddy), facing +1 relocated per wall band"}
    out = Path(a.out) if a.out else rx.TABLE_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    cat = (lambda L, shp, dt: np.concatenate(L)[order] if L else np.zeros(shp, dt))
    np.savez_compressed(
        out, keys=keys[order], macro=cat(M_, (0, 8), np.int16), cont=cat(C_, (0, 4, 3), np.int16),
        k_strike=cat(S_, (0, 2), np.int16), end=cat(E_, (0, 4), np.float16), conf=cat(F_, (0, 2), np.int16),
        meta=np.array(json.dumps(meta)))
    print(f"{n} window cells -> {out} ({out.stat().st_size / 1e6:.1f} MB)")
    for k, v in meta_types.items():
        print(f"  {k:24s} {v}")
    return 0


# ---- fix (stage 4): the table patched for the review's generator findings -----------------------------------------------

def _unpack_v1(pk: int):
    """Stage 2's unpack_key (bbq not sign-extended: -1 came back as 127): the visited domain stage 2 built."""
    from dataclasses import replace as _rep
    from ssbot.map2 import reflex as rx
    k = rx.unpack_key(pk)
    return _rep(k, bbq=k.bbq + 128) if k.bbq < 0 else k


def _fix_plan(T) -> tuple:
    """(cells to rebuild by group key, keys to drop, counts): (a) the float's 'release + attack on frame 1' entries (the
    Deflate eats that attack: reflex.swings) re-judged with the fixed generator; (b) the visited domain under the
    sign-extended unpack_key: its new cells built, the cells only the old unpack made (a hold of ~31 u) dropped."""
    from ssbot.map2 import reflex as rx
    todo = defaultdict(set)
    drop = set()
    cnt = Counter()
    for pk in T.keys():
        k = rx.unpack_key(pk)
        e = T._entry(pk)
        m = e.macro
        if k.cls == "F" and m.family == "ds" and not m.jh and m.t <= 1:
            todo[(k.wt, k.cls, k.st, k.j, k.band, k.cvx, k.chg)].add(k)
            drop.add(pk)
            cnt[("phantom", k.wt)] += 1
    for path in sorted((S2 / "build").glob("*_visited.pkl")):
        wt_name, cls = path.stem.split("_visited")[0].rsplit("_", 1)
        old = {c for (_, cs) in visited_groups(wt_name, cls, unpack=_unpack_v1) for c in cs}
        new = {c for (_, cs) in visited_groups(wt_name, cls) for c in cs}
        for c in old - new:
            pk = rx.pack_key(c)
            if T.get(c) is not None:
                drop.add(pk)
                cnt[("bbq_drop", wt_name, cls)] += 1
            cnt[("bbq_old_only", wt_name, cls)] += 1
        for c in new - old:
            todo[(c.wt, c.cls, c.st, c.j, c.band, c.cvx, c.chg)].add(c)
            cnt[("bbq_new", wt_name, cls)] += 1
    return {g: sorted(cs, key=rx.pack_key) for g, cs in todo.items()}, drop, cnt


def cmd_fix(a) -> int:
    """Re-judge the cells the review's generator findings touch (_fix_plan) with the fixed generator, patch the table
    (rows of the dropped keys removed, the rebuilt windows added) -> the v2 knowledge file (reflex.TABLE_PATH) and a copy
    in s2\\."""
    cap0 = etiquette()
    from ssbot.map2 import reflex as rx
    src = Path(a.src) if a.src else S2 / "clapper_windows_v1.npz"
    z = np.load(src)
    meta = json.loads(str(z["meta"]))
    arr = {n: np.asarray(z[n]) for n in ("keys", "macro", "cont", "k_strike", "end", "conf")}
    T = rx.Table()
    T._arr = (arr["keys"], arr["macro"], arr["cont"], arr["k_strike"], arr["end"], arr["conf"])
    todo, drop, cnt = _fix_plan(T) if not a.no_plan else ({}, set(), Counter())
    repl = [S2 / x for x in a.replace.split(",") if x]
    for bp in repl:
        wt_name, cls = bp.stem.split("_visited")[0].rsplit("_", 1)
        for pk in T.keys():
            k = rx.unpack_key(pk)
            if k.wt == wt_name and k.cls == cls:
                drop.add(pk)
                cnt[("replaced", wt_name, cls)] += 1
    print(f"fix: {sum(len(c) for c in todo.values())} cells in {len(todo)} groups to (re)build, {len(drop)} rows "
          f"dropped; {dict(cnt)}", flush=True)
    out_b = S2 / "build_fix" / "fix.pkl"
    out_b.parent.mkdir(parents=True, exist_ok=True)
    done = {tuple(r["gkey"]) for r in read_build(out_b) if not r.get("err")}
    flight = _flight_templates()
    jobs = []
    for g, cells in sorted(todo.items()):
        if g in done:
            continue
        wt = rx.WINDOWS[g[0]]
        mode = "exact" if g[1] == "G" else MODES[wt.family]
        jobs.append(((g[0], g[1], g[2], g[3], g[4], g[5], g[6]), cells, mode, flight, a.max_try))
    from multiprocessing import Pool
    t0 = time.time()
    n_done = 0
    with Pool(min(a.jobs, cap0), initializer=_build_init, maxtasksperchild=40) as pool:
        pending = []
        it = iter(jobs)
        exhausted = False
        while True:
            cap = 2 if _paused() else min(a.jobs, cap0)
            while not exhausted and len(pending) < cap and not stop_requested():
                try:
                    job = next(it)
                except StopIteration:
                    exhausted = True
                    break
                pending.append(pool.apply_async(_build_job, (job,)))
            if not pending:
                break
            still = []
            for ar in pending:
                if ar.ready():
                    r = ar.get()
                    with open(out_b, "ab") as fh:
                        pickle.dump(r, fh, protocol=pickle.HIGHEST_PROTOCOL)
                    n_done += 1
                    if r["err"]:
                        print("error", r["gkey"], r["err"][-600:], flush=True)
                    if n_done % 50 == 0 or n_done == len(jobs):
                        print(f"{n_done}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
                else:
                    still.append(ar)
            pending = still
            if stop_requested() and not pending:
                print("STOP: the fix cut (the groups done are saved)", flush=True)
                return 0
            time.sleep(0.2)
    # the patch
    keep = ~np.isin(arr["keys"], np.fromiter(drop, np.int64, len(drop)))
    K_, M_, C_, S_, E_, F_ = ([arr["keys"][keep]], [arr["macro"][keep]], [arr["cont"][keep]], [arr["k_strike"][keep]],
                              [arr["end"][keep]], [arr["conf"][keep]])
    st = Counter()
    for r in [x for bp in ([] if a.no_plan else [out_b]) + repl for x in _iter_build(bp)]:
        if r.get("err") or not r["res"]:
            continue
        st.update({k: v for k, v in r["stats"].items() if isinstance(v, (int, float))})
        pks = np.fromiter((int(k) for k in r["res"]), np.int64, len(r["res"]))
        enc = list(r["res"].values())
        K_.append(pks)
        M_.append(np.array([e[0] for e in enc], np.int16).reshape(-1, 8))
        C_.append(np.array([e[1] for e in enc], np.int16).reshape(-1, 4, 3))
        S_.append(np.array([e[2] for e in enc], np.int16).reshape(-1, 2))
        E_.append(np.array([e[3] for e in enc], np.float16).reshape(-1, 4))
        F_.append(np.array([e[4] for e in enc], np.int16).reshape(-1, 2))
    keys = np.concatenate(K_)
    order = np.argsort(keys, kind="stable")
    keys = keys[order]
    dup = np.flatnonzero(np.diff(keys) == 0)
    if len(dup):
        # a rebuilt key also kept (should not happen: every rebuilt cell's old row was dropped or absent): the rebuilt
        # row wins (it comes later in the stable order)
        keep2 = np.ones(len(keys), bool)
        keep2[dup] = False
        keys = keys[keep2]
        order = order[keep2]
    cat = (lambda L: np.concatenate(L)[order])
    meta2 = dict(meta)
    meta2.update(version=rx.VERSION, built=time.strftime("%Y-%m-%d %H:%M"), patched_from=str(src.name),
                 patch={"dropped": int(len(drop)), "rebuilt_cells": int(sum(len(c) for c in todo.values())),
                        "replaced_by": [str(x.relative_to(S2)) for x in repl],
                        "rebuilt_windows": int(sum(len(K) for K in K_[1:])), "counts": {str(k): v for k, v in cnt.items()},
                        "stats": dict(st),
                        "why": "stage 4: the float's release + attack on frame 1 (no slash: reflex.swings), the visited "
                               "domain under the sign-extended unpack_key; the generator with the swing screen and the "
                               "Clappers' physics steps anchored (reflex.clapper_steps)"})
    out = Path(a.out) if a.out else rx.TABLE_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, keys=keys, macro=cat(M_), cont=cat(C_), k_strike=cat(S_), end=cat(E_), conf=cat(F_),
                        meta=np.array(json.dumps(meta2)))
    import shutil
    shutil.copy2(out, S2 / out.name)
    print(f"{len(keys)} window cells -> {out} ({out.stat().st_size / 1e6:.1f} MB); patch {meta2['patch']}", flush=True)
    return 0


# ---- bitcheck: the generator against the judge ---------------------------------------------------------------------------

def _bit_job(args) -> dict:
    """One sampled cell of a built type: (a) the screen's soundness - lanes it pruned at the cell's nodes judged
    exactly (a window there would be a lane the screen lost); (b) 'ref' vs the judge: the entry's macro at the cell's
    nodes, the reference verdict vs the exact judge's; (c) the entry's macro at random interior points of the cell,
    judged exactly (the table's claim inside the cell)."""
    import random
    from ssbot.map2 import reflex as rx, reflex_gen as rg
    W, G = _G["W"], _G["gen"]
    ev = G.ev
    key, entry, seed = args
    from ssbot.knowledge import kinematics as km
    rnd = random.Random(seed)
    wt = rx.WINDOWS[key.wt]
    out = {"key": key, "conf": entry.conf, "pruned": [], "nodes": [], "interior": [], "err": None}
    try:
        o_t = template_obs(key.st, key.j)
        sm = rx.cell_samples(W, key, o_t, eps=0.0)
        if wt.family == "ds":
            ref = rg.Ref(W, sm[0][1][0], wt, alpha=float(sm[0][0][km.ALPHA]))
            for (S, obs) in sm[:4]:
                o = obs[0]
                if abs(o.x - ref.o.x) > 1e-9 or abs(float(S[km.ALPHA]) - ref.alpha) > 1e-9:
                    ref = rg.Ref(W, o, wt, alpha=float(S[km.ALPHA]))
                macros = rg.macro_grid(wt, key.cls, rg.T_MAX)
                ln = rg.screen_ds(W, ref, [S], macros)
                pr = [q for q in range(len(macros)) if not ln.ok[0, q]]
                for q in rnd.sample(pr, min(3, len(pr))):
                    v = rx.judge(W, ev, S, [o], o.iid, wt, macros[q])
                    out["pruned"].append((macros[q].label(), int(ln.why[0, q]), bool(v.window), v.why))
                if key.cls == "G":
                    continue
                v_ex = rx.judge(W, ev, S, [o], o.iid, wt, entry.macro)
                q = next((i for i, m in enumerate(macros) if m == entry.macro), None)
                rv_ = rg.refeval_ds(W, ev, ref, S, entry.macro, ln.c[0, q]) if q is not None and ln.ok[0, q] else None
                out["nodes"].append((bool(v_ex.window), None if rv_ is None else bool(rv_.window), v_ex.why,
                                     None if rv_ is None else rv_.why))
        elif wt.strike == "down":
            # judge_cl_fast (the screen inside the continuation search) against judge_cl: the same verdict and the
            # same continuation per hook variant
            from dataclasses import replace as _rep
            for (S, obs) in sm[:2]:
                o = obs[0]
                ref = rg.Ref(W, o, wt)
                m0 = _rep(entry.macro, cont=())
                v1 = rx.judge_cl(W, ev, S, [o], o.iid, wt, m0)
                v2 = rg.judge_cl_fast(W, ev, S, [o], o.iid, wt, m0, ref)
                out["pruned"].append(("cl", 0, (v1.window, v1.cont) != (v2.window, v2.cont), f"{v1.cont}|{v2.cont}"))
        for _ in range(3):
            S, o = _interior_point(W, key, o_t, rnd)
            if S is None:
                continue
            jf = rx.judge
            v = jf(W, ev, S, [o], o.iid, wt, entry.macro)
            out["interior"].append((bool(v.window), v.why, v.lands, v.safe, v.exit, v.n, float(S[km.ALPHA])))
            S0_ = S.copy()                                  # (stage 4) the same point at the corners' phase
            S0_[km.ALPHA] = S0_[km.ALO] = S0_[km.AHI] = 0.0
            v0 = jf(W, ev, S0_, [o], o.iid, wt, entry.macro)
            out.setdefault("interior0", []).append((bool(v0.window), v0.why))
    except Exception:
        import traceback
        out["err"] = traceback.format_exc()[-800:]
    return out


def _interior_point(W, key, o_t, rnd, phase: bool = True):
    """A random state inside the cell (its continuous bins and its wall band) and the Clapper sample there. phase
    (stage 4): her physics phase (ALPHA) random too - the cells' corners are all at ALPHA 0; the float (F): the float
    state of the cell's vx class with her vx drawn inside the class (the corners hold the key since the open: vx
    exactly 0 or +-8.5)."""
    from dataclasses import replace as _rep
    from ssbot.knowledge import kinematics as km
    from ssbot.map2 import reflex as rx, strike as sk
    lo, hi = rx.WALL_BANDS[key.band], rx.WALL_BANDS[key.band + 1]
    f = rnd.uniform(lo + 0.05, hi - 0.05)
    cx = cm.WALL_R - f
    o = _rep(o_t, x=cx, face=1, cast2=None, rune=None)
    q = rx.dx_q(key.cls)
    dx = (key.dxq + rnd.random()) * q
    hx = cx + dx
    tw = 1 if cx >= hx else -1
    alpha = rnd.random() if phase else 0.0

    def ph(S):
        S[km.ALPHA] = S[km.ALO] = S[km.AHI] = alpha
        return S
    if key.cls == "G":
        return ph(km.initial_state(W.params, hx, sk.FLOOR + sk.FOOT, ground=True, facing=tw)), o
    if key.cls == "A":
        wt = rx.WINDOWS[key.wt]
        if wt.family == "cl":
            lo_v, hi_v = rx.CL_VY_SAMPLE[key.sub]
            vy = rnd.uniform(lo_v, hi_v)
            h = (key.bbq + rnd.random()) * rx.BB_Q
            bb = h - rx._hold_off(vy)
        else:
            vy = (key.sub + rnd.random()) * rx.VY_Q
            bb = (key.bbq + rnd.random()) * rx.BB_Q
        S = km.initial_state(W.params, hx, sk.FLOOR + bb + sk.FOOT, ground=False, vy=vy, facing=tw)
        S[km.AIRDASHED] = float(key.adash)
        return ph(S), o
    if key.cls == "F":
        from ssbot.tools import m3_accept as ma
        fr = key.sub * rx.FPH_Q + rnd.randrange(rx.FPH_Q)
        bb = (key.bbq + rnd.random()) * rx.BB_Q
        S = ma.float_state(W, hx, sk.FLOOR + bb, key=key.vxc, extra=fr, face=tw)
        vlo, vhi = {-1: (-8.5, -1.0), 0: (-0.99, 0.99), 1: (1.0, 8.5)}[int(key.vxc)]
        S[km.VX] = rnd.uniform(vlo, vhi)
        S[km.AIRDASHED] = float(key.adash)
        return ph(S), o
    return None, None


def cmd_bitcheck(a) -> int:
    import random
    from ssbot.map2 import reflex as rx
    cap = etiquette()
    T = rx.Table.load(a.table or None)
    by = defaultdict(list)
    sel = {tuple(x.split(":")) for x in a.types.split(",")} if a.types else None
    skip = {tuple(x.split(":")) for x in a.skip.split(",")} if a.skip else set()
    for pk in T.keys():
        k = rx.unpack_key(pk)
        if (sel is not None and (k.wt, k.cls) not in sel) or (k.wt, k.cls) in skip:
            continue
        by[(k.wt, k.cls)].append(pk)
    rnd = random.Random(7)
    jobs = []
    for (wt, cls), pks in sorted(by.items()):
        for pk in rnd.sample(pks, min(a.n, len(pks))):
            jobs.append((rx.unpack_key(pk), T._entry(pk), rnd.randrange(1 << 30)))
    print(f"{len(jobs)} cells sampled from {len(by)} (type, class) groups", flush=True)
    from multiprocessing import Pool
    res = []
    t0 = time.time()
    with Pool(min(a.jobs, cap), initializer=_build_init, maxtasksperchild=20) as pool:
        for k, r in enumerate(pool.imap_unordered(_bit_job, jobs)):
            res.append(r)
            if r["err"]:
                print("error", r["key"], r["err"][-400:], flush=True)
            if k % 50 == 0:
                print(f"{k + 1}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
            if stop_requested():
                break
    sfx = f"_{a.tag}" if a.tag else ""
    with open(S2 / f"bitcheck{sfx}.pkl", "wb") as fh:
        pickle.dump(res, fh)
    lines = ["BITCHECK (reflex_build bitcheck): per (type, class) - pruned lanes judged exactly (a window = a lane the "
             "screen lost), the entry at the cell's nodes 'ref' vs the judge, the entry at random interior points judged "
             "exactly (full / partial cells; stage 4: her physics phase random, the float's vx inside its class)"]
    agg = defaultdict(Counter)
    for r in res:
        k = r["key"]
        g = agg[(k.wt, k.cls)]
        full = r["conf"][0] == r["conf"][1]
        for (_, why, win, _) in r["pruned"]:
            g["pruned"] += 1
            g["pruned_win"] += win
        for (ex, rf, _, _) in r["nodes"]:
            if rf is None:
                continue
            g["nodes"] += 1
            g["n_ref_ex"] += (rf and ex)
            g["n_ref_notex"] += (rf and not ex)
            g["n_notref_ex"] += ((not rf) and ex)
        for (win, *_r) in r["interior"]:
            g["int_full" if full else "int_part"] += 1
            g["int_full_ok" if full else "int_part_ok"] += win
        for (win, *_r) in r.get("interior0", []):
            g["int0_full" if full else "int0_part"] += 1
            g["int0_full_ok" if full else "int0_part_ok"] += win
    for (wt, cls), g in sorted(agg.items()):
        lines.append(f"  {wt:12s} {cls}  pruned lanes judged {g['pruned']:4d} windows among them {g['pruned_win']:3d} | "
                     f"nodes ref&judge {g['n_ref_ex']:4d} ref-only {g['n_ref_notex']:3d} judge-only {g['n_notref_ex']:3d} | "
                     f"interior full {g['int_full_ok']}/{g['int_full']} partial {g['int_part_ok']}/{g['int_part']} | "
                     f"the same points at ALPHA 0: full {g['int0_full_ok']}/{g['int0_full']} partial "
                     f"{g['int0_part_ok']}/{g['int0_part']}")
    txt = "\n".join(lines)
    (S2 / f"bitcheck{sfx}.txt").write_text(txt, "utf-8")
    print(txt)
    return 0


# ---- replay: Reflex.check over recorded episodes, frame by frame ------------------------------------------------------------

M_CLAW = 1 << 4


def _replay_init(table_path: str, lead: int = 1):
    _build_init()
    from ssbot.map2 import reflex as rx
    _G["table"] = rx.Table.load(table_path or None)
    _G["lead"] = int(lead)


CLAW_BLOCK_F = 36                  # M4 live.CLAW_BLOCK_F: a Clawline pressed this recently may still be in its block
CLAW_LOCK_F = 13                   # M4 press.CLAW_LOCK_F: the next Clawline from control + 13


def _claw_track(T) -> tuple:
    """Per game frame (as the bot's observation frame fo): M4's view of her Clawlines - (P: the last Clawline's press
    frame <= fo, its control (-1: not seen by fo), busy: in its block now (_busy_claw: a Clawline latched in the last
    CLAW_BLOCK_F frames and a Harpoon clip or no input)). Control = M4 S1's feed: the first frame >= P + 3 accepting
    input without a Harpoon clip."""
    n = len(T.act)
    P = np.full(n, -1, np.int64)
    C = np.full(n, -1, np.int64)
    busy = np.zeros(n, bool)
    p_, c_ = -1, -1
    last_claw = -10 ** 9
    for g in range(n):
        m = int(T.act[g])
        if (m & M_CLAW) and not (g and int(T.act[g - 1]) & M_CLAW):
            p_, c_ = g, -1
        elif p_ >= 0 and c_ < 0 and g >= p_ + 3 and T.acc[g] and not T.clip[g].startswith("Harpoon"):
            c_ = g
        if m & M_CLAW:
            last_claw = g
        P[g], C[g] = p_, c_
        busy[g] = (g - last_claw < CLAW_BLOCK_F) and (T.clip[g].startswith("Harpoon") or not T.acc[g])
    return P, C, busy


def _replay_job(path: str) -> dict:
    """One trace replayed tick by tick as the bot sees it with a lead (stage 4; f = each game frame, fo = f + 1 - lead:
    her estimated state at fo, the keys in flight = the latched masks of fo + 1 .. f + 1 with the hold filter's state
    after them (act.hf at f + 1), the latched mask at fo, every Clapper as M2's Episode sees it at fo with its Memory and
    the leftover hazards - a Clapper in its intro kept: the reflex gates it -, the Clawline state as M4 computes it (its
    block, the lock to control + 13)): Reflex.check's verdict and time per tick; for the first frame of each run of
    presses (the same target and window) the press judged exactly (reflex.judge_press: closed loop, every Clapper and
    hazard as recorded at f + 1, her estimated state at f + 1; a Clawline window's continuation as the runtime picks it
    for each outcome's stop)."""
    from ssbot.knowledge import kinematics as km
    from ssbot.map2 import reflex as rx
    from ssbot.tools import m2_validate as mv
    W = _G["W"]
    ev = _G["gen"].ev
    lead = int(_G.get("lead", 1))
    out = {"path": path, "err": None, "ticks": 0, "fires": [], "hits": Counter(), "ms": [], "ms_hit": [],
           "ms_check": [], "refresh": [], "n_g": 0, "id": None, "unit": None, "arm": None, "manifest": None,
           "lead": lead, "claw_viol": 0, "gates": Counter()}
    try:
        T = TraceFrames(path)
    except Exception:
        import traceback
        out["err"] = traceback.format_exc()[-600:]
        return out
    E = T.E
    K = W.K
    out.update(n_g=int(E.n_g), id=T.meta["id"], unit=T.tr.get("unit") or T.meta.get("unit"), arm=T.meta.get("arm"),
               manifest=T.meta.get("manifest"))
    R = rx.Reflex(_G["table"], W=W)
    mem_at = mv._memories(E)
    obs_g, mems_g, obs_j = {}, {}, {}
    for g in range(E.n_g):
        obs, mems, oj = [], {}, []
        for iid in E.iids:
            mm = mem_at(iid, g)
            o = E.obs(iid, g, mm)
            if o is not None and o.st is not None and o.st not in cm.DEAD:
                obs.append(o)
                mems[iid] = mm
                if o.st not in cm.INTRO:
                    oj.append(o)
        obs_g[g], mems_g[g], obs_j[g] = obs, mems, oj
    cP, cC, cbusy = _claw_track(T)
    prev_press = None
    try:
        for g in range(1 + lead, E.n_g - 2):
            fo, f = g - lead + 1, g
            if not (T.ok[fo] and T.ok[f + 1]) or not obs_g[fo]:
                prev_press = None
                continue
            obs, mems = obs_g[fo], mems_g[fo]
            hz = E.ghost_hazards(fo, {o.iid for o in obs_j[fo]}, K)
            inflight = np.asarray(T.act[fo + 1:f + 2], np.int64)
            hold = km.HoldState.from_hf(T.hf[f + 1]) if T.hf[f + 1] else None
            claw_free = not bool(cbusy[fo]) and not (cP[fo] >= 0 and cC[fo] < 0)
            lock = int(cC[fo]) + CLAW_LOCK_F if cC[fo] >= 0 else None
            n_ref = R.stats["refresh"]
            t0 = time.perf_counter()
            p = R.check(T.S[:, fo], inflight, hold, obs, mems, hz, fo=fo, f=f, claw_free=claw_free,
                        lat_s=int(T.act[fo]), claw_lock_until=lock, inflight_latched=True)
            dt = (time.perf_counter() - t0) * 1e3
            out["ticks"] += 1
            out["ms"].append(dt)
            for w_ in R.last.get("why") or ():
                if w_ in ("intro", "in a Clawline", "claw busy", "claw lock", "cl low hp", "solo only"):
                    out["gates"][w_] += 1
            hl = R.last.get("hits") or []
            refreshed = R.stats["refresh"] > n_ref
            out.setdefault("ms_norefresh", []).append(dt - (R.ms["refresh"][-1] if refreshed else 0.0))
            if hl:
                out["ms_hit"].append(dt)
                if refreshed:
                    out["refresh"].append(dt)
                for (wn, iid, full) in hl:
                    out["hits"][(wn, full)] += 1
            if p is None:
                prev_press = None
                continue
            key = (p.iid, p.window)
            first = prev_press != key
            prev_press = key
            rec = {"g": g, "fo": fo, "window": p.window, "iid": p.iid, "macro": p.macro.label(), "conf": p.conf,
                   "k_strike": p.k_strike, "end": p.end, "first": first, "ms": dt, "st": next(
                       (o.st for o in obs if o.iid == p.iid), None), "j": next((o.j for o in obs if o.iid == p.iid), None),
                   "cls": (rx.her_class(T.S[:, fo]) or ("-",))[0], "n_cl": len(obs), "lead": lead,
                   "ref": p.ref_rel() if p.alts else None, "drift": p.drift}
            if p.p_abs is not None and cC[fo] >= 0 and cC[fo] + 1 <= p.p_abs <= cC[fo] + CLAW_LOCK_F - 1:
                out["claw_viol"] += 1                  # a Clawline pressed inside the previous one's lock (lost live)
            if first:
                # the press judged exactly: her state at f + 1 (the estimator's), the Clappers as recorded at f + 1
                S1 = T.S[:, f + 1]
                o1, m1 = obs_j.get(f + 1) or obs_j[fo], mems_g.get(f + 1) or mems
                if any(o.iid == p.iid for o in o1):
                    hz1 = E.ghost_hazards(f + 1, {o.iid for o in o1}, K)
                    wt = rx.WINDOWS[p.window]
                    v = rx.judge_press(W, ev, S1, o1, p.iid, wt, p.macro, mems=m1, hazards=hz1,
                                       ref=p.ref_rel() if p.alts else None,
                                       dlat=0 if (p.drift or not p.alts) else rx.DRIFT_LAT)
                    rec["judge"] = (bool(v.window), v.why, v.lands, v.safe, v.exit, v.n)
            out["fires"].append(rec)
    except Exception:
        import traceback
        out["err"] = traceback.format_exc()[-800:]
    out["ms_check"] = list(R.ms.get("check", []))
    out["stats"] = dict(R.stats)
    return out


REPLAY_SETS = {
    "held": ["held"],                                   # SP14 (w7 / w13: the default jt + rnjb) and the air show b11-16
    "sp13": ["fit:1v1sp13_fp1", "rx:1v1sp13_fp5"],      # the forced CLAWSTRIKE (w7 / w13)
}


def _replay_paths(spec: str) -> list:
    if spec.startswith("@"):
        return [x.strip() for x in Path(spec[1:]).read_text("utf-8").splitlines() if x.strip()]
    out = []
    for item in REPLAY_SETS.get(spec, [spec]):
        s, _, man = item.partition(":")
        for p in sorted(_set_dir(s).glob("*.pkl")):
            if man:
                with open(p, "rb") as fh:
                    if pickle.load(fh)["meta"].get("manifest") != man:
                        continue
            out.append(str(p))
    return out


def cmd_replay(a) -> int:
    cap = etiquette()
    paths = []
    for s in a.sets.split(","):
        paths += _replay_paths(s)
    if a.limit:
        paths = paths[:a.limit]
    print(f"replay: {len(paths)} traces", flush=True)
    from multiprocessing import Pool
    res = []
    t0 = time.time()
    with Pool(min(a.jobs, cap), initializer=_replay_init, initargs=(a.table, a.lead), maxtasksperchild=10) as pool:
        for k, r in enumerate(pool.imap_unordered(_replay_job, paths)):
            res.append(r)
            if r["err"]:
                print("error", r["path"], r["err"][-500:], flush=True)
            if k % 20 == 0:
                print(f"{k + 1}/{len(paths)} {time.time() - t0:.0f}s fires {sum(len(x['fires']) for x in res)}",
                      flush=True)
            if stop_requested():
                print("STOP: the replay cut", flush=True)
                break
    out = S2 / f"replay_{a.tag}.pkl"
    with open(out, "wb") as fh:
        pickle.dump(res, fh, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"{len(res)} traces in {time.time() - t0:.0f}s -> {out}")
    return 0


# ---- report: the replay's numbers ---------------------------------------------------------------------------------------

def _group_of(r: dict) -> str:
    unit = "w13" if "w13" in str(r.get("unit")) else "w7"
    man, arm = str(r.get("manifest")), str(r.get("arm"))
    if "air1" in man:
        kind = "show"
    elif "sp13_fp" in man:
        kind = "clawstrike"
    else:
        kind = "default"
    return f"{unit} {kind}"


def _runs(fires: list) -> list:
    """The fires grouped into runs (consecutive frames, the same target and window): [first fire, last g]."""
    out = []
    for f in fires:
        if out and not f["first"] and out[-1][0]["iid"] == f["iid"] and out[-1][0]["window"] == f["window"] and \
                f["g"] == out[-1][1] + 1:
            out[-1][1] = f["g"]
        else:
            out.append([f, f["g"]])
    return out


def cmd_report(a) -> int:
    from ssbot.tools import m2_validate as mv
    res = pickle.load(open(S2 / f"replay_{a.tag}.pkl", "rb"))
    evs = []
    for nm in ("events_all.pkl",):
        p = OUT / nm
        if p.exists():
            evs += pickle.load(open(p, "rb"))
    ev_by = defaultdict(list)
    for e in evs:
        ev_by[(e["ep"], e["tgt"])].append(e)
    G = defaultdict(lambda: defaultdict(Counter))
    minutes = Counter()
    ticks = defaultdict(list)
    ticks_nr = defaultdict(list)
    tick_hit = defaultdict(list)
    chk = defaultdict(list)
    refr = defaultdict(list)
    open_t = defaultdict(Counter)
    gates = defaultdict(Counter)                                # (stage 4) the gates before the lookup / the Clawline's
    chk_why = defaultdict(Counter)                              # the check's failures by step and reason
    viol = Counter()
    leads = Counter()
    n_tr = Counter()
    for r in res:
        if r["err"] or not r["ticks"]:
            continue
        grp = _group_of(r)
        n_tr[grp] += 1
        gates[grp].update(r.get("gates") or {})
        viol[grp] += int(r.get("claw_viol", 0))
        leads[r.get("lead", 1)] += 1
        for k_, v_ in (r.get("stats") or {}).items():
            if k_.startswith("check_fail_"):
                chk_why[grp][k_[len("check_fail_"):]] += v_
        minutes[grp] += r["n_g"] / 3600.0
        ticks[grp] += r["ms"][1:]                               # (the first tick: the compiled paths' warm-up)
        ticks_nr[grp] += r.get("ms_norefresh", r["ms"])[1:]
        tick_hit[grp] += r["ms_hit"][1:] if r["ms_hit"] else []
        chk[grp] += r["ms_check"]
        refr[grp] += r["refresh"]
        for (wn, full), n in r["hits"].items():
            open_t[grp][(wn, full)] += n
        with open(r["path"], "rb") as fh:
            tr = pickle.load(fh)
        E = mv.Episode(tr)
        for f0, g1 in _runs(r["fires"]):
            wn = f0["window"]
            c = G[grp][wn]
            c["runs"] += 1
            c["full" if f0["conf"][0] == f0["conf"][1] else "partial"] += 1
            jd = f0.get("judge")
            ok = bool(jd and jd[0])
            c["sim_ok"] += ok
            c["sim_n"] += jd is not None
            g0 = f0["g"]
            span = (g0, max(g1, g0) + 2 + (max(f0["k_strike"]) - g0 if f0["k_strike"] else 40))
            same = [e for e in ev_by.get((r["id"], f0["iid"]), []) if e["wt"] == wn and g0 - 2 <= e["gd"] <= g1 + 2]
            hit = [g for g in E.hits.get(f0["iid"], {}) if span[0] <= g <= span[1]]
            if same:
                c["bot_same"] += 1
                c["bot_same_ok"] += any(e["live"]["ok"] for e in same)
            elif hit:
                c["bot_other_hit"] += 1
            else:
                c["bot_none"] += 1
                c["missed_ok"] += ok                           # the bot did not hit it; the press would have, safely
    lines = [f"(the bot's lead f + 1 - fo: {dict(leads)})",
             "THE REPLAY (reflex_build replay / report, table " + a.tag + "): per group of recordings (traces, fight "
             "minutes), per window type: fire runs (the reflex fires: a run of frames, the same target and window), "
             "per minute, full / partial cells, the first press of each run judged exactly by simulation (closed loop, "
             "every Clapper and hazard: lands, touches nothing, an exit), what the bot did in the run (the same window "
             "type pressed, another hit on the target, none), the runs the bot missed whose press the judge passes "
             "(per minute)"]
    for grp in sorted(G):
        lines.append(f"\n{grp}: {n_tr[grp]} traces, {minutes[grp]:.1f} fight minutes")
        lines.append(f"  {'window':12s} {'runs':>5s} {'/min':>5s} {'full':>5s} {'part':>5s} {'sim ok':>9s} "
                     f"{'bot same (ok)':>14s} {'bot other hit':>13s} {'bot none':>9s} {'missed, sim ok /min':>20s}")
        for wn, c in sorted(G[grp].items(), key=lambda kv: -kv[1]["runs"]):
            m = max(minutes[grp], 1e-9)
            lines.append(f"  {wn:12s} {c['runs']:5d} {c['runs'] / m:5.1f} {c['full']:5d} {c['partial']:5d} "
                         f"{c['sim_ok']:4d}/{c['sim_n']:<4d} {c['bot_same']:6d} ({c['bot_same_ok']:4d}) "
                         f"{c['bot_other_hit']:13d} {c['bot_none']:9d} {c['missed_ok']:8d} {c['missed_ok'] / m:9.2f}")
        ot = open_t[grp]
        lines.append(f"  gates (ticks): {dict(gates[grp])}; the check's failures by step: {dict(chk_why[grp])}; "
                     f"Clawlines pressed inside the previous one's lock: {viol[grp]}")
        lines.append("  open (frames with a table window for her state, full / partial): " +
                     ", ".join(f"{wn} {ot[(wn, True)]}/{ot[(wn, False)]}" for wn in sorted({k[0] for k in ot})))
    lines.append("\nTHE COST PER TICK (ms, Reflex.check on this process, Idle priority; the first tick of each trace "
                 "excluded: the compiled paths' warm-up):")
    for grp in sorted(ticks):
        v = np.asarray(ticks[grp])
        h = np.asarray(tick_hit[grp])
        lines.append(f"  {grp:16s} ticks {len(v):7d} p50 {np.percentile(v, 50):.3f} p99 {np.percentile(v, 99):.3f} "
                     f"p99.9 {np.percentile(v, 99.9):.2f} max {v.max():.1f} | ticks with a window {len(h)} "
                     f"({len(h) / max(len(v), 1):.1%}) p50 {np.percentile(h, 50) if len(h) else 0:.3f} "
                     f"p99 {np.percentile(h, 99) if len(h) else 0:.2f} | checks {len(chk[grp])} p50 "
                     f"{np.percentile(chk[grp], 50) if chk[grp] else 0:.3f} p99 "
                     f"{np.percentile(chk[grp], 99) if chk[grp] else 0:.2f} | refreshes {len(refr[grp])} "
                     f"(their ticks p50 {np.percentile(refr[grp], 50) if refr[grp] else 0:.2f})")
    lines.append("THE COST WITHOUT THE PREDICTION'S REFRESH (the world handed in from outside - M4's workers - the bot's "
                 "thread does the lookup, the gates and the check only):")
    for grp in sorted(ticks_nr):
        v = np.asarray(ticks_nr[grp])
        lines.append(f"  {grp:16s} ticks {len(v):7d} p50 {np.percentile(v, 50):.3f} p99 {np.percentile(v, 99):.3f} "
                     f"p99.9 {np.percentile(v, 99.9):.2f} max {v.max():.1f}")
    txt = "\n".join(lines)
    (S2 / f"replay_{a.tag}.txt").write_text(txt, "utf-8")
    print(txt)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="reflex_build")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("frames")
    p.add_argument("--sets", default=",".join(SETS))
    p.add_argument("--jobs", type=int, default=8)
    p.add_argument("--limit", type=int, default=0)
    p = sub.add_parser("build")
    p.add_argument("--types", required=True, help="wt:cls,... e.g. claw_slam0:G,pogo_head2:A")
    p.add_argument("--jobs", type=int, default=8)
    p.add_argument("--mode", default="")
    p.add_argument("--j", default="", help="anchor frames lo-hi only")
    p.add_argument("--order", default="interleave")
    p.add_argument("--every", type=int, default=20)
    p.add_argument("--maxtasks", type=int, default=40)
    p.add_argument("--flight", action="store_true")
    p.add_argument("--max-try", type=int, default=0, help="macros evaluated per cell (0: reflex_gen.MAX_TRY)")
    p.add_argument("--domain", default="dense", choices=("dense", "visited"))
    p.add_argument("--nbr", type=int, default=1)
    p.add_argument("--cl-partial", action="store_true", help="(stage 4) keep a Clawline window's partial cells (the "
                   "runtime checks every press from her exact state)")
    p.add_argument("--out-dir", default="", help="the build files' folder under s2 (default build)")
    p = sub.add_parser("pack")
    p.add_argument("--out", default="")
    p = sub.add_parser("fix")
    p.add_argument("--src", default="")
    p.add_argument("--replace", default="", help="build files (under s2) whose (window, class) rows replace the "
                   "source's: build_v2/claw_slam0_A.pkl,...")
    p.add_argument("--no-plan", action="store_true", help="only --replace (the review's cell fixes already in --src)")
    p.add_argument("--out", default="")
    p.add_argument("--jobs", type=int, default=8)
    p.add_argument("--max-try", type=int, default=0)
    p = sub.add_parser("bitcheck")
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--jobs", type=int, default=8)
    p.add_argument("--table", default="")
    p.add_argument("--tag", default="", help="the output's suffix (s2/bitcheck_<tag>.pkl / .txt)")
    p.add_argument("--types", default="", help="only these wt:cls")
    p.add_argument("--skip", default="", help="not these wt:cls")
    p = sub.add_parser("replay")
    p.add_argument("--sets", default="held,sp13")
    p.add_argument("--jobs", type=int, default=8)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--table", default="")
    p.add_argument("--tag", default="v1")
    p.add_argument("--lead", type=int, default=1, help="f + 1 - fo: the bot sees STATE 1 - 2 frames late (lead 2 - 3)")
    p = sub.add_parser("report")
    p.add_argument("--tag", default="v1")
    a = ap.parse_args(argv)
    return {"frames": cmd_frames, "build": cmd_build, "pack": cmd_pack, "bitcheck": cmd_bitcheck,
            "replay": cmd_replay, "report": cmd_report, "fix": cmd_fix}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
