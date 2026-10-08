"""Reactive support audit (task "reactive support", forum.md §22): recorded Forum planner episodes replayed open loop
(as tools.forum_hit_forensics: the recorded STATEs drive ForumPlannerPolicy, the prefix of each tick is the recorded
ACTION masks, the supervisor never takes the keys), once per variant of the reactive support.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.forum_react_audit C:/ssbot/data/runs/m2/<run> [<run> ...]
        --out <dir> [--variants off,delay,escape] [--forced-rank share] [--episodes 0,3] [--every 3]
        [--workers 2] [--threads 4] [--deadline-ms inf]

Per episode and variant (<out>/<run>_i<inst>_ep<k>.json, the variants inside; existing files are skipped):
  ticks   every `every`-th battle tick and the ticks K_SET frames before each damage hit: FORCED_RISK, n_safe, the rows
          (ok and known), the chosen plan and its first contact with the recorded damage colliders over its horizon
          (hindsight, open loop: the enemies' reactions to another hero are not modelled; forum.md §19.1), how many
          rows the recorded future leaves clear (of all, of the safe ones), the planner's time (no deadline cut with
          --deadline-ms inf), the escape check's.
          The first variant's pass (off) also decomposes its support by category over the rows' nominal centres
          (frames 1 .. T, invulnerable frames clear; decompose_categories): the share of the live cells each covers
          alone and how many rows would be clear without it, for the support as it is and the delayed one
          (ReactConfig: strikes; +c +i +p5 too).
  hits    each damage hit: covered by the variant's support forecast L frames before (L = 2 3 4 12 24 36; the hero box
          at the hit frame or the one before, a chain's Final Hit at its hook as the live accounting). A hit outside
          a forecast made within its attack's wind-up is what the delay must never cause.
"""
import argparse
import json
import math
import random
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from ssbot.tools.forum_hit_forensics import K_SET, FramePolys, _mask_of, _own_ids, first_contact

LAGS = (2, 3, 4, 12, 24, 36)
CATS = ("start_attack", "start_idle", "entry", "committed_fine", "committed_window", "committed_bbox", "chain",
        "hazard", "body", "death", "arena")
COMMITTED = ("committed_fine", "committed_window", "committed_bbox")
EXT = {"delay": "delay", "delay_c": "delay+c", "delay_i": "delay+i", "delay_ci": "delay+c+i",
       "delay_cip5": "delay+c+i+p5"}


def categories(fcast) -> dict[str, dict]:
    """Per category (CATS) the placement masks (fine pm / window wm / bbox bb) and box kinds of a MultiForecast:
    start_attack  a later instance of an attack family (not committed); start_idle  of the idle family (and the
    current idle instance without its tube); entry  the entry families and the next wave's entries; committed  the
    current attacks, their re-anchors and tails (not a multi-hit family), by placement kind (fine: entry known to a
    few bins; window: an entry interval, the walk's hull; bbox: the family template from the start when the anchor is
    not known, a re-anchor); chain  a committed multi-hit family
    (MULTI_HIT); hazard  thrown hazards (self templates, paths, hazard tubes); body  the idle body and collider
    tubes; death  death tails; arena  arena-wide boxes."""
    from ssbot.combat.multi_forecast import ENTRY_OWNER, MULTI_HIT
    from ssbot.core.forum import FORUM_TYPES
    tk_of = {s.iid: s.type_key for s in fcast.subjects}
    out = {}
    for name, meta in (("pm", fcast.pm), ("wm", fcast.wm), ("bb", fcast.bb)):
        n = len(meta["owner"])
        cat = np.full(n, "", object)
        for i in range(n):
            o, fam, com = int(meta["owner"][i]), str(meta["family"][i]), bool(meta["committed"][i])
            tk = tk_of.get(o)
            sp = FORUM_TYPES.get(tk) if tk else None
            if fam.startswith("ent/"):
                c = "hazard"
            elif o <= ENTRY_OWNER or (sp is not None and fam == sp.entry_family):
                c = "entry"
            elif sp is not None and fam == sp.idle_family:
                c = "start_idle"
            elif com:
                c = "chain" if (tk, fam) in MULTI_HIT else \
                    {"pm": "committed_fine", "wm": "committed_window", "bb": "committed_bbox"}[name]
            else:
                c = "start_attack"
            cat[i] = c
        for c in CATS:
            out.setdefault(c, {})[name] = cat == c
    kinds = {"body": ("idle", "collider"), "hazard": ("hazard",), "death": ("death",), "arena": ("arena",)}
    for c in CATS:
        out[c]["kinds"] = kinds.get(c, ())
    return out


