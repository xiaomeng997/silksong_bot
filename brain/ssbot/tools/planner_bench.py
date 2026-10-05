"""Planner tick latency on logged fights (M2 W4 stage A; DESIGN §3.5.4 budget p99 <= 3 ms per tick): replay a recording
through OracleBackend, StateTracker, the forecaster, the tactics and the planner (open loop: the logged actions drive
the game, the planner only plans) and time every tick.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.planner_bench C:/ssbot/data/runs/m2/<run>/rec/<date>/TRAIN/i2_002
        [--frames 20000] [--start F] [--threads 4] [--view oracle|ve] [--json out.json]

Reports p50 / p99 / max of the whole tick (forecast + tactics + planner) and of each planner phase, the share of
ticks with FORCED_RISK and the modes. The first 50 ticks (numba compilation, caches) are left out.

Forum (round R0 scaffold, forum_bench): ../scripts/uv.cmd run python -m ssbot.tools.planner_bench --encounter Forum
    --cache C:/ssbot/data/m2_forum_r0/cache --extra C:/ssbot/data/m2_forum_r0/build_all/extra
    --fight <run>/i<n>/ep<k> [--start F] [--frames 4000] [--n 400] [--T 36] [--threads 4]
"""
import argparse
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np


def idle_tube_hits(s, T: float, tk: np.ndarray, x: np.ndarray, y: np.ndarray, g: list[float], v_top: float,
                   hulls: dict) -> np.ndarray:
    """[n, steps] candidate centres inside an idle subject's body tube (forum_support.SubjectRecall.in_idle_tube,
    vectorised over the steps; past the calibrated bins the growth goes on at the type's top speed)."""
    from ssbot.knowledge import hitbox_tables as hb
    from ssbot.knowledge.forum_support import tube_bin
    b = s.seen_box
    if b is None:
        rel = hulls.get(s.tk)
        if rel is None:
            return np.zeros(x.shape, bool)
        b = (s.pos[0] + rel[0], s.pos[1] + rel[1], s.pos[0] + rel[2], s.pos[1] + rel[3])
    dt = (T - s.seen_T) + tk
    k = tube_bin(dt)
    n = len(g) - 1
    gr = np.where(k <= n, np.asarray(g)[np.minimum(k, n)], g[-1] + v_top * (k - n) * hb.BIN_S)
    vx, vy = (0.0 if math.isnan(v) else v for v in s.vel)
    hx, hy = hb.HERO_HALF_U[0] + gr, hb.HERO_HALF_U[1] + gr
    return (x >= b[0] + vx * dt - hx) & (x <= b[2] + vx * dt + hx) & (y >= b[1] + vy * dt - hy) & \
        (y <= b[3] + vy * dt + hy)


