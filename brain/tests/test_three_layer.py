"""The three-layer support of the wave-0 de-saturation (forum.md §23): the reactive support's "+n" (attacks not started
out of the support, the escape check over every lock-in) and "+g" (the idle tube's growth held after the reaction
window), the pins / bells not thrown yet, the hit-back bells, the clash layer's tier gate and the kill-freeze rule; on
the synthetic Reed tables of test_multi_forecast."""
import math

import numpy as np
import pytest

from ssbot.combat import multi_forecast as mfm
from ssbot.combat import projectiles as pj
from ssbot.combat.forum_planner import ForumConfig, ForumPlanner
from ssbot.combat.multi_forecast import REACT_HOLD_S, REACT_THROWN, MultiForecaster, ReactConfig
from ssbot.combat.planner import PlannerConfig
from ssbot.core.worldstate import E, ORACLE, DamageBox, Entity
from tests.test_forum_planner import _ctx, arena, params  # noqa: F401
from tests.test_multi_forecast import BIN, REED, _ent, _go, _run, _tables, _ws


@pytest.fixture
def strikes(monkeypatch):
    monkeypatch.setattr(mfm, "_STRIKE_TAB", {(REED, "RE_STAB"): (0.5, 0.51), (REED, "RE_DEFEND"): (0.6, 0.62)})


def _idle_reed(mf, frames=2, x=20.0):
    _run(mf, [(f, f * BIN, [_ent(7, x, 5.0, "Alert", box=(x - 0.5, 4.0, x + 0.5, 6.0))],
               [_go(7, "Alert", 0, 0.0)] if f == 0 else []) for f in range(frames)])


def test_parse_the_new_extensions():
    assert ReactConfig.parse("escape+n+g") == ReactConfig(True, False, False, "keep", True, True)
    assert ReactConfig.parse("delay+n").notstarted and not ReactConfig.parse("delay+n").hold
    assert ForumConfig(react="escape+n+g").notstarted and not ForumConfig(react="escape+g").notstarted
    with pytest.raises(ValueError):
        ReactConfig.parse("escape+z")


def test_not_started_attacks_leave_the_support_and_keep_their_strike_time(strikes):
    """+n: an idle Reed's later stab / defence (families with a strike time) and its later idle instances are not
    placed; the subject's earliest strike (the escape check's threat) is the same as without."""
    mf = MultiForecaster(_tables(), ORACLE, waves=False)
    _idle_reed(mf)
    mf.react = ReactConfig()
    base = mf.forecast(0.8)
    mf.react = ReactConfig(notstarted=True)
    ns = mf.forecast(0.8)
    later = [(fam, c) for fam, c in zip(base.bb["family"], base.bb["committed"]) if not c]
    assert any(fam in ("RE_STAB", "RE_DEFEND") for fam, _ in later)
    assert not any(not c for c in ns.bb["committed"])
    assert ns.subjects[0].t_strike == base.subjects[0].t_strike and math.isfinite(ns.subjects[0].t_strike)
    # the idle body tube stays
    assert any(b[1] == "idle" for b in ns.boxes)


def test_hold_stops_the_idle_growth_after_the_reaction_window(strikes):
    """+g: the idle tube grows by the type's idle growth (0.05 u a bin here) for REACT_HOLD_S, then keeps its size."""
    mf = MultiForecaster(_tables(), ORACLE, waves=False)
    _idle_reed(mf)
    tk = np.arange(0, 49) * BIN
    x = 20.5 + 0.25 + 0.05 * 20            # past the box's edge + the hero's half width by 20 bins of growth
    X, Y = np.full((1, 49), x), np.full((1, 49), 5.0)
    mf.react = ReactConfig()
    grow = mf.forecast(0.8)._box_occ(X, Y, tk, kinds=("idle",))[0]
    mf.react = ReactConfig(hold=True)
    held = mf.forecast(0.8)._box_occ(X, Y, tk, kinds=("idle",))[0]
    assert grow[30:].all() and not held.any()
    near = 20.5 + 0.25 + 0.05 * (REACT_HOLD_S / BIN - 1)
    held2 = mf.forecast(0.8)._box_occ(np.full((1, 49), near), Y, tk, kinds=("idle",))[0]
    assert held2[int(round(REACT_HOLD_S / BIN)):].all()


