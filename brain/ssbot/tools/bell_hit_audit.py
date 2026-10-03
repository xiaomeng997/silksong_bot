"""Property test of the known-effect invariant on recordings (M2 plan 2026-10-02; train/bell_hit_monitor.py): for every
drop bell the hero tinked in a recorded fight, in the oracle view and in the vision view (filter with the dust cues,
SimpleNoise, the WorldState k frames late), the danger zone the bell leaves around the hero in the 1 s after the tink,
once the view has had EVAL_LAG_S to see it, must not exceed the untouched bell's (the same bell's exact path from the
last forecast before the tink). Violations are model errors to fix, not hits for the planner to avoid.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.bell_hit_audit C:/ssbot/data/runs/m2/<run> [<run> ...]
        [--views oracle,degraded_dust] [--max-fights 0] [--noise-seed 1] [--json out.json]

Every recorded frame goes through the view's backend and its Forecaster (as PlannerPolicy builds it: margin, dust
cues, hurtbox table); a forecast is made on every frame from 0.5 s before to 1.2 s after a recorded tink (the frames
the monitor needs) and every 6th frame otherwise. Fights without a tink are skipped.
"""
import argparse
import json
import math
import random
import sys
from collections import Counter
from pathlib import Path


def _tink_frames(reader, f0: int, f1: int) -> list[int]:
    from ssbot.train.bell_hit_monitor import tinks_of
    return [s["f"] for s in reader.states(f0, f1, keys=("f", "ev")) if tinks_of(s)]


def run_fight(row: dict, run: Path, view: str, noise_seed: int, model, tpls, mon_stats: Counter, cases: list) -> None:
    from ssbot.backends.degraded import DegradedOracleBackend
    from ssbot.backends.observability import ObservabilityFilter
    from ssbot.backends.oracle_backend import OracleBackend
    from ssbot.combat.forecast import Forecaster, load_box_margin, load_hurtbox
    from ssbot.core.bosses import BELL_BEAST
    from ssbot.core.worldstate import ORACLE, VISION_EQUIVALENT
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.postmortem import find_recording
    from ssbot.train.bell_hit_monitor import BellHitMonitor
    from ssbot.train.planner_policy import COMFORT, HORIZON_S, MARGIN_ORACLE, NOISE_K, TELL_ONSET, TELLS

    r = RecordingReader(find_recording(run, row))
    f1 = row["f_end"]
    f0 = f1 - row["acts"]
    tinks = _tink_frames(r, f0, f1)
    if not tinks:
        return
    if view == "oracle":
        margin, fview = MARGIN_ORACLE, ORACLE
        backend = OracleBackend(bosses=[BELL_BEAST])
    else:
        from ssbot.backends.noise_simple import SIGMA_HERO_U, SIGMA_POS_U
        from ssbot.core.worldstate import Kind
        sg = NOISE_K * math.hypot(SIGMA_HERO_U, SIGMA_POS_U[Kind.BOSS])
        margin, fview = (MARGIN_ORACLE[0] + sg, MARGIN_ORACLE[1] + sg), VISION_EQUIVALENT
        backend = DegradedOracleBackend(OracleBackend(bosses=[BELL_BEAST]),
                                        ObservabilityFilter(bosses=[BELL_BEAST], tells=TELLS[view],
                                                            tell_onset=TELL_ONSET))
        backend.reset(noise_seed)
    fc = Forecaster(model, fview, margin=margin, templates=tpls(margin), comfort=COMFORT)
    fc.bell_tells = view == "degraded_dust"
    if fview != ORACLE:
        fc.hurtbox = load_hurtbox()
        fc.box_margin = load_box_margin() or {}
    fc.reset()
    dense = set()
    for ft in tinks:
        dense.update(range(ft - 30, ft + 72))
    mon = BellHitMonitor()
    raws: list[dict] = []
    for s in r.states(f0, f1):
        ws = backend.feed(s)
        raws.append(s)
        if ws is None:
            continue
        fc.update(ws)
        fo = ws.stamp.frame
        if s["f"] in dense or s["f"] % 6 == 0:
            f = fc.forecast(HORIZON_S)
            mon.on_tick(f, fo, ws.stamp.t_game_s, raws)
            raws = []
    st = mon.stats()
    for k in ("tinks", "skipped", "evaluated", "violations", "over_template"):
        mon_stats[k] += st[k]
    for c in mon.cases:
        cases.append(dict(c, fight=f"{run.name}/i{row.get('instance')}/ep{row.get('episode')}", view=view))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+", type=Path)
    ap.add_argument("--views", default="oracle,degraded_dust")
    ap.add_argument("--max-fights", type=int, default=0)
    ap.add_argument("--noise-seed", type=int, default=1)
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    from ssbot.combat.boss_model import BossModel
    from ssbot.combat.forecast import load_planner_templates
    from ssbot.tools.postmortem import episode_rows
    model = BossModel.load("BellBeast")
    cache: dict = {}

    def tpls(margin):
        if margin not in cache:
            cache[margin] = load_planner_templates(model, margin)
        return cache[margin]

    out: dict = {}
    for view in (v for v in a.views.split(",") if v):
        stats: Counter = Counter()
        cases: list = []
        n = 0
        for run in a.runs:
            for ap_ in sorted(run.glob("attempts_i*.jsonl")):
                inst = int(ap_.stem.split("_i")[1])
                for ep, row in enumerate(episode_rows(run, inst)):
                    if not row.get("recording") or row.get("outcome") == "HARNESS_FAIL":
                        continue
                    if a.max_fights and n >= a.max_fights:
                        break
                    seed = random.Random(a.noise_seed * 7919 + 1000 * inst + ep).randrange(1 << 30)
                    run_fight(row, run, view, seed, model, tpls, stats, cases)
                    n += 1
                    print(f"[{view}] {n} i{inst} ep{ep}: {dict(stats)}", flush=True)
        out[view] = {"fights": n, **dict(stats), "violation_cases": [c for c in cases if c["violation"]][:30],
                     "over_template_cases": [c for c in cases if c["over_template"]][:30],
                     "sample": cases[:10]}
    print(json.dumps({v: {k: x for k, x in d.items() if not k.endswith("cases") and k != "sample"}
                      for v, d in out.items()}, indent=1))
    if a.json:
        a.json.write_text(json.dumps(out, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
