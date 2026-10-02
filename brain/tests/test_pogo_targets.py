"""Registry hit targets (ssbot.combat.pogo_targets): the bells' predicted paths against their recorded flights, and the
planner bouncing off a bell below a falling hero (the bounce accepted only where every timing lane's spike meets the
bell's certain circle)."""
import numpy as np
import pytest

from ssbot.combat import pogo_targets as pt
from ssbot.combat.boss_model import BossModel
from ssbot.combat.forecast import Forecaster, load_planner_templates
from ssbot.combat.planner import Planner, PlannerConfig
from ssbot.combat.safety_filter import FilterContext
from ssbot.combat.tactics import Tactics, load_playbook
from ssbot.core.worldstate import ORACLE, E, Entity, Kind, WorldState
from ssbot.knowledge import kinematics as kin

MARGIN = (0.15, 0.25)


def test_registry_paths_follow_the_recorded_flights():
    reg = {s.prefix: s for s in pt.load_registry()}
    atk, drop = reg["BoneBeast AtkBell"], reg["BoneBeast DropBell"]
    assert "Launch" in atk.states and "Dormant" not in atk.states and "Antic" not in drop.states
    tk = np.arange(121) / 60.0
    # recording 20261001_122249 i0_000: launched at (80.19, 0.95) with (-1, 38); Launched Up 0.25 s later at vy 20.84;
    # First Bounce at y 2.9635 with vx -12, about 1.05 s after the launch
    cx, cy, ok = pt.simulate(atk, 80.19, 0.95, -1.0, 38.0, 0, None, tk)
    assert ok.all()
    land = tk[np.argmax((tk > 0.3) & (np.diff(cx, prepend=cx[0]) < -0.1))]
    assert 0.95 < land < 1.2
    assert abs(cx[-1] - cx[int(land * 60) + 6] + 12.0 * (tk[-1] - tk[int(land * 60) + 6])) < 0.5
    # a drop bell falls straight (vx 0) and its bounce side is random: the path ends at the ground
    cx, cy, ok = pt.simulate(drop, 85.0, 12.0, 0.0, -17.0, 0, None, tk)
    assert ok[:10].all() and not ok[-1] and np.allclose(cx[ok], 85.0)
    # past the attack bell's End Timer the path ends
    cx, cy, ok = pt.simulate(atk, 80.0, 4.0, -12.0, 5.0, 1, 0.5, tk)
    assert ok[tk < 0.49].all() and not ok[tk > 0.55].any()


@pytest.fixture(scope="module")
def setup():
    m = BossModel.load()
    return m, load_planner_templates(m, MARGIN), kin.HeroParams.load(), \
        kin.Terrain2D.from_boxes([(60.0, 0.0, 110.0, 2.0), (67.2, 0.0, 69.2, 14.0), (102.0, 0.0, 104.0, 14.0)])


def _tick(setup, bells, hero_y=7.5, hero_vy=0.0):
    m, tpls, params, arena = setup
    fc = Forecaster(m, ORACLE, margin=MARGIN, templates=tpls)
    fc.tracker.roots = lambda origin: ([], True)
    ws = WorldState()
    ws.hero.pos = E((85.0, hero_y))
    ws.res.hp, ws.res.hp_max, ws.res.silk = E(5), E(5), E(3)
    ws.entities = [Entity(id=10 + i, kind=Kind.HAZARD_DYN, type_key=E(tk), pos=E(pos), vel=E(vel),
                          fsm=[("Control", st, 0.1)]) for i, (tk, st, pos, vel) in enumerate(bells)]
    fc.targets.update(ws, 0.0)
    fc._ws = ws
    f = fc.forecast(2.0, 0.0)
    prefs = Tactics(load_playbook()).decide(ws, f, None, 3)
    planner = Planner(params, arena, PlannerConfig(threads=1))
    start = kin.initial_state(params, 85.0, hero_y, vy=hero_vy)
    r = planner.tick(ws, start, kin.HoldState.idle(1), np.zeros(1, np.int64), f, prefs,
                     FilterContext.from_world(ws, None, 3))
    return planner, r


def test_the_planner_bounces_off_a_bell_below(setup):
    # an attack bell rolling under a hero at the top of a jump (no boss drawn): down attacks meet it in every lane
    planner, r = _tick(setup, [("BoneBeast AtkBell L", "In Air", (85.5, 4.3), (-12.0, 0.0))])
    assert planner.last_bell_pogo > 0 and planner.pogo_log["bell"] > 0, (planner.pogo_log, r.name, r.S)
    # without the bell nothing bounces
    planner, r = _tick(setup, [])
    assert planner.last_bell_pogo == 0 and planner.pogo_log["accepted"] == 0
    # a bell not in a hittable state (collider off) is no target
    planner, r = _tick(setup, [("BoneBeast DropBell M", "Antic", (85.0, 3.6), (0.0, 0.0))])
    assert planner.last_bell_pogo == 0


def test_a_side_slash_redirects_a_falling_drop_bell(setup):
    # a drop bell falling beside a standing hero: its exact path is the support (two bounce sides); a side slash that
    # meets it knocks it away from the hitter, so the slash's rows are scored against the one redirected path
    m, tpls, params, arena = setup
    fc = Forecaster(m, ORACLE, margin=MARGIN, templates=tpls)
    fc.tracker.roots = lambda origin: ([], True)
    ws = WorldState()
    ws.hero.pos = E((85.0, 3.0544))
    ws.res.hp, ws.res.hp_max, ws.res.silk = E(5), E(5), E(3)
    tk = "BoneBeast DropBell M2"
    ws.entities = [Entity(id=7, kind=Kind.HAZARD_DYN, type_key=E(tk), pos=E((86.6, 5.0)), vel=E((0.0, -20.0)),
                          fsm=[("Control", "Air", 0.2)])]
    fc.targets.update(ws, 0.0)
    fc._ws = ws
    fc.tracker.bells[7] = (tk, -1.5, (86.6, 13.74))
    f = fc.forecast(2.0, 0.0)
    assert len(f.det) == 1
    x = np.array([[86.6]]); y = np.array([[4.0]])
    assert f.occupied(x, y, np.array([0.05]))[0, 0]
    # 0.3 s on it has bounced (+-4 u/s, vy 30) to about y 8, 1.2 u to either side; knocked right at 0.02 s (5 u/s,
    # then its bounce goes right) only the right branch is left
    xs, ys, t3 = np.array([[85.2], [87.8]]), np.array([[8.0], [8.0]]), np.array([0.3])
    assert f.occupied(xs, ys, t3)[:, 0].all()
    o = f.occupied_redirect(xs, ys, t3, tk, 0.02, 1)
    assert not o[0, 0] and o[1, 0]
    prefs = Tactics(load_playbook()).decide(ws, f, None, 3)
    planner = Planner(params, arena, PlannerConfig(threads=1))
    planner.tick(ws, kin.initial_state(params, 85.0, 2.015 + params.foot), kin.HoldState.idle(1),
                 np.zeros(1, np.int64), f, prefs, FilterContext.from_world(ws, None, 3))
    assert planner.last_redirect > 0