def forum_bench(a: argparse.Namespace) -> int:
    """--encounter Forum (round R0 scaffold; the planner has no multi-enemy forecast before round R2): replay a
    fight's cache (ssbot.tools.forum_extract) open loop through the enemies' trackers and, every tick, time what the
    planner's support phase will cost on real Forum walks: every subject's support placements at horizon 0.8 s
    (forum_support.SubjectRecall.placements_of, the fold's tables with the other fold's held-out margins; anchors of
    attacks that start later every 0.2 s), one SupportQuery over all of them and a planner-sized batch of hero
    centre paths (--n candidates x --T steps: ballistic fans from the hero, ssbot.combat.fastquery.query_par). Reports
    p50 / p99 / max of each phase, the placements per tick and the share of ticks where every candidate path meets the
    support (an upper bound of FORCED_RISK for this crude candidate set)."""
    import numba

    from ssbot.combat.fastquery import query_par
    from ssbot.knowledge.forum_cache import cache_name, load_cache
    from ssbot.knowledge.forum_support import FoldTables, SubjectRecall, SubjectTracker, margins_from_contacts, \
        read_contacts, replay

    numba.set_num_threads(a.threads)
    rows = read_contacts(a.extra / "contacts.jsonl.gz")
    growth, speeds, hulls = None, {}, {}
    skip: set = set()
    if a.idle_growth is not None:
        # the idle body tube (support_recall --write-margins: production_tubes): idle enemies by their body as last
        # seen instead of their idle templates; past the calibrated bins the growth goes on at the type's top speed
        from ssbot.knowledge.gauntlet_tables import FORUM_SPECS
        doc = json.loads(a.idle_growth.read_text("utf-8"))["production_tubes"]
        growth, speeds, hulls = doc["idle_growth"], doc["tube_speed"], doc["body_hull"]
        skip = {sp.idle_family for sp in FORUM_SPECS.values()}
    rec = SubjectRecall(FoldTables(a.extra, a.fold, margins=margins_from_contacts(rows, fold=1 - a.fold,
                                                                                  skip_families=skip),
                                   base=a.margin), idle_growth=growth)
    rec.body_rel = {k: tuple(v) for k, v in hulls.items()}
    q = rec.t.query
    cache = load_cache(a.cache / cache_name(a.fight))
    side = int(round(math.sqrt(a.n)))
    vx = np.repeat(np.linspace(-9.0, 9.0, side), side)
    vy = np.tile(np.linspace(-12.0, 16.0, side), side)
    tk = np.arange(a.T + 1, dtype=np.float64) / 60.0
    tr = SubjectTracker()
    t_track, t_fc, t_q, n_pl, forced, n_tubes = [], [], [], [], 0, []
    t_prev = time.perf_counter()
    n = 0
    i0 = int(np.searchsorted(cache["f"], a.start)) if a.start is not None else 0
    for i, f, T in replay(cache, tr):
        t1 = time.perf_counter()
        if i < i0:
            t_prev = time.perf_counter()
            continue
        n += 1
        if n > a.frames:
            break
        pl = []
        tubes = []
        for s in tr.subjects.values():
            if s.state is not None:
                pl += rec.placements_of(s, T, 0.8 + 1e-6, anchor_step=12)
                if growth is not None and rec.idle_tube_ok(s, T):
                    tubes.append(s)
        t2 = time.perf_counter()
        hx = float(0.5 * (cache["hbox"][i, 0] + cache["hbox"][i, 2]))
        hy = float(0.5 * (cache["hbox"][i, 1] + cache["hbox"][i, 3]))
        x = hx + vx[:, None] * tk[None, :]
        y = np.maximum(hy + vy[:, None] * tk[None, :] - 0.5 * 50.0 * tk[None, :] ** 2, 4.05)
        q.clear()
        for key, t_ref, anchor, mirror in pl:
            q.place(key, t_ref, anchor, mirror)
        hit = query_par(q, x, y, tk) if pl else np.zeros(x.shape, bool)
        for s in tubes:          # the idle body tubes (box tests per step)
            hit |= idle_tube_hits(s, T, tk, x, y, growth[s.tk], speeds.get(s.tk, 0.0), rec.body_rel)
        n_tubes.append(len(tubes))
        t3 = time.perf_counter()
        if n > 50:
            t_track.append((t1 - t_prev) * 1e3)
            t_fc.append((t2 - t1) * 1e3)
            t_q.append((t3 - t2) * 1e3)
            n_pl.append(len(pl))
            forced += bool(hit.any(axis=1).all())
        t_prev = time.perf_counter()
    q_ = lambda v: {"p50": round(float(np.percentile(v, 50)), 3), "p99": round(float(np.percentile(v, 99)), 3),  # noqa
                    "max": round(float(np.max(v)), 3)} if v else {}
    out = {"encounter": "Forum", "fight": a.fight, "ticks": len(t_fc), "candidates": side * side, "steps": a.T,
           "track_ms": q_(t_track), "placements_ms": q_(t_fc), "query_ms": q_(t_q),
           "tick_ms": q_([x + y + z for x, y, z in zip(t_track, t_fc, t_q)]), "placements": q_(n_pl),
           "idle_body_tubes": q_(n_tubes[-len(n_pl):] if n_pl else []), "idle_growth": str(a.idle_growth),
           "all_candidates_meet_support_share": round(forced / max(1, len(t_fc)), 4), "threads": a.threads}
    print(json.dumps(out, indent=1))
    if a.json:
        a.json.write_text(json.dumps(out, indent=1), "utf-8")
    return 0


def _forum_prefs(tac, ws, fc):
    """Today's planner has no Forum tactics (R3/R6): HOLD where the hero stands, the playbook's weights, the risk map
    over the Forum floor from the MultiForecast (Tactics.risk_map's weighting)."""
    from ssbot.combat.tactics.modes import HOLD, TacticPrefs
    from ssbot.core.forum import FLOOR_Y, WALL_L, WALL_R
    from ssbot.knowledge import hitbox_tables as hb
    xs = np.arange(WALL_L + 0.5, WALL_R - 0.5 + 1e-9, 0.5)
    tk = np.arange(0, 61, 2) / 60.0
    occ = fc.occupied(np.repeat(xs[:, None], len(tk), 1), np.full((len(xs), len(tk)), FLOOR_Y + hb.HERO_HALF_U[1]),
                      tk)
    w = 1.0 / (1.0 + tk)
    return TacticPrefs(HOLD, float(ws.hero.pos.v[0]), dict(tac.pb.weights), risk_x=xs, risk=(occ * w).sum(axis=1) /
                       w.sum())


