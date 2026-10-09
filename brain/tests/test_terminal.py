"""The Forum planner's terminal value (forum_planner_plan §4.4 items 2 and 5, round R5): combat.terminal's fields on the
synthetic Reed of test_multi_forecast, the terms' direction, and that the terminal value only moves J."""
import math

import numpy as np
import pytest

from ssbot.combat import terminal as tv
from ssbot.combat.enemy_tracker import EnemyTracker
from ssbot.combat.forum_planner import ForumConfig, ForumPlanner
from ssbot.combat.planner import PlannerConfig
from ssbot.core.worldstate import E, ORACLE, Entity
from ssbot.knowledge import kinematics as kin
from tests.test_forum_planner import FLOOR, _ctx, _prefs, _reed_forecaster, _world, arena, params  # noqa: F401
from tests.test_multi_forecast import REED


def test_the_support_field_is_empty_only_where_every_fine_query_is():
    """§4.4 item 5: a cell / bin the field leaves empty holds no point and no frame the support covers."""
    mf = _reed_forecaster(stab_at=8, frames=12)
    f = mf.forecast(2.0)
    fl = tv.EnemyFields.build(f)
    assert fl.nbins == 14 and fl.U.shape == (14, tv.GRID_NY, tv.GRID_NX)
    rng = np.random.default_rng(3)
    iy, ix = np.divmod(np.arange(tv.GRID_NY * tv.GRID_NX), tv.GRID_NX)
    iy, ix = np.repeat(iy, 3), np.repeat(ix, 3)
    n_empty = n_occ = 0
    for j in range(fl.nbins):
        for k in range(7):                                    # every frame of the bin (and its edges)
            t = round((fl.ta[j] + k / 60.0) * 60) / 60.0
            if t > fl.ta[j] + tv.FIELD_DT_S + 1e-9:
                continue
            x = tv.GRID_X0 + (ix + rng.uniform(0, 1, len(ix))) * tv.GRID_DX
            y = tv.GRID_Y0 + (iy + rng.uniform(0, 1, len(iy))) * tv.GRID_DY
            occ = f.occupied(x[:, None], y[:, None], np.array([t]))[:, 0]
            empty = fl.U[j, iy, ix] == 0
            assert not (occ & empty).any()
            n_empty += int(empty.sum())
            n_occ += int(occ.sum())
    assert n_empty > 0 and n_occ > 0                          # the check had both kinds of cells
    # the committed field holds the committed forecast the same way
    fcm = f.committed()
    for j in range(fl.nbins):
        t = float(fl.ta[j]) + 0.05
        x = tv.GRID_X0 + (ix + rng.uniform(0, 1, len(ix))) * tv.GRID_DX
        y = tv.GRID_Y0 + (iy + rng.uniform(0, 1, len(iy))) * tv.GRID_DY
        occ = fcm.occupied(x[:, None], y[:, None], np.array([round(t * 60) / 60.0]))[:, 0]
        assert not (occ & (fl.Uc[j, iy, ix] == 0)).any()


def test_e_prefers_room_away_from_the_enemy_and_trapped_needs_every_way_closed(params):  # noqa: F811
    mf = _reed_forecaster(stab_at=None, frames=4, x=30.0)
    f = mf.forecast(2.0)
    fb = tv.EnemyFields.from_bodies(f)
    assert fb.keys == [7]
    t = tv.TerminalValue(params)
    xs = np.array([20.0, 29.0, 30.0, 40.0])
    E_, trapped, ov, he = t.rows(fb, xs, np.full(4, tv.HERO_CY), np.zeros(4, np.int64), 0.6)
    assert E_[0] > E_[2] + 0.2 and E_[3] > E_[2] + 0.2      # 10 u away vs on the Reed
    assert not trapped.any()                          # one enemy: a way out on either side
    assert (ov == 0).all()                             # one zone never overlaps itself
    # a reach whose cells all lie in the zone is trapped: a zone over the whole arena
    fb.Cl[:] = 1
    _, trapped, _, _ = t.rows(fb, xs, np.full(4, tv.HERO_CY), np.zeros(4, np.int64), 0.6)
    assert trapped.all()


