"""The person's general special rule (combat.special_mode, SSBOT_FORUM_SPECIAL_MODE; task 1v1 G1, forum.md 49): the
special support (E's move dropped, its body and hazards and every other enemy kept), the keys filter, the bounce-only
lanes of the special rows, the certified window, the fallback, the L2 strike spot."""
import math
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import forum_v2 as v2
from ssbot.combat import special_mode as sm
from ssbot.combat import specials
from ssbot.combat.attack_range import Mask
from ssbot.combat.forum_planner import ForumConfig, ForumPlanner
from ssbot.combat.planner import PlannerConfig
from ssbot.combat.pogo_slam import SlamTimeline
from ssbot.core.primitives import N_PRIM, Prim
from ssbot.knowledge import kinematics as kin
from tests.test_forum_planner import FLOOR, _ctx, _prefs, _reed_forecaster, _world, arena  # noqa: F401

CL = "Song Heavy Sentry"
pytestmark = pytest.mark.skipif(not specials.SpecialTable.load().entries, reason="no specials_CL_SLAM.json")


@pytest.fixture(scope="module")
def params():
    from ssbot.train.forum_planner_policy import CREST_PARAMS
    return kin.HeroParams.load(CREST_PARAMS["Wanderer"])          # the crest the table was built for

CY = FLOOR + 4.434                # the Clapper's position y (pogo_clapper_slam pos_above_floor)


def _raw(x0, y0, x1, y1) -> Mask:
    return Mask(np.ones((int(round((y1 - y0) / 0.05)), int(round((x1 - x0) / 0.05))), bool),
                int(round(x0 / 0.05)), int(round(y0 / 0.05)))


def _support(parts, trk, samples=v2.SAMPLE_KS):
    """A RangeSupport whose every sample holds raw world boxes per enemy {iid: [(x0, y0, x1, y1)]} (margin 0.5, in the
    escape check from ESC_FROM_K on), focus 7."""
    rs = v2.RangeSupport(v2.Canvas(), samples, 0, None)
    rs.trk, rs.margin_mode, rs.focus, rs.dash_focus = trk, "flat:0.5", 7, None
    for iid, boxes in parts.items():
        for b in boxes:
            c, ix0, iy0 = v2.coarse(_raw(*b), 0.05, rs.cv.cell)
            for si, k in enumerate(samples):
                rs.add_raw(si, iid, c, ix0, iy0, 0.5, 0.5 if k >= v2.ESC_FROM_K else None)
    rs.finish()
    return rs


def _clapper(x: float, face: int, k: int):
    return {"pos": (x, CY), "flipX": face > 0, "type_key": CL,
            "fsms": [{"name": "Control", "state": "Slam Antic", "t": k / 60.0}]}


def _trk(units, fam="CC_SLAM"):
    inst = NS(fam=fam) if fam else None                          # the tracker's instance (special_mode.in_family)
    return NS(now={iid: (CL, e, inst) for iid, e in units.items()}, tables={}, hero=None, T=0.0)


def test_keys_filter_reads_the_keys_a_row_uses():
    rows = np.zeros((3, 10), np.int64)
    rows[0, 2] = kin.B_JUMP
    rows[0, 5] = kin.B_DOWN | kin.B_ATTACK
    rows[1, :4] = kin.B_LEFT
    rows[1, 6] = kin.B_DOWN | kin.B_ATTACK
    rows[2, 1] = kin.B_DASH
    am = np.ones(N_PRIM, bool)
    am[[Prim.DASH, Prim.SILKSKILL, Prim.BIND, Prim.ATTACK_SIDE]] = False     # a partial allowlist
    assert sm.row_keys_allowed(rows, am).tolist() == [True, True, False]
    am[Prim.MOVE] = False
    assert sm.row_keys_allowed(rows, am).tolist() == [True, False, False]
    am[Prim.ATTACK_DOWN] = False
    assert not sm.row_keys_allowed(rows, am).any()


