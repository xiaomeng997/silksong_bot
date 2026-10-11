"""Reactive support (task "reactive support", forum.md §22): multi_forecast.ReactConfig (the strike delays of attacks
not started, the committed / idle / p5 extensions), the planner's escape check and the policy switch, on the synthetic
Reed tables of test_multi_forecast."""
import math

import numpy as np
import pytest

from ssbot.combat import multi_forecast as mfm
from ssbot.combat.forum_planner import ForumConfig, ForumPlanner
from ssbot.combat.multi_forecast import REACT_LATENCY_S, MultiForecaster, ReactConfig, strike_delays
from ssbot.combat.planner import PlannerConfig
from ssbot.core.worldstate import ORACLE
from ssbot.knowledge import kinematics as kin
from tests.test_forum_planner import FLOOR, _ctx, _prefs, _reed_forecaster, _world, arena, params  # noqa: F401
from tests.test_multi_forecast import BIN, REED, _ent, _go, _run, _tables

D_STAB = 0.5                       # a made-up stab delay, longer than the synthetic walk's own (0.1 + 0.05 s)


@pytest.fixture
def strikes(monkeypatch):
    """The synthetic Reed's strike table: the stab with D_STAB, the defence (its counter) with 0.6 s."""
    monkeypatch.setattr(mfm, "_STRIKE_TAB", {(REED, "RE_STAB"): (D_STAB, D_STAB + 0.01),
                                             (REED, "RE_DEFEND"): (0.6, 0.62)})


def _idle_reed(mf, frames=2, x=20.0):
    _run(mf, [(f, f * BIN, [_ent(7, x, 5.0, "Alert", box=(x - 0.5, 4.0, x + 0.5, 6.0))],
               [_go(7, "Alert", 0, 0.0)] if f == 0 else []) for f in range(frames)])


def test_parse_the_switch():
    assert ReactConfig.parse("off") is None and ReactConfig.parse("") is None and ReactConfig.parse(None) is None
    assert ReactConfig.parse("delay") == ReactConfig()
    assert ReactConfig.parse("escape+c+i+p5") == ReactConfig(True, True, True, "p5")
    for bad in ("bogus", "delay+x"):
        with pytest.raises(ValueError):
            ReactConfig.parse(bad)
    assert ForumConfig(react="escape+c").escape and not ForumConfig(react="delay").escape
    assert not ForumConfig().escape


def test_delays_keep_the_exceptions_unless_p5():
    tab = {("A", "EN_SLASH"): (0.483, 0.491), ("B", "RE_THROW"): (0.1, 0.667), ("C", "CB_THROW"): (0.0, 0.658)}
    import json
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "strikes.json"
        p.write_text(json.dumps({"strikes": {f"{tk}/{fam}": {"commit_to_first_attack_collider_s":
                                                             {"n": 9, "min": lo, "p5": p5}}
                                             for (tk, fam), (lo, p5) in tab.items()}}), "utf-8")
        assert strike_delays(ReactConfig(), p) == {("A", "EN_SLASH"): 0.483}
        assert strike_delays(ReactConfig(exceptions="p5"), p) == {("A", "EN_SLASH"): 0.483,
                                                                   ("B", "RE_THROW"): 0.667, ("C", "CB_THROW"): 0.658}


def test_production_strike_table_has_the_wave0_families():
    tab = mfm.strike_table()
    if not tab:
        pytest.skip("no strikes.json")
    d = strike_delays(ReactConfig())
    for k in (("Song Pilgrim 01", "EN_SLASH"), ("Song Pilgrim 01", "EN_CHARGE"), ("Song Pilgrim 03", "CH_WHIP"),
              ("Song Reed", "RE_STAB")):
        assert 0.35 <= d[k] <= 0.9
    assert ("Song Reed", "RE_THROW") not in d and ("Song Automaton Tiny", "AT_FIRE") not in d
    assert REACT_LATENCY_S[ORACLE] == pytest.approx(BIN)