def _pin(iid, x, y, state, armed):
    boxes = [DamageBox(poly=[(x - 1.0, y - 0.05), (x + 1.0, y - 0.05), (x + 1.0, y + 0.05), (x - 1.0, y + 0.05)],
                       active=True)] if armed else []
    return Entity(id=iid, type_key=E("Song Reed Pin Projectile"), pos=E((x, y)), vel=E((0.0, 0.0)),
                  pos_transform=(x, y), fsm=[("Javelin Control", state, 0.0)], dmg_boxes=boxes)


def test_a_pin_not_thrown_is_only_its_reaction_window_reach():
    """+n: a pin in the Reed's hand (not armed) is no self-template window over the horizon (every direction a pin
    ever flew) but a hazard tube over the reaction window; without +n the window stays."""
    tables = _tables()
    mf = MultiForecaster(tables, ORACLE, waves=False)
    mf.update(_ws(0, 0.0, [_pin(50, 20.0, 6.0, "Throw Effect", False)]))
    mf.tables.self_id = lambda tk: 0              # the synthetic tables have no self template: any one will do
    f_old = mf.forecast(0.8)
    ent = lambda f: [fam for m in (f.pm, f.wm) for fam in m["family"] if str(fam).startswith("ent/")]  # noqa: E731
    assert ent(f_old)                             # Throw Effect is no rest state: armed, its self template placed
    mf.react = ReactConfig(notstarted=True)
    f_ns = mf.forecast(0.8)
    assert not ent(f_ns)
    tubes = [b for b in f_ns.boxes if b[1] == "hazard" and b[0] == 50]
    assert len(tubes) == 1 and tubes[0][10] == pytest.approx(mfm.COLLIDER_TUBE_S)
    hx, hy = REACT_THROWN["Song Reed Pin Projectile"]
    assert tubes[0][2:6] == pytest.approx((20.0 - hx, 6.0 - hy, 20.0 + hx, 6.0 + hy))


def _bell(iid, x, y, state, vx=5.0, vy=0.0):
    r = pj.BELL_R
    return Entity(id=iid, type_key=E(pj.BELL), pos=E((x, y)), vel=E((vx, vy)), pos_transform=(x, y),
                  fsm=[("Control", state, 0.0)],
                  dmg_boxes=[DamageBox(poly=[(x - r, y - r), (x + r, y - r), (x + r, y + r), (x - r, y + r)],
                                       active=True)])


def test_a_bell_the_nail_hit_is_the_heros_projectile():
    """forum.md bell paragraph: after Tink / Nail Hit a bell never hurt the hero again: no path; a new throw (Init)
    makes it a hazard again; the planner's own hit (redirect) leaves it harmless from the hit on."""
    hz = pj.HazardTracker(ORACLE)
    hz.update(_ws(0, 0.0, [_bell(9, 30.0, 8.0, "Air")]))
    assert [p.iid for p in hz.paths(0.0, 0.6)] == [9]
    r = hz.redirect(9, 0.1, 1, 0.0, 0.6)
    k = 1 + max(0, int(math.ceil((0.1 - r.t_first) / pj.STEP_S - 1e-9)))
    assert r.on[:, :k].any() and not r.on[:, k:].any()
    hz.update(_ws(1, BIN, [_bell(9, 30.1, 8.0, "Tink L")]))
    hz.update(_ws(2, 2 * BIN, [_bell(9, 30.2, 8.0, "Nail Hit", vx=30.0)]))
    hz.update(_ws(3, 3 * BIN, [_bell(9, 30.7, 8.0, "Air", vx=30.0)]))
    assert hz.paths(3 * BIN, 0.6) == []
    hz.update(_ws(4, 4 * BIN, [_bell(9, 25.0, 9.0, "Init")]))
    hz.update(_ws(5, 5 * BIN, [_bell(9, 25.1, 9.2, "Air")]))
    assert [p.iid for p in hz.paths(5 * BIN, 0.6)] == [9]


