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
    rec = SubjectRecall(FoldTables(a.extra, a.fold, margins=margins_from_contacts(rows, fold=1 - a.fold),
                                   base=a.margin))
    q = rec.t.query
    cache = load_cache(a.cache / cache_name(a.fight))
    side = int(round(math.sqrt(a.n)))
    vx = np.repeat(np.linspace(-9.0, 9.0, side), side)
    vy = np.tile(np.linspace(-12.0, 16.0, side), side)
    tk = np.arange(a.T + 1, dtype=np.float64) / 60.0
    tr = SubjectTracker()
    t_track, t_fc, t_q, n_pl, forced = [], [], [], [], 0
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
        for s in tr.subjects.values():
            if s.state is not None:
                pl += rec.placements_of(s, T, 0.8 + 1e-6, anchor_step=12)
        t2 = time.perf_counter()
        hx = float(0.5 * (cache["hbox"][i, 0] + cache["hbox"][i, 2]))
        hy = float(0.5 * (cache["hbox"][i, 1] + cache["hbox"][i, 3]))
        x = hx + vx[:, None] * tk[None, :]
        y = np.maximum(hy + vy[:, None] * tk[None, :] - 0.5 * 50.0 * tk[None, :] ** 2, 4.05)
        q.clear()
        for key, t_ref, anchor, mirror in pl:
            q.place(key, t_ref, anchor, mirror)
        hit = query_par(q, x, y, tk) if pl else np.zeros(x.shape, bool)
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
           "all_candidates_meet_support_share": round(forced / max(1, len(t_fc)), 4), "threads": a.threads}
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
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
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