def test_special_stacks_drop_the_move_keep_the_body_hazards_and_the_others(monkeypatch):
    tl = SlamTimeline.load()
    x, face = 30.0, 1
    trk = _trk({7: _clapper(x, face, 20)})
    m_box = (x + 2.5, FLOOR, x + 9.0, FLOOR + 6.0)           # E's move (its estimate in front)
    other = (40.0, FLOOR, 41.0, FLOOR + 2.0)                 # another enemy
    rs = _support({7: [m_box], 9: [other]}, trk)
    rs.haz_raw = {7: [(si, *v2.coarse(_raw(20.0, FLOOR, 20.5, FLOOR + 0.5), 0.05, 0.1), 0.5, None)
                      for si in range(len(rs.samples))]}
    st, es = rs.special_stacks(7, list(rs.haz_raw[7]))
    sb, eb = rs.parts_stacks(sm.body_extra(rs, 7, tl, 20, x, CY, face, CL))
    st, es = st | sb, es | eb
    q = lambda stack, px, py: bool(rs._occ_stack(stack, np.array([[px]]), np.array([[py]]), np.zeros(1))[0, 0])  # noqa
    full = rs.stack
    assert q(full, x + 6.0, FLOOR + 1.1) and not q(st, x + 6.0, FLOOR + 1.1)     # the move: dropped
    assert q(st, x, FLOOR + 1.1) and q(st, x + 1.5, FLOOR + 1.1)                 # the body: kept
    assert q(st, 40.5, FLOOR + 1.1) and q(full, 40.5, FLOOR + 1.1)               # the other enemy: kept
    assert q(st, 20.2, FLOOR + 1.1)                                              # E's hazard: kept
    # the escape stack likewise (its samples from ESC_FROM_K on)
    tq = np.array([40 / 60.0])
    assert rs._occ_stack(es, np.array([[40.5]]), np.array([[FLOOR + 1.1]]), tq)[0, 0]
    # (at frame 40 the body has lunged 3.6-4.2 u: x + 8.6 is past it, inside the move's estimate)
    assert rs._occ_stack(rs.stack_esc, np.array([[x + 8.6]]), np.array([[FLOOR + 1.1]]), tq)[0, 0]
    assert not rs._occ_stack(es, np.array([[x + 8.6]]), np.array([[FLOOR + 1.1]]), tq)[0, 0]


def test_full_support_after_the_certified_window():
    trk = _trk({7: _clapper(30.0, 1, 20)})
    rs = _support({7: [(35.0, FLOOR, 38.0, FLOOR + 4.0)]}, trk)
    st, es = rs.special_stacks(7, [])
    z = np.zeros_like(st)
    ctx = NS(st_o=st, es_o=es, st_b=z, es_b=z, contact=np.array([-9, -9]), full_from=np.array([10, 1 << 30]))
    tq = np.arange(20) / 60.0
    xs = np.full((2, 20), 36.0)
    ys = np.full((2, 20), FLOOR + 1.1)
    o = sm.occ_special(ctx, rs, np.array([0, 1]), xs, ys, tq)
    assert not o[0, :10].any() and o[0, 10:].all()           # M's boxes back from the window's end on
    assert not o[1].any()


def _planner(params, arena):
    return ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                        ForumConfig(deadline_ms=math.inf, esc_deadline_ms=math.inf, v2=True))


def _tick(params, arena, parts, k=20, hx=34.0, cx=30.0, face=1, ctx=None):
    trk = _trk({7: _clapper(cx, face, k)})
    rs = _support(parts, trk)
    inner = _reed_forecaster(None, x=46.0).forecast(0.8)
    f = v2.V2Forecast(inner, rs)
    pl = _planner(params, arena)
    pl.debug = True
    start = kin.initial_state(params, hx, FLOOR + params.foot)
    r = pl.tick(_world(hx), start, kin.HoldState.idle(1), np.zeros(1, np.int64), f, _prefs(None, hx), ctx or _ctx())
    return pl, r


@pytest.fixture
def mode_on(monkeypatch):
    monkeypatch.setattr(sm, "SPECIAL_MODE", True)
    monkeypatch.setattr(sm, "LONG", True)
    sm.BOARD.clear()
    yield
    sm.BOARD.clear()


def test_off_no_special_rows(params, arena, monkeypatch):
    monkeypatch.setattr(sm, "SPECIAL_MODE", False)
    monkeypatch.setattr(specials, "SPECIALS_ON", False)
    pl, r = _tick(params, arena, {7: [(32.3, FLOOR, 40.0, FLOOR + 7.0)]})
    assert pl.audit.sm_ticks == 0 and pl.audit.spec_ticks == 0 and not sm.BOARD


def test_special_rows_safe_only_without_the_move_and_only_for_e(params, arena, mode_on):
    # E's move covers the whole front (its estimate): every normal row there is in contact; the special rows drop it
    m_box = (32.3, FLOOR, 40.0, FLOOR + 7.0)
    pl, r = _tick(params, arena, {7: [m_box]}, k=30)
    a = pl.audit
    sc = pl._sctx
    assert a.sm_ticks == 1 and a.sm_rows > 0 and sc is not None
    safe = pl.last_sel["safe"]
    assert a.sm_safe > 0 and safe[sc.rows].any()
    # the normal rows keep M's danger: no safe normal row ends inside the move's box
    box = pl.last_sel["box"]
    normal = np.setdiff1d(np.flatnonzero(safe), sc.rows)
    cxe = 0.5 * (box[normal, -1, 0] + box[normal, -1, 2])
    assert not ((cxe > m_box[0] + 0.3) & (cxe < m_box[2])).any()
    # the bounce lane from the press on (b): the hero rises after the contact on every special row
    for q, row in enumerate(sc.rows):
        c = int(sc.contact[q])
        if c + 3 < box.shape[1]:
            y = 0.5 * (box[row, :, 1] + box[row, :, 3])
            assert y[c + 3] > y[c - 1]
    b = sm.BOARD.get(7)
    assert b is not None and b["on"] and b["x"] is not None