def test_clash_main_runs_in_a_yellow_from_the_plan_not_at_h2(params, arena):
    pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                      ForumConfig(clash=True, clash_main=True, clash_min_p=0.0, clash_max_fail=0.3))
    assert pl.clash_allowed(_ctx(tier="GREEN", h=3))
    assert pl.clash_allowed(_ctx(tier="YELLOW", h=3))
    assert not pl.clash_allowed(_ctx(tier="YELLOW", h=2))
    assert not pl.clash_allowed(_ctx(tier="RED", h=3))
    assert not pl.clash_allowed(_ctx(tier="GREEN", h=3, pause_pending=True))
    on = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"), ForumConfig(clash=True))
    assert on.clash_allowed(_ctx(tier="GREEN", h=3)) and not on.clash_allowed(_ctx(tier="YELLOW", h=3))


def test_the_policy_has_the_main_clash_mode():
    from ssbot.train.forum_planner_policy import CLASH_MODES, ForumPlannerPolicy
    c = ForumPlannerPolicy._fcfg("main")
    assert c.clash and c.clash_main and c.clash_min_p == 0.0 and c.clash_max_fail == pytest.approx(0.3)
    assert not ForumPlannerPolicy._fcfg("on").clash_main and set(CLASH_MODES) >= {"off", "on", "main"}


def test_light_cone_switch_and_its_layer(params, arena):
    """"+l": the escape check's light cone. Its layer: the committed fine placements of the families clash.json does
    not clash (a stab committed a frame ago here: its blade in front of the anchor), never a clashable family's."""
    assert ForumConfig(react="escape+n+l").light_cone and not ForumConfig(react="delay+l").light_cone
    assert not ForumConfig(react="escape+n").light_cone
    mf = MultiForecaster(_tables(), ORACLE, waves=False)
    _run(mf, [(f, f * BIN, [_ent(7, 20.0, 5.0, "Alert" if f < 10 else "Stab Pos", flip=True,
                                 box=(19.5, 4.0, 20.5, 6.0))],
               ([_go(7, "Alert", f, 0.0)] if f == 0 else []) + ([_go(7, "Stab Pos", f, f * BIN)] if f == 10 else []))
              for f in range(12)])
    f = mf.forecast(0.8)
    pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                      ForumConfig(react="escape+n+l"))
    tk = np.arange(0, 49) * BIN
    X, Y = np.full((1, 49), 22.0), np.full((1, 49), 5.0)
    pl._lc_fams = frozenset()
    assert pl._light_cone_occ(f, X, Y, tk)[0].any()
    pl._lc_fams = frozenset({"RE_STAB"})
    assert not pl._light_cone_occ(f, X, Y, tk)[0].any()


def test_state_margins_dilate_a_state_by_its_own_residual():
    """forum.md §23: with the per-state margins a per-state template takes its state's held-out residual (EN_CHARGE
    Charge End 0.40 u instead of the family's 2.96 u, set by its Charge), the family-wide and tail ones the family's."""
    from ssbot.combat.enemy_tables import FORUM_DIR, EnemyTables, parse_state_margins
    if not (FORUM_DIR / "Envoy_hitboxes.npz").exists() or not (FORUM_DIR / "support_margins_state.json").exists():
        pytest.skip("no production templates")
    assert parse_state_margins({"A/B/C D": 0.5}) == {("A", "B", "C D"): 0.5}
    env = ("Song Pilgrim 01",)
    fam = EnemyTables.production(types=env)
    st = EnemyTables.production(types=env, state_margins_path=FORUM_DIR / "support_margins_state.json")
    pad = lambda tb, s: tb.template(tb.key_id("EN_CHARGE", s, "anchor")).pad_x       # noqa: E731
    assert pad(st, "Charge End") < pad(fam, "Charge End") - 2.0
    assert pad(st, "Charge") == pytest.approx(pad(fam, "Charge"))
    assert pad(st, "_tail") == pytest.approx(pad(fam, "_tail"))