def cat_occ(fcast, cats: dict, c: str, cx, cy, t) -> np.ndarray:
    x, y, t = np.asarray(cx, np.float64), np.asarray(cy, np.float64), np.asarray(t, np.float64)
    m = cats[c]
    occ = np.zeros(x.shape, bool)
    if len(fcast.pm["owner"]) and m["pm"].any():
        occ |= fcast._fine_occ(x, y, t, m["pm"])
    if len(fcast.wm["owner"]) and m["wm"].any():
        occ |= fcast._win_occ(x, y, t, m["wm"])
    if len(fcast.bb["owner"]) and m["bb"].any():
        occ |= fcast._bbox_occ(x, y, t, m["bb"])
    if m["kinds"]:
        occ |= fcast._box_occ(x, y, t, kinds=m["kinds"])
    if c == "hazard":
        occ |= fcast._path_occ(x, y, t)
    return occ


def decompose_categories(fcast, cx, cy, t, live) -> dict:
    """Per category: the share of the live cells it covers alone, of the first frame's, and how many rows (of R) are
    clear without it; the rows clear under the whole support, without the later instances (start_attack and
    start_idle) and without every placement of a move not started (those and the entries)."""
    cats = categories(fcast)
    occ = {c: cat_occ(fcast, cats, c, cx, cy, t) & live for c in CATS}
    tot = max(int(live.sum()), 1)
    tot1 = max(int(live[:, 0].sum()), 1)
    full = np.zeros(live.shape, bool)
    for c in CATS:
        full |= occ[c]

    def clear(skip=()):
        u = np.zeros(live.shape, bool)
        for c in CATS:
            if c not in skip:
                u |= occ[c]
        return int((~u.any(axis=1)).sum())
    un = ("start_attack", "start_idle", "entry")
    return {"R": int(live.shape[0]), "clear": clear(), "share": round(float(full.sum() / tot), 3),
            "clear_wo_start": clear(("start_attack", "start_idle")),
            "clear_wo_unstarted": clear(un),
            "clear_wo_unstarted_cwin": clear(un + ("committed_window",)),
            "clear_wo_unstarted_committed": clear(un + COMMITTED),
            "clear_wo_unstarted_committed_chain": clear(un + COMMITTED + ("chain",)),
            "clear_body_hazard_only": clear(un + COMMITTED + ("chain", "death", "arena")),
            "clear_body_only": clear(tuple(c for c in CATS if c != "body")),
            "clear_hazard_only": clear(tuple(c for c in CATS if c != "hazard")),
            "cats": {c: [round(float(occ[c].sum() / tot), 3), round(float(occ[c][:, 0].sum() / tot1), 3),
                         clear((c,))] for c in CATS if occ[c].any()}}


def _coverage(pol, fj, tk) -> dict:
    """The hit at frame fj (or the frame before) against the variant's forecasts L frames earlier (LAGS)."""
    out = {}
    by_f = {x[0]: x for x in pol.forecasts}
    for L in LAGS:
        r = {"union": None, "own": None}
        old = None if fj is None else by_f.get(fj - L)
        if old is not None:
            _, fc, t_o = old
            xs, ys, ts = [], [], []
            for fr in (fj - 1, fj):
                bt = pol._boxes.get(fr)
                if bt is None:
                    continue
                bx, tt = bt
                xs.append(0.5 * (bx[0] + bx[2]))
                ys.append(0.5 * (bx[1] + bx[3]))
                ts.append(tt - t_o)
            if xs:
                X, Y, T = np.array([xs]), np.array([ys]), np.array(ts)
                r["union"] = bool(fc.occupied(X, Y, T).any())
                ids = _own_ids(fc, tk)
                r["own"] = bool(fc.occupied_only(X, Y, T, ids).any()) if ids else False
        out[str(L)] = r
    return out


