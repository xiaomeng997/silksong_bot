"""Review of task 1v1 G1 / G2 (2026-10-12): regression tests for the defects the review found in the special mode
(SSBOT_FORUM_SPECIAL_MODE) and the hop rows (SSBOT_FORUM_RUNE_HOP). Each test fails on 134753a."""
import math
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import forum_v2 as v2
from ssbot.combat import special_mode as sm
from ssbot.combat import specials
from ssbot.combat.holdfilter import hold_filter_jit
from ssbot.combat.pogo_slam import SlamTimeline
from ssbot.knowledge import kinematics as kin
from tests.test_forum_planner import FLOOR, _ctx, _prefs, _reed_forecaster, _world, arena  # noqa: F401
from tests.test_special_mode import CY, _clapper, _planner, _raw, _support, _trk, params  # noqa: F401

pytestmark = pytest.mark.skipif(not specials.SpecialTable.load().entries, reason="no specials_CL_SLAM.json")
M_BOX = (32.3, FLOOR, 40.0, FLOOR + 7.0)       # E's move estimate over the whole front (test_special_mode)


@pytest.fixture
def mode_on(monkeypatch):
    monkeypatch.setattr(sm, "SPECIAL_MODE", True)
    monkeypatch.setattr(sm, "LONG", True)
    sm.BOARD.clear()
    yield
    sm.BOARD.clear()


def _tick(pl, params, rs, hx=34.0, f=None, prefix=None, hold=None):
    inner = _reed_forecaster(None, x=46.0).forecast(0.8)
    f = f or v2.V2Forecast(inner, rs)
    start = kin.initial_state(params, hx, FLOOR + params.foot)
    return pl.tick(_world(hx), start, hold or kin.HoldState.idle(1),
                   np.zeros(1, np.int64) if prefix is None else prefix, f, _prefs(None, hx), _ctx())


def test_press_certified_on_the_rows_own_lane(params, arena):
    # the strike rows' presses lie in their entries on the planner's lane; the same lanes against E far away do not
    tab = specials.SpecialTable.load()
    lut = tab.lut("CL_SLAM", sm.MODE_CERTS, rank_cert=False)
    tl = SlamTimeline.load()
    start = kin.initial_state(params, 34.0, FLOOR + params.foot)
    pre = np.zeros(1, np.int64)
    r = specials.strike_rows(params, arena, start, lut, 30, 30.0, CY, 1, tl.disp, 36, prefix=pre)
    assert len(r.cmd)
    full = np.concatenate([np.zeros((len(r.cmd), 1), np.int64), r.cmd], axis=1)
    lat, _ = hold_filter_jit(full, kin.HoldState.idle(1))
    ro = kin.rollout(start, lat, params, arena)
    pj = 1 + r.j_press + 1
    ok = sm.press_certified(lut, tl.disp, ro.pos, ro.vel, ro.flags, pj, full, 30, 30.0, CY, 1)
    assert ok.all()
    assert not sm.press_certified(lut, tl.disp, ro.pos, ro.vel, ro.flags, pj, full, 30, 45.0, CY, 1).any()


def test_continue_of_a_special_row_is_special_only_while_its_press_is_certified(params, arena, mode_on):
    pl = _planner(params, arena)
    pl.debug = True
    r = _tick(pl, params, _support({7: [M_BOX]}, _trk({7: _clapper(30.0, 1, 30)})))
    assert r.name.startswith("SPECIAL") and not r.S
    # next tick, E 1 u further on: the CONTINUE's press left its cell -> it keeps the full checks (M's danger)
    r2 = _tick(pl, params, _support({7: [M_BOX]}, _trk({7: _clapper(31.0, 1, 31)})))
    N = len(pl.last_sel["J"])
    assert pl._sctx is not None and (N - 1) not in pl._sctx.rows.tolist()
    assert pl.audit.sm_uncert >= 1 and r2.name != "CONTINUE"
    # E where it was: the CONTINUE stays special
    pl2 = _planner(params, arena)
    pl2.debug = True
    _tick(pl2, params, _support({7: [M_BOX]}, _trk({7: _clapper(30.0, 1, 30)})))
    _tick(pl2, params, _support({7: [M_BOX]}, _trk({7: _clapper(30.0, 1, 31)})))
    assert (len(pl2.last_sel["J"]) - 1) in pl2._sctx.rows.tolist()


