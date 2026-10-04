"""Property check of the planner's key economy terms on replayed recordings (M2 plan "key economy": they may only
reorder plans of one safety class, never change Hz / U / S / V / P): every tick of a recording is planned twice from
the same planner state, with the terms on and off (open loop, as ssbot.tools.planner_bench), and the chosen plans'
safety classes (PlanResult.cls: Hz, Hz_soft, U, S, the jump and macro commitments, comfort, V, P, first contact) and
tail results must be identical. The planner state carried on is the "on" one.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.key_cost_check C:/ssbot/data/runs/m2/<run>/rec/<date>/TRAIN/i2_000
        [--frames 6000] [--start F] [--press 0.05] [--change 0.1] [--threads 4] [--json out.json]

Reports the ticks, the class mismatches (must be 0), how often the choice differed, the chosen plans' presses and
plan changes with the terms on and off, and the tick time of both.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

STATE_FIELDS = ("prev_cmd", "prev_name", "ticks", "jump_until", "macro_until", "prev_tail_ok", "prev_d")


def sync(dst, src) -> None:
    for k in STATE_FIELDS:
        v = getattr(src, k)
        setattr(dst, k, v.copy() if isinstance(v, np.ndarray) else v)


def replay(recording: Path, frames: int, start: int | None, press: float, change: float, threads: int,
           scene: str = "Bone_05") -> dict:
    import numba

    from ssbot.backends.oracle_backend import OracleBackend
    from ssbot.combat.boss_model import BossModel
    from ssbot.combat.forecast import Forecaster, load_planner_templates
    from ssbot.combat.planner import Planner, PlannerConfig
    from ssbot.combat.safety_filter import FilterContext
    from ssbot.combat.tactics import Tactics, load_playbook
    from ssbot.core.bosses import BELL_BEAST
    from ssbot.core.worldstate import ORACLE
    from ssbot.knowledge.kinematics import HeroParams, HoldState, StateTracker, Terrain2D
    from ssbot.record.recorder import RecordingReader
    from ssbot.train.planner_policy import COMFORT, MARGIN_ORACLE

    numba.set_num_threads(threads)
    r = RecordingReader(recording)
    params = HeroParams.load()
    terrain = None
    for _, m in r.terrain():
        if m.get("scene_raw") == scene or m.get("scene") == scene:
            terrain = Terrain2D.from_message(m, params.scene(scene))
    terrain = terrain or Terrain2D.empty()
    model = BossModel.load()
    fc = Forecaster(model, ORACLE, margin=MARGIN_ORACLE, templates=load_planner_templates(model, MARGIN_ORACLE),
                    comfort=COMFORT)
    pb = load_playbook()
    fc.no_hurtbox, fc.shape_from = pb.no_hurtbox, pb.shape_from
    tac = Tactics(pb)
    on = Planner(params, terrain, PlannerConfig(threads=threads))
    off = Planner(params, terrain, PlannerConfig(threads=threads))
    on.warm_kernels()
    backend = OracleBackend(bosses=[BELL_BEAST])
    trk = StateTracker(params, terrain)
    f0 = start if start is not None else r.index("state")[0].get("f0", 0)
    out = {"ticks": 0, "class_mismatch": 0, "tail_mismatch": 0, "off_mismatch": 0, "choice_differs": 0,
           "forced": 0, "examples": []}
    kp_on, kc_on, kp_off, kc_off, t_on, t_off = [], [], [], [], [], []
    prev = None
    last_scene_ok = False
    for s in r.states(f0, f0 + frames + 1):
        if prev is None:
            prev = s
            continue
        ws = backend.feed(prev)
        trk.push(prev)
        if ws.game.scene.v != scene or not prev.get("hero"):
            prev = s
            if last_scene_ok:
                on.reset()
            last_scene_ok = False
            continue
        last_scene_ok = True
        fc.update(ws)
        f = fc.forecast(2.0)
        prefs = tac.decide(ws, f, None, 3)
        ctx = FilterContext.from_world(ws, None, 3, want_bind=prefs.want_bind)
        hold = HoldState.from_act(prev.get("act"))
        prefix = np.array([int((s.get("act") or {}).get("mask") or 0)])
        S0 = trk.state()
        sync(off, on)
        w0 = dict(prefs.weights)
        prefs.weights = dict(w0, key_press=0.0, key_change=0.0)
        ta = time.perf_counter()
        ro = off.tick(ws, S0.copy(), hold, prefix, f, prefs, ctx)
        tb = time.perf_counter()
        prefs.weights = dict(w0, key_press=press, key_change=change)
        rn = on.tick(ws, S0.copy(), hold, prefix, f, prefs, ctx)
        tc = time.perf_counter()
        out["ticks"] += 1
        out["forced"] += bool(rn.forced_risk)
        if out["ticks"] > 50:
            t_off.append((tb - ta) * 1e3)
            t_on.append((tc - tb) * 1e3)
        bad = rn.cls != ro.cls or rn.S != ro.S or rn.V != ro.V or rn.P != ro.P or rn.Hz != ro.Hz or rn.U != ro.U \
            or rn.forced_risk != ro.forced_risk
        out["class_mismatch"] += bool(bad)
        out["tail_mismatch"] += bool(rn.tail_ok != ro.tail_ok)
        out["off_mismatch"] += bool(rn.idx_off != ro.idx)
        out["choice_differs"] += bool(rn.idx != ro.idx)
        if (bad or rn.tail_ok != ro.tail_ok) and len(out["examples"]) < 10:
            out["examples"].append({"f": prev["f"], "on": [rn.name, rn.cls, rn.tail_ok],
                                    "off": [ro.name, ro.cls, ro.tail_ok]})
        if ro.cls is not None:
            # the off choice's terms, from the on planner's arrays (same candidates, same state)
            kp_on.append(rn.key_press)
            kc_on.append(rn.key_change)
        prev = s
    q = (lambda v: {"p50": round(float(np.percentile(v, 50)), 3), "p99": round(float(np.percentile(v, 99)), 3)}
         if v else {})
    out.update({"key_press_on_mean": round(float(np.mean(kp_on)), 3) if kp_on else None,
                "key_change_on_mean": round(float(np.mean(kc_on)), 3) if kc_on else None,
                "tick_ms_off": q(t_off), "tick_ms_on": q(t_on), "press": press, "change": change})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recording", type=Path)
    ap.add_argument("--frames", type=int, default=6000)
    ap.add_argument("--start", type=int, default=None)
    ap.add_argument("--press", type=float, default=0.05)
    ap.add_argument("--change", type=float, default=0.1)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    out = replay(a.recording, a.frames, a.start, a.press, a.change, a.threads)
    print(json.dumps(out, indent=1))
    if a.json:
        a.json.write_text(json.dumps(out, indent=1), "utf-8")
    return 1 if out["class_mismatch"] else 0


if __name__ == "__main__":
    sys.exit(main())
