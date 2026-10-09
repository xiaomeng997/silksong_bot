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


def test_a_throw_is_its_body_and_its_hazards_paths(monkeypatch):
    """+n, oracle: a throw family (REACT_THROW_FAMS: the Reed's RE_THROW, the Bellbearer's CB_THROW, whose templates
    hold every pin / bell ever thrown) places none of its templates or tails; its body is the tube; without +n it is
    as before. The synthetic Reed's stab stands in for a throw here."""
    assert ("Song Reed", "RE_THROW") in mfm.REACT_THROW_FAMS and ("Pilgrim 03 Song", "CB_THROW") in mfm.REACT_THROW_FAMS
    monkeypatch.setattr(mfm, "REACT_THROW_FAMS", frozenset({(REED, "RE_STAB")}))
    mf = MultiForecaster(_tables(), ORACLE, waves=False)
    _run(mf, [(f, f * BIN, [_ent(7, 20.0, 5.0, "Alert" if f < 10 else "Stab Pos", flip=True,
                                 box=(19.5, 4.0, 20.5, 6.0))],
               ([_go(7, "Alert", f, 0.0)] if f == 0 else []) + ([_go(7, "Stab Pos", f, f * BIN)] if f == 10 else []))
              for f in range(12)])
    old = mf.forecast(0.8)
    stab = lambda f: [fam for m in (f.pm, f.wm, f.bb) for fam, c in zip(m["family"], m["committed"])  # noqa: E731
                      if fam == "RE_STAB" and c]
    assert stab(old) and not any(b[1] == "idle" for b in old.boxes)
    mf.react = ReactConfig(notstarted=True)
    ns = mf.forecast(0.8)
    assert not stab(ns) and any(b[1] == "idle" and b[0] == 7 for b in ns.boxes)


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


def test_a_bell_in_reach_is_a_hit_target_of_weight_0(params, arena):
    """bell_hits: the bells in reach join the hit targets after the enemies, weight 0 (no J), so the hit branch can
    knock one back; _contacts_fn with the plain support is _contacts."""
    from tests.test_forum_planner import _prefs, _reed_forecaster, _world
    mf = _reed_forecaster(None, frames=3, x=24.0)
    mf.update(_ws(3, 3 * BIN, [_ent(7, 24.0, 4.0, "Alert", flip=True, box=(23.5, 3.0, 24.5, 5.0)),
                               _bell(9, 21.0, 6.0, "Air")]))
    f = mf.forecast(0.8)
    pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"), ForumConfig())
    tk = np.arange(37) * BIN
    tbox, tok, tw, keep = pl._forum_targets(_world(20.0), f, tk, _prefs())
    kinds = [t.hazard for t in keep]
    assert kinds == [False, True] and tw[1] == 0.0 and tw[0] > 0.0
    pl2 = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"), ForumConfig(bell_hits=False))
    assert [t.hazard for t in pl2._forum_targets(_world(20.0), f, tk, _prefs())[3]] == [False]
    bound = np.zeros((2, 37, 4))
    bound[:, :, 0], bound[:, :, 2] = 20.75, 21.25
    bound[:, :, 1], bound[:, :, 3] = 5.0, 7.08
    skip = np.zeros((2, 37), bool)
    a = pl._contacts(f, bound, tk, skip)
    b = pl._contacts_fn(f, bound, tk, skip, lambda X, Y: f.occupied(X, Y, tk))
    assert np.array_equal(a, b) and a.any()


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