def forum_multi_bench(a: argparse.Namespace) -> int:
    """--encounter Forum --multi (round R2): replay a fight's recording through OracleBackend and the run-time
    MultiForecaster (production tables: knowledge/.../forum/*_hitboxes.npz + support_margins.json) and time every
    tick's update and forecast(--horizon) (acceptance (d): the wave-6 replay, target p99 <= 3 ms), with --planner
    today's planner and tactics fed by the MultiForecast (acceptance (g): no Forum planner changes, R3), and the
    process memory (acceptance (e): <= 1.5 GB). --wave N picks the frames of wave N from the fight's cache (room.battles
    there: the test truth, used only to choose the segment). The machine's load is sampled while it runs."""
    import os

    import numba
    import psutil

    from ssbot.backends.oracle_backend import OracleBackend
    from ssbot.combat.enemy_tables import EnemyTables
    from ssbot.combat.multi_forecast import MultiForecaster
    from ssbot.record.recorder import RecordingReader

    numba.set_num_threads(a.threads)
    proc = psutil.Process()
    fl = {f["id"]: f for f in json.loads(a.fights_list.read_text("utf-8"))["fights"]}
    fight = fl[a.fight]
    f0, f1 = int(fight["f0"]), int(fight["f1"])
    start = a.start
    if a.wave is not None:
        from ssbot.knowledge.forum_cache import cache_name, load_cache
        c = load_cache((a.cache or Path("C:/ssbot/data/m2_forum_r0/cache")) / cache_name(a.fight))
        w = c["wave"] % 100
        idx = np.flatnonzero((w == a.wave) & (c["wave"] >= 0))
        if not len(idx):
            raise SystemExit(f"wave {a.wave} not in {a.fight}")
        start = int(c["f"][idx[0]])
        stop = int(c["f"][idx[-1]])
        n_frames = min(a.frames, stop - start + 1) if a.frames else stop - start + 1
    else:
        start = start if start is not None else f0
        n_frames = a.frames
    rss0 = proc.memory_info().rss
    t0 = time.perf_counter()
    tables = EnemyTables.production()
    t_load = time.perf_counter() - t0
    mf = MultiForecaster(tables)
    t0 = time.perf_counter()
    nw = mf.warm()
    t_warm = time.perf_counter() - t0
    rss_tables = proc.memory_info().rss
    peak_warm = getattr(proc.memory_info(), "peak_wset", 0)
    peak_series = []
    planner = tac = trk = None
    if a.planner:
        from ssbot.combat.planner import Planner, PlannerConfig
        from ssbot.combat.safety_filter import FilterContext
        from ssbot.combat.tactics import Tactics, load_playbook
        from ssbot.knowledge.kinematics import HeroParams, HoldState, StateTracker, Terrain2D
        params = HeroParams.load()
        r0 = RecordingReader(fight["path"])
        terrain = None
        for _, m in r0.terrain():
            if (m.get("scene_raw") or m.get("scene")) in ("Hang_04", "Hang_04_boss"):
                terrain = Terrain2D.from_message(m, params.scene("Hang_04"))
        terrain = terrain or Terrain2D.empty()
        planner = Planner(params, terrain, PlannerConfig(threads=a.threads))
        tac = Tactics(load_playbook())
        trk = StateTracker(params, terrain)
    backend = OracleBackend()
    r = RecordingReader(fight["path"])
    t_up, t_fc, t_tick, n_pl, n_bb, n_sub, forced = [], [], [], [], [], [], 0
    n_fine, n_win = [], []
    phases: dict = {}
    load_samples = []
    psutil.cpu_percent(None)
    n = 0
    prev = None
    for s in r.states(f0 - 300, start + n_frames):
        ws = backend.feed(s)
        if s["f"] == f0:
            mf.notify_wake(ws.stamp.t_game_s)
        a0 = time.perf_counter()
        mf.update(ws)
        a1 = time.perf_counter()
        if trk is not None:
            trk.push(s)
        if s["f"] < start or not s.get("hero"):
            prev = s
            continue
        fc = mf.forecast(a.horizon)
        a2 = time.perf_counter()
        n += 1
        if planner is not None and prev is not None:
            prefs = _forum_prefs(tac, ws, fc)
            ctx = FilterContext.from_world(ws, None, 3, want_bind=prefs.want_bind)
            hold = HoldState.from_act(prev.get("act"))
            prefix = np.array([int((s.get("act") or {}).get("mask") or 0)])
            res = planner.tick(ws, trk.state(), hold, prefix, fc, prefs, ctx)
            a3 = time.perf_counter()
            if n > 50:
                t_tick.append((a3 - a0) * 1e3)
                for k, v in res.t_ms.items():
                    phases.setdefault(k, []).append(v)
                forced += res.forced_risk
        if n > 50:
            t_up.append((a1 - a0) * 1e3)
            t_fc.append((a2 - a1) * 1e3)
            n_pl.append(len(fc.placements))
            n_fine.append(fc.n_fine)
            n_win.append(fc.n_window)
            n_bb.append(fc.n_bbox)
            n_sub.append(sum(1 for x in fc.subjects if x.alive and x.in_play))
        if n % 200 == 0:
            load_samples.append(psutil.cpu_percent(None))
            peak_series.append((n, round(getattr(proc.memory_info(), "peak_wset", 0) / 1e6)))
        prev = s
    q_ = lambda v: {"p50": round(float(np.percentile(v, 50)), 3), "p99": round(float(np.percentile(v, 99)), 3),  # noqa
                    "max": round(float(np.max(v)), 3)} if v else {}
    others = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info", "cmdline"]):
        try:
            if p.info["name"] and p.info["name"].lower().startswith(("python", "hollow", "silksong")) \
                    and p.pid != os.getpid():
                others.append(p.info["name"])
        except Exception:
            pass
    out = {"encounter": "Forum", "mode": "multi", "fight": a.fight, "wave": a.wave, "start": start,
           "ticks": len(t_fc), "horizon_s": a.horizon, "threads": a.threads,
           "update_ms": q_(t_up), "forecast_ms": q_(t_fc), "tick_ms": q_(t_tick),
           "planner_phases_ms": {k: q_(v) for k, v in phases.items()},
           "forced_risk_share": round(forced / max(1, len(t_tick)), 4) if t_tick else None,
           "placements": q_(n_pl), "bbox_placements": q_(n_bb), "enemies_in_play": q_(n_sub),
           "tables_load_s": round(t_load, 1), "warm_s": round(t_warm, 1), "warm_templates": nw,
           "rss_mb": {"before": round(rss0 / 1e6), "tables": round(rss_tables / 1e6),
                      "end": round(proc.memory_info().rss / 1e6), "peak": round(proc.memory_info().peak_wset / 1e6)
                      if hasattr(proc.memory_info(), "peak_wset") else None,
                      "peak_after_warm": round(peak_warm / 1e6),
                      "peak_jumps": [x for i, x in enumerate(peak_series)
                                     if i == 0 or x[1] > peak_series[i - 1][1] + 20]},
           "store_mb": round(tables.store.nbytes() / 1e6),
           "placements_by_kind": {"fine": q_(n_fine), "window": q_(n_win), "bbox": q_(n_bb)},
           "machine_cpu_percent": q_(load_samples), "other_processes": dict(Counter(others)),
           "cpu_count": psutil.cpu_count()}
    print(json.dumps(out, indent=1))
    if a.json:
        a.json.write_text(json.dumps(out, indent=1), "utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recording", type=Path, nargs="?")
    ap.add_argument("--encounter", default="BellBeast", choices=("BellBeast", "Forum"))
    ap.add_argument("--cache", type=Path, default=None, help="Forum: the forum_extract caches")
    ap.add_argument("--extra", type=Path, default=None, help="Forum: the build's --extra directory")
    ap.add_argument("--fight", default="", help="Forum: the fight id (<run>/i<n>/ep<k>)")
    ap.add_argument("--fold", type=int, default=0, help="Forum: the tables' fold")
    ap.add_argument("--margin", type=float, default=0.0, help="Forum: base margin added to every template (u)")
    ap.add_argument("--n", type=int, default=400, help="Forum: candidate paths")
    ap.add_argument("--T", type=int, default=36, help="Forum: steps per candidate path")
    ap.add_argument("--frames", type=int, default=20000)
    ap.add_argument("--start", type=int, default=None)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--view", default="oracle")
    ap.add_argument("--idle-growth", type=Path, default=None,
                    help="Forum: a support_margins.json with production_tubes: idle enemies by the idle body tube")
    ap.add_argument("--multi", action="store_true", help="Forum: the run-time MultiForecaster on the recording (R2)")
    ap.add_argument("--fights-list", type=Path, default=Path("C:/ssbot/data/m2_forum_r0/build_all/fights.json"))
    ap.add_argument("--wave", type=int, default=None, help="Forum --multi: the frames of this wave")
    ap.add_argument("--horizon", type=float, default=2.0, help="Forum --multi: the forecast's horizon (s)")
    ap.add_argument("--planner", action="store_true", help="Forum --multi: today's planner and tactics too")
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    if a.encounter == "Forum" and a.multi:
        if not a.fight:
            ap.error("--multi needs --fight")
        return forum_multi_bench(a)
    if a.encounter == "Forum":
        if a.cache is None or a.extra is None or not a.fight:
            ap.error("--encounter Forum needs --cache, --extra and --fight")
        return forum_bench(a)
    if a.recording is None:
        ap.error("a recording is needed")

    import numba

    from ssbot.backends.observability import ObservabilityFilter
    from ssbot.backends.oracle_backend import OracleBackend
    from ssbot.combat.boss_model import BossModel
    from ssbot.combat.forecast import Forecaster
    from ssbot.combat.planner import Planner, PlannerConfig
    from ssbot.combat.safety_filter import FilterContext
    from ssbot.combat.tactics import Tactics, load_playbook
    from ssbot.core.bosses import BELL_BEAST
    from ssbot.core.worldstate import ORACLE, VISION_EQUIVALENT
    from ssbot.knowledge.kinematics import HeroParams, HoldState, StateTracker, Terrain2D
    from ssbot.record.recorder import RecordingReader

    numba.set_num_threads(a.threads)
    r = RecordingReader(a.recording)
    params = HeroParams.load()
    terrain = None
    for _, m in r.terrain():
        if m.get("scene_raw") == "Bone_05" or m.get("scene") == "Bone_05":
            terrain = Terrain2D.from_message(m, params.scene("Bone_05"))
    terrain = terrain or Terrain2D.empty()
    model = BossModel.load()
    view = ORACLE if a.view == "oracle" else VISION_EQUIVALENT
    fc = Forecaster(model, view, margin=(0.15, 0.25), comfort=(0.25, 0.25))
    fc.no_hurtbox, fc.shape_from = load_playbook().no_hurtbox, load_playbook().shape_from
    pb = load_playbook()
    tac = Tactics(pb)
    planner = Planner(params, terrain, PlannerConfig(threads=a.threads))
    backend = OracleBackend(bosses=[BELL_BEAST])
    filt = ObservabilityFilter(bosses=[BELL_BEAST]) if view != ORACLE else None
    trk = StateTracker(params, terrain)
    f0 = a.start if a.start is not None else r.index("state")[0].get("f0", 0)
    totals, phases, modes, forced, names = [], {}, Counter(), 0, Counter()
    n = 0
    prev = None
    for s in r.states(f0, f0 + a.frames + 1):
        if prev is None:
            prev = s
            continue
        ws = backend.feed(prev)
        if filt is not None:
            ws = filt.apply(ws)
        trk.push(prev)
        if ws.game.scene.v != "Bone_05" or not prev.get("hero"):
            prev = s
            continue
        t0 = time.perf_counter()
        fc.update(ws)
        f = fc.forecast(2.0)
        prefs = tac.decide(ws, f, None, 3)
        ctx = FilterContext.from_world(ws, None, 3, want_bind=prefs.want_bind)
        hold = HoldState.from_act(prev.get("act"))
        prefix = np.array([int((s.get("act") or {}).get("mask") or 0)])
        res = planner.tick(ws, trk.state(), hold, prefix, f, prefs, ctx)
        dt = (time.perf_counter() - t0) * 1e3
        n += 1
        if n > 50:
            totals.append(dt)
            for k, v in res.t_ms.items():
                phases.setdefault(k, []).append(v)
            modes[prefs.mode] += 1
            forced += res.forced_risk
            names[res.name.split("+")[0]] += 1
        prev = s
    q = lambda v: {"p50": round(float(np.percentile(v, 50)), 3), "p99": round(float(np.percentile(v, 99)), 3),  # noqa
                   "max": round(float(np.max(v)), 3)} if v else {}
    out = {"ticks": len(totals), "tick_ms": q(totals), "phases_ms": {k: q(v) for k, v in phases.items()},
           "forced_risk_share": round(forced / max(1, len(totals)), 4), "modes": dict(modes),
           "first_primitives": dict(names.most_common(12)), "threads": a.threads, "view": a.view}
    print(json.dumps(out, indent=1))
    if a.json:
        a.json.write_text(json.dumps(out, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
