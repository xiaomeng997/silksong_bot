"""Map v2 stage M4b: THE SEARCH'S SPEED (offline; docs/plans/forum_map_v2.md section 1 L3 'Speed', HANDOFF 'Task map2 -
stage M4' / 'M4b'). The bot does not import this or ssbot.map2.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.m4b_speed ident --tag ref [--units 400] [--jobs 6]
        # every M3 situation searched with a VIRTUAL clock (Searcher.vclock: the time cap counted in work units -
        # closed-loop evaluations + exit checks - instead of seconds): a deterministic run whose digest (every tried
        # plan's key, value, safety; the chosen plan; the counters; the anytime trace) -> m4b/ident_<tag>.json
    ../scripts/uv.cmd run python -m ssbot.tools.m4b_speed identcmp ref new      # the two digests compared
    ../scripts/uv.cmd run python -m ssbot.tools.m4b_speed first --tag t --cap 2 [--workers 2] [--load]
        # the wall-clock run: the search in its own worker processes (boosted like the live bot: High, P-cores,
        # EcoQoS off; --load: busy processes standing in for 2 game instances and 2 bots) - per situation the time
        # to the first safe plan after the branch point (the decision), the anytime trace -> m4b/first_<tag>.json
    ../scripts/uv.cmd run python -m ssbot.tools.m4b_speed report --tags a,b    # the tables
    ../scripts/uv.cmd run python -m ssbot.tools.m4b_speed tick --tag t [--frames 40]
        # the per-tick check of the chosen plan along its nominal outcome -> m4b/tick_<tag>.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

OUT = Path(os.environ.get("SSBOT_M4B_OUT", r"C:\ssbot\data\m2_play\map2\m4\m4b"))   # (T3: SSBOT_M4B_OUT)
SITS = Path(r"C:\ssbot\data\m2_play\map2\m3\sits.pkl")


def load_sits() -> list:
    from ssbot.knowledge import kinematics as km
    with open(SITS, "rb") as fh:
        sits = pickle.load(fh)
    for s in sits:
        s.S = km.pad_state(s.S)
    return sits


def group_of(sit) -> str:
    """The situation's group: forced / person / rec w7 1 / rec w13 1 / rec w13 2 (forced two Clappers: forced2)."""
    src = sit.meta.get("src")
    n = len(sit.obs)
    if src == "rec":
        u = str(sit.meta.get("unit") or "")
        return f"rec {'w7' if 'w7' in u else 'w13'} {n}"
    return src + ("2" if n > 1 else "")


def boost_self(mode: str) -> str:
    """'high': the live bot's worker rule (High priority, the P-cores 0-15, EcoQoS off); 'idle': Idle priority."""
    try:
        import psutil
        p = psutil.Process()
        if mode == "idle":
            p.nice(psutil.IDLE_PRIORITY_CLASS)
            return "idle"
        if mode != "high":
            return "as started"
        p.nice(psutil.HIGH_PRIORITY_CLASS)
        n = psutil.cpu_count() or 16
        p.cpu_affinity([c for c in range(16) if c < n])
        import ctypes

        class _PT(ctypes.Structure):
            _fields_ = [("Version", ctypes.c_uint32), ("ControlMask", ctypes.c_uint32), ("StateMask", ctypes.c_uint32)]
        st = _PT(1, 1, 0)
        k32 = ctypes.windll.kernel32
        k32.SetProcessInformation(ctypes.c_void_p(k32.GetCurrentProcess()), 4, ctypes.byref(st), ctypes.sizeof(st))
        return "high"
    except Exception as e:  # noqa: BLE001
        return f"boost failed: {e}"


# ---- the worker ---------------------------------------------------------------------------------------------------

_W = None