def test_aimed_pins_hit_the_row_that_stays_where_it_was_aimed_at(params, arena):
    """"+a": a pin released at 0.2 s from a Reed at (30, 4) is aimed at where each row is 20 frames before (here: now,
    the release is within the aim lag): a row standing at (20, 4) meets it about 0.3 s later, a row that has jumped
    5 u above by then does not (the 15 deg rays stay below it); a row on the far side is aimed at too."""
    from types import SimpleNamespace
    # on with "+a", and with "+n" (forum.md §23.12: nothing else holds a throw whose wind-up has started)
    assert ForumConfig(react="escape+n+a").pin_aim and ForumConfig(react="escape+n").pin_aim
    assert ForumConfig(react="escape+g+a").pin_aim and not ForumConfig(react="escape+g").pin_aim
    pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                      ForumConfig(react="escape+n+a"))
    T1 = 37
    box = np.zeros((3, T1, 4))
    for i, (x0, dy) in enumerate(((20.0, 0.0), (20.0, 5.0), (40.0, 0.0))):
        y = 4.0 + np.clip(np.arange(T1) - 2, 0, None) * dy / 10.0
        y = np.where(np.arange(T1) > 12, 4.0 + dy, y) if dy else y
        box[i, :, 0], box[i, :, 2] = x0 - 0.25, x0 + 0.25
        box[i, :, 1], box[i, :, 3] = y - 1.04, y + 1.04
    r1 = SimpleNamespace(box=box, flags=np.zeros((3, T1), np.int64))
    tk = np.arange(T1) * BIN
    pins = [((30.0, 4.0), (0.0, 0.0), 0.0, np.array([12 * BIN]))]
    first = pl._pin_contacts(pins, r1, np.arange(3), tk, True)
    assert first[0] >= 12 and first[0] < T1
    assert first[2] >= 12                     # aimed at it too (behind the Reed means toward +x here)
    assert first[1] == -1


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


# ---- the review of 2026-10-08 (forum.md §23.12) ----

def test_a_bellbearer_throw_keeps_its_templates_until_its_release(monkeypatch):
    """+n, oracle: a throw in a state before its release (REACT_KEEP_UNTIL_THROWN: the Bellbearer's Throw Evade / Roof
    Avoid / Throw Antic) keeps its templates (nothing else holds its bell); at the release state it is its body and
    the hazard's path. The synthetic Reed's stab stands in: Stab Pos as the wind-up, Stab as the release."""
    assert mfm.REACT_KEEP_UNTIL_THROWN[("Pilgrim 03 Song", "CB_THROW")] >= {"Throw Antic"}
    assert "Throw" not in mfm.REACT_KEEP_UNTIL_THROWN[("Pilgrim 03 Song", "CB_THROW")]
    monkeypatch.setattr(mfm, "REACT_THROW_FAMS", frozenset({(REED, "RE_STAB")}))
    monkeypatch.setattr(mfm, "REACT_KEEP_UNTIL_THROWN", {(REED, "RE_STAB"): frozenset({"Stab Pos"})})
    mf = MultiForecaster(_tables(), ORACLE, waves=False)
    mf.react = ReactConfig(notstarted=True)
    _run(mf, [(f, f * BIN, [_ent(7, 20.0, 5.0, "Alert" if f < 10 else "Stab Pos", flip=True,
                                 box=(19.5, 4.0, 20.5, 6.0))],
               ([_go(7, "Alert", f, 0.0)] if f == 0 else []) + ([_go(7, "Stab Pos", f, f * BIN)] if f == 10 else []))
              for f in range(12)])
    ns = mf.forecast(0.8)
    stab = [fam for m in (ns.pm, ns.wm, ns.bb) for fam, c in zip(m["family"], m["committed"]) if fam == "RE_STAB" and c]
    assert stab and not any(b[1] == "idle" and b[0] == 7 for b in ns.boxes)


def test_bells_switch_turns_the_hit_back_rule_off(monkeypatch):
    """SSBOT_FORUM_BELLS=off: a bell the nail hit stays a hazard on its path and the planner has no bell targets."""
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy
    monkeypatch.setenv(pj.BELLS_ENV, "off")
    hz = pj.HazardTracker(ORACLE)
    assert not hz.hit_back and not ForumPlannerPolicy._fcfg("main").bell_hits
    hz.update(_ws(0, 0.0, [_bell(9, 30.0, 8.0, "Air")]))
    hz.update(_ws(1, BIN, [_bell(9, 30.1, 8.0, "Tink L")]))
    hz.update(_ws(2, 2 * BIN, [_bell(9, 30.2, 8.0, "Nail Hit", vx=30.0)]))
    hz.update(_ws(3, 3 * BIN, [_bell(9, 30.7, 8.0, "Air", vx=30.0)]))
    assert [p.iid for p in hz.paths(3 * BIN, 0.6)] == [9]
    monkeypatch.setenv(pj.BELLS_ENV, "on")
    assert pj.HazardTracker(ORACLE).hit_back and ForumPlannerPolicy._fcfg("main").bell_hits
    monkeypatch.delenv(pj.BELLS_ENV)
    assert pj.bells_mode() == "on"
    monkeypatch.setenv(pj.BELLS_ENV, "maybe")
    with pytest.raises(ValueError):
        pj.bells_mode()