def run_variant(pol, states, row, variant: str, every: int, deadline_ms, forced_rank: str, fp, dmg_f,
                decomp: bool) -> dict:
    from ssbot.combat.multi_forecast import ReactConfig
    from ssbot.knowledge.kinematics import F_INVULN
    from ssbot.tools.forum_a0_report import type_of
    from ssbot.train.encounters import ENCOUNTERS
    from ssbot.train.planner_policy import HORIZON_S
    pol.reset(random.Random(0), ENCOUNTERS[row["unit"]])
    pol.planner.debug = True
    pol.planner.fcfg.deadline_ms = deadline_ms
    pol.planner.fcfg.forced_rank = forced_rank
    pol.planner.fcfg.react = "off" if variant == "off" else EXT.get(variant, variant)
    pol._set_react(pol.planner.fcfg)
    want = set()
    for c in dmg_f:
        want |= {c - k for k in K_SET}
    f_first = int(states[0]["f"])
    ticks, hits = [], []
    for i, s in enumerate(states):
        nxt = states[i + 1] if i + 1 < len(states) else None
        if nxt is not None:
            pol.sent[int(nxt["f"])] = _mask_of(nxt)
        pol.act(s, None)
        fo = int(s["f"])
        for ev in s.get("ev") or ():
            if ev.get("k") != "damage":
                continue
            d = ev.get("d") or {}
            path = d.get("source")
            src = next((e for e in pol._hit_src.get(fo, []) if e["path"] == path), None)
            sid = None if src is None else src["sid"]
            tk = type_of(path, None)
            if sid is not None:
                tr = pol.fc.trackers.get(sid)
                tk = getattr(tr, "tk", tk) if tr is not None else tk
            fj = fo
            if "Final Hit" in str(d.get("fsm") or ""):
                fj = pol._hook_of(sid, str(path or ""), fo)
            hits.append({"f": fo, "path": path, "type": tk, "hook": fj, "cover": _coverage(pol, fj, tk)})
        li = pol.planner.last_info
        dbg = li.get("dbg") if li else None
        res = pol.planner_last
        if dbg is None or res is None:
            continue
        rel = fo - f_first
        if fo not in want and rel % every:
            continue
        box, flags = dbg["box"], dbg["flags"]
        inv = (flags & F_INVULN) != 0
        T1 = box.shape[1]
        fb, m = fp.window(fo, T1)
        first = first_contact(np.ascontiguousarray(box, np.float64), np.ascontiguousarray(inv), fp.verts,
                              fp.starts, fb, m, 0.0)
        rows = np.flatnonzero(dbg["ok"] & dbg["known"])
        S = li["S"]
        safe = rows[~S[rows]]
        ch = int(dbg["chosen"])
        rec = {"f": fo, "rel": rel, "forced": bool(res.forced_risk), "n_safe": int(res.n_safe), "R": int(len(rows)),
               "m": int(m), "pick": res.name, "pick_first": int(first[ch]) if 0 <= ch < len(first) else None,
               "clear": int((first[rows] < 0).sum()), "safe_clear": int((first[safe] < 0).sum()),
               "ms": round(float(res.t_ms.get("total", 0.0)), 3), "esc": li.get("esc")}
        if len(rows):
            rec["rand_clear"] = round(float((first[rows] < 0).mean()), 3)
        if decomp and len(rows):
            fr = np.arange(1, T1)
            br = box[rows][:, fr]
            cx, cy = 0.5 * (br[..., 0] + br[..., 2]), 0.5 * (br[..., 1] + br[..., 3])
            t = dbg["tk"][fr]
            live = ~inv[rows][:, fr]
            fcast = pol.forecasts[-1][1]
            rec["dec"] = {"off": decompose_categories(fcast, cx, cy, t, live)}
            keep = pol.fc.react
            try:
                for name in ("delay", "delay_ci", "delay_cip5"):
                    pol.fc.react = ReactConfig.parse(EXT[name])
                    t0 = time.perf_counter()
                    f2 = pol.fc.forecast(HORIZON_S)
                    fms = (time.perf_counter() - t0) * 1e3
                    d2 = decompose_categories(f2, cx, cy, t, live)
                    d2["fc_ms"] = round(fms, 3)
                    rec["dec"][name] = d2
            finally:
                pol.fc.react = keep
        ticks.append(rec)
    st = pol.stats()
    return {"ticks": ticks, "hits": hits, "audit": st.get("audit"), "plan_ms_p50": st.get("plan_ms_p50"),
            "plan_ms_p99": st.get("plan_ms_p99"), "tick_ms_p50": st.get("tick_ms_p50"),
            "tick_ms_p99": st.get("tick_ms_p99")}