def test_off_is_the_support_as_before(strikes):
    """react None: every placement's delay is -inf and the queries equal a forecaster that never had the field; a
    delayed forecast in between leaves the state as it was."""
    tk = np.arange(0, 49) * BIN
    X, Y = np.meshgrid(np.arange(14.0, 30.0, 0.5), np.array([4.0, 5.0, 7.0]))
    X, Y = np.repeat(X.reshape(-1, 1), 49, 1), np.repeat(Y.reshape(-1, 1), 49, 1)
    a, b = MultiForecaster(_tables(), ORACLE, waves=False), MultiForecaster(_tables(), ORACLE, waves=False)
    _idle_reed(a)
    _idle_reed(b)
    f0 = a.forecast(0.8)
    assert np.isneginf(f0.bb["ton"]).all() and np.isneginf(f0.pm["ton"]).all() and np.isneginf(f0.wm["ton"]).all()
    b.react = ReactConfig(True, True, True, "p5")
    b.forecast(0.8)
    b.react = None
    f1 = b.forecast(0.8)
    assert np.array_equal(f0.occupied(X, Y, tk), f1.occupied(X, Y, tk))
    assert f0.n_bbox == f1.n_bbox and f0.n_fine == f1.n_fine and f0.n_window == f1.n_window


def test_a_stab_not_started_strikes_no_earlier_than_its_wind_up(strikes):
    """An idle Reed: its later stab's walk rows hold no contact before their earliest start - a frame + D_STAB - the
    latency; the family template (the wind-up, time since the start) is placed at the same start boxes; the delayed
    support never holds a cell the support as before does not (the family template is inside the walk's)."""
    mf = MultiForecaster(_tables(), ORACLE, waves=False)
    _idle_reed(mf)
    tk = np.arange(0, 61) * BIN
    X, Y = np.meshgrid(np.arange(14.0, 30.0, 0.25), np.array([4.0, 5.0, 6.0]))
    X, Y = np.repeat(X.reshape(-1, 1), 61, 1), np.repeat(Y.reshape(-1, 1), 61, 1)
    off = mf.forecast(1.0)
    mf.react = ReactConfig()
    dl = mf.forecast(1.0)
    stab = np.array([f == "RE_STAB" for f in dl.bb["family"]])
    ftid = mf.tables.key_id("RE_STAB", None, "anchor")
    walk_rows = stab & (dl.bb["tid"] != ftid)
    assert walk_rows.any() and (stab & (dl.bb["tid"] == ftid)).any()
    lat = REACT_LATENCY_S[ORACLE]
    want = np.maximum(dl.bb["e0"][walk_rows] - BIN, 0.0) + D_STAB - lat
    assert np.allclose(dl.bb["ton"][walk_rows], want)
    occ = dl._bbox_occ(X, Y, tk, walk_rows)
    first = tk[np.argmax(occ.any(axis=0))] if occ.any() else math.inf
    assert first >= want.min() - 1e-9
    # what the delayed support holds beyond the support as before is the family templates' (the wind-up, measured
    # since the start: not a subset of the walk's hull in general); without them it holds less
    fam_rows = np.isin(dl.bb["tid"], [mf.tables.key_id(fm, None, "anchor") for fm in ("RE_STAB", "RE_DEFEND")])
    extra = dl.occupied(X, Y, tk) & ~off.occupied(X, Y, tk)
    assert not (extra & ~dl._bbox_occ(X, Y, tk, fam_rows)).any()
    assert (dl.occupied(X, Y, tk) & ~dl._bbox_occ(X, Y, tk, fam_rows)).sum() < off.occupied(X, Y, tk).sum()


def test_committed_extension_holds_the_later_states_of_a_fresh_attack(strikes):
    """+c: a stab committed a frame ago: its later states' placements hold nothing before its start + D_STAB - the
    latency; its family template from the start (the wind-up) is placed as before."""
    mf = MultiForecaster(_tables(), ORACLE, waves=False)
    _run(mf, [(f, f * BIN, [_ent(7, 20.0, 5.0, "Alert" if f < 10 else "Stab Pos", flip=True,
                                 box=(19.5, 4.0, 20.5, 6.0))],
               ([_go(7, "Alert", f, 0.0)] if f == 0 else []) + ([_go(7, "Stab Pos", f, f * BIN)] if f == 10 else []))
              for f in range(12)])
    mf.react = ReactConfig(committed=True)
    f = mf.forecast(0.8)
    tr = mf.trackers[7]
    ton = tr.cur.t_start - f.origin_t + D_STAB - REACT_LATENCY_S[ORACLE]
    later = [(m, i) for m in (f.pm, f.wm) for i in range(len(m["owner"])) if m["committed"][i]
             and np.isfinite(m["ton"][i])]
    assert later and all(abs(m["ton"][i] - ton) < 1e-9 for m, i in later)
    # the blade of Stab 1 (x 21-23 in front) not before ton; the family template's wind-up body at the anchor is
    tk = np.arange(0, 49) * BIN
    blade = f.occupied(np.full((1, 49), 22.0), np.full((1, 49), 5.0), tk)[0]
    body = f.committed().occupied(np.full((1, 49), 20.0), np.full((1, 49), 5.0), tk)[0]
    mf.react = None
    blade0 = mf.forecast(0.8).occupied(np.full((1, 49), 22.0), np.full((1, 49), 5.0), tk)[0]
    assert body[:5].all()
    assert blade0.any() and np.flatnonzero(blade)[0] >= np.flatnonzero(blade0)[0]