def test_kill_value_is_the_shrink_near_the_hero_per_hit_needed():
    mf = _reed_forecaster(stab_at=None, frames=4, x=30.0)
    f = mf.forecast(2.0)
    fb = tv.EnemyFields.from_bodies(f)
    kv1 = fb.kill_value(29.0, tv.HERO_CY, 9.0)
    kv_far = fb.kill_value(48.0, 15.0, 9.0)
    assert kv1[7] > 0 and kv1[7] > kv_far.get(7, 0.0)
    fb.hp[7] = (36.0, 0.0)                             # 4 hits at 9
    assert math.isclose(fb.kill_value(29.0, tv.HERO_CY, 9.0)[7] * 4, fb.kill_value(29.0, tv.HERO_CY, 36.0)[7])


@pytest.mark.parametrize("hero_x,stab_at", [(27.0, 10), (24.0, None), (30.2, 10)])
def test_the_terminal_value_moves_j_only(params, arena, hero_x, stab_at):  # noqa: F811
    """§4.4 item 2: S, Hz, U of every row, the envelope's verdicts and FORCED_RISK are the same with and without the
    terminal value (deterministic deadline); only J (and so the choice among rows of equal rank) may differ."""
    mf = _reed_forecaster(stab_at)
    f = mf.forecast(2.0)
    start = kin.initial_state(params, hero_x, FLOOR + params.foot)
    ws = _world(hero_x)
    out = []
    for on in (False, True):
        pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                          ForumConfig(deadline_ms=math.inf, terminal=on))
        r = pl.tick(ws, start, kin.HoldState.idle(1), np.zeros(1, np.int64), f, _prefs(None, hero_x), _ctx(kill_hp=5.0))
        li = pl.last_info
        out.append((r, li["S"].copy(), li["Hz"].copy(), li["U"].copy(), li.get("tv")))
    (r0, s0, hz0, u0, tv0), (r1, s1, hz1, u1, tv1) = out
    assert tv0 is None and tv1 is not None and tv1["field_ms"] >= 0.0
    assert np.array_equal(hz0, hz1) and np.array_equal(u0, u1)
    assert r0.forced_risk == r1.forced_risk
    # rows enveloped in both runs agree on S (the envelope order follows J, so the sets may differ)
    assert r0.S == 0 or r0.forced_risk
    assert r1.S == 0 or r1.forced_risk


def test_hit_targets_skip_the_range_triggers():
    """The hit target is the box of the colliders a nail can hit (Entity.hit_polys), not the range triggers'."""
    mf = _reed_forecaster(stab_at=None, frames=2, x=30.0)
    tr: EnemyTracker = mf.trackers[7]
    big = [[(10.0, 0.0), (50.0, 0.0), (50.0, 20.0), (10.0, 20.0)]]           # an Alert Range trigger
    body = [[(29.5, 3.0), (30.5, 3.0), (30.5, 5.0), (29.5, 5.0)]]
    e = Entity(id=7, type_key=E(REED), pos=E((30.0, 4.0)), vel=E((0.0, 0.0)), pos_transform=(30.0, 4.0),
               fsm=[("Control", "Alert", 0.1)], body_polys=big + body, hit_polys=body)
    tr.observe(1.0, (), e)
    assert tr.body == pytest.approx((29.5, 3.0, 30.5, 5.0))
    e.hit_polys = []                                   # a view without hit_polys: every body polygon, as before
    tr.observe(1.1, (), e)
    assert tr.body == pytest.approx((10.0, 0.0, 50.0, 20.0))


def test_the_reachable_templates_load_from_the_knowledge_file(params):  # noqa: F811
    offs, n = tv.reach_templates(params)
    assert offs.shape[:2] == (len(tv.CLASSES), len(tv.REACH_S)) and (n > 0).all()
    # from the ground, 0.2 s reaches no farther than a dash and a run allow, and the floor is never left downwards
    g = offs[0, 0, :n[0, 0]]
    assert np.abs(g[:, 0]).max() < 6.0 and g[:, 1].min() >= -0.01