def _world():
    """The worker's World, warmed like a live worker's (the numba functions loaded, one small search run)."""
    global _W
    if _W is None:
        from ssbot.knowledge import kinematics as km
        from ssbot.map2 import clapper as cm, search as ms, strike as sk
        _W = ms.World()
        S = km.initial_state(_W.params, 26.0, sk.FLOOR + sk.FOOT, ground=True, facing=1)
        o = cm.Obs(1, "Idle", 8 / 60.0, 33.0, cm.STAND_Y, 0.0, 0.0, -1, 230, None, j=8)
        Sr = ms.Searcher(_W, ms.Cfg(cap_s=0.3, depth=2))
        Sr.vclock = 0.01
        Sr.decide(ms.Situation(S, [o], {1: cm.Memory()}))
    return _W


def plan_digest(plan) -> str:
    return hashlib.md5(repr(plan.key()).encode()).hexdigest()[:16] if plan is not None else "-"


def _r9(v) -> float:
    return float(round(float(v), 9))


def run_one(args) -> dict:
    """One situation: decide() with the given clock; the digest, the anytime trace, the first safe plan."""
    i, sit, cfg_kw, vclock, prio = args[:5]
    part = args[5] if len(args) > 5 else None
    if prio:
        boost_self(prio)
    _mem_guard()
    from ssbot.map2 import search as ms, recognize as rz
    W = _world()
    if vclock is not None:
        # a deterministic run: the shape caches keyed by a rounded polygon hold the first polygon's exact vertices,
        # so their content (which situations a worker ran before) could move a result by < 1e-4 u - start empty
        ms._GROWN.clear()
        ms._SLABS.clear()
    cfg = ms.Cfg(**cfg_kw)
    if getattr(cfg, "tables", False):
        W.table_lib(cfg.tables_file, cfg.tables_budget)      # (T3: loaded once per worker, before the timed decision)
    S = ms.Searcher(W, cfg)
    S.vclock = vclock
    if part is not None:
        S.part = part
    t0 = time.perf_counter()
    try:
        r = S.decide(sit)
    except Exception as ex:  # noqa: BLE001 - a bug: count it, keep going
        import traceback
        return {"i": i, "name": sit.name, "error": repr(ex), "tb": traceback.format_exc()[-2000:]}
    ms_dec = (time.perf_counter() - t0) * 1e3
    ch = r.ev
    tried = [(plan_digest(e.plan), _r9(e.value), bool(e.safe), bool(e.open_ok), _r9(e.value_open), bool(e.finished),
              e.plan.origin) for e in r.tried]
    h = hashlib.md5(repr(tried).encode()).hexdigest()
    first = next((a for a in S.anytime if a[3] and a[4] != "noop"), None)
    probe = dict(getattr(ms, "PROBE_STATS", {}))
    if hasattr(ms, "PROBE_STATS"):
        ms.PROBE_STATS.update(checked=0, violations=0)
    first_any = next((a for a in S.anytime if a[3]), None)
    return {"i": i, "part": part, "name": sit.name, "group": group_of(sit), "moves": sit.meta.get("moves"),
            "ms": round(ms_dec, 1),
            "timed_out": bool(r.timed_out), "n_cand": r.n_cand, "n_pred": r.n_pred, "n_exit": r.n_exit,
            "units": S.ev.units, "ms_pred": round(r.ms_pred, 1), "ms_exit": round(r.ms_exit, 1),
            "chosen": plan_digest(ch.plan) if ch is not None else None,
            "value": _r9(ch.value) if ch is not None else None, "safe": bool(ch.safe) if ch is not None else None,
            "p_safe": _r9(ch.p_safe) if ch is not None else None, "hits": _r9(ch.hits) if ch is not None else None,
            "origin": ch.plan.origin if ch is not None else None,
            "labels": rz.classify(ch, sit) if ch is not None else [],
            "stats": dict(S.stats), "tried_hash": h, "n_tried": len(tried), "probe": probe,
            "anytime": [(round(a[0], 4), round(a[1], 1), round(a[2], 4), a[3], a[4], a[5]) for a in S.anytime],
            "marks": [m for m in getattr(S, "marks", []) if m[0] < 1500][:60],
            "first_safe_ms": None if first is None else first[1], "first_any_ms": None if first_any is None else
            first_any[1], "log": ms.plan_log(ch) if ch is not None else None}


MEM_LIMIT_GB = float(os.environ.get("SSBOT_M4B_MEM_GB", "10"))


