"""Forum plan R2 acceptance (f), forum_planner_plan.md §4.4 item 6: a kill or a bell redirect never enlarges the
danger zone around the hero over the next 1 s (a violation is a model error, or a game rule that does enlarge it,
each one explained).

Replays recordings through OracleBackend and the run-time MultiForecaster (production tables) and compares, on a grid
of hero-centre positions around the hero's position (near: +-2 u; wide: +-6 u, informational) and the next 1 s in
1/60 s bins, what the forecast covers with and without the action:
  kill (simulated)      every in-play enemy at every --every-th frame: MultiForecaster.forecast_if_killed([iid])
                        against forecast();
  kill (recorded)       the frame before each recorded kill: the same what-if for the enemy that died; and the
                        forecast after the kill against the one before it (same absolute times), restricted to the
                        dead enemy's support and the wave entries;
  redirect (simulated)  every bell on a path within --bell-near u of the hero at every --every-th frame, hit now away
                        from the hero (sideways; down when it is below, up when above): MultiForecast.bell_redirected
                        against occupied();
  redirect (recorded)   the frame before each recorded Nail Hit, the same with the direction it went.
Violations (cells covered with the action and not without) are classified: kills by what covers them (the wave
entries queued by a wave's last kill, the dead enemy's death tail box, its instance tails, other), redirects by what
the redirected path met before the first violating time (dome contact -> undetermined tube, side wall rebound, floor
bounce, none: direct).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.consistency_audit --fights C:/ssbot/data/m2_forum_r0/fresh/fights.json
        [--max-fights N] [--every 30] [--workers 3] [--json out.json]
"""
import argparse
import json
import math
import time
import traceback
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

H_S = 1.0                      # the property's window
BIN = 1.0 / 60.0
NEAR_U, NEAR_STEP = 2.0, 0.25
WIDE_U, WIDE_STEP = 6.0, 0.5
TK = np.arange(0, int(round(H_S / BIN)) + 1) * BIN

_TABLES = None


def _grid(hx: float, hy: float, r: float, step: float) -> tuple[np.ndarray, np.ndarray]:
    g = np.arange(-r, r + 1e-9, step)
    gx, gy = np.meshgrid(hx + g, hy + g, indexing="ij")
    n = gx.size
    return np.repeat(gx.reshape(n, 1), len(TK), axis=1), np.repeat(gy.reshape(n, 1), len(TK), axis=1)


def _tables():
    global _TABLES
    if _TABLES is None:
        from ssbot.combat.enemy_tables import EnemyTables
        _TABLES = EnemyTables.production()
    return _TABLES


def _init_worker() -> None:
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass


def _entry_ids() -> set:
    from ssbot.combat.multi_forecast import ENTRY_OWNER
    from ssbot.core.forum import FORUM_WAVES
    return {ENTRY_OWNER - w for w in range(len(FORUM_WAVES))}


def _classify_kill(F, v: int, X, Y, tk, viol: np.ndarray, waiting: set) -> Counter:
    """What covers the violating cells of the what-if forecast F (victim v): the next wave (its entries, its waiting
    members' walks: the kill ended a wave), the death box, the victim's tails, other."""
    out = Counter()
    left = viol.copy()
    ent = F.occupied_only(X, Y, tk, _entry_ids()) & left
    out["wave entries"] += int(ent.sum())
    left &= ~ent
    if waiting:
        wm = F.occupied_only(X, Y, tk, waiting) & left
        out["next wave's waiting members"] += int(wm.sum())
        left &= ~wm
    death = F._box_occ(X, Y, np.asarray(tk, np.float64), kinds=("death",), only={v}) & left
    out["death box"] += int(death.sum())
    left &= ~death
    own = F.occupied_only(X, Y, tk, {v} | {o for o, m in F.groups.items() if v in m}) & left
    out["victim (tails; a pooled Tiny's walk, its group's rows)"] += int(own.sum())
    left &= ~own
    out["other"] += int(left.sum())
    return out


def _waiting(mf) -> set:
    return {i for i, t in mf.trackers.items() if not t.in_play and not t.dead}