def _late_support(trk, k_late):
    """E's move over the front on every sample; another enemy over the whole arena from look-ahead k_late on (every
    row is in contact by then: FORCED_RISK)."""
    rs = v2.RangeSupport(v2.Canvas(), v2.SAMPLE_KS, 0, None)
    rs.trk, rs.margin_mode, rs.focus, rs.dash_focus = trk, "flat:0.5", 7, None
    for iid, b, k0 in ((7, M_BOX, 0), (9, (10.0, FLOOR, 53.0, FLOOR + 20.0), k_late)):
        c, ix0, iy0 = v2.coarse(_raw(*b), 0.05, rs.cv.cell)
        for si, k in enumerate(v2.SAMPLE_KS):
            if k >= k0:
                rs.add_raw(si, iid, c, ix0, iy0, 0.5, 0.5 if k >= v2.ESC_FROM_K else None)
    rs.finish()
    return rs


@pytest.mark.parametrize("k_late", [22, 31])
def test_forced_risk_never_ranks_the_special_rows(params, arena, mode_on, k_late):
    # 134753a chose a SPECIAL row here: its first contact and share were read without M's danger
    pl = _planner(params, arena)
    pl.debug = True
    r = _tick(pl, params, _late_support(_trk({7: _clapper(30.0, 1, 30)}), k_late))
    assert r.forced_risk and pl.audit.sm_rows > 0
    assert not r.name.startswith("SPECIAL") and pl.audit.sm_forced_out == 1


def test_a_special_rows_escape_keeps_the_moves_danger(params, arena, mode_on, monkeypatch):
    # an escape command from the bounce state leaves the certified bounce (other keys): 134753a checked it against
    # the special support (M's danger dropped through the certified window); now the full escape support, and only
    # the row's own continuation (tail_ok, the certified path) reads the special one
    calls = []
    orig = sm.occ_special

    def rec(ctx, rs, q, x, y, tq, esc=False):
        calls.append(bool(esc))
        return orig(ctx, rs, q, x, y, tq, esc=esc)
    monkeypatch.setattr(sm, "occ_special", rec)
    pl = _planner(params, arena)
    pl.debug = True
    r = _tick(pl, params, _support({7: [M_BOX]}, _trk({7: _clapper(30.0, 1, 30)})))
    assert r.name.startswith("SPECIAL") and pl.audit.v2_esc_rows > 0
    assert calls and not any(calls)


def test_the_tail_follows_the_entrys_jump_past_the_horizon(params, arena):
    # the special mode's rows carry their whole template past the horizon: a jpost entry's jump runs to press + 19
    # in the template the tail check and the CONTINUE read (134753a cut it at the horizon for in-horizon presses)
    tab = specials.SpecialTable.load()
    lut = tab.lut("CL_SLAM", sm.MODE_CERTS, rank_cert=False)
    tl = SlamTimeline.load()
    start = kin.initial_state(params, 34.0, FLOOR + params.foot)
    r = specials.strike_rows(params, arena, start, lut, 10, 30.0, CY, 1, tl.disp, 36, max_rows=400, per_entry=4,
                             prefix=np.zeros(1, np.int64), long_hi=sm.LONG_PRESS_MAX)
    late = [q for q in range(len(r.cmd)) if r.entry[q].jpost and 17 < r.j_press[q] <= 34]
    assert late
    for q in late:
        j = int(r.j_press[q])
        assert ((r.full[q][j + 3:j + 19] & kin.B_JUMP) != 0).all()