def _mem_guard() -> None:
    """A worker that grows past MEM_LIMIT_GB of private memory ends itself (M4b: the M3 code's caches reached 48 GB
    on one two-Clapper situation and starved the machine) - the pool re-submits its job once, then records it."""
    import threading
    if getattr(_mem_guard, "on", False):
        return
    _mem_guard.on = True

    def watch():
        import psutil
        p = psutil.Process()
        while True:
            try:
                if p.memory_info().private > MEM_LIMIT_GB * 2 ** 30:
                    os._exit(9)
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.5)
    threading.Thread(target=watch, daemon=True).start()


def _pool_run(jobs: list, n_workers: int, out_path: Path, max_tasks: int = 8) -> list:
    """The jobs in worker processes; every result as a line as it comes (<out>.partial.jsonl); a worker lost (the
    memory guard) breaks the pool - the unfinished jobs are re-submitted, a job lost twice is recorded as an error."""
    from concurrent.futures import ProcessPoolExecutor, as_completed
    from concurrent.futures.process import BrokenProcessPool
    from collections import Counter as _C
    res = []
    t0 = time.time()
    part = out_path.with_suffix(".partial.jsonl")
    left = {n: j for n, j in enumerate(jobs)}
    tries = _C()
    with part.open("w", encoding="utf-8") as fh:
        while left:
            try:
                with ProcessPoolExecutor(max_workers=n_workers, max_tasks_per_child=max_tasks) as ex:
                    futs = {ex.submit(run_one, j): n for n, j in left.items()}
                    for f in as_completed(futs):
                        n = futs[f]
                        r = f.result()
                        res.append(r)
                        fh.write(json.dumps(r, default=str) + chr(10))
                        fh.flush()
                        left.pop(n, None)
                        if len(res) % 20 == 0:
                            print(f"{len(res)}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
            except BrokenProcessPool:
                for n in list(left):
                    tries[n] += 1
                    if tries[n] >= 3:
                        j = left.pop(n)
                        r = {"i": j[0], "part": j[5] if len(j) > 5 else None, "name": j[1].name,
                             "error": "worker lost (memory guard)"}
                        res.append(r)
                        fh.write(json.dumps(r, default=str) + chr(10))
                        fh.flush()
                print(f"a worker was lost: {len(left)} jobs re-submitted", flush=True)
    res.sort(key=lambda r: r["i"])
    out_path.write_text(json.dumps(res, indent=1, default=str), "utf-8")
    print(f"done {len(res)} in {time.time() - t0:.0f}s -> {out_path}", flush=True)
    return res


def _proc_child(job, q) -> None:
    try:
        q.put((job[0], job[5] if len(job) > 5 else None, run_one(job)))
    except Exception as ex:  # noqa: BLE001
        q.put((job[0], None, {"i": job[0], "name": job[1].name, "error": repr(ex)}))


def _proc_run(jobs: list, n_workers: int, out_path: Path, tries_max: int = 2) -> list:
    """One process per job (the identity runs: nothing carried between situations); a process that dies without a
    result (the memory guard) is retried once, then recorded - only that job (a broken pool would fail them all)."""
    import multiprocessing as mp
    from collections import Counter as _C
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    todo = list(range(len(jobs)))
    running: dict = {}
    got: dict = {}
    tries = _C()
    res = []
    t0 = time.time()
    part = out_path.with_suffix(".partial.jsonl")
    with part.open("w", encoding="utf-8") as fh:
        while todo or running:
            while todo and len(running) < n_workers:
                n = todo.pop(0)
                pr = ctx.Process(target=_proc_child, args=(jobs[n], q), daemon=True)
                pr.start()
                running[n] = pr
            try:
                while True:
                    i, _, r = q.get(timeout=0.2)
                    n = next((m for m in running if jobs[m][0] == i and m not in got), None)
                    if n is None:
                        continue
                    got[n] = r
                    res.append(r)
                    fh.write(json.dumps(r, default=str) + chr(10))
                    fh.flush()
                    if len(res) % 20 == 0:
                        print(f"{len(res)}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
            except Exception:  # noqa: BLE001 - queue empty
                pass
            for n, pr in list(running.items()):
                if n in got:
                    pr.join(timeout=5)
                    running.pop(n)
                elif not pr.is_alive():
                    running.pop(n)
                    tries[n] += 1
                    if tries[n] < tries_max:
                        todo.append(n)
                        print(f"job {jobs[n][0]} lost (exit {pr.exitcode}): retried", flush=True)
                    else:
                        r = {"i": jobs[n][0], "name": jobs[n][1].name, "error": f"worker lost (exit {pr.exitcode})"}
                        got[n] = r
                        res.append(r)
                        fh.write(json.dumps(r, default=str) + chr(10))
                        fh.flush()
    res.sort(key=lambda r: r["i"])
    out_path.write_text(json.dumps(res, indent=1, default=str), "utf-8")
    print(f"done {len(res)} in {time.time() - t0:.0f}s -> {out_path}", flush=True)
    return res


def _select(sits: list, a) -> list:
    out = list(enumerate(sits))
    if getattr(a, "groups", ""):
        gs = set(a.groups.split(","))
        out = [(i, s) for i, s in out if group_of(s) in gs]
    if getattr(a, "limit", 0):
        out = out[:a.limit]
    return out


def cmd_ident(a) -> int:
    boost_self("idle")
    sits = load_sits()
    cfg_kw = dict(cap_s=a.units * 0.01, depth=a.depth)
    cfg_kw.update(_cfg_over(getattr(a, "cfg", "")))       # (T3: e.g. the live flags, the tables)
    sel = _select(sits, a)
    if a.only_i:
        keep = {int(x) for x in a.only_i.split(",") if x.strip()}
        sel = [(i, s) for i, s in sel if i in keep]
    jobs = [(i, s, cfg_kw, 0.01, "idle") for i, s in sel]
    OUT.mkdir(parents=True, exist_ok=True)
    _proc_run(jobs, a.jobs, OUT / f"ident_{a.tag}.json")
    return 0


IDENT_KEYS = ("chosen", "value", "safe", "p_safe", "hits", "n_cand", "n_pred", "n_exit", "units", "tried_hash",
              "n_tried", "timed_out", "labels")


def cmd_identcmp(a) -> int:
    A = {r["i"]: r for r in json.loads((OUT / f"ident_{a.a}.json").read_text("utf-8"))}
    B = {r["i"]: r for r in json.loads((OUT / f"ident_{a.b}.json").read_text("utf-8"))}
    same, diff = 0, []
    for i in sorted(set(A) & set(B)):
        ra, rb = A[i], B[i]
        if "error" in ra or "error" in rb:
            diff.append((i, ra.get("name"), "error", ra.get("error"), rb.get("error")))
            continue
        bad = [k for k in IDENT_KEYS if ra.get(k) != rb.get(k)]
        aa = [x[:5] for x in ra.get("anytime", [])]
        ab = [x[:5] for x in rb.get("anytime", [])]
        aa = [(x[0], x[2], x[3], x[4]) for x in aa]
        ab = [(x[0], x[2], x[3], x[4]) for x in ab]
        if aa != ab:
            bad.append("anytime")
        if bad:
            diff.append((i, ra["name"], bad, {k: (ra.get(k), rb.get(k)) for k in bad if k != "anytime"}))
        else:
            same += 1
    print(f"identical {same} / {len(set(A) & set(B))}; differ {len(diff)}")
    for d in diff[:40]:
        print(" ", str(d)[:400])
    ta = sum(r.get("ms", 0) for r in A.values()) / 1e3
    tb = sum(r.get("ms", 0) for r in B.values()) / 1e3
    print(f"total decide time {a.a} {ta:.0f} s, {a.b} {tb:.0f} s (x{ta / max(tb, 1e-9):.2f})")
    return 0 if not diff else 1


# ---- the load: busy processes standing in for the games and the bots ------------------------------------------------

def _busy(kind: str, stop: str) -> None:
    if kind == "bot":
        boost_self("high")
    t_end = time.time() + 6 * 3600
    x = 0.0
    while time.time() < t_end and not os.path.exists(stop):
        t = time.perf_counter()
        if kind == "bot":                  # a bot tick: ~8 ms of work per 16.7 ms frame
            while time.perf_counter() - t < 0.008:
                x = x * 1.000001 + 1.0
            time.sleep(0.0087)
        else:                              # a game thread: busy
            for _ in range(200000):
                x = x * 1.000001 + 1.0


def start_load(n_game: int = 4, n_bot: int = 2) -> tuple:
    import multiprocessing as mp
    stop = str(OUT / "load.stop")
    if os.path.exists(stop):
        os.remove(stop)
    ps = [mp.Process(target=_busy, args=("game", stop), daemon=True) for _ in range(n_game)]
    ps += [mp.Process(target=_busy, args=("bot", stop), daemon=True) for _ in range(n_bot)]
    for p in ps:
        p.start()
    return ps, stop


def stop_load(ps, stop: str) -> None:
    Path(stop).write_text("stop", "utf-8")
    for p in ps:
        p.join(timeout=10)
        if p.is_alive():
            p.terminate()


def _cfg_over(spec: str) -> dict:
    """Cfg overrides 'k=v;k=v' (the values Python literals, cast to the field's type)."""
    from ssbot.map2 import search as ms
    out = {}
    for kv in (spec or "").split(";"):
        if kv.strip():
            k, v = kv.split("=")
            out[k.strip()] = type(getattr(ms.Cfg(), k.strip()))(eval(v))  # noqa: S307 - our own command line
    return out


def cmd_first(a) -> int:
    sits = load_sits()
    cfg_kw = dict(cap_s=a.cap, depth=a.depth)
    for kv in (a.cfg or "").split(";"):
        if kv.strip():
            k, v = kv.split("=")
            cfg_kw[k.strip()] = type(getattr(__import__("ssbot.map2.search", fromlist=["Cfg"]).Cfg(), k.strip()))(
                eval(v))  # noqa: S307 - our own command line
    pr = getattr(a, "prio", "high")             # (T3: 'idle' - the stage's runs at Idle priority)
    if a.split > 1:
        jobs = [(i, s, cfg_kw, None, pr, (q, a.split)) for i, s in _select(sits, a) for q in range(a.split)]
    else:
        jobs = [(i, s, cfg_kw, None, pr) for i, s in _select(sits, a)]
    OUT.mkdir(parents=True, exist_ok=True)
    load = start_load(a.load_game, a.load_bot) if a.load else None
    try:
        res = _pool_run(jobs, a.workers * max(1, a.split), OUT / f"first_{a.tag}.json", max_tasks=a.max_tasks)
    finally:
        if load is not None:
            stop_load(*load)
    if a.split > 1:
        res = merge_parts(res)
        (OUT / f"first_{a.tag}.json").write_text(json.dumps(res, indent=1, default=str), "utf-8")
    print(report_first({a.tag: res}))
    return 0


def merge_parts(res: list) -> list:
    """A split search's parts merged per situation: the best plan (safe first, then the value), the anytime traces
    joined (at each change the best so far over the parts), the first safe plan the earliest over the parts."""
    by = defaultdict(list)
    for r in res:
        by[r["i"]].append(r)
    out = []
    for i, rr in sorted(by.items()):
        ok = [r for r in rr if "error" not in r]
        if not ok:
            out.append(rr[0])
            continue
        best = max(ok, key=lambda r: (bool(r["safe"]), r["value"] if r["value"] is not None else -9))
        m = dict(best)
        ev = sorted([a for r in ok for a in r["anytime"]], key=lambda a: a[1])
        trace, cur = [], None
        for a in ev:
            if cur is None or (a[3], a[2]) > (cur[3], cur[2]):
                cur = a
                trace.append(a)
        m["anytime"] = trace
        fs = [r["first_safe_ms"] for r in ok if r["first_safe_ms"] is not None]
        fa = [r["first_any_ms"] for r in ok if r["first_any_ms"] is not None]
        m["first_safe_ms"] = min(fs) if fs else None
        m["first_any_ms"] = min(fa) if fa else None
        m["ms"] = max(r["ms"] for r in ok)
        m["parts"] = len(rr)
        out.append(m)
    return out


def _pct(v, qs=(50, 90, 99), fmt="{:.0f}"):
    v = np.asarray([x for x in v if x is not None], float)
    if not len(v):
        return "-"
    return " / ".join(fmt.format(np.percentile(v, q, method="higher")) for q in qs)   # (no interpolation: inf stays)


GROUPS = ("rec w7 1", "rec w13 1", "rec w13 2", "forced", "forced2", "person")


def value_at(anytime: list, t_ms: float):
    """The best plan's value at wall time t_ms (None: no plan yet; the noop counts as a plan)."""
    v = None
    for a in anytime:
        if a[1] <= t_ms:
            v = a[2]
    return v


def value_safe_at(anytime: list, t_ms: float):
    """The best SAFE plan's value at wall time t_ms (None: no safe plan yet; the noop counts)."""
    v = None
    for a in anytime:
        if a[1] <= t_ms and a[3]:
            v = a[2]
    return v


_REF: dict = {}


def ref_values(tag: str = "v4") -> dict:
    """An M3-era 60 s run (primitives only): situation name -> (value, safe, origin). v4: M3's (the M3 models);
    m4a2: M4a's re-run at e6a4513 (the current models)."""
    if tag not in _REF:
        p = SITS.parent / f"run_none_{tag}.json"
        _REF[tag] = {r["name"]: (r["value"], r["safe"], r["origin"]) for r in json.loads(p.read_text("utf-8"))
                     if "error" not in r}
    return _REF[tag]


def v4_values() -> dict:
    return ref_values("v4")


TS = (250, 500, 1000, 2000)


def report_first(runs: dict) -> str:
    lines = []
    for ref in ("v4", "m4a2"):
        v4 = ref_values(ref)
        for tag, res in runs.items():
            ok = [r for r in res if "error" not in r]
            lines.append(f"=== {tag}: the anytime value (the best safe plan's value at t; {ref} = that 60 s run) - "
                         f"mean value / share >= {ref} - 0.05 / share with a safe strike or endpoint plan")
            for g in GROUPS + ("all",):
                rr = [r for r in ok if (g == "all" or r["group"] == g) and r["name"] in v4]
                if not rr:
                    continue
                cells = []
                for t in TS:
                    vs = [value_safe_at(r["anytime"], t) for r in rr]
                    good = [v is not None and v >= (v4[r["name"]][0] if v4[r["name"]][0] is not None else -1) - 0.05
                            for v, r in zip(vs, rr)]
                    strike = [any(a[1] <= t and a[3] and a[4] != "noop" for a in r["anytime"]) for r in rr]
                    mv = np.mean([v if v is not None else -1.0 for v in vs])
                    cells.append(f"{t / 1000:g}s {mv:5.2f} {np.mean(good):4.2f} {np.mean(strike):4.2f}")
                v4m = np.mean([v4[r["name"]][0] if v4[r["name"]][0] is not None else -1.0 for r in rr])
                lines.append(f"{g:10s} n {len(rr):3d}  " + "  |  ".join(cells) + f"  |  {ref} {v4m:5.2f}")
    # the first safe plan, over the situations where the current models' 60 s run (m4a2) had a safe non-noop plan
    m4 = ref_values("m4a2")
    for tag, res in runs.items():
        ok = [r for r in res if "error" not in r]
        lines.append(f"=== {tag}: {len(res)} situations, errors {len(res) - len(ok)}; the first safe plan over the "
                     f"situations where m4a2's 60 s search had a safe strike / endpoint plan (none: not by the cap)")
        lines.append(f"{'group':10s} {'n':>4s}  first safe plan ms p50/p90/p99 (none)   first safe incl. noop   "
                     f"decide ms p50/p90")
        for g in GROUPS + ("all",):
            rr = [r for r in ok if (g == "all" or r["group"] == g) and r["name"] in m4 and m4[r["name"]][1]
                  and m4[r["name"]][2] != "noop"]
            if not rr:
                continue
            fs = [r["first_safe_ms"] if r["first_safe_ms"] is not None else np.inf for r in rr]   # none: never
            fa = [r["first_any_ms"] if r["first_any_ms"] is not None else np.inf for r in rr]
            lines.append(f"{g:10s} {len(rr):4d}  {_pct(fs):24s} ({sum(1 for x in fs if not np.isfinite(x)):3d})   "
                         f"{_pct(fa):22s}  {_pct([r['ms'] for r in rr])}")
    return "\n".join(lines)


def run_tick(args) -> dict:
    """One situation: decide (wall clock, cap), then the checks of the chosen plan: the full tick_check (and M3's)
    at the decision, TickCheck's build and its per-frame check along every safe outcome (the Clappers observed from
    that outcome's branch, her position from its trajectory), and one observation moved 1 u (must fail)."""
    i, sit, cfg_kw, prio, max_frames = args
    if prio:
        boost_self(prio)
    from ssbot.map2 import search as ms
    W = _world()
    S = ms.Searcher(W, ms.Cfg(**cfg_kw))
    try:
        r = S.decide(sit)
    except Exception as ex:  # noqa: BLE001
        import traceback
        return {"i": i, "name": sit.name, "error": repr(ex), "tb": traceback.format_exc()[-2000:]}
    ch = r.ev
    out = {"i": i, "name": sit.name, "group": group_of(sit), "ms": round(r.ms, 1),
           "safe": bool(ch.safe) if ch is not None else None}
    if ch is None or not ch.plan.segs:
        return out
    if not ch.finished:
        S.ev.finish(ch)
    S.ev.reset()
    ok, bad, ms_full = S.ev.tick_check(sit, ch.plan)
    S.ev.reset()
    ok3, bad3, ms_m3 = S.ev.tick_check_m3(sit, ch.plan)
    t = time.perf_counter()
    tc = ms.TickCheck(ch)
    ms_build = (time.perf_counter() - t) * 1e3
    kb_pickle = len(pickle.dumps(tc)) / 1024.0
    frames, oks, n_out = [], [], 0
    for o in ch.outcomes:
        if not o.safe:
            continue
        n_out += 1
        for n in range(0, min(int(getattr(o, "k_end", o.tr.end)), max_frames) + 1):
            obs = ms.observe_branch(sit, o.branch, n)
            t = time.perf_counter()
            okn, left, pc = tc.check(n, o.tr.pos[n], obs)
            frames.append((time.perf_counter() - t) * 1e3)
            oks.append(bool(okn))
    nom = ch.nominal
    moved = None
    if nom is not None and nom.safe and nom.k_end >= 5:
        obs = ms.observe_branch(sit, nom.branch, 5)
        for ob in obs:
            ob.x += 1.0
        moved = bool(tc.check(5, nom.tr.pos[5], obs)[0])
    out.update(kb_pickle=round(kb_pickle, 1), full_ok=bool(ok), full_bad=bad, ms_full=round(ms_full, 2), m3_ok=bool(ok3), m3_bad=bad3,
               ms_m3=round(ms_m3, 2), ms_build=round(ms_build, 2), n_outcomes=n_out,
               frame_ms=[round(x, 4) for x in frames], frame_ok=sum(oks), frame_n=len(oks), moved_ok=moved)
    return out


def cmd_tick(a) -> int:
    from concurrent.futures import ProcessPoolExecutor, as_completed
    sits = load_sits()
    cfg_kw = dict(cap_s=a.cap, depth=a.depth, pass2_after=a.pass2_after)
    cfg_kw.update(_cfg_over(a.cfg))
    jobs = [(i, s, cfg_kw, "high", a.frames) for i, s in _select(sits, a)]
    load = start_load(a.load_game, a.load_bot) if a.load else None
    res = []
    t0 = time.time()
    try:
        with ProcessPoolExecutor(max_workers=a.workers, max_tasks_per_child=24) as ex:
            futs = [ex.submit(run_tick, j) for j in jobs]
            for n, f in enumerate(as_completed(futs)):
                res.append(f.result())
                if (n + 1) % 20 == 0:
                    print(f"{n + 1}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
    finally:
        if load is not None:
            stop_load(*load)
    res.sort(key=lambda r: r["i"])
    (OUT / f"tick_{a.tag}.json").write_text(json.dumps(res, indent=1, default=str), "utf-8")
    print(report_tick(res))
    return 0


def report_tick(res: list) -> str:
    ok = [r for r in res if "error" not in r and "full_ok" in r]
    lines = [f"tick checks: {len(ok)} situations with a plan ({len(res) - len(ok)} without / errors)"]
    for g in GROUPS + ("all",):
        rr = [r for r in ok if g == "all" or r["group"] == g]
        if not rr:
            continue
        fr = [x for r in rr for x in r["frame_ms"]]
        lines.append(f"{g:10s} n {len(rr):3d}  per-frame check ms p50/p90/p99/max {_pct(fr, (50, 90, 99, 100), '{:.3f}')}"
                     f" (frames {len(fr)}, consistent {sum(r['frame_ok'] for r in rr)}/{sum(r['frame_n'] for r in rr)})"
                     f"  build {_pct([r['ms_build'] for r in rr], fmt='{:.1f}')} ms, {_pct([r.get('kb_pickle') for r in rr], fmt='{:.0f}')} kB"
                     f"  full check {_pct([r['ms_full'] for r in rr], fmt='{:.1f}')}"
                     f" (fails {sum(1 for r in rr if not r['full_ok'])}; unsafe chosen {sum(1 for r in rr if not r['safe'])})"
                     f"  M3 check {_pct([r['ms_m3'] for r in rr], fmt='{:.1f}')} (fails {sum(1 for r in rr if not r['m3_ok'])})"
                     f"  moved 1 u still ok {sum(1 for r in rr if r.get('moved_ok'))}")
    return "\n".join(lines)


def cmd_report(a) -> int:
    runs = {t: json.loads((OUT / f"first_{t}.json").read_text("utf-8")) for t in a.tags.split(",")}
    print(report_first(runs))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="m4b_speed")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ident")
    p.add_argument("--tag", required=True)
    p.add_argument("--units", type=int, default=400)
    p.add_argument("--depth", type=int, default=3)
    p.add_argument("--jobs", type=int, default=6)
    p.add_argument("--groups", default="")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--only-i", default="", help="only these situation indices (comma-separated)")
    p.add_argument("--cfg", default="", help="Cfg overrides k=v;k=v (T3)")
    p.set_defaults(fn=cmd_ident)
    p = sub.add_parser("identcmp")
    p.add_argument("a")
    p.add_argument("b")
    p.set_defaults(fn=cmd_identcmp)
    p = sub.add_parser("first")
    p.add_argument("--tag", required=True)
    p.add_argument("--cap", type=float, default=2.0)
    p.add_argument("--depth", type=int, default=3)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--max-tasks", type=int, default=24)
    p.add_argument("--load", action="store_true")
    p.add_argument("--load-game", type=int, default=4)
    p.add_argument("--load-bot", type=int, default=2)
    p.add_argument("--groups", default="")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--cfg", default="", help="Cfg overrides k=v;k=v")
    p.add_argument("--split", type=int, default=1, help="a split search: this many parts per situation in parallel")
    p.add_argument("--prio", default="high", choices=("high", "idle"), help="the workers' priority (T3: idle)")
    p.set_defaults(fn=cmd_first)
    p = sub.add_parser("tick")
    p.add_argument("--tag", required=True)
    p.add_argument("--cap", type=float, default=1.0)
    p.add_argument("--depth", type=int, default=3)
    p.add_argument("--pass2-after", type=int, default=6)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--frames", type=int, default=60)
    p.add_argument("--cfg", default="", help="Cfg overrides k=v;k=v")
    p.add_argument("--load", action="store_true")
    p.add_argument("--load-game", type=int, default=4)
    p.add_argument("--load-bot", type=int, default=2)
    p.add_argument("--groups", default="")
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(fn=cmd_tick)
    p = sub.add_parser("report")
    p.add_argument("--tags", required=True)
    p.set_defaults(fn=cmd_report)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