def _redirect_class(F, iid: int, d: int, t_first: float) -> str:
    """What the redirected path met before t_first (s from the origin)."""
    from ssbot.combat.projectiles import BELL_FLOOR_Y, BELL_R, STEP_S
    from ssbot.core.forum import WALL_L, WALL_R
    p = F._fc.hazards.redirect(iid, 0.0, d, F.origin_t, F.horizon)
    if p is None:
        return "no path"
    k = int(max(0, math.floor((t_first - p.t_first) / STEP_S))) + 1
    if p.tube_from is not None and p.tube_from <= t_first + 1e-9:
        return "dome contact (undetermined tube)"
    xs, ys = p.xs[:k + 1], p.ys[:k + 1]
    if np.any(xs <= WALL_L + BELL_R + 1e-6) or np.any(xs >= WALL_R - BELL_R - 1e-6):
        return "side wall rebound"
    if np.any(ys <= BELL_FLOOR_Y + 1e-6):
        return "floor bounce"
    return "up hit falls back (gravity)" if d == 2 else "direct"


def _haz_dir(vx: float, vy: float) -> int | None:
    if abs(vx) >= 20.0:
        return 1 if vx > 0 else -1
    if vy >= 20.0:
        return 2
    if vy <= -20.0:
        return 0
    return None


def audit_fight(job: dict) -> dict:
    try:
        return _audit_fight(job)
    except Exception as e:  # noqa: BLE001
        return {"id": job["id"], "error": f"{type(e).__name__}: {e} {traceback.format_exc()[-1200:]}"}