def _esc_tick(params, arena, react, dl=math.inf, fail=None):
    from ssbot.knowledge import kinematics as kin
    from tests.test_forum_planner import FLOOR, _prefs, _reed_forecaster, _world
    mf = _reed_forecaster(None, frames=3, x=25.0)       # 5 u off: the stab in the check's reach, safe rows left
    mf.react = ReactConfig.parse(react)
    pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                      ForumConfig(deadline_ms=math.inf, chunk=16, react=react, esc_deadline_ms=dl))
    if fail is not None:
        pl._escape_fail = lambda f, start, hold, full, hold_end, r1, rows, threats: (
            np.full(len(rows), fail, np.int64), [["test"] for _ in rows])
    r = pl.tick(_world(20.0), kin.initial_state(params, 20.0, FLOOR + params.foot), kin.HoldState.idle(1),
                np.zeros(1, np.int64), mf.forecast(0.8), _prefs(), _ctx())
    return pl, r


def test_with_n_a_failed_or_unchecked_escape_is_not_safe(params, arena, strikes):
    """esc_veto ("escape" + "+n"): the attacks not started are only the escape check's, so a chosen row that failed
    it (every checked row failed: the fewest failures) or that it could not check before its deadline is S = 1 (a
    YELLOW, never certified); a row that passed stays S = 0; without "+n" the check stays a ranking preference."""
    assert ForumConfig(react="escape+n").esc_veto and not ForumConfig(react="escape+g").esc_veto
    assert not ForumConfig(react="delay+n").esc_veto
    pl, r = _esc_tick(params, arena, "escape+n", fail=0)
    assert not r.forced_risk and r.S == 0 and pl.audit.esc_unsafe == 0 and not pl.last_info["esc"]["unsafe"]
    pl, r = _esc_tick(params, arena, "escape+n", fail=1)
    assert not r.forced_risk and r.S == 1 and pl.audit.esc_failed == 1 and pl.audit.esc_unsafe == 1
    assert pl.last_info["esc"]["unsafe"] and pl.prev_esc_unsafe
    pl, r = _esc_tick(params, arena, "escape+n", dl=0.0)
    assert not r.forced_risk and r.S == 1 and pl.audit.esc_unchecked == 1 and pl.last_info["esc"]["checked"] == 0
    pl, r = _esc_tick(params, arena, "escape", fail=1)
    assert not r.forced_risk and r.S == 0 and pl.audit.esc_unsafe == 0 and "unsafe" not in pl.last_info["esc"]


def test_planned_safe_counts_the_hits_a_safe_plan_did_not_avoid():
    from ssbot.train.forum_planner_policy import planned_safe
    log = [{"kind": "damage", "path": "a", "lag": {"12": [0, False, False, False, False], "24": [1, True, False,
                                                                                               False, False],
                                                   "30": None}, "safe30": True, "clash30": False},
           {"kind": "damage", "path": "b", "lag": {"12": [1, False, False, True, True], "24": [0, False, True, False,
                                                                                              False],
                                                   "30": [0, False, False, False, False]}, "safe30": True,
            "clash30": True},
           {"kind": "tick", "path": "c", "lag": {}, "safe30": True}]
    p = planned_safe(log)
    assert p["hits"] == 2 and p["12"] == 1 and p["24"] == 1 and p["30"] == 1 and p["unknown_30"] == 1
    assert p["esc_12"] == 1 and p["pin_12"] == 1 and p["any30"] == 2 and p["clash30"] == 1
    assert p["by_src"] == {"a": 1, "b": 1}


