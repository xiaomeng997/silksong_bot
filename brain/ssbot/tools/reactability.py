"""Reactability of the Bell Beast's attacks from each floor position (M2 stage C; DESIGN §3.5.3 "reactable"): for
every attack branch the boss can choose underground, a planner tick d frames after the boss is first drawn (the
vision-equivalent view's first sight of it), the hero standing idle at x. S = 0 means some plan escapes; otherwise
the attack is unreactable there and only the stance avoids it.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.reactability [--delay 4] [--json out.json]

Branches: a charge or a leap from either anchor (first drawn in Charge Emerge / Leap Out), a burst at x 81.25-90.75
(uniform in 81.21-91.21, first drawn in Burst Out; 20 slices) and the rage burst at 86.21. The expected unreactable
share at x weighs them with the decision chain's shares (burst 0.262 in P1, 0.414 in P2; charge and leap halves of
the rest, each anchor half of that). Synthetic Bone_05 floor and gates, margins 0.15 / 0.25 u (PlannerPolicy oracle).

Result (2026-10-02, d = 4 frames, the DelayLine's longest delay): a charge is unreactable from x <= 80.5 (left
anchor) / >= 90 (right), a leap from <= 82.5 / >= 88, a burst within bx - 3.75 .. bx + 4.0, the rage burst at
84-88.5. The expected share is lowest at x 83 (0.157 P1 / 0.248 P2) against 0.21 / 0.33 at the oracle view's
hidden stance 85.5: playbook stance.hidden_x_vision.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

MARGIN = (0.15, 0.25)
P_BURST = {"P1": 0.262, "P2": 0.414}


def table(delay: int, threads: int = 8) -> tuple[np.ndarray, list[str], np.ndarray]:
    """[branches, x] S of the chosen plan (1: unreactable), branch names, x grid."""
    from ssbot.combat.boss_model import Anchor, BossModel
    from ssbot.combat.forecast import Ctx, Forecaster, Root, load_planner_templates
    from ssbot.combat.planner import Planner, PlannerConfig
    from ssbot.combat.safety_filter import FilterContext
    from ssbot.combat.tactics import Tactics, load_playbook
    from ssbot.core.worldstate import ORACLE, E, WorldState
    from ssbot.knowledge import kinematics as kin

    m = BossModel.load()
    tpls = load_planner_templates(m, MARGIN)
    params = kin.HeroParams.load()
    arena = kin.Terrain2D.from_boxes([(60.0, 0.0, 110.0, 2.0), (67.2, 0.0, 69.2, 14.0), (102.0, 0.0, 104.0, 14.0)])
    planner = Planner(params, arena, PlannerConfig(threads=threads))
    tac = Tactics(load_playbook())
    branches = []
    for fam, st in (("BB_CHARGE", "Charge Emerge"), ("BB_LEAP", "Leap Out")):
        for d in ("Set L", "Set R"):
            branches.append((f"{fam[3:]} {d}", st, Ctx(fam, d, m.anchor(fam, d), "P1", False)))
    for bx in np.arange(81.25, 91.21, 0.5):
        branches.append((f"BURST {bx:.2f}", "Burst Out", Ctx("BB_BURST", None, Anchor(float(bx), 5.49, 1), "P1",
                                                              False)))
    branches.append(("RAGE", "Rage Burst", Ctx("BB_RAGE", "-", m.anchor("BB_RAGE", "-"), "P1", False)))
    xs = np.arange(70.0, 101.21, 0.5)
    out = np.zeros((len(branches), len(xs)), np.int8)
    tau = delay * params.frame_time
    for b, (_, st, ctx) in enumerate(branches):
        fc = Forecaster(m, ORACLE, margin=MARGIN, templates=tpls)
        fc.tracker.state, fc.tracker.t_entry = st, -tau
        fc.tracker.roots = lambda origin, st=st, ctx=ctx: ([Root(st, -tau, -tau, ctx, current=True)], True)
        f = fc.forecast(2.0, 0.0)
        for i, x in enumerate(xs):
            ws = WorldState()
            ws.hero.pos = E((float(x), 3.0544))
            ws.res.hp, ws.res.hp_max, ws.res.silk = E(5), E(5), E(5)
            prefs = tac.decide(ws, f, None, 3)
            planner.reset()
            r = planner.tick(ws, kin.initial_state(params, float(x), 2.015 + params.foot), kin.HoldState.idle(1),
                             np.zeros(1, np.int64), f, prefs, FilterContext.from_world(ws, None, 3))
            out[b, i] = int(r.S > 0)
    return out, [n for n, _, _ in branches], xs


def expected(R: np.ndarray, p_burst: float) -> np.ndarray:
    """[x] expected unreactable share: rows charge L/R, leap L/R, 20 burst slices, rage (ignored: one per fight)."""
    pc = (1.0 - p_burst) / 4.0
    return pc * R[:4].sum(axis=0) + p_burst * R[4:24].mean(axis=0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--delay", type=int, default=4)
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    R, names, xs = table(a.delay)
    for n, row in zip(names, R):
        print(f"{n:16s}", "".join("#" if v else "." for v in row))
    print(" " * 17 + "".join(str(int(x) % 10) if x == int(x) else " " for x in xs))
    res = {}
    for ph, pb in P_BURST.items():
        e = expected(R, pb)
        best = np.argsort(e, kind="stable")[:5]
        res[ph] = {"best": [(float(xs[i]), round(float(e[i]), 3)) for i in best],
                   "at_85.5": round(float(e[int(np.searchsorted(xs, 85.5))]), 3)}
        print(ph, res[ph])
    if a.json:
        a.json.write_text(json.dumps({"delay": a.delay, "x": xs.tolist(), "branches": names, "S": R.tolist(),
                                      "expected": res}, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