def test_idle_extension_leaves_the_idle_roots_to_the_tube(strikes):
    mf = MultiForecaster(_tables(), ORACLE, waves=False)
    _idle_reed(mf)
    mf.react = ReactConfig(idle=True)
    f = mf.forecast(0.8)
    assert any(b[1] == "idle" for b in f.boxes)
    assert not any(fam == "RE_IDLE" and not c for fam, c in zip(f.bb["family"], f.bb["committed"]))
    mf.react = None
    assert any(fam == "RE_IDLE" for fam in mf.forecast(0.8).bb["family"])


def test_the_policy_reads_the_react_switch(monkeypatch):
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy
    monkeypatch.delenv("SSBOT_FORUM_REACT", raising=False)
    assert ForumPlannerPolicy._fcfg().react == "off" == ForumConfig().react
    monkeypatch.setenv("SSBOT_FORUM_REACT", "escape+c")
    assert ForumPlannerPolicy._fcfg().react == "escape+c"
    monkeypatch.setenv("SSBOT_FORUM_REACT", "fast")
    with pytest.raises(ValueError):
        ForumPlannerPolicy._fcfg()


def test_escape_check_fails_against_the_wall_and_passes_in_the_open(params, arena, strikes):
    """A Reed idling at the hero's side: a plan ending pressed into the left wall with the Reed on the right of it
    (the stab's family reaches 1-3 u in front, both facings) has the stab's escape only by running out of its reach
    or jumping; 25 u from it, nothing to escape; the off / delay planners never run the check."""
    for x_reed, x_hero, want_threats in ((16.5, 15.2, True), (45.0, 20.0, False)):
        mf = _reed_forecaster(None, frames=3, x=x_reed)
        mf.react = ReactConfig()
        f = mf.forecast(0.8)
        pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                          ForumConfig(deadline_ms=math.inf, chunk=16, react="escape"))
        th = pl._threats(f, (x_hero, FLOOR + 1.04))
        assert bool(th) == want_threats
        r = pl.tick(_world(x_hero), kin.initial_state(params, x_hero, FLOOR + params.foot), kin.HoldState.idle(1),
                    np.zeros(1, np.int64), f, _prefs(), _ctx())
        esc = pl.last_info["esc"]
        if r.forced_risk or not want_threats:
            continue
        assert esc is not None and esc["threats"] == len(th) and esc["checked"] >= 1
        assert pl.audit.esc_ticks == 1
    pl2 = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                       ForumConfig(deadline_ms=math.inf, chunk=16, react="delay"))
    mf = _reed_forecaster(None, frames=3, x=16.5)
    mf.react = ReactConfig()
    pl2.tick(_world(15.2), kin.initial_state(params, 15.2, FLOOR + params.foot), kin.HoldState.idle(1),
             np.zeros(1, np.int64), mf.forecast(0.8), _prefs(), _ctx())
    assert pl2.last_info["esc"] is None and pl2.audit.esc_ticks == 0


def test_escape_check_keeps_to_its_deadline(params, arena, strikes):
    """esc_deadline_ms: no escape batch starts past it (the order's choice stands, counted esc_cut); inf (the
    default with deadline_ms inf): never cut."""
    picks = {}
    for dl in (math.inf, 0.0):
        mf = _reed_forecaster(None, frames=3, x=16.5)
        mf.react = ReactConfig()
        pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                          ForumConfig(deadline_ms=math.inf, chunk=16, react="escape", esc_deadline_ms=dl))
        r = pl.tick(_world(15.2), kin.initial_state(params, 15.2, FLOOR + params.foot), kin.HoldState.idle(1),
                    np.zeros(1, np.int64), mf.forecast(0.8), _prefs(), _ctx())
        esc = pl.last_info["esc"]
        picks[dl] = r.idx
        if dl == 0.0:
            assert pl.audit.esc_cut == 1 and esc["cut"] and esc["checked"] == 0
        else:
            assert pl.audit.esc_cut == 0 and not esc["cut"] and esc["checked"] >= 1