def run_episode(job: dict) -> dict:
    from ssbot.record.recorder import RecordingReader
    pol = _POL["pol"]
    row = job["row"]
    t_job = time.perf_counter()
    rd = RecordingReader(row["recording"])
    for _, m in rd.terrain():
        if (m.get("scene_raw") or m.get("scene")) in ("Hang_04", "Hang_04_boss"):
            pol.terrain_msg = m
    states = list(rd.states(row["f_wake"], row["f_end"]))
    fp = FramePolys(states)
    dmg_f = sorted({int(s["f"]) for s in states for ev in (s.get("ev") or ()) if ev.get("k") == "damage"})
    out = {"run": job["run"], "inst": row["_inst"], "ep": row["episode"], "seed": row.get("seed"),
           "outcome": row.get("outcome"), "n_states": len(states), "dmg_f": dmg_f, "variants": {}}
    for k, v in enumerate(job["variants"]):
        out["variants"][v] = run_variant(pol, states, row, v, job["every"], job["deadline_ms"], job["forced_rank"],
                                         fp, dmg_f, decomp=(k == 0 and job["decomp"]))
    out["secs"] = round(time.perf_counter() - t_job, 1)
    return out


_POL: dict = {}


def _init(threads: int, crest: str = "Reaper") -> None:
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass
    import dataclasses
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy
    pol = ForumPlannerPolicy(threads=threads, crest=crest)
    pol.warmup()
    step0 = pol.sc.step

    def step(*args, **kw):
        r = step0(*args, **kw)
        pol.sc.pq = None
        return r._replace(mask=None, outcome=None) if hasattr(r, "_replace") else \
            dataclasses.replace(r, mask=None, outcome=None)
    pol.sc.step = step
    _POL["pol"] = pol


def _job_safe(job: dict) -> dict:
    try:
        return run_episode(job)
    except Exception:
        import traceback
        return {"run": job["run"], "inst": job["row"]["_inst"], "ep": job["row"]["episode"],
                "error": traceback.format_exc()[-2000:]}


def jobs_of(run: Path, a) -> list[dict]:
    out = []
    for p in sorted(run.glob("attempts_i*.jsonl")):
        inst = int(p.stem.split("_i")[1])
        for x in p.read_text("utf-8").splitlines():
            if not x.strip():
                continue
            r = json.loads(x)
            if r.get("outcome") == "HARNESS_FAIL" or not r.get("recording"):
                continue
            if a.episodes and r["episode"] not in a.episodes:
                continue
            r["_inst"] = inst
            r.pop("acts", None)
            out.append({"run": run.name, "row": r, "every": a.every, "deadline_ms": a.deadline_ms,
                        "forced_rank": a.forced_rank, "variants": a.variants, "decomp": not a.no_decomp})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="*", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--variants", type=lambda s: [x for x in s.split(",") if x], default=["off", "delay", "escape"])
    ap.add_argument("--forced-rank", default="share", choices=("share", "seen", "seen_cf"))
    ap.add_argument("--episodes", type=lambda s: [int(x) for x in s.split(",") if x], default=None)
    ap.add_argument("--every", type=int, default=3)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--deadline-ms", type=float, default=math.inf)
    ap.add_argument("--no-decomp", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="at most this many episodes per run (0: all)")
    ap.add_argument("--crest", default=None, help="the policy's crest (default: the first run's encounter: fo_W "
                    "Wanderer, else Reaper; one crest per call)")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    jobs = []
    for r in a.runs:
        js = [j for j in jobs_of(r, a)
              if not (a.out / f"{j['run']}_i{j['row']['_inst']}_ep{j['row']['episode']}.json").exists()]
        jobs += js[:a.limit] if a.limit else js
    print(f"{len(jobs)} episodes", flush=True)
    t0 = time.perf_counter()

    def write(res):
        p = a.out / f"{res['run']}_i{res['inst']}_ep{res['ep']}.json"
        p.write_text(json.dumps(res, default=str), "utf-8")
        print(f"{p.name} {'ERROR' if 'error' in res else ''} {res.get('secs')} s ({time.perf_counter() - t0:.0f} s)",
              flush=True)
    crest = a.crest
    if crest is None and jobs:
        from ssbot.train.encounters import ENCOUNTERS
        crest = "Wanderer" if ENCOUNTERS[jobs[0]["row"]["unit"]].savestate == "fo_W" else "Reaper"
    if a.workers <= 1:
        _init(a.threads, crest or "Reaper")
        for j in jobs:
            write(_job_safe(j))
    else:
        with ProcessPoolExecutor(a.workers, initializer=_init, initargs=(a.threads, crest or "Reaper")) as ex:
            for res in ex.map(_job_safe, jobs):
                write(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
