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

OUT = Path(r"C:\ssbot\data\m2_play\map2\m4\m4b")
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
    i, sit, cfg_kw, vclock, prio = args
    if prio:
        boost_self(prio)
    from ssbot.map2 import search as ms, recognize as rz
    W = _world()
    if vclock is not None:
        # a deterministic run: the shape caches keyed by a rounded polygon hold the first polygon's exact vertices,
        # so their content (which situations a worker ran before) could move a result by < 1e-4 u - start empty
        ms._GROWN.clear()
        ms._SLABS.clear()
    cfg = ms.Cfg(**cfg_kw)
    S = ms.Searcher(W, cfg)
    S.vclock = vclock
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
    first_any = next((a for a in S.anytime if a[3]), None)
    return {"i": i, "name": sit.name, "group": group_of(sit), "moves": sit.meta.get("moves"), "ms": round(ms_dec, 1),
            "timed_out": bool(r.timed_out), "n_cand": r.n_cand, "n_pred": r.n_pred, "n_exit": r.n_exit,
            "units": S.ev.units, "ms_pred": round(r.ms_pred, 1), "ms_exit": round(r.ms_exit, 1),
            "chosen": plan_digest(ch.plan) if ch is not None else None,
            "value": _r9(ch.value) if ch is not None else None, "safe": bool(ch.safe) if ch is not None else None,
            "p_safe": _r9(ch.p_safe) if ch is not None else None, "hits": _r9(ch.hits) if ch is not None else None,
            "origin": ch.plan.origin if ch is not None else None,
            "labels": rz.classify(ch, sit) if ch is not None else [],
            "stats": dict(S.stats), "tried_hash": h, "n_tried": len(tried),
            "anytime": [(round(a[0], 4), round(a[1], 1), round(a[2], 4), a[3], a[4], a[5]) for a in S.anytime],
            "first_safe_ms": None if first is None else first[1], "first_any_ms": None if first_any is None else
            first_any[1], "log": ms.plan_log(ch) if ch is not None else None}


def _pool_run(jobs: list, n_workers: int, out_path: Path, max_tasks: int = 8) -> list:
    from concurrent.futures import ProcessPoolExecutor, as_completed
    res = []
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=n_workers, max_tasks_per_child=max_tasks) as ex:
        futs = {ex.submit(run_one, j): j[0] for j in jobs}
        for n, f in enumerate(as_completed(futs)):
            r = f.result()
            res.append(r)
            if (n + 1) % 20 == 0:
                print(f"{n + 1}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
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
    jobs = [(i, s, cfg_kw, 0.01, "idle") for i, s in _select(sits, a)]
    OUT.mkdir(parents=True, exist_ok=True)
    _pool_run(jobs, a.jobs, OUT / f"ident_{a.tag}.json")
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


def cmd_first(a) -> int:
    sits = load_sits()
    cfg_kw = dict(cap_s=a.cap, depth=a.depth)
    for kv in (a.cfg or "").split(","):
        if kv.strip():
            k, v = kv.split("=")
            cfg_kw[k.strip()] = type(getattr(__import__("ssbot.map2.search", fromlist=["Cfg"]).Cfg(), k.strip()))(
                eval(v))  # noqa: S307 - our own command line
    jobs = [(i, s, cfg_kw, None, "high") for i, s in _select(sits, a)]
    OUT.mkdir(parents=True, exist_ok=True)
    load = start_load(a.load_game, a.load_bot) if a.load else None
    try:
        res = _pool_run(jobs, a.workers, OUT / f"first_{a.tag}.json", max_tasks=a.max_tasks)
    finally:
        if load is not None:
            stop_load(*load)
    print(report_first({a.tag: res}))
    return 0


def _pct(v, qs=(50, 90, 99), fmt="{:.0f}"):
    v = np.asarray([x for x in v if x is not None], float)
    if not len(v):
        return "-"
    return " / ".join(fmt.format(np.percentile(v, q)) for q in qs)


GROUPS = ("rec w7 1", "rec w13 1", "rec w13 2", "forced", "forced2", "person")


def value_at(anytime: list, t_ms: float):
    """The best plan's value at wall time t_ms (None: no plan yet; the noop counts as a plan)."""
    v = None
    for a in anytime:
        if a[1] <= t_ms:
            v = a[2]
    return v


def report_first(runs: dict) -> str:
    lines = []
    for tag, res in runs.items():
        ok = [r for r in res if "error" not in r]
        lines.append(f"=== {tag}: {len(res)} situations, errors {len(res) - len(ok)}")
        lines.append(f"{'group':10s} {'n':>4s}  first safe plan ms p50/p90/p99 (none)   first safe incl. noop   "
                     f"decide ms p50/p90")
        for g in GROUPS + ("all",):
            rr = [r for r in ok if g == "all" or r["group"] == g]
            if not rr:
                continue
            fs = [r["first_safe_ms"] for r in rr]
            fa = [r["first_any_ms"] for r in rr]
            lines.append(f"{g:10s} {len(rr):4d}  {_pct(fs):24s} ({sum(1 for x in fs if x is None):3d})   "
                         f"{_pct(fa):22s}  {_pct([r['ms'] for r in rr])}")
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
    p.add_argument("--cfg", default="", help="Cfg overrides k=v,k=v")
    p.set_defaults(fn=cmd_first)
    p = sub.add_parser("report")
    p.add_argument("--tags", required=True)
    p.set_defaults(fn=cmd_report)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