def test_another_enemy_on_the_strike_keeps_the_rows_unsafe(params, arena, mode_on):
    m_box = (32.3, FLOOR, 40.0, FLOOR + 7.0)
    pl, r = _tick(params, arena, {7: [m_box], 9: [(31.0, FLOOR, 40.0, FLOOR + 9.0)]}, k=30)
    assert pl.audit.sm_rows > 0 and pl.audit.sm_safe == 0
    assert sm.BOARD.get(7) is not None and not sm.BOARD[7]["on"]


def test_the_keys_filter_vetoes_special_rows_without_down_attack(params, arena, mode_on):
    am = np.ones(N_PRIM, bool)
    am[Prim.ATTACK_DOWN] = False
    pl, r = _tick(params, arena, {7: [(32.3, FLOOR, 40.0, FLOOR + 7.0)]}, ctx=_ctx(allowed_mask=am))
    assert pl.audit.sm_keys_veto > 0 and pl.audit.sm_safe == 0


def test_long_rows_from_the_antic_start(params, arena):
    # at the antic's first frames the yellow entries' presses (k 42-50, in front) lie past the horizon: long rows
    # (the row is the template's first T masks, the whole template in .full)
    tab = specials.SpecialTable.load()
    lut = tab.lut("CL_SLAM", sm.MODE_CERTS, rank_cert=False)
    tl = SlamTimeline.load()
    start = kin.initial_state(params, 34.0, FLOOR + params.foot)
    r = specials.strike_rows(params, arena, start, lut, 1, 30.0, CY, 1, tl.disp, 36, max_rows=200, per_entry=2,
                             prefix=np.zeros(1, np.int64), long_hi=sm.LONG_PRESS_MAX)
    lg = [q for q in range(len(r.cmd)) if r.j_press[q] > 34]
    assert lg and all(len(r.full[q]) > 36 for q in lg)
    # every row's whole template runs LONG_POST frames past its press (review: the tail follows the certified bounce)
    assert all(r.full[q] is None or len(r.full[q]) == max(36, int(r.j_press[q]) + 1 + specials.LONG_POST)
               for q in range(len(r.cmd)))
    assert all(r.full[q] is None or np.array_equal(r.full[q][:36], r.cmd[q]) for q in range(len(r.cmd)))
    assert any(42 <= 1 + 1 + r.j_press[q] + 1 <= 51 and r.entry[q].dx0 > 0 for q in lg)     # yellow ones among them


def test_l2_strike_spot_follows_the_board(monkeypatch):
    from tests.test_forum_l2 import CC, WinFc, clapper, l2, subj, world
    from ssbot.combat import special_board
    monkeypatch.setattr(special_board, "L2_ON", True)
    s = [subj(9, CC, 35.0, y=7.45, state="Slam Antic", family="CC_SLAM", committed=True)]
    sm.BOARD.clear()
    t = l2()
    p = t.decide(world(30.0, ents=[clapper(9, 35.0, False)]), WinFc(s), None, 3)
    assert p.stance_x == pytest.approx(22.0)                      # no decision: today's step out
    sm.BOARD[9] = {"on": False, "x": None}
    t = l2()
    p = t.decide(world(30.0, ents=[clapper(9, 35.0, False)]), WinFc(s), None, 3)
    assert p.stance_x == pytest.approx(22.0)                      # no safe strike: today's step out
    sm.BOARD[9] = {"on": True, "x": 31.5}
    t = l2()
    p = t.decide(world(30.0, ents=[clapper(9, 35.0, False)]), WinFc(s), None, 3)
    assert p.stance_x == pytest.approx(31.5) and p.hit_w.get(9, 0.0) > 0
    sm.BOARD.clear()


def test_approach_codes_match_the_per_row_check():
    tl = SlamTimeline.load()
    rng = np.random.default_rng(3)
    n, L = 6, 70
    x = 30.0 + rng.uniform(-6, 6, (n, 1)) + np.cumsum(rng.uniform(-0.2, 0.2, (n, L)), axis=1)
    y = FLOOR + 1.0 + rng.uniform(0, 4, (n, 1)) + np.zeros((n, L))
    box = np.stack([x - 0.25, y - 1.0, x + 0.25, y + 1.0], axis=-1)
    flags = np.zeros((n, L), np.int64)
    pj = np.array([10, 30, 50, 60, 65, 69])
    got = sm.approach_codes(tl, 5, 30.0, CY, 1, pj, box, flags)
    want = [sm.real_approach_fail(tl, 5, 30.0, CY, 1, int(pj[q]), box[q], flags[q]) for q in range(n)]
    assert got.tolist() == want