def _audit_fight(job: dict) -> dict:
    from ssbot.backends.oracle_backend import OracleBackend
    from ssbot.combat.multi_forecast import MultiForecaster
    from ssbot.combat.projectiles import BELL, hazard_type
    from ssbot.core.worldstate import Ev
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.multi_recall import wave_of
    tables = _tables()
    mf = MultiForecaster(tables)
    backend = OracleBackend()
    r = RecordingReader(job["path"])
    f0, f1 = int(job["f0"]), int(job["f1"])
    if job.get("frames"):
        f1 = min(f1, f0 + int(job["frames"]))
    every = job["every"]
    stats: dict = defaultdict(Counter)
    examples: list = []
    wave = wave_of(job["id"])
    last_f = None
    t_ms = []

    def note(kind: str, zone: str, viol: np.ndarray, cls: Counter | str, info: dict) -> None:
        st = stats[f"{kind}/{zone}"]
        st["checks"] += 1
        n = int(viol.sum())
        if not n:
            return
        st["violating checks"] += 1
        st["cells"] += n
        if isinstance(cls, str):
            st[f"class: {cls}"] += 1
        else:
            for k, v in cls.items():
                if v:
                    st[f"cells: {k}"] += v
        if len(examples) < 400:
            t_first = float(TK[np.flatnonzero(viol.any(axis=0))[0]])
            examples.append({"fight": job["id"], "kind": kind, "zone": zone, "cells": n, "t_first": round(t_first, 4),
                             "class": cls if isinstance(cls, str) else dict(cls), **info})

    def kill_whatif(kind: str, ws, f: int, F, v: int) -> None:
        tr = mf.trackers.get(v)
        if tr is None or tr.dead or not tr.in_play:
            return
        hx, hy = ws.hero.pos.v
        Fk = mf.forecast_if_killed([v], H_S + 0.1)
        stats[f"{kind}/by type"][tr.tk] += 1
        for zone, (rad, step) in (("near", (NEAR_U, NEAR_STEP)), ("wide", (WIDE_U, WIDE_STEP))):
            X, Y = _grid(hx, hy, rad, step)
            base = F.occupied(X, Y, TK)
            viol = Fk.occupied(X, Y, TK) & ~base
            cls = _classify_kill(Fk, v, X, Y, TK, viol, _waiting(mf)) if viol.any() else Counter()
            if zone == "near" and viol.any():
                stats[f"{kind}/near violations by type"][tr.tk] += 1
            note(kind, zone, viol, cls, {"f": f, "victim": tr.tk, "state": tr.state, "family": tr.cur.family if tr.cur else
                                         None, "hero": [round(hx, 2), round(hy, 2)],
                                         "enemy": None if tr.pos is None else [round(tr.pos[0], 2),
                                                                               round(tr.pos[1], 2)]})

    def redirect_whatif(kind: str, ws, F, iid: int, d: int) -> None:
        hx, hy = ws.hero.pos.v
        for zone, (rad, step) in (("near", (NEAR_U, NEAR_STEP)), ("wide", (WIDE_U, WIDE_STEP))):
            X, Y = _grid(hx, hy, rad, step)
            red = F.bell_redirected(X, Y, TK, iid, 0.0, d)
            if red is None:
                return
            viol = red & ~F.occupied(X, Y, TK)
            cls = ""
            if viol.any():
                cls = _redirect_class(F, iid, d, float(TK[np.flatnonzero(viol.any(axis=0))[0]]))
            h = mf.hazards.h.get(iid)
            note(kind, zone, viol, cls, {"d": d, "hero": [round(hx, 2), round(hy, 2)],
                                         "bell": None if h is None else [round(h.pos[0], 2), round(h.pos[1], 2)],
                                         "bell_v": None if h is None else [round(h.vel[0], 2), round(h.vel[1], 2)]})

    prev_F = None
    prev_T = None
    ws_prev = None
    for s in r.states(f0 - 300, f1 + 2):
        f = s["f"]
        ws = backend.feed(s)
        if last_f is not None and last_f < f0 <= f:
            mf.notify_wake(ws.stamp.t_game_s, wave)
        last_f = f
        in_fight = f0 <= f <= f1 and ws.hero is not None and ws.hero.pos is not None
        # ---- recorded events at this frame, checked on the state before it (frame k - 1) ----
        kills, redirects = [], []
        if in_fight and ws_prev is not None and ws_prev.hero is not None and ws_prev.hero.pos is not None:
            for ev in ws.events:
                d = ev.data
                if d is None:
                    continue
                if ev.kind == Ev.ENEMY_KILLED or (ev.kind == Ev.HIT_DEALT and getattr(d, "killing", False)):
                    tr = mf.trackers.get(d.target_id)
                    if tr is not None and not tr.dead and d.target_id not in kills:
                        kills.append(d.target_id)
                elif ev.kind == Ev.FSM_TRANSITION and d.enemy_id in mf.trackers:
                    tr = mf.trackers[d.enemy_id]
                    if d.fsm == tr.table.spec.control_fsm and d.to_state in tr.table.spec.death_states \
                            and not tr.dead and d.enemy_id not in kills:
                        kills.append(d.enemy_id)
            for e in ws.entities:
                h = mf.hazards.h.get(e.id)
                if h is None or h.tk != BELL or hazard_type(e) != BELL:
                    continue
                st = e.fsm[0][1] if e.fsm else None
                if st == "Nail Hit" and h.state != "Nail Hit":
                    dd = _haz_dir(float(e.vel.v[0]), float(e.vel.v[1])) if e.vel.conf > 0 else None
                    redirects.append((e.id, dd))
        if kills or redirects:
            a = time.perf_counter()
            Fp = mf.forecast(H_S + 0.1)
            for v in kills:
                kill_whatif("kill (recorded, what-if)", ws_prev, f - 1, Fp, v)
            for iid, dd in redirects:
                if dd is None:
                    stats["redirect (recorded, what-if)/near"]["direction unknown"] += 1
                    continue
                redirect_whatif("redirect (recorded, what-if)", ws_prev, Fp, iid, dd)
            t_ms.append(1e3 * (time.perf_counter() - a))
            prev_F, prev_T = Fp, mf.t
        mf.update(ws)
        if kills and prev_F is not None:
            # the forecast after the kill against the one before it, on the dead enemy's support and the entries
            Fk = mf.forecast(H_S + 0.1)
            dt = mf.t - prev_T
            hx, hy = ws.hero.pos.v
            for zone, (rad, step) in (("near", (NEAR_U, NEAR_STEP)), ("wide", (WIDE_U, WIDE_STEP))):
                X, Y = _grid(hx, hy, rad, step)
                before = prev_F.occupied(X, Y, TK + dt)
                for v in kills:
                    tr = mf.trackers[v]
                    after = Fk.occupied_only(X, Y, TK, {v} | _entry_ids())
                    viol = after & ~before
                    cls = _classify_kill(Fk, v, X, Y, TK, viol, _waiting(mf)) if viol.any() else Counter()
                    note("kill (recorded, after vs before)", zone, viol, cls,
                         {"f": f, "victim": tr.tk, "hero": [round(hx, 2), round(hy, 2)]})
        # ---- simulated actions on the sampled frames ----
        if in_fight and (f - f0) % every == 0:
            a = time.perf_counter()
            F = None
            for v, tr in list(mf.trackers.items()):
                if not tr.dead and tr.in_play and tr.pos is not None:
                    F = F if F is not None else mf.forecast(H_S + 0.1)
                    kill_whatif("kill (simulated)", ws, f, F, v)
            hx, hy = ws.hero.pos.v
            for iid, h in list(mf.hazards.h.items()):
                if h.tk != BELL or h.last_T < mf.t - 0.05 or abs(h.pos[0] - hx) > job["bell_near"] \
                        or abs(h.pos[1] - hy) > job["bell_near"]:
                    continue
                F = F if F is not None else mf.forecast(H_S + 0.1)
                dirs = [1 if h.pos[0] >= hx else -1]
                if h.pos[1] < hy - 0.5:
                    dirs.append(0)
                if h.pos[1] > hy + 0.5:
                    dirs.append(2)
                for dd in dirs:
                    redirect_whatif("redirect (simulated)", ws, F, iid, dd)
            t_ms.append(1e3 * (time.perf_counter() - a))
        ws_prev = ws
        prev_T = mf.t
        prev_F = None
    return {"id": job["id"], "stats": {k: dict(v) for k, v in stats.items()}, "examples": examples,
            "ms_per_sample": round(float(np.mean(t_ms)), 2) if t_ms else None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fights", type=Path, default=Path("C:/ssbot/data/m2_forum_r0/fresh/fights.json"))
    ap.add_argument("--max-fights", type=int, default=0)
    ap.add_argument("--skip", type=int, default=0)
    ap.add_argument("--ids", nargs="+", default=None, help="only these fights")
    ap.add_argument("--every", type=int, default=30)
    ap.add_argument("--frames", type=int, default=0, help="only the first N frames of each fight")
    ap.add_argument("--bell-near", type=float, default=4.0)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    fl = json.loads(a.fights.read_text("utf-8"))["fights"][a.skip:]
    if a.ids:
        fl = [f for f in fl if f["id"] in a.ids]
    if a.max_fights:
        fl = fl[:a.max_fights]
    jobs = [{"id": f["id"], "path": f["path"], "f0": f["f0"], "f1": f["f1"], "every": a.every,
             "bell_near": a.bell_near, "frames": a.frames} for f in fl]
    t0 = time.perf_counter()
    tot: dict = defaultdict(Counter)
    examples: list = []
    errors = []
    if a.workers > 1:
        ex = ProcessPoolExecutor(max_workers=a.workers, initializer=_init_worker)
        it = ex.map(audit_fight, jobs, chunksize=1)
    else:
        _init_worker()
        it = map(audit_fight, jobs)
    for i, res in enumerate(it):
        if "error" in res:
            errors.append(res)
            print(f"[{i + 1}/{len(jobs)}] {res['id']} ERROR {res['error']}", flush=True)
            continue
        for k, v in res["stats"].items():
            tot[k].update(v)
        examples += res["examples"]
        near = {k: v.get("violating checks", 0) for k, v in tot.items() if k.endswith("/near")}
        print(f"[{i + 1}/{len(jobs)}] {res['id']} near violations {near} ({res['ms_per_sample']} ms/sample, "
              f"{time.perf_counter() - t0:.0f} s)", flush=True)
    from ssbot.record.recorder import find_repo_root, git_info
    out = {"fights": len(jobs), "every": a.every, "window_s": H_S, "near_u": NEAR_U, "wide_u": WIDE_U,
           "stats": {k: dict(v) for k, v in sorted(tot.items())}, "errors": errors[:20],
           "examples": examples[:600], "elapsed_s": round(time.perf_counter() - t0, 1),
           "code": git_info(find_repo_root())}
    print(json.dumps(out["stats"], indent=1))
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(out, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