@pytest.fixture
def body_only(monkeypatch):
    """The test Reed's stab as a body-only family (no strike time), its defence a strike."""
    monkeypatch.setattr(mfm, "_STRIKE_TAB", {(REED, "RE_DEFEND"): (0.6, 0.62)})
    monkeypatch.setattr(mfm, "body_only_families", lambda path=None: frozenset({(REED, "RE_STAB")}))


def test_parse_body_reach_and_lock_check():
    assert ReactConfig.parse("escape+n+g+b").bodyreach and not ReactConfig.parse("escape+n+b").bodyreach_all
    assert ReactConfig.parse("escape+n+br").bodyreach_all and ReactConfig.parse("escape+n+k") == \
        ReactConfig.parse("escape+n")
    with pytest.raises(ValueError):
        ReactConfig.parse("escape+b")                     # needs +n
    assert ForumConfig(react="escape+n+b").body_reach == (True, False)
    assert ForumConfig(react="escape+n+br").body_reach == (True, True)
    assert ForumConfig(react="escape+n").body_reach == (False, False)
    assert ForumConfig(react="escape+n+k").lock_check and not ForumConfig(react="delay+n+k").lock_check


def test_body_reach_leaves_body_only_families_to_the_tube(body_only):
    """+b / +br: a body-only family not started is not placed when the collider tube holds its reaction window (the
    Reed's only with +br, BODYREACH_KEEP); +n alone keeps it; an enemy not seen lately keeps it (no tube)."""
    def later(rc, frames=2, origin=None):
        mf = MultiForecaster(_tables(), ORACLE, waves=False)
        _idle_reed(mf, frames)
        mf.react = rc
        f = mf.forecast(0.8) if origin is None else mf.forecast(0.8, origin_t=origin)
        return {fam for fam, c in zip(f.bb["family"], f.bb["committed"]) if not c}, f
    fams, _ = later(ReactConfig(notstarted=True))
    assert "RE_STAB" in fams and "RE_DEFEND" not in fams
    fams, _ = later(ReactConfig(notstarted=True, bodyreach=True))
    assert "RE_STAB" in fams                            # the Reed's body is kept with +b
    fams, f = later(ReactConfig(notstarted=True, bodyreach=True, bodyreach_all=True))
    assert "RE_STAB" not in fams and any(b[1] == "collider" for b in f.boxes)
    fams, _ = later(ReactConfig(notstarted=True, bodyreach=True, bodyreach_all=True), origin=0.6 + 2 * BIN)
    assert "RE_STAB" in fams                            # last seen 0.6 s ago: no collider tube, kept


def test_body_reach_threats_and_the_bind_lock(params, arena, body_only):
    """The escape check takes "+br"'s body-only families as threats (no wind-up); "+k": a Bind is threatened when an
    attack not started may start and reach the hero during the Bind's lock, not when the hero is far."""
    from tests.test_forum_planner import _reed_forecaster
    mf = _reed_forecaster(None, frames=3, x=25.0)
    mf.react = ReactConfig.parse("escape+n+br")
    pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                      ForumConfig(deadline_ms=math.inf, react="escape+n+br+k"))
    f = mf.forecast(2.0)
    th = {t[-1]: t for t in pl._threats(f, (24.0, 5.0))}
    assert f"{REED}/RE_STAB" in th and th[f"{REED}/RE_STAB"][2] == 1.0
    pl.fcfg.react = "escape+n"
    assert f"{REED}/RE_STAB" not in {t[-1] for t in pl._threats(f, (24.0, 5.0))}
    pl.fcfg.react = "escape+n+br+k"

    def stand(x):
        b = np.array([x - 0.3, 4.0, x + 0.3, 6.0])
        return np.tile(b, (101, 1))
    assert pl._bind_threatened(f, stand(23.0), 1, (23.0, 5.0))
    assert not pl._bind_threatened(f, stand(4.0), 1, (4.0, 5.0))
