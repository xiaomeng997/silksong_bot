"""The Forum integration of 2026-10-08 (HANDOFF "Forum integration 2026-10-08"): the tracks' switches together.
FORCED_RISK's keys stack (seen > the committed fine share of seen_cf > P > P_cm > P_f of commit_rank > the first
contacts > J), a switched-off key is 0 on every row, the policy's switches combine, and a tick with every switch on
runs (Wanderer, clash, escape, commit_rank, terminal value)."""
import math

import numpy as np
import pytest

from ssbot.combat.forum_planner import ForumConfig, ForumPlanner
from ssbot.combat.multi_forecast import ReactConfig
from ssbot.combat.planner import PlannerConfig
from ssbot.knowledge import kinematics as kin
from ssbot.train.forum_planner_policy import CREST_PARAMS
from tests.test_forum_planner import FLOOR, _ctx, _prefs, _reed_forecaster, _world
from tests.test_forum_planner import arena, params  # noqa: F401 (fixtures)

XS = (30.6, 31.0, 31.6, 32.0)


def _tick(params, arena, x, crest="Reaper", react=None, **kw):
    mf = _reed_forecaster(10, frames=17)
    mf.react = ReactConfig.parse(react) if react else None
    p = params if crest == "Reaper" else kin.HeroParams.load(CREST_PARAMS[crest])
    pl = ForumPlanner(p, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                      ForumConfig(deadline_ms=math.inf, chunk=16, **({"react": react} if react else {}), **kw),
                      crest=crest)
    r = pl.tick(_world(x), kin.initial_state(p, x, FLOOR + p.foot), kin.HoldState.idle(1), np.zeros(1, np.int64),
                mf.forecast(0.8), _prefs(), _ctx())
    return r, pl


def _key(ls, j):
    """FORCED_RISK's order for row j (ForumPlanner.tick's lexsort, primary key first)."""
    return (ls["hz"][j], ls["hz_soft"][j], ls["U"][j], ls["S"][j], ls["clash_p"][j], not ls["keep"][j],
            not ls["mkeep"][j], not ls["V"][j], ls["sk_n"][j], -ls["sk_f"][j], ls["sk_c"][j], ls["Pc"][j],
            ls["Pcm"][j], ls["Pf"][j], -ls["t_c"][j], -ls["t_hit"][j], -ls["J"][j])


@pytest.mark.parametrize("fr,pc", [("share", False), ("seen", False), ("seen_cf", False), ("share", True),
                                   ("seen_cf", True)])
def test_forced_risk_takes_the_least_row_on_the_stacked_keys(params, arena, fr, pc):  # noqa: F811
    """On a FORCED_RISK tick (no escape check) the chosen row is the least of the choice set on the stacked keys; the
    keys of a switch that is off are 0 on every row."""
    n = 0
    for x in XS:
        r, pl = _tick(params, arena, x, forced_rank=fr, commit_rank=pc)
        if not r.forced_risk:
            continue
        ls = pl.last_sel
        sel = np.flatnonzero(ls["sel"])
        assert r.idx in sel and ls["chosen"] == r.idx
        assert min(_key(ls, j) for j in sel) == _key(ls, r.idx)
        if fr == "share":
            assert not ls["sk_n"].any() and not ls["sk_c"].any()
        if fr != "seen_cf":
            assert not ls["sk_c"].any()
        if not pc:
            assert not ls["Pcm"].any() and not ls["Pf"].any()
        n += 1
    assert n > 0


def test_every_switch_on_runs_a_tick(params, arena):  # noqa: F811
    """Wanderer, seen_cf, commit_rank, the clash branch, escape and the terminal value together: every tick decides
    (a known row; FORCED_RISK's choice inside its choice set) and reports each track's fields."""
    for x in XS:
        r, pl = _tick(params, arena, x, crest="Wanderer", react="escape", forced_rank="seen_cf", commit_rank=True,
                      clash=True, terminal=True)
        li = pl.last_info
        assert r.idx >= 0 and r.name
        assert {"Pcm", "Pf", "seen", "seen_cf", "esc"} <= set(li)
        if r.forced_risk:
            assert pl.last_sel["sel"][r.idx]
    assert pl.audit.ticks == 1


def test_the_policy_combines_the_switches(monkeypatch):
    from ssbot.combat import forum_planner as fp
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy
    for k in ("SSBOT_FORUM_FR", "SSBOT_FORUM_REACT", "SSBOT_FORUM_AB"):
        monkeypatch.delenv(k, raising=False)
    c = ForumPlannerPolicy._fcfg()
    # the defaults the tracks left: share, react off, clash off, commit_rank on, terminal value off, T 36
    assert (c.forced_rank, c.react, c.clash) == ("share", "off", False)
    assert (c.commit_rank, c.terminal, c.T) == (fp.PC_ON, fp.TV_ON, fp.T_ENV)
    monkeypatch.setenv("SSBOT_FORUM_FR", "seen_cf")
    monkeypatch.setenv("SSBOT_FORUM_REACT", "escape")
    c = ForumPlannerPolicy._fcfg("on")
    assert (c.forced_rank, c.react, c.escape, c.clash, c.clash_branch, c.clash_tiers) == \
        ("seen_cf", "escape", True, True, True, ("GREEN",))
    monkeypatch.setenv("SSBOT_FORUM_AB", "A:fr=seen_cf,rx=escape+c;B:pc=0,fr=share,rx=off")
    assert ForumPlannerPolicy._ab_arms() == [("A", {"forced_rank": "seen_cf", "react": "escape+c"}),
                                             ("B", {"commit_rank": False, "forced_rank": "share", "react": "off"})]
    monkeypatch.setenv("SSBOT_FORUM_AB", "A:rx=fast")
    with pytest.raises(ValueError):
        ForumPlannerPolicy._ab_arms()
